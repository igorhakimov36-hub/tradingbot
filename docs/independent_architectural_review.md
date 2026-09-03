# Independent Architectural Review

Written cold, as the incoming Head of Quant Research, with no obligation
to agree with anything proposed before this document. No code was
touched to produce it. Where I disagree with the existing roadmap, I
say so directly, as asked.

---

## Executive summary

The research discipline in this project — the Setup Evaluation
Framework, controlled experiments, and the out-of-sample pass that just
ran — is genuinely strong, better than most retail systematic projects
ever reach. That is not the problem. The problem is that the roadmap
reads as a straight line from "more research" to "live trading," and it
skips three categories of work a real trading operation cannot skip:
**execution-cost realism, live operations (monitoring/recovery), and a
formal re-certification gate for what actually belongs in the Setup
Library** — the last one made urgent by the out-of-sample pass that
just showed one of the two "approved" setups doesn't hold up.

I would not keep the roadmap as written.

---

## 1. Would I keep this roadmap exactly as written?

No. Rewritten below, with justification for every change.

**Original:**
```
Dataset 2024–2025 → Cross-Asset Validation → Regime Research →
Multi-Position Engine → Portfolio Risk Engine → Portfolio Decision
Engine → Binance Testnet → Live Trading
```

**My version:**
```
Dataset 2024–2025 (BTC/ETH/SOL/XRP)
        |
        v
Cross-Asset Out-of-Sample Validation + Correlation/Diversification Analysis
        |
        v
Setup Library Re-Certification  <-- a DECISION GATE, not a build step
        |
        v
Regime Definition & Validation  <-- build and validate an actual
        |                          classifier before relying on one
        v
Execution Cost Realism Audit    <-- new phase, currently absent
        |
        v
Multi-Position Execution Engine + Portfolio Risk Engine (one phase, not two)
        |
        v
Portfolio Decision Engine
        |
        v
Live Infrastructure: Monitoring, Alerting, Crash Recovery & Reconciliation  <-- new phase
        |
        v
Binance Testnet  <-- rescoped: connectivity/order-lifecycle ONLY
        |
        v
Shadow Trading   <-- new phase: paper-execute on real live data,
        |            measure decision-for-decision parity vs. backtest
        v
Live Trading (small, explicitly capped pilot allocation)
```

---

## 2. Would I change the order of any phase?

Three changes, each for a specific technical reason:

- **"Setup Library Re-Certification" inserted immediately after
  cross-asset validation, before anything else.** The out-of-sample
  pass that just completed found that Order Block Continuation's
  approval does not hold up (0 of 6 out-of-sample months profitable,
  drawdown 2–3x worse than the backtest that approved it). Building a
  Portfolio Decision Engine, a Risk Engine, or a Multi-Position Engine
  *around* a Setup Library whose membership is already in question is
  building infrastructure for the wrong portfolio. Decide what actually
  belongs in the library first — this may shrink to one setup, or zero,
  and that outcome should be allowed to happen before more engineering
  is invested downstream of it.
- **"Regime Research" moved after re-certification and made concrete,
  not moved for ordering reasons but for a definitional one.** The only
  regime signal currently computed (`structure["market_structure"]`) is
  already documented in this project's own audit as "a cruder
  2-adjacent-candle heuristic," legacy-tied, not a rigorously validated
  classifier. Building a "Regime Research" phase on top of a classifier
  already known to be crude risks manufacturing a false sense of
  explanation for what might just be noise. Define and validate the
  regime classifier itself first — with the same rigor already applied
  to every tracker — then test whether Liquidity Sweep Reversal's
  Jan–Mar/Apr–Jun split actually correlates with it.
- **"Execution Cost Realism Audit" inserted before any portfolio
  infrastructure, not bundled into Testnet.** Every backtest run in this
  project's entire history used `ExecutionConfig`'s defaults:
  `fee_rate=0.0004`, `slippage_rate=0.0002` (fixed, size-independent),
  `latency_bars=0`, `fill_probability=1.0`. That means every single
  measured result assumes instant, guaranteed, full fills with a flat
  2-basis-point slippage regardless of order size or volatility — and
  every setup measured so far is already marginal-to-negative under
  those optimistic assumptions. This needs to be stress-tested before
  investing a month in portfolio-layer engineering that might be
  optimizing allocation of an edge that doesn't survive real friction.

---

## 3. Is there a missing phase that absolutely should exist before Binance Testnet?

Two, not one:

**Execution Cost Realism Audit** (justified above) — without it,
Testnet validates that orders can be *placed*, not that the backtest's
performance numbers mean anything close to what live trading would
actually produce.

**Live Infrastructure: Monitoring, Alerting, Crash Recovery & State
Reconciliation.** Nothing in the current project addresses: how a live
process detects its own data feed has gone stale; how it alerts a human
when an exception occurs; what happens if the process crashes with a
position open (does it know that position exists on restart? does it
reconcile local state against the exchange's actual account state, or
risk double-entering / abandoning a stop-loss?). This is not
"infrastructure for later" — a system that connects to Testnet without
this already built has no way to detect or recover from the exact
failure modes Testnet exists to surface. Building this *after* Testnet
inverts the point of testing.

---

## 4. Is there a phase that should be removed completely?

Not removed — **rescoped, because it is currently doing two different
jobs under one name.** "Binance Testnet" as written implies it will
validate execution quality (fills, slippage) as well as connectivity.
It cannot do the former: testnet order books are thin, often
artificially/synthetically maintained, and do not reflect real market
liquidity or spread dynamics. Treating a clean Testnet run as evidence
that slippage assumptions are realistic would be a false signal. Keep
Testnet, narrow its claimed scope to connectivity and order-lifecycle
correctness, and get execution-cost evidence from the dedicated audit
phase instead (Question 2).

---

## 5. The single biggest architectural weakness

**The backtest engine's single-position-at-a-time constraint.** This
is not a new observation — it is already in the roadmap as a phase — but
it deserves being named explicitly as *the* answer, because of how much
of the project's own measured history traces back to it. Five
independent research cycles (Order Block, Volume Node, SMT, Fair Value
Gap, and the dedicated Portfolio Decision Engine research) all
converged on the same root mechanism: crowding of 30–55% between any
two setups registered together, driven by `BacktestRunner` never even
calling `strategy_callback` while a trade is open. Every "combined
portfolio" number produced so far measures resource contention, not
genuine setup interaction. This is also the same architectural gap that
blocks real multi-*asset* trading (concurrent positions across BTC,
ETH, SOL, XRP have the identical structural problem as concurrent
positions across setups on one asset) — so fixing it serves both the
Setup Library work and the Cross-Asset work at once.

**Two close seconds, worth naming because they compound the first:**
funding-rate and open-interest data (`funding_loader.py`,
`open_interest_loader.py`, and real `BTCUSDT-funding-2024-*.csv` files)
have been downloaded and sit completely unused — no tracker, no Setup,
no part of the Snapshot ever reads them, despite both being arguably
*more* directly tied to institutional positioning than several ICT-style
price-action concepts already built into the Setup Library. And every
setup built so far was designed, iterated on, and judged exclusively
against BTCUSDT — "no parameter tuning" has been genuinely and
carefully honored, but *setup selection* itself (which five ideas got
built, which survived) was still shaped entirely by one asset's
behavior, a subtler form of the same overfitting risk the project has
otherwise worked hard to avoid.

---

## 6. If this were my own firm, what's the next milestone (not task)?

**Confirmed Alpha Certification.** Not "build the next thing" — a
formal gate: using the now-multi-asset, now-out-of-sample-tested
dataset, determine which setups (if any) demonstrate real,
non-marginal, reasonably regime-robust profitability, and reduce the
Setup Library to exactly that set before any further infrastructure
investment. Being honest about where the numbers currently stand: only
Liquidity Sweep Reversal has shown genuine positive edge in any
out-of-sample window, and even that was concentrated in 3 of 6 months.
A firm that built a Risk Engine and a Multi-Position Engine around a
five-setup library, only to discover the library should really contain
one setup, would have spent a month building portfolio machinery for a
single-strategy book. The milestone is the certification decision
itself, not the code that follows it.

---

## 7. Evidence required before trading $1 of real capital

Measurable, not aspirational:

1. **At least one setup or portfolio with positive expectancy across
   every out-of-sample window tested**, not a majority — or an explicit,
   independently-validated regime filter that reliably predicts *in
   advance* which windows will be profitable, not one identified by
   looking backward at which months happened to work.
2. **A sample size adequate for the claim being made.** Current best
   case (Liquidity Sweep Reversal, pooled across 6 OOS months) is 76
   trades — thin for a statistical claim of edge. Fisher/Mann-Whitney
   tests already flagged as underpowered below n=8 per arm in every
   prior report; the same standard should gate a live-capital decision,
   not just a research conclusion.
3. **A validated, data-derived transaction cost model** replacing the
   current fixed 2bp slippage / 0-latency / 100%-fill assumptions,
   confirmed against real achievable fills at the position sizes being
   considered — not assumed away.
4. **Multi-Position Engine and Portfolio Risk Engine built and
   independently validated** with the exact same rigor already applied
   to every Market Intelligence tracker: replay-safety, determinism,
   regression, before either is trusted with real capital allocation
   decisions.
5. **A monitoring system that has been failure-tested, not just built** —
   simulate a stalled data feed, a stuck order, an unhandled exception,
   and confirm the system detects and alerts on each, before assuming it
   will in production.
6. **A crash-recovery drill that has actually been run**: kill the
   live process mid-trade, restart it, and confirm it reconciles
   against the exchange's real account/position state without
   double-entering or abandoning a stop-loss. Not designed — executed
   and observed.
7. **A written, hard-enforced (not merely intended) capital-at-risk cap
   and kill-switch**, exercised at least once in a drill before being
   trusted in production.
8. **A pre-defined maximum acceptable live-vs-backtest decision
   divergence**, measured via the Shadow Trading phase (Question 1) —
   run the live decision path against real market data in parallel with
   the backtest replaying the identical data, and require a measured
   parity result before capital is at risk, not an assumption of parity.

---

## 8. Subsystem maturity classification

**Mature** (validated repeatedly, stable, trustworthy):
- Market Intelligence trackers (all 11 — Market Structure, FVG, Order
  Blocks, Breaker Blocks, Equal Highs/Lows, Session Boundaries,
  Liquidity Pools, Delta, CVD, Volume Profile, Correlation Engine)
- Market Intelligence Snapshot Builder (pure mapping, well-tested boundary)
- Setup Evaluation Framework itself (the `Setup`/`ConditionResult`/
  `SetupResult` contract — the architecture, not any specific setup)
- Trade Journal, Replay Engine, `WindowManager`
- Historical data infrastructure (loader, downloader — just extended
  and re-validated this session)

**Experimental / early, real progress but unsettled**:
- Setup Library *membership* — 5 built, mixed and now partly
  contradicted results; genuinely still research, not infrastructure
- `StrategyEngineV2`'s arbitration ("first fired setup wins") — already
  known and documented as inadequate
- Correlation Engine's real-world applicability — only one pair
  (BTC/ETH) ever validated against real data

**Not yet built (pre-experimental)**:
- Multi-position execution
- Portfolio Risk Engine
- Portfolio Decision Engine (designed on paper only, per the prior
  research cycle — zero code)
- Any live/execution infrastructure: order management beyond the
  backtest's simplified model, live data feeds, monitoring, disaster
  recovery, reconciliation
- Execution-cost realism validation against real market microstructure
- Funding-rate / open-interest integration into any decision path
  (data exists, is completely unused)

---

## 9. Architectural risks not yet addressed

Going through each named risk directly, grounded in what the code
actually does:

- **Execution**: the backtest's `ExecutionSimulator` models a
  simplified all-or-nothing fill (`fill_probability` is a single
  Bernoulli draw for the entire order, not partial-fill dynamics) with
  no market-impact/size-dependent cost. There is no real order-management
  concept (order types, cancel/replace, maker vs. taker choice) beyond
  "submit and it either fills or doesn't."
- **Latency**: entirely unmodeled in every backtest run so far
  (`latency_bars=0` was the default and was never overridden). A live
  system has real network/processing latency between signal generation
  and order placement that the backtest cannot represent at all.
- **Slippage**: fixed at 0.02%, size-independent, not derived from real
  order-book or trade-tape data — flagged above as the most concrete,
  immediately actionable gap.
- **Commissions**: `fee_rate=0.0004` (4bp) needs explicit verification
  against Binance's actual current fee schedule and the account's real
  tier/discount status, not assumed correct because it looks
  plausible.
- **Portfolio exposure / correlated positions**: no aggregate risk
  limit exists anywhere in the codebase — position sizing is purely
  per-trade (`calculate_position_size`, 1% of equity, no portfolio-level
  cap). Worth stating plainly: BTC, ETH, SOL, and XRP are historically
  highly correlated in risk-on/risk-off regimes. A "multi-asset"
  portfolio across these four is not automatically a *diversified* one —
  concurrent positions across all four could still be one concentrated
  bet on the same underlying factor. "Cross-Asset Validation" should
  explicitly measure this correlation, not assume adding symbols adds
  diversification.
- **Exchange failures**: no resilience design exists for websocket
  disconnects, API rate-limiting, or exchange maintenance windows — this
  is a live-infrastructure gap, not a backtest concern, but it is
  currently unaddressed even at the design level.
- **Partial fills**: not modeled (see Execution, above).
- **Risk management**: per-trade only; no daily loss limit, no maximum
  concurrent position count, no portfolio-level drawdown circuit
  breaker anywhere in the current architecture.
- **Monitoring**: does not exist in any form.
- **Recovery after crashes**: does not exist in any form — no state
  reconciliation against exchange truth on restart.

**Additional risks worth naming, not on the given list:**
- **Model/data drift monitoring**: no mechanism proposed for detecting,
  once live, that a certified setup's real performance is diverging
  from backtest expectations and should be automatically suspended —
  this is the live-trading analog of the out-of-sample discipline that
  should be a *continuous* practice, not a one-time pre-launch gate
  (the roadmap currently reads as linear; this discipline should be
  cyclical).
- **Tail-risk / abnormal-market circuit breakers**: no design exists
  for halting trading during a flash crash, an exchange-specific
  de-peg, or a suspicious price divergence from other venues.
- **Credential/key management**: not yet relevant since no live code
  exists, but worth flagging early rather than as a Testnet afterthought.

---

## 10. One month of research only — highest confidence gain per unit effort

Ranked by expected confidence gained per unit of effort, using
infrastructure that already exists or was just built:

1. **Extend the out-of-sample pass across all four assets, both years.**
   The dataset now exists; the methodology already exists (it just ran).
   This directly tests whether Liquidity Sweep Reversal's regime-
   dependent edge is a BTC-specific artifact or a genuine cross-market
   phenomenon — the single highest-value, lowest-new-effort research
   available right now.
2. **Build and validate an actual regime classifier**, then re-test the
   Jan–Mar/Apr–Jun split against it with a real, falsifiable hypothesis
   instead of an observed pattern. Turns "we noticed something
   suspicious" into "we have a testable claim."
3. **A transaction-cost realism audit** using whatever real trade-tape
   or order-book data can be obtained for BTC/ETH, re-running the
   already-built backtests under a conservative, data-derived cost
   overlay to see whether any certified edge survives real friction.
4. **A correlation and true-diversification analysis** across the four
   assets and across what each setup would generate on each of them —
   answering the "is this really diversification" question with data
   instead of assumption.
5. **A written monitoring & failure-mode requirements specification** —
   a design document, not code, cheap to produce, that gives the
   eventual live-infrastructure phase a concrete target to build and be
   tested against.

None of this is new coding. All of it is measurement, exactly matching
the discipline already established across this project's prior
research cycles — pointed, this time, at the questions that stand
directly between the current state and a defensible decision to risk
real capital.
