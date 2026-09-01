from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal


JournalEventType = Literal[
    "SIGNAL",
    "IGNORED",
    "PENDING",
    "REJECTED",
    "OPENED",
    "CLOSED",
]


@dataclass(frozen=True)
class JournalEntry:
    timestamp: datetime
    event_type: JournalEventType

    # Optional and last-in-line on purpose: portfolio support is being
    # prepared for, but no existing single-symbol caller should be
    # forced to name it.
    symbol: str | None = None

    decision: str | None = None
    side: str | None = None
    score: float | None = None

    requested_entry: float | None = None
    entry_price: float | None = None
    exit_price: float | None = None

    stop_loss: float | None = None
    take_profit: float | None = None
    quantity: float | None = None

    entry_fee: float = 0.0
    exit_fee: float = 0.0

    gross_pnl: float = 0.0
    net_pnl: float = 0.0

    exit_reason: str | None = None
    rejection_reason: str | None = None

    metadata: dict[str, Any] | None = None


class TradeJournal:
    """
    Stores the complete history of backtest decisions
    and execution events.

    Important:
    The journal records more than successful trades.

    It can also record:
    - signals
    - ignored signals
    - pending orders
    - rejected / unfilled orders
    - opened trades
    - closed trades
    """

    def __init__(self):
        self._entries: list[JournalEntry] = []


    def _validate_timestamp(
        self,
        timestamp: datetime,
    ) -> None:

        if not isinstance(timestamp, datetime):
            raise TypeError(
                "timestamp must be a datetime"
            )

        if (
            timestamp.tzinfo is None
            or timestamp.utcoffset() is None
        ):
            raise ValueError(
                "timestamp must be timezone-aware"
            )


    def record(
        self,
        entry: JournalEntry,
    ) -> None:

        if not isinstance(entry, JournalEntry):
            raise TypeError(
                "entry must be a JournalEntry"
            )

        self._validate_timestamp(
            entry.timestamp
        )

        self._entries.append(entry)


    def record_signal(
        self,
        timestamp: datetime,
        decision: str,
        score: float | None = None,
        metadata: dict[str, Any] | None = None,
        symbol: str | None = None,
    ) -> None:

        self.record(
            JournalEntry(
                timestamp=timestamp,
                event_type="SIGNAL",
                decision=decision,
                score=score,
                metadata=metadata,
                symbol=symbol,
            )
        )


    def record_ignored(
        self,
        timestamp: datetime,
        score: float | None = None,
        metadata: dict[str, Any] | None = None,
        symbol: str | None = None,
    ) -> None:

        self.record(
            JournalEntry(
                timestamp=timestamp,
                event_type="IGNORED",
                decision="IGNORE",
                score=score,
                metadata=metadata,
                symbol=symbol,
            )
        )


    def record_pending(
        self,
        timestamp: datetime,
        side: str,
        requested_entry: float,
        stop_loss: float,
        take_profit: float,
        quantity: float,
        metadata: dict[str, Any] | None = None,
        symbol: str | None = None,
    ) -> None:

        self.record(
            JournalEntry(
                timestamp=timestamp,
                event_type="PENDING",
                side=side,
                requested_entry=requested_entry,
                stop_loss=stop_loss,
                take_profit=take_profit,
                quantity=quantity,
                metadata=metadata,
                symbol=symbol,
            )
        )


    def record_rejected(
        self,
        timestamp: datetime,
        side: str,
        requested_entry: float,
        reason: str,
        metadata: dict[str, Any] | None = None,
        symbol: str | None = None,
    ) -> None:

        self.record(
            JournalEntry(
                timestamp=timestamp,
                event_type="REJECTED",
                side=side,
                requested_entry=requested_entry,
                rejection_reason=reason,
                metadata=metadata,
                symbol=symbol,
            )
        )


    def record_opened(
        self,
        timestamp: datetime,
        side: str,
        requested_entry: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        quantity: float,
        entry_fee: float,
        metadata: dict[str, Any] | None = None,
        symbol: str | None = None,
    ) -> None:

        self.record(
            JournalEntry(
                timestamp=timestamp,
                event_type="OPENED",
                side=side,
                requested_entry=requested_entry,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                quantity=quantity,
                entry_fee=entry_fee,
                metadata=metadata,
                symbol=symbol,
            )
        )


    def record_closed(
        self,
        timestamp: datetime,
        side: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
        entry_fee: float,
        exit_fee: float,
        gross_pnl: float,
        net_pnl: float,
        exit_reason: str,
        metadata: dict[str, Any] | None = None,
        symbol: str | None = None,
    ) -> None:

        self.record(
            JournalEntry(
                timestamp=timestamp,
                event_type="CLOSED",
                side=side,
                entry_price=entry_price,
                exit_price=exit_price,
                quantity=quantity,
                entry_fee=entry_fee,
                exit_fee=exit_fee,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                exit_reason=exit_reason,
                metadata=metadata,
                symbol=symbol,
            )
        )


    def entries(
        self,
    ) -> list[JournalEntry]:
        """
        Return a copy so external code cannot mutate
        the journal's internal list.
        """

        return list(self._entries)


    def by_event(
        self,
        event_type: JournalEventType,
    ) -> list[JournalEntry]:

        return [
            entry
            for entry in self._entries
            if entry.event_type == event_type
        ]


    def closed_trades(
        self,
    ) -> list[JournalEntry]:

        return self.by_event("CLOSED")


    def rejected_orders(
        self,
    ) -> list[JournalEntry]:

        return self.by_event("REJECTED")


    def ignored_signals(
        self,
    ) -> list[JournalEntry]:

        return self.by_event("IGNORED")


    def total_net_pnl(
        self,
    ) -> float:

        return sum(
            entry.net_pnl
            for entry in self.closed_trades()
        )


    def total_fees(
        self,
    ) -> float:
        """
        Fees are counted from CLOSED events only.

        A CLOSED event contains both the entry and
        exit fee for that completed trade.
        """

        return sum(
            entry.entry_fee + entry.exit_fee
            for entry in self.closed_trades()
        )


    def to_dicts(
        self,
    ) -> list[dict[str, Any]]:

        return [
            asdict(entry)
            for entry in self._entries
        ]


    def __len__(
        self,
    ) -> int:

        return len(self._entries)