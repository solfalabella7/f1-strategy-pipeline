---
cursor:
  subagentId: "bc-15b6e3a7-d8bb-532f-b880-2e94deb4686e"
---

# Entrega 3 · Resumen para el grupo

Notebook: [`Entrega3_F1_v6.ipynb`](Entrega3_F1_v6.ipynb). Corre de punta a punta sin errores, con las salidas guardadas. Desde una carpeta vacía tarda unos 5 minutos: baja las vueltas del Drive y reconstruye las paradas desde OpenF1, igual que la Entrega 2. **Para la defensa, abrilo tal cual: no hace falta volver a correrlo.** Se corrió con scikit-learn 1.6.1, la versión de Colab con la que se ejecutó la v5. Primero verifiqué que con esa versión la v5 reproduce exactamente sus números (0,151 y 256/802). Con otra versión pueden moverse decimales.

## Checklist de la consigna

| Qué pide el instructivo | v5 | v6 | Dónde |
|---|---|---|---|
| Métrica declarada antes de elegir | ✅ | ✅ | §3 |
| Piso `Dummy` con la misma validación | ⚠️ solo "nunca parar" (F1 = 0) | ✅ y además "siempre parar" (0,064), que es el piso real | §3, §4 |
| Validación por entidad (carrera) | ⚠️ había folds sin LLUVIA | ✅ 4 pedazos de carreras, una con lluvia en cada uno | §3.1 |
| Todo adentro de un pipeline | ❌ la historia se armaba afuera | ✅ transformador `HistoriaCausal` | §2 |
| Logística primero, ≥2 familias más, media ± desvío | ✅ | ✅ con F1 de entrenamiento al lado | §4 |
| El complejo solo si gana por más que el desvío | ✅ | ✅ | §6 |
| Ajuste del elegido con tabla completa | ⚠️ el mejor C quedaba en el borde de la grilla | ✅ grilla ampliada y curva de validación | §5 |
| Desbalance: decisión y costo | ✅ | ✅ | §5, §7 |
| Columnas probadas que no sirvieron, con y sin cada una | ⚠️ solo con la logística | ✅ con el modelo elegido de cada paso | §8 |
| Test mirado una vez | ✅ con salvedad | ✅ con la misma salvedad: 2025 ya se había visto en versiones previas | §9 |
| Dónde se equivoca: matrices por fila y columna, reporte por clase | ✅ | ✅ y lectura de errores más profunda | §9, §10 |
| En qué se apoya: permutación en validación, chequeo de fuga | ✅ | ✅ y prueba de borrar el futuro | §2, §11 |
| Lo marcado en la Entrega 2 | ✅ | ✅ | §1 |
| Qué se probó y no anduvo | ⚠️ disperso | ✅ en una tabla | §13 |
| Respuestas a lo que se pregunta | — | ✅ | §16 |
| Que no responda una sola persona | — | ⚠️ depende del grupo | — |

## Qué se verificó y qué se cambió en cada punto

1. **Pipeline y fuga.**
   - La v5 armaba las variables históricas antes del pipeline. Ahora el primer paso del `Pipeline` es `HistoriaCausal`. Recibe solo carrera, piloto, vuelta, circuito y equipo, y lee de un registro de la carrera solo vueltas anteriores. No aprende nada en `fit`.
   - Se comprobó que las 18 variables son idénticas a las de la v5.
   - Si para 300 vueltas se borra todo lo que pasó desde esa vuelta en adelante, ninguna variable cambia: no usan el futuro.
   - Afuera quedan la limpieza del dato de origen, qué vueltas se predicen y las etiquetas. Ninguna de las tres calcula estadísticas.
2. **Validación.**
   - En 2023–2024 hay solo 4 carreras con LLUVIA. Con los 5 pedazos de la v5, **dos folds no tenían LLUVIA**, y el F1 macro de cada fold promediaba 3 o 4 clases según el caso: un fold daba 0,555 con 3 clases y 0,416 con las 4. El desvío entre folds era 0,141 y salía del reparto, no del modelo.
   - Corrección: 4 pedazos de 10 carreras, estratificando las **carreras** por "tuvo lluvia". Cada fold queda con una carrera con lluvia y las 4 clases, y los dos modelos usan los mismos pedazos.
3. **Selección de modelos.**
   - `pit_stop`: random forest, con +0,039 ± 0,026 sobre la logística.
   - `new_compound`: **también random forest**, con +0,049 ± 0,034. **Esto cambia respecto de la v5**, que elegía la logística (+0,059 ± 0,080). La ventaja era parecida; lo que bajó es el desvío. El ruido de los folds sin lluvia tapaba la diferencia.
   - Sobreajuste: el bosque memoriza. En `pit_stop` da 0,318 en entrenamiento contra 0,146 en validación; en compuesto, 0,836 contra 0,561. La curva muestra que más profundidad sube el F1 de entrenamiento sin mover el de validación. Se reporta siempre el de validación.
4. **Errores de `pit_stop`.**
   - Las falsas alarmas no son al azar. El 57 % llega 1 a 10 vueltas antes de una parada real. Vienen en 641 rachas (8 vueltas de mediana) y el 70,5 % de esas rachas termina en una parada real. El modelo detecta la **"ventana de parada"**, no la vuelta exacta.
   - Las paradas omitidas son **reactivas**: 27,9 % con safety car (contra 1,1 % de las detectadas), 22,9 % a lluvia (contra 0,7 %) y 32 % con neumático de menos de 8 vueltas.
   - Implica que el modelo no sirve como orden automática. Sí sirve como aviso, y con safety car o lluvia está ciego.
5. **Importancia por permutación** (en validación, sobre las variables ya construidas).
   - Parada: `tyre_age_prev`, `stops_before`, `used_hard`, `compound_prev`.
   - Compuesto: `lap_number`, `field_lluvia_prev`, `field_soft_prev`, `field_hard_prev`, `used_*`.
   - Ninguna usa información futura (prueba de borrar el futuro) y ninguna domina sola.
   - Contraprueba: validando al azar por filas, el F1 de parada pasa de 0,146 a 0,250 y el de compuesto de 0,561 a 0,753. Ese salto es la fuga que evita partir por carrera.
6. **Correcciones de la Entrega 2.**
   - Se mantienen `gap_to_leader` descriptivo, el histograma corregido de H1 y la H4 con INTERMEDIATE/WET.
   - A H4 se le agregó un movimiento: **solo paradas a seco**. Con safety car se monta HARD en el 35,6 % de las paradas y sin safety car en el 54,3 % (brecha 0,187). El efecto no es solo lluvia.
   - `gap_to_leader` y `safety_car_active` siguen fuera del modelo; safety car se usa solo para leer errores.
7. **Sistema integrado.**
   - Acierta parada y compuesto en **342 de 802 paradas reales (42,6 %)**: anticipa el 54,9 % de las paradas y, entre esas, acierta el compuesto en el 77,7 %.
   - El 64,1 % del modelo de compuesto solo (medido sobre paradas reales) **no es** el rendimiento del recomendador. En el sistema, las paradas a LLUVIA casi nunca se anticipan (3,5 %) y se aciertan 0. Solo el 5,6 % de las alarmas es "parada con compuesto correcto".
   - Con el mismo detector y "siempre HARD" habría 228 aciertos completos. El modelo de compuesto suma 114.
   - La suba contra la v5 (256) viene sobre todo de **más alarmas** (umbral 0,475 contra 0,55; 6.077 alarmas contra 3.625). No es un sistema mejor: avisa más.
8. **Markdown.** Todas las interpretaciones se reescribieron con los números de esta corrida y se verificaron contra las salidas. El resumen del §15 se genera solo. No quedan números de la v5 salvo donde se los cita como "v5".

## Números finales

| | Validación 2023–24 (4 folds) | Test 2025 | Piso en test |
|---|---|---|---|
| `pit_stop` · random forest, umbral 0,475 | F1 0,146 ± 0,030 (piso 0,064) | F1 0,128 · precisión 7,2 % · recall 54,9 % | "siempre parar" 0,060 |
| `new_compound` · random forest | F1 macro 0,561 ± 0,064 (piso 0,173) | F1 macro 0,638 · accuracy 64,1 % (sobre paradas reales) | "siempre HARD" 0,140 |
| Sistema completo | — | 342/802 paradas con las dos decisiones bien (42,6 %) | — |

## Pendientes y decisiones del grupo

1. **Aceptar el random forest para el compuesto.** La regla de la cátedra lo elige. Quedarse con la logística por interpretabilidad sería ir contra esa regla; no lo recomiendo.
2. **Umbral.** Se aplicó la regla escrita (máximo F1 → 0,475). La curva es plana entre 0,45 y 0,575: con 0,55, el F1 es el mismo y hay menos falsas alarmas. No lo cambié después de ver el test para no contaminarlo. Si prefieren menos alarmas, definan la regla de desempate por escrito y sepan que el test ya se miró con 0,475.
3. **Opción para la Entrega 4:** un bosque más regularizado (hoja 25 o 60) da casi el mismo F1 de validación con menos sobreajuste.
4. **Mejoras de la Entrega 4:**
   - Agregar tiempos de las vueltas anteriores, para detectar cuándo se seca la pista (el caso de Bélgica 2025, 0 de 26).
   - Mostrar la probabilidad como "ventana de parada" y avisar cuando hay safety car o lluvia.
   - En la app, enchufar el registro de la carrera en curso: `set_params(historia__registro=...)` (§14).
5. Sigue pendiente de la Entrega 2: subir a Drive el `f1_silver_pit_stops.csv` de la corrida de Airflow y cargar `ID_DRIVE_PITS`. La corrida guardada usó la reconstrucción desde OpenF1, con las mismas 2.333 × 93 filas y columnas.
6. **Campus:** el calendario (actualizado el 30/09) fija la Entrega 3 para el **28/10**. No hay avisos ni consultas nuevas sobre la entrega. Confirmen la fecha de defensa.
7. Repartir quién explica cada parte: la evaluación es individual.

## Frases para la defensa

- **Qué cambió:** "Pasamos la construcción de variables adentro del pipeline con un transformador propio, y arreglamos la validación: con 5 pedazos había folds sin lluvia y el F1 macro de cada uno medía cosas distintas."
- **Métrica:** "Solo el 3 % de las vueltas es parada. 'Nunca parar' tiene 96,9 % de accuracy, por eso usamos el F1 de la clase 'para'."
- **Piso:** "'Siempre parar' da 0,064 y nosotros 0,146: el doble. Con precisión del 7 % no alcanza para una orden automática; sirve como aviso de ventana."
- **Validación:** "Por carrera, porque las vueltas de una carrera se parecen. Al azar el número sube a 0,250, y esa diferencia es la fuga."
- **Modelo:** "El bosque le gana a la logística por más que el desvío en los dos pasos: +0,039 ± 0,026 en parada y +0,049 ± 0,034 en compuesto."
- **Una confusión:** "En Bélgica 2025 todos pasan de intermedios a MEDIUM y el modelo dice LLUVIA, porque en la vuelta anterior todo el pelotón estaba en intermedios. Le falta una señal de pista secándose."
- **Fuga:** "La variable que más pesa es la edad del neumático al **empezar** la vuelta. Borramos el futuro de 300 vueltas y ninguna variable cambió."
