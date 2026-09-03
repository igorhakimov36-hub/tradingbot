# Out-of-Sample Validation — Setup Library vs. Six Months of 2024

No setup was modified. No parameter was changed. No optimization was
performed. This report runs the Setup Library exactly as it exists
today — the same committed code already approved, archived, or
rejected — against real BTCUSDT data it has never been backtested
against before: January through June 2024, six independent 30-ish-day
windows, using the `WindowManager` TRAIN/VALIDATION/HELD_OUT
infrastructure that has existed since Phase 0 but had never actually
been exercised until now.

**Data disclosure, stated plainly rather than worked around:**

- **S004 (SMT Reversal) could not be tested.** No ETHUSDT data exists
  for any 2024 month — only `ETHUSDT-1m-recent30d.csv` exists, matching
  the original research window only. Fabricating substitute reference
  data was explicitly out of scope, so S004 is absent from this report
  entirely, not silently approximated.
- **S001 (Liquidity Sweep Reversal) ran without `smt_pairs` configured**
  for all six 2024 months, for the same reason — its SMT
  additional-evidence check structurally could not be satisfied.
  This is a disclosed, minor difference from the original window's run
  (which had live ETH data via Step 0); the setup's own measured
  sensitivity to this was small (13 trades with SMT wired vs. 12
  without, out of the same 30-day window), so it does not materially
  affect the comparison below, but it is not a like-for-like control.
- 2024 monthly 15m candles were built fresh from the raw 1m CSVs via
  the same `TimeframeManager`, not from the one pre-built
  `BTCUSDT-15m-2024-01.csv` file, for methodological consistency with
  every other backtest in this project.

---

## Full results, per setup, per month, vs. the original window

### S001 — Liquidity Sweep Reversal (currently APPROVED)

| Metric | 2024-01 | 2024-02 | 2024-03 | 2024-04 | 2024-05 | 2024-06 | ORIGINAL |
|---|---:|---:|---:|---:|---:|---:|---:|
| Trades | 10 | 7 | 25 | 13 | 10 | 11 | 13 |
| Win Rate | 30.00% | 14.29% | 24.00% | 46.15% | 50.00% | 45.45% | 38.46% |
| Profit Factor | 0.653 | 0.251 | 0.473 | **1.280** | **1.479** | **1.244** | 0.922 |
| Expectancy | -28.68 | -74.97 | -45.08 | 18.04 | 29.25 | 16.40 | -5.69 |
| Average R | -0.271 | -0.739 | -0.456 | 0.183 | 0.290 | 0.171 | -0.045 |
| Net Profit | -286.76 | -524.82 | -1,127.08 | 234.51 | 292.51 | 180.35 | -74.02 |
| Gross Profit | 538.82 | 175.82 | 1,012.11 | 1,072.56 | 903.78 | 920.28 | 875.86 |
| Gross Loss | 825.58 | 700.64 | 2,139.19 | 838.05 | 611.28 | 739.93 | 949.88 |
| Max Drawdown | 6.27% | 5.25% | 11.27% | 3.49% | 2.39% | 2.39% | 4.72% |
| Recovery Factor | -0.449 | -1.000 | -1.000 | 0.671 | 1.191 | 0.725 | -0.157 |
| Holding Time | 4.09h | 9.11h | 3.84h | 2.16h | 4.12h | 6.41h | 14.59h |
| Trade Frequency | 0.323/day | 0.241/day | 0.806/day | 0.433/day | 0.323/day | 0.367/day | 0.433/day |

### S002 — Order Block Continuation (currently APPROVED)

| Metric | 2024-01 | 2024-02 | 2024-03 | 2024-04 | 2024-05 | 2024-06 | ORIGINAL |
|---|---:|---:|---:|---:|---:|---:|---:|
| Trades | 115 | 82 | 131 | 104 | 95 | 66 | 59 |
| Win Rate | 33.04% | 30.49% | 30.53% | 29.81% | 32.63% | 28.79% | 33.90% |
| Profit Factor | 0.737 | 0.647 | 0.642 | 0.625 | 0.717 | 0.612 | 0.764 |
| Expectancy | -18.89 | -26.07 | -23.27 | -26.10 | -20.55 | -30.82 | -18.10 |
| Average R | -0.196 | -0.274 | -0.260 | -0.286 | -0.211 | -0.324 | -0.176 |
| Net Profit | -2,172.41 | -2,137.66 | -3,048.40 | -2,714.63 | -1,952.21 | -2,033.80 | -1,067.91 |
| Gross Profit | 6,090.70 | 3,911.69 | 5,475.41 | 4,526.17 | 4,935.49 | 3,208.37 | 3,457.62 |
| Gross Loss | 8,263.10 | 6,049.35 | 8,523.81 | 7,240.79 | 6,887.70 | 5,242.17 | 4,525.53 |
| Max Drawdown | **23.11%** | **24.17%** | **36.85%** | **32.61%** | **23.19%** | **28.42%** | 13.26% |
| Recovery Factor | -0.924 | -0.884 | -0.827 | -0.832 | -0.822 | -0.666 | -0.786 |
| Holding Time | 3.80h | 4.94h | 3.14h | 3.41h | 4.52h | 7.15h | 8.66h |
| Trade Frequency | 3.710/day | 2.828/day | 4.226/day | 3.467/day | 3.065/day | 2.200/day | 1.967/day |

### S003 — Volume Node Reversal (currently RESEARCH ARCHIVE)

| Metric | 2024-01 | 2024-02 | 2024-03 | 2024-04 | 2024-05 | 2024-06 | ORIGINAL |
|---|---:|---:|---:|---:|---:|---:|---:|
| Trades | 44 | 40 | 65 | 62 | 48 | 30 | 33 |
| Win Rate | 36.36% | 35.00% | 33.85% | 35.48% | 18.75% | 36.67% | 21.21% |
| Profit Factor | 0.904 | 0.849 | 0.799 | 0.868 | 0.349 | 0.919 | 0.411 |
| Expectancy | -6.64 | -11.25 | -14.54 | -9.74 | -52.00 | -6.15 | -49.75 |
| Average R | -0.053 | -0.102 | -0.139 | -0.089 | -0.575 | -0.051 | -0.519 |
| Net Profit | -292.08 | -450.14 | -944.78 | -604.03 | -2,495.79 | -184.60 | -1,641.78 |
| Gross Profit | 2,743.36 | 2,533.76 | 3,744.30 | 3,983.29 | 1,337.59 | 2,091.81 | 1,146.95 |
| Gross Loss | 3,035.44 | 2,983.90 | 4,689.08 | 4,587.32 | 3,833.38 | 2,276.41 | 2,788.73 |
| Max Drawdown | 11.37% | 8.04% | 11.11% | 15.68% | 27.73% | 10.42% | 18.92% |
| Recovery Factor | -0.257 | -0.539 | -0.844 | -0.359 | -0.900 | -0.162 | -0.868 |
| Holding Time | 12.32h | 13.27h | 5.48h | 8.28h | 10.51h | 18.65h | 18.01h |
| Trade Frequency | 1.419/day | 1.379/day | 2.097/day | 2.067/day | 1.548/day | 1.000/day | 1.100/day |

### S005 — Fair Value Gap Rebalance (currently RESEARCH ARCHIVE)

| Metric | 2024-01 | 2024-02 | 2024-03 | 2024-04 | 2024-05 | 2024-06 | ORIGINAL |
|---|---:|---:|---:|---:|---:|---:|---:|
| Trades | 74 | 71 | 96 | 90 | 94 | 59 | 60 |
| Win Rate | 35.14% | 35.21% | 34.38% | 33.33% | 31.91% | 40.68% | 40.00% |
| Profit Factor | 0.805 | 0.806 | 0.792 | 0.766 | 0.701 | **1.023** | 0.992 |
| Expectancy | -13.80 | -14.21 | -15.55 | -17.71 | -21.74 | 1.66 | -0.60 |
| Average R | -0.131 | -0.135 | -0.153 | -0.178 | -0.226 | 0.026 | 0.004 |
| Net Profit | -1,020.93 | -1,008.61 | -1,493.16 | -1,593.70 | -2,043.13 | 98.15 | -36.14 |
| Gross Profit | 4,205.85 | 4,187.66 | 5,673.73 | 5,217.84 | 4,796.83 | 4,395.99 | 4,318.02 |
| Gross Loss | 5,226.79 | 5,196.27 | 7,166.89 | 6,811.55 | 6,839.96 | 4,297.84 | 4,354.16 |
| Max Drawdown | 17.35% | 13.21% | 22.14% | 20.95% | 21.87% | 8.64% | 7.11% |
| Recovery Factor | -0.588 | -0.755 | -0.628 | -0.715 | -0.934 | 0.106 | -0.047 |
| Holding Time | 5.38h | 5.31h | 3.12h | 4.61h | 4.60h | 8.68h | 8.38h |
| Trade Frequency | 2.387/day | 2.448/day | 3.097/day | 3.000/day | 3.032/day | 1.967/day | 2.000/day |

---

## Consistency and aggregate summary

| Setup | Mean PF (6 OOS months) | Stdev PF | CV | Months PF ≥ 1 | Pooled 6-month net | Pooled 6-month PF |
|---|---:|---:|---:|---:|---:|---:|
| Liquidity Sweep Reversal | 0.896 | 0.502 | 0.560 | 3/6 | -1,231.30 | 0.790 |
| Order Block Continuation | 0.663 | 0.051 | **0.077** | 0/6 | **-14,059.11** | 0.667 |
| Volume Node Reversal | 0.781 | 0.216 | 0.277 | 0/6 | -4,971.40 | 0.768 |
| Fair Value Gap Rebalance | 0.815 | 0.109 | 0.134 | 1/6 | -7,061.39 | 0.801 |

CV = coefficient of variation of monthly profit factor across the 6
out-of-sample months (lower = more stable behavior month to month —
not a statement about whether that behavior is good).

---

## Answers

**1. Which setups remain consistent?**
By statistical stability (low variance in monthly profit factor):
**Order Block Continuation is by far the most consistent** (CV=0.077,
every month's PF within a narrow 0.612–0.737 band). Fair Value Gap
Rebalance is second (CV=0.134). This needs an immediate caveat:
consistency here describes *stability of a bad result*, not stability
of a good one — see Question 3.

**2. Which setups completely break down?**
None fail catastrophically in the sense of a sign-reversal producing
runaway losses. The closest to a "breakdown" is Liquidity Sweep
Reversal's March 2024 (PF 0.473, expectancy -45.08, net -1,127.08 — its
single worst month across the entire study, worse than its own original
window). The more concerning pattern belongs to Order Block
Continuation: not a breakdown in one month, but a *sustained* failure
to ever cross breakeven — 0 of 6 months profitable, and drawdown
consistently 23–37% versus the 13.26% that helped justify its original
approval.

**3. Do the APPROVED decisions remain justified?**

*Liquidity Sweep Reversal — partially.* This is genuinely the most
interesting result in the study: 3 of 6 out-of-sample months show real,
positive edge (PF 1.24–1.48, expectancy +16 to +29 per trade), and 3
show real losses (PF 0.25–0.65). The original approval was never a
claim of guaranteed profitability (its own original PF was 0.922, a
marginal number) — the out-of-sample data is consistent with a setup
that has genuine, regime-dependent edge rather than no edge at all.
The split is also suspiciously clean: Jan–Mar uniformly negative,
Apr–Jun uniformly positive, which reads as a real regime effect worth
a dedicated future investigation, not noise (see Question 7). Verdict:
the approval is not refuted, but it should no longer be described as
"a setup that works" without the qualifier "conditional on regime."

*Order Block Continuation — no, not on this evidence.* Every single
out-of-sample month is worse than the backtest that led to approval —
lower profit factor in 6 of 6 months, and drawdown roughly double-to-
triple the original in every month (23–37% vs. 13.26%). This is not one
bad month; it is six consecutive confirmations of the same negative
result, which is exactly the kind of low-variance signal that should
be trusted *more*, not less, than a single noisy window. Stated
plainly: **this result calls the original approval into serious
question.**

**4. Do the RESEARCH ARCHIVE decisions remain justified?**

*Volume Node Reversal — yes, and the picture is somewhat better than
the archived report suggested.* In 5 of 6 out-of-sample months, profit
factor sits in the 0.80–0.92 range — materially closer to breakeven
than the original window's 0.411, which now looks like it may have
been an unusually harsh sample for this setup specifically. May 2024
(PF 0.349) shows the original's severity can recur, so this is not a
reversal of the archive decision — it is still 0/6 profitable months —
but it reinforces that "RESEARCH ARCHIVE, not REJECTED" was the
correct, proportionate call: there is more real signal here than the
single worst-case window implied.

*Fair Value Gap Rebalance — yes, with the opposite correction.* Most
2024 months (5 of 6) are *worse* than the original's near-breakeven
0.992 profit factor, landing instead in the 0.70–0.81 range — the
original window now looks like it may have been closer to a favorable
outlier than a representative sample. June 2024 (PF 1.023, the only
profitable out-of-sample month for this setup) shows the earlier
"closest to breakeven of any setup measured" framing wasn't wrong, just
not typical. RESEARCH ARCHIVE remains the right, cautious categorization
either way.

**5. Do the REJECTED decisions remain justified?**
**Unresolved by this study.** SMT Reversal could not be evaluated
out-of-sample at all — no ETHUSDT data exists for any 2024 month. Its
REJECTED status was grounded in two independent facts from the original
research: the worst measured standalone performance of any setup
(PF 0.334) and a *structural*, data-independent finding (its two
evidence conditions were proven, by the tracker's own definitions, to
be non-discriminating — not merely correlated in one sample). That
second reason does not require out-of-sample reconfirmation, since it
is a logical property of the code, not a backtest artifact. The first
reason — that it was simply the worst-performing setup measured —
remains untested beyond the original 30-day window, and that gap should
be stated honestly rather than assumed to resolve in either direction.

**6. Which setup generalizes best?**
Depends on which question is being asked, and both readings deserve
stating rather than picking one:
- **By evidence of genuine positive edge existing at all**: Liquidity
  Sweep Reversal, uniquely — it is the only setup that crossed profit
  factor 1.0 with real margin (1.24–1.48) in more than one out-of-sample
  month (3 of 6).
- **By pooled aggregate profit factor across all six months**: Fair
  Value Gap Rebalance (0.801) and Liquidity Sweep Reversal (0.790) are
  effectively tied, both ahead of Volume Node Reversal (0.768) and
  clearly ahead of Order Block Continuation (0.667, worst by a wide
  margin on every measure — aggregate PF, monthly consistency of
  failure, and drawdown).
- Order Block Continuation, despite being the most *statistically
  consistent*, generalizes worst in the sense that actually matters —
  it reliably fails to be profitable.

**7. Which setup is most regime-dependent?**
**Liquidity Sweep Reversal, clearly and by a wide margin** — highest
coefficient of variation (0.560, more than double the next-highest),
the widest profit-factor range of any setup in the study (0.251 to
1.479), and a striking temporal split (uniformly bad Jan–Mar, uniformly
good Apr–Jun) that looks like a genuine regime effect rather than
random month-to-month noise. This is directionally consistent with the
setup's own institutional thesis — a liquidity-sweep-and-reversal
setup is generally expected to behave differently in choppy/ranging
conditions than in strongly trending ones — but confirming that
specific hypothesis would require reading `structure["market_
structure"]` per month, which is a natural next step, not attempted in
this validation pass.

---

## Honest overall conclusion

This out-of-sample pass does not uniformly confirm or uniformly
overturn the prior research. It does something more useful: it
sharpens each verdict.

- **Order Block Continuation's approval looks the weakest of anything
  in the Setup Library** once measured against data it has never seen
  — six consecutive months of worse profitability and roughly double
  the drawdown that helped justify approving it in the first place.
  This is the one finding in this report that should change how the
  project treats an existing decision, not just add color to it.
- **Liquidity Sweep Reversal is real but conditional** — the only
  setup in the library with genuine, repeated, non-marginal
  out-of-sample profitability, concentrated in specific months, not
  spread evenly. Its approval survives, with an added, evidence-backed
  caveat about regime dependency that wasn't previously characterized.
- **Both archived setups look roughly where they were left** — neither
  jumps to clearly profitable nor collapses to clearly worthless; the
  original single-window verdicts were reasonable, if not perfectly
  representative in either direction.
- **SMT Reversal's rejection remains only partially tested** — its
  strongest justification (the structural, non-discriminating-evidence
  finding) doesn't need re-confirmation, but its performance-based
  justification does, and this study could not provide that
  confirmation for lack of data.

No parameter was tuned to produce this outcome, and none of these
conclusions were available before this backtest ran.
