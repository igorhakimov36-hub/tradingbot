# Current CVD/Delta Signal Value and Incremental-Edge — SOL TRAIN Report

**Status: TRAIN-only research. Not a VALIDATION-grade claim, not a
production change.** Frozen protocol:
`docs/cvd_delta_signal_value_train_protocol.md`, SHA-256
`f2cb19b1841f02bb8bce1c15f4d28d3b0cd0bb38a93462edd4e17150be5034b8` —
verified unchanged immediately before the TRAIN harness's first run and
again immediately before this report was written.

**Bottom line**: no current CVD/Delta field clears this sprint's own
promotion bar. One field (`cvd_direction`) initially looked promising
at the pooled level (a 6.4-point gap, exceeding the 5-point threshold,
in the same direction in all 4 TRAIN months) but **failed its own
required redundancy and secondary-endpoint checks** — the entire effect
was concentrated in round-number-sourced pools (16.2pp gap there vs.
−0.5pp everywhere else) and vanished at the +2/−1 ATR secondary
endpoint (33.0% vs. 33.7%, essentially flat). The two currently-gating
fields (`price_cvd_divergence_flag`, `cvd_exhaustion_flag`) show no
reliable evidence either way at TRAIN sample sizes. `delta_direction`
shows no signal. No field is proposed for demotion — the evidence is
too fragile to act on in either direction.

## 1. Active field inventory

| Field | Formula | Units | Lookback/warmup | Range | State | Consumer | Role | Scale-invariant |
|---|---|---|---|---|---|---|---|---|
| `delta` | `2·taker_buy − volume` | base-asset volume | none (per-bar) | ℝ | one-shot (fresh per bar) | none | — | No (raw magnitude) |
| `delta_pct` | `delta/volume·100` | % | none | [−100, 100] | one-shot | none | — | Yes |
| `delta_direction` | `sign(delta)` | categorical | none | BULLISH/BEARISH/NEUTRAL | **persistent** (repeats while sign holds) | none currently — **tested this sprint as a candidate** | — | Yes |
| `delta_strength` | `\|delta_pct\|` | % | none | [0, 100] | one-shot | none | — | Yes |
| `cumulative_delta` | running Σdelta since tracker start | base-asset volume | none (unanchored) | ℝ, unbounded | persistent, unanchored | none (module's own code comments it as superseded by CVD) | — | No |
| `cvd` | running Σdelta under an anchor | base-asset volume | none (unanchored for `continuous`) | ℝ, unbounded | persistent | none directly (only its derived fields are read) | metadata | No |
| `cvd_direction` | `sign(cvd_slope)` over `window=20` | categorical | 20 bars | BULLISH/BEARISH/NEUTRAL | **persistent** | S007 | **non-gating** | Yes |
| `cvd_change_over_window` | `cvd[-1]−cvd[0]` | base-asset volume | 20 bars | ℝ | persistent | none | — | No |
| `cvd_slope` | `change/(window−1)` | volume/bar | 20 bars | ℝ | persistent | none | — | No |
| `price_cvd_divergence_flag` | window-relative price/CVD new-extreme disagreement | categorical | 20 bars | bullish/bearish_divergence/none | **persistent** | S001 | **gating** | Yes |
| `cvd_exhaustion_flag` | window-relative CVD new-extreme + deceleration | categorical | 20 bars | bullish/bearish_exhaustion/none | **persistent** | S001 | **gating** | Yes |

**Scope of this sprint (frozen in the protocol)**: the four fields with
a genuine bullish/bearish interpretation —
`cvd_direction`, `price_cvd_divergence_flag`, `cvd_exhaustion_flag`,
`delta_direction`. The continuous magnitudes underlying them
(`cvd`, `cvd_slope`, `cvd_change_over_window`, `delta`, `delta_pct`,
`delta_strength`, `cumulative_delta`) are not independently tested —
they either drive one of the four directional fields already in scope,
or (for `cumulative_delta`) are already documented in the codebase
itself as superseded. Frozen legacy-engine functions
(`evaluate_bos_quality`) were confirmed in the completed audit to have
zero Delta/CVD dependency and are out of scope.

### Frequency (raw directional bars, pooled per field, all 4 TRAIN months, 11,516 bars total)

| Field | Bullish bars | Bearish bars | Bullish % | One-shot events |
|---|---|---|---|---|
| `cvd_direction` | 3,846 | 7,594 | 33.6% | 1,029 |
| `delta_direction` | 5,306 | 6,210 | 46.1% | 5,507 |
| `price_cvd_divergence_flag` | 399 | 848 | 32.0% | 823 |
| `cvd_exhaustion_flag` | 494 | 166 | 74.8% | 442 |

`cvd_direction` and `price_cvd_divergence_flag` both skew markedly
bearish (≈2:1) across all 4 TRAIN months consistently — a genuine,
stable asymmetry in this dataset's own order-flow readings, not
obviously an artifact (the audit found no data-quality issue that would
produce it) but worth carrying forward as context, not itself tested as
a hypothesis this sprint. `cvd_exhaustion_flag` skews bullish (≈3:1) —
the opposite asymmetry, consistent with exhaustion being the
"deceleration at a new extreme" condition, which fires more often at
CVD lows given the bearish skew above (more bearish CVD periods produce
more CVD-low decelerations).

## 2. Consumer map

| Setup | Field(s) | Role | Current sample (this sprint's CVD-blind candidate pool) |
|---|---|---|---|
| S001 (`liquidity_sweep_reversal.py`) | `price_cvd_divergence_flag`, `cvd_exhaustion_flag` (combined via OR into one `cvd_confirms_reversal` gate) | **Required/gating** | 465 CVD-blind candidates (sweep confirmed + evidence_count≥1, independent of CVD) |
| S007 (`trend_continuation_confluence.py`) | `cvd_direction` | **Non-gating** additional evidence | 25 candidates total (S007 is not part of any active backtest configuration — see the completed audit, Section 8) |

## 3. Frozen protocol

Full rules in `docs/cvd_delta_signal_value_train_protocol.md`. Key
implementation choices locked before any outcome was computed: event
identity `(field_name, bar_i, confirmed_at)`; edge-triggering as one
causal transition (not requiring an intervening neutral reading between
flips); S001's CVD-blind candidate = sweep confirmed AND
evidence_count≥1 from CHOCH/multi-source/SMT, evaluated via S001's own
real, unmodified private methods, CVD excluded; S007's CVD-blind
candidate = its own two required conditions (already CVD-blind in
production), de-duplicated by collapsing consecutive same-`(pool_id,
direction)` runs to their first bar; reused `+1/−1` primary / `+2/−1`
secondary ATR endpoint, 32-bar horizon; a ≥30-resolved-outcome sample
gate before any comparison can support `PROMOTE`/`PROPOSE DEMOTION`;
month-clustered uncertainty (4 clusters, t-distribution df=3) as the
primary CI method, naive binomial CI reported alongside as an
explicitly-labeled upper bound on precision only.

## 4. Implementation and tests

Three new research modules, 24 new tests, all passing; full suite
**1084 passed, 0 failed**.

- `strategy/research/cvd_delta_native_events.py` — `classify_directional`,
  `edge_trigger_events`, `raw_directional_bar_count`. 10 tests,
  including causal prefix-consistency (no lookahead/no backdating) and
  distinct-event-identity-after-a-gap.
- `strategy/research/cvd_delta_opportunity_populations.py` —
  `classify_confirmation`, `classify_opportunity`. 8 tests, including
  an exhaustive mutual-exclusivity check across every real field value.
- `strategy/research/cvd_delta_neutral_setups.py` —
  `CVDNeutralLiquiditySweepReversalSetup`, a direct subclass of the
  real, unmodified `LiquiditySweepReversalSetup` overriding **only**
  `_cvd_confirms`. 6 tests, including a structural proof (`vars()`
  inspection) that no other method is overridden, and a direct
  side-by-side proof that every other required/additional condition is
  byte-identical between production and the neutral variant on the same
  snapshot.

All 12 required research tests are covered by this set (edge-triggering
correctness, distinct identities, confirmation-timestamp correctness,
CVD-blind capture before conditioning, mutual exclusivity, next-candle
outcome start — reused and already proven in
`liquidity_pool_staleness_telemetry`'s own tests — no-future-data,
same-bar ambiguity — same reuse — exact S001 linkage, CVD-field
neutralization leaving other conditions untouched, determinism, and
production byte-identity when research mode is absent).

## 5. Population A — native one-shot event results

Pooled, all 4 TRAIN months, primary endpoint (`+1/−1 ATR`):

| Field | Events | Favorable rate | n resolved |
|---|---|---|---|
| `cvd_direction` | 1,029 | 50.3% | 1,025 |
| `delta_direction` | 5,507 | 49.7% | 5,488 |
| `price_cvd_divergence_flag` | 823 | 50.2% | 820 |
| `cvd_exhaustion_flag` | 442 | 48.0% | 442 |

**All four fields sit within 2 points of 50%, pooled.** None shows a
directional edge as a standalone trend-continuation-style event (this
population treats a "bullish" reading as implying an UP move, matching
S007's own interpretation — the opposite convention from S001's
mean-reversion-style sweep events). Per-direction (bullish vs. bearish)
splits and per-month splits (in the diagnostic scripts underlying this
report) show the same flatness, no field favoring one direction
consistently. This is a stable null across a very large sample (raw
directional bars: 11,440–11,516 per field pooled) — not underpowered.

## 6. Population B — CVD-blind opportunity incremental value

### S001 (n=465 CVD-blind candidates, pooled)

| Field | CONFIRMS rate (n) | CONTRADICTS rate (n) | NEUTRAL rate (n) | CONFIRMS−CONTRADICTS |
|---|---|---|---|---|
| `cvd_direction` | 51.2% (217) | 44.7% (246) | — (0) | **+6.44pp** |
| `delta_direction` | 47.2% (339) | 49.2% (124) | — (0) | −2.00pp |
| `price_cvd_divergence_flag` | 44.7% (47) | 50.0% (58) | 47.8% (358) | −5.32pp |
| `cvd_exhaustion_flag` | 57.1% (7) | 65.2% (23) | 46.7% (433) | −8.07pp (n=7, uninterpretable) |

`cvd_direction`'s pooled gap (+6.44pp) exceeds the 5-point threshold
and is positive in all 4 TRAIN months (56.0%/54.2%/48.1%/47.7%
CONFIRMS vs. 47.8%/43.5%/47.4%/40.0% CONTRADICTS — gaps of +8.2, +10.7,
+0.8, +7.7 points). This is the only field that reaches the primary
screening bar — **it does not survive the required follow-up checks**
(Section 7).

`price_cvd_divergence_flag` (currently gating) shows CONFIRMS
numerically **below both** CONTRADICTS and NEUTRAL — a concerning
direction for a field that currently blocks trades unless it agrees.
Per-month CONFIRMS rates are 63.6%/54.5%/21.4%/45.5% (n=11–14 per
month) — wildly unstable, and the month-clustered CI half-width
(±28.9 points around a 46.3% mean) dwarfs the point estimate itself.
**This is a genuinely fragile result, not a confident negative
finding** — see Section 9.

`cvd_exhaustion_flag`'s CONFIRMS group (n=7) is far below the 30-observation
sample gate and is not interpretable at all, despite the
numerically large-looking rates.

### S007 (n=25 candidates total — diagnostic-only per the frozen protocol)

`cvd_direction`: CONFIRMS 57.1% (n=21) vs. CONTRADICTS 0.0% (n=4) — an
enormous-looking gap on a sample too small to mean anything (the
CONTRADICTS group alone has only 4 observations). `delta_direction`:
CONFIRMS 66.7% (n=12) vs. CONTRADICTS 30.8% (n=13) — same issue. Both
are reported for completeness only; neither supports any conclusion.

## 7. Incremental value / redundancy analysis

**`cvd_direction` at S001's candidate pool — the one field that cleared
the primary screening bar — fails on follow-up:**

- **Secondary endpoint (`+2/−1 ATR`) is flat**: CONFIRMS 33.02% vs.
  CONTRADICTS 33.74% — essentially no gap, in mild tension with the
  primary endpoint's own 6.4-point gap. A real, robust effect should
  show *some* coherent (even if attenuated) pattern at the secondary
  endpoint; here it does not.
- **Source stratification collapses the effect entirely**:
  round-number-only pools show a 16.2-point CONFIRMS−CONTRADICTS gap;
  every other source shows −0.5 points (i.e. no gap at all, direction
  reversed). The pooled effect is **not a general property of the
  field — it is concentrated in one source subgroup**, exactly the
  pattern the frozen decision rule's redundancy requirement is designed
  to catch.
- **Market-structure stratification is inconsistent**: BULLISH_BOS
  +3.9pp, BEARISH_BOS +16.7pp, but **NO_BOS reverses to −5.7pp**.
- **Month-clustered CIs overlap substantially**: CONFIRMS 51.5% ± 6.7,
  CONTRADICTS 44.7% ± 5.8 — the true uncertainty (once monthly
  clustering is respected, rather than the far narrower naive
  per-observation CI) is wide enough that the two groups are not
  cleanly separated.
- Direction (LONG/SHORT) and volume-regime splits were both consistent
  in sign (not concentrated in one direction or one volume regime),
  which is the one control this field *does* pass — but a field that
  fails two of five controls (source, market structure) and the
  secondary endpoint does not meet "survives basic redundancy controls"
  as a whole.

**Classification: `Insufficient evidence`** for a genuine incremental
effect — the pooled signal that initially looked real is better
explained as concentrated in a single, dominant subgroup
(round-number-sourced pools, which are ~94% of the underlying pool
population per the completed Wick-Extremity/Touch-Volume research) than
as a general property of `cvd_direction` itself.

**Other three fields**: no pooled effect large enough to test for
redundancy in the first place (`delta_direction`: −2.0pp;
`price_cvd_divergence_flag`: negative and unstable, Section 9;
`cvd_exhaustion_flag`: uninterpretable at n=7).

## 8. Exact S001 ablation (S007: opportunity-slicing only, per protocol)

Control (real, unmodified S001) vs. `CVDNeutralLiquiditySweepReversalSetup`
(CVD gate removed, everything else identical), standalone, exact
`pool_id` linkage, pooled across 4 TRAIN months:

| | n | Win rate | PF | Net P&L | Expectancy |
|---|---|---|---|---|---|
| CONTROL (production) | 61 | 36.1% | 0.85 | −$672.92 | −$11.03 |
| NEUTRAL (CVD removed) | 455 | 35.2% | 0.83 | −$5,504.22 | −$12.10 |
| SHARED (same pool, both fire) | 56 | 37.5% | 0.92 | −$311.01 | −$5.55 |
| NEUTRAL-ONLY (CVD would have blocked) | 399 | 34.8% | 0.81 | −$5,193.21 | −$13.02 |
| CONTROL-ONLY | 4 | 25.0% | 0.50 | −$178.44 | −$44.61 |

**Path-dependency vs. direct CVD filtering, explained separately**: the
neutral variant's raw signal count is a strict superset of control's at
the *signal* level (every candidate that satisfies production's CVD
condition also satisfies the always-true neutral condition, with
nothing else changed — proven directly in
`tests/test_cvd_delta_neutral_setups.py`). At the *trade* level, this
project's single-open-position backtest engine means an extra
CVD-blocked-in-production trade taken by the neutral variant can occupy
the one available slot and cause a later, otherwise-shared candidate to
be skipped — this is the entire explanation for the 4 `CONTROL-ONLY`
trades (all in 2024-09 and 2025-12, the two months where an
extra-signal-driven orphaned open position also appeared at month end).
**399 of 403 non-shared trades are directly attributable to CVD
filtering; only 4 are a path-dependency artifact** — the ablation is
overwhelmingly a clean measurement of the CVD gate's own effect, not
slot-contention noise.

**Reading the result**: removing the CVD gate multiplies trade count
~7.5× (61→455) at essentially the same win rate (36.1% vs. 35.2%) and a
very slightly worse expectancy (−$11.03 vs. −$12.10 per trade) — the
gate's main current effect is **frequency reduction, not detectable
quality selection**. `SHARED` trades (agreed by both variants) are the
best-performing subgroup (37.5% win rate, PF 0.92), and `NEUTRAL-ONLY`
(CVD-blocked) trades are the worst large subgroup (34.8%, PF 0.81) —
a small, directionally-supportive-of-the-gate signal, but the gap
(2.7 points win rate) is well within noise at these sample sizes and in
**mild tension** with Section 6/7's finding that `price_cvd_divergence_flag`
CONFIRMS underperforms NEUTRAL/CONTRADICTS at the module level. Neither
direction of evidence is strong enough to overrule the other — both
point toward the same overall conclusion: **the current CVD gate's
value is not established, but neither is its removal clearly
beneficial.** Note, as context already established throughout this
research series: neither CONTROL nor NEUTRAL is net profitable on
TRAIN in this raw form (PF < 1 for both) — this sprint does not change
that standing fact, and is not a claim that S001 is or is close to
being profitable either way.

## 9. Sample-size, clustering, overlap, and censoring limitations

- **Hypotheses tested**: 4 fields × (1 native-event pooled comparison +
  1 S001 opportunity CONFIRMS-vs-CONTRADICTS comparison) = 8 primary
  comparisons, plus 2 diagnostic-only S007 comparisons — 10 total.
  Given that **zero** comparisons cleared every required check even
  before any multiple-comparison adjustment, a formal correction (e.g.
  Bonferroni) would only make the bar stricter and does not change any
  verdict here — noted for transparency, not applied as a separate
  gate.
- **Clustering was addressed at the source**, not patched on
  afterward: Population A already de-duplicates persistent per-bar
  readings into one-shot events; S007's Population B candidates are
  de-duplicated by consecutive-run collapse. The remaining
  month-to-month clustering is handled via the frozen month-clustered
  CI method (Section 3) wherever a pooled rate is reported as evidence
  for or against promotion.
- **`price_cvd_divergence_flag`'s CONFIRMS group (n=47) has a
  month-clustered CI half-width of ±28.9 points** around a 46.3% mean —
  this dwarfs the point estimate. This is reported as a genuine,
  concerning-looking pooled number, but the sprint's own statistical
  discipline ("do not promote/demote based on a handful of trades")
  applies symmetrically — this sample is too fragile to justify
  `PROPOSE DEMOTION` despite the numerically negative pooled gap.
- **`cvd_exhaustion_flag`'s CONFIRMS group (n=7) is below the frozen
  30-observation gate** in every context tested — never used to support
  any conclusion.
- **S007's total sample (n=25) is far below any usable threshold** —
  every S007-specific number in this report is diagnostic context only,
  per the frozen protocol.
- **Overlap between fields**: `price_cvd_divergence_flag` and
  `cvd_exhaustion_flag` jointly gate S001 via an OR (`cvd_confirms_reversal`
  is satisfied if either matches) — evaluated here as two separate
  hypotheses per the authorizing instructions, but a reader should not
  interpret either field's own verdict as describing the *combined*
  gate's behavior in isolation; Section 8's ablation measures the
  combined gate directly.
- **Censoring**: right-censored (unresolved-within-32-bar-horizon)
  outcomes are excluded from every reported rate's numerator/denominator
  but retained in the underlying `n` counts reported alongside — never
  silently dropped from disclosure.

## 10. Verdicts

| Field | Current role | Verdict | Basis |
|---|---|---|---|
| `cvd_direction` | Non-gating (S007) | **INCONCLUSIVE** | S007's own sample (n=25) is far too small to judge its current role; the larger S001-candidate-pool evidence (n=465) initially cleared the promotion screening bar but failed the required secondary-endpoint and source-redundancy checks — the apparent effect is explained by round-number-source concentration, not the field itself |
| `price_cvd_divergence_flag` | Gating (S001) | **INCONCLUSIVE** | Pooled CONFIRMS underperforms both CONTRADICTS and NEUTRAL, a direction that would normally support scrutiny — but month-clustered uncertainty (±28.9pp on a 46.3% mean, n=47) is too wide to support any conclusion, including `PROPOSE DEMOTION` |
| `cvd_exhaustion_flag` | Gating (S001) | **INCONCLUSIVE** | CONFIRMS group (n=7) is far below the sample-size gate in every context |
| `delta_direction` | Not currently consumed | **RETAIN AS METADATA** | Correctly calculated (per the completed audit); no directional value found at either the native-event level (49.7% pooled favorable) or the S001-candidate-pool level (−2.0pp CONFIRMS−CONTRADICTS, flat across redundancy checks) |

No field is proposed for demotion, promotion, or a "keep current role"
confirmation this sprint — the evidence for the two currently-gating
fields is genuinely too fragile (small, unstable samples) to move in
either direction, and `cvd_direction`'s one promising-looking result
did not survive its own required checks. This is a materially different
conclusion from "no field has any value" — it is "no field's value or
lack of value is established at TRAIN sample sizes with the controls
this sprint's own protocol requires."

## 11. Session-anchored CVD gate

**Not justified yet, and the completed sprint reinforces rather than
loosens that gate.** The authorizing instructions require: (a) a
currently-useful field a reset mechanism could plausibly improve, and
(b) confidence the experiment would not merely introduce a reset
artifact. Neither condition is met:
- No field demonstrated reliable directional or incremental value this
  sprint (Section 10) — there is no established "useful field" for a
  session anchor to improve.
- The one field that came closest (`cvd_direction`) failed specifically
  because its apparent effect was a **source-concentration artifact**,
  not because of any property a session reset would address —
  introducing a reset now would add a new, untested degree of freedom
  on top of an effect already shown not to generalize, exactly the
  outcome the authorizing instructions warned against.
- If a future sprint ever does establish a genuinely useful,
  redundancy-surviving field, a `daily`-anchored UTC reset would be the
  only anchor with clear institutional meaning for a 24/7 market like
  SOL (a fixed calendar boundary, already implemented and tested in the
  completed audit's Section 5) — worth naming for that future sprint,
  not worth building now.

## 12. Recommended next step

No further CVD/Delta correction, promotion, or setup integration is
supported by this sprint's own evidence. Two narrow, low-cost follow-ups
would most directly resolve this sprint's own two open questions,
neither authorized to execute now:
1. **A larger-sample, dedicated look at `price_cvd_divergence_flag`
   specifically** (the one field showing a numerically concerning
   direction) — e.g. extending to the SECONDARY_VALIDATION months under
   a fresh, separately-frozen protocol, since TRAIN alone (n=47 CONFIRMS)
   cannot resolve it either way.
2. **Re-running `cvd_direction`'s S001-candidate-pool test after
   excluding round-number-only pools by design**, rather than as a
   post-hoc stratification, to see if a genuinely different-population
   experiment confirms or refutes Section 7's redundancy finding.

Otherwise, per the standing module decision register, the next
undecided module areas remain CVD/Delta-adjacent work this sprint was
explicitly scoped to avoid (FVG/IFVG, Volume Profile, ATR/Regime, S008,
portfolio) — left to the user's own prioritization.

## 13. Explicit confirmation

**No production logic was modified.** `strategy/features/delta.py`,
`strategy/features/cvd.py`, `strategy/setups/liquidity_sweep_reversal.py`,
`strategy/setups/trend_continuation_confluence.py`, and every other
production file this sprint read were **read only, never edited**.
**No new setup was created or integrated** —
`CVDNeutralLiquiditySweepReversalSetup` is a research-only subclass used
solely for this sprint's ablation measurement, never registered in any
production `StrategyEngineV2` configuration. All new files (3 research
modules, 3 test files, this report, the frozen protocol + hash) remain
**uncommitted**, per the authorizing instructions, awaiting approval.

---
Deliverables (all uncommitted):
`docs/cvd_delta_signal_value_train_protocol.md` + `.sha256`,
`strategy/research/cvd_delta_native_events.py`,
`strategy/research/cvd_delta_opportunity_populations.py`,
`strategy/research/cvd_delta_neutral_setups.py`,
`tests/test_cvd_delta_native_events.py`,
`tests/test_cvd_delta_opportunity_populations.py`,
`tests/test_cvd_delta_neutral_setups.py`, this report. Full test suite:
1084 passed, 0 failed.
