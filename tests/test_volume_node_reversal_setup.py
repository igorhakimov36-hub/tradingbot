from datetime import datetime, timezone

import pytest

from strategy.market_intelligence_snapshot import Level, MarketIntelligenceSnapshot
from strategy.setups.volume_node_reversal import VolumeNodeReversalSetup

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
SETUP = VolumeNodeReversalSetup()

BUCKET_SIZE = 50.0


def _level(kind, price, raw_extra=None):
    raw = {"width": 1}
    if raw_extra is not None:
        raw = raw_extra

    return Level(
        kind=kind, price=price, distance_from_price=0.0, swept=None,
        source_module="volume_profile", raw=raw,
    )


def _snapshot(levels=None, current_price=10000.0, bucket_size=BUCKET_SIZE, has_forming_profile=True):
    volume_profile = {}
    if has_forming_profile:
        volume_profile = {"current_forming_profile": {"bucket_size": bucket_size}}

    return MarketIntelligenceSnapshot(
        symbol="BTCUSDT", timeframe="15m", timestamp=START, current_price=current_price,
        structure={}, zones=[], levels=levels or [],
        order_flow={"delta": {}, "cvd": {}},
        sessions={"active_now": [], "previous_period_high_low": {}},
        intermarket={}, volume_profile=volume_profile, data_quality={},
    )


# =========================================================
# No fire - required condition
# =========================================================


def test_does_not_fire_with_no_levels():
    result = SETUP.evaluate(_snapshot(levels=[]))

    assert result.fired is False
    assert result.direction is None
    assert result.required_conditions[0].name == "price_at_high_volume_node"


def test_does_not_fire_without_a_poc_level():
    hvn = _level("hvn", price=9990.0)

    result = SETUP.evaluate(_snapshot(levels=[hvn], current_price=10000.0))

    assert result.fired is False


def test_does_not_fire_without_a_forming_profile_bucket_size():
    poc = _level("poc", price=10025.0)
    hvn = _level("hvn", price=9990.0)

    result = SETUP.evaluate(_snapshot(levels=[poc, hvn], current_price=10000.0, has_forming_profile=False))

    assert result.fired is False


def test_does_not_fire_when_price_outside_every_node_bucket():
    poc = _level("poc", price=10025.0)
    hvn = _level("hvn", price=9990.0)  # bucket [9990, 10040)

    result = SETUP.evaluate(_snapshot(levels=[poc, hvn], current_price=8000.0))

    assert result.fired is False


def test_does_not_fire_when_node_price_equals_poc():
    poc = _level("poc", price=10000.0)
    hvn = _level("hvn", price=10000.0)  # the POC itself, no directional read

    result = SETUP.evaluate(_snapshot(levels=[poc, hvn], current_price=10010.0))

    assert result.fired is False


def test_ignores_lvn_levels():
    poc = _level("poc", price=10025.0)
    lvn = _level("lvn", price=9990.0)

    result = SETUP.evaluate(_snapshot(levels=[poc, lvn], current_price=10000.0))

    assert result.fired is False


# =========================================================
# Fires - direction inference
# =========================================================


def test_node_below_poc_fires_long_support_read():
    poc = _level("poc", price=10025.0)
    hvn = _level("hvn", price=9950.0)  # below POC -> support

    result = SETUP.evaluate(_snapshot(levels=[poc, hvn], current_price=9960.0))

    assert result.fired is True
    assert result.direction == "LONG"
    assert result.setup_name == "volume_node_reversal"


def test_node_above_poc_fires_short_resistance_read():
    poc = _level("poc", price=9900.0)
    hvn = _level("hvn", price=10000.0)  # above POC -> resistance

    result = SETUP.evaluate(_snapshot(levels=[poc, hvn], current_price=10010.0))

    assert result.fired is True
    assert result.direction == "SHORT"


def test_fires_even_with_zero_additional_evidence():
    poc = _level("poc", price=10025.0)
    hvn = _level("hvn", price=9950.0, raw_extra={"width": 1})

    result = SETUP.evaluate(_snapshot(levels=[poc, hvn], current_price=9960.0))

    assert result.fired is True
    assert result.evidence_count == 0


def test_first_candidate_wins_when_multiple_nodes_qualify():
    poc = _level("poc", price=20000.0)
    first = _level("hvn", price=9950.0)   # bucket [9950,10000) contains 9960
    second = _level("hvn", price=9950.0)  # identical candidate, listed second

    result = SETUP.evaluate(_snapshot(levels=[poc, first, second], current_price=9960.0))

    assert result.fired is True


# =========================================================
# Stop-loss evidence (zone_high/zone_low, reused by the adapter unmodified)
# =========================================================


def test_support_read_zone_bounds_use_node_width_and_bucket_size():
    poc = _level("poc", price=10100.0)
    hvn = _level("hvn", price=9950.0, raw_extra={"width": 3})

    result = SETUP.evaluate(_snapshot(levels=[poc, hvn], current_price=9960.0, bucket_size=50.0))

    evidence = result.required_conditions[0].evidence
    assert evidence["zone_low"] == pytest.approx(9950.0 - 3 * 50.0)   # one full node-width below the bucket
    assert evidence["zone_high"] == pytest.approx(9950.0 + 50.0)      # top of the node's own bucket


def test_resistance_read_zone_bounds_use_node_width_and_bucket_size():
    poc = _level("poc", price=9800.0)
    hvn = _level("hvn", price=10000.0, raw_extra={"width": 2})

    result = SETUP.evaluate(_snapshot(levels=[poc, hvn], current_price=10010.0, bucket_size=50.0))

    evidence = result.required_conditions[0].evidence
    assert evidence["zone_low"] == pytest.approx(10000.0)                       # bottom of the node's own bucket
    assert evidence["zone_high"] == pytest.approx(10000.0 + 50.0 + 2 * 50.0)     # one full node-width above the bucket


# =========================================================
# Additional evidence
# =========================================================


def test_node_is_wide_satisfied_when_width_greater_than_one():
    poc = _level("poc", price=10100.0)
    hvn = _level("hvn", price=9950.0, raw_extra={"width": 2})

    result = SETUP.evaluate(_snapshot(levels=[poc, hvn], current_price=9960.0))

    wide_condition = next(c for c in result.additional_evidence if c.name == "node_is_wide")
    assert wide_condition.satisfied is True
    assert result.evidence_count >= 1


def test_node_is_wide_not_satisfied_for_single_bucket_width():
    poc = _level("poc", price=10100.0)
    hvn = _level("hvn", price=9950.0, raw_extra={"width": 1})

    result = SETUP.evaluate(_snapshot(levels=[poc, hvn], current_price=9960.0))

    wide_condition = next(c for c in result.additional_evidence if c.name == "node_is_wide")
    assert wide_condition.satisfied is False


def test_value_area_confluence_satisfied_when_node_inside_value_area():
    poc = _level("poc", price=10100.0)
    hvn = _level("hvn", price=9950.0)
    vah = _level("vah", price=10200.0)
    val = _level("val", price=9900.0)

    result = SETUP.evaluate(_snapshot(levels=[poc, hvn, vah, val], current_price=9960.0))

    confluence = next(c for c in result.additional_evidence if c.name == "value_area_confluence")
    assert confluence.satisfied is True
    assert result.evidence_count >= 1


def test_value_area_confluence_not_satisfied_when_node_outside_value_area():
    poc = _level("poc", price=10100.0)
    hvn = _level("hvn", price=9950.0)
    vah = _level("vah", price=10200.0)
    val = _level("val", price=10000.0)  # node (9950) sits below VAL

    result = SETUP.evaluate(_snapshot(levels=[poc, hvn, vah, val], current_price=9960.0))

    confluence = next(c for c in result.additional_evidence if c.name == "value_area_confluence")
    assert confluence.satisfied is False


def test_value_area_confluence_not_satisfied_when_vah_val_missing():
    poc = _level("poc", price=10100.0)
    hvn = _level("hvn", price=9950.0)

    result = SETUP.evaluate(_snapshot(levels=[poc, hvn], current_price=9960.0))

    confluence = next(c for c in result.additional_evidence if c.name == "value_area_confluence")
    assert confluence.satisfied is False


def test_both_additional_conditions_can_agree_simultaneously():
    poc = _level("poc", price=10100.0)
    hvn = _level("hvn", price=9950.0, raw_extra={"width": 2})
    vah = _level("vah", price=10200.0)
    val = _level("val", price=9900.0)

    result = SETUP.evaluate(_snapshot(levels=[poc, hvn, vah, val], current_price=9960.0))

    assert result.fired is True
    assert result.evidence_count == 2


# =========================================================
# Reasoning chain
# =========================================================


def test_reasoning_explains_the_failure_when_not_fired():
    result = SETUP.evaluate(_snapshot(levels=[]))

    assert "no high volume node" in result.reasoning.lower()


def test_reasoning_explains_a_fired_setup():
    poc = _level("poc", price=10100.0)
    hvn = _level("hvn", price=9950.0)

    result = SETUP.evaluate(_snapshot(levels=[poc, hvn], current_price=9960.0))

    assert result.fired is True
    assert "LONG" in result.reasoning
    assert "volume node reversal" in result.reasoning.lower()


def test_result_is_deterministic():
    poc = _level("poc", price=10100.0)
    hvn = _level("hvn", price=9950.0)
    snapshot = _snapshot(levels=[poc, hvn], current_price=9960.0)

    result_a = SETUP.evaluate(snapshot)
    result_b = SETUP.evaluate(snapshot)

    assert result_a == result_b
