# Strategy Engine V2 — Architectural Audit

**This is an inspection report, not a design document.** Every claim below was
verified by reading the actual committed source files on the date of this
audit (`strategy/market_intelligence_snapshot.py`,
`strategy/market_intelligence_coordinator.py`,
`strategy/setups/liquidity_sweep_reversal.py`,
`strategy/strategy_engine_v2.py`,
`strategy/strategy_engine_v2_backtest_adapter.py`, and every tracker's own
`snapshot()`/`to_dict()` method) — not by recalling what was intended when
each piece was built. Where a module is computed but unused, or wired but
never fed real data, that is stated plainly, not smoothed over.

No code was changed to produce this report.

**Documentation consistency note (added during the repository integrity
sprint, not a rewrite of the analysis below):** this audit reflects the
codebase as it existed at the end of Phase 2.1, when `LiquiditySweepReversalSetup`
was the only setup in existence. Two later setups changed the facts in
specific places this document states as general, still-current claims:
`VolumeNodeReversalSetup` (S003) now reads `snapshot.levels` (kind
`poc`/`hvn`/`vah`/`val`), and `SmtReversalSetup` (S004) now reads
`snapshot.intermarket` as its primary signal, with `MarketIntelligenceCoordinator`
wired to populate it with real data (Step 0, after this audit was written).
The specific sentences affected are flagged inline below with a
`[SUPERSEDED]` marker; nothing else in this document was changed.

---

## PART 1 — Complete Decision Flow

```
Raw OHLCV (1m, BacktestRunner.candles)
  |
  v
TimeframeManager (via BarSeriesProvider, native mode)
  - Purpose: releases pre-aggregated 15m candles, point-in-time-safe against
    the 1m replay clock.
  - Input: real 15m candle series (pre-computed once, outside the replay,
    from the same 1m data) + the growing 1m visible history each tick.
  - Output: market_snapshot["BTCUSDT"]["15m"] - a growing list of CLOSED
    15m candles, exposed to the strategy callback every 1m tick.
  - Dependencies: none beyond the raw candle data.
  |
  v
MarketIntelligenceCoordinator.sync_and_build()
  - Purpose: owns and syncs 10 Phase 1 feature trackers against the 15m
    candle stream, one new candle at a time (looped internally to handle
    real-data gaps - see the class's own docstring), then calls the pure
    Snapshot Builder. Caches and returns the previous snapshot unchanged
    when the 15m history has not grown (an efficiency measure, not a
    decision-relevant one).
  - Input: market_snapshot["BTCUSDT"]["15m"], current 1m candle's close,
    current 1m candle's timestamp.
  - Output: one MarketIntelligenceSnapshot.
  - Dependencies: MarketStructureTracker, FairValueGapTracker,
    OrderBlockTracker, BreakerBlockTracker, EqualLevelsTracker,
    SessionBoundariesTracker, LiquidityPoolTracker, DeltaTracker, CVDTracker,
    VolumeProfileTracker - imported and instantiated directly.
    **CorrelationTracker is not imported, not instantiated, not synced
    anywhere in this class.**
  |
  v
build_market_intelligence_snapshot() (strategy/market_intelligence_snapshot.py)
  - Purpose: pure mapping function - reshapes each tracker's already-computed
    snapshot() dict into the unified Zone/Level schema plus the structure/
    order_flow/sessions/volume_profile/data_quality sections. Performs no
    detection logic.
  - Input: the 10 trackers' snapshot() dicts (intermarket is an accepted
    parameter but the Coordinator never passes it, so it always defaults to
    `None` -> `{}`).
  - Output: MarketIntelligenceSnapshot (frozen dataclass).
  - Dependencies: none beyond the input dicts' documented shapes.
  |
  v
StrategyEngineV2.decide()
  - Purpose: evaluates every registered Setup against the snapshot, returns
    all results (fired and not).
  - Input: one MarketIntelligenceSnapshot.
  - Output: EngineDecision (all_results, fired_setups).
  - Dependencies: strategy.setups.base.Setup protocol only - verified by
    direct inspection that this file has zero imports from
    strategy.features.* or strategy.market_intelligence_coordinator.
  - **Exactly one Setup is registered anywhere in this codebase:
    LiquiditySweepReversalSetup.**
  |
  v
LiquiditySweepReversalSetup.evaluate()
  - Purpose: checks for a Liquidity Pool swept THIS bar + CVD confirmation +
    at least one of {CHOCH, multi-source pool, SMT} (permanent rule, added
    after controlled experimentation).
  - Input: the snapshot's `zones` (filtered to kind="liquidity_pool"),
    `order_flow["cvd"]`, `structure["choch"]`, `intermarket`.
  - Output: SetupResult (fired, direction, required_conditions,
    additional_evidence, evidence_count, reasoning).
  - Dependencies: strategy.market_intelligence_snapshot types only.
  |
  v
engine_decision_to_dict() (strategy/strategy_engine_v2.py)
  - Purpose: adapts EngineDecision into the {"decision": ...} dict shape
    BacktestRunner.run_strategy()'s strategy_callback contract requires.
  - Input: EngineDecision.
  - Output: dict with decision/setup_name/reasoning/evidence_count/
    required_conditions/additional_evidence. Never a "score" key.
  |
  v
strategy_callback (strategy/strategy_engine_v2_backtest_adapter.py)
  - Purpose: the actual function BacktestRunner calls. Reads
    market_snapshot["BTCUSDT"]["15m"], calls the Coordinator, calls the
    engine, enriches the dict with market_structure_regime/active_sessions
    (for POST-HOC reporting only - read below on why this is not a decision
    input), returns it.
  - Input: (current_candle, market_snapshot) - BacktestRunner's fixed
    signature.
  - Output: the decision dict above.
  |
  v
trade_setup_callback (same file)
  - Purpose: builds concrete order parameters for a fired LONG/SHORT.
    Reads the LAST fired SetupResult via a closure shared with
    strategy_callback (not recomputed). Stop-loss = swept pool's zone edge
    (zone_high for SHORT, zone_low for LONG) + a small buffer, falling back
    to a fixed 0.6% friction floor if that would be invalid or too tight.
    Take-profit = fixed 2R multiple of whatever risk resulted. Position size
    = create_risk_based_trade_setup (shared with the old engine), 1% equity
    risk.
  - Input: (decision, current_candle, market_snapshot, current_equity).
  - Output: TradeSetup (side, entry_price, stop_loss, take_profit, quantity).
  |
  v
BacktestRunner.run_strategy()
  - Purpose: submits the TradeSetup to ExecutionSimulator, records every
    event (SIGNAL/IGNORED/PENDING/REJECTED/OPENED/CLOSED) to TradeJournal
    with setup_name threaded through, tracks equity.
  - Input: the two callbacks above, the window's candle data.
  - Output: BacktestResult (journal, performance).
```

**Note on what the old engine's decision inputs never touch this flow.**
`strategy/strategy_engine.py`, `strategy/decision_engine.py`,
`strategy/order_block.py`, and `strategy/liquidity.py` still exist, are still
importable, and are still the baseline used for A/B comparison — but none of
them are called anywhere in the V2 flow above. Two systems coexist; this
audit covers only the V2 path.

---

## PART 2 — Market Intelligence Inventory

| Module | Tracker class | Snapshot fields (from `snapshot()`/`to_dict()`) | Status | Influences decisions? |
|---|---|---|---|---|
| Market Structure | `MarketStructureTracker` | `market_structure`, `last_swing_high`, `last_swing_low`, `bos`, `choch`, `timeframe`, `context` | PARTIALLY USED | **YES** — `choch` is read directly by the setup (`_choch_confirms`), one of the 3 additional-evidence checks. `bos`, `market_structure`, `last_swing_high/low` are computed and placed in the snapshot but never read by the setup. `market_structure` is read by the adapter, but only to annotate journal metadata for reporting — it does not affect firing. |
| Fair Value Gaps | `FairValueGapTracker` | `direction`, `zone_high`, `zone_low`, `created_at`, `timeframe`, `age_in_bars`, `gap_size`, `gap_size_atr_ratio`, `atr_at_creation`, `formation_volume`, `fill_status`, `fill_pct`, `distance_from_price`, `context` | UNUSED | **NO** — flows into `snapshot.zones` (kind="fvg"), but the only setup filters to `kind == "liquidity_pool"` and never reads FVG zones. |
| Order Blocks | `OrderBlockTracker` | `direction`, `zone_high`, `zone_low`, `created_at`, `origin_timestamp`, `timeframe`, `age_in_bars`, `formation_volume`, `atr_at_creation`, `impulse_strength`, `touch_count`, `mitigation_status`, `mitigation_pct`, `distance_from_price`, `mitigation_zone_high/low/pct/status`, `context` | UNUSED | **NO** — same reason as FVG; also feeds Breaker Blocks internally (Coordinator passes `order_blocks.snapshot()["mitigated"]` to `BreakerBlockTracker.sync()`), so it is not fully inert, but that consumer (Breaker Blocks) is itself unused by the setup. |
| Breaker Blocks | `BreakerBlockTracker` | `direction`, `zone_high`, `zone_low`, `created_at`, `source_direction`, `source_origin_timestamp`, `timeframe`, `age_in_bars`, `atr_at_creation`, `impulse_strength`, `touch_count`, `mitigation_status`, `mitigation_pct`, `distance_from_price`, `context` | UNUSED | **NO** — flows into `snapshot.zones` (kind="breaker_block"), never read. |
| Equal Highs/Lows | `EqualLevelsTracker` | `direction`, `level`, `pivot_prices`, `pivot_timestamps`, `pivot_count`, `max_deviation`, `created_at`, `timeframe`, `age_in_bars`, `swept_status`, `swept_timestamp`, `distance_from_price`, `context` | PARTIALLY USED | **YES, indirectly** — its own `snapshot.levels` entries (kind="equal_highs"/"equal_lows") are never read by the setup, but the Coordinator feeds this tracker's raw `snapshot()` output into `LiquidityPoolTracker.sync(equal_levels_snapshot=...)` — one of Liquidity Pools' three sub-detectors. Liquidity Pools IS read by the setup, so Equal Highs/Lows influences decisions only through that path, never directly. |
| Session Boundaries | `SessionBoundariesTracker` | Per anchor name: `{"current": {...}, "closed": [...]}`, each period exposing `name`, `period_start`, `period_end`, `session_high`, `session_low`, `high_timestamp`, `low_timestamp`, `candle_count`, `is_closed`, `timeframe`, `context` | PARTIALLY USED | **YES, indirectly** — feeds `LiquidityPoolTracker` (a sub-detector input) and anchors `CVDTracker`'s "daily" anchor (both read by the setup). Also anchors `VolumeProfileTracker` (which is itself unused - see below). Its own `snapshot.sessions`/session-kind `snapshot.levels` entries are read only by the adapter, for journal metadata, never for the decision itself. |
| Liquidity Pools | `LiquidityPoolTracker` | `direction`, `level`, `zone_high`, `zone_low`, `created_at`, `timeframe`, `age_in_bars`, `bars_since_last_touch`, `contributing_touches`, `touch_count`, `sources`, `swept_status`, `swept_timestamp`, `sweep_penetration`, `sweep_rejection`, `distance_from_price`, `context` | ACTIVE | **YES, directly** — the setup's Required Condition #1 (`liquidity_pool_swept_this_bar`) reads `zone.status`, `.resolution_detail`, `.resolved_at`, `.direction`, `.zone_high`, `.zone_low`, `.raw["sources"]`. The same `zone_high`/`zone_low` are read again by the adapter's `trade_setup_callback` for stop-loss placement. |
| Delta | `DeltaTracker` | `timeframe`, `cumulative_delta`, `bars_accumulated`, `bars_with_missing_data`, `delta`, `delta_pct`, `delta_direction`, `delta_strength` | PARTIALLY USED | **YES, indirectly only** — `snapshot.order_flow["delta"]` is populated but never read by the setup. `CVDTracker` calls `calculate_delta()` internally on every bar (not via the snapshot, via its own direct dependency inside `strategy/features/cvd.py`), so Delta's underlying computation genuinely feeds CVD, but the Delta *module's own tracker output* reaching the snapshot is unread. |
| CVD | `CVDTracker` | Per anchor name: `cvd`, `cvd_direction`, `cvd_change_over_window`, `cvd_slope`, `price_cvd_divergence_flag`, `cvd_exhaustion_flag`, `anchor_type`, `anchor_timestamp`, `bars_since_anchor`, `bars_with_missing_data`, `timeframe`, `context` | ACTIVE | **YES, directly** — Required Condition #2 (`cvd_confirms_reversal`) scans every configured anchor's `cvd_exhaustion_flag`/`price_cvd_divergence_flag`. Configured anchors in the Coordinator: `"daily"` (session-anchored) and `"continuous"`. |
| Volume Profile | `VolumeProfileTracker` | `period_type`, `period_start`, `period_end`, `poc_price`, `value_area_high`, `value_area_low`, `histogram`, `total_period_volume`, `data_quality`, `hvn_nodes`, `lvn_nodes`, `poc_shift_from_previous_period`, `value_area_overlap_ratio`, `bucket_size`, `value_area_percentage`, `timeframe`, `is_closed`, `context` | UNUSED | **NO** — flows into `snapshot.levels` (kind="poc"/"vah"/"val"/"hvn"/"lvn"), `snapshot.volume_profile`, and `snapshot.data_quality["volume_profile_data_quality"]`, but nothing downstream reads any of it. Unlike Delta/Equal Highs/Session Boundaries, Volume Profile has **no indirect path either** — it feeds no other tracker. |
| Correlation Engine / SMT | `CorrelationTracker` | `price_correlation`, `relative_strength_ratio`, `relative_strength_change_over_window`, `structural_agreement`, `structural_divergence_flag`, `structural_divergence_history`, `lead_lag_bars`, `lead_lag_correlation`, `bars_since_start`, `window`, `max_lag`, `timeframe`, `context` | **NOT WIRED** | **NO, structurally cannot** — this is a different category from "unused." The class is never imported, never instantiated, never synced anywhere in `MarketIntelligenceCoordinator`. The setup's `_smt_confirms` method is real, working code that reads `snapshot.intermarket`, but `intermarket` is always `{}` because the Coordinator never passes anything else to the Snapshot Builder. The SMT check in the running system evaluates `satisfied=False` on every single bar, unconditionally, by construction — not because SMT rarely agrees, but because there is no data for it to ever agree with. |

**Fourteen Phase 1 modules were built. Eleven trackers exist today** (Mitigation
Blocks was folded into Order Block's fields, not a separate tracker, per the
Phase 1.6 decision). Of those eleven: **2 are ACTIVE** (Liquidity Pools, CVD),
**4 are PARTIALLY USED via an indirect path** (Market Structure, Equal
Highs/Lows, Session Boundaries, Delta), **4 are fully UNUSED despite being
computed** (Fair Value Gaps, Order Blocks, Breaker Blocks, Volume Profile),
and **1 is not wired into the pipeline at all** (Correlation Engine/SMT).

---

## PART 3 — Snapshot Field Mapping

Every field on `MarketIntelligenceSnapshot`, traced to its producing tracker
and its consumer(s).

| Snapshot field | Producing tracker | Read by setup? | Read by adapter? | Affects a trade? |
|---|---|---|---|---|
| `symbol` | Coordinator (passthrough) | Yes (`SetupResult.symbol`) | No | No |
| `timeframe` | Coordinator (passthrough) | No | No | No |
| `timestamp` | Coordinator (passthrough) | Yes (`SetupResult.timestamp`; sweep-freshness check) | Yes (`timestamp` used to sync coordinator) | No |
| `current_price` | Coordinator (passthrough of `current_candle["close"]`) | No | No — the adapter re-reads `current_candle["close"]` directly, not through the snapshot | No |
| `structure["market_structure"]` | `MarketStructureTracker` | No | Yes, for journal metadata only | No |
| `structure["last_swing_high"/"last_swing_low"]` | `MarketStructureTracker` | No | No | No |
| `structure["bos"]` | `MarketStructureTracker` | No | No | No |
| `structure["choch"]` | `MarketStructureTracker` | **Yes** (`_choch_confirms`) | No | No (additional evidence only, not stop/target) |
| `zones` (kind="fvg") | `FairValueGapTracker` | No | No | No |
| `zones` (kind="order_block") | `OrderBlockTracker` | No | No | No |
| `zones` (kind="breaker_block") | `BreakerBlockTracker` | No | No | No |
| `zones` (kind="liquidity_pool") | `LiquidityPoolTracker` | **Yes** (`_find_fresh_sweep`, sweep condition) | No (adapter reads `SetupResult.required_conditions[0].evidence`, not the snapshot directly) | **Yes** (`zone_high`/`zone_low` -> stop-loss) |
| `levels` (all 9 kinds) | `EqualLevelsTracker`, `SessionBoundariesTracker`, `VolumeProfileTracker` | **No — never accessed anywhere in the setup** | No | No |
| `order_flow["delta"]` | `DeltaTracker` | No | No | No |
| `order_flow["cvd"]` | `CVDTracker` | **Yes** (`_cvd_confirms`) | No | No (gates firing only) |
| `sessions["active_now"]` | `SessionBoundariesTracker` | No | Yes, for journal metadata only | No |
| `sessions["previous_period_high_low"]` | `SessionBoundariesTracker` | No | No | No |
| `intermarket` | (never populated — Coordinator omits it) | **Yes** (`_smt_confirms`), but always empty | No | No |
| `volume_profile` | `VolumeProfileTracker` | No | No | No |
| `data_quality` | `DeltaTracker`, `CVDTracker`, `VolumeProfileTracker` (aggregated) | No | No | No |
| `context` | (always `{}`) | No | No | No |

**Of roughly 20 top-level/nested snapshot sections, 3 are read by the setup
(`structure.choch`, `zones` filtered to liquidity pools, `order_flow.cvd`)
and 2 more are read by the adapter for reporting only (`structure.
market_structure`, `sessions.active_now`). Every other field — including
the entire `levels` list, regardless of which of three trackers produced
an entry — is computed, placed in the snapshot, and never read again.**
`[SUPERSEDED]` As of S003, `VolumeNodeReversalSetup` reads `snapshot.levels`
(`poc`/`hvn`/`vah`/`val` kinds) — the `levels` list is no longer universally
unread, though this remained true for every setup that existed when this
audit was written.

---

## PART 4 — Setup Analysis

**Only one setup exists: `LiquiditySweepReversalSetup`.**

### Required conditions (all three must be true to fire)

| Condition | Producing module | Exact snapshot field read |
|---|---|---|
| `liquidity_pool_swept_this_bar` | Liquidity Pools | `snapshot.zones` filtered to `kind == "liquidity_pool" and status == "resolved" and resolution_detail == "swept" and resolved_at == snapshot.timestamp`; then `.direction`, `.zone_high`, `.zone_low`, `.raw["sources"]` |
| `cvd_confirms_reversal` | CVD | `snapshot.order_flow["cvd"][anchor]["cvd_exhaustion_flag"]` and `["price_cvd_divergence_flag"]`, for every configured anchor |
| `has_additional_confirmation` | Aggregate of the three "additional evidence" checks below (`evidence_count >= 1`) | Derived from the three rows below, not a separate snapshot field |

### Additional evidence (individually recorded; their count gates the third required condition above)

| Condition | Producing module | Exact snapshot field read |
|---|---|---|
| `choch_confirms_direction` | Market Structure | `snapshot.structure["choch"]` |
| `pool_has_multiple_sources` | Liquidity Pools | the same swept zone's `raw["sources"]` (length > 1) — no new snapshot field, reuses the sweep condition's own zone |
| `smt_confirms_direction` | Correlation Engine/SMT | `snapshot.intermarket[pair]["structural_divergence_flag"]` — always empty dict in the real system, so this condition can never be satisfied today |

**Only two Market Intelligence families out of four ever gate a real decision
in the running system**: Zones (via Liquidity Pools only) and Order Flow
(via CVD only). Structure contributes to evidence, never to the primary gate.
Levels and Intermarket contribute nothing measurable today — Levels because
nothing reads them, Intermarket because nothing feeds them.
`[SUPERSEDED]` This was true only for `LiquiditySweepReversalSetup` in
isolation. S003 (`VolumeNodeReversalSetup`) now gates its own required
condition on Levels; S004 (`SmtReversalSetup`, later rejected) gated its
required condition on Intermarket, and `MarketIntelligenceCoordinator` was
wired (Step 0) to actually feed it real data — "nothing feeds them" no
longer describes the current Coordinator.

---

## PART 5 — Unused Intelligence

For every module with zero real influence on today's decisions.

### Fair Value Gaps
**Why unused:** the one setup filters `snapshot.zones` to `kind ==
"liquidity_pool"` explicitly; FVG zones are never inspected.
**Integration difficulty:** low. FVG zones are already in the exact same
unified `Zone` schema as Liquidity Pools — reading `zone.kind == "fvg"` would
require the same handful of lines already used for reading Liquidity Pools.
**Natural consumer:** an "FVG Rebalance" setup (a return-to-fill setup,
already named as a candidate in the original Phase 2.1 setup-selection
discussion) would consume this directly; alternatively, an existing setup
could add "does an unfilled FVG exist near the swept pool" as new additional
evidence.

### Order Blocks
**Why unused:** same filtering reason as FVG — the setup only ever looks at
`kind == "liquidity_pool"`.
**Integration difficulty:** low, same unified schema reason as FVG. Slightly
richer fields available (`impulse_strength`, `mitigation_zone_*`) if a future
setup wants finer-grained detail than the base Zone schema exposes.
**Natural consumer:** an "Order Block Continuation" setup (the other
candidate named at setup-selection time); or as additional evidence for the
existing setup ("is there an unmitigated Order Block in the reversal
direction near price").

### Breaker Blocks
**Why unused:** same reason as FVG/Order Blocks. Its only current
consumption is structural (Order Blocks' `mitigated` list feeds Breaker
Blocks' own tracker at the Coordinator level), not decision-level.
**Integration difficulty:** low, same schema reason.
**Natural consumer:** a setup specifically about failed-then-flipped zones
acting as new support/resistance — this is Breaker Blocks' own institutional
purpose, and no existing setup approximates it.

### Volume Profile
**Why unused:** its `levels` entries (POC/VAH/VAL/HVN/LVN) are populated but
the setup never reads `snapshot.levels` at all — not specific to Volume
Profile, this applies to every Level-family module equally.
**Integration difficulty:** low-to-medium. Reading a nearby POC/VAH/VAL as
additional evidence is straightforward (same `Level` schema, `distance_from_
price` already computed). A "Volume Profile Acceptance/Rejection" setup
(named as a candidate in the Phase 2 review) would need the
`poc_shift_from_previous_period`/`value_area_overlap_ratio` fields
specifically, both already present on `snapshot.volume_profile` (not
currently exposed per-Level, only on the whole-profile dict) — reading those
two fields would need looking at `snapshot.volume_profile` directly, not
`snapshot.levels`, a small but real distinction to get right if built.
**Natural consumer:** either a dedicated acceptance/rejection setup, or as
additional evidence ("is the swept pool near a low-volume node, implying
price should move through quickly").

### Equal Highs/Lows and Session Boundaries
**Why partially unused:** already covered in Part 2 — these two are not
fully dark, they feed Liquidity Pools and (Session Boundaries only) CVD's
anchor and Volume Profile's anchor. What's unused specifically is their
*own* direct snapshot representation (`snapshot.levels` entries for
equal_highs/equal_lows/session_high/session_low, and `snapshot.sessions`
itself).
**Integration difficulty:** low — same Level schema as Volume Profile.
**Natural consumer:** a setup wanting to distinguish "which specific
sub-detector" contributed to a swept pool already has that information
available via `zone.raw["sources"]` (already read by `pool_has_multiple_
sources`) — reading the standalone Equal Highs/Lows or Session Boundaries
Level entries would mostly duplicate that, unless a future setup wants to
react to an *unswept* equal-level or session extreme specifically (a
distinct concept from "was absorbed into a pool").

### Delta
**Why unused:** `order_flow["delta"]` (per-bar delta/delta_pct/delta_
direction/delta_strength) is populated but never read; CVD's own internal
use of `calculate_delta()` is a separate code path, not a consumption of
this snapshot field.
**Integration difficulty:** trivial — it's a flat dict already in the
snapshot.
**Natural consumer:** any setup wanting immediate single-bar order-flow
confirmation *in addition to* CVD's cumulative view — e.g., "did the sweep
candle itself show strong opposing delta."

### Correlation Engine / SMT
**Why unused:** genuinely different from every module above — this one is
not merely unread, it is never computed in the running system at all.
`CorrelationTracker` requires a second symbol's candle stream, which the
Coordinator has never been given.
**Integration difficulty:** medium — not because the tracker or the setup's
consumption code needs work (both already exist and are tested), but
because it requires: (1) a second symbol's candles wired into
`BacktestRunner`'s `provider_specs` (already proven possible — Phase 1.10's
real BTC/ETH validation used exactly this), and (2) the Coordinator
instantiating and syncing a `CorrelationTracker` and passing its output as
`intermarket` to the Snapshot Builder — a real, if modest, Coordinator
change, not a one-line fix.
**Natural consumer:** the existing setup's `smt_confirms_direction`
condition would start actually contributing the moment this is wired — no
setup-level code change needed at all, only Coordinator + backtest-setup
change.

---

## PART 6 — Dependency Graph

```
Raw 1m candles
  |
  +--> TimeframeManager --> 15m candles
                              |
        +---------------------+---------------------+---------------------------+
        |                     |                       |                         |
        v                     v                       v                         v
  MarketStructureTracker  FairValueGapTracker    OrderBlockTracker        EqualLevelsTracker
        |                     |                       |                         |
        |                     |                       v                         |
        |                     |                 BreakerBlockTracker              |
        |                     |                 (consumes OrderBlock's           |
        |                     |                  own snapshot output)            |
        |                     |                       |                         |
        |                     |                       |                         v
        |                     |                       |                 LiquidityPoolTracker <---+
        |                     |                       |                       ^                  |
        |                     |                       |                       |                  |
        |               SessionBoundariesTracker ------+-----------------------+                  |
        |                     |                                                                   |
        |                     +--------------------------> CVDTracker (session-anchored)          |
        |                     |                                                                   |
        |                     +--------------------------> VolumeProfileTracker                   |
        |                     |                                (session-anchored, output UNUSED)  |
        |                     |                                                                   |
        |               DeltaTracker --(feeds internally, not via snapshot)--> CVDTracker          |
        |                                                                                          |
        |  (Session Boundaries' snapshot output also feeds Liquidity Pools directly, alongside ----+
        |   Equal Highs/Lows' snapshot output - both as explicit sync() parameters)
        |
        v
  build_market_intelligence_snapshot()
        |
        v
  MarketIntelligenceSnapshot
        |
        v
  StrategyEngineV2.decide()
        |
        v
  LiquiditySweepReversalSetup.evaluate()
        reads: zones[liquidity_pool], order_flow.cvd, structure.choch, intermarket (always empty)
        |
        v
  SetupResult --> engine_decision_to_dict() --> decision dict
        |
        v
  trade_setup_callback (reads SetupResult.required_conditions[0].evidence.zone_high/zone_low)
        |
        v
  TradeSetup --> BacktestRunner --> ExecutionSimulator --> TradeJournal

  CorrelationTracker: exists in strategy/features/correlation.py, imported
  and tested independently, but has NO edge into this graph at all - it is
  never instantiated by MarketIntelligenceCoordinator.

  Volume Profile: has an INCOMING edge (Session Boundaries anchors it) but
  NO OUTGOING edge - its own output reaches the Snapshot and stops there.
```

---

## PART 7 — Decision Coverage

| Module | Snapshot | Setup | Decision | Trade |
|---|---|---|---|---|
| Market Structure | ✓ | ✓ (choch only) | ✓ (additional evidence only) | ✗ |
| Fair Value Gaps | ✓ | ✗ | ✗ | ✗ |
| Order Blocks | ✓ | ✗ | ✗ | ✗ |
| Breaker Blocks | ✓ | ✗ | ✗ | ✗ |
| Equal Highs/Lows | ✓ (own fields unused; feeds Liquidity Pools) | ✗ (directly) | ✓ (indirectly, via Liquidity Pools) | ✗ |
| Session Boundaries | ✓ (own fields unused; feeds Liquidity Pools + CVD + Volume Profile) | ✗ (directly) | ✓ (indirectly, via Liquidity Pools and CVD) | ✗ |
| Liquidity Pools | ✓ | ✓ | ✓ (Required Condition #1) | ✓ (stop-loss) |
| Delta | ✓ (own field unused; feeds CVD internally) | ✗ (directly) | ✓ (indirectly, via CVD) | ✗ |
| CVD | ✓ | ✓ | ✓ (Required Condition #2) | ✗ |
| Volume Profile | ✓ | ✗ | ✗ | ✗ |
| Correlation Engine / SMT | ✗ (never populated) | code exists, always evaluates False | ✗ | ✗ |

---

## PART 8 — Redundancy

**Duplicated logic:** none found. Every zone-lifecycle computation
(mitigation/fill/sweep math) still runs through the shared
`zone_lifecycle.py` functions established in Phase 1; the Snapshot Builder
reuses tracker outputs verbatim per its own stated design; the setup and
adapter each read distinct, non-overlapping slices of the `SetupResult`
(the setup builds `required_conditions`, the adapter only ever reads
`required_conditions[0].evidence` for the stop price — no recomputation).

**Snapshot fields never read by anything:** the entire `levels` list (all
nine kinds), `structure["bos"]`, `structure["last_swing_high"/"last_swing_
low"]`, `order_flow["delta"]`, `sessions["previous_period_high_low"]`,
`volume_profile` (the whole dict), `data_quality` (the whole dict),
`current_price` (recomputed independently by the adapter instead). This is
a substantial fraction of the Snapshot's total surface area.
`[SUPERSEDED]` `levels` (`poc`/`hvn`/`vah`/`val` kinds, via S003) and
`volume_profile["current_forming_profile"]["bucket_size"]` (also via S003)
are now read. `structure["bos"]`, `structure["last_swing_high"/"last_swing_low"]`,
`order_flow["delta"]`, `sessions["previous_period_high_low"]`, and
`current_price`'s adapter-recomputation remain accurate as of this update.

**Trackers producing information nobody consumes:** Fair Value Gaps, Order
Blocks (beyond feeding Breaker Blocks), Breaker Blocks, and Volume Profile
in full. Correlation Engine produces nothing at all in the running system
(never invoked).

**Setup conditions that overlap completely:** none *within* the single
existing setup — the three required conditions and three additional-evidence
checks each read a distinct field. The overlap found in this project was
empirical, not structural: the Round 2 controlled experiment showed that,
once `has_additional_confirmation` is required, a separately-tested
"disable round-number-only pools" filter excluded zero additional trades
(every trade passing confirmation already had ≥2 sources) — this is a
measured behavioral overlap between a permanent rule and a research
variable, not two setup conditions checking the same field.

---

## PART 9 — Research Opportunities

Ranked using only the three stated criteria — richness of information,
independence from evidence the current setup already consumes, and expected
contribution to future controlled experiments. Not ranked by which would be
most profitable, which is not knowable from architecture alone.

**1. Order Blocks.** Richest currently-unused Zone module — exposes
`impulse_strength`, dual mitigation tracking (wick zone + tighter body
zone), and touch history the setup's existing Liquidity Pool check does not
provide at all. Highly independent from CVD/Liquidity-Pool evidence, since
it is a *price-structure* zone concept, not an order-flow or liquidity-pool
one — a genuinely different family of confirmation. High value for future
controlled experiments: "does an Order Block near the swept pool improve
outcomes" is a clean, single-variable, well-defined next experiment using
the exact same methodology as Round 1/2.

**2. Volume Profile.** Second-richest — `poc_shift_from_previous_period`
and `value_area_overlap_ratio` are continuous, already-computed acceptance/
rejection signals with no analog anywhere in the current setup. Fully
independent evidence family (a volume-at-price concept, unrelated to
liquidity-pool sweeps or CVD). Slightly harder to experiment with cleanly
than Order Blocks because it is a whole-profile concept rather than a
per-zone one — a controlled experiment would need to define a specific
comparison rule (e.g. "value_area_overlap_ratio above/below some measured
threshold") rather than a simple presence/absence check.

**3. Fair Value Gaps.** Same schema-level ease of integration as Order
Blocks, but conceptually closer to what Liquidity Pools/structure already
capture (an imbalance is itself a byproduct of the same impulsive moves BOS/
CHOCH already react to) — lower independence from evidence the setup
already has, even though the specific field (`fill_status`/`fill_pct`) is
new.

**4. Correlation Engine / SMT.** Potentially the *most* independent
evidence of all (a second symbol entirely), but currently the most
expensive to actually test, because independence here is unproven, not
just unmeasured — the Coordinator change required (a second symbol's
candles, a new tracker instantiation) is real integration work, not a
same-day controlled experiment the way filtering an existing field is.
Ranked below Order Blocks/Volume Profile because "expected contribution to
a *near-term* controlled experiment" is lower given the setup cost, even
though the ceiling on information richness may be higher.

**5. Breaker Blocks.** Least independent of the group — mechanically almost
identical to Order Blocks (shares `zone_lifecycle.py`), so an experiment
using it would likely correlate heavily with an Order Block experiment
rather than add a distinct dimension, similar to how the round-number
filter and the confirmation requirement turned out to overlap in Round 2.

**6. Equal Highs/Lows, Session Boundaries, Delta (as direct snapshot
reads).** Lowest incremental research value of the unused/partial group —
each already contributes to the decision indirectly through Liquidity Pools
or CVD. Reading their own direct snapshot fields on top of that would very
likely re-measure information the setup already has, the same overlap
pattern already demonstrated empirically in Round 2 for a different pair of
conditions.

---

## PART 10 — Final Scorecard

| Module | Implemented | In Snapshot | Used by Setup | Affects Decision | Affects Trade | Research Priority | Comments |
|---|---|---|---|---|---|---|---|
| Liquidity Pools | ✓ | ✓ | ✓ | ✓ | ✓ | — (already active) | Core of the only setup; also the only module read by the trade-construction step. |
| CVD | ✓ | ✓ | ✓ | ✓ | ✗ | — (already active) | Second required condition; never used for stop/target. |
| Market Structure | ✓ | ✓ | Partial (choch only) | Partial | ✗ | Low | `bos`/regime/swing levels computed and unused; regime read only for reporting metadata. |
| Equal Highs/Lows | ✓ | ✓ (unread directly) | ✗ (directly) | Indirect | ✗ | Low (6th) | Value already captured via Liquidity Pools. |
| Session Boundaries | ✓ | ✓ (unread directly) | ✗ (directly) | Indirect | ✗ | Low (6th) | Anchors 3 other trackers; own fields never read. |
| Delta | ✓ | ✓ (unread) | ✗ (directly) | Indirect (via CVD) | ✗ | Low (6th) | Per-bar fields computed, sit unused alongside CVD's cumulative view. |
| Order Blocks | ✓ | ✓ | ✗ | ✗ | ✗ | **High (1st)** | Richest unused Zone module; independent evidence family; easy to add to a controlled experiment. |
| Volume Profile | ✓ | ✓ | ✗ | ✗ | ✗ | **High (2nd)** | Richest continuous acceptance/rejection signal available; fully independent family. |
| Fair Value Gaps | ✓ | ✓ | ✗ | ✗ | ✗ | Medium (3rd) | Easy to add, but lower independence from existing evidence. |
| Breaker Blocks | ✓ | ✓ | ✗ | ✗ | ✗ | Low (5th) | Mechanically close to Order Blocks; likely correlated, not additive. |
| Correlation Engine / SMT | ✓ (tracker exists, tested) | ✗ (never populated) | Code path exists, always False | ✗ | ✗ | Medium (4th) | Most independent possible evidence in principle; genuinely not wired, requiring real Coordinator work, not just a setup change. |

**Summary in one line**: of eleven implemented Market Intelligence modules,
two directly gate every trade this system takes, four contribute only
through indirect paths that mostly duplicate what the two active modules
already see, four are fully computed and fully unread, and one — Correlation
Engine/SMT — has a real, tested consumption path in the setup that has
never once received real data because nothing in the running system feeds
it.
