from strategy.order_block import detect_order_block


def _candle(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close}


BULLISH_LEG = [
    _candle(97, 100, 95, 99),
    _candle(99, 105, 98, 101),
    _candle(101, 102, 90, 98),
    _candle(98, 103, 96, 97),
    _candle(97, 104, 90, 100),
    _candle(100, 101, 96, 99),
]

BEARISH_LEG = [
    _candle(103, 105, 100, 101),
    _candle(101, 102, 98, 99),
    _candle(102, 110, 101, 105),
    _candle(103, 104, 97, 99),
    _candle(95, 96, 90, 92),
    _candle(96, 97, 96, 97),
]


def test_too_few_candles_returns_no_order_block():
    candles = [_candle(100, 101, 99, 100)] * 3

    assert detect_order_block(candles) == "no_order_block"


def test_bullish_break_of_structure_returns_bullish_order_block():
    candles = BULLISH_LEG + [_candle(104, 107, 103, 106)]

    assert detect_order_block(candles) == "bullish_order_block"


def test_bearish_break_of_structure_returns_bearish_order_block():
    candles = BEARISH_LEG + [_candle(90, 91, 84, 85)]

    assert detect_order_block(candles) == "bearish_order_block"


def test_no_break_of_structure_returns_no_order_block():
    candles = BULLISH_LEG + [_candle(99, 101, 98, 100)]

    assert detect_order_block(candles) == "no_order_block"
