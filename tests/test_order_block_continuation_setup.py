from datetime import datetime, timedelta, timezone

import pytest

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot, Zone
from strategy.setups.order_block_continuation import OrderBlockContinuationSetup

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
SETUP = OrderBlockContinuationSetup()


def _zone(
    kind="order_block",
    direction="bullish",
    zone_relative_position="inside_price",
    status="active",
    zone_high=105.0,
    zone_low=100.0,
    touch_count=1,
    raw_extra=None,
):
    raw = {"mitigation_zone_high": 103.0, "mitigation_zone_low": 101.0}
    if raw_extra is not None:
        raw = raw_extra

    return Zone(
        kind=kind, direction=direction, zone_relative_position=zone_relative_position,
        zone_high=zone_high, zone_low=zone_low, status=status,
        resolution_detail="unmitigated" if status == "active" else "fully_mitigated",
        resolution_pct=0.0, touch_count=touch_count,
        distance_from_price=0.0, created_at=START - timedelta(hours=1),
        resolved_at=None, source_module="order_block", raw=raw,
    )


def _snapshot(zones=None, current_price=102.0, timestamp=START):
    return MarketIntelligenceSnapshot(
        symbol="BTCUSDT", timeframe="15m", timestamp=timestamp, current_price=current_price,
        structure={"choch": "NO_CHOCH"},
        zones=zones or [], levels=[],
        order_flow={"delta": {}, "cvd": {}},
        sessions={"active_now": [], "previous_period_high_low": {}},
        intermarket={}, volume_profile={}, data_quality={},
    )


# =========================================================
# No fire - required condition
# =========================================================


def test_does_not_fire_with_no_zones():
    result = SETUP.evaluate(_snapshot(zones=[]))

    assert result.fired is False
    assert result.direction is None
    assert result.required_conditions[0].name == "active_order_block_first_touch"
    assert result.required_conditions[0].satisfied is False


def test_does_not_fire_when_price_not_inside_the_zone():
    zone = _zone(zone_relative_position="below_price")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is False


def test_does_not_fire_on_second_touch():
    zone = _zone(touch_count=2)

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is False


def test_does_not_fire_on_zero_touches_even_if_inside_price():
    # Defensive - touch_count should never be 0 while inside_price in
    # practice, but the condition must not silently accept it either.
    zone = _zone(touch_count=0)

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is False


def test_does_not_fire_on_a_resolved_mitigated_block():
    zone = _zone(status="resolved")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is False


def test_ignores_non_order_block_zones():
    liquidity_pool_zone = _zone(kind="liquidity_pool")

    result = SETUP.evaluate(_snapshot(zones=[liquidity_pool_zone]))

    assert result.fired is False


# =========================================================
# Fires - direction inference
# =========================================================


def test_bullish_order_block_first_touch_fires_long():
    zone = _zone(direction="bullish")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is True
    assert result.direction == "LONG"
    assert result.setup_name == "order_block_continuation"


def test_bearish_order_block_first_touch_fires_short():
    zone = _zone(direction="bearish")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is True
    assert result.direction == "SHORT"


def test_fires_even_with_zero_additional_evidence():
    # Unlike Liquidity Sweep Reversal's current permanent rule, this
    # setup does not (yet) require any additional confirmation.
    zone = _zone(raw_extra={"mitigation_zone_high": None, "mitigation_zone_low": None})

    result = SETUP.evaluate(_snapshot(zones=[zone], current_price=999.0))

    assert result.fired is True
    assert result.evidence_count == 0


def test_first_candidate_wins_when_multiple_qualify_on_same_bar():
    first = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    second = _zone(direction="bearish", zone_high=205.0, zone_low=200.0)

    result = SETUP.evaluate(_snapshot(zones=[first, second]))

    assert result.direction == "LONG"  # the first zone in the list, deterministically


# =========================================================
# Additional evidence
# =========================================================


def test_body_zone_confirmation_satisfied_when_price_inside_body():
    zone = _zone(raw_extra={"mitigation_zone_high": 103.0, "mitigation_zone_low": 101.0})

    result = SETUP.evaluate(_snapshot(zones=[zone], current_price=102.0))

    body_condition = next(c for c in result.additional_evidence if c.name == "body_zone_confirms_precision")
    assert body_condition.satisfied is True
    assert result.evidence_count >= 1


def test_body_zone_confirmation_not_satisfied_when_price_outside_body_but_inside_wick():
    zone = _zone(raw_extra={"mitigation_zone_high": 103.0, "mitigation_zone_low": 101.0})

    result = SETUP.evaluate(_snapshot(zones=[zone], current_price=104.5))  # inside [100,105] wick, outside [101,103] body

    body_condition = next(c for c in result.additional_evidence if c.name == "body_zone_confirms_precision")
    assert body_condition.satisfied is False


def test_body_zone_confirmation_handles_missing_mitigation_fields_gracefully():
    zone = _zone(raw_extra={})  # no mitigation_zone_high/low keys at all

    result = SETUP.evaluate(_snapshot(zones=[zone], current_price=102.0))

    body_condition = next(c for c in result.additional_evidence if c.name == "body_zone_confirms_precision")
    assert body_condition.satisfied is False


def test_confluence_satisfied_when_overlapping_same_direction_block_exists():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    overlapping = _zone(direction="bullish", zone_high=103.0, zone_low=98.0)

    result = SETUP.evaluate(_snapshot(zones=[primary, overlapping]))

    confluence = next(c for c in result.additional_evidence if c.name == "order_block_confluence")
    assert confluence.satisfied is True
    assert result.evidence_count >= 1


def test_confluence_not_satisfied_when_other_block_is_opposite_direction():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    opposite = _zone(direction="bearish", zone_high=103.0, zone_low=98.0, touch_count=1)

    result = SETUP.evaluate(_snapshot(zones=[primary, opposite]))

    confluence = next(c for c in result.additional_evidence if c.name == "order_block_confluence")
    assert confluence.satisfied is False


def test_confluence_not_satisfied_when_other_block_does_not_overlap_range():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    far_away = _zone(direction="bullish", zone_high=50.0, zone_low=40.0, zone_relative_position="below_price")

    result = SETUP.evaluate(_snapshot(zones=[primary, far_away]))

    confluence = next(c for c in result.additional_evidence if c.name == "order_block_confluence")
    assert confluence.satisfied is False


def test_confluence_not_satisfied_when_other_block_is_resolved():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    resolved = _zone(direction="bullish", zone_high=103.0, zone_low=98.0, status="resolved")

    result = SETUP.evaluate(_snapshot(zones=[primary, resolved]))

    confluence = next(c for c in result.additional_evidence if c.name == "order_block_confluence")
    assert confluence.satisfied is False


def test_both_additional_conditions_can_agree_simultaneously():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0,
                     raw_extra={"mitigation_zone_high": 103.0, "mitigation_zone_low": 101.0})
    overlapping = _zone(direction="bullish", zone_high=103.0, zone_low=98.0)

    result = SETUP.evaluate(_snapshot(zones=[primary, overlapping], current_price=102.0))

    assert result.fired is True
    assert result.evidence_count == 2


# =========================================================
# Reasoning chain
# =========================================================


def test_reasoning_explains_the_failure_when_not_fired():
    result = SETUP.evaluate(_snapshot(zones=[]))

    assert "no first-touch active order block" in result.reasoning.lower()


def test_reasoning_explains_a_fired_setup():
    zone = _zone(direction="bullish")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is True
    assert "LONG" in result.reasoning
    assert "order block continuation" in result.reasoning.lower()


def test_evidence_preserved_for_stop_loss_placement():
    # trade_setup_callback reads required_conditions[0].evidence's
    # zone_high/zone_low directly - must survive intact, matching the
    # exact same access pattern Liquidity Sweep Reversal relies on.
    zone = _zone(direction="bullish", zone_high=205.0, zone_low=200.0)

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    evidence = result.required_conditions[0].evidence
    assert evidence["zone_high"] == 205.0
    assert evidence["zone_low"] == 200.0


def test_result_is_deterministic():
    zone = _zone(direction="bullish")
    snapshot = _snapshot(zones=[zone])

    result_a = SETUP.evaluate(snapshot)
    result_b = SETUP.evaluate(snapshot)

    assert result_a == result_b
