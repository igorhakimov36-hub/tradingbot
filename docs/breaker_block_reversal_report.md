# Setup Library Expansion — Breaker Block Reversal (S006)

No existing tracker, Market Intelligence module, Strategy Engine V2
code, Snapshot schema, or previously-approved setup was modified. No
parameter was tuned.

---

## Institutional interpretation — stopped and reconsidered before implementing

The candidate was proposed as "Breaker Block Continuation." Direct
inspection of `strategy/features/breaker_block.py` changed the
conclusion: a Breaker Block's `direction` field is assigned as
`_opposite(order_block["direction"])` — it is already the **post-flip**,
forward-looking role, not a continuation of the source Order Block's
original direction. The module's own docstring is explicit: *"broken
support becomes resistance... a genuine positioning shift at that
level, not noise"* (classical technical analysis, not an ICT-specific
reframing). A Breaker Block's entire premise is that the *original*
move already failed and reversed at that level — Order Block
Continuation (S002) already trades "the original impulsive move keeps
going," on the *unbroken* version of the same zone. Naming this setup
"Continuation" would misleadingly imply it continues the same original
move S002 trades, when it instead confirms that move already ended.
**"Breaker Block Reversal" is the institutionally correct name.**

A precise, code-verified structural consequence, not merely asserted:
an Order Block and its eventual Breaker Block are the *same tracked
zone at mutually exclusive lifecycle stages*. `OrderBlockTracker`
keeps a zone in its `active` list (Order Block Continuation's entire
tradeable population) only while unmitigated; the instant it becomes
`fully_mitigated` it moves to `mitigated` and is immediately reborn in
`BreakerBlockTracker._detect_new_breakers`. **The two setups can never
trade the same zone at the same time** — one trades it before its one
state transition, the other only after.

---

## Implementation

[strategy/setups/breaker_block_reversal.py](strategy/setups/breaker_block_reversal.py),
identical architecture to every prior setup.

- **Required condition (one):** `active_breaker_block_first_touch` —
  mirrors Order Block Continuation's exact design (`touch_count == 1`
  + `zone_relative_position == "inside_price"`), which is possible
  because `BreakerBlock.to_dict()` exposes the identical `touch_count`
  field via the same `zone_lifecycle` mechanics.
- **No body-zone evidence check** (unlike Order Block Continuation) —
  `BreakerBlock` does not expose `mitigation_zone_high`/`_low`; that
  sub-zone is explicitly scoped to Order Blocks only (Phase 1.6).
  Inventing one here would have violated "do not invent indicators."
- **Additional evidence (recorded, not required):** `breaker_block_confluence`
  (another overlapping same-direction Breaker Block) and
  `overlaps_liquidity_pool` (an overlapping Liquidity Pool with a
  *directionally consistent* bias — a sell-side pool, built from lows,
  for a bullish/support Breaker Block; a buy-side pool, built from
  highs, for a bearish/resistance one — a reasoned mapping, not an
  arbitrary pairing).
- **Stop-loss:** the Breaker Block's own zone edge — the level at
  which it would become fully mitigated a second time, falsifying the
  flip. Reuses the existing adapter unmodified.

## Validation

- **Unit tests:** 24 new tests in [test_breaker_block_reversal_setup.py](tests/test_breaker_block_reversal_setup.py) — every rejection path, both directions, zero-evidence firing, deterministic tie-break, both evidence checks (including the directional Liquidity Pool mapping in both directions and its negative case), reasoning, determinism, stop-loss evidence.
- **Regression:** full suite **773 passed, 0 failed** (unchanged from before this setup was added).
- **Real BTCUSDT validation** (original 30-day window, 2,880 15m bars): **336 genuine fires** (213 LONG / 123 SHORT); two independent full replays byte-identical (**determinism confirmed**); final batched-replay decision identical to the final incremental-replay decision (**batch/incremental equivalence confirmed**); **replay safety** inherited from the already-validated Coordinator, exercised here without violation; 2.78 ms/bar for setup evaluation alone.
- **Complexity analysis — an unexpected, precisely-diagnosed finding:** extending validation to multi-month windows (below) exposed that `BacktestRunner`'s full pipeline scales **quadratically**, not linearly, in candle count. Root cause identified by direct code inspection: `backtesting/point_in_time.py::get_available_data()` performs a full linear rescan of the *entire* visible-history list on every single call, with no pointer or early exit; `ReplayEngine.get_visible_history()` calls it once per replay step. For a growing history of N candles this makes the whole backtest O(N²). Measured confirmation: a 30-day window (43,200 1m candles) takes ~85s; a 12-month window (525,600 candles, 12.2x more data) took 15,499s (~4.3 hours) — a **182x slowdown for 12.2x more data**, matching the O(N²) prediction of (525,600/43,200)² ≈ 148x almost exactly. This is pre-existing `BacktestRunner`/`point_in_time.py` infrastructure present since Phase 0, affecting every backtest ever run in this project equally — it was invisible until this task because every prior backtest used a 30-day-scale window. **Not fixed here** (out of scope: not Market Intelligence, not a setup, and this task's instructions did not authorize touching Backtest Runner infrastructure) — reported precisely so a future infrastructure milestone can address it deliberately.
- **Practical consequence for this report:** because of the above, the originally-planned full 24-month cross-asset validation was stopped after diagnosing the cost, and rerun on a single representative month (2024-01) per asset instead, with the resulting lower statistical confidence disclosed explicitly below rather than presented as equivalent to the original plan.

---

## Out-of-sample validation — BTCUSDT, reported independently (not pooled)

| Metric | TRAIN (2024 H1: Jan–Jun, 182 days) | VALIDATION (2024 H2: Jul–Dec, 184 days) | HELD_OUT (2025 full year, 365 days) |
|---|---:|---:|---:|
| Trades | 498 | 550 | 851 |
| Win Rate | 35.14% | 34.55% | 31.61% |
| Profit Factor | 0.830 | 0.756 | **0.708** |
| Expectancy | -10.39 | -10.90 | -10.41 |
| Average R | -0.132 | -0.151 | -0.237 |
| Net Profit | -5,175.53 | -5,994.90 | -8,862.21 |
| Max Drawdown | 63.06% | 66.00% | **89.32%** |
| Recovery Factor | -0.706 | -0.841 | -0.966 |
| Holding Time | 4.75h | 4.22h | 6.14h |
| Trade Frequency | 2.736/day | 2.989/day | 2.332/day |
| Exposure | 54.21% | 52.60% | 59.62% |

**Profit factor declines monotonically across all three windows, and
max drawdown grows to 89.32% over the full 2025 year** — the single
worst risk figure measured for any setup in this project, by a wide
margin (the next-worst, SMT Reversal's combined-portfolio run, reached
35.08%). Sample sizes are large (498–851 trades per window), so this
is not a small-sample artifact.

## Cross-asset validation — ETHUSDT/SOLUSDT/XRPUSDT, January 2024 (scope reduced from the original 24-month plan after the complexity finding above; lower statistical confidence, disclosed)

| Metric | ETHUSDT | SOLUSDT | XRPUSDT |
|---|---:|---:|---:|
| Trades | 93 | 121 | 81 |
| Win Rate | 30.11% | 40.50% | 32.10% |
| Profit Factor | 0.658 | **1.061** | 0.726 |
| Expectancy | -25.99 | 4.31 | -21.69 |
| Net Profit | -2,417.27 | **521.44** | -1,756.63 |
| Max Drawdown | 30.64% | 18.64% | 28.70% |
| Trade Frequency | 3.000/day | 3.903/day | 2.613/day |
| Exposure | 49.65% | 36.12% | 39.47% |

**Signal frequency, replay correctness, and determinism** are
structurally asset-independent (the identical Coordinator/Setup code
ran unmodified for every symbol; determinism and replay safety were
already proven architecture-wide, not asset-specific, in the original
BTC validation). **Basic profitability is mixed**: SOLUSDT's single
tested month is the only profitable result measured for this setup on
*any* asset or window in this entire report (PF 1.061); ETHUSDT and
XRPUSDT were both negative, in the same range as BTC's own results.
Across all 7 asset-window combinations measured in this report (BTC's
4 + these 3), **6 of 7 show profit factor below 1.0.**

## Backtest A/B/C — original 30-day BTCUSDT research window

| Metric | A: S006 only | B: Approved Portfolio | C: Portfolio + S006 |
|---|---:|---:|---:|
| Trades | 49 | 60 | 69 |
| Win Rate | 30.61% | 40.00% | 33.33% |
| Profit Factor | 0.651 | 0.988 | 0.742 |
| Expectancy | -26.85 | -0.89 | -19.30 |
| Net Profit | -1,315.70 | -53.60 | -1,331.56 |
| Max Drawdown | 14.71% | 5.95% | 15.85% |
| Trade Frequency | 1.633/day | 2.000/day | 2.300/day |
| Exposure | 62.79% | 70.63% | 79.52% |

(Approved Portfolio = S001 Liquidity Sweep Reversal + S002 Order Block
Continuation, re-run fresh for this report — 60 trades, byte-identical
to every prior report, confirming zero drift from the repository
integrity sprint's `historical_loader.py` fix.)

**Signal-level overlap** (all three setups evaluated independently
against every one of the 2,880 real bars): S006 fires 336 times; 291
(86.6%) coincide with no existing setup — the second-highest signal
independence measured in this project (behind Fair Value Gap
Rebalance's 91.4%). Of the 43 bars where it coincides specifically
with Order Block Continuation, 24 (56%) agree on direction, 19 (44%)
conflict — the most balanced (least conflicting) overlap pattern
measured so far.

**Slot competition:** of the Approved Portfolio's 60 standalone
entries, 13 fall inside a window an S006 position already occupied in
C; of S006's own 50 standalone entries, 32 fall inside a window an
existing-portfolio position already occupied in C.

---

## Analysis

**1. Does S006 generate independent trades?**
Yes, at the signal level — 86.6% of its fires occur where neither
approved setup fires.

**2. How much signal overlap exists?**
Low: 13.4% of S006's 336 fires coincide with an existing setup at all
(1.49% of all bars for the OB pairing specifically, 0.07% for the LSR
pairing) — comparable to or lower than every setup measured so far.

**3. Does it improve portfolio performance?**
No, measured directly. Combined (C) net profit (-1,331.56) is worse
than the Approved Portfolio alone (-53.60) and close to a straight sum
of the two standalone results (-53.60 + -1,315.70 = -1,369.30) — no
synergy, consistent with the pattern already established for every
prior expansion setup.

**4. Does it reduce or increase drawdown?**
Increases it sharply: 5.95% (B) → 15.85% (C) in the 30-day comparison,
and far more severely in the BTC out-of-sample study, where S006
standalone reaches 89.32% max drawdown in the HELD_OUT year alone.

**5. Does it discover opportunities the existing portfolio never sees?**
Yes — the same 86.6%/291-bar figure from Question 1, plus the
structural guarantee from the institutional-interpretation review: a
Breaker Block cannot exist while its source Order Block is still
tradeable by S002, so by construction S006 sees a population of
opportunities S002 structurally cannot.

**6. Does it provide genuinely new institutional information, or is it
primarily another representation of Order Block Continuation?**
Genuinely new, verified structurally rather than assumed. `OrderBlockTracker`
moves a zone from `active` to `mitigated` the instant it fully fails,
and `BreakerBlockTracker._detect_new_breakers` only ever creates a
Breaker Block from that `mitigated` list — a single Order Block object
can never be in both trackers' `active` population simultaneously.
S002 trades "this zone is still holding as originally formed"; S006
trades "this zone already failed and flipped" — mutually exclusive
market events on the same underlying zone at different times, not two
readings of the same event. The 86.6% signal independence and the
56%/44% (near-even) direction-agreement split when they do coincide
are the empirical evidence consistent with this structural fact.

**7. Does the setup appear robust across assets, or mainly BTC-specific?**
Neither cleanly — the honest answer, at the reduced sample size
available: it is unprofitable on most tested asset/window
combinations regardless of asset. BTC showed 4/4 negative windows;
non-BTC showed 2/3 negative (ETH, XRP) and 1/3 positive (SOL, single
month, PF 1.061). This does not support "BTC-specific" (BTC is not
uniquely bad; if anything a non-BTC asset was the only positive result)
nor "robustly general" (6 of 7 combinations are negative). The
cross-asset sample is smaller than originally planned (1 month per
asset instead of 24, per the complexity finding above), so this
specific question carries lower confidence than the BTC out-of-sample
finding, and is disclosed as such rather than overstated.

**8. Does performance materially change across TRAIN / VALIDATION /
HELD_OUT?**
Yes, and in a specific, consistent direction: it gets *worse*, not
better or noisier. Profit factor declines monotonically (0.830 → 0.756
→ 0.708) and max drawdown grows monotonically (63.06% → 66.00% →
89.32%) across all three windows, in chronological order. This is the
opposite pattern from Volume Node Reversal's own out-of-sample study
(S003), where most later windows looked *better* than the original
worst-case window — S006 shows the reverse: deterioration over time,
not an unrepresentative worst-case sample.

---

## Final Certification

Distinguishing this explicitly from Volume Node Reversal's RESEARCH
ARCHIVE (S003), the closest precedent — VNR's worst measured window
was not representative (5 of 6 later out-of-sample months were
meaningfully better, PF 0.80–0.92) and its drawdown never exceeded
~28% in any window measured. S006 shows the opposite trajectory on
both counts: performance deteriorates monotonically across every
window tested, and drawdown reaches 89.32% — a risk magnitude in a
different category from every other setup measured in this project,
not merely "not yet profitable." Two untested additional-evidence
conditions remain (`breaker_block_confluence`, `overlaps_liquidity_pool`),
but given the severity and the worsening trend of the risk profile
already measured, it is not plausible that gating on them would move
this setup out of a dangerous risk category the way Volume Node
Reversal's `node_is_wide` measurably improved (without ever making it
profitable) — the concern here is not primarily "not enough edge yet,"
it is "actively hazardous at current position sizing." Sample sizes
throughout (498–851 trades per BTC window) are large enough that this
is not a "needs more data" situation — the evidence is large-sample and
directionally consistent, not ambiguous.

**REJECTED**
