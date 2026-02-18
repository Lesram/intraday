#!/usr/bin/env python3
"""
Run blueprint live-acceptance probes for the Evolving Organism and produce
machine-readable + markdown evidence artifacts.

Supports:
- LT-06: 24h paper execute run verification
- LT-07: 5-day paper accumulation verification

This script is operationally bounded and can be started/stopped safely.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


DEFAULT_BASE_URL = os.getenv("ORGANISM_BASE_URL", "http://localhost:8000")
DEFAULT_PATHS = [
    os.getenv("ORGANISM_API_PATH", "/api/v1/organism"),
    "/organism",
]
REPORT_DIR = Path("reports")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ProbeResult:
    timestamp: str
    ok: bool
    health_ok: bool
    status_code: int
    regime: str | None
    brain_generation: int | None
    total_trades: int | None
    errors: list[str]


class OrganismAcceptanceRunner:
    def __init__(
        self,
        base_url: str,
        interval_seconds: int,
        duration_seconds: int,
        manual_tick: bool,
        token: str | None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.interval_seconds = max(5, interval_seconds)
        self.duration_seconds = max(60, duration_seconds)
        self.manual_tick = manual_tick
        self.token = token
        self.session = requests.Session()

        self.path_prefix: str | None = None
        self.probes: list[ProbeResult] = []
        self.started_at = _iso_now()

    def _ensure_token(self) -> None:
        if self.token:
            return

        username = (
            os.getenv("SMOKE_USERNAME")
            or os.getenv("TEST_ADMIN_USERNAME")
            or os.getenv("ADMIN_USERNAME")
            or "admin"
        )
        password = (
            os.getenv("SMOKE_PASSWORD")
            or os.getenv("TEST_ADMIN_PASSWORD")
            or os.getenv("ADMIN_PASSWORD")
            or "admin123"
        )

        login_paths = ["/api/v1/auth/login", "/auth/login"]
        payloads = [
            {"username": username, "password": password},
            {"email": username, "password": password},
            {"identifier": username, "password": password},
        ]
        for path in login_paths:
            url = f"{self.base_url}{path}"
            for payload in payloads:
                try:
                    resp = self.session.post(url, json=payload, timeout=10)
                    if resp.status_code == 200:
                        body = resp.json()
                        token = body.get("access_token") if isinstance(body, dict) else None
                        if token:
                            self.token = str(token)
                            return
                except requests.RequestException:
                    continue

    def _headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def discover_path(self) -> str:
        self._ensure_token()
        for path in DEFAULT_PATHS:
            url = f"{self.base_url}{path}/status"
            try:
                resp = self.session.get(url, timeout=10, headers=self._headers())
                if resp.status_code in (200, 401, 403):
                    self.path_prefix = path
                    return path
            except requests.RequestException:
                continue
        raise RuntimeError("Could not discover organism API path (/api/v1/organism or /organism)")

    def _health(self) -> tuple[bool, int]:
        try:
            resp = self.session.get(f"{self.base_url}/health", timeout=10)
            return resp.status_code == 200, resp.status_code
        except requests.RequestException:
            return False, 0

    def _status(self) -> tuple[int, dict[str, Any] | None, list[str]]:
        assert self.path_prefix is not None
        url = f"{self.base_url}{self.path_prefix}/status"
        errors: list[str] = []
        try:
            resp = self.session.get(url, timeout=15, headers=self._headers())
            code = resp.status_code
            data = None
            if code == 200:
                data = resp.json()
            else:
                errors.append(f"status endpoint returned {code}")
            return code, data, errors
        except requests.RequestException as e:
            return 0, None, [f"status request error: {e}"]

    def _tick(self) -> list[str]:
        if not self.manual_tick:
            return []
        assert self.path_prefix is not None
        url = f"{self.base_url}{self.path_prefix}/tick"
        try:
            resp = self.session.post(url, timeout=60, headers=self._headers())
            if resp.status_code != 200:
                return [f"manual tick returned {resp.status_code}"]
        except requests.RequestException as e:
            return [f"manual tick error: {e}"]
        return []

    def run(self) -> dict[str, Any]:
        self.discover_path()
        deadline = time.time() + self.duration_seconds

        while time.time() < deadline:
            probe_errors: list[str] = []
            health_ok, health_code = self._health()
            if not health_ok:
                probe_errors.append(f"health check failed ({health_code})")

            tick_errors = self._tick()
            probe_errors.extend(tick_errors)

            status_code, status_payload, status_errors = self._status()
            probe_errors.extend(status_errors)

            regime = None
            brain_generation = None
            total_trades = None
            if status_payload:
                regime = (status_payload.get("regime") or {}).get("last_regime")
                live_engine = status_payload.get("live_engine") or {}
                engine = live_engine.get("engine") or {}
                brain_generation = engine.get("brain_generation")
                total_trades = engine.get("total_trades")

            self.probes.append(
                ProbeResult(
                    timestamp=_iso_now(),
                    ok=len(probe_errors) == 0,
                    health_ok=health_ok,
                    status_code=status_code,
                    regime=regime,
                    brain_generation=brain_generation,
                    total_trades=total_trades,
                    errors=probe_errors,
                )
            )
            time.sleep(self.interval_seconds)

        return self.summarize()

    def summarize(self) -> dict[str, Any]:
        errors = [p for p in self.probes if not p.ok]
        generations = [p.brain_generation for p in self.probes if p.brain_generation is not None]
        trades = [p.total_trades for p in self.probes if p.total_trades is not None]

        monotonic_generation = all(
            generations[i] >= generations[i - 1] for i in range(1, len(generations))
        ) if len(generations) > 1 else True
        monotonic_trades = all(
            trades[i] >= trades[i - 1] for i in range(1, len(trades))
        ) if len(trades) > 1 else True

        return {
            "started_at": self.started_at,
            "ended_at": _iso_now(),
            "base_url": self.base_url,
            "path_prefix": self.path_prefix,
            "interval_seconds": self.interval_seconds,
            "duration_seconds": self.duration_seconds,
            "probe_count": len(self.probes),
            "error_probe_count": len(errors),
            "monotonic_brain_generation": monotonic_generation,
            "monotonic_total_trades": monotonic_trades,
            "latest_brain_generation": generations[-1] if generations else None,
            "latest_total_trades": trades[-1] if trades else None,
            "probes": [p.__dict__ for p in self.probes],
        }


def write_reports(mode: str, summary: dict[str, Any]) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")

    json_path = REPORT_DIR / f"organism_{mode.lower()}_acceptance_{ts}.json"
    md_path = REPORT_DIR / f"organism_{mode.lower()}_acceptance_{ts}.md"

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    verdict = "PASS" if summary["error_probe_count"] == 0 else "WARN"
    md = [
        f"# {mode} Acceptance Report",
        "",
        f"- Started: {summary['started_at']}",
        f"- Ended: {summary['ended_at']}",
        f"- Base URL: {summary['base_url']}",
        f"- API Path: {summary['path_prefix']}",
        f"- Duration (s): {summary['duration_seconds']}",
        f"- Probe Interval (s): {summary['interval_seconds']}",
        f"- Probe Count: {summary['probe_count']}",
        f"- Error Probe Count: {summary['error_probe_count']}",
        f"- Monotonic Brain Generation: {summary['monotonic_brain_generation']}",
        f"- Monotonic Total Trades: {summary['monotonic_total_trades']}",
        f"- Latest Brain Generation: {summary['latest_brain_generation']}",
        f"- Latest Total Trades: {summary['latest_total_trades']}",
        "",
        f"## Verdict: {verdict}",
        "",
        "- `PASS` means no probe-level API/health/tick errors were observed during the run.",
        "- `WARN` means one or more probes failed and requires investigation.",
    ]
    md_path.write_text("\n".join(md), encoding="utf-8")
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run organism live acceptance probes")
    p.add_argument("--mode", choices=["LT06", "LT07"], required=True)
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--interval-seconds", type=int, default=300)
    p.add_argument("--duration-hours", type=float, default=None)
    p.add_argument("--manual-tick", action="store_true", help="Call /tick each probe")
    p.add_argument("--token", default=os.getenv("ORGANISM_ADMIN_TOKEN", ""))
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.duration_hours is not None:
        duration_seconds = int(args.duration_hours * 3600)
    else:
        duration_seconds = 24 * 3600 if args.mode == "LT06" else 5 * 24 * 3600

    runner = OrganismAcceptanceRunner(
        base_url=args.base_url,
        interval_seconds=args.interval_seconds,
        duration_seconds=duration_seconds,
        manual_tick=args.manual_tick,
        token=args.token or None,
    )

    summary = runner.run()
    json_path, md_path = write_reports(args.mode, summary)

    print(f"Acceptance summary written: {json_path}")
    print(f"Acceptance report written:  {md_path}")
    print(
        "Verdict:",
        "PASS" if summary["error_probe_count"] == 0 else "WARN",
        f"(error probes={summary['error_probe_count']})",
    )

    return 0 if summary["error_probe_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
