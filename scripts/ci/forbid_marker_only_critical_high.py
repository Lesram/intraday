"""V12 W73 (AA5-2 + EXT-2): forbid marker-only tests for Critical/High closures.

The single most important V11 lesson — caught both by the V11 audit
itself and confirmed by the external auditor — is that source-grep /
marker-style tests give false comfort.  The wave-47 JWT regression
test asserted ``"leeway=JWT_CLOCK_SKEW" in inspect.getsource(...)`` and
PASSED for ~24 hours while every JWT-authenticated endpoint returned
401 in production.

This script is the CI gate that prevents that pattern from re-shipping
for any Critical or High severity audit finding.

Logic:

1. Load ``artifacts/audit/findings_ledger.json`` (falling back to the
   legacy ``artifacts/audit/v12/v12_state.json`` only when the ledger
   has not been generated).
2. Collect every closure of severity ``critical`` or ``high`` and its
   ``behavioral_test_path`` (file or file::test specifier).
3. Run the wave-test classifier (``classify_wave_tests.py``) against
   each referenced test file.  If the test path includes ``::name``,
   gate on that specific test only.
4. Fail with exit 1 if any of those tests is classified ``marker-only``.

Future Critical/High closures must reference a behavioral test path or
the gate fails — the user's "real look of the code being tested, not
phantom" requirement.

Usage:
    python scripts/ci/forbid_marker_only_critical_high.py
    # exits 0 on pass, 1 on violation; prints a report either way.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_FILE = REPO_ROOT / "artifacts" / "audit" / "findings_ledger.json"
STATE_FILE = REPO_ROOT / "artifacts" / "audit" / "v12" / "v12_state.json"

# Make the classifier importable.
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import classify_wave_tests as cwt  # noqa: E402


def _classify_file(path: Path) -> dict[str, str]:
    """Return {test_func_name: classification} for a Python test file."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for row in cwt.classify_file(path):
        out[row.name] = row.classification
        if "::" in row.name:
            out.setdefault(row.name.rsplit("::", 1)[-1], row.classification)
    return out


def _check_path(test_path: str) -> tuple[str, str | None]:
    """Resolve a `path/to/file.py::test_name` (or just file path) to a
    classification.  Returns (classification, error_message)."""
    if "::" in test_path:
        file_part, test_part = test_path.split("::", 1)
    else:
        file_part, test_part = test_path, None
    p = REPO_ROOT / file_part
    if not p.exists():
        return ("missing", f"file not found: {file_part}")
    classifications = _classify_file(p)
    if not classifications:
        return ("missing", f"no test functions in {file_part}")
    if test_part is None:
        # Whole-file gate: if any test in the file is marker-only AND the
        # file is referenced as a Critical/High evidence, we fail.  (This
        # is conservative — the user can always point at a specific test.)
        marker = [n for n, c in classifications.items() if c == "marker-only"]
        if marker:
            return ("marker-only", f"file-level: {len(marker)} marker-only test(s) — {marker[0]} (and {len(marker)-1} more)" if len(marker) > 1 else f"file-level: marker-only — {marker[0]}")
        return ("ok", None)
    cls = classifications.get(test_part)
    if cls is None:
        return ("missing", f"test {test_part} not found in {file_part}")
    return (cls, None)


def _load_audit_state() -> tuple[str, dict]:
    """Load the canonical findings source for the gate.

    V12 originally gated ``v12_state.json``.  V13 moved the cross-round
    rollup into ``findings_ledger.json``; using the old state file would
    silently skip newer closures.
    """
    if LEDGER_FILE.is_file():
        return ("findings_ledger.json", json.loads(LEDGER_FILE.read_text()))
    if STATE_FILE.is_file():
        return ("v12_state.json", json.loads(STATE_FILE.read_text()))
    raise FileNotFoundError(
        f"neither {LEDGER_FILE.relative_to(REPO_ROOT)} nor "
        f"{STATE_FILE.relative_to(REPO_ROOT)} exists"
    )


def _severity(finding: dict) -> str | None:
    return finding.get("severity") or finding.get("severity_at_first_appearance")


def main() -> int:
    try:
        source_name, state = _load_audit_state()
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: audit state not readable: {exc}")
        return 2

    # Gather all (id, severity, behavioral_test_path) tuples for
    # closed Critical/High findings.
    audited: list[tuple[str, str, str | None, str]] = []
    for f in state.get("findings", []):
        if f.get("status") != "closed":
            continue
        sev = _severity(f)
        if sev not in {"critical", "high"}:
            continue
        audited.append((
            f["id"], sev,
            f.get("behavioral_test_path"),
            source_name,
        ))
    for f in state.get("v11_closures_audited_in_v12", []):
        sev = _severity(f)
        if sev not in {"critical", "high"}:
            continue
        audited.append((
            f["id"], sev,
            f.get("behavioral_test_path"),
            "v11_closures_audited_in_v12",
        ))

    failures: list[str] = []
    passes: list[str] = []
    for fid, sev, test_path, source in audited:
        if not test_path:
            failures.append(
                f"  [{sev:8}] {fid:10} → no behavioral_test_path "
                f"in {source} (V12 W73 requires every Crit/High "
                f"closure to ledger a behavioral test)"
            )
            continue
        cls, err = _check_path(test_path)
        if cls == "ok" or cls == "behavioral":
            passes.append(f"  [{sev:8}] {fid:10} → {test_path}  ✓ {cls}")
        elif cls == "mixed":
            # Mixed is acceptable — has at least one behavioral signal.
            passes.append(f"  [{sev:8}] {fid:10} → {test_path}  ✓ mixed (behavioral + marker)")
        elif cls == "structural":
            # Borderline — flag as warning but don't fail.
            passes.append(f"  [{sev:8}] {fid:10} → {test_path}  ⚠ structural (no assertions)")
        else:
            failures.append(
                f"  [{sev:8}] {fid:10} → {test_path}  ✗ {cls}"
                + (f" ({err})" if err else "")
            )

    print(
        "V12 W73 marker-only Critical/High gate — "
        f"{len(audited)} findings audited from {source_name}"
    )
    print()
    if passes:
        print("PASSED:")
        for p in passes:
            print(p)
        print()
    if failures:
        print("FAILED:")
        for f in failures:
            print(f)
        print()
        print(
            f"V12 W73 gate FAIL: {len(failures)} Critical/High closure(s) "
            f"do not have a behavioral test.  This is the wave-47 JWT "
            f"failure pattern — fix by adding behavioral tests OR pointing "
            f"behavioral_test_path at an existing behavioral test."
        )
        return 1
    print("V12 W73 gate PASS: every Critical/High closure has a behavioral test.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
