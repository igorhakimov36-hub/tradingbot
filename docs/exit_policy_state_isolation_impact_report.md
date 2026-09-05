# Exit-Policy State Isolation Impact Audit

Follow-up to the Progressive Stop Management reconciliation (which
corrected `StaircaseExitPolicy`'s `id(trade)`-keyed state-reuse defect
and left Policy D classified **INSUFFICIENT EVIDENCE**). This audit
asks whether the same defect class reaches any other exit-policy
implementation or earlier conclusion, and adds deterministic
regression coverage that does not depend on CPython happening to reuse
an address during a test run.

## 1. Implementation / version / defect / affected-experiment table

| Implementation | Instantiation pattern actually used | Classification | Affected experiment(s) |
|---|---|---|---|
| `StaircaseExitPolicy` — paired mode | fresh instance per trade (`paired_trade_simulator.py`, `progstop_paired_comparison.py`) | **Verified unaffected** — immune by construction | Progressive Stop paired A/B/C/D comparison — untouched |
| `StaircaseExitPolicy` — sequential mode | one instance reused for every trade in a TRAIN month (`progstop_sequential_backtest.py`) | **Reachable contamination demonstrated + historical impact confirmed** (already fixed, prior session) | Sequential backtest, funding recompute, final metrics — corrected; Policy D verdict corrected NO SUPPORTED IMPROVEMENT → **INSUFFICIENT EVIDENCE**, which stays frozen |
| `StructureBasedTrailExitPolicy` | one instance reused for the entire month, per (window, setup-group) — the **only** mode this sprint ever used; no fresh-per-trade variant exists for it | **Reachable contamination demonstrated + historical impact confirmed** (fixed and reverified this audit) | Exit Management Sprint's causal-correction addendum baseline — Policy D's numbers changed in 5 of 6 (window, setup-group) cells; verdict **REJECT STRUCTURE TRAIL unchanged**, now resting on a strictly weaker case for D than previously reported |
| `StructureBasedTrailExitPolicy` vs. the **main** sprint report's own tables | `docs/exit_management_research_sprint_report.md` | **Historical impact uncertain — moot** (see §2) | Not corrected here; orthogonal, already-superseded defect |
| `paired_trade_simulator.py` | always constructs a fresh policy per trade | **Verified unaffected** | N/A |
| `gap_aware_stop_fill.py`, `funding_overlay.py`, `liquidity_pool_source_grouping.py` | no `id()`- or object-identity-keyed state of any kind (grepped explicitly) | **Verified unaffected** | N/A |
| `backtesting/backtest_runner.py`, `execution_simulator.py`, `exit_policy.py` | permanent, committed infrastructure; no identity-keyed state | **Verified unaffected** | Shared by every sprint |

No case of genuinely **unavailable historical code** was found this
round: `StructureBasedTrailExitPolicy`'s source, though documented as
"not committed," was still present in this session's own scratchpad
and was inspected and corrected directly.

## 2. A discrepancy found while establishing historical linkage (not this defect)

Connecting each artifact to its actual report exposed that
`docs/exit_management_research_sprint_report.md`'s own published
tables (e.g. 2024-01 S005 D: n=99, net=−$2,370.82) match the
**pre-causal-correction, same-bar-bug** artifact
(`exit_management_sprint_results_ORIGINAL_BUGGY.pkl`), not the
next-bar-corrected numbers in its own
`exit_management_sprint_causal_correction_addendum.md` (n=93,
net=−$2,107.13 for the same cell — verified by direct pickle
inspection). The main report's headline tables were apparently never
updated after that addendum was written. This is a **documentation
synchronization gap from an unrelated, already-fixed defect** (same-bar
retroactivity, not `id()` reuse) — flagged for the user's attention,
not corrected here, since fixing it is outside this audit's scope
(§5's "no Hypothesis 2 / no expansion" boundary). The addendum, which
*is* internally consistent and up to date, is the artifact this id()
audit built its own correction on top of — confirmed by the exact
numeric match above.

## 3. Deterministic evidence

**Ownership check (per requirement):** both policies' identity-keyed
state held the same class of fields — original risk (R0 /
`initial_risk`), MFE (`max_favorable_price`), activation flags
(`activated`), and pending stop/target adjustments
(`pending_stop_price` / `pending_stop`, `pending_take_profit`). All are
now attribute-owned directly on the `SimulatedTrade` object in both
policies (`_progressive_stop_state`, `_structure_trail_state`), never
looked up by `id()`.

**Run-reset check:** confirmed, not assumed — both
`run_exit_management_sprint.py::run_one()` and
`progstop_sequential_backtest.py::run_variant()` construct a **brand
new** policy instance on every call (once per month / window ×
setup-group), so no state ever persists across separate runs. The
defect was reachable only *within* a single run's sequence of trades,
never across run boundaries.

**New regression tests** (added this audit; originally drafted in the
session scratchpad, then relocated into the repository proper —
uncommitted, alongside the rest of this research sequence — as
[`tests/test_structure_based_trail_exit_policy_state_isolation.py`](../tests/test_structure_based_trail_exit_policy_state_isolation.py),
following a follow-up check that the scratchpad-only copies were not
durably recoverable across sessions; see the Addendum at the end of
this document):

`test_structure_based_trail_exit_policy_state_isolation.py`, using
`monkeypatch.setattr("builtins.id", lambda obj: 999999)` to **force** a
collision deterministically rather than hoping CPython reuses an
address:

- `test_old_id_keyed_reference_leaks_pending_stop_under_forced_id_collision` — a minimal reference reproduction of the pre-fix dict-keyed mechanism, under a forced collision: **fails to isolate** (trade2 receives trade1's pending stop) — proves the defect class is real and deterministic, not merely theoretical.
- `test_fixed_structure_based_trail_policy_immune_to_forced_id_collision` — the real, current (fixed) policy, under the **identical** forced collision: **stays isolated** (trade2 unaffected, trade1's own state independently intact).
- `test_fixed_policy_two_distinct_trades_never_share_state_object` — direct construction check with real (unpatched) `id()`, mirroring the existing Progressive Stop pattern.

All 3 pass. The existing 2 tests in `tests/test_progressive_stop_policies.py` were re-inspected and reconfirmed to already meet this same bar (neither depends on an actual collision occurring during the run — see prior audit).

## 4. Corrections and rerun results

**Fix** (identical pattern to `StaircaseExitPolicy`'s): state moved
from an `id(trade)`-keyed dict onto a `_structure_trail_state`
attribute on the trade object; `trade_log` (post-run diagnostics only,
never read during a run) changed from an `id()`-keyed dict to a plain
list, since it too could silently overwrite one trade's logged
diagnostics with another's on collision. `run_exit_management_sprint.py`
and `smoke_test_exit_policy.py` updated for the `trade_log` shape
change (list, not dict).

**Rerun** (same BTCUSDT symbol, same 2024-01 / 2025-03 windows, same
S001_only / S005_only / S001_S005 setup groups, same entry logic and
exit parameters — no new tuning, no new periods):

| Window | Group | Pre-fix n / net P&L | Post-fix n / net P&L | Δ net P&L |
|---|---|---|---|---|
| 2024-01 | S001_only | 10 / −$490.05 | 10 / −$490.05 | $0.00 |
| 2024-01 | S005_only | 93 / −$2,107.13 | 89 / −$2,340.20 | −$233.07 |
| 2024-01 | S001_S005 | 101 / −$2,195.77 | 92 / −$2,605.37 | −$409.60 |
| 2025-03 | S001_only | 16 / +$212.86 | 16 / +$97.04 | −$115.83 |
| 2025-03 | S005_only | 123 / −$3,723.88 | 120 / −$3,769.46 | −$45.58 |
| 2025-03 | S001_S005 | 137 / −$3,594.01 | 133 / −$3,732.35 | −$138.34 |

Control (Policy A) reproduced **byte-identical** in all 6 cases
(`exit_policy=None` never touches the affected code path) — confirming
these differences are attributable solely to the fix. Since the only
code difference between the two runs is the state-lookup mechanism,
**any non-zero difference is itself proof that a real `id()` collision
occurred in that specific historical run** — not merely a theoretical
property of the old code. Full detail, including the drawdown deltas,
is in `docs/exit_management_sprint_id_reuse_correction_addendum.md`.

**Funding:** not applicable — the Exit Management Sprint never
incorporated a funding overlay (grepped both its report and addendum;
zero mentions), so no funding recomputation is required for this
correction.

## 5. Verdicts

- **Progressive Stop Management, Policy D: INSUFFICIENT EVIDENCE** — unchanged, parameters frozen, not reopened by this audit. Protocol hash unchanged (`d24f43255bbc26df541fde29da6db2594688827155b211f29bc103a4c53e6e99`). The 3 April 2024 SHORT winners-cut-short adverse trades remain disclosed in `docs/sol_progressive_stop_management_research_report.md`, unaltered.
- **Exit Management Sprint: REJECT STRUCTURE TRAIL — remains supported**, and now rests on a case that is if anything *weaker* for Policy D than what was previously reported, never stronger. No verdict in `docs/exit_management_research_sprint_report.md` or its addendum is reversed.
- **Main report document's own stale tables (§2): unverified / flagged, not corrected** — a documentation-sync issue from an unrelated, already-superseded defect, outside this audit's scope.
- **No other implementation requires revision.**

## 6. Test results and changed files

Full project suite: **1153 passed, 0 failed** (unchanged from before this audit — no committed file's behavior changed).
Combined progressive-stop + new state-isolation tests: **22 passed, 0 failed**.

**Changed files this audit** (repository paths are untracked/uncommitted, matching the rest of this research sequence; the smoke test remains scratchpad-only as a minor, non-essential diagnostic):

- [`strategy/research/structure_based_trail_exit_policy.py`](../strategy/research/structure_based_trail_exit_policy.py) (repo, relocated from scratchpad) — `id(trade)`-keyed dict → attribute-based state; `trade_log` dict → list
- [`strategy/research/run_exit_management_sprint.py`](../strategy/research/run_exit_management_sprint.py) (repo, relocated from scratchpad) — import updated to the repo-resident policy module; `trade_log` save call updated for the list shape
- `smoke_test_exit_policy.py` (scratchpad only — diagnostic-only script, not part of the headline rerun configuration; `trade_log` iteration updated for the list shape but not relocated)
- [`tests/test_structure_based_trail_exit_policy_state_isolation.py`](../tests/test_structure_based_trail_exit_policy_state_isolation.py) (repo, relocated from scratchpad, new) — 3 deterministic regression tests
- [`docs/exit_management_sprint_id_reuse_correction_addendum.md`](exit_management_sprint_id_reuse_correction_addendum.md) (repo, new)
- [`docs/id_trade_state_leakage_impact_audit_report.md`](id_trade_state_leakage_impact_audit_report.md) (repo, new)
- `docs/exit_policy_state_isolation_impact_report.md` (repo, this document)

No production file, no committed strategy/backtesting code, and no
new data period (SOL FINAL_HELD_OUT and every restricted period
remain untouched) were accessed or modified. All files listed above
remain uncommitted, alongside the rest of this research sequence.

## Addendum: recoverability follow-up

A subsequent check confirmed the fixed policy, its rerun
configuration, and its regression tests initially existed **only**
under the session's OS-temp scratchpad
(`AppData\Local\Temp\claude\...\scratchpad`), entirely outside the git
repository — not recoverable if that temp directory were cleared
between sessions. This has been corrected: the canonical, current
copies now live in the repository (untracked/uncommitted) at
`strategy/research/structure_based_trail_exit_policy.py`,
`strategy/research/run_exit_management_sprint.py`, and
`tests/test_structure_based_trail_exit_policy_state_isolation.py`.
Re-verified from the new locations with no scratchpad path hacks: full
suite **1156 passed, 0 failed** (1153 prior + 3 new), and a
syntax/import check of the relocated harness (no backtest rerun
performed — no new simulation defect was found that would require
one).
