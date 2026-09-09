# Defensa de la Entrega 1

## Apertura: tres oraciones

Queremos estudiar cuándo conviene entrar a boxes para cambiar neumáticos y qué compuesto utilizar, según el circuito, las condiciones de carrera y el uso de los neumáticos. Nuestra fuente es OpenF1 y conservamos sus respuestas originales en Bronce para poder reconstruir el dataset sin volver a descargarlas. Una fila representa una vuelta registrada de un piloto en una carrera; la primera columna objetivo describe la acción observada durante la vuelta siguiente, no una estrategia óptima demostrada.

## Qué se entrega

- Un pipeline de Airflow que descubre carreras, descarga o reutiliza Bronce, transforma Silver y verifica el CSV.
- Un CSV con clave compuesta `(session_key, driver_number, lap_number)` y la etiqueta `accion_observada_proxima_vuelta`.
- Una versión inmutable con `manifest.json`, `quality.json`, `global_validation.json`, reportes por sesión y el CSV.
- Pruebas automatizadas de los casos que pueden invalidar los datos.
- Evidencia de la ejecución y métricas en `docs/RESULTADOS_ENTREGA1.md`.

La ruta vigente se obtiene de `include/output/silver/current.json`: el archivo `release_id` identifica `include/output/silver/releases/<release_id>/f1_silver_dataset.csv`. Los archivos antiguos directamente bajo `silver/` se conservan como históricos y no son la entrega vigente.

## La decisión y la etiqueta

Al terminar la vuelta `t`, queremos estimar si el piloto cambia neumáticos durante la vuelta `t+1`. El instante de decisión se estima como `lap_date_start + lap_duration`; se descartan para aprendizaje los tiempos ausentes o no utilizables y se distinguen las vueltas de entrada/salida de boxes.

El objetivo puede ser `CONTINUAR`, `BOX_SOFT`, `BOX_MEDIUM`, `BOX_HARD`, `BOX_INTERMEDIATE` o `BOX_WET`. Si la evidencia es insuficiente, queda nulo y se informa el motivo. La etiqueta se construye después de la carrera, usando información futura exclusivamente para definir el resultado observado. Esa información no se incluye en los predictores.

Ejemplo auditado: Austria 2024, piloto 1. Al terminar la vuelta 22, el objetivo es la parada registrada en la vuelta 23. El siguiente stint comienza en la vuelta 24 con HARD y esa vuelta figura como salida de boxes. La fecha del evento de pit puede caer dentro de la vuelta de salida: no se supone que ese timestamp sea el instante de entrada al pit lane.

Se acepta inicialmente la correspondencia conservadora pit en `L`, nuevo stint y vuelta de salida en `L+1`, con fin del stint anterior en `L`. Otras convenciones, cambios durante bandera roja, eventos múltiples y discordancias quedan fuera de la etiqueta confirmada. Cambiar a otro juego del mismo compuesto también es una acción `BOX_*`.

## Recorrido del DAG: minutos 2–7

1. `check_openf1_source`: si el snapshot local está completo, permite una ejecución sin red; si faltan entradas, comprueba la fuente.
2. `land_bronze_meetings` y `land_bronze_sessions`: conservan catálogos por temporada.
3. `discover_race_sessions`: selecciona carreras principales no canceladas y comprueba su identidad.
4. `land_bronze_*`: una tarea por endpoint; descarga cada sesión o valida y reutiliza su archivo existente.
5. `build_silver_layer`: integra datos por piloto/vuelta, reconstruye estados, calcula variables al decidir, construye etiquetas y publica solo un lote que supera calidad.
6. `validate`: verifica los hashes y el CSV de la versión exacta devuelta por la transformación.

Meetings es dependencia explícita de Silver. El DAG permite una corrida activa y dos tareas activas; la pausa entre solicitudes es de 5 segundos y los errores transitorios tienen reintentos.

## Defender los criterios: minutos 7–12

| Criterio | Evidencia a mostrar |
| --- | --- |
| Clave única | `duplicate_key_count = 0`, claves presentes y válidas. |
| Más de 1.000 filas | `total_rows` del reporte de la versión mostrada. |
| Cinco columnas útiles o más | Ejemplos: compuesto, edad del neumático, ritmo reciente, circuito, temperatura, posición y gaps. |
| Mezcla de tipos | Esquema explícito: números, categorías/texto, booleanos y fechas UTC. El CSV por sí mismo no guarda tipos. |
| Nulos conocidos | Conteos y porcentajes por columna, más motivos específicos de exclusión de etiquetas y decisiones. |
| Sin columnas totalmente vacías | `empty_columns = []` en el CSV publicado. |
| Unidad de análisis | Explicar por qué una vuelta por piloto representa un estado para tomar la decisión siguiente. |

Los flags de calidad y campos retrospectivos están disponibles para auditar, pero no todos son predictores. El listado permitido vive en `src/decisions.py::FEATURES` y se conserva en los reportes.

## Preguntas que todos deben poder responder

**¿Dónde está Bronce?** En `include/output/bronze/season=.../session=.../`, más los catálogos de cada temporada. Se conserva el cuerpo original de cada respuesta válida, incluidas ausencias reconocidas por la API.

**¿Qué ocurre al repetir?** Bronce válido se reutiliza. Misma entrada y mismo código identifican la misma versión; se verifica su integridad antes de reutilizarla. Si cambia una transformación se produce otra versión. Un fallo no mueve el puntero de la última versión aprobada.

**¿Por qué hay nulos?** No se mezclan todos los casos: no aplicable (duraciones de boxes en vueltas sin parada), fuente no disponible, ausencia de un registro anterior válido, tolerancia temporal superada o etiqueta que no puede confirmarse. El detalle está en el diccionario y los reportes.

**¿Por qué no imputamos todas las ausencias como cero?** Cero puede significar distancia temporal nula, neumático nuevo o una medición real. Usarlo para representar desconocimiento inventaría observaciones.

**¿Cómo evitamos usar el futuro?** Las condiciones se unen mediante el último evento anterior al instante de decisión. El ritmo usa solo vueltas ya observadas del piloto y stint. La parada futura, el compuesto siguiente y los resultados finales de carrera no están en la lista de predictores.

**¿La edad del neumático mide su estado físico?** Es una aproximación por vueltas completadas. No mide desgaste físico, temperaturas internas ni inventario de juegos. El ritmo reciente también está influido por tráfico, combustible y condiciones de pista.

**¿La predicción dice qué conviene?** Inicialmente reproduce una acción observada. Comparar conveniencia exige estimar el resultado de alternativas no ejecutadas, con supuestos e incertidumbre. Los resultados experimentales posteriores se evalúan y documentan por separado.

**¿Por qué dejamos etiquetas sin asignar?** Para no convertir una falta de evidencia en una falsa decisión de continuar o en una falsa parada. Se informa cuántas filas quedan disponibles para aprendizaje y qué sesgo introduce esa selección.

**¿Qué hacemos cuando termina el Safety Car?** Un aviso `IN THIS LAP` o `ENDING` no prueba que ya haya terminado. Durante esa transición marcamos el estado incierto y no lo usamos como estado confirmado para aprendizaje. Un `CLEAR` sectorizado no borra otras amarillas.

## Ensayo y preparación

- Antes de entrar: iniciar Docker/Airflow, abrir el DAG con la corrida corregida en verde y localizar el CSV de esa misma versión.
- Tener visibles las métricas del reporte, el diccionario y dos o tres ejemplos de etiquetas con sus fuentes.
- Repartir la exposición, pero rotar las preguntas de ensayo: cualquiera debe poder explicar cualquier tarea.
- Respetar el guion: 0–2 apertura; 2–7 DAG; 7–12 CSV/calidad; 12–18 preguntas; 18–20 devolución.
- No depender de una descarga durante la presentación ni mostrar como vigente un CSV histórico anterior a las correcciones.

## Fuentes y límites

La consigna local es `docs/Entrega1.md`. La referencia de los campos de origen es [OpenF1](https://openf1.org/docs/), consultada el 9 de septiembre de 2026. Las reglas de interpretación conservadora y los ejemplos temporales son decisiones del proyecto, contrastadas con su snapshot; no son una garantía de exactitud de todos los eventos de la fuente.
