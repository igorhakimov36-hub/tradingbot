# Liquidity Sweep Staleness Telemetry — Secondary Validation Report

**Final verdict: KEEP POLICY A.**

The corrected research question — are Policy A sweeps that occur only
after a pool has remained beyond its boundary for more than 16 completed
bars (`LATE_RECLAIM`) materially weaker than timely sweeps — is answered
clearly and consistently: **no.** `LATE_RECLAIM` sweeps show directional
first-passage performance statistically indistinguishable from (and in
half the tested months, slightly better than) `TIMELY_RECLAIM` and
`SAME_CANDLE_SWEEP` sweeps, stable across all three sensitivity windows.
This directly fails the mandatory first condition for promotion. No
production behavior was changed.

## Architecture decision

A research-only observer was used, not a permanent addition to
`strategy/features/liquidity_pool.py`. Recorded in full in
`strategy/research/liquidity_pool_staleness_telemetry.py`'s own module
docstring: adding new, additive snapshot keys to production would also
have been non-breaking, but this remains a hypothesis-validation sprint,
not an implementation-authorization one — every prior sprint in this
series (Order Block Policy B/C, Liquidity Pool Policy B/C) kept the
identical zero-production-footprint boundary, and this sprint keeps it
too. `strategy/features/liquidity_pool.py` is touched only by a direct,
read-only test confirming Policy A's own behavior is unaffected.

## Frozen protocol and hash

`docs/liquidity_pool_staleness_secondary_validation_protocol.md`,
written and hashed before any SECONDARY_VALIDATION file was opened.
SHA-256:

```
209bbf7b081750cf467352286e47324b643bc481e4dba1ce2341d28203a4bf5b
```

Re-verified via `sha256sum -c` immediately before writing this report —
**confirmed unchanged**.

## Exact month-access log

**Proposed and used**: 2024-03, 2024-06, 2025-04, 2025-09. Verified
*before* the protocol was frozen: `docs/out_of_sample_validation_report.md`
references 2024-03/2024-06 only as a **pre-SOL-pivot BTC** table,
unrelated to Liquidity Pool/S001 analysis on any symbol.
`docs/phase5_strategic_roadmap_decision.md` references all four months
only in its price-derived regime table (Section 1.4), explicitly
documented there as computed with zero strategy or setup evaluation. No
prior TRAIN (2024-02/04/09, 2025-12) or VALIDATION (2024-11/08/10,
2025-05) artifact from this project's own research references any of
these four months. **Confirmed: none was previously used for Liquidity
Pool lifecycle or S001 staleness outcome analysis.**

**FINAL_HELD_OUT (2025-02, 2025-07) was never accessed** — asserted at
runtime on every processed month string, exactly as in the two prior
VALIDATION experiments.

## Complete category counts (de-duplicated, window=16)

| Month | Raw | Dedup | SAME_CANDLE_SWEEP | TIMELY_RECLAIM | LATE_RECLAIM | UNRESOLVED_OR_CENSORED |
|---|---:|---:|---:|---:|---:|---:|
| 2024-03 | 2,541 | 2,540 | 1,125 (44.3%) | 1,023 (40.3%) | 291 (11.5%) | 101 (4.0%) |
| 2024-06 | 785 | 785 | 321 (40.9%) | 302 (38.5%) | 118 (15.0%) | 44 (5.6%) |
| 2025-04 | 1,601 | 1,600 | 661 (41.3%) | 628 (39.3%) | 238 (14.9%) | 73 (4.6%) |
| 2025-09 | 1,073 | 1,073 | 423 (39.4%) | 445 (41.5%) | 157 (14.6%) | 48 (4.5%) |

Raw-vs-dedup reduction is 0–0.06% in every month — consistent with
every prior Liquidity Pool sprint's own finding that pool formation's
own tolerance-based clustering already prevents meaningful overlap.

## Module-level first-passage results (primary: ±1 ATR, window=16, de-duplicated)

| Category | n | Favorable | Adverse | Censored | Favorable rate (of resolved) | Median MFE | Median MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| `SAME_CANDLE_SWEEP` | 2,530 | 1,286 | 1,231 | 13 | 51.1% | 2.395 ATR | 2.217 ATR |
| `TIMELY_RECLAIM` | 2,398 | 1,181 | 1,211 | 6 | 49.4% | 2.208 ATR | 2.366 ATR |
| `LATE_RECLAIM` | 803 | 408 | 394 | 1 | 50.9% | 2.320 ATR | 2.328 ATR |

**`LATE_RECLAIM`'s favorable rate (50.9%) is not lower than either
`SAME_CANDLE_SWEEP` (51.1%) or `TIMELY_RECLAIM` (49.4%)** — all three are
within ~1.7 percentage points of each other and of a coin flip. MFE/MAE
(explicitly descriptive independent extrema, **not** simulated
profitability — each is its own running maximum over the fixed horizon,
not a sequential trade outcome) show the same pattern: all three
categories cluster tightly around 2.2–2.4 ATR for both.

**Per month:**

| Month | SAME favorable% | TIMELY favorable% | LATE favorable% |
|---|---:|---:|---:|
| 2024-03 | 52.1% | 48.9% | 46.2% |
| 2024-06 | 46.9% | 50.2% | 49.2% |
| 2025-04 | 52.4% | 51.0% | **54.9%** |
| 2025-09 | 49.5% | 47.5% | **54.8%** |

`LATE_RECLAIM` underperforms both other categories in only **1 of 4**
months (2024-03, by 2.7 points); it is the **best**-performing category
in 2 of 4 months (2025-04, 2025-09); roughly tied in 2024-06. This
directly fails the promotion rule's own explicit bar ("worse... in at
least 3 of 4 months").

**Secondary endpoint (+2 ATR favorable vs. −1 ATR adverse, window=16,
pooled):** `SAME_CANDLE_SWEEP` 33.1%, `TIMELY_RECLAIM` 32.1%,
`LATE_RECLAIM` 31.5% — again no meaningful separation (≤1.6 points).

**Per direction (window=16):** buy_side and sell_side both reproduce the
same no-degradation pattern (`LATE_RECLAIM` favorable rate 51.5%
buy_side / 50.3% sell_side, both ≥ or ≈ the other categories) — not a
one-direction artifact.

**Ambiguity** (same-bar favorable+adverse, counted conservatively as
adverse): 0.6% (`SAME_CANDLE_SWEEP`, `TIMELY_RECLAIM`), 1.1%
(`LATE_RECLAIM`) — immaterial to any of the above.

## Sensitivity analysis (windows 8/16/32)

| Window | LATE_RECLAIM n | LATE_RECLAIM favorable rate |
|---:|---:|---:|
| 8 | 1,108 | 49.8% |
| 16 | 803 | 50.9% |
| 32 | 530 | 50.5% |

**Stable within a 1.1-point band across all three window sizes** — no
window shows `LATE_RECLAIM` materially underperforming, and the pattern
does not depend on which of the three pre-declared window sizes is used.
(`TIMELY_RECLAIM`'s own count shifts as expected — larger windows
reclassify some `LATE_RECLAIM` events as `TIMELY_RECLAIM` — but its own
favorable rate stays in the same 49.6–49.7% band throughout, and
`SAME_CANDLE_SWEEP` is unaffected by window choice by construction.)

## Exact S001 linkage proof

Reused the proven approach: `strategy_callback` instrumented to call the
real, unmodified `LiquiditySweepReversalSetup._find_fresh_sweep(snapshot)`
directly, keyed by the exact 1-minute `current_candle` timestamp;
`OPENED`/`CLOSED` paired by chronological order (`record_closed`'s own
timestamp is the exit time, not entry — already discovered and fixed in
the prior VALIDATION sprint). All required proofs asserted and held for
every one of the 4 months: `len(opened) == len(closed)`; both sequences
strictly monotonic in time; `side` and `entry_price` match within every
paired `(opened[i], closed[i])`; open time never after close time.
**Zero unmatched trades in any month** (92/92 total).

| Month | Closed | Exact links recorded | Unmatched |
|---|---:|---:|---:|
| 2024-03 | 44 | 44 | 0 |
| 2024-06 | 14 | 14 | 0 |
| 2025-04 | 20 | 20 | 0 |
| 2025-09 | 14 | 14 | 0 |

**A material, honest limitation**: every one of the 92 exactly-linked
S001 trades classified as `SAME_CANDLE_SWEEP` (71) or `TIMELY_RECLAIM`
(21) — **zero classified as `LATE_RECLAIM` in any of the 4 months.**
S001's own multi-condition gating (CVD confirmation plus ≥1 of
CHOCH/multi-source/SMT, on top of the raw sweep) evidently biases toward
fresher sweeps in this sample; this is not itself surprising, but it
means **the S001-specific comparison for `LATE_RECLAIM` specifically is
not possible with this data** — reported plainly rather than
substituted with an approximation.

## S001 performance tables (diagnostic only — NOT used to justify the verdict)

| Tag | n | Win rate | Total P&L | Avg P&L | PF | Avg win | Avg loss | Largest-winner contribution |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `SAME_CANDLE_SWEEP` | 71 | 32.4% | -1,417.65 | -19.97 | 0.74 | 178.80 | 115.21 | 4.8% |
| `TIMELY_RECLAIM` | 21 | 23.8% | -1,060.56 | -50.50 | 0.44 | 164.57 | 117.71 | **21.9%** |

Denominators stated explicitly: n=71 and n=21. Neither group is called
profitable or unprofitable here — both show PF<1 in this sample, but
**`TIMELY_RECLAIM`'s single largest winning trade contributes 21.9% of
its own total gross wins**, a concentration flag explicitly worth
disclosing rather than treating 21 trades as a stable estimate of
anything. No `LATE_RECLAIM` comparison exists (Section above). This
table is diagnostic only and does not inform the verdict below.

## Bias, overlap, censoring, and sample-size limitations

- Overlap: near-zero (0–0.06% raw-to-dedup reduction), consistent with
  every prior Liquidity Pool sprint.
- Censoring: 3.2–5.6% (`UNRESOLVED_OR_CENSORED`) per month — modest, not
  concentrated in any one month.
- Module-level sample sizes are large and adequate (803–2,530 per
  category at the primary window) — this part of the analysis is
  well-powered.
- S001-linked sample sizes are small (14–44 trades per month, only two
  of the three categories represented at all) — explicitly **not**
  adequate to independently confirm or contradict the module-level
  finding; treated as secondary and non-decisive throughout.

## Explicit comparison with the previous TRAIN and VALIDATION findings

**These are related but not the same measurement, stated precisely to
avoid conflation:** the prior TRAIN/VALIDATION Policy C experiments
measured "of pools where both Policy A and a *bounded Policy-C-style
state machine* eventually resolve, what fraction of the time does
Policy A's sweep occur strictly after Policy C would already have
invalidated the pool" — a comparison between two different *policies'*
resolution timing, which found ~94% (TRAIN 94.6%, VALIDATION 94.2%).
**This sprint measures something different**: directly splitting Policy
A's own real, actual sweeps by how many bars elapsed between first
close-beyond and the sweep itself, then asking whether the *late* half
of that split shows worse forward directional behavior than the *timely*
half. The ~94% figure from the prior sprints is not contradicted or
superseded by this sprint's finding — they answer different questions.
What this sprint newly establishes is that the earlier sprints'
implicit premise (that "late" necessarily means "lower quality") does
not hold up when tested directly and correctly: lateness by itself does
not predict weaker forward performance.

## Final verdict

**KEEP POLICY A.**

Applying the frozen decision rule literally: `PROMOTE POLICY C TO A
CONTROLLED PRODUCTION-CANDIDATE BACKTEST` requires, as its first and
mandatory condition, that `LATE_RECLAIM` show **worse** directional
first-passage results than timely sweeps, pooled *and* in at least 3 of
4 months. **The opposite is observed**: `LATE_RECLAIM` is statistically
indistinguishable from the other two categories pooled (50.9% vs.
51.1%/49.4%), underperforms in only 1 of 4 months, and is the
best-performing category in 2 of 4 months — coherent across all three
sensitivity windows (8/16/32), not a one-direction or one-source
artifact, and not driven by censoring or overlap. This is exactly the
condition the protocol names for `KEEP POLICY A`: "late sweeps are equal
or better." The evidence here is consistent and clear, not conflicting
or underpowered, so `INCONCLUSIVE` would understate what was found —
this sprint reaches a decisive answer, and that answer does not favor
treating sweep lateness as a signal-quality filter.

## Exact next action requiring approval

None. `KEEP POLICY A` does not authorize a controlled A-versus-C
backtest or any further implementation work. If a future research
question wants to test a genuinely different signal-quality hypothesis
for Liquidity Pool sweeps (e.g., penetration depth, source count, or
some other property established or considered in these sprints), it
would need its own, separately-scoped and separately-authorized
proposal — this sprint's own finding does not motivate one on its own.

---

**Production behavior remains unchanged throughout. FINAL_HELD_OUT was
not accessed. Not implementing Policy C in production, not testing Wick
Extremity or Touch Count/Volume, not beginning CVD/Delta or S008.**
