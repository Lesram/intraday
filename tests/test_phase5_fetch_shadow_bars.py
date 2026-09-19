"""Tests for Phase 5 shadow live-bar fetch helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import pickle
from pathlib import Path

import pandas as pd

from scripts.phase5_fetch_shadow_bars import (
    event_time_window,
    normalize_alpaca_bar_rows,
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


def test_event_time_window_brackets_shadow_timestamps_and_clips_future_end():
    events = [
        {"timestamp": "2026-05-05T14:09:44Z"},
        {"timestamp": "not-a-date"},
        {"timestamp": "2026-05-05T19:38:09Z"},
        {"_invalid_json": True, "timestamp": "2026-05-06T00:00:00Z"},
    ]

    window = event_time_window(
        events,
        pre_event_padding_minutes=10,
        post_event_padding_minutes=90,
        now=datetime(2026, 5, 5, 20, 30, tzinfo=UTC),
    )

    assert window == {
        "start": "2026-05-05T13:59:44+00:00".replace("+00:00", "Z"),
        "end": "2026-05-05T20:30:00Z",
    }


def test_normalize_alpaca_bar_rows_maps_and_sorts_rows():
    frame = normalize_alpaca_bar_rows([
        {"t": "2026-05-05T14:01:00Z", "o": 101, "h": 102, "l": 100, "c": 101.5, "v": 2},
        {"t": "2026-05-05T14:00:00Z", "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 1},
    ])

    assert list(frame.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert list(frame["timestamp"]) == [
        "2026-05-05T14:00:00Z",
        "2026-05-05T14:01:00Z",
    ]
    assert list(frame["close"]) == [100.5, 101.5]


def test_write_outputs_creates_compatible_bars_pickle(tmp_path: Path):
    bars = {"AAPL": _bars()}

    outputs = write_outputs(
        bars,
        tmp_path,
        telemetry_path=tmp_path / "telemetry.jsonl",
        timeframe="1Min",
        lookback=10,
        query_window={"start": "2026-05-05T14:00:00Z", "end": "2026-05-05T20:00:00Z"},
    )

    assert Path(outputs["summary"]).is_file()
    with Path(outputs["bars"]).open("rb") as fh:
        loaded = pickle.load(fh)
    assert list(loaded) == ["AAPL"]
    assert list(loaded["AAPL"].columns) == ["timestamp", "open", "high", "low", "close", "volume"]
