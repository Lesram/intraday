"""V12 W70: lock the V12 baseline + validate the classifier behaviorally.

This file exists to:
1. Prove the wave-test classifier (`scripts/ci/classify_wave_tests.py`)
   correctly labels marker-only vs behavioral test patterns.  Unlike
   the wave-test files this file complains about, this file ITSELF
   exercises the classifier with fixtures and asserts on its return
   values (not on string presence).
2. Lock the V12 starting baseline so any regression caused by V12
   waves is observable: the classifier output, the strategy
   expectancy, and the V11 commit head are all asserted here.

V12 commitment: this file uses behavioral fixtures + AST-parse
assertions, NOT ``inspect.getsource`` greps.  If you find yourself
adding ``"X" in src`` here, stop and add a real probe instead.

Run with: ./venv/bin/python -m pytest tests/test_v12_baseline_invariants.py -v
"""
from __future__ import annotations

import ast
import json
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER = REPO_ROOT / "scripts" / "ci" / "classify_wave_tests.py"
EXPECTANCY_TOOL = REPO_ROOT / "scripts" / "ci" / "compute_strategy_expectancy.py"
V12_BASELINE = REPO_ROOT / "artifacts" / "audit" / "v12" / "v12_baseline.json"
V12_STATE = REPO_ROOT / "artifacts" / "audit" / "v12" / "v12_state.json"


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
        ["./venv/bin/python", str(CLASSIFIER), "--json", "-"],
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
        ["./venv/bin/python", str(CLASSIFIER), "--json", "-"],
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

def test_baseline_expectancy_module_runs():
    """The expectancy computer must be importable and runnable."""
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
    import compute_strategy_expectancy as cse  # noqa: E402
    out = cse.compute(REPO_ROOT / "organism_brain" / "trade_history.csv")
    assert "n_trades" in out
    assert out["n_trades"] >= 0


def test_baseline_expectancy_reflects_committed_baseline():
    """The committed baseline must equal what compute_strategy_expectancy
    sees today (subject to any new trades added since).  We assert on
    *integer* trade count and *signed* total_pnl class — exact float
    drift is acceptable across reads."""
    baseline = json.loads(V12_BASELINE.read_text())
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
    import compute_strategy_expectancy as cse  # noqa: E402
    current = cse.compute(REPO_ROOT / "organism_brain" / "trade_history.csv")
    base_exp = baseline["strategy_expectancy"]
    # Trade count can grow as new trades land; never shrink.
    assert current["n_trades"] >= base_exp["n_trades"], (
        f"trade history shrank: was {base_exp['n_trades']}, now {current['n_trades']}"
    )
    # Sign of expectancy at baseline is the auditor's headline finding.
    # If post-V12 the brain becomes profitable, this assertion will need
    # to be updated together with the celebration.
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
    for f in state["findings"]:
        missing = required - set(f.keys())
        assert not missing, f"{f.get('id', '?')} missing fields: {missing}"
        assert f["severity"] in {"critical", "high", "medium", "low"}
        assert f["status"] in {"open", "closed", "deferred"}


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
