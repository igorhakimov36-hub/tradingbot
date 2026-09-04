# Order Block Lifecycle Research — Wick Mitigation vs. Close-Confirmed Invalidation

**Recommendation: KEEP POLICY A (current production lifecycle).**

This is a research and decision sprint. No production behavior was changed.
`strategy/features/order_block.py` and `strategy/features/breaker_block.py`
are byte-for-byte unmodified by this sprint.

## Git checkpoint

1. `git status` before this sprint: clean (Module Logic Correction 2 had
   just been committed).
2. Correction 2's exact 8 files were confirmed via `git status`/`git diff --stat`
   before this sprint began.
3. Committed as `a87e5f9` ("Module Logic Correction 2: Order Block event
   identity and impulse-leg boundary").
4/5/7. No unrelated files included; nothing pushed, merged, rewritten, or
   reverted.
6. Working tree confirmed clean immediately before this sprint's first edit.

This sprint's own changes remain **uncommitted**, per this project's
established pattern.

## 1. Exact lifecycle definitions

**Policy A (current production control)** — documented, not reimplemented,
directly from `strategy/features/order_block.py`:
- Touch: OHLC wick overlap with `[zone_low, zone_high]` (`is_touching_zone`).
- Mitigation depth: continuous wick penetration (`compute_mitigation`),
  monotonically non-decreasing.
- `mitigation_pct >= 1.0` (reachable by a wick alone; close irrelevant) ==
  `mitigation_status == "fully_mitigated"`.
- Full mitigation moves the block from `active` to `mitigated` — a
  one-way, monotonic transition.
- `BreakerBlockTracker` consumes the `mitigated` list directly — no
  separate close confirmation required for breaker eligibility.

**Policy B (separated-lifecycle research candidate)**:
1. Touch — unchanged, still wick-based.
2. Mitigation percentage — unchanged, still wick-based, still carries
   useful depth information; no longer drives the active→retired
   transition by itself.
3. `mitigation_pct >= 1.0` alone does **not** confirm invalidation.
4. Invalidation requires a **close** beyond the Order Block's far
   boundary: bullish → `close < zone_low`; bearish → `close > zone_high`.
   Latches permanently once True (mirrors Policy A's own one-way
   `mitigation_status` transition, applied to a stricter trigger).
5. Breaker eligibility becomes True at the exact candle invalidation is
   confirmed — not at 100% wick mitigation.
6. A wick that fully traverses the zone and closes back inside is
   recorded as `mitigation_status == "fully_mitigated"` (shared,
   unchanged field) without `invalidated` becoming True.

**Invalidation boundary decision** (stated before implementation): the
**full Order Block boundary** (`zone_high`/`zone_low` — the same boundary
already used for touch/mitigation) was pre-registered as the **primary**
hypothesis. The tighter body/mitigation-zone boundary, and "both as
separate fields," are recorded as **exploratory alternatives**, not
implemented — see `strategy/research/order_block_lifecycle_policy_b.py`'s
own docstring for the full reasoning (the instruction's own phrase "the
Order Block's far boundary" maps to this codebase's `zone_high`/`zone_low`,
not the separately-named, narrower `mitigation_zone_*` fields; requiring a
close beyond the wider boundary is also the more conservative criterion,
consistent with correcting a "premature invalidation" concern in one
direction only). No multi-close confirmation or candle-count threshold was
introduced.

## 2. Research implementation and files

```
strategy/research/__init__.py                          (new)
strategy/research/order_block_lifecycle_policy_b.py     (new — PolicyBOrderBlockState)
tests/test_order_block_lifecycle_policy_b.py            (new — 15 causal tests)
```

`OrderBlockTracker`/`BreakerBlockTracker` are untouched. `PolicyBOrderBlockState`
never creates, resizes, or reinterprets a zone — it is constructed with the
exact `zone_high`/`zone_low`/`origin_timestamp` of an already-created,
real Order Block and shadows it candle-by-candle, reusing the same pure
helpers (`is_touching_zone`, `compute_mitigation`, `mitigation_status_from_pct`)
Policy A itself uses — no new detection logic was invented, only a
different post-creation state-transition rule.

## 3. Focused tests

15 tests in `tests/test_order_block_lifecycle_policy_b.py`, covering all 14
required scenarios: partial wick entry (mitigation only, no invalidation);
full wick traversal + close-back-inside compared directly against a real
`OrderBlockTracker` running Policy A side-by-side (A retires to `mitigated`,
B records full mitigation without invalidation); close-confirmed
invalidation, both directions; breaker eligibility following invalidation
specifically, not mitigation; independent observability of touch/mitigation/
invalidation/breaker fields; bullish/bearish symmetry; same-bar causal
ordering (a single candle that touches, fully wick-mitigates, and
close-invalidates all at once); no future-candle use; independent tracker
instances; multiple simultaneously-tracked blocks remaining independent;
non-duplicating repeated `apply_candle()` calls; identical creation
count/origin between A and B (by construction); determinism (5 independent
runs, identical final state); and a direct confirmation that production's
own `OrderBlockTracker` still exhibits Policy A's behavior unchanged
(the wick-traversal-and-reclaim scenario still retires under real,
unmodified production code).

## 4. Full-suite result

**918/918 passing** (903 pre-sprint + 15 new).

## 5. SOL TRAIN module-level comparison

**Runner**: `order_block_lifecycle_sol_train.py` (scratchpad, not committed
— the smallest harness needed, per instruction, not a SOL strategy
baseline). Drove the real, unmodified `MarketStructureTracker` →
`OrderBlockTracker` → `BreakerBlockTracker` chain (the exact corrected
Module Logic Correction 1/2 wiring) directly, one candle at a time, and
shadowed every created Order Block with a `PolicyBOrderBlockState`. Used
only the 4 locked SOL TRAIN months; SOL VALIDATION/HELD_OUT were never
accessed.

**SOL configuration, logged per month** (via `strategy/instrument_scale.py`,
computed from each month's own first close — never from strategy
performance):

| Month | Reference price | round_number_spacing | volume_profile_bucket_size | Dataset hash | 15m bars |
|---|---:|---:|---:|---|---:|
| 2024-02 | 97.316 | 1.0 | 0.1 | `0505e9a12f29d85c` | 2,783 |
| 2024-04 | 202.423 | 2.0 | 0.2 | `7fdd3534be4b4fce` | 2,879 |
| 2024-09 | 135.188 | 1.0 | 0.1 | `152567a60cd94ec9` | 2,879 |
| 2025-12 | 133.62 | 1.0 | 0.1 | `29e07d7347c4232c` | 2,975 |

(Order Block creation itself does not consume `round_number_spacing`/
`volume_profile_bucket_size` — these are logged here to satisfy the SOL
research-runner readiness discipline, not because this specific module
reads them.)

## 6. Monthly/regime result table

Regime labels reused from `docs/phase5_strategic_roadmap_decision.md`
Section 1.4 (computed from raw price, independent of this sprint).

| Month | Regime | Blocks created | A retired | B invalidated | Wick-full-traversal + reclaim | …never subsequently invalidated | …invalidated anyway (delayed) |
|---|---|---:|---:|---:|---:|---:|---:|
| 2024-02 | strong bull | 342 | 328 | 318 | 136 (39.8%) | 4 (2.9% of reclaimed) | 132 (97.1%) |
| 2024-04 | strong bear | 361 | 327 | 320 | 140 (38.8%) | 6 (4.3%) | 134 (95.7%) |
| 2024-09 | low-range/directionless | 365 | 341 | 329 | 140 (38.4%) | 7 (5.0%) | 133 (95.0%) |
| 2025-12 | lowest-volatility range | 356 | 345 | 338 | 138 (38.8%) | 3 (2.2%) | 135 (97.8%) |
| **Total** | | **1,424** | **1,341** | **1,305** | **554 (38.9%)** | **20 (1.4% of all blocks; 3.6% of reclaimed)** | **534 (96.4% of reclaimed)** |

**By direction** (all 8 direction×month cells checked — no concentration in
one direction): reclaimed-never-invalidated counts range 0–6 per cell,
never more than ~5% of that cell's own reclaimed population, in both
bullish and bearish blocks, in every regime.

**Time from creation to first touch**: median 2–3 bars under Policy A
(touch counted only once a block re-enters after a genuine clear); median
0 bars under Policy B is an artifact of measuring touch identically but B's
own state object is only instantiated once creation is already known,
so its "first touch" frequently coincides with the very next candle after
creation in fast-forming zones — not a substantive lifecycle difference,
since both policies use the exact same `is_touching_zone` rule.

**Block age at retirement (Policy A)**: median 11–15 bars across the four
months — consistent, no regime showing a wildly different aging pattern.

**Direction-normalized excursion at pre-declared horizons** (4/8/16
completed 15m candles, median price units): favorable and adverse
excursions are broadly comparable in magnitude at every horizon in every
month (e.g., 2024-02 horizon-4: favorable 0.300 vs. adverse 0.279;
2024-04 horizon-16: favorable 0.645 vs. adverse 0.484) — no horizon or
month shows a lopsided asymmetry that would suggest Policy A's earlier
retirement is systematically cutting off large favorable continuations
Policy B would have captured.

**Concentration check**: the "genuinely rescued" population (reclaimed,
never invalidated) is small (3–7 per month) and stays small and consistent
across every regime — not concentrated in, or driven by, any single month
or a handful of outlier events.

**Percentage of cases where A and B behave identically** (never reclaimed
at all — either both never resolve, or A's retirement bar was already a
close-confirmed invalidation with no intervening wick-only reclaim):
**~60% of all created blocks in every month** (58.5%–60.9%), consistent
across regimes.

## 7. Downstream diagnostic results

Not run this sprint. The module-level evidence (Section 6) is already
decisive and consistent across all four TRAIN regimes without it, and the
instruction frames the S002/S006 diagnostic as conditional ("if used").
Given the clear result below, running it would not have changed the
recommendation; it remains available as a follow-up if the eventual
validation experiment (Section 9, if ever authorized) calls for it.

## 8. Point-in-time and same-bar safety analysis

- `PolicyBOrderBlockState.apply_candle()` is called once per candle, in
  the same replay order the real trackers already receive — no batching,
  no lookahead.
- Same-bar ordering is causal and documented: touch → mitigation depth →
  invalidation, all computed from the same single candle's OHLC, matching
  the same ordering Policy A's own `OrderBlock.apply_candle()` already
  uses (touch, then mitigation) — the invalidation check is simply an
  additional, final step reading the same candle's `close`, never a
  different bar's data.
- Directly tested: `test_no_future_candle_is_used`,
  `test_same_bar_ordering_is_causal_touch_then_mitigation_then_invalidation`.
- The research harness feeds `PolicyBOrderBlockState` the exact same
  candle, in the exact same loop iteration, as the real `OrderBlockTracker`
  and `MarketStructureTracker` receive — no separate or reordered replay
  path exists for the comparison.

## 9. Recommendation

**KEEP POLICY A.** Evaluated directly against the pre-declared decision
criteria:

- Wick-only full traversals **are** a material, repeated population
  (~39% of all created blocks, consistent 38.4%–39.8% across all four
  regimes) — this criterion for considering Policy B is met.
- However, a meaningful proportion of that population does **not**
  reject/recover in the sense that matters: **96.4% of reclaimed blocks
  eventually close-confirm invalidation anyway** — Policy B does not
  change the final outcome for the overwhelming majority of this
  population, it only delays reaching the same conclusion Policy A
  already reaches via wick penetration.
- Only **1.4% of all created blocks** (3.6% of the reclaimed population)
  are genuinely "rescued" by Policy B — never subsequently invalidated at
  all. This rate is small and consistent across every TRAIN regime (bull,
  bear, low-range, low-volatility range) and both directions — not
  concentrated in one month or a few outliers, but also not large enough
  in any regime to constitute a "meaningful proportion" by the user's own
  stated bar.
- Breaker creation under Policy A is therefore **not demonstrably
  premature** in the cases that matter: for 96.4% of the reclaimed
  population, A's earlier trigger anticipates the same eventual outcome;
  only the small 1.4% remainder represents a case where A's trigger was
  arguably wrong, and this rate does not clear a "material, repeated"
  bar on its own.
- Excursion analysis at all three pre-declared horizons shows no
  systematic asymmetry favoring later retirement.
- Evidence is **consistent, not mixed**, across all four TRAIN
  regimes — which itself supports a decisive recommendation rather than
  requesting a further validation experiment.

This matches the user's own "Retain Policy A if" criteria precisely:
wick-only full traversals are common but "usually continue through the
block anyway," and "separating invalidation merely delays the same
outcome" — directly demonstrated by the 96.4% figure, not assumed.

## 10. Exact next action requiring approval

None requested by this report. Per instruction, stopping after the
research report. If, at some future point, a different research question
specifically targets the ~1.4% "genuinely rescued" population (e.g.,
whether those particular blocks are economically distinguishable in
advance, or whether they cluster with any other available Market
Intelligence signal), that would be a new, separately-scoped research
question — not something this sprint's evidence supports pursuing as a
lifecycle-wide policy change.

---

**Not changing the production default. Not moving to Liquidity Sweep or any
other sprint without separate approval.**
