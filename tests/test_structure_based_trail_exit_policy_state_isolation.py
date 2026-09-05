"""
Deterministic state-isolation regression tests for
StructureBasedTrailExitPolicy (Exit Management Sprint, research-only,
never committed). Added by the Exit-Policy State Isolation Impact
Audit; relocated from a session scratchpad into tests/ (still
uncommitted) so this coverage remains recoverable across sessions.

These tests force the id(trade)-collision condition directly (by
monkeypatching the builtin id() to return a fixed value for two
DIFFERENT objects) rather than relying on CPython happening to reuse
a real memory address during the test run - the same requirement
already applied to the Progressive Stop Management sprint's own
regression tests in tests/test_progressive_stop_policies.py.

_OldIdKeyedReferencePolicy below is a minimal, deliberately-defective
reproduction of ONLY the state-lookup mechanism
(trade_log[id(trade)]) that the pre-fix StructureBasedTrailExitPolicy
actually used (apply_pending + trade_log storage) - not used anywhere
in the real research pipeline, kept here solely as the "affected
implementation" reference that this test proves fails, contrasted
directly against the real, current (fixed) StructureBasedTrailExitPolicy
imported from strategy/research/, which must pass the identical
forced-collision condition.
"""

import pytest

from backtesting.execution_simulator import SimulatedTrade
from strategy.research.structure_based_trail_exit_policy import StructureBasedTrailExitPolicy


def _long_trade(entry=100.0, stop=99.0, tp=104.0, qty=10.0):
    return SimulatedTrade(side="LONG", requested_entry=entry, entry_price=entry, stop_loss=stop, take_profit=tp, quantity=qty, entry_fee=0.0)


class _OldIdKeyedReferencePolicy:
    """Deliberately-defective reference: dict keyed by id(trade), matching
    the pre-fix StructureBasedTrailExitPolicy's own apply_pending()."""

    def __init__(self):
        self.trade_log = {}

    def seed_pending_stop(self, trade, pending_stop):
        self.trade_log[id(trade)] = {"pending_stop": pending_stop, "pending_take_profit": None}

    def apply_pending(self, trade):
        state = self.trade_log.get(id(trade))
        if state is None:
            return
        if state["pending_stop"] is not None:
            trade.stop_loss = state["pending_stop"]
            state["pending_stop"] = None


def test_old_id_keyed_reference_leaks_pending_stop_under_forced_id_collision(monkeypatch):
    """Demonstrates the DEFECT deterministically: with id() forced to
    collide (never left to chance), the buggy dict-keyed policy hands
    trade2 a pending stop that was decided for trade1, an entirely
    unrelated trade."""
    policy = _OldIdKeyedReferencePolicy()

    trade1 = _long_trade(entry=100.0, stop=99.0)
    trade2 = _long_trade(entry=200.0, stop=198.0)  # unrelated trade, no adjustment of its own
    assert trade1 is not trade2

    monkeypatch.setattr("builtins.id", lambda obj: 999999)  # force a collision for BOTH lookups

    policy.seed_pending_stop(trade1, pending_stop=99.75)  # trade1's own, legitimate adjustment - stored under the forced key
    policy.apply_pending(trade2)

    # THE DEFECT: trade2 silently received trade1's pending stop.
    assert trade2.stop_loss == pytest.approx(99.75)


def test_fixed_structure_based_trail_policy_immune_to_forced_id_collision(monkeypatch):
    """Same forced collision, against the REAL, CURRENT (fixed)
    StructureBasedTrailExitPolicy. Attribute-based storage must be
    immune by construction: id() is never consulted to find a trade's
    own state, so forcing every trade's id() to collide changes
    nothing about which state a given trade object carries."""
    policy = StructureBasedTrailExitPolicy(coordinator=None)

    trade1 = _long_trade(entry=100.0, stop=99.0)
    setattr(trade1, policy._STATE_ATTR, {
        "pending_stop": 99.75, "pending_take_profit": None,
        "num_stop_moves": 0, "num_tp_moves": 0,
    })

    trade2 = _long_trade(entry=200.0, stop=198.0)  # unrelated, no state of its own yet

    assert trade1 is not trade2
    monkeypatch.setattr("builtins.id", lambda obj: 999999)  # identical forced collision

    policy.apply_pending(trade2)

    # trade2 must be untouched - it never had its own pending_stop set.
    assert trade2.stop_loss == pytest.approx(198.0)
    # trade1's own state must remain independently intact.
    assert trade1.stop_loss == pytest.approx(99.0)  # apply_pending was never called on trade1 here


def test_fixed_policy_two_distinct_trades_never_share_state_object():
    """Direct construction check (no monkeypatch needed): two distinct,
    field-identical trade objects must never resolve to the same
    stored state object under the real (unpatched) id()."""
    policy = StructureBasedTrailExitPolicy(coordinator=None)

    trade_a = _long_trade(entry=100.0, stop=99.0)
    setattr(trade_a, policy._STATE_ATTR, {"pending_stop": 99.5, "pending_take_profit": None})

    trade_b = _long_trade(entry=100.0, stop=99.0)  # identical field values, distinct object
    assert trade_b is not trade_a
    assert getattr(trade_b, policy._STATE_ATTR, None) is None  # no state carried over

    policy.apply_pending(trade_b)
    assert trade_b.stop_loss == pytest.approx(99.0)  # unaffected by trade_a's own pending stop
