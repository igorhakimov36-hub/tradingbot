# Liquidity Pool Hybrid Policy C — SOL VALIDATION Experiment Report

**Recommendation: INCONCLUSIVE for full promotion, as originally framed** — the
specific hypothesis that motivated Policy C ("captures a materially-sized
population of genuine sweeps Policy A would otherwise miss entirely")
is **refuted at exactly 0%**. A different, real, well-evidenced, and
TRAIN-consistent finding survives instead: Policy C corrects the **timing/
staleness attribution** of sweeps Policy A already eventually recognizes.
This is a genuine result worth acting on, but it is not what "promote
Policy C" was originally proposed to mean, so it is reported honestly as
its own, narrower finding rather than forced into a clean yes. No
production behavior was changed.

## 1. Frozen protocol and hash

`docs/liquidity_pool_policy_c_validation_protocol.md`, written and hashed
before any VALIDATION file was opened. SHA-256:

```
af7890c9e1ea60aea30fc9880af997e6290b27711d738a054876f69f5bc84048
```

Re-verified via `sha256sum -c` immediately before writing this report —
**confirmed unchanged** (`liquidity_pool_policy_c_validation_protocol.md: OK`).

## 2. Exact A/B/C state definitions

Restated briefly from the frozen protocol (full text there, not
altered): **Policy A** is production's own unmodified
`LiquidityPool.check_sweep` (same-candle wick-beyond-then-close-back
only). **Policy B** (immediate invalidation on first close beyond, no
same-candle exception) is a fixed control, not separately re-tested this
sprint beyond the TRAIN sprint's own already-decisive rejection (58%
unconditional reclaim rate there argued against it; nothing here
contradicts that). **Policy C**: `UNSWEPT` → (same-candle check, always
first) → `ACCEPTANCE_PENDING` on a bare close beyond → within the next
*N* candles (inclusive of the *N*th), a close back through the **boundary
frozen at pending-entry** is a multi-candle sweep; otherwise, on the
candle immediately after the *N*th pending candle, → `ACCEPTED_INVALIDATED`
(terminal, can never later sweep). Implemented exactly as specified in
`strategy/research/liquidity_pool_policy_c.py`.

## 3. Tests and full-suite result

17 tests in `tests/test_liquidity_pool_policy_c.py` (all 15 required
scenarios, some split into two tests each for buy/sell symmetry): fresh
same-candle sweep; first close beyond entering pending; reclaim inside
8/16/32 bars; reclaim exactly on the window's own boundary candle
(included); acceptance after window expiry; a very late reclaim cannot
resurrect an already-invalidated pool; at most one sweep event per
pool's lifetime; distinct identity for a new nearby pool; buy/sell
symmetry (both the same-candle and pending paths); independent
instances; right-censoring via explicit finalization (not silently left
non-terminal); no lookahead; same-bar precedence (same-candle check
always evaluated before the pending-window logic, proven directly);
determinism; and a direct confirmation production's own `LiquidityPool.check_sweep`
is unmodified.

**Full suite: 972/972 passing.**

## 4. Complete lifecycle tables (de-duplicated, per month, all 3 windows)

| Month | Regime | n | Window | SWEPT (same/multi) | ACCEPTED_INVALIDATED | Other |
|---|---|---:|---:|---|---:|---:|
| 2024-11 | strong bull | 1,471 | 8 | 1,121 / 9 | 318 (21.6%) | 23 |
| | | | 16 | 1,191 / 9 | 248 (16.9%) | 23 |
| | | | 32 | 1,263 / 10 | 175 (11.9%) | 23 |
| 2024-08 | strong bear | 1,066 | 8 | 797 / 4 | 249 (23.4%) | 16 |
| | | | 16 | 858 / 6 | 186 (17.4%) | 16 |
| | | | 32 | 910 / 6 | 134 (12.6%) | 16 |
| 2024-10 | low-vol/directionless | 826 | 8 | 631 / 1 | 180 (21.8%) | 14 |
| | | | 16 | 673 / 1 | 137 (16.6%) | 15 |
| | | | 32 | 704 / 1 | 106 (12.8%) | 15 |
| 2025-05 | range/low-vol | 1,736 | 8 | 1,304 / 14 | 396 (22.8%) | 22 |
| | | | 16 | 1,386 / 19 | 309 (17.8%) | 22 |
| | | | 32 | 1,469 / 22 | 222 (12.8%) | 23 |

("Other" = still `UNSWEPT`/`ACCEPTANCE_PENDING` at month end, i.e.
censored.)

## 5. Raw versus de-duplicated results

| Month | Raw | De-duplicated | Reduction |
|---|---:|---:|---:|
| 2024-11 | 1,471 | 1,471 | 0 (0.00%) |
| 2024-08 | 1,066 | 1,066 | 0 (0.00%) |
| 2024-10 | 828 | 826 | 2 (0.24%) |
| 2025-05 | 1,736 | 1,736 | 0 (0.00%) |

Confirms the TRAIN finding: overlap is structurally near-absent for
Liquidity Pools (formation itself requires tolerance-based clustering,
which already prevents two overlapping pools of the same direction from
ever coexisting). No conclusion here depends meaningfully on
de-duplication.

## 6. Directional response analysis

Median MFE/MAE (ATR-at-event units), pooled across all 4 VALIDATION
months, for the three populations this experiment's core question turns
on:

| Population | n | h=1 MFE/MAE | h=4 MFE/MAE | h=16 MFE/MAE | h=32 MFE/MAE |
|---|---:|---|---|---|---|
| `policy_a_late` (A resolves strictly after C(16) already invalidated) | 698 | 0.475 / 0.492 | 0.818 / 0.917 | 1.571 / 1.640 | 2.217 / 2.319 |
| `policy_c_multi_candle` (C's own genuinely distinct-timing sweep) | 35 | 0.365 / 0.396 | 0.651 / 0.647 | **1.500 / 1.028** | **1.894 / 1.731** |
| `same_candle_agree` (A and C agree, identical candle) | 3,986 | 0.398 / 0.410 | 0.803 / 0.819 | 1.584 / 1.591 | 2.256 / 2.326 |

**`policy_a_late` and `same_candle_agree` both show MAE slightly
exceeding MFE at every horizon** (adverse excursion modestly larger than
favorable, consistent with a reversal setup whose typical edge is thin
at this raw, cost-free measurement). **`policy_c_multi_candle` is the
one population where MFE clearly exceeds MAE from h=8 onward** (h=16:
1.500 vs. 1.028; h=32: 1.894 vs. 1.731) — a real, if small-sample
(n=35 pooled), signal that Policy C's own genuinely-distinct-timing
sweeps have *better*, not worse, directional validity than either the
late-Policy-A population or the ordinary agreement population. This
directly satisfies promotion criterion 4 for the population it applies
to, though the population itself is small.

## 7. Window sensitivity (8/16/32)

The invalidated-percentage decreases smoothly and monotonically as the
window widens, in **every** month — e.g. 2024-11: 21.6% → 16.9% → 11.9%;
2025-05: 22.8% → 17.8% → 12.8%. This is coherent, expected behavior (a
wider window gives more pools a chance to reclaim before being written
off), not fragile or erratic — window=16 does not "alone succeed while 8
and 32 fail materially"; all three move together in the same direction
with no discontinuity. The fragility clause in the frozen protocol does
not trigger.

## 8. TRAIN-versus-VALIDATION comparison

Using the identical, unmodified Policy C(16) analysis applied to both
datasets:

| | TRAIN (2024-02/04/09, 2025-12) | VALIDATION (2024-11/08/10, 2025-05) |
|---|---:|---:|
| Pooled n | 5,040 | 5,099 |
| Invalidated (window=16) | 861 (17.1%) | 881 (17.3%) |
| Pools where both A and C(16) eventually resolve | 738 | 740 |
| Of those, A resolves strictly after C already invalidated | 698 (94.6%) | 697 (94.2%) |

**Degradation from TRAIN to VALIDATION is negligible** (17.1%→17.3%
invalidated; 94.6%→94.2% late-A-rate) — both figures are essentially
identical across the two independent datasets, satisfying promotion
criterion 7 cleanly.

## 9. Exact S001 linkage results

**Exact linkage achieved: 71/71 closed trades matched (100%), zero
approximation.** Mechanism: `strategy_callback` was wrapped to call the
real, unmodified `LiquiditySweepReversalSetup._find_fresh_sweep(snapshot)` —
the exact pure, read-only function the real `evaluate()` call already
uses internally — on the exact snapshot object already built for that
bar, at the exact 1-minute `current_candle` timestamp the trade journal
itself uses. Since `_find_fresh_sweep` returns at most one zone, no
signal can ever match more than one candidate ambiguously; since the
match key is the zone's own `(direction, created_at)` identity (not a
timestamp proximity search), no event was assigned by temporal
proximity. The wrapper's own return value is passed through completely
unchanged, so no decision or trade was altered by this instrumentation.

| Tag | n | Win rate | Total P&L | Avg P&L | PF |
|---|---:|---:|---:|---:|---:|
| `fresh_same_candle_sweep` | 46 | 34.8% | -651.20 | -14.16 | 0.82 |
| `delayed_current_rule_sweep` | 25 | 44.0% | +317.57 | +12.70 | 1.19 |

**This remains diagnostic-only, secondary evidence** — not used to
justify the recommendation below, per instruction. It is directionally
consistent with the TRAIN sprint's own (approximately-matched, now
superseded) finding that delayed sweeps did not perform worse — now on
firmer, exact-linkage footing, but still too small a sample (25 vs. 46
trades) to be decisive on its own.

**Two bugs were found and fixed during this sprint, disclosed in full:**

1. **Creation-bar spurious-sweep bug** (affects the main VALIDATION
   harness): the research harness initially evaluated a newly-created
   pool's sweep condition against *its own creation candle*. Production
   never does this — `LiquidityPoolTracker._ingest()`'s own
   `_check_sweeps()` runs *before* that candle's new touches are
   registered, so a pool can never be swept (or flagged close-beyond) on
   the exact candle that created it. This inflated same-candle-sweep
   counts and, more importantly, produced a spurious, window-independent
   "Policy C captures pools Policy A never resolves" result (initially
   40.8%, identical across all three window sizes — a red flag caught by
   noticing the suspicious window-independence, then confirmed by direct
   single-case inspection of a degenerate, zero-width, round-number pool).
   Fixed by skipping each shadow's own origin bar; the corrected result
   (Section 4, endpoint 5 discussion below) is 0%, not 40.8%.
2. **`record_closed` uses the exit timestamp, not entry** (affects the
   first S001 exact-linkage attempt): the initial linkage script matched
   a `ClosedTrade`'s own `.timestamp` (confirmed, by reading
   `backtest_runner.py:444-457`, to be recorded at `record_closed()`
   time — i.e., the *exit* bar) against the entry-time-keyed
   `exact_links` map, which almost never coincided, producing near-total
   "no exact linkage found" results (21/21, 19/19, etc., unmatched, in
   the sense that the count of recorded links equaled trade count but
   the lookup itself failed). Fixed by pairing `opened[i]` with
   `closed[i]` by chronological order — valid because this backtest
   engine holds at most one open position at a time, confirmed
   throughout this project's architecture. After the fix, 71/71 trades
   matched exactly.

Both bugs were caught by direct, single-case inspection rather than
trusting an initially-plausible-looking aggregate number — consistent
with this project's established verification discipline.

## 10. HELD_OUT and VALIDATION confirmation

**SOL FINAL HELD_OUT (2025-02, 2025-07) was never accessed anywhere in
this sprint.** Only the four locked VALIDATION month files
(`SOLUSDT-1m-2024-11.csv`, `-2024-08.csv`, `-2024-10.csv`, `-2025-05.csv`)
were opened, confirmed by the dataset hashes logged in each month's
config output (matching the identical hashes already recorded in the
Order Block Policy C VALIDATION experiment for the same months, an
independent consistency check). No BTC data was used for any
model-selection decision.

## 11. Recommendation

**Applying the seven promotion criteria literally, as a conjunctive
checklist ("promote only if [all of]"), not selectively:**

1. Bounded state machine separates fast/stale sweeps consistently across
   ≥3/4 months — **met**: invalidated-% is 16.6–17.8% in every one of
   the 4 VALIDATION months.
2. Policy C removes a material population of very late/stale Policy A
   sweeps — **met, strongly**: 94.2% of the 740 pools both policies
   eventually resolve show Policy A resolving strictly after Policy C
   already gave up — material in absolute count (740) and rate,
   matching TRAIN almost exactly (94.6%, 738 pools).
3. Policy C captures a material multi-candle rejection population
   **missed by A** — **fails, at exactly 0%.** After fixing the
   creation-bar bug, zero pools that Policy A leaves permanently
   unresolved by month end are ever resolved as `SWEPT` by Policy C, at
   any window size. This is mechanically necessary, not a data
   artifact: Policy C's same-candle check is byte-for-byte identical to
   Policy A's own rule, so any pool Policy A's identical check never
   resolves cannot be resolved by Policy C's identical check either. The
   *only* pools Policy C ever recognizes as swept that aren't
   simultaneous with Policy A are the small `policy_c_multi_candle`
   population (9–19 per month) — and Policy A **eventually** recognizes
   those same pools too (later, via its own same-candle mechanism,
   consistent with the TRAIN finding that virtually every reclaim
   mechanically satisfies the wick rule) — so even this population is
   not "missed by A," only *delayed* relative to Policy C.
4. Retained/new Policy C sweep events show at least equal or better
   directional validity than removed stale events — **met** for the
   `policy_c_multi_candle` population specifically (Section 6: MFE
   clearly exceeds MAE at h≥8, unlike either comparison population), on
   a small sample (n=35).
5. Coherent under 8/16/32 sensitivity — **met**: smooth, monotonic,
   no fragility.
6. No conclusion depends on approximate S001 matching, one month, one
   direction, or overlapping pools — **met**: S001 linkage is now exact
   (100%); every finding is consistent across all 4 months and both
   directions (per-direction breakdown: buy_side 17.7% invalidated,
   sell_side 16.8%, window=16); de-duplication changes nothing.
7. TRAIN-to-VALIDATION degradation disclosed and acceptable —
   **met**: negligible (Section 8).

**Six of seven criteria are cleanly met. Criterion 3 — the specific
premise the promotion decision was framed around ("captures a material
multi-candle rejection population missed by A") — fails at exactly 0%,
not "weakly" or "ambiguously."** This is not noisy or inconclusive data;
it is a clear, mechanistically-explained, well-evidenced negative result
on one specific, named question. Per the instruction not to force a
clean outcome and not to silently reinterpret a failing criterion to
make the checklist pass, the honest verdict for the question as
originally framed is:

**INCONCLUSIVE** for `PROMOTE POLICY C TO ADDITIVE PRODUCTION IMPLEMENTATION`
as originally conceived (a lifecycle change that captures missed
opportunities). The evidence does **not** support treating Policy C as
a source of new, previously-undetected sweep signals. It **does**
support a different, narrower, well-evidenced finding: **Policy A's
existing sweep timestamps frequently (~94% of the time, when both
eventually resolve) understate how long a pool has already been
"beyond" its boundary before the officially-recognized sweep** — a real
staleness/attribution issue, not a missed-detection issue.

## 12. Exact next action requiring approval

Not a promotion of Policy C. If this staleness/timing finding is worth
acting on, the narrower, more defensible next step would be a
**separately-scoped, additive research proposal**: expose
"bars/closes-beyond since a pool's first clean close beyond its
boundary" as a new, purely observational field on the existing
`swept`/`active` snapshot output (no state-machine change, no new
invalidation semantics, no change to `swept_status` or Breaker Block
eligibility) — letting a future setup (e.g., inside an eventual S008
ablation) optionally weight or filter on sweep staleness itself, without
adopting Policy C's bounded-invalidation mechanics or its now-refuted
missed-population premise. This is **proposed only, not started**, and
requires separate authorization before any implementation, TRAIN
re-analysis, or further data access.

---

**Not changing production behavior. Not accessing HELD_OUT. Not
beginning S008 or CVD review.**
