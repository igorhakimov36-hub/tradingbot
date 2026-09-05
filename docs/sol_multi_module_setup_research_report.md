# SOLUSDT Multi-Module Setup Discovery — TRAIN Evaluation Report

Frozen protocol: `docs/sol_multi_module_setup_research_protocol.md`
(hash `a86b2cd9c7a003688a8dd510b581ea0b75a107815be638daafa9afc306b242c0`,
verified unchanged before every outcome computation below). This
report implements and evaluates the 3 candidates that protocol
defined (S008, S009, S011), standalone against unchanged S001 as
reference, on all 4 SOL TRAIN months.

**Revision note**: the interaction analysis (§4) was initially
delivered with a real measurement gap in the S009 opportunity capture
and an under-explained S011 structural limitation. Both are repaired
below (§4), two new predeclared ablation backtests were run where the
diagnostic-only slicing could not substitute for an executable
comparison, and S008's funnel (§5) and S011's evidence (§3b) are now
reported with full counts, exclusions, and uncertainty. **The
full-setup performance findings (§3) and the component-contribution
findings (§4, §7) are reported as separate deliverables, as requested
— neither was allowed to silently stand in for the other.** No
non-promotion decision changed: S008 remains unscored, S009 remains
unsupported, S011 remains insufficient evidence (§6, unchanged).

## Bottom line

**None of the 3 candidates qualifies for a frozen VALIDATION
experiment.** S008 essentially never fires on SOL TRAIN (a genuine,
causally-explained null, not a bug — condition funnel in §5). S009 is
an **unsupported hypothesis** — negative after-cost expected value in
all 4 of 4 TRAIN months, with an economically disqualifying 55.8% max
drawdown; its confirmation condition has a real but small measured
effect (+$6.02/trade, §4b), nowhere near enough to close the gap. S011
is **insufficient evidence** — its entire pooled net P&L is
attributable to a single +41.36R trade (leave-one-out net is
**negative**, −$1,187.58, §3b), positive in only 2 of 4 months, and its
month-clustered 95% CI is [−$106.67, +$151.55] — wide enough to be
uninformative. The most informative failed hypothesis is S009's:
order-flow participation asymmetry between a failed excursion and its
rejection, even though real, measurable, and confirmed by a real
predeclared ablation backtest, does not translate into a tradeable
edge once frequency (165 trades/month) and drawdown are accounted for.

---

## 1. What was implemented

Three research-only setups, `strategy/research/setups/`
(`s008_displacement_continuation.py`, `s009_failed_auction_reversal.py`,
`s011_value_area_fade.py`), plus a shared, parameterized backtest
adapter (`strategy/research/multi_module_backtest_adapter.py`) — all
uncommitted, matching this project's established research-only
precedent. S001 (`strategy/setups/liquidity_sweep_reversal.py`) and its
production adapter were not touched. S009 and S011 each additionally
expose one constructor flag (`require_confirmation` /
`require_cvd_confirmation`, both defaulting to `True` — the frozen,
production behavior) enabling the predeclared ablation comparisons in
§4b without duplicating or redesigning either candidate's own
condition logic.

## 2. Verification found and fixed 3 real implementation bugs before any outcome was trusted

Research discipline caught these before they reached this report —
disclosed in full, not silently corrected:

- **Instrument-scale defect (harness-level, not a setup bug).** My
  first backtest driver constructed `MarketIntelligenceCoordinator`
  without passing SOL-appropriate `round_number_spacing`/
  `volume_profile_bucket_size` (every established SOL script in this
  project passes these explicitly via `strategy/instrument_scale.py`'s
  helpers — I omitted them). This silently used BTC-scaled defaults
  ($500 spacing, $50 buckets) on SOL data. Caught because the S001
  reference (n=37 pooled) did not match the already-established SOL
  TRAIN baseline (n=61, net −$672.92, from the Progressive Stop and
  CVD sprints). Fixed; **S001 now reproduces exactly n=61, net
  −$672.92** — confirmed below.
- **S008's mitigation-zone condition checked `mitigation_zone_status
  == "active"`** — not a real value of that field (confirmed by
  reading `strategy/features/order_block.py`'s own
  `MitigationStatus = Literal["unmitigated", "partially_mitigated",
  "fully_mitigated"]`); this made the condition permanently
  unsatisfiable. Fixed to `!= "fully_mitigated"` (the frozen design's
  actual intent). A synthetic unit test's own fixture used the same
  wrong string, so it did not catch this — only real-data replay did.
  Recorded as a concrete verification lesson: synthetic fixtures
  written against an assumption, not a verified real value, can be
  self-consistently wrong.
- **S011's stop-loss construction never applied the production
  `MIN_RISK_PERCENT` floor** (unlike S008/S009, which did). Caught by
  inspecting sample trades: stops sat ~0.1% from entry (well under the
  0.6% floor every other setup in this project respects), which
  `create_risk_based_trade_setup` does not itself enforce — it is
  purely the caller's responsibility. Fixed; S011 stops now correctly
  floor at ~0.62%.

All 3 fixes restore the frozen protocol's own already-stated intent
(no threshold was changed, no candidate redesigned) — no re-freeze was
required. Full reruns after each fix: 1156 tests, 0 failed throughout.
A fourth, distinct issue — a measurement gap in the diagnostic
opportunity-population *capture script* (never in the real backtest
economics above) — was found in a later completion pass; see §4.

## 3. Standalone results (fixed exits, funding-inclusive, 1% equity risk/trade)

**Control reproduction check**: S001 reference, this sprint's harness
vs. established baseline — **n=61 both, net −$668.27 after funding
(−$672.92 before funding; the $4.65 shift is the funding overlay,
matching the SOL Funding sprint's own finding that funding is
economically negligible) — exact match.**

### Pooled (4 TRAIN months)

| | S001 (ref) | S008 | S009 | S011 |
|---|---:|---:|---:|---:|
| n | 61 | **0** | 659 | 60 |
| Win rate | 36.1% | — | 36.6% | 26.7% |
| Profit factor | 0.854 | — | 0.885 | 1.459 |
| Net P&L | −$668.27 | $0 | **−$5,346.82** | **+$2,509.97** |
| Expectancy/trade | −$10.96 | — | −$8.11 | +$41.83 |
| Max drawdown | 7.63% | — | **55.80%** | 20.39% |
| Avg win / avg loss | $177.66 / −$117.35 | — | $171.20 / −$111.50 | $498.40 / −$124.19 |
| Largest trade as % of net P&L | 27.8% | — | 4.0% | **147.3%** |
| +50% fees/slippage: net P&L | −$1,038.98 | — | −$9,003.21 | +$2,098.81 |
| +50% fees/slippage: expectancy | −$17.03 | — | −$13.66 | +$34.98 |
| Month-clustered 95% CI (mean trade P&L) | −$13.09 ± $31.15 | — | **−$7.91 ± $7.84** | +$22.44 ± **$129.11** |

### Per month

| Month | S001 n / net | S009 n / net | S011 n / net |
|---|---:|---:|---:|
| 2024-02 | 15 / −$248.53 | 174 / −$2,322.39 | 14 / −$687.42 |
| 2024-04 | 16 / +$174.62 | 200 / −$1,326.86 | 25 / **+$3,076.61** |
| 2024-09 | 19 / −$191.74 | 138 / −$243.38 | 11 / −$410.41 |
| 2025-12 | 11 / −$402.62 | 147 / −$1,454.19 | 10 / +$531.19 |

S009: net P&L negative in **4 of 4** months. S011: net P&L positive in
only **2 of 4** months, and 2024-04 alone (n=25, only 3 winners)
supplies +$3,076.61 of the pooled +$2,509.97 — without that one month
the other three months net to **−$566.64**.

## 3b. S011 evidence, in full (requested detail)

- **Exact net total** (pooled, 4 TRAIN months, funding-inclusive): **+$2,509.97**, n=60.
- **The single most influential trade**: LONG, entry $120.20 → exit
  $151.17 (TAKE_PROFIT, POC-target), opened 2024-04-13 20:09 UTC.
  - **Signed contribution: +$3,697.54.**
  - **Original R**: risk unit R0×quantity = $89.40; this trade closed
    at **+41.36R** — the take-profit is the current period's own
    `poc_price`, structurally uncapped (unlike the other candidates'
    fixed 2R), so a single trade reaching a distant POC can post an
    R-multiple far outside the ±1R/2R range every other result in this
    project's history has used.
  - **147.3% of the pooled net total** by itself.
- **Leave-one-out net total** (excluding only this one trade):
  **−$1,187.58**, n=59 — i.e., **the entire pooled result is
  attributable to this single trade; without it, S011's TRAIN result
  is negative.**
- **Month-clustered 95% CI — exact estimand stated**: the population
  mean of S011's own per-trade net P&L in USD (funding-inclusive),
  estimated as the unweighted mean of the 4 TRAIN months' own
  per-trade-P&L means (one cluster mean per month, this project's
  standing 4-cluster/t-distribution-df=3 convention). Per-month means:
  2024-02 = −$49.10, 2024-04 = +$123.06, 2024-09 = −$37.31,
  2025-12 = +$53.12. Point estimate **+$22.44/trade**, cluster SE
  $40.57, **95% CI = [−$106.66, +$151.55] per trade**.
- **Concentration, described factually**: the top 3 trades by
  |P&L| (+$3,697.54, +$1,694.75, +$600.35) sum to **238.8% of the
  pooled net total** — meaning the remaining 57 trades are net
  negative in aggregate. This is **consistent with either** a genuine,
  occasionally-large POC-target payoff (a real property of this
  candidate's own uncapped-target design) **or** a small-sample
  outlier dominating an otherwise-flat-to-negative population — at
  n=60 with this concentration, **the data cannot distinguish the two
  explanations; neither is asserted over the other.**

## 4. Interaction analysis (completed — §5 of the protocol)

**What was wrong originally, precisely**: S009's opportunity capture
derived `direction` from `result.direction`, a field the Setup only
populates once the full candidate has fired (both the progress and
confirmation conditions satisfied). This silently collapsed the
intended "base" / "base+progress" / "full" nested slices to the same
fired-only subset — the report's own §4 originally disclosed this as
a limitation rather than presenting misleading identical numbers, but
did not fix it. It is fixed below.

**The fix**: `strategy/research/multi_module_opportunity_population.py`
now peeks `setup._pending` — the causal excursion state the Setup
already maintains internally, fixed at the PRIOR bar, strictly before
the current bar's own progress/confirmation conditions are evaluated
— immediately before calling `evaluate()`. This is a read-only
observation of state the Setup was already carrying, never a second
implementation of the trigger logic and never information from a
later bar or a successful signal. `tests/test_multi_module_opportunity_capture_observer.py`
proves directly (not by assumption) that this peek does not alter the
Setup's own `fired`/`direction`/`reasoning` sequence, run bar-for-bar
against a plain (unobserved) run of the same setup on the same
snapshots.

**S011 was re-audited, not bugged the same way**: its capture already
derived direction from the extension condition's own evidence
(present regardless of fire status), not from `result.direction`. What
IS genuinely unidentifiable is the "regime-only, no extension" layer:
the base opportunity definition (RANGE regime + a forming profile)
does not by itself imply any direction or reference risk — there is no
principled "which way would this trade go" answer without the
extension condition's own boundary read. This is a **structural
property of the candidate's own design**, not a measurement bug —
reported below as an explicit, counted exclusion (2,338 regime-only
bars across 4 months) rather than silently omitted or scored with an
invented direction rule.

### 4a. Completed opportunity-population comparisons (diagnostic — 4 TRAIN months, forward first-passage, 50-bar horizon)

All figures below use a 95% Wilson-score CI on the resolved favorable
rate (exact, since a normal approximation is unreliable at some of
these small resolved-n counts).

**S009** (now correctly differentiated):

| Population | n total | n resolved | % resolved | Favorable rate | 95% CI |
|---|---:|---:|---:|---:|---:|
| Base (pending excursion exists) | 4,390 | 3,229 | 73.6% | 50.6% | [48.9%, 52.3%] |
| Base + progress (closes further) | 2,281 | 1,714 | 75.1% | 50.8% | [48.4%, 53.1%] |
| Full (fired: progress + confirmation) | 1,159 | 925 | 79.8% | 52.4% | [49.2%, 55.6%] |

Excluded: 15 bars where entry price equaled the excursion close
exactly (undefined reference risk, r_unit=0) — a genuine, disclosed
exclusion, not folded into either the numerator or denominator.

**Reading this honestly**: the progress condition alone adds almost no
diagnostic separation (50.6% → 50.8%, fully overlapping CIs) — this
now-correctly-measured population confirms, rather than merely
asserts, that S009's real economic contribution (§4b) comes almost
entirely from the confirmation (delta) condition, not the progress
condition, which is the opposite of what an uncorrected reading might
have suggested. The full layer's own CI [49.2%, 55.6%] still overlaps
the base layer's [48.9%, 52.3%] — **an observed uplift (50.6%→52.4%),
not proof of a real interaction effect** at this sample size.

**S011**:

| Population | n total | n resolved | % resolved | Favorable rate | 95% CI |
|---|---:|---:|---:|---:|---:|
| Regime-only (no extension) | 2,338 | — | — | **not identifiable** (no direction/risk defined) | — |
| Base+extension (smallest identifiable population) | 723 | 264 | 36.5% | 50.8% | [44.8%, 56.7%] |
| Full (fired: extension + CVD exhaustion) | 41 | 13 | 31.7% | 84.6% | [57.8%, 95.7%] |

**Reading this honestly**: the jump from 50.8% to 84.6% is a large
observed uplift, but the full layer's own CI is built on only 13
resolved outcomes — its lower bound (57.8%) barely clears the base
layer's upper bound (56.7%). This is **suggestive, not confirmatory**:
consistent with CVD exhaustion doing real discriminating work here,
and equally consistent with a small-sample artifact given how few
resolved observations exist at this final layer. The regime-only
population (2,338 bars) is reported for completeness (it establishes
how much of the "RANGE regime" base is even reachable) but is not, and
cannot be, scored on the same forward-outcome yardstick — explained,
not presented as a null result.

**S008** (unchanged from the original report — re-verified correct):

| Population | n total | n resolved | % resolved | Favorable rate | 95% CI |
|---|---:|---:|---:|---:|---:|
| Base (impulse_strength >= 1.0) | 11,452 | 958 | 8.4% | 56.9% | [53.7%, 60.0%] |
| Base + touch==1 | 4,237 | 202 | 4.8% | 67.3% | [60.6%, 73.4%] |
| Full (fired) | 1 | 1 | 100% | 100% | [20.7%, 100%] (n=1, uninformative) |

Full funnel and explanation of these two named populations: §5.

### 4b. Completed sequential comparisons (real executable backtests — predeclared ablations)

Per the frozen protocol's own instruction ("conditions that change
entry eligibility also require real sequential backtests to measure
executable results"), the diagnostic slicing above cannot substitute
for an executable comparison when a condition is REMOVED from gating
(that changes which bars actually become trades). Two predeclared
ablations were added as constructor flags on the existing candidate
classes (`S009FailedAuctionReversalSetup(require_confirmation=False)`,
`S011ValueAreaFadeSetup(require_cvd_confirmation=False)`) — same
thresholds, same timing, same risk/cost conventions as the frozen
candidates; only which condition gates firing changes. Run via
`strategy/research/multi_module_ablation_backtest.py`, same 4 TRAIN
months, funding-inclusive.

| | S009 progress-only (ablation) | S009 full (frozen) | S011 extension-only (ablation) | S011 full (frozen) |
|---|---:|---:|---:|---:|
| n | 731 | 659 | 489 | 60 |
| Win rate | 33.1% | 36.6% | 24.3% | 26.7% |
| Profit factor | 0.787 | 0.885 | 0.848 | 1.459 |
| Net P&L | −$10,328.44 | −$5,346.82 | −$6,137.77 | +$2,509.97 |
| Expectancy/trade | −$14.13 | −$8.11 | −$12.55 | +$41.83 |
| Confirmation pass-through rate | — | 90.2% of ablation trades | — | 12.3% of ablation trades |

**Distinguishing observed uplift from evidence of a real interaction**,
per candidate:

- **S009's confirmation condition (delta) shows a real, measurable,
  but modest improvement**: expectancy moves from −$14.13 to −$8.11
  (+$6.02/trade), removing roughly 1 in 10 trades. The confirmation
  condition is doing genuine, directionally-consistent work — it
  removes trades that would otherwise be worse — but this improvement
  is nowhere near large enough to flip the candidate positive. This is
  an observed uplift with real support (both the ablation backtest and
  the diagnostic base-vs-full gradient point the same direction),
  correctly distinguished in §4a from an unsupported claim of "the
  filter works."
- **S011's CVD confirmation condition shows a much larger swing**
  (expectancy −$12.55 → +$41.83, +$54.38/trade) but is far more
  aggressive (passes only 12.3% of extension-only candidates through,
  vs. S009's 90.2%) — a much smaller, more selected final population.
  Combined with §3b's own finding (the entire positive full-candidate
  result depends on one 41R trade), **this large swing cannot be
  distinguished from a small-sample selection effect concentrated in
  very few trades** — it is reported as an observed association, not
  evidence of a real interaction, consistent with §4a's own CI
  overlap finding.
- **The extension-only ablation is itself clearly negative** (−$12.55/trade,
  n=489) — confirming that the base "trigger+context" layer alone
  (RANGE regime + magnitude extension, no order-flow confirmation) is
  not a standalone edge for either candidate; whatever value either
  candidate has (S009 weakly, S011 possibly) comes from the
  confirmation layer, not the base trigger.

## 5. Why S008 essentially never fires — condition funnel (units and timing verified)

All counts pooled across the 4 TRAIN months, all timestamps/units
already-closed 15m bars (no future data at any stage — each stage is a
`ConditionResult.satisfied` flag read directly off the real
`S008DisplacementContinuationSetup.evaluate()` call, not a
re-implementation):

| Stage | n bars | % of prior stage | % of total 15m bars |
|---|---:|---:|---:|
| Total 15m bars (4mo) | 11,516 | — | 100% |
| Bar has >= 1 active Order Block | 11,468 | 99.6% | 99.6% |
| + `impulse_strength >= 1.0` on that block | 11,452 | 99.9% | 99.5% |
| + `touch_count == 1` (first retest) | 4,237 | 37.0% | 36.8% |
| + price inside active (`!= fully_mitigated`) mitigation zone | 6 | 0.14% | 0.05% |
| + all three simultaneously (fired) | 1 | 16.7% | 0.009% |

**Which population produced which figure, exactly**:
- **56.9%** is the resolved favorable rate of the **"impulse_strength
  >= 1.0" stage** (n=11,452 opportunity bars) — but only **958 of
  those (8.4%) ever resolve** (hit either the +1R or −1R forward
  first-passage level) within the 50-bar diagnostic horizon; the
  remaining 91.6% hit `NO_RESOLUTION`. 56.9% is the favorable share of
  the 958 that DID resolve, **95% Wilson CI [53.7%, 60.0%]** — not a
  claim about the full 11,452.
- **67.3%** is the same computation restricted to the **"+ touch==1"
  stage** (n=4,237 bars), of which **202 (4.8%) resolve**, **95%
  Wilson CI [60.6%, 73.4%]**. The CIs of the two stages do not
  overlap (53.7–60.0% vs. 60.6–73.4%), a genuine, if small-sample,
  gradient.
- **impulse_strength >= 1.0 is satisfied on 99.5% of all 15m bars with
  an active Order Block** — SOL's own impulse-strength distribution
  makes this threshold almost never binding, contrary to the original
  design's assumption that it would be a meaningful filter.
- **The true binding constraint is mitigation-zone containment**:
  37.0% of impulse-qualifying bars also have `touch_count == 1`, but
  only **6 of those 4,237** (0.14%) also have price inside the
  (narrow, origin-candle-body) mitigation zone. Minimum observed
  distance between price and the mitigation zone's own boundary, at
  the exact moment all of impulse/touch already held, was as small as
  0.01–0.09% of price across 3 of 4 TRAIN months — extremely close,
  but the zone is narrow enough relative to normal SOL bar ranges that
  price's close essentially never lands inside it on the exact bar
  that also registers the qualifying first touch.
- **Setup parameters were kept unchanged throughout** (`IMPULSE_THRESHOLD
  = 1.0`, `touch_count == 1`, no threshold relaxed to generate trades)
  — this funnel measures the frozen candidate exactly as designed, not
  a loosened variant.

This is disclosed as a genuine structural characteristic of Order
Block mitigation-zone width vs. SOL's own volatility — not the
already-known A1/A2 tracker defects (which remain unresolved and are
carried forward as a separate, disclosed limitation per the frozen
protocol).

## 6. Decision, applying the frozen criteria (§6 of the protocol)

**Unchanged from the original report, now on a completed evidentiary
basis** (§4/§5 resolve the measurement gaps; no new evidence in this
revision moved any candidate across a decision boundary):

- **S008 — cannot be evaluated (0 trades).** Per the frozen
  falsification rule, archived as "needs more data / structurally too
  rare on this instrument," not rejected on economic grounds (none
  exist to reject). The underlying displacement hypothesis itself is
  not refuted — its own funnel (§5) and diagnostic gradient (§4a) point
  the right direction on a small, if non-overlapping-CI, sample — but
  the specific mitigation-zone-entry mechanism as designed cannot be
  tested on SOL TRAIN at this threshold.
- **S009 — Unsupported hypothesis.** Negative after-cost expected
  value in 4 of 4 TRAIN months (the frozen criterion's own bar is
  ≥3/4). The month-clustered 95% CI's upper bound (+$0.07) technically
  touches zero, but weighed against 4/4-month consistency, n=659, a
  55.8% max drawdown (economically disqualifying on its own), and the
  now-completed ablation showing the confirmation condition's own real
  but modest contribution (+$6.02/trade, §4b) cannot close a
  −$14-to-−$8 gap into positive territory, the weight of evidence
  supports **unsupported**, not merely insufficient — stated plainly
  rather than mechanically deferring to the CI's hairline overlap.
- **S011 — Insufficient evidence.** Fails the frozen "≥3/4 months"
  requirement for positive classification (2 of 4 positive). §3b's
  completed evidence sharpens, rather than changes, this call: the
  **entire pooled result is one 41.36R trade** (leave-one-out net =
  −$1,187.58) and the diagnostic full-layer CI [57.8%, 95.7%] barely
  clears the base layer's own upper bound — both independently
  disqualify treating the attractive pooled PF/expectancy as reliable.
  Genuinely open, not rejected — a larger sample or a capped/structural
  take-profit (rather than the uncapped POC target, which is this
  candidate's own source of concentration) could resolve this
  differently in the future, but that is a new experiment, not
  authorized here.

**No candidate is recommended for a frozen VALIDATION experiment —
unchanged.**

## 7. Module contribution

- **Order Block `impulse_strength`**: not discriminating at the
  `>= 1.0` threshold on SOL (98% pass rate) — the threshold itself, not
  the field, needs reconsideration in any future attempt, informed by
  SOL's own impulse distribution rather than the BTC-derived "1x ATR"
  assumption.
- **Order Block `mitigation_zone`**: the true binding constraint for
  S008 — too narrow relative to SOL's bar ranges to coincide with a
  qualifying touch. A future variant might trial the outer (wick) zone
  instead, disclosed here as a candidate follow-up, not attempted.
- **Value Area boundary (progress condition)**: essentially no
  standalone contribution — the diagnostic base-vs-base+progress
  gradient is flat (50.6% vs 50.8%, fully overlapping CIs, §4a), and
  the extension-only-style ablation logic (progress alone would be
  this layer) is consistent with that null.
- **Delta `delta_strength`** (S009's confirmation condition): the
  weaker-then-stronger participation asymmetry is real and measurable
  — the predeclared ablation backtest (§4b) shows it improves
  expectancy by +$6.02/trade (−$14.13 → −$8.11) while removing ~10% of
  trades, a genuine, directionally-consistent, but modest contribution
  that does not survive contact with realistic frequency/drawdown/cost
  accounting — an example of this project's own recurring finding
  (module_decision_register.md §E) that a real, measurable pattern
  does not automatically imply a tradeable edge.
- **RANGE regime gate + Value Area extension** (S011's base+context):
  the predeclared ablation backtest (§4b) shows this layer ALONE is
  clearly negative (−$12.55/trade, n=489, WR 24.3%) — the regime and
  magnitude conditions are not, by themselves, a standalone edge.
- **CVD exhaustion** (S011's confirmation condition), still
  E1-INCONCLUSIVE at the unconditional level in the module decision
  register, was tested here under a genuinely new conditional (RANGE +
  magnitude extension). The ablation shows a large associated swing
  (+$54.38/trade) but passes only 12.3% of extension-only candidates
  and, combined with §3b's single-trade concentration finding, **the
  result remains inconclusive rather than confirming or rejecting
  CVD's value** — the swing is real in the data but not distinguishable
  from a small-sample selection effect at this n.

## 8. Excluded candidate — S010

Not built, consistent with `docs/phase4_setup_expansion_research_design.md`'s
own risk assessment, re-confirmed unchanged: the 3-part sequence
(unbounded-lookback breakout event, retest-hold, value migration) has
no principled lookback bound and was independently flagged as the most
likely to simply not fire enough to test — nothing this sprint found
changes that assessment.

## 9. Preserved boundaries

Progressive-stop Policy D remains frozen at INSUFFICIENT EVIDENCE, not
reopened. No FVG/IFVG logic was touched. No portfolio-level
(multi-setup, first-fired-wins) evaluation was run — every candidate
was tested strictly standalone, as required. No new SOL period was
accessed (only the 4 already-registered TRAIN months); FINAL_HELD_OUT
and VALIDATION remain untouched. No production file was modified.

## 10. Tests and changed files

**Full suite: 1196 passed, 0 failed** (1186 prior + 8 predeclared-ablation
unit tests + 2 opportunity-capture-observer tests). S001
control-equivalence test
(`test_s001_control_runs_unaffected_by_new_research_modules_present`)
still passes unmodified — confirms none of this completion pass's new
code changes S001's own result.

Changed/added files this completion pass (all uncommitted):
- `strategy/research/setups/s009_failed_auction_reversal.py` — added
  `require_confirmation` constructor flag (default `True`, matching
  frozen/production behavior exactly)
- `strategy/research/setups/s011_value_area_fade.py` — added
  `require_cvd_confirmation` constructor flag (default `True`, matching
  frozen/production behavior exactly)
- `strategy/research/multi_module_opportunity_population.py` — repaired
  (S009's direction/risk now derived causally from `setup._pending`,
  peeked before `evaluate()`; S011 re-audited and its structural
  regime-only limitation now explicitly counted, not silently omitted)
- `strategy/research/multi_module_ablation_backtest.py` (new) —
  predeclared ablation backtest driver (§4b)
- `tests/test_multi_module_opportunity_capture_observer.py` (new) —
  proves the capture's observer does not alter Setup decisions
- `tests/test_s009_failed_auction_reversal_setup.py`,
  `test_s011_value_area_fade_setup.py` — added ablation-flag tests
- `docs/sol_multi_module_setup_research_report.md` (this document)

Unchanged from the original delivery: `strategy/research/setups/s008_displacement_continuation.py`,
`strategy/research/multi_module_backtest_adapter.py`,
`strategy/research/multi_module_standalone_backtest.py`,
`tests/test_s008_displacement_continuation_setup.py`,
`tests/test_multi_module_setups_causal_and_control.py`,
`docs/sol_multi_module_setup_research_protocol.md` / `.sha256` (frozen,
hash still verified unchanged).

**Experiment manifest / reproducibility**: primary driver scripts live
in the repository (uncommitted), per the recoverability lesson from
the Exit-Policy State Isolation audit earlier this session — not
scratchpad-only:
- [`strategy/research/multi_module_standalone_backtest.py`](../strategy/research/multi_module_standalone_backtest.py)
  — produces §3's results. `python -m strategy.research.multi_module_standalone_backtest`.
- [`strategy/research/multi_module_opportunity_population.py`](../strategy/research/multi_module_opportunity_population.py)
  — produces §4a's repaired opportunity population.
  `python -m strategy.research.multi_module_opportunity_population`.
- [`strategy/research/multi_module_ablation_backtest.py`](../strategy/research/multi_module_ablation_backtest.py)
  (new) — produces §4b's ablation results.
  `python -m strategy.research.multi_module_ablation_backtest`.

The funnel/evidence-clarity aggregation scripts (S008 funnel, S011
evidence-clarity, ablation-vs-full stats — simple pickle-to-table
computations directly over the pkl schemas the three scripts above
produce) remain session-scratchpad-only — trivially reconstructable
from the field names shown in §3b/§4/§5's own tables, not themselves a
record of any defect or decision.
