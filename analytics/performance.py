from dataclasses import dataclass
from math import sqrt

from backtesting.trade_journal import JournalEntry, TradeJournal


@dataclass(frozen=True)
class PerformanceReport:
    total_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int

    win_rate: float

    total_net_pnl: float
    average_net_pnl: float

    average_win: float
    average_loss: float

    gross_profit: float
    gross_loss: float
    profit_factor: float | None

    total_fees: float

    max_drawdown: float
    max_drawdown_percent: float

    sharpe_ratio: float | None


def _get_closed_trades(
    journal: TradeJournal,
) -> list[JournalEntry]:

    return journal.closed_trades()


def _calculate_max_drawdown(
    pnl_values: list[float],
    initial_equity: float,
) -> tuple[float, float]:

    if initial_equity <= 0:
        raise ValueError(
            "initial_equity must be positive"
        )

    equity = initial_equity
    peak_equity = initial_equity

    max_drawdown = 0.0
    max_drawdown_percent = 0.0

    for pnl in pnl_values:
        equity += pnl

        if equity > peak_equity:
            peak_equity = equity

        drawdown = peak_equity - equity

        if drawdown > max_drawdown:
            max_drawdown = drawdown

        if peak_equity > 0:
            drawdown_percent = (
                drawdown / peak_equity
            ) * 100.0

            if (
                drawdown_percent
                > max_drawdown_percent
            ):
                max_drawdown_percent = (
                    drawdown_percent
                )

    return (
        max_drawdown,
        max_drawdown_percent,
    )


def _calculate_sharpe_ratio(
    pnl_values: list[float],
) -> float | None:
    """
    Simple trade-level Sharpe ratio.

    This is intentionally NOT annualized yet.

    Later, when the system has real timestamps
    and a defined return frequency, we can add
    a time-based annualized Sharpe.
    """

    if len(pnl_values) < 2:
        return None

    mean_pnl = (
        sum(pnl_values)
        / len(pnl_values)
    )

    squared_differences = [
        (pnl - mean_pnl) ** 2
        for pnl in pnl_values
    ]

    variance = (
        sum(squared_differences)
        / (len(pnl_values) - 1)
    )

    standard_deviation = sqrt(variance)

    if standard_deviation == 0:
        return None

    return (
        mean_pnl
        / standard_deviation
    )


def calculate_performance(
    journal: TradeJournal,
    initial_equity: float = 10_000.0,
) -> PerformanceReport:

    if not isinstance(journal, TradeJournal):
        raise TypeError(
            "journal must be a TradeJournal"
        )

    if initial_equity <= 0:
        raise ValueError(
            "initial_equity must be positive"
        )

    closed_trades = _get_closed_trades(
        journal
    )

    pnl_values = [
        trade.net_pnl
        for trade in closed_trades
    ]

    total_trades = len(pnl_values)

    winning_values = [
        pnl
        for pnl in pnl_values
        if pnl > 0
    ]

    losing_values = [
        pnl
        for pnl in pnl_values
        if pnl < 0
    ]

    breakeven_values = [
        pnl
        for pnl in pnl_values
        if pnl == 0
    ]

    winning_trades = len(winning_values)
    losing_trades = len(losing_values)
    breakeven_trades = len(
        breakeven_values
    )

    if total_trades == 0:
        win_rate = 0.0
        average_net_pnl = 0.0
    else:
        win_rate = (
            winning_trades
            / total_trades
        ) * 100.0

        average_net_pnl = (
            sum(pnl_values)
            / total_trades
        )

    if winning_values:
        average_win = (
            sum(winning_values)
            / len(winning_values)
        )
    else:
        average_win = 0.0

    if losing_values:
        average_loss = (
            sum(losing_values)
            / len(losing_values)
        )
    else:
        average_loss = 0.0

    gross_profit = sum(
        winning_values
    )

    gross_loss = abs(
        sum(losing_values)
    )

    if gross_loss == 0:
        profit_factor = None
    else:
        profit_factor = (
            gross_profit
            / gross_loss
        )

    total_net_pnl = sum(
        pnl_values
    )

    total_fees = (
        journal.total_fees()
    )

    (
        max_drawdown,
        max_drawdown_percent,
    ) = _calculate_max_drawdown(
        pnl_values=pnl_values,
        initial_equity=initial_equity,
    )

    sharpe_ratio = (
        _calculate_sharpe_ratio(
            pnl_values
        )
    )

    return PerformanceReport(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        breakeven_trades=breakeven_trades,

        win_rate=win_rate,

        total_net_pnl=total_net_pnl,
        average_net_pnl=average_net_pnl,

        average_win=average_win,
        average_loss=average_loss,

        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,

        total_fees=total_fees,

        max_drawdown=max_drawdown,
        max_drawdown_percent=(
            max_drawdown_percent
        ),

        sharpe_ratio=sharpe_ratio,
    )