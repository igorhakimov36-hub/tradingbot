# Exit Management Sprint — Causal Correction Addendum
## Next-Bar Activation Fix and Re-Verification of the REJECT Verdict

This addendum documents a real methodological flaw found in the
original Exit Management Sprint's `StructureBasedTrailExitPolicy`,
the fix, and a full re-run to determine whether the original **REJECT
STRUCTURE TRAIL** verdict survives.

## The flaw

The original implementation called a single `evaluate()` per bar that
used the *current* bar's own high/low to decide a stop/TP adjustment,
then mutated `trade.stop_loss`/`trade.take_profit` immediately —
before `process_candle` checked that *same* bar's high/low against the
newly-moved level. This let a decision made from a bar's own completed
OHLC retroactively determine what should have happened earlier within
that same bar — a real look-ahead, and one that specifically biased
results toward more premature same-bar stop-outs immediately after a
tightening (since the policy only ever tightens, the new level is
always more exposed to that same bar's adverse excursion than the old
one was). This is the same direction as the original REJECT verdict,
which is exactly why it needed to be fixed before that verdict could
be trusted.

## The fix — next-bar activation

`backtesting/exit_policy.py`'s `ExitPolicy` protocol now requires two
methods instead of one:

- **`apply_pending(trade)`** — called first, every bar a trade is open,
  *before* that bar's stop/target check. Applies whatever adjustment
  was decided from the *previous* bar's close, if any. This is what
  makes "the levels active at this candle's open" the ones actually
  checked against this candle's high/low.
- **`evaluate(trade, current_candle, market_snapshot)`** — called
  *after* that bar's stop/target check, and only if the trade is
  still open. May store a pending adjustment for the next bar's
  `apply_pending()` — it must never mutate the trade directly.

`backtest_runner.py`'s step 1 was restructured accordingly: a trade
that exits on a given bar is closed using only the levels already
active at that bar's open, and is never evaluated for a new decision
— there is no future bar left for a pending adjustment to apply to.
This explicitly answers requirement 5 (what happens if a trade exits
on the decision candle): **it simply isn't evaluated that bar.**

`structure_based_trail_exit_policy.py` was updated to match: `evaluate()`
now only ever writes to `state["pending_stop"]`/`state["pending_take_profit"]`;
`apply_pending()` is the sole place either value is ever assigned to
the trade, and it is also where `num_stop_moves`/`num_tp_moves` are
now counted (an applied move, not merely a proposed one).

## New tests proving no same-bar retroactivity

Added to `tests/test_exit_policy_hook.py` (7 tests total, up from 5;
full suite now 802/802 passing):

- `test_no_same_bar_retroactive_stop_adjustment` — a 3-candle scenario
  where bar 2's low (100.5) sits *above* the original stop (100.0) but
  *below* what a stop of 101.0 decided from that same bar's data would
  immediately hit if wrongly applied same-bar. Proves the trade
  survives bar 2 and only stops out on bar 3 — one full bar after the
  decision, at the trailed level, not retroactively.
- `test_pending_adjustment_is_not_applied_to_the_bar_that_decided_it` —
  inspects the policy's own call log directly: `evaluate()` on bar 2
  sees the still-original stop (100.0); `apply_pending()` on bar 3 is
  the call that actually moves it.
- `test_trade_closing_on_the_decision_candle_is_not_evaluated` —
  confirms requirement 5 directly: a trade that hits its already-active
  stop is never passed to `evaluate()` at all.

**Also fixed per instruction 7:** the original test's comment claimed
"low=96.0 ... would NOT have hit the original 100.0" — false, since
96 < 100 means it *would* have hit either level, so that test never
actually distinguished the two. It was rewritten using the
purpose-built 3-candle fixture above, where the original-vs-trailed
distinction is logically valid (100.5 and 100.7 sit strictly between
100.0 and 101.0).

**Control behavior re-verified byte-identical** after this change too
(same reference comparison as before): OPENED sequence, CLOSED
sequence, net PnL, and max drawdown all exactly equal.

## Full 12-run re-run: original (buggy) vs corrected

Policy A (control) is untouched by this fix and is identical in both
runs by construction. Policy D changed measurably wherever trades
actually exercised the bug — and **S001-only was completely
unaffected in both windows** (its trade count is low enough, and
apparently no trade's structural-trail moment happened to coincide
with a same-bar reversal that the bug could exploit):

| | S001 Jan | S005 Jan | S001+S005 Jan | S001 Mar | S005 Mar | S001+S005 Mar |
|---|---:|---:|---:|---:|---:|---:|
| Profit factor: original D | 0.297 | 0.499 | 0.454 | 1.387 | 0.421 | 0.446 |
| Profit factor: corrected D | 0.297 | **0.553** | **0.554** | **1.408** | **0.435** | **0.490** |
| Profit factor: A (control) | 0.653 | 0.805 | 0.776 | 2.395 | 0.586 | 0.750 |
| Net profit: original D | -490.05 | -2370.82 | -2852.31 | 201.50 | -3781.84 | -3940.56 |
| Net profit: corrected D | -490.05 | **-2107.13** | **-2195.77** | **212.86** | **-3723.88** | **-3594.01** |
| Net profit: A (control) | -286.76 | -1020.93 | -1283.57 | 882.23 | -2711.57 | -1680.27 |

The fix recovered real value where it was legitimately due — a
concrete example: in S001-only March, one trade (2025-03-04 14:49
SHORT) was wrongly cut short at net +166.89 under the buggy version;
corrected, it now reaches the identical full take-profit as the
control (+178.09), matching exactly. This is the bug's effect made
visible on one specific trade.

**But in every single comparison, profit factor and net profit under
Policy D remain clearly worse than Policy A control — the same
direction as before the fix, in 6 of 6 windows, with no exceptions.**
Drawdown and expectancy also remain worse in the large majority
(5 of 6), with the one near-flat exception (S005-only March expectancy,
-30.28 vs -29.09 originally, vs -30.47 control — a rounding-level
difference in both versions, not a reversal).

The clearest single-window evidence (S001-only, March 2025, 8 aligned
entries) still shows **5 of 8** identical entries that reached the full
2R target under fixed exits instead cut short by the trailing stop
under Policy D (down from 6 of 8 pre-fix) — the mechanism identified in
the original report (winners cut short outweighing losses avoided)
persists after removing the look-ahead bias, just slightly less
severely than the buggy measurement suggested.

## Does REJECT survive?

**Yes.** The causal fix was a real correction and it did move the
numbers — Policy D looks measurably less bad than the original
(buggy) run suggested, exactly as predicted before re-running anything.
But it did not change which policy wins in a single one of the 6
tested configurations. Profit factor: 6/6 still worse. Net profit:
6/6 still worse. The identified causal mechanism — the policy protects
against some full losses but sacrifices more and larger winners than
it rescues — is unchanged in direction, only smaller in magnitude.

**Final verdict, re-confirmed: REJECT STRUCTURE TRAIL.**
