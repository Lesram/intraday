#!/usr/bin/env python3
"""Phase 7 integration checkpoint.

Read-only validation for the paper platform after Phase 6 and before Phase 7
refactors.  It answers one operational question:

    Is the running paper system coherently integrated with the current branch,
    runtime config, brain state, DB state, and Phase 6 evidence loop?

Outputs:
  artifacts/phase7/integration_validation.json
  artifacts/phase7/INTEGRATION_VALIDATION_REPORT.md

Auth for protected API probes is optional and read from environment only:
  PHASE7_AUTH_TOKEN
  PHASE7_AUTH_USERNAME / PHASE7_AUTH_PASSWORD
  V13_AUTH_TOKEN
  V13_AUTH_USERNAME / V13_AUTH_PASSWORD
  INTRA_API_USER / INTRA_API_PASSWORD
For the default localhost paper runtime only, the checkpoint falls back to the
same dev-paper admin credentials used by ``phase7_security_sanity.py``.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "artifacts" / "phase7"
REPORT_PATH = ARTIFACT_DIR / "INTEGRATION_VALIDATION_REPORT.md"
JSON_PATH = ARTIFACT_DIR / "integration_validation.json"

API_BASE = os.getenv("PHASE7_API_BASE", "http://localhost:8000")
API_CONTAINER = os.getenv("PHASE7_API_CONTAINER", "intra-api-1")
DB_CONTAINER = os.getenv("PHASE7_DB_CONTAINER", "trading_platform_db_paper")
DB_USER = os.getenv("PHASE7_DB_USER", "trading")
DB_NAME = os.getenv("PHASE7_DB_NAME", "algotrading")
TIMEOUT = float(os.getenv("PHASE7_PROBE_TIMEOUT_SEC", "8"))

HOT_PATH_FILES = (
    "backend/organism/live_engine.py",
    "backend/organism/brain_persistence.py",
    "backend/organism/candidate_shadow_telemetry.py",
    "backend/infra/security.py",
    "backend/api/lifespan.py",
    "backend/api/routes/auth.py",
    "backend/api/routes/orders.py",
    "backend/api/routes/strategy_health.py",
    "backend/api/routes/data_integrity_health.py",
    "backend/api/routes_setup.py",
    "docker-compose.paper.yml",
)

SENSITIVE_OUTPUT_KEYS = (
    "ALPACA_API_KEY_ID",
    "ALPACA_API_SECRET_KEY",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "APCA_API_KEY_ID",
    "APCA_API_SECRET_KEY",
    "JWT_SECRET",
    "JWT_SECRET_KEY",
    "SECURITY_JWT_SECRET",
    "REDIS_PASSWORD",
    "REDIS_URL",
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    "GRAFANA_ADMIN_PASSWORD",
    "PHASE7_AUTH_TOKEN",
    "PHASE7_AUTH_PASSWORD",
    "PHASE7_LOCAL_DEFAULT_AUTH_PASSWORD",
    "V13_AUTH_TOKEN",
    "V13_AUTH_PASSWORD",
    "INTRA_API_PASSWORD",
)

_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?m)^(\s*\"?(?:"
    + "|".join(re.escape(key) for key in SENSITIVE_OUTPUT_KEYS)
    + r")(?:\s*[:=]\s*))([^\",\n\r]+)"
)

_AUTH_HEADERS_CACHE: tuple[dict[str, str], str | None] | None = None


def _redact_sensitive_output(text: str) -> str:
    """Redact secret-bearing env/config values before writing artifacts."""
    if not text:
        return text
    return _SENSITIVE_ASSIGNMENT_RE.sub(r"\1<REDACTED>", text)


@dataclass
class Check:
    name: str
    status: str
    evidence: str
    severity: str = "info"


def _run(cmd: list[str], *, timeout: int = 15) -> dict[str, Any]:
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
            "stdout": _redact_sensitive_output(proc.stdout.strip()),
            "stderr": _redact_sensitive_output(proc.stderr.strip()),
        }
    except Exception as exc:  # noqa: BLE001
        return {"returncode": 999, "stdout": "", "stderr": str(exc)}


def _git(*args: str) -> str:
    result = _run(["git", *args], timeout=10)
    return result["stdout"] if result["returncode"] == 0 else ""


def _docker_exec(container: str, shell_cmd: str, *, timeout: int = 15) -> dict[str, Any]:
    return _run(["docker", "exec", container, "sh", "-lc", shell_cmd], timeout=timeout)


def _psql(sql: str, *, timeout: int = 15) -> dict[str, Any]:
    return _run(
        [
            "docker",
            "exec",
            DB_CONTAINER,
            "psql",
            "-U",
            DB_USER,
            "-d",
            DB_NAME,
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
            "-c",
            sql,
        ],
        timeout=timeout,
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _host_file_sha(rel_path: str) -> str | None:
    path = ROOT / rel_path
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError:
        return None


def _container_file_sha(rel_path: str) -> str | None:
    try:
        data = subprocess.check_output(
            ["docker", "exec", API_CONTAINER, "cat", f"/app/{rel_path}"],
            cwd=ROOT,
            timeout=10,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return _sha256_bytes(data)


def _json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _csv_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open(newline="") as f:
            return sum(1 for _ in csv.DictReader(f))
    except (OSError, csv.Error, UnicodeDecodeError):
        return 0


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    except (OSError, UnicodeDecodeError):
        return 0


def _local_paper_default_auth() -> tuple[str | None, str | None]:
    """Return dev-paper credentials only for the localhost paper API target."""
    if not (
        API_BASE.startswith("http://localhost:")
        or API_BASE.startswith("http://127.0.0.1:")
        or API_BASE.startswith("http://[::1]:")
    ):
        return None, None
    return (
        os.getenv("PHASE7_LOCAL_DEFAULT_AUTH_USERNAME", "admin@example.com"),
        os.getenv("PHASE7_LOCAL_DEFAULT_AUTH_PASSWORD", "admin123"),
    )


def _auth_payload() -> tuple[dict[str, str], str | None]:
    global _AUTH_HEADERS_CACHE
    if _AUTH_HEADERS_CACHE is not None:
        return _AUTH_HEADERS_CACHE

    token = os.getenv("PHASE7_AUTH_TOKEN") or os.getenv("V13_AUTH_TOKEN")
    if token:
        _AUTH_HEADERS_CACHE = ({"Authorization": f"Bearer {token}"}, None)
        return _AUTH_HEADERS_CACHE

    username = (
        os.getenv("PHASE7_AUTH_USERNAME")
        or os.getenv("V13_AUTH_USERNAME")
        or os.getenv("INTRA_API_USER")
    )
    password = (
        os.getenv("PHASE7_AUTH_PASSWORD")
        or os.getenv("V13_AUTH_PASSWORD")
        or os.getenv("INTRA_API_PASSWORD")
    )
    if not username or not password:
        default_username, default_password = _local_paper_default_auth()
        username = username or default_username
        password = password or default_password
    if not username or not password:
        _AUTH_HEADERS_CACHE = ({}, "auth env not set")
        return _AUTH_HEADERS_CACHE

    status, payload, raw = _http_post_json(
        "/api/v1/auth/login",
        {"username": username, "password": password},
    )
    if status != 200 or not isinstance(payload, dict):
        _AUTH_HEADERS_CACHE = ({}, f"login failed status={status} body={raw[:120]}")
        return _AUTH_HEADERS_CACHE
    access_token = payload.get("access_token")
    if not access_token:
        _AUTH_HEADERS_CACHE = ({}, "login response missing access_token")
        return _AUTH_HEADERS_CACHE
    _AUTH_HEADERS_CACHE = ({"Authorization": f"Bearer {access_token}"}, None)
    return _AUTH_HEADERS_CACHE


def _http_post_json(path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | None, str]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{API_BASE.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return _open_json(req)


def _http_get_json(path: str, *, authenticated: bool = False) -> tuple[int, dict[str, Any] | None, str]:
    headers: dict[str, str] = {}
    if authenticated:
        auth_headers, auth_error = _auth_payload()
        if auth_error:
            return 0, None, auth_error
        headers.update(auth_headers)
    req = urllib.request.Request(f"{API_BASE.rstrip('/')}{path}", headers=headers)
    return _open_json(req)


def _open_json(req: urllib.request.Request) -> tuple[int, dict[str, Any] | None, str]:
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = None
            return resp.status, payload if isinstance(payload, dict) else None, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, None, raw
    except Exception as exc:  # noqa: BLE001
        return 0, None, str(exc)


def collect_repo() -> dict[str, Any]:
    return {
        "branch": _git("branch", "--show-current"),
        "head": _git("rev-parse", "HEAD"),
        "head_short": _git("rev-parse", "--short", "HEAD"),
        "status_short": _git("status", "--short"),
        "upstream": _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"),
    }


def collect_container() -> dict[str, Any]:
    ps = _run(
        [
            "docker",
            "ps",
            "--filter",
            f"name={API_CONTAINER}",
            "--format",
            "{{.Names}}|{{.Status}}|{{.Image}}",
        ],
        timeout=10,
    )
    env = _docker_exec(API_CONTAINER, "env", timeout=10)
    env_map: dict[str, str] = {}
    if env["returncode"] == 0:
        for line in env["stdout"].splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                env_map[key] = value
    return {
        "docker_ps": ps,
        "git_sha": env_map.get("GIT_SHA"),
        "phase5_telemetry_enabled": env_map.get(
            "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED"
        ),
        "phase5_telemetry_path": env_map.get(
            "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH"
        ),
        "phase6_telemetry_enabled": env_map.get(
            "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED"
        ),
        "phase6_telemetry_path": env_map.get(
            "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_PATH"
        ),
        "exploration_enabled": env_map.get("ORGANISM_EXPLORATION_ENABLED"),
        "build_time": env_map.get("BUILD_TIME"),
        "image_sha": env_map.get("IMAGE_SHA"),
        "kill_switches": {
            "ORGANISM_DRAWDOWN_KILL_PCT": env_map.get("ORGANISM_DRAWDOWN_KILL_PCT"),
            "ORGANISM_MAX_DAILY_LOSS": env_map.get("ORGANISM_MAX_DAILY_LOSS"),
            "ORGANISM_MAX_NOTIONAL": env_map.get("ORGANISM_MAX_NOTIONAL"),
        },
    }


def collect_http() -> dict[str, Any]:
    healthz_status, healthz_payload, healthz_raw = _http_get_json("/healthz")
    strategy_status, strategy_payload, strategy_raw = _http_get_json(
        "/api/v1/health/strategy",
        authenticated=True,
    )
    audit_status, audit_payload, audit_raw = _http_get_json(
        "/api/v1/audit/chain-detail",
        authenticated=True,
    )
    deploy_status, deploy_payload, deploy_raw = _http_get_json(
        "/api/v1/health/deploy",
        authenticated=True,
    )
    integrity_status, integrity_payload, integrity_raw = _http_get_json(
        "/api/v1/health/data-integrity",
        authenticated=True,
    )
    return {
        "healthz": {
            "status": healthz_status,
            "payload": healthz_payload,
            "raw": healthz_raw[:500],
        },
        "strategy_health": {
            "status": strategy_status,
            "payload": strategy_payload,
            "raw": strategy_raw[:500],
        },
        "audit_chain_detail": {
            "status": audit_status,
            "payload": audit_payload,
            "raw": audit_raw[:500],
        },
        "deploy_health": {
            "status": deploy_status,
            "payload": deploy_payload,
            "raw": deploy_raw[:500],
        },
        "data_integrity": {
            "status": integrity_status,
            "payload": integrity_payload,
            "raw": integrity_raw[:500],
        },
    }


def collect_db() -> dict[str, Any]:
    queries = {
        "migration_head": "SELECT version_num FROM alembic_version;",
        "audit_log_columns": """
SELECT string_agg(column_name, ',' ORDER BY ordinal_position)
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'audit_logs';
""",
        "realized_trades_count": "SELECT count(*) FROM realized_trades;",
        "outbox_summary": """
SELECT count(*)::text || '|' || COALESCE(MIN(created_at)::text, '') || '|' || COALESCE(MAX(created_at)::text, '')
FROM outbox_events;
""",
        "open_positions": "SELECT count(*) FROM positions WHERE qty <> 0;",
        "positions_by_symbol": """
SELECT COALESCE(string_agg(symbol || ':' || qty::text, ',' ORDER BY symbol), '')
FROM positions
WHERE qty <> 0;
""",
        "orders_by_status": """
SELECT COALESCE(string_agg(status || ':' || n::text, ',' ORDER BY status), '')
FROM (
    SELECT status, count(*) AS n
    FROM orders
    GROUP BY status
) s;
""",
        "throwaway_users": """
SELECT count(*) FROM users
WHERE email LIKE 'audit_%@example.com' OR email LIKE 'v11_%@example.com';
        """,
    }
    out: dict[str, Any] = {}
    for name, sql in queries.items():
        if not sql:
            continue
        result = _psql(sql, timeout=20)
        out[name] = result
    return out


def collect_brain_and_evidence() -> dict[str, Any]:
    brain_dir = ROOT / "organism_brain"
    manifest = _json_file(brain_dir / "manifest.json")
    strategy_summary = _json_file(ROOT / "artifacts" / "phase6_strategy_evidence" / "strategy_evidence_summary.json")
    advisory_policy = _json_file(ROOT / "artifacts" / "phase6_strategy_evidence" / "realtime_advisory_policy.json")
    return {
        "manifest": {
            "gen": manifest.get("gen"),
            "total_trades": manifest.get("total_trades"),
            "ml_is_trained": manifest.get("ml_is_trained"),
            "saved_at": manifest.get("saved_at"),
        },
        "trade_history_rows": _csv_count(brain_dir / "trade_history.csv"),
        "phase5_candidate_filter_rows": _jsonl_count(
            brain_dir / "candidate_filter_shadow_telemetry.jsonl"
        ),
        "phase6_strategy_evidence_rows": _jsonl_count(
            brain_dir / "strategy_evidence_events.jsonl"
        ),
        "phase6_summary": {
            "telemetry_rows": strategy_summary.get("telemetry_rows"),
            "joined_outcome_rows": strategy_summary.get("joined_outcome_rows"),
            "outcome_recommendation": strategy_summary.get("outcome_recommendation"),
        },
        "phase6_policy_actions": advisory_policy.get("actions", []),
    }


def collect_parity() -> dict[str, Any]:
    mismatches: list[str] = []
    checked = 0
    for rel in HOT_PATH_FILES:
        host_sha = _host_file_sha(rel)
        container_sha = _container_file_sha(rel)
        checked += 1
        if not host_sha or not container_sha:
            mismatches.append(f"{rel}: unreadable host={bool(host_sha)} container={bool(container_sha)}")
        elif host_sha != container_sha:
            mismatches.append(f"{rel}: host={host_sha[:12]} container={container_sha[:12]}")
    return {"checked": checked, "mismatches": mismatches}


def collect_command_gates() -> dict[str, Any]:
    return {
        "deploy_parity_sandbox": _run(
            [sys.executable, "scripts/ci/check_deploy_parity.py"],
            timeout=30,
        ),
        "docker_compose_config": _run(
            ["docker-compose", "-f", "docker-compose.paper.yml", "config"],
            timeout=30,
        ),
        "runtime_snapshot": _run(
            [sys.executable, "scripts/runtime/write_runtime_snapshot.py"],
            timeout=60,
        ),
        "migration_smoke": _run(
            [sys.executable, "scripts/ci/check_migrations.py"],
            timeout=30,
        ),
    }


def build_checks(data: dict[str, Any]) -> list[Check]:
    checks: list[Check] = []
    repo = data["repo"]
    container = data["container"]
    http = data["http"]
    db = data["db"]
    brain = data["brain_and_evidence"]
    parity = data["parity"]
    gates = data["command_gates"]

    checks.append(
        Check(
            "repo_clean",
            "PASS" if not repo["status_short"] else "WARN",
            "worktree clean" if not repo["status_short"] else repo["status_short"],
            "medium",
        )
    )
    container_sha = container.get("git_sha")
    head = repo.get("head")
    sha_status = "PASS" if container_sha == head else "WARN"
    checks.append(
        Check(
            "container_git_sha_matches_head",
            sha_status,
            f"container={container_sha} head={head}",
            "medium",
        )
    )
    checks.append(
        Check(
            "hot_path_byte_parity",
            "PASS" if not parity["mismatches"] else "FAIL",
            f"checked={parity['checked']} mismatches={parity['mismatches'][:3]}",
            "critical",
        )
    )
    checks.append(
        Check(
            "healthz",
            "PASS" if http["healthz"]["status"] == 200 else "FAIL",
            f"status={http['healthz']['status']} payload={http['healthz']['payload']}",
            "critical",
        )
    )
    strategy_payload = http["strategy_health"]["payload"] or {}
    checks.append(
        Check(
            "strategy_health_authenticated",
            "PASS" if http["strategy_health"]["status"] == 200 else "WARN",
            (
                f"status={http['strategy_health']['status']} "
                f"n_trades={strategy_payload.get('n_trades')} "
                f"total_pnl={strategy_payload.get('total_pnl')} "
                f"is_profitable={strategy_payload.get('is_profitable')}"
            ),
            "high",
        )
    )
    deploy_payload = http["deploy_health"]["payload"] or {}
    checks.append(
        Check(
            "deploy_health_authenticated",
            "PASS" if http["deploy_health"]["status"] == 200 else "WARN",
            (
                f"status={http['deploy_health']['status']} "
                f"source_sha={deploy_payload.get('source_sha')} "
                f"migration_head={deploy_payload.get('migration_head')} "
                f"build_time={deploy_payload.get('build_time')}"
            ),
            "high",
        )
    )
    integrity_payload = http["data_integrity"]["payload"] or {}
    checks.append(
        Check(
            "data_integrity_authenticated",
            "PASS" if http["data_integrity"]["status"] == 200 else "WARN",
            (
                f"status={http['data_integrity']['status']} "
                f"accounting_status={integrity_payload.get('accounting_status')} "
                f"realized={integrity_payload.get('realized_trades')} "
                f"brain={integrity_payload.get('brain_total_trades')}"
            ),
            "medium",
        )
    )
    kill_switches = container.get("kill_switches") or {}
    missing_kill = [k for k, v in kill_switches.items() if not v]
    checks.append(
        Check(
            "kill_switch_env_present",
            "PASS" if not missing_kill else "FAIL",
            json.dumps(kill_switches, sort_keys=True),
            "high",
        )
    )
    checks.append(
        Check(
            "phase5_telemetry_enabled",
            "PASS" if container.get("phase5_telemetry_enabled") == "true" else "FAIL",
            str(container.get("phase5_telemetry_enabled")),
            "high",
        )
    )
    checks.append(
        Check(
            "phase6_telemetry_enabled",
            "PASS" if container.get("phase6_telemetry_enabled") == "true" else "FAIL",
            str(container.get("phase6_telemetry_enabled")),
            "high",
        )
    )
    checks.append(
        Check(
            "phase6_evidence_integrated",
            "PASS" if (brain["phase5_candidate_filter_rows"] or brain["phase6_strategy_evidence_rows"]) else "WARN",
            (
                f"phase5_rows={brain['phase5_candidate_filter_rows']} "
                f"phase6_rows={brain['phase6_strategy_evidence_rows']} "
                f"joined={brain['phase6_summary'].get('joined_outcome_rows')}"
            ),
            "medium",
        )
    )
    migration = db["migration_head"]
    checks.append(
        Check(
            "db_migration_head_readable",
            "PASS" if migration["returncode"] == 0 and migration["stdout"] else "FAIL",
            f"db={migration['stdout']}",
            "high",
        )
    )
    checks.append(
        Check(
            "open_positions_readable",
            "PASS" if db["open_positions"]["returncode"] == 0 else "FAIL",
            (
                f"count={db['open_positions']['stdout']} "
                f"positions={db['positions_by_symbol']['stdout']}"
            ),
            "medium",
        )
    )
    checks.append(
        Check(
            "outbox_events_readable",
            "PASS" if db["outbox_summary"]["returncode"] == 0 else "FAIL",
            db["outbox_summary"]["stdout"] or db["outbox_summary"]["stderr"],
            "medium",
        )
    )
    audit_payload = http["audit_chain_detail"]["payload"] or {}
    audit_rows = audit_payload.get("row_count") or len(audit_payload.get("rows", []))
    checks.append(
        Check(
            "audit_log_hash_chain",
            (
                "PASS"
                if http["audit_chain_detail"]["status"] == 200
                and audit_payload.get("all_valid") is True
                else "FAIL"
            ),
            (
                f"status={http['audit_chain_detail']['status']} "
                f"all_valid={audit_payload.get('all_valid')} rows={audit_rows} "
                f"columns={db['audit_log_columns']['stdout']}"
            ),
            "critical",
        )
    )
    for name, result in gates.items():
        checks.append(
            Check(
                name,
                "PASS" if result["returncode"] == 0 else "FAIL",
                (result["stdout"] or result["stderr"])[:500],
                "high",
            )
        )
    return checks


def build_report(data: dict[str, Any], checks: list[Check]) -> str:
    failed = [c for c in checks if c.status == "FAIL"]
    warned = [c for c in checks if c.status == "WARN"]
    policy_actions = data["brain_and_evidence"].get("phase6_policy_actions") or []
    strategy = (data["http"]["strategy_health"].get("payload") or {})
    deploy = (data["http"]["deploy_health"].get("payload") or {})
    integrity = (data["http"]["data_integrity"].get("payload") or {})
    db = data["db"]
    container = data["container"]
    generated_at = data["generated_at"]
    verdict = "PASS" if not failed else "FAIL"

    lines = [
        "# Phase 7 Integration Validation Checkpoint",
        "",
        f"Generated: {generated_at}",
        f"Branch: `{data['repo']['branch']}`",
        f"HEAD: `{data['repo']['head']}`",
        f"Container SHA: `{data['container'].get('git_sha')}`",
        f"Overall verdict: **{verdict}**",
        "",
        "## Executive Verdict",
        "",
    ]
    if failed:
        lines.append(
            f"The integration checkpoint found {len(failed)} failing check(s). "
            "Do not start Phase 7 refactors until the failures are resolved."
        )
    else:
        lines.append(
            "The integration checkpoint found no failing checks. Phase 6 is wired "
            "into the current paper runtime, and Phase 7 can begin with baseline "
            "inventory/refactor work while telemetry continues collecting evidence."
        )
    if warned:
        lines.append(
            f"There are {len(warned)} warning(s). Warnings are not blockers, but "
            "they should be carried into the Phase 7 risk register."
        )
    lines.extend(
        [
            "",
            "## Check Matrix",
            "",
            "| Check | Status | Severity | Evidence |",
            "|-------|--------|----------|----------|",
        ]
    )
    for check in checks:
        evidence = check.evidence.replace("\n", " ")[:300]
        lines.append(f"| `{check.name}` | {check.status} | {check.severity} | {evidence} |")

    lines.extend(
        [
            "",
            "## Strategy Health Snapshot",
            "",
            f"- `n_trades`: {strategy.get('n_trades')}",
            f"- `total_pnl`: {strategy.get('total_pnl')}",
            f"- `win_rate`: {strategy.get('win_rate')}",
            f"- `sharpe_ratio_per_trade`: {strategy.get('sharpe_ratio_per_trade')}",
            f"- `is_profitable`: {strategy.get('is_profitable')}",
            f"- `source`: {strategy.get('source')}",
            "",
            "## Operator View Snapshot",
            "",
            f"- Container SHA: `{data['container'].get('git_sha')}`",
            f"- Deploy endpoint SHA: `{deploy.get('source_sha')}`",
            f"- Build time: `{deploy.get('build_time') or container.get('build_time')}`",
            f"- Migration head: `{deploy.get('migration_head') or data['db']['migration_head']['stdout']}`",
            f"- Runtime config hash: `{deploy.get('runtime_config_hash')}`",
            f"- Kill switches: `{json.dumps(container.get('kill_switches') or {}, sort_keys=True)}`",
            f"- Open positions: `{db['open_positions']['stdout']}` ({db['positions_by_symbol']['stdout'] or 'none'})",
            f"- Orders by status: `{db['orders_by_status']['stdout']}`",
            f"- Outbox events count/min/max: `{db['outbox_summary']['stdout']}`",
            f"- Data integrity status: `{integrity.get('accounting_status')}`; "
            f"realized=`{integrity.get('realized_trades')}`, "
            f"brain=`{integrity.get('brain_total_trades')}`",
            "",
            "## Phase 6 Evidence Snapshot",
            "",
            f"- Phase 5 candidate-filter rows: {data['brain_and_evidence']['phase5_candidate_filter_rows']}",
            f"- Phase 6 strategy-evidence rows: {data['brain_and_evidence']['phase6_strategy_evidence_rows']}",
            f"- Joined outcome rows: {data['brain_and_evidence']['phase6_summary'].get('joined_outcome_rows')}",
            f"- Outcome recommendation: {data['brain_and_evidence']['phase6_summary'].get('outcome_recommendation')}",
            "",
            "| Filter | Action | Events | Outcomes | Mean bps | Win rate |",
            "|--------|--------|--------|----------|----------|----------|",
        ]
    )
    for action in policy_actions:
        lines.append(
            "| "
            f"{action.get('filter')} | {action.get('shadow_action')} | "
            f"{action.get('events')} | {action.get('outcomes')} | "
            f"{action.get('mean_directional_bps')} | {action.get('win_rate')} |"
        )
    if not policy_actions:
        lines.append("| none | none | 0 | 0 | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Integration Position",
            "",
            "- Phase 7 should start with P7.0 baseline inventory.",
            "- Phase 6 telemetry should remain enabled during Phase 7.",
            "- No strategy promotion is justified by this checkpoint.",
            "- Warnings should become Phase 7 risk-register entries.",
            "",
            "## Raw Artifact",
            "",
            f"JSON: `{JSON_PATH.relative_to(ROOT)}`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-report", action="store_true", help="Collect JSON only")
    args = parser.parse_args()

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": datetime.now(UTC).isoformat(),
        "repo": collect_repo(),
        "container": collect_container(),
        "http": collect_http(),
        "db": collect_db(),
        "brain_and_evidence": collect_brain_and_evidence(),
        "parity": collect_parity(),
        "command_gates": collect_command_gates(),
    }
    checks = build_checks(data)
    data["checks"] = [asdict(c) for c in checks]
    JSON_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    if not args.no_report:
        REPORT_PATH.write_text(build_report(data, checks))

    failed = [c for c in checks if c.status == "FAIL"]
    warned = [c for c in checks if c.status == "WARN"]
    print(f"Phase 7 integration checkpoint: {len(checks) - len(failed) - len(warned)} pass, {len(warned)} warn, {len(failed)} fail")
    print(f"JSON: {JSON_PATH}")
    if not args.no_report:
        print(f"Report: {REPORT_PATH}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
