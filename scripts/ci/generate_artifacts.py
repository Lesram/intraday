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
import subprocess
import sys
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


def sh(cmd: list[str], cwd: str | None = None) -> str:
    try:
        return subprocess.check_output(cmd, text=True, cwd=cwd or str(ROOT), stderr=subprocess.STDOUT).strip()
    except Exception:
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
    script_files = [f for f in diff_names if f.startswith("scripts/")]

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
    result = subprocess.run(
        [python, str(ROOT / "scripts" / "runtime" / "write_runtime_snapshot.py")],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    if result.returncode != 0:
        write("runtime_config_snapshot.json", {
            "error": result.stderr.strip() or "snapshot script failed",
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
        test_path = ROOT / path
        if not test_path.exists():
            results[name] = {"status": "skipped", "reason": "file not found"}
            continue
        out = sh([sys.executable, "-m", "pytest", "-q", "--timeout=30", "--tb=line", str(test_path)])
        if "passed" in out:
            passed = int(out.split(" passed")[0].split()[-1]) if "passed" in out else 0
            failed = int(out.split(" failed")[0].split()[-1]) if "failed" in out else 0
            results[name] = {"status": "pass" if failed == 0 else "fail", "passed": passed, "failed": failed}
        else:
            results[name] = {"status": "error", "output": out[-500:]}

    all_pass = all(r.get("status") == "pass" for r in results.values())
    write("test_summary.json", {
        "overall": "pass" if all_pass else "fail",
        "suites": results,
    })


# ── 5. replay_summary.json ───────────────────────────────────────────
def gen_replay_summary() -> None:
    replay_path = ROOT / "tests" / "test_replay_simulator.py"
    if not replay_path.exists():
        write("replay_summary.json", {"status": "skipped", "reason": "file not found"})
        return
    out = sh([sys.executable, "-m", "pytest", "-q", "--timeout=120", "--tb=line", str(replay_path)])
    passed = int(out.split(" passed")[0].split()[-1]) if "passed" in out else 0
    failed = int(out.split(" failed")[0].split()[-1]) if "failed" in out else 0
    write("replay_summary.json", {
        "status": "pass" if failed == 0 else "fail",
        "passed": passed,
        "failed": failed,
        "output_tail": out[-500:],
    })


# ── 6. grep_assertions.json ──────────────────────────────────────────
def gen_grep_assertions() -> None:
    """Verify trading invariants via grep — hard-coded assertions."""
    checks = []

    def check(name: str, pattern: str, path: str, must_exist: bool = True) -> None:
        try:
            out = subprocess.run(
                ["grep", "-rn", pattern, str(ROOT / path)],
                capture_output=True, text=True,
            )
            found = out.returncode == 0
        except Exception:
            found = False
        passed = found == must_exist
        checks.append({
            "name": name,
            "pattern": pattern,
            "path": path,
            "must_exist": must_exist,
            "found": found,
            "passed": passed,
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
    test_path = ROOT / "tests" / "test_semantic_invariants.py"
    if not test_path.exists():
        write("semantic_invariants_summary.json", {
            "status": "skipped", "reason": "test file not found",
        })
        return

    out = sh([
        sys.executable, "-m", "pytest", str(test_path),
        "-v", "--timeout=30", "--tb=short",
    ])

    # Parse pytest verbose output
    tests = []
    passed = 0
    failed = 0
    for line in out.splitlines():
        if " PASSED" in line:
            test_name = line.split(" PASSED")[0].strip().split("::")[-1]
            tests.append({"name": test_name, "status": "passed"})
            passed += 1
        elif " FAILED" in line:
            test_name = line.split(" FAILED")[0].strip().split("::")[-1]
            tests.append({"name": test_name, "status": "failed"})
            failed += 1

    write("semantic_invariants_summary.json", {
        "overall": "pass" if failed == 0 and passed > 0 else "fail",
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "tests": tests,
        "output_tail": out[-800:] if failed > 0 else "",
    })


# ── 8. spec_drift_summary.json ──────────────────────────────────────
def gen_spec_drift_summary() -> None:
    """Run the 3-way drift check and export structured JSON summary."""
    drift_script = ROOT / "scripts" / "ci" / "check_spec_drift.py"
    if not drift_script.exists():
        write("spec_drift_summary.json", {
            "status": "skipped", "reason": "check_spec_drift.py not found",
        })
        return

    result = subprocess.run(
        [sys.executable, str(drift_script), "--json"],
        cwd=str(ROOT), capture_output=True, text=True,
    )

    # Try to parse JSON output from --json mode
    try:
        data = json.loads(result.stdout)
        write("spec_drift_summary.json", data)
        return
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: parse text output
    drifted = result.returncode != 0
    write("spec_drift_summary.json", {
        "overall": "fail" if drifted else "pass",
        "exit_code": result.returncode,
        "output": result.stdout.strip()[-800:],
    })


def _backfill_task_report_tests() -> None:
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
        elif status in ("fail", "error"):
            failed.append(name)

    # Also include semantic invariants
    si_path = ART / "semantic_invariants_summary.json"
    if si_path.exists():
        si = json.loads(si_path.read_text())
        if si.get("overall") == "pass":
            passed.append("semantic_invariants")
        elif si.get("overall") == "fail":
            failed.append("semantic_invariants")

    # Also include replay
    rp_path = ART / "replay_summary.json"
    if rp_path.exists():
        rp = json.loads(rp_path.read_text())
        if rp.get("status") == "pass":
            passed.append("replay_simulator")
        elif rp.get("status") == "fail":
            failed.append("replay_simulator")

    if passed or failed:
        tr["tests_passed"] = passed
        tr["tests_failed"] = failed
        tr_path.write_text(json.dumps(tr, indent=2))
        print(f"  -> backfilled task_report: {len(passed)} passed, {len(failed)} failed")


# ── main ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    print(f"Generating artifacts (mode={mode})...")

    gen_task_report()
    gen_runtime_snapshot()
    gen_changed_files()
    gen_grep_assertions()

    if mode == "full":
        gen_test_summary()
        gen_replay_summary()
        gen_semantic_invariants_summary()
        gen_spec_drift_summary()
    elif mode == "quick":
        print("  (skipping test/replay/semantic/drift in quick mode)")

    # Backfill test results into task_report
    _backfill_task_report_tests()

    # Validate task_report completeness — FATAL on errors
    errors = validate_task_report()
    if errors:
        print(f"\nERROR: task_report.json validation FAILED ({len(errors)} issues):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("Done.")
