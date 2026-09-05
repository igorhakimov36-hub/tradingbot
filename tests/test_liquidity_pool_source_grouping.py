"""
Tests for strategy/research/liquidity_pool_source_grouping.py.
"""

from strategy.research.liquidity_pool_source_grouping import can_satisfy_multi_source, source_group


def test_round_number_only():
    assert source_group(["round_number"]) == "round_number_only"


def test_round_number_plus_other():
    assert source_group(["round_number", "equal_highs"]) == "round_number_plus_other"
    assert source_group(["equal_highs", "round_number"]) == "round_number_plus_other"


def test_no_round_number_single_source():
    assert source_group(["equal_highs"]) == "no_round_number"


def test_no_round_number_multi_source():
    assert source_group(["equal_highs", "session_high"]) == "no_round_number"


def test_unknown_when_empty():
    assert source_group([]) == "unknown"


def test_unknown_when_missing_is_caller_responsibility_empty_list():
    # This module only ever receives an already-extracted list; an
    # empty list is the frozen "missing/unknown" representation.
    assert source_group([]) == "unknown"


def test_groups_are_mutually_exclusive_over_a_representative_sample():
    samples = [
        ["round_number"], ["round_number", "equal_highs"], ["round_number", "session_high"],
        ["equal_highs"], ["equal_lows"], ["session_high"], ["equal_highs", "session_high"],
        [], ["equal_highs", "round_number", "session_high"],
    ]
    for sources in samples:
        group = source_group(sources)
        assert group in ("round_number_only", "round_number_plus_other", "no_round_number", "unknown")


# =========================================================
# Structural fact: round_number_only can never satisfy multi_source
# =========================================================


def test_round_number_only_can_never_satisfy_multi_source():
    assert can_satisfy_multi_source(["round_number"]) is False


def test_multi_source_pools_can_satisfy_multi_source():
    assert can_satisfy_multi_source(["round_number", "equal_highs"]) is True
    assert can_satisfy_multi_source(["equal_highs", "session_high"]) is True


def test_single_source_non_round_number_also_cannot_satisfy_multi_source():
    # Not unique to round numbers - ANY single-source pool structurally
    # cannot satisfy multi_source; round numbers just dominate the
    # single-source population (~93% of all pools per prior sprints).
    assert can_satisfy_multi_source(["equal_highs"]) is False


# =========================================================
# Determinism
# =========================================================


def test_deterministic():
    sources = ["round_number", "equal_highs"]
    assert source_group(sources) == source_group(list(sources))
