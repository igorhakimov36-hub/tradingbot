# Phase 2 — Step 0 + Step 1: Correlation Wiring & Order Block Continuation

Scope of this report, exactly as instructed: fix the CorrelationTracker
integration gap found by the architectural audit, build exactly one new
Strategy Engine V2 setup (Order Block Continuation) using only the
already-implemented OrderBlockTracker, validate both to the same
standard as every prior Phase 1/2 module, then run three independent,
unmodified backtests and report the comparison and edge analysis. No
parameter was tuned to make either setup look better. Liquidity Sweep
Reversal's own code was not touched.

---

## STEP 0 — Wiring CorrelationTracker into the Coordinator

**What was broken.** The audit found `MarketIntelligenceCoordinator`
never imported or instantiated `CorrelationTracker`, so
`snapshot.intermarket` was always `{}` and Liquidity Sweep Reversal's
`smt_confirms_direction` check structurally could never be satisfied.

**What changed.** [strategy/market_intelligence_coordinator.py](strategy/market_intelligence_coordinator.py):
- `__init__` gained an optional `smt_pairs: list[SMTPair] | None = None`
  parameter (default `None` — fully backward compatible; every existing
  caller and test that never mentions SMT is unaffected).
- `sync_and_build` gained an optional `reference_candles_15m: dict[str,
  list] | None = None` parameter, keyed by reference symbol name.
- Each configured pair's `CorrelationTracker` is synced once per call
  with the current full candle lists (not folded into the existing
  per-candle replay loop — `CorrelationTracker.sync()` is explicitly
  documented safe against any batch size, unlike the point-in-time
  trackers that loop needs to protect).
- The cache key that short-circuits an unchanged call now also checks
  reference-candle lengths, so a reference-only update cannot return a
  stale snapshot.
- `CorrelationTracker`'s own logic was not touched.

[strategy/strategy_engine_v2_backtest_adapter.py](strategy/strategy_engine_v2_backtest_adapter.py)
gained an optional `reference_symbols: list[str] | None = None`
parameter on `make_strategy_engine_v2_callbacks`, so a real backtest can
actually forward a second symbol's candles from `market_snapshot` into
the coordinator — completing the wiring end-to-end, not just at the
Coordinator's own API surface.

**Validation.**
- 6 new unit tests in [test_market_intelligence_coordinator.py](tests/test_market_intelligence_coordinator.py):
  backward compatibility with no `smt_pairs`, real intermarket data
  production, missing-reference honest-partial state, determinism,
  batched-vs-incremental equivalence, and cache correctness when only
  the reference stream grows.
- 2 new unit tests in [test_strategy_engine_v2_backtest_adapter.py](tests/test_strategy_engine_v2_backtest_adapter.py)
  for the new passthrough parameter.
- **Real-data validation** (BTCUSDT + ETHUSDT, same real 30-day window,
  2,880 real 15m bars each, confirmed timestamp-aligned at every one of
  the 2,880 overlapping bars):
  - Incremental replay (real cadence): no crash, 8.22s.
  - Real correlation produced: `price_correlation = 0.816`,
    `relative_strength_ratio = 31.85`, `structural_agreement =
    both_bearish`, **190 real structural divergence events** recorded
    over the 30-day window (SMT genuinely fires on real data, not
    structurally dead).
  - Batched (single call, full history) vs incremental (one bar at a
    time) replay: **byte-identical**.
  - Two independent incremental replays: **byte-identical**
    (deterministic).
- Full suite: **685 passed**, same 4 pre-existing unrelated
  `test_historical_loader.py` failures as every prior session (confirmed
  out of scope long ago).

**One expected, disclosed consequence.** Because Liquidity Sweep
Reversal's `smt_confirms_direction` check already existed but was
structurally always `False`, live-wiring real SMT data can only ever
**add** fires that were previously blocked (a bar where CHOCH and
multi-source both failed to confirm, but SMT now does) — it cannot
remove any. Report A below (13 trades) is one trade more than the last
recorded Liquidity Sweep Reversal baseline (12 trades) for exactly this
reason. No line of `strategy/setups/liquidity_sweep_reversal.py` was
changed; only real data reaching an already-existing, previously-dormant
code path changed.

---

## STEP 1 — Order Block Continuation

**Naming decision (as requested, explained before implementing).**
"Continuation" is correct, not "Reversal": Order Blocks' own module
docstring already frames a retest as "a better-defined, better-risk
re-entry" into the SAME direction that produced the original break. A
"the block failed, treat it as a flipped support/resistance" reading is
not a new idea here — that is exactly what Breaker Blocks already are
(an Order Block that fully mitigated and is re-exposed with flipped
polarity). Building "Order Block Reversal" would duplicate Breaker
Blocks' own thesis under a different name. Continuation is the one
reading that adds information rather than repeating an existing module.

**Architecture** — identical shape to Liquidity Sweep Reversal (Setup →
Conditions → Evidence → SetupResult → Strategy Engine V2 → Backtest
Adapter → Trade Journal), implemented in
[strategy/setups/order_block_continuation.py](strategy/setups/order_block_continuation.py):

- **Required condition (one):** `active_order_block_first_touch` — an
  ACTIVE Order Block zone (`kind == "order_block"`, `status ==
  "active"`) where price is currently inside it
  (`zone_relative_position == "inside_price"`, recomputed fresh from
  the current bar's price by the Snapshot Builder every call) **and**
  this is the very first touch (`touch_count == 1`). Direction: LONG
  for a bullish block, SHORT for a bearish one.
- **Why `touch_count == 1` instead of a same-bar freshness timestamp**
  (unlike Liquidity Pool's `resolved_at == snapshot.timestamp`):
  Liquidity Pools move to a permanently "swept" list once resolved, so
  without a same-bar check that setup would fire forever afterward.
  Order Block's `inside_price` fact is recomputed fresh every bar and
  naturally reverts to false once price leaves — no permanent-truth
  risk exists. What needs guarding instead is unlimited re-firing on
  the *same* zone's second, third, ... retest; `touch_count == 1`
  restricts this to the first touch only, which institutionally is
  also the strongest read (later retests consume progressively more of
  the block's resting interest). Combined with the engine's own
  one-trade-at-a-time behavior, no further de-duplication is needed.
- **Additional evidence (recorded, not required to fire):**
  `body_zone_confirms_precision` (price also inside the tighter
  body-based mitigation sub-zone — Order Block's own Mitigation Block
  fields) and `order_block_confluence` (another active, same-direction
  Order Block with an overlapping range also currently exists). Neither
  gates firing. This is a deliberate difference from Liquidity Sweep
  Reversal's *current* form: that setup's "require ≥1 confirmation"
  rule was earned through controlled experimentation specific to
  sweeps: importing that exact threshold onto a structurally different
  setup with no equivalent evidence would be assuming, not measuring.
- **Reads only Order Block zones.** No CVD, no CHOCH, no SMT, no other
  Zone kind — a deliberate scientific choice so this backtest's results
  can be attributed to Order Blocks specifically, matching the stated
  goal of isolating one module's standalone predictive power.
- **Stop-loss:** the touched block's own zone edge — `zone_low` for
  LONG, `zone_high` for SHORT — the block's own invalidation level (this
  is the wick-based zone at which `mitigation_status` would reach
  `"fully_mitigated"`), reusing the *identical* adapter code path
  Liquidity Sweep Reversal already uses (same `STOP_BUFFER_PCT`,
  `MIN_RISK_PERCENT` floor, `REWARD_MULTIPLE`, `create_risk_based_
  trade_setup`, 1% equity risk) — no adapter changes were needed at all,
  since both setups place their zone edges in `required_conditions[0]
  .evidence["zone_high"/"zone_low"]`.

**Validation.**
- 22 new unit tests in [test_order_block_continuation_setup.py](tests/test_order_block_continuation_setup.py):
  every required-condition rejection path (no zones, price outside
  zone, second touch, zero touches, resolved block, wrong zone kind),
  direction inference both ways, firing with zero additional evidence,
  deterministic tie-break among simultaneous candidates, both evidence
  checks individually and together (including a missing-fields
  graceful-degradation case), reasoning strings, determinism, and the
  stop-loss evidence contract.
- **Real-data validation** (BTCUSDT, same 2,880 real 15m bars): no
  crash; **392 genuine fires** over 30 real days (165 LONG / 227
  SHORT; evidence_count distribution 0→157, 1→183, 2→52 — a real,
  non-degenerate spread, not always-0 or always-max); two independent
  full replays byte-identical (deterministic); final batched-replay
  decision identical to the final incremental-replay decision; 2.83
  ms/bar, the same complexity ballpark as every other Phase 2 real-data
  run.
- Full suite after this step: **685 passed**, same 4 pre-existing
  unrelated failures.

---

## BACKTEST — Three independent runs, real BTCUSDT (+ETHUSDT reference) data

All three runs share identical infrastructure — same coordinator
configuration (now including the live `btc_eth` SMT pair from Step 0),
same adapter, same 1% equity risk, same fixed 2R reward, same
one-trade-at-a-time engine. The **only** variable is which setup(s) are
registered. 30-day real window: 2026-08-02 → 2026-09-01.

| Metric | A: LSR only | B: OB only | C: LSR + OB combined |
|---|---:|---:|---:|
| Total Trades | 13 | 59 | 60 |
| Win Rate | 38.46% | 33.90% | 40.00% |
| Profit Factor | 0.922 | 0.764 | 0.988 |
| Expectancy | -5.69 | -18.10 | -0.89 |
| Average R | -0.045 | -0.176 | 0.001 |
| Avg Winner | 175.17 | 172.88 | 180.65 |
| Avg Loser | -118.74 | -116.04 | -121.92 |
| Net Profit | -74.02 | -1,067.91 | -53.60 |
| Gross Profit | 875.86 | 3,457.62 | 4,335.57 |
| Gross Loss | 949.88 | 4,525.53 | 4,389.17 |
| Max Drawdown | 471.54 (4.72%) | 1,358.04 (13.26%) | 625.78 (5.95%) |
| Recovery Factor | -0.157 | -0.786 | -0.086 |
| Avg Holding Time | 14.59h | 8.66h | 8.48h |
| Trade Frequency | 0.433/day | 1.967/day | 2.000/day |
| Exposure | 26.35% | 70.94% | 70.63% |

**Neither setup shows a standalone positive edge in this 30-day sample**
(both profit factors < 1, both expectancies negative) — reported
exactly as measured, with no optimization attempted, matching the
explicit instruction not to tune toward a better-looking result. This
mirrors Liquidity Sweep Reversal's own history: its *original*
two-required-condition form was also strongly net-negative (-53.78
expectancy) before controlled experimentation identified a specific,
measured improvement. Order Block Continuation has not yet been through
that same process — it is reported here at its first-version baseline,
exactly where Liquidity Sweep Reversal itself once stood.

---

## EDGE ANALYSIS

**1. Does Order Block produce independent edge?**
Not in this sample, standalone: PF 0.764, expectancy -18.10 per trade,
net -1,067.91 over 59 trades. This does not mean the module carries no
information — it means the *specific, ungated, single-condition* setup
built here (first touch only, no required confirmation) does not clear
breakeven at these real prices over this window. That is a measured
fact about this particular setup design, not a verdict on Order Blocks
as a module.

**2. Does it generate different trades than Liquidity Sweep Reversal?**
Yes, overwhelmingly. Evaluating both setups independently against every
one of the 2,880 real bars (bypassing the one-trade-at-a-time engine
entirely, to measure true signal-level co-occurrence): LSR fires alone
on 9 bars, OB fires alone on 389 bars, and **both fire together on only
3 of 2,880 bars (0.1%)**. The two setups are reading almost entirely
non-overlapping conditions — expected, since one requires a liquidity
sweep + CVD exhaustion, and the other requires a fresh Order Block
retest, mechanically unrelated events.

**3. How much overlap exists between the two?**
Negligible at the signal level (3 of 2,880 bars, 0.1%). The much larger
interaction is *architectural*, not statistical: Order Block fires 392
times over 30 days and holds a position 70.94% of the time (Report B's
own exposure), while Liquidity Sweep Reversal fires only 12 times with
26.35% exposure. When both setups are registered together, the
single-active-trade constraint means Order Block's sheer frequency
crowds out Liquidity Sweep Reversal's rarer opportunities: **of
Report A's own 13 standalone LSR trades, 7 fall inside a time window
where an Order Block position was already open in Report C** — genuinely
crowded out, not merely coincidental absence. Report C's actual
LSR-attributed trade count (6) is consistent with 13 − 7 = 6.

**4. When both fire simultaneously, are they confirming the same
behavior or two independent ones?**
Mostly neither — they barely coincide at all (question 2/3). Of the 3
bars where they DO fire together, only 1 (33%) agrees on direction; the
other 2 (67%) fire in **opposite** directions on the same bar (one
example: 2026-08-08 19:30 UTC, LSR reads LONG off a sell-side sweep
while OB reads SHORT off a bearish block retest at the same price and
time). This is a genuine, measured finding: on the rare bars where both
mechanisms are active, they are more often in tension than agreement,
consistent with them being conceptually different theses (stop-hunt
reversal vs. trend-retracement continuation), not two lenses on the
same event.

**5. Does combining both improve the system, or simply duplicate
information?**
Neither, precisely. It does not duplicate — signal-level overlap is
0.1%, ruling out redundancy as the dominant effect. It does not clearly
improve, either: Report C's expectancy (-0.89) and profit factor
(0.988) look better than Report B's alone, but this is not evidence of
synergy — Report C is mechanically dominated by Order Block's own 54
trades (matching its standalone character closely) plus whichever 6 of
Liquidity Sweep Reversal's rarer trades happened to find a free slot;
at n=6 this is far too small a sample to attribute the slightly better
combined number to anything beyond which specific trades got lucky with
slot availability. The measured, attributable effect of combining these
two specific setups under the current engine is **slot competition**, an
architectural consequence of "only one active trade at a time" combined
with a large frequency mismatch (392 vs. 12 signal-level fires) — not a
statistical relationship between the two setups' information content.

---

## What this does and does not conclude

Per the explicit instructions for this phase: this is a measurement, not
an optimization, and not a recommendation to ship or discard Order Block
Continuation. It establishes, with real data: the setup is correctly
architected, replay-safe, deterministic, and genuinely fires on real
price action; it is currently unprofitable in its first, ungated form
over this specific 30-day window; and it operates almost entirely
independently of Liquidity Sweep Reversal at the signal level, with the
main cross-setup interaction being slot competition from the shared
one-trade-at-a-time engine, not overlapping information. Whether to run
the same controlled-experiment protocol already applied to Liquidity
Sweep Reversal (single-variable tests — e.g., requiring the confluence
evidence, or restricting to a specific regime) is a decision for a
future, explicitly-scoped research phase, not attempted here.
