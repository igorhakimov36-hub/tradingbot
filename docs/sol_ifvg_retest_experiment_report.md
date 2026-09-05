# SOL IFVG + Retest Experiment — Results & Decision Report

Frozen protocol: `docs/sol_ifvg_retest_experiment_protocol.md` (hash
`a1b1c3696274c75e7f9cbb5914de7b7177d604675dd0aa4fcc3e7a1c7669b624`,
verified unchanged before this report was written). Baseline
conclusions preserved unmodified throughout (§1 of the protocol).

## Bottom line

**Unsupported candidate — both arms.** Arm A (inversion entry) and
Arm B (retest entry) are each negative in **4 of 4 TRAIN months**,
each with a month-clustered 95% CI that **excludes zero** (Arm A:
[−$23.54, −$11.26]/trade; Arm B: [−$24.37, −$6.54]/trade), and neither
result is concentration-driven (largest single trade is 1.3% of Arm
A's net, 3.5% of Arm B's — a broad, consistent negative result across
913 and 378 trades respectively, not an artifact of one bad trade).
Arm A's own closed-trade drawdown (158.7% of starting equity, pooled)
is economically disqualifying on its own. **Neither arm is
recommended for VALIDATION.**

---

## 1. Results

### Pooled (4 TRAIN months)

| | Arm A — Inversion | Arm B — Retest |
|---|---:|---:|
| n (LONG / SHORT) | 913 (461 / 452) | 378 (180 / 198) |
| Win rate | 31.5% | 31.7% |
| Profit factor | 0.720 | 0.775 |
| Net P&L (funding-inclusive) | **−$15,869.58** | **−$6,126.07** |
| Expectancy/trade | −$17.38 | −$16.21 |
| Mean net R | −0.213 | −0.166 |
| Max drawdown (closed-trade equity curve) | **$15,869.58 (158.7%)** | $6,456.97 (62.5%) |
| Median holding time | 64 min | 154 min |
| Largest trade as % of net P&L | 1.3% | 3.5% |
| +50% fees/slippage: net P&L | −$19,818.09 | −$7,576.75 |
| +50% fees/slippage: expectancy | −$21.71 | −$20.04 |
| Month-clustered 95% CI (mean trade P&L) | **[−$23.54, −$11.26]** | **[−$24.37, −$6.54]** |

**Drawdown definition** (stated per the frozen protocol): a
closed-trade equity curve starting at $10,000, peak-to-trough on
realized P&L only — this **understates** true intrabar mark-to-market
drawdown, the same disclosed limitation every prior report in this
project has carried. At Arm A's own frequency (913 trades/4 months,
~228/month) and persistent negative expectancy, the pooled drawdown
figure exceeding 100% of starting equity means a real account sized
this way would have been wiped out well before the 4-month mark — the
single most decisive number in this report.

### Per month

| Month | Arm A n / net | Arm A WR | Arm B n / net | Arm B WR |
|---|---:|---:|---:|---:|
| 2024-02 | 240 / −$5,545.10 | 27.9% | 118 / −$2,580.89 | 29.7% |
| 2024-04 | 307 / −$4,532.30 | 32.6% | 118 / −$1,892.23 | 31.4% |
| 2024-09 | 198 / −$3,042.04 | 33.3% | 77 / −$631.39 | 35.1% |
| 2025-12 | 168 / −$2,750.13 | 32.7% | 65 / −$1,021.56 | 32.3% |

**Every single month, both arms, is net negative** — the most
consistent (least mixed-direction) result of any hypothesis tested in
this project's history to date.

### Opportunity funnel (per month, from the frozen ledger)

| Month | Arm A events → trades (blocked) | Arm B events → trades (blocked) |
|---|---|---|
| 2024-02 | 241 → 240 (1) | 119 → 118 (1) |
| 2024-04 | 308 → 307 (1) | 119 → 118 (1) |
| 2024-09 | 199 → 198 (1) | 78 → 77 (1) |
| 2025-12 | 169 → 168 (1) | 66 → 65 (1) |

Essentially every confirmed event became a trade (the one "blocked"
per month is an already-open position from the immediately preceding
signal, not a systematic filter) — this is a **high-frequency**
setup by this project's own standards, not a rare-signal one; the
S007/S010-style "does it even fire enough to test" risk that applied
to several earlier candidates does not apply here at all.

---

## 2. Applying the frozen decision criteria

Per §6 of the frozen protocol: **"Unsupported candidate: consistently
negative after-cost expected value across ≥3 of 4 months."** Both arms
satisfy this at the strongest possible level (4 of 4, not merely 3),
**and** independently satisfy the disqualifying conditions the
protocol lists under "insufficient evidence" would have covered had
the result been weaker (it is not weaker — the CI excludes zero in the
negative direction for both arms, which is stronger evidence than
"insufficient," not the same thing). **Verdict: UNSUPPORTED CANDIDATE,
both arms.** No VALIDATION access is warranted or taken.

## 3. Why — read against this project's own prior findings

- **Frequency is not the problem** — both arms fire often enough to
  test cleanly, unlike several earlier hypotheses in this project's
  history that were shelved for insufficient signal frequency (S007,
  S010, S008 from the Multi-Module sprint).
- **The result is not concentration-driven** — unlike S011 (Multi-Module
  sprint), whose entire positive pooled result depended on one 41R
  trade, both IFVG arms' losses are broadly distributed (1.3%/3.5%
  concentration) — this is a **more trustworthy negative** than S011's
  positive was a trustworthy positive, precisely because it does not
  hinge on a small number of extreme outcomes.
- **Consistent with this project's own recurring finding**
  (`module_decision_register.md` §E, restated in the Multi-Module
  report): a real, implementable, causally-sound lifecycle mechanism
  (inversion and retest are both real, deterministic, well-defined
  events — proven in the implementation sprint) does not automatically
  imply a tradeable edge. The mechanism working exactly as designed
  and the mechanism being profitable are independent questions, and
  this experiment answers only the second, negatively.
- **Arm A vs. Arm B, read carefully, not as a paired comparison** (per
  the frozen protocol's own explicit instruction): Arm B's expectancy
  (−$16.21) is very slightly better than Arm A's (−$17.38), and its
  drawdown is much smaller in absolute and percentage terms — but Arm
  B trades roughly 40% as often as Arm A, on a subset of gaps that
  happened to also retest. This is **not evidence that waiting for a
  retest improves the edge** in any rigorous sense (both remain firmly
  unsupported, and the CIs overlap substantially) — it is consistent
  with, at most, "trading less produces smaller losses," which is true
  of nearly any negative-expectancy strategy and is not itself a
  finding about retest quality.

## 4. Cumulative trial disclosure (per the frozen protocol §4)

This experiment brings this project's cumulative count of
independently-tested SOL TRAIN hypotheses to approximately **21-22**
(the ~19-20 already disclosed in the Multi-Module report, plus these 2
arms). These remain exploratory, repeatedly-inspected TRAIN results,
not fresh out-of-sample evidence — stated explicitly, not omitted.

## 5. What this does and does not say about the underlying implementation

**The FVG/IFVG lifecycle implementation itself is not challenged by
this result.** Every event fired exactly where the already-proven
event-ordering tests said it would (§7 of the protocol); the negative
result is an economic finding about the trading thesis, not a defect
report about the tracker. Per the explicit distinction required by
this experiment's own design: the actual stops that closed these
trades were `ExecutionSimulator`'s own wick-based, intrabar checks —
`is_failed`/`inversion_expired` remained descriptive throughout and
were never the mechanism that ended a trade.

---

## 6. Test results and changed files

**Full suite: 1223 passed, 0 failed** (1213 prior + 10 new adapter
tests). All pre-existing FVG/IFVG/S005 tests pass unmodified.

Changed/added files (all uncommitted):
- `strategy/research/ifvg_retest_adapter.py` (new) — the research
  integration (§2 of the protocol).
- `strategy/research/ifvg_retest_backtest.py` (new) — the frozen
  backtest driver; run via `python -m strategy.research.ifvg_retest_backtest`.
- `tests/test_ifvg_retest_adapter.py` (new) — 10 focused tests (event
  timing, direction both ways, no-duplicate-refire, retest
  precondition, cooldown, failed-gap exclusion, state isolation,
  non-retroactive attribution, stop/target construction).
- `docs/sol_ifvg_retest_experiment_protocol.md` / `.sha256` (frozen,
  hash verified unchanged throughout).
- `docs/sol_ifvg_retest_experiment_report.md` (this document).

**Result ledger, saved in a documented, recoverable project location**
(not scratchpad-only): `strategy/research/ifvg_retest_results.pkl` —
contains, per arm per month, the full trade list (with funding-adjusted
P&L) and the complete opportunity ledger (every confirmed event,
`became_trade` flag included). Reproducible in full by re-running the
driver above against the same, already-authorized TRAIN data.

No production file was modified. Progressive-stop Policy D and S001's
own stop logic were not touched. No VALIDATION/SECONDARY_VALIDATION/
FINAL_HELD_OUT data was accessed.

---

# PART B — Targeted AlgoAlpha Comparison

Analytical only, per the authorizing instruction: **no change to
liquidity detection, no incorporation into Part A** (already frozen
and concluded above). Source code was supplied directly and is
compared as actual code, not inferred from a screenshot — the
Patternsmart link is used, per instruction, only for its public
description context; its protected source was not obtained and does
not block this comparison.

## B1. What AlgoAlpha "Liquidity Sweep Filter" actually computes (source-verified)

**Trend/regime filter**: `basis = SMA(EMA(src, len), len)`,
`deviation = EMA(|close - basis|, len*3) * mult`, bands =
`basis ± deviation` — a **Keltner-style, mean-absolute-deviation band**,
not ATR-based and not related to our own BOS/CHoCH swing-structure
regime at all. `trend` flips only when **close** crosses fully outside
a band. This is a materially different regime concept from anything in
`strategy/market_structure.py` or `strategy/features/market_structure_tracker.py`.

**Pivot confirmation timing and swing sensitivity**: `peakform`/
`valleyform` are a plain **3-bar fractal** (`high[1] > high and
high[2] < high[1]`) — the *same* sensitivity class as our own
`find_swing_high`/`find_swing_low` (`strategy/market_structure.py`),
confirmed by direct comparison, not the MSB-OB script's
parameterized-lookback ZigZag reviewed earlier. **This is a genuine
point of similarity, not a difference**, between AlgoAlpha and our own
existing swing detection.

**Trend-conditioned liquidity tracking — the one genuinely new
mechanism here**: a swing high is only ever recorded as a liquidity
candidate **while `trend < 0`** (a downtrend, per AlgoAlpha's own band
filter) **and** its own high sits below the current upper band (`high[1]
< upper`); the mirror for swing lows requiring `trend > 0`. **Our own
Liquidity Pool module tracks equal-highs/lows, session extremes, and
round numbers with no trend-conditioning of any kind** — this is a
genuinely new hypothesis, not a repeat of anything in the completed
Liquidity Pool lifecycle series (which tested geometry, touch count,
volume, and staleness — never regime-conditioning of which pivots
count as liquidity in the first place).

**Sweep/reclaim vs. breakout — a confirmed, consequential
definitional difference**: removal/"sweep" fires on `high > lineLevel`
**alone** — there is **no requirement that price close back below the
level**. This is a **breakout/breach definition**, not the
reject-and-reverse definition our own `LiquidityPool.check_sweep`
requires (`candle.high > zone_high AND candle.close < zone_high`).
AlgoAlpha's own "liquidation swept" event fires on simple level
penetration; ours requires the specific rejection shape S001's entire
reversal thesis depends on. These measure genuinely different things
and are not interchangeable definitions of the same word.

**A second, independent removal trigger not tied to price action at
all**: a peak/valley line is also discarded if the band's own boundary
moves past it (`upper < lineLevel`) — a "regime made this level
contextually stale" rule with no equivalent in our own system (which
prunes only by age or by an actual sweep/fill/mitigation event, never
by an unrelated indicator's own drift).

**What the displayed volume/"liquidation" numbers actually measure**
(verified directly, not inferred): `aPeakVols`/`aValleyVols` store
**the volume of the candle that originally formed the swing pivot** —
not the volume of the breakout candle, not a measure of actual forced
liquidations. Labeled "liquidation" in the script's own alert text and
display, this is a **relabeling of ordinary OHLCV volume**, not a new
data source. This is fully consistent with, and does not update, the
SOL strategic review's own already-established finding
(`docs/sol_strategy_edge_strategic_review.md` §3.2): no genuine
reported-liquidation data source has been found or purchased in this
project, and nothing here changes that — AlgoAlpha's own "liquidation"
figures are computed from the same OHLCV this project already has,
under a different name.

**Duplicate events, overlapping levels, historical plotting**: removal
iterates the line arrays **backward** (`for ln = qt-1 to 0`) while
removing by index — the **safe** direction for in-place removal during
iteration (each removal only invalidates indices already visited),
unlike MSB-OB's own forward-iteration-with-front-shift defect found in
the prior comparison. **No code defect was found in this script.**
Arrays are FIFO-capped at 500, a bound comparable in spirit to this
project's own `max_tracked_*` conventions, coupled directly to the
display object rather than a separate internal record — a reasonable
Pine-specific pattern, not a design worth importing given our own
already-separated state/rendering architecture.

**Volume-percentile normalization (`major_sweep_thresh`)**: a rolling
min-max percentile over a `len*mult`-bar window, applied to
**formation-time** volume. This is **closely related to, but not
identical to**, the already-tested-and-rejected D5 hypothesis
(`module_decision_register.md`: "Do not promote normalized Volume as a
filter") — D5 tested a causal trailing-median relative-volume baseline
applied to **sweep-time** volume on the Liquidity Pool's own candidate
population, a different population and a different moment than
AlgoAlpha's own formation-time measure. Per the explicit instruction
not to let a prior null result on an isolated factor settle a
different interaction: **this is not conclusively the same question
as D5**, but it is close enough that any future test of it should be
designed to distinguish "is this D5 again under a new name" from "is
this a genuinely new signal" before drawing a conclusion either way.

**Volume profile display**: a standard volume-by-price histogram,
recomputed by nested loops every bar over the candle range since the
last trend-filter flip — conceptually adjacent to (but windowed
differently from) our own session-based Volume Profile module.
Recomputing a full O(resolution × leg-length) histogram from scratch
every bar, with no incremental caching, is a real performance
consideration for this script's own design, not something to import
as-is even if the underlying "profile since last regime flip" concept
were pursued.

## B2. Distinguishing source-verified findings from visual inference

Everything in B1 is a direct claim about the supplied code, verified
by reading it — no screenshot, no chart image, and no inference from
UI behavior was used for this comparison (unlike the necessarily
partial Nephew_Sam_ comparison, where only screenshots were available).

## B3. Recommended follow-up hypothesis (at most one, per instruction)

**Regime-conditioned liquidity tracking** — testing whether gating
which Liquidity Pool pivots are even considered "liquidity" by a
trend/regime filter (analogous to AlgoAlpha's own trend<0-for-highs /
trend>0-for-lows rule, though not necessarily using AlgoAlpha's exact
Keltner-style band) changes S001's own signal quality — is the single
genuinely new, not-previously-tested idea this comparison surfaced.
This is **not** the breakout-vs-reject question (that is a
definitional choice already correctly resolved in our own favor by
S001's own institutional logic, not an open question) and **not**
simply D5 again (per B1's own caveat, though the two should be
explicitly distinguished if this is ever pursued). **Not started here**
— this is a recommendation for a future, separately-authorized,
frozen research sprint, following this project's own standing
discipline (signal-frequency check first, frozen protocol before
outcomes, TRAIN-only).

## B4. Explicit confirmations

No liquidity detection code was modified. AlgoAlpha was not
incorporated into Part A, which was already frozen and concluded
before this section was written. No new backtest, optimization, or
market-data period was used for Part B. All new work from both parts
remains uncommitted for review.
