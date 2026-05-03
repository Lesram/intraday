"""V8 / Wave-36 (2026-05-03): behavioral tests for decorative subsystem cleanup.

Locks the regressions for:
- NN-CRIT-2: backend/strategies/parity_checker.py was orphan (no live
  callers, only in __init__.py re-export). Deleted.
- NN-CRIT-3: 6 of 8 risk modules truly orphan: black_swan_protection,
  correlation_breakdown, margin_calculator, volatility_checker,
  position_limits, risk_calculator. Deleted. (advanced_risk_manager
  retained because portfolio_optimizer references it; that file is
  itself orphan and tracked for wave 38.)

Wave-36 partial: NN-CRIT-2's full claim ("4,872 LOC of BaseStrategy
subclasses fully decorative") was over-broad — basic.py, engine.py,
trading_strategies.py, types.py, advanced_strategies.py, and
versioning.py ARE reached from live code paths. Only parity_checker
was orphan. NN-HIGH-2 (OrderStateMachine + OrderIntegrityService)
deferred — has tests that imply intent to wire; deferring deletion
prevents losing context. NN-HIGH-3 (SecurityMiddleware helpers): no
action — SecurityHeadersMiddleware IS wired via middleware_setup.py;
the other classes in security_hardening.py are duplicates of
canonical middlewares but tracked for future cleanup.

Run with: ./venv/bin/python -m pytest tests/test_wave36_fixes.py -v
"""
from __future__ import annotations

import os

import pytest


# ─────────────────────────────────────────────────────────────────────
# NN-CRIT-2 / NN-CRIT-3 — orphan modules deleted
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", [
    "backend/strategies/parity_checker.py",
    "backend/risk/black_swan_protection.py",
    "backend/risk/correlation_breakdown.py",
    "backend/risk/margin_calculator.py",
    "backend/risk/volatility_checker.py",
    "backend/risk/position_limits.py",
    "backend/risk/risk_calculator.py",
])
def test_wave36_orphan_module_deleted(path: str):
    """The orphan modules must stay deleted. Re-creation without wiring
    them in would re-introduce the audit-surface cost."""
    assert not os.path.isfile(path), (
        f"NN-CRIT-2/3 regression: {path} re-created. If you need this "
        "logic, wire it into a live import path (lifespan / live_engine "
        "/ a router) AND add a reachability test."
    )


def test_wave36_strategies_init_imports_only_live_modules():
    """backend/strategies/__init__.py re-exports only versioning (M-41)
    which IS reached by strategy_service.py.  parity_checker (M-42) was
    deleted — the re-export must be gone too."""
    # Look at non-comment lines only (preamble explains the deletion).
    code = "\n".join(
        line for line in open("backend/strategies/__init__.py").readlines()
        if not line.lstrip().startswith("#")
    )
    assert "parity_checker" not in code, (
        "NN-CRIT-2 regression: backend/strategies/__init__.py still "
        "imports/re-exports parity_checker. Either undelete the file "
        "(with wiring) or drop the import."
    )
    assert "versioning" in code, (
        "Wave-36 over-cleanup: backend/strategies/__init__.py no longer "
        "re-exports versioning, but strategy_service.py imports it."
    )


def test_wave36_versioning_remains_imported_live():
    """backend/services/strategy_service.py must still successfully import
    versioning, since that import is reached by 3 live route handlers
    (strategy.py, optimizations.py, backtest.py)."""
    from backend.services.strategy_service import StrategyService  # noqa: F401


def test_wave36_no_dangling_risk_imports():
    """No backend code may import from the 6 deleted risk modules."""
    import subprocess
    deleted_modules = [
        "black_swan_protection",
        "correlation_breakdown",
        "margin_calculator",
        "volatility_checker",
        "position_limits",
        "risk_calculator",
    ]
    pat = r"|".join(f"backend\\.risk\\.{m}" for m in deleted_modules)
    out = subprocess.run(
        ["bash", "-c", f"grep -rnE '{pat}' backend/ --include='*.py' || true"],
        capture_output=True, text=True, timeout=10,
    )
    hits = [
        line for line in out.stdout.splitlines()
        if line.strip() and "test_" not in line
    ]
    assert len(hits) == 0, (
        f"Wave-36 regression: {len(hits)} dangling import(s) of deleted "
        f"risk module(s):\n" + "\n".join(hits)
    )
