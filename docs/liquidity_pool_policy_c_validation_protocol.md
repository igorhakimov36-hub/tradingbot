# Liquidity Pool Hybrid Policy C — SOL VALIDATION Experiment — Frozen Protocol

**Written and frozen BEFORE any SOL VALIDATION data is loaded.** Its
SHA-256 hash is recorded immediately after saving, before any VALIDATION
file is opened, and restated in the final results report. A mismatch
between the recorded hash and a recomputed hash at report time means the
protocol was altered after seeing results.

## Locked VALIDATION periods

`SOLUSDT`, months: **2024-11, 2024-08, 2024-10, 2025-05**. SOL FINAL
HELD_OUT (2025-02, 2025-07) and every reserved/unassigned month are
off-limits for the duration of this experiment. No BTC data is used for
any model-selection decision.

## Exact state definitions

**Policy A (production control, unmodified):** exactly `strategy/features/liquidity_pool.py`'s
own `LiquidityPool.check_sweep` — a pool is `unswept` until a single
candle satisfies wick-beyond-then-close-back (buy_side:
`high > zone_high and close < zone_high`; sell_side:
`low < zone_low and close > zone_low`), evaluated against the pool's
*current, live* zone bounds at that moment. A bare close beyond does not
change `swept_status`.

**Policy B (immediate invalidation control):** the first candle whose
close is beyond the outer boundary (buy_side: `close > zone_high`;
sell_side: `close < zone_low`) — evaluated with no same-candle
wick-beyond-then-close-back exception — immediately and permanently
retires the pool. It can never later generate a sweep of any kind,
fresh or delayed.

**Policy C (bounded failed-acceptance state machine):**

1. A fresh pool begins in `UNSWEPT`.
2. On every candle, first check the same-candle condition (identical to
   Policy A): wick beyond + close back on the same candle → emit an
   **immediate same-candle sweep** event and stop tracking this pool
   (terminal). This check applies whether the pool is `UNSWEPT` or
   already `ACCEPTANCE_PENDING`.
3. If not a same-candle sweep, and the pool is `UNSWEPT`: a close beyond
   the outer boundary with no same-candle rejection transitions the pool
   to `ACCEPTANCE_PENDING`. **The boundary tested for the remainder of
   this pool's pending window is frozen at its live value on this exact
   candle** (not re-evaluated against a subsequently widening zone) —
   this is the "which boundary must be closed back through" decision,
   made explicitly, not left ambiguous.
4. While `ACCEPTANCE_PENDING`, for each of the next candles counted from
   (and including) the candle immediately after entering
   `ACCEPTANCE_PENDING`, up to and **including candle number 16**
   (16 completed 15-minute candles, the window is inclusive of its own
   16th candle — this is the "is the 16th candle included" decision,
   made explicitly: yes):
   - If that candle's close is back on the inside of the frozen boundary
     (buy_side: `close < frozen_zone_high`; sell_side:
     `close > frozen_zone_low`) → emit a **multi-candle failed-acceptance
     sweep** event, terminal, and stop tracking this pool. This is
     evaluated independently of whether that same candle's own wick
     also happens to extend beyond the boundary — once already in
     `ACCEPTANCE_PENDING`, only the close position (relative to the
     frozen boundary) determines reclaim, not a fresh wick-based test.
   - Repeated closes beyond the boundary during the pending window do
     **not** reset or extend the 16-candle count — the window is anchored
     exclusively to the original entry into `ACCEPTANCE_PENDING`. This is
     the "how are repeated closes beyond treated" decision, made
     explicitly.
   - **A pool emits at most one sweep event in its lifetime** (same-candle
     or multi-candle, never both, never repeated) — enforced by
     terminating tracking the instant either fires.
5. If no qualifying reclaim occurs by (and including) the 16th candle of
   the pending window, the pool transitions to `ACCEPTED_INVALIDATED` on
   the candle immediately following the 16th pending candle, and can
   never later generate a sweep of any kind under Policy C.
6. Every transition (`UNSWEPT`→`ACCEPTANCE_PENDING`,
   `ACCEPTANCE_PENDING`→sweep, `ACCEPTANCE_PENDING`→`ACCEPTED_INVALIDATED`)
   records its own timestamp and the pool's stable `(direction, created_at)`
   identity — the exact same identity convention already used throughout
   this project's research (matching `LiquidityPoolTracker`'s own internal
   `_seen_eqh_keys`-style keys).
7. **Same-bar ambiguity**: since reclaim (step 4) is checked *before* the
   16-candle boundary is evaluated as expired, a reclaim occurring
   exactly on candle 16 always wins — there is no genuine ambiguity
   between "reclaim on the 16th candle" and "window expired," because
   expiry is only declared starting the candle *after* the 16th pending
   candle, never on it. Same-candle-sweep vs. multi-candle-sweep
   ambiguity cannot occur either, since the same-candle check (step 2)
   always runs first and, if it fires, terminates tracking before the
   pending-window logic is ever reached that candle.
8. **Distinct identity for a new pool near an accepted old one**: relies
   entirely on the existing, unmodified production pool-creation/matching
   mechanism (`LiquidityPoolTracker._register_candidate`) — an
   `ACCEPTED_INVALIDATED` pool (Policy C) is never re-matched against for
   new candidate touches in production's own matching logic regardless
   of this research policy (production doesn't know about Policy C's
   states at all), so any genuinely new candidate cluster forming near
   the old pool's price becomes, by construction, a new `LiquidityPool`
   object with its own, later `created_at` timestamp — a distinct
   `(direction, created_at)` identity automatically, requiring no new
   logic.
9. Bullish/bearish (buy_side/sell_side) rules are fully mirrored as
   stated above.
10. No event is ever backdated: every transition's timestamp is the
    candle on which it is detected, never the candle that caused the
    underlying price condition to first become true in some other sense.
11. No current-bar decision affects an earlier part of the same bar: all
    checks (same-candle sweep, pending-transition, reclaim, expiry) are
    evaluated once per candle, using only that candle's own OHLC and the
    pool's state as of the *start* of that candle — no field computed
    later in the same candle's processing feeds back into an earlier
    check for that same candle.

## Frozen parameter sensitivity

- **Primary Policy C window: 16 completed 15-minute candles.**
- **Sensitivity windows: 8 and 32 candles** (identical state-machine
  logic, only the window length changes) — pre-declared, not expanded
  after seeing results.
- Policy A and Policy B run as fixed controls, no parameters.

## Primary module-level endpoints (unconditional, complete cohort)

For every eligible first-breach event (a pool's first clean close beyond
its outer boundary — identical trigger condition as Policy C's own
`UNSWEPT`→`ACCEPTANCE_PENDING` transition):

1. Reclaim within the bounded window (per window size: 8/16/32).
2. Continued acceptance beyond the window (→ `ACCEPTED_INVALIDATED`).
3. Right-censoring (month ends before either resolves).
4. Cases where Policy A's own sweep occurs *after* Policy C would already
   have invalidated the pool (Policy A "late" relative to Policy C).
5. Cases where Policy C captures a multi-candle sweep that Policy A's own
   `swept_status` never reaches by month end (a pool Policy A would leave
   permanently `unswept`, that Policy C correctly resolves within its
   window).
6. Cases where Policy A and Policy C detect the identical same-candle
   sweep (both fire on the same candle, by construction, since Policy C's
   own same-candle check is copied verbatim from Policy A).
7. Time from first breach to reclaim or to `ACCEPTED_INVALIDATED`.
8. Penetration depth in ATR and zone-width units.

Reported: pooled; per month/regime; buy-side/sell-side; by pool source;
by source count; raw and de-duplicated (using the same frozen,
structural-identity-only clustering rule from the TRAIN research); with
Wilson-score confidence intervals sized to the de-duplicated N. No
primary result is conditioned on surviving to a later horizon — every
event is retained in the denominator unless explicitly right-censored.

## Directional validity endpoint

For each sweep produced by Policy A or Policy C (same-candle or
multi-candle), beginning no earlier than the next completed candle after
the sweep, measure direction-normalized MFE/MAE (in ATR-at-event units)
and first-passage of +0.5/+1.0/+2.0 ATR favorable vs. an equally-defined
adverse move, at horizons 1/2/4/8/16/32 bars — complete cohort, same-bar
ambiguity resolved conservatively (favorable+adverse both true on one
candle → counted as adverse-first, mirroring the conservative convention
already established for Order Block VALIDATION). This is explicitly a
**module-validity study**, not a profitability claim.

## S001 linkage restriction

Nearest-timestamp matching (used descriptively in the TRAIN report,
where it was also mis-tallied and has since been corrected) is **not**
used as primary evidence here. Exact linkage is established by directly
calling the real, unmodified `LiquiditySweepReversalSetup._find_fresh_sweep(snapshot)`
method against the *exact* `MarketIntelligenceSnapshot` object the real
decision loop already produced for that bar — a pure, read-only,
side-effect-free query already used internally by the real `evaluate()`
call — and reading its returned zone's own `(direction, created_at)`
identity directly, the same identity convention the pool-lifecycle
research already uses. This guarantees: every tagged signal references
an existing, exactly-identified pool (or none, if `_find_fresh_sweep`
returns `None`, in which case there is no signal to tag); no signal can
match more than one event, since `_find_fresh_sweep` returns at most one
zone; no event is ever assigned by temporal proximity; and the
instrumentation changes no decisions or trades, since it is a second,
parallel call to the identical pure function with the identical
snapshot input, never substituted into the real decision path. If this
exact linkage cannot be established for a given signal for any reason,
that signal is excluded from the S001 analysis rather than
approximately matched. S001's own analysis remains secondary and
diagnostic throughout, run standalone (no combined portfolio), with no
parameter of S001 itself modified or optimized.

## Promotion criteria (restated verbatim, not to be altered post-hoc)

Promote Policy C to additive production implementation only if:
1. The bounded state machine separates fast failed acceptance from stale
   delayed sweeps consistently across ≥3 of 4 VALIDATION months.
2. Policy C removes a material population of very late/stale Policy A
   sweeps.
3. Policy C captures a material multi-candle rejection population missed
   by Policy A.
4. Retained/new Policy C sweep events show at least equal or better
   directional validity than the removed stale events.
5. Results remain coherent under 8/16/32-bar sensitivity.
6. No conclusion depends on approximate S001 matching, one month, one
   direction, or overlapping pools.
7. TRAIN-to-VALIDATION degradation is disclosed and acceptable.

**If 16 alone appears successful while 8 and 32 fail materially, the
threshold is classified as fragile and the result is `INCONCLUSIVE`** —
not a license to search for a different window.

---
FROZEN — SHA-256 of this file (computed over the file as saved, before
any VALIDATION data was loaded): see
`docs/liquidity_pool_policy_c_validation_protocol.sha256`
