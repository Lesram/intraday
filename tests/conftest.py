"""
Test Configuration and Fixtures
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Test data fixtures
@pytest.fixture
def sample_price_data():
    """Sample price data for testing"""
    dates = pd.date_range(start='2024-01-01', end='2024-01-31', freq='D')
    np.random.seed(42)
    
    # Generate realistic stock price data
    base_price = 100.0
    returns = np.random.normal(0.001, 0.02, len(dates))  # 0.1% daily return, 2% volatility
    prices = [base_price]
    
    for ret in returns[1:]:
        prices.append(prices[-1] * (1 + ret))
    
    data = pd.DataFrame({
        'timestamp': dates,
        'open': [p * np.random.uniform(0.99, 1.01) for p in prices],
        'high': [p * np.random.uniform(1.005, 1.02) for p in prices],
        'low': [p * np.random.uniform(0.98, 0.995) for p in prices],
        'close': prices,
        'volume': np.random.randint(100000, 1000000, len(dates))
    })
    
    return data.set_index('timestamp')

@pytest.fixture
def sample_features():
    """Sample feature data for testing"""
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', end='2024-01-31', freq='D')
    
    return pd.DataFrame({
        'sma_20': np.random.uniform(95, 105, len(dates)),
        'sma_50': np.random.uniform(95, 105, len(dates)),
        'ema_12': np.random.uniform(95, 105, len(dates)),
        'ema_26': np.random.uniform(95, 105, len(dates)),
        'rsi': np.random.uniform(30, 70, len(dates)),
        'macd': np.random.uniform(-2, 2, len(dates)),
        'macd_signal': np.random.uniform(-2, 2, len(dates)),
        'bb_upper': np.random.uniform(102, 108, len(dates)),
        'bb_lower': np.random.uniform(92, 98, len(dates)),
        'atr': np.random.uniform(1, 3, len(dates)),
        'volume_sma': np.random.uniform(200000, 800000, len(dates))
    }, index=dates)

@pytest.fixture
def mock_alpaca_client():
    """Mock Alpaca client for testing"""
    client = AsyncMock()
    client.get_historical_data.return_value = pd.DataFrame({
        'open': [100, 101, 102],
        'high': [101, 102, 103],
        'low': [99, 100, 101],
        'close': [100.5, 101.5, 102.5],
        'volume': [100000, 120000, 90000]
    })
    client.submit_order.return_value = {'id': 'test_order_123', 'status': 'accepted'}
    client.is_connected.return_value = True
    return client

@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing"""
    client = AsyncMock()
    client.get.return_value = None
    client.set.return_value = True
    client.ping.return_value = True
    return client

@pytest.fixture
def test_config():
    """Test configuration"""
    return {
        'environment': 'test',
        'max_position_size': 1000,
        'max_portfolio_risk': 0.02,
        'var_confidence_level': 0.95,
        'lookback_period': 252
    }

# Event loop fixture for async tests
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def async_setup():
    """Async setup for tests that need it"""
    # Any async setup code here
    yield
    # Any async cleanup code here

# FastAPI Testing Fixtures
@pytest.fixture
def client():
    """Create test client with mocked dependencies."""
    from fastapi.testclient import TestClient
    from unittest.mock import Mock
    from backend.api.main import app
    from backend.infra.users import UserRepository
    
    # Mock all the app state dependencies that endpoints need
    mock_risk_manager = Mock()
    mock_risk_manager.get_risk_metrics.return_value = {"status": "healthy", "risk_level": "low"}
    mock_risk_manager.get_portfolio_risk.return_value = {"var": 0.05, "sharpe": 1.2}
    
    mock_model_manager = Mock()
    mock_model_manager.get_model_status.return_value = {"status": "ready", "accuracy": 0.85}
    mock_model_manager.get_predictions.return_value = {"symbol": "AAPL", "prediction": "buy"}
    
    mock_strategy_manager = Mock()
    mock_strategy_manager.get_signals.return_value = {"signal": "buy", "confidence": 0.8}
    mock_strategy_manager.get_strategy_status.return_value = {"active": True, "pnl": 1250.0}
    
    mock_data_client = Mock()
    mock_data_client.get_market_data.return_value = {"price": 150.0, "volume": 1000000}
    
    # Set up app state with all required dependencies
    app.state.risk_manager = mock_risk_manager
    app.state.model_manager = mock_model_manager
    app.state.strategy_manager = mock_strategy_manager
    app.state.data_client = mock_data_client
    app.state.user_repository = UserRepository()
    app.state.is_initialized = True
    
    return TestClient(app)

@pytest.fixture
def mock_app_state():
    """Mock application state for testing."""
    from unittest.mock import Mock
    from backend.infra.users import UserRepository
    
    # Mock the app state to avoid dependencies
    mock_state = Mock()
    mock_state.is_initialized = True
    mock_state.user_repository = UserRepository()
    return mock_state

@pytest.fixture
def admin_token():
    """Create admin token for testing."""
    from backend.infra.security import create_access_token
    return create_access_token(
        data={"sub": "admin@algotrading.com", "roles": ["admin"]}
    )

@pytest.fixture
def trader_token():
    """Create trader token for testing."""
    from backend.infra.security import create_access_token
    return create_access_token(
        data={"sub": "trader@algotrading.com", "roles": ["trader"]}
    )

@pytest.fixture
def readonly_token():
    """Create read-only token for testing."""
    from backend.infra.security import create_access_token
    return create_access_token(
        data={"sub": "viewer@algotrading.com", "roles": ["read-only"]}
    )
