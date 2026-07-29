"""V13 W92 (Lens 1: Deploy / Runtime Truth) — behavioral coverage.

Closes the V10/V11 wave-47 class of bug: code on disk says "fixed",
container says "broken", audit says "closed".  W92 ships a parity
checker (``scripts/ci/check_deploy_parity.py``) that fails CI when
host SHA / container SHA / hot-path bytes don't match.

These tests exercise the checker in two modes:

1. **Sandbox** (always runs in CI): the checker's own logic must
   reject ``unknown``/empty SHAs, accept matching SHAs, and the
   five hot-path files must exist on host.

2. **Live probe** (gated on ``V13_LIVE_PROBES=1``): the checker
   actually probes localhost:8000 endpoints + container bytes.
   Skipped without the env var so CI without a running container
   doesn't false-fail.

Run with:
    ./venv/bin/python -m pytest tests/test_v13_w92_deploy_parity.py -v
    V13_LIVE_PROBES=1 ./venv/bin/python -m pytest tests/test_v13_w92_deploy_parity.py -v
"""
# wave: V13-W92
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "ci" / "check_deploy_parity.py"

# Ensure the checker is importable as a module for unit-level testing.
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import check_deploy_parity as parity  # noqa: E402


# ------------------------------------------------------------------ #
# Sandbox / unit-level                                               #
# ------------------------------------------------------------------ #


def test_w92_checker_script_exists():
    assert CHECKER.is_file(), "W92 deliverable: check_deploy_parity.py must exist"


def test_w92_parity_compare_rejects_empty():
    assert parity.parity_compare("", "abc") is False
    assert parity.parity_compare("abc", "") is False


def test_w92_parity_compare_rejects_unknown_marker():
    """`unknown` is the sentinel deploy_health.py returns when GIT_SHA
    isn't baked in — parity must FAIL on it, not silently match
    `unknown == unknown`."""
    assert parity.parity_compare("unknown", "unknown") is False
    assert parity.parity_compare("abc", "unknown") is False


def test_w92_parity_compare_accepts_match():
    assert parity.parity_compare("a" * 64, "a" * 64) is True


def test_w92_parity_compare_rejects_mismatch():
    assert parity.parity_compare("a" * 64, "b" * 64) is False


def test_w92_hot_path_list_covers_runtime_and_api_routes():
    """Deploy drift hid route-level V13 closures, so parity must cover
    both organism runtime files and audit-facing API route modules."""
    required = {
        "backend/organism/live_engine.py",
        "backend/organism/brain_persistence.py",
        "backend/infra/outbox_worker.py",
        "backend/infra/security.py",
        "backend/api/lifespan.py",
        "backend/api/routes/orders.py",
        "backend/api/routes/strategy_health.py",
        "backend/api/routes/data_integrity_health.py",
        "backend/api/routes_setup.py",
    }
    assert required.issubset(set(parity.HOT_PATH_FILES))


def test_w92_hot_path_files_all_exist():
    """Every entry in HOT_PATH_FILES must exist on host.  If a file is
    renamed/moved, this test fails — forcing the checker to be
    updated, not silently drift."""
    missing = [
        rel for rel in parity.HOT_PATH_FILES
        if not (REPO_ROOT / rel).is_file()
    ]
    assert not missing, f"hot-path files missing on host: {missing}"


def test_w92_sandbox_self_test_exits_zero():
    """The checker invoked without V13_LIVE_PROBES must exit 0 in a
    clean repo.  This is what runs in CI on every PR."""
    env = os.environ.copy()
    env.pop("V13_LIVE_PROBES", None)
    proc = subprocess.run(
        [sys.executable, str(CHECKER)],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, (
        f"sandbox self-test failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert "PASS" in proc.stdout


def test_w92_deploy_probe_rejects_stale_container_sha(monkeypatch):
    def fake_get(path, *, authenticated=False):
        assert authenticated is True
        return 200, {
            "source_sha": "a" * 40,
            "migration_head": "20260503_000003",
        }, "{}"

    monkeypatch.setattr(parity, "_http_get_json", fake_get)
    monkeypatch.setattr(parity, "_host_git_sha", lambda: "b" * 40)

    result = parity.probe_deploy_endpoint()
    assert result.passed is False
    assert "expected host HEAD" in result.detail


def test_w92_deploy_probe_accepts_current_host_sha(monkeypatch):
    sha = "c" * 40

    def fake_get(path, *, authenticated=False):
        assert authenticated is True
        return 200, {
            "source_sha": sha,
            "migration_head": "20260503_000003",
        }, "{}"

    monkeypatch.setattr(parity, "_http_get_json", fake_get)
    monkeypatch.setattr(parity, "_host_git_sha", lambda: sha)

    result = parity.probe_deploy_endpoint()
    assert result.passed is True


def test_w92_auth_headers_requires_token_or_login(monkeypatch):
    monkeypatch.delenv("V13_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("V13_AUTH_USERNAME", raising=False)
    monkeypatch.delenv("V13_AUTH_PASSWORD", raising=False)
    monkeypatch.setattr(parity, "_AUTH_HEADER_CACHE", None)

    headers, err = parity._auth_headers()
    assert headers is None
    assert "missing auth" in err


# ------------------------------------------------------------------ #
# Live probe (opt-in)                                                #
# ------------------------------------------------------------------ #


@pytest.mark.skipif(
    os.environ.get("V13_LIVE_PROBES") != "1",
    reason="live probes require V13_LIVE_PROBES=1 + running container",
)
def test_w92_live_probe_deploy_endpoint():
    """Live: /api/v1/health/deploy returns 200 with non-`unknown`
    GIT_SHA.  Run after `make rebuild-paper` against a running paper
    container."""
    result = parity.probe_deploy_endpoint()
    assert result.passed, f"live deploy probe failed: {result.detail}"


@pytest.mark.skipif(
    os.environ.get("V13_LIVE_PROBES") != "1",
    reason="live probes require V13_LIVE_PROBES=1 + running container",
)
def test_w92_live_probe_strategy_endpoint():
    result = parity.probe_strategy_endpoint()
    assert result.passed, f"live strategy probe failed: {result.detail}"


@pytest.mark.skipif(
    os.environ.get("V13_LIVE_PROBES") != "1",
    reason="live probes require V13_LIVE_PROBES=1 + running container",
)
def test_w92_live_probe_audit_chain_detail():
    result = parity.probe_audit_chain_detail()
    assert result.passed, f"live audit-chain probe failed: {result.detail}"


@pytest.mark.skipif(
    os.environ.get("V13_LIVE_PROBES") != "1",
    reason="live probes require V13_LIVE_PROBES=1 + running container",
)
def test_w92_live_probe_hot_path_byte_parity():
    result = parity.probe_hot_path_byte_parity()
    assert result.passed, f"live hot-path probe failed: {result.detail}"
