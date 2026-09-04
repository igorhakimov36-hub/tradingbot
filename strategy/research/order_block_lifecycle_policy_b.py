"""
Order Block Lifecycle Research - Policy B (Separated Lifecycle Candidate)

RESEARCH-ONLY. Not wired into production. `OrderBlockTracker`
(strategy/features/order_block.py) and `BreakerBlockTracker` are
completely unmodified by this module - this is an explicitly separate,
disabled-by-default experimental policy, consumed only by research
scripts and this module's own test suite.

Research question
------------------
Does the current production lifecycle (Policy A) prematurely treat a
wick-only full penetration of an Order Block as confirmed invalidation
- creating Breaker-eligible blocks from price action that later
reclaims/rejects rather than genuinely breaking through? Policy B tests
an alternative: full wick penetration remains informative (recorded as
deep mitigation), but confirmed invalidation - and therefore Breaker
eligibility - requires a CLOSE beyond the Order Block's far boundary.

Policy A (current production control, exactly as implemented in
strategy/features/order_block.py - documented here, NOT reimplemented)
------------------------------------------------------------------------
- Touch: OHLC wick overlap with [zone_low, zone_high]
  (`is_touching_zone`).
- Mitigation depth: computed continuously from wick penetration
  (`compute_mitigation`), monotonically non-decreasing (deepest
  penetration only ever extends toward the far edge).
- `mitigation_pct >= 1.0` (reached by a WICK alone, close irrelevant) ==
  `mitigation_status == "fully_mitigated"`.
- Full mitigation moves the block from `_active` to `_mitigated`
  (`OrderBlockTracker._update_active`) - a one-way, monotonic
  transition, exactly like Policy B's invalidation latch below.
- `BreakerBlockTracker` consumes the `mitigated` list directly - no
  separate close confirmation is required for Breaker eligibility under
  Policy A.

Policy B (research candidate, implemented in this module)
------------------------------------------------------------------------
1. Touch: UNCHANGED - still wick-based, via the same `is_touching_zone`.
2. Mitigation percentage: UNCHANGED - still wick-based, via the same
   `compute_mitigation` - it continues to carry useful, informational
   depth data under B, it just no longer drives the active-> retired
   transition by itself.
3. `mitigation_pct >= 1.0` alone does NOT confirm invalidation under B.
4. Invalidation requires a CLOSE beyond the Order Block's far boundary:
   bullish block -> `close < zone_low`; bearish block -> `close >
   zone_high`. Once True, `invalidated` latches permanently (mirrors
   Policy A's own one-way "fully_mitigated" transition - not a new kind
   of state machine, the same shape applied to a different trigger).
5. Breaker eligibility (`breaker_eligible`) becomes True at the exact
   candle `invalidated` becomes True - not at 100% wick mitigation.
6. A wick that fully traverses the zone and closes back inside is
   recorded as `mitigation_status == "fully_mitigated"` (same as Policy
   A - this field is shared, informational, and unchanged) WITHOUT
   `invalidated` becoming True - this is the entire behavioral
   difference from Policy A for this specific, pre-declared scenario.

Invalidation boundary - decision, stated before implementation
------------------------------------------------------------------------
Three candidate boundaries were considered:
(a) the full Order Block boundary (`zone_high`/`zone_low` - the same
    wick-range boundary already used for touch/mitigation);
(b) the tighter body/mitigation-zone boundary
    (`mitigation_zone_high`/`mitigation_zone_low`);
(c) both, as separate fields.

**(a) is the PRE-REGISTERED PRIMARY hypothesis, and the only one
implemented here.** The instruction describes invalidation as requiring
a close beyond "the Order Block's far boundary" - in this codebase's own
language, that is `zone_high`/`zone_low` (the primary zone), not the
narrower `mitigation_zone_*` fields, which are explicitly documented
elsewhere (order_block.py's own module docstring) as a separate, tighter
"tighter, higher-confidence re-entry sub-zone" concept with an
independent purpose. Requiring a close beyond the FULL range is also the
economically stronger, more conservative invalidation criterion - a
close beyond only the tighter body would flag invalidation on cases
where price is still technically within the wick range, which reads as
premature in the same direction Policy B is designed to correct.

(b) (tighter body boundary) and (c) (both, separately) are recorded as
EXPLORATORY alternatives - not implemented, not measured, left for
future research if (a)'s results motivate a closer look at a stricter
or looser variant. This is a deliberate scope boundary, not an
oversight: implementing multiple invalidation boundaries in the same
sprint before establishing whether closing beyond even the widest
boundary is a repeated, material phenomenon would be premature.

No multi-close confirmation and no candle-count threshold are
introduced - invalidation is a single-candle, close-based test, exactly
mirroring `detect_bos`'s own existing single-candle, close-based
convention elsewhere in this codebase (Module Logic Correction 1's own
"Crossing semantics" section applied the identical reasoning).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from strategy.features.zone_lifecycle import (
    compute_mitigation,
    is_touching_zone,
    mitigation_status_from_pct,
)
from strategy.features.order_block import Direction, MitigationStatus


@dataclass
class PolicyBOrderBlockState:
    """
    Shadows a single, already-created OrderBlock (from the real,
    unmodified OrderBlockTracker) with Policy B's separated lifecycle.
    Constructed with the SAME zone bounds and identity as the real
    Order Block it shadows - never creates, resizes, or reinterprets a
    zone itself. Call apply_candle() once per new candle, in the same
    order and on the same candles the real tracker itself receives.
    """

    direction: Direction
    zone_high: float
    zone_low: float
    created_at: datetime
    origin_timestamp: datetime

    touch_count: int = 0
    mitigation_pct: float = 0.0
    mitigation_status: MitigationStatus = "unmitigated"

    invalidated: bool = False
    invalidated_at: datetime | None = None
    breaker_eligible: bool = False

    # Diagnostic-only: records the specific pre-declared scenario
    # ("wick fully traverses, closes back inside") the moment it first
    # occurs, independent of what happens afterward.
    wick_full_traversal_reclaimed: bool = False
    wick_full_traversal_reclaimed_at: datetime | None = None

    _deepest_penetration: float = field(init=False, repr=False)
    _currently_touching: bool = field(init=False, repr=False, default=False)

    def __post_init__(self) -> None:
        self._deepest_penetration = (
            self.zone_high if self.direction == "bullish" else self.zone_low
        )

    def apply_candle(self, candle: dict[str, Any], timestamp_key: str = "timestamp") -> None:
        # 1. Touch - identical rule to Policy A, unchanged.
        overlapping = is_touching_zone(candle, self.zone_high, self.zone_low)
        if overlapping and not self._currently_touching:
            self.touch_count += 1
        self._currently_touching = overlapping

        # 2. Mitigation depth - identical rule to Policy A, unchanged;
        # remains informational only under Policy B (does not drive
        # invalidation or breaker eligibility by itself).
        was_fully_mitigated = self.mitigation_status == "fully_mitigated"
        self._deepest_penetration, self.mitigation_pct = compute_mitigation(
            self.direction, self.zone_high, self.zone_low,
            self._deepest_penetration, candle,
        )
        self.mitigation_status = mitigation_status_from_pct(self.mitigation_pct)

        # Diagnostic: the exact bar wick-mitigation first reaches 100%
        # while NOT yet invalidated and the close is back inside the
        # zone - the specific scenario Policy B is designed to treat
        # differently from Policy A.
        newly_fully_mitigated = self.mitigation_status == "fully_mitigated" and not was_fully_mitigated
        close_back_inside = self.zone_low <= candle["close"] <= self.zone_high
        if newly_fully_mitigated and close_back_inside and not self.invalidated:
            self.wick_full_traversal_reclaimed = True
            self.wick_full_traversal_reclaimed_at = candle[timestamp_key]

        # 3. Invalidation - NEW, close-confirmed, latched permanently
        # once True (mirrors Policy A's own one-way mitigation_status
        # transition, applied to a different, stricter trigger).
        if not self.invalidated:
            if self.direction == "bullish" and candle["close"] < self.zone_low:
                self.invalidated = True
            elif self.direction == "bearish" and candle["close"] > self.zone_high:
                self.invalidated = True

            if self.invalidated:
                self.invalidated_at = candle[timestamp_key]
                self.breaker_eligible = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "zone_high": self.zone_high,
            "zone_low": self.zone_low,
            "created_at": self.created_at,
            "origin_timestamp": self.origin_timestamp,
            "touch_count": self.touch_count,
            "mitigation_pct": self.mitigation_pct,
            "mitigation_status": self.mitigation_status,
            "invalidated": self.invalidated,
            "invalidated_at": self.invalidated_at,
            "breaker_eligible": self.breaker_eligible,
            "wick_full_traversal_reclaimed": self.wick_full_traversal_reclaimed,
            "wick_full_traversal_reclaimed_at": self.wick_full_traversal_reclaimed_at,
        }
