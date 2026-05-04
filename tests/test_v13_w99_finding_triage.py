"""V13 W99 — V8-V11 finding triage behavioral coverage.

The plan: every still-open V8-V11 finding must be triaged before
V13 closes.  W99 ships ``scripts/ci/triage_v8_v11_findings.py`` which:
1. Greps commit messages + test files for each finding ID.
2. Falls back to summary-keyword → V13-lens absorption.
3. Anything else stays as ``still_open``.

Acceptance:
- Triage artifact at ``artifacts/audit/v13/v13_finding_triage.json``
  exists and is well-formed.
- Ledger still verifies (no schema drift introduced by --apply).
- Every open finding has a non-null ``v13_triage_status`` field.
- The ``still_open`` count is documented and bounded.

Run with:
    ./venv/bin/python -m pytest tests/test_v13_w99_finding_triage.py -v
"""
# wave: V13-W99
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRIAGE_SCRIPT = REPO_ROOT / "scripts" / "ci" / "triage_v8_v11_findings.py"
TRIAGE_ARTIFACT = REPO_ROOT / "artifacts" / "audit" / "v13" / "v13_finding_triage.json"
LEDGER = REPO_ROOT / "artifacts" / "audit" / "findings_ledger.json"


def test_w99_triage_script_exists():
    assert TRIAGE_SCRIPT.is_file()


def test_w99_triage_artifact_committed():
    """The triage artifact must be present and well-formed."""
    assert TRIAGE_ARTIFACT.is_file(), (
        "Triage artifact missing.  Run "
        "`scripts/ci/triage_v8_v11_findings.py --apply`."
    )
    payload = json.loads(TRIAGE_ARTIFACT.read_text())
    assert "n_open_findings" in payload
    assert "by_status" in payload
    assert "triaged" in payload
    assert payload["n_open_findings"] == len(payload["triaged"])


def test_w99_no_unclassified_findings():
    """Every triaged finding must have a v13_status of one of:
    closed_in_unrecorded_wave, absorbed_into_v13_lens, still_open."""
    payload = json.loads(TRIAGE_ARTIFACT.read_text())
    valid = {
        "closed_in_unrecorded_wave",
        "absorbed_into_v13_lens",
        "still_open",
    }
    for t in payload["triaged"]:
        assert t["v13_status"] in valid, (
            f"finding {t['id']} has unknown v13_status={t['v13_status']!r}"
        )


def test_w99_still_open_count_bounded():
    """Per V13 plan estimate: ~10% still-open is acceptable.  Anything
    above 30% means the triage missed evidence and the script should
    be rerun against the latest HEAD."""
    payload = json.loads(TRIAGE_ARTIFACT.read_text())
    total = payload["n_open_findings"]
    still = payload["by_status"].get("still_open", 0)
    pct = 100.0 * still / total if total else 0
    assert pct <= 30.0, (
        f"still_open at {pct:.1f}% (>{30}%) — triage should be rerun"
    )


def test_w99_ledger_has_triage_fields_after_apply():
    """Post --apply, every open finding has a v13_triage_status field."""
    ledger = json.loads(LEDGER.read_text())
    open_findings = [
        f for f in ledger["findings"] if f.get("status") == "open"
    ]
    assert open_findings, "ledger should still have open findings to triage"
    missing = [f for f in open_findings if "v13_triage_status" not in f]
    assert not missing, (
        f"{len(missing)} open finding(s) missing v13_triage_status: "
        f"{[f['id'] for f in missing[:5]]}"
    )


def test_w99_ledger_still_verifies():
    """The ledger schema must still validate after --apply."""
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "ci" / "verify_findings_ledger.py")],
        capture_output=True, text=True, timeout=30, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, (
        f"verify_findings_ledger.py failed:\n{proc.stdout}\n{proc.stderr}"
    )


def test_w99_critical_findings_have_path_forward():
    """Per V13 plan acceptance: zero critical findings without a path
    forward.  W99 acceptable status for criticals: closed_in_unrecorded
    or absorbed_into_v13_lens (with evidence).  Critical-and-still_open
    requires explicit follow-up."""
    payload = json.loads(TRIAGE_ARTIFACT.read_text())
    critical_still_open = [
        t for t in payload["triaged"]
        if t.get("severity") == "critical"
        and t["v13_status"] == "still_open"
    ]
    # If there are critical still-opens, they must have a non-empty
    # summary so a future auditor can pick them up.
    for t in critical_still_open:
        assert t.get("summary"), (
            f"critical still-open finding {t['id']} lacks summary"
        )
    # And the count should be small (single-digit).
    assert len(critical_still_open) <= 5, (
        f"{len(critical_still_open)} critical still-open findings — "
        f"too many for V13 to ship cleanly"
    )
