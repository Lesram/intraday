"""Audit 2026-06-09 finding 3.3 — fail-closed execution mode & risk breakers.

Previously: TRADING_EXECUTION_MODE defaulted to "execute" (missing env var
= send real orders) and the dollar circuit breakers defaulted to 0 =
disabled, with nothing preventing an execute-mode start without them.

Verifies:
1. Missing/unrecognized TRADING_EXECUTION_MODE resolves to "shadow".
2. Explicit paper/live/execute still resolve to "execute".
3. Engine startup guard raises in execute mode with breakers disabled.
4. Guard is wired into OrganismLiveEngine.__init__ (structural).
5. Shadow/dry_run modes are unaffected by the guard.
"""

import inspect

import pytest

from backend.config.settings import AppSettings
from backend.organism import live_engine as le
from backend.organism.live_engine import OrganismLiveEngine


# ── 1–2. Execution-mode resolution ───────────────────────────────────


def test_missing_mode_resolves_to_shadow(monkeypatch):
    monkeypatch.delenv("TRADING_EXECUTION_MODE", raising=False)
    assert AppSettings().trading_execution_mode == "shadow"


def test_unrecognized_mode_resolves_to_shadow(monkeypatch):
    monkeypatch.setenv("TRADING_EXECUTION_MODE", "bananas")
    assert AppSettings().trading_execution_mode == "shadow"


@pytest.mark.parametrize("raw", ["paper", "live", "execute", "PAPER", " Live "])
def test_explicit_execution_aliases_still_execute(monkeypatch, raw):
    monkeypatch.setenv("TRADING_EXECUTION_MODE", raw)
    assert AppSettings().trading_execution_mode == "execute"


@pytest.mark.parametrize("raw", ["shadow", "dry_run"])
def test_non_executing_modes_pass_through(monkeypatch, raw):
    monkeypatch.setenv("TRADING_EXECUTION_MODE", raw)
    assert AppSettings().trading_execution_mode == raw


# ── 3–5. Startup guard ───────────────────────────────────────────────


def _force_mode(monkeypatch, mode: str):
    """Make the guard see a given effective mode regardless of env."""
    import backend.services.trading_execution_mode as tem

    real = tem.get_trading_execution_mode

    def fake():
        state = real()
        object.__setattr__(state, "mode", mode) if hasattr(state, "__dataclass_fields__") else None
        return state

    # Simpler: stub with a minimal namespace exposing .mode
    class _S:
        pass

    s = _S()
    s.mode = mode
    monkeypatch.setattr(tem, "get_trading_execution_mode", lambda: s)


def test_guard_raises_in_execute_mode_with_breakers_disabled(monkeypatch):
    _force_mode(monkeypatch, "execute")
    monkeypatch.setattr(le, "MAX_DAILY_LOSS", 0.0)
    monkeypatch.setattr(le, "MAX_NOTIONAL_PER_TRADE", 0.0)
    with pytest.raises(RuntimeError, match="REFUSING TO START"):
        OrganismLiveEngine._assert_risk_limits_armed()


def test_guard_raises_when_only_daily_loss_disabled(monkeypatch):
    _force_mode(monkeypatch, "execute")
    monkeypatch.setattr(le, "MAX_DAILY_LOSS", 0.0)
    monkeypatch.setattr(le, "MAX_NOTIONAL_PER_TRADE", 2000.0)
    with pytest.raises(RuntimeError, match="ORGANISM_MAX_DAILY_LOSS"):
        OrganismLiveEngine._assert_risk_limits_armed()


def test_guard_passes_in_execute_mode_with_breakers_armed(monkeypatch):
    _force_mode(monkeypatch, "execute")
    monkeypatch.setattr(le, "MAX_DAILY_LOSS", 1100.0)
    monkeypatch.setattr(le, "MAX_NOTIONAL_PER_TRADE", 2000.0)
    OrganismLiveEngine._assert_risk_limits_armed()  # must not raise


@pytest.mark.parametrize("mode", ["shadow", "dry_run"])
def test_guard_noop_outside_execute_mode(monkeypatch, mode):
    _force_mode(monkeypatch, mode)
    monkeypatch.setattr(le, "MAX_DAILY_LOSS", 0.0)
    monkeypatch.setattr(le, "MAX_NOTIONAL_PER_TRADE", 0.0)
    OrganismLiveEngine._assert_risk_limits_armed()  # must not raise


def test_guard_wired_into_engine_init():
    src = inspect.getsource(OrganismLiveEngine.__init__)
    assert "_assert_risk_limits_armed()" in src, (
        "engine __init__ must call the fail-closed risk-limit guard"
    )
