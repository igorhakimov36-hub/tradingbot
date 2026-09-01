from datetime import datetime, timedelta, timezone
from typing import Any

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse_timeframe_minutes(timeframe: str) -> int:
    if len(timeframe) < 2:
        raise ValueError(f"Invalid timeframe: {timeframe}")

    unit = timeframe[-1]

    try:
        value = int(timeframe[:-1])
    except ValueError as exc:
        raise ValueError(f"Invalid timeframe: {timeframe}") from exc

    if value <= 0:
        raise ValueError(f"Invalid timeframe: {timeframe}")

    if unit == "m":
        return value

    if unit == "h":
        return value * 60

    raise ValueError(f"Invalid timeframe: {timeframe}")


def _bucket_start(timestamp: datetime, minutes: int) -> datetime:
    elapsed_minutes = (timestamp - _EPOCH) // timedelta(minutes=minutes)

    return _EPOCH + elapsed_minutes * timedelta(minutes=minutes)


class TimeframeManager:
    """
    Exposes higher-timeframe candle histories derived from a
    point-in-time-safe 1m feed, without ever leaking a bar before it
    has actually closed.

    Two sources are supported per timeframe:

    - Derived (default): candles are aggregated on the fly from the
      1m history passed to sync().
    - Native: a real, independently-sourced candle series for that
      timeframe (e.g. Binance's own 15m klines) is supplied via
      `native_series`. No aggregation happens - candles are simply
      released once their own closing boundary (open time + duration)
      has been reached by the 1m clock.

    Either way, a bar is only exposed through get_history() once the
    market has actually moved past its close - never based on an
    assumed candle count. This is what keeps both modes safe against
    gaps in the source data and against look-ahead bias.

    One instance is meant to live for exactly one backtest run. Call
    sync() once per replay step with the full visible_history_1m seen
    so far; only the candles added since the last call are processed.
    """

    SOURCE_TIMEFRAME_MINUTES = 1

    def __init__(
        self,
        timeframes: list[str],
        native_series: dict[str, list[dict[str, Any]]] | None = None,
        timestamp_key: str = "timestamp",
    ):
        if not timeframes:
            raise ValueError("timeframes cannot be empty")

        self.timestamp_key = timestamp_key

        self._minutes: dict[str, int] = {}

        for timeframe in timeframes:
            minutes = _parse_timeframe_minutes(timeframe)

            if minutes <= self.SOURCE_TIMEFRAME_MINUTES:
                raise ValueError(
                    f"{timeframe} must be larger than the "
                    f"{self.SOURCE_TIMEFRAME_MINUTES}m source timeframe"
                )

            self._minutes[timeframe] = minutes

        native_series = native_series or {}

        for timeframe in native_series:
            if timeframe not in self._minutes:
                raise ValueError(
                    f"native_series has an entry for '{timeframe}' "
                    f"which was not declared in timeframes"
                )

        self._native_candles: dict[str, list[dict[str, Any]]] = {
            timeframe: sorted(series, key=lambda c: c[timestamp_key])
            for timeframe, series in native_series.items()
        }

        self._native_index: dict[str, int] = {
            timeframe: 0 for timeframe in self._native_candles
        }

        self._closed: dict[str, list[dict[str, Any]]] = {
            timeframe: [] for timeframe in self._minutes
        }

        self._forming: dict[str, dict[str, Any] | None] = {
            timeframe: None for timeframe in self._minutes
        }

        self._consumed = 0
        self._last_candle: dict[str, Any] | None = None
        self._last_timestamp: datetime | None = None

    def sync(self, visible_history_1m: list[dict[str, Any]]) -> None:
        if len(visible_history_1m) < self._consumed:
            raise ValueError(
                "visible_history_1m went backwards - TimeframeManager "
                "does not support rewinding"
            )

        if self._consumed > 0:
            checkpoint = visible_history_1m[self._consumed - 1]

            if checkpoint != self._last_candle:
                raise ValueError(
                    "visible_history_1m does not extend the history "
                    "previously seen by this TimeframeManager"
                )

        for candle in visible_history_1m[self._consumed :]:
            self._ingest(candle)

        self._consumed = len(visible_history_1m)

        for timeframe in self._native_candles:
            self._advance_native(timeframe)

    def _ingest(self, candle: dict[str, Any]) -> None:
        timestamp = candle[self.timestamp_key]

        if not isinstance(timestamp, datetime):
            raise TypeError(f"{self.timestamp_key} must be a datetime object")

        if self._last_timestamp is not None and timestamp < self._last_timestamp:
            raise ValueError("1m candles must be in chronological order")

        self._last_timestamp = timestamp
        self._last_candle = candle

        for timeframe, minutes in self._minutes.items():
            if timeframe in self._native_candles:
                # Real candles already exist for this timeframe -
                # aggregating from 1m would be redundant and could
                # subtly disagree with the exchange's own bars.
                continue

            bucket_start = _bucket_start(timestamp, minutes)
            forming = self._forming[timeframe]

            if forming is None or bucket_start > forming[self.timestamp_key]:
                if forming is not None:
                    self._closed[timeframe].append(forming)

                self._forming[timeframe] = self._new_bucket(bucket_start, candle)

                continue

            self._merge(forming, candle)

    def _new_bucket(
        self,
        bucket_start: datetime,
        candle: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            self.timestamp_key: bucket_start,
            "open": candle["open"],
            "high": candle["high"],
            "low": candle["low"],
            "close": candle["close"],
            "volume": candle["volume"],
            "taker_buy_volume": candle.get("taker_buy_volume"),
        }

    def _merge(self, bucket: dict[str, Any], candle: dict[str, Any]) -> None:
        bucket["high"] = max(bucket["high"], candle["high"])
        bucket["low"] = min(bucket["low"], candle["low"])
        bucket["close"] = candle["close"]
        bucket["volume"] += candle["volume"]

        # A partial sum across some-known/some-missing minutes would be
        # a fabricated approximation, not an honest gap - the same
        # "never silently default to zero/partial" principle
        # strategy/features/delta.py already applies. One missing
        # contributing minute poisons the whole aggregated bucket.
        candle_taker_buy = candle.get("taker_buy_volume")

        if bucket["taker_buy_volume"] is None or candle_taker_buy is None:
            bucket["taker_buy_volume"] = None
        else:
            bucket["taker_buy_volume"] += candle_taker_buy

    def _advance_native(self, timeframe: str) -> None:
        """
        Release native candles whose *closing* boundary (open time +
        duration) has been reached by the 1m clock. A native candle's
        own timestamp is its open time, so comparing that directly
        against "now" would expose a bar up to a full timeframe early
        - this is the look-ahead trap this method exists to avoid.
        """

        if self._last_timestamp is None:
            return

        minutes = self._minutes[timeframe]
        series = self._native_candles[timeframe]
        index = self._native_index[timeframe]

        while index < len(series):
            candle = series[index]
            bucket_close = candle[self.timestamp_key] + timedelta(minutes=minutes)

            if bucket_close > self._last_timestamp:
                break

            self._closed[timeframe].append(dict(candle))
            index += 1

        self._native_index[timeframe] = index

        if (
            index < len(series)
            and series[index][self.timestamp_key] <= self._last_timestamp
        ):
            self._forming[timeframe] = dict(series[index])
        else:
            self._forming[timeframe] = None

    def get_history(self, timeframe: str) -> list[dict[str, Any]]:
        """
        Only CLOSED candles for `timeframe`. The currently forming
        bar is never included here.
        """

        self._validate_timeframe(timeframe)

        return list(self._closed[timeframe])

    def get_forming_candle(self, timeframe: str) -> dict[str, Any] | None:
        """
        The in-progress (not yet closed) candle for `timeframe`, if
        any. Callers must not treat this as a confirmed bar for
        structure detection (BOS/CHoCH/order blocks/liquidity).
        """

        self._validate_timeframe(timeframe)

        forming = self._forming[timeframe]

        return dict(forming) if forming is not None else None

    def get_all_histories(self) -> dict[str, list[dict[str, Any]]]:
        return {timeframe: self.get_history(timeframe) for timeframe in self._minutes}

    def _validate_timeframe(self, timeframe: str) -> None:
        if timeframe not in self._minutes:
            raise ValueError(f"Unknown timeframe: {timeframe}")
