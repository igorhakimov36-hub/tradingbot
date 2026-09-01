"""
Setup Evaluation Framework - Phase 2.1, Step 2/3.

Purpose
-------
Replaces the old weighted-scoring Decision Engine (docs/
strategy_engine_v2_architecture.md, section 4: "recommend replacing
it, not tuning it"). A decision is the output of evaluating explicit,
named institutional setups against a MarketIntelligenceSnapshot - never
a hand-weighted sum of sub-scores. Every setup:

- reads ONLY a MarketIntelligenceSnapshot (never a tracker, never raw
  candles) - the Snapshot Builder boundary applies here too;
- has no arbitrary numeric weights anywhere;
- records exactly which conditions were checked, what raw evidence
  satisfied or failed each one, and a human-readable reasoning string -
  the "complete reasoning chain" every trade must carry into the Trade
  Journal;
- distinguishes REQUIRED conditions (all must be true for the setup to
  fire) from ADDITIONAL evidence (recorded for context/statistics, not
  gating) - `evidence_count` is a raw count of confirming context, in
  the same descriptive spirit Liquidity Pools already exposes
  `sources`/`touch_count`, never a weighted composite pretending to be
  a probability.

Adding a new setup means adding a new class implementing evaluate() -
nothing here, in StrategyEngineV2, or in the Snapshot Builder needs to
change.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot

Side = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class ConditionResult:
    """
    One named, independently-inspectable check against the snapshot -
    the atomic unit of the reasoning chain. `evidence` carries the raw
    field values that were actually compared, not a restatement of the
    verdict - so a Trade Journal entry (or a future statistical study)
    can see exactly what was true, not just that something fired.
    """

    name: str
    satisfied: bool
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SetupResult:
    setup_name: str
    fired: bool
    direction: Side | None
    required_conditions: list[ConditionResult]
    additional_evidence: list[ConditionResult]
    evidence_count: int
    reasoning: str
    symbol: str
    timestamp: datetime


class Setup(Protocol):
    """
    A named institutional setup. Implementations must be pure
    functions of the snapshot they are given - no internal state
    carried between calls (any "did this already fire recently"
    bookkeeping belongs in the snapshot's own zone/level history, which
    is already replay-safe, not invented fresh per setup).
    """

    name: str

    def evaluate(self, snapshot: MarketIntelligenceSnapshot) -> SetupResult: ...
