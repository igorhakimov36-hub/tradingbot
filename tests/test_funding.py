from strategy.funding import calculate_funding_score


def test_funding_bullish_negative():
    assert calculate_funding_score(
        -0.01,
        "bullish_order_block",
    ) == 15


def test_funding_bullish_positive():
    assert calculate_funding_score(
        0.01,
        "bullish_order_block",
    ) == 0


def test_funding_bearish_positive():
    assert calculate_funding_score(
        0.01,
        "bearish_order_block",
    ) == 15


def test_funding_bearish_negative():
    assert calculate_funding_score(
        -0.01,
        "bearish_order_block",
    ) == 0