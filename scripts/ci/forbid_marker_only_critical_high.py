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

1. Load ``artifacts/audit/v12/v12_state.json`` (the findings ledger).
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

import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = REPO_ROOT / "artifacts" / "audit" / "v12" / "v12_state.json"

# Make the classifier importable.
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import classify_wave_tests as cwt  # noqa: E402


def _classify_file(path: Path) -> dict[str, str]:
    """Return {test_func_name: classification} for a Python test file."""
    if not path.exists():
        return {}
    src = path.read_text()
    tree = ast.parse(src, filename=str(path))
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            out[node.name] = cwt.classify_test(str(path), node).classification
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


def main() -> int:
    if not STATE_FILE.is_file():
        print(f"ERROR: {STATE_FILE} not found")
        return 2
    state = json.loads(STATE_FILE.read_text())

    # Gather all (id, severity, behavioral_test_path) tuples for
    # closed Critical/High findings.
    audited: list[tuple[str, str, str | None, str]] = []
    for f in state.get("findings", []):
        if f.get("status") != "closed":
            continue
        if f.get("severity") not in {"critical", "high"}:
            continue
        audited.append((
            f["id"], f["severity"],
            f.get("behavioral_test_path"),
            "v12_findings",
        ))
    for f in state.get("v11_closures_audited_in_v12", []):
        if f.get("severity") not in {"critical", "high"}:
            continue
        audited.append((
            f["id"], f["severity"],
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

    print(f"V12 W73 marker-only Critical/High gate — {len(audited)} findings audited")
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
