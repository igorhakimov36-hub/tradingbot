from datetime import datetime, timezone

import pytest

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot
from strategy.setups.base import ConditionResult, SetupResult
from strategy.strategy_engine_v2 import StrategyEngineV2, engine_decision_to_dict

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _snapshot():
    return MarketIntelligenceSnapshot(
        symbol="BTCUSDT", timeframe="15m", timestamp=START, current_price=100.0,
        structure={}, zones=[], levels=[],
        order_flow={"delta": {}, "cvd": {}},
        sessions={"active_now": [], "previous_period_high_low": {}},
        intermarket={}, volume_profile={}, data_quality={},
    )


class _AlwaysFires:
    name = "always_fires"

    def evaluate(self, snapshot):
        return SetupResult(
            setup_name=self.name, fired=True, direction="LONG",
            required_conditions=[ConditionResult(name="always_true", satisfied=True, detail="", evidence={})],
            additional_evidence=[], evidence_count=0, reasoning="always fires",
            symbol=snapshot.symbol, timestamp=snapshot.timestamp,
        )


class _NeverFires:
    name = "never_fires"

    def evaluate(self, snapshot):
        return SetupResult(
            setup_name=self.name, fired=False, direction=None,
            required_conditions=[ConditionResult(name="always_false", satisfied=False, detail="", evidence={})],
            additional_evidence=[], evidence_count=0, reasoning="never fires",
            symbol=snapshot.symbol, timestamp=snapshot.timestamp,
        )


# =========================================================
# StrategyEngineV2
# =========================================================


def test_engine_requires_at_least_one_setup():
    with pytest.raises(ValueError):
        StrategyEngineV2(symbol="BTCUSDT", setups=[])


def test_engine_evaluates_every_registered_setup():
    engine = StrategyEngineV2(symbol="BTCUSDT", setups=[_AlwaysFires(), _NeverFires()])

    decision = engine.decide(_snapshot())

    assert len(decision.all_results) == 2
    assert len(decision.fired_setups) == 1
    assert decision.fired_setups[0].setup_name == "always_fires"


def test_engine_with_no_fired_setups():
    engine = StrategyEngineV2(symbol="BTCUSDT", setups=[_NeverFires()])

    decision = engine.decide(_snapshot())

    assert decision.fired_setups == []
    assert len(decision.all_results) == 1


def test_engine_never_imports_a_feature_tracker():
    # Structural check of the architectural boundary itself: parse the
    # actual import statements (not docstring prose, which legitimately
    # mentions strategy.features when explaining the boundary).
    import ast

    import strategy.strategy_engine_v2 as module

    source = open(module.__file__, encoding="utf-8").read()
    tree = ast.parse(source)

    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert not any(name.startswith("strategy.features") for name in imported_modules)
    assert "strategy.market_intelligence_coordinator" not in imported_modules


# =========================================================
# engine_decision_to_dict
# =========================================================


def test_decision_dict_for_no_fired_setup():
    engine = StrategyEngineV2(symbol="BTCUSDT", setups=[_NeverFires()])
    decision = engine.decide(_snapshot())

    result_dict = engine_decision_to_dict(decision)

    assert result_dict["decision"] == "IGNORE"
    assert result_dict["setup_name"] is None
    assert result_dict["evidence_count"] == 0
    assert "score" not in result_dict  # V2 never populates a score


def test_decision_dict_for_fired_setup():
    engine = StrategyEngineV2(symbol="BTCUSDT", setups=[_AlwaysFires()])
    decision = engine.decide(_snapshot())

    result_dict = engine_decision_to_dict(decision)

    assert result_dict["decision"] == "LONG"
    assert result_dict["setup_name"] == "always_fires"
    assert result_dict["reasoning"] == "always fires"
    assert len(result_dict["required_conditions"]) == 1
    assert result_dict["required_conditions"][0]["name"] == "always_true"


def test_decision_dict_uses_first_fired_setup_when_multiple_fire():
    class _AlsoFires:
        name = "also_fires"

        def evaluate(self, snapshot):
            return SetupResult(
                setup_name=self.name, fired=True, direction="SHORT",
                required_conditions=[], additional_evidence=[], evidence_count=0,
                reasoning="also fires", symbol=snapshot.symbol, timestamp=snapshot.timestamp,
            )

    engine = StrategyEngineV2(symbol="BTCUSDT", setups=[_AlwaysFires(), _AlsoFires()])
    decision = engine.decide(_snapshot())

    assert len(decision.fired_setups) == 2
    result_dict = engine_decision_to_dict(decision)
    assert result_dict["setup_name"] == "always_fires"  # first one registered, documented policy
