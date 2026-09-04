"""
Trend Continuation Confluence - the first Phase 3 setup (S007), and the
first setup in this project deliberately designed around multiple
independent Market Intelligence families from the start, rather than
discovered to combine them after the fact (S001 is the only prior setup
that reads more than one family, and that combination was a side effect
of choosing the richest single primitive, Liquidity Pools, not a
confluence-first design).

Why this candidate, and why now
--------------------------------
Per docs/phase3_confluence_research_design.md, this is the top-ranked
of five proposed S007 candidates - the only one that is a direct,
falsifiable test of an already-diagnosed failure rather than a
speculative new combination: docs/out_of_sample_validation_report.md
found Order Block Continuation (S002) failed every out-of-sample month
with no structural or order-flow context ever required to fire. This
setup is that missing context, made explicit: a confirmed structural
trend, retested at a genuine liquidity level, is a fundamentally
different (and testable) claim than "price touched a zone once."

Institutional logic
--------------------
A confirmed structural trend (BOS) implies a broken liquidity level -
the swing high/low institutions defended has already given way. Price
frequently retraces to retest that same level from the other side
("old resistance becomes support," and the mirror for downtrends)
before continuing. That retest is the entry; the trend confirms
*that* a continuation thesis is even on the table, and the retest zone
supplies *where*.

Family scoping decided at Step 0 (see docs/phase3_confluence_research_design.md
Step 0 verification and the conversation record - not silently narrowed
from the original candidate wording, but explicitly resolved this way
before implementation began):

1. Structure is read via `structure.bos` exactly as
   MarketStructureTracker documents it - a LEVEL-based reading, true on
   every bar the break still holds, not just the bar it first occurred.
   The original candidate wording ("a fresh BOS") would require
   knowing whether the break is recent, which needs either a history
   this tracker does not expose or state carried inside this Setup -
   the latter is explicitly forbidden by `strategy/setups/base.py`'s
   Setup protocol ("no internal state carried between calls"). Using
   `bos` as-is is the only zero-state, zero-new-logic option available.
2. "Liquidity" is scoped to Liquidity Pool zones specifically, not
   Equal Highs/Lows. The backtest adapter's stop-placement logic reads
   `required_conditions[0].evidence["zone_high"/"zone_low"]` - Liquidity
   Pools have a real zone; Equal Highs/Lows are single-price Levels with
   no width, and giving them one here would mean inventing a synthetic
   zone or changing the adapter, both against this task's constraints.
3. There is no "first touch" concept for a Liquidity Pool the way there
   is for Order Blocks. `liquidity_pool.py` confirms `touch_count`
   there counts the sub-detectors that FORMED the pool (equal-highs
   pivots, session extremes, round numbers) - not post-formation
   revisits. A pool is only ever `active` (unswept) or `swept`
   (retired), with no partial state between. The condition below is
   therefore named for what it actually checks - price currently inside
   an active, never-swept pool - not borrowed from S002/S006's
   "first touch" language, which would misdescribe this tracker's own
   semantics.

Direction and the pool/BOS pairing
------------------------------------
`BULLISH_BOS` (close still above the broken swing high) pairs with a
`buy_side` pool (built from prior highs) sitting at `inside_price`: a
level that was resistance, broken cleanly (never wick-rejected, or the
tracker would have marked it `swept` and retired it), now being
retested from above - a LONG continuation. `BEARISH_BOS` mirrors this
with a `sell_side` pool for SHORT. A pool of the wrong side (e.g. a
sell_side pool during a BULLISH_BOS) does not qualify - it is not the
level this trend broke.

This does not verify that the specific retested pool is the same swing
level that produced the specific current BOS reading - both are read
independently off the same snapshot, the same loose-coupling already
used by Liquidity Sweep Reversal (which does not verify its swept pool
and its optional CHOCH reading share a common cause either). Disclosed
here, not hidden.

Required conditions (ALL must be true to fire)
--------------------------------------------------
1. `price_inside_active_liquidity_pool` - an active (never-swept)
   Liquidity Pool zone of the side matching the current trend direction
   contains current price (`zone_relative_position == "inside_price"`).
   Placed FIRST in `required_conditions` - the backtest adapter reads
   `required_conditions[0].evidence` for `zone_high`/`zone_low`
   unmodified, the same convention S001/S002/S003/S006 already
   established.
2. `structural_trend_confirmed` - `structure.bos` is `BULLISH_BOS` or
   `BEARISH_BOS` (not `NO_BOS`).

Additional evidence (individually recorded; NOT required to fire)
------------------------------------------------------------------------
- `value_area_confluence` - the touched pool's zone overlaps the
  current forming period's Value Area (`[value_area_low,
  value_area_high]`) - two independently-computed concepts (a
  price-action liquidity zone, a volume-distribution area) agreeing
  this is a significant region. A structural overlap test, the same
  "two independent methods agree" shape already used by Order Block
  Continuation's `order_block_confluence` and Volume Node Reversal's
  `value_area_confluence` - not a magnitude/threshold invented here.
- `cvd_confirms_trend` - any configured CVD anchor's `cvd_direction`
  (already a discrete, tracker-computed classification - "BULLISH" /
  "BEARISH" / "NEUTRAL" / None - never a raw threshold picked here)
  agrees with the trend direction, i.e. order flow shows continuation
  participation rather than exhaustion at the retest.

Volume Profile's continuous migration fields
(`poc_shift_from_previous_period`, `value_area_overlap_ratio`) are
deliberately NOT used, for the same reason Volume Node Reversal's own
docstring already gives: turning either into a fire condition would
require inventing a cutoff, which this project's standing instruction
not to invent new thresholds/indicators rules out. `value_area_confluence`
above uses the same containment-test shape that field's own tracker
already exposes as a boundary, not a magnitude.

Stop-loss
---------
The touched Liquidity Pool's own zone edge - `zone_low` for LONG (the
level must hold as support), `zone_high` for SHORT (the level must hold
as resistance) - placed into the first required condition's evidence
exactly like every existing zone-based setup, so the existing backtest
adapter needs no changes.

If more than one qualifying pool exists on the same bar (rare, same
class of event as LSR's own simultaneous-sweep case), the first found in
the snapshot's own zone ordering is used - deterministic, not claimed to
be "the best."

Architectural compliance (Step 0 verification)
------------------------------------------------
No tracker, Snapshot, Coordinator, Strategy Engine, or BacktestRunner
change was needed or made. This class is a pure function of the
snapshot it receives - no state carried between calls, per the Setup
protocol. Every field read here already exists in
`MarketIntelligenceSnapshot` exactly as produced by existing trackers.
"""

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot, Zone
from strategy.setups.base import ConditionResult, Setup, SetupResult, Side

_TREND_SIDE = {"BULLISH_BOS": ("LONG", "buy_side"), "BEARISH_BOS": ("SHORT", "sell_side")}


class TrendContinuationConfluenceSetup:
    name = "trend_continuation_confluence"

    def evaluate(self, snapshot: MarketIntelligenceSnapshot) -> SetupResult:
        bos = snapshot.structure.get("bos")
        trend = _TREND_SIDE.get(bos)
        direction: Side | None = trend[0] if trend else None
        pool_side = trend[1] if trend else None

        pool = self._find_pullback_pool(snapshot, pool_side) if pool_side else None

        liquidity_condition = self._liquidity_condition(pool, direction)
        structure_condition = self._structure_condition(bos)

        required = [liquidity_condition, structure_condition]

        if pool is None or direction is None:
            return SetupResult(
                setup_name=self.name,
                fired=False,
                direction=None,
                required_conditions=required,
                additional_evidence=[],
                evidence_count=0,
                reasoning="No qualifying liquidity pool retest under a confirmed structural trend on this bar.",
                symbol=snapshot.symbol,
                timestamp=snapshot.timestamp,
            )

        additional = [
            self._value_area_confluence(snapshot, pool),
            self._cvd_confirms_trend(snapshot, direction),
        ]
        evidence_count = sum(1 for c in additional if c.satisfied)

        fired = all(c.satisfied for c in required)

        return SetupResult(
            setup_name=self.name,
            fired=fired,
            direction=direction if fired else None,
            required_conditions=required,
            additional_evidence=additional,
            evidence_count=evidence_count,
            reasoning=self._build_reasoning(fired, direction, pool, required, additional, evidence_count),
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
        )

    def _find_pullback_pool(self, snapshot: MarketIntelligenceSnapshot, pool_side: str) -> Zone | None:
        candidates = [
            zone for zone in snapshot.zones
            if zone.kind == "liquidity_pool"
            and zone.status == "active"
            and zone.direction == pool_side
            and zone.zone_relative_position == "inside_price"
        ]

        return candidates[0] if candidates else None

    def _liquidity_condition(self, pool: Zone | None, direction: Side | None) -> ConditionResult:
        if pool is None:
            return ConditionResult(
                name="price_inside_active_liquidity_pool",
                satisfied=False,
                detail="no active liquidity pool of the trend-matching side currently contains price",
                evidence={},
            )

        return ConditionResult(
            name="price_inside_active_liquidity_pool",
            satisfied=True,
            detail=(
                f"{pool.direction} liquidity pool [{pool.zone_low:.2f}, {pool.zone_high:.2f}] "
                f"currently contains price ({direction} pullback)"
            ),
            evidence={
                "direction": pool.direction,
                "zone_high": pool.zone_high,
                "zone_low": pool.zone_low,
                "sources": pool.raw.get("sources", []),
            },
        )

    def _structure_condition(self, bos: str | None) -> ConditionResult:
        satisfied = bos in ("BULLISH_BOS", "BEARISH_BOS")

        return ConditionResult(
            name="structural_trend_confirmed",
            satisfied=satisfied,
            detail=f"bos={bos}",
            evidence={"bos": bos},
        )

    def _value_area_confluence(self, snapshot: MarketIntelligenceSnapshot, pool: Zone) -> ConditionResult:
        vah_levels = [lvl for lvl in snapshot.levels if lvl.kind == "vah"]
        val_levels = [lvl for lvl in snapshot.levels if lvl.kind == "val"]

        overlaps = (
            bool(vah_levels) and bool(val_levels)
            and pool.zone_low <= vah_levels[0].price
            and pool.zone_high >= val_levels[0].price
        )

        return ConditionResult(
            name="value_area_confluence",
            satisfied=overlaps,
            detail=(
                f"pool=[{pool.zone_low:.2f}, {pool.zone_high:.2f}] vs value area "
                f"[{val_levels[0].price if val_levels else None}, {vah_levels[0].price if vah_levels else None}]"
            ),
            evidence={
                "pool_zone_low": pool.zone_low,
                "pool_zone_high": pool.zone_high,
                "value_area_low": val_levels[0].price if val_levels else None,
                "value_area_high": vah_levels[0].price if vah_levels else None,
            },
        )

    def _cvd_confirms_trend(self, snapshot: MarketIntelligenceSnapshot, direction: Side) -> ConditionResult:
        target = "BULLISH" if direction == "LONG" else "BEARISH"

        matches = [
            anchor_name for anchor_name, data in snapshot.order_flow.get("cvd", {}).items()
            if data.get("cvd_direction") == target
        ]

        return ConditionResult(
            name="cvd_confirms_trend",
            satisfied=bool(matches),
            detail=(f"confirmed by {matches}" if matches else f"no configured CVD anchor showed {target}"),
            evidence={"matching_anchors": matches, "checked_anchors": list(snapshot.order_flow.get("cvd", {}).keys())},
        )

    def _build_reasoning(
        self,
        fired: bool,
        direction: Side,
        pool: Zone,
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
            f"{direction} - trend continuation confluence. "
            f"{required_summary} "
            f"Additional evidence ({evidence_count}/{len(additional)}): {evidence_summary}."
        )
