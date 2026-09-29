"""Audit 2026-09-29 R11: the standalone extra_counters.json rewrite is atomic.

``_persist_exit_levels_standalone`` rewrote the file in place with
``open(path, "w")`` on every brain-save cadence; a crash or serializer error
mid-write left truncated JSON and forced a backup restore on the next start.
"""
from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from unittest.mock import MagicMock

import pytest

from backend.organism import brain_persistence
from backend.organism.live_engine import OrganismLiveEngine

PRIOR = {"tick_count": 42, "peak_equity": 100000.0, "exit_levels": {"MSFT": {"entry": 400.0}}}


def _engine(brain_dir: Path) -> OrganismLiveEngine:
    engine = object.__new__(OrganismLiveEngine)
    engine._accounting_lock = RLock()
    engine.brain = MagicMock()
    engine.brain.brain_dir = brain_dir
    engine._pending_entry_order_ids = {"AAPL": "order-1"}
    return engine


def _others(brain_dir: Path) -> list[str]:
    return sorted(p.name for p in brain_dir.iterdir() if p.name != "extra_counters.json")


class _Unprintable:
    """``default=str`` fails on this only after part of the document is encoded."""

    def __str__(self) -> str:
        raise RuntimeError("serializer failed mid-document")


def test_rewrite_goes_through_same_dir_temp_and_replace(tmp_path, monkeypatch):
    ec_path = tmp_path / "extra_counters.json"
    ec_path.write_text(json.dumps(PRIOR))
    replaced = []
    real_replace = brain_persistence.os.replace

    def spy(src, dst):
        replaced.append((Path(src).parent, Path(src).name.endswith(".tmp"), Path(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(brain_persistence.os, "replace", spy)
    _engine(tmp_path)._persist_exit_levels_standalone(
        {"AAPL": {"entry": 150.0}}, {"AAPL": {"direction": 1}},
    )
    data = json.loads(ec_path.read_text())
    assert data["tick_count"] == 42 and data["peak_equity"] == 100000.0
    assert data["exit_levels"] == {"AAPL": {"entry": 150.0}}
    assert data["entry_metadata"] == {"AAPL": {"direction": 1}}
    assert data["pending_entry_order_ids"] == {"AAPL": "order-1"}
    assert replaced == [(tmp_path, True, ec_path)]
    assert _others(tmp_path) == []


@pytest.mark.parametrize("failure", ["serializer", "fsync", "replace"])
def test_failed_rewrite_leaves_previous_file_intact(tmp_path, monkeypatch, failure):
    ec_path = tmp_path / "extra_counters.json"
    ec_path.write_text(json.dumps(PRIOR, indent=2))
    before = ec_path.read_bytes()
    entry_metadata = {"AAPL": {"direction": 1}}
    if failure == "serializer":
        entry_metadata["AAPL"]["bad"] = _Unprintable()
    else:
        def fail(*args, **kwargs):
            raise OSError("disk full")
        monkeypatch.setattr(brain_persistence.os, failure, fail)
    # The method logs and swallows persistence errors (unchanged contract).
    _engine(tmp_path)._persist_exit_levels_standalone({"AAPL": {"entry": 150.0}}, entry_metadata)
    assert ec_path.read_bytes() == before
    assert json.loads(ec_path.read_text()) == PRIOR
    assert _others(tmp_path) == []
