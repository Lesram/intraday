"""Audit 2026-06-09 finding 3.6 — brain save/load race + mid-swap detection.

Root cause of the 2026-06-09 corrupt_head_* snapshots: load() ran lockless
while save()'s "atomic" swap is a file-by-file shutil.move loop, so a load
racing a save observed a half-swapped directory and quarantined a healthy
brain. Fixes under test:

1. save() leaves a .save_complete sentinel; it is absent mid-swap.
2. load() acquires the same exclusive lock save() holds (waits for an
   in-flight save instead of reading a half-swapped dir).
3. A successful load writes the sentinel for legacy brains.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from backend.organism.brain_persistence import (
    LOCK_FILE,
    SAVE_COMPLETE_SENTINEL,
    OrganismBrain,
    _BrainLock,
)


def _make_learner(total_trades=10, generation=3):
    return SimpleNamespace(
        state=SimpleNamespace(
            generation=generation,
            total_trades=total_trades,
            cumulative_pnl=-1.0,
            best_sharpe=0.5,
            total_bars_seen=0,
            retrain_count=0,
            drift_events=0,
            best_generation=0,
            generation_accuracies=[],
            model_metrics=[],
            evaluation_events=[],
        ),
        trade_history=[],
        _reference_features=None,
        _bars_since_retrain=0,
    )


def _make_signal_gen():
    return SimpleNamespace(
        _is_trained=True,
        _feature_cols=["f0", "f1"],
        _xgb_params={},
        _clf=None,
        _reg=None,
        generation=3,
        train_window=1000,
        _latest_metrics=None,
    )


def _seed_brain(tmp_path):
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    brain.save(
        signal_gen=_make_signal_gen(),
        learner=_make_learner(),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=True,
    )
    return brain


def test_save_writes_completion_sentinel(tmp_path):
    brain = _seed_brain(tmp_path)
    assert (brain.brain_dir / SAVE_COMPLETE_SENTINEL).is_file(), (
        "save() must leave a completion sentinel after the swap"
    )


def test_load_succeeds_and_backfills_sentinel_for_legacy_brain(tmp_path):
    brain = _seed_brain(tmp_path)
    # Simulate a legacy (pre-sentinel) brain.
    (brain.brain_dir / SAVE_COMPLETE_SENTINEL).unlink()

    fresh = OrganismBrain(brain_dir=brain.brain_dir)
    assert fresh.load() is True, "legacy brain without sentinel must still load"
    assert (brain.brain_dir / SAVE_COMPLETE_SENTINEL).is_file(), (
        "successful load must backfill the sentinel"
    )


def test_load_waits_for_inflight_save_lock(tmp_path):
    """While the save lock is held, load() must wait — not read through."""
    brain = _seed_brain(tmp_path)

    lock = _BrainLock(brain.brain_dir / LOCK_FILE)
    lock.acquire()  # simulate an in-flight save

    results: dict = {}

    def _load():
        fresh = OrganismBrain(brain_dir=brain.brain_dir)
        t0 = time.monotonic()
        results["ok"] = fresh.load()
        results["elapsed"] = time.monotonic() - t0

    t = threading.Thread(target=_load)
    t.start()
    time.sleep(1.5)  # loader should be blocked waiting on the lock
    assert t.is_alive() or results.get("elapsed", 0) >= 1.0, (
        "load() must wait while the save lock is held"
    )
    lock.release()
    t.join(timeout=30)
    assert results.get("ok") is True, "load must succeed once the save lock clears"


def test_load_roundtrip_after_save(tmp_path):
    brain = _seed_brain(tmp_path)
    fresh = OrganismBrain(brain_dir=brain.brain_dir)
    assert fresh.load() is True
    assert fresh.generation == 3
