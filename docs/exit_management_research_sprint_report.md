# Exit Management Research Sprint
## Structure-Based Dynamic Exit Policy vs Fixed Exits (S001, S005)

> ## ⚠️ SUPERSEDED — the headline tables below are NOT the current numbers
>
> This document is preserved as the **original, as-delivered version**
> (v1 — first same-bar, buggy exit-timing implementation). Its own
> "Results" tables (2024-01 / 2025-03, Section "Results") reflect that
> **original, pre-correction** run and are kept here unedited for
> historical record only. Two independent defects were found and fixed
> after this report was delivered, each producing its own corrected
> numbers:
>
> - **v2 — causal (same-bar → next-bar activation) correction**:
>   [`docs/exit_management_sprint_causal_correction_addendum.md`](exit_management_sprint_causal_correction_addendum.md)
> - **v3 — `id(trade)` state-reuse correction** (current, most
>   authoritative numbers): [`docs/exit_management_sprint_id_reuse_correction_addendum.md`](exit_management_sprint_id_reuse_correction_addendum.md)
> - Full audit trail and historical-artifact linkage:
>   [`docs/id_trade_state_leakage_impact_audit_report.md`](id_trade_state_leakage_impact_audit_report.md),
>   [`docs/exit_policy_state_isolation_impact_report.md`](exit_policy_state_isolation_impact_report.md)
>
> **The verdict itself did not change across any of these
> corrections: REJECT STRUCTURE TRAIL, v3 resting on a case that is if
> anything weaker for Policy D than this original (v1) report shows —
> never stronger.** Use v3 (the id-reuse addendum) for any current
> reference to this sprint's numbers; use this document only to see
> what was originally reported and why it changed.

**Question asked:** if a trade moves in our favor, can we reduce full-stop
losses and protect profits using only confirmed market structure? The
answer was not assumed — it was measured.

---

## Step 0 — Architecture Check

Confirmed by reading `execution_simulator.py`, `trade_setup.py`, and
`backtest_runner.py`: dynamic stop/TP updates were **not** supported,
not because `SimulatedTrade` is immutable (it isn't — a plain mutable
dataclass), but because `BacktestRunner.on_replay_step` never gives
anything a chance to touch an open trade before `process_candle` checks
it, and deliberately never builds a `market_snapshot` while a trade is
open (a documented performance decision).

**Smallest additive change made** (approved before implementation):
- One new optional parameter, `exit_policy: ExitPolicy | None = None`,
  on `BacktestRunner.run_strategy`. Default `None` → the
  snapshot-while-open branch is never taken, `process_candle` runs
  unmodified.
- New minimal file [backtesting/exit_policy.py](../backtesting/exit_policy.py) —
  just the `ExitPolicy` protocol. No change to `ExecutionSimulator`,
  `SimulatedTrade`, `TradeJournal`, `TradeSetup`, or `StrategyEngineV2`.
- The concrete `StructureBasedTrailExitPolicy` was kept as **research-only
  scratchpad code**, per this project's established precedent for
  controlled-experiment wrappers (VNR Round 1's `_FilterWrapper`) — not
  committed.

**Control byte-identical, verified directly:** a fresh S001-only
2024-01 run on the post-edit code with `exit_policy` omitted was
compared trade-for-trade against the same backtest already computed by
the pre-edit code (from an independent process still running the old
module in memory). OPENED sequence, CLOSED sequence, net PnL, and max
drawdown were all exactly equal.

**Full regression suite: 800/800 passing** (795 pre-existing + 5 new
tests for the hook itself — verifying `exit_policy=None` is never
invoked, a policy is called exactly once per open-trade bar, a stop
mutation actually flows through to `ExecutionSimulator`, and omitting
the argument matches passing `None` explicitly).

**Disclosed modeling choice:** the policy sees the current bar's
high/low (to judge unrealized R) before that same bar's stop/target
check runs — the same same-bar ordering ambiguity
`ExecutionSimulator.process_candle` already accepts via its own
`STOP_LOSS_AMBIGUOUS` convention, not a new risk.

## Exit Policy D — Implementation Summary

Fixed, pre-declared logic only, reusing only already-exposed
`MarketIntelligenceSnapshot` fields:

- **Activation:** current bar's favorable excursion (high for LONG,
  low for SHORT) reaches ≥1R of the trade's *original* risk. Before
  that, nothing moves.
- **Stop:** `new_stop = max(current_stop, true_break_even, confirmed candidates)`
  (min for SHORT) — monotonic by construction, folds "move to
  break-even" and "trail with structure" into one rule. True
  break-even is the exact algebraic inverse of `ExecutionSimulator`'s
  own entry/exit fee+slippage formulas (verified to net exactly
  0.00000000 in isolation), not an approximation. Confirmed candidates:
  last confirmed swing low/high, a liquidity pool swept in the trade's
  favor since entry, an active opposing-direction OB/FVG zone, or a
  CHOCH-against-direction warning (treated as one more candidate at
  `current_price × (1 ∓ 0.001)`, the same buffer constant already used
  elsewhere in this codebase).
- **Take-profit:** advances only to the *nearest* confirmed structural
  target beyond the current TP (never the most optimistic one, never
  closer) — opposing liquidity pool, prior session high/low, POC/VAH/VAL/HVN/LVN,
  or an opposing FVG/OB zone.

## Research Scope

**Windows:** 2024-01, and 2025-03 (the same randomly-selected 2025
month already drawn and used for S007 — not re-drawn, per instruction).
**Setups:** S001 only, S005 only, S001+S005. **6 A/D comparisons total.**

## Results

> **[v1 — SUPERSEDED, historical only]** These tables reflect the
> original same-bar-bug implementation. See the notice at the top of
> this document for the current (v3) numbers in
> `docs/exit_management_sprint_id_reuse_correction_addendum.md`.

### 2024-01

| Metric | S001 A | S001 D | S005 A | S005 D | S001+S005 A | S001+S005 D |
|---|---:|---:|---:|---:|---:|---:|
| Trades | 10 | 10 | 74 | 99 | 79 | 106 |
| Win Rate % | 30.00 | 40.00 | 35.14 | 40.40 | 34.18 | 37.74 |
| Profit Factor | 0.653 | **0.297** | 0.805 | **0.499** | 0.776 | **0.454** |
| Expectancy | -28.68 | -49.01 | -13.80 | -23.95 | -16.25 | -26.91 |
| Average R | -0.271 | -0.482 | -0.131 | -0.261 | -0.158 | -0.302 |
| Net Profit | -286.76 | -490.05 | -1020.93 | -2370.82 | -1283.57 | -2852.31 |
| Max DD % | 6.27 | 5.86 | 17.35 | 24.44 | 15.31 | 28.99 |

### 2025-03

| Metric | S001 A | S001 D | S005 A | S005 D | S001+S005 A | S001+S005 D |
|---|---:|---:|---:|---:|---:|---:|
| Trades | 13 | 16 | 89 | 130 | 93 | 154 |
| Win Rate % | 61.54 | 62.50 | 28.09 | 36.92 | 33.33 | 37.66 |
| Profit Factor | **2.395** | **1.387** | 0.586 | 0.421 | 0.750 | 0.446 |
| Expectancy | 67.86 | 12.59 | -30.47 | -29.09 | -18.07 | -25.59 |
| Net Profit | 882.23 | 201.50 | -2711.57 | -3781.84 | -1680.27 | -3940.56 |
| Max DD % | 1.20 | 2.36 | 27.12 | 37.82 | 16.80 | **39.41** |

**Profit factor fell in all 6 of 6 comparisons.** Net profit fell in 5
of 6 (the one nominal exception, S005-only March, still shows worse
drawdown and worse net profit — only expectancy ticked up +1.38, a
rounding-level change on a much larger trade count). Max drawdown
worsened in 5 of 6.

### Why: Policy D's own telemetry

| | S001 Jan | S005 Jan | S001+S005 Jan | S001 Mar | S005 Mar | S001+S005 Mar |
|---|---:|---:|---:|---:|---:|---:|
| Reached +1R | 4/10 | 44/79 | 43/84 | 9/13 | 49/101 | 57/112 |
| Received trailed stop | 4 | 44 | 43 | 9 | 49 | 57 |
| Received advanced TP | 4 | 39 | 40 | 9 | 46 | 55 |
| Stopped at ORIGINAL level | 6 | 35 | 40 | 4 | 52 | 55 |
| Stopped at IMPROVED level (full loss avoided) | 4 | 41 | 41 | 9 | 48 | 57 |
| Reached ORIGINAL TP | 0 | 1 | 2 | 0 | 0 | 0 |
| Reached ADVANCED TP | 0 | 2 | 1 | 0 | 1 | 0 |

TP advancement fires on roughly half of activated trades but is
reached almost never (0-2 trades out of 79-154 exits per config) —
the trailing stop consistently triggers first, so the take-profit half
of the policy is effectively moot regardless of its own merit.

**The clearest single piece of evidence — S001-only, 2025-03, 8
trades with identical entries in both runs:**

| Entry | A (fixed) | D (structure trail) |
|---|---|---|
| 03-04 14:49 SHORT | TAKE_PROFIT, net +178.09 | STOP_LOSS, net +166.89 |
| 03-05 00:45 LONG | TAKE_PROFIT, net +181.06 | STOP_LOSS, net +47.52 |
| 03-06 19:45 LONG | TAKE_PROFIT, net +190.39 | STOP_LOSS, net +107.57 |
| 03-10 09:30 SHORT | TAKE_PROFIT, net +192.79 | STOP_LOSS, net +77.12 |
| 03-13 02:00 SHORT | TAKE_PROFIT, net +191.46 | STOP_LOSS, net +58.79 |
| 03-16 16:30 SHORT | TAKE_PROFIT, net +192.57 | STOP_LOSS, net +0.00 |

Six of eight identical entries that reached the full 2R target under
fixed exits were instead cut short by the trailing stop under Policy
D — every one still profitable, every one smaller, one reduced all
the way to break-even. This single window accounts for most of that
config's -55.27 expectancy change.

## Validation

- Determinism: identical re-run of the 10-day smoke test byte-identical.
- Replay safety / no future leakage: activation and trailing use only
  the current bar's own OHLC and a snapshot built from history up to
  and including that bar — no new candle access anywhere in the policy.
- Fixed-exit control byte-identical: confirmed directly (Step 0).
- No setup behavior changed: S001/S005 source files untouched; entries
  are produced by the unmodified `strategy_callback`/`trade_setup_callback`.
- No Strategy Engine behavior changed: `strategy_engine_v2.py` untouched.
- Regression suite: 800/800 passing.
- **Entry-sequence divergence, disclosed rather than hidden:** because
  a faster or slower exit changes when the single-position slot frees
  up, Policy A and D's trade *sequences* diverge after the first exit
  whose timing changed — this is why S005-heavy configs show
  substantially more total trades under D (e.g. 89→130 in March): not
  new signals, but the same signal source re-evaluated sooner between
  shorter-duration trades. Every A/D comparison above is a full-window
  aggregate comparison for this reason, with paired single-trade
  comparisons reported only for the initial run of entries that still
  align exactly.

## Final Conclusion — Answered with measured evidence only

1. **Does it improve S001?** No — profit factor fell in both windows
   (0.653→0.297; 2.395→1.387), expectancy fell in both.
2. **Does it improve S005?** No — profit factor fell in both windows
   (0.805→0.499; 0.586→0.421); net profit and drawdown worsened in
   both, including the one window with a rounding-level expectancy tick-up.
3. **Does it reduce drawdown?** No — worse in 5 of 6 comparisons, once
   dramatically (16.80%→39.41%).
4. **Does it improve expectancy?** No — worse in 5 of 6, by as much as
   -55.27 per trade in one window.
5. **Protect winners or cut them too early?** Cuts them too early. It
   does avoid some full original-stop losses (35-57 trades per config
   exited at an improved level instead) — a real, measured benefit —
   but the winners it sacrifices are larger and more numerous than the
   losses it rescues, net negative in every window tested.
6. **Does dynamic TP help or hurt?** Neither, in practice — it almost
   never gets the chance to matter, because the trailing stop reliably
   exits the trade first (0-2 advanced-TP hits out of hundreds of exits).
7. **Worth promoting to a general Exit Engine?** No, not on this evidence.

**Final verdict: REJECT STRUCTURE TRAIL.**

This rejects the specific fixed policy tested here — activate at +1R,
trail to the tightest confirmed structural level, advance TP to the
nearest confirmed target beyond it — not the general idea that any
dynamic exit could ever help. The identified mechanism (winners cut
short outweighing losses avoided) is consistent across both setups,
both independent months, and all three setup groupings, with no
window contradicting the direction of the result.
