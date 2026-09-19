"""Apr-10 Patch F1 — _write_manifest_guarded helper + save() routing tests.

Verifies:
1. _write_manifest_guarded writes manifest and syncs self._manifest
2. _write_manifest_guarded blocks trained→fresh overwrite (defense-in-depth)
3. _save_manifest delegates to the helper
4. save() early guard still blocks trained→fresh (refactored to use shared check)
5. total_runs uses unified source (in-memory > on-disk > 0)
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from backend.organism.brain_persistence import (
    BRAIN_FORMAT_VERSION,
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
    )


def _read_manifest(brain):
    return json.loads((brain.brain_dir / MANIFEST_FILE).read_text())


def _seed_brain(tmp_path, *, total_trades=195, feature_count=79):
    """Create a brain with a real prior save so manifest+files exist."""
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    brain.save(
        signal_gen=_make_signal_gen(is_trained=True, feature_count=feature_count),
        learner=_make_learner(total_trades=total_trades, generation=27,
                              cumulative_pnl=-492.33, best_sharpe=3.4363),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=True,
    )
    return brain


# ─────────────────────────────────────────────────────────────
# Test 1: _write_manifest_guarded normal write updates self._manifest
# ─────────────────────────────────────────────────────────────

def test_write_manifest_guarded_normal_write(tmp_path):
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    brain.brain_dir.mkdir(parents=True, exist_ok=True)

    learner = _make_learner(total_trades=100, generation=5,
                            cumulative_pnl=-200.0, best_sharpe=2.5)
    sig = _make_signal_gen(is_trained=True, feature_count=42)

    result = brain._write_manifest_guarded(
        brain.brain_dir, sig, learner,
        caller="test",
    )
    assert result is True

    # Manifest written to disk
    m = _read_manifest(brain)
    assert m["generation"] == 5
    assert m["total_trades"] == 100
    assert m["cumulative_pnl"] == -200.0
    assert m["ml_is_trained"] is True
    assert m["feature_count"] == 42
    assert m["total_runs"] == 1  # first save: 0 + 1
    assert m["brain_format_version"] == BRAIN_FORMAT_VERSION

    # self._manifest synced
    assert brain._manifest["generation"] == 5
    assert brain._manifest["total_trades"] == 100
    assert brain._manifest["total_runs"] == 1


# ─────────────────────────────────────────────────────────────
# Test 2: _write_manifest_guarded blocks trained→fresh overwrite
# ─────────────────────────────────────────────────────────────

def test_write_manifest_guarded_blocks_trained_overwrite(tmp_path, caplog):
    brain = _seed_brain(tmp_path, total_trades=195)
    before = _read_manifest(brain)
    assert before["total_trades"] == 195

    import logging
    with caplog.at_level(logging.ERROR):
        result = brain._write_manifest_guarded(
            brain.brain_dir,
            _make_signal_gen(is_trained=False),
            _make_learner(total_trades=0),
            caller="test_block",
            force=False,
        )

    assert result is False
    assert any("BRAIN SAVE BLOCKED (test_block)" in r.getMessage()
               for r in caplog.records)

    # Manifest unchanged
    after = _read_manifest(brain)
    assert after["total_trades"] == 195


# ─────────────────────────────────────────────────────────────
# Test 3: _save_manifest delegates to helper (via total_runs path)
# ─────────────────────────────────────────────────────────────

def test_save_manifest_delegates_to_helper(tmp_path):
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    brain.brain_dir.mkdir(parents=True, exist_ok=True)

    learner = _make_learner(total_trades=50, generation=3)
    sig = _make_signal_gen(is_trained=True, feature_count=20)

    # First save via _save_manifest
    brain._save_manifest(brain.brain_dir, sig, learner, force=True)
    m1 = _read_manifest(brain)
    assert m1["total_trades"] == 50
    assert m1["generation"] == 3
    assert m1["total_runs"] == 1

    # Second save via _save_manifest — total_runs should increment
    brain._save_manifest(brain.brain_dir, sig, learner, force=True)
    m2 = _read_manifest(brain)
    assert m2["total_runs"] == 2

    # self._manifest synced after both calls
    assert brain._manifest["total_runs"] == 2


# ─────────────────────────────────────────────────────────────
# Test 4: save()'s early guard still blocks via shared check
# ─────────────────────────────────────────────────────────────

def test_save_early_guard_blocks_via_shared_check(tmp_path, caplog):
    brain = _seed_brain(tmp_path, total_trades=195)
    before = _read_manifest(brain)
    assert before["total_trades"] == 195
    assert before["ml_is_trained"] is True

    import logging
    with caplog.at_level(logging.ERROR):
        brain.save(
            signal_gen=_make_signal_gen(is_trained=False),
            learner=_make_learner(total_trades=0),
            equity_curve=[100000.0],
            all_trades=[],
            epoch_metrics=[],
            force=False,
        )

    assert any("BRAIN SAVE BLOCKED (save)" in r.getMessage()
               for r in caplog.records)

    # Manifest unchanged
    after = _read_manifest(brain)
    assert after["total_trades"] == 195
    assert after["ml_is_trained"] is True


# ─────────────────────────────────────────────────────────────
# Test 5: total_runs unified — consistent across sequential saves
# ─────────────────────────────────────────────────────────────

def test_total_runs_unified_across_helper_calls(tmp_path):
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    brain.brain_dir.mkdir(parents=True, exist_ok=True)

    learner = _make_learner(total_trades=50, generation=3)
    sig = _make_signal_gen(is_trained=True, feature_count=20)

    # Three sequential writes via the helper
    brain._write_manifest_guarded(brain.brain_dir, sig, learner,
                                   caller="call1")
    m1 = _read_manifest(brain)
    assert m1["total_runs"] == 1

    brain._write_manifest_guarded(brain.brain_dir, sig, learner,
                                   caller="call2")
    m2 = _read_manifest(brain)
    assert m2["total_runs"] == 2

    brain._write_manifest_guarded(brain.brain_dir, sig, learner,
                                   caller="call3")
    m3 = _read_manifest(brain)
    assert m3["total_runs"] == 3

    # Monotonic, no drift
    assert brain._manifest["total_runs"] == 3


# ─────────────────────────────────────────────────────────────
# Test 6: force=True passes through guard in helper
# ─────────────────────────────────────────────────────────────

def test_write_manifest_guarded_force_passes(tmp_path):
    brain = _seed_brain(tmp_path, total_trades=195)
    result = brain._write_manifest_guarded(
        brain.brain_dir,
        _make_signal_gen(is_trained=False),
        _make_learner(total_trades=0),
        caller="force_test",
        force=True,
    )
    assert result is True
    m = _read_manifest(brain)
    assert m["total_trades"] == 0  # overwritten because force=True


# ─────────────────────────────────────────────────────────────
# Test 7: _check_trained_overwrite_guard reads disk when memory empty
# ─────────────────────────────────────────────────────────────

def test_check_guard_reads_disk_fallback(tmp_path):
    """Fresh OrganismBrain instance with empty self._manifest but a
    trained manifest on disk. Guard should still protect."""
    seeded = _seed_brain(tmp_path, total_trades=195)
    seed_dir = seeded.brain_dir

    fresh = OrganismBrain(brain_dir=seed_dir)
    assert not fresh._manifest  # empty, no load() called

    should_block, reason = fresh._check_trained_overwrite_guard(
        seed_dir,
        _make_signal_gen(is_trained=False),
        _make_learner(total_trades=0),
        force=False,
    )
    assert should_block is True
    assert "total_trades=195" in reason
