"""
S009 - Failed Auction Reversal at the Value Area Boundary. Research-only
candidate, SOL Multi-Module Setup Discovery sprint. Frozen design:
docs/sol_multi_module_setup_research_protocol.md, Candidate 2.

Deliberate, disclosed deviation from the plain stateless Setup protocol
------------------------------------------------------------------------
strategy/setups/base.py's own Setup Protocol requires "no internal
state carried between calls." This hypothesis is inherently a 2-bar
pattern (bar N's failed excursion, bar N+1's own delta_strength
compared against bar N's) - Delta (strategy/features/delta.py)
exposes ONLY the single most-recently-CLOSED bar's own value, with no
history, so a pure function of ONE snapshot cannot compare two bars.
This class therefore carries a small, explicit piece of state
(`self._pending`: the most recent still-open bar-N candidate, if any)
across sequential evaluate() calls WITHIN one continuous replay run -
not disguised as stateless, not keyed by id(trade) or any object
identity (no trade exists yet at this point), and never touching
trade-level state at all.

State-isolation guarantee (audited pattern applied here)
------------------------------------------------------------------------
The risk this sprint's own state-isolation audit exists to catch is
state LEAKING ACROSS RUNS or across unrelated objects via a stale
identity-based key. This class has no identity-keyed lookup at all
(there is exactly one `self._pending` slot, not a dict keyed by
id(candle) or id(trade)) - so the id()-reuse defect class does not
apply here by construction. The guarantee this class DOES need, and
provides: a FRESH instance must be constructed for every new backtest
run (exactly the same discipline already audited for
StaircaseExitPolicy/StructureBasedTrailExitPolicy - one instance per
run, never reused across months) - verified directly by
tests/test_s009_failed_auction_reversal.py's own state-isolation test.
Only one bar-N candidate is ever held pending; a new bar-N excursion
overwrites any prior unresolved one (the frozen protocol's own
single-bar-forward-only window - no multi-bar carry beyond N+1).

Hypothesis: an excursion beyond the current period's Value Area that
fails within the same bar (closes back inside), followed by a next bar
showing WEAKER participation on the excursion than the reversal
(delta_strength), is evidence the range extension lacked real
transactional support.
"""

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot
from strategy.setups.base import ConditionResult, Setup, SetupResult, Side


class S009FailedAuctionReversalSetup:
    """
    require_confirmation (default True, the frozen/production
    behavior): when False, weaker_participation_confirms_reversal is
    still computed and reported (additional_evidence), but does not
    gate firing - a predeclared ablation variant (frozen protocol
    Section 5's own "trigger alone" comparison), added to complete the
    interaction analysis, not a new candidate design. Setup parameters
    (thresholds, timing) are unchanged either way.
    """

    name = "s009_failed_auction_reversal"

    def __init__(self, require_confirmation: bool = True) -> None:
        self._pending: dict | None = None
        self._require_confirmation = require_confirmation

    def evaluate(self, snapshot: MarketIntelligenceSnapshot) -> SetupResult:
        result = self._check_trigger(snapshot)
        self._update_pending(snapshot)
        return result

    def _check_trigger(self, snapshot: MarketIntelligenceSnapshot) -> SetupResult:
        pending = self._pending

        if pending is None:
            return self._no_fire(snapshot, "no pending failed-excursion candidate from the prior bar")

        direction: Side = pending["direction"]
        current_delta = self._current_delta_strength(snapshot)

        # "closes further in the reversal direction" is evaluated against
        # bar N's own close (the failed-excursion bar's close, already
        # recorded when the candidate was captured).
        closed_further = (
            snapshot.current_price < pending["excursion_bar_close"] if direction == "SHORT"
            else snapshot.current_price > pending["excursion_bar_close"]
        )

        delta_condition = ConditionResult(
            name="weaker_participation_confirms_reversal",
            satisfied=current_delta is not None and pending["excursion_delta_strength"] is not None
            and current_delta > pending["excursion_delta_strength"],
            detail=f"bar_N+1 delta_strength={current_delta} vs bar_N delta_strength={pending['excursion_delta_strength']}",
            evidence={"current_delta_strength": current_delta, "excursion_delta_strength": pending["excursion_delta_strength"]},
        )
        progress_condition = ConditionResult(
            name="closed_further_in_reversal_direction",
            satisfied=closed_further,
            detail=f"current_price={snapshot.current_price:.2f} vs excursion bar close={pending['excursion_bar_close']:.2f}",
            evidence={"current_price": snapshot.current_price, "excursion_bar_close": pending["excursion_bar_close"]},
        )

        if self._require_confirmation:
            required = [progress_condition, delta_condition]
            additional = []
        else:
            required = [progress_condition]
            additional = [delta_condition]
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

    def _update_pending(self, snapshot: MarketIntelligenceSnapshot) -> None:
        # A new bar-N candidate always overwrites any prior unresolved
        # one - the frozen protocol's single-bar-forward-only window.
        profile = snapshot.volume_profile.get("current_forming_profile")
        if profile is None:
            self._pending = None
            return

        va_high = profile.get("value_area_high")
        va_low = profile.get("value_area_low")
        # This bar's own high/low are not exposed on the Snapshot
        # directly (Zones/Levels are the point-in-time-safe surface) -
        # current_price is the bar's own close, the only per-bar price
        # this Setup protocol exposes; the excursion condition is
        # therefore evaluated on CLOSE vs Value Area boundary (a
        # same-bar close-beyond-then-still-inside pattern is not
        # observable from Snapshot alone) - disclosed narrowing of the
        # frozen design's own "bar N's high/low" language to what the
        # Snapshot interface actually exposes; recorded as a limitation
        # in the delivered report, not silently substituted.
        if va_high is not None and snapshot.current_price > va_high:
            self._pending = {
                "direction": "SHORT",
                "excursion_bar_close": snapshot.current_price,
                "excursion_delta_strength": self._current_delta_strength(snapshot),
            }
        elif va_low is not None and snapshot.current_price < va_low:
            self._pending = {
                "direction": "LONG",
                "excursion_bar_close": snapshot.current_price,
                "excursion_delta_strength": self._current_delta_strength(snapshot),
            }
        else:
            self._pending = None

    def _current_delta_strength(self, snapshot: MarketIntelligenceSnapshot) -> float | None:
        delta = snapshot.order_flow.get("delta", {})
        return delta.get("delta_strength")

    def _no_fire(self, snapshot: MarketIntelligenceSnapshot, reason: str) -> SetupResult:
        return SetupResult(
            setup_name=self.name,
            fired=False,
            direction=None,
            required_conditions=[ConditionResult(name="pending_excursion_exists", satisfied=False, detail=reason, evidence={})],
            additional_evidence=[],
            evidence_count=0,
            reasoning=f"Did not fire - {reason}.",
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
        )

    def _build_reasoning(self, fired: bool, direction: Side, required: list[ConditionResult]) -> str:
        if not fired:
            failed = [c.name for c in required if not c.satisfied]
            return f"Did not fire - failed required condition(s): {', '.join(failed)}."
        required_summary = " ".join(f"Required: {c.detail}." for c in required)
        return f"{direction} - failed auction reversal. {required_summary}"
