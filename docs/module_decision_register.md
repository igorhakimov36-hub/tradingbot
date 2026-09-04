# Module Decision Register
## Consolidated findings from the CMC / Liquidity Sweep / Order Block reviews

**Status: documentation only.** No module listed here has been modified. This register consolidates the three completed comparison reviews (CMC vs. LuxAlgo SMC, Liquidity Sweep vs. LuxAlgo Liquidity Swings, Order Block vs. LuxAlgo Order Blocks & Breaker Blocks) into one classified reference for future sprints.

---

## A. Confirmed corrections required before S008

### A1. Order Block BOS-event identity collapses consecutive same-direction breaks
- **Evidence:** direct code trace of `_detect_new_order_block`'s `is_new_break = bos != "NO_BOS" and bos != self._last_bos_state` — identity is direction-only. Concrete bar-by-bar trace: Bar 5 breaks swing_high=100 → OB#1 created, `last_bos_state="BULLISH_BOS"`. Bar 6 breaks a *new*, higher swing high (106) but `bos` evaluates to the same string `"BULLISH_BOS"` → `is_new_break=False` → no OB#2 created. Only resets if `bos` dips to `"NO_BOS"` in between.
- **Affected modules/setups:** `strategy/features/order_block.py` (`OrderBlockTracker`); downstream S002, S006 (via `BreakerBlockTracker`), proposed S008.
- **Classification:** defect (a correctness gap in the tracker's own edge-detection identity, not a modeling choice — the tracker's intent, per its docstring, is clearly to create one Order Block per genuine structural break).
- **Required tests:** a constructed sustained-trend scenario with ≥2 genuinely different swing-level breaks in the same direction and no intervening `NO_BOS`, asserting the current (collapsing) behavior explicitly, to be updated once corrected.
- **Dependency order:** must be resolved (or explicitly accepted as a known limitation with a documented reason) before S008 is built on top of `impulse_strength`/`mitigation_zone`, since S008's whole thesis is about capturing displacement in trending conditions — exactly where this collapsing is most likely to matter.
- **Future acceptance/rejection criteria:** a corrected identity (direction + broken level, at minimum) must be shown, on real data, to create additional Order Blocks specifically in sustained-trend segments without materially increasing false/noise blocks elsewhere (checked via touch_count/mitigation distribution, not backtest P&L).

### A2. Order Block origin-search boundary is not leg-scoped
- **Evidence:** `_find_last_opposite_candle` searches `self._recent_candles[:-1]` — bounded only by `structure_lookback` (default 500), not by the actual span between the broken swing level and the breakout bar. A leg with no opposite-colored candle (plausible in a strong, low-pullback trend) causes the scan to reach arbitrarily far back, potentially past the relevant swing pivot into unrelated prior structure.
- **Affected modules/setups:** same as A1.
- **Classification:** defect (the module's own docstring and institutional rationale describe "the last opposing candle before the impulsive move" — an origin selected from outside that move contradicts the stated design intent).
- **Required tests:** a constructed long-same-color-run scenario proving the search reaches outside the true impulse leg; a SOL-data behavioral measurement (not a unit test) of how often such runs actually occur on real 15m SOL data.
- **Dependency order:** same as A1 — resolve or explicitly document before S008.
- **Future acceptance/rejection criteria:** a leg-bounded search (e.g., scoped to candles between the broken swing pivot and the breakout bar) must be shown to change origin selection only in the constructed failure case, not in normal cases, before being adopted.

### A3. SOL price scaling (round_number_spacing, volume_profile_bucket_size)
- **Evidence:** `MarketIntelligenceCoordinator.__init__` hardcodes `round_number_spacing=500.0` and `volume_profile_bucket_size=50.0` — both absolute BTC-scaled prices. Confirmed via direct data comparison: SOL's own price range is frequently narrower than 500, and $50 buckets would collapse SOL's Volume Profile into 1-3 buckets. Confirmed further: `LiquidityPoolTracker` itself defaults `round_number_spacing` to `None` (safe), and `VolumeProfileTracker.bucket_size` has **no default at all** (required argument) — the BTC-specific numbers exist in exactly one place, the coordinator's own defaults.
- **Affected modules/setups:** every setup reading Liquidity Pool round-number-sourced zones or any Volume-Profile-derived level (S003, S005, S007, proposed S011).
- **Classification:** defect for SOL use (silently produces degenerate behavior), not a defect for BTC use (the existing default is fine for BTC's own price range).
- **Required tests:** implemented this sprint — see Sprint 1 report (`tests/test_instrument_scale.py`).
- **Dependency order:** resolved in Sprint 1, ahead of any SOL strategy research.
- **Status: corrected this sprint** (see Sprint 1 report below) — not merely registered as pending.

---

## B. Modeling decisions requiring controlled A/B research

For every item below: no change is authorized by this register. Each requires its own future controlled experiment (matching the methodology already used for S001's confirmation-gate promotion), never a threshold chosen by inspection or by fitting to backtest P&L.

### B1. Wick-only Order Block mitigation/invalidation vs. close/body-confirmed
- **Evidence:** `zone_lifecycle.py::compute_mitigation`'s own docstring: *"Uses wick (high/low) penetration... not a close-through-the-zone requirement."* Traced: a single deep wick with an immediate close-back can fully mitigate an Order Block and make it eligible for Breaker Block promotion in one bar. LuxAlgo's comparable script uses close/body-based invalidation throughout. **A real internal inconsistency was found**: our own Liquidity Pool sweep logic treats an identical wick-then-close-back shape as evidence of *rejection* (bullish for reversal), while Order Block mitigation treats the same shape as sufficient for *full invalidation* — opposite readings of a similar pattern in two trackers in the same codebase.
- **Affected:** `order_block.py`, `breaker_block.py`, S002, S006, proposed S008.
- **Classification:** modeling choice (deliberate, documented in the code) — not a bug, but untested against the alternative.
- **Required tests:** wick-only full mitigation with immediate close-back; a companion case isolating close-beyond without deep wick, to document the current boundary precisely; a controlled A/B on real data comparing the current wick-based threshold against a close/body-based alternative.
- **Dependency order:** independent of A1/A2 — can be researched in parallel, ideally before S008 relies heavily on `mitigation_zone_status`.
- **Future acceptance/rejection criteria:** adopt an alternative only if it produces a measurably different (not necessarily "better" without further OOS testing) active-block population on ≥2 independent SOL periods, with the difference explained by fewer premature/spurious invalidations, not by a shrunken sample.

### B2. Separation of touch, mitigation, invalidation, and confirmed breaker
- **Evidence:** traced precisely this sprint — in the current code, "invalidation" is synonymous with reaching 100% mitigation; there is no independently-defined invalidation concept, and "confirmed breaker" inherits the same wick-based trigger.
- **Affected:** same as B1.
- **Classification:** modeling choice / architecture question (should these four remain collapsed into two effective states, or be made genuinely independent fields?).
- **Required tests:** none beyond B1's — this is a conceptual clarification question that would be resolved by whatever B1's research concludes, not a separate experiment.
- **Dependency order:** resolve alongside B1.
- **Future acceptance/rejection criteria:** N/A until B1 is researched — this item exists to make sure any future change to B1 doesn't accidentally conflate concepts that should be recorded separately.

### B3. Liquidity Pool invalidation after sustained acceptance beyond the zone
- **Evidence:** traced precisely this sprint with concrete bar sequences — a pool that is cleanly broken and closed beyond (no same-bar reject) remains "active"/"unswept" indefinitely; a much later, shallower re-test can still be labeled a fresh "sweep," dated arbitrarily far after the level's liquidity was arguably already consumed.
- **Affected:** `liquidity_pool.py`, S001, proposed S007/S009.
- **Classification:** research hypothesis (a real, disclosed gap — not yet known whether it materially affects S001's real signal quality).
- **Required tests:** a constructed stale-sweep scenario (already traced conceptually — bars 1/2/5 in the review); a real-data measurement of how often S001's actual swept-pool signals were preceded by an earlier clean break of the same zone.
- **Dependency order:** independent of A1-A3; relevant to any future S001 re-certification or S009 design.
- **Future acceptance/rejection criteria:** only add a sustained-acceptance invalidation rule if real data shows a measurable fraction of S001's fires are against already-broken (stale) zones, and that excluding them changes win rate/expectancy in a consistent direction across ≥2 periods.

### B4. Single-candle sweep vs. a bounded multi-candle penetration-and-rejection state machine
- **Evidence:** traced precisely — a 2-bar poke-then-reject pattern (Bar 1 pokes above and closes above; Bar 2 closes back below, but Bar 2's own high no longer exceeds the zone) is invisible to the current same-candle rule. Confirmed inherited consistently from `strategy/liquidity.py`'s original single-candle primitive — a deliberate, project-wide convention, not an isolated oversight.
- **Affected:** `liquidity_pool.py`, S001.
- **Classification:** intentional design choice with a disclosed limitation (explicitly not classified as a defect, given the consistent project-wide precedent).
- **Required tests:** a constructed multi-candle rejection scenario proving it is currently missed; if pursued, tests for whatever bounded window (a new parameter) a future state machine would introduce.
- **Dependency order:** independent; lowest priority of the Liquidity Pool items given it requires genuinely new detection logic (a new rejection-window parameter), which this project's own standing rule treats cautiously.
- **Future acceptance/rejection criteria:** only pursue if B3's research shows the single-candle rule is measurably missing a meaningful population of genuine rejections, not merely as a theoretical completeness improvement.

### B5. Mutually exclusive BOS/CHoCH labels vs. retaining both persistent readings
- **Evidence:** traced precisely — `detect_bos`/`detect_choch` can both independently evaluate true on the same bar whenever a break opposes the prevailing `market_structure` regime (both conditions reference the identical `close < previous_swing_low` comparison). LuxAlgo's model is mutually exclusive by construction (`tag = trend.bias == BEARISH ? CHOCH : BOS`).
- **Affected:** `market_structure_tracker.py`, S001 (choch as optional evidence), S007 (bos as required), any future setup reading both.
- **Classification:** modeling choice, with a named real risk (double-counting the same event as two independent confirmations if a future setup naively uses both `bos` and `choch` as separate signals).
- **Required tests:** a unit test documenting the current co-occurrence explicitly (as a factual record, not yet a bug fix); if a mutually-exclusive variant is ever built, a direct comparison against the current independent-fields behavior for any setup that reads both.
- **Dependency order:** independent; relevant to any future setup design (including the "additive event-identity" direction named in the architectural preservation rule below) before that field is built.
- **Future acceptance/rejection criteria:** N/A until a concrete future setup actually needs to read both fields simultaneously — until then this is a named risk, not an active problem, since no current setup gates on both `bos` and `choch` together.

### B6. Fast/internal structure plus slower/swing structure on SOL
- **Evidence:** LuxAlgo's SMC script runs two parallel structure resolutions (internal, length=5; swing, length=50) — a genuinely richer multi-resolution read than our single 3-bar-fractal `MarketStructureTracker`. SOL's measured higher realized volatility (3-7% daily) makes it logically likely — not yet tested — that a single fast resolution produces more noise/churn on SOL than on BTC.
- **Affected:** `market_structure_tracker.py`, S007 (bos-gated), any future regime-gated setup (proposed S011).
- **Classification:** research hypothesis.
- **Required tests:** a real-data measurement of swing-pivot/BOS-flip frequency on SOL vs. BTC at the current 3-bar-fractal resolution, before proposing any specific second resolution or lookback value.
- **Dependency order:** relevant to the paused Sprint 3 (fresh SOL baseline) — the noise-sensitivity question should be measured there before any structural change is proposed.
- **Future acceptance/rejection criteria:** only pursue a second resolution if the frequency measurement shows SOL's current BOS/CHoCH churn rate is materially higher than BTC's in a way that plausibly degrades S007's or a regime gate's reliability.

### B7. Zone-endurance touch/volume accumulation
- **Evidence:** LuxAlgo's Liquidity Swings script accumulates a persistent count/volume tally for a zone while it remains untested — a genuinely different "sustained interest" measure from our `touch_count` (fixed at formation from sub-detector agreement, never updated by later price interaction).
- **Affected:** `liquidity_pool.py`, any future setup wanting a "how well-tested is this level" confirmation (proposed S009).
- **Classification:** research hypothesis (a real, currently-missing capability, not a defect).
- **Required tests:** none yet designed — this is a candidate feature, not a candidate fix; would need its own full test suite if ever built.
- **Dependency order:** lowest priority of the Liquidity Pool items — purely additive, no current setup depends on it.
- **Future acceptance/rejection criteria:** only build if a specific future setup's design (e.g., a revised S009) explicitly calls for it and can state what it would gate or confirm.

### B8. Last-opposite-candle vs. extreme-wick origin selection
- **Evidence:** LuxAlgo's Order Blocks script anchors on the leg's most-extreme-wick candle (by magnitude), not the last opposite-colored candle. Our own module's docstring explicitly grounds the last-opposite-candle rule in dealer/inventory theory ("where positioning against the eventual move was last transacted") — the more textbook ICT definition.
- **Affected:** `order_block.py`, S002, S006, proposed S008.
- **Classification:** research hypothesis (the current rule is judged more institutionally faithful, but this has not been empirically tested against the alternative).
- **Required tests:** a controlled comparison of the two origin-selection rules' resulting touch/mitigation populations on the same real data, only if A1/A2 (which affect the origin-search mechanism more fundamentally) suggest the origin-selection question is a live bottleneck.
- **Dependency order:** lowest priority — only revisit if S008's real-data behavior (post A1/A2 resolution) suggests the origin candle choice is itself a problem, not merely the identity/boundary defects already confirmed.
- **Future acceptance/rejection criteria:** N/A until A1/A2 are resolved and S008 has real data to point to a specific origin-selection problem.

---

## C. Existing behavior retained unless evidence later rejects it

These are conclusions, not open questions — each was directly compared against a specific LuxAlgo alternative and found to be as good or better, on causal/institutional grounds, evidence available today. Listed for completeness and to prevent re-litigating without new evidence.

1. **Liquidity Sweep's wick-beyond-plus-close-back reversal thesis** — more institutionally correct than LuxAlgo Liquidity Swings' break-of-level ("crossed") definition, which has no rejection requirement at all and is a mislabeled comparison to begin with (LuxAlgo's own title is "Liquidity Swings," not "sweep").
2. **Plural, bounded Liquidity Pool tracking** — LuxAlgo tracks only one active zone per side, discarding history; ours tracks a bounded, age-pruned, plural set.
3. **Plural, age-pruned Order Block tracking** — LuxAlgo has no age-based expiry at all (display-count-limited only).
4. **Continuous mitigation-depth information** — strictly richer than LuxAlgo's binary breaker flag.
5. **Separate mitigation-zone information** — LuxAlgo offers only one zone-width toggle (wick vs. body), not two independently-tracked zones.
6. **Edge-triggered touch counting** — LuxAlgo's Order Blocks script has no touch-count concept at all.
7. **Existing persistent BOS/CHoCH readings as context** — retained even as future event-based fields are considered additively (see the architectural preservation rule below); S007 explicitly and deliberately depends on the persistent (not edge-triggered) semantic.

**Each item above is retained "unless evidence later rejects it," not permanently frozen** — if a future controlled experiment (e.g., under B1-B8) produces real data contradicting one of these, this section should be revised, not treated as closed forever.

---

## Architectural preservation rule (guidance for a future sprint, not authorized now)

Per direction: any future correction to the persistent-vs-event-based BOS/CHoCH question (B5) must be **additive**, not a replacement:
- Preserve the existing persistent `bos`/`choch` readings for consumers that need ongoing context (S007's existing dependency must not break).
- Add a new, explicit, one-shot structural-event identity (direction + broken level + timestamp, at minimum) for consumers that need "this specific break happened now" — directly informing how A1's Order Block identity correction should eventually be built: the corrected identity should consume this new event field rather than re-implementing its own direction-string comparison.
- Any such addition must be designed to prevent the same underlying break from being double-counted as two independent confirmations by a future setup (the B5 risk).

This is not authorization to implement any of this now — it is the stated direction for whatever future sprint takes on A1/B5 together.
