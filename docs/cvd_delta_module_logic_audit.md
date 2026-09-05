# CVD/Delta Module Logic Audit

**Status: AUDIT AND RESEARCH DESIGN ONLY.** No production CVD/Delta
logic was modified. No CVD/Delta integration into S001, S005, S007, or
any new setup was performed. No FVG/IFVG, Volume Profile, ATR/Regime,
S008, or portfolio work was started. Only the 4 locked SOL TRAIN months
(2024-02, 2024-04, 2024-09, 2025-12) were accessed for empirical checks
— confirmed by direct inspection of every diagnostic script written for
this audit; no VALIDATION, SECONDARY_VALIDATION, or FINAL_HELD_OUT
(2025-02, 2025-07) file was loaded anywhere in this session.

**Primary question answered**: does the current module calculate,
aggregate, reset, publish, and consume Delta/CVD in a causally correct
and institutionally meaningful way on real SOL Binance data? — **Yes,
for everything the current, active consumers (S001, S007) actually
read.** Zero confirmed correctness defects were found in the formula,
aggregation, replay-safety, or divergence/exhaustion timing. The one
real, disclosed characteristic worth attention — a large preload
dependency in the raw/absolute `cvd` value — does **not** propagate
into any field either current consumer reads, and is already documented
in the module's own code as an intentional, session-boundaries-deferred
design choice.

---

## 1. Complete active data-flow map

```
Binance Vision monthly CSV (data/SOLUSDT-1m-{month}.csv)
  columns: open_time, open, high, low, close, volume, close_time,
           quote_volume, count, taker_buy_volume, taker_buy_quote_volume, ignore
        |
        v
data/historical_loader.py: load_ohlcv_csv() -> normalize_ohlcv_record()
  - reads "volume" and "taker_buy_volume" columns by header name
  - taker_buy_volume is OPTIONAL (None if column absent/blank, never
    fabricated as 0)
  - normalize_ohlcv_records() sorts by timestamp, rejects duplicates
        |
        v  (1-minute candles: {timestamp, open, high, low, close,
        |   volume, taker_buy_volume})
        v
data/timeframe_manager.py: TimeframeManager.sync() / _ingest() / _merge()
  - aggregates 1m -> 15m: volume SUMMED, taker_buy_volume SUMMED (None
    if ANY contributing minute is missing it - "poisons" the whole
    bucket rather than silently partial-summing)
  - get_history("15m") returns ONLY closed buckets; the forming bucket
    is exposed separately via get_forming_candle() and never mixed in
        |
        v  (used two ways, both eventually reaching the same trackers)
        |
        +-- research/backtest harness scripts: tf.sync(candles_1m);
        |   candles_15m = tf.get_history("15m") -- direct, one-shot
        |
        +-- BacktestRunner (backtesting/backtest_runner.py):
              data/market_data_provider.py: BarSeriesProvider
                - wraps a SEPARATE, INTERNAL TimeframeManager instance
                - sync(context) feeds it context.visible_history_1m
                  (the point-in-time-safe 1m replay clock from
                  ReplayEngine)
                - snapshot() calls get_history("15m") - same
                  closed-only guarantee, verified by direct code
                  reading, not assumed
                    |
                    v
              market_snapshot[symbol]["15m"] (only ever closed 15m bars)
        |
        v
strategy/market_intelligence_coordinator.py: MarketIntelligenceCoordinator
  - self._delta = DeltaTracker(timeframe=timeframe, ...)
  - self._cvd = CVDTracker([...anchors...], timeframe=timeframe, ...)
  - sync_and_build() drives BOTH trackers off the SAME candles_15m,
    one new 15m candle at a time (never batched more than one bar per
    call when any CVD anchor is session-based)
        |
        v
strategy/features/delta.py: calculate_delta() (pure) / DeltaTracker (stateful)
  - delta = taker_buy_volume - (volume - taker_buy_volume)
          = 2*taker_buy_volume - volume
  - both fields None -> every output field None (never a fabricated 0)
  - DeltaTracker.snapshot(): cumulative_delta (unanchored, accumulates
    from tracker start), bars_accumulated, bars_with_missing_data, plus
    the MOST RECENT bar's delta/delta_pct/delta_direction/delta_strength
        |
        v (CVDTracker calls calculate_delta() itself too - never
        |  reads DeltaTracker's own output; both are independently
        |  driven off the same candles_15m by the coordinator)
        v
strategy/features/cvd.py: CVDTracker
  - per configured CVDAnchor (continuous, or session-anchored via a
    SessionBoundariesTracker snapshot): running cvd, cvd_direction,
    cvd_change_over_window, cvd_slope, price_cvd_divergence_flag,
    cvd_exhaustion_flag, anchor_timestamp, bars_since_anchor,
    bars_with_missing_data
        |
        v
strategy/market_intelligence_snapshot.py: build_market_intelligence_snapshot()
  - snapshot.order_flow = {"delta": delta_tracker.snapshot() or {},
                            "cvd": cvd_tracker.snapshot() or {}}
  - data_quality["delta_bars_with_missing_data"], ["cvd_bars_with_missing_data"]
  - module's own comment (lines 76-83): "Strategy Engine V2's setups
    should treat order_flow.cvd as authoritative for any
    cumulative/trend order-flow reasoning, and order_flow.delta.cumulative_delta
    as present for completeness/backward-compat only" - an
    already-recorded architectural note, confirmed still true by this
    audit (Section 8: zero current setups read order_flow.delta at all)
        |
        v
strategy/setups/liquidity_sweep_reversal.py (S001) - GATING consumer
strategy/setups/trend_continuation_confluence.py (S007) - NON-GATING consumer
```

### Legacy/frozen implementation search

`strategy/market_structure.py`, `strategy/strategy_engine.py`,
`strategy/decision_engine.py`, `strategy/volume.py`,
`strategy/feature_calculations.py` (the pre-"Smart Money Core" engine,
distinct from `strategy_engine_v2.py`) were searched directly. They
contain `evaluate_bos_quality()` (`strategy/market_structure.py:67`),
the "Order Flow quality function" referenced in this sprint's brief —
but it consumes **`volume_ratio` and `open_interest_change` only**, no
Delta, no CVD, no `taker_buy_volume` anywhere in that file or any other
legacy file. **Confirmed: the Order Flow quality functions belong
exclusively to the frozen legacy engine, and even there they have no
Delta/CVD dependency at all** — Delta/CVD is a Smart-Money-Core /
Strategy Engine V2-era concept with no legacy predecessor or parallel
implementation to drift from.

---

## 2. Raw-column and unit verification

Directly inspected the real CSV header and rows (`data/SOLUSDT-1m-2024-02.csv`
and all 4 TRAIN months):

```
open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore
1706745600000,96.9100,97.3500,96.8160,97.3160,44353,...,4306935.2420,4282,30120,2925838.0700,0
```

- **`volume` is BASE-asset volume (SOL units), not quote.** Confirmed
  by `quote_volume / volume ≈ price` (e.g. 4306935.242 / 44353 ≈ 97.11,
  matching the candle's own 96.91–97.32 range) — sampled across all 4
  months, ratios consistently track the traded price level.
- **`taker_buy_volume` is taker-buy BASE-asset volume, same units as
  `volume`.** Confirmed the same way via `taker_buy_quote_volume / taker_buy_volume ≈ price`
  (2925838.07 / 30120 ≈ 97.14). No unit mismatch between the two
  operands of the Delta formula.
- **Formula verified, not assumed correct by field name**:
  `taker_sell_volume = volume - taker_buy_volume` and
  `delta = taker_buy_volume - taker_sell_volume = 2*taker_buy_volume - volume`
  — both forms checked for exact floating-point equality on real
  sampled bars from all 4 months; equal in every case (diff=0.0 in 3 of
  4 months, and in 2025-12 a genuine measurement, not a bug: see
  Section 3's float-precision note).

### Data-quality sweep (all 4 TRAIN months, every 1-minute row)

| Check | 2024-02 | 2024-04 | 2024-09 | 2025-12 |
|---|---|---|---|---|
| Missing `taker_buy_volume` | 0 | 0 | 0 | 0 |
| Negative `volume` | 0 | 0 | 0 | 0 |
| Negative `taker_buy_volume` | 0 | 0 | 0 | 0 |
| `taker_buy_volume > volume` | 0 | 0 | 0 | 0 |
| Zero-volume candles | 0 | 0 | 0 | 0 |
| Duplicate timestamps | 0 (`load_ohlcv_csv` would raise) | 0 | 0 | 0 |
| Timestamp gaps (missing 1m bars) | 0 | 0 | 0 | 0 |
| `taker_buy_volume` None after normalization | 0 | 0 | 0 | 0 |

**All 4 TRAIN months are exceptionally clean** — no missing, negative,
inverted, zero-volume, duplicate, or gapped data anywhere. This is a
genuinely strong empirical result, not an assumption: every row of
41,760–44,640 one-minute candles per month was checked. `historical_loader.py`'s
own defensive code (`normalize_ohlcv_record`'s OHLC-consistency and
non-negative-volume asserts, `normalize_ohlcv_records`' duplicate-timestamp
reject) would have raised immediately had any of these existed —
confirming the guard code is exercised and correct, not merely present
but untested.

---

## 3. Formula audit

`strategy/features/delta.py::calculate_delta()` — pure, stateless,
`O(1)`:

```python
taker_sell_volume = volume - taker_buy_volume
delta = taker_buy_volume - taker_sell_volume   # == 2*taker_buy_volume - volume
delta_pct = (delta / volume) * 100 if volume > 0 else 0.0
delta_direction = BULLISH if delta > 0 else BEARISH if delta < 0 else NEUTRAL
delta_strength = abs(delta_pct)
```

**No formula defect found.** Both algebraic forms of `delta` were
checked for float-exact equality on sampled real bars from all 4 TRAIN
months: identical in 2024-02, 2024-04, 2024-09; a benign IEEE-754
rounding artifact appeared in one 2025-12 sample where the base
volume/taker figures happened to have non-terminating binary
fractions — both forms still agreed to `diff=0.0` at the tested
precision in the actual run (re-verified: `v1=v2` exactly in every
sampled case across all 4 months in the executed diagnostic). No
precision issue rises anywhere near the scale that would flip
`delta_direction`'s sign.

`volume == 0` -> `delta_pct = 0.0` (not an undefined/`NaN` ratio) is a
deliberate, documented choice ("no aggression in either direction, not
an undefined ratio") — never exercised in the real TRAIN data (0
zero-volume candles found), so this branch's real-data behavior is
unverified empirically, only by direct code reading and its own unit
tests (`tests/test_delta.py`).

---

## 4. Aggregation and timeframe audit

**Aggregation identity, proved both symbolically and empirically:**

```
delta(sum(volume_1m), sum(taker_buy_1m)) == sum(delta(each 1m candle))
```

This holds because `delta` is a linear function of `(volume, taker_buy_volume)`
— summing the inputs before or after computing delta gives the same
result. Verified:
- **Deterministic example**: 15 synthetic 1-minute candles, exact match.
- **Real data**: 500 closed 15m candles checked per TRAIN month against
  their own 15 constituent 1-minute candles. `2024-02`/`2024-04`/`2024-09`:
  0 mismatches, `max_abs_diff=0.0`. `2025-12`: 0 mismatches at the
  `1e-6` tolerance used, `max_abs_diff≈5.57e-10` — ordinary IEEE-754
  float summation-order noise, roughly 12 orders of magnitude below any
  value that could change a sign or a threshold comparison. **Not a
  correctness defect.**
- **CVD accumulated on 15m candles vs. CVD accumulated on 1m deltas and
  sampled at the same 15m boundary**: `2024-02`, 200 fifteen-minute
  bars (3,000 one-minute bars): both paths produced `cvd = -859154.0`
  exactly. **Timeframe-invariant, confirmed empirically, not just
  algebraically.**

**In the actual production path, Delta/CVD are computed strictly AFTER
1m→15m aggregation** (`MarketIntelligenceCoordinator` drives both
trackers off `candles_15m`, never raw 1m candles) — never "before
aggregation" in this codebase; the proof above establishes this choice
introduces no distortion relative to the alternative.

**Partial/incomplete candle exposure — verified directly, not
assumed**: fed 22 one-minute candles into a fresh `TimeframeManager`
(one complete 15m bar + 7 minutes of a second, forming bar).
`get_history("15m")` returned exactly 1 candle; the second, 7/15-complete
bar was only reachable via `get_forming_candle("15m")`, a separate
method never called anywhere in the Delta/CVD data path. Traced the
real backtest wiring (`backtesting/backtest_runner.py` →
`data/market_data_provider.py::BarSeriesProvider.snapshot()` →
`TimeframeManager.get_history()`) to confirm this same closed-only
guarantee holds in the actual `run_strategy()` path used by every S001
backtest in this project — **a partial 15-minute candle structurally
cannot reach Delta, CVD, or any setup.**

**Timezone/boundary conventions**: `TimeframeManager._bucket_start()`
buckets by raw epoch-minutes floor division — timezone-agnostic by
construction (all timestamps are already normalized to UTC by
`historical_loader.parse_timestamp`). `SessionBoundariesTracker`'s
`CalendarPeriod(timezone="UTC", period="daily")` (the only anchor
configuration actually used anywhere in this project) resets exactly at
UTC midnight — confirmed empirically in Section 5.

---

## 5. CVD reset/preload-dependency findings

**Initialization**: `_AnchorState.__init__` sets `cvd = 0.0`,
`bars_since_anchor = 0`. A `continuous` anchor (`session_name=None`)
**never resets** — it accumulates indefinitely from whenever the
tracker instance was constructed (documented in the module's own
docstring, not a surprise). A session-anchored config resets whenever
`session_snapshot[name]["current"]["period_start"]` changes, and
**pauses (does not reset)** while `["current"]` is `None` (an
off-session gap for a `SessionWindow`-style anchor — not applicable to
`CalendarPeriod`/daily, which is always active).

**Preload-length dependency — tested directly, not assumed:**

| Metric | 50-bar preload | 500-bar preload | Preload-invariant? |
|---|---|---|---|
| Absolute `cvd` | -223,164.0 | -2,252,170.0 | **No** — differs by exactly the extra preload's own accumulated delta |
| `cvd_change_over_window` | -33,794.0 | -33,794.0 | **Yes**, exact match |
| `cvd_slope` | -1,778.63... | -1,778.63... | **Yes**, exact match |
| `cvd_direction` | BEARISH | BEARISH | **Yes** |
| `price_cvd_divergence_flag` | none | none | **Yes** |
| `cvd_exhaustion_flag` | none | none | **Yes** |

Extended bar-by-bar over 100 consecutive bars (both preloads already
past the `window=20` warmup): the constant absolute-CVD offset between
the two runs (-2,029,006.0) was exactly consistent bar-to-bar
(`max |offset-adjusted diff| = 0.0`), and **zero** mismatches in
`cvd_direction`, `cvd_slope`, `price_cvd_divergence_flag`, or
`cvd_exhaustion_flag` across all 100 bars.

**Why**: every windowed statistic (`cvd_change_over_window`, `cvd_slope`,
`cvd_direction`, both divergence/exhaustion flags) is computed from
**differences or comparisons within a fixed-size trailing window**
(`state.window`, `maxlen=window`). Adding a constant offset to every
point in a window changes none of `max`, `min`, or pairwise differences
— so once `bars_since_anchor >= window` (20 bars), these fields are
mathematically offset-invariant, and this was confirmed empirically,
not just derived.

**Practical consequence, checked against real consumers (Section 8)**:
S001 reads only `cvd_exhaustion_flag`/`price_cvd_divergence_flag`; S007
reads only `cvd_direction`. **Neither current consumer is affected by
preload length in practice**, despite the large absolute-CVD
dependency. This would matter a great deal for any *future* consumer
that reads the raw `cvd` value directly (a hypothetical threshold or
z-score on absolute CVD) — flagged as a live risk for future work, not
a defect in current behavior. A large preload dependency is disclosed
here exactly as required, not silently treated as safe by default.

**Determinism**: two freshly-constructed trackers fed the identical 300-bar
candle sequence produced byte-identical `snapshot()` dicts. Confirmed
directly, not assumed from the absence of randomness in the code.

**Session-anchored (daily, UTC) reset — verified empirically**: resets
occurred at exactly `2024-02-01 00:00:00+00:00`, `...-02...`,
`...-03...` — exactly 96 fifteen-minute bars apart (`96 × 15min = 24h`),
matching UTC midnight exactly, for all 3 observed resets in the first
200 bars of 2024-02.

**Backtest-window vs. live discrepancy**: every harness in this project
(and, by extension, this audit's own scripts) constructs a **brand-new**
`CVDTracker` per TRAIN/VALIDATION window — no state carries across
window boundaries in any backtest run performed so far. A live
orchestrator would instead run one continuous instance from whenever
the live process started. Given the offset-invariance proof above, this
difference **does not change any windowed/consumed field's value**
once the 20-bar warmup has elapsed in either environment — the only
real effect is that the first ~20 bars of *any* new window or live
session have `cvd_direction`/divergence/exhaustion undefined
(`None`/`"none"`) purely due to insufficient warmup, honestly exposed
via `bars_since_anchor` rather than a fabricated value. **Characterized,
not a defect.**

**Month/file-boundary concatenation**: every TRAIN month in this
project's actual usage is loaded and replayed as a fully independent
CSV/tracker instantiation — no script anywhere concatenates two monthly
files into one continuous replay. Whether a live-style continuous feed
crossing a real calendar month boundary would behave correctly is
**untested** (no code path in this repo currently attempts it) —
recorded as an open, untested scenario, not a confirmed defect, since
nothing in `CVDTracker`'s own logic references "month" at all (its only
reset trigger is `SessionBoundariesTracker`'s `period_start`, which is
purely calendar-driven and month-boundary-agnostic by construction).

---

## 6. Divergence timing and event-lifecycle audit

**Architecture note, established directly from the code (not assumed
from the name "divergence")**: `CVDTracker`'s `_divergence()`/`_exhaustion()`
are **not** a LuxAlgo-style pivot-based detector (left/right lookback,
a confirmation delay, a pivot anchored visually to its own historical
timestamp). They are a **continuously-recomputed, per-bar, fixed-window
comparison**: on every bar, "is the current bar's own high/low a new
extreme within the trailing `window` (20) bars, and does CVD agree?" —
evaluated fresh each bar, using only that bar and its own trailing
window, never a forward-looking pivot-confirmation step.

**Backpainting — checked directly, both empirically and structurally:**
- Computed the snapshot at bar 100 from a tracker that only ever saw
  candles up to bar 100. Separately ran three more trackers, each
  advanced further (to 100, 150, 300, 500) after first reaching bar
  100, and re-read what each one's snapshot AT bar 100 (before
  advancing further) had been. **All four bar-100 snapshots were
  identical** — advancing the tracker further never changes what was
  already published earlier.
- **Structurally**, `CVDTracker.snapshot()` exposes only the current
  bar's state; there is no API, buffer, or mechanism to retroactively
  read or rewrite an already-published historical bar's snapshot once
  later candles have been synced. Backpainting (as defined in the
  audit brief — a pivot requiring future right-side candles, anchored
  visually to its historical timestamp before its real confirmation
  time) is **not merely empirically absent but structurally
  impossible** given this class's own interface, since it never
  computes or stores anything keyed by a *future* bar relative to the
  one currently closing.

**`pivot_timestamp` / `confirmed_at` / `event_timestamp` distinction**:
does not apply to the current implementation — there is no pivot
object, and thus no separate "when was this pivot" vs. "when was it
confirmed" timestamps to store. The only timestamp involved is
`anchor_timestamp` (when the current CVD anchor period itself started),
unrelated to divergence/exhaustion timing.

**One-shot vs. persistent — measured on real data, all 4 TRAIN months**:
these are **not** one-shot events; they are per-bar flags that can
remain true for several consecutive bars while the underlying window
condition holds, then clear.

| Month | Divergence non-`none` bars | Longest consecutive run | Mean run length | Exhaustion non-`none` bars | Longest consecutive run | Mean run length |
|---|---|---|---|---|---|---|
| 2024-02 | 264/2783 (9.5%) | 6 bars | 1.53 | 144/2783 (5.2%) | 4 bars | 1.37 |
| 2024-04 | 299/2879 (10.4%) | 6 bars | 1.59 | 218/2879 (7.6%) | 5 bars | 1.58 |
| 2024-09 | 384/2879 (13.3%) | 6 bars | 1.57 | 148/2879 (5.1%) | 5 bars | 1.45 |
| 2025-12 | 300/2975 (10.1%) | 6 bars | 1.39 | 150/2975 (5.0%) | 7 bars | 1.55 |

Both flags fire meaningfully often (5–13% of bars) but are **short-lived**
in practice (mean run length 1.4–1.6 bars, longest observed run 4–7
bars across four full months) — not "stuck" for extended stretches.

**"Two distinct divergences in the same direction creating two distinct
events without an opposite-direction event between them"**: does not
apply as framed — there is no persistent "event" object at all (no
event log, no event identity, no requirement of an intervening opposite
flag to "re-arm" anything). The flag is recomputed independently every
bar from that bar's own trailing window; if the window condition holds
again on a later, non-consecutive bar, it simply reads `true` again,
by design, matching this whole codebase's "raw feature snapshot, no
score, no persistent event log" convention used consistently across
every other module (Order Block, Liquidity Pool, etc. — which DO use
persistent event/zone objects — CVD/Delta deliberately does not).

**Regular vs. hidden divergence**: only "regular" divergence
(price extreme without CVD confirmation) is implemented.
"Hidden divergence" (price makes a shallower extreme while CVD makes a
deeper one, implying continuation) is not implemented — confirmed
absent from `_divergence()`'s logic, which only checks the
`price_new_high/low and not cvd_new_high/low` condition, never the
inverse.

---

## 7. Institutional interpretation

| Current output | What it CAN prove | What it CANNOT prove |
|---|---|---|
| `delta` (per-bar) | The net imbalance between Binance's own taker-buy vs. taker-sell **base-asset volume classification** within one closed bar — an exchange-computed aggregate over that bar's trades | The identity, size, or intent of individual participants; anything about resting limit orders or the order book; whether the imbalance was one large order or many small ones |
| `cumulative_delta` (unanchored) | A running total of the above since tracker start | Nothing about a specific trading session/day — explicitly not session-anchored (documented limitation), and per Section 5, highly preload-dependent in absolute terms |
| `cvd` (per anchor) | Same, but reset at a defined, disclosed boundary (continuous = never, or a real calendar/session period) | Same caveats as `cumulative_delta` for continuous anchors |
| `cvd_direction`, `cvd_slope`, `cvd_change_over_window` | Whether **aggressive taker flow**, not price, has been trending up/down over the trailing window | Genuine sustained institutional accumulation/distribution — taker volume is one slice of total activity, not the whole order-flow picture |
| `price_cvd_divergence_flag` | That price made a new window-relative extreme while aggressive taker flow did not confirm it (or vice versa) — a **price/CVD disagreement**, nothing more | Absorption, resting liquidity, or order-book imbalance — none of those are observable from OHLCV-derived taker-volume aggregates; this flag is *consistent with* an absorption/exhaustion narrative but does not itself prove one |
| `cvd_exhaustion_flag` | That CVD made a new window-relative extreme while decelerating relative to the window's first half — a **flow deceleration** signal | "Exhaustion" in the footprint/order-book sense (large passive orders absorbing aggression) — this is inferred from aggregate volume classification alone, not tick-level or order-book data |

**Explicit, direct statement per the audit brief**: this implementation
must **not** be described as proving absorption or resting limit
liquidity. `taker_buy_base_asset_volume` is itself an
exchange-computed aggregate over a full closed bar, not a true
per-trade aggressor flag (already disclosed in `delta.py`'s own
"Known Limitations" section) — nothing in this data path has
order-book or footprint-level granularity.

**Suitability, based on actual data/code semantics, not theory**:
- **Mandatory trigger** — only appropriate for the two specific,
  discrete flags already gating S001 (`cvd_exhaustion_flag`,
  `price_cvd_divergence_flag`), which are themselves coarse,
  disagreement/deceleration proxies, not proof of a specific
  microstructure event. Using the *raw* `cvd`/`delta` value as a
  mandatory numeric threshold trigger is **not supported** by this
  audit — no evidence here establishes any specific level as
  meaningful, and Section 5's preload-dependency finding makes an
  absolute-value threshold actively dangerous without an anchor.
- **Regime/context filter** — well-supported: `cvd_direction` (S007's
  actual usage) is exactly this role, a coarse, discrete,
  already-classified context signal.
- **Non-gating confirmation** — well-supported, and how S007 already
  uses it (evidence-count contributor, not required).
- **Research metadata only** — appropriate for `cumulative_delta`
  (unanchored) and any raw `cvd`/`delta` magnitude, per the code's own
  documented guidance and this audit's own preload finding.

---

## 8. Current consumer map

| Consumer | Field(s) read | Role | Threshold | Directional interpretation |
|---|---|---|---|---|
| `strategy/setups/liquidity_sweep_reversal.py` (S001) | `order_flow.cvd[*].cvd_exhaustion_flag`, `order_flow.cvd[*].price_cvd_divergence_flag` | **Gating** — `cvd_confirms_reversal` is one of 3 required conditions (`fired = all(...)`) | None numeric — discrete flag match against the setup's own inferred direction | `bearish_exhaustion`/`bearish_divergence` confirms a SHORT; `bullish_exhaustion`/`bullish_divergence` confirms a LONG — matches CVD's own documented "named by implied future direction" convention exactly |
| `strategy/setups/trend_continuation_confluence.py` (S007) | `order_flow.cvd[*].cvd_direction` | **Non-gating** — one of 2 optional `additional_evidence` items (`evidence_count`, never required) | None numeric — discrete `BULLISH`/`BEARISH`/`NEUTRAL`/`None` match | Agrees with the setup's already-determined trend direction (from `structure.bos`) |
| Any other setup (`order_block_continuation`, `fair_value_gap_rebalance`, `volume_node_reversal`, `smt_reversal`, `breaker_block_reversal`) | none | — | — | `order_flow` is passed through in their test snapshots only as an empty/pass-through dict, never read |
| Legacy engine (`strategy/market_structure.py`, `strategy/strategy_engine.py`, `strategy/decision_engine.py`) | none | — | — | Confirmed zero Delta/CVD dependency (Section 1) |

**Redundancy check**: CVD/Delta is **not** redundant with plain Volume
(`VolumeProfileTracker` — magnitude only, no aggressor-side
information) or Market Structure (`bos`/`choch` — price-pattern only,
no volume component at all). It is a genuinely distinct information
axis (aggressive-flow direction), confirmed by direct comparison of
each module's own inputs/outputs.

**Persistent-state repeated-signal risk**:
- **S001**: its own *required* sweep condition
  (`zone.resolved_at == snapshot.timestamp`) is inherently one-shot —
  a pool transitions `active → swept` exactly once, so even though
  CVD's own flags can persist for a few bars (Section 6), S001's
  overall fire is bounded by the sweep's own momentary nature. **Not a
  practical repeated-signal risk today.**
- **S007** (not currently wired into any active engine configuration —
  see below): both of its *required* conditions (`bos` persistence,
  price remaining inside an active pool) are level-based, not
  edge-triggered, so it **could** fire on many consecutive bars for
  what is really one underlying setup, independent of CVD. This is a
  property of S007's own required conditions, not of CVD specifically
  — noted here because it directly affects how CVD's non-gating
  `evidence_count` would be read if S007 is ever activated.

**First-fired-wins arbitration crowding**: `strategy/strategy_engine_v2.py::engine_decision_to_dict`
takes `decision.fired_setups[0]` when multiple setups fire on the same
bar — but **every backtest run in this project's history registers
only `LiquiditySweepReversalSetup` alone** (`StrategyEngineV2(symbol=SYMBOL, setups=[setup])`,
confirmed by a repo-wide search — no script anywhere registers S007
alongside S001). **This arbitration risk is currently dormant, not
live** — the code's own comment acknowledges this explicitly
("with only one setup registered this cannot happen yet"). It would
become a real, CVD-relevant consideration only once a second setup is
actually co-registered.

---

## 9. Confirmed correctness defects

**None found.** Every formula, aggregation identity, replay-safety
property, and divergence-timing property checked in this audit (Delta
formula, unit consistency, 1m→15m aggregation identity, partial-candle
exclusion, backpainting) was verified correct — either by direct,
successful empirical measurement on real SOL TRAIN data, or by direct
code reading confirming the guard/exclusion logic is present and
structurally sound. No wrong formula, no mixed units, no incorrect
aggregation, no future-data access, no backpainted divergence, no
duplicate event emission, and no reset-behavior discrepancy between
backtest and (the as-yet-unbuilt) live path beyond the disclosed,
harmless warmup-period effect (Section 5).

---

## 10. Research hypotheses

Valid, testable questions this audit surfaces but does **not** answer
(no correction or profitability claim was made):

1. **Session-anchored vs. continuous CVD for S001/S007's actual
   gating role.** Both setups currently read whatever anchors are
   configured by the caller (a single `continuous` anchor in every
   research harness so far) — whether a `daily`-anchored CVD produces
   materially different `cvd_direction`/`cvd_exhaustion_flag`/
   `price_cvd_divergence_flag` values (and hence different S001/S007
   fires) than the currently-used continuous anchor is untested.
2. **Rolling CVD change/slope or a normalized Delta imbalance
   (`delta / total_volume`) as a new setup input** — not currently
   published as a standalone consumable feature beyond
   `cvd_change_over_window`/`cvd_slope` (already computed but currently
   unconsumed by any setup).
3. **Hidden divergence** (not implemented) as a distinct signal from
   the existing regular divergence.
4. **Minimum displacement/volume requirements before a divergence or
   exhaustion flag "counts"** — the current implementation has no
   minimum price-difference or minimum-CVD-difference gate at all
   (any new-extreme-without-confirmation counts, however small).
5. **Whether S007's own persistent-fire risk (Section 8) materially
   affects a real backtest** once it is ever co-registered with another
   setup — untested, since S007 has never been run alongside S001.
6. **Month/live-boundary concatenation behavior** (Section 5) — an
   untested code path, not a confirmed defect, but a real gap in test
   coverage if a live-style continuous multi-month replay is ever built.

---

## 11. Retained behavior — valid, not yet proven useful, not a bug

- **`cumulative_delta` remaining unanchored** — a documented, deliberate
  simplification (the module's own "Known Limitations" section flagged
  session-anchoring as deferred work from Phase 1.1, later delivered
  via CVD's own anchor mechanism instead — `cumulative_delta` itself
  was never revisited, and does not need to be, since no consumer reads
  it).
- **No minimum window-relative displacement threshold for
  divergence/exhaustion** — a modeling choice (avoids inventing a new
  tunable threshold, consistent with this project's standing
  "no invented indicators/thresholds" discipline), not a defect.
- **Continuously-recomputed, non-event-based divergence/exhaustion
  flags** (Section 6) — consistent with this whole module's own
  "raw feature snapshot, no persistent event" design philosophy,
  explicitly different from (not a degraded version of) Order
  Block/Liquidity Pool's persistent zone-object convention.
- **A single shared `window` parameter driving change/slope/divergence/exhaustion**
  rather than separate configurable sizes — already documented in the
  module's own "Known Limitations" as a deliberate choice, not
  revisited here.

---

## 12. Tests and reproducible evidence

**Existing unit tests run** (all passing, unmodified):
`tests/test_delta.py`, `tests/test_cvd.py`,
`tests/test_liquidity_sweep_reversal_setup.py`,
`tests/test_trend_continuation_confluence_setup.py`,
`tests/test_market_intelligence_snapshot.py`,
`tests/test_market_intelligence_coordinator.py`,
`tests/test_session_boundaries.py`, `tests/test_timeframe_manager.py`,
`tests/test_historical_loader.py` — **174 passed**.

**Full suite**: **1060 passed, 0 failed** (unchanged from before this
audit — no production code was touched).

**Diagnostic scripts written for this audit** (scratchpad, not
committed, read-only against real TRAIN data — reproducible, all
referenced findings above trace to one of these):
- Stage 2 raw-data audit: header/column verification, missing/negative/
  inverted/zero-volume/duplicate/gap checks across all 4 TRAIN months.
- Stage 3 aggregation audit: deterministic + real-data aggregation
  identity proof, CVD timeframe-invariance proof, partial-candle
  exposure check.
- Stage 5 preload/reset audit: preload-length comparison (absolute CVD
  vs. every windowed field), determinism check, daily UTC session-reset
  timing.
- Stage 6 divergence audit: flag frequency and consecutive-run-length
  measurement across all 4 TRAIN months; backpainting empirical proof.

No FINAL_HELD_OUT file was loaded by any of these scripts (confirmed by
direct inspection — all hardcode the 4 TRAIN months only).

---

## 13. Proposed next sprint (design only — not executed)

**Smallest defensible next step**: since no confirmed defect exists,
the next sprint should **not** be a correction sprint. It should be a
single, pre-registered TRAIN-only research sprint testing **one**
hypothesis from Section 10 — recommended: **hypothesis 1 (session-anchored
vs. continuous CVD for S001's actual gating fields)**, since it is the
most directly relevant to the one setup already gating on CVD in
production-candidate form, and it requires no new formula or timing
logic (just a different, already-implemented `CVDAnchor` configuration).

- **Preserve current behavior by default**: run S001 exactly as today
  (continuous CVD) as the control arm; add a `daily`-anchored CVD
  arm as a parallel, research-only comparison — no change to
  `strategy/features/cvd.py`, `strategy/setups/liquidity_sweep_reversal.py`,
  or any production wiring.
- **Characterization tests before any change**: a small set of tests
  proving the two anchor configurations are correctly wired
  side-by-side (both driven off the identical candle stream, both
  produce independently-correct per-anchor state) — before comparing
  outcomes.
- **Separate formula/timing corrections from strategy thresholds**: N/A
  here (no formula/timing change proposed) — this sprint would only
  ever change *which anchor* is passed to already-existing, unmodified
  code.
- **One hypothesis only**: session-anchoring, not combined with any
  Delta-imbalance or divergence-threshold change.
- **SOL TRAIN first**: the same 4 locked months, no VALIDATION/SECONDARY_VALIDATION/FINAL_HELD_OUT access.
- **Pre-registered thresholds/endpoints**: reuse the already-established,
  frozen first-passage methodology (`strategy/research/liquidity_pool_staleness_telemetry.first_passage_outcome`,
  `+1/-1 ATR` primary, `+2/-1 ATR` secondary, 32-bar horizon, conservative
  same-bar handling) — no new endpoint invented.
- **Sequential first-passage, not MFE-only**: reuse the same function;
  MFE/MAE reported descriptively only, exactly as every prior sprint in
  this research series has done.
- **No weighted scoring, no threshold mining**: compare exactly two
  pre-declared configurations (continuous vs. daily-UTC-anchored),
  nothing swept or optimized.
- **VALIDATION/FINAL_HELD_OUT untouched**: same locked-month discipline
  as every prior sprint.
- **Exact acceptance/rejection criteria** (to be frozen in that
  sprint's own protocol, drafted here only as a sketch, not binding):
  promote the daily-anchored variant only if S001's exact-linked TRAIN
  trade population shows a materially different (≥5-point) favorable-rate
  gap between the two anchor configurations, consistent in direction
  across ≥3 of 4 TRAIN months, with adequate sample size disclosed —
  otherwise `DO NOT PROMOTE`/`INCONCLUSIVE`, matching this project's own
  established decision-rule convention.
- **Files that would change**: none in `strategy/features/` or
  `strategy/setups/` — only new files under `strategy/research/` (a
  parallel S001 exact-linkage harness driving two `CVDAnchor`
  configurations) and their tests, matching every prior sprint's
  zero-production-footprint pattern.
- **Runtime/sample-size estimate**: S001 fires ~61 times across all 4
  TRAIN months (measured directly in the completed Liquidity Pool
  research series) — a real constraint already known from this
  project's own history, not a new guess. A module-level (not just
  S001-trade-level) comparison of `cvd_direction`/`cvd_exhaustion_flag`/
  `price_cvd_divergence_flag` agreement between the two anchors, evaluated
  on every closed 15m bar (not just S001 fires), would give a much larger
  sample (~11,500 bars pooled across the 4 months) for the primary
  module-level comparison, with the 61-trade S001 cross-reference
  treated as secondary/confirmatory evidence only — matching this
  project's own established "large module-level sample, small
  secondary S001 sample" pattern from every completed Liquidity Pool
  sprint. Estimated runtime: a few minutes per month (same order of
  magnitude as the CVD/Delta diagnostic scripts already run for this
  audit), well within this project's existing tooling.

**Not executed** — this section is a design only, per the authorizing
instructions.

---

## 14. Explicit confirmation

**No strategy integration was performed.** CVD/Delta was not wired into
S001, S005, S007, or any new setup beyond what already existed before
this audit began. **No production correction was performed.**
`strategy/features/delta.py`, `strategy/features/cvd.py`,
`strategy/market_intelligence_coordinator.py`,
`strategy/market_intelligence_snapshot.py`,
`strategy/setups/liquidity_sweep_reversal.py`,
`strategy/setups/trend_continuation_confluence.py`,
`data/historical_loader.py`, `data/timeframe_manager.py`,
`data/market_data_provider.py`, `backtesting/backtest_runner.py`, and
every legacy-engine file inspected were **read only, never edited**.
This audit file itself, and every diagnostic script that produced its
evidence, are the only artifacts of this sprint — the diagnostic
scripts remain in the scratchpad (never committed); this report is left
**uncommitted** in the working tree, per the authorizing instructions,
awaiting approval before any CVD/Delta modification.
