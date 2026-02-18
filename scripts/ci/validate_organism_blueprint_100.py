#!/usr/bin/env python3
"""
Validate blueprint 100%-completion evidence for the Evolving Organism.

This script does not fabricate runtime proof; it inspects repository artifacts
and test outputs to produce an objective pass/pending matrix.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
DOC_AUDITS = ROOT / "docs" / "audits"


@dataclass
class CheckItem:
    key: str
    description: str
    status: str
    evidence: str


def _latest(pattern: str) -> Path | None:
    matches = sorted(REPORTS.glob(pattern))
    return matches[-1] if matches else None


def _acceptance_ok(prefix: str, min_seconds: int) -> tuple[bool, str]:
    latest_json = _latest(f"{prefix}_*.json")
    latest_md = _latest(f"{prefix}_*.md")
    if not latest_json or not latest_md:
        return False, f"run scripts/ci/run_organism_live_acceptance.py --mode {prefix.split('_')[1].upper()}"

    try:
        payload = json.loads(latest_json.read_text(encoding="utf-8"))
    except Exception:
        return False, f"invalid evidence file: {latest_json.relative_to(ROOT)}"

    duration = int(payload.get("duration_seconds", 0) or 0)
    errors = int(payload.get("error_probe_count", 0) or 0)
    if duration < min_seconds:
        return False, (
            f"latest run too short ({duration}s < {min_seconds}s): "
            f"{latest_json.relative_to(ROOT)}"
        )
    if errors > 0:
        return False, (
            f"latest run has errors ({errors}): "
            f"{latest_json.relative_to(ROOT)}"
        )

    return True, str(latest_md.relative_to(ROOT))


def run_checks() -> list[CheckItem]:
    checks: list[CheckItem] = []

    required_files = [
        ROOT / "backend" / "organism" / "live_engine.py",
        ROOT / "backend" / "organism" / "scheduler.py",
        ROOT / "backend" / "organism" / "brain_persistence.py",
        ROOT / "tests" / "test_organism_live_engine.py",
        ROOT / "tests" / "test_self_evolution.py",
        ROOT / "tests" / "test_organism_blueprint_persistence.py",
    ]

    all_present = all(p.exists() for p in required_files)
    checks.append(
        CheckItem(
            key="core_files",
            description="Core blueprint implementation files present",
            status="PASS" if all_present else "FAIL",
            evidence="; ".join(str(p.relative_to(ROOT)) for p in required_files if p.exists()),
        )
    )

    comp_report = DOC_AUDITS / "EVOLVING_ORGANISM_BLUEPRINT_COMPLIANCE_AUDIT_2026-02-16.md"
    checks.append(
        CheckItem(
            key="compliance_report",
            description="Blueprint compliance audit report exists",
            status="PASS" if comp_report.exists() else "FAIL",
            evidence=str(comp_report.relative_to(ROOT)) if comp_report.exists() else "missing",
        )
    )

    lt06_ok, lt06_evidence = _acceptance_ok("organism_lt06_acceptance", 24 * 3600)
    lt07_ok, lt07_evidence = _acceptance_ok("organism_lt07_acceptance", 5 * 24 * 3600)

    checks.append(
        CheckItem(
            key="lt06",
            description="LT-06 (24h paper) evidence present",
            status="PASS" if lt06_ok else "PENDING",
            evidence=lt06_evidence,
        )
    )

    checks.append(
        CheckItem(
            key="lt07",
            description="LT-07 (5-day paper) evidence present",
            status="PASS" if lt07_ok else "PENDING",
            evidence=lt07_evidence,
        )
    )

    return checks


def write_report(checks: list[CheckItem]) -> tuple[Path, Path]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
    json_path = REPORTS / f"organism_blueprint_100_validation_{ts}.json"
    md_path = REPORTS / f"organism_blueprint_100_validation_{ts}.md"

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "checks": [c.__dict__ for c in checks],
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    pass_count = sum(1 for c in checks if c.status == "PASS")
    pending_count = sum(1 for c in checks if c.status == "PENDING")
    fail_count = sum(1 for c in checks if c.status == "FAIL")

    overall = "PASS" if fail_count == 0 and pending_count == 0 else "PENDING"

    lines = [
        "# Organism Blueprint 100% Validation",
        "",
        f"- Generated At: {payload['generated_at']}",
        f"- PASS: {pass_count}",
        f"- PENDING: {pending_count}",
        f"- FAIL: {fail_count}",
        f"- Overall: {overall}",
        "",
        "## Check Matrix",
    ]

    for c in checks:
        lines.append(f"- [{c.status}] {c.key}: {c.description}")
        lines.append(f"  - Evidence: {c.evidence}")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    checks = run_checks()
    json_path, md_path = write_report(checks)
    print(f"Validation JSON: {json_path}")
    print(f"Validation MD:   {md_path}")

    has_fail = any(c.status == "FAIL" for c in checks)
    has_pending = any(c.status == "PENDING" for c in checks)
    if has_fail:
        return 2
    if has_pending:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
