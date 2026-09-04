# Order Block Hybrid Policy C — SOL VALIDATION Experiment — Frozen Protocol

**This document is written and frozen BEFORE any SOL VALIDATION data is
loaded.** Its SHA-256 hash is recorded at the end of this file (computed
over everything above the hash line) and restated in the final results
report. Any discrepancy between that recorded hash and a recomputed hash
of this file at report time means the protocol was altered after seeing
results, and the experiment must be treated as compromised.

## Locked VALIDATION periods

`SOLUSDT`, months: **2024-11, 2024-08, 2024-10, 2025-05**. No other SOL
month is accessed. SOL FINAL HELD_OUT (2025-02, 2025-07) and every
reserved/unassigned month are explicitly off-limits for the duration of
this experiment. No BTC data is used for any model-selection decision
here.

## Frozen event definition (identical to TRAIN, not renegotiated)

An event is a candle on which, for a specific, already-created Order
Block (from the real, unmodified `OrderBlockTracker`/`MarketStructureTracker`
chain):
1. Wick-based mitigation first reaches 100% (`mitigation_pct >= 1.0`,
   via `compute_mitigation`, wick-only).
2. That same candle's close does **not** confirm invalidation (bullish:
   close is not `< zone_low`; bearish: close is not `> zone_high`).
3. The close lands back on the non-invalidated side of the far boundary
   (equivalently: inside or beyond the favorable side of `[zone_low, zone_high]`).
4. Under Policy A, this candle is exactly the one that retires the block
   to `mitigated` (Breaker-eligible).
5. Under Policy C, this candle marks `mitigation_status = "fully_mitigated"`
   but leaves `invalidated = False` — no Breaker eligibility yet.

This is exactly `PolicyBOrderBlockState.wick_full_traversal_reclaimed`'s
first-transition event, unchanged from the TRAIN sprint's own
implementation in `strategy/research/order_block_lifecycle_policy_b.py`.
**Not modified for this experiment.**

## Frozen de-duplication rule (fixed using TRAIN information only)

TRAIN found 71–79% of raw events share zone overlap with another event.
The following deterministic rule is frozen, using only structural
identity, zone overlap, and event timing — never price outcome:

1. Group events by direction (bullish/bearish) within each VALIDATION
   month independently (no cross-month clustering).
2. Within a direction, sort events by `traversal_bar_i` (ascending).
3. Walk the sorted list; add each event to the current open cluster if
   its zone `[zone_low, zone_high]` overlaps the **cluster's most
   recently added event's** zone AND its `traversal_bar_i` is within 20
   completed 15m bars of that same event. Otherwise, close the current
   cluster and start a new one with this event.
4. **Representative selection per cluster: the earliest event by
   `traversal_bar_i`** (a structural/temporal property, never a
   price-outcome property) is the de-duplicated representative.
5. Both raw (all events) and de-duplicated (one representative per
   cluster) results are reported. **De-duplicated is primary.**
6. Residual dependence between clusters (e.g., two different-direction
   clusters responding to the same underlying volatility event) is not
   further modeled — documented as an acknowledged limitation, not
   corrected for, since doing so would require a new, unfrozen rule.

This is the exact clustering rule already used descriptively in the
TRAIN addendum (Section 7 there), now formally frozen for VALIDATION
before results are seen.

## Primary endpoint — competing-risks first passage

For each **de-duplicated** event, beginning with the **first completed
15-minute candle after** the traversal-and-reclaim candle (the traversal
candle itself contributes no outcome — "no same-event-candle execution
or outcome credit"):

- **ATR at event time**: the `AverageTrueRangeTracker`'s (period 14,
  matching `OrderBlockTracker`'s own default) point-in-time `.current()`
  value as of the traversal candle itself — computed from a standalone
  tracker instance fed the identical candle stream, never recomputed
  using any candle after the traversal candle.

**Bullish block, frozen formulas** (`zone_high`, `zone_low`, `atr` as
defined above; `candle` iterated forward one at a time starting the bar
after traversal):
- Favorable-first: `candle["high"] - traversal_close >= 1.0 * atr`
- Invalidation-first: `candle["close"] < zone_low`

**Bearish block, frozen formulas** (mirrored):
- Favorable-first: `traversal_close - candle["low"] >= 1.0 * atr`
- Invalidation-first: `candle["close"] > zone_high`

**Resolution rule, evaluated candle-by-candle, forward only:**
- If invalidation-first is true on this candle and favorable-first is
  false on this same candle → **invalidation wins**.
- If favorable-first is true on this candle and invalidation-first is
  false on this same candle → **favorable wins**.
- **If both conditions are true on the same candle** (ambiguous —
  intrabar order unknown) → classified as **ambiguous**, and for the
  **primary, conservative result, counted as invalidation-first**.
  Reported separately both ways (Section "Ambiguity sensitivity").
- If neither is true, advance to the next candle.
- If the month ends (or the tracked Order Block would exceed
  `max_age_bars`) before either resolves → **right-censored** — not a
  win or loss, excluded from the win/loss rate numerator but retained in
  the denominator for censoring-rate reporting.
- Early invalidations (e.g., on the very next candle) are **never
  discarded** — they are the fastest possible "invalidation-first"
  outcomes and count fully.
- **No conditioning on surviving to any later horizon** — every
  de-duplicated event enters the primary analysis exactly once, at event
  time, regardless of how quickly it resolves.

## Secondary endpoints (frozen, same complete cohort)

- `+0.5 ATR` and `+2.0 ATR` favorable-first vs. invalidation-first (same
  competing-risks logic, only the favorable threshold changes).
- Time to favorable-threshold resolution and time to invalidation
  (bars), reported separately for whichever occurred, plus full
  time-to-invalidation distribution regardless of what won the race.
- Status at 1, 2, 4, 8, 16, 32 bars, computed for **every** event
  (favorable-first-already / invalidated-already / still-unresolved),
  never restricted to a survivor subset for this specific table (a
  clearly-labeled separate survivor-conditioned table may accompany it).
- Original-direction and prospective-breaker-direction raw return at
  each horizon (signed, from traversal close).
- MFE/MAE from traversal close, in ATR and zone-width units (as in
  TRAIN).
- Probability of a new favorable `structural_break_event` (same
  direction as the original block) occurring before invalidation.
- Percentage still censored/unresolved at every horizon.

Unconditional (complete-cohort) statistics are primary. Any
survivor-conditioned table (as TRAIN reported) is explicitly labeled
secondary/descriptive only, never used to support the primary
recommendation.

## Optional sequential simulation

Not included in this experiment. A defensible trade specification (entry
timing, stop, fixed target, fee/slippage model) cannot be written without
effectively designing a new setup, which is out of scope here. Per
instruction, this is skipped, and real P&L testing is deferred to a
future, separately-authorized S008 ablation.

## Statistical assessment plan

Results are reported: pooled; per month/regime; by direction (bullish/
bearish); raw and de-duplicated; with the ambiguous-same-bar candles
included (primary, conservative) and excluded (sensitivity check); and
with a simple cluster-aware confidence interval (Wilson score interval
computed on the de-duplicated N, not the raw N, to avoid treating
overlapping blocks as independent observations).

## Promotion criteria (restated verbatim, not to be altered post-hoc)

Primary evidence supports Policy C only if, in the **de-duplicated,
pooled** cohort:
1. `+1 ATR before close invalidation` favors the original-direction
   interpretation.
2. Direction of the effect is consistent in at least 3 of 4 VALIDATION
   months.
3. The result is not driven by one month, one direction, or a small
   number of clusters.
4. The effect survives the conservative same-bar (ambiguous-as-invalidation)
   handling.
5. Policy C does not retain a large population of stale blocks for
   impractically long periods (assessed via the time-to-resolution/
   censoring distribution).
6. TRAIN-to-VALIDATION degradation is disclosed and judged acceptable.

If any condition fails, the result is `KEEP POLICY A` or `INCONCLUSIVE` —
not a renegotiated threshold or definition.

## Confirmation

This protocol is written and this file saved to disk before any
`SOLUSDT-1m-2024-11.csv`, `2024-08`, `2024-10`, or `2025-05` file is
opened by any script in this experiment. The hash below is computed
immediately after saving, before any VALIDATION data access.

---
FROZEN — SHA-256 of this file (computed over the file as saved, before
any VALIDATION data was loaded): see `docs/order_block_policy_c_validation_protocol.sha256`
