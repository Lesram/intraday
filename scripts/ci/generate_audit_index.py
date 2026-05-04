#!/usr/bin/env python3
"""Generate docs/engineering/LIVE_AUDIT_INDEX.md from current repo state.

This file is regenerated on every PR and post-close run so the latest
audit surface is always documented and machine-readable.

Requirements enforced:
  - Latest trading report path must not be "none"
  - Open risks must not say "None identified" (at minimum, list known constraints)
  - PR scope classification is required
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from change_scope import get_change_set  # noqa: E402


def sh(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, cwd=str(ROOT), stderr=subprocess.STDOUT).strip()
    except Exception:
        return ""


def classify_pr_scope(changed: list[str]) -> str:
    """Classify PR scope based on changed file paths."""
    has_backend_logic = any(
        p.startswith("backend/") and not p.startswith("backend/config/")
        for p in changed
    )
    has_config = any(
        p.startswith(("backend/config/", ".env", "docker-compose"))
        for p in changed
    )
    has_tests_docs = any(
        p.startswith(("tests/", "docs/"))
        for p in changed
    )
    has_evidence_tooling = any(
        p.startswith(("scripts/ci/", "artifacts/"))
        for p in changed
    )

    if has_backend_logic:
        return "backend_logic"
    if has_config and not has_backend_logic:
        return "runtime_config_only"
    if (has_tests_docs or has_evidence_tooling) and not has_backend_logic and not has_config:
        return "tooling/evidence_only"
    if not changed:
        return "empty"
    return "mixed"


def main() -> None:
    sha = sh(["git", "rev-parse", "HEAD"])
    short_sha = sha[:10]
    branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Detect PR number from env (GitHub Actions) or gh CLI
    pr_number = os.environ.get("GITHUB_PR_NUMBER", "")
    if not pr_number:
        pr_number = sh(["gh", "pr", "view", "--json", "number", "-q", ".number"])
    pr_label = f"PR #{pr_number}" if pr_number else "n/a"

    change_set = get_change_set(root=ROOT)
    all_changed = [p for p in change_set.paths if p.strip()]
    backend_changed = [p for p in all_changed if p.startswith("backend/")]
    backend_runtime_changed = [
        p for p in backend_changed
        if not p.startswith(("backend/migrations/", "backend/config/"))
    ]
    tests_changed = [p for p in all_changed if p.startswith("tests/")]
    organism_changed = [p for p in all_changed if p.startswith("backend/organism/")]
    docs_changed = [p for p in all_changed if p.startswith("docs/")]

    # PR scope classification
    scope = classify_pr_scope(all_changed)

    # Load runtime snapshots
    defaults_path = ROOT / "artifacts" / "runtime_defaults_snapshot.json"
    resolved_path = ROOT / "artifacts" / "resolved_config_snapshot.json"
    live_path = ROOT / "artifacts" / "live_process_runtime_snapshot.json"
    legacy_path = ROOT / "artifacts" / "runtime_config_snapshot.json"

    # Prefer resolved config snapshot for display
    snapshot_path = resolved_path if resolved_path.exists() else (defaults_path if defaults_path.exists() else legacy_path)
    if snapshot_path and snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text())
        # Extract constants from resolved.resolved or top-level
        src = snapshot.get("resolved", snapshot)
        live_constants = {
            "timeframe": src.get("timeframe"),
            "max_positions": src.get("max_positions"),
            "alpha_top_n": src.get("alpha_top_n"),
            "learning_mode_threshold": src.get("learning_mode_threshold_trades"),
            "evolution_freeze": src.get("evolution_freeze_until_trades"),
            "horizon_timeout_bars": src.get("horizon_timeout_bars"),
            "drawdown_kill_pct": src.get("drawdown_kill_pct"),
            "exploration_enabled": src.get("exploration_enabled"),
            "bar_boundary_entry_only": src.get("bar_boundary_entry_only"),
        }
        snapshot_label = snapshot_path.name
    else:
        live_constants = {"note": "No runtime snapshot found — run write_runtime_snapshot.py"}
        snapshot_label = "missing"

    # Load grep assertions
    grep_path = ROOT / "artifacts" / "grep_assertions.json"
    if grep_path.exists():
        grep_data = json.loads(grep_path.read_text())
        grep_status = grep_data.get("overall", "unknown")
        failing_checks = [c["name"] for c in grep_data.get("checks", []) if not c.get("passed")]
    else:
        grep_status = "not run"
        failing_checks = []

    # Find latest improve doc
    improve_docs = sorted(ROOT.glob("docs/architecture/improve*.md"))
    latest_improve = str(improve_docs[-1].relative_to(ROOT)) if improve_docs else "none"

    # Find latest trading report
    report_patterns = [
        "docs/architecture/*trading*report*",
        "docs/architecture/*trading_report*",
        "docs/**/trading_report*",
    ]
    report_paths = []
    for pat in report_patterns:
        report_paths.extend(sorted(ROOT.glob(pat)))
    latest_report = str(report_paths[-1].relative_to(ROOT)) if report_paths else ""

    # Open risks — never say "None identified"
    risks: list[str] = []
    if grep_status == "fail":
        risks.append(f"Grep assertions failing: {', '.join(failing_checks)}")
    if snapshot_label == "missing":
        risks.append("No runtime config snapshot — organism constants not verified")
    if organism_changed:
        risks.append(f"{len(organism_changed)} organism file(s) changed — require replay verification")
    elif backend_runtime_changed:
        risks.append(
            f"{len(backend_runtime_changed)} backend runtime file(s) changed — require targeted verification"
        )
    if not latest_report:
        risks.append("No trading report found — paper trading results not documented")
    # Always include at least one structural risk
    if not risks:
        risks.append("No code changes in this PR — verify evidence artifacts are current")

    # Warnings for missing data
    warnings: list[str] = []
    if not latest_report:
        warnings.append("WARNING: latest_report is empty — commit a trading report before merge")

    # Generate markdown
    lines = [
        "# Live Audit Index",
        "",
        f"Generated: {timestamp}",
        f"PR: {pr_label}",
        f"SHA: `{short_sha}`",
        f"Branch: `{branch}`",
        f"Scope: **{scope}**",
        f"Change scope: `{change_set.scope}` (`{change_set.ref}`)",
        "",
        "## Changed files",
        "",
        "| Category | Count | Files |",
        "|----------|-------|-------|",
        f"| Backend | {len(backend_changed)} | {', '.join(f'`{p}`' for p in backend_changed[:10]) or 'none'} |",
        f"| Organism | {len(organism_changed)} | {', '.join(f'`{p}`' for p in organism_changed[:10]) or 'none'} |",
        f"| Tests | {len(tests_changed)} | {', '.join(f'`{p}`' for p in tests_changed[:10]) or 'none'} |",
        f"| Docs | {len(docs_changed)} | {', '.join(f'`{p}`' for p in docs_changed[:10]) or 'none'} |",
        "",
        "## Live constants",
        "",
        f"Source: `{snapshot_label}`",
        "",
        "```json",
        json.dumps(live_constants, indent=2),
        "```",
        "",
        "## Snapshot files",
        "",
        f"- Defaults: `artifacts/runtime_defaults_snapshot.json`",
        f"- Resolved config: `artifacts/resolved_config_snapshot.json`",
        f"- Live process: `artifacts/live_process_runtime_snapshot.json`",
        "",
        "## Reference paths",
        "",
        f"- Latest improve doc: `{latest_improve}`",
        f"- Latest trading report: `{latest_report or 'MISSING — required before merge'}`",
        f"- Grep assertions: `artifacts/grep_assertions.json` (status: **{grep_status}**)",
        f"- Semantic invariants: `tests/test_semantic_invariants.py`",
        "",
        "## Open risks",
        "",
    ]
    for r in risks:
        lines.append(f"- {r}")

    if warnings:
        lines.append("")
        lines.append("## Warnings")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")

    lines.append("")

    out = ROOT / "docs" / "engineering" / "LIVE_AUDIT_INDEX.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    print(f"Audit index written to {out}")


if __name__ == "__main__":
    main()
