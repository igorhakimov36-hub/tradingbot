"""
Liquidity Pool Hybrid Policy C - bounded failed-acceptance state machine.
RESEARCH-ONLY, not wired into production. LiquidityPoolTracker
(strategy/features/liquidity_pool.py) is completely unmodified.

Implements exactly docs/liquidity_pool_policy_c_validation_protocol.md's
frozen state-machine specification - see that document for the full
rationale and the explicit answers to every definitional question
(which boundary, whether the 16th candle counts, same-bar ambiguity,
distinct identity for new pools, repeated closes during the pending
window). This module must not be altered after VALIDATION results are
seen.

States: UNSWEPT -> ACCEPTANCE_PENDING -> {SWEPT (same_candle or
multi_candle) | ACCEPTED_INVALIDATED}. SWEPT and ACCEPTED_INVALIDATED
are both terminal - a pool never re-enters UNSWEPT or ACCEPTANCE_PENDING
after reaching either, and emits at most one sweep event ever.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

Direction = Literal["buy_side", "sell_side"]
PolicyCState = Literal["UNSWEPT", "ACCEPTANCE_PENDING", "SWEPT", "ACCEPTED_INVALIDATED"]
SweepType = Literal["same_candle", "multi_candle"]


@dataclass
class PolicyCPoolState:
    """
    Shadows a single, already-created LiquidityPool (from the real,
    unmodified LiquidityPoolTracker) with Policy C's bounded lifecycle.
    Call apply_candle() once per candle, in the same order the real
    tracker itself receives, passing that candle's currently-live zone
    bounds (as the real tracker sees them at that moment) for the
    same-candle check, and this instance's own frozen boundary is used
    automatically once ACCEPTANCE_PENDING begins.
    """

    direction: Direction
    created_at: Any
    window_bars: int

    state: PolicyCState = "UNSWEPT"
    frozen_boundary: float | None = None
    pending_entered_bar_i: int | None = None
    sweep_type: SweepType | None = None
    sweep_bar_i: int | None = None
    sweep_timestamp: Any = None
    invalidated_bar_i: int | None = None
    invalidated_timestamp: Any = None
    censored: bool = False

    def apply_candle(
        self,
        candle: dict[str, Any],
        bar_i: int,
        live_zone_high: float,
        live_zone_low: float,
        timestamp_key: str = "timestamp",
    ) -> None:
        if self.state in ("SWEPT", "ACCEPTED_INVALIDATED"):
            return  # terminal - no event may be emitted twice, ever

        # Same-candle check always runs first, regardless of current
        # state (UNSWEPT or ACCEPTANCE_PENDING) - identical to Policy A's
        # own rule, using the LIVE zone bounds (matching production's own
        # convention of checking against the current, possibly-widened
        # zone, not a frozen one, for this specific check only).
        if self.direction == "buy_side":
            same_candle_sweep = candle["high"] > live_zone_high and candle["close"] < live_zone_high
        else:
            same_candle_sweep = candle["low"] < live_zone_low and candle["close"] > live_zone_low

        if same_candle_sweep:
            self.state = "SWEPT"
            self.sweep_type = "same_candle"
            self.sweep_bar_i = bar_i
            self.sweep_timestamp = candle[timestamp_key]
            return

        if self.state == "UNSWEPT":
            if self.direction == "buy_side":
                close_beyond = candle["close"] > live_zone_high
            else:
                close_beyond = candle["close"] < live_zone_low

            if close_beyond:
                self.state = "ACCEPTANCE_PENDING"
                self.frozen_boundary = live_zone_high if self.direction == "buy_side" else live_zone_low
                self.pending_entered_bar_i = bar_i
            return

        # state == "ACCEPTANCE_PENDING"
        bars_since_pending = bar_i - self.pending_entered_bar_i

        if bars_since_pending <= self.window_bars:
            if self.direction == "buy_side":
                reclaimed = candle["close"] < self.frozen_boundary
            else:
                reclaimed = candle["close"] > self.frozen_boundary

            if reclaimed:
                self.state = "SWEPT"
                self.sweep_type = "multi_candle"
                self.sweep_bar_i = bar_i
                self.sweep_timestamp = candle[timestamp_key]
            # else: repeated close beyond during the window does not
            # reset or extend it - remain ACCEPTANCE_PENDING.
        else:
            # bars_since_pending > window_bars: the window (inclusive of
            # its own window_bars-th candle) has passed with no reclaim.
            self.state = "ACCEPTED_INVALIDATED"
            self.invalidated_bar_i = bar_i
            self.invalidated_timestamp = candle[timestamp_key]

    def finalize_censoring(self) -> None:
        """Call once, at end-of-window, if the pool never reached a
        terminal state - marks it right-censored rather than silently
        leaving it in a non-terminal state."""
        if self.state not in ("SWEPT", "ACCEPTED_INVALIDATED"):
            self.censored = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "created_at": self.created_at,
            "window_bars": self.window_bars,
            "state": self.state,
            "sweep_type": self.sweep_type,
            "sweep_bar_i": self.sweep_bar_i,
            "sweep_timestamp": self.sweep_timestamp,
            "invalidated_bar_i": self.invalidated_bar_i,
            "invalidated_timestamp": self.invalidated_timestamp,
            "censored": self.censored,
        }
