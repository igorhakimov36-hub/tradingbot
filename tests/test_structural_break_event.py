from datetime import datetime, timedelta, timezone

from strategy.features.market_structure_tracker import MarketStructureTracker
from strategy.market_structure import detect_bos, detect_choch, detect_market_structure, get_last_swing_levels

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(minute_offset, open_, high, low, close, volume=10.0):
    return {
        "timestamp": START + timedelta(minutes=minute_offset),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _bullish_setup():
    """Identical to test_market_structure_tracker.py's own fixture:
    confirms a BULLISH_BOS at the last candle (close 111 > prior swing
    high 110, pivot candle = index 3, timestamp START+3min)."""
    return [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 102, 88, 101),
        _candle(2, 101, 103, 95, 102),
        _candle(3, 102, 110, 100, 103),
        _candle(4, 104, 105, 101, 101, volume=50.0),
        _candle(5, 101, 104, 100, 103),
        _candle(6, 103, 108, 102, 107),
        _candle(7, 107, 112, 106, 111),  # BOS confirmation (111 > 110)
    ]


def _bullish_setup_with_second_level():
    """_bullish_setup() extended so a second, higher, distinct swing
    high (118, pivot candle index 8) is confirmed AND broken on the
    same later candle (index 10, close 119) - without bos ever
    returning to NO_BOS in between."""
    return _bullish_setup() + [
        _candle(8, 113, 118, 110, 113),
        _candle(9, 113, 114, 111, 113),
        _candle(10, 113, 120, 112, 119),  # 118 confirmed AND broken here
    ]


def _bearish_setup():
    """Mirror image of _bullish_setup(): confirms a BEARISH_BOS at the
    last candle (close 89 < prior swing low 90, pivot candle index 3,
    timestamp START+3min)."""
    return [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 112, 98, 99),
        _candle(2, 99, 105, 97, 98),
        _candle(3, 98, 100, 90, 97),
        _candle(4, 96, 99, 95, 99, volume=50.0),
        _candle(5, 99, 100, 96, 97),
        _candle(6, 97, 98, 92, 93),
        _candle(7, 93, 94, 88, 89),  # BOS confirmation (89 < 90)
    ]


def _all_events(tracker, candles):
    """Feed candles one at a time and collect every non-None
    structural_break_event seen, in order."""
    events = []
    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])
        event = tracker.snapshot()["structural_break_event"]
        if event is not None:
            events.append(event)
    return events


# =========================================================
# Failing characterization test (the confirmed correction target):
# a new, distinct same-direction level must fire its own event even
# though the persistent bos string never returns to NO_BOS.
# =========================================================


def test_new_distinct_level_break_fires_new_event_without_intervening_no_bos():
    candles = _bullish_setup_with_second_level()
    tracker = MarketStructureTracker()

    events = []
    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])
        snap = tracker.snapshot()
        if n >= 8:
            assert snap["bos"] == "BULLISH_BOS", f"n={n} unexpected bos={snap['bos']}"
        if snap["structural_break_event"] is not None:
            events.append(snap["structural_break_event"])

    assert len(events) == 2
    assert events[0].direction == "bullish"
    assert events[0].level == 110.0
    assert events[1].direction == "bullish"
    assert events[1].level == 118.0
    assert events[0].event_id != events[1].event_id
    assert events[0].pivot_timestamp != events[1].pivot_timestamp


# =========================================================
# Required test 1: repeated closes beyond the same level do not re-fire
# =========================================================


def test_repeated_closes_beyond_same_level_do_not_refire():
    candles = _bullish_setup() + [
        _candle(8, 111, 115, 110, 113),
        _candle(9, 113, 116, 111, 114),
        _candle(10, 114, 117, 112, 115),
    ]
    tracker = MarketStructureTracker()
    events = _all_events(tracker, candles)

    assert len(events) == 1
    assert events[0].level == 110.0


# =========================================================
# Required test 2: two distinct same-direction levels -> two events
# =========================================================


def test_two_distinct_same_direction_levels_produce_two_events():
    candles = _bullish_setup_with_second_level()
    tracker = MarketStructureTracker()
    events = _all_events(tracker, candles)

    assert [e.level for e in events] == [110.0, 118.0]


# =========================================================
# Required test 3: bullish and bearish symmetry
# =========================================================


def test_bearish_break_fires_event_symmetric_to_bullish():
    candles = _bearish_setup()
    tracker = MarketStructureTracker()
    events = _all_events(tracker, candles)

    assert len(events) == 1
    assert events[0].direction == "bearish"
    assert events[0].level == 90.0
    assert events[0].confirming_close == 89


def test_bullish_break_fires_event():
    candles = _bullish_setup()
    tracker = MarketStructureTracker()
    events = _all_events(tracker, candles)

    assert len(events) == 1
    assert events[0].direction == "bullish"
    assert events[0].level == 110.0
    assert events[0].confirming_close == 111


# =========================================================
# Required test 4: exact close at the level -> no event
# =========================================================


def test_exact_close_at_level_does_not_fire():
    candles = _bullish_setup()[:-1] + [
        _candle(7, 107, 112, 106, 110.0),  # close exactly equals the level, not beyond it
    ]
    tracker = MarketStructureTracker()
    events = _all_events(tracker, candles)

    assert events == []
    assert tracker.snapshot()["bos"] == "NO_BOS"


# =========================================================
# Required test 5: wick beyond, close inside -> no close-confirmed break
# =========================================================


def test_wick_beyond_level_with_close_inside_does_not_fire():
    candles = _bullish_setup()[:-1] + [
        _candle(7, 107, 130, 106, 109.0),  # high=130 wicks well beyond 110, close stays under
    ]
    tracker = MarketStructureTracker()
    events = _all_events(tracker, candles)

    assert events == []
    assert tracker.snapshot()["bos"] == "NO_BOS"


# =========================================================
# Required tests 6/7: pivot confirmation timing, no backdating
# =========================================================


def test_event_confirmed_at_is_breaking_candle_not_pivot_candle():
    candles = _bullish_setup()
    tracker = MarketStructureTracker()
    tracker.sync(candles)

    event = tracker.snapshot()["structural_break_event"]
    assert event is not None
    assert event.pivot_timestamp == START + timedelta(minutes=3)  # the pivot candle (index 3)
    assert event.confirmed_at == START + timedelta(minutes=7)  # the breaking candle (index 7)
    assert event.confirmed_at != event.pivot_timestamp
    assert event.confirmed_at > event.pivot_timestamp


def test_pivot_confirmed_while_price_already_beyond_it_fires_immediately_not_backdated():
    # Candle index 10 is the FIRST bar where level 118 (pivot index 8)
    # becomes visible as "last swing high" AND close is already beyond
    # it on that very same bar - the event must fire on candle 10, not
    # retroactively on an earlier candle.
    candles = _bullish_setup_with_second_level()
    tracker = MarketStructureTracker()

    fired_at = None
    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])
        event = tracker.snapshot()["structural_break_event"]
        if event is not None and event.level == 118.0:
            fired_at = event.confirmed_at

    assert fired_at == START + timedelta(minutes=10)


# =========================================================
# Required test 8: reset / new-window behavior
# =========================================================


def test_independent_tracker_instances_do_not_share_consumption_state():
    candles = _bullish_setup()

    tracker_a = MarketStructureTracker()
    tracker_a.sync(candles)
    events_a = [tracker_a.snapshot()["structural_break_event"]]

    tracker_b = MarketStructureTracker()
    tracker_b.sync(candles)
    events_b = [tracker_b.snapshot()["structural_break_event"]]

    assert events_a[0] is not None
    assert events_b[0] is not None
    assert events_a[0] == events_b[0]  # same content, deterministic
    assert tracker_a._consumed_break_pivots == tracker_b._consumed_break_pivots


# =========================================================
# Required test 9: repeated snapshot() calls do not re-consume/re-create
# =========================================================


def test_repeated_snapshot_calls_are_idempotent():
    candles = _bullish_setup()
    tracker = MarketStructureTracker()
    tracker.sync(candles)

    first = tracker.snapshot()["structural_break_event"]
    second = tracker.snapshot()["structural_break_event"]
    third = tracker.snapshot()["structural_break_event"]

    assert first == second == third
    assert first.event_id == second.event_id == third.event_id

    # Re-calling sync() with the SAME (non-extended) candle list must not
    # re-ingest and must not change the latest event.
    tracker.sync(candles)
    assert tracker.snapshot()["structural_break_event"] == first


# =========================================================
# Required test 10: deterministic event IDs
# =========================================================


def test_event_ids_are_deterministic_across_independent_runs():
    candles = _bullish_setup_with_second_level()

    tracker_1 = MarketStructureTracker()
    events_1 = _all_events(tracker_1, candles)

    tracker_2 = MarketStructureTracker()
    events_2 = _all_events(tracker_2, candles)

    assert [e.event_id for e in events_1] == [e.event_id for e in events_2]


def test_event_ids_differ_by_direction_even_at_the_same_timestamp():
    tracker = MarketStructureTracker()
    assert tracker._maybe_create_break_event(
        direction="bullish",
        pivot_candle={"timestamp": START},
        pivot_price=100.0,
        candle={"timestamp": START, "close": 101.0},
    ).event_id != MarketStructureTracker()._maybe_create_break_event(
        direction="bearish",
        pivot_candle={"timestamp": START},
        pivot_price=100.0,
        candle={"timestamp": START, "close": 99.0},
    ).event_id


# =========================================================
# Required test 11: bounded event-consumption memory
# =========================================================


def test_consumed_pivot_memory_is_bounded_by_structure_lookback():
    lookback = 10
    tracker = MarketStructureTracker(structure_lookback=lookback)

    # A long, choppy zig-zag sequence that repeatedly confirms and
    # breaks many distinct swing highs/lows over a much longer history
    # than the lookback window.
    candles = []
    price = 100.0
    for i in range(400):
        if i % 2 == 0:
            price += 5
            candles.append(_candle(i, price, price + 3, price - 3, price + 1))
        else:
            price -= 2
            candles.append(_candle(i, price, price + 3, price - 3, price - 1))

    max_seen = 0
    for n in range(1, len(candles) + 1, 5):
        tracker.sync(candles[:n])
        max_seen = max(max_seen, len(tracker._consumed_break_pivots))

    assert max_seen <= lookback


# =========================================================
# Required test 12: no duplicate independent event when bos and choch
# are simultaneously true for the same underlying level break
# =========================================================


def test_simultaneous_bos_and_choch_produce_exactly_one_event():
    # Construct a bearish-regime window where the close then breaks the
    # existing swing high - this makes detect_bos return BULLISH_BOS
    # AND detect_choch return BULLISH_CHOCH on the same candle, from the
    # exact same previous_swing_high comparison.
    candles = [
        _candle(0, 97, 100, 95, 98),
        _candle(1, 100, 105, 98, 102),
        _candle(2, 105, 118, 100, 110),  # swing high pivot: high=118
        _candle(3, 108, 110, 90, 95),
        _candle(4, 90, 108, 80, 85, volume=50.0),  # swing low pivot: low=80
        _candle(5, 87, 106, 85, 90),
        _candle(6, 85, 104, 82, 88),  # regime BEARISH by here (lower high, lower low vs idx5)
        _candle(7, 88, 130, 80, 119),  # close breaks above 118 while regime is BEARISH
    ]

    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    prev_high, prev_low = get_last_swing_levels(highs[:-1], lows[:-1])
    regime = detect_market_structure(highs[:-1], lows[:-1])
    bos = detect_bos(candles[-1]["close"], prev_high, prev_low)
    choch = detect_choch(regime, candles[-1]["close"], prev_high, prev_low)

    # Precondition: this hand-built sequence really does produce the
    # simultaneous-reading scenario this test is meant to exercise.
    assert bos == "BULLISH_BOS"
    assert choch == "BULLISH_CHOCH"

    tracker = MarketStructureTracker()
    tracker.sync(candles)
    snap = tracker.snapshot()

    assert snap["bos"] == "BULLISH_BOS"
    assert snap["choch"] == "BULLISH_CHOCH"
    assert snap["structural_break_event"] is not None
    assert snap["structural_break_event"].direction == "bullish"
    assert snap["structural_break_event"].level == prev_high


# =========================================================
# Required test 13: existing persistent fields remain byte-for-byte
# identical to the pre-existing reference computation
# =========================================================


def test_existing_persistent_fields_are_unaffected_and_field_is_purely_additive():
    candles = _bullish_setup_with_second_level()
    tracker = MarketStructureTracker()

    for n in range(1, len(candles) + 1):
        tracker.sync(candles[:n])
        snap = tracker.snapshot()

        highs = [c["high"] for c in candles[:n]]
        lows = [c["low"] for c in candles[:n]]
        prev_high, prev_low = get_last_swing_levels(highs[:-1], lows[:-1])
        reference = {
            "market_structure": detect_market_structure(highs[:-1], lows[:-1]),
            "last_swing_high": prev_high,
            "last_swing_low": prev_low,
            "bos": detect_bos(candles[:n][-1]["close"], prev_high, prev_low),
            "choch": detect_choch(
                detect_market_structure(highs[:-1], lows[:-1]),
                candles[:n][-1]["close"],
                prev_high,
                prev_low,
            ),
        }

        for key, value in reference.items():
            assert snap[key] == value, f"n={n} field={key}"

    assert "structural_break_event" in snap
    assert "structural_break_event" not in reference
