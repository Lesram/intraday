"""V13 W91: lock the V13 plan document so it can't be silently modified.

The V13_PLAN.md is the user-approved plan for the V13 cycle.  This test
asserts the document exists, is structured per the W91 commit body, and
explicitly forbids an 18th lens.

Run with:
    ./venv/bin/python -m pytest tests/test_v13_w91_plan_doc.py -v
"""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
V13_PLAN = REPO_ROOT / "artifacts" / "audit" / "v13" / "V13_PLAN.md"


def test_v13_plan_doc_exists():
    assert V13_PLAN.is_file(), (
        "V13 W91 deliverable: artifacts/audit/v13/V13_PLAN.md must exist"
    )


def test_v13_plan_lists_seven_lenses():
    """Each of the 7 V13 lenses (per V13_FRAMEWORK.md) must have a wave."""
    src = V13_PLAN.read_text()
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
    assert not missing, f"V13 plan missing lenses: {missing}"


def test_v13_plan_explicitly_forbids_18th_lens():
    """The hard constraint: no lens expansion in V13."""
    src = V13_PLAN.read_text()
    assert (
        "no 18th lens" in src.lower()
        or "no new lens" in src.lower()
        or "shrink, not expand" in src.lower()
    ), "V13 plan must explicitly forbid lens expansion"


def test_v13_plan_has_per_wave_verification_protocol():
    """V13 must follow V12's wave protocol."""
    src = V13_PLAN.read_text()
    assert "verification protocol" in src.lower()
    assert "lint_ratchet" in src.lower()
    assert "audit_gate" in src.lower() or "forbid_marker_only" in src.lower()


def test_v13_plan_has_explicit_open_questions_for_user():
    """V13 plan must surface the questions the user must answer
    BEFORE execution begins."""
    src = V13_PLAN.read_text()
    assert "Open questions for the user" in src
    # Specifically the 5 questions from the plan body.
    assert "expectancy floor" in src.lower()
    assert "frontend" in src.lower()
    assert "_live_tick_inner" in src


def test_v13_plan_has_v12_baseline_reference():
    """V13 plan must reference the V12 final baseline numbers (0 fail
    / 7,107 pass) so V13 regressions are detectable against the right
    baseline."""
    src = V13_PLAN.read_text()
    assert "7,107" in src or "7107" in src or "0 fail" in src.lower()


def test_v13_plan_lists_what_v13_will_not_do():
    """V13 plan must scope OUT the unexplored areas (load test, chaos,
    etc.) — those are post-V13 engineering work, not audit work."""
    src = V13_PLAN.read_text()
    assert "What V13 will NOT do" in src or "will not do" in src.lower()
    # Specific exclusions called out.
    assert "18th lens" in src or "no 18th" in src.lower() or "no new lens" in src.lower()
    assert "load test" in src.lower() or "chaos" in src.lower() or "disaster recovery" in src.lower()
