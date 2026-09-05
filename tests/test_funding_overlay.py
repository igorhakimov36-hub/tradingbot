"""
Tests for strategy/research/funding_overlay.py.
"""

from datetime import datetime, timedelta, timezone

import pytest

from strategy.research.funding_overlay import (
    funding_events_for_position,
    funding_summary_for_trade,
    load_funding_records_with_mark_price,
)

T0 = datetime(2024, 2, 1, 0, 0, tzinfo=timezone.utc)
T8 = datetime(2024, 2, 1, 8, 0, tzinfo=timezone.utc)
T16 = datetime(2024, 2, 1, 16, 0, tzinfo=timezone.utc)
T24 = datetime(2024, 2, 2, 0, 0, tzinfo=timezone.utc)


def _record(t, rate, mark_price=100.0):
    return {"timestamp": t, "rate": rate, "mark_price": mark_price}


# =========================================================
# Requirement 1: funding payment/receipt signs
# =========================================================


def test_long_pays_on_positive_rate():
    events = funding_events_for_position(T0, T24, "LONG", quantity=10.0, funding_records=[_record(T8, 0.0001, 100.0)])
    assert len(events) == 1
    # payment = -(+1) * (10*100) * 0.0001 = -0.1 (LONG pays -> negative cash flow)
    assert events[0]["payment"] == pytest.approx(-0.1)


def test_short_receives_on_positive_rate():
    events = funding_events_for_position(T0, T24, "SHORT", quantity=10.0, funding_records=[_record(T8, 0.0001, 100.0)])
    assert events[0]["payment"] == pytest.approx(0.1)


def test_short_pays_on_negative_rate():
    events = funding_events_for_position(T0, T24, "SHORT", quantity=10.0, funding_records=[_record(T8, -0.0001, 100.0)])
    assert events[0]["payment"] == pytest.approx(-0.1)


def test_long_receives_on_negative_rate():
    events = funding_events_for_position(T0, T24, "LONG", quantity=10.0, funding_records=[_record(T8, -0.0001, 100.0)])
    assert events[0]["payment"] == pytest.approx(0.1)


def test_notional_uses_mark_price_times_quantity_no_double_leverage():
    # notional = quantity * mark_price ONLY - no separate leverage factor applied.
    events = funding_events_for_position(T0, T24, "LONG", quantity=5.0, funding_records=[_record(T8, 0.001, 200.0)])
    expected = -1.0 * (5.0 * 200.0) * 0.001
    assert events[0]["payment"] == pytest.approx(expected)


def test_invalid_side_raises():
    with pytest.raises(ValueError):
        funding_events_for_position(T0, T24, "SIDEWAYS", 10.0, [_record(T8, 0.0001)])


# =========================================================
# Requirement 2: position-open eligibility and settlement boundaries
# =========================================================


def test_settlement_before_entry_not_charged():
    before_entry = T0 - timedelta(hours=1)
    events = funding_events_for_position(T0, T24, "LONG", 10.0, [_record(before_entry, 0.0001)])
    assert events == []


def test_settlement_after_exit_not_charged():
    after_exit = T24 + timedelta(hours=1)
    events = funding_events_for_position(T0, T24, "LONG", 10.0, [_record(after_exit, 0.0001)])
    assert events == []


def test_settlement_strictly_between_entry_and_exit_charged():
    events = funding_events_for_position(T0, T24, "LONG", 10.0, [_record(T8, 0.0001), _record(T16, 0.0001)])
    assert len(events) == 2


def test_inclusive_boundary_charges_settlement_exactly_at_exit():
    events = funding_events_for_position(T0, T8, "LONG", 10.0, [_record(T8, 0.0001)], boundary="inclusive")
    assert len(events) == 1


def test_exclusive_exit_boundary_does_not_charge_settlement_exactly_at_exit():
    events = funding_events_for_position(T0, T8, "LONG", 10.0, [_record(T8, 0.0001)], boundary="exclusive_exit")
    assert events == []


def test_settlement_exactly_at_entry_is_charged_under_both_conventions():
    events_inclusive = funding_events_for_position(T8, T24, "LONG", 10.0, [_record(T8, 0.0001)], boundary="inclusive")
    events_exclusive = funding_events_for_position(T8, T24, "LONG", 10.0, [_record(T8, 0.0001)], boundary="exclusive_exit")
    assert len(events_inclusive) == 1
    assert len(events_exclusive) == 1


def test_never_open_position_never_charged():
    events = funding_events_for_position(T0, T0, "LONG", 10.0, [_record(T8, 0.0001)])
    assert events == []


# =========================================================
# Requirement 3: missing funding data never replaced with zero
# =========================================================


def test_missing_rate_flagged_not_zeroed():
    events = funding_events_for_position(T0, T24, "LONG", 10.0, [{"timestamp": T8, "rate": None, "mark_price": 100.0}])
    assert len(events) == 1
    assert events[0]["missing_data"] is True
    assert events[0]["payment"] is None


def test_missing_mark_price_flagged_not_zeroed():
    events = funding_events_for_position(T0, T24, "LONG", 10.0, [{"timestamp": T8, "rate": 0.0001, "mark_price": None}])
    assert events[0]["missing_data"] is True
    assert events[0]["payment"] is None


def test_summary_net_available_false_when_any_settlement_missing():
    records = [_record(T8, 0.0001), {"timestamp": T16, "rate": None, "mark_price": None}]
    summary = funding_summary_for_trade(T0, T24, "LONG", 10.0, records)
    assert summary["n_settlements"] == 2
    assert summary["n_missing"] == 1
    assert summary["net_available"] is False


def test_summary_net_available_true_when_complete():
    records = [_record(T8, 0.0001), _record(T16, -0.0002)]
    summary = funding_summary_for_trade(T0, T24, "LONG", 10.0, records)
    assert summary["net_available"] is True
    assert summary["n_missing"] == 0


def test_summary_paid_received_net_signs():
    # LONG: positive rate at T8 -> pays; negative rate at T16 -> receives.
    records = [_record(T8, 0.0001, 100.0), _record(T16, -0.0002, 100.0)]
    summary = funding_summary_for_trade(T0, T24, "LONG", 10.0, records)
    # T8: pays 0.1; T16: receives 0.2
    assert summary["paid"] == pytest.approx(0.1)
    assert summary["received"] == pytest.approx(0.2)
    assert summary["net"] == pytest.approx(0.1)


def test_zero_settlements_in_range_is_a_valid_empty_summary():
    summary = funding_summary_for_trade(T0, T0 + timedelta(minutes=5), "LONG", 10.0, [_record(T8, 0.0001)])
    assert summary["n_settlements"] == 0
    assert summary["net_available"] is True
    assert summary["net"] == 0.0


# =========================================================
# load_funding_records_with_mark_price
# =========================================================


def test_load_funding_records_with_mark_price(tmp_path):
    csv_path = tmp_path / "SOLUSDT-funding-2024-02.csv"
    csv_path.write_text(
        "fundingTime,fundingRate,markPrice,symbol\n"
        "1706745600000,0.00005150,96.92434636,SOLUSDT\n"
        "1706774400000,0.00010000,94.89019007,SOLUSDT\n",
        encoding="utf-8",
    )
    records = load_funding_records_with_mark_price(csv_path)
    assert len(records) == 2
    assert records[0]["rate"] == pytest.approx(0.0000515)
    assert records[0]["mark_price"] == pytest.approx(96.92434636)
    assert records[0]["timestamp"] < records[1]["timestamp"]


def test_load_funding_records_blank_fields_become_none(tmp_path):
    csv_path = tmp_path / "SOLUSDT-funding-blank.csv"
    csv_path.write_text(
        "fundingTime,fundingRate,markPrice,symbol\n"
        "1706745600000,,,SOLUSDT\n",
        encoding="utf-8",
    )
    records = load_funding_records_with_mark_price(csv_path)
    assert records[0]["rate"] is None
    assert records[0]["mark_price"] is None


# =========================================================
# Determinism
# =========================================================


def test_deterministic():
    records = [_record(T8, 0.0001), _record(T16, -0.0002)]
    r1 = funding_summary_for_trade(T0, T24, "LONG", 10.0, records)
    r2 = funding_summary_for_trade(T0, T24, "LONG", 10.0, records)
    assert r1 == r2
