#!/usr/bin/env python3
"""Read-only market-data pull for the intraday regime study (research only).

Run on the Mac AFTER the close (it refuses during market hours):

    ~/VS/intra/venv/bin/python -B ~/VS/intra/research/regime_study/pull_research_bars.py

What it does
  * Reads the paper account's Alpaca keys from ~/VS/intra/.env (never printed).
  * GET-only requests to Alpaca's market-data API (data.alpaca.markets) and one
    GET of the paper trading clock. No orders, no account changes.
  * Downloads 1-minute bars (2025-01-02 .. last close) and daily bars (2016-01-04 ..)
    for the platform's 20 core symbols plus the 10 sector ETFs, SIP feed when the
    plan allows it, IEX otherwise (recorded per file).
  * Writes gzip CSVs + a manifest (row counts, sha256, feed) under
    ~/VS/intra/research/regime_study/data/. Re-running resumes: finished files are kept.
Throttled to about 3 requests/second; backs off on HTTP 429.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/Users/marselkei/VS/intra")
ENV_FILE = ROOT / ".env"
OUT = ROOT / "research/regime_study/data"
DATA = "https://data.alpaca.markets/v2/stocks/bars"
CLOCK = "https://paper-api.alpaca.markets/v2/clock"
CORE = ["AAPL", "AMD", "AMZN", "AVGO", "CAT", "COST", "CRM", "GOOGL", "IWM", "LLY",
        "META", "MSFT", "NVDA", "QQQ", "SPY", "TSLA", "WMT", "XLE", "XLK", "XOM"]
SECTORS = ["XLF", "XLV", "XLI", "XLU", "XLP", "XLY", "XLB", "XLRE"]   # XLE/XLK already in CORE
SYMBOLS = CORE + SECTORS
PULLS = (("1Min", "2025-01-02T00:00:00Z"), ("1Day", "2016-01-04T00:00:00Z"))
MIN_INTERVAL = 0.35                                    # seconds between requests


def env_keys() -> tuple[str, str]:
    keys = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip().removeprefix("export ").strip()
        if name in ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY"):
            keys[name] = value.strip().strip('"').strip("'")
    if len(keys) != 2 or not all(keys.values()):
        sys.exit("STOPPED: Alpaca keys not found in ~/VS/intra/.env")
    return keys["ALPACA_API_KEY_ID"], keys["ALPACA_API_SECRET_KEY"]


_last = [0.0]


def get(url: str, params: dict, key: str, secret: str) -> dict:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    request = urllib.request.Request(f"{url}?{query}" if query else url,
                                     headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
                                              "Accept": "application/json"})
    for attempt in range(6):
        wait = MIN_INTERVAL - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                time.sleep(min(60, 2 ** attempt * 2))
                continue
            raise
        except urllib.error.URLError:
            time.sleep(min(60, 2 ** attempt * 2))
    raise RuntimeError(f"giving up after retries: {url}")


def pull(symbol: str, timeframe: str, start: str, end: str, key: str, secret: str) -> tuple[list, str]:
    for feed in ("sip", "iex"):
        rows, token = [], None
        try:
            while True:
                page = get(DATA, {"symbols": symbol, "timeframe": timeframe, "start": start, "end": end,
                                  "limit": 10000, "adjustment": "all", "feed": feed, "page_token": token},
                           key, secret)
                rows += (page.get("bars") or {}).get(symbol, [])
                token = page.get("next_page_token")
                if not token:
                    return rows, feed
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403) and feed == "sip":
                continue                                # plan without SIP history: fall back to IEX
            raise
    return [], "none"


def main() -> int:
    key, secret = env_keys()
    clock = get(CLOCK, {}, key, secret)
    if clock.get("is_open"):
        sys.exit("STOPPED: the market is open; run this after the close")
    # Stay 20 minutes behind now: plans without real-time SIP refuse the most recent window.
    end = (datetime.now(timezone.utc) - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"files": {}}
    manifest.update({"pulled_through": end, "source": "Alpaca market data v2 (GET only)",
                     "adjustment": "all"})
    for timeframe, start in PULLS:
        for symbol in SYMBOLS:
            name = f"{timeframe}/{symbol}.csv.gz"
            if name in manifest["files"] and manifest["files"][name].get("end") == end[:10]:
                continue
            rows, feed = pull(symbol, timeframe, start, end, key, secret)
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["t", "o", "h", "l", "c", "v", "n", "vw"])
            for bar in rows:
                writer.writerow([bar.get(k) for k in ("t", "o", "h", "l", "c", "v", "n", "vw")])
            raw = gzip.compress(buffer.getvalue().encode())
            path = OUT / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            manifest["files"][name] = {"rows": len(rows), "feed": feed, "sha256": hashlib.sha256(raw).hexdigest(),
                                       "start": start[:10], "end": end[:10]}
            manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
            print(f"{timeframe:4s} {symbol:5s} {len(rows):7d} bars ({feed})", flush=True)
    print(f"DONE: {len(manifest['files'])} files in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
