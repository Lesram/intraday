"""
Module 57: ML Model Management System
Comprehensive model lifecycle management for machine learning workflows.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json
import logging
from pathlib import Path
import pickle
from typing import Any

import joblib
import numpy as np

from ..utils.secure_pickle import secure_load


class ModelStatus(Enum):
    """Model status enumeration."""
    REGISTERED = "registered"
    TRAINING = "training"
    TRAINED = "trained"
    DEPLOYED = "deployed"
    RETIRED = "retired"
    FAILED = "failed"


class ModelFormat(Enum):
    """Model serialization format."""
    JOBLIB = "joblib"
    PICKLE = "pickle"
    JSON = "json"


@dataclass
class ModelMetadata:
    """Model metadata structure."""
    name: str
    version: str
    model_type: str
    status: ModelStatus
    created_at: datetime
    updated_at: datetime
    description: str = ""
    tags: list[str] = None
    metrics: dict[str, float] = None
    parameters: dict[str, Any] = None
    file_path: str | None = None
    file_size: int | None = None
    checksum: str | None = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.metrics is None:
            self.metrics = {}
        if self.parameters is None:
            self.parameters = {}


@dataclass
class ModelPerformance:
    """Model performance tracking."""
    model_name: str
    version: str
    timestamp: datetime
    metrics: dict[str, float]
    dataset_info: dict[str, Any] = None

    def __post_init__(self):
        if self.dataset_info is None:
            self.dataset_info = {}


class ModelRegistry:
    """Central model registry for metadata management."""

    def __init__(self, registry_path: str = "models/registry.json"):
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.models = self._load_registry()

    def _load_registry(self) -> dict[str, dict]:
        """Load model registry from file."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path) as f:
                    data = json.load(f)
                    # Convert datetime strings back to datetime objects
                    for model_data in data.values():
                        if isinstance(model_data.get('created_at'), str):
                            model_data['created_at'] = datetime.fromisoformat(model_data['created_at'])
                        if isinstance(model_data.get('updated_at'), str):
                            model_data['updated_at'] = datetime.fromisoformat(model_data['updated_at'])
                        if isinstance(model_data.get('status'), str):
                            model_data['status'] = ModelStatus(model_data['status'])
                    return data
            except Exception as e:
                logging.warning(f"Failed to load registry: {e}")
        return {}

    def _save_registry(self):
        """Save model registry to file."""
        try:
            # Convert datetime and enum objects for JSON serialization
            data = {}
            for key, model_data in self.models.items():
                data[key] = model_data.copy()
                if isinstance(data[key].get('created_at'), datetime):
                    data[key]['created_at'] = data[key]['created_at'].isoformat()
                if isinstance(data[key].get('updated_at'), datetime):
                    data[key]['updated_at'] = data[key]['updated_at'].isoformat()
                if isinstance(data[key].get('status'), ModelStatus):
                    data[key]['status'] = data[key]['status'].value

            with open(self.registry_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to save registry: {e}")

    def register_model(self, metadata: ModelMetadata) -> bool:
        """Register a model in the registry."""
        try:
            key = f"{metadata.name}:{metadata.version}"
            self.models[key] = asdict(metadata)
            self._save_registry()
            return True
        except Exception:
            return False

    def get_model_metadata(self, name: str, version: str = None) -> ModelMetadata | None:
        """Get model metadata."""
        if version:
            key = f"{name}:{version}"
            if key in self.models:
                data = self.models[key].copy()
                return ModelMetadata(**data)
        else:
            # Get latest version
            matching_models = [(k, v) for k, v in self.models.items() if k.startswith(f"{name}:")]
            if matching_models:
                # Sort by version (simple string comparison for now)
                latest = max(matching_models, key=lambda x: x[0])
                return ModelMetadata(**latest[1])
        return None

    def list_models(self, status: ModelStatus = None) -> list[ModelMetadata]:
        """List all models or filter by status."""
        models = []
        for model_data in self.models.values():
            metadata = ModelMetadata(**model_data)
            if status is None or metadata.status == status:
                models.append(metadata)
        return models

    def update_model_status(self, name: str, version: str, status: ModelStatus) -> bool:
        """Update model status."""
        key = f"{name}:{version}"
        if key in self.models:
            self.models[key]['status'] = status
            self.models[key]['updated_at'] = datetime.now()
            self._save_registry()
            return True
        return False

    def delete_model(self, name: str, version: str) -> bool:
        """Delete model from registry."""
        key = f"{name}:{version}"
        if key in self.models:
            del self.models[key]
            self._save_registry()
            return True
        return False


class ModelStorage:
    """Model file storage management."""

    def __init__(self, storage_path: str = "models/storage"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _get_model_path(self, name: str, version: str, format_type: ModelFormat) -> Path:
        """Get the file path for a model."""
        filename = f"{name}_v{version}.{format_type.value}"
        return self.storage_path / filename

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate file checksum."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def save_model(self, model: Any, name: str, version: str,
                   format_type: ModelFormat = ModelFormat.JOBLIB) -> tuple[bool, str | None, int | None]:
        """Save model to storage."""
        try:
            file_path = self._get_model_path(name, version, format_type)

            if format_type == ModelFormat.JOBLIB:
                joblib.dump(model, file_path)
            elif format_type == ModelFormat.PICKLE:
                with open(file_path, 'wb') as f:
                    pickle.dump(model, f)
            elif format_type == ModelFormat.JSON:
                # For simple models that can be serialized to JSON
                with open(file_path, 'w') as f:
                    json.dump(model, f, indent=2)

            file_size = file_path.stat().st_size
            self._calculate_checksum(file_path)

            return True, str(file_path), file_size
        except Exception as e:
            logging.error(f"Failed to save model: {e}")
            return False, None, None

    def load_model(self, name: str, version: str,
                   format_type: ModelFormat = ModelFormat.JOBLIB) -> Any | None:
        """Load model from storage with secure pickle verification."""
        try:
            file_path = self._get_model_path(name, version, format_type)

            if not file_path.exists():
                return None

            if format_type == ModelFormat.JOBLIB:
                return joblib.load(file_path)
            elif format_type == ModelFormat.PICKLE:
                with open(file_path, 'rb') as f:
                    # Use secure pickle with migration support
                    return secure_load(f)
            elif format_type == ModelFormat.JSON:
                with open(file_path) as f:
                    return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load model: {e}")
            return None

    def delete_model_file(self, name: str, version: str, format_type: ModelFormat) -> bool:
        """Delete model file from storage."""
        try:
            file_path = self._get_model_path(name, version, format_type)
            if file_path.exists():
                file_path.unlink()
                return True
        except Exception:
            pass
        return False

    def list_model_files(self) -> list[dict[str, Any]]:
        """List all model files in storage."""
        files = []
        for file_path in self.storage_path.glob("*"):
            if file_path.is_file():
                files.append({
                    'name': file_path.name,
                    'size': file_path.stat().st_size,
                    'modified': datetime.fromtimestamp(file_path.stat().st_mtime),
                    'path': str(file_path)
                })
        return files


class PerformanceTracker:
    """Model performance tracking and monitoring."""

    def __init__(self, tracking_path: str = "models/performance.json"):
        self.tracking_path = Path(tracking_path)
        self.tracking_path.parent.mkdir(parents=True, exist_ok=True)
        self.performance_data = self._load_performance_data()

    def _load_performance_data(self) -> list[dict]:
        """Load performance data from file."""
        if self.tracking_path.exists():
            try:
                with open(self.tracking_path) as f:
                    data = json.load(f)
                    # Convert timestamp strings back to datetime objects
                    for entry in data:
                        if isinstance(entry.get('timestamp'), str):
                            entry['timestamp'] = datetime.fromisoformat(entry['timestamp'])
                    return data
            except Exception:
                pass
        return []

    def _save_performance_data(self):
        """Save performance data to file."""
        try:
            # Convert datetime objects for JSON serialization
            data = []
            for entry in self.performance_data:
                entry_copy = entry.copy()
                if isinstance(entry_copy.get('timestamp'), datetime):
                    entry_copy['timestamp'] = entry_copy['timestamp'].isoformat()
                data.append(entry_copy)

            with open(self.tracking_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to save performance data: {e}")

    def log_performance(self, performance: ModelPerformance):
        """Log model performance metrics."""
        self.performance_data.append(asdict(performance))
        self._save_performance_data()

    def get_performance_history(self, model_name: str,
                              days: int = 30) -> list[ModelPerformance]:
        """Get performance history for a model."""
        cutoff_date = datetime.now() - timedelta(days=days)
        history = []

        for entry in self.performance_data:
            if (entry['model_name'] == model_name and
                entry['timestamp'] >= cutoff_date):
                history.append(ModelPerformance(**entry))

        return sorted(history, key=lambda x: x.timestamp)

    def get_model_metrics_summary(self, model_name: str) -> dict[str, Any]:
        """Get summary statistics for model metrics."""
        model_data = [entry for entry in self.performance_data
                     if entry['model_name'] == model_name]

        if not model_data:
            return {}

        # Aggregate metrics
        all_metrics = {}
        for entry in model_data:
            for metric, value in entry['metrics'].items():
                if metric not in all_metrics:
                    all_metrics[metric] = []
                all_metrics[metric].append(value)

        summary = {}
        for metric, values in all_metrics.items():
            summary[metric] = {
                'mean': np.mean(values),
                'std': np.std(values),
                'min': np.min(values),
                'max': np.max(values),
                'latest': values[-1] if values else None,
                'count': len(values)
            }

        return summary


class ModelManager:
    """Main model management orchestrator."""

    def __init__(self, base_path: str = "models"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        self.registry = ModelRegistry(str(self.base_path / "registry.json"))
        self.storage = ModelStorage(str(self.base_path / "storage"))
        self.performance_tracker = PerformanceTracker(str(self.base_path / "performance.json"))

        self.active_models = {}  # In-memory cache of loaded models

    def register_model(self, model: Any, name: str, version: str,
                      model_type: str = "unknown", description: str = "",
                      tags: list[str] = None, parameters: dict[str, Any] = None,
                      format_type: ModelFormat = ModelFormat.JOBLIB) -> bool:
        """Register and save a new model."""
        try:
            # Save model to storage
            success, file_path, file_size = self.storage.save_model(
                model, name, version, format_type
            )

            if not success:
                return False

            # Create metadata
            metadata = ModelMetadata(
                name=name,
                version=version,
                model_type=model_type,
                status=ModelStatus.REGISTERED,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                description=description,
                tags=tags or [],
                parameters=parameters or {},
                file_path=file_path,
                file_size=file_size
            )

            # Register in registry
            return self.registry.register_model(metadata)

        except Exception as e:
            logging.error(f"Failed to register model: {e}")
            return False

    def load_model(self, name: str, version: str = None,
                   format_type: ModelFormat = ModelFormat.JOBLIB) -> Any | None:
        """Load a model from storage."""
        # Get metadata to find the correct version
        metadata = self.registry.get_model_metadata(name, version)
        if not metadata:
            return None

        # Check if already loaded in cache
        cache_key = f"{metadata.name}:{metadata.version}"
        if cache_key in self.active_models:
            return self.active_models[cache_key]

        # Load from storage
        model = self.storage.load_model(metadata.name, metadata.version, format_type)
        if model is not None:
            self.active_models[cache_key] = model

        return model

    def deploy_model(self, name: str, version: str = None) -> bool:
        """Deploy a model (mark as deployed)."""
        metadata = self.registry.get_model_metadata(name, version)
        if metadata:
            return self.registry.update_model_status(
                metadata.name, metadata.version, ModelStatus.DEPLOYED
            )
        return False

    def retire_model(self, name: str, version: str) -> bool:
        """Retire a model."""
        return self.registry.update_model_status(name, version, ModelStatus.RETIRED)

    def delete_model(self, name: str, version: str,
                     format_type: ModelFormat = ModelFormat.JOBLIB) -> bool:
        """Completely delete a model."""
        # Remove from cache
        cache_key = f"{name}:{version}"
        if cache_key in self.active_models:
            del self.active_models[cache_key]

        # Delete file
        self.storage.delete_model_file(name, version, format_type)

        # Remove from registry
        return self.registry.delete_model(name, version)

    def list_models(self, status: ModelStatus = None) -> list[ModelMetadata]:
        """List all models."""
        return self.registry.list_models(status)

    def get_model_info(self, name: str, version: str = None) -> ModelMetadata | None:
        """Get detailed model information."""
        return self.registry.get_model_metadata(name, version)

    def log_model_performance(self, name: str, version: str,
                            metrics: dict[str, float],
                            dataset_info: dict[str, Any] = None):
        """Log model performance metrics."""
        performance = ModelPerformance(
            model_name=name,
            version=version,
            timestamp=datetime.now(),
            metrics=metrics,
            dataset_info=dataset_info or {}
        )
        self.performance_tracker.log_performance(performance)

    def get_model_performance_history(self, name: str, days: int = 30) -> list[ModelPerformance]:
        """Get model performance history."""
        return self.performance_tracker.get_performance_history(name, days)

    def get_model_metrics_summary(self, name: str) -> dict[str, Any]:
        """Get model performance summary."""
        return self.performance_tracker.get_model_metrics_summary(name)

    def cleanup_cache(self):
        """Clear the model cache."""
        self.active_models.clear()

    def get_storage_info(self) -> dict[str, Any]:
        """Get storage information."""
        files = self.storage.list_model_files()
        total_size = sum(f['size'] for f in files)

        return {
            'total_files': len(files),
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'files': files
        }


# Example utility functions for common ML model types
def create_sample_sklearn_model():
    """Create a sample sklearn model for testing."""
    from sklearn.datasets import make_regression
    from sklearn.linear_model import LinearRegression

    X, y = make_regression(n_samples=100, n_features=5, noise=0.1, random_state=42)
    model = LinearRegression()
    model.fit(X, y)
    return model, X, y


def create_sample_model_data():
    """Create sample data for model testing."""
    return {
        'accuracy': 0.95,
        'precision': 0.93,
        'recall': 0.91,
        'f1_score': 0.92
    }
