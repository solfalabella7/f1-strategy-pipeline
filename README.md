# f1-strategy-pipeline

Pipeline de datos para analizar y modelar estrategias de neumáticos de Fórmula 1 utilizando la API pública [OpenF1](https://openf1.org/), Apache Airflow y PostgreSQL.

---

## 🏎️ Descripción del Proyecto

El objetivo de este proyecto es construir un pipeline de datos robusto, reproducible y validado según los principios de **DataOps** y arquitectura **Medallion (Data Lakehouse)** para analizar decisiones de paradas en boxes, degradación de neumáticos y ritmo de carrera en las temporadas 2023, 2024 y 2025.

El pipeline genera **dos datasets analíticos complementarios en la capa Silver**:

1. **`f1_silver_dataset.csv` (Dataset de Vueltas)**:  
   - **Unidad de análisis:** 1 fila = 1 vuelta de un piloto en una carrera.
   - **Dimensiones:** 77.373 filas × 89 columnas.
   - **Clave primaria:** `(session_key, driver_number, lap_number)` (0 duplicados).

2. **`f1_silver_pit_stops.csv` (Dataset de Paradas en Boxes)**:  
   - **Unidad de análisis:** 1 fila = 1 parada en boxes de un vehículo en una carrera.
   - **Dimensiones:** 2.333 filas × 93 columnas.
   - **Clave primaria:** `(session_key, driver_number, lap_number, pit_index)` (0 duplicados).
   - **Variable resuelta:** `new_compound` (compuesto de neumático montado tras la parada, determinado emparejando la detención con el stint de salida sin asumir cambios arbitrarios).

```
OpenF1 API (v1)
      │
      ▼ (Ingesta HTTP con control de rate-limit, reintentos e idempotencia)
[Capa Bronce] ───► JSONs inmutables en include/output/bronze/
      │
      ▼ (Limpieza determinística, uniones temporales As-Of y resolución de paradas/stints)
[Capa Silver] ───► laps.csv / pit_stops.csv y reportes de calidad en include/output/silver/
      │
      ├───────────────┬─────────────────┐
      ▼               ▼                 ▼
f1_silver_dataset.csv  f1_silver_pit_stops.csv  PostgreSQL 16 (Esquema relacional)
```

---

## 🛠️ Tecnologías

- **Python 3.10+**: Lógica de transformación, uniones temporales y scripts analíticos.
- **Apache Airflow (vía Astronomer / Astro Runtime 3.3)**: Orquestación del flujo de datos con la TaskFlow API.
- **PostgreSQL 16**: Base de datos relacional para consulta e indexación de telemetría y eventos.
- **Docker & Docker Compose**: Contenedorización de PostgreSQL y servicios de Airflow.
- **OpenF1 API**: Fuente pública de telemetría, tiempos de vuelta, clima y radio de dirección de carrera.

---

## 📋 Prerrequisitos

Asegúrate de contar con las siguientes herramientas instaladas en tu sistema:

1. **Docker Desktop** (en Windows/Mac) o **Docker Engine** (en Linux/WSL2), con el motor en ejecución.
1. **Docker Desktop** (en Windows/Mac) o **Docker Engine** (en Linux/WSL2), con el motor en ejecución.  
   *Nota para Windows:* Asegúrate de que Docker Desktop esté abierto y con el motor iniciado (*Engine running*). Si recién lo instalaste o tu terminal no reconoce `docker`, reinicia la terminal o editor para refrescar el `PATH`.
2. **Astro CLI** (v1.40+): Utilizado para gestionar el entorno de desarrollo de Airflow.  
   *Instalación en Windows (winget):* `winget install Astronomer.Astro`  
   *Instalación en macOS/Linux:* `brew install astro` o vía curl según la [documentación oficial](https://www.astronomer.io/docs/astro/cli/install-cli).
3. **Python 3.10 o superior** (para pruebas locales o ejecución directa de la capa Silver).

---

## 🚀 Puesta en Marcha

### 1. Iniciar la Base de Datos (PostgreSQL)

Para levantar el contenedor de PostgreSQL con el esquema relacional inicializado automáticamente:

```bash
docker compose up -d
```

* **Host**: `localhost`
* **Puerto**: `5433` (mapeado al puerto interno 5432)
* **Base de datos**: `f1_strategy`
* **Usuario**: `f1user`
* **Contraseña**: `f1password`
* **DDL / Esquema**: Se ejecuta automáticamente desde [`database/init/001_create_schema.sql`](database/init/001_create_schema.sql).

---

### 2. Iniciar el Orquestador (Apache Airflow)

El entorno de Airflow está empaquetado como un proyecto de Astro CLI:

1. Inicia el entorno local de desarrollo:
   ```bash
   astro dev start
   ```
   *(Este comando descarga la imagen del Runtime, compila las dependencias de `requirements.txt` y levanta el Webserver, Scheduler, Triggerer y base de datos de metadatos).*

   > **💡 Solución de problemas comunes al iniciar:**
   > - **`Failed to find a container runtime`**: Docker Desktop no está en ejecución o la ruta a `docker.exe` no está cargada en el `PATH` de la terminal activa. Verifica ejecutando `docker version`.
   > - **`this is not an Astro project directory`**: Falta la carpeta de configuración `.astro/` en el proyecto. Puedes regenerarla ejecutando `astro dev init -f`.

2. Abre tu navegador e ingresa a:
   * **URL**: [http://localhost:8080](http://localhost:8080)
   * **Usuario**: `admin`
   * **Contraseña**: `admin`

3. **Disparar el Pipeline de F1**:
   * En la interfaz web, activa el DAG **`f1_strategy_pipeline`** y presiona **Trigger DAG**.
   * También puedes dispararlo directamente por terminal:
     ```bash
     astro dev run dags trigger f1_strategy_pipeline
     ```

4. **Detener el entorno de Airflow** cuando finalices:
   ```bash
   astro dev stop
   ```

---

### 3. Ejecución Local de la Capa Silver (Sin Docker)

El módulo [`src/silver_pipeline.py`](src/silver_pipeline.py) es completamente determinístico y utiliza únicamente la librería estándar de Python (no depende de Airflow ni de llamadas de red). Procesa los archivos descargados en la capa Bronce:

* **Procesar una sesión específica (ej. Gran Premio de Austria 2024, sesión 9550):**
  ```bash
  python -m src.silver_pipeline --season 2024 --session-key 9550
  ```
  Genera `laps.json`, `laps.csv`, `pit_stops.json`, `pit_stops.csv` y el reporte de calidad `validation.json` en `include/output/silver/season=2024/session=9550/`.

* **Procesar todas las sesiones disponibles en Bronce (70 carreras):**
  ```bash
  python -m src.silver_pipeline --all
  ```
  Genera la capa Silver para cada sesión, consolida `f1_silver_dataset.csv` y `f1_silver_pit_stops.csv`, y genera `global_validation.json` y `anomalies.json`.

* **Verificar los 7 Criterios de Calidad de la Cátedra:**
  ```bash
  python verify_quality_criteria.py
  ```

---

## 🧪 Pruebas Automatizadas

Para validar las transformaciones, la resolución de stints/paradas y la integridad del pipeline:

1. **Instalar pytest**:
   ```bash
   pip install pytest
   ```

2. **Ejecutar tests unitarios de la capa Silver**:
   ```bash
   python -m pytest tests/test_silver_pipeline.py
   ```

3. **Ejecutar tests de integridad de DAGs (dentro de Astro)**:
   ```bash
   astro dev pytest
   ```

---

## 📂 Estructura del Repositorio

```text
├── .astro/                      # Configuración y pruebas de integridad del proyecto Astro CLI
├── dags/
│   └── f1_strategy_pipeline.py  # DAG principal de ingesta Bronce y orquestación Silver
├── database/
│   └── init/
│       └── 001_create_schema.sql # DDL de PostgreSQL con tablas relacionales e índices
├── docs/
│   └── SILVER.md                # Especificación y contrato de datos de la capa Silver
├── src/
│   └── silver_pipeline.py       # Motor determinístico de enriquecimiento, joins As-Of y stints/pits
├── tests/
│   ├── dags/                    # Pruebas de integridad de DAGs de Airflow
│   └── test_silver_pipeline.py  # Pruebas unitarias de uniones, resolución de pits y validaciones
├── verify_quality_criteria.py   # Script de auditoría de los 7 criterios de calidad
├── airflow_settings.yaml        # Conexiones locales de Airflow (OpenF1 HTTP Hook)
├── docker-compose.yml           # Definición del servicio PostgreSQL 16
├── Dockerfile                   # Imagen base de Astro Runtime
└── requirements.txt             # Paquetes y proveedores de Python para Airflow
```