"""
CVD-blind opportunity classification for the Signal-Value research
sprint. RESEARCH-ONLY, pure functions.

Population B (per the frozen protocol): for S001/S007, the exact
decision stage immediately before any CVD/Delta field is applied - i.e.
every bar that satisfies every NON-CVD required condition, captured
WITHOUT conditioning on what CVD itself reads that bar (so the
candidates CVD would have rejected are never silently excluded). For
each such candidate, every current CVD/Delta field's own reading at
that bar is classified relative to the candidate's own already-
determined direction (established independently of CVD - the swept
pool's direction for S001, the BOS-implied trend direction for S007).
"""

from typing import Any, Literal

from strategy.research.cvd_delta_native_events import classify_directional

Verdict = Literal["CONFIRMS", "CONTRADICTS", "NEUTRAL"]


def classify_confirmation(field_name: str, field_value: Any, candidate_direction: str) -> Verdict:
    """
    `candidate_direction`: "LONG" or "SHORT" - the candidate's own
    already-determined direction, established independently of CVD.
    Matches the exact mapping the real setups already use: a LONG
    candidate is confirmed by a "bullish" reading, a SHORT candidate by
    a "bearish" reading (LiquiditySweepReversalSetup._cvd_confirms's
    own target_exhaustion/target_divergence mapping;
    TrendContinuationConfluenceSetup._cvd_confirms_trend's own
    BULLISH/BEARISH target mapping) - both already implement this same
    rule, reused here for classification only, never re-derived
    differently.
    """

    if candidate_direction not in ("LONG", "SHORT"):
        raise ValueError(f"candidate_direction must be LONG or SHORT, got {candidate_direction!r}")

    direction = classify_directional(field_name, field_value)

    if direction is None:
        return "NEUTRAL"

    expected = "bullish" if candidate_direction == "LONG" else "bearish"

    return "CONFIRMS" if direction == expected else "CONTRADICTS"


def classify_opportunity(
    candidate_direction: str,
    field_values: dict[str, Any],
) -> dict[str, Verdict]:
    """
    `field_values`: {field_name: raw_value} for every field to classify
    at one candidate opportunity. Returns {field_name: verdict}.
    Verdicts are mutually exclusive by construction (each field
    produces exactly one of CONFIRMS/CONTRADICTS/NEUTRAL).
    """

    return {
        field_name: classify_confirmation(field_name, value, candidate_direction)
        for field_name, value in field_values.items()
    }
