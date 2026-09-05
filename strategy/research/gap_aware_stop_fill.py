"""
Gap-aware stop-fill sensitivity check for the SOL Progressive Stop
Management sprint. RESEARCH-ONLY, pure function.

`backtesting/execution_simulator.py::ExecutionSimulator.process_candle`
fills a stop-loss exit at exactly `trade.stop_loss`, regardless of how
far the triggering candle's low (LONG) / high (SHORT) undercuts it -
there is no gap-through worse-fill modeling anywhere in the simulator
(a pre-existing, disclosed limitation shared by every policy in this
sprint, including the control - see
docs/profitability_root_cause_investigation.md, Section 2, item 8).
This is not modified here (out of this sprint's scope, and shared
identically by the control) - instead, this module recomputes what a
more conservative, gap-aware fill WOULD have been, as a POST-HOC
sensitivity check applied symmetrically to all four policies, per the
sprint's own instruction not to assume a fill at the requested stop
when the next executable price is worse.

"Already-breached-on-activation" is the same phenomenon: a stop applied
via `apply_pending()` at a bar's open can be immediately worse than
that bar's own opening price (a gap at open, before any intrabar
movement) - `gap_aware_stop_fill` treats this identically to an
intrabar gap-through, since `process_candle` cannot distinguish the two
either (it only ever sees a bar's high/low).
"""

from typing import Any


def gap_aware_stop_fill(side: str, stop_price: float, candle: dict[str, Any]) -> tuple[float, bool]:
    """
    Returns (realistic_fill_price, was_gapped). `candle` must have
    "open"/"high"/"low". A LONG stop is gapped if the candle's own open
    is already at or below the stop (the market opened through it,
    before any intrabar movement); a SHORT stop is gapped if the open
    is already at or above the stop. When gapped, the realistic fill is
    the candle's own open (the worst price actually reachable, not the
    stale requested stop level) - never a price better than what the
    market actually offered.
    """

    if side == "LONG":
        gapped = candle["open"] <= stop_price
        return (candle["open"], True) if gapped else (stop_price, False)

    gapped = candle["open"] >= stop_price
    return (candle["open"], True) if gapped else (stop_price, False)


def gap_aware_net_pnl(
    side: str,
    quantity: float,
    entry_price: float,
    entry_fee: float,
    stop_price: float,
    candle: dict[str, Any],
    fee_rate: float,
    slippage_rate: float,
) -> dict[str, Any]:
    """
    Recomputes net P&L for one stop-loss exit under the gap-aware fill,
    using the SAME fee/slippage formulas
    ExecutionSimulator._apply_exit_slippage/close_trade already use
    (never a new cost convention) - reused, not reimplemented
    differently.
    """

    realistic_price, was_gapped = gap_aware_stop_fill(side, stop_price, candle)

    if side == "LONG":
        executed_exit = realistic_price * (1 - slippage_rate)
        gross_pnl = (executed_exit - entry_price) * quantity
    else:
        executed_exit = realistic_price * (1 + slippage_rate)
        gross_pnl = (entry_price - executed_exit) * quantity

    exit_fee = executed_exit * quantity * fee_rate
    net_pnl = gross_pnl - entry_fee - exit_fee

    return {
        "was_gapped": was_gapped,
        "realistic_fill_price": realistic_price,
        "executed_exit": executed_exit,
        "exit_fee": exit_fee,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
    }
