"""
MLOps Model Management System
Handles model versioning, deployment, monitoring, and automated retraining
"""

import asyncio
import hashlib
import json
import logging
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..config import get_settings
from ..models.ensemble_model import EnsembleModel, ModelPerformance
from ..utils.logger import audit_logger, performance_logger


class ModelStatus(Enum):
    """Model lifecycle status"""

    TRAINING = "training"
    TRAINED = "trained"
    DEPLOYED = "deployed"
    CHAMPION = "champion"
    CHALLENGER = "challenger"
    DEPRECATED = "deprecated"
    FAILED = "failed"


class DriftType(Enum):
    """Types of model drift"""

    DATA_DRIFT = "data_drift"
    CONCEPT_DRIFT = "concept_drift"
    PERFORMANCE_DRIFT = "performance_drift"


@dataclass
class ModelVersion:
    """Model version metadata"""

    model_id: str
    version: str
    created_at: datetime
    status: ModelStatus
    metrics: Dict[str, float]
    training_data_hash: str
    feature_names: List[str]
    model_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DriftDetection:
    """Drift detection result"""

    drift_type: DriftType
    severity: float  # 0-1 scale
    detected_at: datetime
    affected_features: List[str]
    recommendation: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelMonitoring:
    """Model monitoring metrics"""

    model_id: str
    timestamp: datetime
    prediction_count: int
    avg_confidence: float
    accuracy: float
    latency_ms: float
    error_rate: float
    drift_score: float


class ModelRegistry:
    """Manages model versions and metadata"""

    def __init__(self, base_path: str = "./models"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)
        self.registry_file = self.base_path / "model_registry.json"
        self.models: Dict[str, List[ModelVersion]] = {}
        self.load_registry()

    def load_registry(self):
        """Load model registry from disk"""
        try:
            if self.registry_file.exists():
                with open(self.registry_file, "r") as f:
                    data = json.load(f)

                # Reconstruct ModelVersion objects
                for model_id, versions in data.items():
                    self.models[model_id] = [
                        ModelVersion(
                            model_id=v["model_id"],
                            version=v["version"],
                            created_at=datetime.fromisoformat(v["created_at"]),
                            status=ModelStatus(v["status"]),
                            metrics=v["metrics"],
                            training_data_hash=v["training_data_hash"],
                            feature_names=v["feature_names"],
                            model_path=v.get("model_path"),
                            metadata=v.get("metadata", {}),
                        )
                        for v in versions
                    ]
        except Exception as e:
            logging.error(f"Error loading model registry: {e}")
            self.models = {}

    def save_registry(self):
        """Save model registry to disk"""
        try:
            # Convert to serializable format
            data = {}
            for model_id, versions in self.models.items():
                data[model_id] = [
                    {
                        "model_id": v.model_id,
                        "version": v.version,
                        "created_at": v.created_at.isoformat(),
                        "status": v.status.value,
                        "metrics": v.metrics,
                        "training_data_hash": v.training_data_hash,
                        "feature_names": v.feature_names,
                        "model_path": v.model_path,
                        "metadata": v.metadata,
                    }
                    for v in versions
                ]

            with open(self.registry_file, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logging.error(f"Error saving model registry: {e}")

    def register_model(
        self,
        model_id: str,
        model: EnsembleModel,
        training_data: pd.DataFrame,
        metrics: Dict[str, float],
    ) -> ModelVersion:
        """Register a new model version"""

        # Generate version
        if model_id not in self.models:
            self.models[model_id] = []
        version = f"v{len(self.models[model_id]) + 1}"

        # Calculate training data hash
        data_hash = hashlib.md5(
            pd.util.hash_pandas_object(training_data).values
        ).hexdigest()

        # Save model to disk
        model_path = self.base_path / model_id / version
        model_path.mkdir(parents=True, exist_ok=True)

        # Serialize model (simplified approach)
        model_file = model_path / "ensemble_model.pkl"
        try:
            with open(model_file, "wb") as f:
                pickle.dump(model, f)
        except Exception as e:
            logging.error(f"Error saving model to disk: {e}")
            model_file = None

        # Create model version
        model_version = ModelVersion(
            model_id=model_id,
            version=version,
            created_at=datetime.now(),
            status=ModelStatus.TRAINED,
            metrics=metrics,
            training_data_hash=data_hash,
            feature_names=list(training_data.columns),
            model_path=str(model_file) if model_file else None,
            metadata={
                "training_samples": len(training_data),
                "features_count": len(training_data.columns),
            },
        )

        self.models[model_id].append(model_version)
        self.save_registry()

        audit_logger.info(
            "model_registered",
            model_id=model_id,
            version=version,
            metrics=metrics,
            training_samples=len(training_data),
        )

        return model_version

    def get_champion_model(self, model_id: str) -> Optional[ModelVersion]:
        """Get current champion model"""
        if model_id not in self.models:
            return None

        champions = [
            v for v in self.models[model_id] if v.status == ModelStatus.CHAMPION
        ]
        return champions[-1] if champions else None

    def promote_to_champion(self, model_id: str, version: str) -> bool:
        """Promote model version to champion"""
        if model_id not in self.models:
            return False

        # Demote current champion
        for model_version in self.models[model_id]:
            if model_version.status == ModelStatus.CHAMPION:
                model_version.status = ModelStatus.DEPLOYED

        # Promote new champion
        for model_version in self.models[model_id]:
            if model_version.version == version:
                model_version.status = ModelStatus.CHAMPION
                self.save_registry()

                audit_logger.info(
                    "model_promoted_to_champion", model_id=model_id, version=version
                )
                return True

        return False

    def get_model_versions(self, model_id: str) -> List[ModelVersion]:
        """Get all versions of a model"""
        return self.models.get(model_id, [])


class DriftDetector:
    """Detects various types of model drift"""

    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.reference_data = {}  # model_id -> reference statistics
        self.monitoring_data = {}  # model_id -> recent data

    def set_reference_data(self, model_id: str, data: pd.DataFrame):
        """Set reference data for drift detection"""
        self.reference_data[model_id] = {
            "mean": data.mean().to_dict(),
            "std": data.std().to_dict(),
            "correlations": data.corr().to_dict(),
            "feature_names": list(data.columns),
        }

    def detect_data_drift(
        self, model_id: str, current_data: pd.DataFrame
    ) -> Optional[DriftDetection]:
        """Detect data drift using statistical tests"""

        if model_id not in self.reference_data:
            return None

        reference = self.reference_data[model_id]
        drift_scores = {}
        affected_features = []

        for feature in reference["feature_names"]:
            if feature not in current_data.columns:
                continue

            ref_mean = reference["mean"][feature]
            ref_std = reference["std"][feature]

            curr_mean = current_data[feature].mean()
            curr_std = current_data[feature].std()

            # Calculate drift score using normalized difference
            mean_drift = abs(curr_mean - ref_mean) / (ref_std + 1e-8)
            std_drift = abs(curr_std - ref_std) / (ref_std + 1e-8)

            drift_score = (mean_drift + std_drift) / 2
            drift_scores[feature] = drift_score

            if drift_score > 2.0:  # Threshold for significant drift
                affected_features.append(feature)

        # Overall drift severity
        avg_drift = np.mean(list(drift_scores.values()))

        if avg_drift > 1.5:  # Overall drift threshold
            return DriftDetection(
                drift_type=DriftType.DATA_DRIFT,
                severity=min(1.0, avg_drift / 3.0),
                detected_at=datetime.now(),
                affected_features=affected_features,
                recommendation="Consider retraining model with recent data",
                details={
                    "feature_drift_scores": drift_scores,
                    "avg_drift_score": avg_drift,
                },
            )

        return None

    def detect_performance_drift(
        self,
        model_id: str,
        recent_predictions: List[Tuple[float, float]],  # (prediction, actual)
        baseline_metrics: Dict[str, float],
    ) -> Optional[DriftDetection]:
        """Detect performance drift"""

        if len(recent_predictions) < 100:  # Need enough samples
            return None

        predictions, actuals = zip(*recent_predictions)

        # Calculate current performance
        mse = np.mean([(p - a) ** 2 for p, a in recent_predictions])
        mae = np.mean([abs(p - a) for p, a in recent_predictions])

        # Compare with baseline
        baseline_mse = baseline_metrics.get("mse", mse)
        baseline_mae = baseline_metrics.get("mae", mae)

        mse_degradation = (mse - baseline_mse) / (baseline_mse + 1e-8)
        mae_degradation = (mae - baseline_mae) / (baseline_mae + 1e-8)

        avg_degradation = (mse_degradation + mae_degradation) / 2

        if avg_degradation > 0.2:  # 20% performance degradation
            return DriftDetection(
                drift_type=DriftType.PERFORMANCE_DRIFT,
                severity=min(1.0, avg_degradation),
                detected_at=datetime.now(),
                affected_features=[],
                recommendation="Model performance has degraded significantly. Immediate retraining recommended.",
                details={
                    "current_mse": mse,
                    "baseline_mse": baseline_mse,
                    "current_mae": mae,
                    "baseline_mae": baseline_mae,
                    "degradation_pct": avg_degradation * 100,
                },
            )

        return None


class ModelManager:
    """Main MLOps model management system"""

    def __init__(self):
        self.settings = get_settings()
        self.registry = ModelRegistry()
        self.drift_detector = DriftDetector()
        self.monitoring_data = {}
        self.retraining_queue = []

    async def train_and_register_model(
        self,
        model_id: str,
        training_data: pd.DataFrame,
        features: pd.DataFrame,
        target_column: str = "close",
    ) -> ModelVersion:
        """Train a new model and register it"""

        # Create and train ensemble model
        ensemble_model = EnsembleModel()

        training_results = await ensemble_model.train_models(
            training_data, features, target_column
        )

        # Calculate training metrics
        # Make some predictions on validation set for metrics
        val_data = training_data.tail(100)
        val_features = features.tail(100)

        predictions = []
        actuals = []

        for i in range(10, len(val_data)):  # Make 10 predictions
            pred_data = val_data.iloc[:i]
            pred_features = val_features.iloc[:i]

            prediction = ensemble_model.predict(pred_data, pred_features, model_id)
            actual = val_data[target_column].iloc[i]

            predictions.append(prediction.ensemble_prediction)
            actuals.append(actual)

        # Calculate metrics
        mse = np.mean([(p - a) ** 2 for p, a in zip(predictions, actuals)])
        mae = np.mean([abs(p - a) for p, a in zip(predictions, actuals)])

        returns = [(p - a) / a for p, a in zip(predictions[1:], actuals[:-1])]
        from ..utils.helpers import calculate_sharpe_ratio

        sharpe = calculate_sharpe_ratio(returns)

        metrics = {
            "mse": mse,
            "mae": mae,
            "sharpe_ratio": sharpe,
            "training_success": sum(training_results.values()),
        }

        # Register model
        model_version = self.registry.register_model(
            model_id, ensemble_model, training_data, metrics
        )

        # Set reference data for drift detection
        self.drift_detector.set_reference_data(model_id, features)

        audit_logger.info(
            "model_trained_and_registered",
            model_id=model_id,
            version=model_version.version,
            metrics=metrics,
        )

        return model_version

    async def deploy_model(self, model_id: str, version: str) -> bool:
        """Deploy a model version"""

        versions = self.registry.get_model_versions(model_id)
        target_version = next((v for v in versions if v.version == version), None)

        if not target_version:
            return False

        target_version.status = ModelStatus.DEPLOYED
        self.registry.save_registry()

        audit_logger.info("model_deployed", model_id=model_id, version=version)

        return True

    async def run_champion_challenger_test(
        self,
        model_id: str,
        challenger_version: str,
        test_data: pd.DataFrame,
        features: pd.DataFrame,
    ) -> Dict[str, Any]:
        """Run A/B test between champion and challenger models"""

        champion = self.registry.get_champion_model(model_id)
        challenger = next(
            (
                v
                for v in self.registry.get_model_versions(model_id)
                if v.version == challenger_version
            ),
            None,
        )

        if not champion or not challenger:
            return {"error": "Champion or challenger model not found"}

        # Load models (simplified - in practice, would load from disk)
        results = {
            "champion": {
                "version": champion.version,
                "metrics": champion.metrics.copy(),
            },
            "challenger": {
                "version": challenger.version,
                "metrics": challenger.metrics.copy(),
            },
            "test_period": {
                "start": datetime.now() - timedelta(days=7),
                "end": datetime.now(),
            },
            "recommendation": "maintain_champion",  # Default
        }

        # Compare metrics (simplified comparison)
        champ_sharpe = champion.metrics.get("sharpe_ratio", 0)
        chal_sharpe = challenger.metrics.get("sharpe_ratio", 0)

        champ_mse = champion.metrics.get("mse", float("inf"))
        chal_mse = challenger.metrics.get("mse", float("inf"))

        # Decision logic
        if chal_sharpe > champ_sharpe * 1.1 and chal_mse < champ_mse * 0.9:
            results["recommendation"] = "promote_challenger"
            results["reason"] = "Challenger shows significantly better performance"
        elif chal_sharpe < champ_sharpe * 0.9 or chal_mse > champ_mse * 1.1:
            results["recommendation"] = "reject_challenger"
            results["reason"] = "Challenger performance is worse than champion"

        audit_logger.info(
            "champion_challenger_test_completed",
            model_id=model_id,
            recommendation=results["recommendation"],
            champion_version=champion.version,
            challenger_version=challenger.version,
        )

        return results

    async def monitor_model_performance(
        self,
        model_id: str,
        predictions: List[Tuple[float, float, float]],  # prediction, actual, confidence
        features: pd.DataFrame,
    ) -> List[DriftDetection]:
        """Monitor model performance and detect drift"""

        if model_id not in self.monitoring_data:
            self.monitoring_data[model_id] = {
                "predictions": [],
                "monitoring_history": [],
            }

        # Add new predictions
        self.monitoring_data[model_id]["predictions"].extend(predictions)

        # Keep only recent data
        if len(self.monitoring_data[model_id]["predictions"]) > 10000:
            self.monitoring_data[model_id]["predictions"] = self.monitoring_data[
                model_id
            ]["predictions"][-5000:]

        # Calculate monitoring metrics
        recent_preds = self.monitoring_data[model_id]["predictions"][-1000:]

        if len(recent_preds) >= 100:
            pred_values, actual_values, confidences = zip(*recent_preds)

            monitoring = ModelMonitoring(
                model_id=model_id,
                timestamp=datetime.now(),
                prediction_count=len(recent_preds),
                avg_confidence=np.mean(confidences),
                accuracy=1
                - np.mean([abs(p - a) / a for p, a in zip(pred_values, actual_values)]),
                latency_ms=50,  # Placeholder
                error_rate=0.01,  # Placeholder
                drift_score=0.1,  # Placeholder
            )

            self.monitoring_data[model_id]["monitoring_history"].append(monitoring)

        # Detect drift
        drift_detections = []

        # Data drift
        data_drift = self.drift_detector.detect_data_drift(model_id, features)
        if data_drift:
            drift_detections.append(data_drift)

        # Performance drift
        if len(recent_preds) >= 100:
            champion = self.registry.get_champion_model(model_id)
            if champion:
                perf_drift = self.drift_detector.detect_performance_drift(
                    model_id, [(p, a) for p, a, _ in recent_preds], champion.metrics
                )
                if perf_drift:
                    drift_detections.append(perf_drift)

        # Log drift detections
        for drift in drift_detections:
            audit_logger.warning(
                "model_drift_detected",
                model_id=model_id,
                drift_type=drift.drift_type.value,
                severity=drift.severity,
                recommendation=drift.recommendation,
            )

            # Add to retraining queue if severe
            if drift.severity > 0.7 and model_id not in self.retraining_queue:
                self.retraining_queue.append(model_id)

        return drift_detections

    async def auto_retrain_models(
        self, training_data: pd.DataFrame, features: pd.DataFrame
    ) -> Dict[str, ModelVersion]:
        """Automatically retrain models in queue"""

        retrained_models = {}

        for model_id in self.retraining_queue.copy():
            try:
                # Retrain model
                new_version = await self.train_and_register_model(
                    model_id, training_data, features
                )

                # Set as challenger
                new_version.status = ModelStatus.CHALLENGER
                self.registry.save_registry()

                retrained_models[model_id] = new_version
                self.retraining_queue.remove(model_id)

                audit_logger.info(
                    "model_auto_retrained",
                    model_id=model_id,
                    new_version=new_version.version,
                )

            except Exception as e:
                logging.error(f"Error auto-retraining model {model_id}: {e}")

        return retrained_models

    def get_model_status(self) -> Dict[str, Dict[str, Any]]:
        """Get comprehensive model status"""
        status = {}

        for model_id, versions in self.registry.models.items():
            champion = self.registry.get_champion_model(model_id)
            latest = versions[-1] if versions else None

            monitoring_history = self.monitoring_data.get(model_id, {}).get(
                "monitoring_history", []
            )
            latest_monitoring = monitoring_history[-1] if monitoring_history else None

            status[model_id] = {
                "total_versions": len(versions),
                "champion_version": champion.version if champion else None,
                "latest_version": latest.version if latest else None,
                "champion_metrics": champion.metrics if champion else {},
                "latest_monitoring": (
                    latest_monitoring.__dict__ if latest_monitoring else None
                ),
                "in_retraining_queue": model_id in self.retraining_queue,
                "versions": [
                    {
                        "version": v.version,
                        "status": v.status.value,
                        "created_at": v.created_at.isoformat(),
                        "metrics": v.metrics,
                    }
                    for v in versions
                ],
            }

        return status
