"""
SOL Multi-Module Setup Discovery - standalone backtest driver.
Frozen protocol: docs/sol_multi_module_setup_research_protocol.md
(hash a86b2cd9c7a003688a8dd510b581ea0b75a107815be638daafa9afc306b242c0,
verified unchanged before this run).

Runs S001 (reference, unmodified production adapter) and the 3 new
candidates (S008/S009/S011, via the new generic research adapter),
each STANDALONE (one setup registered at a time - no portfolio
crowding), across all 4 SOL TRAIN months, then applies the existing
funding overlay to each candidate's own actual position lifetimes.
Reproducibility: run via `python -m strategy.research.multi_module_standalone_backtest`
from the repository root (all imports are ordinary package imports -
no session-specific paths).
"""

import pickle
import sys
import time
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backtesting.backtest_runner import BacktestRunner, ProviderSpec
from backtesting.window_manager import TimeWindow, WindowManager
from data.historical_loader import load_ohlcv_csv
from data.timeframe_manager import TimeframeManager
from strategy.instrument_scale import default_round_number_spacing, default_volume_profile_bucket_size
from strategy.market_intelligence_coordinator import MarketIntelligenceCoordinator
from strategy.research.funding_overlay import funding_summary_for_trade, load_funding_records_with_mark_price
from strategy.research.multi_module_backtest_adapter import (
    make_multi_module_callbacks, s008_stop_target, s009_stop_target, s011_stop_target,
)
from strategy.research.setups.s008_displacement_continuation import S008DisplacementContinuationSetup
from strategy.research.setups.s009_failed_auction_reversal import S009FailedAuctionReversalSetup
from strategy.research.setups.s011_value_area_fade import S011ValueAreaFadeSetup
from strategy.setups.liquidity_sweep_reversal import LiquiditySweepReversalSetup
from strategy.strategy_engine_v2 import StrategyEngineV2
from strategy.strategy_engine_v2_backtest_adapter import make_strategy_engine_v2_callbacks

SYMBOL = "SOLUSDT"
TRAIN_MONTHS = ["2024-02", "2024-04", "2024-09", "2025-12"]

CANDIDATES = {
    "S001_reference": ("production", None),
    "S008": (S008DisplacementContinuationSetup, s008_stop_target),
    "S009": (S009FailedAuctionReversalSetup, s009_stop_target),
    "S011": (S011ValueAreaFadeSetup, s011_stop_target),
}


def load_month(month: str):
    path = REPO_ROOT / "data" / f"{SYMBOL}-1m-{month}.csv"
    candles_1m = load_ohlcv_csv(str(path))

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
    return candles_1m, window_manager, provider_specs


def run_candidate(label: str, candles_1m, window_manager, provider_specs):
    setup_cls, stop_target_fn = CANDIDATES[label]
    reference_price = candles_1m[0]["close"]
    coordinator = MarketIntelligenceCoordinator(
        symbol=SYMBOL, timeframe="15m",
        round_number_spacing=default_round_number_spacing(reference_price),
        volume_profile_bucket_size=default_volume_profile_bucket_size(reference_price),
    )

    if label == "S001_reference":
        engine = StrategyEngineV2(symbol=SYMBOL, setups=[LiquiditySweepReversalSetup()])
        strategy_callback, trade_setup_callback = make_strategy_engine_v2_callbacks(engine, coordinator)
    else:
        engine = StrategyEngineV2(symbol=SYMBOL, setups=[setup_cls()])
        strategy_callback, trade_setup_callback = make_multi_module_callbacks(engine, coordinator, stop_target_fn)

    runner = BacktestRunner(window_manager=window_manager, candles=candles_1m, symbol=SYMBOL, provider_specs=provider_specs)

    t0 = time.perf_counter()
    result = runner.run_strategy(
        window_name="VALIDATION", strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback, initial_equity=10_000.0,
    )
    elapsed = time.perf_counter() - t0

    trades = []
    opened = list(result.journal.by_event("OPENED"))
    closed = list(result.journal.closed_trades())
    n_orphaned = 0
    if len(opened) == len(closed) + 1:
        n_orphaned = 1
        opened = opened[:-1]
    for o, c in zip(opened, closed):
        trades.append({
            "entry_timestamp": o.timestamp, "exit_timestamp": c.timestamp,
            "side": c.side, "quantity": c.quantity, "entry_price": c.entry_price,
            "exit_price": c.exit_price, "original_stop_loss": o.stop_loss, "original_take_profit": o.take_profit,
            "net_pnl": c.net_pnl, "entry_fee": c.entry_fee, "exit_fee": c.exit_fee, "exit_reason": c.exit_reason,
        })

    return {"trades": trades, "n_orphaned": n_orphaned, "elapsed": elapsed, "total_trades": result.performance.total_trades}


def main(out_path: str) -> None:
    all_results = {}
    for label in CANDIDATES:
        all_results[label] = {}
        for month in TRAIN_MONTHS:
            candles_1m, window_manager, provider_specs = load_month(month)
            r = run_candidate(label, candles_1m, window_manager, provider_specs)
            print(f"{label} / {month}: n={r['total_trades']} orphaned={r['n_orphaned']} ({r['elapsed']:.1f}s)")
            all_results[label][month] = r

    # Funding overlay - recompute per candidate's own actual position
    # lifetimes (never reusing another candidate's funding total).
    funding_by_month = {
        m: load_funding_records_with_mark_price(str(REPO_ROOT / "data" / f"SOLUSDT-funding-{m}.csv"))
        for m in TRAIN_MONTHS
    }

    for label in CANDIDATES:
        for month in TRAIN_MONTHS:
            fr = funding_by_month[month]
            for t in all_results[label][month]["trades"]:
                summary = funding_summary_for_trade(t["entry_timestamp"], t["exit_timestamp"], t["side"], t["quantity"], fr, boundary="inclusive")
                t["funding_net"] = summary["net"]
                t["funding_n_settlements"] = summary["n_settlements"]
                t["funding_net_available"] = summary["net_available"]
                t["net_pnl_after_funding"] = t["net_pnl"] + summary["net"] if summary["net_available"] else t["net_pnl"]

    with open(out_path, "wb") as f:
        pickle.dump(all_results, f)
    print(f"\nSaved to {out_path}")
    print("DONE.")


if __name__ == "__main__":
    default_out = str(REPO_ROOT / "strategy" / "research" / "multi_module_standalone_results.pkl")
    main(sys.argv[1] if len(sys.argv) > 1 else default_out)
