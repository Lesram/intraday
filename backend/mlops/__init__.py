"""
MLOps Registry and Drift Detection Module (Branch 2.6)

Provides on-disk model registry with artifacts/{model_name}/{version}/ structure,
Population Stability Index (PSI) drift detection, feature schema validation,
and inference telemetry integration.
"""

from .model_manager import (
    DriftDetection,
    DriftDetector,
    DriftType,
    ModelManager,
    ModelMonitoring,
    ModelRegistry,
    ModelStatus,
    ModelVersion,
    NoopModel,
    SchemaMismatchError,
    detect_data_drift,
    get_champion_model,
    get_model_manager,
    register_model,
)

__all__ = [
    "ModelManager",
    "ModelRegistry",
    "DriftDetector",
    "ModelVersion",
    "ModelStatus",
    "DriftType",
    "DriftDetection",
    "ModelMonitoring",
    "NoopModel",
    "SchemaMismatchError",
    "get_model_manager",
    "register_model",
    "get_champion_model",
    "detect_data_drift",
]
