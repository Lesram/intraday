"""V12 W77 (EXT-9): behavioral tests for the findings ledger system.

Closes the external auditor's #14 finding: V1-V11 deferral state lived
in prose across multiple synthesis docs.  W77 builds:

- ``scripts/ci/build_findings_ledger.py`` — parses V8-V11 synthesis
  docs + v12_state.json into a unified machine-readable ledger.
- ``scripts/ci/verify_findings_ledger.py`` — asserts every closed
  finding has a behavioral_test_path; every deferred has a reason.
- ``artifacts/audit/findings_ledger.json`` (machine-readable).
- ``artifacts/audit/findings_ledger_v12.md`` (human-readable rollup).

These tests drive the parser + verifier behaviorally — assert on
return values, exit codes, file outputs, not on source markers.

Run with:
    ./venv/bin/python -m pytest tests/test_v12_w77_findings_ledger.py -v
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_JSON = REPO_ROOT / "artifacts" / "audit" / "findings_ledger.json"
LEDGER_MD = REPO_ROOT / "artifacts" / "audit" / "findings_ledger_v12.md"
BUILDER = REPO_ROOT / "scripts" / "ci" / "build_findings_ledger.py"
VERIFIER = REPO_ROOT / "scripts" / "ci" / "verify_findings_ledger.py"


# ────────────────────────────────────────────────────────────────────
# Builder: parses real synthesis docs.
# ────────────────────────────────────────────────────────────────────

def test_w77_builder_runs_and_produces_ledger(tmp_path: Path):
    """The build script runs cleanly and writes both outputs.

    V12 W80 (post-audit cleanup): redirect outputs to tmp_path so
    running the test does NOT mutate tracked artifacts.  Pre-W80 the
    builder always wrote into ``artifacts/audit/``, dirtying the repo
    every time pytest ran (V12 external auditor caught this)."""
    out_json = tmp_path / "findings_ledger.json"
    out_md = tmp_path / "findings_ledger_v12.md"
    proc = subprocess.run(
        [str(REPO_ROOT / "venv" / "bin" / "python"), str(BUILDER),
         "--out-json", str(out_json), "--out-md", str(out_md)],
        capture_output=True, text=True, timeout=60, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_json.is_file()
    assert out_md.is_file()
    # The committed artifact should NOT have been touched by this test.
    # (We don't compare mtimes — that would be flaky under fast CI;
    # the implicit assertion is that we redirected the outputs.)


def test_w77_builder_parses_v11_synthesis_findings():
    """The ledger must contain finding IDs that appear in V11
    synthesis (DD5-1, AAA-F1, etc.) — proves the parser sees the
    actual table format."""
    data = json.loads(LEDGER_JSON.read_text())
    ids = {f["id"] for f in data["findings"]}
    expected_v11_ids = {"DD5-1", "DD5-2", "DD5-3", "AAA-F1", "AAA-F2",
                        "CCC-2", "AA5-1", "AA5-2", "BB5-F1", "BB5-F4",
                        "EXT-1", "EXT-2"}
    missing = expected_v11_ids - ids
    assert not missing, f"V11/EXT findings missing from ledger: {missing}"


def test_w77_builder_overlays_v12_state_closures():
    """Findings closed in V12 (DD5-1/2/3, EXT-1, etc.) must reflect
    status=closed with a behavioral_test_path."""
    data = json.loads(LEDGER_JSON.read_text())
    by_id = {f["id"]: f for f in data["findings"]}
    for ident in ("DD5-1", "DD5-2", "DD5-3", "EXT-1", "AA5-2"):
        f = by_id.get(ident)
        assert f is not None, f"{ident} missing from ledger"
        assert f["status"] == "closed", (
            f"{ident}: expected closed, got {f['status']}"
        )
        assert f["behavioral_test_path"], (
            f"{ident}: closed without behavioral_test_path — gate violation"
        )


def test_w77_builder_includes_v11_audited_closures():
    """V11-closed findings audited by V12 W73 (AA5-1, BB5-F4, AAA-F1,
    AAA-F2, CCC-2) must show as closed via the v11_closures_audited
    overlay."""
    data = json.loads(LEDGER_JSON.read_text())
    by_id = {f["id"]: f for f in data["findings"]}
    for ident in ("AA5-1", "BB5-F4", "AAA-F1", "AAA-F2", "CCC-2"):
        f = by_id.get(ident)
        assert f is not None, f"{ident} missing"
        assert f["status"] == "closed", (
            f"{ident}: expected closed (V11 closure audited in V12), "
            f"got {f['status']}"
        )


# ────────────────────────────────────────────────────────────────────
# Verifier: catches violations.
# ────────────────────────────────────────────────────────────────────

def test_w77_verifier_passes_against_committed_ledger():
    """Live ledger must pass internal consistency check."""
    proc = subprocess.run(
        [str(REPO_ROOT / "venv" / "bin" / "python"), str(VERIFIER)],
        capture_output=True, text=True, timeout=30, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, (
        f"Ledger verification failed:\n{proc.stdout}\n{proc.stderr}"
    )
    assert "PASS" in proc.stdout


def test_w77_verifier_catches_closed_without_test(tmp_path: Path):
    """Inject a closed finding without behavioral_test_path; verifier
    must exit 1."""
    sb = tmp_path
    (sb / "artifacts" / "audit").mkdir(parents=True)
    (sb / "scripts" / "ci").mkdir(parents=True)
    # Copy the verifier; rewrite REPO_ROOT to use the sandbox path.
    verifier_src = VERIFIER.read_text()
    (sb / "scripts" / "ci" / "verify_findings_ledger.py").write_text(verifier_src)
    bad = {
        "schema_version": 1,
        "n_findings": 1,
        "findings": [
            {
                "id": "FAKE-CLOSED",
                "first_appearance_version": "v12",
                "track": "v12",
                "summary": "fabricated closed without test",
                "severity_at_first_appearance": "critical",
                "status": "closed",
                "wave_closed": 99,
                "behavioral_test_path": None,
                "deferral_reason": None,
            },
        ],
    }
    (sb / "artifacts" / "audit" / "findings_ledger.json").write_text(json.dumps(bad))
    proc = subprocess.run(
        [str(REPO_ROOT / "venv" / "bin" / "python"),
         "scripts/ci/verify_findings_ledger.py"],
        capture_output=True, text=True, timeout=30, cwd=sb,
    )
    assert proc.returncode == 1, (
        f"Verifier should reject closed-without-test.\nstdout:\n{proc.stdout}"
    )
    assert "FAKE-CLOSED" in proc.stdout
    assert "behavioral_test_path" in proc.stdout


def test_w77_verifier_catches_deferred_without_reason(tmp_path: Path):
    """Inject a deferred finding without deferral_reason; verifier
    must exit 1."""
    sb = tmp_path
    (sb / "artifacts" / "audit").mkdir(parents=True)
    (sb / "scripts" / "ci").mkdir(parents=True)
    verifier_src = VERIFIER.read_text()
    (sb / "scripts" / "ci" / "verify_findings_ledger.py").write_text(verifier_src)
    bad = {
        "schema_version": 1,
        "n_findings": 1,
        "findings": [
            {
                "id": "FAKE-DEFERRED",
                "first_appearance_version": "v12",
                "track": "v12",
                "summary": "fabricated deferred without reason",
                "severity_at_first_appearance": "high",
                "status": "deferred",
                "wave_closed": None,
                "behavioral_test_path": None,
                "deferral_reason": None,
            },
        ],
    }
    (sb / "artifacts" / "audit" / "findings_ledger.json").write_text(json.dumps(bad))
    proc = subprocess.run(
        [str(REPO_ROOT / "venv" / "bin" / "python"),
         "scripts/ci/verify_findings_ledger.py"],
        capture_output=True, text=True, timeout=30, cwd=sb,
    )
    assert proc.returncode == 1
    assert "FAKE-DEFERRED" in proc.stdout
    assert "deferral_reason" in proc.stdout


# ────────────────────────────────────────────────────────────────────
# Schema integrity.
# ────────────────────────────────────────────────────────────────────

def test_w77_ledger_schema_version_1():
    data = json.loads(LEDGER_JSON.read_text())
    assert data["schema_version"] == 1
    assert "n_findings" in data
    assert "findings" in data
    assert isinstance(data["findings"], list)


def test_w77_ledger_every_record_has_required_fields():
    """Every ledger record carries the required schema fields."""
    data = json.loads(LEDGER_JSON.read_text())
    required = {
        "id", "first_appearance_version", "track", "summary",
        "severity_at_first_appearance", "status",
        "wave_closed", "behavioral_test_path", "deferral_reason",
    }
    for f in data["findings"]:
        missing = required - set(f.keys())
        assert not missing, f"{f.get('id', '?')} missing fields: {missing}"
        assert f["status"] in {
            "open", "closed", "deferred", "documented_by_design",
        }, f"{f['id']}: bad status {f['status']}"


def test_w77_no_duplicate_ids_in_ledger():
    data = json.loads(LEDGER_JSON.read_text())
    ids = [f["id"] for f in data["findings"]]
    duplicates = [i for i in set(ids) if ids.count(i) > 1]
    assert not duplicates, f"Duplicate IDs in ledger: {duplicates}"
