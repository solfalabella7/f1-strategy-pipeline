from datetime import datetime, timezone

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
