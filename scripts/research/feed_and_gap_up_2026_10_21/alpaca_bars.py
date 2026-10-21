"""Minimal Alpaca market-data client for the research scripts in this folder.

Read-only: it calls only the market-data bars endpoint. The API keys are read
from an env file (default ``.env`` in the current directory) and are never
printed, logged or written anywhere. Nothing here imports the live engine.
"""
from __future__ import annotations

import http.client
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://data.alpaca.markets/v2/stocks/bars"

# The 20 symbols the installed release trades (brain universe_selector.active,
# 2026-10-20): the code's default 22 minus SH and PSQ.
LIVE_SYMBOLS = ["NVDA", "XLK", "COST", "AMD", "IWM", "MSFT", "WMT", "QQQ", "AAPL", "AMZN",
                "AVGO", "CAT", "CRM", "GOOGL", "LLY", "META", "SPY", "TSLA", "XLE", "XOM"]


def load_keys(env_path: str | os.PathLike = ".env") -> tuple[str, str]:
    """Return (key_id, secret) from an env file without echoing either."""
    want = {"ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY"}
    vals: dict[str, str] = {}
    for raw in Path(env_path).read_text().splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[7:].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k in want:
            vals[k] = v.strip().strip('"').strip("'")
    missing = want - set(vals)
    if missing:
        sys.exit(f"missing in {env_path}: {sorted(missing)}")
    return vals["ALPACA_API_KEY_ID"], vals["ALPACA_API_SECRET_KEY"]


def _ctx() -> ssl.SSLContext:
    caf = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    return ssl.create_default_context(cafile=caf) if caf else ssl.create_default_context()


def get_bars(params: dict, key: str, sec: str) -> dict[str, list[dict]]:
    """Fetch every page of a multi-symbol bars request; retries transient errors."""
    out: dict[str, list[dict]] = {}
    token = None
    while True:
        p = dict(params)
        if token:
            p["page_token"] = token
        req = urllib.request.Request(BASE + "?" + urllib.parse.urlencode(p), headers={
            "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec, "Accept": "application/json"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60, context=_ctx()) as r:
                    j = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(5 * (attempt + 1))
                    continue
                sys.exit(f"HTTP {e.code}: {e.read()[:200]!r}")
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException,
                    json.JSONDecodeError) as e:
                if attempt < 3:
                    time.sleep(5 * (attempt + 1))
                    continue
                sys.exit(f"network error after retries: {e}")
        for s, bars in (j.get("bars") or {}).items():
            out.setdefault(s, []).extend(bars)
        token = j.get("next_page_token")
        if not token:
            return out
        time.sleep(0.3)


def fetch_minute_bars(start: str, end: str, feed: str, key: str, sec: str,
                      symbols: list[str] = LIVE_SYMBOLS) -> dict[str, list[dict]]:
    return get_bars({"symbols": ",".join(symbols), "timeframe": "1Min", "start": start, "end": end,
                     "feed": feed, "limit": "10000", "adjustment": "raw", "sort": "asc"}, key, sec)
