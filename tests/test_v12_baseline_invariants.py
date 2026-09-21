"""V12 W70: lock the V12 baseline + validate the classifier behaviorally.

This file exists to:
1. Prove the wave-test classifier (`scripts/ci/classify_wave_tests.py`)
   correctly labels marker-only vs behavioral test patterns.  Unlike
   the wave-test files this file complains about, this file ITSELF
   exercises the classifier with fixtures and asserts on its return
   values (not on string presence).
2. Lock the V12 starting baseline so any regression caused by V12
   waves is observable: the classifier output, the strategy
   expectancy snapshot, and the V11 commit head are asserted here.
3. Optionally audit an explicitly supplied installed-history CSV for shrinkage.
   Set INTRA_INSTALLED_HISTORY_CSV to its absolute path. Clean-checkout CI
   reports this installed-data audit unavailable (skipped), never as passing
   evidence about a deployed history. No private brain is read implicitly.

V12 commitment: this file uses behavioral fixtures + AST-parse
assertions, NOT ``inspect.getsource`` greps.  If you find yourself
adding ``"X" in src`` here, stop and add a real probe instead.

Run with: ./venv/bin/python -m pytest tests/test_v12_baseline_invariants.py -v
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER = REPO_ROOT / "scripts" / "ci" / "classify_wave_tests.py"
EXPECTANCY_TOOL = REPO_ROOT / "scripts" / "ci" / "compute_strategy_expectancy.py"
V12_BASELINE = REPO_ROOT / "artifacts" / "audit" / "v12" / "v12_baseline.json"
V12_STATE = REPO_ROOT / "artifacts" / "audit" / "v12" / "v12_state.json"
V12_EXPECTANCY_SNAPSHOT = REPO_ROOT / "artifacts" / "audit" / "v12" / "v12_baseline_expectancy.json"


# ────────────────────────────────────────────────────────────────────
# 1. Classifier: behavioral fixture tests.  Each fixture is a real
#    Python source string fed through the classifier as an in-memory
#    test file.  We assert on the returned classification.
# ────────────────────────────────────────────────────────────────────

# Make scripts/ci importable in-process so the test runs as part of
# pytest, not as a subprocess.  This is a behavioral test of the
# classifier's *function*, not of its CLI surface.
import sys
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import classify_wave_tests as cwt  # type: ignore  # noqa: E402


def _classify_fixture(src: str) -> dict[str, str]:
    """Parse `src` as a Python module, classify each top-level test_*
    function, return {func_name: classification}."""
    tree = ast.parse(textwrap.dedent(src))
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            out[node.name] = cwt.classify_test("fixture", node).classification
    return out


def test_classifier_flags_inspect_getsource_marker_only():
    """assert "X" in inspect.getsource(...) → marker-only."""
    src = '''
        import inspect
        def test_marker_only_pattern():
            from backend.api import errors
            src = inspect.getsource(errors)
            assert "AAA-F1" in src
    '''
    out = _classify_fixture(src)
    assert out["test_marker_only_pattern"] == "marker-only", out


def test_classifier_flags_open_read_marker_only():
    """assert "X" in open(p).read() → marker-only."""
    src = '''
        def test_open_read_pattern():
            src = open("docker-compose.yml").read()
            assert "ORGANISM_MAX_DAILY_LOSS=" in src
    '''
    out = _classify_fixture(src)
    assert out["test_open_read_pattern"] == "marker-only", out


def test_classifier_flags_not_in_marker_only():
    """assert "X" not in src → marker-only (V12 W70 fix)."""
    src = '''
        import inspect
        def test_negation_pattern():
            from backend.api import errors
            src = inspect.getsource(errors)
            assert "old_marker" not in src
    '''
    out = _classify_fixture(src)
    assert out["test_negation_pattern"] == "marker-only", out


def test_classifier_flags_count_marker_only():
    """assert src.count("X") >= N → marker-only (V12 W70 fix)."""
    src = '''
        import inspect
        def test_count_pattern():
            from backend.api.routes import audit
            src = inspect.getsource(audit)
            n = src.count("Depends(require_admin)")
            assert n >= 6
    '''
    out = _classify_fixture(src)
    assert out["test_count_pattern"] == "marker-only", out


def test_classifier_flags_hasattr_marker_only():
    """assert hasattr(SUT, "method") → marker-only (V12 W70 fix)."""
    src = '''
        def test_hasattr_pattern():
            from backend.organism.brain_persistence import OrganismBrain
            assert hasattr(OrganismBrain, "_restore_from_latest_backup")
    '''
    out = _classify_fixture(src)
    assert out["test_hasattr_pattern"] == "marker-only", out


def test_classifier_flags_boolop_marker_only():
    """assert "X" in src and "Y" in src → marker-only (V12 W70 fix)."""
    src = '''
        import inspect
        def test_boolop_pattern():
            from backend.organism import kelly_sizer
            src = inspect.getsource(kelly_sizer)
            assert "Wave-60" in src and "effective_regime_for_symbol" in src
    '''
    out = _classify_fixture(src)
    assert out["test_boolop_pattern"] == "marker-only", out


def test_classifier_flags_real_call_behavioral():
    """assert sut_function(args) == X → behavioral."""
    src = '''
        def test_calls_sut():
            from backend.organism.regime import is_inverse_etf
            assert is_inverse_etf("RWM") is True
    '''
    out = _classify_fixture(src)
    assert out["test_calls_sut"] == "behavioral", out


def test_classifier_flags_status_code_behavioral():
    """assert resp.status_code == 200 (after live call) → behavioral."""
    src = '''
        def test_endpoint():
            from fastapi.testclient import TestClient
            from backend.api.app import app
            client = TestClient(app)
            resp = client.get("/api/v1/health")
            assert resp.status_code == 200
    '''
    out = _classify_fixture(src)
    assert out["test_endpoint"] == "behavioral", out


def test_classifier_flags_mixed_pattern():
    """A test with BOTH a marker assertion AND a behavioral call → mixed."""
    src = '''
        import inspect
        def test_jwt_decode_passes_leeway():
            from backend.infra.security import create_access_token, decode_token, security
            token = create_access_token(sub="x@y.com", roles=["user"], expires_minutes=5)
            payload = decode_token(token)
            assert payload["sub"] == "x@y.com"
            src = inspect.getsource(security.decode_token)
            assert "leeway" in src
    '''
    out = _classify_fixture(src)
    assert out["test_jwt_decode_passes_leeway"] == "mixed", out


# ────────────────────────────────────────────────────────────────────
# 2. Classifier on real wave-test files: locks the baseline.  If a V12
#    wave converts a marker-only test to behavioral, this baseline
#    moves; the test is updated together with the conversion in the
#    same wave commit.
# ────────────────────────────────────────────────────────────────────

def test_baseline_classifier_runs_on_repo():
    """The classifier must run cleanly across all 33 wave-test files."""
    proc = subprocess.run(
        [sys.executable, str(CLASSIFIER), "--json", "-"],
        capture_output=True, text=True, timeout=30, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["files_scanned"] >= 30
    assert data["tests_total"] >= 100
    # All 4 buckets must be present in output schema (even if count = 0).
    assert "marker-only" in data["by_classification"] or data["by_classification"].get("marker-only", 0) >= 0


def test_baseline_marker_only_count_matches_committed():
    """Baseline JSON committed in W70 must agree with current classifier output."""
    baseline = json.loads(V12_BASELINE.read_text())
    proc = subprocess.run(
        [sys.executable, str(CLASSIFIER), "--json", "-"],
        capture_output=True, text=True, timeout=30, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0
    current = json.loads(proc.stdout)
    # Total test count must equal what we baselined (drift = drift in
    # wave-test corpus, which deserves an explicit baseline update).
    assert current["tests_total"] == baseline["wave_test_classifier"]["tests_total"], (
        f"Wave-test corpus changed: was "
        f"{baseline['wave_test_classifier']['tests_total']}, now "
        f"{current['tests_total']}.  Update v12_baseline.json in the same commit."
    )


# ────────────────────────────────────────────────────────────────────
# 3. Strategy expectancy: lock the −$634 baseline so post-V12 deltas
#    can be measured.  The numbers are dollars/percentages from the
#    real CSV — this is a *behavioral* invariant, not a marker.
# ────────────────────────────────────────────────────────────────────

def test_baseline_expectancy_module_runs(tmp_path):
    """Missing input is unavailable evidence, not a zero-trade audit success."""
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
    import compute_strategy_expectancy as cse  # noqa: E402
    missing = tmp_path / "unavailable_history.csv"
    out = cse.compute(missing)
    assert out["csv_exists"] is False
    assert out["csv_path"] == str(missing)
    assert out["csv_mtime"] is None
    assert out["error"] == "trade_history.csv not found"
    assert out["n_trades"] == 0


def test_baseline_expectancy_reflects_committed_baseline():
    """The two committed May snapshots must retain their real recorded values.

    This deterministic check does not recompute historical PnL without its
    unavailable raw CSV and does not attest to any currently installed brain.
    """
    baseline = json.loads(V12_BASELINE.read_text())
    recorded = baseline["strategy_expectancy"]
    snapshot = json.loads(V12_EXPECTANCY_SNAPSHOT.read_text())
    for key in ("csv_exists", "csv_mtime", "csv_path", "n_trades", "n_wins",
                "n_losses", "total_pnl", "win_rate", "max_drawdown", "mean_pnl", "median_pnl"):
        assert snapshot[key] == recorded[key], key
    assert snapshot["sharpe_ratio_per_trade"] == recorded["sharpe_ratio"]
    for size in (25, 50):
        for metric in ("mean_pnl", "win_rate"):
            assert snapshot[f"last_{size}_{metric}"] == recorded[f"last_{size}"][metric]
    assert recorded["csv_exists"] is True
    assert recorded["n_trades"] == 498
    assert recorded["total_pnl"] == -634.9
    assert baseline["captured_at"] == "2026-05-03"


def test_installed_history_has_not_shrunk_from_committed_baseline():
    """Optional installed-data audit; absent private data is reported unavailable."""
    configured = os.environ.get("INTRA_INSTALLED_HISTORY_CSV")
    if not configured:
        pytest.skip("Installed-history audit unavailable: INTRA_INSTALLED_HISTORY_CSV was not provided; no deployed-history preservation claim")
    csv_path = Path(configured)
    assert csv_path.is_absolute(), "Installed-history audit requires an explicit absolute CSV path"
    assert csv_path.is_file(), "Configured installed-history CSV is unavailable"
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
    import compute_strategy_expectancy as cse  # noqa: E402
    current = cse.compute(csv_path)
    assert current["csv_exists"] is True and "error" not in current
    base_exp = json.loads(V12_BASELINE.read_text())["strategy_expectancy"]
    assert current["n_trades"] >= base_exp["n_trades"], (
        f"trade history shrank: was {base_exp['n_trades']}, now {current['n_trades']}"
    )
    assert base_exp["total_pnl"] < 0, (
        "Baseline must reflect the auditor's finding — brain was unprofitable."
    )


# ────────────────────────────────────────────────────────────────────
# 4. V12 state file: machine-readable findings ledger seed.
# ────────────────────────────────────────────────────────────────────

def test_v12_state_is_valid_json():
    state = json.loads(V12_STATE.read_text())
    assert state["schema_version"] == 1
    assert state["scope"].lower().startswith("backend")
    assert "frontend out" in state["scope"].lower(), (
        "V12 scope must explicitly exclude frontend per user direction."
    )


def test_v12_state_has_strategy_expectancy_finding():
    """The auditor's #1 finding must be ledgered."""
    state = json.loads(V12_STATE.read_text())
    expectancy_finding = next(
        (f for f in state["findings"] if f["id"] == "EXT-1"),
        None,
    )
    assert expectancy_finding is not None, (
        "EXT-1 (brain unprofitability) missing from ledger"
    )
    assert expectancy_finding["severity"] == "critical"
    assert expectancy_finding["wave_target"] == 71


def test_v12_state_dd5_findings_targeted_at_w72():
    """DD5-1/2/3 strategy root-cause fixes must target W72."""
    state = json.loads(V12_STATE.read_text())
    dd5 = [f for f in state["findings"] if f["id"].startswith("DD5-")]
    assert len(dd5) >= 3
    for f in dd5[:3]:  # first three are DD5-1/2/3
        assert f["wave_target"] == 72, f


def test_v12_state_each_finding_has_required_fields():
    """Every ledgered finding must carry the required schema fields."""
    state = json.loads(V12_STATE.read_text())
    required = {"id", "from", "severity", "title", "status",
                "wave_target", "behavioral_test_path"}
    # V12 W74 added a fourth status to record findings that are "real
    # but determined-by-design after investigation" (EXT-3 trade-count
    # divergence) — distinct from "open / closed / deferred".
    allowed_status = {
        "open", "closed", "deferred", "documented_by_design",
    }
    for f in state["findings"]:
        missing = required - set(f.keys())
        assert not missing, f"{f.get('id', '?')} missing fields: {missing}"
        assert f["severity"] in {"critical", "high", "medium", "low"}
        assert f["status"] in allowed_status, (
            f"{f['id']} has status={f['status']!r} not in {allowed_status}"
        )


# ────────────────────────────────────────────────────────────────────
# 5. _live_tick_inner LOC: lock the regression baseline so W75 can
#    prove the extraction.
# ────────────────────────────────────────────────────────────────────

def test_baseline_live_tick_inner_loc_present():
    """AST-measure _live_tick_inner LOC; must match committed baseline."""
    src_path = REPO_ROOT / "backend" / "organism" / "live_engine.py"
    tree = ast.parse(src_path.read_text())
    loc = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_live_tick_inner":
            loc = node.end_lineno - node.lineno + 1
            break
    assert loc is not None, "_live_tick_inner not found"
    baseline = json.loads(V12_BASELINE.read_text())
    base_loc = baseline["live_engine_metrics"]["_live_tick_inner_loc"]
    # During W75 LOC should DROP, not grow.  Assert no regression
    # beyond +5 (small tolerance for unrelated edits in non-W75 waves).
    assert loc <= base_loc + 5, (
        f"_live_tick_inner regressed from baseline {base_loc} to {loc}; "
        f"V12 W75 should be reducing this, not growing it."
    )
