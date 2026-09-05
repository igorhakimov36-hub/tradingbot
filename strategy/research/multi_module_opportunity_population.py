"""
SOL Multi-Module Setup Discovery - opportunity-population capture for
the frozen interaction tests (Section 5 of the protocol).

Repaired version (see docs/sol_multi_module_setup_research_report.md,
"Interaction analysis completion" section, for the full account of
what was wrong and why):

- S009's prior capture derived direction from `result.direction`,
  which is populated only once the full candidate fires - this
  silently collapsed the "base" and "base+progress" nested slices to
  the fired-only subset. Fixed by peeking `setup._pending` - the
  causal state the setup itself already carries, fixed at the PRIOR
  bar, strictly before the current bar's own trigger conditions are
  evaluated - never information from a later bar or a successful
  signal. This is a read-only OBSERVATION of state the setup already
  maintains; it does not call any different method or alter what
  evaluate() computes or returns (proven by
  tests/test_multi_module_opportunity_capture_observer.py).
- S011's own capture never depended on result.direction (it already
  read direction from the extension condition's own evidence, which
  exists independent of fire status) - re-audited and confirmed
  correct. What IS genuinely unidentifiable for S011 is scoring a
  forward outcome for the "regime-only, no extension" layer: the base
  opportunity definition (RANGE regime + a forming profile) does not
  by itself imply ANY direction or reference risk (there is no
  natural "which way would this trade go" answer without the
  extension condition's own magnitude/boundary read) - this is a
  structural property of the candidate's own design, not a
  measurement bug, and is reported as an explicit, counted exclusion
  rather than silently omitted or scored with an invented rule.
"""

import pickle
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from data.historical_loader import load_ohlcv_csv
from data.timeframe_manager import TimeframeManager
from strategy.instrument_scale import default_round_number_spacing, default_volume_profile_bucket_size
from strategy.market_intelligence_coordinator import MarketIntelligenceCoordinator
from strategy.research.setups.s008_displacement_continuation import S008DisplacementContinuationSetup
from strategy.research.setups.s009_failed_auction_reversal import S009FailedAuctionReversalSetup
from strategy.research.setups.s011_value_area_fade import S011ValueAreaFadeSetup

SYMBOL = "SOLUSDT"
TRAIN_MONTHS = ["2024-02", "2024-04", "2024-09", "2025-12"]
HORIZON_BARS = 50  # 15m bars => 12.5 hours forward-looking cap for the diagnostic first-passage check


def _coordinator_for_month(candles_1m):
    reference_price = candles_1m[0]["close"]
    return MarketIntelligenceCoordinator(
        symbol=SYMBOL, timeframe="15m",
        round_number_spacing=default_round_number_spacing(reference_price),
        volume_profile_bucket_size=default_volume_profile_bucket_size(reference_price),
    )


def _load_month(month):
    path = REPO_ROOT / "data" / f"{SYMBOL}-1m-{month}.csv"
    candles_1m = load_ohlcv_csv(str(path))
    tf = TimeframeManager(timeframes=["15m"])
    tf.sync(candles_1m)
    return candles_1m, tf.get_history("15m")


def forward_first_passage(candles_15m, idx, entry_price, r_unit, direction, horizon=HORIZON_BARS):
    if r_unit is None or r_unit <= 0:
        return None
    target = entry_price + r_unit if direction == "LONG" else entry_price - r_unit
    stop = entry_price - r_unit if direction == "LONG" else entry_price + r_unit

    for j in range(idx + 1, min(idx + 1 + horizon, len(candles_15m))):
        bar = candles_15m[j]
        if direction == "LONG":
            hit_target = bar["high"] >= target
            hit_stop = bar["low"] <= stop
        else:
            hit_target = bar["low"] <= target
            hit_stop = bar["high"] >= stop
        if hit_target and hit_stop:
            return "AMBIGUOUS"
        if hit_target:
            return "FAVORABLE"
        if hit_stop:
            return "ADVERSE"
    return "NO_RESOLUTION"


# =========================================================
# S008 - direction/r_unit already derivable from the opportunity
# condition's own evidence regardless of fire status (unchanged from
# the original capture - re-verified correct, not modified).
# =========================================================

def walk_s008(month):
    candles_1m, candles_15m = _load_month(month)
    coordinator = _coordinator_for_month(candles_1m)
    setup = S008DisplacementContinuationSetup()

    rows = []
    for i in range(len(candles_15m)):
        visible = candles_15m[: i + 1]
        current_price = visible[-1]["close"]
        snapshot = coordinator.sync_and_build(visible, current_price=current_price, timestamp=visible[-1]["timestamp"])
        result = setup.evaluate(snapshot)

        if not result.required_conditions or not result.required_conditions[0].satisfied:
            continue

        ev = result.required_conditions[0].evidence
        direction = "LONG" if ev["direction"] == "bullish" else "SHORT"
        r_unit = abs(current_price - (ev["zone_low"] if ev["direction"] == "bullish" else ev["zone_high"]))
        outcome = forward_first_passage(candles_15m, i, current_price, r_unit, direction) if r_unit > 0 else None

        rows.append({
            "month": month, "bar_index": i, "timestamp": visible[-1]["timestamp"],
            "condition_flags": {c.name: c.satisfied for c in result.required_conditions},
            "fired": result.fired, "direction": direction, "outcome": outcome,
        })
    return rows


# =========================================================
# S009 - REPAIRED: derive direction/r_unit from setup._pending,
# peeked BEFORE evaluate() is called (the causal state fixed at the
# prior bar), never from result.direction.
# =========================================================

def walk_s009(month):
    candles_1m, candles_15m = _load_month(month)
    coordinator = _coordinator_for_month(candles_1m)
    setup = S009FailedAuctionReversalSetup()

    rows = []
    excluded_zero_risk = 0
    for i in range(len(candles_15m)):
        visible = candles_15m[: i + 1]
        current_price = visible[-1]["close"]
        snapshot = coordinator.sync_and_build(visible, current_price=current_price, timestamp=visible[-1]["timestamp"])

        pending_before = setup._pending  # read-only peek of causal state fixed at a PRIOR bar
        result = setup.evaluate(snapshot)  # real, unmodified call - never skipped, never altered

        if pending_before is None:
            continue  # no base opportunity entering this bar - correctly excluded, not a gap

        direction = pending_before["direction"]
        excursion_close = pending_before["excursion_bar_close"]
        r_unit = abs(current_price - excursion_close)
        if r_unit <= 0:
            excluded_zero_risk += 1
            continue

        outcome = forward_first_passage(candles_15m, i, current_price, r_unit, direction)

        rows.append({
            "month": month, "bar_index": i, "timestamp": visible[-1]["timestamp"],
            "condition_flags": {c.name: c.satisfied for c in result.required_conditions},
            "fired": result.fired, "direction": direction, "outcome": outcome,
        })

    return rows, excluded_zero_risk


# =========================================================
# S011 - re-audited: extension-satisfied layer's direction/r_unit was
# already correctly read from evidence (not result.direction). The
# regime-only ("base", no extension) layer is counted but explicitly
# marked as having no identifiable direction/r_unit - not scored.
# =========================================================

def walk_s011(month):
    candles_1m, candles_15m = _load_month(month)
    coordinator = _coordinator_for_month(candles_1m)
    setup = S011ValueAreaFadeSetup()

    rows = []
    n_regime_only_unscorable = 0
    for i in range(len(candles_15m)):
        visible = candles_15m[: i + 1]
        current_price = visible[-1]["close"]
        snapshot = coordinator.sync_and_build(visible, current_price=current_price, timestamp=visible[-1]["timestamp"])
        result = setup.evaluate(snapshot)

        if not result.required_conditions or not result.required_conditions[0].satisfied:
            continue  # regime condition itself not satisfied - not part of the base population at all

        if len(result.required_conditions) < 2:
            # regime satisfied but no forming profile - base opportunity
            # incomplete per the frozen definition (requires both).
            continue

        extension_ev = result.required_conditions[1].evidence
        if "bucket_size" not in extension_ev:
            # regime + profile present, but extension direction is
            # undefined (price not extended) - counted, not scored.
            n_regime_only_unscorable += 1
            continue

        direction = "SHORT" if "value_area_high" in extension_ev else "LONG"
        r_unit = extension_ev["bucket_size"]
        outcome = forward_first_passage(candles_15m, i, current_price, r_unit, direction)

        rows.append({
            "month": month, "bar_index": i, "timestamp": visible[-1]["timestamp"],
            "condition_flags": {c.name: c.satisfied for c in result.required_conditions},
            "fired": result.fired, "direction": direction, "outcome": outcome,
        })

    return rows, n_regime_only_unscorable


def main(out_path: str) -> None:
    all_rows = {"s008_displacement_continuation": [], "s009_failed_auction_reversal": [], "s011_value_area_fade": []}
    exclusions = {"s009_excluded_zero_risk": 0, "s011_regime_only_unscorable": 0}

    for month in TRAIN_MONTHS:
        rows = walk_s008(month)
        print(f"s008_displacement_continuation / {month}: {len(rows)} base-opportunity bars")
        all_rows["s008_displacement_continuation"].extend(rows)

        rows, excluded = walk_s009(month)
        print(f"s009_failed_auction_reversal / {month}: {len(rows)} base-opportunity bars (excluded_zero_risk={excluded})")
        all_rows["s009_failed_auction_reversal"].extend(rows)
        exclusions["s009_excluded_zero_risk"] += excluded

        rows, unscorable = walk_s011(month)
        print(f"s011_value_area_fade / {month}: {len(rows)} extension-satisfied bars (regime_only_unscorable={unscorable})")
        all_rows["s011_value_area_fade"].extend(rows)
        exclusions["s011_regime_only_unscorable"] += unscorable

    with open(out_path, "wb") as f:
        pickle.dump({"rows": all_rows, "exclusions": exclusions}, f)
    print(f"\nSaved to {out_path}")
    print(f"Exclusions: {exclusions}")
    print("DONE.")


if __name__ == "__main__":
    default_out = str(REPO_ROOT / "strategy" / "research" / "multi_module_opportunity_population.pkl")
    main(sys.argv[1] if len(sys.argv) > 1 else default_out)
