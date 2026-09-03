"""
Fair Value Gap Rebalance - the fifth Strategy Engine V2 setup (S005).

Why Fair Value Gaps, and why now
------------------------------------
Every remaining unused tracker was reviewed against expected
independent information, portfolio diversification, overlap with the
two APPROVED setups (S001 Liquidity Sweep Reversal, S002 Order Block
Continuation), institutional validity, architectural simplicity, and
research value. Fair Value Gaps ranked highest, decided by one verified
structural fact: `strategy/features/fair_value_gap.py`'s own docstring
states this tracker is "a fully independent primitive - no dependency
on any other Smart Money module," detected by a plain 3-candle wick-
overlap check. Order Blocks AND Breaker Blocks, by contrast, are both
explicitly gated on `detect_bos` - a candidate setup built around BOS
directly would share its literal triggering event with Order Block
Continuation (monetizing the same detected break at two different
times: momentum-now vs. retest-later). Fair Value Gaps carry no such
shared root cause with either approved setup. Equal Highs/Lows and
Delta were ruled out for the same reason S001 already exercises them
indirectly (both are sub-detector inputs already consumed by Liquidity
Pools/CVD); Breaker Blocks was ruled out as already twice-flagged
mechanically near-identical to Order Blocks.

Institutional logic
--------------------
A Fair Value Gap marks a 3-candle imbalance - two-sided trading did not
fully occur at that level during the impulsive move that created it.
Price statistically revisits ("fills") this zone. Exactly like Order
Block Continuation's institutional reading (not "the move failed",
which is Breaker Blocks' domain), a FIRST retracement into a still-
unfilled gap offers a defined re-entry into the SAME direction that
produced the original impulsive move - the gap's remaining unfilled
interest is expected to support continuation once partially rebalanced,
not to reverse it. This setup was named alongside Order Block
Continuation as a peer candidate in Liquidity Sweep Reversal's own
module docstring ("Order Block Continuation and FVG Rebalance were
considered but only exercise the Zones family") - this is that setup,
now built.

Direction
---------
A bullish FVG (created during an upward impulsive move, sitting below
price) acts as support on a retracement into it - a LONG setup. A
bearish FVG (created during a downward move) acts as resistance - a
SHORT setup. The tracker's own `direction` field, unmodified.

Required condition (the only one that gates firing)
--------------------------------------------------------
`price_rebalancing_unfilled_gap` - an ACTIVE Fair Value Gap zone
(`kind == "fvg"`, `status == "active"`) that has begun filling but is
not yet fully filled (`resolution_detail == "partially_filled"` - the
Snapshot's mapping of the tracker's own `fill_status` field) AND price
is CURRENTLY inside it (`zone_relative_position == "inside_price"`,
recomputed fresh from the current bar's price every call).

Why this combination, not a "first touch" counter (Fair Value Gaps
expose no `touch_count` field the way Order Blocks do, so Order Block
Continuation's exact mechanism does not transfer directly): the two
conditions together are mutually reinforcing rather than independently
gate-able. By the time a snapshot reflects the CURRENT bar's price
fully applied to the tracker, a gap that price is presently inside must
already show `fill_pct > 0` - "active" (0% filled) and "inside_price"
simultaneously true is not a state that occurs in practice, since
entering the gap is exactly what advances `fill_status` past "active".
Requiring "partially_filled" (not "completely_filled", which moves the
zone to the resolved/filled list entirely) together with "inside_price"
isolates the same institutionally meaningful moment Order Block
Continuation isolates via `touch_count == 1` - the retracement is
underway but the gap has not yet been fully consumed - without needing
a field this tracker does not expose.

Known re-fire characteristic (documented, not treated as a defect,
same shape as Volume Node Reversal's own accepted characteristic): a
gap can remain "partially_filled" and "inside_price" across several
consecutive bars while price consolidates inside it, or across
separate later visits if price exits and re-enters before the gap is
eventually fully filled. This is bounded and self-limiting - the
condition permanently stops being true once fully filled, and the
one-trade-at-a-time engine already prevents any double-counting while
a position from an earlier bar is still open.

Additional evidence (individually recorded; NOT required to fire)
------------------------------------------------------------------------
Matching every setup built since Liquidity Sweep Reversal's own
permanent confirmation gate was earned through experimentation specific
to that setup - no confirmation is required here yet:

- `fvg_confluence` - another ACTIVE Fair Value Gap of the SAME
  direction with an overlapping range also exists - the identical
  "independent zones agreeing" shape as Order Block Continuation's
  `order_block_confluence`, generalized to this zone kind.
- `overlaps_order_block_zone` - an ACTIVE Order Block of the SAME
  direction, with an overlapping range, also currently exists - a
  genuinely new CROSS-FAMILY confluence check (two independently-
  triggered zone detectors, one BOS-gated and one not, agreeing on the
  same price region), not previously exercised by any setup.

Stop-loss
---------
The gap's own zone edge - `zone_low` for LONG, `zone_high` for SHORT -
the level at which the gap would become fully filled and the
"held as support/resistance" thesis is falsified. Reuses the *exact*
existing adapter code path unmodified (same evidence keys Liquidity
Sweep Reversal, Order Block Continuation, and Volume Node Reversal
already use).
"""

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot, Zone
from strategy.setups.base import ConditionResult, Setup, SetupResult, Side


class FairValueGapRebalanceSetup:
    name = "fair_value_gap_rebalance"

    def evaluate(self, snapshot: MarketIntelligenceSnapshot) -> SetupResult:
        touched_gap = self._find_rebalancing_gap(snapshot)

        touch_condition = self._touch_condition(touched_gap)

        if touched_gap is None:
            return SetupResult(
                setup_name=self.name,
                fired=False,
                direction=None,
                required_conditions=[touch_condition],
                additional_evidence=[],
                evidence_count=0,
                reasoning="No partially-filled Fair Value Gap currently contains price.",
                symbol=snapshot.symbol,
                timestamp=snapshot.timestamp,
            )

        direction: Side = "LONG" if touched_gap.direction == "bullish" else "SHORT"

        additional = [
            self._fvg_confluence(snapshot, touched_gap),
            self._overlaps_order_block_zone(snapshot, touched_gap),
        ]
        evidence_count = sum(1 for c in additional if c.satisfied)

        required = [touch_condition]
        fired = all(c.satisfied for c in required)

        return SetupResult(
            setup_name=self.name,
            fired=fired,
            direction=direction if fired else None,
            required_conditions=required,
            additional_evidence=additional,
            evidence_count=evidence_count,
            reasoning=self._build_reasoning(fired, direction, touched_gap, required, additional, evidence_count),
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
        )

    def _find_rebalancing_gap(self, snapshot: MarketIntelligenceSnapshot) -> Zone | None:
        candidates = [
            zone for zone in snapshot.zones
            if zone.kind == "fvg"
            and zone.status == "active"
            and zone.resolution_detail == "partially_filled"
            and zone.zone_relative_position == "inside_price"
        ]

        return candidates[0] if candidates else None

    def _touch_condition(self, touched_gap: Zone | None) -> ConditionResult:
        if touched_gap is None:
            return ConditionResult(
                name="price_rebalancing_unfilled_gap",
                satisfied=False,
                detail="no partially-filled Fair Value Gap currently contains price",
                evidence={},
            )

        return ConditionResult(
            name="price_rebalancing_unfilled_gap",
            satisfied=True,
            detail=(
                f"{touched_gap.direction} FVG [{touched_gap.zone_low:.2f}, "
                f"{touched_gap.zone_high:.2f}] being rebalanced (fill_pct={touched_gap.resolution_pct})"
            ),
            evidence={
                "direction": touched_gap.direction,
                "zone_high": touched_gap.zone_high,
                "zone_low": touched_gap.zone_low,
                "fill_pct": touched_gap.resolution_pct,
            },
        )

    def _fvg_confluence(self, snapshot: MarketIntelligenceSnapshot, touched_gap: Zone) -> ConditionResult:
        overlapping = [
            zone for zone in snapshot.zones
            if zone is not touched_gap
            and zone.kind == "fvg"
            and zone.status == "active"
            and zone.direction == touched_gap.direction
            and zone.zone_high >= touched_gap.zone_low
            and zone.zone_low <= touched_gap.zone_high
        ]

        return ConditionResult(
            name="fvg_confluence",
            satisfied=bool(overlapping),
            detail=(
                f"{len(overlapping)} other overlapping {touched_gap.direction} FVG(s) found"
                if overlapping else "no other overlapping same-direction FVG found"
            ),
            evidence={"overlapping_count": len(overlapping)},
        )

    def _overlaps_order_block_zone(self, snapshot: MarketIntelligenceSnapshot, touched_gap: Zone) -> ConditionResult:
        overlapping = [
            zone for zone in snapshot.zones
            if zone.kind == "order_block"
            and zone.status == "active"
            and zone.direction == touched_gap.direction
            and zone.zone_high >= touched_gap.zone_low
            and zone.zone_low <= touched_gap.zone_high
        ]

        return ConditionResult(
            name="overlaps_order_block_zone",
            satisfied=bool(overlapping),
            detail=(
                f"{len(overlapping)} overlapping {touched_gap.direction} Order Block(s) found"
                if overlapping else "no overlapping same-direction Order Block found"
            ),
            evidence={"overlapping_count": len(overlapping)},
        )

    def _build_reasoning(
        self,
        fired: bool,
        direction: Side,
        touched_gap: Zone,
        required: list[ConditionResult],
        additional: list[ConditionResult],
        evidence_count: int,
    ) -> str:
        if not fired:
            failed = [c.name for c in required if not c.satisfied]
            return f"Did not fire - failed required condition(s): {', '.join(failed)}."

        evidence_summary = "; ".join(f"{c.name}={'yes' if c.satisfied else 'no'}" for c in additional)
        required_summary = " ".join(f"Required: {c.detail}." for c in required)

        return (
            f"{direction} - fair value gap rebalance. "
            f"{required_summary} "
            f"Additional evidence ({evidence_count}/{len(additional)}): {evidence_summary}."
        )
