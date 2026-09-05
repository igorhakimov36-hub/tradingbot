"""
CVD-neutral research variants of S001/S007 for the Signal-Value
ablation. RESEARCH-ONLY. Each is a subclass of the real, unmodified
production Setup that overrides ONLY the single CVD-dependent method,
calling nothing else differently - every other condition (sweep
detection, CHOCH, multi-source, SMT for S001; liquidity/structure
conditions for S007) is inherited unchanged from the production class.

`strategy/setups/liquidity_sweep_reversal.py` and
`strategy/setups/trend_continuation_confluence.py` are not modified.
"""

from strategy.setups.base import ConditionResult, Side
from strategy.setups.liquidity_sweep_reversal import LiquiditySweepReversalSetup
from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot


class CVDNeutralLiquiditySweepReversalSetup(LiquiditySweepReversalSetup):
    """
    S001 with `cvd_confirms_reversal` always satisfied - i.e. the CVD
    gate is removed while every other required/additional condition
    (sweep detection, CHOCH, multi-source, SMT, evidence_count) is
    evaluated by the real, unmodified inherited methods exactly as
    production does. Used only to measure what S001 would have traded
    if CVD were never a gate - not a proposal to change production.
    """

    name = "liquidity_sweep_reversal_cvd_neutral_research"

    def _cvd_confirms(self, snapshot: MarketIntelligenceSnapshot, direction: Side) -> ConditionResult:
        return ConditionResult(
            name="cvd_confirms_reversal",
            satisfied=True,
            detail="CVD-neutral research variant - this condition is always satisfied; the real CVD dependency is removed for ablation only, not a production change.",
            evidence={"neutralized": True},
        )
