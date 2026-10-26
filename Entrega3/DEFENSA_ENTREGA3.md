# Guía de defensa · Entrega 3 · Modelado

**Grupo 5K10-10** · Castillo, Expósito, Epifani, Falabella, Farías y Camacho
**Notebook:** [`Entrega3_Modelado.ipynb`](Entrega3_Modelado.ipynb) (ya ejecutado, con semilla `SEED = 42` y las salidas guardadas)

> Llegar 5 minutos antes con el notebook **abierto y ya ejecutado**. No correrlo en vivo: la grilla tarda cerca de un minuto.
> Para volver a ejecutarlo: `cd Entrega3` y `python -m jupyter nbconvert --to notebook --execute --inplace Entrega3_Modelado.ipynb`.

---

## Reparto de los 25 minutos

La nota es individual y las preguntas son dirigidas: **todos tienen que poder contestar todo**. El reparto es sólo para saber quién arranca cada parte.

| Min. | Momento | Habla | Sección del notebook |
|---|---|---|---|
| 0–2 | Qué cambió desde la Entrega 2 | **Farías** | 1 |
| 2–4 | Qué predecimos y con qué métrica | **Falabella** | 2.1, 2.2 |
| 4–7 | Cómo partimos los datos y el piso | **Epifani** | 2.3, 4 (pedazos), 5.1 |
| 7–10 | La comparación de modelos | **Castillo** | 5.2, 6 |
| 10–13 | Pesos, columnas que no sirvieron y ajuste | **Expósito** | 7, 8, 9 |
| 13–16 | El modelo final: test, dónde se equivoca y en qué se apoya | **Camacho** | 10, 11, 12 |
| 16–22 | Preguntas dirigidas | todos | — |
| 22–25 | Devolución | — | — |

---

## 0–2 · Qué cambió (Farías)

**En dos oraciones:** aplicamos las diez observaciones de la Entrega 2: sacamos safety car, amarilla, `i1_speed`, `st_speed` e `interval`, borramos las vueltas con `pit_stop` nulo, convertimos el gap al líder a segundos enteros (líder = 0, doblados = máximo) y reemplazamos el boxplot de la hipótesis 1 por un histograma. El objetivo es `new_compound`, que ya estaba planteado en la Entrega 2; lo que cambió es que WET se une con INTERMEDIATE en una clase `LLUVIA`, porque tiene sólo 7 paradas.

Datos a mano:
- 6.627 vueltas borradas por `pit_stop` nulo (carreras de 2023 sin datos de pits).
- Gap: 119 paradas doblados → 139 s (el máximo de las paradas de entrenamiento); 182 líderes → 0. **El máximo se aprende adentro del pipeline** (`GapALider.fit`), porque si se calcula con todo el dataset ya miró el test. En el CSV de vueltas el máximo es 2.500 s (bandera roja), por eso no lo usamos.
- Hipótesis 4: con safety car, el 27,9 % de las paradas monta lluvia, contra 7,4 % sin safety car. La brecha del safety car era en buena parte **lluvia**. Agregar la columna de nuevo al modelo cambia −0,002.

## 2–4 · Qué predecimos y la métrica (Falabella)

- **Qué:** el compuesto que se monta en una parada. Hay 4 clases: HARD 47 %, MEDIUM 28 %, SOFT 15 % y LLUVIA 10 %. Una fila es una parada.
- **Métrica: F1 macro.** El error caro es recomendar HARD cuando correspondía SOFT, o seco cuando llueve, y esos errores están en las clases chicas. El F1 macro le da el mismo peso a cada clase. La accuracy premia decir HARD siempre: 0,518 sin mirar ninguna columna.

## 4–7 · Partición y piso (Epifani)

- **Test = temporada 2025 entera** (815 paradas, 24 carreras), separada al principio y mirada una sola vez. Imita el uso: la app va a predecir carreras futuras.
- **Validación = `StratifiedGroupKFold(5)` con `groups=session_key`** sobre 2023–2024. Una carrera nunca queda de los dos lados (la tabla de pedazos muestra 0 carreras compartidas).
- **¿Por qué por carrera?** En una carrera paran 20 autos con la misma lluvia y el mismo safety car. Si se arma al azar, el F1 sube de 0,444 a 0,642 (logística) y de 0,558 a 0,830 (bosque), y esa diferencia es fuga.
- **¿Por qué no `TimeSeriesSplit` adentro?** Con dos temporadas, los pedazos por fecha quedan con una carrera de lluvia o ninguna. El cambio de temporada lo mide el test.
- **Piso:** «siempre HARD» da F1 macro 0,182 ± 0,023 y «al azar con proporciones» 0,242 ± 0,021. En el test, el piso da 0,142.
- El pedazo 1 no tiene LLUVIA: en 2023–2024 la lluvia está en 4 carreras. Eso explica parte del desvío.

## 7–10 · Comparación (Castillo)

| Modelo | F1 macro | Diferencia pareada vs. logística |
|---|---|---|
| Logística (la simple) | 0,444 ± 0,101 | — |
| Árbol | 0,412 ± 0,042 | −0,032 ± 0,092 |
| HistGradientBoosting | 0,497 ± 0,102 | +0,053 ± 0,081 |
| **Random forest** | **0,558 ± 0,137** | **+0,114 ± 0,070, gana en 5 de 5 pedazos** |

- Mismas columnas, mismo pipeline y mismos pedazos para todos.
- El desvío de cada modelo es grande porque los pedazos son distintos entre sí (el 2 es difícil para todos). Por eso comparamos **la diferencia pedazo a pedazo**: el bosque le gana a la logística por más que el desvío de esa diferencia. El boosting no.

## 10–13 · Pesos, columnas y ajuste (Expósito)

- **`class_weight="balanced"`:** el F1 macro del bosque pasa de 0,535 a 0,543. SOFT sube de 0,39 a 0,42 y MEDIUM de 0,50 a 0,53. Cuesta 1,7 puntos de accuracy y un poco de HARD. Lo dejamos porque mejora las clases caras.
- **Columnas que no sirvieron** (diferencia dentro del desvío ~0,13): circuito (a la logística le **resta** 0,073 porque memoriza dónde llovió), equipo, safety car, VSC, gap y posición.
- **Las que sí sirven:** estado del pelotón (sacarlo cuesta −0,054), clima (−0,029) y compuestos ya usados (−0,021, la regla de los dos compuestos).
- **Grilla de 32 combinaciones:** la mejor es `max_depth=12`, `min_samples_leaf=25`, `max_features="sqrt"`, con **0,577 ± 0,048**. Lo que más pesa es el tamaño de hoja: con hojas de 1, el F1 es 0,98 en entrenamiento y 0,55 en validación (sobreajuste). Con hojas de 25, el desvío cae de 0,137 a 0,048.

## 13–16 · Modelo final (Camacho)

- **Test, una vez: F1 macro 0,629**, accuracy 0,636 y accuracy balanceada 0,670, contra 0,142 del piso.
- **Honestidad:** en el test, la logística da 0,616. La elección se hizo con validación cruzada y no se cambia mirando el test.
- **Dónde se equivoca:**
  - LLUVIA: recall 0,84 y precisión 0,59. Casi nunca se le escapa la lluvia.
  - SOFT: lo predice de más (precisión 0,44), sobre todo en lugar de MEDIUM.
  - Últimas 10 vueltas: acierta 31 %, contra 74 % con más de 35 vueltas por delante.
  - **Ejemplo:** en Japón 2025, Lawson y Sainz (con medios de 31 vueltas y 21 vueltas por delante) montan SOFT y el modelo dice HARD. Las dos opciones cumplen la regla; decide cuántos juegos de neumáticos nuevos le quedan a cada piloto, y OpenF1 no publica ese dato.
  - **Bélgica 2025, 0 de 26:** la carrera largó con intermedios, pero OpenF1 registra el primer stint como MEDIUM. Es un error del dato de origen.
- **En qué se apoya:** la columna que más pesa es `lap_number` (−0,059 al permutarla), que junto con las vueltas programadas da las vueltas que faltan. **No es fuga** porque se conoce siempre: con 10 vueltas o menos por delante, el 48,5 % de las paradas monta SOFT, contra 9,2 % con más de 35. **Pero** parte de su peso viene de una sola carrera con lluvia en el final (Países Bajos 2023).
- Después vienen `used_medium`, el pelotón en SOFT y en lluvia, y `compound_prev`. Las columnas con importancia negativa (`used_hard`, `pit_stop_number`, `tyre_age_prev`…) quedan para medirlas con validación cruzada en la Entrega 4. No las sacamos mirando el test.

---

## Preguntas probables y respuesta corta

| Pregunta | Respuesta |
|---|---|
| ¿Por qué esa métrica? | El error caro es no ver SOFT o LLUVIA, que son clases chicas. El F1 macro las pesa igual que a HARD. |
| ¿Cuánto le gana al piso? ¿Es mucho? | 0,629 contra 0,142 en el test. Sirve como segunda opinión para el muro, no para decidir solo. |
| ¿Qué pasa si armás los pedazos al azar? | Sube a 0,83, y es fuga entre paradas de la misma carrera. |
| ¿Por qué random forest y no uno más complejo? | El boosting, que es más complejo, no le gana a la logística por más que el desvío (+0,053 ± 0,081). El bosque sí (+0,114 ± 0,070, en 5 de 5 pedazos). |
| ¿Por qué el test da más que la validación? | 2025 tiene dos carreras de lluvia claras que el modelo acierta. En la validación había un pedazo sin lluvia que castigaba. Es variación dentro del desvío. |
| ¿Qué hay adentro del pipeline? | Columnas derivadas (vueltas que faltan, avance de carrera), gap al líder con el máximo aprendido en `fit`, imputación con la mediana, escalado, one-hot y el modelo. |
| ¿Y las columnas de la vuelta anterior? ¿No están afuera del pipeline? | Son el estado de la carrera **antes** de la parada, calculado con las vueltas anteriores de **ese mismo piloto**. No usan estadísticas del dataset ni la respuesta, igual que la posición o el clima. Lo que aprende algo de los datos (máximo del gap, medianas, escalas) está adentro. |
| ¿Por qué no usar `current_compound` y `tyre_age` directamente? | En la Entrega 2 vimos fuga parcial: en algunas vueltas de pit ya muestran la goma nueva. Usamos el valor de la vuelta anterior. |
| ¿Por qué las vueltas programadas y no `session_max_lap_observed`? | La segunda se conoce al final de la carrera: en Interlagos 2024, acortada, da 69 en vez de 71. |
| ¿Qué probaron que no anduvo? | Circuito, equipo, safety car, VSC, gap y posición. También la validación al azar, el boosting y las hojas chicas. Y la edad del neumático, que esperábamos que pesara, no pesa para elegir el compuesto. |
| ¿Qué cambiarían para la Entrega 4? | Volver a medir sin las columnas con importancia negativa, corregir el primer stint de Bélgica 2025 en el pipeline, y que la app devuelva las probabilidades de cada compuesto. |
