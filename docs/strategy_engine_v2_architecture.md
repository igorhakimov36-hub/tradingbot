# Strategy Engine V2 — Architectural Review (Phase 2, pre-implementation)

**Status: architecture only. No implementation in this document.**

Phase 1 built thirteen Market Intelligence modules, each independently
researched, implemented, tested, and validated on real BTCUSDT/ETHUSDT
data. This document is the institutional design review requested before
any of them are connected to a decision layer: what each module should
expose upward, how those outputs compose into a single snapshot object,
whether the existing scoring-based decision model should survive contact
with this much raw intelligence, and how the backtest pipeline needs to
evolve to make the whole system's value *measurable* rather than assumed.

Nothing here changes existing code. Every Phase 1 module's public
contract stays exactly as shipped — this review is about the layer being
built *on top*, and about a small number of things worth reorganizing
*before* that layer is written.

---

## 1. Module-by-module review

For each module: what it exposes today, what is actually decision-relevant
versus explainability/audit-only, what is redundant now that later modules
exist, and what it naturally groups or must stay separate from.

### Market Structure (BOS/CHOCH, swing pivots, `detect_market_structure`)

Foundational — nearly every later module is built on
`find_swing_pivots`/`get_last_swing_levels`. Decision-relevant: BOS/CHOCH
direction and how recently it occurred, and the last two swing highs/lows
as reference/invalidation levels. **Finding:** `detect_market_structure`'s
crude two-candle BULLISH/BEARISH/RANGE heuristic (used only by the frozen
`strategy_engine.py`) is now inferior to genuine swing-pivot-based
structure, which every Phase 1 module already uses instead. It should not
be extended or trusted going forward — flagged for retirement once V2
replaces the frozen pipeline (see §5), not touched now.

### Fair Value Gaps

Decision-relevant: active (unfilled) gaps as inefficiency/target zones,
and the fill event itself. Groups with Order Blocks / Breaker Blocks /
Liquidity Pools under one **Zones** family — see §2.

### Order Blocks

Decision-relevant: zone location, `mitigation_status`, `touch_count`,
`distance_from_price`. The newer body-based `mitigation_zone_*` fields are
genuinely useful but finer-grained than a first decision layer needs —
classify as available-but-secondary, not omitted. Tightly coupled to
Breaker Blocks (which consume its `mitigated` list directly) — the two
should be presented to the Strategy Engine as one conceptual lineage
(an Order Block's "afterlife"), not two unrelated collections.

### Breaker Blocks

Shares ~90% of its shape with Order Blocks by design (`zone_lifecycle.py`).
This is the strongest concrete argument for a **shared zone schema** at the
snapshot layer (§3) rather than per-type special-casing.

### Mitigation Blocks

Correctly *not* an independent object (fields on Order Block) — this
decision holds and needs no revisiting.

### Equal Highs / Equal Lows

Decision-relevant: `level` + `swept_status` transition (a liquidity-grab
event). `pivot_prices`/`pivot_timestamps` are audit-trail, not
decision-tier. **Important overlap:** an EQH/EQL cluster is literally one
of Liquidity Pools' three sub-detector inputs — for clusters that get
absorbed into a pool, the pool's own `swept_status` supersedes the
cluster's; clusters that never get absorbed retain independent value.

### Session Boundaries

The most cross-cutting *infrastructure* module — CVD, Liquidity Pools, and
Volume Profile all consume it already. For the Strategy Engine directly
(not as plumbing for other modules), only a thin slice matters: which
named session/kill-zone is active right now, and the immediately prior
closed period's high/low. The full multi-anchor historical apparatus is
audit-tier, not something the decision layer should read directly.

### Liquidity Pools

The single most decision-relevant "reversal setup" primitive in the whole
platform — an active pool near price, followed by a sweep with rejection,
is a classic setup. `sources` (which sub-detectors agree) is a good raw
confluence count without being a hidden score. `contributing_touches` is
audit-tier. Groups with Equal Highs/Lows, Session Boundaries (its own
inputs) and with the Zones family (§2) by shared lifecycle shape.

### Delta

Decision-relevant: per-bar `delta_direction`/`delta_strength` as immediate
order-flow confirmation of the *current* bar. **Finding:** `cumulative_delta`
(unanchored, running since tracker start) is now redundant — CVD does this
properly (anchored, windowed, with divergence/exhaustion). Recommend the
snapshot builder scope Delta to per-bar order flow only and let CVD own
all cumulative/anchored order-flow reasoning, avoiding two competing
"cumulative delta" numbers reaching the decision layer. (No change to the
Delta module itself — its `cumulative_delta` field stays; it's simply not
promoted into the snapshot.)

### CVD

Decision-relevant: `price_cvd_divergence_flag` and `cvd_exhaustion_flag`
are exactly the reversal tells the Strategy Engine wants; `cvd_direction`/
`cvd_slope` for trend confirmation. `bars_since_anchor`/
`bars_with_missing_data` are data-quality/audit-tier.

### Correlation Engine / SMT

Decision-relevant: `structural_divergence_flag`/`structural_divergence_history`
(this *is* SMT). **Important nuance for V2's future design, not a change
now:** SMT divergence is only meaningful when the pair is actually
correlated — `price_correlation` should gate whether a divergence reading
is trusted, not be read independently. A "divergence" on a pair with near-zero
correlation is noise, not signal; this comparison belongs in the Decision
Engine's setup logic, not inside the Correlation Engine (which correctly
stays neutral). `lead_lag_bars`/`lead_lag_correlation` are research-tier
for a first decision layer, not immediately actionable. Structurally
distinct from every other family: keyed by symbol *pair*, must support
multiple simultaneous named instances (BTC/ETH, BTC/DXY, ...), never
collapses into the primary symbol's own zones/levels.

### Volume Profile

Decision-relevant: `poc_price`/`value_area_high`/`value_area_low` as
reference levels (a third "levels" family alongside EQH/EQL and Session
highs/lows), HVN/LVN as support/resistance-like magnets/vacuums. The full
`histogram` is valuable for future AI/statistics but not something a
rule-based decision layer consumes directly — audit/AI-tier, not
decision-tier, though it must stay available (never discarded) for that
future use. `value_area_overlap_ratio`/`poc_shift_from_previous_period`
are the acceptance/rejection signal, exactly as designed in Phase 1.12.

---

## 2. The real taxonomy: four families, not thirteen modules

Reviewing all thirteen modules' output side by side, the same handful of institutional
*shapes* keep recurring, independent of which module produced them. This
is the organizing principle the Market Intelligence Snapshot should use —
grouped by **what kind of fact this is**, not by which tracker computed it.

1. **Zones** — a price range with a lifecycle (created → touched →
   resolved): FVG, Order Blocks, Breaker Blocks, Liquidity Pools. These
   already share the same mechanical vocabulary by deliberate design
   (`zone_lifecycle.py`) — `zone_high`/`zone_low`, touch count, a
   mitigation/fill/sweep status that all mean "is this resolved yet,"
   `distance_from_price`. This is the strongest, most concrete grouping
   finding in this review.
2. **Levels** — a single reference price, not a range: Equal Highs/Lows,
   Session highs/lows, Volume Profile POC/VAH/VAL/HVN/LVN. Looser than
   Zones (an HVN's "width" doesn't map onto a session high) — worth a
   *light* shared shape (kind, price, distance, raw), not a forced
   uniform schema that would lose real information.
3. **Order Flow** — Delta (bar-level) → CVD (cumulative/anchored), a
   strict small-to-large hierarchy always read together.
4. **Intermarket** — Correlation Engine/SMT instances, keyed by pair name,
   inherently plural and independent of the primary symbol's own data.

Plus two cross-cutting, non-family pieces that deserve their own top-level
slots rather than being buried inside a family: **Structure** (BOS/CHOCH,
swing levels — the most fundamental, most frequently referenced fact) and
**Session/time context** (a thin "which session are we in right now"
projection, distinct from the full Session Boundaries historical output).

### A real naming inconsistency to normalize — not fix retroactively

FVG/Order Blocks/Breaker Blocks use `bullish`/`bearish`; Liquidity Pools
use `buy_side`/`sell_side` (correct, standard ICT vocabulary for *where
resting liquidity sits*, not a directional forecast). These aren't
interchangeable, and mapping one onto the other is genuinely easy to get
backwards (a buy-side pool sits *above* price, sourced from highs — the
same geometric category as a bearish zone's origin, not a bullish one).

**Recommendation: do not rename any Phase 1 module's fields.** Every one
of those names is tested, documented, and doc-specified — renaming now
would be exactly the kind of interface churn this project has avoided at
every step. Instead, normalize *only at the Snapshot boundary*: every
unified Zone gets a derived, purely geometric
`zone_relative_position: "above_price" | "below_price"` field, safe to
compute uniformly regardless of institutional vocabulary, alongside the
zone's own native `direction` value (preserved as-is, in `raw`).

---

## 3. Market Intelligence Snapshot design

**Principle:** the Snapshot is a thin, deterministic *mapping* over each
tracker's already-existing `.snapshot()` output — never a reimplementation
of any tracker's logic, and never a source of new computation. Building it
is applying "Reuse > Extend > Create" one layer up: read
`OrderBlockTracker.snapshot()["active"]`, reshape into the unified Zone
shape, done.

```
Replay
  ↓
Market Intelligence Modules   (13 trackers, each already synced this step)
  ↓
Snapshot Builder              (pure function: trackers' outputs → MarketIntelligenceSnapshot)
  ↓
Market Intelligence Snapshot  (one object per replay step)
  ↓
Strategy Engine V2            (reads ONLY the snapshot, never a tracker)
  ↓
Execution Simulator
```

The Strategy Engine never imports or calls a feature tracker directly —
enforced by having the Snapshot Builder be the *only* code that touches
`strategy.features.*`. This is a real architectural boundary, not just a
convention: it means every future module (Footprint, once Trade-Level
Infrastructure exists; a future Portfolio layer) only ever needs to extend
the Snapshot Builder, never touch the Strategy Engine itself.

```
MarketIntelligenceSnapshot:
    symbol: str
    timeframe: str
    timestamp: datetime            # current replay instant

    structure: {
        bos_direction, bos_timestamp,
        choch_direction, choch_timestamp,
        last_swing_high, last_swing_low,
    }

    zones: list[Zone]               # unified FVG + Order Block + Breaker Block + Liquidity Pool
    levels: list[Level]             # unified EQH/EQL + session highs/lows + POC/VAH/VAL/HVN/LVN

    order_flow: {
        delta: {...current bar only...},
        cvd: {anchor_name: {...}, ...},   # one or more configured anchors
    }

    sessions: {
        active_now: [session_name, ...],       # e.g. ["london", "london_killzone"]
        previous_period_high_low: {...},        # bounded - immediately prior period only
    }

    intermarket: {pair_name: {...CorrelationTracker snapshot...}, ...}

    volume_profile: {
        current_forming: {...},                 # poc/vah/val/hvn/lvn only, histogram dropped here
        recent_closed: [...],                   # small bounded N, not the full history
    }

    data_quality: {...}             # aggregated completeness flags (bars_with_missing_data etc.)
    context: {}                     # reserved, Context Preservation
```

**Zone (unified schema):**

```
Zone:
    kind: "fvg" | "order_block" | "breaker_block" | "liquidity_pool"
    direction: <the zone's own native value, unchanged>
    zone_relative_position: "above_price" | "below_price"   # derived, unambiguous
    zone_high, zone_low: float
    status: "active" | "resolved"            # unified from filled/mitigated/swept
    resolution_detail: str                    # the ORIGINAL vocabulary, preserved
    resolution_pct: float                     # unified from fill_pct/mitigation_pct
    touch_count: int
    distance_from_price: float
    created_at: datetime
    resolved_at: datetime | None
    source_module: str
    raw: dict                                 # the full, unmodified original snapshot dict
```

The `raw` field is not optional decoration — it's how the unified schema
avoids the one real risk of unification: losing institution-specific detail
(Order Block's `impulse_strength`, Liquidity Pool's `sweep_penetration`
and `sources`) in service of a convenient common shape. Every Zone/Level
carries its full native dict unchanged; the unified fields are for
cross-cutting reasoning ("give me every unresolved zone within 1 ATR of
price, regardless of type"), never a replacement for the original.

**Level (unified schema, deliberately looser):**

```
Level:
    kind: "equal_highs" | "equal_lows" | "session_high" | "session_low" |
          "poc" | "vah" | "val" | "hvn" | "lvn"
    price: float
    distance_from_price: float
    source_module: str
    raw: dict
```

---

## 4. Decision Engine: is scoring still appropriate?

**No — recommend replacing it, not tuning it.** The reasoning:

The current `decision_engine.py` is a hand-weighted sum
(`bos_score` ∈ {0,10,20,30}, `choch_score` ∈ {0,-20}, similar for
liquidity/volume/OI/funding) thresholded at 80. Every Phase 1 module was
built on an explicit, repeated principle: raw, explainable, deterministic
features — *never* a score, *never* a hidden decision. Feeding thirteen
modules' worth of carefully-preserved raw intelligence into a new
hand-tuned weighted sum at the Decision Engine would not fix the
architecture — it would just relocate the exact problem Phase 1 spent a
year avoiding, one layer up.

Concretely, a scalar score has three structural weaknesses that matter
for *this* platform's stated goals:

- **Not statistically measurable per-component.** Once "sell-side pool
  swept" and "CVD showed exhaustion" and "BOS confirmed" are summed into
  one number, you can no longer ask "how did the sweep-alone condition
  perform, historically" — exactly the question the backtest needs to
  answer to prove the new Market Intelligence is worth having.
- **Not AI-compatible in the way "future AI compatible" should mean.**
  Feeding a pre-aggregated score into a future ML model is circular — the
  score is already someone's hand-designed nonlinear combination of the
  same underlying features. An ML layer wants the raw feature vector, not
  a human's prior best guess at how to combine it.
- **Not Portfolio-compatible.** A portfolio allocator needs to know *which
  kind* of setup is active and its component evidence to size/diversify
  across setup types — not compare opaque scores across symbols.

**Recommendation:** a **named-condition / setup-evaluation model**. A
decision is the output of evaluating a small number of explicit, declared
setups (e.g. `liquidity_sweep_reversal`, `order_block_retest_continuation`,
`smt_divergence_reversal`), each a specific, named combination of Snapshot
fields with no arbitrary numeric weights — e.g.:

> `liquidity_sweep_reversal` fires when: an unswept sell-side Liquidity
> Pool exists within N ATR of price, AND CVD shows `bullish_exhaustion`,
> AND `bos_direction` agrees.

The engine's output records exactly which setup(s) evaluated true, and
*which specific field values* satisfied each condition — not a number.
This is not "scoring with extra steps": there are no weights, every
condition is independently backtestable in isolation, the full reasoning
chain survives into the Trade Journal, and it is the natural substrate a
future ML model would *learn over* (which conditions are true) rather than
be handed a pre-collapsed verdict.

A single numeric field is still legitimate, but only as **descriptive
metadata**, not a judgment: an `evidence_count` (how many independent
Zones/Levels/flags support this setup) is a raw count, in the same spirit
Liquidity Pools already exposes `sources`/`touch_count` — never a weighted
composite pretending to be a probability.

**Honest caveat:** this is an architecture recommendation, not a
profitability claim. A rule-based condition system isn't automatically
better at prediction than a well-tuned score — whether any setup actually
has edge is exactly what the backtest in §5 needs to prove. What changes
is that the system becomes capable of proving or disproving it per-setup,
which the current architecture cannot do at all.

---

## 5. Backtest integration

**Recording every feature.** The full Market Intelligence Snapshot should
be persisted at every bar where a setup evaluates true, plus a periodic
sample (e.g. every N bars) for statistical baseline comparison — not
literally every bar for a multi-year window, to keep storage bounded, but
never only at trade-outcome time. Without the snapshot at the *decision*
instant, no later analysis can ask whether a specific feature actually
predicted anything.

**Explaining every decision.** Each decision record carries: the setup
name, the specific field values that satisfied (or failed) each of its
conditions, and a reference to the Snapshot at that instant. No opaque
aggregate score anywhere in the record.

**Trade Journal evolution.** `JournalEntry` already has a `metadata: dict`
escape hatch and a `score: float | None` field. Recommend: promote
`setup_name: str | None` to a first-class field (query/grouping
convenience — "show me every trade from `liquidity_sweep_reversal`"), keep
the full per-condition evidence in `metadata` (already generic enough, no
schema migration needed), and treat `score` as legacy — present only for
entries still produced by the old frozen pipeline during the A/B
comparison period (see below), never populated by Strategy Engine V2.

**Statistics to collect:**
- Per-setup win rate, expectancy, average R-multiple, **and sample size**
  — many setups will have small sample counts over any single backtest
  window; point estimates without a sample-size caveat are misleading.
- Feature-validity studies decoupled from any trade: of all
  `bearish_divergence` CVD events, what fraction preceded a real reversal
  within N bars? This can be measured directly from recorded snapshots,
  without ever having taken a trade — exactly why replay safety and raw
  feature preservation mattered from Phase 1.1 onward.
- **Confluence value — the single most important validation question this
  whole project has been building toward:** does a setup requiring
  multiple independent Market Intelligence sources agreeing (e.g., pool
  sweep + CVD exhaustion + SMT divergence) outperform a setup requiring
  only one? This directly tests whether the thirteen-module investment was
  worth it, or whether one or two modules would have sufficed.
- Regime-conditioned performance: sliced by `price_correlation` level, by
  active session/kill-zone, by ATR percentile — several Phase 1 modules
  (Correlation Engine, Session Boundaries) exist specifically to make this
  slicing possible.

**Judging whether the new intelligence actually helps.** Run the same
window through both the old frozen scoring pipeline and Strategy Engine
V2, compare win rate/expectancy/Sharpe/max drawdown/trade frequency, and —
critically — report whether any difference is **statistically significant
given the sample size**, not just a point-estimate P&L delta from one
window. This directly serves the "statistically measurable" objective
stated for this phase; a single 30-day backtest showing V2 "made more
money" would be exactly the kind of unproven assumption this project has
consistently avoided elsewhere.

---

## 6. What should be reorganized before Strategy Engine V2 is written

Concrete, scoped findings — nothing here is proposed for immediate action
except where noted:

1. **Delta's `cumulative_delta` should not reach the Snapshot.** CVD
   supersedes it for any anchored/cumulative use. No change to the Delta
   module; the Snapshot Builder simply doesn't surface that field.
2. **`detect_market_structure`'s two-candle heuristic is obsolete** next
   to genuine swing-pivot structure. Flagged for retirement alongside the
   rest of the frozen pipeline once V2 is validated (see point 4) — not
   touched now, since it's still load-bearing for the live frozen path.
3. **Direction vocabulary stays as-is per module** (`bullish`/`bearish` vs.
   `buy_side`/`sell_side`); normalization happens only at the Snapshot
   boundary via the derived `zone_relative_position` field. No renames.
4. **The old `strategy/order_block.py`, `strategy/liquidity.py`,
   `strategy/decision_engine.py`, and `market_structure.py`'s
   scoring-helper functions (`evaluate_bos_quality`,
   `confirm_bos_with_volume`, `confirm_bos_with_open_interest`) become
   retirement candidates — but only after Strategy Engine V2 is built,
   wired, and validated via the A/B comparison in §5.** This was always
   the documented plan (the two Order Block implementations were
   explicitly noted as "intended to coexist until a future Strategy
   Engine redesign migrates over" back in Phase 0) — Phase 2 is that
   redesign, but retiring the old pipeline before V2 is *proven*, not just
   built, would remove the only baseline the A/B comparison needs.
5. **Session Boundaries' full multi-anchor output should not flow into
   the Snapshot directly** — only the thin "active sessions right now +
   previous period high/low" projection described in §3. This is a
   Snapshot-construction decision, not a change to the module.

No Phase 1 module's public interface, tests, or behavior needs to change
for any of this. Every finding above is resolved at the Snapshot-Builder
boundary or deferred until V2 exists to compare against.

---

## Summary

- Thirteen modules collapse into four real families (Zones, Levels, Order
  Flow, Intermarket) plus two cross-cutting concerns (Structure,
  Session/time context) — this is what the Snapshot should be organized
  around, not module-by-module passthrough.
- The Snapshot is a pure, deterministic mapping over existing
  `.snapshot()` outputs, never new computation, and is the *only* thing
  Strategy Engine V2 ever reads.
- The scoring model should be replaced, not tuned — a named-condition
  setup-evaluation model is recommended, preserving full reasoning chains
  and remaining genuinely AI- and Portfolio-compatible instead of only
  claiming to be.
- The backtest pipeline needs to record snapshots at decision time (not
  just outcomes), group results by setup, and report statistical
  significance, not point-estimate P&L — this is what makes "did the
  Market Intelligence layer actually help" an answerable question instead
  of an assumption.
- Nothing in Phase 1 needs to change. The old frozen pipeline stays alive
  as the A/B baseline until Strategy Engine V2 is validated against it.
