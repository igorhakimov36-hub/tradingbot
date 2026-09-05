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


def test_no_fire_with_no_pending_excursion():
    setup = S009FailedAuctionReversalSetup()
    result = setup.evaluate(_snapshot(current_price=100.0, delta_strength=1.0))
    assert result.fired is False


def test_short_excursion_then_stronger_rejection_delta_confirms_reversal():
    setup = S009FailedAuctionReversalSetup()
    # bar N: excursion beyond value_area_high, close at 112, WEAK delta (weak excursion)
    setup.evaluate(_snapshot(current_price=112.0, delta_strength=2.0))
    # bar N+1: closes further down (reversal direction for SHORT), STRONGER delta (real rejection)
    result = setup.evaluate(_snapshot(current_price=108.0, delta_strength=5.0))

    assert result.fired is True
    assert result.direction == "SHORT"


def test_long_excursion_then_stronger_rejection_delta_confirms_reversal():
    setup = S009FailedAuctionReversalSetup()
    # bar N: excursion beyond value_area_low, close at 88, WEAK delta (weak excursion)
    setup.evaluate(_snapshot(current_price=88.0, delta_strength=2.0))
    # bar N+1: closes further up (reversal direction for LONG), STRONGER delta (real rejection)
    result = setup.evaluate(_snapshot(current_price=92.0, delta_strength=5.0))

    assert result.fired is True
    assert result.direction == "LONG"


def test_does_not_fire_when_rejection_delta_is_not_stronger():
    setup = S009FailedAuctionReversalSetup()
    setup.evaluate(_snapshot(current_price=112.0, delta_strength=5.0))
    result = setup.evaluate(_snapshot(current_price=108.0, delta_strength=2.0))  # weaker, not stronger
    assert result.fired is False


def test_does_not_fire_when_price_does_not_progress_further():
    setup = S009FailedAuctionReversalSetup()
    setup.evaluate(_snapshot(current_price=112.0, delta_strength=5.0))
    result = setup.evaluate(_snapshot(current_price=115.0, delta_strength=1.0))  # further AWAY, not reversal
    assert result.fired is False


def test_pending_excursion_expires_after_one_bar_no_multi_bar_carry():
    setup = S009FailedAuctionReversalSetup()
    setup.evaluate(_snapshot(current_price=112.0, delta_strength=2.0))  # bar N: excursion (weak delta)
    # bar N+1: price back inside the value area (neither a trigger nor a new excursion) - the window expires
    setup.evaluate(_snapshot(current_price=100.0, delta_strength=1.0))
    # bar N+2: even with a delta that would have satisfied the ORIGINAL bar N comparison, no pending candidate remains
    result = setup.evaluate(_snapshot(current_price=95.0, delta_strength=10.0))
    assert result.fired is False


def test_new_excursion_overwrites_prior_unresolved_one():
    setup = S009FailedAuctionReversalSetup()
    setup.evaluate(_snapshot(current_price=112.0, delta_strength=5.0))  # bar N: SHORT excursion pending
    # bar N+1 is itself a NEW excursion (beyond value_area_low) rather than a trigger bar
    setup.evaluate(_snapshot(current_price=85.0, delta_strength=1.0))  # weak delta on the new excursion
    # bar N+2 should be evaluated against the NEW (LONG) pending excursion, not the stale SHORT one
    result = setup.evaluate(_snapshot(current_price=89.0, delta_strength=3.0))  # stronger rejection delta
    assert result.fired is True
    assert result.direction == "LONG"


# =========================================================
# State-isolation: fresh instance per run, no cross-instance leakage
# =========================================================


def test_fresh_instance_has_no_memory_of_a_previous_instance():
    setup_a = S009FailedAuctionReversalSetup()
    setup_a.evaluate(_snapshot(current_price=112.0, delta_strength=5.0))  # bar N pending on setup_a only

    setup_b = S009FailedAuctionReversalSetup()  # a fresh instance, as a new backtest run would construct
    result = setup_b.evaluate(_snapshot(current_price=108.0, delta_strength=2.0))

    # setup_b must NOT fire from setup_a's own pending excursion state.
    assert result.fired is False
    assert setup_b._pending is None or setup_b._pending is not setup_a._pending


# =========================================================
# Predeclared ablation: require_confirmation=False (frozen protocol
# Section 5's "trigger alone" comparison)
# =========================================================


def test_default_constructor_requires_confirmation_matching_frozen_behavior():
    setup = S009FailedAuctionReversalSetup()
    assert setup._require_confirmation is True


def test_ablation_fires_on_progress_alone_without_stronger_rejection_delta():
    setup = S009FailedAuctionReversalSetup(require_confirmation=False)
    setup.evaluate(_snapshot(current_price=112.0, delta_strength=5.0))  # bar N: excursion, delta=5.0
    # bar N+1: progresses further (SHORT), but delta is WEAKER not stronger - would fail under default gating
    result = setup.evaluate(_snapshot(current_price=108.0, delta_strength=1.0))

    assert result.fired is True
    assert result.direction == "SHORT"
    # the confirmation condition is still computed and reported, just non-gating
    assert result.additional_evidence[0].name == "weaker_participation_confirms_reversal"
    assert result.additional_evidence[0].satisfied is False


def test_ablation_still_requires_progress_condition():
    setup = S009FailedAuctionReversalSetup(require_confirmation=False)
    setup.evaluate(_snapshot(current_price=112.0, delta_strength=5.0))  # bar N: excursion
    # bar N+1: does NOT progress further (moves away from reversal direction)
    result = setup.evaluate(_snapshot(current_price=115.0, delta_strength=1.0))
    assert result.fired is False


def test_ablation_and_default_agree_when_confirmation_is_satisfied():
    setup_default = S009FailedAuctionReversalSetup()
    setup_ablation = S009FailedAuctionReversalSetup(require_confirmation=False)
    for setup in (setup_default, setup_ablation):
        setup.evaluate(_snapshot(current_price=112.0, delta_strength=2.0))
    r_default = setup_default.evaluate(_snapshot(current_price=108.0, delta_strength=5.0))
    r_ablation = setup_ablation.evaluate(_snapshot(current_price=108.0, delta_strength=5.0))
    assert r_default.fired == r_ablation.fired == True
    assert r_default.direction == r_ablation.direction == "SHORT"
