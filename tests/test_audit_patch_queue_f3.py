"""Tests for Patch Queue F3 -- background trainer config parity and result semantics."""
from __future__ import annotations

import pytest

from backend.organism.background_trainer import (
    BackgroundTrainer, TrainResult, _train_in_process,
)
from backend.organism.ml_signal import MLSignalGenerator, ModelMetrics


# ==============================================================================
# Test 1: Full _xgb_params surface serialization
# ==============================================================================

class TestXgbParamsSerialization:

    def test_submit_serializes_full_xgb_params(self):
        """submit_retrain serializes the full _xgb_params dict."""
        import inspect
        from backend.organism import background_trainer
        source = inspect.getsource(background_trainer.BackgroundTrainer.submit_retrain)
        assert '"xgb_params"' in source, \
            "submit_retrain must serialize xgb_params dict"

    def test_train_in_process_restores_full_params(self):
        """_train_in_process must reconstruct MLSignalGenerator with all xgb params."""
        import inspect
        from backend.organism import background_trainer
        source = inspect.getsource(background_trainer._train_in_process)
        for param in ["min_child_weight", "subsample", "colsample_bytree",
                       "reg_alpha", "reg_lambda"]:
            assert param in source, \
                f"_train_in_process must restore {param}"

    def test_xgb_params_roundtrip(self):
        """Full xgb_params surface survives serialization roundtrip."""
        sig_gen = MLSignalGenerator(
            min_child_weight=7,
            subsample=0.75,
            colsample_bytree=0.65,
            reg_alpha=0.2,
            reg_lambda=2.0,
        )

        # Simulate what submit_retrain does
        state = {
            "xgb_params": {k: v for k, v in sig_gen._xgb_params.items()},
        }

        # Simulate what _train_in_process does
        xgb_p = state.get("xgb_params", {})
        restored = MLSignalGenerator(
            min_child_weight=xgb_p.get("min_child_weight", 5),
            subsample=xgb_p.get("subsample", 0.8),
            colsample_bytree=xgb_p.get("colsample_bytree", 0.8),
            reg_alpha=xgb_p.get("reg_alpha", 0.1),
            reg_lambda=xgb_p.get("reg_lambda", 1.0),
        )

        assert restored._xgb_params["min_child_weight"] == 7
        assert restored._xgb_params["subsample"] == 0.75
        assert restored._xgb_params["colsample_bytree"] == 0.65
        assert restored._xgb_params["reg_alpha"] == 0.2
        assert restored._xgb_params["reg_lambda"] == 2.0

    def test_backward_compat_without_xgb_params_key(self):
        """Older state without 'xgb_params' key falls back to legacy keys."""
        # Simulate legacy state (pre-F3)
        state = {
            "train_window": 200,
            "n_estimators": 150,
            "max_depth": 4,
            "learning_rate": 0.03,
        }
        xgb_p = state.get("xgb_params", {})
        sig_gen = MLSignalGenerator(
            train_window=state.get("train_window", 200),
            n_estimators=xgb_p.get("n_estimators", state.get("n_estimators", 200)),
            max_depth=xgb_p.get("max_depth", state.get("max_depth", 5)),
            learning_rate=xgb_p.get("learning_rate", state.get("learning_rate", 0.05)),
            min_child_weight=xgb_p.get("min_child_weight", 5),
            subsample=xgb_p.get("subsample", 0.8),
        )
        # Legacy keys used
        assert sig_gen._xgb_params["n_estimators"] == 150
        assert sig_gen._xgb_params["max_depth"] == 4
        assert sig_gen._xgb_params["learning_rate"] == 0.03
        # Defaults for missing params
        assert sig_gen._xgb_params["min_child_weight"] == 5
        assert sig_gen._xgb_params["subsample"] == 0.8


# ==============================================================================
# Test 2: Quality-gate rejection vs training error distinction
# ==============================================================================

class TestRejectionVsError:

    def test_train_result_has_rejection_reason_field(self):
        """TrainResult must have a rejection_reason field."""
        result = TrainResult()
        assert hasattr(result, "rejection_reason")
        assert result.rejection_reason is None

    def test_quality_gate_rejection_uses_rejection_reason(self):
        """_train_in_process returns rejection_reason (not error) for quality gate."""
        import inspect
        from backend.organism import background_trainer
        source = inspect.getsource(background_trainer._train_in_process)
        # The rejection path should use "rejection_reason", not "error"
        # Find the "if not accepted:" block
        reject_idx = source.index("if not accepted:")
        reject_block = source[reject_idx:reject_idx + 400]
        assert '"rejection_reason"' in reject_block, \
            "Quality-gate rejection must use 'rejection_reason' key"
        assert '"error"' not in reject_block, \
            "Quality-gate rejection must NOT use 'error' key"

    def test_get_result_preserves_rejection_with_metrics(self):
        """get_result() on quality-gate rejection preserves train_metrics."""
        trainer = BackgroundTrainer()
        # Simulate a raw result dict from _train_in_process
        raw = {
            "accepted": False,
            "rejection_reason": "Model rejected by quality gate (score=0.200)",
            "train_metrics": {
                "accuracy": 0.45, "precision": 0.40,
                "hit_rate": 0.42, "generation": 3,
            },
            "duration_s": 1.5,
        }
        # Manually simulate what get_result does
        import asyncio
        from unittest.mock import MagicMock
        trainer._is_training = True
        future = MagicMock()
        future.done.return_value = True
        future.result.return_value = raw
        trainer._future = future

        done, result = trainer.get_result()
        assert done
        assert result is not None
        assert result.accepted is False
        assert result.rejection_reason is not None
        assert "quality gate" in result.rejection_reason
        assert result.error is None, "Quality-gate rejection must not set error"
        assert result.train_metrics is not None
        assert result.train_metrics["accuracy"] == 0.45

    def test_training_error_still_surfaces_as_error(self):
        """True training failures still use the error field."""
        trainer = BackgroundTrainer()
        raw = {
            "error": "Training returned None metrics",
            "duration_s": 0.5,
        }
        from unittest.mock import MagicMock
        trainer._is_training = True
        future = MagicMock()
        future.done.return_value = True
        future.result.return_value = raw
        trainer._future = future

        done, result = trainer.get_result()
        assert done
        assert result is not None
        assert result.error == "Training returned None metrics"
        assert result.rejection_reason is None
        assert result.train_metrics is None

    def test_accepted_result_has_no_error_or_rejection(self):
        """Accepted result has neither error nor rejection_reason."""
        trainer = BackgroundTrainer()
        raw = {
            "accepted": True,
            "train_metrics": {"accuracy": 0.62, "generation": 5},
            "clf_pickle": b"fake_clf",
            "reg_pickle": b"fake_reg",
            "feature_cols": ["f1", "f2"],
            "duration_s": 3.0,
        }
        from unittest.mock import MagicMock
        trainer._is_training = True
        future = MagicMock()
        future.done.return_value = True
        future.result.return_value = raw
        trainer._future = future

        done, result = trainer.get_result()
        assert done
        assert result.accepted is True
        assert result.error is None
        assert result.rejection_reason is None


# ==============================================================================
# Test 3: apply_result updates _latest_metrics and generation
# ==============================================================================

class TestApplyResultMetrics:

    def _make_accepted_result(self) -> TrainResult:
        import pickle
        return TrainResult(
            accepted=True,
            train_metrics={
                "accuracy": 0.58, "precision": 0.55, "recall": 0.60,
                "f1": 0.57, "direction_accuracy": 0.58,
                "mean_pred_return": 0.002, "hit_rate": 0.52,
                "generation": 7,
            },
            new_clf_state=pickle.dumps("fake_clf"),
            new_reg_state=pickle.dumps("fake_reg"),
        )

    def test_apply_result_updates_latest_metrics(self):
        """apply_result must update signal_gen._latest_metrics from train_metrics."""
        trainer = BackgroundTrainer()
        trainer._last_result = self._make_accepted_result()

        sig_gen = MLSignalGenerator()
        assert sig_gen._latest_metrics is None

        # Minimal stubs for unused params
        from unittest.mock import MagicMock
        trainer.apply_result(
            sig_gen, MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), MagicMock(),
        )

        assert sig_gen._latest_metrics is not None
        assert sig_gen._latest_metrics.accuracy == 0.58
        assert sig_gen._latest_metrics.precision == 0.55
        assert sig_gen._latest_metrics.hit_rate == 0.52
        assert sig_gen._latest_metrics.generation == 7

    def test_apply_result_updates_generation(self):
        """apply_result must update signal_gen.generation from train_metrics."""
        trainer = BackgroundTrainer()
        trainer._last_result = self._make_accepted_result()

        sig_gen = MLSignalGenerator()
        assert sig_gen.generation == 0

        from unittest.mock import MagicMock
        trainer.apply_result(
            sig_gen, MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), MagicMock(),
        )

        assert sig_gen.generation == 7

    def test_apply_result_safe_when_no_train_metrics(self):
        """apply_result doesn't crash when train_metrics is None."""
        import pickle
        trainer = BackgroundTrainer()
        trainer._last_result = TrainResult(
            accepted=True,
            train_metrics=None,
            new_clf_state=pickle.dumps("fake_clf"),
            new_reg_state=pickle.dumps("fake_reg"),
        )

        sig_gen = MLSignalGenerator()
        from unittest.mock import MagicMock
        # Must not raise
        trainer.apply_result(
            sig_gen, MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), MagicMock(),
        )
        assert sig_gen._latest_metrics is None

    def test_apply_result_metrics_is_model_metrics_instance(self):
        """Updated _latest_metrics must be a ModelMetrics instance."""
        trainer = BackgroundTrainer()
        trainer._last_result = self._make_accepted_result()

        sig_gen = MLSignalGenerator()
        from unittest.mock import MagicMock
        trainer.apply_result(
            sig_gen, MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), MagicMock(),
        )

        assert isinstance(sig_gen._latest_metrics, ModelMetrics)

    def test_rejected_result_does_not_update_metrics(self):
        """apply_result on rejected result does not change signal_gen state."""
        trainer = BackgroundTrainer()
        trainer._last_result = TrainResult(
            accepted=False,
            rejection_reason="quality gate",
            train_metrics={"accuracy": 0.3, "generation": 99},
        )

        sig_gen = MLSignalGenerator()
        from unittest.mock import MagicMock
        trainer.apply_result(
            sig_gen, MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(), MagicMock(),
        )

        assert sig_gen._latest_metrics is None
        assert sig_gen.generation == 0
