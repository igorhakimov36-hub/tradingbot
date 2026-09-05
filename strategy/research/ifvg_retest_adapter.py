"""
IFVG + Retest research integration - SOL Multi-Module follow-up sprint.

Why this is NOT a plain Setup
------------------------------
Every production Setup reads ONLY a MarketIntelligenceSnapshot
(strategy/setups/base.py's own protocol). Confirmed inversion/retest
state does not exist anywhere in that Snapshot today - the production
MarketIntelligenceCoordinator constructs its own FairValueGapTracker
with track_inversions/track_retests at their default False (preserved,
unchanged, per this sprint's own explicit boundary) - so a Setup
literally cannot obtain this information from evaluate(snapshot)
alone, no matter how it is structured. This module is therefore a
standalone strategy_callback/trade_setup_callback pair - the exact
same shape strategy_engine_v2_backtest_adapter.py and
strategy.research.multi_module_backtest_adapter already use for
S001/S008/S009/S011 - not a new architectural pattern.

It owns a SEPARATE FairValueGapTracker instance (track_inversions=True,
track_retests=True), fed the identical 15m candle stream the
production coordinator already receives via market_snapshot. This is
a second, independent instance of an already-existing, already-tested
tracker - no detection logic is duplicated or reimplemented; only the
opt-in flags already built in the implementation sprint are turned on.

Stable event identity
----------------------
A FairValueGap carries no explicit id. `_gap_key` uses
(direction, zone_high, zone_low, created_at) - the same
composite-key-with-creation-timestamp pattern already established for
Breaker Block (strategy/features/breaker_block.py's own `_source_key`),
chosen for the identical reason: boundaries alone are not guaranteed
unique across time, but pairing them with the confirming candle's own
timestamp is.

Two arms, one shared detection substrate
------------------------------------------
Arm A (IFVGInversionEntryAdapter): fires the exact bar
`inverted_bar_index` first equals the current bar - immediate entry on
inversion confirmation, no retest wait.
Arm B (IFVGRetestEntryAdapter): fires the exact bar
`retest_confirmed_this_bar` is True for an already-inverted, not-failed
gap - waits for the tracker's own 2-bar rejection pattern.

Effective direction (the actual trade direction) is the OPPOSITE of
the gap's own original direction: an originally-bullish gap that
inverts is now acting as resistance - the continuation thesis is
SHORT (price rejects the newly-broken level). The mirror holds for an
originally-bearish gap.

Actionability / no retroactive signals
-----------------------------------------
Both arms check ONLY whether the confirming field equals the CURRENT
bar being processed (`inverted_bar_index == current_bar_index` /
`retest_confirmed_this_bar is True`, itself already computed as
`last_retest_bar_index == current_bar_index` inside the tracker) -
never scanning backward through history for a previously-missed event.
Combined with the already-proven one-shot, non-retroactive lifecycle
guarantees from the implementation sprint (a fact reused here, not
re-derived), a signal is only ever raised on the exact replay step its
confirming candle closes, and never re-raised or backdated.

Stop-loss: the tracker's own CLOSE-CONFIRMED FAILURE boundary
------------------------------------------------------------------
The initial stop is placed at the gap's own zone edge that would flip
`is_failed=True` (zone_high for an originally-bullish/now-inverted
gap, zone_low for the mirror) - the SAME boundary the tracker already
uses for its own lifecycle failure state, per
docs/fvg_ifvg_nephew_sam_comparison_and_stop_design_report.md's own
Addendum SS4c design. This is DELIBERATELY NOT the same thing as the
actual protective stop that will execute in the backtest: the
tracker's `is_failed` is a close-confirmed, lagging, descriptive
lifecycle marker (a later bar's CLOSE past the boundary), while
ExecutionSimulator's own stop-loss check (unchanged, reused as-is)
compares each new candle's WICK (high/low) against the stop level -
an intrabar, immediate execution rule. In practice, the real backtest
stop will almost always fire before the tracker's own `is_failed`
could ever be observed, since a wick reaching the stop level precedes
a close beyond it. `is_failed`/`inversion_expired` remain purely
descriptive here, used only for the opportunity ledger, never as the
mechanism that actually closes a trade.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Literal

from strategy.features.fair_value_gap import FairValueGapTracker
from strategy.trade_setup import TradeSetup, create_risk_based_trade_setup

Side = Literal["LONG", "SHORT"]

MIN_RISK_PERCENT = 0.006  # matches every other adapter's own floor rationale, unchanged
STOP_BUFFER_PCT = 0.001  # matches the existing project-wide constant, unchanged
REWARD_MULTIPLE = 2.0  # fixed 2R, matching the project's own control-comparable convention


def _gap_key(gap: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (gap["direction"], gap["zone_high"], gap["zone_low"], gap["created_at"])


def _effective_direction(original_direction: str) -> Side:
    return "SHORT" if original_direction == "bullish" else "LONG"


@dataclass(frozen=True)
class IFVGEvent:
    gap_key: tuple[Any, Any, Any, Any]
    original_direction: str
    effective_direction: Side
    zone_high: float
    zone_low: float
    event_type: Literal["inversion", "retest"]
    confirmed_at: datetime
    confirmed_bar_index: int


def _apply_min_risk_floor(entry: float, stop: float, decision: Side) -> float:
    if decision == "LONG":
        if stop >= entry:
            stop = entry * (1 - MIN_RISK_PERCENT)
        if entry - stop < entry * MIN_RISK_PERCENT:
            stop = entry * (1 - MIN_RISK_PERCENT)
        return stop
    if stop <= entry:
        stop = entry * (1 + MIN_RISK_PERCENT)
    if stop - entry < entry * MIN_RISK_PERCENT:
        stop = entry * (1 + MIN_RISK_PERCENT)
    return stop


def _stop_target(decision: Side, entry: float, event: IFVGEvent) -> tuple[float, float]:
    # Failure boundary: the ORIGINAL far edge of the gap - the same
    # edge the tracker itself uses to mark is_failed. For an
    # originally-bullish (now-inverted, SHORT) gap this is zone_high;
    # for an originally-bearish (now-inverted, LONG) gap this is zone_low.
    if event.original_direction == "bullish":
        boundary = event.zone_high
    else:
        boundary = event.zone_low

    if decision == "LONG":
        stop = _apply_min_risk_floor(entry, boundary * (1 - STOP_BUFFER_PCT), decision)
        risk = entry - stop
        return stop, entry + risk * REWARD_MULTIPLE

    stop = _apply_min_risk_floor(entry, boundary * (1 + STOP_BUFFER_PCT), decision)
    risk = stop - entry
    return stop, entry - risk * REWARD_MULTIPLE


def make_ifvg_callbacks(
    symbol: str,
    arm: Literal["inversion", "retest"],
    timeframe_key: str = "15m",
    timestamp_key: str = "timestamp",
    risk_percent: float = 1.0,
    inversion_watch_bars: int = 500,
    retest_cooldown_bars: int = 5,
    event_log: list[IFVGEvent] | None = None,
) -> tuple[Callable[..., dict[str, Any]], Callable[..., TradeSetup]]:
    """
    event_log, if supplied, is appended to (in-place) with every
    confirmed event THIS ARM's own trigger condition matches, whether
    or not it wins the engine's own one-trade-at-a-time arbitration -
    the same "record the decision, not just the trade" separation
    already used throughout the multi-module opportunity-ledger work.
    """

    tracker = FairValueGapTracker(
        timeframe=timeframe_key,
        track_inversions=True,
        track_retests=(arm == "retest"),
        inversion_watch_bars=inversion_watch_bars,
        retest_cooldown_bars=retest_cooldown_bars,
    )
    last_event: dict[str, IFVGEvent | None] = {"value": None}
    seen_15m_len: dict[str, int] = {"value": 0}

    def strategy_callback(current_candle: dict[str, Any], market_snapshot: dict[str, Any]) -> dict[str, Any]:
        candles_15m = market_snapshot.get(symbol, {}).get(timeframe_key, [])

        if not candles_15m:
            last_event["value"] = None
            return {"decision": "IGNORE", "setup_name": None, "reasoning": "no 15m history yet",
                     "evidence_count": 0, "required_conditions": [], "additional_evidence": []}

        if len(candles_15m) > seen_15m_len["value"]:
            tracker.sync(candles_15m)
            seen_15m_len["value"] = len(candles_15m)

        current_bar_index = len(candles_15m) - 1
        snap = tracker.snapshot()

        # confirmed_at is deliberately the DECISION bar's own timestamp
        # (the same 1-minute candle passed to both callbacks, and the
        # same one BacktestRunner will record as a trade's own entry
        # timestamp if it opens one) - NOT the 15m candle's own
        # inverted_at/created_at, which uses a different clock and
        # would not reliably match a resulting trade record. The 15m
        # tracker-level timestamp remains available on the gap dict
        # itself for anyone reading the tracker directly.
        decision_timestamp = current_candle[timestamp_key]

        matched: IFVGEvent | None = None
        for gap in snap["filled"]:
            if arm == "inversion":
                if gap["is_inverted"] and gap["inverted_bar_index"] == current_bar_index:
                    matched = IFVGEvent(
                        gap_key=_gap_key(gap), original_direction=gap["direction"],
                        effective_direction=_effective_direction(gap["direction"]),
                        zone_high=gap["zone_high"], zone_low=gap["zone_low"],
                        event_type="inversion", confirmed_at=decision_timestamp,
                        confirmed_bar_index=gap["inverted_bar_index"],
                    )
                    break
            else:
                if gap["is_inverted"] and not gap["is_failed"] and gap["retest_confirmed_this_bar"]:
                    matched = IFVGEvent(
                        gap_key=_gap_key(gap), original_direction=gap["direction"],
                        effective_direction=_effective_direction(gap["direction"]),
                        zone_high=gap["zone_high"], zone_low=gap["zone_low"],
                        event_type="retest", confirmed_at=decision_timestamp,
                        confirmed_bar_index=current_bar_index,
                    )
                    break

        last_event["value"] = matched

        if matched is None:
            return {"decision": "IGNORE", "setup_name": None, "reasoning": "no confirmed event this bar",
                     "evidence_count": 0, "required_conditions": [], "additional_evidence": []}

        if event_log is not None:
            event_log.append(matched)

        return {
            "decision": matched.effective_direction,
            "setup_name": f"ifvg_{arm}_entry",
            "reasoning": f"{matched.event_type} confirmed for {matched.original_direction} gap [{matched.zone_low}, {matched.zone_high}]",
            "evidence_count": 0, "required_conditions": [], "additional_evidence": [],
        }

    def trade_setup_callback(decision: str, current_candle: dict[str, Any], market_snapshot: dict[str, Any], current_equity: float) -> TradeSetup:
        event = last_event["value"]
        if event is None:
            raise ValueError("trade_setup_callback called with no confirmed event recorded this step")

        entry = current_candle["close"]
        stop, take_profit = _stop_target(decision, entry, event)

        return create_risk_based_trade_setup(
            side=decision, entry_price=entry, stop_loss=stop, take_profit=take_profit,
            equity=current_equity, risk_percent=risk_percent,
        )

    return strategy_callback, trade_setup_callback
