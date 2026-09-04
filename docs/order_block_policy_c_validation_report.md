# Order Block Hybrid Policy C — SOL VALIDATION Experiment Report

**Final recommendation: KEEP POLICY A.**

This reverses the TRAIN addendum's recommendation to promote Policy C to
VALIDATION testing. The addendum's headline evidence (75–89%
original-direction favorability at horizon ≥4 bars) was
survival-conditioned, exactly as flagged before this experiment began.
The frozen, unconditional, competing-risks protocol applied here — to
both VALIDATION *and*, for comparison, TRAIN — shows the opposite
picture. No production behavior was changed.

## 1. Frozen validation protocol and hash

Protocol written and saved to `docs/order_block_policy_c_validation_protocol.md`
**before** any VALIDATION data was loaded. SHA-256 (computed immediately
after saving, before data access):

```
514886b978056b6e941280ad8ec52bea1b02c3aeb572449f6ab7ae1be15c2d2f
```

Recorded in `docs/order_block_policy_c_validation_protocol.sha256`.
Re-verified via `sha256sum -c` immediately before writing this report —
**confirmed unchanged** (`order_block_policy_c_validation_protocol.md: OK`).
The protocol was not altered after results were seen.

## Git/research checkpoint

1. `git status` before this experiment: clean (TRAIN research sprint had
   just been committed).
2. TRAIN's exact files (`strategy/research/`, `tests/test_order_block_lifecycle_policy_b.py`,
   both TRAIN report docs) confirmed via `git status`.
3. Committed as `43f9bc2` ("Order Block Lifecycle Research: Policy B/C
   candidate + SOL TRAIN evidence").
4/8. No unrelated files included; nothing pushed, merged, rewritten, or
   reverted; production default (Policy A) unchanged throughout.
5. Commit hash: `43f9bc2`.
6/7. This experiment's own protocol (Section 1) was written, saved, and
   hashed before any VALIDATION file was opened.

This experiment's own new files remain **uncommitted**, per the
established pattern (commit only when asked).

## 2. Exact event and de-duplication definitions

Both frozen and unchanged from `docs/order_block_policy_c_validation_protocol.md`
(Sections "Frozen event definition" and "Frozen de-duplication rule") —
not restated here in full; see that file. In summary: the event is the
first candle where wick-based mitigation reaches 100% while the close
remains on the non-invalidated side (`PolicyBOrderBlockState.wick_full_traversal_reclaimed`'s
first transition, unmodified from TRAIN); de-duplication clusters
same-direction events with overlapping zones within 20 bars of each
other, keeping the earliest (`traversal_bar_i`) as representative —
structural-identity/timing only, never price outcome.

## 3. Tests for the validation harness

15 new tests in `tests/test_order_block_policy_c_validation.py`, written
and passing against **synthetic** candle data before any VALIDATION file
was opened: `first_passage_outcome`'s favorable-first, invalidation-first,
same-bar-ambiguous (counted conservatively as invalidation), censored,
bearish symmetry, no-same-event-candle-credit, early-invalidation-not-discarded,
and threshold-parameterization cases; `deduplicate_events`'s
overlap-clustering, non-overlap-separation, time-gap-separation,
direction-isolation, multi-event chaining, and determinism cases.

## 4. Full-suite result

**933/933 passing** (918 TRAIN-sprint baseline + 15 new).

## 5. Complete-cohort first-passage table (primary endpoint: +1.0 ATR favorable vs. close-invalidation, first to occur)

**De-duplicated (primary) results, by month:**

| Month | Regime | n (dedup) | Favorable-first | Invalidation-first | Favorable rate | 95% CI (Wilson) |
|---|---|---:|---:|---:|---:|---|
| 2024-11 | strong bull | 102 | 40 | 62 | 39.2% | [30.3%, 48.9%] |
| 2024-08 | strong bear | 108 | 44 | 64 | 40.7% | [31.9%, 50.2%] |
| 2024-10 | low-vol/directionless | 121 | 50 | 71 | 41.3% | [32.9%, 50.2%] |
| 2025-05 | range/low-vol | 136 | 59 | 77 | 43.4% | [35.3%, 51.8%] |
| **Pooled** | | **467** | **193** | **274** | **41.3%** | **[36.9%, 45.8%]** |

Zero censoring occurred at the primary threshold in any VALIDATION
month (every event resolved to favorable or invalidation before month
end) — see Section 6 for the pure (threshold-independent) censoring
rate, which is small but non-zero (2.1%).

**Raw (non-de-duplicated) results are consistent** with the primary,
de-duplicated result: pooled raw favorable rate 41.1% (239/582) vs.
pooled de-duplicated 41.3% (193/467) — de-duplication does not change
the conclusion, it only corrects the sample-size/independence claim.

**By direction (de-duplicated, pooled):** bullish 41.0% (102/249
resolved), bearish 41.7% (91/218 resolved) — no directional asymmetry.

**Invalidation wins the unconditional race in every single VALIDATION
month, at a consistent ~57–61% rate**, and in both directions. This
directly fails promotion criterion 1 ("+1 ATR before close invalidation
favors the original-direction interpretation") in all four months, not
just on average.

## 6. Time-to-event and censoring table

| | n | Median (bars) | P25 | P75 |
|---|---:|---:|---:|---:|
| Time to +1.0 ATR favorable (when it wins) | 193 | 2 | 1 | 3 |
| Time to invalidation (when it wins the race) | 274 | 1 | 1 | 2 |
| Pure time-to-invalidation (regardless of the +1ATR race, threshold-independent) | 457 | 3 | — | — (max 1,385 bars ≈ 14.4 days) |

**Pure censoring rate** (event never resolves to invalidation by
month-end, independent of the +1ATR threshold): 10/467 (2.1%) — small,
consistent with TRAIN's 3.6% censoring rate.

**Invalidation, when it wins, resolves faster (median 1 bar) than
favorable does (median 2 bars)** — the opposite of what would be needed
to support Policy C's premise that waiting is usually rewarded quickly.

**Status at each horizon (complete cohort, no survivor conditioning),
de-duplicated pooled:**

| Horizon | Invalidated by then | Not yet invalidated | n with data |
|---:|---:|---:|---:|
| 1 | 163 | 304 | 467 |
| 2 | 214 | 253 | 467 |
| 4 | 263 | 204 | 467 |
| 8 | 314 | 153 | 467 |
| 16 | 348 | 119 | 467 |
| 32 | 379 | 87 | 466 |

Every event is retained in this table's denominator at every horizon
(per protocol) — this is *not* the survivor-conditioned table from the
TRAIN addendum. "Not yet invalidated" includes both events that already
resolved favorably and events still unresolved either way; it is not
itself a claim of favorable outcome.

**Secondary thresholds (de-duplicated, pooled):**

| Threshold | Favorable-first | Invalidation-first |
|---|---:|---:|
| +0.5 ATR | 247 (52.9%) | 220 (47.1%) |
| +1.0 ATR (primary) | 193 (41.3%) | 274 (58.7%) |
| +2.0 ATR | 130 (27.8%) | 337 (72.2%) |

The favorable rate **monotonically decreases** as the required favorable
threshold increases — exactly what would be expected if invalidation
tends to arrive before large favorable moves have time to develop, not
evidence of a hidden favorable-direction edge at a different threshold.

**New favorable structural break before invalidation**: 149/467 (31.9%)
— a minority, not the majority needed to argue that continuation
structure reliably develops before invalidation.

## 7. Raw versus de-duplicated results

Already presented inline in Section 5 — raw and de-duplicated results
agree closely (41.1% vs. 41.3% pooled favorable rate); the conclusion
does not depend on which is used. De-duplicated is treated as primary
per the frozen protocol.

**Residual dependence / cluster-size distribution:**

| Month | Clusters | Singleton clusters | Max cluster size | Mean cluster size |
|---|---:|---:|---:|---:|
| 2024-11 | 102 | 81 (79.4%) | 4 | 1.24 |
| 2024-08 | 108 | 84 (77.8%) | 4 | 1.28 |
| 2024-10 | 121 | 97 (80.2%) | 3 | 1.21 |
| 2025-05 | 136 | 107 (78.7%) | 4 | 1.26 |

Most clusters (78–80%) are singletons; the residual dependence from the
remaining ~20–22% multi-member clusters is modest (max cluster size 3–4)
and does not materially inflate the apparent sample size — de-duplication
removes real but limited over-counting, consistent with TRAIN's own
~15–18% raw-to-dedup reduction.

## 8. Per-regime and per-direction results

Already tabulated in Section 5. The ~57–61% invalidation-first rate is
**consistent across all four VALIDATION regimes** (strong bull, strong
bear, low-vol/directionless, range/low-vol) and **both directions** —
this is not a one-month, one-regime, or one-direction effect. Per the
frozen promotion criteria, such cross-regime consistency would have
supported promotion had the direction of the effect favored Policy C —
here the same consistency instead supports `KEEP POLICY A` decisively,
since the consistent finding runs the other way.

## 9. Ambiguity sensitivity

Only 1 of 467 de-duplicated events had an ambiguous same-bar resolution
(both +1ATR favorable and close-invalidation true on the same candle).
Excluding it: favorable rate moves from 41.3% (193/467, with ambiguous
counted conservatively as invalidation) to 41.4% (193/466, excluded
entirely) — an immaterial difference. The conclusion is fully robust to
same-bar handling.

## 10. TRAIN-versus-VALIDATION comparison

The exact same frozen `first_passage_outcome`/`deduplicate_events`
functions were applied to the 4 SOL TRAIN months, for direct comparison
(not a new analysis choice — reusing the identical, already-tested,
unmodified code):

| | TRAIN (2024-02/04/09, 2025-12) | VALIDATION (2024-11/08/10, 2025-05) |
|---|---:|---:|
| Pooled de-duplicated n | 466 | 467 |
| Favorable-first | 195 (41.8%) | 193 (41.3%) |
| Invalidation-first | 271 (58.2%) | 274 (58.7%) |

**TRAIN-to-VALIDATION degradation is negligible (41.8% → 41.3%, 0.5
percentage points)** — well within noise. This is the single most
important finding of this whole experiment: **the TRAIN addendum's
apparent 75–89% original-direction-favoring result does not reflect a
real signal that failed to replicate — it never existed under the
correct, unconditional methodology, in TRAIN or VALIDATION.** Both
datasets show the same ~42% unconditional favorable-first rate; the
addendum's number was an artifact of measuring only the sub-population
that had already survived several bars without invalidating, which is
mechanically selected to look favorable regardless of the underlying
lifecycle policy.

## 11. HELD_OUT confirmation

**SOL FINAL HELD_OUT (2025-02, 2025-07) was never loaded or referenced
by any script in this experiment.** The harness asserts this explicitly
at runtime (`assert forbidden not in month` for every processed month
string) and only four VALIDATION month files
(`SOLUSDT-1m-2024-11.csv`, `-2024-08.csv`, `-2024-10.csv`,
`-2025-05.csv`) were opened, confirmed by the dataset hashes logged in
Section "config" output for each month. No BTC data was used for any
model-selection decision in this experiment.

## 12. Final recommendation

**KEEP POLICY A.**

Evaluated literally against the frozen promotion criteria:
1. `+1 ATR before close invalidation favors the original-direction
   interpretation` — **fails**: invalidation wins 58.7% vs. 41.3% in the
   de-duplicated pooled cohort.
2. `Direction consistent in ≥3 of 4 VALIDATION months` — the effect
   (invalidation winning more often) is consistent in **all 4** months,
   but in the direction that supports Policy A, not Policy C.
3. `Not driven by one month, direction, or a few clusters` — confirmed;
   consistent across regimes, directions, and robust to raw vs.
   de-duplicated framing.
4. `Survives conservative same-bar handling` — confirmed (Section 9),
   though moot here since the result already fails criterion 1.
5. `Policy C does not retain a large population of stale blocks for
   impractically long periods` — **partially concerning**: while only
   2.1% are ever censored, the pure time-to-invalidation distribution has
   a long tail (max 1,385 bars ≈ 14.4 days), meaning a real minority of
   Policy-C-"active" blocks would remain nominally un-invalidated for
   very long periods — an additional, independent reason for caution
   about Policy C, beyond the primary endpoint's own failure.
6. `TRAIN-to-VALIDATION degradation disclosed and acceptable` — disclosed
   in full (Section 10): degradation is negligible, but only because the
   TRAIN result being compared against was itself already not
   supportive under the correct methodology. There is no TRAIN evidence,
   correctly measured, that ever favored Policy C.

None of the conditions required to promote Policy C are met. This is a
clean `KEEP POLICY A` outcome, not `INCONCLUSIVE` — the evidence is
decisive and consistent, not mixed.

## 13. Exact next action requiring approval

**None requested.** Per the production-promotion boundary already
established, Policy C is not implemented in production, and this report
does not ask for that. If a future, separately-scoped research question
wants to revisit Order Block lifecycle semantics, it should start from
the honest baseline this experiment establishes — the wick-based,
immediate-mitigation framing (Policy A) is not empirically outperformed
by a close-confirmation delay, at least not via this specific `+1.0 ATR`
/ far-boundary-close formulation, on either TRAIN or VALIDATION SOL data.
No implementation change is proposed. Not moving to Liquidity Sweep,
S008, or any other sprint. HELD_OUT remains untouched for a genuine
future final check, whenever that becomes appropriate.

---

**Production default remains Policy A, unchanged throughout this
experiment.**
