from datetime import datetime, timezone

import pytest

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot
from strategy.setups.base import ConditionResult, SetupResult
from strategy.strategy_engine_v2 import EngineDecision
from strategy.strategy_engine_v2_backtest_adapter import make_strategy_engine_v2_callbacks

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


class _StubCoordinator:
    def __init__(self):
        self.calls = []

    def sync_and_build(self, candles_15m, current_price, timestamp):
        self.calls.append((len(candles_15m), current_price, timestamp))
        return MarketIntelligenceSnapshot(
            symbol="BTCUSDT", timeframe="15m", timestamp=timestamp, current_price=current_price,
            structure={}, zones=[], levels=[], order_flow={"delta": {}, "cvd": {}},
            sessions={"active_now": [], "previous_period_high_low": {}},
            intermarket={}, volume_profile={}, data_quality={},
        )


class _StubEngine:
    symbol = "BTCUSDT"

    def __init__(self, decision_factory):
        self._decision_factory = decision_factory

    def decide(self, snapshot):
        return self._decision_factory(snapshot)


def _fired_decision(snapshot, direction, zone_high, zone_low):
    result = SetupResult(
        setup_name="liquidity_sweep_reversal", fired=True, direction=direction,
        required_conditions=[
            ConditionResult(
                name="liquidity_pool_swept_this_bar", satisfied=True, detail="",
                evidence={"zone_high": zone_high, "zone_low": zone_low, "direction": "buy_side" if direction == "SHORT" else "sell_side"},
            ),
            ConditionResult(name="cvd_confirms_reversal", satisfied=True, detail="", evidence={}),
        ],
        additional_evidence=[], evidence_count=0, reasoning="fired",
        symbol=snapshot.symbol, timestamp=snapshot.timestamp,
    )
    return EngineDecision(symbol=snapshot.symbol, timestamp=snapshot.timestamp, all_results=[result], fired_setups=[result])


def _no_fire_decision(snapshot):
    return EngineDecision(symbol=snapshot.symbol, timestamp=snapshot.timestamp, all_results=[], fired_setups=[])


def _candle(close, high=None, low=None, timestamp=START):
    return {"timestamp": timestamp, "open": close, "high": high or close + 1, "low": low or close - 1, "close": close, "volume": 10.0}


# =========================================================
# strategy_callback
# =========================================================


def test_strategy_callback_ignores_when_no_15m_history():
    coordinator = _StubCoordinator()
    engine = _StubEngine(_no_fire_decision)
    strategy_callback, _ = make_strategy_engine_v2_callbacks(engine, coordinator)

    result = strategy_callback(_candle(100.0), {"BTCUSDT": {"15m": []}})

    assert result["decision"] == "IGNORE"
    assert coordinator.calls == []  # never even called the coordinator


def test_strategy_callback_returns_ignore_when_no_setup_fires():
    coordinator = _StubCoordinator()
    engine = _StubEngine(_no_fire_decision)
    strategy_callback, _ = make_strategy_engine_v2_callbacks(engine, coordinator)

    market_snapshot = {"BTCUSDT": {"15m": [_candle(100.0)]}}
    result = strategy_callback(_candle(100.0), market_snapshot)

    assert result["decision"] == "IGNORE"
    assert len(coordinator.calls) == 1


def test_strategy_callback_enriches_decision_with_regime_and_session_context():
    class _RegimeCoordinator(_StubCoordinator):
        def sync_and_build(self, candles_15m, current_price, timestamp):
            snap = super().sync_and_build(candles_15m, current_price, timestamp)
            return MarketIntelligenceSnapshot(
                symbol=snap.symbol, timeframe=snap.timeframe, timestamp=snap.timestamp,
                current_price=snap.current_price,
                structure={"market_structure": "BULLISH"}, zones=[], levels=[],
                order_flow={"delta": {}, "cvd": {}},
                sessions={"active_now": ["london"], "previous_period_high_low": {}},
                intermarket={}, volume_profile={}, data_quality={},
            )

    coordinator = _RegimeCoordinator()
    engine = _StubEngine(_no_fire_decision)
    strategy_callback, _ = make_strategy_engine_v2_callbacks(engine, coordinator)

    result = strategy_callback(_candle(100.0), {"BTCUSDT": {"15m": [_candle(100.0)]}})

    assert result["market_structure_regime"] == "BULLISH"
    assert result["active_sessions"] == ["london"]


def test_strategy_callback_returns_fired_setup_decision():
    coordinator = _StubCoordinator()
    engine = _StubEngine(lambda snap: _fired_decision(snap, "LONG", zone_high=99.0, zone_low=95.0))
    strategy_callback, _ = make_strategy_engine_v2_callbacks(engine, coordinator)

    market_snapshot = {"BTCUSDT": {"15m": [_candle(100.0)]}}
    result = strategy_callback(_candle(100.0), market_snapshot)

    assert result["decision"] == "LONG"
    assert result["setup_name"] == "liquidity_sweep_reversal"


# =========================================================
# trade_setup_callback - stop-loss placement
# =========================================================


def test_trade_setup_callback_raises_without_a_prior_fired_setup():
    coordinator = _StubCoordinator()
    engine = _StubEngine(_no_fire_decision)
    _, trade_setup_callback = make_strategy_engine_v2_callbacks(engine, coordinator)

    with pytest.raises(ValueError):
        trade_setup_callback("LONG", _candle(100.0), {"BTCUSDT": {"15m": []}}, current_equity=10_000.0)


def test_long_stop_placed_beyond_swept_zone_low():
    coordinator = _StubCoordinator()
    engine = _StubEngine(lambda snap: _fired_decision(snap, "LONG", zone_high=99.0, zone_low=95.0))
    strategy_callback, trade_setup_callback = make_strategy_engine_v2_callbacks(engine, coordinator)

    current_candle = _candle(100.0)
    strategy_callback(current_candle, {"BTCUSDT": {"15m": [current_candle]}})

    setup = trade_setup_callback("LONG", current_candle, {"BTCUSDT": {"15m": [current_candle]}}, current_equity=10_000.0)

    assert setup.side == "LONG"
    assert setup.stop_loss < 95.0  # beyond (below) the swept zone's low edge
    assert setup.stop_loss < setup.entry_price
    assert setup.take_profit > setup.entry_price
    assert setup.risk_reward_ratio == pytest.approx(2.0)  # fixed 2R, matching the old engine


def test_short_stop_placed_beyond_swept_zone_high():
    coordinator = _StubCoordinator()
    engine = _StubEngine(lambda snap: _fired_decision(snap, "SHORT", zone_high=105.0, zone_low=101.0))
    strategy_callback, trade_setup_callback = make_strategy_engine_v2_callbacks(engine, coordinator)

    current_candle = _candle(100.0)
    strategy_callback(current_candle, {"BTCUSDT": {"15m": [current_candle]}})

    setup = trade_setup_callback("SHORT", current_candle, {"BTCUSDT": {"15m": [current_candle]}}, current_equity=10_000.0)

    assert setup.side == "SHORT"
    assert setup.stop_loss > 105.0  # beyond (above) the swept zone's high edge
    assert setup.stop_loss > setup.entry_price
    assert setup.take_profit < setup.entry_price
    assert setup.risk_reward_ratio == pytest.approx(2.0)


def test_long_falls_back_to_min_risk_floor_when_zone_stop_too_tight():
    coordinator = _StubCoordinator()
    # zone_low very close to entry (100.0) - natural risk would be tiny.
    engine = _StubEngine(lambda snap: _fired_decision(snap, "LONG", zone_high=100.1, zone_low=99.999))
    strategy_callback, trade_setup_callback = make_strategy_engine_v2_callbacks(engine, coordinator)

    current_candle = _candle(100.0)
    strategy_callback(current_candle, {"BTCUSDT": {"15m": [current_candle]}})

    setup = trade_setup_callback("LONG", current_candle, {"BTCUSDT": {"15m": [current_candle]}}, current_equity=10_000.0)

    risk = setup.entry_price - setup.stop_loss
    assert risk == pytest.approx(setup.entry_price * 0.006, rel=1e-3)  # MIN_RISK_PERCENT floor applied


def test_long_falls_back_when_zone_low_is_above_entry():
    coordinator = _StubCoordinator()
    # Degenerate/stale case: zone sits AT/ABOVE entry - a naive stop
    # would violate "LONG stop must be below entry".
    engine = _StubEngine(lambda snap: _fired_decision(snap, "LONG", zone_high=102.0, zone_low=100.5))
    strategy_callback, trade_setup_callback = make_strategy_engine_v2_callbacks(engine, coordinator)

    current_candle = _candle(100.0)
    strategy_callback(current_candle, {"BTCUSDT": {"15m": [current_candle]}})

    setup = trade_setup_callback("LONG", current_candle, {"BTCUSDT": {"15m": [current_candle]}}, current_equity=10_000.0)

    assert setup.stop_loss < setup.entry_price  # never raises, always produces a valid setup


def test_risk_percent_matches_old_engine_convention():
    coordinator = _StubCoordinator()
    engine = _StubEngine(lambda snap: _fired_decision(snap, "LONG", zone_high=99.0, zone_low=95.0))
    strategy_callback, trade_setup_callback = make_strategy_engine_v2_callbacks(engine, coordinator)

    current_candle = _candle(100.0)
    strategy_callback(current_candle, {"BTCUSDT": {"15m": [current_candle]}})
    setup = trade_setup_callback("LONG", current_candle, {"BTCUSDT": {"15m": [current_candle]}}, current_equity=10_000.0)

    risk_amount = (setup.entry_price - setup.stop_loss) * setup.quantity
    assert risk_amount == pytest.approx(10_000.0 * 0.01, rel=1e-2)  # 1% of equity risked
