# SOL Funding Impact and Source-Conditioned S001 Re-analysis

**Status: bounded research sprint. No production change, no confirmation
gate removed or modified, no parameter optimization, no paid
subscription, no new setup, no alternative-strategy backtest, no
VALIDATION/FINAL_HELD_OUT access.** Repository state: commit `5034c70`
(strategic review checkpoint, verified below). New artifacts this
sprint: `strategy/research/funding_overlay.py`,
`strategy/research/liquidity_pool_source_grouping.py`, 3 new test
files (35 tests), frozen protocol `docs/sol_funding_source_reanalysis_protocol.md`
(SHA-256 `f6def1ff905d10b44ed7527f6c94f0d65c5b78de74118bf5831249d586a13f98`).
Python 3.13.14, `venv/Scripts/python.exe`. Data coverage used: SOL TRAIN
1-minute klines (already validated, unchanged) plus newly-downloaded
SOL funding-rate history for the 4 TRAIN months only (`data/SOLUSDT-funding-2024-02.csv`,
`-2024-04.csv`, `-2024-09.csv`, `-2025-12.csv`), retrieved read-only
from Binance's public `/fapi/v1/fundingRate` endpoint. Full test suite:
**1119 passed, 0 failed** (1084 pre-existing + 35 new).

## 1. The three strategic hypotheses, updated priority

Restated from `docs/sol_strategy_edge_strategic_review.md`:

1. **Round-number-conditional confirmation gating** — S001's
   confirmation requirement may discriminate against round-number-sourced
   pools in a way that hurts rather than helps selection. Ranked #1:
   cheapest (no new data), most directly evidenced (two prior sprints'
   small-sample observations pointed the same way), tests an existing
   setup's own architecture.
2. **Regime-conditional reversal thesis** — sweep reversals may work in
   ranging conditions and fail in trends; BTC evidence showed S001's win
   rate swinging 30%→61.5% between two months. Ranked #2: plausible,
   cheap, but SOL-untested (BTC-only evidence).
3. **Forced-liquidation behavior (derivatives-information route)** —
   genuinely new information (actual reported liquidations vs. our
   Delta/CVD proxy), but blocked on unverified/unavailable historical
   depth from every evaluated vendor. Ranked #3, scoped
   prospective-collection-only.

**Does the funding omission change this ranking?** No — and this
sprint's own measurement (Section 2) confirms that conclusion
empirically rather than leaving it as a plausibility argument. Funding
was flagged in the strategic review as a *previously unstated gap in
every cost model*, not as a reason to distrust any specific hypothesis
over another: it applies equally to whichever hypothesis is tested next.
Its only *procedural* relevance was as a prerequisite check (would a
material, undisclosed cost make any TRAIN comparison untrustworthy?) —
which this sprint's Section 2 now resolves directly: funding is small
enough, on the actual trade ledgers, that it does not materially affect
either the absolute S001 numbers or a relative comparison between
configurations. The ranking stands as originally given.

**Clarifying the strategic review's own data-availability language**:
"no evaluated provider confirmed historical liquidation depth" means
exactly that — not verified among Binance, CoinGlass, and Coinalyze,
the three sources actually checked. It does not establish that no
provider anywhere offers usable historical coverage; the review said so
explicitly ("Unverified — would require a paid account to test") and
this sprint does not expand that survey.

## 2. Checkpoint verification

- Commit `5034c70` ("research: SOLUSDT strategy and edge strategic
  review") confirmed present in `git log`; `git show --stat` confirms
  it contains exactly `docs/sol_strategy_edge_strategic_review.md`
  (1 file, 641 insertions) — no unrelated content.
- `git status --short` at sprint start showed a clean working tree (the
  strategic review was already committed in the immediately preceding
  turn) — no separate commit was needed for it this sprint; recorded
  here per the instruction to record the existing checkpoint if already
  committed, without rewriting history.
- Full suite re-run before any new work: 1084 passed (matching the
  count reported in the prior sprint's own closure).

## 3. Funding coverage and fixed-trade overlay

### 3.1 Coverage verification

No SOL funding data existed locally before this sprint (only partial
BTC coverage, Jan–Jul 2024). Retrieved SOL funding history for the 4
TRAIN months only, read-only, from Binance's public `/fapi/v1/fundingRate`
endpoint (the same venue already confirmed as the data source for
price data). **Result: 100% complete** — every month has exactly the
expected number of settlements (87/90/90/93 for Feb/Apr/Sep/Dec,
matching 29/30/30/31 days × 3 settlements/day), zero missing
`fundingRate` or `markPrice` values, uniform 8-hour spacing throughout
(no hourly-shift anomaly observed in these specific 4 months, though the
overlay implementation never assumes this — see 3.2). One incidental
finding, corrected immediately: the download's inclusive month-boundary
parameter captured a single stray settlement record each for 2024-03
and 2024-10 (both **FORBIDDEN** months — SECONDARY_VALIDATION and
VALIDATION respectively) as an artifact of using "first of next month"
as an inclusive end-time. **Both stray files were deleted immediately
upon discovery, before any use** — each contained a single funding-rate
number, never inspected for content beyond confirming it needed
deletion, never used in any computation below.

### 3.2 Accounting convention (verified against Binance's own
documentation, checked 2026-09-05)

Per [Binance's funding-fee FAQ](https://www.binance.com/en/support/faq/detail/360033525031):
`funding_amount = mark_price_at_settlement × position_size × funding_rate`;
positive rate → LONG pays / SHORT receives; negative rate → SHORT pays
/ LONG receives; a position is liable only if open (already entered,
not yet closed) **at the settlement's own real timestamp** — closing
strictly before it exempts the trade. `strategy/research/funding_overlay.py`
implements this exactly: `payment_to_trader = -side_sign × quantity ×
mark_price × rate` (no leverage re-multiplication — `quantity × mark_price`
already is the full notional, matching Binance's own "Nominal Value of
Positions" wording), using each settlement's **own recorded timestamp**
(never an assumed invariant 8-hour grid — verified moot for these 4
months specifically, since none showed a schedule deviation, but the
implementation does not rely on that being true). Two boundary
conventions (`inclusive`: a settlement exactly at entry or exit is
charged; `exclusive_exit`: a settlement exactly at exit is not) were
computed side by side, per the sprint's own instruction to flag
ambiguity and report sensitivity — **both conventions produced
identical results on the real ledgers** (no trade in either the control
or neutral run happened to enter/exit at a settlement's exact timestamp),
so the ambiguity is real in principle (tested directly,
`test_settlement_exactly_at_entry_is_charged_under_both_conventions`
etc.) but did not matter empirically here.

### 3.3 Applied to the real S001 ledgers

The original CVD signal-value sprint's saved trade records did not
include `quantity` (needed for the funding formula). The **exact same**
control (`LiquiditySweepReversalSetup`) and CVD-neutral
(`CVDNeutralLiquiditySweepReversalSetup`) backtests were re-run,
unchanged, to recover it — verified byte-identical to the original,
already-published result before proceeding (61 control trades,
net P&L −$672.92; 455 neutral trades, net P&L −$5,504.22, both matching
exactly).

| Run | n trades | Trades crossing ≥1 settlement | n settlements | Funding paid | Funding received | Funding net | Orig. net P&L | Net P&L after funding |
|---|---|---|---|---|---|---|---|---|
| CONTROL | 61 | 11 (18.0%) | 11 | $2.36 | $7.00 | **+$4.64** | −$672.92 | **−$668.27** |
| NEUTRAL | 455 | 98 (21.5%) | 105 | $57.01 | $68.59 | **+$11.58** | −$5,504.22 | **−$5,492.64** |

Win rate is unchanged to 3 decimal places in both runs (funding never
flips a single trade's win/loss sign in either ledger). Per-month and
directional breakdowns (both boundary conventions, identical results)
are in the underlying analysis artifacts; the pooled picture already
answers the sprint's own question: **funding shifts total net P&L by
0.7% (control) and 0.2% (neutral) — economically negligible at these
trade counts and holding times.** Funding concentration is real but
does not change this conclusion: the single largest trade's `|funding_net|`
ranged from 22% to 224% of that run's own small aggregate net (the
224% figure, 2024-09 control, is an artifact of a near-zero aggregate
net built from offsetting positive/negative individual contributions —
disclosed, not hidden, and still economically small in absolute dollar
terms: the largest single-trade funding contribution across every
month/run was $10.63).

**This is a fixed-trade overlay only** — it does not reproduce
funding-induced changes to position sizing, margin availability, or
execution (per the sprint's own required framing) — a materially larger
or smaller position, or a funding-rate-driven change to when a trade
would have been taken, is not modeled here.

**Conclusion for Section 7's decision**: funding does **not** prevent a
trustworthy comparison — the overlay is small enough, and stable enough
across both boundary conventions, to proceed with the source-conditioned
analysis without first addressing funding accounting.

## 4. Exact source-confirmation semantics

Traced directly in `strategy/setups/liquidity_sweep_reversal.py`
(`evaluate()`, lines 105–154, unchanged, re-read for this sprint):

`pool_has_multiple_sources` (via `_multi_source_pool`) is **not an
independent mandatory gate.** It is one of three alternative
confirmations —
```
additional = [_choch_confirms(...), _multi_source_pool(swept_pool), _smt_confirms(...)]
evidence_count = sum(1 for c in additional if c.satisfied)
confirmation_condition = ConditionResult(satisfied = evidence_count >= 1)
required = [sweep_condition, cvd_condition, confirmation_condition]
fired = all(c.satisfied for c in required)
```
— feeding a single minimum-count rule (`evidence_count >= 1`), itself
one of three required conditions that must ALL hold. A pool is never
rejected *specifically* "because it lacks multiple sources" — it is
rejected only if **all three** of CHOCH, multi-source, and SMT fail to
confirm. It is a **ranking-irrelevant, count-contributing input** —
not a tie-breaker either (no ranking/tie-break logic exists anywhere in
S001; `evidence_count` is descriptive metadata on `SetupResult`, never
used to choose between candidates — confirmed by reading the full
class, and consistent with `strategy/strategy_engine_v2.py`'s own
first-registered-setup-wins arbitration, which has nothing to do with
per-setup evidence counts).

**`_find_fresh_sweep` selects `pool_id` before any source or
confirmation check**: `candidates = [zone for zone in snapshot.zones if
...]; return candidates[0] if candidates else None` — selection is by
zone-list position only. **No source-based selection bias enters before
`pool_id` is chosen** — confirmed by direct reading, not inferred.

**A newly-established structural fact, not previously stated precisely
anywhere in this project**: `_multi_source_pool` requires
`len(sources) > 1`. A `round_number_only` pool (by definition,
`sources == ["round_number"]`, length 1) can **never** satisfy this
condition — not because of any policy choice, but because it is
definitionally single-source. This means round-number-only pools can
only ever pass S001's confirmation via CHOCH (structure) or SMT
(intermarket) — multi-source is categorically unavailable to them. This
was verified computationally, not just logically: in the pre-filter
population (Section 5), **zero** round-number-only candidates ever
showed `multi_source_satisfied = True` (asserted directly in the
analysis script, held for all 4,396 round-number-only candidates).

## 5. Opportunity-population completeness

The completed CVD signal-value sprint's own `s001_candidates` ledger
(n=465) was built with an explicit filter — `if evidence_count >= 1:
candidates.append(...)` — meaning it **already excluded** every
candidate that failed the confirmation requirement entirely. Per the
sprint's own instruction, **this ledger alone cannot measure the value
of the confirmation/source filter**, since the population it rejected
was never recorded.

**One authorized, read-only replay** (`funding_sprint_prefilter_replay.py`)
recovered the missing pre-filter population: every bar where
`_find_fresh_sweep` returns a pool, regardless of confirmation or CVD
status, with each of the three confirmation checks recorded
individually. It calls only S001's own real, unmodified private methods
(the same ones `evaluate()` itself calls, in the same order), makes no
lifecycle or tracker change, and is per-bar snapshot observation, not a
backtest — no portfolio slot availability is involved, so which
opportunities are observed cannot be influenced by trade-execution
state. Verified safe by two dedicated tests (`test_funding_source_reanalysis_observer.py`)
proving observation is byte-identical to production and idempotent.
**Cross-check**: the replay's own `confirmation_would_pass` counts
(117/110/113/125 per TRAIN month) match the original sprint's
`s001_candidates` counts exactly — confirming this is the same
population, now with its rejected superset also captured.

**Result: 4,721 freshly-swept pools pooled across 4 TRAIN months** (vs.
465 that ever reach confirmation, and 61 real trades) — only 9.85% of
all swept pools pass confirmation at all.

## 6. Frozen analysis plan

Full text: `docs/sol_funding_source_reanalysis_protocol.md`, SHA-256
`f6def1ff905d10b44ed7527f6c94f0d65c5b78de74118bf5831249d586a13f98`,
verified unchanged immediately before computing any subgroup outcome
and again before writing this report. It completes the strategic
review's own decision criterion (left with an implicit comparator):
**comparator** = round-number-only candidates rejected solely because
CHOCH and SMT both fail, vs. the currently-accepted population's own
real after-cost expectancy (−$11.03/trade); **threshold** = the
newly-unblocked population must be directionally at-least-as-good as
that baseline, in ≥3 of 4 TRAIN months, on ≥30 resolved outcomes — tied
directly to the actual decision (would we accept these trades if the
gate were relaxed for this source only?), not a generic percentage. It
also corrects, before any result was seen, a latent flaw in the
original framing: since round-number-only pools can never satisfy
multi-source (Section 4), the real question is "does removing the
*entire* confirmation requirement for round-number-only pools help,"
not "does multi-source specifically help them."

## 7. Source/CVD comparison

### 7.1 Pre-filter population: source composition and confirmation-pass mechanics

| Source group | n (% of pre-filter pop.) | Confirmation pass rate | How it passes | Would fire in production |
|---|---|---|---|---|
| `round_number_only` | 4,396 (93.1%) | 4.2% (183) | 100% via CHOCH only (0 via multi-source — structurally impossible) | 5 |
| `round_number_plus_other` | 215 (4.6%) | **100.0%** (215) | 98% via multi-source alone | 38 |
| `no_round_number` | 110 (2.3%) | 60.9% (67) | 94% via multi-source alone | 11 |
| `unknown` | 0 | — | — | — |

**Any pool with ≥2 sources passes confirmation almost automatically**
(100% and 60.9% pass rates) **because multi-source alone satisfies the
minimum-count rule** — this is the real mechanism, precisely
characterized for the first time in this project: it is not that
round-number pools are penalized by a source-quality judgment, it is
that single-source pools (of which round-number is 93%+ of the
population, but not definitionally the only kind) have one fewer path
to confirmation than multi-source pools have, by construction.

### 7.2 Directional outcomes, confirmation-passing candidates, by source group

Primary endpoint (+1/−1 ATR), all figures resolved (censored excluded
from rate, included in n):

| Source group | n | Primary favorable rate | Secondary favorable rate | Month-clustered mean ± half-width (4 clusters) |
|---|---|---|---|---|
| `round_number_only` | 183 | 49.5% (n=182) | 34.1% (n=179) | 49.2% ± 11.7pp |
| `round_number_plus_other` | 215 | 47.2% (n=214) | 32.4% (n=210) | 47.6% ± 5.9pp |
| `no_round_number` | 67 | 44.8% (n=67) | 34.8% (n=66) | 43.5% ± 20.7pp |

**No source group differs meaningfully from any other, or from 50%.**
Every month-clustered confidence interval overlaps every other group's.
`no_round_number`'s wide interval (±20.7pp) reflects its own small
sample (n=67) — not a stronger effect, a noisier one.

### 7.3 The key diagnostic: candidates that would be newly unblocked

Round-number-only candidates **rejected** by confirmation (n=4,213 —
the population a source-conditional rule change would newly admit):

| | n | Primary favorable rate | Secondary favorable rate | Month-clustered mean ± half-width |
|---|---|---|---|---|
| Pooled | 4,213 | 50.1% (n=4,194) | 34.8% (n=4,115) | 50.2% ± 2.9pp |
| 2024-02 | 983 | 51.3% | — | — |
| 2024-04 | 1,037 | 51.4% | — | — |
| 2024-09 | 1,169 | 47.5% | — | — |
| 2025-12 | 1,024 | 50.7% | — | — |

**This is the single most decisive number in this sprint.** At n=4,213
(the largest sample this entire research series has ever produced for
a single comparison), the newly-unblocked population sits at almost
exactly 50% favorable, stable within a 4-point range across all 4 TRAIN
months, with a tight month-clustered interval (±2.9pp). There is no
directional edge, positive or negative, to be found here — the
population the sprint set out to test shows a flat coin-flip base rate.

### 7.4 CVD alignment — diagnostic only, per the frozen plan, not
decision-driving

Among round-number-only confirmation-passing candidates (n=183),
`cvd_direction` CONFIRMS showed 56.0% favorable (n=109) vs. CONTRADICTS
39.7% (n=73) — a 16.3-point gap. **This is reported as a diagnostic
observation only, exactly as the frozen plan specified** — it was not
the pre-registered primary comparison, it was not used to gate the
Section 8 decision, and per the sprint's own "no additional subgroup
search after viewing results" rule, it is not chased further here. It
is noted as a genuinely interesting pattern for a possible future,
separately-pre-registered hypothesis — not evidence for or against
Hypothesis 1 as tested.

### 7.5 What the numbers do and do not establish

- **Higher win rate**: none of the three source groups shows one
  relative to another with any consistency once month-clustered
  uncertainty is applied.
- **Less-negative expectancy**: not measurable directly for the
  newly-unblocked population (it was never traded — no realized P&L
  exists for it, and none is invented here, per the sprint's own
  explicit instruction). The directional favorable-rate proxy (50.1%)
  gives no reason to expect it would out-perform the currently-accepted
  population's own realized −$11.03/trade.
- **Positive after-cost expectancy**: not established for any group.
- **Reliable incremental improvement**: not established. A
  better-looking point estimate in one subgroup (there isn't a
  meaningfully better-looking one here) would not, on its own, establish
  that the current confirmation requirement *causes* losses — and this
  sprint does not even have that better-looking point estimate to
  begin with.

## 8. What remains unknown

- Whether CHOCH or SMT, evaluated on their own (outside the OR'd
  minimum-count rule), carry any independent value — not tested this
  sprint, and not implicated by this sprint's own null result (this
  sprint tested source composition, not the individual merit of the
  other two confirmation paths).
- Whether the `cvd_direction`/round-number diagnostic (Section 7.4)
  reflects anything real — explicitly left open, not investigated
  further per the frozen plan's own discipline.
- Whether funding matters more for a live, continuously-running
  position-sizing/margin-aware system than for this fixed-trade overlay
  — explicitly out of scope (Section 3.3's own limitation).
- Whether the regime-conditional hypothesis (Hypothesis 2) holds on
  SOL — untouched by this sprint, remains the natural next step.

## 9. Final conclusion and recommended next action

### Decision: **DO NOT PURSUE THIS SOURCE HYPOTHESIS**

Per the frozen decision rule, this verdict applies because the bounded,
properly-isolated re-analysis — at roughly 70–140× the sample size of
the original small-sample observations that motivated Hypothesis 1
(Touch/Volume sprint's 29/32 real trades; here, 183/4,213 candidates) —
found **no economically relevant, consistent directional effect** by
source group, and specifically found the population that would be
newly unblocked by relaxing the confirmation requirement for
round-number-only pools sitting at an almost exactly flat 50.1%
favorable rate, stable across all 4 TRAIN months. This is not explained
by funding (quantified and shown immaterial, Section 3), not explained
by source-selection bias entering before `pool_id` choice (ruled out,
Section 4), and not explained by an incomplete opportunity population
(corrected via the one authorized replay, Section 5). The original
small-sample observation does not replicate at scale — the honest
reading is that it was noise, not a masked real effect.

Funding accounting does **not** need to be addressed first — it was
quantified directly on the real ledgers and found immaterial to every
conclusion in this report.

### Recommended next action

**Per the strategic review's own contingency ("if the source hypothesis
is unsupported, return to the ranked strategic alternatives rather than
automatically adding another filter"): proceed to Hypothesis 2
(regime-conditional reversal thesis) as the next bounded sprint.** It
remains untested on SOL, has real (if BTC-only) supporting evidence,
requires no new data, and — like this sprint — can reuse the
already-recovered pre-filter population (`funding_sprint_prefilter_population.pkl`,
now stratifiable by `structure` state) as its own starting candidate
set, keeping the "shortest sensible route" discipline intact. This
sprint does not design that experiment — it is named here only as the
recommended next action, per the strategic review's own priority order,
not executed.

## 10. Explicit confirmations

No production file was modified. No confirmation gate was removed or
altered in production. No parameter optimization was performed. No
subscription or data purchase was made. No new setup was built. No
alternative-strategy backtest was run. VALIDATION and FINAL_HELD_OUT
(2025-02, 2025-07) were not accessed. SOL remains the primary research
instrument. All new files from this sprint (research modules, tests,
frozen protocol + hash, this report) are left **uncommitted**, per the
authorizing instructions, awaiting your review.
