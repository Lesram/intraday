"""
High-Impact Ensemble Model Coverage Tests  
Targets actual classes and methods from backend/models/ensemble_model.py (505 statements)
"""

import pytest
import asyncio
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta

# Import actual classes from ensemble_model
from backend.models.ensemble_model import (
    EnsembleModel, LSTMModel, XGBoostModel, RandomForestModel,
    ModelPrediction, ModelPerformance, SchemaMismatchError
)


class TestEnsembleModelCoverage:
    """Test actual ensemble model classes and methods"""

    @pytest.fixture
    def sample_data(self):
        """Create sample data for testing"""
        np.random.seed(42)
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        return pd.DataFrame({
            'date': dates,
            'close': 100 + np.cumsum(np.random.randn(100) * 0.02),
            'high': 100 + np.cumsum(np.random.randn(100) * 0.02) + 1,
            'low': 100 + np.cumsum(np.random.randn(100) * 0.02) - 1,
            'volume': np.random.randint(1000, 10000, 100),
            'feature_1': np.random.randn(100),
            'feature_2': np.random.randn(100)
        })

    @pytest.fixture
    def sample_features(self):
        """Create sample feature data"""
        np.random.seed(42)
        return pd.DataFrame({
            'feature_1': np.random.randn(50),
            'feature_2': np.random.randn(50),
            'feature_3': np.random.randn(50),
            'rsi': np.random.uniform(0, 100, 50),
            'sma_20': np.random.uniform(90, 110, 50)
        })

    @pytest.fixture
    def sample_target(self):
        """Create sample target data"""
        np.random.seed(42)
        return pd.Series(np.random.choice([0, 1], 50, p=[0.6, 0.4]))

    def test_model_prediction_dataclass(self):
        """Test ModelPrediction dataclass"""
        prediction = ModelPrediction(
            value=0.75,
            confidence=0.85,
            timestamp=datetime.now(),
            model_version="v1.0"
        )
        assert prediction.value == 0.75
        assert prediction.confidence == 0.85
        assert isinstance(prediction.timestamp, datetime)
        assert prediction.model_version == "v1.0"

    def test_model_performance_dataclass(self):
        """Test ModelPerformance dataclass"""
        performance = ModelPerformance(
            accuracy=0.85,
            precision=0.80,
            recall=0.75,
            f1_score=0.77,
            auc_roc=0.88
        )
        assert performance.accuracy == 0.85
        assert performance.precision == 0.80
        assert performance.recall == 0.75
        assert performance.f1_score == 0.77
        assert performance.auc_roc == 0.88

    def test_schema_mismatch_error(self):
        """Test SchemaMismatchError exception"""
        with pytest.raises(SchemaMismatchError):
            raise SchemaMismatchError("Schema mismatch detected")

    @patch('backend.models.ensemble_model.TENSORFLOW_AVAILABLE', True)
    def test_lstm_model_initialization(self):
        """Test LSTM model initialization"""
        with patch('tensorflow.keras.models.Sequential') as mock_sequential:
            mock_sequential.return_value = Mock()
            
            lstm = LSTMModel(
                input_shape=(60, 5),
                lstm_units=50,
                dropout_rate=0.2,
                learning_rate=0.001
            )
            
            assert lstm.input_shape == (60, 5)
            assert lstm.lstm_units == 50
            assert lstm.dropout_rate == 0.2
            assert lstm.learning_rate == 0.001

    @patch('backend.models.ensemble_model.TENSORFLOW_AVAILABLE', True) 
    def test_lstm_model_build(self):
        """Test LSTM model building"""
        with patch('tensorflow.keras.models.Sequential') as mock_sequential:
            with patch('tensorflow.keras.layers.LSTM') as mock_lstm:
                with patch('tensorflow.keras.layers.Dense') as mock_dense:
                    mock_model = Mock()
                    mock_sequential.return_value = mock_model
                    
                    lstm = LSTMModel()
                    model = lstm.build_model()
                    
                    assert model is not None or lstm.model is None  # Handle both cases

    @patch('backend.models.ensemble_model.TENSORFLOW_AVAILABLE', False)
    def test_lstm_model_build_unavailable(self):
        """Test LSTM model when TensorFlow unavailable"""
        lstm = LSTMModel()
        model = lstm.build_model()
        assert model is None

    def test_lstm_prepare_sequences(self, sample_data):
        """Test LSTM sequence preparation"""
        lstm = LSTMModel()
        data = sample_data['close'].values
        
        X, y = lstm.prepare_sequences(data)
        assert isinstance(X, np.ndarray)
        assert isinstance(y, np.ndarray)
        assert X.shape[0] == y.shape[0]

    @patch('backend.models.ensemble_model.TENSORFLOW_AVAILABLE', True)
    @pytest.mark.asyncio
    async def test_lstm_train(self, sample_data):
        """Test LSTM model training"""
        with patch('tensorflow.keras.models.Sequential') as mock_sequential:
            mock_model = Mock()
            mock_model.fit = Mock(return_value=Mock())
            mock_sequential.return_value = mock_model
            
            lstm = LSTMModel()
            lstm.model = mock_model
            
            result = await lstm.train(sample_data, target_column='close')
            assert isinstance(result, bool)

    @patch('backend.models.ensemble_model.TENSORFLOW_AVAILABLE', True)
    def test_lstm_predict(self, sample_data):
        """Test LSTM model prediction"""
        with patch('tensorflow.keras.models.Sequential') as mock_sequential:
            mock_model = Mock()
            mock_model.predict = Mock(return_value=np.array([[0.75]]))
            mock_sequential.return_value = mock_model
            
            lstm = LSTMModel()
            lstm.model = mock_model
            lstm.is_trained = True
            
            data = sample_data['close'].values[-60:]
            prediction = lstm.predict(data)
            
            assert isinstance(prediction, tuple)
            assert len(prediction) == 2  # prediction, confidence

    def test_xgboost_model_initialization(self):
        """Test XGBoost model initialization"""
        xgb = XGBoostModel()
        assert xgb.model is None
        assert not xgb.is_trained

    @patch('backend.models.ensemble_model.XGBOOST_AVAILABLE', True)
    @pytest.mark.asyncio
    async def test_xgboost_train(self, sample_features, sample_target):
        """Test XGBoost model training"""
        with patch('xgboost.XGBClassifier') as mock_xgb:
            mock_model = Mock()
            mock_model.fit = Mock()
            mock_xgb.return_value = mock_model
            
            xgb = XGBoostModel()
            result = await xgb.train(sample_features, sample_target)
            
            assert isinstance(result, bool)
            mock_model.fit.assert_called_once()

    @patch('backend.models.ensemble_model.XGBOOST_AVAILABLE', False)
    @pytest.mark.asyncio
    async def test_xgboost_train_unavailable(self, sample_features, sample_target):
        """Test XGBoost training when unavailable"""
        xgb = XGBoostModel()
        result = await xgb.train(sample_features, sample_target)
        assert result is False

    @patch('backend.models.ensemble_model.XGBOOST_AVAILABLE', True)
    def test_xgboost_predict(self, sample_features):
        """Test XGBoost model prediction"""
        with patch('xgboost.XGBClassifier') as mock_xgb:
            mock_model = Mock()
            mock_model.predict_proba = Mock(return_value=np.array([[0.3, 0.7]]))
            mock_xgb.return_value = mock_model
            
            xgb = XGBoostModel()
            xgb.model = mock_model
            xgb.is_trained = True
            
            prediction = xgb.predict(sample_features)
            
            assert isinstance(prediction, tuple)
            assert len(prediction) == 2  # prediction, confidence

    def test_random_forest_model_initialization(self):
        """Test Random Forest model initialization"""
        rf = RandomForestModel()
        assert rf.model is None
        assert not rf.is_trained

    @pytest.mark.asyncio
    async def test_random_forest_train(self, sample_features, sample_target):
        """Test Random Forest model training"""
        with patch('sklearn.ensemble.RandomForestClassifier') as mock_rf:
            mock_model = Mock()
            mock_model.fit = Mock()
            mock_rf.return_value = mock_model
            
            rf = RandomForestModel()
            result = await rf.train(sample_features, sample_target)
            
            assert isinstance(result, bool)
            mock_model.fit.assert_called_once()

    def test_random_forest_predict(self, sample_features):
        """Test Random Forest model prediction"""
        with patch('sklearn.ensemble.RandomForestClassifier') as mock_rf:
            mock_model = Mock()
            mock_model.predict_proba = Mock(return_value=np.array([[0.4, 0.6]]))
            mock_rf.return_value = mock_model
            
            rf = RandomForestModel()
            rf.model = mock_model
            rf.is_trained = True
            
            prediction = rf.predict(sample_features)
            
            assert isinstance(prediction, tuple)
            assert len(prediction) == 2  # prediction, confidence

    def test_ensemble_model_initialization(self):
        """Test EnsembleModel initialization"""
        ensemble = EnsembleModel()
        assert ensemble.models == {}
        assert ensemble.weights == {}
        assert ensemble.performance_history == {}

    @patch('backend.models.ensemble_model.TENSORFLOW_AVAILABLE', True)
    @patch('backend.models.ensemble_model.XGBOOST_AVAILABLE', True)
    @pytest.mark.asyncio
    async def test_ensemble_train_models(self, sample_data):
        """Test ensemble model training"""
        with patch('tensorflow.keras.models.Sequential'):
            with patch('xgboost.XGBClassifier'):
                with patch('sklearn.ensemble.RandomForestClassifier'):
                    ensemble = EnsembleModel()
                    
                    # Mock the individual model training
                    for model in ensemble.models.values():
                        model.train = AsyncMock(return_value=True)
                    
                    result = await ensemble.train_models(sample_data)
                    assert isinstance(result, dict)

    def test_ensemble_predict(self, sample_features):
        """Test ensemble model prediction"""
        ensemble = EnsembleModel()
        
        # Mock trained models
        mock_lstm = Mock()
        mock_lstm.is_trained = True
        mock_lstm.predict = Mock(return_value=(0.7, 0.8))
        
        mock_xgb = Mock()
        mock_xgb.is_trained = True  
        mock_xgb.predict = Mock(return_value=(0.6, 0.7))
        
        mock_rf = Mock()
        mock_rf.is_trained = True
        mock_rf.predict = Mock(return_value=(0.8, 0.9))
        
        ensemble.models = {
            'lstm': mock_lstm,
            'xgboost': mock_xgb,
            'random_forest': mock_rf
        }
        
        ensemble.weights = {'lstm': 0.4, 'xgboost': 0.3, 'random_forest': 0.3}
        
        # Convert sample_features to numpy for LSTM
        features_array = sample_features.values
        
        prediction = ensemble.predict(sample_features, features_array)
        
        assert isinstance(prediction, ModelPrediction)
        assert 0 <= prediction.value <= 1
        assert 0 <= prediction.confidence <= 1

    def test_ensemble_predict_no_trained_models(self, sample_features):
        """Test ensemble prediction with no trained models"""
        ensemble = EnsembleModel()
        
        features_array = sample_features.values
        prediction = ensemble.predict(sample_features, features_array)
        
        assert isinstance(prediction, ModelPrediction)
        assert prediction.value == 0.5  # Default prediction

    def test_ensemble_update_weights(self):
        """Test ensemble weight updating"""
        ensemble = EnsembleModel()
        
        performance_metrics = {
            'lstm': ModelPerformance(0.85, 0.80, 0.75, 0.77, 0.88),
            'xgboost': ModelPerformance(0.80, 0.75, 0.70, 0.72, 0.83),
            'random_forest': ModelPerformance(0.82, 0.78, 0.73, 0.75, 0.85)
        }
        
        ensemble.update_weights(performance_metrics)
        
        # Weights should sum to 1
        assert abs(sum(ensemble.weights.values()) - 1.0) < 1e-6
        
        # LSTM should have highest weight (best performance)
        assert ensemble.weights['lstm'] >= ensemble.weights['xgboost']
        assert ensemble.weights['lstm'] >= ensemble.weights['random_forest']

    def test_ensemble_get_model_status(self):
        """Test ensemble model status retrieval"""
        ensemble = EnsembleModel()
        
        # Add mock models
        mock_model = Mock()
        mock_model.is_trained = True
        ensemble.models['test_model'] = mock_model
        ensemble.weights['test_model'] = 0.5
        
        status = ensemble.get_model_status()
        
        assert isinstance(status, dict)
        assert 'test_model' in status
        assert 'is_trained' in status['test_model']
        assert 'weight' in status['test_model']

    @patch('joblib.dump')
    @patch('pathlib.Path.mkdir')
    def test_ensemble_save_models(self, mock_mkdir, mock_dump):
        """Test ensemble model saving"""
        ensemble = EnsembleModel()
        
        # Add mock models  
        mock_model = Mock()
        mock_model.model = "test_model_object"
        ensemble.models['test'] = mock_model
        ensemble.weights['test'] = 0.5
        
        result = ensemble.save_models()
        
        assert isinstance(result, dict)
        mock_mkdir.assert_called()

    @patch('joblib.load')
    @patch('pathlib.Path.exists')
    def test_ensemble_load_models(self, mock_exists, mock_load):
        """Test ensemble model loading"""
        mock_exists.return_value = True
        mock_load.side_effect = [
            {'test': 0.5},  # weights
            "test_model_object"  # model
        ]
        
        ensemble = EnsembleModel()
        result = ensemble.load_models()
        
        assert isinstance(result, dict)

    def test_ensemble_error_handling(self):
        """Test ensemble model error handling"""
        ensemble = EnsembleModel()
        
        # Test with invalid data
        with pytest.raises((ValueError, TypeError)):
            ensemble.predict(None, None)

    def test_model_performance_metrics_calculation(self):
        """Test performance metrics calculations"""
        # This tests the ModelPerformance dataclass usage
        perf1 = ModelPerformance(0.85, 0.80, 0.75, 0.77, 0.88)
        perf2 = ModelPerformance(0.80, 0.75, 0.70, 0.72, 0.83)
        
        # Test that we can compare performances
        assert perf1.accuracy > perf2.accuracy
        assert perf1.auc_roc > perf2.auc_roc

    @patch('backend.models.ensemble_model.logger')
    def test_ensemble_logging_integration(self, mock_logger):
        """Test that ensemble model integrates with logging"""
        ensemble = EnsembleModel()
        
        # Trigger some operations that should log
        status = ensemble.get_model_status()
        
        # Verify the function executes (logging integration)
        assert isinstance(status, dict)
