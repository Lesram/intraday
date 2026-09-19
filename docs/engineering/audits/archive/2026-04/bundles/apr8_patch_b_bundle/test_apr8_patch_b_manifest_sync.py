"""Apr-8 Patch B — manifest sync regression tests.

Recovery incident (2026-04-08): learning_state.json was healthy
(gen=18, total_trades=195, best_sharpe=2.8956) while manifest.json was
stale (gen=0, best_sharpe=0, ml_is_trained=false, feature_count=0),
because save_essential_state() only touched total_trades and
cumulative_pnl and left the other fields at whatever self._manifest
happened to contain.

Patch B wires both save paths (save_essential_state and _save_manifest)
to write live authoritative fields from learner.state and signal_gen
through the shared helper _apply_live_manifest_fields.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from backend.organism.brain_persistence import (
    MANIFEST_FILE,
    OrganismBrain,
)


# ─────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────

def _make_learner(
    generation=18,
    total_trades=195,
    cumulative_pnl=-656.67,
    best_sharpe=2.8956,
):
    return SimpleNamespace(
        state=SimpleNamespace(
            generation=generation,
            total_trades=total_trades,
            cumulative_pnl=cumulative_pnl,
            best_sharpe=best_sharpe,
            total_bars_seen=0,
            retrain_count=0,
            drift_events=0,
            best_generation=generation,
            generation_accuracies=[],
            model_metrics=[],
            evaluation_events=[],
        ),
        trade_history=[],
        _reference_features=None,
        _bars_since_retrain=0,
    )


def _make_signal_gen(is_trained=True, feature_count=79):
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


def _read_manifest(brain: OrganismBrain) -> dict:
    return json.loads((brain.brain_dir / MANIFEST_FILE).read_text())


def _brain(tmp_path) -> OrganismBrain:
    return OrganismBrain(brain_dir=tmp_path / "brain")


# ─────────────────────────────────────────────────────────────
# 1. save_essential_state writes learner.state fields
# ─────────────────────────────────────────────────────────────

def test_essential_writes_learner_state_fields(tmp_path):
    brain = _brain(tmp_path)
    learner = _make_learner()
    sg = _make_signal_gen()
    brain.save_essential_state(
        signal_gen=sg, learner=learner, all_trades=[]
    )
    m = _read_manifest(brain)
    assert m["generation"] == 18
    assert m["total_trades"] == 195
    assert m["cumulative_pnl"] == -656.67
    assert m["best_sharpe"] == 2.8956


# ─────────────────────────────────────────────────────────────
# 2. save_essential_state writes signal_gen fields
# ─────────────────────────────────────────────────────────────

def test_essential_writes_signal_gen_fields(tmp_path):
    brain = _brain(tmp_path)
    brain.save_essential_state(
        signal_gen=_make_signal_gen(is_trained=True, feature_count=79),
        learner=_make_learner(),
        all_trades=[],
    )
    m = _read_manifest(brain)
    assert m["ml_is_trained"] is True
    assert m["feature_count"] == 79


# ─────────────────────────────────────────────────────────────
# 3. full save() path writes the same authoritative values
# ─────────────────────────────────────────────────────────────

def test_full_save_writes_authoritative_values(tmp_path, monkeypatch):
    brain = _brain(tmp_path)
    # Neutralize model-binary write (_is_trained=False makes it a no-op)
    sg = _make_signal_gen(is_trained=False, feature_count=42)
    learner = _make_learner(
        generation=7, total_trades=50, cumulative_pnl=123.45,
        best_sharpe=1.234,
    )
    brain.save(
        signal_gen=sg,
        learner=learner,
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
    )
    m = _read_manifest(brain)
    assert m["generation"] == 7
    assert m["total_trades"] == 50
    assert m["cumulative_pnl"] == 123.45
    assert m["best_sharpe"] == 1.234
    assert m["ml_is_trained"] is False
    assert m["feature_count"] == 42


# ─────────────────────────────────────────────────────────────
# 4. Fallback when learner is None — no crash
# ─────────────────────────────────────────────────────────────

def test_manifest_helper_fallback_learner_none(tmp_path):
    """When learner is None, _apply_live_manifest_fields must fall back
    to self._manifest values and not crash. The helper is the unit
    responsible for fallback safety; the save paths themselves always
    receive non-None learner/signal_gen from live_engine._save_brain.
    """
    brain = _brain(tmp_path)
    brain._manifest = {
        "generation": 3, "total_trades": 10,
        "cumulative_pnl": -5.0, "best_sharpe": 0.5,
    }
    manifest: dict = {}
    brain._apply_live_manifest_fields(
        manifest, signal_gen=_make_signal_gen(), learner=None
    )
    assert manifest["generation"] == 3
    assert manifest["total_trades"] == 10
    assert manifest["best_sharpe"] == 0.5


# ─────────────────────────────────────────────────────────────
# 5. Fallback when signal_gen is None — no crash
# ─────────────────────────────────────────────────────────────

def test_manifest_helper_fallback_signal_gen_none(tmp_path):
    """When signal_gen is None, ml_is_trained/feature_count fall back
    to self._manifest and the helper does not crash. Learner fields
    still reflect live learner.state.
    """
    brain = _brain(tmp_path)
    brain._manifest = {"ml_is_trained": True, "feature_count": 79}
    manifest: dict = {}
    brain._apply_live_manifest_fields(
        manifest, signal_gen=None, learner=_make_learner()
    )
    assert manifest["ml_is_trained"] is True
    assert manifest["feature_count"] == 79
    assert manifest["generation"] == 18


# ─────────────────────────────────────────────────────────────
# 6. Patch C compat — finite best_sharpe is written
# ─────────────────────────────────────────────────────────────

def test_best_sharpe_finite_written(tmp_path):
    brain = _brain(tmp_path)
    brain.save_essential_state(
        signal_gen=_make_signal_gen(),
        learner=_make_learner(best_sharpe=2.8956),
        all_trades=[],
    )
    assert _read_manifest(brain)["best_sharpe"] == 2.8956


# ─────────────────────────────────────────────────────────────
# 7. Patch C compat — -inf best_sharpe falls back, not -inf
# ─────────────────────────────────────────────────────────────

def test_best_sharpe_neg_inf_falls_back(tmp_path):
    brain = _brain(tmp_path)
    brain._manifest = {"best_sharpe": 1.5}
    brain.save_essential_state(
        signal_gen=_make_signal_gen(),
        learner=_make_learner(best_sharpe=-np.inf),
        all_trades=[],
    )
    m = _read_manifest(brain)
    # Must not be -inf (non-JSON) and must not be silently 0 when we
    # have a fallback in self._manifest
    assert m["best_sharpe"] == 1.5
    assert np.isfinite(m["best_sharpe"])


# ─────────────────────────────────────────────────────────────
# 8. Regression — stale _manifest is overridden by live state
# ─────────────────────────────────────────────────────────────

def test_stale_manifest_overridden_by_live_state(tmp_path):
    """Reproduce the 2026-04-08 recovery incident scenario.

    self._manifest holds post-wipe zeros, but learner/signal_gen have
    the real healthy values. The written manifest MUST reflect the
    live objects, not the stale dict.
    """
    brain = _brain(tmp_path)
    brain._manifest = {
        "generation": 0,
        "best_sharpe": 0,
        "ml_is_trained": False,
        "feature_count": 0,
        "total_trades": 0,
        "cumulative_pnl": 0.0,
    }
    brain.save_essential_state(
        signal_gen=_make_signal_gen(is_trained=True, feature_count=79),
        learner=_make_learner(
            generation=18, total_trades=195,
            cumulative_pnl=-656.67, best_sharpe=2.8956,
        ),
        all_trades=[],
    )
    m = _read_manifest(brain)
    assert m["generation"] == 18
    assert m["total_trades"] == 195
    assert m["best_sharpe"] == 2.8956
    assert m["ml_is_trained"] is True
    assert m["feature_count"] == 79
    # In-memory copy also updated
    assert brain._manifest["generation"] == 18
    assert brain._manifest["best_sharpe"] == 2.8956
