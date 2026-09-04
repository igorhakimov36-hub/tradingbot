# Liquidity Sweep Staleness Telemetry — Secondary Validation — Frozen Protocol

**Written and frozen BEFORE any SECONDARY_VALIDATION data is loaded.**
SHA-256 hash recorded immediately after saving, before any of the four
new month files are opened, and re-verified before the final report is
written.

## Corrected research question

The prior VALIDATION experiment asked whether Policy C detects sweeps
Policy A misses entirely — structurally impossible, since both share an
identical same-candle sweep condition (confirmed at exactly 0% there).
**This experiment asks a different, correct question**: are Policy A
sweeps that occur only after a pool has remained beyond its boundary for
more than 16 completed bars (`LATE_RECLAIM`) materially weaker, in
directional first-passage terms, than timely sweeps (`SAME_CANDLE_SWEEP`,
`TIMELY_RECLAIM`)? Policy C is evaluated here as a **candidate stale-signal
filter**, not as an alternative detector.

This document does not reinterpret or overwrite
`docs/liquidity_pool_policy_c_validation_report.md` — that report's
findings and verdict stand as delivered.

## Month-access log and verification

**Proposed SECONDARY_VALIDATION months**: 2024-03, 2024-06, 2025-04,
2025-09.

**Verification performed before this protocol was frozen**: searched
`docs/` for every occurrence of these four month strings.
- `docs/out_of_sample_validation_report.md` references 2024-03/2024-06 —
  a **pre-SOL-pivot BTC** out-of-sample table, unrelated to Liquidity
  Pool lifecycle or S001 staleness analysis on any symbol.
- `docs/phase5_strategic_roadmap_decision.md` references all four months
  in its Section 1.4 regime table — a **price-derived-only** table
  (open/close change %, range %, realized volatility), explicitly
  documented there as computed with "zero strategy or setup ever
  evaluated." Not a Liquidity Pool lifecycle or S001 outcome analysis.
- No TRAIN or VALIDATION pickle/report from this project's own Order
  Block or Liquidity Pool research sprints references any of these four
  months — TRAIN used 2024-02/04/09 and 2025-12; VALIDATION used
  2024-11/08/10 and 2025-05.

**Conclusion: none of the four proposed months has been previously used
for Liquidity Pool lifecycle or S001 staleness outcome analysis.**
Proceeding with all four as named. `SOLUSDT-1m-2024-03.csv`,
`-2024-06.csv`, `-2025-04.csv`, `-2025-09.csv` confirmed present on disk
before this protocol was frozen (not yet opened by any analysis script).

**FINAL_HELD_OUT (2025-02, 2025-07) is never accessed in this
experiment**, confirmed explicitly at runtime by the harness (an assert
on every processed month string), exactly as done in the two prior
VALIDATION experiments.

## Architecture decision (Step 1)

Recorded in full in `strategy/research/liquidity_pool_staleness_telemetry.py`'s
own module docstring: a research-only observer is used, not a
permanent, additive change to `strategy/features/liquidity_pool.py`. The
telemetry is driven entirely from the real, unmodified
`LiquidityPoolTracker`'s own snapshot output plus a companion,
externally-tracked bar-index timeline — it never adds fields to, or
otherwise touches, any production file. This preserves the exact
zero-production-footprint boundary every prior research sprint in this
series has kept, appropriate for a still-research (not
implementation-authorization) sprint.

## Frozen classification (four mutually exclusive categories)

Exactly as specified by the authorizing instructions and implemented in
`classify_staleness()`:
- `SAME_CANDLE_SWEEP`: Policy A's own sweep fires with no clean close
  beyond ever occurring strictly before the sweep candle.
- `TIMELY_RECLAIM`: a clean close beyond occurs, and Policy A's sweep
  confirms within 1–16 completed candles of it (bar 0 = the close-beyond
  candle; bar 1 = the next completed candle; 16 is inclusive).
- `LATE_RECLAIM`: same, but confirmation takes 17+ completed candles.
- `UNRESOLVED_OR_CENSORED`: Policy A's sweep never confirms before the
  dataset ends — never conflated with "accepted liquidity."

Counting convention (frozen, not renegotiated after seeing results):
bar 0 is the close-beyond candle itself; the pool's own creation candle
is excluded from sweep/close-beyond eligibility entirely (the corrected
origin-bar behavior from the prior VALIDATION sprint, reused unchanged
here — the harness skips each pool's own creation bar for both Policy A
bookkeeping and telemetry, exactly as fixed there).

## Frozen window parameters

- **Primary window: 16 completed 15-minute candles** (matches the
  classification boundary above).
- **Sensitivity windows: 8 and 32** — the classification function
  re-applied with `primary_window=8` and `primary_window=32`, changing
  only which bar-count separates `TIMELY_RECLAIM` from `LATE_RECLAIM`.
  Not optimized by P&L; not expanded beyond these two values after
  seeing results.

## Primary directional endpoint (frozen formulas)

For each de-duplicated pool with a confirmed Policy A sweep (any of the
three resolved categories), beginning with the candle immediately after
the sweep-confirmation candle:

- **ATR frozen at sweep confirmation**: the value of a standalone,
  point-in-time `AverageTrueRangeTracker` (period 14) at the sweep
  candle itself — never recomputed with a later candle.
- **Expected reversal direction**: a swept `buy_side` pool implies a
  SHORT/DOWN reversal; a swept `sell_side` pool implies a LONG/UP
  reversal — matching `LiquiditySweepReversalSetup`'s own existing
  direction mapping exactly (not a new convention).
- **Favorable** (buy_side): `reference_close - candle["low"] >= 1.0 * atr`.
  **Adverse** (buy_side): `candle["high"] - reference_close >= 1.0 * atr`.
  Sell_side mirrored.
- **Resolution**: first candle (in forward order) satisfying either
  condition wins; a candle satisfying **both** is conservatively counted
  as **adverse** (reported separately both ways as the ambiguity
  check). No resolution within the frozen maximum horizon (32 bars,
  matching the widest sensitivity window) is right-censored, not a win
  or loss.
- **No conditioning on survival to a later horizon** — every resolved
  sweep (of any category) enters the primary endpoint once, at its own
  confirmation, regardless of category.

## Secondary endpoints (frozen)

- `+2 ATR` favorable vs. `-1 ATR` adverse first passage (same sequential
  logic, only the favorable threshold changes).
- Time to favorable/adverse resolution (bars).
- MFE and MAE from the reference close, in ATR units — **explicitly
  labeled as descriptive independent extrema, not simulated
  profitability** (they are not first-passage/sequential; they are
  each direction's own running maximum over the fixed horizon).
- Reported: pooled; per month; per direction; per pool source; raw and
  de-duplicated (same frozen structural clustering rule as the two
  prior sprints — zone overlap + within-20-bar timing, same direction,
  earliest representative); censored-event counts at every breakdown.

## S001 exact linkage (frozen requirements)

Nearest-timestamp or approximate matching is **not** used. Linkage is
established by directly calling
`LiquiditySweepReversalSetup._find_fresh_sweep(snapshot)` — the exact,
unmodified, pure, read-only method the real `evaluate()` call already
uses — from inside an instrumented `strategy_callback` wrapper, keyed by
the exact 1-minute `current_candle` timestamp the trade journal itself
uses (not `sync_and_build`'s own 15m snapshot timestamp, which does not
align with entry timing 1:1 — the exact bug already found and fixed in
the prior VALIDATION sprint). `OPENED` and `CLOSED` journal records are
paired by chronological order (not by matching `record_closed`'s own
timestamp, which is the **exit** time, not entry — the second bug
already found and fixed in the prior sprint). Before trusting this
pairing, the harness asserts, per month:
- `len(opened) == len(closed)` (no orphaned open position at month end
  for this single-setup, standalone run).
- The two sequences are monotonically non-decreasing in time (a proxy
  for "only one trade can be open at a time," consistent with this
  project's own single-slot backtest engine).
- Each paired `(opened[i], closed[i])`'s side matches.
- Zero unmatched trades remain, or the exact count and reason for any
  exception is reported explicitly (not silently dropped).

## Decision rule (restated verbatim, frozen)

`PROMOTE POLICY C TO A CONTROLLED PRODUCTION-CANDIDATE BACKTEST` only if:
1. `LATE_RECLAIM` has worse directional first-passage results than
   timely sweeps (pooled AND in ≥3 of 4 months).
2. Same direction under 8/16/32 sensitivity.
3. Not created by censoring, overlap, one direction, one source, or a
   few outliers.
4. Exact-linked S001 evidence does not contradict it.
5. Sample sizes adequate and disclosed.

`KEEP POLICY A` if late sweeps are equal or better, or excluding them
would consistently remove valuable signals.

`INCONCLUSIVE` if sample sizes are insufficient, results conflict across
months/windows, or module-level and S001 evidence disagree materially.

This rule is not altered after results are seen.

---
FROZEN — SHA-256 of this file (computed over the file as saved, before
any SECONDARY_VALIDATION data was loaded): see
`docs/liquidity_pool_staleness_secondary_validation_protocol.sha256`
