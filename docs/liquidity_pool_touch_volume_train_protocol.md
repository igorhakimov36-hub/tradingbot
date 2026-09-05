# Liquidity Pool Touch Count and Volume — Frozen TRAIN Protocol

**Written and frozen BEFORE any TRAIN outcome (directional or S001) is
computed.** SHA-256 hash recorded immediately after saving, before the
telemetry harness is run against the four TRAIN months, and re-verified
before the final report is written.

## Research question (two independent hypotheses, never combined)

1. **Touch Count**: does the number of distinct prior interactions
   (touch episodes) with a Liquidity Pool contain reliable information
   about the quality of its later sweep? Direction is not assumed in
   advance — more touches could strengthen a level (more resting
   liquidity, more validation) or weaken it (repeated testing consumes
   the level).
2. **Volume**: does the actual total traded volume during those
   interactions contain reliable information about sweep quality,
   independent of Touch Count?

No combined rule, weighted score, or optimized filter is produced in
this sprint. Each hypothesis gets its own verdict.

## Locked scope (already final, not reopened here)

Existing Liquidity Pool geometry kept; Wick-Extremity geometry rejected
(`docs/liquidity_pool_wick_extremity_train_report.md`); Policy A kept;
Policy C not revived; S001 unchanged; no production signal or lifecycle
change; no CVD/Delta, FVG/IFVG, S008, or portfolio work. Observational
research only.

## Scope and data boundary

**TRAIN months only**: 2024-02, 2024-04, 2024-09, 2025-12. No
VALIDATION, SECONDARY_VALIDATION, or FINAL_HELD_OUT month is accessed,
enforced by an explicit assert on every processed month string
(`FORBIDDEN_MONTHS` in the harness), matching every prior sprint.

## Step 0 audit findings that shape this protocol

Recorded in full in the final report's Section 1; summarized here only
where they drive a frozen methodological choice:
- Round-number-only pools are 94.4% of all created pool instances and
  94.8% of actual sweeps (pooled, 4 TRAIN months) — essentially
  unchanged between creation and sweep, i.e. round numbers are not
  disproportionately filtered out by Policy A's own sweep condition.
- Round-number-only pools are only 47.5% of exact-linked S001 trades
  (vs. 94.4% of the underlying pool population) — S001's own
  `pool_has_multiple_sources` additional-evidence check structurally
  discriminates against single-source (round-number-only) pools,
  requiring CHOCH or SMT confirmation instead when a round-number pool
  sweeps. This is a genuine, pre-existing S001 architecture property
  (`strategy/setups/liquidity_sweep_reversal.py`), not a defect and not
  changed here.
- Only ~60–82 unique logical price levels (grouped by
  `(direction, round(level_at_creation / round_number_spacing) * round_number_spacing)`)
  produce ~99.3%–99.7% of all pool instances per month — round numbers
  are permanent price levels that legitimately re-form a fresh pool
  every time price revisits them after a prior sweep (documented,
  intentional behavior in `strategy/features/liquidity_pool.py`'s own
  docstring: "new orders accumulating near the same price afterward are
  a genuinely NEW pool, not a continuation of consumed liquidity" — not
  a duplicate-creation defect). This means the ~5,040-pool population
  used throughout this and the prior Wick-Extremity sprint has
  substantially fewer truly independent price levels than its raw count
  suggests. Both raw (per-pool-instance) and level-aware framings are
  carried through this protocol's reporting requirements; this is
  disclosed as a standing limitation on effective sample size, not
  silently corrected (no production or research population change is
  made because of it).

## Touch Episode definition (frozen)

Measured on **completed 15-minute candles** (the strategy timeframe
`LiquidityPoolTracker` itself already runs on — confirmed unchanged
from every prior sprint in this series).

- **Overlap** (inclusive both ends): a candle's `[low, high]` range
  overlaps the pool's zone `[zone_low, zone_high]` iff
  `candle_low <= zone_high AND candle_high >= zone_low`.
- **Current effective geometry**: the pool's live `zone_high`/`zone_low`
  AT that bar (production's own, possibly-widened-by-later-touches
  boundary) — never a fixed creation-time snapshot.
- A new episode begins when the current completed candle overlaps and
  the immediately preceding completed candle did not. Consecutive
  overlapping candles are one episode. An episode ends once at least
  one complete candle is outside the zone.
- The pool's own confirmation/creation candle never counts (excluded
  unconditionally).
- Only candles strictly after `pool_confirmed_at` (`created_at`) are
  eligible.
- The confirmed sweep candle is excluded from pre-sweep touch-episode
  counting entirely — including truncating an in-progress episode at
  the bar immediately before the sweep candle, never extending into it.
  The sweep candle's own interaction is recorded as a separate field
  (Section "Sweep-candle interaction" below), never folded into the
  episode count or pre-sweep volume.
- No future candle ever alters a previously published count — episode
  boundaries are determined strictly in forward chronological order
  from already-elapsed bars only.

Implemented in `strategy/research/liquidity_pool_touch_episodes.py`
(`classify_touch_episodes`), covered by 13 tests including causal
prefix/no-lookahead and current-effective-geometry checks.

**Frozen buckets** (declared before any outcome was computed, never
adjusted afterward): `0`, `1`, `2`, `3+` previous touch episodes.

## Volume definition (frozen)

**Actual total traded volume only.** `taker_buy_volume`, delta, CVD,
buy/sell imbalance, and any other directional order-flow feature are
explicitly excluded from this sprint (reserved for a later, separately
pre-registered CVD/Delta sprint).

### Zone-volume proxy (disclosed as approximate)

Where causally aligned 1-minute data is available (it is, for all four
TRAIN months), a 15-minute candle's own "zone volume" is estimated by
summing the full `volume` of every **completed** 1-minute candle within
that 15m candle's own time window (`[T, T+15min)`, matching
`data/timeframe_manager.py`'s own bucket-start convention) whose own
`[low, high]` range overlaps the pool's zone at that bar (same overlap
test as touch episodes). **This is explicitly a proxy, not a
measurement**: OHLCV data cannot prove that all — or even most — of a
1-minute candle's volume actually traded inside the exact price zone; a
1m candle that merely wicks through the zone contributes its entire
volume. A 1-minute candle whose own range never overlaps the zone
contributes exactly zero — **no uniform-within-range volume allocation
is ever invented.**

Implemented in `strategy/research/liquidity_pool_touch_volume.py`
(`zone_overlapping_1m_indices`, `candle_zone_volume`), covered by tests
proving non-overlapping 1m candles contribute zero.

### Relative volume normalization (frozen)

No existing point-in-time **trailing-over-time** relative-volume
convention exists in this repository —
`strategy/features/volume_profile.py`'s own `relative_volume` field is
a same-period, cross-sectional bucket-vs-average-bucket figure (a
different axis: comparing price buckets within one profile period, not
a candle's volume against its own recent history), confirmed by
reading that module directly, not assumed. A new trailing, causal,
scale-invariant **median** baseline is used instead:

`relative_volume(t) = volume(t) / median(volume(t - lookback .. t - 1))`

**Frozen parameters**: `lookback_minutes = 240` (4 hours of 1-minute
candles), `min_warmup = 240` (a candle before the 240th of the month has
an **undefined** relative volume — `None`, excluded from
relative-volume-dependent aggregates, never treated as zero or
back-filled). Never normalized using the full month or any future
candle — proven by
`test_changing_a_future_candle_does_not_change_an_earlier_relative_volume`
and `test_relative_volume_uses_only_strictly_prior_candles`. This
choice (4-hour trailing median) is made once, before any outcome is
computed, specifically to be long enough to smooth single-candle noise
while remaining short enough to stay point-in-time reactive without
requiring multi-day warmup; it is not revisited after seeing results.

### Reported volume fields (frozen, kept separate — never merged)

1. `pre_sweep_cumulative_touch_volume_raw` / `..._relative` — summed
   across all pre-sweep touch episodes only (sweep candle excluded).
2. `mean_relative_touch_volume_intensity` — mean of the relative volume
   of every zone-overlapping 1-minute candle across all pre-sweep
   episodes (an intensity/rate figure, not a total — deliberately kept
   distinct from the cumulative total, which is naturally correlated
   with Touch Count and pool duration and therefore cannot alone prove
   an independent Volume effect).
3. `sweep_candle_relative_volume` (and `sweep_candle_volume_raw` for
   transparency) — the sweep 15m candle's own zone-overlapping 1-minute
   relative volume, mean-aggregated the same way, computed and reported
   **separately** from every pre-sweep figure.

**Only normalized relative volume may qualify for promotion.** Raw
volume is reported for transparency only, per the authorizing
instructions.

## Formation contributors vs. post-confirmation touches (frozen, kept separate)

`formation_contributor_count`: the number of touches recorded on the
pool's own creation bar (from the reused Wick-Extremity touch ledger,
`strategy/research/liquidity_pool_wick_extremity_ledger.py`, unchanged)
— normally exactly 2 (a pool always forms from a pairwise match) but
can exceed 2 if additional same-bar candidates widen it before the bar
closes; captured precisely, never assumed to be a fixed constant.
`n_touch_episodes` (the Touch Count hypothesis variable): computed
independently as above. These two numbers are never combined into one
count or one score, per the authorizing instructions and proven by
`test_formation_contributor_count_independent_of_episode_count`.

## Directional endpoint (frozen, reused unchanged from every prior sprint)

Sequential, unconditional first-passage, starting at the candle
immediately after sweep confirmation:
- ATR frozen at sweep confirmation (standalone, point-in-time
  `AverageTrueRangeTracker`, period 14).
- **Primary**: `+1 ATR` favorable vs. `-1 ATR` adverse, whichever first.
- **Secondary**: `+2 ATR` favorable vs. `-1 ATR` adverse, whichever
  first.
- Fixed horizon: 32 candles (matching every prior sprint's own widest
  sensitivity window) — no resolution within it is right-censored.
- Same-bar ambiguity (both conditions satisfied on the same candle):
  counted conservatively as **adverse**.
- No conditioning on survival to a later horizon.
- MFE/MAE reported descriptively only (independent running extrema, not
  simulated profitability).
- Reused unchanged from
  `strategy/research/liquidity_pool_staleness_telemetry.first_passage_outcome`.

## Population / conversion analysis horizon (frozen)

A **fixed 32-candle observation horizon from pool creation** is used to
classify a pool created near month-end as "too early to judge" rather
than a false failure: any pool whose `origin_bar_i` is within 32 bars
of the month's own last bar is flagged `insufficient_observation_window`
in the population tables and excluded from formation-to-sweep
conversion-rate denominators (but never excluded from the raw creation
count, which is unconditional).

## Censoring (frozen, reused convention)

A pool that never sweeps and is not `insufficient_observation_window`
by month end is right-censored — reported explicitly as its own
category everywhere, never conflated with "did not sweep because it was
a bad pool" or silently dropped from any denominator.

## S001 linkage (frozen, reused unchanged proven method)

Exact linkage only — no nearest-timestamp matching. Instrument
`strategy_callback` to call the real, unmodified
`LiquiditySweepReversalSetup._find_fresh_sweep(snapshot)` directly,
keyed by the exact 1-minute `current_candle` timestamp;
`OPENED`/`CLOSED` journal records paired by chronological index (not
`record_closed`'s own exit timestamp). Required proofs before trusting
the pairing: equal lengths, monotonic ordering, per-pair side/entry
match — identical to every prior sprint.

## Statistical discipline (frozen, restated from the authorizing instructions)

Touch Count and Volume are evaluated as **two separate hypotheses**,
never combined into a score or a joint filter in this sprint. No
threshold search for best P&L; no rule selected from the
best-performing month; no repeated gating backtests. One-pass
telemetry, then post-hoc slicing of the same, already-fixed event
population — the population and its telemetry are computed once, and
every reported breakdown (pooled/per-month/per-direction/per-source/
Round-Number-vs-not/raw-vs-dedup) is a slice of that one fixed dataset,
not a re-run.

## Decision rule (frozen, not renegotiated after results are seen)

Separate verdict for Touch Count and for Volume, each one of
`PROMOTE TO VALIDATION`, `DO NOT PROMOTE`, `INCONCLUSIVE`.

**PROMOTE TO VALIDATION** only if, on the primary favorable-first
endpoint:
1. The difference between the weakest and strongest predeclared group
   is **at least 5 percentage points**.
2. The relationship has the **same direction in at least 3 of 4 TRAIN
   months**.
3. It remains coherent under the secondary (`+2/-1 ATR`) endpoint.
4. It is not explained by one direction, one source, pool age,
   censoring, or overlap (a single-source or single-month artifact is
   disqualifying even if criteria 1–3 pass).
5. Compared groups have adequate sample sizes (disclosed explicitly,
   not asserted).
6. S001 evidence does not materially contradict it (treated as
   secondary if S001 group sizes are small — no threshold is derived
   from a handful of trades).

**Touch Count additionally requires**: the trend across the fixed
0/1/2/3+ buckets must be **coherent/monotonic-or-clearly-directional**,
not merely "some pair of buckets differs" — a result driven by
selecting one convenient pair of buckets while the others are flat or
contradictory is `INCONCLUSIVE`, not `PROMOTE`.

**Volume additionally requires**: the effect must survive
normalization (raw volume alone never qualifies) and must remain after
controlling for Touch Count, direction, source, and pool age — an
effect that disappears once Touch Count is held roughly constant is
`DO NOT PROMOTE`, not spun as a weaker version of a Volume effect.

**DO NOT PROMOTE** if groups are statistically/practically
indistinguishable, or the effect reverses/vanishes under any of the
required controls above.

**INCONCLUSIVE** if sample sizes are inadequate for the comparison
actually required, results conflict materially across months, or the
module-level and S001 evidence disagree materially.

If both Touch Count and Volume independently qualify for
`PROMOTE TO VALIDATION`, the recommended next step is **two separate**
frozen VALIDATION experiments — never a combined rule at this stage.

---
FROZEN — SHA-256 of this file (computed over the file as saved, before
the telemetry harness was run against any TRAIN month): see
`docs/liquidity_pool_touch_volume_train_protocol.sha256`.
