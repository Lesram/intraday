"""Contracts for pinned-source CI, durable timeout reporting and opt-in delivery."""
import json
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = [("paper-postclose-audit.yml", "collect-and-audit"), ("nightly.yml", "deep-tests")]


def _load(name):
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text())


@pytest.mark.parametrize("name,job_name", WORKFLOWS)
def test_reusable_workflow_requires_source_and_does_not_self_schedule(name, job_name):
    workflow = _load(name)
    triggers = workflow.get("on", workflow.get(True))
    assert "schedule" not in triggers  # The reviewed main bridge is the single scheduler.
    for event in ("workflow_call", "workflow_dispatch"):
        inputs = triggers[event]["inputs"]
        assert inputs["source_sha"]["required"] is True
        assert inputs["notify_issues"]["default"] is False
        assert inputs["notify_issues"]["type"] == "boolean"
    job = workflow["jobs"][job_name]
    checkout = job["steps"][0]
    assert checkout["with"]["ref"] == "${{ inputs.source_sha }}"
    assert checkout["with"]["persist-credentials"] is False
    assert workflow["permissions"] == {"contents": "read"}
    assert "permissions" not in job
    assert job["env"]["USE_MOCK_BROKER"] == "true"
    assert job["env"]["TRADING_EXECUTION_MODE"] == "shadow"
    assert "secrets." not in json.dumps(job)


@pytest.mark.parametrize("name,job_name", WORKFLOWS)
def test_status_job_survives_worker_failure_and_only_sends_with_explicit_input(name, job_name):
    job = _load(name)["jobs"]["report-status"]
    assert job["needs"] == job_name and job["if"] == "always()"
    assert job["permissions"]["issues"] == "write"
    assert all("checkout" not in step.get("uses", "") for step in job["steps"])
    script = job["steps"][0]["with"]["script"]
    assert "process.env.NOTIFY_ISSUES === 'true'" in script
    assert "finally" in script and "workflow-status/result.json" in script
    assert "labels: ['bug']" in script
    assert "strategy" not in script.split("labels:")[-1].split("}")[0]
    upload = job["steps"][-1]
    assert upload["if"] == "always()"
    assert upload["with"]["if-no-files-found"] == "error"


@pytest.mark.parametrize("name,job_name", WORKFLOWS)
def test_provenance_program_validates_full_sha_and_clears_stale_evidence(name, job_name, tmp_path):
    job = _load(name)["jobs"][job_name]
    run = next(step["run"] for step in job["steps"] if step.get("id") == "provenance")
    code = run.split("<<'PYCODE'\n", 1)[1].rsplit("\nPYCODE", 1)[0]
    # Execute the actual workflow inline program with a fake git binary, no network.
    bindir = tmp_path / "bin"
    bindir.mkdir()
    git = bindir / "git"
    git.write_text("#!/bin/sh\nprintf '%s\\n' aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n")
    git.chmod(0o755)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "replay_summary.json").write_text('{"status":"pass"}')
    env = {"PATH": str(bindir), "CI_EXPECTED_SHA": "a" * 40, "GITHUB_SHA": "b" * 40,
           "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
           "GITHUB_ENV": str(tmp_path / "env"), "GITHUB_OUTPUT": str(tmp_path / "output")}
    import sys
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not (artifacts / "replay_summary.json").exists()
    provenance = json.loads((artifacts / "ci_run_provenance.json").read_text())
    assert provenance["source_sha"] == "a" * 40 and provenance["caller_sha"] == "b" * 40
    env["CI_EXPECTED_SHA"] = "main"
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    env["CI_EXPECTED_SHA"] = "c" * 40
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode != 0


def test_nightly_runs_suite_once_and_retains_raw_failure_output():
    job = _load("nightly.yml")["jobs"]["deep-tests"]
    steps = [step for step in job["steps"] if "pytest tests/" in step.get("run", "")]
    assert len(steps) == 1
    run = steps[0]["run"]
    assert "set -o pipefail" in run and "tee test_reports/nightly.log" in run
    assert "--junitxml=test_reports/nightly.xml" in run
    assert steps[0]["timeout-minutes"] < job["timeout-minutes"]
    assert "actions-gh-pages" not in json.dumps(job)


def test_postclose_failure_reports_have_freshness_and_outcome_context():
    job = _load("paper-postclose-audit.yml")["jobs"]["collect-and-audit"]
    step = next(step for step in job["steps"] if step.get("run") == "python scripts/ci/check_kpi_thresholds.py")
    assert step["if"] == "always()"
    assert step["env"]["CI_ARTIFACT_PACK_OUTCOME"] == "${{ steps.pack.outcome }}"
    assert step["env"]["CI_UPSTREAM_STATUS"] == "${{ job.status }}"
    assert step["env"]["CI_REQUIRE_PHASE8"] == "true"


@pytest.mark.parametrize("name,job_name", WORKFLOWS)
@pytest.mark.parametrize("notify,result,delivery_error,existing", [
    (False, "failure", False, False),
    (True, "success", False, False),
    (True, "failure", False, False),
    (True, "cancelled", True, False),
    (True, "failure", False, True),
])
def test_notification_program_is_opt_in_and_retains_delivery_failures(
    name, job_name, notify, result, delivery_error, existing, tmp_path,
):
    import shutil
    node = shutil.which("node")
    assert node, "Node is required to verify workflow notification behavior"
    script = _load(name)["jobs"]["report-status"]["steps"][0]["with"]["script"]
    url = "https://github.com/owner/repo/actions/runs/123"
    existing_issue = [{"number": 5, "title": "[Post-Close Audit] CI evidence failure" if job_name == "collect-and-audit" else "[Nightly Audit] CI evidence failure", "body": url, "html_url": "https://github.com/owner/repo/issues/5"}] if existing else []
    fixture = f"""
const calls = [];
const errors = [];
const context = {{serverUrl: 'https://github.com', repo: {{owner: 'owner', repo: 'repo'}}, sha: 'caller', runId: 123, workflow: 'audit'}};
const core = {{setFailed: msg => errors.push(msg), summary: {{addHeading() {{return this;}}, addRaw() {{return this;}}, async write() {{}}}}}};
const github = {{rest: {{issues: {{listForRepo: 'listForRepo', listComments: 'listComments',
  create: async args => {{calls.push(args); if ({str(delivery_error).lower()}) throw new Error('simulated permission failure'); return {{data: {{html_url: 'https://github.com/owner/repo/issues/1'}}}};}},
  createComment: async args => {{calls.push(args); return {{data: {{}}}};}}
}}}}, paginate: async fn => fn === 'listForRepo' ? {json.dumps(existing_issue)} : []}};
process.env.AUDIT_RESULT = {json.dumps(result)};
process.env.AUDITED_SHA = 'a'.repeat(40);
process.env.EXPECTED_SHA = 'a'.repeat(40);
process.env.NOTIFY_ISSUES = {json.dumps(str(notify).lower())};
(async () => {{
{script}
console.log(JSON.stringify({{calls, errors}}));
}})().catch(error => {{console.error(error); process.exitCode = 1;}});
"""
    completed = subprocess.run([node, "-e", fixture], cwd=tmp_path, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    observed = json.loads(completed.stdout)
    artifact = json.loads((tmp_path / "workflow-status/result.json").read_text())
    assert artifact["result"] == result
    if not notify or result == "success" or existing:
        assert observed["calls"] == []
    else:
        assert len(observed["calls"]) == 1
        assert observed["calls"][0]["labels"] == ["bug"]
    if delivery_error:
        assert observed["errors"]
        assert artifact["notification"] == "failed"
    elif notify and result != "success":
        assert artifact["notification"] == "delivered"
    elif not notify and result != "success":
        assert "disabled" in artifact["notification"]


def test_focused_pr_workflow_runs_new_checker_and_workflow_cases():
    workflow = _load("artifact-reporting.yml")
    triggers = workflow.get("on", workflow.get(True))
    paths = set(triggers["pull_request"]["paths"])
    assert {"scripts/ci/check_kpi_thresholds.py", ".github/workflows/nightly.yml",
            "tests/test_postclose_kpi_reporting.py", "tests/test_monday_ci_workflows.py"} <= paths
    steps = workflow["jobs"]["focused-tests"]["steps"]
    run = next(step["run"] for step in steps if "pytest --noconftest" in step.get("run", ""))
    assert "tests/test_postclose_kpi_reporting.py" in run
    assert "tests/test_monday_ci_workflows.py" in run
    assert any(step.get("uses", "").startswith("actions/setup-node@") for step in steps)


@pytest.mark.parametrize("name,job_name", WORKFLOWS + [("paper-readiness.yml", "operational-safety")])
def test_runner_paths_are_configured_only_after_job_starts(name, job_name, tmp_path):
    import re
    import sys
    workflow = _load(name)
    job = workflow["jobs"][job_name]
    # GitHub rejects these runner-time contexts in job-level env, before jobs start.
    assert not re.search(r"\b(?:runner|steps|job)\.", json.dumps(job.get("env", {})))
    step = next(step for step in job["steps"] if step.get("name") == "Configure isolated test paths")
    code = step["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    output = tmp_path / "github_env"
    env = {"RUNNER_TEMP": str(tmp_path), "GITHUB_ENV": str(output)}
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert {"ORGANISM_BRAIN_DIR", "ORGANISM_SHADOW_EXIT_TELEMETRY_PATH"} <= values.keys()
    assert all(value.startswith(str(tmp_path) + "/") for value in values.values())
    setup_index = job["steps"].index(step)
    tests_index = next(i for i, candidate in enumerate(job["steps"])
                       if "pytest" in candidate.get("run", "") or "generate_artifacts.py full" in candidate.get("run", ""))
    assert setup_index < tests_index


def test_nightly_database_driver_matches_async_tests_and_migrations_really_run():
    job = _load("nightly.yml")["jobs"]["deep-tests"]
    assert job["env"]["DATABASE_URL"].startswith("postgresql+asyncpg://")
    setup = next(step for step in job["steps"] if step.get("name") == "Set up isolated test database")
    assert setup["run"].strip() == "python -m alembic upgrade head"
    assert setup.get("continue-on-error", False) is False
    # Resolve the checked-in migration location rather than silently checking
    # a conventional directory that is absent from this repository.
    import configparser
    config = configparser.ConfigParser(defaults={"here": str(ROOT)})
    config.read(ROOT / "alembic.ini")
    migration_env = Path(config["alembic"]["script_location"]) / "env.py"
    assert migration_env.is_file()
    assert "postgresql+psycopg2://" in migration_env.read_text()


@pytest.mark.parametrize("name,job_name", WORKFLOWS)
def test_scheduled_validation_uses_same_safe_environment_as_readiness(name, job_name):
    job = _load(name)["jobs"][job_name]
    reference = _load("paper-readiness.yml")["jobs"]["operational-safety"]
    for key in ("PYTHONPATH", "SECURITY_JWT_SECRET", "PICKLE_HMAC_SECRET",
                "USE_MOCK_BROKER", "USE_MOCK_DATA", "APP_ENVIRONMENT", "TRADING_EXECUTION_MODE"):
        assert job["env"][key] == reference["env"][key]
    setup = next(step["run"] for step in job["steps"] if step.get("name") == "Configure isolated test paths")
    for key in ("ORGANISM_BRAIN_DIR", "ORGANISM_SHADOW_EXIT_TELEMETRY_PATH",
                "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH", "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_PATH"):
        assert key in setup
    assert any("pip install -r requirements.lock" in step.get("run", "") for step in job["steps"])
