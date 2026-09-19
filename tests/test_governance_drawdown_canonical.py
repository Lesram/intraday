"""Tests for the canonical drawdown-kill resolution and startup validator.

These tests verify:
  1. Env var override is resolved and source is recorded as "env".
  2. Absence of env var falls back to code default and source is "code_default".
  3. Drift warning fires when env value exceeds 1.5x the code default.
  4. Drift warning does NOT fire when value comes from code default.
"""
from __future__ import annotations

import logging
import os

import pytest

from backend.organism.governance import (
    DEFAULT_DRAWDOWN_KILL_PCT,
    GovernanceController,
)


@pytest.fixture
def clean_env(monkeypatch):
    """Ensure env is reset between tests."""
    monkeypatch.delenv("ORGANISM_DRAWDOWN_KILL_PCT", raising=False)
    monkeypatch.delenv("ORGANISM_DRAWDOWN_COOLDOWN_S", raising=False)
    yield monkeypatch


def test_drawdown_kill_uses_env_when_set(clean_env):
    clean_env.setenv("ORGANISM_DRAWDOWN_KILL_PCT", "0.10")
    gov = GovernanceController()
    assert gov._drawdown_limit == pytest.approx(0.10)
    assert gov._drawdown_limit_source == "env"


def test_drawdown_kill_uses_code_default_when_env_absent(clean_env):
    gov = GovernanceController()
    assert gov._drawdown_limit == pytest.approx(DEFAULT_DRAWDOWN_KILL_PCT)
    assert gov._drawdown_limit_source == "code_default"


def test_drawdown_kill_drift_warning_fires_on_permissive_env(clean_env, caplog):
    clean_env.setenv("ORGANISM_DRAWDOWN_KILL_PCT", "0.20")
    with caplog.at_level(logging.WARNING, logger="backend.organism.governance"):
        gov = GovernanceController()
    assert gov._drawdown_limit == pytest.approx(0.20)
    warn_lines = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("is 4.00x the code default" in r.getMessage() for r in warn_lines), (
        "expected a warning that env value is 4.00x code default"
    )


def test_drawdown_kill_drift_warning_silent_on_default(clean_env, caplog):
    with caplog.at_level(logging.WARNING, logger="backend.organism.governance"):
        GovernanceController()
    warn_lines = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "drawdown_kill_pct" in r.getMessage()
    ]
    assert warn_lines == [], "drift warning must not fire when source is code_default"


def test_drawdown_kill_drift_warning_silent_below_ratio(clean_env, caplog):
    # 0.07 < 0.05 * 1.5 = 0.075 → no warning
    clean_env.setenv("ORGANISM_DRAWDOWN_KILL_PCT", "0.07")
    with caplog.at_level(logging.WARNING, logger="backend.organism.governance"):
        GovernanceController()
    warn_lines = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "drawdown_kill_pct" in r.getMessage()
    ]
    assert warn_lines == []


def test_drawdown_kill_drift_warning_fires_at_boundary(clean_env, caplog):
    # 0.08 > 0.075 → warning fires
    clean_env.setenv("ORGANISM_DRAWDOWN_KILL_PCT", "0.08")
    with caplog.at_level(logging.WARNING, logger="backend.organism.governance"):
        GovernanceController()
    warn_lines = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "drawdown_kill_pct" in r.getMessage()
    ]
    assert warn_lines, "drift warning must fire when env exceeds 1.5x default"
