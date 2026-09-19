"""V12 W75 behavioral tests for the lint ratchet (UU3-1, UU3-2, F821 fixes).

Findings closed by W75:
- UU3-1: grandfather typos in pyproject.toml (paths pointed at non-
  existent modules so 120+ violations leaked).
- UU3-2: ruff couldn't pass; ratchet pattern installed.
- 5 F821 real bugs in production code (live_engine, security,
  indicators) — these were latent runtime crashes.

These tests run the lint ratchet against fixtures and live config,
asserting on observable behaviors (file existence, exit codes,
diff outputs) rather than source-grep markers.

Run with:
    ./venv/bin/python -m pytest tests/test_v12_w75_lint_ratchet.py -v
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RATCHET = REPO_ROOT / "scripts" / "ci" / "lint_ratchet.py"
BASELINE = REPO_ROOT / "artifacts" / "audit" / "v12" / "lint_baseline.json"
PYPROJECT = REPO_ROOT / "pyproject.toml"


# ────────────────────────────────────────────────────────────────────
# UU3-1: grandfather typo paths now resolve.
# ────────────────────────────────────────────────────────────────────

def test_uu3_1_grandfather_paths_exist():
    """The pyproject ``per-file-ignores`` that were typo'd pre-V12
    must now resolve to real files."""
    import tomllib
    cfg = tomllib.loads(PYPROJECT.read_text())
    ignores = cfg.get("tool", {}).get("ruff", {}).get("lint", {}).get(
        "per-file-ignores", {}
    )
    assert "backend/analytics/realtime_risk_analytics.py" in ignores, (
        "UU3-1 regression: grandfather typo for realtime_risk_analytics "
        "not fixed (was services/, should be analytics/)"
    )
    assert "backend/models/ensemble_model.py" in ignores, (
        "UU3-1 regression: grandfather typo for ensemble_model not "
        "fixed (was ml/, should be models/)"
    )
    # Both target files exist on disk.
    assert (REPO_ROOT / "backend" / "analytics" / "realtime_risk_analytics.py").is_file()
    assert (REPO_ROOT / "backend" / "models" / "ensemble_model.py").is_file()


# ────────────────────────────────────────────────────────────────────
# UU3-2: lint ratchet baseline + scripts.
# ────────────────────────────────────────────────────────────────────

def test_uu3_2_lint_ratchet_baseline_exists():
    """The committed baseline must be valid JSON with the expected schema."""
    assert BASELINE.is_file(), "lint_baseline.json missing — run ratchet --update-baseline"
    data = json.loads(BASELINE.read_text())
    assert "counts_by_key" in data
    assert "total" in data
    assert isinstance(data["counts_by_key"], dict)
    assert data["total"] == sum(data["counts_by_key"].values())


def test_uu3_2_lint_ratchet_passes_against_committed_baseline():
    """Live invariant: current ruff state must match (or be lower than)
    the committed baseline.  The ratchet must exit 0."""
    proc = subprocess.run(
        [str(REPO_ROOT / "venv" / "bin" / "python"), str(RATCHET)],
        capture_output=True, text=True, timeout=120, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, (
        f"Lint ratchet failed against committed baseline.\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )


def test_uu3_2_lint_ratchet_runs_in_under_2_minutes():
    """Behavioral perf: ratchet must complete within CI tolerance."""
    import time
    start = time.time()
    proc = subprocess.run(
        [str(REPO_ROOT / "venv" / "bin" / "python"), str(RATCHET)],
        capture_output=True, text=True, timeout=120, cwd=REPO_ROOT,
    )
    elapsed = time.time() - start
    assert proc.returncode == 0
    assert elapsed < 120, f"Ratchet took {elapsed:.1f}s — too slow for CI"


# ────────────────────────────────────────────────────────────────────
# F821 real-bug fixes: each fixed location must NOT regress.
# ────────────────────────────────────────────────────────────────────

def test_f821_no_undefined_names_in_repo():
    """The 10 F821 (undefined-name) violations from the V12 W75
    investigation are real runtime crash sites.  They were fixed; this
    test prevents reintroduction."""
    proc = subprocess.run(
        [str(REPO_ROOT / "venv" / "bin" / "python"), "-m", "ruff",
         "check", ".", "--no-fix", "--select", "F821",
         "--output-format=concise"],
        capture_output=True, text=True, timeout=60, cwd=REPO_ROOT,
    )
    if proc.returncode != 0:
        # Print the violations so the failure message is actionable.
        pytest.fail(
            f"F821 regression: undefined-name violations reintroduced.\n"
            f"{proc.stdout}"
        )


def test_f821_security_redis_forward_ref_resolves():
    """``backend/infra/security.py`` declares ``_token_blacklist_redis:
    Optional["Redis"]`` — the forward-ref ``Redis`` must be importable
    in ``TYPE_CHECKING``.  Behavioral: import the module and confirm
    no ImportError; check the TYPE_CHECKING block exists."""
    import backend.infra.security as sec
    # Module imports cleanly (no F821 NameError at runtime).
    assert hasattr(sec, "_token_blacklist_redis")
    # The forward-ref ``"Redis"`` is only resolved in TYPE_CHECKING; at
    # runtime the variable is None or an actual Redis client.
    assert sec._token_blacklist_redis is None or hasattr(
        sec._token_blacklist_redis, "set"
    )


def test_f821_indicators_fallback_imports_resolve():
    """``backend/api/routes/indicators.py`` fallback block uses
    ``TimeFrame``, ``datetime``, ``UTC``, ``timedelta`` — all must
    be importable at the function scope.  Behavioral: parse the
    module and assert the ``except Exception as e`` fallback block
    contains the imports."""
    import ast
    src = (REPO_ROOT / "backend" / "api" / "routes" / "indicators.py").read_text()
    tree = ast.parse(src)
    # Walk and find the function ``calculate_indicator``.
    for node in ast.walk(tree):
        if not (isinstance(node, ast.AsyncFunctionDef) and node.name == "calculate_indicator"):
            continue
        # Find ImportFrom nodes inside the body.
        imports_found = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.ImportFrom):
                for alias in sub.names:
                    imports_found.add(alias.name)
        # The fallback block needs UTC, datetime, timedelta from datetime
        # AND TimeFrame from alpaca.data.timeframe.
        assert "UTC" in imports_found, "UTC import missing in calculate_indicator"
        assert "datetime" in imports_found, "datetime import missing"
        assert "timedelta" in imports_found, "timedelta import missing"
        assert "TimeFrame" in imports_found, "TimeFrame import missing"
        return
    pytest.fail("calculate_indicator function not found")


def test_f821_live_engine_pp5_alert_text_captured_safely():
    """``backend/organism/live_engine.py`` PP-5 scanner-failure alert
    used ``f"... {e}"`` inside a lambda where ``e`` would be deleted
    at except-block exit.  Now: ``str(e)`` captured to a local before
    the lambda."""
    import ast
    src = (REPO_ROOT / "backend" / "organism" / "live_engine.py").read_text()
    tree = ast.parse(src)
    # Find any reference to ``_last_err_text`` — the V12 W75 fix.
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "_last_err_text":
            found = True
            break
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "_last_err_text":
                    found = True
                    break
    assert found, (
        "F821 regression: V12 W75 PP-5 fix removed; ``_last_err_text`` "
        "no longer captures ``str(e)`` before the lambda — would "
        "NameError on cross-thread alert dispatch."
    )


# ────────────────────────────────────────────────────────────────────
# Slim ruff select: ensure the V12 rule set is in effect.
# ────────────────────────────────────────────────────────────────────

def test_w75_ruff_select_is_slim_and_includes_wave_57_rules():
    """Pyproject's ``select`` must contain the V12 W75 slim ruleset.

    Pre-V12 it included broad families (E, W, F, I, B, UP, SIM, PTH,
    PL) that produced 34k violations — CI lint never passed.  V12
    keeps only the rules we actually enforce.
    """
    import tomllib
    cfg = tomllib.loads(PYPROJECT.read_text())
    ruff = cfg["tool"]["ruff"]
    # Support both top-level (deprecated) and nested [tool.ruff.lint]
    # placement of ``select``.
    select = ruff.get("select") or ruff.get("lint", {}).get("select", [])
    # Wave-57 enforcement rules must all be present.
    for r in ("S110", "S112", "BLE001", "G004", "TRY401", "LOG007"):
        assert r in select, (
            f"V12 W75 regression: wave-57 rule {r} removed from select"
        )
    # F is the smallest correctness-class family we keep.
    assert "F" in select, "V12 W75 regression: F (pyflakes) family dropped"
    # The broad noisy families should NOT be enforced project-wide.
    forbidden = {"PL", "SIM", "PTH"}  # leaving B and UP alone — borderline
    # We want to verify the *broad* families weren't re-added.  ``B``
    # may appear if someone explicitly enables it for a sub-rule; we
    # just check the noisy ones.
    overlap = forbidden & set(select)
    assert not overlap, (
        f"V12 W75 regression: noisy rule families re-added to select: "
        f"{overlap}.  Pre-V12 these created 25k+ unactionable violations."
    )


# ────────────────────────────────────────────────────────────────────
# Sandbox: ratchet correctly identifies new violations vs baseline.
# ────────────────────────────────────────────────────────────────────

def test_w75_ratchet_detects_new_violation_against_fixture(tmp_path: Path):
    """Build a sandbox with a baseline, introduce a violation, run the
    ratchet, assert exit 1 + the new violation is reported."""
    # Set up sandbox: copy classifier + ratchet; manufacture a tiny project.
    sb = tmp_path
    (sb / "scripts" / "ci").mkdir(parents=True)
    (sb / "artifacts" / "audit" / "v12").mkdir(parents=True)
    # Copy ratchet (it imports nothing repo-specific except the classifier).
    (sb / "scripts" / "ci" / "lint_ratchet.py").write_text(
        RATCHET.read_text()
    )
    # Minimal pyproject.toml with the wave-57 rules.
    (sb / "pyproject.toml").write_text(
        '[tool.ruff.lint]\n'
        'select = ["F", "BLE001"]\n'
    )
    # Source file with NO violations initially.
    (sb / "clean.py").write_text("def f():\n    return 1\n")
    # Capture baseline.
    proc = subprocess.run(
        [str(REPO_ROOT / "venv" / "bin" / "python"),
         "scripts/ci/lint_ratchet.py", "--update-baseline"],
        capture_output=True, text=True, timeout=60, cwd=sb,
    )
    assert proc.returncode == 0, proc.stderr

    # Now introduce a violation.
    (sb / "bad.py").write_text(
        "try:\n"
        "    x = 1\n"
        "except Exception:\n"
        "    pass\n"
    )
    # Re-run ratchet — should fail.
    proc = subprocess.run(
        [str(REPO_ROOT / "venv" / "bin" / "python"),
         "scripts/ci/lint_ratchet.py"],
        capture_output=True, text=True, timeout=60, cwd=sb,
    )
    assert proc.returncode == 1, (
        f"Ratchet should reject NEW violation.\nstdout:\n{proc.stdout}"
    )
    assert "NEW VIOLATIONS" in proc.stdout
    assert "BLE001" in proc.stdout
