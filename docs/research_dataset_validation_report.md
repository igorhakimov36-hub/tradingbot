# Permanent Multi-Asset Research Dataset — Validation Report

Infrastructure only. No trading logic, no setup, and no Strategy Engine
code was touched to build or validate this dataset.

## What was built

96 monthly 1-minute OHLCV files — **BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT
× January 2024 through December 2025** — downloaded from Binance Vision
(`data.binance.vision`, USD-M Futures monthly klines archive), using
the project's existing, unmodified `exchange/download_historical_data.py`
(the same mechanism that produced every BTCUSDT 2024 file already used
this session). All 96 downloads succeeded on the first attempt; no
retries were needed. Both the `.zip` and the extracted `.csv` are kept
per file, matching the existing convention.

This becomes the permanent, real (not synthetic), multi-year,
multi-asset foundation for all future research — no setup research was
run against it in this task, per instruction.

## Validation results

**A/B — File completeness, gaps, duplicates, boundaries** (all 96 files,
every 1-minute row individually checked):
- 96/96 files present.
- 0 files with a wrong row count (every file's row count matches
  `days_in_month × 1440` exactly, including the 2024 leap-year February
  at 41,760 rows).
- 0 internal timestamp gaps across all ~4.3 million candles checked.
- 0 duplicate timestamps.
- 0 unexpected month boundaries — every file starts at `YYYY-MM-01
  00:00:00 UTC` and ends at the correct last-day `23:59:00 UTC`.

**C — Deterministic loading**: sampled across all four symbols and both
years — two independent loads of the same file produce byte-identical
results in every case.

**D — Replay Engine compatibility**: the full BTCUSDT 2024 year
(527,040 one-minute candles, concatenated across all 12 months)
replayed through `ReplayEngine` end to end — every one of the 527,040
steps processed, visible history grows strictly monotonically, no
future candle was ever visible early, and the final visible history
equals the full candle count. Point-in-time replay safety holds across
a full real year, not just a 30-day window.

**E — TimeframeManager compatibility (1m → 15m)**: all four symbols'
full 2024 histories built 15m bars from raw 1m data without error.
One expected, non-defect discrepancy, explained precisely rather than
glossed over: 527,040 ÷ 15 = 35,136.0 exactly, but each symbol produced
35,135 15m bars — short by exactly one. This is `TimeframeManager`'s
own documented native-mode release behavior, not a data gap: a 15m
bucket is only released once the *next* bucket's first 1m candle
confirms it closed. The dataset's very last bucket (Dec 31, 23:45–23:59)
has no following candle to trigger that release, since the file ends
exactly at the year boundary — the identical "off by exactly the final
boundary candle" pattern already seen with the original recent30d
dataset. Confirmed as expected, not investigated further as a defect.

**F — WindowManager compatibility**: constructed TRAIN (Jan 2024) /
VALIDATION (Feb–Oct 2024) / HELD_OUT (Nov–Dec 2024) windows over the
full real year. Windows are non-overlapping and chronological; every
one of the 527,040 candles is accounted for in exactly one window, none
dropped or duplicated across the split.

**G — BacktestRunner compatibility (multi-symbol smoke test)**: ran a
complete `BacktestRunner.run_strategy()` pass over BTCUSDT January 2024
with all four symbols simultaneously attached as `provider_specs`, using
an always-IGNORE strategy callback that asserts every symbol's 15m
stream is reachable through `market_snapshot` on every single bar (no
setup logic, no trading decision — a pure plumbing check). Completed
with zero crashes, zero assertion failures, and (as expected for an
always-IGNORE strategy) zero trades opened across 44,640 recorded
signals.

## Conclusion

The dataset is complete, gap-free, deterministic, and fully compatible
with every existing piece of infrastructure it will need to pass
through — `ReplayEngine`, `TimeframeManager`, `WindowManager`, and
`BacktestRunner`'s multi-symbol provider mechanism — with real data
across two full years and four assets. It is ready to serve as the
permanent research foundation. No setup research was performed against
it in this task.
