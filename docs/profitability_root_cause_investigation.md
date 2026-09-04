# Profitability Root-Cause Investigation

**Status: diagnostic report only. No production code, threshold, or configuration was modified to produce this document. No optimization search was run.**

---

## 0. Reproducibility record

- **Repository state:** commit `4b5d8d8376daa4fe7f54d2fff63fa2036e98bf65` (2026-09-03 23:36:29 +0300), plus uncommitted working-tree changes from this session: `backtesting/backtest_runner.py` (modified — additive `exit_policy` hook), and new untracked files `backtesting/exit_policy.py`, `strategy/setups/trend_continuation_confluence.py`, `tests/test_exit_policy_hook.py`, `tests/test_trend_continuation_confluence_setup.py`, plus several `docs/*.md` reports. None of these uncommitted changes alter S001 or S005's behavior; they are additive (S007, the exit-policy hook) and were verified byte-identical to prior behavior when unused.
- **Dataset/symbol:** BTCUSDT, Binance Vision monthly klines, real exchange data (`taker_buy_volume` field confirmed present and genuine, not synthetic, by direct inspection of `data/BTCUSDT-1m-2024-01.csv`).
- **Windows used for the numbers in this report:** 2024-01 and 2025-03 — the same two windows every setup in this project (S006, S007, the Exit Management Sprint) has already been measured against. **This is flagged explicitly in Section 7 as a contamination concern**, not glossed over.
- **Timeframe:** 15m derived from 1m via `TimeframeManager`, decision loop runs on the 1m clock.
- **Initial equity:** $10,000. **Fees:** 0.04% per side. **Slippage:** 0.02% per side, adverse direction always. **Risk per trade:** 1% of current equity, with a 0.6% price-distance floor (`MIN_RISK_PERCENT`). **Reward:** fixed 2R for every setup evaluated here (no dynamic exit is used in the results below — the Exit Management Sprint's structure-trail policy was independently tested and rejected).
- **Setups evaluated:** S001 (Liquidity Sweep Reversal, APPROVED), S005 (Fair Value Gap Rebalance, RESEARCH ARCHIVE), S007 (Trend Continuation Confluence, PENDING) — standalone and in combination. S002/S003/S004/S006 are excluded from this report's quantitative section because they are already REJECTED/OOS-failed and their inclusion would only reproduce known-bad results; their prior findings are cited where relevant to root causes.
- **Exact reproduction:** every number in Sections 3-4 below is mined directly from two already-completed, cached backtest runs from this session (`exit_management_sprint_results.pkl`, `s007_clean_portfolio_results.pkl` in the session scratchpad) plus a new **read-only** post-hoc MAE/MFE reconstruction script (`profitability_investigation.py`) that scans the real 1-minute candles between each already-decided trade's already-recorded entry/exit timestamps. No new strategy decision was made to produce this report; the trades analyzed are the exact trades those runs already produced.

---

## 1. Executive verdict

**The system is not consistently profitable primarily because the dominant setup in every combined-portfolio configuration (S005) has a near-zero-to-negative pre-cost edge, and because the portfolio's one-trade-at-a-time capacity is monopolized by whichever setup fires most often — currently S005 — which suppresses the one setup (S001) that showed a real, substantial edge in one of the two tested windows.** This is a portfolio-construction and setup-quality problem, not primarily a data-integrity or execution-modeling problem: the backtest infrastructure itself is unusually well-built (see Section 2) and no confirmed defect was found that manufactures fake profit or loss. Transaction costs are real and material (10-35% of gross swings) but do not by themselves explain the losses — S005 loses money before fees are even removed, in both tested windows. Win rate, not payoff ratio, is the swing variable between the system's profitable and unprofitable configurations: payoff ratio is remarkably stable (~1.47-1.52) across every setup and every window measured, while win rate swings from 28% (losing) to 62% (winning) — the edge, where it exists, lives entirely in entry selectivity, not in stop/target geometry.

## 2. Trustworthiness assessment of the current backtest

Audited directly against Phase 2's 18-item checklist, by reading `backtesting/point_in_time.py`, `replay_engine.py`, `window_manager.py`, `market_data_provider.py`, `timeframe_manager.py`, `execution_simulator.py`, `trade_setup.py`, `trade_journal.py`, `risk_management.py`, and `analytics/performance.py` in full (not summarized from memory).

| # | Item | Classification | Finding |
|---|---|---|---|
| 1 | Look-ahead bias | **Verified safe** | `get_available_data` filters strictly on `data_timestamp <= current_time`; `TimeframeManager._advance_native` releases a native higher-timeframe candle only once `bucket_close > last_timestamp` fails — explicitly designed to avoid the "candle timestamp is its open time" trap, and its own docstring names that exact trap. |
| 2 | Same-bar retroactivity | **Confirmed defect, already found and fixed this project** | The original `StructureBasedTrailExitPolicy` used a bar's own high/low to move a stop, then checked that same bar against the new stop. Found, fixed (next-bar activation via `apply_pending`/`evaluate` split), re-verified — see `docs/exit_management_sprint_causal_correction_addendum.md`. **Not present in S001/S005/S007's own entry logic** — none of them mutate their own decision using data not yet available to the deciding bar. |
| 3 | Repainting / delayed confirmation used retroactively | **Verified safe, with one disclosed limitation** | Structure fields (`bos`/`choch`/swing levels) are computed from `find_local_extrema`-style fractal pivots requiring bars on both sides — genuinely confirmed, not repainted. `market_structure`'s own docstring self-discloses it as "a crude two-adjacent-candle heuristic" — a **material modeling limitation**, not a repainting defect: it is what it is on every bar, just crude. |
| 4 | Candle/OI/funding alignment | **Verified safe for candles (Zones/Levels/Structure); N/A for OI/funding (not wired to any Setup)** | Traced the full path: a research script builds a 15m array once with `TimeframeManager` (safe, pure aggregation), hands it to `BarSeriesProvider`, which wraps it in a **second, independent** `TimeframeManager` in native mode and re-applies bar-by-bar closing-boundary release during actual replay — the real point-in-time gate is this second layer, driven by the 1-minute clock, not the pre-built array's own order. Confirmed by reading both layers, not assumed. |
| 5 | Timestamp/timezone errors | **Verified safe** | Every timestamp is required to be timezone-aware (`TradeJournal._validate_timestamp` raises otherwise); `historical_loader.py`'s `parse_timestamp` was already audited and fixed for real validation in the prior Repository Integrity Sprint. |
| 6 | Entry on unavailable information | **Verified safe** | Entry decisions run through the same `market_snapshot` construction as everything else; `StrategyEngineV2`/`Setup` only ever receive already-synced tracker snapshots. |
| 7 | Stop/target same-bar ordering | **Material modeling limitation, disclosed by the codebase itself** | `ExecutionSimulator.process_candle`'s `STOP_LOSS_AMBIGUOUS` path conservatively assumes the stop wins when both stop and target are hit in one bar — a real, unavoidable OHLC-bar limitation (true intrabar order is unknowable), resolved in the conservative direction (biases the backtest pessimistic, not optimistic). |
| 8 | Gap handling | **Low-risk limitation** | No explicit gap-fill logic exists; `process_candle` checks `high`/`low` against levels regardless of gap size, meaning a large gap through both stop and target still resolves via the same ambiguous-conservative rule rather than "filled at the gap price" — crypto perpetuals gap far less than equities, but this was not separately stress-tested. |
| 9 | Slippage direction errors | **Verified safe** | `_apply_entry_slippage`/`_apply_exit_slippage` always move the fill price against the trader (LONG entries pay up, LONG exits receive less; mirrored for SHORT) — confirmed by direct formula inspection and by the exact $9.20-on-$46,000 slippage arithmetic verified earlier this session while diagnosing an unrelated test discrepancy. |
| 10 | Fee duplication/omission | **Verified safe** | Fees are charged once per side (`entry_fee` at open, `exit_fee` at close) via `entry_notional * fee_rate`; `TradeJournal.total_fees()` sums both from `CLOSED` events only, no double-counting path found. |
| 11 | Position-sizing errors | **Material modeling limitation, not a defect** | `calculate_position_size` is arithmetically correct (verified: `quantity = risk_amount / risk_per_unit`), but **enforces no leverage or margin cap** — `position_notional` is never checked against equity. In practice the `MIN_RISK_PERCENT = 0.006` floor in the S001/S005/S007 adapter incidentally bounds worst-case leverage to roughly 1.67x at 1% risk, but this is an accident of a different parameter, not an explicit constraint. |
| 12 | Equity/compounding errors | **Verified safe** | `current_equity` only changes on `CLOSED` events (`current_equity += net_pnl`), and `net_pnl` already includes both fees — the code comment explicitly warns against double-deducting, and no double-deduction was found. |
| 13 | Duplicate signals from one event | **Material, setup-specific limitation, already measured** | S005's own docstring self-discloses "a gap can remain partially_filled and inside_price across several consecutive bars" — not a bug, an accepted re-fire characteristic bounded only by the one-trade-at-a-time engine. This is the direct mechanism behind S005's very high trade count (74-89/month) — see Section 4. |
| 14 | Unrealistic fills at extremes | **Verified safe, by design choice** | Stops/targets fill exactly at their own level plus slippage, never at a better intrabar price — a conservative, not optimistic, assumption. |
| 15 | Survivorship/symbol-selection bias | **Not applicable in the tested scope** | Single symbol (BTCUSDT), a listed, still-trading instrument for the entire window — no delisting/survivorship pathway exists in this dataset. |
| 16 | Data gaps/duplicates/corrupted OHLCV | **Verified safe** | `normalize_ohlcv_records` (audited and hardened in the prior Repository Integrity Sprint) rejects duplicate timestamps and OHLC-consistency violations (`high < low`, etc.) outright. |
| 17 | Train/validation/held-out leakage | **Confirmed defect class does not exist in the mechanism, but the discipline has been violated in practice — see Section 7** | `WindowManager._validate_windows` enforces non-overlapping, chronologically ordered windows structurally — there is no code path for one window's data to leak into another. But the *human* discipline of only inspecting HELD_OUT once has not been followed: 2024-01 and 2025-03 have been reused as evaluation windows across S006, S007, and the Exit Management Sprint. This is a process failure, not a mechanism failure — addressed in Section 7. |
| 18 | Hidden control-vs-experimental differences | **Verified safe, directly tested twice this session** | The `exit_policy` hook was verified byte-identical against the pre-change code (trade-for-trade, net-PnL-for-net-PnL) both before and after the causal-correctness fix. |

**Overall: no confirmed defect capable of manufacturing false profit was found. One confirmed defect (same-bar retroactivity in a since-rejected exit policy) was already found and fixed by this project before this report, and did not affect S001/S005/S007's own reported numbers, which never used that policy. The backtest's remaining limitations are disclosed, bounded, and — where they bias anything — bias toward pessimism (ambiguous same-bar resolution, no fill improvement) rather than optimism. The held-out-window discipline has been compromised by repeated reuse and must be treated as contaminated going forward (Section 7).**

## 3. Quantified profitability decomposition

Full metrics, mined from real, already-completed backtests (not re-run for this report):

### 2024-01

| Metric | S001 | S005 | S001+S005 | S007 | S001+S007 | S001+S005+S007 |
|---|---:|---:|---:|---:|---:|---:|
| Trades | 10 | 74 | 79 | 2 | 11 | 79 |
| Win rate % | 30.0 | 35.1 | 34.2 | 0.0 | 27.3 | 34.2 |
| Payoff ratio | 1.52 | 1.49 | 1.49 | — | 1.52 | 1.49 |
| Avg R / Median R | -0.27 / -1.16 | -0.13 / -1.16 | -0.16 / -1.16 | -1.16 / -1.16 | -0.35 / -1.16 | -0.16 / -1.16 |
| Profit factor | 0.653 | 0.805 | 0.776 | 0.000 | 0.571 | 0.776 |
| Net profit | -286.76 | -1020.93 | -1283.57 | -238.56 | -403.26 | -1283.57 |
| Pre-fee P&L | -167.14 | -173.99 | -369.06 | — | — | -369.06 |
| Max DD | 638.27 | 1735.03 | 1530.87 | 238.56 | 752.72 | 1530.87 |
| Longest losing streak | 5 | 8 | 8 | 2 | 6 | 8 |
| Median MAE (R) | 1.03 | 1.03 | 1.03 | 1.12 | 1.03 | 1.03 |
| Reached ≥+1R then still lost | 10.0% | 18.9% | 16.5% | 100%* | 18.2% | 16.5% |

### 2025-03

| Metric | S001 | S005 | S001+S005 | S007 | S001+S007 | S001+S005+S007 |
|---|---:|---:|---:|---:|---:|---:|
| Trades | 13 | 89 | 93 | 4 | 17 | 93 |
| Win rate % | 61.5 | 28.1 | 33.3 | 50.0 | 58.8 | 32.3 |
| Payoff ratio | 1.50 | 1.50 | 1.50 | 1.47 | 1.47 | 1.50 |
| Avg R / Median R | 0.64 / 1.74 | -0.34 / -1.16 | -0.18 / -1.16 | 0.29 / 0.29 | 0.56 / 1.74 | -0.21 / -1.16 |
| Profit factor | 2.395 | 0.586 | 0.750 | 1.469 | 2.104 | 0.716 |
| Net profit | +882.23 | -2711.57 | -1680.27 | +116.13 | +1008.61 | -1925.41 |
| Pre-fee P&L | +1050.00 | -1755.30 | -628.37 | +170.43 | +1237.39 | -876.81 |
| Max DD | 131.29 | 2711.57 | 1680.27 | 247.35 | 338.29 | 1925.41 |
| Longest losing streak | 1 | 6 | 6 | 2 | 2 | 6 |
| Median MAE (R) | 0.78 | 1.04 | 1.04 | 0.69 | 0.78 | 1.04 |
| Reached ≥+1R then still lost | 7.7% | 15.7% | 16.1% | 25.0% | 11.8% | 17.2% |

*S007's own n=2/n=4 samples are too small to draw any conclusion from — included for completeness only, exactly as already flagged in this project's own S007 reports.

**Three findings dominate everything else:**

1. **Payoff ratio is almost perfectly constant (1.47-1.52) across every setup, every combination, and both windows.** This is the single most important structural fact in this investigation: the 2R fixed target combined with zone-edge stops produces a stable realized reward-to-risk geometry regardless of which setup or regime generated the trade. **The edge, wherever it exists, lives entirely in win rate — not in stop/target construction.**
2. **Win rate is the swing variable, and it swings with the calendar month, not with setup identity in a stable way**: S001 alone went from 30.0% (losing) in January to 61.5% (strongly winning) in March. S005 went from 35.1% (losing) to 28.1% (losing worse). Neither setup's win rate is stable across two months — this is the direct, measured reason a 2-window sample cannot yet certify anything (Section 7).
3. **S005 is not merely "high frequency" — it has a negative pre-fee edge in the one window where the difference matters most** (March: -1755.30 pre-fee vs a small January pre-fee loss of -173.99). This rules out "it would be fine without costs" as an excuse; S005's problem is signal quality, and transaction costs make an already-losing setup lose faster, not the other way around.

## 4. Setup-by-setup diagnosis

**S001 (Liquidity Sweep Reversal):** real but **regime-dependent** edge. Positive R even before removing fees in March (+1050 pre-fee on 13 trades), roughly breakeven-to-slightly-negative pre-fee in January (-167 on 10 trades). Sample size (10-13 trades/month) is far too small to certify either result; the two months disagree in sign on win rate (30% vs 61.5%), which this project's own prior OOS methodology (Fisher/Mann-Whitney flagged unreliable below n≈8/arm) already treats as inconclusive at this scale.

**S005 (Fair Value Gap Rebalance):** the dominant trade-count contributor (74-89 trades/month, 6-9x every other setup) with a **negative edge that survives fee removal in the more decisive of the two windows**. Its own docstring already discloses the mechanism: no confirmation gate, no magnitude filter, and a documented multi-bar re-fire characteristic on a single structural event — this is not a hidden flaw, it is exactly what the setup was built to do, and it does it too often. This project's own RESEARCH ARCHIVE status (best standalone PF 0.992 from an earlier, different 30-day window) already flagged it as marginal; two additional independent months now show it clearly net-negative, not marginal.

**S007 (Trend Continuation Confluence):** too rare to diagnose (2 and 4 trades/month) — this report changes nothing about that already-reached conclusion. Notably, its MAE/MFE profile (median MAE 0.69-1.12R, i.e. comparable to the other setups) does not show it behaving pathologically; it simply hasn't fired enough to know.

## 5. Portfolio interaction and crowding diagnosis

This is the most actionable finding in this report. Compare **S001 alone in March** (13 trades, win rate 61.5%, net +882.23) against **S001+S005+S007 in March** (93 trades, win rate 32.3%, net -1925.41). Adding S005 to the portfolio did not merely add its own -2711.57 alongside S001's +882.23 — it **suppressed S001's own trade count and win-rate profile entirely**: the combined portfolio's win rate (32.3%) is close to S005's own standalone win rate (28.1%), not a blend weighted toward S001's much better result, because S005 occupies the single available trade slot on the vast majority of bars where either setup might have fired. **The one-trade-at-a-time engine, combined with a setup that fires 6-9x more often than any other, means the portfolio's realized performance is overwhelmingly determined by whichever setup wins the occupancy race, not by a capital-weighted blend of each setup's own edge.** This exact mechanism — not a flaw in S001 or S007 individually — is the single highest-value, most directly measured root cause in this investigation.

## 6. Regime analysis (explicitly bounded by sample size)

Hour-of-day and day-of-week breakdowns were computed for every configuration. **They are reported for completeness but are not actionable**: with 10-93 trades spread across 24 hours and 7 days, most buckets contain 1-4 trades, and the "best"/"worst" hours/days differ completely between January and March for the same setup (e.g. S005's best day is Friday in January, Thursday in March) — a clear signature of noise, not a real session effect, consistent with the user's own instruction not to draw conclusions from insufficiently sampled cuts. **Open question, not answerable with current data:** whether a genuine session/regime effect exists at all would require a substantially longer, continuous window (a full year at minimum) before any single hour/day bucket has enough independent trades to distinguish signal from noise.

## 7. Trade-level forensic findings

- **"Reached ≥+1R then still lost" occurs in 10-19% of trades across every setup and window** (excluding S007's tiny samples). This directly quantifies the "moved favorably and reversed" failure mode the user asked about. **This project already tested the obvious fix** (move to break-even + structure-based trailing once +1R is reached) in the Exit Management Sprint and measured it net-negative in 6 of 6 tested configurations — the mechanism that creates this 10-19% population (fixed exits, no protection) is real, but the specific correction already tried made things worse by cutting a larger number of genuine full-target winners short than it rescued from this smaller population. This is not a contradiction; it is why "a few visually convincing examples" (Phase 4's own warning) are an unreliable guide, and why that sprint's aggregate, not anecdotal, measurement is the one to trust.
- **Median MAE clusters remarkably close to 1.0R in every single configuration and window** (0.78-1.04R). This means the typical losing trade's worst point during its life is very close to the stop distance itself — stops are not being hit on minor noise well short of 1R (which would indicate "too tight"), nor is price typically travelling far past 1R before the stop catches up (which would indicate "too loose" relative to real volatility). **Stop placement geometry itself does not appear to be the primary problem** — the payoff-ratio stability in Section 3 already pointed to the same conclusion from a different angle.
- **S005 crowding out S001/S007** is not anecdotal — Section 5's numbers are the aggregate proof; the specific mechanism (S005 firing on far more bars, especially since it has no confirmation gate) is directly documented in S005's own module docstring, not inferred.

## 8. Architecture assessment

Separating architecture from strategy-edge questions, as instructed:

- **Setup arbitration:** `StrategyEngineV2.decide()` evaluates every registered setup every bar and takes `fired_setups[0]` (registration order) on a tie — confirmed by direct code reading. This is a real, disclosed limitation (already flagged during S007's own development) but is **not** the primary crowding mechanism measured in Section 5 — the dominant effect is *occupancy* (S005 simply fires on far more bars, so it usually gets there first *and* keeps the slot longer), not the tie-break rule itself. Fixing the tie-break alone would not fix the measured problem.
- **One global open-trade restriction:** confirmed to be the direct mechanism behind Section 5's finding. A cleaner architecture (see Section 9, Portfolio Risk Manager) is necessary but should be evaluated on whether it changes the *measured* crowding numbers, not assumed to help.
- **Signal/event-consumption:** no setup carries state (the `Setup` protocol explicitly forbids it — confirmed by reading `strategy/setups/base.py`), and "cooldown" today is entirely a side effect of each zone/level's own lifecycle plus the trade-slot restriction. This works but conflates "this setup shouldn't re-fire on the same event" with "no other setup can trade at all" — exactly the crowding mechanism in Section 5.
- **O(n²) point-in-time lookup:** confirmed directly in code this session (`ReplayEngine.get_visible_history()` calls `get_available_data()`, which does a full linear scan of `self.records` from index 0 on every single step, not from a cursor) — this affects **research reliability, not backtest correctness**: it does not create wrong numbers, but it makes multi-month backtests (already measured at ~180x slower than linear scaling would predict for a 12x larger dataset) prohibitively slow, which directly limits how much data this investigation itself could analyze in the time available. This is a real bottleneck on the *investigation's own thoroughness*, not a correctness bug.
- **Regime classification:** does not exist as an activation gate anywhere in the current setup library (confirmed: `market_structure` is read only as descriptive metadata by the backtest adapter, never as a firing condition by any of S001/S005/S007).
- **Confidence scores:** none of S001/S005/S007 produce one; the old score-based engine is frozen and unused by any currently-evaluated setup.
- **Reporting system:** sufficient to produce this report's Section 3 (every field needed was already in the Journal), **insufficient for MAE/MFE and true intrabar drawdown** without the ad-hoc script this report had to write — the Trade Journal records entry/exit only, never the path between them, and `analytics/performance.py`'s max-drawdown is computed strictly from closed-trade PnL sequence, meaning **every drawdown number in every report this project has ever produced, including this one's own Section 3 table, understates true mark-to-market drawdown** (it cannot see unrealized pain while a trade is still open). This is a genuine, newly-surfaced reporting gap.

## 9. Ranked recommendations

### A. Corrections (fix regardless of strategy performance)
1. **Disclose the mark-to-market drawdown gap in every future report** (Section 8) — trivial effort, prevents silently understating risk in every certification going forward. *Priority: high, effort: trivial.*
2. **Add an explicit leverage/notional cap to position sizing** (Section 2, item 11) — currently only incidentally bounded by an unrelated floor parameter. *Priority: medium, effort: low.*
3. **Retire 2024-01/2025-03 as a "held-out" claim anywhere it is still used that way** — reclassify as contaminated validation data (Section 7 detail below). *Priority: high, effort: trivial (process change only).*

### B. Improvements to existing behavior (evidence-supported)
1. **Portfolio-level risk/occupancy allocation, not a single global trade slot** — directly targets the Section 5 mechanism, the single best-evidenced improvement in this report. *Impact: high. Evidence: strong (measured, not inferred). Effort: moderate-high (a real architectural change). Overfitting risk: low (a capacity/plumbing fix, not a threshold fit).*
2. **Isolate or reduce S005's fire frequency with a confirmation gate**, mirroring how S001's own "require ≥1 additional confirmation" rule was earned through controlled experimentation. *Impact: high (removes the dominant weak trade population). Evidence: strong. Effort: low-moderate. Overfitting risk: moderate — must be earned through controlled experimentation on train/validation data only, exactly as S001's own gate was, never fit to 2024-01/2025-03.*
3. **Keep S007 in research/pending status until a genuinely fresh window produces ≥8-10 trades** before any certification attempt — already this project's own stated position; this report's evidence changes nothing about it.
4. **Do not re-attempt structure-based dynamic exits without new evidence** — already tested, already measured net-negative in 6/6 configurations. Re-opening this without a different mechanism would be re-litigating a settled measurement.

### C. New modules (evaluated against the 10-point rubric; only justified ones included)

**1. Portfolio Risk Manager / capital-and-slot allocator**
- *Problem solved:* Section 5's crowding mechanism — currently one binary global slot, winner-take-all by occupancy.
- *Why existing architecture can't solve it:* `BacktestRunner`'s one-trade-at-a-time design is a stated, deliberate simplification ("Current limitation (deliberate, not yet lifted)" in its own docstring), not an oversight to patch locally.
- *Inputs/outputs:* per-setup fired signals + current open positions → an allocation decision (which signal, if any, gets capital this bar).
- *Integration point:* between `StrategyEngineV2.decide()` and `BacktestRunner`'s trade-opening step.
- *Point-in-time requirement:* must only ever see already-fired `SetupResult`s for the current bar, nothing about future signals.
- *Complexity:* high — this is the biggest architectural lift in this report.
- *Expected value:* high, directly targets the largest measured root cause.
- *Risks:* a poorly designed allocator could simply recreate winner-take-all with extra steps, or introduce genuine multi-position portfolio risk (correlated drawdowns) that the current single-position design structurally cannot have.
- *Tests:* determinism, replay safety, a regression proving the single-setup-standalone case is unchanged, and a specific test reproducing Section 5's crowding measurement to confirm it actually changes.
- *Acceptance:* measured portfolio win rate/expectancy moves toward a capital-weighted blend of standalone setup performance, not toward the highest-frequency setup's own numbers.

**2. Signal Event Registry / Event-Consumption Manager**
- *Problem solved:* today, "don't re-fire on the same event" is implicit in each zone/level's own lifecycle, which is correct for a single setup but does nothing to prevent two different setups (or a rare one and a frequent one) both wanting the same bar.
- *Why existing architecture can't solve it:* the `Setup` protocol forbids internal state by design (verified in `strategy/setups/base.py`) — a registry is exactly the "state that belongs elsewhere" the protocol's own docstring points to, not something a Setup should own.
- *Integration point:* alongside the Portfolio Risk Manager above — arguably the same module's internal bookkeeping rather than a separate one; listed separately only because it has a distinct, narrower responsibility (identity/dedup, not capital allocation).
- *Complexity:* moderate. *Expected value:* moderate, mostly in combination with #1.
- *Acceptance:* measurable reduction in the "duplicate signal from one structural event across bars" population already characterized in Section 4/S005.

**3. MAE/MFE Analytics Module**
- *Problem solved:* Section 8's reporting gap — no report in this project's history, including this one without the ad-hoc script, could answer "were stops/targets well placed" quantitatively.
- *Why existing architecture can't solve it:* `TradeJournal` records entry/exit only; the information needed (intrabar path) exists in the replay but is never captured.
- *Inputs/outputs:* entry/exit timestamps + underlying candle series → MAE/MFE in R per trade, aggregable by setup/regime.
- *Integration point:* an optional hook in `BacktestRunner`, symmetric to the `exit_policy` hook already added this session — same "additive, opt-in, byte-identical when unused" pattern.
- *Complexity:* low (this report's own script is most of the implementation). *Expected value:* moderate-high — this is cheap and already proven useful in this very report.
- *Acceptance:* every future setup certification report includes MAE/MFE without a bespoke script.

**4. Data Quality and Point-in-Time Integrity Validator**
- *Problem solved:* today, safety is verified by hand, per-setup, in prose (as this report and every prior one have done). A repository-wide automated check exists nowhere.
- *Why existing architecture can't solve it:* `PointInTimeViolation` exists as an exception class but nothing systematically runs every tracker/setup through an adversarial "does this ever see the future" harness.
- *Complexity:* moderate. *Expected value:* moderate — mostly insurance against regressions, not a source of new edge.
- *Acceptance:* a new tracker or setup cannot be certified without passing this validator, replacing the current per-setup manual replay-safety script pattern.

### Not recommended, and why

- **Market Regime Classifier as a new module:** the raw ingredient (`market_structure`) already exists; the gap is that nothing *uses* it as a gate, not that it's missing. Building a new classifier before using the existing one would be solving the wrong layer.
- **Walk-Forward Validation Engine, Monte Carlo/Bootstrap module, Parameter Stability Analyzer:** all are legitimate ideas in general, but **premature here** — with 10-93 trades per configuration, none of these techniques can produce a meaningful result yet (a bootstrap CI on 10 trades is close to meaningless). Building this tooling now would produce impressive-looking but uninformative output. Revisit once the Portfolio Risk Manager (above) produces a portfolio with enough independent trades to make walk-forward/bootstrap analysis worth running.
- **Setup Correlation and Signal-Overlap Analyzer as a standalone module:** this report's Section 5 already did this analysis by hand using existing cached results with no new module — build it only if this kind of analysis becomes a recurring, frequent need, not preemptively.
- **Experiment Registry with config hashing, Drift/Live-vs-Backtest Monitoring:** both are real needs for a *production* trading system, but this system has no live trading path yet — building monitoring for a system that has never run live is solving a problem that does not exist yet.
- **Execution Quality and Cost Model beyond what exists:** the current fixed fee/slippage model is simple but was not found to be a primary root cause (Section 3's pre-fee P&L numbers show S005 loses even before costs) — a more sophisticated cost model would refine a secondary factor, not the primary one.

## 10. Robust research design going forward

**The existing 2024-01/2025-03 "validation" windows are contaminated and must not be used as a final held-out claim again.** They have been directly inspected and used to inform decisions (setup selection, exit-policy rejection, this very report) repeatedly across S006, S007, and the Exit Management Sprint this session alone. Per the user's own stated rule, this is classified as contaminated, not a genuine blind test.

**Proposed fresh, untouched final holdout:** the multi-asset dataset already downloaded for this project includes full 2024-2025 BTCUSDT coverage. A month not yet inspected by any decision in this project (e.g., 2024-09 or 2025-08 — to be drawn by the same documented-random method already used for the 2025 month selection, and then genuinely not looked at until a final certification run) should be reserved now and never touched during development. This report does not draw that month itself, to avoid pre-empting the user's own choice of when to lock it.

**Process going forward:**
- Use 2024-01 and other already-seen months freely for hypothesis formation and threshold decisions (they are contaminated for certification, but not wasted — they are now legitimately TRAIN-tier data).
- Reserve a second, still-clean month as VALIDATION for model/setup selection.
- Touch the new final holdout exactly once, at the end, for a single confirmation run.
- Any future setup (S008-S011 from the Phase 4 proposal, or a redesigned S005) must clear a minimum independent-trade-count bar (this report suggests ≥30, informed by the n=10-13 samples that already produced sign-flipping win rates between two months) before its win rate/expectancy is treated as more than a hypothesis.

## 11. Smallest high-confidence implementation sprint to run first

Given everything measured above, the single highest-value, lowest-overfitting-risk, smallest first step is:

**Build the MAE/MFE Analytics hook (New Module #3) and re-run S001/S005/S007 standalone and combined on the still-unused TRAIN-tier months already downloaded (not 2024-01/2025-03) — no strategy change, no threshold change — purely to convert this report's ad-hoc script into a repeatable, committed capability and to see whether the payoff-ratio-stability / MAE-clusters-at-1R findings (Section 3/7) replicate on data this investigation has not yet looked at.** This is deliberately the smallest, most measurement-only sprint possible: it adds no new logic that could change a backtest result, it directly extends something already proven useful in this exact report, and it produces the evidence needed to decide whether Recommendation B.2 (an S005 confirmation gate) is worth designing at all — without touching S005 itself yet.

**Stopping here. No code will be modified, no threshold changed, and no new module implemented without your explicit approval of a specific item from Section 9.**
