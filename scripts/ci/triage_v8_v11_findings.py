"""V13 W99 (Lens 6 + Lens 1): triage the 103 still-open V8-V11 findings.

Per V13 plan: every still-open finding parsed from V8-V11 synthesis
docs must be classified before V13 closes.  Realistic outcome
estimate (per plan): ~70% closed-in-unrecorded-wave, ~20%
absorbed-into-V13-lens, ~10% deprecated.

Triage method (automated, evidence-based):

1. **closed_in_unrecorded_wave**: the finding ID appears in either
   (a) any commit message reachable from HEAD, or
   (b) a test file's source.  These are tracked-but-untagged closures.

2. **absorbed_into_v13_lens**: the finding's summary keywords match
   a V13 W92-W98 lens deliverable.  Heuristic: keyword match on
   "drawdown", "halt", "ATR", etc.  → Lens 2; "expectancy",
   "win_rate" → Lens 3; "GDPR", "outbox", "audit_log" → Lens 4;
   etc.

3. **still_open**: anything else.  Listed in stdout for human follow-up.

Output:
- Pretty stdout summary (counts per status, top N still-opens).
- JSON file at artifacts/audit/v13/v13_finding_triage.json with the
  full classification + evidence for each finding.

Usage:
    python scripts/ci/triage_v8_v11_findings.py
    python scripts/ci/triage_v8_v11_findings.py --apply  # update ledger
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER = REPO_ROOT / "artifacts" / "audit" / "findings_ledger.json"
TRIAGE = REPO_ROOT / "artifacts" / "audit" / "v13" / "v13_finding_triage.json"


_LENS_KEYWORDS = {
    "v13_w92_lens1_deploy": (
        "deploy", "container", "image", "build", "compose", "rebuild",
        "wave-47", "JWT", "jwt regression", "live image", "stale",
    ),
    "v13_w93_lens2_safety": (
        "drawdown", "halt", "max-loss", "max daily", "atr", "stop_loss",
        "max_loss", "exit", "broker timeout", "watchdog", "throttle",
        "safety", "circuit",
    ),
    "v13_w94_lens3_expectancy": (
        "expectancy", "pnl", "win_rate", "win-rate", "sharpe",
        "drawdown_max", "realized pnl", "profitable",
    ),
    "v13_w95_lens4_data": (
        "outbox", "audit_log", "audit-log", "audit log", "GDPR", "gdpr",
        "schema", "migration", "alembic", "duplicate index",
        "realized_trades", "brain_save", "brain-save", "brain backup",
        "brain.load", "session", "rollback", "atomic",
    ),
    "v13_w96_lens5_auth": (
        "IDOR", "idor", "RBAC", "rbac", "JWT", "auth", "auth bypass",
        "cross-user", "cross user", "permission", "role",
        "blacklist", "logout", "X-API-Key",
    ),
    "v13_w97_lens6_test_ci": (
        "marker-only", "marker test", "wave test", "ci-grep",
        "ci grep", "lint", "ratchet", "spec drift",
    ),
    "v13_w98_lens7_frontend": (
        "frontend", "npm", "vite", "tsc", "react", "Protected",
        "VITE_DEV_BYPASS_AUTH", "websocket", "ws auth",
    ),
}


def _commit_messages_blob() -> str:
    """All commit messages reachable from HEAD as a single string."""
    proc = subprocess.run(
        ["git", "log", "--all", "--format=%H %s%n%b"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60,
    )
    return proc.stdout if proc.returncode == 0 else ""


def _tests_dir_blob() -> str:
    """Concatenate all tests/*.py file contents as a string."""
    out: list[str] = []
    for f in sorted((REPO_ROOT / "tests").rglob("*.py")):
        try:
            out.append(f.read_text())
        except OSError:
            continue
    return "\n".join(out)


def _classify(
    finding: dict,
    commit_blob: str,
    tests_blob: str,
) -> dict:
    """Return the classification for one finding."""
    fid = finding["id"]
    summary = finding.get("summary", "") or ""

    # 1. ID-grep evidence in commit messages or tests.
    id_pat = re.compile(rf"\b{re.escape(fid)}\b")
    in_commit = bool(id_pat.search(commit_blob))
    in_tests = bool(id_pat.search(tests_blob))

    if in_commit or in_tests:
        return {
            "id": fid,
            "v13_status": "closed_in_unrecorded_wave",
            "evidence": {
                "id_in_commit_messages": in_commit,
                "id_in_test_files": in_tests,
            },
            "v13_lens": None,
        }

    # 2. Summary keyword → V13 lens absorption.
    summary_lower = summary.lower()
    for lens, kws in _LENS_KEYWORDS.items():
        if any(kw.lower() in summary_lower for kw in kws):
            return {
                "id": fid,
                "v13_status": "absorbed_into_v13_lens",
                "evidence": {"matched_lens": lens, "summary": summary[:120]},
                "v13_lens": lens,
            }

    # 3. Unmatched — genuinely still open.
    return {
        "id": fid,
        "v13_status": "still_open",
        "evidence": {"summary": summary[:120]},
        "v13_lens": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true",
        help="Update findings_ledger.json with the triage classifications.",
    )
    args = parser.parse_args()

    ledger = json.loads(LEDGER.read_text())
    findings = ledger.get("findings", [])
    open_findings = [f for f in findings if f.get("status") == "open"]

    print(f"V13 W99 triage — {len(open_findings)} open finding(s)")
    print("=" * 60)

    commit_blob = _commit_messages_blob()
    tests_blob = _tests_dir_blob()

    triaged: list[dict] = []
    by_status: dict[str, int] = {}
    for f in open_findings:
        c = _classify(f, commit_blob, tests_blob)
        c["severity"] = f.get("severity_at_first_appearance")
        c["summary"] = f.get("summary", "")[:140]
        c["first_version"] = f.get("first_appearance_version")
        triaged.append(c)
        by_status[c["v13_status"]] = by_status.get(c["v13_status"], 0) + 1

    print("Status breakdown:")
    for status, count in sorted(by_status.items()):
        pct = 100.0 * count / len(open_findings)
        print(f"  {status:35s} {count:4d}  ({pct:.1f}%)")
    print()

    still_open = [t for t in triaged if t["v13_status"] == "still_open"]
    if still_open:
        print("  Top still-open by severity:")
        for s in sorted(
            still_open,
            key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(
                x.get("severity", "low"), 4
            ),
        )[:15]:
            print(
                f"    [{s.get('severity','?'):8s}] {s['id']:12s} {s['summary'][:80]}"
            )

    # Write the triage artifact.
    TRIAGE.parent.mkdir(parents=True, exist_ok=True)
    TRIAGE.write_text(json.dumps({
        "triage_at_branch_head": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        ).stdout.strip(),
        "n_open_findings": len(open_findings),
        "by_status": by_status,
        "triaged": triaged,
    }, indent=2, sort_keys=True) + "\n")
    print(f"\nTriage artifact written to {TRIAGE}")

    if args.apply:
        # Update the ledger findings with canonical V13 triage states.
        triage_by_id = {t["id"]: t for t in triaged}
        for f in findings:
            if f.get("status") != "open":
                continue
            t = triage_by_id.get(f["id"])
            if not t:
                continue
            f["v13_triage_status"] = t["v13_status"]
            f["v13_lens"] = t["v13_lens"]
            if t["v13_status"] == "closed_in_unrecorded_wave":
                f["status"] = "closed_unverified"
                f["deferral_reason"] = (
                    "V13 triage found finding ID evidence in commits/tests, "
                    "but the V12 ledger lacks a behavioral close record. "
                    "Backfill close commit + behavioral_test_path before "
                    "promoting to status=closed."
                )
            elif t["v13_status"] == "absorbed_into_v13_lens":
                f["status"] = "absorbed"
                f["deferral_reason"] = (
                    "V13 triage mapped this finding into a broader V13 lens. "
                    "Keep absorbed status until the lens-level closure points "
                    "to exact behavioral evidence for this ID."
                )
            elif t["v13_status"] == "still_open":
                f["status"] = "open"

        by_status: dict[str, int] = {}
        for f in findings:
            status = f.get("status", "unknown")
            by_status[status] = by_status.get(status, 0) + 1
        ledger["by_status"] = by_status
        LEDGER.write_text(
            json.dumps(ledger, indent=2, sort_keys=True) + "\n"
        )
        print("findings_ledger.json updated with v13_triage_status fields")

    return 0


if __name__ == "__main__":
    sys.exit(main())
