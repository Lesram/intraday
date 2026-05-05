"""Fetch live-session bars for Phase 5 shadow telemetry outcomes.

Creates a bars.pkl compatible with the Phase 5 outcome joiner, limited to the
symbols observed in candidate-filter shadow telemetry unless explicitly
overridden. This is evidence-only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pickle
import sys
from datetime import UTC, datetime
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


async def fetch_symbol_bars(
    symbols: list[str],
    *,
    lookback: int,
    timeframe: str,
) -> dict[str, pd.DataFrame]:
    client = AlpacaDataClient()
    bars: dict[str, pd.DataFrame] = {}
    try:
        for symbol in symbols:
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
    return parser.parse_args(argv)


async def async_main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv(args.env_file)
    events = load_shadow_events(args.telemetry_path)
    symbols = symbols_from_events(events, args.symbols)
    if not symbols:
        bars: dict[str, pd.DataFrame] = {}
    else:
        bars = await fetch_symbol_bars(
            symbols,
            lookback=args.lookback,
            timeframe=args.timeframe,
        )
    outputs = write_outputs(
        bars,
        args.out_dir,
        telemetry_path=args.telemetry_path,
        timeframe=args.timeframe,
        lookback=args.lookback,
    )
    print(json.dumps(outputs, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
