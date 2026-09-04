# S007 — Trend Continuation Confluence
## Initial Validation Report (Phase 3, Step 1)

**This is NOT a certification.** No verdict (APPROVED / RESEARCH ARCHIVE /
REJECTED) is issued here. This document covers only: architecture
verification, implementation, the full validation suite, and one
initial two-window backtest, per the Phase 3 Step 1 task scope. Full
multi-asset, multi-year certification is future work.

---

## 1. Step 0 — Design Verification (recap)

Confirmed before implementation began (see chat record and
`docs/phase3_confluence_research_design.md`):

- No tracker, `MarketIntelligenceSnapshot`, `MarketIntelligenceCoordinator`,
  `StrategyEngineV2`, or `BacktestRunner` change was needed or made.
- `structure.bos` is used exactly as documented (level-based, no
  freshness/state) — the `Setup` protocol forbids internal state, so this
  was the only zero-state option, not a simplification of convenience.
- "Liquidity" is scoped to Liquidity Pool zones only (not Equal
  Highs/Lows), matching the backtest adapter's existing
  `zone_high`/`zone_low` stop-placement contract exactly.
- "First touch" language was deliberately not reused from S002/S006 —
  Liquidity Pools have no revisit counter; the condition checks "price
  currently inside an active, never-swept pool," named accordingly.

## 2. Implementation

- [strategy/setups/trend_continuation_confluence.py](../strategy/setups/trend_continuation_confluence.py) —
  `TrendContinuationConfluenceSetup`. Required conditions, in adapter-
  mandated order: `price_inside_active_liquidity_pool` (index 0, carries
  `zone_high`/`zone_low` for stop placement), `structural_trend_confirmed`
  (`bos` in `BULLISH_BOS`/`BEARISH_BOS`). Optional evidence:
  `value_area_confluence` (pool zone overlaps `[value_area_low,
  value_area_high]`), `cvd_confirms_trend` (any CVD anchor's
  `cvd_direction` agrees with trend direction).
- Stop-loss: the touched pool's own `zone_low` (LONG) / `zone_high`
  (SHORT) — identical mechanism to S001/S002/S003/S006, no adapter
  change.
- No new indicator, no new threshold. `value_area_confluence` reuses
  the exact containment-test shape already established by S003;
  `cvd_confirms_trend` reads an already-discrete tracker classification.

## 3. Validation Suite

| Check | Result |
|---|---|
| Unit tests | 22/22 passing — required-condition rejection/fire paths (both directions), pool-side mismatch, swept-pool exclusion, non-liquidity-pool zone exclusion, both optional evidences independently, reasoning strings, stop-loss evidence, determinism |
| Full regression suite | 795/795 passing (773 pre-existing + 22 new), zero regressions |
| Determinism | Same BacktestRunner backtest run twice on real BTCUSDT data (14-day slice) → byte-identical opened-trade sequence and net PnL |
| Replay safety / incremental replay | A hand-rolled, per-1-minute-bar walk-forward (bypassing `BacktestRunner`/`PointInTime` entirely, replicating the real adapter's exact mechanism — last-closed 15m history + live 1m close) reproduced BacktestRunner's own 2 real trade opens exactly, timestamp-for-timestamp and price-for-price (matched against `requested_entry`, the pre-slippage decision price — the initial raw comparison against post-slippage `entry_price` mismatched by exactly the configured 0.02% slippage rate, a test-harness correction, not a defect) |
| Real BTCUSDT data | 30 raw fires over a 14-day/1343-15m-bar slice, collapsing to 2 actual trade opens (level-based `bos` persists across many consecutive bars while a pool remains `inside_price`, matching the setup's own documented re-fire characteristic) |
| Complexity | `evaluate()` is O(zones + levels) per bar — one linear scan of `snapshot.zones` for a matching Liquidity Pool, one of `snapshot.levels` for VAH/VAL, one dict iteration over `order_flow.cvd` — identical complexity class to every existing setup. No new tracker, no change to the pre-existing O(n²) `BacktestRunner`/`get_available_data()` scaling issue (unrelated to this setup, previously reported against S006, not re-triggered here since both validation windows are single 30-day months, well inside the range that stayed fast in every prior report) |
| Zero regression | Confirmed by the full suite above |

## 4. Initial Backtest — A/B/C, two independent windows

**Windows:** 2024-01 (standard first window used throughout this
project) and 2025-03. The 2025 month was selected by a documented
random draw executed *before* any backtest ran:
`secrets.randbelow(12) + 1` → **3** (March). Not chosen based on
performance.

**Configs:** A = S007 only. B = Approved Portfolio (Liquidity Sweep
Reversal + Order Block Continuation — identical composition to every
prior report's "Approved Portfolio"). C = Approved Portfolio + S007.

### 2024-01

| Metric | A: S007 only | B: Approved Portfolio | C: Portfolio + S007 |
|---|---:|---:|---:|
| Trades | 2 | 121 | 121 |
| Win Rate % | 0.00 | 33.06 | 33.06 |
| Profit Factor | 0.000 | 0.739 | 0.739 |
| Expectancy | -119.28 | -18.64 | -18.64 |
| Net Profit | -238.56 | -2255.90 | -2255.90 |
| Max DD % | 2.39 | 23.93 | 23.93 |

C is **byte-identical** to B — zero net new trades.

### 2025-03

| Metric | A: S007 only | B: Approved Portfolio | C: Portfolio + S007 |
|---|---:|---:|---:|
| Trades | 4 | 114 | 114 |
| Win Rate % | 50.00 | 36.84 | 36.84 |
| Profit Factor | 1.469 | 0.880 | 0.880 |
| Expectancy | 29.03 | -8.62 | -8.62 |
| Net Profit | 116.13 | -982.23 | -982.23 |
| Max DD % | 2.39 | 19.63 | 19.63 |

C matches B in total count (114) but is **not** trade-for-trade
identical: one new trade was added (`trend_continuation_confluence`,
2025-03-28 07:41 SHORT), displacing none — a different combined-run
open/close history happened to leave the slot free at that exact
moment, discussed in Q2/Q7 below.

## 5. Initial Analysis

**1. Does S007 generate independent trades?**
Yes. Standalone (A) fired 2 trades in 2024-01 and 4 in 2025-03, all
distinctly attributed (`setup_name == "trend_continuation_confluence"`)
and structurally reading different required fields (Liquidity Pool
zones + `structure.bos`) than either Approved Portfolio setup.

**2. Does it overlap with the current portfolio?**
Yes, almost completely — but at the **slot** level, not the
mechanistic level. Every one of S007's 6 standalone fire opportunities
across both windows occurred while the Approved Portfolio already held
an open position. Order Block Continuation alone opened 104-112 trades
per month; with the position capacity that saturated, a setup firing
2-4 times a month has almost no room left. This is the same
cross-bar slot competition already documented elsewhere in this
project (13-57% in earlier measurements), now observed at its
practical extreme against the single highest-frequency setup in the
library.

**3. Does it improve or degrade portfolio performance?**
Materially unmeasurable from this sample. 2024-01: C ≡ B to the last
decimal (0 new trades converted). 2025-03: exactly 1 of 114 trades in C
came from S007 — far too small a sample to read as improvement or
degradation. The finding that actually matters here is structural, not
S007's own performance: **the current Approved Portfolio's trade
capacity is almost entirely consumed by Order Block Continuation**
(already a setup whose own OOS validation showed it failing every
held-out month — see `docs/out_of_sample_validation_report.md`). Any
low-frequency setup added to this portfolio today, regardless of its
own merit, will look like it "does nothing" simply because it never
gets a turn. That is a portfolio-capacity finding, not a verdict on
S007.

**4. Does it introduce new market behaviour?**
Structurally yes — it is the only continuation-thesis setup in the
library (every other setup, S001/S003/S004/S006, is reversal-type; OB
Continuation is nominally continuation but requires no structural or
order-flow context, which its own OOS failure was attributed to).
Standalone performance was directionally different across the two
windows (2024-01: 0% win rate, n=2; 2025-03: 50% win rate, PF 1.469,
n=4) — both samples are far too small to interpret, stated plainly
rather than oversold.

**5. Are the required conditions firing as expected?**
Yes. `price_inside_active_liquidity_pool` and `structural_trend_confirmed`
behaved exactly as the design predicted: because `bos` is level-based
(persists across every bar the break still holds, not edge-triggered),
the raw fire count (30 over 14 days) was an order of magnitude higher
than the actual trade-open count (2) — the same documented pattern
already disclosed in this setup's own docstring, and confirmed against
real data, not just unit tests.

**6. Are the optional confirmations behaving as intended?**
Confirmed correct in isolation (12 of the 22 unit tests exercise
`value_area_confluence` and `cvd_confirms_trend` independently,
including "no data configured" and "wrong direction" cases). Not yet
extracted at the individual real-trade level — the Trade Journal's
`OPENED` event does not carry `evidence_count`/`reasoning`, only the
execution fields, so seeing the live evidence distribution for the 6
real fires would require re-evaluating the engine at those specific
timestamps. Worth doing in the full certification pass; not required
to answer today's architecture question, and not fabricated here.

**7. Does anything appear architecturally inconsistent?**
One real subtlety, not a defect: config C's specific trade set is not
simply "A's fires layered onto B's" — the 2025-03-28 trade that
appears in C but not in A exists because the *combined* portfolio's
open/close history left the position slot free at that exact bar, while
in the S007-only run a still-open earlier S007 trade (from 2025-03-26)
plausibly still occupied it. This is expected path-dependence
already inherent to `BacktestRunner`'s one-trade-at-a-time,
first-registered-setup-wins design — not something S007 introduced,
just the first time this project has traced a concrete example of it
end-to-end for a specific low-frequency setup. Also worth flagging for
the eventual Portfolio Decision Engine: S007 is registered last in
`StrategyEngineV2`'s setup list for Config C, so on any bar where it
ties with LSR or OB Continuation, it loses the tie-break by
construction — a real, disclosed structural disadvantage under the
current "first-registered wins" simultaneous-fire policy, not a bug in
S007 itself.

## 6. What this report does not claim

No certification verdict. No multi-asset check. No out-of-sample
study. No statistical significance test (n=2 and n=4 standalone trades
rule that out outright). These are explicitly out of scope for today's
task and are the natural next step once the architecture and hypothesis
have been confirmed to behave correctly here.
