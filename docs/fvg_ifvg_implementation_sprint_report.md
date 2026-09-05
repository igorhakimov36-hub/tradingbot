# FVG/IFVG Unified Lifecycle — Implementation & Verification Sprint

Implements the design from `docs/fvg_ifvg_module_logic_review.md`
(Section 6a, Path B). **Opt-in, disabled by default. Zero production
behavior change when unused** — proven below, not assumed.

## Lifecycle, in brief

A `FairValueGap` is created exactly as before (3-candle wick geometry,
confirmed the instant candle C closes). Wick-based fill tracking is
**completely unchanged** — a gap still moves from `active` to `filled`
at 100% wick penetration, and that transition is the ONLY thing that
ever removes a gap from `active`. What's new only applies **after**
that point, and only when opted into:

1. **Fill ≠ inversion, explicitly.** A `filled` gap gains
   `filled_at`/`filled_bar_index` (recorded once, at the transition)
   and becomes an *inversion candidate* — still the SAME object, same
   identity/direction/boundaries, now additionally watched for a
   **close-based**, strictly-stronger confirmation.
2. **Inversion** fires the first time a later candle's own **close**
   (not wick) clears the gap's far edge — `close < zone_low` (bullish)
   / `close > zone_high` (bearish), strict inequality (a close exactly
   at the boundary does not count). One-shot: `is_inverted` is sticky,
   set at most once, `inverted_at` never overwritten.
3. **Post-inversion failure**: an inverted gap that is later reclaimed
   the OTHER way (close beyond the ORIGINAL far edge) is marked
   `is_failed` — a third, terminal state — and permanently excluded
   from further inversion/retest checks. Also one-shot.
4. **Bounded retention**: a filled-but-not-yet-inverted gap is watched
   for at most `inversion_watch_bars` (default 500) candles from its
   own `filled_bar_index`, then `inversion_expired` is set and it's
   excluded from further inversion checks (`inversion_expired_count`)
   — the same pattern already used for unfilled-gap pruning.
   Retained-record count remains bounded by the pre-existing
   `max_tracked_filled` FIFO eviction — no new unbounded structure.
5. **Retest** (`track_retests`, independently optional, meaningless
   without `track_inversions`): a 2-bar rejection pattern against the
   gap's own original boundary, with a bar-count cooldown
   (`retest_cooldown_bars`, default 5) between repeat signals for the
   same gap. `retest_confirmed_this_bar` is a one-shot-per-bar flag
   (true only on the exact confirming snapshot, false before and
   after) — `last_retest_bar_index` is the sticky record.

**Both new flags default to `False`.** When both are off, none of
`_update_inversions`/`_check_failure`/`_check_retest` ever execute —
`snapshot()`'s returned dict keys remain exactly `{"active", "filled",
"expired_count"}`, byte-identical to before this sprint.

## Event ordering, proven (not asserted)

Every scenario the sprint named is a passing, deterministic test in
`tests/test_fair_value_gap_inversion.py`:

| Scenario | Test |
|---|---|
| Wick fill without inversion | `test_wick_fill_without_inversion` |
| Later close-confirmed inversion (separate bar) | `test_later_close_confirmed_inversion_on_a_separate_bar` |
| Fill AND inversion on the same candle | `test_fill_and_inversion_confirmed_on_the_same_candle` |
| Boundary equality (no inversion) | `test_close_exactly_at_boundary_does_not_confirm_inversion` |
| Repeated closes beyond boundary (no duplicate event) | `test_repeated_closes_beyond_boundary_do_not_duplicate_the_inversion_event` |
| Post-inversion failure | `test_post_inversion_failure_when_price_reclaims_the_original_zone`, `test_failure_is_also_idempotent` |
| Bounded retention / expiry | `test_inversion_candidate_expires_after_the_watch_window`, `test_inversion_still_eligible_exactly_at_the_watch_window_boundary` |
| Retest independence, timing, one-shot signal, cooldown, and its own precondition (never before inversion) | `test_retest_requires_track_retests_flag_even_with_inversions_on`, `test_retest_confirmed_this_bar_is_true_only_on_the_exact_confirming_bar`, `test_retest_cooldown_suppresses_an_immediate_repeat_signal`, `test_retest_fires_again_once_cooldown_elapses`, `test_retest_never_evaluated_before_inversion` |
| Feature fully inert when disabled, even under would-be-triggering price action | `test_disabled_tracker_snapshot_shape_unchanged_even_when_price_would_invert` |

**Knowability / permissibility**: every new field is written exactly
once, on the replay step whose own already-closed candle confirms it
— `inverted_at`/`failed_at`/timestamps are always the confirming
candle's own timestamp, never a later or earlier one. No field is
ever revised once set (proven by the idempotency tests above), so no
retroactive signal is possible — a snapshot taken at bar N never
changes when a later bar M > N is processed.

## Existing consumers preserved

**Scope decision, stated explicitly**: `MarketIntelligenceCoordinator`
and `market_intelligence_snapshot.py`'s `_map_zones()` are **not
modified** — they never read `"inverted"`/`"failed"`/the new
per-gap fields at all. This means inverted zones are **structurally
unreachable** from `snapshot.zones` today, regardless of any flag —
the strongest available form of "cannot accidentally change existing
FVG selection," stronger than a status filter that could in principle
be loosened by mistake later. S005 (`FairValueGapRebalanceSetup`) is
untouched and was not re-read for this sprint beyond the compatibility
proof below.

**Proof, on real SOL TRAIN data (2024-02, already-authorized, no new
period)**, `tests/test_fair_value_gap_inversion_compatibility.py`:
- `test_legacy_active_and_filled_population_identical_with_inversions_enabled`
  — same `active`/`filled` **counts, order, and every legacy field**
  (`direction`, `zone_high`, `zone_low`, `created_at`, `fill_status`,
  `fill_pct`, etc.) whether `track_inversions`/`track_retests` are on
  or off, on a real month of data — and confirms the feature is
  meaningfully exercised (at least one real inversion occurs on real
  SOL 15m data, not just synthetic sequences).
- `test_s005_backtest_result_unaffected_by_the_new_tracker_capability_existing`
  — S005's own real backtest (same month), run before and after
  exercising the new inversion tracker in the same process: **byte-
  identical trade count and net P&L.**

## Verification summary

- **Full suite: 1213 passed, 0 failed** (1196 prior + 15 new lifecycle
  unit tests + 2 real-data compatibility tests).
- All 41 pre-existing FVG/S005 tests pass **unmodified** — including
  the two exact-dict-equality assertions on `snapshot()`'s own empty-
  state shape, which structurally could not pass if the disabled
  feature changed anything.
- No VALIDATION/HELD_OUT data accessed; no new setup built; no
  threshold optimized (`inversion_watch_bars`/`retest_cooldown_bars`
  are engineering retention bounds, chosen the same way
  `max_age_bars`/`max_tracked_filled` already were — not fit to any
  outcome).

## Changed files

- `strategy/features/fair_value_gap.py` (production, modified) —
  the extension described above; `apply_candle()` (wick-fill math)
  and `_detect_new_gap()` (formation) are **byte-for-byte unchanged**.
- `tests/test_fair_value_gap_inversion.py` (new) — 15 lifecycle tests.
- `tests/test_fair_value_gap_inversion_compatibility.py` (new) — 2
  real-data compatibility tests.
- `docs/fvg_ifvg_implementation_sprint_report.md` (this document).

All prior uncommitted research (the SOL Multi-Module Setup Discovery
sprint and its own verdicts, and everything before it) is untouched —
confirmed via `git status`, unchanged file list plus these additions.
Nothing is committed.

## Not in scope (per the authorizing instruction)

No new setup consumes the inversion/retest fields yet. No frozen
profitability experiment was run. `MarketIntelligenceCoordinator`
wiring, a future IFVG-consuming setup, and the 3-arm controlled
comparison outlined in the prior review's Section 6e remain future,
separately-authorized work.
