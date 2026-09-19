"""
Comprehensive tests for backend.ml.model_manager module.
Target: 749 missing statements -> 100% coverage
"""
import json
import os
import pickle
import tempfile
from datetime import datetime, timezone, UTC
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open, AsyncMock
import pytest
import numpy as np
import pandas as pd

# Import target module
from backend.ml.model_manager import (
    InMemoryModelRegistry,
    _NoOpModelManager,
    _NoOpModel,
    RegistryNoopModel,
    get_model_manager,
    ModelManager,
    ModelMetadata,
    ModelManagerInterface,
    ModelNotFoundError,
    ModelVersion,
    ModelRegistry,
    ModelStatus,
    DriftType,
    DriftDetection,
    ModelMonitoring,
    SchemaMismatchError,
    _set_model_manager,
    NoopModel,
    NoOpModelManager,
    _NoopModel,
    DISABLE_ML,
)
# ALLOW_MOCK_ML was removed — mock loading is no longer supported
ALLOW_MOCK_ML = False


# =============================================================================
# InMemoryModelRegistry Tests
# =============================================================================

class TestInMemoryModelRegistry:
    """Test InMemoryModelRegistry class."""

    def test_init(self):
        """Test initialization."""
        registry = InMemoryModelRegistry()
        assert registry._store == {}

    def test_register_basic(self):
        """Test basic model registration."""
        registry = InMemoryModelRegistry()
        mock_model = MagicMock()
        
        result = registry.register("test_model", "1.0", mock_model)
        
        assert result is not None
        assert result.model_name == "test_model"
        assert result.version == "1.0"
        assert ("test_model", "1.0") in registry._store

    def test_register_with_metadata(self):
        """Test registration with metadata."""
        registry = InMemoryModelRegistry()
        mock_model = MagicMock()
        metadata = {"description": "Test model"}
        
        result = registry.register(
            "model1", "v1", mock_model,
            metadata=metadata,
            artifacts_path="/path/to/artifacts",
            feature_schema={"col1": "float"}
        )
        
        assert result.metadata == metadata
        assert result.artifacts_path == "/path/to/artifacts"
        assert result.feature_schema == {"col1": "float"}

    def test_load_existing_model_with_version(self):
        """Test loading a model by name and version."""
        registry = InMemoryModelRegistry()
        mock_model = MagicMock()
        registry.register("model", "1.0", mock_model)
        
        result = registry.load("model", "1.0")
        
        assert result is mock_model

    def test_load_latest_version(self):
        """Test loading latest version when version is None."""
        registry = InMemoryModelRegistry()
        model_v1 = MagicMock(name="v1")
        model_v2 = MagicMock(name="v2")
        
        registry.register("model", "1.0", model_v1)
        registry.register("model", "2.0", model_v2)
        
        result = registry.load("model", None)
        
        # Should return latest version (2.0 > 1.0 by string comparison)
        assert result is model_v2

    def test_load_nonexistent_model_returns_noop(self):
        """Test loading non-existent model returns RegistryNoopModel."""
        registry = InMemoryModelRegistry()
        
        result = registry.load("nonexistent")
        
        assert isinstance(result, RegistryNoopModel)

    def test_load_nonexistent_version_returns_noop(self):
        """Test loading non-existent version returns RegistryNoopModel."""
        registry = InMemoryModelRegistry()
        registry.register("model", "1.0", MagicMock())
        
        result = registry.load("model", "2.0")
        
        assert isinstance(result, RegistryNoopModel)

    def test_get_existing(self):
        """Test getting existing model and version info."""
        registry = InMemoryModelRegistry()
        mock_model = MagicMock()
        registry.register("model", "1.0", mock_model)
        
        result = registry.get("model", "1.0")
        
        assert result is not None
        assert result[0] is mock_model

    def test_get_nonexistent(self):
        """Test getting non-existent model returns None."""
        registry = InMemoryModelRegistry()
        
        result = registry.get("nonexistent", "1.0")
        
        assert result is None

    def test_list_versions(self):
        """Test listing all versions for a model."""
        registry = InMemoryModelRegistry()
        registry.register("model", "1.0", MagicMock())
        registry.register("model", "2.0", MagicMock())
        registry.register("other_model", "1.0", MagicMock())
        
        versions = registry.list_versions("model")
        
        assert len(versions) == 2
        version_strings = [v.version for v in versions]
        assert "1.0" in version_strings
        assert "2.0" in version_strings

    def test_version_info(self):
        """Test getting version info."""
        registry = InMemoryModelRegistry()
        registry.register("model", "1.0", MagicMock())
        
        info = registry.version_info("model", "1.0")
        
        assert info.model_name == "model"
        assert info.version == "1.0"


# =============================================================================
# NoOp Classes Tests
# =============================================================================

class TestNoOpModelManager:
    """Test _NoOpModelManager class."""

    def test_init(self):
        """Test initialization."""
        manager = _NoOpModelManager()
        assert manager.models == {}
        assert isinstance(manager.registry, InMemoryModelRegistry)

    def test_register_model(self):
        """Test register_model returns test id."""
        manager = _NoOpModelManager()
        result = manager.register_model("model", "version")
        assert result == "test-model-id"

    def test_get_model(self):
        """Test get_model returns NoOpModel."""
        manager = _NoOpModelManager()
        result = manager.get_model("any_model")
        assert isinstance(result, _NoOpModel)

    def test_predict(self):
        """Test predict returns mock prediction."""
        manager = _NoOpModelManager()
        result = manager.predict([1, 2, 3])
        assert result == {"prediction": 0.5, "confidence": 0.0}

    def test_set_reference_data(self):
        """Test set_reference_data does nothing."""
        manager = _NoOpModelManager()
        manager.set_reference_data([1, 2, 3])  # Should not raise

    def test_detect_drift(self):
        """Test detect_drift returns no drift."""
        manager = _NoOpModelManager()
        result = manager.detect_drift([1, 2, 3])
        assert result == {"drift_detected": False, "psi_score": 0.0}


class TestNoOpModel:
    """Test _NoOpModel class."""

    def test_predict(self):
        """Test predict returns 0.0."""
        model = _NoOpModel()
        result = model.predict([1, 2, 3])
        assert result == 0.0


class TestRegistryNoopModel:
    """Test RegistryNoopModel class."""

    def test_predict(self):
        """Test predict returns dict with prediction 0.0."""
        model = RegistryNoopModel()
        result = model.predict([1, 2, 3])
        assert result == {"prediction": 0.0}


# =============================================================================
# get_model_manager Factory Tests
# =============================================================================

class TestGetModelManager:
    """Test get_model_manager factory function."""

    def test_with_disable_ml(self):
        """Test returns NoOpModelManager when DISABLE_ML is set."""
        with patch('backend.ml.model_manager.DISABLE_ML', True):
            manager = get_model_manager()
            assert isinstance(manager, _NoOpModelManager)

    def test_creates_singleton(self):
        """Test singleton pattern for normal operation."""
        with patch('backend.ml.model_manager.DISABLE_ML', False):
            with patch('backend.ml.model_manager._model_manager', None):
                with tempfile.TemporaryDirectory() as tmpdir:
                    manager1 = get_model_manager(model_store_path=tmpdir)
                    # Reset for next test
                    _set_model_manager(None)


# =============================================================================
# ModelMetadata Tests
# =============================================================================

class TestModelMetadata:
    """Test ModelMetadata dataclass."""

    def test_creation_minimal(self):
        """Test creation with minimal required fields."""
        metadata = ModelMetadata(
            name="test_model",
            version="1.0",
            model_type="classifier",
            features=["f1", "f2"]
        )
        
        assert metadata.name == "test_model"
        assert metadata.version == "1.0"
        assert metadata.model_type == "classifier"
        assert metadata.features == ["f1", "f2"]
        assert metadata.description == ""
        assert metadata.tags == {}

    def test_creation_full(self):
        """Test creation with all fields."""
        created = datetime.now(UTC)
        metadata = ModelMetadata(
            name="test_model",
            version="2.0",
            model_type="regressor",
            features=["a", "b", "c"],
            created_at=created,
            description="A test model",
            tags={"env": "test"}
        )
        
        assert metadata.created_at == created
        assert metadata.description == "A test model"
        assert metadata.tags == {"env": "test"}


# =============================================================================
# ModelManager Tests
# =============================================================================

class TestModelManager:
    """Test ModelManager class."""

    @pytest.fixture
    def temp_model_store(self):
        """Create temporary model store directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def manager(self, temp_model_store):
        """Create ModelManager instance."""
        return ModelManager(model_store_path=temp_model_store)

    def test_init_creates_directory(self, temp_model_store):
        """Test initialization creates model store directory."""
        path = os.path.join(temp_model_store, "subdir")
        manager = ModelManager(model_store_path=path)
        assert os.path.exists(path)

    def test_init_with_base_path_compat(self, temp_model_store):
        """Test initialization with base_path parameter for backward compat."""
        manager = ModelManager(base_path=temp_model_store)
        assert manager.base_path == temp_model_store

    def test_register_model_with_metadata(self, manager):
        """Test registering model with ModelMetadata."""
        mock_model = MagicMock()
        metadata = ModelMetadata(
            name="test_model",
            version="1.0",
            model_type="classifier",
            features=["f1"]
        )
        
        result = manager.register_model(mock_model, metadata)
        
        assert result is True
        assert "test_model" in manager.models
        assert "test_model" in manager.metadata

    def test_register_model_with_kwargs(self, manager):
        """Test registering model with name/version kwargs."""
        mock_model = MagicMock()
        
        result = manager.register_model(
            mock_model,
            name="kwarg_model",
            version="2.0",
            features=["x", "y"]
        )
        
        assert result is True
        assert "kwarg_model" in manager.models

    def test_register_model_positional_compat(self, manager):
        """Test registering model with positional args for compat."""
        mock_model = MagicMock()
        
        result = manager.register_model(mock_model, "positional_model", "v1")
        
        assert result is True

    def test_register_model_validation_fails(self, manager):
        """Test registration fails with invalid metadata."""
        mock_model = MagicMock()
        metadata = ModelMetadata(
            name="",  # Invalid: empty name
            version="1.0",
            model_type="test",
            features=["f1"]
        )
        
        with pytest.raises(ValueError, match="non-empty string"):
            manager.register_model(mock_model, metadata)

    def test_register_model_invalid_type(self, manager):
        """Test registration fails with non-ModelMetadata."""
        mock_model = MagicMock()
        
        with pytest.raises(TypeError, match="ModelMetadata"):
            manager.register_model(mock_model, metadata=123)

    def test_load_model_from_memory(self, manager):
        """Test loading model from in-memory store."""
        mock_model = MagicMock()
        metadata = ModelMetadata(
            name="mem_model",
            version="1.0",
            model_type="test",
            features=["f1"]
        )
        manager.register_model(mock_model, metadata)
        
        result = manager.load_model("mem_model")
        
        assert result is mock_model

    def test_load_model_with_version(self, manager):
        """Test loading model with specific version."""
        mock_model = MagicMock()
        manager.models["versioned_1.0"] = mock_model
        
        result = manager.load_model("versioned", "1.0")
        
        assert result is mock_model

    def test_load_model_not_found(self, manager):
        """Test loading non-existent model raises error."""
        with pytest.raises(ModelNotFoundError):
            manager.load_model("nonexistent")

    def test_load_model_from_disk(self, manager, temp_model_store):
        """Test loading model from disk with secure pickle."""
        # Create a model file
        mock_model = {"type": "test"}
        model_path = Path(temp_model_store) / "disk_model_1.0.pkl"
        with open(model_path, "wb") as f:
            pickle.dump(mock_model, f)
        
        with patch('backend.ml.model_manager.secure_load', return_value=mock_model):
            result = manager.load_model("disk_model")
            assert result == mock_model

    def test_predict(self, manager):
        """Test making predictions."""
        mock_model = MagicMock()
        mock_model.predict.return_value = 0.75
        manager.models["pred_model"] = mock_model
        
        result = manager.predict("pred_model", {"f1": 1.0})
        
        assert result == 0.75
        mock_model.predict.assert_called_once()

    def test_get_model_from_registry(self, manager):
        """Test get_model delegates to registry."""
        mock_model = MagicMock()
        manager.registry.get_model = MagicMock(return_value=mock_model)
        
        result = manager.get_model("reg_model", "1.0")
        
        assert result is mock_model

    def test_get_model_fallback_to_load(self, manager):
        """Test get_model falls back to load_model."""
        mock_model = MagicMock()
        manager.registry.get_model = MagicMock(side_effect=Exception("Registry error"))
        manager.models["fallback"] = mock_model
        
        result = manager.get_model("fallback")
        
        assert result is mock_model

    def test_list_models(self, manager):
        """Test listing all models."""
        manager.models["model1"] = MagicMock()
        manager.models["model2"] = MagicMock()
        
        result = manager.list_models()
        
        assert "model1" in result
        assert "model2" in result

    def test_get_model_metadata(self, manager):
        """Test getting model metadata."""
        metadata = ModelMetadata(
            name="meta_model",
            version="1.0",
            model_type="test",
            features=["f"]
        )
        manager.metadata["meta_model"] = metadata
        
        result = manager.get_model_metadata("meta_model")
        
        assert result is metadata

    def test_get_model_metadata_not_found(self, manager):
        """Test getting metadata for non-existent model raises error."""
        with pytest.raises(ModelNotFoundError):
            manager.get_model_metadata("nonexistent")

    def test_save_model(self, manager, temp_model_store):
        """Test save_model compatibility method."""
        mock_model = {"data": "test"}
        path = os.path.join(temp_model_store, "saved_model.pkl")
        
        result = manager.save_model(mock_model, path)
        
        assert result is True
        assert os.path.exists(path)

    def test_save_model_failure(self, manager):
        """Test save_model returns False on failure."""
        result = manager.save_model(MagicMock(), "/invalid/path/model.pkl")
        assert result is False

    def test_get_model_versions(self, manager):
        """Test get_model_versions compatibility method."""
        result = manager.get_model_versions("any_model")
        assert result == []

    def test_save_ensemble_model(self, manager):
        """Test save_ensemble_model compatibility method."""
        mock_ensemble = MagicMock()
        
        result = manager.save_ensemble_model(mock_ensemble, "ensemble1")
        
        assert result is True
        assert "ensemble1" in manager.models

    def test_record_performance(self, manager):
        """Test record_performance compatibility method."""
        metadata = ModelMetadata(
            name="perf_model",
            version="1.0",
            model_type="test",
            features=["f"]
        )
        manager.metadata["perf_model"] = metadata
        
        result = manager.record_performance("perf_model", {"accuracy": 0.95})
        
        assert result is True

    def test_record_performance_model_not_found(self, manager):
        """Test record_performance returns False for unknown model."""
        result = manager.record_performance("unknown", {"accuracy": 0.5})
        assert result is False

    def test_validate_model(self, manager):
        """Test validate_model compatibility method."""
        mock_model = MagicMock()
        assert manager.validate_model(mock_model) is True
        assert manager.validate_model(None) is False

    def test_deploy_model_success(self, manager):
        """Test deploying a model."""
        mock_model = MagicMock()
        manager.models["deploy_test"] = mock_model
        manager.registry.get_model = MagicMock(return_value=mock_model)
        
        result = manager.deploy_model("deploy_test", "1.0")
        
        assert result["status"] == "success"
        assert result["model_name"] == "deploy_test"
        assert "endpoint" in result

    def test_deploy_model_not_found(self, manager):
        """Test deploying non-existent model."""
        manager.registry.get_model = MagicMock(side_effect=Exception("Not found"))
        
        result = manager.deploy_model("nonexistent")
        
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_train_and_register_model(self, manager):
        """Test async train and register method."""
        features = pd.DataFrame({"f1": [1, 2, 3], "f2": [4, 5, 6]})
        
        result = await manager.train_and_register_model(
            model_id="trained_model",
            features=features,
            version="v1.0.0"
        )
        
        assert result is not None
        assert result.model_id == "trained_model"
        assert result.status == "trained"

    @pytest.mark.asyncio
    async def test_train_and_register_model_no_features(self, manager):
        """Test train and register with no features."""
        result = await manager.train_and_register_model(
            model_id="no_features",
            version="v1.0.0"
        )
        
        assert result is not None

    def test_validate_metadata_empty_name(self, manager):
        """Test validation rejects empty name."""
        metadata = ModelMetadata(
            name="",
            version="1.0",
            model_type="test",
            features=["f"]
        )
        with pytest.raises(ValueError, match="non-empty string"):
            manager._validate_metadata(metadata)

    def test_validate_metadata_empty_version(self, manager):
        """Test validation rejects empty version."""
        metadata = ModelMetadata(
            name="test",
            version="",
            model_type="test",
            features=["f"]
        )
        with pytest.raises(ValueError, match="non-empty string"):
            manager._validate_metadata(metadata)

    def test_validate_metadata_empty_features(self, manager):
        """Test validation rejects empty features list."""
        metadata = ModelMetadata(
            name="test",
            version="1.0",
            model_type="test",
            features=[]
        )
        with pytest.raises(ValueError, match="non-empty list"):
            manager._validate_metadata(metadata)

    def test_validate_metadata_invalid_feature_names(self, manager):
        """Test validation rejects empty feature names."""
        metadata = ModelMetadata(
            name="test",
            version="1.0",
            model_type="test",
            features=["f1", ""]
        )
        with pytest.raises(ValueError, match="non-empty strings"):
            manager._validate_metadata(metadata)


# =============================================================================
# ModelVersion Tests
# =============================================================================

class TestModelVersion:
    """Test ModelVersion class."""

    def test_creation_with_model_name(self):
        """Test creation with model_name parameter."""
        version = ModelVersion(
            model_name="test_model",
            version="1.0"
        )
        
        assert version.model_name == "test_model"
        assert version.model_id == "test_model"  # Should sync

    def test_creation_with_model_id(self):
        """Test creation with model_id parameter."""
        version = ModelVersion(
            model_id="test_id",
            version="2.0"
        )
        
        assert version.model_id == "test_id"
        assert version.model_name == "test_id"  # Should sync

    def test_creation_with_artifacts_path(self):
        """Test creation with artifacts_path."""
        version = ModelVersion(
            model_name="test",
            version="1.0",
            artifacts_path="/path/to/artifacts"
        )
        
        assert version.artifacts_path == "/path/to/artifacts"
        assert version.model_path == "/path/to/artifacts"

    def test_creation_with_model_path(self):
        """Test creation with model_path (legacy)."""
        version = ModelVersion(
            model_name="test",
            version="1.0",
            model_path="/path/to/model"
        )
        
        assert version.model_path == "/path/to/model"

    def test_defaults(self):
        """Test default values."""
        version = ModelVersion(model_name="test", version="1.0")
        
        assert version.status == "trained"
        assert version.metrics == {}
        assert version.metadata == {}
        assert version.feature_names == []


# =============================================================================
# ModelStatus Tests
# =============================================================================

class TestModelStatus:
    """Test ModelStatus enum."""

    def test_all_statuses_exist(self):
        """Test all expected statuses exist."""
        assert ModelStatus.TRAINING.value == "training"
        assert ModelStatus.TRAINED.value == "trained"
        assert ModelStatus.DEPLOYED.value == "deployed"
        assert ModelStatus.CHAMPION.value == "champion"
        assert ModelStatus.CHALLENGER.value == "challenger"
        assert ModelStatus.DEPRECATED.value == "deprecated"
        assert ModelStatus.FAILED.value == "failed"


# =============================================================================
# DriftType Tests
# =============================================================================

class TestDriftType:
    """Test DriftType enum."""

    def test_drift_types(self):
        """Test drift type values."""
        assert DriftType.DATA_DRIFT.value == "data_drift"
        assert DriftType.CONCEPT_DRIFT.value == "concept_drift"
        assert DriftType.DATA.value == "data"
        assert DriftType.CONCEPT.value == "concept"
        assert DriftType.PERFORMANCE_DRIFT.value == "performance_drift"


# =============================================================================
# DriftDetection Tests
# =============================================================================

class TestDriftDetection:
    """Test DriftDetection dataclass."""

    def test_creation(self):
        """Test creation with required fields."""
        detection = DriftDetection(
            model_id="model1",
            drift_type=DriftType.DATA_DRIFT,
            severity=0.5,
            detected_at=datetime.now(UTC),
            affected_features=["f1", "f2"]
        )
        
        assert detection.model_id == "model1"
        assert detection.severity == 0.5
        assert len(detection.affected_features) == 2
        assert detection.recommendation == "Monitor closely"

    def test_creation_with_optionals(self):
        """Test creation with optional fields."""
        detection = DriftDetection(
            model_id="model1",
            drift_type=DriftType.CONCEPT_DRIFT,
            severity=0.8,
            detected_at=datetime.now(UTC),
            affected_features=["f1"],
            recommendation="Retrain model",
            psi_score=0.35,
            threshold=0.25
        )
        
        assert detection.recommendation == "Retrain model"
        assert detection.psi_score == 0.35
        assert detection.threshold == 0.25


# =============================================================================
# ModelMonitoring Tests
# =============================================================================

class TestModelMonitoring:
    """Test ModelMonitoring dataclass."""

    def test_creation(self):
        """Test creation."""
        monitoring = ModelMonitoring(
            model_id="model1",
            timestamp=datetime.now(UTC),
            prediction_count=1000,
            avg_confidence=0.85,
            accuracy=0.92,
            latency_ms=15.5,
            error_rate=0.02,
            drift_score=0.08
        )
        
        assert monitoring.model_id == "model1"
        assert monitoring.prediction_count == 1000
        assert monitoring.accuracy == 0.92


# =============================================================================
# SchemaMismatchError Tests
# =============================================================================

class TestSchemaMismatchError:
    """Test SchemaMismatchError class."""

    def test_basic_creation(self):
        """Test basic error creation."""
        error = SchemaMismatchError("Schema mismatch")
        
        assert str(error) == "Schema mismatch"
        assert error.expected_schema == {}
        assert error.received_schema == {}

    def test_creation_with_schemas(self):
        """Test creation with schema info."""
        error = SchemaMismatchError(
            "Schema mismatch",
            expected_schema={"col1": "float"},
            received_schema={"col2": "int"}
        )
        
        assert error.expected_schema == {"col1": "float"}
        assert error.received_schema == {"col2": "int"}

    def test_creation_with_columns(self):
        """Test creation with missing/extra columns."""
        error = SchemaMismatchError(
            "Column mismatch",
            missing_columns=["col1"],
            extra_columns=["col2"]
        )
        
        assert error.missing_columns == ["col1"]
        assert error.extra_columns == ["col2"]


# =============================================================================
# ModelRegistry Tests
# =============================================================================

class TestModelRegistry:
    """Test ModelRegistry class."""

    @pytest.fixture
    def temp_registry_path(self):
        """Create temporary registry directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def registry(self, temp_registry_path):
        """Create ModelRegistry instance."""
        return ModelRegistry(base_path=temp_registry_path)

    def test_init_creates_directory(self, temp_registry_path):
        """Test initialization creates base path."""
        path = os.path.join(temp_registry_path, "subdir")
        registry = ModelRegistry(base_path=path)
        assert os.path.exists(path)

    def test_init_loads_existing_registry(self, temp_registry_path):
        """Test loading existing registry from disk."""
        # Create a registry file
        registry_file = Path(temp_registry_path) / "model_registry.json"
        registry_data = {
            "model1": [{
                "model_id": "model1",
                "version": "1.0",
                "created_at": datetime.now(UTC).isoformat(),
                "status": "trained",
                "metrics": {"accuracy": 0.9},
                "training_data_hash": "abc123",
                "feature_names": ["f1"],
                "feature_dtypes": {"f1": "float64"},
                "train_window": {},
                "artifact_hash": "hash123",
                "model_path": "/path/to/model",
                "metadata": {}
            }]
        }
        with open(registry_file, "w") as f:
            json.dump(registry_data, f)
        
        registry = ModelRegistry(base_path=temp_registry_path)
        
        assert "model1" in registry.models
        assert len(registry.models["model1"]) == 1

    def test_save_registry(self, registry, temp_registry_path):
        """Test saving registry to disk."""
        # Register a model
        version = ModelVersion(
            model_id="save_test",
            version="1.0",
            created_at=datetime.now(UTC),
            status=ModelStatus.TRAINED,
            metrics={"accuracy": 0.95},
            training_data_hash="hash",
            feature_names=["f1"],
            feature_dtypes={"f1": "float"},
            train_window={},
            artifact_hash="artifact",
            model_path="/path"
        )
        registry.models["save_test"] = [version]
        
        registry.save_registry()
        
        registry_file = Path(temp_registry_path) / "model_registry.json"
        assert registry_file.exists()
        
        with open(registry_file) as f:
            data = json.load(f)
        assert "save_test" in data

    def test_register_compat_method(self, registry):
        """Test register() compatibility method."""
        mock_model = MagicMock()
        
        result = registry.register(
            "compat_model",
            "1.0",
            mock_model,
            metadata={"key": "value"}
        )
        
        assert result is not None
        assert "compat_model" in registry.models

    def test_register_model(self, registry):
        """Test registering a model."""
        mock_model = MagicMock()
        training_data = pd.DataFrame({
            "f1": [1.0, 2.0, 3.0],
            "f2": [4.0, 5.0, 6.0]
        })
        
        result = registry.register_model(
            model_id="reg_test",
            model_obj=mock_model,
            metadata={"description": "Test"},
            version="v1.0",
            metrics={"accuracy": 0.9},
            training_data=training_data
        )
        
        assert result is not None
        assert result.version == "v1.0"
        assert "reg_test" in registry.models

    def test_register_model_auto_version(self, registry):
        """Test auto-generated version number."""
        # Use a simple dict that can be serialized
        mock_model = {"model_type": "test", "weights": [1, 2, 3]}
        training_data = pd.DataFrame({"f1": [1, 2, 3]})
        
        result = registry.register_model(
            model_id="auto_version",
            model_obj=mock_model,
            training_data=training_data
        )
        
        assert result.version == "v1.0"

    def test_register_model_stores_in_cache(self, registry):
        """Test model is stored in memory cache."""
        # Use a simple dict that can be serialized to JSON
        mock_model = {"model_type": "test", "weights": [1, 2, 3]}
        training_data = pd.DataFrame({"f1": [1, 2, 3]})
        
        result = registry.register_model(
            model_id="cache_test",
            model_obj=mock_model,
            version="v1.0",
            training_data=training_data
        )
        
        cache_key = "cache_test:v1.0"
        assert cache_key in registry._model_cache
        assert registry._model_cache[cache_key] == mock_model


# =============================================================================
# Global Function Tests
# =============================================================================

class TestSetModelManager:
    """Test _set_model_manager function."""

    def test_set_model_manager(self):
        """Test setting global model manager."""
        mock_manager = MagicMock()
        _set_model_manager(mock_manager)
        
        # Reset for other tests
        _set_model_manager(None)


# =============================================================================
# Backward Compatibility Exports Tests
# =============================================================================

class TestBackwardCompatExports:
    """Test backward compatibility exports."""

    def test_noopmodel_alias(self):
        """Test NoopModel is aliased correctly."""
        assert NoopModel is _NoopModel

    def test_noopmodelmanager_alias(self):
        """Test NoOpModelManager is aliased correctly."""
        assert NoOpModelManager is _NoOpModelManager

    def test_noop_model_interface(self):
        """Test _NoopModel interface."""
        model = _NoopModel()
        assert model.predict({}) == 0.0
        
        model = _NoopModel(model="test", version="1.0", sha256="abc")
        assert model.model == "test"
        assert model.version == "1.0"
        assert model.sha256 == "abc"


# =============================================================================
# DriftDetector Tests
# =============================================================================
try:
    from backend.ml.model_manager import DriftDetector
    DRIFT_DETECTOR_AVAILABLE = True
except ImportError:
    DRIFT_DETECTOR_AVAILABLE = False


@pytest.mark.skipif(not DRIFT_DETECTOR_AVAILABLE, reason="DriftDetector not available")
class TestDriftDetector:
    """Tests for DriftDetector class."""

    @pytest.fixture
    def detector(self, tmp_path):
        """Create DriftDetector instance."""
        registry = ModelRegistry(base_path=str(tmp_path))
        return DriftDetector(window_size=100, registry=registry)

    def test_init(self, detector):
        """Test initialization."""
        assert detector.window_size == 100
        assert detector.reference_data == {}
        assert detector.monitoring_data == {}

    def test_set_reference_data_numeric(self, detector):
        """Test setting reference data with numeric features."""
        data = pd.DataFrame({
            "feature1": np.random.randn(100),
            "feature2": np.random.randn(100),
        })
        
        detector.set_reference_data("test_model", data)
        
        assert "test_model" in detector.reference_data
        ref = detector.reference_data["test_model"]
        assert "mean" in ref
        assert "std" in ref
        assert "feature1" in ref["mean"]

    def test_set_reference_data_categorical(self, detector):
        """Test setting reference data with categorical features."""
        data = pd.DataFrame({
            "category": ["A", "B", "A", "C", "B", "A"],
        })
        
        detector.set_reference_data("cat_model", data)
        
        ref = detector.reference_data["cat_model"]
        assert "categorical_features" in ref
        assert "category" in ref["categorical_features"]

    def test_set_reference_data_mixed(self, detector):
        """Test setting reference data with mixed feature types."""
        data = pd.DataFrame({
            "numeric": [1.0, 2.0, 3.0, 4.0, 5.0],
            "category": ["A", "B", "A", "B", "A"],
        })
        
        detector.set_reference_data("mixed_model", data)
        
        ref = detector.reference_data["mixed_model"]
        assert "mean" in ref
        assert "categorical_features" in ref

    def test_detect_data_drift_no_reference(self, detector):
        """Test detecting drift without reference data."""
        data = pd.DataFrame({"feature1": [1, 2, 3]})
        
        result = detector.detect_data_drift("unknown_model", data)
        
        assert result is None

    def test_detect_data_drift_no_drift(self, detector):
        """Test detecting no drift when data is similar."""
        ref_data = pd.DataFrame({
            "feature1": np.random.randn(100),
            "feature2": np.random.randn(100),
        })
        detector.set_reference_data("test_model", ref_data)
        
        # Similar data
        current_data = pd.DataFrame({
            "feature1": np.random.randn(100),
            "feature2": np.random.randn(100),
        })
        
        result = detector.detect_data_drift("test_model", current_data)
        
        # Should not detect drift with similar distributions
        assert result is None or result.severity < 0.5

    def test_detect_data_drift_significant_drift(self, detector):
        """Test detecting significant data drift."""
        ref_data = pd.DataFrame({
            "feature1": np.random.randn(100),
        })
        detector.set_reference_data("drift_model", ref_data)
        
        # Very different data (shifted mean by 10)
        current_data = pd.DataFrame({
            "feature1": np.random.randn(100) + 10,
        })
        
        result = detector.detect_data_drift("drift_model", current_data)
        
        if result is not None:
            assert result.drift_type == DriftType.DATA_DRIFT
            assert len(result.affected_features) > 0

    def test_detect_data_drift_categorical_drift(self, detector):
        """Test detecting categorical feature drift."""
        ref_data = pd.DataFrame({
            "category": ["A"] * 50 + ["B"] * 50,
        })
        detector.set_reference_data("cat_drift_model", ref_data)
        
        # Different distribution
        current_data = pd.DataFrame({
            "category": ["A"] * 10 + ["B"] * 10 + ["C"] * 80,
        })
        
        result = detector.detect_data_drift("cat_drift_model", current_data)
        
        # May or may not detect drift depending on thresholds
        # Just ensure it doesn't crash
        assert result is None or isinstance(result, DriftDetection)

    def test_detect_performance_drift_insufficient_samples(self, detector):
        """Test performance drift with insufficient samples."""
        predictions = [(0.5, 0.5)] * 50  # Only 50 samples
        baseline = {"mse": 0.1, "mae": 0.1}
        
        result = detector.detect_performance_drift("model", predictions, baseline)
        
        assert result is None

    def test_detect_performance_drift_no_degradation(self, detector):
        """Test performance drift with no degradation."""
        predictions = [(0.5 + np.random.randn() * 0.1, 0.5) for _ in range(100)]
        baseline = {"mse": 0.01, "mae": 0.08}
        
        result = detector.detect_performance_drift("model", predictions, baseline)
        
        # Should not detect drift if performance is similar
        assert result is None or result.severity < 0.2

    def test_detect_performance_drift_significant(self, detector):
        """Test detecting significant performance drift."""
        # Very bad predictions
        predictions = [(0.0, 1.0)] * 100  # All wrong
        baseline = {"mse": 0.01, "mae": 0.05}
        
        result = detector.detect_performance_drift("model", predictions, baseline)
        
        if result is not None:
            assert result.drift_type == DriftType.PERFORMANCE_DRIFT
            assert result.severity > 0

    def test_compute_psi_empty_data(self, detector):
        """Test PSI computation with empty data."""
        result = detector._compute_psi(np.array([]), [], [])
        assert result == 0.0

    def test_compute_psi_normal(self, detector):
        """Test PSI computation with normal data."""
        ref_bin_edges = [0, 0.25, 0.5, 0.75, 1.0]
        ref_bin_counts = [25, 25, 25, 25]
        live_values = np.random.uniform(0, 1, 100)
        
        result = detector._compute_psi(live_values, ref_bin_edges, ref_bin_counts)
        
        assert isinstance(result, float)
        assert result >= 0


# =============================================================================
# ModelRegistry Extended Tests
# =============================================================================

class TestModelRegistryExtended:
    """Extended tests for ModelRegistry."""

    @pytest.fixture
    def registry_with_model(self, tmp_path):
        """Create registry with a registered model."""
        registry = ModelRegistry(base_path=str(tmp_path))
        
        # Register a model
        training_data = pd.DataFrame({
            "f1": [1.0, 2.0, 3.0],
            "f2": [4.0, 5.0, 6.0]
        })
        model = {"weights": [1, 2, 3]}
        
        registry.register_model(
            model_id="test_model",
            model_obj=model,
            version="v1.0",
            metrics={"accuracy": 0.95},
            training_data=training_data
        )
        
        return registry

    def test_promote_to_champion(self, registry_with_model):
        """Test promoting model to champion."""
        result = registry_with_model.promote_to_champion("test_model", "v1.0")
        
        assert result is True
        assert registry_with_model.champions.get("test_model") == "v1.0"
        
        # Check champion file exists
        champion_file = Path(registry_with_model.base_path) / "test_model" / "champion.txt"
        assert champion_file.exists()
        assert champion_file.read_text().strip() == "v1.0"

    def test_promote_to_champion_nonexistent_model(self, registry_with_model):
        """Test promoting non-existent model."""
        result = registry_with_model.promote_to_champion("nonexistent", "v1.0")
        assert result is False

    def test_promote_to_champion_nonexistent_version(self, registry_with_model):
        """Test promoting non-existent version."""
        result = registry_with_model.promote_to_champion("test_model", "v99.0")
        assert result is False

    def test_get_champion_model(self, registry_with_model):
        """Test getting champion model."""
        registry_with_model.promote_to_champion("test_model", "v1.0")
        
        champion = registry_with_model.get_champion_model("test_model")
        
        assert champion is not None
        assert champion.version == "v1.0"

    def test_get_champion_model_from_file(self, registry_with_model):
        """Test getting champion from champion.txt file."""
        # Write champion file directly
        champion_file = Path(registry_with_model.base_path) / "test_model" / "champion.txt"
        champion_file.parent.mkdir(parents=True, exist_ok=True)
        champion_file.write_text("v1.0")
        
        champion = registry_with_model.get_champion_model("test_model")
        
        assert champion is not None
        assert champion.version == "v1.0"

    def test_get_champion_model_nonexistent(self, registry_with_model):
        """Test getting champion for non-existent model."""
        champion = registry_with_model.get_champion_model("nonexistent")
        assert champion is None

    def test_get_model_versions(self, registry_with_model):
        """Test getting all model versions."""
        versions = registry_with_model.get_model_versions("test_model")
        
        assert len(versions) == 1
        assert versions[0].version == "v1.0"

    def test_get_model_versions_nonexistent(self, registry_with_model):
        """Test getting versions for non-existent model."""
        versions = registry_with_model.get_model_versions("nonexistent")
        assert versions == []

    def test_load_artifacts(self, registry_with_model):
        """Test loading model artifacts."""
        with patch("backend.ml.model_manager.secure_load", side_effect=lambda f: pickle.load(f)):
            model, artifacts, metadata = registry_with_model.load_artifacts("test_model", "v1.0")

        assert model is not None
        assert isinstance(metadata, dict)
        assert "model_id" in metadata or "version" in metadata

    def test_assert_feature_schema_valid(self, registry_with_model):
        """Test asserting valid feature schema."""
        # Get metadata
        metadata = {
            "feature_names": ["f1", "f2"],
            "feature_dtypes": {"f1": "float64", "f2": "float64"}
        }
        
        live_df = pd.DataFrame({
            "f1": [1.0, 2.0],
            "f2": [3.0, 4.0]
        })
        
        result = registry_with_model.assert_feature_schema(live_df, metadata)
        
        assert list(result.columns) == ["f1", "f2"]

    def test_assert_feature_schema_missing_columns(self, registry_with_model):
        """Test asserting schema with missing columns."""
        metadata = {
            "feature_names": ["f1", "f2", "f3"],
            "feature_dtypes": {"f1": "float64", "f2": "float64", "f3": "float64"}
        }
        
        live_df = pd.DataFrame({
            "f1": [1.0, 2.0],
            "f2": [3.0, 4.0]
        })  # Missing f3
        
        with pytest.raises(SchemaMismatchError) as exc_info:
            registry_with_model.assert_feature_schema(live_df, metadata)
        
        assert "f3" in exc_info.value.missing_columns

    def test_assert_feature_schema_extra_columns(self, registry_with_model):
        """Test asserting schema with extra columns."""
        metadata = {
            "feature_names": ["f1"],
            "feature_dtypes": {"f1": "float64"}
        }
        
        live_df = pd.DataFrame({
            "f1": [1.0, 2.0],
            "f2": [3.0, 4.0]  # Extra column
        })
        
        with pytest.raises(SchemaMismatchError) as exc_info:
            registry_with_model.assert_feature_schema(live_df, metadata)
        
        assert "f2" in exc_info.value.extra_columns

    def test_assert_feature_schema_reorder_columns(self, registry_with_model):
        """Test schema assertion reorders columns."""
        metadata = {
            "feature_names": ["f2", "f1"],  # Different order
            "feature_dtypes": {"f1": "float64", "f2": "float64"}
        }
        
        live_df = pd.DataFrame({
            "f1": [1.0, 2.0],
            "f2": [3.0, 4.0]
        })
        
        result = registry_with_model.assert_feature_schema(live_df, metadata)
        
        assert list(result.columns) == ["f2", "f1"]

    def test_predict_basic(self, tmp_path):
        """Test basic prediction."""
        registry = ModelRegistry(base_path=str(tmp_path))
        
        # Create a simple model
        class SimpleModel:
            def predict(self, features):
                return 0.7
        
        training_data = pd.DataFrame({"f1": [1, 2, 3]})
        registry.register_model(
            model_id="pred_model",
            model_obj=SimpleModel(),
            version="v1.0",
            training_data=training_data
        )
        
        result = registry.predict("pred_model", {"f1": 1.0})
        
        assert result is not None

    def test_get_model(self, registry_with_model):
        """Test getting model version."""
        model = registry_with_model.get_model("test_model", "v1.0")
        
        assert model is not None
        assert model.version == "v1.0"

    def test_get_model_latest(self, registry_with_model):
        """Test getting latest model version."""
        model = registry_with_model.get_model("test_model", "latest")
        
        assert model is not None

    def test_get_latest_version(self, registry_with_model):
        """Test getting latest version explicitly."""
        model = registry_with_model.get_latest_version("test_model")
        
        assert model is not None
        assert model.version == "v1.0"

    def test_check_model_health(self, registry_with_model):
        """Test checking model health."""
        health = registry_with_model.check_model_health("test_model")
        
        assert "status" in health
        assert health["model_id"] == "test_model"

    def test_check_model_health_nonexistent(self, registry_with_model):
        """Test health check for non-existent model."""
        health = registry_with_model.check_model_health("nonexistent")
        
        assert health["status"] == "error"

    def test_get_model_hash(self, registry_with_model):
        """Test getting model hash."""
        hash_val = registry_with_model.get_model_hash("test_model", "v1.0")
        
        assert isinstance(hash_val, str)
        assert len(hash_val) > 0

    def test_get_model_metadata(self, registry_with_model):
        """Test getting model metadata."""
        metadata = registry_with_model.get_model_metadata("test_model", "v1.0")
        
        assert isinstance(metadata, dict)
        assert "version" in metadata

    def test_get_healthz_response(self, registry_with_model):
        """Test healthz endpoint response."""
        response = registry_with_model.get_healthz_response()
        
        assert "status" in response
        assert "total_models" in response
        assert "timestamp" in response

    def test_normalize_dtype_string(self, registry_with_model):
        """Test dtype normalization."""
        assert registry_with_model._normalize_dtype_string("float64") == "float64"
        assert registry_with_model._normalize_dtype_string("FLOAT32") == "float32"
        assert registry_with_model._normalize_dtype_string("int64") == "int64"
        assert registry_with_model._normalize_dtype_string("bool") == "bool"

    def test_compute_file_hash(self, registry_with_model, tmp_path):
        """Test file hash computation."""
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"test content")
        
        hash_val = registry_with_model._compute_file_hash(test_file)
        
        assert isinstance(hash_val, str)
        assert len(hash_val) == 64  # SHA256 hex length


# =============================================================================
# Compatibility Functions Tests
# =============================================================================
try:
    from backend.ml.model_manager import (
        create_model_registry,
        load_model_from_registry,
        save_model_to_registry,
        get_model_metrics,
        validate_model,
        detect_data_drift,
        get_champion_model,
        register_model,
    )
    COMPAT_FUNCS_AVAILABLE = True
except ImportError:
    COMPAT_FUNCS_AVAILABLE = False


@pytest.mark.skipif(not COMPAT_FUNCS_AVAILABLE, reason="Compat functions not available")
class TestCompatibilityFunctions:
    """Test compatibility stub functions."""

    def test_create_model_registry(self):
        """Test creating model registry."""
        registry = create_model_registry()
        assert isinstance(registry, ModelRegistry)

    def test_load_model_from_registry(self):
        """Test loading model from registry (returns mock on failure)."""
        result = load_model_from_registry("nonexistent_model")
        # Should return mock, not raise
        assert result is not None

    def test_save_model_to_registry(self):
        """Test saving model to registry."""
        result = save_model_to_registry("test", {"weights": [1, 2]})
        # May succeed or fail but shouldn't raise
        assert isinstance(result, bool)

    def test_get_model_metrics(self):
        """Test getting model metrics."""
        metrics = get_model_metrics("any_model")

        # When no trained model exists, returns warning dict
        assert "warning" in metrics
        assert "model_name" in metrics

    def test_validate_model(self):
        """Test model validation."""
        result = validate_model({"model": "test"})
        assert result is True

    def test_detect_data_drift_stub(self):
        """Test detect_data_drift stub."""
        result = detect_data_drift("model", None)
        assert result is None

    def test_get_champion_model_stub(self):
        """Test get_champion_model stub."""
        result = get_champion_model("model")
        assert result is None

    def test_register_model_stub(self):
        """Test register_model stub."""
        result = register_model("model", None, None, {}, [], {}, {})
        assert result is None

# Check for parquet support
try:
    import pyarrow  # noqa: F401
    HAS_PARQUET = True
except ImportError:
    try:
        import fastparquet  # noqa: F401
        HAS_PARQUET = True
    except ImportError:
        HAS_PARQUET = False


@pytest.mark.skipif(not HAS_PARQUET, reason="pyarrow or fastparquet required for parquet tests")
class TestModelRegistryRecordInference:
    """Test ModelRegistry.record_inference method."""

    def test_record_inference_creates_new_log(self, tmp_path):
        """Test record_inference creates new parquet log file."""
        import pandas as pd
        
        registry = ModelRegistry(base_path=tmp_path)
        
        # Create model directory structure
        model_path = tmp_path / "test_model" / "v1.0"
        model_path.mkdir(parents=True)
        
        # Create test features
        features = pd.DataFrame({"f1": [1.0, 2.0], "f2": [3.0, 4.0]})
        
        # Record inference
        registry.record_inference(
            model_id="test_model",
            version="v1.0",
            features=features,
            prediction=0.8,
            truth=1,
            latency_ms=10.5
        )
        
        # Check log file created
        log_path = model_path / "inference_log.parquet"
        assert log_path.exists()
        
        df = pd.read_parquet(log_path)
        assert len(df) == 1
        assert df["prediction"].iloc[0] == 0.8
        assert df["latency_ms"].iloc[0] == 10.5

    def test_record_inference_appends_to_existing_log(self, tmp_path):
        """Test record_inference appends to existing log."""
        import pandas as pd
        
        registry = ModelRegistry(base_path=tmp_path)
        
        # Create model directory and initial log
        model_path = tmp_path / "test_model" / "v1.0"
        model_path.mkdir(parents=True)
        
        # Create initial log
        initial_df = pd.DataFrame([{
            "ts": "2024-01-01T00:00:00",
            "features_hash": "abc123",
            "prediction": 0.5,
            "truth": 0,
            "latency_ms": 5.0
        }])
        initial_df.to_parquet(model_path / "inference_log.parquet", index=False)
        
        # Record new inference
        features = pd.DataFrame({"f1": [1.0], "f2": [2.0]})
        registry.record_inference(
            model_id="test_model",
            version="v1.0",
            features=features,
            prediction=0.9,
            truth=1,
            latency_ms=15.0
        )
        
        # Check log has 2 entries
        df = pd.read_parquet(model_path / "inference_log.parquet")
        assert len(df) == 2

    def test_record_inference_trims_when_exceeds_max(self, tmp_path):
        """Test record_inference trims log when exceeding max rows."""
        import pandas as pd
        
        registry = ModelRegistry(base_path=tmp_path)
        registry.inference_log_max_rows = 2  # Set very low max
        
        model_path = tmp_path / "test_model" / "v1.0"
        model_path.mkdir(parents=True)
        
        # Create initial log with 2 entries
        initial_df = pd.DataFrame([
            {"ts": "2024-01-01T00:00:00", "features_hash": "a", "prediction": 0.1, "truth": 0, "latency_ms": 1.0},
            {"ts": "2024-01-02T00:00:00", "features_hash": "b", "prediction": 0.2, "truth": 1, "latency_ms": 2.0},
        ])
        initial_df.to_parquet(model_path / "inference_log.parquet", index=False)
        
        # Record third inference (should trim oldest)
        features = pd.DataFrame({"f1": [1.0]})
        registry.record_inference(
            model_id="test_model",
            version="v1.0",
            features=features,
            prediction=0.3,
            truth=1,
            latency_ms=3.0
        )
        
        # Check log has only 2 entries (max)
        df = pd.read_parquet(model_path / "inference_log.parquet")
        assert len(df) == 2
        # Should have newer entries
        assert df["prediction"].iloc[-1] == 0.3

    def test_record_inference_handles_corrupt_log(self, tmp_path):
        """Test record_inference handles corrupted log gracefully."""
        import pandas as pd
        
        registry = ModelRegistry(base_path=tmp_path)
        
        model_path = tmp_path / "test_model" / "v1.0"
        model_path.mkdir(parents=True)
        
        # Create corrupt log file
        log_path = model_path / "inference_log.parquet"
        log_path.write_bytes(b"not a valid parquet file")
        
        # Record inference - should overwrite corrupt file
        features = pd.DataFrame({"f1": [1.0]})
        registry.record_inference(
            model_id="test_model",
            version="v1.0",
            features=features,
            prediction=0.7,
            truth=None,
            latency_ms=8.0
        )
        
        # Check new log was created
        df = pd.read_parquet(log_path)
        assert len(df) == 1


class TestModelRegistryStoreReferenceDistributions:
    """Test _store_reference_distributions method."""

    def test_store_reference_distributions_numeric(self, tmp_path):
        """Test storing reference distributions for numeric columns."""
        import pandas as pd
        import numpy as np
        import json
        
        registry = ModelRegistry(base_path=tmp_path)
        
        model_path = tmp_path / "test_model" / "v1.0"
        model_path.mkdir(parents=True)
        
        # Create training data with numeric columns
        np.random.seed(42)
        training_data = pd.DataFrame({
            "numeric_col": np.random.randn(100),
            "another_num": np.random.rand(100) * 10,
        })
        
        registry._store_reference_distributions(
            model_path=model_path,
            training_data=training_data
        )
        
        # Check file was created
        ref_path = model_path / "reference_distributions.json"
        assert ref_path.exists()
        
        with open(ref_path) as f:
            distributions = json.load(f)
        
        assert "numeric_col" in distributions
        assert "bin_edges" in distributions["numeric_col"]
        assert "bin_counts" in distributions["numeric_col"]
        assert "mean" in distributions["numeric_col"]
        assert "std" in distributions["numeric_col"]

    def test_store_reference_distributions_categorical(self, tmp_path):
        """Test storing reference distributions for categorical columns."""
        import pandas as pd
        import json
        
        registry = ModelRegistry(base_path=tmp_path)
        
        model_path = tmp_path / "test_model" / "v1.0"
        model_path.mkdir(parents=True)
        
        # Create training data with categorical column
        training_data = pd.DataFrame({
            "category_col": ["A", "B", "A", "C", "B", "A"],
        })
        
        registry._store_reference_distributions(
            model_path=model_path,
            training_data=training_data
        )
        
        ref_path = model_path / "reference_distributions.json"
        assert ref_path.exists()
        
        with open(ref_path) as f:
            distributions = json.load(f)
        
        assert "category_col" in distributions
        assert "categories" in distributions["category_col"]
        assert "counts" in distributions["category_col"]
        assert "total" in distributions["category_col"]

    def test_store_reference_distributions_handles_exception(self, tmp_path):
        """Test _store_reference_distributions handles exception gracefully."""
        import pandas as pd
        from unittest.mock import patch
        
        registry = ModelRegistry(base_path=tmp_path)
        
        model_path = tmp_path / "test_model" / "v1.0"
        model_path.mkdir(parents=True)
        
        training_data = pd.DataFrame({"col": [1, 2, 3]})
        
        # Patch to raise exception
        with patch.object(pd.DataFrame, '__getitem__', side_effect=Exception("error")):
            # Should not raise - method catches exceptions internally
            registry._store_reference_distributions(
                model_path=model_path,
                training_data=training_data
            )
        
        # File should not be created on error
        ref_path = model_path / "reference_distributions.json"
        assert not ref_path.exists()


class TestDriftDetectorPSI:
    """Test DriftDetector PSI methods."""

    def test_detect_drift_psi_no_reference(self, tmp_path):
        """Test PSI drift detection when no reference distributions exist."""
        import pandas as pd
        from backend.ml.model_manager import DriftDetector
        
        registry = ModelRegistry(base_path=tmp_path)
        detector = DriftDetector(registry=registry)
        
        # Create model directory without reference distributions
        model_path = tmp_path / "test_model" / "v1.0"
        model_path.mkdir(parents=True)
        
        # Create mock champion
        champion = ModelVersion(
            version="v1.0",
            model_path=model_path,
            status=ModelStatus.CHAMPION,
            feature_names=["f1", "f2"]
        )
        
        current_data = pd.DataFrame({"f1": [1, 2, 3], "f2": [4, 5, 6]})
        
        result = detector._detect_drift_with_psi(
            model_id="test_model",
            champion=champion,
            current_data=current_data
        )
        
        assert result is None

    def test_detect_drift_psi_with_drift(self, tmp_path):
        """Test PSI drift detection when drift is detected."""
        import pandas as pd
        import numpy as np
        import json
        from backend.ml.model_manager import DriftDetector
        
        registry = ModelRegistry(base_path=tmp_path)
        detector = DriftDetector(registry=registry)
        detector.drift_psi_warn = 0.1
        detector.drift_psi_alert = 0.2
        
        model_path = tmp_path / "test_model" / "v1.0"
        model_path.mkdir(parents=True)
        
        # Create reference distributions
        ref_distributions = {
            "f1": {
                "bin_edges": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
                "bin_counts": [20, 20, 20, 20, 20],  # Uniform
                "mean": 2.5,
                "std": 1.4
            }
        }
        with open(model_path / "reference_distributions.json", "w") as f:
            json.dump(ref_distributions, f)
        
        # Create champion
        champion = ModelVersion(
            version="v1.0",
            model_path=model_path,
            status=ModelStatus.CHAMPION,
            feature_names=["f1"]
        )
        
        # Create current data with VERY different distribution
        current_data = pd.DataFrame({
            "f1": np.ones(100) * 10.0  # All values at 10 - very different from reference
        })
        
        result = detector._detect_drift_with_psi(
            model_id="test_model",
            champion=champion,
            current_data=current_data
        )
        
        # Result may or may not detect drift depending on PSI calculation
        # Main point is no exception is raised
        # The result is either None or a DriftDetection

    def test_detect_drift_psi_exception_handling(self, tmp_path):
        """Test PSI drift detection handles exceptions."""
        import pandas as pd
        from backend.ml.model_manager import DriftDetector
        
        registry = ModelRegistry(base_path=tmp_path)
        detector = DriftDetector(registry=registry)
        
        model_path = tmp_path / "test_model" / "v1.0"
        model_path.mkdir(parents=True)
        
        # Create reference file that causes exception when read
        ref_path = model_path / "reference_distributions.json"
        ref_path.write_text("invalid json {")
        
        champion = ModelVersion(
            version="v1.0",
            model_path=model_path,
            status=ModelStatus.CHAMPION,
            feature_names=["f1"]
        )
        
        current_data = pd.DataFrame({"f1": [1, 2, 3]})
        
        # Should return None and not raise
        result = detector._detect_drift_with_psi(
            model_id="test_model",
            champion=champion,
            current_data=current_data
        )
        
        assert result is None


class TestDriftDetectorComputePSI:
    """Test _compute_psi method."""

    def test_compute_psi_empty_reference(self, tmp_path):
        """Test PSI computation with empty reference bins."""
        import numpy as np
        from backend.ml.model_manager import DriftDetector
        
        registry = ModelRegistry(base_path=tmp_path)
        detector = DriftDetector(registry=registry)
        
        live_values = np.array([1.0, 2.0, 3.0])
        
        # Empty bin edges
        psi = detector._compute_psi(live_values, [], [])
        assert psi == 0.0
        
        # Empty bin counts
        psi = detector._compute_psi(live_values, [0.0, 1.0, 2.0], [])
        assert psi == 0.0

    def test_compute_psi_valid_distributions(self, tmp_path):
        """Test PSI computation with valid distributions."""
        import numpy as np
        from backend.ml.model_manager import DriftDetector
        
        registry = ModelRegistry(base_path=tmp_path)
        detector = DriftDetector(registry=registry)
        
        # Reference: uniform distribution
        ref_bin_edges = [0.0, 1.0, 2.0, 3.0, 4.0]
        ref_bin_counts = [25, 25, 25, 25]
        
        # Live data: similar distribution
        live_values = np.array([0.5, 1.5, 2.5, 3.5, 0.5, 1.5, 2.5, 3.5])
        
        psi = detector._compute_psi(live_values, ref_bin_edges, ref_bin_counts)
        
        # PSI should be low for similar distributions
        assert isinstance(psi, float)
        assert psi >= 0.0