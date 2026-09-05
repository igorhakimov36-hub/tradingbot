# SOLUSDT Multi-Module Setup Discovery — Frozen Research Protocol

Frozen before any candidate outcome is computed. Hashed immediately
after this document is finalized; the hash is verified unchanged
before any result in the eventual report is interpreted.

---

## 1. Module inventory (compact)

Reused from `docs/phase4_setup_expansion_research_design.md` (Step 1,
already-completed inspection) and `docs/module_decision_register.md`,
re-verified against current source this session (read-only, no file
changed).

| Module | Usable fields | Data required / SOL TRAIN availability | Availability in replay | Possible role | Known limitations / overlap |
|---|---|---|---|---|---|
| Order Block (`strategy/features/order_block.py`) | `impulse_strength` (unbounded, ATR-at-creation-normalized), `mitigation_zone_high/low` (origin candle body), `mitigation_zone_status`, `touch_count`, `zone_high/low` (full wick) | 1m OHLCV only, already available all 4 TRAIN months | Updated every bar from already-closed history; `touch_count` edge-triggered | Location + risk management (stop) | **A1/A2 (register): BOS-event identity collapses consecutive same-direction breaks; origin-search not leg-scoped — unresolved.** Accepted as a disclosed limitation for this sprint, not silently ignored (see §2, Candidate 1). Overlaps S002 (rejected) — this candidate must not repeat S002's missing magnitude filter. |
| Delta (`strategy/features/delta.py`) | `delta_strength`, `delta_direction` — **single most-recent CLOSED bar only**, not aggregated | 1m OHLCV (`taker_buy_volume`), confirmed real exchange data | One value per closed bar, no smoothing | Trigger / confirmation | Noisy by construction (no smoothing) — disclosed in Candidate 2's own failure modes. |
| CVD (`strategy/features/cvd.py`) | `cvd_direction`, `cvd_exhaustion_flag`, `price_cvd_divergence_flag`, per anchor | Same OHLCV base | `cvd_direction`/slope `None` until `bars_since_anchor >= window` (default 20) | Confirmation | **E1 (register): no field met signal-value promotion criteria — none rejected either (INCONCLUSIVE).** Usable as optional/untested evidence, never claimed proven. Correlated with Delta (both order-flow proxies from the same underlying taker-volume data) — **never used together as two independent confirmations in this sprint's candidates** (checked explicitly per candidate below). |
| Market Structure (`strategy/features/market_structure_tracker.py`) | `market_structure` (BULLISH/BEARISH/RANGE/UNKNOWN), `bos`, `choch` | Same OHLCV base | Level-based, persists while true | Regime gate | **B5 (register), re-confirmed by direct condition trace this session: `bos` and `choch` CAN both be true on the same bar.** Not used together as independent confirmations in any candidate below. |
| Volume Profile (`strategy/features/volume_profile.py`) | `current_forming_profile` / `closed_profiles`, each with `poc_price`, `value_area_high/low`, `bucket_size`, `poc_shift_from_previous_period`, `value_area_overlap_ratio` | Same OHLCV base | `current_forming_profile` is the live, in-progress period's own VA at decision time — this is what every candidate below reads (never a closed_profile, avoiding stale-period leakage) | Location + confirmation + target (S011's TP) | `poc_shift`/`overlap_ratio` are `None` for the first period of a run (no prior) — not required by any candidate below. |
| Session Boundaries (`strategy/features/session_boundaries.py`) | `previous_period_high_low` (derived snapshot key), `active_now` | Same OHLCV base | Prior period only available once one full period has closed | Not used this sprint | Excluded candidate (S010) depended on this; not built (§4). |
| ATR | N/A as a standalone field | — | **Not wired into the Coordinator/Snapshot** — confirmed again this session. Only accessible indirectly via Order Block's own `impulse_strength`/`atr_at_creation`. | — | No candidate below assumes a standalone ATR field exists. |
| Funding | `data/SOLUSDT-funding-{2024-02,2024-04,2024-09,2025-12}.csv` — all 4 TRAIN months confirmed present | Full coverage confirmed this session | Post-hoc overlay (`strategy/research/funding_overlay.py`, already built and tested in a prior sprint) | Cost model | Reused unmodified from the funding sprint; not re-derived. |
| Open Interest | No SOL file exists at all | N/A | N/A | Not used | Confirmed absent, not attempted. |

**Correlated-output rule applied**: no candidate below reads both
`bos` and `choch` as independent confirmations, and no candidate reads
both Delta and CVD as independent confirmations of the same
directional read (Candidate 1 uses CVD only as *optional* evidence;
Candidate 2 uses Delta only; Candidate 3 uses CVD exhaustion only).

---

## 2. Candidates (3 — see §4 for the excluded 4th)

All three are adopted from `docs/phase4_setup_expansion_research_design.md`'s
already-designed S008/S009/S011 (that document's own Step 1-3 research
was never implemented or backtested — this protocol carries it forward
into implementation), revised here only where current-session field
verification or the module decision register requires an explicit
disclosure. No threshold below was chosen by looking at TRAIN outcomes.

### Candidate 1 — S008: Displacement-Impulse Continuation
**Mechanism:** continuation. **Role split:** Order Block = location +
risk; `impulse_strength` = trigger-gate; CVD `cvd_direction` = optional
confirmation (not required).

- **Hypothesis:** an Order Block whose favorable excursion already
  exceeds its own creation-time ATR (`impulse_strength >= 1.0`)
  reflects validated institutional displacement; a first retracement
  into the origin candle's body (`mitigation_zone`) offers re-entry
  into that same participation.
- **Base opportunity:** any Order Block with `impulse_strength >= 1.0`,
  still active (not fully mitigated).
- **Context/location:** price currently inside that block's
  `mitigation_zone` range; `mitigation_zone_status == "active"`.
- **Trigger:** `touch_count == 1` (first revisit) on the current bar's
  close, all of the above true simultaneously.
- **Confirmation (optional, non-gating):** `cvd_direction` agreeing
  with the block's own direction — recorded, never required to fire.
- **Timing/expiration/invalidation:** evaluated fresh each bar from
  already-closed history (no future-candle dependency); invalidated
  when `mitigation_zone_status` leaves `"active"` or `touch_count != 1`.
- **Stop-loss:** the primary Order Block's own `zone_low`/`zone_high`
  (full wick range — one level looser than the mitigation-zone entry).
- **Take-profit:** fixed 2R (control-comparable).
- **Sizing:** identical to production convention — 1% equity risk per
  trade, `MIN_RISK_PERCENT = 0.006` floor, via the same
  `create_risk_based_trade_setup` production helper S001 uses.
- **Disclosed limitation carried forward, not silently ignored (A1/A2):**
  the Order Block tracker's own BOS-event identity can collapse
  consecutive same-direction breaks, and its origin search is not
  leg-scoped. This candidate's `impulse_strength`/`mitigation_zone`
  reads inherit both defects unresolved. Accepted per the register's
  own instruction ("resolved... or explicitly accepted as a known
  limitation with a documented reason") — resolving A1/A2 is out of
  scope for this sprint (a tracker-level correction, not a setup-level
  choice), and is disclosed here as a limit on how confidently any S008
  result should be read, not swept under the result.
- **What would contradict the hypothesis:** OOS profit factor at or
  below 1.0 consistent with control, or no measurable difference
  between the impulse-filtered and an unfiltered Order Block re-entry
  (interaction test, §5).

### Candidate 2 — S009: Failed Auction Reversal at the Value Area Boundary
**Mechanism:** reversal (mechanistically distinct from S001 — no
Liquidity Pool sweep involved at all).

- **Hypothesis:** an excursion beyond the current period's Value Area
  that fails within the same bar (closes back inside), followed by a
  next bar showing WEAKER participation on the excursion than the
  reversal, is evidence the range extension lacked real transactional
  support.
- **Base opportunity:** any bar N whose high exceeds
  `current_forming_profile.value_area_high` (SHORT case; mirror for
  LONG/`value_area_low`).
- **Context/location:** bar N's own close is back at or below
  `value_area_high` (failed excursion, same bar).
- **Trigger:** bar N+1 closes further in the reversal direction AND
  bar N+1's `delta_strength` exceeds bar N's own `delta_strength` (a
  plain numeric comparison of two already-closed bars, no invented
  magnitude).
- **Timing/expiration/invalidation:** the failed-excursion condition
  is evaluated only on bar N itself; if bar N+1 does not satisfy the
  trigger, the opportunity expires (no multi-bar carry-forward window
  — matches the project's own single-candle-primitive precedent,
  disclosed as a limitation, not a defect, per register B4).
- **Stop-loss:** bar N's own high (SHORT) / low (LONG) — the excursion
  extreme, already closed by entry time.
- **Take-profit:** fixed 2R.
- **Sizing:** identical production convention (as Candidate 1).
- **What would contradict the hypothesis:** the delta_strength
  comparison shows no measurable difference from an unfiltered
  poke-and-reject baseline (interaction test, §5), or OOS profit
  factor at/below 1.0.

### Candidate 3 — S011: Value Area Extension Fade (RANGE regime)
**Mechanism:** mean reversion (the only candidate with a hard regime
gate).

- **Hypothesis:** in an established RANGE regime, a price extension
  beyond the current Value Area by a multiple of the profile's own
  bucket resolution, with CVD already showing exhaustion, is evidence
  of over-extension relative to two-sided value.
- **Base opportunity:** `structure.market_structure == "RANGE"` AND a
  `current_forming_profile` exists.
- **Context/location:** current price beyond `value_area_high` (SHORT)
  / `value_area_low` (LONG) by >= 3x the current profile's own
  `bucket_size` (tracker-native unit, not an invented number).
- **Trigger/confirmation:** CVD exhaustion flag agreeing with a
  reversion read on the current bar's close (the only place this
  sprint uses CVD as a REQUIRED, not merely optional, confirmation —
  disclosed since `cvd_exhaustion_flag` itself remains E1
  INCONCLUSIVE at TRAIN sample sizes; this candidate tests it under a
  genuinely new condition, a RANGE regime + magnitude extension, not a
  re-run of the already-INCONCLUSIVE unconditional test).
- **Stop-loss:** entry offset by one further `bucket_size` multiple
  beyond the extension (reusing the same resolution unit as the
  trigger, not an invented percentage).
- **Take-profit:** the current period's own `poc_price` — a
  structural target, not fixed 2R (disclosed deviation from the
  fixed-2R convention, since "reversion to value" IS a
  reversion-to-POC thesis by construction).
- **Sizing:** identical production convention (as Candidate 1).
- **What would contradict the hypothesis:** the RANGE gate fires
  predominantly right before a real subsequent BOS (regime-label lag
  fading directly into a real breakout) — checked directly in §7, not
  assumed away; or OOS profit factor at/below 1.0.

---

## 3. Common conventions (frozen, apply to all 3 + S001 reference)

- **Symbol:** SOLUSDT only.
- **Periods:** the 4 already-registered SOL TRAIN months — 2024-02,
  2024-04, 2024-09, 2025-12 — and no others. VALIDATION,
  SECONDARY_VALIDATION, and FINAL_HELD_OUT are not accessed.
- **Costs:** fee 0.04%/side, slippage 0.02%/side (project standard,
  matching every prior SOL/BTC report) + funding via the existing,
  already-tested `strategy/research/funding_overlay.py` overlay,
  applied post-hoc to each candidate's own actual position lifetimes
  (never reusing S001's own funding total for a different candidate's
  generally-different exit times — same discipline as the Progressive
  Stop sprint).
- **State isolation:** every research Setup class is a pure function
  of its snapshot argument (per `strategy/setups/base.py`'s own
  protocol, re-confirmed this session) — no internal state carried
  between calls, satisfying the "no state can leak between trades,
  setups, or runs" requirement by construction, not by a patched fix.
  The audited attribute-based state-isolation pattern (from the
  Exit-Policy audits) applies only if a future exit-policy experiment
  is layered on top — **fixed exits only this sprint** (§6), so no
  exit-policy state exists to isolate; still verified by an explicit
  regression test (§8) that two sequential `evaluate()` calls on
  different snapshots never share mutable state.
- **FVG/IFVG boundary respected:** no candidate touches Fair Value Gap
  logic; the pending FVG lifecycle comparison and IFVG design remain
  untouched, per explicit instruction.
- **Position management:** fixed exits only. Progressive-stop Policy D
  remains frozen at INSUFFICIENT EVIDENCE, not touched, not jointly
  optimized with any candidate's entry.
- **One-trade-at-a-time, standalone only:** each candidate (and the
  S001 reference) is run alone via `StrategyEngineV2` with exactly one
  registered setup — no first-fired-wins arbitration between
  candidates this sprint (explicit instruction).
- **Reporting:** pooled (4-month) and per-month; month-clustered
  uncertainty (4 clusters, t-distribution df=3), the same method frozen
  and reused throughout this project's SOL research — no new
  statistical method introduced.

---

## 4. Excluded candidate — S010 (Session Range Breakout with Value Area
Acceptance Retest)

Not built. Reusing Phase 4's own already-completed risk assessment,
re-confirmed unchanged this session: the required 3-part sequence
(breakout event M at an unbounded historical distance, a later
retest-hold, then value-area migration) has no natural non-arbitrary
lookback bound without risking a fitted parameter, and is explicitly
flagged as the most likely of the four original proposals to simply
not fire often enough to test — the same failure mode already observed
with S007 (2-4 fires/month, too rare to certify). Building a third
reversal-adjacent or a fourth thin-sample candidate instead of
investigating this properly would not improve on Phase 4's own
reasoning; nothing has changed since that assessment to make S010 more
viable. Revisit only if S008/S009/S011 results show the portfolio
still needs a fourth setup and a non-arbitrary lookback bound can be
justified independently of any TRAIN result.

---

## 5. Interaction tests (predeclared, per candidate)

For each candidate, before any performance backtest, capture the full
opportunity population (every bar satisfying the BASE opportunity
condition alone, regardless of whether later filters would reject it
— never sliced from an already-filtered ledger) and report, on that
same population, the favorable-outcome rate under a fixed forward
first-passage endpoint (matching this project's own established
+1/-1 ATR-equivalent convention, adapted per candidate's own natural
unit) for four nested slices:

1. **Base trigger alone** (opportunity condition only).
2. **Trigger + context/location condition** (the zone/regime
   containment requirement, no confirmation).
3. **Trigger + confirmation** (the order-flow read, no context
   requirement) — where a candidate's design does not structurally
   separate context and trigger into two independently-omittable
   parts, this slice is marked N/A rather than forced.
4. **Trigger + both** (the actual candidate as designed).

This is diagnostic (opportunity-level), not executable-P&L — §6-7
covers real sequential backtests for the actual, complete candidates.
Per instruction, a combined hypothesis is not rejected solely because
an individual component shows no standalone main effect.

---

## 6. Metrics and decision criteria (frozen)

**Primary:** net expectancy in original R, pooled and per-month.
**Secondary:** net P&L, profit factor, marked-to-market drawdown,
exposure, win rate, average win/loss, trade count/frequency,
concentration (largest single trade as % of net; per-month
concentration; recurring-price-level concentration where applicable),
cost-sensitivity (a predeclared +50% relative increase to both fee and
slippage rates, applied uniformly — not a magnitude search).

**Decision language (frozen, matching this project's established
three-way classification):**
- **Positive exploratory performance**: after-cost expected value
  clearly positive, consistent in direction across >= 3 of 4 TRAIN
  months, and the interaction test (§5) shows the full candidate
  outperforming its base-trigger-alone slice (evidence the added
  conditions are doing real work, not just reducing sample size).
- **Insufficient evidence**: mixed direction across months, or a
  month-clustered CI that includes zero, or a sample too small
  (< 20 pooled trades) to distinguish from noise.
- **Unsupported hypothesis**: consistently negative after-cost expected
  value across >= 3 of 4 months, or the interaction test shows the
  full candidate performing no better (or worse) than its base-trigger
  slice.

Only "positive exploratory performance" candidates (at most 1-2) are
recommended for a separate, future, frozen VALIDATION experiment — not
authorized or executed this sprint.

**Planned run count (frozen):** 3 candidates x 1 standalone backtest
each (4 TRAIN months pooled) = 3 runs, plus S001 unchanged as a
reference re-run (not re-tuned) = 4 total sequential backtests. Plus
each candidate's own §5 interaction-test population slice (diagnostic,
not a backtest). No threshold sweep, no repeated re-runs with adjusted
parameters. If a candidate's disappointing result is observed, it is
reported as observed — no expansion of the search, no new comparison
added after the fact.

---

## 7. Trial log (all candidate variants and relevant prior research, for
multiple-comparison awareness)

This sprint tests exactly 3 new hypotheses (S008, S009, S011) plus 1
unchanged reference (S001). Relevant prior trials on the same SOL TRAIN
months, for cumulative multiple-comparison awareness (not re-run, not
re-interpreted, listed for disclosure only): S001 lifecycle
policy/geometry/touch/volume (5 sprints, module_decision_register.md
§D), CVD/Delta signal-value (4 field hypotheses, §E), SOL funding/source
re-analysis (1 hypothesis), SOL progressive-stop management (3
policies). This sprint's own 3 new hypotheses bring the project's
cumulative count of independently-tested SOL TRAIN hypotheses to
approximately 16-17 — disclosed explicitly in the final report's
uncertainty section, not hidden.

---

## 8. Verification plan (before outcomes are computed)

- Unit tests per candidate: opportunity-condition boundaries, direction
  (LONG/SHORT) symmetry, stop/target construction, determinism.
- State-isolation regression test: two sequential `evaluate()` calls on
  independently-constructed snapshots never share mutable state
  (direct proof, not an assumption).
- Causal-timing test per candidate: confirm every field read at
  decision time comes from already-closed history (no future-candle
  use) — direct code-path assertion, not a visual check.
- **S001 control-equivalence test**: run S001 standalone before and
  after this sprint's new research modules exist in the repository;
  confirm byte-identical output (trade count, net P&L, every field) —
  proves the new research code has zero footprint on the existing
  control.
- Full project regression suite run after implementation, before and
  after the interaction-test/backtest scripts are written.

---

## 9. Explicit boundaries (restated)

No production file is modified. No new symbol/month combination is
accessed. FINAL_HELD_OUT remains untouched. Progressive-stop Policy D
stays frozen (INSUFFICIENT EVIDENCE). No FVG/IFVG logic is touched. No
portfolio-level (multi-setup, first-fired-wins) evaluation this sprint.
All new code and docs are left uncommitted for review.
