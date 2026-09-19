"""Audit 2026-06-09 finding 3.5 — pyramid gating + idempotency key collisions.

Previously: pyramid adds checked only the ban flag + global halt (skipping
liquidity/fitness gates), and entry/pyramid idempotency keys were identical
for the same symbol+tick (silent dedup of one of two legitimate intents).

Verifies:
1. _passes_entry_gates supports for_pyramid_add mode: presence/sector/
   long_only checks skipped, quality gates (liquidity, fitness, ban) kept.
2. The pyramid add block routes through the shared gate helper.
3. Entry and exit idempotency keys carry intent (reason), side, and qty.
"""

import inspect

import pandas as pd

from backend.organism.live_engine import OrganismLiveEngine


class _EvolvedParams:
    symbol_fitness: dict = {}
    symbol_trade_counts: dict = {}


class _GateShim:
    """Carries only the state _passes_entry_gates touches."""

    _passes_entry_gates = OrganismLiveEngine._passes_entry_gates

    def __init__(self, *, learning=False, banned=(), liquid=True, fitness=None,
                 trade_counts=None):
        self._exit_cooldown = {}
        self._symbol_exit_type = {}
        self._symbol_exit_tick = {}
        self._pending_entry = {}
        self._entry_metadata = {}
        self._symbol_banned = set(banned)
        self._tick_count = 100
        self._STOP_LOSS_REENTRY_TICKS = 10
        self._FTF_LOSS_REENTRY_TICKS = 10
        self._is_learning_mode = learning
        self._liquid = liquid
        self.evolved_params = _EvolvedParams()
        self.evolved_params.symbol_fitness = dict(fitness or {})
        self.evolved_params.symbol_trade_counts = dict(trade_counts or {})

    def _passes_liquidity_gate(self, symbol, features_by_symbol):
        return self._liquid


_FEATS = {"NVDA": pd.DataFrame({"close": [100.0]})}


def test_pyramid_mode_skips_presence_checks_for_open_position():
    shim = _GateShim(learning=True)
    # Symbol IS open and has entry metadata — normal mode rejects...
    shim._entry_metadata["NVDA"] = {"entry_source": "alpha"}
    ok, reason = shim._passes_entry_gates(
        "NVDA", 1.0, _FEATS, {"NVDA"}, set(),
        fitness_gate=0.0, min_trades_for_fitness=10,
    )
    assert not ok and reason == "open_position"
    # ...pyramid mode passes (presence checks are definitionally satisfied).
    ok, reason = shim._passes_entry_gates(
        "NVDA", 1.0, _FEATS, {"NVDA"}, set(),
        fitness_gate=0.0, min_trades_for_fitness=10,
        for_pyramid_add=True,
    )
    assert ok, f"pyramid mode must skip presence checks, got: {reason}"


def test_pyramid_mode_still_blocks_illiquid_symbol():
    shim = _GateShim(learning=True, liquid=False)
    ok, reason = shim._passes_entry_gates(
        "NVDA", 1.0, _FEATS, {"NVDA"}, set(),
        fitness_gate=0.0, min_trades_for_fitness=10,
        for_pyramid_add=True,
    )
    assert not ok and reason == "liquidity"


def test_pyramid_mode_still_blocks_banned_symbol():
    shim = _GateShim(learning=True, banned={"NVDA"})
    ok, reason = shim._passes_entry_gates(
        "NVDA", 1.0, _FEATS, {"NVDA"}, set(),
        fitness_gate=0.0, min_trades_for_fitness=10,
        for_pyramid_add=True,
    )
    assert not ok and reason == "circuit_breaker"


def test_pyramid_mode_still_enforces_fitness_gate():
    shim = _GateShim(
        learning=False,
        fitness={"NVDA": 0.10},        # collapsed fitness
        trade_counts={"NVDA": 50},     # enough trades for the gate to bind
    )
    ok, reason = shim._passes_entry_gates(
        "NVDA", 1.0, _FEATS, {"NVDA"}, set(),
        fitness_gate=0.45, min_trades_for_fitness=10,
        for_pyramid_add=True,
    )
    assert not ok and reason == "fitness_gate"


# ── Structural wiring ────────────────────────────────────────────────


def test_pyramid_block_routes_through_shared_gates():
    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    assert "for_pyramid_add=True" in src, (
        "pyramid add block must call _passes_entry_gates in pyramid mode"
    )


def test_entry_idem_key_includes_intent_side_qty():
    src = inspect.getsource(OrganismLiveEngine._submit_entry_order)
    assert '_{reason}_{side}_q{shares}' in src, (
        "entry idempotency key must include intent/side/qty so a same-tick "
        "entry and pyramid add cannot collide"
    )


def test_exit_idem_key_includes_intent_qty():
    src = inspect.getsource(OrganismLiveEngine._submit_exit_order)
    assert '_{reason}_q{shares}' in src, (
        "exit idempotency key must include intent/qty so distinct same-tick "
        "exit intents cannot collide"
    )
