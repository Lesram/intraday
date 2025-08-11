"""
MLOps Model Registry and Drift Detection System (Branch 2.6)
On-disk model registry with feature schema lock, PSI drift detection, and inference telemetry.
Integrates with existing observability infrastructure from Branch 2.5.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
import hashlib
import json
import logging
from pathlib import Path
import pickle
from typing import Any

import numpy as np
import pandas as pd

from ..config import get_settings
from ..models.ensemble_model import EnsembleModel

# Import MLOps components with fallback for backward compatibility
try:
    from ..infra.logging import get_structured_logger
    from ..infra.metrics import get_metrics_registry

    OBSERVABILITY_AVAILABLE = True
    logger = get_structured_logger("mlops.model_manager")
    metrics = get_metrics_registry()
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    import logging

    logger = logging.getLogger("mlops.model_manager")
    metrics = None

# Backward compatibility imports
try:
    from ..utils.logger import audit_logger, performance_logger
except ImportError:
    # Fallback to standard logger for missing utils
    audit_logger = logger
    performance_logger = logger


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
    """Model version metadata with registry support"""

    model_id: str
    version: str
    created_at: datetime
    status: ModelStatus
    metrics: dict[str, float]
    training_data_hash: str
    feature_names: list[str]
    feature_dtypes: dict[str, str] = field(default_factory=dict)
    train_window: dict[str, str] = field(default_factory=dict)
    artifact_hash: str | None = None
    model_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SchemaMismatchError(ValueError):
    """Raised when feature schema doesn't match expected schema"""

    def __init__(
        self, message: str, expected_schema: dict[str, str], received_schema: dict[str, str]
    ):
        super().__init__(message)
        self.expected_schema = expected_schema
        self.received_schema = received_schema


@dataclass
class DriftDetection:
    """Enhanced drift detection result with PSI support"""

    drift_type: DriftType
    severity: float  # 0-1 scale
    detected_at: datetime
    affected_features: list[str]
    recommendation: str
    details: dict[str, Any] = field(default_factory=dict)
    model_name: str | None = None
    psi_score: float | None = None
    threshold: float | None = None


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
    """On-disk model registry with artifacts/{model_name}/{version}/ structure"""

    def __init__(self, base_path: str = "./artifacts"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True, parents=True)
        self.registry_file = self.base_path / "model_registry.json"
        self.models: dict[str, list[ModelVersion]] = {}
        self.champions: dict[str, str] = {}  # model_name -> version
        self.load_registry()

        # Get MLOps settings from config
        settings = get_settings()
        self.drift_psi_warn = getattr(settings, "mlops_drift_psi_warn", 0.1)
        self.drift_psi_alert = getattr(settings, "mlops_drift_psi_alert", 0.25)
        self.inference_log_max_rows = getattr(settings, "mlops_inference_log_max_rows", 200000)

    def load_registry(self):
        """Load model registry from disk"""
        try:
            if self.registry_file.exists():
                with open(self.registry_file) as f:
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
                            feature_dtypes=v.get("feature_dtypes", {}),
                            train_window=v.get("train_window", {}),
                            artifact_hash=v.get("artifact_hash"),
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
                        "feature_dtypes": v.feature_dtypes,
                        "train_window": v.train_window,
                        "artifact_hash": v.artifact_hash,
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
        metrics: dict[str, float],
        train_window: dict[str, str] | None = None,
        artifacts: dict[str, Any] | None = None,
    ) -> ModelVersion:
        """Register a new model version with on-disk artifacts storage"""

        # Generate version
        if model_id not in self.models:
            self.models[model_id] = []
        version = f"v{len(self.models[model_id]) + 1}"

        # Calculate training data hash
        data_hash = hashlib.md5(pd.util.hash_pandas_object(training_data).values).hexdigest()

        # Create model directory with new structure: artifacts/{model_name}/{version}/
        model_path = self.base_path / model_id / version
        model_path.mkdir(parents=True, exist_ok=True)

        # Persist model object
        model_file = model_path / "model.bin"
        try:
            with open(model_file, "wb") as f:
                pickle.dump(model, f)
        except Exception as e:
            logger.error(f"Error saving model to disk: {e}")
            model_file = None

        # Persist artifacts
        if artifacts:
            artifacts_path = model_path / "artifacts.pkl"
            with open(artifacts_path, "wb") as f:
                pickle.dump(artifacts, f)

        # Compute artifact hash
        artifact_hash = None
        if model_file:
            artifact_hash = self._compute_file_hash(model_file)

        # Get feature dtypes
        feature_dtypes = {col: str(training_data[col].dtype) for col in training_data.columns}

        # Branch 2.9: Create standardized feature schema
        from ..features.types import FeatureSchema

        try:
            feature_schema = FeatureSchema(
                columns=list(training_data.columns),
                dtypes={
                    col: self._normalize_dtype_string(str(training_data[col].dtype))
                    for col in training_data.columns
                },
            )
            feature_schema_dict = {
                "columns": feature_schema.columns,
                "dtypes": feature_schema.dtypes,
            }
        except Exception as e:
            logger.warning(f"Could not create FeatureSchema: {e}")
            feature_schema_dict = {"columns": list(training_data.columns), "dtypes": feature_dtypes}

        # Create metadata.json
        metadata = {
            "model_id": model_id,
            "version": version,
            "created_at": datetime.now(UTC).isoformat(),
            "train_window": train_window or {},
            "feature_names": list(training_data.columns),  # Legacy compatibility
            "feature_dtypes": feature_dtypes,  # Legacy compatibility
            "feature_schema": feature_schema_dict,  # Branch 2.9: Standardized schema
            "metrics": metrics,
            "artifact_hash": artifact_hash,
            "training_samples": len(training_data),
            "features_count": len(training_data.columns),
        }

        # Store metadata.json
        metadata_path = model_path / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        # Store reference distributions for drift detection
        self._store_reference_distributions(model_path, training_data)

        # Create model version
        model_version = ModelVersion(
            model_id=model_id,
            version=version,
            created_at=datetime.now(),
            status=ModelStatus.TRAINED,
            metrics=metrics,
            training_data_hash=data_hash,
            feature_names=list(training_data.columns),
            feature_dtypes=feature_dtypes,
            train_window=train_window or {},
            artifact_hash=artifact_hash,
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
            artifact_hash=artifact_hash,
        )

        # Increment registration metric (using module-level metrics registry)
        if globals().get("metrics") and hasattr(globals()["metrics"], "inc_counter"):
            globals()["metrics"].inc_counter("mlops_models_registered_total", {"model": model_id})

        return model_version

    def get_champion_model(self, model_id: str) -> ModelVersion | None:
        """Get current champion model with on-disk champion.txt support"""

        # Check on-disk champion file first
        champion_file = self.base_path / model_id / "champion.txt"
        champion_version = None

        if champion_file.exists():
            champion_version = champion_file.read_text().strip()
            self.champions[model_id] = champion_version
        else:
            # Fall back to in-memory champions or status
            if model_id not in self.models:
                return None

            # Check existing champion from status
            champions = [v for v in self.models[model_id] if v.status == ModelStatus.CHAMPION]
            if champions:
                return champions[-1]

            return None

        # Find champion version
        if champion_version and model_id in self.models:
            for version in self.models[model_id]:
                if version.version == champion_version:
                    return version

        return None

    def promote_to_champion(self, model_id: str, version: str) -> bool:
        """Promote model version to champion with champion.txt file"""
        if model_id not in self.models:
            return False

        # Verify version exists
        target_version = None
        for model_version in self.models[model_id]:
            if model_version.version == version:
                target_version = model_version
                break

        if not target_version:
            return False

        # Demote current champion
        for model_version in self.models[model_id]:
            if model_version.status == ModelStatus.CHAMPION:
                model_version.status = ModelStatus.DEPLOYED

        # Promote new champion
        target_version.status = ModelStatus.CHAMPION
        self.champions[model_id] = version
        self.save_registry()

        # Write champion.txt file
        champion_file = self.base_path / model_id / "champion.txt"
        champion_file.parent.mkdir(parents=True, exist_ok=True)
        champion_file.write_text(version)

        audit_logger.info("model_promoted_to_champion", model_id=model_id, version=version)

        # Increment promotion metric (using module-level metrics registry)
        if globals().get("metrics") and hasattr(globals()["metrics"], "inc_counter"):
            globals()["metrics"].inc_counter("mlops_models_promoted_total", {"model": model_id})

        return True

    def get_model_versions(self, model_id: str) -> list[ModelVersion]:
        """Get all versions of a model"""
        return self.models.get(model_id, [])

    def load_artifacts(
        self, model_id: str, version: str
    ) -> tuple[Any, dict[str, Any], dict[str, Any]]:
        """
        Load model artifacts from disk.

        Args:
            model_id: Name of the model
            version: Version to load

        Returns:
            Tuple of (model_obj, artifacts, metadata)
        """
        try:
            version_path = self.base_path / model_id / version

            # Load model object
            model_path = version_path / "model.bin"
            with open(model_path, "rb") as f:
                model_obj = pickle.load(f)

            # Load artifacts (optional)
            artifacts = {}
            artifacts_path = version_path / "artifacts.pkl"
            if artifacts_path.exists():
                with open(artifacts_path, "rb") as f:
                    artifacts = pickle.load(f)

            # Load metadata
            metadata_path = version_path / "metadata.json"
            with open(metadata_path) as f:
                metadata = json.load(f)

            logger.debug(
                f"Loaded artifacts for {model_id}/{version}",
                {
                    "model_id": model_id,
                    "version": version,
                    "artifact_hash": metadata.get("artifact_hash"),
                },
            )

            return model_obj, artifacts, metadata

        except Exception as e:
            logger.error(
                f"Failed to load artifacts for {model_id}/{version}",
                {"error": str(e), "model_id": model_id, "version": version},
            )
            raise

    def assert_feature_schema(
        self, live_df: pd.DataFrame, metadata: dict[str, Any]
    ) -> pd.DataFrame:
        """
        Validate feature schema against expected schema.

        Args:
            live_df: Live features DataFrame
            metadata: Model metadata with expected schema

        Returns:
            DataFrame with corrected column order if needed

        Raises:
            SchemaMismatchError: If schema doesn't match
        """
        expected_features = set(metadata["feature_names"])
        expected_dtypes = metadata.get("feature_dtypes", {})
        received_features = set(live_df.columns)
        received_dtypes = {col: str(live_df[col].dtype) for col in live_df.columns}

        # Check for missing or extra columns
        missing_features = expected_features - received_features
        extra_features = received_features - expected_features

        if missing_features or extra_features:
            error_msg = "Schema mismatch for model features"
            if missing_features:
                error_msg += f". Missing features: {sorted(missing_features)}"
            if extra_features:
                error_msg += f". Extra features: {sorted(extra_features)}"

            raise SchemaMismatchError(
                error_msg, expected_schema=expected_dtypes, received_schema=received_dtypes
            )

        # Reorder columns to match expected order if needed
        expected_order = metadata["feature_names"]
        if list(live_df.columns) != expected_order:
            logger.debug("Reordering columns to match expected schema")
            live_df = live_df[expected_order]

        return live_df

    def record_inference(
        self,
        model_id: str,
        version: str,
        features: pd.DataFrame,
        prediction: float,
        truth: float | None,
        latency_ms: float,
    ) -> None:
        """
        Record inference telemetry to parquet log.

        Args:
            model_id: Name of the model
            version: Model version
            features: Input features DataFrame
            prediction: Model prediction
            truth: Ground truth (if available)
            latency_ms: Inference latency in milliseconds
        """
        try:
            # Create features hash (never log raw features)
            features_hash = hashlib.sha256(str(features.values.tobytes()).encode()).hexdigest()[:16]

            # Create inference record
            inference_record = {
                "ts": datetime.now(UTC).isoformat(),
                "features_hash": features_hash,
                "prediction": prediction,
                "truth": truth,
                "latency_ms": latency_ms,
            }

            # Append to inference log
            log_path = self.base_path / model_id / version / "inference_log.parquet"

            # Convert to DataFrame
            new_df = pd.DataFrame([inference_record])

            # Append or create
            if log_path.exists():
                try:
                    existing_df = pd.read_parquet(log_path)
                    combined_df = pd.concat([existing_df, new_df], ignore_index=True)

                    # Trim if exceeds max rows
                    if len(combined_df) > self.inference_log_max_rows:
                        combined_df = combined_df.tail(self.inference_log_max_rows)

                    combined_df.to_parquet(log_path, index=False)
                except Exception:
                    # Fallback to overwrite if corruption
                    new_df.to_parquet(log_path, index=False)
            else:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                new_df.to_parquet(log_path, index=False)

            # Record metrics (using module-level metrics registry)
            if globals().get("metrics") and hasattr(globals()["metrics"], "inc_counter"):
                globals()["metrics"].inc_counter(
                    "model_inferences_total", {"model": model_id, "version": version}
                )

                globals()["metrics"].observe_histogram(
                    "model_latency_seconds",
                    latency_ms / 1000.0,
                    {"model": model_id, "version": version},
                )

        except Exception as e:
            logger.error(
                f"Failed to record inference for {model_id}/{version}",
                {"error": str(e), "model_id": model_id, "version": version},
            )

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def _normalize_dtype_string(self, dtype_str: str) -> str:
        """Normalize pandas dtype string to standardized format."""
        dtype_str = dtype_str.lower()

        # Map to standard dtype strings
        if "float64" in dtype_str or "double" in dtype_str:
            return "float64"
        elif "float32" in dtype_str or "single" in dtype_str:
            return "float32"
        elif "int64" in dtype_str:
            return "int64"
        elif "int32" in dtype_str:
            return "int32"
        elif "bool" in dtype_str:
            return "bool"
        else:
            # Default to float64 for numeric, keep original for others
            return "float64" if pd.api.types.is_numeric_dtype(dtype_str) else dtype_str

    def _store_reference_distributions(self, model_path: Path, training_data: pd.DataFrame) -> None:
        """Store reference distributions for PSI drift detection."""
        reference_distributions = {}

        for column in training_data.columns:
            if pd.api.types.is_numeric_dtype(training_data[column]):
                # For numeric features, create histogram bins
                values = training_data[column].dropna()
                if len(values) > 0:
                    try:
                        counts, bin_edges = np.histogram(values, bins=10)
                        reference_distributions[column] = {
                            "bin_edges": bin_edges.tolist(),
                            "bin_counts": counts.tolist(),
                            "mean": float(values.mean()),
                            "std": float(values.std()),
                        }
                    except Exception:
                        reference_distributions[column] = {
                            "bin_edges": [],
                            "bin_counts": [],
                            "mean": 0.0,
                            "std": 1.0,
                        }
            else:
                # For categorical features, store value counts
                value_counts = training_data[column].value_counts()
                reference_distributions[column] = {
                    "categories": value_counts.index.tolist(),
                    "counts": value_counts.values.tolist(),
                    "total": len(training_data[column]),
                }

        ref_path = model_path / "reference_distributions.json"
        with open(ref_path, "w") as f:
            json.dump(reference_distributions, f, indent=2)


class DriftDetector:
    """Enhanced drift detector with PSI (Population Stability Index) support"""

    def __init__(self, window_size: int = 1000, registry: ModelRegistry | None = None):
        self.window_size = window_size
        self.reference_data = {}  # model_id -> reference statistics
        self.monitoring_data = {}  # model_id -> recent data
        self.registry = registry

        # Get drift thresholds from settings
        settings = get_settings()
        self.drift_psi_warn = getattr(settings, "mlops_drift_psi_warn", 0.1)
        self.drift_psi_alert = getattr(settings, "mlops_drift_psi_alert", 0.25)
        self.perf_alert_drop = getattr(settings, "mlops_perf_alert_drop", 0.05)

    def set_reference_data(self, model_id: str, data: pd.DataFrame):
        """Set reference data for drift detection"""
        self.reference_data[model_id] = {
            "mean": data.mean().to_dict(),
            "std": data.std().to_dict(),
            "correlations": data.corr().to_dict(),
            "feature_names": list(data.columns),
        }

    def detect_data_drift(self, model_id: str, current_data: pd.DataFrame) -> DriftDetection | None:
        """Detect data drift using PSI and statistical tests"""

        # Try to get reference distributions from registry
        champion = None
        if self.registry:
            champion = self.registry.get_champion_model(model_id)

        if champion:
            return self._detect_drift_with_psi(model_id, champion, current_data)

        # Fallback to existing statistical drift detection
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
                model_name=model_id,
            )

        return None

    def _detect_drift_with_psi(
        self, model_id: str, champion: ModelVersion, current_data: pd.DataFrame
    ) -> DriftDetection | None:
        """Detect drift using Population Stability Index (PSI)"""
        try:
            # Load reference distributions
            ref_dists_path = (
                self.registry.base_path
                / model_id
                / champion.version
                / "reference_distributions.json"
            )
            if not ref_dists_path.exists():
                logger.warning(
                    f"No reference distributions found for {model_id}/{champion.version}"
                )
                return None

            with open(ref_dists_path) as f:
                reference_distributions = json.load(f)

            # Compute PSI for each feature
            psi_scores = {}
            for feature in champion.feature_names:
                if feature not in current_data.columns:
                    continue

                ref_dist = reference_distributions.get(feature, {})
                if not ref_dist.get("bin_edges"):
                    continue

                psi_score = self._compute_psi(
                    current_data[feature].values, ref_dist["bin_edges"], ref_dist["bin_counts"]
                )
                psi_scores[feature] = psi_score

            if not psi_scores:
                return None

            # Determine drift severity based on PSI scores
            max_psi = max(psi_scores.values())
            avg_psi = sum(psi_scores.values()) / len(psi_scores)

            # Determine severity
            severity = None
            threshold = None
            if max_psi >= self.drift_psi_alert:
                severity = "alert"
                threshold = self.drift_psi_alert
            elif max_psi >= self.drift_psi_warn:
                severity = "warn"
                threshold = self.drift_psi_warn

            if severity:
                drift_detection = DriftDetection(
                    drift_type=DriftType.DATA_DRIFT,
                    severity=max_psi / self.drift_psi_alert,  # Normalize severity
                    detected_at=datetime.now(),
                    affected_features=[
                        f for f, s in psi_scores.items() if s >= self.drift_psi_warn
                    ],
                    recommendation=f"Data drift detected with PSI {max_psi:.3f}. Consider retraining model.",
                    details={
                        "psi_scores": psi_scores,
                        "max_psi": max_psi,
                        "avg_psi": avg_psi,
                        "threshold": threshold,
                    },
                    model_name=model_id,
                    psi_score=max_psi,
                    threshold=threshold,
                )

                # Increment drift alert metric
                if globals().get("metrics") and hasattr(globals()["metrics"], "inc_counter"):
                    globals()["metrics"].inc_counter(
                        "model_drift_alerts_total", {"model": model_id, "type": "input_psi"}
                    )

                logger.warning(
                    f"Data drift detected for {model_id}",
                    {
                        "model_id": model_id,
                        "drift_type": "input_psi",
                        "severity": severity,
                        "max_psi": max_psi,
                        "threshold": threshold,
                    },
                )

                return drift_detection

            return None

        except Exception as e:
            logger.error(
                f"Failed to detect PSI drift for {model_id}",
                {"error": str(e), "model_id": model_id},
            )
            return None

    def _compute_psi(
        self, live_values: np.ndarray, ref_bin_edges: list[float], ref_bin_counts: list[int]
    ) -> float:
        """Compute Population Stability Index between live and reference data."""
        if not ref_bin_edges or not ref_bin_counts:
            return 0.0

        try:
            # Create live distribution using same bins
            live_counts, _ = np.histogram(live_values, bins=ref_bin_edges)

            # Check for empty data
            if sum(live_counts) == 0 or sum(ref_bin_counts) == 0:
                return 0.0

            # Convert to proportions
            ref_props = np.array(ref_bin_counts) / sum(ref_bin_counts)
            live_props = live_counts / sum(live_counts)

            # Add small epsilon to avoid log(0)
            epsilon = 1e-6
            ref_props = np.maximum(ref_props, epsilon)
            live_props = np.maximum(live_props, epsilon)

            # Compute PSI
            psi = sum((live_props - ref_props) * np.log(live_props / ref_props))
            return float(psi)

        except Exception:
            return 0.0

    def detect_performance_drift(
        self,
        model_id: str,
        recent_predictions: list[tuple[float, float]],  # (prediction, actual)
        baseline_metrics: dict[str, float],
    ) -> DriftDetection | None:
        """Detect performance drift"""

        if len(recent_predictions) < 100:  # Need enough samples
            return None

        predictions, actuals = zip(*recent_predictions, strict=False)

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
    """Enhanced MLOps model management system with Branch 2.6 features"""

    def __init__(self, registry_root: str | None = None):
        self.settings = get_settings()
        self.registry = ModelRegistry(
            registry_root or getattr(self.settings, "mlops_registry_root", "./artifacts")
        )
        self.drift_detector = DriftDetector(registry=self.registry)
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

        training_results = await ensemble_model.train_models(training_data, features, target_column)

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
        mse = np.mean([(p - a) ** 2 for p, a in zip(predictions, actuals, strict=False)])
        mae = np.mean([abs(p - a) for p, a in zip(predictions, actuals, strict=False)])

        returns = [(p - a) / a for p, a in zip(predictions[1:], actuals[:-1], strict=False)]
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
    ) -> dict[str, Any]:
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
        predictions: list[tuple[float, float, float]],  # prediction, actual, confidence
        features: pd.DataFrame,
    ) -> list[DriftDetection]:
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
            self.monitoring_data[model_id]["predictions"] = self.monitoring_data[model_id][
                "predictions"
            ][-5000:]

        # Calculate monitoring metrics
        recent_preds = self.monitoring_data[model_id]["predictions"][-1000:]

        if len(recent_preds) >= 100:
            pred_values, actual_values, confidences = zip(*recent_preds, strict=False)

            monitoring = ModelMonitoring(
                model_id=model_id,
                timestamp=datetime.now(),
                prediction_count=len(recent_preds),
                avg_confidence=np.mean(confidences),
                accuracy=1
                - np.mean(
                    [abs(p - a) / a for p, a in zip(pred_values, actual_values, strict=False)]
                ),
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
    ) -> dict[str, ModelVersion]:
        """Automatically retrain models in queue"""

        retrained_models = {}

        for model_id in self.retraining_queue.copy():
            try:
                # Retrain model
                new_version = await self.train_and_register_model(model_id, training_data, features)

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

    def get_model_status(self) -> dict[str, dict[str, Any]]:
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
                "latest_monitoring": (latest_monitoring.__dict__ if latest_monitoring else None),
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


# Global model manager instance
_model_manager: ModelManager | None = None


def get_model_manager() -> ModelManager:
    """Get global model manager instance"""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager


def register_model(
    model_name: str,
    version: str | None,
    model_obj: Any,
    artifacts: dict[str, Any],
    metrics: dict[str, float],
    feature_list: list[str],
    feature_dtypes: dict[str, str],
    train_window: dict[str, str],
) -> ModelVersion:
    """Convenience function to register a model with the global manager"""
    manager = get_model_manager()
    # Convert parameters to match registry interface
    training_data = pd.DataFrame(columns=feature_list)
    for col, dtype in feature_dtypes.items():
        training_data[col] = training_data[col].astype(dtype)

    return manager.registry.register_model(
        model_name, model_obj, training_data, metrics, train_window, artifacts
    )


def get_champion_model(model_name: str) -> ModelVersion | None:
    """Convenience function to get champion model"""
    manager = get_model_manager()
    return manager.registry.get_champion_model(model_name)


def detect_data_drift(model_name: str, live_df: pd.DataFrame) -> DriftDetection | None:
    """Convenience function to detect data drift"""
    manager = get_model_manager()
    return manager.drift_detector.detect_data_drift(model_name, live_df)
