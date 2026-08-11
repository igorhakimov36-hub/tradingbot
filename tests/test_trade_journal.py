from datetime import datetime, timezone

import pytest

from backtesting.trade_journal import (
    JournalEntry,
    TradeJournal,
)


def utc_time(
    hour: int = 12,
    minute: int = 0,
) -> datetime:
    return datetime(
        2025,
        1,
        1,
        hour,
        minute,
        tzinfo=timezone.utc,
    )


# =========================================================
# BASIC JOURNAL
# =========================================================

def test_new_journal_is_empty():
    journal = TradeJournal()

    assert len(journal) == 0
    assert journal.entries() == []


def test_record_accepts_valid_journal_entry():
    journal = TradeJournal()

    entry = JournalEntry(
        timestamp=utc_time(),
        event_type="SIGNAL",
        decision="LONG",
        score=85.0,
    )

    journal.record(entry)

    assert len(journal) == 1
    assert journal.entries()[0] == entry


def test_record_rejects_non_journal_entry():
    journal = TradeJournal()

    with pytest.raises(TypeError):
        journal.record(
            {
                "event_type": "SIGNAL"
            }
        )


# =========================================================
# TIMESTAMP SAFETY
# =========================================================

def test_naive_timestamp_is_rejected():
    journal = TradeJournal()

    naive_timestamp = datetime(
        2025,
        1,
        1,
        12,
        0,
    )

    with pytest.raises(ValueError):
        journal.record_signal(
            timestamp=naive_timestamp,
            decision="LONG",
            score=90.0,
        )


def test_invalid_timestamp_type_is_rejected():
    journal = TradeJournal()

    with pytest.raises(TypeError):
        journal.record_signal(
            timestamp="2025-01-01T12:00:00Z",
            decision="LONG",
            score=90.0,
        )


def test_timezone_aware_timestamp_is_allowed():
    journal = TradeJournal()

    journal.record_signal(
        timestamp=utc_time(),
        decision="LONG",
        score=90.0,
    )

    assert len(journal) == 1


# =========================================================
# SIGNAL / IGNORE
# =========================================================

def test_signal_is_recorded():
    journal = TradeJournal()

    journal.record_signal(
        timestamp=utc_time(),
        decision="LONG",
        score=87.5,
        metadata={
            "bos_score": 30,
            "liquidity_score": 25,
        },
    )

    entry = journal.entries()[0]

    assert entry.event_type == "SIGNAL"
    assert entry.decision == "LONG"
    assert entry.score == 87.5
    assert entry.metadata["bos_score"] == 30


def test_ignored_signal_is_recorded():
    journal = TradeJournal()

    journal.record_ignored(
        timestamp=utc_time(),
        score=65.0,
        metadata={
            "reason": "score_below_threshold"
        },
    )

    entry = journal.entries()[0]

    assert entry.event_type == "IGNORED"
    assert entry.decision == "IGNORE"
    assert entry.score == 65.0
    assert (
        entry.metadata["reason"]
        == "score_below_threshold"
    )


# =========================================================
# PENDING / REJECTED
# =========================================================

def test_pending_order_is_recorded():
    journal = TradeJournal()

    journal.record_pending(
        timestamp=utc_time(),
        side="LONG",
        requested_entry=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        quantity=2.0,
    )

    entry = journal.entries()[0]

    assert entry.event_type == "PENDING"
    assert entry.side == "LONG"
    assert entry.requested_entry == 100.0
    assert entry.stop_loss == 95.0
    assert entry.take_profit == 110.0
    assert entry.quantity == 2.0


def test_rejected_order_is_recorded():
    journal = TradeJournal()

    journal.record_rejected(
        timestamp=utc_time(),
        side="SHORT",
        requested_entry=100.0,
        reason="NOT_FILLED",
    )

    entry = journal.entries()[0]

    assert entry.event_type == "REJECTED"
    assert entry.side == "SHORT"
    assert entry.rejection_reason == "NOT_FILLED"


# =========================================================
# OPEN / CLOSE
# =========================================================

def test_opened_trade_is_recorded():
    journal = TradeJournal()

    journal.record_opened(
        timestamp=utc_time(),
        side="LONG",
        requested_entry=100.0,
        entry_price=100.1,
        stop_loss=95.0,
        take_profit=110.0,
        quantity=1.0,
        entry_fee=0.04,
    )

    entry = journal.entries()[0]

    assert entry.event_type == "OPENED"
    assert entry.side == "LONG"
    assert entry.requested_entry == 100.0
    assert entry.entry_price == 100.1
    assert entry.entry_fee == 0.04


def test_closed_trade_is_recorded():
    journal = TradeJournal()

    journal.record_closed(
        timestamp=utc_time(13),
        side="LONG",
        entry_price=100.1,
        exit_price=109.9,
        quantity=1.0,
        entry_fee=0.04,
        exit_fee=0.044,
        gross_pnl=9.8,
        net_pnl=9.716,
        exit_reason="TAKE_PROFIT",
    )

    entry = journal.entries()[0]

    assert entry.event_type == "CLOSED"
    assert entry.exit_price == 109.9
    assert entry.gross_pnl == 9.8
    assert entry.net_pnl == 9.716
    assert entry.exit_reason == "TAKE_PROFIT"


# =========================================================
# FILTERING
# =========================================================

def test_by_event_returns_only_requested_events():
    journal = TradeJournal()

    journal.record_signal(
        timestamp=utc_time(12),
        decision="LONG",
        score=90.0,
    )

    journal.record_ignored(
        timestamp=utc_time(12, 1),
        score=50.0,
    )

    journal.record_rejected(
        timestamp=utc_time(12, 2),
        side="LONG",
        requested_entry=100.0,
        reason="NOT_FILLED",
    )

    assert len(journal.by_event("SIGNAL")) == 1
    assert len(journal.by_event("IGNORED")) == 1
    assert len(journal.by_event("REJECTED")) == 1
    assert len(journal.by_event("CLOSED")) == 0


def test_closed_trades_returns_only_closed_events():
    journal = TradeJournal()

    journal.record_opened(
        timestamp=utc_time(12),
        side="LONG",
        requested_entry=100.0,
        entry_price=100.1,
        stop_loss=95.0,
        take_profit=110.0,
        quantity=1.0,
        entry_fee=0.04,
    )

    journal.record_closed(
        timestamp=utc_time(13),
        side="LONG",
        entry_price=100.1,
        exit_price=109.9,
        quantity=1.0,
        entry_fee=0.04,
        exit_fee=0.044,
        gross_pnl=9.8,
        net_pnl=9.716,
        exit_reason="TAKE_PROFIT",
    )

    assert len(journal.closed_trades()) == 1
    assert (
        journal.closed_trades()[0].event_type
        == "CLOSED"
    )


def test_rejected_orders_returns_only_rejections():
    journal = TradeJournal()

    journal.record_rejected(
        timestamp=utc_time(),
        side="LONG",
        requested_entry=100.0,
        reason="NOT_FILLED",
    )

    journal.record_ignored(
        timestamp=utc_time(12, 1),
        score=60.0,
    )

    assert len(journal.rejected_orders()) == 1
    assert (
        journal.rejected_orders()[0]
        .rejection_reason
        == "NOT_FILLED"
    )


def test_ignored_signals_returns_only_ignored():
    journal = TradeJournal()

    journal.record_ignored(
        timestamp=utc_time(),
        score=50.0,
    )

    journal.record_signal(
        timestamp=utc_time(12, 1),
        decision="LONG",
        score=90.0,
    )

    assert len(journal.ignored_signals()) == 1


# =========================================================
# ANALYTICS FOUNDATIONS
# =========================================================

def test_total_net_pnl_uses_closed_trades_only():
    journal = TradeJournal()

    journal.record_closed(
        timestamp=utc_time(13),
        side="LONG",
        entry_price=100.0,
        exit_price=110.0,
        quantity=1.0,
        entry_fee=0.1,
        exit_fee=0.1,
        gross_pnl=10.0,
        net_pnl=9.8,
        exit_reason="TAKE_PROFIT",
    )

    journal.record_closed(
        timestamp=utc_time(14),
        side="SHORT",
        entry_price=100.0,
        exit_price=105.0,
        quantity=1.0,
        entry_fee=0.1,
        exit_fee=0.1,
        gross_pnl=-5.0,
        net_pnl=-5.2,
        exit_reason="STOP_LOSS",
    )

    journal.record_ignored(
        timestamp=utc_time(15),
        score=40.0,
    )

    assert journal.total_net_pnl() == pytest.approx(
        4.6
    )


def test_total_fees_uses_closed_trades_only():
    journal = TradeJournal()

    journal.record_closed(
        timestamp=utc_time(13),
        side="LONG",
        entry_price=100.0,
        exit_price=110.0,
        quantity=1.0,
        entry_fee=0.10,
        exit_fee=0.12,
        gross_pnl=10.0,
        net_pnl=9.78,
        exit_reason="TAKE_PROFIT",
    )

    journal.record_closed(
        timestamp=utc_time(14),
        side="SHORT",
        entry_price=100.0,
        exit_price=90.0,
        quantity=1.0,
        entry_fee=0.11,
        exit_fee=0.09,
        gross_pnl=10.0,
        net_pnl=9.80,
        exit_reason="TAKE_PROFIT",
    )

    assert journal.total_fees() == pytest.approx(
        0.42
    )


# =========================================================
# DATA SAFETY / EXPORT
# =========================================================

def test_entries_returns_copy_of_internal_list():
    journal = TradeJournal()

    journal.record_signal(
        timestamp=utc_time(),
        decision="LONG",
        score=90.0,
    )

    external_entries = journal.entries()

    external_entries.clear()

    assert len(external_entries) == 0
    assert len(journal) == 1


def test_to_dicts_exports_journal_entries():
    journal = TradeJournal()

    journal.record_signal(
        timestamp=utc_time(),
        decision="LONG",
        score=88.0,
    )

    result = journal.to_dicts()

    assert isinstance(result, list)
    assert len(result) == 1

    assert result[0]["event_type"] == "SIGNAL"
    assert result[0]["decision"] == "LONG"
    assert result[0]["score"] == 88.0
    assert result[0]["timestamp"] == utc_time()