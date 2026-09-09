"""F1: fuente/caché → Bronce por endpoint → Silver versionado → calidad.

Una fila es una vuelta de un piloto. La etiqueta describe una acción observada
en la próxima vuelta; no certifica que esa estrategia fuera óptima.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pendulum
from airflow.providers.http.hooks.http import HttpHook
from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.bronze import land_response
from src.io_utils import bronze_payload
from src.release import REQUIRED_SOURCES, expected_inventory, input_hashes, verify_release

log = logging.getLogger(__name__)
OUTPUT_DIR = PROJECT_ROOT / "include/output"
BRONZE_DIR = OUTPUT_DIR / "bronze"
SILVER_DIR = OUTPUT_DIR / "silver"
SEASONS = [2023, 2024, 2025]
CONN_ID = "openf1"
REQUEST_DELAY_SECONDS = 5


def fetch(endpoint, parameters):
    return HttpHook(method="GET", http_conn_id=CONN_ID).run(
        endpoint=f"v1/{endpoint}", data=parameters,
        extra_options={"check_response": False, "timeout": (10, 60)},
    )


def land_json(endpoint, parametros, destino):
    return land_response(endpoint, parametros, destino, fetch, REQUEST_DELAY_SECONDS)


@dag(
    dag_id="f1_strategy_pipeline", schedule=None,
    start_date=pendulum.datetime(2026, 9, 1, tz="America/Argentina/Buenos_Aires"),
    catchup=False, max_active_tasks=2, max_active_runs=1,
    default_args={"retries": 2, "retry_delay": pendulum.duration(seconds=65)},
    tags=["ciencia-de-datos", "formula-1", "openf1"], doc_md=__doc__,
)
def f1_strategy_pipeline():
    @task
    def check_openf1_source():
        # A complete local Bronze snapshot permits a fully offline rerun.
        try:
            hashes = input_hashes(BRONZE_DIR)
            if {year for year, _ in expected_inventory(BRONZE_DIR)} == set(SEASONS):
                log.info("Snapshot local completo: %s archivos; no se necesita red", len(hashes))
                return "local_snapshot"
        except (OSError, ValueError, KeyError):
            pass
        response = fetch("sessions", {"year": SEASONS[-1], "session_type": "Race"})
        response.raise_for_status()
        rows, available = bronze_payload(response.json())
        if not available or not rows:
            raise ValueError("OpenF1 no devuelve sesiones")
        return "openf1_available"

    @task
    def land_bronze_meetings():
        return [land_json("meetings", {"year": year}, BRONZE_DIR / f"season={year}" / "meetings.json") for year in SEASONS]

    @task
    def land_bronze_sessions():
        return [land_json("sessions", {"year": year, "session_type": "Race"}, BRONZE_DIR / f"season={year}" / "sessions.json") for year in SEASONS]

    @task
    def discover_race_sessions(rutas_sessions):
        races = []
        for name in rutas_sessions:
            records, _ = bronze_payload(json.loads(Path(name).read_text(encoding="utf-8")), name)
            races.extend({"season": s["year"], "session_key": s["session_key"]} for s in records
                         if s.get("session_name") == "Race" and s.get("is_cancelled") is not True)
        if not races or len({(r["season"], r["session_key"]) for r in races}) != len(races):
            raise ValueError("Inventario de carreras vacío o duplicado")
        return races

    @task
    def land_endpoint(carreras, endpoint):
        return [land_json(endpoint, {"session_key": r["session_key"]},
                          BRONZE_DIR / f"season={r['season']}" / f"session={r['session_key']}" / f"{endpoint}.json")
                for r in carreras]

    @task
    def build_silver_layer():
        from src.silver_pipeline import build_all_sessions
        result = build_all_sessions(BRONZE_DIR, SILVER_DIR)
        log.info("Silver: %s", result["summary"])
        return {"release_path": result["release_path"], "release_id": result["release_id"],
                "processed_sessions": result["summary"]["processed_sessions"]}

    @task
    def validate(silver_info):
        from src.quality import validate_csv
        path = Path(silver_info["release_path"])
        manifest = verify_release(path)
        if manifest["release_id"] != silver_info["release_id"]:
            raise ValueError("La salida no corresponde a esta ejecución")
        report = validate_csv(path / "f1_silver_dataset.csv")
        result = {k: report[k] for k in ("status", "total_rows", "total_cols", "duplicate_key_count", "empty_columns", "eligible_labeled_rows")}
        log.info("Calidad: %s; CSV: %s", result, path / "f1_silver_dataset.csv")
        return result

    source = check_openf1_source()
    meetings, sessions = land_bronze_meetings(), land_bronze_sessions()
    source >> [meetings, sessions]
    races = discover_race_sessions(sessions)
    bronze_tasks = [land_endpoint.override(task_id="land_bronze_" + ("positions" if endpoint == "position" else endpoint))(races, endpoint)
                    for endpoint in REQUIRED_SOURCES]
    silver = build_silver_layer()
    [meetings, *bronze_tasks] >> silver
    validate(silver)


f1_strategy_pipeline()
