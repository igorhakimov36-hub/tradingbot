"""
Order Block Continuation - the second Strategy Engine V2 setup (Phase
2, second-setup work).

Why "Continuation", not "Reversal"
------------------------------------
Order Blocks (strategy/features/order_block.py) mark the last opposing-
direction candle before an impulsive break of structure - the module's
own docstring frames a retest of this zone as "a better-defined,
better-risk re-entry" into the SAME direction that created the move,
not a signal that the move has failed. A "the block failed, treat it
as resistance/support flipping" interpretation is already a separate,
already-built concept - that is exactly what Breaker Blocks are
(an Order Block that got fully mitigated and is re-exposed with flipped
polarity). Building an "Order Block Reversal" setup here would
duplicate Breaker Blocks' own thesis under a different name, not add
new information. Continuation is the one reading that does not
overlap an existing module.

Why this setup deliberately reads ONLY Order Block data
------------------------------------------------------------
Liquidity Sweep Reversal requires genuine agreement across three
Market Intelligence families (Zones, Order Flow, Structure) - a
deliberate design choice for THAT setup, to demonstrate the full
Snapshot architecture. This setup does the opposite on purpose: every
required condition and every piece of additional evidence comes from
Order Block zones alone (kind == "order_block" in the snapshot's
`zones` list - no CVD, no CHOCH, no SMT, no other Zone kind). The goal
stated for this work is to measure the STANDALONE predictive power of
one Market Intelligence module, not to build the richest possible
setup - mixing in confirmation from other modules would make it
impossible to attribute a later backtest's results to Order Blocks
specifically.

Institutional logic
--------------------
An Order Block records the last opposing-direction candle before an
impulsive break of structure - the zone where the participants who
caused that move are believed to have last transacted. Price returning
to this zone for the FIRST time (touch_count == 1 - see below) offers
a defined, better-risk re-entry into the same direction that produced
the original break, before any of the block's remaining resting
interest has been consumed by repeated visits.

Direction
---------
A bullish Order Block (origin was the last down-candle before an
upward break) sits below price and acts as support on retest - a LONG
setup. A bearish Order Block (origin was the last up-candle before a
downward break) sits above price and acts as resistance on retest - a
SHORT setup. This is the tracker's own `direction` field, unmodified.

Required conditions (the only one that gates firing)
--------------------------------------------------------
1. `active_order_block_first_touch` - an ACTIVE (not yet fully
   mitigated) Order Block zone where price is CURRENTLY inside the
   zone (`zone_relative_position == "inside_price"`, itself always
   computed fresh from the CURRENT bar's price by the Snapshot Builder)
   AND this is the first time it has ever been touched
   (`touch_count == 1`).

Why `touch_count == 1` instead of an explicit this-bar freshness
timestamp (unlike Liquidity Sweep Reversal's `resolved_at ==
snapshot.timestamp`): Liquidity Pools move to a permanently "resolved/
swept" list once swept, so without a same-bar freshness check that
setup would fire on every subsequent bar forever. Order Block zones
behave differently - `zone_relative_position` is recomputed fresh from
the CURRENT price on every call and is only "inside_price" while price
actually sits in the zone right now; it naturally reverts to false the
moment price exits, with no permanent-truth risk to guard against.
What DOES need guarding is a zone being retested multiple times
(second, third visit) without limit - `touch_count == 1` restricts
this setup to the FIRST touch only, which is also the institutionally
strongest read (later retests consume progressively more of the
block's resting interest and are considered weaker, not stronger,
in ICT re-entry theory). Combined with the backtest engine's own
one-trade-at-a-time constraint (a fired first touch opens/queues a
trade, so the same lingering touch cannot re-ask the strategy for a
decision on its very next bar), no additional bar-level de-duplication
is needed here.

Additional evidence (individually recorded; NOT required to fire)
------------------------------------------------------------------------
Unlike Liquidity Sweep Reversal's current (permanent, post-experiment)
form, this setup does NOT yet require any additional confirmation -
this is this setup's first version, and gating on "at least one
additional confirmation" the way Liquidity Sweep Reversal now does was
itself earned there through controlled, measured experimentation (see
that module's own docstring), not assumed. Copying that exact rule
onto a structurally different setup without equivalent evidence would
be importing an untested assumption, not applying a validated one.
Both checks below are recorded on every fire, for future controlled-
experiment candidates:

- `body_zone_confirms_precision` - price is not merely inside the
  outer wick-based zone but ALSO inside the tighter, body-based
  mitigation sub-zone (`mitigation_zone_high`/`mitigation_zone_low` -
  Order Block's own Mitigation Block fields, see that module's
  docstring: "a return into the body is a stricter, more selective
  re-entry signal than a return anywhere into the wick range").
- `order_block_confluence` - another ACTIVE Order Block of the SAME
  direction, with an overlapping price range, also currently exists -
  multiple independent institutional footprints reinforcing the same
  level, rather than one isolated zone.

`evidence_count` is a raw count of the two above - descriptive
statistics for the Trade Journal, exactly the same spirit as every
other setup in this package, never a weight and never (yet) a gate.

If more than one Order Block qualifies on the same bar (rare), the
first one found in the snapshot's own zone ordering is used -
deterministic, matching Liquidity Sweep Reversal's identical policy
for simultaneous sweeps.
"""

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot, Zone
from strategy.setups.base import ConditionResult, Setup, SetupResult, Side


class OrderBlockContinuationSetup:
    name = "order_block_continuation"

    def evaluate(self, snapshot: MarketIntelligenceSnapshot) -> SetupResult:
        touched_block = self._find_first_touch_order_block(snapshot)

        touch_condition = self._touch_condition(touched_block)

        if touched_block is None:
            return SetupResult(
                setup_name=self.name,
                fired=False,
                direction=None,
                required_conditions=[touch_condition],
                additional_evidence=[],
                evidence_count=0,
                reasoning="No first-touch active Order Block detected on this bar.",
                symbol=snapshot.symbol,
                timestamp=snapshot.timestamp,
            )

        direction: Side = "LONG" if touched_block.direction == "bullish" else "SHORT"

        additional = [
            self._body_zone_confirms(snapshot, touched_block),
            self._order_block_confluence(snapshot, touched_block),
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
            reasoning=self._build_reasoning(fired, direction, touched_block, required, additional, evidence_count),
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
        )

    def _find_first_touch_order_block(self, snapshot: MarketIntelligenceSnapshot) -> Zone | None:
        candidates = [
            zone for zone in snapshot.zones
            if zone.kind == "order_block"
            and zone.status == "active"
            and zone.zone_relative_position == "inside_price"
            and zone.touch_count == 1
        ]

        return candidates[0] if candidates else None

    def _touch_condition(self, touched_block: Zone | None) -> ConditionResult:
        if touched_block is None:
            return ConditionResult(
                name="active_order_block_first_touch",
                satisfied=False,
                detail="no active, first-touch Order Block currently contains price",
                evidence={},
            )

        return ConditionResult(
            name="active_order_block_first_touch",
            satisfied=True,
            detail=(
                f"{touched_block.direction} Order Block [{touched_block.zone_low:.2f}, "
                f"{touched_block.zone_high:.2f}] touched for the first time"
            ),
            evidence={
                "direction": touched_block.direction,
                "zone_high": touched_block.zone_high,
                "zone_low": touched_block.zone_low,
                "touch_count": touched_block.touch_count,
            },
        )

    def _body_zone_confirms(self, snapshot: MarketIntelligenceSnapshot, touched_block: Zone) -> ConditionResult:
        mitigation_zone_high = touched_block.raw.get("mitigation_zone_high")
        mitigation_zone_low = touched_block.raw.get("mitigation_zone_low")

        inside_body = (
            mitigation_zone_high is not None
            and mitigation_zone_low is not None
            and mitigation_zone_low <= snapshot.current_price <= mitigation_zone_high
        )

        return ConditionResult(
            name="body_zone_confirms_precision",
            satisfied=inside_body,
            detail=(
                f"current_price={snapshot.current_price:.2f} vs body zone "
                f"[{mitigation_zone_low}, {mitigation_zone_high}]"
            ),
            evidence={
                "current_price": snapshot.current_price,
                "mitigation_zone_high": mitigation_zone_high,
                "mitigation_zone_low": mitigation_zone_low,
            },
        )

    def _order_block_confluence(self, snapshot: MarketIntelligenceSnapshot, touched_block: Zone) -> ConditionResult:
        overlapping = [
            zone for zone in snapshot.zones
            if zone is not touched_block
            and zone.kind == "order_block"
            and zone.status == "active"
            and zone.direction == touched_block.direction
            and zone.zone_high >= touched_block.zone_low
            and zone.zone_low <= touched_block.zone_high
        ]

        return ConditionResult(
            name="order_block_confluence",
            satisfied=bool(overlapping),
            detail=(
                f"{len(overlapping)} other overlapping {touched_block.direction} Order Block(s) found"
                if overlapping else "no other overlapping same-direction Order Block found"
            ),
            evidence={"overlapping_count": len(overlapping)},
        )

    def _build_reasoning(
        self,
        fired: bool,
        direction: Side,
        touched_block: Zone,
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
            f"{direction} - order block continuation. "
            f"{required_summary} "
            f"Additional evidence ({evidence_count}/{len(additional)}): {evidence_summary}."
        )
