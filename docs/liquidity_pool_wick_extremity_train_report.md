# LuxAlgo Wick-Extremity Zone — Controlled Geometry Ablation — SOL TRAIN Report

**Status: TRAIN-only exploratory sprint. Not a VALIDATION-grade claim,
not a production change.** Frozen protocol:
`docs/liquidity_pool_wick_extremity_train_protocol.md`, SHA-256
`9d6063fdb5f850564b702a0ac62e696d453a4d5bb6abd6600a17452e98619942` —
verified unchanged immediately before the TRAIN harness's first run and
again immediately before this report was written.

## 1. Architecture audit

Production `LiquidityPool` (`strategy/features/liquidity_pool.py`) is a
**band**, not a line: `zone_high`/`zone_low`, widened by
`register_touch` (`zone_high = max(...)`, `zone_low = min(...)`)
whenever a same-direction candidate lands within
`atr * tolerance_atr_multiplier` of the current band. Both wick-breach
and close-reclaim (`LiquidityPool.check_sweep`, Policy A) are evaluated
against the **same** boundary — the band's outer edge.

Three contributing source types, three anchor-eligibility profiles:
- `round_number` — pure arithmetic; **never** anchored to a real candle.
- `session_high`/`session_low` — the contributed price (`period["session_high"]`/
  `["session_low"]`) is **exactly equal to** the candle's own real
  high/low at `high_timestamp`/`low_timestamp`
  (`strategy/features/session_boundaries.py:284-315`) — directly,
  exactly anchorable.
- `equal_highs`/`equal_lows` — the contributed price is
  `EqualLevelCluster.level = sum(pivot_prices)/len(pivot_prices)`, a
  running **mean** of the cluster's own individual pivot prices, not
  any single candle's real wick. `EqualLevelCluster.to_dict()`
  (`strategy/features/equal_highs_lows.py:150-161`) already exposes
  `pivot_prices`/`pivot_timestamps` as fresh list copies, so the
  cluster's own most extreme individual pivot is directly recoverable —
  anchorable one level deeper than the contributed mean.

`LiquidityPool.register_touch` retains only `contributing_touches`
(timestamps) and `sources` (deduplicated source-type strings) —
per-touch `(price, source, timestamp)` triples are discarded by
production's own public data, motivating the research-only touch
ledger built for this sprint (Section 3).

## 2. Frozen protocol

Written and hashed **before** any TRAIN outcome was computed
(`docs/liquidity_pool_wick_extremity_train_protocol.md`). Recorded
there, not restated in full here: geometry formulas, the eligibility
rule (a pool is Wick-Zone-eligible iff its **current defining touch** —
tracked causally — has a resolvable candle anchor), the tie-break rule
(earliest timestamp wins among ties), replay-safety rules
(`zone_available_at`, creation-bar exclusion, freeze-after-confirmation),
de-duplication (reused unchanged), the directional first-passage
endpoint (reused unchanged from
`strategy/research/liquidity_pool_staleness_telemetry.py`), the S001
linkage requirements, and the decision rule.

## 3. Implementation (research-only, zero production footprint)

`strategy/features/liquidity_pool.py` is **not modified**. Three new
research modules, 37 tests, all passing:

- `strategy/research/liquidity_pool_wick_extremity.py` — pure functions:
  `wick_zone_boundaries`, `check_wick_zone_sweep`, `resolve_anchor`.
  18 tests (`tests/test_liquidity_pool_wick_extremity.py`), covering all
  12 required causal scenarios plus symmetry/determinism/tie-break
  checks, including a direct proof (`test_production_policy_a_unchanged`)
  that `strategy/features/liquidity_pool.py`'s own `check_sweep`
  behavior is untouched.
- `strategy/research/liquidity_pool_wick_extremity_ledger.py` — a
  temporary, uninstallable monkeypatch of `LiquidityPool.register_touch`
  (calls the real, unmodified method **first**, with unmodified
  arguments, then only observes) plus per-instance wrapping of one
  `LiquidityPoolTracker`'s own `_detect_new_equal_level_candidates` /
  `_detect_new_session_candidates` (each delegates to the original
  bound method unchanged; only additionally stashes the exact
  contributing cluster/period dict). 6 tests
  (`tests/test_liquidity_pool_wick_extremity_ledger.py`), including
  `test_production_output_byte_identical_with_and_without_ledger` — a
  direct, full-snapshot equality proof that installing the ledger does
  not alter `LiquidityPoolTracker.snapshot()` output in any way, and
  `test_uninstall_restores_exact_original_method`.
- `strategy/research/liquidity_pool_wick_extremity_eligibility.py` —
  `current_defining_touch` (causal, tie-break-respecting) and
  `anchor_for_defining_touch` (dispatches `resolve_anchor` by source).
  13 tests (`tests/test_liquidity_pool_wick_extremity_eligibility.py`),
  including `test_causal_prefix_consistency_no_lookahead`, which proves
  the defining touch after *k* observed touches depends only on those
  *k* touches.

Full suite: **1029 passed** (992 pre-existing + 37 new), 0 failed.

## 4. Replay-safety proof

- `zone_available_at = anchor_timestamp`: a pool's Wick Zone cannot be
  evaluated for a sweep on or before its own anchor candle — enforced
  in the harness (`current_candle["timestamp"] <= anchor.anchor_timestamp`
  → skip).
- The pool's own creation bar is excluded from Wick-Zone evaluation
  (`i == origin_bar_i` → skip), mirroring production Policy A's own
  inherent immunity to this (its `_check_sweeps` runs before
  `_detect_new_*` in `_ingest`, so a pool cannot be swept on the same
  candle it is created — confirmed by direct code reading, not assumed).
- `current_defining_touch` is recomputed only from touches already
  observed at time *t* (proved by
  `test_causal_prefix_consistency_no_lookahead`); a pool's eligibility
  can change over its life but never using information from a later bar.
- `equal_highs`/`equal_lows` cluster snapshots are captured via
  `dict(cluster)` at the exact moment a touch is detected; because
  `EqualLevelCluster.to_dict()` already returns fresh `list(...)` copies
  of `pivot_prices`/`pivot_timestamps` on every call
  (`strategy/features/equal_highs_lows.py:159-160`), this shallow copy
  is a genuine point-in-time snapshot, never a live-mutating reference
  to the tracker's evolving cluster.

## 5. Event population

Pool identity is the `(direction, created_at)` tuple, matching every
prior sprint's own linkage convention.

| Month | Raw pools | Dedup pools | Eligible (dedup) | Eligible % | Wick-swept | Wick-censored |
|---|---|---|---|---|---|---|
| 2024-02 | 1208 | 1207 | 68 | 5.6% | 59 | 9 |
| 2024-04 | 1233 | 1233 | 55 | 4.5% | 36 | 19 |
| 2024-09 | 1363 | 1363 | 62 | 4.5% | 45 | 17 |
| 2025-12 | 1237 | 1237 | 78 | 6.3% | 64 | 14 |
| **Pooled** | **5041** | **5040** | **263** | **5.2%** | **204** | **59** |

De-duplication removed only 1 pool total across all 4 months (1208→1207
in 2024-02, unchanged elsewhere) — this pool population is already
near-fully-deduplicated by production's own greedy clustering, matching
the pattern already observed in the prior Liquidity Pool Policy C
sprint.

Wick-anchor source at confirmation (pooled, n=204): `equal_highs` 76,
`equal_lows` 75, `session_high` 31, `session_low` 22. `round_number` is
never eligible by construction (0, as required).

**Eligibility is genuinely rare**: only ~5.2% of all pools ever have a
real-candle-anchorable defining touch, pooled and consistent across all
four TRAIN months (4.5%–6.3%). This is the dominant limitation of this
whole ablation and is treated as a frequency finding, not spun toward
either verdict — see Section 8.

## 6. Directional first-passage results (eligible pools only, A vs. W on the SAME subset)

Primary endpoint (+1 ATR favorable / −1 ATR adverse), pooled:

| Policy | Favorable rate | n resolved | n censored | n eligible |
|---|---|---|---|---|
| A (production) | 49.8% | 235 | 28 | 263 |
| W (Wick-Extremity) | 52.2% | 203 | 60 | 263 |

Per month:

| Month | n eligible | A favorable | A n | W favorable | W n |
|---|---|---|---|---|---|
| 2024-02 | 68 | 54.8% | 62 | 50.8% | 59 |
| 2024-04 | 55 | 56.3% | 48 | 47.2% | 36 |
| 2024-09 | 62 | 44.4% | 54 | 52.3% | 44 |
| 2025-12 | 78 | 45.1% | 71 | 56.3% | 64 |

**A favors 2 of 4 months (2024-02, 2024-04); W favors the other 2
(2024-09, 2025-12)** — no consistent directional advantage for either
policy across months.

Per direction (pooled): buy_side A=51.2% (n=121) vs. W=53.8% (n=106);
sell_side A=48.2% (n=114) vs. W=50.5% (n=97) — both directions show the
same small, non-material A/W gap.

Per source (pooled): `session_high` A=48.4% vs. W=41.9% (n=31 each,
W worse here); `session_low` A=59.1% vs. W=63.6% (n=22 each); `equal_highs`
A=53.9% vs. W=58.7% (n=76/75); `equal_lows` A=44.0% vs. W=46.7% (n=75
each) — mixed, no source shows a large, consistent A/W gap.

Secondary endpoint (+2 ATR / −1 ATR), pooled: A=34.2% (n=231),
W=33.0% (n=200) — same pattern, no material difference.

MFE/MAE (descriptive only, mean ATR units, pooled): A mean MFE=3.045,
mean MAE=2.896 (n=235); W mean MFE=2.999, mean MAE=2.956 (n=204) —
nearly identical.

Same-bar ambiguous resolutions (counted conservatively as adverse, per
protocol): A=2/235, W=1/204 — negligible either way.

**Agreement/A-only/W-only breakdown** (pooled, n=263 eligible pools):
agreement (both A and W confirm a sweep) = 204; A-only (A confirms, W
never does within the same TRAIN horizon) = 31; neither resolves before
month-end = 28; **W-only = 0**.

### Single-case verification of the W-only=0 pattern (not treated as automatically trustworthy)

Zero `W_only` events across 263 eligible pools is exactly the kind of
suspiciously clean pattern this project's own prior sprints have found
concealing a bug (the creation-bar spurious-sweep bug in the Policy C
VALIDATION sprint). Direct inspection of one `agreement` case
(2024-02, sell_side, `equal_lows` source) found: Policy A's own zone_low
= 98.6095; Policy W's outer boundary = 98.607 (marginally more extreme,
consistent with `equal_lows`' anchor being the cluster's own most
extreme individual pivot, always ≤ the cluster's mean); Policy W's inner
boundary = 98.783 — **less extreme (closer to price) than Policy A's own
zone_low**. This means Policy W's full condition (wick beyond 98.607
**and** close back above 98.783) is strictly harder to satisfy than
Policy A's single-boundary condition (wick beyond 98.6095 **and** close
back above 98.6095 — the same number for both halves) whenever the
inner boundary sits inside the outer one, which it structurally always
does (`inner` is the anchor candle's own body edge, `outer` its wick
extreme). **Policy W's full-zone-rejection is a strictly narrower filter
than Policy A's single-boundary rule for this codebase's definitions** —
mechanistically explaining why W never fires without A also firing.
This is a real structural property of the two geometries as defined
here, not a harness bug — but it is a material, pre-registration-time-
unanticipated finding in its own right (see Section 8).

## 7. S001 comparison

**S001 under Policy A (real, exact linkage)**: reused the proven method
unchanged — instrumented `strategy_callback` calling the real
`LiquiditySweepReversalSetup._find_fresh_sweep(snapshot)` directly, keyed
by the exact 1-minute `current_candle` timestamp; `OPENED`/`CLOSED`
paired by chronological order. **61/61 trades exactly linked, 0
unmatched**, across all 4 TRAIN months (15+16+19+11).

**S001 under Policy W**: a full shadow arbitration re-simulation
(mirroring `_find_fresh_sweep`'s own selection logic, fed Policy-W
events) was **not built**. Cross-referencing the 61 real, exactly-linked
S001 trades against the eligible-pool set already computed in Section 5
found only **22 of 61 real trades** trade an eligible-under-W pool at
all, and only **16 of those 22** trade a pool Policy W actually swept.
A shadow re-arbitration on a base this small (16 trades, pooled across
4 months, 3–6 per month) would not produce evidence more reliable than
directly reading the real trades' own production P&L split by pool
eligibility/sweep status — so that direct, no-simulation-needed
cross-tabulation was used instead, and is reported here as the S001-level
evidence. Not building the shadow arbitration, once this small base was
known, is disclosed explicitly as a deviation from the frozen protocol's
Section "S001 linkage," item 2 — made for a stated, honest reason
(sample size), not to avoid an inconvenient result.

| Subset | n | Win rate | Total net P&L | Avg net P&L |
|---|---|---|---|---|
| All S001 trades (TRAIN pooled) | 61 | 36.1% | −$672.92 | −$11.03 |
| Non-eligible-pool trades | 39 | 43.6% | +$454.24 | +$11.65 |
| Eligible-pool trades (any anchorable source) | 22 | 22.7% | −$1,127.16 | −$51.23 |
| Eligible **and** Policy-W-swept | 16 | 25.0% | −$707.69 | −$44.23 |
| Eligible but Policy W never fired | 6 | 16.7% | −$419.47 | −$69.91 |

Both eligible-pool subgroups (Wick-Zone-swept and not) underperform the
non-eligible baseline by a wide margin, but **do not differ meaningfully
from each other** (25.0% vs. 16.7% win rate on n=16 vs. n=6 — well within
noise for samples this small). This does **not** support Policy W as an
S001-level improvement over Policy A; if anything it suggests whatever
makes a pool anchorable (proximity to a session extreme or an equal-level
cluster, rather than a bare round number) correlates with worse S001
outcomes generally — a separate, unexplained pattern, noted here as an
observation for a possible future sprint, explicitly **not** interpreted
as evidence for or against this ablation's own question.

## 8. Frequency and sample-size effects

- Eligibility (~5.2% pooled, 4.5%–6.3% per month) is the binding
  constraint on this whole analysis. `round_number` sources dominate the
  overall pool population (visible in `sources_at_creation` for the
  large majority of pools not appearing in Section 6's per-source table
  at all) and are never anchorable by construction — this is an inherent
  property of SOL's own price structure and this instrument's round-number
  spacing (1.0–2.0 over the four TRAIN months), not a parameter this
  sprint tuned or could tune.
- At n≈200–235 resolved outcomes per policy pooled, the observed ~2.4
  percentage-point primary-endpoint gap (52.2% vs. 49.8%) is well within
  one binomial standard error (≈3.5 points at n≈200, p≈0.5) — not a
  material effect by the frozen decision rule's own standard.
- S001-level evidence (n=16–22) is too small to support any independent
  conclusion on its own; it is reported descriptively, not weighted as
  strongly as the module-level result.

## 9. Limitations and rejected alternatives

- A from-scratch LuxAlgo pivot/cluster reimplementation was rejected
  (would no longer be a valid ablation of the same pools) in favor of
  the touch-ledger observer wrapper — as pre-registered.
  Adding the touch/anchor granularity as new production snapshot fields
  was considered and rejected as premature for a still-research sprint —
  as pre-registered.
- A full shadow S001-under-W arbitration simulation was not built once
  its base sample (16 trades) was known to be too small to add reliable
  evidence beyond the direct real-trade cross-tabulation used instead —
  disclosed in Section 7, not decided before seeing the sample size.
- The W-only=0 finding (Section 6) means this ablation, as geometrically
  defined here, can only ever make Policy A's own detection **stricter**
  (a subset of A's events), never find sweeps A misses — an intrinsic
  property of "inner boundary strictly inside outer boundary" for every
  anchor this sprint's eligibility rule can produce, not a tunable
  parameter.
- Round-number ineligibility (~95% of all pools) means any future
  extension of Wick-Zone geometry to round-number-sourced pools would
  require a fundamentally different anchor definition (round numbers
  have no candle to anchor to) — out of scope here, noted for a possible
  future, separately pre-registered sprint.

## 10. Verdict

**KEEP CURRENT GEOMETRY.**

The frozen decision rule's promotion criterion 1 requires Policy W to be
materially better than Policy A on the same eligible subset, pooled
**and** in at least 3 of 4 TRAIN months. Neither holds: the pooled
primary-endpoint gap (52.2% vs. 49.8%) is within noise at this sample
size, and only 2 of 4 months favor W (the other 2 favor A). The
secondary endpoint, MFE/MAE, and the real-trade S001 cross-tabulation
all corroborate the same "no material advantage" conclusion. This is
not classified as INCONCLUSIVE-for-insufficient-sample: the eligible
subset, while a small fraction (~5.2%) of the total pool population, was
large enough (263 pools, ~200+ resolved outcomes per policy) to produce
a stable result close to 50/50 rather than wildly conflicting or
underpowered — the frozen rule's own "equal or worse... no material
directional advantage" KEEP condition is squarely met.

## 11. Proposed next step

None proposed by this report. Per the authorizing instructions, this
sprint stops here: no production logic change, no Touch Count/Volume
experiment, no new data partition access, no further module work,
pending the user's explicit direction on what (if anything) to research
next.

---
Deliverables: `docs/liquidity_pool_wick_extremity_train_protocol.md` +
`.sha256`, `strategy/research/liquidity_pool_wick_extremity.py`,
`strategy/research/liquidity_pool_wick_extremity_ledger.py`,
`strategy/research/liquidity_pool_wick_extremity_eligibility.py`,
`tests/test_liquidity_pool_wick_extremity.py`,
`tests/test_liquidity_pool_wick_extremity_ledger.py`,
`tests/test_liquidity_pool_wick_extremity_eligibility.py`, this report.
Full test suite: 1029 passed, 0 failed.
