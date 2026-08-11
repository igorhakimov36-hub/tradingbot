from dataclasses import dataclass
from typing import Literal

from strategy.risk_management import calculate_position_size


Side = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class TradeSetup:
    side: Side

    entry_price: float
    stop_loss: float
    take_profit: float
    quantity: float

    risk_per_unit: float
    reward_per_unit: float
    risk_reward_ratio: float


def create_trade_setup(
    side: Side,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    quantity: float,
) -> TradeSetup:
    """
    Create and validate a trade setup.

    This module does NOT decide whether to enter a trade.

    It receives an already-approved LONG/SHORT decision
    and validates the proposed:

    - entry
    - stop loss
    - take profit
    - quantity

    It also calculates the planned risk/reward.
    """

    if side not in {"LONG", "SHORT"}:
        raise ValueError(
            "side must be LONG or SHORT"
        )

    if entry_price <= 0:
        raise ValueError(
            "entry_price must be positive"
        )

    if stop_loss <= 0:
        raise ValueError(
            "stop_loss must be positive"
        )

    if take_profit <= 0:
        raise ValueError(
            "take_profit must be positive"
        )

    if quantity <= 0:
        raise ValueError(
            "quantity must be positive"
        )

    if side == "LONG":
        if stop_loss >= entry_price:
            raise ValueError(
                "LONG stop_loss must be below entry"
            )

        if take_profit <= entry_price:
            raise ValueError(
                "LONG take_profit must be above entry"
            )

        risk_per_unit = (
            entry_price - stop_loss
        )

        reward_per_unit = (
            take_profit - entry_price
        )

    else:
        if stop_loss <= entry_price:
            raise ValueError(
                "SHORT stop_loss must be above entry"
            )

        if take_profit >= entry_price:
            raise ValueError(
                "SHORT take_profit must be below entry"
            )

        risk_per_unit = (
            stop_loss - entry_price
        )

        reward_per_unit = (
            entry_price - take_profit
        )

    risk_reward_ratio = (
        reward_per_unit / risk_per_unit
    )

    return TradeSetup(
        side=side,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        quantity=quantity,
        risk_per_unit=risk_per_unit,
        reward_per_unit=reward_per_unit,
        risk_reward_ratio=risk_reward_ratio,
    )


def create_risk_based_trade_setup(
    side: Side,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    equity: float,
    risk_percent: float,
) -> TradeSetup:
    """
    Create a TradeSetup whose quantity is calculated
    from account equity and allowed risk.

    Example:

        equity = 10,000
        risk_percent = 1%
        entry = 100
        stop = 95

        risk_amount = 100
        risk_per_unit = 5
        quantity = 20
    """

    position_size = calculate_position_size(
        equity=equity,
        risk_percent=risk_percent,
        entry_price=entry_price,
        stop_loss=stop_loss,
    )

    return create_trade_setup(
        side=side,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        quantity=position_size.quantity,
    )