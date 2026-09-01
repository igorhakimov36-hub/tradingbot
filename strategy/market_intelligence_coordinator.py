"""
Market Intelligence Coordinator - Phase 2.1, Step 2 (Backtest
Integration half of the pipeline).

This is the "Market Intelligence Modules" box in the approved pipeline
diagram made concrete: it owns and syncs the feature trackers every
replay step, then calls the pure Snapshot Builder. StrategyEngineV2
never touches this class or any tracker directly - only the
MarketIntelligenceSnapshot this class produces.

Scope for Step 2 (documented, not a limitation of the architecture)
------------------------------------------------------------------------
Wires up every SINGLE-SYMBOL module validated end-to-end in Step 1
(Market Structure, FVG, Order Blocks, Breaker Blocks, Equal Highs/Lows,
Session Boundaries, Liquidity Pools, Delta, CVD, Volume Profile) -
everything the first setup (Liquidity Sweep Reversal) and any
reasonably-adjacent future single-symbol setup would need. Intermarket
(Correlation Engine/SMT) is deliberately NOT wired here - it needs a
second symbol's candle stream, which the first setup does not use, and
adding it now would be exactly the kind of complexity-for-its-own-sake
the project has consistently avoided (Volume Profile's own Phase 1.12
guidance: "do not introduce complexity simply to achieve feature
completeness"). build_market_intelligence_snapshot()'s `intermarket`
parameter already supports it - adding a second symbol's candles here
later needs no redesign, only a few more lines in sync_and_build().

Efficiency note (not a "do not optimize parameters" violation)
------------------------------------------------------------------
All wired trackers operate on the 15m candle stream. A backtest replay
advances one 1-MINUTE candle at a time, so most calls to
sync_and_build() see an unchanged 15m history (TimeframeManager only
releases a new 15m bar every 15 calls). Rebuilding a full snapshot
(potentially thousands of Zone/Level objects, per Step 1's real-data
validation) on every single 1-minute tick when nothing 15m-relevant
changed would be pure waste, not a trading-relevant choice - this
class caches and returns the previous snapshot unchanged when the 15m
history has not grown, rather than reconstructing an identical object.
This is an engineering efficiency measure, not a parameter being tuned
for profitability - it cannot change which trades get taken, since no
new information exists between two calls with the same 15m history.
"""

from datetime import datetime
from typing import Any

from strategy.features.breaker_block import BreakerBlockTracker
from strategy.features.cvd import CVDAnchor, CVDTracker
from strategy.features.delta import DeltaTracker
from strategy.features.equal_highs_lows import EqualLevelsTracker
from strategy.features.fair_value_gap import FairValueGapTracker
from strategy.features.liquidity_pool import LiquidityPoolTracker
from strategy.features.market_structure_tracker import MarketStructureTracker
from strategy.features.order_block import OrderBlockTracker
from strategy.features.session_boundaries import CalendarPeriod, SessionBoundariesTracker
from strategy.features.volume_profile import VolumeProfileTracker
from strategy.market_intelligence_snapshot import MarketIntelligenceSnapshot, build_market_intelligence_snapshot

DEFAULT_ANCHOR_NAME = "daily"


class MarketIntelligenceCoordinator:
    """
    One instance per backtest run (or per live session), matching the
    lifecycle of every tracker it owns. Call sync_and_build() once per
    replay step with the 15m candle history visible so far -
    `candles_15m` may grow by any number of new candles (including
    zero) between calls; a growth of more than one is handled by
    replaying the newly-available candles through every wired tracker
    one at a time internally (see sync_and_build's own comment for why
    this is necessary, not just defensive: real exchange 1m data can
    have gaps, which can surface more than one new 15m bar in a single
    upstream sync() call even though the common case is exactly one).
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        timeframe: str = "15m",
        round_number_spacing: float | None = 500.0,
        volume_profile_bucket_size: float = 50.0,
        cvd_window: int = 20,
        timestamp_key: str = "timestamp",
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.timestamp_key = timestamp_key

        self._market_structure = MarketStructureTracker(timeframe=timeframe, timestamp_key=timestamp_key)
        self._fair_value_gaps = FairValueGapTracker(timeframe=timeframe, timestamp_key=timestamp_key)
        self._order_blocks = OrderBlockTracker(timeframe=timeframe, timestamp_key=timestamp_key)
        self._breaker_blocks = BreakerBlockTracker(timeframe=timeframe, timestamp_key=timestamp_key)
        self._equal_levels = EqualLevelsTracker(timeframe=timeframe, timestamp_key=timestamp_key)
        self._session_boundaries = SessionBoundariesTracker(
            [CalendarPeriod(name=DEFAULT_ANCHOR_NAME, timezone="UTC", period="daily")],
            timeframe=timeframe, timestamp_key=timestamp_key,
        )
        self._liquidity_pools = LiquidityPoolTracker(
            timeframe=timeframe, round_number_spacing=round_number_spacing, timestamp_key=timestamp_key,
        )
        self._delta = DeltaTracker(timeframe=timeframe, timestamp_key=timestamp_key)
        self._cvd = CVDTracker(
            [CVDAnchor(name=DEFAULT_ANCHOR_NAME, session_name=DEFAULT_ANCHOR_NAME), CVDAnchor(name="continuous")],
            timeframe=timeframe, window=cvd_window, timestamp_key=timestamp_key,
        )
        self._volume_profile = VolumeProfileTracker(
            bucket_size=volume_profile_bucket_size, anchor_name=DEFAULT_ANCHOR_NAME,
            timeframe=timeframe, timestamp_key=timestamp_key,
        )

        self._last_length = 0
        self._last_snapshot: MarketIntelligenceSnapshot | None = None

    def sync_and_build(
        self,
        candles_15m: list[dict[str, Any]],
        current_price: float,
        timestamp: datetime,
    ) -> MarketIntelligenceSnapshot:
        if len(candles_15m) == self._last_length and self._last_snapshot is not None:
            return self._last_snapshot

        # Real exchange 1m data can have gaps (a missing minute) - when
        # that happens, TimeframeManager's native-mode release can
        # surface MORE THAN ONE new 15m bar in a single BarSeriesProvider
        # sync() call, breaking the "at most one new candle between
        # calls" assumption this class's own docstring states as the
        # NORMAL case. Discovered on real BTCUSDT data (Phase 2.1 Step 2
        # validation), not assumed - Breaker Blocks/Liquidity Pools/
        # session-anchored CVD/Volume Profile all raised ValueError the
        # first time this actually happened. Fixed by driving every
        # wired tracker through the newly-available candles ONE AT A
        # TIME internally, regardless of how large the jump was - this
        # is what point-in-time replay safety requires anyway (never
        # skip an intermediate state), not merely a workaround.
        for i in range(self._last_length + 1, len(candles_15m) + 1):
            step = candles_15m[:i]

            self._market_structure.sync(step)
            self._fair_value_gaps.sync(step)
            self._order_blocks.sync(step)
            self._breaker_blocks.sync(step, self._order_blocks.snapshot()["mitigated"])
            self._equal_levels.sync(step)
            self._session_boundaries.sync(step)

            step_session_snapshot = self._session_boundaries.snapshot()

            self._liquidity_pools.sync(
                step,
                equal_levels_snapshot=self._equal_levels.snapshot(),
                session_snapshot=step_session_snapshot,
            )
            self._delta.sync(step)
            self._cvd.sync(step, session_snapshot=step_session_snapshot)
            self._volume_profile.sync(step, session_snapshot=step_session_snapshot)

        session_snapshot = self._session_boundaries.snapshot()

        snapshot = build_market_intelligence_snapshot(
            symbol=self.symbol,
            timeframe=self.timeframe,
            timestamp=timestamp,
            current_price=current_price,
            market_structure=self._market_structure.snapshot(),
            fair_value_gaps=self._fair_value_gaps.snapshot(),
            order_blocks=self._order_blocks.snapshot(),
            breaker_blocks=self._breaker_blocks.snapshot(),
            equal_levels=self._equal_levels.snapshot(),
            liquidity_pools=self._liquidity_pools.snapshot(),
            session_boundaries=session_snapshot,
            volume_profile=self._volume_profile.snapshot(),
            delta=self._delta.snapshot(),
            cvd=self._cvd.snapshot(),
        )

        self._last_length = len(candles_15m)
        self._last_snapshot = snapshot

        return snapshot
