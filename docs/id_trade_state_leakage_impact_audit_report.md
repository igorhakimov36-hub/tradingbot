# Impact Audit: `id(trade)`-Keyed State-Reuse Defect

Narrowly scoped audit, triggered by the confirmed `id(trade)`-keyed
state-leakage bug found while reconciling the SOL Progressive Stop
Management sprint. Scope: find every occurrence of persistent state
keyed by `id(trade)` (or an equivalent object-identity key) across all
exit-research code, determine which are actually exploitable (not
every `id()` use is defective), and correct + rerun only what is
confirmed affected — same periods, same frozen parameters, no new
tuning.

## Method

Searched the full repository, `strategy/research/`, `backtesting/`,
and this session's own scratchpad (the only place research-only,
never-committed exit-policy code can persist between sprints) for
`id(` used as a dict/cache key on a trade-like object. Cross-checked
every hit against whether its owning policy instance is ever reused
across more than one trade in a single run — a fresh instance per
trade cannot leak state regardless of `id()` reuse; only a reused
instance can.

## Confirmed defects (2 total)

**1. `StaircaseExitPolicy` (SOL Progressive Stop Management sprint,
`strategy/research/progressive_stop_policies.py`) — already fixed and
reported** in the prior turn. One policy instance reused across all
trades in a sequential-backtest month; `id()`-keyed dict leaked stale
R0/MFE/stop state across trades once CPython reused a collected
trade's address. Fixed by moving state onto the trade object itself as
an attribute. Sequential backtest, funding recompute, and final
metrics were rerun; Policy D's verdict changed from "NO SUPPORTED
IMPROVEMENT" to **INSUFFICIENT EVIDENCE**, which **remains frozen at
that verdict** — untouched by this audit.

**2. `StructureBasedTrailExitPolicy` (Exit Management Sprint,
scratchpad-only, never committed) — newly found and fixed by this
audit.** Same exploitable pattern: `run_exit_management_sprint.py`
constructs one policy instance per window/setup-group and reuses it
for the entire month. `trade_log`, keyed by `id(trade)`, could leak
stale `activated`/`true_be`/pending-stop state the same way. Fixed
identically (attribute-based state; `trade_log` changed from an
`id()`-keyed dict to a plain list, since it too could have silently
overwritten one trade's diagnostics with another's on collision).
Rerun on the sprint's own original configuration (BTCUSDT, 2024-01 and
2025-03, S001_only/S005_only/S001_S005, Policy A vs Policy D) shows
Policy A (control) reproduces byte-identical in all 6 cases, and
Policy D's numbers change in 5 of 6 cases — always in the *unfavorable*
direction for Policy D relative to what was originally reported. **The
sprint's original "REJECT STRUCTURE TRAIL" verdict is unchanged, and
is now supported by a case that is if anything weaker for Policy D
than the one originally reported** — no conclusion in
`docs/exit_management_research_sprint_report.md` is reversed. Full
detail in the new
[`docs/exit_management_sprint_id_reuse_correction_addendum.md`](exit_management_sprint_id_reuse_correction_addendum.md).

## Unaffected implementations (checked, not assumed)

- **`paired_trade_simulator.py`** — always constructs a fresh policy
  instance per trade by design (the paired comparison's own frozen
  protocol). No `id()` usage found regardless; immune by construction
  even where an `id()`-keyed cache would otherwise be a risk.
- **`gap_aware_stop_fill.py`, `funding_overlay.py`,
  `liquidity_pool_source_grouping.py`** — no `id()`-keyed (or
  equivalent identity-keyed) state of any kind found. Grepped
  explicitly; zero hits.
- **`backtesting/backtest_runner.py`, `backtesting/execution_simulator.py`,
  `backtesting/exit_policy.py`** — permanent infrastructure shared by
  every sprint; no `id()`-keyed state found. These were already
  exercised correctly by the paired comparisons above (which never hit
  the bug), so this is a direct confirmation, not an inference.

## Unavailable historical code

None. `StructureBasedTrailExitPolicy`'s source was expected to be
unavailable (its own sprint report describes it as "research-only
scratchpad code... not committed" to the repository), but it was still
present in this session's own scratchpad directory and was inspected
and corrected directly. It remains uncommitted, consistent with the
project's established precedent for controlled-experiment wrappers —
only the fix itself (in that same scratchpad file) is new.

## Regression test determinism (requirement re-verified)

Both new tests in `tests/test_progressive_stop_policies.py` were
re-inspected line by line:

- `test_reused_policy_instance_does_not_leak_state_across_trades_via_id_reuse`
  explicitly asserts trade2's state is correct **"whether or not
  id(trade2) happens to equal the old trade1_id in this run"** — it
  checks the actual mechanism (attribute storage is per-object) rather
  than depending on a collision occurring.
- `test_two_trades_with_colliding_ids_get_independent_state_directly`
  sidesteps GC/address timing entirely by using two distinct objects
  with identical field values, proving independence is by object
  identity, never by address or field value.

Neither test's pass/fail outcome depends on CPython actually reusing
an address during the run. Confirmed deterministic.

## Constraints honored

- Policy D (Progressive Stop Management) remains classified
  **INSUFFICIENT EVIDENCE**; its parameters were not reopened or
  retuned. Protocol hash unchanged
  (`d24f43255bbc26df541fde29da6db2594688827155b211f29bc103a4c53e6e99`).
- The 3 April 2024 SHORT winners-cut-short adverse trades remain
  disclosed, unaltered, in
  `docs/sol_progressive_stop_management_research_report.md`.
- No production file was changed (`git status` shows only the
  already-uncommitted research files from this sprint sequence, plus
  the two new docs this audit adds).
- No new data period was accessed — only 2024-01 and 2025-03 (Exit
  Management Sprint's own original BTCUSDT periods) and the existing
  SOL TRAIN months already in use.

## Bottom line

One additional real defect was found and fixed, in code that was never
committed and remains uncommitted. It changed Policy D's (Exit
Management Sprint) reported numbers but not its verdict — REJECT
STRUCTURE TRAIL stands, on weaker evidence for Policy D than
originally reported, not stronger. No other implementation in the
exit-research codebase is affected. The Progressive Stop Management
sprint's Policy D verdict (INSUFFICIENT EVIDENCE) is unrelated to this
second defect and remains exactly as delivered.
