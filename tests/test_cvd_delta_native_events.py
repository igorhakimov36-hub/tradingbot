"""
Tests for strategy/research/cvd_delta_native_events.py.
"""

from datetime import datetime, timedelta, timezone

import pytest

from strategy.research.cvd_delta_native_events import (
    classify_directional,
    edge_trigger_events,
    raw_directional_bar_count,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _readings(values):
    return [
        {"bar_i": i, "timestamp": START + timedelta(minutes=15 * i), "value": v}
        for i, v in enumerate(values)
    ]


# =========================================================
# classify_directional
# =========================================================


def test_classify_directional_cvd_direction():
    assert classify_directional("cvd_direction", "BULLISH") == "bullish"
    assert classify_directional("cvd_direction", "BEARISH") == "bearish"
    assert classify_directional("cvd_direction", "NEUTRAL") is None
    assert classify_directional("cvd_direction", None) is None


def test_classify_directional_divergence_and_exhaustion():
    assert classify_directional("price_cvd_divergence_flag", "bullish_divergence") == "bullish"
    assert classify_directional("price_cvd_divergence_flag", "bearish_divergence") == "bearish"
    assert classify_directional("price_cvd_divergence_flag", "none") is None
    assert classify_directional("cvd_exhaustion_flag", "bullish_exhaustion") == "bullish"
    assert classify_directional("cvd_exhaustion_flag", "none") is None


def test_classify_directional_unknown_field_raises():
    with pytest.raises(ValueError):
        classify_directional("not_a_real_field", "BULLISH")


# =========================================================
# Requirement 1: persistent readings produce one-shot events
# =========================================================


def test_persistent_run_produces_exactly_one_event():
    values = ["none", "bullish_divergence", "bullish_divergence", "bullish_divergence", "none"]
    events = edge_trigger_events("price_cvd_divergence_flag", _readings(values))
    assert len(events) == 1
    assert events[0]["direction"] == "bullish"
    assert events[0]["bar_i"] == 1  # the bar the value FIRST changed


def test_raw_bar_count_counts_every_bar_not_deduplicated():
    values = ["none", "bullish_divergence", "bullish_divergence", "bullish_divergence", "none"]
    counts = raw_directional_bar_count("price_cvd_divergence_flag", _readings(values))
    assert counts == {"bullish": 3, "bearish": 0}


# =========================================================
# Requirement 2: distinct same-direction events retain distinct identities
# =========================================================


def test_same_direction_recurring_after_a_gap_is_a_second_event():
    values = ["none", "bullish_divergence", "none", "none", "bullish_divergence"]
    events = edge_trigger_events("price_cvd_divergence_flag", _readings(values))
    assert len(events) == 2
    assert events[0]["bar_i"] == 1
    assert events[1]["bar_i"] == 4
    assert events[0]["event_id"] != events[1]["event_id"]


def test_direct_flip_without_intervening_none_is_its_own_event():
    values = ["bullish_divergence", "bearish_divergence"]
    events = edge_trigger_events("price_cvd_divergence_flag", _readings(values))
    assert len(events) == 2
    assert events[0]["direction"] == "bullish"
    assert events[1]["direction"] == "bearish"
    assert events[1]["bar_i"] == 1


# =========================================================
# Requirement 3: events are available only at their real confirmation
# timestamp (no lookahead / no backdating - causal prefix consistency)
# =========================================================


def test_causal_prefix_consistency_no_lookahead():
    values = ["none", "bullish_divergence", "none", "bearish_divergence", "none"]
    readings = _readings(values)

    full = edge_trigger_events("price_cvd_divergence_flag", readings)
    prefix = edge_trigger_events("price_cvd_divergence_flag", readings[:3])

    # Every event found using only the first 3 bars must appear
    # identically (same confirmed_at, same bar_i) in the full run - a
    # later bar must never change what was already true earlier.
    for event in prefix:
        assert event in full


def test_confirmed_at_matches_the_bar_the_value_actually_changed():
    values = ["none", "none", "bearish_exhaustion"]
    events = edge_trigger_events("cvd_exhaustion_flag", _readings(values))
    assert len(events) == 1
    assert events[0]["confirmed_at"] == START + timedelta(minutes=30)  # bar_i=2
    assert events[0]["bar_i"] == 2


# =========================================================
# Determinism
# =========================================================


def test_deterministic():
    values = ["none", "bullish_divergence", "none", "bearish_divergence"]
    readings = _readings(values)
    r1 = edge_trigger_events("price_cvd_divergence_flag", readings)
    r2 = edge_trigger_events("price_cvd_divergence_flag", readings)
    assert r1 == r2
