"""
SOL Multi-Module Setup Discovery - predeclared ablation backtests.

Frozen protocol Section 5 names 4 nested comparisons per candidate
(base trigger / trigger+context / trigger+confirmation / trigger+both)
and states explicitly: "Conditions that change entry eligibility also
require real sequential backtests to measure executable results." The
original report ran only the "trigger+both" (full, frozen) variant as
a real backtest; the diagnostic-only opportunity population cannot
substitute for an executable comparison when a condition is REMOVED
from gating (that changes which bars become trades, not just how a
fixed set of trades is scored). This driver completes the two
identifiable ablations (S009's confirmation gate; S011's CVD gate) as
real, executable backtests - same periods, same fixed thresholds, same
risk/cost conventions as the frozen candidates, reusing
`strategy.research.setups.s009_failed_auction_reversal.S009FailedAuctionReversalSetup(require_confirmation=False)`
and `strategy.research.setups.s011_value_area_fade.S011ValueAreaFadeSetup(require_cvd_confirmation=False)` -
a constructor flag, not a redesigned setup, so the underlying
condition logic and thresholds are byte-identical to the frozen
candidates.

S008 has no identifiable ablation backtest this round: its full
(frozen) form already produces zero trades, and per the frozen
protocol's own instruction ("Keep the setup parameters unchanged. Do
not relax thresholds merely to generate trades"), no threshold was
loosened to force a comparison. S008's own explanation is a condition
funnel (counts only, see the report), not a new backtest.
"""

import pickle
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from strategy.market_intelligence_coordinator import MarketIntelligenceCoordinator
from strategy.research.funding_overlay import funding_summary_for_trade, load_funding_records_with_mark_price
from strategy.research.multi_module_backtest_adapter import make_multi_module_callbacks, s009_stop_target, s011_stop_target
from strategy.research.multi_module_standalone_backtest import CANDIDATES as _UNUSED, TRAIN_MONTHS, load_month, SYMBOL
from strategy.research.setups.s009_failed_auction_reversal import S009FailedAuctionReversalSetup
from strategy.research.setups.s011_value_area_fade import S011ValueAreaFadeSetup
from strategy.strategy_engine_v2 import StrategyEngineV2
from strategy.instrument_scale import default_round_number_spacing, default_volume_profile_bucket_size
from backtesting.backtest_runner import BacktestRunner
import time

ABLATIONS = {
    "S009_progress_only": (lambda: S009FailedAuctionReversalSetup(require_confirmation=False), s009_stop_target),
    "S011_extension_only": (lambda: S011ValueAreaFadeSetup(require_cvd_confirmation=False), s011_stop_target),
}


def run_ablation(label, candles_1m, window_manager, provider_specs):
    setup_factory, stop_target_fn = ABLATIONS[label]
    reference_price = candles_1m[0]["close"]
    coordinator = MarketIntelligenceCoordinator(
        symbol=SYMBOL, timeframe="15m",
        round_number_spacing=default_round_number_spacing(reference_price),
        volume_profile_bucket_size=default_volume_profile_bucket_size(reference_price),
    )
    engine = StrategyEngineV2(symbol=SYMBOL, setups=[setup_factory()])
    strategy_callback, trade_setup_callback = make_multi_module_callbacks(engine, coordinator, stop_target_fn)
    runner = BacktestRunner(window_manager=window_manager, candles=candles_1m, symbol=SYMBOL, provider_specs=provider_specs)

    t0 = time.perf_counter()
    result = runner.run_strategy(
        window_name="VALIDATION", strategy_callback=strategy_callback,
        trade_setup_callback=trade_setup_callback, initial_equity=10_000.0,
    )
    elapsed = time.perf_counter() - t0

    trades = []
    opened = list(result.journal.by_event("OPENED"))
    closed = list(result.journal.closed_trades())
    n_orphaned = 0
    if len(opened) == len(closed) + 1:
        n_orphaned = 1
        opened = opened[:-1]
    for o, c in zip(opened, closed):
        trades.append({
            "entry_timestamp": o.timestamp, "exit_timestamp": c.timestamp,
            "side": c.side, "quantity": c.quantity, "entry_price": c.entry_price,
            "exit_price": c.exit_price, "original_stop_loss": o.stop_loss, "original_take_profit": o.take_profit,
            "net_pnl": c.net_pnl, "entry_fee": c.entry_fee, "exit_fee": c.exit_fee, "exit_reason": c.exit_reason,
        })

    return {"trades": trades, "n_orphaned": n_orphaned, "elapsed": elapsed, "total_trades": result.performance.total_trades}


def main(out_path: str) -> None:
    all_results = {}
    for label in ABLATIONS:
        all_results[label] = {}
        for month in TRAIN_MONTHS:
            candles_1m, window_manager, provider_specs = load_month(month)
            r = run_ablation(label, candles_1m, window_manager, provider_specs)
            print(f"{label} / {month}: n={r['total_trades']} orphaned={r['n_orphaned']} ({r['elapsed']:.1f}s)")
            all_results[label][month] = r

    funding_by_month = {
        m: load_funding_records_with_mark_price(str(REPO_ROOT / "data" / f"SOLUSDT-funding-{m}.csv"))
        for m in TRAIN_MONTHS
    }
    for label in ABLATIONS:
        for month in TRAIN_MONTHS:
            fr = funding_by_month[month]
            for t in all_results[label][month]["trades"]:
                summary = funding_summary_for_trade(t["entry_timestamp"], t["exit_timestamp"], t["side"], t["quantity"], fr, boundary="inclusive")
                t["funding_net"] = summary["net"]
                t["net_pnl_after_funding"] = t["net_pnl"] + summary["net"] if summary["net_available"] else t["net_pnl"]

    with open(out_path, "wb") as f:
        pickle.dump(all_results, f)
    print(f"\nSaved to {out_path}")
    print("DONE.")


if __name__ == "__main__":
    default_out = str(REPO_ROOT / "strategy" / "research" / "multi_module_ablation_results.pkl")
    main(sys.argv[1] if len(sys.argv) > 1 else default_out)
