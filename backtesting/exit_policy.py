"""
Exit Policy hook - Exit Management Research Sprint, Step 0.

Purpose
-------
BacktestRunner deliberately never builds a market_snapshot while a
trade is open (a documented performance decision in run_strategy's own
comments: "no point paying for it... while a trade/order is already
active") and gives nothing a chance to inspect or adjust an open
SimulatedTrade before its stop/target are checked each bar. This is
the smallest additive change that makes dynamic exit management
possible without touching ExecutionSimulator, SimulatedTrade,
TradeJournal, TradeSetup, or StrategyEngineV2 at all.

Contract
--------
`run_strategy(..., exit_policy=None)` is the default and preserves
existing behaviour EXACTLY - the market_snapshot-while-open branch in
BacktestRunner is only taken when a concrete ExitPolicy is passed, so
every existing caller and every existing report's control backtest is
unaffected.

Two-phase contract - NEXT-BAR ACTIVATION (causally required)
-----------------------------------------------------------------
An earlier version of this hook called a single `evaluate()` that
mutated the trade directly, using the CURRENT bar's own high/low, right
before that SAME bar's stop/target check ran. That let a decision made
from a bar's own completed OHLC retroactively affect whether that same
bar's price action would have hit the (just-moved) level - impossible
in reality, since the bar's full high/low can only be known once it has
already happened, at which point that bar's own execution is already
decided.

The corrected contract splits this into two calls, both required:

- `apply_pending(trade)` - called FIRST, before this bar's stop/target
  check, for every bar a trade is open. Applies whatever adjustment was
  decided from the PREVIOUS bar's close (if any) - this is what makes
  "the levels active at this candle's open" the ones actually checked
  against this candle's high/low, never levels derived from the candle
  itself.
- `evaluate(trade, current_candle, market_snapshot)` - called AFTER
  this bar's stop/target check, and ONLY if the trade is still open
  (a trade that exits on this bar used only the levels already active
  at its open, per above - there is no future bar left for a new
  decision to apply to, so evaluate() is simply not called for it).
  May store a pending adjustment for the NEXT bar's apply_pending() to
  apply - must NOT mutate `trade.stop_loss`/`trade.take_profit`
  directly, since that would reintroduce the same-bar retroactivity
  this contract exists to prevent.

An ExitPolicy is responsible for its own invariants (never loosening a
stop, never reducing a take-profit toward entry, staying on the correct
side of current price) - BacktestRunner enforces none of this, exactly
as it enforces none of a Setup's institutional logic either.

Replay Safety
-------------
Inherited entirely from the snapshot passed in and the current bar's
own already-known OHLC - no new candle access, no lookahead. The
two-phase split above additionally removes the same-bar retroactivity
a single-call design would otherwise permit.
"""

from typing import Any, Protocol

from backtesting.execution_simulator import SimulatedTrade


class ExitPolicy(Protocol):
    def apply_pending(
        self,
        trade: SimulatedTrade,
    ) -> None: ...

    def evaluate(
        self,
        trade: SimulatedTrade,
        current_candle: dict[str, Any],
        market_snapshot: dict[str, Any],
    ) -> None: ...
