from datetime import datetime, timezone

from data.historical_loader import load_ohlcv_csv
from data.funding_loader import load_funding_csvs
from data.open_interest_loader import load_open_interest_csv

from backtesting.window_manager import (
    TimeWindow,
    WindowManager,
)

from backtesting.backtest_runner import (
    BacktestRunner,
    ProviderSpec,
)

from backtesting.execution_simulator import (
    ExecutionConfig,
)

from backtesting.experiment_manager import (
    ExperimentManager,
)

from strategy.strategy_engine import (
    strategy_callback,
)

from strategy.trade_setup_callback import (
    MIN_RISK_PERCENT,
    trade_setup_callback,
)


def main():

    # Most recent 30 days as of the download (2026-08-02 -> 2026-09-01
    # UTC). Open Interest is only retrievable for this trailing window
    # at all - Binance does not retain it further back, for any
    # symbol - so this range was chosen specifically to allow a full
    # evaluation with real Funding AND real Open Interest together.
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
            datetime(
                2026,
                8,
                2,
                tzinfo=timezone.utc,
            ),
            datetime(
                2026,
                8,
                20,
                tzinfo=timezone.utc,
            ),
        ),
        validation=TimeWindow(
            "VALIDATION",
            datetime(
                2026,
                8,
                20,
                tzinfo=timezone.utc,
            ),
            datetime(
                2026,
                8,
                26,
                tzinfo=timezone.utc,
            ),
        ),
        held_out=TimeWindow(
            "HELD_OUT",
            datetime(
                2026,
                8,
                26,
                tzinfo=timezone.utc,
            ),
            datetime(
                2026,
                9,
                1,
                tzinfo=timezone.utc,
            ),
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

    execution_config = ExecutionConfig()

    train_result = runner.run_strategy(
        window_name="TRAIN",
        strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback,
        execution_config=execution_config,
        initial_equity=10_000,
    )

    print()
    print("========== TRAIN ==========")
    print(train_result.performance)
    print("============================")
    print()

    validation_result = runner.run_strategy(
        window_name="VALIDATION",
        strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback,
        execution_config=execution_config,
        initial_equity=10_000,
    )

    print("========== VALIDATION ==========")
    print(validation_result.performance)
    print("=================================")
    print()

    experiments = ExperimentManager()

    experiments.record_experiment(
        experiment_id="baseline-v1",
        version="v1",
        timestamp=datetime.now(timezone.utc),
        window_name="VALIDATION",
        parameters={
            "min_risk_percent": MIN_RISK_PERCENT,
            "risk_percent": 1.0,
            "funding_enabled": True,
            "open_interest_enabled": True,
            "dataset": "recent30d (2026-08-02 to 2026-09-01)",
        },
        performance=validation_result.performance,
        notes="Real signal detection, Funding, and Open Interest all wired in - most recent 30 days.",
    )

    print("Recorded VALIDATION result as experiment 'baseline-v1'.")
    print()


if __name__ == "__main__":
    main()
