"""
ML Pipeline Orchestrator for Trading Platform.

Provides a unified interface for:
- Feature engineering pipeline with caching
- Model training with validation
- Batch and streaming inference
- Model versioning and A/B testing
- Performance monitoring and drift detection

This orchestrator coordinates between feature engineering, training,
and inference to provide a cohesive ML workflow.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Pipeline execution stages."""

    DATA_INGESTION = "data_ingestion"
    FEATURE_ENGINEERING = "feature_engineering"
    FEATURE_VALIDATION = "feature_validation"
    MODEL_TRAINING = "model_training"
    MODEL_VALIDATION = "model_validation"
    MODEL_DEPLOYMENT = "model_deployment"
    INFERENCE = "inference"
    MONITORING = "monitoring"


class PipelineStatus(Enum):
    """Pipeline execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PipelineConfig:
    """Configuration for ML pipeline."""

    # Feature engineering
    feature_cache_ttl_seconds: int = 3600
    feature_cache_dir: str = ".cache/features"

    # Training
    validation_split: float = 0.2
    early_stopping_patience: int = 10
    max_training_time_seconds: int = 3600

    # Inference
    batch_size: int = 32
    inference_timeout_ms: float = 100.0

    # Monitoring
    drift_threshold: float = 0.1
    performance_window_days: int = 7

    # A/B Testing
    enable_ab_testing: bool = False
    challenger_traffic_pct: float = 0.1


@dataclass
class FeatureCacheEntry:
    """Cached feature data."""

    cache_key: str
    features: pd.DataFrame
    created_at: datetime
    expires_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at


@dataclass
class PipelineRunResult:
    """Result from a pipeline run."""

    run_id: str
    status: PipelineStatus
    stage: PipelineStage
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    output: Any = None
    error: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


class FeatureStore(Protocol):
    """Protocol for feature store implementations."""

    async def get_features(
        self,
        symbols: list[str],
        feature_names: list[str],
        start_time: datetime,
        end_time: datetime,
    ) -> pd.DataFrame:
        ...

    async def store_features(
        self,
        features: pd.DataFrame,
        metadata: dict[str, Any],
    ) -> None:
        ...


class FeaturePipeline:
    """
    Feature engineering pipeline with caching and validation.

    Handles:
    - Feature computation from raw data
    - Feature caching for efficiency
    - Feature validation and schema checks
    - Feature versioning
    """

    def __init__(
        self,
        config: PipelineConfig,
        feature_store: FeatureStore | None = None,
    ):
        self.config = config
        self.feature_store = feature_store
        self._cache: dict[str, FeatureCacheEntry] = {}
        self._feature_registry: dict[str, Callable] = {}

        # Ensure cache directory exists
        Path(config.feature_cache_dir).mkdir(parents=True, exist_ok=True)

    def register_feature(
        self,
        name: str,
        compute_fn: Callable[[pd.DataFrame], pd.Series],
        dependencies: list[str] | None = None,
    ):
        """Register a feature computation function."""
        self._feature_registry[name] = {
            "compute": compute_fn,
            "dependencies": dependencies or [],
        }
        logger.info(f"Registered feature: {name}")

    def _compute_cache_key(
        self,
        symbols: list[str],
        feature_names: list[str],
        start_time: datetime,
        end_time: datetime,
    ) -> str:
        """Compute cache key for feature request."""
        key_data = {
            "symbols": sorted(symbols),
            "features": sorted(feature_names),
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
        }
        return hashlib.sha256(
            json.dumps(key_data, sort_keys=True).encode()
        ).hexdigest()[:16]

    async def get_features(
        self,
        data: pd.DataFrame,
        feature_names: list[str],
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        Compute or retrieve cached features.

        Args:
            data: Raw data DataFrame with OHLCV columns
            feature_names: List of feature names to compute
            use_cache: Whether to use cache

        Returns:
            DataFrame with computed features
        """
        # Check cache
        if use_cache:
            cache_key = self._compute_cache_key(
                symbols=data['symbol'].unique().tolist() if 'symbol' in data.columns else ['default'],
                feature_names=feature_names,
                start_time=data.index.min() if hasattr(data.index, 'min') else datetime.now(UTC),
                end_time=data.index.max() if hasattr(data.index, 'max') else datetime.now(UTC),
            )

            if cache_key in self._cache:
                entry = self._cache[cache_key]
                if not entry.is_expired:
                    logger.debug(f"Cache hit for features: {cache_key}")
                    return entry.features

        # Compute features
        result = data.copy()

        # Sort by dependencies and compute
        sorted_features = self._sort_by_dependencies(feature_names)

        for feature_name in sorted_features:
            if feature_name not in self._feature_registry:
                logger.warning(f"Feature not registered: {feature_name}")
                continue

            try:
                compute_fn = self._feature_registry[feature_name]["compute"]
                result[feature_name] = compute_fn(result)
            except Exception as e:
                logger.error(f"Failed to compute feature {feature_name}: {e}")
                result[feature_name] = np.nan

        # Cache result
        if use_cache:
            expires = datetime.now(UTC) + timedelta(seconds=self.config.feature_cache_ttl_seconds)
            self._cache[cache_key] = FeatureCacheEntry(
                cache_key=cache_key,
                features=result[feature_names],
                created_at=datetime.now(UTC),
                expires_at=expires,
            )

        return result[feature_names]

    def _sort_by_dependencies(self, feature_names: list[str]) -> list[str]:
        """Sort features by their dependencies (topological sort)."""
        visited = set()
        result = []

        def visit(name: str):
            if name in visited:
                return
            visited.add(name)

            if name in self._feature_registry:
                for dep in self._feature_registry[name]["dependencies"]:
                    visit(dep)

            result.append(name)

        for name in feature_names:
            visit(name)

        return result

    def validate_features(
        self,
        features: pd.DataFrame,
        schema: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """
        Validate features against schema.

        Returns:
            Tuple of (is_valid, list of validation errors)
        """
        errors = []

        # Check required columns
        for col, spec in schema.items():
            if col not in features.columns:
                errors.append(f"Missing required feature: {col}")
                continue

            # Type check
            if "dtype" in spec:
                if not np.issubdtype(features[col].dtype, spec["dtype"]):
                    errors.append(f"Type mismatch for {col}: expected {spec['dtype']}")

            # Range check
            if "min" in spec and features[col].min() < spec["min"]:
                errors.append(f"{col} below minimum: {features[col].min()} < {spec['min']}")

            if "max" in spec and features[col].max() > spec["max"]:
                errors.append(f"{col} above maximum: {features[col].max()} > {spec['max']}")

            # Null check
            if spec.get("nullable", True) is False and features[col].isnull().any():
                errors.append(f"{col} contains null values but is non-nullable")

        return len(errors) == 0, errors

    def clear_cache(self, expired_only: bool = True):
        """Clear feature cache."""
        if expired_only:
            self._cache = {
                k: v for k, v in self._cache.items()
                if not v.is_expired
            }
        else:
            self._cache = {}


class InferencePipeline:
    """
    Real-time and batch inference pipeline.

    Handles:
    - Model loading and caching
    - Batch inference for efficiency
    - Streaming inference with low latency
    - A/B testing between models
    - Fallback to baseline models
    """

    def __init__(
        self,
        config: PipelineConfig,
        feature_pipeline: FeaturePipeline,
    ):
        self.config = config
        self.feature_pipeline = feature_pipeline

        # Model registry
        self._champion_model: Any = None
        self._challenger_model: Any = None
        self._fallback_model: Any = None

        # Request counter for A/B testing
        self._request_counter = 0

    def set_champion_model(self, model: Any):
        """Set the primary production model."""
        self._champion_model = model
        logger.info("Champion model updated")

    def set_challenger_model(self, model: Any):
        """Set the A/B test challenger model."""
        self._challenger_model = model
        logger.info("Challenger model set for A/B testing")

    def set_fallback_model(self, model: Any):
        """Set fallback model for degraded mode."""
        self._fallback_model = model
        logger.info("Fallback model configured")

    def _select_model(self) -> tuple[Any, str]:
        """Select model for this request (handles A/B testing)."""
        self._request_counter += 1

        if self.config.enable_ab_testing and self._challenger_model:
            # Route percentage of traffic to challenger
            if (self._request_counter % 100) < (self.config.challenger_traffic_pct * 100):
                return self._challenger_model, "challenger"

        return self._champion_model, "champion"

    async def predict(
        self,
        features: dict[str, Any] | pd.DataFrame,
        timeout_ms: float | None = None,
    ) -> dict[str, Any]:
        """
        Make a single prediction.

        Args:
            features: Feature dict or DataFrame row
            timeout_ms: Optional timeout override

        Returns:
            Prediction result with metadata
        """
        timeout = (timeout_ms or self.config.inference_timeout_ms) / 1000.0
        start_time = datetime.now(UTC)

        # Select model
        model, model_variant = self._select_model()

        if model is None:
            if self._fallback_model:
                model = self._fallback_model
                model_variant = "fallback"
                logger.warning("Using fallback model")
            else:
                raise RuntimeError("No model available for inference")

        try:
            # Convert to expected format
            if isinstance(features, dict):
                features_df = pd.DataFrame([features])
            else:
                features_df = features

            # Make prediction with timeout
            prediction = await asyncio.wait_for(
                self._run_prediction(model, features_df),
                timeout=timeout,
            )

            latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return {
                "prediction": prediction,
                "model_variant": model_variant,
                "latency_ms": latency_ms,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except TimeoutError:
            logger.error(f"Prediction timed out after {timeout}s")
            raise
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            raise

    async def _run_prediction(self, model: Any, features: pd.DataFrame) -> Any:
        """Run model prediction (may be sync or async)."""
        if hasattr(model, "predict_async"):
            return await model.predict_async(features)
        elif hasattr(model, "predict"):
            # Run sync prediction in executor
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, model.predict, features)
        else:
            raise ValueError("Model must have predict or predict_async method")

    async def predict_batch(
        self,
        features_batch: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        """
        Make batch predictions for efficiency.

        Args:
            features_batch: DataFrame with multiple rows

        Returns:
            List of prediction results
        """
        start_time = datetime.now(UTC)

        model, model_variant = self._select_model()

        if model is None:
            raise RuntimeError("No model available for inference")

        try:
            predictions = await self._run_prediction(model, features_batch)
            latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return [
                {
                    "prediction": pred,
                    "model_variant": model_variant,
                    "latency_ms": latency_ms / len(predictions),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                for pred in predictions
            ]

        except Exception as e:
            logger.error(f"Batch prediction failed: {e}")
            raise


class PipelineOrchestrator:
    """
    Orchestrates the full ML pipeline lifecycle.

    Coordinates:
    - Feature engineering
    - Model training
    - Model deployment
    - Inference
    - Monitoring
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.feature_pipeline = FeaturePipeline(config)
        self.inference_pipeline = InferencePipeline(config, self.feature_pipeline)

        # Run history
        self._runs: list[PipelineRunResult] = []
        self._current_run: PipelineRunResult | None = None

    def register_features(self, features: dict[str, Callable]):
        """Register multiple feature functions."""
        for name, fn in features.items():
            self.feature_pipeline.register_feature(name, fn)

    async def run_training_pipeline(
        self,
        training_data: pd.DataFrame,
        feature_names: list[str],
        model_class: type,
        model_params: dict[str, Any],
    ) -> PipelineRunResult:
        """
        Execute the full training pipeline.

        Stages:
        1. Feature engineering
        2. Train/validation split
        3. Model training
        4. Model validation
        """
        run_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        start_time = datetime.now(UTC)

        result = PipelineRunResult(
            run_id=run_id,
            status=PipelineStatus.RUNNING,
            stage=PipelineStage.FEATURE_ENGINEERING,
            started_at=start_time,
        )
        self._current_run = result

        try:
            # Stage 1: Feature Engineering
            logger.info(f"[{run_id}] Stage 1: Feature Engineering")
            features = await self.feature_pipeline.get_features(
                training_data, feature_names
            )

            # Stage 2: Split data
            result.stage = PipelineStage.MODEL_TRAINING
            logger.info(f"[{run_id}] Stage 2: Model Training")

            split_idx = int(len(features) * (1 - self.config.validation_split))
            train_features = features.iloc[:split_idx]
            val_features = features.iloc[split_idx:]

            # Stage 3: Train model
            model = model_class(**model_params)

            # Assuming y is last column or separately provided
            X_train = train_features.iloc[:, :-1]
            y_train = train_features.iloc[:, -1]

            if hasattr(model, "fit"):
                model.fit(X_train, y_train)

            # Stage 4: Validate
            result.stage = PipelineStage.MODEL_VALIDATION
            logger.info(f"[{run_id}] Stage 3: Model Validation")

            X_val = val_features.iloc[:, :-1]
            y_val = val_features.iloc[:, -1]

            if hasattr(model, "predict"):
                predictions = model.predict(X_val)

                # Compute metrics
                from sklearn.metrics import mean_absolute_error, mean_squared_error

                result.metrics = {
                    "mse": mean_squared_error(y_val, predictions),
                    "mae": mean_absolute_error(y_val, predictions),
                    "samples_train": len(X_train),
                    "samples_val": len(X_val),
                }

            # Stage 5: Deploy
            result.stage = PipelineStage.MODEL_DEPLOYMENT
            self.inference_pipeline.set_champion_model(model)

            # Complete
            result.status = PipelineStatus.COMPLETED
            result.completed_at = datetime.now(UTC)
            result.duration_seconds = (result.completed_at - start_time).total_seconds()
            result.output = model

            logger.info(f"[{run_id}] Pipeline completed in {result.duration_seconds:.2f}s")

        except Exception as e:
            result.status = PipelineStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now(UTC)
            logger.error(f"[{run_id}] Pipeline failed: {e}")

        self._runs.append(result)
        self._current_run = None

        return result

    async def run_inference(
        self,
        data: pd.DataFrame | dict[str, Any],
        feature_names: list[str],
    ) -> dict[str, Any]:
        """
        Run inference with automatic feature computation.

        Args:
            data: Raw data or pre-computed features
            feature_names: Features to compute if needed

        Returns:
            Prediction result
        """
        # Compute features if needed
        if isinstance(data, pd.DataFrame):
            features = await self.feature_pipeline.get_features(data, feature_names)
        else:
            features = data

        return await self.inference_pipeline.predict(features)

    def get_pipeline_status(self) -> dict[str, Any]:
        """Get current pipeline status."""
        return {
            "current_run": {
                "run_id": self._current_run.run_id,
                "stage": self._current_run.stage.value,
                "status": self._current_run.status.value,
            } if self._current_run else None,
            "recent_runs": [
                {
                    "run_id": r.run_id,
                    "status": r.status.value,
                    "duration_seconds": r.duration_seconds,
                    "metrics": r.metrics,
                }
                for r in self._runs[-10:]
            ],
            "feature_cache_size": len(self.feature_pipeline._cache),
            "champion_model_loaded": self.inference_pipeline._champion_model is not None,
            "challenger_model_loaded": self.inference_pipeline._challenger_model is not None,
        }


# Factory function

def create_pipeline(
    feature_cache_ttl: int = 3600,
    enable_ab_testing: bool = False,
) -> PipelineOrchestrator:
    """
    Create a configured pipeline orchestrator.

    Args:
        feature_cache_ttl: Feature cache TTL in seconds
        enable_ab_testing: Whether to enable A/B testing

    Returns:
        Configured PipelineOrchestrator
    """
    config = PipelineConfig(
        feature_cache_ttl_seconds=feature_cache_ttl,
        enable_ab_testing=enable_ab_testing,
    )

    return PipelineOrchestrator(config)
