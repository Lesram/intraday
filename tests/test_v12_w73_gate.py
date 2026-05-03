"""V12 W73: behavioral test for the marker-only-critical-high CI gate.

The gate (``scripts/ci/forbid_marker_only_critical_high.py``) is the
heart of W73 — it prevents future Critical/High audit closures from
shipping with marker-only tests, the wave-47 JWT failure pattern.

These tests run the gate against fabricated v12_state.json fixtures
to verify it correctly flags violations and passes when all closures
have behavioral tests.

Run with:
    ./venv/bin/python -m pytest tests/test_v12_w73_gate.py -v
"""
from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
GATE = REPO_ROOT / "scripts" / "ci" / "forbid_marker_only_critical_high.py"


def test_gate_script_exists_and_runs():
    """Gate must be runnable as a Python entrypoint."""
    proc = subprocess.run(
        ["./venv/bin/python", str(GATE)],
        capture_output=True, text=True, timeout=30, cwd=REPO_ROOT,
    )
    # Exit 0 = pass (current state); exit 1 = at least one Crit/High
    # violation; exit 2 = state file missing.  We tolerate 0 or 1 here
    # — the meaningful assertion is "doesn't crash".
    assert proc.returncode in (0, 1), proc.stderr
    assert "marker-only Critical/High gate" in proc.stdout


def test_gate_passes_on_real_state_file():
    """Live invariant: the live v12_state.json + tests must pass the
    gate (W73 is itself supposed to satisfy the gate it just built)."""
    proc = subprocess.run(
        ["./venv/bin/python", str(GATE)],
        capture_output=True, text=True, timeout=30, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, (
        f"V12 W73 gate failed against live state.json:\n{proc.stdout}\n{proc.stderr}"
    )


def test_gate_fails_when_critical_finding_lacks_test(tmp_path: Path):
    """Build a fabricated state.json with a Critical finding pointing
    at a non-existent test file.  Gate must exit 1."""
    state_dir = tmp_path / "artifacts" / "audit" / "v12"
    state_dir.mkdir(parents=True)
    fake_state = {
        "schema_version": 1,
        "findings": [
            {
                "id": "FAKE-1",
                "from": "v12",
                "severity": "critical",
                "title": "fabricated for test",
                "status": "closed",
                "wave_target": 99,
                "wave_closed": 99,
                "behavioral_test_path": "tests/test_does_not_exist.py::test_nope",
            }
        ],
    }
    (state_dir / "v12_state.json").write_text(json.dumps(fake_state))
    # Set up a sandbox repo containing only the gate + classifier.
    (tmp_path / "scripts" / "ci").mkdir(parents=True)
    classifier_src = (REPO_ROOT / "scripts" / "ci" / "classify_wave_tests.py").read_text()
    gate_src = (REPO_ROOT / "scripts" / "ci" / "forbid_marker_only_critical_high.py").read_text()
    (tmp_path / "scripts" / "ci" / "classify_wave_tests.py").write_text(classifier_src)
    (tmp_path / "scripts" / "ci" / "forbid_marker_only_critical_high.py").write_text(gate_src)

    proc = subprocess.run(
        [str(REPO_ROOT / "venv" / "bin" / "python"),
         "scripts/ci/forbid_marker_only_critical_high.py"],
        capture_output=True, text=True, timeout=30, cwd=tmp_path,
    )
    assert proc.returncode == 1, (
        f"Gate should fail on missing test, got exit={proc.returncode}.\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "FAKE-1" in proc.stdout
    assert "missing" in proc.stdout or "not found" in proc.stdout


def test_gate_fails_on_marker_only_test_for_high_finding(tmp_path: Path):
    """Build a state.json with a High finding pointing at a real but
    marker-only test.  Gate must exit 1."""
    # Set up sandbox.
    (tmp_path / "tests").mkdir()
    marker_only_src = textwrap.dedent('''
        import inspect
        def test_only_marker():
            from os import path  # any module
            src = inspect.getsource(path)
            assert "join" in src
    ''')
    (tmp_path / "tests" / "test_marker_only_fixture.py").write_text(marker_only_src)

    state_dir = tmp_path / "artifacts" / "audit" / "v12"
    state_dir.mkdir(parents=True)
    fake_state = {
        "schema_version": 1,
        "findings": [
            {
                "id": "HIGH-FAKE",
                "from": "v12",
                "severity": "high",
                "title": "fabricated marker-only",
                "status": "closed",
                "wave_target": 99,
                "wave_closed": 99,
                "behavioral_test_path": "tests/test_marker_only_fixture.py::test_only_marker",
            }
        ],
    }
    (state_dir / "v12_state.json").write_text(json.dumps(fake_state))

    (tmp_path / "scripts" / "ci").mkdir(parents=True)
    classifier_src = (REPO_ROOT / "scripts" / "ci" / "classify_wave_tests.py").read_text()
    gate_src = (REPO_ROOT / "scripts" / "ci" / "forbid_marker_only_critical_high.py").read_text()
    (tmp_path / "scripts" / "ci" / "classify_wave_tests.py").write_text(classifier_src)
    (tmp_path / "scripts" / "ci" / "forbid_marker_only_critical_high.py").write_text(gate_src)

    proc = subprocess.run(
        [str(REPO_ROOT / "venv" / "bin" / "python"),
         "scripts/ci/forbid_marker_only_critical_high.py"],
        capture_output=True, text=True, timeout=30, cwd=tmp_path,
    )
    assert proc.returncode == 1, (
        f"Gate should reject marker-only test for High finding.\n"
        f"stdout:\n{proc.stdout}"
    )
    assert "HIGH-FAKE" in proc.stdout
    assert "marker-only" in proc.stdout


def test_gate_passes_on_behavioral_test(tmp_path: Path):
    """A real, behavioral test for a Critical finding must pass."""
    (tmp_path / "tests").mkdir()
    behavioral_src = textwrap.dedent('''
        def test_real_call():
            import os
            # Calls live code, asserts on return value.
            cwd = os.getcwd()
            assert isinstance(cwd, str)
            assert len(cwd) > 0
    ''')
    (tmp_path / "tests" / "test_behavioral_fixture.py").write_text(behavioral_src)

    state_dir = tmp_path / "artifacts" / "audit" / "v12"
    state_dir.mkdir(parents=True)
    fake_state = {
        "schema_version": 1,
        "findings": [
            {
                "id": "CRIT-OK",
                "from": "v12",
                "severity": "critical",
                "title": "fabricated behavioral",
                "status": "closed",
                "wave_target": 99,
                "wave_closed": 99,
                "behavioral_test_path": "tests/test_behavioral_fixture.py::test_real_call",
            }
        ],
    }
    (state_dir / "v12_state.json").write_text(json.dumps(fake_state))

    (tmp_path / "scripts" / "ci").mkdir(parents=True)
    classifier_src = (REPO_ROOT / "scripts" / "ci" / "classify_wave_tests.py").read_text()
    gate_src = (REPO_ROOT / "scripts" / "ci" / "forbid_marker_only_critical_high.py").read_text()
    (tmp_path / "scripts" / "ci" / "classify_wave_tests.py").write_text(classifier_src)
    (tmp_path / "scripts" / "ci" / "forbid_marker_only_critical_high.py").write_text(gate_src)

    proc = subprocess.run(
        [str(REPO_ROOT / "venv" / "bin" / "python"),
         "scripts/ci/forbid_marker_only_critical_high.py"],
        capture_output=True, text=True, timeout=30, cwd=tmp_path,
    )
    assert proc.returncode == 0, (
        f"Gate should pass on real behavioral test.\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "CRIT-OK" in proc.stdout
