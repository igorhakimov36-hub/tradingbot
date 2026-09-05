"""
Proves the opportunity-population capture's own observation technique
(peeking setup._pending before calling evaluate(), used to derive
S009's causal base-opportunity direction/risk - see
strategy/research/multi_module_opportunity_population.py) does not
alter the setup's own decisions. A read-only peek of an attribute the
setup already maintains cannot change behavior, but this is proven
directly rather than assumed: the same snapshot sequence run with vs.
without the peek must produce byte-identical fired/direction results.
"""

from datetime import datetime, timezone

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot
from strategy.research.setups.s009_failed_auction_reversal import S009FailedAuctionReversalSetup

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _snapshot(current_price, delta_strength=None, va_high=110.0, va_low=90.0):
    profile = {"value_area_high": va_high, "value_area_low": va_low} if va_high is not None else None
    return MarketIntelligenceSnapshot(
        symbol="SOLUSDT", timeframe="15m", timestamp=START, current_price=current_price,
        structure={}, zones=[], levels=[],
        order_flow={"delta": {"delta_strength": delta_strength} if delta_strength is not None else {}, "cvd": {}},
        sessions={"active_now": [], "previous_period_high_low": {}},
        intermarket={}, volume_profile={"current_forming_profile": profile}, data_quality={},
    )


SEQUENCE = [
    _snapshot(current_price=100.0, delta_strength=1.0),
    _snapshot(current_price=112.0, delta_strength=2.0),   # excursion (SHORT pending)
    _snapshot(current_price=108.0, delta_strength=5.0),   # trigger: progresses + stronger delta -> fires
    _snapshot(current_price=88.0, delta_strength=1.0),    # new excursion (LONG pending)
    _snapshot(current_price=95.0, delta_strength=6.0),    # progresses further, weaker check -> fires
    _snapshot(current_price=100.0, delta_strength=1.0),   # no excursion, no pending
]


def test_observer_peek_does_not_alter_fired_or_direction_sequence():
    plain_setup = S009FailedAuctionReversalSetup()
    plain_results = [plain_setup.evaluate(s) for s in SEQUENCE]

    observed_setup = S009FailedAuctionReversalSetup()
    observed_results = []
    peeked_pending_states = []
    for s in SEQUENCE:
        peeked_pending_states.append(observed_setup._pending)  # the observer's own read-only peek
        observed_results.append(observed_setup.evaluate(s))

    assert [r.fired for r in plain_results] == [r.fired for r in observed_results]
    assert [r.direction for r in plain_results] == [r.direction for r in observed_results]
    assert [r.reasoning for r in plain_results] == [r.reasoning for r in observed_results]

    # sanity: the peek actually observed real state transitions (not a no-op check)
    assert any(p is not None for p in peeked_pending_states)


def test_observer_peek_reads_the_same_object_evaluate_will_use():
    """The peeked pending state must be the EXACT state evaluate() consumes
    on this call - not a copy, not stale, not from a later bar."""
    setup = S009FailedAuctionReversalSetup()
    setup.evaluate(_snapshot(current_price=112.0, delta_strength=2.0))  # bar N: excursion captured

    pending_before = setup._pending
    assert pending_before is not None
    assert pending_before["direction"] == "SHORT"
    assert pending_before["excursion_bar_close"] == 112.0

    result = setup.evaluate(_snapshot(current_price=108.0, delta_strength=5.0))
    # the trigger's own evidence must match exactly what was peeked
    assert result.required_conditions[0].evidence["excursion_bar_close"] == pending_before["excursion_bar_close"]
