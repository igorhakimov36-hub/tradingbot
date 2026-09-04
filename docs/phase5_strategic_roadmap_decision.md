# Strategic Roadmap Decision
## Lead Quantitative Systems Architect Recommendation

**Status: decision memo only. Nothing implemented, no backtest launched.**

Grounded in `docs/profitability_root_cause_investigation.md` and
`docs/phase4_setup_expansion_research_design.md` — no new investigation
was run to produce this document; it is a synthesis and decision.

---

## 1-4. Direct answers

### 1. Build/fix order: first through fourth

1. **O(n²) point-in-time fix** — cheapest, lowest-risk, zero-edge-impact item in this entire roadmap, and it unblocks every multi-month effort after it. Fixing it later just means paying its cost repeatedly in the meantime.
2. **MAE/MFE + mark-to-market drawdown module** — independent of (1) (see Section 12: these two can run in parallel if resourced separately), cheap, and directly extends a capability this investigation already had to hand-build once.
3. **Fresh-period validation of S001, S005, S007** on a newly-reserved, never-inspected period — this is where (1) and (2) pay off together, and it is the gate that determines how urgent everything after it really is.
4. **S008 implementation**, informed by whatever (3) shows about the continuation thesis's fresh-data legs.

### 2. What should the next sprint be?

**The O(n²) fix**, immediately followed by the MAE/MFE module (Section 12 notes these could be parallelized; sequentially, performance first). Not S008, not S005 redesign, not the Portfolio Risk Manager — all three are premature for reasons detailed below. This is a refinement of the user's own "Path B" framing, made explicit: performance optimization is the correct first move, but it must be followed by an explicit **fresh validation of the existing three setups** before any new setup is built (see Section 5 answer) — a step Path B's literal phrasing skips.

### 3. Is the O(n²) bottleneck a prerequisite for meaningful multi-month research, and does it come before MAE/MFE?

**Yes, it is a prerequisite for the CERTIFICATION-scale research this roadmap eventually needs (multi-month, multi-regime samples large enough to certify a setup) — but it is not a hard blocker for building the MAE/MFE module itself**, which can be developed and unit-tested against the already-fast single-month runs already cached this session. The two are independent workstreams; performance is recommended first only because it is the smaller, crisper task with zero design ambiguity, and finishing it first means every subsequent research run — including the MAE/MFE module's own validation — is already fast.

**Root cause, confirmed by direct code reading (not inferred):** `ReplayEngine.get_visible_history()` calls `get_available_data(records=self.records, current_time=..., ...)`, which does a full linear rescan of the *entire* records list, filtering by timestamp, on **every single replay step** — even though `self.records` is sorted once at construction and `current_time` only ever advances monotonically as replay proceeds. This is an O(n) scan repeated n times = O(n²) total, and it is the same mechanism this project already measured producing a ~180x slowdown for a 12x larger dataset in an earlier phase.

**Safest byte-identical optimization:** `ReplayEngine` already tracks `current_index`, which advances in lockstep with the replay position over the same sorted `records` array `get_visible_history()` re-scans from scratch. Since every record at `index < current_index` was already stepped over (and the array is sorted once, never mutated), `self.records[:self.current_index]` is *exactly* the same set `get_available_data` recomputes by filtering — but as an O(1) slice instead of an O(n) scan. This requires no change to `get_available_data`'s public contract (it stays a pure, general-purpose function for callers without a natural cursor, e.g. ad hoc scripts) — only `ReplayEngine`'s own internal use of it changes to the slice. The same repeated-full-rescan pattern also exists, at smaller absolute cost, in `PointEventProvider`/`BarSeriesProvider`'s native-mode calls to `get_available_data`/`get_latest_two_available_records` on their own (shorter) series — worth the same cursor treatment as a secondary step, not the primary one (the 1-minute `ReplayEngine` scan dominates the measured slowdown).

**Regression requirements before this is trusted:**
- Re-run every already-cached backtest configuration from this session (S001, S005, S007, and every combination, across both existing windows) and diff trade-for-trade, metric-for-metric against the cached pre-change results — not just "similar," exactly equal.
- New unit tests for the cursor logic directly: monotonic advancement, duplicate timestamps, `current_time` before any record, `current_time` after all records, a single-record series.
- Re-run the original O(n²)-discovering scenario (the multi-month Breaker Block OOS study) and confirm the timing now scales sub-quadratically — proof the fix actually changed the complexity class, not just a constant factor.
- Full existing test suite: zero regressions.

### 4. What should happen to S005?

**Quarantine but retain as a diagnostic control.** Not full archive: S005's code, tests, and historical results remain fully valid as a known-bad, high-frequency reference case — exactly the kind of setup a future Portfolio Risk Manager needs to prove it can suppress, and a real comparison point for any future confirmation-gate methodology. Not immediate redesign: redesigning now, before a confirmation-gate methodology has been proven on fresh (not contaminated) data and before the O(n²)/MAE-MFE tooling exists to evaluate the redesign properly, risks re-inventing S001's own "add ≥1 confirmation" fix without the controlled-experiment discipline that made it trustworthy the first time. Not "revisit only after new setups exist" either — that leaves S005 sitting in the "Approved Portfolio" default membership, actively damaging every combined-portfolio test run between now and then. **Concrete action:** remove S005 from any default "combined portfolio" wiring immediately (a configuration change, not a redesign) so it stops crowding other research, while keeping it fully runnable standalone.

---

## 5. S008 immediately after diagnostics, or fresh validation of S001/S005/S007 first?

**Fresh validation first.** S008 was explicitly designed as a second, differently-constructed answer to the same continuation-thesis gap S007 was built for — but S007 itself has never been evaluated on data it wasn't partly shaped around, and if a fresh period shows the continuation thesis simply doesn't hold up (or, conversely, that S001's edge was a real, reproducible March effect), that materially changes how much this roadmap should invest in continuation setups versus something else. Building S008 before that check risks spending real implementation effort investigating a thesis that fresh data might have already discredited or *already confirmed strongly enough to reprioritize*. It is also more efficient: fresh validation of S001/S005/S007 and the eventual validation of S008 can share the same newly-reserved period, rather than burning two separate never-touched windows in immediate succession.

## 6. Which of S008-S011, in what order?

Unchanged from `phase4_setup_expansion_research_design.md`, restated with the crowding evidence now reinforcing it: **S008 → S011 → S009. S010 remains not recommended for now.**

- **S008 first:** cheapest correct implementation (every field it needs — `impulse_strength`, `mitigation_zone`, `touch_count` — already exists on the Order Block tracker, confirmed in the Phase 4 audit), directly answers the diagnosed continuation gap, and — per the new crowding evidence — is worth validating *standalone* before ever combining it with anything, exactly per the existing validation plan's "signal-frequency check first" step.
- **S011 second:** the only candidate addressing the completely unaddressed RANGE regime, uses only already-wired fields (no new infrastructure), and is expected to be the highest-frequency of the four — directly useful for hitting the trade-count bar (Section 8) faster than S007/S008 are likely to.
- **S009 third:** sound economically but explicitly flagged as the candidate most likely to behave like a variant of S001 even though its trigger differs — worth building only once it's clear the portfolio still needs a third reversal-flavored setup after S008/S011's real numbers are in.
- **S010 not now:** the most restrictive signal sequence of the four, real risk of reproducing S007's "too rare to certify" problem, no natural non-arbitrary lookback parameter without risking a fitted threshold. Revisit only after S008/S011 results clarify whether a fourth setup is even worth the engineering cost.

## 7. When should a Portfolio Risk Manager / multi-position capability be introduced?

**Not before at least two setups have individually cleared the Section 8 evidence bar below** — realistically, after S008 (and ideally S011) have been fresh-validated standalone. This is the highest engineering-effort, highest-design-risk item in the entire roadmap (report 1 itself called it "the biggest architectural lift"), and building it before knowing the final setup roster risks sizing and shaping it around the wrong set of signals — exactly the "later work makes earlier work obsolete" failure mode the user asked about. A capital allocator is only worth building once there is more than one setup with a *proven* (not merely hypothesized) edge worth protecting from crowding.

## 8. Minimum evidence for an individual setup before portfolio integration

- **≥30 independent closed trades**, not accumulated by stitching together many very short windows.
- Measured across **at least 2 distinct periods** not used to design its rules, with the **same sign** of edge in both (a directionally consistent result, not a coin flip) — the same standard this project's own Fisher/Mann-Whitney precedent already treats n<8/arm as unreliable, raised here given the sign-flipping win rates already observed at n=10-13.
- A **signal-frequency check passed before full backtesting** (already this project's own stated plan) — confirms the setup fires often enough to reach the trade-count bar within a reasonable number of months, before investing in a full validation run.
- **MAE/MFE reviewed**, not just profit factor — no single trade should account for more than roughly 30-40% of total net profit (guards against a result driven by 1-2 outliers, a concern report 1 raised directly).
- Full existing validation suite passed: unit tests, replay safety, determinism, zero regression.

## 9. Minimum evidence for the combined portfolio before paper trading

- **≥2 (ideally 3+) individually-qualified setups** (Section 8) combined under the Portfolio Risk Manager.
- A portfolio-level backtest across **≥3-6 months** (continuous or independently-drawn, summing to that), spanning **at least one trending and one ranging period** (given S001's own demonstrated regime-dependence).
- Net profitability, after realistic costs, in the **majority of sub-periods**, not just in aggregate — protects against one outsized month carrying the whole result.
- Max drawdown and recovery factor within a range **declared before the run, not after**.
- Direct evidence the allocator produces something closer to a capital-weighted blend of standalone edges than to winner-take-all-by-occupancy — testable against the exact methodology `profitability_root_cause_investigation.md` Section 5 already used.
- The untouched final HELD_OUT period (Section 11) reviewed **exactly once**, confirming the validation-stage conclusion — no second look, no post-hoc adjustment.
- No result may depend on excluding a "bad month" from the sample.

## 10. Required months / symbols / trades / regimes at each stage

| Stage | Trades | Periods | Symbols | Regimes |
|---|---|---|---|---|
| Individual setup certification | ≥30 | ≥2 independent, not used for rule design | BTCUSDT only | at least the regime(s) the setup's own thesis targets |
| Portfolio certification (pre-paper-trading) | sufficient for the above per setup, combined | ≥3-6 months | BTCUSDT only — multi-asset is a later gate, matching this project's own Breaker Block precedent of single-asset-first | at least 1 trending + 1 ranging period represented |
| Before real capital (out of this roadmap's current scope) | not addressed here | — | multi-asset cross-check | — |

## 11. TRAIN / VALIDATION / HELD_OUT going forward

- **TRAIN:** 2024-01 and 2025-03 — reclassified honestly as contaminated-for-certification but legitimate for hypothesis formation and threshold decisions, exactly as `profitability_root_cause_investigation.md` Section 10 already proposed. Not wasted, just demoted.
- **VALIDATION:** 2-3 freshly-drawn, not-yet-inspected months, selected by the same documented-random method already used for the 2025-03 draw, used for setup selection/comparison during Sprints 3-6 below. May be inspected repeatedly during development — that is what validation is for.
- **HELD_OUT:** exactly one genuinely untouched period, reserved now (as a *name*, not a result — drawing which month it is does not inspect its performance), sealed until one single final confirmation run at the portfolio-certification gate (Section 9). Recommend reserving this in Sprint 1 below, via the same random-draw discipline, from months not yet touched by any decision in this project.

## 12. What can proceed in parallel vs. what is strictly dependent

**Parallel-safe:**
- The O(n²) fix and the MAE/MFE module (independent code paths, both additive, neither reads the other).
- Drafting S008/S011's setup code and unit tests (writing the classes does not require the performance fix or MAE/MFE to exist) — though *validating/backtesting* them should wait for both, so they are diagnosed with full tooling from day one rather than needing a second pass.
- Reserving the final HELD_OUT period (a naming/documentation action) can happen any time, independent of everything else.

**Strictly dependent:**
- Fresh-period validation of S001/S005/S007 → needs a reserved VALIDATION period (Section 11) to exist, and benefits materially from both the perf fix and MAE/MFE being done first (not a hard correctness dependency, but doing it before either exists means redoing the diagnostic pass later).
- Portfolio Risk Manager → needs ≥2 individually-qualified setups (Section 8), which needs fresh validation results.
- Paper trading discussion → needs the Section 9 bar cleared, which needs the Portfolio Risk Manager.
- S005 redesign (if ever pursued) → needs a proven confirmation-gate methodology (S001's own precedent) and fresh (not contaminated) confirmation that S005 is still bad.

## 13. What should explicitly not be worked on yet

- Portfolio Risk Manager / multi-position capability (Section 7).
- S005 full redesign (Section 4) — quarantine only, for now.
- S010 (Section 6).
- Multi-asset/multi-symbol validation (Section 10) — single-symbol certification comes first.
- Live trading, paper-trading infrastructure, Binance integration — nowhere near ready.
- Walk-Forward/Monte Carlo/Bootstrap tooling — already flagged in report 1 as premature given current sample sizes; revisit once the portfolio has enough independent trades for these techniques to say anything.
- Experiment Registry with config hashing, Drift/Live-vs-Backtest monitoring — no live path exists yet to monitor.
- Any threshold tuning against 2024-01 or 2025-03.

## 14. Smallest next sprint maximizing information, minimizing overfitting/waste

**The O(n²) fix, immediately followed by the MAE/MFE module** — see the full Sprint 1/2 specification below. Both are pure research-reliability work: zero strategy logic touched, zero threshold decisions made, fully reusable regardless of which setups eventually get built, and both directly unblock the fresh-validation sprint that follows. This is the smallest unit of work that improves the *reliability of every future measurement* without making any claim about profitability at all.

---

## Path comparison

| | Path A (diagnostics → fresh validation → new setups → PRM) | Path B (perf → diagnostics → new setups → portfolio) | Path C (S008 immediately → validate → infra later) | Path D (PRM first → then evaluate) |
|---|---|---|---|---|
| Expected information value | High | High | Low-moderate (no tooling to interpret results well) | Low (built before knowing what it needs to allocate) |
| Probability of improving the system | Moderate (addresses real, measured root causes) | Moderate (same, better sequenced) | Low (adds a setup into an already-diagnosed crowding trap) | Low (solves a problem before confirming it's still the right problem) |
| Engineering effort | Moderate, well-spread | Moderate, well-spread | Moderate concentrated in one setup, wasted if fresh data disagrees | High, concentrated, high risk of rework |
| Dependency risk | Low — each phase's inputs exist before it starts | Low, same | High — skips the crowding fix entirely, so any multi-setup test still misleads | High — depends on an unknown future setup roster |
| Overfitting risk | Low | Low | Moderate (no MAE/MFE to sanity-check new trades) | Low direct overfitting risk, but high design-mismatch risk |
| Risk of misleading results | Low | Low | **High** — S008 combined with S005 still active would immediately reproduce Section 5's crowding artifact | Moderate — a portfolio tool tested against an unvalidated setup roster proves little |
| Later work makes this obsolete? | No | No | Possibly — S008's own validation may need redoing once diagnostics exist | **Likely** — PRM design may need reworking once S008/S011's real shape is known |

**Selected path: a refined Path A** — functionally Path B's ordering (performance fix first) merged with Path A's explicit phases, with one addition neither literal path stated outright: **fresh validation of the three existing setups is its own explicit phase, before any new setup is built**, not skipped or folded into "new setups." Path C and D are rejected outright: C reintroduces the exact crowding artifact this investigation just spent significant effort diagnosing, and D risks building the highest-effort component of this roadmap against an incomplete picture of what it needs to manage.

---

## Numbered roadmap

### Sprint 1 — Point-in-time performance correction
- **Objective:** eliminate the O(n²) replay bottleneck without changing any backtest result.
- **Deliverables:** cursor-based `ReplayEngine.get_visible_history()`; the same treatment for `PointEventProvider`/`BarSeriesProvider`'s native-mode lookups as a secondary fix; the final HELD_OUT period reserved and documented (a name only, drawn randomly, not inspected).
- **Files/modules likely affected:** `backtesting/replay_engine.py`, `data/market_data_provider.py`; `backtesting/point_in_time.py` untouched (its public function keeps its existing contract for non-cursor callers).
- **Tests/invariants:** new unit tests for the cursor logic (monotonic advancement, duplicates, boundary cases); every existing test still passes.
- **Backtests/analyses to run:** re-run every already-cached configuration from this session and diff trade-for-trade against the cached results; re-run the original multi-month scenario that first exposed the O(n²) behavior and confirm sub-quadratic scaling.
- **Acceptance:** 100% identical results on every re-run; measured, not assumed, complexity improvement.
- **Rejection/stop criteria:** any single trade, metric, or timestamp differs from the pre-change reference — revert and re-diagnose, do not "fix" the discrepancy by adjusting the new code to match if the old code was itself wrong (surface it as a new finding instead).
- **Effort:** Small.
- **Dependency:** none — can start immediately.

### Sprint 2 — MAE/MFE and mark-to-market diagnostics module
- **Objective:** convert this investigation's ad hoc script into a permanent, reusable capability.
- **Deliverables:** an opt-in hook (same additive, byte-identical-when-unused pattern as the `exit_policy` hook already added this session) that reconstructs MAE/MFE and true mark-to-market equity/drawdown from the replay's own candle path; committed unit tests.
- **Files/modules likely affected:** a new module (e.g. `backtesting/trade_analytics.py`), a small additive hook in `backtesting/backtest_runner.py`, `analytics/performance.py` extended (additively) to optionally report mark-to-market drawdown alongside the existing trade-close-based figure — the existing figure must remain available unchanged for comparability with every prior report.
- **Tests/invariants:** unit tests for MAE/MFE computation on synthetic candle paths with known answers; a regression proving existing `PerformanceReport` fields are unchanged when the new hook is unused.
- **Backtests/analyses to run:** re-run S001/S005/S007 on the existing (contaminated-for-certification but fine-for-tooling-validation) 2024-01/2025-03 data to confirm the module reproduces this report's own numbers exactly.
- **Acceptance:** MAE/MFE and mark-to-market drawdown reproduce this report's hand-computed numbers exactly; zero change to any existing metric when unused.
- **Rejection/stop criteria:** any discrepancy against this report's already-published numbers must be explained before proceeding — either this report or the new module has a bug.
- **Effort:** Small-Medium.
- **Dependency:** none (parallel-safe with Sprint 1; sequenced after it here only for single-threaded execution efficiency).

### Sprint 3 — Fresh-period validation of S001, S005 (quarantined), S007
- **Objective:** determine whether the existing setups' measured edges (or lack thereof) replicate on data no decision in this project has ever touched.
- **Deliverables:** standalone and combined backtests of S001/S005/S007 on 2-3 newly-drawn VALIDATION months (Section 11); full metric tables plus MAE/MFE per Sprint 2's tooling; an updated verdict on whether S001's edge looks real, whether S005's pre-fee negativity replicates, and whether S007 finally reaches an interpretable sample size.
- **Files/modules likely affected:** none in `strategy/`/`backtesting/` — this is a research script exercise, no production code change (S005 stays quarantined out of default combined-portfolio wiring per Section 4, a configuration choice already made in Sprint 0/now, not new work here).
- **Tests/invariants:** none new — this sprint consumes Sprint 1/2's already-tested infrastructure.
- **Backtests/analyses to run:** the full standard suite (standalone, pairwise, triple combination) across the newly-drawn months, using Sprint 1's fast replay and Sprint 2's MAE/MFE.
- **Acceptance:** a clear, documented verdict per setup — replicated, contradicted, or still inconclusive — with sample sizes stated plainly.
- **Rejection/stop criteria:** if a setup's win rate flips sign again on fresh data (as already seen between Jan/Mar for both S001 and S005), that setup remains "inconclusive," not certified, regardless of how the aggregate number looks.
- **Effort:** Medium.
- **Dependency:** Sprints 1 and 2 (for efficiency and diagnostic quality), plus a drawn VALIDATION period (Section 11, ideally reserved in Sprint 1).

### Sprint 4 — S008 (Displacement-Impulse Continuation) implementation and standalone validation
- **Objective:** implement the highest-ranked Phase 4 candidate and validate it standalone, informed by Sprint 3's findings on the continuation thesis.
- **Deliverables:** `strategy/setups/displacement_impulse_continuation.py` (S008) per the Phase 4 specification; full unit test suite; Step-0-style architecture verification (expected to pass cleanly, per Phase 4's own audit); standalone signal-frequency check *before* any performance backtest; standalone backtest with MAE/MFE on the same VALIDATION months from Sprint 3.
- **Files/modules likely affected:** new setup file, new test file — no change to `StrategyEngineV2`, `MarketIntelligenceSnapshot`, or any existing setup (confirmed feasible with zero infra change in the Phase 4 audit).
- **Tests/invariants:** unit tests for the impulse-magnitude boundary, mitigation-zone vs. full-zone stop distinction, touch-count gating, determinism, replay safety, zero regression.
- **Backtests/analyses to run:** standalone only in this sprint — do not combine with S001/S005/S007 yet (that risks re-measuring Section 5's crowding artifact before a Portfolio Risk Manager exists to address it).
- **Acceptance:** fires with an interpretable frequency (a real signal-count check, not assumed); MAE/MFE profile reviewed for outlier concentration.
- **Rejection/stop criteria:** if standalone signal frequency is too low to reach the Section 8 trade-count bar within a reasonable number of months, treat as "pending," exactly as S007 already is — do not force a verdict.
- **Effort:** Medium.
- **Dependency:** Sprints 1-3 (infrastructure + a documented view of whether continuation setups are worth this investment).

### Sprint 5 (conditional) — S011 (Value Area Extension Fade) implementation and standalone validation
- **Objective:** fill the completely unaddressed RANGE regime.
- **Deliverables/process:** identical structure to Sprint 4, applied to S011.
- **Effort:** Small-Medium (uses only already-wired fields, per Phase 4's audit).
- **Dependency:** Sprint 4 (sequenced after, not blocked by, per Section 6's ranking) plus Sprints 1-3.

### Sprint 6 (gated) — Portfolio Risk Manager design and implementation
- **Objective:** replace the single global trade slot with an allocator that reflects each setup's own edge rather than raw occupancy.
- **Gate to even start this sprint:** at least 2 of {S001, S008, S011, S009} have individually cleared the Section 8 evidence bar. If fewer than 2 have, this sprint does not start yet — extend Sprints 4/5 (or add S009) instead.
- **Deliverables:** a Portfolio Risk Manager module per report 1's own 10-point module spec; a direct test reproducing `profitability_root_cause_investigation.md` Section 5's crowding measurement to confirm the new allocator actually changes it.
- **Files/modules likely affected:** new module, an integration point between `StrategyEngineV2.decide()` and `BacktestRunner`'s trade-opening step.
- **Tests/invariants:** determinism, replay safety, a standalone-setup-unchanged regression, the crowding-reproduction test above.
- **Backtests/analyses to run:** the qualified setups combined, across the Section 9 evidence window (≥3-6 months, ≥1 trending + ≥1 ranging).
- **Acceptance/rejection:** per Section 9 in full.
- **Effort:** Large.
- **Dependency:** Sprints 3-5 (needs a qualified, known setup roster).

---

## Decision table

| Item | Do now | Do next | Defer | Archive/reject |
|---|---|---|---|---|
| O(n²) replay fix | ✅ | | | |
| MAE/MFE + mark-to-market module | ✅ | | | |
| Reserve final HELD_OUT period (name only) | ✅ | | | |
| Fresh-period validation of S001/S005/S007 | | ✅ | | |
| S005: remove from default combined-portfolio wiring | ✅ | | | |
| S005: full redesign | | | ✅ | |
| S008 implementation | | ✅ | | |
| S011 implementation | | | ✅ (after S008) | |
| S009 implementation | | | ✅ (after S008+S011 results) | |
| S010 implementation | | | | ✅ (not recommended for now) |
| Portfolio Risk Manager | | | ✅ (gated on ≥2 qualified setups) | |
| Multi-asset/multi-symbol validation | | | ✅ (after single-symbol certification) | |
| Walk-Forward / Monte Carlo / Bootstrap tooling | | | ✅ (after sample sizes justify it) | |
| Experiment Registry / Drift monitoring | | | | ✅ (no live path exists yet) |
| Paper trading infrastructure | | | | ✅ (far too early) |
| Threshold tuning on 2024-01/2025-03 | | | | ✅ (never) |

---

## Explicit caveats preserved

No threshold in this roadmap is to be tuned against 2024-01 or 2025-03. The final HELD_OUT period is not to be opened until every design decision in Sprints 1-6 is frozen. Every infrastructure change (Sprints 1-2) must be proven trade-for-trade and metric-for-metric identical to its pre-change reference before being trusted. Nothing in this roadmap assumes more setups or concurrent positions automatically improve profitability — Sprint 6 is explicitly gated on evidence, not scheduled by default. Profitability is not presented as guaranteed at any stage. Sprints 1-2 improve research reliability only and create no trading edge of any kind; Sprints 3-5 investigate possible edge; Sprint 6 is architecture that can only ever protect an edge that already exists, never manufacture one.

---

## Final recommendation

**Next approved sprint: Point-in-time performance correction (Sprint 1), followed immediately by the MAE/MFE and mark-to-market diagnostics module (Sprint 2). Reason:** both are pure research-reliability work with zero strategy or threshold changes and already-identified, low-risk implementations; fixing the confirmed O(n²) bottleneck first means every subsequent sprint in this roadmap — fresh validation, S008/S011 implementation, and eventually the Portfolio Risk Manager's own evidence-gathering — runs at the speed this investigation needed and didn't fully have, while the diagnostics module converts a capability this report had to hand-build once into something every future setup gets for free. Neither sprint touches S001, S005, or S007's actual behavior, so neither carries any overfitting risk, and both are prerequisites — directly or by efficiency — for every higher-value, higher-risk decision (S005's fate, S008's priority, the Portfolio Risk Manager's design) that follows.

**Stopping here. Awaiting explicit approval before implementing Sprint 1.**
