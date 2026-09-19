"""Apr-10 Patch F2 — save_essential_state routed through _write_manifest_guarded.

Verifies:
1. total_runs is consistent across alternating save()/save_essential_state() calls
2. save_essential_state blocks trained→fresh via the unified helper
3. fresh OrganismBrain instance with trained on-disk manifest is guarded on both paths
4. normal essential save still succeeds
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
# Test 1: total_runs consistent across alternating save paths
# ─────────────────────────────────────────────────────────────

def test_total_runs_consistent_alternating_paths(tmp_path):
    """save() and save_essential_state() must produce monotonic
    total_runs with no drift, regardless of alternation order."""
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    brain.brain_dir.mkdir(parents=True, exist_ok=True)

    learner = _make_learner(total_trades=50, generation=3,
                            cumulative_pnl=-100.0, best_sharpe=2.0)
    sig = _make_signal_gen(is_trained=True, feature_count=20)

    # 1. save() → total_runs = 1
    brain.save(signal_gen=sig, learner=learner, equity_curve=[100000.0],
               all_trades=[], epoch_metrics=[], force=True)
    m1 = _read_manifest(brain)
    assert m1["total_runs"] == 1

    # 2. save_essential_state() → total_runs = 2
    brain.save_essential_state(signal_gen=sig, learner=learner,
                                all_trades=[], equity_curve=[100000.0])
    m2 = _read_manifest(brain)
    assert m2["total_runs"] == 2

    # 3. save() again → total_runs = 3
    brain.save(signal_gen=sig, learner=learner, equity_curve=[100000.0],
               all_trades=[], epoch_metrics=[], force=True)
    m3 = _read_manifest(brain)
    assert m3["total_runs"] == 3

    # 4. save_essential_state() again → total_runs = 4
    brain.save_essential_state(signal_gen=sig, learner=learner,
                                all_trades=[], equity_curve=[100000.0])
    m4 = _read_manifest(brain)
    assert m4["total_runs"] == 4

    # All in-memory synced
    assert brain._manifest["total_runs"] == 4


# ─────────────────────────────────────────────────────────────
# Test 2: save_essential_state blocks trained→fresh via helper
# ─────────────────────────────────────────────────────────────

def test_essential_state_blocks_trained_overwrite_via_helper(tmp_path, caplog):
    brain = _seed_brain(tmp_path, total_trades=195)
    before = _read_manifest(brain)
    assert before["total_trades"] == 195
    assert before["ml_is_trained"] is True

    import logging
    with caplog.at_level(logging.ERROR):
        brain.save_essential_state(
            signal_gen=_make_signal_gen(is_trained=False),
            learner=_make_learner(total_trades=0),
            all_trades=[],
        )

    # Guard message now comes from the helper
    assert any(
        "BRAIN SAVE BLOCKED (save_essential_state)" in r.getMessage()
        for r in caplog.records
    ), (
        f"Expected guard log. Got: {[r.getMessage() for r in caplog.records]}"
    )

    # Manifest unchanged
    after = _read_manifest(brain)
    assert after["total_trades"] == 195
    assert after["ml_is_trained"] is True


# ─────────────────────────────────────────────────────────────
# Test 3: fresh instance + trained disk → guarded on both paths
# ─────────────────────────────────────────────────────────────

def test_fresh_instance_guarded_both_paths(tmp_path, caplog):
    """A fresh OrganismBrain (empty self._manifest) pointing at an
    already-trained brain dir is guarded on BOTH save() and
    save_essential_state(), using the on-disk manifest fallback."""
    seeded = _seed_brain(tmp_path, total_trades=195)
    seed_dir = seeded.brain_dir

    # --- Test via save_essential_state ---
    fresh1 = OrganismBrain(brain_dir=seed_dir)
    assert not fresh1._manifest

    import logging
    with caplog.at_level(logging.ERROR):
        fresh1.save_essential_state(
            signal_gen=_make_signal_gen(is_trained=False),
            learner=_make_learner(total_trades=0),
            all_trades=[],
        )

    assert any("BRAIN SAVE BLOCKED" in r.getMessage() for r in caplog.records)
    after1 = json.loads((seed_dir / MANIFEST_FILE).read_text())
    assert after1["total_trades"] == 195

    caplog.clear()

    # --- Test via save() ---
    fresh2 = OrganismBrain(brain_dir=seed_dir)
    assert not fresh2._manifest

    with caplog.at_level(logging.ERROR):
        fresh2.save(
            signal_gen=_make_signal_gen(is_trained=False),
            learner=_make_learner(total_trades=0),
            equity_curve=[100000.0],
            all_trades=[],
            epoch_metrics=[],
            force=False,
        )

    assert any("BRAIN SAVE BLOCKED" in r.getMessage() for r in caplog.records)
    after2 = json.loads((seed_dir / MANIFEST_FILE).read_text())
    assert after2["total_trades"] == 195


# ─────────────────────────────────────────────────────────────
# Test 4: normal essential save still succeeds
# ─────────────────────────────────────────────────────────────

def test_essential_save_healthy_succeeds(tmp_path):
    brain = _seed_brain(tmp_path, total_trades=195)

    brain.save_essential_state(
        signal_gen=_make_signal_gen(is_trained=True, feature_count=79),
        learner=_make_learner(total_trades=200, generation=28,
                              cumulative_pnl=-480.0, best_sharpe=3.5),
        all_trades=[],
        equity_curve=[100000.0],
    )

    m = _read_manifest(brain)
    assert m["total_trades"] == 200
    assert m["generation"] == 28
    assert m["ml_is_trained"] is True
    assert m["feature_count"] == 79
    # total_runs incremented from prior seed save
    assert m["total_runs"] >= 2
