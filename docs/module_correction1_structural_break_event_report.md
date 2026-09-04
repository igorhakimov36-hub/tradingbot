# Module Logic Correction 1 — Additive Structural Break Event Identity

**Verdict: STRUCTURAL BREAK EVENT ACCEPTED — ready for Order Block correction**

## Git checkpoint

1. `git status` at sprint start showed a clean working tree (Sprint 1B had just
   been committed).
2. Sprint 1B's checkpoint: `3fe7585` ("Sprint 1B: cache tracker snapshot
   serialization, fix redundant double-call cost"), on top of Sprint 1's
   `a4b1911`, both confirmed present via `git log`.
3. Sprint 1B was committed as its own clean checkpoint (7 files: the 4 modified
   trackers, 2 new test files, and the Sprint 1B report — exactly the files
   flagged by `git status`, nothing else) before this correction began.
4/5. No unrelated files were included; nothing was pushed, merged, rewritten,
   deleted, or reverted.
6. New commit hash: `3fe7585` (Sprint 1B checkpoint).
7. Working tree confirmed clean (`git status --short` empty) immediately before
   this correction's first edit.

This correction's own changes are **not committed** — left in the working tree
per the pattern used throughout this project (commit only when asked).

## 1. Design decision for event identity

`StructuralBreakEvent` (new, `strategy/features/market_structure_tracker.py`):
a frozen dataclass carrying `direction` ("bullish"/"bearish", lowercase to stay
visually distinct from the existing uppercase `BULLISH_BOS`/`BEARISH_BOS`
enums — a different concept, not a replacement), `level` (the broken price),
`pivot_timestamp` (the identity of the broken swing/pivot), `confirmed_at` (the
breaking candle's timestamp), `confirming_close`, and a deterministic
`event_id` string (`f"{timeframe}:{direction}:{pivot_timestamp!r}"`).

**Identity choice — pivot timestamp, not a new index scheme.**
`strategy/market_structure.py`'s `find_swing_pivots()` already returns
`(index, price)` pairs for every confirmed pivot — it was simply never called
from `MarketStructureTracker` before (only `get_last_swing_levels()`, which
discards the index, was used). No change to `market_structure.py` was needed:
the tracker now additionally calls `find_swing_pivots()` itself, maps the
returned local index back to the actual candle in `self._recent_candles`, and
uses that candle's own timestamp as the pivot's stable identity. A local
in-window index could not itself serve as a durable identity, since
`_recent_candles` is a sliding window that pops from the front once
`structure_lookback` is exceeded — every candle's own timestamp is stable
across that sliding regardless.

**A pivot fires at most one event, tracked via a consumed-pivot set** keyed on
`(direction, pivot_timestamp)`. Direction is part of the key because a swing
high and a swing low are different structural objects even in the
(exceedingly unlikely) case they share a timestamp.

## 2. Exact crossing semantics

- **Close-based, strict inequality** (`close > level` / `close < level`),
  identical to `detect_bos`'s own existing convention — chosen for consistency
  with the existing persistent BOS definition, not for any other reason. An
  exact close at the level does not fire (test: exact-close case).
- **Wick beyond, close inside:** does not fire — only `close` is ever compared,
  never `high`/`low` (test: wick-beyond case).
- **Pivot confirmed while price is already beyond it:** fires immediately, on
  the bar the pivot first becomes the recognized "last" pivot — this is when
  the break first becomes knowable, and is not a backdated event to the
  pivot's own earlier candle. **Alternative considered and rejected:**
  requiring an edge relative to the *previous* bar's close (previous close
  below the level, current close above it). This was rejected because it would
  permanently miss a level that was already broken by the time it became the
  tracked "last" pivot — violating "every distinct broken level produces
  exactly one event." Recorded here as the unresolved alternative, per
  instruction, in case future research wants to revisit it.
- **Gaps across a level:** handled identically to a smooth crossing — only the
  current bar's close is ever compared, so no separate gap-detection logic
  exists or is needed.
- **New swing level appearing while the previous break state persists:**
  handled by per-pivot-identity consumption — a new, distinct pivot is a new
  key in the consumed set regardless of what has already fired.
- **Several candidate swing levels in the same direction:** only the single
  *most recent* confirmed pivot (`swing_highs[-1]`/`swing_lows[-1]`) is ever
  evaluated per bar — identical restriction to what `get_last_swing_levels`
  has always applied to `bos`/`choch`. An earlier pivot that gets superseded
  before ever being tested (price never closed beyond it while it held "last"
  status) correctly never produces an event — it was never actually broken.

## 3. Changed files

```
strategy/features/market_structure_tracker.py | 147 ++++++++++++++++++++++-
1 file changed, 147 insertions(+), 1 deletion(-)
```
Plus one new test file (untracked): `tests/test_structural_break_event.py`.
No other file was touched — confirmed by `git diff --stat`. In particular,
`strategy/market_structure.py`, `OrderBlockTracker`, `_detect_new_order_block`,
`_find_last_opposite_candle`, `LiquidityPoolTracker`, `BreakerBlockTracker`,
every setup (S001/S005/S007, the proposed S008), and all entry/exit/risk/
execution/portfolio logic are untouched.

## 4. New tests

16 tests in `tests/test_structural_break_event.py`, all passing:

- The required failing characterization test, written and confirmed failing
  (`KeyError`/missing field) before implementation, now passing:
  `test_new_distinct_level_break_fires_new_event_without_intervening_no_bos` —
  breaks swing high A (110.0, event A fires), then a new, distinct, higher
  swing high B (118.0) is confirmed and broken on a later bar while `bos`
  stays `BULLISH_BOS` continuously throughout — event B fires exactly once,
  with a distinct `event_id` and `pivot_timestamp` from event A.
- Repeated closes beyond the same level do not re-fire.
- Two distinct same-direction levels produce two distinct events.
- Bullish/bearish symmetry (mirrored fixtures, both directions verified).
- Exact close at the level does not fire.
- Wick beyond with close inside does not fire.
- Pivot confirmation timing (`pivot_timestamp` is the pivot's own candle,
  `confirmed_at` is the later breaking candle, and they differ).
- No event backdating, including the "pivot confirmed while price already
  beyond it" case (event fires on the confirmation bar, not the pivot's own
  earlier bar).
- Independent tracker instances share no consumption state (reset/new-window
  behavior — there is no in-place `reset()` method on this tracker; a fresh
  instance is the existing convention, confirmed clean by this test).
- Repeated `snapshot()` calls are idempotent and do not re-consume; re-`sync()`
  with a non-extended candle list is a no-op (guarded by the tracker's
  existing `_consumed` check) and does not alter the latest event.
- Deterministic event IDs across independent runs of the same candle sequence,
  and IDs differ by direction even at an identical timestamp.
- Bounded event-consumption memory: a 400-candle choppy zig-zag sequence with
  `structure_lookback=10` never lets the consumed-pivot set exceed 10 entries.
- No duplicate independent event when persistent `bos` and `choch` are
  simultaneously true for the same underlying level break (hand-verified
  precondition: a bearish-regime window where the close breaks the existing
  swing high, making `detect_bos` return `BULLISH_BOS` and `detect_choch`
  return `BULLISH_CHOCH` from the identical comparison) — exactly one event
  fires.
- Existing persistent fields (`market_structure`, `last_swing_high`,
  `last_swing_low`, `bos`, `choch`) remain byte-for-byte identical to an
  independently recomputed reference at every bar of a run that also produces
  break events, and `structural_break_event` is confirmed to be a field the
  reference computation never had — i.e. purely additive.

## 5. Full-suite result

**889/889 passing** (873 pre-correction + 16 new).

## 6. Existing-behavior regression comparison

Freshly re-run for this report, 2024-01+2024-02, S001+S005+S007 (159 trades):

| Dimension | Equal |
|---|---|
| opened / closed / signals / ignored / rejected | True |
| equity_curve | True |
| total_trades / total_net_pnl / max_drawdown / max_drawdown_percent / profit_factor / total_fees | True |
| deterministic (same run twice) | True |

Every pre-existing dimension is identical pre- vs. post-correction. The
snapshot gained exactly one additive field (`structural_break_event`); no
pre-existing field was required to be, or was, compared as part of a whole-dict
equality check for this proof (Section 4's dedicated test does that
separately, field-by-field, confirming the addition is purely additive).

## 7. Point-in-time safety analysis

- The new logic operates on `highs[:-1]`/`lows[:-1]` — the exact same
  point-in-time-safe slice already used by `get_last_swing_levels`,
  `detect_market_structure`, `detect_bos`, and `detect_choch`. No new
  lookahead is introduced; a pivot can only be recognized once its confirming
  neighbor candles are already in history (rule 4/7/8 from the authorization).
- The event's `confirmed_at` is always the current replay candle being
  ingested — never the pivot's own, earlier candle (rule 5/6), verified by
  `test_event_confirmed_at_is_breaking_candle_not_pivot_candle` and
  `test_pivot_confirmed_while_price_already_beyond_it_fires_immediately_not_backdated`.
- This tracker's `_ingest()` is called only once per already-closed candle,
  via the same `sync()` contract every other tracker in this codebase uses —
  no unfinished higher-timeframe candle or future candle can reach this logic
  (inherited, not newly introduced).
- Repeated `snapshot()` calls perform no consumption or mutation (rule 10),
  and repeated `sync()` calls with a non-growing candle list are a no-op via
  the tracker's pre-existing `_consumed` guard.

## 8. Memory-bounding explanation

The consumed-pivot set is pruned every `_ingest()` call to exactly the
pivot timestamps still present in `_recent_candles` — a pivot that has
scrolled out of the sliding window can never again be reported as the "last"
swing high/low (`find_swing_pivots` only ever scans the current window), so
its consumption marker can be safely discarded. This bounds the set's size to
the same `O(structure_lookback)` (default 500) the tracker already uses for
everything else — no new asymptotic behavior class is introduced. Verified
directly by `test_consumed_pivot_memory_is_bounded_by_structure_lookback`
(400 candles, `structure_lookback=10`, set size never exceeds 10).

## 9. Remaining limitations

- `get_last_swing_levels`'s existing behavior — the "last" confirmed pivot is
  whichever one is chronologically most recent, not necessarily the
  highest/lowest price — is inherited unchanged. This means the "broken
  level" a bullish event references could in principle be numerically lower
  than an earlier, already-broken level, if that is how the existing pivot
  selection behaves in a given sequence. This is pre-existing behavior, not
  altered or newly introduced by this correction, and is out of scope to
  change here.
- The event is a neutral `structural_break_event`, deliberately not resolved
  into a mutually-exclusive BOS-vs-CHoCH classification — per instruction,
  this avoids resolving modeling decision B5 in this sprint.
- No consumer reads this field yet (explicit integration boundary) — its
  value is entirely unproven in terms of downstream usefulness until Order
  Block actually consumes it in the next, separately-approved correction.
- The rejected "edge relative to previous close" crossing alternative
  (Section 2) remains an open, recorded research question if a future need
  for stricter edge semantics ever arises.

## 10. Proposed next correction

**Order Block correction:** have `OrderBlockTracker` consume
`structural_break_event` (rather than re-deriving edge-triggering by comparing
consecutive raw `bos` readings itself, as its docstring currently describes),
and bound its origin-candle search to the specific leg between the previous
consumed pivot and the newly broken one — directly targeting the
already-confirmed origin-search-boundary correction item from
`docs/module_decision_register.md`. This was explicitly not started here.

**Verdict: STRUCTURAL BREAK EVENT ACCEPTED — ready for Order Block correction.**

Stopping here per instruction. Not proceeding to the Order Block correction,
Liquidity Sweep experiments, MAE/MFE, SOL baseline, S008, optimization, or
portfolio work without separate approval.
