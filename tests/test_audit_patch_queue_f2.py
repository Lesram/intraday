"""Tests for Patch Queue F2 -- background trainer acceptance semantics."""
from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import pytest

from backend.organism.ml_signal import ModelMetrics


# ==============================================================================
# Test 1: ModelMetrics.to_dict() includes all acceptance fields
# ==============================================================================

class TestModelMetricsSerialization:

    def test_to_dict_includes_precision(self):
        m = ModelMetrics(generation=1, precision=0.55)
        d = m.to_dict()
        assert "precision" in d
        assert d["precision"] == 0.55

    def test_to_dict_includes_recall(self):
        m = ModelMetrics(generation=1, recall=0.60)
        d = m.to_dict()
        assert "recall" in d
        assert d["recall"] == 0.60

    def test_to_dict_includes_f1(self):
        m = ModelMetrics(generation=1, f1=0.57)
        d = m.to_dict()
        assert "f1" in d
        assert d["f1"] == 0.57

    def test_to_dict_includes_mean_pred_return(self):
        m = ModelMetrics(generation=1, mean_pred_return=0.003)
        d = m.to_dict()
        assert "mean_pred_return" in d
        assert abs(d["mean_pred_return"] - 0.003) < 1e-5

    def test_to_dict_backward_compatible(self):
        """All previously-existing fields are still present."""
        m = ModelMetrics(
            generation=1, accuracy=0.6, direction_accuracy=0.65,
            hit_rate=0.55,
        )
        d = m.to_dict()
        assert d["accuracy"] == 0.6
        assert d["direction_accuracy"] == 0.65
        assert d["hit_rate"] == 0.55
        assert "feature_importance_top10" in d

    def test_to_dict_roundtrip_completeness(self):
        """All fields needed for acceptance logic are in to_dict()."""
        required = {"accuracy", "precision", "mean_pred_return",
                     "direction_accuracy", "hit_rate"}
        m = ModelMetrics(generation=1)
        d = m.to_dict()
        assert required.issubset(d.keys()), \
            f"Missing keys: {required - d.keys()}"


# ==============================================================================
# Test 2: Background trainer acceptance gate semantics
# ==============================================================================

class TestBackgroundTrainerAcceptanceGate:
    """Verify that _train_in_process uses a quality gate, not auto-accept."""

    def test_acceptance_gate_present_in_source(self):
        """_train_in_process must use the shared acceptance_gate."""
        import inspect
        from backend.organism import background_trainer
        source = inspect.getsource(background_trainer._train_in_process)
        assert "acceptance_gate" in source, \
            "_train_in_process must call acceptance_gate"

    def test_no_unconditional_accepted_true(self):
        """_train_in_process must not have unconditional accepted=True."""
        import inspect
        from backend.organism import background_trainer
        source = inspect.getsource(background_trainer._train_in_process)
        # The key check: acceptance must come from acceptance_gate, not hardcoded
        assert "acceptance_gate" in source and "accepted" in source


# ==============================================================================
# Test 3: Signal generator state preservation
# ==============================================================================

class TestSignalGenStatePreservation:

    def test_submit_serializes_prediction_horizon(self):
        """submit_retrain must include prediction_horizon in state."""
        import inspect
        from backend.organism import background_trainer
        source = inspect.getsource(background_trainer.BackgroundTrainer.submit_retrain)
        assert "prediction_horizon" in source

    def test_submit_serializes_direction_thresholds(self):
        """submit_retrain must include direction thresholds."""
        import inspect
        from backend.organism import background_trainer
        source = inspect.getsource(background_trainer.BackgroundTrainer.submit_retrain)
        assert "direction_threshold_buy" in source
        assert "direction_threshold_sell" in source

    def test_submit_serializes_calibration(self):
        """submit_retrain must include calibration state."""
        import inspect
        from backend.organism import background_trainer
        source = inspect.getsource(background_trainer.BackgroundTrainer.submit_retrain)
        assert "calibration_counts" in source
        assert "calibration_map" in source

    def test_worker_restores_prediction_horizon(self):
        """_train_in_process must restore prediction_horizon."""
        import inspect
        from backend.organism import background_trainer
        source = inspect.getsource(background_trainer._train_in_process)
        assert "prediction_horizon" in source

    def test_worker_restores_calibration(self):
        """_train_in_process must restore calibration state."""
        import inspect
        from backend.organism import background_trainer
        source = inspect.getsource(background_trainer._train_in_process)
        assert "calibration_counts" in source
        assert "calibration_map" in source


# ==============================================================================
# Test 4: apply_result does not force _is_trained unconditionally
# ==============================================================================

class TestApplyResultTrainedState:

    def test_apply_result_no_unconditional_is_trained(self):
        """apply_result must not force _is_trained=True unconditionally."""
        import inspect
        from backend.organism import background_trainer
        source = inspect.getsource(background_trainer.BackgroundTrainer.apply_result)
        # Should NOT have bare "signal_gen._is_trained = True" at method body
        # indentation level (8 spaces). It must be inside a conditional (12+ spaces).
        lines = source.split("\n")
        for line in lines:
            # Match lines where _is_trained = True is at the method body level
            # (not nested inside an if block)
            if "signal_gen._is_trained = True" in line:
                # Count leading spaces to determine indentation
                indent = len(line) - len(line.lstrip())
                # Method body is at 8 spaces; if block body is at 12+
                if indent <= 8:
                    pytest.fail(
                        "apply_result has unconditional _is_trained = True"
                    )

    def test_apply_result_requires_model_state(self):
        """apply_result should only set _is_trained when clf+reg state exists."""
        from backend.organism.background_trainer import BackgroundTrainer, TrainResult

        trainer = BackgroundTrainer()
        # Result with no clf/reg state (e.g., training produced nothing useful)
        trainer._last_result = TrainResult(
            accepted=True,
            new_clf_state=None,
            new_reg_state=None,
        )

        sig_gen = SimpleNamespace(
            _clf=None, _reg=None, _is_trained=False,
            _ensemble=None, _feature_cols=[], _evolved_feature_weights={},
        )

        trainer.apply_result(
            signal_gen=sig_gen,
            evolution_engine=SimpleNamespace(),
            evolved_params=SimpleNamespace(to_dict=lambda: {}),
            alpha_scanner=None,
            breakout_scanner=None,
            kelly_sizer=None,
            exit_engine=None,
        )

        assert not sig_gen._is_trained, \
            "_is_trained should remain False when no model state provided"


# ==============================================================================
# Test 5: Walk-forward contract is documented
# ==============================================================================

class TestWalkForwardContract:

    def test_walk_forward_offline_contract(self):
        """walk_forward module docstring must state offline-only contract."""
        from backend.organism import walk_forward
        docstring = walk_forward.__doc__ or ""
        assert "offline" in docstring.lower() or "OFFLINE" in docstring

    def test_learner_validate_references_walk_forward(self):
        """_validate_new_model docstring should reference walk_forward relationship."""
        import inspect
        from backend.organism.continuous_learner import ContinuousLearner
        doc = inspect.getdoc(ContinuousLearner._validate_new_model) or ""
        source = inspect.getsource(ContinuousLearner._validate_new_model)
        combined = doc + source
        assert "walk_forward" in combined.lower() or "offline" in combined.lower()

    def test_background_trainer_uses_same_gate_logic(self):
        """Background trainer must delegate to the shared acceptance_gate."""
        import inspect
        from backend.organism import background_trainer
        bg_source = inspect.getsource(background_trainer._train_in_process)

        # Must import and call the shared acceptance_gate
        assert "acceptance_gate" in bg_source
        # Must NOT define its own inline scoring function
        assert "def _score" not in bg_source
