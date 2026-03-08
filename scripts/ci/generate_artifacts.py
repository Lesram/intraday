#!/usr/bin/env python3
"""Generate the full artifact pack for PR and post-close runs.

Produces:
  artifacts/task_report.json
  artifacts/runtime_config_snapshot.json
  artifacts/changed_files.json
  artifacts/test_summary.json
  artifacts/replay_summary.json
  artifacts/grep_assertions.json
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
ART.mkdir(exist_ok=True)

sys.path.insert(0, str(ROOT))


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
    diff_names = sh(["git", "diff", "--name-only", "HEAD"]).splitlines()
    if not diff_names:
        diff_names = sh(["git", "diff", "--name-only", "HEAD~1"]).splitlines()
    write("task_report.json", {
        "task_id": os.environ.get("INTRA_TASK_ID", ""),
        "summary": os.environ.get("INTRA_TASK_SUMMARY", ""),
        "sha": sh(["git", "rev-parse", "HEAD"]),
        "branch": sh(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "files_changed": diff_names,
        "commands": [],
        "tests_passed": [],
        "tests_failed": [],
        "runtime_behavior_changed": [],
        "docs_updated": [],
        "risks": [],
        "follow_ups": [],
    })


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
    base = os.environ.get("GITHUB_BASE_REF", "main")
    diff_output = sh(["git", "diff", "--name-only", f"origin/{base}...HEAD"])
    if not diff_output:
        diff_output = sh(["git", "diff", "--name-only", "HEAD~1"])
    paths = [p for p in diff_output.splitlines() if p.strip()]

    backend_files = [p for p in paths if p.startswith("backend/")]
    test_files = [p for p in paths if p.startswith("tests/")]
    organism_files = [p for p in paths if p.startswith("backend/organism/")]
    config_files = [p for p in paths if p.startswith(("backend/config/", ".env", "docker-compose"))]
    docs_files = [p for p in paths if p.startswith("docs/")]

    write("changed_files.json", {
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

    # Invariant: exploration execution block must NOT exist
    check("no_exploration_submit_order",
          "_submit_entry_order.*exploration",
          "backend/organism/live_engine.py", must_exist=False)

    # Invariant: learning mode must zero ML
    check("learning_mode_zeros_ml",
          "0\\.65.*breakout_score",
          "backend/organism/live_engine.py", must_exist=True)

    # Invariant: horizon timeout exists
    check("horizon_timeout_exists",
          "_HORIZON_TIMEOUT_BARS",
          "backend/organism/adaptive_exits.py", must_exist=True)

    # Invariant: evolution freeze at 300
    check("evolution_freeze_300",
          "_EVOLUTION_FREEZE_TRADES.*=.*300",
          "backend/organism/live_engine.py", must_exist=True)

    # Invariant: bar-boundary entry gating exists
    check("bar_boundary_entry",
          "_is_entry_bar",
          "backend/organism/live_engine.py", must_exist=True)

    # Invariant: alpha_top_n is separate from max_positions
    check("alpha_top_n_separate",
          "ALPHA_TOP_N",
          "backend/organism/live_engine.py", must_exist=True)

    # Invariant: no hardcoded secret values in tracked files
    # Match actual key patterns (PK..., SK...) not the header name
    check("no_hardcoded_alpaca_secret",
          "ALPACA_API_SECRET_KEY.*=.*[A-Za-z0-9]{20}",
          "backend/", must_exist=False)

    # Invariant: EOD flatten exists
    check("eod_flatten_exists",
          "15:58\\|force.close\\|eod_flatten\\|_flatten_all",
          "backend/organism/live_engine.py", must_exist=True)

    # ── AIA PR#3 review assertions (7 explicit checks) ──────────

    # 1. Exploration execution fully removed (no route to order submission)
    check("exploration_execution_removed",
          "exploration.*_submit\\|_submit.*exploration",
          "backend/organism/live_engine.py", must_exist=False)

    # 2. Learning confidence ignores ML (uses 0.65×breakout + 0.35×tension)
    check("learning_confidence_ignores_ml",
          "0\\.65 \\* breakout_score",
          "backend/organism/live_engine.py", must_exist=True)

    # 3. Alpha scanner zeros ML weight in learning mode
    #    The guard: `if learning_mode or not ml_is_trained: effective_ml_weight = 0.0`
    check("alpha_scanner_ml_zero_in_learning",
          "learning_mode.*ml_is_trained",
          "backend/organism/alpha_scanner.py", must_exist=True)

    # 4. Kelly disabled in learning mode (fixed ATR-dollar risk only)
    check("kelly_disabled_in_learning",
          "_RISK_BUDGET_PER_TRADE_LEARNING",
          "backend/organism/kelly_sizer.py", must_exist=True)

    # 5. No warm-start apply before 300 trades (evolution freeze gate)
    check("no_warm_start_apply_before_300_trades",
          "_trade_count >= _EVOLUTION_FREEZE_TRADES",
          "backend/organism/live_engine.py", must_exist=True)

    # 6. Breakout path uses shared main gates (_is_entry_bar gate)
    check("breakout_path_uses_shared_main_gates",
          "_is_entry_bar",
          "backend/organism/live_engine.py", must_exist=True)

    # 7. ALPHA_TOP_N defined independently from MAX_OPEN_POSITIONS
    check("alpha_top_n_independent_from_max_positions",
          "ALPHA_TOP_N = _env_int",
          "backend/organism/live_engine.py", must_exist=True)

    all_passed = all(c["passed"] for c in checks)
    write("grep_assertions.json", {
        "overall": "pass" if all_passed else "fail",
        "checks": checks,
    })


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
    elif mode == "quick":
        print("  (skipping test/replay in quick mode)")

    print("Done.")
