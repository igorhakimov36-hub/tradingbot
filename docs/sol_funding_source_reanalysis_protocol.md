# SOL Funding Impact and Source-Conditioned S001 Re-analysis — Frozen Limited Analysis Plan

**Written and frozen BEFORE computing any subgroup outcome.** SHA-256
hash recorded immediately after saving, before any source-group or
CVD-alignment breakdown is computed, and re-verified before the final
report is written.

**Explicit context**: 2024-02, 2024-04, 2024-09, 2025-12 have already
been inspected repeatedly across five prior sprints in this project.
**This is exploratory re-analysis of already-seen data, not new
out-of-sample validation.** No verdict below should be read as
VALIDATION-grade evidence — only as a gate on whether a future,
separately-pre-registered VALIDATION experiment is warranted.

## Opportunity definitions (frozen)

- **Pre-filter population** (recovered via the one authorized replay,
  `funding_sprint_prefilter_replay.py`): every bar where
  `LiquiditySweepReversalSetup._find_fresh_sweep(snapshot)` returns a
  pool — i.e. every freshly-swept Liquidity Pool, **regardless of
  confirmation or CVD status**. n=4,721 pooled, 4 TRAIN months. This is
  the unbiased base population for the source-group comparison — source
  membership is recorded here, before any confirmation or CVD
  conditioning is applied.
- **Confirmation-passing subset**: pre-filter candidates with
  `evidence_count >= 1` (CHOCH/multi-source/SMT, OR'd) — n=465,
  identical to the completed CVD sprint's own `s001_candidates`
  (cross-checked: per-month counts match exactly: 117/110/113/125).
- **Production-firing subset**: confirmation-passing candidates that
  additionally satisfy `cvd_condition` — the real, exact-linked trades
  already reported (n=61).

## Source-confirmation semantics (frozen finding, not re-litigated)

`pool_has_multiple_sources` is **not** an independent mandatory gate —
it is one of three alternative confirmations
(CHOCH/multi-source/SMT) feeding a single minimum-count rule
(`evidence_count >= 1`), itself one of three required conditions
(sweep, CVD, confirmation) that must ALL hold for S001 to fire. A
round-number-only pool is not rejected *because* it lacks multiple
sources — it is rejected only if evidence_count is exactly 0, i.e. if
CHOCH and SMT *also* fail to confirm. Empirically, multi-source is the
**sole** confirming condition for 273 of 465 (58.7%) confirmation-passing
candidates pooled — not a marginal contributor.

`_find_fresh_sweep` selects the candidate pool by zone-list position
only (`candidates[0]`) — **no source-based selection occurs before
`pool_id` is chosen.** Source composition affects only the downstream
confirmation check, never which pool is nominated.

## Source grouping (frozen, mutually exclusive, decision-time only)

Applied to `sources` as recorded on the pre-filter population (already
the pool's own state at the moment `_find_fresh_sweep` selected it —
no later-acquired source is ever used):

1. `round_number_only`: `sources == ["round_number"]`.
2. `round_number_plus_other`: `"round_number" in sources and len(sources) > 1`.
3. `no_round_number`: `"round_number" not in sources`.
4. `unknown`: `sources` empty or missing. (Expected to be empty in
   practice — a pool cannot exist in production without ≥1 recorded
   source — reported explicitly if non-empty, never silently dropped.)

## CVD interpretation (frozen, reused unchanged)

`cvd_direction`, `price_cvd_divergence_flag`, `cvd_exhaustion_flag` at
the candidate's own bar, classified relative to the candidate's own
already-determined direction via
`strategy/research/cvd_delta_opportunity_populations.classify_confirmation`
(already tested, unchanged) — aligned = CONFIRMS, opposed = CONTRADICTS,
neutral = NEUTRAL. This is a diagnostic cross-tabulation only, per the
authorizing instructions — not a combined trading rule, and not itself
gating any comparison below.

## Primary comparison and decision criterion (frozen, completing the
strategic review's own criterion)

The strategic review (Section 6) proposed: promote to a frozen
VALIDATION experiment only if newly-unblocked round-number trades show
after-cost expected value "positive or not statistically distinguishable
from the currently-passing population's own (already-negative)
expectancy," in ≥3 of 4 TRAIN months. That criterion's **comparator**
was left implicit; completed here, before results are seen:

**Comparator**: round-number-only candidates that fail confirmation
*solely* because CHOCH and SMT both fail (i.e. would pass if
multi-source counted, or if the gate were removed for this source only)
vs. the actual currently-passing population's own after-cost
expectancy (the real 61-trade control ledger, already reported:
−$11.03/trade).

**Practical threshold, tied to the trading decision**: since these are
trades the system currently forgoes *entirely*, the relevant question
is not a percentage-point gap but whether newly-included round-number
trades would be **accretive or neutral** to the currently-accepted
population's own (already negative) per-trade expectancy — i.e. "at
least as good as what we already accept," consistent with the review's
own framing. A subgroup that is directionally better than the current
−$11.03/trade baseline, in ≥3 of 4 TRAIN months, on an adequate sample
(≥30 resolved outcomes, matching the sample-size gate already used in
the CVD signal-value protocol), is the bar for
`DESIGN A CONTROLLED SOURCE-CONFIRMATION EXPERIMENT`. This is **not**
a generic 5-percentage-point or 50% rule — it is anchored to the
system's own current (negative) accepted-trade baseline, the actual
after-cost economic quantity a promotion decision would change.

## Outcome timing, horizon, cost treatment (frozen, reused unchanged)

Sequential first-passage, starting the candle after confirmation; ATR
frozen at confirmation; primary `+1/−1 ATR`, secondary `+2/−1 ATR`;
32-candle horizon; same-bar ambiguity conservative; unresolved-in-horizon
right-censored. Reused directly from
`strategy/research/liquidity_pool_staleness_telemetry.first_passage_outcome`,
unchanged. For actual traded outcomes (the 61/455-trade ledgers), the
already-reported fee/slippage-inclusive net P&L is used, now with the
fixed-trade funding overlay (Step 2) added where a real trade exists.
Event-level directional outcomes (favorable/adverse/censored) and
realized trade P&L are kept in separate columns throughout — an
opportunity that was never traded is never assigned an invented P&L.

## Uncertainty method (frozen, reused unchanged)

Month-clustered: 4 TRAIN months as 4 clusters, mean of per-month rates
± its own standard error across those 4 cluster means (t-distribution,
df=3), exactly as used in the CVD signal-value protocol. A naive
per-observation binomial CI is reported alongside, explicitly labeled
as an upper bound on precision only.

## Sample-size limitations (frozen, disclosed before results)

Round-number-only pools that fail confirmation solely for lack of
CHOCH/SMT are expected to be a small fraction of the 4,721-pool
pre-filter population (most round-number pools are rejected because
NO condition, including multi-source, confirms — multi-source itself
requires ≥2 *sources*, i.e. the pool must already be more than
round-number-only to satisfy it, which is definitionally impossible for
`round_number_only` pools). **This is flagged explicitly now, before
computation**: `_multi_source_pool` checks `len(sources) > 1` — a
`round_number_only` pool (by this grouping's own definition,
`sources == ["round_number"]`) can **never** satisfy `multi_source_satisfied`
by construction. This means the round-number/multi-source interaction
hypothesized in the strategic review must be evaluated as "does
removing the *entire* confirmation requirement for round-number-only
pools help," not "does multi-source specifically help them" — corrected
here, transparently, before computation, per the sprint's own
instruction to complete an incomplete criterion rather than silently
proceed.

## Decision and stopping rules (frozen, restated verbatim from the
authorizing instructions)

One of: `DESIGN A CONTROLLED SOURCE-CONFIRMATION EXPERIMENT`,
`ADDRESS FUNDING ACCOUNTING FIRST`, `DO NOT PURSUE THIS SOURCE HYPOTHESIS`,
`INCONCLUSIVE`. No additional subgroup search after viewing results. Do
not continue slicing TRAIN until a favorable subgroup appears.

---
FROZEN — SHA-256 of this file (computed over the file as saved, before
any source-group or CVD-alignment outcome was computed): see
`docs/sol_funding_source_reanalysis_protocol.sha256`.
