# FVG/IFVG Incremental Comparison (Nephew_Sam_) + Initial-Stop Design Hypothesis

Comparison, focused diagnostics, and design only. **No production file
modified, no backtest run, no new data period accessed.**

---

## ADDENDUM (completes this report — read first)

Two things below are corrected or completed relative to the original
document (Sections 0–6 following this addendum, preserved unedited for
the record):

1. **Section 2 is now completed** using an explicit
   observed/inferred/unknown taxonomy, per the correct instruction
   that obtaining the Nephew_Sam_ source is not a prerequisite for
   finishing this task — only for verifying claims beyond what the
   screenshots themselves support. See **Addendum §A**.
2. **Section 4a's classification is corrected.** The original text
   called the S001 sweep-extreme stop a fix for a stop that "can sit
   inside the very wick that justified entry" — worded to imply the
   current pool-boundary stop was somehow deficient. That framing was
   wrong, and is retracted below, not merely softened. See
   **Addendum §B**, which also supplies the exact code trace proving
   the sweep-event identity claim the original report only asserted
   from recency.

Section 5's "one recommended next experiment" is replaced by
**Addendum §C**.

---

### Addendum §A — Behavioral comparison, completed

**Observed** (stated or shown directly in the screenshots, not
inferred):
- The indicator's title is "FVG/iFVG (Nephew_Sam_)."
- Five independent timeframe slots exist, each with its own FVG/iFVG
  label pair; "Chart" and "15 minute" are enabled in the settings
  screenshot.
- "Wait for candle close to identify FVGs?" is present as a toggle and
  is **unchecked** in the captured configuration.
- "Hide FVGs lower than enabled timeframes?" is present and **checked**
  — the option's own name states a cross-timeframe suppression rule
  exists; this is observed (the rule is named), not inferred.
- "Filled FVG Type" is a dropdown currently set to "Close"; only this
  one fill-type control is visible in the captured screenshots.
- "Max bars back to find FVGs?" = 300.
- "Delete Boxes after fill?" is checked; "Extend Boxes?" is unchecked;
  "Length of Boxes" = 20.
- FVG and IFVG have independently configurable bullish/bearish
  box and border colors.
- In the specific captured configuration, "Show iFVG" is unchecked,
  and neither chart screenshot shows an iFVG rendering.

**Inferred** (a specific, falsifiable behavioral rule that the
observations above reasonably support, stated as a hypothesis, not a
fact) — for each, the **targeted additional capture that would
distinguish it from a competing explanation**, obtainable directly in
TradingView with no source code:

| # | Inferred rule | Competing explanation | Distinguishing capture |
|---|---|---|---|
| 1 | With "wait for candle close" off, a zone can be drawn from the still-forming candle's own live high/low, and its boundary can still change before that candle closes | The toggle only changes **when** a box first appears (early preview) but its final geometry never differs from the close-based result | Screenshot the same still-forming candle's region twice — once mid-bar, once just before close — with the toggle off; compare the drawn zone's boundaries and presence between the two captures. If either differs for the same, not-yet-closed candle, repainting is directly demonstrated with no source needed |
| 2 | "Hide FVGs lower than enabled timeframes" is a pure **display** filter — the suppressed lower-TF zones still exist and update internally, just unrendered | Suppression also stops the lower-TF zone from being tracked/updated at all once a higher TF is enabled | Uncheck the option on the same chart/config and see whether previously-invisible lower-TF boxes reappear already at their full, correctly-aged geometry (supports "display-only") vs. appearing freshly formed only from that moment on (supports "not tracked while hidden") |
| 3 | "Delete Boxes after fill" is cosmetic — the underlying record survives and can still later render as an iFVG | Deletion removes the zone from all further consideration; a deleted FVG can never later show an iFVG box | With "Delete Boxes after fill" on and "Show iFVG" on, locate a historical fill-then-invert sequence; if an iFVG box appears for a zone whose FVG box was already deleted, internal survival is proven directly |
| 4 | The single visible "Filled FVG Type" (Close) setting governs both fill **and** any inversion confirmation — one unified rule, unlike our own deliberately split wick-fill/close-inversion design | A separate, not-yet-captured inversion-confirmation control exists further down the settings panel (which scrolls, and was not fully captured) | Scroll and screenshot the complete Inputs and Style tabs in full; check specifically for any "iFVG"-scoped confirmation-type control distinct from "Filled FVG Type" |

**Unknown** (screenshots provide no basis to even form a hypothesis):
exact zone-formation geometry (candle count, wick vs. body, any
minimum-size filter); deduplication/identity mechanism for overlapping
or repeated zones; the exact retest rule and its actionable timing;
whether multiple simultaneously-enabled timeframes interact beyond the
named display-hiding rule (row 2) — e.g., whether a lower-TF zone can
be invalidated by higher-TF price action. None of these are guessed at
below.

**Compared against our implemented module — without claiming to
reconstruct Nephew_Sam_'s own algorithm**:

| Property | Ours (verified in code) | Nephew_Sam_ (observed/inferred only) |
|---|---|---|
| Candle-close wait for formation | Always — structural (the tracker only ever sees already-closed candles) | Optionally off (observed); consequence inferred, not confirmed (row 1) |
| Fill rule | Wick, fixed, no runtime toggle | Configurable dropdown, "Close" selected (observed); whether it also governs inversion is unknown (row 4) |
| Inversion rule | Close, fixed, deliberately different from fill | Unknown whether inversion exists as its own rule or reuses "Filled FVG Type" |
| Multiple timeframes | One tracker instance per coordinator run | Five simultaneous, independently-labeled slots (observed) — a real capability gap on our side, unchanged from the prior version of this report |
| Post-fill record survival | Same object continues (Path B, verified in our own tests) | Unknown (row 3) — plausible either way from what's observable |
| Cross-zone/cross-TF interaction | None | A named display-suppression rule exists (row 2); whether it is purely cosmetic is unresolved |

No rule above is asserted as Nephew_Sam_'s actual algorithm — each is
labeled by exactly the evidence tier it belongs to, and the table's
right column is explicitly comparative to what we can support, not a
claim about what the reference indicator "really does."

---

### Addendum §B — Initial-stop reclassification (correction, not a refinement)

**The original Section 4a was wrong to imply a correctness gap.**
Restated precisely:

**Entry timing, re-examined**: S001 fires and enters on the exact bar
`_find_fresh_sweep` matches — the sweep candle's own **close**, which
by the sweep's own definition (`candle.close > zone_low` for the
sell-side case) is **already back above the pool boundary**. This
means, at the moment of entry, the sweep's own wick extreme is already
historical, already-reclaimed, already-survived price action **within
the same bar as entry** — not an untested boundary the position is
still exposed to. Placing the stop at the pool boundary rather than
beyond the wick does not violate anything the trade has already
survived; it defines a **different, and equally coherent, invalidation
question**: "does price hold above the level it just reclaimed?"
versus "does price hold above the deepest point it wicked to?" Neither
is entailed by the other, and preferring one is a claim about what
predicts continuation, not a claim about correctness.

**The current implementation matches its own documented contract
exactly** — `strategy/strategy_engine_v2_backtest_adapter.py`'s own
docstring states the stop is placed "Beyond the swept Liquidity Pool's
own zone edge - the price level that would invalidate the setup's
thesis (if price re-enters/exceeds the pool's zone, the 'reversal'
reading was wrong)." This is the deliberately chosen, already-stated
design. No implementation defect and no violated contract were
demonstrated in the original Section 4a, and none is demonstrated now.
**Reclassified: the sweep-extreme stop is a strategy hypothesis,
competing against an intentional, already-documented convention — not
a fix.**

**Sweep-event identity, now proven by direct code trace (not
recency)**, per the explicit instruction not to substitute recency for
identity:

1. `LiquidityPool.check_sweep(candle, timestamp_key, atr)`
   (`strategy/features/liquidity_pool.py:230`) tests the sweep
   condition against **the single `candle` argument it is called
   with**, and on the same line sets
   `self.swept_timestamp = candle[timestamp_key]` (line 255) — the
   identical candle, no lag, no separate confirmation step.
2. `LiquidityPoolTracker._check_sweeps(candle)` (line 435) calls
   `pool.check_sweep(candle, ...)` with **the one new candle being
   ingested this step** — the same candle `_ingest()` is currently
   processing, never a batch.
3. `market_intelligence_snapshot.py`'s zone builder maps the "swept"
   list with `resolved_at_field="swept_timestamp"` (line 333) — so
   `zone.resolved_at` **is** `swept_timestamp` from step 1, verbatim.
4. `LiquiditySweepReversalSetup._find_fresh_sweep` requires
   `zone.resolved_at == snapshot.timestamp`, and
   `strategy_engine_v2_backtest_adapter.py` sets
   `snapshot.timestamp = candles_15m[-1][timestamp_key]` — the latest
   15m candle in the coordinator's own growing history at this exact
   decision point.

Chaining 1→4: whenever `_find_fresh_sweep` returns a match, the
matched pool's own `swept_timestamp` is **provably** the timestamp of
`candles_15m[-1]` — because both sides of the equality in step 4
resolve, independently, to the identity established in steps 1–3. This
is a **proof**, not an inference from "the sweep is usually recent":
**the latest 15m candle is not merely likely to be the sweep event, it
is definitionally the same candle whenever the setup fires at all.**
Consequently, `candles_15m[-1]["low"]`/`["high"]` — already available
in the adapter's own `market_snapshot` parameter, no new plumbing — is
exactly the sweep extreme, using only information the setup already
had at the moment it decided to fire.

**What this does and does not settle**: the identity trace above
removes any doubt about *which* candle the sweep-extreme value would
come from, if this hypothesis is ever tested. It does **not** make the
hypothesis itself more or less likely to improve S001 — that remains
strictly an empirical question, per Addendum §C. Risk budgeting
(`create_risk_based_trade_setup`, `risk_percent`, `MIN_RISK_PERCENT`
floor) and the initial-stop/trailing-stop separation from the original
Section 4d stand unchanged — both were already stated correctly and
require no correction. Section 4b (FVG continuation) and Section 4c
(IFVG reversal design) also stand: neither claimed a correctness
defect, only proposed a boundary, and both remain labeled as
hypotheses.

---

### Addendum §C — One recommended bounded next experiment

**Strongest actionable FVG/IFVG hypothesis**: whether **inversion +
retest** (the extension already implemented and disabled by default,
`docs/fvg_ifvg_implementation_sprint_report.md`) identifies a
genuinely different, non-redundant opportunity population from S005's
own existing fill-based continuation thesis — this is the only FVG/IFVG
hypothesis in this whole review series that is already fully
*implemented* (not merely designed), making it the cheapest one to
actually evaluate next.

- **Baseline**: S005 exactly as it exists today (`fair_value_gap_rebalance.py`,
  unchanged) — a continuation thesis on a partially-filled, still-active
  gap.
- **Proposed difference**: a new, separate, research-only setup (not a
  modification to S005) requiring `is_inverted` and, optionally,
  `retest_confirmed_this_bar` — a **reversal** thesis on the opposite
  side of the same zone family, using fields that already exist on the
  tracker today.
- **Required integration** (none of this exists yet, and none of it is
  built by this addendum): `MarketIntelligenceCoordinator` would need
  to construct its `FairValueGapTracker` with `track_inversions=True`
  (optionally `track_retests=True`); `market_intelligence_snapshot.py`'s
  `_map_zones` would need to additionally read the tracker's
  `"inverted"` list (and `"failed"`, for completeness) and expose it
  as its own zone status or kind — done carefully enough that S005's
  own `kind=="fvg" and status=="active"` filter still cannot see them,
  preserving the structural non-interference already proven.
- **Evidence needed to evaluate it** (a future, separately-authorized
  sprint, not this one): a frozen protocol; a signal-frequency check
  on SOL TRAIN first (matching this project's own S007/S010-risk
  lesson — confirm it fires enough to be worth a full backtest before
  investing in one); then a standalone TRAIN backtest reporting
  expectancy in R, net P&L, drawdown, and cost sensitivity — not merely
  trade count or win rate, and not compared against S005's own
  (already known to be weak, RESEARCH ARCHIVE) numbers as if beating a
  weak baseline were itself evidence of an edge.

**The screenshot examples in Addendum §A are development observations
about a third-party indicator's own UI and display behavior — they are
not, and are not offered as, evidence of trading value for anything in
this codebase.**

---

## 0. A necessary correction before anything else

What was supplied this turn is **four screenshots** — a chart with the
indicator plotted, and two settings panels — **not Pine Script source
code**. Section 2 is explicit throughout about which findings come
from directly reading code (as with LuxAlgo/ChartPrime, the prior
comparison) versus what is *inferred* from a compiled indicator's UI
and chart output. Per this project's own standing discipline, an
inference from a screenshot is disclosed as exactly that, never
presented as a verified fact.

---

## 1. Baseline (reused, not re-audited)

From `docs/fvg_ifvg_module_logic_review.md` and
`docs/fvg_ifvg_implementation_sprint_report.md`:

- Wick-based fill (unchanged, primary) is separated from a
  **close-based, strictly-stronger** inversion confirmation on the
  **same object** — identity, direction, boundaries, and full
  transition history preserved on one `FairValueGap` record.
- Bounded retention: `inversion_watch_bars` (default 500) for
  not-yet-inverted candidates; overall count bounded by the
  pre-existing `max_tracked_filled` FIFO.
- Retest is a **separate, independently-optional** flag
  (`track_retests`), never gating inversion itself; one-shot-per-bar
  signal with a cooldown.
- Both flags default `False`; `snapshot()`'s returned keys are
  byte-identical to the pre-extension shape when unused; proven on
  real SOL TRAIN data (2024-02) that the legacy `active`/`filled`
  population is unaffected either way.
- **`MarketIntelligenceCoordinator` and `market_intelligence_snapshot.py`
  do not wire up or read the new fields at all** — inverted zones are
  structurally invisible to every current setup (including S005)
  regardless of the flag. This remains true today; nothing in this
  turn changes it.
- **Order Block decision preserved**: Policy A (immediate
  breaker-eligibility) remains the validated production default
  (`docs/order_block_policy_c_validation_report.md`, "KEEP POLICY A");
  the just-completed MSB-OB comparison changed nothing.

---

## 2. The supplied reference, examined precisely

**Name/version, confirmed directly from the screenshot**: the
indicator's own title bar reads **"FVG/iFVG (Nephew_Sam_)"** — yes,
this is the Nephew_Sam_ indicator, a **different author and different
codebase** from the previously-reviewed LuxAlgo FVG and ChartPrime
IFVG scripts (which were compared against actual source in the prior
sprint). Nothing here should be assumed to share their exact
algorithm merely because the concept name overlaps.

### What is directly confirmed from the settings panel (not inferred)

- **Simultaneous multi-timeframe detection/display**: 5 independently
  toggleable timeframe slots (Chart, 15m, 1h, 4h, 1D), each with its
  own FVG **and** iFVG label pair ("1h FVG"/"1h iFVG", etc.) — a
  capability our tracker does not have today (one instance per
  timeframe, never multiple simultaneously in one coordinator run).
- **"Wait for candle close to identify FVGs?" — shown UNCHECKED.**
  This is the single most consequential, directly-observable setting
  for a causal-correctness review: if formation does not wait for the
  confirming candle to close, the indicator is identifying gaps from
  the **currently-forming candle's own intrabar high/low** — a
  textbook repainting pattern (the zone can appear, then silently
  disappear or move, as the still-open candle's own extremes change
  before it closes). This is **directly observable from the toggle's
  existence and its shown state**, not an assumption about hidden
  logic — but I cannot confirm the *exact* mechanism (whether it
  merely previews and then finalizes, or genuinely emits an
  actionable-looking signal that later retracts) without source.
  **This is the single most important thing to verify if the actual
  script becomes available.**
- **"Filled FVG Type: Close"** — a dropdown currently set to
  close-based fill/mitigation confirmation. Directly comparable to
  ChartPrime's own close-based rule (already compared) and to our own
  **inversion** confirmation (also close-based) — but note this
  dropdown's mere existence implies at least one other option (almost
  certainly "Wick") is selectable, meaning **this single indicator can
  reproduce either convention** depending on configuration — a
  capability neither LuxAlgo, ChartPrime, nor our own tracker offers
  as a runtime toggle (ours is a fixed code-level choice, deliberately,
  per the already-registered B1 hypothesis).
- **"Max bars back to find FVGs?: 300"** — a bounded-retention setting,
  directly comparable to our `max_age_bars` (5000)/ChartPrime's
  `longevity` (500). A parameter-value difference only, not evidence
  either default is more correct.
- **"Delete Boxes after fill?" — checked.** Visually removes a filled
  box. Whether this ALSO discards the underlying record (making later
  inversion impossible to track, the same question our own design
  explicitly solved for) or is purely cosmetic (state retained
  internally, only the drawing removed) **cannot be determined from a
  screenshot** — this is exactly the kind of "chart appearance vs.
  what was actually tracked" distinction the task asks to separate,
  and here it is genuinely unresolvable without source.
- **"Extend Boxes?" unchecked, "Length of Boxes: 20"** — a fixed-width
  visual box, cosmetic only (comparable to ChartPrime's own
  cosmetic-only box-shrink-on-expiry behavior, already reviewed and
  not adopted).
- **Separate FVG vs. IFVG color/border settings** — confirms FVG and
  IFVG are visually distinguished, consistent with (but not proof of)
  either architecture: a shared-identity in-place extension (our own
  Path B) or a separate-object design (Breaker Block's Path A). The
  UI alone cannot distinguish these, and this is precisely the
  architectural question this whole review series has focused on.

### What the chart screenshots show (and their real limit)

Both chart screenshots show FVG boxes/labels on what is stated to be a
SOLUSDT chart, at multiple zoom levels, consistent with a working FVG
detector. **"Show iFVG" was unchecked in this specific configuration**
— neither chart screenshot demonstrates the inversion/iFVG behavior at
all, so no comparison of actionable inversion or retest timing is
possible from what was supplied. A chart image can show that zones
were *drawn* at certain levels; it cannot show **when** a zone became
actionable relative to the candle that confirmed it, whether the
indicator's own displayed history has since been repainted, or what a
strategy reading this indicator's live output (not its historical
chart render) would actually have received at each bar. This is
exactly the "chart appearance vs. executable signal" distinction the
task asks to preserve, and it is the reason a screenshot cannot settle
it either way.

### Bottom line on the comparison itself

**This comparison is incomplete, and is disclosed as incomplete
rather than papered over.** The formation geometry, exact inversion
confirmation rule, deduplication mechanism, and actionable retest
timing cannot be verified without the actual Pine source — attempting
synthetic candle-sequence comparisons (as was done for LuxAlgo/
ChartPrime, where source was available) against inferred behavior
would misrepresent inference as verification, which this project's
standing discipline explicitly rules out. **If the Nephew_Sam_ source
becomes available, re-run the identical methodology already
established** (Section 5b/5c of `docs/fvg_ifvg_module_logic_review.md`)
against it directly.

---

## 3. Adoption assessment (only for what is actually confirmed)

| Item | Confirmed how | Recommendation | Reason |
|---|---|---|---|
| Simultaneous multi-timeframe FVG/iFVG detection | Settings panel, directly | **DEFER FOR RESEARCH** | A genuine capability gap (today: one timeframe per coordinator instance) — plausibly useful (a 1h FVG as context for a 15m entry), but adds real architectural surface (coordinator would need to own N trackers) and no evidence yet that multi-TF confluence adds trading value here |
| Runtime-selectable Close/Wick fill type | Settings panel, directly | **REJECT for now** | Directly duplicates the already-registered, not-yet-tested B1 hypothesis (wick vs. close mitigation) — a runtime toggle is a UI convenience, not new information; testing the underlying question is already queued, a toggle doesn't change its priority |
| "Wait for candle close" = off (default shown) | Settings panel, directly; exact consequence not verifiable | **Flag only — no action possible without source** | This is the single highest-value verification target if source becomes available; our own tracker already waits for close by construction (no toggle needed, no repainting possible) |
| "Delete boxes after fill" — does it also discard the underlying record? | Not verifiable from UI | **Cannot classify** | Requires source |
| Exact formation geometry, inversion rule, dedup, retest timing | Not verifiable from UI | **Cannot classify** | Requires source |

**No change to the current FVG/IFVG implementation is justified by
this turn's comparison** — not because nothing looks interesting, but
because what looks interesting (the close-candle-wait toggle
especially) cannot be acted on without the actual code, and everything
that IS verifiable either duplicates an already-queued hypothesis (B1)
or is a UI capability gap worth a future, separately-scoped look
(multi-timeframe), not an immediate change.

---

## 4. Initial-stop design hypothesis (fully self-contained — does not depend on the missing reference code)

### 4a. Liquidity Sweep Reversal (S001) — sweep extreme vs. pool boundary

**Current production stop** (`strategy/strategy_engine_v2_backtest_adapter.py`,
verified by direct reading): the swept Liquidity Pool's own **static
zone edge** — `zone_low` for LONG (sell-side pool swept),
`zone_high` for SHORT — offset by the existing `STOP_BUFFER_PCT`.

**The distinction this hypothesis turns on, stated precisely**:
- **Pool boundary** (`zone.zone_low`/`zone.zone_high`): the resting-
  order zone's own edge, fixed **before** the sweep occurred.
- **Sweep extreme**: the actual low (LONG case) / high (SHORT case) of
  the **specific candle whose wick-beyond-then-close-back is what
  confirmed the sweep** — by `LiquiditySweepReversalSetup._find_fresh_sweep`'s
  own condition, this is `zone.resolved_at == snapshot.timestamp`, i.e.
  the sweep resolves on the **same 15m candle** already available as
  `market_snapshot[symbol]["15m"][-1]` in the adapter — no new
  plumbing needed to read it, though it is a different object from the
  1-minute `current_candle` the adapter's `trade_setup_callback`
  otherwise uses for entry price (a real, concrete implementation
  detail to get right, not a new architectural dependency).
- **A verified geometric fact, not a hypothesis**: by the sweep's own
  definition (wicks beyond the pool boundary, then closes back), the
  sweep extreme is **always at least as far** from the pool boundary
  in the adverse direction (`sweep_low <= zone_low` for the LONG case).
  **This proposal can only ever widen the stop, never tighten it** —
  it is not a risk-reduction idea, it is a correctness idea: the
  current stop can sit *inside* the very wick that justified entry,
  meaning a retest that never actually exceeds the sweep's own extreme
  could still stop the trade out on a technicality the entry signal's
  own evidence already survived once.

**What actually falsifies the thesis, stated without assuming
intent**: the setup's claim is "resting orders here were triggered and
the move reversed" — a later close/wick that **exceeds the sweep
candle's own extreme** directly means price revisited that level and
went **further** than the event that supposedly exhausted it,
independent of any belief about who was defending the level or why.
This is a structural falsification condition, not an assumption that
"smart money is defending this price."

**Design**: `stop = sweep_extreme * (1 - STOP_BUFFER_PCT)` (LONG) /
`sweep_extreme * (1 + STOP_BUFFER_PCT)` (SHORT), using the existing
buffer constant, replacing the pool-boundary anchor. Take-profit
convention, position-sizing convention (`create_risk_based_trade_setup`,
`risk_percent`), and `MIN_RISK_PERCENT` floor all **unchanged** — a
wider stop simply yields a smaller position at the same fractional
risk, which is the position-sizing mechanism already in place, not a
new one.

### 4b. FVG continuation (S005) — does the sweep-extreme idea even apply?

**No — and stating precisely why is itself the deliverable here.**
S005's own required condition (`price_rebalancing_unfilled_gap`) never
reads a Liquidity Pool sweep at all — there is no "causally identified
sweep" belonging to this setup's thesis, per the explicit instruction
to apply the sweep-based anchor **only** where one genuinely exists.
S005's own current stop (the gap's far zone edge — the point at which
the gap becomes fully filled, falsifying "unfilled interest remains")
is **already the causally correct invalidation boundary for FVG's own
thesis** — unlike the sweep case, entry happens **after** price is
already inside the gap (`partially_filled` + `inside_price` both
required), so the stop (the far edge) is a level price has **not yet
crossed**, not a boundary the entry candle itself may have already
breached. There is no analogous "the confirming candle already
violated the naive stop" problem here. **Recommendation: no change to
S005's stop logic.**

### 4c. IFVG reversal (hypothetical future setup — not yet built) — its own invalidation, and where a sweep-style anchor DOES generalize

No IFVG-consuming setup exists yet (§1). Designing its invalidation
logic in the same spirit as 4a/4b:

- **The natural boundary**: an inverted gap's own **failure**
  condition (already implemented, §1) is a close beyond the zone's
  **original far edge** — `zone_high` for a bullish-original,
  now-inverted-to-resistance gap (SHORT entry), `zone_low` for the
  mirror. This is not a new rule to invent — **it is already exactly
  the same boundary the tracker itself uses to mark `is_failed`** —
  meaning a future setup that stops a SHORT at `zone_high` would be
  stopped out **exactly when, and only when, the tracker's own
  lifecycle would independently mark the thesis failed.** Stop
  placement and thesis invalidation are the same event by construction
  if this boundary is used.
- **Where the sweep-extreme idea genuinely generalizes**: the retest
  signal (§1) fires when `previous_candle["high"] >= zone_low` (the
  bullish-original case) — the bar that actually **tagged** the level
  may have wicked slightly beyond `zone_low` without closing beyond
  it, structurally the same shape as a Liquidity Pool sweep's own
  wick-beyond-then-reject pattern, just against a different zone type.
  **The retest-confirming bar's own high is the IFVG-reversal
  equivalent of "the sweep candle's own extreme"** — a causally
  identified, entry-thesis-specific excursion, not an arbitrary choice.
  Anchoring the stop to `max(zone_low, previous_candle["high"])` (with
  the same buffer) rather than `zone_low` alone applies the *same
  underlying principle* as 4a (never let the stop sit inside the wick
  that the entry signal's own evidence already survived), to a
  genuinely different setup and zone type — not a repeat of the same
  tested hypothesis under a new name, since the object (an FVG's own
  inversion boundary) and the confirming event (a 2-bar rejection, not
  a pool sweep) are both structurally distinct from S001's.

### 4d. Shared design constraints (apply to all three)

- **R0 defined consistently**: `R0 = |entry_price - stop_loss| * quantity`,
  from the actual entry/stop/quantity the trade was opened with —
  unchanged from every prior sprint's own convention this session.
- **Position sizing unchanged**: `create_risk_based_trade_setup`,
  `risk_percent`, `MIN_RISK_PERCENT` floor — a wider stop only ever
  changes quantity, never the fractional risk budget.
- **Initial stop vs. trailing kept strictly separate**: none of this
  interacts with Progressive Stop Policy D, which remains frozen at
  INSUFFICIENT EVIDENCE. This design changes only where the stop
  starts, never how (or whether) it moves afterward.
- **Epistemic caution, stated directly**: none of 4a–4c assumes a
  sweep or FVG "proves" defended or accumulating positioning — every
  invalidation boundary above is justified purely by what the setup's
  own entry evidence would need to survive a second time, not by a
  claim about who is trading at that level or why.

### 4e. On the two supplied reference links

- The arXiv paper (Cont, Kukanov, Stoikov, "The Price Impact of Order
  Book Events," fetched directly) is **not** a stop-loss or position-
  sizing methodology paper — it establishes that short-term price
  impact is driven by order-flow imbalance relative to order-book
  depth (`ΔP = β·OFI`), with depth-driven, session-time-varying impact
  (higher at open, lower at close). Relevance here is indirect at
  best: it supports the general, already-well-known idea that
  execution/impact conditions vary by session, not a specific claim
  about where an initial stop belongs. Not used to justify any
  specific number above.
- The CME position-sizing page could not be fetched in this session
  (two attempts, both timed out) — not read, and nothing above is
  attributed to it. The design in 4a–4c instead rests entirely on this
  project's own already-implemented, fixed-fractional-risk sizing
  convention (`create_risk_based_trade_setup`), which is the standard,
  independently well-established practice the page's own title
  suggests it teaches — stated as a reasonable inference from the
  title alone, not as a verified citation.

---

## 5. Decision report

### Comparison table (Section 3, repeated for the deliverable)

See Section 3 above — no row currently supports an immediate change;
two rows (multi-timeframe detection, close-candle-wait mechanism) are
flagged as high-value future verification/research targets.

### Strongest justified change from this entire turn

**The S001 sweep-extreme stop (§4a) is the strongest, most concretely
justified proposal in this document** — it rests on a verified
geometric fact (the sweep extreme is never closer than the pool
boundary), a precisely-identifiable data source (`market_snapshot[symbol]["15m"][-1]`,
already available, no new tracker needed), and a falsification
condition stated without assuming market intent.

### Affected consumers

- **S001** (`strategy/setups/liquidity_sweep_reversal.py` +
  `strategy_engine_v2_backtest_adapter.py`): would require a NEW,
  disabled-by-default adapter variant (mirroring this session's own
  `require_confirmation`/`require_cvd_confirmation` ablation-flag
  pattern) — never modifying the production adapter's own default
  stop logic in place.
- **S005**: no change recommended (§4b).
- **A future IFVG-reversal setup**: design-only (§4c); no setup exists
  yet to affect.

### Required verification (future, not authorized here)

1. A focused unit test proving the sweep-extreme is correctly read
   from the 15m candle matching `resolved_at`, not the 1-minute
   `current_candle`.
2. A byte-identical control-equivalence proof that the EXISTING
   pool-boundary stop variant is unaffected (same pattern as every
   ablation this session).
3. A frozen research protocol before any TRAIN-data outcome is
   computed — this design is not yet authorized for backtesting.

### One recommended next task

**Design-and-implement (not backtest) a disabled-by-default S001 stop
variant** implementing §4a exactly, with the 3 verification items
above, as its own bounded sprint — matching this session's own
established "implement first, prove control-equivalence, freeze
before computing outcomes" sequence. **What would demonstrate trading
value**: a future, separately-authorized frozen TRAIN backtest
comparing this variant against unchanged S001, reporting whether the
(necessarily) larger average risk-per-trade is offset by fewer
premature stop-outs on retests that never truly exceeded the sweep's
own extreme — expectancy and drawdown, not merely win-rate, since a
wider stop mechanically raises win-rate somewhat regardless of edge.

**If the Nephew_Sam_ Pine source becomes available**, the second
recommended task is completing Section 2's comparison properly against
real code, prioritized on the "wait for candle close" mechanism first.

---

## 6. Explicit confirmations

No production file was modified. No new SOL/BTC data period was
accessed. No backtest was run. All prior uncommitted work (Multi-Module
Setup Discovery, FVG/IFVG design review and implementation, the MSB-OB
Order Block comparison) remains untouched.
