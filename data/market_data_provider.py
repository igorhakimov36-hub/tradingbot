from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from backtesting.point_in_time import get_latest_two_available_records
from data.timeframe_manager import TimeframeManager


@dataclass(frozen=True)
class ReplayContext:
    """
    Everything a MarketDataProvider might need to update itself by
    one replay step. Every provider receives the exact same context;
    each one reads only the fields it actually needs. This is what
    lets a Provider be indifferent to whether "now" is advancing
    because of backtest replay or a live clock tick.
    """

    current_time: datetime
    current_candle: dict[str, Any]
    visible_history_1m: list[dict[str, Any]]


class MarketDataProvider(Protocol):
    """
    Anything that can answer "what do we know right now" for one
    named market-data stream, without ever revealing data from the
    future - regardless of where the data actually came from (CSV
    replay, REST poll, WebSocket stream) or which exchange it
    originated from. Strategy code consumes only the shape returned
    by snapshot(); it never sees a Provider directly.
    """

    name: str

    def sync(self, context: ReplayContext) -> None: ...

    def snapshot(self) -> Any: ...


class PointEventProvider:
    """
    For data that represents a single known value as of an instant
    (Funding, Open Interest, ...). Wraps the existing, unmodified
    get_latest_two_available_records() - no new alignment logic.
    """

    def __init__(
        self,
        name: str,
        records: list[dict[str, Any]],
        timestamp_key: str = "timestamp",
    ):
        self.name = name
        self._records = records
        self._timestamp_key = timestamp_key
        self._snapshot: dict[str, Any] | None = None

    def sync(self, context: ReplayContext) -> None:
        current, previous = get_latest_two_available_records(
            records=self._records,
            current_time=context.current_time,
            timestamp_key=self._timestamp_key,
        )

        self._snapshot = {"current": current, "previous": previous}

    def snapshot(self) -> Any:
        return self._snapshot


class BarSeriesProvider:
    """
    For data shaped like candles (a value per closed time bucket):
    a secondary timeframe, or a future per-candle Delta/Footprint/CVD
    series. Wraps the existing, unmodified TimeframeManager (native
    mode) - no new alignment logic, no aggregation from 1m.
    """

    def __init__(
        self,
        name: str,
        timeframe: str,
        native_series: list[dict[str, Any]],
        timestamp_key: str = "timestamp",
    ):
        self.name = name
        self._timeframe = timeframe
        self._manager = TimeframeManager(
            timeframes=[timeframe],
            native_series={timeframe: native_series},
            timestamp_key=timestamp_key,
        )

    def sync(self, context: ReplayContext) -> None:
        self._manager.sync(context.visible_history_1m)

    def snapshot(self) -> Any:
        return self._manager.get_history(self._timeframe)
