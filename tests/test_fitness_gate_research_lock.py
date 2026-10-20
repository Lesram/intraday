"""Audit 2026-10-20 (C13-02) — no hard fitness ban while the research policy
is locked.

Under the research lock evolution never runs, so ``symbol_fitness`` is frozen
at its pre-cutoff values while ``symbol_trade_counts`` keep rising. The hard
gate (fitness < 0.45 with >= 10 trades) therefore became a permanent ban fitted
on as few as 10 old trades: XLE and XLK blocked, COST at its 10th close. While
locked, the hard gate is skipped (the soft AlphaScanner multiplier remains);
unlocked semantics are unchanged.
"""
from __future__ import annotations

import pandas as pd

from backend.organism import research_policy
from backend.organism.live_engine import OrganismLiveEngine


class _EvolvedParams:
    symbol_fitness: dict = {}
    symbol_trade_counts: dict = {}


class _GateShim:
    """Carries only the state _passes_entry_gates touches."""

    _passes_entry_gates = OrganismLiveEngine._passes_entry_gates

    def __init__(self, *, fitness=None, trade_counts=None):
        self._exit_cooldown = {}
        self._symbol_exit_type = {}
        self._symbol_exit_tick = {}
        self._pending_entry = {}
        self._entry_metadata = {}
        self._symbol_banned = set()
        self._tick_count = 100
        self._STOP_LOSS_REENTRY_TICKS = 10
        self._FTF_LOSS_REENTRY_TICKS = 10
        self._is_learning_mode = False
        self.evolved_params = _EvolvedParams()
        self.evolved_params.symbol_fitness = dict(fitness or {})
        self.evolved_params.symbol_trade_counts = dict(trade_counts or {})

    def _passes_liquidity_gate(self, symbol, features_by_symbol):
        return True


_FEATS = {"XLE": pd.DataFrame({"close": [90.0]})}


def _gate(shim, **kw):
    return shim._passes_entry_gates(
        "XLE", 1.0, _FEATS, set(), set(),
        fitness_gate=0.45, min_trades_for_fitness=10, **kw,
    )


def test_installed_policy_is_locked():
    # The behaviour below is what runs live only because the lock is on.
    assert research_policy.RESEARCH_POLICY_LOCKED is True


def test_locked_policy_does_not_hard_ban_low_frozen_fitness():
    shim = _GateShim(fitness={"XLE": 0.10}, trade_counts={"XLE": 50})
    assert _gate(shim) == (True, "")


def test_locked_policy_does_not_ban_missing_fitness_with_trades():
    shim = _GateShim(fitness={}, trade_counts={"XLE": 50})
    assert _gate(shim) == (True, "")


def test_locked_policy_does_not_ban_pyramid_adds_on_fitness():
    shim = _GateShim(fitness={"XLE": 0.10}, trade_counts={"XLE": 50})
    assert _gate(shim, for_pyramid_add=True) == (True, "")


def test_unlocked_policy_keeps_the_hard_gate(monkeypatch):
    monkeypatch.setattr(research_policy, "RESEARCH_POLICY_LOCKED", False)
    low = _GateShim(fitness={"XLE": 0.10}, trade_counts={"XLE": 50})
    assert _gate(low) == (False, "fitness_gate")
    missing = _GateShim(fitness={}, trade_counts={"XLE": 50})
    assert _gate(missing) == (False, "fitness_gate")
    few_trades = _GateShim(fitness={"XLE": 0.10}, trade_counts={"XLE": 9})
    assert _gate(few_trades) == (True, "")
    healthy = _GateShim(fitness={"XLE": 0.60}, trade_counts={"XLE": 50})
    assert _gate(healthy) == (True, "")
