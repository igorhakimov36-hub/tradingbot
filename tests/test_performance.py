from datetime import datetime, timezone

import pytest

from analytics.performance import calculate_performance
from backtesting.trade_journal import TradeJournal


def utc_time(hour: int = 12) -> datetime:
    return datetime(
        2025,
        1,
        1,
        hour,
        0,
        tzinfo=timezone.utc,
    )


def add_closed_trade(
    journal: TradeJournal,
    hour: int,
    net_pnl: float,
    entry_fee: float = 0.0,
    exit_fee: float = 0.0,
) -> None:

    journal.record_closed(
        timestamp=utc_time(hour),
        side="LONG",
        entry_price=100.0,
        exit_price=110.0,
        quantity=1.0,
        entry_fee=entry_fee,
        exit_fee=exit_fee,
        gross_pnl=(
            net_pnl
            + entry_fee
            + exit_fee
        ),
        net_pnl=net_pnl,
        exit_reason="TEST",
    )


# =========================================================
# VALIDATION
# =========================================================

def test_invalid_journal_type_is_rejected():
    with pytest.raises(TypeError):
        calculate_performance(
            journal=[]
        )


def test_zero_initial_equity_is_rejected():
    journal = TradeJournal()

    with pytest.raises(ValueError):
        calculate_performance(
            journal=journal,
            initial_equity=0.0,
        )


def test_negative_initial_equity_is_rejected():
    journal = TradeJournal()

    with pytest.raises(ValueError):
        calculate_performance(
            journal=journal,
            initial_equity=-1000.0,
        )


# =========================================================
# EMPTY JOURNAL
# =========================================================

def test_empty_journal_returns_zero_metrics():
    journal = TradeJournal()

    report = calculate_performance(
        journal=journal
    )

    assert report.total_trades == 0
    assert report.winning_trades == 0
    assert report.losing_trades == 0
    assert report.breakeven_trades == 0

    assert report.win_rate == 0.0

    assert report.total_net_pnl == 0.0
    assert report.average_net_pnl == 0.0

    assert report.average_win == 0.0
    assert report.average_loss == 0.0

    assert report.gross_profit == 0.0
    assert report.gross_loss == 0.0

    assert report.profit_factor is None

    assert report.total_fees == 0.0

    assert report.max_drawdown == 0.0
    assert report.max_drawdown_percent == 0.0

    assert report.sharpe_ratio is None


# =========================================================
# TRADE COUNTS / WIN RATE
# =========================================================

def test_trade_counts_are_correct():
    journal = TradeJournal()

    add_closed_trade(journal, 12, 100.0)
    add_closed_trade(journal, 13, -50.0)
    add_closed_trade(journal, 14, 0.0)

    report = calculate_performance(
        journal=journal
    )

    assert report.total_trades == 3
    assert report.winning_trades == 1
    assert report.losing_trades == 1
    assert report.breakeven_trades == 1


def test_win_rate_is_calculated_correctly():
    journal = TradeJournal()

    add_closed_trade(journal, 12, 100.0)
    add_closed_trade(journal, 13, 50.0)
    add_closed_trade(journal, 14, -25.0)
    add_closed_trade(journal, 15, -25.0)

    report = calculate_performance(
        journal=journal
    )

    assert report.win_rate == pytest.approx(
        50.0
    )


# =========================================================
# PNL
# =========================================================

def test_total_net_pnl_is_correct():
    journal = TradeJournal()

    add_closed_trade(journal, 12, 100.0)
    add_closed_trade(journal, 13, -40.0)
    add_closed_trade(journal, 14, 20.0)

    report = calculate_performance(
        journal=journal
    )

    assert report.total_net_pnl == pytest.approx(
        80.0
    )


def test_average_net_pnl_is_correct():
    journal = TradeJournal()

    add_closed_trade(journal, 12, 100.0)
    add_closed_trade(journal, 13, -40.0)
    add_closed_trade(journal, 14, 30.0)

    report = calculate_performance(
        journal=journal
    )

    assert report.average_net_pnl == pytest.approx(
        30.0
    )


def test_average_win_is_correct():
    journal = TradeJournal()

    add_closed_trade(journal, 12, 100.0)
    add_closed_trade(journal, 13, 50.0)
    add_closed_trade(journal, 14, -20.0)

    report = calculate_performance(
        journal=journal
    )

    assert report.average_win == pytest.approx(
        75.0
    )


def test_average_loss_is_correct():
    journal = TradeJournal()

    add_closed_trade(journal, 12, 100.0)
    add_closed_trade(journal, 13, -20.0)
    add_closed_trade(journal, 14, -40.0)

    report = calculate_performance(
        journal=journal
    )

    assert report.average_loss == pytest.approx(
        -30.0
    )


# =========================================================
# PROFIT FACTOR
# =========================================================

def test_profit_factor_is_correct():
    journal = TradeJournal()

    add_closed_trade(journal, 12, 100.0)
    add_closed_trade(journal, 13, 50.0)

    add_closed_trade(journal, 14, -30.0)
    add_closed_trade(journal, 15, -20.0)

    report = calculate_performance(
        journal=journal
    )

    # Gross profit = 150
    # Gross loss   = 50
    # PF           = 3
    assert report.gross_profit == pytest.approx(
        150.0
    )

    assert report.gross_loss == pytest.approx(
        50.0
    )

    assert report.profit_factor == pytest.approx(
        3.0
    )


def test_profit_factor_is_none_without_losses():
    journal = TradeJournal()

    add_closed_trade(journal, 12, 100.0)
    add_closed_trade(journal, 13, 50.0)

    report = calculate_performance(
        journal=journal
    )

    assert report.gross_loss == 0.0
    assert report.profit_factor is None


# =========================================================
# FEES
# =========================================================

def test_total_fees_are_correct():
    journal = TradeJournal()

    add_closed_trade(
        journal=journal,
        hour=12,
        net_pnl=100.0,
        entry_fee=1.0,
        exit_fee=2.0,
    )

    add_closed_trade(
        journal=journal,
        hour=13,
        net_pnl=-50.0,
        entry_fee=1.5,
        exit_fee=2.5,
    )

    report = calculate_performance(
        journal=journal
    )

    assert report.total_fees == pytest.approx(
        7.0
    )


# =========================================================
# DRAWDOWN
# =========================================================

def test_max_drawdown_is_calculated_from_equity_curve():
    journal = TradeJournal()

    # Equity:
    #
    # 10,000
    # 10,500   peak
    # 10,300
    #  9,900
    # 10,100
    #
    # Maximum drawdown:
    # 10,500 - 9,900 = 600

    add_closed_trade(journal, 12, 500.0)
    add_closed_trade(journal, 13, -200.0)
    add_closed_trade(journal, 14, -400.0)
    add_closed_trade(journal, 15, 200.0)

    report = calculate_performance(
        journal=journal,
        initial_equity=10_000.0,
    )

    assert report.max_drawdown == pytest.approx(
        600.0
    )

    assert (
        report.max_drawdown_percent
        == pytest.approx(
            (600.0 / 10_500.0) * 100.0
        )
    )


def test_no_drawdown_when_equity_only_rises():
    journal = TradeJournal()

    add_closed_trade(journal, 12, 100.0)
    add_closed_trade(journal, 13, 200.0)
    add_closed_trade(journal, 14, 300.0)

    report = calculate_performance(
        journal=journal
    )

    assert report.max_drawdown == 0.0
    assert report.max_drawdown_percent == 0.0


# =========================================================
# SHARPE
# =========================================================

def test_sharpe_is_none_with_one_trade():
    journal = TradeJournal()

    add_closed_trade(
        journal,
        12,
        100.0,
    )

    report = calculate_performance(
        journal=journal
    )

    assert report.sharpe_ratio is None


def test_sharpe_is_none_when_variance_is_zero():
    journal = TradeJournal()

    add_closed_trade(journal, 12, 100.0)
    add_closed_trade(journal, 13, 100.0)
    add_closed_trade(journal, 14, 100.0)

    report = calculate_performance(
        journal=journal
    )

    assert report.sharpe_ratio is None


def test_trade_level_sharpe_is_correct():
    journal = TradeJournal()

    add_closed_trade(journal, 12, 10.0)
    add_closed_trade(journal, 13, 20.0)
    add_closed_trade(journal, 14, 30.0)

    report = calculate_performance(
        journal=journal
    )

    # Mean = 20
    #
    # Sample standard deviation:
    # sqrt(
    #   ((10-20)^2 +
    #    (20-20)^2 +
    #    (30-20)^2) / 2
    # )
    #
    # = sqrt(100)
    # = 10
    #
    # Sharpe = 20 / 10 = 2

    assert report.sharpe_ratio == pytest.approx(
        2.0
    )


# =========================================================
# NON-TRADE EVENTS
# =========================================================

def test_ignored_and_rejected_events_do_not_affect_performance():
    journal = TradeJournal()

    add_closed_trade(
        journal,
        12,
        100.0,
    )

    journal.record_ignored(
        timestamp=utc_time(13),
        score=50.0,
    )

    journal.record_rejected(
        timestamp=utc_time(14),
        side="LONG",
        requested_entry=100.0,
        reason="NOT_FILLED",
    )

    report = calculate_performance(
        journal=journal
    )

    assert report.total_trades == 1
    assert report.total_net_pnl == pytest.approx(
        100.0
    )