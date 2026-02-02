"""Paper trading E2E smoke checks.

Goal: a repeatable, low-risk go/no-go check before enabling paper execution.

What it checks (no order placement by default):
- Backend is reachable and healthy.
- Metrics endpoint responds.
- (Optional) Admin trading execution-mode endpoint is reachable and consistent.
- (Optional) Can set/clear runtime execution-mode override.

Usage (PowerShell):
  $env:SMOKE_BASE_URL = "http://localhost:8000"
    # Option A: provide an already-issued JWT
    $env:SMOKE_ADMIN_TOKEN = "<admin_jwt>"  # optional
    # Option B: let the script login to obtain a JWT automatically
    $env:SMOKE_USERNAME = "admin@example.com"  # optional
    $env:SMOKE_PASSWORD = "admin123"          # optional
  python scripts/testing/paper_trading_smoke.py

Exit codes:
- 0: all checks passed
- 1: one or more checks failed
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


def _join(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    timeout_s: float = 10.0,
) -> tuple[int, dict]:
    data_bytes = None
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if body is not None:
        data_bytes = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, method=method, headers=hdrs, data=data_bytes)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8") or "{}")
            return resp.status, payload
    except urllib.error.HTTPError as e:
        raw = e.read() if hasattr(e, "read") else b""
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            payload = {"raw": raw.decode("utf-8", errors="replace")}
        return int(getattr(e, "code", 500)), payload


def _http_text(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_s: float = 10.0,
) -> tuple[int, str]:
    hdrs = {"Accept": "text/plain"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url=url, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
            return resp.status, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read() if hasattr(e, "read") else b""
        return int(getattr(e, "code", 500)), raw.decode("utf-8", errors="replace")


def _check_health(base_url: str) -> None:
    # This codebase exposes health endpoints both at the root (e.g. /health, /healthz)
    # and also under /api/v1 via routers. Which one is present depends on the entrypoint
    # and reverse-proxy setup, so we probe a few canonical paths.
    candidates = [
        "/health",
        "/healthz",
        "/livez",
        "/readyz",
        "/api/v1/health",
        "/api/v1/healthz",
    ]

    last_err: Exception | None = None
    last_seen: tuple[str, int, dict] | None = None

    for _ in range(10):
        for path in candidates:
            url = _join(base_url, path)
            try:
                status, payload = _http_json("GET", url, timeout_s=5.0)
                last_seen = (path, status, payload)

                if status == 200 and payload.get("status") in {"healthy", "ok", "alive"}:
                    return

            except Exception as e:  # noqa: BLE001 - smoke runner
                last_err = e
        time.sleep(0.5)

    if last_seen and last_seen[1] == 404:
        path, status, payload = last_seen
        raise RuntimeError(
            "No health endpoint found (got 404). "
            f"Last tried {path} -> {status} {payload}. "
            "If you are behind a proxy or mounted at a sub-path, set SMOKE_BASE_URL accordingly."
        )

    raise RuntimeError(f"Health check failed: last_err={last_err}, last_seen={last_seen}")


def _check_metrics(base_url: str) -> None:
    candidates = [
        "/metrics",
        "/api/v1/metrics",
    ]

    last: tuple[str, int, str] | None = None
    for path in candidates:
        url = _join(base_url, path)
        status, text = _http_text("GET", url, timeout_s=10.0)
        last = (path, status, text)
        if status == 200:
            # Minimal sanity: should look like Prometheus exposition.
            if "process_" not in text and "http_" not in text:
                raise RuntimeError(
                    f"Metrics at {path} returned 200 but did not include expected Prometheus keys"
                )
            return

    if last is None:
        raise RuntimeError("Metrics endpoint probe did not run")
    path, status, text = last
    raise RuntimeError(f"Metrics endpoint failed: {path} -> {status} {text[:2000]}")


def _admin_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login_for_token(base_url: str, username: str, password: str) -> str:
    """Login and return access_token.

    This is not a special login and does not grant extra privileges.
    Whatever roles the user has in the DB will be encoded into the JWT.
    """
    candidates = [
        "/api/v1/auth/login",
        "/auth/login",
    ]

    last: tuple[str, int, dict] | None = None
    for path in candidates:
        url = _join(base_url, path)
        status, payload = _http_json(
            "POST",
            url,
            body={"username": username, "password": password},
            timeout_s=10.0,
        )
        last = (path, status, payload)
        if status == 200 and isinstance(payload, dict) and payload.get("access_token"):
            return str(payload["access_token"])

    if last is None:
        raise RuntimeError("Login probe did not run")
    path, status, payload = last
    raise RuntimeError(f"Login failed: {path} -> {status} {payload}")


def _check_admin_execution_mode(base_url: str, token: str, *, mutate: bool) -> None:
    url = _join(base_url, "/api/v1/admin/trading/execution-mode")

    status, payload = _http_json("GET", url, headers=_admin_headers(token), timeout_s=10.0)
    if status != 200:
        raise RuntimeError(f"Admin execution-mode GET failed: {status} {payload}")

    mode = payload.get("mode")
    alpaca_base_url = payload.get("alpaca_base_url")
    alpaca_paper = payload.get("alpaca_paper")
    allowed = set(payload.get("allowed_modes") or [])

    if mode not in allowed:
        raise RuntimeError(f"Execution mode {mode!r} not in allowed_modes={sorted(allowed)}")

    if isinstance(alpaca_base_url, str) and "paper" not in alpaca_base_url.lower() and alpaca_paper:
        raise RuntimeError(f"alpaca_paper=True but alpaca_base_url={alpaca_base_url!r}")

    if mutate:
        # Set override to dry_run, then clear it. This exercises the runtime override plumbing.
        status, payload_put = _http_json(
            "PUT",
            url,
            headers=_admin_headers(token),
            body={"mode": "dry_run"},
            timeout_s=10.0,
        )
        if status != 200 or payload_put.get("mode") != "dry_run":
            raise RuntimeError(f"Admin execution-mode PUT failed: {status} {payload_put}")

        status, payload_del = _http_json("DELETE", url, headers=_admin_headers(token), timeout_s=10.0)
        if status != 200:
            raise RuntimeError(f"Admin execution-mode DELETE failed: {status} {payload_del}")


def main() -> int:
    base_url = os.environ.get("SMOKE_BASE_URL", "http://localhost:8000")
    admin_token = os.environ.get("SMOKE_ADMIN_TOKEN") or os.environ.get("ADMIN_JWT")
    smoke_username = os.environ.get("SMOKE_USERNAME")
    smoke_password = os.environ.get("SMOKE_PASSWORD")
    mutate = os.environ.get("SMOKE_MUTATE", "0") == "1"

    failures: list[str] = []

    try:
        _check_health(base_url)
        print("OK: health")
    except Exception as e:  # noqa: BLE001 - smoke runner
        failures.append(f"health: {e}")

    try:
        _check_metrics(base_url)
        print("OK: metrics")
    except Exception as e:  # noqa: BLE001 - smoke runner
        failures.append(f"metrics: {e}")

    if not admin_token and smoke_username and smoke_password:
        try:
            admin_token = _login_for_token(base_url, smoke_username, smoke_password)
            print("OK: login (token acquired)")
        except Exception as e:  # noqa: BLE001 - smoke runner
            failures.append(f"login: {e}")

    if admin_token:
        try:
            _check_admin_execution_mode(base_url, admin_token, mutate=mutate)
            print("OK: admin execution-mode")
            if mutate:
                print("OK: admin override set/cleared")
        except Exception as e:  # noqa: BLE001 - smoke runner
            failures.append(f"admin execution-mode: {e}")
    else:
        print(
            "SKIP: admin execution-mode "
            "(set SMOKE_ADMIN_TOKEN or SMOKE_USERNAME/SMOKE_PASSWORD to enable)"
        )

    if failures:
        print("\nFAILURES:")
        for item in failures:
            print(f"- {item}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
