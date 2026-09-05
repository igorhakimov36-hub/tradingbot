# SOL Progressive Stop Management Research — Frozen Analysis Plan

**Written and frozen BEFORE computing any candidate-policy outcome.**
SHA-256 hash recorded immediately after saving, before any backtest is
run, and re-verified before the final report is written.

**Revision note**: this document's PBO/CSCV section was revised once,
in place, after the user supplied the actual "Probability of Backtest
Overfitting" paper (it had not been attached when this protocol was
first drafted) — grounding that section in the paper's own directly-quoted
guidance rather than a from-memory summary. This revision happened
**before any candidate-policy outcome was computed** (verified: no
backtest had been run at the time of the edit) and touched only the
PBO/CSCV methodology discussion — no policy definition, timing rule,
comparison, or decision criterion elsewhere in this document was
altered. The hash below is of the final, revised text.

**Explicit framing, per the authorizing instructions**: 2024-02,
2024-04, 2024-09, 2025-12 have already been inspected repeatedly across
six prior sprints in this project. This protocol freeze is a discipline
device (pre-registering hypotheses and decision rules before seeing
results) — it does **not** create a fresh holdout, and no verdict below
is VALIDATION-grade evidence.

## Hypothesis

Gradually reducing original downside as a trade moves favorably may
improve net expectancy or reduce drawdown without sacrificing too much
upside. **Not assumed true** — the completed, causally-corrected Exit
Management Sprint already rejected a different (structure-based)
trailing mechanism on BTC data, 6/6 configurations, via the identical
"protects some losses, sacrifices more/larger winners" mechanism this
sprint must test for, not assume away.

## The four policies (frozen, restated exactly)

All four keep entry logic, position sizing, initial stop, and
take-profit identical. R0 = `|entry_price − original_stop_loss|`,
captured once, never recalculated from a tightened stop.

- **A — Control**: existing fixed stop and take-profit, unchanged
  (`exit_policy=None`).
- **B — Quarter-R staircase**: `step_size=0.25R`, `tighten_per_step=0.25R`.
- **C — Half-R staircase**: `step_size=0.50R`, `tighten_per_step=0.50R`.
- **D — Slower quarter-R staircase**: `step_size=0.25R`, `tighten_per_step=0.125R`.

Implemented as one parameterized `StaircaseExitPolicy`
(`strategy/research/progressive_stop_policies.py`, already tested — 26
tests) via `stop_R(MFE_R) = -1.00 + floor(MFE_R / step_size) ×
tighten_per_step`, clamped to never exceed the running maximum (monotonic,
never loosens). Take-profit is never touched by any policy. These are
**declared research candidates, not claimed-optimal settings** — the
parameter set is not expanded after seeing results.

## Execution timeframe (frozen, documented)

**1-minute**, inherited unchanged from the existing infrastructure:
`BacktestRunner.on_replay_step` runs on the 1-minute replay clock;
`ExecutionSimulator.process_candle` checks stop/target against each
1-minute candle's own high/low; `ExitPolicy.apply_pending`/`evaluate`
are called on that same 1-minute cadence (confirmed by direct reading
of `backtest_runner.py` lines 414–493). This is the SAME granularity
every existing S001 backtest and cost figure in this project has always
used (entries are decided from 15m-derived signals, but stop/target
resolution has always been 1-minute) — not a new choice for this
sprint, made explicit here because it was previously undocumented.

## Timing rules (frozen)

- **Next-bar activation**: reused unchanged from
  `backtesting/exit_policy.py`'s two-phase `apply_pending`/`evaluate`
  contract (already causally verified in the completed Exit Management
  Sprint's addendum). A stop decided from bar N's own close-derived MFE
  is applied only at bar N+1's open, before bar N+1's own stop/target
  check — never retroactively to bar N.
- **Entry-bar exclusion**: `apply_pending`/`evaluate` are never called
  for the bar a trade opens on (a structural property of
  `BacktestRunner`'s own control flow — `active_trade` only becomes
  non-`None` after the opening branch completes for that bar) — MFE
  tracking therefore begins at the trade's own `entry_price` on the
  first bar the policy observes it, never at an earlier, pre-entry
  price. Verified directly by test
  (`test_mfe_tracking_starts_from_entry_price_not_bar_open`).
- **Gap and already-breached-on-activation handling**: `ExecutionSimulator.process_candle`
  fills a stop exit at exactly `trade.stop_loss` regardless of how far
  the triggering candle's low/high undercuts it — no gap-through
  worse-fill modeling exists anywhere in the simulator, for ANY policy,
  including the control (a pre-existing, disclosed limitation — see
  `docs/profitability_root_cause_investigation.md`, Section 2, item 8).
  This sprint does not modify `execution_simulator.py` (out of scope).
  Instead, `strategy/research/gap_aware_stop_fill.py` (tested, 9 tests)
  recomputes, as a **post-hoc sensitivity check applied identically to
  all four policies**, what the fill would have been if the triggering
  candle's own open had already gapped through the stop — using the
  candle's open as the realistic worst executable price rather than the
  stale requested level. **The primary comparison uses the existing
  simulator convention** (consistent with every other report in this
  project); the gap-aware recomputation is reported alongside as a
  sensitivity check, not a replacement.
- **Tick-size rounding**: stop prices are rounded to 2 decimal places
  (`DEFAULT_PRICE_TICK = 0.01`) — a disclosed, reasonable assumption for
  SOL's own TRAIN-period price range, not verified against Binance's
  exact historical tick size for the full 2024–2025 SOLUSDT perpetual
  period.

## Cost treatment (frozen)

Fees (0.04%/side) and slippage (0.02%/side) exactly as used throughout
this project. **Funding is recalculated per policy, per trade, using
each trade's own actual (policy-specific) entry/exit timestamps** —
reusing `strategy/research/funding_overlay.py` unchanged (already
tested, 22 tests, from the completed funding sprint). The control's
already-published funding total is never reused for a different
policy's own, generally different, exit timing. If any TRAIN-month
funding record used by a policy's trades is found incomplete, this is
disclosed explicitly and that trade's funding-inclusive figure is
reported as unavailable — never assumed zero.

## Comparisons (frozen, both required, kept separate)

1. **Paired comparison**: identical baseline (control) entries and
   quantities; for each entry, sequential candle-by-candle exits are
   independently simulated under each policy from the SAME entry —
   answers "what would have happened to exactly these trades under a
   tighter stop," free of any slot-availability confound. Reports:
   baseline losses reduced, baseline winners closed early (including
   winners turned into losses), net monetary value saved vs. sacrificed,
   paired per-entry change in net R (always expressed in the ORIGINAL
   R0, never a policy-specific recalculated R).
2. **Sequential standalone backtest**: each policy run through the real
   `BacktestRunner` end to end, independently — entries can differ from
   the control once an earlier exit frees the single trade slot sooner
   or later. This additional effect (a changed entry sequence, not a
   direct exit effect) is reported **separately**, never conflated with
   the paired comparison's own direct-effect numbers.

MFE/MAE independent-excursion figures may be reported to help explain a
result but are never substituted for either comparison above.

## Statistical treatment and safeguards (frozen)

- **Primary uncertainty method**: month-clustered (4 TRAIN months as 4
  clusters; mean of per-month paired-difference values ± its own
  standard error across those 4 cluster means, t-distribution df=3) —
  reused unchanged from every prior sprint's own convention this
  session. A naive per-trade CI is reported alongside, explicitly
  labeled as an upper bound on precision only (assumes independence
  the data does not have).
- **Multiple-comparison control**: three candidate policies (B, C, D)
  are compared against the control — a family of 3 comparisons.
  A Bonferroni-adjusted significance threshold (α/3) is applied to any
  point where a formal significance claim is made; where only a
  descriptive point estimate and CI are reported, the family size (3)
  is disclosed alongside so a reader can judge multiplicity
  themselves — no formal claim of "policy X beats control" is made
  without this adjustment.
- **Temporal dependence**: trades within a month are not independent
  (shared regime, overlapping-in-effect market conditions) — addressed
  structurally by the month-clustered method above (each month
  contributes exactly one point to the cluster-level statistic,
  regardless of how many trades it contains), not by treating every
  trade as an independent observation.
- **Concentration check**: for every reported effect, the largest
  single trade's own contribution to the aggregate paired money-saved/
  sacrificed figure is reported as a percentage of that aggregate —
  an effect resting on 1–2 exceptional trades is disclosed as such, not
  presented as a general pattern.
- **Sample-size disclosure**: S001 produces ~11–19 trades/month on SOL
  TRAIN (already established, ~61 total pooled) — far too few for any
  of the four candidate-policy comparisons to be definitive on their
  own; this is stated plainly wherever a result is reported, not just
  once in a limitations section.

### Is a formal PBO/CSCV estimate meaningful here? (addressed per the
authorizing instructions, using Bailey, Borwein, López de Prado and
Zhu, "The Probability of Backtest Overfitting" — the actual paper,
fetched and read directly for this protocol, not recalled from memory)

**No — not with the evidence available in this sprint, and not
recommended for implementation.** Grounded directly in the paper's own
stated guidance, not an approximation of it:

- **On S (the number of subsamples)**: the paper states plainly, "S
  must be large enough so that the number of combinations suffices to
  draw inference. If S is too small, the left tail of the distribution
  of logits will be underrepresented," and concludes "we believe that
  S=16 is a reasonable value to use in most cases" — because S=16
  yields 12,780 logits with an estimation error `σ[f(λ)] < 0.0045`
  (via `σ[p̂] ≈ √(p(1−p)/N)`, worst case at p=0.5). The paper's S=4
  appears **only once**, in Figure 1, as a simple diagram explaining
  the combinatorial mechanic — never recommended as an analysis scale.
  This sprint has 4 TRAIN months. Treating each month as one subsample
  (the only natural choice, matching every other method already used in
  this project) gives S=4, C(4,2)=6 logits, and at p=0.5,
  `σ[p̂] ≈ √(0.25/6) ≈ 0.204` — roughly **45× larger** estimation error
  than the paper's own S=16 baseline. This is not a marginal shortfall;
  it is an order-of-magnitude gap from the paper's own stated threshold
  for the method to say anything at all.
- **On N (the number of trials/configurations)**: the paper states "N
  must be large enough to provide sufficient granularity... if the
  investor is sensitive to values of λ<1/10... N>>10 is required." This
  sprint has N=4 (policies A, B, C, D) — again below the paper's own
  explicit floor.
- **On T (the observation count)**: the paper's own worked practical
  application (Section 6) — an "optimal monthly trading rule" search
  over Entry day/Holding period/**Stop loss**/Side, structurally the
  closest example in the paper to this sprint's own subject — uses
  N=8,800 parameter combinations tested against T=1,000 daily prices
  (~4 years). This sprint's own pooled trade count (~61 real trades
  across the control alone) is two orders of magnitude below that T,
  and N=4 is three orders of magnitude below that N.
- **On misuse**: the paper separately warns, "we must warn the reader
  against applying CSCV to guide the search for an optimal strategy...
  CSCV can be employed to evaluate the quality of a strategy selection
  process, but PBO should not be the objective function on which such
  selection relies" — reinforcing (independent of the power question
  above) that even a well-powered PBO estimate must never be used to
  pick the winning policy after the fact; this protocol's own frozen,
  no-post-hoc-expansion parameter set already respects that boundary
  for an entirely separate reason (Step 6's own discipline).

Computing a PBO number on S=4/N=4 would produce a precise-looking
figure the paper's own quantitative guidance says cannot be trusted —
false precision, not real insight. **The safeguards this protocol
already applies instead** (month-clustering, a pre-registered/frozen
parameter set with no post-hoc expansion, sign-consistency-across-months
requirements, Bonferroni-adjusted multiplicity disclosure, and explicit
"insufficient evidence" as an allowed, non-forced verdict) are the
*appropriate* response to this project's actual sample size and
repeated-TRAIN-reuse history — a lighter-weight, honestly-scoped
substitute, not an attempt to informally approximate CSCV. If a future
sprint accumulates enough independent months (SECONDARY_VALIDATION plus
a larger TRAIN pool, pushing S toward double digits) and enough trades
per policy (dozens to hundreds, not single digits, pushing N and T
toward the paper's own stated floors), a properly-powered CSCV/PBO
estimate could become worth the effort — not before.

## Decision criteria (frozen, four allowed outcomes)

For each candidate policy (B, C, D) independently:

- **Evidence of improved net expectancy**: paired AND sequential net R
  per trade improves vs. control, in the same direction in ≥3 of 4
  TRAIN months, surviving the Bonferroni-adjusted multiplicity
  disclosure, not resting on 1–2 exceptional trades (concentration
  check < 50% of the aggregate effect from any single trade).
- **Risk reduction accompanied by lower returns**: marked-to-market
  drawdown and/or full-loss frequency measurably improve, but net
  expectancy/net P&L does not (a legitimate, distinct, non-null
  finding — not automatically inferior, reported as its own category).
- **No supported improvement**: neither expectancy nor risk-adjusted
  metrics improve, or the direction is inconsistent/reverses across
  months.
- **Insufficient evidence**: sample size, month-count, or conflicting
  signals prevent any of the above three from being supported — this is
  a valid, standalone conclusion, not evidence of "no effect."

**A smaller loss is not proof of a profitable strategy. An inconclusive
result is not proof of no effect.** Both stated explicitly wherever
relevant, not only here.

## Data boundary

SOL TRAIN only: 2024-02, 2024-04, 2024-09, 2025-12. No VALIDATION,
SECONDARY_VALIDATION, or FINAL_HELD_OUT month accessed (2025-02,
2025-07 never touched).

---
FROZEN — SHA-256 of this file (computed over the file as saved, before
any candidate-policy outcome was computed): see
`docs/sol_progressive_stop_management_protocol.sha256`.
