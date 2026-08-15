from strategy.volume import calculate_volume_score


def test_volume_score_high():
    assert calculate_volume_score(3.0, "bullish_order_block") == 25


def test_volume_score_medium():
    assert calculate_volume_score(2.0, "bullish_order_block") == 20


def test_volume_score_low():
    assert calculate_volume_score(1.3, "bullish_order_block") == 10


def test_volume_score_none():
    assert calculate_volume_score(0.5, "bullish_order_block") == 0