#!/usr/bin/env python3
"""Phase 7.8 live security sanity checkpoint.

This is intentionally a behavioral HTTP probe, not a source-marker check.  It
verifies the access boundaries that matter for the paper runtime:

* admin login, /me, and logout blacklist behavior;
* unauthenticated requests stay unauthenticated;
* default user-role tokens cannot read operator/trading control surfaces;
* debug/test endpoints are absent.

The user-role token is minted locally with the app's configured JWT secret.  A
self-registered user would receive the same role shape from /auth/register, but
this probe avoids creating or deleting live users.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.infra.security import create_access_token


@dataclass
class HttpResult:
    status: int
    body_preview: str


@dataclass
class Probe:
    name: str
    method: str
    path: str
    expected_status: int
    token_kind: str | None = None
    actual_status: int | None = None
    passed: bool = False
    body_preview: str = ""


@dataclass
class SecurityReport:
    generated_at: str
    base_url: str
    passed: int
    failed: int
    probes: list[Probe]

    def to_jsonable(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["overall"] = "pass" if self.failed == 0 else "fail"
        return payload


def _request(
    *,
    base_url: str,
    method: str,
    path: str,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> HttpResult:
    body = None
    headers: dict[str, str] = {}
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            preview = resp.read(1_000_000).decode(errors="replace")
            return HttpResult(status=int(resp.status), body_preview=preview)
    except urllib.error.HTTPError as exc:
        preview = exc.read(1_000_000).decode(errors="replace")
        return HttpResult(status=int(exc.code), body_preview=preview)


def _admin_login(base_url: str, username: str, password: str) -> str:
    result = _request(
        base_url=base_url,
        method="POST",
        path="/api/v1/auth/login",
        payload={"username": username, "password": password},
    )
    if result.status != 200:
        raise RuntimeError(
            f"admin login failed: status={result.status} body={result.body_preview[:160]}"
        )
    payload = json.loads(result.body_preview)
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("admin login response did not include access_token")
    return str(token)


def _run_probe(base_url: str, probe: Probe, tokens: dict[str, str]) -> Probe:
    token = tokens.get(probe.token_kind or "")
    result = _request(
        base_url=base_url,
        method=probe.method,
        path=probe.path,
        token=token,
    )
    probe.actual_status = result.status
    probe.body_preview = result.body_preview[:240]
    probe.passed = result.status == probe.expected_status
    return probe


def run_security_sanity(
    *,
    base_url: str,
    admin_user: str,
    admin_password: str,
) -> SecurityReport:
    admin_token = _admin_login(base_url, admin_user, admin_password)
    user_token = create_access_token(
        sub="phase7-user@example.com",
        roles=["user"],
        expires_minutes=10,
    )
    tokens = {"admin": admin_token, "user": user_token}

    probes = [
        Probe("admin_me", "GET", "/api/v1/auth/me", 200, "admin"),
        Probe("admin_settings", "GET", "/api/v1/settings/organism", 200, "admin"),
        Probe("admin_strategy_health", "GET", "/api/v1/health/strategy", 200, "admin"),
        Probe("admin_deploy_health", "GET", "/api/v1/health/deploy", 200, "admin"),
        Probe("admin_data_integrity", "GET", "/api/v1/health/data-integrity", 200, "admin"),
        Probe("admin_orders", "GET", "/api/v1/orders/", 200, "admin"),
        Probe("user_me", "GET", "/api/v1/auth/me", 200, "user"),
        Probe("user_settings_forbidden", "GET", "/api/v1/settings/organism", 403, "user"),
        Probe("user_strategy_health_forbidden", "GET", "/api/v1/health/strategy", 403, "user"),
        Probe("user_deploy_health_forbidden", "GET", "/api/v1/health/deploy", 403, "user"),
        Probe("user_data_integrity_forbidden", "GET", "/api/v1/health/data-integrity", 403, "user"),
        Probe("user_orders_forbidden", "GET", "/api/v1/orders/", 403, "user"),
        Probe("user_cancel_forbidden", "POST", "/api/v1/orders/00000000-0000-0000-0000-000000000000/cancel", 403, "user"),
        Probe("user_organism_brain_forbidden", "GET", "/api/v1/organism/brain", 403, "user"),
        Probe("public_settings_unauthorized", "GET", "/api/v1/settings/organism", 401),
        Probe("debug_http_401_absent", "GET", "/test/http-401", 404),
        Probe("debug_api_http_401_absent", "GET", "/api/v1/test/http-401", 404),
    ]

    completed = [_run_probe(base_url, probe, tokens) for probe in probes]

    logout = _request(
        base_url=base_url,
        method="POST",
        path="/api/v1/auth/logout",
        token=admin_token,
    )
    completed.append(
        Probe(
            name="admin_logout",
            method="POST",
            path="/api/v1/auth/logout",
            expected_status=200,
            token_kind="admin",
            actual_status=logout.status,
            passed=logout.status == 200,
            body_preview=logout.body_preview[:240],
        )
    )
    after_logout = _request(
        base_url=base_url,
        method="GET",
        path="/api/v1/auth/me",
        token=admin_token,
    )
    completed.append(
        Probe(
            name="admin_token_revoked_after_logout",
            method="GET",
            path="/api/v1/auth/me",
            expected_status=401,
            token_kind="admin",
            actual_status=after_logout.status,
            passed=after_logout.status == 401,
            body_preview=after_logout.body_preview[:240],
        )
    )

    passed = sum(1 for probe in completed if probe.passed)
    failed = len(completed) - passed
    return SecurityReport(
        generated_at=datetime.now(UTC).isoformat(),
        base_url=base_url,
        passed=passed,
        failed=failed,
        probes=completed,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--admin-user", default="admin@example.com")
    parser.add_argument("--admin-password", default="admin123")
    parser.add_argument(
        "--output",
        default="artifacts/phase7/security_sanity.json",
        help="JSON output path",
    )
    args = parser.parse_args()

    report = run_security_sanity(
        base_url=args.base_url,
        admin_user=args.admin_user,
        admin_password=args.admin_password,
    )
    payload = report.to_jsonable()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
