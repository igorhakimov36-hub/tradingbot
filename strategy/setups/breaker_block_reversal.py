"""
Breaker Block Reversal - the sixth Strategy Engine V2 setup (S006).

Why "Reversal", not "Continuation" (explained before implementation,
per instruction, not decided by naming preference)
------------------------------------------------------------------------
`strategy/features/breaker_block.py`'s own code and docstring settle
this: a Breaker Block's `direction` field is assigned as
`_opposite(order_block["direction"])` - it is already the POST-FLIP,
forward-looking role, not a continuation of the source Order Block's
original direction. The module's own purpose statement is explicit:
"broken support becomes resistance... a genuine positioning shift at
that level, not noise" - classical technical analysis (Edwards &
Magee), not an ICT-specific reframing. A Breaker Block's entire
institutional premise is that the ORIGINAL move already failed and
reversed at this level. Order Block Continuation (S002) already trades
the "the original impulsive move keeps going" thesis, on the UNBROKEN
version of the same zone. Naming this setup "Continuation" would
misleadingly imply it continues that same original move; it instead
trades confirmation that the original move already ended. "Reversal"
is the institutionally correct name.

A precise structural consequence, not asserted but true by
construction: an Order Block and its eventual Breaker Block are the
SAME tracked zone at mutually exclusive lifecycle stages -
`OrderBlockTracker` only keeps a zone in its `active` list (Order Block
Continuation's tradeable population) while unmitigated; the instant it
becomes `fully_mitigated` it moves to `mitigated` and is immediately
reborn here with flipped polarity (`BreakerBlockTracker._detect_new_breakers`).
The two setups can never compete for the same zone at the same time -
they trade the same underlying zone before and after its one state
transition, never simultaneously.

Institutional logic
--------------------
Once an Order Block fully fails (price fully mitigates it), classical
trapped-trader psychology applies: participants who positioned at the
original zone are now underwater, and their eventual breakeven-exit
flow reinforces the same price level in the OPPOSITE role - a failed
bearish Order Block (resistance) becomes new support; a failed bullish
Order Block (support) becomes new resistance. The FIRST retest of this
newly-flipped zone, while it is still active (not yet itself fully
mitigated a second time), offers a defined re-entry in the Breaker's
own (already-flipped) direction.

Direction
---------
The Breaker Block's own `direction` field, unmodified - "bullish" means
this zone now acts as support (LONG on retest), "bearish" means
resistance (SHORT on retest). No inversion is applied here; the
tracker already did the flip.

Required condition (the only one that gates firing)
--------------------------------------------------------
`active_breaker_block_first_touch` - an ACTIVE Breaker Block zone
(`kind == "breaker_block"`, `status == "active"`) where price is
CURRENTLY inside it (`zone_relative_position == "inside_price"`) and
this is the first touch (`touch_count == 1`). This mirrors Order Block
Continuation's exact required-condition design - not by choice, but
because `BreakerBlock.to_dict()` exposes the identical `touch_count`
field via the same `zone_lifecycle` mechanics Order Blocks use, so the
same freshness reasoning applies unchanged: `touch_count == 1` is the
institutionally strongest read (later retests consume progressively
more of the flipped zone's resting interest), and the engine's own
one-trade-at-a-time behavior prevents re-firing while a position from
an earlier touch is still open.

Why no body-zone (tighter sub-zone) evidence check, unlike Order Block
Continuation: Breaker Blocks do not expose `mitigation_zone_high`/
`mitigation_zone_low` - the Mitigation Block sub-zone fields are
explicitly scoped to Order Blocks only (Phase 1.6: "Breaker Blocks do
not currently get an equivalent tighter sub-zone - the architecture
doc only scopes this to Order Blocks"). Building an analogous check
here would require inventing a sub-zone this tracker does not compute
- not done.

Additional evidence (individually recorded; NOT required to fire)
------------------------------------------------------------------------
Matching every setup's first-version precedent - no confirmation gate
is imposed, since Liquidity Sweep Reversal's own gate was earned
through controlled experimentation specific to that setup:

- `breaker_block_confluence` - another ACTIVE Breaker Block of the SAME
  direction with an overlapping range also exists - the identical
  "independent zones agreeing" shape as Order Block Continuation's
  `order_block_confluence`, applied to this zone kind.
- `overlaps_liquidity_pool` - an active or swept Liquidity Pool zone
  with a DIRECTIONALLY CONSISTENT bias overlaps this Breaker Block's
  range. Liquidity Pools use `buy_side`/`sell_side` (built from highs/
  lows respectively), not `bullish`/`bearish`; the correct mapping is a
  sell_side pool (built from lows, itself support-associated) for a
  bullish (support) Breaker Block, and a buy_side pool (built from
  highs, resistance-associated) for a bearish (resistance) Breaker
  Block - not an arbitrary pairing, but the one that keeps both
  confluence checks pointing at the same structural role. A genuinely
  new cross-family confluence check - no existing setup checks Breaker
  Block x Liquidity Pool agreement.

Stop-loss
---------
The Breaker Block's own zone edge - `zone_low` for LONG, `zone_high`
for SHORT - the level at which the Breaker Block itself would become
fully mitigated a second time, falsifying the "flip held" thesis.
Reuses the *exact* existing adapter code path unmodified, identical to
every setup before it.
"""

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot, Zone
from strategy.setups.base import ConditionResult, Setup, SetupResult, Side


class BreakerBlockReversalSetup:
    name = "breaker_block_reversal"

    def evaluate(self, snapshot: MarketIntelligenceSnapshot) -> SetupResult:
        touched_breaker = self._find_first_touch_breaker(snapshot)

        touch_condition = self._touch_condition(touched_breaker)

        if touched_breaker is None:
            return SetupResult(
                setup_name=self.name,
                fired=False,
                direction=None,
                required_conditions=[touch_condition],
                additional_evidence=[],
                evidence_count=0,
                reasoning="No first-touch active Breaker Block detected on this bar.",
                symbol=snapshot.symbol,
                timestamp=snapshot.timestamp,
            )

        direction: Side = "LONG" if touched_breaker.direction == "bullish" else "SHORT"

        additional = [
            self._breaker_block_confluence(snapshot, touched_breaker),
            self._overlaps_liquidity_pool(snapshot, touched_breaker),
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
            reasoning=self._build_reasoning(fired, direction, touched_breaker, required, additional, evidence_count),
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
        )

    def _find_first_touch_breaker(self, snapshot: MarketIntelligenceSnapshot) -> Zone | None:
        candidates = [
            zone for zone in snapshot.zones
            if zone.kind == "breaker_block"
            and zone.status == "active"
            and zone.zone_relative_position == "inside_price"
            and zone.touch_count == 1
        ]

        return candidates[0] if candidates else None

    def _touch_condition(self, touched_breaker: Zone | None) -> ConditionResult:
        if touched_breaker is None:
            return ConditionResult(
                name="active_breaker_block_first_touch",
                satisfied=False,
                detail="no active, first-touch Breaker Block currently contains price",
                evidence={},
            )

        return ConditionResult(
            name="active_breaker_block_first_touch",
            satisfied=True,
            detail=(
                f"{touched_breaker.direction} Breaker Block [{touched_breaker.zone_low:.2f}, "
                f"{touched_breaker.zone_high:.2f}] touched for the first time"
            ),
            evidence={
                "direction": touched_breaker.direction,
                "zone_high": touched_breaker.zone_high,
                "zone_low": touched_breaker.zone_low,
                "touch_count": touched_breaker.touch_count,
                "source_direction": touched_breaker.raw.get("source_direction"),
            },
        )

    def _breaker_block_confluence(self, snapshot: MarketIntelligenceSnapshot, touched_breaker: Zone) -> ConditionResult:
        overlapping = [
            zone for zone in snapshot.zones
            if zone is not touched_breaker
            and zone.kind == "breaker_block"
            and zone.status == "active"
            and zone.direction == touched_breaker.direction
            and zone.zone_high >= touched_breaker.zone_low
            and zone.zone_low <= touched_breaker.zone_high
        ]

        return ConditionResult(
            name="breaker_block_confluence",
            satisfied=bool(overlapping),
            detail=(
                f"{len(overlapping)} other overlapping {touched_breaker.direction} Breaker Block(s) found"
                if overlapping else "no other overlapping same-direction Breaker Block found"
            ),
            evidence={"overlapping_count": len(overlapping)},
        )

    def _overlaps_liquidity_pool(self, snapshot: MarketIntelligenceSnapshot, touched_breaker: Zone) -> ConditionResult:
        # A bullish (support) Breaker Block is corroborated by a sell-side
        # pool (built from lows, itself support-associated); a bearish
        # (resistance) Breaker Block by a buy-side pool (built from
        # highs, resistance-associated) - matching structural roles, not
        # an arbitrary pairing.
        target_pool_direction = "sell_side" if touched_breaker.direction == "bullish" else "buy_side"

        overlapping = [
            zone for zone in snapshot.zones
            if zone.kind == "liquidity_pool"
            and zone.direction == target_pool_direction
            and zone.zone_high >= touched_breaker.zone_low
            and zone.zone_low <= touched_breaker.zone_high
        ]

        return ConditionResult(
            name="overlaps_liquidity_pool",
            satisfied=bool(overlapping),
            detail=(
                f"{len(overlapping)} overlapping {target_pool_direction} Liquidity Pool(s) found"
                if overlapping else f"no overlapping {target_pool_direction} Liquidity Pool found"
            ),
            evidence={"overlapping_count": len(overlapping), "target_pool_direction": target_pool_direction},
        )

    def _build_reasoning(
        self,
        fired: bool,
        direction: Side,
        touched_breaker: Zone,
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
            f"{direction} - breaker block reversal. "
            f"{required_summary} "
            f"Additional evidence ({evidence_count}/{len(additional)}): {evidence_summary}."
        )
