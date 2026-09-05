"""
S011 - Value Area Extension Fade (RANGE regime). Research-only
candidate, SOL Multi-Module Setup Discovery sprint. Frozen design:
docs/sol_multi_module_setup_research_protocol.md, Candidate 3.

Pure function of its snapshot, no internal state carried between
calls - matches strategy/setups/base.py's Setup protocol exactly.

Hypothesis: in an established RANGE regime, a price extension beyond
the current Value Area by a multiple of the profile's own bucket
resolution, with CVD already showing exhaustion, is evidence of
over-extension relative to two-sided value. Take-profit is the current
period's own poc_price - a structural target, not fixed 2R, since
"reversion to value" IS a reversion-to-POC thesis by construction
(disclosed deviation from the fixed-2R convention used by the other
two candidates, for direct comparability).
"""

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot
from strategy.setups.base import ConditionResult, Setup, SetupResult, Side

BUCKET_MULTIPLE = 3.0


class S011ValueAreaFadeSetup:
    """
    require_cvd_confirmation (default True, the frozen/production
    behavior): when False, cvd_exhaustion_confirms_reversion is still
    computed and reported (additional_evidence), but does not gate
    firing - a predeclared ablation variant (frozen protocol Section
    5's own "trigger+context, no confirmation" comparison), added to
    complete the interaction analysis, not a new candidate design.
    Setup parameters (thresholds, timing) are unchanged either way.
    """

    name = "s011_value_area_fade"

    def __init__(self, require_cvd_confirmation: bool = True) -> None:
        self._require_cvd_confirmation = require_cvd_confirmation

    def evaluate(self, snapshot: MarketIntelligenceSnapshot) -> SetupResult:
        regime_condition = self._regime_condition(snapshot)
        profile = snapshot.volume_profile.get("current_forming_profile")

        if not regime_condition.satisfied or profile is None:
            return SetupResult(
                setup_name=self.name,
                fired=False,
                direction=None,
                required_conditions=[regime_condition],
                additional_evidence=[],
                evidence_count=0,
                reasoning="Did not fire - RANGE regime or current_forming_profile not present.",
                symbol=snapshot.symbol,
                timestamp=snapshot.timestamp,
            )

        extension_condition, direction = self._extension_condition(snapshot, profile)

        if direction is None:
            return SetupResult(
                setup_name=self.name,
                fired=False,
                direction=None,
                required_conditions=[regime_condition, extension_condition],
                additional_evidence=[],
                evidence_count=0,
                reasoning="Did not fire - no qualifying Value Area extension.",
                symbol=snapshot.symbol,
                timestamp=snapshot.timestamp,
            )

        cvd_condition = self._cvd_exhaustion_condition(snapshot, direction)

        if self._require_cvd_confirmation:
            required = [regime_condition, extension_condition, cvd_condition]
            additional = []
        else:
            required = [regime_condition, extension_condition]
            additional = [cvd_condition]
        fired = all(c.satisfied for c in required)

        return SetupResult(
            setup_name=self.name,
            fired=fired,
            direction=direction if fired else None,
            required_conditions=required,
            additional_evidence=additional,
            evidence_count=sum(1 for c in additional if c.satisfied),
            reasoning=self._build_reasoning(fired, direction, required),
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
        )

    def _regime_condition(self, snapshot: MarketIntelligenceSnapshot) -> ConditionResult:
        regime = snapshot.structure.get("market_structure")
        return ConditionResult(
            name="range_regime",
            satisfied=regime == "RANGE",
            detail=f"market_structure={regime}",
            evidence={"market_structure": regime},
        )

    def _extension_condition(self, snapshot: MarketIntelligenceSnapshot, profile: dict) -> tuple[ConditionResult, Side | None]:
        va_high = profile.get("value_area_high")
        va_low = profile.get("value_area_low")
        bucket_size = profile.get("bucket_size")

        if va_high is None or va_low is None or not bucket_size:
            return (
                ConditionResult(
                    name="value_area_extension",
                    satisfied=False,
                    detail="value_area_high/low or bucket_size unavailable",
                    evidence={},
                ),
                None,
            )

        threshold = BUCKET_MULTIPLE * bucket_size

        if snapshot.current_price > va_high + threshold:
            return (
                ConditionResult(
                    name="value_area_extension",
                    satisfied=True,
                    detail=f"price={snapshot.current_price:.2f} beyond value_area_high={va_high:.2f} by >= {BUCKET_MULTIPLE}x bucket_size={bucket_size}",
                    evidence={"current_price": snapshot.current_price, "value_area_high": va_high, "bucket_size": bucket_size},
                ),
                "SHORT",
            )
        if snapshot.current_price < va_low - threshold:
            return (
                ConditionResult(
                    name="value_area_extension",
                    satisfied=True,
                    detail=f"price={snapshot.current_price:.2f} beyond value_area_low={va_low:.2f} by >= {BUCKET_MULTIPLE}x bucket_size={bucket_size}",
                    evidence={"current_price": snapshot.current_price, "value_area_low": va_low, "bucket_size": bucket_size},
                ),
                "LONG",
            )
        return (
            ConditionResult(
                name="value_area_extension",
                satisfied=False,
                detail=f"price={snapshot.current_price:.2f} within {BUCKET_MULTIPLE}x bucket_size of value area",
                evidence={"current_price": snapshot.current_price, "value_area_high": va_high, "value_area_low": va_low},
            ),
            None,
        )

    def _cvd_exhaustion_condition(self, snapshot: MarketIntelligenceSnapshot, direction: Side) -> ConditionResult:
        target = "bearish_exhaustion" if direction == "SHORT" else "bullish_exhaustion"
        matches = [
            anchor for anchor, data in snapshot.order_flow.get("cvd", {}).items()
            if data.get("cvd_exhaustion_flag") == target
        ]
        return ConditionResult(
            name="cvd_exhaustion_confirms_reversion",
            satisfied=bool(matches),
            detail=(f"confirmed by {matches}" if matches else f"no configured CVD anchor showed {target}"),
            evidence={"matching_anchors": matches},
        )

    def _build_reasoning(self, fired: bool, direction: Side, required: list[ConditionResult]) -> str:
        if not fired:
            failed = [c.name for c in required if not c.satisfied]
            return f"Did not fire - failed required condition(s): {', '.join(failed)}."
        required_summary = " ".join(f"Required: {c.detail}." for c in required)
        return f"{direction} - value area extension fade. {required_summary}"
