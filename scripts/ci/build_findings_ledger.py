"""V12 W77 (EXT-9): build the consolidated findings ledger.

External auditor finding: V1-V11 deferral state lives in prose
across multiple synthesis docs and per-track reports — not
machine-readable, hard to programmatically verify completeness.

This script:

1. Parses ``artifacts/audit/MASTER_AUDIT_SYNTHESIS_v{8..11}.md``
   for finding IDs in the standard markdown-table format.
2. Merges with ``artifacts/audit/v12/v12_state.json`` (the V12-era
   closures, which are the authoritative source for V11→V12
   transitions).
3. Writes ``artifacts/audit/findings_ledger.json`` (machine-
   readable) and ``artifacts/audit/findings_ledger_v12.md``
   (human-readable rollup).

V2-V7 findings are not parsed (those rounds used a less consistent
table format); they are tracked in the legacy
``FINDINGS_LEDGER.md`` and referenced by ID where they reappear in
later synthesis documents.

Usage:
    python scripts/ci/build_findings_ledger.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = REPO_ROOT / "artifacts" / "audit"
V12_STATE = AUDIT_DIR / "v12" / "v12_state.json"
LEDGER_JSON = AUDIT_DIR / "findings_ledger.json"
LEDGER_MD = AUDIT_DIR / "findings_ledger_v12.md"


# Match a markdown table row whose first cell is an ID like
# ``DD5-2``, ``AA4-1``, ``HH3-N-1``, ``W3-G1``, ``BB5-F4``, etc.
_ID_RE = re.compile(r"^[A-Z]{1,4}\d?(?:-[A-Z0-9]+)+$")
_TABLE_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|")


def _parse_synthesis(path: Path) -> list[dict]:
    """Parse a single MASTER_AUDIT_SYNTHESIS_vN.md file for findings.

    Heuristics: look for table rows whose first cell looks like a
    finding ID.  Capture the four pipe-separated columns:
    ``| ID | Track | Summary | Wave |``.

    Returns a list of dicts ``{id, track, summary, wave, version}``.
    """
    version_match = re.search(r"_v(\d+)\.md$", path.name)
    version = f"v{version_match.group(1)}" if version_match else "unknown"
    out: list[dict] = []
    current_severity: str | None = None
    for line in path.read_text().splitlines():
        # Track current severity context from headers.
        if re.match(r"^### (Critical|High|Medium|Low)", line):
            current_severity = line.split()[1].lower().rstrip("()")
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        ident = cells[0].rstrip("*").strip()
        if not _ID_RE.match(ident):
            continue
        out.append({
            "id": ident,
            "version": version,
            "track": cells[1],
            "summary": cells[2],
            "wave_target_raw": cells[3],
            "severity": current_severity or "unknown",
        })
    return out


def _load_v12_state() -> tuple[list[dict], list[dict]]:
    """Return (v12_findings, v11_closures_audited_in_v12).  Both lists
    contain dicts with at least ``id``, ``status``, and
    ``behavioral_test_path``."""
    state = json.loads(V12_STATE.read_text())
    return state.get("findings", []), state.get(
        "v11_closures_audited_in_v12", []
    )


def build_ledger() -> dict:
    # Parse synthesis docs.
    parsed: dict[str, dict] = OrderedDict()
    for v in (8, 9, 10, 11):
        path = AUDIT_DIR / f"MASTER_AUDIT_SYNTHESIS_v{v}.md"
        if not path.is_file():
            continue
        for finding in _parse_synthesis(path):
            # Use the most recent occurrence for shared ID across versions.
            parsed[finding["id"]] = finding

    # Overlay v12 state closures + per-finding metadata.
    v12_findings, v11_audited = _load_v12_state()
    v12_overlay: dict[str, dict] = {}
    for f in v12_findings:
        v12_overlay[f["id"]] = f
    v11_audit_overlay: dict[str, dict] = {}
    for f in v11_audited:
        v11_audit_overlay[f["id"]] = f

    # Merge into a single ledger.
    merged: list[dict] = []
    seen_ids: set[str] = set()
    # First, every parsed finding (V8-V11).
    for ident, parsed_data in parsed.items():
        record = {
            "id": ident,
            "first_appearance_version": parsed_data["version"],
            "track": parsed_data["track"],
            "summary": parsed_data["summary"],
            "severity_at_first_appearance": parsed_data["severity"],
            "wave_target_raw": parsed_data["wave_target_raw"],
            "status": "open",      # default; overlays below.
            "wave_closed": None,
            "behavioral_test_path": None,
            "deferral_reason": None,
            "v12_audit": None,
        }
        # Apply V12-state closure overlay.
        if ident in v12_overlay:
            ov = v12_overlay[ident]
            record["status"] = ov["status"]
            record["wave_closed"] = ov.get("wave_closed")
            record["behavioral_test_path"] = ov.get("behavioral_test_path")
            if ov["status"] == "deferred":
                record["deferral_reason"] = ov.get("notes")
        elif ident in v11_audit_overlay:
            ov = v11_audit_overlay[ident]
            record["status"] = "closed"
            record["wave_closed"] = ov.get("wave_closed")
            record["behavioral_test_path"] = ov.get("behavioral_test_path")
            record["v12_audit"] = ov.get("v12_w73_audit")
        merged.append(record)
        seen_ids.add(ident)

    # Second, V12-only findings (EXT-* and any V12-introduced IDs).
    for f in v12_findings:
        if f["id"] in seen_ids:
            continue
        merged.append({
            "id": f["id"],
            "first_appearance_version": "v12",
            "track": f.get("from", "v12"),
            "summary": f["title"],
            "severity_at_first_appearance": f["severity"],
            "wave_target_raw": str(f.get("wave_target") or ""),
            "status": f["status"],
            "wave_closed": f.get("wave_closed"),
            "behavioral_test_path": f.get("behavioral_test_path"),
            "deferral_reason": f.get("notes") if f["status"] == "deferred" else None,
            "v12_audit": None,
        })
        seen_ids.add(f["id"])

    # Third, V11 closures audited in V12 that aren't in synthesis tables
    # (e.g. BB5-F4 closed in wave-67 prior to V12 audit but not table-listed).
    for f in v11_audited:
        if f["id"] in seen_ids:
            continue
        merged.append({
            "id": f["id"],
            "first_appearance_version": "v11",
            "track": f.get("from", "v11"),
            "summary": f["title"],
            "severity_at_first_appearance": f["severity"],
            "wave_target_raw": str(f.get("wave_closed") or ""),
            "status": "closed",
            "wave_closed": f.get("wave_closed"),
            "behavioral_test_path": f.get("behavioral_test_path"),
            "deferral_reason": None,
            "v12_audit": f.get("v12_w73_audit"),
        })
        seen_ids.add(f["id"])

    # Aggregate stats.
    by_status: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for r in merged:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        sev = r["severity_at_first_appearance"]
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {
        "schema_version": 1,
        "captured_at_branch_head": _git_head(),
        "n_findings": len(merged),
        "by_status": by_status,
        "by_severity": by_severity,
        "findings": merged,
    }


def _git_head() -> str:
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def write_ledger_md(ledger: dict, path: Path) -> None:
    """Render a human-readable rollup."""
    lines: list[str] = []
    lines.append("# Findings Ledger (V8-V12, machine-readable mirror)\n")
    lines.append(
        "Generated by `scripts/ci/build_findings_ledger.py` from "
        "V8-V11 synthesis docs + `artifacts/audit/v12/v12_state.json`.\n"
    )
    lines.append(f"Branch HEAD: `{ledger['captured_at_branch_head'][:12]}`\n")
    lines.append("## Summary\n")
    lines.append(f"- Total findings: **{ledger['n_findings']}**")
    for status, n in sorted(ledger["by_status"].items()):
        lines.append(f"- {status}: {n}")
    lines.append("")
    lines.append("## Findings\n")
    lines.append("| ID | Version | Severity | Status | Wave Closed | Behavioral Test | Summary |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in sorted(ledger["findings"], key=lambda x: (x["status"] != "open", x["id"])):
        lines.append(
            f"| `{r['id']}` | {r['first_appearance_version']} | "
            f"{r['severity_at_first_appearance']} | {r['status']} | "
            f"{r.get('wave_closed') or '—'} | "
            f"{r.get('behavioral_test_path') or '—'} | "
            f"{r['summary'][:120]} |"
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    # V12 W80 (post-audit cleanup): explicit output flags so tests can
    # redirect into a tmp dir.  Pre-W80 the builder always wrote into
    # ``artifacts/audit/``, which meant ``test_v12_w77_findings_ledger.py``
    # mutated tracked files every time it ran (auditor caught this).
    parser.add_argument(
        "--out-json", default=str(LEDGER_JSON),
        help="JSON output path (default: artifacts/audit/findings_ledger.json)",
    )
    parser.add_argument(
        "--out-md", default=str(LEDGER_MD),
        help="Markdown output path (default: artifacts/audit/findings_ledger_v12.md)",
    )
    args = parser.parse_args()

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)

    ledger = build_ledger()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    write_ledger_md(ledger, out_md)
    print(f"Wrote {out_json} ({ledger['n_findings']} findings)")
    print(f"Wrote {out_md}")
    print(f"By status: {ledger['by_status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
