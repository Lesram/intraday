"""Apr-9 Patch F-lite — trained-state overwrite guard extended to
BrainPersistence.save_essential_state().

Closes the Patch E gap: save_essential_state() now refuses to overwrite a
manifest showing total_trades>0 OR ml_is_trained==True with an incoming
fresh learner/signal_gen. Unlike save(), there is no force flag — the
essential-save path is protected unconditionally. This is the specific
failure mode observed in the 2026-04-08 02:08 UTC and 2026-04-09 02:58 UTC
wipe incidents.

Guard also works when self._manifest is empty (fresh OrganismBrain instance
pointing at an already-trained brain dir) by falling back to on-disk
manifest.json.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from backend.organism.brain_persistence import MANIFEST_FILE, OrganismBrain


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


def _seed_trained_brain(tmp_path, *, total_trades=195, feature_count=79):
    """Create a brain with a healthy prior full save (force=True to bypass
    the save() guard during test setup). Returns the brain instance with
    self._manifest populated from the save."""
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    brain.save(
        signal_gen=_make_signal_gen(is_trained=True, feature_count=feature_count),
        learner=_make_learner(
            total_trades=total_trades,
            generation=27,
            cumulative_pnl=-492.33,
            best_sharpe=3.4363,
        ),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=True,
    )
    return brain


# ─────────────────────────────────────────────────────────────
# Test 1: save_essential_state BLOCKS trained→untrained overwrite
# ─────────────────────────────────────────────────────────────

def test_essential_state_guard_blocks_trained_overwrite(tmp_path, caplog):
    brain = _seed_trained_brain(tmp_path, total_trades=195, feature_count=79)
    before = _read_manifest(brain)
    assert before["total_trades"] == 195
    assert before["ml_is_trained"] is True
    assert before["feature_count"] == 79
    assert before["generation"] == 27

    import logging
    with caplog.at_level(logging.ERROR):
        brain.save_essential_state(
            signal_gen=_make_signal_gen(is_trained=False, feature_count=0),
            learner=_make_learner(total_trades=0),
            all_trades=[],
            equity_curve=[100000.0],
            epoch_metrics=[],
        )

    # Guard fired: BRAIN SAVE BLOCKED log
    assert any(
        "BRAIN SAVE BLOCKED (save_essential_state)" in r.getMessage()
        for r in caplog.records
    ), (
        "Expected 'BRAIN SAVE BLOCKED (save_essential_state)' ERROR log. "
        f"Got: {[r.getMessage() for r in caplog.records]}"
    )

    # Manifest unchanged
    after = _read_manifest(brain)
    assert after["total_trades"] == 195
    assert after["ml_is_trained"] is True
    assert after["feature_count"] == 79
    assert after["generation"] == 27


# ─────────────────────────────────────────────────────────────
# Test 2: save_essential_state ALLOWS normal trained save
# ─────────────────────────────────────────────────────────────

def test_essential_state_guard_allows_healthy_save(tmp_path):
    brain = _seed_trained_brain(tmp_path, total_trades=195, feature_count=79)
    before = _read_manifest(brain)
    assert before["total_trades"] == 195

    # Healthy live learner + trained signal_gen — should succeed
    brain.save_essential_state(
        signal_gen=_make_signal_gen(is_trained=True, feature_count=79),
        learner=_make_learner(
            total_trades=200,
            generation=28,
            cumulative_pnl=-480.0,
            best_sharpe=3.5,
        ),
        all_trades=[],
        equity_curve=[100000.0],
        epoch_metrics=[],
    )

    after = _read_manifest(brain)
    # Essential-save updates total_trades / cumulative_pnl from live state
    # via _apply_live_manifest_fields (Patch B).
    assert after["total_trades"] == 200
    assert after["cumulative_pnl"] == -480.0
    assert after["ml_is_trained"] is True
    assert after["feature_count"] == 79


# ─────────────────────────────────────────────────────────────
# Test 3: fresh OrganismBrain instance reads from disk fallback
# ─────────────────────────────────────────────────────────────

def test_essential_state_guard_reads_disk_when_memory_empty(tmp_path):
    """A freshly-instantiated OrganismBrain pointing at an already-trained
    brain dir has self._manifest empty until load() is called. The guard
    must still protect the on-disk trained state by falling back to reading
    manifest.json from disk."""
    # Step 1: seed a trained brain
    seeded = _seed_trained_brain(tmp_path, total_trades=195, feature_count=79)
    seed_dir = seeded.brain_dir

    # Step 2: create a BRAND NEW OrganismBrain instance at the same dir
    # without calling load(). self._manifest will be empty.
    fresh = OrganismBrain(brain_dir=seed_dir)
    assert fresh._manifest == {} or not fresh._manifest, (
        f"Expected empty self._manifest on fresh instance, got {fresh._manifest}"
    )

    # Step 3: attempt a trained→fresh overwrite via save_essential_state
    import logging
    import io
    logger = logging.getLogger("backend.organism.brain_persistence")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.ERROR)
    logger.addHandler(handler)
    try:
        fresh.save_essential_state(
            signal_gen=_make_signal_gen(is_trained=False, feature_count=0),
            learner=_make_learner(total_trades=0),
            all_trades=[],
            equity_curve=[100000.0],
            epoch_metrics=[],
        )
    finally:
        logger.removeHandler(handler)

    log_output = stream.getvalue()
    assert "BRAIN SAVE BLOCKED (save_essential_state)" in log_output, (
        "Expected guard to fire via disk fallback when self._manifest is empty. "
        f"Log output: {log_output!r}"
    )

    # Manifest on disk unchanged
    after = json.loads((seed_dir / MANIFEST_FILE).read_text())
    assert after["total_trades"] == 195
    assert after["ml_is_trained"] is True
    assert after["generation"] == 27
