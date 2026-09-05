# SOL IFVG + Retest Experiment — Frozen Protocol

Frozen before any TRAIN outcome is computed. Hashed immediately after
finalization; the hash is verified unchanged before any result in the
eventual report is interpreted.

---

## 1. Baseline (preserved, reused — not re-derived)

- FVG/IFVG lifecycle implementation: `strategy/features/fair_value_gap.py`
  (`docs/fvg_ifvg_implementation_sprint_report.md`) — wick-based fill
  separated from close-confirmed, strictly-stronger inversion, on the
  same object; post-inversion failure; bounded retention
  (`inversion_watch_bars`); independently-optional retest
  (`track_retests`); both flags default `False`.
- `docs/fvg_ifvg_nephew_sam_comparison_and_stop_design_report.md`
  Addendum, preserved verbatim:
  - S001's sweep-event identity was verified by direct code trace
    (not recency).
  - S001's current pool-boundary stop follows its own documented,
    intentional contract; a sweep-extreme stop remains a strategy
    hypothesis, not a correction — **this experiment does not touch
    S001 or its stop logic at all.**
  - Current Order Block behavior is unchanged (`docs/order_block_msb_ob_comparison_report.md`
    — no change was justified there either).
  - **IFVG and retest tracking remain unexposed through the
    coordinator/snapshot path.** This experiment does not change that
    — it reads the tracker directly via a standalone research adapter
    (`strategy/research/ifvg_retest_adapter.py`), never modifying
    `MarketIntelligenceCoordinator` or `market_intelligence_snapshot.py`.
- Working tree at the start of this sprint: 21 uncommitted files (the
  Multi-Module Setup Discovery sprint, the FVG/IFVG design review and
  implementation sprint, the Order Block and Nephew_Sam_ comparison
  reports) — preserved unchanged throughout.

## 2. Research integration (already completed, described here for the record)

`strategy/research/ifvg_retest_adapter.py` — a standalone
strategy_callback/trade_setup_callback pair (the same shape as every
other adapter in this project), owning its own
`FairValueGapTracker(track_inversions=True, track_retests=<arm==retest>)`
instance, fed the identical 15m candle stream the production
coordinator already receives. No detection logic is duplicated — only
the already-built, already-tested opt-in flags are turned on in a
second, independent tracker instance.

- **Identity**: `(direction, zone_high, zone_low, created_at)` —
  the same composite-key-plus-creation-timestamp pattern already
  established for Breaker Block.
- **Original vs. effective direction**: an originally-bullish gap that
  inverts trades **SHORT** (now acting as resistance); the mirror
  holds for originally-bearish. Recorded on every event as both
  `original_direction` and `effective_direction`.
- **Actionability, proven (not assumed)**: both arms check only
  whether the confirming field equals the bar currently being
  processed — never scanning backward for a missed prior event.
  `tests/test_ifvg_retest_adapter.py::test_event_bar_attribution_is_not_retroactive_under_incremental_sync`
  proves this directly under the real, incremental one-candle-at-a-time
  replay contract.

## 3. The experiment (frozen before outcomes)

**Primary question**: does the implemented IFVG + confirmed-retest
mechanism support a tradable SOLUSDT setup, after costs, on the
already-registered SOL TRAIN months?

**Two arms, standalone, no portfolio crowding between them**:
- **Arm A — inversion entry**: enter the effective direction the exact
  bar `is_inverted` first becomes true for a given gap.
- **Arm B — retest entry**: enter the effective direction the exact
  bar `retest_confirmed_this_bar` is true for an already-inverted,
  not-failed gap (the tracker's own 2-bar rejection pattern,
  `retest_cooldown_bars=5` default, unchanged).

**These arms have deliberately different entry timing and are not a
paired, identical-entry comparison** — Arm B's population is a strict
subset of gaps that both inverted AND later retested; Arm A trades
every inversion regardless of whether a retest ever follows. Results
are reported per arm, never subtracted or differenced against each
other as if matched.

**Entry**: current bar's own close (matching every existing setup's
convention), on the exact bar the arm's own trigger condition is met.

**Initial stop** (identical construction for both arms): the gap's own
**original far edge** — `zone_high` for an originally-bullish
(now-SHORT) gap, `zone_low` for the mirror — offset by the existing
`STOP_BUFFER_PCT`, floored by the existing `MIN_RISK_PERCENT`. This is
**the same boundary the tracker's own `is_failed` state uses** — by
construction, stop-placement and the tracker's own descriptive
thesis-failure marker are the same price level, though **not the same
mechanism** (see below).

**Explicit distinction (required by the authorizing instruction)**:
the tracker's `is_failed` is a **close-confirmed, lagging** lifecycle
marker (set only when a later candle's own CLOSE clears the boundary).
The actual protective stop that executes in this backtest is
`ExecutionSimulator`'s own **existing, unmodified, wick-based**
stop-loss check — comparing each new candle's high/low against the
stop level, intrabar. In practice the real stop will almost always
fire before `is_failed` could ever be observed (a wick reaching the
level precedes a close beyond it). `is_failed`/`inversion_expired` are
used **only** for the opportunity ledger (Section 5) — never as the
mechanism that closes a trade.

**Target**: fixed 2R, matching this project's own control-comparable
convention (S008/S009's own fixed-2R choice, for the same reason:
isolating the entry/stop mechanism as the variable under test).

**Expiry/duplicate handling**: reused, not reinvented — the tracker's
own `inversion_watch_bars` (default 500) bounds how long an
uninverted, filled gap is watched; `is_inverted`/`is_failed` are
one-shot and sticky (proven in the implementation sprint); the retest
cooldown (5 bars) is unchanged.

**Position sizing**: `create_risk_based_trade_setup`, `risk_percent=1.0`,
`MIN_RISK_PERCENT=0.006` — identical to every other setup in this
project. R0 defined consistently as `|entry - stop| * quantity` from
the actual entry/stop/quantity a trade opened with.

**Explicitly excluded from this experiment**: trailing-stop logic
(Progressive Stop Policy D remains frozen, INSUFFICIENT EVIDENCE, not
touched); any alternative initial-stop placement (the sweep-extreme
idea remains its own, separate, S001-only hypothesis, not applied
here); any parameter grid or threshold search on
`inversion_watch_bars`/`retest_cooldown_bars`/`STOP_BUFFER_PCT` — all
held at their existing, already-established defaults.

## 4. Data boundaries and prior reuse (disclosed, not hidden)

**SOL TRAIN months only**: 2024-02, 2024-04, 2024-09, 2025-12 — the
same 4 months already used by every SOL sprint in this project's
history. **These are explicitly exploratory results, not fresh
out-of-sample evidence** — this project's own cumulative trial count
across these same 4 months now includes (per the Multi-Module sprint's
own trial log): the Liquidity Pool lifecycle series (5 sprints), CVD/Delta
signal-value (4 hypotheses), SOL funding/source re-analysis (1),
Progressive Stop Management (3 policies), Multi-Module Setup Discovery
(S008/S009/S011, 3 hypotheses + 2 predeclared ablations). This
experiment (2 arms) brings the cumulative count to approximately
19-20 independently-tested SOL TRAIN hypotheses — disclosed explicitly
in the final report's uncertainty section, not omitted.

**No VALIDATION, SECONDARY_VALIDATION, or FINAL_HELD_OUT access.**

**Instrument scale**: `default_round_number_spacing`/
`default_volume_profile_bucket_size` from `strategy.instrument_scale`,
computed from each month's own first candle close — **not directly
used by this experiment** (the FVG tracker consumes only raw OHLCV,
no round-number or volume-profile dependency) — confirmed here for
completeness, matching the standing verification habit this project
follows for every SOL script, not because it is load-bearing here.

**Costs**: fee 0.04%/side, slippage 0.02%/side (project standard) +
the existing, already-tested `strategy/research/funding_overlay.py`
overlay, computed per trade from its own actual entry/exit timestamps
— never reusing another arm's or another sprint's funding total.

## 5. Opportunity ledger (frozen definition, before any outcome is seen)

For **every** event either arm's own trigger condition matches
(recorded via `event_log`, §2) — not only ones that become trades —
record: gap identity, original/effective direction, event type,
confirming bar/timestamp, and, for events that do **not** become
completed trades, the reason: blocked by an already-open position
(one-trade-at-a-time), or (Arm A only, diagnostic) whether the
underlying gap ever later retested/failed/expired. This ledger is
built **before** any P&L is computed, from the same real backtest run
that produces the trades — not reconstructed after the fact from
surviving trades alone.

## 6. Metrics and decision criteria (frozen)

**Per arm, pooled and per-month**: opportunity funnel (events →
completed trades, with no-trade reasons), LONG/SHORT counts, gross and
net P&L, total costs, win rate, profit factor, expectancy in dollars
and in fixed initial R, average holding time, and marked-to-market
drawdown (closed-trade equity curve — the same understated-but-disclosed
convention used in every prior report this project has produced).
Concentration (largest trade as % of net; per-month dependence) and a
month-clustered 95% CI (4 clusters, t-distribution df=3 — this
project's standing convention) on mean per-trade P&L, with its own
estimand stated explicitly, per the lesson already learned in the
Multi-Module sprint's own S011 completion.

**Decision language (frozen, matching this project's established
three-way classification)**:
- **Support for future validation**: after-cost expected value clearly
  positive, consistent in direction across ≥3 of 4 TRAIN months, month-
  clustered CI excluding zero, and no single trade or month
  responsible for the majority of the net result.
- **Insufficient evidence**: mixed direction across months, a CI
  including zero, a sample too small (<20 pooled trades) to
  distinguish from noise, or a result concentrated in one dominant
  trade/month (mirroring the S011 lesson directly).
- **Unsupported candidate**: consistently negative after-cost expected
  value across ≥3 of 4 months.

**VALIDATION is not accessed automatically** regardless of the TRAIN
result — a "support for future validation" verdict here only
identifies a candidate for a **separate, future, explicitly authorized**
frozen VALIDATION experiment.

**Planned run count**: 2 arms × 4 TRAIN months = 8 sequential
backtests (each a full-month, single-setup, standalone run). No
threshold sweep, no repeated re-runs with adjusted parameters. If a
disappointing result is observed, it is reported as observed.

## 7. Verification plan (before outcomes are computed)

- Focused adapter tests (`tests/test_ifvg_retest_adapter.py`): event
  timing, direction (both original-direction cases), no-duplicate
  refire, retest-requires-inversion precondition, retest cooldown,
  failed-gap exclusion, state isolation across independent instances,
  non-retroactive event-bar attribution, stop/target construction. All
  written and passing before this protocol was frozen.
- Full project regression suite, before and after.
- A real-data pipeline smoke test (10-day SOL slice) confirming both
  arms run cleanly through the actual `BacktestRunner`/
  `ExecutionSimulator` path and that the opportunity ledger correctly
  distinguishes "event occurred" from "event became a trade" (directly
  observed: the retest arm's own smoke test showed 37 events, 36
  trades — one event blocked by an already-open position, exactly the
  ledger's own purpose).
- Legacy compatibility: reuses
  `tests/test_fair_value_gap_inversion_compatibility.py` unmodified —
  not re-proven here, since this experiment does not touch the
  production coordinator/snapshot/S005 path at all (§1).

## 8. Explicit boundaries (restated)

No production file is modified. No VALIDATION/SECONDARY_VALIDATION/
FINAL_HELD_OUT data is accessed. Progressive-stop Policy D and S001's
stop logic are untouched. No parameter grid or outcome-driven
threshold change. All new code and docs are left uncommitted for
review.
