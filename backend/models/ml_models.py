"""
ML Models Pydantic Models
Comprehensive data models for ML model management API
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ModelType(str, Enum):
    """Supported model types."""
    ENSEMBLE = "ensemble"
    LSTM = "lstm"
    XGBOOST = "xgboost"
    RANDOM_FOREST = "random_forest"
    REGRESSION = "regression"
    CLASSIFICATION = "classification"


class ModelStatus(str, Enum):
    """Model status states."""
    TRAINING = "training"
    READY = "ready"
    FAILED = "failed"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"


class TrainingStatus(str, Enum):
    """Training job status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ==================== REQUEST MODELS ====================

class ModelTrainingRequest(BaseModel):
    """Request to train a new model."""
    model_config = ConfigDict(protected_namespaces=())

    model_type: ModelType = Field(..., description="Type of model to train")
    model_name: str = Field(..., min_length=1, max_length=100, description="Unique model name")
    features: list[str] = Field(
        default_factory=lambda: ["technical", "sentiment"],
        description="Features to use for training"
    )
    symbols: list[str] = Field(
        default_factory=lambda: ["AAPL", "MSFT", "GOOGL"],
        description="Symbols to train on"
    )
    lookback_days: int = Field(default=90, ge=30, le=365, description="Days of historical data")
    test_size: float = Field(default=0.2, ge=0.1, le=0.4, description="Test set proportion")
    hyperparameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Model-specific hyperparameters"
    )
    retrain: bool = Field(default=False, description="Retrain existing model")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model_type": "ensemble",
                "model_name": "price_predictor_v1",
                "features": ["technical", "sentiment", "volume"],
                "symbols": ["AAPL", "MSFT"],
                "lookback_days": 90,
                "test_size": 0.2,
                "hyperparameters": {
                    "lstm_units": 128,
                    "xgboost_n_estimators": 100
                },
                "retrain": False
            }
        }
    )


class ModelActivationRequest(BaseModel):
    """Request to activate/deactivate a model."""
    active: bool = Field(..., description="Whether to activate or deactivate")


class ModelComparisonRequest(BaseModel):
    """Request to compare multiple models."""
    model_ids: list[UUID] = Field(..., min_length=2, max_length=5, description="Model IDs to compare")
    metric: str = Field(default="accuracy", description="Primary metric for comparison")


class PredictionRequest(BaseModel):
    """Request for model prediction."""
    symbol: str = Field(..., min_length=1, max_length=10, description="Symbol to predict")
    model_id: UUID | None = Field(None, description="Specific model ID (uses active if not provided)")
    data: dict[str, Any] = Field(default_factory=dict, description="Input features")


# ==================== RESPONSE MODELS ====================

class ModelMetrics(BaseModel):
    """Model performance metrics."""

    # Classification metrics
    accuracy: float | None = Field(None, ge=0, le=1, description="Classification accuracy")
    precision: float | None = Field(None, ge=0, le=1, description="Precision score")
    recall: float | None = Field(None, ge=0, le=1, description="Recall score")
    f1_score: float | None = Field(None, ge=0, le=1, description="F1 score")

    # Regression metrics
    mae: float | None = Field(None, ge=0, description="Mean Absolute Error")
    rmse: float | None = Field(None, ge=0, description="Root Mean Squared Error")
    r2_score: float | None = Field(None, description="R² score")
    mape: float | None = Field(None, ge=0, description="Mean Absolute Percentage Error")

    # Additional metrics
    training_time: float | None = Field(None, ge=0, description="Training time in seconds")
    inference_time: float | None = Field(None, ge=0, description="Average inference time in ms")

    # Custom metrics
    custom_metrics: dict[str, Any] = Field(default_factory=dict, description="Additional custom metrics")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "accuracy": 0.85,
                "precision": 0.83,
                "recall": 0.87,
                "f1_score": 0.85,
                "mae": 1.23,
                "rmse": 1.87,
                "r2_score": 0.92,
                "training_time": 245.5,
                "inference_time": 12.3
            }
        }
    )


class FeatureImportance(BaseModel):
    """Feature importance information."""
    feature_name: str = Field(..., description="Name of the feature")
    importance: float = Field(..., ge=0, le=1, description="Importance score")
    rank: int = Field(..., ge=1, description="Rank by importance")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "feature_name": "RSI_14",
                "importance": 0.23,
                "rank": 1
            }
        }
    )


class DriftMetrics(BaseModel):
    """Model drift detection metrics."""
    psi_score: float = Field(..., ge=0, description="Population Stability Index")
    drift_detected: bool = Field(..., description="Whether significant drift was detected")
    affected_features: list[str] = Field(default_factory=list, description="Features with drift")
    drift_severity: str = Field(..., description="low, medium, high")
    last_checked: datetime = Field(..., description="Last drift check timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "psi_score": 0.15,
                "drift_detected": True,
                "affected_features": ["volume", "volatility"],
                "drift_severity": "medium",
                "last_checked": "2025-10-15T22:00:00Z"
            }
        }
    )


class ModelInfo(BaseModel):
    """Comprehensive model information."""
    model_config = ConfigDict(protected_namespaces=())

    # Identity
    id: UUID = Field(..., description="Model unique identifier")
    name: str = Field(..., description="Model name")
    version: str = Field(..., description="Model version")
    model_type: ModelType = Field(..., description="Type of model")

    # Status
    status: ModelStatus = Field(..., description="Current model status")
    active: bool = Field(..., description="Whether model is active for predictions")

    # Metadata
    path: str = Field(..., description="Storage path for model artifacts")
    trained_at: datetime = Field(..., description="Training completion timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    # Performance
    metrics: ModelMetrics = Field(..., description="Performance metrics")

    # Configuration
    features: list[str] = Field(default_factory=list, description="Features used")
    symbols: list[str] = Field(default_factory=list, description="Symbols trained on")
    hyperparameters: dict[str, Any] = Field(default_factory=dict, description="Model hyperparameters")

    # Statistics
    prediction_count: int = Field(default=0, ge=0, description="Total predictions made")
    avg_confidence: float | None = Field(None, ge=0, le=1, description="Average prediction confidence")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "price_predictor_v1",
                "version": "1.0.0",
                "model_type": "ensemble",
                "status": "ready",
                "active": True,
                "path": "/models/price_predictor_v1",
                "trained_at": "2025-10-15T20:00:00Z",
                "created_at": "2025-10-15T19:00:00Z",
                "updated_at": "2025-10-15T20:00:00Z",
                "metrics": {
                    "accuracy": 0.85,
                    "precision": 0.83,
                    "recall": 0.87,
                    "f1_score": 0.85
                },
                "features": ["RSI", "MACD", "volume"],
                "symbols": ["AAPL", "MSFT"],
                "prediction_count": 1523,
                "avg_confidence": 0.78
            }
        }
    )


class ModelListResponse(BaseModel):
    """List of models with pagination."""
    models: list[ModelInfo] = Field(..., description="List of models")
    total: int = Field(..., ge=0, description="Total number of models")
    page: int = Field(default=1, ge=1, description="Current page")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


class TrainingProgress(BaseModel):
    """Training progress information."""
    training_id: str = Field(..., description="Training job ID")
    status: TrainingStatus = Field(..., description="Training status")
    progress: float = Field(..., ge=0, le=1, description="Progress percentage (0-1)")
    current_epoch: int | None = Field(None, ge=0, description="Current epoch")
    total_epochs: int | None = Field(None, ge=1, description="Total epochs")
    current_metrics: dict[str, float] = Field(default_factory=dict, description="Current epoch metrics")
    eta_seconds: int | None = Field(None, ge=0, description="Estimated time to completion")
    started_at: datetime = Field(..., description="Training start time")
    message: str | None = Field(None, description="Status message")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "training_id": "train_123456",
                "status": "running",
                "progress": 0.65,
                "current_epoch": 65,
                "total_epochs": 100,
                "current_metrics": {
                    "loss": 0.234,
                    "accuracy": 0.82
                },
                "eta_seconds": 420,
                "started_at": "2025-10-15T22:00:00Z",
                "message": "Training in progress..."
            }
        }
    )


class TrainingResponse(BaseModel):
    """Response when starting model training."""
    training_id: str = Field(..., description="Unique training job ID")
    model_name: str = Field(..., description="Model being trained")
    status: TrainingStatus = Field(..., description="Initial status")
    message: str = Field(..., description="Confirmation message")
    started_at: datetime = Field(..., description="Training start time")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "training_id": "train_123456",
                "model_name": "price_predictor_v1",
                "status": "pending",
                "message": "Training job queued successfully",
                "started_at": "2025-10-15T22:00:00Z"
            }
        }
    )


class ModelComparisonResult(BaseModel):
    """Result of comparing multiple models."""
    models: list[ModelInfo] = Field(..., description="Models being compared")
    best_model_id: UUID = Field(..., description="ID of best performing model")
    comparison_metric: str = Field(..., description="Metric used for comparison")
    metrics_comparison: dict[str, dict[str, float]] = Field(
        ...,
        description="Metrics for each model"
    )
    recommendations: list[str] = Field(default_factory=list, description="Recommendations")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "models": [],
                "best_model_id": "123e4567-e89b-12d3-a456-426614174000",
                "comparison_metric": "accuracy",
                "metrics_comparison": {
                    "model_1": {"accuracy": 0.85, "f1": 0.83},
                    "model_2": {"accuracy": 0.82, "f1": 0.80}
                },
                "recommendations": [
                    "Model 1 performs better on accuracy",
                    "Consider ensemble approach"
                ]
            }
        }
    )


class PredictionResponse(BaseModel):
    """Model prediction response."""
    symbol: str = Field(..., description="Symbol predicted")
    prediction: float = Field(..., description="Predicted value")
    confidence: float = Field(..., ge=0, le=1, description="Prediction confidence")
    model_id: UUID = Field(..., description="Model used for prediction")
    model_name: str = Field(..., description="Model name")
    features_used: list[str] = Field(default_factory=list, description="Features used")
    timestamp: datetime = Field(..., description="Prediction timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "AAPL",
                "prediction": 185.50,
                "confidence": 0.82,
                "model_id": "123e4567-e89b-12d3-a456-426614174000",
                "model_name": "price_predictor_v1",
                "features_used": ["RSI", "MACD", "volume"],
                "timestamp": "2025-10-15T22:30:00Z"
            }
        }
    )


class ModelHealthResponse(BaseModel):
    """Model health check response."""
    model_id: UUID = Field(..., description="Model ID")
    model_name: str = Field(..., description="Model name")
    health_score: float = Field(..., ge=0, le=1, description="Overall health score (0-1)")
    status: ModelStatus = Field(..., description="Model status")
    drift_metrics: DriftMetrics | None = Field(None, description="Drift detection metrics")
    recent_performance: dict[str, float] = Field(
        default_factory=dict,
        description="Recent performance metrics"
    )
    issues: list[str] = Field(default_factory=list, description="Detected issues")
    recommendations: list[str] = Field(default_factory=list, description="Health recommendations")
    last_checked: datetime = Field(..., description="Last health check timestamp")


class MonitoringSnapshot(BaseModel):
    """A persisted monitoring snapshot for a model."""

    id: UUID = Field(..., description="Snapshot ID")
    model_id: UUID | None = Field(None, description="Related model registry ID")
    model_name: str = Field(..., description="Model name")
    model_version: str = Field(..., description="Model version")
    window_start: datetime = Field(..., description="Evaluation window start")
    window_end: datetime = Field(..., description="Evaluation window end")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Performance metrics")
    drift: dict[str, Any] = Field(default_factory=dict, description="Drift metrics")
    created_at: datetime = Field(..., description="Snapshot creation time")


class MonitoringSnapshotListResponse(BaseModel):
    model_id: UUID = Field(..., description="Model registry ID")
    snapshots: list[MonitoringSnapshot] = Field(..., description="Snapshots")


class MonitoringRunResponse(BaseModel):
    snapshot: MonitoringSnapshot = Field(..., description="Created snapshot")


class RetrainIfNeededRequest(BaseModel):
    lookback_days: int = Field(default=60, ge=30, le=365, description="Days of market data for monitoring")
    min_return_drop: float = Field(default=0.02, ge=0.0, le=1.0, description="Minimum drop vs reference to trigger retrain")
    psi_threshold: float = Field(default=0.15, ge=0.0, le=1.0, description="PSI threshold to trigger retrain")


class RetrainIfNeededResponse(BaseModel):
    should_retrain: bool = Field(..., description="Whether retraining was triggered")
    reasons: list[str] = Field(default_factory=list, description="Reasons for retrain")
    training_id: str | None = Field(None, description="Training job ID if enqueued")
    snapshot: MonitoringSnapshot | None = Field(None, description="Latest monitoring snapshot")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model_id": "123e4567-e89b-12d3-a456-426614174000",
                "model_name": "price_predictor_v1",
                "health_score": 0.85,
                "status": "ready",
                "drift_metrics": None,
                "recent_performance": {
                    "accuracy": 0.83,
                    "latency_ms": 12.5
                },
                "issues": [],
                "recommendations": [
                    "Model performing well",
                    "No action required"
                ],
                "last_checked": "2025-10-15T22:00:00Z"
            }
        }
    )


class LifecycleModelSummary(BaseModel):
    model_id: UUID = Field(..., description="Model registry ID")
    model_name: str = Field(..., description="Model name")
    model_version: str = Field(..., description="Model version")
    active: bool = Field(..., description="Whether active")
    last_snapshot: MonitoringSnapshot | None = Field(None, description="Latest monitoring snapshot")
    last_retrain_decision: dict[str, Any] | None = Field(None, description="Latest retrain decision event payload")


class LifecycleSummaryResponse(BaseModel):
    scheduler_enabled: bool = Field(..., description="Whether in-process scheduler is enabled")
    scheduler_state: dict[str, Any] = Field(default_factory=dict, description="Scheduler next run times/state")
    active_models: list[LifecycleModelSummary] = Field(default_factory=list, description="Active models")
    last_promotion_review: dict[str, Any] | None = Field(None, description="Latest promotion review payload")


class LifecycleRunResponse(BaseModel):
    ok: bool = Field(..., description="Whether job completed")
    message: str = Field(..., description="Human summary")
    details: dict[str, Any] = Field(default_factory=dict, description="Job details")


class FeatureImportanceResponse(BaseModel):
    """Feature importance analysis response."""
    model_id: UUID = Field(..., description="Model ID")
    model_name: str = Field(..., description="Model name")
    features: list[FeatureImportance] = Field(..., description="Feature importance rankings")
    generated_at: datetime = Field(..., description="Generation timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model_id": "123e4567-e89b-12d3-a456-426614174000",
                "model_name": "price_predictor_v1",
                "features": [
                    {"feature_name": "RSI_14", "importance": 0.23, "rank": 1},
                    {"feature_name": "MACD", "importance": 0.18, "rank": 2}
                ],
                "generated_at": "2025-10-15T22:00:00Z"
            }
        }
    )


class ModelVersionInfo(BaseModel):
    """Model version history information."""
    version: str = Field(..., description="Version identifier")
    trained_at: datetime = Field(..., description="Training timestamp")
    metrics: ModelMetrics = Field(..., description="Version metrics")
    active: bool = Field(..., description="Whether this version is active")
    notes: str | None = Field(None, description="Version notes")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "version": "1.0.0",
                "trained_at": "2025-10-15T20:00:00Z",
                "metrics": {"accuracy": 0.85},
                "active": True,
                "notes": "Initial production version"
            }
        }
    )


class ModelVersionHistoryResponse(BaseModel):
    """Model version history response."""
    model_name: str = Field(..., description="Model name")
    versions: list[ModelVersionInfo] = Field(..., description="Version history")
    current_version: str = Field(..., description="Currently active version")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model_name": "price_predictor",
                "versions": [],
                "current_version": "1.0.0"
            }
        }
    )
