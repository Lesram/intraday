#!/usr/bin/env python3
"""Fetch a broad minute-bar corpus for the exit-logic experiment (Task A).

The cached corpus was ~8 benign April days / 34 trades — too small and not
representative for a Gate-2 read. This fetches 1-min bars for the 22-symbol
universe over the full live span (Mar 30 – Jun 19 2026) via Alpaca (SIP), and
writes artifacts/broad_corpus/bars.pkl in the dict[symbol -> DataFrame] format
collect_cached_bars() expects (it globs artifacts/**/bars*.pkl and dedups by
symbol+date, so this becomes the authoritative source for the broad window).

Run from repo root WITH Alpaca creds in env:
    set -a; source .env; set +a
    ./venv/bin/python scripts/fetch_broad_corpus.py
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Same 22-symbol set the prior replays kept (COIN/NFLX excluded as thin).
SYMBOLS = [
    "AAPL", "AMD", "AMZN", "AVGO", "CAT", "COST", "CRM", "GOOGL", "IWM", "LLY",
    "META", "MSFT", "NVDA", "PSQ", "QQQ", "SH", "SPY", "TSLA", "WMT", "XLE",
    "XLK", "XOM",
]
# Override via argv: fetch_broad_corpus.py [START END [OUT_SUBDIR]]
START = sys.argv[1] if len(sys.argv) > 1 else "2026-03-30"
END = sys.argv[2] if len(sys.argv) > 2 else "2026-06-19"
OUT_SUBDIR = sys.argv[3] if len(sys.argv) > 3 else "broad_corpus"


def main() -> None:
    import os

    from backend.data.alpaca_client import AlpacaClient

    key = os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY")
    sec = os.environ.get("ALPACA_API_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY")
    if not key or not sec:
        raise SystemExit("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY not in env "
                         "(run: set -a; source .env; set +a)")
    client = AlpacaClient(api_key=key, secret_key=sec, paper=True)

    bars: dict[str, object] = {}
    for sym in SYMBOLS:
        try:
            df = client.get_historical_data(
                sym, timeframe="1Min", start=START, end=END, limit=60_000,
            )
        except Exception as e:  # noqa: BLE001
            print(f"  {sym}: FETCH FAILED {e}", flush=True)
            continue
        if df is None or df.empty:
            print(f"  {sym}: EMPTY", flush=True)
            continue
        rename = {"Open": "open", "High": "high", "Low": "low",
                  "Close": "close", "Volume": "volume"}
        df = df.rename(columns=rename)
        if "timestamp" not in df.columns or "close" not in df.columns:
            print(f"  {sym}: missing timestamp/close cols {list(df.columns)}", flush=True)
            continue
        bars[sym] = df
        ts = df["timestamp"]
        print(f"  {sym}: {len(df)} bars  {ts.min()} -> {ts.max()}", flush=True)

    if not bars:
        raise SystemExit("No bars fetched for any symbol.")

    out_dir = ROOT / "artifacts" / OUT_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "bars.pkl"
    with open(out, "wb") as fh:
        pickle.dump(bars, fh)
    tot = sum(len(d) for d in bars.values())
    print(f"\nWrote {out}: {len(bars)} symbols, {tot} total bars "
          f"({START} -> {END}).", flush=True)


if __name__ == "__main__":
    main()
