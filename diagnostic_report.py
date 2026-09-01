"""
TEMPORARY DIAGNOSTIC SCRIPT - delete once the Funding/Open Interest
investigation is done.

Does NOT modify the strategy, the scoring system, or the backtest
engine. It observes exactly what decision_engine.make_decision() is
called with on every real backtest step, by monkey-patching the name
at runtime from here only - no production file is touched, and the
real, unmodified strategy_callback / trade_setup_callback / decision
logic runs exactly as it does in run_backtest.py.
"""

import statistics
from datetime import datetime, timezone

import strategy.strategy_engine as strategy_engine_module
from strategy.decision_engine import make_decision as real_make_decision

from data.historical_loader import load_ohlcv_csv
from data.funding_loader import load_funding_csvs
from data.open_interest_loader import load_open_interest_csv
from backtesting.window_manager import TimeWindow, WindowManager
from backtesting.backtest_runner import BacktestRunner, ProviderSpec
from backtesting.execution_simulator import ExecutionConfig
from strategy.strategy_engine import strategy_callback
from strategy.trade_setup_callback import trade_setup_callback

WINDOW_NAME = "TRAIN"

records: list[dict] = []


def recording_make_decision(**kwargs):
    result = real_make_decision(**kwargs)
    records.append({"inputs": kwargs, "result": result})
    return result


strategy_engine_module.make_decision = recording_make_decision


def score_bucket(score: float) -> str:
    if score < 20:
        return "0-20"
    if score < 40:
        return "20-40"
    if score < 60:
        return "40-60"
    if score < 70:
        return "60-70"
    if score < 80:
        return "70-79"
    return "80+"


def main():
    # Same recent-30-day dataset as run_backtest.py (2026-08-02 ->
    # 2026-09-01 UTC) - the only window where real Open Interest is
    # obtainable at all.
    candles = load_ohlcv_csv("data/BTCUSDT-1m-recent30d.csv")
    candles_15m = load_ohlcv_csv("data/BTCUSDT-15m-recent30d.csv")
    funding_records = load_funding_csvs(
        [
            "data/BTCUSDT-funding-2026-08.csv",
        ]
    )
    open_interest_records = load_open_interest_csv(
        "data/BTCUSDT-open_interest-recent30d.csv"
    )

    window_manager = WindowManager(
        train=TimeWindow(
            "TRAIN",
            datetime(2026, 8, 2, tzinfo=timezone.utc),
            datetime(2026, 8, 20, tzinfo=timezone.utc),
        ),
        validation=TimeWindow(
            "VALIDATION",
            datetime(2026, 8, 20, tzinfo=timezone.utc),
            datetime(2026, 8, 26, tzinfo=timezone.utc),
        ),
        held_out=TimeWindow(
            "HELD_OUT",
            datetime(2026, 8, 26, tzinfo=timezone.utc),
            datetime(2026, 9, 1, tzinfo=timezone.utc),
        ),
    )

    runner = BacktestRunner(
        window_manager=window_manager,
        candles=candles,
        symbol="BTCUSDT",
        provider_specs={
            "BTCUSDT": {
                "15m": ProviderSpec(
                    kind="bar_series",
                    records=candles_15m,
                    timeframe="15m",
                ),
                "funding": ProviderSpec(
                    kind="point_event",
                    records=funding_records,
                ),
                "open_interest": ProviderSpec(
                    kind="point_event",
                    records=open_interest_records,
                ),
            },
        },
    )

    runner.run_strategy(
        window_name=WINDOW_NAME,
        strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback,
        execution_config=ExecutionConfig(),
        initial_equity=10_000,
    )

    total_candles = len(runner.get_window_candles(WINDOW_NAME))

    bullish_ob = sum(1 for r in records if r["inputs"]["signal"] == "bullish_order_block")
    bearish_ob = sum(1 for r in records if r["inputs"]["signal"] == "bearish_order_block")

    bullish_bos = sum(1 for r in records if r["inputs"]["bos_quality"]["bos"] == "BULLISH_BOS")
    bearish_bos = sum(1 for r in records if r["inputs"]["bos_quality"]["bos"] == "BEARISH_BOS")

    bullish_choch = sum(1 for r in records if r["inputs"]["choch"] == "BULLISH_CHOCH")
    bearish_choch = sum(1 for r in records if r["inputs"]["choch"] == "BEARISH_CHOCH")

    bullish_sweep = sum(1 for r in records if r["inputs"]["liquidity_sweep"] == "BULLISH_SWEEP")
    bearish_sweep = sum(1 for r in records if r["inputs"]["liquidity_sweep"] == "BEARISH_SWEEP")

    scores = [r["result"]["score"] for r in records]

    distribution = {label: 0 for label in ["0-20", "20-40", "40-60", "60-70", "70-79", "80+"]}
    for score in scores:
        distribution[score_bucket(score)] += 1

    decisions = [r["result"]["decision"] for r in records]

    rejected = [
        r
        for r in records
        if r["inputs"]["signal"] in ("bullish_order_block", "bearish_order_block")
        and r["result"]["decision"] == "IGNORE"
    ]
    rejected_scores = [r["result"]["score"] for r in rejected]

    component_names = [
        "liquidity_score",
        "bos_score",
        "choch_score",
        "volume_score",
        "open_interest_score",
        "funding_score",
    ]

    zero_counts = {name: 0 for name in component_names}
    for r in rejected:
        for name in component_names:
            if r["result"][name] == 0:
                zero_counts[name] += 1

    most_common_reason = max(zero_counts, key=zero_counts.get) if rejected else None

    print("====================")
    print(f"Total candles (1m, {WINDOW_NAME}): {total_candles}")
    print(f"Total decision evaluations: {len(records)}")
    print()
    print(f"Bullish Order Blocks: {bullish_ob}")
    print(f"Bearish Order Blocks: {bearish_ob}")
    print(f"Bullish BOS: {bullish_bos}")
    print(f"Bearish BOS: {bearish_bos}")
    print(f"Bullish CHOCH: {bullish_choch}")
    print(f"Bearish CHOCH: {bearish_choch}")
    print(f"Bullish Liquidity Sweeps: {bullish_sweep}")
    print(f"Bearish Liquidity Sweeps: {bearish_sweep}")
    print()
    print(f"Highest Decision Score: {max(scores) if scores else 'N/A'}")
    print(f"Average Decision Score: {statistics.mean(scores):.2f}" if scores else "Average Decision Score: N/A")
    print()
    print("Decision Score Distribution:")
    for label in ["0-20", "20-40", "40-60", "60-70", "70-79", "80+"]:
        print(f"  {label}: {distribution[label]}")
    print()
    print(f"LONG: {decisions.count('LONG')}")
    print(f"SHORT: {decisions.count('SHORT')}")
    print(f"IGNORE: {decisions.count('IGNORE')}")
    print()
    print(f"Number of trades rejected because score < threshold: {len(rejected)}")
    print(f"Highest rejected score: {max(rejected_scores) if rejected_scores else 'N/A'}")

    if rejected:
        rate = zero_counts[most_common_reason] / len(rejected) * 100
        print(
            f"Most common reason for rejection: {most_common_reason} == 0 "
            f"in {zero_counts[most_common_reason]}/{len(rejected)} rejected cases ({rate:.1f}%)"
        )
    else:
        print("Most common reason for rejection: N/A (no rejected signals)")

    print()
    print("Component zero-rate among rejected cases (supporting detail):")
    for name in component_names:
        rate = zero_counts[name] / len(rejected) * 100 if rejected else 0.0
        print(f"  {name}: {zero_counts[name]}/{len(rejected)} ({rate:.1f}%)")
    print("====================")


if __name__ == "__main__":
    main()
