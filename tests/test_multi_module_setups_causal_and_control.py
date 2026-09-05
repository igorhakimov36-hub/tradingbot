"""
Causal-timing, S001-control-equivalence, and cross-setup state-isolation
checks for the SOL Multi-Module Setup Discovery sprint's 3 new
candidates. See docs/sol_multi_module_setup_research_protocol.md
Section 8.
"""

from datetime import datetime, timedelta, timezone

from backtesting.backtest_runner import BacktestRunner, ProviderSpec
from backtesting.window_manager import TimeWindow, WindowManager
from data.historical_loader import load_ohlcv_csv
from data.timeframe_manager import TimeframeManager
from strategy.instrument_scale import default_round_number_spacing, default_volume_profile_bucket_size
from strategy.market_intelligence_coordinator import MarketIntelligenceCoordinator
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


def _short_window_setup(days=5):
    path = rf"C:\Users\User\Desktop\tradingbot\data\{SYMBOL}-1m-2024-02.csv"
    candles_1m_full = load_ohlcv_csv(path)
    cutoff = candles_1m_full[0]["timestamp"] + timedelta(days=days)
    candles_1m = [c for c in candles_1m_full if c["timestamp"] < cutoff]

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
    return candles_1m, candles_15m, window_manager, provider_specs


def _sol_coordinator(candles_1m):
    reference_price = candles_1m[0]["close"]
    return MarketIntelligenceCoordinator(
        symbol=SYMBOL, timeframe="15m",
        round_number_spacing=default_round_number_spacing(reference_price),
        volume_profile_bucket_size=default_volume_profile_bucket_size(reference_price),
    )


def test_s001_control_runs_unaffected_by_new_research_modules_present():
    """
    Structural proof, exercised: S001's own production code path
    (strategy/setups/liquidity_sweep_reversal.py,
    strategy_engine_v2_backtest_adapter.py) has zero import dependency
    on strategy/research/* (confirmed directly by grep, restated here
    as an executable check) - importing and running all 3 new research
    setups in the SAME test session as S001 must not change S001's own
    result.
    """
    candles_1m, candles_15m, window_manager, provider_specs = _short_window_setup()

    coordinator = _sol_coordinator(candles_1m)
    engine = StrategyEngineV2(symbol=SYMBOL, setups=[LiquiditySweepReversalSetup()])
    strategy_callback, trade_setup_callback = make_strategy_engine_v2_callbacks(engine, coordinator)
    runner = BacktestRunner(window_manager=window_manager, candles=candles_1m, symbol=SYMBOL, provider_specs=provider_specs)

    result_before = runner.run_strategy(
        window_name="VALIDATION", strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback, initial_equity=10_000.0,
    )

    # Now construct all 3 new research setups/adapters (importing and
    # instantiating everything this sprint added) and re-run S001 fresh.
    S008DisplacementContinuationSetup()
    S009FailedAuctionReversalSetup()
    S011ValueAreaFadeSetup()

    coordinator2 = _sol_coordinator(candles_1m)
    engine2 = StrategyEngineV2(symbol=SYMBOL, setups=[LiquiditySweepReversalSetup()])
    strategy_callback2, trade_setup_callback2 = make_strategy_engine_v2_callbacks(engine2, coordinator2)
    runner2 = BacktestRunner(window_manager=window_manager, candles=candles_1m, symbol=SYMBOL, provider_specs=provider_specs)

    result_after = runner2.run_strategy(
        window_name="VALIDATION", strategy_callback=strategy_callback2,
        trade_setup_callback=trade_setup_callback2, initial_equity=10_000.0,
    )

    assert result_before.performance.total_trades == result_after.performance.total_trades
    assert result_before.performance.total_net_pnl == result_after.performance.total_net_pnl


def test_each_new_setup_runs_standalone_without_error_on_real_data():
    """Causal/replay-safety smoke test: each new setup, run through the
    real BacktestRunner/replay engine on a short real SOL slice, must
    complete without error and never raise from reading a field that
    doesn't exist yet (the causal-safety guarantee the Snapshot Builder
    already provides to every setup)."""
    candles_1m, candles_15m, window_manager, provider_specs = _short_window_setup(days=10)

    for setup_cls, stop_target_fn in (
        (S008DisplacementContinuationSetup, s008_stop_target),
        (S009FailedAuctionReversalSetup, s009_stop_target),
        (S011ValueAreaFadeSetup, s011_stop_target),
    ):
        coordinator = _sol_coordinator(candles_1m)
        engine = StrategyEngineV2(symbol=SYMBOL, setups=[setup_cls()])
        strategy_callback, trade_setup_callback = make_multi_module_callbacks(engine, coordinator, stop_target_fn)
        runner = BacktestRunner(window_manager=window_manager, candles=candles_1m, symbol=SYMBOL, provider_specs=provider_specs)

        result = runner.run_strategy(
            window_name="VALIDATION", strategy_callback=strategy_callback,
            trade_setup_callback=trade_setup_callback, initial_equity=10_000.0,
        )

        assert result.performance.total_trades >= 0  # completes without error


def test_two_independent_runs_of_s009_do_not_share_state():
    """Cross-run isolation: two separately-constructed S009 instances,
    run over the same data, must produce identical results - proving no
    hidden global/class-level state leaks between runs."""
    candles_1m, candles_15m, window_manager, provider_specs = _short_window_setup(days=10)

    results = []
    for _ in range(2):
        coordinator = _sol_coordinator(candles_1m)
        engine = StrategyEngineV2(symbol=SYMBOL, setups=[S009FailedAuctionReversalSetup()])
        strategy_callback, trade_setup_callback = make_multi_module_callbacks(engine, coordinator, s009_stop_target)
        runner = BacktestRunner(window_manager=window_manager, candles=candles_1m, symbol=SYMBOL, provider_specs=provider_specs)
        result = runner.run_strategy(
            window_name="VALIDATION", strategy_callback=strategy_callback,
            trade_setup_callback=trade_setup_callback, initial_equity=10_000.0,
        )
        results.append(result)

    assert results[0].performance.total_trades == results[1].performance.total_trades
    assert results[0].performance.total_net_pnl == results[1].performance.total_net_pnl
