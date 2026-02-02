"""
Multi-Model Ensemble Framework for Trading Predictions.

Provides production-ready ensemble capabilities:
- Multiple voting strategies (weighted, majority, stacking)
- Dynamic weight adjustment based on recent performance
- Confidence-weighted predictions
- Model health monitoring and automatic fallback
- Support for heterogeneous model types

This framework complements the existing EnsembleModel by providing
a more modular and configurable ensemble approach.
"""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import logging
from typing import Any, Protocol

import numpy as np

logger = logging.getLogger(__name__)


class VotingStrategy(Enum):
    """Ensemble voting strategies."""

    WEIGHTED_AVERAGE = "weighted_average"  # Weighted average of predictions
    MAJORITY_VOTE = "majority_vote"        # Majority vote for classification
    CONFIDENCE_WEIGHTED = "confidence_weighted"  # Weight by model confidence
    STACKING = "stacking"                  # Meta-learner combines predictions
    DYNAMIC = "dynamic"                    # Adaptive weights based on performance


@dataclass
class ModelPredictionResult:
    """Result from a single model prediction."""

    model_id: str
    model_name: str
    prediction: float
    confidence: float
    direction: str  # 'long', 'short', 'neutral'
    latency_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    features_used: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def signal_strength(self) -> float:
        """Compute signal strength based on confidence and direction."""
        multiplier = 1.0 if self.direction == 'long' else (-1.0 if self.direction == 'short' else 0.0)
        return self.confidence * multiplier


@dataclass
class EnsemblePredictionResult:
    """Combined result from ensemble prediction."""

    symbol: str
    final_prediction: float
    final_confidence: float
    final_direction: str
    voting_strategy: VotingStrategy
    individual_predictions: list[ModelPredictionResult]
    model_weights: dict[str, float]
    agreement_score: float  # How much models agree (0-1)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    total_latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def model_count(self) -> int:
        return len(self.individual_predictions)

    @property
    def active_models(self) -> list[str]:
        return [p.model_name for p in self.individual_predictions]


class BaseModel(Protocol):
    """Protocol for models that can be used in ensemble."""

    async def predict(self, features: dict[str, Any]) -> ModelPredictionResult:
        """Make a prediction with the model."""
        ...

    @property
    def model_id(self) -> str:
        """Unique identifier for this model."""
        ...

    @property
    def model_name(self) -> str:
        """Human-readable model name."""
        ...


@dataclass
class ModelPerformanceTracker:
    """Tracks recent performance metrics for a model."""

    model_id: str
    window_size: int = 100

    # Rolling metrics
    predictions: deque = field(default_factory=lambda: deque(maxlen=100))
    actuals: deque = field(default_factory=lambda: deque(maxlen=100))
    latencies: deque = field(default_factory=lambda: deque(maxlen=100))
    confidences: deque = field(default_factory=lambda: deque(maxlen=100))

    # Computed metrics (cached)
    _accuracy: float = 0.5
    _mae: float = 0.0
    _avg_latency_ms: float = 0.0
    _reliability_score: float = 1.0

    def __post_init__(self):
        self.predictions = deque(maxlen=self.window_size)
        self.actuals = deque(maxlen=self.window_size)
        self.latencies = deque(maxlen=self.window_size)
        self.confidences = deque(maxlen=self.window_size)

    def record_prediction(
        self,
        prediction: float,
        confidence: float,
        latency_ms: float,
    ):
        """Record a new prediction."""
        self.predictions.append(prediction)
        self.confidences.append(confidence)
        self.latencies.append(latency_ms)
        self._recalculate_metrics()

    def record_actual(self, actual: float):
        """Record actual value for latest prediction."""
        if len(self.actuals) < len(self.predictions):
            self.actuals.append(actual)
            self._recalculate_metrics()

    def _recalculate_metrics(self):
        """Recalculate performance metrics."""
        if self.latencies:
            self._avg_latency_ms = sum(self.latencies) / len(self.latencies)

        if self.actuals and self.predictions:
            n = min(len(self.actuals), len(self.predictions))
            preds = list(self.predictions)[:n]
            acts = list(self.actuals)[:n]

            # MAE
            self._mae = sum(abs(p - a) for p, a in zip(preds, acts, strict=False)) / n

            # Direction accuracy
            correct = sum(
                1 for p, a in zip(preds, acts, strict=False)
                if (p > 0 and a > 0) or (p < 0 and a < 0) or (p == 0 and a == 0)
            )
            self._accuracy = correct / n if n > 0 else 0.5

        # Reliability score based on variance of predictions
        if len(self.predictions) >= 5:
            pred_std = np.std(list(self.predictions))
            conf_mean = np.mean(list(self.confidences)) if self.confidences else 0.5
            self._reliability_score = min(1.0, conf_mean * (1 / (1 + pred_std)))

    @property
    def accuracy(self) -> float:
        return self._accuracy

    @property
    def mae(self) -> float:
        return self._mae

    @property
    def avg_latency_ms(self) -> float:
        return self._avg_latency_ms

    @property
    def reliability_score(self) -> float:
        return self._reliability_score

    @property
    def performance_score(self) -> float:
        """Combined performance score for weight calculation."""
        # Combine accuracy, reliability, and speed
        accuracy_weight = 0.5
        reliability_weight = 0.3
        speed_weight = 0.2

        # Normalize latency (faster is better, assume 100ms is baseline)
        speed_score = min(1.0, 100 / max(self._avg_latency_ms, 1))

        return (
            accuracy_weight * self._accuracy +
            reliability_weight * self._reliability_score +
            speed_weight * speed_score
        )


class EnsembleManager:
    """
    Manages a collection of models and provides ensemble predictions.

    Features:
    - Add/remove models dynamically
    - Multiple voting strategies
    - Automatic weight adjustment
    - Health monitoring
    - Graceful degradation

    Usage:
        ensemble = EnsembleManager(strategy=VotingStrategy.CONFIDENCE_WEIGHTED)
        ensemble.register_model(model1, weight=1.0)
        ensemble.register_model(model2, weight=0.8)

        result = await ensemble.predict(symbol="AAPL", features={...})
    """

    def __init__(
        self,
        strategy: VotingStrategy = VotingStrategy.CONFIDENCE_WEIGHTED,
        min_models: int = 1,
        max_latency_ms: float = 5000.0,
        enable_dynamic_weights: bool = True,
        performance_window: int = 100,
    ):
        self.strategy = strategy
        self.min_models = min_models
        self.max_latency_ms = max_latency_ms
        self.enable_dynamic_weights = enable_dynamic_weights
        self.performance_window = performance_window

        # Model registry
        self._models: dict[str, BaseModel] = {}
        self._base_weights: dict[str, float] = {}
        self._performance: dict[str, ModelPerformanceTracker] = {}
        self._enabled: dict[str, bool] = {}

        # Meta-learner for stacking (optional)
        self._meta_learner: Any = None

    def register_model(
        self,
        model: BaseModel,
        weight: float = 1.0,
        enabled: bool = True,
    ):
        """Register a model with the ensemble."""
        model_id = model.model_id

        self._models[model_id] = model
        self._base_weights[model_id] = weight
        self._enabled[model_id] = enabled
        self._performance[model_id] = ModelPerformanceTracker(
            model_id=model_id,
            window_size=self.performance_window,
        )

        logger.info(
            f"Registered model '{model.model_name}' ({model_id}) "
            f"with weight {weight}"
        )

    def unregister_model(self, model_id: str):
        """Remove a model from the ensemble."""
        if model_id in self._models:
            del self._models[model_id]
            del self._base_weights[model_id]
            del self._enabled[model_id]
            del self._performance[model_id]
            logger.info(f"Unregistered model {model_id}")

    def set_model_enabled(self, model_id: str, enabled: bool):
        """Enable or disable a model."""
        if model_id in self._enabled:
            self._enabled[model_id] = enabled
            logger.info(f"Model {model_id} {'enabled' if enabled else 'disabled'}")

    def get_effective_weights(self) -> dict[str, float]:
        """Get effective weights for all enabled models."""
        weights = {}

        for model_id, enabled in self._enabled.items():
            if not enabled:
                continue

            base_weight = self._base_weights.get(model_id, 1.0)

            if self.enable_dynamic_weights:
                # Adjust weight based on recent performance
                perf = self._performance.get(model_id)
                if perf:
                    performance_multiplier = perf.performance_score
                    weights[model_id] = base_weight * performance_multiplier
                else:
                    weights[model_id] = base_weight
            else:
                weights[model_id] = base_weight

        # Normalize weights to sum to 1
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    async def predict(
        self,
        symbol: str,
        features: dict[str, Any],
        timeout_ms: float | None = None,
    ) -> EnsemblePredictionResult:
        """
        Generate ensemble prediction from all enabled models.

        Args:
            symbol: Trading symbol
            features: Feature dict for prediction
            timeout_ms: Optional timeout override

        Returns:
            EnsemblePredictionResult with combined prediction
        """
        timeout = (timeout_ms or self.max_latency_ms) / 1000.0
        start_time = datetime.now(UTC)

        # Get enabled models
        active_models = [
            (model_id, model)
            for model_id, model in self._models.items()
            if self._enabled.get(model_id, True)
        ]

        if len(active_models) < self.min_models:
            raise ValueError(
                f"Insufficient active models: {len(active_models)} < {self.min_models}"
            )

        # Run predictions in parallel with timeout
        async def safe_predict(model_id: str, model: BaseModel) -> ModelPredictionResult | None:
            try:
                pred_start = datetime.now(UTC)
                result = await asyncio.wait_for(
                    model.predict(features),
                    timeout=timeout,
                )
                latency = (datetime.now(UTC) - pred_start).total_seconds() * 1000

                # Record performance
                self._performance[model_id].record_prediction(
                    prediction=result.prediction,
                    confidence=result.confidence,
                    latency_ms=latency,
                )

                return result

            except TimeoutError:
                logger.warning(f"Model {model_id} timed out")
                return None
            except Exception as e:
                logger.error(f"Model {model_id} prediction failed: {e}")
                return None

        # Execute all predictions
        tasks = [
            safe_predict(model_id, model)
            for model_id, model in active_models
        ]
        results = await asyncio.gather(*tasks)

        # Filter successful predictions
        predictions = [r for r in results if r is not None]

        if not predictions:
            raise RuntimeError("All models failed to produce predictions")

        # Get effective weights
        weights = self.get_effective_weights()

        # Combine predictions based on strategy
        final_prediction, final_confidence, final_direction = self._combine_predictions(
            predictions, weights
        )

        # Calculate agreement score
        agreement = self._calculate_agreement(predictions)

        total_latency = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return EnsemblePredictionResult(
            symbol=symbol,
            final_prediction=final_prediction,
            final_confidence=final_confidence,
            final_direction=final_direction,
            voting_strategy=self.strategy,
            individual_predictions=predictions,
            model_weights=weights,
            agreement_score=agreement,
            total_latency_ms=total_latency,
            metadata={
                "models_requested": len(active_models),
                "models_responded": len(predictions),
            }
        )

    def _combine_predictions(
        self,
        predictions: list[ModelPredictionResult],
        weights: dict[str, float],
    ) -> tuple[float, float, str]:
        """Combine predictions based on voting strategy."""

        if self.strategy == VotingStrategy.WEIGHTED_AVERAGE:
            return self._weighted_average(predictions, weights)

        elif self.strategy == VotingStrategy.CONFIDENCE_WEIGHTED:
            return self._confidence_weighted(predictions, weights)

        elif self.strategy == VotingStrategy.MAJORITY_VOTE:
            return self._majority_vote(predictions)

        elif self.strategy == VotingStrategy.DYNAMIC:
            # Use confidence-weighted with performance adjustment
            return self._confidence_weighted(predictions, weights)

        elif self.strategy == VotingStrategy.STACKING:
            return self._stacking(predictions)

        else:
            return self._weighted_average(predictions, weights)

    def _weighted_average(
        self,
        predictions: list[ModelPredictionResult],
        weights: dict[str, float],
    ) -> tuple[float, float, str]:
        """Simple weighted average of predictions."""
        total_weight = 0.0
        weighted_pred = 0.0
        weighted_conf = 0.0

        for pred in predictions:
            w = weights.get(pred.model_id, 1.0 / len(predictions))
            weighted_pred += pred.prediction * w
            weighted_conf += pred.confidence * w
            total_weight += w

        if total_weight > 0:
            final_pred = weighted_pred / total_weight
            final_conf = weighted_conf / total_weight
        else:
            final_pred = predictions[0].prediction if predictions else 0.0
            final_conf = 0.5

        direction = 'long' if final_pred > 0 else ('short' if final_pred < 0 else 'neutral')
        return final_pred, final_conf, direction

    def _confidence_weighted(
        self,
        predictions: list[ModelPredictionResult],
        weights: dict[str, float],
    ) -> tuple[float, float, str]:
        """Weight predictions by both base weight and confidence."""
        total_weight = 0.0
        weighted_pred = 0.0
        max_conf = 0.0

        for pred in predictions:
            base_w = weights.get(pred.model_id, 1.0 / len(predictions))
            # Combine base weight with confidence
            effective_w = base_w * pred.confidence

            weighted_pred += pred.prediction * effective_w
            total_weight += effective_w
            max_conf = max(max_conf, pred.confidence)

        if total_weight > 0:
            final_pred = weighted_pred / total_weight
        else:
            final_pred = predictions[0].prediction if predictions else 0.0

        # Final confidence is based on agreement and max confidence
        direction = 'long' if final_pred > 0 else ('short' if final_pred < 0 else 'neutral')
        return final_pred, max_conf * 0.9, direction

    def _majority_vote(
        self,
        predictions: list[ModelPredictionResult],
    ) -> tuple[float, float, str]:
        """Majority vote for direction."""
        long_votes = sum(1 for p in predictions if p.direction == 'long')
        short_votes = sum(1 for p in predictions if p.direction == 'short')
        neutral_votes = len(predictions) - long_votes - short_votes

        max_votes = max(long_votes, short_votes, neutral_votes)

        if long_votes == max_votes:
            direction = 'long'
            final_pred = sum(p.prediction for p in predictions if p.direction == 'long') / max(long_votes, 1)
        elif short_votes == max_votes:
            direction = 'short'
            final_pred = sum(p.prediction for p in predictions if p.direction == 'short') / max(short_votes, 1)
        else:
            direction = 'neutral'
            final_pred = 0.0

        confidence = max_votes / len(predictions)
        return final_pred, confidence, direction

    def _stacking(
        self,
        predictions: list[ModelPredictionResult],
    ) -> tuple[float, float, str]:
        """Use meta-learner to combine predictions."""
        if self._meta_learner is None:
            # Fall back to confidence-weighted if no meta-learner
            return self._confidence_weighted(
                predictions, self.get_effective_weights()
            )

        # Build feature vector from predictions
        features = np.array([
            [p.prediction, p.confidence]
            for p in predictions
        ]).flatten()

        # Meta-learner prediction
        final_pred = self._meta_learner.predict([features])[0]
        final_conf = 0.8  # Meta-learner confidence

        direction = 'long' if final_pred > 0 else ('short' if final_pred < 0 else 'neutral')
        return final_pred, final_conf, direction

    def _calculate_agreement(
        self,
        predictions: list[ModelPredictionResult],
    ) -> float:
        """Calculate how much models agree on direction."""
        if len(predictions) <= 1:
            return 1.0

        directions = [p.direction for p in predictions]
        most_common = max(set(directions), key=directions.count)
        agreement = directions.count(most_common) / len(directions)

        return agreement

    def record_actual(self, model_id: str, actual: float):
        """Record actual outcome for performance tracking."""
        if model_id in self._performance:
            self._performance[model_id].record_actual(actual)

    def get_model_health(self) -> dict[str, dict[str, Any]]:
        """Get health metrics for all models."""
        return {
            model_id: {
                "enabled": self._enabled.get(model_id, True),
                "base_weight": self._base_weights.get(model_id, 1.0),
                "accuracy": perf.accuracy,
                "mae": perf.mae,
                "avg_latency_ms": perf.avg_latency_ms,
                "reliability_score": perf.reliability_score,
                "performance_score": perf.performance_score,
            }
            for model_id, perf in self._performance.items()
        }

    def get_ensemble_status(self) -> dict[str, Any]:
        """Get overall ensemble status."""
        active_count = sum(1 for e in self._enabled.values() if e)
        weights = self.get_effective_weights()

        return {
            "strategy": self.strategy.value,
            "total_models": len(self._models),
            "active_models": active_count,
            "min_models_required": self.min_models,
            "healthy": active_count >= self.min_models,
            "effective_weights": weights,
            "model_health": self.get_model_health(),
        }


# Factory function for creating ensembles

def create_ensemble(
    strategy: str = "confidence_weighted",
    min_models: int = 1,
    enable_dynamic_weights: bool = True,
) -> EnsembleManager:
    """
    Create an ensemble manager with the specified strategy.

    Args:
        strategy: Voting strategy name
        min_models: Minimum models required for prediction
        enable_dynamic_weights: Whether to adjust weights based on performance

    Returns:
        Configured EnsembleManager
    """
    strategy_enum = VotingStrategy(strategy)

    return EnsembleManager(
        strategy=strategy_enum,
        min_models=min_models,
        enable_dynamic_weights=enable_dynamic_weights,
    )
