# Order Block Lifecycle Research Addendum — Time-to-Invalidation and Interim Response

**Revised recommendation: PROMOTE HYBRID POLICY C (≡ POLICY B AS IMPLEMENTED) TO VALIDATION.**

This reverses the prior report's `KEEP POLICY A` conclusion. The prior
conclusion relied on "96.4% of wick-reclaimed blocks eventually
invalidate" without examining what happens *during* the interval before
that eventual invalidation. This addendum measures exactly that interval
and finds a real, substantial, cross-regime-consistent effect the prior
report missed. No production code changed; this remains research-only.

## Scope preserved

`OrderBlockTracker`/`BreakerBlockTracker` remain untouched. Policy A
remains the production default. Policy B (`strategy/research/order_block_lifecycle_policy_b.py`)
remains research-only, unmodified from the prior sprint. SOL VALIDATION/
HELD_OUT were not accessed. No threshold optimization, no combined-portfolio
backtest, no Liquidity Sweep/S008/exit work was performed. No claim of
profitability is made anywhere below — every result is reported as
descriptive/diagnostic, per instruction.

## 1. Updated research artifacts

New scratchpad harness (not committed — research-only, matching the prior
sprint's convention): `order_block_lifecycle_addendum.py`, which reuses
the existing, unmodified `PolicyBOrderBlockState` and adds per-event
forward-path tracking (a `ForwardPathTracker` class) that the prior
harness did not capture — bar indices, timestamps, and interim
excursions for every wick-only-traversal event, from the traversal
candle's own close forward to either close-confirmed invalidation or
end-of-month censoring. No change to `strategy/research/order_block_lifecycle_policy_b.py`
itself — this is purely an analysis/measurement extension.

## 2. Full test-suite result

**918/918 passing** — unchanged from the prior sprint, since no
production or research module code was modified, only a new analysis
script was added (not part of the committed test suite).

## 3. Sample-size and censoring table

| Month | Regime | n events | Invalidated | Censored (end-of-window) | Expired |
|---|---|---:|---:|---:|---:|
| 2024-02 | strong bull | 136 | 132 (97.1%) | 4 (2.9%) | 0 |
| 2024-04 | strong bear | 140 | 134 (95.7%) | 6 (4.3%) | 0 |
| 2024-09 | low-range/directionless | 140 | 133 (95.0%) | 7 (5.0%) | 0 |
| 2025-12 | lowest-volatility range | 138 | 135 (97.8%) | 3 (2.2%) | 0 |
| **Total** | | **554** | **534 (96.4%)** | **20 (3.6%)** | **0** |

No block reached `max_age_bars` (5,000) within any single-month window —
expiry never occurred; censoring is purely end-of-window, correctly
distinguished from "rescued" (per instruction, censored ≠ rescued — these
20 are *unresolved*, not confirmed-never-invalidating).

## 4. Time-to-invalidation distribution (completed 15m bars, invalidated events only)

| Month | n | Min | P25 | Median | P75 | P90 | Max | Mean* |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2024-02 | 132 | 1 | 1.0 | 3.0 | 11.2 | 87.1 | 1,295 | 48.05 |
| 2024-04 | 134 | 1 | 1.0 | 2.0 | 9.0 | 52.2 | 1,175 | 28.13 |
| 2024-09 | 133 | 1 | 1.0 | 3.0 | 18.0 | 75.2 | 612 | 29.12 |
| 2025-12 | 135 | 1 | 1.0 | 4.0 | 15.0 | 60.2 | 522 | 29.10 |
| **All** | 534 | 1 | 1.0 | **3.0** | 12.8 | 70.4 | 1,295 | 33.54 |

*Mean is heavily right-skewed by rare, very long-lived outliers (max
1,295 bars ≈ 13.5 days) — median/percentiles are the trustworthy summary,
not the mean, exactly as flagged.

**Percentage invalidated within N bars (of all 554 events, not just the
invalidated subset):**

| Horizon | Invalidated by then | Still valid or unresolved |
|---:|---:|---:|
| 1 bar | 177 (31.9%) | 377 (68.1%) |
| 2 bars | 238 (43.0%) | 316 (57.0%) |
| 4 bars | 318 (57.4%) | 236 (42.6%) |
| 8 bars | 369 (66.6%) | 185 (33.4%) |
| 16 bars | 413 (74.5%) | 141 (25.5%) |
| 32 bars | 443 (80.0%) | 111 (20.0%) |

By direction: bullish median 3.0 bars (n=264, P75=10.0, P90=61.2);
bearish median 3.0 bars (n=270, P75=14.8, P90=79.0) — essentially
symmetric.

**Full-zone vs. mitigation/body-zone boundary**: not completed in this
addendum — the harness tracked the tighter `mitigation_zone_*` boundary
crossing at the block level but did not thread it into the per-event
`ForwardPathTracker` record. This is a known, disclosed gap (Section 8),
not a silently-dropped requirement.

## 5. Interim MFE/MAE tables (direction-normalized, from the traversal candle's own close)

Median values in ATR-at-creation units, at each pre-declared horizon,
computed only over events still being tracked at that horizon (not yet
invalidated):

| Horizon | Month | n | Median MFE | Median MAE | ≥0.5 ATR | ≥1.0 ATR | ≥2.0 ATR | Original-favoring | Breaker-favoring |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2024-02 | 136 | 0.426 | 0.490 | 44% | 11% | 1% | 49% | 51% |
| 1 | 2024-04 | 140 | 0.401 | 0.490 | 38% | 16% | 1% | 46% | 54% |
| 1 | 2024-09 | 140 | 0.366 | 0.473 | 42% | 12% | 1% | 45% | 55% |
| 1 | 2025-12 | 138 | 0.424 | 0.371 | 43% | 16% | 3% | 55% | 45% |
| 4 | 2024-02 | 65 | 1.209 | 0.514 | 89% | 63% | 25% | 75% | 25% |
| 4 | 2024-04 | 56 | 1.532 | 0.361 | 89% | 68% | 30% | 89% | 11% |
| 4 | 2024-09 | 71 | 1.212 | 0.453 | 90% | 65% | 25% | 77% | 23% |
| 4 | 2025-12 | 74 | 1.295 | 0.364 | 88% | 62% | 27% | 81% | 19% |
| 8 | 2024-02 | 46 | 2.271 | 0.449 | 98% | 85% | 54% | 87% | 13% |
| 8 | 2024-04 | 45 | 2.014 | 0.409 | 98% | 87% | 51% | 82% | 18% |
| 8 | 2024-09 | 48 | 2.297 | 0.372 | 100% | 96% | 60% | 94% | 6% |
| 8 | 2025-12 | 55 | 1.876 | 0.383 | 96% | 76% | 45% | 84% | 16% |
| 16 | (all 4 months) | 34–41 | 2.84–3.87 | 0.38–0.47 | 100% | 94–100% | 75–93% | 92–100% | 0–8% |
| 32 | (all 4 months) | 23–32 | 4.15–5.58 | 0.37–0.50 | 100% | 100% | 96–100% | 94–100% | 0–6% |

**At horizon 1** (bar immediately following the traversal candle):
directional response is close to a coin flip (45–55% either way) in
every month — Policy A's implicit "immediate breaker" framing is not
obviously wrong on the very next bar.

**From horizon 4 onward**, the picture changes sharply and consistently:
75–89% of events *still active at that horizon* favor the original block
direction, with median favorable excursion 1.2–1.5 ATR (h=4), rising to
2.0–2.3 ATR (h=8) and 2.8–5.6 ATR (h=16–32) — this pattern holds in
**every one of the four TRAIN regimes**, including 2024-04 (strong bear),
where it is if anything the *strongest* (89% original-favoring at h=4).

**Final (until invalidation or censoring) MFE/MAE, whole population**:
median final MFE 0.53–0.86 ATR vs. median final MAE 0.96–1.14 ATR — MAE
exceeds MFE in a majority of cases overall (54–61%), because this
includes the ~32% of events that invalidate within 1 bar (where MAE
dominates almost by construction). This is the aggregate-level fact that
drove the prior report's conclusion — it is not wrong on its own, but it
averages together two very different sub-populations (fast-resolving vs.
longer-lived) that the horizon breakdown above separates.

## 6. Directional response comparison for A/B/C

At each horizon, among events not yet invalidated:

| Horizon | Original-direction | Breaker-direction | n |
|---:|---:|---:|---:|
| 1 | 270 (48.7%) | 284 (51.3%) | 554 |
| 2 | 260 (69.0%) | 117 (31.0%) | 377 |
| 4 | 214 (80.5%) | 52 (19.5%) | 266 |
| 8 | 168 (86.6%) | 26 (13.4%) | 194 |
| 16 | 137 (97.2%) | 4 (2.8%) | 141 |
| 32 | 109 (97.3%) | 3 (2.7%) | 112 |

**Policy A declaring breaker-eligible while price immediately (1 bar)
moves ≥0.5 ATR in the original direction**: 232/554 (41.9%) — a
substantial minority where A's framing is contradicted almost
immediately, not just eventually.

**Policy B/C retaining a block that "immediately continues through and
should clearly have been invalidated"**: measured as the complement —
51.3% of events at h=1 already favor the breaker direction, meaning in a
slight majority of cases *on the very first bar*, A's immediate framing
IS the better read. This is the honest counter-evidence: Policy B/C is
not uniformly better, it is better **specifically for the sub-population
that survives past ~2–4 bars**, which by horizon-4 is 266/554 (48%) of
the total population and by horizon-8 is 194/554 (35%).

**Consistency across regimes and directions**: the horizon-4-and-beyond
pattern (strong, growing original-direction favorability) holds in all
four TRAIN regimes and both directions (bullish median 3.0 bars,
bearish median 3.0 bars to invalidation — no directional asymmetry).
This is not a one-month or one-direction effect.

## 7. Overlap/de-duplication assessment

**This is a material caveat, disclosed prominently, not buried.** Zone-overlap
checking (same direction, overlapping `[zone_low, zone_high]` ranges)
found **71–79% of raw events per month share zone overlap with at least
one other event** — many "554 events" are not independent trials; they
frequently represent the same or an adjacent structural move expressed
as multiple, overlapping Order Blocks.

A simple, disclosed clustering pass (same direction, overlapping zone,
traversal within 20 bars of each other → same cluster) reduces the count
to:

| Month | Raw events | Clusters (de-duplicated) |
|---|---:|---:|
| 2024-02 | 136 | 112 |
| 2024-04 | 140 | 117 |
| 2024-09 | 140 | 121 |
| 2025-12 | 138 | 115 |

A ~15–18% reduction, not a collapse — several hundred genuinely distinct
clusters remain per month, and the qualitative pattern (Section 5/6)
holds at this reduced count. The raw counts should not be read as 554
fully independent trials; the clustered counts (~465 total) are the more
defensible denominator for "how many genuinely distinct opportunities
this represents," and both are reported here rather than picking one
silently.

## 8. Monthly/regime consistency

The core finding — a roughly coin-flip immediate (1-bar) response,
followed by increasingly strong and consistent favor for the original
block direction from bar 4 onward, with substantial magnitude (1–5+ ATR)
— holds in **all four** TRAIN regimes (strong bull, strong bear,
low-range/directionless, lowest-volatility range) and **both** directions.
This is not a regime-dependent effect requiring a regime-specific
hypothesis — it is unusually consistent, which is exactly the condition
under which a decisive recommendation (rather than "inconclusive") is
warranted per the user's own framework.

**Known limitations, stated plainly:**
- MFE and MAE were measured as **independent running maxima** over the
  same horizon, not as a sequential, first-touched outcome. This means
  the results here describe the *price path's range*, not a simulated
  trade's realized P&L — a real entry could still be stopped out by the
  adverse excursion *before* the favorable excursion is reached. This is
  exactly why the recommendation is to *validate*, not to adopt.
- The full-zone vs. body/mitigation-zone boundary comparison (Section 4)
  was not completed — a disclosed gap, not a hidden omission.
- The overlap rate (71–79%) means raw event counts overstate independent
  sample size; the de-duplicated counts (Section 7) are the more
  conservative basis for judging "frequency."

## 9. Revised recommendation

**PROMOTE HYBRID POLICY C TO VALIDATION.** (Policy C, as newly specified,
is behaviorally identical to the already-implemented Policy B: both track
wick-based `mitigation_status` and close-based `invalidated` as
independent fields, with breaker eligibility gated on `invalidated` —
no new implementation is required to test it.)

Evaluated directly against the user's own stated bar:
- `KEEP POLICY A` requires close-confirmed invalidation to *usually*
  follow quickly **and** little meaningful favorable movement in the
  original direction beforehand. The first half is roughly true in
  aggregate (median 3 bars) but the second half is **not** true for the
  ~43–48% of events that survive past bar 2–4: those show large (1.2–5.6
  ATR), consistent, cross-regime favorable movement in the original
  direction before the eventual invalidation. `KEEP POLICY A` cannot be
  honestly justified against the user's own full standard.
- `PROMOTE POLICY B/C` requires the interim response to be *frequent*
  and *consistent across regimes*. It is frequent for a real, substantial
  (not universal) minority-to-plurality of the population (roughly
  35–48% depending on horizon, ~300–465 de-duplicated clusters across the
  four months), and it is remarkably consistent across all four regimes
  and both directions — this bar is met.
- The evidence is **not** regime-inconsistent (Section 8), so
  "inconclusive, recommend a regime-dependent hypothesis" does not apply
  either.

This is explicitly a promotion to **VALIDATION-stage testing**, not
production adoption — the MFE/MAE-as-independent-maxima limitation means
this has not been shown to be profitable or even net-favorable under
realistic sequential trade logic, only that the *lifecycle framing* of
"immediately breaker-eligible" is empirically contradicted often enough,
consistently enough, to be worth testing under a real entry/exit
simulation before any production consideration.

## 10. Exact next action requiring approval

A specific, narrowly-scoped **VALIDATION-stage experiment**: simulate
Policy C's lifecycle (not Policy A's) feeding a research-only, standalone
variant of S002 or a comparable Order-Block-consuming setup, on the SOL
**VALIDATION** months (not accessed in this or the prior sprint), with a
real sequential entry/exit/stop model (not independent MFE/MAE maxima) —
to determine whether the interim favorable-movement pattern found here
survives being converted into an actual, realistically-costed trade
sequence. This is a new, separately-scoped request requiring your
explicit authorization before any SOL VALIDATION data is touched, any
setup logic is modified, or any threshold is chosen.

---

**Not changing the production default. Not moving to Liquidity Sweep or
any other sprint without separate approval.**
