"""Apr-8 Patch A — force-save admin path regression tests.

Recovery gap: the walk-forward gate in OrganismLiveEngine._save_brain blocks
the full BrainPersistence.save() call when a regression is detected,
which means ML joblibs + reference features + evolved_params never
land on disk for an entire session. Patch A adds an explicit
admin-only recovery path:

  BrainPersistence.save(force=False)  # audit flag, default unchanged
  OrganismLiveEngine.force_save_brain()       # bypass gate, full save
  POST /api/v1/organism/save?force=true
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi import HTTPException

from backend.organism.brain_persistence import (
    MANIFEST_FILE,
    OrganismBrain,
)


# ─────────────────────────────────────────────────────────────
# helpers (mirrors test_apr8_patch_b_manifest_sync)
# ─────────────────────────────────────────────────────────────

def _make_learner(best_sharpe=1.5, total_trades=50):
    return SimpleNamespace(
        state=SimpleNamespace(
            generation=3,
            total_trades=total_trades,
            cumulative_pnl=42.0,
            best_sharpe=best_sharpe,
            total_bars_seen=0,
            retrain_count=0,
            drift_events=0,
            best_generation=3,
            generation_accuracies=[],
            model_metrics=[],
            evaluation_events=[],
        ),
        trade_history=[],
        _reference_features=None,
        _bars_since_retrain=0,
    )


def _make_signal_gen(is_trained=False, feature_count=79):
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


# ─────────────────────────────────────────────────────────────
# 1. save(force=False) — default behavior unchanged
# ─────────────────────────────────────────────────────────────

def test_save_force_false_default_behavior(tmp_path):
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    brain.save(
        signal_gen=_make_signal_gen(),
        learner=_make_learner(),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=False,
    )
    m = _read_manifest(brain)
    assert m["generation"] == 3
    assert m["total_trades"] == 50


# ─────────────────────────────────────────────────────────────
# 2. save(force=True) still writes full artifacts
# ─────────────────────────────────────────────────────────────

def test_save_force_true_still_full_save(tmp_path):
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    brain.save(
        signal_gen=_make_signal_gen(feature_count=42),
        learner=_make_learner(),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=True,
    )
    m = _read_manifest(brain)
    assert m["generation"] == 3
    assert m["feature_count"] == 42
    # Full save also writes learning_state.json / trade_history
    assert (brain.brain_dir / "learning_state.json").exists()


# ─────────────────────────────────────────────────────────────
# 3-5, 10. OrganismLiveEngine.force_save_brain() — unit tests with a
#          hand-built stub engine. We deliberately do NOT spin up
#          a full OrganismLiveEngine; we bind the unbound method to a
#          minimal namespace to exercise the save path logic.
# ─────────────────────────────────────────────────────────────

from backend.organism.live_engine import OrganismLiveEngine


def _make_stub_engine():
    brain = MagicMock()
    brain.save = MagicMock()
    brain.walk_forward_gate = MagicMock(return_value=(True, "ok"))
    stub = SimpleNamespace(
        brain=brain,
        signal_gen=_make_signal_gen(is_trained=True, feature_count=79),
        learner=_make_learner(best_sharpe=1.25, total_trades=77),
        _equity_curve=[100000.0, 100100.0],
        _all_trades=[],
        _epoch_metrics=[],
        _peak_equity=100100.0,
        _tick_count=4242,
        _bars_since_retrain=10,
        _exit_levels={},
        _entry_metadata={},
        _entry_timestamps=[],
        _pending_entry={},
        _watchdog_last_brain_save_tick=0,
        universe_selector=SimpleNamespace(to_dict=lambda: {}),
        kelly_sizer=SimpleNamespace(regime_stats_to_dict=lambda: {}),
        evolved_params=SimpleNamespace(to_dict=lambda: {}),
        governance=None,
        regime_detector=None,
        _persist_exit_levels_standalone=MagicMock(),
    )
    # Bind extra: signal_gen needs calibration_to_dict
    stub.signal_gen.calibration_to_dict = lambda: {}
    return stub


def test_force_save_brain_calls_brain_save_force_true():
    stub = _make_stub_engine()
    result = OrganismLiveEngine.force_save_brain(stub)
    assert stub.brain.save.called
    kwargs = stub.brain.save.call_args.kwargs
    assert kwargs["force"] is True
    assert kwargs["signal_gen"] is stub.signal_gen
    assert kwargs["learner"] is stub.learner
    assert kwargs["all_trades"] is stub._all_trades
    assert result["success"] is True
    assert result["forced"] is True
    assert result["tick"] == 4242
    assert result["generation"] == 3
    assert result["total_trades"] == 77
    assert result["best_sharpe"] == 1.25
    assert result["ml_is_trained"] is True
    assert result["feature_count"] == 79


def test_force_save_brain_bypasses_walk_forward_gate():
    stub = _make_stub_engine()
    # Set up a "would-fail" gate
    stub.brain.walk_forward_gate = MagicMock(return_value=(False, "regression"))
    result = OrganismLiveEngine.force_save_brain(stub)
    # Gate should NEVER be called on force path
    assert not stub.brain.walk_forward_gate.called
    # But brain.save WAS called
    assert stub.brain.save.called
    assert result["success"] is True


def test_force_save_brain_updates_watchdog_tick():
    stub = _make_stub_engine()
    stub._tick_count = 9999
    OrganismLiveEngine.force_save_brain(stub)
    assert stub._watchdog_last_brain_save_tick == 9999


def test_force_save_brain_persists_exit_levels():
    stub = _make_stub_engine()
    OrganismLiveEngine.force_save_brain(stub)
    assert stub._persist_exit_levels_standalone.called


def test_force_save_brain_graceful_exception():
    stub = _make_stub_engine()
    stub.brain.save = MagicMock(side_effect=RuntimeError("disk full"))
    result = OrganismLiveEngine.force_save_brain(stub)
    assert result["success"] is False
    assert result["forced"] is True
    assert "disk full" in result["error"]
    assert result["tick"] == 4242


def test_force_save_brain_nonfinite_sharpe_returns_none():
    stub = _make_stub_engine()
    stub.learner.state.best_sharpe = float("-inf")
    result = OrganismLiveEngine.force_save_brain(stub)
    assert result["best_sharpe"] is None


# ─────────────────────────────────────────────────────────────
# 7-9. Route tests — direct async-function invocation
#      (FastAPI's DI wraps require_admin at request-time; calling
#      the handler directly bypasses auth, which is fine for unit-
#      testing the logic. Auth wiring is verified separately below.)
# ─────────────────────────────────────────────────────────────

from backend.organism.routes import force_save, router


def _fake_request(engine):
    req = MagicMock()
    req.app.state.organism_scheduler = SimpleNamespace(_engine=engine)
    return req


def test_route_rejects_without_force_query():
    req = _fake_request(engine=MagicMock())
    with pytest.raises(HTTPException) as exc:
        asyncio.get_event_loop().run_until_complete(
            force_save(request=req, force=False, _admin=None)
        )
    assert exc.value.status_code == 400
    assert "force=true" in str(exc.value.detail)


def test_route_calls_force_save_brain_when_forced():
    engine = MagicMock()
    engine.force_save_brain = MagicMock(
        return_value={
            "success": True,
            "forced": True,
            "tick": 101,
            "generation": 5,
            "total_trades": 99,
            "best_sharpe": 1.2,
            "ml_is_trained": True,
            "feature_count": 79,
        }
    )
    req = _fake_request(engine=engine)
    result = asyncio.get_event_loop().run_until_complete(
        force_save(request=req, force=True, _admin=None)
    )
    assert engine.force_save_brain.called
    assert result["success"] is True
    assert result["tick"] == 101
    assert result["generation"] == 5


def test_route_returns_409_when_engine_inactive():
    req = MagicMock()
    req.app.state.organism_scheduler = None
    with pytest.raises(HTTPException) as exc:
        asyncio.get_event_loop().run_until_complete(
            force_save(request=req, force=True, _admin=None)
        )
    assert exc.value.status_code == 409


def test_route_has_require_admin_dependency():
    """Verify the /save route is wired to require_admin.

    FastAPI routes expose dependencies via the route object's
    dependant tree. We scan the router for our /save route and
    assert require_admin appears in its dependants.
    """
    from backend.infra.security import require_admin

    save_route = None
    for r in router.routes:
        if getattr(r, "path", None) in ("/save", "/organism/save"):
            save_route = r
            break
    assert save_route is not None, "/save route not registered"

    # Walk the dependant tree for require_admin
    def _has_dep(dependant, target):
        for sub in dependant.dependencies:
            if sub.call is target or _has_dep(sub, target):
                return True
        return False

    assert _has_dep(save_route.dependant, require_admin)


# ─────────────────────────────────────────────────────────────
# 6. Regression — normal _save_brain still respects the gate
#    (sanity check: Patch A did not weaken _save_brain)
# ─────────────────────────────────────────────────────────────

def test_save_brain_still_calls_walk_forward_gate():
    """Static sanity: _save_brain source still contains a
    walk_forward_gate call and an `if not should_save:` branch.
    Patch A must not have touched this path.
    """
    import inspect
    src = inspect.getsource(OrganismLiveEngine._save_brain)
    assert "walk_forward_gate" in src
    assert "should_save" in src
    assert "save_essential_state" in src
