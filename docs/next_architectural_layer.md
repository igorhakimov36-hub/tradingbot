# What's Next — An Independent Technical Assessment

Written as if this were my own project, inheriting it exactly as it
stands today. Not a continuation of the prior roadmap — a challenge to
it, where the evidence warrants one.

---

## The headline finding

Five independent research cycles (S002–S005, plus the Portfolio
Decision Engine research) have all converged on the same root cause:
**the system can hold exactly one position at a time**, and every
setup's own standalone quality is irrelevant to whether it gets to act
— only whether its signal happens to arrive while the single slot is
free. This is a resource-scarcity problem, not an information problem,
and it is currently the ceiling on everything downstream of it.

A second, quieter finding sits underneath all of it: **every backtest
in this project has been run on the same single 30-day window.**
`WindowManager`'s `TRAIN`/`VALIDATION`/`HELD_OUT` split has existed
since Phase 0 and has never been used for its purpose. Every
promotion/rejection verdict so far is a statement about one month of
price action.

These two findings, not "which setup should we build next," are what I
would act on first.

---

## Candidate directions, evaluated

### A. Out-of-sample re-validation of the existing Setup Library
**What:** re-run S001–S005 against the already-present, unused 2024
monthly data (`BTCUSDT-1m-2024-01.csv` … `-06.csv`), using the
`WindowManager` split that already exists in the codebase.
**Benefits:** nearly free — no new infrastructure, no new code beyond
pointing the same, already-validated pipeline at different data;
directly answers whether any of the five keep/discard verdicts
generalize, or were shaped by this one window's idiosyncrasies; costs
a day, not a month.
**Risks:** almost none technically; the only "risk" is finding out an
approved setup doesn't hold up, which is exactly the kind of finding
this research platform exists to surface, not to avoid.
**Long-term impact:** every subsequent decision (what to build, what
to promote to live) inherits whatever confidence this step establishes
or undermines. Skipping it means building on an unverified foundation.
**Blocks future work:** not directly, but it should gate confidence in
everything else — deploying an "approved" setup live on the strength of
one month's backtest would be a mistake regardless of what else gets
built.
**Verdict: do this first, before committing to a month of engineering
on anything else.**

### B. Multi-position execution (concurrent trades)
**What:** replace `BacktestRunner`'s single `active_trade: SimulatedTrade
| None` with support for N concurrent positions, so setups no longer
share one slot.
**Benefits:** directly attacks the measured, dominant bottleneck (30–
55% cross-bar crowding vs. 0–1.3% same-bar conflicts); for the first
time, a "combined portfolio" backtest would measure genuine interaction
effects (correlated drawdowns, diversification) instead of measuring
resource contention; unlocks every setup's own already-measured
standalone quality (S001 and S005 both hover near breakeven standalone
— that signal is currently being destroyed by the slot mechanism, not
by the setups).
**Risks:** the largest, most invasive change proposed here — touches
`ExecutionSimulator`, `TradeJournal`, and `BacktestRunner`, all
previously stable, heavily-relied-upon infrastructure; real correctness
risk (P&L accounting across concurrent positions, replay-safety of
concurrent state, look-ahead risk if not built as carefully as every
tracker before it) that demands the same full validation rigor
(determinism, incremental/batched replay, regression) applied to a much
larger surface area than any single tracker.
**Long-term impact:** mandatory, not optional, for the stated
destination. No serious multi-strategy live book runs one trade system-
wide; this is infrastructure that has to exist before "fully automated
live trading" is a coherent goal, not a nice-to-have.
**Blocks future work:** yes, heavily — a meaningful risk engine, capital
allocation across setups, and honest portfolio backtesting are all
either trivial or meaningless without it.
**Verdict: the highest-leverage architectural investment available
right now.**

### C. Portfolio-level Risk Engine
**What:** aggregate exposure caps, max concurrent positions, a
portfolio-level risk budget (not just 1% per trade with no ceiling on
how many trades stack), a drawdown circuit breaker.
**Benefits:** the safety layer multi-position execution cannot safely
ship without — uncapped concurrent 1%-risk trades across five setups
firing together is a real blow-up scenario the current architecture
doesn't need to worry about only because it structurally can't happen
yet.
**Risks:** moderate engineering effort; conceptually simpler than B,
but the two are tightly coupled — building B without C is genuinely
dangerous, not just incomplete.
**Long-term impact:** mandatory for live trading, for the same reason
B is — this is closer to a prerequisite than an enhancement.
**Blocks future work:** blocks any responsible path to live capital,
regardless of how good the Setup Library is.
**Verdict: build alongside B, not after it — treat B and C as one
paired milestone, not two sequential ones.**

### D. Portfolio Decision Engine (as designed last turn)
**I need to walk this back.** The design is sound architecture, but I
now think I scoped it against the wrong problem. As specified — sitting
on top of the *existing* single-slot engine — it can only resolve the
0–1.3%-of-bars case where two setups fire simultaneously. The 30–55%
cross-bar starvation case, which every measurement says is the actual
problem, is invisible to it by construction (`BacktestRunner` never
even calls `strategy_callback` while a trade is open).
**Where it still matters:** once B and C exist, a *different*, smaller
version of this problem reappears — a risk budget will eventually be
full while more signals fire than it can admit. That's a legitimate,
narrower arbitration problem, and the design from last turn (context
object, ledger, explicit policies) is the right shape for it. But it
becomes a component of the Risk Engine's *admission control*, not a
replacement for "which setup wins the one slot in the whole system."
**Verdict: real value, wrong sequencing. Build it as part of C, sized
to the actual remaining problem, not as an independent milestone before
B and C exist.**

### E. Setup Performance Ledger
**What:** point-in-time-safe, per-setup running expectancy/drawdown,
fed only by the Trade Journal's own past closed trades.
**Benefits:** legitimate, well-scoped, independently testable.
**Risks:** low, if built with the same replay-safety discipline as
every tracker.
**Long-term impact:** genuinely useful for future capital-allocation
decisions (should setup X get a larger or smaller share of the risk
budget).
**Blocks future work:** not urgently — its main use case (deciding
between competing signals for a scarce resource) shrinks once B exists,
and grows again once C's risk-budget admission control needs it.
**Verdict: sequence after B/C, build when the Risk Engine's admission
logic actually needs it, not before.**

### F. Setup Retirement / Lifecycle Framework
**What:** formalize what's already happening ad hoc — APPROVED /
RESEARCH ARCHIVE / REJECTED, plus a required periodic re-validation
policy for anything APPROVED (regime drift is real; an approved setup
today isn't guaranteed to still be approved in six months).
**Benefits:** good hygiene, makes the project's own history legible
without re-reading five separate reports.
**Risks:** essentially none.
**Long-term impact:** modest — this is documentation and process, not
new capability.
**Blocks future work:** no.
**Verdict: low effort, do it eventually, not urgent. A half-day task,
not a month.**

### G. Live infrastructure / Binance integration
**What:** exchange connectivity, order placement, live market data,
eventually real capital.
**Benefits:** it's the stated destination, and the plumbing itself
(auth, rate limits, websockets, reconnection) is well-understood,
solved engineering — genuinely low research risk in isolation.
**Risks:** doing this now means connecting real (or even testnet) order
flow to a system with no risk engine, no concurrent-position support,
and no out-of-sample-confirmed edge. That's building the delivery truck
before there's a product worth delivering — the risk isn't in the
exchange integration itself, it's in what it would be shipping.
**Long-term impact:** necessary eventually, provides zero value now.
**Blocks future work:** no — nothing else depends on this existing yet.
**Verdict: correctly last. When it does happen, gate it behind a
live-vs-backtest parity test suite (does the live path reach identical
decisions to a backtest replaying the same data) before any real
capital, and start on testnet regardless.**

### H. Signal queue / trade scheduling
**What:** infrastructure for queuing/prioritizing signals in a live
setting.
**Verdict: premature. This is a live-infrastructure concern (G) that
doesn't exist as an independent problem until G is actually reached —
folding it into G's design later costs nothing; building it now would
be solving for constraints (live latency, exchange rate limits) the
backtest environment doesn't have.**

### I. Building S006 and beyond
**I believe this is currently a mistake, and I want to say so
directly, as asked.** Not because setup research lacks value in
principle — the methodology built across S001–S005 (controlled
experiments, signal-overlap analysis, honest APPROVED/ARCHIVE/REJECTED
verdicts) is genuinely strong work and shouldn't be abandoned. But
right now, every new setup does two things, both counterproductive: it
adds another contender to a resource-contention problem already proven
to dominate outcomes more than setup quality does, and it produces
another verdict resting on a single, never-cross-validated window (see
Finding A). Building S006 today would very likely just reproduce the
same "each is fine, together they degrade" pattern for a sixth time,
teaching us little we don't already know, while the two things that
would actually change the picture — concurrency and out-of-sample
validation — remain undone. **Pause new setups until B and C exist,
and until A has actually run.**

---

## Ranked roadmap

| Rank | Milestone | Engineering effort | Research value | Architectural value | Contribution to live trading |
|---|---|---|---|---|---|
| 1 | **A. Out-of-sample re-validation** | Low (~1 day) | Very High | Low | High — nothing else should be trusted without this |
| 2 | **B. Multi-position execution** | High | Very High | Very High | Mandatory |
| 2 (tied, paired) | **C. Portfolio-level Risk Engine** | Medium-High | Medium | Very High | Mandatory |
| 4 | **D. Portfolio Decision Engine (rescoped as risk-budget admission control)** | Medium | Medium | Medium | Contributory |
| 5 | **E. Setup Performance Ledger** | Low-Medium | Medium | Low-Medium | Contributory |
| 6 | **F. Setup Retirement / Lifecycle Framework** | Low | Low | Low | Low |
| 7 | **G. Live infrastructure / Binance integration** | High | Low (well-understood problem) | Medium | Necessary eventually, zero value now |
| 8 | **H. Signal queue / trade scheduling** | — | — | — | Folds into G when reached |
| — | **I. New setups (S006+)** | — | — | — | Paused, not ranked — see above |

**The month I'd actually spend:** day one on A; the remainder on B and
C together, as one paired milestone, because shipping concurrency
without a risk budget is not a version of this I'd be comfortable
running even in a backtest, let alone toward the stated destination of
live capital.
