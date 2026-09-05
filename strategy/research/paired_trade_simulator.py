"""
Paired-trade simulator for the SOL Progressive Stop Management sprint.
RESEARCH-ONLY. Replays ONE already-decided trade (fixed entry price,
stop, take-profit, quantity, side - exactly as the control produced it)
candle-by-candle under a given ExitPolicy, using the real, unmodified
`ExecutionSimulator` for fills/fees/slippage and the exact same
apply_pending-before / evaluate-after ordering
`backtesting/backtest_runner.py` itself uses (mirrored here, not
reimplemented differently) - so a paired comparison never depends on
the single-trade-slot engine's own entry-sequencing (Requirement 4's
"first perform a paired comparison... free of slot availability").

This module does not decide entries - it takes an already-opened
SimulatedTrade-equivalent (from a real control run) and asks "what
would have happened to exactly this trade under a different exit
policy," starting from the SAME entry.
"""

from dataclasses import dataclass
from typing import Any

from backtesting.execution_simulator import ExecutionConfig, ExecutionSimulator, SimulatedTrade
from backtesting.exit_policy import ExitPolicy


@dataclass
class PairedSimulationResult:
    trade: SimulatedTrade
    n_bars: int
    exit_bar_index: int | None  # index into candles_1m_from_entry, 0-based; None if never closed within the given candles


def simulate_paired_trade(
    side: str,
    entry_price: float,
    entry_fee: float,
    stop_loss: float,
    take_profit: float,
    quantity: float,
    candles_1m_from_entry: list[dict[str, Any]],
    exit_policy: ExitPolicy,
    execution_config: ExecutionConfig | None = None,
) -> PairedSimulationResult:
    """
    `candles_1m_from_entry`: 1-minute candles starting from the bar
    AFTER the trade's own entry bar (matching the real BacktestRunner's
    own behavior: apply_pending/evaluate are never called for the entry
    bar itself - see strategy/research/progressive_stop_policies.py's
    own module docstring, verified against backtest_runner.py directly).

    Mirrors backtest_runner.py's own per-bar ordering exactly:
    1. apply_pending(trade) - apply whatever was decided from the
       previous bar.
    2. process_candle(trade, high, low) - the real, unmodified
       ExecutionSimulator's own stop/target check.
    3. If still open: evaluate(trade, candle, {}) - the policy may
       store a new pending adjustment for the NEXT bar.

    market_snapshot is passed as an empty dict - none of the candidate
    policies in this sprint (pure R-multiple staircases) read it; this
    keeps the paired simulator free of any MarketIntelligenceCoordinator
    dependency, matching the sprint's own "no new setup / no market
    condition dependency" scope.
    """

    simulator = ExecutionSimulator(config=execution_config or ExecutionConfig())

    trade = SimulatedTrade(
        side=side, requested_entry=entry_price, entry_price=entry_price,
        stop_loss=stop_loss, take_profit=take_profit, quantity=quantity,
        entry_fee=entry_fee,
    )

    exit_bar_index: int | None = None

    for i, candle in enumerate(candles_1m_from_entry):
        exit_policy.apply_pending(trade)

        was_open = trade.is_open
        trade = simulator.process_candle(trade, high=candle["high"], low=candle["low"])

        if was_open and not trade.is_open:
            exit_bar_index = i
            break

        exit_policy.evaluate(trade, candle, {})

    return PairedSimulationResult(trade=trade, n_bars=len(candles_1m_from_entry), exit_bar_index=exit_bar_index)
