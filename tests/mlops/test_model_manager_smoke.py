"""
Smoke tests for MLOps model manager functionality.
Tests basic register/load/predict operations and error handling.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
from backend.mlops.model_manager import ModelManager, ModelMetadata, ModelNotFoundError


class TestModelManagerSmoke:
    """Smoke tests for basic ModelManager functionality."""

    def setup_method(self):
        """Set up test environment with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.model_manager = ModelManager(model_store_path=self.temp_dir)

    def teardown_method(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_register_model_basic(self):
        """Test basic model registration."""
        # Create a mock model
        mock_model = Mock()
        mock_model.predict = Mock(return_value=[0.5, 0.3, 0.8])
        
        metadata = ModelMetadata(
            name="test_model",
            version="1.0",
            model_type="classification",
            features=["feature1", "feature2", "feature3"]
        )
        
        # Register the model
        result = self.model_manager.register_model(
            model=mock_model,
            metadata=metadata
        )
        
        # Verify registration
        assert result is True
        assert "test_model" in self.model_manager.list_models()

    def test_load_model_success(self):
        """Test successful model loading."""
        # First register a model
        mock_model = Mock()
        metadata = ModelMetadata(
            name="load_test_model",
            version="1.0",
            model_type="regression",
            features=["x", "y"]
        )
        
        self.model_manager.register_model(mock_model, metadata)
        
        # Load the model
        loaded_model = self.model_manager.load_model("load_test_model", "1.0")
        
        # Verify loaded model
        assert loaded_model is not None
        assert hasattr(loaded_model, 'predict')

    def test_predict_with_registered_model(self):
        """Test prediction with a registered model."""
        # Mock model with predict method
        mock_model = Mock()
        mock_model.predict.return_value = [0.75]
        
        metadata = ModelMetadata(
            name="predict_model",
            version="1.0",
            model_type="regression",
            features=["price", "volume"]
        )
        
        # Register model
        self.model_manager.register_model(mock_model, metadata)
        
        # Test prediction
        input_data = [[100.0, 5000]]
        result = self.model_manager.predict("predict_model", input_data)
        
        # Verify prediction
        assert result == [0.75]
        mock_model.predict.assert_called_once_with(input_data)

    def test_register_model_conflict(self):
        """Test model registration conflict handling."""
        mock_model1 = Mock()
        mock_model2 = Mock()
        
        metadata = ModelMetadata(
            name="conflict_model",
            version="1.0",
            model_type="classification",
            features=["a", "b"]
        )
        
        # Register first model
        result1 = self.model_manager.register_model(mock_model1, metadata)
        assert result1 is True
        
        # Try to register same model again
        result2 = self.model_manager.register_model(mock_model2, metadata)
        
        # Should handle conflict (either reject or update depending on implementation)
        assert isinstance(result2, bool)

    def test_load_missing_model(self):
        """Test loading a model that doesn't exist."""
        with pytest.raises(ModelNotFoundError):
            self.model_manager.load_model("nonexistent_model", "1.0")

    def test_predict_missing_model(self):
        """Test prediction with missing model raises appropriate error."""
        with pytest.raises((ModelNotFoundError, KeyError, ValueError)):
            self.model_manager.predict("missing_model", [[1, 2, 3]])

    def test_model_metadata_validation(self):
        """Test model metadata validation."""
        mock_model = Mock()
        
        # Test with invalid metadata (missing required fields)
        with pytest.raises((ValueError, TypeError)):
            invalid_metadata = ModelMetadata(
                name="",  # Empty name should be invalid
                version="1.0",
                model_type="classification",
                features=[]
            )
            self.model_manager.register_model(mock_model, invalid_metadata)

    @patch('backend.mlops.model_manager.pickle')
    def test_model_persistence(self, mock_pickle):
        """Test model persistence mechanisms."""
        mock_model = Mock()
        metadata = ModelMetadata(
            name="persist_model",
            version="1.0", 
            model_type="regression",
            features=["x"]
        )
        
        # Mock pickle operations
        mock_pickle.dump.return_value = None
        mock_pickle.load.return_value = mock_model
        
        # Register model (should trigger persistence)
        self.model_manager.register_model(mock_model, metadata)
        
        # Verify pickle.dump was called for persistence
        assert mock_pickle.dump.call_count >= 1
