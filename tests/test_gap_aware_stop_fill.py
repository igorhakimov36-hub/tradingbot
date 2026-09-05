"""
Tests for strategy/research/gap_aware_stop_fill.py.
"""

import pytest

from strategy.research.gap_aware_stop_fill import gap_aware_net_pnl, gap_aware_stop_fill


def _candle(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}


# =========================================================
# gap_aware_stop_fill
# =========================================================


def test_long_no_gap_fills_at_requested_stop():
    price, gapped = gap_aware_stop_fill("LONG", stop_price=99.0, candle=_candle(99.5, 99.6, 98.5, 99.0))
    assert price == 99.0
    assert gapped is False


def test_long_gap_through_open_fills_at_open_not_stop():
    # Market opened BELOW the stop - a live stop-market order would fill
    # at (or near) the open, never at the stale, already-breached level.
    price, gapped = gap_aware_stop_fill("LONG", stop_price=99.0, candle=_candle(97.0, 97.5, 96.5, 97.2))
    assert price == 97.0
    assert gapped is True


def test_short_no_gap_fills_at_requested_stop():
    price, gapped = gap_aware_stop_fill("SHORT", stop_price=101.0, candle=_candle(100.5, 101.2, 100.4, 100.8))
    assert price == 101.0
    assert gapped is False


def test_short_gap_through_open_fills_at_open_not_stop():
    price, gapped = gap_aware_stop_fill("SHORT", stop_price=101.0, candle=_candle(103.0, 103.5, 102.5, 103.2))
    assert price == 103.0
    assert gapped is True


def test_long_open_exactly_at_stop_is_a_gap_not_a_normal_fill():
    price, gapped = gap_aware_stop_fill("LONG", stop_price=99.0, candle=_candle(99.0, 99.2, 98.0, 98.5))
    assert gapped is True
    assert price == 99.0  # open == stop, still the worse-or-equal convention


# =========================================================
# gap_aware_net_pnl - reuses the same fee/slippage formulas as the simulator
# =========================================================


def test_gap_aware_net_pnl_no_gap_matches_normal_fill_math():
    result = gap_aware_net_pnl(
        side="LONG", quantity=10.0, entry_price=100.0, entry_fee=0.4,
        stop_price=99.0, candle=_candle(99.5, 99.6, 98.9, 99.2),
        fee_rate=0.0004, slippage_rate=0.0002,
    )
    assert result["was_gapped"] is False
    expected_exit = 99.0 * (1 - 0.0002)
    expected_gross = (expected_exit - 100.0) * 10.0
    expected_fee = expected_exit * 10.0 * 0.0004
    assert result["gross_pnl"] == pytest.approx(expected_gross)
    assert result["net_pnl"] == pytest.approx(expected_gross - 0.4 - expected_fee)


def test_gap_aware_net_pnl_with_gap_is_worse_than_naive_fill_for_long():
    naive = gap_aware_net_pnl(
        side="LONG", quantity=10.0, entry_price=100.0, entry_fee=0.4,
        stop_price=99.0, candle=_candle(99.5, 99.6, 98.9, 99.2),
        fee_rate=0.0004, slippage_rate=0.0002,
    )
    gapped = gap_aware_net_pnl(
        side="LONG", quantity=10.0, entry_price=100.0, entry_fee=0.4,
        stop_price=99.0, candle=_candle(96.0, 96.5, 95.5, 96.2),
        fee_rate=0.0004, slippage_rate=0.0002,
    )
    assert gapped["was_gapped"] is True
    assert gapped["net_pnl"] < naive["net_pnl"]


def test_gap_aware_net_pnl_with_gap_is_worse_for_short():
    gapped = gap_aware_net_pnl(
        side="SHORT", quantity=10.0, entry_price=100.0, entry_fee=0.4,
        stop_price=101.0, candle=_candle(105.0, 105.5, 104.5, 105.2),
        fee_rate=0.0004, slippage_rate=0.0002,
    )
    normal = gap_aware_net_pnl(
        side="SHORT", quantity=10.0, entry_price=100.0, entry_fee=0.4,
        stop_price=101.0, candle=_candle(100.9, 101.2, 100.5, 101.0),
        fee_rate=0.0004, slippage_rate=0.0002,
    )
    assert gapped["was_gapped"] is True
    assert gapped["net_pnl"] < normal["net_pnl"]


# =========================================================
# Determinism
# =========================================================


def test_deterministic():
    candle = _candle(97.0, 97.5, 96.5, 97.2)
    r1 = gap_aware_net_pnl("LONG", 10.0, 100.0, 0.4, 99.0, candle, 0.0004, 0.0002)
    r2 = gap_aware_net_pnl("LONG", 10.0, 100.0, 0.4, 99.0, candle, 0.0004, 0.0002)
    assert r1 == r2
