"""
Strategy Engine V2 <-> BacktestRunner adapter - Phase 2.1, Step 5
(Backtest Integration).

BacktestRunner.run_strategy() expects two callbacks with a fixed
signature (see backtesting/backtest_runner.py's own docstring):
`strategy_callback(current_candle, market_snapshot) -> dict` and
`trade_setup_callback(decision, current_candle, market_snapshot,
current_equity) -> TradeSetup`. Neither callback signature carries the
rich EngineDecision/SetupResult a Setup produces - only the bare
"LONG"/"SHORT"/"IGNORE" string and the raw market_snapshot. This
factory builds a matched PAIR of callbacks that share the last fired
SetupResult via a closure, so trade_setup_callback can read exactly
which zone justified the trade (to place an institutionally-grounded
stop) without recomputing the whole Market Intelligence Snapshot a
second time.

Stop-loss placement
--------------------
Beyond the swept Liquidity Pool's own zone edge - the price level that
would invalidate the setup's thesis (if price re-enters/exceeds the
pool's zone, the "reversal" reading was wrong) - rather than the old
engine's generic wick-plus-fixed-percentage convention. This is a
single principled choice, not a tuned parameter: it is derived directly
from the setup's own reasoning, not selected by testing alternatives.

Risk management is otherwise IDENTICAL to the old engine on purpose,
so the A/B comparison isolates the decision criteria (which setups
fire) as the variable being tested, not a different risk scheme:
same 1% equity risk per trade (create_risk_based_trade_setup, already
shared infrastructure), the same minimum-risk floor rationale
(a stop tighter than round-trip friction cost is mostly noise, not
real risk), and the same fixed 2R reward target.
"""

from datetime import datetime
from typing import Any, Callable

from strategy.market_intelligence_coordinator import MarketIntelligenceCoordinator
from strategy.setups.base import SetupResult
from strategy.strategy_engine_v2 import StrategyEngineV2, engine_decision_to_dict
from strategy.trade_setup import TradeSetup, create_risk_based_trade_setup

MIN_RISK_PERCENT = 0.006  # matches strategy/trade_setup_callback.py's own floor rationale exactly
REWARD_MULTIPLE = 2.0  # matches the old engine's fixed 2R target, for a fair A/B comparison
STOP_BUFFER_PCT = 0.001  # a small buffer beyond the invalidation zone edge, not a tuned parameter


def make_strategy_engine_v2_callbacks(
    engine: StrategyEngineV2,
    coordinator: MarketIntelligenceCoordinator,
    candle_timeframe_key: str = "15m",
    timestamp_key: str = "timestamp",
    risk_percent: float = 1.0,
    reference_symbols: list[str] | None = None,
) -> tuple[Callable[..., dict[str, Any]], Callable[..., TradeSetup]]:
    """
    reference_symbols (optional, defaults to none - fully backward
    compatible): symbol name(s) also attached to BacktestRunner via
    provider_specs (e.g. "ETHUSDT") whose candle history should be
    forwarded to the coordinator's `reference_candles_15m` so an
    intermarket-configured Coordinator (see Step 0's `smt_pairs` wiring)
    actually receives real reference data during a backtest, instead of
    an intermarket-aware setup's SMT check structurally never having
    anything to evaluate. A coordinator with no smt_pairs configured
    simply ignores whatever is passed here, exactly as it always has.
    """

    last_fired: dict[str, SetupResult | None] = {"result": None}

    def strategy_callback(
        current_candle: dict[str, Any],
        market_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        candles_15m = market_snapshot[engine.symbol].get(candle_timeframe_key, [])

        if not candles_15m:
            last_fired["result"] = None
            return {
                "decision": "IGNORE",
                "setup_name": None,
                "reasoning": "no 15m history available yet",
                "evidence_count": 0,
                "required_conditions": [],
                "additional_evidence": [],
            }

        reference_candles_15m = {
            symbol: market_snapshot[symbol][candle_timeframe_key]
            for symbol in (reference_symbols or [])
            if symbol in market_snapshot and market_snapshot[symbol].get(candle_timeframe_key)
        }

        snapshot = coordinator.sync_and_build(
            candles_15m,
            current_price=current_candle["close"],
            timestamp=candles_15m[-1][timestamp_key],
            reference_candles_15m=reference_candles_15m,
        )

        decision = engine.decide(snapshot)
        last_fired["result"] = decision.fired_setups[0] if decision.fired_setups else None

        result_dict = engine_decision_to_dict(decision)

        # Regime/session context for post-hoc "performance by regime"/
        # "performance by session" reporting - read directly off the
        # snapshot already built above, not a new computation. Full
        # snapshot archival (a complete MarketIntelligenceSnapshot per
        # signal) is documented future work, not needed to answer
        # these specific, coarser reporting questions now.
        result_dict["market_structure_regime"] = snapshot.structure.get("market_structure")
        result_dict["active_sessions"] = list(snapshot.sessions.get("active_now", []))

        return result_dict

    def trade_setup_callback(
        decision: str,
        current_candle: dict[str, Any],
        market_snapshot: dict[str, Any],
        current_equity: float,
    ) -> TradeSetup:
        result = last_fired["result"]

        if result is None:
            raise ValueError(
                "trade_setup_callback called with no fired setup recorded - "
                "strategy_callback and trade_setup_callback must be called "
                "in the same replay step"
            )

        entry = current_candle["close"]
        sweep_evidence = result.required_conditions[0].evidence
        zone_high = sweep_evidence["zone_high"]
        zone_low = sweep_evidence["zone_low"]

        if decision == "LONG":
            stop = zone_low * (1 - STOP_BUFFER_PCT)

            if stop >= entry:
                # The zone-based stop is invalid (too close to or above
                # entry) - fall back to the same friction floor used below.
                stop = entry * (1 - MIN_RISK_PERCENT)

            risk = entry - stop

            if risk < entry * MIN_RISK_PERCENT:
                stop = entry * (1 - MIN_RISK_PERCENT)
                risk = entry - stop

            take_profit = entry + (risk * REWARD_MULTIPLE)

        elif decision == "SHORT":
            stop = zone_high * (1 + STOP_BUFFER_PCT)

            if stop <= entry:
                stop = entry * (1 + MIN_RISK_PERCENT)

            risk = stop - entry

            if risk < entry * MIN_RISK_PERCENT:
                stop = entry * (1 + MIN_RISK_PERCENT)
                risk = stop - entry

            take_profit = entry - (risk * REWARD_MULTIPLE)

        else:
            raise ValueError("decision must be LONG or SHORT")

        return create_risk_based_trade_setup(
            side=decision,
            entry_price=entry,
            stop_loss=stop,
            take_profit=take_profit,
            equity=current_equity,
            risk_percent=risk_percent,
        )

    return strategy_callback, trade_setup_callback
