"""
Progressive stop-management research policies for the SOL Progressive
Stop Management sprint. RESEARCH-ONLY. Implements the ExitPolicy
protocol (backtesting/exit_policy.py, unmodified) - no change to
backtesting/execution_simulator.py or backtesting/backtest_runner.py.

R0 convention (frozen, never recomputed)
------------------------------------------------------------------------
R0 = |entry_price - original_stop_loss|, captured once when the policy
first observes the trade (its own `stop_loss` at that moment is, by
construction, still the setup's original stop - this policy never
tightens on the entry bar itself, matching the two-phase contract's own
"apply_pending runs before this bar's check, evaluate runs after" timing,
so the first bar this class ever sees a trade is always with its
original, untouched stop). All subsequent stop levels are expressed as
a multiple of this SAME frozen R0 - never recalculated from a later,
tightened stop.

Staircase formula (frozen, covers all three candidate policies with two
parameters - step_size, the MFE increment that triggers a re-check, and
tighten_per_step, how much the stop moves per step):

    stop_R(MFE_R) = -1.00 + floor(MFE_R / step_size) * tighten_per_step

- Policy B (quarter-R staircase): step_size=0.25, tighten_per_step=0.25.
- Policy C (half-R staircase): step_size=0.50, tighten_per_step=0.50.
- Policy D (slower quarter-R staircase): step_size=0.25, tighten_per_step=0.125.

`stop_R` is clamped to [-1.00, MFE_R - 0] (never below the original
stop, never ahead of price) and is monotonically non-decreasing by
construction (the running stop is always `max(previous_stop_R, new_stop_R)`).
Take-profit is never touched by any policy in this module.

MFE tracking (frozen)
------------------------------------------------------------------------
Maximum favorable excursion is tracked using each bar's own high (LONG)
/ low (SHORT), starting from the FIRST bar this policy observes a given
trade (never the entry bar itself - the two-phase ExitPolicy contract
guarantees evaluate()/apply_pending() are never called for the bar a
trade opens on, so pre-entry/entry-bar price movement is structurally
excluded, not filtered by extra logic here). MFE is a running maximum -
a later retracement never reduces it, matching "use the trade's maximum
favorable progress observed so far, not its current progress."

Tick-size rounding (disclosed assumption, not verified against Binance's
own historical tick size for the full 2024-2025 SOLUSDT perpetual
period): stop prices are rounded to 2 decimal places
(`DEFAULT_PRICE_TICK = 0.01`), a reasonable, documented convention for
SOL's own ~$90-220 TRAIN-period price range - not claimed authoritative.
"""

import math
from dataclasses import dataclass, field
from typing import Any

from backtesting.execution_simulator import SimulatedTrade

DEFAULT_PRICE_TICK = 0.01


def round_to_tick(price: float, tick: float = DEFAULT_PRICE_TICK) -> float:
    return round(round(price / tick) * tick, 10)


def staircase_stop_r(mfe_r: float, step_size: float, tighten_per_step: float) -> float:
    """
    Pure function: given the trade's own maximum favorable excursion in
    R units and the two staircase parameters, returns the stop level in
    R units (negative = still within original risk, 0 = breakeven,
    positive = locked-in profit). Never below -1.00 (the original
    stop); never ahead of the excursion that produced it.
    """

    if mfe_r <= 0:
        return -1.00

    n_steps = math.floor(mfe_r / step_size)
    stop_r = -1.00 + n_steps * tighten_per_step

    return stop_r


def stop_price_from_r(side: str, entry_price: float, r0: float, stop_r: float, tick: float = DEFAULT_PRICE_TICK) -> float:
    if side == "LONG":
        price = entry_price + stop_r * r0
    else:
        price = entry_price - stop_r * r0

    return round_to_tick(price, tick)


@dataclass
class _TradeState:
    r0: float
    max_favorable_price: float  # running max (LONG) / min (SHORT) since first observed bar
    current_stop_r: float = -1.00
    pending_stop_price: float | None = None
    n_tightenings: int = 0


class StaircaseExitPolicy:
    """
    Generic staircase progressive-stop ExitPolicy, parameterized by
    (step_size, tighten_per_step) - Policies B/C/D are three named
    instances of this same class, never three separate implementations.

    Implements the ExitPolicy protocol
    (backtesting/exit_policy.py) exactly: apply_pending() applies a
    pending stop decided from the PREVIOUS bar's close; evaluate() -
    called only for a trade still open after the current bar's own
    stop/target check - computes this bar's own contribution to MFE and
    stores (never applies) the next pending stop. Never mutates
    trade.stop_loss/take_profit directly from evaluate().
    """

    # Attribute name used to attach per-trade state directly to the
    # SimulatedTrade object itself (see _state_for's own docstring for
    # why - never `id(trade)`-keyed).
    _STATE_ATTR = "_progressive_stop_state"

    def __init__(self, step_size: float, tighten_per_step: float, price_tick: float = DEFAULT_PRICE_TICK):
        self._step_size = step_size
        self._tighten_per_step = tighten_per_step
        self._price_tick = price_tick

    def _state_for(self, trade: SimulatedTrade) -> _TradeState:
        """
        State is stored as an attribute ON the trade object itself
        (`SimulatedTrade` is a plain, `__slots__`-free mutable
        dataclass - dynamic attribute assignment is safe and does not
        touch the class's own defined fields), never in an external
        dict keyed by `id(trade)`. CPython reuses an object's `id()`
        once it is garbage collected - across a multi-trade sequential
        backtest (one policy instance reused for every trade in a
        month, per `backtesting/backtest_runner.py`'s own design), a
        closed trade's SimulatedTrade is dereferenced and can be
        garbage-collected before the NEXT trade's own SimulatedTrade is
        allocated, letting the new object legally receive the exact
        same `id()` as the old one - an `id()`-keyed dict would then
        silently hand the new, unrelated trade the OLD trade's stale
        r0/MFE/stop state. Confirmed empirically (not merely a
        theoretical risk) while reconciling this sprint's own paired
        vs. sequential results - see the report's own correction
        section. Storing state on the object itself makes this
        impossible by construction: there is no lookup key to collide.
        """

        state = getattr(trade, self._STATE_ATTR, None)
        if state is None:
            r0 = abs(trade.entry_price - trade.stop_loss)
            state = _TradeState(r0=r0, max_favorable_price=trade.entry_price)
            setattr(trade, self._STATE_ATTR, state)
        return state

    def apply_pending(self, trade: SimulatedTrade) -> None:
        state = getattr(trade, self._STATE_ATTR, None)
        if state is None or state.pending_stop_price is None:
            return

        # Never loosen: for LONG the stop only ever moves up; for SHORT
        # only ever moves down. Enforced here as a final, structural
        # guard in addition to current_stop_r's own monotonic tracking.
        if trade.side == "LONG":
            trade.stop_loss = max(trade.stop_loss, state.pending_stop_price)
        else:
            trade.stop_loss = min(trade.stop_loss, state.pending_stop_price)

        state.pending_stop_price = None

    def evaluate(self, trade: SimulatedTrade, current_candle: dict[str, Any], market_snapshot: dict[str, Any]) -> None:
        state = self._state_for(trade)

        if trade.side == "LONG":
            state.max_favorable_price = max(state.max_favorable_price, current_candle["high"])
            mfe_r = (state.max_favorable_price - trade.entry_price) / state.r0 if state.r0 else 0.0
        else:
            state.max_favorable_price = min(state.max_favorable_price, current_candle["low"])
            mfe_r = (trade.entry_price - state.max_favorable_price) / state.r0 if state.r0 else 0.0

        new_stop_r = staircase_stop_r(mfe_r, self._step_size, self._tighten_per_step)
        new_stop_r = max(new_stop_r, state.current_stop_r)  # monotonic - never loosens

        if new_stop_r > state.current_stop_r:
            state.current_stop_r = new_stop_r
            state.n_tightenings += 1
            state.pending_stop_price = stop_price_from_r(
                trade.side, trade.entry_price, state.r0, new_stop_r, self._price_tick,
            )


def make_policy_b() -> StaircaseExitPolicy:
    """Quarter-R staircase: +0.25R MFE -> tighten 0.25R."""
    return StaircaseExitPolicy(step_size=0.25, tighten_per_step=0.25)


def make_policy_c() -> StaircaseExitPolicy:
    """Half-R staircase: +0.50R MFE -> tighten 0.50R."""
    return StaircaseExitPolicy(step_size=0.50, tighten_per_step=0.50)


def make_policy_d() -> StaircaseExitPolicy:
    """Slower quarter-R staircase: +0.25R MFE -> tighten 0.125R."""
    return StaircaseExitPolicy(step_size=0.25, tighten_per_step=0.125)
