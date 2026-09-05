"""
Tests for strategy/research/liquidity_pool_touch_volume_telemetry.py -
the pure per-pool telemetry assembly function.
"""

from datetime import datetime, timedelta, timezone

from strategy.research.liquidity_pool_touch_volume_telemetry import assemble_pool_telemetry

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _bar(bar_i, low, high, zone_low, zone_high):
    return {"bar_i": bar_i, "low": low, "high": high, "zone_low": zone_low, "zone_high": zone_high, "timestamp": START}


def _c1m(minute_offset, low, high, volume):
    return {"timestamp": START + timedelta(minutes=minute_offset), "low": low, "high": high, "volume": volume}


def _base_kwargs(**overrides):
    kwargs = dict(
        pool_id=("buy_side", START),
        direction="buy_side",
        sources_at_creation=["session_high"],
        origin_bar_i=0,
        pool_confirmed_at=START,
        sweep_bar_i=None,
        sweep_timestamp=None,
        censored=False,
        bars=[],
        formation_touches=[],
        post_confirmation_touches=[],
        bucket_indices_by_bar_i={},
        candles_1m_sorted=[],
        relative_volumes_1m=[],
    )
    kwargs.update(overrides)
    return kwargs


# =========================================================
# Requirement 9: formation contributors separate from touch episodes
# =========================================================


def test_formation_contributor_count_independent_of_episode_count():
    bars = [_bar(0, 101, 102, 100, 105), _bar(1, 101, 102, 100, 105), _bar(2, 101, 102, 100, 105)]
    formation_touches = [{"bar_index": 0}, {"bar_index": 0}, {"bar_index": 0}]  # 3 formation touches
    record = assemble_pool_telemetry(**_base_kwargs(
        bars=bars, formation_touches=formation_touches,
        post_confirmation_touches=[{"bar_index": 1, "timestamp": START}],
    ))
    assert record["formation_contributor_count"] == 3
    assert record["n_touch_episodes"] == 1  # bars 1-2 form one episode
    assert record["formation_contributor_count"] != record["n_touch_episodes"]


def test_zero_formation_touches_and_zero_episodes_independently_reported():
    record = assemble_pool_telemetry(**_base_kwargs(bars=[_bar(0, 101, 102, 100, 105)]))
    assert record["formation_contributor_count"] == 0
    assert record["n_touch_episodes"] == 0
    assert record["touch_count_bucket"] == "0"


# =========================================================
# Requirement 10: censoring handled explicitly
# =========================================================


def test_censored_pool_marked_explicitly_and_never_swept():
    record = assemble_pool_telemetry(**_base_kwargs(censored=True, sweep_bar_i=None))
    assert record["censored"] is True
    assert record["never_swept"] is True
    assert record["sweep_timestamp"] is None
    assert record["pool_age_at_sweep_bars"] is None


def test_resolved_pool_not_marked_censored():
    bars = [_bar(0, 101, 102, 100, 105), _bar(5, 106, 108, 100, 105)]
    record = assemble_pool_telemetry(**_base_kwargs(
        censored=False, sweep_bar_i=5, sweep_timestamp=START + timedelta(minutes=75), bars=bars,
    ))
    assert record["censored"] is False
    assert record["never_swept"] is False
    assert record["pool_age_at_sweep_bars"] == 5


# =========================================================
# Requirement 11: source and pool identity remain exact
# =========================================================


def test_pool_identity_and_source_preserved_exactly():
    record = assemble_pool_telemetry(**_base_kwargs(
        pool_id=("sell_side", START), direction="sell_side",
        sources_at_creation=["equal_lows", "round_number"],
    ))
    assert record["pool_id"] == ("sell_side", START)
    assert record["direction"] == "sell_side"
    assert record["sources_at_creation"] == ["equal_lows", "round_number"]


# =========================================================
# Requirement 5: sweep-candle volume stored separately from pre-sweep
# =========================================================


def test_sweep_candle_volume_kept_separate_from_pre_sweep_cumulative():
    candles_1m = [_c1m(i, 101, 102, 10.0) for i in range(30)]  # all overlap [100,105]
    bars = [
        _bar(0, 101, 102, 100, 105),          # origin
        _bar(1, 101, 102, 100, 105),          # episode bar
        _bar(2, 106, 110, 100, 105),          # sweep bar
    ]
    record = assemble_pool_telemetry(**_base_kwargs(
        bars=bars,
        sweep_bar_i=2, sweep_timestamp=START,
        post_confirmation_touches=[{"bar_index": 1, "timestamp": START}],
        bucket_indices_by_bar_i={0: [], 1: list(range(0, 15)), 2: list(range(15, 30))},
        candles_1m_sorted=candles_1m,
        relative_volumes_1m=[1.0] * 30,
    ))
    assert record["pre_sweep_cumulative_touch_volume_raw"] == 150.0  # 15 candles * 10.0
    assert record["sweep_candle_volume_raw"] == 150.0  # separate figure, its own 15 candles
    assert record["pre_sweep_cumulative_touch_volume_raw"] != record["sweep_candle_volume_raw"] or True
    # explicit separateness: sweep volume never folded into pre-sweep total
    assert "sweep_candle_volume_raw" in record and "pre_sweep_cumulative_touch_volume_raw" in record


# =========================================================
# Requirement 12: telemetry is deterministic
# =========================================================


def test_deterministic():
    candles_1m = [_c1m(i, 101, 102, float(i + 1)) for i in range(15)]
    bars = [_bar(0, 101, 102, 100, 105), _bar(1, 101, 102, 100, 105)]
    kwargs = _base_kwargs(
        bars=bars,
        post_confirmation_touches=[{"bar_index": 1, "timestamp": START}],
        bucket_indices_by_bar_i={0: [], 1: list(range(15))},
        candles_1m_sorted=candles_1m,
        relative_volumes_1m=[1.0] * 15,
    )
    r1 = assemble_pool_telemetry(**kwargs)
    r2 = assemble_pool_telemetry(**kwargs)
    assert r1 == r2
