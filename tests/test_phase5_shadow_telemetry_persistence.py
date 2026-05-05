"""Phase 5 persistence tests for candidate-filter shadow telemetry."""

from __future__ import annotations

from types import SimpleNamespace

from backend.organism.brain_persistence import (
    CANDIDATE_FILTER_SHADOW_TELEMETRY_FILE,
    OrganismBrain,
)


def _learner() -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(
            generation=3,
            total_trades=50,
            cumulative_pnl=42.0,
            best_sharpe=1.5,
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


def _signal_gen() -> SimpleNamespace:
    return SimpleNamespace(
        _is_trained=False,
        _feature_cols=["f0", "f1"],
        _xgb_params={},
        _clf=None,
        _reg=None,
        generation=0,
        train_window=1000,
        _latest_metrics=None,
    )


def test_full_brain_save_preserves_phase5_shadow_telemetry_file(tmp_path):
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    brain.save(
        signal_gen=_signal_gen(),
        learner=_learner(),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=True,
    )
    telemetry = brain.brain_dir / CANDIDATE_FILTER_SHADOW_TELEMETRY_FILE
    telemetry.write_text('{"symbol":"AAPL","matched_filters":["conf_45_55"]}\n')

    brain.save(
        signal_gen=_signal_gen(),
        learner=_learner(),
        equity_curve=[100000.0, 100001.0],
        all_trades=[],
        epoch_metrics=[],
        force=True,
    )

    assert telemetry.read_text() == '{"symbol":"AAPL","matched_filters":["conf_45_55"]}\n'
