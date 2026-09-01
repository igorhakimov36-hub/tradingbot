import pytest

from strategy.features.zone_lifecycle import (
    compute_impulse_strength,
    compute_mitigation,
    is_touching_zone,
    mitigation_status_from_pct,
    update_favorable_extreme,
)


def _candle(high, low):
    return {"high": high, "low": low}


# =========================================================
# compute_mitigation
# =========================================================


def test_bullish_mitigation_progresses_as_price_falls_into_zone():
    penetration, pct = compute_mitigation(
        "bullish", zone_high=110, zone_low=100, deepest_penetration=110,
        candle=_candle(high=112, low=105),
    )
    assert penetration == 105
    assert pct == pytest.approx(0.5)


def test_bullish_mitigation_reaches_full_at_zone_low():
    _, pct = compute_mitigation(
        "bullish", zone_high=110, zone_low=100, deepest_penetration=110,
        candle=_candle(high=112, low=95),
    )
    assert pct == 1.0


def test_bullish_mitigation_never_decreases_on_a_shallower_candle():
    penetration, pct = compute_mitigation(
        "bullish", zone_high=110, zone_low=100, deepest_penetration=103,
        candle=_candle(high=112, low=107),  # shallower than prior deepest (103)
    )
    assert penetration == 103  # unchanged - deepest so far still wins
    assert pct == pytest.approx((110 - 103) / 10)


def test_bearish_mitigation_progresses_as_price_rises_into_zone():
    penetration, pct = compute_mitigation(
        "bearish", zone_high=110, zone_low=100, deepest_penetration=100,
        candle=_candle(high=105, low=98),
    )
    assert penetration == 105
    assert pct == pytest.approx(0.5)


def test_mitigation_clamped_on_extreme_overshoot():
    _, pct = compute_mitigation(
        "bullish", zone_high=110, zone_low=100, deepest_penetration=110,
        candle=_candle(high=112, low=10),
    )
    assert pct == 1.0


def test_zero_span_zone_is_immediately_fully_mitigated():
    penetration, pct = compute_mitigation(
        "bullish", zone_high=100, zone_low=100, deepest_penetration=100,
        candle=_candle(high=105, low=95),
    )
    assert pct == 1.0


# =========================================================
# mitigation_status_from_pct
# =========================================================


def test_status_boundaries():
    assert mitigation_status_from_pct(0.0) == "unmitigated"
    assert mitigation_status_from_pct(0.01) == "partially_mitigated"
    assert mitigation_status_from_pct(0.99) == "partially_mitigated"
    assert mitigation_status_from_pct(1.0) == "fully_mitigated"


# =========================================================
# is_touching_zone
# =========================================================


def test_touching_when_ranges_overlap():
    assert is_touching_zone(_candle(high=105, low=95), zone_high=110, zone_low=100) is True


def test_not_touching_when_fully_above():
    assert is_touching_zone(_candle(high=130, low=120), zone_high=110, zone_low=100) is False


def test_not_touching_when_fully_below():
    assert is_touching_zone(_candle(high=90, low=80), zone_high=110, zone_low=100) is False


def test_touching_at_exact_boundary():
    assert is_touching_zone(_candle(high=100, low=90), zone_high=110, zone_low=100) is True


# =========================================================
# update_favorable_extreme
# =========================================================


def test_bullish_extreme_tracks_highest_high():
    extreme = update_favorable_extreme("bullish", current_extreme=100, candle=_candle(high=105, low=95))
    assert extreme == 105

    extreme = update_favorable_extreme("bullish", current_extreme=105, candle=_candle(high=102, low=95))
    assert extreme == 105  # does not shrink


def test_bearish_extreme_tracks_lowest_low():
    extreme = update_favorable_extreme("bearish", current_extreme=100, candle=_candle(high=105, low=95))
    assert extreme == 95

    extreme = update_favorable_extreme("bearish", current_extreme=95, candle=_candle(high=105, low=98))
    assert extreme == 95  # does not grow back


# =========================================================
# compute_impulse_strength
# =========================================================


def test_impulse_strength_none_without_atr():
    assert compute_impulse_strength("bullish", 110, 100, 120, None) is None
    assert compute_impulse_strength("bullish", 110, 100, 120, 0) is None


def test_bullish_impulse_strength_positive_after_favorable_move():
    strength = compute_impulse_strength("bullish", zone_high=110, zone_low=100, extreme_since_creation=130, atr_at_creation=10)
    assert strength == pytest.approx(2.0)


def test_bearish_impulse_strength_positive_after_favorable_move():
    strength = compute_impulse_strength("bearish", zone_high=110, zone_low=100, extreme_since_creation=80, atr_at_creation=10)
    assert strength == pytest.approx(2.0)


def test_impulse_strength_zero_at_creation():
    strength = compute_impulse_strength("bullish", zone_high=110, zone_low=100, extreme_since_creation=110, atr_at_creation=10)
    assert strength == 0.0
