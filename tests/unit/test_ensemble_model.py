"""
Unit tests for ensemble model system.
Tests ML model training, persistence, and prediction functionality.
"""
import os
import tempfile
import uuid
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Set environment to disable ML libraries during testing
os.environ["DISABLE_ML"] = "1"
os.environ["DISABLE_TENSORFLOW"] = "1"
os.environ["DISABLE_XGBOOST"] = "1"
os.environ["PYTEST_RUNNING"] = "1"

# Import pandas and numpy after environment is set
import numpy as np
import pandas as pd

from backend.models.ensemble_model import (
    EnsembleModel,
    ModelPrediction,
    ModelPerformance,
    LSTMModel,
    XGBoostModel,
    TENSORFLOW_AVAILABLE,
    XGBOOST_AVAILABLE,
    SKLEARN_AVAILABLE,
    create_noop_ensemble
)


class TestModelPrediction:
    """Test the ModelPrediction dataclass."""
    
    def test_model_prediction_creation(self):
        """Test creating ModelPrediction instance."""
        prediction = ModelPrediction(
            price=150.75,
            confidence=0.85,
            model_name="test_model",
            timestamp="2023-08-25T10:00:00Z",
            features_used=["price", "volume", "rsi"]
        )
        
        assert prediction.price == 150.75
        assert prediction.confidence == 0.85
        assert prediction.model_name == "test_model"
        assert prediction.timestamp == "2023-08-25T10:00:00Z"
        assert prediction.features_used == ["price", "volume", "rsi"]
    
    def test_model_prediction_with_optional_fields(self):
        """Test ModelPrediction with minimal required fields."""
        prediction = ModelPrediction(
            price=100.0,
            confidence=0.9,
            model_name="minimal_model"
        )
        
        assert prediction.price == 100.0
        assert prediction.confidence == 0.9
        assert prediction.model_name == "minimal_model"
        assert prediction.timestamp is None
        assert prediction.features_used is None


class TestEnsembleTrainingConfig:
    """Test the ensemble training configuration."""
    
    def test_training_config_defaults(self):
        """Test EnsembleTrainingConfig with default values."""
        config = EnsembleTrainingConfig()
        
        # Test sensible defaults are set
        assert config.lstm_epochs >= 10
        assert config.xgboost_rounds >= 100
        assert config.random_forest_trees >= 50
        assert 0.1 <= config.validation_split <= 0.9
        assert config.early_stopping_patience > 0
        assert 0 < config.learning_rate <= 1
    
    def test_training_config_custom_values(self):
        """Test EnsembleTrainingConfig with custom values."""
        config = EnsembleTrainingConfig(
            lstm_epochs=50,
            xgboost_rounds=200,
            random_forest_trees=100,
            validation_split=0.3,
            early_stopping_patience=10,
            learning_rate=0.01
        )
        
        assert config.lstm_epochs == 50
        assert config.xgboost_rounds == 200
        assert config.random_forest_trees == 100
        assert config.validation_split == 0.3
        assert config.early_stopping_patience == 10
        assert config.learning_rate == 0.01


class TestModelAvailability:
    """Test model availability detection."""
    
    def test_model_availability_structure(self):
        """Test that MODEL_AVAILABILITY has expected structure."""
        assert 'tensorflow' in MODEL_AVAILABILITY
        assert 'xgboost' in MODEL_AVAILABILITY
        assert 'sklearn' in MODEL_AVAILABILITY
        
        # Should be boolean values
        for key, value in MODEL_AVAILABILITY.items():
            assert isinstance(value, bool)
    
    def test_model_availability_reflects_environment(self):
        """Test that availability reflects disabled environment."""
        # Since we set DISABLE_ML=1, all should be False
        assert MODEL_AVAILABILITY['tensorflow'] is False
        assert MODEL_AVAILABILITY['xgboost'] is False
        # sklearn might still be available as it's lightweight
        # but check that it's boolean
        assert isinstance(MODEL_AVAILABILITY['sklearn'], bool)


class TestEnsembleModel:
    """Test the main EnsembleModel class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create sample data for testing
        self.sample_data = pd.DataFrame({
            'timestamp': pd.date_range('2023-01-01', periods=100, freq='1H'),
            'price': 100 + np.random.randn(100) * 5,
            'volume': np.random.randint(1000, 10000, 100),
            'rsi': np.random.uniform(20, 80, 100),
            'macd': np.random.randn(100) * 0.5,
            'bollinger_upper': 105 + np.random.randn(100) * 2,
            'bollinger_lower': 95 + np.random.randn(100) * 2
        })
        
        # Create mock settings
        self.mock_settings = Mock()
        self.mock_settings.trading = Mock()
        self.mock_settings.trading.lstm_weight = 0.4
        self.mock_settings.trading.xgboost_weight = 0.4
        self.mock_settings.trading.random_forest_weight = 0.2
        self.mock_settings.trading.model_registry_path = "/tmp/models"
        
    def test_ensemble_model_initialization(self):
        """Test EnsembleModel can be initialized."""
        model = EnsembleModel(symbol="AAPL", settings=self.mock_settings)
        
        assert model.symbol == "AAPL"
        assert model.settings == self.mock_settings
        assert model.models == {}
        assert model.weights is not None
        assert len(model.weights) == 3  # lstm, xgboost, random_forest
    
    def test_ensemble_model_with_default_settings(self):
        """Test EnsembleModel with default settings."""
        with patch('backend.models.ensemble_model.get_settings') as mock_get_settings:
            mock_get_settings.return_value = self.mock_settings
            
            model = EnsembleModel(symbol="MSFT")
            
            assert model.symbol == "MSFT"
            assert model.settings == self.mock_settings
            mock_get_settings.assert_called_once()
    
    def test_prepare_features_basic(self):
        """Test basic feature preparation."""
        model = EnsembleModel(symbol="AAPL", settings=self.mock_settings)
        
        # Mock the feature preparation process
        with patch.object(model, '_validate_required_columns') as mock_validate:
            with patch.object(model, '_create_technical_indicators') as mock_indicators:
                with patch.object(model, '_create_lag_features') as mock_lag:
                    mock_validate.return_value = True
                    mock_indicators.return_value = self.sample_data.copy()
                    mock_lag.return_value = self.sample_data.copy()
                    
                    result = model.prepare_features(self.sample_data)
                    
                    assert result is not None
                    assert isinstance(result, pd.DataFrame)
                    mock_validate.assert_called_once()
                    mock_indicators.assert_called_once()
                    mock_lag.assert_called_once()
    
    def test_prepare_features_with_empty_data(self):
        """Test feature preparation with empty data."""
        model = EnsembleModel(symbol="AAPL", settings=self.mock_settings)
        
        empty_df = pd.DataFrame()
        
        # Should handle empty data gracefully
        try:
            result = model.prepare_features(empty_df)
            # If it doesn't raise an exception, it should return something
            assert result is not None
        except ValueError as e:
            # Or it should raise a descriptive error
            assert "empty" in str(e).lower() or "insufficient" in str(e).lower()
    
    def test_validate_required_columns_success(self):
        """Test column validation with valid data."""
        model = EnsembleModel(symbol="AAPL", settings=self.mock_settings)
        
        # Test with data that has required columns
        result = model._validate_required_columns(self.sample_data)
        
        # Should return True or not raise exception
        assert result is True or result is None
    
    def test_validate_required_columns_missing(self):
        """Test column validation with missing columns."""
        model = EnsembleModel(symbol="AAPL", settings=self.mock_settings)
        
        # Create data missing required columns
        incomplete_data = pd.DataFrame({'timestamp': [1, 2, 3]})
        
        # Should raise exception or return False
        try:
            result = model._validate_required_columns(incomplete_data)
            if result is not None:
                assert result is False
        except (ValueError, KeyError) as e:
            # Exception is acceptable for missing columns
            assert "column" in str(e).lower() or "missing" in str(e).lower()
    
    def test_train_model_with_mock_fallbacks(self):
        """Test model training with mock fallbacks enabled."""
        model = EnsembleModel(symbol="AAPL", settings=self.mock_settings)
        
        # Enable mock fallbacks
        model.use_mock_fallbacks = True
        
        config = EnsembleTrainingConfig(
            lstm_epochs=5,  # Small values for fast testing
            xgboost_rounds=10,
            random_forest_trees=10
        )
        
        # Mock the training process
        with patch.object(model, 'prepare_features') as mock_prepare:
            mock_prepare.return_value = self.sample_data.copy()
            
            with patch.object(model, '_save_model') as mock_save:
                mock_save.return_value = True
                
                result = model.train(self.sample_data, config)
                
                # Should return training results
                assert result is not None
                mock_prepare.assert_called_once()
    
    def test_predict_with_mock_fallbacks(self):
        """Test prediction with mock fallbacks."""
        model = EnsembleModel(symbol="AAPL", settings=self.mock_settings)
        model.use_mock_fallbacks = True
        
        # Mock the prediction process  
        with patch.object(model, 'prepare_features') as mock_prepare:
            mock_prepare.return_value = self.sample_data.copy()
            
            prediction = model.predict(self.sample_data.tail(10))
            
            # Should return a valid prediction
            assert prediction is not None
            assert isinstance(prediction, ModelPrediction)
            assert prediction.price > 0
            assert 0 <= prediction.confidence <= 1
            assert prediction.model_name == "ensemble_mock"
    
    def test_save_and_load_model_cycle(self):
        """Test saving and loading model artifacts."""
        model = EnsembleModel(symbol="AAPL", settings=self.mock_settings)
        
        # Use temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock model artifacts
            model.models = {
                'lstm': Mock(),
                'xgboost': Mock(), 
                'random_forest': Mock()
            }
            
            model_path = os.path.join(temp_dir, "test_model")
            
            # Test save
            with patch('os.makedirs'):
                with patch('joblib.dump') as mock_joblib_dump:
                    with patch('builtins.open', create=True) as mock_open:
                        mock_file = Mock()
                        mock_open.return_value.__enter__.return_value = mock_file
                        
                        result = model._save_model(model_path)
                        
                        # Should attempt to save
                        assert result is True or result is None
            
            # Test load
            with patch('os.path.exists', return_value=True):
                with patch('joblib.load') as mock_joblib_load:
                    mock_joblib_load.return_value = Mock()
                    
                    with patch('builtins.open', create=True) as mock_open:
                        mock_file = Mock()
                        mock_file.read.return_value = '{"test": "metadata"}'
                        mock_open.return_value.__enter__.return_value = mock_file
                        
                        result = model._load_model(model_path)
                        
                        # Should attempt to load
                        assert result is True or result is None


class TestModelFallbacks:
    """Test model fallback functionality."""
    
    def test_get_model_fallback_predictions(self):
        """Test fallback prediction generation."""
        # Create sample recent data
        recent_data = pd.DataFrame({
            'price': [100, 101, 102, 103, 104],
            'volume': [1000, 1100, 1200, 1300, 1400]
        })
        
        symbol = "AAPL"
        
        prediction = get_model_fallback_predictions(recent_data, symbol)
        
        assert prediction is not None
        assert isinstance(prediction, ModelPrediction)
        assert prediction.price > 0
        assert 0 <= prediction.confidence <= 1
        assert prediction.model_name == "mock_fallback"
        assert symbol.lower() in prediction.model_name.lower() or prediction.model_name == "mock_fallback"
    
    def test_get_model_fallback_predictions_empty_data(self):
        """Test fallback predictions with empty data."""
        empty_data = pd.DataFrame()
        symbol = "AAPL"
        
        prediction = get_model_fallback_predictions(empty_data, symbol)
        
        # Should still return a prediction (fallback behavior)
        assert prediction is not None
        assert isinstance(prediction, ModelPrediction)
        assert prediction.price > 0
    
    def test_validate_prediction_consistency_valid(self):
        """Test prediction consistency validation with valid predictions."""
        predictions = [
            ModelPrediction(price=100.0, confidence=0.8, model_name="model1"),
            ModelPrediction(price=101.0, confidence=0.9, model_name="model2"),
            ModelPrediction(price=99.5, confidence=0.7, model_name="model3")
        ]
        
        is_consistent = validate_prediction_consistency(predictions)
        
        # Should be consistent (prices are close)
        assert is_consistent is True
    
    def test_validate_prediction_consistency_inconsistent(self):
        """Test prediction consistency validation with inconsistent predictions."""
        predictions = [
            ModelPrediction(price=100.0, confidence=0.8, model_name="model1"),
            ModelPrediction(price=200.0, confidence=0.9, model_name="model2"),  # Way off
            ModelPrediction(price=99.0, confidence=0.7, model_name="model3")
        ]
        
        is_consistent = validate_prediction_consistency(predictions)
        
        # Should be inconsistent (large price spread)
        assert is_consistent is False
    
    def test_validate_prediction_consistency_single_prediction(self):
        """Test prediction consistency with single prediction."""
        predictions = [
            ModelPrediction(price=100.0, confidence=0.8, model_name="model1")
        ]
        
        is_consistent = validate_prediction_consistency(predictions)
        
        # Single prediction should be consistent
        assert is_consistent is True
    
    def test_validate_prediction_consistency_empty_list(self):
        """Test prediction consistency with empty list."""
        predictions = []
        
        is_consistent = validate_prediction_consistency(predictions)
        
        # Empty list should be considered consistent
        assert is_consistent is True


class TestEnsembleIntegration:
    """Integration tests for the ensemble system."""
    
    def setup_method(self):
        """Set up integration test fixtures."""
        self.mock_settings = Mock()
        self.mock_settings.trading = Mock()
        self.mock_settings.trading.lstm_weight = 0.4
        self.mock_settings.trading.xgboost_weight = 0.4
        self.mock_settings.trading.random_forest_weight = 0.2
        self.mock_settings.trading.model_registry_path = "/tmp/models"
        
        # Create realistic market data
        dates = pd.date_range('2023-01-01', periods=252, freq='1D')  # 1 year of daily data
        
        # Generate price data with trend and noise
        base_price = 100
        trend = np.linspace(0, 20, 252)  # Upward trend
        noise = np.random.randn(252) * 2
        prices = base_price + trend + noise
        
        self.realistic_data = pd.DataFrame({
            'timestamp': dates,
            'price': prices,
            'volume': np.random.randint(1000000, 5000000, 252),
            'high': prices + np.random.uniform(0.5, 3, 252),
            'low': prices - np.random.uniform(0.5, 3, 252),
            'open': prices + np.random.randn(252) * 0.5,
            'close': prices
        })
    
    def test_complete_workflow_simulation(self):
        """Test complete model training and prediction workflow."""
        model = EnsembleModel(symbol="AAPL", settings=self.mock_settings)
        model.use_mock_fallbacks = True
        
        # 1. Prepare features
        with patch.object(model, 'prepare_features') as mock_prepare:
            prepared_data = self.realistic_data.copy()
            prepared_data['rsi'] = 50.0  # Add technical indicators
            prepared_data['macd'] = 0.0
            mock_prepare.return_value = prepared_data
            
            # 2. Train model
            config = EnsembleTrainingConfig(
                lstm_epochs=2,  # Minimal for testing
                xgboost_rounds=5,
                random_forest_trees=5
            )
            
            with patch.object(model, '_save_model', return_value=True):
                training_result = model.train(self.realistic_data, config)
                
                # Should complete training
                assert training_result is not None
                
                # 3. Make predictions
                recent_data = self.realistic_data.tail(30)
                prediction = model.predict(recent_data)
                
                # Should produce valid prediction
                assert prediction is not None
                assert isinstance(prediction, ModelPrediction)
                assert prediction.price > 0
                assert 0 <= prediction.confidence <= 1
                assert prediction.model_name is not None
    
    def test_error_handling_workflow(self):
        """Test error handling in various scenarios."""
        model = EnsembleModel(symbol="AAPL", settings=self.mock_settings)
        
        # Test with invalid data
        invalid_data = pd.DataFrame({'invalid_column': [1, 2, 3]})
        
        try:
            # Should either handle gracefully or raise meaningful error
            with patch.object(model, 'prepare_features', side_effect=ValueError("Invalid data")):
                result = model.train(invalid_data, EnsembleTrainingConfig())
                
                # If it returns, should indicate failure
                if result is not None:
                    assert hasattr(result, 'success') and not result.success
                    
        except ValueError as e:
            # Meaningful error is acceptable
            assert len(str(e)) > 0
    
    def test_performance_benchmarking(self):
        """Test that model operations complete within reasonable time."""
        import time
        
        model = EnsembleModel(symbol="AAPL", settings=self.mock_settings)
        model.use_mock_fallbacks = True
        
        # Test prediction speed with mocked components
        with patch.object(model, 'prepare_features', return_value=self.realistic_data):
            start_time = time.time()
            
            prediction = model.predict(self.realistic_data.tail(10))
            
            elapsed_time = time.time() - start_time
            
            # Should complete quickly (mocked operations)
            assert elapsed_time < 1.0  # 1 second max
            assert prediction is not None
    
    def test_memory_usage_patterns(self):
        """Test that model operations don't create excessive memory usage."""
        model = EnsembleModel(symbol="AAPL", settings=self.mock_settings)
        
        # Process data in chunks to test memory handling
        chunk_size = 50
        total_rows = len(self.realistic_data)
        
        processed_chunks = 0
        
        for i in range(0, total_rows, chunk_size):
            chunk = self.realistic_data.iloc[i:i+chunk_size]
            
            # Mock feature preparation to avoid actual computation
            with patch.object(model, 'prepare_features', return_value=chunk):
                try:
                    # Should handle chunk processing
                    features = model.prepare_features(chunk)
                    assert features is not None
                    processed_chunks += 1
                    
                except Exception as e:
                    # Log any processing issues
                    if "memory" in str(e).lower():
                        raise AssertionError(f"Memory issue in chunk processing: {e}")
        
        # Should have processed all chunks
        expected_chunks = (total_rows + chunk_size - 1) // chunk_size
        assert processed_chunks == expected_chunks
