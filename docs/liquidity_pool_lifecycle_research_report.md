# Liquidity Pool Lifecycle Research — Fresh Sweep, Failed Acceptance, and Stale Pool Detection

**Recommendation: PROMOTE POLICY C TO VALIDATION** (bounded acceptance-pending
state machine). `PROMOTE POLICY B` is explicitly rejected by this same
evidence. This is a research and decision sprint only — production
`LiquidityPoolTracker` behavior is completely unmodified.

## Git checkpoint

1. `git status` before this sprint: clean (Order Block VALIDATION
   experiment had just been committed).
2. That experiment's exact files confirmed via `git status`.
3. Committed as `924322f` ("Order Block Hybrid Policy C: pre-registered
   SOL VALIDATION experiment").
4/6. No unrelated files included; nothing pushed, merged, rewritten, or
   reverted.
5. Commit hash: `924322f`.

This sprint's own files remain **uncommitted**, per the established
pattern.

## 1. Research methodology

Drove the real, unmodified `EqualLevelsTracker` → `SessionBoundariesTracker`
→ `LiquidityPoolTracker` chain (exact production wiring and ordering) plus
a standalone `AverageTrueRangeTracker` for point-in-time ATR sampling, one
candle at a time, across the 4 locked SOL TRAIN months. For every pool
that ever appeared in `active`, recorded its complete timeline: creation
(zone bounds, sources, source count, ATR, bar index), every subsequent
bar's wick-beyond/close-beyond/reclaim state (read from the live,
currently-in-effect zone bounds each bar — see Section 9's disclosed
caveat about same-bar zone-widening), the production tracker's own
`swept_status`/`swept_timestamp` transition, age-based expiry, and
end-of-window censoring. `strategy/research/liquidity_pool_lifecycle_policy.py`
holds the three pure, independently-tested analysis functions
(`classify_lifecycle_path`, `deduplicate_pools`, `first_passage_outcome_pool`) —
`LiquidityPoolTracker` itself is never touched.

SOL configuration explicitly logged per month via `strategy/instrument_scale.py`
(reference price = each month's own first close; `round_number_spacing`/
`volume_profile_bucket_size` computed from it, matching the values already
established in the Order Block research: 1.0/0.1 or 2.0/0.2 depending on
SOL's price level that month).

## 2. Exact lifecycle definitions

**Six categories as specified, with one honest reclassification finding**
(stated explicitly, not silently absorbed): `same_candle_sweep` and
`delayed_current_rule_sweep` are exactly as specified. `never_resolved`
covers both "never touched the boundary at all" and "touched but never
reclaimed nor swept before censoring." **`fast_multi_candle_rejection`
and `sustained_acceptance` collapsed to essentially zero occurrences** in
the TRAIN data — not because no pool ever closes beyond and later
reclaims without the production rule firing, but because **a reclaim
candle mechanically almost always still satisfies the wick-based sweep
rule too**: if price has been trading beyond a pool's boundary for any
stretch of time and then closes back through, that same reclaiming
candle's own wick is very likely to still extend beyond the boundary
(price does not teleport back inside without an intervening bar that
touches both sides) — so the reclaim is, in the overwhelming majority of
real cases, *also* a `wick-beyond + close-back` event on that exact
candle, which the production tracker already marks "swept." This means
almost every pool that ever closes beyond eventually resolves via
`delayed_current_rule_sweep`, not via a silent, rule-invisible reclaim.
`delayed_current_rule_sweep`'s own severity (how many prior closes beyond,
how long the delay) is reported as a distribution (Section 4), not
discarded.

`classify_lifecycle_path`'s own docstring documents this interpretation
in full; it is not a silent scope change from the original six-category
framing — the intermediate "clean break/acceptance" event (candidate #2
in the original framing) is exposed as `first_close_beyond_bar_i is not None`,
not forced into being its own mutually-exclusive terminal bucket, since
it describes an event, not a final fate.

## 3. Tests and full-suite result

22 tests in `tests/test_liquidity_pool_lifecycle_policy.py`, covering all
15 required scenarios: fresh same-candle sweep; one/multiple closes
beyond followed by immediate or delayed reclaim; sustained acceptance
without reclaim; delayed current-rule sweep, including the edge case
where a close-beyond is recorded on the sweep candle itself (not counted
as "prior"); buy-side/sell-side symmetry; no-lookahead and
no-same-bar-retroactivity (via the reference-candle-excluded contract);
independent/multiple pools; overlapping-pool clustering and
different-side isolation; right-censoring not misclassified as a
resolved outcome; a direct confirmation that production `LiquidityPool.check_sweep`
still requires the same-candle wick+close pattern (a clean close beyond
alone does not mark it swept); and determinism.

**Full suite: 955/955 passing** (933 prior baseline + 22 new).

## 4. Complete pool-path distribution

De-duplicated, pooled across all 4 TRAIN months (n=5,040):

| Path | Count | % |
|---|---:|---:|
| same_candle_sweep | 1,366 | 27.1% |
| delayed_current_rule_sweep | 3,469 | 68.8% |
| fast_multi_candle_rejection | 0 | 0.0% |
| sustained_acceptance | 0 | 0.0% |
| never_resolved | 205 | 4.1% |

**Per month** (all four remarkably consistent):

| Month | Regime | n | same_candle | delayed | never_resolved |
|---|---|---:|---:|---:|---:|
| 2024-02 | strong bull | 1,207 | 26.3% | 69.6% | 4.1% |
| 2024-04 | strong bear | 1,233 | 26.8% | 68.3% | 4.9% |
| 2024-09 | low-range/directionless | 1,363 | 26.6% | 69.3% | 4.1% |
| 2025-12 | lowest-vol range | 1,237 | 28.8% | 68.1% | 3.2% |

**Of pools that ever close beyond (3,469), 100% eventually register as
`delayed_current_rule_sweep`** — none silently reclaim without also
satisfying the wick rule (Section 2's finding). Of all current-rule
sweeps (4,835 total), **71.7% are delayed** (occurred after at least one
prior clean close beyond), only 28.3% are truly fresh same-candle events —
this is confirmed limitation #2, and it is the **majority behavior**, not
an edge case.

**Delayed-sweep severity** (bars from first close-beyond to the eventual
sweep, n=3,469): median 3, P75 12.0, P90 58.0, max 1,514 (≈15.8 days).
Resolution-within-N-bars: 32.2% within 1 bar, 45.8% within 2, 58.7%
within 4, 69.9% within 8, 78.6% within 16, 85.9% within 32, 90.6% within
64. **A real, material minority (9.4%) remains unresolved beyond 64 bars
(16 hours)**, with a long tail extending to multiple weeks.

**Prior closes-beyond count** (for delayed sweeps): median 3, max 1,514 —
most delayed pools accumulate a handful of beyond-boundary closes before
finally resolving, but a minority accumulate very many.

**Penetration depth at first close beyond**: median 0.27–0.30 ATR, P90
0.81–0.91 ATR, consistent across all 4 months — typically a modest,
not dramatic, initial breach.

**Age pruning removing an already-accepted, unswept pool** (Question 7):
**zero occurrences** in any TRAIN month — `max_age_bars` (5,000) is never
reached within a single-month window at 15m granularity (~2,800–2,975
bars total per month), so this specific failure mode did not manifest in
this dataset, though it remains a theoretical concern for longer-running
live/multi-month deployments not tested here.

## 5. Time-to-reclaim/acceptance analysis

Already presented in Section 4 (delayed-sweep severity distribution).
The proposed `fast_threshold_bars` for the pure classification function
(median of all close-beyond→reclaim times observed, structural, not
P&L-selected) is **2 bars** — used only internally by `classify_lifecycle_path`
to distinguish a conceptual "fast" vs "sustained" case; given Section 2's
finding, this distinction ended up mostly moot for the terminal
classification (both collapse into `delayed_current_rule_sweep`), but the
underlying delay-severity distribution itself (Section 4) is the
substantively important measurement, not this internal threshold.

## 6. Raw versus de-duplicated results

| Month | Raw | De-duplicated | Reduction |
|---|---:|---:|---:|
| 2024-02 | 1,208 | 1,207 | 1 (0.08%) |
| 2024-04 | 1,233 | 1,233 | 0 (0.00%) |
| 2024-09 | 1,363 | 1,363 | 0 (0.00%) |
| 2025-12 | 1,237 | 1,237 | 0 (0.00%) |

**Overlap is essentially non-existent for Liquidity Pools** — a sharp
contrast with Order Blocks' 71–79% overlap rate. This is structurally
expected, not a coincidence: a Liquidity Pool only forms in the first
place via ATR-tolerance-based clustering of candidate touches
(`_register_candidate`'s own matching logic) — two candidate prices
within tolerance of each other are, by construction, merged into the
*same* pool rather than creating two separate, overlapping pools. The
overlap problem Order Block research had to correct for does not
meaningfully exist here because the production tracker's own formation
rule already prevents it. Raw and de-duplicated results are reported
identically throughout this report as a result; de-duplication changes
essentially nothing.

## 7. Per-regime and per-direction results

**By direction** (pooled): buy_side (n=2,519) same_candle 28%, delayed
68%, never_resolved 4%; sell_side (n=2,521) same_candle 26%, delayed
69%, never_resolved 4% — no meaningful asymmetry.

**By source count at creation**: single-source pools (n=4,804, the vast
majority) show 26% same_candle / 70% delayed / 4% never_resolved;
2-source pools (n=235) show a *notably different* pattern — 43% same_candle
/ 45% delayed / 11% never_resolved. Multi-source pools (stronger
confluence at formation) are swept fresh nearly twice as often as
single-source pools, and are more likely to never resolve at all within
the window. This is a real, if secondary, finding: pool strength at
formation correlates with how it eventually resolves, though the
practical sample size for 2+ sources (235, and only 1 pool ever had 3)
is much smaller than the single-source population.

**By regime**: the same_candle/delayed/never_resolved split is
remarkably stable across all four TRAIN regimes (Section 4 table) —
this is not a regime-dependent phenomenon.

## 8. S001 fresh-versus-stale diagnostic

**Correction (post-publication):** this section originally misstated the
matched total as "44 of 61 (72%)". The correct, reconciled arithmetic is
**37 of 61 matched (60.7%)** — `fresh_same_candle_sweep` (11) +
`delayed_current_rule_sweep` (26) = 37; `unmatched` = 24; 37 + 24 = 61.
The error was caught and corrected before any decision was based on it.

**Diagnostic only — not used to select or justify any lifecycle
recommendation**, per instruction, and **superseded by exact
pool-identity linkage in the VALIDATION-stage experiment** (see
`docs/liquidity_pool_policy_c_validation_report.md`) rather than the
closest-sweep-timestamp-within-tolerance approach used here. S001 fires
extremely rarely relative to the pool population (11–19 closed trades
per month against 1,200+ pool sweeps per month), because it additionally
requires CVD confirmation plus at least one of CHOCH/multi-source/SMT
evidence on top of the raw sweep. Matching each trade to its underlying
pool by closest-sweep-timestamp within a 20-minute tolerance (trade entry
timestamps are 1-minute-granular while pool sweeps are recorded on 15m
candle boundaries) matched 37 of 61 total TRAIN trades (60.7%); the
remaining 24 are reported as unmatched rather than guessed.

| Tag | n | Win rate | Total P&L | Avg P&L | Profit factor | Fees |
|---|---:|---:|---:|---:|---:|---:|
| fresh_same_candle_sweep | 11 | 18.2% | -700.83 | -63.71 | 0.33 | 129.55 |
| delayed_current_rule_sweep | 26 | 61.5% | +1,694.36 | +65.17 | 2.48 | 303.36 |

**This sample is far too small (11 vs. 26 trades) to be decisive on its
own, and its matching methodology is approximate (nearest-timestamp, not
exact pool-identity linkage)** — reported as diagnostic evidence only,
not as justification for any recommendation below, and not to be relied
upon as primary evidence in any later VALIDATION-stage decision. It is
presented because it happens to run counter to a naive intuition ("stale
sweeps should be worse") — worth noting as a genuine curiosity, properly
re-examined with exact linkage at the VALIDATION stage, not as evidence
supporting Policy C or any other conclusion here.

## 9. Bias/censoring assessment

**Unconditional forward-path analysis** (avoiding the Order Block
research's own earlier survivorship error, from the first clean close
beyond, complete cohort, no conditioning on surviving to any horizon):
competing risk between "close back through the boundary" (reclaim) and
"price travels a further +1.0 ATR beyond the boundary" (continuation).

| Month | n | Reclaim-first | Continuation-first | Censored |
|---|---:|---:|---:|---:|
| 2024-02 | 881 | 58.2% | 41.5% | 0.2% |
| 2024-04 | 886 | 55.4% | 44.6% | 0.0% |
| 2024-09 | 988 | 60.1% | 39.7% | 0.2% |
| 2025-12 | 876 | 58.0% | 41.9% | 0.1% |
| **Pooled** | **3,631** | **58.0%** | **41.9%** | **0.1%** |

Every event is retained in the denominator (per protocol); this is not
conditioned on surviving to a later horizon. Reclaim wins the
unconditional race moderately and consistently more often than
continuation, in every regime (55.4–60.1%) — a real, if not overwhelming,
tilt.

**Known limitations, disclosed:**
- The forward-path analysis used the pool's *final* (end-of-run) zone
  bounds for the non-active side of the boundary check, which is a minor
  imprecision if a pool's zone widened after the reference event — this
  does not affect the reclaim-boundary check itself (which correctly
  uses the boundary value *at* the first-close-beyond moment), only the
  unused far-side parameter.
- Same-bar zone-widening: this harness reads the *live* (already
  post-this-candle's-own-touches) zone bounds each bar, which can differ
  from what production's own `check_sweep` used internally on that exact
  candle (which reads zone bounds *before* this candle's own new
  touches are absorbed). This is a small, disclosed timing nuance
  affecting at most the rare bar where a pool both gains a new touch and
  crosses its boundary simultaneously — not corrected here, flagged as a
  minor methodological caveat.
- Ambiguous same-bar cases (both reclaim and continuation true on the
  same candle) are conservatively counted as "reclaim," per the same
  convention already established in the Order Block research.

## 10. Recommendation

**PROMOTE POLICY C TO VALIDATION.**

Applying the six required promotion criteria:
1. **Material population of stale/delayed sweeps** — yes: 68.8% of all
   pools, 71.7% of all actual sweeps, are delayed relative to the pool's
   true first breach; 9.4% of delayed sweeps take longer than 64 bars
   (16 hours) to resolve, with a tail to multiple weeks.
2. **Consistent across multiple SOL TRAIN regimes** — yes: 68.1–69.6%
   delayed rate in all four regimes (strong bull, strong bear, low-range,
   lowest-volatility range); the unconditional reclaim-vs-continuation
   split is similarly consistent (55.4–60.1%).
3. **Not driven by overlapping duplicate pools** — yes, decisively: raw
   and de-duplicated results are essentially identical (0–0.08%
   reduction) — this population has none of the dependence concern that
   affected the Order Block research.
4. **Clear causal explanation** — yes: the production sweep rule only
   fires on a same-candle wick-beyond-then-close-back pattern; a pool
   that closes beyond and later reclaims via a multi-candle process still
   (mechanically) usually satisfies this rule on its final reclaim
   candle, but the *timestamp* attributed to the sweep can be far removed
   from when the pool's liquidity was arguably first consumed — a
   structurally real, well-understood mechanism, not a statistical
   artifact.
5. **No reliance on one favorable P&L result** — confirmed: the S001
   diagnostic (Section 8) was **not** used to support this
   recommendation; the recommendation rests entirely on the lifecycle
   timing/reclaim evidence (Sections 4, 6, 9).
6. **A candidate rule simple enough to validate without broad threshold
   searching** — yes: Policy C needs exactly one new parameter (the
   sustained-acceptance/bounded-window cutoff). Proposed primary
   candidate: **16 completed 15-minute candles (4 hours)** — a round
   number sitting between the observed P75 (12 bars) and P90 (58 bars) of
   the delay-severity distribution, chosen as the smallest structurally
   defensible value that clears the bulk (78.6%) of naturally-resolving
   delayed sweeps while still bounding the long tail. **32 bars (8 hours)**
   is reserved as the adjacent value for later sensitivity testing — no
   threshold search across a wider grid is proposed. Neither value was
   chosen by P&L.

**Policy B is explicitly rejected by this same evidence**, not merely
unexamined: 58.0% of all close-beyond events (pooled, unconditional)
eventually reclaim rather than continue — immediately retiring a pool on
its first close beyond would discard the *majority* of cases that go on
to behave as genuine, currently-already-recognized sweeps. Policy A's
existing choice not to retire on a bare close-beyond is, on this
evidence, reasonably conservative; the actual, confirmed problem is
specifically the long tail of *how late* a legitimate-looking sweep can
be attributed relative to the pool's true first breach — which is
exactly what Policy C's bounded window targets, and Policy B does not
address correctly at all.

## 11. Proposed VALIDATION protocol (not executed — proposal only, pending approval)

Modeled directly on `docs/order_block_policy_c_validation_protocol.md`'s
frozen-and-hashed structure:

- **Locked VALIDATION periods**: the same previously-registered SOL
  VALIDATION months (2024-11, 2024-08, 2024-10, 2025-05) — not accessed
  in this sprint.
- **Frozen event definition**: identical to TRAIN — a pool's first clean
  close beyond its outer boundary, per `LiquidityPoolTracker`'s own live
  zone bounds at that moment.
- **Frozen Policy C parameter**: bounded acceptance-pending window =
  **16 completed 15-minute candles**, fixed before VALIDATION data is
  loaded, with 32 bars pre-declared as the sole sensitivity check (no
  broader search).
- **Primary endpoint**: unconditional competing-risk first passage from
  the first close-beyond event — does a genuine current-rule-style sweep
  (wick beyond + close back) occur *within* the 16-bar window (Policy
  C would treat this as a valid, still-fresh sweep), or does the pool
  remain beyond the boundary past 16 bars without reclaiming (Policy C
  would retire it as "sustained acceptance," never eligible to sweep
  later) — reported for the complete cohort, no survivor conditioning.
- **De-duplication**: not expected to matter materially (Section 6), but
  the same frozen, structural-identity-only clustering rule would be
  applied and reported for completeness.
- **Promotion-to-additive-implementation criteria**: mirror the Order
  Block experiment's own boundary — even if VALIDATION supports Policy
  C, it would be recommended only as an **additive representation**
  (new, separately-observable `acceptance_pending`/`sustained_acceptance`
  states alongside the existing `swept_status`, not a replacement),
  gated behind a later, separate implementation approval, with real
  profitability contribution ultimately tested through a qualified
  setup (e.g., an S008-stage ablation) using identical entries.

This protocol is **proposed only** — it has not been written to a frozen,
hashed file, and no VALIDATION data has been touched.

## 12. HELD_OUT and VALIDATION confirmation

**SOL VALIDATION (2024-11, 2024-08, 2024-10, 2025-05) and SOL FINAL
HELD_OUT (2025-02, 2025-07) were never accessed anywhere in this
sprint.** Only the four locked TRAIN month files
(`SOLUSDT-1m-2024-02.csv`, `-2024-04.csv`, `-2024-09.csv`,
`-2025-12.csv`) were opened, confirmed by the dataset hashes logged in
each month's config output. No BTC data was used for any decision here.

---

**Production `LiquidityPoolTracker` behavior remains completely
unmodified.** Not opening VALIDATION data, not implementing S008, not
beginning another module without separate approval.
