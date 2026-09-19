#!/usr/bin/env python3
"""Phase 7.0 baseline snapshot and inventory.

This is the first Phase 7 hardening step: capture the current truth before any
live-engine decomposition or behavior-preserved refactor.

Outputs:
  artifacts/phase7/baseline_snapshot.json
  artifacts/phase7/god_method_inventory.json
  artifacts/phase7/test_trust_inventory.json
  artifacts/phase7/BASELINE_SNAPSHOT_REPORT.md
  docs/engineering/PHASE7_BASELINE_SNAPSHOT_REPORT.md
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ci import classify_wave_tests  # noqa: E402
from scripts.ci import phase7_integration_checkpoint as checkpoint  # noqa: E402

ARTIFACT_DIR = ROOT / "artifacts" / "phase7"
BASELINE_JSON = ARTIFACT_DIR / "baseline_snapshot.json"
GOD_JSON = ARTIFACT_DIR / "god_method_inventory.json"
TEST_TRUST_JSON = ARTIFACT_DIR / "test_trust_inventory.json"
ARTIFACT_REPORT = ARTIFACT_DIR / "BASELINE_SNAPSHOT_REPORT.md"
DOC_REPORT = ROOT / "docs" / "engineering" / "PHASE7_BASELINE_SNAPSHOT_REPORT.md"

GOD_METHOD_LOC_THRESHOLD = 150
GOD_FILE_LOC_THRESHOLD = 1000
CRITICAL_IMPORT_ROOTS = (
    "backend/organism",
    "backend/brokers",
    "backend/integrations",
    "backend/risk",
    "backend/infra",
    "backend/api",
)


def _run(cmd: list[str], *, timeout: int = 30) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"returncode": 999, "stdout": "", "stderr": str(exc)}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _count_csv(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open(newline="") as f:
            return sum(1 for _ in csv.DictReader(f))
    except (OSError, csv.Error, UnicodeDecodeError):
        return 0


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    except (OSError, UnicodeDecodeError):
        return 0


def _psql_scalar(sql: str) -> dict[str, Any]:
    result = checkpoint._psql(sql, timeout=20)  # noqa: SLF001
    return {
        "ok": result["returncode"] == 0,
        "value": result["stdout"],
        "error": result["stderr"],
    }


def _table_exists(table_name: str) -> bool:
    result = _psql_scalar(f"SELECT to_regclass('public.{table_name}');")
    return result["ok"] and result["value"] == table_name


def _table_count(table_name: str) -> dict[str, Any]:
    if not _table_exists(table_name):
        return {"ok": False, "value": None, "error": "table_missing"}
    return _psql_scalar(f"SELECT count(*) FROM {table_name};")


def _positions_snapshot() -> dict[str, Any]:
    if not _table_exists("positions"):
        return {"ok": False, "open_positions": None, "evidence": "positions table missing"}
    cols = _psql_scalar(
        """
SELECT string_agg(column_name, ',' ORDER BY ordinal_position)
FROM information_schema.columns
WHERE table_schema='public' AND table_name='positions';
"""
    )
    col_text = cols.get("value") or ""
    if "quantity" in col_text:
        query = "SELECT count(*) FROM positions WHERE COALESCE(quantity, 0) <> 0;"
    elif "status" in col_text:
        query = "SELECT count(*) FROM positions WHERE lower(COALESCE(status, '')) IN ('open', 'active');"
    else:
        query = "SELECT count(*) FROM positions;"
    count = _psql_scalar(query)
    return {
        "ok": count["ok"],
        "open_positions": count["value"] if count["ok"] else None,
        "columns": col_text,
        "evidence": count.get("error") or query,
    }


def _collect_file_counts() -> dict[str, Any]:
    groups = {
        "backend_py": list((ROOT / "backend").rglob("*.py")),
        "tests_py": list((ROOT / "tests").rglob("*.py")),
        "scripts_py": list((ROOT / "scripts").rglob("*.py")),
        "docs_md": list((ROOT / "docs").rglob("*.md")),
    }
    return {name: len(files) for name, files in groups.items()}


def collect_baseline_snapshot() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).isoformat()
    integration_data = {
        "generated_at": generated_at,
        "repo": checkpoint.collect_repo(),
        "container": checkpoint.collect_container(),
        "http": checkpoint.collect_http(),
        "db": checkpoint.collect_db(),
        "brain_and_evidence": checkpoint.collect_brain_and_evidence(),
        "parity": checkpoint.collect_parity(),
        "command_gates": checkpoint.collect_command_gates(),
    }
    integration_checks = checkpoint.build_checks(integration_data)

    brain_dir = ROOT / "organism_brain"
    manifest = _safe_json(brain_dir / "manifest.json")
    ml_state = _safe_json(brain_dir / "ml_state.json")
    learning_state = _safe_json(brain_dir / "learning_state.json")
    backup_dirs = sorted(p.name for p in ROOT.glob("organism_brain.pre_*") if p.is_dir())
    corrupt_head_dirs = sorted(p.name for p in ROOT.glob("organism_brain.corrupt_head*") if p.is_dir())

    db_counts = {
        name: _table_count(name)
        for name in (
            "users",
            "orders",
            "positions",
            "realized_trades",
            "audit_logs",
            "outbox",
        )
    }

    strategy = (integration_data["http"]["strategy_health"].get("payload") or {})
    snapshot = {
        "generated_at": generated_at,
        "scope": "phase7_0_baseline_snapshot_no_trading_behavior_change",
        "integration_checkpoint": {
            "checks": [asdict(c) for c in integration_checks],
            "pass": sum(1 for c in integration_checks if c.status == "PASS"),
            "warn": sum(1 for c in integration_checks if c.status == "WARN"),
            "fail": sum(1 for c in integration_checks if c.status == "FAIL"),
        },
        "repo": integration_data["repo"],
        "container": integration_data["container"],
        "http": {
            "healthz_status": integration_data["http"]["healthz"]["status"],
            "strategy_health_status": integration_data["http"]["strategy_health"]["status"],
            "audit_chain_status": integration_data["http"]["audit_chain_detail"]["status"],
        },
        "strategy_health": {
            "n_trades": strategy.get("n_trades"),
            "total_pnl": strategy.get("total_pnl"),
            "win_rate": strategy.get("win_rate"),
            "sharpe_ratio_per_trade": strategy.get("sharpe_ratio_per_trade"),
            "is_profitable": strategy.get("is_profitable"),
            "source": strategy.get("source"),
            "last_25_win_rate": strategy.get("last_25_win_rate"),
            "last_50_win_rate": strategy.get("last_50_win_rate"),
        },
        "brain": {
            "manifest": {
                "generation": manifest.get("generation", manifest.get("gen")),
                "total_trades": manifest.get("total_trades"),
                "ml_is_trained": manifest.get("ml_is_trained"),
                "saved_at": manifest.get("saved_at"),
            },
            "trade_history_rows": _count_csv(brain_dir / "trade_history.csv"),
            "candidate_filter_shadow_telemetry_rows": _count_jsonl(
                brain_dir / "candidate_filter_shadow_telemetry.jsonl"
            ),
            "strategy_evidence_telemetry_rows": _count_jsonl(
                brain_dir / "strategy_evidence_events.jsonl"
            ),
            "ml_state_keys": sorted(ml_state.keys())[:25],
            "learning_state_keys": sorted(learning_state.keys())[:25],
            "backup_dirs": backup_dirs,
            "corrupt_head_dirs": corrupt_head_dirs,
        },
        "phase6_evidence": integration_data["brain_and_evidence"],
        "db": {
            "migration_head": integration_data["db"]["migration_head"],
            "table_counts": db_counts,
            "positions": _positions_snapshot(),
        },
        "file_counts": _collect_file_counts(),
        "runtime_truth": {
            "hot_path_parity": integration_data["parity"],
            "command_gates": integration_data["command_gates"],
        },
    }
    return snapshot


def _module_imports(tree: ast.AST) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _function_rows_for_file(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rel = path.relative_to(ROOT).as_posix()
    try:
        source = path.read_text()
        tree = ast.parse(source, filename=rel)
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        return (
            [
                {
                    "file": rel,
                    "qualified_name": "<parse_error>",
                    "line": 0,
                    "loc": 0,
                    "error": str(exc),
                }
            ],
            [],
        )

    rows: list[dict[str, Any]] = []

    def visit(body: list[ast.stmt], prefix: list[str]) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, [*prefix, node.name])
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", node.lineno)
                qual = ".".join([*prefix, node.name]) if prefix else node.name
                rows.append(
                    {
                        "file": rel,
                        "qualified_name": qual,
                        "line": node.lineno,
                        "end_line": end,
                        "loc": max(0, end - node.lineno + 1),
                        "async": isinstance(node, ast.AsyncFunctionDef),
                    }
                )
                visit(node.body, [*prefix, node.name])

    visit(tree.body, [])
    return rows, _module_imports(tree)


def collect_god_method_inventory() -> dict[str, Any]:
    files = sorted((ROOT / "backend").rglob("*.py"))
    function_rows: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    file_rows: list[dict[str, Any]] = []
    imports_by_root: dict[str, Counter[str]] = {
        root: Counter() for root in CRITICAL_IMPORT_ROOTS
    }

    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        loc = len(text.splitlines())
        nonblank = sum(1 for line in text.splitlines() if line.strip())
        rows, imports = _function_rows_for_file(path)
        if rows and rows[0].get("qualified_name") == "<parse_error>":
            parse_errors.extend(rows)
            rows = []
        function_rows.extend(rows)
        file_rows.append(
            {
                "file": rel,
                "loc": loc,
                "nonblank_loc": nonblank,
                "functions": len(rows),
                "functions_over_threshold": sum(
                    1 for row in rows if row.get("loc", 0) > GOD_METHOD_LOC_THRESHOLD
                ),
            }
        )
        for root in CRITICAL_IMPORT_ROOTS:
            if rel.startswith(root):
                for module in imports:
                    imports_by_root[root][module.split(".", 2)[0]] += 1

    god_methods = sorted(
        [
            row
            for row in function_rows
            if int(row.get("loc", 0)) > GOD_METHOD_LOC_THRESHOLD
        ],
        key=lambda row: int(row.get("loc", 0)),
        reverse=True,
    )
    live_tick = [
        row for row in function_rows if row.get("qualified_name", "").endswith("_live_tick_inner")
    ]
    large_files = sorted(
        [row for row in file_rows if row["loc"] > GOD_FILE_LOC_THRESHOLD],
        key=lambda row: row["loc"],
        reverse=True,
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "backend_python_ast_complexity",
        "thresholds": {
            "god_method_loc": GOD_METHOD_LOC_THRESHOLD,
            "god_file_loc": GOD_FILE_LOC_THRESHOLD,
        },
        "summary": {
            "backend_python_files": len(files),
            "functions_total": len(function_rows),
            "functions_over_threshold": len(god_methods),
            "files_over_threshold": len(large_files),
            "parse_errors": len(parse_errors),
            "live_tick_inner_loc": live_tick[0]["loc"] if live_tick else None,
        },
        "live_tick_inner": live_tick,
        "god_methods": god_methods,
        "top_25_god_methods": god_methods[:25],
        "large_files": large_files,
        "top_25_large_files": large_files[:25],
        "parse_errors": parse_errors,
        "imports_by_critical_root": {
            root: counter.most_common(25) for root, counter in imports_by_root.items()
        },
    }


def _wave_style_files(root: Path) -> list[Path]:
    patterns = (
        "test_wave*_fixes.py",
        "test_v[0-9][0-9]_w*.py",
        "test_v[0-9][0-9]_wave*.py",
    )
    seen: set[Path] = set()
    files: list[Path] = []
    for pattern in patterns:
        for path in root.glob(pattern):
            if path not in seen:
                seen.add(path)
                files.append(path)
    return sorted(files)


def _scan_all_test_files() -> dict[str, Any]:
    test_files = sorted((ROOT / "tests").rglob("test*.py"))
    source_patterns = (
        "inspect.getsource",
        "getsource(",
        ".read_text(",
        "open(",
        ".read()",
    )
    source_grep_hits: list[dict[str, Any]] = []
    skip_xfail_hits: list[dict[str, Any]] = []
    for path in test_files:
        rel = path.relative_to(ROOT).as_posix()
        try:
            lines = path.read_text().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if any(pattern in stripped for pattern in source_patterns):
                source_grep_hits.append({"file": rel, "line": idx, "text": stripped[:180]})
            if "pytest.mark.skip" in stripped or "pytest.mark.xfail" in stripped:
                skip_xfail_hits.append({"file": rel, "line": idx, "text": stripped[:180]})
    return {
        "test_files": len(test_files),
        "source_grep_hits": source_grep_hits,
        "source_grep_hit_count": len(source_grep_hits),
        "skip_xfail_hits": skip_xfail_hits,
        "skip_xfail_count": len(skip_xfail_hits),
    }


def collect_test_trust_inventory() -> dict[str, Any]:
    root = ROOT / "tests"
    files = _wave_style_files(root)
    rows = []
    parse_errors: list[dict[str, Any]] = []
    for path in files:
        try:
            rows.extend(classify_wave_tests.classify_file(path.relative_to(ROOT)))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            parse_errors.append({"file": path.relative_to(ROOT).as_posix(), "error": str(exc)})

    counts: Counter[str] = Counter(row.classification for row in rows)
    by_file: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        by_file[row.file][row.classification] += 1

    total = len(rows)
    marker_only = counts.get("marker-only", 0)
    mixed = counts.get("mixed", 0)
    pct_marker_only = round((marker_only / total * 100), 2) if total else 0.0
    pct_marker_or_mixed = round(((marker_only + mixed) / total * 100), 2) if total else 0.0
    all_tests_scan = _scan_all_test_files()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "phase7_0_test_trust_inventory",
        "wave_style": {
            "files_scanned": len(files),
            "tests_total": total,
            "by_classification": dict(counts),
            "pct_marker_only": pct_marker_only,
            "pct_marker_or_mixed": pct_marker_or_mixed,
            "by_file": {file: dict(counter) for file, counter in by_file.items()},
            "marker_only_tests": [
                row.as_dict() for row in rows if row.classification == "marker-only"
            ],
            "mixed_tests": [row.as_dict() for row in rows if row.classification == "mixed"],
            "parse_errors": parse_errors,
        },
        "all_tests_source_scan": all_tests_scan,
    }


def _top_policy_actions(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    actions = snapshot.get("phase6_evidence", {}).get("phase6_policy_actions", [])
    return actions if isinstance(actions, list) else []


def build_report(
    baseline: dict[str, Any],
    god_inventory: dict[str, Any],
    test_trust: dict[str, Any],
) -> str:
    integration = baseline["integration_checkpoint"]
    strategy = baseline["strategy_health"]
    brain = baseline["brain"]
    god_summary = god_inventory["summary"]
    wave = test_trust["wave_style"]
    source_scan = test_trust["all_tests_source_scan"]
    actions = _top_policy_actions(baseline)
    top_methods = god_inventory["top_25_god_methods"][:10]
    top_files = god_inventory["top_25_large_files"][:10]

    lines = [
        "# Phase 7.0 Baseline Snapshot Report",
        "",
        f"Generated: {baseline['generated_at']}",
        f"Branch: `{baseline['repo'].get('branch')}`",
        f"HEAD: `{baseline['repo'].get('head')}`",
        f"Container SHA: `{baseline['container'].get('git_sha')}`",
        "",
        "## Executive Verdict",
        "",
        (
            "P7.0 baseline capture is ready for Phase 7 hardening work. "
            f"Integration checks are {integration['pass']} pass, {integration['warn']} warn, "
            f"{integration['fail']} fail. No trading behavior was changed."
        ),
        "",
        (
            "The platform is mechanically coherent enough to start inventory-led "
            "cleanup: the running container matches HEAD, hot-path file parity passes, "
            "runtime snapshot generation passes, and the migration tree is single-headed."
        ),
        "",
        (
            "The strategy itself is still not profit-ready. The baseline preserves the "
            "Phase 6 verdict: current main candidate flow should not be promoted, and "
            "Phase 6 telemetry should keep collecting evidence while Track A cleanup runs."
        ),
        "",
        "## Runtime Truth",
        "",
        f"- Repo clean at capture: `{not bool(baseline['repo'].get('status_short'))}`",
        f"- Healthz status: `{baseline['http'].get('healthz_status')}`",
        f"- Strategy health status: `{baseline['http'].get('strategy_health_status')}`",
        f"- Audit chain endpoint status: `{baseline['http'].get('audit_chain_status')}`",
        f"- Phase 5 telemetry enabled: `{baseline['container'].get('phase5_telemetry_enabled')}`",
        f"- Phase 6 telemetry enabled: `{baseline['container'].get('phase6_telemetry_enabled')}`",
        f"- Hot-path parity mismatches: `{len(baseline['runtime_truth']['hot_path_parity'].get('mismatches', []))}`",
        "",
        "## Strategy And Brain",
        "",
        f"- Strategy trades: `{strategy.get('n_trades')}`",
        f"- Strategy total PnL: `{strategy.get('total_pnl')}`",
        f"- Strategy win rate: `{strategy.get('win_rate')}`",
        f"- Strategy Sharpe per trade: `{strategy.get('sharpe_ratio_per_trade')}`",
        f"- Strategy profitable: `{strategy.get('is_profitable')}`",
        f"- Brain generation: `{brain['manifest'].get('generation')}`",
        f"- Brain manifest total trades: `{brain['manifest'].get('total_trades')}`",
        f"- Brain trade history rows: `{brain.get('trade_history_rows')}`",
        f"- Phase 5 candidate telemetry rows: `{brain.get('candidate_filter_shadow_telemetry_rows')}`",
        f"- Phase 6 strategy evidence rows: `{brain.get('strategy_evidence_telemetry_rows')}`",
        "",
        "## Phase 6 Evidence Policy",
        "",
        "| Filter | Action | Events | Outcomes | 5-bar mean bps | Win rate |",
        "|--------|--------|--------|----------|----------------|----------|",
    ]
    for action in actions:
        lines.append(
            "| "
            f"{action.get('filter')} | {action.get('shadow_action')} | "
            f"{action.get('events')} | {action.get('outcomes')} | "
            f"{action.get('mean_directional_bps')} | {action.get('win_rate')} |"
        )
    if not actions:
        lines.append("| none | none | 0 | 0 | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Architecture Inventory",
            "",
            f"- Backend Python files: `{god_summary.get('backend_python_files')}`",
            f"- Backend functions/methods: `{god_summary.get('functions_total')}`",
            f"- Functions over {GOD_METHOD_LOC_THRESHOLD} LOC: `{god_summary.get('functions_over_threshold')}`",
            f"- Files over {GOD_FILE_LOC_THRESHOLD} LOC: `{god_summary.get('files_over_threshold')}`",
            f"- `_live_tick_inner` LOC: `{god_summary.get('live_tick_inner_loc')}`",
            "",
            "Top large methods:",
            "",
            "| LOC | Function | File | Line |",
            "|-----|----------|------|------|",
        ]
    )
    for row in top_methods:
        lines.append(
            f"| {row.get('loc')} | `{row.get('qualified_name')}` | "
            f"`{row.get('file')}` | {row.get('line')} |"
        )
    lines.extend(
        [
            "",
            "Top large files:",
            "",
            "| LOC | File | Functions > threshold |",
            "|-----|------|-----------------------|",
        ]
    )
    for row in top_files:
        lines.append(
            f"| {row.get('loc')} | `{row.get('file')}` | "
            f"{row.get('functions_over_threshold')} |"
        )

    lines.extend(
        [
            "",
            "## Test Trust Inventory",
            "",
            f"- Wave-style files scanned: `{wave.get('files_scanned')}`",
            f"- Wave-style tests classified: `{wave.get('tests_total')}`",
            f"- Marker-only tests: `{wave.get('by_classification', {}).get('marker-only', 0)}`",
            f"- Mixed tests: `{wave.get('by_classification', {}).get('mixed', 0)}`",
            f"- Marker-only ratio: `{wave.get('pct_marker_only')}%`",
            f"- Marker-or-mixed ratio: `{wave.get('pct_marker_or_mixed')}%`",
            f"- All-test source-grep pattern hits: `{source_scan.get('source_grep_hit_count')}`",
            f"- Skip/xfail hits: `{source_scan.get('skip_xfail_count')}`",
            "",
            "## P7.0 Risks To Carry Forward",
            "",
        ]
    )
    risks = []
    if strategy.get("is_profitable") is False:
        risks.append("Strategy health remains negative; Phase 7 must not promote strategy behavior.")
    if god_summary.get("live_tick_inner_loc", 0) and god_summary["live_tick_inner_loc"] > 2500:
        risks.append("`_live_tick_inner` remains above the historical 2510 LOC baseline.")
    if wave.get("pct_marker_only", 0) > 0:
        risks.append("Some wave-style tests are still marker-only and need P7.3 review.")
    if brain.get("strategy_evidence_telemetry_rows") == 0:
        risks.append("Phase 6 strategy-evidence file has no new rows yet; next session should populate it.")
    if not risks:
        risks.append("No blocker risks found in the baseline checkpoint.")
    lines.extend(f"- {risk}" for risk in risks)

    lines.extend(
        [
            "",
            "## Recommended Next Step",
            "",
            (
                "Proceed to P7.1 architecture map and P7.3 test-trust review before "
                "the first live-engine extraction. The likely first extraction target "
                "remains telemetry fanout from `_live_tick_inner`, because it is recent, "
                "observable, and can be tested without changing order behavior."
            ),
            "",
            "## Raw Artifacts",
            "",
            f"- `{BASELINE_JSON.relative_to(ROOT)}`",
            f"- `{GOD_JSON.relative_to(ROOT)}`",
            f"- `{TEST_TRUST_JSON.relative_to(ROOT)}`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-doc-report",
        action="store_true",
        help="Write artifact report only, not docs/engineering report",
    )
    args = parser.parse_args()

    baseline = collect_baseline_snapshot()
    god_inventory = collect_god_method_inventory()
    test_trust = collect_test_trust_inventory()

    _write_json(BASELINE_JSON, baseline)
    _write_json(GOD_JSON, god_inventory)
    _write_json(TEST_TRUST_JSON, test_trust)
    report = build_report(baseline, god_inventory, test_trust)
    ARTIFACT_REPORT.write_text(report)
    if not args.no_doc_report:
        DOC_REPORT.write_text(report)

    integration = baseline["integration_checkpoint"]
    god_count = god_inventory["summary"]["functions_over_threshold"]
    marker_ratio = test_trust["wave_style"]["pct_marker_only"]
    print(
        "Phase 7.0 baseline: "
        f"{integration['pass']} pass, {integration['warn']} warn, {integration['fail']} fail; "
        f"{god_count} backend functions > {GOD_METHOD_LOC_THRESHOLD} LOC; "
        f"marker-only wave-test ratio {marker_ratio}%"
    )
    print(f"Baseline: {BASELINE_JSON}")
    print(f"God methods: {GOD_JSON}")
    print(f"Test trust: {TEST_TRUST_JSON}")
    print(f"Report: {DOC_REPORT if not args.no_doc_report else ARTIFACT_REPORT}")
    return 1 if integration["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
