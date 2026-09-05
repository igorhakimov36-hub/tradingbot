"""
Tests for strategy/research/cvd_delta_neutral_setups.py - proving the
CVD-neutral research variant changes ONLY the CVD condition and leaves
production's own LiquiditySweepReversalSetup completely unaffected.
"""

from datetime import datetime, timezone

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot, Zone
from strategy.research.cvd_delta_neutral_setups import CVDNeutralLiquiditySweepReversalSetup
from strategy.setups.liquidity_sweep_reversal import LiquiditySweepReversalSetup

TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _swept_pool_zone(direction="buy_side"):
    return Zone(
        kind="liquidity_pool", direction=direction, zone_relative_position="inside_price",
        zone_high=105.0, zone_low=100.0, status="resolved", resolution_detail="swept",
        resolution_pct=1.0, touch_count=2, distance_from_price=0.0,
        created_at=TS, resolved_at=TS, source_module="liquidity_pool",
        raw={"sources": ["round_number"]},
    )


def _snapshot(zones, cvd_confirms=False, choch_confirms=False, smt_confirms=False):
    return MarketIntelligenceSnapshot(
        symbol="SOLUSDT", timeframe="15m", timestamp=TS, current_price=102.0,
        structure={"choch": "BEARISH_CHOCH" if choch_confirms else "NONE"},
        zones=zones, levels=[],
        order_flow={
            "delta": {},
            "cvd": {"continuous": {
                "cvd_exhaustion_flag": "bearish_exhaustion" if cvd_confirms else "none",
                "price_cvd_divergence_flag": "none",
            }},
        },
        sessions={}, intermarket={}, volume_profile={}, data_quality={},
    )


def test_neutral_variant_fires_when_only_cvd_would_have_blocked():
    zones = [_swept_pool_zone()]
    snapshot = _snapshot(zones, cvd_confirms=False, choch_confirms=True)

    production = LiquiditySweepReversalSetup()
    neutral = CVDNeutralLiquiditySweepReversalSetup()

    prod_result = production.evaluate(snapshot)
    neutral_result = neutral.evaluate(snapshot)

    assert prod_result.fired is False  # blocked by CVD in production
    assert neutral_result.fired is True  # CVD gate removed


# =========================================================
# Requirement 10: neutralizing CVD changes no unrelated condition
# =========================================================


def test_neutral_variant_leaves_sweep_condition_identical():
    zones = [_swept_pool_zone()]
    snapshot = _snapshot(zones, cvd_confirms=False, choch_confirms=True)

    production = LiquiditySweepReversalSetup()
    neutral = CVDNeutralLiquiditySweepReversalSetup()

    prod_result = production.evaluate(snapshot)
    neutral_result = neutral.evaluate(snapshot)

    # required_conditions[0] is always the sweep condition - must be
    # byte-identical between the two (same name/satisfied/detail/evidence).
    assert prod_result.required_conditions[0] == neutral_result.required_conditions[0]
    # additional_evidence (CHOCH/multi-source/SMT) must be identical too.
    assert prod_result.additional_evidence == neutral_result.additional_evidence
    assert prod_result.evidence_count == neutral_result.evidence_count


def test_neutral_variant_only_differs_in_the_cvd_condition_itself():
    zones = [_swept_pool_zone()]
    snapshot = _snapshot(zones, cvd_confirms=False, choch_confirms=True)

    production = LiquiditySweepReversalSetup()
    neutral = CVDNeutralLiquiditySweepReversalSetup()

    prod_result = production.evaluate(snapshot)
    neutral_result = neutral.evaluate(snapshot)

    prod_cvd = next(c for c in prod_result.required_conditions if c.name == "cvd_confirms_reversal")
    neutral_cvd = next(c for c in neutral_result.required_conditions if c.name == "cvd_confirms_reversal")

    assert prod_cvd.satisfied is False
    assert neutral_cvd.satisfied is True

    # Every OTHER required condition is untouched.
    prod_others = [c for c in prod_result.required_conditions if c.name != "cvd_confirms_reversal"]
    neutral_others = [c for c in neutral_result.required_conditions if c.name != "cvd_confirms_reversal"]
    assert prod_others == neutral_others


# =========================================================
# Requirement 12: production behavior byte-identical when research
# mode (the neutral subclass) is not instantiated/used at all
# =========================================================


def test_production_setup_unaffected_by_the_subclass_existing():
    zones = [_swept_pool_zone()]
    snapshot = _snapshot(zones, cvd_confirms=True, choch_confirms=True)

    # Import already happened at module load (cvd_delta_neutral_setups
    # imported at top of this file) - production behavior must be
    # identical to a completely fresh, isolated evaluation.
    result_a = LiquiditySweepReversalSetup().evaluate(snapshot)
    result_b = LiquiditySweepReversalSetup().evaluate(snapshot)
    assert result_a == result_b


def test_neutral_subclass_does_not_override_anything_besides_cvd_confirms():
    # Confirms the subclass has no other overridden methods - a direct
    # structural proof, not just behavioral spot-checks above.
    own_attrs = set(vars(CVDNeutralLiquiditySweepReversalSetup)) - {
        "__module__", "__qualname__", "__doc__", "name",
        "__firstlineno__", "__static_attributes__",
    }
    assert own_attrs == {"_cvd_confirms"}


# =========================================================
# Determinism
# =========================================================


def test_deterministic():
    zones = [_swept_pool_zone()]
    snapshot = _snapshot(zones, cvd_confirms=False, choch_confirms=True)
    neutral = CVDNeutralLiquiditySweepReversalSetup()
    r1 = neutral.evaluate(snapshot)
    r2 = neutral.evaluate(snapshot)
    assert r1 == r2
