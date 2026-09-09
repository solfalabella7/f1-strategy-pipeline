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
    # 5. Capa Silver: Transformación y validación
    # -----------------------------------------------------------------------

    # Lee exclusivamente los datos almacenados en Bronce y genera los datasets
    # transformados y enriquecidos de la capa Silver junto con las validaciones.
    @task
    def build_silver_layer() -> dict:
        import sys
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))

        from src.silver_pipeline import build_all_sessions

        log.info(
            "Iniciando transformación de Capa Silver desde %s hacia %s",
            BRONZE_DIR,
            SILVER_DIR,
        )

        resultado = build_all_sessions(
            bronze_dir=BRONZE_DIR,
            silver_dir=SILVER_DIR,
        )

        log.info(
            "Capa Silver finalizada: %s sesiones procesadas, %s filas generadas, %s anomalías detectadas.",
            resultado["summary"]["processed_sessions"],
            resultado["summary"]["total_silver_rows"],
            resultado["summary"]["anomaly_count"],
        )

        return {
            "processed_sessions": resultado["summary"]["processed_sessions"],
            "silver_rows": resultado["summary"]["total_silver_rows"],
            "anomaly_count": resultado["summary"]["anomaly_count"],
        }


    # -----------------------------------------------------------------------
    # 6. Grafo del Pipeline (Bronce -> Silver)
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

    silver_task = build_silver_layer()

    # La capa Silver se ejecuta una vez concluida la ingesta de todas las fuentes Bronce.
    bronze_tasks >> silver_task


f1_strategy_pipeline()