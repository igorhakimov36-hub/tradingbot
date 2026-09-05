"""
Generic, parameterized StrategyEngineV2 <-> BacktestRunner adapter for
the SOL Multi-Module Setup Discovery sprint's 3 research candidates.

The existing production adapter
(strategy/strategy_engine_v2_backtest_adapter.py) hardcodes S001's own
stop-placement rule (the swept Liquidity Pool's zone edge) directly
inside trade_setup_callback - it cannot be reused as-is for candidates
with different stop/target conventions. This module factors out the
identical strategy_callback/trade_setup_callback wiring and parameterizes
ONLY the stop/target construction, via a small per-candidate function -
a "small research adapter for existing outputs," reusing
create_risk_based_trade_setup (the same production sizing helper S001
uses) unmodified, so position sizing/risk convention is identical to
production, not reinvented.

Same 1% equity risk per trade, same MIN_RISK_PERCENT floor, same
STOP_BUFFER_PCT as the production adapter - this file changes WHICH
stop/target a setup's own evidence (and, where needed, the snapshot
that produced it) implies, never the risk/sizing mechanics around it.
"""

from typing import Any, Callable, Protocol

from strategy.market_intelligence_coordinator import MarketIntelligenceCoordinator
from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot
from strategy.setups.base import SetupResult
from strategy.strategy_engine_v2 import StrategyEngineV2, engine_decision_to_dict
from strategy.trade_setup import TradeSetup, create_risk_based_trade_setup

MIN_RISK_PERCENT = 0.006  # matches strategy_engine_v2_backtest_adapter.py's own floor rationale
STOP_BUFFER_PCT = 0.001  # matches the existing project-wide constant


class StopTargetFn(Protocol):
    def __call__(self, decision: str, entry: float, result: SetupResult, snapshot: MarketIntelligenceSnapshot) -> tuple[float, float]: ...


def make_multi_module_callbacks(
    engine: StrategyEngineV2,
    coordinator: MarketIntelligenceCoordinator,
    stop_target_fn: StopTargetFn,
    candle_timeframe_key: str = "15m",
    timestamp_key: str = "timestamp",
    risk_percent: float = 1.0,
) -> tuple[Callable[..., dict[str, Any]], Callable[..., TradeSetup]]:
    last_fired: dict[str, SetupResult | None] = {"result": None}
    last_snapshot: dict[str, MarketIntelligenceSnapshot | None] = {"value": None}

    def strategy_callback(current_candle: dict[str, Any], market_snapshot: dict[str, Any]) -> dict[str, Any]:
        candles_15m = market_snapshot[engine.symbol].get(candle_timeframe_key, [])

        if not candles_15m:
            last_fired["result"] = None
            last_snapshot["value"] = None
            return {
                "decision": "IGNORE", "setup_name": None, "reasoning": "no 15m history available yet",
                "evidence_count": 0, "required_conditions": [], "additional_evidence": [],
            }

        snapshot = coordinator.sync_and_build(
            candles_15m, current_price=current_candle["close"], timestamp=candles_15m[-1][timestamp_key],
        )

        decision = engine.decide(snapshot)
        last_fired["result"] = decision.fired_setups[0] if decision.fired_setups else None
        last_snapshot["value"] = snapshot

        result_dict = engine_decision_to_dict(decision)
        result_dict["market_structure_regime"] = snapshot.structure.get("market_structure")
        return result_dict

    def trade_setup_callback(
        decision: str, current_candle: dict[str, Any], market_snapshot: dict[str, Any], current_equity: float,
    ) -> TradeSetup:
        result = last_fired["result"]
        snapshot = last_snapshot["value"]

        if result is None or snapshot is None:
            raise ValueError(
                "trade_setup_callback called with no fired setup recorded - "
                "strategy_callback and trade_setup_callback must be called in the same replay step"
            )

        entry = current_candle["close"]
        stop, take_profit = stop_target_fn(decision, entry, result, snapshot)

        return create_risk_based_trade_setup(
            side=decision, entry_price=entry, stop_loss=stop, take_profit=take_profit,
            equity=current_equity, risk_percent=risk_percent,
        )

    return strategy_callback, trade_setup_callback


def _apply_min_risk_floor_long(entry: float, stop: float) -> float:
    if stop >= entry:
        stop = entry * (1 - MIN_RISK_PERCENT)
    if entry - stop < entry * MIN_RISK_PERCENT:
        stop = entry * (1 - MIN_RISK_PERCENT)
    return stop


def _apply_min_risk_floor_short(entry: float, stop: float) -> float:
    if stop <= entry:
        stop = entry * (1 + MIN_RISK_PERCENT)
    if stop - entry < entry * MIN_RISK_PERCENT:
        stop = entry * (1 + MIN_RISK_PERCENT)
    return stop


def s008_stop_target(decision: str, entry: float, result: SetupResult, snapshot: MarketIntelligenceSnapshot) -> tuple[float, float]:
    evidence = result.required_conditions[0].evidence  # displaced_order_block_exists
    zone_high = evidence["zone_high"]
    zone_low = evidence["zone_low"]

    if decision == "LONG":
        stop = _apply_min_risk_floor_long(entry, zone_low * (1 - STOP_BUFFER_PCT))
        risk = entry - stop
        return stop, entry + risk * 2.0

    stop = _apply_min_risk_floor_short(entry, zone_high * (1 + STOP_BUFFER_PCT))
    risk = stop - entry
    return stop, entry - risk * 2.0


def s009_stop_target(decision: str, entry: float, result: SetupResult, snapshot: MarketIntelligenceSnapshot) -> tuple[float, float]:
    # required_conditions[0] = closed_further_in_reversal_direction, whose
    # evidence carries the bar-N excursion close (this Setup's own
    # disclosed surrogate for "bar N's own high/low" - see
    # s009_failed_auction_reversal.py's own docstring).
    excursion_close = result.required_conditions[0].evidence["excursion_bar_close"]

    if decision == "LONG":
        stop = _apply_min_risk_floor_long(entry, excursion_close * (1 - STOP_BUFFER_PCT))
        risk = entry - stop
        return stop, entry + risk * 2.0

    stop = _apply_min_risk_floor_short(entry, excursion_close * (1 + STOP_BUFFER_PCT))
    risk = stop - entry
    return stop, entry - risk * 2.0


def s011_stop_target(decision: str, entry: float, result: SetupResult, snapshot: MarketIntelligenceSnapshot) -> tuple[float, float]:
    extension_evidence = result.required_conditions[1].evidence  # value_area_extension
    bucket_size = extension_evidence["bucket_size"]
    profile = snapshot.volume_profile.get("current_forming_profile") or {}
    poc_price = profile.get("poc_price")

    if decision == "LONG":
        stop = _apply_min_risk_floor_long(entry, entry - bucket_size)
        if poc_price is not None and poc_price > entry:
            return stop, poc_price
        return stop, entry + (entry - stop) * 2.0  # fallback: POC not beyond entry, use 2R

    stop = _apply_min_risk_floor_short(entry, entry + bucket_size)
    if poc_price is not None and poc_price < entry:
        return stop, poc_price
    return stop, entry - (stop - entry) * 2.0  # fallback: POC not beyond entry, use 2R
