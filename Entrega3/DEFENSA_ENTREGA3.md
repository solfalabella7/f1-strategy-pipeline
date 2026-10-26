# Guía de defensa · Entrega 3 · Modelado

**Grupo 5K10-10** · Castillo, Expósito, Epifani, Falabella, Farías y Camacho
**Notebook:** [`Entrega3_Modelado.ipynb`](Entrega3_Modelado.ipynb) (ya ejecutado, con semilla `SEED = 42` y las salidas guardadas)

> Llegar 5 minutos antes con el notebook **abierto y ya ejecutado**. No correrlo en vivo: tarda cerca de un minuto y medio.
> Para volver a ejecutarlo hacen falta los CSV de la capa Silver en `include/output/silver/` (no están en git: se generan con el DAG o con `python -m src.silver_pipeline --all`). Después: `cd Entrega3` y `python -m jupyter nbconvert --to notebook --execute --inplace Entrega3_Modelado.ipynb`.

---

## Reparto de los 25 minutos

La nota es individual y las preguntas son dirigidas: **todos tienen que poder contestar todo**. El reparto es sólo para saber quién arranca cada parte.

| Min. | Momento | Habla | Sección del notebook |
|---|---|---|---|
| 0–2 | Qué cambió desde la Entrega 2 | **Farías** | 1 |
| 2–4 | Qué predecimos y con qué métrica | **Falabella** | 2.1, 2.2 |
| 4–7 | Cómo partimos los datos y el piso | **Epifani** | 2.3, 4 (pedazos), 5.1, 6 |
| 7–10 | La comparación y por qué ganó la logística | **Castillo** | 5.2, 9, 10 |
| 10–13 | Pesos y columnas que no sirvieron | **Expósito** | 7, 8, y lo de Bélgica en la 12 |
| 13–16 | El modelo final: test, dónde se equivoca y en qué se apoya | **Camacho** | 11, 12, 13 |
| 16–22 | Preguntas dirigidas | todos | — |
| 22–25 | Devolución | — | — |

---

## 0–2 · Qué cambió (Farías)

**En dos oraciones:** aplicamos las diez observaciones de la Entrega 2 (sacamos safety car, amarilla, `i1_speed`, `st_speed` e `interval`; borramos las vueltas con `pit_stop` nulo; convertimos el gap al líder a segundos enteros con líder = 0 y doblados = máximo; reemplazamos el boxplot de la hipótesis 1 por un histograma) y corregimos un dato de OpenF1 en Bélgica 2025. El objetivo sigue siendo `new_compound`; WET se une con INTERMEDIATE en la clase `LLUVIA` porque tiene sólo 7 paradas.

Datos a mano:
- 6.627 vueltas borradas por `pit_stop` nulo (carreras de 2023 sin datos de pits).
- Gap: 119 paradas de doblados → 139 s (el máximo de las paradas de entrenamiento); 182 líderes → 0. **El máximo se aprende adentro del pipeline** (`GapALider.fit`), porque si se calcula con todo el dataset ya miró el test. En el CSV de vueltas el máximo es 2.500 s (bandera roja), por eso no lo usamos.
- Hipótesis 4: con safety car, el 27,9 % de las paradas monta lluvia, contra 7,4 % sin safety car. La brecha del safety car era en buena parte **lluvia**. Agregar la columna de nuevo al modelo cambia −0,002.
- **Bélgica 2025:** OpenF1 da un stint de INTERMEDIATE de 1 vuelta y otro de MEDIUM desde la vuelta 2, sin parada entre los dos. Es imposible. La regla que lo detecta revisa las 70 carreras y sólo encuentra esos 20 pilotos (ninguna carrera de entrenamiento).

## 2–4 · Qué predecimos y la métrica (Falabella)

- **Qué:** el compuesto que se monta en una parada. Hay 4 clases: HARD 47 %, MEDIUM 28 %, SOFT 15 % y LLUVIA 10 %. Una fila es una parada.
- **Métrica: F1 macro.** El error caro es recomendar HARD cuando correspondía SOFT, o seco cuando llueve, y esos errores están en las clases chicas. El F1 macro le da el mismo peso a cada clase. La accuracy premia decir HARD siempre: 0,518 sin mirar ninguna columna.

## 4–7 · Partición y piso (Epifani)

- **Test = temporada 2025 entera** (815 paradas, 24 carreras). Imita el uso: la app va a predecir carreras futuras.
- **Validación por carrera** sobre 2023–2024: una carrera nunca queda de los dos lados.
  - Para comparar y ajustar: `StratifiedGroupKFold(5)` con `groups=session_key`.
  - Para la comparación final: `GroupKFold` repetido 10 veces (50 mediciones). `StratifiedGroupKFold` arma casi siempre los mismos pedazos, cualquiera sea la semilla.
- **¿Por qué por carrera?** En una carrera paran 20 autos con la misma lluvia y el mismo safety car. Si se arma al azar, el F1 sube de 0,444 a 0,642 (logística) y de 0,558 a 0,830 (bosque), y esa diferencia es fuga.
- **Piso:** «siempre HARD» da 0,182 ± 0,023; «al azar con proporciones», 0,242. En el test, el piso da 0,142.

## 7–10 · Comparación y elección (Castillo)

1. **Sin ajustar** (sección 5): logística 0,444 · árbol 0,412 · boosting 0,497 · random forest 0,558. El bosque parecía ganar por +0,114.
2. **Pero era injusto:** el bosque se iba a ajustar y la logística no. Ajustamos **los dos finalistas** (sección 9):
   - logística `C=0,003`, `balanced`: **0,517** (le suma 0,07 al ajuste);
   - random forest `max_depth=12`, `min_samples_leaf=25`: **0,577**.
3. **Comparación justa** (sección 10, 50 mediciones): logística 0,503 ± 0,097 · bosque 0,542 ± 0,078 · **diferencia +0,039 ± 0,058**. El bosque gana en el 74 % de las mediciones, pero **no por más que el desvío**.
4. **Regla fijada antes de correr: se queda la logística.** Además se lee con coeficientes y da probabilidades para la app.

## 10–13 · Pesos y columnas (Expósito)

- **`class_weight="balanced"`:** en la logística, el F1 macro sube de 0,433 a 0,466 y LLUVIA de 0,21 a 0,32. La grilla lo vuelve a elegir con casi todos los `C`.
- **Columnas que no sirvieron:** circuito (a la logística le **resta** 0,073, porque memoriza dónde llovió), equipo, safety car, VSC, gap y posición, todas dentro del ruido.
- **Las que sí:** estado del pelotón, clima y compuestos ya usados.
- **Lo que probamos para Bélgica:** vueltas desde la última lluvia, tendencia del tiempo de vuelta del piloto y del pelotón. Ninguna suma (+0,001 a +0,010, con desvíos de 0,024 a 0,051). En Bélgica OpenF1 no registró lluvia durante la carrera.

## 13–16 · Modelo final (Camacho)

- **Test: F1 macro 0,651**, accuracy 0,663 y accuracy balanceada 0,693, contra 0,142 del piso. El random forest, como referencia, da 0,629.
- **Por qué el test da más que la validación (0,503):** para el test el modelo se entrena con 40 carreras y no con 32, y en la validación muchos pedazos no tienen lluvia: si el modelo predice LLUVIA una vez en esos pedazos, la clase entra con 0 y le resta un cuarto al F1 macro.
- **Transparencia (decirlo si preguntan):** el test se miró una vez en la primera versión (random forest: 0,629). Después cambiamos el modelo por la regla de la validación cruzada, no por el test, y corregimos Bélgica, que es un dato. El 0,651 se lee con esa salvedad.
- **Dónde se equivoca:**
  - LLUVIA tiene recall **0,94** y precisión 0,60. SOFT es la más difícil (F1 0,52).
  - Últimas 10 vueltas: acierta 23 %, contra 72–73 % en el resto.
  - **Ejemplo:** en Japón 2025, Lawson y Sainz (con medios de 31 vueltas y 21 vueltas por delante) montan SOFT y el modelo dice HARD. Decide cuántos juegos de neumáticos nuevos le quedan a cada piloto, y OpenF1 no publica ese dato.
  - **Bélgica 2025, 0 de 26:** con el dato corregido, el pelotón está con intermedios y el modelo dice LLUVIA, pero la pista se secaba y todos pasaron a gomas de seco. Es un punto ciego documentado.
- **En qué se apoya:**
  - **Coeficientes:** `used_medium` → HARD (+0,21); `used_hard` → MEDIUM (+0,19); `rain_so_far`, `field_wet_prev` y `humidity` → LLUVIA; la temperatura de pista → SOFT.
  - **La que más pesa es `used_medium`** (0,062 en la validación, en los 5 pedazos). **No es fuga:** se calcula con las vueltas anteriores al pit. Es la regla de los dos compuestos: el 65 % de los que ya usaron MEDIUM montan HARD, contra 26 % de los que no.
  - Sin Países Bajos 2023, `lap_number` **sube** de 0,006 a 0,048: esa carrera, con lluvia en el final, tapaba el efecto del final de carrera (89 % SOFT en las últimas 10 vueltas).

---

## Preguntas probables y respuesta corta

| Pregunta | Respuesta |
|---|---|
| ¿Por qué esa métrica? | El error caro es no ver SOFT o LLUVIA, que son clases chicas. El F1 macro las pesa igual que a HARD. |
| ¿Cuánto le gana al piso? ¿Es mucho? | 0,651 contra 0,142 en el test. Sirve como segunda opinión para el muro, no para decidir solo. |
| ¿Qué pasa si armás los pedazos al azar? | Sube a 0,64 con la logística y a 0,83 con el bosque. Es fuga entre paradas de la misma carrera. |
| ¿Por qué la logística y no el random forest, si en el test el bosque…? | En el test el bosque da **menos** (0,629). Pero la elección no sale del test: con los dos ajustados y 50 mediciones, el bosque le gana por +0,039 ± 0,058, dentro del ruido. Regla del instructivo: se queda el simple. |
| ¿Por qué cambiaron de modelo? | La primera comparación tenía el bosque ajustado contra la logística sin ajustar. Al ajustar los dos, la ventaja desapareció. |
| ¿Por qué el test da más que la validación? | Para el test se entrena con más carreras, y en la validación hay pedazos sin lluvia que castigan la clase LLUVIA. |
| ¿Por qué `C=0,003`, tan regularizado? | Con 40 carreras, la logística sin regularizar aprende patrones de carreras puntuales (F1 de entrenamiento 0,72, de validación 0,45). La curva de validación lo muestra. |
| ¿Qué hay adentro del pipeline? | Columnas derivadas (vueltas que faltan, avance de carrera), gap al líder con el máximo aprendido en `fit`, imputación con la mediana, escalado, one-hot y el modelo. |
| ¿Y las columnas de la vuelta anterior? ¿No están afuera del pipeline? | Son el estado de la carrera **antes** de la parada, calculado con las vueltas anteriores de **ese mismo piloto**. No usan estadísticas del dataset ni la respuesta. Lo que aprende algo de los datos (máximo del gap, medianas, escalas) está adentro. |
| ¿La corrección de Bélgica no es mirar el test? | La encontramos en el análisis de errores, sí. Pero corrige un dato que es físicamente imposible, con una regla que no mira el objetivo ni el modelo y que no toca ninguna carrera de entrenamiento. Y Bélgica sigue en 0 de 26: no la corregimos para mejorar el número. |
| ¿Por qué las vueltas programadas y no `session_max_lap_observed`? | La segunda se conoce al final de la carrera: en Interlagos 2024, acortada, da 69 en vez de 71. |
| ¿Qué probaron que no anduvo? | Circuito, equipo, safety car, VSC, gap y posición; la validación al azar; el random forest (dentro del ruido); las columnas de pista que se seca. Y la edad del neumático, que esperábamos que pesara, no pesa para elegir el compuesto. |
| ¿Qué cambiarían para la Entrega 4? | Mover los transformadores a un módulo para guardar el modelo, que la app devuelva las probabilidades de cada compuesto, y revisar Miami 2025 en el pipeline. |
