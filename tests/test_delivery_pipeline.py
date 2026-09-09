import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.bronze import land_response
from src.decisions import FEATURES, TARGET
from src.io_utils import atomic_json, bronze_payload
from src.quality import QualityError, validate_csv
from src.release import expected_inventory
from src.silver_pipeline import build_session, _asof_indexed, _build_asof_index
from src.track_state import TrackTimeline


@pytest.fixture
def bronze(tmp_path):
    root = tmp_path / "bronze"
    folder = root / "season=2024/session=1"
    common = {"session_key": 1, "meeting_key": 1, "driver_number": 1}
    atomic_json(root / "season=2024/sessions.json", [{"session_key": 1, "meeting_key": 1, "year": 2024, "session_name": "Race", "session_type": "Race", "circuit_short_name": "Test", "date_start": "2024-01-01T12:00:00Z"}])
    atomic_json(root / "season=2024/meetings.json", [{"meeting_key": 1, "meeting_name": "Test GP"}])
    atomic_json(folder / "drivers.json", [dict(common, full_name="Test Driver")])
    atomic_json(folder / "laps.json", [dict(common, lap_number=i, date_start=f"2024-01-01T12:0{i-1}:00Z", lap_duration=60.0, is_pit_out_lap=i == 3) for i in range(1, 6)])
    atomic_json(folder / "stints.json", [dict(common, stint_number=1, lap_start=1, lap_end=2, compound="MEDIUM", tyre_age_at_start=0), dict(common, stint_number=2, lap_start=3, lap_end=5, compound="HARD", tyre_age_at_start=0)])
    atomic_json(folder / "pit.json", [dict(common, lap_number=2, date="2024-01-01T12:02:10Z", lane_duration=20)])
    atomic_json(folder / "race_control.json", [{"session_key": 1, "date": "2024-01-01T11:59:00Z", "category": "SessionStatus", "message": "SESSION STARTED"}])
    for name in ("weather", "position", "intervals"):
        atomic_json(folder / f"{name}.json", [dict(common, date="2024-01-01T12:00:00Z", air_temperature=20, track_temperature=30, humidity=50, rainfall=0, position=1, interval=0, gap_to_leader=0)])
    return root


def build(root, tmp_path):
    return build_session(root, tmp_path / "silver", 2024, 1)[1]


def change(root, name, transform):
    path = root / "season=2024/session=1" / f"{name}.json"
    atomic_json(path, transform(json.loads(path.read_text())))


def test_next_lap_target_uses_pit_and_next_out_stint(bronze, tmp_path):
    rows = build(bronze, tmp_path)
    assert rows[0][TARGET] == "BOX_HARD"
    assert rows[0]["decision_eligible"]
    assert rows[0]["decision_timestamp"] == "2024-01-01T12:01:00+00:00"
    assert not rows[1]["decision_eligible"]
    assert rows[-1][TARGET] is None
    assert rows[-1]["target_exclusion_reason"] == "unobserved_next_lap"


def test_same_compound_new_set_counts_as_change(bronze, tmp_path):
    change(bronze, "stints", lambda rows: [dict(r, compound="MEDIUM") for r in rows])
    assert build(bronze, tmp_path)[0][TARGET] == "BOX_MEDIUM"


@pytest.mark.parametrize("case", ["gap", "missing_source", "no_change_evidence", "past_pit", "red_flag"])
def test_ambiguous_targets_are_not_silent_continue(bronze, tmp_path, case):
    if case == "gap":
        change(bronze, "laps", lambda rows: [r for r in rows if r["lap_number"] != 2])
    elif case == "missing_source":
        change(bronze, "pit", lambda _: {"detail": "No results found."})
    elif case == "no_change_evidence":
        change(bronze, "stints", lambda rows: [dict(rows[0], lap_end=5)])
    elif case == "past_pit":
        change(bronze, "pit", lambda rows: [dict(rows[0], date="2024-01-01T11:00:00Z")])
    else:
        change(bronze, "race_control", lambda rows: rows + [{"session_key": 1, "date": "2024-01-01T12:01:30Z", "flag": "RED", "message": "RED FLAG"}])
    row = build(bronze, tmp_path)[0]
    assert row[TARGET] is None
    assert row["target_exclusion_reason"]


def test_future_changes_cannot_change_current_features(bronze, tmp_path):
    first = build(bronze, tmp_path)[0]
    change(bronze, "laps", lambda rows: [dict(r, lap_duration=90) if r["lap_number"] >= 4 else r for r in rows])
    change(bronze, "stints", lambda rows: [rows[0], dict(rows[1], compound="SOFT")])
    second = build(bronze, tmp_path)[0]
    assert {k: first[k] for k in FEATURES} == {k: second[k] for k in FEATURES}
    assert first[TARGET] != second[TARGET]


def test_restart_clears_old_red_and_sc():
    events = [
        {"date": "2024-01-01T12:00:00Z", "category": "SafetyCar", "message": "SAFETY CAR DEPLOYED"},
        {"date": "2024-01-01T12:01:00Z", "flag": "RED"},
        {"date": "2024-01-01T12:02:00Z", "category": "SessionStatus", "message": "SESSION STARTED"},
        {"date": "2024-01-01T12:03:00Z", "category": "SafetyCar", "message": "VIRTUAL SAFETY CAR DEPLOYED"},
    ]
    state = TrackTimeline(events).at("2024-01-01T12:04:00Z")
    assert state["virtual_safety_car_active"]
    assert not state["safety_car_active"] and not state["red_flag_active"]


def test_sector_clear_does_not_clear_other_sector():
    events = [{"date": f"2024-01-01T12:00:0{i}Z", "flag": flag, "scope": "Sector", "sector": sector}
              for i, (flag, sector) in enumerate((("YELLOW", 1), ("YELLOW", 2), ("CLEAR", 1)))]
    assert TrackTimeline(events).at("2024-01-01T12:01:00Z")["yellow_flag_active"]


def test_ending_notice_is_not_a_known_green_state():
    timeline = TrackTimeline([
        {"date": "2024-01-01T12:00:00Z", "category": "SafetyCar", "message": "SAFETY CAR DEPLOYED"},
        {"date": "2024-01-01T12:01:00Z", "category": "SafetyCar", "message": "SAFETY CAR IN THIS LAP"},
        {"date": "2024-01-01T12:02:00Z", "flag": "CLEAR", "scope": "Track", "message": "TRACK CLEAR"},
    ])
    assert not timeline.at("2024-01-01T12:01:30Z")["race_control_state_known"]
    assert not timeline.at("2024-01-01T12:02:30Z")["safety_car_active"]
    assert not timeline.at(None)["race_control_state_known"]


def test_production_asof_uses_instants_not_strings():
    index = _build_asof_index([{"session_key": 1, "date": "2024-01-01T09:00:00-03:00"}, {"session_key": 1, "date": "2024-01-01T12:00:01Z"}], ("session_key",))
    row, age = _asof_indexed(index, (1,), datetime(2024, 1, 1, 12, tzinfo=timezone.utc))
    assert row["date"].endswith("-03:00") and age == 0


def test_cache_corruption_is_preserved_and_fails(tmp_path):
    path = tmp_path / "laps.json"
    path.write_text("[unfinished")
    fetch = Mock()
    with pytest.raises(ValueError, match="Corrupt Bronze"):
        land_response("laps", {}, path, fetch, pause=lambda _: None)
    assert path.read_text() == "[unfinished"
    fetch.assert_not_called()


def test_invalid_http_payload_is_not_published(tmp_path):
    response = Mock(status_code=200, text='{"error":"bad"}')
    response.json.return_value = {"error": "bad"}
    with pytest.raises(ValueError):
        land_response("laps", {}, tmp_path / "laps.json", lambda *args: response, pause=lambda _: None)
    assert not (tmp_path / "laps.json").exists()


def test_no_results_is_valid_and_cached(tmp_path):
    response = Mock(status_code=404, text='{"detail":"No results found."}')
    response.json.return_value = {"detail": "No results found."}
    fetch = Mock(return_value=response)
    for _ in range(2):
        land_response("pit", {}, tmp_path / "pit.json", fetch, pause=lambda _: None)
    assert fetch.call_count == 1
    assert bronze_payload(response.json()) == ([], False)


def test_inventory_cannot_claim_no_missing_sessions_for_empty_input(tmp_path):
    with pytest.raises(ValueError, match="Empty"):
        expected_inventory(tmp_path)


def test_quality_rejects_one_row_three_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("session_key,driver_number,lap_number\n1,1,1\n")
    with pytest.raises(QualityError) as error:
        validate_csv(path)
    assert error.value.report["status"] == "failed"
    assert any("insufficient_rows" in e for e in error.value.report["errors"])


def test_quality_rejects_future_join_even_with_timezone_offsets(tmp_path):
    path = tmp_path / "bad.csv"
    rows = [{"session_key": 1, "driver_number": 1, "lap_number": 1,
             "current_compound": "HARD", "lap_duration": 90, "air_temperature": 20,
             "position": 1, "lap_date_start": "2024-01-01T09:00:00-03:00", "weather_timestamp": "2024-01-01T12:00:01Z"}]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(QualityError) as error:
        validate_csv(path, min_rows=1, require_target=False)
    assert error.value.report["invalid_counts"]["future_join:weather_timestamp"] == 1
