# Repository Audit — Main Branch

Inspection only. No code was modified, fixed, or refactored to produce
this report. Every claim below was verified directly against the
current `main` branch (confirmed via `git status` — clean working
tree, `git log` — HEAD at `9971b37`) or by executing existing code
in isolation to check a specific claim empirically, never by
inference alone.

---

## Verification checklist

**Every approved setup exists and is wired correctly.**
- `strategy/setups/liquidity_sweep_reversal.py` — `LiquiditySweepReversalSetup` present. The permanent "require ≥1 additional confirmation" change is intact: `required = [sweep_condition, cvd_condition, confirmation_condition]` (3 required conditions), confirmed by direct read of the current file, not memory.
- `strategy/setups/order_block_continuation.py` — `OrderBlockContinuationSetup` present, single required condition (`active_order_block_first_touch`), matching its documented design.

**Every archived setup exists.**
- `strategy/setups/volume_node_reversal.py` — `VolumeNodeReversalSetup` present, unmodified since S003. Its two research reports (`volume_node_reversal_report.md`, `volume_node_reversal_round1_experiments.md`) both now carry the `STATUS: RESEARCH ARCHIVE` banner added when it was archived.
- `strategy/setups/fair_value_gap_rebalance.py` — `FairValueGapRebalanceSetup` present, matching `fair_value_gap_rebalance_report.md`'s `RESEARCH ARCHIVE` verdict.

**The rejected setup exists (code was never asked to be removed).**
- `strategy/setups/smt_reversal.py` — `SmtReversalSetup` present, unmodified since S004, matching `smt_reversal_report.md`'s `REJECTED` verdict and the explicit instruction to leave it in place, untouched, not revisited.

**Strategy Engine V2 integration** — `strategy/strategy_engine_v2.py` unchanged this entire research cycle (not present in the diff of any commit after its own foundation commit). `engine_decision_to_dict()`'s `fired_setups[0]` tie-break is exactly as originally built and as described in the Portfolio Decision Engine research (never modified to add arbitration, correctly, since that engine was never implemented).

**Coordinator integration** — `strategy/market_intelligence_coordinator.py` verified by direct read: all 10 single-symbol trackers wired in `__init__` and synced in `sync_and_build`'s per-candle loop; `smt_pairs`/`CorrelationTracker` wiring from Step 0 present and intact, including the cache-key fix (`_last_reference_lengths`) that prevents a reference-only update from returning a stale snapshot.

**Snapshot fields** — `strategy/market_intelligence_snapshot.py` has **not been modified at all since Phase 2.1 Step 1** (absent from every commit's diff since). Zero drift in the `Zone`/`Level`/`MarketIntelligenceSnapshot` schema across five setups and one architecture change built on top of it.

**Backtest adapter integration** — `strategy/strategy_engine_v2_backtest_adapter.py` verified by direct read: `reference_symbols` parameter and forwarding logic from Step 0 intact; the generic `required_conditions[0].evidence["zone_high"/"zone_low"]` stop-loss contract is used identically by all five setups (confirmed each setup's required condition places these exact keys), so the adapter needed no per-setup special-casing, exactly as designed.

**Trade Journal integration** — `setup_name` threading confirmed present at 15 call sites in `backtesting/trade_journal.py` and 15 in `backtesting/backtest_runner.py`, matching the original Step 4 implementation.

**Permanent experiment promotions** — Liquidity Sweep Reversal's confirmation gate (the only permanent promotion made this project) verified intact, as above. No other permanent promotions were made (Volume Node Reversal's `node_is_wide` finding was explicitly left as a documented, not-yet-acted-on research lead — correctly, it has not been silently promoted into the setup's required conditions; the code still shows zero required-condition gating beyond the single first-touch check).

**Architectural connections** — Full regression suite re-run fresh for this audit: **745 passed**, identical count to every prior report this session. All 96 dataset files remain present and unmodified (spot-checked; this audit did not re-run the full per-file dataset validation since no code path that reads them changed).

---

## Consistency check — findings

**1. `docs/strategy_engine_v2_audit.md` contains claims that are now factually false, unflagged as stale.**
Lines 144, 195, 223, and 421 assert "the entire `levels` list... is never read by anything" and that "Levels and Intermarket contribute nothing measurable today." Both claims were true when written (before S003/S004 existed) and are **false now**: `VolumeNodeReversalSetup` reads `snapshot.levels` extensively (`strategy/setups/volume_node_reversal.py:169,172,179,235,236` — POC/HVN/VAH/VAL), and `SmtReversalSetup` reads `snapshot.intermarket` as its sole required-condition data source. The document carries no "as of" date or superseded-by note. Anyone reading it today without cross-referencing later reports would draw an incorrect conclusion about what the Snapshot's Levels and Intermarket fields do. This is documentation drift, not a code problem — the code is correct; the older document simply was never revisited after later work invalidated part of it.

**2. `COMMON_SMT_PAIRS` (in `strategy/features/correlation.py`) is defined, tested, and never consumed by any runtime code path.**
It is imported and exercised only by its own test, `tests/test_correlation.py` (lines 7, 337, 340, 351). Every actual `SMTPair` used in the Coordinator, `SmtReversalSetup`'s validation, and every backtest run this session was constructed manually inline (`SMTPair(name="btc_eth", primary_symbol="BTCUSDT", reference_symbol="ETHUSDT")`), never by referencing this predefined list. Not dead code in the sense of being unreachable — it is reachable and tested — but it is unused documentation-as-code: a list of 4 "common" pairs (`btc_eth`, `btc_total3`, `btc_dominance`, `eth_sol`) of which only one (`btc_eth`) has ever had real data behind it, and even that one was never actually sourced from this list.

**3. Five tests in `tests/test_historical_loader.py` pass today for a reason unrelated to what they claim to verify — confirmed empirically, not inferred.**
`parse_timestamp()` does not support ISO-8601 strings (it treats any string as a numeric epoch value); this is the known, already-disclosed cause of the file's 4 visible failures. What had not previously been checked: calling `normalize_ohlcv_record()` and `normalize_ohlcv_records()` directly with valid *numeric* timestamps (bypassing the ISO bug) shows that **no OHLC sanity validation and no duplicate-timestamp rejection exist in the current implementation at all** —
```
high<low record accepted with no error
negative-volume record accepted with no error
duplicate-timestamp records accepted with no error, both retained
```
This means `test_high_below_low_is_rejected`, `test_high_below_close_is_rejected`,
`test_low_above_open_is_rejected`, `test_negative_volume_is_rejected`, and
`test_duplicate_timestamp_is_rejected` currently show green **only because
their ISO-format timestamp strings trigger the unrelated `parse_timestamp`
failure before the code ever reaches the validation these tests are named
for** — validation that does not exist. This is the single most
consequential finding in this audit for future risk: if the already-known
ISO-timestamp bug is ever "fixed" without also checking these five tests
specifically, they will start failing for real, and whoever fixes the
timestamp bug will reasonably (and incorrectly) conclude they introduced a
regression, when in fact they will have simply removed the accidental mask
over five tests that were never verifying real behavior. `test_missing_
ohlcv_field_is_rejected` was checked and confirmed to pass for the
*correct* reason (the missing-field check runs before timestamp parsing
is ever reached).

**4. `strategy/setups/__init__.py` is empty — there is no canonical, importable registry of the Setup Library or its current statuses.**
"Which setups exist," "which are approved," and "which constitute the current Approved Portfolio" are facts that live only in documentation (`docs/*.md`) and in ephemeral, uncommitted research scripts written during each backtest session — never in a single committed module a future session (or a future engineer) could import to get an authoritative answer. Every backtest performed this session manually re-typed the list `[LiquiditySweepReversalSetup(), OrderBlockContinuationSetup()]` inline; nothing in the committed codebase encodes "these two, and only these two, are currently approved." This is consistent with every setup's own architecture (deliberately decoupled, "adding a setup needs no other file to change") but means the *portfolio composition itself* has no code-level source of truth — only a documentation-level one, which is a weaker guarantee than the rest of this codebase's own standards.

**5. Two parallel, fully coexisting trading pipelines remain in the repository, confirmed still both alive.**
`strategy/strategy_engine.py`, `strategy/decision_engine.py`, `strategy/order_block.py` (the pre-Phase-2 version), `strategy/liquidity.py`, `strategy/funding.py`, `strategy/volume.py`, `strategy/open_interest.py`, `strategy/feature_pipeline.py`, `strategy/feature_calculations.py`, and `strategy/trade_setup_callback.py` are all still present, still have passing tests (`test_funding.py`, `test_volume.py`, `test_open_interest.py`, etc.), and are still referenced by `run_backtest.py` and `diagnostic_report.py`. None of this is dead code — it is a fully separate, still-functional legacy scoring engine that Strategy Engine V2 was built to replace, not delete. Confirmed: no file in this legacy set imports anything from `strategy/setups/`, `strategy_engine_v2.py`, or `market_intelligence_coordinator.py`, and nothing in the V2 pipeline imports the legacy set — the separation is clean, but two independently-runnable trading systems now permanently coexist in one repository with no marker in either indicating which one a new reader should trust.

---

## Project health

**1. Architecture consistency.** Consistent. The layering described in every architecture document (Market Intelligence → Snapshot → Setup Evaluation → Strategy Engine V2 → Backtest Adapter → Journal) matches the actual import graph exactly, verified this session and in the original Phase 2 audit's own AST-parsing test. No setup imports a tracker directly; the Snapshot Builder remains a pure mapping function; `strategy_engine_v2.py` has zero feature-layer imports.

**2. Implementation consistency.** Consistent, with the one caveat above (Finding 3) in an adjacent, non-V2 module (`data/historical_loader.py`) that the new architecture depends on for loading data but did not implement.

**3. Documentation consistency.** Inconsistent in one specific, identified place (Finding 1) — `strategy_engine_v2_audit.md` is stale on the Levels/Intermarket usage question as of S003/S004. Every other document delivered this session (setup reports, the Portfolio Decision Engine design, the out-of-sample report, the independent review, the dataset validation report) was checked against current code and found accurate as of this audit.

**4. Unused code.** `COMMON_SMT_PAIRS` (Finding 2) — reachable, tested, never consumed by runtime code. No genuinely dead (unreachable) code was found in any module touched this session.

**5. Missing integrations.** None found relative to what was actually promised — every documented integration (Step 0's Coordinator/adapter wiring, every setup's adapter contract) was verified present. The one true absence is architectural rather than a broken promise: no committed "Approved Portfolio" registry (Finding 4) — this was never promised as a deliverable, so it is a gap to note for the future, not a broken integration.

**6. Broken assumptions.** `data/historical_loader.py`'s test suite assumes OHLC sanity and duplicate-timestamp validation exist; they do not (Finding 3). This is a broken assumption baked directly into the test suite itself, not into any code this session wrote or relied on incorrectly — real Binance Vision data has never violated these invariants, so it has never surfaced as a live bug, only as a latent one.

**7. Technical debt.** The two-pipeline coexistence (Finding 5) is the largest single piece of technical debt in the repository — not urgent, since the separation is clean, but a standing cost every new contributor pays in orientation time. The stale audit document (Finding 1) is smaller, cheap-to-fix debt.

**8. What would surprise us in six months.** Finding 3, unambiguously. A future engineer fixing the well-known, already-documented ISO-timestamp bug in `parse_timestamp` — a completely reasonable, low-risk-looking cleanup — would unknowingly cause five tests to fail, and would have no reason to suspect those five tests were never testing real behavior in the first place. Second most likely surprise: someone reading `strategy_engine_v2_audit.md` in isolation (it is the most detailed, most "official-looking" document in `docs/`) and concluding Volume Profile and Correlation Engine are still completely unused, missing that two later setups already changed that.
