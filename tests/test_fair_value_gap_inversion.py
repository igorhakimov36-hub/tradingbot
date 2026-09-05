"""
FVG inversion lifecycle tests - opt-in, disabled-by-default extension.
See strategy/features/fair_value_gap.py's own "Inversion lifecycle"
docstring section and docs/fvg_ifvg_module_logic_review.md for the
design this implements.

Covers, per the authorizing sprint's own explicit event-ordering list:
wick fill without inversion, later close-confirmed inversion, fill and
inversion confirmed on the same candle, boundary equality, repeated
closes beyond the boundary, post-inversion failure, bounded retention/
expiry, and the independently-optional retest signal.

Assertions look up the specific gap under test by its own zone
boundaries (`_find_gap`) rather than assuming a list has exactly one
entry - the sliding 3-candle detection window can legitimately form an
extra, unrelated gap from candles added later in a sequence (itself a
correct, already-tested behavior, not something these lifecycle tests
exist to constrain) and this file's own assertions should not be
fragile to that.
"""

from datetime import datetime, timedelta, timezone

from strategy.features.fair_value_gap import FairValueGapTracker

START = datetime(2024, 1, 1, tzinfo=timezone.utc)

ZONE_LOW = 101
ZONE_HIGH = 116


def _candle(minute_offset, open_, high, low, close, volume=100.0):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _bullish_gap_setup_candles():
    """A/B/C forming a bullish gap zone [101, 116]."""
    return [
        _candle(0, 100, 101, 99, 100),      # A - high=101
        _candle(1, 100, 115, 100, 114),     # B - impulsive
        _candle(2, 116, 120, 116, 118),     # C - low=116
    ]


def _find_gap(entries, zone_low=ZONE_LOW, zone_high=ZONE_HIGH):
    for entry in entries:
        if entry["zone_low"] == zone_low and entry["zone_high"] == zone_high:
            return entry
    raise AssertionError(f"no gap [{zone_low}, {zone_high}] found in {entries}")


# =========================================================
# Feature-off: exact pre-existing behavior, nothing new happens
# =========================================================


def test_disabled_tracker_snapshot_shape_unchanged_even_when_price_would_invert():
    """With track_inversions=False (default), even a candle sequence
    that WOULD invert the gap if the feature were on must produce the
    exact pre-existing 3-key snapshot shape - the feature must be
    truly dormant, not merely visually hidden."""
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 100, 100, 90, 95),   # fills AND would-invert
        _candle(4, 95, 96, 85, 90),     # would-fail-check territory too
    ]
    tracker = FairValueGapTracker()
    tracker.sync(candles)

    snapshot = tracker.snapshot()
    assert set(snapshot.keys()) == {"active", "filled", "expired_count"}

    gap = _find_gap(snapshot["filled"])
    # the filled dict itself still carries the new fields (harmless,
    # additive to_dict() output) but every one must be at its neutral
    # "never happened" default - never silently computed.
    assert gap["filled_at"] is None
    assert gap["is_inverted"] is False
    assert gap["is_failed"] is False


# =========================================================
# 1. Wick fill without inversion
# =========================================================


def test_wick_fill_without_inversion():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),  # wick to 100 (<=101) fills fully; close 110 stays above zone_low
    ]
    tracker = FairValueGapTracker(track_inversions=True)
    tracker.sync(candles)

    gap = _find_gap(tracker.snapshot()["filled"])
    assert gap["fill_status"] == "completely_filled"
    assert gap["filled_at"] == START + timedelta(minutes=3)
    assert gap["filled_bar_index"] == 3
    assert gap["is_inverted"] is False
    assert all(g["zone_low"] != ZONE_LOW for g in tracker.snapshot()["inverted"])


# =========================================================
# 2. Later close-confirmed inversion (separate bar from fill)
# =========================================================


def test_later_close_confirmed_inversion_on_a_separate_bar():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),  # bar 3: fills (wick), closes above zone_low - no inversion yet
        _candle(4, 108, 100, 94, 95),    # bar 4: closes at 95, strictly below zone_low=101 - inversion confirms HERE
    ]
    tracker = FairValueGapTracker(track_inversions=True)
    tracker.sync(candles)

    gap = _find_gap(tracker.snapshot()["filled"])
    assert gap["filled_bar_index"] == 3
    assert gap["is_inverted"] is True
    assert gap["inverted_at"] == START + timedelta(minutes=4)
    assert gap["inverted_bar_index"] == 4
    assert gap["filled_bar_index"] != gap["inverted_bar_index"]

    inverted_gap = _find_gap(tracker.snapshot()["inverted"])
    assert inverted_gap["inverted_bar_index"] == 4


# =========================================================
# 3. Fill AND inversion confirmed on the SAME candle
# =========================================================


def test_fill_and_inversion_confirmed_on_the_same_candle():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 90, 95),  # bar 3: wick to 90 fills fully; close 95 ALSO strictly below zone_low=101
    ]
    tracker = FairValueGapTracker(track_inversions=True)
    tracker.sync(candles)

    gap = _find_gap(tracker.snapshot()["filled"])
    assert gap["filled_bar_index"] == 3
    assert gap["is_inverted"] is True
    assert gap["inverted_bar_index"] == 3
    assert gap["filled_at"] == gap["inverted_at"] == START + timedelta(minutes=3)


# =========================================================
# 4. Boundary equality - close exactly AT the edge does not invert
# =========================================================


def test_close_exactly_at_boundary_does_not_confirm_inversion():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),  # fills
        _candle(4, 105, 106, 100, 101.0),  # closes EXACTLY at zone_low=101 - must NOT invert
    ]
    tracker = FairValueGapTracker(track_inversions=True)
    tracker.sync(candles)

    gap = _find_gap(tracker.snapshot()["filled"])
    assert gap["is_inverted"] is False

    # One tick below confirms it, proving the boundary check itself is live.
    tracker2 = FairValueGapTracker(track_inversions=True)
    tracker2.sync(candles[:-1] + [_candle(4, 105, 106, 100, 100.99)])
    gap2 = _find_gap(tracker2.snapshot()["filled"])
    assert gap2["is_inverted"] is True


# =========================================================
# 5. Repeated closes beyond the boundary - no duplicate event
# =========================================================


def test_repeated_closes_beyond_boundary_do_not_duplicate_the_inversion_event():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),  # fills
        _candle(4, 108, 100, 94, 95),    # inverts HERE (bar 4)
        _candle(5, 90, 91, 80, 85),      # closes below zone_low AGAIN - must not re-trigger
        _candle(6, 80, 81, 70, 75),      # again
    ]
    tracker = FairValueGapTracker(track_inversions=True)
    tracker.sync(candles)

    gap = _find_gap(tracker.snapshot()["filled"])
    assert gap["is_inverted"] is True
    assert gap["inverted_bar_index"] == 4  # unchanged by bars 5/6
    assert gap["inverted_at"] == START + timedelta(minutes=4)


# =========================================================
# 6. Post-inversion failure
# =========================================================


def test_post_inversion_failure_when_price_reclaims_the_original_zone():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),  # fills
        _candle(4, 108, 100, 94, 95),    # inverts (close=95 < zone_low=101)
        _candle(5, 96, 116.5, 96, 116.5),  # closes at 116.5, strictly above zone_high=116 - failure confirmed
    ]
    tracker = FairValueGapTracker(track_inversions=True)
    tracker.sync(candles)

    gap = _find_gap(tracker.snapshot()["filled"])
    assert gap["is_inverted"] is True
    assert gap["is_failed"] is True
    assert gap["failed_at"] == START + timedelta(minutes=5)
    assert gap["failed_bar_index"] == 5

    assert all(g["zone_low"] != ZONE_LOW for g in tracker.snapshot()["inverted"])  # moved out once failed
    _find_gap(tracker.snapshot()["failed"])  # present in the failed bucket


def test_failure_is_also_idempotent():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),
        _candle(4, 108, 100, 94, 95),
        _candle(5, 96, 116.5, 96, 116.5),  # fails here
        _candle(6, 116.5, 120, 116.5, 118),  # closes even higher - must not re-trigger
    ]
    tracker = FairValueGapTracker(track_inversions=True)
    tracker.sync(candles)

    gap = _find_gap(tracker.snapshot()["filled"])
    assert gap["failed_bar_index"] == 5


# =========================================================
# 7. Bounded retention / explicit expiry of inversion candidates
# =========================================================


def test_inversion_candidate_expires_after_the_watch_window():
    # Small window for a fast, deterministic test.
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),   # bar 3: fills, filled_bar_index=3
        _candle(4, 110, 111, 109, 110),   # bar 4: neutral, no inversion
        _candle(5, 110, 111, 109, 110),   # bar 5: neutral
        _candle(6, 110, 111, 109, 110),   # bar 6: neutral - still within window (6-3=3, not > 3)
        _candle(7, 110, 111, 109, 110),   # bar 7: 7-3=4 > 3 -> expires HERE, before any inversion check
        _candle(8, 108, 109, 94, 95),     # bar 8: would invert if still eligible - must NOT invert (expired)
    ]
    tracker = FairValueGapTracker(track_inversions=True, inversion_watch_bars=3)
    tracker.sync(candles)

    gap = _find_gap(tracker.snapshot()["filled"])
    assert gap["inversion_expired"] is True
    assert gap["is_inverted"] is False
    assert tracker.snapshot()["inversion_expired_count"] >= 1


def test_inversion_still_eligible_exactly_at_the_watch_window_boundary():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),   # fills, filled_bar_index=3
        _candle(4, 110, 111, 109, 110),
        _candle(5, 110, 111, 109, 110),
        _candle(6, 108, 100, 94, 95),     # bar 6: 6-3=3, not > 3 - still eligible, and closes below zone_low -> inverts
    ]
    tracker = FairValueGapTracker(track_inversions=True, inversion_watch_bars=3)
    tracker.sync(candles)

    gap = _find_gap(tracker.snapshot()["filled"])
    assert gap["inversion_expired"] is False
    assert gap["is_inverted"] is True


# =========================================================
# 8. Retest signal - independently optional, tested separately
# =========================================================
#
# Bar 4 (the inversion bar) deliberately keeps its own high at/below
# zone_low=101 throughout this section, so it never itself satisfies
# the retest geometry's own "prior bar reached the level" check -
# isolating the retest pattern to the specific bars intended to
# demonstrate it.


def test_retest_requires_track_retests_flag_even_with_inversions_on():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),
        _candle(4, 100, 100, 94, 95),      # inverts (high=100, stays below zone_low=101)
        _candle(5, 95, 101, 90, 96),       # prior bar's high reaches exactly 101 (zone_low)
        _candle(6, 96, 100, 90, 95),       # current bar's high (100) stays <= 101 -> retest pattern present
    ]
    tracker_off = FairValueGapTracker(track_inversions=True, track_retests=False)
    tracker_off.sync(candles)
    gap_off = _find_gap(tracker_off.snapshot()["filled"])
    assert gap_off["last_retest_bar_index"] is None
    assert gap_off["retest_confirmed_this_bar"] is False

    tracker_on = FairValueGapTracker(track_inversions=True, track_retests=True)
    tracker_on.sync(candles)
    gap_on = _find_gap(tracker_on.snapshot()["filled"])
    assert gap_on["last_retest_bar_index"] == 6


def test_retest_confirmed_this_bar_is_true_only_on_the_exact_confirming_bar():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),
        _candle(4, 100, 100, 94, 95),      # inverts
        _candle(5, 95, 101, 90, 96),       # prior-bar setup
        _candle(6, 96, 100, 90, 95),       # retest confirms HERE (bar 6)
    ]
    tracker = FairValueGapTracker(track_inversions=True, track_retests=True)
    tracker.sync(candles[:-1])
    gap_before = _find_gap(tracker.snapshot()["filled"])
    assert gap_before["retest_confirmed_this_bar"] is False

    tracker.sync(candles)
    gap_at = _find_gap(tracker.snapshot()["filled"])
    assert gap_at["retest_confirmed_this_bar"] is True

    tracker.sync(candles + [_candle(7, 95, 96, 90, 92)])
    gap_after = _find_gap(tracker.snapshot()["filled"])
    assert gap_after["retest_confirmed_this_bar"] is False   # one-shot, not sticky
    assert gap_after["last_retest_bar_index"] == 6            # but the record itself persists


def test_retest_cooldown_suppresses_an_immediate_repeat_signal():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),
        _candle(4, 100, 100, 94, 95),      # inverts
        _candle(5, 95, 101, 90, 96),       # setup
        _candle(6, 96, 100, 90, 95),       # retest #1 confirms (bar 6)
        _candle(7, 95, 101, 90, 96),       # setup again, immediately
        _candle(8, 96, 100, 90, 95),       # would be retest #2 at bar 8 - within cooldown (8-6=2 <= 5) - suppressed
    ]
    tracker = FairValueGapTracker(track_inversions=True, track_retests=True, retest_cooldown_bars=5)
    tracker.sync(candles)
    gap = _find_gap(tracker.snapshot()["filled"])
    assert gap["last_retest_bar_index"] == 6  # NOT updated to 8 - cooldown suppressed the repeat


def test_retest_fires_again_once_cooldown_elapses():
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),
        _candle(4, 100, 100, 94, 95),      # inverts
        _candle(5, 95, 101, 90, 96),
        _candle(6, 96, 100, 90, 95),       # retest #1 (bar 6)
    ]
    # pad past the cooldown window with neutral candles, none re-triggering
    for i in range(7, 13):
        candles.append(_candle(i, 95, 96, 90, 92))
    candles += [
        _candle(13, 95, 101, 90, 96),      # setup again, well past cooldown (13-6=7 > 5)
        _candle(14, 96, 100, 90, 95),      # retest #2
    ]
    tracker = FairValueGapTracker(track_inversions=True, track_retests=True, retest_cooldown_bars=5)
    tracker.sync(candles)
    gap = _find_gap(tracker.snapshot()["filled"])
    assert gap["last_retest_bar_index"] == 14


def test_retest_never_evaluated_before_inversion():
    """A retest check against a not-yet-inverted gap must never fire -
    the geometry alone (price revisiting zone_low) is not sufficient;
    inversion must be confirmed first."""
    candles = _bullish_gap_setup_candles() + [
        _candle(3, 105, 106, 100, 110),   # fills, NOT inverted
        _candle(4, 95, 101, 90, 105),     # prior bar's high reaches 101, closes back inside (still not inverted)
        _candle(5, 95, 100, 90, 102),     # current bar's high stays <= 101 - geometrically a "retest" shape, but gap never inverted
    ]
    tracker = FairValueGapTracker(track_inversions=True, track_retests=True)
    tracker.sync(candles)
    gap = _find_gap(tracker.snapshot()["filled"])
    assert gap["is_inverted"] is False
    assert gap["last_retest_bar_index"] is None
