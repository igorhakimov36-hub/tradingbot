# Phase 4 — Setup Library Expansion
## Research & Design Only — No Code, No Backtests

This document is Step 1-3 of the requested research task: repository
capability inspection, 4 candidate setups, and a ranked recommendation.
**Nothing has been implemented.** No file outside `docs/` was touched
to produce this document, and no backtest was run.

---

## STEP 1 — Repository & Capability Inspection

### 1.1 Precise logic of S001, S005, S007 (re-verified against current source, not memory)

**S001 — Liquidity Sweep Reversal** (`strategy/setups/liquidity_sweep_reversal.py`, APPROVED)
Required: (1) a Liquidity Pool zone resolved as `swept` with `resolved_at`
equal to the current bar (a fresh sweep), (2) any configured CVD anchor
shows `cvd_exhaustion_flag`/`price_cvd_divergence_flag` agreeing with
the inferred reversal direction, (3) at least one of three additional
confirmations (CHOCH agreement, the swept pool having >1 contributing
source, SMT agreement) — this third gate was added after controlled
experimentation, not part of the original design. Direction: sweeping
a buy-side pool (built from highs) → SHORT; sell-side → LONG. Stop:
the swept pool's own zone edge.

**S005 — Fair Value Gap Rebalance** (`strategy/setups/fair_value_gap_rebalance.py`, RESEARCH ARCHIVE, best standalone PF 0.992)
Required (single condition, no confirmation gate): an active FVG zone
with `resolution_detail == "partially_filled"` AND price currently
`inside_price`. Direction from the gap's own `direction` field
(bullish → LONG). Two optional, non-gating evidences (another
overlapping same-direction FVG; an overlapping same-direction Order
Block). **No CVD, no structure requirement, no displacement filter, no
frequency limiter beyond the zone's own lifecycle** — this absence is
exactly why it fires 70-130+ times/month in every window tested in
this project (see Exit Management Sprint results) and dominates the
one-trade-at-a-time slot.

**S007 — Trend Continuation Confluence** (`strategy/setups/trend_continuation_confluence.py`, PENDING)
Required: (1) an active, never-swept Liquidity Pool zone of the
trend-matching side currently `inside_price`, (2) `structure.bos` is
`BULLISH_BOS`/`BEARISH_BOS` (level-based, persists as long as the
break holds). Optional: Value Area overlap, CVD direction agreement.
Fires 2-4 times/month standalone in both tested windows — too rare to
draw conclusions from, confirmed in this project's own prior report.

### 1.2 Point-in-time-safe features confirmed available today

Verified by reading the tracker/coordinator/snapshot code directly,
not assumed:

| Family | Fields confirmed available via `MarketIntelligenceSnapshot` |
|---|---|
| Zones | FVG, Order Block (incl. `impulse_strength` — furthest favorable excursion since creation, ATR-at-creation-normalized; `mitigation_zone_high/low` — the origin candle's BODY, a tighter sub-zone than the wick range), Breaker Block, Liquidity Pool (incl. `sweep_penetration`/`sweep_rejection` in ATR units) |
| Levels | Equal Highs/Lows, Session High/Low (previous CLOSED period only), POC/VAH/VAL/HVN/LVN |
| Order Flow | Delta (`delta_strength`, `delta_direction`, bar-level), CVD (`cvd_direction`, `cvd_exhaustion_flag`, `price_cvd_divergence_flag`, anchored or continuous) |
| Structure | `market_structure` (BULLISH/BEARISH/RANGE/UNKNOWN), `bos`, `choch`, `last_swing_high/low` — all level-based (persist while true), not edge-triggered |
| Sessions | `active_now`, `previous_period_high_low` — thin, used by zero existing setups |
| Volume Profile (raw) | `poc_shift_from_previous_period`, `value_area_overlap_ratio`, `bucket_size`, histogram — richer than the Levels mapping |
| Intermarket/SMT | Correlation, structural divergence — **already proven non-discriminating** (S004 REJECTED: its flags satisfied ~100% of real fires) |

**Real order-flow data confirmed, not assumed:** checked
`data/BTCUSDT-1m-2024-01.csv` directly — `taker_buy_volume` is present
and is genuine exchange data (Binance Vision), not synthetic. Delta/CVD
rest on real data.

### 1.3 Inputs unavailable or unreliable today

| Input | Status |
|---|---|
| Funding rate | Real historical data exists (`data/BTCUSDT-funding-2024-*.csv`, full coverage), but **no tracker or snapshot field consumes it**. A generic `PointEventProvider` exists at the `BacktestRunner` harness level (attachable via `provider_specs`), but nothing turns it into Market Intelligence. **Requires new infrastructure** (a tracker + a new snapshot field) before any setup could use it. |
| Open Interest | Data exists only as `BTCUSDT-open_interest-recent30d.csv` — a **rolling 30-day snapshot that does not cover 2024-01 or 2025-03**, the two windows this project's every prior report has used. Same missing-tracker gap as funding, plus insufficient historical range for comparable testing. **Do not build on this without first downloading full historical OI and adding a tracker.** |
| Liquidations, order-book depth, footprint | No data of any kind exists in this repository. **Not available at all** — any setup requiring these must be deferred entirely. |
| VWAP with deviation bands | No tracker computes a running/anchored VWAP. Volume Profile's POC/Value-Area is the closest existing proxy (a volume-weighted "fair value" concept, though methodologically distinct from a true VWAP). Any "extension from value" candidate below is built on Volume Profile, not VWAP, and this substitution is disclosed rather than hidden. |
| ATR | `AverageTrueRangeTracker` **exists in code** (`strategy/features/utils.py`) but is **not wired into `MarketIntelligenceCoordinator` or the Snapshot** — invisible to any Setup today. Cheaper to fix than the funding/OI gap (no new tracker needed, just wiring), but still not currently available. Order Block's own `impulse_strength` and `atr_at_creation` fields are the only ATR-normalized values a Setup can read today, and only in the context of an Order Block's own lifecycle. |

### 1.4 Underrepresented market regimes

- **Every existing setup is reversal-type except S007** (continuation),
  and S007 fires too rarely to matter. There is still no validated
  continuation exposure in the portfolio.
- **No setup requires or is gated by a specific volatility or trend
  regime.** `structure.market_structure` (BULLISH/BEARISH/RANGE) is
  read only as optional context by the backtest adapter for post-hoc
  reporting — never as a firing condition. A RANGE-specific setup does
  not exist.
- **No setup implements a breakout mechanic.** S007 requires an
  *already-established* trend (BOS already active) and a retest of an
  existing zone — it does not trade the breakout moment itself. Nothing
  in the library trades "price just left an established range/session
  boundary and is retesting it."
- **Sessions is completely unused** as a required condition by any of
  S001-S007 (confirmed in the Phase 3 document already produced this
  project).
- **Volume Profile has never been used for a deviation/extension-based
  mean-reversion thesis** — S003 (archived) used HVN *reaction*, with
  no regime gate and no magnitude requirement; nothing fades a
  statistically extended move away from value.

### 1.5 Overlap map for anything proposed

- Anything built on Liquidity Pool zones will structurally overlap
  with S001 unless required-condition wiring genuinely differs (S001
  requires a *swept* pool; a pool that is *active and unswept* is a
  disjoint population, as S007 already demonstrated).
- Anything built on Order Block zones without a magnitude/context
  filter risks being S002 again (a setup this project's own OOS report
  already showed fails from exactly that omission).
- Anything requiring Intermarket/SMT as a hard gate reuses a mechanism
  already measured non-discriminating (S004) — usable only as
  descriptive/optional evidence, never a required gate, without new
  justification this project doesn't have.
- FVG zones without a magnitude or confirmation filter risk
  reproducing S005's own high-frequency, portfolio-damaging behavior.

---

## STEP 2 — Four Candidates

### Candidate 1 — S008: Displacement-Impulse Continuation
**Category:** Trend continuation following institutional displacement and a controlled pullback.

1. **Hypothesis:** An Order Block whose subsequent favorable excursion
   (`impulse_strength`) has already exceeded its own creation-time ATR
   represents genuine institutional displacement — inventory was
   built and the market has already validated it with real distance
   travelled, not just a structural break. A first retracement into the
   ORIGIN candle's body (the tighter `mitigation_zone`, not the full
   wick) offers a defined re-entry into that same participation, with
   order-flow confirming continued (not exhausted) pressure.
2. **Regime:** Active only where `impulse_strength >= 1.0` exists on a
   still-active Order Block — implicitly trend-active by construction.
3. **Inactive when:** no Order Block currently has `impulse_strength >= 1.0`;
   the Order Block's mitigation zone has already been fully mitigated
   (moved to the resolved list); `touch_count != 1` (not the first
   revisit — reuses the exact field OB Continuation already exposes).
4. **Point-in-time signal sequence:** (a) an Order Block exists with
   `impulse_strength >= 1.0` at the moment of evaluation (a value the
   tracker already updates every bar from already-closed history), (b)
   price is currently inside that block's `mitigation_zone` range, (c)
   `mitigation_zone_status == "active"` (not yet fully mitigated), (d)
   `touch_count == 1` on the PRIMARY zone (first revisit).
5. **Entry trigger:** all of (4) true on the current bar's close.
6. **Stop-loss:** the primary Order Block's own `zone_low`/`zone_high`
   (the full wick range, one level looser than the mitigation-zone
   entry) — the level at which the displacement thesis itself, not
   just the tighter body-zone, is falsified. Fixed at entry, from an
   already-closed candle's data — no future-candle dependency.
7. **Take-profit:** fixed 2R, matching every existing setup's control
   convention, so a future A/B against fixed exits is comparable
   without conflating two changes at once.
8. **Required data:** Order Block tracker fields only (`impulse_strength`,
   `mitigation_zone_*`, `touch_count`) — all confirmed available today.
   Optional CVD confirmation (`cvd_direction` agreeing with the OB's
   direction) — confirmed available.
9. **Expected frequency:** low. `impulse_strength >= 1.0` is a real
   filter on top of every Order Block that forms (most will not reach
   a full ATR of favorable excursion before being retested) — plausibly
   2-8 trades/month on 15m BTCUSDT, not measured.
10. **Expected holding time:** medium — a continuation trade targeting
    a fresh 2R beyond an already-displaced move; comparable to S007's
    observed 2-6 hour range, not verified.
11. **Overlap:** shares the Order Block zone family with S002 (rejected)
    but requires the two conditions (impulse filter, mitigation-zone
    entry) S002 never had — S002's own OOS failure is the direct
    motivation. Zero required-family overlap with S001 (no Liquidity
    Pool) or S005 (no FVG). Shares "BOS-adjacent, continuation" framing
    with S007 conceptually but uses a completely different zone/field
    set (no Liquidity Pool, no raw `bos` read — displacement is
    measured on the Order Block itself, not the swing structure).
12. **Failure modes:** `impulse_strength` grows unbounded per its own
    docstring ("never capped, unlike mitigation_pct") — a very old,
    long-since-irrelevant Order Block could still show a high value
    from a move long past; needs an age/staleness bound decided at
    implementation time, not tuned on 2024-01/2025-03. False positives:
    a displaced move that was itself a blow-off top/bottom, where the
    "continuation" retest is actually the start of a reversal.
13. **Look-ahead/repainting:** none identified — `impulse_strength` is
    computed from already-closed history each sync() call (matching
    the tracker's own documented replay-safety), and the mitigation
    zone's edges are fixed at the origin candle, a past bar. Standard
    same-bar stop/target ambiguity only (already handled by
    `ExecutionSimulator`'s existing `STOP_LOSS_AMBIGUOUS` convention).
14. **Minimum tests required:** unit tests for the impulse-filter
    boundary (exactly 1.0, just below, just above), mitigation-zone
    vs. full-zone stop distinction, touch-count gating (0/1/2+), CVD
    optional-evidence independence; a real-data replay-safety run
    confirming `impulse_strength` never uses a future candle; a
    determinism run; full-suite zero-regression.
15. **Falsification:** if out-of-sample profit factor stays below 1.0
    across two independent windows the way S002/S006 did, or if the
    "genuine displacement" filter shows no measurable difference from
    an unfiltered Order Block Continuation re-run, archive or reject.

### Candidate 2 — S009: Failed Auction Reversal at the Value Area Boundary
**Category:** Liquidity sweep / failed auction reversal.

1. **Hypothesis:** Auction Market Theory: an excursion beyond the
   current period's Value Area that fails to build new acceptance
   (closes back inside within one bar) with WEAKER participation on
   the excursion than on the rejection is evidence the attempted
   range extension was not supported by real transactional interest —
   a structurally different claim from S001's "resting orders were
   triggered," even though the surface pattern (poke-and-reject) looks
   similar.
2. **Regime:** value-area-defined markets — most naturally RANGE, but
   not regime-gated by construction (the failure condition is
   self-selecting: a trending market rarely produces a value-area
   excursion that fails).
3. **Inactive when:** no current-period Value Area exists yet (early in
   a session, `current_forming_profile` absent); the excursion bar
   closes BEYOND the boundary (a genuine breakout, not a failure —
   explicitly the complement of Candidate 3 below, never both true on
   the same bar by construction).
4. **Point-in-time signal sequence:** (a) bar N's high exceeds
   `value_area_high` (SHORT case; mirror for LONG/`value_area_low`),
   (b) bar N's own close is back at or below `value_area_high` (the
   excursion failed within the same bar it occurred — no future bar
   needed), (c) bar N's `delta_strength` is less than bar N's own
   directional-opposite requirement is not applicable here since it is
   one bar — instead: the FIRST subsequent bar (N+1) that itself closes
   further in the reversal direction must show `delta_strength` greater
   than bar N's `delta_strength` (a plain numeric comparison between
   two already-closed bars' own fields, no invented magnitude).
5. **Entry trigger:** condition (4)(c) confirmed on bar N+1's close.
6. **Stop-loss:** bar N's own high (SHORT) / low (LONG) — the
   excursion extreme itself, already a closed, past value by the time
   of entry on bar N+1.
7. **Take-profit:** fixed 2R (control-comparable, as in Candidate 1).
8. **Required data:** Volume Profile (`value_area_high/low`, confirmed
   available), Delta (`delta_strength`, confirmed available, real
   data). No new infrastructure needed.
9. **Expected frequency:** low-moderate — a value-area excursion is
   common, but the same-bar-failure-then-weaker-momentum condition is
   restrictive; not measured, plausibly comparable to or rarer than S001.
10. **Expected holding time:** short — this is an intrabar/next-bar
    reversal thesis, plausibly shorter than S001's observed ~4 hours.
11. **Overlap:** no Liquidity Pool dependency at all — zero required-
    family overlap with S001. Distinguishing mechanism (participation
    comparison between two specific bars, not a pool-sweep event) is
    genuinely different, but this must be measured, not assumed — flagged
    explicitly as the candidate most likely to *behave* similarly to
    S001 even though it is *mechanistically* distinct, since both are
    "poke-and-reject" reversal theses at bottom.
12. **Failure modes:** `delta_strength` is a single-bar measure with no
    smoothing — noisy by construction; a large excursion bar with
    naturally high volume could trivially have higher delta_strength
    than a quiet reversal bar even when the reversal is real, inverting
    the intended read. This needs to be watched for directly in real
    data, not assumed away.
13. **Look-ahead/repainting:** entry uses bar N+1's own close and
    delta_strength — both known only once bar N+1 has closed, and the
    entry decision happens at that same close, consistent with every
    existing setup's convention (decide on a bar's own close, using
    only that bar and earlier). No retroactive test-window use.
14. **Minimum tests required:** unit tests for the same-bar-failure
    condition, the two-bar delta_strength comparison (both directions),
    the "no acceptance yet" inactive case, determinism, replay safety,
    full-suite regression.
15. **Falsification:** if the delta_strength comparison shows no
    measurable difference from a random/no-filter baseline in real
    data (a natural first control experiment once implemented), or if
    OOS profit factor stays below 1.0 across two windows.

### Candidate 3 — S010: Session Range Breakout with Value Area Acceptance Retest
**Category:** Confirmed breakout and retest with participation/acceptance evidence.

1. **Hypothesis:** A clean breakout of a prior closed session's range,
   followed by a retest that HOLDS (does not close back beyond the
   broken level) while the new period's own Value Area has already
   migrated to fully sit on the breakout side, is auction-market
   evidence that the market has already re-priced fair value beyond
   the old range — not merely that price touched a new extreme.
2. **Regime:** expansion/trending only, self-selecting by construction
   (a range-bound market does not produce this sequence).
3. **Inactive when:** no closed prior-session high/low exists yet;
   the retest bar closes back beyond the broken level (the breakout
   has failed — this candidate does not fire on a failed breakout,
   Candidate 2 addresses failure, not this one).
4. **Point-in-time signal sequence:** (a) some prior bar M closed
   beyond `previous_period_high_low[session].session_high` (SHORT
   mirrors `session_low`) — a genuine breakout event, (b) the CURRENT
   bar retraces to touch that same level (`zone`-style containment:
   current price within a small, tracker-native tolerance is not
   available for a Level, so this uses direct price comparison against
   the fixed `session_high` value, not an invented buffer — current
   bar's low <= session_high <= current bar's high, for the SHORT
   case direction reversed) without closing back below it, (c) the
   CURRENT forming period's `value_area_low` (LONG) / `value_area_high`
   (SHORT) is at or beyond the broken level — the new value area has
   fully migrated past it, a structural containment test, not a
   magnitude threshold.
5. **Entry trigger:** all of (4) true on the retest bar's close.
6. **Stop-loss:** the broken session's own `session_high`/`session_low`
   value, adjusted by the same small fixed buffer convention already
   used elsewhere in this codebase (`STOP_BUFFER_PCT`) — a fixed,
   already-established constant, not a new invented one.
7. **Take-profit:** fixed 2R.
8. **Required data:** Session Boundaries (`previous_period_high_low`,
   confirmed available, currently unused by any setup), Volume Profile
   (`value_area_low/high`, confirmed available). No new infrastructure.
9. **Expected frequency:** low — requires a specific 3-part sequence
   (breakout, retest-hold, value migration) across potentially many
   bars; plausibly the rarest of the four candidates, likely comparable
   to or rarer than S007's 2-4/month.
10. **Expected holding time:** medium-long — breakout-continuation
    trades typically run further than reversal trades.
11. **Overlap:** the only candidate requiring Sessions as a hard gate —
    zero required-family overlap with any existing setup. Conceptually
    adjacent to S007 (both continuation-flavored) but S007 requires an
    *already-active* BOS and a Liquidity Pool retest; this requires a
    *specific session-boundary break event* and Volume-Area migration,
    with no BOS or Liquidity Pool read at all.
12. **Failure modes:** the breakout event (a) may be arbitrarily far in
    the past by the time a qualifying retest occurs — needs a bounded
    lookback decided at implementation, not fit to 2024-01/2025-03;
    thinly-traded sessions (e.g., low-volume periods) may produce
    spurious "breakouts" of a session range that was never meaningful.
13. **Look-ahead/repainting:** the breakout bar M is always a past,
    already-closed bar relative to the retest bar being evaluated — no
    future data used. The "value area migration" read uses the
    CURRENT forming period's own already-computed VAL/VAH at decision
    time, consistent with how every existing Volume-Profile-reading
    setup already works.
14. **Minimum tests required:** unit tests for the 3-part sequence
    (breakout detection, retest-without-failure, value migration),
    the bounded-lookback boundary, both directions, determinism,
    replay safety (specifically: confirm the "some prior bar M"
    lookback never scans beyond point-in-time-visible history),
    full-suite regression.
15. **Falsification:** if the required 3-part sequence essentially never
    co-occurs in real 15m BTCUSDT data (a real risk given its
    restrictiveness — worth checking signal frequency alone before
    investing in full backtesting), archive as "needs more data" rather
    than reject; if it fires often enough to test and underperforms
    OOS, reject.

### Candidate 4 — S011: Value Area Extension Fade (RANGE regime)
**Category:** Mean reversion after statistically abnormal extension from value.

1. **Hypothesis:** In an established RANGE regime (no active BOS,
   `market_structure == "RANGE"`), a price extension beyond the current
   Value Area by a multiple of the profile's own bucket resolution,
   with order flow already showing exhaustion, is evidence the auction
   has over-extended relative to where two-sided trade has actually
   occurred — a reversion-to-value thesis, explicitly NOT attempted in
   a trending regime, where fighting the trend would be the wrong side
   of a real institutional flow.
2. **Regime:** RANGE only — the only candidate of the four with an
   explicit, hard regime gate using an already-computed field
   (`structure.market_structure`) never used as a gate by any existing
   setup.
3. **Inactive when:** `market_structure != "RANGE"`; no
   `current_forming_profile` exists yet.
4. **Point-in-time signal sequence:** (a) `structure.market_structure == "RANGE"`,
   (b) current price is beyond `value_area_high` (SHORT) /
   `value_area_low` (LONG) by at least 3x the current profile's own
   `bucket_size` — a unit-based, tracker-native multiple, not an
   invented absolute number (mirrors S003's own "same bucket" precedent
   for avoiding invented tolerances), (c) any configured CVD anchor
   shows the exhaustion flag agreeing with a reversion (price extended
   up, CVD shows bearish exhaustion, and the mirror).
5. **Entry trigger:** all of (4) true on the current bar's close.
6. **Stop-loss:** current price at signal time, offset by one further
   `bucket_size` multiple beyond the entry (e.g., entry level + 1
   bucket for a SHORT) — reusing the tracker's own resolution unit for
   the stop distance too, not an invented percentage.
7. **Take-profit:** the current period's own `poc_price` — the
   auction's actual point of control, a real structural target rather
   than a fixed 2R (disclosed as a deliberate deviation from the
   "fixed 2R for comparability" convention used in the other three
   candidates, because "reversion to value" is specifically a
   reversion-to-POC thesis — the take-profit target IS the hypothesis).
8. **Required data:** Structure (`market_structure`, confirmed
   available, never previously used as a gate), Volume Profile
   (`value_area_high/low`, `bucket_size`, `poc_price`, confirmed
   available), CVD exhaustion flag (confirmed available). No new
   infrastructure — this candidate uses ONLY already-wired fields,
   explicitly avoiding the ATR/VWAP gap identified in Step 1.
9. **Expected frequency:** moderate — RANGE regimes are common on 15m
   BTCUSDT, and a 3-bucket extension is a real but not rare event;
   plausibly the highest-frequency of the four candidates, needing its
   own frequency check against the S005 lesson (a magnitude filter
   already built in via the 3-bucket requirement, unlike S005's
   single, unfiltered zone-touch condition).
10. **Expected holding time:** short — a reversion-to-POC trade within
    an established range should resolve faster than a trend trade.
11. **Overlap:** shares Volume Profile with S003 (archived) and S005
    (optional evidence only) but is the only setup requiring a RANGE
    regime gate and an extension MAGNITUDE, neither of which S003 ever
    had (S003 required only HVN reaction, any regime, any distance).
12. **Failure modes:** `market_structure`'s own docstring already
    flags it as "a crude two-adjacent-candle heuristic" — a real,
    disclosed limitation this candidate inherits directly, not newly
    introduced; a range that is about to break (regime label lagging
    reality) would fade directly into a real breakout.
13. **Look-ahead/repainting:** none — all fields read are already-
    computed as of the current bar's close, matching every other zone/
    level-reading setup's established, already-validated pattern.
14. **Minimum tests required:** unit tests for the RANGE gate (present/
    absent), the 3-bucket boundary (exactly at, just under, just
    over), POC-based take-profit construction, CVD exhaustion-flag
    gating both directions, determinism, replay safety, full-suite
    regression.
15. **Falsification:** if `market_structure`'s known crudeness causes
    this to fire predominantly right before real breakouts (measurable
    directly: check how often a fade's stop is hit vs. its target
    within N bars of a subsequent real BOS), reject regardless of raw
    profit factor — that would indicate the regime gate itself is
    unreliable, a more fundamental problem than a bad parameter.

**Design-restriction compliance, stated plainly for all four:** every
threshold above is either a natural unit already computed by an
existing tracker (`impulse_strength >= 1.0`, `bucket_size` multiples)
or an existing fixed constant already used elsewhere in this codebase
(`STOP_BUFFER_PCT`, fixed 2R) — none were chosen by looking at
2024-01 or 2025-03 results, and none exist yet as tested code. Every
"cooldown"/event-consumption requirement is satisfied the same way
every existing setup already satisfies it: through the underlying
zone/level's own lifecycle (a mitigated Order Block, a filled FVG, a
swept pool moves out of the active/eligible population permanently) and
`BacktestRunner`'s existing one-trade-at-a-time capacity — **not** by
adding state to a `Setup`, which `strategy/setups/base.py`'s own
protocol explicitly forbids ("no internal state carried between
calls"). No new setup-side state is proposed anywhere above.

---

## STEP 3 — Ranking and Recommendation

| Criterion | S008 Displacement | S009 Failed Auction | S010 Breakout+Retest | S011 Value Fade |
|---|---|---|---|---|
| Economic rationale | Strong (reuses a real, already-computed displacement measure) | Strong (genuine AMT concept) | Strong (standard institutional playbook) | Strong (classic reversion-to-value) |
| Complementarity | High (fills continuation gap left by S007's rarity) | Medium (reversion-flavored like S001) | High (fills the completely-empty breakout category) | High (fills the completely-empty RANGE category) |
| Data availability | Confirmed, no new infra | Confirmed, no new infra | Confirmed, no new infra | Confirmed, no new infra, avoids the ATR/VWAP gap entirely |
| Expected sample size | Low-moderate | Low-moderate | **Likely very low — real risk** | Moderate-high (needs its own frequency check) |
| Implementation complexity | Low (reuses existing OB fields directly) | Moderate (new cross-bar delta comparison) | **High (3-part sequence, unbounded-lookback risk)** | Low-moderate (single-bar gate + magnitude) |
| Look-ahead risk | Low | Low | Low, but the lookback-bound decision needs care | Low |
| OOS survival probability (informed guess, not a claim) | Moderate | Moderate | Low (may simply not fire enough to test) | Moderate |

### Recommended build order: **S008 → S011 → S009**

- **S008 (Displacement-Impulse Continuation) first.** Cheapest to
  build correctly (every field it needs already exists on the Order
  Block tracker, no new cross-bar logic), directly answers the same
  diagnosed gap S007 was built to answer but through an entirely
  different mechanism (magnitude-filtered Order Block, not
  Liquidity-Pool retest) — genuinely complementary to S007 rather than
  redundant with it, and gives the continuation category a second,
  differently-constructed data point.
- **S011 (Value Area Extension Fade) second.** Fills the one regime
  (RANGE) nothing in the library currently addresses at all, uses only
  already-wired fields, and its expected frequency is the most likely
  of the four to actually produce a testable sample size — directly
  addressing this project's stated concern about S007's untestable
  rarity.
- **S009 (Failed Auction Reversal) third.** Sound economically, but
  explicitly flagged as the candidate most likely to *behave* similarly
  to S001 even though its trigger mechanism differs — worth building
  only after S008/S011 to see whether the portfolio still needs a third
  reversal-flavored setup once real numbers are in.

### Not recommended for now: **S010 (Session Range Breakout with Value Area Acceptance Retest)**

This is the strongest *economic* idea of the four — a genuine breakout
mechanic is a real, currently-empty gap — but it is explicitly flagged
as attractive-but-risky given this repository's current data: the
3-part sequence (breakout, then a later retest, then value migration)
is the most restrictive of anything proposed, the "how far back may
the breakout event M be" question has no natural, non-arbitrary answer
without risking a fitted parameter, and there is a real chance it
produces too few signals to certify at all — the same failure mode
already observed with S007. Recommend revisiting only after S008/S011
results are in and the value of a third or fourth setup is reassessed
against real portfolio-capacity data (the S002/S005 crowding lesson
this project already learned directly).

### Proposed validation plan (once approved to implement)

1. Step 0 architecture check per setup (confirm every field used truly
   requires no tracker/Snapshot/Engine change — expected to pass
   cleanly for all three recommended candidates given Step 1's audit).
2. Implement + full unit test suite per setup, in the recommended order.
3. Real-data replay safety / determinism / no-lookahead verification
   per setup (same protocol as every setup in this project).
4. **Signal-frequency check FIRST, before any performance backtest** —
   run each new setup standalone across a window NOT used for any
   threshold decision above, and confirm it fires often enough to be
   worth backtesting at all (directly targets the S007/S010-risk
   lesson).
5. Only then: initial A/B/C-style backtests (setup alone; combined with
   the current portfolio; full portfolio) — using windows chosen the
   same documented-random way as before, and only after all thresholds
   above are frozen from Step 2, never adjusted afterward.
6. Full certification (multi-asset, multi-window OOS) only for
   candidates that clear the initial checks — matching this project's
   existing S001-S007 methodology exactly.

**No code has been written. No backtest has been run. Waiting for
approval before Step 0 of implementation begins on the recommended
order (S008, then S011, then S009).**
