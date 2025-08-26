"""
Targeted ensemble model tests - Focus on achieving maximum coverage 
with proper mocking for test environment compatibility

Strategy:
- Test core model functionality without heavy ML library dependencies
- Focus on business logic, error handling, and integration paths
- Target the 365 uncovered lines systematically
"""

import os
import tempfile
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import pytest
import pandas as pd
import numpy as np

# Force test environment settings
os.environ['DISABLE_ML'] = '1'
os.environ['DISABLE_TENSORFLOW'] = '1'
os.environ['DISABLE_XGBOOST'] = '1'
os.environ['PYTEST_RUNNING'] = '1'

from backend.models.ensemble_model import (
    EnsembleModel,
    LSTMModel, 
    XGBoostModel,
    RandomForestModel,
    ModelPrediction,
    ModelPerformance,
    create_noop_ensemble,
    DISABLE_ML,
    TENSORFLOW_AVAILABLE,
    XGBOOST_AVAILABLE, 
    SKLEARN_AVAILABLE,
)


class TestEnvironmentSetup:
    """Verify test environment is properly configured"""
    
    def test_disable_ml_flag_set(self):
        """Test that DISABLE_ML is properly set"""
        assert DISABLE_ML == True
        
    def test_availability_flags_disabled(self):
        """Test that ML library flags are disabled in test mode"""
        assert TENSORFLOW_AVAILABLE == False
        assert XGBOOST_AVAILABLE == False
        # sklearn might still be available for basic usage
        
    def test_noop_ensemble_creation(self):
        """Test no-op ensemble factory works"""
        noop = create_noop_ensemble()
        assert noop is not None
        assert hasattr(noop, 'train')
        assert hasattr(noop, 'predict')


class TestModelDataClasses:
    """Test data class functionality comprehensively"""
    
    def test_model_prediction_full_creation(self):
        """Test ModelPrediction with all attributes"""
        timestamp = datetime.now()
        prediction = ModelPrediction(
            symbol="TSLA",
            timestamp=timestamp,
            predictions={"lstm": 245.5, "xgboost": 247.2, "random_forest": 244.8},
            confidence_scores={"lstm": 0.85, "xgboost": 0.78, "random_forest": 0.72}, 
            ensemble_prediction=245.8,
            ensemble_confidence=0.78,
            metadata={
                "weights": {"lstm": 0.4, "xgboost": 0.4, "random_forest": 0.2},
                "models_active": 3,
                "training_date": "2023-01-01"
            }
        )
        
        assert prediction.symbol == "TSLA"
        assert prediction.timestamp == timestamp
        assert len(prediction.predictions) == 3
        assert len(prediction.confidence_scores) == 3
        assert prediction.ensemble_prediction == 245.8
        assert prediction.ensemble_confidence == 0.78
        assert prediction.metadata["models_active"] == 3
        
    def test_model_performance_comprehensive(self):
        """Test ModelPerformance with various metrics"""
        timestamp = datetime.now()
        performance = ModelPerformance(
            model_name="enhanced_lstm",
            mse=0.0234,
            mae=0.123,
            sharpe_ratio=2.15,
            accuracy=0.892,
            last_updated=timestamp
        )
        
        assert performance.model_name == "enhanced_lstm"
        assert performance.mse == 0.0234
        assert performance.mae == 0.123
        assert performance.sharpe_ratio == 2.15
        assert performance.accuracy == 0.892
        assert performance.last_updated == timestamp


class TestLSTMModelComprehensive:
    """Comprehensive LSTM model testing"""
    
    def test_lstm_initialization_variants(self):
        """Test LSTM initialization with various parameters"""
        # Default initialization
        model1 = LSTMModel()
        assert model1.sequence_length == 60
        assert model1.features == 1
        assert model1.max_epochs == 50
        assert model1.early_stopping_patience == 10
        assert model1.random_seed == 42
        
        # Custom initialization
        model2 = LSTMModel(
            sequence_length=30,
            features=5,
            max_epochs=25,
            early_stopping_patience=5,
            random_seed=123
        )
        assert model2.sequence_length == 30
        assert model2.features == 5
        assert model2.max_epochs == 25
        assert model2.early_stopping_patience == 5
        assert model2.random_seed == 123
        
        # No seed initialization  
        model3 = LSTMModel(random_seed=None)
        assert model3.random_seed is None
        
    def test_prepare_sequences_edge_cases(self):
        """Test sequence preparation with edge cases"""
        model = LSTMModel(sequence_length=10)
        
        # Insufficient data
        short_data = np.array([[1], [2], [3]])
        X, y = model.prepare_sequences(short_data)
        assert X.shape[0] == 0
        assert y.shape[0] == 0
        
        # Exact minimum data
        exact_data = np.array([[i] for i in range(11)])
        X, y = model.prepare_sequences(exact_data)
        assert X.shape == (1, 10, 1)
        assert y.shape == (1, 1)
        
        # Larger dataset
        large_data = np.array([[i] for i in range(50)])
        X, y = model.prepare_sequences(large_data)
        assert X.shape == (40, 10, 1)
        assert y.shape == (40, 1)
        
    def test_build_model_disabled_tensorflow(self):
        """Test build_model when TensorFlow is disabled"""
        model = LSTMModel()
        result = model.build_model()
        assert result is None
        
    @pytest.mark.asyncio
    async def test_train_disabled_libraries(self):
        """Test training when libraries are disabled"""
        model = LSTMModel()
        data = pd.DataFrame({"close": [100, 101, 102, 103, 104]})
        
        result = await model.train(data, "close")
        
        assert result == False
        assert model.is_trained == False
        assert model.model is None
        assert model.scaler is None
        
    def test_predict_various_states(self):
        """Test prediction in various model states"""
        model = LSTMModel()
        data = pd.DataFrame({"close": [100, 101, 102]})
        
        # Untrained model
        price, confidence = model.predict(data)
        assert price == 0.0
        assert confidence == 0.0
        
        # Trained but no model
        model.is_trained = True
        price, confidence = model.predict(data)
        assert price == 0.0
        assert confidence == 0.0
        
        # Model but no scaler
        model.model = MagicMock()
        price, confidence = model.predict(data)
        assert price == 0.0
        assert confidence == 0.0


class TestXGBoostModelComprehensive:
    """Comprehensive XGBoost model testing"""
    
    def test_xgboost_initialization(self):
        """Test XGBoost model initialization"""
        model = XGBoostModel()
        
        assert model.model is None
        assert model.scaler is None
        assert model.is_trained == False
        assert model.feature_importance == {}
        
    @pytest.mark.asyncio
    async def test_train_disabled_libraries(self):
        """Test training when XGBoost/sklearn disabled"""
        model = XGBoostModel()
        features = pd.DataFrame({"f1": [1, 2, 3], "f2": [4, 5, 6]})
        target = pd.Series([1.1, 2.2, 3.3])
        
        result = await model.train(features, target)
        
        assert result == False
        assert model.is_trained == False
        
    def test_predict_various_states(self):
        """Test XGBoost prediction in various states"""
        model = XGBoostModel()
        features = pd.DataFrame({"f1": [1], "f2": [2]})
        
        # Untrained
        price, confidence = model.predict(features)
        assert price == 0.0
        assert confidence == 0.0
        
        # Trained but no model
        model.is_trained = True
        price, confidence = model.predict(features)
        assert price == 0.0
        assert confidence == 0.0


class TestRandomForestModelComprehensive:
    """Comprehensive Random Forest model testing"""
    
    def test_random_forest_initialization(self):
        """Test Random Forest model initialization"""  
        model = RandomForestModel()
        
        assert model.model is None
        assert model.scaler is None
        assert model.is_trained == False
        
    @pytest.mark.asyncio 
    async def test_train_disabled_libraries(self):
        """Test training when sklearn is disabled"""
        model = RandomForestModel()
        features = pd.DataFrame({"f1": [1, 2, 3]})
        target = pd.Series([1.1, 2.2, 3.3])
        
        result = await model.train(features, target)
        
        # Will depend on whether sklearn is actually available
        assert isinstance(result, bool)
        
    def test_predict_various_states(self):
        """Test Random Forest prediction states"""
        model = RandomForestModel()
        features = pd.DataFrame({"f1": [1], "f2": [2]})
        
        # Untrained
        price, confidence = model.predict(features)
        assert price == 0.0
        assert confidence == 0.0


class TestEnsembleModelCore:
    """Test core EnsembleModel functionality"""
    
    def test_ensemble_initialization(self):
        """Test EnsembleModel initialization and defaults"""
        ensemble = EnsembleModel()
        
        # Check model instances
        assert isinstance(ensemble.models["lstm"], LSTMModel)
        assert isinstance(ensemble.models["xgboost"], XGBoostModel)
        assert isinstance(ensemble.models["random_forest"], RandomForestModel)
        
        # Check default weights
        assert ensemble.weights["lstm"] == 0.4
        assert ensemble.weights["xgboost"] == 0.4
        assert ensemble.weights["random_forest"] == 0.2
        
        # Check initial state
        assert ensemble.performance_history == []
        assert hasattr(ensemble, 'settings')
        
    @pytest.mark.asyncio
    async def test_train_models_comprehensive(self):
        """Test comprehensive model training workflow"""
        ensemble = EnsembleModel()
        
        # Mock all model training methods to succeed
        ensemble.models["lstm"].train = AsyncMock(return_value=True)
        ensemble.models["xgboost"].train = AsyncMock(return_value=True)
        ensemble.models["random_forest"].train = AsyncMock(return_value=True)
        
        # Create comprehensive test data
        price_data = pd.DataFrame({
            "close": np.random.randn(150) + 100,
            "open": np.random.randn(150) + 100,
            "high": np.random.randn(150) + 105,
            "low": np.random.randn(150) + 95,
            "volume": np.random.randint(1000, 10000, 150),
            "timestamp": pd.date_range("2023-01-01", periods=150, freq="5min")
        })
        
        features = pd.DataFrame({
            "sma_10": np.random.randn(150),
            "ema_20": np.random.randn(150),
            "rsi": np.random.randn(150),
            "macd": np.random.randn(150),
            "volume_ratio": np.random.randn(150)
        })
        
        results = await ensemble.train_models(price_data, features, "close")
        
        # Verify all models were trained
        assert results["lstm"] == True
        assert results["xgboost"] == True 
        assert results["random_forest"] == True
        
        # Verify method calls
        ensemble.models["lstm"].train.assert_called_once_with(price_data, "close")
        ensemble.models["xgboost"].train.assert_called_once()
        ensemble.models["random_forest"].train.assert_called_once()
        
    def test_predict_comprehensive_success(self):
        """Test comprehensive prediction workflow with all models succeeding"""
        ensemble = EnsembleModel()
        
        # Mock successful predictions from all models
        ensemble.models["lstm"].predict = Mock(return_value=(151.5, 0.85))
        ensemble.models["xgboost"].predict = Mock(return_value=(152.2, 0.78))
        ensemble.models["random_forest"].predict = Mock(return_value=(150.8, 0.72))
        
        price_data = pd.DataFrame({
            "close": [149.5, 150.2, 151.1, 150.9, 151.3],
            "timestamp": pd.date_range("2023-01-01", periods=5, freq="1H")
        })
        features = pd.DataFrame({
            "feature1": [0.1, 0.2, 0.3, 0.4, 0.5],
            "feature2": [1.1, 1.2, 1.3, 1.4, 1.5]
        })
        
        result = ensemble.predict(price_data, features, "NVDA")
        
        # Verify result structure
        assert isinstance(result, ModelPrediction)
        assert result.symbol == "NVDA"
        assert isinstance(result.timestamp, datetime)
        assert len(result.predictions) == 3
        assert len(result.confidence_scores) == 3
        
        # Verify individual predictions
        assert result.predictions["lstm"] == 151.5
        assert result.predictions["xgboost"] == 152.2
        assert result.predictions["random_forest"] == 150.8
        
        # Verify ensemble calculation
        assert result.ensemble_prediction > 0
        assert result.ensemble_confidence > 0
        assert result.metadata["models_active"] == 3
        
    def test_predict_with_model_failures(self):
        """Test prediction handling when some models fail"""
        ensemble = EnsembleModel()
        
        # Mock mixed success/failure
        ensemble.models["lstm"].predict = Mock(return_value=(151.5, 0.85))
        ensemble.models["xgboost"].predict = Mock(side_effect=Exception("XGBoost failed"))
        ensemble.models["random_forest"].predict = Mock(return_value=(150.8, 0.72))
        
        price_data = pd.DataFrame({"close": [150.0, 151.0]})
        features = pd.DataFrame({"feature1": [1.0, 1.1]})
        
        result = ensemble.predict(price_data, features, "AAPL")
        
        # Should still work with successful models
        assert len(result.predictions) == 2
        assert "lstm" in result.predictions
        assert "random_forest" in result.predictions
        assert "xgboost" not in result.predictions
        assert result.ensemble_prediction > 0
        
    def test_update_weights_comprehensive(self):
        """Test comprehensive weight update scenarios"""
        ensemble = EnsembleModel()
        
        # Test with strong LSTM performance
        strong_lstm_performance = {
            "lstm": ModelPerformance("lstm", 0.01, 0.08, 2.5, 0.95, datetime.now()),
            "xgboost": ModelPerformance("xgboost", 0.05, 0.15, 1.2, 0.78, datetime.now()),
            "random_forest": ModelPerformance("random_forest", 0.08, 0.18, 0.9, 0.72, datetime.now())
        }
        
        original_weights = ensemble.weights.copy()
        ensemble.update_weights(strong_lstm_performance)
        
        # LSTM should get higher weight
        assert ensemble.weights["lstm"] > original_weights["lstm"]
        
        # Weights should sum to approximately 1
        weight_sum = sum(ensemble.weights.values())
        assert abs(weight_sum - 1.0) < 0.01
        
    def test_get_model_status_comprehensive(self):
        """Test comprehensive model status reporting"""
        ensemble = EnsembleModel()
        
        # Set varied model states
        ensemble.models["lstm"].is_trained = True
        ensemble.models["xgboost"].is_trained = False
        ensemble.models["xgboost"].feature_importance = {
            "sma_10": 0.25, "rsi": 0.35, "macd": 0.40
        }
        ensemble.models["random_forest"].is_trained = True
        
        status = ensemble.get_model_status()
        
        # Verify status structure
        assert len(status) == 3
        for model_name, model_status in status.items():
            assert "is_trained" in model_status
            assert "weight" in model_status
            assert "available" in model_status
            
        # Verify specific states
        assert status["lstm"]["is_trained"] == True
        assert status["xgboost"]["is_trained"] == False
        assert "feature_importance" in status["xgboost"]
        assert len(status["xgboost"]["feature_importance"]) == 3


class TestEnsemblePersistenceComprehensive:
    """Comprehensive testing of model persistence"""
    
    def test_save_models_untrained_comprehensive(self):
        """Test saving when models are in various untrained states"""
        ensemble = EnsembleModel()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            results = ensemble.save_models(tmp_dir)
            
            # All models should fail to save when untrained
            assert results["lstm"] == False
            assert results["xgboost"] == False
            assert results["random_forest"] == False
            
            # Model card should still be created
            model_card_path = Path(tmp_dir) / "model_card.json"
            assert model_card_path.exists()
            
    def test_load_models_missing_directory(self):
        """Test loading from non-existent directory"""
        ensemble = EnsembleModel()
        
        results = ensemble.load_models("/completely/nonexistent/path/12345")
        
        # All loads should fail
        assert results["lstm"] == False
        assert results["xgboost"] == False
        assert results["random_forest"] == False


class TestEnsembleWeightManagement:
    """Test ensemble weight management and optimization"""
    
    def test_weight_update_edge_cases(self):
        """Test weight updates with edge case performance metrics"""
        ensemble = EnsembleModel()
        
        # Test with zero performance
        zero_performance = {
            "lstm": ModelPerformance("lstm", 1.0, 1.0, 0.0, 0.0, datetime.now()),
            "xgboost": ModelPerformance("xgboost", 1.0, 1.0, 0.0, 0.0, datetime.now()),
            "random_forest": ModelPerformance("random_forest", 1.0, 1.0, 0.0, 0.0, datetime.now())
        }
        
        ensemble.update_weights(zero_performance)
        
        # Should maintain minimum weights
        for weight in ensemble.weights.values():
            assert weight >= 0.1
            
        # Test with missing model performance
        partial_performance = {
            "lstm": ModelPerformance("lstm", 0.05, 0.1, 1.5, 0.8, datetime.now()),
        }
        
        ensemble.update_weights(partial_performance)
        
        # Missing models should get fallback weight
        assert ensemble.weights["xgboost"] >= 0.1
        assert ensemble.weights["random_forest"] >= 0.1
        
    def test_weight_normalization(self):
        """Test that weights are properly normalized"""
        ensemble = EnsembleModel()
        
        # Create performance with very different scores
        extreme_performance = {
            "lstm": ModelPerformance("lstm", 0.001, 0.01, 10.0, 0.99, datetime.now()),
            "xgboost": ModelPerformance("xgboost", 0.5, 0.8, 0.1, 0.3, datetime.now()),
            "random_forest": ModelPerformance("random_forest", 0.3, 0.5, 0.5, 0.5, datetime.now())
        }
        
        ensemble.update_weights(extreme_performance)
        
        # Weights should sum to 1 regardless of extreme differences
        weight_sum = sum(ensemble.weights.values())
        assert abs(weight_sum - 1.0) < 0.01
        
        # Best performing model should get highest weight
        assert ensemble.weights["lstm"] > ensemble.weights["xgboost"]
        assert ensemble.weights["lstm"] > ensemble.weights["random_forest"]


class TestEnsembleErrorHandling:
    """Comprehensive error handling tests"""
    
    def test_predict_with_empty_data(self):
        """Test prediction with empty or malformed data"""
        ensemble = EnsembleModel()
        
        # Mock models to handle gracefully
        ensemble.models["lstm"].predict = Mock(return_value=(0.0, 0.0))
        ensemble.models["xgboost"].predict = Mock(return_value=(0.0, 0.0))
        ensemble.models["random_forest"].predict = Mock(return_value=(0.0, 0.0))
        
        # Empty dataframes
        empty_price = pd.DataFrame({"close": []})
        empty_features = pd.DataFrame({"feature1": []})
        
        result = ensemble.predict(empty_price, empty_features, "TEST")
        
        assert isinstance(result, ModelPrediction)
        assert result.symbol == "TEST"
        assert result.ensemble_prediction == 0.0
        assert result.ensemble_confidence == 0.0
        
    def test_predict_all_models_fail(self):
        """Test prediction when all models fail"""
        ensemble = EnsembleModel()
        
        # Make all models fail
        ensemble.models["lstm"].predict = Mock(side_effect=Exception("LSTM failed"))
        ensemble.models["xgboost"].predict = Mock(side_effect=Exception("XGBoost failed"))
        ensemble.models["random_forest"].predict = Mock(side_effect=Exception("RF failed"))
        
        price_data = pd.DataFrame({"close": [100, 101]})
        features = pd.DataFrame({"feature1": [1, 2]})
        
        result = ensemble.predict(price_data, features, "FAIL")
        
        # Should still return a result with defaults
        assert isinstance(result, ModelPrediction)
        assert len(result.predictions) == 0
        assert result.ensemble_prediction == 0.0
        assert result.ensemble_confidence == 0.0
        
    def test_save_models_io_errors(self):
        """Test saving models with I/O errors"""
        ensemble = EnsembleModel()
        
        # Try to save to a read-only or invalid location
        results = ensemble.save_models("/root/readonly/path")
        
        # Should handle gracefully without crashing
        assert isinstance(results, dict)
        assert len(results) == 3


class TestEnsembleIntegrationWorkflows:
    """Integration workflow testing"""
    
    @pytest.mark.asyncio
    async def test_complete_workflow_simulation(self):
        """Test a complete training-prediction-persistence workflow"""
        ensemble = EnsembleModel()
        
        # Step 1: Mock successful training
        for model in ensemble.models.values():
            model.train = AsyncMock(return_value=True)
            model.is_trained = True
            
        price_data = pd.DataFrame({
            "close": np.random.randn(100) + 150,
            "timestamp": pd.date_range("2023-01-01", periods=100, freq="1H")
        })
        features = pd.DataFrame({
            "sma": np.random.randn(100),
            "rsi": np.random.randn(100) * 50 + 50
        })
        
        # Train models
        train_results = await ensemble.train_models(price_data, features)
        assert all(train_results.values())
        
        # Step 2: Mock predictions
        ensemble.models["lstm"].predict = Mock(return_value=(152.0, 0.8))
        ensemble.models["xgboost"].predict = Mock(return_value=(151.5, 0.75))
        ensemble.models["random_forest"].predict = Mock(return_value=(151.8, 0.7))
        
        # Make predictions
        prediction = ensemble.predict(price_data.tail(10), features.tail(10), "WORKFLOW_TEST")
        assert prediction.ensemble_prediction > 0
        assert len(prediction.predictions) == 3
        
        # Step 3: Update weights based on synthetic performance
        performance_metrics = {
            "lstm": ModelPerformance("lstm", 0.02, 0.1, 1.8, 0.85, datetime.now()),
            "xgboost": ModelPerformance("xgboost", 0.03, 0.12, 1.6, 0.82, datetime.now()),
            "random_forest": ModelPerformance("random_forest", 0.04, 0.15, 1.4, 0.79, datetime.now())
        }
        
        original_weights = ensemble.weights.copy()
        ensemble.update_weights(performance_metrics)
        
        # Weights should have changed
        assert ensemble.weights != original_weights
        
        # Step 4: Get final status
        status = ensemble.get_model_status()
        assert all(model_status["is_trained"] for model_status in status.values())
        
    def test_ensemble_metadata_tracking(self):
        """Test that ensemble properly tracks metadata"""
        ensemble = EnsembleModel()
        
        # Mock predictions with different confidence levels
        ensemble.models["lstm"].predict = Mock(return_value=(150.0, 0.9))
        ensemble.models["xgboost"].predict = Mock(return_value=(149.5, 0.3))  # Low confidence
        ensemble.models["random_forest"].predict = Mock(return_value=(150.2, 0.8))
        
        price_data = pd.DataFrame({"close": [148, 149, 150]})
        features = pd.DataFrame({"f1": [1, 2, 3]})
        
        result = ensemble.predict(price_data, features, "META_TEST")
        
        # Check metadata tracking
        assert "weights" in result.metadata
        assert "models_active" in result.metadata
        assert result.metadata["weights"] == ensemble.weights
        
        # Models with non-zero predictions should be counted as active
        active_count = len([p for p in result.predictions.values() if p != 0.0])
        assert result.metadata["models_active"] == active_count


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
