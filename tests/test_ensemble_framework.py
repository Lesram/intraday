"""
Tests for the Multi-Model Ensemble Framework.
"""

import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

from backend.ml.ensemble_framework import (
    EnsembleManager,
    VotingStrategy,
    ModelPredictionResult,
    ModelPerformanceTracker,
    create_ensemble,
)


class MockModel:
    """Mock model for testing."""
    
    def __init__(self, model_id: str, prediction: float, confidence: float, direction: str = 'long'):
        self._model_id = model_id
        self._model_name = f"Mock_{model_id}"
        self._prediction = prediction
        self._confidence = confidence
        self._direction = direction
    
    @property
    def model_id(self) -> str:
        return self._model_id
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    async def predict(self, features: dict) -> ModelPredictionResult:
        return ModelPredictionResult(
            model_id=self._model_id,
            model_name=self._model_name,
            prediction=self._prediction,
            confidence=self._confidence,
            direction=self._direction,
            latency_ms=10.0,
        )


class TestModelPerformanceTracker:
    """Tests for performance tracking."""

    def test_initial_state(self):
        """Test initial tracker state."""
        tracker = ModelPerformanceTracker(model_id="test")
        
        assert tracker.accuracy == 0.5
        assert tracker.avg_latency_ms == 0.0
        assert tracker.reliability_score == 1.0

    def test_record_prediction(self):
        """Test recording predictions."""
        tracker = ModelPerformanceTracker(model_id="test")
        
        tracker.record_prediction(
            prediction=1.5,
            confidence=0.8,
            latency_ms=50.0,
        )
        
        assert tracker.avg_latency_ms == 50.0
        assert len(tracker.predictions) == 1

    def test_performance_score(self):
        """Test combined performance score."""
        tracker = ModelPerformanceTracker(model_id="test")
        
        # Record some predictions
        for i in range(10):
            tracker.record_prediction(
                prediction=1.0 + i * 0.1,
                confidence=0.8,
                latency_ms=50.0,
            )
        
        score = tracker.performance_score
        assert 0 <= score <= 1


class TestEnsembleManager:
    """Tests for EnsembleManager."""

    @pytest.fixture
    def ensemble(self):
        """Create test ensemble."""
        return EnsembleManager(strategy=VotingStrategy.WEIGHTED_AVERAGE)

    @pytest.fixture
    def mock_models(self):
        """Create mock models."""
        return [
            MockModel("model1", prediction=1.5, confidence=0.8, direction='long'),
            MockModel("model2", prediction=1.3, confidence=0.7, direction='long'),
            MockModel("model3", prediction=-0.5, confidence=0.6, direction='short'),
        ]

    def test_register_model(self, ensemble, mock_models):
        """Test model registration."""
        ensemble.register_model(mock_models[0], weight=1.0)
        
        assert "model1" in ensemble._models
        assert ensemble._base_weights["model1"] == 1.0
        assert ensemble._enabled["model1"] is True

    def test_unregister_model(self, ensemble, mock_models):
        """Test model removal."""
        ensemble.register_model(mock_models[0])
        ensemble.unregister_model("model1")
        
        assert "model1" not in ensemble._models

    def test_set_model_enabled(self, ensemble, mock_models):
        """Test enabling/disabling models."""
        ensemble.register_model(mock_models[0])
        
        ensemble.set_model_enabled("model1", False)
        assert ensemble._enabled["model1"] is False
        
        ensemble.set_model_enabled("model1", True)
        assert ensemble._enabled["model1"] is True

    def test_get_effective_weights(self, ensemble, mock_models):
        """Test weight calculation."""
        ensemble.register_model(mock_models[0], weight=2.0)
        ensemble.register_model(mock_models[1], weight=1.0)
        
        weights = ensemble.get_effective_weights()
        
        # Weights should be normalized
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_predict_weighted_average(self, mock_models):
        """Test weighted average prediction."""
        ensemble = EnsembleManager(strategy=VotingStrategy.WEIGHTED_AVERAGE)
        
        for model in mock_models[:2]:
            ensemble.register_model(model, weight=1.0)
        
        result = await ensemble.predict(symbol="AAPL", features={})
        
        assert result.symbol == "AAPL"
        assert result.model_count == 2
        assert result.voting_strategy == VotingStrategy.WEIGHTED_AVERAGE
        # Average of 1.5 and 1.3 = 1.4
        assert abs(result.final_prediction - 1.4) < 0.1

    @pytest.mark.asyncio
    async def test_predict_confidence_weighted(self, mock_models):
        """Test confidence-weighted prediction."""
        ensemble = EnsembleManager(strategy=VotingStrategy.CONFIDENCE_WEIGHTED)
        
        for model in mock_models[:2]:
            ensemble.register_model(model, weight=1.0)
        
        result = await ensemble.predict(symbol="AAPL", features={})
        
        assert result.voting_strategy == VotingStrategy.CONFIDENCE_WEIGHTED
        # Higher confidence model should have more influence
        assert result.final_prediction > 0

    @pytest.mark.asyncio
    async def test_predict_majority_vote(self, mock_models):
        """Test majority vote prediction."""
        ensemble = EnsembleManager(strategy=VotingStrategy.MAJORITY_VOTE)
        
        for model in mock_models:
            ensemble.register_model(model, weight=1.0)
        
        result = await ensemble.predict(symbol="AAPL", features={})
        
        assert result.voting_strategy == VotingStrategy.MAJORITY_VOTE
        # 2 long, 1 short -> should be long
        assert result.final_direction == 'long'

    @pytest.mark.asyncio
    async def test_agreement_score(self, mock_models):
        """Test model agreement calculation."""
        ensemble = EnsembleManager(strategy=VotingStrategy.WEIGHTED_AVERAGE)
        
        for model in mock_models:
            ensemble.register_model(model, weight=1.0)
        
        result = await ensemble.predict(symbol="AAPL", features={})
        
        # 2/3 agreement
        assert abs(result.agreement_score - 0.666) < 0.1

    @pytest.mark.asyncio
    async def test_insufficient_models(self):
        """Test error when not enough models."""
        ensemble = EnsembleManager(min_models=3)
        ensemble.register_model(MockModel("model1", 1.0, 0.8))
        
        with pytest.raises(ValueError, match="Insufficient active models"):
            await ensemble.predict(symbol="AAPL", features={})

    def test_model_health(self, ensemble, mock_models):
        """Test model health reporting."""
        for model in mock_models:
            ensemble.register_model(model, weight=1.0)
        
        health = ensemble.get_model_health()
        
        assert len(health) == 3
        assert "model1" in health
        assert "accuracy" in health["model1"]

    def test_ensemble_status(self, ensemble, mock_models):
        """Test ensemble status reporting."""
        for model in mock_models:
            ensemble.register_model(model, weight=1.0)
        
        status = ensemble.get_ensemble_status()
        
        assert status["total_models"] == 3
        assert status["active_models"] == 3
        assert status["healthy"] is True


class TestCreateEnsemble:
    """Tests for ensemble factory function."""

    def test_create_weighted_average(self):
        """Test creating weighted average ensemble."""
        ensemble = create_ensemble(strategy="weighted_average")
        
        assert ensemble.strategy == VotingStrategy.WEIGHTED_AVERAGE

    def test_create_confidence_weighted(self):
        """Test creating confidence-weighted ensemble."""
        ensemble = create_ensemble(strategy="confidence_weighted")
        
        assert ensemble.strategy == VotingStrategy.CONFIDENCE_WEIGHTED

    def test_create_with_options(self):
        """Test creating ensemble with custom options."""
        ensemble = create_ensemble(
            strategy="majority_vote",
            min_models=2,
            enable_dynamic_weights=False,
        )
        
        assert ensemble.strategy == VotingStrategy.MAJORITY_VOTE
        assert ensemble.min_models == 2
        assert ensemble.enable_dynamic_weights is False
