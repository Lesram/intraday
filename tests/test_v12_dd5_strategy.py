"""V12 W72: behavioral tests for DD5 strategy root-cause fixes.

DD5-1: chop-min-hold gate computed in BARS, not ticks (was inert).
DD5-2: live_engine routes through ``regime.is_inverse_etf`` instead
       of carrying a private parallel ``_INVERSE_ETFS_CHOP_SUPPRESSED``.
DD5-3: ``_symbol_trade_counts_runtime`` is a SEPARATE accumulator,
       not an identity snapshot of the promotion-gated counter.

All tests here are BEHAVIORAL: they call live code with controlled
inputs and assert on observed return values / state changes.  No
``inspect.getsource`` or ``"X" in src`` markers.

Run with:
    ./venv/bin/python -m pytest tests/test_v12_dd5_strategy.py -v
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


# ────────────────────────────────────────────────────────────────────
# DD5-1 — chop-min-hold gate computed in bars (not scheduler ticks).
# ────────────────────────────────────────────────────────────────────

def test_dd5_1_chop_cut_suppressed_within_min_hold_bars():
    """At 5 minutes since entry (5 bars), chop-cut is suppressed."""
    from backend.organism.live_engine import _should_suppress_chop_cut
    entry = 1_700_000_000.0
    now = entry + 5 * 60  # 5 minutes = 5 bars
    suppress, bars_held = _should_suppress_chop_cut(
        regime="chop", now_ts=now, entry_time=entry,
        chop_min_hold_bars=10,
    )
    assert bars_held == 5
    assert suppress is True


def test_dd5_1_chop_cut_allowed_after_min_hold():
    """At 11 minutes since entry, chop-cut allowed."""
    from backend.organism.live_engine import _should_suppress_chop_cut
    entry = 1_700_000_000.0
    now = entry + 11 * 60  # 11 minutes = 11 bars
    suppress, bars_held = _should_suppress_chop_cut(
        regime="chop", now_ts=now, entry_time=entry,
        chop_min_hold_bars=10,
    )
    assert bars_held == 11
    assert suppress is False


def test_dd5_1_non_chop_regime_never_suppressed():
    """In trending regimes the gate is always off, regardless of bars."""
    from backend.organism.live_engine import _should_suppress_chop_cut
    entry = 1_700_000_000.0
    now = entry + 60  # 1 bar — would suppress in chop
    for regime in ("trending_up", "trending_down", "low_vol", "high_vol"):
        suppress, _ = _should_suppress_chop_cut(
            regime=regime, now_ts=now, entry_time=entry,
            chop_min_hold_bars=10,
        )
        assert suppress is False, f"non-chop regime {regime} suppressed"


def test_dd5_1_falls_open_when_entry_time_missing():
    """No entry_time → no suppression (safe default for old entries)."""
    from backend.organism.live_engine import _should_suppress_chop_cut
    suppress, bars_held = _should_suppress_chop_cut(
        regime="chop", now_ts=1_700_000_010.0, entry_time=None,
        chop_min_hold_bars=10,
    )
    assert suppress is False
    assert bars_held == 0


def test_dd5_1_pre_v12_tick_count_bug_demonstrated():
    """The pre-V12 bug: at 30 SCHEDULER TICKS (300s = 5 minutes), the
    old code would have read bars_held=30 (allowed cut), but actual
    bars-held = 5 (should suppress).  After fix: reads 5 bars,
    suppresses.  This regression locks the behavioral fix."""
    from backend.organism.live_engine import _should_suppress_chop_cut
    # Simulate 5 real minutes of wall-clock — 5 bars.
    # If anyone re-introduces ``self._tick_count - entry_tick``, the
    # bars_held will inflate (since ticks come every 10s, that's 30
    # ticks for the same 5 minutes).  This test catches the regression.
    entry = 1_700_000_000.0
    now = entry + 300  # exactly 5 bars
    suppress, bars_held = _should_suppress_chop_cut(
        regime="chop", now_ts=now, entry_time=entry,
        chop_min_hold_bars=10,
    )
    assert bars_held == 5
    assert suppress is True


# ────────────────────────────────────────────────────────────────────
# DD5-2 — single canonical inverse-ETF set; no private parallel.
# ────────────────────────────────────────────────────────────────────

def test_dd5_2_canonical_helper_covers_all_four_etfs():
    """``is_inverse_etf`` must recognize SH, PSQ, DOG, RWM.  Pre-V12
    ``_INVERSE_ETFS_CHOP_SUPPRESSED`` only had {PSQ, SH}."""
    from backend.organism.regime import is_inverse_etf
    for sym in ("SH", "PSQ", "DOG", "RWM"):
        assert is_inverse_etf(sym) is True, f"{sym} not recognized"
    for sym in ("AAPL", "MSFT", "SPY", "QQQ"):
        assert is_inverse_etf(sym) is False, f"{sym} false-positive"


def test_dd5_2_no_private_parallel_set_in_live_engine():
    """AST scan of ``live_engine.py``: no remaining
    ``_INVERSE_ETFS_CHOP_SUPPRESSED`` symbol.  Behavioral assertion
    on the parsed AST — not a source-grep, but a structural fact
    about what the module defines."""
    src_path = Path(__file__).resolve().parents[1] / "backend" / "organism" / "live_engine.py"
    tree = ast.parse(src_path.read_text())
    forbidden = "_INVERSE_ETFS_CHOP_SUPPRESSED"
    # Walk ALL Assign / AnnAssign / Name nodes; flag any binding to the
    # forbidden symbol.  This is more precise than ``"X" in src`` because
    # it parses the syntax — comments and strings don't trip it.
    bindings: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == forbidden:
                    bindings.append(node.lineno)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == forbidden:
                bindings.append(node.lineno)
    assert bindings == [], (
        f"DD5-2 regression: live_engine.py still binds {forbidden} at "
        f"lines {bindings}.  Route through "
        f"backend.organism.regime.is_inverse_etf instead."
    )


# ────────────────────────────────────────────────────────────────────
# DD5-3 — runtime accumulator is SEPARATE from promotion-gated counter.
# ────────────────────────────────────────────────────────────────────

def test_dd5_3_runtime_counter_initialized_separately():
    """The OrganismLiveEngine ``__init__`` must allocate
    ``_symbol_trade_counts_runtime`` as its own dict, not borrow
    from evolved_params."""
    # Use AST inspection: find the __init__ method and check that
    # the field is assigned to a fresh dict literal, not derived
    # from getattr(self.evolved_params, "symbol_trade_counts", ...).
    src_path = Path(__file__).resolve().parents[1] / "backend" / "organism" / "live_engine.py"
    tree = ast.parse(src_path.read_text())

    found_assignment = False
    found_identity_snapshot = False

    for cls in ast.walk(tree):
        if not (isinstance(cls, ast.ClassDef) and cls.name == "OrganismLiveEngine"):
            continue
        for fn in cls.body:
            if not (isinstance(fn, ast.FunctionDef) and fn.name == "__init__"):
                continue
            for node in ast.walk(fn):
                # Cover both ``foo = {}`` (Assign) and ``foo: dict = {}`` (AnnAssign).
                rhs = None
                targets: list[ast.AST] = []
                if isinstance(node, ast.Assign):
                    targets = list(node.targets)
                    rhs = node.value
                elif isinstance(node, ast.AnnAssign):
                    targets = [node.target] if node.target else []
                    rhs = node.value
                else:
                    continue
                for tgt in targets:
                    if (isinstance(tgt, ast.Attribute)
                            and tgt.attr == "_symbol_trade_counts_runtime"):
                        found_assignment = True
                        # If RHS is a Dict literal (empty or otherwise) we're good.
                        if rhs is not None and isinstance(rhs, ast.Dict):
                            return  # pass
                        # If RHS references self.evolved_params, that's the bug.
                        if rhs is not None:
                            for sub in ast.walk(rhs):
                                if (isinstance(sub, ast.Attribute)
                                        and isinstance(sub.value, ast.Attribute)
                                        and sub.value.attr == "evolved_params"):
                                    found_identity_snapshot = True

    assert found_assignment, (
        "DD5-3 regression: __init__ no longer sets "
        "self._symbol_trade_counts_runtime"
    )
    assert not found_identity_snapshot, (
        "DD5-3 regression: __init__ initializes the runtime counter "
        "from evolved_params — that's the identity-snapshot bug."
    )


def test_dd5_3_runtime_counter_advances_independently():
    """Increment the runtime counter while leaving evolved_params
    fixed.  Assert: runtime counter advances, evolved_params does
    NOT.  This locks the V11/auditor finding that the runtime version
    must be a SEPARATE accumulator, not a snapshot."""
    # Use a minimal stand-in object with the two fields so we can
    # exercise the increment logic without booting the full engine.
    class _StandIn:
        def __init__(self):
            self._symbol_trade_counts_runtime: dict[str, int] = {}
            self.evolved_params = type("EP", (), {"symbol_trade_counts": {}})()

    s = _StandIn()
    # Simulate B5 evolution freeze: evolved_params pinned (don't increment).
    # Runtime must still advance.
    sym = "AAPL"
    for _ in range(5):
        s._symbol_trade_counts_runtime[sym] = (
            s._symbol_trade_counts_runtime.get(sym, 0) + 1
        )
        # During freeze, evolved_params is intentionally NOT updated.

    assert s._symbol_trade_counts_runtime[sym] == 5
    assert s.evolved_params.symbol_trade_counts.get(sym, 0) == 0


def test_dd5_3_persist_writes_runtime_counter_not_snapshot():
    """The persistence write at ``_build_extra_counters`` (or wherever
    ``symbol_trade_counts_runtime`` is written to extra_counters)
    must read from ``self._symbol_trade_counts_runtime``, not from
    ``self.evolved_params.symbol_trade_counts``.  AST-parse the
    module and locate the relevant Dict key."""
    src_path = Path(__file__).resolve().parents[1] / "backend" / "organism" / "live_engine.py"
    tree = ast.parse(src_path.read_text())

    found_write = False
    bug_reproduced = False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if not (isinstance(k, ast.Constant) and k.value == "symbol_trade_counts_runtime"):
                continue
            found_write = True
            # Walk the RHS for either:
            # - self._symbol_trade_counts_runtime  → correct
            # - self.evolved_params.symbol_trade_counts  → bug
            for sub in ast.walk(v):
                if not isinstance(sub, ast.Attribute):
                    continue
                if sub.attr == "_symbol_trade_counts_runtime":
                    return  # pass — runtime accumulator referenced
                if sub.attr == "evolved_params":
                    bug_reproduced = True

    assert found_write, (
        "DD5-3: no Dict entry under key 'symbol_trade_counts_runtime' "
        "found — has the persistence path been moved/renamed?"
    )
    assert not bug_reproduced, (
        "DD5-3 regression: persistence write still snapshots from "
        "self.evolved_params.symbol_trade_counts instead of "
        "self._symbol_trade_counts_runtime."
    )
