"""Build one-session Silver data from immutable Bronze JSON files.

This module intentionally has no OpenF1 or Airflow dependency.  It is a
local, deterministic transformation and can be run with the repository's
Python interpreter.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


DEFAULT_BRONZE = Path("include/output/bronze")
DEFAULT_SILVER = Path("include/output/silver")
ASOF_TOLERANCE_SECONDS = 120.0
NUMERIC = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def rows_from_json(path: Path) -> tuple[list[dict[str, Any]], bool]:
    """Return rows and whether the Bronze response contains usable data."""
    value = read_json(path)
    if isinstance(value, list):
        return value, True
    if isinstance(value, dict) and value.get("detail") == "No results found":
        return [], False
    return [], False


def parse_timestamp(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def strict_decimal(value: Any) -> float | None:
    """Convert only numeric values and strictly numeric strings."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, str) and NUMERIC.fullmatch(value.strip()):
        parsed = float(value.strip())
        return parsed if math.isfinite(parsed) else None
    return None


def asof_previous(
    rows: list[dict[str, Any]],
    key: tuple[Any, ...],
    timestamp: datetime | None,
    key_fields: tuple[str, ...],
    date_field: str = "date",
) -> tuple[dict[str, Any] | None, float | None]:
    if timestamp is None:
        return None, None
    candidates = [
        row
        for row in rows
        if tuple(row.get(field) for field in key_fields) == key
        and parse_timestamp(row.get(date_field)) is not None
        and parse_timestamp(row.get(date_field)) <= timestamp
    ]
    if not candidates:
        return None, None
    selected = max(candidates, key=lambda row: parse_timestamp(row[date_field]))
    age = (timestamp - parse_timestamp(selected[date_field])).total_seconds()
    return selected, age


def _build_asof_index(
    rows: list[dict[str, Any]],
    key_fields: tuple[str, ...],
    date_field: str = "date",
) -> dict[tuple[Any, ...], tuple[list[datetime], list[dict[str, Any]]]]:
    grouped: dict[tuple[Any, ...], list[tuple[datetime, dict[str, Any]]]] = {}
    for row in rows:
        timestamp = parse_timestamp(row.get(date_field))
        if timestamp is None:
            continue
        key = tuple(row.get(field) for field in key_fields)
        grouped.setdefault(key, []).append((timestamp, row))
    return {
        key: (
            [timestamp for timestamp, _ in ordered],
            [row for _, row in ordered],
        )
        for key, values in grouped.items()
        for ordered in [sorted(values, key=lambda item: item[0])]
    }


def _asof_indexed(
    index: dict[tuple[Any, ...], tuple[list[datetime], list[dict[str, Any]]]],
    key: tuple[Any, ...],
    timestamp: datetime | None,
) -> tuple[dict[str, Any] | None, float | None]:
    if timestamp is None or key not in index:
        return None, None
    timestamps, rows = index[key]
    position = bisect_right(timestamps, timestamp) - 1
    if position < 0:
        return None, None
    selected = rows[position]
    return selected, (timestamp - timestamps[position]).total_seconds()


def _stint_for_lap(
    stints: list[dict[str, Any]],
    driver_number: Any,
    lap_number: int,
    max_lap: int,
) -> tuple[dict[str, Any] | None, str]:
    driver_stints = sorted(
        (row for row in stints if row.get("driver_number") == driver_number),
        key=lambda row: row.get("stint_number") or 0,
    )
    known_starts = [row.get("lap_start") for row in driver_stints]
    for index, stint in enumerate(driver_stints):
        start = stint.get("lap_start")
        if start is None:
            continue
        next_starts = [
            candidate
            for candidate in known_starts[index + 1 :]
            if candidate is not None
        ]
        next_start = min(next_starts) if next_starts else None
        upper = next_start
        if upper is None:
            upper = (
                (stint.get("lap_end") + 1)
                if stint.get("lap_end") is not None
                else max_lap + 1
            )
        if start <= lap_number < upper:
            return stint, "open_ended" if next_start is None and stint.get(
                "lap_end"
            ) is None else "assigned"
    return None, "no_match"


def _race_control_state(
    events: list[dict[str, Any]], lap: dict[str, Any]
) -> dict[str, Any]:
    lap_time = parse_timestamp(lap.get("date_start"))
    lap_number = lap.get("lap_number")
    usable = []
    for event in events:
        event_time = parse_timestamp(event.get("date"))
        event_lap = event.get("lap_number")
        if lap_time is not None:
            if event_time is not None and event_time <= lap_time:
                usable.append(event)
        elif (
            event_lap is not None and lap_number is not None and event_lap <= lap_number
        ):
            usable.append(event)
    usable.sort(
        key=lambda row: (
            parse_timestamp(row.get("date"))
            or datetime.min.replace(tzinfo=timezone.utc)
        )
    )
    safety_car = virtual_safety_car = yellow = red = False
    yellow_scope = None
    session_status = None
    for event in usable:
        message = str(event.get("message") or "").upper()
        flag = str(event.get("flag") or "").upper()
        category = str(event.get("category") or "").upper()
        is_virtual_safety_car = "VIRTUAL SAFETY CAR" in message
        is_safety_car_event = category == "SAFETYCAR" and not is_virtual_safety_car
        if is_virtual_safety_car and "DEPLOYED" in message:
            virtual_safety_car = True
        elif is_virtual_safety_car and (
            "ENDING" in message or "TRACK CLEAR" in message
        ):
            virtual_safety_car = False
        if is_safety_car_event and "DEPLOYED" in message:
            safety_car = True
            virtual_safety_car = False
        elif is_safety_car_event and any(
            token in message for token in ("ENDING", "IN THIS LAP", "TRACK CLEAR")
        ):
            safety_car = False
        if flag in {"YELLOW", "DOUBLE YELLOW"} or "YELLOW FLAG" in message:
            yellow = True
            yellow_scope = event.get("scope")
        if flag == "CLEAR" or message.startswith("CLEAR "):
            yellow = False
            yellow_scope = None
        if flag == "RED" or (
            category == "FLAG"
            and message.startswith("RED FLAG")
            and not message.startswith("CHEQUERED FLAG")
        ):
            red = True
        if flag == "GREEN" and "PIT EXIT OPEN" not in message:
            yellow = red = False
            yellow_scope = None
        if "SESSION RESUMED" in message:
            yellow = red = False
            yellow_scope = None
        if category == "SESSIONSTATUS":
            session_status = event.get("message") or event.get("flag")
        if message.startswith("CHEQUERED FLAG"):
            session_status = "SESSION FINISHED"
            red = False
    recent = usable[-1] if usable else None
    return {
        "safety_car_active": safety_car,
        "virtual_safety_car_active": virtual_safety_car,
        "yellow_flag_active": yellow,
        "yellow_flag_scope": yellow_scope,
        "red_flag_active": red,
        "session_status": session_status,
        "race_control_event_count": len(usable),
        "race_control_recent_event": recent.get("message") if recent else None,
        "race_control_recent_event_timestamp": recent.get("date") if recent else None,
        "race_control_join_status": (
            "timestamp_asof" if lap_time is not None else "lap_number_fallback"
        ),
    }


def build_session(
    bronze_dir: Path = DEFAULT_BRONZE,
    silver_dir: Path = DEFAULT_SILVER,
    season: int = 2024,
    session_key: int = 9550,
) -> tuple[Path, list[dict[str, Any]], dict[str, Any]]:
    root = bronze_dir / f"season={season}"
    session_dir = root / f"session={session_key}"
    sessions = read_json(root / "sessions.json")
    session = next(row for row in sessions if row.get("session_key") == session_key)
    meetings = read_json(root / "meetings.json")
    meeting = next(
        (
            row
            for row in meetings
            if row.get("meeting_key") == session.get("meeting_key")
        ),
        {},
    )
    source_names = (
        "drivers",
        "laps",
        "stints",
        "weather",
        "position",
        "intervals",
        "pit",
        "race_control",
    )
    source_rows: dict[str, list[dict[str, Any]]] = {}
    availability: dict[str, bool] = {}
    for name in source_names:
        source_rows[name], availability[name] = rows_from_json(
            session_dir / f"{name}.json"
        )

    laps = source_rows["laps"]
    max_laps = max((row.get("lap_number") or 0 for row in laps), default=0)
    weather = source_rows["weather"]
    positions = source_rows["position"]
    intervals = source_rows["intervals"]
    weather_index = _build_asof_index(weather, ("session_key",))
    position_index = _build_asof_index(positions, ("session_key", "driver_number"))
    interval_index = _build_asof_index(intervals, ("session_key", "driver_number"))
    pit_by_key = {
        (row.get("driver_number"), row.get("lap_number")): row
        for row in source_rows["pit"]
    }
    drivers = {
        (row.get("session_key"), row.get("driver_number")): row
        for row in source_rows["drivers"]
    }
    lap_counts = Counter(row.get("driver_number") for row in laps)
    last_laps = {
        driver: max(
            row.get("lap_number") or 0
            for row in laps
            if row.get("driver_number") == driver
        )
        for driver in lap_counts
    }

    output: list[dict[str, Any]] = []
    for lap in laps:
        lap_time = parse_timestamp(lap.get("date_start"))
        driver_key = (session_key, lap.get("driver_number"))
        driver = drivers.get(driver_key, {})
        stint, stint_status = _stint_for_lap(
            source_rows["stints"],
            lap.get("driver_number"),
            lap.get("lap_number"),
            max_laps,
        )
        weather_row, weather_age = _asof_indexed(
            weather_index, (session_key,), lap_time
        )
        position_row, position_age = _asof_indexed(
            position_index, (session_key, lap.get("driver_number")), lap_time
        )
        interval_row, interval_age = _asof_indexed(
            interval_index, (session_key, lap.get("driver_number")), lap_time
        )
        weather_ok = weather_row is not None and weather_age <= ASOF_TOLERANCE_SECONDS
        position_available = position_row is not None
        position_stale = position_available and position_age > ASOF_TOLERANCE_SECONDS
        interval_ok = (
            interval_row is not None and interval_age <= ASOF_TOLERANCE_SECONDS
        )
        pit = pit_by_key.get((lap.get("driver_number"), lap.get("lap_number")))
        row = {
            "season": season,
            "session_key": session_key,
            "meeting_key": lap.get("meeting_key"),
            "driver_number": lap.get("driver_number"),
            "lap_number": lap.get("lap_number"),
            "session_name": session.get("session_name"),
            "session_type": session.get("session_type"),
            "session_date_start": session.get("date_start"),
            "circuit_key": session.get("circuit_key"),
            "circuit_short_name": session.get("circuit_short_name"),
            "country_code": session.get("country_code"),
            "country_name": session.get("country_name"),
            "meeting_name": meeting.get("meeting_name"),
            "full_name": driver.get("full_name"),
            "name_acronym": driver.get("name_acronym"),
            "team_name": driver.get("team_name"),
            "team_colour": driver.get("team_colour"),
            "country_code_driver": driver.get("country_code"),
            "lap_date_start": lap.get("date_start"),
            "lap_duration": lap.get("lap_duration"),
            "duration_sector_1": lap.get("duration_sector_1"),
            "duration_sector_2": lap.get("duration_sector_2"),
            "duration_sector_3": lap.get("duration_sector_3"),
            "i1_speed": lap.get("i1_speed"),
            "i2_speed": lap.get("i2_speed"),
            "st_speed": lap.get("st_speed"),
            "is_pit_out_lap": lap.get("is_pit_out_lap"),
            "stint_number": stint.get("stint_number") if stint else None,
            "current_compound": stint.get("compound") if stint else None,
            "tyre_age_at_start": stint.get("tyre_age_at_start") if stint else None,
            "tyre_age": (
                stint.get("tyre_age_at_start")
                + max(0, lap.get("lap_number") - stint.get("lap_start"))
            )
            if stint
            and stint.get("lap_start") is not None
            and stint.get("tyre_age_at_start") is not None
            else None,
            "has_stint": stint is not None,
            "stint_assignment_status": stint_status,
            "air_temperature": weather_row.get("air_temperature")
            if weather_ok
            else None,
            "track_temperature": weather_row.get("track_temperature")
            if weather_ok
            else None,
            "humidity": weather_row.get("humidity") if weather_ok else None,
            "pressure": weather_row.get("pressure") if weather_ok else None,
            "rainfall": weather_row.get("rainfall") if weather_ok else None,
            "wind_direction": weather_row.get("wind_direction") if weather_ok else None,
            "wind_speed": weather_row.get("wind_speed") if weather_ok else None,
            "weather_timestamp": weather_row.get("date") if weather_row else None,
            "weather_timestamp_age_seconds": weather_age,
            "has_weather": weather_ok,
            "weather_stale": weather_row is not None and not weather_ok,
            "weather_join_method": "asof_previous",
            "position": position_row.get("position") if position_available else None,
            "position_timestamp": position_row.get("date") if position_row else None,
            "position_timestamp_age_seconds": position_age,
            "has_position": position_available,
            "position_available": position_available,
            "position_missing": not position_available,
            "position_stale": position_stale,
            "position_join_method": "asof_previous",
            "interval_raw": interval_row.get("interval") if interval_row else None,
            "gap_to_leader_raw": interval_row.get("gap_to_leader")
            if interval_row
            else None,
            "interval": strict_decimal(interval_row.get("interval"))
            if interval_ok and interval_row
            else None,
            "gap_to_leader": strict_decimal(interval_row.get("gap_to_leader"))
            if interval_ok and interval_row
            else None,
            "interval_timestamp": interval_row.get("date") if interval_row else None,
            "interval_timestamp_age_seconds": interval_age,
            "has_interval": interval_ok,
            "interval_stale": interval_row is not None and not interval_ok,
            "interval_join_method": "asof_previous",
            "pit_data_available": availability["pit"],
            "pit_stop": (pit is not None) if availability["pit"] else None,
            "pit_date": pit.get("date") if pit else None,
            "pit_duration": pit.get("pit_duration") if pit else None,
            "lane_duration": pit.get("lane_duration") if pit else None,
            "stop_duration": pit.get("stop_duration") if pit else None,
            "lap_timestamp_available": lap_time is not None,
            "timestamp_join_status": "available"
            if lap_time is not None
            else "missing_lap_timestamp",
            "has_lap_duration": lap.get("lap_duration") is not None,
            "complete_sector_times": all(
                lap.get(key) is not None
                for key in (
                    "duration_sector_1",
                    "duration_sector_2",
                    "duration_sector_3",
                )
            ),
            "complete_speed_measurements": all(
                lap.get(key) is not None for key in ("i1_speed", "i2_speed", "st_speed")
            ),
            "complete_lap_record": all(
                lap.get(key) is not None
                for key in (
                    "lap_duration",
                    "duration_sector_1",
                    "duration_sector_2",
                    "duration_sector_3",
                    "i1_speed",
                    "i2_speed",
                    "st_speed",
                )
            ),
            "driver_lap_count": lap_counts.get(lap.get("driver_number"), 0),
            "driver_last_lap_observed": last_laps.get(lap.get("driver_number")),
            "session_max_lap_observed": max_laps,
            "laps_missing_until_session_max": max_laps
            - (last_laps.get(lap.get("driver_number"), max_laps)),
        }
        row["possible_early_exit"] = row["driver_last_lap_observed"] < max_laps
        row.update(_race_control_state(source_rows["race_control"], lap))
        output.append(row)

    destination = silver_dir / f"season={season}" / f"session={session_key}"
    destination.mkdir(parents=True, exist_ok=True)
    output_path = destination / "laps.json"
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    return (
        output_path,
        output,
        {
            "availability": availability,
            "session": session,
            "meeting": meeting,
            "bronze_lap_count": len(laps),
            "source_counts": {name: len(source_rows[name]) for name in source_rows},
            "source_available": availability,
            "temporal_join_evaluated": {
                "weather": sum(
                    lap_time is not None
                    for lap_time in [
                        parse_timestamp(lap.get("date_start")) for lap in laps
                    ]
                ),
                "position": sum(
                    lap_time is not None
                    for lap_time in [
                        parse_timestamp(lap.get("date_start")) for lap in laps
                    ]
                ),
                "intervals": sum(
                    lap_time is not None
                    for lap_time in [
                        parse_timestamp(lap.get("date_start")) for lap in laps
                    ]
                ),
                "race_control": sum(
                    lap_time is not None
                    for lap_time in [
                        parse_timestamp(lap.get("date_start")) for lap in laps
                    ]
                ),
            },
            "future_temporal_joins": {
                "weather": 0,
                "position": 0,
                "intervals": 0,
                "race_control": 0,
            },
            "race_control_timestamp_assignments": sum(
                1
                for lap in laps
                if parse_timestamp(lap.get("date_start")) is not None
                for event in source_rows["race_control"]
                if parse_timestamp(event.get("date")) is not None
                and parse_timestamp(event.get("date"))
                <= parse_timestamp(lap.get("date_start"))
            ),
            "race_control_future_assignments": 0,
            "race_control_fallback_rows": sum(
                parse_timestamp(lap.get("date_start")) is None for lap in laps
            ),
        },
    )


def validate(
    rows: list[dict[str, Any]], bronze_count: int, source_meta: dict[str, Any]
) -> dict[str, Any]:
    def pct(count: int) -> float:
        return round(100 * count / len(rows), 2) if rows else 0.0

    duplicate_keys = len(rows) - len(
        {(r["session_key"], r["driver_number"], r["lap_number"]) for r in rows}
    )
    stale = lambda name: sum(bool(row[name]) for row in rows)
    null_counts = {
        key: sum(row.get(key) is None for row in rows)
        for key in (
            "lap_date_start",
            "lap_duration",
            "current_compound",
            "weather_timestamp",
            "position",
            "interval",
            "pit_duration",
        )
    }
    future_temporal_joins = {
        "weather": sum(
            bool(
                row["weather_timestamp"]
                and row["lap_date_start"]
                and row["weather_timestamp"] > row["lap_date_start"]
            )
            for row in rows
        ),
        "position": sum(
            bool(
                row["position_timestamp"]
                and row["lap_date_start"]
                and row["position_timestamp"] > row["lap_date_start"]
            )
            for row in rows
        ),
        "intervals": sum(
            bool(
                row["interval_timestamp"]
                and row["lap_date_start"]
                and row["interval_timestamp"] > row["lap_date_start"]
            )
            for row in rows
        ),
        "race_control": sum(
            bool(
                row["race_control_recent_event_timestamp"]
                and row["lap_date_start"]
                and row["race_control_recent_event_timestamp"] > row["lap_date_start"]
            )
            for row in rows
        ),
    }
    return {
        "session": source_meta["session"],
        "bronze_lap_count": bronze_count,
        "silver_row_count": len(rows),
        "row_count_difference": len(rows) - bronze_count,
        "duplicate_key_count": duplicate_keys,
        "stints": {
            "has_stint_pct": pct(sum(row["has_stint"] for row in rows)),
            "no_stint_pct": pct(sum(not row["has_stint"] for row in rows)),
            "status_counts": dict(
                Counter(row["stint_assignment_status"] for row in rows)
            ),
            "compounds": dict(
                Counter(
                    row["current_compound"]
                    for row in rows
                    if row["current_compound"] is not None
                )
            ),
        },
        "weather": {
            "coverage_pct": pct(sum(row["has_weather"] for row in rows)),
            "without_weather": sum(not row["has_weather"] for row in rows),
            "stale": stale("weather_stale"),
            "age_seconds": _distribution(rows, "weather_timestamp_age_seconds"),
        },
        "position": {
            "available_pct": pct(sum(row["position_available"] for row in rows)),
            "missing_pct": pct(sum(row["position_missing"] for row in rows)),
            "stale_pct": pct(sum(row["position_stale"] for row in rows)),
            "coverage_pct": pct(sum(row["position_available"] for row in rows)),
            "available": sum(row["position_available"] for row in rows),
            "missing": sum(row["position_missing"] for row in rows),
            "stale": stale("position_stale"),
            "age_seconds": _distribution(rows, "position_timestamp_age_seconds"),
        },
        "intervals": {
            "coverage_pct": pct(sum(row["has_interval"] for row in rows)),
            "stale": stale("interval_stale"),
            "null_converted_values": sum(
                row["has_interval"]
                and row["interval_raw"] is not None
                and row["interval"] is None
                for row in rows
            ),
            "age_seconds": _distribution(rows, "interval_timestamp_age_seconds"),
        },
        "pit": {
            "true": sum(row["pit_stop"] is True for row in rows),
            "false": sum(
                row["pit_stop"] is False and row["pit_data_available"] for row in rows
            ),
            "data_unavailable": sum(not row["pit_data_available"] for row in rows),
        },
        "race_control": {
            "safety_car_rows": sum(row["safety_car_active"] for row in rows),
            "virtual_safety_car_rows": sum(
                row["virtual_safety_car_active"] for row in rows
            ),
            "yellow_flag_rows": sum(row["yellow_flag_active"] for row in rows),
            "yellow_flag_scopes": dict(
                Counter(
                    row["yellow_flag_scope"]
                    for row in rows
                    if row["yellow_flag_scope"] is not None
                )
            ),
            "red_flag_rows": sum(row["red_flag_active"] for row in rows),
            "session_statuses": sorted(
                {
                    row["session_status"]
                    for row in rows
                    if row["session_status"] is not None
                }
            ),
            "timestamp_assignments": source_meta["race_control_timestamp_assignments"],
            "future_assignments": future_temporal_joins["race_control"],
            "fallback_rows": source_meta["race_control_fallback_rows"],
            "examples": [
                {
                    key: row[key]
                    for key in (
                        "lap_number",
                        "race_control_recent_event",
                        "safety_car_active",
                        "virtual_safety_car_active",
                        "yellow_flag_active",
                        "yellow_flag_scope",
                        "red_flag_active",
                    )
                }
                for row in rows
                if row["safety_car_active"]
                or row["yellow_flag_active"]
                or row["red_flag_active"]
            ][:5],
        },
        "quality": {
            "missing_lap_timestamp": sum(
                not row["lap_timestamp_available"] for row in rows
            ),
            "null_counts": null_counts,
            "possible_early_exit_rows": sum(row["possible_early_exit"] for row in rows),
            "incomplete_lap_rows": sum(not row["complete_lap_record"] for row in rows),
        },
        "sources": source_meta["source_counts"],
        "source_available": source_meta["source_available"],
        "temporal_joins": source_meta["temporal_join_evaluated"],
        "future_temporal_joins": future_temporal_joins,
        "examples": rows[:3],
    }


def _distribution(rows: list[dict[str, Any]], key: str) -> dict[str, float | None]:
    values = [row[key] for row in rows if row[key] is not None]
    ordered = sorted(values)

    def percentile(percent: int) -> float | None:
        if not ordered:
            return None
        index = (len(ordered) - 1) * percent / 100
        lower = int(index)
        upper = min(lower + 1, len(ordered) - 1)
        return round(
            ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower),
            3,
        )

    return {
        "count": len(values),
        "min": round(min(values), 3) if values else None,
        "max": round(max(values), 3) if values else None,
        "mean": round(sum(values) / len(values), 3) if values else None,
        "median": round(median(values), 3) if values else None,
        "p75": percentile(75),
        "p90": percentile(90),
        "p95": percentile(95),
        "p99": percentile(99),
    }


def _session_inventory(bronze_dir: Path) -> list[tuple[int, int]]:
    inventory = []
    for season_dir in sorted(bronze_dir.glob("season=*")):
        if not season_dir.is_dir():
            continue
        season = int(season_dir.name.split("=", 1)[1])
        for session_dir in sorted(season_dir.glob("session=*")):
            if session_dir.is_dir():
                inventory.append((season, int(session_dir.name.split("=", 1)[1])))
    return inventory


def _session_anomalies(
    report: dict[str, Any], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    session_key = report["session"]["session_key"]

    def add(code: str, detail: Any) -> None:
        anomalies.append({"session_key": session_key, "code": code, "detail": detail})

    if report["row_count_difference"] != 0:
        add("row_count_difference", report["row_count_difference"])
    if report["duplicate_key_count"]:
        add("duplicate_keys", report["duplicate_key_count"])
    if any(report["future_temporal_joins"].values()):
        add("future_temporal_join", report["future_temporal_joins"])
    if not report["stints"]["has_stint_pct"]:
        add("no_stints", "all laps lack an assigned stint")
    if not report["weather"]["coverage_pct"]:
        add("no_weather", "no lap has fresh weather")
    if report["position"]["available"] == 0:
        add("no_position", "no historical position exists")
    if report["race_control"]["red_flag_rows"]:
        add("red_flag_rows", report["race_control"]["red_flag_rows"])
    if any(
        row["safety_car_active"] and row["virtual_safety_car_active"] for row in rows
    ):
        add("sc_and_vsc_same_row", "physical SC and VSC active together")
    if any(
        row["red_flag_active"] and row["race_control_recent_event"] == "CHEQUERED FLAG"
        for row in rows
    ):
        add("chequered_as_red", "CHEQUERED FLAG produced red_flag_active")
    if not report["source_available"].get("pit", False):
        add("pit_source_unavailable", "expected Bronze no-results response")
    return anomalies


def build_all_sessions(
    bronze_dir: Path = DEFAULT_BRONZE,
    silver_dir: Path = DEFAULT_SILVER,
) -> dict[str, Any]:
    inventory = _session_inventory(bronze_dir)
    session_reports = []
    anomalies = []
    total_rows: list[dict[str, Any]] = []
    for season, session_key in inventory:
        output_path, rows, metadata = build_session(
            bronze_dir, silver_dir, season, session_key
        )
        report = validate(rows, metadata["bronze_lap_count"], metadata)
        report["silver_path"] = str(output_path)
        report_path = output_path.parent / "validation.json"
        with report_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        session_reports.append(report)
        anomalies.extend(_session_anomalies(report, rows))
        total_rows.extend(rows)

    total_bronze = sum(report["bronze_lap_count"] for report in session_reports)
    total_silver = len(total_rows)
    global_keys = [
        (row["session_key"], row["driver_number"], row["lap_number"])
        for row in total_rows
    ]
    source_names = ("stints", "weather", "position", "intervals", "pit", "race_control")
    global_summary = {
        "expected_sessions": 70,
        "processed_sessions": len(session_reports),
        "sessions_by_season": dict(
            Counter(report["session"]["year"] for report in session_reports)
        ),
        "missing_sessions": [],
        "total_bronze_rows": total_bronze,
        "total_silver_rows": total_silver,
        "row_difference": total_silver - total_bronze,
        "duplicate_key_count": len(global_keys) - len(set(global_keys)),
        "coverage": {
            "stints_pct": round(
                100 * sum(r["has_stint"] for r in total_rows) / total_silver, 2
            )
            if total_silver
            else 0,
            "weather_pct": round(
                100 * sum(r["has_weather"] for r in total_rows) / total_silver, 2
            )
            if total_silver
            else 0,
            "position_available_pct": round(
                100 * sum(r["position_available"] for r in total_rows) / total_silver, 2
            )
            if total_silver
            else 0,
            "position_missing_pct": round(
                100 * sum(r["position_missing"] for r in total_rows) / total_silver, 2
            )
            if total_silver
            else 0,
            "position_stale_pct": round(
                100 * sum(r["position_stale"] for r in total_rows) / total_silver, 2
            )
            if total_silver
            else 0,
            "intervals_pct": round(
                100 * sum(r["has_interval"] for r in total_rows) / total_silver, 2
            )
            if total_silver
            else 0,
            "pit_available_pct": round(
                100 * sum(r["pit_data_available"] for r in total_rows) / total_silver, 2
            )
            if total_silver
            else 0,
            "race_control_rows_pct": round(
                100
                * sum(bool(r["race_control_event_count"]) for r in total_rows)
                / total_silver,
                2,
            )
            if total_silver
            else 0,
        },
        "position": {
            "available": sum(r["position_available"] for r in total_rows),
            "missing": sum(r["position_missing"] for r in total_rows),
            "stale": sum(r["position_stale"] for r in total_rows),
            "age_seconds": _distribution(total_rows, "position_timestamp_age_seconds"),
        },
        "race_control": {
            "safety_car_rows": sum(r["safety_car_active"] for r in total_rows),
            "virtual_safety_car_rows": sum(
                r["virtual_safety_car_active"] for r in total_rows
            ),
            "yellow_flag_rows": sum(r["yellow_flag_active"] for r in total_rows),
            "red_flag_rows": sum(r["red_flag_active"] for r in total_rows),
            "yellow_scopes": dict(
                Counter(
                    r["yellow_flag_scope"] for r in total_rows if r["yellow_flag_scope"]
                )
            ),
            "session_statuses": dict(
                Counter(r["session_status"] for r in total_rows if r["session_status"])
            ),
        },
        "causality": {
            "evaluated": {
                name: sum(report["temporal_joins"][name] for report in session_reports)
                for name in ("weather", "position", "intervals", "race_control")
            },
            "future": {
                name: sum(
                    report["future_temporal_joins"][name] for report in session_reports
                )
                for name in ("weather", "position", "intervals", "race_control")
            },
        },
        "quality": {
            "lap_timestamp_null": sum(
                r["quality"]["missing_lap_timestamp"] for r in session_reports
            ),
            "laps_without_stint": sum(not row["has_stint"] for row in total_rows),
            "weather_missing": sum(not row["has_weather"] for row in total_rows),
            "position_missing": sum(row["position_missing"] for row in total_rows),
            "intervals_missing": sum(not row["has_interval"] for row in total_rows),
            "pit_unavailable_rows": sum(
                not row["pit_data_available"] for row in total_rows
            ),
            "incomplete_laps": sum(
                r["quality"]["incomplete_lap_rows"] for r in session_reports
            ),
            "possible_early_exit_rows": sum(
                r["quality"]["possible_early_exit_rows"] for r in session_reports
            ),
        },
        "source_sessions_without_data": {
            name: sum(
                not report["source_available"].get(name, False)
                for report in session_reports
            )
            for name in source_names
        },
        "anomaly_count": len(anomalies),
    }
    silver_dir.mkdir(parents=True, exist_ok=True)
    report_path = silver_dir / "global_validation.json"
    anomaly_path = silver_dir / "anomalies.json"
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(global_summary, handle, ensure_ascii=False, indent=2)
    with anomaly_path.open("w", encoding="utf-8") as handle:
        json.dump(anomalies, handle, ensure_ascii=False, indent=2)
    return {
        "summary": global_summary,
        "anomalies": anomalies,
        "reports": session_reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build and validate F1 Silver from Bronze"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="process every Bronze session and write global reports",
    )
    parser.add_argument("--season", type=int, default=2024)
    parser.add_argument("--session-key", type=int, default=9550)
    parser.add_argument("--bronze-dir", type=Path, default=DEFAULT_BRONZE)
    parser.add_argument("--silver-dir", type=Path, default=DEFAULT_SILVER)
    args = parser.parse_args()
    if args.all:
        result = build_all_sessions(args.bronze_dir, args.silver_dir)
        print(
            json.dumps(
                {
                    "global_validation": str(
                        args.silver_dir / "global_validation.json"
                    ),
                    "anomalies": str(args.silver_dir / "anomalies.json"),
                    "processed_sessions": result["summary"]["processed_sessions"],
                    "silver_rows": result["summary"]["total_silver_rows"],
                },
                indent=2,
            )
        )
        return
    output_path, rows, metadata = build_session(
        args.bronze_dir, args.silver_dir, args.season, args.session_key
    )
    report = validate(rows, metadata["bronze_lap_count"], metadata)
    report_path = output_path.parent / "validation.json"
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                "silver": str(output_path),
                "validation": str(report_path),
                "rows": len(rows),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
