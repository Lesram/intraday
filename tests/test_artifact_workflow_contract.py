"""Failure-path contracts for workflows that generate full evidence packs."""

from pathlib import Path
import shlex

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
FULL_CONSUMERS = [
    ("pr-verify.yml", "organism-tests"),
    ("paper-postclose-audit.yml", "collect-and-audit"),
]


def _job(workflow: str, job_name: str) -> dict:
    path = ROOT / ".github" / "workflows" / workflow
    return yaml.safe_load(path.read_text())["jobs"][job_name]


def _full_pack(job: dict) -> dict:
    return next(
        step for step in job["steps"]
        if step.get("run", "").strip()
        == "python scripts/ci/generate_artifacts.py full"
    )


@pytest.mark.parametrize("workflow,job_name", FULL_CONSUMERS)
def test_full_pack_failures_remain_fatal(workflow, job_name):
    job = _job(workflow, job_name)
    assert job.get("continue-on-error", False) is False
    assert _full_pack(job).get("continue-on-error", False) is False


@pytest.mark.parametrize("workflow,job_name", FULL_CONSUMERS)
def test_failed_full_pack_still_produces_and_uploads_audit_index(workflow, job_name):
    job = _job(workflow, job_name)
    steps = job["steps"]
    pack_index = steps.index(_full_pack(job))
    index_step = next(
        step for step in steps
        if step.get("run") == "python scripts/ci/generate_audit_index.py"
    )
    upload_step = next(
        step for step in steps
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )

    assert pack_index < steps.index(index_step) < steps.index(upload_step)
    assert index_step.get("if") == "always()"
    assert upload_step.get("if") == "always()"
    uploaded_paths = upload_step["with"]["path"].splitlines()
    assert "artifacts/" in uploaded_paths
    assert "docs/engineering/LIVE_AUDIT_INDEX.md" in uploaded_paths


def test_failed_organism_suite_still_generates_full_evidence():
    job = _job("pr-verify.yml", "organism-tests")
    pack = _full_pack(job)
    preceding_steps = job["steps"][:job["steps"].index(pack)]
    assert any("pytest" in step.get("run", "") for step in preceding_steps)
    assert pack.get("if") == "always()"


@pytest.mark.parametrize("command", [
    "python scripts/ci/run_phase8_postclose_evidence.py",
    "python scripts/ci/check_kpi_thresholds.py",
])
def test_postclose_reporting_runs_even_when_an_earlier_report_fails(command):
    job = _job("paper-postclose-audit.yml", "collect-and-audit")
    report_step = next(step for step in job["steps"] if step.get("run") == command)
    assert job["steps"].index(_full_pack(job)) < job["steps"].index(report_step)
    assert report_step.get("if") == "always()"


@pytest.mark.parametrize("workflow,job_name", FULL_CONSUMERS)
def test_full_pack_has_bounded_time_and_reporting_headroom(workflow, job_name):
    job = _job(workflow, job_name)
    pack_minutes = _full_pack(job)["timeout-minutes"]
    # Six ordinary suites, replay, semantic checks, snapshot and spec checks
    # can consume 20.5 minutes at their configured process timeout ceilings.
    assert 21 <= pack_minutes <= 25
    assert job["timeout-minutes"] >= pack_minutes + 10


def test_organism_job_budget_covers_existing_suite_limits_and_reporting():
    job = _job("pr-verify.yml", "organism-tests")
    bounded_minutes = sum(step.get("timeout-minutes", 0) for step in job["steps"])
    # A job timeout would suppress even always() evidence steps. Keep extra
    # time beyond all explicit suite, full-pack and audit-index ceilings.
    assert job["timeout-minutes"] >= bounded_minutes + 5


def test_focused_checks_cover_stacked_prs_and_all_owned_sources():
    path = ROOT / ".github" / "workflows" / "artifact-reporting.yml"
    workflow = yaml.safe_load(path.read_text())
    # PyYAML's YAML 1.1 resolver reads GitHub's unquoted `on` as boolean True.
    triggers = workflow.get("on", workflow.get(True))
    pull_request = triggers["pull_request"]
    assert "branches" not in pull_request
    assert "branches-ignore" not in pull_request
    assert set(pull_request["paths"]) >= {
        ".github/workflows/artifact-reporting.yml",
        ".github/workflows/pr-verify.yml",
        ".github/workflows/paper-postclose-audit.yml",
        "scripts/ci/generate_artifacts.py",
        "scripts/ci/change_scope.py",
        "scripts/ci/generate_audit_index.py",
        "requirements.lock",
        "tests/test_generate_artifacts.py",
        "tests/test_artifact_workflow_contract.py",
        "tests/test_artifact_change_scope.py",
    }
    assert workflow["permissions"] == {"contents": "read"}


def test_focused_checks_run_isolated_tests_and_keep_failure_evidence():
    job = _job("artifact-reporting.yml", "focused-tests")
    assert job["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert job["env"]["USE_MOCK_BROKER"] == "true"
    assert job["env"]["TRADING_EXECUTION_MODE"] == "shadow"
    test_step = next(step for step in job["steps"] if "pytest --noconftest" in step.get("run", ""))
    run = test_step["run"]
    tokens = shlex.split(run.replace("\\\n", " "))
    assert "--noconftest" in tokens
    assert "addopts=" in tokens
    assert set(tokens) >= {
        "tests/test_generate_artifacts.py",
        "tests/test_artifact_workflow_contract.py",
        "tests/test_artifact_change_scope.py",
    }
    assert "set -o pipefail" in run
    assert job.get("continue-on-error", False) is False
    assert test_step.get("continue-on-error", False) is False
    assert 0 < test_step["timeout-minutes"] < job["timeout-minutes"]

    upload = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/upload-artifact@"))
    assert job["steps"].index(test_step) < job["steps"].index(upload)
    assert upload["if"] == "always()"
    output_dir = upload["with"]["path"].rstrip("/")
    assert f"--junitxml={output_dir}/junit.xml" in tokens
    assert tokens[tokens.index("tee") + 1] == f"{output_dir}/pytest.log"


def test_focused_dependencies_match_repository_pins():
    job = _job("artifact-reporting.yml", "focused-tests")
    install = next(step for step in job["steps"] if "pip install" in step.get("run", ""))
    tokens = shlex.split(install["run"])
    packages = tokens[tokens.index("install") + 1:]
    assert {item.split("==")[0] for item in packages} == {"pytest", "pytest-timeout", "PyYAML"}
    locked = set((ROOT / "requirements.lock").read_text().splitlines())
    assert set(packages) <= locked
