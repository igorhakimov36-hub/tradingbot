from strategy.market_structure import find_local_extrema, find_swing_pivots, get_last_swing_levels


# =========================================================
# find_local_extrema - the generic primitive find_swing_pivots is
# itself now built on top of (Phase 1.12, extracted for Volume
# Profile's HVN/LVN, which needs the identical fractal rule applied to
# a volume-by-price histogram instead of a price-by-time series)
# =========================================================


def test_find_local_extrema_detects_peaks_and_troughs():
    values = [1, 5, 2, 8, 3]

    peaks, troughs = find_local_extrema(values)

    assert peaks == [1, 3]
    assert troughs == [2]


def test_find_local_extrema_empty_when_too_short():
    assert find_local_extrema([1, 2]) == ([], [])


def test_find_local_extrema_matches_find_swing_pivots_via_highs_and_lows():
    highs = [100, 105, 102, 108, 104]
    lows = [90, 95, 88, 96, 92]

    high_peaks, _ = find_local_extrema(highs)
    _, low_troughs = find_local_extrema(lows)

    swing_highs, swing_lows = find_swing_pivots(highs, lows)

    assert [i for i, _ in swing_highs] == high_peaks
    assert [i for i, _ in swing_lows] == low_troughs


def test_find_swing_pivots_detects_high_and_low():
    highs = [100, 105, 102, 108, 104]
    lows = [90, 95, 88, 96, 92]

    swing_highs, swing_lows = find_swing_pivots(highs, lows)

    assert swing_highs == [(1, 105), (3, 108)]
    assert swing_lows == [(2, 88)]


def test_find_swing_pivots_empty_when_too_short():
    assert find_swing_pivots([100, 105], [90, 95]) == ([], [])


def test_find_swing_pivots_returns_every_pivot_not_just_last():
    highs = [100, 110, 100, 115, 100, 120, 100]
    lows = [50, 50, 50, 50, 50, 50, 50]

    swing_highs, _ = find_swing_pivots(highs, lows)

    assert len(swing_highs) == 3
    assert [price for _, price in swing_highs] == [110, 115, 120]


def test_get_last_swing_levels_matches_last_pivot_from_find_swing_pivots():
    highs = [100, 110, 100, 115, 100]
    lows = [50, 40, 50, 35, 50]

    swing_highs, swing_lows = find_swing_pivots(highs, lows)
    last_high, last_low = get_last_swing_levels(highs, lows)

    assert last_high == swing_highs[-1][1]
    assert last_low == swing_lows[-1][1]


def test_get_last_swing_levels_none_when_no_pivots():
    assert get_last_swing_levels([100, 101], [99, 98]) == (None, None)


def test_get_last_swing_levels_independent_high_low_availability():
    # A high pivot with no corresponding low pivot in range, and vice
    # versa - each side must be independently None/populated.
    highs = [100, 110, 100]
    lows = [50, 51, 52]  # monotonically increasing - no low pivot

    last_high, last_low = get_last_swing_levels(highs, lows)

    assert last_high == 110
    assert last_low is None
