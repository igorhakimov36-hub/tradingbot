"""
Strategy Engine V2 - Phase 2.1, Step 2.

Consumes ONLY a MarketIntelligenceSnapshot. Never imports or calls a
feature tracker, never touches strategy.features.* - that boundary is
enforced structurally by this module's own imports, not just by
convention.

Decision model
--------------
No weighted scoring (see docs/strategy_engine_v2_architecture.md,
section 4, for the full reasoning behind replacing rather than tuning
the old Decision Engine). This engine evaluates every registered named
Setup against the snapshot and returns every SetupResult, fired or not
- the caller (or the backtest adapter) decides what to do with a fired
setup, this class does not itself pick "the best" one out of several
simultaneous fires beyond taking the first (documented, not hidden -
see EngineDecision).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot
from strategy.setups.base import Setup, SetupResult


@dataclass(frozen=True)
class EngineDecision:
    symbol: str
    timestamp: datetime
    all_results: list[SetupResult]
    fired_setups: list[SetupResult]


class StrategyEngineV2:
    """
    One instance per backtest run (or per live session), matching the
    lifecycle convention of every other stateful object in this
    codebase - though this engine itself holds no state between calls
    beyond its fixed list of registered setups.
    """

    def __init__(self, symbol: str, setups: list[Setup]):
        if not setups:
            raise ValueError("setups cannot be empty")

        self.symbol = symbol
        self.setups = setups

    def decide(self, snapshot: MarketIntelligenceSnapshot) -> EngineDecision:
        all_results = [setup.evaluate(snapshot) for setup in self.setups]
        fired_setups = [result for result in all_results if result.fired]

        return EngineDecision(
            symbol=self.symbol,
            timestamp=snapshot.timestamp,
            all_results=all_results,
            fired_setups=fired_setups,
        )


def engine_decision_to_dict(decision: EngineDecision) -> dict[str, Any]:
    """
    Adapts an EngineDecision into the {"decision": ..., ...} shape
    BacktestRunner.run_strategy()'s strategy_callback contract expects
    (see backtesting/backtest_runner.py). If more than one setup fires
    on the same bar, the first is used - with only one setup registered
    this cannot happen yet; a real ranking policy for simultaneous
    fires is future work once a second setup exists, not decided here.

    "score" is deliberately never populated - Strategy Engine V2 has no
    scoring concept (see module docstring). "setup_name"/"reasoning"/
    "required_conditions"/"additional_evidence"/"evidence_count" are
    the complete reasoning chain, all threaded into the Trade Journal's
    metadata by BacktestRunner unchanged.
    """

    if not decision.fired_setups:
        return {
            "decision": "IGNORE",
            "setup_name": None,
            "reasoning": "No setup fired on this bar.",
            "evidence_count": 0,
            "required_conditions": [],
            "additional_evidence": [],
        }

    result = decision.fired_setups[0]

    return {
        "decision": result.direction,
        "setup_name": result.setup_name,
        "reasoning": result.reasoning,
        "evidence_count": result.evidence_count,
        "required_conditions": [vars(c) for c in result.required_conditions],
        "additional_evidence": [vars(c) for c in result.additional_evidence],
    }
