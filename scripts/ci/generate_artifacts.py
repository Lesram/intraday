#!/usr/bin/env python3
"""Generate the full artifact pack for PR and post-close runs.

Produces:
  artifacts/task_report.json
  artifacts/runtime_defaults_snapshot.json
  artifacts/resolved_config_snapshot.json      (env > .env > code defaults)
  artifacts/live_process_runtime_snapshot.json  (from running container process)
  artifacts/runtime_config_snapshot.json        (legacy compat)
  artifacts/changed_files.json
  artifacts/test_summary.json
  artifacts/replay_summary.json
  artifacts/grep_assertions.json
  artifacts/semantic_invariants_summary.json
  artifacts/spec_drift_summary.json
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
ART.mkdir(exist_ok=True)

sys.path.insert(0, str(ROOT))

from change_scope import get_change_set  # noqa: E402

TASK_REPORT_REQUIRED_FIELDS = [
    "summary",
    "commands",
    "risks",
]
TASK_REPORT_NEED_ONE_OF = [
    ("tests_passed", "tests_failed"),
]

# Keep the complete CPU-bound replay within the workflows' 50-minute pack.
# Hosted replay passed at 456s, then reached 22/28 cases before a 600s process
# cutoff; retain all case deadlines and collect uncensored case timing.
TEST_SUITE_TIMEOUT_SECONDS = 180
REPLAY_TIMEOUT_SECONDS = 1200
RUNTIME_SNAPSHOT_FILES = (
    "runtime_defaults_snapshot.json",
    "resolved_config_snapshot.json",
    "live_process_runtime_snapshot.json",
    "runtime_config_snapshot.json",
)


@dataclass
class CommandResult:
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    timed_out: bool = False

    @property
    def output(self) -> str:
        return self.stdout + ("\n" if self.stdout and self.stderr else "") + self.stderr


def run_command(cmd: list[str], *, timeout: float) -> CommandResult:
    """Retain process failures and bound the entire child process group."""
    try:
        process = subprocess.Popen(
            cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors="replace", start_new_session=(os.name == "posix"),
        )
    except OSError as exc:
        return CommandResult(None, error=str(exc))
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return CommandResult(process.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        stdout, stderr = process.communicate()
        return CommandResult(
            process.returncode, stdout, stderr,
            error=f"command timed out after {timeout}s", timed_out=True,
        )


def command_evidence(name: str, result: CommandResult) -> dict:
    """Keep complete output alongside a bounded, backwards-compatible JSON tail."""
    output_path = ART / f"{name}.log"
    output_path.write_text(result.output + (f"\n{result.error}\n" if result.error else ""))
    return {
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "error": result.error,
        "output_file": str(output_path.relative_to(ROOT)),
        "output_tail": result.output[-800:],
    }


def run_pytest(
    name: str, path: str, *, timeout: float, test_timeout: int = 30,
    verbose: bool = False,
) -> dict:
    """Require fresh JUnit results, actual executed tests, and a successful process."""
    junit_path = ART / f"{name}.junit.xml"
    junit_path.unlink(missing_ok=True)
    test_path = ROOT / path
    if not test_path.is_file():
        result = CommandResult(None, error=f"required test file not found: {path}")
    else:
        progress_flags = ["-vv", "--durations=0"] if verbose else ["-q"]
        result = run_command([
            sys.executable, "-m", "pytest", *progress_flags, f"--timeout={test_timeout}",
            "--tb=line", f"--junitxml={junit_path}", str(test_path),
        ], timeout=timeout)

    data = {
        "status": "fail", "passed": 0, "failed": 0, "errors": 0, "skipped": 0,
        "total": 0, "tests": [], **command_evidence(name, result),
        "junit_file": str(junit_path.relative_to(ROOT)),
    }
    try:
        report = ET.parse(junit_path).getroot()
        if report.tag not in {"testsuites", "testsuite"}:
            raise ValueError(f"unexpected JUnit root: {report.tag}")
        for case in report.iter("testcase"):
            status = (
                "error" if case.find("error") is not None else
                "failed" if case.find("failure") is not None else
                "skipped" if case.find("skipped") is not None else "passed"
            )
            data["errors" if status == "error" else status] += 1
            data["tests"].append({"name": case.get("name", ""), "status": status})
        data["total"] = sum(data[key] for key in ("passed", "failed", "errors", "skipped"))
        if data["total"] == 0 or data["passed"] + data["failed"] + data["errors"] == 0:
            raise ValueError("no tests executed (empty or all skipped)")
        if result.exit_code == 0 and not result.error and not data["failed"] and not data["errors"]:
            data["status"] = "pass"
    except (OSError, ET.ParseError, ValueError) as exc:
        data["error"] = "; ".join(filter(None, (data["error"], f"invalid pytest evidence: {exc}")))
    if result.exit_code not in (None, 0) and not data["error"]:
        data["error"] = f"pytest exited with code {result.exit_code}"
    return data


def sh(cmd: list[str], cwd: str | None = None) -> str:
    try:
        return subprocess.check_output(cmd, text=True, cwd=cwd or str(ROOT), stderr=subprocess.STDOUT, timeout=30).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def write(name: str, data: dict | list) -> Path:
    p = ART / name
    p.write_text(json.dumps(data, indent=2))
    print(f"  -> {p}")
    return p


# ── 1. task_report.json ──────────────────────────────────────────────
def gen_task_report() -> None:
    change_set = get_change_set(root=ROOT)
    diff_names = [f for f in change_set.paths if f.strip()]

    sha = sh(["git", "rev-parse", "HEAD"])
    branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])

    # Auto-derive summary from latest commit message if env var not set
    summary = os.environ.get("INTRA_TASK_SUMMARY", "")
    if not summary:
        summary = sh(["git", "log", "-1", "--format=%s"])
    if not summary:
        summary = "Evidence pack generation and validation"

    # Classify changed files for risk assessment
    backend_files = [f for f in diff_names if f.startswith("backend/")]
    backend_runtime_files = [
        f for f in backend_files
        if not f.startswith(("backend/migrations/", "backend/config/"))
    ]
    organism_files = [f for f in diff_names if f.startswith("backend/organism/")]
    config_files = [f for f in diff_names if f.startswith(("backend/config/", ".env", "docker-compose"))]
    test_files = [f for f in diff_names if f.startswith("tests/")]
    docs_files = [f for f in diff_names if f.startswith("docs/")]

    # Auto-derive risks
    risks = []
    if organism_files:
        risks.append(f"{len(organism_files)} organism file(s) changed — replay verification required")
    elif backend_runtime_files:
        risks.append(f"{len(backend_runtime_files)} backend runtime file(s) changed — targeted verification required")
    if config_files:
        risks.append(f"{len(config_files)} config file(s) changed — runtime drift check required")
    if not test_files and organism_files:
        risks.append("Organism changed without test changes — verify coverage")
    elif not test_files and backend_runtime_files:
        risks.append("Backend runtime changed without test changes — verify coverage")
    if not risks:
        risks.append("Evidence/tooling changes only — low risk, verify artifact completeness")

    # Auto-derive commands
    commands = [
        "python scripts/runtime/write_runtime_snapshot.py",
        "python scripts/ci/generate_artifacts.py full",
        "python -m pytest tests/test_semantic_invariants.py -v --timeout=30",
        "python scripts/ci/check_spec_drift.py --json",
    ]

    # Auto-derive docs_updated
    docs_updated = docs_files if docs_files else []

    # Runtime behavior changed if backend runtime files touched
    runtime_behavior_changed = backend_runtime_files if backend_runtime_files else []

    write("task_report.json", {
        "task_id": os.environ.get("INTRA_TASK_ID", "evidence-repair"),
        "summary": summary,
        "sha": sha,
        "branch": branch,
        "change_scope": change_set.scope,
        "change_ref": change_set.ref,
        "files_changed": diff_names,
        "commands": commands,
        "tests_passed": [],  # filled after test runs
        "tests_failed": [],  # filled after test runs
        "runtime_behavior_changed": runtime_behavior_changed,
        "docs_updated": docs_updated,
        "risks": risks,
        "follow_ups": [],
    })


def validate_task_report() -> list[str]:
    """Validate task_report.json has required non-empty fields. Returns errors.

    FATAL: any error here blocks artifact generation.
    """
    p = ART / "task_report.json"
    if not p.exists():
        return ["task_report.json does not exist"]
    data = json.loads(p.read_text())
    errors = []
    for field in TASK_REPORT_REQUIRED_FIELDS:
        val = data.get(field)
        if not val:
            errors.append(f"task_report.json: '{field}' is empty or missing")
    for group in TASK_REPORT_NEED_ONE_OF:
        if not any(data.get(f) for f in group):
            errors.append(
                f"task_report.json: at least one of {group} must be non-empty"
            )
    # SHA mismatch check — report SHA must match current HEAD
    report_sha = data.get("sha", "")
    head_sha = sh(["git", "rev-parse", "HEAD"])
    if report_sha and head_sha and report_sha != head_sha:
        errors.append(
            f"task_report.json: SHA mismatch — report={report_sha[:10]} vs HEAD={head_sha[:10]}"
        )
    return errors


# ── 2. runtime_config_snapshot.json ───────────────────────────────────
def gen_runtime_snapshot() -> None:
    # Prefer venv python for organism module imports (requires Python 3.12+)
    venv_python = ROOT / "venv" / "bin" / "python3"
    python = str(venv_python) if venv_python.exists() else sys.executable
    for name in RUNTIME_SNAPSHOT_FILES:
        (ART / name).unlink(missing_ok=True)
    result = run_command(
        [python, str(ROOT / "scripts" / "runtime" / "write_runtime_snapshot.py")],
        timeout=60,
    )
    errors = []
    if result.exit_code != 0 or result.error:
        errors.append(result.error or f"snapshot script exited with code {result.exit_code}")
    for name in RUNTIME_SNAPSHOT_FILES:
        try:
            data = json.loads((ART / name).read_text())
            if not isinstance(data, dict) or not data:
                raise ValueError("empty or invalid snapshot")
            if data.get("error"):
                errors.append(f"{name}: {data['error']}")
        except (OSError, ValueError) as exc:
            errors.append(f"{name}: {exc}")
            write(name, {"error": f"snapshot generation failed: {exc}"})
    if result.exit_code != 0 or result.error:
        # Existing KPI consumers inspect the legacy error key. Keep that
        # failure signal even if the command wrote all snapshots before dying.
        legacy_path = ART / "runtime_config_snapshot.json"
        legacy = json.loads(legacy_path.read_text())
        legacy["error"] = "; ".join(filter(None, (legacy.get("error"), errors[0])))
        write(legacy_path.name, legacy)
    write("runtime_snapshot_summary.json", {
        "overall": "fail" if errors else "pass",
        **command_evidence("runtime_snapshot", result),
        "errors": errors,
    })


# ── 3. changed_files.json ────────────────────────────────────────────
def gen_changed_files() -> None:
    change_set = get_change_set(root=ROOT)
    paths = [p for p in change_set.paths if p.strip()]

    backend_files = [p for p in paths if p.startswith("backend/")]
    test_files = [p for p in paths if p.startswith("tests/")]
    organism_files = [p for p in paths if p.startswith("backend/organism/")]
    config_files = [p for p in paths if p.startswith(("backend/config/", ".env", "docker-compose"))]
    docs_files = [p for p in paths if p.startswith("docs/")]

    write("changed_files.json", {
        "scope": change_set.scope,
        "ref": change_set.ref,
        "total": len(paths),
        "all": paths,
        "backend": backend_files,
        "organism": organism_files,
        "tests": test_files,
        "config": config_files,
        "docs": docs_files,
    })


# ── 4. test_summary.json ─────────────────────────────────────────────
def gen_test_summary() -> None:
    suites = [
        ("organism_live_engine", "tests/test_organism_live_engine.py"),
        ("organism_engine_scenarios", "tests/test_organism_engine_scenarios.py"),
        ("multi_tick_state", "tests/test_multi_tick_state.py"),
        ("safety_invariants", "tests/test_safety_invariants.py"),
        ("self_evolution", "tests/test_self_evolution.py"),
        ("algorithm_improvements", "tests/test_algorithm_improvements.py"),
    ]
    results = {}
    for name, path in suites:
        results[name] = run_pytest(name, path, timeout=TEST_SUITE_TIMEOUT_SECONDS)

    all_pass = all(r.get("status") == "pass" for r in results.values())
    write("test_summary.json", {
        "overall": "pass" if all_pass else "fail",
        "suites": results,
    })


# ── 5. replay_summary.json ───────────────────────────────────────────
def gen_replay_summary() -> None:
    write("replay_summary.json", run_pytest(
        "replay_simulator", "tests/test_replay_simulator.py",
        timeout=REPLAY_TIMEOUT_SECONDS, test_timeout=120, verbose=True,
    ))


# ── 6. grep_assertions.json ──────────────────────────────────────────
def gen_grep_assertions() -> None:
    """Verify trading invariants via grep — hard-coded assertions."""
    checks = []

    def check(name: str, pattern: str, path: str, must_exist: bool = True) -> None:
        result = run_command(["grep", "-rn", pattern, str(ROOT / path)], timeout=10)
        found = result.exit_code == 0
        # grep exit 1 means no matches; execution/path errors must never make
        # a negative assertion pass.
        passed = result.exit_code in (0, 1) and not result.error and found == must_exist
        checks.append({
            "name": name,
            "pattern": pattern,
            "path": path,
            "must_exist": must_exist,
            "found": found,
            "passed": passed,
            "exit_code": result.exit_code,
            "error": result.error or result.stderr.strip(),
        })

    # ── Original 8 invariants ──────────────────────────────────────

    check("no_exploration_submit_order",
          "_submit_entry_order.*exploration",
          "backend/organism/live_engine.py", must_exist=False)

    check("learning_mode_zeros_ml",
          "0\\.65.*breakout_score",
          "backend/organism/live_engine.py", must_exist=True)

    check("horizon_timeout_exists",
          "_HORIZON_TIMEOUT_BARS",
          "backend/organism/adaptive_exits.py", must_exist=True)

    check("evolution_freeze_300",
          "_EVOLUTION_FREEZE_TRADES.*=.*300",
          "backend/organism/live_engine.py", must_exist=True)

    check("bar_boundary_entry",
          "_is_entry_bar",
          "backend/organism/live_engine.py", must_exist=True)

    check("alpha_top_n_separate",
          "ALPHA_TOP_N",
          "backend/organism/live_engine.py", must_exist=True)

    check("no_hardcoded_alpaca_secret",
          "ALPACA_API_SECRET_KEY.*=.*[A-Za-z0-9]{20}",
          "backend/", must_exist=False)

    check("eod_flatten_exists",
          "15:58\\|force.close\\|eod_flatten\\|_flatten_all",
          "backend/organism/live_engine.py", must_exist=True)

    # ── AIA PR#3 review assertions (7 explicit checks) ──────────

    check("exploration_execution_removed",
          "exploration.*_submit\\|_submit.*exploration",
          "backend/organism/live_engine.py", must_exist=False)

    check("learning_confidence_ignores_ml",
          "0\\.65 \\* breakout_score",
          "backend/organism/live_engine.py", must_exist=True)

    check("alpha_scanner_ml_zero_in_learning",
          "learning_mode.*ml_is_trained",
          "backend/organism/alpha_scanner.py", must_exist=True)

    check("kelly_disabled_in_learning",
          "_RISK_BUDGET_PER_TRADE_LEARNING",
          "backend/organism/kelly_sizer.py", must_exist=True)

    check("no_warm_start_apply_before_300_trades",
          "_trade_count >= _EVOLUTION_FREEZE_TRADES",
          "backend/organism/live_engine.py", must_exist=True)

    check("breakout_path_uses_shared_main_gates",
          "_is_entry_bar",
          "backend/organism/live_engine.py", must_exist=True)

    check("alpha_top_n_independent_from_max_positions",
          "ALPHA_TOP_N = _env_int",
          "backend/organism/live_engine.py", must_exist=True)

    all_passed = all(c["passed"] for c in checks)
    write("grep_assertions.json", {
        "overall": "pass" if all_passed else "fail",
        "checks": checks,
    })


# ── 7. semantic_invariants_summary.json ──────────────────────────────
def gen_semantic_invariants_summary() -> None:
    """Run semantic invariant tests and export structured JSON summary."""
    data = run_pytest(
        "semantic_invariants", "tests/test_semantic_invariants.py",
        timeout=TEST_SUITE_TIMEOUT_SECONDS,
    )
    write("semantic_invariants_summary.json", {**data, "overall": data["status"]})


# ── 8. spec_drift_summary.json ──────────────────────────────────────
def gen_spec_drift_summary() -> None:
    """Run the 3-way drift check and export structured JSON summary."""
    drift_script = ROOT / "scripts" / "ci" / "check_spec_drift.py"
    result = run_command(
        [sys.executable, str(drift_script), "--json"],
        timeout=30,
    )
    try:
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or data.get("overall") not in ("pass", "fail"):
            raise ValueError("missing spec drift verdict")
    except (json.JSONDecodeError, ValueError):
        data = {"overall": "fail"}
        result.error = result.error or "spec drift script did not produce a valid JSON verdict"
    if result.exit_code != 0 or result.error:
        data["overall"] = "fail"
    write("spec_drift_summary.json", {**data, **command_evidence("spec_drift", result)})


def _backfill_task_report_tests(*, include_full: bool = True) -> None:
    """Backfill tests_passed / tests_failed from test_summary.json into task_report."""
    tr_path = ART / "task_report.json"
    ts_path = ART / "test_summary.json"
    if not tr_path.exists() or not ts_path.exists():
        return
    tr = json.loads(tr_path.read_text())
    ts = json.loads(ts_path.read_text())

    passed = []
    failed = []
    for name, info in ts.get("suites", {}).items():
        status = info.get("status", "")
        if status == "pass":
            passed.append(name)
        else:
            failed.append(name)
    if not ts.get("suites"):
        failed.append("required_test_suites")

    # Also include semantic invariants
    si_path = ART / "semantic_invariants_summary.json"
    if include_full and si_path.exists():
        si = json.loads(si_path.read_text())
        if si.get("overall") == "pass":
            passed.append("semantic_invariants")
        else:
            failed.append("semantic_invariants")

    # Also include replay
    rp_path = ART / "replay_summary.json"
    if include_full and rp_path.exists():
        rp = json.loads(rp_path.read_text())
        if rp.get("status") == "pass":
            passed.append("replay_simulator")
        else:
            failed.append("replay_simulator")

    if passed or failed:
        tr["tests_passed"] = passed
        tr["tests_failed"] = failed
        tr_path.write_text(json.dumps(tr, indent=2))
        print(f"  -> backfilled task_report: {len(passed)} passed, {len(failed)} failed")


def gen_quick_test_summary(*, success: bool = True) -> None:
    """Record that quick mode intentionally skips expensive test suites.

    Clean CI runners still validate the task-report schema. Without an
    explicit quick-mode evidence row, ``task_report.json`` has no test result
    fields and the artifact pack fails after doing the useful snapshot work.
    """
    write("test_summary.json", {
        "overall": "pass" if success else "fail",
        "mode": "quick",
        "suites": {
            "quick_artifact_pack": {
                "status": "pass" if success else "fail",
                "passed": 1 if success else 0,
                "failed": 0 if success else 1,
                "reason": (
                    "quick mode generated snapshots and grep assertions; full suites intentionally skipped"
                    if success else
                    "quick snapshot or grep checks failed; full suites intentionally skipped"
                ),
            }
        },
    })
    for name in ("replay_summary.json", "semantic_invariants_summary.json", "spec_drift_summary.json"):
        write(name, {
            "status": "skipped", "overall": "skipped", "mode": "quick",
            "reason": "intentionally not run in quick mode",
        })


# ── main ──────────────────────────────────────────────────────────────
def main(mode: str = "full") -> int:
    if mode not in ("full", "quick"):
        print(f"ERROR: unknown artifact mode: {mode}")
        return 2
    print(f"Generating artifacts (mode={mode})...")

    gen_task_report()
    gen_changed_files()
    stages = [
        ("runtime_snapshot_summary.json", gen_runtime_snapshot),
        ("grep_assertions.json", gen_grep_assertions),
    ]
    if mode == "full":
        stages.extend([
            ("test_summary.json", gen_test_summary),
            ("replay_summary.json", gen_replay_summary),
            ("semantic_invariants_summary.json", gen_semantic_invariants_summary),
            ("spec_drift_summary.json", gen_spec_drift_summary),
        ])
    else:
        print("  (skipping test/replay/semantic/drift in quick mode)")

    # Finish the remaining evidence even when an earlier required stage fails.
    errors = []
    for filename, generate in stages:
        (ART / filename).unlink(missing_ok=True)
        try:
            generate()
            data = json.loads((ART / filename).read_text())
            if data.get("overall", data.get("status")) != "pass":
                errors.append(f"{filename}: required check failed")
        except Exception as exc:  # noqa: BLE001 -- retain unexpected stage failures and finish the pack
            write(filename, {"overall": "fail", "status": "fail", "error": str(exc)})
            errors.append(f"{filename}: {exc}")

    if mode == "quick":
        gen_quick_test_summary(success=not errors)

    # Backfill test results into task_report
    _backfill_task_report_tests(include_full=mode == "full")

    errors.extend(validate_task_report())
    report_path = ART / "task_report.json"
    report = json.loads(report_path.read_text())
    report["artifact_pack_status"] = "fail" if errors else "pass"
    report["artifact_pack_errors"] = errors
    report_path.write_text(json.dumps(report, indent=2))
    if errors:
        print(f"\nERROR: artifact pack FAILED ({len(errors)} issues):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "full"))
