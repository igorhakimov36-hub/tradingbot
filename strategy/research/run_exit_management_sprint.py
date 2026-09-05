"""
Exit Management Research Sprint - main comparison run.

Policy A (control, exit_policy=None) vs Policy D
(StructureBasedTrailExitPolicy) on S001 only, S005 only, and S001+S005,
across 2024-01 and 2025-03 (the same randomly-selected 2025 month
already used and documented for S007's initial validation - not
re-drawn).

No entry logic change (S001/S005 untouched), no Strategy Engine
change, no optimization. Not part of the committed codebase - lives
under strategy/research/ (uncommitted) rather than only a session
scratchpad so this exact rerun configuration remains recoverable
across sessions, per the Exit-Policy State Isolation Impact Audit.
"""

import pickle
import sys
import time

sys.path.insert(0, r"C:\Users\User\Desktop\tradingbot")

from backtesting.backtest_runner import BacktestRunner, ProviderSpec
from backtesting.window_manager import TimeWindow, WindowManager
from data.historical_loader import load_ohlcv_csv
from data.timeframe_manager import TimeframeManager
from datetime import timedelta
from strategy.market_intelligence_coordinator import MarketIntelligenceCoordinator
from strategy.research.structure_based_trail_exit_policy import StructureBasedTrailExitPolicy
from strategy.setups.fair_value_gap_rebalance import FairValueGapRebalanceSetup
from strategy.setups.liquidity_sweep_reversal import LiquiditySweepReversalSetup
from strategy.strategy_engine_v2 import StrategyEngineV2
from strategy.strategy_engine_v2_backtest_adapter import make_strategy_engine_v2_callbacks

SYMBOL = "BTCUSDT"
WINDOWS = [(2024, 1), (2025, 3)]

SETUP_GROUPS = {
    "S001_only": lambda: [LiquiditySweepReversalSetup()],
    "S005_only": lambda: [FairValueGapRebalanceSetup()],
    "S001_S005": lambda: [LiquiditySweepReversalSetup(), FairValueGapRebalanceSetup()],
}


def run_one(candles_1m, candles_15m, window_manager, provider_specs, build_setups, policy_name):
    coordinator = MarketIntelligenceCoordinator(symbol=SYMBOL, timeframe="15m")
    engine = StrategyEngineV2(symbol=SYMBOL, setups=build_setups())
    strategy_callback, trade_setup_callback = make_strategy_engine_v2_callbacks(engine, coordinator)

    exit_policy = None
    policy_obj = None
    if policy_name == "D_structure_trail":
        policy_obj = StructureBasedTrailExitPolicy(coordinator=coordinator)
        exit_policy = policy_obj

    runner = BacktestRunner(window_manager=window_manager, candles=candles_1m, symbol=SYMBOL, provider_specs=provider_specs)

    t0 = time.perf_counter()
    result = runner.run_strategy(
        window_name="VALIDATION", strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback, initial_equity=10_000.0,
        exit_policy=exit_policy,
    )
    elapsed = time.perf_counter() - t0

    return result, policy_obj, elapsed


def run_window(year, month):
    print(f"\n{'='*80}\n{SYMBOL} - {year}-{month:02d}\n{'='*80}")
    path = rf"C:\Users\User\Desktop\tradingbot\data\{SYMBOL}-1m-{year}-{month:02d}.csv"
    candles_1m = load_ohlcv_csv(path)
    print(f"  {len(candles_1m)} 1m bars ({candles_1m[0]['timestamp']} -> {candles_1m[-1]['timestamp']})")

    tf = TimeframeManager(timeframes=["15m"])
    tf.sync(candles_1m)
    candles_15m = tf.get_history("15m")

    data_start = candles_1m[0]["timestamp"]
    data_end = candles_1m[-1]["timestamp"]

    window_manager = WindowManager(
        train=TimeWindow(name="TRAIN", start=data_start - timedelta(days=2), end=data_start - timedelta(days=1)),
        validation=TimeWindow(name="VALIDATION", start=data_start, end=data_end + timedelta(minutes=1)),
        held_out=TimeWindow(name="HELD_OUT", start=data_end + timedelta(days=1), end=data_end + timedelta(days=2)),
    )
    provider_specs = {SYMBOL: {"15m": ProviderSpec(kind="bar_series", records=candles_15m, timeframe="15m")}}

    window_results = {}
    for group_name, build_setups in SETUP_GROUPS.items():
        for policy_name in ("A_control", "D_structure_trail"):
            key = f"{group_name}__{policy_name}"
            result, policy_obj, elapsed = run_one(candles_1m, candles_15m, window_manager, provider_specs, build_setups, policy_name)
            print(f"  [{key}] done in {elapsed:.1f}s, trades={result.performance.total_trades}")
            window_results[key] = {
                "result": result,
                "trade_log": list(policy_obj.trade_log) if policy_obj else None,
                "elapsed": elapsed,
            }

    return window_results, data_start, data_end


if __name__ == "__main__":
    all_results = {}
    for year, month in WINDOWS:
        key = f"{year}-{month:02d}"
        window_results, data_start, data_end = run_window(year, month)
        all_results[key] = {"windows": window_results, "data_start": data_start, "data_end": data_end}

        out_path = r"C:\Users\User\AppData\Local\Temp\claude\C--Users-User-Desktop-tradingbot-tests\e5098a2f-3edb-4bdb-8512-f3c4bc79f151\scratchpad\exit_management_sprint_results_ID_FIX_RERUN.pkl"
        with open(out_path, "wb") as f:
            pickle.dump(all_results, f)
        print(f"  Saved progress through {key}")

    print("\nDONE.")
