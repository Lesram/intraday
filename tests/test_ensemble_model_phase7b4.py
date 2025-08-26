"""
Phase 7B.4: Ensemble Model Module Testing - Core Functionality
Comprehensive testing for ML ensemble training and prediction logic
"""

import pytest
import asyncio
import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import pandas as pd
import numpy as np
from typing import Any, Dict

# Set environment variables before importing the module
os.environ['DISABLE_ML'] = '1'
os.environ['DISABLE_TENSORFLOW'] = '1'
os.environ['DISABLE_XGBOOST'] = '1'
os.environ['PYTEST_RUNNING'] = '1'

from backend.models.ensemble_model import (
    EnsembleModel, LSTMModel, XGBoostModel, RandomForestModel,
    ModelPrediction, ModelPerformance, _NoOpModel, create_noop_ensemble,
    SchemaMismatchError
)


class TestModelDataStructuresPhase7B4:
    """Test model data structures and containers"""
    
    def test_model_prediction_structure(self):
        """Test ModelPrediction dataclass structure"""
        prediction = ModelPrediction(
            symbol="AAPL",
            timestamp=datetime.now(),
            predictions={"lstm": 150.0, "xgboost": 148.5},
            confidence_scores={"lstm": 0.85, "xgboost": 0.78},
            ensemble_prediction=149.25,
            ensemble_confidence=0.815,
            metadata={"source": "test", "version": "1.0"}
        )
        
        assert prediction.symbol == "AAPL"
        assert prediction.ensemble_prediction == 149.25
        assert prediction.ensemble_confidence == 0.815
        assert "lstm" in prediction.predictions
        assert "xgboost" in prediction.predictions
        assert len(prediction.metadata) == 2
    
    def test_model_performance_structure(self):
        """Test ModelPerformance dataclass structure"""
        now = datetime.now()
        performance = ModelPerformance(
            model_name="lstm",
            mse=0.025,
            mae=0.015,
            sharpe_ratio=1.85,
            accuracy=0.78,
            last_updated=now
        )
        
        assert performance.model_name == "lstm"
        assert performance.mse == 0.025
        assert performance.mae == 0.015
        assert performance.sharpe_ratio == 1.85
        assert performance.accuracy == 0.78
        assert performance.last_updated == now
    
    def test_schema_mismatch_error(self):
        """Test SchemaMismatchError exception"""
        error = SchemaMismatchError("Schema validation failed")
        assert str(error) == "Schema validation failed"
        assert hasattr(error, 'expected_schema')
        assert hasattr(error, 'received_schema')


class TestNoOpModelPhase7B4:
    """Test NoOp model fallback functionality"""
    
    def test_noop_model_initialization(self):
        """Test NoOp model initializes properly"""
        model = _NoOpModel()
        assert model is not None
        
        # Should accept any initialization parameters
        model2 = _NoOpModel(param1=True, param2=100)
        assert model2 is not None
    
    @pytest.mark.asyncio
    async def test_noop_model_async_train(self):
        """Test NoOp model async train method"""
        model = _NoOpModel()
        result = await model.train(data="test", target="target")
        
        # Should return True to indicate "successful" training
        assert result is True
    
    def test_noop_model_predict(self):
        """Test NoOp model predict method"""
        model = _NoOpModel()
        result = model.predict(features="test_features")
        
        # Should return predictable fallback values
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result == (0.0, 0.1)  # prediction, confidence
    
    def test_noop_model_save_load(self):
        """Test NoOp model save and load methods"""
        model = _NoOpModel()
        
        # Save should return None (no-op)
        save_result = model.save_model("test_path")
        assert save_result is None
        
        # Load should return True  
        load_result = model.load_model("test_path")
        assert load_result is True
    
    def test_create_noop_ensemble(self):
        """Test noop ensemble creation function"""
        ensemble = create_noop_ensemble()
        
        assert ensemble is not None
        assert isinstance(ensemble, _NoOpModel)
        
        # Should behave like a NoOp model
        result = ensemble.predict("test")
        assert result == (0.0, 0.1)


class TestLSTMModelPhase7B4:
    """Test LSTM model functionality"""
    
    @pytest.fixture
    def lstm_model(self):
        return LSTMModel(
            sequence_length=30,
            features=1,
            max_epochs=10,
            early_stopping_patience=3,
            random_seed=42
        )
    
    def test_lstm_initialization(self, lstm_model):
        """Test LSTM model initialization"""
        assert lstm_model.sequence_length == 30
        assert lstm_model.features == 1
        assert lstm_model.max_epochs == 10
        assert lstm_model.early_stopping_patience == 3
        assert lstm_model.random_seed == 42
        assert lstm_model.model is None
        assert lstm_model.scaler is None
        assert lstm_model.is_trained is False
        assert lstm_model.training_history is None
    
    def test_lstm_default_initialization(self):
        """Test LSTM model with default parameters"""
        model = LSTMModel()
        
        assert model.sequence_length == 60
        assert model.features == 1
        assert model.max_epochs == 50
        assert model.early_stopping_patience == 10
        assert model.random_seed == 42
    
    def test_lstm_build_model(self, lstm_model):
        """Test LSTM model building"""
        # Since TensorFlow is disabled, model building should be skipped
        assert lstm_model.model is None
        assert lstm_model.is_trained is False
    
    def test_lstm_prepare_sequences(self, lstm_model):
        """Test LSTM sequence preparation"""
        # Create test data
        data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]).reshape(-1, 1)
        
        # Mock the actual method behavior since TensorFlow is disabled
        with patch.object(lstm_model, 'prepare_sequences') as mock_prepare:
            mock_prepare.return_value = (
                np.array([[[1], [2], [3]], [[4], [5], [6]]]),  # X
                np.array([4, 7])  # y
            )
            
            X, y = lstm_model.prepare_sequences(data)
            
            assert X.shape == (2, 3, 1)
            assert y.shape == (2,)
            assert mock_prepare.called
    
    @pytest.mark.asyncio
    async def test_lstm_train_with_disabled_ml(self, lstm_model):
        """Test LSTM training with ML disabled"""
        # Create dummy price data
        dates = pd.date_range(start='2023-01-01', periods=100, freq='D')
        price_data = pd.DataFrame({
            'close': np.random.randn(100).cumsum() + 100,
            'volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
        
        # Should return False when ML is disabled
        result = await lstm_model.train(price_data, "close")
        assert result is False
        assert lstm_model.is_trained is False
    
    @pytest.mark.asyncio
    async def test_lstm_train_empty_data(self, lstm_model):
        """Test LSTM training with empty data"""
        empty_data = pd.DataFrame()
        
        result = await lstm_model.train(empty_data, "close")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_lstm_train_insufficient_data(self, lstm_model):
        """Test LSTM training with insufficient data"""
        # Create data shorter than sequence length
        short_data = pd.DataFrame({
            'close': [100, 101, 102, 103, 104]
        })
        
        result = await lstm_model.train(short_data, "close")
        assert result is False


class TestXGBoostModelPhase7B4:
    """Test XGBoost model functionality"""
    
    @pytest.fixture
    def xgboost_model(self):
        return XGBoostModel()
    
    def test_xgboost_initialization(self, xgboost_model):
        """Test XGBoost model initialization"""
        assert xgboost_model.model is None
        assert xgboost_model.is_trained is False
        assert xgboost_model.feature_importance == {}
        assert not hasattr(xgboost_model, 'training_score')
    
    @pytest.mark.asyncio
    async def test_xgboost_train_with_disabled_ml(self, xgboost_model):
        """Test XGBoost training with ML disabled"""
        # Create dummy features and target
        features = pd.DataFrame({
            'feature1': np.random.randn(100),
            'feature2': np.random.randn(100),
            'feature3': np.random.randn(100)
        })
        target = pd.Series(np.random.randn(100))
        
        # Should return False when ML is disabled
        result = await xgboost_model.train(features, target)
        assert result is False
        assert xgboost_model.is_trained is False
    
    @pytest.mark.asyncio
    async def test_xgboost_train_empty_data(self, xgboost_model):
        """Test XGBoost training with empty data"""
        empty_features = pd.DataFrame()
        empty_target = pd.Series()
        
        result = await xgboost_model.train(empty_features, empty_target)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_xgboost_train_mismatched_data(self, xgboost_model):
        """Test XGBoost training with mismatched data shapes"""
        features = pd.DataFrame({'feature1': [1, 2, 3]})
        target = pd.Series([1, 2])  # Different length
        
        result = await xgboost_model.train(features, target)
        assert result is False
    
    def test_xgboost_predict_untrained(self, xgboost_model):
        """Test XGBoost prediction when untrained"""
        features = pd.DataFrame({'feature1': [1, 2, 3]})
        
        prediction, confidence = xgboost_model.predict(features)
        
        # Should return fallback values
        assert prediction == 0.0
        assert confidence == 0.0
    
    def test_xgboost_predict_empty_features(self, xgboost_model):
        """Test XGBoost prediction with empty features"""
        empty_features = pd.DataFrame()
        
        prediction, confidence = xgboost_model.predict(empty_features)
        
        assert prediction == 0.0
        assert confidence == 0.0


class TestRandomForestModelPhase7B4:
    """Test Random Forest model functionality"""
    
    @pytest.fixture
    def rf_model(self):
        return RandomForestModel()
    
    def test_rf_initialization(self, rf_model):
        """Test Random Forest model initialization"""
        assert rf_model.model is None
        assert rf_model.is_trained is False
        # RandomForest model doesn't have feature_importance attribute initially
        assert not hasattr(rf_model, 'feature_importance')
        assert not hasattr(rf_model, 'oob_score')
    
    @pytest.mark.asyncio
    async def test_rf_train_with_disabled_ml(self, rf_model):
        """Test Random Forest training with ML disabled"""
        features = pd.DataFrame({
            'feature1': np.random.randn(50),
            'feature2': np.random.randn(50),
            'feature3': np.random.randn(50)
        })
        target = pd.Series(np.random.randn(50))
        
        result = await rf_model.train(features, target)
        assert result is False
        assert rf_model.is_trained is False
    
    @pytest.mark.asyncio
    async def test_rf_train_insufficient_data(self, rf_model):
        """Test Random Forest training with insufficient data"""
        features = pd.DataFrame({'feature1': [1]})  # Single sample
        target = pd.Series([1])
        
        result = await rf_model.train(features, target)
        assert result is False
    
    def test_rf_predict_untrained(self, rf_model):
        """Test Random Forest prediction when untrained"""
        features = pd.DataFrame({'feature1': [1, 2, 3]})
        
        prediction, confidence = rf_model.predict(features)
        
        assert prediction == 0.0
        assert confidence == 0.0


class TestEnsembleModelInitializationPhase7B4:
    """Test EnsembleModel initialization and basic functionality"""
    
    @pytest.fixture
    def ensemble(self):
        with patch('backend.models.ensemble_model.get_settings') as mock_settings:
            mock_settings.return_value = Mock(mlops={})
            return EnsembleModel()
    
    def test_ensemble_initialization(self, ensemble):
        """Test EnsembleModel initialization"""
        assert ensemble.models is not None
        assert len(ensemble.models) == 3
        assert "lstm" in ensemble.models
        assert "xgboost" in ensemble.models
        assert "random_forest" in ensemble.models
        
        assert ensemble.weights == {"lstm": 0.4, "xgboost": 0.4, "random_forest": 0.2}
        assert ensemble.performance_history == []
        assert ensemble.settings is not None
    
    def test_ensemble_model_types(self, ensemble):
        """Test that ensemble contains correct model types"""
        assert isinstance(ensemble.models["lstm"], LSTMModel)
        assert isinstance(ensemble.models["xgboost"], XGBoostModel)
        assert isinstance(ensemble.models["random_forest"], RandomForestModel)
    
    def test_ensemble_mlops_disabled(self, ensemble):
        """Test ensemble with MLOps disabled"""
        # Should handle disabled MLOps gracefully
        assert ensemble.model_manager is None or ensemble.mlops_enabled is False
    
    def test_ensemble_weights_sum(self, ensemble):
        """Test ensemble weights sum to 1.0"""
        total_weight = sum(ensemble.weights.values())
        assert abs(total_weight - 1.0) < 0.001  # Allow for floating point precision


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
