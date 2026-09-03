from datetime import datetime, timedelta, timezone

import pytest

from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot
from strategy.setups.smt_reversal import SmtReversalSetup

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
SETUP = SmtReversalSetup()


def _pair_data(direction="bullish_divergence", event_timestamp=START, primary_price=100.0,
                reference_price=200.0, structural_agreement="diverging", price_correlation=0.8,
                history=None):
    if history is None:
        history = [{
            "direction": direction, "timestamp": event_timestamp,
            "primary_price": primary_price, "reference_price": reference_price,
        }] if direction != "none" else []

    return {
        "price_correlation": price_correlation,
        "structural_agreement": structural_agreement,
        "structural_divergence_flag": direction,
        "structural_divergence_history": history,
    }


def _snapshot(intermarket=None, current_price=150.0, timestamp=START):
    return MarketIntelligenceSnapshot(
        symbol="BTCUSDT", timeframe="15m", timestamp=timestamp, current_price=current_price,
        structure={}, zones=[], levels=[],
        order_flow={"delta": {}, "cvd": {}},
        sessions={"active_now": [], "previous_period_high_low": {}},
        intermarket=intermarket or {}, volume_profile={}, data_quality={},
    )


# =========================================================
# No fire - required condition
# =========================================================


def test_does_not_fire_with_no_intermarket_pairs():
    result = SETUP.evaluate(_snapshot(intermarket={}))

    assert result.fired is False
    assert result.direction is None
    assert result.required_conditions[0].name == "intermarket_divergence_this_bar"


def test_does_not_fire_with_empty_divergence_history():
    pair = _pair_data(direction="none")

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": pair}))

    assert result.fired is False


def test_does_not_fire_when_latest_divergence_is_stale():
    pair = _pair_data(direction="bullish_divergence", event_timestamp=START - timedelta(minutes=30))

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": pair}, timestamp=START))

    assert result.fired is False


# =========================================================
# Fires - direction inference
# =========================================================


def test_bullish_divergence_fires_long():
    pair = _pair_data(direction="bullish_divergence", event_timestamp=START)

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": pair}, timestamp=START))

    assert result.fired is True
    assert result.direction == "LONG"
    assert result.setup_name == "smt_reversal"


def test_bearish_divergence_fires_short():
    pair = _pair_data(direction="bearish_divergence", event_timestamp=START)

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": pair}, timestamp=START))

    assert result.fired is True
    assert result.direction == "SHORT"


def test_fires_even_with_zero_additional_evidence():
    pair = _pair_data(direction="bullish_divergence", event_timestamp=START,
                       structural_agreement="both_bullish", price_correlation=-0.3)

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": pair}, timestamp=START))

    assert result.fired is True
    assert result.evidence_count == 0


def test_first_pair_with_fresh_divergence_wins_deterministically():
    stale_pair = _pair_data(direction="bearish_divergence", event_timestamp=START - timedelta(minutes=30))
    fresh_pair = _pair_data(direction="bullish_divergence", event_timestamp=START)

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": stale_pair, "btc_total3": fresh_pair}, timestamp=START))

    assert result.fired is True
    assert result.direction == "LONG"


# =========================================================
# Stop-loss evidence (zone_high/zone_low, reused by the adapter unmodified)
# =========================================================


def test_bullish_divergence_places_pivot_as_zone_low():
    pair = _pair_data(direction="bullish_divergence", event_timestamp=START, primary_price=95.0)

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": pair}, current_price=100.0, timestamp=START))

    evidence = result.required_conditions[0].evidence
    assert evidence["zone_low"] == 95.0
    assert evidence["zone_high"] == 100.0


def test_bearish_divergence_places_pivot_as_zone_high():
    pair = _pair_data(direction="bearish_divergence", event_timestamp=START, primary_price=110.0)

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": pair}, current_price=100.0, timestamp=START))

    evidence = result.required_conditions[0].evidence
    assert evidence["zone_high"] == 110.0
    assert evidence["zone_low"] == 100.0


def test_evidence_preserved_for_stop_loss_placement():
    pair = _pair_data(direction="bullish_divergence", event_timestamp=START, primary_price=205.0)

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": pair}, timestamp=START))

    evidence = result.required_conditions[0].evidence
    assert evidence["pair_name"] == "btc_eth"
    assert evidence["zone_low"] == 205.0


# =========================================================
# Additional evidence
# =========================================================


def test_structural_agreement_evidence_satisfied_when_diverging():
    pair = _pair_data(direction="bullish_divergence", event_timestamp=START, structural_agreement="diverging")

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": pair}, timestamp=START))

    agreement = next(c for c in result.additional_evidence if c.name == "overall_structural_agreement_diverging")
    assert agreement.satisfied is True
    assert result.evidence_count >= 1


def test_structural_agreement_evidence_not_satisfied_when_both_bullish():
    pair = _pair_data(direction="bullish_divergence", event_timestamp=START, structural_agreement="both_bullish")

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": pair}, timestamp=START))

    agreement = next(c for c in result.additional_evidence if c.name == "overall_structural_agreement_diverging")
    assert agreement.satisfied is False


def test_positive_correlation_evidence_satisfied():
    pair = _pair_data(direction="bullish_divergence", event_timestamp=START, price_correlation=0.75)

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": pair}, timestamp=START))

    correlation_condition = next(c for c in result.additional_evidence if c.name == "pair_is_positively_correlated")
    assert correlation_condition.satisfied is True


def test_negative_correlation_evidence_not_satisfied():
    pair = _pair_data(direction="bullish_divergence", event_timestamp=START, price_correlation=-0.4)

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": pair}, timestamp=START))

    correlation_condition = next(c for c in result.additional_evidence if c.name == "pair_is_positively_correlated")
    assert correlation_condition.satisfied is False


def test_none_correlation_evidence_not_satisfied():
    pair = _pair_data(direction="bullish_divergence", event_timestamp=START, price_correlation=None)

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": pair}, timestamp=START))

    correlation_condition = next(c for c in result.additional_evidence if c.name == "pair_is_positively_correlated")
    assert correlation_condition.satisfied is False


def test_both_additional_conditions_can_agree_simultaneously():
    pair = _pair_data(direction="bearish_divergence", event_timestamp=START,
                       structural_agreement="diverging", price_correlation=0.9)

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": pair}, timestamp=START))

    assert result.fired is True
    assert result.evidence_count == 2


# =========================================================
# Reasoning chain
# =========================================================


def test_reasoning_explains_the_failure_when_not_fired():
    result = SETUP.evaluate(_snapshot(intermarket={}))

    assert "no configured intermarket pair" in result.reasoning.lower() or "no intermarket" in result.reasoning.lower()


def test_reasoning_explains_a_fired_setup():
    pair = _pair_data(direction="bullish_divergence", event_timestamp=START)

    result = SETUP.evaluate(_snapshot(intermarket={"btc_eth": pair}, timestamp=START))

    assert result.fired is True
    assert "LONG" in result.reasoning
    assert "smt reversal" in result.reasoning.lower()


def test_result_is_deterministic():
    pair = _pair_data(direction="bullish_divergence", event_timestamp=START)
    snapshot = _snapshot(intermarket={"btc_eth": pair}, timestamp=START)

    result_a = SETUP.evaluate(snapshot)
    result_b = SETUP.evaluate(snapshot)

    assert result_a == result_b
