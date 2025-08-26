"""
ML-Enabled Test Configuration for High Coverage Testing
This configuration enables actual ML libraries for comprehensive coverage testing
"""

import os
import sys
import warnings
import pytest
import asyncio
from unittest.mock import Mock, patch
import pandas as pd
import numpy as np

# Enable ML libraries for high coverage testing
os.environ.pop('DISABLE_ML', None)
os.environ.pop('DISABLE_TENSORFLOW', None)
os.environ.pop('DISABLE_XGBOOST', None)
os.environ.pop('DISABLE_TORCH', None)
os.environ['ENABLE_ML_TESTING'] = '1'

# Still suppress verbose ML library logging
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# Import actual ML libraries with fallback to mocks
TENSORFLOW_AVAILABLE = False
XGBOOST_AVAILABLE = False
SKLEARN_AVAILABLE = False

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers, callbacks
    TENSORFLOW_AVAILABLE = True
    print("✅ TensorFlow loaded for testing")
except ImportError as e:
    print(f"❌ TensorFlow not available: {e}")
    # Create comprehensive TensorFlow mocks
    tf = Mock()
    keras = Mock()
    layers = Mock()
    callbacks = Mock()
    
    # Configure keras.Sequential mock
    mock_model = Mock()
    mock_model.compile = Mock()
    mock_model.fit = Mock(return_value=Mock(history={'loss': [0.1, 0.05], 'val_loss': [0.12, 0.06]}))
    mock_model.predict = Mock(return_value=[[100.5]])
    keras.Sequential = Mock(return_value=mock_model)
    
    # Configure layers mocks
    layers.LSTM = Mock(return_value=Mock())
    layers.Dense = Mock(return_value=Mock())
    layers.Dropout = Mock(return_value=Mock())
    
    # Configure callbacks mocks
    callbacks.EarlyStopping = Mock(return_value=Mock())
    callbacks.ReduceLROnPlateau = Mock(return_value=Mock())
    
    # Add to sys.modules
    sys.modules['tensorflow'] = tf
    sys.modules['tensorflow.keras'] = keras
    sys.modules['tensorflow.keras.layers'] = layers
    sys.modules['tensorflow.keras.callbacks'] = callbacks

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
    print("✅ XGBoost loaded for testing")
except ImportError as e:
    print(f"❌ XGBoost not available: {e}")
    # Create XGBoost mock
    xgb = Mock()
    
    # Configure XGBRegressor mock
    mock_xgb_model = Mock()
    mock_xgb_model.fit = Mock()
    mock_xgb_model.predict = Mock(return_value=np.array([102.5, 103.0, 101.8]))
    mock_xgb_model.feature_importances_ = np.array([0.4, 0.35, 0.25])
    xgb.XGBRegressor = Mock(return_value=mock_xgb_model)
    
    sys.modules['xgboost'] = xgb

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import mean_squared_error, mean_absolute_error
    import joblib
    SKLEARN_AVAILABLE = True
    print("✅ Scikit-learn loaded for testing")
except ImportError as e:
    print(f"❌ Scikit-learn not available: {e}")
    # Create sklearn mocks
    from unittest.mock import MagicMock
    
    # Standard Scaler mock
    mock_scaler = MagicMock()
    mock_scaler_instance = MagicMock()
    mock_scaler_instance.fit_transform = Mock(return_value=np.random.randn(50, 3))
    mock_scaler_instance.transform = Mock(return_value=np.random.randn(5, 3))
    mock_scaler_instance.inverse_transform = Mock(return_value=np.array([[105.2]]))
    mock_scaler.return_value = mock_scaler_instance
    
    # RandomForestRegressor mock
    mock_rf_model = MagicMock()
    mock_rf_model.fit = Mock()
    mock_rf_model.predict = Mock(return_value=np.array([104.0]))
    
    # Mock individual estimators for variance calculation
    mock_estimator1 = Mock()
    mock_estimator2 = Mock()  
    mock_estimator3 = Mock()
    mock_estimator1.predict.return_value = np.array([102.0])
    mock_estimator2.predict.return_value = np.array([106.0])
    mock_estimator3.predict.return_value = np.array([104.0])
    mock_rf_model.estimators_ = [mock_estimator1, mock_estimator2, mock_estimator3]
    
    # TimeSeriesSplit mock
    mock_tss = Mock()
    mock_tss.split.return_value = [
        (np.arange(30), np.arange(30, 40)),
        (np.arange(35), np.arange(35, 45)),
        (np.arange(40), np.arange(40, 50))
    ]
    
    # Metrics mocks
    mock_mse = Mock(side_effect=[0.8, 0.6, 0.4])
    mock_mae = Mock(side_effect=[0.5, 0.4, 0.3])
    
    # Mock joblib
    mock_joblib = Mock()
    mock_joblib.dump = Mock()
    mock_joblib.load = Mock(return_value=mock_rf_model)
    
    # Add to sys.modules with proper module structure
    sklearn_module = Mock()
    sklearn_ensemble = Mock()
    sklearn_preprocessing = Mock()
    sklearn_model_selection = Mock()
    sklearn_metrics = Mock()
    
    sklearn_ensemble.RandomForestRegressor = Mock(return_value=mock_rf_model)
    sklearn_preprocessing.StandardScaler = mock_scaler
    sklearn_model_selection.TimeSeriesSplit = Mock(return_value=mock_tss)
    sklearn_metrics.mean_squared_error = mock_mse
    sklearn_metrics.mean_absolute_error = mock_mae
    
    sklearn_module.ensemble = sklearn_ensemble
    sklearn_module.preprocessing = sklearn_preprocessing
    sklearn_module.model_selection = sklearn_model_selection
    sklearn_module.metrics = sklearn_metrics
    
    sys.modules['sklearn'] = sklearn_module
    sys.modules['sklearn.ensemble'] = sklearn_ensemble
    sys.modules['sklearn.preprocessing'] = sklearn_preprocessing
    sys.modules['sklearn.model_selection'] = sklearn_model_selection
    sys.modules['sklearn.metrics'] = sklearn_metrics
    sys.modules['joblib'] = mock_joblib


@pytest.fixture(scope="session")
def ml_environment():
    """Fixture providing ML environment information"""
    return {
        'tensorflow_available': TENSORFLOW_AVAILABLE,
        'xgboost_available': XGBOOST_AVAILABLE, 
        'sklearn_available': SKLEARN_AVAILABLE,
        'testing_mode': 'ml_enabled'
    }


@pytest.fixture
def sample_price_data():
    """Generate sample price data for testing"""
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='1h')
    
    # Generate realistic price data with trend and volatility
    base_price = 100
    price_changes = np.random.normal(0, 1, 100).cumsum() * 0.5
    prices = base_price + price_changes
    
    return pd.DataFrame({
        'timestamp': dates,
        'open': prices + np.random.normal(0, 0.1, 100),
        'high': prices + np.abs(np.random.normal(0, 0.5, 100)),
        'low': prices - np.abs(np.random.normal(0, 0.5, 100)),
        'close': prices,
        'volume': np.random.randint(1000, 10000, 100)
    })


@pytest.fixture  
def sample_features():
    """Generate sample features for ML model testing"""
    np.random.seed(42)
    return pd.DataFrame({
        'sma_20': np.random.normal(100, 5, 50),
        'ema_12': np.random.normal(100, 3, 50),
        'rsi': np.random.uniform(20, 80, 50),
        'macd': np.random.normal(0, 1, 50),
        'bollinger_upper': np.random.normal(105, 2, 50),
        'bollinger_lower': np.random.normal(95, 2, 50),
        'volume_sma': np.random.normal(5000, 1000, 50),
        'price_change': np.random.normal(0, 0.5, 50)
    })


@pytest.fixture
def mock_mlops_manager():
    """Mock MLOps manager for testing"""
    mock_manager = Mock()
    mock_manager.log_model_training = Mock()
    mock_manager.log_prediction = Mock()
    mock_manager.get_model_metadata = Mock(return_value={'version': '1.0.0', 'accuracy': 0.85})
    mock_manager.store_model = Mock()
    mock_manager.load_model = Mock()
    return mock_manager


# Ensure asyncio event loop is properly configured
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Configuration for high-coverage testing
def pytest_configure(config):
    """Configure pytest for ML-enabled testing"""
    print("🧪 ML-Enabled Test Configuration Active")
    print(f"📊 TensorFlow: {'✅' if TENSORFLOW_AVAILABLE else '🔧 Mocked'}")
    print(f"📊 XGBoost: {'✅' if XGBOOST_AVAILABLE else '🔧 Mocked'}")  
    print(f"📊 Scikit-learn: {'✅' if SKLEARN_AVAILABLE else '🔧 Mocked'}")


def pytest_collection_modifyitems(config, items):
    """Mark tests appropriately based on ML library availability"""
    ml_marker = pytest.mark.skipif(
        not any([TENSORFLOW_AVAILABLE, XGBOOST_AVAILABLE, SKLEARN_AVAILABLE]),
        reason="ML libraries not available"
    )
    
    for item in items:
        if "ml_enabled" in item.name or "tensorflow" in item.name or "xgboost" in item.name:
            item.add_marker(ml_marker)
