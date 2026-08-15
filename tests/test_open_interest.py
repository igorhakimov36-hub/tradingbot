from strategy.open_interest import calculate_open_interest_score


def test_open_interest_bullish_high():
    assert calculate_open_interest_score(
        3.0,
        "bullish_order_block",
    ) == 30


def test_open_interest_bullish_medium():
    assert calculate_open_interest_score(
        1.5,
        "bullish_order_block",
    ) == 20


def test_open_interest_bullish_low():
    assert calculate_open_interest_score(
        0.5,
        "bullish_order_block",
    ) == 10


def test_open_interest_bearish_high():
    assert calculate_open_interest_score(
        -3.0,
        "bearish_order_block",
    ) == 30


def test_open_interest_bearish_medium():
    assert calculate_open_interest_score(
        -1.5,
        "bearish_order_block",
    ) == 20


def test_open_interest_bearish_low():
    assert calculate_open_interest_score(
        -0.5,
        "bearish_order_block",
    ) == 10