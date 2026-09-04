# LuxAlgo Wick-Extremity Zone — Controlled Geometry Ablation — Frozen TRAIN Protocol

**Written and frozen BEFORE any TRAIN data is loaded for outcome
computation.** SHA-256 hash recorded immediately after saving, before
any of the four TRAIN month files are opened for this sprint's own
analysis, and re-verified before the final report is written.

## Research question

Production's Liquidity Pool sweep check (Policy A, `LiquidityPool.check_sweep`
in `strategy/features/liquidity_pool.py`) evaluates both wick-breach and
close-reclaim against the **band's own outer edge** (`zone_high` /
`zone_low`), which widens over the pool's life as more same-direction
touches land within tolerance. This sprint asks: if the sweep zone is
instead anchored to a **single real candle's own wick extremity**
(LuxAlgo-style — outer = that candle's high/low, inner = that candle's
own body edge), rather than the production band, does sweep detection
and downstream directional performance change materially, for the
subset of pools where such a real-candle anchor can be identified
without lookahead? This is a **pure geometry ablation** — no new
detection source, no new pool population, same pools, same de-duplication,
same directional-outcome methodology already used in every prior sprint
in this series.

This is a **TRAIN-only exploratory sprint**. Its output is a
recommendation (PROMOTE WICK ZONE TO VALIDATION / KEEP CURRENT GEOMETRY /
INCONCLUSIVE), not a production change and not a VALIDATION-grade claim.

## Scope and data boundary

**TRAIN months only**: 2024-02, 2024-04, 2024-09, 2025-12 — the same four
months used for every prior TRAIN sprint in this series (Order Block,
Liquidity Pool Policy C). No VALIDATION (2024-11, 2024-08, 2024-10,
2025-05), SECONDARY_VALIDATION (2024-03, 2024-06, 2025-04, 2025-09), or
FINAL_HELD_OUT (2025-02, 2025-07) month is accessed in this sprint,
enforced explicitly by the harness (an assert on every processed month
string, matching the pattern used in every prior sprint).

## Architecture audit (summary; full re-statement in the report)

- `LiquidityPool` is a **band**, not a line: `zone_high`/`zone_low`,
  widened by `register_touch` (`zone_high = max(...)`, `zone_low = min(...)`)
  whenever a same-direction candidate lands within
  `atr * tolerance_atr_multiplier` of the current band.
- Both wick-breach and close-reclaim (Policy A's own `check_sweep`) use
  the **same** boundary — the band's outer edge — for a given direction.
- Three contributing source types, three different anchor-eligibility
  profiles:
  - `round_number`: pure arithmetic, **never** anchored to any real candle.
  - `session_high` / `session_low`: directly anchorable via
    `SessionBoundariesTracker`'s own `high_timestamp` / `low_timestamp`,
    confirmed set exactly when a candle's own high/low extends the
    session extreme (`strategy/features/session_boundaries.py:284-315`).
  - `equal_highs` / `equal_lows`: the contributed price is
    `EqualLevelCluster.level = sum(pivot_prices) / len(pivot_prices)` — a
    **running mean**, not any single candle's real wick — anchorable only
    by looking one level deeper, into that cluster's own
    `pivot_prices` / `pivot_timestamps`, for its most extreme individual
    pivot.
- `LiquidityPool.register_touch` retains only `contributing_touches` as a
  list of **timestamps** (no per-touch price) and `sources` as a
  deduplicated list of source-type strings. Per-touch
  `(price, source, timestamp)` triples are **not** retained by
  production's own public data.

## Architecture decision (research-only, zero production footprint)

`strategy/features/liquidity_pool.py` is **not modified**. A research-only
observer wrapper captures per-touch `(pool_id, price, timestamp,
bar_index, source)` plus the exact `session_period` / `equal_level_cluster`
snapshot state at the moment of each touch's own registration — by
wrapping the tracker's own touch-registration entry point, never by
reimplementing LuxAlgo pivot/cluster detection from scratch (explicitly
rejected — a from-scratch reimplementation would no longer be a valid
ablation of the same pools). `strategy/research/liquidity_pool_wick_extremity.py`
contains only pure functions (`wick_zone_boundaries`,
`check_wick_zone_sweep`, `resolve_anchor`) with no side effects and no
reference to any production class; confirmed by
`test_module_has_no_production_side_effects_at_import`.

## Geometry (frozen; implemented in `liquidity_pool_wick_extremity.py`)

- **Outer boundary**: buy_side = anchor candle's `high`; sell_side =
  anchor candle's `low`.
- **Inner boundary**: buy_side = `max(anchor.open, anchor.close)`;
  sell_side = `min(anchor.open, anchor.close)`.
- **Wick-Zone Sweep** (full rejection, not mere touch): buy_side =
  `candle.high > outer AND candle.close < inner` (both strict); sell_side
  mirrored. A candle that only penetrates the outer boundary without
  closing back beyond the inner boundary does **not** trigger — it is
  neither a Policy A event nor a Policy W event under this definition.

## Eligibility rule (frozen, declared before any outcome was computed)

A pool is **Wick-Zone-eligible** if and only if its current
**defining touch** — the specific touch that set the pool's own
current `zone_high` (buy_side) / `zone_low` (sell_side), tracked
**causally, updated every time a new touch actually widens the
boundary** — has a resolvable real-candle anchor:
- `round_number`-sourced defining touches: **never** eligible.
- `session_high` / `session_low`-sourced defining touches: eligible via
  that period's own `high_timestamp` / `low_timestamp`.
- `equal_highs` / `equal_lows`-sourced defining touches: eligible via the
  contributing cluster's own most extreme individual pivot, using the
  **exact cluster snapshot captured at the moment that touch was
  registered** — never a later, further-evolved version of that cluster.

Because the defining touch is tracked causally (only touches already
observed by time *t* can be "current" at *t*), this rule introduces
**no lookahead**: a pool's Wick-Zone eligibility and geometry at any
candle reflect only touches registered strictly before that candle. A
pool ineligible early in its life may become eligible later (if a
widening touch happens to come from an anchorable source), and vice
versa is impossible (widening never un-registers an earlier eligible
touch's already-realized sweeps, since those are evaluated forward-only
as they occur).

Mixed-source pools are evaluated purely by which touch currently sets
the boundary — non-defining touches from non-anchorable sources do not
disqualify eligibility.

## Tie-break rule (frozen)

If more than one candidate anchor shares the identical extreme price,
the **earliest timestamp** among them wins, deterministically
(implemented in `resolve_anchor`, `test_tie_break_earliest_timestamp_wins`).

## Replay-safety / no-backpainting rules (frozen)

- `anchor_timestamp`: the timestamp of the defining touch's own anchor
  candle.
- `zone_available_at` = `anchor_timestamp`. The Wick Zone defined by a
  given anchor **cannot be evaluated for a sweep on or before its own
  `zone_available_at`** — a candle cannot be swept by a zone whose
  anchor candle it itself is, or that has not yet closed. This
  generalizes the already-established "creation candle cannot sweep its
  own pool" rule to "an anchor candle cannot sweep the zone it itself
  defines."
- The pool's own **creation candle** (`origin_bar_i`, the fix already
  applied in the Policy C VALIDATION and Staleness sprints) is excluded
  from Wick-Zone sweep evaluation for the same reason it is excluded
  from Policy A: production's own per-candle check runs before that
  candle's new touches are registered.
- **Frozen after confirmation**: once Policy A itself confirms the
  pool's sweep, or the pool is invalidated/right-censored at dataset
  end, the Wick-Zone anchor/geometry current at that exact moment is
  the one used for all downstream Policy W reporting for that pool — it
  is not re-derived retroactively, and no candle after resolution is
  evaluated against it.
- `pool_confirmed_at`: the timestamp of Policy A's own sweep-confirmation
  candle (or, for invalidated/censored pools, the invalidation/dataset-end
  timestamp) — recorded per pool for reporting, not used to alter
  eligibility computed causally as above.

## Ambiguity and censoring (reused unchanged from prior sprints)

- Same-bar favorable-and-adverse resolution in the downstream
  first-passage endpoint: counted **conservatively as adverse** (the
  convention frozen in every prior sprint in this series).
- No resolution within the frozen maximum horizon (32 bars) is
  **right-censored**, not a win or loss.
- No conditioning on survival to a later horizon — every resolved
  sweep (Policy A, Policy W, or both) enters the primary endpoint once,
  at its own confirmation.

## De-duplication (reused unchanged)

Same frozen structural clustering rule as every prior Liquidity Pool
sprint: zone overlap + within-20-bar timing + same direction → earliest
representative kept. Applied at the pool level; Policy W inherits the
same de-duplicated pool population as Policy A (it is the same pools,
re-evaluated with a different geometry, not a new population).

## Directional first-passage endpoint (frozen formulas, reused unchanged)

For each de-duplicated pool with a confirmed sweep (Policy A and/or
Policy W), beginning at the candle immediately after the sweep-confirmation
candle:
- ATR frozen at sweep confirmation (standalone, point-in-time
  `AverageTrueRangeTracker`, period 14 — never recomputed later).
- Expected reversal direction: swept `buy_side` → SHORT/DOWN; swept
  `sell_side` → LONG/UP (matching `LiquiditySweepReversalSetup`'s own
  existing mapping).
- **Primary**: `+1 ATR` favorable vs. `-1 ATR` adverse first passage.
- **Secondary**: `+2 ATR` favorable vs. `-1 ATR` adverse first passage.
- MFE/MAE reported separately, explicitly labeled descriptive-only (not
  simulated profitability).
- Reported: pooled; per month; per direction; per source; per
  eligible-vs-ineligible; agreement / Policy-A-only / Policy-W-only
  event breakdowns; raw and de-duplicated; censored-event counts at
  every breakdown.

## S001 linkage (frozen requirements — two distinct, separately labeled analyses)

1. **S001 under Policy A (real, exact)**: identical to every prior
   sprint's proven method — instrument `strategy_callback` to call the
   real, unmodified `LiquiditySweepReversalSetup._find_fresh_sweep(snapshot)`
   directly, keyed by the exact 1-minute `current_candle` timestamp;
   `OPENED`/`CLOSED` journal records paired by chronological index (not
   `record_closed`'s own timestamp, which is the exit time); required
   proofs before trusting the pairing: equal lengths, monotonic
   ordering, per-pair side/entry-price match. This is genuine production
   behavior, not a simulation.
2. **S001 under Policy W (shadow, explicitly disclosed as best-effort,
   not a production-equivalence claim)**: a research-only shadow
   arbitration that mirrors `_find_fresh_sweep`'s own selection logic
   (freshness preference, cooldown/one-fresh-sweep-at-a-time behavior)
   but is fed Policy-W-confirmed sweep events in place of Policy-A ones.
   Any point where the shadow's arbitration logic must diverge from or
   approximate the real setup's internals (because the real setup's
   selection is itself driven by production's own tracker state, not
   swappable in isolation without modifying production) is disclosed
   **explicitly and by name** in the final report's methodology section,
   pre-registered here as a **known limitation**, not decided post-hoc.
   This shadow result is reported **separately** from, and never merged
   into, the real Policy-A S001 result.

Nearest-timestamp or approximate matching is not used for either
analysis.

## Decision rule (frozen, not altered after results are seen)

`PROMOTE WICK ZONE TO VALIDATION` only if, pooled and in at least 3 of 4
TRAIN months:
1. Among eligible pools, Policy W's directional first-passage results
   are materially better than Policy A's own results on the same
   eligible subset (not compared against the full, mostly-ineligible
   population — an apples-to-apples eligible-only comparison).
2. The improvement is not created by censoring, one direction, one
   source, or a small number of outlier pools.
3. Shadow S001-under-W does not contradict the module-level finding.
4. Sample sizes (eligible pool count, per-month and pooled) are adequate
   and disclosed; if eligibility is too rare for a meaningful sample,
   this is reported as a frequency limitation, not reinterpreted as a
   negative or positive result.

`KEEP CURRENT GEOMETRY` if eligible-subset results are equal or worse
under Policy W, or eligibility is common but shows no material
directional advantage.

`INCONCLUSIVE` if sample sizes are insufficient for a meaningful
comparison, results conflict materially across months, or module-level
and shadow-S001 evidence disagree materially. Consistent with this
series' standing practice, a narrow, structurally-forced result (e.g.
an eligibility rate near zero, mechanically limiting comparison power)
is classified as **INCONCLUSIVE due to insufficient eligible sample**,
not forced into KEEP or PROMOTE.

This rule is not renegotiated after seeing results.

---
FROZEN — SHA-256 of this file (computed over the file as saved, before
any TRAIN data was loaded for this sprint's own outcome computation):
see `docs/liquidity_pool_wick_extremity_train_protocol.sha256`.
