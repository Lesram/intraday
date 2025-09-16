"""
Phase 1.1: Standardized Mock Objects Framework
Addresses AttributeError issues (25.2% of test failures) by providing standardized mock interfaces.
"""

from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional


class StandardOrderMock(Mock):
    """Standardized mock for Order objects with complete interface"""
    
    def __init__(self, *args, **kwargs):
        # Initialize without spec to avoid recursion issues
        super().__init__()
        
        # Set default values directly
        self.symbol = kwargs.get('symbol', 'AAPL')
        self.quantity = kwargs.get('quantity', 100)
        self.side = kwargs.get('side', 'buy')
        self.order_type = kwargs.get('order_type', 'market')
        self.price = kwargs.get('price', 150.0)
        self.status = kwargs.get('status', 'pending')
        self.timestamp = kwargs.get('timestamp', datetime.now())
        self.filled_quantity = kwargs.get('filled_quantity', 0)
        self.remaining_quantity = kwargs.get('remaining_quantity', 100)
        self.fees = kwargs.get('fees', 0.0)
        self.order_id = kwargs.get('order_id', 'test_order_123')
        self.broker_order_id = kwargs.get('broker_order_id', 'broker_123')
        self.average_fill_price = kwargs.get('average_fill_price', 0.0)
        self.commission = kwargs.get('commission', 1.0)
        
        # Mock methods
        self.to_dict = Mock(return_value={
            'symbol': self.symbol,
            'quantity': self.quantity,
            'side': self.side,
            'order_type': self.order_type,
            'price': self.price,
            'status': self.status
        })
        
        self.validate = Mock(return_value=True)
        self.is_filled = Mock(return_value=(self.status == 'filled'))
        self.is_cancelled = Mock(return_value=(self.status == 'cancelled'))
        self.get_status = Mock(return_value=self.status)


class StandardEnsembleModelMock(Mock):
    """Standardized mock for EnsembleModel with complete interface"""
    
    def __init__(self, *args, **kwargs):
        # Initialize without spec to avoid recursion issues
        super().__init__()
        
        # Set default attributes directly
        self.models = kwargs.get('models', {
            'lstm': Mock(is_trained=False, predict=Mock(return_value=(0.7, 0.8))),
            'xgboost': Mock(is_trained=False, predict=Mock(return_value=(0.6, 0.75))),
            'random_forest': Mock(is_trained=False, predict=Mock(return_value=(0.65, 0.7)))
        })
        
        self.weights = kwargs.get('weights', {
            'lstm': 0.4,
            'xgboost': 0.4, 
            'random_forest': 0.2
        })
        
        self.performance_history = kwargs.get('performance_history', [])
        self.settings = kwargs.get('settings', Mock(mlops={'inference_telemetry_enabled': False}))
        self.model_manager = kwargs.get('model_manager', None)
        self.mlops_enabled = kwargs.get('mlops_enabled', False)
        self.random_seed = kwargs.get('random_seed', 42)
        
        # Mock methods with realistic return values
        self.train_models = Mock(return_value={'lstm': True, 'xgboost': True, 'random_forest': True})
        self.predict = Mock(return_value=(0.7, 0.85))
        self.update_weights = Mock(return_value=None)
        self.get_model_status = Mock(return_value={
            'lstm': {'is_trained': True, 'available': True, 'weight': 0.4},
            'xgboost': {'is_trained': True, 'available': True, 'weight': 0.4},
            'random_forest': {'is_trained': True, 'available': True, 'weight': 0.2}
        })
        self.save_models = Mock(return_value={'lstm': True, 'xgboost': True, 'random_forest': True})
        self.load_models = Mock(return_value={'lstm': True, 'xgboost': True, 'random_forest': True})


class StandardLSTMModelMock(Mock):
    """Standardized mock for LSTM model"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(spec_set=[
            'model', 'is_trained', 'sequence_length', 'features',
            'train', 'predict', 'save', 'load'
        ])
        
        self.model = None
        self.is_trained = kwargs.get('is_trained', False)
        self.sequence_length = kwargs.get('sequence_length', 60)
        self.features = kwargs.get('features', ['close', 'volume'])
        
        self.train.return_value = True
        self.predict.return_value = (0.7, 0.8)
        self.save.return_value = True
        self.load.return_value = True


class StandardXGBoostModelMock(Mock):
    """Standardized mock for XGBoost model"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(spec_set=[
            'model', 'is_trained', 'features', 'params',
            'train', 'predict', 'save', 'load'
        ])
        
        self.model = None
        self.is_trained = kwargs.get('is_trained', False)
        self.features = kwargs.get('features', ['close', 'volume', 'sma_20'])
        self.params = kwargs.get('params', {'max_depth': 6, 'learning_rate': 0.1})
        
        self.train.return_value = True
        self.predict.return_value = (0.6, 0.75)
        self.save.return_value = True
        self.load.return_value = True


class StandardRandomForestModelMock(Mock):
    """Standardized mock for Random Forest model"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(spec_set=[
            'model', 'is_trained', 'features', 'n_estimators',
            'train', 'predict', 'save', 'load'
        ])
        
        self.model = None
        self.is_trained = kwargs.get('is_trained', False)
        self.features = kwargs.get('features', ['close', 'volume', 'rsi'])
        self.n_estimators = kwargs.get('n_estimators', 100)
        
        self.train.return_value = True
        self.predict.return_value = (0.65, 0.7)
        self.save.return_value = True
        self.load.return_value = True


class StandardSettingsMock(Mock):
    """Standardized mock for Settings objects"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(spec_set=[
            'mlops', 'database_url', 'api_keys', 'logging_level',
            'model_save_path', 'data_source', 'risk_management'
        ])
        
        self.mlops = kwargs.get('mlops', {
            'inference_telemetry_enabled': False,
            'drift_detection_enabled': True,
            'model_registry_enabled': True
        })
        self.database_url = kwargs.get('database_url', 'sqlite:///:memory:')
        self.api_keys = kwargs.get('api_keys', {'alpaca': 'test_key'})
        self.logging_level = kwargs.get('logging_level', 'INFO')
        self.model_save_path = kwargs.get('model_save_path', './models')
        self.data_source = kwargs.get('data_source', 'mock')
        self.risk_management = kwargs.get('risk_management', {'max_position_size': 10000})


class StandardModelRegistryMock(Mock):
    """Standardized mock for ModelRegistry with get method"""
    
    def __init__(self, *args, **kwargs):
        # Initialize without spec to avoid recursion
        super().__init__()
        
        # Internal store for mock data - set directly to avoid issues
        self._store = {}
        
        # Create and assign methods manually to avoid Mock recursion
        def mock_register(name, version, model, **kwargs):
            class MockModelVersion:
                def __init__(self):
                    self.model_name = name
                    self.version = version
                    self.metadata = kwargs.get('metadata', {})
                    self.feature_schema = kwargs.get('feature_schema', {})
                    self.artifacts_path = kwargs.get('artifacts_path', None)
            
            mock_version = MockModelVersion()
            self._store[(name, version)] = (model, mock_version)
            return mock_version
        
        def mock_get(name, version):
            """Get method that returns (model, version_info) tuple"""
            key = (name, version)
            if key in self._store:
                return self._store[key]  # Returns (model, version_info)
            return None
        
        def mock_load(name, version=None):
            """Load method that returns just the model"""
            if version is None:
                # Find latest version
                matching_versions = [k for k in self._store.keys() if k[0] == name]
                if not matching_versions:
                    return None
                latest_key = max(matching_versions, key=lambda x: x[1])
                return self._store[latest_key][0]
            else:
                key = (name, version)
                if key in self._store:
                    return self._store[key][0]
            return None
        
        def mock_version_info(name, version):
            """Version info method"""
            key = (name, version)
            if key in self._store:
                return self._store[key][1]
            return None
        
        def mock_list_versions(name):
            """List versions for a model"""
            versions = []
            for key, (model, version_info) in self._store.items():
                if key[0] == name:
                    versions.append(version_info)
            return versions
        
        # Manually assign methods to avoid Mock attribute issues
        object.__setattr__(self, 'register', mock_register)
        object.__setattr__(self, 'get', mock_get) 
        object.__setattr__(self, 'load', mock_load)
        object.__setattr__(self, 'version_info', mock_version_info)
        object.__setattr__(self, 'list_versions', mock_list_versions)
        
        # Simple Mock objects for other methods
        self.get_champion_model = Mock(return_value=None)
        self.promote_to_champion = Mock(return_value=True)


class StandardAlpacaClientMock(Mock):
    """Standardized mock for Alpaca client"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(spec_set=[
            'get_account', 'get_positions', 'submit_order', 'cancel_order',
            'get_orders', 'get_bars', 'get_trades', 'close_position',
            'get_portfolio_history', 'list_assets'
        ])
        
        # Default return values
        self.get_account.return_value = {
            'equity': 100000.0,
            'cash': 50000.0,
            'buying_power': 200000.0,
            'status': 'ACTIVE'
        }
        
        self.get_positions.return_value = []
        self.submit_order.return_value = StandardOrderMock()
        self.cancel_order.return_value = True
        self.get_orders.return_value = []
        self.close_position.return_value = True


class StandardDataFrameMock:
    """Standardized mock for pandas DataFrame operations"""
    
    @staticmethod
    def create_price_data(length=100):
        """Create mock price data DataFrame"""
        dates = pd.date_range(start='2023-01-01', periods=length, freq='5min')
        base_price = 100.0
        
        # Generate realistic price movements
        returns = np.random.normal(0, 0.002, length)
        prices = [base_price]
        for ret in returns[1:]:
            prices.append(prices[-1] * (1 + ret))
        
        return pd.DataFrame({
            'timestamp': dates,
            'open': prices,
            'high': [p * (1 + abs(np.random.normal(0, 0.001))) for p in prices],
            'low': [p * (1 - abs(np.random.normal(0, 0.001))) for p in prices],
            'close': prices,
            'volume': np.random.randint(1000, 10000, length)
        })
    
    @staticmethod
    def create_features_data(length=100):
        """Create mock features DataFrame"""
        return pd.DataFrame({
            'close': np.random.randn(length) * 10 + 100,
            'volume': np.random.randint(1000, 10000, length),
            'sma_20': np.random.randn(length) * 5 + 100,
            'rsi': np.random.uniform(20, 80, length),
            'macd': np.random.randn(length) * 2
        })


# Convenience factory functions
def create_standard_ensemble_mock(**kwargs):
    """Factory function for creating standardized ensemble model mocks"""
    return StandardEnsembleModelMock(**kwargs)


def create_standard_registry_mock(**kwargs):
    """Factory function for creating standardized model registry mocks"""
    return StandardModelRegistryMock(**kwargs)


def create_standard_order_mock(**kwargs):
    """Factory function for creating standardized order mocks"""
    return StandardOrderMock(**kwargs)


def create_standard_alpaca_mock(**kwargs):
    """Factory function for creating standardized Alpaca client mocks"""
    return StandardAlpacaClientMock(**kwargs)


# Test data generators
def generate_sample_data():
    """Generate sample test data for common use cases"""
    return {
        'price_data': StandardDataFrameMock.create_price_data(),
        'features_data': StandardDataFrameMock.create_features_data(),
        'sample_features': {
            'close': 150.0,
            'volume': 5000,
            'sma_20': 148.5,
            'rsi': 65.0,
            'macd': 2.1
        }
    }
