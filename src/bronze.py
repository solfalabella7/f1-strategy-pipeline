"""Cache validation and atomic landing; HTTP transport injected by Airflow."""
import json
import time
from pathlib import Path

from src.io_utils import atomic_text, bronze_payload


def land_response(endpoint, parameters, destination, fetch, delay=5, pause=time.sleep):
    destination = Path(destination)
    if destination.exists():
        try:
            bronze_payload(json.loads(destination.read_text(encoding="utf-8")), str(destination))
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f"Corrupt Bronze cache preserved at {destination}; quarantine and re-fetch explicitly") from exc
        return str(destination)
    wait = delay
    try:
        response = fetch(endpoint, parameters)
        if response.status_code == 429:
            try:
                wait = max(delay, min(120, float(response.headers.get("Retry-After", 65))))
            except (TypeError, ValueError):
                wait = 65
        if response.status_code == 404:
            rows, available = bronze_payload(response.json(), endpoint)
            if available:
                response.raise_for_status()
        else:
            response.raise_for_status()
            rows, available = bronze_payload(response.json(), endpoint)
        atomic_text(destination, response.text)
        return str(destination)
    finally:
        pause(wait)
