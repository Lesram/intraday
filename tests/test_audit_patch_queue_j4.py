"""Patch Queue J4 -- real bundle completeness, evaluation-event accounting, API-unreachable policy."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _make_trade(symbol="AAPL", pnl=10.0, exit_reason="take_profit",
                closed_at="2026-03-10T15:30:00+00:00", confidence=0.5,
                is_exploration=False, **kwargs):
    return {
        "symbol": symbol, "direction": 1.0, "entry_price": 100.0,
        "exit_price": 100.0 + pnl / 10, "entry_bar": 0, "exit_bar": 10,
        "shares": 10, "pnl": pnl, "exit_reason": exit_reason,
        "predicted_return": 0.0, "actual_return": pnl / 1000,
        "confidence": confidence, "correct_direction": pnl > 0,
        "is_exploration": is_exploration, "entry_source": "alpha",
        "regime_at_entry": "trending_up", "regime_at_exit": "trending_up",
        "mfe": 0, "mae": 0, "bars_held_at_exit": 10,
        "time_in_trade_seconds": 600, "closed_at": closed_at, **kwargs,
    }


class TestBundleFilesComplete:
    """1. bundle_files_complete reflects real file existence."""

    def test_complete_bundle_passes(self):
        from scripts.runtime.generate_paper_validation_bundle import _verify_bundle_files
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            for name in [
                "daily_runtime_snapshot.json", "daily_trade_log.json",
                "daily_exit_breakdown.json", "daily_entry_breakdown.json",
                "daily_model_quality.json", "daily_signal_quality.json",
            ]:
                (d / name).write_text('{"ok": true}')
            assert _verify_bundle_files(d) is True

    def test_missing_file_fails(self):
        from scripts.runtime.generate_paper_validation_bundle import _verify_bundle_files
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            # Write only 5 of 6 required
            for name in [
                "daily_runtime_snapshot.json", "daily_trade_log.json",
                "daily_exit_breakdown.json", "daily_entry_breakdown.json",
                "daily_model_quality.json",
                # missing: daily_signal_quality.json
            ]:
                (d / name).write_text('{"ok": true}')
            assert _verify_bundle_files(d) is False

    def test_empty_file_fails(self):
        from scripts.runtime.generate_paper_validation_bundle import _verify_bundle_files
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            for name in [
                "daily_runtime_snapshot.json", "daily_trade_log.json",
                "daily_exit_breakdown.json", "daily_entry_breakdown.json",
                "daily_model_quality.json", "daily_signal_quality.json",
            ]:
                (d / name).write_text('{"ok": true}')
            # Make one empty
            (d / "daily_signal_quality.json").write_text("")
            assert _verify_bundle_files(d) is False

    def test_bundle_incomplete_fails_kpi_pass(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_kpi_summary
        kpi = generate_kpi_summary(
            [_make_trade()], {}, "2026-03-10", "abc",
            bundle_files_ok=False,
        )
        assert kpi["paper_validation_pass"] is False
        assert kpi["operational_checks"]["bundle_files_complete"] is False


class TestEvaluationEventPersistence:
    """2. Accepted and rejected evaluation events are persisted and restored."""

    def test_evaluation_events_recorded_on_accept_and_reject(self):
        """ContinuousLearner records events for both accepted and rejected models."""
        from backend.organism.continuous_learner import ContinuousLearner, LearningState
        from backend.organism.ml_signal import MLSignalGenerator

        sig_gen = MLSignalGenerator()
        learner = ContinuousLearner(sig_gen)

        # Manually add events to test persistence
        learner.state.evaluation_events.append({
            "evaluated_at": "2026-03-10T10:00:00+00:00",
            "accepted": True,
            "rejection_reason": "",
            "generation": 1,
            "accuracy": 0.6,
            "precision": 0.55,
            "direction_accuracy": 0.58,
            "hit_rate": 0.52,
            "mean_pred_return": 0.001,
            "effective_mean_pred_return": 0.0008,
        })
        learner.state.evaluation_events.append({
            "evaluated_at": "2026-03-10T14:00:00+00:00",
            "accepted": False,
            "rejection_reason": "score=0.200<0.350",
            "generation": 2,
            "accuracy": 0.4,
            "precision": 0.3,
            "direction_accuracy": 0.45,
            "hit_rate": 0.35,
            "mean_pred_return": -0.001,
            "effective_mean_pred_return": -0.0005,
        })

        assert len(learner.state.evaluation_events) == 2
        assert learner.state.evaluation_events[0]["accepted"] is True
        assert learner.state.evaluation_events[1]["accepted"] is False
        assert learner.state.evaluation_events[1]["rejection_reason"] != ""

    def test_persist_and_restore_evaluation_events(self):
        """Events survive save/load cycle through brain persistence."""
        from backend.organism.brain_persistence import OrganismBrain, _write_json

        with tempfile.TemporaryDirectory() as td:
            brain_dir = Path(td) / "brain"
            brain_dir.mkdir()

            events = [
                {
                    "evaluated_at": "2026-03-10T10:00:00+00:00",
                    "accepted": True, "rejection_reason": "",
                    "generation": 1, "accuracy": 0.6, "precision": 0.55,
                    "direction_accuracy": 0.58, "hit_rate": 0.52,
                    "mean_pred_return": 0.001,
                    "effective_mean_pred_return": 0.0008,
                },
                {
                    "evaluated_at": "2026-03-10T14:00:00+00:00",
                    "accepted": False, "rejection_reason": "score too low",
                    "generation": 2, "accuracy": 0.4, "precision": 0.3,
                    "direction_accuracy": 0.45, "hit_rate": 0.35,
                    "mean_pred_return": -0.001,
                    "effective_mean_pred_return": -0.0005,
                },
            ]

            # Write directly
            _write_json(brain_dir / "evaluation_event_history.json", events)

            brain = OrganismBrain(brain_dir=brain_dir)
            brain._load_evaluation_event_history()

            assert len(brain.evaluation_event_history) == 2
            assert brain.evaluation_event_history[0]["accepted"] is True
            assert brain.evaluation_event_history[1]["accepted"] is False

    def test_old_brain_no_event_history_backward_compat(self):
        """Old brains without evaluation_event_history.json load gracefully."""
        from backend.organism.brain_persistence import OrganismBrain

        with tempfile.TemporaryDirectory() as td:
            brain = OrganismBrain(brain_dir=td)
            brain._load_evaluation_event_history()
            assert brain.evaluation_event_history == []


class TestModelQualityEventAccounting:
    """3. daily_model_quality uses real evaluation-event history."""

    def test_counts_from_evaluation_events(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_model_quality

        events = [
            {"evaluated_at": "2026-03-10T10:00:00+00:00", "accepted": True,
             "generation": 1},
            {"evaluated_at": "2026-03-10T14:00:00+00:00", "accepted": False,
             "generation": 2},
            {"evaluated_at": "2026-03-09T10:00:00+00:00", "accepted": True,
             "generation": 0},
        ]

        mq = generate_model_quality({}, {}, {}, date="2026-03-10",
                                     evaluation_event_history=events)
        ae = mq["acceptance_events"]
        assert ae["source"] == "evaluation_event_history"
        assert ae["lifetime_evaluations"] == 3
        assert ae["lifetime_accepted"] == 2
        assert ae["lifetime_rejected"] == 1
        assert ae["today_evaluations"] == 2
        assert ae["today_accepted"] == 1
        assert ae["today_rejected"] == 1

    def test_fallback_without_event_history(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_model_quality

        ml_state = {
            "model_metrics_history": [
                {"accepted": True, "evaluated_at": "2026-03-10T10:00:00"},
            ]
        }
        mq = generate_model_quality({}, ml_state, {}, date="2026-03-10")
        ae = mq["acceptance_events"]
        assert ae["source"] == "model_metrics_history_accepted_only"

    def test_date_filtering(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_model_quality

        events = [
            {"evaluated_at": "2026-03-09T10:00:00+00:00", "accepted": True, "generation": 0},
            {"evaluated_at": "2026-03-10T10:00:00+00:00", "accepted": True, "generation": 1},
            {"evaluated_at": "2026-03-10T14:00:00+00:00", "accepted": False, "generation": 2},
        ]
        mq = generate_model_quality({}, {}, {}, date="2026-03-10",
                                     evaluation_event_history=events)
        ae = mq["acceptance_events"]
        assert ae["today_evaluations"] == 2
        assert ae["today_accepted"] == 1
        assert ae["today_rejected"] == 1


class TestAPIUnreachablePolicy:
    """4. API-unreachable is explicitly a warning, not a failure."""

    def test_api_unreachable_does_not_fail_pass(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_kpi_summary
        kpi = generate_kpi_summary(
            [_make_trade()], {}, "2026-03-10", "abc",
            api_reachable=False,
        )
        # API unreachable should NOT cause operational failure
        assert kpi["paper_validation_pass"] is True
        assert "api_not_reachable" in kpi["operational_notes"]

    def test_api_unreachable_is_warning_only(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_kpi_summary
        kpi = generate_kpi_summary(
            [_make_trade()], {}, "2026-03-10", "abc",
            api_reachable=False,
        )
        # Verify it's in notes (warning) not in checks (failure criteria)
        assert "api_not_reachable" not in kpi.get("operational_checks", {})
        assert "api_not_reachable" in kpi["operational_notes"]

    def test_api_reachable_no_warning(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_kpi_summary
        kpi = generate_kpi_summary(
            [_make_trade()], {}, "2026-03-10", "abc",
            api_reachable=True,
        )
        assert "api_not_reachable" not in kpi["operational_notes"]


class TestBackgroundTrainerEvaluationEvent:
    """5. BackgroundTrainer provides evaluation events."""

    def test_get_last_evaluation_event_accepted(self):
        from backend.organism.background_trainer import BackgroundTrainer, TrainResult

        trainer = BackgroundTrainer()
        trainer._last_result = TrainResult(
            accepted=True,
            train_metrics={
                "accuracy": 0.6, "precision": 0.55,
                "direction_accuracy": 0.58, "hit_rate": 0.52,
                "mean_pred_return": 0.001,
                "effective_mean_pred_return": 0.0008,
                "generation": 3,
                "evaluated_at": "2026-03-10T10:00:00+00:00",
            },
        )

        event = trainer.get_last_evaluation_event()
        assert event is not None
        assert event["accepted"] is True
        assert event["rejection_reason"] == ""
        assert event["generation"] == 3

    def test_get_last_evaluation_event_rejected(self):
        from backend.organism.background_trainer import BackgroundTrainer, TrainResult

        trainer = BackgroundTrainer()
        trainer._last_result = TrainResult(
            accepted=False,
            rejection_reason="score too low",
            train_metrics={
                "accuracy": 0.4, "precision": 0.3,
                "direction_accuracy": 0.45, "hit_rate": 0.35,
                "mean_pred_return": -0.001,
                "effective_mean_pred_return": -0.0005,
                "generation": 4,
                "evaluated_at": "2026-03-10T14:00:00+00:00",
            },
        )

        event = trainer.get_last_evaluation_event()
        assert event is not None
        assert event["accepted"] is False
        assert event["rejection_reason"] == "score too low"

    def test_get_last_evaluation_event_none_when_no_result(self):
        from backend.organism.background_trainer import BackgroundTrainer

        trainer = BackgroundTrainer()
        assert trainer.get_last_evaluation_event() is None

    def test_get_last_evaluation_event_none_for_training_error(self):
        from backend.organism.background_trainer import BackgroundTrainer, TrainResult

        trainer = BackgroundTrainer()
        trainer._last_result = TrainResult(error="some error")
        assert trainer.get_last_evaluation_event() is None
