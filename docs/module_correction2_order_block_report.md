# Module Logic Correction 2 — Order Block Event Identity and Origin-Leg Boundary

**Verdict: ORDER BLOCK CORRECTIONS ACCEPTED**

## Git checkpoint

1. `git status` before this correction: clean (Module Logic Correction 1 had
   just been committed).
2. Module Logic Correction 1's exact files (`strategy/features/market_structure_tracker.py`,
   `tests/test_structural_break_event.py`, `docs/module_correction1_structural_break_event_report.md`)
   were confirmed and committed as their own checkpoint before any Correction 2
   edit began.
3. Commit hash: `38dbc78` ("Module Logic Correction 1: additive structural-break
   event identity").
4/5. No unrelated files were included; nothing pushed, merged, deleted, or
   reverted.
6. Working tree confirmed clean immediately before this correction's first edit.
7. A pre-Correction-2 behavioral reference (2024-01+02, 5 setups, full trade/
   signal/equity detail plus direct Order Block population sampling) was
   captured before any Phase 2A or 2B code was written, and reused as the
   "pre" baseline for both phases' comparisons below.

This correction's own changes remain **uncommitted**, per this project's
established pattern (commit only when asked).

---

## Phase 2A — Consume `StructuralBreakEvent`

### Design

`OrderBlockTracker._detect_new_order_block`'s direction-only trigger
(`bos != "NO_BOS" and bos != self._last_bos_state`, with `bos`/swing levels
independently re-derived via its own `get_last_swing_levels`/`detect_bos`
calls) is replaced by direct consumption of the `structural_break_event`
its caller now passes into `sync()` — the exact same additive, one-shot,
per-pivot-identity event Module Logic Correction 1 added to
`MarketStructureTracker`. Since that event is already proven one-shot per
distinct pivot upstream (Correction 1's own test suite), "event is not
`None` this bar" is the entire, sufficient trigger — no separate
consumption-tracking is needed inside `OrderBlockTracker` itself.
`previous_swing_high`/`previous_swing_low`/`bos` are no longer computed
independently in this method at all, removing a second, redundant
computation of exactly what `MarketStructureTracker` already computes.

`OrderBlockTracker.sync()` gained a required `structural_break_event`
parameter and the same one-new-candle-per-call guard `LiquidityPoolTracker`
already established for its own point-in-time snapshot inputs
(`equal_levels_snapshot`/`session_snapshot`) — batching would misattribute
when a break actually occurred. `MarketIntelligenceCoordinator.sync_and_build()`
now syncs `MarketStructureTracker` first (unchanged ordering) and passes its
`structural_break_event` snapshot value straight into `OrderBlockTracker.sync()`.

### Failing characterization test (required, run before implementing)

Reproduced the confirmed defect directly against the pre-Phase-2A code: a
sequence breaking swing high A (110) then a distinct, higher swing high B
(118) — with `bos` staying `BULLISH_BOS` continuously, no intervening
`NO_BOS` — produced **only 1 Order Block**, confirming the collapse. Fixed
by the design above; the corrected code produces exactly 2, one per event.

### Results

25 tests in `tests/test_order_block_feature.py` (all updated to the new
signature via a `sync_ob()` test helper that drives a companion
`MarketStructureTracker` in lockstep, mirroring the coordinator's real
wiring) + 4 new dedicated confirmation tests in
`tests/test_order_block_structural_break_event.py` (bullish and bearish
distinct-level dedup, repeated-closes non-refire, snapshot-call idempotency)
+ updates to `tests/test_snapshot_cache.py` (22 tests) and
`tests/test_breaker_block.py`'s one real-`OrderBlockTracker` integration
test — all passing.

**Phase 2A comparison artifact** (2024-01+02, 5 setups: S001/S002/S005/S006/S007):

| Setup | pre (bos-comparison) opened | post (event-consumption) opened |
|---|---:|---:|
| liquidity_sweep_reversal (S001) | 6 | 6 |
| order_block_continuation (S002) | 108 | 111 |
| fair_value_gap_rebalance (S005) | 81 | 78 |
| breaker_block_reversal (S006) | 44 | 49 |
| trend_continuation_confluence (S007) | 5 | 5 |

**Exactly which populations changed, and why (not judged by P&L):**

- **S002 (order_block_continuation) changed directly and as intended**:
  its own FIRED-signal sequence changed (108→111) because more distinct,
  correctly-identified Order Blocks now exist for it to read as its
  required `active_order_block_first_touch` condition — this is the
  direct, intended effect of no longer collapsing multiple distinct breaks.
- **S006 (breaker_block_reversal) changed directly and as intended**: its
  own FIRED-signal sequence changed (44→49) because Breaker Blocks are
  derived from `OrderBlockTracker`'s `mitigated` list — more distinct
  Order Blocks means more/different mitigated blocks feeding
  `BreakerBlockTracker`.
- **S001 (liquidity_sweep_reversal) and S007 (trend_continuation_confluence)
  did NOT change at the decision level**: their own FIRED-signal sequences
  are byte-for-byte identical pre/post (verified directly). Their `opened`/
  `closed` trade *records* differ only because `StrategyEngineV2.decide()`
  uses first-fired-wins arbitration across setups on the same bar
  (`strategy_engine_v2.py:69`, "if more than one setup fires on the same
  bar, the first is used") — S002 firing on additional, correctly-identified
  bars can win arbitration on bars where S001/S007 also independently fire,
  shifting *which* setup's signal gets realized as a trade that bar. This is
  a pre-existing, documented engine property being exercised differently by
  a corrected upstream input, not a change to S001/S007's own logic.
- **S005 (fair_value_gap_rebalance)'s FIRED-signal sequence also changed
  (81→78)**, which was NOT expected from `overlaps_order_block_zone` being
  non-gating `additional_evidence` (confirmed by direct code reading:
  `fired = all(c.satisfied for c in [touch_condition])`, no order_block
  condition in `required`). Investigated: the exact same arbitration
  mechanism explains it — S002 is registered before S005 in the engine's
  setup list, so on the 3 bars where S002 now newly fires alongside S005,
  S002 wins arbitration, and S005's own signal for that bar is never
  recorded as a `LONG`/`SHORT` engine decision, even though S005's own
  `evaluate()` would have returned `fired=True` had it been asked. The
  arithmetic checks out exactly: S002 +3 (108→111) matches S005's −3
  (81→78). S005's own condition logic is unaffected; only whether its
  signal gets *surfaced* by the engine on contested bars changed.

---

## Phase 2B — Bound origin search to the relevant impulse leg

### Architecture decision

**Candidates considered** (as specified): (a) the most recent confirmed
opposing swing pivot preceding the break, (b) the broken pivot's own
candle, (c) another explicitly justified origin.

**(a) was implemented first and then rejected** after it failed to
reproduce this codebase's own established reference case. The canonical
`_bullish_setup` fixture (used across `test_order_block_feature.py`,
`test_snapshot_cache.py`, `test_breaker_block.py`) has its origin candle
(idx4) positioned *after* the broken swing-high pivot (idx3), during a
brief consolidation before the actual breakout. Bounding the leg to "the
most recent opposing-direction swing pivot" computed a *later*, tighter
boundary (a minor swing-low fractal at idx5, itself just a 1-point wiggle
within that same consolidation) that excluded idx4 entirely — verified
directly via `find_swing_pivots`, not assumed. This would have broken the
required regression-preservation test (#12) for the single most
established example in the whole test suite.

**(b) was adopted instead**: the leg is bounded to the broken pivot's own
candle (inclusive) through the breaking candle (exclusive), using
`structural_break_event.pivot_timestamp` **directly** — the exact same
pivot identity Module Logic Correction 1 already established — rather than
re-deriving it independently via a second `find_swing_pivots` call. This
is economically coherent: any opposite-colored candle between when the
broken level was *formed* and when it was *broken* represents genuine
positioning specifically tied to that level's eventual breakout — exactly
the concept an Order Block is meant to capture — and it is causally
consistent with the level actually being reported by the event. It also
directly satisfies requirement 8 ("break event and leg boundary share
consistent pivot identity") by construction, not merely by coincidence.

This was derivable from currently-available event/pivot information (the
event's own `pivot_timestamp`) without any new architectural decision or
heuristic beyond choosing between the two explicitly offered candidates —
so Phase 2B was not blocked.

**Crossing/boundary requirements, addressed:**
1/2. Point-in-time available, never a future pivot — `pivot_timestamp` was
   already established as point-in-time-safe by Correction 1, and the leg
   excludes the current (breaking) candle.
3. Represents the actual movement leading into the break — verified via
   the canonical fixture reproducing its established origin exactly.
4. Prevents an unrelated candle from prior structure — verified via a
   constructed defect-demonstration case (below).
5. Avoids arbitrary fixed-bar lookbacks — the boundary is the pivot's own
   structural identity, not a fixed N.
6. No valid opposite candle inside the leg → **no Order Block is created**
   (the most conservative option, matching the existing, already-established
   "no opposite-colored candle found" behavior exactly — not a new failure
   mode). The other three options offered (leg extreme candle, body-based
   origin, unresolved candidate for research) were not chosen: no repository
   evidence favors them over the already-existing conservative convention,
   and choosing one would be new detection logic, not a correction.

### Failing characterization test (confirmed against Phase-2A-only code)

Constructed a sequence where event B's leg (bounded to its own broken
pivot) contains no opposite-colored candle at all. Against Phase-2A-only
code (unbounded search), the origin search reached backward past the leg
boundary and **incorrectly reused event A's own origin candle** (idx4) for
event B — two Order Blocks with byte-identical zones and origin timestamps,
despite being different structural breaks. Fixed by the leg-bounded search;
the corrected code creates **zero** Order Blocks for event B (per the
conservative no-origin rule), never touching idx4.

### Focused tests (12 required scenarios, `tests/test_order_block_impulse_leg_boundary.py`, 9 tests)

Valid opposite candle inside the leg selected; opposite candle existing only
before the leg boundary correctly excluded; no opposite candle inside the
leg correctly produces no Order Block; several opposite candles in a leg
select the closest (last) one, not the first; bullish/bearish symmetry;
origin always strictly earlier than the break event; break event and leg
share the exact same pivot identity (direct assertion:
`leg[0]["timestamp"] == event.pivot_timestamp`); a long same-color
momentum run (extending the canonical fixture ~30 additional same-direction
candles) never reaches back into unrelated structure; independent tracker
instances share no state; multiple simultaneously-active blocks each retain
their own correctly-bounded origin.

### Results

**Phase 2B comparison artifact** (2024-01+02, Phase 2A held constant as the
baseline in both runs via a targeted `_find_impulse_leg` monkeypatch back to
Phase 2A's own unbounded search — confirmed to exactly reproduce Phase 2A's
own numbers before comparing):

| Setup | Phase 2A only, opened | Phase 2A+2B, opened |
|---|---:|---:|
| liquidity_sweep_reversal (S001) | 6 | 6 |
| order_block_continuation (S002) | 111 | 105 |
| fair_value_gap_rebalance (S005) | 78 | 80 |
| breaker_block_reversal (S006) | 49 | 50 |
| trend_continuation_confluence (S007) | 5 | 5 |

**Attribution:**
- **S002 dropped (111→105)**: direct, intended consequence — several
  previously-created Order Blocks (each traced to the unbounded search
  reaching into unrelated prior structure) no longer exist, removing
  spurious first-touch opportunities.
- **S006 rose slightly (49→50)**, **S005 shifted (78→80)**: the same
  arbitration mechanism from Phase 2A (first-fired-wins across setups)
  redistributing which setup's signal gets surfaced on contested bars, now
  reacting to S002's reduced-and-differently-timed firing.
- **S001, S007 FIRED-signal sequences remain byte-for-byte identical** to
  the Phase 2A baseline (directly verified) — their own logic is completely
  unaffected by Phase 2B; only shared-slot trade timing shifted.
- **Order Block population** (direct tracker-level sampling, bypassing the
  coordinator's cache): active and mitigated counts are **monotonically
  lower or equal** post-2B at every one of 29 sample points across the full
  2-month run (e.g., final sample: active 55→48, mitigated 500→500 capped)
  — consistent with the fix only ever *removing* spurious blocks, never
  adding new ones.

---

## Changed files

```
strategy/features/order_block.py               | (docstring + _find_impulse_leg + sync/detect signature changes)
strategy/market_intelligence_coordinator.py     | (wires structural_break_event into OrderBlockTracker.sync)
tests/test_order_block_feature.py               | (updated to new sync() signature via sync_ob() helper)
tests/test_snapshot_cache.py                    | (same, for OrderBlockTracker section)
tests/test_breaker_block.py                     | (same, for the one real-OrderBlockTracker integration test)
```
New files:
```
tests/test_order_block_structural_break_event.py    | Phase 2A confirmation tests (4)
tests/test_order_block_impulse_leg_boundary.py       | Phase 2B confirmation tests (9)
```
No other file was touched. In particular, per the explicit prohibitions:
`_find_last_opposite_candle`'s own matching logic, mitigation/invalidation,
touch counting, `impulse_strength`, block expiry, Breaker Block confirmation
semantics, every setup's own decision logic, and entry/exit/risk/portfolio
logic are all unchanged.

## Full-suite result

**903/903 passing**: 889 (pre-Correction-2 baseline) + 1 (new
`test_rejects_more_than_one_new_candle_per_call` guard test added to
`test_order_block_feature.py`, whose own count moved from 24 to 25) + 4
(`test_order_block_structural_break_event.py`, Phase 2A) + 9
(`test_order_block_impulse_leg_boundary.py`, Phase 2B) = 903, confirmed
directly against pytest's own collection counts at each stage, not
estimated.

## Consumer impact analysis

| Consumer | Reads Order Block? | Impact |
|---|---|---|
| S001 (liquidity_sweep_reversal) | No | Unaffected at the decision level (verified: identical FIRED sequence both phases); trade timing shifts only via shared-slot arbitration. |
| S002 (order_block_continuation) | Yes — required condition (`active_order_block_first_touch`) | Directly and intentionally affected by both phases (Section results above). |
| S005 (fair_value_gap_rebalance) | Yes — but only as non-gating `additional_evidence` (`overlaps_order_block_zone`), confirmed by direct code reading | `fired`/direction decision unaffected; realized trade count shifts only via engine arbitration on bars contested with S002. |
| S006 (breaker_block_reversal) / BreakerBlockTracker | Yes — indirectly, required condition (`active_breaker_block_first_touch`) reads Breaker Blocks derived from Order Block's `mitigated` list | Directly and intentionally affected by both phases. |
| S007 (trend_continuation_confluence) | No (confirmed: its required/optional conditions are `price_inside_active_liquidity_pool`/`structural_trend_confirmed`/`value_area_confluence`/`cvd_confirms_trend` — no order_block reference in code, only a docstring comparison) | Unaffected at the decision level (verified: identical FIRED sequence both phases); trade timing shifts only via arbitration. |
| S008 (proposed) | Not yet implemented | N/A — no code exists to affect. |

For S001 and S007 (truly unaffected consumers), decision-level exact
equality was required and verified. For S002, S005, S006 (affected
consumers), identical trades were explicitly not required; instead:
- Every difference traces to one of the two approved corrections
  (event-consumption in Phase 2A, leg-bounding in Phase 2B) or the
  pre-existing, unmodified arbitration mechanism reacting to a corrected
  input — never to any unrelated or unapproved change.
- No unrelated field or timing mechanism changed — `StrategyEngineV2.decide()`,
  every setup's own `evaluate()`, and the backtest engine's slot logic are
  byte-for-byte unmodified.
- No look-ahead or same-bar retroactivity was introduced (Section below).
- No change was accepted merely because P&L improved — net P&L differences
  (S002A: −3475.29 → S002B: −3441.08 in the Phase 2B step) are reported only
  as diagnostic observations; the corrections were made because the
  confirmed defects were real, not because either change happened to move
  net P&L in a particular direction.

## Point-in-time and replay-safety proof

- **Phase 2A**: `structural_break_event` is computed by `MarketStructureTracker`
  from the same `highs[:-1]`/`lows[:-1]` slice as every other swing/BOS
  primitive in this codebase, and is fed to `OrderBlockTracker.sync()` in
  the same replay step, immediately after `MarketStructureTracker.sync()`
  is called for that identical step — no future information crosses the
  boundary. The one-new-candle-per-call guard prevents any batched,
  ambiguous attribution.
- **Phase 2B**: the leg boundary is derived from `pivot_timestamp`, which
  was already established as point-in-time-safe in Module Logic Correction 1
  (the pivot is only recognized once its own confirming neighbor candles
  are already in history). The leg itself excludes the current (breaking)
  candle. No candle after the pivot and before-or-including the break can
  ever be excluded from consideration, and no candle at or after the break
  can ever be included.
- Directly verified: `test_origin_candle_is_always_earlier_than_the_break_event`
  asserts `origin_timestamp < created_at` for every produced Order Block.

## Determinism

Two independent runs of the full 2024-01 backtest with S002
(`order_block_continuation`) alone — the most heavily affected single
consumer — produced byte-for-byte identical trade sequences (112 trades
each, verified directly, not assumed from the earlier combined-setup runs).

## Unresolved ambiguity

- The rejected Phase 2B alternative ("most recent opposing swing pivot")
  remains a documented, deliberately-not-chosen candidate — recorded in
  `_find_impulse_leg`'s own docstring — in case future research wants to
  revisit whether a stricter, opposing-swing-anchored leg definition might
  be preferable for a different origin-selection philosophy. Not pursued
  here since it directly conflicted with an already-established reference
  case.
- The engine's first-fired-wins arbitration (`strategy_engine_v2.py:69`) is
  explicitly documented in the code itself as "future work once a second
  setup exists, not decided here" — it was already a known open item before
  this correction, not newly discovered, but this correction's own
  investigation is the first time its concrete effect on realized trade
  counts across multiple setups was directly measured and traced.

## Proposed next research decision

**Wick-based versus close/body-confirmed invalidation.** This correction
deliberately left mitigation/invalidation semantics untouched (explicit
prohibition). The module's own docstring already documents that wick-based
mitigation can be triggered by a rejected stop-hunt rather than durable
positioning, while the existing `mitigation_zone_*` (body-based) fields are
already tracked in parallel as informational-only. A future, separately
authorized research sprint could evaluate whether `mitigation_zone_status`
(not `mitigation_status`) should drive the active→mitigated transition
instead — a genuine, pre-identified modeling question, not decided or
touched by this correction.

---

**Verdict: ORDER BLOCK CORRECTIONS ACCEPTED.**

Both confirmed defects (direction-only event collapsing distinct breaks;
unbounded origin search selecting unrelated candles from prior structure)
are fixed, proven by dedicated failing-then-passing tests, and shown to
affect only the consumers that genuinely read Order Block output — with
every observed difference in those consumers traced to a specific,
approved mechanism (event consumption, leg bounding, or the pre-existing
arbitration rule reacting to corrected inputs), never to an unrelated or
unapproved change. Full suite passes (903/903), determinism is directly
verified, and no look-ahead or retroactivity was introduced.

Stopping here per instruction. Not beginning Liquidity Sweep changes,
mitigation A/B research, SOL baseline, S008, or any other sprint without
separate approval.
