import pytest

from strategy.trade_setup import (
    TradeSetup,
    create_trade_setup,
    create_risk_based_trade_setup,
)


# =========================================================
# LONG
# =========================================================

def test_valid_long_setup_is_created():
    setup = create_trade_setup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        quantity=2.0,
    )

    assert isinstance(setup, TradeSetup)
    assert setup.side == "LONG"

    assert setup.entry_price == 100.0
    assert setup.stop_loss == 95.0
    assert setup.take_profit == 110.0
    assert setup.quantity == 2.0


def test_long_risk_per_unit_is_correct():
    setup = create_trade_setup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        quantity=1.0,
    )

    assert setup.risk_per_unit == pytest.approx(
        5.0
    )


def test_long_reward_per_unit_is_correct():
    setup = create_trade_setup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        quantity=1.0,
    )

    assert setup.reward_per_unit == pytest.approx(
        10.0
    )


def test_long_risk_reward_ratio_is_correct():
    setup = create_trade_setup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        quantity=1.0,
    )

    assert setup.risk_reward_ratio == pytest.approx(
        2.0
    )


def test_long_stop_loss_must_be_below_entry():
    with pytest.raises(ValueError):
        create_trade_setup(
            side="LONG",
            entry_price=100.0,
            stop_loss=100.0,
            take_profit=110.0,
            quantity=1.0,
        )

    with pytest.raises(ValueError):
        create_trade_setup(
            side="LONG",
            entry_price=100.0,
            stop_loss=101.0,
            take_profit=110.0,
            quantity=1.0,
        )


def test_long_take_profit_must_be_above_entry():
    with pytest.raises(ValueError):
        create_trade_setup(
            side="LONG",
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=100.0,
            quantity=1.0,
        )

    with pytest.raises(ValueError):
        create_trade_setup(
            side="LONG",
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=99.0,
            quantity=1.0,
        )


# =========================================================
# SHORT
# =========================================================

def test_valid_short_setup_is_created():
    setup = create_trade_setup(
        side="SHORT",
        entry_price=100.0,
        stop_loss=105.0,
        take_profit=90.0,
        quantity=3.0,
    )

    assert isinstance(setup, TradeSetup)
    assert setup.side == "SHORT"

    assert setup.entry_price == 100.0
    assert setup.stop_loss == 105.0
    assert setup.take_profit == 90.0
    assert setup.quantity == 3.0


def test_short_risk_per_unit_is_correct():
    setup = create_trade_setup(
        side="SHORT",
        entry_price=100.0,
        stop_loss=105.0,
        take_profit=90.0,
        quantity=1.0,
    )

    assert setup.risk_per_unit == pytest.approx(
        5.0
    )


def test_short_reward_per_unit_is_correct():
    setup = create_trade_setup(
        side="SHORT",
        entry_price=100.0,
        stop_loss=105.0,
        take_profit=90.0,
        quantity=1.0,
    )

    assert setup.reward_per_unit == pytest.approx(
        10.0
    )


def test_short_risk_reward_ratio_is_correct():
    setup = create_trade_setup(
        side="SHORT",
        entry_price=100.0,
        stop_loss=105.0,
        take_profit=90.0,
        quantity=1.0,
    )

    assert setup.risk_reward_ratio == pytest.approx(
        2.0
    )


def test_short_stop_loss_must_be_above_entry():
    with pytest.raises(ValueError):
        create_trade_setup(
            side="SHORT",
            entry_price=100.0,
            stop_loss=100.0,
            take_profit=90.0,
            quantity=1.0,
        )

    with pytest.raises(ValueError):
        create_trade_setup(
            side="SHORT",
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=90.0,
            quantity=1.0,
        )


def test_short_take_profit_must_be_below_entry():
    with pytest.raises(ValueError):
        create_trade_setup(
            side="SHORT",
            entry_price=100.0,
            stop_loss=105.0,
            take_profit=100.0,
            quantity=1.0,
        )

    with pytest.raises(ValueError):
        create_trade_setup(
            side="SHORT",
            entry_price=100.0,
            stop_loss=105.0,
            take_profit=101.0,
            quantity=1.0,
        )


# =========================================================
# GENERAL VALIDATION
# =========================================================

def test_invalid_side_is_rejected():
    with pytest.raises(ValueError):
        create_trade_setup(
            side="INVALID",
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            quantity=1.0,
        )


@pytest.mark.parametrize(
    "entry_price",
    [0.0, -1.0, -100.0],
)
def test_entry_price_must_be_positive(
    entry_price,
):
    with pytest.raises(ValueError):
        create_trade_setup(
            side="LONG",
            entry_price=entry_price,
            stop_loss=95.0,
            take_profit=110.0,
            quantity=1.0,
        )


@pytest.mark.parametrize(
    "stop_loss",
    [0.0, -1.0, -100.0],
)
def test_stop_loss_must_be_positive(
    stop_loss,
):
    with pytest.raises(ValueError):
        create_trade_setup(
            side="LONG",
            entry_price=100.0,
            stop_loss=stop_loss,
            take_profit=110.0,
            quantity=1.0,
        )


@pytest.mark.parametrize(
    "take_profit",
    [0.0, -1.0, -100.0],
)
def test_take_profit_must_be_positive(
    take_profit,
):
    with pytest.raises(ValueError):
        create_trade_setup(
            side="LONG",
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=take_profit,
            quantity=1.0,
        )


@pytest.mark.parametrize(
    "quantity",
    [0.0, -1.0, -100.0],
)
def test_quantity_must_be_positive(
    quantity,
):
    with pytest.raises(ValueError):
        create_trade_setup(
            side="LONG",
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            quantity=quantity,
        )


# =========================================================
# QUANTITY DOES NOT CHANGE R:R
# =========================================================

def test_quantity_does_not_change_risk_reward_ratio():
    setup_small = create_trade_setup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        quantity=1.0,
    )

    setup_large = create_trade_setup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        quantity=100.0,
    )

    assert (
        setup_small.risk_reward_ratio
        == pytest.approx(
            setup_large.risk_reward_ratio
        )
    )

    # =========================================================
# RISK-BASED TRADE SETUP
# =========================================================

def test_risk_based_long_setup_calculates_quantity():
    setup = create_risk_based_trade_setup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        equity=10_000.0,
        risk_percent=1.0,
    )

    # Risk budget = 10,000 * 1% = 100
    # Risk per unit = 100 - 95 = 5
    # Quantity = 100 / 5 = 20
    assert setup.quantity == pytest.approx(
        20.0
    )


def test_risk_based_short_setup_calculates_quantity():
    setup = create_risk_based_trade_setup(
        side="SHORT",
        entry_price=100.0,
        stop_loss=105.0,
        take_profit=90.0,
        equity=10_000.0,
        risk_percent=1.0,
    )

    assert setup.quantity == pytest.approx(
        20.0
    )


def test_risk_based_setup_preserves_risk_budget():
    setup = create_risk_based_trade_setup(
        side="LONG",
        entry_price=100.0,
        stop_loss=98.0,
        take_profit=106.0,
        equity=10_000.0,
        risk_percent=1.0,
    )

    actual_planned_risk = (
        setup.quantity
        * setup.risk_per_unit
    )

    assert actual_planned_risk == pytest.approx(
        100.0
    )


def test_wider_stop_reduces_risk_based_quantity():
    tight = create_risk_based_trade_setup(
        side="LONG",
        entry_price=100.0,
        stop_loss=98.0,
        take_profit=110.0,
        equity=10_000.0,
        risk_percent=1.0,
    )

    wide = create_risk_based_trade_setup(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        equity=10_000.0,
        risk_percent=1.0,
    )

    assert wide.quantity < tight.quantity


def test_larger_equity_increases_risk_based_quantity():
    small = create_risk_based_trade_setup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        equity=10_000.0,
        risk_percent=1.0,
    )

    large = create_risk_based_trade_setup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        equity=20_000.0,
        risk_percent=1.0,
    )

    assert large.quantity == pytest.approx(
        small.quantity * 2
    )


def test_risk_based_setup_preserves_trade_levels():
    setup = create_risk_based_trade_setup(
        side="LONG",
        entry_price=250.0,
        stop_loss=245.0,
        take_profit=265.0,
        equity=25_000.0,
        risk_percent=0.5,
    )

    assert setup.side == "LONG"
    assert setup.entry_price == 250.0
    assert setup.stop_loss == 245.0
    assert setup.take_profit == 265.0


def test_risk_based_setup_calculates_risk_reward():
    setup = create_risk_based_trade_setup(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        equity=10_000.0,
        risk_percent=1.0,
    )

    assert setup.risk_per_unit == pytest.approx(
        5.0
    )

    assert setup.reward_per_unit == pytest.approx(
        10.0
    )

    assert setup.risk_reward_ratio == pytest.approx(
        2.0
    )


def test_risk_based_setup_rejects_invalid_equity():
    with pytest.raises(ValueError):
        create_risk_based_trade_setup(
            side="LONG",
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            equity=0.0,
            risk_percent=1.0,
        )


def test_risk_based_setup_rejects_invalid_risk_percent():
    with pytest.raises(ValueError):
        create_risk_based_trade_setup(
            side="LONG",
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            equity=10_000.0,
            risk_percent=0.0,
        )