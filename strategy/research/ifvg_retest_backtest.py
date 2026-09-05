"""
SOL IFVG + Retest experiment - standalone backtest driver.
Frozen protocol: docs/sol_ifvg_retest_experiment_protocol.md
(hash a1b1c3696274c75e7f9cbb5914de7b7177d604675dd0aa4fcc3e7a1c7669b624,
verified unchanged before this run).

Runs both arms (inversion, retest), each STANDALONE, across all 4 SOL
TRAIN months, capturing both the completed-trade ledger AND the
opportunity ledger (every confirmed event, whether or not it became a
trade) - then applies the existing funding overlay per trade's own
actual position lifetime.
"""

import pickle
import sys
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backtesting.backtest_runner import BacktestRunner, ProviderSpec
from backtesting.window_manager import TimeWindow, WindowManager
from data.historical_loader import load_ohlcv_csv
from data.timeframe_manager import TimeframeManager
from strategy.research.funding_overlay import funding_summary_for_trade, load_funding_records_with_mark_price
from strategy.research.ifvg_retest_adapter import make_ifvg_callbacks

SYMBOL = "SOLUSDT"
TRAIN_MONTHS = ["2024-02", "2024-04", "2024-09", "2025-12"]
ARMS = ["inversion", "retest"]


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


def run_arm(arm: str, candles_1m, window_manager, provider_specs):
    event_log = []
    strategy_callback, trade_setup_callback = make_ifvg_callbacks(SYMBOL, arm=arm, event_log=event_log)
    runner = BacktestRunner(window_manager=window_manager, candles=candles_1m, symbol=SYMBOL, provider_specs=provider_specs)

    result = runner.run_strategy(
        window_name="VALIDATION", strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback, initial_equity=10_000.0,
    )

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

    # Opportunity ledger: every confirmed event, whether or not it
    # became a completed trade - matched to trades by (timestamp, side)
    # since that is the exact decision moment each event corresponds to.
    trade_entry_times = {(t["entry_timestamp"], t["side"]) for t in trades}
    ledger = []
    for ev in event_log:
        became_trade = (ev.confirmed_at, ev.effective_direction) in trade_entry_times
        ledger.append({
            "gap_key": ev.gap_key, "original_direction": ev.original_direction,
            "effective_direction": ev.effective_direction, "event_type": ev.event_type,
            "confirmed_at": ev.confirmed_at, "confirmed_bar_index": ev.confirmed_bar_index,
            "became_trade": became_trade,
        })

    return {
        "trades": trades, "ledger": ledger, "n_orphaned": n_orphaned,
        "total_trades": result.performance.total_trades, "total_events": len(event_log),
    }


def main(out_path: str) -> None:
    all_results = {}
    for arm in ARMS:
        all_results[arm] = {}
        for month in TRAIN_MONTHS:
            candles_1m, window_manager, provider_specs = load_month(month)
            r = run_arm(arm, candles_1m, window_manager, provider_specs)
            print(f"{arm} / {month}: events={r['total_events']} trades={r['total_trades']} orphaned={r['n_orphaned']}")
            all_results[arm][month] = r

    funding_by_month = {
        m: load_funding_records_with_mark_price(str(REPO_ROOT / "data" / f"SOLUSDT-funding-{m}.csv"))
        for m in TRAIN_MONTHS
    }
    for arm in ARMS:
        for month in TRAIN_MONTHS:
            fr = funding_by_month[month]
            for t in all_results[arm][month]["trades"]:
                summary = funding_summary_for_trade(t["entry_timestamp"], t["exit_timestamp"], t["side"], t["quantity"], fr, boundary="inclusive")
                t["funding_net"] = summary["net"]
                t["net_pnl_after_funding"] = t["net_pnl"] + summary["net"] if summary["net_available"] else t["net_pnl"]

    with open(out_path, "wb") as f:
        pickle.dump(all_results, f)
    print(f"\nSaved to {out_path}")
    print("DONE.")


if __name__ == "__main__":
    default_out = str(REPO_ROOT / "strategy" / "research" / "ifvg_retest_results.pkl")
    main(sys.argv[1] if len(sys.argv) > 1 else default_out)
