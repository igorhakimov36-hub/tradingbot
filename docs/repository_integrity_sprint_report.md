# Repository Integrity Sprint — Final Report

Scope, exactly as instructed: resolve only the issues the Repository
Audit discovered. No feature work, no optimization, no architectural
change. Files touched this sprint: `data/historical_loader.py` and
`docs/strategy_engine_v2_audit.md` — confirmed via `git status`, nothing
else. Every explicitly deferred item (Strategy Engine V2, Setup
Library, Coordinator, Snapshot, Backtest Adapter, Portfolio research,
`COMMON_SMT_PAIRS`, Legacy Engine, Setup Registry) was left untouched.

---

## 1–3. Every issue fixed, why it existed, how it was fixed

### Issue A — ISO-8601 timestamp strings were never actually supported

**Why it existed:** `parse_timestamp()`'s string branch unconditionally
did `parse_timestamp(float(value))` — treating every string as a
numeric epoch value. Any ISO-format string (`"2025-01-01T12:00:00Z"`)
failed with `ValueError: could not convert string to float`. This was
never exercised by real data (every actual downloaded CSV uses numeric
`open_time` in milliseconds), only by test fixtures written to a
different, generic-timestamp contract.

**How it was fixed:** the string branch now tries the existing numeric
path first (preserving all real-data behavior exactly), and only on
failure falls back to `datetime.fromisoformat(value.replace("Z", "+00:00"))`,
routed back through `parse_timestamp` for the same UTC normalization
every other input type already gets. Real CSV timestamps (`"1704067200000"`)
still succeed on the first attempt and never reach the new fallback path.

### Issue B — no OHLC relationship validation existed, despite five tests claiming to enforce it

**Why it existed:** `normalize_ohlcv_record()` converted `open`/`high`/
`low`/`close`/`volume` to floats and stopped — no cross-field check ever
existed. Verified empirically (not inferred) before any fix was written:
calling the function directly with a numeric timestamp (bypassing the
ISO bug) and a `high < low` record, and separately a negative-volume
record, both were silently accepted. The five tests named for this
behavior (`test_high_below_low_is_rejected`, `test_high_below_close_is_rejected`,
`test_low_above_open_is_rejected`, `test_negative_volume_is_rejected`,
`test_duplicate_timestamp_is_rejected`) were passing only because their
ISO-format timestamp fixtures triggered Issue A's `ValueError` before
the code ever reached the (nonexistent) validation they were named for.

**How it was fixed:** `normalize_ohlcv_record()` now validates, after
converting to floats and before returning: `high >= low`, `high >= open`
and `high >= close`, `low <= open` and `low <= close` — the complete,
symmetric candle-validity constraint (not just the three specific
one-sided cases the existing tests happened to name), and `volume >= 0`.
`normalize_ohlcv_records()` now rejects a duplicate timestamp after
sorting (a single linear pass over adjacent pairs).

### Issue C — a column-name mismatch, found while fixing Issue A, not a pre-existing masked test

**Why it existed:** `load_ohlcv_csv()` unconditionally read `row["open_time"]`
(the real Binance Vision column name). One test's CSV fixture used a
plainer `"timestamp"` header instead, causing an immediate `KeyError`
— a failure visible in every test run this project has had, already
counted among the "4 pre-existing failures," but never previously
root-caused past "the ISO timestamp bug." Investigating Issue A
revealed this second, independent cause in the same test.

**How it was fixed:** `load_ohlcv_csv()` now accepts either `open_time`
(Binance Vision's real column, used first) or `timestamp` as a fallback
— the same "accept an equivalent alternate name" pattern the function
already used for optional `taker_buy_volume`. Every real file in this
project has `open_time` and is completely unaffected; the fallback path
is only ever reached by the one test fixture that needed it.

---

## 4. Whether any behavioural change occurred

**None, for any real data or any existing decision path.** Verified,
not assumed:
- Every `.csv` file in `data/` that `load_ohlcv_csv()` is actually used
  for (100 of 109 files — the other 9 are funding-rate/open-interest
  files with a different schema, loaded by their own dedicated loaders,
  never by this function) loads with **zero exceptions** under the new
  validation.
- Spot-checked row counts for five files across the dataset
  (`BTCUSDT-1m-2024-01`, `-2024-02` leap-year February, `-recent30d`,
  `ETHUSDT-1m-recent30d`, `XRPUSDT-1m-2025-12`) are **identical** to
  their previously-recorded counts.
- Re-ran the exact three backtests from the S002 report
  (`LiquiditySweepReversalSetup` alone, `OrderBlockContinuationSetup`
  alone, both combined) end-to-end after the fix: **13, 59, and 60
  trades respectively — byte-identical to the original report.** This
  is the strongest available confirmation that Strategy Engine V2,
  every setup, the Coordinator, and the adapter behave exactly as
  before, since none of them were touched and the data they consume is
  provably unchanged.

The only behavioral change anywhere is that `load_ohlcv_csv()`/
`normalize_ohlcv_record()` will now raise `ValueError` on malformed
input (bad OHLC relationships, negative volume, duplicate timestamps,
or a truly unparseable timestamp string) that it previously accepted
silently — this is the intended fix, not a side effect, and it does
not fire on any data this project currently uses.

`docs/strategy_engine_v2_audit.md` — a documentation-only change. Three
sentences that are no longer accurate (given S003/S004, built after
this document was written) were annotated in place with `[SUPERSEDED]`
markers explaining exactly what changed and citing which later setup
changed it. No other sentence, table, or section was edited or
reworded.

---

## 5. Regression results

- `tests/test_historical_loader.py`: **16/16 passed** (was 12/16). All
  four previously-failing tests now pass for the reason they were
  written to verify, confirmed by direct inspection of which code path
  each one now exercises — not merely by the test going green.
- Full suite: **749 passed, 0 failed** (was 745 passed, 4 failed — the
  count increased by exactly 4, matching the four tests that now pass
  genuinely; no test was skipped, deleted, or weakened to reach this
  number).
- Live backtest re-run: 13 / 59 / 60 trades, exactly matching the
  original S002 report — zero replay regression, zero setup behavior
  change, zero Strategy Engine behavior change, demonstrated directly
  rather than argued from "nothing else was touched."

---

## 6. Remaining technical debt, intentionally left for future milestones

Everything the audit found but this sprint was explicitly told not to
touch:
- `COMMON_SMT_PAIRS` remains defined and tested but unused by any
  runtime code path.
- `strategy/setups/__init__.py` remains empty — no committed registry
  of which setups exist or which are currently approved.
- The two coexisting pipelines (Strategy Engine V2 and the legacy
  `strategy_engine.py`/`decision_engine.py` scoring engine) remain
  fully separate and both fully functional, with no marker indicating
  which one a new reader should trust.
- No canonical "Approved Portfolio" module exists in committed code;
  that fact still lives only in documentation and disposable research
  scripts.

None of these were touched this sprint, as instructed — they are
deferred, not forgotten.
