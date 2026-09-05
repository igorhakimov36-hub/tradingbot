"""
StructureBasedTrailExitPolicy - Exit Management Research Sprint,
Exit Policy D (STRUCTURE-BASED TRAIL).

Research-only, per the established precedent for this project's
controlled-experiment wrappers (e.g. VNR Round 1's `_FilterWrapper`) -
NOT committed to backtesting/. Only the generic ExitPolicy hook
(backtesting/exit_policy.py) and the additive BacktestRunner parameter
are permanent infrastructure. Lives under strategy/research/ (rather
than only a session scratchpad) so the corrected version, its rerun
configuration, and its regression tests remain recoverable across
sessions - moved here uncommitted by the Exit-Policy State Isolation
Impact Audit, which found the earlier scratchpad-only copy was not
durably recoverable.

Uses the caller-supplied MarketIntelligenceCoordinator (the SAME
instance the entry strategy_callback uses) to build a
MarketIntelligenceSnapshot from the raw 15m candle history
BacktestRunner's own market_snapshot dict carries - entries and this
policy never run in the same bar (BacktestRunner evaluates entries only
while flat, this policy only while a trade is open), so sharing one
coordinator is safe and mirrors how a live system would keep Market
Intelligence updating continuously regardless of position state.

Fixed, pre-declared logic only - no threshold search, no parameter
fit. Every constant here (the 0.001 stop buffer for a CHOCH-against
warning) is copied from strategy_engine_v2_backtest_adapter.py's own
existing STOP_BUFFER_PCT convention, not invented for this policy.

Mechanics
---------
Before +1R (measured off the CURRENT bar's own high/low against the
trade's ORIGINAL, unmodified risk-per-unit): no stop or TP change.

At and after +1R: on every bar, the new stop is
    max(current_stop, true_break_even, *valid confirmed candidates)   (LONG)
    min(current_stop, true_break_even, *valid confirmed candidates)   (SHORT)
- monotonic by construction (a stop is only ever adjusted toward, never
away from, the current price), which folds "move to true break-even"
and "then trail with structure" into one rule rather than two separate
code paths, since true_break_even is simply always one of the
candidates being maxed/minned against.

True break-even is computed by inverting ExecutionSimulator's own
exact entry/exit formulas (fee_rate, slippage_rate) for the price at
which a same-side exit right now would net exactly zero - not an
approximation.

Take-profit only ever advances to the NEAREST confirmed structural
target beyond the current TP (never the most optimistic one), and only
after +1R activation, using the same "only strictly beyond, never
closer" invariant.

Next-bar activation (causal correctness)
-----------------------------------------
Corrected per the two-phase contract in backtesting/exit_policy.py:
evaluate() NEVER mutates the trade directly - it only computes and
stores a pending stop/take-profit in this trade's own state entry.
apply_pending() is the only method that ever assigns to
trade.stop_loss/trade.take_profit, and BacktestRunner calls it before
that bar's own stop/target check - so a decision made from bar N's
close can only affect bar N+1 onward, never bar N itself. An earlier
version of this file mutated the trade directly inside evaluate(),
which let a decision made from a bar's own high/low retroactively
affect whether that same bar's price action would have hit the
just-moved level - corrected here, not merely documented.
"""

from typing import Any

STOP_BUFFER_PCT = 0.001  # matches strategy_engine_v2_backtest_adapter.py's STOP_BUFFER_PCT exactly


class StructureBasedTrailExitPolicy:
    # State is attached directly to the SimulatedTrade object itself
    # (unhashable, __slots__-free mutable dataclass - dynamic attribute
    # assignment is safe), never in a dict keyed by id(trade). CPython
    # reuses a garbage-collected object's id() - across a multi-trade
    # sequential run (one policy instance reused for every trade in a
    # window/setup-group, per run_exit_management_sprint.py's own
    # design), a closed trade can be collected before the next trade's
    # SimulatedTrade is allocated, letting the new object legally
    # receive the exact same id() as the old one. An id()-keyed dict
    # would then silently hand the new, unrelated trade the OLD
    # trade's stale activation/trail state. Confirmed as a real
    # (not merely theoretical) defect during the Progressive Stop
    # Management sprint's own reconciliation, and fixed here identically
    # per the narrowly scoped impact audit that found this occurrence.
    _STATE_ATTR = "_structure_trail_state"

    def __init__(self, coordinator, fee_rate=0.0004, slippage_rate=0.0002, timeframe_key="15m"):
        self.coordinator = coordinator
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        self.timeframe_key = timeframe_key
        # Insertion-ordered list, one entry per trade seen - never keyed
        # by id(trade) (a second id()-keyed dict here would silently
        # overwrite an earlier trade's logged state whenever an id()
        # collision occurred, corrupting reporting stats even though it
        # would not affect execution once state moved onto the trade
        # object itself - avoided entirely, not just made execution-safe).
        self.trade_log: list[dict[str, Any]] = []

    def _true_break_even(self, trade) -> float:
        qty = trade.quantity

        if trade.side == "LONG":
            executed_exit = (trade.entry_price * qty + trade.entry_fee) / (qty * (1 - self.fee_rate))
            return executed_exit / (1 - self.slippage_rate)

        executed_exit = (trade.entry_price * qty - trade.entry_fee) / (qty * (1 + self.fee_rate))
        return executed_exit / (1 + self.slippage_rate)

    def evaluate(self, trade, current_candle: dict[str, Any], market_snapshot: dict[str, Any]) -> None:
        state = getattr(trade, self._STATE_ATTR, None)

        if state is None:
            state = {
                "side": trade.side,
                "initial_risk": abs(trade.entry_price - trade.stop_loss),
                "original_stop": trade.stop_loss,
                "original_take_profit": trade.take_profit,
                "activated": False,
                "num_stop_moves": 0,
                "num_tp_moves": 0,
                "true_be": None,
                "entry_seen_at": current_candle["timestamp"],
                "pending_stop": None,
                "pending_take_profit": None,
            }
            setattr(trade, self._STATE_ATTR, state)
            self.trade_log.append(state)

        candles_15m = market_snapshot.get(trade.symbol, {}).get(self.timeframe_key, [])
        if not candles_15m:
            return

        current_price = current_candle["close"]
        timestamp = candles_15m[-1]["timestamp"]
        snapshot = self.coordinator.sync_and_build(candles_15m, current_price=current_price, timestamp=timestamp)

        if trade.side == "LONG":
            favorable_move = current_candle["high"] - trade.entry_price
        else:
            favorable_move = trade.entry_price - current_candle["low"]

        r_multiple = (favorable_move / state["initial_risk"]) if state["initial_risk"] else 0.0

        if not state["activated"]:
            if r_multiple >= 1.0:
                state["activated"] = True
            else:
                return

        if state["true_be"] is None:
            state["true_be"] = self._true_break_even(trade)

        self._trail_stop(trade, snapshot, state, current_price)
        self._advance_take_profit(trade, snapshot, state)

    def apply_pending(self, trade) -> None:
        state = getattr(trade, self._STATE_ATTR, None)
        if state is None:
            return

        if state["pending_stop"] is not None:
            trade.stop_loss = state["pending_stop"]
            state["pending_stop"] = None
            state["num_stop_moves"] += 1

        if state["pending_take_profit"] is not None:
            trade.take_profit = state["pending_take_profit"]
            state["pending_take_profit"] = None
            state["num_tp_moves"] += 1

    def _trail_stop(self, trade, snapshot, state, current_price: float) -> None:
        candidates = [state["true_be"]]
        structure = snapshot.structure

        if trade.side == "LONG":
            if structure.get("last_swing_low") is not None:
                candidates.append(structure["last_swing_low"])
            if structure.get("choch") == "BEARISH_CHOCH":
                candidates.append(current_price * (1 - STOP_BUFFER_PCT))
        else:
            if structure.get("last_swing_high") is not None:
                candidates.append(structure["last_swing_high"])
            if structure.get("choch") == "BULLISH_CHOCH":
                candidates.append(current_price * (1 + STOP_BUFFER_PCT))

        for zone in snapshot.zones:
            if trade.side == "LONG":
                if (
                    zone.kind == "liquidity_pool" and zone.direction == "sell_side"
                    and zone.status == "resolved" and zone.resolution_detail == "swept"
                    and zone.resolved_at is not None and zone.resolved_at >= state["entry_seen_at"]
                ):
                    candidates.append(zone.zone_high)
                if (
                    zone.kind in ("order_block", "fvg") and zone.direction == "bullish"
                    and zone.status == "active" and zone.zone_relative_position == "below_price"
                ):
                    candidates.append(zone.zone_high)
            else:
                if (
                    zone.kind == "liquidity_pool" and zone.direction == "buy_side"
                    and zone.status == "resolved" and zone.resolution_detail == "swept"
                    and zone.resolved_at is not None and zone.resolved_at >= state["entry_seen_at"]
                ):
                    candidates.append(zone.zone_low)
                if (
                    zone.kind in ("order_block", "fvg") and zone.direction == "bearish"
                    and zone.status == "active" and zone.zone_relative_position == "above_price"
                ):
                    candidates.append(zone.zone_low)

        # Only ever STORED here as pending - never assigned to
        # trade.stop_loss directly. apply_pending() is the sole place
        # that happens, on the NEXT bar, per the causal contract in
        # backtesting/exit_policy.py.
        if trade.side == "LONG":
            valid = [c for c in candidates if c is not None and c < current_price and c > trade.stop_loss]
            if valid:
                new_stop = max(valid)
                if new_stop > trade.stop_loss:
                    state["pending_stop"] = new_stop
        else:
            valid = [c for c in candidates if c is not None and c > current_price and c < trade.stop_loss]
            if valid:
                new_stop = min(valid)
                if new_stop < trade.stop_loss:
                    state["pending_stop"] = new_stop

    def _advance_take_profit(self, trade, snapshot, state) -> None:
        candidates = []

        for zone in snapshot.zones:
            if trade.side == "LONG":
                if (
                    zone.kind == "liquidity_pool" and zone.direction == "buy_side"
                    and zone.status == "active" and zone.zone_relative_position == "above_price"
                ):
                    candidates.append(zone.zone_low)
                if (
                    zone.kind in ("order_block", "fvg") and zone.direction == "bearish"
                    and zone.status == "active" and zone.zone_relative_position == "above_price"
                ):
                    candidates.append(zone.zone_low)
            else:
                if (
                    zone.kind == "liquidity_pool" and zone.direction == "sell_side"
                    and zone.status == "active" and zone.zone_relative_position == "below_price"
                ):
                    candidates.append(zone.zone_high)
                if (
                    zone.kind in ("order_block", "fvg") and zone.direction == "bullish"
                    and zone.status == "active" and zone.zone_relative_position == "below_price"
                ):
                    candidates.append(zone.zone_high)

        for level in snapshot.levels:
            if trade.side == "LONG" and level.kind in ("session_high", "poc", "vah", "hvn", "lvn"):
                candidates.append(level.price)
            elif trade.side == "SHORT" and level.kind in ("session_low", "poc", "val", "hvn", "lvn"):
                candidates.append(level.price)

        # Stored as pending only - see the same note in _trail_stop.
        if trade.side == "LONG":
            valid = [c for c in candidates if c is not None and c > trade.take_profit]
            if valid:
                state["pending_take_profit"] = min(valid)
        else:
            valid = [c for c in candidates if c is not None and c < trade.take_profit]
            if valid:
                state["pending_take_profit"] = max(valid)
