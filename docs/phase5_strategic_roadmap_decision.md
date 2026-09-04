# Strategic Roadmap Decision (Revision 2)
## Lead Quantitative Systems Architect Recommendation

**Status: decision memo and data-readiness inspection only. Nothing implemented, no data downloaded, no threshold selected, no strategy-performance backtest run.** This revision supersedes Revision 1 in full — two new requirements (multi-factor setup/exit research methodology, and a pivot to SOLUSDT as the primary instrument) are integrated into one unified roadmap, with the conflict between them resolved explicitly in Section 0.

---

## 0. Resolving the conflict between the two new requirements

There is no fundamental conflict, but the sequencing matters. "Design a multi-factor setup with an ablation study" and "SOLUSDT is now primary, BTC results don't transfer" both bear on **S008**, the next setup in line. Resolution: **S008 is redesigned as a genuine multi-factor candidate (Section 3) and evaluated primarily on SOLUSDT data (Section 1), using the same ablation methodology regardless of instrument.** Nothing about the multi-factor research design depends on which symbol it runs on; nothing about the SOL pivot changes how many components a setup should have. The one place they interact concretely: **S008's originally-proposed trigger threshold (`impulse_strength >= 1.0`) is ATR-normalized, not an absolute price level — it was already built to be scale-invariant in the Phase 4 design, before the SOL pivot was requested, and needs no rework for that reason alone.** Not everything transfers this cleanly — Section 1 identifies exactly what does not.

---

## 1. SOLUSDT data-readiness inspection (performed now, read-only)

### 1.1 Files present, coverage, gaps

All 24 monthly files exist: `SOLUSDT-1m-2024-01.csv` through `SOLUSDT-1m-2025-12.csv`, continuous, no missing months. This was already validated at the raw-file level in `docs/research_dataset_validation_report.md` (built for a four-asset, two-year dataset including SOLUSDT): 0 files with a wrong row count, 0 internal timestamp gaps, 0 duplicate timestamps, correct month boundaries, across all four symbols — SOLUSDT included, not a BTC-only check. **Re-verified directly for this report**, not merely cited: `load_ohlcv_csv` was run against `SOLUSDT-1m-2024-01.csv` just now — 44,640 rows, first/last timestamps exactly at the month boundary, loads through the same hardened `normalize_ohlcv_records` pipeline (duplicate-timestamp and OHLC-consistency checks) with zero errors.

### 1.2 `taker_buy_volume` (real order flow data)

**Confirmed genuine, not synthetic**, by direct inspection of the raw CSV header and values (`SOLUSDT-1m-2024-01.csv`: `taker_buy_volume` present and populated on every row checked) and by loading through `load_ohlcv_csv`, which confirmed **zero `None` values** for `taker_buy_volume` across the full January 2024 file. Delta/CVD are as reliable for SOL as they were already confirmed to be for BTC.

### 1.3 Timestamp/OHLCV/aggregation integrity

Passes today's actual integrity code, not just inspection: `load_ohlcv_csv` → `normalize_ohlcv_records` (duplicate-timestamp rejection, `high < low` rejection, all already-hardened from the earlier Repository Integrity Sprint) succeeded with no exceptions. `TimeframeManager`/`WindowManager`/`ReplayEngine`/`BacktestRunner` compatibility for SOLUSDT specifically was already exercised end-to-end (all four symbols, full 2024 year) in the dataset validation report — no SOL-specific incompatibility found there or here.

### 1.4 Regime coverage — computed directly from price, not from any strategy backtest

Every SOL month's open/close change %, high/low range %, and daily-close realized volatility was computed directly from raw OHLC (no setup, no signal, no trade was involved in producing this table):

| Month | Chg% | Range% | Daily vol% | Month | Chg% | Range% | Daily vol% |
|---|---:|---:|---:|---|---:|---:|---:|
| 2024-01 | -4.8 | 48.3 | 4.85 | 2025-01 | +22.4 | 76.3 | 5.10 |
| 2024-02 | **+29.8** | 44.8 | 3.34 | 2025-02 | **-36.1** | 86.4 | 4.26 |
| 2024-03 | +61.1 | 102.4 | 5.08 | 2025-03 | -15.9 | 61.0 | **7.26** |
| 2024-04 | **-37.5** | 81.3 | 4.62 | 2025-04 | +18.5 | 65.2 | 4.92 |
| 2024-05 | +30.8 | 59.8 | 4.12 | 2025-05 | +6.0 | 32.8 | 3.54 |
| 2024-06 | -11.6 | 44.8 | 3.58 | 2025-06 | -1.0 | 33.8 | 3.56 |
| 2024-07 | +17.1 | 61.5 | 4.50 | 2025-07 | +11.3 | 42.7 | 3.29 |
| 2024-08 | -21.2 | 58.4 | 4.80 | 2025-08 | +16.5 | 40.0 | 4.67 |
| 2024-09 | **+12.7** | **34.3** | 3.26 | 2025-09 | +4.0 | 32.9 | 3.46 |
| 2024-10 | +10.6 | 37.8 | **3.13** | 2025-10 | -10.3 | 68.3 | 4.89 |
| 2024-11 | +41.0 | 70.7 | 4.39 | 2025-11 | -28.7 | 56.3 | 4.19 |
| 2024-12 | -20.4 | 41.2 | 3.85 | 2025-12 | -6.6 | **25.8** | **3.11** |

**Conclusion: the SOL dataset genuinely covers strong uptrends (Feb/Mar/Nov 2024, Jan 2025), strong downtrends (Apr 2024, Feb/Nov 2025), low-range/directionless periods (Sep 2024, May/Jun/Sep/Dec 2025), a clear high-volatility outlier (Mar 2025 at 7.26% daily vol, the single most volatile month in the dataset), and low-volatility periods (Oct 2024, Dec 2025) — every regime category the user asked for is genuinely represented**, not asserted without evidence.

### 1.5 Confirmed BTC-specific hidden thresholds — the most important finding in this section

Two absolute-price-scale defaults in `MarketIntelligenceCoordinator.__init__` are hardcoded for BTC's price level and **will not transfer to SOL without a decision**, confirmed by direct comparison against SOL's actual price range:

- **`round_number_spacing: float = 500.0`** — SOL's entire monthly range is frequently *smaller than one spacing unit* (e.g., January 2024: high 116.87, low 78.96, a $38 range against a $500 spacing). At this setting, the round-number liquidity sub-detector would **never fire for SOL**, silently disabling one of three Liquidity Pool sources without anyone deciding to.
- **`volume_profile_bucket_size: float = 50.0`** — against SOL's typical monthly range of $30-150, a $50 bucket would collapse the entire Volume Profile histogram into 1-3 buckets total, destroying POC/VAH/VAL/HVN/LVN resolution — this breaks S003, S011, and the Volume-Profile-based optional evidence already used by S005/S007.

**Fields confirmed already scale-invariant, needing no change:** `DEFAULT_TOLERANCE_ATR_MULTIPLIER` (Liquidity Pool clustering, ATR-relative), `MIN_RISK_PERCENT`/`STOP_BUFFER_PCT`/`REWARD_MULTIPLE` (all percentage-of-price, not absolute), Order Block's `impulse_strength` (ATR-at-creation-normalized — this is exactly why S008's originally-proposed trigger needs no rework, per Section 0).

**This is not a threshold decision made here.** No new number is chosen in this report. The finding is scoped precisely: these two defaults must be revisited *before* any SOL setup research reads Liquidity Pool round-number sources or Volume Profile at all, via the same non-fitted, unit-based discipline already used throughout this project (e.g., a spacing/bucket size derived from SOL's own tick size or a fixed small-integer dollar amount, not chosen by looking at backtest results) — flagged as a required Sprint 1 sub-task (Section 6), not decided now.

### 1.6 Fees, slippage, and position sizing under SOL volatility

- **Fees:** Binance USD-M futures fee schedules are uniform per account tier across symbols on the same product line — the existing `fee_rate=0.0004` is not BTC-specific and needs no SOL-specific change.
- **Slippage:** the existing fixed `slippage_rate=0.0002` was never validated against either BTC's or SOL's actual order-book depth — it is a modeling assumption, not a measured one. SOL futures typically carries materially less depth than BTC futures, meaning **real slippage for a given notional size is plausibly higher for SOL** — this is an **open question requiring a stress test** (a range of slippage assumptions re-run against frozen setup logic, per Section 8), not a number to guess now.
- **Position sizing / the 0.6% `MIN_RISK_PERCENT` floor:** this is a *percentage* of price, so it scales correctly across instruments arithmetically — but whether 0.6% is an appropriate *minimum stop distance relative to SOL's own noise level* is unverified. SOL's realized daily volatility (3.1-7.3% across the table above) runs meaningfully higher than BTC's typical 1-3% in this project's own prior data — this raises a real, open possibility that a 0.6% floor is tighter, relative to SOL's actual noise, than it was for BTC. **This must be measured via fresh SOL MAE data (Section 6, Sprint 3), not assumed either way.**

---

## 2. Revised primary-instrument decision

**SOLUSDT becomes the primary research, development, validation, and eventual paper-trading instrument, effective immediately. BTCUSDT is retained exclusively as a later, frozen-logic, cross-asset robustness check — never used again for threshold selection or setup design decisions from this point forward.** Every BTCUSDT result already produced in this project (S001/S005/S007 status, the Exit Management Sprint's structure-trail rejection, the profitability root-cause investigation) is downgraded to **architecture and methodology evidence only** — proof the infrastructure works and proof of *how* to investigate, never a claim about SOL's own numbers. No performance figure already computed for BTC may be cited as if it applies to SOL.

---

## 3. Multi-factor setup architecture — recommendation

### 3.1 Recommended entry architecture

Evaluating the seven candidate components against this project's own founding architectural principle — `strategy/setups/base.py`'s explicit rejection of "a hand-weighted sum of sub-scores... no arbitrary numeric weights anywhere," the reason the old Decision Engine was replaced — the recommended default structure is:

1. **One primary event trigger** (required, non-negotiable) — defines the institutional event being traded. Every existing setup already has exactly this.
2. **One regime/context gate** (required) — genuinely new: no existing setup uses `market_structure` as a firing condition today, confirmed in the prior root-cause investigation. This directly targets an already-identified gap, not a speculative addition.
3. **Several independent confirmations, gated by a minimum-count rule by default** — not a weighted score by default. This matches the architecture's own stated principle and this project's own precedent (S001's "≥1 of 3" gate, earned through controlled experimentation, not assumed). A **calibrated** (not arbitrary) weighted score is evaluated only as a *later*, explicitly-justified research question (Section 3.3) — never the starting design.
4. **A veto condition for clearly unfavorable environments** — evaluated as its own ablation arm, not assumed necessary. If a regime gate (item 2) already excludes the clearly unfavorable case, a separate veto may prove redundant — this is exactly the kind of redundancy the required ablation study must detect, not assume away in either direction.
5. **A separate risk/exit policy** — already architecturally available via the `exit_policy` hook built this session; exit research proceeds independently per Section 4, entries frozen first.

### 3.2 Which modules contribute to the first new setup (S008)

S008's original Phase 4 design (Order Block `impulse_strength >= 1.0` as the primary trigger, entry into the `mitigation_zone`) is retained as the primary trigger — it is already ATR-normalized and needed no SOL-specific rework (Section 0). Expanded to a genuine multi-factor candidate for the required ablation study, drawing each confirmation from a **different** Market Intelligence family to maximize the chance of real independent information, per instruction 2:

- **Primary trigger (required):** Order Block with `impulse_strength >= 1.0`, first touch of its `mitigation_zone`.
- **Regime gate (required):** `structure.market_structure` compatible with the trigger's direction (not `RANGE`, not the opposing trend).
- **Confirmation candidates (evaluated independently, not assumed mandatory):**
  - CVD/Delta agreement (Order Flow family).
  - Value Area position — mitigation zone overlaps the current Value Area (Volume Profile family).
  - Liquidity Pool confluence — an active, unswept pool overlaps the mitigation zone (Liquidity family, structurally distinct from Zones).
  - Session context — the retest occurs during an active named session/kill-zone (Sessions family, unused by every existing setup to date).

### 3.3 Mandatory, scored, or veto?

**Mandatory: only the primary trigger and the regime gate.** **Scored: no, not by default** — a minimum-confirmation-count rule is the starting hypothesis, consistent with this project's own architecture and with instruction 8 ("prefer simple combinations when performance is statistically indistinguishable from more complex ones"). A calibrated score is promoted to an active research question **only if** the ablation study (Section 3.4) shows the four confirmations have clearly *unequal* individual contribution — in which case an equal-weight minimum-count rule is provably leaving information on the table, and a calibrated (never hand-picked) weighting becomes worth testing, itself validated for overfitting by confirming any learned weights transfer from TRAIN to VALIDATION. **Veto: evaluated, not assumed** — tested as its own ablation arm against the regime gate's own explanatory power, since the two may be redundant.

### 3.4 Ablation methodology (resolving instructions 4-10 concretely)

**Method, chosen specifically to avoid a pitfall this project already discovered:** the Exit Management Sprint found that changing exit timing changes *which entries even get evaluated* (the one-trade-at-a-time slot reopens at a different time), confounding naive "run N separate backtest variants" comparisons. The same risk applies to *gating* conditions (the regime gate, the minimum-count rule) but **not** to *non-gating* confirmations recorded as evidence on every trigger-fire regardless of outcome — the existing `SetupResult.additional_evidence` schema already records each confirmation's `satisfied`/not status per trade, independent of whether it gates firing. This makes an efficient, sounder ablation possible:

- **Confirmations (non-gating):** run the primary-trigger-only setup **once**, with all four confirmations recorded as evidence but none gating. Post-hoc, slice the *same* realized trade set by which confirmations were present, and measure the outcome distribution per subset — a single backtest pass, no slot-occupancy confound, directly measuring items 4 and 5 (redundant/correlated confirmations show up as subsets with near-identical outcome distributions).
- **The regime gate and any minimum-count rule (gating):** these genuinely change which bars open a trade, so they require actual separate runs: trigger alone; trigger + regime gate; trigger + regime gate + minimum-count-of-N, for the small number of N worth testing (not a swept search) — exactly the "trigger alone / trigger + each confirmation / trigger + selected combinations / full setup" structure instruction 5 asks for, with the non-gating half of it done in one pass and the gating half done as a small, pre-declared handful of runs, not sixteen.

**Controlling multiple-hypothesis testing and selection bias (instruction 10):** the primary hypothesis (which single confirmation is expected to matter most) is stated **before** looking at SOL VALIDATION results — CVD agreement, on the reasoning that order-flow confirmation already has the strongest existing precedent in this project (S001's own required condition). Any other confirmation found to "work" after the fact is treated as exploratory, requiring independent confirmation on a *second* VALIDATION period before being taken seriously, not accepted from the same look that generated the hypothesis. **Reject components that only look good on a shrunken sample** (instruction 7): any subset with fewer than the Section 7 minimum trade count is reported as inconclusive, never as a positive result, regardless of its apparent profit factor.

---

## 4. Exit-management research plan

**The prior rejection is scoped precisely, not generalized:** `StructureBasedTrailExitPolicy` — a specific rule (+1R activation, structure-based trailing, nearest-beyond-TP advancement) — was rejected on BTC data. It says nothing about a fixed-percent-of-target protection rule, partial profit-taking, volatility-aware management, time-based exits, a differently-activated structure trail, or a limited continuation-trailing TP. All are treated as genuinely open questions.

### 4.1 Pre-declared exit policies to evaluate (documented before any test)

1. **Fixed control** (already exists — the comparison baseline).
2. **Near-target protection** — move the stop to protect a fixed fraction of unrealized profit only after price reaches a high, pre-declared percentage of the 2R target (e.g., 80% — a round, pre-declared number, not fit).
3. **Partial profit-taking** — close a pre-declared fraction of the position at 1R, let the remainder run to the original 2R.
4. **Volatility-aware stop/target** — requires ATR wired into the snapshot (currently not — Section 6 dependency), sized in ATR units, not a percentage.
5. **Time-based exit** — close a trade that has not reached some minimal favorable excursion within a pre-declared number of bars.
6. **Structure trailing, differently activated** — trail only after a *new, confirmed* structural event forms in the trade's favor post-entry (e.g., a fresh swing pivot), not a flat R-multiple threshold — a genuinely distinct hypothesis from the rejected policy, not a re-run of it.
7. **Limited continuation trailing TP** — for trades already exceeding a pre-declared R-multiple (e.g., 2.5R), allow the target to trail loosely to capture the "continues substantially beyond 2R" population.

**BTC's own MAE/MFE data (from the root-cause investigation) motivates which hypotheses are worth testing at all, without being trusted as SOL's answer:** 10-19% of BTC trades reached ≥1R then reversed to a loss (motivates #2/#3), median MAE clustered near 1.0R (cautions against assuming stops are simply "too tight" — a volatility-aware *widening* is not obviously justified without SOL-specific evidence), and MFE reached as high as 2.8R in some trades (motivates #7). **Every one of these must be re-measured on SOL before any conclusion is drawn** — this is stated as motivation for *which hypotheses to bother testing*, not as evidence about SOL.

### 4.2 Staged testing protocol (adopted directly from the instructions, matching how the Exit Management Sprint was already correctly run)

1. Establish S001/S005/S007/S008's fixed-exit expectancy on SOL TRAIN/VALIDATION data first — entries frozen, no exit research yet.
2. Test each pre-declared exit policy on the **exact same entries** — this is precisely the discipline the original Exit Management Sprint already used (same-entries-different-exits), now applied on SOL and to a wider, pre-declared policy set.
3. Attribute any improvement specifically to the exit change (report which fraction of any performance delta is attributable to fewer full-stop losses vs. cut winners vs. captured continuation, exactly as the original sprint's own report format already did).
4. Test the final frozen entry+exit combination on the untouched SOL HELD_OUT period exactly once, only after both are frozen — never before.

### 4.3 Evidence that would justify adopting a dynamic exit

Profit factor and net profit **improve or hold flat with a clear drawdown improvement**, in the **same direction across at least two independent SOL VALIDATION periods**, surviving a sensitivity check across the nearby activation parameters (e.g., 75%/80%/85% for the near-target-protection rule) rather than one lucky number, and net of fees and adverse (worse-than-base-case) slippage.

### 4.4 Evidence that would cause rejection

Any of: the policy depends on a single outlier trade to look good; it fails to replicate sign across two VALIDATION periods; a nearby activation parameter (not the chosen one) performs materially worse, indicating a fragile, unstable threshold rather than a real effect; or — the exact mechanism already found once — it sacrifices more and larger winners than the full losses it avoids, in aggregate.

---

## 5. What changes because SOL is now primary

| Question | Answer |
|---|---|
| Recommended setup order | **Unchanged** (S008 → S011 → S009, S010 deferred) — the ranking logic (data availability, complexity, redundancy) was never BTC-specific. |
| Minimum required trade count | **Unchanged in principle** (≥30 trades, ≥2 independent periods) but treated as *more* uncertain until SOL's own signal frequency is measured — SOL's higher realized volatility (Section 1.4) could plausibly change how often a given structural event occurs; this is measured in Sprint 3, not assumed either direction. |
| Stop/target research priorities | **Elevated** — the 0.6% floor's appropriateness for SOL's noise level (Section 1.6) is now an open, flagged question rather than an inherited assumption. |
| Dynamic exit hypotheses | **Unchanged set** (Section 4.1) — none of the seven candidate policies were BTC-specific in their construction; only their evidentiary support must be re-established on SOL. |
| Portfolio concurrency/exposure limits | **Unchanged in design, re-evaluated in evidence** — the crowding mechanism identified against BTC (S005 dominating occupancy) is an architectural fact about the one-trade-at-a-time engine, not a BTC-specific behavior; still expected to reproduce on SOL, but reported as an expectation to confirm, not assumed. |
| Required slippage stress tests | **New requirement, added** (Section 1.6) — SOL's plausibly thinner order-book depth is a real, previously-unexamined question; a slippage-sensitivity re-run (frozen setup logic, varied slippage assumption) is now an explicit Sprint 7 task. |
| S005 quarantine decision | **Unchanged, and now applies identically to SOL** — S005's own re-fire characteristic (no confirmation gate, no magnitude filter) is a property of its rule logic, not of BTC's price behavior; it is expected to still overtrade on SOL, but this is now something Sprint 3 measures directly rather than assumes carried over from the BTC-only finding. |

---

## 6. SOL research partition — proposed, pending your approval, not yet used for any backtest

Selected using **only** the price-derived table in Section 1.4 — trend direction and realized volatility computed from raw OHLC, with zero strategy or setup ever evaluated against them. 2024-01 and 2025-03 are deliberately excluded from all three partitions below, even though neither has been inspected for SOL specifically — a conservative choice to keep this project's "these two calendar windows are retired" discipline unambiguous across every symbol, not a strict logical necessity.

- **TRAIN (hypothesis formation, freely re-inspected during design):** 2024-02 (strong bull, +29.8%), 2024-04 (strong bear, -37.5%), 2024-09 (range/low-directional, +12.7%, tightest range of 2024), 2025-12 (range, lowest realized volatility in the dataset).
- **VALIDATION (setup/model selection, inspected during comparison, not tuned beyond recognition):** 2024-11 (strong bull, +41.0%), 2024-08 (strong bear, -21.2%), 2024-10 (low-vol, directionless-leaning), 2025-05 (range, low-vol).
- **FINAL HELD_OUT (opened exactly once, only after every design decision above is frozen):** 2025-02 (strong bear, -36.1%, widest range in the dataset) and 2025-07 (moderate bull, range-bound character) — chosen for regime diversity, not performance, and not inspected as part of producing this report.
- **Reserved, unassigned:** every other SOL month (2024-01/03/05/06/07/12; 2025-01/03/04/06/08/09/10/11) — available for a later VALIDATION redraw or eventual multi-month portfolio certification, not designated yet.

**This partition is a proposal.** It is documented before any setup touches it, per instruction, and awaits your explicit confirmation before Sprint 3 uses it.

---

## 7. Everything from Revision 1 that still holds, restated briefly

Sections 7-11 of Revision 1 (minimum evidence for portfolio integration, minimum evidence for paper trading, parallel-vs-dependent work, what not to work on yet, the path comparison) are **unchanged in substance** and carry forward — only the instrument (SOL, not BTC) and the setup design methodology (multi-factor, ablation-tested, per Section 3) change. In particular: the Portfolio Risk Manager remains gated on ≥2 individually-qualified setups; S005 remains quarantined, not archived, not redesigned yet; S010 remains deferred; multi-asset validation, live infrastructure, and Monte Carlo/walk-forward tooling remain explicitly not-yet.

---

## 8. Revised roadmap (supersedes Revision 1's sprint list)

### Sprint 1 — Point-in-time performance correction + symbol-agnostic infrastructure confirmation
- **Objective:** eliminate the confirmed O(n²) replay bottleneck; confirm (not newly build) that the fix and all touched infrastructure are symbol-agnostic.
- **Deliverables:** cursor-based `ReplayEngine.get_visible_history()`; the same treatment for `PointEventProvider`/`BarSeriesProvider` native-mode lookups; a documented decision on `round_number_spacing`/`volume_profile_bucket_size` for SOL (the decision itself, not a fitted value — e.g., disable the round-number sub-detector for SOL pending a principled, non-fitted spacing, and pick a SOL-appropriate bucket size derived from tick size or a fixed small round number, never from backtest performance); the final SOL HELD_OUT reservation confirmed as untouched.
- **Files/modules likely affected:** `backtesting/replay_engine.py`, `data/market_data_provider.py`, `strategy/market_intelligence_coordinator.py` (default values only, no logic change).
- **Tests/invariants:** cursor-logic unit tests; full existing suite (already symbol-agnostic by construction — no test hardcodes BTC prices as a correctness assumption, confirmed by design) must still pass unchanged; a new smoke test confirming the coordinator's defaults are surfaced as configurable (not hardcoded assumptions) for a second symbol.
- **Backtests/analyses to run:** re-run every already-cached BTC configuration from this session and diff trade-for-trade against the cached results (this remains the correctness reference, even though BTC is no longer the research target); no SOL strategy backtest yet.
- **Acceptance:** 100% identical BTC results pre/post change; SOL data loads and replays through the corrected engine with zero errors (a plumbing check, not a performance claim).
- **Rejection/stop criteria:** any BTC trade/metric differs from the pre-change reference.
- **Effort:** Small-Medium (slightly larger than Revision 1's estimate, to include the coordinator-defaults decision).
- **Dependency:** none — can start immediately. **Can proceed unchanged from Revision 1's approval, with the coordinator-defaults sub-task added.**

### Sprint 2 — MAE/MFE and mark-to-market diagnostics (symbol-agnostic)
- **Objective:** unchanged from Revision 1 — build the permanent diagnostics hook.
- **Deliverables/tests/acceptance:** unchanged from Revision 1, with one addition: validate the module against **both** a BTC re-run (matching the root-cause investigation's hand-computed numbers exactly, the correctness reference) **and** a SOL smoke run (confirming no symbol-specific assumption leaked into the implementation — e.g., no hardcoded price-scale constant).
- **Effort:** Small-Medium. **Dependency:** none (parallel-safe with Sprint 1).

### Sprint 3 — Fresh SOL baseline for S001, S005, S007
- **Objective:** establish a completely new SOLUSDT baseline for every existing setup — explicitly not assumed to inherit BTC's numbers.
- **Deliverables:** standalone and combined backtests of S001/S005/S007 on the SOL TRAIN and VALIDATION periods (Section 6); full metric tables plus MAE/MFE (Sprint 2's tooling); explicit measurement of (a) SOL signal frequency for all three setups, (b) whether the 0.6% stop floor behaves appropriately against SOL's own MAE distribution, (c) whether S005 still overtrades and still shows a negative pre-fee edge on SOL, (d) whether S001's edge is regime-dependent on SOL the way it was hypothesized to be on BTC.
- **Files/modules affected:** none in `strategy/`/`backtesting/` — research scripts only.
- **Backtests to run:** standalone + pairwise + triple combination, across all 8 TRAIN+VALIDATION SOL months.
- **Acceptance:** a documented, evidence-based verdict per setup on SOL — replicated-BTC-pattern, contradicted, or newly-inconclusive — stated plainly with sample sizes.
- **Rejection/stop criteria:** any setup whose SOL win rate flips sign between TRAIN and VALIDATION periods remains "inconclusive," exactly as the BTC Jan/Mar sign-flip was already treated.
- **Effort:** Medium-Large (more months than the original BTC-only Sprint 3).
- **Dependency:** Sprints 1-2, plus your approval of the Section 6 partition.

### Sprint 4 — S008 (multi-factor Displacement-Impulse Continuation) design finalization + ablation-ready implementation
- **Objective:** implement S008 per Section 3's expanded, ablation-ready design, primarily evaluated on SOL.
- **Deliverables:** `strategy/setups/displacement_impulse_continuation.py` with the primary trigger, regime gate, and four confirmations recorded as non-gating evidence (per Section 3.4's methodology); full unit test suite including confirmation-independence tests; the single-pass confirmation ablation on SOL VALIDATION data; the small, pre-declared set of gating-combination runs (trigger alone / +regime gate / +minimum-count-of-N).
- **Files/modules affected:** new setup file, new test file — zero change to `StrategyEngineV2`/`MarketIntelligenceSnapshot` (confirmed feasible in the original Phase 4 audit).
- **Tests/invariants:** determinism, replay safety, zero regression, plus the ablation-specific tests above.
- **Acceptance:** a stated verdict on which confirmations (if any) survive the redundancy/correlation check (instructions 3-4) and whether a minimum-count rule outperforms the trigger+gate alone by more than sampling noise, reported honestly if inconclusive.
- **Rejection/stop criteria:** per Section 8's individual-setup evidence bar (Revision 1, carried forward) — any subset below the minimum trade count is reported inconclusive, not positive.
- **Effort:** Large (expanded scope vs. Revision 1's single-trigger S008).
- **Dependency:** Sprints 1-3.

### Sprint 5 — Exit-management research on frozen S001/S005(quarantine-control)/S007/S008 entries
- **Objective:** execute Section 4's staged protocol on SOL data, entries frozen from Sprints 3-4.
- **Deliverables:** the seven pre-declared exit policies (Section 4.1) tested against identical entries; the full required per-policy report (net profit/expectancy, PF, win rate, avg winner/loser, MAE/MFE, mark-to-market drawdown, % full-target winners sacrificed, losses avoided, gains captured beyond 2R, activation-parameter sensitivity, post-cost results); a volatility-aware policy variant only if the small ATR-wiring task (a prerequisite noted in Section 4.1) is completed first.
- **Files/modules affected:** new policy implementations under the existing `ExitPolicy` protocol (research-only/scratchpad for the exploratory ones, matching this project's established precedent, promoted to committed code only for a policy that survives Section 4.3's bar).
- **Acceptance/rejection:** exactly Section 4.3/4.4.
- **Effort:** Large.
- **Dependency:** Sprint 4 (frozen entries required first, per the staged protocol itself).

### Sprint 6 (conditional) — S011, then S009
- **Objective/structure:** unchanged from Revision 1, evaluated on SOL, gated on Sprint 4's evidence.
- **Effort:** Small-Medium (S011) / Medium (S009). **Dependency:** Sprint 4.

### Sprint 7 — SOL-specific stress tests
- **Objective:** answer the slippage-realism and position-sizing questions raised in Section 1.6.
- **Deliverables:** a sensitivity re-run of every qualified setup under a range of slippage assumptions (frozen setup logic, no threshold change), and a direct comparison of SOL vs. BTC MAE distributions to check whether the 0.6% floor needs revisiting (a finding to report, not a number to pick here).
- **Effort:** Small-Medium. **Dependency:** Sprints 3-6 (needs qualified setups to stress-test).

### Sprint 8 (gated) — Portfolio Risk Manager
- **Objective/gate/deliverables:** unchanged from Revision 1, evaluated on SOL, gated on ≥2 SOL-qualified setups from Sprints 4-6.
- **Effort:** Large. **Dependency:** Sprints 3-7.

### Sprint 9 (final, once-only) — Frozen-logic BTC robustness check + SOL HELD_OUT confirmation
- **Objective:** the two "look once" events in this entire roadmap, performed together at the very end: (a) run every frozen, fully-decided setup+exit+portfolio configuration against the untouched SOL HELD_OUT months (Section 6) exactly once; (b) run the same frozen configuration against BTC as a cross-asset robustness check, per the original instruction that BTC now serves this role only.
- **Rejection/stop criteria:** if HELD_OUT contradicts VALIDATION's conclusion, the honest result is reported as such — it is not a license to return to Sprint 4/5 and adjust, which would make the held-out period retroactively contaminated (Revision 1's process failure, avoided this time by rule).
- **Effort:** Medium. **Dependency:** every prior sprint fully frozen.

---

## Final answers, stated explicitly

- **Revised primary-instrument decision:** SOLUSDT is primary for all research, development, validation, and paper trading from this point forward. BTCUSDT is retained only as a later, frozen-logic robustness check (Sprint 9).
- **Missing SOL data that must be obtained:** **none.** All 24 months (2024-01 through 2025-12) exist, are gap-free, duplicate-free, and pass the existing integrity pipeline — confirmed directly in Section 1, not assumed.
- **Revised TRAIN/VALIDATION/HELD_OUT structure:** Section 6, proposed and pending your approval — 4 TRAIN months, 4 VALIDATION months, 2 HELD_OUT months, spanning strong bull, strong bear, range, high-vol, and low-vol conditions, selected from price data alone.
- **Can Sprint 1 still be approved unchanged?** **Nearly** — the O(n²) fix itself is identical to Revision 1, but Sprint 1 now also carries the `round_number_spacing`/`volume_profile_bucket_size` decision from Section 1.5, since leaving BTC-scaled defaults in place would silently corrupt every SOL result that follows. This is a small addition to Sprint 1's scope, not a new sprint.
- **Exact first implementation sprint recommended:** **Sprint 1 as revised in Section 8** — the O(n²) replay fix, together with the coordinator-defaults decision for SOL and confirmation that the fix and every touched module remain symbol-agnostic. Still zero strategy logic touched, zero threshold fit to any backtest result, and now explicitly the gate that prevents every subsequent SOL sprint from silently inheriting a BTC-shaped bug.

**Stopping here. Awaiting your approval of Section 6's partition and Sprint 1 as revised before implementing anything.**
