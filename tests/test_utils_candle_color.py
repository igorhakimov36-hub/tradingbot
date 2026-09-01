from strategy.features.utils import is_bearish_candle, is_bullish_candle


def _candle(open_, close):
    return {"open": open_, "high": max(open_, close), "low": min(open_, close), "close": close}


def test_bullish_candle_detected():
    assert is_bullish_candle(_candle(open_=100, close=105)) is True
    assert is_bearish_candle(_candle(open_=100, close=105)) is False


def test_bearish_candle_detected():
    assert is_bearish_candle(_candle(open_=105, close=100)) is True
    assert is_bullish_candle(_candle(open_=105, close=100)) is False


def test_doji_is_neither():
    doji = _candle(open_=100, close=100)
    assert is_bullish_candle(doji) is False
    assert is_bearish_candle(doji) is False
