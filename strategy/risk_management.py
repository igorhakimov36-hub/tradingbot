from dataclasses import dataclass


@dataclass(frozen=True)
class PositionSize:
    equity: float
    risk_percent: float
    risk_amount: float

    entry_price: float
    stop_loss: float
    risk_per_unit: float

    quantity: float
    position_notional: float


def calculate_position_size(
    equity: float,
    risk_percent: float,
    entry_price: float,
    stop_loss: float,
) -> PositionSize:
    """
    Calculate position size from account risk.

    Example:

        equity = 10,000
        risk_percent = 1
        entry = 100
        stop = 95

    Maximum account risk:
        10,000 * 1% = 100

    Risk per unit:
        abs(100 - 95) = 5

    Quantity:
        100 / 5 = 20
    """

    if equity <= 0:
        raise ValueError(
            "equity must be positive"
        )

    if risk_percent <= 0:
        raise ValueError(
            "risk_percent must be positive"
        )

    if risk_percent > 100:
        raise ValueError(
            "risk_percent cannot exceed 100"
        )

    if entry_price <= 0:
        raise ValueError(
            "entry_price must be positive"
        )

    if stop_loss <= 0:
        raise ValueError(
            "stop_loss must be positive"
        )

    if entry_price == stop_loss:
        raise ValueError(
            "entry_price and stop_loss "
            "cannot be equal"
        )

    risk_amount = (
        equity * (risk_percent / 100.0)
    )

    risk_per_unit = abs(
        entry_price - stop_loss
    )

    quantity = (
        risk_amount / risk_per_unit
    )

    position_notional = (
        quantity * entry_price
    )

    return PositionSize(
        equity=equity,
        risk_percent=risk_percent,
        risk_amount=risk_amount,
        entry_price=entry_price,
        stop_loss=stop_loss,
        risk_per_unit=risk_per_unit,
        quantity=quantity,
        position_notional=position_notional,
    )