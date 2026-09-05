# Current CVD/Delta Signal Value and Incremental-Edge Research — Frozen TRAIN Protocol

**Written and frozen BEFORE any TRAIN outcome is computed.** SHA-256
hash recorded immediately after saving, before any TRAIN month is
loaded for outcome computation, and re-verified before the final report
is written.

## Research question

Given the completed audit found no correctness defect
(`docs/cvd_delta_module_logic_audit.md`), do any current Delta/CVD
outputs provide reliable directional or incremental value beyond the
non-CVD information already available to S001 and S007? Session-anchored
CVD is explicitly **not** tested this sprint (gated on this sprint's own
result — see Section "Session-anchor gate").

## Locked scope

No modification to: Delta formula, CVD accumulation, reset behavior,
aggregation, divergence/exhaustion definitions, thresholds, S001/S007
production logic, trade setup, risk, exit logic, portfolio arbitration.
No new session resets, normalized indicators, hidden divergence,
weighted scoring, combined CVD signal, or CVD integration into a new
setup. Research-only observers/wrappers only, proven byte-identical to
production where used.

## Step 1 — Active field scope (frozen; excludes fields with no
directional interpretation)

Four fields are researched, matching every field currently published
with a genuine bullish/bearish interpretation:
`cvd_direction` (consumed, non-gating, S007), `price_cvd_divergence_flag`
(consumed, gating, S001), `cvd_exhaustion_flag` (consumed, gating, S001),
`delta_direction` (published, currently unconsumed by any setup — tested
here as a candidate). `cumulative_delta`, `delta_pct`, `delta_strength`,
`cvd`, `cvd_change_over_window`, `cvd_slope` are continuous magnitudes
underlying the four directional fields above (or, for `cumulative_delta`,
already documented in the codebase itself as superseded by CVD) — not
independently tested as separate hypotheses in this sprint, consistent
with "do not test a field merely because it exists." Frozen legacy-engine
functions (`evaluate_bos_quality` etc., confirmed in the completed audit
to have zero Delta/CVD dependency) are out of scope.

## Step 2 — Population A: native one-shot events (frozen)

**Event identity**: `(field_name, bar_i, confirmed_at)` — unique per
event by construction (a field can have at most one transition per bar).

**Edge detection (reused exactly from `strategy/research/cvd_delta_native_events.py`,
already tested)**: an event fires at bar *i* iff the field's raw value
at bar *i* is directional (bullish/bearish, not neutral/none) AND
differs from the immediately preceding bar's own raw value. A
same-direction value persisting across consecutive bars produces
exactly one event, at the bar it first appeared. A direct flip
(bullish→bearish with no intervening neutral bar) is its own new event.
`confirmed_at` is always that bar's own timestamp — every field's
computation already uses only that bar's own trailing window (proven
no-lookahead in the completed audit), so there is no earlier "pivot"
candle to backdate to.

**De-duplication**: none needed across events of the SAME field (edge
detection already produces one event per causal transition). No
cross-field de-duplication is performed — each field is evaluated as
its own independent hypothesis (per the authorizing instructions), so
two different fields both firing on the same bar are recorded as two
separate events belonging to two separate hypotheses.

## Step 3 — Population B: CVD-blind setup opportunities (frozen)

**S001**: a candidate opportunity exists at bar *i* iff
`LiquiditySweepReversalSetup._find_fresh_sweep(snapshot) is not None`
(a pool was freshly swept this bar — the sweep_condition) **AND**
`evidence_count >= 1` from CHOCH/multi-source/SMT evaluated via the
setup's own real, unmodified `_choch_confirms`/`_multi_source_pool`/
`_smt_confirms` methods (the confirmation_condition) — i.e. every
required condition **except** `cvd_condition` is satisfied, computed by
calling the real production methods directly (never re-derived). The
candidate's direction is the swept pool's own implied direction
(`SHORT` for a swept `buy_side` pool, `LONG` for `sell_side`), exactly
as production computes it. No de-duplication is needed: a pool can only
be freshly swept once (`resolved_at == snapshot.timestamp` is
momentarily true for exactly one bar per pool), so S001 candidates are
already one-shot by construction (confirmed in the completed audit,
Section 8).

**S007**: a candidate opportunity exists at bar *i* iff
`_liquidity_condition` and `_structure_condition` (S007's real,
unmodified private methods) are both satisfied — this is **already**
CVD-blind at the gating level in production (CVD is non-gating there),
so Population B for S007 is simply every bar where these two conditions
hold. **De-duplication (frozen, required)**: both of S007's required
conditions are level-based, not edge-triggered (documented directly in
the completed audit, Section 8) — the same underlying pool/trend
combination can satisfy both conditions on many consecutive bars.
Candidates are clustered by `(pool_id, direction)`: consecutive bars
where the same pool remains the qualifying pool and both conditions
still hold are one cluster: only the **first** bar of each maximal
consecutive run is kept as the representative opportunity. This exactly
mirrors the edge-triggering logic already applied to Population A,
applied here to avoid treating one persistent setup condition as
dozens of independent opportunities.

**Field classification at each candidate**: for every candidate and
every one of the 4 fields in scope, `strategy/research/cvd_delta_opportunity_populations.classify_confirmation`
(already tested) reads that field's raw value at that exact bar and
classifies it `CONFIRMS`/`CONTRADICTS`/`NEUTRAL` relative to the
candidate's own already-determined direction — computed **without**
conditioning on what CVD says (every candidate satisfying the non-CVD
requirements is included, whether or not `cvd_condition` would actually
have passed).

## Step 4 — Directional endpoint (frozen, reused unchanged)

Identical to every prior sprint in this research series: sequential,
unconditional first-passage starting the candle immediately after
confirmation; ATR frozen at confirmation (standalone, point-in-time
`AverageTrueRangeTracker`, period 14); primary `+1/-1 ATR`, secondary
`+2/-1 ATR`; fixed 32-candle horizon (unchanged — nothing about
CVD/Delta events makes the existing horizon invalid, so no new horizon
is introduced); same-bar ambiguity counted conservatively as adverse;
unresolved-within-horizon is right-censored, never a win/loss; no
conditioning on survival; MFE/MAE descriptive only. Reused directly
from `strategy/research/liquidity_pool_staleness_telemetry.first_passage_outcome`.

## Step 5 — Sample-size gates (frozen)

A pooled (4-month) comparison group with **fewer than 30 resolved
outcomes** is reported descriptively but is **never** used alone to
support `PROMOTE TO VALIDATION` or `PROPOSE DEMOTION` — classified
`INCONCLUSIVE` for that specific comparison regardless of the observed
gap. A per-month breakdown with fewer than 5 resolved outcomes in a
given month is reported but excluded from the "same direction in ≥3/4
months" tally for that month (treated as data-free for that month, not
as a vote either way).

## Step 6 — Clustering-aware uncertainty (frozen)

Individual 15-minute bars within a persistent field-reading run are not
independent observations (measured directly in the completed audit:
mean consecutive-run length 1.4–1.6 bars, longest observed run 4–7
bars) — already addressed structurally for the *primary* reported
figures by using one-shot events (Population A) and de-duplicated
opportunities (Population B), which removes the within-run
non-independence at the source rather than papering over it with a
post-hoc variance correction. For the *pooled* (4-month) percentage-point
comparisons, the **primary uncertainty estimate is month-clustered**:
each of the 4 TRAIN months is treated as one cluster; the reported
interval is the mean of the 4 per-month rates ± its own standard error
across those 4 cluster-level means (a t-distribution with 3 degrees of
freedom). A naive per-observation binomial CI is also reported
alongside, explicitly labeled as an **upper bound on precision** (it
assumes independence the data does not have, so it is always narrower
than or equal to the true uncertainty) — never used alone to justify a
promotion.

## Step 7 — Redundancy controls (frozen)

For every field showing an apparent pooled/CONFIRMS-vs-comparison
effect, the same comparison is re-run within fixed strata: per source
(Liquidity Pool `round_number`-only vs. other), per Market Structure
state (`snapshot.structure["bos"]`/`["choch"]` at the candidate bar),
per raw-volume regime (candidate bar's own 15m `volume`, split at the
pooled TRAIN median into "low"/"high"), per direction, per month. An
effect that only appears in one stratum and vanishes or reverses in
every other is classified `Mostly redundant confirmation` or
`No measurable information`, never `Incremental information`, per the
decision rules below.

## Step 8 — Exact S001/S007 ablation (frozen)

S001: real backtest (control) vs. `strategy/research/cvd_delta_neutral_setups.CVDNeutralLiquiditySweepReversalSetup`
(neutral variant — a direct subclass overriding only `_cvd_confirms`,
already tested to change nothing else). Both run standalone
(`StrategyEngineV2(setups=[...])` with exactly one setup each, never
combined), exact `pool_id` linkage via the same proven
`_find_fresh_sweep` instrumentation method used in every prior sprint —
never nearest-timestamp matching.

S007: **no A/B backtest is run.** CVD is already non-gating in
production, so a control-vs-neutral backtest would produce byte-identical
trades by construction (proven directly in
`tests/test_cvd_delta_neutral_setups.py`'s equivalent reasoning applied
to S001, and true a fortiori for S007 since CVD was never in
S007's own `required` list at all) — running one anyway would not be
informative and is explicitly discouraged by the authorizing
instructions. S007 evidence comes entirely from Population B's
opportunity-slicing analysis (Step 6/Section 5 of the report), reported
as diagnostic-only given its small sample (S007 has never been
backtested standalone in this project's history prior to this sprint;
its own sample size is established empirically in this sprint's Step
1 inventory, not assumed in advance).

## Decision rules (restated verbatim from the authorizing instructions, frozen)

Separate verdict per active field, one of:
`KEEP CURRENT ROLE`, `PROMOTE TO VALIDATION`, `PROPOSE DEMOTION`,
`RETAIN AS METADATA`, `INCONCLUSIVE`.

- **KEEP CURRENT ROLE**: a field already consumed by a setup
  demonstrates reliable incremental value in its current role.
- **PROMOTE TO VALIDATION**: a metadata/non-gating field demonstrates
  ALL of: ≥5-percentage-point primary favorable-rate separation between
  `CONFIRMS` and the relevant comparison group; same direction in ≥3 of
  4 TRAIN months; coherent secondary-endpoint behavior; adequate sample
  size (Step 5); no dependence on one direction/regime/outlier;
  survives Step 7's redundancy controls; setup-level evidence does not
  materially contradict it. Authorizes a future frozen VALIDATION
  experiment only, never production integration.
- **PROPOSE DEMOTION**: a currently gating field consistently removes
  equal-or-better opportunities, worsens after-cost expectancy, or has
  no incremental value despite adequate power. Does not modify
  production this sprint — requires a separate approved correction
  sprint.
- **RETAIN AS METADATA**: calculation correct, reliable decision value
  absent.
- **INCONCLUSIVE**: insufficient sample or cross-month consistency
  (Step 5).

Not renegotiated after results are seen.

## Data boundary

SOL TRAIN only: 2024-02, 2024-04, 2024-09, 2025-12. No VALIDATION,
SECONDARY_VALIDATION, or FINAL_HELD_OUT month accessed, enforced by an
explicit assert on every processed month string in every harness
script, matching every prior sprint. 2025-02 and 2025-07 are never
referenced.

---
FROZEN — SHA-256 of this file (computed over the file as saved, before
any TRAIN month was loaded for this sprint's own outcome computation):
see `docs/cvd_delta_signal_value_train_protocol.sha256`.
