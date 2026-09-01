from datetime import datetime, timedelta, timezone

import pytest

from strategy.market_intelligence_coordinator import MarketIntelligenceCoordinator
from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, high, low, close=None, volume=10.0, taker_buy_volume=None):
    if close is None:
        close = (high + low) / 2

    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": close, "high": high, "low": low, "close": close,
        "volume": volume, "taker_buy_volume": taker_buy_volume,
    }


def _candles(count, step_minutes=15):
    return [
        _candle(i * step_minutes, high=100 + (i % 7), low=90 + (i % 5), taker_buy_volume=5.0)
        for i in range(count)
    ]


def _run_incrementally(coordinator, candles):
    """
    The real usage pattern: several wired trackers (Breaker Blocks,
    Liquidity Pools, session-anchored CVD/Volume Profile) enforce
    exactly one new candle per sync() call, since their second inputs
    are point-in-time snapshots, not historical records. In the real
    backtest this is naturally satisfied - BacktestRunner calls the
    adapter every 1-minute tick, and the 15m candle list it exposes
    never grows by more than one bar between consecutive ticks. Tests
    must replicate that one-candle-at-a-time cadence, not batch.
    """

    result = None
    for n in range(1, len(candles) + 1):
        step = candles[:n]
        result = coordinator.sync_and_build(step, current_price=step[-1]["close"], timestamp=step[-1]["timestamp"])
    return result


def test_sync_and_build_returns_a_valid_snapshot():
    coordinator = MarketIntelligenceCoordinator(symbol="BTCUSDT", timeframe="15m")
    candles = _candles(10)

    snapshot = _run_incrementally(coordinator, candles)

    assert isinstance(snapshot, MarketIntelligenceSnapshot)
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.timeframe == "15m"
    assert snapshot.timestamp == candles[-1]["timestamp"]


def test_two_independent_incremental_replays_are_deterministic():
    candles = _candles(15)

    replay_a = MarketIntelligenceCoordinator(symbol="BTCUSDT", timeframe="15m")
    replay_b = MarketIntelligenceCoordinator(symbol="BTCUSDT", timeframe="15m")

    result_a = _run_incrementally(replay_a, candles)
    result_b = _run_incrementally(replay_b, candles)

    assert result_a == result_b


def test_unchanged_candle_history_returns_cached_snapshot_without_rebuilding():
    coordinator = MarketIntelligenceCoordinator(symbol="BTCUSDT", timeframe="15m")
    candles = _candles(5)

    first = _run_incrementally(coordinator, candles)
    second = coordinator.sync_and_build(candles, current_price=candles[-1]["close"], timestamp=candles[-1]["timestamp"])

    assert first is second  # literally the same cached object, not just equal


def test_growing_history_by_one_candle_produces_a_fresh_snapshot():
    coordinator = MarketIntelligenceCoordinator(symbol="BTCUSDT", timeframe="15m")
    candles = _candles(5)

    first = _run_incrementally(coordinator, candles)

    candles = candles + [_candle(5 * 15, high=105, low=95, taker_buy_volume=5.0)]
    second = coordinator.sync_and_build(candles, current_price=candles[-1]["close"], timestamp=candles[-1]["timestamp"])

    assert first is not second
    assert second.timestamp == candles[-1]["timestamp"]


def test_batched_growth_is_handled_by_internal_one_candle_replay():
    # Real exchange 1m data can have gaps, which can surface more than
    # one new 15m bar in a single upstream sync() call even though the
    # common case is exactly one (discovered during Step 2's real-data
    # validation). The coordinator must not crash - it replays the
    # newly-available candles through every tracker one at a time
    # internally, and must produce the SAME result as if sync_and_build
    # had been called once per new candle.
    candles = _candles(5)

    batched = MarketIntelligenceCoordinator(symbol="BTCUSDT", timeframe="15m")
    batched_result = batched.sync_and_build(candles, current_price=candles[-1]["close"], timestamp=candles[-1]["timestamp"])

    incremental = MarketIntelligenceCoordinator(symbol="BTCUSDT", timeframe="15m")
    incremental_result = _run_incrementally(incremental, candles)

    assert batched_result == incremental_result


def test_snapshot_populates_zones_and_structure_on_real_trackers():
    # Not asserting specific zone counts (that depends on exact price
    # action) - just that the wiring produces internally consistent,
    # non-crashing output across every wired module.
    coordinator = MarketIntelligenceCoordinator(symbol="BTCUSDT", timeframe="15m")
    candles = _candles(60)

    snapshot = _run_incrementally(coordinator, candles)

    assert snapshot.structure["bos"] in {"NO_BOS", "BULLISH_BOS", "BEARISH_BOS"}
    assert isinstance(snapshot.zones, list)
    assert isinstance(snapshot.levels, list)
    assert "delta" in snapshot.order_flow
    assert "cvd" in snapshot.order_flow
    assert snapshot.intermarket == {}  # deliberately not wired for Step 2
