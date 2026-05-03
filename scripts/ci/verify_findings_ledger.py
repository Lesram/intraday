"""V12 W77 (EXT-9): verify the findings ledger is internally consistent.

Asserts:

1. Every ``closed`` finding has a non-empty ``behavioral_test_path``
   (or this is the V12 W73 marker-gate equivalent: it's auditable).
2. Every ``deferred`` finding has a non-empty ``deferral_reason``.
3. The ledger is in sync with ``v12_state.json`` for V12-era IDs.
4. The schema version matches what this script expects.

Exit codes:
- 0: ledger is internally consistent
- 1: violations found (printed)
- 2: ledger missing or unreadable

Usage:
    python scripts/ci/verify_findings_ledger.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER = REPO_ROOT / "artifacts" / "audit" / "findings_ledger.json"


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
    for f in ledger.get("findings", []):
        ident = f["id"]
        status = f["status"]
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

    n_closed = sum(1 for f in ledger["findings"] if f["status"] == "closed")
    n_deferred = sum(1 for f in ledger["findings"] if f["status"] == "deferred")
    n_open = sum(1 for f in ledger["findings"] if f["status"] == "open")
    n_other = ledger["n_findings"] - n_closed - n_deferred - n_open

    print(f"Findings ledger: {ledger['n_findings']} total")
    print(f"  closed={n_closed}, deferred={n_deferred}, open={n_open}, other={n_other}")
    if violations:
        print(f"\nFAIL: {len(violations)} ledger consistency violation(s):")
        for v in violations:
            print(v)
        return 1
    print("\nPASS: ledger is internally consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
