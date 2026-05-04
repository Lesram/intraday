"""Apr-8 Patch E — trained-state overwrite guard regression tests.

BrainPersistence.save() refuses to overwrite a manifest showing
total_trades>0 OR ml_is_trained==True with an incoming fresh
learner/signal_gen state, unless force=True.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from backend.organism.brain_persistence import MANIFEST_FILE, OrganismBrain


def _make_learner(total_trades=0):
    return SimpleNamespace(
        state=SimpleNamespace(
            generation=0,
            total_trades=total_trades,
            cumulative_pnl=0.0,
            best_sharpe=float("-inf"),
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


def _seed_brain(tmp_path, *, total_trades, ml_trained, feature_count=42):
    """Create a brain with a real prior save so manifest+files exist."""
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    brain.save(
        signal_gen=_make_signal_gen(is_trained=ml_trained, feature_count=feature_count),
        learner=_make_learner(total_trades=total_trades),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=True,
    )
    return brain


# ─────────────────────────────────────────────────────────────
# 1. Guard blocks zero-overwrite of trained manifest
# ─────────────────────────────────────────────────────────────

def test_guard_blocks_zero_overwrite_of_trained(tmp_path):
    brain = _seed_brain(tmp_path, total_trades=195, ml_trained=True)
    before = _read_manifest(brain)
    assert before["total_trades"] == 195
    assert before["ml_is_trained"] is True

    brain.save(
        signal_gen=_make_signal_gen(is_trained=False, feature_count=0),
        learner=_make_learner(total_trades=0),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=False,
    )

    after = _read_manifest(brain)
    assert after["total_trades"] == 195
    assert after["ml_is_trained"] is True


# ─────────────────────────────────────────────────────────────
# 2. Guard allows save with incoming trained state
# ─────────────────────────────────────────────────────────────

def test_guard_allows_save_with_trained_incoming(tmp_path):
    brain = _seed_brain(tmp_path, total_trades=195, ml_trained=True)
    brain.save(
        signal_gen=_make_signal_gen(is_trained=True, feature_count=42),
        learner=_make_learner(total_trades=200),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=False,
    )
    m = _read_manifest(brain)
    assert m["total_trades"] == 200
    assert m["ml_is_trained"] is True


# ─────────────────────────────────────────────────────────────
# 3. Guard allows save when existing manifest is untrained
# ─────────────────────────────────────────────────────────────

def test_guard_allows_save_when_existing_untrained(tmp_path):
    brain = _seed_brain(tmp_path, total_trades=0, ml_trained=False, feature_count=0)
    brain.save(
        signal_gen=_make_signal_gen(is_trained=False, feature_count=0),
        learner=_make_learner(total_trades=0),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=False,
    )
    m = _read_manifest(brain)
    assert m["total_trades"] == 0


# ─────────────────────────────────────────────────────────────
# 4. force=True bypasses guard
# ─────────────────────────────────────────────────────────────

def test_force_true_bypasses_guard(tmp_path):
    # F3: force=True alone is no longer enough; full break-glass triad required.
    brain = _seed_brain(tmp_path, total_trades=195, ml_trained=True)
    brain.save(
        signal_gen=_make_signal_gen(is_trained=False, feature_count=0),
        learner=_make_learner(total_trades=0),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=True,
        allow_reset=True,
        reset_reason="test break-glass",
    )
    m = _read_manifest(brain)
    assert m["total_trades"] == 0
    assert m["ml_is_trained"] is False


# ─────────────────────────────────────────────────────────────
# 5. Existing trades>0 + incoming trained models → allowed
# ─────────────────────────────────────────────────────────────

def test_guard_allows_existing_trades_incoming_trained(tmp_path):
    brain = _seed_brain(tmp_path, total_trades=195, ml_trained=True)
    brain.save(
        signal_gen=_make_signal_gen(is_trained=True, feature_count=42),
        learner=_make_learner(total_trades=0),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=False,
    )
    m = _read_manifest(brain)
    # incoming trained → guard does not fire
    assert m["ml_is_trained"] is True


# ─────────────────────────────────────────────────────────────
# 6. Existing ml_is_trained=True + incoming trades>0 → allowed
# ─────────────────────────────────────────────────────────────

def test_guard_allows_existing_trained_incoming_trades(tmp_path):
    brain = _seed_brain(tmp_path, total_trades=195, ml_trained=True)
    brain.save(
        signal_gen=_make_signal_gen(is_trained=False, feature_count=0),
        learner=_make_learner(total_trades=10),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=False,
    )
    m = _read_manifest(brain)
    assert m["total_trades"] == 10


# ─────────────────────────────────────────────────────────────
# 7. Empty self._manifest → fresh save proceeds
# ─────────────────────────────────────────────────────────────

def test_guard_empty_manifest_allows_fresh_save(tmp_path):
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    assert brain._manifest == {} or not brain._manifest
    brain.save(
        signal_gen=_make_signal_gen(is_trained=False, feature_count=0),
        learner=_make_learner(total_trades=0),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=False,
    )
    assert (brain.brain_dir / MANIFEST_FILE).exists()


# ─────────────────────────────────────────────────────────────
# 8. learner=None handled gracefully by guard
# ─────────────────────────────────────────────────────────────

def test_guard_handles_none_learner(tmp_path):
    brain = _seed_brain(tmp_path, total_trades=195, ml_trained=True)
    # learner=None: guard treats incoming_trades=0; signal_gen untrained;
    # existing manifest is trained → guard should BLOCK (no crash).
    brain.save(
        signal_gen=_make_signal_gen(is_trained=False, feature_count=0),
        learner=None,
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=False,
    )
    m = _read_manifest(brain)
    assert m["total_trades"] == 195
