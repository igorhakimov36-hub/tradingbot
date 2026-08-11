import pytest

from strategy.risk_management import (
    PositionSize,
    calculate_position_size,
)


# =========================================================
# BASIC CALCULATION
# =========================================================

def test_position_size_is_created():
    result = calculate_position_size(
        equity=10_000.0,
        risk_percent=1.0,
        entry_price=100.0,
        stop_loss=95.0,
    )

    assert isinstance(result, PositionSize)


def test_risk_amount_is_calculated_correctly():
    result = calculate_position_size(
        equity=10_000.0,
        risk_percent=1.0,
        entry_price=100.0,
        stop_loss=95.0,
    )

    assert result.risk_amount == pytest.approx(
        100.0
    )


def test_risk_per_unit_is_calculated_correctly():
    result = calculate_position_size(
        equity=10_000.0,
        risk_percent=1.0,
        entry_price=100.0,
        stop_loss=95.0,
    )

    assert result.risk_per_unit == pytest.approx(
        5.0
    )


def test_quantity_is_calculated_correctly():
    result = calculate_position_size(
        equity=10_000.0,
        risk_percent=1.0,
        entry_price=100.0,
        stop_loss=95.0,
    )

    # $100 account risk / $5 risk per unit
    assert result.quantity == pytest.approx(
        20.0
    )


def test_position_notional_is_calculated_correctly():
    result = calculate_position_size(
        equity=10_000.0,
        risk_percent=1.0,
        entry_price=100.0,
        stop_loss=95.0,
    )

    assert result.position_notional == pytest.approx(
        2_000.0
    )


# =========================================================
# SHORT POSITION
# =========================================================

def test_short_position_uses_absolute_stop_distance():
    result = calculate_position_size(
        equity=10_000.0,
        risk_percent=1.0,
        entry_price=100.0,
        stop_loss=105.0,
    )

    assert result.risk_per_unit == pytest.approx(
        5.0
    )

    assert result.quantity == pytest.approx(
        20.0
    )


# =========================================================
# DIFFERENT RISK PERCENTAGES
# =========================================================

def test_half_percent_risk():
    result = calculate_position_size(
        equity=10_000.0,
        risk_percent=0.5,
        entry_price=100.0,
        stop_loss=95.0,
    )

    assert result.risk_amount == pytest.approx(
        50.0
    )

    assert result.quantity == pytest.approx(
        10.0
    )


def test_two_percent_risk():
    result = calculate_position_size(
        equity=10_000.0,
        risk_percent=2.0,
        entry_price=100.0,
        stop_loss=95.0,
    )

    assert result.risk_amount == pytest.approx(
        200.0
    )

    assert result.quantity == pytest.approx(
        40.0
    )


# =========================================================
# STOP DISTANCE EFFECT
# =========================================================

def test_wider_stop_produces_smaller_position():
    tight_stop = calculate_position_size(
        equity=10_000.0,
        risk_percent=1.0,
        entry_price=100.0,
        stop_loss=95.0,
    )

    wide_stop = calculate_position_size(
        equity=10_000.0,
        risk_percent=1.0,
        entry_price=100.0,
        stop_loss=90.0,
    )

    assert (
        wide_stop.quantity
        < tight_stop.quantity
    )


def test_tighter_stop_produces_larger_position():
    wide_stop = calculate_position_size(
        equity=10_000.0,
        risk_percent=1.0,
        entry_price=100.0,
        stop_loss=90.0,
    )

    tight_stop = calculate_position_size(
        equity=10_000.0,
        risk_percent=1.0,
        entry_price=100.0,
        stop_loss=98.0,
    )

    assert (
        tight_stop.quantity
        > wide_stop.quantity
    )


def test_different_stop_distances_preserve_risk_budget():
    tight_stop = calculate_position_size(
        equity=10_000.0,
        risk_percent=1.0,
        entry_price=100.0,
        stop_loss=98.0,
    )

    wide_stop = calculate_position_size(
        equity=10_000.0,
        risk_percent=1.0,
        entry_price=100.0,
        stop_loss=90.0,
    )

    tight_total_risk = (
        tight_stop.quantity
        * tight_stop.risk_per_unit
    )

    wide_total_risk = (
        wide_stop.quantity
        * wide_stop.risk_per_unit
    )

    assert tight_total_risk == pytest.approx(
        100.0
    )

    assert wide_total_risk == pytest.approx(
        100.0
    )


# =========================================================
# EQUITY EFFECT
# =========================================================

def test_larger_equity_produces_larger_position():
    small_account = calculate_position_size(
        equity=10_000.0,
        risk_percent=1.0,
        entry_price=100.0,
        stop_loss=95.0,
    )

    large_account = calculate_position_size(
        equity=20_000.0,
        risk_percent=1.0,
        entry_price=100.0,
        stop_loss=95.0,
    )

    assert large_account.quantity == pytest.approx(
        small_account.quantity * 2
    )


# =========================================================
# VALIDATION
# =========================================================

@pytest.mark.parametrize(
    "equity",
    [0.0, -1.0, -10_000.0],
)
def test_equity_must_be_positive(equity):
    with pytest.raises(ValueError):
        calculate_position_size(
            equity=equity,
            risk_percent=1.0,
            entry_price=100.0,
            stop_loss=95.0,
        )


@pytest.mark.parametrize(
    "risk_percent",
    [0.0, -0.1, -10.0],
)
def test_risk_percent_must_be_positive(
    risk_percent,
):
    with pytest.raises(ValueError):
        calculate_position_size(
            equity=10_000.0,
            risk_percent=risk_percent,
            entry_price=100.0,
            stop_loss=95.0,
        )


@pytest.mark.parametrize(
    "risk_percent",
    [100.1, 150.0, 1000.0],
)
def test_risk_percent_cannot_exceed_100(
    risk_percent,
):
    with pytest.raises(ValueError):
        calculate_position_size(
            equity=10_000.0,
            risk_percent=risk_percent,
            entry_price=100.0,
            stop_loss=95.0,
        )


@pytest.mark.parametrize(
    "entry_price",
    [0.0, -1.0, -100.0],
)
def test_entry_price_must_be_positive(
    entry_price,
):
    with pytest.raises(ValueError):
        calculate_position_size(
            equity=10_000.0,
            risk_percent=1.0,
            entry_price=entry_price,
            stop_loss=95.0,
        )


@pytest.mark.parametrize(
    "stop_loss",
    [0.0, -1.0, -100.0],
)
def test_stop_loss_must_be_positive(
    stop_loss,
):
    with pytest.raises(ValueError):
        calculate_position_size(
            equity=10_000.0,
            risk_percent=1.0,
            entry_price=100.0,
            stop_loss=stop_loss,
        )


def test_entry_and_stop_cannot_be_equal():
    with pytest.raises(ValueError):
        calculate_position_size(
            equity=10_000.0,
            risk_percent=1.0,
            entry_price=100.0,
            stop_loss=100.0,
        )


# =========================================================
# RESULT VALUES
# =========================================================

def test_result_preserves_original_inputs():
    result = calculate_position_size(
        equity=25_000.0,
        risk_percent=0.75,
        entry_price=250.0,
        stop_loss=245.0,
    )

    assert result.equity == 25_000.0
    assert result.risk_percent == 0.75
    assert result.entry_price == 250.0
    assert result.stop_loss == 245.0