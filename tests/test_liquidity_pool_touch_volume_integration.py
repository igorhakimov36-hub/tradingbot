"""
Integration proof for the Touch Count / Volume research sprint:
Policy A's own tracker output and S001's own setup evaluation are
byte-identical whether or not this sprint's telemetry (touch episodes +
touch volume + the reused Wick-Extremity touch ledger) is being
consumed alongside the real replay. Reuses the same
install_touch_ledger infrastructure already proven safe in the
Wick-Extremity sprint (tests/test_liquidity_pool_wick_extremity_ledger.py);
this file additionally proves the NEW touch-episode/volume computation
built on top of it is equally inert, and that S001's own
LiquiditySweepReversalSetup produces identical fired/direction results
either way.
"""

from datetime import datetime, timedelta, timezone

from strategy.features.equal_highs_lows import EqualLevelsTracker
from strategy.features.liquidity_pool import LiquidityPoolTracker
from strategy.features.session_boundaries import CalendarPeriod, SessionBoundariesTracker
from strategy.features.utils import AverageTrueRangeTracker
from strategy.market_intelligence_snapshot import build_market_intelligence_snapshot
from strategy.research.liquidity_pool_touch_episodes import classify_touch_episodes
from strategy.research.liquidity_pool_touch_volume import relative_volume_series
from strategy.research.liquidity_pool_touch_volume_telemetry import assemble_pool_telemetry
from strategy.research.liquidity_pool_wick_extremity_ledger import install_touch_ledger
from strategy.setups.liquidity_sweep_reversal import LiquiditySweepReversalSetup

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _make_candles(n, base=100.0):
    candles = []
    price = base
    for i in range(n):
        # Gentle drift + one clean sweep-and-reverse near the end.
        if i == n - 2:
            o, h, l, c = price, price + 6.0, price - 1.0, price - 4.0
        else:
            o, h, l, c = price, price + 1.0, price - 1.0, price + 0.2
        candles.append({
            "timestamp": START + timedelta(minutes=15 * i),
            "open": o, "high": h, "low": l, "close": c, "volume": 100.0 + i,
        })
        price = c
    return candles


def _run_replay(consume_telemetry: bool):
    candles_15m = _make_candles(60)

    equal_levels = EqualLevelsTracker(timeframe="15m")
    sessions = SessionBoundariesTracker([CalendarPeriod(name="daily", timezone="UTC", period="daily")], timeframe="15m")
    liquidity_pools = LiquidityPoolTracker(timeframe="15m", round_number_spacing=1.0)
    atr_tracker = AverageTrueRangeTracker(period=14)

    handle = install_touch_ledger(liquidity_pools)

    setup = LiquiditySweepReversalSetup()
    fired_log = []
    snapshots_log = []

    for i in range(1, len(candles_15m) + 1):
        step = candles_15m[:i]
        equal_levels.sync(step)
        sessions.sync(step)
        liquidity_pools.sync(step, equal_levels_snapshot=equal_levels.snapshot(), session_snapshot=sessions.snapshot())
        atr_tracker.sync(step)

        snapshot = build_market_intelligence_snapshot(
            symbol="SOLUSDT", timeframe="15m", timestamp=step[-1]["timestamp"], current_price=step[-1]["close"],
            market_structure={}, fair_value_gaps={}, order_blocks={}, breaker_blocks={},
            equal_levels=equal_levels.snapshot(), liquidity_pools=liquidity_pools.snapshot(),
            session_boundaries=sessions.snapshot(), volume_profile={}, delta={}, cvd={}, intermarket={},
        )
        snapshots_log.append(liquidity_pools.snapshot())

        result = setup.evaluate(snapshot)
        fired_log.append((result.fired, result.direction))

        if consume_telemetry:
            # Exercise the new telemetry machinery on every bar, reading
            # only from already-public snapshot/ledger data - must never
            # feed back into or alter the tracker/setup.
            bars = [{"bar_i": i, "low": step[-1]["low"], "high": step[-1]["high"],
                     "zone_low": 0.0, "zone_high": 1_000_000.0}]
            classify_touch_episodes(bars, origin_bar_i=0, sweep_bar_i=None)
            relative_volume_series(step, lookback_minutes=5, min_warmup=5)
            for entry in handle.ledger:
                assemble_pool_telemetry(
                    pool_id=entry["pool_id"], direction=entry["direction"],
                    sources_at_creation=[entry["source"]], origin_bar_i=0,
                    pool_confirmed_at=entry["timestamp"], sweep_bar_i=None, sweep_timestamp=None,
                    censored=False, bars=[], formation_touches=[], post_confirmation_touches=[],
                    bucket_indices_by_bar_i={}, candles_1m_sorted=[], relative_volumes_1m=[],
                )

    handle.uninstall()
    return fired_log, snapshots_log


def test_policy_a_and_s001_byte_identical_with_and_without_telemetry():
    fired_with, snapshots_with = _run_replay(consume_telemetry=True)
    fired_without, snapshots_without = _run_replay(consume_telemetry=False)

    assert fired_with == fired_without
    assert snapshots_with == snapshots_without
