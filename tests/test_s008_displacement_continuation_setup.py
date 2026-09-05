from datetime import datetime, timedelta, timezone

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot, Zone
from strategy.research.setups.s008_displacement_continuation import IMPULSE_THRESHOLD, S008DisplacementContinuationSetup

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
SETUP = S008DisplacementContinuationSetup()


def _zone(direction="bullish", impulse_strength=1.5, mitigation_status="unmitigated", touch_count=1, zone_high=105.0, zone_low=100.0, mz_high=103.0, mz_low=101.0):
    return Zone(
        kind="order_block", direction=direction, zone_relative_position="inside_price",
        zone_high=zone_high, zone_low=zone_low, status="active", resolution_detail="unmitigated",
        resolution_pct=0.0, touch_count=touch_count, distance_from_price=0.0,
        created_at=START - timedelta(hours=1), resolved_at=None, source_module="order_block",
        raw={"impulse_strength": impulse_strength, "mitigation_zone_high": mz_high, "mitigation_zone_low": mz_low, "mitigation_zone_status": mitigation_status},
    )


def _snapshot(zones=None, current_price=102.0, cvd=None):
    return MarketIntelligenceSnapshot(
        symbol="SOLUSDT", timeframe="15m", timestamp=START, current_price=current_price,
        structure={}, zones=zones or [], levels=[],
        order_flow={"delta": {}, "cvd": cvd or {}},
        sessions={"active_now": [], "previous_period_high_low": {}},
        intermarket={}, volume_profile={}, data_quality={},
    )


def test_does_not_fire_with_no_order_blocks():
    result = SETUP.evaluate(_snapshot(zones=[]))
    assert result.fired is False
    assert result.required_conditions[0].name == "displaced_order_block_exists"


def test_does_not_fire_below_impulse_threshold():
    zone = _zone(impulse_strength=IMPULSE_THRESHOLD - 0.01)
    result = SETUP.evaluate(_snapshot(zones=[zone]))
    assert result.fired is False


def test_fires_at_exactly_the_impulse_threshold():
    zone = _zone(impulse_strength=IMPULSE_THRESHOLD)
    result = SETUP.evaluate(_snapshot(zones=[zone]))
    assert result.fired is True
    assert result.direction == "LONG"


def test_does_not_fire_when_price_outside_mitigation_zone():
    zone = _zone(mz_high=103.0, mz_low=101.0)
    result = SETUP.evaluate(_snapshot(zones=[zone], current_price=110.0))
    assert result.fired is False
    failed = [c.name for c in result.required_conditions if not c.satisfied]
    assert "price_inside_active_mitigation_zone" in failed


def test_does_not_fire_when_mitigation_zone_not_active():
    zone = _zone(mitigation_status="fully_mitigated")
    result = SETUP.evaluate(_snapshot(zones=[zone]))
    assert result.fired is False


def test_does_not_fire_on_second_touch():
    zone = _zone(touch_count=2)
    result = SETUP.evaluate(_snapshot(zones=[zone]))
    assert result.fired is False
    failed = [c.name for c in result.required_conditions if not c.satisfied]
    assert "first_retest" in failed


def test_bearish_block_fires_short():
    zone = _zone(direction="bearish")
    result = SETUP.evaluate(_snapshot(zones=[zone]))
    assert result.fired is True
    assert result.direction == "SHORT"


def test_cvd_confirmation_is_optional_not_gating():
    zone = _zone(direction="bullish")
    result_no_cvd = SETUP.evaluate(_snapshot(zones=[zone], cvd={}))
    result_with_cvd = SETUP.evaluate(_snapshot(zones=[zone], cvd={"anchor1": {"cvd_direction": "up"}}))

    assert result_no_cvd.fired is True
    assert result_with_cvd.fired is True
    assert result_no_cvd.evidence_count == 0
    assert result_with_cvd.evidence_count == 1


def test_deterministic_across_repeated_calls():
    zone = _zone()
    snapshot = _snapshot(zones=[zone])
    r1 = SETUP.evaluate(snapshot)
    r2 = SETUP.evaluate(snapshot)
    assert r1.fired == r2.fired
    assert r1.direction == r2.direction


def test_no_state_carried_between_unrelated_snapshots():
    fresh_setup = S008DisplacementContinuationSetup()
    zone_a = _zone(direction="bullish", impulse_strength=2.0)
    zone_b = _zone(direction="bearish", impulse_strength=1.2)

    result_a = fresh_setup.evaluate(_snapshot(zones=[zone_a]))
    result_b = fresh_setup.evaluate(_snapshot(zones=[zone_b]))

    assert result_a.direction == "LONG"
    assert result_b.direction == "SHORT"  # unaffected by the prior call
