from strategy.decision_engine import make_decision


def run_decision(
    signal="bullish_order_block",
    liquidity_sweep="NO_SWEEP",
    liquidity_strength=0.0,
    market_structure="RANGE",
    bos="NO_BOS",
    bos_quality="NONE",
    choch="NO_CHOCH",
    volume_ratio=0.5,
    open_interest_change=0.0,
    funding_rate=0.0
):
    return make_decision(
        signal=signal,
        liquidity_sweep=liquidity_sweep,
        liquidity_strength=liquidity_strength,
        market_structure=market_structure,
        bos_quality={
            "bos": bos,
            "quality": bos_quality
        },
        choch=choch,
        volume_ratio=volume_ratio,
        open_interest_change=open_interest_change,
        funding_rate=funding_rate
    )


# =========================================================
# BULLISH BOS TESTS
# =========================================================

def test_bullish_strong_bos_gets_30_points():
    result = run_decision(
        signal="bullish_order_block",
        bos="BULLISH_BOS",
        bos_quality="STRONG"
    )

    assert result["bos_score"] == 30


def test_bullish_medium_bos_gets_20_points():
    result = run_decision(
        signal="bullish_order_block",
        bos="BULLISH_BOS",
        bos_quality="MEDIUM"
    )

    assert result["bos_score"] == 20


def test_bullish_weak_bos_gets_10_points():
    result = run_decision(
        signal="bullish_order_block",
        bos="BULLISH_BOS",
        bos_quality="WEAK"
    )

    assert result["bos_score"] == 10


def test_bearish_bos_does_not_support_bullish_setup():
    result = run_decision(
        signal="bullish_order_block",
        bos="BEARISH_BOS",
        bos_quality="STRONG"
    )

    assert result["bos_score"] == 0


# =========================================================
# BEARISH BOS TESTS
# =========================================================

def test_bearish_strong_bos_gets_30_points():
    result = run_decision(
        signal="bearish_order_block",
        bos="BEARISH_BOS",
        bos_quality="STRONG"
    )

    assert result["bos_score"] == 30


def test_bearish_medium_bos_gets_20_points():
    result = run_decision(
        signal="bearish_order_block",
        bos="BEARISH_BOS",
        bos_quality="MEDIUM"
    )

    assert result["bos_score"] == 20


def test_bearish_weak_bos_gets_10_points():
    result = run_decision(
        signal="bearish_order_block",
        bos="BEARISH_BOS",
        bos_quality="WEAK"
    )

    assert result["bos_score"] == 10


def test_bullish_bos_does_not_support_bearish_setup():
    result = run_decision(
        signal="bearish_order_block",
        bos="BULLISH_BOS",
        bos_quality="STRONG"
    )

    assert result["bos_score"] == 0


# =========================================================
# LIQUIDITY TESTS
# =========================================================

def test_bullish_sweep_supports_bullish_setup():
    result = run_decision(
        signal="bullish_order_block",
        liquidity_sweep="BULLISH_SWEEP",
        liquidity_strength=2.0
    )

    assert result["liquidity_score"] == 20


def test_bearish_sweep_does_not_support_bullish_setup():
    result = run_decision(
        signal="bullish_order_block",
        liquidity_sweep="BEARISH_SWEEP",
        liquidity_strength=2.0
    )

    assert result["liquidity_score"] == 0


def test_bearish_sweep_supports_bearish_setup():
    result = run_decision(
        signal="bearish_order_block",
        liquidity_sweep="BEARISH_SWEEP",
        liquidity_strength=2.0
    )

    assert result["liquidity_score"] == 20


def test_bullish_sweep_does_not_support_bearish_setup():
    result = run_decision(
        signal="bearish_order_block",
        liquidity_sweep="BULLISH_SWEEP",
        liquidity_strength=2.0
    )

    assert result["liquidity_score"] == 0


# =========================================================
# CHOCH TESTS
# =========================================================

def test_bearish_choch_penalizes_bullish_setup():
    result = run_decision(
        signal="bullish_order_block",
        choch="BEARISH_CHOCH"
    )

    assert result["choch_score"] == -20


def test_bullish_choch_does_not_penalize_bullish_setup():
    result = run_decision(
        signal="bullish_order_block",
        choch="BULLISH_CHOCH"
    )

    assert result["choch_score"] == 0


def test_bullish_choch_penalizes_bearish_setup():
    result = run_decision(
        signal="bearish_order_block",
        choch="BULLISH_CHOCH"
    )

    assert result["choch_score"] == -20


def test_bearish_choch_does_not_penalize_bearish_setup():
    result = run_decision(
        signal="bearish_order_block",
        choch="BEARISH_CHOCH"
    )

    assert result["choch_score"] == 0


# =========================================================
# COMBINED LOGIC TEST
# =========================================================

def test_strong_bos_with_opposite_choch_combines_correctly():
    result = run_decision(
        signal="bullish_order_block",
        bos="BULLISH_BOS",
        bos_quality="STRONG",
        choch="BEARISH_CHOCH"
    )

    assert result["bos_score"] == 30
    assert result["choch_score"] == -20
    assert result["score"] == 10
    assert result["decision"] == "IGNORE"