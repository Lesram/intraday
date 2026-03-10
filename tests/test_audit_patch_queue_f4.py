"""Tests for Patch Queue F4 -- preserve background trainer _is_trained semantics."""
from __future__ import annotations

import pickle

import pytest
from unittest.mock import MagicMock

from backend.organism.background_trainer import BackgroundTrainer, TrainResult
from backend.organism.ml_signal import MLSignalGenerator


# ==============================================================================
# Test 1: TrainResult has is_trained field
# ==============================================================================

class TestTrainResultField:

    def test_train_result_has_is_trained_field(self):
        """TrainResult must have an is_trained field defaulting to None."""
        result = TrainResult()
        assert hasattr(result, "is_trained")
        assert result.is_trained is None

    def test_train_result_is_trained_can_be_set(self):
        result = TrainResult(is_trained=True)
        assert result.is_trained is True
        result2 = TrainResult(is_trained=False)
        assert result2.is_trained is False


# ==============================================================================
# Test 2: get_result preserves is_trained from raw
# ==============================================================================

class TestGetResultPreservesIsTrained:

    def _make_trainer_with_raw(self, raw: dict) -> BackgroundTrainer:
        trainer = BackgroundTrainer()
        trainer._is_training = True
        future = MagicMock()
        future.done.return_value = True
        future.result.return_value = raw
        trainer._future = future
        return trainer

    def test_accepted_result_preserves_is_trained_true(self):
        raw = {
            "accepted": True,
            "train_metrics": {"accuracy": 0.6, "generation": 5},
            "clf_pickle": b"fake",
            "reg_pickle": b"fake",
            "is_trained": True,
            "duration_s": 1.0,
        }
        trainer = self._make_trainer_with_raw(raw)
        done, result = trainer.get_result()
        assert done
        assert result.is_trained is True

    def test_accepted_result_preserves_is_trained_false(self):
        raw = {
            "accepted": True,
            "train_metrics": {"accuracy": 0.6, "generation": 5},
            "clf_pickle": b"fake",
            "reg_pickle": b"fake",
            "is_trained": False,
            "duration_s": 1.0,
        }
        trainer = self._make_trainer_with_raw(raw)
        done, result = trainer.get_result()
        assert done
        assert result.is_trained is False

    def test_accepted_result_missing_is_trained_gives_none(self):
        """Legacy result without is_trained key should give None."""
        raw = {
            "accepted": True,
            "train_metrics": {"accuracy": 0.6},
            "clf_pickle": b"fake",
            "reg_pickle": b"fake",
            "duration_s": 1.0,
        }
        trainer = self._make_trainer_with_raw(raw)
        done, result = trainer.get_result()
        assert done
        assert result.is_trained is None


# ==============================================================================
# Test 3: apply_result uses is_trained instead of inferring from pickle
# ==============================================================================

class TestApplyResultIsTrained:

    def test_is_trained_false_does_not_flip_to_true(self):
        """Accepted result with clf+reg state but is_trained=False must NOT
        set signal_gen._is_trained = True."""
        trainer = BackgroundTrainer()
        trainer._last_result = TrainResult(
            accepted=True,
            new_clf_state=pickle.dumps("fake_clf"),
            new_reg_state=pickle.dumps("fake_reg"),
            is_trained=False,
            train_metrics={"accuracy": 0.5, "generation": 1},
        )

        sig_gen = MLSignalGenerator()
        sig_gen._is_trained = False

        trainer.apply_result(
            sig_gen, MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), MagicMock(),
        )

        assert sig_gen._is_trained is False, \
            "is_trained=False from worker must not be overridden by pickle presence"

    def test_is_trained_true_sets_trained(self):
        """Accepted result with is_trained=True sets signal_gen._is_trained=True."""
        trainer = BackgroundTrainer()
        trainer._last_result = TrainResult(
            accepted=True,
            new_clf_state=pickle.dumps("fake_clf"),
            new_reg_state=pickle.dumps("fake_reg"),
            is_trained=True,
            train_metrics={"accuracy": 0.5, "generation": 1},
        )

        sig_gen = MLSignalGenerator()
        sig_gen._is_trained = False

        trainer.apply_result(
            sig_gen, MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), MagicMock(),
        )

        assert sig_gen._is_trained is True

    def test_is_trained_none_leaves_existing_state(self):
        """Accepted result with is_trained=None leaves signal_gen._is_trained unchanged."""
        trainer = BackgroundTrainer()
        trainer._last_result = TrainResult(
            accepted=True,
            new_clf_state=pickle.dumps("fake_clf"),
            new_reg_state=pickle.dumps("fake_reg"),
            is_trained=None,
            train_metrics={"accuracy": 0.5, "generation": 1},
        )

        # Case A: was already True → stays True
        sig_gen_a = MLSignalGenerator()
        sig_gen_a._is_trained = True
        trainer.apply_result(
            sig_gen_a, MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), MagicMock(),
        )
        assert sig_gen_a._is_trained is True

        # Case B: was False → stays False
        trainer._last_result = TrainResult(
            accepted=True,
            new_clf_state=pickle.dumps("fake_clf"),
            new_reg_state=pickle.dumps("fake_reg"),
            is_trained=None,
            train_metrics={"accuracy": 0.5, "generation": 1},
        )
        sig_gen_b = MLSignalGenerator()
        sig_gen_b._is_trained = False
        trainer.apply_result(
            sig_gen_b, MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), MagicMock(),
        )
        assert sig_gen_b._is_trained is False

    def test_no_pickle_inference_in_apply_result_source(self):
        """apply_result must NOT contain 'new_clf_state and result.new_reg_state'
        logic for setting _is_trained."""
        import inspect
        from backend.organism import background_trainer
        source = inspect.getsource(background_trainer.BackgroundTrainer.apply_result)
        assert "new_clf_state and result.new_reg_state" not in source, \
            "apply_result must not infer _is_trained from pickle presence"


# ==============================================================================
# Test 4: Rejected results unchanged
# ==============================================================================

class TestRejectedResultUnchanged:

    def test_rejected_result_does_not_touch_is_trained(self):
        """Rejected result must not modify signal_gen._is_trained."""
        trainer = BackgroundTrainer()
        trainer._last_result = TrainResult(
            accepted=False,
            rejection_reason="quality gate",
            is_trained=True,  # even if worker says True, rejected = no apply
        )

        sig_gen = MLSignalGenerator()
        sig_gen._is_trained = False

        trainer.apply_result(
            sig_gen, MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), MagicMock(),
        )

        assert sig_gen._is_trained is False, \
            "Rejected result must not change _is_trained"
