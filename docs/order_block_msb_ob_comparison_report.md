# Order Block Comparison — "Market Structure Break & Order Block" (MSB-OB) vs. Current Implementation

Comparison and focused diagnostics only. **No production file modified,
no backtest run, no new data period accessed.** Reuses the completed
correction/lifecycle reports rather than repeating their audits.

---

## 1. Baseline (current, corrected implementation — reused, not re-audited)

- **Structural-break identity** (`docs/module_correction1_structural_break_event_report.md`,
  ACCEPTED): `StructuralBreakEvent`, one-shot per distinct pivot,
  identity = `(direction, pivot_timestamp)` — never a raw
  direction-only `bos` comparison. Close-based, strict inequality,
  fires the instant the break becomes knowable (never backdated to
  the pivot's own earlier candle).
- **Order Block trigger** (`docs/module_correction2_order_block_report.md`
  Phase 2A, ACCEPTED): `structural_break_event is not None` this bar —
  no independent re-derivation of `bos`/swing state inside
  `OrderBlockTracker` at all.
- **Origin-candle search** (Phase 2B, ACCEPTED): bounded to the leg
  between the **broken pivot's own candle** (inclusive,
  `structural_break_event.pivot_timestamp`) and the breaking candle
  (exclusive) — Path (b) of two candidates considered; Path (a) ("most
  recent OPPOSING swing pivot") was implemented, tested, and
  **rejected** for failing this codebase's own canonical reference
  case. No opposite candle in the leg → **no Order Block created**
  (conservative, unchanged failure mode).
- **Swing/pivot detection** (`strategy/market_structure.py`): a fixed
  **3-bar fractal** (`find_swing_pivots`/`find_local_extrema`) —
  scans the full bounded window each call, returns every pivot, no
  parameterized lookback, **no enforced alternation** between highs
  and lows (a swing high and swing low series are found independently).
- **Zone geometry**: primary zone = origin candle's full **wick**
  range (`zone_high=origin.high`, `zone_low=origin.low`); a SEPARATE,
  narrower **mitigation zone** = the same candle's **body**
  (`max(open,close)`/`min(open,close)`), tracked with its own
  independent lifecycle via the identical shared
  `zone_lifecycle.compute_mitigation` function.
- **Touch/mitigation/invalidation**: wick-based, continuous
  `mitigation_pct` in `[0,1]`, edge-triggered `touch_count` (increments
  only on the transition into touching), three states
  (unmitigated/partially/fully). No separate "invalidation" concept —
  full mitigation is the only terminal active-state transition.
- **Breaker Block integration**: a **separate tracker**
  (`BreakerBlockTracker`) subscribing to `OrderBlockTracker`'s own
  `mitigated` list — a fresh object with flipped polarity and its own
  independent touch/mitigation lifecycle, linked to its source only by
  a composite key for provenance. **Policy A** (immediate
  breaker-eligibility the instant full mitigation is reached) is the
  validated, retained production default —
  `docs/order_block_policy_c_validation_report.md`'s own final
  recommendation: **"KEEP POLICY A"** (a bounded, delayed
  "acceptance-pending" alternative, Policy C, was built, TRAIN- and
  VALIDATION-tested, and not promoted).
- **No minimum displacement/size/volume qualification filter** gates
  Order Block formation itself in the current implementation —
  `impulse_strength` is a purely descriptive, post-hoc field (furthest
  favorable excursion since creation, ATR-normalized), never a
  formation gate.
- **Replay safety**: point-in-time by construction — `sync()` accepts
  at most one new candle per call (since `structural_break_event` is a
  snapshot, not a history), rejects rewinds/divergence, bounded
  `structure_lookback` (500) rescan, `max_age_bars` (5000) pruning of
  stale unfilled blocks.
- **Downstream consumers** (confirmed by grep, not assumed): S002
  (`order_block_continuation`), S006 (`breaker_block_reversal`), S005
  (`fair_value_gap_rebalance`, cross-family confluence only), S008
  (research-only, `strategy/research/setups/`).

---

## 2. MSB-OB, examined mechanism by mechanism

**Swing/structural-break detection**: a genuine **ZigZag**, not a
fractal — `to_up`/`to_down` fire when the current bar's high/low is
the extreme of a **rolling `zigzag_len`-bar window** (default 9), and
`trend` only flips when the opposite extreme condition fires. This
**enforces strict alternation** between confirmed highs and lows (a
real structural property ours does not have) and is **coarser by
construction** than a 3-bar fractal — a single-bar wiggle within a
9-bar window is never itself a confirmed pivot.

**Break/"market" confirmation**: gated by a **magnitude threshold**
(`fib_factor`, default 0.33) — the newest confirmed swing low must
undercut the *previous* confirmed swing low by at least
`fib_factor × range` (not merely "any lower low", and not a live,
bar-by-bar "close beyond level" check the way `detect_bos` is) —
confirmation only re-evaluates at zigzag pivot-confirmation moments,
which are themselves delayed by the zigzag's own lookback. This is a
**materially different, coarser, and later** confirmation timing than
our own close-based, every-bar `StructuralBreakEvent`.

**Duplicate-event handling**: `last_l0 == l0 or last_h0 == h0` — a
**value-equality** dedup against the swing-low/high price recorded at
the last flip. See Example 3 below for why this is a real collision
risk our own timestamp-based identity was specifically designed to
avoid.

**Origin-candle search range**: `for i = h1i to l0i[zigzag_len]`
(bullish case) — from the **prior-to-prior** swing high's own bar
index forward to the newest swing low, offset by `zigzag_len`. This
range is **not bounded to the specific broken pivot's own leg** — it
spans potentially several zigzag legs. See Example 2 below.

**Zone geometry**: `high[bu_ob_since]`/`low[bu_ob_since]` — the origin
candle's full **wick** range, matching our own primary zone
convention. **No body-based sub-zone (our "mitigation zone") exists in
MSB-OB at all.**

**"BB"/"MB" (Breaker/Momentum Block)**: a **second, separately-computed
box**, created **simultaneously** with the OB at the same break event,
from a **different, wider search range** (`l1i - zigzag_len to h1i`) —
merely re-labeled "BB" vs. "MB" depending on whether `l0 < l1`. **This
is not the same concept as our Breaker Block** (an Order Block that
later becomes fully mitigated and is reborn with flipped polarity) —
MSB-OB's "BB" is a second zone type built alongside every OB, from an
unrelated lookback window, never triggered by a mitigation event at
all. Flagged as a **naming collision**, not a genuine alternative
architecture to compare against ours on this dimension.

**Touch/mitigation/invalidation**: **close-based**, binary only (no
partial-mitigation percentage) — `close < bottom` (bullish) deletes
the box entirely; `close < top` (still inside) fires an unthrottled
per-bar alert (no first-touch distinction, no cooldown, no
`touch_count`-style state at all).

**A confirmed implementation defect in the supplied script**: the
bearish-OB lifecycle loop uses `if close > top: delete ... ` followed
by a **separate** `if close > bottom: alert() else: extend()` (not
`else if`, unlike the bullish loop's own `if/else if/else`) — since
`top > bottom` always, `close > top` implies `close > bottom` is also
true, so an invalidating bar **also fires the "in zone" alert in the
same pass**, and `f_delete_box` (`array.shift`, removing the array's
**front** element) is called while iterating `for bear_ob in
be_ob_boxes` **without tracking which element is actually being
visited** — with more than one active bearish OB, this can delete the
wrong box or skip/double-process another mid-iteration. This is a
demonstrated code defect in the reference script, not a design choice
to weigh — not comparable to any of our own conventions.

---

## 3. Comparisons using identical candle sequences

**Example 1 — swing-detection sensitivity (directly relevant to the
already-registered, not-yet-tested `module_decision_register.md` B6
hypothesis)**

Bars 1–9 (a mostly-clean uptrend with one 1-bar pullback at bar 4):
`H/L` = (100/98), (102/99), (104/101), **(103/100)**, (106/102),
(108/104), (110/105), (112/107), (114/109).

- **Ours**: bar 4's low (100) is below bar 3's (101) and bar 5's
  (102) — a genuine 3-bar fractal trough. `find_swing_pivots` records
  it as a swing low; it becomes `previous_swing_low` for any
  `detect_bos`/CHoCH check until superseded.
- **MSB-OB** (`zigzag_len=9`): bar 1's own low (98) is still lower
  than bar 4's (100), so bar 4 is never the 9-bar lowest — `to_down`
  never fires here; the zigzag stays in its existing uptrend leg,
  never registering this pullback as a turning point at all.

**Confirmed, concrete demonstration of the B6 concern**: our
fast, fixed-resolution fractal registers materially more, smaller-scale
swing points on the identical sequence than a parameterized-lookback
zigzag would — exactly the "single fast resolution produces more
noise/churn" hypothesis B6 already named but never tested. **This
comparison does not resolve B6 — it sharpens the concrete alternative
to test.**

**Example 2 — origin-search range (the class of defect our own A2
correction fixed)**

A prior swing high (h1) at bar 0, three bearish candles (bars 1–3,
unrelated consolidation predating the actual impulse), then a later,
distinct swing high forms and gets broken at bar 20 by an
uninterrupted bullish run from bar 10 onward (no bearish candle
anywhere in [10, 20)).

- **Ours**: leg = [pivot-candle-at-bar-10, bar 20) — scanned for a
  bearish candle, finds none → **no Order Block created** (the
  conservative, already-established behavior).
- **MSB-OB**: origin range `h1i (bar 0) to l0i[zigzag_len]` — spans
  back through bars 1–3, the unrelated consolidation — finds and
  selects bar 3 (the last bearish candle in that wide range) as the
  origin, **reusing economically unrelated prior structure** for a
  break that occurred 17+ bars later. This is precisely the failure
  mode `docs/module_correction2_order_block_report.md`'s own Phase 2B
  failing-characterization test was built to demonstrate and fix.

**Example 3 — duplicate-event dedup: value equality vs. timestamp
identity**

Two structurally distinct swing lows, confirmed at different times,
that happen to share the identical price (e.g., both print exactly
$100.00 — plausible on any instrument with round-number clustering).

- **Ours**: identity = `(direction, pivot_timestamp)` — two different
  timestamps → two distinct events, both correctly fire, two Order
  Blocks created.
- **MSB-OB**: `last_l0 == l0` (value-only comparison) — the second
  break's own `l0` equals the value recorded at the first break →
  **the genuinely new, distinct break is silently suppressed.** This
  is exactly the collision class `docs/module_correction1_structural_break_event_report.md`'s
  own design rationale explicitly reasoned about and chose
  timestamp-based identity specifically to avoid.

---

## 4. Comparison table and recommendations

| Dimension | Ours (current) | MSB-OB | Classification | Recommendation |
|---|---|---|---|---|
| Swing detection | Fixed 3-bar fractal, no alternation enforced | Parameterized N-bar ZigZag, strict alternation | Confirmed sensitivity/coverage difference (Example 1) | **DEFER FOR RESEARCH** — a genuinely different, not-yet-tested resolution; directly operationalizes the already-registered B6 hypothesis, not a new one |
| Break confirmation | Close-based, every bar, no magnitude requirement | Magnitude-gated (`fib_factor`), only re-evaluated at pivot-confirmation | Intentional semantic difference + a real, new, not-previously-registered hypothesis (distinct from B6 — this is about break MAGNITUDE, not swing RESOLUTION) | **DEFER FOR RESEARCH** — worth its own future controlled comparison; `fib_factor` would need to be a fixed, disclosed constant, not fit to any outcome |
| Duplicate-event handling | Timestamp identity, collision-proof by construction | Value equality, demonstrated collision risk (Example 3) | **Confirmed correctness weakness in the reference code**, not a defect in ours | **RETAIN** ours; nothing to adopt here |
| Origin-search range | Leg-bounded to the specific broken pivot (Path b, already tested and chosen over the wider alternative) | Wide, multi-leg range (Example 2) | **Confirmed defect-class match** — MSB-OB's range is the same failure mode our own A2 correction was built to eliminate | **RETAIN** ours; **REJECT** adopting MSB-OB's range |
| Zone geometry (primary) | Full wick | Full wick | Same | **RETAIN** — no difference |
| Mitigation sub-zone (body) | Yes, independent lifecycle | None | Existing capability we already have that MSB-OB lacks | **RETAIN** — already superior, nothing to adopt |
| Mitigation rule | Wick-based, continuous % | Close-based, binary | Intentional semantic difference, **directly relevant to the already-registered, untested B1 hypothesis** (`module_decision_register.md`) — not a new question | **DEFER FOR RESEARCH** — reinforces B1's priority, does not itself authorize testing it now |
| Touch/retest signal | Edge-triggered `touch_count` | Unthrottled per-bar alert, no first-touch distinction | Confirmed our design is more information-preserving (no repeat-fire noise) | **RETAIN** — nothing to adopt |
| Breaker Block | Mitigation-triggered polarity flip, separate tracker, Policy A validated (KEEP POLICY A) | Not equivalent — a second, simultaneously-created zone from an unrelated wider window, naming collision only | **Not a genuine alternative to compare** on this dimension | **RETAIN** ours; MSB-OB's "BB/MB" is out of scope as a Breaker Block comparison |
| Bearish-OB lifecycle loop (array shift while iterating, asymmetric if/elif) | N/A (no equivalent construct) | **Confirmed implementation defect** | Demonstrated code defect, not a design choice | **REJECT** — not adoptable in any form |
| Minimum size/displacement filter on origin candle | None | None | Same (neither system gates formation on size) | **RETAIN** — no difference to act on |

---

## 5. Practical recommendation

**No change to the current implementation is justified by this
comparison alone.** Every genuine mechanism difference found (swing
resolution, break-confirmation magnitude, wick-vs-close mitigation) is
either **already a registered, not-yet-tested hypothesis**
(B1, B6 — this comparison sharpens the concrete alternative worth
testing, it does not newly justify testing it) or a **freshly
identified, defensible future hypothesis** (magnitude-gated break
confirmation) requiring its own controlled experiment before any
adoption. Every place MSB-OB's own mechanism was compared against
something we already deliberately changed (origin-search range,
event-identity dedup), **our current implementation is the
demonstrably more correct one**, confirmed by direct reproduction of
the exact failure modes our own correction reports already fixed.

**Affected consumers if any DEFER-FOR-RESEARCH item is later
pursued**: S002 (`order_block_continuation`), S006
(`breaker_block_reversal`), S008 (research-only), and transitively
S005/S001/S007 via the same first-fired-wins arbitration effect
already measured and disclosed in
`docs/module_correction2_order_block_report.md`'s own Phase 2A/2B
comparison artifacts — any future swing-resolution or break-magnitude
change would need the identical before/after opened-trade comparison
methodology already established there, not a new one.

**Verification requirements for any future DEFER-FOR-RESEARCH work**
(not authorized by this comparison): a frozen protocol per this
project's standing discipline; the alternative implemented as a
parallel, disabled-by-default research module (matching the FVG
inversion sprint's own precedent), never replacing
`market_structure.py`/`order_block.py` in place; a byte-identical
control-equivalence proof for every existing setup before any outcome
is computed; TRAIN-only evaluation.

**Bounded next task, if this direction is pursued**: a single,
narrowly-scoped research sprint building an alternative,
parameterized-lookback swing detector (operationalizing B6) as a
research-only module alongside the existing fractal detector — signal-
frequency check first (matching this project's own established
S007/S010 lesson: verify it fires often enough to test before
investing in a full backtest) — **not started here**.

**Keeping the current implementation exactly as-is remains a fully
valid, and on the evidence gathered here, the currently best-supported
outcome.**

---

## 6. Explicit confirmations

No production file was modified. No new SOL/BTC data period was
accessed. No backtest was run — every synthetic example in Section 3
is a hand-constructed, illustrative candle sequence. All prior
uncommitted work (the SOL Multi-Module Setup Discovery sprint, the
FVG/IFVG design review and implementation sprint, and everything
before them) remains untouched and uncommitted.
