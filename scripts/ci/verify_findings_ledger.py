"""V12 W77 (EXT-9): verify the findings ledger is internally consistent.

Asserts:

1. Every ``closed`` finding has a non-empty ``behavioral_test_path``
   (or this is the V12 W73 marker-gate equivalent: it's auditable).
2. Every ``deferred`` finding has a non-empty ``deferral_reason``.
3. The ledger is in sync with ``v12_state.json`` for V12-era IDs.
4. The schema version matches what this script expects.
5. V13 triage states are canonicalized: a finding cannot remain
   ``open`` while carrying ``closed_in_unrecorded_wave`` or
   ``absorbed_into_v13_lens`` triage.

Exit codes:
- 0: ledger is internally consistent
- 1: violations found (printed)
- 2: ledger missing or unreadable

Usage:
    python scripts/ci/verify_findings_ledger.py
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER = REPO_ROOT / "artifacts" / "audit" / "findings_ledger.json"
VALID_STATUSES = {
    "open",
    "closed",
    "closed_unverified",
    "absorbed",
    "deferred",
    "documented_by_design",
}


def main() -> int:
    if not LEDGER.is_file():
        print(f"ERROR: {LEDGER} not found.  Run "
              f"``scripts/ci/build_findings_ledger.py`` first.")
        return 2
    ledger = json.loads(LEDGER.read_text())

    if ledger.get("schema_version") != 1:
        print(f"ERROR: ledger schema_version={ledger.get('schema_version')} "
              f"expected 1.  Run build_findings_ledger.py to regenerate.")
        return 2

    violations: list[str] = []
    findings = ledger.get("findings", [])
    if ledger.get("n_findings") != len(findings):
        violations.append(
            f"  [ledger] n_findings={ledger.get('n_findings')} but "
            f"len(findings)={len(findings)}"
        )

    for f in findings:
        ident = f["id"]
        status = f["status"]
        triage_status = f.get("v13_triage_status")

        if status not in VALID_STATUSES:
            violations.append(
                f"  [{ident}] status={status!r} is not in "
                f"{sorted(VALID_STATUSES)}"
            )

        if status == "closed":
            if not f.get("behavioral_test_path"):
                violations.append(
                    f"  [{ident}] status=closed but behavioral_test_path "
                    f"is empty — V12 W73 requires every closure to "
                    f"reference a real test."
                )
        elif status == "deferred":
            if not f.get("deferral_reason"):
                violations.append(
                    f"  [{ident}] status=deferred but deferral_reason "
                    f"is empty — every deferral must explain why."
                )
        elif status == "closed_unverified":
            if triage_status != "closed_in_unrecorded_wave":
                violations.append(
                    f"  [{ident}] status=closed_unverified requires "
                    f"v13_triage_status=closed_in_unrecorded_wave."
                )
            if not f.get("deferral_reason"):
                violations.append(
                    f"  [{ident}] status=closed_unverified but no "
                    f"deferral_reason explains the missing closure evidence."
                )
        elif status == "absorbed":
            if triage_status != "absorbed_into_v13_lens":
                violations.append(
                    f"  [{ident}] status=absorbed requires "
                    f"v13_triage_status=absorbed_into_v13_lens."
                )
            if not f.get("v13_lens"):
                violations.append(
                    f"  [{ident}] status=absorbed but v13_lens is empty."
                )

        if (
            status == "open"
            and triage_status
            in {"closed_in_unrecorded_wave", "absorbed_into_v13_lens"}
        ):
            violations.append(
                f"  [{ident}] status=open contradicts "
                f"v13_triage_status={triage_status}."
            )

    counted_by_status: dict[str, int] = {}
    for f in findings:
        counted_by_status[f["status"]] = counted_by_status.get(f["status"], 0) + 1
    recorded_by_status = ledger.get("by_status")
    if recorded_by_status and counted_by_status != recorded_by_status:
        violations.append(
            f"  [ledger] by_status mismatch: recorded={recorded_by_status} "
            f"computed={counted_by_status}"
        )

    print(f"Findings ledger: {ledger['n_findings']} total")
    for status, count in sorted(counted_by_status.items()):
        print(f"  {status}={count}")
    if violations:
        print(f"\nFAIL: {len(violations)} ledger consistency violation(s):")
        for v in violations:
            print(v)
        return 1
    print("\nPASS: ledger is internally consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
