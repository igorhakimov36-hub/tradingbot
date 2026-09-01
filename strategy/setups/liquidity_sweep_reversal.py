"""
Liquidity Sweep Reversal - the first Strategy Engine V2 setup (Phase
2.1, Step 2/3).

Why this setup was chosen
--------------------------
Per the Phase 2 architectural review, Liquidity Pools is "the single
most decision-relevant reversal setup primitive in the whole platform"
- liquidity engineering (price running resting stops before reversing)
is the central thesis smart-money-concepts trading is built on, not
one technique among many. This setup is also the richest available
demonstration of the completed Market Intelligence architecture: it
requires genuine agreement across three of the four families from the
Snapshot taxonomy - Zones (a swept Liquidity Pool), Order Flow (CVD
exhaustion/divergence confirming the reversal), and Structure
(CHOCH, recorded as additional evidence) - rather than reading a single
module in isolation. Order Block Continuation and FVG Rebalance were
considered but only exercise the Zones family; SMT Reversal is
correlation-only and needs a second symbol wired up for no added
benefit to validating the core architecture.

Institutional logic
--------------------
A Liquidity Pool aggregates resting stop/breakout orders (equal highs/
lows, session extremes, round numbers). When price sweeps it - wicking
beyond the pool and closing back inside/beyond in the opposite
direction - those resting orders have just been triggered. That, by
itself, only tells you liquidity was taken; it says nothing about
whether the triggering was a genuine reversal or a continuation stop-
run. Order flow confirmation (CVD exhaustion or divergence in the
reversal's direction) is what distinguishes "liquidity was taken and
the move continued" from "liquidity was taken and the move is
exhausted" - which is why sweep-alone is NOT sufficient to fire this
setup; both are REQUIRED.

Direction
---------
A buy-side pool (built from highs - equal highs, session highs) sitting
ABOVE price getting swept implies the up-move exhausted taking out
resting sell-stops/breakout-buys - a SHORT setup. A sell-side pool
(built from lows) swept implies the down-move exhausted - a LONG setup.

Required conditions (BOTH must be true to fire)
--------------------------------------------------
1. `liquidity_pool_swept_this_bar` - a Liquidity Pool zone resolved
   (swept) with `resolved_at` equal to the CURRENT snapshot's
   timestamp - i.e. the sweep happened on THIS bar, not some earlier
   bar still sitting in the tracker's bounded history.
2. `cvd_confirms_reversal` - ANY configured CVD anchor shows the
   matching exhaustion or divergence flag for the inferred direction.

Additional evidence (recorded, never gates firing)
------------------------------------------------------
- `choch_confirms_direction` - Market Structure's CHOCH reading agrees.
- `pool_has_multiple_sources` - the swept pool was itself confluence
  (more than one sub-detector agreed it was a pool), not a single weak
  signal.
- `smt_confirms_direction` - any configured intermarket pair shows
  structural divergence agreeing (empty/unsatisfied if no intermarket
  pair is wired up - this setup does not require one).

`evidence_count` is a raw count of how many of the three ABOVE were
satisfied - descriptive statistics for the Trade Journal, never a
weight and never part of the fire/no-fire decision.

If more than one Liquidity Pool was swept on the same bar (rare), the
first one found in the snapshot's own zone ordering is used -
deterministic, since that ordering is itself deterministic, but not
claimed to be "the best" one; ranking simultaneous sweeps is a future
refinement, not needed to validate this setup.
"""

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot, Zone
from strategy.setups.base import ConditionResult, Setup, SetupResult, Side


class LiquiditySweepReversalSetup:
    name = "liquidity_sweep_reversal"

    def evaluate(self, snapshot: MarketIntelligenceSnapshot) -> SetupResult:
        swept_pool = self._find_fresh_sweep(snapshot)

        sweep_condition = self._sweep_condition(snapshot, swept_pool)

        if swept_pool is None:
            return SetupResult(
                setup_name=self.name,
                fired=False,
                direction=None,
                required_conditions=[sweep_condition],
                additional_evidence=[],
                evidence_count=0,
                reasoning="No liquidity pool sweep detected on this bar.",
                symbol=snapshot.symbol,
                timestamp=snapshot.timestamp,
            )

        direction: Side = "SHORT" if swept_pool.direction == "buy_side" else "LONG"

        cvd_condition = self._cvd_confirms(snapshot, direction)
        required = [sweep_condition, cvd_condition]
        fired = all(c.satisfied for c in required)

        additional = [
            self._choch_confirms(snapshot, direction),
            self._multi_source_pool(swept_pool),
            self._smt_confirms(snapshot, direction),
        ]
        evidence_count = sum(1 for c in additional if c.satisfied)

        return SetupResult(
            setup_name=self.name,
            fired=fired,
            direction=direction if fired else None,
            required_conditions=required,
            additional_evidence=additional,
            evidence_count=evidence_count,
            reasoning=self._build_reasoning(fired, direction, swept_pool, required, additional, evidence_count),
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
        )

    def _find_fresh_sweep(self, snapshot: MarketIntelligenceSnapshot) -> Zone | None:
        candidates = [
            zone for zone in snapshot.zones
            if zone.kind == "liquidity_pool"
            and zone.status == "resolved"
            and zone.resolution_detail == "swept"
            and zone.resolved_at == snapshot.timestamp
        ]

        return candidates[0] if candidates else None

    def _sweep_condition(self, snapshot: MarketIntelligenceSnapshot, swept_pool: Zone | None) -> ConditionResult:
        if swept_pool is None:
            return ConditionResult(
                name="liquidity_pool_swept_this_bar",
                satisfied=False,
                detail="no liquidity pool was swept on this bar",
                evidence={},
            )

        return ConditionResult(
            name="liquidity_pool_swept_this_bar",
            satisfied=True,
            detail=(
                f"{swept_pool.direction} liquidity pool [{swept_pool.zone_low:.2f}, "
                f"{swept_pool.zone_high:.2f}] swept at {swept_pool.resolved_at}"
            ),
            evidence={
                "direction": swept_pool.direction,
                "zone_high": swept_pool.zone_high,
                "zone_low": swept_pool.zone_low,
                "sources": swept_pool.raw.get("sources", []),
                "swept_timestamp": swept_pool.resolved_at,
            },
        )

    def _cvd_confirms(self, snapshot: MarketIntelligenceSnapshot, direction: Side) -> ConditionResult:
        target_exhaustion = "bearish_exhaustion" if direction == "SHORT" else "bullish_exhaustion"
        target_divergence = "bearish_divergence" if direction == "SHORT" else "bullish_divergence"

        matches = []
        for anchor_name, data in snapshot.order_flow.get("cvd", {}).items():
            if data.get("cvd_exhaustion_flag") == target_exhaustion:
                matches.append({"anchor": anchor_name, "flag": "cvd_exhaustion_flag", "value": target_exhaustion})
            if data.get("price_cvd_divergence_flag") == target_divergence:
                matches.append({"anchor": anchor_name, "flag": "price_cvd_divergence_flag", "value": target_divergence})

        return ConditionResult(
            name="cvd_confirms_reversal",
            satisfied=bool(matches),
            detail=(
                f"CVD confirmed via {matches}" if matches
                else f"no configured CVD anchor showed {target_exhaustion}/{target_divergence}"
            ),
            evidence={"matches": matches, "checked_anchors": list(snapshot.order_flow.get("cvd", {}).keys())},
        )

    def _choch_confirms(self, snapshot: MarketIntelligenceSnapshot, direction: Side) -> ConditionResult:
        target = "BEARISH_CHOCH" if direction == "SHORT" else "BULLISH_CHOCH"
        actual = snapshot.structure.get("choch")

        return ConditionResult(
            name="choch_confirms_direction",
            satisfied=actual == target,
            detail=f"choch={actual}, expected={target}",
            evidence={"choch": actual},
        )

    def _multi_source_pool(self, swept_pool: Zone) -> ConditionResult:
        sources = swept_pool.raw.get("sources", [])

        return ConditionResult(
            name="pool_has_multiple_sources",
            satisfied=len(sources) > 1,
            detail=f"sources={sources}",
            evidence={"sources": sources},
        )

    def _smt_confirms(self, snapshot: MarketIntelligenceSnapshot, direction: Side) -> ConditionResult:
        target = "bearish_divergence" if direction == "SHORT" else "bullish_divergence"

        matches = [
            pair_name for pair_name, data in snapshot.intermarket.items()
            if data.get("structural_divergence_flag") == target
        ]

        return ConditionResult(
            name="smt_confirms_direction",
            satisfied=bool(matches),
            detail=(f"confirmed by {matches}" if matches else "no configured intermarket pair confirmed"),
            evidence={"matching_pairs": matches},
        )

    def _build_reasoning(
        self,
        fired: bool,
        direction: Side,
        swept_pool: Zone,
        required: list[ConditionResult],
        additional: list[ConditionResult],
        evidence_count: int,
    ) -> str:
        if not fired:
            failed = [c.name for c in required if not c.satisfied]
            return f"Did not fire - failed required condition(s): {', '.join(failed)}."

        evidence_summary = "; ".join(f"{c.name}={'yes' if c.satisfied else 'no'}" for c in additional)

        return (
            f"{direction} - liquidity sweep reversal. "
            f"Required: {required[0].detail}. "
            f"Required: {required[1].detail}. "
            f"Additional evidence ({evidence_count}/{len(additional)}): {evidence_summary}."
        )
