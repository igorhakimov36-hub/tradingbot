# SOLUSDT Strategy and Edge — Strategic Review

**Status: research closure, repository/report inspection, and public-source
research only. No production change, no new backtest, no subscription,
no data purchase, no exchange integration was performed to produce this
document.** No new outcome data was accessed — every SOL/BTC number
cited below comes from already-completed, already-reported TRAIN-tier
research; FINAL_HELD_OUT (2025-02, 2025-07) remains untouched.

## Lead summary

1. **Current system assessment**: S001 (Liquidity Sweep Reversal) is
   the only setup with meaningful SOL TRAIN evidence, and that evidence
   is currently negative (61 trades, 36.1% win rate, PF 0.85, −$672.92,
   expectancy −$11.03 per trade, pooled across 4 TRAIN months). Five
   dedicated research sprints (lifecycle policy, staleness, geometry,
   touch/volume, CVD/Delta) exhaustively tested the Liquidity Pool
   feature and S001's own CVD gate and found no promotable improvement
   and no confirmed defect. The infrastructure itself (replay safety,
   cost modeling, aggregation) is unusually well-audited and trustworthy.
2. **Main evidence gap**: not "we haven't found the edge yet" in a
   generic sense — it is that **every sub-population of S001 tested so
   far on SOL TRAIN sits at a raw favorable rate within a few points of
   50%, at trade counts (25–465 per hypothesis) too small to distinguish
   a real, small edge from noise, while the one architecture choice most
   likely to be actively *hurting* selection (the multi-source
   confirmation gate) has never itself been tested against a
   round-number-aware alternative.**
3. **Ranked hypotheses** (below): (1) round-number-conditional
   confirmation gating, (2) regime-conditional reversal thesis, (3) a
   derivatives-information route (forced-liquidation behavior),
   explicitly scoped as prospective-collection-only given verified data
   availability limits.
4. **Additional paid data**: **not justified yet.** Verified
   public-documentation research (Section 4) found no vendor with
   *confirmed* historical liquidation-event depth matching our TRAIN
   months at any price, and Binance's own market-wide liquidation feed
   is forward-only (no historical REST backfill at all, at any price).
5. **One recommended next action**: re-analyze the already-collected
   S001 CVD-blind candidate population (from the completed CVD
   signal-value sprint) conditioned on Liquidity Pool source
   (round-number-only vs. other), asking whether S001's own multi-source
   confirmation requirement is net-helping or net-hurting. This is
   the cheapest possible next step (a re-analysis of existing data, not
   a new backtest) and targets the most concrete, already-evidenced lead
   in this review.

---

## 1. Assessment of the current system

### 1.1 What has actually been measured on SOL

Every SOL-TRAIN number below is a report finding, not a new measurement
made for this review.

| Source | Population | n | Win rate | PF | Net P&L | Expectancy |
|---|---|---|---|---|---|---|
| CVD signal-value ablation, control (real S001) | 4 TRAIN months, exact linkage | 61 | 36.1% | 0.85 | −$672.92 | −$11.03 |
| Same, CVD-neutral variant | same months, CVD gate removed | 455 | 35.2% | 0.83 | −$5,504.22 | −$12.10 |
| Touch/Volume sprint, S001 source cross-reference | round-number-only trades | 29 | 41.4% | — | +$144.01 | +$4.97 |
| Same, non-round-number trades | 32 | 31.2% | — | −$816.92 | −$25.53 |

**S001's raw, unfiltered TRAIN performance is negative**, and it has
been negative across every research angle this project has taken on it
(lifecycle policy variants, sweep geometry, touch count, volume,
divergence/exhaustion). This is not a single disappointing run — it is
the consistent output of five independently-designed, pre-registered
TRAIN sprints, each of which asked a genuinely different question and
each of which returned `KEEP CURRENT` / `DO NOT PROMOTE` / `INCONCLUSIVE`
rather than a promotable improvement. That consistency is itself
evidence: it is much more likely that S001's core entry thesis, as
currently gated, has no easily-discoverable edge in this feature space
than that five different well-designed experiments all missed the same
real effect by bad luck.

### 1.2 Interpreting the CVD ablation precisely (61 vs. 455 trades)

The instruction to interpret this precisely is well-placed — it is easy
to over-read. What the numbers show and do not show:

- **Aggregate net P&L (−$672.92 vs. −$5,504.22) is arithmetic, not
  evidence of filtering quality.** 455 trades at roughly the same
  per-trade expectancy as 61 trades will always sum to a much larger
  loss. This comparison alone proves nothing about whether CVD is
  adding value.
- **The comparison that actually bears on filtering quality is
  per-trade, risk-normalized, and matched by pool**: SHARED trades (the
  56 pools both variants agreed on) had the best win rate (37.5%) and
  PF (0.92) of any subgroup; NEUTRAL-ONLY trades (399 pools CVD would
  have blocked) had a slightly worse win rate (34.8%) and PF (0.81).
  This is a real, if very weak (2.7-point win-rate gap, well within
  noise at n=399 vs. n=56), signal *in favor* of the gate doing
  something.
- **This is in direct tension with the module-level finding for the
  same underlying fields**: `price_cvd_divergence_flag` CONFIRMS
  candidates underperformed both CONTRADICTS and NEUTRAL candidates at
  the pooled directional level (44.7% vs. 50.0% vs. 47.8%) — a signal
  *against* the gate's value, on a larger (n=465) though still modest
  population.
- **Both directions of evidence are weak enough that neither should be
  acted on alone.** The honest reading is: **the CVD gate's net effect
  on trade quality is not established in either direction** — it
  measurably reduces trade count (a real, direct effect, confirmed via
  the CVD-neutral subclass ablation) without measurably improving or
  worsening per-trade quality at TRAIN sample sizes. "Frequency
  reduction without demonstrated quality improvement" is a materially
  different, more precise conclusion than either "the filter works" or
  "the filter doesn't work."
- **Path dependency was checked and is not the explanation**: only 4 of
  403 non-shared trades were attributable to the single-open-position
  engine's slot contention rather than direct CVD filtering (verified
  directly in the completed report, Section 8) — the 7.5× trade-count
  difference is a clean measurement of the gate itself.

### 1.3 Ranking the candidate explanations for the profitability gap

Separating demonstrated findings from plausible-but-unmeasured
explanations, using the option list provided:

| Explanation | Status on SOL | Evidence |
|---|---|---|
| **Entry selection** | **Demonstrated primary issue** | S001's raw favorable rate sits at ~50% across every tested sub-population (Population A native events: 48.0–50.3%; Population B CVD-blind candidates: 44.7–51.2% by field/verdict) — a near-coin-flip *before* costs, on the setup's own core thesis (sweep + CVD + evidence-count) |
| **Redundant confirmations** | **Demonstrated, specific mechanism identified** | S001's own multi-source confirmation requirement structurally discriminates against round-number-sourced pools (47.5% of S001 trades vs. 94.4% of the underlying pool population are round-number-only) — and the limited SOL sample shows round-number trades outperforming, not underperforming, non-round-number trades (41.4% vs. 31.2% win rate, n=29/32). The confirmation gate may be filtering for the wrong thing. |
| **Insufficient/restricted opportunity frequency** | **Demonstrated constraint on what can be concluded, not itself a cause of unprofitability** | 61 trades across 4 months (~15/month) is consistent with the BTC investigation's own finding (10–13 trades/month for S001) — this bounds statistical power severely; it does not by itself explain a *negative* result (a low-frequency setup can still have positive expectancy) |
| **Trading costs and execution assumptions** | **Demonstrated secondary, not primary** | The BTC profitability investigation found the dominant weak setup there (S005) was net-negative *pre-fee* — costs make a losing setup lose faster, they do not manufacture the loss. No SOL-specific pre/post-fee decomposition has been run this session, but there is no reason from the BTC evidence to expect costs are the primary driver here either |
| **Exit design** | **Demonstrated not-primary on BTC; untested on SOL** | The BTC investigation found payoff ratio stable (~1.5) across every setup/window and median MAE clustering near 1.0R — stop/target geometry was explicitly ruled out as the primary driver there. This has not been separately re-verified on SOL, but the SOL research this session used the same ATR-based first-passage endpoint (not a fixed-R adapter change), so there is no new reason to suspect exit geometry is SOL's primary issue either |
| **Weak setups dominating portfolio activity** | **Not currently applicable to SOL** | This BTC-diagnosed mechanism (S005 monopolizing the one-trade-slot) requires multiple setups registered together. Every SOL backtest this session ran `StrategyEngineV2` with S001 alone — the crowding mechanism is architecturally real and dormant (confirmed via direct code reading of `strategy_engine_v2.py`'s first-fired-wins arbitration) but not currently active for SOL |
| **Unsuitable market conditions** | **Plausible, unmeasured on SOL** | The BTC investigation found S001's own win rate swung from 30% to 61.5% between two months — a real, demonstrated regime-dependence *on BTC*. Whether the same pattern holds on SOL's own 4 TRAIN months has not been isolated as its own question (the closest existing cut, Market Structure `bos` state, showed inconsistent redundancy-check results for `cvd_direction` in the CVD sprint, itself suggestive of regime sensitivity but not a direct test) |
| **Missing information** | **Plausible, genuinely unexplored** | CVD/Delta (order-flow proxy from OHLCV) was exhaustively tested and found not to add reliable value. True derivatives information (open interest, funding, actual reported liquidations) has never been incorporated into any SOL setup research — this is a real gap, addressed in Sections 4–6 |
| **Research design or sample limitations** | **Demonstrated, contributing factor throughout** | Every SOL hypothesis this session has been tested on 4 TRAIN months only (by design, per the project's own data-use discipline) — sample sizes of 25–465 per hypothesis are adequate to rule out *large* effects but not adequate to confirm or rule out a *small, real* edge, which is exactly the kind of edge a competitive, well-arbitraged market like SOL perpetuals would be expected to offer if one exists at all |

**Strongest supported explanation, stated as one sentence**: S001's
core entry thesis has not been shown to separate favorable from
unfavorable outcomes at better than chance on SOL TRAIN, and the one
architectural choice added specifically to improve it (the multi-source
confirmation gate) is measurably reshaping *which* trades are taken in
a direction (away from round-number sources) that the limited evidence
suggests may be the wrong direction — making "redundant/mis-targeted
confirmation compounding a weak core entry signal" the most concrete,
evidence-backed candidate root cause, ahead of costs, exit design, or
missing information (all of which are plausible but comparatively
unmeasured or already ruled out as primary on the comparable BTC
evidence).

### 1.4 Shortest sensible route

Given the above, the shortest sensible route is **improving an existing
setup's entry-selection logic** (S001's own confirmation gate), not
building a new setup, not acquiring new data yet, and not a broad
research-infrastructure correction. The evidence for this ranking:
S001 is the only setup with a large-enough, well-characterized evidence
base to act on; the specific mechanism (round-number discrimination) is
already measured, not hypothesized from theory; and it requires no new
data collection, matching the "smallest experiment" discipline this
project has followed throughout. Building a new setup would discard
five sprints of specific, hard-won characterization of S001's own
Liquidity Pool feature; acquiring new data is not yet justified
(Section 4–5); and no research-design defect was found large enough to
invalidate the existing evidence (Section 2 audits found no confirmed
correctness defect in either the Liquidity Pool feature or the CVD/Delta
pipeline).

---

## 2. SOLUSDT as the primary instrument

### 2.1 Data venue — verified, not assumed

**Confirmed directly from the repository**: `docs/research_dataset_validation_report.md`
states the full 96-file, 4-symbol (BTC/ETH/SOL/XRP), 2-year (2024–2025)
dataset was "downloaded from Binance Vision (`data.binance.vision`,
**USD-M Futures** monthly klines archive)." This is corroborated by the
project's own live-data infrastructure (`exchange/binance_data.py`,
`exchange/download_historical_klines.py`) which exclusively targets
`fapi.binance.com` — the Binance USDⓈ-M perpetual futures API, never
spot (`api.binance.com`). **All SOL research in this project, and the
intended execution venue implied by the existing infrastructure, is
Binance USDT-margined perpetual futures — not spot.** There is no
venue mismatch between the research data and the infrastructure that
would execute it, but this means **every profitability number in every
report is a perpetual-futures result, and funding cost has never been
included in any cost model used** (Section 2.4).

### 2.2 Liquidity, opportunity frequency, holding time

SOL is one of the most liquid USDT-margined perpetuals on Binance by
public reputation and typical daily volume — this is **stated as
general market knowledge, not independently verified for this review**
(no live order-book or volume-at-size data was pulled; doing so was out
of scope). What **is** measured from this project's own research: S001
produces roughly 11–19 fresh-sweep-with-confirmation candidates per
TRAIN month before any CVD gate (465 CVD-blind candidates / 4 months /
~4 candidates-per-week), and 11–19 actual trades per month after every
gate. This is a real, small, measured opportunity rate — consistent
with, not contradicted by, general claims of SOL's liquidity (a liquid
market does not imply frequent *qualifying setups* for any one specific
entry thesis).

### 2.3 Regime dependence

Not separately measured for SOL as its own question this session (see
Section 1.3). The comparable BTC finding (win rate 30%→61.5% between
two single months) is a warning sign worth carrying forward, not a SOL
measurement.

### 2.4 Funding and liquidation exposure — a genuine, previously
unstated gap

**No cost model used in any report this project has produced (BTC or
SOL) includes perpetual funding cost.** The BTC profitability
investigation's own cost model states "Fees: 0.04% per side. Slippage:
0.02% per side" — funding is absent. Since the confirmed execution
venue is perpetual futures (Section 2.1), and this project's own trades
can hold for multiple hours to plausibly over a funding interval (8h),
**funding is a real, currently-unmodeled cost or credit** for every
historical result in this project. This does not necessarily change any
conclusion (funding on SOLUSDT perpetual is typically small relative to
a 1R/2R trade, and can be positive or negative depending on position
side and prevailing market skew), but it has never been checked, and
should be disclosed as a limitation in every future certification
report, not assumed negligible without a measurement.

**Liquidation exposure** (the trader's own position being forcibly
closed) is a real perpetual-specific risk not modeled by any current
backtest — `calculate_position_size` (per the BTC investigation) has no
leverage/margin cap; this is an existing, disclosed limitation
(Section 2, item 11 of that report), not new to this review.

### 2.5 BTC context / SOL-BTC relative strength — infrastructure
already exists, unused

`strategy/features/correlation.py`'s `CorrelationTracker` and S001's own
`_smt_confirms` (SMT/intermarket divergence check) are already built,
already tested, and already wired into S001's `additional_evidence` —
but **every SOL research harness this session constructed
`MarketIntelligenceCoordinator` with no configured `smt_pairs`**,
meaning this evidence source has been present in the architecture but
never actually exercised with a real BTC-SOL pair. This is the cheapest
possible incremental information source available: no new code, no new
data (BTC OHLCV for the same months is already downloaded and validated
per `research_dataset_validation_report.md`), just configuring an
already-tested mechanism. Noted as directly relevant to Hypothesis
ranking, Section 6.

### 2.6 SOL suitability verdict

SOL remains an appropriate primary instrument: the data venue matches
the likely execution venue, general liquidity is not in serious doubt,
and the project's own infrastructure already supports BTC-context
enrichment at effectively zero marginal cost. The **specific,
previously-unstated gap is funding-cost omission** from every backtest
to date — worth correcting before any live-pilot cost claim, not before
continuing TRAIN-tier research (funding's effect on a *relative*
TRAIN comparison between two configurations of the same setup, on the
same instrument, is a second-order concern; its effect on an *absolute*
profitability claim before live piloting is not).

---

## 3. Liquidation and derivatives information — what would actually be new

### 3.1 The CoinGlass distinction (per the user's own reference,
verified against current documentation, checked 2026-09-05)

- **[Liquidation Heatmap](https://docs.coinglass.com/reference/liquidation-heatmap)**:
  confirmed **modeled/estimated**, not historical fact. The
  documentation's own wording: liquidation levels are shown "by
  calculating them based on market data and various leverage amounts."
  This is a **forward-looking, assumption-driven model of where
  liquidations *could* cluster**, not a record of where they *did*.
  Requires Professional ($699/mo) or Enterprise. **No explicit SOL
  confirmation** in the documentation fetched — coverage would need to
  be checked against the `supported-exchange-pair` endpoint, which
  requires an account to query (not done here — no subscription
  authorized).
- **[Liquidation History](https://docs.coinglass.com/reference/liquidation-history)**:
  confirmed **aggregated reports of executed liquidation events**
  (`long_liquidation_usd`/`short_liquidation_usd` per time bucket) —
  genuinely different information from the heatmap. Available from the
  Hobbyist tier ($29/mo) upward, with interval restrictions below
  Standard ($299/mo). **The documentation does not state how far back
  historical data actually extends** — `start_time`/`end_time`
  parameters exist, but per the user's own explicit caution, a
  parameter's existence does not prove depth. **Unverified — would
  require a paid account to test**, which this review is not authorized
  to obtain.

**Neither CoinGlass product should be assumed to "prove" anything about
price behavior even if purchased**: a bright band on a modeled heatmap
does not mean price is drawn to it (it is a projection, not an
observation); a real liquidation burst reported in the history endpoint
does not by itself tell you whether the subsequent move is continuation
(forced flow still working through the book) or reversal (forced flow
exhausted) — both are legitimate, competing hypotheses, addressed as
separate mechanisms in Section 5's Hypothesis 3, not assumed in either
direction.

### 3.2 What our own OHLCV + taker-volume pipeline cannot see

Distinguishing the six information types precisely, and what a
new source would add:

| Type | Do we have it? | What it adds beyond current pipeline |
|---|---|---|
| Modeled future liquidation concentration (heatmap) | No | A leverage-assumption-driven price-level projection — genuinely new, but explicitly a model, not a measurement; usefulness depends entirely on the model's own unverifiable assumptions |
| Reported liquidation activity (history) | No | Confirmation that forced selling/buying *actually happened*, with size and side — current pipeline can only *infer* aggressive flow via taker-volume Delta, which cannot distinguish a voluntary aggressive market order from a forced liquidation order |
| Open interest / change in OI | Only last 30 days, BTC only, via Binance's free endpoint (`exchange/download_historical_open_interest.py`, confirmed capped at 30 days in that file's own code comment) | Position-buildup context — but OI alone cannot reveal net long/short positioning (a symmetric increase in both longs and shorts also raises OI) |
| Funding / spot-perp basis | Funding: available free & full-history from Binance for any symbol (`exchange/download_historical_funding.py`, no retention cap found); SOL funding not yet downloaded locally. Basis: not currently collected | Funding is a real cost/signal not currently in any cost model (Section 2.4); basis would require spot data collection (not currently in the dataset) |
| Executed aggressive flow | Already have (Delta/CVD, exhaustively tested this sprint — no reliable value found) | Nothing new — this is exactly what was just tested |
| Resting order-book liquidity | No, and not obtainable for a historical backtest at all — no historical order-book snapshot vendor was evaluated (out of scope of the two named CoinGlass products) | Order-book depth at the moment of a would-be entry — the one category this review did not find *any* even-partially-verified historical source for |

**Correcting three assumptions explicitly, per the review's own
instruction**: increasing open interest does not, by itself, reveal net
positioning (longs and shorts can both increase); a liquidation burst
does not necessarily cause a reversal (continuation-during-cascade and
reversal-after-exhaustion are both live, competing hypotheses, not one
default); resting order-book liquidity is never guaranteed to remain
available between observation and execution, so even a real-time
order-book feed would carry execution-uncertainty a backtest cannot
fully represent.

### 3.3 Reconstructed heatmaps are not point-in-time information

A liquidation heatmap re-rendered today for a past date reflects prices
that have since moved and clusters recalculated with today's model —
**it is not what a trader actually saw at the historical decision
moment**, and CoinGlass's own documentation gives no indication the
heatmap product retains dated, point-in-time snapshots (only a
real-time chart with selectable lookback *windows*, not archived
historical *renderings*). Using a present-day heatmap re-render to
"backtest" a past decision would silently leak information unavailable
at the time — this review does not recommend that approach, and it
would need to be explicitly ruled out before any future sprint touched
this product.

---

## 4. Data-source comparison

All figures below are from documentation fetched 2026-09-05, links
inline; "Unverified" marks anything this review could not confirm
without a paid account (not obtained, per the review's own scope).

| | **Binance (direct exchange)** | **CoinGlass** | **Coinalyze** |
|---|---|---|---|
| SOL/exchange coverage | SOLUSDT USDⓈ-M perpetual — the actual venue our data already comes from | Multi-exchange aggregator incl. Binance; SOL support plausible but not explicitly confirmed in fetched docs — would need `supported-exchange-pair` query | Multi-exchange aggregator; SOL liquidation page exists publicly (spot-checked page pattern, not deeply verified) |
| Measured vs. modeled | Measured (klines, funding are exchange-reported; OI is exchange-reported but short-retention) | [Liquidation History](https://docs.coinglass.com/reference/liquidation-history) = measured/aggregated; [Liquidation Heatmap](https://docs.coinglass.com/reference/liquidation-heatmap) = **explicitly modeled**, not measured | Liquidation history = measured/aggregated (per public API doc) |
| Resolution | 1m klines already in use; funding per 8h funding event; OI per requested interval (30-day cap) | Liquidation history: 1m–1w intervals (tier-gated); heatmap: no fixed candle resolution, price-bucketed | Liquidation history: down to 1-minute buckets |
| Historical coverage (verified) | Klines: full, already validated for our TRAIN periods. Funding: full history, not retention-limited (no cap found in code/docs). **OI: 30 days only, confirmed in this project's own downloader code comment.** **Market-wide liquidations: none — REST endpoint forward-only via WebSocket subscription, no historical backfill at all**, confirmed via Binance's own current changelog | **Unverified** — start/end-time parameters exist; actual depth not documented, not tested (no subscription obtained) | **Confirmed limited**: intraday liquidation data explicitly capped at 1,500–2,000 datapoints with **old data deleted daily** per Coinalyze's own docs — does **not** support arbitrary historical backfill to our TRAIN months at intraday resolution |
| Point-in-time snapshots | N/A (klines/funding are immutable historical records by nature) | Not confirmed for the heatmap (Section 3.3) | Not applicable — rolling window, not an archive |
| API vs. chart-only | Full REST/WebSocket API, already integrated in this project | Full REST API (tiered) | Full REST API (documented, key-gated) |
| Plan / cost | **Free** (klines, funding); OI free but 30-day-capped | Liquidation history from **$29/mo** (Hobbyist, interval-restricted) to **$299/mo** (Standard, for 1m–30m intervals unrestricted); Heatmap requires **$699/mo** (Professional) or Enterprise | **Free** for the documented public tier |
| Integration effort | None — already integrated | Low-moderate (new REST client, new data-quality audit matching this project's own standing discipline) | Low (simple REST client) |

**Reading this table**: for the one category we most lack (reported,
market-wide historical liquidations), **no evaluated source has
confirmed historical depth matching our TRAIN months** — Binance has
none at all (by design, not by omission), Coinalyze explicitly does
not retain enough, and CoinGlass's actual depth is undocumented and
would require paying to find out. This is the central finding driving
Section 6/7's recommendation to treat any liquidation-data hypothesis
as **prospective-collection-only**, not a purchase decision, until that
depth question is separately, cheaply resolved (e.g. a single support
inquiry to CoinGlass asking for SOL history depth before any
subscription, which this review does not execute).

---

## 5. Ranked testable edge hypotheses

### Hypothesis 1 (top priority) — Round-number-conditional confirmation gating

- **Mechanism**: round numbers are genuine, simple psychological/
  institutional levels (documented in this project's own Liquidity Pool
  architecture) that do not require multi-source confluence to be real
  — S001's "require ≥1 additional confirmation" rule (added via a small,
  n=12, BTC-only experiment per its own docstring) was never tested for
  whether it helps or hurts specifically at round-number-sourced sweeps,
  which are 94% of the underlying population.
- **Why it could persist**: if true, this is not a market inefficiency
  being arbitraged away — it is a **specific implementation choice in
  our own system** that may be filtering the wrong population; its
  "persistence" is an engineering question, not a market-competition one.
- **Observable before entry**: the swept pool's own `sources` field
  (already computed, already logged) — fully available at decision time.
- **Expected direction/horizon**: same reversal thesis and horizon as
  current S001 (+1/−1 ATR primary), conditioned on source.
- **Failure conditions**: if round-number-only performance is itself
  unstable across a larger sample or reverses sign, the hypothesis fails.
- **Existing evidence**: supporting — round-number S001 trades
  outperformed non-round-number trades in the Touch/Volume sprint
  (41.4% vs. 31.2% win rate, n=29/32); the CVD sprint's own
  `cvd_direction` redundancy check independently found the *same*
  round-number subgroup behaving differently from the rest (though for
  a different field). Contradicting/limiting: both supporting
  observations are on small samples (n=29–246) and neither was
  pre-registered as this specific hypothesis.
- **Incremental information beyond current inputs**: none required —
  this re-conditions existing fields, adds nothing new.
- **Minimum components/data**: none beyond already-collected TRAIN data
  and already-computed `sources`.
- **Cost/complexity/execution sensitivity**: lowest of all three —
  a stratified re-analysis, not a new backtest.
- **Smallest rejecting experiment**: Section 7.

### Hypothesis 2 — Regime-conditional reversal thesis

- **Mechanism**: liquidity-sweep reversals are a mean-reversion thesis;
  in a strongly trending regime a "sweep" is more often genuine
  continuation than exhaustion. BTC evidence already shows S001's win
  rate swinging 30%→61.5% between two months — consistent with,
  though not proof of, regime dependence.
- **Why it could persist**: regime-conditional edges are harder to
  arbitrage away than unconditional ones, since they require correctly
  classifying the regime in real time, not just knowing the base rate.
- **Observable before entry**: `structure.bos`/`choch` (already
  computed) and/or an ATR-percentile proxy (computable from existing
  OHLCV, no new data).
- **Expected direction/horizon**: unchanged S001 thesis, conditioned on
  regime state.
- **Failure conditions**: if SOL's own regime cuts show no consistent
  pattern (plausible — the BTC investigation's own regime/session
  analysis was explicitly non-actionable due to sample size), the
  hypothesis fails for lack of resolvable signal, not necessarily
  because the mechanism is wrong.
- **Existing evidence**: supporting on BTC only (not SOL); no SOL-specific
  test has been run. This is the hypothesis's main weakness relative to
  Hypothesis 1.
- **Incremental information**: none beyond existing fields.
- **Minimum components/data**: none new.
- **Cost/complexity**: low-moderate (a new regime-classification harness,
  not a new setup).
- **Smallest rejecting experiment**: split existing S001 CVD-blind
  candidates by `bos` state and by an ATR-percentile tercile at
  confirmation; if no split shows a ≥5-point, cross-month-consistent
  favorable-rate gap, reject.

### Hypothesis 3 — Forced-liquidation behavior (derivatives-information route)

- **Mechanism**: two competing, explicitly separate sub-hypotheses per
  the review's own instruction — (a) price continues during an active
  liquidation cascade (forced flow still working through the book), or
  (b) price reverses once forced flow exhausts (the cascade "runs out"
  of positions to liquidate). A genuine reported-liquidation feed could
  distinguish "this move was forced" from "this move was voluntary,"
  information the current Delta/CVD proxy structurally cannot provide
  (it sees aggressive-side volume, not *why* that volume traded).
- **Why it could persist**: forced flow is mechanically distinct from
  informed flow — a real edge here would be structural (about how
  liquidation engines work), not merely a slow-moving informational
  advantage.
- **Observable before entry**: N/A currently — this is the one
  hypothesis requiring new information, not a re-conditioning of
  existing fields.
- **Expected direction/horizon**: two directions, deliberately not
  pre-committed (Section 3.1) — the experiment would need to
  distinguish them, not assume one.
- **Failure conditions**: if reported liquidation events show no
  measurable relationship to subsequent price behavior beyond what
  Delta/CVD already captures (a real possibility, given Delta/CVD's own
  exhaustive, largely-null result this sprint), the hypothesis fails.
- **Existing evidence**: none — genuinely untested in this project.
- **Incremental information beyond current inputs**: potentially real
  (Section 3.2) — this is the hypothesis's main strength.
- **Minimum components/data**: a market-wide historical liquidation feed
  — **confirmed unavailable from Binance directly** (Section 4), and
  **unverified from every evaluated paid vendor**. This is the
  hypothesis's central weakness: it cannot be tested on the existing
  TRAIN periods at all without either (a) paying for unverified vendor
  depth, or (b) collecting prospectively from today forward.
- **Cost/complexity/execution sensitivity**: highest of the three —
  genuinely requires new data infrastructure, and even then only
  forward-looking (no way to test it retroactively on 2024–2025 TRAIN
  months without a vendor of unverified quality).
- **Smallest rejecting experiment**: Section 7 addresses this as a
  design-only, prospective-collection proposal, not an executable
  TRAIN experiment (there is no TRAIN-compatible version of this
  experiment given current data availability).

### The CVD-direction/round-number interaction — explicitly addressed

**This does not deserve its own slot among the three.** It is
evidentially a special case of Hypothesis 1: the CVD sprint's finding
that `cvd_direction`'s apparent effect was concentrated in
round-number-sourced pools is the same underlying population split
Hypothesis 1 investigates, observed through a different (and, on its
own, redundancy-check-failed) field. Treating it as a fourth, separate
hypothesis would double-count one population split as if it were two
independent pieces of evidence — exactly the "multiple correlated
confirmations do not constitute independent evidence" pattern this
review was asked to guard against. It is folded into Hypothesis 1's own
evidence base (Section 5, Hypothesis 1's "existing evidence" bullet),
not discarded and not separately prioritized.

---

## 6. Recommended next action

**Hypothesis 1 (round-number-conditional confirmation gating) is the
single recommended next action.** It is the cheapest (no new data, no
new backtest — a stratified re-analysis of data already collected in
the completed CVD signal-value sprint), the most directly evidenced
(two independent sprints already surfaced the same population split
from different angles), and it tests whether an **existing setup's own
architecture** is mis-targeted — exactly the "shortest sensible route"
conclusion from Section 1.4. It is prioritized over Hypothesis 2
(plausible but SOL-untested, BTC-only evidence) and Hypothesis 3
(mechanistically interesting but blocked on unverified/unavailable
historical data).

### Experiment design (not executed)

- **Baseline**: S001 exactly as currently gated (multi-source
  confirmation required for every pool, regardless of source).
- **One substantive change**: for round-number-only-sourced pools
  specifically, evaluate outcomes with the multi-source confirmation
  requirement removed (i.e., treat CHOCH/multi-source/SMT evidence as
  informational, not gating, for this source subgroup only) — everything
  else (sweep detection, CVD gate, direction mapping) stays exactly as
  currently implemented. This is a single, isolated change to one
  population's gating logic, not a new setup and not a threshold search.
- **Exact candidate population and causal timing**: reuse the
  already-collected `s001_candidates` population from the completed CVD
  signal-value sprint (465 CVD-blind candidates, 4 TRAIN months, each
  with its own `sources`, `bar_i`, `direction`, and CVD-condition
  reading already recorded) — split into round-number-only vs. other,
  cross-referenced against which candidates *did* vs. *did not* have
  evidence_count≥1. No new snapshot replay is required; this is a
  re-slice of already-materialized data, with the same causal
  guarantees already proven in that sprint (candidates were captured
  before CVD conditioning, using the real, unmodified private methods).
- **Primary decision metric, tied to trading use**: after-cost expected
  value per candidate (not just win rate) under the existing +1/−1 ATR
  first-passage endpoint **and** a direct comparison of the exact
  round-number-only S001 trades that were blocked by the confirmation
  gate (already identifiable from the existing `would_fire_in_production`
  field in that same dataset) against the trades that passed.
- **Realistic costs**: apply the same fee (0.04%/side) and slippage
  (0.02%/side) already used throughout this project's BTC and SOL
  research — no new assumption introduced. Funding is **not** included
  (Section 2.4's gap applies here too) — this should be disclosed in
  the eventual report as a known limitation, not silently assumed zero.
- **Matched-event and sequential-portfolio results**: report both the
  module-level (event-population) comparison and an exact,
  pool_id-linked sequential backtest of "S001 with round-number pools
  exempted from the multi-source gate" vs. production S001, using the
  same exact-linkage method (never nearest-timestamp) already proven in
  every prior sprint.
- **Sample-size and dependence treatment**: reuse the same
  month-clustered uncertainty method already frozen and used in the CVD
  signal-value protocol (4 clusters, t-distribution df=3) — do not
  introduce a new statistical method for this experiment.
- **Multiple-testing controls**: this is a single, pre-specified
  hypothesis (one population split, one gating change) — no threshold
  sweep, no multi-field search. If a future sprint tests this alongside
  Hypothesis 2 or 3 in the same protocol, report both as separate
  hypotheses with that count disclosed, as this project's own CVD sprint
  already did.
- **Practical improvement threshold and stopping rule, justified (not
  a generic 5pp/50%)**: given round-number pools are 94% of the pool
  population and currently only 47.5% of trades, a change here could
  plausibly double S001's trade count from this source alone — the
  relevant question is not "does the favorable rate cross an arbitrary
  5-point bar" but **whether the after-cost expected value per newly-included
  trade is non-negative**, since these are trades the system currently
  forgoes entirely. Proposed stopping rule: promote to a frozen
  VALIDATION experiment only if (a) after-cost expected value for the
  newly-unblocked round-number trades is positive or not statistically
  distinguishable from the currently-passing population's own
  (already-negative) expectancy — i.e., "at least as good as what we
  already accept" — **and** (b) this holds in at least 3 of 4 TRAIN
  months. This threshold is tied directly to the actual trading
  decision (would we accept these trades if the gate were relaxed?),
  not a borrowed generic percentage.
- **What would reject the idea**: newly-unblocked round-number trades
  showing after-cost expected value clearly worse than the
  currently-gated population's own, or no consistent direction across
  TRAIN months — either would indicate the confirmation gate is doing
  useful work for round-number pools specifically, contradicting
  Hypothesis 1.
- **Time, data cost, implementation effort**: no new data. Estimated
  effort: a few hours (re-slicing an existing pickle plus one new,
  small research module analogous in size to
  `cvd_delta_opportunity_populations.py`, with its own tests, following
  this project's established pattern) — the smallest-effort experiment
  proposed anywhere in this review.

### What this review does not authorize

This design is not executed. No new backtest was run, no new outcome
data was accessed, no subscription was purchased, and no production
file was modified to produce this review.

---

## 7. Updated immediate roadmap

| Item | Disposition | Why |
|---|---|---|
| Round-number-conditional S001 confirmation re-analysis | **Do next** | Cheapest, most evidenced, tests an existing setup's own architecture (Section 6) |
| Regime-conditional reversal thesis (Hypothesis 2) | **Do after Hypothesis 1**, not before | Plausible but currently only BTC-evidenced; a natural second small experiment reusing the same candidate population |
| Configure an existing BTC-SOL SMT pair in a research harness | **Do opportunistically, low cost** | Already-built, already-tested infrastructure, zero new data — worth including alongside Hypothesis 2's regime work rather than as its own sprint |
| Forced-liquidation / derivatives-data route (Hypothesis 3) | **Defer — propose a prospective, forward-only paper-observation plan in a future sprint; do not purchase data now** | No vendor evaluated has *confirmed* historical depth matching TRAIN months at any price; Binance itself has no historical market-wide liquidation REST data at all |
| CoinGlass or any paid liquidation/OI subscription | **Stop — not justified yet** | Undocumented actual depth (Section 4); resolve the depth question via a free inquiry before any purchase decision, and only after Hypotheses 1–2 are exhausted |
| Portfolio-level allocator / multi-setup crowding fix (from the BTC profitability investigation) | **Defer** | Confirmed dormant for SOL (only one setup has ever been registered in any SOL run) — real but not currently active; revisit only once a second SOL setup is seriously considered |
| S005 (Fair Value Gap Rebalance) revival on SOL | **Stop for now** | Already RESEARCH ARCHIVE status from the BTC investigation (net-negative, no confirmation gate); no SOL-specific reason found to revisit ahead of fixing S001 |
| S007 (Trend Continuation Confluence) standalone certification | **Defer** | n=25 candidates on SOL TRAIN (this sprint's own measurement) is far too small; not worth a dedicated backtest until either Hypothesis 1 or 2 produces a reason to prioritize it |
| Funding-cost inclusion in the standard cost model | **Do, low effort, before any live-pilot claim** | Confirmed venue is perpetual futures; confirmed no report has ever included funding; free data already obtainable per-symbol from Binance |
| MAE/MFE Analytics hook (from the BTC profitability investigation, item C.3) | **Do opportunistically** | Already scoped, low effort, already proven useful once; would strengthen any future SOL certification report without being on the critical path |

---

## 8. What would make a profitability claim plausible

This review does not claim S001, or any current setup, will become
profitable. The evidence needed before that claim would be reasonable:
(a) after-cost, funding-inclusive expected value measurably positive on
a pre-registered TRAIN experiment (not a threshold search); (b) that
result replicating in direction across at least 3 of 4 TRAIN months and
surviving the same redundancy controls (source, direction, regime) this
project's own CVD sprint already applied; (c) an independent
confirmation on the untouched SECONDARY_VALIDATION months under a fresh,
separately-frozen protocol; and only then (d) a single, final check
against FINAL_HELD_OUT (2025-02, 2025-07), touched exactly once. No step
in this project's history to date has produced (a) for any setup on
SOL — this review's own recommended next action (Section 6) is aimed
squarely at generating a first, honest attempt at (a), nothing more.

---

## 9. Explicit confirmations

No production file was modified. No new backtest was run and no new
outcome data was accessed to produce this review — every SOL/BTC number
above is drawn from already-completed, already-committed reports. No
subscription, data purchase, or exchange integration was performed.
FINAL_HELD_OUT (2025-02, 2025-07) was not accessed. This document is
left **uncommitted**, per the authorizing instructions, awaiting your
review before any implementation, subscription, new backtest, or
further module work.
