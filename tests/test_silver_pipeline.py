import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.silver_pipeline import (
    _race_control_state,
    _stint_for_lap,
    asof_previous,
    strict_decimal,
)


def test_stint_shared_start_uses_next_start_as_exclusive_boundary():
    stints = [
        {"driver_number": 1, "stint_number": 1, "lap_start": 1, "lap_end": 1},
        {"driver_number": 1, "stint_number": 2, "lap_start": 1, "lap_end": 54},
        {"driver_number": 1, "stint_number": 3, "lap_start": 54, "lap_end": 59},
    ]

    first, _ = _stint_for_lap(stints, 1, 1, 59)
    middle, _ = _stint_for_lap(stints, 1, 53, 59)
    last, _ = _stint_for_lap(stints, 1, 54, 59)

    assert first["stint_number"] == 2
    assert middle["stint_number"] == 2
    assert last["stint_number"] == 3


def test_asof_never_selects_future_measurement():
    lap_time = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    rows = [{"session_key": 1, "date": "2024-01-01T12:00:01+00:00", "value": 1}]

    selected, age = asof_previous(rows, (1,), lap_time, ("session_key",))

    assert selected is None
    assert age is None


def test_strict_decimal_does_not_turn_unknowns_into_zero():
    assert strict_decimal(1.25) == 1.25
    assert strict_decimal("2.5") == 2.5
    assert strict_decimal("") is None
    assert strict_decimal("UNKNOWN") is None
    assert strict_decimal("nan") is None


def test_race_control_separates_vsc_and_rejects_chequered_as_red():
    events = [
        {
            "date": "2024-01-01T12:00:00+00:00",
            "category": "SafetyCar",
            "message": "VIRTUAL SAFETY CAR DEPLOYED",
            "flag": None,
            "scope": None,
        },
        {
            "date": "2024-01-01T12:01:00+00:00",
            "category": "Flag",
            "message": "CHEQUERED FLAG",
            "flag": "CHEQUERED",
            "scope": "Track",
        },
    ]

    state = _race_control_state(
        events, {"date_start": "2024-01-01T12:00:30+00:00", "lap_number": 1}
    )

    assert state["virtual_safety_car_active"] is True
    assert state["safety_car_active"] is False
    assert state["red_flag_active"] is False


def test_resolve_driver_pits_standard_sequence():
    from src.silver_pipeline import resolve_driver_pits

    pits = [{"driver_number": 10, "lap_number": 20, "date": "2024-06-30T13:27:27.391000+00:00"}]
    stints = [
        {"driver_number": 10, "stint_number": 1, "lap_start": 1, "lap_end": 20, "compound": "MEDIUM", "tyre_age_at_start": 0},
        {"driver_number": 10, "stint_number": 2, "lap_start": 21, "lap_end": 42, "compound": "HARD", "tyre_age_at_start": 0},
    ]

    details = resolve_driver_pits(pits, stints)

    assert 20 in details
    assert details[20]["pit_stop_number"] == 1
    assert details[20]["current_compound"] == "MEDIUM"
    assert details[20]["new_compound"] == "HARD"
    assert details[20]["stint_in_number"] == 1
    assert details[20]["new_stint_number"] == 2


def test_resolve_driver_pits_shared_lap_boundary_2023():
    from src.silver_pipeline import resolve_driver_pits

    pits = [{"driver_number": 10, "lap_number": 10, "date": "2023-06-18T18:17:04.109000+00:00"}]
    stints = [
        {"driver_number": 10, "stint_number": 1, "lap_start": 1, "lap_end": 10, "compound": "SOFT", "tyre_age_at_start": 0},
        {"driver_number": 10, "stint_number": 2, "lap_start": 10, "lap_end": 33, "compound": "HARD", "tyre_age_at_start": 0},
    ]

    details = resolve_driver_pits(pits, stints)

    assert 10 in details
    assert details[10]["current_compound"] == "SOFT"
    assert details[10]["new_compound"] == "HARD"


def test_resolve_driver_pits_multiple_stops():
    from src.silver_pipeline import resolve_driver_pits

    pits = [
        {"driver_number": 1, "lap_number": 23, "date": "2024-06-30T13:30:32+00:00"},
        {"driver_number": 1, "lap_number": 51, "date": "2024-06-30T14:03:40+00:00"},
        {"driver_number": 1, "lap_number": 64, "date": "2024-06-30T14:19:30+00:00"},
    ]
    stints = [
        {"driver_number": 1, "stint_number": 1, "lap_start": 1, "lap_end": 23, "compound": "MEDIUM", "tyre_age_at_start": 0},
        {"driver_number": 1, "stint_number": 2, "lap_start": 24, "lap_end": 51, "compound": "HARD", "tyre_age_at_start": 0},
        {"driver_number": 1, "stint_number": 3, "lap_start": 52, "lap_end": 64, "compound": "MEDIUM", "tyre_age_at_start": 3},
        {"driver_number": 1, "stint_number": 4, "lap_start": 65, "lap_end": 71, "compound": "SOFT", "tyre_age_at_start": 0},
    ]

    details = resolve_driver_pits(pits, stints)

    assert len(details) == 3
    assert details[23]["current_compound"] == "MEDIUM"
    assert details[23]["new_compound"] == "HARD"
    assert details[51]["current_compound"] == "HARD"
    assert details[51]["new_compound"] == "MEDIUM"
    assert details[64]["current_compound"] == "MEDIUM"
    assert details[64]["new_compound"] == "SOFT"


def test_resolve_driver_pits_retirement_in_pits():
    from src.silver_pipeline import resolve_driver_pits

    pits = [{"driver_number": 44, "lap_number": 25, "date": "2024-06-30T13:35:00+00:00"}]
    stints = [
        {"driver_number": 44, "stint_number": 1, "lap_start": 1, "lap_end": 25, "compound": "HARD", "tyre_age_at_start": 0},
    ]

    details = resolve_driver_pits(pits, stints)

    assert 25 in details
    assert details[25]["current_compound"] == "HARD"
    assert details[25]["new_compound"] is None


def test_resolve_driver_pits_lap_one_pit():
    from src.silver_pipeline import resolve_driver_pits

    pits = [{"driver_number": 16, "lap_number": 1, "date": "2024-06-30T13:04:53+00:00"}]
    stints = [
        {"driver_number": 16, "stint_number": 1, "lap_start": 1, "lap_end": 1, "compound": "MEDIUM", "tyre_age_at_start": 0},
        {"driver_number": 16, "stint_number": 2, "lap_start": 2, "lap_end": 16, "compound": "HARD", "tyre_age_at_start": 0},
    ]

    details = resolve_driver_pits(pits, stints)

    assert 1 in details
    assert details[1]["current_compound"] == "MEDIUM"
    assert details[1]["new_compound"] == "HARD"
    assert details[1]["pit_stop_number"] == 1

