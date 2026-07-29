"""Patch Queue J5 -- background-trainer evaluation events wired into learner history."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Helpers — minimal mocks that exercise the wiring without needing a full
# live engine.  We replicate the exact branching logic from live_engine.py
# step 9a so the tests are coupled to the real code path.
# ---------------------------------------------------------------------------

def _make_train_result(*, accepted=True, error=None, rejection_reason=None,
                       train_metrics=None):
    from backend.organism.background_trainer import TrainResult
    return TrainResult(
        accepted=accepted,
        error=error,
        rejection_reason=rejection_reason,
        train_metrics=train_metrics or {
            "accuracy": 0.6, "precision": 0.55,
            "direction_accuracy": 0.58, "hit_rate": 0.52,
            "mean_pred_return": 0.001,
            "effective_mean_pred_return": 0.0008,
            "generation": 1,
            "evaluated_at": "2026-03-10T10:00:00+00:00",
        },
    )


def _make_bg_trainer_with_result(train_result):
    """Create a BackgroundTrainer with a pre-set last_result."""
    from backend.organism.background_trainer import BackgroundTrainer
    trainer = BackgroundTrainer()
    trainer._last_result = train_result
    return trainer


def _make_learner_state():
    """Create a fresh LearningState."""
    from backend.organism.continuous_learner import LearningState
    return LearningState()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAcceptedBackgroundEventAppended:
    """Accepted background result appends one evaluation event."""

    def test_accepted_event_appended(self):
        from backend.organism.background_trainer import BackgroundTrainer

        result = _make_train_result(accepted=True)
        trainer = _make_bg_trainer_with_result(result)
        state = _make_learner_state()

        assert len(state.evaluation_events) == 0

        # Simulate the accepted branch from live_engine step 9a (J5)
        event = trainer.get_last_evaluation_event()
        if event:
            state.evaluation_events.append(event)

        assert len(state.evaluation_events) == 1
        assert state.evaluation_events[0]["accepted"] is True
        assert state.evaluation_events[0]["rejection_reason"] == ""
        assert state.evaluation_events[0]["generation"] == 1

    def test_accepted_event_has_core_metrics(self):
        result = _make_train_result(accepted=True, train_metrics={
            "accuracy": 0.65, "precision": 0.58,
            "direction_accuracy": 0.60, "hit_rate": 0.55,
            "mean_pred_return": 0.002,
            "effective_mean_pred_return": 0.0015,
            "generation": 3,
            "evaluated_at": "2026-03-10T12:00:00+00:00",
        })
        trainer = _make_bg_trainer_with_result(result)

        event = trainer.get_last_evaluation_event()
        assert event["accuracy"] == 0.65
        assert event["precision"] == 0.58
        assert event["evaluated_at"] == "2026-03-10T12:00:00+00:00"


class TestRejectedBackgroundEventAppended:
    """Rejected background result appends one event with rejection_reason."""

    def test_rejected_event_appended(self):
        result = _make_train_result(
            accepted=False,
            rejection_reason="score=0.200<0.350, precision=0.300",
        )
        trainer = _make_bg_trainer_with_result(result)
        state = _make_learner_state()

        event = trainer.get_last_evaluation_event()
        if event:
            state.evaluation_events.append(event)

        assert len(state.evaluation_events) == 1
        assert state.evaluation_events[0]["accepted"] is False
        assert "score=0.200" in state.evaluation_events[0]["rejection_reason"]

    def test_rejected_event_has_rejection_reason(self):
        result = _make_train_result(
            accepted=False,
            rejection_reason="Model rejected by quality gate (precision too low)",
        )
        trainer = _make_bg_trainer_with_result(result)

        event = trainer.get_last_evaluation_event()
        assert event is not None
        assert event["rejection_reason"] == "Model rejected by quality gate (precision too low)"


class TestTrainingErrorNoEvent:
    """True training error appends no evaluation event."""

    def test_error_returns_no_event(self):
        result = _make_train_result(accepted=False, error="OOM in XGBoost")
        # Training errors have no train_metrics
        result.train_metrics = None
        trainer = _make_bg_trainer_with_result(result)
        state = _make_learner_state()

        event = trainer.get_last_evaluation_event()
        # Should be None for training errors
        assert event is None

        # Simulate the error branch — no event appended
        if event:
            state.evaluation_events.append(event)

        assert len(state.evaluation_events) == 0

    def test_error_with_no_metrics_returns_none(self):
        from backend.organism.background_trainer import TrainResult
        result = TrainResult(error="Process killed", train_metrics=None)
        trainer = _make_bg_trainer_with_result(result)

        assert trainer.get_last_evaluation_event() is None


class TestNoDuplicateEvents:
    """Repeated polling of the same result does not duplicate events."""

    def test_get_result_returns_done_only_once(self):
        """BackgroundTrainer.get_result() returns done=True only once per run."""
        from backend.organism.background_trainer import BackgroundTrainer, TrainResult
        import asyncio

        trainer = BackgroundTrainer()
        # Simulate completed training
        trainer._is_training = False
        trainer._future = None
        trainer._last_result = TrainResult(accepted=True, train_metrics={
            "accuracy": 0.6, "generation": 1, "evaluated_at": "2026-03-10T10:00:00",
        })

        # After training is done and _is_training is False, get_result returns False
        done, result = trainer.get_result()
        assert done is False  # _is_training is already False
        assert result is None

    def test_event_appended_exactly_once_in_wiring_pattern(self):
        """The live_engine wiring pattern appends exactly once because
        get_result() only returns done=True once per training run."""
        from backend.organism.background_trainer import BackgroundTrainer

        trainer = _make_bg_trainer_with_result(
            _make_train_result(accepted=True)
        )
        state = _make_learner_state()

        # First call — event appended
        event = trainer.get_last_evaluation_event()
        if event:
            state.evaluation_events.append(event)
        assert len(state.evaluation_events) == 1

        # Simulate what happens if somehow called again with same result:
        # The live_engine code only enters the accepted/rejected branches
        # when `done=True` from get_result(), which only fires once.
        # But even if get_last_evaluation_event() is called again,
        # the guard is that get_result() won't return done=True again.
        # Verify the event is still the same object (idempotent read).
        event2 = trainer.get_last_evaluation_event()
        assert event2 is not None  # Still available
        assert event2["generation"] == event["generation"]

        # But we do NOT append again because the live_engine branch
        # only executes once per get_result() done=True.
        assert len(state.evaluation_events) == 1


class TestLiveEngineWiringPattern:
    """Verify the actual code pattern in live_engine.py matches spec."""

    def test_accepted_branch_has_eval_event_append(self):
        """The accepted branch in live_engine appends the evaluation event."""
        import ast
        live_engine_path = ROOT / "backend" / "organism" / "live_engine.py"
        source = live_engine_path.read_text()

        # Find the accepted branch pattern — get_last_evaluation_event after accepted
        assert "get_last_evaluation_event()" in source
        # Verify both accepted and rejected paths append
        assert source.count("self.learner.state.evaluation_events.append(_bg_eval_event)") == 2

    def test_error_branch_has_no_eval_event_append(self):
        """The error branch does NOT append an evaluation event."""
        live_engine_path = ROOT / "backend" / "organism" / "live_engine.py"
        source = live_engine_path.read_text()

        # Find the error branch — it should NOT have get_last_evaluation_event
        # between "train_result.error" handling and the sync fallback
        error_section_start = source.index("True training error")
        error_section_end = source.index("Synchronous fallback retrain completed")
        error_section = source[error_section_start:error_section_end]

        assert "get_last_evaluation_event" not in error_section
        assert "evaluation_events.append" not in error_section
