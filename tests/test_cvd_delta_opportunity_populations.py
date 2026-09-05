"""
Tests for strategy/research/cvd_delta_opportunity_populations.py.
"""

import pytest

from strategy.research.cvd_delta_opportunity_populations import (
    classify_confirmation,
    classify_opportunity,
)


def test_long_confirmed_by_bullish():
    assert classify_confirmation("cvd_direction", "BULLISH", "LONG") == "CONFIRMS"


def test_long_contradicted_by_bearish():
    assert classify_confirmation("cvd_direction", "BEARISH", "LONG") == "CONTRADICTS"


def test_short_confirmed_by_bearish():
    assert classify_confirmation("price_cvd_divergence_flag", "bearish_divergence", "SHORT") == "CONFIRMS"


def test_short_contradicted_by_bullish():
    assert classify_confirmation("price_cvd_divergence_flag", "bullish_divergence", "SHORT") == "CONTRADICTS"


def test_neutral_reading_is_neutral_regardless_of_direction():
    assert classify_confirmation("cvd_exhaustion_flag", "none", "LONG") == "NEUTRAL"
    assert classify_confirmation("cvd_exhaustion_flag", "none", "SHORT") == "NEUTRAL"


def test_invalid_candidate_direction_raises():
    with pytest.raises(ValueError):
        classify_confirmation("cvd_direction", "BULLISH", "SIDEWAYS")


# =========================================================
# Requirement 5: CONFIRMS/CONTRADICTS/NEUTRAL mutually exclusive
# =========================================================


def test_verdicts_mutually_exclusive_across_all_real_field_values():
    all_values_per_field = {
        "cvd_direction": ["BULLISH", "BEARISH", "NEUTRAL", None],
        "delta_direction": ["BULLISH", "BEARISH", "NEUTRAL", None],
        "price_cvd_divergence_flag": ["bullish_divergence", "bearish_divergence", "none"],
        "cvd_exhaustion_flag": ["bullish_exhaustion", "bearish_exhaustion", "none"],
    }
    possible_verdicts = {"CONFIRMS", "CONTRADICTS", "NEUTRAL"}

    for field, values in all_values_per_field.items():
        for value in values:
            for direction in ("LONG", "SHORT"):
                verdict = classify_confirmation(field, value, direction)
                assert verdict in possible_verdicts
                # exactly one verdict per call - never a combination
                assert isinstance(verdict, str)


def test_classify_opportunity_returns_one_verdict_per_field():
    result = classify_opportunity(
        candidate_direction="LONG",
        field_values={
            "cvd_direction": "BULLISH",
            "delta_direction": "BEARISH",
            "price_cvd_divergence_flag": "none",
            "cvd_exhaustion_flag": "bullish_exhaustion",
        },
    )
    assert result == {
        "cvd_direction": "CONFIRMS",
        "delta_direction": "CONTRADICTS",
        "price_cvd_divergence_flag": "NEUTRAL",
        "cvd_exhaustion_flag": "CONFIRMS",
    }
