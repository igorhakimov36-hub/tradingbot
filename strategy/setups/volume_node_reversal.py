"""
Volume Node Reversal - the third Strategy Engine V2 setup.

Why Volume Profile, and why now
---------------------------------
The architectural audit (docs/strategy_engine_v2_audit.md) found Volume
Profile fully computed and mapped into every snapshot (both `snapshot.
levels` - POC/VAH/VAL/HVN/LVN - and the raw `snapshot.volume_profile`
dict) but read by NO existing setup at all - the entire "how volume
distributed across price" family had zero influence on any decision.
Ranked highest-priority remaining module per the audit's own criteria:
richest still-unused signal, and - critically - ZERO mechanical overlap
with either existing setup. Liquidity Sweep Reversal reads Zones
(liquidity pools) + Order Flow (CVD) + Structure (CHOCH). Order Block
Continuation reads Zones (order blocks) only. Neither has ever touched
`snapshot.levels` or `snapshot.volume_profile` - this setup is the
first to do so, guaranteeing it measures genuinely new information
rather than a repackaging of an existing read.

Why High Volume Nodes, not Low Volume Nodes or cross-period migration
----------------------------------------------------------------------
Volume Profile exposes three distinct institutional readings, and only
one was chosen:
1. High Volume Node (HVN) reaction (chosen here) - a price shelf where
   the market spent disproportionate time/volume is standard auction-
   market-theory support/resistance: heavy prior two-sided acceptance
   at a level tends to produce a reaction (stall or reverse) on retest,
   not a clean pass-through.
2. Low Volume Node (LVN) - the OPPOSITE institutional reading (a level
   the market spent little time at acts as a "void," and price
   typically ACCELERATES through it rather than reacting). Combining
   both HVN-reversal and LVN-continuation into one setup would mean two
   setups wearing one name with opposite theses picked by which node
   type happened to be nearest - not built here to keep this setup's
   institutional logic singular and testable in isolation. LVN
   Continuation is a legitimate, independent future setup candidate,
   not implemented in this pass.
3. Cross-period Value Area migration/acceptance (`poc_shift_from_
   previous_period`, `value_area_overlap_ratio`) - the tracker's own
   docstring frames these as "a high overlap ratio reads as acceptance,
   a low one as rejection/migration," but both are CONTINUOUS scores
   with no tracker-asserted threshold. Building a fire condition on
   them would require inventing a cutoff (e.g. "overlap < 0.3"), which
   the instruction not to invent new thresholds/indicators rules out.
   HVN reaction needed no such invention (see below).

Institutional logic
--------------------
A High Volume Node above the current period's Point of Control (POC)
represents a shelf of heavy prior acceptance ABOVE fair value - price
rallying up into it from below is testing prior resistance, with a
reversal-down thesis. A High Volume Node BELOW the POC is the mirror -
prior acceptance below fair value acting as support on a decline from
above, with a reversal-up thesis. A node AT the POC itself has no such
directional read (the POC IS current fair value, not a secondary
shelf) and is excluded from candidacy.

Required condition (the only one that gates firing)
--------------------------------------------------------
`price_at_high_volume_node` - CURRENT price falls inside the SAME price
bucket as an HVN node of the CURRENT FORMING profile (`node.price <=
current_price < node.price + bucket_size`), where `bucket_size` is the
tracker's own fixed histogram resolution (Volume Profile's own
fundamental unit, not a tolerance invented here), and the node's price
differs from the current POC (direction would otherwise be undefined).

Why "same bucket" rather than an invented distance tolerance: Zones
(Liquidity Pools, Order Blocks) already carry a real, tracker-computed
width (zone_high/zone_low) to test against. A Level (HVN included) is a
single price with no such width of its own - `bucket_size` is the one
already-computed unit of resolution this tracker exposes, so "same
bucket" is the only "at this level" test available without picking an
arbitrary buffer.

Known re-fire characteristic (documented, not treated as a defect):
unlike Order Block Continuation's `touch_count == 1`, there is no
per-node "first touch only" concept here - a node can be legitimately
retested multiple times across separate visits, and each qualifying
bar is evaluated independently. This mirrors Liquidity Sweep Reversal's
own accepted behavior (a new pool can form near a similar level and be
swept again later) rather than being a newly introduced gap; the
backtest's own one-trade-at-a-time constraint already prevents any
double-counting while a position from an earlier touch is still open.

Additional evidence (individually recorded; NOT required to fire)
------------------------------------------------------------------------
Matching Order Block Continuation's precedent for a first-version
setup: no confirmation gate is imposed here, since Liquidity Sweep
Reversal's own "require >=1 confirmation" rule was earned through
controlled experimentation specific to that setup, not assumed
transferable.

- `node_is_wide` - the touched node's own `width` (a plateau measure
  already computed by the tracker) spans more than a single bucket -
  the same "more than the bare minimum count" pattern already used by
  Liquidity Sweep Reversal's `pool_has_multiple_sources`
  (`len(sources) > 1`), not a new continuous threshold.
- `value_area_confluence` - the touched node also falls within the
  CURRENT period's own Value Area (between VAL and VAH) - two
  independently-computed Volume Profile concepts (a node and the Value
  Area) agreeing this is a significant region, the same "independent
  confirmation" shape as Order Block Continuation's `order_block_
  confluence`.

Stop-loss
---------
The node's own already-computed span, reusing `width` and
`bucket_size` exactly as given (no invented percentage): for a
support read (LONG), the invalidation floor is one full node-width
below the node's own bucket; for a resistance read (SHORT), the
invalidation ceiling is one full node-width above it. Placed into the
required condition's evidence as `zone_low`/`zone_high` - the exact
same keys Liquidity Sweep Reversal and Order Block Continuation already
use, so the existing backtest adapter needs no changes at all to place
this setup's stop correctly.
"""

from strategy.market_intelligence_snapshot import Level, MarketIntelligenceSnapshot
from strategy.setups.base import ConditionResult, Setup, SetupResult, Side


class VolumeNodeReversalSetup:
    name = "volume_node_reversal"

    def evaluate(self, snapshot: MarketIntelligenceSnapshot) -> SetupResult:
        touched_node, poc_price, bucket_size = self._find_touched_node(snapshot)

        touch_condition = self._touch_condition(touched_node, poc_price, bucket_size)

        if touched_node is None:
            return SetupResult(
                setup_name=self.name,
                fired=False,
                direction=None,
                required_conditions=[touch_condition],
                additional_evidence=[],
                evidence_count=0,
                reasoning="No High Volume Node currently touched by price on this bar.",
                symbol=snapshot.symbol,
                timestamp=snapshot.timestamp,
            )

        direction: Side = "SHORT" if touched_node.price > poc_price else "LONG"

        additional = [
            self._node_is_wide(touched_node),
            self._value_area_confluence(snapshot, touched_node),
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
            reasoning=self._build_reasoning(fired, direction, touched_node, required, additional, evidence_count),
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
        )

    def _find_touched_node(
        self, snapshot: MarketIntelligenceSnapshot
    ) -> tuple[Level | None, float | None, float | None]:
        poc_levels = [lvl for lvl in snapshot.levels if lvl.kind == "poc"]
        poc_price = poc_levels[0].price if poc_levels else None

        current_profile = snapshot.volume_profile.get("current_forming_profile") or {}
        bucket_size = current_profile.get("bucket_size")

        if poc_price is None or not bucket_size:
            return None, poc_price, bucket_size

        candidates = [
            lvl for lvl in snapshot.levels
            if lvl.kind == "hvn"
            and lvl.price != poc_price
            and lvl.price <= snapshot.current_price < lvl.price + bucket_size
        ]

        return (candidates[0] if candidates else None), poc_price, bucket_size

    def _touch_condition(
        self, touched_node: Level | None, poc_price: float | None, bucket_size: float | None
    ) -> ConditionResult:
        if touched_node is None:
            return ConditionResult(
                name="price_at_high_volume_node",
                satisfied=False,
                detail="no High Volume Node currently contains price",
                evidence={},
            )

        width = touched_node.raw.get("width", 1)
        is_resistance = touched_node.price > poc_price

        if is_resistance:
            zone_low = touched_node.price
            zone_high = touched_node.price + bucket_size + (width * bucket_size)
        else:
            zone_low = touched_node.price - (width * bucket_size)
            zone_high = touched_node.price + bucket_size

        return ConditionResult(
            name="price_at_high_volume_node",
            satisfied=True,
            detail=(
                f"HVN at {touched_node.price:.2f} (width={width}) touched, "
                f"{'above' if is_resistance else 'below'} POC={poc_price:.2f}"
            ),
            evidence={
                "node_price": touched_node.price,
                "poc_price": poc_price,
                "width": width,
                "zone_high": zone_high,
                "zone_low": zone_low,
            },
        )

    def _node_is_wide(self, touched_node: Level) -> ConditionResult:
        width = touched_node.raw.get("width", 1)

        return ConditionResult(
            name="node_is_wide",
            satisfied=width > 1,
            detail=f"node width={width}",
            evidence={"width": width},
        )

    def _value_area_confluence(self, snapshot: MarketIntelligenceSnapshot, touched_node: Level) -> ConditionResult:
        vah_levels = [lvl for lvl in snapshot.levels if lvl.kind == "vah"]
        val_levels = [lvl for lvl in snapshot.levels if lvl.kind == "val"]

        inside_value_area = (
            bool(vah_levels) and bool(val_levels)
            and val_levels[0].price <= touched_node.price <= vah_levels[0].price
        )

        return ConditionResult(
            name="value_area_confluence",
            satisfied=inside_value_area,
            detail=(
                f"node_price={touched_node.price:.2f} vs value area "
                f"[{val_levels[0].price if val_levels else None}, {vah_levels[0].price if vah_levels else None}]"
            ),
            evidence={
                "node_price": touched_node.price,
                "value_area_low": val_levels[0].price if val_levels else None,
                "value_area_high": vah_levels[0].price if vah_levels else None,
            },
        )

    def _build_reasoning(
        self,
        fired: bool,
        direction: Side,
        touched_node: Level,
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
            f"{direction} - volume node reversal. "
            f"{required_summary} "
            f"Additional evidence ({evidence_count}/{len(additional)}): {evidence_summary}."
        )
