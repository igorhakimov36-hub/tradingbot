from datetime import datetime, timezone

from data.historical_loader import load_ohlcv_csv

from backtesting.window_manager import (
    TimeWindow,
    WindowManager,
)

from backtesting.backtest_runner import (
    BacktestRunner,
)

from backtesting.execution_simulator import (
    ExecutionConfig,
)

from strategy.strategy_engine import (
    strategy_callback,
)

from strategy.trade_setup_callback import (
    trade_setup_callback,
)


def main():

    candles = load_ohlcv_csv("data/BTCUSDT-1m-2024-01.csv")

    window_manager = WindowManager(
        train=TimeWindow(
            "TRAIN",
            datetime(
                2024,
                1,
                1,
                tzinfo=timezone.utc,
            ),
            datetime(
                2024,
                1,
                20,
                tzinfo=timezone.utc,
            ),
        ),
        validation=TimeWindow(
            "VALIDATION",
            datetime(
                2024,
                1,
                20,
                tzinfo=timezone.utc,
            ),
            datetime(
                2024,
                1,
                26,
                tzinfo=timezone.utc,
            ),
        ),
        held_out=TimeWindow(
            "HELD_OUT",
            datetime(
                2024,
                1,
                26,
                tzinfo=timezone.utc,
            ),
            datetime(
                2024,
                2,
                1,
                tzinfo=timezone.utc,
            ),
        ),
    )

    runner = BacktestRunner(
        window_manager=window_manager,
        candles=candles,
    )

    result = runner.run_strategy(
        window_name="TRAIN",
        strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback,
        execution_config=ExecutionConfig(),
        initial_equity=10_000,
    )

    print()
    print("========== BACKTEST ==========")
    print(result.performance)
    print("==============================")
    print()


if __name__ == "__main__":
    main()
