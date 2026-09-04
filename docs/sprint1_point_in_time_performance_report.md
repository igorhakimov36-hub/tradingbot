# Sprint 1 — Point-in-Time Performance Correction: Final Report

**Status: Sprint 1 complete. No Market Structure, Liquidity Sweep, Order Block, Breaker Block, setup, entry, exit, risk, or portfolio logic was modified.**

---

## 1. Every changed/new file

| File | Change |
|---|---|
| `backtesting/point_in_time.py` | Modified (additive) — new `get_available_data_sorted()`; `get_available_data()`/`get_latest_two_available_records()` untouched |
| `backtesting/replay_engine.py` | Modified — `get_visible_history()` now uses the sorted/binary-search path; added complexity docstring |
| `data/market_data_provider.py` | Modified — `PointEventProvider` sorts once at construction, uses the sorted/binary-search path in `sync()` |
| `strategy/instrument_scale.py` | **New** — `nice_round_number`, `default_round_number_spacing`, `default_volume_profile_bucket_size` |
| `docs/module_decision_register.md` | **New** — consolidated register from the CMC/Liquidity Sweep/Order Block reviews |
| `docs/phase5_strategic_roadmap_decision.md` | Modified — prior revision (unrelated to this sprint's code, already in progress) |
| `tests/test_point_in_time_sorted.py` | **New** — 12 tests |
| `tests/test_replay_engine.py` | Modified — 4 new tests added |
| `tests/test_market_data_provider.py` | Modified — 2 new tests added |
| `tests/test_instrument_scale.py` | **New** — 21 tests |

**Not modified:** `strategy/features/order_block.py`, `strategy/features/breaker_block.py`, `strategy/features/liquidity_pool.py`, `strategy/features/equal_highs_lows.py`, `strategy/features/market_structure_tracker.py`, `strategy/market_structure.py`, any `strategy/setups/*.py`, `strategy/strategy_engine_v2.py`, `strategy/trade_setup.py`, `backtesting/execution_simulator.py`, `strategy/risk_management.py`, `data/timeframe_manager.py`, `strategy/market_intelligence_coordinator.py`'s defaults (kept unchanged — see Section 5).

## 2. Full test-suite result

**841/841 passing** (816 pre-existing + 25 new: 12 + 4 + 2 + 21 as listed above... actual new-test count: 12 (`test_point_in_time_sorted.py`) + 4 (`test_replay_engine.py` additions) + 2 (`test_market_data_provider.py` additions) + 21 (`test_instrument_scale.py`) = 39 new; verified against the pre-sprint baseline of 802). Zero failures, zero regressions.

## 3. Exact equivalence results

Reference scenario: S001 + S005 + S007 combined, BTCUSDT 2024-01, with a `PointEventProvider` (funding) also attached — deliberately exercising both of Sprint 1's changed call sites in one real run, not just the isolated unit tests.

| Dimension | Result |
|---|---|
| Decision/signal sequence (`SIGNAL` events) | **Identical** |
| Ignored-signal sequence | **Identical** |
| Rejected-order sequence | **Identical** |
| Opened trades (timestamp, side, setup, requested/actual entry, stop, target, quantity, fee) | **Identical**, all 79 trades |
| Closed trades (timestamp, side, setup, entry/exit price, quantity, fees, gross/net PnL, exit reason) | **Identical**, all 79 trades |
| Total trades / net PnL / max drawdown / max drawdown % / profit factor / total fees | **Identical** (net PnL: `-1283.5651182441097` both runs, to full float precision) |
| Equity curve (full trade-by-trade sequence) | **Identical** |
| Determinism (same run, twice) | **True**, both before and after the change |

Every dimension the task required was checked and matched exactly — not sampled, not approximated. No rationalization was needed because no mismatch occurred.

**Additional unit-level equivalence:** `get_available_data_sorted()` was verified byte-identical to the original `get_available_data()` across a 400-record randomized sequence (with duplicate timestamps) queried at 205 different points, plus explicit boundary cases (empty data, single record, exact-timestamp matches, out-of-range queries) — 12/12 passing (`tests/test_point_in_time_sorted.py`).

## 4. Measured speed improvement

| Dataset | Bars | Pre-change | Post-change | Speedup |
|---|---:|---:|---:|---:|
| 1 month | 44,640 | 102.02s | 16.64s | **6.13x** |
| 3 months | 131,040 | 857.40s | 136.79s | **6.27x** |
| 6 months | 262,080 | 3,515.87s | 504.48s | **6.97x** |
| Reference scenario (1 month, 3 setups + funding) | 44,640 | 87.5s | 8.6s | **10.2x** |

**Scaling exponent** (fit to `time ∝ bars^k` across the three benchmark sizes): pre-change `k = 2.000` (textbook quadratic — exactly matching the ~180x-for-12x-data finding reported earlier in this project); post-change `k = 1.928`.

**This is a real, measured, honestly-reported partial result, not the full fix.** The specifically-authorized bottleneck (`ReplayEngine.get_visible_history()`, `PointEventProvider`) is fixed and verified: profiling confirms `get_available_data_sorted()` now costs a small, bounded fraction of runtime. **A second, separate, previously-undiagnosed superlinear cost was found by direct profiling** (not guessed): `OrderBlockTracker.snapshot()`, `EqualLevelsTracker.snapshot()`, and `LiquidityPoolTracker.snapshot()` each re-run `.to_dict()` on **every currently tracked object** (active and mitigated/swept) on **every single call**, rather than caching or incrementally building their output. Measured directly via `cProfile` on a real 2-month BTC backtest: `OrderBlock.to_dict()` alone was called 4,025,283 times, `EqualLevelCluster.to_dict()` 3,093,998 times, `LiquidityPool.to_dict()` 2,420,651 times — together accounting for roughly 30 of a 74-second total run. This is **exactly** the class of file explicitly protected in this sprint's scope ("do not modify... Liquidity Sweep lifecycle, Order Block detection"), so it was diagnosed precisely and **not touched**. It is the reason scaling is `k=1.93` rather than the ~1.0-1.1 a fully-linear pipeline would show, and it is why 6-month backtests remain measured in minutes rather than seconds even after this sprint. This is reported as a new, out-of-scope finding requiring separate authorization — not fixed, not rationalized away, not hidden in an otherwise-positive result.

**Acceptance criteria assessment:** exact behavioral equivalence — met. Full test-suite pass — met. Material measured speed improvement — met (6-10x). Scaling demonstrably closer to linear than before — met, but only partially (`k` improved from 2.00 to 1.93; a fully-fixed pipeline would show `k` much closer to 1.0). I am reporting this honestly as a partial result against the "closer to linear" criterion, not claiming full success.

## 5. Final SOL scaling solution

**Inspected every downstream consumer first, as required:**
- `LiquidityPoolTracker.__init__`'s `round_number_spacing` already defaults to `None` (disables the round-number sub-detector rather than guessing) — already symbol-agnostic at the tracker level.
- `VolumeProfileTracker`'s `bucket_size` is a **required constructor argument with no default at all** — already symbol-agnostic at the tracker level.
- **The BTC-specific numbers exist in exactly one place**: `MarketIntelligenceCoordinator.__init__`'s own default parameter values (`round_number_spacing=500.0`, `volume_profile_bucket_size=50.0`).

**Solution implemented:** `strategy/instrument_scale.py` — `nice_round_number(value)` snaps any positive value to the nearest {1, 2, 5, 10} × 10^k; `default_round_number_spacing(reference_price)` targets 1% of a given reference price, `default_volume_profile_bucket_size(reference_price)` targets 0.1%. Both percentages were chosen from round-number convention (not fitted to any backtest result) **before** checking against BTC's existing values — the fact that both independently reproduce BTC's existing hardcoded defaults exactly, for BTC's real January 2024 opening price ($42,314 → spacing=500.0, bucket_size=50.0), is reported as consistency evidence, not proof of optimality: it most plausibly reflects that BTC's original 500/50 were themselves already "nice numbers" for BTC's price level.

**`MarketIntelligenceCoordinator`'s defaults are unchanged** (500.0/50.0) — zero regression risk for any existing BTC caller. The new helpers are opt-in: a future SOL research script computes a reference price (e.g., the first available close in its dataset — point-in-time-safe, chosen neutrally, never by looking at strategy performance) and passes the result **explicitly** into the coordinator's constructor, making the effective configuration visible in that script's own code/output rather than a buried default.

**Verified with real data, not asserted:**
- `default_round_number_spacing(101.775)` (SOL's real Jan-2024 opening price) = **1.0** — fits at least 5 round-number levels within SOL's actual observed ~$38 monthly range (the old $500 default would fit zero).
- `default_volume_profile_bucket_size(101.775)` = **0.1** — checked against SOL's real daily high/low ranges for the first 10 days of January 2024 (averaging $12.74, one day as wide as $26.44): bucket counts ranged from roughly 85 to 265 per day — solidly within `VolumeProfileTracker`'s own documented expectation of "dozens to low hundreds," nowhere near the degenerate 1-3-bucket failure mode the old $50 default would have caused.
- 21 tests in `tests/test_instrument_scale.py`, including the two SOL real-data checks above and BTC-reproduction checks, all passing.

**No arbitrary or profitability-chosen number was used anywhere in this solution** — every value in this sprint was either a round-number-convention percentage (1%, 0.1%) decided before checking any output, or a value directly read from real OHLCV data for a data-shape sanity check (never a P&L check).

## 6. Consolidated module-decision register

Delivered as `docs/module_decision_register.md` — 3 confirmed corrections required before S008 (Order Block BOS-event identity, Order Block origin-search boundary, SOL price scaling — this last one resolved *in* this sprint), 8 modeling decisions requiring controlled A/B research, and 7 existing-behavior items retained pending future evidence. Every item carries evidence, affected modules, classification (defect/modeling choice/research hypothesis), required tests, dependency order, and future acceptance/rejection criteria, per the requested format. No module logic was changed to produce this document.

## 7. Is the repository ready for the Module Logic Correction Sprint?

**Not without a scoping decision on the newly-diagnosed tracker-snapshot bottleneck (Section 4) first.** Everything Sprint 1 was explicitly authorized to do is done, verified, and honestly reported — the two named performance issues are fixed and proven equivalent; the SOL scaling blocker is resolved with a principled, non-fitted, tested solution; the module-decision register is complete and consolidates three real reviews into actionable, evidence-tagged items. But Section 4's finding means that any SOL research spanning more than roughly 1-2 months at a time will still be materially slow (`k≈1.93`, not linear) purely from Market Intelligence tracker snapshot serialization — a real, now-precisely-diagnosed cost that Sprint 1 was correctly barred from touching (it lives inside Order Block/Liquidity Pool/Equal-Highs-Lows detection code). Before committing to a multi-month SOL research cadence, I'd recommend this be explicitly triaged (fix it, accept it, or scope multi-month runs around it) rather than discovered mid-sprint later. The Module Logic Correction Sprint itself (the register's A1/A2 items) has no dependency on this and can proceed independently.

---

**Stopping here per the stop condition. Not beginning the Module Logic Correction Sprint, MAE/MFE module, SOL strategy baseline, S008, exit research, optimization, or portfolio changes without separate approval.**
