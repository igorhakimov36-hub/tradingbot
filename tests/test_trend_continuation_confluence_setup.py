from datetime import datetime, timedelta, timezone

from strategy.market_intelligence_snapshot import Level, MarketIntelligenceSnapshot, Zone
from strategy.setups.trend_continuation_confluence import TrendContinuationConfluenceSetup

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
SETUP = TrendContinuationConfluenceSetup()


def _pool(direction="buy_side", zone_relative_position="inside_price", status="active", zone_high=105.0, zone_low=100.0, sources=None):
    return Zone(
        kind="liquidity_pool", direction=direction, zone_relative_position=zone_relative_position,
        zone_high=zone_high, zone_low=zone_low, status=status,
        resolution_detail="unswept" if status == "active" else "swept",
        resolution_pct=None, touch_count=2,
        distance_from_price=0.0, created_at=START - timedelta(hours=2),
        resolved_at=None, source_module="liquidity_pool", raw={"sources": sources or ["equal_highs"]},
    )


def _other_zone(kind="order_block", direction="buy_side", zone_relative_position="inside_price", zone_high=105.0, zone_low=100.0):
    return Zone(
        kind=kind, direction=direction, zone_relative_position=zone_relative_position,
        zone_high=zone_high, zone_low=zone_low, status="active",
        resolution_detail="unmitigated", resolution_pct=0.0, touch_count=1,
        distance_from_price=0.0, created_at=START - timedelta(hours=1),
        resolved_at=None, source_module="order_block", raw={},
    )


def _level(kind, price):
    return Level(kind=kind, price=price, distance_from_price=None, swept=None, source_module="volume_profile", raw={})


def _snapshot(bos="NO_BOS", zones=None, levels=None, cvd=None, current_price=102.0, timestamp=START):
    return MarketIntelligenceSnapshot(
        symbol="BTCUSDT", timeframe="15m", timestamp=timestamp, current_price=current_price,
        structure={"bos": bos}, zones=zones or [], levels=levels or [],
        order_flow={"delta": {}, "cvd": cvd or {}},
        sessions={"active_now": [], "previous_period_high_low": {}},
        intermarket={}, volume_profile={}, data_quality={},
    )


# =========================================================
# No fire - required conditions
# =========================================================


def test_does_not_fire_with_no_structure_and_no_zones():
    result = SETUP.evaluate(_snapshot())

    assert result.fired is False
    assert result.direction is None
    assert result.required_conditions[0].name == "price_inside_active_liquidity_pool"
    assert result.required_conditions[1].name == "structural_trend_confirmed"


def test_does_not_fire_on_no_bos_even_with_a_qualifying_pool():
    pool = _pool(direction="buy_side")

    result = SETUP.evaluate(_snapshot(bos="NO_BOS", zones=[pool]))

    assert result.fired is False


def test_does_not_fire_on_bullish_bos_with_no_zones():
    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[]))

    assert result.fired is False
    assert result.required_conditions[1].satisfied is True
    assert result.required_conditions[0].satisfied is False


def test_does_not_fire_when_pool_is_wrong_side_for_trend():
    sell_side_pool = _pool(direction="sell_side")

    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[sell_side_pool]))

    assert result.fired is False


def test_does_not_fire_when_pool_not_inside_price():
    pool = _pool(direction="buy_side", zone_relative_position="below_price")

    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[pool]))

    assert result.fired is False


def test_does_not_fire_when_pool_already_swept():
    pool = _pool(direction="buy_side", status="swept")

    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[pool]))

    assert result.fired is False


def test_ignores_non_liquidity_pool_zones():
    order_block = _other_zone(kind="order_block", direction="buy_side")

    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[order_block]))

    assert result.fired is False


# =========================================================
# Fires - direction inference
# =========================================================


def test_bullish_bos_with_buy_side_pool_fires_long():
    pool = _pool(direction="buy_side")

    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[pool]))

    assert result.fired is True
    assert result.direction == "LONG"
    assert result.setup_name == "trend_continuation_confluence"


def test_bearish_bos_with_sell_side_pool_fires_short():
    pool = _pool(direction="sell_side")

    result = SETUP.evaluate(_snapshot(bos="BEARISH_BOS", zones=[pool]))

    assert result.fired is True
    assert result.direction == "SHORT"


def test_fires_even_with_zero_additional_evidence():
    pool = _pool(direction="buy_side")

    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[pool]))

    assert result.fired is True
    assert result.evidence_count == 0


def test_first_candidate_wins_when_multiple_qualify_on_same_bar():
    first = _pool(direction="buy_side", zone_high=105.0, zone_low=100.0)
    second = _pool(direction="buy_side", zone_high=205.0, zone_low=200.0)

    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[first, second]))

    assert result.required_conditions[0].evidence["zone_low"] == 100.0


# =========================================================
# Additional evidence - value_area_confluence
# =========================================================


def test_value_area_confluence_satisfied_when_pool_overlaps_value_area():
    pool = _pool(direction="buy_side", zone_high=105.0, zone_low=100.0)
    levels = [_level("val", 98.0), _level("vah", 103.0)]

    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[pool], levels=levels))

    va = next(c for c in result.additional_evidence if c.name == "value_area_confluence")
    assert va.satisfied is True
    assert result.evidence_count >= 1


def test_value_area_confluence_not_satisfied_when_pool_does_not_overlap():
    pool = _pool(direction="buy_side", zone_high=105.0, zone_low=100.0)
    levels = [_level("val", 10.0), _level("vah", 20.0)]

    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[pool], levels=levels))

    va = next(c for c in result.additional_evidence if c.name == "value_area_confluence")
    assert va.satisfied is False


def test_value_area_confluence_not_satisfied_when_no_value_area_present():
    pool = _pool(direction="buy_side")

    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[pool], levels=[]))

    va = next(c for c in result.additional_evidence if c.name == "value_area_confluence")
    assert va.satisfied is False


# =========================================================
# Additional evidence - cvd_confirms_trend
# =========================================================


def test_cvd_confirms_trend_satisfied_when_matching_anchor_bullish():
    pool = _pool(direction="buy_side")
    cvd = {"continuous": {"cvd_direction": "BULLISH"}}

    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[pool], cvd=cvd))

    confirm = next(c for c in result.additional_evidence if c.name == "cvd_confirms_trend")
    assert confirm.satisfied is True
    assert result.evidence_count >= 1


def test_cvd_confirms_trend_not_satisfied_when_anchor_disagrees():
    pool = _pool(direction="sell_side")
    cvd = {"continuous": {"cvd_direction": "BULLISH"}}

    result = SETUP.evaluate(_snapshot(bos="BEARISH_BOS", zones=[pool], cvd=cvd))

    confirm = next(c for c in result.additional_evidence if c.name == "cvd_confirms_trend")
    assert confirm.satisfied is False


def test_cvd_confirms_trend_not_satisfied_when_no_anchors_configured():
    pool = _pool(direction="buy_side")

    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[pool], cvd={}))

    confirm = next(c for c in result.additional_evidence if c.name == "cvd_confirms_trend")
    assert confirm.satisfied is False


def test_both_additional_conditions_can_agree_simultaneously():
    pool = _pool(direction="buy_side", zone_high=105.0, zone_low=100.0)
    levels = [_level("val", 98.0), _level("vah", 103.0)]
    cvd = {"continuous": {"cvd_direction": "BULLISH"}}

    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[pool], levels=levels, cvd=cvd))

    assert result.fired is True
    assert result.evidence_count == 2


# =========================================================
# Reasoning chain
# =========================================================


def test_reasoning_explains_the_failure_when_not_fired():
    result = SETUP.evaluate(_snapshot())

    assert "no qualifying liquidity pool retest" in result.reasoning.lower()


def test_reasoning_explains_a_fired_setup():
    pool = _pool(direction="buy_side")

    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[pool]))

    assert result.fired is True
    assert "LONG" in result.reasoning
    assert "trend continuation confluence" in result.reasoning.lower()


def test_evidence_preserved_for_stop_loss_placement():
    pool = _pool(direction="buy_side", zone_high=205.0, zone_low=200.0)

    result = SETUP.evaluate(_snapshot(bos="BULLISH_BOS", zones=[pool]))

    evidence = result.required_conditions[0].evidence
    assert evidence["zone_high"] == 205.0
    assert evidence["zone_low"] == 200.0


def test_result_is_deterministic():
    pool = _pool(direction="buy_side")
    snapshot = _snapshot(bos="BULLISH_BOS", zones=[pool])

    result_a = SETUP.evaluate(snapshot)
    result_b = SETUP.evaluate(snapshot)

    assert result_a == result_b
