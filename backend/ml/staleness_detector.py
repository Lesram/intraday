"""
Model Staleness Detection (M-47)

Detects when ML models need retraining based on:
- Time since last training
- Performance degradation
- Feature drift
- Prediction distribution shifts
- Market regime changes

Extends the existing drift.py and monitoring.py with staleness-specific detection.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
import logging

import numpy as np
import pandas as pd

from .drift import compute_drift, build_drift_baseline, DriftResult
from .monitoring import RetrainDecision, decide_retrain

logger = logging.getLogger(__name__)


class StalenessReason(Enum):
    """Reasons why a model may be stale."""
    AGE = "age"                           # Model is too old
    PERFORMANCE_DECAY = "performance_decay"  # Performance has degraded
    FEATURE_DRIFT = "feature_drift"        # Input features have drifted
    PREDICTION_DRIFT = "prediction_drift"  # Prediction distribution changed
    REGIME_CHANGE = "regime_change"        # Market regime has changed
    LOW_CONFIDENCE = "low_confidence"      # Model confidence degraded
    MANUAL = "manual"                      # Manual retraining triggered


class StalenessLevel(Enum):
    """Level of model staleness."""
    FRESH = "fresh"           # Model is recently trained and performing well
    AGING = "aging"           # Model is getting older, monitoring needed
    STALE = "stale"           # Model should be retrained soon
    CRITICAL = "critical"     # Model must be retrained immediately


@dataclass
class StalenessMetrics:
    """Comprehensive model staleness metrics."""
    # Time-based
    model_age_days: int
    days_since_validation: int
    max_age_days: int
    
    # Performance-based
    current_accuracy: float
    baseline_accuracy: float
    accuracy_decay_pct: float
    
    current_sharpe: float
    baseline_sharpe: float
    sharpe_decay_pct: float
    
    # Drift-based
    feature_drift_psi: float
    prediction_drift_psi: float
    drift_threshold: float
    
    # Confidence-based
    avg_confidence: float
    confidence_std: float
    low_confidence_pct: float  # % predictions below threshold
    
    # Regime-based
    current_regime: str
    training_regime: str
    regime_match: bool
    
    # Overall
    staleness_score: float  # 0-1, higher is more stale
    staleness_level: StalenessLevel
    reasons: list[StalenessReason]
    
    # Recommendations
    should_retrain: bool
    urgency: str  # "low", "medium", "high", "critical"
    recommended_action: str


@dataclass
class ModelPerformanceRecord:
    """Record of model performance at a point in time."""
    timestamp: datetime
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    sharpe_ratio: float
    predictions_count: int
    avg_confidence: float


class ModelStalenessDetector:
    """
    Detects model staleness and recommends retraining.
    
    Monitors multiple signals:
    1. Model age (time since training)
    2. Performance decay (accuracy, Sharpe degradation)
    3. Feature drift (PSI on input features)
    4. Prediction drift (distribution of outputs)
    5. Regime detection (market conditions vs training period)
    
    Usage:
        detector = ModelStalenessDetector(
            max_age_days=90,
            accuracy_decay_threshold=0.10,
            drift_threshold=0.15,
        )
        
        # Register baseline
        detector.set_baseline(
            model_id="model_v1",
            trained_at=datetime(2026, 1, 1),
            baseline_accuracy=0.65,
            baseline_sharpe=1.5,
            feature_baseline=drift_baseline,
        )
        
        # Check staleness
        metrics = detector.check_staleness(
            model_id="model_v1",
            current_features=X_recent,
            current_predictions=y_pred,
            current_performance=perf_dict,
        )
    """
    
    def __init__(
        self,
        max_age_days: int = 90,
        validation_frequency_days: int = 7,
        accuracy_decay_threshold: float = 0.10,
        sharpe_decay_threshold: float = 0.30,
        drift_threshold: float = 0.15,
        confidence_threshold: float = 0.6,
        low_confidence_max_pct: float = 0.30,
    ):
        """
        Initialize staleness detector.
        
        Args:
            max_age_days: Maximum model age before considered stale
            validation_frequency_days: How often to validate model
            accuracy_decay_threshold: Max accuracy drop before stale
            sharpe_decay_threshold: Max Sharpe drop before stale
            drift_threshold: PSI threshold for drift detection
            confidence_threshold: Confidence level below which is "low"
            low_confidence_max_pct: Max % of low-confidence predictions
        """
        self.max_age_days = max_age_days
        self.validation_frequency_days = validation_frequency_days
        self.accuracy_decay_threshold = accuracy_decay_threshold
        self.sharpe_decay_threshold = sharpe_decay_threshold
        self.drift_threshold = drift_threshold
        self.confidence_threshold = confidence_threshold
        self.low_confidence_max_pct = low_confidence_max_pct
        
        # Model baselines
        self._baselines: dict[str, dict[str, Any]] = {}
        
        # Performance history
        self._performance_history: dict[str, list[ModelPerformanceRecord]] = {}
        
        # Last validation times
        self._last_validated: dict[str, datetime] = {}
        
        # Prediction history for drift
        self._prediction_history: dict[str, list[float]] = {}
        self._baseline_predictions: dict[str, list[float]] = {}
    
    def set_baseline(
        self,
        model_id: str,
        trained_at: datetime,
        baseline_accuracy: float,
        baseline_sharpe: float,
        baseline_precision: float = 0.0,
        baseline_recall: float = 0.0,
        feature_baseline: dict[str, Any] | None = None,
        training_regime: str = "unknown",
        prediction_baseline: list[float] | None = None,
    ) -> None:
        """
        Set baseline metrics for a model.
        
        Args:
            model_id: Model identifier
            trained_at: When model was trained
            baseline_accuracy: Accuracy at training time
            baseline_sharpe: Sharpe ratio at training time
            baseline_precision: Precision at training time
            baseline_recall: Recall at training time
            feature_baseline: Feature drift baseline (from build_drift_baseline)
            training_regime: Market regime during training
            prediction_baseline: Baseline prediction distribution
        """
        self._baselines[model_id] = {
            "trained_at": trained_at,
            "accuracy": baseline_accuracy,
            "sharpe": baseline_sharpe,
            "precision": baseline_precision,
            "recall": baseline_recall,
            "feature_baseline": feature_baseline,
            "training_regime": training_regime,
        }
        
        if prediction_baseline:
            self._baseline_predictions[model_id] = prediction_baseline
        
        self._last_validated[model_id] = trained_at
        
        logger.info(
            f"Set baseline for model {model_id}",
            extra={
                "trained_at": trained_at.isoformat(),
                "accuracy": baseline_accuracy,
                "sharpe": baseline_sharpe,
            }
        )
    
    def record_performance(
        self,
        model_id: str,
        accuracy: float,
        sharpe_ratio: float,
        precision: float = 0.0,
        recall: float = 0.0,
        predictions_count: int = 0,
        avg_confidence: float = 0.0,
    ) -> None:
        """Record current model performance."""
        if model_id not in self._performance_history:
            self._performance_history[model_id] = []
        
        record = ModelPerformanceRecord(
            timestamp=datetime.now(UTC),
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0,
            sharpe_ratio=sharpe_ratio,
            predictions_count=predictions_count,
            avg_confidence=avg_confidence,
        )
        
        self._performance_history[model_id].append(record)
        
        # Keep last 100 records
        if len(self._performance_history[model_id]) > 100:
            self._performance_history[model_id] = self._performance_history[model_id][-100:]
    
    def record_predictions(
        self,
        model_id: str,
        predictions: list[float] | np.ndarray,
        confidences: list[float] | np.ndarray | None = None,
    ) -> None:
        """Record predictions for drift detection."""
        if model_id not in self._prediction_history:
            self._prediction_history[model_id] = []
        
        preds = list(predictions) if isinstance(predictions, np.ndarray) else predictions
        self._prediction_history[model_id].extend(preds)
        
        # Keep last 10000 predictions
        if len(self._prediction_history[model_id]) > 10000:
            self._prediction_history[model_id] = self._prediction_history[model_id][-10000:]
    
    def check_staleness(
        self,
        model_id: str,
        current_features: pd.DataFrame | None = None,
        current_predictions: list[float] | None = None,
        current_performance: dict[str, float] | None = None,
        current_regime: str = "unknown",
        current_confidences: list[float] | None = None,
    ) -> StalenessMetrics:
        """
        Check model staleness across all dimensions.
        
        Args:
            model_id: Model to check
            current_features: Recent feature data for drift detection
            current_predictions: Recent predictions
            current_performance: Current performance metrics dict
            current_regime: Current market regime
            current_confidences: Confidence scores for recent predictions
            
        Returns:
            StalenessMetrics with comprehensive analysis
        """
        now = datetime.now(UTC)
        reasons: list[StalenessReason] = []
        
        baseline = self._baselines.get(model_id, {})
        if not baseline:
            logger.warning(f"No baseline found for model {model_id}")
            return self._create_unknown_metrics(model_id)
        
        trained_at = baseline.get("trained_at", now)
        model_age_days = (now - trained_at).days
        
        last_validated = self._last_validated.get(model_id, trained_at)
        days_since_validation = (now - last_validated).days
        
        # 1. Check age
        age_staleness = min(1.0, model_age_days / self.max_age_days)
        if model_age_days >= self.max_age_days:
            reasons.append(StalenessReason.AGE)
        
        # 2. Check performance decay
        current_perf = current_performance or {}
        current_accuracy = current_perf.get("accuracy", baseline.get("accuracy", 0.5))
        current_sharpe = current_perf.get("sharpe_ratio", baseline.get("sharpe", 0.0))
        
        baseline_accuracy = baseline.get("accuracy", current_accuracy)
        baseline_sharpe = baseline.get("sharpe", current_sharpe)
        
        accuracy_decay = (baseline_accuracy - current_accuracy) / baseline_accuracy if baseline_accuracy > 0 else 0
        sharpe_decay = (baseline_sharpe - current_sharpe) / abs(baseline_sharpe) if baseline_sharpe != 0 else 0
        
        performance_staleness = (accuracy_decay + sharpe_decay) / 2
        
        if accuracy_decay >= self.accuracy_decay_threshold:
            reasons.append(StalenessReason.PERFORMANCE_DECAY)
        if sharpe_decay >= self.sharpe_decay_threshold:
            reasons.append(StalenessReason.PERFORMANCE_DECAY)
        
        # 3. Check feature drift
        feature_drift_psi = 0.0
        if current_features is not None and baseline.get("feature_baseline"):
            drift_result = compute_drift(
                baseline["feature_baseline"],
                current_features,
            )
            feature_drift_psi = drift_result.psi_score
            
            if feature_drift_psi >= self.drift_threshold:
                reasons.append(StalenessReason.FEATURE_DRIFT)
        
        # 4. Check prediction drift
        prediction_drift_psi = 0.0
        if current_predictions and model_id in self._baseline_predictions:
            prediction_drift_psi = self._calculate_prediction_drift(
                model_id, current_predictions
            )
            if prediction_drift_psi >= self.drift_threshold:
                reasons.append(StalenessReason.PREDICTION_DRIFT)
        
        # 5. Check regime
        training_regime = baseline.get("training_regime", "unknown")
        regime_match = current_regime == training_regime
        if not regime_match:
            reasons.append(StalenessReason.REGIME_CHANGE)
        
        # 6. Check confidence
        avg_confidence = 0.7
        confidence_std = 0.1
        low_confidence_pct = 0.0
        
        if current_confidences:
            conf_array = np.array(current_confidences)
            avg_confidence = float(np.mean(conf_array))
            confidence_std = float(np.std(conf_array))
            low_confidence_pct = float(np.mean(conf_array < self.confidence_threshold))
            
            if low_confidence_pct > self.low_confidence_max_pct:
                reasons.append(StalenessReason.LOW_CONFIDENCE)
        
        # Calculate overall staleness score
        drift_staleness = max(feature_drift_psi, prediction_drift_psi) / self.drift_threshold
        regime_staleness = 0.5 if not regime_match else 0.0
        confidence_staleness = low_confidence_pct / self.low_confidence_max_pct if self.low_confidence_max_pct > 0 else 0
        
        staleness_score = min(1.0, (
            0.25 * age_staleness +
            0.30 * max(0, performance_staleness) +
            0.25 * min(1.0, drift_staleness) +
            0.10 * regime_staleness +
            0.10 * min(1.0, confidence_staleness)
        ))
        
        # Determine level
        if staleness_score < 0.25:
            staleness_level = StalenessLevel.FRESH
            urgency = "low"
        elif staleness_score < 0.50:
            staleness_level = StalenessLevel.AGING
            urgency = "low"
        elif staleness_score < 0.75:
            staleness_level = StalenessLevel.STALE
            urgency = "medium"
        else:
            staleness_level = StalenessLevel.CRITICAL
            urgency = "high"
        
        # Make unique
        reasons = list(set(reasons))
        
        # Determine if retraining is needed
        should_retrain = (
            staleness_level in [StalenessLevel.STALE, StalenessLevel.CRITICAL] or
            len(reasons) >= 2
        )
        
        if staleness_level == StalenessLevel.CRITICAL:
            urgency = "critical"
        
        # Generate recommendation
        recommended_action = self._generate_recommendation(
            staleness_level, reasons, model_age_days
        )
        
        # Update validation time
        self._last_validated[model_id] = now
        
        metrics = StalenessMetrics(
            model_age_days=model_age_days,
            days_since_validation=days_since_validation,
            max_age_days=self.max_age_days,
            current_accuracy=current_accuracy,
            baseline_accuracy=baseline_accuracy,
            accuracy_decay_pct=accuracy_decay * 100,
            current_sharpe=current_sharpe,
            baseline_sharpe=baseline_sharpe,
            sharpe_decay_pct=sharpe_decay * 100,
            feature_drift_psi=feature_drift_psi,
            prediction_drift_psi=prediction_drift_psi,
            drift_threshold=self.drift_threshold,
            avg_confidence=avg_confidence,
            confidence_std=confidence_std,
            low_confidence_pct=low_confidence_pct * 100,
            current_regime=current_regime,
            training_regime=training_regime,
            regime_match=regime_match,
            staleness_score=staleness_score,
            staleness_level=staleness_level,
            reasons=reasons,
            should_retrain=should_retrain,
            urgency=urgency,
            recommended_action=recommended_action,
        )
        
        logger.info(
            f"Staleness check for model {model_id}",
            extra={
                "staleness_score": f"{staleness_score:.2f}",
                "staleness_level": staleness_level.value,
                "should_retrain": should_retrain,
                "reasons": [r.value for r in reasons],
            }
        )
        
        return metrics
    
    def _calculate_prediction_drift(
        self,
        model_id: str,
        current_predictions: list[float],
    ) -> float:
        """Calculate prediction distribution drift using PSI."""
        baseline_preds = self._baseline_predictions.get(model_id, [])
        if not baseline_preds or len(current_predictions) < 100:
            return 0.0
        
        try:
            # Create bins from baseline
            baseline_array = np.array(baseline_preds)
            current_array = np.array(current_predictions)
            
            # Use quantile-based bins
            n_bins = 10
            edges = np.percentile(baseline_array, np.linspace(0, 100, n_bins + 1))
            edges[0] = -np.inf
            edges[-1] = np.inf
            
            # Calculate proportions
            baseline_counts, _ = np.histogram(baseline_array, bins=edges)
            current_counts, _ = np.histogram(current_array, bins=edges)
            
            eps = 1e-6
            baseline_props = (baseline_counts + eps) / (baseline_counts.sum() + eps * n_bins)
            current_props = (current_counts + eps) / (current_counts.sum() + eps * n_bins)
            
            # PSI
            psi = float(np.sum((current_props - baseline_props) * np.log(current_props / baseline_props)))
            
            return max(0.0, psi)
            
        except Exception as e:
            logger.warning(f"Failed to calculate prediction drift: {e}")
            return 0.0
    
    def _generate_recommendation(
        self,
        level: StalenessLevel,
        reasons: list[StalenessReason],
        age_days: int,
    ) -> str:
        """Generate actionable recommendation."""
        if level == StalenessLevel.FRESH:
            return "Model is performing well. Continue monitoring."
        
        if level == StalenessLevel.AGING:
            return f"Model is {age_days} days old. Schedule validation and prepare retraining data."
        
        if level == StalenessLevel.STALE:
            reason_str = ", ".join(r.value for r in reasons)
            return f"Model should be retrained due to: {reason_str}. Initiate retraining pipeline."
        
        # CRITICAL
        return "CRITICAL: Model requires immediate retraining. Consider fallback to simpler model."
    
    def _create_unknown_metrics(self, model_id: str) -> StalenessMetrics:
        """Create metrics when baseline is unknown."""
        return StalenessMetrics(
            model_age_days=0,
            days_since_validation=0,
            max_age_days=self.max_age_days,
            current_accuracy=0.0,
            baseline_accuracy=0.0,
            accuracy_decay_pct=0.0,
            current_sharpe=0.0,
            baseline_sharpe=0.0,
            sharpe_decay_pct=0.0,
            feature_drift_psi=0.0,
            prediction_drift_psi=0.0,
            drift_threshold=self.drift_threshold,
            avg_confidence=0.0,
            confidence_std=0.0,
            low_confidence_pct=0.0,
            current_regime="unknown",
            training_regime="unknown",
            regime_match=False,
            staleness_score=1.0,
            staleness_level=StalenessLevel.CRITICAL,
            reasons=[StalenessReason.MANUAL],
            should_retrain=True,
            urgency="critical",
            recommended_action=f"No baseline found for model {model_id}. Set baseline or retrain.",
        )
    
    def get_performance_trend(
        self,
        model_id: str,
        metric: str = "accuracy",
        window: int = 10,
    ) -> dict[str, Any]:
        """Get performance trend for a model."""
        history = self._performance_history.get(model_id, [])
        
        if len(history) < 2:
            return {"trend": "unknown", "change": 0.0, "data_points": len(history)}
        
        # Get metric values
        values = []
        for record in history[-window:]:
            val = getattr(record, metric, None)
            if val is not None:
                values.append(val)
        
        if len(values) < 2:
            return {"trend": "unknown", "change": 0.0, "data_points": len(values)}
        
        # Calculate trend
        start_val = np.mean(values[:len(values)//2])
        end_val = np.mean(values[len(values)//2:])
        change = (end_val - start_val) / start_val if start_val != 0 else 0
        
        if change > 0.05:
            trend = "improving"
        elif change < -0.05:
            trend = "degrading"
        else:
            trend = "stable"
        
        return {
            "trend": trend,
            "change": change,
            "data_points": len(values),
            "start_value": start_val,
            "end_value": end_val,
        }
    
    def to_dict(self, metrics: StalenessMetrics) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "model_age_days": metrics.model_age_days,
            "days_since_validation": metrics.days_since_validation,
            "max_age_days": metrics.max_age_days,
            "current_accuracy": metrics.current_accuracy,
            "baseline_accuracy": metrics.baseline_accuracy,
            "accuracy_decay_pct": metrics.accuracy_decay_pct,
            "current_sharpe": metrics.current_sharpe,
            "baseline_sharpe": metrics.baseline_sharpe,
            "sharpe_decay_pct": metrics.sharpe_decay_pct,
            "feature_drift_psi": metrics.feature_drift_psi,
            "prediction_drift_psi": metrics.prediction_drift_psi,
            "drift_threshold": metrics.drift_threshold,
            "avg_confidence": metrics.avg_confidence,
            "confidence_std": metrics.confidence_std,
            "low_confidence_pct": metrics.low_confidence_pct,
            "current_regime": metrics.current_regime,
            "training_regime": metrics.training_regime,
            "regime_match": metrics.regime_match,
            "staleness_score": metrics.staleness_score,
            "staleness_level": metrics.staleness_level.value,
            "reasons": [r.value for r in metrics.reasons],
            "should_retrain": metrics.should_retrain,
            "urgency": metrics.urgency,
            "recommended_action": metrics.recommended_action,
        }


# Singleton instance
_detector: ModelStalenessDetector | None = None


def get_staleness_detector() -> ModelStalenessDetector:
    """Get or create the model staleness detector singleton."""
    global _detector
    if _detector is None:
        _detector = ModelStalenessDetector()
    return _detector
