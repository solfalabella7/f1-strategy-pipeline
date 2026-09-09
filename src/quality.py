"""One executable quality contract for Airflow, CLI and release validation."""
from collections import Counter
import csv
import math
from pathlib import Path

from src.decisions import TARGET, CLASSES, FEATURES
from src.io_utils import timestamp

PRIMARY_KEY = ("session_key", "driver_number", "lap_number")
BOOL_COLUMNS = set("""is_pit_out_lap has_stint has_weather weather_stale has_position
position_available position_missing position_stale has_interval interval_stale
pit_data_available pit_stop lap_timestamp_available has_lap_duration complete_sector_times
complete_speed_measurements complete_lap_record possible_early_exit safety_car_active
virtual_safety_car_active yellow_flag_active red_flag_active race_control_state_known
race_control_transition_pending decision_safety_car decision_virtual_safety_car
decision_yellow_flag decision_red_flag decision_state_known decision_eligible target_available""".split())
NUMBER_COLUMNS = set("""season session_key meeting_key driver_number lap_number circuit_key
lap_duration duration_sector_1 duration_sector_2 duration_sector_3 i1_speed i2_speed st_speed
stint_number tyre_age_at_start tyre_age air_temperature track_temperature humidity pressure
rainfall wind_direction wind_speed weather_timestamp_age_seconds position
position_timestamp_age_seconds interval gap_to_leader interval_timestamp_age_seconds
pit_duration lane_duration stop_duration driver_lap_count driver_last_lap_observed
session_max_lap_observed laps_missing_until_session_max race_control_event_count
decision_tyre_age decision_air_temperature decision_track_temperature decision_humidity
decision_rainfall decision_position decision_interval decision_gap_to_leader pace_last_3
pace_delta_last_3""".split())
DATE_COLUMNS = set("""session_date_start lap_date_start weather_timestamp position_timestamp
interval_timestamp pit_date race_control_recent_event_timestamp decision_timestamp
decision_race_control_timestamp decision_weather_timestamp decision_position_timestamp
decision_intervals_timestamp target_pit_event_timestamp""".split())
STRING_COLUMNS = set("""session_name session_type circuit_short_name country_code country_name
meeting_name full_name name_acronym team_name team_colour country_code_driver current_compound
stint_assignment_status weather_join_method position_join_method interval_raw gap_to_leader_raw
interval_join_method timestamp_join_status yellow_flag_scope session_status race_control_recent_event
race_control_join_status decision_exclusion_reason target_exclusion_reason""".split()) | {TARGET}


def column_type(name):
    for columns, kind in ((BOOL_COLUMNS, "boolean"), (NUMBER_COLUMNS, "numeric"),
                          (DATE_COLUMNS, "datetime_utc"), (STRING_COLUMNS, "categorical_or_text")):
        if name in columns:
            return kind
    raise ValueError(f"Column without declared type: {name}")


class QualityError(ValueError):
    def __init__(self, report):
        self.report = report
        super().__init__("Quality validation failed: " + "; ".join(report["errors"]))


def validate_csv(path: Path, min_rows=1001, require_target=True):
    nulls, invalid, classes, reasons = Counter(), Counter(), Counter(), Counter()
    keys, errors, populated_types = set(), [], set()
    duplicates = count = trainable = 0
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)):
            errors.append("duplicate_columns")
        required = set(PRIMARY_KEY) | ({TARGET, "decision_eligible", "target_available", "target_exclusion_reason"} if require_target else set())
        if required - set(fields):
            errors.append("missing_columns: " + ",".join(sorted(required - set(fields))))
        types = {}
        for name in fields:
            try:
                types[name] = column_type(name)
            except ValueError:
                errors.append("undeclared_type: " + name)
        for row in reader:
            count += 1
            if None in row or any(v is None for v in row.values()):
                invalid["malformed_csv_row"] += 1
            key = tuple(row.get(k) for k in PRIMARY_KEY)
            if any(not v or not v.isdigit() or int(v) <= 0 for v in key):
                invalid["invalid_primary_key"] += 1
            duplicates += key in keys
            keys.add(key)
            for name in fields:
                value = row.get(name)
                if value is None or value == "":
                    nulls[name] += 1
                    continue
                kind = types.get(name)
                populated_types.add(kind)
                if kind == "boolean" and value not in {"True", "False"}:
                    invalid[name] += 1
                elif kind == "numeric":
                    try:
                        if not math.isfinite(float(value)):
                            invalid[name] += 1
                    except ValueError:
                        invalid[name] += 1
                elif kind == "datetime_utc" and timestamp(value) is None:
                    invalid[name] += 1
            for left, right in (("safety_car_active", "virtual_safety_car_active"), ("decision_safety_car", "decision_virtual_safety_car")):
                if row.get(left) == row.get(right) == "True":
                    invalid["simultaneous_sc_vsc"] += 1
            for reference, joined in (
                ("lap_date_start", ("weather_timestamp", "position_timestamp", "interval_timestamp", "race_control_recent_event_timestamp")),
                ("decision_timestamp", ("decision_weather_timestamp", "decision_position_timestamp", "decision_intervals_timestamp", "decision_race_control_timestamp")),
            ):
                anchor = timestamp(row.get(reference))
                for name in joined:
                    date = timestamp(row.get(name))
                    if date and anchor and date > anchor:
                        invalid["future_join:" + name] += 1
            if require_target:
                label = row.get(TARGET) or ""
                if label and label not in CLASSES:
                    invalid["invalid_target_class"] += 1
                if (row.get("target_available") == "True") != bool(label):
                    invalid["target_availability_mismatch"] += 1
                if not label and not row.get("target_exclusion_reason"):
                    invalid["unexplained_missing_target"] += 1
                if label:
                    classes[label] += 1
                else:
                    reasons[row.get("target_exclusion_reason")] += 1
                trainable += bool(label) and row.get("decision_eligible") == "True"
    if count < min_rows:
        errors.append(f"insufficient_rows: {count} < {min_rows}")
    useful = set(fields) & (set(FEATURES) | {"lap_duration", TARGET, "air_temperature", "position"})
    if len(useful) < 5:
        errors.append("fewer_than_five_useful_columns")
    if duplicates:
        errors.append(f"duplicate_keys: {duplicates}")
    empty = [name for name in fields if nulls[name] == count]
    if empty:
        errors.append("empty_columns: " + ",".join(empty))
    if not {"numeric", "categorical_or_text", "datetime_utc"} <= populated_types:
        errors.append("missing_required_type_mix")
    if invalid:
        errors.append("invalid_values_or_invariants: " + str(dict(invalid)))
    if require_target and not trainable:
        errors.append("no_eligible_labeled_rows")
    report = {
        "status": "failed" if errors else "passed", "errors": errors,
        "total_rows": count, "total_cols": len(fields), "useful_columns": sorted(useful),
        "duplicate_key_count": duplicates, "empty_columns": empty,
        "schema": types, "invalid_counts": dict(invalid),
        "nulls": {name: {"count": nulls[name], "pct": round(100 * nulls[name] / count, 3) if count else 0} for name in fields},
        "target_classes": dict(classes), "target_missing_reasons": dict(reasons),
        "eligible_labeled_rows": trainable,
        "unit_of_analysis": "Una vuelta registrada de un piloto en una carrera; clave (session_key, driver_number, lap_number).",
    }
    if errors:
        raise QualityError(report)
    return report
