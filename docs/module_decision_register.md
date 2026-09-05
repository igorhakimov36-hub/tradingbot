# Module Decision Register
## Consolidated findings from the CMC / Liquidity Sweep / Order Block reviews

**Status: documentation only.** No module listed here has been modified. This register consolidates the three completed comparison reviews (CMC vs. LuxAlgo SMC, Liquidity Sweep vs. LuxAlgo Liquidity Swings, Order Block vs. LuxAlgo Order Blocks & Breaker Blocks) into one classified reference for future sprints.

---

## A. Confirmed corrections required before S008

### A1. Order Block BOS-event identity collapses consecutive same-direction breaks
- **Evidence:** direct code trace of `_detect_new_order_block`'s `is_new_break = bos != "NO_BOS" and bos != self._last_bos_state` — identity is direction-only. Concrete bar-by-bar trace: Bar 5 breaks swing_high=100 → OB#1 created, `last_bos_state="BULLISH_BOS"`. Bar 6 breaks a *new*, higher swing high (106) but `bos` evaluates to the same string `"BULLISH_BOS"` → `is_new_break=False` → no OB#2 created. Only resets if `bos` dips to `"NO_BOS"` in between.
- **Affected modules/setups:** `strategy/features/order_block.py` (`OrderBlockTracker`); downstream S002, S006 (via `BreakerBlockTracker`), proposed S008.
- **Classification:** defect (a correctness gap in the tracker's own edge-detection identity, not a modeling choice — the tracker's intent, per its docstring, is clearly to create one Order Block per genuine structural break).
- **Required tests:** a constructed sustained-trend scenario with ≥2 genuinely different swing-level breaks in the same direction and no intervening `NO_BOS`, asserting the current (collapsing) behavior explicitly, to be updated once corrected.
- **Dependency order:** must be resolved (or explicitly accepted as a known limitation with a documented reason) before S008 is built on top of `impulse_strength`/`mitigation_zone`, since S008's whole thesis is about capturing displacement in trending conditions — exactly where this collapsing is most likely to matter.
- **Future acceptance/rejection criteria:** a corrected identity (direction + broken level, at minimum) must be shown, on real data, to create additional Order Blocks specifically in sustained-trend segments without materially increasing false/noise blocks elsewhere (checked via touch_count/mitigation distribution, not backtest P&L).

### A2. Order Block origin-search boundary is not leg-scoped
- **Evidence:** `_find_last_opposite_candle` searches `self._recent_candles[:-1]` — bounded only by `structure_lookback` (default 500), not by the actual span between the broken swing level and the breakout bar. A leg with no opposite-colored candle (plausible in a strong, low-pullback trend) causes the scan to reach arbitrarily far back, potentially past the relevant swing pivot into unrelated prior structure.
- **Affected modules/setups:** same as A1.
- **Classification:** defect (the module's own docstring and institutional rationale describe "the last opposing candle before the impulsive move" — an origin selected from outside that move contradicts the stated design intent).
- **Required tests:** a constructed long-same-color-run scenario proving the search reaches outside the true impulse leg; a SOL-data behavioral measurement (not a unit test) of how often such runs actually occur on real 15m SOL data.
- **Dependency order:** same as A1 — resolve or explicitly document before S008.
- **Future acceptance/rejection criteria:** a leg-bounded search (e.g., scoped to candles between the broken swing pivot and the breakout bar) must be shown to change origin selection only in the constructed failure case, not in normal cases, before being adopted.

### A3. SOL price scaling (round_number_spacing, volume_profile_bucket_size)
- **Evidence:** `MarketIntelligenceCoordinator.__init__` hardcodes `round_number_spacing=500.0` and `volume_profile_bucket_size=50.0` — both absolute BTC-scaled prices. Confirmed via direct data comparison: SOL's own price range is frequently narrower than 500, and $50 buckets would collapse SOL's Volume Profile into 1-3 buckets. Confirmed further: `LiquidityPoolTracker` itself defaults `round_number_spacing` to `None` (safe), and `VolumeProfileTracker.bucket_size` has **no default at all** (required argument) — the BTC-specific numbers exist in exactly one place, the coordinator's own defaults.
- **Affected modules/setups:** every setup reading Liquidity Pool round-number-sourced zones or any Volume-Profile-derived level (S003, S005, S007, proposed S011).
- **Classification:** defect for SOL use (silently produces degenerate behavior), not a defect for BTC use (the existing default is fine for BTC's own price range).
- **Required tests:** implemented this sprint — see Sprint 1 report (`tests/test_instrument_scale.py`).
- **Dependency order:** resolved in Sprint 1, ahead of any SOL strategy research.
- **Status: corrected this sprint** (see Sprint 1 report below) — not merely registered as pending.

---

## B. Modeling decisions requiring controlled A/B research

For every item below: no change is authorized by this register. Each requires its own future controlled experiment (matching the methodology already used for S001's confirmation-gate promotion), never a threshold chosen by inspection or by fitting to backtest P&L.

### B1. Wick-only Order Block mitigation/invalidation vs. close/body-confirmed
- **Evidence:** `zone_lifecycle.py::compute_mitigation`'s own docstring: *"Uses wick (high/low) penetration... not a close-through-the-zone requirement."* Traced: a single deep wick with an immediate close-back can fully mitigate an Order Block and make it eligible for Breaker Block promotion in one bar. LuxAlgo's comparable script uses close/body-based invalidation throughout. **A real internal inconsistency was found**: our own Liquidity Pool sweep logic treats an identical wick-then-close-back shape as evidence of *rejection* (bullish for reversal), while Order Block mitigation treats the same shape as sufficient for *full invalidation* — opposite readings of a similar pattern in two trackers in the same codebase.
- **Affected:** `order_block.py`, `breaker_block.py`, S002, S006, proposed S008.
- **Classification:** modeling choice (deliberate, documented in the code) — not a bug, but untested against the alternative.
- **Required tests:** wick-only full mitigation with immediate close-back; a companion case isolating close-beyond without deep wick, to document the current boundary precisely; a controlled A/B on real data comparing the current wick-based threshold against a close/body-based alternative.
- **Dependency order:** independent of A1/A2 — can be researched in parallel, ideally before S008 relies heavily on `mitigation_zone_status`.
- **Future acceptance/rejection criteria:** adopt an alternative only if it produces a measurably different (not necessarily "better" without further OOS testing) active-block population on ≥2 independent SOL periods, with the difference explained by fewer premature/spurious invalidations, not by a shrunken sample.

### B2. Separation of touch, mitigation, invalidation, and confirmed breaker
- **Evidence:** traced precisely this sprint — in the current code, "invalidation" is synonymous with reaching 100% mitigation; there is no independently-defined invalidation concept, and "confirmed breaker" inherits the same wick-based trigger.
- **Affected:** same as B1.
- **Classification:** modeling choice / architecture question (should these four remain collapsed into two effective states, or be made genuinely independent fields?).
- **Required tests:** none beyond B1's — this is a conceptual clarification question that would be resolved by whatever B1's research concludes, not a separate experiment.
- **Dependency order:** resolve alongside B1.
- **Future acceptance/rejection criteria:** N/A until B1 is researched — this item exists to make sure any future change to B1 doesn't accidentally conflate concepts that should be recorded separately.

### B3. Liquidity Pool invalidation after sustained acceptance beyond the zone
- **Evidence:** traced precisely this sprint with concrete bar sequences — a pool that is cleanly broken and closed beyond (no same-bar reject) remains "active"/"unswept" indefinitely; a much later, shallower re-test can still be labeled a fresh "sweep," dated arbitrarily far after the level's liquidity was arguably already consumed.
- **Affected:** `liquidity_pool.py`, S001, proposed S007/S009.
- **Classification:** research hypothesis (a real, disclosed gap — not yet known whether it materially affects S001's real signal quality).
- **Required tests:** a constructed stale-sweep scenario (already traced conceptually — bars 1/2/5 in the review); a real-data measurement of how often S001's actual swept-pool signals were preceded by an earlier clean break of the same zone.
- **Dependency order:** independent of A1-A3; relevant to any future S001 re-certification or S009 design.
- **Future acceptance/rejection criteria:** only add a sustained-acceptance invalidation rule if real data shows a measurable fraction of S001's fires are against already-broken (stale) zones, and that excluding them changes win rate/expectancy in a consistent direction across ≥2 periods.
- **CLOSED by the Liquidity Pool Lifecycle Research Series — see Section D below.** The exact hypothesis named here (a bounded "Acceptance Pending" state, Policy C) was built, TRAIN-tested, and VALIDATION-tested on real SOL data; the corrected, reframed question ("are late-confirming sweeps materially weaker than timely ones?") was also separately tested. Net result: **do not promote — Policy A retained.** This entry is left in place as the original research-hypothesis record; D1–D3 below are the closing decision.

### B4. Single-candle sweep vs. a bounded multi-candle penetration-and-rejection state machine
- **Evidence:** traced precisely — a 2-bar poke-then-reject pattern (Bar 1 pokes above and closes above; Bar 2 closes back below, but Bar 2's own high no longer exceeds the zone) is invisible to the current same-candle rule. Confirmed inherited consistently from `strategy/liquidity.py`'s original single-candle primitive — a deliberate, project-wide convention, not an isolated oversight.
- **Affected:** `liquidity_pool.py`, S001.
- **Classification:** intentional design choice with a disclosed limitation (explicitly not classified as a defect, given the consistent project-wide precedent).
- **Required tests:** a constructed multi-candle rejection scenario proving it is currently missed; if pursued, tests for whatever bounded window (a new parameter) a future state machine would introduce.
- **Dependency order:** independent; lowest priority of the Liquidity Pool items given it requires genuinely new detection logic (a new rejection-window parameter), which this project's own standing rule treats cautiously.
- **Future acceptance/rejection criteria:** only pursue if B3's research shows the single-candle rule is measurably missing a meaningful population of genuine rejections, not merely as a theoretical completeness improvement.
- **Status: B3's research (Section D) did not find a measurable population of missed genuine rejections large enough to justify this** — Policy C's multi-candle bounded-window variant returned INCONCLUSIVE/KEEP-POLICY-A across both the original and reframed questions. Not pursued; left open only if future, differently-scoped evidence emerges.

### B5. Mutually exclusive BOS/CHoCH labels vs. retaining both persistent readings
- **Evidence:** traced precisely — `detect_bos`/`detect_choch` can both independently evaluate true on the same bar whenever a break opposes the prevailing `market_structure` regime (both conditions reference the identical `close < previous_swing_low` comparison). LuxAlgo's model is mutually exclusive by construction (`tag = trend.bias == BEARISH ? CHOCH : BOS`).
- **Affected:** `market_structure_tracker.py`, S001 (choch as optional evidence), S007 (bos as required), any future setup reading both.
- **Classification:** modeling choice, with a named real risk (double-counting the same event as two independent confirmations if a future setup naively uses both `bos` and `choch` as separate signals).
- **Required tests:** a unit test documenting the current co-occurrence explicitly (as a factual record, not yet a bug fix); if a mutually-exclusive variant is ever built, a direct comparison against the current independent-fields behavior for any setup that reads both.
- **Dependency order:** independent; relevant to any future setup design (including the "additive event-identity" direction named in the architectural preservation rule below) before that field is built.
- **Future acceptance/rejection criteria:** N/A until a concrete future setup actually needs to read both fields simultaneously — until then this is a named risk, not an active problem, since no current setup gates on both `bos` and `choch` together.

### B6. Fast/internal structure plus slower/swing structure on SOL
- **Evidence:** LuxAlgo's SMC script runs two parallel structure resolutions (internal, length=5; swing, length=50) — a genuinely richer multi-resolution read than our single 3-bar-fractal `MarketStructureTracker`. SOL's measured higher realized volatility (3-7% daily) makes it logically likely — not yet tested — that a single fast resolution produces more noise/churn on SOL than on BTC.
- **Affected:** `market_structure_tracker.py`, S007 (bos-gated), any future regime-gated setup (proposed S011).
- **Classification:** research hypothesis.
- **Required tests:** a real-data measurement of swing-pivot/BOS-flip frequency on SOL vs. BTC at the current 3-bar-fractal resolution, before proposing any specific second resolution or lookback value.
- **Dependency order:** relevant to the paused Sprint 3 (fresh SOL baseline) — the noise-sensitivity question should be measured there before any structural change is proposed.
- **Future acceptance/rejection criteria:** only pursue a second resolution if the frequency measurement shows SOL's current BOS/CHoCH churn rate is materially higher than BTC's in a way that plausibly degrades S007's or a regime gate's reliability.

### B7. Zone-endurance touch/volume accumulation
- **Evidence:** LuxAlgo's Liquidity Swings script accumulates a persistent count/volume tally for a zone while it remains untested — a genuinely different "sustained interest" measure from our `touch_count` (fixed at formation from sub-detector agreement, never updated by later price interaction).
- **Affected:** `liquidity_pool.py`, any future setup wanting a "how well-tested is this level" confirmation (proposed S009).
- **Classification:** research hypothesis (a real, currently-missing capability, not a defect).
- **Required tests:** none yet designed — this is a candidate feature, not a candidate fix; would need its own full test suite if ever built.
- **Dependency order:** lowest priority of the Liquidity Pool items — purely additive, no current setup depends on it.
- **Future acceptance/rejection criteria:** only build if a specific future setup's design (e.g., a revised S009) explicitly calls for it and can state what it would gate or confirm.

### B8. Last-opposite-candle vs. extreme-wick origin selection
- **Evidence:** LuxAlgo's Order Blocks script anchors on the leg's most-extreme-wick candle (by magnitude), not the last opposite-colored candle. Our own module's docstring explicitly grounds the last-opposite-candle rule in dealer/inventory theory ("where positioning against the eventual move was last transacted") — the more textbook ICT definition.
- **Affected:** `order_block.py`, S002, S006, proposed S008.
- **Classification:** research hypothesis (the current rule is judged more institutionally faithful, but this has not been empirically tested against the alternative).
- **Required tests:** a controlled comparison of the two origin-selection rules' resulting touch/mitigation populations on the same real data, only if A1/A2 (which affect the origin-search mechanism more fundamentally) suggest the origin-selection question is a live bottleneck.
- **Dependency order:** lowest priority — only revisit if S008's real-data behavior (post A1/A2 resolution) suggests the origin candle choice is itself a problem, not merely the identity/boundary defects already confirmed.
- **Future acceptance/rejection criteria:** N/A until A1/A2 are resolved and S008 has real data to point to a specific origin-selection problem.

---

## C. Existing behavior retained unless evidence later rejects it

These are conclusions, not open questions — each was directly compared against a specific LuxAlgo alternative and found to be as good or better, on causal/institutional grounds, evidence available today. Listed for completeness and to prevent re-litigating without new evidence.

1. **Liquidity Sweep's wick-beyond-plus-close-back reversal thesis** — more institutionally correct than LuxAlgo Liquidity Swings' break-of-level ("crossed") definition, which has no rejection requirement at all and is a mislabeled comparison to begin with (LuxAlgo's own title is "Liquidity Swings," not "sweep").
2. **Plural, bounded Liquidity Pool tracking** — LuxAlgo tracks only one active zone per side, discarding history; ours tracks a bounded, age-pruned, plural set.
3. **Plural, age-pruned Order Block tracking** — LuxAlgo has no age-based expiry at all (display-count-limited only).
4. **Continuous mitigation-depth information** — strictly richer than LuxAlgo's binary breaker flag.
5. **Separate mitigation-zone information** — LuxAlgo offers only one zone-width toggle (wick vs. body), not two independently-tracked zones.
6. **Edge-triggered touch counting** — LuxAlgo's Order Blocks script has no touch-count concept at all.
7. **Existing persistent BOS/CHoCH readings as context** — retained even as future event-based fields are considered additively (see the architectural preservation rule below); S007 explicitly and deliberately depends on the persistent (not edge-triggered) semantic.

**Each item above is retained "unless evidence later rejects it," not permanently frozen** — if a future controlled experiment (e.g., under B1-B8) produces real data contradicting one of these, this section should be revised, not treated as closed forever.

---

## D. Liquidity Pool Lifecycle Research Series — CLOSED

**Status: production decisions confirmed below.** This section closes
out the multi-sprint Liquidity Pool lifecycle/geometry/telemetry
research series run against real SOL TRAIN (and, where noted,
VALIDATION/SECONDARY_VALIDATION) data. Every sprint followed the
project's frozen-and-hashed protocol discipline; every research module
lived under `strategy/research/` with zero production footprint,
proven byte-identical to `strategy/features/liquidity_pool.py`'s own
behavior in each sprint's own test suite. `strategy/features/liquidity_pool.py`
and `strategy/setups/liquidity_sweep_reversal.py` (S001) were **not
modified by any sprint in this series**.

### Confirmed production decisions

- **D1. Keep current Liquidity Pool formation and geometry.** The band
  model (`zone_high`/`zone_low`, widened by `register_touch`) is
  retained unchanged.
  Evidence: `docs/liquidity_pool_wick_extremity_train_report.md`
  (verdict: **KEEP CURRENT GEOMETRY**). A LuxAlgo-style Wick-Extremity
  Zone ablation (anchoring the sweep boundary to a single real candle's
  own wick instead of the production band) was built, tested, and run
  on all 4 TRAIN months: only 5.2% of pools (263/5,040) were ever
  geometry-eligible, the pooled primary-endpoint gap (52.2% vs. 49.8%)
  was within noise, and only 2 of 4 months favored the alternative
  geometry — the frozen promotion criterion (material effect **and**
  ≥3/4 months) failed outright.

- **D2. Keep lifecycle Policy A** (the existing same-candle
  wick-beyond-then-close-back sweep rule). **Do not promote bounded
  Acceptance Pending / Policy C** (supersedes B3's open status above).
  Evidence, two separate controlled experiments:
  - `docs/liquidity_pool_policy_c_validation_report.md` — pre-registered
    SOL VALIDATION experiment on Policy C's original formulation
    (Policy C as an *additional detector* of sweeps Policy A misses).
    Verdict: **INCONCLUSIVE** — the core criterion was structurally
    impossible to pass (Policy C's same-candle check is byte-identical
    to Policy A's, so it can never detect a sweep Policy A misses,
    confirmed at exactly 0%), even though 6 of 7 other criteria passed.
  - `docs/liquidity_pool_staleness_secondary_validation_report.md` —
    the corrected, reframed question ("are Policy A sweeps that only
    confirm after 16+ bars beyond the boundary materially weaker than
    timely ones?"), tested on 4 separately-verified-unused SECONDARY_VALIDATION
    months. Verdict: **KEEP POLICY A** — late-confirming sweeps
    (`LATE_RECLAIM`) were statistically indistinguishable from, or
    better than, timely sweeps, stable across all 3 tested windows
    (8/16/32 bars).
  - Net decision: Policy C (in either formulation) is not promoted;
    Policy A remains production logic.

- **D3. Do not promote LuxAlgo Wick-Extremity geometry.** Same evidence
  as D1.

- **D4. Do not promote Touch Count as a filter.**
  Evidence: `docs/liquidity_pool_touch_volume_train_report.md`. Tested
  as an independent hypothesis (frozen buckets 0/1/2/3+ prior touch
  episodes, candle-overlap definition) across all 4 TRAIN months
  (n=224–2,473 pools per bucket). Pooled primary-endpoint spread was
  1.6 percentage points (well below the frozen 5-point threshold), not
  monotonic, and the bucket ranking reshuffled every TRAIN month
  (same-direction-in-≥3/4-months criterion failed). Classified as a
  confident null result, not an underpowered one, given the large
  per-bucket sample sizes.

- **D5. Do not promote normalized Volume as a filter.**
  Evidence: same report as D4. Tested independently of Touch Count
  (outcome-blind quartile buckets on a new causal trailing-median
  relative-volume baseline, `lookback_minutes=240`). Pooled spread was
  3.6 points (below threshold), U-shaped rather than monotonic, and the
  direction of the effect **flipped** between TRAIN months. Controlling
  for Touch Count collapsed the gap to 1.3 points; controlling for
  source showed the 94%-majority round-number population had
  essentially zero effect (0.04-point gap) — the only sizeable gap was
  confined to the smallest, least-powered non-round-number subgroup,
  disqualifying by the frozen protocol's own source-control requirement.

- **D6. Do not build a combined Touch Count + Volume rule.** Per the
  authorizing instructions for that sprint, the two were evaluated as
  fully independent hypotheses throughout and no combined score/filter
  was ever computed — moot now that both were independently rejected
  (D4, D5), but recorded explicitly since it was a standing scope
  boundary, not an afterthought.

- **D7. Keep the research telemetry research-only.** Every module built
  across this series (`strategy/research/liquidity_pool_lifecycle_policy.py`,
  `liquidity_pool_policy_c.py`, `liquidity_pool_staleness_telemetry.py`,
  `liquidity_pool_wick_extremity*.py`, `liquidity_pool_touch_episodes.py`,
  `liquidity_pool_touch_volume*.py`) remains under `strategy/research/`
  only. None is imported by `strategy/features/`, `strategy/setups/`,
  or the live/backtest execution path. Each sprint's own test suite
  includes a direct byte-identical-production-output proof.

### Confirmed structural findings (measurements, not modeling choices)

- **D8. Round Numbers dominate pool creation (94.4%) and actual sweeps
  (94.8%) almost identically, but only 47.5% of exact-linked S001
  trades** (vs. 94.4% of the underlying population).
  Evidence: `docs/liquidity_pool_touch_volume_train_report.md`, Section
  1. Traced to a specific, pre-existing mechanism: S001's own
  `pool_has_multiple_sources` additional-evidence check
  (`strategy/setups/liquidity_sweep_reversal.py`) structurally
  disadvantages single-source (round-number-only) pools, which must
  clear CHOCH or SMT confirmation alone instead of getting a "free"
  additional-evidence point. This is a **confirmed characterization of
  existing S001 behavior**, directly measured — not a defect (S001 was
  explicitly out of scope for correction in that sprint) and not a
  hypothesis.

- **D9. ~5,041 pool instances correspond to only ~60–82 unique logical
  price levels per month (~70 typical) — 99.3–99.7% of pool instances
  are re-creations of the same recurring levels, not independent
  events.**
  Evidence: same report, Section 1. Recorded explicitly as an
  **effective-sample-size and dependence caveat, not a confirmed
  implementation defect** — `strategy/features/liquidity_pool.py`'s own
  docstring documents this as intentional ("new orders accumulating
  near the same price afterward are a genuinely NEW pool, not a
  continuation of consumed liquidity"), and it was characterized, not
  repaired, per that sprint's explicit instructions. Applies to every
  pool-instance-count statistic produced across this entire research
  series (this report and the Wick-Extremity report before it) — the
  true number of independent round-number observations is a small
  fraction of the raw pool-instance count.

### Open future question

- **D10. The current Liquidity Sweep module (`strategy/setups/liquidity_sweep_reversal.py`,
  S001) is retained pending evidence from future setup-level work.**
  This research series tested the Liquidity Pool *feature* module
  (`strategy/features/liquidity_pool.py`) exhaustively — geometry,
  lifecycle timing, touch count, and volume — and found no promotable
  improvement. It did **not** test S001's own arbitration logic (the
  CVD/CHOCH/multi-source confirmation-count gate, D8's own mechanism)
  against an alternative. Whether S001's own confirmation logic —
  separately from the Liquidity Pool feature it consumes — could be
  improved (e.g., the round-number-discrimination effect in D8) is an
  open question for a future, separately-pre-registered S001
  re-certification sprint, not addressed here.

---

## E. CVD/Delta Module — Audit and Signal-Value Research — CLOSED

**Status: production decisions confirmed below.** Closes two completed
sprints: `docs/cvd_delta_module_logic_audit.md` (correctness audit) and
`docs/cvd_delta_signal_value_train_report.md` (TRAIN signal-value
research, frozen protocol SHA-256
`f2cb19b1841f02bb8bce1c15f4d28d3b0cd0bb38a93462edd4e17150be5034b8`,
verified unchanged through this closure). Both reports' original text
and frozen verdicts are **preserved unmodified** — this section adds
closure and interpretive context, it does not restate or re-derive
their findings.

### Confirmed production decisions

- **E1. No current CVD/Delta field met the signal-value sprint's own
  promotion criteria.** `cvd_direction`, `price_cvd_divergence_flag`,
  `cvd_exhaustion_flag`, and `delta_direction` were each tested as a
  separate hypothesis on real SOL TRAIN data; none reached
  `PROMOTE TO VALIDATION`. Verdicts (report Section 10): `cvd_direction`
  INCONCLUSIVE (S007 sample too small; the larger, initially-promising
  S001-candidate-pool effect failed its own required secondary-endpoint
  and source-redundancy checks), `price_cvd_divergence_flag`
  INCONCLUSIVE (numerically concerning direction, but n=47 with a
  month-clustered CI half-width of ±28.9 points — too unstable for any
  conclusion), `cvd_exhaustion_flag` INCONCLUSIVE (n=7, below the
  sprint's own 30-observation sample gate), `delta_direction`
  RETAIN AS METADATA (calculated correctly per the audit; no
  directional value found).
- **E2. No production demotion is justified by the available
  evidence.** Both currently-gating S001 fields
  (`price_cvd_divergence_flag`, `cvd_exhaustion_flag`) returned
  INCONCLUSIVE, not a confirmed negative result — the sprint's own
  statistical discipline explicitly treats "insufficient/unstable
  sample" as distinct from "demonstrated no value," and applies that
  distinction symmetrically to promotion and demotion decisions.
- **E3. Current production behavior remains unchanged.**
  `strategy/features/delta.py`, `strategy/features/cvd.py`,
  `strategy/setups/liquidity_sweep_reversal.py`, and
  `strategy/setups/trend_continuation_confluence.py` were read-only
  throughout both sprints — confirmed directly (git diff against the
  closure checkpoint shows zero changes to any file outside
  `strategy/research/`, `tests/`, and `docs/`).
- **E4. Signal calculation correctness and trading usefulness are
  separate, independently-established conclusions.** The audit
  (`cvd_delta_module_logic_audit.md`) found the Delta formula, unit
  handling, 1m→15m aggregation, replay-safety, and divergence/exhaustion
  timing all **correct** — a code/data-integrity finding. The
  signal-value sprint separately found no field's **directional value**
  established at TRAIN sample sizes — an entirely different question,
  answered independently. Neither finding implies the other; a
  correctly-calculated field can still carry no decision-relevant
  information, and this register records both conclusions as distinct
  facts rather than collapsing them into one "CVD is/isn't good" verdict.
- **E5. Session-reset (session-anchored CVD) research remains
  deferred**, per the signal-value report's own Section 11: no field
  established value for a reset mechanism to improve, and the one
  near-miss (`cvd_direction`) failed for a reason (source concentration)
  a reset would not address. Not revisited until a future sprint
  establishes a genuinely useful, redundancy-surviving field.

### Recorded limitations (from the signal-value report, restated for register visibility)

- **Sample-size**: `price_cvd_divergence_flag` CONFIRMS n=47,
  `cvd_exhaustion_flag` CONFIRMS n=7, S007's entire candidate pool n=25
  — all below or at the edge of the sprint's own 30-observation gate.
- **Source-dependence**: `cvd_direction`'s pooled 6.4-point gap was
  concentrated entirely in round-number-sourced pools (+16.2pp there vs.
  −0.5pp elsewhere).
- **Endpoint dependence**: `cvd_direction`'s primary-endpoint
  (`+1/−1 ATR`) gap did not replicate at the secondary endpoint
  (`+2/−1 ATR`: 33.02% vs. 33.74%, essentially flat).

### Interpretive clarifications (this closure, not a reopening of the frozen verdicts)

These qualify how the above findings should and should not be read.
They do not change any verdict in the original report.

- **A source-specific effect is not automatically an artifact — it may
  be a conditional hypothesis.** `cvd_direction`'s effect being confined
  to round-number-sourced pools was classified `Insufficient evidence`
  for a *general* incremental effect (correct, since the original,
  unconditional hypothesis as tested did not hold across the whole
  population) — but this is not evidence that a *narrower*, explicitly
  conditional hypothesis ("does `cvd_direction` add value specifically
  at round-number-sourced S001 candidates?") is false. That narrower
  question was not pre-registered or tested as its own hypothesis this
  sprint, and remains open, not rejected.
- **Failure at the +2 ATR secondary endpoint limits the claim the +1 ATR
  primary result can support — it does not erase the primary result.**
  The primary-endpoint gap (6.44pp, positive in 4/4 months) is a real,
  measured pattern in the TRAIN data. Its failure to replicate at a
  larger favorable-move threshold means the evidence cannot support a
  claim of a robust, magnitude-scalable effect — but the primary-endpoint
  measurement itself stands as reported, unretracted.
- **Worse total P&L with many more trades does not, by itself, prove
  better filtering.** The S001 ablation (Section 8 of the signal-value
  report) found removing the CVD gate multiplies trade count ~7.5×
  while total net P&L worsens roughly proportionally (both control and
  neutral have per-trade expectancy within about $1 of each other,
  −$11.03 vs. −$12.10). The *aggregate* P&L difference is arithmetic
  (more losing-expectancy trades sum to a larger loss) and was never
  used alone in the report to argue the gate adds value — the report's
  own basis for any (weak, inconclusive) support of the gate was the
  per-trade SHARED-vs-NEUTRAL-ONLY comparison (37.5% vs. 34.8% win
  rate), explicitly flagged there as within noise at this sample size.
  Recorded here to preempt a future reader citing the aggregate P&L gap
  alone as if it were the evidence.
- **Failure to establish value does not prove a feature is useless.**
  Every `INCONCLUSIVE` verdict in E1 reflects "not enough evidence to
  conclude either way," not "shown to add nothing." Treat these fields
  as genuinely open questions for a better-powered future sprint, not
  as settled negatives.

---

## Architectural preservation rule (guidance for a future sprint, not authorized now)

Per direction: any future correction to the persistent-vs-event-based BOS/CHoCH question (B5) must be **additive**, not a replacement:
- Preserve the existing persistent `bos`/`choch` readings for consumers that need ongoing context (S007's existing dependency must not break).
- Add a new, explicit, one-shot structural-event identity (direction + broken level + timestamp, at minimum) for consumers that need "this specific break happened now" — directly informing how A1's Order Block identity correction should eventually be built: the corrected identity should consume this new event field rather than re-implementing its own direction-string comparison.
- Any such addition must be designed to prevent the same underlying break from being double-counted as two independent confirmations by a future setup (the B5 risk).

This is not authorization to implement any of this now — it is the stated direction for whatever future sprint takes on A1/B5 together.
