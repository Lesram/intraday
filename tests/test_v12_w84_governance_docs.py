"""V12 W84 (post-audit cleanup): tests for branch hygiene + V13 framework docs.

Closes 2 of the V12 external auditor's 10 cleanup items:

(9) Audit-artifact branch hygiene.  Pre-W84 the release branch
    carried 142 tracked files under artifacts/audit/ (V11 + V12
    auditors both flagged this).  W84 snapshots the current state
    to audit-evidence/v12 (non-destructive) and documents the V13+
    cutover plan in BRANCH_HYGIENE.md.

(10) V13 7-lens framework.  Auditor's recommendation:
     Deploy/Runtime Truth, Trading Safety, Strategy Expectancy,
     Data Integrity, Auth/RBAC, Test/CI Quality, Frontend/Product
     Contract.  W84 documents the framework in V13_FRAMEWORK.md.

Run with:
    ./venv/bin/python -m pytest tests/test_v12_w84_governance_docs.py -v
"""
from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
V13_FRAMEWORK = REPO_ROOT / "artifacts" / "audit" / "V13_FRAMEWORK.md"
BRANCH_HYGIENE = REPO_ROOT / "artifacts" / "audit" / "BRANCH_HYGIENE.md"


# ────────────────────────────────────────────────────────────────────
# V13 7-lens framework doc.
# ────────────────────────────────────────────────────────────────────

def test_w84_v13_framework_doc_exists():
    assert V13_FRAMEWORK.is_file(), (
        "V12 W84 regression: V13_FRAMEWORK.md missing — V13 has no "
        "documented framework to follow."
    )


def test_w84_v13_framework_lists_seven_lenses():
    """The doc must contain all 7 named lenses (auditor's
    recommendation list).  Behavioral check: parse the markdown,
    count headings, look for known names."""
    src = V13_FRAMEWORK.read_text()
    expected_lenses = (
        "Deploy / Runtime Truth",
        "Trading Safety",
        "Strategy Expectancy",
        "Data Integrity",
        "Auth / RBAC",
        "Test / CI Quality",
        "Frontend / Product Contract",
    )
    missing = [n for n in expected_lenses if n not in src]
    assert not missing, (
        f"V12 W84 regression: V13 framework missing lenses: {missing}"
    )


def test_w84_v13_framework_has_no_lens_expansion_clause():
    """The doc must explicitly forbid an 18th lens — the auditor's
    specific concern.  Lock the 17→7 contract."""
    src = V13_FRAMEWORK.read_text()
    assert "No new lens introduction" in src or "no 18th" in src.lower() \
        or "shrink, not expand" in src.lower(), (
        "V12 W84 regression: V13 framework no longer prohibits "
        "lens expansion — the cycle drift the auditor warned about "
        "could repeat."
    )


# ────────────────────────────────────────────────────────────────────
# Branch hygiene doc.
# ────────────────────────────────────────────────────────────────────

def test_w84_branch_hygiene_doc_exists():
    assert BRANCH_HYGIENE.is_file()


def test_w84_branch_hygiene_doc_describes_v13_cutover():
    """The doc must describe what gets removed from the release
    branch at V13 cutover, AND why the 4 CI-dependent files stay."""
    src = BRANCH_HYGIENE.read_text()
    assert "V13 cutover" in src
    assert "v12_state.json" in src
    assert "lint_baseline.json" in src
    assert "findings_ledger.json" in src


def test_w84_audit_evidence_branch_exists():
    """Behavioral: the snapshot branch must actually exist in this
    repo's git refs.  Locks the non-destructive hygiene approach."""
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "audit-evidence/v12"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, (
        "V12 W84 regression: audit-evidence/v12 branch missing.  "
        "Recreate via:\n"
        "  git branch audit-evidence/v12 HEAD"
    )


def test_w84_audit_evidence_branch_contains_v12_synthesis():
    """The snapshot branch must carry the V12 synthesis doc — that's
    the immutable record V13+ refers back to."""
    proc = subprocess.run(
        ["git", "show",
         "audit-evidence/v12:artifacts/audit/MASTER_AUDIT_SYNTHESIS_v12.md"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, (
        f"V12 W84 regression: audit-evidence/v12 branch is missing "
        f"the V12 synthesis doc.\n{proc.stderr}"
    )
    assert "Master Audit Synthesis" in proc.stdout
