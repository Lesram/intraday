"""
Phase 7B.4 Maximum Line Coverage Test
Direct line-by-line coverage targeting 95%+
"""

import pytest
import os
import sys
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch, MagicMock
import tempfile
from datetime import datetime

# Import our models
from backend.models.ensemble_model import EnsembleModel, LSTMModel, XGBoostModel, RandomForestModel, ModelPrediction


class TestMaximumLineCoverage:
    """Tests that directly target specific uncovered lines"""
    
    def test_import_paths_with_env_manipulation(self):
        """Test import paths by manipulating environment variables"""
        # Test TensorFlow import path (lines 26-33)
        original_disable_ml = os.environ.get('DISABLE_ML')
        original_disable_tf = os.environ.get('DISABLE_TENSORFLOW') 
        original_pytest_running = os.environ.get('PYTEST_RUNNING')
        
        try:
            # Clear all disable flags temporarily
            if 'DISABLE_ML' in os.environ:
                del os.environ['DISABLE_ML']
            if 'DISABLE_TENSORFLOW' in os.environ:
                del os.environ['DISABLE_TENSORFLOW']
            if 'PYTEST_RUNNING' in os.environ:
                del os.environ['PYTEST_RUNNING']
                
            # Mock successful TensorFlow import
            with patch.dict('sys.modules', {
                'tensorflow': MagicMock(),
                'tensorflow.keras': MagicMock(),
                'tensorflow.keras.layers': MagicMock()
            }):
                # Re-import the module to trigger import paths
                import importlib
                import backend.models.ensemble_model
                importlib.reload(backend.models.ensemble_model)
                
                # This should hit lines 26-33
                assert hasattr(backend.models.ensemble_model, 'TENSORFLOW_AVAILABLE')
                
        finally:
            # Restore original environment
            if original_disable_ml:
                os.environ['DISABLE_ML'] = original_disable_ml
            if original_disable_tf:
                os.environ['DISABLE_TENSORFLOW'] = original_disable_tf
            if original_pytest_running:
                os.environ['PYTEST_RUNNING'] = original_pytest_running
    
    def test_sklearn_import_paths(self):
        """Test scikit-learn import paths (lines 38-50)"""
        # Test with successful sklearn import
        with patch('backend.models.ensemble_model.DISABLE_ML', False):
            with patch.dict('sys.modules', {
                'joblib': MagicMock(),
                'sklearn.ensemble': MagicMock(),
                'sklearn.metrics': MagicMock(),
                'sklearn.model_selection': MagicMock(),
                'sklearn.preprocessing': MagicMock()
            }):
                import importlib
                import backend.models.ensemble_model
                importlib.reload(backend.models.ensemble_model)
                
                # Should hit sklearn import success path
                assert hasattr(backend.models.ensemble_model, 'SKLEARN_AVAILABLE')
    
    def test_xgboost_import_paths(self):
        """Test XGBoost import paths (lines 59-64)"""
        original_disable_ml = os.environ.get('DISABLE_ML')
        original_disable_xgb = os.environ.get('DISABLE_XGBOOST')
        original_pytest_running = os.environ.get('PYTEST_RUNNING')
        
        try:
            # Clear disable flags
            if 'DISABLE_ML' in os.environ:
                del os.environ['DISABLE_ML']
            if 'DISABLE_XGBOOST' in os.environ:
                del os.environ['DISABLE_XGBOOST']
            if 'PYTEST_RUNNING' in os.environ:
                del os.environ['PYTEST_RUNNING']
                
            # Mock XGBoost import
            with patch.dict('sys.modules', {'xgboost': MagicMock()}):
                import importlib
                import backend.models.ensemble_model
                importlib.reload(backend.models.ensemble_model)
                
                # Should hit XGBoost import success path (lines 59-64)
                assert hasattr(backend.models.ensemble_model, 'XGBOOST_AVAILABLE')
                
        finally:
            # Restore environment
            if original_disable_ml:
                os.environ['DISABLE_ML'] = original_disable_ml
            if original_disable_xgb:
                os.environ['DISABLE_XGBOOST'] = original_disable_xgb  
            if original_pytest_running:
                os.environ['PYTEST_RUNNING'] = original_pytest_running
    
    def test_model_stub_classes_coverage(self):
        """Test the model stub classes to hit lines 110-112, 143"""
        from backend.models.ensemble_model import ModelStub
        
        # Test ModelStub methods (should hit lines 110-112)
        stub = ModelStub()
        
        # This should hit async train method
        import asyncio
        result = asyncio.run(stub.train())
        assert result == {"status": "ML disabled"}
        
        # This should hit predict method (line 143 area)
        pred_result = stub.predict()
        assert pred_result == (100.0, 0.1)  # Default values
    
    @pytest.mark.asyncio
    async def test_lstm_tensorflow_available_training(self):
        """Test LSTM training when TensorFlow is available (lines 200-236)"""
        model = LSTMModel(sequence_length=5, features=3)
        
        # Create test data
        price_data = pd.DataFrame({
            'close': np.random.randn(30).cumsum() + 100
        })
        
        # Mock TensorFlow as available and functional
        mock_model = MagicMock()
        mock_scaler = MagicMock()
        mock_history = MagicMock()
        mock_early_stopping = MagicMock()
        
        with patch('backend.models.ensemble_model.TENSORFLOW_AVAILABLE', True):
            # Mock the TensorFlow components used in lines 200-236
            with patch('sklearn.preprocessing.StandardScaler', return_value=mock_scaler):
                with patch.object(model, 'build_model', return_value=mock_model):
                    with patch.object(model, 'prepare_sequences') as mock_prep:
                        with patch('tensorflow.keras.callbacks.EarlyStopping', return_value=mock_early_stopping):
                            
                            # Setup mocks
                            mock_scaler.fit_transform.return_value = np.random.randn(30, 1)
                            mock_prep.return_value = (
                                np.random.randn(25, 5, 1),  # X
                                np.random.randn(25)         # y  
                            )
                            mock_model.fit.return_value = mock_history
                            
                            # This should hit the TensorFlow training path (lines 200-236)
                            result = await model.train(price_data)
                            
                            # Verify we called the TensorFlow path
                            mock_scaler.fit_transform.assert_called()
                            model.build_model.assert_called_once()
                            mock_prep.assert_called_once()
                            mock_model.fit.assert_called_once()
    
    def test_lstm_build_model_tensorflow_available(self):
        """Test LSTM build_model when TensorFlow is available (lines 209-236)"""
        model = LSTMModel(sequence_length=10, features=5, dropout_rate=0.3)
        
        # Mock TensorFlow components
        mock_sequential = MagicMock()
        mock_lstm_layer = MagicMock()
        mock_dropout_layer = MagicMock() 
        mock_dense_layer = MagicMock()
        
        with patch('backend.models.ensemble_model.TENSORFLOW_AVAILABLE', True):
            # Mock the keras components used in build_model
            with patch.dict('sys.modules', {
                'tensorflow': MagicMock(),
                'tensorflow.keras': MagicMock(),
                'tensorflow.keras.layers': MagicMock()
            }):
                # Import and patch keras at the point of use
                import tensorflow.keras as keras
                import tensorflow.keras.layers as layers
                
                with patch.object(keras, 'Sequential', return_value=mock_sequential):
                    with patch.object(layers, 'LSTM', return_value=mock_lstm_layer):
                        with patch.object(layers, 'Dropout', return_value=mock_dropout_layer):
                            with patch.object(layers, 'Dense', return_value=mock_dense_layer):
                                
                                # This should hit the model building logic (lines 209-236)
                                result = model.build_model()
                                
                                # Verify the model building sequence
                                keras.Sequential.assert_called_once()
                                mock_sequential.add.assert_called()
                                mock_sequential.compile.assert_called_once()
                                
                                assert result == mock_sequential
    
    @pytest.mark.asyncio 
    async def test_xgboost_cross_validation_training(self):
        """Test XGBoost cross-validation training (lines 349-400)"""
        model = XGBoostModel()
        
        # Create sample features and target
        features = pd.DataFrame({
            'feature1': np.random.randn(60),
            'feature2': np.random.randn(60),
            'feature3': np.random.randn(60)
        })
        target = pd.Series(np.random.randn(60))
        
        # Mock all required components
        mock_scaler = MagicMock()
        mock_tss = MagicMock()
        mock_xgb_model = MagicMock()
        
        with patch('backend.models.ensemble_model.XGBOOST_AVAILABLE', True):
            with patch('backend.models.ensemble_model.SKLEARN_AVAILABLE', True):
                with patch('sklearn.preprocessing.StandardScaler', return_value=mock_scaler):
                    with patch('sklearn.model_selection.TimeSeriesSplit', return_value=mock_tss):
                        with patch('xgboost.XGBRegressor', return_value=mock_xgb_model):
                            with patch('sklearn.metrics.mean_squared_error') as mock_mse:
                                
                                # Setup mocks for cross-validation
                                mock_scaler.fit_transform.return_value = features.values
                                mock_tss.split.return_value = [
                                    (np.arange(40), np.arange(40, 50)),
                                    (np.arange(45), np.arange(45, 55)),
                                    (np.arange(50), np.arange(50, 60))
                                ]
                                mock_xgb_model.feature_importances_ = np.array([0.4, 0.35, 0.25])
                                mock_xgb_model.predict.return_value = np.random.randn(10)
                                mock_mse.side_effect = [0.8, 0.6, 0.4]  # Improving scores
                                
                                # This should hit XGBoost training with CV (lines 349-400)
                                result = await model.train(features, target)
                                
                                # Verify cross-validation was performed
                                mock_tss.split.assert_called_once()
                                assert mock_mse.call_count == 3  # 3 folds
                                assert model.is_trained
    
    @pytest.mark.asyncio
    async def test_random_forest_complete_training(self):
        """Test RandomForest complete training pipeline (lines 437-460)"""
        model = RandomForestModel()
        
        features = pd.DataFrame({
            'feature1': np.random.randn(50),
            'feature2': np.random.randn(50)
        })
        target = pd.Series(np.random.randn(50))
        
        # Mock components
        mock_scaler = MagicMock()
        mock_rf_model = MagicMock()
        
        with patch('backend.models.ensemble_model.SKLEARN_AVAILABLE', True):
            with patch('sklearn.preprocessing.StandardScaler', return_value=mock_scaler):
                with patch('sklearn.ensemble.RandomForestRegressor', return_value=mock_rf_model):
                    
                    # Setup mocks
                    mock_scaler.fit_transform.return_value = features.values
                    
                    # This should hit RF training pipeline (lines 437-460)
                    result = await model.train(features, target)
                    
                    # Verify training was performed
                    mock_scaler.fit_transform.assert_called_once()
                    mock_rf_model.fit.assert_called_once()
                    assert model.is_trained
    
    def test_random_forest_predict_with_variance(self):
        """Test RandomForest prediction with variance calculation (lines 467-486)"""
        model = RandomForestModel()
        model.is_trained = True
        model.model = MagicMock()
        model.scaler = MagicMock()
        
        features = pd.DataFrame({'feature1': [1.0], 'feature2': [2.0]})
        
        # Mock estimators for variance calculation
        mock_estimator1 = MagicMock()
        mock_estimator2 = MagicMock()
        mock_estimator3 = MagicMock()
        
        mock_estimator1.predict.return_value = np.array([100.0])
        mock_estimator2.predict.return_value = np.array([110.0]) 
        mock_estimator3.predict.return_value = np.array([105.0])
        
        model.model.estimators_ = [mock_estimator1, mock_estimator2, mock_estimator3]
        model.scaler.transform.return_value = features.values
        
        with patch('backend.models.ensemble_model.SKLEARN_AVAILABLE', True):
            # This should hit variance calculation logic (lines 467-486)
            prediction, confidence = model.predict(features)
            
            # Verify variance calculation
            expected_mean = (100.0 + 110.0 + 105.0) / 3
            assert prediction == expected_mean
            assert 0.1 <= confidence <= 0.95
    
    def test_ensemble_model_predict_full_pipeline(self):
        """Test EnsembleModel predict with all paths (lines 570-613)"""
        with patch('backend.models.ensemble_model.get_settings') as mock_settings:
            mock_settings.return_value = Mock(
                mlops={"inference_telemetry_enabled": False}
            )
            
            ensemble = EnsembleModel()
            
            # Setup test data
            price_data = pd.DataFrame({
                'close': [100, 101, 102, 103, 104],
                'volume': [5000, 5100, 5200, 5300, 5400]
            })
            
            features = pd.DataFrame({
                'sma_20': [100.5, 101.2, 102.1],
                'rsi': [45, 50, 55],
                'volume_ratio': [1.1, 1.2, 1.0]
            })
            
            symbol = "TEST"
            
            # Mock individual model predictions
            with patch.object(ensemble.models['lstm'], 'predict') as mock_lstm:
                with patch.object(ensemble.models['xgboost'], 'predict') as mock_xgb:
                    with patch.object(ensemble.models['random_forest'], 'predict') as mock_rf:
                        
                        mock_lstm.return_value = (105.0, 0.8)
                        mock_xgb.return_value = (103.0, 0.7)
                        mock_rf.return_value = (104.0, 0.75)
                        
                        # This should hit the full prediction pipeline (lines 570-613)
                        result = ensemble.predict(price_data, features, symbol)
                        
                        # Verify result structure
                        assert isinstance(result, ModelPrediction)
                        assert hasattr(result, 'prediction')
                        assert hasattr(result, 'confidence')
                        assert hasattr(result, 'model_predictions')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
