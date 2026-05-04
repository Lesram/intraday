"""V12 W75 (UU3-2): lint ratchet — fail CI on NEW violations only.

Pre-V12 the codebase carried ~34k lint violations and CI's strict
``ruff check --no-fix`` could never pass.  V11 wave-57 shipped a
narrower rule set but the audit cycle kept producing new
violations because there was no per-PR gate — the rule was wired
but unenforced (V8 OO "wired but unreachable" pattern).

This script implements the ratchet pattern recommended by the
external V11 auditor: capture the current violation set as a
baseline, then refuse new violations that aren't in it.

Behavior:

- ``python scripts/ci/lint_ratchet.py``
    Runs ruff, compares against ``artifacts/audit/v12/lint_baseline.json``,
    exits 0 if no NEW violations, exits 1 with a diff report otherwise.
    Baseline shrinkage (violations fixed) is reported but never fails.

- ``python scripts/ci/lint_ratchet.py --update-baseline``
    Re-captures the current state.  Use after intentional refactors.

- ``python scripts/ci/lint_ratchet.py --shrink-baseline``
    Updates the baseline ONLY to remove fixed violations.  Refuses
    to record new violations.  Recommended for incremental cleanup
    PRs that should ratchet the baseline tighter.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "artifacts" / "audit" / "v12" / "lint_baseline.json"


def _normalize_path(p: str) -> str:
    """Strip the absolute repo prefix so baselines are portable."""
    prefix = str(REPO_ROOT)
    if p.startswith(prefix):
        return p[len(prefix):].lstrip("/")
    return p


def _violation_key(v: dict) -> tuple[str, str]:
    """Stable identity for a violation: (path, rule).  Line numbers
    drift on refactors — the baseline tolerates intra-file movement
    but flags the introduction of a NEW (path, rule) pair."""
    return (_normalize_path(v["filename"]), v["code"])


def run_ruff() -> list[dict]:
    """Run ruff and return the parsed JSON violation list."""
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", ".",
         "--no-fix", "--output-format=json"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    # Ruff exits 1 when violations found; both 0 and 1 are normal here.
    if proc.returncode not in (0, 1):
        print(f"Ruff command failed (exit {proc.returncode}):", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        sys.exit(2)
    if not proc.stdout.strip():
        return []
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        print(f"Failed to parse ruff JSON output: {e}", file=sys.stderr)
        sys.exit(2)


def load_baseline() -> dict:
    if not BASELINE.is_file():
        return {"counts_by_key": {}, "total": 0, "captured_at": None}
    return json.loads(BASELINE.read_text())


def write_baseline(violations: list[dict], reason: str) -> None:
    import datetime
    counts: dict[str, int] = {}
    for v in violations:
        key = "::".join(_violation_key(v))
        counts[key] = counts.get(key, 0) + 1
    payload = {
        "counts_by_key": counts,
        "total": sum(counts.values()),
        "captured_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "reason": reason,
    }
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote baseline with {payload['total']} total violations across "
          f"{len(counts)} (path, rule) pairs.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-baseline", action="store_true",
                        help="Re-capture full baseline from current state.")
    parser.add_argument("--shrink-baseline", action="store_true",
                        help="Update baseline ONLY to remove fixed violations.")
    args = parser.parse_args()

    current = run_ruff()
    current_counts: dict[str, int] = {}
    for v in current:
        key = "::".join(_violation_key(v))
        current_counts[key] = current_counts.get(key, 0) + 1

    if args.update_baseline:
        write_baseline(current, reason="--update-baseline manual refresh")
        return 0

    baseline = load_baseline()
    base_counts: dict[str, int] = baseline.get("counts_by_key", {})

    new_violations: dict[str, int] = {}     # exceeds baseline
    fixed_violations: dict[str, int] = {}    # below baseline

    keys = set(current_counts) | set(base_counts)
    for k in keys:
        cur = current_counts.get(k, 0)
        base = base_counts.get(k, 0)
        if cur > base:
            new_violations[k] = cur - base
        elif cur < base:
            fixed_violations[k] = base - cur

    print(f"Lint ratchet — current={sum(current_counts.values())}, "
          f"baseline={sum(base_counts.values())}")
    if fixed_violations:
        total_fixed = sum(fixed_violations.values())
        print(f"\nFixed: {total_fixed} violation(s) cleared since baseline.")
        for k, n in sorted(fixed_violations.items(),
                           key=lambda kv: -kv[1])[:10]:
            print(f"  -{n:5d}  {k}")
    if new_violations:
        total_new = sum(new_violations.values())
        print(f"\nNEW VIOLATIONS ({total_new}):")
        for k, n in sorted(new_violations.items(),
                           key=lambda kv: -kv[1])[:30]:
            print(f"  +{n:5d}  {k}")
        print()
        print(
            "V12 W75 ratchet FAIL: new violations not in baseline.  "
            "Either fix them, or — if intentional — re-run with "
            "``--update-baseline`` to record the new ceiling.  Note: "
            "the audit_gate job runs alongside this; do not raise the "
            "ceiling silently.")
        return 1

    if args.shrink_baseline and fixed_violations:
        write_baseline(current, reason="--shrink-baseline incremental cleanup")
        return 0

    print("\nLint ratchet PASS: no new violations vs baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
