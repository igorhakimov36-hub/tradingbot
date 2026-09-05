from datetime import datetime, timezone

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot
from strategy.research.setups.s011_value_area_fade import BUCKET_MULTIPLE, S011ValueAreaFadeSetup

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
SETUP = S011ValueAreaFadeSetup()

VA_HIGH = 110.0
VA_LOW = 90.0
BUCKET = 2.0


def _snapshot(current_price, regime="RANGE", cvd=None, profile_present=True):
    profile = {"value_area_high": VA_HIGH, "value_area_low": VA_LOW, "bucket_size": BUCKET, "poc_price": 100.0} if profile_present else None
    return MarketIntelligenceSnapshot(
        symbol="SOLUSDT", timeframe="15m", timestamp=START, current_price=current_price,
        structure={"market_structure": regime}, zones=[], levels=[],
        order_flow={"delta": {}, "cvd": cvd or {}},
        sessions={"active_now": [], "previous_period_high_low": {}},
        intermarket={}, volume_profile={"current_forming_profile": profile}, data_quality={},
    )


def test_does_not_fire_outside_range_regime():
    result = SETUP.evaluate(_snapshot(current_price=VA_HIGH + BUCKET * BUCKET_MULTIPLE + 1, regime="BULLISH", cvd={"a": {"cvd_exhaustion_flag": "bearish_exhaustion"}}))
    assert result.fired is False


def test_does_not_fire_without_a_forming_profile():
    result = SETUP.evaluate(_snapshot(current_price=VA_HIGH + 10, profile_present=False))
    assert result.fired is False


def test_does_not_fire_within_bucket_threshold_of_value_area():
    just_inside = VA_HIGH + (BUCKET * BUCKET_MULTIPLE) - 0.01
    result = SETUP.evaluate(_snapshot(current_price=just_inside, cvd={"a": {"cvd_exhaustion_flag": "bearish_exhaustion"}}))
    assert result.fired is False


def test_fires_short_exactly_at_the_bucket_threshold_with_exhaustion():
    at_threshold = VA_HIGH + (BUCKET * BUCKET_MULTIPLE) + 0.01
    result = SETUP.evaluate(_snapshot(current_price=at_threshold, cvd={"a": {"cvd_exhaustion_flag": "bearish_exhaustion"}}))
    assert result.fired is True
    assert result.direction == "SHORT"


def test_fires_long_below_value_area_with_exhaustion():
    below = VA_LOW - (BUCKET * BUCKET_MULTIPLE) - 0.01
    result = SETUP.evaluate(_snapshot(current_price=below, cvd={"a": {"cvd_exhaustion_flag": "bullish_exhaustion"}}))
    assert result.fired is True
    assert result.direction == "LONG"


def test_cvd_exhaustion_is_required_not_optional():
    at_threshold = VA_HIGH + (BUCKET * BUCKET_MULTIPLE) + 0.01
    result = SETUP.evaluate(_snapshot(current_price=at_threshold, cvd={}))
    assert result.fired is False
    failed = [c.name for c in result.required_conditions if not c.satisfied]
    assert "cvd_exhaustion_confirms_reversion" in failed


def test_wrong_direction_exhaustion_flag_does_not_satisfy():
    at_threshold = VA_HIGH + (BUCKET * BUCKET_MULTIPLE) + 0.01  # SHORT candidate
    result = SETUP.evaluate(_snapshot(current_price=at_threshold, cvd={"a": {"cvd_exhaustion_flag": "bullish_exhaustion"}}))
    assert result.fired is False


def test_deterministic_across_repeated_calls():
    snapshot = _snapshot(current_price=VA_HIGH + 10, cvd={"a": {"cvd_exhaustion_flag": "bearish_exhaustion"}})
    r1 = SETUP.evaluate(snapshot)
    r2 = SETUP.evaluate(snapshot)
    assert r1.fired == r2.fired
    assert r1.direction == r2.direction


def test_no_state_carried_between_unrelated_snapshots():
    fresh_setup = S011ValueAreaFadeSetup()
    result_short = fresh_setup.evaluate(_snapshot(current_price=VA_HIGH + 10, cvd={"a": {"cvd_exhaustion_flag": "bearish_exhaustion"}}))
    result_long = fresh_setup.evaluate(_snapshot(current_price=VA_LOW - 10, cvd={"a": {"cvd_exhaustion_flag": "bullish_exhaustion"}}))
    assert result_short.direction == "SHORT"
    assert result_long.direction == "LONG"  # unaffected by the prior call


# =========================================================
# Predeclared ablation: require_cvd_confirmation=False (frozen
# protocol Section 5's "trigger+context, no confirmation" comparison)
# =========================================================


def test_default_constructor_requires_cvd_confirmation_matching_frozen_behavior():
    setup = S011ValueAreaFadeSetup()
    assert setup._require_cvd_confirmation is True


def test_ablation_fires_on_extension_alone_without_cvd_exhaustion():
    setup = S011ValueAreaFadeSetup(require_cvd_confirmation=False)
    at_threshold = VA_HIGH + (BUCKET * BUCKET_MULTIPLE) + 0.01
    result = setup.evaluate(_snapshot(current_price=at_threshold, cvd={}))  # no CVD anchor at all
    assert result.fired is True
    assert result.direction == "SHORT"
    assert result.additional_evidence[0].name == "cvd_exhaustion_confirms_reversion"
    assert result.additional_evidence[0].satisfied is False


def test_ablation_still_requires_extension_condition():
    setup = S011ValueAreaFadeSetup(require_cvd_confirmation=False)
    just_inside = VA_HIGH + (BUCKET * BUCKET_MULTIPLE) - 0.01
    result = setup.evaluate(_snapshot(current_price=just_inside, cvd={}))
    assert result.fired is False


def test_ablation_and_default_agree_when_cvd_confirms():
    setup_default = S011ValueAreaFadeSetup()
    setup_ablation = S011ValueAreaFadeSetup(require_cvd_confirmation=False)
    at_threshold = VA_HIGH + (BUCKET * BUCKET_MULTIPLE) + 0.01
    snap = _snapshot(current_price=at_threshold, cvd={"a": {"cvd_exhaustion_flag": "bearish_exhaustion"}})
    r_default = setup_default.evaluate(snap)
    r_ablation = setup_ablation.evaluate(snap)
    assert r_default.fired == r_ablation.fired == True
    assert r_default.direction == r_ablation.direction == "SHORT"
