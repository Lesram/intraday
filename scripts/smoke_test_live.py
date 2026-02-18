#!/usr/bin/env python3
"""
Live Smoke Test — verifies the platform is working end-to-end.

Usage:
    python scripts/smoke_test_live.py
    python scripts/smoke_test_live.py --base-url http://localhost:8000

Checks:
    1. Health endpoint → 200 OK
    2. Auth (login) → JWT token
    3. Portfolio → real Alpaca data
    4. Organism status → current state
    5. Organism runs → recent tick history
    6. Strategies → strategy list
    7. WebSocket → receives tick within 90s
"""
import argparse
import asyncio
import os
import sys
import time

import httpx

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")


class SmokeTestRunner:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.token: str | None = None
        self.results: list[tuple[str, bool, str]] = []

    # ------------------------------------------------------------------
    def _record(self, name: str, passed: bool, detail: str = ""):
        tag = "PASS" if passed else "FAIL"
        print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
        self.results.append((name, passed, detail))

    # ------------------------------------------------------------------
    async def run_all(self):
        async with httpx.AsyncClient(timeout=15) as client:
            await self._check_health(client)
            await self._check_auth(client)
            if self.token:
                await self._check_portfolio(client)
                await self._check_organism_status(client)
                await self._check_organism_runs(client)
                await self._check_strategies(client)
            else:
                for name in ("portfolio", "organism/status", "organism/runs", "strategies"):
                    self._record(name, False, "Skipped — no auth token")

        await self._check_websocket()
        return all(passed for _, passed, _ in self.results)

    # ------------------------------------------------------------------
    async def _check_health(self, client: httpx.AsyncClient):
        try:
            r = await client.get(f"{self.base}/health")
            self._record("health", r.status_code == 200, f"HTTP {r.status_code}")
        except Exception as e:
            self._record("health", False, str(e))

    async def _check_auth(self, client: httpx.AsyncClient):
        try:
            r = await client.post(
                f"{self.base}/api/v1/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            )
            if r.status_code == 200:
                data = r.json()
                self.token = data.get("access_token") or data.get("token")
                self._record("auth/login", bool(self.token), "Token acquired")
            else:
                self._record("auth/login", False, f"HTTP {r.status_code}: {r.text[:120]}")
        except Exception as e:
            self._record("auth/login", False, str(e))

    async def _authed_get(self, client: httpx.AsyncClient, path: str) -> httpx.Response | None:
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            return await client.get(f"{self.base}/api/v1{path}", headers=headers)
        except Exception:
            return None

    async def _check_portfolio(self, client: httpx.AsyncClient):
        r = await self._authed_get(client, "/portfolio/")
        if r and r.status_code == 200:
            data = r.json()
            equity = data.get("total_equity") or data.get("equity") or 0
            self._record("portfolio", True, f"equity=${equity}")
        else:
            self._record("portfolio", False, f"HTTP {r.status_code if r else 'no response'}")

    async def _check_organism_status(self, client: httpx.AsyncClient):
        r = await self._authed_get(client, "/organism/status")
        if r and r.status_code == 200:
            data = r.json()
            self._record("organism/status", True, f"state={data.get('state', 'unknown')}")
        else:
            code = r.status_code if r else "no response"
            # 404 is acceptable if organism module is not enabled
            self._record("organism/status", code in (200, 404), f"HTTP {code}")

    async def _check_organism_runs(self, client: httpx.AsyncClient):
        r = await self._authed_get(client, "/organism/runs?limit=5")
        if r and r.status_code == 200:
            data = r.json()
            count = len(data) if isinstance(data, list) else data.get("count", "?")
            self._record("organism/runs", True, f"runs={count}")
        else:
            code = r.status_code if r else "no response"
            self._record("organism/runs", code in (200, 404), f"HTTP {code}")

    async def _check_strategies(self, client: httpx.AsyncClient):
        r = await self._authed_get(client, "/strategies/")
        if r and r.status_code == 200:
            data = r.json()
            count = len(data) if isinstance(data, list) else data.get("count", "?")
            self._record("strategies", True, f"count={count}")
        else:
            self._record("strategies", False, f"HTTP {r.status_code if r else 'no response'}")

    async def _check_websocket(self):
        try:
            import socketio  # type: ignore[import-untyped]
        except ImportError:
            self._record("websocket", False, "python-socketio not installed")
            return

        sio = socketio.AsyncClient()
        received = asyncio.Event()

        @sio.on("organism_tick")
        async def on_tick(data):
            received.set()

        @sio.on("connect")
        async def on_connect():
            pass

        try:
            await sio.connect(self.base, transports=["websocket"], wait_timeout=10)
            try:
                await asyncio.wait_for(received.wait(), timeout=90)
                self._record("websocket", True, "organism_tick received")
            except asyncio.TimeoutError:
                self._record("websocket", False, "No organism_tick within 90s (organism may be disabled)")
            await sio.disconnect()
        except Exception as e:
            self._record("websocket", False, str(e))


async def main():
    parser = argparse.ArgumentParser(description="Live smoke test")
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()

    print(f"\nSmoke Test — {args.base_url}")
    print("=" * 50)

    runner = SmokeTestRunner(args.base_url)
    all_passed = await runner.run_all()

    print("=" * 50)
    passed = sum(1 for _, p, _ in runner.results if p)
    total = len(runner.results)
    print(f"Result: {passed}/{total} passed")

    if all_passed:
        print("SMOKE TEST: PASS")
    else:
        print("SMOKE TEST: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
