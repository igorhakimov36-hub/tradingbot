"""
S008 - Displacement-Impulse Continuation. Research-only candidate,
SOL Multi-Module Setup Discovery sprint. Frozen design:
docs/sol_multi_module_setup_research_protocol.md, Candidate 1.

Pure function of its snapshot, no internal state carried between
calls, matching strategy/setups/base.py's Setup protocol exactly (same
contract as every production setup) - this class differs from a
production setup only in where it lives (strategy/research/, not
strategy/setups/), never in its interface.

Hypothesis: an Order Block whose favorable excursion since creation
already exceeds its own creation-time ATR (impulse_strength >= 1.0)
reflects validated institutional displacement. A first retracement
into the ORIGIN candle's body (mitigation_zone, tighter than the full
wick zone) offers a defined re-entry into that same participation.

Disclosed limitation (module_decision_register.md A1/A2, not resolved
by this sprint): the Order Block tracker's own BOS-event identity can
collapse consecutive same-direction breaks, and its origin search is
not leg-scoped. impulse_strength/mitigation_zone inherit both defects
unresolved - accepted explicitly here, not silently ignored, per the
register's own "resolve or explicitly accept as a known limitation"
instruction.
"""

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot, Zone
from strategy.setups.base import ConditionResult, Setup, SetupResult, Side

IMPULSE_THRESHOLD = 1.0


class S008DisplacementContinuationSetup:
    name = "s008_displacement_continuation"

    def evaluate(self, snapshot: MarketIntelligenceSnapshot) -> SetupResult:
        block = self._find_candidate(snapshot)
        opportunity_condition = self._opportunity_condition(block)

        if block is None:
            return SetupResult(
                setup_name=self.name,
                fired=False,
                direction=None,
                required_conditions=[opportunity_condition],
                additional_evidence=[],
                evidence_count=0,
                reasoning="No active Order Block with impulse_strength >= 1.0 found.",
                symbol=snapshot.symbol,
                timestamp=snapshot.timestamp,
            )

        direction: Side = "LONG" if block.direction == "bullish" else "SHORT"

        mitigation_condition = self._mitigation_zone_condition(snapshot, block)
        touch_condition = self._touch_condition(block)
        cvd_evidence = self._cvd_confirms(snapshot, direction)

        required = [opportunity_condition, mitigation_condition, touch_condition]
        fired = all(c.satisfied for c in required)
        evidence_count = 1 if cvd_evidence.satisfied else 0

        return SetupResult(
            setup_name=self.name,
            fired=fired,
            direction=direction if fired else None,
            required_conditions=required,
            additional_evidence=[cvd_evidence],
            evidence_count=evidence_count,
            reasoning=self._build_reasoning(fired, direction, required, cvd_evidence),
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
        )

    def _find_candidate(self, snapshot: MarketIntelligenceSnapshot) -> Zone | None:
        candidates = [
            z for z in snapshot.zones
            if z.kind == "order_block"
            and z.status == "active"
            and (z.raw.get("impulse_strength") or 0.0) >= IMPULSE_THRESHOLD
        ]
        return candidates[0] if candidates else None

    def _opportunity_condition(self, block: Zone | None) -> ConditionResult:
        if block is None:
            return ConditionResult(
                name="displaced_order_block_exists",
                satisfied=False,
                detail=f"no active Order Block with impulse_strength >= {IMPULSE_THRESHOLD}",
                evidence={},
            )
        return ConditionResult(
            name="displaced_order_block_exists",
            satisfied=True,
            detail=f"{block.direction} Order Block impulse_strength={block.raw.get('impulse_strength'):.3f}",
            evidence={
                "direction": block.direction,
                "impulse_strength": block.raw.get("impulse_strength"),
                "zone_high": block.zone_high,
                "zone_low": block.zone_low,
            },
        )

    def _mitigation_zone_condition(self, snapshot: MarketIntelligenceSnapshot, block: Zone) -> ConditionResult:
        mz_high = block.raw.get("mitigation_zone_high")
        mz_low = block.raw.get("mitigation_zone_low")
        mz_status = block.raw.get("mitigation_zone_status")

        inside = (
            mz_high is not None and mz_low is not None
            and mz_low <= snapshot.current_price <= mz_high
            and mz_status != "fully_mitigated"
        )

        return ConditionResult(
            name="price_inside_active_mitigation_zone",
            satisfied=inside,
            detail=(
                f"current_price={snapshot.current_price:.2f} vs mitigation zone "
                f"[{mz_low}, {mz_high}] status={mz_status}"
            ),
            evidence={"mitigation_zone_high": mz_high, "mitigation_zone_low": mz_low, "mitigation_zone_status": mz_status},
        )

    def _touch_condition(self, block: Zone) -> ConditionResult:
        return ConditionResult(
            name="first_retest",
            satisfied=block.touch_count == 1,
            detail=f"touch_count={block.touch_count}",
            evidence={"touch_count": block.touch_count},
        )

    def _cvd_confirms(self, snapshot: MarketIntelligenceSnapshot, direction: Side) -> ConditionResult:
        target = "up" if direction == "LONG" else "down"
        matches = [
            anchor for anchor, data in snapshot.order_flow.get("cvd", {}).items()
            if data.get("cvd_direction") == target
        ]
        return ConditionResult(
            name="cvd_direction_agrees",
            satisfied=bool(matches),
            detail=(f"confirmed by {matches}" if matches else "no configured CVD anchor agreed (not required)"),
            evidence={"matching_anchors": matches},
        )

    def _build_reasoning(self, fired: bool, direction: Side, required: list[ConditionResult], cvd_evidence: ConditionResult) -> str:
        if not fired:
            failed = [c.name for c in required if not c.satisfied]
            return f"Did not fire - failed required condition(s): {', '.join(failed)}."
        required_summary = " ".join(f"Required: {c.detail}." for c in required)
        return f"{direction} - displacement-impulse continuation. {required_summary} Optional cvd_direction_agrees={'yes' if cvd_evidence.satisfied else 'no'}."
