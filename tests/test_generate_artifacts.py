"""Exercise artifact failure reporting without importing the trading platform."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "generate_artifacts.py"


@pytest.fixture
def generator(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("generate_artifacts_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    monkeypatch.setattr(module, "ART", artifact_dir)
    # The child pytest must neither discover repository conftest nor load
    # unrelated installed plugins; only its timeout plugin is needed.
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTEST_ADDOPTS", "-p pytest_timeout")
    return module


def _test_file(generator, source, path="tests/test_example.py"):
    target = generator.ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source)
    return path


@pytest.mark.parametrize(("source", "status", "passed", "failed", "errors", "exit_code"), [
    ("def test_good(): assert True\n", "pass", 1, 0, 0, 0),
    ("def test_good(): assert True\ndef test_bad(): assert False\n", "fail", 1, 1, 0, 1),
    ("def test_bad(): assert False\n", "fail", 0, 1, 0, 1),
    ("def helper(): pass\n", "fail", 0, 0, 0, 5),
    ("import pytest\n@pytest.mark.skip\ndef test_skipped(): pass\n", "fail", 0, 0, 0, 0),
    ("raise RuntimeError('collection failure sentinel')\n", "fail", 0, 0, 1, 2),
])
def test_real_pytest_counts_and_exit_status(generator, source, status, passed, failed, errors, exit_code):
    path = _test_file(generator, source)

    result = generator.run_pytest("example", path, timeout=15)

    assert result["status"] == status
    assert (result["passed"], result["failed"], result["errors"]) == (passed, failed, errors)
    assert result["exit_code"] == exit_code
    output = (generator.ROOT / result["output_file"]).read_text()
    assert output
    assert result["output_tail"] == output[-800:]
    if "collection failure" in source:
        assert "collection failure sentinel" in output


def test_failed_process_overrides_passing_junit(generator, monkeypatch):
    path = _test_file(generator, "def test_good(): assert True\n")
    run_command = generator.run_command

    def fail_after_tests(cmd, **kwargs):
        result = run_command(cmd, **kwargs)
        assert result.exit_code == 0
        result.exit_code = 3
        result.stderr = "post-test process failure sentinel"
        return result

    monkeypatch.setattr(generator, "run_command", fail_after_tests)

    result = generator.run_pytest("example", path, timeout=15)

    assert result["passed"] == 1
    assert result["status"] == "fail"
    assert result["exit_code"] == 3
    assert "post-test process failure sentinel" in (generator.ROOT / result["output_file"]).read_text()


@pytest.mark.parametrize("fresh_xml", [None, "not XML", "<notjunit/>"])
def test_stale_or_malformed_junit_cannot_pass(generator, monkeypatch, fresh_xml):
    path = _test_file(generator, "def test_good(): assert True\n")
    xml_path = generator.ART / "example.junit.xml"
    xml_path.write_text('<testsuites><testsuite><testcase name="old_pass"/></testsuite></testsuites>')

    def no_real_test(cmd, **kwargs):
        if fresh_xml is not None:
            xml_path.write_text(fresh_xml)
        return generator.CommandResult(0, stdout="99 passed (untrusted text)\n")

    monkeypatch.setattr(generator, "run_command", no_real_test)
    result = generator.run_pytest("example", path, timeout=15)

    assert result["status"] == "fail"
    assert result["passed"] == 0
    assert "invalid pytest evidence" in result["error"]


def test_missing_required_suite_is_a_failure(generator):
    generator.gen_test_summary()
    generator.gen_replay_summary()
    generator.gen_semantic_invariants_summary()

    suites = json.loads((generator.ART / "test_summary.json").read_text())
    assert suites["overall"] == "fail"
    assert len(suites["suites"]) == 6
    assert all(row["status"] == "fail" for row in suites["suites"].values())
    assert json.loads((generator.ART / "replay_summary.json").read_text())["status"] == "fail"
    assert json.loads((generator.ART / "semantic_invariants_summary.json").read_text())["overall"] == "fail"


def test_missing_command_retains_error(generator):
    result = generator.run_command([str(generator.ROOT / "missing-executable")], timeout=1)

    assert result.exit_code is None
    assert result.error
    assert not result.timed_out


def test_command_timeout_retains_partial_output(generator):
    started = time.monotonic()
    result = generator.run_command([
        sys.executable, "-c", "import time; print('before timeout', flush=True); time.sleep(30)",
    ], timeout=0.3)

    assert time.monotonic() - started < 5
    assert result.timed_out
    assert result.exit_code != 0
    assert "before timeout" in result.output
    assert "timed out" in result.error


def test_pytest_wall_timeout_cannot_pass(generator):
    path = _test_file(generator, "import time\ndef test_wait(): time.sleep(30)\n")

    result = generator.run_pytest("example", path, timeout=0.3)

    assert result["status"] == "fail"
    assert result["timed_out"]
    assert "timed out" in result["error"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX process group cleanup")
def test_timeout_terminates_descendants(generator):
    marker = generator.ROOT / "descendant_survived"
    child = f"import time; from pathlib import Path; time.sleep(0.8); Path({str(marker)!r}).write_text('alive')"
    parent = f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(30)"

    result = generator.run_command([sys.executable, "-c", parent], timeout=0.2)

    assert result.timed_out
    time.sleep(1)
    assert not marker.exists()


@pytest.mark.parametrize(("exit_code", "stdout"), [
    (1, '{"overall": "pass", "drift_count": 0}'),
    (0, "not a JSON verdict"),
    (0, "[]"),
])
def test_spec_drift_requires_process_and_json_success(generator, monkeypatch, exit_code, stdout):
    monkeypatch.setattr(generator, "run_command", lambda *a, **kw: generator.CommandResult(exit_code, stdout))

    generator.gen_spec_drift_summary()

    result = json.loads((generator.ART / "spec_drift_summary.json").read_text())
    assert result["overall"] == "fail"
    assert result["exit_code"] == exit_code


def test_spec_drift_preserves_valid_schema(generator, monkeypatch):
    original = {"overall": "pass", "drift_count": 0, "sources": {"runtime_defaults": 12}}
    monkeypatch.setattr(generator, "run_command", lambda *a, **kw: generator.CommandResult(0, json.dumps(original)))

    generator.gen_spec_drift_summary()

    result = json.loads((generator.ART / "spec_drift_summary.json").read_text())
    assert all(result[key] == value for key, value in original.items())


def test_negative_grep_assertions_fail_on_execution_error(generator):
    generator.gen_grep_assertions()

    result = json.loads((generator.ART / "grep_assertions.json").read_text())
    assert result["overall"] == "fail"
    assert all(not check["passed"] for check in result["checks"])
    assert all(check["exit_code"] == 2 for check in result["checks"])


@pytest.mark.parametrize("return_code", [0, 1])
def test_snapshot_must_be_fresh_and_complete(generator, monkeypatch, return_code):
    for name in generator.RUNTIME_SNAPSHOT_FILES:
        (generator.ART / name).write_text('{"old": "snapshot"}')
    monkeypatch.setattr(generator, "run_command", lambda *a, **kw: generator.CommandResult(return_code, stderr="snapshot sentinel"))

    generator.gen_runtime_snapshot()

    result = json.loads((generator.ART / "runtime_snapshot_summary.json").read_text())
    assert result["overall"] == "fail"
    assert result["exit_code"] == return_code
    assert "snapshot sentinel" in (generator.ART / "runtime_snapshot.log").read_text()
    for name in generator.RUNTIME_SNAPSHOT_FILES:
        assert "error" in json.loads((generator.ART / name).read_text())


def test_snapshot_error_preserves_original_diagnostic(generator, monkeypatch):
    def failed_snapshot(*args, **kwargs):
        for name in generator.RUNTIME_SNAPSHOT_FILES:
            generator.write(name, {"error": "original import failure sentinel"})
        return generator.CommandResult(0)

    monkeypatch.setattr(generator, "run_command", failed_snapshot)

    generator.gen_runtime_snapshot()

    result = json.loads((generator.ART / "runtime_snapshot_summary.json").read_text())
    assert result["overall"] == "fail"
    assert all("original import failure sentinel" in error for error in result["errors"])
    for name in generator.RUNTIME_SNAPSHOT_FILES:
        assert json.loads((generator.ART / name).read_text())["error"] == "original import failure sentinel"


def test_snapshot_process_failure_marks_legacy_error_without_discarding_values(generator, monkeypatch):
    def failed_after_write(*args, **kwargs):
        for name in generator.RUNTIME_SNAPSHOT_FILES:
            generator.write(name, {"observed_value": 12})
        return generator.CommandResult(1, stderr="failure after snapshots were written")

    monkeypatch.setattr(generator, "run_command", failed_after_write)

    generator.gen_runtime_snapshot()

    legacy = json.loads((generator.ART / "runtime_config_snapshot.json").read_text())
    assert legacy["observed_value"] == 12
    assert "code 1" in legacy["error"]
    assert json.loads((generator.ART / "runtime_snapshot_summary.json").read_text())["overall"] == "fail"


def _stub_pack(generator, monkeypatch, failed_stage=None):
    monkeypatch.setattr(generator, "get_change_set", lambda **kw: SimpleNamespace(paths=[], scope="task", ref="HEAD"))
    monkeypatch.setattr(generator, "sh", lambda *a, **kw: "test-evidence")
    stages = {
        "gen_runtime_snapshot": ("runtime_snapshot_summary.json", {"overall": "pass"}),
        "gen_grep_assertions": ("grep_assertions.json", {"overall": "pass", "checks": []}),
        "gen_test_summary": ("test_summary.json", {"overall": "pass", "suites": {"example": {"status": "pass"}}}),
        "gen_replay_summary": ("replay_summary.json", {"status": "pass", "passed": 1, "failed": 0}),
        "gen_semantic_invariants_summary": ("semantic_invariants_summary.json", {"overall": "pass", "passed": 1, "failed": 0}),
        "gen_spec_drift_summary": ("spec_drift_summary.json", {"overall": "pass"}),
    }
    for function_name, (filename, data) in stages.items():
        if function_name == failed_stage:
            data = {**data, "overall": "fail", "status": "fail"}
            if "suites" in data:
                data["suites"] = {"example": {"status": "fail"}}
        monkeypatch.setattr(generator, function_name, lambda filename=filename, data=data: generator.write(filename, data))
    return stages


@pytest.mark.parametrize("failed_stage", [
    None, "gen_runtime_snapshot", "gen_grep_assertions", "gen_test_summary",
    "gen_replay_summary", "gen_semantic_invariants_summary", "gen_spec_drift_summary",
])
def test_full_exit_requires_every_gate_but_finishes_evidence(generator, monkeypatch, failed_stage):
    stages = _stub_pack(generator, monkeypatch, failed_stage)

    exit_code = generator.main("full")

    assert exit_code == (1 if failed_stage else 0)
    assert all((generator.ART / filename).exists() for filename, _ in stages.values())
    report = json.loads((generator.ART / "task_report.json").read_text())
    assert report["artifact_pack_status"] == ("fail" if failed_stage else "pass")
    if failed_stage:
        assert report["artifact_pack_errors"]
    if failed_stage == "gen_replay_summary":
        assert "replay_simulator" in report["tests_failed"]
        assert "replay_simulator" not in report["tests_passed"]


def test_unexpected_stage_error_does_not_hide_other_evidence(generator, monkeypatch):
    stages = _stub_pack(generator, monkeypatch)

    def broken_replay():
        raise RuntimeError("stage failure sentinel")

    monkeypatch.setattr(generator, "gen_replay_summary", broken_replay)

    assert generator.main("full") == 1
    assert all((generator.ART / filename).exists() for filename, _ in stages.values())
    replay = json.loads((generator.ART / "replay_summary.json").read_text())
    assert replay["status"] == "fail"
    assert "stage failure sentinel" in replay["error"]


@pytest.mark.parametrize("old_status", ["pass", "fail"])
def test_quick_mode_replaces_stale_full_results(generator, monkeypatch, old_status):
    _stub_pack(generator, monkeypatch)
    for name in ("replay_summary.json", "semantic_invariants_summary.json", "spec_drift_summary.json"):
        (generator.ART / name).write_text(json.dumps({"status": old_status, "overall": old_status, "passed": 999}))

    assert generator.main("quick") == 0

    report = json.loads((generator.ART / "task_report.json").read_text())
    assert report["tests_passed"] == ["quick_artifact_pack"]
    assert report["tests_failed"] == []
    for name in ("replay_summary.json", "semantic_invariants_summary.json", "spec_drift_summary.json"):
        data = json.loads((generator.ART / name).read_text())
        assert data["status"] == "skipped"
        assert "passed" not in data


def test_full_mode_replaces_quick_skip_markers(generator, monkeypatch):
    _stub_pack(generator, monkeypatch)
    assert generator.main("quick") == 0

    assert generator.main("full") == 0

    report = json.loads((generator.ART / "task_report.json").read_text())
    assert set(report["tests_passed"]) == {"example", "replay_simulator", "semantic_invariants"}
    assert "quick_artifact_pack" not in report["tests_passed"]


@pytest.mark.parametrize("failed_stage", ["gen_runtime_snapshot", "gen_grep_assertions"])
def test_quick_failure_is_not_reported_as_passed_checks(generator, monkeypatch, failed_stage):
    _stub_pack(generator, monkeypatch, failed_stage)

    assert generator.main("quick") == 1

    summary = json.loads((generator.ART / "test_summary.json").read_text())
    assert summary["overall"] == "fail"
    assert summary["suites"]["quick_artifact_pack"]["passed"] == 0
    report = json.loads((generator.ART / "task_report.json").read_text())
    assert report["tests_passed"] == []
    assert report["tests_failed"] == ["quick_artifact_pack"]


def test_invalid_mode_never_reuses_stale_evidence(generator):
    assert generator.main("typo") == 2
    assert not (generator.ART / "task_report.json").exists()
