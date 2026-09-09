"""End-of-lap features and conservative next-lap observed tyre-change labels."""
from collections import Counter, defaultdict, deque
from datetime import timedelta
from statistics import median

from src.io_utils import timestamp
from src.track_state import TrackTimeline

TARGET = "accion_observada_proxima_vuelta"
COMPOUNDS = ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET")
CLASSES = ("CONTINUAR",) + tuple("BOX_" + c for c in COMPOUNDS)
NUMERIC_FEATURES = (
    "lap_number", "decision_tyre_age", "pace_last_3", "pace_delta_last_3",
    "decision_air_temperature", "decision_track_temperature", "decision_humidity",
    "decision_rainfall", "decision_position", "decision_interval", "decision_gap_to_leader",
    "decision_safety_car", "decision_virtual_safety_car", "decision_yellow_flag",
)
CATEGORICAL_FEATURES = ("circuit_short_name", "current_compound")
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def end_of_lap(row):
    start = timestamp(row.get("lap_date_start"))
    duration = row.get("lap_duration")
    if start is None or not isinstance(duration, (int, float)) or not 0 < duration < 600:
        return None
    return start + timedelta(seconds=duration)


def enrich_decisions(rows, sources, availability):
    # Imported here to preserve compatibility of existing public Silver helpers.
    from src.silver_pipeline import _asof_indexed, _build_asof_index, strict_decimal

    track = TrackTimeline(sources["race_control"])
    indexes = {
        name: _build_asof_index(sources[name], ("session_key",) if name == "weather" else ("session_key", "driver_number"))
        for name in ("weather", "position", "intervals")
    }
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["session_key"], row["driver_number"])].append(row)
    for (session, driver), laps in grouped.items():
        laps.sort(key=lambda r: r["lap_number"])
        by_lap = {r["lap_number"]: r for r in laps}
        pits = defaultdict(list)
        for pit in sources["pit"]:
            if pit.get("driver_number") == driver:
                pits[pit.get("lap_number")].append(pit)
        stints = [s for s in sources["stints"] if s.get("driver_number") == driver]
        history = deque(maxlen=3)
        previous_lap = None
        previous_stint = None
        for row in laps:
            number = row["lap_number"]
            moment = end_of_lap(row)
            state = track.at(moment)
            if previous_lap != number - 1 or previous_stint != row["stint_number"]:
                history.clear()
            previous_lap, previous_stint = number, row["stint_number"]
            row["decision_timestamp"] = moment.isoformat() if moment else None
            row["decision_tyre_age"] = row["tyre_age"] + 1 if row["tyre_age"] is not None else None
            row["decision_safety_car"] = state["safety_car_active"]
            row["decision_virtual_safety_car"] = state["virtual_safety_car_active"]
            row["decision_yellow_flag"] = state["yellow_flag_active"]
            row["decision_red_flag"] = state["red_flag_active"]
            row["decision_state_known"] = state["race_control_state_known"]
            row["decision_race_control_timestamp"] = state["race_control_recent_event_timestamp"]
            for source, fields in {
                "weather": ("air_temperature", "track_temperature", "humidity", "rainfall"),
                "position": ("position",),
                "intervals": ("interval", "gap_to_leader"),
            }.items():
                key = (session,) if source == "weather" else (session, driver)
                selected, age = _asof_indexed(indexes[source], key, moment)
                usable = selected is not None and (source == "position" or age <= 120)
                row[f"decision_{source}_timestamp"] = selected.get("date") if selected else None
                for field in fields:
                    value = selected.get(field) if usable else None
                    row["decision_" + field] = strict_decimal(value)
            clean = (moment is not None and not row["is_pit_out_lap"] and not pits[number]
                     and state["race_control_state_known"] and not state["red_flag_active"]
                     and not state["safety_car_active"] and not state["virtual_safety_car_active"]
                     and not state["yellow_flag_active"])
            if clean:
                history.append(row["lap_duration"])
            else:
                history.clear()
            row["pace_last_3"] = median(history) if history else None
            row["pace_delta_last_3"] = history[-1] - history[0] if len(history) >= 2 else None
            reason = None
            if moment is None:
                reason = "missing_or_invalid_lap_end"
            elif row["current_compound"] not in COMPOUNDS or row["tyre_age"] is None:
                reason = "unknown_current_tyres"
            elif row["is_pit_out_lap"] or pits[number]:
                reason = "current_pit_or_out_lap"
            elif not state["race_control_state_known"]:
                reason = "unknown_track_state"
            elif state["red_flag_active"] or state["session_status"] in {"SESSION FINISHED", "SESSION ABORTED"}:
                reason = "session_not_racing"
            row["decision_eligible"] = reason is None
            row["decision_exclusion_reason"] = reason

            label, why, event_date = None, None, None
            following = by_lap.get(number + 1)
            horizon_end = end_of_lap(following) if following else None
            if moment is None:
                why = "missing_decision_timestamp"
            elif following is None or horizon_end is None or horizon_end <= moment:
                why = "unobserved_next_lap"
            elif timestamp(following.get("lap_date_start")) < moment - timedelta(seconds=2):
                why = "overlapping_lap_times"
            elif not availability["pit"] or not availability["stints"]:
                why = "missing_pit_or_stint_source"
            elif state["red_flag_active"] or any(
                moment < date <= horizon_end and snapshot["red_flag_active"]
                for date, snapshot in zip(track.times, track.states)
            ):
                why = "red_flag_in_horizon"
            else:
                events = pits[number + 1]
                starts = [s for s in stints if s.get("lap_start") in {number + 1, number + 2}]
                if not events:
                    if starts or following["stint_number"] != row["stint_number"] or not row["has_stint"]:
                        why = "stint_change_without_pit_evidence"
                    else:
                        label = "CONTINUAR"
                elif len(events) != 1:
                    why = "multiple_pit_events"
                else:
                    # Primary observed convention: pit lap L, new stint/out-lap L+1.
                    # Shared starts, same-lap starts and unsupported variants remain null.
                    candidates = [s for s in starts if s.get("lap_start") == number + 2]
                    after = by_lap.get(number + 2)
                    pit_time = timestamp(events[0].get("date"))
                    old = [s for s in stints if s.get("stint_number") == row["stint_number"]]
                    valid = (len(starts) == len(candidates) == len(old) == 1 and after is not None
                             and after["is_pit_out_lap"] is True
                             and old[0].get("lap_end") == number + 1
                             and candidates[0].get("stint_number") == after["stint_number"]
                             and candidates[0].get("stint_number") != row["stint_number"])
                    after_end = end_of_lap(after) if after else None
                    if pit_time is None or after_end is None or not moment < pit_time <= after_end:
                        why = "pit_timestamp_unconfirmed"
                    elif not valid:
                        why = "pit_stint_alignment_ambiguous"
                    elif candidates[0].get("compound") not in COMPOUNDS:
                        why = "unknown_next_compound"
                    else:
                        label = "BOX_" + candidates[0]["compound"]
                        event_date = pit_time.isoformat()
            row[TARGET] = label
            row["target_available"] = label is not None
            row["target_exclusion_reason"] = why
            row["target_pit_event_timestamp"] = event_date
    return rows


def decision_summary(rows):
    return {
        "target": TARGET,
        "class_counts": dict(Counter(r[TARGET] for r in rows if r[TARGET] is not None)),
        "target_missing_reasons": dict(Counter(r["target_exclusion_reason"] for r in rows if not r["target_available"])),
        "decision_exclusion_reasons": dict(Counter(r["decision_exclusion_reason"] for r in rows if not r["decision_eligible"])),
        "training_rows": sum(r["decision_eligible"] and r["target_available"] for r in rows),
        "predictors": list(FEATURES),
    }
