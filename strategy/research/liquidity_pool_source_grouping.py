"""
Mutually-exclusive Liquidity Pool source grouping for the SOL Funding
Impact / Source-Conditioned S001 Re-analysis sprint. RESEARCH-ONLY,
pure function, no tracker/production dependency.

Frozen groups (docs/sol_funding_source_reanalysis_protocol.md):
1. round_number_only: sources == ["round_number"].
2. round_number_plus_other: "round_number" in sources and len(sources) > 1.
3. no_round_number: "round_number" not in sources.
4. unknown: sources empty/missing - kept explicit, never silently
   folded into another group.

Applied only to `sources` as already recorded on a pool at the moment
it was selected by `_find_fresh_sweep` (the pool's own state at
decision time) - never a later-evolved version of that pool's sources.

A `round_number_only` pool can never satisfy
`LiquiditySweepReversalSetup._multi_source_pool` (which requires
`len(sources) > 1`) by construction - this module's own
`can_satisfy_multi_source` helper makes that structural fact explicit
and testable, rather than left implicit.
"""

from typing import Literal

SourceGroup = Literal["round_number_only", "round_number_plus_other", "no_round_number", "unknown"]


def source_group(sources: list[str]) -> SourceGroup:
    if not sources:
        return "unknown"

    if sources == ["round_number"]:
        return "round_number_only"

    if "round_number" in sources and len(sources) > 1:
        return "round_number_plus_other"

    if "round_number" not in sources:
        return "no_round_number"

    return "unknown"


def can_satisfy_multi_source(sources: list[str]) -> bool:
    """
    Mirrors LiquiditySweepReversalSetup._multi_source_pool's own
    condition (len(sources) > 1) exactly - used to make explicit,
    testable, and pre-registered the structural fact that
    round_number_only pools can never pass via this path.
    """

    return len(sources) > 1
