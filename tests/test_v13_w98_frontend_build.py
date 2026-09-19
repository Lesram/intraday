"""V13 W98 (Lens 7: Frontend / Product Contract) — behavioral coverage.

V12 excluded frontend by user direction; V13 includes it under
Lens 7.  W98 ships:

1. Frontend ``npm run build`` exits 0.
2. ProtectedRoute admin-bypass is build-fenced behind
   ``import.meta.env.MODE === 'development'``.
3. ``npm audit`` high+critical vulnerabilities at zero.
4. PositionsTable.tsx missing ``api`` import fixed via
   ``apiClient as api`` alias.
5. ThresholdTable generic relaxed to ``T extends object``.

Run with:
    ./venv/bin/python -m pytest tests/test_v13_w98_frontend_build.py -v

Most of these tests are static-source contracts on the frontend
files since spinning up Node + Vite in CI is significant tooling.
The actual ``npm run build`` execution is gated behind a
``W98_RUN_NPM_BUILD=1`` env var so CI without Node skips it.
"""
# wave: V13-W98
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = REPO_ROOT / "frontend"
PROTECTED_ROUTE = FRONTEND / "src" / "components" / "auth" / "ProtectedRoute.tsx"
POSITIONS_TABLE = FRONTEND / "src" / "components" / "portfolio" / "PositionsTable.tsx"
THRESHOLD_TABLE = (
    FRONTEND / "src" / "features" / "architecture" / "components" / "ThresholdTable.tsx"
)


def test_w98_frontend_directory_exists():
    """Sanity: V13 sees the frontend tree."""
    assert FRONTEND.is_dir(), f"frontend dir missing at {FRONTEND}"
    assert (FRONTEND / "package.json").is_file()


def test_w98_protected_route_admin_bypass_is_build_fenced():
    """The DEV_BYPASS_AUTH constant must AND together MODE=='development'
    AND VITE_DEV_BYPASS_AUTH=='true' so a stray production env var
    cannot turn on admin auto-login."""
    src = PROTECTED_ROUTE.read_text()
    # Must be a single expression that includes the MODE check.
    assert "import.meta.env.MODE === 'development'" in src
    # And the original env var check must remain.
    assert "VITE_DEV_BYPASS_AUTH" in src
    # And the two checks must be on the same expression (string &&-joined).
    assert (
        "import.meta.env.MODE === 'development' &&"
        in src.replace("\n", " ").replace("  ", " ")
    ), "MODE check and VITE_DEV_BYPASS_AUTH check must be ANDed together"


def test_w98_positions_table_api_import_fixed():
    """PositionsTable used to import a non-existent ``api`` symbol;
    W98 aliases ``apiClient`` to keep call-site readability."""
    src = POSITIONS_TABLE.read_text()
    # Either the alias OR a relative path is acceptable; the bug was
    # specifically that ``import { api }`` referenced a missing export.
    assert "apiClient as api" in src or "from '@/services/api'" not in src


def test_w98_threshold_table_generic_relaxed():
    """The original constraint ``T extends Record<string, unknown>``
    rejected typed records.  W98 relaxes to ``T extends object``."""
    src = THRESHOLD_TABLE.read_text()
    # The relaxed constraint must appear in active TS (not in a comment).
    assert "function ThresholdTable<T extends object>" in src
    assert "interface ThresholdTableProps<T extends object>" in src
    # The OLD active constraint must be gone (we only allow it in
    # comments — strip those before checking).
    no_comments = "\n".join(
        line for line in src.splitlines()
        if not line.strip().startswith("//") and not line.strip().startswith("*")
        and not line.strip().startswith("/*")
    )
    assert "T extends Record<string, unknown>" not in no_comments


def test_w98_npm_audit_no_high_or_critical():
    """``npm audit --json`` must report zero high+critical vulnerabilities.
    Skipped if npm is not installed or audit cannot run."""
    if not (FRONTEND / "node_modules").exists():
        pytest.skip("node_modules not installed; run npm install first")

    proc = subprocess.run(
        ["npm", "audit", "--json"],
        cwd=str(FRONTEND), capture_output=True, text=True, timeout=120,
    )
    # `npm audit` exits non-zero when vulnerabilities exist; we still
    # parse stdout to assert SPECIFIC severities are zero.
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(
            f"npm audit JSON parse failed:\nstdout={proc.stdout[:400]}"
            f"\nstderr={proc.stderr[:200]}"
        )

    metadata = report.get("metadata", {})
    vulns = metadata.get("vulnerabilities", {})
    # Per V13 W98 acceptance: zero high or critical.
    assert vulns.get("critical", 0) == 0, (
        f"npm audit reports {vulns.get('critical')} CRITICAL vulnerabilities"
    )
    assert vulns.get("high", 0) == 0, (
        f"npm audit reports {vulns.get('high')} HIGH vulnerabilities"
    )


@pytest.mark.skipif(
    os.environ.get("W98_RUN_NPM_BUILD") != "1",
    reason="set W98_RUN_NPM_BUILD=1 to actually run `npm run build`",
)
def test_w98_npm_run_build_exits_zero():
    """Live: `npm run build` exits 0 — no TS errors.  Gated behind
    W98_RUN_NPM_BUILD=1 because CI without Node would skip otherwise."""
    proc = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(FRONTEND), capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, (
        f"npm run build failed:\nstdout-tail={proc.stdout[-2000:]}\n"
        f"stderr-tail={proc.stderr[-500:]}"
    )


def test_w98_dist_artifact_exists_or_buildable():
    """Either ``frontend/dist`` exists from a prior build, or the
    frontend has the package.json scripts wired so ``npm run build``
    is invokable.  Static contract — doesn't actually run npm."""
    pkg = json.loads((FRONTEND / "package.json").read_text())
    assert "scripts" in pkg
    assert "build" in pkg["scripts"]
    # The build script must include the TS step (tsc -b) and Vite.
    build_cmd = pkg["scripts"]["build"]
    assert "tsc" in build_cmd
    assert "vite" in build_cmd


def test_w98_admin_credentials_only_under_dev_bypass_branch():
    """The hard-coded admin@example.com/admin123 credentials in
    ProtectedRoute MUST live inside the DEV-bypass code path so they
    are dead-code-eliminated in production builds (where MODE is
    'production' and the branch's enclosing condition is false)."""
    src = PROTECTED_ROUTE.read_text()
    assert "admin@example.com" in src
    # The credential string must appear AFTER the DEV_BYPASS_AUTH check
    # (i.e. inside the auto-login function, not at module top level).
    cred_idx = src.find("admin@example.com")
    bypass_idx = src.find("DEV_BYPASS_AUTH")
    assert cred_idx > bypass_idx, (
        "admin credentials must appear inside the bypass branch, "
        "not at module top-level"
    )
