"""Tests for Phase 5 shadow live-bar fetch helpers."""

from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd

from scripts.phase5_fetch_shadow_bars import (
    summarize_bars,
    symbols_from_events,
    write_outputs,
)


def _bars() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-05-05T14:00:00Z", periods=2, freq="min", tz="UTC"),
        "open": [100.0, 101.0],
        "high": [101.0, 102.0],
        "low": [99.0, 100.0],
        "close": [100.5, 101.5],
        "volume": [1000.0, 1100.0],
    })


def test_symbols_from_events_uses_explicit_or_observed_symbols():
    events = [
        {"symbol": "aapl"},
        {"symbol": "MSFT"},
        {"symbol": ""},
        {"_invalid_json": True, "symbol": "TSLA"},
    ]

    assert symbols_from_events(events) == ["AAPL", "MSFT"]
    assert symbols_from_events(events, " tsla, aapl ") == ["TSLA", "AAPL"]


def test_summarize_bars_reports_ranges_and_empty_frames():
    summary = summarize_bars({
        "AAPL": _bars(),
        "MSFT": pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"]),
    })

    assert summary["AAPL"]["rows"] == 2
    assert summary["AAPL"]["start"].startswith("2026-05-05T14:00:00")
    assert summary["MSFT"]["rows"] == 0


def test_write_outputs_creates_compatible_bars_pickle(tmp_path: Path):
    bars = {"AAPL": _bars()}

    outputs = write_outputs(
        bars,
        tmp_path,
        telemetry_path=tmp_path / "telemetry.jsonl",
        timeframe="1Min",
        lookback=10,
    )

    assert Path(outputs["summary"]).is_file()
    with Path(outputs["bars"]).open("rb") as fh:
        loaded = pickle.load(fh)
    assert list(loaded) == ["AAPL"]
    assert list(loaded["AAPL"].columns) == ["timestamp", "open", "high", "low", "close", "volume"]
