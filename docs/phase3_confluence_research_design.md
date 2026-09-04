# Phase 3 — Institutional Confluence Research
## Step 1: Research Design (S007 Candidate Selection)

**Status: DESIGN ONLY. No code written. No repository files modified.**

This document reviews every Market Intelligence module, every implemented
setup (S001–S006), and every research report produced so far, then
proposes five S007 candidates that each combine multiple independent
Market Intelligence families. It ranks them and recommends exactly one
for implementation. Per the task instructions, this is architecture and
research design only.

---

## 0. A correction before designing anything: "Market Regime" is not an
independent family in this codebase today

The task brief listed eight example independent families, including
**Market Regime**, alongside **Price Structure (BOS/CHOCH)**. Before
proposing candidates, this needs to be checked against what actually
exists — not assumed.

Direct inspection of `strategy/features/market_structure_tracker.py` and
`strategy/market_intelligence_snapshot.py` shows there is no independent
regime classifier module. The only regime-shaped signal anywhere in the
snapshot is `snapshot.structure["market_structure"]`
(`BULLISH`/`BEARISH`/`RANGE`/`UNKNOWN`) — and that field comes from the
**exact same tracker and the exact same dict** that also produces `bos`
and `choch`. "Price Structure" and "Market Regime" are not two
independent families here; they are two readings off one tracker.

There is an `AverageTrueRangeTracker` (`strategy/features/utils.py`),
which could in principle back a volatility-regime classifier, but it is
not wired into `MarketIntelligenceCoordinator` or into
`build_market_intelligence_snapshot` at all — it is not part of Market
Intelligence today, it is invisible to any setup.

**Consequence for this design:** no candidate below claims "Price
Structure" and "Market Regime" as two separate families — that would be
double-counting one tracker's output to satisfy a counting rule, exactly
the kind of box-checking this project has consistently rejected in favor
of technical correctness. Where a candidate needs regime context, it
spends its one "Structure" family on `market_structure` directly. Where
a candidate's institutional thesis genuinely depends on volatility
regime, that is flagged as **infrastructure this candidate cannot
honestly assume today** — building it would be a new module, out of
scope for "reuse only existing Market Intelligence modules."

This leaves **seven** independent families actually available in the
current snapshot: Zones (Smart Money), Liquidity, Levels/Volume Profile,
Order Flow, Structure, Intermarket/SMT, Sessions.

---

## 1. What we already know (grounding, not speculation)

A candidate's "expected independent edge" is not a guess — this project
has already measured each family's standalone behavior:

| Setup | Families (required) | Certification | Key finding |
|---|---|---|---|
| S001 Liquidity Sweep Reversal | Zones(Liquidity Pool) + Order Flow(CVD); Structure/Zones/Intermarket as optional confirmation | **APPROVED** | Only setup requiring cross-family agreement from the start. Expectancy flipped -53.78 → +3.88 per trade after requiring ≥1 additional confirmation. |
| S002 Order Block Continuation | Zones only | APPROVED (original), **fails OOS** | 0/6 profitable OOS months; drawdown 23–37% vs 13.26% original. No structural or order-flow confirmation of trend context was ever required — diagnosed as the likely cause. |
| S003 Volume Node Reversal | Levels(Volume Profile) only | RESEARCH ARCHIVE | `node_is_wide` / `value_area_confluence` filters measurably improved results — Volume Profile carries *some* signal, but never validated combined with anything else. |
| S004 SMT Reversal | Intermarket only | **REJECTED** | `structural_agreement`/`structural_divergence_flag` satisfied ~100% of real fires — proven structurally non-discriminating at their current thresholds. |
| S005 FVG Rebalance | Zones only | RESEARCH ARCHIVE | Best standalone result yet, PF 0.992 — close to breakeven alone. |
| S006 Breaker Block Reversal | Zones only | **REJECTED** | Monotonic OOS deterioration, drawdown to 89.32%. |

Three conclusions follow directly, and shape everything below:

1. **Every setup in the library except S001 is single-family.** The
   library has never actually tested whether combining families helps —
   Phase 3's premise is untested, not proven, which is exactly why it's
   worth doing.
2. **The only two ingredients with any measured positive contribution**
   are Liquidity Pools + Order Flow + Structure (via S001) and, more
   weakly, Volume Profile (via S003). Order Block zones, Breaker Block
   zones, and Intermarket/SMT's *current* flags have each been
   individually rejected or failed OOS standalone.
3. **Sessions has never been used by any setup, required or optional.**
   It is the one completely untested family in the entire library.

Any candidate that requires Intermarket/SMT as a hard gate is reusing a
mechanism we have *already measured* to be non-discriminating (S004).
That does not make it invalid to propose, but it must be flagged
honestly wherever it appears below, not silently assumed to work
differently this time because it's now part of a bigger combination.

---

## 2. Five candidates

### Candidate A — Session Liquidity Raid
**Families combined:** Sessions + Liquidity + Order Flow (required) → Volume Profile + Structure (optional confirmation) — **4 families**

- **Institutional trading thesis:** Session opens (particularly London
  and New York) are when institutional liquidity raids concentrate —
  price is deliberately run through the prior session's high/low to
  trigger resting stops before reversing ("Judas Swing" / kill-zone
  manipulation). This is one of the most standard concepts in
  session-based smart-money trading, and it has never been tested here.
- **Required conditions:** (1) a level in `sessions.previous_period_high_low`
  is swept this bar AND that same price also corresponds to an active or
  freshly-swept Liquidity Pool / Equal High-Low zone — i.e. the session
  extreme *is* a tracked liquidity concentration, not merely a
  coincidental price level; (2) CVD shows exhaustion or divergence
  (`order_flow.cvd`) in the reversal direction.
- **Optional confirmations:** the sweep occurs at or beyond a Low
  Volume Node, or outside the current Value Area (`volume_profile`) —
  a thin, low-resistance area is easier to run through cheaply, which is
  itself supporting evidence of a deliberate raid rather than organic
  flow; CHOCH agrees (`structure`).
- **Expected market regime:** most active at session opens/kill zones;
  expected weak or absent during low-activity windows (Asian session on
  BTC in particular) — a testable, falsifiable prediction, not assumed.
- **Expected holding time:** short (hours) — intraday reversal.
- **Expected trade frequency:** low — requires coincidence of a session
  boundary *and* a tracked liquidity zone at the same price.
- **Expected signal frequency:** low, similar order of magnitude to S001's
  own rare joint-condition population, restricted further by the
  session-anchoring requirement.
- **Expected overlap with S001–S006:** moderate. Shares its two required
  families (Liquidity, Order Flow) with S001, but the session-anchoring
  requirement means it fires on a materially different, narrower
  population than S001's "any liquidity pool, any time" criterion.
- **Expected independent information gain:** high on the Sessions axis
  specifically — this is the only candidate that puts a completely
  untested family to a real test.
- **Expected architectural complexity:** moderate. Requires new logic
  cross-referencing `sessions.previous_period_high_low` against the
  `zones` list by price — no existing setup reads both a Level
  substructure and a Zone substructure together.
- **Why these families reinforce each other:** Sessions supplies *when*
  and *where* institutional attention concentrates; Liquidity confirms
  that price level is a genuine resting-order magnet, not an arbitrary
  session boundary; Volume Profile independently corroborates that the
  area is structurally thin; Order Flow is the only family that can
  distinguish "stop-run that reverses" from "stop-run that continues."
  None of these four measure the same underlying phenomenon.
- **Professional concept represented:** session-open liquidity
  manipulation / kill-zone trading.

---

### Candidate B — Trend Continuation Confluence
**Families combined:** Structure + Liquidity (required) → Volume Profile + Order Flow (optional confirmation) — **4 families**

- **Institutional trading thesis:** a confirmed trend leg (BOS) retraces
  to retest the last resting-liquidity zone before the breakout — "old
  resistance becomes support." The retest is validated by the volume
  profile's value area genuinely migrating in the trend direction
  (Auction Market Theory: fair value relocating, not just price
  drifting), and by order flow agreeing with continuation rather than
  showing exhaustion. This is the direct, hypothesis-driven answer to
  **why S002 failed OOS**: S002 required only a first-touch Order Block
  with zero structural or order-flow context, and its OOS report
  concluded exactly that lack of context as the likely cause. This
  candidate is that missing context, made explicit and testable, not a
  new speculative idea.
- **Required conditions:** (1) a fresh BOS (within a bounded recent
  window, using the same timestamp-freshness technique already validated
  in S004) confirming an active trend leg; (2) price makes first touch of
  an active, unswept Liquidity Pool or Equal High/Low in the pullback
  direction (reusing the first-touch detection pattern already proven in
  S002/S006).
- **Optional confirmations:** the retest level falls within the
  previous closed period's Value Area boundary in the trend direction
  (`volume_profile.value_area_high/low`, `poc_shift_from_previous_period`
  — both already computed, zero new calculation needed); the current
  bar's `delta_direction` agrees with the trend direction (continuation,
  not exhaustion).
- **Expected market regime:** trending only (`structure.market_structure`
  == BULLISH or BEARISH). Expected to perform poorly or not fire in
  RANGE — a falsifiable, pre-registered prediction.
- **Expected holding time:** medium — continuation trades typically run
  to a new swing extreme, longer than a reversal scalp.
- **Expected trade frequency:** moderate-low — gated on BOS frequency,
  itself already a bounded, infrequent event.
- **Expected signal frequency:** low-moderate.
- **Expected overlap with S001–S006:** low-moderate in family
  composition (shares Liquidity with S001), **zero mechanistic overlap**
  — S001 is a reversal setup triggered by a sweep; this is a
  continuation setup triggered by a retest of an *unswept* zone. The two
  cannot fire on the same event by construction.
- **Expected independent information gain:** high. Every other setup in
  the library (S001, S003, S004, S006) is reversal-type. The library
  currently has **zero validated continuation logic** — S002 was the one
  continuation attempt and it failed specifically from missing this
  confirmation stack.
- **Expected architectural complexity:** the lowest of any 4-family
  candidate here. Three of its four families are read via fields already
  computed and exposed with no new arithmetic (`market_structure`,
  Volume Profile's migration fields, `delta_direction`); the only new
  logic is "fresh BOS + subsequent zone retest," which recombines two
  patterns already proven safe elsewhere (S004's timestamp-freshness
  check, S002/S006's first-touch check) rather than inventing a new one.
- **Why these families reinforce each other:** Structure supplies
  *direction and context* (is there actually a trend to continue);
  Liquidity supplies *where* institutions are likely to re-enter; Volume
  Profile is an entirely independent, volume-based method of confirming
  the same directional bias (not price-action-derived at all); Order
  Flow is the immediate, bar-level confirmation that real participation
  is occurring at the retest. Each answers a question the others cannot.
- **Professional concept represented:** break-retest-continuation, the
  standard trend-following institutional playbook, combined with Auction
  Market Theory's value-migration concept.

---

### Candidate C — Smart Money Zone / Value Area Confluence
**Families combined:** Zones + Volume Profile (required) → Order Flow + Structure (optional confirmation) — **4 families**

- **Institutional trading thesis:** smart-money price-action zones
  (Order Blocks/FVGs, built from swing and impulse geometry) and volume
  profile fair-value zones (built from traded volume distribution) are
  constructed from **methodologically unrelated data** — one from price
  geometry, one from volume distribution. They should rarely coincide by
  chance. When an active zone's price range genuinely overlaps the
  current Value Area or POC, that is agreement between two independent
  measurement methods, not two views of the same underlying fact.
- **Required conditions:** (1) first touch of an active Order Block or
  FVG zone; (2) that zone's `[zone_low, zone_high]` range geometrically
  overlaps `[value_area_low, value_area_high]` or sits within one bucket
  of `poc_price` (`volume_profile`).
- **Optional confirmations:** Order Flow absorption at the zone (CVD
  divergence, or low `delta_strength` indicating absorption rather than
  continuation); `market_structure` not contradicting the zone's
  direction.
- **Expected market regime:** agnostic; optional Structure confirmation
  narrows it.
- **Expected holding time:** short-medium.
- **Expected trade frequency:** low — geometric overlap between a zone
  and a value area is a fairly restrictive coincidence by construction.
- **Expected signal frequency:** low.
- **Expected overlap with S001–S006:** low. No existing setup
  cross-references Zones against Volume Profile; this is a genuinely
  distinct mechanism from anything tried so far.
- **Expected independent information gain:** uncertain, and this needs
  to be said plainly rather than talked up. Its two required families —
  Zones and Volume Profile alone — are the **two weakest-measured
  families in the library** (S002/S006 rejected, S003/S005 both merely
  archived, none approved). This candidate is a bet that combining two
  individually mediocre signals produces a strong one; nothing measured
  so far supports that, and this project's own methodology exists
  precisely to catch that kind of hopeful reasoning. It should be judged
  as a real but unproven idea, not a favorite.
- **Expected architectural complexity:** moderate-high — genuinely new
  geometric zone-vs-value-area overlap logic; no existing setup performs
  this kind of two-shape overlap arithmetic.
- **Why these families reinforce each other:** by construction, a
  price-geometry-derived zone and a volume-derived fair-value zone
  measure different things and should not agree unless something real is
  happening at that price.
- **Professional concept represented:** cross-methodology confluence —
  independent agreement between price-action and volume-based theories
  of value.

---

### Candidate D — Session Range Breakout with Cross-Asset Confirmation
**Families combined:** Sessions + Structure + Intermarket (required) → Volume Profile (optional confirmation) — **4 families**

- **Institutional trading thesis:** session-range breakouts (e.g. New
  York breaking the Asian range) are a standard institutional playbook,
  but a large fraction are false/manipulative single-asset moves.
  Requiring a correlated asset to not simultaneously contradict the
  breakout direction is meant to filter idiosyncratic, thin, one-asset
  moves from genuine market-wide expansion.
- **Required conditions:** (1) price closes beyond
  `sessions.previous_period_high_low` for the current session/day; (2) a
  fresh BOS confirms the same direction; (3) a configured correlated
  asset's `structural_divergence_flag` does **not** oppose the breakout
  direction (a "does not contradict" filter, deliberately not reusing
  S004's rejected "confirms" framing).
- **Optional confirmations:** the breakout level sits outside the
  current Value Area (range expansion, not rotation).
- **Expected market regime:** expansion/trending days only.
- **Expected holding time:** medium-long.
- **Expected trade frequency:** low.
- **Expected signal frequency:** low.
- **Expected overlap with S001–S006:** low — shares no required family
  with any existing setup.
- **Expected independent information gain:** this needs the same honesty
  as Candidate C's caveat, but sharper: this candidate's Intermarket
  condition reuses the **exact flag** (`structural_divergence_flag`)
  already measured in S004 to be satisfied on effectively 100% of real
  fires — i.e., proven to almost never say no. Reframing it as a "does
  not contradict" filter does not change the underlying flag's measured
  behavior; there is no evidence this reframing fixes the
  non-discrimination problem, only a hope that it might.
- **Expected architectural complexity:** the highest of the five, and
  for a reason worth stating plainly given this project's eventual live
  BTCUSDT goal: this is the only candidate whose **required** conditions
  depend on live multi-symbol synchronization at decision time. In
  backtesting, correlated-asset data is a convenience already wired up
  (Step 0 of an earlier phase). In live trading, it is a second live feed
  that must stay in sync, with its own failure modes — a real
  operational cost none of the other four candidates carry as a hard
  requirement.
- **Why these families reinforce each other:** Sessions and Structure
  jointly establish "did a genuine range expansion happen"; Intermarket
  is meant to independently establish "is this market-wide, not
  one-asset noise" — a legitimate institutional question, even though
  our current implementation of the answer is already in doubt.
- **Professional concept represented:** opening-range breakout with
  cross-market confirmation.

---

### Candidate E — Liquidity-Zone Termination Reversal
**Families combined:** Liquidity + Zones + Volume Profile (required) → Intermarket (optional, descriptive only) — **4 families**

- **Institutional trading thesis:** the most commonly cited "smart
  money" pattern in retail ICT literature — liquidity is run specifically
  to trigger stops sitting just beyond a pre-existing Order Block, FVG,
  or Breaker Block, funding entries into that zone before reversing.
  This is a strictly narrower, more specific criterion than S001's "any
  liquidity pool sweep."
- **Required conditions:** (1) a Liquidity Pool sweep that terminates
  (price reverses) specifically inside an already-active, opposing Smart
  Money Zone (Order Block/FVG/Breaker Block) — not just any sweep; (2)
  that zone sits near the prior period's POC (`volume_profile`), an
  independent "fair value magnet" confirmation, deliberately not CVD, to
  keep this candidate mechanistically distinct from S001.
- **Optional confirmations:** Intermarket structural agreement, recorded
  as descriptive evidence only — given S004's finding, this project does
  not propose it as a differentiator here.
- **Expected market regime:** agnostic.
- **Expected holding time:** short.
- **Expected trade frequency:** low — a joint sweep-and-zone-overlap
  event is rarer than a sweep alone.
- **Expected signal frequency:** low, a strict subset of S001's own
  already-rare fire population.
- **Expected overlap with S001–S006:** **high**, and this is this
  candidate's defining weakness, not a minor caveat. It is, in essence,
  "S001 with a Zone gate substituted for the CVD gate." The most likely
  outcome is that it captures a subset of trades S001 (already
  APPROVED) would have caught anyway, rather than surfacing new
  information — a real possibility, not assumed away.
- **Expected independent information gain:** low-to-moderate; the open
  empirical question ("does the zone-gate change the population in a
  way that matters") is legitimate, but modest in scope compared to the
  other four candidates.
- **Expected architectural complexity:** moderate — same geometric
  zone-overlap logic as Candidate C, between a swept Liquidity Pool and
  another active zone.
- **Why these families reinforce each other:** Liquidity identifies
  *that* a stop-run occurred; Zones identify *why* — a specific
  pre-existing institutional interest level; Volume Profile is an
  independent confirmation that the same area matters by a completely
  different (volume-based) measure.
- **Professional concept represented:** stop-hunt into a supply/demand
  zone.

---

## 3. Ranking

Ranked by the six stated criteria, in the priority order given (research
value → independent edge → architectural quality → institutional
validity → cross-asset robustness → lowest overlap):

| Rank | Candidate | Rationale |
|---|---|---|
| **1** | **B — Trend Continuation Confluence** | Only candidate directly answering an already-diagnosed failure (S002's OOS report). Fills a real, currently-empty gap in the library (zero validated continuation logic). Cheapest correct architecture of any 4-family candidate — three families are ready-made field reads. No live multi-symbol dependency. Its two required families (Structure, Liquidity) are the two with the best measured track record via S001. |
| **2** | **A — Session Liquidity Raid** | The only candidate testing the one completely unused family (Sessions). Strong, well-established institutional grounding. Moderate, honest complexity. Main caveat: crypto's 24/7 market may weaken session effects relative to FX/equities — a testable prediction, not a blocker. |
| **3** | **C — Smart Money Zone / Value Area Confluence** | Lowest overlap and a genuine methodological-independence argument, but built from the two weakest-measured families in the library. Legitimate to research, but should not be mistaken for a safe bet. |
| **4** | **D — Session Range Breakout w/ Cross-Asset Confirmation** | Novel combination, but its Intermarket condition reuses a mechanism already measured non-discriminating in S004, and it is the only candidate requiring live multi-symbol synchronization as a hard dependency — a real cost against the eventual single-asset live-trading goal. |
| **5** | **E — Liquidity-Zone Termination Reversal** | Most textbook-correct institutional pattern of the five, but the highest overlap with an already-APPROVED setup. Most likely outcome is a redundant subset of S001 rather than new information — the least efficient use of research effort. |

---

## 4. Final recommendation: build Candidate B (Trend Continuation Confluence) as S007

Implement B before any of the other four for four concrete reasons:

1. **It is hypothesis-driven, not speculative.** Every other candidate
   proposes a new combination and hopes it works. B is different: the
   out-of-sample validation report already told us why S002 failed
   (first-touch zone, zero context), and B is the direct, falsifiable
   test of that diagnosis. If B also fails despite adding exactly the
   context S002 lacked, that is itself a valuable, sharper finding about
   the limits of Liquidity-zone retests generally.

2. **It closes a real gap, not a redundant one.** S001, S003, S004, and
   S006 are all reversal-type. The library has never validated a single
   continuation setup — S002 was the one attempt and it failed. A future
   Portfolio Decision Engine needs setups that behave differently across
   regimes; an all-reversal library cannot supply that on its own.

3. **It is the cheapest of the five to build without cutting corners.**
   Three of its four families are already-computed fields requiring zero
   new arithmetic; the one new mechanism (fresh-BOS + subsequent zone
   retest) recombines two techniques already validated elsewhere in this
   codebase (S004's timestamp-freshness check, S002/S006's first-touch
   check) rather than inventing new detection logic.

4. **It carries no new operational risk toward the live-trading goal.**
   Unlike D, it has no live multi-symbol dependency. Unlike D, it does
   not lean on the one mechanism (Intermarket structural-divergence
   flags) already measured to be non-discriminating.

Candidates A and C remain reasonable next steps after B completes its
research cycle — A specifically because Sessions remains completely
untested, C because its cross-methodology argument is legitimate even
though its ingredients are individually weaker. D and E are not
recommended for near-term implementation: D reuses a mechanism already
shown not to work, and E's most likely outcome is redundancy with an
already-approved setup rather than new information.

No code has been written. No setup has been implemented. This document
is a proposal for Step 2 (implementation) to act on, pending explicit
direction to proceed.
