# Setup Library Expansion — Fair Value Gap Rebalance (S005)

Research-lead selection, implementation, validation, and portfolio
backtest for the fifth Strategy Engine V2 setup. No parameter was
tuned; no existing Market Intelligence module, tracker, or approved
setup (S001, S002) was modified. S003 (RESEARCH ARCHIVE) and S004
(REJECTED) were not revisited.

---

## Step 1 — Selection

Every remaining tracker not yet the basis of a built setup was
reviewed against six criteria (independent info, diversification,
overlap with S001+S002, institutional validity, architectural
simplicity, research value). One verified fact decided the ranking:
`strategy/features/fair_value_gap.py`'s own docstring confirms Fair
Value Gap detection is "a fully independent primitive - no dependency
on any other Smart Money module" (a plain 3-candle wick-overlap check).
Order Blocks *and* Breaker Blocks, by contrast, are both explicitly
gated on `detect_bos` — a BOS-based candidate setup would share its
literal triggering event with S002 (Order Block Continuation),
monetizing the same detected break at two different times.

| Candidate | Independent info | Diversification | Overlap w/ S001+S002 | Institutional validity | Simplicity | Research value |
|---|---|---|---|---|---|---|
| Breaker Blocks | Low | Low | High — already twice flagged as near-identical to Order Blocks | Medium | High | Low |
| Equal Highs/Lows (standalone) | Low | Low | High — already a sub-detector feeding S001's Liquidity Pools | Medium | High | Low |
| Delta (standalone) | Low | Low | High — same computation CVD already uses in S001 | Low | High | Low |
| Market Structure / BOS Momentum | Medium | Medium | Medium — shares its literal triggering event with S002 | High | High | Medium |
| Session Boundaries (standalone) | Medium | Medium | Medium — session extremes already feed S001's Liquidity Pools | Medium | Medium | Medium |
| **Fair Value Gaps** | **High** | **High** | **Low** — independent detection trigger, no shared root cause with S001 or S002 | **High** | **High** | **High** |

**Selected: Fair Value Gap Rebalance.**

## Step 2 — Implementation

[strategy/setups/fair_value_gap_rebalance.py](strategy/setups/fair_value_gap_rebalance.py),
identical architecture to every prior setup.

- **Required condition (one):** `price_rebalancing_unfilled_gap` — an
  ACTIVE FVG zone with `fill_status == "partially_filled"` (the
  Snapshot's mapping of the tracker's own field) and price currently
  inside it. FVG exposes no `touch_count` the way Order Blocks do, so
  Order Block Continuation's exact freshness mechanism does not
  transfer directly; this combination isolates the same institutionally
  meaningful moment (a retracement is underway, the gap is not yet
  fully consumed) without a field the tracker doesn't expose — "active"
  (0% filled) and "inside price" cannot co-occur in practice, since
  entering the gap is exactly what advances `fill_status`.
- **Additional evidence (recorded, not required):** `fvg_confluence`
  (another overlapping same-direction FVG — the same shape as S002's
  `order_block_confluence`) and `overlaps_order_block_zone` (a
  genuinely new cross-family check: an overlapping same-direction
  Order Block also exists).
- **Stop-loss:** the gap's own zone edge, reusing the exact adapter
  code path unmodified.

## Step 3 — Validation

- 20 new unit tests in [test_fair_value_gap_rebalance_setup.py](tests/test_fair_value_gap_rebalance_setup.py):
  every rejection path, both directions, zero-evidence firing,
  deterministic tie-break, both evidence checks individually and
  together (including cross-kind confluence), reasoning, determinism,
  stop-loss evidence.
- **Real-data validation** (BTCUSDT, 2,880 real 15m bars): no crash;
  **455 genuine fires** (296 LONG / 159 SHORT; evidence distribution
  0→270, 1→168, 2→17 — non-degenerate); two independent full replays
  byte-identical; final batched-replay decision identical to the final
  incremental-replay decision; 2.82 ms/bar — same complexity ballpark
  as every prior setup. Zero replay violations.
- Full suite: **745 passed**, same 4 pre-existing unrelated
  `test_historical_loader.py` failures as every prior session.

---

## Step 4/5 — Backtest & Comparison

Real BTCUSDT (+ETHUSDT reference) data, same 30-day window.

| Metric | A: Approved Portfolio (LSR+OB) | B: New (FVG only) | C: Portfolio + FVG |
|---|---:|---:|---:|
| Trades | 60 | 60 | 72 |
| Win Rate | 40.00% | 40.00% | 38.89% |
| Profit Factor | 0.988 | **0.992** | 0.947 |
| Expectancy | -0.89 | **-0.60** | -3.94 |
| Average R | 0.001 | 0.004 | -0.029 |
| Net Profit | -53.60 | -36.14 | -283.71 |
| Gross Profit | 4,335.57 | 4,318.02 | 5,077.87 |
| Gross Loss | 4,389.17 | 4,354.16 | 5,361.58 |
| Max Drawdown | 625.78 (5.95%) | 762.24 (7.11%) | 1,256.95 (11.45%) |
| Recovery Factor | -0.086 | -0.047 | -0.226 |
| Holding Time | 8.48h | 8.38h | 8.22h |
| Trade Frequency | 2.000/day | 2.000/day | 2.400/day |
| Exposure | 70.63% | 69.87% | 82.16% |

**S005's own standalone result (PF 0.992, expectancy -0.60) is the
closest to breakeven of any setup measured in this project to date**
(S001: 0.988, S002: 0.764, S003: 0.411, S004: 0.334) — reported exactly
as measured, still net-negative, not a claim of edge.

**Signal-level overlap** (all three setups evaluated independently
against every one of the 2,880 real bars):

| | bars | % |
|---|---:|---:|
| LSR only | 9 | 0.31% |
| OB only | 351 | 12.19% |
| FVG only | 416 | 14.44% |
| LSR+OB | 2 | 0.07% |
| FVG+LSR | 0 | 0.00% |
| FVG+OB | 38 | 1.32% |
| all three | 1 | 0.03% |
| none | 2,063 | 71.63% |

FVG fires 455 times total; **416 (91.4%) coincide with no existing
setup — the highest signal independence measured for any setup built
in this project.** Of the 39 bars where it does coincide, direction
agreement is close to even (20 agree, 18 conflict) — a materially
healthier overlap pattern than either S003 (67% conflict) or S004 (84%
conflict) showed.

**Slot competition**: of the Approved Portfolio's 60 standalone
entries, 25 fall inside a window an FVG position already occupied in
C; of FVG's own 60 standalone entries, 29 fall inside a window an
existing-portfolio position already occupied in C — substantial mutual
crowding despite the low signal-level overlap, since all three setups
fire often enough to frequently compete for the same single trade slot.

---

## Step 6 — Answers

**1. Does S005 produce independent edge?**
Not proven. Standalone profit factor is 0.992 — the closest to 1.0 (and
to a positive edge) of any setup measured, but still below it, and net
profit is still negative (-36.14 over 60 trades).

**2. Does it discover trades that S001 and S002 never see?**
Yes, decisively — 91.4% of its 455 signal-level fires occur on bars
where neither approved setup fires, the highest independence ratio
measured across all setups built so far.

**3. Does it improve the approved portfolio?**
No, measured directly. Combined net profit (-283.71) is worse than the
Approved Portfolio alone (-53.60) and worse than the naive sum of the
two standalone results (-53.60 + -36.14 = -89.74) — combining does not
average out, driven by slot competition changing which specific trades
each setup gets to take once registered together.

**4. Does it increase or reduce drawdown?**
Increases it — from 5.95% (A) to 11.45% (C), roughly double, despite
FVG's own standalone drawdown (7.11%) being only modestly worse than
A's.

**5. Does it compete with existing setups for the same trades?**
Yes, substantially at the trade/slot level (25 of 60 and 29 of 60
entries crowded out respectively) even though genuine signal-level
overlap is low (8.6% of FVG's fires coincide with an existing setup
at all) — the competition is for the shared single-trade-at-a-time
slot, not for the same underlying information.

**6. Status.**
Neither APPROVED (no configuration demonstrates a positive edge, and
combining harms the portfolio) nor REJECTED (unlike S004, this setup's
own standalone result is the best measured to date, its signal
independence is the highest measured to date, and it carries two
untested additional-evidence conditions — `fvg_confluence`,
`overlaps_order_block_zone` — that have not been evaluated as gating
confirmations this cycle, a genuine open research lever, unlike S004's
provably non-discriminating evidence).

---

## Recommendation

**RESEARCH ARCHIVE**
