"""
Comprehensive tests for backend/ml/ensemble_framework.py

This module tests all classes and functions in the ensemble_framework module:
- VotingStrategy enum
- ModelPredictionResult dataclass
- EnsemblePredictionResult dataclass
- ModelPerformanceTracker
- EnsembleManager (predict, register/unregister, voting strategies, etc.)
- create_ensemble factory function
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from backend.ml.ensemble_framework import (
    VotingStrategy,
    ModelPredictionResult,
    EnsemblePredictionResult,
    ModelPerformanceTracker,
    EnsembleManager,
    create_ensemble,
)


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def sample_model_prediction():
    """Create a sample model prediction result."""
    return ModelPredictionResult(
        model_id="model_001",
        model_name="Test Model",
        prediction=0.75,
        confidence=0.85,
        direction="long",
        latency_ms=15.5,
    )


@pytest.fixture
def mock_model():
    """Create a mock model that follows the BaseModel protocol."""
    model = MagicMock()
    model.model_id = "mock_model_1"
    model.model_name = "Mock Model 1"
    model.predict = AsyncMock(
        return_value=ModelPredictionResult(
            model_id="mock_model_1",
            model_name="Mock Model 1",
            prediction=0.5,
            confidence=0.8,
            direction="long",
            latency_ms=10.0,
        )
    )
    return model


@pytest.fixture
def mock_model_2():
    """Create a second mock model."""
    model = MagicMock()
    model.model_id = "mock_model_2"
    model.model_name = "Mock Model 2"
    model.predict = AsyncMock(
        return_value=ModelPredictionResult(
            model_id="mock_model_2",
            model_name="Mock Model 2",
            prediction=0.3,
            confidence=0.7,
            direction="long",
            latency_ms=12.0,
        )
    )
    return model


@pytest.fixture
def mock_short_model():
    """Create a mock model with short prediction."""
    model = MagicMock()
    model.model_id = "mock_short_model"
    model.model_name = "Mock Short Model"
    model.predict = AsyncMock(
        return_value=ModelPredictionResult(
            model_id="mock_short_model",
            model_name="Mock Short Model",
            prediction=-0.4,
            confidence=0.6,
            direction="short",
            latency_ms=8.0,
        )
    )
    return model


# ==============================================================================
# VotingStrategy Tests
# ==============================================================================


class TestVotingStrategy:
    """Tests for VotingStrategy enum."""

    def test_all_strategies_exist(self):
        """Test all voting strategies are defined."""
        assert VotingStrategy.WEIGHTED_AVERAGE.value == "weighted_average"
        assert VotingStrategy.MAJORITY_VOTE.value == "majority_vote"
        assert VotingStrategy.CONFIDENCE_WEIGHTED.value == "confidence_weighted"
        assert VotingStrategy.STACKING.value == "stacking"
        assert VotingStrategy.DYNAMIC.value == "dynamic"

    def test_enum_count(self):
        """Test number of strategies."""
        assert len(VotingStrategy) == 5


# ==============================================================================
# ModelPredictionResult Tests
# ==============================================================================


class TestModelPredictionResult:
    """Tests for ModelPredictionResult dataclass."""

    def test_basic_creation(self):
        """Test basic result creation."""
        result = ModelPredictionResult(
            model_id="test_model",
            model_name="Test",
            prediction=0.5,
            confidence=0.8,
            direction="long",
            latency_ms=10.0,
        )

        assert result.model_id == "test_model"
        assert result.model_name == "Test"
        assert result.prediction == 0.5
        assert result.confidence == 0.8
        assert result.direction == "long"
        assert result.latency_ms == 10.0

    def test_default_timestamp(self):
        """Test timestamp defaults to now."""
        result = ModelPredictionResult(
            model_id="test",
            model_name="Test",
            prediction=0.0,
            confidence=0.5,
            direction="neutral",
            latency_ms=5.0,
        )

        assert result.timestamp is not None
        assert isinstance(result.timestamp, datetime)

    def test_default_features_used(self):
        """Test features_used defaults to empty list."""
        result = ModelPredictionResult(
            model_id="test",
            model_name="Test",
            prediction=0.0,
            confidence=0.5,
            direction="neutral",
            latency_ms=5.0,
        )

        assert result.features_used == []

    def test_default_metadata(self):
        """Test metadata defaults to empty dict."""
        result = ModelPredictionResult(
            model_id="test",
            model_name="Test",
            prediction=0.0,
            confidence=0.5,
            direction="neutral",
            latency_ms=5.0,
        )

        assert result.metadata == {}

    def test_signal_strength_long(self):
        """Test signal_strength for long prediction."""
        result = ModelPredictionResult(
            model_id="test",
            model_name="Test",
            prediction=0.5,
            confidence=0.8,
            direction="long",
            latency_ms=5.0,
        )

        assert result.signal_strength == 0.8  # confidence * 1.0

    def test_signal_strength_short(self):
        """Test signal_strength for short prediction."""
        result = ModelPredictionResult(
            model_id="test",
            model_name="Test",
            prediction=-0.5,
            confidence=0.8,
            direction="short",
            latency_ms=5.0,
        )

        assert result.signal_strength == -0.8  # confidence * -1.0

    def test_signal_strength_neutral(self):
        """Test signal_strength for neutral prediction."""
        result = ModelPredictionResult(
            model_id="test",
            model_name="Test",
            prediction=0.0,
            confidence=0.8,
            direction="neutral",
            latency_ms=5.0,
        )

        assert result.signal_strength == 0.0  # confidence * 0


# ==============================================================================
# EnsemblePredictionResult Tests
# ==============================================================================


class TestEnsemblePredictionResult:
    """Tests for EnsemblePredictionResult dataclass."""

    def test_basic_creation(self, sample_model_prediction):
        """Test basic result creation."""
        result = EnsemblePredictionResult(
            symbol="AAPL",
            final_prediction=0.6,
            final_confidence=0.85,
            final_direction="long",
            voting_strategy=VotingStrategy.CONFIDENCE_WEIGHTED,
            individual_predictions=[sample_model_prediction],
            model_weights={"model_001": 1.0},
            agreement_score=1.0,
        )

        assert result.symbol == "AAPL"
        assert result.final_prediction == 0.6
        assert result.final_confidence == 0.85
        assert result.final_direction == "long"

    def test_model_count_property(self, sample_model_prediction):
        """Test model_count property."""
        result = EnsemblePredictionResult(
            symbol="AAPL",
            final_prediction=0.6,
            final_confidence=0.85,
            final_direction="long",
            voting_strategy=VotingStrategy.WEIGHTED_AVERAGE,
            individual_predictions=[sample_model_prediction, sample_model_prediction],
            model_weights={},
            agreement_score=1.0,
        )

        assert result.model_count == 2

    def test_active_models_property(self, sample_model_prediction):
        """Test active_models property."""
        result = EnsemblePredictionResult(
            symbol="AAPL",
            final_prediction=0.6,
            final_confidence=0.85,
            final_direction="long",
            voting_strategy=VotingStrategy.WEIGHTED_AVERAGE,
            individual_predictions=[sample_model_prediction],
            model_weights={},
            agreement_score=1.0,
        )

        assert result.active_models == ["Test Model"]


# ==============================================================================
# ModelPerformanceTracker Tests
# ==============================================================================


class TestModelPerformanceTracker:
    """Tests for ModelPerformanceTracker class."""

    def test_basic_creation(self):
        """Test basic tracker creation."""
        tracker = ModelPerformanceTracker(model_id="test_model")

        assert tracker.model_id == "test_model"
        assert tracker.window_size == 100
        assert len(tracker.predictions) == 0

    def test_custom_window_size(self):
        """Test tracker with custom window size."""
        tracker = ModelPerformanceTracker(model_id="test", window_size=50)
        assert tracker.window_size == 50

    def test_record_prediction(self):
        """Test recording predictions."""
        tracker = ModelPerformanceTracker(model_id="test")

        tracker.record_prediction(
            prediction=0.5,
            confidence=0.8,
            latency_ms=10.0,
        )

        assert len(tracker.predictions) == 1
        assert len(tracker.confidences) == 1
        assert len(tracker.latencies) == 1

    def test_record_actual(self):
        """Test recording actuals."""
        tracker = ModelPerformanceTracker(model_id="test")

        # First record prediction, then actual
        tracker.record_prediction(0.5, 0.8, 10.0)
        tracker.record_actual(0.6)

        assert len(tracker.actuals) == 1

    def test_avg_latency_calculation(self):
        """Test average latency is calculated correctly."""
        tracker = ModelPerformanceTracker(model_id="test")

        tracker.record_prediction(0.5, 0.8, 10.0)
        tracker.record_prediction(0.5, 0.8, 20.0)
        tracker.record_prediction(0.5, 0.8, 30.0)

        assert tracker.avg_latency_ms == 20.0  # Average of 10, 20, 30

    def test_accuracy_property(self):
        """Test accuracy calculation."""
        tracker = ModelPerformanceTracker(model_id="test")

        # Perfect predictions
        tracker.record_prediction(1.0, 0.9, 10.0)
        tracker.record_actual(1.0)
        tracker.record_prediction(1.0, 0.9, 10.0)
        tracker.record_actual(1.0)

        # Accuracy should be 1.0 (both correct direction)
        assert tracker.accuracy == 1.0

    def test_mae_property(self):
        """Test MAE calculation."""
        tracker = ModelPerformanceTracker(model_id="test")

        tracker.record_prediction(1.0, 0.9, 10.0)
        tracker.record_actual(0.5)
        tracker.record_prediction(2.0, 0.9, 10.0)
        tracker.record_actual(1.5)

        # MAE = (0.5 + 0.5) / 2 = 0.5
        assert abs(tracker.mae - 0.5) < 0.01

    def test_reliability_score_needs_data(self):
        """Test reliability score needs sufficient data."""
        tracker = ModelPerformanceTracker(model_id="test")

        # Initial reliability is 1.0
        assert tracker.reliability_score == 1.0

        # Add some predictions
        for i in range(10):
            tracker.record_prediction(0.5, 0.8, 10.0)

        # Reliability should be recalculated
        assert 0 <= tracker.reliability_score <= 1

    def test_performance_score_combined(self):
        """Test combined performance score."""
        tracker = ModelPerformanceTracker(model_id="test")

        # Add data
        for i in range(10):
            tracker.record_prediction(0.5, 0.8, 50.0)  # Fast latency
            tracker.record_actual(0.5)  # Perfect accuracy

        score = tracker.performance_score
        assert 0 <= score <= 1

    def test_window_size_limits(self):
        """Test deque respects window size."""
        tracker = ModelPerformanceTracker(model_id="test", window_size=5)

        for i in range(10):
            tracker.record_prediction(float(i), 0.8, 10.0)

        # Should only keep last 5
        assert len(tracker.predictions) == 5


# ==============================================================================
# EnsembleManager Tests
# ==============================================================================


class TestEnsembleManagerInit:
    """Tests for EnsembleManager initialization."""

    def test_default_init(self):
        """Test default initialization."""
        manager = EnsembleManager()

        assert manager.strategy == VotingStrategy.CONFIDENCE_WEIGHTED
        assert manager.min_models == 1
        assert manager.max_latency_ms == 5000.0
        assert manager.enable_dynamic_weights
        assert len(manager._models) == 0

    def test_custom_init(self):
        """Test custom initialization."""
        manager = EnsembleManager(
            strategy=VotingStrategy.MAJORITY_VOTE,
            min_models=3,
            max_latency_ms=1000.0,
            enable_dynamic_weights=False,
        )

        assert manager.strategy == VotingStrategy.MAJORITY_VOTE
        assert manager.min_models == 3
        assert manager.max_latency_ms == 1000.0
        assert not manager.enable_dynamic_weights


class TestEnsembleManagerRegistration:
    """Tests for model registration."""

    def test_register_model(self, mock_model):
        """Test registering a model."""
        manager = EnsembleManager()
        manager.register_model(mock_model, weight=1.5)

        assert mock_model.model_id in manager._models
        assert manager._base_weights[mock_model.model_id] == 1.5
        assert manager._enabled[mock_model.model_id]

    def test_register_model_disabled(self, mock_model):
        """Test registering a disabled model."""
        manager = EnsembleManager()
        manager.register_model(mock_model, enabled=False)

        assert not manager._enabled[mock_model.model_id]

    def test_unregister_model(self, mock_model):
        """Test unregistering a model."""
        manager = EnsembleManager()
        manager.register_model(mock_model)
        manager.unregister_model(mock_model.model_id)

        assert mock_model.model_id not in manager._models

    def test_set_model_enabled(self, mock_model):
        """Test enabling/disabling a model."""
        manager = EnsembleManager()
        manager.register_model(mock_model)

        manager.set_model_enabled(mock_model.model_id, False)
        assert not manager._enabled[mock_model.model_id]

        manager.set_model_enabled(mock_model.model_id, True)
        assert manager._enabled[mock_model.model_id]


class TestEnsembleManagerWeights:
    """Tests for weight calculation."""

    def test_get_effective_weights_single(self, mock_model):
        """Test effective weights with single model."""
        manager = EnsembleManager()
        manager.register_model(mock_model, weight=1.0)

        weights = manager.get_effective_weights()

        assert mock_model.model_id in weights
        assert weights[mock_model.model_id] == 1.0  # Normalized to 1.0

    def test_get_effective_weights_multiple(self, mock_model, mock_model_2):
        """Test effective weights with multiple models."""
        manager = EnsembleManager(enable_dynamic_weights=False)
        manager.register_model(mock_model, weight=2.0)
        manager.register_model(mock_model_2, weight=2.0)

        weights = manager.get_effective_weights()

        # Both should have equal normalized weights
        assert abs(weights[mock_model.model_id] - 0.5) < 0.01
        assert abs(weights[mock_model_2.model_id] - 0.5) < 0.01

    def test_effective_weights_exclude_disabled(self, mock_model, mock_model_2):
        """Test disabled models are excluded from weights."""
        manager = EnsembleManager()
        manager.register_model(mock_model, weight=1.0)
        manager.register_model(mock_model_2, weight=1.0, enabled=False)

        weights = manager.get_effective_weights()

        assert mock_model.model_id in weights
        assert mock_model_2.model_id not in weights


class TestEnsembleManagerPredict:
    """Tests for prediction functionality."""

    @pytest.mark.asyncio
    async def test_basic_predict(self, mock_model):
        """Test basic ensemble prediction."""
        manager = EnsembleManager()
        manager.register_model(mock_model)

        result = await manager.predict(symbol="AAPL", features={"close": 150.0})

        assert isinstance(result, EnsemblePredictionResult)
        assert result.symbol == "AAPL"
        assert len(result.individual_predictions) == 1

    @pytest.mark.asyncio
    async def test_predict_multiple_models(self, mock_model, mock_model_2):
        """Test prediction with multiple models."""
        manager = EnsembleManager()
        manager.register_model(mock_model)
        manager.register_model(mock_model_2)

        result = await manager.predict(symbol="AAPL", features={})

        assert result.model_count == 2
        assert len(result.model_weights) == 2

    @pytest.mark.asyncio
    async def test_predict_insufficient_models_raises(self, mock_model):
        """Test error when insufficient models."""
        manager = EnsembleManager(min_models=3)
        manager.register_model(mock_model)

        with pytest.raises(ValueError, match="Insufficient active models"):
            await manager.predict(symbol="AAPL", features={})

    @pytest.mark.asyncio
    async def test_predict_records_performance(self, mock_model):
        """Test prediction records performance metrics."""
        manager = EnsembleManager()
        manager.register_model(mock_model)

        await manager.predict(symbol="AAPL", features={})

        perf = manager._performance[mock_model.model_id]
        assert len(perf.predictions) == 1

    @pytest.mark.asyncio
    async def test_predict_with_timeout_model(self):
        """Test handling of model timeout."""
        async def slow_predict(*args, **kwargs):
            await asyncio.sleep(10)  # Way beyond timeout
            return ModelPredictionResult(
                model_id="slow",
                model_name="Slow",
                prediction=0.5,
                confidence=0.8,
                direction="long",
                latency_ms=10000,
            )

        slow_model = MagicMock()
        slow_model.model_id = "slow_model"
        slow_model.model_name = "Slow Model"
        slow_model.predict = slow_predict

        fast_model = MagicMock()
        fast_model.model_id = "fast_model"
        fast_model.model_name = "Fast Model"
        fast_model.predict = AsyncMock(
            return_value=ModelPredictionResult(
                model_id="fast_model",
                model_name="Fast Model",
                prediction=0.5,
                confidence=0.8,
                direction="long",
                latency_ms=5,
            )
        )

        manager = EnsembleManager(min_models=1, max_latency_ms=100)
        manager.register_model(slow_model)
        manager.register_model(fast_model)

        result = await manager.predict(symbol="AAPL", features={})

        # Only fast model should respond
        assert result.model_count == 1
        assert result.individual_predictions[0].model_id == "fast_model"

    @pytest.mark.asyncio
    async def test_predict_all_fail_raises(self):
        """Test error when all models fail."""
        async def failing_predict(*args, **kwargs):
            raise RuntimeError("Model failed")

        fail_model = MagicMock()
        fail_model.model_id = "fail_model"
        fail_model.model_name = "Fail Model"
        fail_model.predict = failing_predict

        manager = EnsembleManager()
        manager.register_model(fail_model)

        with pytest.raises(RuntimeError, match="All models failed"):
            await manager.predict(symbol="AAPL", features={})


class TestEnsembleManagerVotingStrategies:
    """Tests for different voting strategies."""

    @pytest.mark.asyncio
    async def test_weighted_average_strategy(self, mock_model, mock_model_2):
        """Test weighted average voting."""
        manager = EnsembleManager(
            strategy=VotingStrategy.WEIGHTED_AVERAGE,
            enable_dynamic_weights=False,
        )
        manager.register_model(mock_model, weight=1.0)
        manager.register_model(mock_model_2, weight=1.0)

        result = await manager.predict(symbol="AAPL", features={})

        # Average of 0.5 and 0.3 = 0.4
        assert result.voting_strategy == VotingStrategy.WEIGHTED_AVERAGE
        assert 0.3 <= result.final_prediction <= 0.5

    @pytest.mark.asyncio
    async def test_majority_vote_strategy(self, mock_model, mock_model_2, mock_short_model):
        """Test majority vote for direction."""
        manager = EnsembleManager(strategy=VotingStrategy.MAJORITY_VOTE)
        manager.register_model(mock_model)
        manager.register_model(mock_model_2)
        manager.register_model(mock_short_model)

        result = await manager.predict(symbol="AAPL", features={})

        # 2 long, 1 short = long wins
        assert result.final_direction == "long"
        assert result.voting_strategy == VotingStrategy.MAJORITY_VOTE

    @pytest.mark.asyncio
    async def test_confidence_weighted_strategy(self, mock_model):
        """Test confidence-weighted voting."""
        manager = EnsembleManager(strategy=VotingStrategy.CONFIDENCE_WEIGHTED)
        manager.register_model(mock_model)

        result = await manager.predict(symbol="AAPL", features={})

        assert result.voting_strategy == VotingStrategy.CONFIDENCE_WEIGHTED

    @pytest.mark.asyncio
    async def test_dynamic_strategy(self, mock_model):
        """Test dynamic strategy."""
        manager = EnsembleManager(strategy=VotingStrategy.DYNAMIC)
        manager.register_model(mock_model)

        result = await manager.predict(symbol="AAPL", features={})

        assert result.voting_strategy == VotingStrategy.DYNAMIC

    @pytest.mark.asyncio
    async def test_stacking_strategy_no_metalearner(self, mock_model, mock_model_2):
        """Test stacking falls back without meta-learner."""
        manager = EnsembleManager(strategy=VotingStrategy.STACKING)
        manager.register_model(mock_model)
        manager.register_model(mock_model_2)

        result = await manager.predict(symbol="AAPL", features={})

        # Should fall back to confidence-weighted
        assert result.voting_strategy == VotingStrategy.STACKING


class TestEnsembleManagerAgreement:
    """Tests for agreement calculation."""

    @pytest.mark.asyncio
    async def test_full_agreement(self, mock_model, mock_model_2):
        """Test 100% agreement when all models agree."""
        manager = EnsembleManager()
        manager.register_model(mock_model)
        manager.register_model(mock_model_2)

        result = await manager.predict(symbol="AAPL", features={})

        # Both predict long
        assert result.agreement_score == 1.0

    @pytest.mark.asyncio
    async def test_partial_agreement(self, mock_model, mock_short_model):
        """Test partial agreement with conflicting predictions."""
        manager = EnsembleManager()
        manager.register_model(mock_model)
        manager.register_model(mock_short_model)

        result = await manager.predict(symbol="AAPL", features={})

        # 1 long, 1 short = 50% agreement
        assert result.agreement_score == 0.5


class TestEnsembleManagerHealth:
    """Tests for health monitoring."""

    def test_get_model_health(self, mock_model):
        """Test getting model health metrics."""
        manager = EnsembleManager()
        manager.register_model(mock_model, weight=1.5)

        health = manager.get_model_health()

        assert mock_model.model_id in health
        assert health[mock_model.model_id]["enabled"]
        assert health[mock_model.model_id]["base_weight"] == 1.5
        assert "accuracy" in health[mock_model.model_id]
        assert "mae" in health[mock_model.model_id]

    def test_get_ensemble_status(self, mock_model, mock_model_2):
        """Test getting ensemble status."""
        manager = EnsembleManager(min_models=1)
        manager.register_model(mock_model)
        manager.register_model(mock_model_2, enabled=False)

        status = manager.get_ensemble_status()

        assert status["strategy"] == "confidence_weighted"
        assert status["total_models"] == 2
        assert status["active_models"] == 1
        assert status["healthy"]

    def test_ensemble_unhealthy_insufficient_models(self, mock_model):
        """Test unhealthy status with insufficient models."""
        manager = EnsembleManager(min_models=5)
        manager.register_model(mock_model)

        status = manager.get_ensemble_status()

        assert not status["healthy"]

    def test_record_actual(self, mock_model):
        """Test recording actual outcomes."""
        manager = EnsembleManager()
        manager.register_model(mock_model)

        # Record a prediction first
        manager._performance[mock_model.model_id].record_prediction(0.5, 0.8, 10.0)

        # Record actual
        manager.record_actual(mock_model.model_id, 0.6)

        assert len(manager._performance[mock_model.model_id].actuals) == 1


# ==============================================================================
# create_ensemble Factory Tests
# ==============================================================================


class TestCreateEnsemble:
    """Tests for create_ensemble factory function."""

    def test_create_with_defaults(self):
        """Test creating ensemble with defaults."""
        ensemble = create_ensemble()

        assert isinstance(ensemble, EnsembleManager)
        assert ensemble.strategy == VotingStrategy.CONFIDENCE_WEIGHTED
        assert ensemble.min_models == 1
        assert ensemble.enable_dynamic_weights

    def test_create_weighted_average(self):
        """Test creating weighted average ensemble."""
        ensemble = create_ensemble(strategy="weighted_average")

        assert ensemble.strategy == VotingStrategy.WEIGHTED_AVERAGE

    def test_create_majority_vote(self):
        """Test creating majority vote ensemble."""
        ensemble = create_ensemble(strategy="majority_vote")

        assert ensemble.strategy == VotingStrategy.MAJORITY_VOTE

    def test_create_with_custom_min_models(self):
        """Test creating ensemble with custom min_models."""
        ensemble = create_ensemble(min_models=3)

        assert ensemble.min_models == 3

    def test_create_without_dynamic_weights(self):
        """Test creating ensemble without dynamic weights."""
        ensemble = create_ensemble(enable_dynamic_weights=False)

        assert not ensemble.enable_dynamic_weights


# ==============================================================================
# Voting Strategy Implementation Tests
# ==============================================================================


class TestWeightedAverageVoting:
    """Direct tests for _weighted_average method."""

    def test_single_prediction(self):
        """Test weighted average with single prediction."""
        manager = EnsembleManager()
        pred = ModelPredictionResult(
            model_id="m1",
            model_name="M1",
            prediction=0.5,
            confidence=0.8,
            direction="long",
            latency_ms=10,
        )

        final_pred, final_conf, direction = manager._weighted_average(
            [pred], {"m1": 1.0}
        )

        assert final_pred == 0.5
        assert final_conf == 0.8
        assert direction == "long"

    def test_multiple_predictions(self):
        """Test weighted average with multiple predictions."""
        manager = EnsembleManager()
        preds = [
            ModelPredictionResult("m1", "M1", 0.6, 0.8, "long", 10),
            ModelPredictionResult("m2", "M2", 0.4, 0.6, "long", 10),
        ]
        weights = {"m1": 0.5, "m2": 0.5}

        final_pred, final_conf, direction = manager._weighted_average(preds, weights)

        assert abs(final_pred - 0.5) < 0.01  # (0.6 + 0.4) / 2
        assert direction == "long"


class TestMajorityVote:
    """Direct tests for _majority_vote method."""

    def test_clear_majority_long(self):
        """Test clear majority for long."""
        manager = EnsembleManager()
        preds = [
            ModelPredictionResult("m1", "M1", 0.5, 0.8, "long", 10),
            ModelPredictionResult("m2", "M2", 0.5, 0.8, "long", 10),
            ModelPredictionResult("m3", "M3", -0.5, 0.8, "short", 10),
        ]

        final_pred, confidence, direction = manager._majority_vote(preds)

        assert direction == "long"
        assert confidence == 2 / 3

    def test_clear_majority_short(self):
        """Test clear majority for short."""
        manager = EnsembleManager()
        preds = [
            ModelPredictionResult("m1", "M1", -0.5, 0.8, "short", 10),
            ModelPredictionResult("m2", "M2", -0.5, 0.8, "short", 10),
            ModelPredictionResult("m3", "M3", 0.5, 0.8, "long", 10),
        ]

        final_pred, confidence, direction = manager._majority_vote(preds)

        assert direction == "short"


class TestConfidenceWeighted:
    """Direct tests for _confidence_weighted method."""

    def test_higher_confidence_has_more_weight(self):
        """Test high confidence predictions have more weight."""
        manager = EnsembleManager()
        preds = [
            ModelPredictionResult("m1", "M1", 1.0, 0.9, "long", 10),  # High conf
            ModelPredictionResult("m2", "M2", 0.0, 0.1, "neutral", 10),  # Low conf
        ]
        weights = {"m1": 0.5, "m2": 0.5}

        final_pred, final_conf, direction = manager._confidence_weighted(preds, weights)

        # Should be closer to 1.0 due to higher confidence
        assert final_pred > 0.5


class TestAgreementCalculation:
    """Direct tests for _calculate_agreement method."""

    def test_all_agree(self):
        """Test all predictions agree."""
        manager = EnsembleManager()
        preds = [
            ModelPredictionResult("m1", "M1", 0.5, 0.8, "long", 10),
            ModelPredictionResult("m2", "M2", 0.5, 0.8, "long", 10),
        ]

        agreement = manager._calculate_agreement(preds)
        assert agreement == 1.0

    def test_none_agree(self):
        """Test no predictions agree."""
        manager = EnsembleManager()
        preds = [
            ModelPredictionResult("m1", "M1", 0.5, 0.8, "long", 10),
            ModelPredictionResult("m2", "M2", -0.5, 0.8, "short", 10),
        ]

        agreement = manager._calculate_agreement(preds)
        assert agreement == 0.5  # 1/2

    def test_single_prediction(self):
        """Test single prediction always agrees."""
        manager = EnsembleManager()
        preds = [
            ModelPredictionResult("m1", "M1", 0.5, 0.8, "long", 10),
        ]

        agreement = manager._calculate_agreement(preds)
        assert agreement == 1.0


# ==============================================================================
# Integration Tests
# ==============================================================================


class TestIntegration:
    """Integration tests for ensemble workflow."""

    @pytest.mark.asyncio
    async def test_full_prediction_workflow(self, mock_model, mock_model_2):
        """Test complete prediction workflow."""
        manager = create_ensemble(
            strategy="confidence_weighted",
            min_models=1,
            enable_dynamic_weights=True,
        )

        manager.register_model(mock_model, weight=1.0)
        manager.register_model(mock_model_2, weight=0.8)

        # Make prediction
        result = await manager.predict(symbol="AAPL", features={"close": 150.0})

        assert result.model_count == 2
        assert result.agreement_score == 1.0  # Both long
        assert result.final_direction == "long"

        # Record actual
        manager.record_actual(mock_model.model_id, 0.5)

        # Check status
        status = manager.get_ensemble_status()
        assert status["healthy"]

    @pytest.mark.asyncio
    async def test_dynamic_weight_adjustment(self, mock_model, mock_model_2):
        """Test weights adjust based on performance."""
        manager = EnsembleManager(enable_dynamic_weights=True)
        manager.register_model(mock_model, weight=1.0)
        manager.register_model(mock_model_2, weight=1.0)

        # Get initial weights
        initial_weights = manager.get_effective_weights()

        # Make predictions to populate performance
        for _ in range(5):
            await manager.predict(symbol="AAPL", features={})
            manager.record_actual(mock_model.model_id, 0.5)

        # Weights should still be defined (may change slightly)
        new_weights = manager.get_effective_weights()
        assert len(new_weights) == 2

    @pytest.mark.asyncio
    async def test_graceful_degradation(self):
        """Test ensemble degrades gracefully with failing models."""
        async def sometimes_fails(*args, **kwargs):
            raise RuntimeError("Random failure")

        fail_model = MagicMock()
        fail_model.model_id = "fail"
        fail_model.model_name = "Fail"
        fail_model.predict = sometimes_fails

        good_model = MagicMock()
        good_model.model_id = "good"
        good_model.model_name = "Good"
        good_model.predict = AsyncMock(
            return_value=ModelPredictionResult(
                model_id="good",
                model_name="Good",
                prediction=0.5,
                confidence=0.8,
                direction="long",
                latency_ms=10,
            )
        )

        manager = EnsembleManager(min_models=1)
        manager.register_model(fail_model)
        manager.register_model(good_model)

        # Should still work with just the good model
        result = await manager.predict(symbol="AAPL", features={})
        assert result.model_count == 1
        assert result.individual_predictions[0].model_id == "good"

# ==============================================================================
# Additional Edge Case Tests for 100% Coverage
# ==============================================================================


class TestEnsembleManagerStackingStrategy:
    """Test stacking strategy with meta-learner."""

    @pytest.mark.asyncio
    async def test_stacking_with_meta_learner(self):
        """Test stacking strategy uses meta-learner when available."""
        manager = EnsembleManager(
            strategy=VotingStrategy.STACKING,
            min_models=1
        )
        
        # Set up a mock meta-learner
        mock_meta = MagicMock()
        mock_meta.predict = MagicMock(return_value=[0.75])
        manager._meta_learner = mock_meta
        
        # Create mock models
        model1 = MagicMock()
        model1.model_id = "model1"
        model1.model_name = "Model 1"
        model1.predict = AsyncMock(
            return_value=ModelPredictionResult(
                model_id="model1", model_name="Model 1",
                prediction=0.5, confidence=0.8, direction="long", latency_ms=10
            )
        )
        
        model2 = MagicMock()
        model2.model_id = "model2"
        model2.model_name = "Model 2"
        model2.predict = AsyncMock(
            return_value=ModelPredictionResult(
                model_id="model2", model_name="Model 2",
                prediction=0.3, confidence=0.7, direction="long", latency_ms=12
            )
        )
        
        manager.register_model(model1)
        manager.register_model(model2)
        
        result = await manager.predict(symbol="AAPL", features={})
        
        assert result is not None
        mock_meta.predict.assert_called_once()

    @pytest.mark.asyncio
    async def test_stacking_without_meta_learner_fallback(self):
        """Test stacking falls back to confidence-weighted without meta-learner."""
        manager = EnsembleManager(
            strategy=VotingStrategy.STACKING,
            min_models=1
        )
        
        # No meta-learner set (should fall back)
        model = MagicMock()
        model.model_id = "model1"
        model.model_name = "Model 1"
        model.predict = AsyncMock(
            return_value=ModelPredictionResult(
                model_id="model1", model_name="Model 1",
                prediction=0.5, confidence=0.8, direction="long", latency_ms=10
            )
        )
        
        manager.register_model(model)
        
        result = await manager.predict(symbol="AAPL", features={})
        assert result is not None


class TestEnsembleManagerMajorityVoteEdges:
    """Test majority vote edge cases."""

    @pytest.mark.asyncio
    async def test_majority_vote_neutral_wins(self):
        """Test majority vote when neutral wins."""
        manager = EnsembleManager(
            strategy=VotingStrategy.MAJORITY_VOTE,
            min_models=1
        )
        
        # Create 3 neutral models
        for i in range(3):
            model = MagicMock()
            model.model_id = f"neutral_{i}"
            model.model_name = f"Neutral {i}"
            model.predict = AsyncMock(
                return_value=ModelPredictionResult(
                    model_id=f"neutral_{i}", model_name=f"Neutral {i}",
                    prediction=0.0, confidence=0.5, direction="neutral", latency_ms=10
                )
            )
            manager.register_model(model)
        
        result = await manager.predict(symbol="AAPL", features={})
        assert result.final_direction == "neutral"

    @pytest.mark.asyncio
    async def test_majority_vote_short_wins(self):
        """Test majority vote when short wins."""
        manager = EnsembleManager(
            strategy=VotingStrategy.MAJORITY_VOTE,
            min_models=1
        )
        
        # 2 short, 1 long
        for i in range(2):
            model = MagicMock()
            model.model_id = f"short_{i}"
            model.model_name = f"Short {i}"
            model.predict = AsyncMock(
                return_value=ModelPredictionResult(
                    model_id=f"short_{i}", model_name=f"Short {i}",
                    prediction=-0.5, confidence=0.7, direction="short", latency_ms=10
                )
            )
            manager.register_model(model)
        
        long_model = MagicMock()
        long_model.model_id = "long_1"
        long_model.model_name = "Long 1"
        long_model.predict = AsyncMock(
            return_value=ModelPredictionResult(
                model_id="long_1", model_name="Long 1",
                prediction=0.5, confidence=0.7, direction="long", latency_ms=10
            )
        )
        manager.register_model(long_model)
        
        result = await manager.predict(symbol="AAPL", features={})
        assert result.final_direction == "short"


class TestEnsembleManagerConfidenceWeightedEdges:
    """Test confidence-weighted edge cases."""

    @pytest.mark.asyncio
    async def test_confidence_weighted_zero_weights(self):
        """Test confidence-weighted with zero total weight."""
        manager = EnsembleManager(
            strategy=VotingStrategy.CONFIDENCE_WEIGHTED,
            min_models=1
        )
        
        # Model with zero confidence
        model = MagicMock()
        model.model_id = "zero_conf"
        model.model_name = "Zero Conf"
        model.predict = AsyncMock(
            return_value=ModelPredictionResult(
                model_id="zero_conf", model_name="Zero Conf",
                prediction=0.5, confidence=0.0, direction="long", latency_ms=10
            )
        )
        manager.register_model(model)
        
        result = await manager.predict(symbol="AAPL", features={})
        assert result is not None


class TestEnsembleManagerAgreement:
    """Test agreement calculation."""

    @pytest.mark.asyncio
    async def test_calculate_agreement_single_prediction(self):
        """Test agreement with single prediction is 1.0."""
        manager = EnsembleManager(min_models=1)
        
        model = MagicMock()
        model.model_id = "single"
        model.model_name = "Single"
        model.predict = AsyncMock(
            return_value=ModelPredictionResult(
                model_id="single", model_name="Single",
                prediction=0.5, confidence=0.8, direction="long", latency_ms=10
            )
        )
        manager.register_model(model)
        
        result = await manager.predict(symbol="AAPL", features={})
        assert result.agreement_score == 1.0

    @pytest.mark.asyncio
    async def test_calculate_agreement_mixed_directions(self):
        """Test agreement with mixed directions."""
        manager = EnsembleManager(min_models=1)
        
        # 2 long, 1 short
        for i in range(2):
            model = MagicMock()
            model.model_id = f"long_{i}"
            model.model_name = f"Long {i}"
            model.predict = AsyncMock(
                return_value=ModelPredictionResult(
                    model_id=f"long_{i}", model_name=f"Long {i}",
                    prediction=0.5, confidence=0.8, direction="long", latency_ms=10
                )
            )
            manager.register_model(model)
        
        short = MagicMock()
        short.model_id = "short"
        short.model_name = "Short"
        short.predict = AsyncMock(
            return_value=ModelPredictionResult(
                model_id="short", model_name="Short",
                prediction=-0.5, confidence=0.8, direction="short", latency_ms=10
            )
        )
        manager.register_model(short)
        
        result = await manager.predict(symbol="AAPL", features={})
        assert 0.6 <= result.agreement_score <= 0.7  # 2/3 = 0.666
