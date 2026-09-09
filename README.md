# F1 Strategy Pipeline

Pipeline de datos para estudiar decisiones de neumáticos en carreras de Fórmula 1.

La pregunta del proyecto es: **¿conviene entrar a boxes a cambiar el compuesto en una determinada vuelta, dadas las condiciones de carrera, el circuito y el estado actual de los neumáticos? Si conviene, ¿a qué compuesto cambiar?**

La fuente es la API pública [OpenF1](https://openf1.org/). El pipeline conserva las respuestas originales en Bronce, construye un dataset Silver por piloto y vuelta, y etiqueta la acción observada en la vuelta siguiente. Esa etiqueta describe lo que hizo el equipo; no demuestra que haya sido la decisión óptima.

## Estado del proyecto

La Entrega 1 está implementada y validada: 70 carreras de 2023–2025, 77.373 filas, 117 columnas, 0 claves duplicadas, 0 columnas completamente vacías, 64.001 filas elegibles y etiquetadas, y 27 pruebas aprobadas.

La versión vigente se identifica en `include/output/silver/current.json`. La release validada es `c17cb51d8d3f88c45d3a823b`.

PostgreSQL, el modelo predictivo y el recomendador de alternativas son etapas posteriores. El esquema SQL está preparado, pero la Entrega 1 no carga Silver en PostgreSQL.

## Arquitectura

```text
OpenF1 API → Airflow / Astro → Bronce: include/output/bronze/
                                  ↓
                Silver versionado: include/output/silver/releases/<release_id>/
                                  ├── f1_silver_dataset.csv
                                  ├── quality.json
                                  ├── global_validation.json
                                  ├── anomalies.json
                                  └── manifest.json
```

`current.json` apunta a la última release validada. Bronce se conserva para reconstruir Silver sin consultar nuevamente la API.

## Unidad de análisis y etiqueta

Una fila representa una vuelta registrada de un piloto en una carrera. La clave es `(session_key, driver_number, lap_number)`. El instante de decisión se estima al finalizar la vuelta `t`, usando `lap_date_start + lap_duration`; la etiqueta describe la acción observada durante la vuelta siguiente.

Las clases de `accion_observada_proxima_vuelta` son `CONTINUAR`, `BOX_SOFT`, `BOX_MEDIUM`, `BOX_HARD`, `BOX_INTERMEDIATE` y `BOX_WET`.

Cuando la parada, el inicio del stint o el instante siguiente no pueden confirmarse, la etiqueta queda nula y se informa `target_exclusion_reason`. No se asigna `CONTINUAR` por defecto.

Los predictores permitidos están definidos en `src/decisions.py::FEATURES`. Incluyen compuesto y edad actuales, ritmo histórico, circuito, clima, posición, intervalos y estado de pista disponibles hasta la decisión. No incluyen la parada futura, el compuesto siguiente ni resultados finales.

Más detalles: [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) y [docs/SILVER.md](docs/SILVER.md).

## Requisitos

- Docker Desktop o Docker Engine en ejecución.
- Astro CLI 1.40 o posterior.
- Python 3.10 o posterior para pruebas y ejecución local.

La imagen usa Astro Runtime 3.3. Las dependencias adicionales de Airflow están en `requirements.txt`.

## Ejecución con Astro

Desde la raíz del repositorio:

```bash
astro dev start
```

Abrir [http://localhost:8080](http://localhost:8080) con usuario `admin` y contraseña `admin`. Activar y ejecutar el DAG `f1_strategy_pipeline`.

El DAG comprueba el snapshot local o la fuente, descarga/reutiliza catálogos y Bronce, descubre carreras no canceladas, construye una release Silver y verifica el manifiesto, los hashes y el CSV de esa misma release.

La configuración permite una corrida activa y dos tareas activas. Las respuestas existentes se reutilizan después de validarlas; las nuevas se publican mediante escritura atómica. Los errores transitorios tienen dos reintentos y la pausa entre solicitudes es de 5 segundos.

Para detener el entorno:

```bash
astro dev stop
```

## PostgreSQL local

El `docker-compose.yml` levanta PostgreSQL 16 en `localhost:5433` con base `f1_strategy`, usuario `f1user`, contraseña `f1password` y esquema inicial `database/init/001_create_schema.sql`.

```bash
docker compose up -d
```

El esquema pertenece a la etapa relacional posterior. Actualmente no es destino automático del DAG de la Entrega 1.

## Ejecución local desde Bronce

La transformación no consulta la API y puede ejecutarse sobre el snapshot local:

```bash
python -m src.silver_pipeline --season 2024 --session-key 9550
python -m src.silver_pipeline --all
```

`--all` publica una release validada bajo `include/output/silver/releases/` y actualiza `current.json`. Para verificar una release concreta:

```bash
python verify_quality_criteria.py \
  --csv include/output/silver/releases/<release_id>/f1_silver_dataset.csv \
  --report include/output/silver/releases/<release_id>/quality-check.json
```

La validación bloquea la salida ante claves duplicadas, filas insuficientes, tipos no declarados, valores inválidos, joins futuros, estados SC/VSC simultáneos, columnas vacías o etiquetas inconsistentes.

## Pruebas

```bash
python -m pytest tests -q
astro dev pytest
```

La suite cubre transformaciones Silver, integridad del DAG, ingesta atómica, caché corrupta, inventario incompleto, etiquetas ambiguas, reinicios, amarillas por sector, joins temporales y el contrato de calidad.

## Documentación

- [docs/Entrega1.md](docs/Entrega1.md): lineamientos de la cátedra.
- [docs/ENTREGA1_DEFENSA.md](docs/ENTREGA1_DEFENSA.md): guion y preguntas para la exposición.
- [docs/RESULTADOS_ENTREGA1.md](docs/RESULTADOS_ENTREGA1.md): métricas y evidencia de la release.
- [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md): fuentes, tipos, nulos y uso de variables.
- [docs/PLAN_TRABAJO.md](docs/PLAN_TRABAJO.md): etapas posteriores, modelo y recomendador.

## Estructura principal

```text
├── dags/f1_strategy_pipeline.py
├── src/{bronze,decisions,io_utils,quality,release,silver_pipeline,track_state}.py
├── tests/
├── database/init/001_create_schema.sql
├── docs/
├── verify_quality_criteria.py
├── airflow_settings.yaml
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Límites conocidos

La acción observada no es una etiqueta causal de conveniencia. Las filas con fuente ausente o alineación temporal ambigua se excluyen del aprendizaje y se contabilizan. `tyre_age` es edad en vueltas, no una medición física de desgaste. Para recomendar una estrategia habrá que estimar las consecuencias de alternativas no ejecutadas, incorporando pérdida de boxes, tráfico, clima, neutralizaciones, horizonte e incertidumbre.
