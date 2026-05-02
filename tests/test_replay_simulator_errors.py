"""Audit-M finding M-12 (2026-05-02): negative tests for ReplayEngine error paths.

Three `raise ValueError(...)` sites in backend/organism/replay_simulator.py
were previously untested. This file asserts each fires with the expected
message under the expected precondition.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.organism.replay_simulator import ReplayEngine


async def test_from_alpaca_raises_when_keys_missing(monkeypatch):
    """ReplayEngine.from_alpaca should raise ValueError if Alpaca keys are absent."""
    for var in (
        "ALPACA_API_KEY_ID",
        "ALPACA_API_KEY",
        "ALPACA_API_SECRET_KEY",
        "ALPACA_SECRET_KEY",
    ):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(ValueError, match="ALPACA_API_KEY"):
        await ReplayEngine.from_alpaca(
            symbols=["SPY"],
            start="2026-01-01",
            end="2026-01-02",
            timeframe="1Min",
        )


async def test_from_alpaca_raises_when_no_bars_loaded(monkeypatch):
    """ReplayEngine.from_alpaca should raise ValueError if no symbol returns bars."""
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test-key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "test-secret")

    class _FakeAlpacaClient:
        def __init__(self, **kwargs):
            pass

        def get_historical_data(self, *args, **kwargs):
            return None  # simulate no bars for any symbol

    import backend.data.alpaca_client as ac_mod
    monkeypatch.setattr(ac_mod, "AlpacaClient", _FakeAlpacaClient)

    with pytest.raises(ValueError, match="No bars loaded"):
        await ReplayEngine.from_alpaca(
            symbols=["SPY", "QQQ"],
            start="2026-01-01",
            end="2026-01-02",
            timeframe="1Min",
        )


def test_from_csv_raises_when_directory_empty(tmp_path: Path):
    """ReplayEngine.from_csv should raise ValueError if no CSVs are found."""
    empty_dir = tmp_path / "empty_csvs"
    empty_dir.mkdir()

    with pytest.raises(ValueError, match="No CSV files found"):
        ReplayEngine.from_csv(str(empty_dir))
