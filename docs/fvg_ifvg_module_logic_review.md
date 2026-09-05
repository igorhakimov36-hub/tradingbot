# FVG / IFVG Module Logic Review

Inspection, causal-correctness diagnostics, and comparison/design
only. **No production file was modified. No new market-data period
was accessed. No backtest was run.** The completed SOL Multi-Module
Setup Discovery work and all other uncommitted research from this
session are untouched (confirmed: `git status` shows the same 16 files
as before this review began, plus this new document).

---

## 1. Current state

**Implementation**: `strategy/features/fair_value_gap.py`
(`FairValueGapTracker` / `FairValueGap`) — a standalone, OHLCV-only
primitive, no dependency on any other Smart Money module.

**Wiring**: `strategy/market_intelligence_coordinator.py` constructs
one `FairValueGapTracker` per symbol/timeframe (line 103), syncs it
inside the same one-candle-at-a-time loop every other tracker uses
(line 162), and passes its `.snapshot()` output to
`build_market_intelligence_snapshot()` (line 208).
`strategy/market_intelligence_snapshot.py`'s `_map_zones()` (lines
202–233) folds both the `active` and `filled` lists into the unified
`Zone` shape: `kind="fvg"`, `status="active"|"resolved"`,
`resolution_detail=fill_status`, `resolution_pct=fill_pct`,
`zone_relative_position` recomputed fresh from **whatever
`current_price` the caller passed to `sync_and_build()`** (see §3 —
this is not necessarily the same candle that drove FVG detection).

**Active consumers** (grepped, not assumed):
- `strategy/setups/fair_value_gap_rebalance.py` — **S005, the only
  production setup reading `kind == "fvg"`.** Research-archive status
  per the BTC profitability investigation (net-negative, no
  confirmation gate), not currently recommended for revival
  (`sol_strategy_edge_strategic_review.md` §7), but its code is live
  and would immediately see any FVG module change.
- `strategy/research/structure_based_trail_exit_policy.py` — reads
  `zone.kind in ("order_block", "fvg")` as one of several trailing-
  stop candidate sources. **Not an active/production consumer**: this
  file is the Exit Management Sprint's own research-only, never-
  committed scratchpad code (relocated into the repo, still
  uncommitted, per that sprint's own precedent). Listed for
  completeness only.
- No other setup, research module, or exit policy references
  `kind == "fvg"` (grepped across `strategy/` and `tests/`).

**The project's own existing precedent for "a zone flips after being
fully invalidated"**: `strategy/features/breaker_block.py`
(`BreakerBlockTracker`), consumed by
`strategy/setups/breaker_block_reversal.py`. This is directly relevant
to §4 and is discussed there in full — flagged here so its existence
is established before any IFVG design discussion.

---

## 2. Existing FVG logic, in plain language (code-verified)

Everything below is confirmed by direct code reading
(`strategy/features/fair_value_gap.py`), not inferred from the
docstring alone — each item notes where the two agree or diverge.

**Formation condition, geometry, timeframe**: a 3-candle window,
called A (oldest), B (middle), C (newest) here. A **bullish** gap
forms when `A.high < C.low` (zone = `[A.high, C.low]`). A **bearish**
gap forms when `A.low > C.high` (zone = `[C.high, A.low]`). No
condition on B's own high/low/close at all beyond its existence (its
`volume` is recorded as `formation_volume`, nothing else about B is
read). Single timeframe, caller-supplied and never inferred
(`timeframe` is a pass-through label) — the tracker is fed whatever
candle stream the coordinator gives it (15m in every current wiring).
**No minimum-size filter of any kind** — verified directly: the only
comparison is `A.high < C.low` / `A.low > C.high`, an arbitrarily
small gap qualifies exactly the same as a large one.

**Availability timing**: a gap becomes part of the snapshot the
instant candle C is `sync()`'d — i.e., the same replay step C itself
closes. `created_at` and `origin_bar_index` are both **C's own**
timestamp/index, not A's (see §3 for why this is a meaningful,
deliberately causal choice, and one minor naming imprecision it
creates).

**First touch / partial fill / full fill**: continuous, wick-based.
`FairValueGap.apply_candle()` tracks `_deepest_penetration` (the
furthest wick has reached into the zone from the far edge) and derives
`fill_pct` in `[0, 1]` each time a **new, already-closed** candle is
applied. Three states: `active` (0%), `partially_filled` (0–100%
exclusive), `completely_filled` (100%, at which point the gap moves
from the tracker's `_active` list to `_filled` and is **never updated
again**). No independent "first touch" counter exists (no
`touch_count` field, confirmed absent from `to_dict()`) — unlike Order
Block/Breaker Block, which do expose one.

**Mitigation vocabulary**: this module uses "fill", not "mitigation" —
`fill_status`/`fill_pct`, mapped by the snapshot builder onto the same
generic `resolution_detail`/`resolution_pct` fields Order Block/Breaker
Block/Liquidity Pool populate under their own vocabulary
(`mitigation_status`/`mitigation_pct`, `resolution_detail` for
Liquidity Pool). Purely a naming difference at the Zone-unification
layer, not a behavioral one.

**Invalidation / expiration**: no "invalidation" concept distinct from
full fill — a completely-filled gap is retired to the `_filled` list
permanently (bounded to the most recent `max_tracked_filled=500`).
Separately, an **unfilled** gap is dropped entirely (not moved
anywhere, just removed and counted in `expired_count`) after
`max_age_bars=5000` candles with no fill progress at all reaching
100%. These are two different, independently-triggered retirement
paths — full fill vs. staleness — both permanent, no way back.

**Zone identity / duplicates**: each gap is a fresh `FairValueGap`
object, identity is implicit (object identity, no explicit composite
key the way Breaker Block needs one). Because detection only ever
compares the current sliding 3-candle window (`A`=oldest of the last
3, `C`=newest), the same `(A, C)` pair is tested exactly once — as soon
as a new candle arrives, the window slides and that exact pair can
never be re-tested. **No duplicate-detection risk by construction**,
verified by tracing the sliding-window mechanics, not assumed.

**Outputs consumed by S005**: `direction`, `zone_high`/`zone_low`
(stop-loss level), `status`/`resolution_detail` (gates firing — must
be `active` + `partially_filled`), `zone_relative_position` (must be
`inside_price`). `fill_pct` is read only for display in the
`ConditionResult.detail` string, not gated on directly.

---

## 3. Causal correctness review

**Completed-candle availability**: confirmed sound.
`FairValueGapTracker.sync()` carries the identical rewind/divergence
guard every tracker in this codebase uses (raises if `candles` goes
backwards or diverges from history already consumed) — a gap can only
ever be detected from candles the tracker has actually been fed, one
at a time, in the coordinator's own `for i in range(...)` loop
(`market_intelligence_coordinator.py` lines 158–166), which itself only
advances through **already-closed** 15m candles.

**ATR self-reference avoided**: `_ingest()` calls
`self._atr.ingest_one(candle)` strictly **after** `_detect_new_gap()`
(line 278) — `gap_size_atr_ratio` is computed from ATR measured
*before* the impulsive middle candle is folded in, avoiding the ratio
being inflated by the very candle that created the gap. Verified by
reading the call order directly, not merely trusting the docstring's
own claim.

**HTF alignment**: not applicable in the current wiring — the tracker
only ever receives the same single-timeframe stream the coordinator is
built for (15m in every current setup/research script). No
cross-timeframe request is made internally by this module at all (a
structural difference from LuxAlgo's own script, which explicitly
supports evaluating on a **different** `tf` via `request.security` —
see §5's causal-timing comparison).

**Replay determinism**: `build_market_intelligence_snapshot()` is
documented and verified as a pure function of already-computed tracker
outputs (no hidden state of its own) — calling it twice with identical
inputs is guaranteed identical. `FairValueGapTracker.sync()` is
purely incremental and order-preserving.

**One real timing subtlety found, worth flagging precisely** (not
present in the module's own docstring, found by reasoning through the
actual replay granularity): the **fill-status update grain (15m, only
on newly-closed candles) is coarser than the `zone_relative_position`
grain (whatever `current_price` the caller passes — the current
1-minute candle's close, in every actual backtest wiring in this
project)**. This means it is possible for `zone_relative_position ==
"inside_price"` to be true **before** the 15m candle that will
eventually register the corresponding fill has closed — i.e., price
can visibly be "inside" a gap for several 1-minute ticks while the
gap's own `fill_status` still reads `"active"` (0% filled), because
`fill_pct` only advances once a full 15m candle closes and its wick is
applied. **This directly contradicts one specific claim in
`fair_value_gap_rebalance.py`'s own docstring** ("`active` (0% filled)
and `inside_price` simultaneously true is not a state that occurs in
practice") — under real 1m-driven replay, it demonstrably can occur,
for as long as ~14 minutes within a forming 15m bar. **This is not a
functional defect**: S005 requires `resolution_detail ==
"partially_filled"`, not `"active"`, so this timing gap cannot cause
an incorrect fire — it only means the setup becomes eligible to fire
slightly later than the very first 1-minute tick that visually entered
the gap (once the enclosing 15m candle actually closes and registers
the fill). Classified as a **documentation-vs-reality mismatch**, not
a correctness defect, but corrected here since the original docstring
claim is demonstrably false under the system's own real replay
mechanics.

**Minor naming imprecision** (not a defect): `origin_bar_index` and
`created_at` are both set to candle **C's** (the confirming candle's)
own index/timestamp, not candle A's. This is the *causally correct*
choice (age and creation time must be measured from when the gap
became knowable, never from the historical candle that merely
participated in it) — but the field name "origin" reads as if it
should be A's index. Recommend a docstring clarification only; no
behavior change needed.

---

## 4. IFVG within the existing FVG module — does equivalent behavior already exist?

**No, not for FVG specifically** — demonstrated concretely, not
assumed. Take a gap that reaches `fill_status == "completely_filled"`:
`_update_fills()` moves it from `self._active` to `self._filled`
(`fair_value_gap.py` lines 285–293), and `apply_candle()` — the only
method that ever changes a gap's own state — is called **exclusively**
on members of `self._active` (line 285: `for gap in self._active:`).
Once filled, a `FairValueGap` object is never touched again. There is
no field, method, or code path anywhere in this module that flips a
filled gap's role or gives it a second, inverted lifecycle. Synthetic
Example 3 (§5) demonstrates this with an exact candle sequence: our
tracker retires the gap at full fill; a close-confirmed inversion
event one bar later has nothing left to act on.

**The project DOES already have an equivalent CONCEPT — for Order
Blocks, not FVG — via a structurally different architecture.**
`BreakerBlockTracker` (`strategy/features/breaker_block.py`) is "not a
new pattern - a polarity flip of a failed Order Block" (its own
docstring). Its own explicit design choice: **a separate tracker
class, subscribing to the source tracker's `mitigated` output**, not
an in-place lifecycle extension of the same `OrderBlock` object. A new
`BreakerBlock` is a **new object** with its own fresh
`touch_count`/`mitigation_pct` lifecycle, linked back to its source
only via a composite key (`direction`, `origin_timestamp`,
`zone_high`, `zone_low`, `created_at`) for provenance — it does not
literally reuse the same struct.

**This is a direct, load-bearing precedent conflict with the stated
preferred IFVG architecture** ("a lifecycle extension of the same
zone, retaining its identity, original direction, boundaries, and
transition history"). Two legitimate paths exist, and the project has
already chosen the separate-tracker path once (for Breaker Block):

- **Path A — separate tracker (Breaker Block's own precedent)**:
  build `InversionFairValueGapTracker`, subscribing to
  `FairValueGapTracker.snapshot()["filled"]`, reusing
  `strategy/features/zone_lifecycle.py`'s shared mitigation/touch math
  exactly as Breaker Block already does (no lifecycle logic
  duplicated a third time). Pros: proven pattern, zero risk to
  `FairValueGapTracker` itself, identical testing/wiring shape to an
  already-shipped module. Cons: does not literally satisfy "retaining
  its identity" — the inverted zone is a **new** object with its own
  fresh `touch_count`, linked by composite key, not the same struct
  continuing.
- **Path B — in-place lifecycle extension (the stated preference)**:
  add `is_inverted`/`inverted_at`/`inversion_direction` fields directly
  to `FairValueGap`, and change `_update_fills()` to keep a
  fully-filled gap under continued tracking (a new `_inverted` list,
  or a state flag on the existing object) instead of retiring it.
  Pros: literally satisfies "same zone, same identity, full transition
  history in one object" — a completely-filled gap's own `touch_count`
  (if added, see §6), `formation_volume`, `atr_at_creation` etc. remain
  attached to the SAME record its inverted life is judged against.
  Cons: a real, new precedent for this codebase (every existing
  "zone flips" case uses Path A) — the case for it should rest on the
  concrete identity benefit above, not on being the first
  implementation attempted.

**Recommendation for §6**: Path B, precisely because FVG's own fill
lifecycle (unlike Order Block's mitigation lifecycle) has no
independent "touch" concept to preserve separately — inversion IS this
zone's next lifecycle stage, not a materially different pattern the
way Breaker Block genuinely is its own tracked entity with its own
touch/impulse math. Detailed in §6.

---

## 5. Comparison with the supplied reference implementations

Both reference scripts are present in the prompt (LuxAlgo "Fair Value
Gap" and ChartPrime "Inversion Fair Value Gaps" — supplied twice,
byte-identical both times, so this review treats it as one IFVG
reference, not two). **No reference code is missing; this comparison
is complete.**

### 5a. Comparison table

| Dimension | Ours (`fair_value_gap.py`) | LuxAlgo FVG | ChartPrime IFVG |
|---|---|---|---|
| Formation geometry | `A.high < C.low` (bull) / `A.low > C.high` (bear) | Same core geometry, **+ requires `close[1] > high[2]`** (bull) — the middle candle's own close must also clear A's high | Same core geometry as ours (no middle-candle-close requirement) |
| Minimum-size filter | **None** | Optional (`thresholdPer`, default 0 = off; or adaptive "auto" mode) | **Required by default** (`minSizePerc = 0.1%` of price) |
| Detection timing | On C's own `sync()` step (already-closed only) | Confirmed via `request.security(...)`; causally equivalent, but the script's own `tf` input allows an *unaligned* HTF request with no explicit `lookahead_off` shown — a real repainting risk class our single-timeframe-only tracker cannot have by construction | Explicitly gated on `barstate.isconfirmed` — same causal guarantee, different mechanism |
| Fill/mitigation rule | **Wick-based**, continuous `fill_pct` in [0,1], 3 states | **Close-based**, binary only (no partial-fill concept at all) — mitigated only when `close` fully clears the *opposite* edge | Same close-based, binary, full-clear rule as LuxAlgo (no partial-fill tracking) |
| What happens at full fill/mitigation | Gap retired to `_filled` list, no further updates | Box deleted; optional dashed mitigation line drawn | **Zone flips** (`isInverted = true`), same box/identity continues |
| Zone lifetime bound | `max_age_bars=5000`, hard-pruned from tracking | None shown (relies on `showLast`/display limits only) | `longevity=500` bars — **cosmetic only**: box shrinks to a 5-bar marker, but the underlying `FVGZone` struct is never removed from `activeZones` |
| Cross-zone interaction | None — every gap tracked fully independently | None | **`checkOverlap()`**: a new zone can retire an existing unmitigated zone if their ranges overlap |
| Touch/retest signal | No independent touch counter for FVG at all (S005 gates on `zone_relative_position == inside_price`, continuous) | None (display-only script) | **2-bar rejection pattern**: prior bar's high/low reaches the (former) zone edge, current bar fails to exceed it, with a 5-bar cooldown between repeat signals |
| Post-inversion failure state | N/A (no inversion concept) | N/A | **Yes** — `isInverted and close > z.top` (bull case) retires the zone as "failed", a third lifecycle outcome beyond fill/inversion |

### 5b. Synthetic candle examples (identical sequence used throughout)

All prices illustrative SOL-scale (~$100), 15m bars, A/B/C = the
3-candle detection window.

**Example 1 — formation-condition divergence (LuxAlgo's extra
middle-candle-close requirement)**
- A: `H=100.20, L=99.80`
- B: `H=101.00, L=100.10, C=100.15` (impulsive wick, but its own close
  never exceeds A's high)
- C: `L=100.30, H=100.60, C=100.50`

Ours: `A.high(100.20) < C.low(100.30)` → **bullish FVG detected**,
zone `[100.20, 100.30]`. LuxAlgo: `low(100.30) > high[2](100.20)` ✓,
but `close[1](100.15) > high[2](100.20)` → **False — LuxAlgo does not
detect this gap**, even though the same 3-candle wick geometry exists.
**Confirmed correctness-relevant semantic difference** (§5c).

**Example 2 — fill/mitigation divergence (wick vs. close)**, same
zone `[100.20, 100.30]`:
- D: `L=100.15, H=100.35, C=100.28` (wick dips below the zone's own
  bottom, closes back inside)

Ours: `_deepest_penetration = min(100.30, 100.15) = 100.15` →
`fill_pct = (100.30-100.15)/(100.30-100.20) = 1.5` → clamped to
**1.0 → `completely_filled`, retired.** LuxAlgo/ChartPrime: mitigation
check is `close(100.28) < zone_low(100.20)` → **False — the gap
remains fully active/unmitigated** under a close-based rule. **The
same candle produces opposite lifecycle outcomes in the two designs**
— the single largest, most consequential divergence found in this
review.

**Example 3 — proof that no FVG-inversion path exists today**,
continuing Example 2 (our tracker already retired this gap at D):
- E: `L=99.90, H=100.05, C=99.95` (closes well below the zone)

ChartPrime: `close(99.95) < z.bottom(100.20)` → **inversion confirmed**
— same zone object flips to bearish/resistance, box/identity
continues. Ours: the gap was already moved to `_filled` at candle D
and is never evaluated again — **there is nothing left in this
tracker's own state for candle E to act on.** This is the concrete
demonstration requested by §4: equivalent behavior does not exist for
FVG today.

**Example 4 — actionable-retest timing**, continuing (zone now
notionally inverted, boundaries unchanged `[100.20, 100.30]`, now
acting as resistance):
- F: `L=100.10, H=100.19, C=100.12`
- G: `L=100.05, H=100.20, C=100.08` (reaches exactly the boundary)
- H: `L=100.00, H=100.15, C=100.05` (fails to exceed it)

ChartPrime: at H, `high[1](100.20) >= z.bottom(100.20)` ✓ and
`high(100.15) <= z.bottom(100.20)` ✓ → **retest signal fires at H** —
a specific 2-bar rejection pattern. The closest analog our own Zone
model offers today, `zone_relative_position == "inside_price"`, would
instead be **continuously true across F, G, and H** (any bar with
price between 100.20–100.30) — a materially cruder, more repeat-prone
signal absent additional filtering (the same "known re-fire
characteristic" already disclosed and accepted for S005 itself, and
already bounded by the one-trade-at-a-time engine — not a new problem,
but a real design-choice gap worth naming precisely for any future
IFVG-consuming setup).

### 5c. Classification of every difference found

| # | Difference | Classification | Rationale |
|---|---|---|---|
| 1 | LuxAlgo's `close[1] > high[2]` middle-candle-close requirement | **Research hypothesis** | A plausible additional displacement-confirmation filter (the impulsive candle must show real follow-through, not just a wick), but untested — not a correctness defect in either direction; our tracker's own docstring never claimed to require this |
| 2 | No minimum-size filter in ours vs. both reference scripts having one (optional/default-off in LuxAlgo, required-by-default in ChartPrime) | **Research hypothesis** | Directly parallel to the already-explored Order Block `impulse_strength` and S011 `bucket_size`-multiple filters in this project's own recent work — worth testing, not assumed beneficial |
| 3 | Wick-based (ours) vs. close-based (both reference scripts) fill/mitigation | **Intentional semantic difference, already disclosed** | `fair_value_gap.py`'s own docstring explicitly names this as a deliberate, documented choice mirroring the identical wick-vs-close question already flagged and left open for Order Block (`module_decision_register.md` B1) — not a defect, a live open question this review does not resolve |
| 4 | No cross-zone `checkOverlap`-style consumption in ours | **Research hypothesis** | A new mechanic, not present in our design at all; plausible but unproven — could also be a source of false invalidation (an unrelated, coincidentally-overlapping gap retiring one that was about to fill legitimately) |
| 5 | ChartPrime's cosmetic-only `longevity` (never actually prunes) vs. our hard `max_age_bars` prune | **Not adopted — ours is correct as-is** | Bounded memory/computation over a multi-year replay is a real engineering requirement this project already takes seriously (see `fair_value_gap.py`'s own "Known Limitations"); ChartPrime's unbounded-array behavior is a liability of a charting tool that only cares about a fixed visual window, not a design worth importing |
| 6 | No FVG-native inversion lifecycle in ours | **Confirmed gap, addressed in §6** | Demonstrated concretely in Example 3, not assumed |
| 7 | No 2-bar rejection retest pattern for any zone kind in ours | **Research hypothesis, addressed in §6** | A specific, well-defined signal worth adding for any IFVG-consuming setup, but its trading value is unproven |
| 8 | Post-inversion "failure" retirement (`isInverted and close > top`) | **Confirmed gap, worth adopting for correctness of the lifecycle model** | Without it, an inverted zone that gets fully reclaimed the other way would keep signaling as if still valid — a real state-machine completeness gap, not merely a hypothesis, once inversion itself is built |
| 9 | LuxAlgo's unguarded higher-timeframe `request.security` (repainting risk class) | **Not applicable — already avoided by construction** | Our architecture never lets a setup read a different, unaligned timeframe through this module; noted for completeness, not actionable |

Per the explicit instruction: **neither reference implementation's
greater complexity nor its recognizable-indicator branding is treated
as evidence of correctness** — every row above is graded on the
synthetic-example behavior actually traced, not on authorship.

---

## 6. Decision report

### 6a. Recommended combined design

**RETAIN** (no change):
- Wick-based fill tracking as the *primary* fill/partial-fill signal
  (item 3) — already an intentional, disclosed choice; a close-based
  variant remains a separate, not-yet-authorized experiment (same
  status as the parallel Order Block B1 question).
- Hard `max_age_bars` pruning over ChartPrime's cosmetic-only
  longevity (item 5).
- Single-timeframe-only design (no internal HTF request) — avoids
  LuxAlgo's own repainting risk class by construction (item 9).
- `FairValueGapTracker`'s existing detection/fill code — **unchanged**.

**ADOPT** (add, following the Breaker Block precedent's own reused
infrastructure — `strategy/features/zone_lifecycle.py` — rather than
reinventing wick/close math a third time):
- **Path B in-place inversion lifecycle** (§4): extend `FairValueGap`
  with `is_inverted: bool`, `inverted_at: datetime | None`, and keep a
  fully-filled gap under continued tracking instead of permanent
  retirement, **using a CLOSE-based confirmation rule for inversion
  specifically** (matching both reference scripts exactly — this is
  the one place this review recommends adopting close-based logic,
  since "inversion" is explicitly a stronger, close-confirmed claim
  than "filled", and conflating the two by reusing the wick-based fill
  event would blur exactly the distinction item 3/§4 require keeping
  separate). A gap must first be wick-fully-filled (existing behavior,
  unchanged) — inversion confirmation is a **subsequent, independent,
  close-based check** applied only to already-fully-filled gaps, never
  a substitute for fill tracking.
- **Post-inversion failure retirement** (item 8) — a third terminal
  state (`failed`) alongside `completely_filled`/`expired`, using the
  same close-through-the-opposite-edge rule.

**ADAPT** (build as a new, explicitly optional field/output, gated so
S005's own existing behavior is provably unchanged unless a future
setup opts in):
- A **retest signal**, modeled on ChartPrime's 2-bar rejection pattern
  (item 7) rather than continuous `zone_relative_position`, added as a
  new boolean output (e.g. `retest_confirmed`) computed only for
  already-inverted zones — never gating S005 itself, which does not
  read inversion state at all.

**REJECT / defer, pending evidence** (research hypotheses, not
adopted without a controlled experiment):
- Middle-candle-close requirement (item 1).
- Minimum-size filter (item 2).
- Cross-zone `checkOverlap` consumption (item 4) — the false-invalidation
  risk named in item 4's own rationale means this needs its own
  evidence before being trusted, not just novelty.

### 6b. Affected consumers

- `strategy/setups/fair_value_gap_rebalance.py` (S005): **zero
  required changes** — none of the ADOPT/ADAPT items touch the
  `active`/`partially_filled`/`inside_price` fields S005 already
  reads; a new `inverted`/`failed` status only ever applies to gaps
  that have already left the `active` list S005 filters on.
- `strategy/research/structure_based_trail_exit_policy.py`: unaffected
  (reads only `kind`/`direction`, not fill/inversion state).
- Any **future** IFVG-consuming setup (not yet designed) would be the
  first real consumer of the new fields — out of scope for this
  review per the explicit "leave production behavior and strategy
  parameters unchanged" boundary.

### 6c. Required verification (before any of the above is implemented)

1. Unit tests replaying the exact 4 synthetic sequences in §5b against
   both the current tracker and the proposed extension, asserting the
   documented divergence is reproduced deterministically.
2. A real-data replay-safety check (existing project convention):
   confirm the new inversion/failure fields never use a not-yet-closed
   candle, mirroring the check already applied to every other tracker
   in this codebase.
3. Byte-identical-output proof that S005's own real-data backtest
   result is unchanged before/after the ADOPT items are added
   (matching this project's own established "prove the control is
   untouched" discipline from the multi-module and exit-policy
   sprints).
4. A frozen research protocol (per this project's standing discipline)
   before any candidate setup is built on top of the new fields —
   not authorized by this review.

### 6d. Recommended implementation order

1. Extend `FairValueGap`/`FairValueGapTracker` with the ADOPT items
   (inversion + post-inversion failure), reusing
   `zone_lifecycle.py`'s existing helpers where the close-based check
   overlaps with what Breaker Block/Order Block already compute for
   themselves (avoid a third reimplementation of the same math).
2. Add the ADAPT retest signal as a new, additive Zone/output field —
   never gating any existing setup.
3. Only then, in a separate, explicitly-authorized sprint: design one
   new setup consuming the new fields, under this project's full
   frozen-protocol discipline (module inventory, freeze, TRAIN-only
   evaluation) — matching exactly the process just completed for
   S008/S009/S011.

### 6e. Later controlled comparison (outlined, not run — no backtest performed in this review)

Once implemented and verified (§6c), a three-arm standalone comparison
on the existing SOL TRAIN months, reusing S005's own current
required-condition logic unchanged as the control:

1. **Current FVG behavior** — S005 exactly as it exists today (wick
   fill only, no inversion field even present).
2. **Revised FVG behavior** — S005 unchanged, but running against the
   extended tracker (inversion/failure fields computed and available,
   simply unused by S005) — this arm's own purpose is to prove, by
   direct backtest equivalence, that adding the new fields changes
   nothing about S005's real trades (the same control-equivalence
   proof required in §6c, now also demonstrated at the strategy level,
   not just the tracker level).
3. **Revised FVG with IFVG signals enabled** — a new, explicitly
   separate research-only setup (not S005) that additionally requires
   `is_inverted` and the retest signal, isolating what the inversion
   concept itself contributes (trade frequency, expectancy in R, net
   P&L, cost sensitivity, drawdown) independent of S005's own
   already-documented weaknesses (no confirmation gate, high
   frequency, RESEARCH ARCHIVE status).

This isolates exactly what each change contributes — arm 2 vs. arm 1
proves the extension is inert until used; arm 3 vs. arm 1/2 measures
the inversion/retest concept's own standalone value — matching the
same standalone-before-portfolio, frozen-before-computed discipline
already used throughout this project's SOL research.

---

## 7. Explicit confirmations

No production file was modified to produce this review. No new SOL/BTC
data period was accessed. No backtest was run — every synthetic
example in §5b is a hand-constructed, illustrative candle sequence,
not a real-data measurement. This document and all prior uncommitted
research remain unstaged, awaiting review before any implementation
begins.
