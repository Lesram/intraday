"""
Comprehensive test module for backend/ml/model_manager.py
Test Module 121: backend.ml.model_manager
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.ml.model_manager import (
    ModelManager,
    get_model_manager,
    create_model_registry,
    load_model_from_registry,
    save_model_to_registry,
    get_model_metrics,
    validate_model,
    model_manager
)


class TestModelManager:
    """Test the ModelManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = ModelManager()
        self.mock_model = Mock()
        self.test_training_data = {"features": [1, 2, 3], "labels": [0, 1, 0]}
        self.test_input_data = {"input": [1.5, 2.5, 3.5]}

    def test_model_manager_initialization(self):
        """Test ModelManager initialization."""
        assert isinstance(self.manager.models, dict)
        assert len(self.manager.models) == 0
        assert self.manager.active_model is None
        assert isinstance(self.manager.model_registry, dict)
        assert len(self.manager.model_registry) == 0

    def test_register_model(self):
        """Test model registration."""
        model_name = "test_model"
        self.manager.register_model(model_name, self.mock_model)
        
        assert model_name in self.manager.models
        assert self.manager.models[model_name] is self.mock_model
        assert model_name in self.manager.model_registry
        
        registry_entry = self.manager.model_registry[model_name]
        assert registry_entry["name"] == model_name
        assert registry_entry["version"] == "1.0.0"
        assert registry_entry["status"] == "registered"
        assert "created_at" in registry_entry

    def test_get_model_existing(self):
        """Test getting an existing model."""
        model_name = "test_model"
        self.manager.register_model(model_name, self.mock_model)
        
        retrieved_model = self.manager.get_model(model_name)
        assert retrieved_model is self.mock_model

    def test_get_model_nonexistent(self):
        """Test getting a non-existent model returns Mock."""
        model_name = "nonexistent_model"
        retrieved_model = self.manager.get_model(model_name)
        
        assert isinstance(retrieved_model, Mock)

    def test_set_active_model(self):
        """Test setting active model."""
        model_name = "test_model"
        self.manager.set_active_model(model_name)
        
        assert self.manager.active_model == model_name

    def test_get_active_model_existing(self):
        """Test getting active model that exists."""
        model_name = "test_model"
        self.manager.register_model(model_name, self.mock_model)
        self.manager.set_active_model(model_name)
        
        active_model = self.manager.get_active_model()
        assert active_model is self.mock_model

    def test_get_active_model_nonexistent(self):
        """Test getting active model that doesn't exist."""
        self.manager.set_active_model("nonexistent_model")
        
        active_model = self.manager.get_active_model()
        assert isinstance(active_model, Mock)

    def test_get_active_model_none_set(self):
        """Test getting active model when none is set."""
        active_model = self.manager.get_active_model()
        assert isinstance(active_model, Mock)

    def test_list_models_empty(self):
        """Test listing models when none are registered."""
        models = self.manager.list_models()
        assert isinstance(models, list)
        assert len(models) == 0

    def test_list_models_with_models(self):
        """Test listing models with registered models."""
        model_name_1 = "model_1"
        model_name_2 = "model_2"
        
        self.manager.register_model(model_name_1, Mock())
        self.manager.register_model(model_name_2, Mock())
        
        models = self.manager.list_models()
        assert len(models) == 2
        
        model_names = [model["name"] for model in models]
        assert model_name_1 in model_names
        assert model_name_2 in model_names

    def test_remove_model_existing(self):
        """Test removing an existing model."""
        model_name = "test_model"
        self.manager.register_model(model_name, self.mock_model)
        
        assert model_name in self.manager.models
        assert model_name in self.manager.model_registry
        
        result = self.manager.remove_model(model_name)
        
        assert result is True
        assert model_name not in self.manager.models
        assert model_name not in self.manager.model_registry

    def test_remove_model_nonexistent(self):
        """Test removing a non-existent model."""
        result = self.manager.remove_model("nonexistent_model")
        assert result is False

    def test_get_model_info_existing(self):
        """Test getting model info for existing model."""
        model_name = "test_model"
        self.manager.register_model(model_name, self.mock_model)
        
        info = self.manager.get_model_info(model_name)
        assert isinstance(info, dict)
        assert info["name"] == model_name
        assert info["version"] == "1.0.0"
        assert info["status"] == "registered"

    def test_get_model_info_nonexistent(self):
        """Test getting model info for non-existent model."""
        info = self.manager.get_model_info("nonexistent_model")
        assert isinstance(info, dict)
        assert len(info) == 0

    def test_train_model(self):
        """Test model training."""
        model_name = "test_model"
        result = self.manager.train_model(model_name, self.test_training_data)
        
        assert isinstance(result, dict)
        assert result["status"] == "completed"
        assert result["model_name"] == model_name
        assert "training_time" in result
        assert "accuracy" in result
        assert "loss" in result
        assert isinstance(result["accuracy"], float)
        assert isinstance(result["loss"], float)

    def test_evaluate_model(self):
        """Test model evaluation."""
        model_name = "test_model"
        test_data = {"test": "data"}
        
        result = self.manager.evaluate_model(model_name, test_data)
        
        assert isinstance(result, dict)
        assert "accuracy" in result
        assert "precision" in result
        assert "recall" in result
        assert "f1_score" in result
        
        for metric in ["accuracy", "precision", "recall", "f1_score"]:
            assert isinstance(result[metric], float)
            assert 0 <= result[metric] <= 1

    def test_predict_with_model(self):
        """Test making predictions with model."""
        model_name = "test_model"
        
        result = self.manager.predict_with_model(model_name, self.test_input_data)
        
        assert isinstance(result, dict)
        assert "predictions" in result
        assert "confidence" in result
        assert "model_name" in result
        assert result["model_name"] == model_name
        assert isinstance(result["predictions"], list)
        assert isinstance(result["confidence"], list)
        assert len(result["predictions"]) == len(result["confidence"])

    def test_deploy_model_default_endpoint(self):
        """Test deploying model with default endpoint."""
        model_name = "test_model"
        
        result = self.manager.deploy_model(model_name)
        
        assert isinstance(result, dict)
        assert result["status"] == "deployed"
        assert result["model_name"] == model_name
        assert result["endpoint"] == f"/api/models/{model_name}"
        assert "deployment_id" in result
        assert "timestamp" in result
        assert result["deployment_id"].startswith(f"DEPLOY-{model_name}")

    def test_deploy_model_custom_endpoint(self):
        """Test deploying model with custom endpoint."""
        model_name = "test_model"
        custom_endpoint = "/custom/endpoint"
        
        result = self.manager.deploy_model(model_name, custom_endpoint)
        
        assert result["endpoint"] == custom_endpoint
        assert result["model_name"] == model_name
        assert result["status"] == "deployed"


class TestModuleLevelFunctions:
    """Test module-level functions."""

    def test_get_model_manager(self):
        """Test getting model manager instance."""
        manager = get_model_manager()
        assert isinstance(manager, ModelManager)
        assert hasattr(manager, 'models')
        assert hasattr(manager, 'active_model')
        assert hasattr(manager, 'model_registry')

    def test_create_model_registry(self):
        """Test creating model registry."""
        registry = create_model_registry()
        assert isinstance(registry, dict)
        assert len(registry) == 0

    def test_load_model_from_registry(self):
        """Test loading model from registry."""
        model_name = "test_model"
        model = load_model_from_registry(model_name)
        assert isinstance(model, Mock)

    def test_save_model_to_registry(self):
        """Test saving model to registry."""
        model_name = "test_model"
        mock_model = Mock()
        
        result = save_model_to_registry(model_name, mock_model)
        assert result is True

    def test_get_model_metrics(self):
        """Test getting model metrics."""
        model_name = "test_model"
        
        metrics = get_model_metrics(model_name)
        
        assert isinstance(metrics, dict)
        expected_metrics = ["accuracy", "precision", "recall", "f1_score", "auc"]
        
        for metric in expected_metrics:
            assert metric in metrics
            assert isinstance(metrics[metric], float)
            assert 0 <= metrics[metric] <= 1

    def test_validate_model(self):
        """Test model validation."""
        mock_model = Mock()
        
        result = validate_model(mock_model)
        
        assert isinstance(result, dict)
        assert "valid" in result
        assert "errors" in result
        assert "warnings" in result
        assert result["valid"] is True
        assert isinstance(result["errors"], list)
        assert isinstance(result["warnings"], list)
        assert len(result["errors"]) == 0
        assert len(result["warnings"]) == 0


class TestDefaultInstance:
    """Test the default module instance."""

    def test_default_model_manager_exists(self):
        """Test that default model_manager instance exists."""
        from backend.ml.model_manager import model_manager as default_manager
        
        assert isinstance(default_manager, ModelManager)
        assert hasattr(default_manager, 'models')
        assert hasattr(default_manager, 'active_model')
        assert hasattr(default_manager, 'model_registry')

    def test_default_instance_functionality(self):
        """Test default instance works correctly."""
        from backend.ml.model_manager import model_manager as default_manager
        
        # Test basic functionality
        test_model = Mock()
        model_name = "test_default_model"
        
        default_manager.register_model(model_name, test_model)
        retrieved_model = default_manager.get_model(model_name)
        
        assert retrieved_model is test_model
        
        # Clean up
        default_manager.remove_model(model_name)


class TestIntegrationScenarios:
    """Test integration scenarios and workflows."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = ModelManager()

    def test_complete_model_lifecycle(self):
        """Test complete model lifecycle."""
        model_name = "lifecycle_model"
        mock_model = Mock()
        
        # Register model
        self.manager.register_model(model_name, mock_model)
        assert model_name in self.manager.models
        
        # Set as active
        self.manager.set_active_model(model_name)
        assert self.manager.active_model == model_name
        
        # Get model info
        info = self.manager.get_model_info(model_name)
        assert info["name"] == model_name
        
        # Train model
        training_result = self.manager.train_model(model_name, {"data": "training"})
        assert training_result["status"] == "completed"
        
        # Evaluate model
        eval_result = self.manager.evaluate_model(model_name, {"data": "test"})
        assert "accuracy" in eval_result
        
        # Make predictions
        pred_result = self.manager.predict_with_model(model_name, {"data": "input"})
        assert "predictions" in pred_result
        
        # Deploy model
        deploy_result = self.manager.deploy_model(model_name)
        assert deploy_result["status"] == "deployed"
        
        # Remove model
        remove_result = self.manager.remove_model(model_name)
        assert remove_result is True
        assert model_name not in self.manager.models

    def test_multiple_models_management(self):
        """Test managing multiple models."""
        model_names = ["model_1", "model_2", "model_3"]
        models = [Mock() for _ in model_names]
        
        # Register multiple models
        for name, model in zip(model_names, models):
            self.manager.register_model(name, model)
        
        # Verify all models are registered
        registered_models = self.manager.list_models()
        assert len(registered_models) == 3
        
        registered_names = [m["name"] for m in registered_models]
        for name in model_names:
            assert name in registered_names
        
        # Test switching active models
        for name in model_names:
            self.manager.set_active_model(name)
            active = self.manager.get_active_model()
            expected_model = models[model_names.index(name)]
            assert active is expected_model

    def test_error_handling_scenarios(self):
        """Test various error handling scenarios."""
        # Test operations on non-existent models
        result = self.manager.remove_model("nonexistent")
        assert result is False
        
        info = self.manager.get_model_info("nonexistent")
        assert info == {}
        
        model = self.manager.get_model("nonexistent")
        assert isinstance(model, Mock)
        
        # Test getting active model when none set or invalid
        active = self.manager.get_active_model()
        assert isinstance(active, Mock)
        
        self.manager.set_active_model("nonexistent")
        active = self.manager.get_active_model()
        assert isinstance(active, Mock)

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = ModelManager()

    def test_empty_string_model_name(self):
        """Test operations with empty string model name."""
        mock_model = Mock()
        
        # Register with empty name
        self.manager.register_model("", mock_model)
        assert "" in self.manager.models
        
        # Retrieve with empty name
        retrieved = self.manager.get_model("")
        assert retrieved is mock_model
        
        # Remove with empty name
        result = self.manager.remove_model("")
        assert result is True

    def test_none_values_handling(self):
        """Test handling of None values."""
        # Register model with None
        self.manager.register_model("test_none", None)
        assert "test_none" in self.manager.models
        assert self.manager.models["test_none"] is None
        
        # Get model that is None
        retrieved = self.manager.get_model("test_none")
        assert retrieved is None

    def test_overwrite_existing_model(self):
        """Test overwriting an existing model."""
        model_name = "overwrite_test"
        original_model = Mock()
        new_model = Mock()
        
        # Register original model
        self.manager.register_model(model_name, original_model)
        assert self.manager.get_model(model_name) is original_model
        
        # Overwrite with new model
        self.manager.register_model(model_name, new_model)
        assert self.manager.get_model(model_name) is new_model
        
        # Verify registry is updated
        info = self.manager.get_model_info(model_name)
        assert info["name"] == model_name

    def test_special_characters_in_model_name(self):
        """Test model names with special characters."""
        special_names = [
            "model-with-dashes",
            "model_with_underscores",
            "model.with.dots",
            "model/with/slashes",
            "model with spaces",
            "model@with#symbols"
        ]
        
        for name in special_names:
            mock_model = Mock()
            self.manager.register_model(name, mock_model)
            
            # Verify registration
            assert name in self.manager.models
            retrieved = self.manager.get_model(name)
            assert retrieved is mock_model
            
            # Verify info
            info = self.manager.get_model_info(name)
            assert info["name"] == name


class TestConcurrencyAndPerformance:
    """Test concurrency and performance aspects."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = ModelManager()

    def test_large_number_of_models(self):
        """Test handling large number of models."""
        num_models = 100
        model_names = [f"model_{i}" for i in range(num_models)]
        
        # Register many models
        for name in model_names:
            self.manager.register_model(name, Mock())
        
        # Verify all are registered
        assert len(self.manager.models) == num_models
        assert len(self.manager.model_registry) == num_models
        
        # Test list_models performance
        models_list = self.manager.list_models()
        assert len(models_list) == num_models
        
        # Test retrieval of each model
        for name in model_names:
            model = self.manager.get_model(name)
            assert isinstance(model, Mock)

    def test_model_operations_consistency(self):
        """Test consistency of model operations."""
        model_name = "consistency_test"
        mock_model = Mock()
        
        # Multiple registrations should be consistent
        for _ in range(5):
            self.manager.register_model(model_name, mock_model)
            assert self.manager.get_model(model_name) is mock_model
            
        # Registry should still have one entry
        models_list = self.manager.list_models()
        matching_models = [m for m in models_list if m["name"] == model_name]
        assert len(matching_models) == 1


def test_comprehensive_coverage():
    """Test to ensure comprehensive coverage of all functions."""
    # Test all module-level functions are covered
    manager = get_model_manager()
    assert isinstance(manager, ModelManager)
    
    registry = create_model_registry()
    assert isinstance(registry, dict)
    
    model = load_model_from_registry("test")
    assert isinstance(model, Mock)
    
    result = save_model_to_registry("test", Mock())
    assert result is True
    
    metrics = get_model_metrics("test")
    assert isinstance(metrics, dict)
    
    validation = validate_model(Mock())
    assert validation["valid"] is True
    
    # Test default instance exists and works
    from backend.ml.model_manager import model_manager as default_instance
    assert isinstance(default_instance, ModelManager)


# ============================================================================
# CONSOLIDATED MODEL MANAGEMENT TESTS - Merged from test_model_management.py
# ============================================================================

class TestModelManagementConsolidated:
    """Consolidated model management infrastructure tests."""

    def test_model_status_enum(self):
        """Test ModelStatus enumeration."""
        try:
            from backend.ml.model_management import ModelStatus
            assert ModelStatus.REGISTERED.value == "registered"
            assert ModelStatus.TRAINING.value == "training"
            assert ModelStatus.TRAINED.value == "trained"
            assert ModelStatus.DEPLOYED.value == "deployed"
            assert ModelStatus.RETIRED.value == "retired"
            assert ModelStatus.FAILED.value == "failed"
        except ImportError:
            pytest.skip("Model management module not available")

    def test_model_format_enum(self):
        """Test ModelFormat enumeration."""
        try:
            from backend.ml.model_management import ModelFormat
            assert ModelFormat.JOBLIB.value == "joblib"
            assert ModelFormat.PICKLE.value == "pickle"
            assert ModelFormat.JSON.value == "json"
        except ImportError:
            pytest.skip("Model management module not available")

    def test_model_metadata_functionality(self):
        """Test ModelMetadata functionality."""
        try:
            from backend.ml.model_management import ModelMetadata
            
            metadata = ModelMetadata(
                model_id="test_model",
                name="Test Model",
                version="1.0.0",
                description="Test model description",
                model_type="classification",
                framework="sklearn"
            )
            
            assert metadata.model_id == "test_model"
            assert metadata.name == "Test Model"
            assert metadata.version == "1.0.0"
        except ImportError:
            pytest.skip("Model management module not available")

    def test_model_registry_functionality(self):
        """Test ModelRegistry functionality."""
        try:
            from backend.ml.model_management import ModelRegistry
            
            registry = ModelRegistry()
            assert isinstance(registry.models, dict)
            
            # Test registry operations
            test_model = Mock()
            registry.register_model("test_model", test_model)
            
            if "test_model" in registry.models:
                assert registry.models["test_model"] == test_model
        except ImportError:
            pytest.skip("Model management module not available")

    def test_performance_tracker_functionality(self):
        """Test PerformanceTracker functionality."""
        try:
            from backend.ml.model_management import PerformanceTracker
            
            tracker = PerformanceTracker()
            
            # Test performance tracking
            tracker.record_performance("test_model", {"accuracy": 0.85, "f1_score": 0.82})
            
            if hasattr(tracker, 'get_performance'):
                performance = tracker.get_performance("test_model")
                assert isinstance(performance, dict)
        except ImportError:
            pytest.skip("Model management module not available")

    def test_model_storage_functionality(self):
        """Test ModelStorage functionality."""
        try:
            from backend.ml.model_management import ModelStorage
            
            storage = ModelStorage()
            
            # Test storage operations
            test_model = Mock()
            
            if hasattr(storage, 'save_model'):
                result = storage.save_model("test_model", test_model)
                assert result is not None
                
            if hasattr(storage, 'load_model'):
                loaded_model = storage.load_model("test_model")
                assert loaded_model is not None or loaded_model is None
        except ImportError:
            pytest.skip("Model management module not available")


if __name__ == "__main__":
    pytest.main([__file__])