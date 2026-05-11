"""Fetch live-session bars for Phase 5 shadow telemetry outcomes.

Creates a bars.pkl compatible with the Phase 5 outcome joiner, limited to the
symbols observed in candidate-filter shadow telemetry unless explicitly
overridden. This is evidence-only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pickle
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.integrations.alpaca_data import AlpacaDataClient  # noqa: E402
from scripts.phase3_ml_target_redesign import parse_symbols  # noqa: E402
from scripts.phase4_candidate_shadow_analysis import (  # noqa: E402
    DEFAULT_TELEMETRY_PATH,
    load_shadow_events,
)

DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase5_shadow_live_bars"
_BAR_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def symbols_from_events(events: list[dict[str, Any]], explicit: str | None = None) -> list[str]:
    if explicit:
        return parse_symbols(explicit) or []
    symbols = {
        str(event.get("symbol") or "").strip().upper()
        for event in events
        if not event.get("_invalid_json")
    }
    return sorted(symbol for symbol in symbols if symbol)


def summarize_bars(bars: dict[str, pd.DataFrame]) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for symbol, frame in bars.items():
        if frame.empty:
            rows[symbol] = {"rows": 0, "start": None, "end": None}
            continue
        timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        rows[symbol] = {
            "rows": int(len(frame)),
            "start": pd.Timestamp(timestamps.min()).isoformat(),
            "end": pd.Timestamp(timestamps.max()).isoformat(),
        }
    return rows


def _parse_event_timestamps(events: list[dict[str, Any]]) -> list[pd.Timestamp]:
    timestamps: list[pd.Timestamp] = []
    for event in events:
        if event.get("_invalid_json"):
            continue
        raw = event.get("timestamp")
        if raw is None:
            continue
        timestamp = pd.to_datetime(str(raw), utc=True, errors="coerce")
        if pd.isna(timestamp):
            continue
        timestamps.append(pd.Timestamp(timestamp))
    return timestamps


def event_time_window(
    events: list[dict[str, Any]],
    *,
    pre_event_padding_minutes: int = 30,
    post_event_padding_minutes: int = 90,
    now: datetime | None = None,
) -> dict[str, str] | None:
    """Return an RFC3339 window that brackets observed shadow events.

    Phase 5 needs bars around the event timestamps. A broad ascending Alpaca
    query can truncate to stale early-history bars before reaching the paper
    session, so the default fetch path is event-windowed.
    """
    timestamps = _parse_event_timestamps(events)
    if not timestamps:
        return None

    start = min(timestamps) - timedelta(minutes=max(pre_event_padding_minutes, 0))
    end = max(timestamps) + timedelta(minutes=max(post_event_padding_minutes, 0))
    now_ts = pd.Timestamp(now or datetime.now(UTC))
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    else:
        now_ts = now_ts.tz_convert("UTC")
    if end > now_ts:
        end = now_ts
    if end <= start:
        end = max(timestamps) + timedelta(minutes=15)
    return {
        "start": start.isoformat().replace("+00:00", "Z"),
        "end": end.isoformat().replace("+00:00", "Z"),
    }


def normalize_alpaca_bar_rows(raw_bars: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for bar in raw_bars:
        rows.append({
            "timestamp": bar.get("t"),
            "open": float(bar.get("o")) if bar.get("o") is not None else None,
            "high": float(bar.get("h")) if bar.get("h") is not None else None,
            "low": float(bar.get("l")) if bar.get("l") is not None else None,
            "close": float(bar.get("c")) if bar.get("c") is not None else None,
            "volume": float(bar.get("v")) if bar.get("v") is not None else None,
        })
    frame = pd.DataFrame(rows, columns=_BAR_COLUMNS)
    if frame.empty:
        return pd.DataFrame(columns=_BAR_COLUMNS)
    return frame.sort_values("timestamp").reset_index(drop=True)


async def fetch_symbol_bars(
    symbols: list[str],
    *,
    lookback: int,
    timeframe: str,
    query_window: dict[str, str] | None = None,
) -> dict[str, pd.DataFrame]:
    client = AlpacaDataClient()
    bars: dict[str, pd.DataFrame] = {}
    try:
        for symbol in symbols:
            if query_window:
                url = f"{client.base_url}/stocks/{symbol.upper()}/bars"
                params = {
                    "start": query_window["start"],
                    "end": query_window["end"],
                    "timeframe": timeframe,
                    "adjustment": "split",
                    "limit": min(max(lookback * 2, 10_000), 10_000),
                    "sort": "asc",
                    "feed": os.getenv("ALPACA_DATA_FEED", "sip"),
                }
                response = await client._request_with_retry(  # noqa: SLF001
                    "GET",
                    url,
                    params=params,
                    headers=client._get_auth_headers(),  # noqa: SLF001
                )
                if response.status_code != 200:
                    raise RuntimeError(
                        f"Alpaca bars fetch failed for {symbol}: "
                        f"{response.status_code} {response.text[:200]}"
                    )
                frame = normalize_alpaca_bar_rows(response.json().get("bars", []))
            else:
                frame = await client.get_historical_bars_df(
                    symbol,
                    lookback=lookback,
                    timeframe=timeframe,
                )
            bars[symbol] = frame
    finally:
        await client.close()
    return bars


def write_outputs(
    bars: dict[str, pd.DataFrame],
    out_dir: Path,
    *,
    telemetry_path: Path,
    timeframe: str,
    lookback: int,
    query_window: dict[str, str] | None = None,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    bars_path = out_dir / "bars.pkl"
    summary_path = out_dir / "summary_shadow_live_bars.json"
    with bars_path.open("wb") as fh:
        pickle.dump(bars, fh)
    summary = {
        "scope": "phase5_shadow_live_bar_fetch_no_live_behavior_change",
        "generated_at": datetime.now(UTC).isoformat(),
        "telemetry_path": str(telemetry_path),
        "timeframe": timeframe,
        "lookback": lookback,
        "query_window": query_window,
        "symbols": sorted(bars),
        "bar_metadata": summarize_bars(bars),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return {"bars": str(bars_path), "summary": str(summary_path)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telemetry-path", type=Path, default=DEFAULT_TELEMETRY_PATH)
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--lookback", type=int, default=1000)
    parser.add_argument("--timeframe", default="1Min")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--pre-event-padding-minutes", type=int, default=30)
    parser.add_argument("--post-event-padding-minutes", type=int, default=90)
    parser.add_argument("--disable-event-window", action="store_true")
    return parser.parse_args(argv)


async def async_main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv(args.env_file)
    events = load_shadow_events(args.telemetry_path)
    symbols = symbols_from_events(events, args.symbols)
    query_window = None
    if not args.disable_event_window:
        query_window = event_time_window(
            events,
            pre_event_padding_minutes=args.pre_event_padding_minutes,
            post_event_padding_minutes=args.post_event_padding_minutes,
        )
    if not symbols:
        bars: dict[str, pd.DataFrame] = {}
    else:
        bars = await fetch_symbol_bars(
            symbols,
            lookback=args.lookback,
            timeframe=args.timeframe,
            query_window=query_window,
        )
    outputs = write_outputs(
        bars,
        args.out_dir,
        telemetry_path=args.telemetry_path,
        timeframe=args.timeframe,
        lookback=args.lookback,
        query_window=query_window,
    )
    print(json.dumps(outputs, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
