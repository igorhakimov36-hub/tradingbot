# Setup Library Expansion — SMT Reversal (S004)

Research-lead selection, implementation, validation, and portfolio
backtest for the fourth Strategy Engine V2 setup. No parameter was
tuned to make the result look better; no existing Market Intelligence
module or setup was modified.

---

## Selection — why Correlation Engine / SMT, now

Reviewed every existing tracker, every implemented setup, and every
completed research report (the architectural audit, S002's and S003's
edge analyses) against the five stated criteria:

| Candidate | Independent info | Overlap w/ S001–S003 | Institutional validity | Diversification | Architectural risk |
|---|---|---|---|---|---|
| Breaker Blocks | Low | High — audit already flagged as mechanically near-identical to Order Blocks | Medium | Low | Low |
| Fair Value Gaps | Medium | Medium — typically forms from the same impulsive leg Order Block Continuation already trades | Medium | Medium | Low |
| Equal Highs/Lows or Session Boundaries as standalone setups | Low | High — both already feed Liquidity Pools as sub-detectors; a standalone setup would largely re-trade what Liquidity Sweep Reversal already captures | Medium | Low | Low |
| Delta as standalone | Low | High — the same computation CVD already uses in Liquidity Sweep Reversal | Low | Low | Low |
| **Correlation Engine / SMT** | **Highest** — a second market (ETHUSDT) entirely | **Lowest** — used only as an optional, non-required evidence check in Liquidity Sweep Reversal; zero use elsewhere | High — SMT is documented, established ICT theory | **Highest** — a genuinely different data source | **Low, and already paid** — Step 0 wired and validated `CorrelationTracker` end-to-end on real data |

The prior audit ranked SMT below Fair Value Gaps only because of
integration cost ("the most expensive to actually test... real
Coordinator work"). Step 0 already paid that cost and validated it (190
real structural divergence events, byte-identical replay, deterministic).
With that removed, SMT is the only remaining candidate that is an
entirely unused *family* (Intermarket), not merely an unused module
within an already-heavily-used family — the clear winner on both lowest
overlap and highest diversification. No architectural issue blocked
implementation.

---

## Implementation — `SmtReversalSetup`

[strategy/setups/smt_reversal.py](strategy/setups/smt_reversal.py),
identical shape to every prior setup. Reuses `CorrelationTracker`'s
already-computed `structural_divergence_flag`/`structural_divergence_
history` completely unmodified — "SMT" is not a new detector, exactly
as `correlation.py`'s own docstring establishes.

- **Required condition (one):** `intermarket_divergence_this_bar` —
  some configured pair's most recent recorded divergence event
  (`structural_divergence_history[-1]`) has a timestamp equal to the
  current bar. Direction: `bullish_divergence` → LONG, `bearish_
  divergence` → SHORT.
- **Why freshness via history, not the sticky flag** (the same
  reasoning shape as Liquidity Sweep Reversal's `resolved_at ==
  snapshot.timestamp`): `structural_divergence_flag` only updates on
  bars where the primary stream confirms a new pivot and otherwise
  holds its last value untouched — reading it directly would fire on
  every bar until the next pivot, not just the bar the divergence
  actually happened on.
- **Additional evidence (recorded, not required):** `overall_
  structural_agreement_diverging` (the pair's broader `structural_
  agreement` field also reads "diverging") and `pair_is_positively_
  correlated` (a sign check on `price_correlation`, not a magnitude
  threshold).
- **Stop-loss:** the triggering swing pivot's own price
  (`primary_price`) as the invalidation edge, placed as `zone_high`/
  `zone_low` — the existing adapter needed zero changes.
- **Disclosed limitation:** only the `btc_eth` pair has ever been
  validated against real data; the logic is pair-agnostic but this
  report's measurements reflect BTC/ETH only.

## Validation

- 19 new unit tests in [test_smt_reversal_setup.py](tests/test_smt_reversal_setup.py):
  every rejection path (no pairs, empty history, stale divergence),
  both directions, deterministic first-fresh-pair selection among
  multiple pairs, exact stop-bound placement per direction, both
  evidence checks individually and together, reasoning strings,
  determinism.
- **Real-data validation** (BTCUSDT+ETHUSDT, 2,880 real 15m bars,
  confirmed timestamp-aligned): no crash; **190 genuine fires — an
  exact match to Step 0's own independently-measured 190 real
  divergence events**, confirming the freshness logic misses none and
  double-counts none; 87 LONG / 103 SHORT; two independent full
  replays byte-identical; final batched-replay decision identical to
  the final incremental-replay decision; 2.97 ms/bar, the same
  complexity ballpark as every prior setup.
- **A decisive finding surfaced during validation, not assumed**:
  evidence-count distribution across all 190 real fires was **0→0,
  1→0, 2→190** — both additional evidence conditions were satisfied on
  every single fire, with no exceptions. This is not incidental: a
  structural divergence event is, by the tracker's own definition, a
  moment where the primary and reference streams' pivot trends
  disagree on the axis that fired — which structurally forces
  `structural_agreement` toward "diverging" on that same bar in almost
  every case (the one theoretical exception is insufficient pivot
  history on the untested axis, not observed here). This closes off,
  before any further work, the "gate on one of the two confirmations"
  research path that produced a real finding for Volume Node Reversal
  — there is no discriminating lever to test here, measured directly.
- Full suite: **725 passed**, same 4 pre-existing unrelated
  `test_historical_loader.py` failures as every prior session.

---

## Backtest — real BTCUSDT (+ETHUSDT) data, same 30-day window

| Metric | A: Existing Portfolio (LSR+OB) | B: New (SMT only) | C: Portfolio + SMT |
|---|---:|---:|---:|
| Total Trades | 60 | 67 | 78 |
| Win Rate | 40.00% | 19.40% | 21.79% |
| Profit Factor | 0.988 | 0.334 | 0.395 |
| Expectancy | -0.89 | -51.20 | -44.98 |
| Average R | 0.001 | -0.598 | -0.527 |
| Avg Winner | 180.65 | 132.44 | 134.46 |
| Avg Loser | -121.92 | -95.40 | -94.98 |
| Net Profit | -53.60 | -3,430.09 | -3,508.16 |
| Gross Profit | 4,335.57 | 1,721.71 | 2,285.88 |
| Gross Loss | 4,389.17 | 5,151.80 | 5,794.04 |
| Max Drawdown | 625.78 (5.95%) | 3,430.09 (34.30%) | 3,508.16 (35.08%) |
| Recovery Factor | -0.086 | -1.000 | -1.000 |
| Avg Holding Time | 8.48h | 7.56h | 7.50h |
| Trade Frequency | 2.000/day | 2.233/day | 2.600/day |
| Exposure | 70.63% | 70.32% | 81.29% |

(Existing Portfolio = Liquidity Sweep Reversal + Order Block
Continuation; Volume Node Reversal is RESEARCH ARCHIVE, not part of
the live portfolio composition per the prior sprint's decision.)

**Signal-level overlap** (all three setups evaluated independently
against every one of the 2,880 real bars):

| | bars | % |
|---|---:|---:|
| LSR only | 9 | 0.31% |
| OB only | 360 | 12.50% |
| SMT only | 159 | 5.52% |
| LSR+OB | 3 | 0.10% |
| LSR+SMT | 2 | 0.07% |
| OB+SMT | 29 | 1.01% |
| all three | 0 | 0.00% |
| none | 2,318 | 80.49% |

SMT fires 190 times total; 159 (83.7%) coincide with no existing setup
— genuinely new signal. Of the 31 bars where it does coincide with an
existing setup, only 5 (16%) agree on direction; **26 (84%) fire in the
opposite direction on the same bar.**

**Slot competition**: of the Existing Portfolio's 60 standalone
entries, 19 fall inside a window where an SMT position was already
open in C; of SMT's own 67 standalone entries, 33 fall inside a window
where an existing-portfolio position was already open in C.

---

## Answers

**1. Does S004 discover genuinely new trades?**
Yes, clearly at the signal level — 83.7% of its 190 real fires occur
where neither existing setup fires. But "new" is not "useful": measured
standalone performance is the worst of any setup built so far (profit
factor 0.334, expectancy -51.20, net -3,430.09 over 67 trades) —
noticeably worse than Volume Node Reversal's own already-negative
baseline (0.411).

**2. Does it improve portfolio diversity?**
At the signal level, yes (low overlap, as above). At the risk-outcome
level, no — combining it degrades every risk metric sharply: max
drawdown rises from 5.95% to 35.08% (nearly 6x), net profit falls from
-53.60 to -3,508.16. This mirrors, at a larger magnitude, the same
pattern already measured for Volume Node Reversal: genuine signal
independence does not automatically translate into beneficial
portfolio diversification under a one-trade-at-a-time engine when the
new setup's own standalone quality is this poor.

**3. Does it add independent information?**
Yes, mechanically (different market, low signal overlap) — but the
measured direction of that information is unfavorable, and when it
does coincide with an existing setup's read, it disagrees 84% of the
time, more often in conflict than either candidate tested in S003.

**4. Should S004 become APPROVED, RESEARCH ARCHIVE, or REJECTED?**

Unlike Volume Node Reversal, there is no measured, untested lever left
to justify further research: both of this setup's additional evidence
conditions were satisfied on literally 100% of its 190 real fires, with
a clear mechanistic reason (a structural divergence event, by
definition, already implies the broader structural-agreement field
reads "diverging" on that same bar) — gating on either condition would
provably reproduce the exact same baseline result, not a genuine
single-variable experiment. Combined with the worst standalone
performance and the most severe portfolio harm measured across all
four setups built this project, the evidence does not support
"further research" the way it did for S003.

---

## Recommendation

**REJECTED**
