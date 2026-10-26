# Guía de defensa · Entrega 3 · Modelado

**Grupo 5K10-10** · Castillo, Expósito, Epifani, Falabella, Farías y Camacho
**Notebook:** [`Entrega3_Modelado.ipynb`](Entrega3_Modelado.ipynb) (ya ejecutado, con semilla `SEED = 42` y las salidas guardadas)

> Llegar 5 minutos antes con el notebook **abierto y ya ejecutado**. No correrlo en vivo: tarda cerca de un minuto y medio.
> Para volver a ejecutarlo hacen falta los CSV de la capa Silver en `include/output/silver/` (no están en git: se generan con el DAG o con `python -m src.silver_pipeline --all`). Después: `cd Entrega3` y `python -m jupyter nbconvert --to notebook --execute --inplace Entrega3_Modelado.ipynb`.

---

## Reparto de los 25 minutos

La nota es individual y las preguntas son dirigidas: **todos tienen que poder contestar todo**. El reparto es sólo para saber quién arranca cada parte.

Los 16 minutos de exposición se reparten en **seis bloques de 2:40 cada uno**, en el orden del notebook. Los tres primeros cubren el planteo y los tres últimos el resultado, como pide el instructivo.

| Min. | Momento | Habla | Sección del notebook |
|---|---|---|---|
| 0:00–2:40 | Qué cambió desde la Entrega 2 y qué predecimos | **Farías** | 1, 2.1 |
| 2:40–5:20 | La métrica y cómo partimos los datos | **Falabella** | 2.2, 2.3, 4 (tabla de pedazos), 6 |
| 5:20–8:00 | Las columnas, el pipeline y el piso | **Epifani** | 3, 4, 5.1 |
| 8:00–10:40 | La comparación, los pesos, las columnas que no sirvieron y el ajuste | **Castillo** | 5.2, 7, 8, 9 |
| 10:40–13:20 | La elección, el test y dónde se equivoca | **Expósito** | 10, 11, 12 |
| 13:20–16:00 | En qué se apoya y por qué no da más | **Camacho** | 13, 14 |
| 16:00–22:00 | Preguntas dirigidas | todos | — |
| 22:00–25:00 | Devolución | — | — |

> **Ensayar con cronómetro.** 2:40 alcanza para los números de cada bloque, no para leer el notebook. Cada uno muestra **una tabla o un gráfico** y dice lo que significa. Si alguien se pasa, el siguiente arranca igual en su minuto.

---

## 0:00–2:40 · Qué cambió y qué predecimos (Farías)

**Qué cambió, en dos oraciones:** aplicamos las diez observaciones de la Entrega 2 (sacamos safety car, amarilla, `i1_speed`, `st_speed` e `interval`; borramos las vueltas con `pit_stop` nulo; convertimos el gap al líder a segundos enteros con líder = 0 y doblados = máximo; reemplazamos el boxplot de la hipótesis 1 por un histograma) y corregimos un dato de OpenF1 en Bélgica 2025. El objetivo no cambió.

Datos a mano:
- 6.627 vueltas borradas por `pit_stop` nulo (carreras de 2023 sin datos de pits).
- Gap: 119 paradas de doblados → 139 s; 182 líderes → 0. El máximo se aprende adentro del pipeline (lo explica Epifani).
- Hipótesis 4: con safety car, el 27,9 % de las paradas monta lluvia, contra 7,4 % sin safety car. La brecha del safety car era en buena parte **lluvia**. Agregar la columna de nuevo al modelo cambia −0,002.
- **Bélgica 2025:** OpenF1 da un stint de INTERMEDIATE de 1 vuelta y otro de MEDIUM desde la vuelta 2, sin parada entre los dos. Es imposible. La regla que lo detecta revisa las 70 carreras y sólo encuentra esos 20 pilotos (ninguna carrera de entrenamiento).

**Qué predecimos:** `new_compound`, el compuesto que se monta en una parada. Una fila es una parada. WET se une con INTERMEDIATE en la clase `LLUVIA` porque tiene sólo 7 paradas. Quedan 4 clases: HARD 47 %, MEDIUM 28 %, SOFT 15 % y LLUVIA 10 %.

## 2:40–5:20 · Métrica y partición (Falabella)

- **Métrica: F1 macro.** El error caro es recomendar HARD cuando correspondía SOFT, o seco cuando llueve, y esos errores están en las clases chicas. El F1 macro le da el mismo peso a cada clase. La accuracy premia decir HARD siempre: 0,518 sin mirar ninguna columna.
- **Test = temporada 2025 entera** (815 paradas, 24 carreras). Imita el uso: la app va a predecir carreras futuras.
- **Validación por carrera** sobre 2023–2024: una carrera nunca queda de los dos lados (la tabla de pedazos muestra 0 carreras compartidas).
  - Para comparar y ajustar: `StratifiedGroupKFold(5)` con `groups=session_key`.
  - Para la comparación final: `GroupKFold` repetido 10 veces (50 mediciones). `StratifiedGroupKFold` arma casi siempre los mismos pedazos, cualquiera sea la semilla.
  - El pedazo 1 no tiene LLUVIA: en 2023–2024 la lluvia está en 4 carreras. Eso explica parte del desvío.
- **¿Por qué por carrera? (sección 6)** En una carrera paran 20 autos con la misma lluvia y el mismo safety car. Si se arma al azar, el F1 sube de 0,444 a 0,642 (logística) y de 0,558 a 0,830 (bosque), y esa diferencia es fuga.

## 5:20–8:00 · Columnas, pipeline y piso (Epifani)

- **Columnas (sección 3):** todo lo que viene del CSV de vueltas se toma de la **vuelta anterior** del piloto, porque en la Entrega 2 vimos que `current_compound` y `tyre_age` a veces ya muestran la goma nueva en la vuelta del pit.
  - Compuesto con el que llega y su edad.
  - Compuestos ya usados en la carrera (la regla de los dos compuestos de seco).
  - Qué lleva el pelotón.
  - Clima, posición y gap.
  - Vueltas programadas en lugar de `session_max_lap_observed`, que se conoce al final (en Interlagos 2024, acortada, da 69 en vez de 71).
- **Pipeline (sección 4):** columnas derivadas, gap al líder, imputación con la mediana, escalado, one-hot y el modelo. El gap usa el máximo **aprendido en `fit`**, sólo con el entrenamiento: si se calcula con todo el dataset, ya miró el test. En el CSV de vueltas el máximo es 2.500 s (bandera roja), por eso no lo usamos.
- **Piso (sección 5.1):** «siempre HARD» da 0,182 ± 0,023; «al azar con proporciones», 0,242. En el test, el piso da 0,142.

## 8:00–10:40 · Comparación, pesos, columnas y ajuste (Castillo)

- **Comparación sin ajustar (sección 5.2):** logística 0,444 · árbol 0,412 · boosting 0,497 · random forest 0,558. Mismas columnas y mismos pedazos para todos. El bosque parecía ganar por +0,114.
- **`class_weight="balanced"` (sección 7):** en la logística, el F1 macro sube de 0,433 a 0,466 y LLUVIA de 0,21 a 0,32.
- **Columnas (sección 8):**
  - **No sirvieron:** circuito (a la logística le **resta** 0,073, porque memoriza dónde llovió), equipo, safety car, VSC, gap y posición, todas dentro del ruido.
  - **Sí sirven:** estado del pelotón, clima y compuestos ya usados.
- **Ajuste (sección 9):** la primera comparación era injusta, porque el bosque se iba a ajustar y la logística no. Ajustamos **los dos finalistas**:
  - logística `C=0,003`, `balanced`: **0,517** (el ajuste le suma 0,07, porque mucha regularización generaliza mejor a carreras nuevas);
  - random forest `max_depth=12`, `min_samples_leaf=25`: **0,577** (con hojas de 1 sobreajusta: 0,98 en entrenamiento).

## 10:40–13:20 · Elección, test y errores (Expósito)

- **Comparación justa (sección 10, 50 mediciones):** logística 0,503 ± 0,097 · bosque 0,542 ± 0,078 · **diferencia +0,039 ± 0,058**. El bosque gana en el 74 % de las mediciones, pero **no por más que el desvío**. Regla fijada antes de correr: **se queda la logística**.
- **Test (sección 11): F1 macro 0,651**, accuracy 0,663 y accuracy balanceada 0,693, contra 0,142 del piso. El random forest, como referencia, da 0,629.
  - **Por qué da más que la validación (0,503):** para el test el modelo se entrena con 40 carreras y no con 32, y en la validación muchos pedazos no tienen lluvia: si el modelo predice LLUVIA una vez en esos pedazos, la clase entra con 0 y le resta un cuarto al F1 macro.
  - **Transparencia (decirlo si preguntan):** el test se miró una vez en la primera versión (random forest: 0,629). Después cambiamos el modelo por la regla de la validación cruzada, no por el test, y corregimos Bélgica, que es un dato. El 0,651 se lee con esa salvedad.
- **Dónde se equivoca (sección 12):**
  - LLUVIA tiene recall **0,94** y precisión 0,60. SOFT es la más difícil (F1 0,52).
  - Últimas 10 vueltas: acierta 23 %, contra 72–73 % en el resto.
  - **Ejemplo:** en Japón 2025, Lawson y Sainz (con medios de 31 vueltas y 21 vueltas por delante) montan SOFT y el modelo dice HARD. Decide cuántos juegos de neumáticos nuevos le quedan a cada piloto, y OpenF1 no publica ese dato.
  - **Bélgica 2025, 0 de 26:** con el dato corregido, el pelotón está con intermedios y el modelo dice LLUVIA, pero la pista se secaba y todos pasaron a gomas de seco. Probamos tres columnas de pista que se seca y ninguna suma (+0,001 a +0,010, con desvíos de 0,024 a 0,051). Es un punto ciego documentado.

## 13:20–16:00 · En qué se apoya y por qué no da más (Camacho)

- **En qué se apoya (sección 13):**
  - **Coeficientes:** `used_medium` → HARD (+0,21); `used_hard` → MEDIUM (+0,19); `rain_so_far`, `field_wet_prev` y `humidity` → LLUVIA; la temperatura de pista → SOFT.
  - **La que más pesa es `used_medium`** (0,062 en la validación, en los 5 pedazos). **No es fuga:** se calcula con las vueltas anteriores al pit. Es la regla de los dos compuestos: el 65 % de los que ya usaron MEDIUM montan HARD, contra 26 % de los que no.
  - Sin Países Bajos 2023, `lap_number` **sube** de 0,006 a 0,048: esa carrera, con lluvia en el final, tapaba el efecto del final de carrera (89 % SOFT en las últimas 10 vueltas).
- **¿Por qué no da más?** (sección 14, todo sobre el entrenamiento):

  | Qué se compara | F1 macro |
  |---|---|
  | La mayoría de los demás en **la misma carrera**, misma situación | **0,836** |
  | La mayoría en la misma situación, en **otras carreras** | 0,500 |
  | El modelo, en carreras que no vio | 0,503 |

  - Los equipos no eligen al azar: en la misma carrera coinciden mucho. El modelo ya rinde lo mismo que la misma situación tomada de otras carreras. **Lo que falta es información de la carrera, no un modelo más complejo.**
  - Probamos darle lo que montaron los que pararon antes en la carrera: +0,034 ± 0,047, dentro del ruido.
  - Para la app: el compuesto real está **entre las dos primeras opciones en el 83 %** de las paradas (piso «HARD o MEDIUM»: 77 %).
  - **Cierre:** para la Entrega 4, sumar al pipeline los juegos de neumáticos disponibles y la nominación de Pirelli (`Entrega4/PENDIENTES.md`).

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
| ¿Por qué no da más? ¿No probaron algo más potente? | Copiar lo que se hizo en la misma situación en otras carreras da 0,500, lo mismo que el modelo. En la misma carrera los pilotos coinciden con 0,836. La diferencia es información de la carrera (juegos de neumáticos disponibles, compuestos de Pirelli, degradación), no complejidad del modelo. Por eso el random forest tampoco le gana. |
| ¿Cómo sacaron ese 0,836? ¿No es trampa? | Cada parada se compara con la mayoría de las **otras** paradas de su grupo, sin contarse a sí misma. No es un modelo usable, porque mira paradas posteriores de la misma carrera: es una cota que muestra de dónde vendría la mejora. |
| ¿Qué probaron que no anduvo? | Circuito, equipo, safety car, VSC, gap y posición; la validación al azar; el random forest (dentro del ruido); las columnas de pista que se seca; lo que montaron los que pararon antes (+0,034 ± 0,047). Y la edad del neumático, que esperábamos que pesara, no pesa para elegir el compuesto. |
| ¿Qué cambiarían para la Entrega 4? | Sumar al pipeline los entrenamientos y la clasificación para calcular los juegos de neumáticos que le quedan a cada piloto, y la nominación de Pirelli. Que la app muestre las probabilidades (el compuesto correcto está entre las dos primeras en el 83 %). El detalle está en `Entrega4/PENDIENTES.md`. |
