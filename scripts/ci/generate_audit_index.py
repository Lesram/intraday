#!/usr/bin/env python3
"""Generate docs/engineering/LIVE_AUDIT_INDEX.md from current repo state.

This file is regenerated on every PR and post-close run so the latest
audit surface is always documented and machine-readable.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def sh(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, cwd=str(ROOT), stderr=subprocess.STDOUT).strip()
    except Exception:
        return ""


def main() -> None:
    sha = sh(["git", "rev-parse", "HEAD"])
    short_sha = sha[:10]
    branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Changed backend files vs main
    base = "origin/main" if branch != "main" else "HEAD~1"
    diff_output = sh(["git", "diff", "--name-only", f"{base}...HEAD"])
    all_changed = [p for p in diff_output.splitlines() if p.strip()]
    backend_changed = [p for p in all_changed if p.startswith("backend/")]
    tests_changed = [p for p in all_changed if p.startswith("tests/")]
    organism_changed = [p for p in all_changed if p.startswith("backend/organism/")]
    docs_changed = [p for p in all_changed if p.startswith("docs/")]

    # Load runtime snapshot if it exists
    snapshot_path = ROOT / "artifacts" / "runtime_config_snapshot.json"
    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text())
        live_constants = {
            "timeframe": snapshot.get("timeframe"),
            "max_positions": snapshot.get("max_positions"),
            "alpha_top_n": snapshot.get("alpha_top_n"),
            "learning_mode_threshold": snapshot.get("learning_mode_threshold_trades"),
            "evolution_freeze": snapshot.get("evolution_freeze_until_trades"),
            "horizon_timeout_bars": snapshot.get("horizon_timeout_bars"),
            "drawdown_kill_pct": snapshot.get("drawdown_kill_pct"),
            "exploration_enabled": snapshot.get("exploration_enabled"),
            "bar_boundary_entry_only": snapshot.get("bar_boundary_entry_only"),
        }
    else:
        live_constants = {"note": "runtime_config_snapshot.json not found — run write_runtime_snapshot.py"}

    # Load grep assertions if they exist
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
    report_paths = sorted(ROOT.glob("docs/architecture/*trading*report*"))
    latest_report = str(report_paths[-1].relative_to(ROOT)) if report_paths else "none"

    # Open risks
    risks: list[str] = []
    if grep_status == "fail":
        risks.append(f"Grep assertions failing: {', '.join(failing_checks)}")
    if not snapshot_path.exists():
        risks.append("No runtime config snapshot — organism constants not verified")
    if organism_changed:
        risks.append(f"{len(organism_changed)} organism file(s) changed — require replay verification")

    # Generate markdown
    lines = [
        "# Live Audit Index",
        "",
        f"Generated: {timestamp}",
        f"SHA: `{short_sha}`",
        f"Branch: `{branch}`",
        "",
        "## Changed files",
        "",
        f"| Category | Count | Files |",
        f"|----------|-------|-------|",
        f"| Backend | {len(backend_changed)} | {', '.join(f'`{p}`' for p in backend_changed[:10]) or 'none'} |",
        f"| Organism | {len(organism_changed)} | {', '.join(f'`{p}`' for p in organism_changed[:10]) or 'none'} |",
        f"| Tests | {len(tests_changed)} | {', '.join(f'`{p}`' for p in tests_changed[:10]) or 'none'} |",
        f"| Docs | {len(docs_changed)} | {', '.join(f'`{p}`' for p in docs_changed[:10]) or 'none'} |",
        "",
        "## Live constants",
        "",
        "```json",
        json.dumps(live_constants, indent=2),
        "```",
        "",
        "## Reference paths",
        "",
        f"- Latest improve doc: `{latest_improve}`",
        f"- Latest trading report: `{latest_report}`",
        f"- Runtime snapshot: `artifacts/runtime_config_snapshot.json`",
        f"- Grep assertions: `artifacts/grep_assertions.json` (status: **{grep_status}**)",
        "",
        "## Open risks",
        "",
    ]
    if risks:
        for r in risks:
            lines.append(f"- {r}")
    else:
        lines.append("- None identified")

    lines.append("")

    out = ROOT / "docs" / "engineering" / "LIVE_AUDIT_INDEX.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    print(f"Audit index written to {out}")


if __name__ == "__main__":
    main()
