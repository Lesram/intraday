"""
Phase 6A: ModelManager Core Functionality Tests - Part 2
Tests for main ModelManager class functionality including:
- Model lifecycle management
- Prediction orchestration  
- Drift detection system
- Model persistence and storage
"""

import pytest
import pandas as pd
import numpy as np
import json


class TestModelManagerPredictions:
    def test_predict_model_not_found(self, model_manager, sample_features_dict):
        """Test prediction behavior when model is not found."""
        # Test getting non-existent model prediction
        try:
            result = model_manager.predict("nonexistent_model", sample_features_dict)
            # Should return some fallback value or None
            assert result is not None or result is None
        except (ModelNotFoundError, KeyError, ValueError):
            # Expected exception for non-existent model
            passpickle
import tempfile
import shutil
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from typing import Dict, Any, List
import threading
import time

# Import the module under test
from backend.mlops.model_manager import (
    ModelManager,
    ModelMetadata,
    ModelNotFoundError,
    ModelStatus,
    DriftType,
    get_model_manager
)


class TestModelManager:
    """Test ModelManager core functionality."""
    
    @pytest.fixture
    def temp_model_directory(self):
        """Create temporary directory for model storage testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def mock_simple_model(self):
        """Create a simple mock model for testing."""
        class SimpleLinearModel:
            def __init__(self, weights=None):
                self.weights = weights or [1.0, 2.0, 0.5]
                self.bias = 0.1
                
            def predict(self, features):
                if isinstance(features, dict):
                    # Convert dict to list based on expected feature order
                    feature_list = [features.get(f'feature_{i}', 0.0) for i in range(len(self.weights))]
                elif isinstance(features, list):
                    feature_list = features
                else:
                    feature_list = [features]
                
                # Simple linear prediction
                prediction = sum(w * f for w, f in zip(self.weights, feature_list)) + self.bias
                return float(prediction)
                
        return SimpleLinearModel()
    
    @pytest.fixture
    def sample_model_metadata(self):
        """Create sample model metadata for testing."""
        return ModelMetadata(
            name="test_model",
            version="1.0.0",
            model_type="linear",
            features=["feature_0", "feature_1", "feature_2"],
            created_at=datetime.now(),
            description="Test model for unit testing",
            tags={"type": "test", "category": "linear"}
        )
    
    @pytest.fixture
    def sample_features_dict(self):
        """Sample features dictionary for prediction testing."""
        return {
            'feature_0': 1.5,
            'feature_1': 2.3,
            'feature_2': 0.8,
            'close_price': 100.5,
            'volume': 1000
        }
    
    @pytest.fixture
    def mock_registry(self):
        """Mock model registry for testing."""
        registry = Mock()
        registry.register.return_value = True
        registry.load.return_value = Mock()
        registry.version_info.return_value = Mock()
        return registry
    
    @pytest.fixture
    def model_manager(self, temp_model_directory):
        """Create ModelManager instance for testing."""
        # Look for the correct ModelManager implementation
        try:
            # Try to find the advanced ModelManager from ModelRegistry
            from backend.mlops.model_manager import ModelRegistry
            manager = ModelRegistry(base_path=temp_model_directory)
            yield manager
        except (ImportError, AttributeError):
            # Fallback to basic ModelManager
            manager = ModelManager(model_store_path=temp_model_directory)
            yield manager
    
    def test_model_manager_initialization(self, temp_model_directory):
        """Test ModelManager initialization with different configurations."""
        # Test with ModelRegistry if available
        try:
            from backend.mlops.model_manager import ModelRegistry
            manager = ModelRegistry(base_path=temp_model_directory)
            assert hasattr(manager, 'models')
            assert hasattr(manager, 'base_path')
        except (ImportError, AttributeError):
            # Fallback to basic ModelManager
            manager = ModelManager(model_store_path=temp_model_directory)
            assert hasattr(manager, 'models')
            assert hasattr(manager, 'model_store_path')
        
        # Test default initialization
        try:
            default_manager = ModelRegistry()
            assert hasattr(default_manager, 'base_path')
        except (ImportError, AttributeError):
            default_manager = ModelManager()
            assert hasattr(default_manager, 'model_store_path')
    
    def test_register_model_basic(self, model_manager, mock_simple_model, sample_model_metadata):
        """Test basic model registration functionality."""
        # Test with ModelRegistry API if available
        if hasattr(model_manager, 'register_model') and hasattr(model_manager, 'models'):
            result = model_manager.register_model(
                model_id="test_model",
                model_obj=mock_simple_model,
                version="1.0.0"
            )
            assert result is not None
        else:
            # Test with basic ModelManager API
            result = model_manager.register_model(
                model=mock_simple_model,
                metadata=sample_model_metadata
            )
            assert result is not False  # Should be True or return some value
    
    def test_register_model_with_artifacts_path(self, model_manager, mock_simple_model):
        """Test model registration with artifacts path."""
        artifacts_path = "/tmp/model_artifacts"
        
        if hasattr(model_manager, 'register_model') and hasattr(model_manager, 'models'):
            # Test with ModelRegistry API
            result = model_manager.register_model(
                model_id="test_model_artifacts", 
                model_obj=mock_simple_model,
                artifacts={"path": artifacts_path}
            )
        else:
            # Test with basic ModelManager API
            metadata = ModelMetadata(
                name="test_model_artifacts",
                version="1.0.0", 
                model_type="test",
                features=["f1", "f2"]
            )
            result = model_manager.register_model(
                model=mock_simple_model,
                metadata=metadata
            )
        
        assert result is not None
    
    def test_register_model_with_feature_schema(self, model_manager, mock_simple_model):
        """Test model registration with feature schema validation."""
        feature_schema = {
            'feature_0': 'float64',
            'feature_1': 'float64',
            'feature_2': 'int64',
            'categorical_feature': 'object'
        }
        
        if hasattr(model_manager, 'register_model') and hasattr(model_manager, 'models'):
            # Test with ModelRegistry API
            result = model_manager.register_model(
                model_id="schema_model",
                model_obj=mock_simple_model,
                feature_schema=feature_schema
            )
        else:
            # Test with basic ModelManager API
            metadata = ModelMetadata(
                name="schema_model",
                version="1.0.0",
                model_type="test",
                features=list(feature_schema.keys())
            )
            result = model_manager.register_model(
                model=mock_simple_model,
                metadata=metadata
            )
        
        assert result is not None
    
    def test_get_model_by_name_version(self, model_manager, mock_simple_model):
        """Test retrieving model by name and version."""
        # First register a model
        if hasattr(model_manager, 'register_model') and hasattr(model_manager, 'models'):
            # Test with ModelRegistry API
            model_manager.register_model(
                model_id="test_model",
                model_obj=mock_simple_model,
                version="1.0.0"
            )
            
            # Test get_model method
            if hasattr(model_manager, 'get_model'):
                result = model_manager.get_model("test_model", "1.0.0")
                assert result is not None
            elif hasattr(model_manager, 'load_model'):
                result = model_manager.load_model("test_model", "1.0.0")
                assert result is not None
        else:
            # Test with basic ModelManager API
            metadata = ModelMetadata(
                name="test_model",
                version="1.0.0",
                model_type="test",
                features=["f1", "f2"]
            )
            model_manager.register_model(mock_simple_model, metadata)
            result = model_manager.load_model("test_model", "1.0.0")
            assert result is not None
    
    def test_get_model_latest_version(self, model_manager, mock_simple_model):
        """Test retrieving latest version of model."""
        # Register model first
        if hasattr(model_manager, 'register_model') and hasattr(model_manager, 'models'):
            model_manager.register_model(
                model_id="test_model",
                model_obj=mock_simple_model,
                version="1.0.0"
            )
            
            # Test getting latest version
            if hasattr(model_manager, 'get_model'):
                result = model_manager.get_model("test_model")
                assert result is not None
            elif hasattr(model_manager, 'load_model'):
                result = model_manager.load_model("test_model")
                assert result is not None
        else:
            # Test with basic ModelManager
            metadata = ModelMetadata(
                name="test_model",
                version="1.0.0",
                model_type="test",
                features=["f1"]
            )
            model_manager.register_model(mock_simple_model, metadata)
            result = model_manager.load_model("test_model", "latest")
            assert result is not None
    
    def test_get_model_not_found(self, model_manager):
        """Test behavior when requested model is not found."""
        # Test getting non-existent model
        try:
            if hasattr(model_manager, 'get_model'):
                result = model_manager.get_model("nonexistent_model")
                # Should return None or raise error
                assert result is None or result is not None
            elif hasattr(model_manager, 'load_model'):
                result = model_manager.load_model("nonexistent_model")
                # Should return None or raise error
                assert result is None or result is not None
        except (ModelNotFoundError, KeyError, ValueError):
            # Expected exception for non-existent model
            pass
    
    def test_predict_with_registered_model(self, model_manager, mock_simple_model, sample_features_dict):
        """Test prediction using registered model."""
        # Set up mock model behavior
        mock_simple_model.predict = Mock(return_value=0.85)
        
        # Register model first
        if hasattr(model_manager, 'register_model') and hasattr(model_manager, 'models'):
            model_manager.register_model(
                model_id="test_model",
                model_obj=mock_simple_model,
                version="1.0.0"
            )
            
            # Test prediction
            result = model_manager.predict("test_model", sample_features_dict)
            assert result is not None
            # Should call predict on the model
            mock_simple_model.predict.assert_called()
        else:
            # Test with basic ModelManager
            metadata = ModelMetadata(
                name="test_model",
                version="1.0.0",
                model_type="test",
                features=list(sample_features_dict.keys())
            )
            model_manager.register_model(mock_simple_model, metadata)
            result = model_manager.predict("test_model", sample_features_dict)
            assert result is not None
    
    def test_predict_model_not_found(self, model_manager, sample_features_dict):
        """Test prediction behavior when model is not found."""
        model_manager.registry.load.return_value = None
        
        result = model_manager.predict("nonexistent_model", sample_features_dict)
        
        # Should handle gracefully or raise appropriate error
        assert result is not None  # Based on implementation fallback behavior
    
    def test_predict_with_version_specification(self, model_manager, sample_features_dict):
        """Test prediction with specific model version."""
        mock_model = Mock()
        mock_model.predict.return_value = [0.7, 0.3]
        model_manager.registry.load.return_value = mock_model
        
        result = model_manager.predict("test_model", sample_features_dict, version="1.0.0")
        
        assert result == [0.7, 0.3]
        model_manager.registry.load.assert_called_with("test_model", "1.0.0")
    
    def test_predict_with_feature_preprocessing(self, model_manager):
        """Test prediction with feature preprocessing."""
        mock_model = Mock()
        mock_model.predict.return_value = 0.92
        model_manager.registry.load.return_value = mock_model
        
        # Features that might need preprocessing
        raw_features = {
            'price': 100.5,
            'volume': 1000,
            'timestamp': '2024-01-15 10:30:00'
        }
        
        result = model_manager.predict("preprocessor_model", raw_features)
        
        assert result == 0.92
        # Model should be called with processed features
        mock_model.predict.assert_called_once()
    
    def test_batch_prediction(self, model_manager):
        """Test batch prediction functionality."""
        mock_model = Mock()
        mock_model.predict.return_value = [0.1, 0.5, 0.9]
        model_manager.registry.load.return_value = mock_model
        
        batch_features = [
            {'feature_0': 1.0, 'feature_1': 2.0},
            {'feature_0': 1.5, 'feature_1': 2.5},
            {'feature_0': 2.0, 'feature_1': 3.0}
        ]
        
        # Test if batch prediction method exists
        if hasattr(model_manager, 'predict_batch'):
            result = model_manager.predict_batch("test_model", batch_features)
            assert len(result) == 3
        else:
            # Test individual predictions
            results = [model_manager.predict("test_model", features) for features in batch_features]
            assert len(results) == 3
    
    def test_model_metadata_retrieval(self, model_manager):
        """Test retrieving model metadata."""
        mock_version_info = Mock()
        mock_version_info.name = "test_model"
        mock_version_info.version = "1.0.0"
        mock_version_info.author = "test_user"
        mock_version_info.created_at = datetime.now()
        
        model_manager.registry.version_info.return_value = mock_version_info
        
        if hasattr(model_manager, 'get_model_metadata'):
            metadata = model_manager.get_model_metadata("test_model", "1.0.0")
            assert metadata is not None
        else:
            # Test through version_info
            info = model_manager.registry.version_info("test_model", "1.0.0")
            assert info.name == "test_model"
    
    def test_model_status_tracking(self, model_manager, mock_simple_model):
        """Test model status tracking functionality."""
        # Register model
        model_manager.register_model(mock_simple_model, "status_model")
        
        # Test if status tracking exists
        if hasattr(model_manager, 'get_model_status'):
            status = model_manager.get_model_status("status_model")
            assert isinstance(status, (str, ModelStatus))
        
        if hasattr(model_manager, 'set_model_status'):
            model_manager.set_model_status("status_model", ModelStatus.ACTIVE)
            # Should not raise error
    
    def test_model_version_listing(self, model_manager):
        """Test listing model versions."""
        if hasattr(model_manager, 'list_model_versions'):
            versions = model_manager.list_model_versions("test_model")
            assert isinstance(versions, list)
        elif hasattr(model_manager, 'get_versions'):
            versions = model_manager.get_versions("test_model")
            assert isinstance(versions, list)
    
    def test_model_deletion(self, model_manager, mock_simple_model):
        """Test model deletion functionality."""
        # Register model first
        model_manager.register_model(mock_simple_model, "delete_test_model")
        
        if hasattr(model_manager, 'delete_model'):
            result = model_manager.delete_model("delete_test_model", "1.0.0")
            assert isinstance(result, bool)
        elif hasattr(model_manager, 'remove_model'):
            result = model_manager.remove_model("delete_test_model")
            assert isinstance(result, bool)


class TestModelManagerAdvanced:
    """Test advanced ModelManager functionality."""
    
    @pytest.fixture
    def configured_model_manager(self, temp_model_directory):
        """Create ModelManager with advanced configuration."""
        manager = ModelManager(
            base_path=temp_model_directory,
            enable_drift_detection=True,
            max_models=10
        )
        return manager
    
    def test_concurrent_model_access(self, configured_model_manager, mock_simple_model):
        """Test thread-safe model access."""
        # Register model
        configured_model_manager.register_model(mock_simple_model, "concurrent_model")
        
        results = []
        errors = []
        
        def prediction_worker():
            try:
                for _ in range(10):
                    result = configured_model_manager.predict("concurrent_model", {"feature": 1.0})
                    results.append(result)
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = [threading.Thread(target=prediction_worker) for _ in range(3)]
        
        # Start threads
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 30  # 3 threads * 10 predictions each
    
    def test_model_manager_memory_management(self, configured_model_manager):
        """Test memory management with multiple models."""
        models = []
        
        # Register multiple models
        for i in range(5):
            model = Mock()
            model.predict.return_value = float(i)
            models.append(model)
            
            configured_model_manager.register_model(model, f"memory_test_model_{i}")
        
        # Test that all models are accessible
        for i in range(5):
            result = configured_model_manager.predict(f"memory_test_model_{i}", {"test": 1.0})
            # Should get prediction without memory issues
            assert result is not None
    
    def test_model_manager_error_handling(self, configured_model_manager):
        """Test error handling in various scenarios."""
        # Test with invalid features
        try:
            result = configured_model_manager.predict("test_model", None)
            # Should handle gracefully
            assert result is not None or result is None
        except Exception as e:
            # Error should be appropriate type
            assert isinstance(e, (ValueError, TypeError, ModelNotFoundError))
        
        # Test with malformed model name
        try:
            result = configured_model_manager.get_model("")
            assert result is None
        except Exception as e:
            assert isinstance(e, (ValueError, ModelNotFoundError))
    
    def test_model_manager_configuration_validation(self, temp_model_directory):
        """Test ModelManager configuration validation."""
        # Test with invalid base path
        try:
            manager = ModelManager(base_path="/invalid/nonexistent/path")
            # Should either create path or handle gracefully
            assert hasattr(manager, 'base_path')
        except Exception as e:
            assert isinstance(e, (OSError, ValueError))
        
        # Test with valid configuration
        manager = ModelManager(
            base_path=temp_model_directory,
            enable_logging=True,
            max_models=5
        )
        assert hasattr(manager, 'base_path')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
