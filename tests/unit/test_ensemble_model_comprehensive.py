"""
Comprehensive tests for ensemble_model.py - Targeting 365/538 uncovered lines
Focus: ML model lifecycle, training, prediction, persistence, MLOps integration

Coverage Strategy:
- Mock all ML dependencies (TensorFlow, XGBoost, sklearn) for test environment
- Test availability flags and fallback patterns  
- Test model training workflows with proper data preparation
- Test prediction pipelines with confidence scoring
- Test ensemble weighting and model selection
- Test persistence operations (save/load models)
- Test MLOps registry integration
- Test error handling and edge cases
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
    MLOPS_AVAILABLE,
    FEATURE_PIPELINE_AVAILABLE,
)


class TestAvailabilityFlags:
    """Test ML library availability flags and DISABLE_ML functionality"""
    
    def test_disable_ml_environment_variable(self):
        """Test DISABLE_ML environment variable handling"""
        # Test cases already set DISABLE_ML=1, so flags should be False
        assert DISABLE_ML == True  # Set in test environment
        assert TENSORFLOW_AVAILABLE == False
        assert XGBOOST_AVAILABLE == False
        assert SKLEARN_AVAILABLE == False
    
    def test_noop_ensemble_factory(self):
        """Test no-op ensemble creation for test mode"""
        noop_model = create_noop_ensemble()
        assert noop_model is not None
        assert hasattr(noop_model, 'is_trained')
        assert hasattr(noop_model, 'train')
        assert hasattr(noop_model, 'predict')
    
    @pytest.mark.asyncio
    async def test_noop_model_interface(self):
        """Test no-op model provides expected interface"""
        from backend.models.ensemble_model import _NoOpModel
        
        model = _NoOpModel()
        assert model.is_trained == False
        
        # Test async training
        result = await model.train()
        assert result == True
        assert model.is_trained == True
        
        # Test prediction
        price, confidence = model.predict()
        assert price == 0.0
        assert confidence == 0.1
        
        # Test save/load
        model.save_model()  # Should not raise
        result = model.load_model()
        assert result == True


class TestModelPredictionDataClass:
    """Test ModelPrediction dataclass functionality"""
    
    def test_model_prediction_creation(self):
        """Test ModelPrediction dataclass creation and attributes"""
        timestamp = datetime.now()
        prediction = ModelPrediction(
            symbol="AAPL",
            timestamp=timestamp,
            predictions={"lstm": 150.0, "xgboost": 151.0},
            confidence_scores={"lstm": 0.8, "xgboost": 0.7}, 
            ensemble_prediction=150.5,
            ensemble_confidence=0.75,
            metadata={"weights": {"lstm": 0.6, "xgboost": 0.4}}
        )
        
        assert prediction.symbol == "AAPL"
        assert prediction.timestamp == timestamp
        assert prediction.predictions["lstm"] == 150.0
        assert prediction.confidence_scores["xgboost"] == 0.7
        assert prediction.ensemble_prediction == 150.5
        assert prediction.ensemble_confidence == 0.75
        assert "weights" in prediction.metadata


class TestModelPerformanceDataClass:
    """Test ModelPerformance dataclass functionality"""
    
    def test_model_performance_creation(self):
        """Test ModelPerformance dataclass creation and attributes"""
        timestamp = datetime.now()
        performance = ModelPerformance(
            model_name="lstm",
            mse=0.05,
            mae=0.15,
            sharpe_ratio=1.2,
            accuracy=0.78,
            last_updated=timestamp
        )
        
        assert performance.model_name == "lstm"
        assert performance.mse == 0.05
        assert performance.mae == 0.15
        assert performance.sharpe_ratio == 1.2
        assert performance.accuracy == 0.78
        assert performance.last_updated == timestamp


class TestLSTMModel:
    """Test LSTMModel implementation with mocked TensorFlow"""
    
    def test_lstm_init(self):
        """Test LSTM model initialization with parameters"""
        model = LSTMModel(
            sequence_length=30,
            features=5,
            max_epochs=20,
            early_stopping_patience=5,
            random_seed=123
        )
        
        assert model.sequence_length == 30
        assert model.features == 5
        assert model.max_epochs == 20
        assert model.early_stopping_patience == 5
        assert model.random_seed == 123
        assert model.is_trained == False
        assert model.model is None
        
    def test_prepare_sequences(self):
        """Test LSTM sequence preparation"""
        model = LSTMModel(sequence_length=5)
        
        # Create test data
        data = np.array([[1], [2], [3], [4], [5], [6], [7], [8]])
        
        X, y = model.prepare_sequences(data)
        
        assert X.shape == (3, 5, 1)  # 3 sequences of length 5
        assert y.shape == (3, 1)
        assert np.array_equal(X[0], [[1], [2], [3], [4], [5]])
        assert y[0] == [6]
        
    @patch('backend.models.ensemble_model.TENSORFLOW_AVAILABLE', True)
    @patch('backend.models.ensemble_model.SKLEARN_AVAILABLE', True)
    @patch('sklearn.preprocessing.StandardScaler')
    @pytest.mark.asyncio
    async def test_lstm_training_success(self, mock_scaler_class):
        """Test successful LSTM training workflow"""
        # Setup mocks
        mock_model = MagicMock()
        mock_history = MagicMock()
        mock_history.history = {"loss": [0.1, 0.05], "val_loss": [0.12, 0.06]}
        mock_model.fit.return_value = mock_history
        
        mock_scaler = MagicMock()
        mock_scaler.fit_transform.return_value = np.random.randn(100, 1)
        mock_scaler_class.return_value = mock_scaler
        
        # Create test data
        data = pd.DataFrame({
            "close": np.random.randn(100) + 100
        })
        
        model = LSTMModel(sequence_length=10)
        
        with patch.object(model, 'build_model', return_value=mock_model):
            result = await model.train(data, "close")
        
        assert result == True
        assert model.is_trained == True
        assert model.model == mock_model
        assert model.scaler == mock_scaler
        assert model.training_history == mock_history
        
    @patch('backend.models.ensemble_model.TENSORFLOW_AVAILABLE', True)
    @patch('backend.models.ensemble_model.SKLEARN_AVAILABLE', True)
    def test_lstm_prediction_untrained(self):
        """Test LSTM prediction when model is not trained"""
        with patch('backend.models.ensemble_model.tf', MagicMock()):
            model = LSTMModel()
            data = pd.DataFrame({"close": [100, 101, 102]})
            
            price, confidence = model.predict(data)
            
            assert price == 0.0
            assert confidence == 0.0
        
    @patch('backend.models.ensemble_model.TENSORFLOW_AVAILABLE', True)
    @patch('backend.models.ensemble_model.SKLEARN_AVAILABLE', True)
    def test_lstm_prediction_trained(self):
        """Test LSTM prediction with trained model"""
        with patch('backend.models.ensemble_model.tf', MagicMock()):
            model = LSTMModel(sequence_length=3)
            model.is_trained = True
            
            # Mock model and scaler
            mock_model = MagicMock()
            mock_model.predict.return_value = np.array([[0.5]])  # Scaled prediction
            model.model = mock_model
            
            mock_scaler = MagicMock()
            mock_scaler.transform.return_value = np.array([[0.1], [0.2], [0.3]])
            mock_scaler.inverse_transform.return_value = np.array([[105.0]])
            model.scaler = mock_scaler
            
            data = pd.DataFrame({"close": [100, 101, 102, 103, 104]})
            
            price, confidence = model.predict(data)
            
            assert price == 105.0
            assert 0.1 <= confidence <= 0.95
            mock_model.predict.assert_called_once()


class TestXGBoostModel:
    """Test XGBoostModel implementation with mocked XGBoost"""
    
    def test_xgboost_init(self):
        """Test XGBoost model initialization"""
        model = XGBoostModel()
        
        assert model.model is None
        assert model.scaler is None
        assert model.is_trained == False
        assert model.feature_importance == {}
        
    @patch('backend.models.ensemble_model.XGBOOST_AVAILABLE', True)
    @patch('backend.models.ensemble_model.SKLEARN_AVAILABLE', True)
    @patch('xgboost.XGBRegressor')
    @patch('sklearn.preprocessing.StandardScaler')
    @patch('sklearn.model_selection.TimeSeriesSplit')
    @pytest.mark.asyncio
    async def test_xgboost_training_success(self, mock_tss_class, mock_scaler_class, mock_xgb_class):
        """Test successful XGBoost training workflow"""
        # Setup mocks
        mock_model = MagicMock()
        mock_model.feature_importances_ = np.array([0.3, 0.4, 0.3])
        mock_xgb_class.return_value = mock_model
        
        mock_scaler = MagicMock()
        mock_scaler.fit_transform.return_value = np.random.randn(100, 3)
        mock_scaler_class.return_value = mock_scaler
        
        # Mock time series split
        mock_tss = MagicMock()
        mock_tss.split.return_value = [
            (np.arange(80), np.arange(80, 100))
        ]
        mock_tss_class.return_value = mock_tss
        
        # Create test data
        features = pd.DataFrame({
            "feature1": np.random.randn(100),
            "feature2": np.random.randn(100), 
            "feature3": np.random.randn(100)
        })
        target = pd.Series(np.random.randn(100))
        
        model = XGBoostModel()
        result = await model.train(features, target)
        
        assert result == True
        assert model.is_trained == True
        assert model.scaler == mock_scaler
        assert len(model.feature_importance) == 3
        
    @pytest.mark.asyncio
    async def test_xgboost_training_disabled_libraries(self):
        """Test XGBoost training when libraries are disabled"""
        model = XGBoostModel()
        features = pd.DataFrame({"feature1": [1, 2, 3]})
        target = pd.Series([1, 2, 3])
        
        result = await model.train(features, target)
        
        assert result == False
        assert model.is_trained == False
        
    def test_xgboost_prediction_untrained(self):
        """Test XGBoost prediction when model is not trained"""
        model = XGBoostModel()
        features = pd.DataFrame({"feature1": [1, 2, 3]})
        
        price, confidence = model.predict(features)
        
        assert price == 0.0
        assert confidence == 0.0
        
    @patch('backend.models.ensemble_model.XGBOOST_AVAILABLE', True)
    def test_xgboost_prediction_trained(self):
        """Test XGBoost prediction with trained model"""
        model = XGBoostModel()
        model.is_trained = True
        
        # Mock model and scaler
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([150.5])
        model.model = mock_model
        
        mock_scaler = MagicMock()
        mock_scaler.transform.return_value = np.array([[0.1, 0.2]])
        model.scaler = mock_scaler
        
        features = pd.DataFrame({"feature1": [100], "feature2": [200]})
        
        price, confidence = model.predict(features)
        
        assert price == 150.5
        assert confidence == 0.7  # Base confidence


class TestRandomForestModel:
    """Test RandomForestModel implementation with mocked sklearn"""
    
    def test_random_forest_init(self):
        """Test Random Forest model initialization"""
        model = RandomForestModel()
        
        assert model.model is None
        assert model.scaler is None
        assert model.is_trained == False
        
    @patch('backend.models.ensemble_model.SKLEARN_AVAILABLE', True)
    @patch('sklearn.ensemble.RandomForestRegressor')
    @patch('sklearn.preprocessing.StandardScaler')
    @pytest.mark.asyncio
    async def test_random_forest_training_success(self, mock_scaler_class, mock_rf_class):
        """Test successful Random Forest training workflow"""
        # Setup mocks
        mock_model = MagicMock()
        mock_rf_class.return_value = mock_model
        
        mock_scaler = MagicMock()
        mock_scaler.fit_transform.return_value = np.random.randn(100, 2)
        mock_scaler_class.return_value = mock_scaler
        
        # Create test data
        features = pd.DataFrame({
            "feature1": np.random.randn(100),
            "feature2": np.random.randn(100)
        })
        target = pd.Series(np.random.randn(100))
        
        model = RandomForestModel()
        result = await model.train(features, target)
        
        assert result == True
        assert model.is_trained == True
        assert model.model == mock_model
        assert model.scaler == mock_scaler
        
    def test_random_forest_prediction_with_estimators(self):
        """Test Random Forest prediction with ensemble variance"""
        model = RandomForestModel()
        model.is_trained = True
        
        # Mock model with estimators
        mock_estimator1 = MagicMock()
        mock_estimator1.predict.return_value = np.array([150.0])
        mock_estimator2 = MagicMock() 
        mock_estimator2.predict.return_value = np.array([152.0])
        
        mock_model = MagicMock()
        mock_model.estimators_ = [mock_estimator1, mock_estimator2]
        model.model = mock_model
        
        mock_scaler = MagicMock()
        mock_scaler.transform.return_value = np.array([[0.1, 0.2]])
        model.scaler = mock_scaler
        
        features = pd.DataFrame({"feature1": [100], "feature2": [200]})
        
        price, confidence = model.predict(features)
        
        assert price == 151.0  # Mean of predictions
        assert 0.1 <= confidence <= 0.95


class TestEnsembleModel:
    """Test EnsembleModel core functionality"""
    
    def test_ensemble_init(self):
        """Test EnsembleModel initialization"""
        ensemble = EnsembleModel()
        
        assert "lstm" in ensemble.models
        assert "xgboost" in ensemble.models
        assert "random_forest" in ensemble.models
        
        assert ensemble.weights["lstm"] == 0.4
        assert ensemble.weights["xgboost"] == 0.4
        assert ensemble.weights["random_forest"] == 0.2
        
        assert ensemble.performance_history == []
        
    @pytest.mark.asyncio
    async def test_train_models_integration(self):
        """Test training all models in ensemble"""
        ensemble = EnsembleModel()
        
        # Mock model training methods
        for model in ensemble.models.values():
            model.train = AsyncMock(return_value=True)
            
        # Create test data
        price_data = pd.DataFrame({
            "close": np.random.randn(100) + 100,
            "timestamp": pd.date_range("2023-01-01", periods=100, freq="1min")
        })
        features = pd.DataFrame({
            "feature1": np.random.randn(100),
            "feature2": np.random.randn(100)
        })
        
        results = await ensemble.train_models(price_data, features)
        
        assert results["lstm"] == True
        assert results["xgboost"] == True
        assert results["random_forest"] == True
        
        # Verify all models were called
        ensemble.models["lstm"].train.assert_called_once_with(price_data, "close")
        ensemble.models["xgboost"].train.assert_called_once()
        ensemble.models["random_forest"].train.assert_called_once()
        
    def test_predict_basic(self):
        """Test basic ensemble prediction workflow"""
        ensemble = EnsembleModel()
        
        # Mock individual model predictions
        ensemble.models["lstm"].predict = Mock(return_value=(150.0, 0.8))
        ensemble.models["xgboost"].predict = Mock(return_value=(151.0, 0.7))
        ensemble.models["random_forest"].predict = Mock(return_value=(149.0, 0.6))
        
        price_data = pd.DataFrame({"close": [100, 101, 102]})
        features = pd.DataFrame({"feature1": [1, 2, 3]})
        
        result = ensemble.predict(price_data, features, "AAPL")
        
        assert isinstance(result, ModelPrediction)
        assert result.symbol == "AAPL"
        assert len(result.predictions) == 3
        assert len(result.confidence_scores) == 3
        assert result.ensemble_prediction > 0
        assert result.ensemble_confidence > 0
        
    def test_predict_with_failed_model(self):
        """Test ensemble prediction when one model fails"""
        ensemble = EnsembleModel()
        
        # Mock predictions with one failure
        ensemble.models["lstm"].predict = Mock(return_value=(150.0, 0.8))
        ensemble.models["xgboost"].predict = Mock(side_effect=Exception("Model failed"))
        ensemble.models["random_forest"].predict = Mock(return_value=(149.0, 0.6))
        
        price_data = pd.DataFrame({"close": [100, 101, 102]})
        features = pd.DataFrame({"feature1": [1, 2, 3]})
        
        result = ensemble.predict(price_data, features, "AAPL")
        
        # Should still work with remaining models
        assert len(result.predictions) == 2  # Only successful models
        assert "xgboost" not in result.predictions
        assert result.ensemble_prediction > 0
        
    def test_update_weights(self):
        """Test ensemble weight updates based on performance"""
        ensemble = EnsembleModel()
        
        performance_metrics = {
            "lstm": ModelPerformance("lstm", 0.05, 0.15, 1.5, 0.85, datetime.now()),
            "xgboost": ModelPerformance("xgboost", 0.03, 0.12, 1.2, 0.78, datetime.now()),
            "random_forest": ModelPerformance("random_forest", 0.08, 0.18, 0.9, 0.72, datetime.now())
        }
        
        original_weights = ensemble.weights.copy()
        ensemble.update_weights(performance_metrics)
        
        # Weights should change based on performance
        assert ensemble.weights != original_weights
        
        # Sum should still be approximately 1
        weight_sum = sum(ensemble.weights.values())
        assert abs(weight_sum - 1.0) < 0.01
        
    def test_get_model_status(self):
        """Test getting status of all models"""
        ensemble = EnsembleModel()
        
        # Set some models as trained
        ensemble.models["lstm"].is_trained = True
        ensemble.models["xgboost"].is_trained = False
        ensemble.models["xgboost"].feature_importance = {"feat1": 0.5, "feat2": 0.5}
        
        status = ensemble.get_model_status()
        
        assert status["lstm"]["is_trained"] == True
        assert status["xgboost"]["is_trained"] == False
        assert status["xgboost"]["feature_importance"] == {"feat1": 0.5, "feat2": 0.5}
        assert all("weight" in model_status for model_status in status.values())
        assert all("available" in model_status for model_status in status.values())


class TestEnsembleModelPersistence:
    """Test ensemble model save/load functionality"""
    
    def test_save_models_untrained(self):
        """Test saving untrained models"""
        ensemble = EnsembleModel()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            results = ensemble.save_models(tmp_dir)
            
            # All should fail because models aren't trained
            assert results["lstm"] == False
            assert results["xgboost"] == False  
            assert results["random_forest"] == False
            
    @patch('backend.models.ensemble_model.TENSORFLOW_AVAILABLE', True)
    @patch('backend.models.ensemble_model.JOBLIB_AVAILABLE', True)
    def test_save_models_trained(self):
        """Test saving trained models"""
        ensemble = EnsembleModel()
        
        # Mock trained models
        mock_tf_model = MagicMock()
        ensemble.models["lstm"].is_trained = True
        ensemble.models["lstm"].model = mock_tf_model
        
        mock_xgb_model = MagicMock()
        ensemble.models["xgboost"].is_trained = True
        ensemble.models["xgboost"].model = mock_xgb_model
        ensemble.models["xgboost"].scaler = MagicMock()
        ensemble.models["xgboost"].feature_importance = {"feat1": 0.6}
        
        mock_rf_model = MagicMock()
        ensemble.models["random_forest"].is_trained = True
        ensemble.models["random_forest"].model = mock_rf_model
        ensemble.models["random_forest"].scaler = MagicMock()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch('backend.models.ensemble_model.joblib') as mock_joblib:
                results = ensemble.save_models(tmp_dir)
                
                assert results["lstm"] == True
                assert results["xgboost"] == True
                assert results["random_forest"] == True
                
                # Verify model card was created
                model_card_path = Path(tmp_dir) / "model_card.json"
                assert model_card_path.exists()
                
                with open(model_card_path) as f:
                    model_card = json.load(f)
                
                assert "ensemble_weights" in model_card
                assert "model_status" in model_card
                assert "training_metadata" in model_card
                
    @patch('backend.models.ensemble_model.TENSORFLOW_AVAILABLE', True)
    @patch('backend.models.ensemble_model.JOBLIB_AVAILABLE', True)
    def test_load_models_success(self):
        """Test loading models successfully"""
        ensemble = EnsembleModel()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create model files
            (tmp_path / "lstm_model.h5").touch()
            (tmp_path / "xgboost_model.joblib").touch()
            (tmp_path / "random_forest_model.joblib").touch()
            
            # Create model card
            model_card = {
                "ensemble_weights": {"lstm": 0.5, "xgboost": 0.3, "random_forest": 0.2},
                "training_metadata": {
                    "lstm": {"sequence_length": 30, "random_seed": 42}
                }
            }
            with open(tmp_path / "model_card.json", "w") as f:
                json.dump(model_card, f)
            
            with patch('backend.models.ensemble_model.keras') as mock_keras, \
                 patch('backend.models.ensemble_model.joblib') as mock_joblib:
                
                # Mock successful loading
                mock_keras.models.load_model.return_value = MagicMock()
                mock_joblib.load.return_value = {
                    "model": MagicMock(),
                    "scaler": MagicMock(),
                    "feature_importance": {"feat1": 0.5}
                }
                
                results = ensemble.load_models(tmp_dir)
                
                assert results["lstm"] == True
                assert results["xgboost"] == True
                assert results["random_forest"] == True
                
                # Verify weights were restored
                assert ensemble.weights["lstm"] == 0.5
                assert ensemble.weights["xgboost"] == 0.3
                assert ensemble.weights["random_forest"] == 0.2
                
    def test_load_models_missing_directory(self):
        """Test loading from non-existent directory"""
        ensemble = EnsembleModel()
        
        results = ensemble.load_models("/non/existent/path")
        
        assert results["lstm"] == False
        assert results["xgboost"] == False
        assert results["random_forest"] == False


class TestEnsembleModelMLOpsIntegration:
    """Test MLOps registry integration functionality"""
    
    @patch('backend.models.ensemble_model.MLOPS_AVAILABLE', True)
    def test_init_with_mlops_enabled(self):
        """Test ensemble initialization with MLOps enabled"""
        with patch('backend.models.ensemble_model.get_model_manager') as mock_manager:
            mock_manager.return_value = MagicMock()
            
            ensemble = EnsembleModel()
            
            assert ensemble.mlops_enabled == True
            assert ensemble.model_manager is not None
            
    @patch('backend.models.ensemble_model.MLOPS_AVAILABLE', False)
    def test_init_with_mlops_disabled(self):
        """Test ensemble initialization with MLOps disabled"""
        ensemble = EnsembleModel()
        
        assert ensemble.mlops_enabled == False
        assert ensemble.model_manager is None
        
    @patch('backend.models.ensemble_model.MLOPS_AVAILABLE', True)
    def test_register_with_mlops_success(self):
        """Test successful MLOps model registration"""
        with patch('backend.models.ensemble_model.get_model_manager') as mock_manager_func:
            mock_manager = MagicMock()
            mock_version = MagicMock()
            mock_version.version = "v1.0.0"
            mock_version.artifact_hash = "abc123"
            
            mock_manager.registry.register_model.return_value = mock_version
            mock_manager_func.return_value = mock_manager
            
            ensemble = EnsembleModel()
            
            training_data = pd.DataFrame({"close": [100, 101, 102]})
            features = pd.DataFrame({"feature1": [1, 2, 3]})
            metrics = {"accuracy": 0.85, "mse": 0.05}
            
            result = ensemble.register_with_mlops(
                "test_model", training_data, features, metrics, "v1.0.0"
            )
            
            assert result is not None
            assert result.version == "v1.0.0"
            mock_manager.registry.register_model.assert_called_once()
            
    def test_register_with_mlops_disabled(self):
        """Test MLOps registration when MLOps is disabled"""
        ensemble = EnsembleModel()  # MLOPs disabled by default in tests
        
        training_data = pd.DataFrame({"close": [100, 101, 102]})
        features = pd.DataFrame({"feature1": [1, 2, 3]})
        metrics = {"accuracy": 0.85}
        
        result = ensemble.register_with_mlops(
            "test_model", training_data, features, metrics
        )
        
        assert result is None
        
    @patch('backend.models.ensemble_model.MLOPS_AVAILABLE', True)
    def test_promote_to_champion_success(self):
        """Test successful champion promotion"""
        with patch('backend.models.ensemble_model.get_model_manager') as mock_manager_func:
            mock_manager = MagicMock()
            mock_manager.registry.promote_to_champion.return_value = True
            mock_manager_func.return_value = mock_manager
            
            ensemble = EnsembleModel()
            
            result = ensemble.promote_to_champion("test_model", "v1.0.0")
            
            assert result == True
            mock_manager.registry.promote_to_champion.assert_called_once_with(
                "test_model", "v1.0.0"
            )
            
    @patch('backend.models.ensemble_model.MLOPS_AVAILABLE', True) 
    def test_get_champion_version(self):
        """Test getting champion model version"""
        with patch('backend.models.ensemble_model.get_model_manager') as mock_manager_func:
            mock_manager = MagicMock()
            mock_version = MagicMock()
            mock_version.version = "v2.0.0"
            mock_manager.registry.get_champion_model.return_value = mock_version
            mock_manager_func.return_value = mock_manager
            
            ensemble = EnsembleModel()
            
            result = ensemble.get_champion_version("test_model")
            
            assert result is not None
            assert result.version == "v2.0.0"
            
    @patch('backend.models.ensemble_model.MLOPS_AVAILABLE', True)
    def test_load_from_registry_champion(self):
        """Test loading champion model from registry"""
        with patch('backend.models.ensemble_model.get_model_manager') as mock_manager_func:
            mock_manager = MagicMock()
            
            # Mock champion model
            mock_champion = MagicMock()
            mock_champion.version = "v1.0.0"
            mock_manager.registry.get_champion_model.return_value = mock_champion
            
            # Mock load artifacts
            mock_artifacts = {
                "ensemble_weights": {"lstm": 0.6, "xgboost": 0.4},
                "performance_history": []
            }
            mock_manager.registry.load_artifacts.return_value = (
                MagicMock(), mock_artifacts, {}
            )
            
            mock_manager_func.return_value = mock_manager
            
            ensemble = EnsembleModel()
            
            result = ensemble.load_from_registry("test_model")
            
            assert result == True
            assert ensemble.weights["lstm"] == 0.6
            assert ensemble.weights["xgboost"] == 0.4


class TestEnsembleModelFeaturePipeline:
    """Test feature pipeline integration"""
    
    @patch('backend.models.ensemble_model.FEATURE_PIPELINE_AVAILABLE', True)
    @patch('backend.models.ensemble_model.align_features_target')
    def test_predict_with_feature_alignment(self, mock_align):
        """Test prediction with feature alignment"""
        ensemble = EnsembleModel()
        
        # Mock feature alignment
        mock_feature_frame = MagicMock()
        mock_feature_frame.X = pd.DataFrame({"feature1": [1, 2, 3]})
        mock_align.return_value = mock_feature_frame
        
        # Mock model predictions
        ensemble.models["lstm"].predict = Mock(return_value=(150.0, 0.8))
        ensemble.models["xgboost"].predict = Mock(return_value=(151.0, 0.7))
        ensemble.models["random_forest"].predict = Mock(return_value=(149.0, 0.6))
        
        price_data = pd.DataFrame({"close": [100, 101, 102]})
        features = pd.DataFrame({"feature1": [1, 2, 3]})
        
        result = ensemble.predict(price_data, features, "AAPL")
        
        mock_align.assert_called_once()
        assert isinstance(result, ModelPrediction)
        
    @patch('backend.models.ensemble_model.FEATURE_PIPELINE_AVAILABLE', True)
    @patch('backend.models.ensemble_model.align_features_target')
    @patch('backend.models.ensemble_model.guard_no_lookahead')
    def test_predict_with_lookahead_guard(self, mock_guard, mock_align):
        """Test prediction with lookahead violation detection"""
        ensemble = EnsembleModel()
        
        # Mock feature alignment
        mock_feature_frame = MagicMock()
        mock_feature_frame.X = pd.DataFrame({"feature1": [1, 2, 3]})
        mock_align.return_value = mock_feature_frame
        
        # Mock lookahead guard raising exception
        mock_guard.side_effect = Exception("Lookahead detected")
        
        # Mock model predictions
        ensemble.models["lstm"].predict = Mock(return_value=(150.0, 0.8))
        ensemble.models["xgboost"].predict = Mock(return_value=(151.0, 0.7))
        ensemble.models["random_forest"].predict = Mock(return_value=(149.0, 0.6))
        
        price_data = pd.DataFrame({"close": [100, 101, 102]})
        features = pd.DataFrame({"feature1": [1, 2, 3]})
        
        # Should still complete prediction despite lookahead warning
        result = ensemble.predict(price_data, features, "AAPL")
        
        mock_guard.assert_called_once()
        assert isinstance(result, ModelPrediction)


class TestEnsembleModelErrorHandling:
    """Test error handling and edge cases"""
    
    def test_predict_empty_data(self):
        """Test prediction with empty data"""
        ensemble = EnsembleModel()
        
        # Mock models to handle empty data gracefully
        ensemble.models["lstm"].predict = Mock(return_value=(0.0, 0.0))
        ensemble.models["xgboost"].predict = Mock(return_value=(0.0, 0.0))
        ensemble.models["random_forest"].predict = Mock(return_value=(0.0, 0.0))
        
        price_data = pd.DataFrame({"close": []})
        features = pd.DataFrame({"feature1": []})
        
        result = ensemble.predict(price_data, features, "AAPL")
        
        assert isinstance(result, ModelPrediction)
        assert result.ensemble_prediction == 0.0
        assert result.ensemble_confidence == 0.0
        
    def test_update_weights_empty_performance(self):
        """Test weight updates with empty performance metrics"""
        ensemble = EnsembleModel()
        original_weights = ensemble.weights.copy()
        
        ensemble.update_weights({})
        
        # Weights should remain unchanged or fall back to defaults
        assert isinstance(ensemble.weights, dict)
        
    @patch('backend.models.ensemble_model.MLOPS_AVAILABLE', True)
    def test_predict_with_schema_mismatch_error(self):
        """Test prediction handling schema mismatch errors"""
        from backend.models.ensemble_model import SchemaValidationError
        
        with patch('backend.models.ensemble_model.get_model_manager') as mock_manager_func:
            mock_manager = MagicMock()
            
            # Mock schema validation failure
            mock_manager.registry.assert_feature_schema.side_effect = SchemaValidationError(
                "Schema mismatch",
                missing_columns=["missing_feature"],
                extra_columns=["extra_feature"]
            )
            
            mock_champion = MagicMock()
            mock_champion.version = "v1.0.0"
            mock_manager.registry.get_champion_model.return_value = mock_champion
            
            mock_manager.registry.load_artifacts.return_value = (
                MagicMock(), 
                {"feature_schema": {"columns": ["expected_feature"]}}, 
                {"feature_schema": {"columns": ["expected_feature"]}}
            )
            
            mock_manager_func.return_value = mock_manager
            
            ensemble = EnsembleModel()
            
            price_data = pd.DataFrame({"close": [100, 101, 102]})
            features = pd.DataFrame({"wrong_feature": [1, 2, 3]})
            
            # Should raise the schema validation error
            with pytest.raises(SchemaValidationError):
                ensemble.predict(price_data, features, "AAPL")


# Performance and Integration Tests
class TestEnsembleModelIntegration:
    """Integration tests for ensemble model workflows"""
    
    @pytest.mark.asyncio
    async def test_full_training_prediction_workflow(self):
        """Test complete training and prediction workflow"""
        ensemble = EnsembleModel()
        
        # Mock all model training
        for model in ensemble.models.values():
            model.train = AsyncMock(return_value=True)
            model.predict = Mock(return_value=(150.0, 0.8))
        
        # Create test data
        price_data = pd.DataFrame({
            "close": np.random.randn(100) + 100,
            "timestamp": pd.date_range("2023-01-01", periods=100, freq="1min")
        })
        features = pd.DataFrame({
            "feature1": np.random.randn(100),
            "feature2": np.random.randn(100)
        })
        
        # Train models
        training_results = await ensemble.train_models(price_data, features)
        assert all(training_results.values())
        
        # Make predictions
        prediction = ensemble.predict(price_data.tail(20), features.tail(20), "AAPL")
        assert isinstance(prediction, ModelPrediction)
        assert prediction.ensemble_prediction > 0
        
        # Update weights based on performance
        performance = {
            "lstm": ModelPerformance("lstm", 0.05, 0.15, 1.2, 0.8, datetime.now()),
            "xgboost": ModelPerformance("xgboost", 0.03, 0.12, 1.5, 0.85, datetime.now()),
            "random_forest": ModelPerformance("random_forest", 0.08, 0.18, 0.9, 0.75, datetime.now())
        }
        ensemble.update_weights(performance)
        
        # Get status
        status = ensemble.get_model_status()
        assert len(status) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
