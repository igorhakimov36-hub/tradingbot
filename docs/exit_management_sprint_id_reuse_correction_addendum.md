# Exit Management Sprint — id(trade) State-Reuse Correction Addendum

This addendum documents a second, independent defect found in
`StructureBasedTrailExitPolicy` (the original Exit Management Sprint's
Policy D), unrelated to the same-bar retroactivity flaw already fixed
in the prior causal-correction addendum. It was found and fixed as
part of a narrowly scoped impact audit triggered by an identical
defect confirmed in the later, separate SOL Progressive Stop
Management sprint.

## The flaw

`StructureBasedTrailExitPolicy.trade_log` was a `dict[int, dict]`
keyed by `id(trade)`. `run_exit_management_sprint.py` (this sprint's
own runner) constructs exactly **one** policy instance per
window/setup-group and passes it to `BacktestRunner.run_strategy()`
for the entire month — the same "one policy instance reused across
many sequential trades" pattern already confirmed exploitable in the
Progressive Stop Management sprint. CPython legally reuses a
garbage-collected object's `id()`; once an earlier `SimulatedTrade` is
closed and dereferenced, a later, unrelated trade's `SimulatedTrade`
can receive the exact same `id()`, silently inheriting the earlier
trade's stale `activated` / `true_be` / pending-stop state from the
`id()`-keyed dict.

## The fix

Identical pattern to the Progressive Stop Management sprint's fix:
state is now stored as an attribute (`_structure_trail_state`)
directly on the `SimulatedTrade` object itself (confirmed safe — the
class is a mutable, `__slots__`-free dataclass), eliminating the
lookup key entirely. `trade_log` (used only for post-run diagnostics,
never read back during a run) was changed from an `id()`-keyed dict to
an insertion-ordered list, since a second `id()`-keyed structure would
still have silently overwritten one trade's logged diagnostics with
another's on collision, even after execution itself was made safe.

This file is research-only scratchpad code (per this sprint's own
original documentation) and was not previously committed; the fix
therefore lives in the same scratchpad location as the original, not
in the repository.

## Re-verification

Re-ran the sprint's own previously-authorized configuration exactly:
BTCUSDT, windows 2024-01 and 2025-03, setup groups S001_only /
S005_only / S001_S005, Policy A (control) vs Policy D
(StructureBasedTrailExitPolicy) — same periods, same strategy
parameters, no new tuning, no new data accessed.

**Control (Policy A) reproduced byte-identical in all 6 cases**, as
expected — `exit_policy=None` never touches the buggy code path.

**Policy D changed in 5 of 6 cases** (trade count changed in 4 of 6 —
the corrupted stop/TP state occasionally altered when a position
closed, shifting downstream entries since the strategy only evaluates
new entries while flat):

| Window | Setup group | PRE-FIX n / net P&L | POST-FIX n / net P&L | Δ net P&L |
|---|---|---|---|---|
| 2024-01 | S001_only | 10 / −$490.05 | 10 / −$490.05 | $0.00 (unaffected — no id() collision occurred in this run) |
| 2024-01 | S005_only | 93 / −$2,107.13 | 89 / −$2,340.20 | −$233.07 |
| 2024-01 | S001_S005 | 101 / −$2,195.77 | 92 / −$2,605.37 | −$409.60 |
| 2025-03 | S001_only | 16 / +$212.86 | 16 / +$97.04 | −$115.83 |
| 2025-03 | S005_only | 123 / −$3,723.88 | 120 / −$3,769.46 | −$45.58 |
| 2025-03 | S001_S005 | 137 / −$3,594.01 | 133 / −$3,732.35 | −$138.34 |

**In every one of the 6 cases, the post-fix result is equal to or
worse than the pre-fix result for Policy D** — the defect never made
Policy D's own case look worse than it truly was; if anything the
original report's numbers were slightly favorable to Policy D relative
to the corrected ones.

## Verdict

**The original "REJECT STRUCTURE TRAIL" verdict is unchanged — and is
now supported by a strictly weaker case for Policy D than originally
reported**, not a stronger one. No conclusion in
`docs/exit_management_research_sprint_report.md` is reversed by this
correction. No production code, no committed strategy code, and no
new data period were touched.
