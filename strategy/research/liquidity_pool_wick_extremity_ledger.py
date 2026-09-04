"""
Research-only touch ledger for the Wick-Extremity Zone ablation.

Production's `LiquidityPool.register_touch` (strategy/features/
liquidity_pool.py) only retains `contributing_touches` (timestamps) and
`sources` (deduplicated source-type strings) - per-touch
(price, source, timestamp) triples, and the exact session/equal-level
snapshot state that contributed a given touch, are discarded. This
module captures that granularity via a temporary, uninstallable
monkeypatch of `LiquidityPool.register_touch` (calls the real,
unmodified method FIRST, with unmodified arguments, then only observes)
plus per-instance wrapping of one `LiquidityPoolTracker` instance's own
`_detect_new_equal_level_candidates` / `_detect_new_session_candidates`
(each wrapper delegates to the original bound method unchanged; it only
additionally stashes the exact contributing cluster/period dict, keyed
by the (direction, price, timestamp, source) it is about to produce, so
the touch ledger can attach it once `register_touch` fires).

`strategy/features/liquidity_pool.py` is not modified. The patch is
installed only for the duration of one research harness run (one
tracker at a time, matching how this project always replays a single
LiquidityPoolTracker per backtest run) and `uninstall()` restores the
exact original method, verified in
tests/test_liquidity_pool_wick_extremity_ledger.py.
"""

from dataclasses import dataclass
from typing import Any, Callable

from strategy.features.liquidity_pool import LiquidityPool, LiquidityPoolTracker

_original_register_touch = LiquidityPool.register_touch
_patch_installed = False
_active_context_store: dict[tuple[Any, ...], dict[str, Any]] | None = None
_active_ledger: list[dict[str, Any]] | None = None


def _instrumented_register_touch(
    self: LiquidityPool,
    price: float,
    timestamp: Any,
    bar_index: int,
    source: str,
) -> None:
    _original_register_touch(self, price, timestamp, bar_index, source)

    if _active_ledger is None:
        return

    source_context = None
    if _active_context_store is not None:
        source_context = _active_context_store.pop((self.direction, price, timestamp, source), None)

    _active_ledger.append({
        "pool_id": (self.direction, self.created_at),
        "direction": self.direction,
        "price": price,
        "timestamp": timestamp,
        "bar_index": bar_index,
        "source": source,
        "zone_high_after": self.zone_high,
        "zone_low_after": self.zone_low,
        "source_context": source_context,
    })


@dataclass
class TouchLedgerHandle:
    ledger: list[dict[str, Any]]
    uninstall: Callable[[], None]


def install_touch_ledger(tracker: LiquidityPoolTracker) -> TouchLedgerHandle:
    """
    Installs the touch ledger on ONE tracker instance. Only one
    installation may be active process-wide at a time (matches this
    project's own one-tracker-per-replay convention); call the returned
    handle's `uninstall()` before installing on another tracker.
    """

    global _patch_installed, _active_context_store, _active_ledger

    if _active_ledger is not None:
        raise RuntimeError(
            "a touch ledger is already installed - uninstall it before "
            "installing a new one"
        )

    context_store: dict[tuple[Any, ...], dict[str, Any]] = {}
    ledger: list[dict[str, Any]] = []

    original_detect_eql = tracker._detect_new_equal_level_candidates
    original_detect_session = tracker._detect_new_session_candidates

    def wrapped_detect_eql(equal_levels_snapshot: dict[str, Any]) -> None:
        for cluster in equal_levels_snapshot.get("equal_highs", []):
            key = (cluster["direction"], cluster["created_at"])
            if key not in tracker._seen_eqh_keys:
                context_store[("buy_side", cluster["level"], cluster["created_at"], "equal_highs")] = dict(cluster)

        for cluster in equal_levels_snapshot.get("equal_lows", []):
            key = (cluster["direction"], cluster["created_at"])
            if key not in tracker._seen_eql_keys:
                context_store[("sell_side", cluster["level"], cluster["created_at"], "equal_lows")] = dict(cluster)

        original_detect_eql(equal_levels_snapshot)

    def wrapped_detect_session(session_snapshot: dict[str, Any]) -> None:
        for name, data in session_snapshot.items():
            for period in data.get("closed", []):
                key = (name, period["period_start"])
                if key not in tracker._seen_session_keys:
                    context_store[("buy_side", period["session_high"], period["high_timestamp"], "session_high")] = dict(period)
                    context_store[("sell_side", period["session_low"], period["low_timestamp"], "session_low")] = dict(period)

        original_detect_session(session_snapshot)

    tracker._detect_new_equal_level_candidates = wrapped_detect_eql
    tracker._detect_new_session_candidates = wrapped_detect_session

    _active_context_store = context_store
    _active_ledger = ledger

    if not _patch_installed:
        LiquidityPool.register_touch = _instrumented_register_touch
        _patch_installed = True

    def uninstall() -> None:
        global _patch_installed, _active_context_store, _active_ledger
        tracker._detect_new_equal_level_candidates = original_detect_eql
        tracker._detect_new_session_candidates = original_detect_session
        if _patch_installed:
            LiquidityPool.register_touch = _original_register_touch
            _patch_installed = False
        _active_context_store = None
        _active_ledger = None

    return TouchLedgerHandle(ledger=ledger, uninstall=uninstall)
