"""
Integration proof for the SOL Funding Impact / Source-Conditioned
Re-analysis sprint: calling LiquiditySweepReversalSetup's own private
condition methods directly, for observation (as the pre-filter replay
does), never changes what evaluate() itself would return, and never
mutates the underlying MarketIntelligenceCoordinator/tracker state -
the exact same "read-only observer" pattern already proven safe in the
completed CVD signal-value sprint, re-verified here for the specific
extra methods (_choch_confirms, _multi_source_pool, _smt_confirms)
this sprint's replay calls that the earlier sprint's own harness did not.
"""

from datetime import datetime, timedelta, timezone

from strategy.market_intelligence_coordinator import MarketIntelligenceCoordinator
from strategy.setups.liquidity_sweep_reversal import LiquiditySweepReversalSetup

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _make_candles(n, base=100.0):
    candles = []
    price = base
    for i in range(n):
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


def _replay(observe_extra: bool):
    candles_15m = _make_candles(60)
    coordinator = MarketIntelligenceCoordinator(
        symbol="SOLUSDT", timeframe="15m", round_number_spacing=1.0, volume_profile_bucket_size=0.1,
    )
    setup = LiquiditySweepReversalSetup()

    fired_log = []
    snapshots_log = []

    for i in range(1, len(candles_15m) + 1):
        step = candles_15m[:i]
        snapshot = coordinator.sync_and_build(step, current_price=step[-1]["close"], timestamp=step[-1]["timestamp"])
        snapshots_log.append(snapshot)

        result = setup.evaluate(snapshot)
        fired_log.append((result.fired, result.direction))

        if observe_extra:
            # Exercise the exact extra private-method calls the
            # pre-filter replay makes, purely for observation.
            swept_pool = setup._find_fresh_sweep(snapshot)
            if swept_pool is not None:
                direction = "SHORT" if swept_pool.direction == "buy_side" else "LONG"
                setup._cvd_confirms(snapshot, direction)
                setup._choch_confirms(snapshot, direction)
                setup._multi_source_pool(swept_pool)
                setup._smt_confirms(snapshot, direction)

    return fired_log, snapshots_log


def test_observing_extra_condition_methods_leaves_evaluate_byte_identical():
    fired_with, snaps_with = _replay(observe_extra=True)
    fired_without, snaps_without = _replay(observe_extra=False)

    assert fired_with == fired_without
    assert snaps_with == snaps_without


def test_calling_private_condition_methods_twice_is_idempotent():
    candles_15m = _make_candles(40)
    coordinator = MarketIntelligenceCoordinator(
        symbol="SOLUSDT", timeframe="15m", round_number_spacing=1.0, volume_profile_bucket_size=0.1,
    )
    setup = LiquiditySweepReversalSetup()

    for i in range(1, len(candles_15m) + 1):
        step = candles_15m[:i]
        snapshot = coordinator.sync_and_build(step, current_price=step[-1]["close"], timestamp=step[-1]["timestamp"])

        swept_pool = setup._find_fresh_sweep(snapshot)
        if swept_pool is not None:
            direction = "SHORT" if swept_pool.direction == "buy_side" else "LONG"
            first = (
                setup._cvd_confirms(snapshot, direction),
                setup._choch_confirms(snapshot, direction),
                setup._multi_source_pool(swept_pool),
                setup._smt_confirms(snapshot, direction),
            )
            second = (
                setup._cvd_confirms(snapshot, direction),
                setup._choch_confirms(snapshot, direction),
                setup._multi_source_pool(swept_pool),
                setup._smt_confirms(snapshot, direction),
            )
            assert first == second
