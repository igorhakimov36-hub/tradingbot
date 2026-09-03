# Portfolio Decision Engine V1 — Architecture Research

Design only. No code was written, no existing file was modified —
`strategy/strategy_engine_v2.py`, every `strategy/setups/*.py`, and
`backtesting/backtest_runner.py` are exactly as they were before this
document. Every claim below cites the actual current source, not
intended behavior.

---

## Part 1 — Where slot competition occurs (traced in the real code)

Two genuinely distinct mechanisms exist today, and they have been
conflated in discussion so far. Separating them is the single most
important finding of this research.

### 1a. Within-bar competition — resolved today by silent registration order

`strategy_engine_v2.py::engine_decision_to_dict()`:

```python
if not decision.fired_setups:
    return {"decision": "IGNORE", ...}
result = decision.fired_setups[0]   # <- the ONLY tie-break rule that exists
```

`StrategyEngineV2.decide()` evaluates every registered setup and keeps
`fired_setups` in registration order. When two or more fire on the same
bar, everything except index `[0]` is silently discarded — not ranked
lower, discarded. `all_results` (which does contain every setup's full
`SetupResult`, fired or not) is computed but never returned to the
caller in more than this one-setup slice, so the Trade Journal has no
record that a second setup also fired that bar. Measured frequency of
this specific situation across every pairing tested so far: 0.00%–1.32%
of bars (S004's `all_three` was 0.00%; S005's `all_three` was 0.03%;
same-pair co-fires topped out at S005's `fvg_ob` at 1.32%). This
mechanism is real but rare in the data measured to date.

### 1b. Cross-bar competition — the dominant, measured effect

`backtesting/backtest_runner.py::run_strategy()`'s `on_replay_step`:

```python
if active_trade is not None:
    ...
    return          # <- market_snapshot and strategy_callback are NEVER reached
if pending_order is not None:
    ...
    return
# only past this point does the strategy get asked for a decision at all
context = ReplayContext(...)
market_snapshot = self._build_market_snapshot(...)
decision_result = strategy_callback(current_candle, market_snapshot)
```

While any trade is open (or an order is pending), **the entire chain —
Coordinator sync, every setup's `.evaluate()`, the Portfolio Decision
Engine itself — is skipped, not merely deprioritized.** A setup whose
genuinely good opportunity appears on bar 500 while a different
setup's trade from bar 480 is still open never gets a chance to be
compared, ranked, or even recorded as missed. (One clarification worth
stating precisely: this does not corrupt Market Intelligence itself —
`MarketIntelligenceCoordinator.sync_and_build()`'s internal one-candle-
at-a-time catch-up loop, already validated for batched growth in Step
0/Step 2, correctly processes however many bars accumulated once
`strategy_callback` is finally called again. Trackers stay correct;
only the *decision* opportunity is lost, for however many bars the
slot was occupied.)

**Direct measured evidence of this mechanism, from every research
report so far:**

| Report | Crowded-out relationship | Measured |
|---|---|---|
| S002 (Order Block) | Of LSR's 13 standalone trades, crowded out by OB in combined run | 7 (54%) |
| S003 (Volume Node) | Of Portfolio's 60 standalone trades, crowded out by VNR | 34 (57%) |
| S003 (Volume Node) | Of VNR's 33 standalone trades, crowded out by Portfolio | 15 (45%) |
| S004 (SMT) | Of Portfolio's 60 standalone trades, crowded out by SMT | 19 (32%) |
| S004 (SMT) | Of SMT's 67 standalone trades, crowded out by Portfolio | 33 (49%) |
| S005 (FVG) | Of Portfolio's 60 standalone trades, crowded out by FVG | 25 (42%) |
| S005 (FVG) | Of FVG's 60 standalone trades, crowded out by Portfolio | 29 (48%) |

Every single expansion setup measured so far both *causes* and
*suffers* roughly 30–55% mutual crowding with whatever else is
registered — this is not noise, it is the structural signature of a
single shared resource under contention.

---

## Part 2 — Why independently useful setups can still reduce portfolio performance

Frame the trade slot as a single server; each setup is a request stream
with its own arrival rate (signal frequency) and service time (holding
time). Their product is *offered load* — which this project has
already been measuring directly under the name **Exposure %** in every
comparison table:

| Setup | Measured exposure (standalone) |
|---|---|
| Liquidity Sweep Reversal | 26.35%–27% |
| Order Block Continuation | ~71% |
| Volume Node Reversal | 70–83% |
| SMT Reversal | 70–81% |
| Fair Value Gap Rebalance | 70–82% |

The moment two setups whose *individual* offered load each approaches
70–80% are registered together, contention is inevitable by
construction — the shared resource caps at 100%, and several
candidates individually demand most of it. This is a resource-scarcity
fact, not an information-quality fact. Combined with Part 1b's
mechanism (a setup's realized trade count is not proportional to its
edge, it is proportional to *its own fire frequency times the fraction
of bars where nothing else happens to be occupying the slot*), the
result is allocation that is **blind to quality**: whichever setup's
signal happens to arrive while the slot is free wins that specific
opportunity, regardless of whether a better setup's signal would have
appeared moments later.

This precisely explains S005's most striking finding: Fair Value Gap
Rebalance measured the *best standalone result of any setup built*
(profit factor 0.992) — combining it with the Approved Portfolio (0.988
standalone) still produced a *worse* combined result (0.947) than
either alone. Slot competition does not protect the objectively better
setup's opportunities; it protects whichever setup's clock happens to
line up with a free slot.

---

## Part 3 — Portfolio Decision Engine V1: architecture

### Placement

```
Market Intelligence
      |
      v
Setup Evaluation           (StrategyEngineV2.decide() -> EngineDecision, unchanged)
      |
      v
Portfolio Decision Engine   (NEW - replaces engine_decision_to_dict()'s
      |                      hardcoded fired_setups[0])
      v
Trade Setup                 (backtest adapter, unchanged interface)
      |
      v
Backtest
```

### What it must never do

- Never import `strategy.features.*` or `strategy.market_intelligence_coordinator` — the same structural boundary already verified (via AST-parsing test) for `StrategyEngineV2` itself extends to this layer.
- Never carry setup-specific logic — it must be able to arbitrate between any registered setups without special-casing a name.
- Never mutate a `SetupResult` — a chosen result is passed through unchanged, exactly like today's `fired_setups[0]` is passed through unchanged.

### Interface

The engine's core function is a pure decision over what it is given:

```
decide(context: PortfolioDecisionContext) -> SetupResult | None
```

`PortfolioDecisionContext` is the answer to Issue 2 above — an explicit,
narrow bundle of plain data the *caller* (the backtest adapter, which
already legitimately reads the snapshot for journal metadata today)
assembles and hands in. The engine treats every field as an opaque
value; it does not know or care how any of them were computed:

- `results: list[SetupResult]` — `EngineDecision.all_results`, not just `fired_setups`. Passing the *unfired* results through as well is what makes "reject conflicting directions" and any future "why didn't setup X fire" analysis possible without a second computation.
- `timestamp`, `symbol` — already on every `SetupResult`, included for convenience.
- `regime: str | None` — optional, forwarded from `snapshot.structure.get("market_structure")`, exactly the field the adapter already reads today for journal metadata. This is the minimum viable resolution to Issue 2: the *adapter* still touches the snapshot (as it always has), the *engine* never does.
- `ledger: SetupPerformanceLedger | None` — optional, a new, narrowly-scoped read-only object (see below), never Market Intelligence.

### `SetupPerformanceLedger` — a new, clearly-bounded component

Several proposed policies (historical expectancy, recent drawdown) need
a running per-setup performance record. This must be built with the
exact same replay-safety discipline as every tracker in this project,
fed **exclusively by the Trade Journal's own past CLOSED entries** —
never by Market Intelligence, never by anything not yet known at
decision time:

- Input: `TradeJournal.closed_trades()`, filtered by `setup_name`, restricted to entries with `timestamp < current decision timestamp`.
- Output per setup: a small set of already-established, already-computed statistics this project already knows how to calculate honestly — win rate, expectancy, recent drawdown over a fixed trailing window — using the exact same formulas `analytics/performance.py` already uses, not new math.
- This is itself a new, independently validatable object: it needs its own replay-safety/determinism/incremental-vs-batch tests before any policy built on it can be trusted, exactly like `MarketStructureTracker` needed before Liquidity Sweep Reversal could read it.

### Output contract — no change downstream

The engine returns one `SetupResult | None`. `engine_decision_to_dict()`
downstream needs no change: it already knows how to turn one
`SetupResult` into the adapter's dict shape. `BacktestRunner` needs no
change either — it still receives the exact same `{"decision": ...}`
shape it does today.

---

## Part 4 — Candidate decision policies

Each is a rule for choosing one `SetupResult` from `context.results`
(restricted to `fired=True` unless noted). None are implemented here.

### First valid setup (status quo)
**Design:** the current, implicit rule — first fired in registration order.
**Pros:** already proven, zero new state, deterministic, zero risk of
introducing a bug into a currently-working system.
**Cons:** arbitrary — registration order has no relationship to
quality; this is the exact mechanism Part 1a and 1b describe as the
source of the measured problem, made explicit rather than fixed.
**Role in V1:** the mandatory control condition every other policy is
measured against, not itself a proposal for change.

### Highest evidence count
**Design:** among fired results, prefer the one with the highest
`evidence_count`.
**Pros:** reuses data every setup already produces, zero new
computation or state, keeps the existing "descriptive count, never a
weight" philosophy intact for a single setup — it becomes a *ranking*
across setups here, which is a new use, but the underlying number is
unchanged.
**Cons — measured, not speculative:** `evidence_count` is not
comparable across setups. Its maximum differs per setup (3 for LSR, 2
for every other setup), and its own discriminating power has already
been measured to vary wildly — S004's SMT evidence was satisfied 2/2 on
**100% of 190 real fires** (proven non-discriminating), while S003's
VNR evidence showed one condition (`node_is_wide`) true 94% of the time
and the other genuinely mixed. A raw cross-setup comparison of this
field would be comparing numbers that don't mean the same thing.
**Verdict:** usable only as a *same-setup* tie-break, not a cross-setup
ranking, given what's already measured.

### Highest historical expectancy
**Design:** among fired results, prefer the setup with the best
`SetupPerformanceLedger` expectancy as of just before this bar.
**Pros:** directly ties the decision to measured, point-in-time-safe
quality; adapts as more trades accumulate; the most direct answer to
"give the slot to whichever setup has actually been better."
**Cons:** cold-start problem (a setup with 0–2 closed trades has no
reliable expectancy — needs an explicit fallback, e.g. defer to "first
valid" until a minimum sample size is reached); non-stationarity (a
setup's true edge can drift — S001's own permanent change already
demonstrated one setup's edge changing after a single architecture
tweak); and this is exactly the kind of statistic that must be
developed on TRAIN and confirmed on HELD_OUT, not fit and judged on the
same window it's tested on (see Part 5).

### Lowest recent drawdown
**Design:** among fired results, prefer the setup currently *least* in
a losing streak (smallest trailing-window drawdown from its ledger).
**Pros:** a risk-first framing — avoid feeding the slot to a setup that
is currently bleeding, independent of its long-run average.
**Cons:** reactive by construction — a setup emerging from a drawdown
right as it's about to recover would be penalized at exactly the wrong
moment (a well-known risk in any recency-based allocation rule); the
trailing-window length is itself a choice that must be fixed by
principled default and never swept/tuned per the standing "do not
optimize" instruction, or this policy becomes curve-fitting by another
name.

### Reject conflicting directions
**Design:** if the fired set (on a bar where multiple fire) contains
both LONG and SHORT, take neither — IGNORE the bar entirely.
**Pros:** the cheapest policy to reason about and to validate (see
Part 5); directly targets a real, already-measured phenomenon — when
setups *do* coincide, they disagree on direction 18–84% of the time
across every pairing tested (S003: 67%, S004: 84%, S005: 47%);
institutionally sound ("if our own modules disagree, stay out" is a
defensible discipline, not merely a technicality).
**Cons:** does nothing for the dominant cross-bar problem (Part 1b) —
same-bar co-fires are 0–1.3% of all bars measured so far, so this
policy's addressable surface is small; it also discards potentially-good
trades where one setup was simply right and the other wrong, gaining
safety at the cost of some real opportunity.

### Confidence ranking (composite score)
**Design:** blend multiple signals (evidence_count, ledger stats,
recency) into one numeric confidence score per fired setup, rank by it.
**A direct tension with this project's own founding decision**: Phase
2's architectural review replaced the old Decision Engine specifically
*because* it was a hand-weighted composite score with no way to
attribute which sub-signal drove a decision (`strategy/setups/base.py`'s
own docstring: "no arbitrary numeric weights anywhere... never a
weighted composite pretending to be a probability"). Building a
cross-setup composite score here would reintroduce exactly the pattern
this platform exists to move past, one layer higher up the stack.
**Recommendation:** do not build this as a blended number. If ranking
by multiple signals is wanted, use an explicit, ordered, lexicographic
tie-break (e.g., "prefer higher ledger expectancy; if tied, prefer
higher evidence_count; if still tied, prefer earlier registration
order") — each step remains individually inspectable and attributable
in the reasoning chain, unlike a single blended score.

### Portfolio diversification preference
**Design:** when multiple setups fire, prefer whichever has been *least*
represented in recently-taken trades, actively rotating exposure rather
than letting the highest-frequency setup dominate by base rate.
**Pros:** directly targets the measured root cause (Part 2) rather than
a symptom — it's the one policy that explicitly tries to counteract
offered-load dominance rather than just picking a "better" winner
within it.
**Cons:** hardest to define rigorously — "diversification" needs an
operational definition (setup identity? realized-return correlation?
regime spread?) before it's testable at all; and it creates a real,
undisguised tension with profit-seeking — deliberately handing the slot
to a rarer, possibly genuinely worse setup purely because it hasn't
fired recently could reduce returns even as it "diversifies," and that
trade-off should be measured explicitly, not assumed away.

### Regime specialization
**Design:** route the slot to whichever setup has historically
performed best in the *current* regime (`context.regime`), when
multiple fire.
**This is the policy that surfaced Issue 2** — it cannot be built from
`SetupResult` alone; it requires `context.regime`, which is why the
interface in Part 3 threads it through explicitly rather than letting
the engine reach for it itself.
**Pros:** reuses a Market Intelligence field that has never gated a
single decision so far (the audit confirmed `structure["market_
structure"]` is read only for post-hoc journal metadata today);
plausible given some qualitative pattern already noted in earlier
research (regime-restricted filtering came up in the very first Round 2
experiments on Liquidity Sweep Reversal).
**Cons:** regimes are coarse (a handful of categories over a 30-day
window), so per-regime, per-setup sample sizes will be small —
compounding the same small-sample caution already flagged repeatedly
in every prior report's statistical tests (Fisher/MWU underpowered
below n=8).

---

## Part 5 — Validation plan (no curve-fitting, no leakage)

Principles that apply to every policy, restated from the discipline
already used across S001–S005 and extended to this new layer:

1. **Point-in-time safety is non-negotiable and now applies to a new
   component.** `SetupPerformanceLedger` must be built and tested with
   the identical replay-safety checklist as every tracker before it:
   determinism, incremental replay, batched-vs-incremental equivalence.
   A ledger that can see a trade's outcome before that trade has closed
   is a leak, full stop.
2. **Single-variable controlled experiments**, exactly the Round 1/2
   methodology already run five times: hold the Approved Portfolio and
   candidate setup registration fixed, change only the arbitration
   rule, compare against the "first valid" control.
3. **Use the three-window split for the first time for real.** Every
   setup built so far had zero fitted parameters, so TRAIN vs VALIDATION
   vs HELD_OUT never mattered much. A policy with accumulating state
   (expectancy, drawdown ranking) is exactly the situation this split
   exists for: develop and sanity-check on TRAIN, measure provisionally
   on VALIDATION, and treat any promotion decision as contingent on
   HELD_OUT confirming the same direction — not merely re-running the
   same window twice.
4. **Same statistical rigor already established**: Fisher's exact on
   win/loss counts, Mann-Whitney U on R-multiples, explicit
   "[UNDERPOWERED]" disclosure below n=8 per arm, promoted on measured
   direction rather than proven significance — the same standard that
   promoted Liquidity Sweep Reversal's own confirmation gate.
5. **Direct trade-level attribution**, the same set-based methodology
   already used for every crowding analysis: for a candidate policy,
   identify exactly which trades it keeps, drops, and newly admits
   relative to "first valid," not just the aggregate metric delta.
6. **No parameter sweeps in this phase.** Any policy needing a constant
   (a trailing window length, a minimum sample size for cold-start) uses
   one principled default, documented with its reasoning, exactly once
   — sweeping it to find the best value is the exact curve-fitting this
   project has repeatedly been instructed to avoid.

Per-policy validation feasibility, measured against what's already known:

- **First valid**: no new validation — it is the control.
- **Highest evidence count**: testable only within-bar; given measured
  co-fire rates of 0–1.3% of bars, the addressable sample across a
  30-day window will likely be single digits — flagged now so a null
  result isn't mistaken for a negative finding rather than a power
  problem.
- **Highest historical expectancy / Lowest recent drawdown**: gated on
  building and independently validating `SetupPerformanceLedger` first;
  only then a TRAIN→VALIDATION→HELD_OUT comparison, as above.
- **Reject conflicting directions**: cheapest to test — answerable
  largely from data already collected in the existing S002–S005
  backtests (their journals already contain every co-fire bar) without
  a new backtest run.
- **Confidence ranking**: not recommended for construction as a blended
  score at all, per Part 4; if a lexicographic variant is built instead,
  validate each rung of the tie-break independently, in the order it's
  applied.
- **Portfolio diversification preference**: requires defining a new
  portfolio-level metric before any test is possible — the most
  research-heavy proposal, not a same-cycle validation candidate.
- **Regime specialization**: requires resolving the `context.regime`
  interface (already specified in Part 3) plus explicit small-sample
  caution per regime × setup cell before trusting any comparison.

---

## Part 6 — Open questions before any implementation

Not answered here, since this document is design-only, but should be
resolved before a V1 is coded:

1. Does V1 ship with only "first valid" and "reject conflicting
   directions" (the two policies with no new infrastructure and the
   cleanest validation path), leaving ledger-dependent and regime-
   dependent policies for a V1.1 once `SetupPerformanceLedger` exists
   and is independently validated?
2. Is the cross-bar starvation problem (Part 1b) — measurably the
   dominant effect, at 30–55% mutual crowding versus 0–1.3% same-bar
   co-fires — explicitly scheduled as a separate, future `BacktestRunner`
   research task, given it cannot be solved by this layer alone?
3. Should "missed opportunities" during an open position at least be
   *logged* (Setup Evaluation still run for observation, execution
   behavior unchanged) even before any execution-side change is made,
   so the next research cycle has real missed-opportunity data instead
   of having to infer it indirectly the way this document did?
