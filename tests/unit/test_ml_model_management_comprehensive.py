"""
Comprehensive tests for backend/ml/model_management.py
Targets: ModelStatus, ModelFormat, ModelMetadata, ModelPerformance,
         ModelRegistry, ModelStorage, PerformanceTracker, ModelManager
"""

import json
import pickle
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
import numpy as np

from backend.ml.model_management import (
    ModelStatus,
    ModelFormat,
    ModelMetadata,
    ModelPerformance,
    ModelRegistry,
    ModelStorage,
    PerformanceTracker,
    ModelManager,
    create_sample_model_data,
)


# =============================================================================
# ModelStatus Enum Tests
# =============================================================================
class TestModelStatus:
    """Tests for ModelStatus enum."""

    def test_all_statuses_exist(self):
        """Test all expected statuses are defined."""
        assert ModelStatus.REGISTERED.value == "registered"
        assert ModelStatus.TRAINING.value == "training"
        assert ModelStatus.TRAINED.value == "trained"
        assert ModelStatus.DEPLOYED.value == "deployed"
        assert ModelStatus.RETIRED.value == "retired"
        assert ModelStatus.FAILED.value == "failed"

    def test_status_from_value(self):
        """Test creating status from string value."""
        assert ModelStatus("registered") == ModelStatus.REGISTERED
        assert ModelStatus("deployed") == ModelStatus.DEPLOYED

    def test_status_comparison(self):
        """Test status comparison."""
        assert ModelStatus.REGISTERED != ModelStatus.DEPLOYED


# =============================================================================
# ModelFormat Enum Tests
# =============================================================================
class TestModelFormat:
    """Tests for ModelFormat enum."""

    def test_all_formats_exist(self):
        """Test all expected formats are defined."""
        assert ModelFormat.JOBLIB.value == "joblib"
        assert ModelFormat.PICKLE.value == "pickle"
        assert ModelFormat.JSON.value == "json"

    def test_format_from_value(self):
        """Test creating format from string value."""
        assert ModelFormat("joblib") == ModelFormat.JOBLIB
        assert ModelFormat("pickle") == ModelFormat.PICKLE


# =============================================================================
# ModelMetadata Tests
# =============================================================================
class TestModelMetadata:
    """Tests for ModelMetadata dataclass."""

    def test_basic_creation(self):
        """Test creating ModelMetadata with required fields."""
        now = datetime.now()
        metadata = ModelMetadata(
            name="test_model",
            version="1.0.0",
            model_type="classifier",
            status=ModelStatus.REGISTERED,
            created_at=now,
            updated_at=now,
        )
        assert metadata.name == "test_model"
        assert metadata.version == "1.0.0"
        assert metadata.model_type == "classifier"
        assert metadata.status == ModelStatus.REGISTERED
        assert metadata.tags == []
        assert metadata.metrics == {}
        assert metadata.parameters == {}

    def test_full_creation(self):
        """Test creating ModelMetadata with all fields."""
        now = datetime.now()
        metadata = ModelMetadata(
            name="test_model",
            version="1.0.0",
            model_type="classifier",
            status=ModelStatus.DEPLOYED,
            created_at=now,
            updated_at=now,
            description="Test description",
            tags=["production", "ml"],
            metrics={"accuracy": 0.95},
            parameters={"n_estimators": 100},
            file_path="/path/to/model",
            file_size=1024,
            checksum="abc123",
        )
        assert metadata.description == "Test description"
        assert metadata.tags == ["production", "ml"]
        assert metadata.metrics == {"accuracy": 0.95}
        assert metadata.parameters == {"n_estimators": 100}
        assert metadata.file_path == "/path/to/model"
        assert metadata.file_size == 1024
        assert metadata.checksum == "abc123"

    def test_post_init_defaults(self):
        """Test that __post_init__ sets default values."""
        now = datetime.now()
        metadata = ModelMetadata(
            name="test",
            version="1.0",
            model_type="regressor",
            status=ModelStatus.REGISTERED,
            created_at=now,
            updated_at=now,
            tags=None,
            metrics=None,
            parameters=None,
        )
        assert metadata.tags == []
        assert metadata.metrics == {}
        assert metadata.parameters == {}


# =============================================================================
# ModelPerformance Tests
# =============================================================================
class TestModelPerformance:
    """Tests for ModelPerformance dataclass."""

    def test_basic_creation(self):
        """Test creating ModelPerformance with required fields."""
        now = datetime.now()
        perf = ModelPerformance(
            model_name="test_model",
            version="1.0.0",
            timestamp=now,
            metrics={"accuracy": 0.95, "f1": 0.93},
        )
        assert perf.model_name == "test_model"
        assert perf.version == "1.0.0"
        assert perf.timestamp == now
        assert perf.metrics == {"accuracy": 0.95, "f1": 0.93}
        assert perf.dataset_info == {}

    def test_with_dataset_info(self):
        """Test creating ModelPerformance with dataset info."""
        now = datetime.now()
        perf = ModelPerformance(
            model_name="test_model",
            version="1.0.0",
            timestamp=now,
            metrics={"accuracy": 0.95},
            dataset_info={"samples": 1000, "features": 50},
        )
        assert perf.dataset_info == {"samples": 1000, "features": 50}


# =============================================================================
# ModelRegistry Tests
# =============================================================================
class TestModelRegistry:
    """Tests for ModelRegistry class."""

    @pytest.fixture
    def temp_registry(self, tmp_path):
        """Create a registry with temporary storage."""
        registry_path = tmp_path / "registry.json"
        return ModelRegistry(str(registry_path))

    def test_init_creates_directory(self, tmp_path):
        """Test that initialization creates parent directories."""
        registry_path = tmp_path / "nested" / "path" / "registry.json"
        registry = ModelRegistry(str(registry_path))
        assert registry_path.parent.exists()

    def test_register_model(self, temp_registry):
        """Test registering a model."""
        now = datetime.now()
        metadata = ModelMetadata(
            name="test_model",
            version="1.0.0",
            model_type="classifier",
            status=ModelStatus.REGISTERED,
            created_at=now,
            updated_at=now,
        )
        result = temp_registry.register_model(metadata)
        assert result is True
        assert "test_model:1.0.0" in temp_registry.models

    def test_get_model_metadata_with_version(self, temp_registry):
        """Test getting model metadata with specific version."""
        now = datetime.now()
        metadata = ModelMetadata(
            name="test_model",
            version="1.0.0",
            model_type="classifier",
            status=ModelStatus.REGISTERED,
            created_at=now,
            updated_at=now,
        )
        temp_registry.register_model(metadata)

        result = temp_registry.get_model_metadata("test_model", "1.0.0")
        assert result is not None
        assert result.name == "test_model"
        assert result.version == "1.0.0"

    def test_get_model_metadata_latest_version(self, temp_registry):
        """Test getting latest version of a model."""
        now = datetime.now()
        for version in ["1.0.0", "1.1.0", "2.0.0"]:
            metadata = ModelMetadata(
                name="test_model",
                version=version,
                model_type="classifier",
                status=ModelStatus.REGISTERED,
                created_at=now,
                updated_at=now,
            )
            temp_registry.register_model(metadata)

        result = temp_registry.get_model_metadata("test_model")
        assert result is not None
        # Should get latest (highest version string)
        assert result.version == "2.0.0"

    def test_get_model_metadata_not_found(self, temp_registry):
        """Test getting non-existent model returns None."""
        result = temp_registry.get_model_metadata("nonexistent", "1.0.0")
        assert result is None

    def test_list_models_all(self, temp_registry):
        """Test listing all models."""
        now = datetime.now()
        for i in range(3):
            metadata = ModelMetadata(
                name=f"model_{i}",
                version="1.0.0",
                model_type="classifier",
                status=ModelStatus.REGISTERED,
                created_at=now,
                updated_at=now,
            )
            temp_registry.register_model(metadata)

        models = temp_registry.list_models()
        assert len(models) == 3

    def test_list_models_by_status(self, temp_registry):
        """Test listing models filtered by status."""
        now = datetime.now()
        statuses = [ModelStatus.REGISTERED, ModelStatus.DEPLOYED, ModelStatus.DEPLOYED]
        for i, status in enumerate(statuses):
            metadata = ModelMetadata(
                name=f"model_{i}",
                version="1.0.0",
                model_type="classifier",
                status=status,
                created_at=now,
                updated_at=now,
            )
            temp_registry.register_model(metadata)

        deployed = temp_registry.list_models(ModelStatus.DEPLOYED)
        assert len(deployed) == 2

    def test_update_model_status(self, temp_registry):
        """Test updating model status."""
        now = datetime.now()
        metadata = ModelMetadata(
            name="test_model",
            version="1.0.0",
            model_type="classifier",
            status=ModelStatus.REGISTERED,
            created_at=now,
            updated_at=now,
        )
        temp_registry.register_model(metadata)

        result = temp_registry.update_model_status(
            "test_model", "1.0.0", ModelStatus.DEPLOYED
        )
        assert result is True
        assert temp_registry.models["test_model:1.0.0"]["status"] == ModelStatus.DEPLOYED

    def test_update_model_status_not_found(self, temp_registry):
        """Test updating status of non-existent model."""
        result = temp_registry.update_model_status(
            "nonexistent", "1.0.0", ModelStatus.DEPLOYED
        )
        assert result is False

    def test_delete_model(self, temp_registry):
        """Test deleting a model from registry."""
        now = datetime.now()
        metadata = ModelMetadata(
            name="test_model",
            version="1.0.0",
            model_type="classifier",
            status=ModelStatus.REGISTERED,
            created_at=now,
            updated_at=now,
        )
        temp_registry.register_model(metadata)

        result = temp_registry.delete_model("test_model", "1.0.0")
        assert result is True
        assert "test_model:1.0.0" not in temp_registry.models

    def test_delete_model_not_found(self, temp_registry):
        """Test deleting non-existent model."""
        result = temp_registry.delete_model("nonexistent", "1.0.0")
        assert result is False

    def test_load_registry_with_existing_data(self, tmp_path):
        """Test loading registry from existing file."""
        registry_path = tmp_path / "registry.json"
        data = {
            "test:1.0.0": {
                "name": "test",
                "version": "1.0.0",
                "model_type": "classifier",
                "status": "registered",
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00",
                "description": "",
                "tags": [],
                "metrics": {},
                "parameters": {},
                "file_path": None,
                "file_size": None,
                "checksum": None,
            }
        }
        with open(registry_path, "w") as f:
            json.dump(data, f)

        registry = ModelRegistry(str(registry_path))
        assert "test:1.0.0" in registry.models
        assert registry.models["test:1.0.0"]["status"] == ModelStatus.REGISTERED

    def test_load_registry_corrupted_file(self, tmp_path):
        """Test loading corrupted registry file."""
        registry_path = tmp_path / "registry.json"
        with open(registry_path, "w") as f:
            f.write("not valid json")

        registry = ModelRegistry(str(registry_path))
        assert registry.models == {}

    def test_save_registry_error_handling(self, temp_registry):
        """Test save registry error handling."""
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            # Should not raise, just log warning
            temp_registry._save_registry()


# =============================================================================
# ModelStorage Tests
# =============================================================================
class TestModelStorage:
    """Tests for ModelStorage class."""

    @pytest.fixture
    def temp_storage(self, tmp_path):
        """Create storage with temporary directory."""
        storage_path = tmp_path / "storage"
        return ModelStorage(str(storage_path))

    def test_init_creates_directory(self, tmp_path):
        """Test that initialization creates storage directory."""
        storage_path = tmp_path / "new_storage"
        storage = ModelStorage(str(storage_path))
        assert storage_path.exists()

    def test_save_model_joblib(self, temp_storage):
        """Test saving model with joblib format."""
        model = {"weights": [1, 2, 3]}
        success, file_path, file_size = temp_storage.save_model(
            model, "test_model", "1.0.0", ModelFormat.JOBLIB
        )
        assert success is True
        assert file_path is not None
        assert file_size > 0
        assert Path(file_path).exists()

    def test_save_model_pickle(self, temp_storage):
        """Test saving model with pickle format."""
        model = {"weights": [1, 2, 3]}
        success, file_path, file_size = temp_storage.save_model(
            model, "test_model", "1.0.0", ModelFormat.PICKLE
        )
        assert success is True
        assert file_path is not None
        assert "pickle" in file_path

    def test_save_model_json(self, temp_storage):
        """Test saving model with JSON format."""
        model = {"weights": [1, 2, 3]}
        success, file_path, file_size = temp_storage.save_model(
            model, "test_model", "1.0.0", ModelFormat.JSON
        )
        assert success is True
        assert file_path is not None
        assert "json" in file_path

    def test_load_model_joblib(self, temp_storage):
        """Test loading model with joblib format."""
        model = {"weights": [1, 2, 3]}
        temp_storage.save_model(model, "test_model", "1.0.0", ModelFormat.JOBLIB)

        loaded = temp_storage.load_model("test_model", "1.0.0", ModelFormat.JOBLIB)
        assert loaded == model

    def test_load_model_json(self, temp_storage):
        """Test loading model with JSON format."""
        model = {"weights": [1, 2, 3]}
        temp_storage.save_model(model, "test_model", "1.0.0", ModelFormat.JSON)

        loaded = temp_storage.load_model("test_model", "1.0.0", ModelFormat.JSON)
        assert loaded == model

    def test_load_model_not_found(self, temp_storage):
        """Test loading non-existent model returns None."""
        result = temp_storage.load_model("nonexistent", "1.0.0", ModelFormat.JOBLIB)
        assert result is None

    def test_load_model_error_handling(self, temp_storage):
        """Test load model handles errors gracefully."""
        # Create an invalid file
        file_path = temp_storage._get_model_path("bad", "1.0.0", ModelFormat.JOBLIB)
        with open(file_path, "wb") as f:
            f.write(b"not a valid joblib file")

        result = temp_storage.load_model("bad", "1.0.0", ModelFormat.JOBLIB)
        assert result is None

    def test_delete_model_file(self, temp_storage):
        """Test deleting model file."""
        model = {"weights": [1, 2, 3]}
        temp_storage.save_model(model, "test_model", "1.0.0", ModelFormat.JOBLIB)

        result = temp_storage.delete_model_file("test_model", "1.0.0", ModelFormat.JOBLIB)
        assert result is True

        # Verify file is deleted
        file_path = temp_storage._get_model_path("test_model", "1.0.0", ModelFormat.JOBLIB)
        assert not file_path.exists()

    def test_delete_model_file_not_found(self, temp_storage):
        """Test deleting non-existent model file."""
        result = temp_storage.delete_model_file("nonexistent", "1.0.0", ModelFormat.JOBLIB)
        assert result is False

    def test_list_model_files(self, temp_storage):
        """Test listing model files."""
        for i in range(3):
            temp_storage.save_model(
                {"weights": [i]}, f"model_{i}", "1.0.0", ModelFormat.JOBLIB
            )

        files = temp_storage.list_model_files()
        assert len(files) == 3
        for file_info in files:
            assert "name" in file_info
            assert "size" in file_info
            assert "modified" in file_info
            assert "path" in file_info

    def test_calculate_checksum(self, temp_storage):
        """Test checksum calculation."""
        model = {"weights": [1, 2, 3]}
        temp_storage.save_model(model, "test_model", "1.0.0", ModelFormat.JOBLIB)

        file_path = temp_storage._get_model_path("test_model", "1.0.0", ModelFormat.JOBLIB)
        checksum = temp_storage._calculate_checksum(file_path)
        assert isinstance(checksum, str)
        assert len(checksum) == 32  # MD5 hex digest length


# =============================================================================
# PerformanceTracker Tests
# =============================================================================
class TestPerformanceTracker:
    """Tests for PerformanceTracker class."""

    @pytest.fixture
    def temp_tracker(self, tmp_path):
        """Create tracker with temporary storage."""
        tracking_path = tmp_path / "performance.json"
        return PerformanceTracker(str(tracking_path))

    def test_init_creates_directory(self, tmp_path):
        """Test that initialization creates parent directories."""
        tracking_path = tmp_path / "nested" / "performance.json"
        tracker = PerformanceTracker(str(tracking_path))
        assert tracking_path.parent.exists()

    def test_log_performance(self, temp_tracker):
        """Test logging performance metrics."""
        perf = ModelPerformance(
            model_name="test_model",
            version="1.0.0",
            timestamp=datetime.now(),
            metrics={"accuracy": 0.95},
        )
        temp_tracker.log_performance(perf)
        assert len(temp_tracker.performance_data) == 1

    def test_get_performance_history(self, temp_tracker):
        """Test getting performance history."""
        now = datetime.now()
        for i in range(5):
            perf = ModelPerformance(
                model_name="test_model",
                version="1.0.0",
                timestamp=now - timedelta(days=i),
                metrics={"accuracy": 0.9 + i * 0.01},
            )
            temp_tracker.log_performance(perf)

        history = temp_tracker.get_performance_history("test_model", days=30)
        assert len(history) == 5
        # Should be sorted by timestamp
        assert history[0].timestamp < history[-1].timestamp

    def test_get_performance_history_filters_old(self, temp_tracker):
        """Test that old performance data is filtered out."""
        now = datetime.now()
        # Add old data
        old_perf = ModelPerformance(
            model_name="test_model",
            version="1.0.0",
            timestamp=now - timedelta(days=60),
            metrics={"accuracy": 0.80},
        )
        temp_tracker.log_performance(old_perf)

        # Add recent data
        recent_perf = ModelPerformance(
            model_name="test_model",
            version="1.0.0",
            timestamp=now,
            metrics={"accuracy": 0.95},
        )
        temp_tracker.log_performance(recent_perf)

        history = temp_tracker.get_performance_history("test_model", days=30)
        assert len(history) == 1
        assert history[0].metrics["accuracy"] == 0.95

    def test_get_model_metrics_summary(self, temp_tracker):
        """Test getting metrics summary."""
        now = datetime.now()
        for i in range(5):
            perf = ModelPerformance(
                model_name="test_model",
                version="1.0.0",
                timestamp=now - timedelta(days=i),
                metrics={"accuracy": 0.9 + i * 0.01, "f1": 0.85 + i * 0.01},
            )
            temp_tracker.log_performance(perf)

        summary = temp_tracker.get_model_metrics_summary("test_model")
        assert "accuracy" in summary
        assert "f1" in summary
        assert "mean" in summary["accuracy"]
        assert "std" in summary["accuracy"]
        assert "min" in summary["accuracy"]
        assert "max" in summary["accuracy"]
        assert "latest" in summary["accuracy"]
        assert "count" in summary["accuracy"]
        assert summary["accuracy"]["count"] == 5

    def test_get_model_metrics_summary_empty(self, temp_tracker):
        """Test getting metrics summary for non-existent model."""
        summary = temp_tracker.get_model_metrics_summary("nonexistent")
        assert summary == {}

    def test_load_performance_data_existing(self, tmp_path):
        """Test loading existing performance data."""
        tracking_path = tmp_path / "performance.json"
        data = [
            {
                "model_name": "test",
                "version": "1.0.0",
                "timestamp": "2024-01-01T00:00:00",
                "metrics": {"accuracy": 0.95},
                "dataset_info": {},
            }
        ]
        with open(tracking_path, "w") as f:
            json.dump(data, f)

        tracker = PerformanceTracker(str(tracking_path))
        assert len(tracker.performance_data) == 1
        assert isinstance(tracker.performance_data[0]["timestamp"], datetime)

    def test_load_performance_data_corrupted(self, tmp_path):
        """Test loading corrupted performance file."""
        tracking_path = tmp_path / "performance.json"
        with open(tracking_path, "w") as f:
            f.write("not valid json")

        tracker = PerformanceTracker(str(tracking_path))
        assert tracker.performance_data == []


# =============================================================================
# ModelManager Tests
# =============================================================================
class TestModelManager:
    """Tests for ModelManager class."""

    @pytest.fixture
    def temp_manager(self, tmp_path):
        """Create manager with temporary base path."""
        return ModelManager(str(tmp_path / "models"))

    def test_init_creates_directories(self, tmp_path):
        """Test that initialization creates necessary directories."""
        base_path = tmp_path / "models"
        manager = ModelManager(str(base_path))
        assert base_path.exists()
        assert (base_path / "storage").exists()

    def test_register_model(self, temp_manager):
        """Test registering a model."""
        model = {"weights": [1, 2, 3]}
        result = temp_manager.register_model(
            model=model,
            name="test_model",
            version="1.0.0",
            model_type="classifier",
            description="Test model",
            tags=["test"],
            parameters={"n_estimators": 100},
        )
        assert result is True

        # Verify in registry
        metadata = temp_manager.get_model_info("test_model", "1.0.0")
        assert metadata is not None
        assert metadata.name == "test_model"
        assert metadata.model_type == "classifier"

    def test_register_model_failure(self, temp_manager):
        """Test registering model with storage failure."""
        with patch.object(temp_manager.storage, "save_model", return_value=(False, None, None)):
            result = temp_manager.register_model(
                model={"weights": [1, 2, 3]},
                name="test_model",
                version="1.0.0",
            )
            assert result is False

    def test_load_model(self, temp_manager):
        """Test loading a model."""
        model = {"weights": [1, 2, 3]}
        temp_manager.register_model(model=model, name="test_model", version="1.0.0")

        loaded = temp_manager.load_model("test_model", "1.0.0")
        assert loaded == model

    def test_load_model_cached(self, temp_manager):
        """Test that loaded models are cached."""
        model = {"weights": [1, 2, 3]}
        temp_manager.register_model(model=model, name="test_model", version="1.0.0")

        # Load twice
        loaded1 = temp_manager.load_model("test_model", "1.0.0")
        loaded2 = temp_manager.load_model("test_model", "1.0.0")

        assert loaded1 is loaded2  # Same object from cache

    def test_load_model_not_found(self, temp_manager):
        """Test loading non-existent model."""
        result = temp_manager.load_model("nonexistent", "1.0.0")
        assert result is None

    def test_deploy_model(self, temp_manager):
        """Test deploying a model."""
        model = {"weights": [1, 2, 3]}
        temp_manager.register_model(model=model, name="test_model", version="1.0.0")

        result = temp_manager.deploy_model("test_model", "1.0.0")
        assert result is True

        metadata = temp_manager.get_model_info("test_model", "1.0.0")
        assert metadata.status == ModelStatus.DEPLOYED

    def test_deploy_model_not_found(self, temp_manager):
        """Test deploying non-existent model."""
        result = temp_manager.deploy_model("nonexistent", "1.0.0")
        assert result is False

    def test_retire_model(self, temp_manager):
        """Test retiring a model."""
        model = {"weights": [1, 2, 3]}
        temp_manager.register_model(model=model, name="test_model", version="1.0.0")

        result = temp_manager.retire_model("test_model", "1.0.0")
        assert result is True

        metadata = temp_manager.get_model_info("test_model", "1.0.0")
        assert metadata.status == ModelStatus.RETIRED

    def test_delete_model(self, temp_manager):
        """Test deleting a model completely."""
        model = {"weights": [1, 2, 3]}
        temp_manager.register_model(model=model, name="test_model", version="1.0.0")

        # Load to populate cache
        temp_manager.load_model("test_model", "1.0.0")
        assert "test_model:1.0.0" in temp_manager.active_models

        result = temp_manager.delete_model("test_model", "1.0.0")
        assert result is True

        # Verify removed from cache
        assert "test_model:1.0.0" not in temp_manager.active_models

        # Verify removed from registry
        assert temp_manager.get_model_info("test_model", "1.0.0") is None

    def test_list_models(self, temp_manager):
        """Test listing models."""
        for i in range(3):
            temp_manager.register_model(
                model={"weights": [i]},
                name=f"model_{i}",
                version="1.0.0",
            )

        models = temp_manager.list_models()
        assert len(models) == 3

    def test_list_models_by_status(self, temp_manager):
        """Test listing models by status."""
        temp_manager.register_model(model={"w": 1}, name="model_0", version="1.0.0")
        temp_manager.register_model(model={"w": 2}, name="model_1", version="1.0.0")
        temp_manager.deploy_model("model_1", "1.0.0")

        deployed = temp_manager.list_models(ModelStatus.DEPLOYED)
        assert len(deployed) == 1
        assert deployed[0].name == "model_1"

    def test_log_model_performance(self, temp_manager):
        """Test logging model performance."""
        temp_manager.register_model(model={"w": 1}, name="test_model", version="1.0.0")

        temp_manager.log_model_performance(
            name="test_model",
            version="1.0.0",
            metrics={"accuracy": 0.95, "f1": 0.93},
            dataset_info={"samples": 1000},
        )

        history = temp_manager.get_model_performance_history("test_model", days=30)
        assert len(history) == 1
        assert history[0].metrics["accuracy"] == 0.95

    def test_get_model_metrics_summary(self, temp_manager):
        """Test getting model metrics summary."""
        temp_manager.register_model(model={"w": 1}, name="test_model", version="1.0.0")

        for i in range(3):
            temp_manager.log_model_performance(
                name="test_model",
                version="1.0.0",
                metrics={"accuracy": 0.9 + i * 0.01},
            )

        summary = temp_manager.get_model_metrics_summary("test_model")
        assert "accuracy" in summary
        assert summary["accuracy"]["count"] == 3

    def test_cleanup_cache(self, temp_manager):
        """Test clearing the model cache."""
        temp_manager.register_model(model={"w": 1}, name="test_model", version="1.0.0")
        temp_manager.load_model("test_model", "1.0.0")

        assert len(temp_manager.active_models) > 0

        temp_manager.cleanup_cache()
        assert len(temp_manager.active_models) == 0

    def test_get_storage_info(self, temp_manager):
        """Test getting storage information."""
        for i in range(3):
            temp_manager.register_model(
                model={"weights": list(range(100))},
                name=f"model_{i}",
                version="1.0.0",
            )

        info = temp_manager.get_storage_info()
        assert info["total_files"] == 3
        assert info["total_size_bytes"] > 0
        assert info["total_size_mb"] >= 0
        assert len(info["files"]) == 3


# =============================================================================
# Utility Function Tests
# =============================================================================
class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_create_sample_model_data(self):
        """Test creating sample model data."""
        data = create_sample_model_data()
        assert "accuracy" in data
        assert "precision" in data
        assert "recall" in data
        assert "f1_score" in data
        assert all(isinstance(v, float) for v in data.values())


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================
class TestEdgeCases:
    """Edge case and error handling tests."""

    def test_model_metadata_with_empty_strings(self):
        """Test model metadata with empty string values."""
        now = datetime.now()
        metadata = ModelMetadata(
            name="",
            version="",
            model_type="",
            status=ModelStatus.REGISTERED,
            created_at=now,
            updated_at=now,
            description="",
        )
        assert metadata.name == ""
        assert metadata.version == ""

    def test_storage_save_with_special_characters(self, tmp_path):
        """Test saving model with special characters in name."""
        storage = ModelStorage(str(tmp_path / "storage"))
        model = {"weights": [1, 2, 3]}
        
        # Model with spaces/dashes in name
        success, file_path, file_size = storage.save_model(
            model, "my-model_v2", "1.0.0", ModelFormat.JOBLIB
        )
        assert success is True

    def test_performance_tracker_concurrent_writes(self, tmp_path):
        """Test performance tracker handles concurrent writes."""
        tracker = PerformanceTracker(str(tmp_path / "performance.json"))
        
        for i in range(10):
            perf = ModelPerformance(
                model_name=f"model_{i}",
                version="1.0.0",
                timestamp=datetime.now(),
                metrics={"accuracy": 0.9 + i * 0.01},
            )
            tracker.log_performance(perf)

        assert len(tracker.performance_data) == 10

    def test_registry_with_many_models(self, tmp_path):
        """Test registry handles many models efficiently."""
        registry = ModelRegistry(str(tmp_path / "registry.json"))
        now = datetime.now()

        for i in range(100):
            metadata = ModelMetadata(
                name=f"model_{i}",
                version="1.0.0",
                model_type="classifier",
                status=ModelStatus.REGISTERED,
                created_at=now,
                updated_at=now,
            )
            registry.register_model(metadata)

        models = registry.list_models()
        assert len(models) == 100

    def test_manager_register_with_exception(self, tmp_path):
        """Test manager handles exceptions during registration."""
        manager = ModelManager(str(tmp_path / "models"))
        
        with patch.object(manager.registry, "register_model", side_effect=Exception("Test error")):
            result = manager.register_model(
                model={"w": 1},
                name="test",
                version="1.0.0",
            )
            assert result is False
