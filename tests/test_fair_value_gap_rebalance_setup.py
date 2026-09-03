from datetime import datetime, timedelta, timezone

import pytest

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot, Zone
from strategy.setups.fair_value_gap_rebalance import FairValueGapRebalanceSetup

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
SETUP = FairValueGapRebalanceSetup()


def _zone(
    kind="fvg",
    direction="bullish",
    zone_relative_position="inside_price",
    status="active",
    resolution_detail="partially_filled",
    zone_high=105.0,
    zone_low=100.0,
    resolution_pct=0.3,
):
    return Zone(
        kind=kind, direction=direction, zone_relative_position=zone_relative_position,
        zone_high=zone_high, zone_low=zone_low, status=status,
        resolution_detail=resolution_detail, resolution_pct=resolution_pct, touch_count=None,
        distance_from_price=0.0, created_at=START - timedelta(hours=1),
        resolved_at=None, source_module="fair_value_gap", raw={},
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
    assert result.required_conditions[0].name == "price_rebalancing_unfilled_gap"


def test_does_not_fire_when_price_not_inside_the_gap():
    zone = _zone(zone_relative_position="below_price")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is False


def test_does_not_fire_when_gap_still_fully_active_unfilled():
    # Defensive - "active" fill_status with price already inside should
    # not occur in practice, but the condition must not accept it.
    zone = _zone(resolution_detail="active")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is False


def test_does_not_fire_when_gap_completely_filled():
    zone = _zone(status="resolved", resolution_detail="completely_filled")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is False


def test_ignores_non_fvg_zones():
    order_block_zone = _zone(kind="order_block")

    result = SETUP.evaluate(_snapshot(zones=[order_block_zone]))

    assert result.fired is False


# =========================================================
# Fires - direction inference
# =========================================================


def test_bullish_fvg_rebalance_fires_long():
    zone = _zone(direction="bullish")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is True
    assert result.direction == "LONG"
    assert result.setup_name == "fair_value_gap_rebalance"


def test_bearish_fvg_rebalance_fires_short():
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
# Additional evidence
# =========================================================


def test_fvg_confluence_satisfied_when_overlapping_same_direction_gap_exists():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    overlapping = _zone(direction="bullish", zone_high=103.0, zone_low=98.0)

    result = SETUP.evaluate(_snapshot(zones=[primary, overlapping]))

    confluence = next(c for c in result.additional_evidence if c.name == "fvg_confluence")
    assert confluence.satisfied is True
    assert result.evidence_count >= 1


def test_fvg_confluence_not_satisfied_when_other_gap_is_opposite_direction():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    opposite = _zone(direction="bearish", zone_high=103.0, zone_low=98.0)

    result = SETUP.evaluate(_snapshot(zones=[primary, opposite]))

    confluence = next(c for c in result.additional_evidence if c.name == "fvg_confluence")
    assert confluence.satisfied is False


def test_fvg_confluence_not_satisfied_when_other_gap_does_not_overlap():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    far_away = _zone(direction="bullish", zone_high=50.0, zone_low=40.0, zone_relative_position="below_price")

    result = SETUP.evaluate(_snapshot(zones=[primary, far_away]))

    confluence = next(c for c in result.additional_evidence if c.name == "fvg_confluence")
    assert confluence.satisfied is False


def test_overlaps_order_block_zone_satisfied_when_same_direction_ob_overlaps():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    order_block = _zone(kind="order_block", direction="bullish", zone_high=103.0, zone_low=98.0)

    result = SETUP.evaluate(_snapshot(zones=[primary, order_block]))

    ob_confluence = next(c for c in result.additional_evidence if c.name == "overlaps_order_block_zone")
    assert ob_confluence.satisfied is True
    assert result.evidence_count >= 1


def test_overlaps_order_block_zone_not_satisfied_when_ob_is_opposite_direction():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    order_block = _zone(kind="order_block", direction="bearish", zone_high=103.0, zone_low=98.0)

    result = SETUP.evaluate(_snapshot(zones=[primary, order_block]))

    ob_confluence = next(c for c in result.additional_evidence if c.name == "overlaps_order_block_zone")
    assert ob_confluence.satisfied is False


def test_overlaps_order_block_zone_not_satisfied_when_ob_is_resolved():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    order_block = _zone(kind="order_block", direction="bullish", zone_high=103.0, zone_low=98.0, status="resolved")

    result = SETUP.evaluate(_snapshot(zones=[primary, order_block]))

    ob_confluence = next(c for c in result.additional_evidence if c.name == "overlaps_order_block_zone")
    assert ob_confluence.satisfied is False


def test_both_additional_conditions_can_agree_simultaneously():
    primary = _zone(direction="bullish", zone_high=105.0, zone_low=100.0)
    overlapping_fvg = _zone(direction="bullish", zone_high=103.0, zone_low=98.0)
    overlapping_ob = _zone(kind="order_block", direction="bullish", zone_high=103.0, zone_low=98.0)

    result = SETUP.evaluate(_snapshot(zones=[primary, overlapping_fvg, overlapping_ob]))

    assert result.fired is True
    assert result.evidence_count == 2


# =========================================================
# Reasoning chain
# =========================================================


def test_reasoning_explains_the_failure_when_not_fired():
    result = SETUP.evaluate(_snapshot(zones=[]))

    assert "no partially-filled fair value gap" in result.reasoning.lower()


def test_reasoning_explains_a_fired_setup():
    zone = _zone(direction="bullish")

    result = SETUP.evaluate(_snapshot(zones=[zone]))

    assert result.fired is True
    assert "LONG" in result.reasoning
    assert "fair value gap rebalance" in result.reasoning.lower()


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
