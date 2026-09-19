#!/usr/bin/env python3
"""Validate fresh post-close CI evidence; write a durable report and fail closed.

This checks software evidence, not live account profitability. Delivery is owned
by the workflow's separately permissioned, opt-in notification job. This module
never sends messages or creates issues.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
REQUIRED_SUITES = {
    "organism_live_engine", "organism_engine_scenarios", "multi_tick_state",
    "safety_invariants", "self_evolution", "algorithm_improvements",
}
STATUS_FILES = {
    "test_summary.json": "overall",
    "replay_summary.json": "status",
    "grep_assertions.json": "overall",
    "runtime_snapshot_summary.json": "overall",
    "semantic_invariants_summary.json": "overall",
    "spec_drift_summary.json": "overall",
    "task_report.json": "artifact_pack_status",
}


def evaluate(
    artifacts: Path, *, expected_sha: str, started_at: float | None = None,
    upstream_status: str = "success", pack_outcome: str = "success",
    require_phase8: bool = False,
) -> list[str]:
    """Return bounded diagnostic messages, without echoing artifact contents."""
    breaches: list[str] = []

    def read(name: str) -> dict[str, Any]:
        path = artifacts / name
        try:
            if started_at is not None and path.stat().st_mtime < started_at:
                breaches.append(f"{name}: stale evidence")
            data = json.loads(path.read_text())
            if not isinstance(data, dict):
                raise ValueError("object required")
            return data
        except (OSError, ValueError):
            breaches.append(f"{name}: missing or invalid evidence")
            return {}

    if upstream_status != "success":
        breaches.append("An upstream workflow step did not succeed")
    if pack_outcome != "success":
        breaches.append("Full artifact generation did not succeed")
    if len(expected_sha) != 40 or any(c not in "0123456789abcdef" for c in expected_sha):
        breaches.append("A full expected source SHA is required")

    evidence = {name: read(name) for name in STATUS_FILES}
    for name, key in STATUS_FILES.items():
        data = evidence[name]
        if data.get(key) != "pass":
            breaches.append(f"{name}: required status is not pass")
        if data.get("timed_out") or data.get("error") or data.get("exit_code", 0) != 0:
            breaches.append(f"{name}: execution failure")
    report = evidence["task_report.json"]
    if report.get("sha") != expected_sha:
        breaches.append("task_report.json: source SHA does not match audited source")
    if report.get("tests_failed") or report.get("artifact_pack_errors"):
        breaches.append("task_report.json: recorded failures")

    def valid_tests(data: Any) -> bool:
        if not isinstance(data, dict):
            return False
        passed = data.get("passed")
        return (
            data.get("status") == "pass" and type(passed) is int and passed > 0
            and data.get("failed") == 0 and data.get("errors", 0) == 0
            and data.get("exit_code", 0) == 0 and not data.get("timed_out")
            and not data.get("error")
        )

    suites = evidence["test_summary.json"].get("suites")
    if not isinstance(suites, dict) or not REQUIRED_SUITES.issubset(suites):
        breaches.append("test_summary.json: required suites are missing")
    elif any(not valid_tests(data) for data in suites.values()):
        breaches.append("test_summary.json: failed, incomplete or zero-test suite")
    for name in ("replay_summary.json", "semantic_invariants_summary.json"):
        if not valid_tests(evidence[name]):
            breaches.append(f"{name}: failed, incomplete or zero-test suite")
    checks = evidence["grep_assertions.json"].get("checks")
    if not isinstance(checks, list) or not checks or any(
        not isinstance(check, dict) or check.get("passed") is not True for check in checks
    ):
        breaches.append("grep_assertions.json: missing or failed invariant assertions")
    snapshot = read("runtime_config_snapshot.json")
    if snapshot.get("error") or snapshot.get("exploration_enabled") is not False:
        breaches.append("runtime_config_snapshot.json: exploration must be explicitly disabled")
    if evidence["runtime_snapshot_summary.json"].get("errors"):
        breaches.append("runtime_snapshot_summary.json: recorded snapshot errors")
    if evidence["spec_drift_summary.json"].get("drift_count", 0) != 0:
        breaches.append("spec_drift_summary.json: runtime/spec drift")
    if require_phase8:
        phase8 = read("phase8_evidence_warehouse/postclose_run_summary.json")
        if phase8.get("ok") is not True or phase8.get("errors"):
            breaches.append("Phase 8 evidence generation did not succeed")
    return breaches


def write_report(artifacts: Path, *, expected_sha: str, breaches: list[str]) -> dict[str, Any]:
    artifacts.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "fail" if breaches else "pass", "source_sha": expected_sha,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "scope": "CI evidence only; no live account or strategy-edge certification",
        "breaches": breaches, "notification": "workflow-managed; no send attempted by checker",
    }
    (artifacts / "postclose_kpi_report.json").write_text(json.dumps(payload, indent=2) + "\n")
    body = (
        f"# Post-close evidence: {payload['status'].upper()}\n\n"
        f"Audited source: `{expected_sha}`\n\n{payload['scope']}.\n\n"
        + ("\n".join(f"- {item}" for item in breaches) if breaches else "Required evidence passed.")
        + "\n\nIssue delivery requires the workflow's explicit notify_issues input.\n"
    )
    (artifacts / "postclose_kpi_report.md").write_text(body)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
            output.write(body)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", type=Path, default=ART)
    parser.add_argument("--expected-sha", default=os.environ.get("CI_EXPECTED_SHA", ""))
    args = parser.parse_args(argv)
    breaches: list[str] = []
    expected_sha = args.expected_sha
    if not expected_sha:
        try:
            expected_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True, cwd=ROOT, timeout=10,
            ).strip()
        except (OSError, subprocess.SubprocessError):
            breaches.append("Unable to establish audited source SHA")
    try:
        started = os.environ.get("CI_RUN_STARTED_AT")
        started_at = float(started) if started else None
        breaches.extend(evaluate(
            args.artifacts_dir, expected_sha=expected_sha, started_at=started_at,
            upstream_status=os.environ.get("CI_UPSTREAM_STATUS", "success"),
            pack_outcome=os.environ.get("CI_ARTIFACT_PACK_OUTCOME", "success"),
            require_phase8=os.environ.get("CI_REQUIRE_PHASE8") == "true",
        ))
    except (TypeError, ValueError):
        breaches.append("Invalid evidence validation metadata")
    payload = write_report(args.artifacts_dir, expected_sha=expected_sha, breaches=breaches)
    print(f"Post-close CI evidence: {payload['status'].upper()} ({len(breaches)} findings)")
    return 1 if breaches else 0


if __name__ == "__main__":
    raise SystemExit(main())
