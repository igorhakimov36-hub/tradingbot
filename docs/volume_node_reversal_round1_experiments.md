# Volume Node Reversal — Round 1 Controlled Experiments

**STATUS: RESEARCH ARCHIVE.** Closed after Round 1 with the measured
conclusion below — not promoted, not rejected outright. `node_is_wide`
is a real, measured, positive single-variable finding; `value_area_
confluence` is measured redundant/mildly harmful; no tested
configuration (including the best one, Experiment B) reaches a
positive expectancy or profit factor above 1. Per explicit instruction,
S003 research is complete for now — no further optimization, tuning,
or promotion of this setup is in scope unless a future sprint reopens
it.

Research-only, exactly matching the methodology already validated on
Liquidity Sweep Reversal's own Round 1: the real, committed
`VolumeNodeReversalSetup` was never modified. Each experiment wraps it
with an external, disposable predicate that can only turn an
already-fired result into a non-fire — never invent a fire the real
setup itself did not produce. No parameter or threshold was tuned; the
two conditions tested (`node_is_wide`, `value_area_confluence`) already
existed in the committed setup as recorded-but-not-required evidence.

**Validation of the research wrapper itself** (before trusting any
experiment built on it): wrapped-setup replay against real BTCUSDT data
produced 152 fires with both confirmations required (vs. 267 unwrapped)
— non-degenerate and consistent with the setup's own previously
measured evidence-count distribution; two independent incremental
replays were byte-identical (deterministic); a single batched call
matched the final incremental-replay decision exactly. Full regression
suite: **706 passed**, same 4 pre-existing unrelated failures — zero
committed code changed this round.

---

## Experiments

| | Confirmation required |
|---|---|
| A | None (current baseline) |
| B | `node_is_wide` only |
| C | `value_area_confluence` only |
| D | Both |

Everything else identical across all four: same coordinator config
(including the live `btc_eth` SMT pair, irrelevant here but kept for
infrastructure parity), same adapter, same 1% equity risk, same fixed
2R reward, same single-setup registration, same real 30-day BTCUSDT
window (2026-08-02 → 2026-09-01).

## Comparison

| Metric | A: baseline | B: node_is_wide | C: value_area_confluence | D: both |
|---|---:|---:|---:|---:|
| Trades | 33 | 32 | 31 | 31 |
| Win Rate | 21.21% | 25.00% | 19.35% | 19.35% |
| Profit Factor | 0.411 | 0.514 | 0.364 | 0.364 |
| Expectancy | -49.75 | -40.10 | -54.05 | -54.05 |
| Average R | -0.519 | -0.408 | -0.570 | -0.570 |
| Avg Winner | 163.85 | 169.59 | 159.82 | 159.82 |
| Avg Loser | -107.26 | -110.00 | -105.38 | -105.38 |
| Net Profit | -1,641.78 | -1,283.29 | -1,675.53 | -1,675.53 |
| Gross Profit | 1,146.95 | 1,356.72 | 958.95 | 958.95 |
| Gross Loss | 2,788.73 | 2,640.01 | 2,634.48 | 2,634.48 |
| Max Drawdown | 1,891.67 (18.92%) | 1,801.14 (17.56%) | 1,919.93 (19.20%) | 1,919.93 (19.20%) |
| Recovery Factor | -0.868 | -0.712 | -0.873 | -0.873 |
| Holding Time | 18.01h | 18.48h | 17.14h | 17.14h |
| Exposure | 82.56% | 82.12% | 73.80% | 73.80% |
| Trade Frequency | 1.100/day | 1.067/day | 1.033/day | 1.033/day |

**D is numerically identical to C in every single figure** — same
trade count, same win rate, same net profit to the cent. This is not
an approximation; it is direct, measured evidence that, on this real
dataset, every trade satisfying `value_area_confluence` also already
satisfies `node_is_wide` — requiring both adds no restriction beyond
requiring `value_area_confluence` alone.

**Statistical significance** (Fisher's exact on win/loss counts,
Mann-Whitney U on R-multiples, vs. A): A-vs-B p=0.7746 (Fisher) /
0.6938 (MWU); A-vs-C p=1.0000 / 0.4399; A-vs-D p=1.0000 / 0.4399. None
of these differences are statistically significant at conventional
thresholds — reported honestly, exactly as Liquidity Sweep Reversal's
own promotion was: a measured directional effect at modest sample
size (31-33 trades), not a proven-significant one.

## Additivity / overlap — direct trade-level analysis on A's own 33 trades

| | node_is_wide=False | value_area_confluence=False |
|---|---|---|
| Excluded by B (not wide) | 2 trades (#6, #8) | — |
| Excluded by C (not confluent) | — | 16 trades |
| Excluded by both | 1 trade (#8) | |
| Excluded by neither (survive into D) | 16 trades | |

Of the 2 trades B excludes, 1 (50%) is also excluded by C. Of the 16
trades C excludes, only 1 (6%) is also excluded by B — confirming B's
excluded set is nearly a subset of C's, not an independent dimension.
Theoretical pure-filtering prediction for D (both required, applied to
A's own historical trades): 16 survive. **Actual D backtest: 31
trades** — the large gap is the same "slot re-fill" effect measured in
Liquidity Sweep Reversal's own Round 2: excluding a trade frees the
single-active-trade slot for a different signal, invisible to A, to
fire instead.

**A genuinely surprising, worth-reporting discrepancy**: within A's
own 33 trades, those satisfying `value_area_confluence` performed
*better* on average (win rate 29.4%, net -471.42, n=17) than those that
did not (win rate 12.5%, net -1,170.37, n=16) — this ex-post
categorization of A's own history suggested confluence was informative
in the *positive* direction. Yet Experiment C's actual re-run backtest
(-1,675.53) was *worse* than baseline A (-1,641.78). The explanation is
the same slot-competition dynamic: filtering live, not after the fact,
changes which signals get to fire at all — C's 31 actual trades are not
"A's 17 confluent trades," they are a different set shaped by which
slots opened up once non-confluent signals stopped taking them. This is
reported explicitly because it demonstrates that simple post-hoc
categorization of one run's own trades does not reliably predict a
live-filtered rerun's result — the same caution already established
in the S001 Round 2 report.

---

## Answers

**1. Does either confirmation improve predictive power?**
`node_is_wide`: yes, measurably — profit factor 0.411→0.514, expectancy
-49.75→-40.10, net loss reduced by 22% (-1,641.78→-1,283.29), max
drawdown reduced (18.92%→17.56%), every profitability metric moved in
the favorable direction. `value_area_confluence`: no — every
profitability metric moved unfavorably (profit factor 0.411→0.364,
expectancy -49.75→-54.05, net loss increased).

**2. Do both confirmations improve predictive power together?**
No. Experiment D is numerically identical to Experiment C — inheriting
C's worse result entirely, not a combination of B's improvement and
C's degradation.

**3. Are the improvements additive?**
No — measured directly, not assumed. Additivity would require the two
conditions to restrict different, largely non-overlapping trade
subsets; instead, `value_area_confluence`'s satisfied set is
empirically almost entirely contained within `node_is_wide`'s
satisfied set (94% of A's trades already had `node_is_wide=True`).
Combining them is not "stacking two filters," it is applying
`value_area_confluence` alone with `node_is_wide` along for the ride.

**4. Which confirmation contributes the most independent information?**
`node_is_wide`, unambiguously — it is the only one of the two that ever
improved a measured outcome in any experiment.

**5. Is one confirmation redundant?**
Yes — `value_area_confluence`. Direct evidence: Experiment D produced
an identical result to Experiment C in every reported figure, meaning
requiring both together is indistinguishable from requiring
`value_area_confluence` alone on this dataset.

**6. Does the setup now demonstrate independent edge?**
No. Even under its best measured configuration (Experiment B), the
setup remains net-negative (-1,283.29 over 32 trades), with a profit
factor below 1 (0.514) and negative expectancy (-40.10 per trade). A
measured improvement is not the same as a demonstrated edge — Round 1
found one real, positive, single-variable effect, but it is not
sufficient on its own to cross into profitability, and none of the
four measured configurations are statistically distinguishable from
baseline at conventional significance thresholds.

---

## Final Decision

**RESEARCH FURTHER**

Justification, using only what was measured this round: `node_is_wide`
is a genuine, positive, single-variable finding — parallel in kind
(though smaller in magnitude) to Liquidity Sweep Reversal's own Round 1
discovery before its permanent promotion. `value_area_confluence` is
measured to be redundant and mildly harmful, and should not be pursued
further as a gating condition for this setup. Neither an outright
REJECT nor an APPROVE is supported by the numbers: REJECT would ignore
a real, measured, favorable effect that has not yet been tried as the
setup's sole permanent condition; APPROVE is unsupported because no
tested configuration — including the best one found — reaches a
positive expectancy or profit factor above 1. The next controlled step,
should this Sprint continue, is a re-baseline of the setup with
`node_is_wide` as its one required confirmation (mirroring exactly how
Liquidity Sweep Reversal's single validated improvement was made
permanent) before any further promotion decision — not attempted here,
per this round's explicit scope.
