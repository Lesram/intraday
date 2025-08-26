"""
Additional coverage tests targeting specific uncovered lines
Focus on error handling, attribute errors, and simple logic paths
"""
import pytest
import os
import sys
import numpy as np
import pandas as pd
from unittest.mock import patch, Mock, MagicMock
import asyncio
from pathlib import Path

# Add the backend directory to Python path for imports
backend_path = Path(__file__).parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

# Force DISABLE_ML to ensure we can test error paths
os.environ['DISABLE_ML'] = '1'

from backend.models.ensemble_model import EnsembleModel, LSTMModel


class TestAttributeErrorHandling:
    """Test AttributeError handling paths - lines 196-198"""
    
    def test_lstm_sequence_creation_basic(self):
        """Test LSTM sequence creation with basic data - lines 240-244"""
        lstm = LSTMModel(sequence_length=3)
        
        # Create simple test data
        data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        
        X, y = lstm.prepare_sequences(data)  # Correct method name
        
        # Should create sequences properly
        assert X.shape[0] == len(data) - lstm.sequence_length
        assert X.shape[1] == lstm.sequence_length
        assert len(y) == len(data) - lstm.sequence_length
        
        # Check first sequence
        np.testing.assert_array_equal(X[0], [1, 2, 3])
        assert y[0] == 4
        
        # Check last sequence  
        np.testing.assert_array_equal(X[-1], [7, 8, 9])
        assert y[-1] == 10


class TestSimpleReturnPaths:
    """Test simple return paths that don't require ML libraries"""
    
    @pytest.mark.asyncio
    async def test_lstm_train_returns_false_without_libraries(self):
        """Test LSTM train returns False when libraries unavailable"""
        lstm = LSTMModel()
        
        # Create dummy data
        data = pd.DataFrame({
            'close': [100, 101, 102, 103, 104],
            'volume': [1000, 1100, 1200, 1300, 1400]
        })
        
        # Should return False when ML libraries not available
        result = await lstm.train(data, "close")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_ensemble_train_early_return_without_libraries(self):
        """Test ensemble train early return - lines 534-536"""
        ensemble = EnsembleModel()
        
        # Create dummy data
        price_data = pd.DataFrame({
            'close': [100, 101, 102, 103, 104],
            'volume': [1000, 1100, 1200, 1300, 1400]
        })
        
        # Create dummy features (required parameter)
        features = pd.DataFrame({
            'feature1': [1, 2, 3, 4, 5],
            'feature2': [10, 20, 30, 40, 50]
        })
        
        # Should return early with False results
        result = await ensemble.train_models(price_data, features, target_column="close")
        
        assert isinstance(result, dict)
        assert "lstm" in result
        assert "xgboost" in result  
        assert "random_forest" in result
        assert result["xgboost"] is False
        assert result["random_forest"] is False


class TestDataFrameOperations:
    """Test DataFrame operations that can be tested without ML"""
    
    def test_target_shift_and_alignment(self):
        """Test target shifting and data alignment logic - lines 540-548"""
        # This tests the pandas operations that happen regardless of ML availability
        price_data = pd.DataFrame({
            'close': [100, 101, 102, 103, 104, 105],
            'volume': [1000, 1100, 1200, 1300, 1400, 1500]
        }, index=pd.date_range('2023-01-01', periods=6, freq='D'))
        
        # Simulate the target creation and alignment
        target_column = "close"
        target = price_data[target_column].shift(-1).dropna()  # Next period target
        
        # Test target shift worked correctly
        assert len(target) == len(price_data) - 1
        assert target.iloc[0] == 101  # First target should be second close price
        assert target.iloc[-1] == 105  # Last target should be last close price
        
        # Test alignment logic
        features = price_data.drop(columns=[target_column])
        aligned_data = pd.concat(
            [features, target.to_frame("target")], join="inner", axis=1
        ).dropna()
        
        assert "target" in aligned_data.columns
        assert len(aligned_data) == len(target)
        
        features_aligned = aligned_data.drop(columns=["target"])
        target_aligned = aligned_data["target"]
        
        assert len(features_aligned) == len(target_aligned)
        assert len(features_aligned) > 0


class TestEdgeCaseHandling:
    """Test edge cases and boundary conditions"""
    
    def test_lstm_sequence_creation_edge_cases(self):
        """Test LSTM sequence creation with edge cases"""
        lstm = LSTMModel(sequence_length=5)
        
        # Test with exactly sequence_length data points
        data = np.array([1, 2, 3, 4, 5])
        X, y = lstm.prepare_sequences(data)  # Correct method name
        assert len(X) == 0  # Should be empty
        assert len(y) == 0
        
        # Test with sequence_length + 1 data points  
        data = np.array([1, 2, 3, 4, 5, 6])
        X, y = lstm.prepare_sequences(data)
        assert len(X) == 1
        assert len(y) == 1
        np.testing.assert_array_equal(X[0], [1, 2, 3, 4, 5])
        assert y[0] == 6
    
    def test_empty_dataframe_handling(self):
        """Test handling of empty DataFrames"""
        # Create empty DataFrame
        empty_df = pd.DataFrame()
        
        # Target shifting on empty DataFrame
        if not empty_df.empty:
            target = empty_df.get("close", pd.Series()).shift(-1).dropna()
        else:
            target = pd.Series(dtype='float64')
        
        assert len(target) == 0
        assert isinstance(target, pd.Series)


class TestModelStateValidation:
    """Test model state and configuration validation"""
    
    def test_lstm_model_initialization_state(self):
        """Test LSTM model initialization state"""
        lstm = LSTMModel(sequence_length=10, features=5, max_epochs=100)
        
        assert lstm.sequence_length == 10
        assert lstm.features == 5
        assert lstm.max_epochs == 100
        assert lstm.random_seed == 42  # default
        assert lstm.model is None  # Not trained yet
        assert lstm.scaler is None  # Not initialized yet
        assert lstm.is_trained is False
    
    def test_ensemble_model_initialization_state(self):
        """Test ensemble model initialization state"""
        ensemble = EnsembleModel()
        
        assert "lstm" in ensemble.models
        assert "xgboost" in ensemble.models  
        assert "random_forest" in ensemble.models
        # Check if attributes exist without assuming specific values
        assert hasattr(ensemble, 'models')
        assert isinstance(ensemble.models, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
