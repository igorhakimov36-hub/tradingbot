from datetime import datetime, timedelta, timezone

import pytest

from strategy.market_intelligence_snapshot import build_market_intelligence_snapshot

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _base_kwargs(**overrides):
    kwargs = dict(
        symbol="BTCUSDT",
        timeframe="15m",
        timestamp=START,
        current_price=100.0,
    )
    kwargs.update(overrides)
    return kwargs


# =========================================================
# Empty / partial input handling
# =========================================================


def test_snapshot_with_no_trackers_wired_is_valid_but_empty():
    snap = build_market_intelligence_snapshot(**_base_kwargs())

    assert snap.zones == []
    assert snap.levels == []
    assert snap.structure["bos"] == "NO_BOS"
    assert snap.order_flow == {"delta": {}, "cvd": {}}
    assert snap.sessions == {"active_now": [], "previous_period_high_low": {}}
    assert snap.intermarket == {}
    assert snap.data_quality == {}


def test_structure_passed_through_when_provided():
    ms_snapshot = {
        "market_structure": "BULLISH",
        "last_swing_high": 110.0,
        "last_swing_low": 95.0,
        "bos": "BULLISH_BOS",
        "choch": "NO_CHOCH",
        "timeframe": "15m",
        "context": {},
    }

    snap = build_market_intelligence_snapshot(**_base_kwargs(market_structure=ms_snapshot))

    assert snap.structure == ms_snapshot


# =========================================================
# Zones - unifying FVG / Order Block / Breaker Block / Liquidity Pool
# =========================================================


def _fvg_entry(direction="bullish", zone_high=105.0, zone_low=100.0, fill_status="active", fill_pct=0.0):
    return {
        "direction": direction, "zone_high": zone_high, "zone_low": zone_low,
        "created_at": START, "timeframe": "15m", "age_in_bars": 3,
        "gap_size": zone_high - zone_low, "gap_size_atr_ratio": 0.5, "atr_at_creation": 2.0,
        "formation_volume": 10.0, "fill_status": fill_status, "fill_pct": fill_pct,
        "distance_from_price": 0.0, "context": {},
    }


def test_active_fvg_maps_to_a_zone_with_correct_status_and_position():
    fvg_snapshot = {"active": [_fvg_entry()], "filled": [], "expired_count": 0}

    snap = build_market_intelligence_snapshot(**_base_kwargs(current_price=102.0, fair_value_gaps=fvg_snapshot))

    assert len(snap.zones) == 1
    zone = snap.zones[0]
    assert zone.kind == "fvg"
    assert zone.status == "active"
    assert zone.zone_relative_position == "inside_price"  # 102 is within [100,105]
    assert zone.resolution_detail == "active"
    assert zone.resolution_pct == 0.0
    assert zone.source_module == "fair_value_gap"
    assert zone.raw == _fvg_entry()


def test_filled_fvg_maps_to_resolved_status():
    fvg_snapshot = {"active": [], "filled": [_fvg_entry(fill_status="completely_filled", fill_pct=1.0)], "expired_count": 0}

    snap = build_market_intelligence_snapshot(**_base_kwargs(fair_value_gaps=fvg_snapshot))

    assert snap.zones[0].status == "resolved"
    assert snap.zones[0].resolution_detail == "completely_filled"
    assert snap.zones[0].resolved_at is None  # FVG never tracked a fill timestamp


def test_zone_relative_position_above_and_below():
    fvg_snapshot = {"active": [_fvg_entry(zone_high=105.0, zone_low=100.0)], "filled": [], "expired_count": 0}

    below = build_market_intelligence_snapshot(**_base_kwargs(current_price=90.0, fair_value_gaps=fvg_snapshot))
    above = build_market_intelligence_snapshot(**_base_kwargs(current_price=200.0, fair_value_gaps=fvg_snapshot))

    assert below.zones[0].zone_relative_position == "above_price"  # zone is ABOVE current price
    assert above.zones[0].zone_relative_position == "below_price"  # zone is BELOW current price


def _order_block_entry(mitigation_status="unmitigated", mitigation_pct=0.0):
    return {
        "direction": "bullish", "zone_high": 105.0, "zone_low": 101.0,
        "created_at": START, "origin_timestamp": START - timedelta(minutes=10),
        "timeframe": "15m", "age_in_bars": 5, "formation_volume": 50.0,
        "atr_at_creation": 2.0, "impulse_strength": 1.5, "touch_count": 2,
        "mitigation_status": mitigation_status, "mitigation_pct": mitigation_pct,
        "distance_from_price": 0.0, "mitigation_zone_high": 104.0,
        "mitigation_zone_low": 101.0, "mitigation_zone_pct": 0.0,
        "mitigation_zone_status": "unmitigated", "context": {},
    }


def test_order_block_maps_with_mitigation_pct_and_touch_count():
    ob_snapshot = {"active": [_order_block_entry(mitigation_status="partially_mitigated", mitigation_pct=0.4)], "mitigated": [], "expired_count": 0}

    snap = build_market_intelligence_snapshot(**_base_kwargs(order_blocks=ob_snapshot))

    zone = snap.zones[0]
    assert zone.kind == "order_block"
    assert zone.resolution_pct == pytest.approx(0.4)
    assert zone.resolution_detail == "partially_mitigated"
    assert zone.touch_count == 2
    assert zone.resolved_at is None  # Order Block never tracked a mitigated_at timestamp


def _breaker_block_entry(mitigation_status="unmitigated", mitigation_pct=0.0):
    return {
        "direction": "bearish", "zone_high": 105.0, "zone_low": 101.0,
        "created_at": START, "source_direction": "bullish",
        "source_origin_timestamp": START - timedelta(minutes=20),
        "timeframe": "15m", "age_in_bars": 2, "atr_at_creation": 2.0,
        "impulse_strength": 0.5, "touch_count": 1,
        "mitigation_status": mitigation_status, "mitigation_pct": mitigation_pct,
        "distance_from_price": 3.0, "context": {},
    }


def test_breaker_block_maps_correctly():
    br_snapshot = {"active": [_breaker_block_entry()], "mitigated": [], "expired_count": 0}

    snap = build_market_intelligence_snapshot(**_base_kwargs(breaker_blocks=br_snapshot))

    zone = snap.zones[0]
    assert zone.kind == "breaker_block"
    assert zone.direction == "bearish"
    assert zone.source_module == "breaker_block"


def _liquidity_pool_entry(swept_status="unswept", swept_timestamp=None):
    return {
        "direction": "buy_side", "level": 103.0, "zone_high": 105.0, "zone_low": 101.0,
        "created_at": START, "timeframe": "15m", "age_in_bars": 4, "bars_since_last_touch": 1,
        "contributing_touches": [START], "touch_count": 2, "sources": ["equal_highs", "round_number"],
        "swept_status": swept_status, "swept_timestamp": swept_timestamp,
        "sweep_penetration": None, "sweep_rejection": None, "distance_from_price": 5.0, "context": {},
    }


def test_liquidity_pool_maps_with_no_resolution_pct_and_swept_timestamp():
    lp_snapshot = {
        "active": [],
        "swept": [_liquidity_pool_entry(swept_status="swept", swept_timestamp=START + timedelta(minutes=5))],
        "expired_count": 0,
    }

    snap = build_market_intelligence_snapshot(**_base_kwargs(liquidity_pools=lp_snapshot))

    zone = snap.zones[0]
    assert zone.kind == "liquidity_pool"
    assert zone.status == "resolved"
    assert zone.resolution_detail == "swept"
    assert zone.resolution_pct is None  # sweeping is binary, no partial-resolution concept
    assert zone.resolved_at == START + timedelta(minutes=5)
    assert zone.raw["sources"] == ["equal_highs", "round_number"]


def test_multiple_zone_kinds_coexist_in_one_unified_list():
    snap = build_market_intelligence_snapshot(
        **_base_kwargs(
            fair_value_gaps={"active": [_fvg_entry()], "filled": [], "expired_count": 0},
            order_blocks={"active": [_order_block_entry()], "mitigated": [], "expired_count": 0},
            breaker_blocks={"active": [_breaker_block_entry()], "mitigated": [], "expired_count": 0},
            liquidity_pools={"active": [_liquidity_pool_entry()], "swept": [], "expired_count": 0},
        )
    )

    kinds = {z.kind for z in snap.zones}
    assert kinds == {"fvg", "order_block", "breaker_block", "liquidity_pool"}
    assert len(snap.zones) == 4


# =========================================================
# Levels - Equal Highs/Lows, Session Boundaries, Volume Profile
# =========================================================


def test_equal_highs_maps_to_a_level_with_swept_bool():
    eq_snapshot = {
        "equal_highs": [{
            "direction": "equal_highs", "level": 108.0, "pivot_prices": [108.0, 108.1],
            "pivot_timestamps": [START], "pivot_count": 2, "max_deviation": 0.1,
            "created_at": START, "timeframe": "15m", "age_in_bars": 3,
            "swept_status": "swept", "swept_timestamp": START, "distance_from_price": 8.0, "context": {},
        }],
        "equal_lows": [], "expired_count": 0,
    }

    snap = build_market_intelligence_snapshot(**_base_kwargs(equal_levels=eq_snapshot))

    assert len(snap.levels) == 1
    level = snap.levels[0]
    assert level.kind == "equal_highs"
    assert level.price == 108.0
    assert level.swept is True
    assert level.distance_from_price == 8.0


def test_session_boundaries_previous_period_becomes_levels_and_active_now():
    session_snapshot = {
        "daily": {
            "current": {"period_start": START, "session_high": 106.0, "session_low": 96.0},
            "closed": [{
                "name": "daily", "period_start": START - timedelta(days=1),
                "period_end": START, "session_high": 105.0, "session_low": 95.0,
                "high_timestamp": START, "low_timestamp": START, "candle_count": 96,
                "is_closed": True, "timeframe": "15m", "context": {},
            }],
        },
        "london_killzone": {"current": None, "closed": []},
    }

    snap = build_market_intelligence_snapshot(**_base_kwargs(current_price=100.0, session_boundaries=session_snapshot))

    assert snap.sessions["active_now"] == ["daily"]
    assert snap.sessions["previous_period_high_low"]["daily"]["session_high"] == 105.0

    level_kinds = {(lvl.kind, lvl.price) for lvl in snap.levels}
    assert ("session_high", 105.0) in level_kinds
    assert ("session_low", 95.0) in level_kinds

    session_high_level = next(lvl for lvl in snap.levels if lvl.kind == "session_high")
    assert session_high_level.distance_from_price == pytest.approx(5.0)  # computed - not natively present


def test_session_with_no_closed_periods_contributes_no_levels():
    session_snapshot = {"daily": {"current": {"period_start": START}, "closed": []}}

    snap = build_market_intelligence_snapshot(**_base_kwargs(session_boundaries=session_snapshot))

    assert snap.levels == []
    assert snap.sessions["previous_period_high_low"] == {}
    assert snap.sessions["active_now"] == ["daily"]


def test_volume_profile_poc_vah_val_hvn_lvn_become_levels():
    vp_snapshot = {
        "current_forming_profile": {
            "poc_price": 100.0, "value_area_high": 105.0, "value_area_low": 95.0,
            "hvn_nodes": [{"price": 100.0, "relative_volume": 2.0, "width": 1}],
            "lvn_nodes": [{"price": 102.0, "relative_volume": 0.1, "width": 1}],
            "data_quality": "approximate",
        },
        "closed_profiles": [],
    }

    snap = build_market_intelligence_snapshot(**_base_kwargs(current_price=110.0, volume_profile=vp_snapshot))

    level_kinds = {lvl.kind for lvl in snap.levels}
    assert level_kinds == {"poc", "vah", "val", "hvn", "lvn"}

    poc_level = next(lvl for lvl in snap.levels if lvl.kind == "poc")
    assert poc_level.price == 100.0
    assert poc_level.distance_from_price == pytest.approx(10.0)

    assert snap.data_quality["volume_profile_data_quality"] == "approximate"


def test_volume_profile_with_no_forming_profile_contributes_no_levels():
    vp_snapshot = {"current_forming_profile": None, "closed_profiles": []}

    snap = build_market_intelligence_snapshot(**_base_kwargs(volume_profile=vp_snapshot))

    assert snap.levels == []


# =========================================================
# Order flow, intermarket, data quality passthrough
# =========================================================


def test_delta_is_passed_through_in_full_including_cumulative():
    delta_snapshot = {
        "timeframe": "15m", "cumulative_delta": 123.0, "bars_accumulated": 10,
        "bars_with_missing_data": 1, "delta": 5.0, "delta_pct": 12.5,
        "delta_direction": "BULLISH", "delta_strength": 12.5,
    }

    snap = build_market_intelligence_snapshot(**_base_kwargs(delta=delta_snapshot))

    assert snap.order_flow["delta"] == delta_snapshot  # unfiltered, exactly as-is
    assert snap.data_quality["delta_bars_with_missing_data"] == 1


def test_cvd_multi_anchor_passthrough():
    cvd_snapshot = {
        "continuous": {"cvd": 50.0, "bars_with_missing_data": 0},
        "daily": {"cvd": 10.0, "bars_with_missing_data": 2},
    }

    snap = build_market_intelligence_snapshot(**_base_kwargs(cvd=cvd_snapshot))

    assert snap.order_flow["cvd"] == cvd_snapshot
    assert snap.data_quality["cvd_bars_with_missing_data"] == {"continuous": 0, "daily": 2}


def test_intermarket_passthrough():
    intermarket_snapshot = {"btc_eth": {"price_correlation": 0.8, "structural_divergence_flag": "none"}}

    snap = build_market_intelligence_snapshot(**_base_kwargs(intermarket=intermarket_snapshot))

    assert snap.intermarket == intermarket_snapshot


# =========================================================
# Purity - determinism, no side effects
# =========================================================


def test_builder_is_a_pure_function():
    fvg_snapshot = {"active": [_fvg_entry()], "filled": [], "expired_count": 0}
    kwargs = _base_kwargs(fair_value_gaps=fvg_snapshot)

    snap_a = build_market_intelligence_snapshot(**kwargs)
    snap_b = build_market_intelligence_snapshot(**kwargs)

    assert snap_a == snap_b
    # The input dict itself must not be mutated by the builder.
    assert fvg_snapshot["active"][0] == _fvg_entry()
