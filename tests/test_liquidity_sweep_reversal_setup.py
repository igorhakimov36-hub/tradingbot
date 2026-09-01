from datetime import datetime, timedelta, timezone

import pytest

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot, Zone
from strategy.setups.liquidity_sweep_reversal import LiquiditySweepReversalSetup

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
SETUP = LiquiditySweepReversalSetup()


def _zone(
    kind="liquidity_pool",
    direction="buy_side",
    status="resolved",
    resolution_detail="swept",
    resolved_at=START,
    zone_high=105.0,
    zone_low=100.0,
    raw_extra=None,
):
    raw = {"sources": ["equal_highs"]}
    if raw_extra:
        raw.update(raw_extra)

    return Zone(
        kind=kind, direction=direction, zone_relative_position="above_price",
        zone_high=zone_high, zone_low=zone_low, status=status,
        resolution_detail=resolution_detail, resolution_pct=None, touch_count=2,
        distance_from_price=5.0, created_at=START - timedelta(hours=1),
        resolved_at=resolved_at, source_module="liquidity_pool", raw=raw,
    )


def _snapshot(
    zones=None,
    structure=None,
    cvd=None,
    intermarket=None,
    timestamp=START,
):
    return MarketIntelligenceSnapshot(
        symbol="BTCUSDT", timeframe="15m", timestamp=timestamp, current_price=100.0,
        structure=structure or {"choch": "NO_CHOCH"},
        zones=zones or [], levels=[],
        order_flow={"delta": {}, "cvd": cvd or {}},
        sessions={"active_now": [], "previous_period_high_low": {}},
        intermarket=intermarket or {}, volume_profile={}, data_quality={},
    )


# =========================================================
# No fire - required conditions
# =========================================================


def test_does_not_fire_when_no_pool_swept():
    result = SETUP.evaluate(_snapshot(zones=[]))

    assert result.fired is False
    assert result.direction is None
    assert result.required_conditions[0].satisfied is False
    assert result.required_conditions[0].name == "liquidity_pool_swept_this_bar"


def test_does_not_fire_when_sweep_happened_on_an_earlier_bar():
    stale_zone = _zone(resolved_at=START - timedelta(minutes=15))  # not THIS bar

    result = SETUP.evaluate(_snapshot(zones=[stale_zone], timestamp=START))

    assert result.fired is False


def test_does_not_fire_when_pool_still_active_not_swept():
    active_zone = _zone(status="active", resolution_detail="unswept", resolved_at=None)

    result = SETUP.evaluate(_snapshot(zones=[active_zone]))

    assert result.fired is False


def test_does_not_fire_when_sweep_present_but_no_cvd_confirmation():
    swept = _zone(direction="buy_side", resolved_at=START)

    result = SETUP.evaluate(_snapshot(zones=[swept], cvd={"daily": {"cvd_exhaustion_flag": "none"}}))

    assert result.fired is False
    assert result.required_conditions[0].satisfied is True  # sweep condition alone satisfied
    assert result.required_conditions[1].satisfied is False  # cvd condition not satisfied


def test_ignores_non_liquidity_pool_zones():
    fvg_zone = _zone(kind="fvg", resolved_at=START)  # a resolved FVG, not a liquidity pool

    result = SETUP.evaluate(_snapshot(zones=[fvg_zone]))

    assert result.fired is False


# =========================================================
# Fires - direction inference
# =========================================================


def test_buy_side_sweep_with_bearish_exhaustion_fires_short():
    swept = _zone(direction="buy_side", resolved_at=START)
    cvd = {"daily": {"cvd_exhaustion_flag": "bearish_exhaustion", "price_cvd_divergence_flag": "none"}}

    result = SETUP.evaluate(_snapshot(zones=[swept], cvd=cvd))

    assert result.fired is True
    assert result.direction == "SHORT"
    assert result.setup_name == "liquidity_sweep_reversal"


def test_sell_side_sweep_with_bullish_divergence_fires_long():
    swept = _zone(direction="sell_side", resolved_at=START)
    cvd = {"continuous": {"cvd_exhaustion_flag": "none", "price_cvd_divergence_flag": "bullish_divergence"}}

    result = SETUP.evaluate(_snapshot(zones=[swept], cvd=cvd))

    assert result.fired is True
    assert result.direction == "LONG"


def test_wrong_direction_cvd_flag_does_not_confirm():
    swept = _zone(direction="buy_side", resolved_at=START)  # implies SHORT
    cvd = {"daily": {"cvd_exhaustion_flag": "bullish_exhaustion"}}  # wrong direction

    result = SETUP.evaluate(_snapshot(zones=[swept], cvd=cvd))

    assert result.fired is False


# =========================================================
# Additional evidence - recorded, never gates firing
# =========================================================


def test_additional_evidence_counted_but_not_required():
    swept = _zone(direction="buy_side", resolved_at=START, raw_extra={"sources": ["equal_highs"]})  # single source
    cvd = {"daily": {"cvd_exhaustion_flag": "bearish_exhaustion"}}
    structure = {"choch": "NO_CHOCH"}  # does not confirm

    result = SETUP.evaluate(_snapshot(zones=[swept], cvd=cvd, structure=structure))

    assert result.fired is True  # still fires - additional evidence is not required
    assert result.evidence_count == 0  # none of the 3 additional conditions satisfied
    assert len(result.additional_evidence) == 3


def test_choch_confirmation_increases_evidence_count():
    swept = _zone(direction="buy_side", resolved_at=START)
    cvd = {"daily": {"cvd_exhaustion_flag": "bearish_exhaustion"}}
    structure = {"choch": "BEARISH_CHOCH"}  # confirms SHORT

    result = SETUP.evaluate(_snapshot(zones=[swept], cvd=cvd, structure=structure))

    assert result.fired is True
    assert result.evidence_count == 1
    choch_condition = next(c for c in result.additional_evidence if c.name == "choch_confirms_direction")
    assert choch_condition.satisfied is True


def test_multi_source_pool_counts_as_evidence():
    swept = _zone(direction="buy_side", resolved_at=START, raw_extra={"sources": ["equal_highs", "session_high"]})
    cvd = {"daily": {"cvd_exhaustion_flag": "bearish_exhaustion"}}

    result = SETUP.evaluate(_snapshot(zones=[swept], cvd=cvd))

    multi_source = next(c for c in result.additional_evidence if c.name == "pool_has_multiple_sources")
    assert multi_source.satisfied is True
    assert result.evidence_count == 1


def test_smt_confirmation_counts_as_evidence():
    swept = _zone(direction="sell_side", resolved_at=START)  # implies LONG
    cvd = {"daily": {"price_cvd_divergence_flag": "bullish_divergence"}}
    intermarket = {"btc_eth": {"structural_divergence_flag": "bullish_divergence"}}

    result = SETUP.evaluate(_snapshot(zones=[swept], cvd=cvd, intermarket=intermarket))

    smt_condition = next(c for c in result.additional_evidence if c.name == "smt_confirms_direction")
    assert smt_condition.satisfied is True
    assert result.evidence_count == 1


def test_all_three_additional_conditions_can_agree_simultaneously():
    swept = _zone(direction="buy_side", resolved_at=START, raw_extra={"sources": ["equal_highs", "round_number"]})
    cvd = {"daily": {"cvd_exhaustion_flag": "bearish_exhaustion"}}
    structure = {"choch": "BEARISH_CHOCH"}
    intermarket = {"btc_eth": {"structural_divergence_flag": "bearish_divergence"}}

    result = SETUP.evaluate(_snapshot(zones=[swept], cvd=cvd, structure=structure, intermarket=intermarket))

    assert result.fired is True
    assert result.evidence_count == 3


# =========================================================
# Reasoning chain
# =========================================================


def test_reasoning_present_and_explains_the_failure_when_not_fired():
    result = SETUP.evaluate(_snapshot(zones=[]))

    assert "no liquidity pool sweep" in result.reasoning.lower()


def test_reasoning_names_the_failed_condition_when_sweep_present_but_cvd_missing():
    swept = _zone(direction="buy_side", resolved_at=START)

    result = SETUP.evaluate(_snapshot(zones=[swept], cvd={}))

    assert "cvd_confirms_reversal" in result.reasoning


def test_reasoning_explains_a_fired_setup():
    swept = _zone(direction="buy_side", resolved_at=START)
    cvd = {"daily": {"cvd_exhaustion_flag": "bearish_exhaustion"}}

    result = SETUP.evaluate(_snapshot(zones=[swept], cvd=cvd))

    assert "SHORT" in result.reasoning
    assert "liquidity sweep reversal" in result.reasoning.lower()


def test_evidence_preserved_for_stop_loss_placement():
    # trade_setup_callback (Step 5) reads the sweep condition's raw
    # zone_high/zone_low directly - this must survive intact.
    swept = _zone(direction="buy_side", resolved_at=START, zone_high=205.0, zone_low=200.0)
    cvd = {"daily": {"cvd_exhaustion_flag": "bearish_exhaustion"}}

    result = SETUP.evaluate(_snapshot(zones=[swept], cvd=cvd))

    evidence = result.required_conditions[0].evidence
    assert evidence["zone_high"] == 205.0
    assert evidence["zone_low"] == 200.0


def test_result_is_deterministic():
    swept = _zone(direction="buy_side", resolved_at=START)
    cvd = {"daily": {"cvd_exhaustion_flag": "bearish_exhaustion"}}
    snapshot = _snapshot(zones=[swept], cvd=cvd)

    result_a = SETUP.evaluate(snapshot)
    result_b = SETUP.evaluate(snapshot)

    assert result_a == result_b
