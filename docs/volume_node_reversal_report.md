# Setup Library Expansion — Volume Node Reversal

**STATUS: RESEARCH ARCHIVE** (see [volume_node_reversal_round1_experiments.md](volume_node_reversal_round1_experiments.md)
for the Round 1 conclusion that closed this setup's research for now —
not promoted, not rejected outright).

Research-lead selection, implementation, validation, and portfolio
backtest for the third Strategy Engine V2 setup. No architecture
document was produced (per instruction — the architecture is settled);
this is a measurement report only. No parameter was tuned to make the
result look better, and neither existing setup's code was touched.

---

## Setup selection — why Volume Profile, why High Volume Nodes

Reviewed against the four stated criteria, using everything already
measured (the architectural audit, both prior edge analyses, the
overlap studies):

| Candidate | Independent info gain | Overlap w/ existing setups | Institutional validity |
|---|---|---|---|
| **Volume Profile** | High — completely untouched family; audit confirmed zero existing setup ever reads `snapshot.levels` or `snapshot.volume_profile` | None — shares no mechanism with liquidity-sweep-reversal or order-block-continuation | High — POC/Value Area/HVN/LVN is standard auction-market theory |
| Fair Value Gaps | Medium | Higher — an imbalance is a byproduct of the same impulsive moves Order Blocks already react to | Medium |
| Breaker Blocks | Low | High — audit explicitly flagged this as mechanically near-identical to Order Blocks, likely correlated not additive | Medium |
| Correlation/SMT as a primary setup | Potentially high, unproven | Already partially exercised — Liquidity Sweep Reversal already reads it as evidence | Medium — needs two-symbol alignment, only one pair (BTC/ETH) ever validated |

Volume Profile wins on **lowest overlap with existing setups**, a
criterion no other candidate could match as cleanly, and on
**independent information gain**, since it was the single richest
completely-unused signal identified in the audit.

Within Volume Profile, three institutional readings exist:
1. **High Volume Node (HVN) reaction** (chosen) — a price shelf of
   heavy prior acceptance acts as support/resistance; standard auction-
   market theory.
2. Low Volume Node (LVN) continuation — the *opposite* thesis (a
   "void" the market moves through quickly). Left for a future,
   separate setup — folding two opposite theses into one setup by
   which node type happens to be nearest would not be a single,
   testable institutional idea.
3. Cross-period Value Area migration (`poc_shift_from_previous_period`,
   `value_area_overlap_ratio`) — both are continuous scores with no
   tracker-asserted threshold; firing on them would require inventing
   a cutoff, which the instruction not to invent new thresholds rules
   out.

No architectural issue blocked implementation — proceeded directly.

---

## Implementation — `VolumeNodeReversalSetup`

[strategy/setups/volume_node_reversal.py](strategy/setups/volume_node_reversal.py),
identical shape to the two existing setups (Setup → Conditions →
Evidence → SetupResult → Strategy Engine V2 → Backtest Adapter → Trade
Journal). No feature tracker was touched; no new indicator was added.

- **Required condition (one):** `price_at_high_volume_node` — current
  price falls inside the same price bucket as an HVN node of the
  *current forming* profile (`node.price <= current_price <
  node.price + bucket_size`, where `bucket_size` is Volume Profile's
  own already-computed histogram resolution — not an invented
  tolerance), and the node's price differs from the current POC
  (otherwise direction is undefined — a node at the POC itself isn't a
  secondary shelf). Direction: a node above POC reads as resistance
  (SHORT); below POC reads as support (LONG).
- **Additional evidence (recorded, not required — matching Order Block
  Continuation's first-version precedent, since Liquidity Sweep
  Reversal's own confirmation gate was earned through experiments
  specific to that setup):** `node_is_wide` (the node's own `width`
  field spans more than one bucket — the same "more than the bare
  minimum count" shape as Liquidity Sweep Reversal's `pool_has_
  multiple_sources`) and `value_area_confluence` (the node also falls
  inside the current Value Area — two independently-computed Volume
  Profile concepts agreeing).
- **Stop-loss:** the node's own already-computed span (`width ×
  bucket_size`) beyond its bucket, in the direction that invalidates
  the support/resistance thesis — placed as `zone_high`/`zone_low` in
  the required condition's evidence, so the **existing backtest
  adapter needed zero changes** to place this setup's stop correctly.

## Validation

- 21 new unit tests in [test_volume_node_reversal_setup.py](tests/test_volume_node_reversal_setup.py):
  every rejection path (no levels, no POC, no bucket size, price
  outside every bucket, node at POC, LVN ignored), both directions,
  zero-evidence firing, deterministic tie-break, exact stop-bound
  arithmetic for both directions, both evidence checks individually
  and together, reasoning strings, determinism.
- **Real-data validation** (BTCUSDT, 2,880 real 15m bars): no crash;
  **267 genuine fires** (99 LONG / 168 SHORT; evidence distribution
  0→25, 1→90, 2→152 — non-degenerate); two independent full replays
  byte-identical; final batched-replay decision identical to the final
  incremental-replay decision; 2.79 ms/bar, the same complexity
  ballpark as every other setup validated so far.
- Full suite: **706 passed**, same 4 pre-existing unrelated
  `test_historical_loader.py` failures as every prior session.

---

## Backtest — three independent runs, real BTCUSDT (+ETHUSDT reference) data

Same shared infrastructure throughout (same coordinator config
including the live `btc_eth` SMT pair, same adapter, same 1% equity
risk, same fixed 2R reward, same one-trade-at-a-time engine). 30-day
real window: 2026-08-02 → 2026-09-01.

| Metric | Existing Portfolio (LSR+OB) | New (VNR only) | Portfolio + VNR |
|---|---:|---:|---:|
| Total Trades | 60 | 33 | 57 |
| Win Rate | 40.00% | 21.21% | 21.05% |
| Profit Factor | 0.988 | 0.411 | 0.414 |
| Expectancy | -0.89 | -49.75 | -47.71 |
| Average R | 0.001 | -0.519 | -0.532 |
| Avg Winner | 180.65 | 163.85 | 159.88 |
| Avg Loser | -121.92 | -107.26 | -103.07 |
| Net Profit | -53.60 | -1,641.78 | -2,719.55 |
| Gross Profit | 4,335.57 | 1,146.95 | 1,918.58 |
| Gross Loss | 4,389.17 | 2,788.73 | 4,638.13 |
| Max Drawdown | 625.78 (5.95%) | 1,891.67 (18.92%) | 3,082.79 (29.75%) |
| Recovery Factor | -0.086 | -0.868 | -0.882 |
| Avg Holding Time | 8.48h | 18.01h | 10.87h |
| Trade Frequency | 2.000/day | 1.100/day | 1.900/day |
| Exposure | 70.63% | 82.56% | 86.07% |

Reported exactly as measured — no tuning attempted. Volume Node
Reversal's own baseline (PF 0.411, expectancy -49.75) is measurably
worse than either existing setup's own first-version baseline (Order
Block Continuation started at PF 0.764, expectancy -18.10). Combining
it with the existing portfolio does not average out — it makes every
risk metric meaningfully worse (net profit roughly 50x more negative,
max drawdown roughly 5x larger as a percentage).

---

## Edge Analysis

**1. Does the new setup produce independent edge?**
No, not in this sample. Standalone: profit factor 0.411, expectancy
-49.75 per trade, net -1,641.78 over 33 trades. This is a real,
unfavorable measurement of the setup's *current* (ungated) form, not a
verdict on Volume Profile as a module — the setup carries two built-in
evidence conditions (`node_is_wide`, `value_area_confluence`) that are
deliberately not yet required, mirroring exactly the situation Order
Block Continuation and Liquidity Sweep Reversal's own *original* form
both started from.

**2. Does it discover trades that no existing setup finds?**
Yes, clearly. Evaluating all three setups independently against every
one of the 2,880 real bars: Volume Node Reversal fires 267 times total,
and **228 of those (85.4%) occur on bars where neither existing setup
fires at all** — a genuinely new signal source, not a repackaging of
Liquidity Pool or Order Block information. Only 39 of its 267 fires
(14.6%) coincide with an existing setup, and of those 39, direction
agreement is nearly a coin flip (20 agree, 19 conflict) — when it does
overlap, it is not simply restating what the other setups already
concluded.

**3. Does it diversify the portfolio?**
Diversifies the *signal mix*, yes — the overlap numbers above confirm
genuinely independent trade discovery. It does **not** diversify the
*risk profile* in the beneficial sense, however: combining it with the
existing portfolio increases exposure (70.63% → 86.07%, the system is
now in a trade nearly the entire window) and drawdown (5.95% → 29.75%)
without any offsetting improvement in return. The mechanism is visible
directly in the trade-level data: of the Existing Portfolio's own 60
standalone entries, 34 fall inside a window where a newly-registered
VNR position was already occupying the single-trade slot in the
combined run — the low-quality new setup is winning slot contention
against the (marginally better) existing portfolio a majority of the
time, which is the opposite of a beneficial diversification effect
under this engine's one-trade-at-a-time constraint.

**4. Should it be promoted into the live research portfolio?**
Not as currently configured. Its standalone performance is
substantially worse than either existing setup's own starting point,
and adding it degrades the combined portfolio's drawdown and net
result materially. At the same time, rejecting the underlying idea
outright would be premature: it has real, measured signal independence
(criterion 2) and institutional grounding (HVN support/resistance is
standard theory), and — like Liquidity Sweep Reversal before its own
Round 1/2 experiments — it has not yet been tested with its own
evidence conditions gating the fire decision. That specific,
single-variable experiment ("require `node_is_wide`", "require
`value_area_confluence`", "require either") is the natural next
controlled-research step, using the exact same protocol already
validated on Liquidity Sweep Reversal, before any promotion decision.

---

## Recommendation

**RESEARCH FURTHER**
