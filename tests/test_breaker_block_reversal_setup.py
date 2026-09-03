from datetime import datetime, timedelta, timezone

import pytest

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot, Zone
from strategy.setups.breaker_block_reversal import BreakerBlockReversalSetup

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
SETUP = BreakerBlockReversalSetup()


def _zone(
    kind="breaker_block",
    direction="bullish",
    zone_relative_position="inside_price",
    status="active",
    zone_high=105.0,
    zone_low=100.0,
    touch_count=1,
    raw_extra=None,
):
    raw = {"source_direction": "bearish" if direction == "bullish" else "bullish"}
    if raw_extra is not None:
        raw = raw_extra

    return Zone(
        kind=kind, direction=direction, zone_relative_position=zone_relative_position,
        zone_high=zone_high, zone_low=zone_low, status=status,
        resolution_detail="unmitigated" if status == "active" else "fully_mitigated",
        resolution_pct=0.0, touch_count=touch_count,
        distance_from_price=0.0, created_at=START - timedelta(hours=1),
        resolved_at=None, source_module="breaker_block", raw=raw,
    )


def _pool(direction="sell_side", zone_high=103.0, zone_low=98.0, status="active"):
    return Zone(
        kind="liquidity_pool", direction=direction, zone_relative_position="inside_price",
        zone_high=zone_high, zone_low=zone_low, status=status,
        resolution_detail="unswept" if status == "active" else "swept",
        resolution_pct=None, touch_count=1,
        distance_from_price=0.0, created_at=START - timedelta(hours=2),
        resolved_at=None, source_module="liquidity_pool", raw={},
    )


def _snapshot(zones=None, current_price=102.0, timestamp=START):
    return MarketIntelligenceSnapshot(
        symbol="BTCUSDT", timeframe="15m", timestamp=timestamp, current_price=current_price,
        structure={}, zones=zones or [], levels=[],
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
    assert result.required_conditions[0].name == "active_breaker_block_first_touch"


def test_does_not_fire_when_price_not_inside_the_zone():
    zone = _zone(zone_relative_position="below_price")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is False


def test_does_not_fire_on_second_touch():
    zone = _zone(touch_count=2)

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is False


def test_does_not_fire_on_zero_touches_even_if_inside_price():
    zone = _zone(touch_count=0)

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is False


def test_does_not_fire_on_a_resolved_re_mitigated_breaker():
    zone = _zone(status="resolved")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is False


def test_ignores_non_breaker_block_zones():
    order_block_zone = _zone(kind="order_block")

    result = SETUP.evaluate(_snapshot(zones=[order_block_zone]))

    assert result.fired is False


# =========================================================
# Fires - direction inference (using the Breaker's OWN, already-flipped direction)
# =========================================================


def test_bullish_breaker_first_touch_fires_long():
    zone = _zone(direction="bullish")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is True
    assert result.direction == "LONG"
    assert result.setup_name == "breaker_block_reversal"


def test_bearish_breaker_first_touch_fires_short():
    zone = _zone(direction="bearish")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is True
    assert result.direction == "SHORT"


def test_fires_even_with_zero_additional_evidence():
    zone = _zone(direction="bullish")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is True
    assert result.evidence_count == 0


def test_first_candidate_wins_when_multiple_qualify_on_same_bar():
    first = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    second = _zone(direction="bearish", zone_high=205.0, zone_low=200.0)

    result = SETUP.evaluate(_snapshot(zones=[first, second]))

    assert result.direction == "LONG"


# =========================================================
# Additional evidence - breaker_block_confluence
# =========================================================


def test_breaker_confluence_satisfied_when_overlapping_same_direction_breaker_exists():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    overlapping = _zone(direction="bullish", zone_high=103.0, zone_low=98.0)

    result = SETUP.evaluate(_snapshot(zones=[primary, overlapping]))

    confluence = next(c for c in result.additional_evidence if c.name == "breaker_block_confluence")
    assert confluence.satisfied is True
    assert result.evidence_count >= 1


def test_breaker_confluence_not_satisfied_when_other_breaker_is_opposite_direction():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    opposite = _zone(direction="bearish", zone_high=103.0, zone_low=98.0, touch_count=1)

    result = SETUP.evaluate(_snapshot(zones=[primary, opposite]))

    confluence = next(c for c in result.additional_evidence if c.name == "breaker_block_confluence")
    assert confluence.satisfied is False


def test_breaker_confluence_not_satisfied_when_other_breaker_does_not_overlap():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    far_away = _zone(direction="bullish", zone_high=50.0, zone_low=40.0, zone_relative_position="below_price")

    result = SETUP.evaluate(_snapshot(zones=[primary, far_away]))

    confluence = next(c for c in result.additional_evidence if c.name == "breaker_block_confluence")
    assert confluence.satisfied is False


def test_breaker_confluence_not_satisfied_when_other_breaker_is_resolved():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    resolved = _zone(direction="bullish", zone_high=103.0, zone_low=98.0, status="resolved")

    result = SETUP.evaluate(_snapshot(zones=[primary, resolved]))

    confluence = next(c for c in result.additional_evidence if c.name == "breaker_block_confluence")
    assert confluence.satisfied is False


# =========================================================
# Additional evidence - overlaps_liquidity_pool (directional mapping)
# =========================================================


def test_bullish_breaker_confirmed_by_overlapping_sell_side_pool():
    breaker = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    pool = _pool(direction="sell_side", zone_high=103.0, zone_low=98.0)

    result = SETUP.evaluate(_snapshot(zones=[breaker, pool]))

    pool_confluence = next(c for c in result.additional_evidence if c.name == "overlaps_liquidity_pool")
    assert pool_confluence.satisfied is True
    assert result.evidence_count >= 1


def test_bearish_breaker_confirmed_by_overlapping_buy_side_pool():
    breaker = _zone(direction="bearish", zone_high=105.0, zone_low=100.0)
    pool = _pool(direction="buy_side", zone_high=107.0, zone_low=103.0)

    result = SETUP.evaluate(_snapshot(zones=[breaker, pool]))

    pool_confluence = next(c for c in result.additional_evidence if c.name == "overlaps_liquidity_pool")
    assert pool_confluence.satisfied is True


def test_bullish_breaker_not_confirmed_by_wrong_side_pool():
    # A buy-side pool (resistance-associated) does not corroborate a
    # bullish (support) breaker, even if it overlaps in price.
    breaker = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    pool = _pool(direction="buy_side", zone_high=103.0, zone_low=98.0)

    result = SETUP.evaluate(_snapshot(zones=[breaker, pool]))

    pool_confluence = next(c for c in result.additional_evidence if c.name == "overlaps_liquidity_pool")
    assert pool_confluence.satisfied is False


def test_overlaps_liquidity_pool_not_satisfied_when_no_pool_present():
    breaker = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)

    result = SETUP.evaluate(_snapshot(zones=[breaker]))

    pool_confluence = next(c for c in result.additional_evidence if c.name == "overlaps_liquidity_pool")
    assert pool_confluence.satisfied is False


def test_overlaps_liquidity_pool_not_satisfied_when_pool_does_not_overlap_range():
    breaker = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    pool = _pool(direction="sell_side", zone_high=50.0, zone_low=40.0)

    result = SETUP.evaluate(_snapshot(zones=[breaker, pool]))

    pool_confluence = next(c for c in result.additional_evidence if c.name == "overlaps_liquidity_pool")
    assert pool_confluence.satisfied is False


def test_both_additional_conditions_can_agree_simultaneously():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    overlapping_breaker = _zone(direction="bullish", zone_high=103.0, zone_low=98.0)
    pool = _pool(direction="sell_side", zone_high=103.0, zone_low=98.0)

    result = SETUP.evaluate(_snapshot(zones=[primary, overlapping_breaker, pool]))

    assert result.fired is True
    assert result.evidence_count == 2


# =========================================================
# Reasoning chain
# =========================================================


def test_reasoning_explains_the_failure_when_not_fired():
    result = SETUP.evaluate(_snapshot(zones=[]))

    assert "no first-touch active breaker block" in result.reasoning.lower()


def test_reasoning_explains_a_fired_setup():
    zone = _zone(direction="bullish")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is True
    assert "LONG" in result.reasoning
    assert "breaker block reversal" in result.reasoning.lower()


def test_evidence_preserved_for_stop_loss_placement():
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
