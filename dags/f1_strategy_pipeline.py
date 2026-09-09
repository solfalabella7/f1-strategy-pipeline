"""
### F1 Strategy Pipeline — Ciencia de Datos, UTN FRM 2026

Pipeline de datos para construir un dataset orientado al análisis de
estrategias de neumáticos de Fórmula 1 utilizando la API de OpenF1.

El pipeline ejecuta:
1. Capa Bronce: Ingesta cruda de la API OpenF1 almacenada en JSON inmutables.
2. Capa Silver: Transformación y enriquecimiento determinístico de datos
   (vueltas, stints, condiciones climáticas, estado de pista y posiciones)
   con validaciones y reportes de calidad.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import pendulum
from airflow.providers.http.hooks.http import HttpHook
from airflow.sdk import dag, task


log = logging.getLogger(__name__)

# Asegurar que la raíz del proyecto esté en sys.path para importar módulos de src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Configuración general
# ---------------------------------------------------------------------------

# Bronce conserva las respuestas originales de OpenF1.
# Las etapas posteriores deberán leer estos archivos y no volver a la fuente.
OUTPUT_DIR = Path("/usr/local/airflow/include/output")
BRONZE_DIR = OUTPUT_DIR / "bronze"
SILVER_DIR = OUTPUT_DIR / "silver"

# La URL base de OpenF1 vive en airflow_settings.yaml.
CONN_ID = "openf1"

# Temporadas incluidas en el alcance actual del dataset.
SEASONS = [2023, 2024, 2025]

# OpenF1 limita la cantidad de requests por minuto.
# Esta pausa, junto con el paralelismo limitado del DAG,
# evita golpear la API con demasiadas consultas simultáneas.
REQUEST_DELAY_SECONDS = 5


# ---------------------------------------------------------------------------
# Función auxiliar de Bronce
# ---------------------------------------------------------------------------

def land_json(
    endpoint: str,
    parametros: dict,
    destino: Path,
) -> str:
    """
    Persiste una respuesta JSON de OpenF1 sin transformarla.

    Regla común de Bronce:
    - si el archivo ya existe, se reutiliza;
    - si OpenF1 devuelve datos, se guarda la respuesta original;
    - si OpenF1 informa que no existen resultados, también se conserva
      esa respuesta como evidencia del dato crudo;
    - cualquier otro error HTTP hace fallar la task.
    """

    # Una corrida posterior no vuelve a pedir información que ya quedó
    # correctamente almacenada en Bronce.
    if destino.exists():
        log.info(
            "Bronce ya existe. Se reutiliza %s",
            destino,
        )
        return str(destino)

    hook = HttpHook(
        method="GET",
        http_conn_id=CONN_ID,
    )

    # Se desactiva el chequeo automático de errores para poder distinguir
    # un 404 que significa "sin resultados" de un error HTTP real.
    response = hook.run(
        endpoint=f"v1/{endpoint}",
        data=parametros,
        extra_options={
            "check_response": False,
        },
    )

    # OpenF1 puede devolver 404 cuando la consulta es válida pero no existen
    # registros para esa sesión. Esa ausencia también forma parte del dato
    # crudo y debe quedar registrada en Bronce.
    if response.status_code == 404:
        try:
            detalle = response.json().get("detail")
        except Exception:
            detalle = None

        if detalle == "No results found.":
            destino.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            destino.write_text(
                response.text,
                encoding="utf-8",
            )

            log.warning(
                "OpenF1 no tiene resultados para endpoint=%s "
                "con parámetros=%s. Se conserva la respuesta en %s",
                endpoint,
                parametros,
                destino,
            )

            time.sleep(REQUEST_DELAY_SECONDS)

            return str(destino)

    # Cualquier otro error HTTP sí representa un fallo real.
    # Por ejemplo, un 429 permitirá que Airflow utilice los retries.
    response.raise_for_status()

    destino.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Bronce conserva directamente el cuerpo recibido desde OpenF1.
    # La interpretación del JSON pertenece a la futura capa Silver.
    destino.write_text(
        response.text,
        encoding="utf-8",
    )

    log.info(
        "Bronce descargado: endpoint=%s -> %s",
        endpoint,
        destino,
    )

    time.sleep(REQUEST_DELAY_SECONDS)

    return str(destino)


@dag(
    dag_id="f1_strategy_pipeline",

    # Para esta entrega el pipeline se ejecuta manualmente.
    schedule=None,

    start_date=pendulum.datetime(
        2026,
        9,
        1,
        tz="America/Argentina/Buenos_Aires",
    ),

    catchup=False,

    # Los distintos endpoints pueden trabajar en paralelo, pero la cantidad
    # se limita para respetar el rate limit de OpenF1.
    max_active_tasks=2,

    tags=[
        "ciencia-de-datos",
        "formula-1",
        "openf1",
    ],

    doc_md=__doc__,
)
def f1_strategy_pipeline():

    # -----------------------------------------------------------------------
    # 1. Verificación de la fuente
    # -----------------------------------------------------------------------

    # Antes de comenzar la ingesta se confirma que OpenF1 esté disponible
    # mediante una consulta pequeña y conocida.
    @task(
        retries=2,
        retry_delay=pendulum.duration(seconds=65),
    )
    def check_openf1_source() -> bool:
        hook = HttpHook(
            method="GET",
            http_conn_id=CONN_ID,
        )

        response = hook.run(
            endpoint="v1/sessions",
            data={
                "year": 2025,
                "session_type": "Race",
            },
        )

        datos = response.json()

        if not datos:
            raise ValueError(
                "OpenF1 respondió, pero no devolvió sesiones."
            )

        log.info(
            "OpenF1 disponible: %s sesiones encontradas en la prueba.",
            len(datos),
        )

        return True


    # -----------------------------------------------------------------------
    # 2. Catálogos generales de Bronce
    # -----------------------------------------------------------------------

    # Meetings identifica los fines de semana de Gran Premio.
    # Cada temporada queda almacenada como un lote independiente.
    @task(
        retries=2,
        retry_delay=pendulum.duration(seconds=65),
    )
    def land_bronze_meetings() -> list[str]:
        rutas = []

        for season in SEASONS:
            destino = (
                BRONZE_DIR
                / f"season={season}"
                / "meetings.json"
            )

            rutas.append(
                land_json(
                    endpoint="meetings",
                    parametros={
                        "year": season,
                    },
                    destino=destino,
                )
            )

        return rutas


    # Sessions permite descubrir posteriormente las carreras que componen
    # cada temporada.
    @task(
        retries=2,
        retry_delay=pendulum.duration(seconds=65),
    )
    def land_bronze_sessions() -> list[str]:
        rutas = []

        for season in SEASONS:
            destino = (
                BRONZE_DIR
                / f"season={season}"
                / "sessions.json"
            )

            rutas.append(
                land_json(
                    endpoint="sessions",
                    parametros={
                        "year": season,
                        "session_type": "Race",
                    },
                    destino=destino,
                )
            )

        return rutas


    # -----------------------------------------------------------------------
    # 3. Descubrimiento de carreras
    # -----------------------------------------------------------------------

    # Esta task no consulta OpenF1.
    # Lee sessions.json desde Bronce y obtiene sólo la metadata necesaria
    # para organizar las siguientes descargas.
    @task
    def discover_race_sessions(
        rutas_sessions: list[str],
    ) -> list[dict]:

        import json

        carreras = []

        for ruta in rutas_sessions:
            with open(
                ruta,
                "r",
                encoding="utf-8",
            ) as f:
                sesiones = json.load(f)

            for sesion in sesiones:

                # OpenF1 también devuelve Sprint cuando se consulta
                # session_type="Race". Para este dataset sólo se consideran
                # las carreras principales.
                if sesion.get("session_name") != "Race":
                    continue

                # Una sesión cancelada puede existir en el catálogo aunque
                # nunca haya generado vueltas ni otros datos de carrera.
                if sesion.get("is_cancelled") is True:
                    log.info(
                        "Se omite la sesión cancelada %s de la temporada %s.",
                        sesion.get("session_key"),
                        sesion.get("year"),
                    )
                    continue

                carreras.append({
                    "season": int(sesion["year"]),
                    "meeting_key": int(sesion["meeting_key"]),
                    "session_key": int(sesion["session_key"]),
                })

        if not carreras:
            raise ValueError(
                "No se encontraron carreras válidas en el Bronce de sesiones."
            )

        log.info(
            "Carreras válidas descubiertas para %s: %s",
            SEASONS,
            len(carreras),
        )

        return carreras


    # -----------------------------------------------------------------------
    # 4. Datos de Bronce por carrera
    # -----------------------------------------------------------------------

    # Cada endpoint tiene su propia task para que el grafo muestre claramente
    # qué conjunto de datos está siendo descargado y dónde ocurre un fallo.

    @task(
        retries=2,
        retry_delay=pendulum.duration(seconds=65),
    )
    def land_bronze_drivers(
        carreras: list[dict],
    ) -> list[str]:

        rutas = []

        for carrera in carreras:
            destino = (
                BRONZE_DIR
                / f"season={carrera['season']}"
                / f"session={carrera['session_key']}"
                / "drivers.json"
            )

            rutas.append(
                land_json(
                    endpoint="drivers",
                    parametros={
                        "session_key": carrera["session_key"],
                    },
                    destino=destino,
                )
            )

        return rutas


    @task(
        retries=2,
        retry_delay=pendulum.duration(seconds=65),
    )
    def land_bronze_laps(
        carreras: list[dict],
    ) -> list[str]:

        rutas = []

        for carrera in carreras:
            destino = (
                BRONZE_DIR
                / f"season={carrera['season']}"
                / f"session={carrera['session_key']}"
                / "laps.json"
            )

            rutas.append(
                land_json(
                    endpoint="laps",
                    parametros={
                        "session_key": carrera["session_key"],
                    },
                    destino=destino,
                )
            )

        return rutas


    @task(
        retries=2,
        retry_delay=pendulum.duration(seconds=65),
    )
    def land_bronze_stints(
        carreras: list[dict],
    ) -> list[str]:

        rutas = []

        for carrera in carreras:
            destino = (
                BRONZE_DIR
                / f"season={carrera['season']}"
                / f"session={carrera['session_key']}"
                / "stints.json"
            )

            rutas.append(
                land_json(
                    endpoint="stints",
                    parametros={
                        "session_key": carrera["session_key"],
                    },
                    destino=destino,
                )
            )

        return rutas


    @task(
        retries=2,
        retry_delay=pendulum.duration(seconds=65),
    )
    def land_bronze_pit(
        carreras: list[dict],
    ) -> list[str]:

        rutas = []

        for carrera in carreras:
            destino = (
                BRONZE_DIR
                / f"season={carrera['season']}"
                / f"session={carrera['session_key']}"
                / "pit.json"
            )

            rutas.append(
                land_json(
                    endpoint="pit",
                    parametros={
                        "session_key": carrera["session_key"],
                    },
                    destino=destino,
                )
            )

        return rutas


    @task(
        retries=2,
        retry_delay=pendulum.duration(seconds=65),
    )
    def land_bronze_weather(
        carreras: list[dict],
    ) -> list[str]:

        rutas = []

        for carrera in carreras:
            destino = (
                BRONZE_DIR
                / f"season={carrera['season']}"
                / f"session={carrera['session_key']}"
                / "weather.json"
            )

            rutas.append(
                land_json(
                    endpoint="weather",
                    parametros={
                        "session_key": carrera["session_key"],
                    },
                    destino=destino,
                )
            )

        return rutas


    @task(
        retries=2,
        retry_delay=pendulum.duration(seconds=65),
    )
    def land_bronze_positions(
        carreras: list[dict],
    ) -> list[str]:

        rutas = []

        for carrera in carreras:
            destino = (
                BRONZE_DIR
                / f"season={carrera['season']}"
                / f"session={carrera['session_key']}"
                / "position.json"
            )

            rutas.append(
                land_json(
                    endpoint="position",
                    parametros={
                        "session_key": carrera["session_key"],
                    },
                    destino=destino,
                )
            )

        return rutas


    @task(
        retries=2,
        retry_delay=pendulum.duration(seconds=65),
    )
    def land_bronze_race_control(
        carreras: list[dict],
    ) -> list[str]:

        rutas = []

        for carrera in carreras:
            destino = (
                BRONZE_DIR
                / f"season={carrera['season']}"
                / f"session={carrera['session_key']}"
                / "race_control.json"
            )

            rutas.append(
                land_json(
                    endpoint="race_control",
                    parametros={
                        "session_key": carrera["session_key"],
                    },
                    destino=destino,
                )
            )

        return rutas


    @task(
        retries=2,
        retry_delay=pendulum.duration(seconds=65),
    )
    def land_bronze_intervals(
        carreras: list[dict],
    ) -> list[str]:

        rutas = []

        for carrera in carreras:
            destino = (
                BRONZE_DIR
                / f"season={carrera['season']}"
                / f"session={carrera['session_key']}"
                / "intervals.json"
            )

            rutas.append(
                land_json(
                    endpoint="intervals",
                    parametros={
                        "session_key": carrera["session_key"],
                    },
                    destino=destino,
                )
            )

        return rutas


    # -----------------------------------------------------------------------
    # 5. Capa Silver: Refinamiento por sesión
    # -----------------------------------------------------------------------

    # Lee exclusivamente los datos almacenados en Bronce y genera los archivos
    # transformados de la capa Silver por cada carrera (laps.csv y laps.json).
    @task
    def refine_silver() -> str:
        """Capa Silver: Refina cada carrera de Bronce a Plata. No toca la red."""
        import sys
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))

        from src.silver_pipeline import refine_all_sessions

        log.info(
            "Iniciando refinamiento de Capa Silver desde %s hacia %s",
            BRONZE_DIR,
            SILVER_DIR,
        )

        sesiones = refine_all_sessions(
            bronze_dir=BRONZE_DIR,
            silver_dir=SILVER_DIR,
        )

        log.info(
            "Refinamiento Silver finalizado: %s sesiones procesadas.",
            len(sesiones),
        )

        return str(SILVER_DIR)


    # -----------------------------------------------------------------------
    # 6. Capa Silver: Consolidación y Deduplicación
    # -----------------------------------------------------------------------

    # Junta los parciales de cada carrera procesada en un único archivo
    # consolidado y deduplica por la clave primaria natural.
    @task
    def consolidate(plata_dir_str: str | None = None) -> str:
        """Junta las sesiones de plata, deduplica por clave primaria y genera _consolidado.csv."""
        import sys
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))

        from src.silver_pipeline import consolidate_sessions

        plata_dir = Path(plata_dir_str) if plata_dir_str else SILVER_DIR
        log.info("Consolidando sesiones desde %s...", plata_dir)

        ruta_consolidado = consolidate_sessions(
            silver_dir=plata_dir,
            bronze_dir=BRONZE_DIR,
            output_filename="_consolidado.csv",
        )

        log.info(
            "Consolidación exitosa. Archivo temporal generado en %s",
            ruta_consolidado,
        )

        return str(ruta_consolidado)


    # -----------------------------------------------------------------------
    # 7. Validación de Calidad de Salida (Los 7 Criterios de Entrega 1)
    # -----------------------------------------------------------------------

    # Chequeos duros. Si alguno falla, el DAG falla: el dato malo no se publica.
    # Esta tarea es la aduana de calidad que protege a la tarea save.
    @task
    def validate(ruta_consolidado: str | None = None) -> str:
        """Firewall de calidad: evalúa los 7 criterios sobre _consolidado.csv antes de publicar."""
        import csv
        from pathlib import Path

        csv_path = Path(ruta_consolidado) if ruta_consolidado else SILVER_DIR / "_consolidado.csv"
        if not csv_path.exists():
            raise FileNotFoundError(
                f"No se encontró el archivo consolidado en {csv_path}"
            )

        rows = []
        with csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            for r in reader:
                rows.append(r)

        total_rows = len(rows)
        total_cols = len(fieldnames)

        # 1. Clave primaria sin duplicados (session_key + driver_number + lap_number)
        keys = [(r["session_key"], r["driver_number"], r["lap_number"]) for r in rows]
        unique_keys = len(set(keys))
        if unique_keys != total_rows:
            raise ValueError(
                f"Fallo de Calidad [1]: Clave duplicada detectada. Claves únicas: {unique_keys}, Total filas: {total_rows}"
            )
        log.info(
            "[1/7] Clave sin duplicados: OK (is_unique=True, %s filas únicas).",
            total_rows,
        )

        # 2. Volumen suficiente (> 1.000 filas)
        if total_rows <= 1000:
            raise ValueError(
                f"Fallo de Calidad [2]: Volumen insuficiente. Filas: {total_rows} (requerido > 1000)"
            )
        log.info(
            "[2/7] Volumen suficiente: OK (%s filas > 1.000).",
            total_rows,
        )

        # 3. Ancho suficiente (>= 5 columnas útiles)
        if total_cols < 5:
            raise ValueError(
                f"Fallo de Calidad [3]: Ancho insuficiente. Columnas: {total_cols} (requerido >= 5)"
            )
        log.info(
            "[3/7] Ancho suficiente: OK (%s columnas >= 5).",
            total_cols,
        )

        # 4. Mezcla de tipos (numéricas, categóricas, booleanas, fechas)
        has_numeric = False
        has_string = False
        has_date = False
        has_bool = False

        for col in fieldnames:
            samples = [r[col] for r in rows if r[col] != ""]
            if not samples:
                continue
            if all(s in ("True", "False") for s in samples[:50]):
                has_bool = True
            elif all(s.replace(".", "", 1).replace("-", "", 1).isdigit() for s in samples[:50]):
                has_numeric = True
            elif any("T" in s and ("+" in s or "Z" in s or "-" in s) for s in samples[:20]):
                has_date = True
            else:
                has_string = True

        if not (has_numeric and has_string and has_date and has_bool):
            raise ValueError(
                f"Fallo de Calidad [4]: Mezcla de tipos incompleta (numeric={has_numeric}, string={has_string}, date={has_date}, bool={has_bool})"
            )
        log.info(
            "[4/7] Mezcla de tipos: OK (detectadas numéricas, categóricas, booleanas y fechas)."
        )

        # 5. Nulos conocidos
        null_counts = {
            col: sum(1 for r in rows if r[col] == "" or r[col] is None)
            for col in fieldnames
        }
        sorted_nulls = sorted(null_counts.items(), key=lambda x: x[1], reverse=True)
        top_nulls_summary = {
            col: f"{(count / total_rows) * 100:.2f}%" for col, count in sorted_nulls[:10]
        }
        log.info(
            "[5/7] Nulos analizados: OK. Top 10 columnas con nulos: %s",
            top_nulls_summary,
        )

        # 6. Sin columnas vacías (ninguna al 100% de nulos)
        empty_cols = [col for col, count in null_counts.items() if count == total_rows]
        if empty_cols:
            raise ValueError(
                f"Fallo de Calidad [6]: Columnas 100%% vacías detectadas: {empty_cols}"
            )
        log.info("[6/7] Sin columnas vacías: OK (0 columnas al 100%% de nulos).")

        # 7. Unidad de análisis
        log.info("[7/7] Unidad de análisis: OK («Una fila es una vuelta completada o intentada por un piloto en un GP»).")

        log.info(
            "=== VALIDACIÓN DE CALIDAD COMPLETADA EXITOSAMENTE: TODOS LOS CRITERIOS CUMPLIDOS ==="
        )

        return str(ruta_consolidado)


    # -----------------------------------------------------------------------
    # 8. Publicación Oficial (Save)
    # -----------------------------------------------------------------------

    # Escribe el entregable final definitivo SOLO SI validate terminó en éxito.
    # Si validate falla, save jamás se ejecuta: el dato erróneo nunca llega a destino.
    @task
    def save(ruta_validada: str | None = None, **context) -> str:
        """Escribe el entregable final f1_silver_dataset.csv una vez superada la validación."""
        import shutil
        from pathlib import Path

        origen = Path(ruta_validada) if ruta_validada else SILVER_DIR / "_consolidado.csv"
        destino = SILVER_DIR / "f1_silver_dataset.csv"

        # Publica el dataset oficial
        shutil.copyfile(origen, destino)
        log.info("Dataset oficial publicado en %s", destino)

        # Guarda además una copia fechada de la corrida
        dag_run = context.get("dag_run")
        if dag_run:
            momento = dag_run.logical_date or dag_run.run_after

            if momento:
                ds = momento.date().isoformat()
                destino_fechado = SILVER_DIR / f"f1_silver_{ds}.csv"

                shutil.copyfile(origen, destino_fechado)
                log.info("Copia fechada respaldada en %s", destino_fechado)

        return str(destino)


    # -----------------------------------------------------------------------
    # 9. Grafo del Pipeline (Bronce -> Refine -> Consolidate -> Validate -> Save)
    # -----------------------------------------------------------------------

    fuente_ok = check_openf1_source()

    meetings_bronze = land_bronze_meetings()
    sessions_bronze = land_bronze_sessions()

    # Estas dos tasks no reciben información del chequeo de fuente.
    # La dependencia explícita representa solamente el orden del pipeline.
    fuente_ok >> [
        meetings_bronze,
        sessions_bronze,
    ]

    carreras = discover_race_sessions(
        sessions_bronze
    )

    # Todos estos endpoints necesitan conocer las carreras, pero no dependen
    # unos de otros. Airflow puede ejecutarlos independientemente respetando
    # el límite de concurrencia configurado en el DAG.
    bronze_tasks = [
        land_bronze_drivers(carreras),
        land_bronze_laps(carreras),
        land_bronze_stints(carreras),
        land_bronze_pit(carreras),
        land_bronze_weather(carreras),
        land_bronze_positions(carreras),
        land_bronze_race_control(carreras),
        land_bronze_intervals(carreras),
    ]

    refine_silver_task = refine_silver()
    consolidate_task = consolidate(refine_silver_task)
    validate_task = validate(consolidate_task)
    save_task = save(validate_task)

    # Flujo canónico: Bronce -> Refine Silver -> Consolidate -> Validate -> Save
    bronze_tasks >> refine_silver_task
    refine_silver_task >> consolidate_task >> validate_task >> save_task


f1_strategy_pipeline()