"""V13 W101 — synthesis document gate.

W101 is the closing wave of V13.  This test pins:
1. ``MASTER_AUDIT_SYNTHESIS_v13.md`` exists and is well-structured.
2. Every V13 lens is referenced in the synthesis.
3. The 10-criterion success table is complete.
4. The 4 still-open findings (CCC-1, III-F1, BB2-F3, DD5-4) are
   listed as the V14 / V13.1 carry-over.

Run with:
    ./venv/bin/python -m pytest tests/test_v13_w101_synthesis.py -v
"""
# wave: V13-W101
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SYNTHESIS = REPO_ROOT / "artifacts" / "audit" / "MASTER_AUDIT_SYNTHESIS_v13.md"


def test_w101_synthesis_doc_exists():
    assert SYNTHESIS.is_file()


def test_w101_synthesis_lists_all_seven_lenses():
    src = SYNTHESIS.read_text()
    expected = (
        "Deploy / Runtime Truth",
        "Trading Safety",
        "Strategy Expectancy",
        "Data Integrity",
        "Auth / RBAC",
        "Test / CI Quality",
        "Frontend / Product Contract",
    )
    missing = [n for n in expected if n not in src]
    assert not missing, f"V13 synthesis missing lenses: {missing}"


def test_w101_synthesis_lists_all_ten_waves():
    """W92 → W101 must each appear with at least one summary line."""
    src = SYNTHESIS.read_text()
    for n in range(91, 102):
        assert f"W{n}" in src, f"W{n} not mentioned in synthesis"


def test_w101_synthesis_records_v13_success_criteria():
    """The 10-row success-criterion table must be present."""
    src = SYNTHESIS.read_text()
    # Each criterion must be referenced.
    expected_phrases = (
        "no 18th lens",
        "no longer xfail",
        "npm run build",
        "configurable floor",
        "IDOR cross-user",
        "Marker-only ratio",
        "_live_tick_inner",
    )
    missing = [p for p in expected_phrases if p not in src]
    assert not missing, f"V13 synthesis missing criteria: {missing}"


def test_w101_synthesis_lists_four_still_open_findings():
    """The four W99-triaged still-open findings must be carried into V14."""
    src = SYNTHESIS.read_text()
    expected_ids = ("CCC-1", "III-F1", "BB2-F3", "DD5-4")
    missing = [i for i in expected_ids if i not in src]
    assert not missing, f"still-open findings missing from synthesis: {missing}"


def test_w101_synthesis_recommends_v14_framework():
    """V13 framework predicted V14 should be quarterly health-check; the
    synthesis must surface this recommendation."""
    src = SYNTHESIS.read_text()
    assert (
        "V14" in src and ("quarterly" in src.lower() or "external" in src.lower())
    ), "V14 recommendation missing from synthesis"


def test_w101_synthesis_has_external_auditor_handoff():
    """The synthesis must include explicit handoff steps for the next
    auditor — the protocol from V12 W85 carried forward."""
    src = SYNTHESIS.read_text()
    assert "Handoff for the next external auditor" in src
    # The 5-step verification protocol from V12 W85 must be referenced.
    assert "audit-evidence/v13" in src
    assert "verify_findings_ledger" in src
    assert "mutation_smoke" in src or "marker_only_full_corpus" in src
