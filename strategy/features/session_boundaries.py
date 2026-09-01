"""
Session Boundaries - Phase 1.7 of the Smart Money Core. Referenced but
never fully specced in docs/smart_money_architecture.md (see "Market
Structure > 5. Liquidity Pools", which explicitly defers to this
primitive, and strategy/features/delta.py's own docstring, which notes
`cumulative_session_delta` was deliberately deferred here too).

Purpose
-------
Professional/interbank trading treats the 24-hour day as overlapping
windows tied to the business hours of a financial center (Tokyo,
London, New York), not arbitrary fixed UTC bands. Crypto never closes,
but volume and volatility still visibly cluster around these windows,
because the same institutional participants (and the algo/retail flow
that shadows them) are active during their own local hours. ICT/SMC
concepts built on top of this: session highs/lows act as resting-
liquidity targets (a London/NY session often "sweeps" the prior Asian
session's high or low before the real directional move - the "Judas
swing" idea); Kill Zones are narrower, higher-conviction sub-windows
within a session; previous session/day/week highs-lows are draw-on-
liquidity reference levels; Opening Range is the high/low of the first
few minutes after a period opens.

The key design insight is that all of the above are the SAME
primitive: "accumulate a high/low from an anchor point until the next
anchor." A Kill Zone is not a different concept from a session - it is
a session with a shorter local-time window. Daily/Weekly high-low are
not a different concept either - they are the same mechanic anchored
to a calendar boundary (local midnight, or a specific weekday) instead
of a named window. This module is deliberately ONE tracker, configured
with different definitions, rather than four or five near-duplicate
detectors - avoiding the "duplicated responsibility" failure mode
already flagged during Phase 0 and avoided again with Mitigation
Blocks (fields on Order Block, not a new tracker).

What makes this "institutional-grade" rather than retail: London and
New York observe Daylight Saving Time, so a session defined by a fixed
UTC window silently drifts an hour off the TRUE local session twice a
year. Tokyo does not observe DST, which is exactly why fixed-UTC-window
indicators "happen to work" for the Asian session and quietly drift for
London/NY. This module defines every window in LOCAL wall-clock time
via the IANA tz database (Python's stdlib `zoneinfo`) and converts to
UTC per-candle, so DST transitions are handled correctly automatically
- not worked around, not ignored.

Inputs
------
OHLCV only, any single timeframe - deliberately timeframe-agnostic,
same convention as every other module in this package. Also a list of
`SessionWindow` and/or `CalendarPeriod` definitions supplied by the
caller - sessions/kill-zones/daily/weekly are all just configuration,
never hardcoded logic. DEFAULT_SESSIONS below is an optional, clearly-
labeled convenience preset (commonly-cited approximate hours), not a
built-in default baked into the tracker itself - a caller must always
pass definitions explicitly.

Outputs (raw features only - see SessionBoundariesTracker.snapshot)
--------------------------------------------------------------------
Per configured definition name: `current` (the still-forming period, or
None while off-session for a SessionWindow) and `closed` (a bounded
history of completed periods), each exposing: name, period_start,
period_end (None while forming), session_high, session_low,
high_timestamp, low_timestamp, candle_count, is_closed, timeframe,
context. No score, no threshold, no BUY/SELL - "previous session
high/low" is just the most recent entry in `closed`, not a separate
concept requiring separate plumbing.

Dependencies
------------
None beyond stdlib OHLCV timestamps and `zoneinfo` (requires IANA tz
data - available via the OS on Linux/macOS, or the `tzdata` PyPI
package on Windows, which happens to already be present in this
project's venv as a transitive dependency; worth pinning explicitly if
this project ever gains a requirements manifest). Consumed by (not
built yet): Liquidity Pools (session-extreme sub-detector, via the same
explicit `sync(candles, session_snapshot)` composition pattern Breaker
Blocks already established with Order Blocks).

Replay Safety
-------------
Different flavor than BOS-confirmed objects (Order Blocks, Breaker
Blocks): a session's high/low is legitimately live and updates every
bar, so there is no single "confirmation instant" to gate exposure on.
The safety property here is that a period only closes when the CURRENT
candle's own timestamp crosses into a new anchor key relative to the
previous candle processed - never based on wall-clock "now," never
based on an assumed candle count, and never by peeking at what anchor
a future candle will fall into. `is_closed` distinguishes a still-
forming period from a resolved one, so a consumer can never mistake a
live extreme for a final one - the same pattern already used for
`mitigation_status`/`fill_status` elsewhere in this package.

Live Trading
------------
Pure function of a bounded recent state (the currently-open period per
definition) - no history rescanning. sync() uses the same "full growing
candle list, only new candles processed" contract as every other
tracker here.

Computational Complexity
-------------------------
O(d) per new candle, where d = number of configured definitions (a
handful - 3 sessions, a few kill zones, daily, weekly). Each definition
does one timezone conversion (`astimezone`, O(1)) and a time-window
comparison per candle. No component of this module ever rescans candle
history. Closed-period history is bounded per definition via
max_tracked_closed, mirroring every other tracker's mitigated/filled
list bound.

Known Limitations / Future Extension Points
--------------------------------------------
- Opening Range is not implemented as a first-class definition type in
  this pass - it is a trivial future wrapper around either definition
  type (freeze the same running extreme after N minutes past
  `period_start` instead of continuing until the next anchor), deferred
  to keep this module's surface focused on what Liquidity Pools/Kill
  Zones/Daily/Weekly actually need today.
- Daily/Weekly default anchor timezone in DEFAULT_SESSIONS is UTC
  midnight, matching Binance's own daily-candle/stats convention
  (crypto-native) rather than the FX convention of a 17:00 New York
  day-roll. This is a preset choice, not a limitation - `timezone` is
  fully configurable per CalendarPeriod.
- A SessionWindow with start_time == end_time is treated as "always in
  session, one instance per local day" (a full 24h window) rather than
  raising an error - a harmless, documented degenerate case.
- The commonly-cited Kill Zone hours in DEFAULT_SESSIONS vary by source
  in retail/ICT literature; they are provided as a labeled starting
  point, not an institutional standard - callers are expected to supply
  their own SessionWindow definitions if they have a different
  convention in mind, which is exactly why these are data, not logic.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

PeriodKind = Literal["daily", "weekly"]

DEFAULT_MAX_TRACKED_CLOSED = 500


@dataclass(frozen=True)
class SessionWindow:
    """
    A recurring, local-time-of-day window - covers named sessions
    (Asian/London/New York) and Kill Zones alike; a Kill Zone is simply
    a SessionWindow with a shorter duration.

    `end_time <= start_time` means the window wraps past local
    midnight (e.g. a window from 22:00 to 02:00 local time). Either
    time may be provided as `time(0, 0)` for both, which is treated as
    "always in session" (see module Known Limitations).
    """

    name: str
    timezone: str
    start_time: time
    end_time: time


@dataclass(frozen=True)
class CalendarPeriod:
    """
    A recurring calendar-boundary window - covers Daily and Weekly
    high/low. Anchored to a timezone's local midnight (`period="daily"`)
    or to a specific weekday's local midnight (`period="weekly"`,
    `week_anchor_day`: Monday=0 ... Sunday=6).
    """

    name: str
    timezone: str
    period: PeriodKind
    week_anchor_day: int = 0


SessionDefinition = SessionWindow | CalendarPeriod


DEFAULT_SESSIONS: list[SessionDefinition] = [
    SessionWindow(name="asian", timezone="Asia/Tokyo", start_time=time(0, 0), end_time=time(9, 0)),
    SessionWindow(name="london", timezone="Europe/London", start_time=time(8, 0), end_time=time(16, 30)),
    SessionWindow(name="new_york", timezone="America/New_York", start_time=time(8, 0), end_time=time(17, 0)),
    SessionWindow(name="asian_killzone", timezone="Asia/Tokyo", start_time=time(0, 0), end_time=time(3, 0)),
    SessionWindow(name="london_killzone", timezone="Europe/London", start_time=time(7, 0), end_time=time(10, 0)),
    SessionWindow(name="new_york_killzone", timezone="America/New_York", start_time=time(7, 0), end_time=time(10, 0)),
    CalendarPeriod(name="daily", timezone="UTC", period="daily"),
    CalendarPeriod(name="weekly", timezone="UTC", period="weekly", week_anchor_day=0),
]


def _resolve_window_anchor(
    definition: SessionWindow,
    local_dt: datetime,
) -> date | None:
    """
    Returns the "window-day" this candle's local time belongs to (used
    as part of the anchor key identifying which specific instance of
    the recurring window this is), or None if the candle falls outside
    the window entirely (off-session).

    A wrapping window (end_time <= start_time) has two local-time
    halves: the "evening" half (local_time >= start_time, same
    window-day as the local date) and the "early morning" half
    (local_time < end_time, belongs to the window that STARTED the
    previous local day) - both must resolve to the same window-day so
    they are treated as one continuous session instance.
    """

    local_time = local_dt.time()
    local_date = local_dt.date()

    start, end = definition.start_time, definition.end_time

    if start == end:
        return local_date  # always in session - one instance per local day

    if start < end:
        if start <= local_time < end:
            return local_date
        return None

    # Wrapping window (end <= start)
    if local_time >= start:
        return local_date

    if local_time < end:
        return local_date - timedelta(days=1)

    return None


def _window_period_bounds(
    definition: SessionWindow,
    window_day: date,
) -> tuple[datetime, datetime]:
    tz = ZoneInfo(definition.timezone)
    start, end = definition.start_time, definition.end_time

    start_local = datetime.combine(window_day, start, tzinfo=tz)

    if start == end:
        end_local = start_local + timedelta(days=1)
    elif end <= start:
        end_local = datetime.combine(window_day + timedelta(days=1), end, tzinfo=tz)
    else:
        end_local = datetime.combine(window_day, end, tzinfo=tz)

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _resolve_calendar_anchor(
    definition: CalendarPeriod,
    local_dt: datetime,
) -> date:
    local_date = local_dt.date()

    if definition.period == "daily":
        return local_date

    days_since_anchor = (local_date.weekday() - definition.week_anchor_day) % 7
    return local_date - timedelta(days=days_since_anchor)


def _calendar_period_bounds(
    definition: CalendarPeriod,
    anchor_date: date,
) -> tuple[datetime, datetime]:
    tz = ZoneInfo(definition.timezone)
    start_local = datetime.combine(anchor_date, time(0, 0), tzinfo=tz)
    duration = timedelta(days=1) if definition.period == "daily" else timedelta(days=7)
    end_local = start_local + duration

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


@dataclass
class SessionExtreme:
    name: str
    period_start: datetime
    timeframe: str

    period_end: datetime | None = None
    session_high: float | None = None
    session_low: float | None = None
    high_timestamp: datetime | None = None
    low_timestamp: datetime | None = None
    candle_count: int = 0
    is_closed: bool = False
    context: dict[str, Any] = field(default_factory=dict)

    def apply_candle(self, candle: dict[str, Any], timestamp_key: str) -> None:
        self.candle_count += 1

        if self.session_high is None or candle["high"] > self.session_high:
            self.session_high = candle["high"]
            self.high_timestamp = candle[timestamp_key]

        if self.session_low is None or candle["low"] < self.session_low:
            self.session_low = candle["low"]
            self.low_timestamp = candle[timestamp_key]

    def close(self, period_end: datetime) -> None:
        self.period_end = period_end
        self.is_closed = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "session_high": self.session_high,
            "session_low": self.session_low,
            "high_timestamp": self.high_timestamp,
            "low_timestamp": self.low_timestamp,
            "candle_count": self.candle_count,
            "is_closed": self.is_closed,
            "timeframe": self.timeframe,
            "context": dict(self.context),
        }


class _DefinitionState:
    __slots__ = ("definition", "current", "closed", "last_anchor_key", "pending_period_end")

    def __init__(self, definition: SessionDefinition):
        self.definition = definition
        self.current: SessionExtreme | None = None
        self.closed: list[SessionExtreme] = []
        self.last_anchor_key: Any = None
        self.pending_period_end: datetime | None = None


class SessionBoundariesTracker:
    """
    Tracks one or more recurring session/calendar-period high-low
    extremes across a growing candle history.

    One instance per backtest run (or per live session), matching the
    lifecycle already used by every other tracker in this codebase.
    Call sync() once per replay step with the full candle history seen
    so far.
    """

    def __init__(
        self,
        definitions: list[SessionDefinition],
        timeframe: str = "unknown",
        max_tracked_closed: int = DEFAULT_MAX_TRACKED_CLOSED,
        timestamp_key: str = "timestamp",
    ):
        if not definitions:
            raise ValueError("definitions cannot be empty")

        names = [d.name for d in definitions]
        if len(names) != len(set(names)):
            raise ValueError("definition names must be unique")

        self.timestamp_key = timestamp_key
        self._timeframe = timeframe
        self._max_tracked_closed = max_tracked_closed

        self._states: dict[str, _DefinitionState] = {
            d.name: _DefinitionState(d) for d in definitions
        }

        self._consumed = 0
        self._last_candle: dict[str, Any] | None = None

    def sync(self, candles: list[dict[str, Any]]) -> None:
        if len(candles) < self._consumed:
            raise ValueError(
                "candles went backwards - SessionBoundariesTracker "
                "does not support rewinding"
            )

        if self._consumed > 0:
            checkpoint = candles[self._consumed - 1]

            if checkpoint != self._last_candle:
                raise ValueError(
                    "candles does not extend the history previously "
                    "seen by this SessionBoundariesTracker"
                )

        for candle in candles[self._consumed:]:
            self._ingest(candle)

        self._consumed = len(candles)

    def _ingest(self, candle: dict[str, Any]) -> None:
        timestamp: datetime = candle[self.timestamp_key]

        for state in self._states.values():
            self._ingest_for_definition(state, candle, timestamp)

        self._last_candle = candle

    def _ingest_for_definition(
        self,
        state: _DefinitionState,
        candle: dict[str, Any],
        timestamp: datetime,
    ) -> None:
        definition = state.definition
        local_dt = timestamp.astimezone(ZoneInfo(definition.timezone))

        if isinstance(definition, SessionWindow):
            anchor = _resolve_window_anchor(definition, local_dt)

            if anchor is None:
                if state.current is not None:
                    self._close_current(state)
                    state.last_anchor_key = None
                return

            period_start, period_end = _window_period_bounds(definition, anchor)
        else:
            anchor = _resolve_calendar_anchor(definition, local_dt)
            period_start, period_end = _calendar_period_bounds(definition, anchor)

        if anchor != state.last_anchor_key:
            if state.current is not None:
                self._close_current(state)

            state.current = SessionExtreme(
                name=definition.name,
                period_start=period_start,
                timeframe=self._timeframe,
            )
            state.last_anchor_key = anchor

        state.current.apply_candle(candle, self.timestamp_key)
        state.pending_period_end = period_end

    def _close_current(self, state: _DefinitionState) -> None:
        current = state.current
        current.close(state.pending_period_end)

        state.closed.append(current)

        if len(state.closed) > self._max_tracked_closed:
            state.closed = state.closed[-self._max_tracked_closed:]

        state.current = None

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "current": state.current.to_dict() if state.current else None,
                "closed": [period.to_dict() for period in state.closed],
            }
            for name, state in self._states.items()
        }
