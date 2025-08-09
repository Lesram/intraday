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
