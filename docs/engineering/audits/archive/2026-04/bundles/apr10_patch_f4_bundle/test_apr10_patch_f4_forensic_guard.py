"""Apr-10 Patch F4 — LiveEngine forensic guard + bypass audit + wipe simulation.

Tests:
1. Forensic guard logs CRITICAL on learner replacement
2. Forensic guard logs CRITICAL on signal_gen replacement
3. Forensic guard blocks save when trained disk + fresh/untrained runtime
4. Bypass audit: only 2 _write_json(MANIFEST_FILE) callsites exist
5. Full-stack wipe simulation: trained disk + regressive incoming → blocked + instrumented
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.organism.brain_persistence import (
    MANIFEST_FILE,
    OrganismBrain,
)


def _make_learner(total_trades=0, generation=0, cumulative_pnl=0.0,
                  best_sharpe=float("-inf")):
    return SimpleNamespace(
        state=SimpleNamespace(
            generation=generation,
            total_trades=total_trades,
            cumulative_pnl=cumulative_pnl,
            best_sharpe=best_sharpe,
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


def _make_signal_gen(is_trained=False, feature_count=0):
    return SimpleNamespace(
        _is_trained=is_trained,
        _feature_cols=[f"f{i}" for i in range(feature_count)],
        _xgb_params={},
        _clf=None,
        _reg=None,
        generation=0,
        train_window=1000,
        _latest_metrics=None,
        _ensemble=None,
    )


def _read_manifest_from_path(brain_dir):
    return json.loads((Path(brain_dir) / MANIFEST_FILE).read_text())


def _seed_trained_manifest(brain_dir, total_trades=195, generation=27):
    """Write a trained manifest directly to disk for testing."""
    brain_dir = Path(brain_dir)
    brain_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "brain_format_version": 2,
        "saved_at": "2026-04-09T20:00:00+00:00",
        "generation": generation,
        "total_runs": 100,
        "total_trades": total_trades,
        "cumulative_pnl": -492.33,
        "best_sharpe": 3.4363,
        "ml_is_trained": True,
        "feature_count": 79,
    }
    (brain_dir / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2))
    return manifest


# ─────────────────────────────────────────────────────────────
# Test 1: Forensic guard logs on learner replacement
# ─────────────────────────────────────────────────────────────

def test_forensic_guard_learner_replacement(tmp_path, caplog):
    """If self.learner is replaced after __init__, _save_brain logs CRITICAL."""
    from backend.organism.live_engine import OrganismLiveEngine

    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    # Minimal init for forensic guard
    engine.signal_gen = _make_signal_gen(is_trained=True, feature_count=79)
    engine.learner = _make_learner(total_trades=200, generation=27)
    engine._forensic_signal_gen_id = id(engine.signal_gen)
    engine._forensic_learner_id = id(engine.learner)

    # Set up brain
    brain_dir = tmp_path / "brain"
    _seed_trained_manifest(brain_dir)
    engine.brain = OrganismBrain(brain_dir=brain_dir)
    engine.brain._manifest = _read_manifest_from_path(brain_dir)

    # Mock out the rest of _save_brain's dependencies
    engine._exit_levels = {}
    engine._entry_metadata = {}
    engine._persist_exit_levels_standalone = MagicMock()
    engine._all_trades = []
    engine._tick_count = 100
    engine._watchdog_last_brain_save_tick = 0

    # REPLACE the learner (simulates unexpected object swap)
    engine.learner = _make_learner(total_trades=200, generation=27)
    # id() has changed

    with caplog.at_level(logging.CRITICAL):
        engine._save_brain()

    assert any(
        "FORENSIC GUARD" in r.getMessage()
        and "identity changed" in r.getMessage()
        for r in caplog.records
    ), f"Expected FORENSIC GUARD CRITICAL log. Got: {[r.getMessage()[:80] for r in caplog.records]}"


# ─────────────────────────────────────────────────────────────
# Test 2: Forensic guard logs on signal_gen replacement
# ─────────────────────────────────────────────────────────────

def test_forensic_guard_signal_gen_replacement(tmp_path, caplog):
    from backend.organism.live_engine import OrganismLiveEngine

    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    engine.signal_gen = _make_signal_gen(is_trained=True, feature_count=79)
    engine.learner = _make_learner(total_trades=200, generation=27)
    engine._forensic_signal_gen_id = id(engine.signal_gen)
    engine._forensic_learner_id = id(engine.learner)

    brain_dir = tmp_path / "brain"
    _seed_trained_manifest(brain_dir)
    engine.brain = OrganismBrain(brain_dir=brain_dir)
    engine.brain._manifest = _read_manifest_from_path(brain_dir)
    engine._exit_levels = {}
    engine._entry_metadata = {}
    engine._persist_exit_levels_standalone = MagicMock()
    engine._all_trades = []
    engine._tick_count = 100
    engine._watchdog_last_brain_save_tick = 0

    # REPLACE signal_gen
    engine.signal_gen = _make_signal_gen(is_trained=True, feature_count=79)

    with caplog.at_level(logging.CRITICAL):
        engine._save_brain()

    assert any(
        "FORENSIC GUARD" in r.getMessage()
        and "identity changed" in r.getMessage()
        for r in caplog.records
    )


# ─────────────────────────────────────────────────────────────
# Test 3: Forensic guard blocks save when disk trained + runtime fresh
# ─────────────────────────────────────────────────────────────

def test_forensic_guard_blocks_regression(tmp_path, caplog):
    """If learner.state.total_trades=0 but disk shows trained,
    _save_brain aborts with CRITICAL."""
    from backend.organism.live_engine import OrganismLiveEngine

    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    engine.signal_gen = _make_signal_gen(is_trained=False)
    engine.learner = _make_learner(total_trades=0)
    engine._forensic_signal_gen_id = id(engine.signal_gen)
    engine._forensic_learner_id = id(engine.learner)

    brain_dir = tmp_path / "brain"
    _seed_trained_manifest(brain_dir, total_trades=195)
    engine.brain = OrganismBrain(brain_dir=brain_dir)
    engine.brain._manifest = _read_manifest_from_path(brain_dir)
    engine._exit_levels = {}
    engine._entry_metadata = {}
    engine._persist_exit_levels_standalone = MagicMock()
    engine._all_trades = []
    engine._tick_count = 100
    engine._watchdog_last_brain_save_tick = 0

    with caplog.at_level(logging.CRITICAL):
        engine._save_brain()

    # Regression guard should have aborted
    assert any(
        "FORENSIC GUARD" in r.getMessage()
        and "Learner state regressed" in r.getMessage()
        for r in caplog.records
    ), f"Expected regression CRITICAL. Got: {[r.getMessage()[:80] for r in caplog.records]}"

    # Manifest on disk unchanged
    after = _read_manifest_from_path(brain_dir)
    assert after["total_trades"] == 195


# ─────────────────────────────────────────────────────────────
# Test 4: Bypass audit — only 2 _write_json(MANIFEST_FILE) callsites
# ─────────────────────────────────────────────────────────────

def test_bypass_audit_manifest_write_callsites():
    """Exactly 2 callsites for _write_json(...MANIFEST_FILE...) in
    brain_persistence.py: the guarded helper and the migration path.
    Any new direct write is a regression."""
    result = subprocess.run(
        [
            sys.executable, "-c",
            "import re, pathlib;"
            "src = pathlib.Path('backend/organism/brain_persistence.py').read_text();"
            "hits = [(i+1, line.strip()) for i, line in enumerate(src.splitlines())"
            "    if '_write_json' in line and 'MANIFEST_FILE' in line];"
            "print(len(hits));"
            "[print(f'  L{n}: {l}') for n, l in hits]",
        ],
        capture_output=True, text=True, cwd="/Users/marselkei/VS/intra",
    )
    output = result.stdout.strip()
    count = int(output.split("\n")[0])
    assert count == 2, (
        f"Expected exactly 2 _write_json(MANIFEST_FILE) callsites "
        f"(guarded helper + migration). Found {count}:\n{output}"
    )


# ─────────────────────────────────────────────────────────────
# Test 5: Full-stack wipe simulation
# ─────────────────────────────────────────────────────────────

def test_full_stack_wipe_simulation(tmp_path, caplog):
    """Simulate the Apr 8/9 wipe: trained brain on disk, regressive
    incoming state via save_essential_state. Must:
    - preserve disk state
    - fire SUSPICIOUS MANIFEST WRITE or BRAIN SAVE BLOCKED
    - not silently succeed"""

    # Step 1: seed trained brain
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    brain.save(
        signal_gen=_make_signal_gen(is_trained=True, feature_count=79),
        learner=_make_learner(total_trades=195, generation=27,
                              cumulative_pnl=-492.33, best_sharpe=3.4363),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=True,
        allow_reset=True,
        reset_reason="wipe simulation seed",
    )
    before = _read_manifest_from_path(tmp_path / "brain")
    assert before["total_trades"] == 195
    assert before["ml_is_trained"] is True

    # Step 2: attempt regressive save_essential_state (the exact wipe path)
    with caplog.at_level(logging.WARNING):
        brain.save_essential_state(
            signal_gen=_make_signal_gen(is_trained=False),
            learner=_make_learner(total_trades=0),
            all_trades=[],
        )

    # Step 3: verify disk is preserved
    after = _read_manifest_from_path(tmp_path / "brain")
    assert after["total_trades"] == 195, (
        f"Wipe simulation FAILED: manifest was overwritten! "
        f"total_trades={after['total_trades']}"
    )
    assert after["ml_is_trained"] is True

    # Step 4: verify instrumentation or block log fired
    all_msgs = [r.getMessage() for r in caplog.records]
    has_block = any("BRAIN SAVE BLOCKED" in m for m in all_msgs)
    has_suspicious = any("SUSPICIOUS MANIFEST WRITE" in m for m in all_msgs)
    assert has_block or has_suspicious, (
        f"Expected BRAIN SAVE BLOCKED or SUSPICIOUS MANIFEST WRITE log. "
        f"Got: {[m[:80] for m in all_msgs]}"
    )
