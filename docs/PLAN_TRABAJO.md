# Plan de trabajo: dataset de estrategia de neumáticos y recomendador

## Objetivo y alcance

Pregunta del proyecto: ¿conviene entrar a boxes a cambiar neumáticos en una determinada vuelta, dadas las condiciones de carrera, el circuito y el estado de los neumáticos? Si conviene, ¿qué compuesto utilizar?

El trabajo tendrá tres resultados verificables:

1. **Entrega 1:** pipeline automático, CSV por piloto y vuelta, objetivo observado documentado, controles de calidad reales y defensa de las decisiones del grupo.
2. **Modelo de decisiones observadas:** estimar la acción que tomaron los equipos en carreras no utilizadas para entrenar. Este resultado mide reproducción de decisiones históricas, no optimalidad estratégica.
3. **Recomendador experimental:** comparar continuar frente a parar con diferentes compuestos mediante estimaciones de consecuencias, incertidumbre y restricciones explícitas.

PostgreSQL y el entrenamiento no son requisitos de `docs/Entrega1.md`. La carga relacional se incorpora como etapa posterior del proyecto. No se incluyen despliegue público ni uso durante carreras en vivo.

Este documento es un plan: no implementa correcciones, etiquetas ni modelos. El calendario y la asignación nominal quedan pendientes de la fecha de entrega y la disponibilidad del grupo.

## Punto de partida

Evidencia de la revisión del 9 de septiembre de 2026:

- 70 carreras de las temporadas 2023, 2024 y 2025; el inventario coincide con el catálogo local de carreras.
- CSV con 77.373 filas y 89 columnas, sin claves duplicadas ni columnas totalmente vacías.
- Dos ejecuciones exitosas observadas en el historial de Airflow.
- Reconstrucción temporal de Austria 2024: 1.407 filas, iguales a la salida almacenada.
- Pruebas existentes: 8 aprobadas y 1 fallida por la política de reintentos del DAG.
- Errores reproducidos en estados de pista y falsos positivos de validación.
- No existe todavía `accion_observada_proxima_vuelta` ni un modelo entrenado.
- No hay etapa de carga a PostgreSQL; las tablas consultadas están vacías.
- La configuración revisada al elaborar este plan vuelve a usar 5 segundos entre consultas y dos tareas activas. No se presupone que siga vigente el cambio transitorio a 3 segundos.

Estos números describen la salida anterior a los cambios. Cada publicación posterior deberá registrar sus propias métricas.

## Hito 1 — Contrato de datos y definición de la decisión

**Trabajo**

- Fijar la unidad de análisis: una vuelta registrada de un piloto en una carrera, identificada por `(session_key, driver_number, lap_number)`.
- Definir el momento de decisión al finalizar una vuelta `t` y el horizonte de acción durante la vuelta `t+1`.
- Verificar con datos reales cómo se relacionan `date_start`, `lap_duration`, el evento de pit y el inicio del siguiente stint. No asumir que el número de vuelta de todas las fuentes representa el mismo instante.
- Documentar cómo obtener `decision_timestamp` para una vuelta completada con tiempos utilizables. No fabricar un instante cuando falten datos o la vuelta sea ambigua.
- Conservar las vueltas incompletas en Silver con indicadores de calidad; distinguirlas de las filas elegibles para aprendizaje y evaluación.
- Crear un diccionario que indique, para cada variable, fuente, unidad, tipo, instante de disponibilidad, significado del nulo y función: identificador, predictor, etiqueta o diagnóstico.
- Separar variables retrospectivas, como `driver_last_lap_observed`, de las permitidas como predictores.

**Archivos previstos:** `docs/SILVER.md`, `docs/DATA_DICTIONARY.md` y contrato de etiquetas.

**Aceptación:** una persona del grupo puede explicar con un ejemplo qué se sabe al decidir, qué se observa después y por qué no se usa información futura como predictor.

## Hito 2 — Ingesta y orquestación confiables

**Trabajo**

- Agregar la dependencia explícita de `land_bronze_meetings` antes de Silver.
- Configurar una sola corrida activa mientras se compartan rutas de salida entre ejecuciones.
- Mantener el margen del límite de consultas y configurar tiempos máximos de conexión/lectura; manejar reintentos de errores transitorios y respuestas de rate limit.
- Validar la estructura de la respuesta antes de dar una descarga por terminada. Distinguir una lista válida, ausencia de resultados reconocida y una respuesta inesperada.
- Escribir cada descarga en un archivo temporal y publicarla de forma atómica. Una escritura incompleta no debe convertirse en un acierto de caché.
- Verificar los archivos reutilizados. Ante corrupción, fallar con un diagnóstico y ofrecer una recuperación controlada, conservando evidencia del archivo original.
- Derivar las carreras esperadas del catálogo de sesiones filtrado por alcance; calcular faltantes y sobrantes.
- Unificar la política de reintentos del DAG y el test que la verifica.
- Conservar la posibilidad de reconstruir Silver sin red desde Bronce existente.

**Archivos previstos:** `dags/f1_strategy_pipeline.py`, `tests/dags/` y pruebas de ingesta con HTTP simulado.

**Aceptación:** una interrupción no deja un archivo final aceptado como válido; un reintento no duplica datos; las dependencias cubren todas las entradas; una segunda corrida reutiliza Bronce validado.

## Hito 3 — Corrección de transformaciones y estado de pista

**Trabajo**

- Reconstruir los estados de sesión, bandera roja, SC y VSC mediante transiciones explícitas, verificadas contra mensajes reales.
- Tratar correctamente suspensión y reinicio; evitar que un estado anterior quede activo indefinidamente.
- Verificar cuándo termina efectivamente una neutralización: un aviso de finalización no debe equipararse sin comprobación al momento de pista libre.
- Mantener las amarillas por alcance y sector. Un evento de limpieza local solo modifica el sector correspondiente.
- Distinguir ausencia de evidencia de estado inactivo. Marcar ambigüedades y limitar su uso en el dataset de decisiones.
- Revisar las uniones temporales usando objetos de fecha normalizados, no comparaciones lexicográficas de cadenas.
- Conservar la semántica de posición como último estado observado; su antigüedad por sí sola no demuestra un dato inválido.
- Mantener la distinción entre fuente ausente, registro inexistente y dato fuera de tolerancia en clima, intervalos y pits.

**Pruebas necesarias:** reinicio de Australia 2023, SC/VSC, dos sectores amarillos con limpieza de uno, eventos futuros, fechas equivalentes con formatos distintos y ausencia de timestamp.

**Aceptación:** los casos reproducidos dejan de producir estados incorrectos; las filas inciertas se identifican; las uniones usadas como predictores no incorporan eventos posteriores al momento de decisión.

## Hito 4 — Etiqueta observada y variables para la decisión

**Trabajo**

- Construir `accion_observada_proxima_vuelta` a partir de evidencia conjunta de pits y stints.
- Usar las clases `CONTINUAR`, `BOX_SOFT`, `BOX_MEDIUM`, `BOX_HARD`, `BOX_INTERMEDIATE` y `BOX_WET` cuando puedan establecerse con evidencia suficiente.
- Un cambio por otro juego del mismo compuesto sigue siendo un cambio de neumáticos. No inferirlo únicamente de un cambio en el nombre del compuesto.
- No convertir automáticamente cualquier entrada a boxes en cambio de neumáticos. Registrar y excluir de este objetivo los eventos sin cambio confirmado o con una interpretación distinta.
- Separar cambios durante interrupciones de carrera de las decisiones de parada dentro del horizonte definido.
- Comprobar que existe la vuelta consecutiva `t+1`; no desplazar etiquetas a través de huecos ni entre pilotos o sesiones.
- Para vueltas finales, horizonte no observable, fuentes ausentes o compuesto desconocido, usar etiqueta nula con un motivo explícito. No asignar `CONTINUAR` por defecto.
- Incorporar `decision_eligible`, `target_available` y motivos de exclusión. La falta de etiqueta futura no debe convertirse en una variable predictora.
- Construir variables disponibles al decidir: compuesto actual, edad del neumático, ritmo reciente, circuito, clima, posición, diferencias temporales y estado de pista.
- Calcular ventanas históricas ordenadas por piloto y sesión; excluir vueltas futuras de cada agregación. Revisar el tratamiento de pits, interrupciones y vueltas atípicas en el ritmo reciente.
- Consultar clima, intervalos y estado de pista al instante de decisión definido, sin reutilizar inadvertidamente una unión anclada a otro instante.
- Mantener una lista explícita de predictores permitidos. No incluir como entradas fechas/duraciones de la parada objetivo, el compuesto siguiente ni resultados finales de carrera.

**Salidas:** Silver enriquecido, etiqueta documentada, distribución de clases y reporte de cobertura/exclusiones. El CSV de la entrega debe señalar claramente la columna objetivo y sus nulos.

**Aceptación:** inspección trazable de ejemplos positivos, negativos y ambiguos; una fila no puede recibir información futura entre sus predictores; los nulos de objetivo tienen una explicación contabilizada.

## Hito 5 — Calidad, pruebas y publicación del dataset

**Trabajo**

- Centralizar las reglas de calidad utilizadas por el DAG y `verify_quality_criteria.py`.
- Comprobar efectivamente clave completa y única, más de 1.000 filas, al menos 5 columnas útiles, mezcla de tipos, nulos cuantificados y ausencia de columnas totalmente vacías en el CSV de entrega.
- Usar un esquema de tipos explícito; diferenciar representación en CSV de los tipos que se obtienen al cargarlo.
- Agregar controles de cobertura de carreras, integridad de uniones, coherencia temporal, etiquetas y estados de pista.
- Diferenciar errores que impiden publicar de advertencias justificadas. Los fallos determinísticos de integridad deben bloquear la salida; no fijar umbrales arbitrarios de cobertura sin analizar el dato.
- Comprobar con entradas deliberadamente inválidas que el verificador falla y devuelve un código de salida no exitoso.
- Añadir pruebas de integración de Bronce a CSV con casos pequeños representativos, además de pruebas de funciones usadas realmente en producción.
- Generar salidas en una ubicación provisional y publicar el conjunto validado con un manifiesto que identifique versión de código, entradas, hashes, alcance y métricas. No mezclar archivos de distintas ejecuciones ni validar un CSV antiguo como si fuera nuevo.
- Comparar dos reconstrucciones con las mismas entradas; los datos deben coincidir. Separar la fecha de ejecución del contenido determinístico del dataset.

**Aceptación:** pruebas aplicables aprobadas; un lote inválido no obtiene estado de calidad exitoso; CSV y reporte corresponden a la misma ejecución; Bronce se conserva.

## Hito 6 — Cierre y defensa de la Entrega 1

**Trabajo**

- Actualizar el README para distinguir lo implementado de lo previsto y documentar los comandos reproducibles.
- Preparar una ficha con unidad de análisis, clave, objetivo observado, columnas útiles, distribución de clases y explicación de los principales nulos.
- Documentar que predecir decisiones observadas no equivale a demostrar cuál habría sido la mejor estrategia.
- Ejecutar el pipeline corregido y conservar una corrida completa en verde con su CSV, manifiesto y reporte.
- Llevar el entorno iniciado y el archivo listo para abrir. No depender de una descarga durante la exposición.
- Ensayar con preguntas cruzadas: cada integrante explica ingesta, transformaciones, etiquetas, calidad y repetibilidad.

**Guion de 20 minutos:** 0–2 problema/fuente/fila; 2–7 DAG; 7–12 CSV y calidad; 12–18 preguntas individuales; 18–20 devolución.

**Aceptación de la Entrega 1:** entorno disponible, corrida exitosa del código corregido, CSV con los requisitos medibles y grupo preparado para defender sus decisiones. Los hitos siguientes no bloquean esta entrega.

## Hito 7 — Persistencia relacional del proyecto completo

**Trabajo**

- Definir qué tablas almacenan registros de fuente y cuáles datos enriquecidos; no presentar el esquema RAW como si ya representara Silver.
- Ajustar tipos, claves y restricciones a los datos observados. Preservar valores originales cuando una conversión numérica pierda significado.
- Implementar carga transaccional e idempotente, respetando el orden de las relaciones.
- Añadir una identidad de evento adecuada para evitar duplicados de race control entre cargas.
- Gestionar conexión y configuración fuera del código de carga; documentar migraciones del esquema.
- Verificar que los recuentos, claves y valores cargados coinciden con los archivos de la versión publicada.

**Aceptación:** repetir la carga no cambia el número de registros ni duplica eventos; un error revierte la operación afectada; las tablas son consultables y trazables al dataset.

## Hito 8 — Modelo de decisiones históricas

**Trabajo**

- Congelar una versión del dataset y separar entrenamiento, validación y prueba por carreras completas y en orden temporal. Como punto de partida, evaluar 2023/2024/2025 para esas particiones, sujeto a cobertura suficiente.
- Ajustar imputación, escalado y codificaciones solo con entrenamiento. Las etiquetas futuras se usan para supervisión, nunca como predictores.
- Medir primero una referencia simple, incluida la predicción de la clase mayoritaria.
- Evaluar un clasificador multiclase o dos etapas: probabilidad de cambiar neumáticos y compuesto condicionado al cambio. Elegir según resultados de validación y cobertura de clases.
- Medir precisión y exhaustividad de las paradas, F1 por clase/macro, matriz de confusión y calibración cuando se publiquen probabilidades. La exactitud global sola es insuficiente ante muchas vueltas sin parada.
- Desglosar resultados por carrera, compuesto y condiciones; reportar explícitamente clases con pocos ejemplos.
- Fijar el criterio de selección con validación antes de consultar la prueba final.

**Aceptación:** evaluación reproducible en carreras no utilizadas para entrenar, comparación contra referencias simples y límites documentados. Si no mejora las referencias, se informa el resultado; no se etiqueta como recomendador óptimo.

## Hito 9 — Evaluación de alternativas y recomendador experimental

**Trabajo**

- Definir la función objetivo antes de optimizar. Propuesta inicial: minimizar el tiempo restante esperado de carrera; cualquier cambio hacia posición final exige un modelo adicional de interacción y tráfico.
- Modelar ritmo y evolución de neumáticos, pérdida de tiempo en boxes, estado de pista y tráfico. No interpretar el ritmo observado como degradación pura sin considerar otros factores.
- Delimitar las acciones factibles según condiciones, reglas aplicables y juegos disponibles. Verificar fuentes oficiales para las reglas; si el inventario de neumáticos no está disponible, declarar supuestos y restringir el alcance.
- Comparar continuar con parar usando distintos compuestos sobre un horizonte explícito. Considerar también las decisiones posteriores, evitando asumir sin análisis que una parada actual es la última de la carrera.
- Integrar incertidumbre sobre clima, neutralizaciones y predicciones; evitar usar el futuro real de la carrera como si ya se conociera al decidir.
- Evaluar primero componentes observables en carreras reservadas y después estrategias en escenarios simulados con referencias simples.
- Reportar ganancias como estimaciones del modelo: la alternativa no ejecutada no tiene un resultado histórico directamente observable. No inferir beneficio causal solo por coincidir con decisiones del equipo o por ganar dentro del propio simulador.
- Entregar una salida reproducible con acción sugerida, alternativas, diferencia estimada de tiempo, incertidumbre y supuestos. Permitir abstención cuando falte información o las alternativas sean indistinguibles.

**Aceptación:** evaluación de componentes y sensibilidad documentadas; acciones trazables a datos y supuestos; comparación fuera del conjunto de ajuste; límites claros sobre disponibilidad de datos y validez de las estimaciones.

## Orden de ejecución y coordinación

1. Completar el contrato del hito 1.
2. Corregir ingesta y transformaciones de los hitos 2 y 3.
3. Construir las etiquetas y variables del hito 4.
4. Consolidar calidad y publicación en el hito 5.
5. Cerrar y ensayar la Entrega 1 con el hito 6.
6. Completar persistencia, modelo histórico y recomendador con los hitos 7, 8 y 9. El entrenamiento desde archivos puede avanzar sin depender de PostgreSQL, siempre sobre una versión validada.

La ingesta y la corrección del estado de pista pueden distribuirse entre integrantes después de acordar el contrato. La documentación acompaña cada cambio. Las etiquetas dependen de resolver primero la semántica temporal; el entrenamiento depende de calidad y separación temporal verificadas.

Las mejoras de rendimiento se realizarán si la medición muestra que son necesarias; por ejemplo, indexar eventos de race control una vez por sesión. No condicionan la entrega a una reestructuración completa del proyecto.

## Decisiones pendientes

- Fecha de la Entrega 1 y disponibilidad de integrantes, para convertir los hitos en un calendario.
- Confirmar el contrato temporal con ejemplos reales antes de fijar las etiquetas.
- Ratificar para la etapa experimental la función objetivo propuesta y el alcance inicial de condiciones de carrera.

Las carencias de datos se documentarán como tales. Ninguna fecha límite convierte una hipótesis sin validar en un resultado comprobado.
