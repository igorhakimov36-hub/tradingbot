"""
Liquidity Sweep Staleness Telemetry - pure, testable analysis functions.
RESEARCH-ONLY, not wired into production.

Architecture decision (documented, not silently assumed)
------------------------------------------------------------------------
This telemetry COULD be added as new, additive dict keys on production
LiquidityPoolTracker's own snapshot() output (a new key is, by itself,
never a breaking change - no existing consumer reads a key it doesn't
already expect). That option was considered and rejected for THIS
sprint specifically: this remains a hypothesis-validation sprint, not an
implementation-authorization sprint, and every one of this project's
prior research sprints (Order Block Policy B/C, Liquidity Pool Policy
B/C) has kept the exact same boundary - zero production files touched
during research, a separate, explicit implementation-authorization step
required before anything here could ever reach `strategy/features/`.
Keeping that boundary here too costs nothing (the pure functions below
are driven by the exact same real, unmodified LiquidityPoolTracker
output a harness script assembles) and keeps this sprint's blast radius
at exactly zero production files, matching every prior sprint's own
choice. `strategy/features/liquidity_pool.py` is not imported for
anything other than a direct, read-only confirmation test that its
own behavior is unaffected.

Classification (four mutually exclusive categories, applied to a
pool's already-fully-known history)
------------------------------------------------------------------------
- SAME_CANDLE_SWEEP: Policy A's own sweep condition fires with no clean
  close beyond the boundary ever having occurred strictly before the
  sweep candle.
- TIMELY_RECLAIM: a clean close beyond DID occur first, and Policy A's
  own sweep confirms within 1-16 completed candles of that first close
  beyond (bar 0 = the close-beyond candle itself; bar 1 = the next
  completed candle; the window is inclusive of bar 16).
- LATE_RECLAIM: same as above, but confirmation takes more than 16
  completed candles (bar 17 or later).
- UNRESOLVED_OR_CENSORED: Policy A's own sweep never confirms before the
  dataset ends - regardless of whether a close-beyond ever occurred.
  Never conflated with "accepted liquidity" - it is explicitly a
  right-censored observation, not a resolved outcome of any kind.

`primary_window` (16) is a parameter, not a hardcoded constant - the
frozen protocol document is the source of truth for its value in this
experiment; 8 and 32 are sensitivity re-runs of the identical function.
"""

from typing import Any, Literal

StalenessClass = Literal[
    "SAME_CANDLE_SWEEP", "TIMELY_RECLAIM", "LATE_RECLAIM", "UNRESOLVED_OR_CENSORED",
]


def classify_staleness(
    current_rule_swept_bar_i: int | None,
    first_close_beyond_bar_i: int | None,
    primary_window: int = 16,
) -> StalenessClass:
    """
    current_rule_swept_bar_i: the bar index Policy A's own
    (production-identical) same-candle wick-beyond-then-close-back rule
    actually fired, or None if it never did before the dataset ended.

    first_close_beyond_bar_i: the bar index of the pool's first clean
    close beyond its outer boundary with no same-candle rejection, or
    None if that never occurred.
    """

    if current_rule_swept_bar_i is not None:
        if first_close_beyond_bar_i is None or first_close_beyond_bar_i >= current_rule_swept_bar_i:
            return "SAME_CANDLE_SWEEP"

        bars_beyond = current_rule_swept_bar_i - first_close_beyond_bar_i
        if bars_beyond <= primary_window:
            return "TIMELY_RECLAIM"
        return "LATE_RECLAIM"

    return "UNRESOLVED_OR_CENSORED"


def first_passage_outcome(
    direction: Literal["buy_side", "sell_side"],
    reference_close: float,
    atr: float,
    forward_candles: list[dict[str, Any]],
    favorable_atr_multiple: float = 1.0,
    adverse_atr_multiple: float = 1.0,
) -> dict[str, Any]:
    """
    Sequential, unconditional first-passage from the candle AFTER sweep
    confirmation (forward_candles must start there - the confirmation
    candle itself contributes no outcome). "Expected reversal direction"
    for a swept buy_side pool is DOWN (a short-reversal setup, matching
    LiquiditySweepReversalSetup's own direction mapping); for a swept
    sell_side pool it is UP.

    Returns {"outcome": "favorable" | "adverse" | "censored",
    "ambiguous": bool, "bars": int | None}. A candle satisfying both
    the favorable and adverse condition simultaneously is conservatively
    counted as "adverse" (the primary, conservative convention for this
    experiment - not the "reclaim" convention used in the Order
    Block/Policy C sprints, since here "adverse" IS the conservative/
    unfavorable direction by definition).
    """

    for i, candle in enumerate(forward_candles, start=1):
        if direction == "buy_side":
            # Swept buy_side pool -> expected reversal is DOWN.
            favorable = (reference_close - candle["low"]) >= favorable_atr_multiple * atr
            adverse = (candle["high"] - reference_close) >= adverse_atr_multiple * atr
        else:
            favorable = (candle["high"] - reference_close) >= favorable_atr_multiple * atr
            adverse = (reference_close - candle["low"]) >= adverse_atr_multiple * atr

        if favorable and adverse:
            return {"outcome": "adverse", "ambiguous": True, "bars": i}
        if adverse:
            return {"outcome": "adverse", "ambiguous": False, "bars": i}
        if favorable:
            return {"outcome": "favorable", "ambiguous": False, "bars": i}

    return {"outcome": "censored", "ambiguous": False, "bars": None}
