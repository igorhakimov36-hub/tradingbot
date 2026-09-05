# Liquidity Pool Touch Count and Volume — SOL TRAIN Report

**Status: TRAIN-only observational research. Not a VALIDATION-grade
claim, not a production change.** Frozen protocol:
`docs/liquidity_pool_touch_volume_train_protocol.md`, SHA-256
`195988d36b580589f0e2fbbf7311bda66273caaca4b1980bc14d6d59de952746` —
verified unchanged immediately before the TRAIN telemetry harness's
first run and again immediately before this report was written.

## 0. Checkpoint

Commit `507f77b` confirmed to contain exactly the 9 completed
Wick-Extremity files (protocol + hash, report, 3 research modules, 3
test files — `git show --stat`), working tree clean before this sprint
began, full suite passing (1029/1029) at that point. This sprint added
9 new uncommitted files; full suite now **1060/1060 passing** (1029 +
31 new tests).

## 1. Architecture and source audit

Re-read `strategy/features/liquidity_pool.py` (full), the relevant
section of `strategy/market_intelligence_coordinator.py`,
`strategy/market_intelligence_snapshot.py` (`Zone.raw` = the pool's own
`to_dict()` output, confirmed by `LiquiditySweepReversalSetup`'s own
`swept_pool.raw.get("sources", [])` read), and
`strategy/setups/liquidity_sweep_reversal.py` (S001) in full — no
changes made to any of them.

The Step 0.5 audit reuses the already-computed, already-verified Policy
A pool population and exact S001 linkage from the completed
Wick-Extremity sprint (same real, unmodified `LiquidityPoolTracker`
output, same 4 TRAIN months) — a static population audit needs no
re-derivation, and reusing it avoids introducing any drift risk.

### Population summary (pooled, 4 TRAIN months)

| | Value |
|---|---|
| Total created pool instances | 5,041 |
| Direction split | buy_side 2,520 / sell_side 2,521 |
| Eventually swept | 4,836 (95.9%) |
| Median lifetime | 3–4 bars (0.75–1.0h) |
| Average lifetime | 60–96 bars (15–24h) — mean pulled far above the
median by a long tail of slow-resolving pools |

The large mean/median gap is itself informative: **most pools resolve
almost immediately**, while a minority persist for a long time,
consistent with round numbers being touched-and-swept quickly relative
to price's typical intraday range, and non-round-number pools
(session/equal-level) taking much longer (Section 3).

### Round Number dominance — measured precisely at each stage, never inferred from another

| Stage | round_number-ONLY | round_number-ANY (incl. multi-source) |
|---|---|---|
| Pool creation | 4,758 / 5,041 = **94.4%** | 4,930 / 5,041 = 97.8% |
| Actual sweeps | 4,583 / 4,836 = **94.8%** | 4,736 / 4,836 = 97.9% |
| S001 signals/trades (exact-linked) | 29 / 61 = **47.5%** | 51 / 61 = 83.6% |

**Round Numbers dominate pool creation and actual sweeps almost
identically (94.4% → 94.8%) — Policy A's own sweep condition does not
disproportionately filter them out.** But Round Numbers make up barely
half of exact-linked S001 trades (47.5%, down from 94.4% of the
underlying population) — a large, real drop-off at the S001 stage, not
at the pool/sweep stage. The mechanism is directly readable in
`strategy/setups/liquidity_sweep_reversal.py`'s own
`_multi_source_pool` check: a round-number-**only** pool has exactly
one source, so `pool_has_multiple_sources` is always `False` for it,
removing one of the three "additional evidence" conditions that gate
`has_additional_confirmation` — a round-number sweep must clear CHOCH
or SMT confirmation alone, while a multi-source pool gets a "free"
additional-evidence point. This is a genuine, **pre-existing** S001
architecture property, confirmed by direct code reading, not a defect
and not changed here (S001 is explicitly out of scope this sprint).

**Directional outcomes were checked separately, not inferred**: among
the 61 real, exactly-linked S001 trades, round-number-only trades
(n=29) had a 41.4% win rate and +$144.01 total net P&L; non-round-number
trades (n=32) had a 31.2% win rate and −$816.92 total net P&L. Reported
descriptively — the sample (29 vs. 32) is far too small to treat as
conclusive on its own, but it does **not** support a "Round Numbers are
low-quality signals" narrative at the S001 level, even though they
dominate the raw pool/sweep population overwhelmingly.

### Is the dominance a duplicate-creation or lifecycle defect? Characterized, not repaired

Grouping pools by `(direction, round(level_at_creation /
round_number_spacing) * round_number_spacing)` — i.e. by the
round-number price grid cell their creation level falls in — found only
**60–82 unique logical price levels per month, accounting for 99.3%–
99.7% of all 1,200+ pool instances that month.** In other words, the
"5,041 created pools" figure (used as a raw sample size throughout this
and the prior Wick-Extremity sprint) is overwhelmingly the **same ~70
round-number price levels being repeatedly re-formed** every time price
revisits them after a prior sweep.

**Determination: this is not a defect.** `strategy/features/liquidity_pool.py`'s
own docstring documents this as intentional: "Once swept, a pool is
retired... new orders accumulating near the same price afterward are a
genuinely NEW pool, not a continuation of consumed liquidity" — round
numbers are permanent arithmetic levels, so this behavior is the
designed consequence of using them as a source, not a lifecycle bug.
Per the authorizing instructions, **no repair was made and none was
needed**; this is disclosed as a standing **effective-sample-size**
limitation instead — pool-instance counts in this report (and in the
prior Wick-Extremity report) substantially overstate the number of
truly independent observations for round-number-sourced statistics,
since the same ~70 levels are resampled repeatedly. This does not
invalidate the aggregate directional results (each resample is still a
genuine, independent-in-time market event with its own price action
afterward), but it means the "n=5,040 pools" framing should be read as
"a few thousand *revisits* of a few dozen *levels*," not a few thousand
structurally distinct levels.

## 2. Frozen protocol

Written and hashed **before** the telemetry harness computed any
outcome (`docs/liquidity_pool_touch_volume_train_protocol.md`).
Recorded there in full: the Touch Episode definition (candle-overlap
state machine on completed 15m candles, current effective zone
geometry, creation-candle and sweep-candle exclusions, frozen 0/1/2/3+
buckets), the Volume definition (1-minute zone-overlap proxy, explicitly
disclosed as approximate; a new causal trailing-median relative-volume
baseline — `lookback_minutes=240`, `min_warmup=240` — since no existing
point-in-time *trailing* convention exists in this repository;
`strategy/features/volume_profile.py`'s own `relative_volume` is a
different, same-period cross-sectional figure, confirmed by reading
that module directly), the reused directional first-passage endpoint,
the fixed 32-bar population-conversion observation horizon, censoring
conventions, the S001 exact-linkage method, and the full decision rule
for both hypotheses.

## 3. Implementation and tests

Four new research modules, 31 new tests, all passing; full suite
**1060 passed, 0 failed**.

- `strategy/research/liquidity_pool_touch_episodes.py` —
  `candle_overlaps_zone`, `classify_touch_episodes`,
  `touch_count_bucket`. 13 tests, including creation-candle exclusion,
  one-episode-for-consecutive-overlap, leaving-and-returning-creates-a-
  second-episode, sweep-candle exclusion (including truncating an
  in-progress episode at the bar before the sweep), and
  current-effective-geometry (not creation-time-fixed) behavior.
- `strategy/research/liquidity_pool_touch_volume.py` —
  `relative_volume_series` (causal trailing median), `bucket_1m_candles`,
  `zone_overlapping_1m_indices`, `candle_zone_volume`,
  `candle_zone_relative_volumes`. 12 tests, including two direct
  no-lookahead proofs (`test_relative_volume_uses_only_strictly_prior_candles`,
  `test_changing_a_future_candle_does_not_change_an_earlier_relative_volume`)
  and a zero-contribution proof for non-overlapping 1m candles.
- `strategy/research/liquidity_pool_touch_volume_telemetry.py` — pure
  `assemble_pool_telemetry`, combining episodes + volume + the reused
  Wick-Extremity touch ledger into one per-pool record. 7 tests,
  including formation-contributors-independent-of-episode-count,
  explicit censoring, exact source/pool-identity, sweep-volume-kept-
  separate, and determinism.
- `tests/test_liquidity_pool_touch_volume_integration.py` — one
  integration test replaying the real `EqualLevelsTracker`/
  `SessionBoundariesTracker`/`LiquidityPoolTracker`/`LiquiditySweepReversalSetup`
  chain twice (with and without this sprint's telemetry machinery
  running alongside it) and asserting **byte-identical** S001
  `fired`/`direction` results and tracker snapshots bar-by-bar either
  way — the mechanism that determines every downstream trade.

All 14 required causal tests are covered by this set (mapped 1:1 in the
commit's own test files); the touch ledger itself
(`strategy/research/liquidity_pool_wick_extremity_ledger.py`) is reused
**unchanged** from the completed Wick-Extremity sprint, where it was
already proven to leave `LiquidityPoolTracker.snapshot()` byte-identical
(`test_production_output_byte_identical_with_and_without_ledger`) — not
re-proven here, only re-used.

## 4. Replay-safety proof

- Touch episodes use only bars already elapsed by the time an episode
  boundary is decided (`classify_touch_episodes` takes an already-ordered,
  already-causal `bars` list; the harness reconstructs each bar's zone
  bounds from the touch ledger's own chronological, bar-indexed
  entries — never a later touch's boundary).
- 1-minute zone-volume is attributed only from candles within the 15m
  bar's own `[T, T+15min)` window, all of which have already completed
  by the time that 15m bar itself closes.
- Relative volume is a strictly-trailing statistic (`i < min_warmup` →
  `None`; window is `[i-lookback, i)`, never including `i` or later) —
  proven directly by two dedicated tests, not merely asserted.
- The sweep candle and the pool's own creation candle are excluded from
  pre-sweep touch/volume accounting in every code path, not just by
  convention.

## 5. Event population and conversion tables

Fixed 32-bar observation-horizon exclusion applied per the frozen
protocol: 70 of 5,041 pools (1.4%) were created within 32 bars of their
month's own end and are excluded from conversion-rate denominators
(never from raw creation counts).

| Month / source | n | Swept % | Conversion rate (fixed horizon) | Touch buckets (0/1/2/3+) | Median age at sweep | Median touch-volume intensity |
|---|---|---|---|---|---|---|
| 2024-02 / round_number_only | 1,132 | 96.2% | 97.2% | 542/417/122/51 | 3 bars (0.75h) | 1.67 |
| 2024-02 / round_number_mixed | 38 | 89.5% | 89.5% | 18/15/3/2 | 2 bars | 1.71 |
| 2024-02 / non_round_number | 38 | 92.1% | 92.1% | 26/5/3/4 | **42 bars (10.5h)** | **2.88** |
| 2024-04 / round_number_only | 1,177 | 95.5% | 95.7% | 562/448/118/49 | 3 bars | 1.59 |
| 2024-04 / round_number_mixed | 31 | 87.1% | 87.1% | 15/9/6/1 | 5 bars | 1.83 |
| 2024-04 / non_round_number | 25 | 88.0% | 88.0% | 12/9/2/2 | **22 bars (5.5h)** | **3.32** |
| 2024-09 / round_number_only | 1,293 | 96.3% | 96.6% | 640/463/138/52 | 3 bars | 1.74 |
| 2024-09 / round_number_mixed | 47 | 87.2% | 87.2% | 18/21/7/1 | 7 bars | 1.74 |
| 2024-09 / non_round_number | 23 | 91.3% | 91.3% | 14/4/4/1 | **22 bars (5.5h)** | **3.53** |
| 2025-12 / round_number_only | 1,156 | 97.3% | 97.6% | 581/412/107/56 | 3 bars | 1.86 |
| 2025-12 / round_number_mixed | 56 | 91.1% | 91.1% | 32/16/5/3 | 5 bars | 2.63 |
| 2025-12 / non_round_number | 25 | 88.0% | 88.0% | 13/9/1/2 | **10 bars (2.5h)** | **4.40** |

**Consistent pattern across all 4 months**: non-round-number pools take
roughly **4–14× longer** to sweep (median 10–42 bars vs. 2–3 bars for
round-number-only) and show **markedly higher** median touch-volume
intensity (2.88–4.40 vs. 1.57–1.86). This is a genuine, consistent
structural difference between source types — but it is a **description
of the population**, not evidence for either hypothesis on its own
(Section 6 tests whether it translates into a directional edge).

Per direction (pooled): buy_side 2,520 pools, 96.0% swept; sell_side
2,521 pools, 95.8% swept — no material asymmetry.

Median confirmation→first-touch and last-touch→sweep lags (pooled,
pools with ≥1 episode, n=2,568/5,041): **1 bar (15 minutes)** each —
most touch activity, when it occurs at all, happens immediately
adjacent to pool formation and immediately before sweep, not spread out
over a long dwell.

Right-censoring (never swept, and not `insufficient_observation_window`):
the remainder of each month/source cell not accounted for by "swept" —
disclosed in every denominator above (`n − n_swept − n_insufficient`),
never dropped silently.

## 6. Touch Count directional analysis

Primary endpoint (+1 ATR / −1 ATR), pooled across all sources, 4 TRAIN months:

| Bucket | n pools | Favorable rate | n resolved |
|---|---|---|---|
| 0 | 2,473 | 49.7% | 2,365 |
| 1 | 1,828 | 50.8% | 1,743 |
| 2 | 516 | 49.2% | 498 |
| 3+ | 224 | 49.8% | 213 |

**Maximum pooled spread: 1.6 percentage points (50.8% − 49.2%)** — far
below the frozen 5-point promotion threshold, and **not monotonic**
(the sequence is flat–up–down–flat, not a trend). Per-month detail
(2024-02: 53.0/50.2/48.4/54.9; 2024-04: 50.2/53.7/47.1/45.1; 2024-09:
46.3/49.6/50.3/54.0; 2025-12: 49.7/49.6/50.9/45.9) shows the bucket
ranking **reshuffles every month** — no bucket is consistently
strongest or weakest across 3 of 4 months. Secondary endpoint (+2/-1
ATR) is equally flat (34.5%/35.5%/32.2%/35.1%). Per-direction
breakdown shows buy_side bucket=3+ at 60.2% (n=103) against sell_side
bucket=3+ at 40.0% (n=110) — a large divergence that **cancels out** in
the pooled figure, itself evidence the pooled near-flatness reflects
genuine noise around zero effect rather than two offsetting real
effects (if it were a real, source- or direction-specific effect, the
frozen decision rule's criterion 4 would disqualify it as a
single-direction artifact regardless). Round-Number-ONLY vs.
non-Round-Number breakdowns are both individually flat as well (spread
≤2pp for round_number-only across all 4 buckets; non-round-number's
somewhat larger spread, e.g. 3+ at 56.3% vs. 0 at 45.2%, sits on n=16 in
the 3+ cell — too small to treat as a real effect and not replicated
consistently month-to-month within that already-small subgroup).

## 7. Volume directional analysis

**Continuous association**: mean touch-volume intensity was 3.082 among
favorable outcomes (n=1,231) vs. 2.883 among adverse outcomes (n=1,214)
— a small, likely-noise difference in the "wrong" direction to build a
promotable signal from (higher intensity associated with slightly more
favorable outcomes, but the gap is a fraction of the underlying
variable's own spread).

**Outcome-blind quartile buckets** (pooled, swept pools with a defined
touch-volume intensity, n=2,455; cut points Q1=1.087, median=1.737,
Q3=3.098):

| Quartile | n pools | Favorable rate | n resolved |
|---|---|---|---|
| Q1 (low) | 614 | 51.0% | 608 |
| Q2 | 614 | 48.8% | 613 |
| Q3 | 613 | 49.3% | 611 |
| Q4 (high) | 614 | 52.4% | 613 |

**U-shaped, not monotonic** (spread 3.6pp, below the 5-point
threshold). Per-month detail shows the pattern is **not stable**: 2024-02
has Q4 as the *lowest* bucket (47.9%); 2024-09 and 2025-12 have Q4 as
the *highest* (55.8%/56.7%). A relationship that flips which bucket is
strongest between months is exactly the "results conflict materially
across months" pattern the frozen protocol treats as disqualifying.

**Touch-Count-controlled** (isolating Volume within `touch_count_bucket="1"`
only, to remove the Touch Count/Volume confound the protocol
specifically flagged): low-volume half 50.1% (n=866) vs. high-volume
half 51.4% (n=868) — **1.3-point gap, effectively no effect once Touch
Count is held constant.**

**Round-Number-controlled**: round-number-only pools (94%+ of the
population) show **essentially zero** volume effect — 50.3% vs. 50.3%
(0.04-point gap, n≈1,160 each half). Non-round-number pools show a
larger gap (43.75% vs. 57.8%, n=64/65) — but this sits on a tiny sample
that is *also* the source with the most extreme median volume intensity
already (Section 5), and per the frozen protocol's Volume-specific
requirement ("it must remain after accounting for Touch Count, pool
age, direction, or source" and "not explained by one... source"), an
effect that appears only in the smallest, most source-concentrated
slice — while vanishing almost completely in the 94%-majority
round-number population — is disqualifying by construction, not
promotable evidence.

## 8. Independence / confounding analysis

Touch Count and Volume were evaluated as fully separate hypotheses
throughout (Sections 6 and 7 use independent bucketing; no combined
score was ever computed). The one place they interact is by
construction: `mean_relative_touch_volume_intensity` is only defined
for pools with ≥1 touch episode, so `touch_count_bucket="0"` pools
(2,473 of 5,041, 49.1%) contribute no Volume observation at all — this
is disclosed directly, not treated as missing-at-random or imputed.
Controlling Volume for Touch Count (Section 7) and for source (Section
7) both **weakened rather than strengthened** any apparent Volume
effect, the opposite of what would be needed to support promotion.

## 9. Exact S001 results

Reused the proven method unchanged: 61/61 real TRAIN trades exactly
linked to `pool_id`, 0 unmatched, across all 4 months (15+16+19+11).

| Touch Count bucket | n | Win rate | PF | Net P&L | Expectancy |
|---|---|---|---|---|---|
| 0 | 46 | 34.8% | 0.81 | −$670.71 | −$14.58 |
| 1 | 13 | 30.8% | 0.66 | −$359.46 | −$27.65 |
| 2 | 1 | 100% | n/a | +$179.69 | +$179.69 |
| 3+ | 1 | 100% | n/a | +$177.56 | +$177.56 |

| Volume quartile | n | Win rate | PF | Net P&L | Expectancy |
|---|---|---|---|---|---|
| Q1 (low) | 5 | 40.0% | 1.01 | +$4.83 | +$0.97 |
| Q2 | 0 | — | — | — | — |
| Q3 | 5 | 60.0% | 2.22 | +$292.81 | +$58.56 |
| Q4 (high) | 5 | 20.0% | 0.37 | −$299.84 | −$59.97 |

**Both cross-tabs are far too small to support any conclusion.**
Touch-Count buckets 2 and 3+ have exactly one trade each (100% win rate
on n=1 is not evidence of anything). Volume quartiles have only 15 of
61 trades classified at all (bucket=0 pools, 46 of 61 trades, have no
defined touch-volume intensity by construction — zero pre-sweep
episodes). Per the frozen protocol ("treat S001 results as secondary if
group sizes are small; do not derive a threshold from a handful of
trades"), **this S001 evidence is not used to support or oppose either
verdict** — it neither materially contradicts nor confirms the
module-level result, which rests on samples one to two orders of
magnitude larger.

## 10. Sample-size, overlap, and censoring limitations

- The ~70-unique-level effective sample size (Section 1) applies to
  every aggregate figure in Sections 5–7 that is dominated by
  round-number pools — the true number of independent price levels
  behind the 2,473-pool bucket=0 population, for example, is a small
  fraction of 2,473.
- Non-round-number and multi-source cells are small in absolute terms
  (23–56 pools per month per cell) even though round-number-only cells
  are large (1,132–1,293) — per-source breakdowns for non-round-number
  pools should be read as suggestive population description (Section
  5), not a statistically powered comparison.
- Right-censored pools are included in every population/conversion
  denominator explicitly (Section 5) and excluded from every directional
  first-passage rate (they contribute no resolved outcome) — never
  conflated.
- 70 pools (1.4%) were excluded from conversion-rate denominators for
  insufficient observation window; none were excluded from raw creation
  counts or from the directional analysis's population entirely (a
  late-created pool that *did* sweep within the dataset still
  contributes a resolved directional outcome).

## 11. Verdicts

### Touch Count: **DO NOT PROMOTE**

The pooled primary-endpoint spread (1.6 points) is far below the
frozen 5-point threshold, the relationship is not monotonic, and the
bucket ranking is not stable across TRAIN months (criterion 2 — same
direction in ≥3/4 months — fails outright, since the ranking changes
every month). The secondary endpoint and per-direction/per-source
breakdowns corroborate a genuine null result rather than an underpowered
one: the sample sizes (2,473/1,828/516/224 pools) are large, and the
result is a stable, confident "no detectable effect," not noise from
too few observations.

### Volume: **DO NOT PROMOTE**

The pooled quartile spread (3.6 points) is below the 5-point threshold
and is U-shaped, not monotonic; the direction of the effect **flips**
between TRAIN months (2024-02 vs. 2024-09/2025-12), failing the
same-direction-in-≥3/4-months criterion directly. The frozen
Volume-specific requirement — the effect must survive controlling for
Touch Count and source — fails explicitly: controlling for Touch Count
collapses the gap to 1.3 points, and controlling for source shows the
94%-majority round-number population has essentially **zero** volume
effect (0.04-point gap), with the only sizeable gap confined to the
smallest, least-powered subgroup (non-round-number, n≈65 per half) —
exactly the single-source artifact the decision rule is written to
exclude.

Neither hypothesis is classified `INCONCLUSIVE`: both were tested on
large, stable, well-populated samples that produced a clear, consistent
null result rather than a conflicting or underpowered one.

## 12. Recommended next step

No production change, no combined Count+Volume rule, no new
data-partition access, and no further module work — per the authorizing
instructions, this sprint stops here. The completed Liquidity Sweep /
Liquidity Pool research series (Lifecycle Policy B/C, Staleness
Telemetry, Wick-Extremity Zone, and this Touch Count/Volume sprint) has
now tested lifecycle policy, staleness filtering, sweep geometry, and
pre-sweep interaction count/volume against Policy A's own real
production behavior, with every promotion candidate either rejected or
found inconclusive on rigorous, pre-registered TRAIN evidence and
Policy A kept unchanged throughout. Recommending the next research
direction is left to the user's own judgment on where to focus next
(e.g. CVD/Delta, FVG/IFVG, S008, or portfolio-level work, all explicitly
out of scope for this sprint).

---
Deliverables (all uncommitted, awaiting approval):
`docs/liquidity_pool_touch_volume_train_protocol.md` + `.sha256`,
`strategy/research/liquidity_pool_touch_episodes.py`,
`strategy/research/liquidity_pool_touch_volume.py`,
`strategy/research/liquidity_pool_touch_volume_telemetry.py`,
`tests/test_liquidity_pool_touch_episodes.py`,
`tests/test_liquidity_pool_touch_volume.py`,
`tests/test_liquidity_pool_touch_volume_telemetry.py`,
`tests/test_liquidity_pool_touch_volume_integration.py`, this report.
Full test suite: 1060 passed, 0 failed.
