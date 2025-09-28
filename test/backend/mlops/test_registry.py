"""
Test Module 62: MLOps Model Registry Service

Comprehensive test suite for the model registry functionality including:
- Model registration and management
- Version control and lifecycle
- Artifact storage and retrieval
- Model validation and transitions
- Search and query capabilities
- Storage backend operations
"""

import pytest
import asyncio
import tempfile
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Test imports with fallback handling
try:
    from backend.mlops.registry import (
        ModelStatus, ModelStage, ArtifactType,
        ModelArtifact, ModelVersion, ModelInfo,
        ModelRegistryStorage, ModelValidator, ModelLifecycleManager,
        ModelRegistry, register_model, create_version, get_model_registry
    )
    MODULE_EXISTS = True
except ImportError as e:
    MODULE_EXISTS = False
    print(f"Module import failed: {e}")
    
    # Create mock classes for testing
    class ModelStatus:
        DRAFT = "draft"
        REGISTERED = "registered"
        STAGING = "staging"
        PRODUCTION = "production"
        ARCHIVED = "archived"
        DEPRECATED = "deprecated"
    
    class ModelStage:
        DEVELOPMENT = "development"
        STAGING = "staging"
        PRODUCTION = "production"
        CHAMPION = "champion"
        CHALLENGER = "challenger"
    
    class ArtifactType:
        MODEL = "model"
        PREPROCESSOR = "preprocessor"
        POSTPROCESSOR = "postprocessor"
        METRICS = "metrics"
        LOGS = "logs"
        CONFIG = "config"
        DOCUMENTATION = "documentation"


@pytest.mark.asyncio
class TestModule62BackendMlopsRegistry:
    """Test suite for Module 62: MLOps Model Registry Service."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def sample_model_info(self):
        """Sample model info for testing."""
        if not MODULE_EXISTS:
            return None
        return ModelInfo(
            name="test_model",
            description="Test model for unit testing",
            owner="test_user",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags={"category": "test", "framework": "sklearn"}
        )
    
    @pytest.fixture
    def sample_model_version(self):
        """Sample model version for testing."""
        if not MODULE_EXISTS:
            return None
        return ModelVersion(
            model_name="test_model",
            version="v1.0.0",
            stage=ModelStage.DEVELOPMENT,
            status=ModelStatus.DRAFT,
            description="Initial test version",
            created_by="test_user",
            metrics={"accuracy": 0.95, "precision": 0.92},
            parameters={"learning_rate": 0.01, "max_depth": 10},
            tags={"experiment": "baseline"}
        )
    
    @pytest.fixture
    def sample_artifact_file(self, temp_storage):
        """Create sample artifact file."""
        artifact_path = Path(temp_storage) / "test_model.pkl"
        artifact_path.write_text("mock model content")
        return str(artifact_path)
    
    def test_module_availability(self):
        """Test module import and basic availability."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test enum availability
        assert hasattr(ModelStatus, 'DRAFT')
        assert hasattr(ModelStage, 'DEVELOPMENT')
        assert hasattr(ArtifactType, 'MODEL')
        
        # Test class availability
        assert ModelRegistry is not None
        assert ModelRegistryStorage is not None
        assert ModelValidator is not None
        assert ModelLifecycleManager is not None
    
    def test_model_status_enum(self):
        """Test ModelStatus enum values."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert ModelStatus.DRAFT.value == "draft"
        assert ModelStatus.REGISTERED.value == "registered"
        assert ModelStatus.STAGING.value == "staging"
        assert ModelStatus.PRODUCTION.value == "production"
        assert ModelStatus.ARCHIVED.value == "archived"
        assert ModelStatus.DEPRECATED.value == "deprecated"
    
    def test_model_stage_enum(self):
        """Test ModelStage enum values."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert ModelStage.DEVELOPMENT.value == "development"
        assert ModelStage.STAGING.value == "staging"
        assert ModelStage.PRODUCTION.value == "production"
        assert ModelStage.CHAMPION.value == "champion"
        assert ModelStage.CHALLENGER.value == "challenger"
    
    def test_artifact_type_enum(self):
        """Test ArtifactType enum values."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert ArtifactType.MODEL.value == "model"
        assert ArtifactType.PREPROCESSOR.value == "preprocessor"
        assert ArtifactType.POSTPROCESSOR.value == "postprocessor"
        assert ArtifactType.METRICS.value == "metrics"
        assert ArtifactType.LOGS.value == "logs"
        assert ArtifactType.CONFIG.value == "config"
        assert ArtifactType.DOCUMENTATION.value == "documentation"
    
    def test_model_artifact_creation(self):
        """Test ModelArtifact creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        artifact = ModelArtifact(
            artifact_id="test_artifact_1",
            name="model.pkl",
            type=ArtifactType.MODEL,
            file_path="/path/to/model.pkl",
            size_bytes=1024,
            checksum="abc123"
        )
        
        assert artifact.artifact_id == "test_artifact_1"
        assert artifact.name == "model.pkl"
        assert artifact.type == ArtifactType.MODEL
        assert artifact.file_path == "/path/to/model.pkl"
        assert artifact.size_bytes == 1024
        assert artifact.checksum == "abc123"
        assert isinstance(artifact.created_at, datetime)
        assert isinstance(artifact.metadata, dict)
    
    def test_model_version_creation(self, sample_model_version):
        """Test ModelVersion creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert sample_model_version.model_name == "test_model"
        assert sample_model_version.version == "v1.0.0"
        assert sample_model_version.stage == ModelStage.DEVELOPMENT
        assert sample_model_version.status == ModelStatus.DRAFT
        assert sample_model_version.description == "Initial test version"
        assert sample_model_version.created_by == "test_user"
        assert isinstance(sample_model_version.created_at, datetime)
        assert isinstance(sample_model_version.artifacts, list)
        assert isinstance(sample_model_version.metrics, dict)
        assert isinstance(sample_model_version.parameters, dict)
        assert isinstance(sample_model_version.tags, dict)
    
    def test_model_info_creation(self, sample_model_info):
        """Test ModelInfo creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert sample_model_info.name == "test_model"
        assert sample_model_info.description == "Test model for unit testing"
        assert sample_model_info.owner == "test_user"
        assert isinstance(sample_model_info.created_at, datetime)
        assert isinstance(sample_model_info.updated_at, datetime)
        assert isinstance(sample_model_info.versions, list)
        assert isinstance(sample_model_info.tags, dict)
    
    def test_model_registry_storage_creation(self, temp_storage):
        """Test ModelRegistryStorage creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        storage = ModelRegistryStorage(temp_storage)
        
        assert storage.storage_path == Path(temp_storage)
        assert storage.models_path.exists()
        assert storage.metadata_path.exists()
        assert storage.artifacts_path.exists()
    
    def test_model_info_storage_operations(self, temp_storage, sample_model_info):
        """Test model info save/load operations."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        storage = ModelRegistryStorage(temp_storage)
        
        # Save model info
        success = storage.save_model_info(sample_model_info)
        assert success is True
        
        # Load model info
        loaded_info = storage.load_model_info(sample_model_info.name)
        assert loaded_info is not None
        assert loaded_info.name == sample_model_info.name
        assert loaded_info.description == sample_model_info.description
        assert loaded_info.owner == sample_model_info.owner
        assert loaded_info.tags == sample_model_info.tags
    
    def test_model_version_storage_operations(self, temp_storage, sample_model_version):
        """Test model version save/load operations."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        storage = ModelRegistryStorage(temp_storage)
        
        # Save model version
        success = storage.save_model_version(sample_model_version)
        assert success is True
        
        # Load model version
        loaded_version = storage.load_model_version(
            sample_model_version.model_name, sample_model_version.version
        )
        assert loaded_version is not None
        assert loaded_version.model_name == sample_model_version.model_name
        assert loaded_version.version == sample_model_version.version
        assert loaded_version.stage == sample_model_version.stage
        assert loaded_version.status == sample_model_version.status
        assert loaded_version.description == sample_model_version.description
        assert loaded_version.created_by == sample_model_version.created_by
        assert loaded_version.metrics == sample_model_version.metrics
        assert loaded_version.parameters == sample_model_version.parameters
        assert loaded_version.tags == sample_model_version.tags
    
    def test_artifact_storage_operations(self, temp_storage, sample_artifact_file):
        """Test artifact storage operations."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        storage = ModelRegistryStorage(temp_storage)
        
        # Store artifact
        artifact = storage.store_artifact(
            "test_model", "v1.0.0", "model.pkl", sample_artifact_file
        )
        
        assert artifact is not None
        assert artifact.name == "model.pkl"
        assert artifact.type == ArtifactType.MODEL
        assert artifact.size_bytes > 0
        assert artifact.checksum != ""
        assert Path(artifact.file_path).exists()
    
    def test_model_listing_operations(self, temp_storage, sample_model_info, sample_model_version):
        """Test model and version listing."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        storage = ModelRegistryStorage(temp_storage)
        
        # Initially empty
        models = storage.list_models()
        assert len(models) == 0
        
        # Save model info and version
        storage.save_model_info(sample_model_info)
        storage.save_model_version(sample_model_version)
        
        # List models
        models = storage.list_models()
        assert len(models) == 1
        assert "test_model" in models
        
        # List versions
        versions = storage.list_versions("test_model")
        assert len(versions) == 1
        assert "v1.0.0" in versions
    
    def test_model_validator_name_validation(self):
        """Test model name validation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        validator = ModelValidator()
        
        # Valid names
        valid, error = validator.validate_model_name("valid_model")
        assert valid is True
        assert error == ""
        
        valid, error = validator.validate_model_name("model-123")
        assert valid is True
        
        # Invalid names
        valid, error = validator.validate_model_name("")
        assert valid is False
        assert "empty" in error.lower()
        
        valid, error = validator.validate_model_name("invalid model!")
        assert valid is False
        assert "alphanumeric" in error.lower()
        
        valid, error = validator.validate_model_name("a" * 101)
        assert valid is False
        assert "100 characters" in error
    
    def test_model_validator_version_validation(self):
        """Test version validation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        validator = ModelValidator()
        
        # Valid versions
        valid, error = validator.validate_version("1.0.0")
        assert valid is True
        assert error == ""
        
        valid, error = validator.validate_version("v2.1.3")
        assert valid is True
        
        valid, error = validator.validate_version("1.0.0-beta")
        assert valid is True
        
        # Invalid versions
        valid, error = validator.validate_version("")
        assert valid is False
        assert "empty" in error.lower()
        
        valid, error = validator.validate_version("1.0")
        assert valid is False
        assert "semantic versioning" in error.lower()
        
        valid, error = validator.validate_version("invalid")
        assert valid is False
    
    def test_model_validator_full_validation(self, sample_model_version):
        """Test complete model version validation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        validator = ModelValidator()
        
        # Valid model version
        valid, errors = validator.validate_model_version(sample_model_version)
        assert valid is True
        assert len(errors) == 0
        
        # Invalid model version
        invalid_version = ModelVersion(
            model_name="",  # Invalid name
            version="invalid",  # Invalid version
            stage=ModelStage.DEVELOPMENT,
            status=ModelStatus.DRAFT,
            description="",  # Invalid description
            created_by=""  # Invalid created_by
        )
        
        valid, errors = validator.validate_model_version(invalid_version)
        assert valid is False
        assert len(errors) > 0
    
    def test_model_validator_custom_rules(self, sample_model_version):
        """Test custom validation rules."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        validator = ModelValidator()
        
        # Add custom rule
        def custom_rule(model_version):
            if "test" not in model_version.model_name:
                return False, "Model name must contain 'test'"
            return True, ""
        
        validator.add_validation_rule("custom_test_rule", custom_rule)
        
        # Valid with custom rule
        valid, errors = validator.validate_model_version(sample_model_version)
        assert valid is True
        
        # Invalid with custom rule
        sample_model_version.model_name = "production_model"
        valid, errors = validator.validate_model_version(sample_model_version)
        assert valid is False
        assert any("custom_test_rule" in error for error in errors)
    
    def test_lifecycle_manager_transitions(self):
        """Test model lifecycle transitions."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        lifecycle = ModelLifecycleManager()
        
        # Valid transitions
        assert lifecycle.can_transition(ModelStatus.DRAFT, ModelStatus.REGISTERED) is True
        assert lifecycle.can_transition(ModelStatus.REGISTERED, ModelStatus.STAGING) is True
        assert lifecycle.can_transition(ModelStatus.STAGING, ModelStatus.PRODUCTION) is True
        assert lifecycle.can_transition(ModelStatus.PRODUCTION, ModelStatus.DEPRECATED) is True
        
        # Invalid transitions
        assert lifecycle.can_transition(ModelStatus.DRAFT, ModelStatus.PRODUCTION) is False
        assert lifecycle.can_transition(ModelStatus.ARCHIVED, ModelStatus.PRODUCTION) is False
        
        # Get allowed transitions
        allowed = lifecycle.get_allowed_transitions(ModelStatus.DRAFT)
        assert ModelStatus.REGISTERED in allowed
        assert ModelStatus.ARCHIVED in allowed
    
    def test_lifecycle_manager_status_transition(self, sample_model_version):
        """Test status transition execution."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        lifecycle = ModelLifecycleManager()
        
        # Valid transition
        old_status = sample_model_version.status
        old_updated_at = sample_model_version.updated_at
        
        success, error = lifecycle.transition_status(sample_model_version, ModelStatus.REGISTERED)
        assert success is True
        assert error == ""
        assert sample_model_version.status == ModelStatus.REGISTERED
        assert sample_model_version.updated_at > old_updated_at
        
        # Invalid transition
        success, error = lifecycle.transition_status(sample_model_version, ModelStatus.DRAFT)
        assert success is False
        assert error != ""
    
    async def test_model_registry_creation(self, temp_storage):
        """Test ModelRegistry creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        registry = ModelRegistry(temp_storage)
        
        assert registry.storage is not None
        assert registry.validator is not None
        assert registry.lifecycle_manager is not None
        assert isinstance(registry.metrics, dict)
        assert registry.metrics['models_registered'] == 0
    
    async def test_model_registration(self, temp_storage):
        """Test model registration."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        registry = ModelRegistry(temp_storage)
        
        # Register model
        model_info = await registry.register_model(
            "test_model", "Test model", "test_user", {"category": "test"}
        )
        
        assert model_info.name == "test_model"
        assert model_info.description == "Test model"
        assert model_info.owner == "test_user"
        assert model_info.tags["category"] == "test"
        assert registry.metrics['models_registered'] == 1
        
        # Try to register duplicate
        with pytest.raises(ValueError, match="already exists"):
            await registry.register_model("test_model", "Duplicate", "test_user")
    
    async def test_model_version_creation(self, temp_storage):
        """Test model version creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        registry = ModelRegistry(temp_storage)
        
        # Register model first
        await registry.register_model("test_model", "Test model", "test_user")
        
        # Create version
        model_version = await registry.create_model_version(
            "test_model", "v1.0.0", "Initial version", "test_user",
            stage=ModelStage.DEVELOPMENT,
            metrics={"accuracy": 0.95},
            parameters={"lr": 0.01},
            tags={"experiment": "baseline"}
        )
        
        assert model_version.model_name == "test_model"
        assert model_version.version == "v1.0.0"
        assert model_version.stage == ModelStage.DEVELOPMENT
        assert model_version.status == ModelStatus.DRAFT
        assert model_version.metrics["accuracy"] == 0.95
        assert registry.metrics['versions_created'] == 1
        
        # Try to create duplicate version
        with pytest.raises(ValueError, match="already exists"):
            await registry.create_model_version(
                "test_model", "v1.0.0", "Duplicate", "test_user"
            )
    
    async def test_artifact_addition(self, temp_storage, sample_artifact_file):
        """Test artifact addition to model version."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        registry = ModelRegistry(temp_storage)
        
        # Setup model and version
        await registry.register_model("test_model", "Test model", "test_user")
        await registry.create_model_version(
            "test_model", "v1.0.0", "Initial version", "test_user"
        )
        
        # Add artifact
        artifact = await registry.add_artifact(
            "test_model", "v1.0.0", "model.pkl", sample_artifact_file,
            ArtifactType.MODEL, {"framework": "sklearn"}
        )
        
        assert artifact.name == "model.pkl"
        assert artifact.type == ArtifactType.MODEL
        assert artifact.metadata["framework"] == "sklearn"
        assert registry.metrics['artifacts_stored'] == 1
        
        # Verify artifact in version
        model_version = await registry.get_model_version("test_model", "v1.0.0")
        assert len(model_version.artifacts) == 1
        assert model_version.artifacts[0].name == "model.pkl"
    
    async def test_status_transition(self, temp_storage):
        """Test model status transition."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        registry = ModelRegistry(temp_storage)
        
        # Setup model and version
        await registry.register_model("test_model", "Test model", "test_user")
        await registry.create_model_version(
            "test_model", "v1.0.0", "Initial version", "test_user"
        )
        
        # Transition status
        success = await registry.transition_model_status(
            "test_model", "v1.0.0", ModelStatus.REGISTERED
        )
        assert success is True
        
        # Verify transition
        model_version = await registry.get_model_version("test_model", "v1.0.0")
        assert model_version.status == ModelStatus.REGISTERED
        
        # Try invalid transition
        with pytest.raises(ValueError, match="Cannot transition"):
            await registry.transition_model_status(
                "test_model", "v1.0.0", ModelStatus.DRAFT
            )
    
    async def test_model_retrieval(self, temp_storage):
        """Test model and version retrieval."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        registry = ModelRegistry(temp_storage)
        
        # Setup model and version
        await registry.register_model("test_model", "Test model", "test_user")
        await registry.create_model_version(
            "test_model", "v1.0.0", "Initial version", "test_user"
        )
        
        # Get model info
        model_info = await registry.get_model_info("test_model")
        assert model_info is not None
        assert model_info.name == "test_model"
        
        # Get model version
        model_version = await registry.get_model_version("test_model", "v1.0.0")
        assert model_version is not None
        assert model_version.version == "v1.0.0"
        
        # Get non-existent
        missing_model = await registry.get_model_info("missing_model")
        assert missing_model is None
        
        missing_version = await registry.get_model_version("test_model", "v2.0.0")
        assert missing_version is None
    
    async def test_model_listing(self, temp_storage):
        """Test model and version listing."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        registry = ModelRegistry(temp_storage)
        
        # Initially empty
        models = await registry.list_models()
        assert len(models) == 0
        
        # Add models
        await registry.register_model("model1", "First model", "user1")
        await registry.register_model("model2", "Second model", "user2")
        await registry.create_model_version("model1", "v1.0.0", "Version 1", "user1")
        await registry.create_model_version("model1", "v1.1.0", "Version 2", "user1")
        
        # List models
        models = await registry.list_models()
        assert len(models) == 2
        model_names = [m.name for m in models]
        assert "model1" in model_names
        assert "model2" in model_names
        
        # List versions
        versions = await registry.list_model_versions("model1")
        assert len(versions) == 2
        version_numbers = [v.version for v in versions]
        assert "v1.0.0" in version_numbers
        assert "v1.1.0" in version_numbers
    
    async def test_model_search(self, temp_storage):
        """Test model search functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        registry = ModelRegistry(temp_storage)
        
        # Add test models
        await registry.register_model(
            "fraud_detection", "Fraud detection model", "user1",
            {"category": "classification", "domain": "finance"}
        )
        await registry.register_model(
            "recommendation_engine", "Product recommendation", "user2",
            {"category": "recommendation", "domain": "ecommerce"}
        )
        await registry.register_model(
            "fraud_classifier", "Advanced fraud classifier", "user1",
            {"category": "classification", "domain": "finance"}
        )
        
        # Search by name
        results = await registry.search_models("fraud")
        assert len(results) == 2
        
        # Search by description
        results = await registry.search_models("recommendation")
        assert len(results) == 1  # Found in name "recommendation_engine"
        
        # Search by tags (only models with classification category)
        results = await registry.search_models("", {"category": "classification"})
        assert len(results) == 2  # fraud_detection and fraud_classifier
        
        results = await registry.search_models("", {"domain": "finance"})
        assert len(results) == 2
    
    async def test_registry_metrics(self, temp_storage):
        """Test registry metrics collection."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        registry = ModelRegistry(temp_storage)
        
        # Initial metrics
        metrics = await registry.get_registry_metrics()
        assert metrics['models_registered'] == 0
        assert metrics['versions_created'] == 0
        assert metrics['artifacts_stored'] == 0
        assert metrics['queries_executed'] == 0
        assert metrics['total_models'] == 0
        
        # Add some data
        await registry.register_model("test_model", "Test", "user")
        await registry.create_model_version("test_model", "v1.0.0", "Version", "user")
        await registry.get_model_info("test_model")  # Query
        
        # Updated metrics
        metrics = await registry.get_registry_metrics()
        assert metrics['models_registered'] == 1
        assert metrics['versions_created'] == 1
        assert metrics['queries_executed'] == 1
        assert metrics['total_models'] == 1
    
    async def test_version_cleanup(self, temp_storage):
        """Test old version cleanup."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        registry = ModelRegistry(temp_storage)
        
        # Setup model with multiple versions
        await registry.register_model("test_model", "Test", "user")
        for i in range(10):
            await registry.create_model_version(
                "test_model", f"v1.{i}.0", f"Version {i}", "user"
            )
        
        # Archive old versions
        for i in range(5):
            await registry.transition_model_status(
                "test_model", f"v1.{i}.0", ModelStatus.REGISTERED
            )
            await registry.transition_model_status(
                "test_model", f"v1.{i}.0", ModelStatus.ARCHIVED
            )
        
        # Cleanup (keep latest 7)
        removed = await registry.cleanup_old_versions("test_model", keep_latest=7)
        
        # Should have removed 3 archived versions
        assert removed == 3
        
        # Verify remaining versions
        versions = await registry.list_model_versions("test_model")
        assert len(versions) == 7
    
    async def test_convenience_functions(self, temp_storage):
        """Test convenience functions."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test register_model function
        model_info = await register_model(
            "test_model", "Test model", "test_user",
            registry=ModelRegistry(temp_storage)
        )
        assert model_info.name == "test_model"
        
        # Test create_version function
        model_version = await create_version(
            "test_model", "v1.0.0", "Test version", "test_user",
            registry=ModelRegistry(temp_storage)
        )
        assert model_version.version == "v1.0.0"
        
        # Test get_model_registry function
        registry = get_model_registry(temp_storage)
        assert isinstance(registry, ModelRegistry)
    
    async def test_error_handling(self, temp_storage):
        """Test error handling scenarios."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        registry = ModelRegistry(temp_storage)
        
        # Invalid model name
        with pytest.raises(ValueError, match="Invalid model name"):
            await registry.register_model("", "Test", "user")
        
        # Model not found for version creation
        with pytest.raises(ValueError, match="not found"):
            await registry.create_model_version(
                "missing_model", "v1.0.0", "Test", "user"
            )
        
        # Version not found for artifact addition
        with pytest.raises(ValueError, match="not found"):
            await registry.add_artifact(
                "missing_model", "v1.0.0", "artifact", "/path/to/file"
            )
        
        # Invalid version format
        await registry.register_model("test_model", "Test", "user")
        with pytest.raises(ValueError, match="Validation failed"):
            await registry.create_model_version(
                "test_model", "invalid_version", "Test", "user"
            )
    
    def test_module_exports(self):
        """Test module exports."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        from backend.mlops.registry import __all__
        
        expected_exports = [
            'ModelStatus', 'ModelStage', 'ArtifactType',
            'ModelArtifact', 'ModelVersion', 'ModelInfo',
            'ModelRegistryStorage', 'ModelValidator', 'ModelLifecycleManager',
            'ModelRegistry',
            'register_model', 'create_version', 'get_model_registry'
        ]
        
        for export in expected_exports:
            assert export in __all__, f"Missing export: {export}"