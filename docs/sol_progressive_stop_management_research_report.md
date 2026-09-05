# SOL Progressive Stop Management Research

**Status: bounded research sprint. No production strategy default
modified, no new setup, no leverage/take-profit change, no data
purchase, no VALIDATION/FINAL_HELD_OUT access.** Repository baseline:
the completed funding/source re-analysis report and frozen protocol
(uncommitted at sprint start, per that sprint's own instructions).
Frozen protocol for this sprint:
`docs/sol_progressive_stop_management_protocol.md`, SHA-256
`d24f43255bbc26df541fde29da6db2594688827155b211f29bc103a4c53e6e99`
(revised once, before any outcome was computed, to ground its PBO/CSCV
discussion in the actual paper the user supplied mid-sprint — see
Section 8). Full test suite: **1153 passed, 0 failed** (1119
pre-existing + 34 new, including 2 regression tests added by the
correction below). Python 3.13.14. SOL TRAIN months only: 2024-02,
2024-04, 2024-09, 2025-12.

---

## CORRECTION (post-delivery, before advancing to Hypothesis 2)

The version of this report first delivered contained **two errors**,
found and fixed via a direct numerical reconciliation the user
requested before this sprint could close. Both are corrected
throughout the sections below; nothing else in this report changed.

**1. A real simulation defect, confirmed and fixed.** `StaircaseExitPolicy`
(`strategy/research/progressive_stop_policies.py`) originally keyed its
per-trade state (R0, running MFE, current stop level) by `id(trade)`.
The **paired comparison** (Section 4.1) creates a fresh policy instance
per trade and was never affected. The **sequential standalone backtest**
(Section 4.2) reuses ONE policy instance across every trade in a month
(15–23 trades) — and CPython reuses an object's `id()` once it is
garbage collected, which happens routinely between a closed trade and
the next one opening (confirmed empirically: 10 of 20 ids collided in
a direct 20-object reproduction). A collision silently handed a new,
unrelated trade the OLD trade's stale R0/MFE/stop state. **Fixed** by
storing state as an attribute directly on the trade object itself
(`SimulatedTrade` is a plain, `__slots__`-free mutable dataclass —
dynamic attribute assignment is safe) instead of an `id()`-keyed
external dict, eliminating the lookup key — and therefore the
collision — entirely. Two new regression tests
(`test_reused_policy_instance_does_not_leak_state_across_trades_via_id_reuse`,
`test_two_trades_with_colliding_ids_get_independent_state_directly`)
guard against a recurrence. **The sequential backtest (Section 4.2) was
re-run with the fix; the paired comparison (Section 4.1) did not need
to be, and its own numbers are unchanged.**

**2. An interpretation error in the concentration narrative**, present
even before the bug fix and corrected independently of it. The
originally-delivered report described the single largest-magnitude
paired trade (a control winner cut short into a loss, Section 5) as
explaining "94.8% of Policy D's entire paired-comparison net effect,"
implying the positive $276 result was manufactured by that one trade.
**This is backwards.** That trade's own contribution is *negative*
(−$261.66) — it suppresses the net total, it does not create it.
Excluding it *increases* the net effect (to ≈$538), it does not
eliminate it. The 94.8% figure is a correct, literal application of
the frozen protocol's own concentration formula (`largest single
|trade diff| ÷ |net aggregate|`) — but that formula measures
**sensitivity of a small net figure to a large adverse outlier**, not
**concentration of the benefit itself**. Both are now reported
separately (Section 4.1).

**Combined effect on the conclusion**: with the bug fixed, Policy D's
sequential (system-level) result is now **materially better than
originally reported** (net P&L improves from −$672.92 to −$397.48, not
to −$709.73) and now closely matches its own paired-comparison result,
as it logically should once entry/state handling is correct — but the
concentration/sensitivity finding, now correctly interpreted, still
means this positive result does not meet the frozen bar for "evidence
of improved net expectancy." The corrected verdict for Policy D is
**INSUFFICIENT EVIDENCE**, not "no supported improvement" as originally
stated (Section 9). Verdicts for B and C are unchanged.

---

**Hypothesis tested, not assumed**: gradually reducing original
downside as a trade moves favorably may improve net expectancy or
reduce drawdown. **Corrected result**: Policies B and C show no
supported improvement, consistent with the completed Exit Management
Sprint's own REJECT verdict on a discretionary structure-based trail.
Policy D shows a real, paired-and-sequential-consistent positive point
estimate that does **not** survive the pre-registered concentration
safeguard, and its confidence interval includes zero — **insufficient
evidence**, genuinely open, neither confirmed nor rejected.

## 1. Baseline

Read in full before implementation: `docs/sol_funding_source_reanalysis_report.md`
(funding overlay methodology and conventions, reused unchanged here),
`docs/exit_management_research_sprint_report.md` and
`docs/exit_management_sprint_causal_correction_addendum.md` (the prior,
discretionary structure-based trail — REJECT STRUCTURE TRAIL, 6/6
configurations worse, mechanism: "protects some losses, sacrifices
more/larger winners than it rescues" — the exact risk this sprint's own
hypothesis needed to be tested against, not assumed away).

S001 standalone, unchanged entry logic, position sizing, initial stop,
and take-profit across all four policies — verified directly: the
control ledger reproduced in this sprint matches every previously
published S001 TRAIN result exactly (61 trades, net P&L −$672.92,
byte-identical, re-confirmed twice: once via a direct re-run, once via
the sequential-backtest harness's own Policy-A path).

`backtesting/exit_policy.py`'s causally-corrected two-phase
`apply_pending`/`evaluate` contract is reused **unchanged** — the same
infrastructure the Exit Management Sprint's own addendum fixed and
re-verified. R0 = `|entry_price − original_stop_loss|`, captured once
per trade, never recalculated from a tightened stop (verified directly
by test, Section 7).

## 2. The four policies

| | Rule | Implementation |
|---|---|---|
| A — Control | Existing fixed stop/TP, unchanged | `exit_policy=None` |
| B — Quarter-R staircase | `step_size=0.25R`, tighten `0.25R` per step | `StaircaseExitPolicy(0.25, 0.25)` |
| C — Half-R staircase | `step_size=0.50R`, tighten `0.50R` per step | `StaircaseExitPolicy(0.50, 0.50)` |
| D — Slower quarter-R staircase | `step_size=0.25R`, tighten `0.125R` per step | `StaircaseExitPolicy(0.25, 0.125)` |

One parameterized `StaircaseExitPolicy`
(`strategy/research/progressive_stop_policies.py`) implements all
three via `stop_R(MFE_R) = −1.00 + floor(MFE_R/step_size) × tighten_per_step`,
clamped monotonic (never loosens — verified by dedicated test,
Section 7), long/short mirrored (verified), take-profit never touched.
**These are declared research candidates, not claimed-optimal
settings — the parameter set was not expanded after seeing results.**

## 3. Execution timeframe, timing, and gap handling

**Execution timeframe: 1-minute**, inherited unchanged from the
existing infrastructure — confirmed by direct reading of
`backtest_runner.py` (lines 414–493): the replay clock, the
`apply_pending`/`process_candle`/`evaluate` sequence, and
`ExecutionSimulator`'s own stop/target check all operate on 1-minute
candles, exactly as every existing S001 result in this project already
has (entries are 15m-signal-derived; stop/target resolution has always
been 1-minute — previously true but undocumented, made explicit here).

- **Next-bar activation**: reused unchanged, verified by test
  (`test_stop_change_is_not_applied_on_the_same_bar_it_was_decided`).
- **Entry-bar exclusion**: `apply_pending`/`evaluate` are structurally
  never called for a trade's own entry bar — pre-entry/entry-bar
  movement is excluded from MFE tracking by construction, verified by
  test.
- **Gap and already-breached-on-activation handling**:
  `ExecutionSimulator.process_candle` fills a stop exit at exactly
  `trade.stop_loss` regardless of how far the triggering candle's
  low/high undercuts it — no gap-through worse-fill modeling exists in
  the simulator, for **any** policy including the control (a
  pre-existing, disclosed limitation — `docs/profitability_root_cause_investigation.md`,
  Section 2, item 8). Not modified here (out of scope). Instead,
  `strategy/research/gap_aware_stop_fill.py` recomputes, as a
  **symmetric, post-hoc sensitivity check**, what the fill would have
  been if the exiting candle's own open had already gapped past the
  stop — using the candle's open as the realistic worst executable
  price. Applied to every stop-loss exit across all four policies:
  **0 of 61 control exits and 0 of the candidate-policy paired exits
  showed a gap at the triggering candle's own open** in these 4 TRAIN
  months — the sensitivity check found no case where it would have
  changed a result, disclosed as a real (if here, empirically
  non-binding) assumption rather than silently ignored.
- **Tick-size rounding**: stop prices rounded to 2 decimal places — a
  disclosed, reasonable assumption for SOL's TRAIN-period price range,
  not verified against Binance's exact historical tick size.

## 4. Direct effect (paired comparison) vs. system effect (sequential backtest)

### 4.1 Paired comparison — identical control entries, independent exits, slot-free

Each of the 61 control trades' own fixed entry (price, side, quantity,
original stop, original TP) was replayed candle-by-candle under each
policy independently, using `strategy/research/paired_trade_simulator.py`
(mirrors `backtest_runner.py`'s own per-bar ordering exactly — verified
by test). This isolates the direct exit effect from any
slot-availability confound.

| Policy | n | Improved | Worsened | Unchanged | Net $ | Mean R diff | Month-clustered mean ± half-width (df=3) |
|---|---|---|---|---|---|---|---|
| B | 61 | 26 | 13 | 22 | **−$567.49** | −0.0944 | −0.087 ± 0.184 |
| C | 61 | 20 | 11 | 30 | **−$332.04** | −0.0561 | −0.061 ± 0.209 |
| D | 61 | 26 | 3 | 32 | **+$276.04** | +0.0433 | +0.052 ± 0.344 |

**Losses reduced vs. winners closed early:**

| Policy | Baseline losses (n=39) reduced | Baseline winners (n=22) closed early | …of which turned into losses | $ saved from reduced losses | $ sacrificed from early-closed winners |
|---|---|---|---|---|---|
| B | 26 | 13 | 6 | +$1,743.96 | −$2,311.45 |
| C | 20 | 11 | 5 | +$1,590.56 | −$1,922.60 |
| D | 26 | 3 | 3 | +$946.76 | −$670.72 |

**Per-month direction (paired $ diff)**: B — negative in 3/4 months
(Feb −89.63, Apr −407.17, Sep −88.12; positive only Dec +17.42). C —
negative in 3/4 (Feb −114.69, Apr −362.91, Dec −34.30; positive only
Sep +179.87). D — positive in 3/4 (Feb +215.33, Sep +278.41, Dec
+219.53; negative only Apr −437.23).

**Concentration — corrected: two distinct questions, not one.** The
frozen protocol's own criterion (`docs/sol_progressive_stop_management_protocol.md`)
reads "not resting on 1–2 exceptional trades (concentration check <50%
of the aggregate effect from any single trade)." Applied **literally**
(largest single trade's own |diff|, divided by the |net aggregate|,
regardless of that trade's sign) this concerns **absolute**
contributions, and is the number this report already computed
correctly: B 47.3% (passes, narrowly), C 74.9% (**fails**), D 94.8%
(**fails decisively**). What the originally-delivered report got wrong
was the **narrative attached to D's own number** — it described the
94.8% figure as if that trade were the *source* of the $276 benefit.
It is not: that trade's own delta is **−$261.66** (a control winner,
+$180.12, cut short by D into a loss, −$81.54 — Section 5). Recomputing
the positive and negative sides **separately** shows why this matters:

| Policy | Positive contributions (n, sum) | Largest single positive, as % of positive sum | Negative contributions (n, sum) | Largest single negative, as % of negative sum |
|---|---|---|---|---|
| B | 26, +$1,743.96 | 15.4% | 13, −$2,311.45 | 11.6% |
| C | 20, +$1,590.56 | 15.6% | 11, −$1,922.60 | 12.9% |
| D | 26, +$946.76 | **8.3%** | 3, −$670.72 | **39.0%** |

**D's own benefit (positive) side is the least concentrated of all
three policies (8.3%, spread across 26 trades)** — not a case of one
lucky trade. What actually fails the frozen check is D's **negative**
side: only 3 trades, summing to −$670.72, and the largest of those
three (−$261.66) is a large fraction of that small negative pool.
**Leave-one-out, verified directly against the saved paired-comparison
data**: excluding that single trade raises D's net from +$276.04 to
**+$537.70** (net_total − worst_trade_delta = 276.04 − (−261.66) =
537.70) — confirming the 94.8% figure signals **sensitivity of a small
net total to a large adverse outlier**, not "concentration of benefit."
This distinction matters for what conclusion it supports: it does
**not** mean D's apparent edge is fabricated by one trade — the benefit
is real and broad-based. It **does** mean the *net* figure is fragile:
a slightly different sample (one more, or one fewer, trade like the
three April outliers below) would move the net total by hundreds of
dollars, comfortably enough to change its sign. **The frozen criterion,
applied exactly as written, still fails for D** — the corrected reason
is fragility to a small number of large adverse trades, not a
fabricated benefit.

All three of D's negative-side trades are concentrated in **2024-04**,
**all SHORT**, **all originally reached the full take-profit under
control** before being cut short into a loss by the staircase
(2024-04-01, 2024-04-05, 2024-04-23 — Section 5 details the largest).
This is a coherent, month-and-direction-concentrated pattern — a real
regime feature of that one month, not a single random fluke — worth
carrying forward as a specific, falsifiable detail (Section 11), not
just a generic "small sample" caveat.

**Directional consistency**: B's effect is concentrated in SHORT trades
(SHORT: −$571.58 over 45 trades; LONG: +$4.08 over 16, essentially
flat). D's effect is concentrated in LONG trades (LONG: +$228.10 over
16; SHORT: +$47.94 over 45, comparatively small) — neither policy's
effect is evenly distributed across direction.

### 4.2 Sequential standalone backtest — the additional (system) effect

Each policy run through the real, unmodified `BacktestRunner.run_strategy(..., exit_policy=...)`
end to end. Earlier/later exits change when the single trade slot frees
up, so entries diverge from the control after the first exit whose
timing changed — reported as its own, separate effect, never conflated
with Section 4.1's direct-exit numbers.

**Corrected** (the version originally delivered used the buggy exit
policy — see the correction notice at the top of this report; every
number below is from the re-run with the `id()`-collision fixed):

| Policy | n (vs. control's 61) | Win rate | PF | Net P&L | Expectancy | Mean net R | Max DD $ (equity-curve) | Max DD % | Exposure % |
|---|---|---|---|---|---|---|---|---|---|
| A (control) | 61 | 36.1% | 0.853 | −$672.92 | −$11.03 | −0.100 | $770.65 | 7.63% | 3.44% |
| B | 68 (+7) | 30.9% | 0.638 | −$1,194.03 | −$17.56 | −0.169 | $1,243.45 | 12.37% | 1.74% |
| C | 64 (+3) | 29.7% | 0.714 | −$945.10 | −$14.77 | −0.141 | $994.53 | 9.90% | 1.92% |
| D | 61 (+0) | 31.1% | 0.895 | **−$397.48** | **−$6.52** | **−0.057** | $814.66 | 8.08% | 2.83% |

**B and C remain worse than control on every metric**, including
drawdown — smaller in magnitude than the buggy run suggested, but the
same direction and the same conclusion. **D is genuinely different from
what was originally reported**: it now shows **improved** net P&L,
expectancy, and profit factor relative to control (net P&L −$397.48 vs.
−$672.92; expectancy −$6.52 vs. −$11.03; PF 0.895 vs. 0.853) — but
**worse** max drawdown (8.08% vs. 7.63%). This is a real, specific,
non-generic finding: **D improves realized return without reducing
risk** — the opposite pairing from the frozen protocol's own "risk
reduction accompanied by lower returns" category, and worth stating
precisely rather than folding into either "improved" or "no
improvement" without qualification.

**Reconciling paired vs. sequential, by shared/lost/newly-admitted
entries** (exact match on `(month, entry_timestamp, side)`, verified
directly against both saved ledgers): for **D**, all 61 sequential
trades are identical, entry-for-entry, to the 61 paired/control
entries — **0 lost, 0 newly admitted**. The tighter-but-gentle D
staircase never changes when the single trade slot frees up relative
to control, so the paired and sequential comparisons now coincide
almost exactly (+$275.44 sequential vs. +$276.04 paired — the ~$0.60
gap is ordinary floating-point/candle-window noise between the two
harnesses, not a further defect). **B loses 1 of control's own entries
and admits 8 new ones** (60 shared, net effect on the shared entries
alone: −$688.45); **C admits 3 new entries with 0 lost** (61 shared,
net effect on shared entries: −$323.32) — both consistent with more
aggressive tightening closing trades faster on average and therefore
freeing the slot for additional, generally lower-quality entries, the
same mechanism identified in the original (buggy) run, just smaller in
magnitude now that the state-leakage inflation is removed.

MAE/MFE (independent excursion maxima) were used only to construct
each trade's own MFE_R for the staircase trigger logic itself — never
substituted for either comparison above, per the frozen protocol.

## 5. Worked trade examples

**A loss meaningfully reduced (Policy D, 2024-09-09 19:54 SHORT,
R0=0.836)**: control ran to its full original stop, −$115.81. Policy D's
staircase caught the retracement earlier, exiting at −$53.66 (paired) /
−$54.15 (sequential, corrected — the small difference is ordinary
cross-harness float/candle-window noise, not a defect) — roughly
halving the loss, exactly the mechanism the hypothesis predicts. This
is one of 26 trades on D's positive side, none of which individually
exceeds 8.3% of that side's own $946.76 total (Section 4.1) — the
benefit this example illustrates is broad-based, not exceptional.

**A winner cut short into a loss (Policy D, 2024-04-01 21:45 SHORT)**:
control reached the full take-profit target, **+$180.12**. Under Policy
D, the trade's own favorable excursion triggered several staircase
tightenings; a subsequent retracement (still well short of the original
take-profit) then hit the tightened stop, closing the trade at
**−$81.54** — a single trade accounting for a $261.66 adverse swing, the
exact same failure mode (winners sacrificed outweighing losses avoided)
the completed Exit Management Sprint already identified and rejected
for a different trailing mechanism. **Corrected characterization**:
this trade does not "explain" D's $276 net benefit — it is one of only
3 trades on D's *negative* side, and its own presence *reduces* the net
total (removing it raises the net to ≈$538, Section 4.1's leave-one-out
check). What it correctly illustrates is a different, still important
point: D's small net benefit is **fragile** — it sits well within the
combined magnitude of just 3 large adverse trades, all in this same
month, all this same direction, all this same failure mode. Two more,
similar trades exist in the same month (2024-04-05, 2024-04-23,
Section 4.1) — a real, coherent, month-and-direction-concentrated
pattern, not an isolated fluke, and the specific, falsifiable reason
this report does not treat D's positive point estimate as established
evidence (Section 9, Section 11).

## 6. Costs, including funding recalculated per policy

Fees (0.04%/side) and slippage (0.02%/side) unchanged throughout —
already included in every net P&L figure above (both the paired
simulator and the sequential backtest use the real, unmodified
`ExecutionSimulator`). **Funding was recalculated for each policy's own
actual position lifetimes** (`strategy/research/funding_overlay.py`,
reused unchanged from the completed funding sprint) — the control's own
funding total was never reused for a different policy's generally
different exit times:

**Corrected** (recomputed against the fixed sequential ledgers):

| Policy | n trades | Settlements crossed | Total funding net | Orig. net P&L | P&L after funding | Shift |
|---|---|---|---|---|---|---|
| A | 61 | 11 | +$4.64 | −$672.92 | −$668.27 | +0.69% |
| B | 68 | 4 | −$1.18 | −$1,194.03 | −$1,195.21 | −0.10% |
| C | 64 | 4 | −$1.19 | −$945.10 | −$946.30 | −0.13% |
| D | 61 | 9 | +$0.36 | −$397.48 | −$397.12 | +0.09% |

Zero missing funding records for any policy (SOL funding coverage
confirmed complete for all 4 TRAIN months in the prior sprint). **Funding
is economically negligible for every policy in this sprint** — it does
not change any comparison, ranking, or conclusion above, before or
after the correction. B and C cross *fewer* settlements than the
control despite having *more* trades, because their tighter stops close
positions faster on average (shorter holding times, less
funding-interval exposure per trade) — a real, disclosed side effect of
the mechanism, not a data problem.

## 7. Tests and verification

7 new/updated test files, **34 new tests** (32 original + 2 regression
tests added by the correction), all passing; full suite **1153 passed,
0 failed**:

- `tests/test_progressive_stop_policies.py` (20 tests): step thresholds
  for all three named policies exactly, long/short symmetry, monotonic
  tightening under retracement, entry-bar exclusion from MFE tracking,
  next-bar activation (never same-bar), tick-size rounding, R0 frozen
  and never recalculated from a tightened stop, **plus 2 new regression
  tests proving a reused policy instance never leaks state across
  trades via `id()` reuse** (`test_reused_policy_instance_does_not_leak_state_across_trades_via_id_reuse`,
  `test_two_trades_with_colliding_ids_get_independent_state_directly`)
  — added directly in response to the confirmed defect (Section
  "CORRECTION" above).
- `tests/test_gap_aware_stop_fill.py` (9 tests): gap detection and
  realistic-fill recomputation, long/short symmetric, reuses the exact
  fee/slippage formulas (never a new cost convention).
- `tests/test_paired_trade_simulator.py` (6 tests): reproduces
  plain-`ExecutionSimulator` behavior exactly when given a no-op
  policy, next-bar activation preserved, take-profit unaffected,
  long/short symmetric.
- Funding-per-policy correctness reuses `strategy/research/funding_overlay.py`
  unchanged (already 22 tests from the completed funding sprint,
  re-run here, all passing) — this sprint's own funding recompute
  (Section 6) is a direct application of that already-tested module to
  a new set of trade ledgers, not new funding logic requiring new tests.
- **Control behavior verified unchanged**: the sequential backtest's
  own Policy-A path (`exit_policy=None`) reproduced the control ledger
  exactly (61 trades, −$672.92) on every one of **four** independent
  runs this sprint performed (control-ledger regeneration, the original
  sequential harness run, the corrected re-run after the fix, and the
  earlier funding-sprint ledger) — the strongest possible confirmation
  that (a) adding the `ExitPolicy` machinery changes nothing when
  unused, and (b) the `id()`-collision fix changed nothing for Policy A
  specifically, since a single-instance-per-month policy is never even
  invoked on the control path (`exit_policy=None`) — consistent with
  the bug being isolated to the candidate policies alone.

## 8. Safeguards for sample size, temporal dependence, and repeated TRAIN reuse

Applied throughout (not appended after the fact):

- **Month-clustering** (4 TRAIN months as 4 clusters, t-distribution
  df=3) as the primary uncertainty method for every paired-difference
  figure — a naive per-trade CI would be narrower and misleadingly
  precise, given trades within a month share regime conditions.
- **Multiple-comparison disclosure**: 3 candidate policies compared
  against 1 control is a family of 3 — stated plainly wherever a result
  is reported; no formal significance claim is made without this
  context, and none of the three results would survive a
  Bonferroni-adjusted threshold in any case (all three month-clustered
  CIs comfortably include zero).
- **Concentration check** (Section 4.1): applied to every policy on
  both its positive and negative sides separately, not collapsed into
  one number — for D, correctly identified fragility to 3 large
  adverse trades, not (as first mis-described) a fabricated benefit.
- **Pre-registration discipline**: the four policies and every
  decision rule were frozen (`docs/sol_progressive_stop_management_protocol.md`,
  hashed) before any outcome was computed; the parameter set was not
  expanded after seeing results.
- **Explicit reuse disclosure**: 2024-02, 2024-04, 2024-09, 2025-12 have
  now been inspected in seven prior sprints across this project. This
  report's own protocol freeze is a discipline device, not a fresh
  holdout — stated explicitly, not implied.

### Is a formal PBO/CSCV estimate meaningful here?

**No, but the reasoning must be stated at the right level of
generality** — verified directly against the actual paper (Bailey,
Borwein, López de Prado, and Zhu, "The Probability of Backtest
Overfitting," fetched and read in full after the user supplied it
mid-sprint), and correcting an over-statement in this report's own
first draft, which blurred four things the paper itself keeps
separate: **recommended settings** (what the authors suggest for
typical use), **conditional precision guidance** (formulas that depend
on the investor's own required resolution and the data's own span),
**illustrative examples** (used once, for exposition, never claimed
sufficient for real inference), and **universal minimum requirements**
(the paper states none — nowhere does it say "S<16 is invalid" or
"N≤10 makes CSCV unusable").

- **Recommended setting, not a hard floor**: the paper's own words are
  "we believe that **S=16 is a reasonable value to use in most cases**"
  — a recommendation for typical use, not a stated minimum below which
  the method fails outright.
- **Conditional precision guidance**: the paper derives *why* S=16 is
  reasonable from two conditions specific to its own worked context —
  the estimation error on the fraction of negative logits,
  `σ[p̂] ≈ √(p(1−p)/N_logits)` (worst case `σ<0.0045` at S=16's 12,780
  logits), and preserving quarterly structure in "4 years of daily
  data." Applied to this sprint's own actual figures — S=4 (one
  subsample per TRAIN month) yields 6 logits, `σ[p̂] ≈ 0.204` at
  p=0.5 — this is a **conditional** computation using the paper's own
  formula on this sprint's own T, not an appeal to a universal rule.
  Similarly, N (trial count): the paper's own conditional statement is
  "if the investor is sensitive to values of λ<1/10... N>>10 is
  required" — the requirement scales with the resolution the
  investor actually needs, not a fixed constant; this sprint's N=4
  gives the relative rank only 4 possible discrete values regardless
  of what resolution is wanted, which is coarse under any reasonable
  reading of that guidance, not only an extreme one.
- **Illustrative example, explicitly not offered as sufficient**: the
  paper's own S=4 appears exactly once, in Figure 1, to explain the
  combinatorial mechanic (six combinations of four subsamples) — it is
  never used for an actual PBO estimate anywhere in the paper, and nothing
  in the text suggests it would be adequate for one. This sprint does not
  claim S=4 is *forbidden* — only that the paper itself never treats
  it as evidentially sufficient, and its own quantitative reasoning
  (above) explains why not, for this sprint's own T.
- **No universal minimum is stated**: the paper's own worked practical
  application (Section 6 — an "optimal monthly trading rule" search
  over Entry day/Holding period/**Stop loss**/Side, structurally the
  closest example to this sprint's own subject) uses N=8,800
  configurations against T=1,000 daily prices (~4 years) — offered here
  as a **scale comparison** (this sprint's own N=4, T≈61 trades is two
  to three orders of magnitude smaller), not as evidence of a formal
  floor the paper itself never states.
- **A separate, independent caution**: the paper warns against ever
  using CSCV/PBO **to guide the search for an optimal strategy** —
  "PBO should not be the objective function on which such selection
  relies." This is a caution about *misuse*, not about minimum sample
  size, and applies regardless of how the power question above is
  resolved.

**Conclusion, restated precisely**: this sprint does not compute a PBO
number, not because the paper declares S=4/N=4 categorically invalid
(it does not), but because applying the paper's own **conditional
precision formulas** to this sprint's own actual T shows the resulting
estimate would carry an error an order of magnitude worse than the
paper's own recommended-setting baseline — a reasoned, data-specific
judgment, not an appeal to a rule the paper itself never states as
universal. The safeguards already applied above (month-clustering,
frozen no-expansion protocol, concentration checks, explicit
multiplicity disclosure, "insufficient evidence" as an allowed
non-forced verdict) remain the right-sized response to this project's
actual evidence. A properly-powered CSCV/PBO estimate could become
worth the effort once this project accumulates enough independent
months and trades per policy to bring the paper's own conditional
precision formula down to a useful error — not before, and not because
of a hard floor the paper does not itself assert.

## 9. Verdicts

Per the frozen decision criteria, evaluated at **both** the direct
(paired) and system (sequential) level, as required:

**Corrected** (using the fixed sequential results, Section 4.2, and the
corrected concentration interpretation, Section 4.1):

| Policy | Paired (direct) | Sequential (system) | **Verdict** |
|---|---|---|---|
| B | Net negative (−$567), inconsistent (3/4 months negative), concentration passes narrowly (47%, and the benefit side is not concentrated: 15.4%) but effect is direction-concentrated (SHORT only) | Worse on every metric, including drawdown (12.4% vs. 7.6%) | **NO SUPPORTED IMPROVEMENT** |
| C | Net negative (−$332), inconsistent (3/4 months negative), concentration check on the **negative** side is elevated (75% of net; benefit side 15.6%, not concentrated) | Worse on every metric, including drawdown (9.9% vs. 7.6%) | **NO SUPPORTED IMPROVEMENT** |
| D | Net positive (+$276), **benefit side broad-based (largest positive trade only 8.3% of the positive total)**, but the frozen concentration criterion still fails on an absolute basis (94.8%) because of sensitivity to 3 large, same-month, same-direction adverse trades; month-clustered CI (+0.052 ± 0.344) includes zero | **Now consistent with the paired result** (net +$275.44, 0 lost/newly-admitted entries) — improved net P&L/PF/expectancy, but **worse** drawdown (8.08% vs. 7.63%) | **INSUFFICIENT EVIDENCE** |

B and C: none of the other three categories applies — no evidence of
improved net expectancy (both worse at both levels); no risk reduction
with lower returns (drawdown is worse, not better, alongside worse
returns); not insufficient evidence either — the sample was large
enough to produce a consistent, decisively negative result across every
metric at the system level, in both the original and corrected runs.

D is different, and the corrected verdict reflects that precisely: it
is **not** "no supported improvement" — the point estimate is
positive, cross-validated by two independent methods (paired and,
after the fix, sequential), broad-based on its own benefit side, and
directionally consistent in 3 of 4 TRAIN months. It is **not**
"evidence of improved net expectancy" either — the frozen protocol's
own pre-registered concentration check fails, the confidence interval
includes zero, and drawdown moved the wrong way. **A genuine, positive,
cross-validated point estimate that fails a pre-registered robustness
check is exactly what "insufficient evidence" exists to describe** — a
different, more precise conclusion than either "the effect doesn't
exist" or "the effect is proven."

## 10. Limitations

- The equity-curve/closed-trade drawdown convention used throughout
  (Section 4.2) understates true intrabar mark-to-market drawdown, per
  the same already-disclosed limitation in
  `docs/profitability_root_cause_investigation.md` — not fixed here
  (out of this sprint's scope), and drawdown is *already* worse for
  every candidate policy under this convention, so this limitation does
  not affect the direction of the conclusion, only its exact magnitude.
- Tick-size rounding (2 decimal places) is a disclosed assumption, not
  verified against Binance's exact historical SOLUSDT perpetual tick
  size for the full 2024–2025 period.
- The gap-aware sensitivity check found zero binding cases in this
  specific 4-month sample — it cannot be said to be validated against a
  real gap event, only shown not to matter here.
- Sample size remains small in absolute terms (61 paired/sequential
  trades, 4 TRAIN months). For B and C this does not weaken the
  conclusion — both are decisively negative at the system level across
  every metric. **For D specifically, small sample size is the central
  limitation**: a genuine positive point estimate exists, but 3 trades
  (all in one month, one direction, one failure mode) are large enough,
  relative to the whole 61-trade sample, to move the net result by
  hundreds of dollars — this is precisely what "insufficient evidence"
  is reporting, not a defect in the measurement itself.

## 11. Recommended next action

**B and C do not merit further work.** Both are decisively negative at
the system level, consistently, across every metric including
drawdown, in both the original and corrected runs — not a borderline
result asking for more data.

**D is a genuinely open question, not a rejected candidate — and not
yet one to promote either.** Per the frozen protocol's own stopping
rule, this sprint does not expand the parameter grid (e.g. testing
intermediate tighten rates between D's 0.125R and A's 0R) chasing a
better staircase — that would be exactly the kind of post-hoc search
the protocol was frozen to prevent, and this sprint's own evidence does
not point to a parameterization problem in the first place. **The
single, bounded, TRAIN-only diagnostic that would most directly resolve
D's own "insufficient evidence" status**, without touching any new data
period: characterize what is distinct about 2024-04's own SHORT-side
price action (volatility, pullback depth, or realized range relative to
the other 3 TRAIN months) using data already downloaded for this
project — if April shows a measurably different regime signature, that
would explain the concentration as a regime effect (directly connecting
to the strategic review's own Hypothesis 2, regime-conditional
reversal) rather than a defect in D itself, and would inform whether
D's edge is a real, regime-conditional effect worth a properly-designed
VALIDATION experiment (with an explicit regime-conditioning rule frozen
in advance, not fit to April after the fact) or a coincidence of which
3 trades happened to occur in the specific 4 TRAIN months examined.
**Additional evidence needed before any adoption decision on D**: this
regime characterization, plus replication of the same paired-and-sequential
comparison on the untouched SECONDARY_VALIDATION months under a
separately-frozen protocol — neither performed in this sprint.

**More broadly**: this sprint's own evidence (both the confirmed defect
and the corrected result) does not change the strategic review's own
priority ordering — entry selection, not exit design, remains the
best-evidenced explanation for S001's current lack of profitability
(Section 1.3 of the strategic review). D's own corrected result is a
genuinely interesting, narrowly-scoped open question, not a reason to
deprioritize the strategic review's own higher-ranked, still-unexplored
hypotheses (regime-conditional reversal thesis; source-conditional
confirmation gating, already DO-NOT-PURSUE per the completed
funding/source sprint).

## 12. Explicit confirmations

No production strategy default was modified. No new setup was created.
No leverage or take-profit logic was changed (take-profit was
structurally untouched by every policy, verified by test). No data was
purchased. No VALIDATION, SECONDARY_VALIDATION, or FINAL_HELD_OUT month
was accessed (2025-02, 2025-07 untouched). All new files from this
sprint (3 research modules, 3 test files, this report, the frozen
protocol + hash) are left **uncommitted**, per the authorizing
instructions, awaiting your review.
