import asyncio
import os
import time
from typing import Any

import httpx


def _mask(s: str | None) -> str:
    if not s:
        return "<unset>"
    return "<set>"


async def _request_json(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> tuple[int, Any]:
    r = await client.request(method, url, **kwargs)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text


async def main() -> int:
    # Load local .env so this script uses the same credentials/config as the server.
    try:
        from dotenv import load_dotenv

        load_dotenv(".env", override=False)
    except Exception:
        pass

    base_url = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    staging_api_key = os.getenv("STAGING_API_KEY")
    username = os.getenv("ADMIN_USERNAME", "admin@example.com")
    password = os.getenv("ADMIN_PASSWORD", "Admin123!@#")

    print("Base URL:", base_url)
    print("STAGING_API_KEY:", _mask(staging_api_key))
    print("ADMIN_USERNAME:", username)
    print("ADMIN_PASSWORD:", _mask(password))

    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        headers: dict[str, str] = {}

        # Prefer non-DB auth for smoke tests (useful when Postgres is down):
        # - If STAGING_API_KEY is set AND server env is dev/development/staging, auth works via X-API-Key.
        # - Otherwise fall back to DB-backed /auth/login.
        if staging_api_key:
            headers = {"X-API-Key": staging_api_key}
            print("Using X-API-Key auth (STAGING_API_KEY).")
        else:
            status, body = await _request_json(
                client,
                "POST",
                f"{base_url}/api/v1/auth/login",
                json={"username": username, "password": password},
            )
            if status != 200:
                print("LOGIN FAILED status=", status)
                print("body=", body)
                print("Tip: if Postgres is down, set STAGING_API_KEY and run server in APP_ENVIRONMENT=development.")
                return 2

            access_token = body.get("access_token") if isinstance(body, dict) else None
            if not access_token:
                print("LOGIN FAILED: missing access_token")
                return 2

            headers = {"Authorization": f"Bearer {access_token}"}
            print("Login OK; token received.")

        # Verify auth works (does not require DB when using X-API-Key)
        status, verify = await _request_json(
            client,
            "GET",
            f"{base_url}/api/v1/auth/verify",
            headers=headers,
        )
        print("GET /auth/verify status=", status)
        if status != 200:
            print("body=", verify)
            return 2

        # Auto breakout scan (real market data)
        payload = {
            "symbols": ["AAPL", "MSFT", "NVDA", "SPY"],
            "timeframe": "1Day",
            "limit": 120,
            "allow_short": False,
            "min_price": 5.0,
            "max_price": 5000.0,
        }
        status, scan = await _request_json(
            client,
            "POST",
            f"{base_url}/api/v1/auto-breakout/run-once",
            headers=headers,
            json=payload,
        )
        print("POST /auto-breakout/run-once status=", status)
        if status != 200:
            print("body=", scan)
            return 3

        candidates = scan.get("candidates", []) if isinstance(scan, dict) else []
        print("Breakout scan candidates:", len(candidates))
        if candidates:
            print("Top candidate:", {k: candidates[0].get(k) for k in ("symbol", "score", "direction", "reason")})

        # Latest
        status, latest = await _request_json(
            client,
            "GET",
            f"{base_url}/api/v1/auto-breakout/latest",
            headers=headers,
        )
        print("GET /auto-breakout/latest status=", status)
        if status != 200:
            print("body=", latest)
            return 4

        # Multi-strategy run-once (goes through full OrderService + StrategyEngine path)
        ms_payload = {"symbols": ["AAPL", "MSFT"], "lookback": 120, "timeframe": "1Day"}
        status, ms = await _request_json(
            client,
            "POST",
            f"{base_url}/api/v1/multi-strategy-live/run-once",
            headers=headers,
            json=ms_payload,
        )
        print("POST /multi-strategy-live/run-once status=", status)
        if status != 200:
            print("body=", ms)
            print("Note: this endpoint requires a working database/outbox to enqueue orders.")
            return 5

        submitted = ms.get("submitted", []) if isinstance(ms, dict) else []
        print("Multi-strategy submitted entries:", len(submitted))

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
