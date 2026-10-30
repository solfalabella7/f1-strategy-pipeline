# Guía de defensa · Entrega 3 · Modelado

**Grupo 5K10-10** · Castillo, Expósito, Epifani, Falabella, Farías y Camacho
**Notebook:** [`Entrega3_F1_v6.ipynb`](Entrega3_F1_v6.ipynb) (ya ejecutado, con semilla `SEED = 42`, scikit-learn 1.6.1 y las salidas guardadas)

> Llegar 5 minutos antes con el notebook **abierto y ya ejecutado**. No correrlo en vivo: desde una carpeta vacía tarda unos 5 minutos, porque baja las vueltas del Drive y reconstruye las paradas desde OpenF1.
> Para volver a ejecutarlo: en Colab, "Ejecutar todo" (si `f1_silver_dataset.csv` y `f1_silver_pit_stops.csv` están subidos al panel Archivos, usa esos). En local: `cd Entrega3` y `python -m jupyter nbconvert --to notebook --execute --inplace Entrega3_F1_v6.ipynb`. Con una versión de scikit-learn distinta de 1.6.1 pueden moverse decimales.

---

## Qué cambió respecto de la primera versión

Leerlo todos antes de ensayar: varias respuestas de la primera guía **ya no valen**.

| Tema | Primera versión (`Entrega3_Modelado.ipynb`) | v6 |
|---|---|---|
| Qué predice | Sólo `new_compound` | Dos pasos: `pit_stop` en cada vuelta y, si para, `new_compound`. Al final, el sistema completo |
| Variables históricas | Se armaban afuera del pipeline | Primer paso del `Pipeline`: el transformador `HistoriaCausal`, con prueba de que no usa el futuro |
| Validación | `StratifiedGroupKFold(5)` y `GroupKFold` repetido 10 veces | 4 pedazos de 10 carreras, una carrera con lluvia en cada uno. Para elegir, 3 repeticiones (12 folds) |
| Modelo de compuesto | Logística `C=0,003` (el bosque no ganaba por más que el desvío) | **Random forest** (profundidad 12, hoja 10): ahora sí gana por más que el desvío |
| Test de compuesto | F1 macro 0,651 | F1 macro **0,638** (802 paradas) |
| `gap_to_leader` | Adentro del pipeline, con el máximo aprendido en `fit` | **Fuera del modelo.** La corrección se hace sólo como análisis descriptivo |
| Hipótesis 4 | "La brecha del safety car era en buena parte lluvia" | La lluvia explica una parte, **pero en seco la brecha sigue** (HARD 35,6 % contra 54,3 %) |
| Momento de carrera | Vueltas programadas | `lap_number`. No se usa ningún total de vueltas |

**Ya no están en el notebook, no citarlos:** la tabla "por qué no da más" (0,836 / 0,500), el 83 % de acierto entre las dos primeras opciones, el ejemplo de Lawson y Sainz en Japón, los coeficientes de la logística y "lo que montaron los que pararon antes".

---

## Reparto de los 25 minutos

La nota es individual y las preguntas son dirigidas: **todos tienen que poder contestar todo**. El reparto es sólo para saber quién arranca cada parte.

Los 16 minutos de exposición se reparten en **seis bloques de 2:40 cada uno**, en el orden del notebook. Los tres primeros cubren el planteo y los tres últimos el resultado, como pide el instructivo.

| Min. | Momento | Habla | Sección del notebook |
|---|---|---|---|
| 0:00–2:40 | Qué cambió desde la Entrega 2 y qué predecimos | **Farías** | 0, 1, 1.1, 1.2, 2.1 |
| 2:40–5:20 | Las variables adentro del pipeline y la prueba de fuga | **Epifani** | 2, 14 |
| 5:20–8:00 | Las métricas, los pisos y cómo partimos los datos | **Falabella** | 3, 3.1, 8 (pedazos al azar) |
| 8:00–10:40 | La comparación, el ajuste y la elección | **Castillo** | 4, 5, 6 |
| 10:40–13:20 | El umbral, el test y los errores de parada | **Expósito** | 7, 9, 10 (parada) |
| 13:20–16:00 | Errores de compuesto, en qué se apoya y el sistema completo | **Camacho** | 10 (compuesto), 8 (ablación), 11, 12, 13 |
| 16:00–22:00 | Preguntas dirigidas | todos | — |
| 22:00–25:00 | Devolución | — | — |

> **Ensayar con cronómetro.** 2:40 alcanza para los números de cada bloque, no para leer el notebook. Cada uno muestra **una tabla o un gráfico** y dice lo que significa. Si alguien se pasa, el siguiente arranca igual en su minuto.

---

## 0:00–2:40 · Qué cambió y qué predecimos (Farías)

**Qué cambió, en dos oraciones:** aplicamos las diez observaciones de la Entrega 2 (sacamos safety car, amarilla, `i1_speed`, `st_speed` e `interval`; borramos las vueltas con `pit_stop` nulo; convertimos el gap al líder a segundos enteros con líder = 0 y doblados = máximo; reemplazamos el boxplot de la hipótesis 1 por un histograma; revisamos la hipótesis 4) y corregimos un dato de OpenF1 en Bélgica 2025. Además, el recomendador ahora tiene dos pasos: primero si para y después qué compuesto monta.

Datos a mano:
- 6.627 vueltas borradas por `pit_stop` nulo (carreras de 2023 sin datos de pits). Quedan 70.746 vueltas y 2.333 paradas.
- **Gap (sección 1.1):** 119 paradas de doblados → 139 s (el máximo de las paradas); 182 líderes → 0. El máximo de las vueltas es 2.500 s por una bandera roja, por eso no se usa. **El gap no entra al modelo:** reemplazar los "+N LAP" exige calcular un máximo con datos, y hacerlo bien por fold no mejoraba el modelo.
- **Hipótesis 4 (sección 1.2):** con safety car, el 27,9 % de las paradas monta lluvia, contra 7,4 % sin safety car (75 de 269 paradas, de 6 carreras). **Pero mirando sólo paradas a seco la brecha sigue:** con safety car se monta HARD en el 35,6 % y sin safety car en el 54,3 % (brecha 0,187). Con safety car la parada cuesta menos y se pone un neumático para menos vueltas. Es asociación, no causa. El safety car queda fuera del modelo y se usa sólo para leer errores.
- **Hipótesis 1 (sección 2.1):** histograma de `tyre_age_prev` normalizado por grupo. Las vueltas con parada tienen mediana 17 vueltas contra 11, pero las distribuciones se superponen mucho: la edad sola no decide cuándo parar.
- **Bélgica 2025:** OpenF1 da a 20 pilotos un stint de 1 vuelta y otro con otro compuesto desde la vuelta 2, sin parada entre los dos. Es imposible. La regla que lo corrige mira sólo la historia de neumáticos y paradas, nunca el compuesto que se predice.

**Qué predecimos:**
- **Paso 1, `pit_stop`:** ¿el piloto para en esta vuelta? Una fila es una vuelta. Sólo el 3 % de las vueltas tiene parada.
- **Paso 2, `new_compound`:** si para, ¿qué compuesto monta? Una fila es una parada. INTERMEDIATE y WET se unen en `LLUVIA`. Quedan 4 clases: HARD 48 %, MEDIUM 28 %, SOFT 14 % y LLUVIA 10 %.

## 2:40–5:20 · Variables adentro del pipeline y prueba de fuga (Epifani)

- **El cambio (sección 2):** en la primera versión las variables históricas se armaban antes del pipeline. Ahora el primer paso del `Pipeline` es `HistoriaCausal`:
  - **Recibe** sólo quién, dónde y cuándo: `session_key`, `driver_number`, `lap_number`, `circuit_short_name`, `team_name`.
  - **Lee** del registro de la carrera (`RegistroCarreras`, lo que la app vería en vivo) **sólo vueltas anteriores**: la última vuelta previa del piloto y la vuelta t−1 del pelotón.
  - **No aprende nada en `fit`:** no hay medias, máximos ni conteos del dataset, así que no puede pasar información de validación a entrenamiento.
  - Después siguen la imputación, el escalado, el one-hot y el modelo, reajustados en cada fold.
- **Las 18 variables:** edad y compuesto del neumático y posición de la vuelta anterior; paradas ya hechas; compuestos ya usados (`used_*`); proporción del pelotón en cada compuesto en la vuelta t−1 (`field_*_prev`); clima de la vuelta anterior; `lap_number`, circuito y equipo.
  - Todo sale de la **vuelta anterior**, porque en la Entrega 2 vimos que `current_compound` y `tyre_age` a veces ya muestran la goma nueva en la vuelta del pit.
  - El momento de carrera se mide con `lap_number`. No se usa `session_max_lap_observed`, que se conoce al final.
- **¿Cómo sabemos que no usa el futuro?**
  - **Borrar el futuro:** para 300 vueltas al azar se borra del registro todo lo que pasó desde esa vuelta en adelante, de todos los pilotos. **Ninguna variable cambia: 0 de 300.**
  - Las 18 variables son idénticas a las que se armaban afuera: no cambian los datos, cambia **dónde** se calculan.
- **Afuera quedan, a propósito:** la limpieza del dato de origen, qué vueltas se predicen (las que tienen al menos una vuelta previa del piloto) y las etiquetas. Ninguna calcula estadísticas.
- **Para la Entrega 4 (sección 14):** se guardan los dos pipelines y un archivo con columnas, umbral y clases. La app le pasa el registro de la carrera en curso con `set_params(historia__registro=...)`. El notebook carga el `.joblib` y comprueba que predice lo mismo.

## 5:20–8:00 · Métricas, pisos y partición (Falabella)

- **Métricas (sección 3):**
  - `pit_stop`: **F1 de la clase "para"**. "Nunca parar" tiene 96,9 % de accuracy en 2025 y no sirve para nada. El F1 combina precisión (cuántas alarmas son paradas reales) y recall (cuántas paradas se anticipan).
  - `new_compound`: **F1 macro**. SOFT y LLUVIA son chicas, y el F1 macro les da el mismo peso que a HARD.
- **Pisos (`DummyClassifier`, misma validación):** en parada, "nunca parar" da 0, pero el piso real es **"siempre parar": 0,064**. En compuesto, "siempre HARD" da 0,173 y "al azar con las proporciones", 0,212.
- **Partición:** se entrena con 2023–2024 (43.685 vueltas, 1.442 paradas, 40 carreras) y el test es 2025 (25.787 vueltas, 802 paradas, 24 carreras). Imita el uso: la app predice carreras nuevas.
- **El problema de los 5 pedazos (sección 3.1):** en 2023–2024 la lluvia está en sólo 4 carreras. Con `StratifiedGroupKFold(5)`, **dos folds quedaban sin LLUVIA**, y cada fold medía una cosa distinta: el fold 4 daba 0,555 promediando 3 clases y daría 0,416 con las 4. El desvío entre folds era 0,141 y salía del reparto, no del modelo.
- **La corrección:** 4 pedazos de 10 carreras, estratificando las **carreras** por "tuvo lluvia".
  - Cada fold tiene una carrera con lluvia (Países Bajos 2023; São Paulo, Gran Bretaña y Canadá 2024) y las 4 clases.
  - Ninguna carrera queda de los dos lados (0 carreras compartidas).
  - Los dos pasos usan los mismos pedazos.
  - Costo: cada entrenamiento ve 30 carreras en lugar de 32.
- **¿Por qué por carrera? (sección 8, contraprueba):** en una carrera paran 20 autos con la misma lluvia y el mismo safety car. Con pedazos al azar por filas, parada sube de **0,146 a 0,250** y compuesto de **0,561 a 0,753**. Esa diferencia es fuga: el bosque reconoce la carrera.

## 8:00–10:40 · Comparación, ajuste y elección (Castillo)

- **Comparación sin ajustar (sección 4):** mismas columnas y mismos pedazos, con el F1 de entrenamiento al lado.

  | | Logística | Árbol | Boosting | Random forest |
  |---|---|---|---|---|
  | `pit_stop` | 0,100 | 0,105 | 0,128 | **0,136** |
  | `new_compound` | 0,376 | 0,389 | 0,446 | **0,546** |

  - El boosting memoriza en compuesto: 0,999 en entrenamiento.
  - La logística por defecto también: 0,765 en entrenamiento contra 0,376 en validación, porque tiene un coeficiente por circuito y por equipo con sólo 1.442 paradas.
  - **Finalistas:** la logística (la referencia obligatoria) y el bosque (el mejor en los dos pasos).
- **Ajuste (sección 5, tabla completa):**
  - `pit_stop`: bosque con profundidad 12 y hoja 10, **0,146 ± 0,030**. Las nueve configuraciones con pesos quedan entre 0,130 y 0,146. **Sin `class_weight` el bosque da 0**: nunca predice parada. Logística: `C=0,001` balanceada, 0,110.
  - `new_compound`: bosque con profundidad 12 y hoja 10, **0,561 ± 0,064**. Logística: `C=0,0003` balanceada, 0,500. El óptimo de `C` quedó adentro de la grilla (con `C=0,0001` ya baja).
  - **Sobreajuste:** el bosque memoriza. En la curva, el F1 de entrenamiento sube con la profundidad y el de validación queda plano. Parada: 0,318 en entrenamiento contra 0,146 en validación; compuesto: 0,836 contra 0,561. Siempre se reporta el de validación. Con hoja 25 el compuesto da casi lo mismo (0,560) con menos brecha: queda como opción para la Entrega 4.
- **Elección (sección 6):** 3 semillas × 4 pedazos = 12 folds, los mismos para los dos finalistas. Regla de la cátedra: el bosque se queda sólo si su ventaja media supera el desvío de las diferencias.
  - `pit_stop`: **+0,039 ± 0,026** → random forest (gana en 10 de 12 folds).
  - `new_compound`: **+0,049 ± 0,034** → random forest (gana en 10 de 12 folds).
  - **Por qué cambia respecto de la primera versión:** la ventaja del bosque era parecida, pero los folds sin lluvia inflaban el desvío y la tapaban. Con folds comparables el desvío baja y la ventaja se ve.
  - Lectura de dominio: elegir compuesto depende de combinaciones ("todavía no usó MEDIUM y la pista está seca → MEDIUM"). Un árbol las arma solo; una logística no.

## 10:40–13:20 · Umbral, test y errores de parada (Expósito)

- **Umbral (sección 7):** con probabilidades fuera de fold de 2023–2024. Regla fijada antes: máximo F1 y, si hay empate, el umbral más alto.
  - Queda **0,475**: F1 0,140, precisión 8,4 %, recall 43,2 %.
  - La curva es casi plana entre 0,45 y 0,575: con 0,55 el F1 es el mismo (0,140), con más precisión (9,3 %) y menos recall (28,7 %).
  - No se cambió después de ver el test.
- **Test 2025, una sola vez (sección 9):**
  - `pit_stop`: F1 **0,128** contra 0,060 de "siempre parar", el doble. Precisión **7,2 %** (una de cada 14 alarmas es una parada real) y recall **54,9 %** (440 de 802 paradas). Queda un poco debajo de la validación (0,146): 2025 trae casos propios, como la salida en mojado de Bélgica.
  - `new_compound` (sobre las paradas reales): F1 macro **0,638** contra 0,140 del piso; accuracy 64,1 % contra 39,0 %. Por clase: HARD 0,72, LLUVIA 0,72, MEDIUM 0,59, SOFT 0,52. Las confusiones son entre compuestos vecinos (MEDIUM→SOFT 56, HARD→MEDIUM 52) y propone SOFT de más (precisión 45 %).
  - **Transparencia (decirlo si preguntan):** versiones anteriores del grupo ya habían mirado 2025, así que no es un test virgen a nivel proyecto. En esta versión no se usó para retocar nada.
- **Errores de parada (sección 10):**
  - **Falsas alarmas (5.637):** el 21,6 % llega 1 a 3 vueltas antes de una parada real y el 35,3 %, 4 a 10 vueltas antes. Vienen en **641 rachas** (8 vueltas de mediana) y el **70,5 %** termina en una parada real. El modelo detecta la **"ventana de parada"**, no la vuelta exacta.
  - **Ejemplo:** Ocon en Canadá, en HARD desde la largada. La alarma se prende en la vuelta 21 y su única parada llega 36 vueltas después.
  - **Paradas omitidas (362):** son **reactivas**. Con safety car el 27,9 % (contra 1,1 % de las detectadas), a lluvia el 22,9 % (contra 0,7 %), con neumático de menos de 8 vueltas el 32 % (contra 3,2 %).
  - Con 3 vueltas de tolerancia casi no cambia (54,9 % → 56,6 %): lo que se escapa, se escapa entero.
  - **Qué implica:** no sirve como orden automática. Sirve como aviso de "se abrió la ventana", y con safety car o lluvia está ciego.

## 13:20–16:00 · Errores de compuesto, en qué se apoya y sistema completo (Camacho)

- **Errores de compuesto (sección 10):**
  - **Bélgica 2025, 0 de 26:** todo el pelotón larga con intermedios y pasa a seco entre las vueltas 11 y 13. El modelo ve `field_lluvia_prev = 1` y dice LLUVIA. No sabe que la pista se seca: eso lo dirían los tiempos de vuelta recientes, que no son columnas del modelo.
  - También cuestan Mónaco (39 %) y Canadá (43 %), donde pesa más la posición en pista y el clima del momento.
  - **Aprendió la regla de los dos compuestos:** en seco, si todavía no usó MEDIUM, propone MEDIUM el 79 % de las veces; si ya lo usó, propone HARD (61 %) o SOFT (33 %).
- **En qué se apoya (sección 11, permutación en validación):**
  - Parada: `tyre_age_prev` (0,028, en los 4 folds), `stops_before`, `used_hard` y `compound_prev`. Neumático viejo y pocas paradas hechas: cerca de parar.
  - Compuesto: `lap_number` (0,049), `field_lluvia_prev` (sólo en 2 de 4 folds: depende de qué carrera con lluvia tocó), `field_soft_prev`, `field_hard_prev`, `used_hard`, `stops_before` y `used_medium`.
  - **Ninguna usa el futuro** (prueba de borrar el futuro) y ninguna domina sola.
- **Ablación (sección 8):** se saca un grupo de columnas por vez. Ninguna caída supera el desvío. En compuesto lo que más resta es el pelotón (−0,049) y `lap_number` (−0,046). Sacar `compound_prev`, `used_*` o el clima sube un poco (+0,014 a +0,016), pero dentro del ruido. Se dejan todas.
- **Sistema completo (sección 12):** el sistema propone compuesto sólo si recomienda parar.
  - Acierta parada y compuesto en **342 de 802 paradas (42,6 %)**: anticipa el 54,9 % y, entre esas, acierta el compuesto en el 77,7 %.
  - Las paradas a LLUVIA casi nunca se anticipan (3,5 %), así que el sistema no acierta **ninguna**, aunque el modelo de compuesto solo acierta el 75,6 % de ellas.
  - Con el mismo detector y "siempre HARD" habría 228 aciertos: el modelo de compuesto suma **114**.
  - Sólo el 5,6 % de las 6.077 alarmas es "parada con el compuesto correcto".
- **Cierre (sección 13):** no funcionó entrenar sin compensar el desbalance, el árbol, el boosting ni validar al azar. Quedan sin resolver las paradas reactivas y la pista que se seca. Para la Entrega 4: tiempos de las vueltas anteriores, mostrar la probabilidad como "ventana de parada", avisar con safety car o lluvia y enchufar el registro de la carrera en curso.

---

## Preguntas probables y respuesta corta

| Pregunta | Respuesta |
|---|---|
| ¿Por qué esa métrica? | En parada, sólo el 3 % de las vueltas es parada: "nunca parar" tiene 96,9 % de accuracy. El F1 de "para" combina no parar de más con no perderse paradas. En compuesto, F1 macro, porque SOFT y LLUVIA son chicas y valen lo mismo que HARD. |
| ¿Cuánto le gana al piso? ¿Es mucho? | Parada: 0,128 contra 0,060 en el test, el doble, pero con precisión del 7 % no alcanza para una orden automática; sirve como aviso de ventana. Compuesto: 0,638 contra 0,140. |
| ¿Qué pasa si armás los pedazos al azar? | Parada sube de 0,146 a 0,250 y compuesto de 0,561 a 0,753. Es fuga entre vueltas de la misma carrera. |
| ¿Por qué 4 pedazos y no 5? | Hay 4 carreras con lluvia en 2023–2024. Con 5 pedazos dos folds quedaban sin LLUVIA y el F1 macro promediaba 3 clases en unos y 4 en otros. Con 4, cada fold tiene una carrera con lluvia. |
| ¿Por qué el random forest y no la logística? | Le gana por más que el desvío en los dos pasos: +0,039 ± 0,026 en parada y +0,049 ± 0,034 en compuesto, en 12 folds. Es la regla de la cátedra. |
| ¿Por qué cambiaron de modelo respecto de la primera versión? | Antes la ventaja del bosque quedaba dentro del ruido porque había folds sin lluvia. Al arreglar los pedazos el desvío bajó y la ventaja se ve. La elección sale de la validación, no del test. |
| ¿El bosque no sobreajusta? | Sí: 0,836 en entrenamiento contra 0,561 en validación en compuesto. Por eso se reporta siempre la validación por carrera. Más profundidad sube el entrenamiento sin mover la validación. Un bosque con hoja 25 da casi lo mismo con menos brecha. |
| ¿Por qué el umbral 0,475 y no 0,5? | Es la regla fijada antes: máximo F1 fuera de fold. La curva es plana entre 0,45 y 0,575. Con 0,55 habría menos alarmas con el mismo F1, pero no la cambiamos después de ver el test. |
| ¿Qué hay adentro del pipeline? | `HistoriaCausal` (arma las 18 variables desde vueltas anteriores), imputación, escalado, one-hot y el modelo. Recibe sólo carrera, piloto, vuelta, circuito y equipo. |
| ¿Cómo saben que no hay fuga? | `HistoriaCausal` no aprende nada en `fit`. Borramos el futuro de 300 vueltas y ninguna variable cambió. Y validar al azar infla el número, validar por carrera no. |
| ¿La variable que más pesa no es fuga? | En parada pesa `tyre_age_prev`, la edad al **empezar** la vuelta, que sale de la vuelta anterior. La edad de la vuelta del pit, que sí tenía fuga parcial, no se usa. |
| ¿Por qué sacaron el gap al líder del modelo? | Reemplazar "+N LAP" por un máximo exige calcularlo con datos. Hacerlo bien por fold no mejoraba el modelo. La corrección pedida está hecha, como análisis descriptivo. |
| ¿Y el safety car? | Fuera del modelo, como pidió el docente. Lo usamos para leer errores: el 27,9 % de las paradas que se escapan son con safety car. |
| Si sacar `used_*` sube el F1, ¿por qué dicen que aprendió la regla de los dos compuestos? | La subida (+0,016) está dentro del desvío (0,064). La información se repite en `stops_before` y `compound_prev`, así que sin `used_*` el bosque la reconstruye. Con `used_*` adentro, la usa: propone MEDIUM el 79 % de las veces si todavía no lo usó. |
| ¿Por qué el test de compuesto da más que la validación? | Para el test se entrena con las 40 carreras y no con 30. El número que estima el rendimiento es el de validación. |
| ¿La corrección de Bélgica no es mirar el test? | Corrige un dato físicamente imposible (un stint nuevo sin parada), con una regla que no mira el objetivo ni el modelo. Y Bélgica sigue en 0 de 26: no mejora el número. |
| ¿Por qué el sistema completo da 42,6 % si el compuesto acierta 64,1 %? | El 64,1 % es "si alguien me dice que hay parada". En el sistema el compuesto sólo juega en las paradas que el primer paso anticipa, y las de lluvia casi nunca se anticipan. |
| ¿Qué probaron que no anduvo? | Entrenar sin pesos de clase (no predice paradas), árbol y boosting (debajo del bosque; el boosting memoriza), la logística sin regularizar, validar al azar y sacar grupos de columnas (todo dentro del ruido). |
| ¿Qué cambiarían para la Entrega 4? | Tiempos de las vueltas anteriores para detectar la pista que se seca (Bélgica), la probabilidad como "ventana de parada", un aviso con safety car o lluvia y el registro de la carrera en vivo con `set_params(historia__registro=...)`. |
