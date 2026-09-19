"""Failure-path tests for the pure post-close evidence validator."""
import json
import os
import time

import pytest

from scripts.ci import check_kpi_thresholds as checker

SHA = "a" * 40


def _write(directory, name, payload):
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return path


@pytest.fixture
def valid_pack(tmp_path):
    result = {"status": "pass", "passed": 3, "failed": 0, "errors": 0, "exit_code": 0}
    for name, field in checker.STATUS_FILES.items():
        _write(tmp_path, name, {field: "pass"})
    _write(tmp_path, "test_summary.json", {
        "overall": "pass", "suites": {key: dict(result) for key in checker.REQUIRED_SUITES},
    })
    _write(tmp_path, "replay_summary.json", result)
    _write(tmp_path, "semantic_invariants_summary.json", {**result, "overall": "pass"})
    _write(tmp_path, "grep_assertions.json", {"overall": "pass", "checks": [{"passed": True}]})
    _write(tmp_path, "task_report.json", {"artifact_pack_status": "pass", "sha": SHA, "tests_failed": []})
    _write(tmp_path, "runtime_config_snapshot.json", {"exploration_enabled": False})
    _write(tmp_path, "phase8_evidence_warehouse/postclose_run_summary.json", {"ok": True, "errors": []})
    return tmp_path


def test_valid_full_evidence_passes(valid_pack):
    assert checker.evaluate(valid_pack, expected_sha=SHA, require_phase8=True) == []


@pytest.mark.parametrize("name", list(checker.STATUS_FILES) + ["runtime_config_snapshot.json"])
def test_any_missing_required_evidence_fails(valid_pack, name):
    (valid_pack / name).unlink()
    assert checker.evaluate(valid_pack, expected_sha=SHA)


@pytest.mark.parametrize("payload", ["not json", "[]", "null", '"pass"'])
def test_malformed_or_wrong_type_evidence_fails(valid_pack, payload):
    (valid_pack / "replay_summary.json").write_text(payload)
    assert checker.evaluate(valid_pack, expected_sha=SHA)


@pytest.mark.parametrize("patch", [
    {"passed": 0}, {"exit_code": 1}, {"timed_out": True},
    {"status": "skipped"}, {"status": "error"}, {"errors": 1},
    {"passed": True}, {"failed": 1}, {"error": "interrupted"},
])
def test_replay_cannot_hide_failure_behind_pass_status(valid_pack, patch):
    path = valid_pack / "replay_summary.json"
    data = json.loads(path.read_text())
    path.write_text(json.dumps({**data, **patch}))
    assert checker.evaluate(valid_pack, expected_sha=SHA)


def test_missing_required_suite_fails(valid_pack):
    path = valid_pack / "test_summary.json"
    data = json.loads(path.read_text())
    del data["suites"]["safety_invariants"]
    path.write_text(json.dumps(data))
    assert "test_summary.json: required suites are missing" in checker.evaluate(valid_pack, expected_sha=SHA)


@pytest.mark.parametrize("snapshot", [{}, {"exploration_enabled": True}, {"exploration_enabled": "false"}])
def test_exploration_requires_explicit_false(valid_pack, snapshot):
    _write(valid_pack, "runtime_config_snapshot.json", snapshot)
    assert checker.evaluate(valid_pack, expected_sha=SHA)


def test_stale_artifact_and_different_commit_fail(valid_pack):
    started = time.time() - 5
    path = valid_pack / "replay_summary.json"
    os.utime(path, (started - 10, started - 10))
    errors = checker.evaluate(valid_pack, expected_sha="b" * 40, started_at=started)
    assert "replay_summary.json: stale evidence" in errors
    assert "task_report.json: source SHA does not match audited source" in errors


@pytest.mark.parametrize("kwargs", [
    {"upstream_status": "failure"}, {"pack_outcome": "skipped"}, {"pack_outcome": "cancelled"},
])
def test_workflow_failure_cannot_be_hidden_by_valid_files(valid_pack, kwargs):
    assert checker.evaluate(valid_pack, expected_sha=SHA, **kwargs)


def test_missing_phase8_evidence_fails_when_required(valid_pack):
    (valid_pack / "phase8_evidence_warehouse/postclose_run_summary.json").unlink()
    assert checker.evaluate(valid_pack, expected_sha=SHA, require_phase8=True)


def test_missing_pack_writes_failure_report_without_attempting_delivery(tmp_path, monkeypatch):
    monkeypatch.setattr(checker.subprocess, "run", lambda *args, **kwargs: pytest.fail("must not send notifications"))
    assert checker.main(["--artifacts-dir", str(tmp_path), "--expected-sha", SHA]) == 1
    result = json.loads((tmp_path / "postclose_kpi_report.json").read_text())
    assert result["status"] == "fail"
    assert result["breaches"]
    assert "no send attempted" in result["notification"]
    assert (tmp_path / "postclose_kpi_report.md").exists()


def test_success_report_and_step_summary_are_durable(valid_pack, tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert checker.main(["--artifacts-dir", str(valid_pack), "--expected-sha", SHA]) == 0
    assert json.loads((valid_pack / "postclose_kpi_report.json").read_text())["status"] == "pass"
    assert "PASS" in summary.read_text()


def test_invalid_runtime_metadata_still_writes_failure_report(valid_pack, monkeypatch):
    monkeypatch.setenv("CI_RUN_STARTED_AT", "bad timestamp")
    assert checker.main(["--artifacts-dir", str(valid_pack), "--expected-sha", SHA]) == 1
    assert json.loads((valid_pack / "postclose_kpi_report.json").read_text())["status"] == "fail"
