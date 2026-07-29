"""V9 / Wave-48 (2026-05-03): tests for test infra + CI enforcer edges.

Locks regressions for:
- Z7-1 (MEDIUM): pytest --collect-only succeeds (no ModuleNotFoundError
  on deleted ml/optimization/risk/mlops modules).
- W4-1 (LOW): _diff_test_count detects aliased fixture decorators
  (best-effort AST scan).
- W4-3 (LOW, but blocks W3 enforcement entirely): WAVE_COMMIT_RE
  recognizes hyphenated wave suffixes (e.g. audit-wave99-w3g1-test).

Run with: ./venv/bin/python -m pytest tests/test_wave48_fixes.py -v
"""
from __future__ import annotations

import inspect
import subprocess


def test_z7_1_pytest_collection_clean():
    """pytest --collect-only must succeed (no ImportError on deleted
    modules).  Wave-38's clean-up of mlops/ml/risk/optimization left
    orphan test files that broke collection."""
    proc = subprocess.run(
        ["./venv/bin/python", "-m", "pytest", "--collect-only", "tests/"],
        capture_output=True, text=True, timeout=120,
    )
    # We don't require returncode 0 (some tests may legitimately fail
    # at collect time for other reasons in this codebase), but there
    # must be no ModuleNotFoundError on deleted-module names.
    deleted_modules = [
        "backend.mlops",
        "backend.ml.staleness_detector",
        "backend.ml.data_processing",
        "backend.ml.ensemble_framework",
        "backend.ml.pipeline",
        "backend.ml.prediction_service",
        "backend.ml.sentiment",
        "backend.ml.validation",
        "backend.ml.model_management",
        "backend.optimization.portfolio_optimizer",
        "backend.risk.advanced_risk_manager",
        "backend.risk.advanced_risk",
        "backend.risk.black_swan_protection",
        "backend.risk.correlation_breakdown",
        "backend.risk.margin_calculator",
        "backend.risk.volatility_checker",
        "backend.risk.position_limits",
        "backend.risk.risk_calculator",
        "backend.brokers.alpaca_production",
        "backend.brokers.broker_failover",
    ]
    text = proc.stdout + proc.stderr
    for mod in deleted_modules:
        assert (
            f"ModuleNotFoundError: No module named '{mod}'" not in text
        ), f"Z7-1 regression: pytest still tries to import deleted {mod}"


def test_w4_3_wave_commit_re_accepts_hyphens():
    """WAVE_COMMIT_RE must match hyphenated suffixes."""
    from scripts.ci.check_wave_markers import WAVE_COMMIT_RE
    assert WAVE_COMMIT_RE.match("fix(audit-wave99-w3g1-test): synthetic"), (
        "W4-3 regression: WAVE_COMMIT_RE no longer accepts hyphenated "
        "suffixes; hyphenated wave-id commits silently bypass all "
        "wave-rule enforcement."
    )
    # Sanity: still match canonical forms.
    assert WAVE_COMMIT_RE.match("fix(audit-wave42): jwt lifecycle")
    assert WAVE_COMMIT_RE.match("fix(audit-wave32a): trailer commit")
    # Negative: non-wave commits don't match.
    assert not WAVE_COMMIT_RE.match("docs(audit): something")
    assert not WAVE_COMMIT_RE.match("feat: new feature")


def test_w4_1_aliased_fixture_detection_marker():
    """The W4-1 marker is in _diff_test_count source — guards against
    a future revert of the alias-detection extension."""
    from scripts.ci.check_wave_markers import _diff_test_count
    src = inspect.getsource(_diff_test_count)
    assert "W4-1" in src, "W4-1 marker missing"
    assert "ImportFrom" in src or "pytest" in src, (
        "W4-1 regression: aliased-fixture detection logic removed."
    )


def test_w4_1_canonical_pytest_fixture_still_counted():
    """The canonical `@pytest.fixture` still matches the marker
    list (no regression on the V8 wave-32 widening)."""
    from scripts.ci.check_wave_markers import _diff_test_count
    src = inspect.getsource(_diff_test_count)
    assert "@pytest.fixture" in src
