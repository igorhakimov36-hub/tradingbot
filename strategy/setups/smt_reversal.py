"""
SMT Reversal - the fourth Strategy Engine V2 setup.

Why Correlation Engine / SMT, and why now
--------------------------------------------
Every existing setup (Liquidity Sweep Reversal, Order Block
Continuation, Volume Node Reversal) is derived entirely from BTCUSDT's
own OHLCV - three different readings of the same single market. The
Intermarket family (`snapshot.intermarket`) is the one Market
Intelligence family none of them treats as a primary signal - Liquidity
Sweep Reversal reads it only as one of three OPTIONAL additional-
evidence checks (`smt_confirms_direction`), never required, and the
other two setups never touch it at all. Before this setup, the entire
Correlation Engine (a second market's own structural read) contributed
at most a tie-breaking vote to one setup's confirmation count - this is
the first setup for which it is the PRIMARY, required signal.

The earlier architectural audit ranked Correlation Engine/SMT below
Fair Value Gaps specifically because of integration cost ("the most
expensive to actually test... real Coordinator work, not just a setup
change"). That cost no longer applies - Step 0 already instantiated
`CorrelationTracker` inside `MarketIntelligenceCoordinator` and
validated it end-to-end on real BTCUSDT/ETHUSDT data (190 genuine
structural divergence events over 30 real days, byte-identical
batched-vs-incremental replay, deterministic). With the integration
cost already paid, SMT is the lowest-overlap, highest-diversification
option remaining: it is the only unused *family*, not merely an unused
module within an already-heavily-used family (Fair Value Gaps and
Breaker Blocks both share Zones with Order Block Continuation and, for
Breaker Blocks, the audit already flagged near-mechanical identity with
Order Blocks - "likely correlated, not additive").

Institutional logic - what "SMT" actually is here
------------------------------------------------------
Per `strategy/features/correlation.py`'s own extensive documentation:
"SMT" (Smart Money Technique / Divergence) is not a separate detector -
it IS `structural_divergence_flag`/`structural_divergence_history`,
applied to a pair of symbols believed to share risk exposure (here,
BTCUSDT vs ETHUSDT, the one pair with real validated data). When the
PRIMARY symbol confirms a new swing pivot that the REFERENCE symbol
fails to confirm with a matching pivot, that failure-to-confirm is read
as smart money moving the primary asset without genuine broad
conviction across the correlated pair - a classic reversal signal at
that swing extreme. This setup reuses that already-computed field
completely unmodified.

Direction
---------
`bullish_divergence` (primary made a new lower low the reference did
NOT confirm) -> LONG. `bearish_divergence` (primary made a new higher
high the reference did NOT confirm) -> SHORT. The tracker's own field
naming, unchanged.

Required condition (the only one that gates firing)
--------------------------------------------------------
`intermarket_divergence_this_bar` - some configured intermarket pair's
MOST RECENT recorded divergence event
(`structural_divergence_history[-1]`) has a timestamp equal to the
current snapshot's timestamp - i.e. the divergence was confirmed on
THIS bar, not some earlier bar still sitting in `structural_divergence_
flag`'s sticky current value.

Why freshness via `structural_divergence_history` rather than the
sticky `structural_divergence_flag` (the same reasoning shape as
Liquidity Sweep Reversal's `resolved_at == snapshot.timestamp`):
`_divergence_flag` is only updated on bars where the PRIMARY stream
confirms a new swing pivot, and otherwise holds its last value
untouched - reading it directly would make this setup fire on every
bar for as long as multiple bars pass before the next primary pivot,
not just the bar the divergence actually occurred on. `structural_
divergence_history` instead carries the real timestamp of each past
event, giving this setup the same same-bar freshness guarantee
Liquidity Sweep Reversal already established for an analogous
"sticky-flag" risk on Liquidity Pools.

Additional evidence (individually recorded; NOT required to fire)
------------------------------------------------------------------------
Matching Order Block Continuation's and Volume Node Reversal's
precedent for a first-version setup - no confirmation gate is imposed,
since Liquidity Sweep Reversal's own gate was earned through controlled
experimentation specific to that setup. Both checks below are
categorical/sign-based, reusing only already-computed fields - no
continuous threshold was invented:

- `overall_structural_agreement_diverging` - the pair's own `structural_
  agreement` field (a categorical read of BOTH streams' overall
  recent-pivot trend, not just this one event) also currently reads
  "diverging" - independent confirmation from the same tracker's
  broader-context field, the same "two independently-computed facts
  agreeing" shape as Order Block Continuation's `order_block_
  confluence`.
- `pair_is_positively_correlated` - the pair's rolling `price_
  correlation` is positive. A divergence between two assets that are
  not even generally correlated is far less informative than one
  between two assets that normally move together - this is a SIGN
  check (positive vs non-positive), not a magnitude threshold.

Stop-loss
---------
The triggering swing pivot's own price (`primary_price` from the
matched `DivergenceEvent`) as the invalidation edge - if price re-
breaks the very extreme that supposedly wasn't confirmed by the
reference asset, the divergence thesis is falsified. For a bullish
divergence (LONG), that pivot was a LOW: placed as `zone_low` (the
current snapshot price becomes `zone_high`, unused by the adapter for
a LONG decision but kept for schema consistency). For a bearish
divergence (SHORT), the pivot was a HIGH: placed as `zone_high` (current
price becomes `zone_low`). Reuses the *exact* existing adapter code
path unmodified - both prices used here are already-known values (the
tracker's own recorded pivot price, and the current bar's own price),
no invented buffer beyond the adapter's own existing `STOP_BUFFER_PCT`.

Known, disclosed limitation
------------------------------
Only one intermarket pair (`btc_eth`) has ever been validated against
real data (Step 0). This setup's logic is pair-agnostic - it iterates
whatever pairs `snapshot.intermarket` happens to contain - but its
measured real-data behavior in this report reflects BTC/ETH only, not
a claim about any other pair (BTC/TOTAL3, BTC.D, etc.) ever working the
same way.
"""

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot
from strategy.setups.base import ConditionResult, Setup, SetupResult, Side


class SmtReversalSetup:
    name = "smt_reversal"

    def evaluate(self, snapshot: MarketIntelligenceSnapshot) -> SetupResult:
        divergence, pair_name = self._find_fresh_divergence(snapshot)

        divergence_condition = self._divergence_condition(snapshot, divergence, pair_name)

        if divergence is None:
            return SetupResult(
                setup_name=self.name,
                fired=False,
                direction=None,
                required_conditions=[divergence_condition],
                additional_evidence=[],
                evidence_count=0,
                reasoning="No intermarket structural divergence confirmed on this bar.",
                symbol=snapshot.symbol,
                timestamp=snapshot.timestamp,
            )

        direction: Side = "LONG" if divergence["direction"] == "bullish_divergence" else "SHORT"

        pair_data = snapshot.intermarket[pair_name]
        additional = [
            self._structural_agreement_confirms(pair_data),
            self._pair_positively_correlated(pair_data),
        ]
        evidence_count = sum(1 for c in additional if c.satisfied)

        required = [divergence_condition]
        fired = all(c.satisfied for c in required)

        return SetupResult(
            setup_name=self.name,
            fired=fired,
            direction=direction if fired else None,
            required_conditions=required,
            additional_evidence=additional,
            evidence_count=evidence_count,
            reasoning=self._build_reasoning(fired, direction, pair_name, required, additional, evidence_count),
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
        )

    def _find_fresh_divergence(self, snapshot: MarketIntelligenceSnapshot):
        for pair_name, pair_data in snapshot.intermarket.items():
            history = pair_data.get("structural_divergence_history") or []

            if history and history[-1]["timestamp"] == snapshot.timestamp:
                return history[-1], pair_name

        return None, None

    def _divergence_condition(self, snapshot: MarketIntelligenceSnapshot, divergence, pair_name) -> ConditionResult:
        if divergence is None:
            return ConditionResult(
                name="intermarket_divergence_this_bar",
                satisfied=False,
                detail="no configured intermarket pair recorded a fresh structural divergence on this bar",
                evidence={},
            )

        primary_price = divergence["primary_price"]
        current_price = snapshot.current_price
        is_bearish = divergence["direction"] == "bearish_divergence"

        if is_bearish:
            zone_high = primary_price
            zone_low = current_price
        else:
            zone_low = primary_price
            zone_high = current_price

        return ConditionResult(
            name="intermarket_divergence_this_bar",
            satisfied=True,
            detail=(
                f"{divergence['direction']} confirmed on pair '{pair_name}' "
                f"(primary_price={primary_price:.2f}, reference_price={divergence['reference_price']:.2f})"
            ),
            evidence={
                "pair_name": pair_name,
                "direction": divergence["direction"],
                "primary_price": primary_price,
                "reference_price": divergence["reference_price"],
                "zone_high": zone_high,
                "zone_low": zone_low,
            },
        )

    def _structural_agreement_confirms(self, pair_data) -> ConditionResult:
        agreement = pair_data.get("structural_agreement")

        return ConditionResult(
            name="overall_structural_agreement_diverging",
            satisfied=agreement == "diverging",
            detail=f"structural_agreement={agreement}",
            evidence={"structural_agreement": agreement},
        )

    def _pair_positively_correlated(self, pair_data) -> ConditionResult:
        correlation = pair_data.get("price_correlation")
        satisfied = correlation is not None and correlation > 0

        return ConditionResult(
            name="pair_is_positively_correlated",
            satisfied=satisfied,
            detail=f"price_correlation={correlation}",
            evidence={"price_correlation": correlation},
        )

    def _build_reasoning(
        self,
        fired: bool,
        direction: Side,
        pair_name: str,
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
            f"{direction} - SMT reversal ({pair_name}). "
            f"{required_summary} "
            f"Additional evidence ({evidence_count}/{len(additional)}): {evidence_summary}."
        )
