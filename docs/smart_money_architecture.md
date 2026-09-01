# Smart Money Module Architecture — Design Specification

Status: **design only, nothing implemented**. This document defines the complete
architecture for 13 Smart Money / Order-Flow / Intermarket modules before any
Phase 1 code is written, per the Phase 0 mandate that every future module
follow one shared design philosophy and integrate into the existing framework
(`data/market_data_provider.py`, `BacktestRunner`, `StrategyEngine`) without
requiring architectural changes.

No implementations, PineScript, or third-party code were referenced. Every
module below is derived from first-principles market microstructure/SMC
theory, redesigned around this project's own primitives.

---

## Cross-Cutting Design Principles (apply to every module below)

These recur so often that they are stated once here instead of 13 times:

1. **Raw features, never decisions.** Every module returns measurements
   (direction, size, age, distance, status) — never a score, a LONG/SHORT
   verdict, or a bucketed signal. Scoring/decision logic lives exclusively in
   the consumer (today's `decision_engine.py`, tomorrow's AI Ranking Engine).
2. **Forming vs. closed.** Any module with a notion of "not finished yet"
   (Volume Profile's current session, Footprint's current candle) must expose
   `closed_*` (safe for signal generation) and `forming_*`/`current_*`
   (provisional, explicitly labeled) separately — the exact pattern already
   proven by `TimeframeManager.get_history()` vs `get_forming_candle()`.
3. **ATR-relative, never fixed-price, tolerances.** Any clustering/threshold
   parameter (equal-highs tolerance, round-number spacing, profile bucket
   size) must be relative to volatility or symbol-configured — a fixed
   dollar value is a Multi-Symbol-by-Design violation on day one.
4. **Provenance over hidden scoring.** Where a module aggregates multiple
   weaker signals (Liquidity Pools, Correlation-informed SMT), it exposes
   *which* sub-signals contributed and their raw counts/timestamps — it does
   not collapse them into an opaque confidence number.
5. **Primary vs. derived modules.** Some modules scan raw OHLCV (Order
   Blocks, FVG, Market Structure). Others are pure functions of another
   module's state transitions (Breaker Blocks watches Order Blocks;
   Mitigation Blocks is arguably not even a separate module — see below).
   Derived modules never re-scan candles a primary module already scanned.
6. **Context symbols via existing Providers — nothing new required.**
   Every intermarket module (SMT, Relative Strength, Correlation) consumes a
   second symbol exactly the way `test_context_symbol_attached_as_read_only_provider`
   already proved works today: another top-level key in `market_snapshot`,
   fed by a `ProviderSpec`, never touching `ReplayEngine`/`BacktestRunner`.
7. **Same core, live or replay.** Every module is designed as a pure
   function of "closed bars/events up to now." None of them may depend on
   `ReplayEngine`-specific mechanics — the only thing that changes between
   backtest and live is who populates the `records` list a Provider wraps.

---

## MARKET STRUCTURE

### 1. Order Blocks

**1. Purpose** — Locate the last opposing-direction candle before an
impulsive move that broke structure: the zone where positioning against the
eventual move was last transacted. Price statistically revisits this zone
before continuing, giving a better-defined, better-risk re-entry than
chasing the breakout candle. This is the same market logic already behind
`strategy/order_block.py` — this design formalizes its **output contract**,
not its detection logic.

**2. Trading Logic** — After a confirmed break of structure (BOS) in
direction D, scan backward through the leg that produced the break for the
most recent candle whose close direction opposes D. That candle's range
defines the zone. The zone is progressively "mitigated" as price re-enters
it; full mitigation is a close beyond the zone in the opposing direction.

**3. Inputs** — OHLCV (any single timeframe — the module is timeframe-
agnostic and can run independently per timeframe), swing highs/lows and BOS
confirmation from the Market Structure primitives already built.

**4. Outputs (raw, no decision):**
- `direction`: bullish | bearish
- `zone_high`, `zone_low`
- `origin_timestamp`, `confirmed_timestamp` (see Replay Safety — these differ)
- `age_in_bars`
- `formation_volume` (of the origin candle)
- `impulse_strength` (ATR-normalized displacement of the move away from the zone)
- `distance_from_price` (absolute and ATR-relative)
- `touch_count`
- `mitigation_status`: unmitigated | partially_mitigated | fully_mitigated
- `mitigation_pct`
- `timeframe`
- `volume_percentile` (formation volume vs. recent N candles — a raw,
  explainable number in [0,1], not a hand-tuned "confidence score")

**5. Dependencies** — Depends on Market Structure (swings, BOS). Consumed
by: Liquidity Pools (zone/pool confluence), Breaker Blocks (hard dependency
— see below), FVG confluence checks, Strategy Engine, AI Ranking.

**6. Replay Safety** — Two timestamps matter and must not be conflated: the
origin candle's own `origin_timestamp` (in the past) and
`confirmed_timestamp` — the bar where the BOS that *validates* this as an
Order Block actually closed. The zone must never be exposed to a strategy
before `confirmed_timestamp`, even though its price levels technically
"existed" earlier — you could not have known it was an Order Block until
the break happened.

**7. Live Trading** — Pure function of closed candles up to now; each newly
closed candle re-evaluates for a new BOS (and thus a new OB) and re-checks
mitigation status of existing zones. No live-specific logic needed.

**8. AI Compatibility** — Expose all fields above per tracked OB. Also
expose aggregate context: count of currently-unmitigated bullish/bearish OBs,
and the feature vector of the *nearest* unmitigated OB in each direction
(since there can be several simultaneously).

**9. Computational Complexity** — O(lookback) per candle for detection
(reusing the existing `STRUCTURE_LOOKBACK` bound). Tracking active zones is
O(k) where k = tracked OBs, bounded by age/count pruning. Caching: only
re-check mitigation for zones whose price range the *current* candle
actually intersects — skip the rest without recomputation.

**10. Edge Cases** — Multiple candidate origin candles in one leg → always
the one closest to the break, not the first. Very large origin-candle range
(rarely fully invalidated) → expose `zone_range_atr_ratio`, do not cap
internally. Nested/overlapping OBs from repeated same-direction impulses →
expose as separate objects. Never-touched OBs accumulating forever → prune
from the *tracked* set by age, but the field `age_in_bars` itself is never
hidden or capped.

**11. Future Extensions** — Multi-timeframe OB confluence (computed
downstream by comparing two independent OB module instances, not inside this
module). ML-learned historical fill-rate as a training label, not a runtime
field.

---

### 2. Fair Value Gaps (FVG)

**1. Purpose** — A 3-candle imbalance (candle 1's wick and candle 3's wick
don't overlap) marks a level where two-sided trading didn't fully occur.
These zones act as magnets — price often "fills" them before continuing, a
statistical tendency independent of any SMC branding.

**2. Trading Logic** — For consecutive candles A, B, C: bullish FVG if
`A.high < C.low` (zone = [A.high, C.low]); bearish if `A.low > C.high` (zone
= [C.high, A.low]). The zone shrinks as price trades back into it
(partial/full fill).

**3. Inputs** — OHLCV only, any timeframe. Fully independent primitive —
no dependency on any other module.

**4. Outputs:**
- `direction`: bullish | bearish
- `zone_high`, `zone_low`
- `origin_timestamp`, `age_in_bars`
- `gap_size`, `gap_size_atr_ratio`
- `fill_status`: unfilled | partially_filled | fully_filled
- `fill_pct`
- `timeframe`, `formation_volume` (of the middle candle)

**5. Dependencies** — Independent. Consumed by: Order Block confluence,
future Breaker/Balanced-Price-Range extensions, Strategy Engine, AI Ranking.

**6. Replay Safety** — Confirmable the instant candle C closes — the same
3-bar-window shape as the swing-pivot fractal already in
`market_structure.py`. Becomes valid at C's close, using only closed data.

**7. Live Trading** — Naturally incremental: check only the last 3 candles
whenever a new one closes.

**8. AI Compatibility** — All fields above per FVG, plus context features
("count of unfilled bullish FVGs above price", "nearest unfilled FVG
distance").

**9. Computational Complexity** — O(1) per new candle — the cheapest
detection in this entire document. Tracking open FVGs for fill updates is
O(k), same proximity-filter caching as Order Blocks.

**10. Edge Cases** — Overlapping/nested FVGs from consecutive impulsive
candles → keep as separate objects. A FVG filled on the very next candle →
still a valid, short-lived data point, not noise to discard. Very
low-volume origin candle → expose raw `formation_volume`, do not filter
internally.

**11. Future Extensions** — Inverse FVG is a direct v2: once `fill_status`
transitions to `fully_filled`, the same zone can be re-exposed with flipped
polarity (support becomes resistance) — architecturally identical pattern
to Breaker Blocks watching Order Blocks. Balanced Price Range (BPR) is
another direct v2: two opposite-direction FVGs whose zones overlap.

---

### 3. Breaker Blocks

**1. Purpose** — An Order Block that gets fully invalidated often flips
polarity: participants who entered at the OB are now trapped, and their
capitulation/breakeven exits can drive the reversal further. The same zone
that was support-generating becomes resistance-generating (or vice versa).

**2. Trading Logic** — Purely a state-transition watcher on the Order Block
module: the instant an OB's `mitigation_status` becomes `fully_mitigated`,
re-expose the identical zone with **opposite** `direction`.

**3. Inputs** — Order Block module's output stream only. No independent
OHLCV scan — this is a **derived module**, not a primary detector.

**4. Outputs** — Same shape as Order Block outputs, plus:
- `source_ob_origin_timestamp` (links back to the parent OB)
- `breaker_confirmed_timestamp` (when the flip occurred)
- its own independent `mitigation_status`/`touch_count` from this point on

**5. Dependencies** — Hard dependency on Order Blocks (must run
after/alongside it). Consumed by Strategy Engine, AI Ranking.

**6. Replay Safety** — Valid exactly at the candle where the parent OB's
mitigation flips to full — inherited directly from Order Blocks' own
point-in-time guarantee. No new risk: this is a re-labeling event, not a
new pattern scan.

**7. Live Trading** — Subscribes to Order Block state-change events. This
implies Order Blocks should expose a clean "just became fully mitigated on
this candle" transition, not just a static status field, so Breaker Blocks
(and Mitigation logic) can react to the transition itself rather than
polling status every bar.

**8. AI Compatibility** — Same feature set as Order Blocks, tagged
`source: "breaker"` so a model can distinguish origin from a primary OB.

**9. Computational Complexity** — O(k) where k = tracked OBs — watches
transitions only, no extra scanning.

**10. Edge Cases** — A breaker gets swept back through in the *original*
direction — recommendation: invalidate/prune rather than flip back a second
time (avoids an oscillating state machine); a genuinely new pattern will be
independently picked up by the primary Order Block detector if one exists.

**11. Future Extensions** — Flip-count statistics per zone as a
backtest/analytics-only aggregate, not needed live.

---

### 4. Mitigation Blocks

**Design recommendation: not a standalone module.** In the retail SMC
literature this term is used inconsistently — sometimes as a synonym for
Breaker Blocks, sometimes as a tighter body-based sub-zone of an Order
Block. Building it as an independent detector would duplicate Order Block's
origin-candle identification — exactly the "duplicated responsibility"
failure mode flagged in the Phase 0 review.

**Recommended design:** two additional fields on the **Order Block**
output itself:
- `mitigation_zone_high`, `mitigation_zone_low` — the origin candle's body
  (`min(open,close)`–`max(open,close)`) rather than its full wick range —
  a tighter, higher-confidence re-entry sub-zone.
- `mitigation_zone_status` — the same unmitigated/partial/full vocabulary,
  evaluated independently against the tighter zone.

Everything else (dependencies, replay safety, live behavior, AI features,
complexity, edge cases) is inherited directly from Order Blocks — zero
additional risk, zero additional detection logic, one detection pass
serving two nested outputs. If real usage later proves Mitigation Blocks
need an independent lifecycle (e.g. surviving after the parent OB is
pruned), split it out then, driven by evidence rather than upfront
speculation.

---

### 5. Liquidity Pools

**1. Purpose** — Aggregate weaker individual signals (equal highs/lows,
session extremes, round numbers) into unified zones of likely resting
stop/breakout orders. Price is statistically drawn to sweep these zones
before reversing — triggering resting orders benefits participants
positioned to absorb the other side.

**2. Trading Logic** — A pool exists where multiple distinct highs (or
lows) cluster within an ATR-relative tolerance. More independent
contributing touches = a "heavier" pool. A sweep is a wick beyond the pool
that closes back inside/beyond in the opposite direction — reusing the
existing `calculate_sweep_strength` concept from `liquidity.py`, generalized
from a single swing point to a pool.

**Design note — this is explicitly a composite/aggregator module.** It is
built from three independent sub-detectors, not one monolithic scan:
- **Equal Highs/Equal Lows** (module 6, below) — the primary structural
  sub-detector.
- **Session extremes** — highest-high/lowest-low of a defined session
  (Asian/London/NY), reusing the Session Boundaries primitive deferred at
  the end of Phase 0.
- **Round numbers** — pure price arithmetic (no candle pattern), spacing
  configured per symbol (e.g. $500 increments for BTC, $0.01 for a
  low-priced altcoin) — a direct Multi-Symbol-by-Design requirement.

**3. Inputs** — Equal Highs/Equal Lows output, Session Boundaries, a
per-symbol round-number spacing configuration, an ATR-relative clustering
tolerance.

**4. Outputs:**
- `direction`: buy_side (liquidity above price) | sell_side (below price)
- `level`, `zone_high`, `zone_low`
- `contributing_touches` (raw list of timestamps — provenance, not a hidden count)
- `touch_count`
- `sources`: which sub-detectors flagged it, e.g. `["equal_highs", "session_high"]`
- `age_in_bars` (oldest and newest contributing touch)
- `swept_status`: unswept | swept
- `swept_timestamp`, `sweep_penetration`, `sweep_rejection`

**5. Dependencies** — Depends on Equal Highs/Equal Lows and Session
Boundaries. Consumed by: Order Block confluence checks, Strategy Engine, AI
Ranking.

**6. Replay Safety** — A pool is only knowable once ≥2 contributing touches
have occurred, each already point-in-time-safe individually. Sweep
detection uses only the current candle's already-known high/low/close.

**7. Live Trading** — Same incremental update per new touch/sweep; no
special-casing.

**8. AI Compatibility** — `touch_count`, `sources` (one-hot-able), `age`,
`swept_status`, `sweep_penetration`/`sweep_rejection`, distance from current
price.

**9. Computational Complexity** — The clustering step is the one part of
this whole document that needs a deliberate algorithm choice: naive
pairwise comparison of all swing points is O(n²) and will not scale to a
multi-year live system. Use sorted-price or ATR-sized-bucket hashing
instead (O(n log n) or O(n)). Flagged explicitly as the one non-trivial
complexity decision in the Market Structure category.

**10. Edge Cases** — Two clusters near but not within tolerance → expose
the raw distance so consumers can re-cluster with a different threshold
rather than the module silently hiding the boundary call. Round-number
granularity must be symbol-configured, never hardcoded.

**11. Future Extensions** — Volume-Profile-weighted pool significance once
Volume Profile (module 10) exists — a pool coinciding with an HVN is a
natural cross-module confluence, computed downstream, not inside this
module.

---

### 6. Equal Highs / Equal Lows (EQH/EQL)

**1. Purpose** — The most specific, most common form of visible liquidity
clustering: 2+ swing highs (or lows) at approximately the same price — an
obvious level many participants will place stops/breakout orders around.

**2. Trading Logic** — Reuse the swing pivots already produced by Market
Structure (no new pivot-detection logic). Compare each newly confirmed
pivot against recent prior pivots of the same type; flag as "equal" if
within an ATR-relative tolerance.

**3. Inputs** — OHLCV, swing pivots from Market Structure (direct reuse),
a configurable ATR-relative tolerance.

**4. Outputs:**
- `direction`: equal_highs | equal_lows
- `level` (representative price) and the individual matched pivot prices
- `pivot_timestamps` (provenance)
- `pivot_count`
- `max_deviation` (how far apart the "equal" pivots actually were)
- `age_in_bars`
- `swept_status` (same vocabulary as Liquidity Pools, which consumes this directly)

**5. Dependencies** — Depends on Market Structure's swing pivots. Consumed
by Liquidity Pools (as a sub-detector) and independently by Strategy Engine
/ AI Ranking (a legitimate standalone signal, not only a Liquidity Pools
input).

**6. Replay Safety** — Inherits Market Structure's existing guarantee: a
pivot is only real once its right-hand neighbor confirms it.

**7. Live Trading** — Same incremental check against the last N confirmed
pivots whenever a new one confirms.

**8. AI Compatibility** — All raw fields above.

**9. Computational Complexity** — O(recent pivots), bounded by the same
lookback pattern as `STRUCTURE_LOOKBACK`.

**10. Edge Cases** — 3+ equal highs, not just 2 → expose full
`pivot_count`, do not hardcode a "2 is enough" cutoff. Slightly
ascending/descending "equal" highs → this is exactly why the tolerance is
ATR-relative, not exact-match; `max_deviation` is exposed so strictness is
inspectable downstream.

**11. Future Extensions** — Trendline liquidity (diagonally trending equal
highs/lows) reuses the same tolerance-clustering logic against a fitted
trendline instead of a flat level.

---

## ORDER FLOW

### 7. Delta

**1. Purpose** — Aggressive buy vs. sell volume *within* a single bar — a
directional proxy that total volume alone cannot provide. Price can rise on
weak delta (thin, reversal-prone) or strong delta (genuine aggression, more
likely to continue); total volume can't distinguish these.

**2. Trading Logic** — `delta = taker_buy_volume - taker_sell_volume` for
the bar (equivalently `2*taker_buy_volume - total_volume`).

**Concrete, already-available data point:** Binance's kline response
(REST, historical, and live stream alike) already includes
`taker_buy_base_asset_volume`. **No tick-level infrastructure is required
for this module** — it only requires the existing kline loader/downloader
to stop discarding a field it already receives. This is the cheapest,
highest-value module in the entire document.

**3. Inputs** — OHLCV + `taker_buy_volume`, any timeframe (requires
extending `historical_loader.py`/`download_historical_klines.py` to
preserve a field they currently discard).

**4. Outputs:**
- `delta` (signed, raw)
- `delta_pct` (delta as % of bar's total volume — normalized, comparable across bars/assets)
- `cumulative_session_delta` (lightweight, single-session running sum — a precursor to full CVD)
- `delta_divergence_flag`: did price make a new high/low without delta confirming — exposed as a flag/measurement, not a verdict.

**5. Dependencies** — Independent primitive. Consumed by: CVD (module 8 —
direct running sum of this module's output), and as future enrichment for
`evaluate_bos_quality` (which already consumes `volume_ratio` — a natural
place to add `delta_pct` later, not changed now). Strategy Engine, AI
Ranking.

**6. Replay Safety** — Computable only once the bar closes, from fields
already present on that closed bar — no lookback, no state. Among the
safest possible module designs.

**7. Live Trading** — Identical computation on each newly closed live
kline; Binance's live kline stream carries the same
`taker_buy_base_asset_volume` field.

**8. AI Compatibility** — `delta`, `delta_pct`, `cumulative_session_delta`,
`delta_divergence_flag` — all continuous/near-continuous, directly usable.

**9. Computational Complexity** — O(1) per bar — a single arithmetic
operation on already-available fields.

**10. Edge Cases** — Missing `taker_buy_volume` on some historical sources
(not all third-party dumps include it) → must return `None`, never
silently default to zero (a fabricated "no aggression" signal is worse than
an honest gap). Near-zero-volume bars → `delta_pct` is noisy; expose raw
`total_volume` alongside so consumers can weight by liquidity themselves.

**11. Future Extensions** — True tick-level delta (via aggTrades aggressor
flags, if/when Trade-Level Infrastructure is built) would be more precise
than the kline-taker-volume approximation used today. **The output
contract defined here must stay identical regardless of which computation
method backs it**, so upgrading the data source later never breaks a
consumer — a direct application of the Exchange-Agnostic principle to data
*precision*, not just data *origin*.

---

### 8. CVD (Cumulative Volume Delta)

**1. Purpose** — The running sum of Delta over time, revealing sustained
order-flow bias and price/flow divergences a single bar's Delta cannot show.

**2. Trading Logic** — `CVD[t] = CVD[t-1] + Delta[t]`, accumulated from a
configurable anchor (session, day, or continuous/unanchored). Divergence
between price direction and CVD direction over a comparison window is the
classic order-flow reversal tell.

**3. Inputs** — Delta module's per-bar output, a configured anchor policy.

**4. Outputs:**
- `cvd` (running value under the chosen anchor)
- `cvd_change_over_window(N)` (bounded, comparable — unlike raw cumulative CVD)
- `cvd_slope` (simple rate-of-change over a configurable window — continuous, ML-friendly)
- `price_cvd_divergence_flag`: bullish_divergence | bearish_divergence | none
- `anchor_type`, `anchor_timestamp`

**5. Dependencies** — Hard dependency on Delta. Complements (does not
modify) Market Structure's BOS/CHOCH — a BOS with supporting CVD trend is a
different, stronger context than one without; that comparison happens
downstream, not inside this module.

**6. Replay Safety** — A running sum of an already-safe input; safe as long
as the anchor/reset boundary itself only ever refers to already-passed
boundaries (e.g. session start), never a lookahead-defined one.

**7. Live Trading** — Same incremental accumulation; requires the
anchor/reset state to persist across calls — the same per-run stateful
pattern `TimeframeManager` already uses, nothing architecturally new.

**8. AI Compatibility** — `cvd`, `cvd_change_over_window`, `cvd_slope`,
`price_cvd_divergence_flag`.

**9. Computational Complexity** — O(1) amortized per bar (running sum plus
a small bounded window for slope/windowed-change).

**10. Edge Cases** — Long-running live systems without a reset accumulate
very large numbers with diminishing marginal information per bar — this is
exactly why the bounded `cvd_change_over_window` is exposed alongside the
unbounded raw `cvd`, not instead of it. Windows straddling a reset boundary
must expose `bars_since_anchor < window` so consumers know a windowed stat
is not yet fully populated, rather than silently returning a
partially-computed number.

**11. Future Extensions** — Multi-timeframe CVD: this module's own output
is itself bar-shaped and could be wrapped as a native `BarSeriesProvider`
input for a higher timeframe — a clean example of a derived module's
output becoming another module's native input, validating the Provider
design's composability.

---

### 9. Footprint

**1. Purpose** — Volume traded at each discrete price level *within* a
single candle, revealing microstructure (absorption, exhaustion) that
Delta's single aggregate number per bar cannot show.

**2. Trading Logic** — Requires trade-level (or order-book) data, binned
into a price×volume grid per candle. Absorption = high volume with little
price progress at a level. Exhaustion = declining volume at new price
extremes.

**3. Inputs** — Trade-level data (`aggTrades` or raw prints). **This is
the module that most concretely requires the Trade-Level/Order-Book Data
Infrastructure flagged — and deliberately not built — in Phase 0. This
module cannot exist at all until that infrastructure decision is made.**

**4. Outputs:**
- `price_levels`: list of `{price, buy_volume, sell_volume, total_volume, delta}`
- `poc_price` (this candle's own point of control — distinct from Volume
  Profile's session-level POC)
- `absorption_ratio` (volume-to-price-range at an extreme, a continuous
  number — not a boolean judgment)
- `imbalance_levels` (raw per-level buy:sell ratios at adjacent diagonal
  levels — exposed as ratios, not flagged as "signals")

**5. Dependencies** — Hard dependency on Trade-Level Infrastructure (not
yet built). No dependency on other SMC modules. Future confluence
(unbuilt): does an Order Block candle show footprint absorption — a far
stronger confirmation than OHLCV alone.

**6. Replay Safety** — Requires the *complete* trade-level data for a
candle before computing anything for it. This needs its own dedicated
point-in-time design, not a reuse of `PointEventProvider` — tick volumes
and query patterns (millions of rows vs. hundreds) are a fundamentally
different scale problem.

**7. Live Trading** — A genuinely different shape of live/backtest parity
than every other module here: backtest reads a candle's full trade set
upfront; live must build the grid incrementally as trades stream in via
WebSocket, finalizing at candle close. The **output contract** must be
identical either way even though the internal computation timing differs —
this asymmetry should be designed for explicitly, not discovered mid-build.

**8. AI Compatibility** — POC (relative to candle range), absorption
ratio, per-level imbalance ratios — potentially as a fixed-size
histogram/vector, a richer feature *type* than any scalar-output module in
this document.

**9. Computational Complexity** — **The highest in this entire document.**
Millions of trades/day for a liquid instrument; a multi-year backtest
cannot replay raw ticks at strategy-evaluation time. Recommended design:
**pre-compute the footprint grid offline once**, store keyed by
`(symbol, timeframe, candle_timestamp)`, and have the runtime module simply
look up rather than recompute. This should be treated as an architecturally
distinct "batch-precomputed artifact + thin provider," not an inline
per-replay-step computation like every other module here.

**10. Edge Cases** — Missing/incomplete tick data for older periods (API
gaps) → expose `data_completeness`, never silently produce a partial grid
that looks complete. Extreme-volume news candles → non-uniform per-candle
cost; grid resolution may need adaptive capping.

**11. Future Extensions** — Multi-exchange footprint aggregation, once
Multi-Exchange infrastructure (Phase 0 principle 2) covers more than one
venue simultaneously.

---

### 10. Volume Profile (including HVN/LVN)

**1. Purpose** — Distribution of total traded volume across price levels
over a session/period (not per-candle like Footprint). Reveals where the
market spent the most "time and volume" (fair value) vs. where it passed
through quickly (likely to be revisited fast).

**2. Trading Logic** — Aggregate volume-at-price across all candles in a
period into a histogram. **POC** = price with the single highest volume.
**Value Area** = the price range containing a configured % (typically 70%)
of total volume, centered on POC. **HVN/LVN** — local peaks/troughs in the
histogram — are folded into this module's output rather than built as a
separate detector, since they are a direct post-processing pass over a
histogram this module already owns (reusing the same fractal
peak/trough-finding *pattern* already used for swing highs/lows, just
applied to a volume-by-price series instead of a price-by-time series).

**3. Inputs** — OHLCV + volume at minimum (coarse approximation: bucket
each candle's total volume across the price bins its range touches). Tick
data (optional) gives a materially more precise version using exact
per-trade price attribution. **Both modes share the same output contract**
— precision is a `data_quality` field, not a different shape.

**4. Outputs:**
- `poc_price`, `value_area_high`, `value_area_low`
- `histogram`: full raw `{price_bucket, volume}` distribution — exposed in
  full, not just derived summary stats, for downstream/AI use
- `period_type`, `period_start`, `period_end`
- `data_quality`: approximate (OHLCV-bucketed) | precise (tick-based)
- `hvn_nodes` / `lvn_nodes`: each with `price`, `relative_volume` (multiple
  of the profile's average bucket volume), `width` (adjacent-bucket span)
- `closed_profiles` (finalized, safe for signal generation) and
  `current_forming_profile` (in-progress, explicitly labeled) — the same
  forming/closed split already established by `TimeframeManager`.

**5. Dependencies** — Independent primitive (OHLCV+volume minimum; tick
data optional). Consumed by: Liquidity Pools (HVN confluence), Strategy
Engine, AI Ranking.

**6. Replay Safety** — A period's profile is only final once the period
itself has closed; the forming profile is exposed separately and must never
be mistaken for a closed one by a consumer.

**7. Live Trading** — The current session's profile (and its HVN/LVN)
updates incrementally as each new candle closes within it, finalizing when
the session boundary passes.

**8. AI Compatibility** — `poc_price` (relative to current price),
`value_area_high/low`, the full `histogram` as a fixed-length binned
vector — letting a model learn its own derived shape features rather than
only consuming hand-picked summary stats.

**9. Computational Complexity** — O(candles × buckets touched) for the
coarse mode — manageable. Tick-based precise mode shares Footprint's cost
profile. **Caching:** closed historical periods never change — compute
once, persist, never recompute across repeated backtest experiments on the
same data, a high-value opportunity given how often the same range gets
re-tested.

**10. Edge Cases** — Bucket size must be ATR-relative or per-symbol
configured, identical requirement to Liquidity Pools' round-number spacing.
Very low-volume periods (illiquid altcoin sessions) produce unreliable
profiles → expose raw `total_period_volume` for consumers to judge
reliability rather than the module implying equal confidence always.

**11. Future Extensions** — Composite/multi-session profiles (e.g. "last
20 sessions overlaid") are a direct aggregation of the same per-period
histograms — no new primitive required.

---

## INTERMARKET

### 11. SMT Divergence

**1. Purpose** — Compare *structure* (not just price) between correlated
instruments. A primary symbol making a new high while a correlated
reference symbol does not suggests the move lacks broad conviction and is
more likely to reverse — correlated assets "should" confirm each other's
structural moves.

**2. Trading Logic** — Run the existing Market Structure detection
independently on a primary and a reference symbol. When the primary breaks
structure, check within a comparison window whether the reference confirms
(broke the same direction) or diverges (did not break, or broke oppositely).

**3. Inputs** — Market Structure output for the primary symbol (already
available) and for a reference symbol via
`market_snapshot[reference_symbol]` — **exactly the pattern already proven
in Phase 0's `test_context_symbol_attached_as_read_only_provider`.** This
is the first module that concretely *requires* that capability, validating
it was built ahead of need.

**4. Outputs:**
- `primary_symbol`, `reference_symbol`
- `divergence_type`: bullish_divergence | bearish_divergence | confirmed | none
- `primary_structure_event`, `reference_structure_event`
- `comparison_window`
- `correlation_context` (optional, from the Correlation Engine — context, not a gate)

**5. Dependencies** — Depends on Market Structure (run per symbol) and
optionally Correlation Engine for context. **`reference_symbol` need not be
a real exchange-tradeable instrument** — it can be a computed/composite
series (e.g. a TOTAL3-style index built upstream from several symbols) as
long as it is exposed through the same `market_snapshot[symbol]["1m"]`
shape. SMT itself is agnostic to whether the reference is "real" or
synthetic — directly resolving the "BTC vs TOTAL3 isn't a Binance symbol"
concern raised during the roadmap review.

**6. Replay Safety** — Both symbols' structure events use only their own
already-closed candles. The comparison itself adds no new risk *provided*
it only compares events already confirmed as of the current synchronized
`ReplayContext` clock on both symbols — never compare a confirmed primary
event against a reference event that hasn't confirmed yet.

**7. Live Trading** — Requires both symbols' live feeds running
concurrently — a real, non-trivial operational requirement (two
subscriptions instead of one), not a detail to hand-wave.

**8. AI Compatibility** — `divergence_type` (categorical), correlation
context (continuous), timing gap between the two symbols' events
(continuous).

**9. Computational Complexity** — O(Market Structure cost × N reference
symbols) — linear, no new algorithmic complexity, reuses an already-bounded
primitive per symbol.

**10. Edge Cases** — Thin/gappy reference-symbol data (newly listed asset)
→ expose `reference_data_quality`/`reference_candle_count`. Multiple
configured reference symbols (BTC vs ETH *and* BTC vs SOL) → output is a
list of per-pair results, never a single hardcoded pair — a direct
requirement from "any pair, not just BTC vs ETH."

**11. Future Extensions** — Multi-way SMT (3+ assets checked for mutual
agreement) is the same pairwise primitive run across more combinations and
aggregated — no new primitive needed.

---

### 12. Relative Strength

**1. Purpose** — How one asset performs *relative to* another (or a
basket), independent of absolute direction — reveals rotation that neither
asset's own chart shows in isolation.

**2. Trading Logic** — Compute the ratio of two price series (e.g.
ETH/BTC) as its own synthetic series, then apply the **same** Market
Structure analysis already built to that ratio series. A rising ratio means
the numerator is outperforming.

**3. Inputs** — Two (or more) symbols' OHLCV via the same context-provider
pattern as SMT.

**4. Outputs:**
- `current_ratio`, a bounded recent ratio window (never an unbounded series)
- `ratio_change_pct(window)` — the primary actionable output
- `ratio_trend`: BULLISH | BEARISH | RANGE — computed by feeding a
  synthetic ratio-candle series through the *existing* Market Structure
  module, not a new trend algorithm
- `numerator_symbol`, `denominator_symbol`

**5. Dependencies** — Requires 2+ symbols (Multi-Symbol infra). **Reuses**
Market Structure internally rather than reimplementing trend detection — a
direct application of "avoid duplicated responsibility."

**6. Replay Safety** — The ratio at time T uses both symbols' already
point-in-time-safe prices at the same instant; the ratio computation itself
introduces no new risk.

**7. Live Trading** — Same computation, incrementally, requiring both
symbols' live feeds (same operational note as SMT).

**8. AI Compatibility** — `current_ratio`, `ratio_change_pct` at multiple
windows, `ratio_trend` (categorical).

**9. Computational Complexity** — O(1) per bar for the ratio; inherits
Market Structure's existing bounded cost for the trend classification on
the synthetic series.

**10. Edge Cases** — Denominator near zero or a stablecoin depeg → expose
raw `denominator_price` alongside the ratio so a division artifact never
masquerades as a genuine signal. Mismatched history length between symbols
→ the ratio series is bounded by the shorter one; expose `ratio_series_start`.

**11. Future Extensions** — Basket-relative-strength: construct a composite
denominator series first (the same "synthetic series as input" trick SMT
uses for TOTAL3), then apply this same pairwise ratio logic unchanged.

---

### 13. Correlation Engine

**1. Purpose** — Quantify co-movement between symbols over a rolling
window. Provides the context that makes SMT and Relative Strength readings
meaningful — a "divergence" between uncorrelated assets is noise; between
highly correlated ones it's a genuine signal.

**2. Trading Logic** — Rolling Pearson correlation (or beta) of returns
over a configurable window. A *change* in correlation (breaking down from
high to low) is itself informative, distinct from the correlation level.

**3. Inputs** — Two (or more) symbols' OHLCV (via close-derived returns), a
configurable window.

**4. Outputs:**
- `correlation_coefficient`, `correlation_window`
- `correlation_trend`: rising | falling | stable
- `symbol_a`, `symbol_b`
- `sample_size` (bars actually used — critical transparency for short-history assets)

**5. Dependencies** — Independent primitive. Consumed by: SMT and Relative
Strength (as optional context), and — critically — **Risk Engine (Phase
6)**, where correlation-adjusted portfolio exposure is a hard requirement,
not a Smart-Money nicety.

**6. Replay Safety** — Rolling statistic over already-closed bars on both
symbols — standard rolling-window safety, the same pattern already used by
`_calculate_volume_ratio`, generalized to two series.

**7. Live Trading** — Same rolling computation, incrementally updated per
new closed bar on either symbol.

**8. AI Compatibility** — `correlation_coefficient`, `correlation_trend` —
directly useful, and valuable as a *normalizing context feature* for other
modules' outputs (a model can learn to discount SMT signals when
correlation is low, something hand-coded gating struggles to do well).

**9. Computational Complexity** — O(window) per bar naively; O(1) amortized
with an incremental rolling-correlation algorithm (add the newest bar's
contribution, subtract the oldest) — flagged explicitly as a caching/
algorithm-choice opportunity, the same "avoid O(n·window) when O(n) is
available" lesson already applied elsewhere in this framework.

**10. Edge Cases** — Very short overlapping history (a newly listed asset)
→ `sample_size` must be exposed; low-sample correlations should be treated
with appropriate skepticism by consumers, not hidden by the module.
Spurious short-window correlation → the window length is always reported
alongside the coefficient, never implicit.

**11. Future Extensions** — A full multi-asset correlation *matrix* for
portfolio-level risk (Phase 6) is this same pairwise primitive called
across all relevant pairs — no new primitive required.

---

## Summary Table

| Module | Category | Primary/Derived | Hard Data Dependency | Complexity |
|---|---|---|---|---|
| Order Blocks | Structure | Primary | OHLCV | Low (bounded lookback) |
| Fair Value Gaps | Structure | Primary | OHLCV | O(1) — cheapest detector |
| Breaker Blocks | Structure | Derived (Order Blocks) | none | Low |
| Mitigation Blocks | Structure | **Fields on Order Blocks**, not a module | none | none (free) |
| Liquidity Pools | Structure | Derived (EQH/EQL + Session + Round #) | Session Boundaries | Medium (clustering algorithm choice matters) |
| Equal Highs/Lows | Structure | Primary (reuses swing pivots) | OHLCV | Low |
| Delta | Order Flow | Primary | `taker_buy_volume` (already in Binance klines) | O(1) — cheapest module overall |
| CVD | Order Flow | Derived (Delta) | none beyond Delta | O(1) amortized |
| Footprint | Order Flow | Primary | **Trade-level data (not yet built)** | **Highest in document** |
| Volume Profile (+HVN/LVN) | Order Flow | Primary | OHLCV (tick optional) | Medium, cacheable |
| SMT Divergence | Intermarket | Derived (Market Structure ×2) | Multi-symbol context | Linear in symbols |
| Relative Strength | Intermarket | Derived (Market Structure reused) | Multi-symbol context | O(1) + reused cost |
| Correlation Engine | Intermarket | Primary | Multi-symbol context | O(1) amortized (incremental) |

**Recommended build order within Phase 1**, purely by dependency and cost:
Fair Value Gaps and Delta first (cheapest, zero new infrastructure, Delta
only needs a loader fix) → Equal Highs/Lows → Order Blocks output
reshaping (raw features + Mitigation fields) → Breaker Blocks → Liquidity
Pools (needs Session Boundaries decision first) → CVD → Correlation Engine
→ SMT / Relative Strength (need the Multi-Symbol context pattern exercised
for real, not just tested) → Volume Profile → Footprint last (blocked on
the Trade-Level Infrastructure decision, the single biggest open
architecture question in this whole document).
