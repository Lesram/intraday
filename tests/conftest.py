"""
Test Configuration and Fixtures
Provides fixtures for testing with isolated metrics registries and loggers.
Enhanced with deterministic behavior and global seeding.
"""

# CRITICAL: Import light mode setup FIRST before anything else
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
try:
    import conftest_light_mode
except ImportError:
    print("⚠️  Light mode setup not found - heavy ML libraries may load")

# Now proceed with rest of conftest setup

# Disable problematic imports that cause test conflicts
import warnings
import os

# Set environment variable to disable problematic ML libraries
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['DISABLE_TRANSFORMERS'] = '1'
os.environ['DISABLE_TORCH'] = '1'  
os.environ['DISABLE_TENSORFLOW'] = '1'
os.environ['DISABLE_XGBOOST'] = '1'
os.environ['PYTEST_RUNNING'] = '1'

# Comprehensive warning suppression
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")
warnings.filterwarnings("ignore", category=UserWarning, module="tensorflow") 
warnings.filterwarnings("ignore", category=UserWarning, module="torch")
warnings.filterwarnings("ignore", category=UserWarning, module="xgboost")

# Mock problematic modules early to prevent import issues
import sys
from unittest.mock import MagicMock

# Mock ALL heavy ML libraries to prevent import hangs on Windows
heavy_ml_modules = [
    'transformers', 'transformers.utils', 'transformers.utils.import_utils',
    'torch', 'torch.nn', 'torch.optim', 'torch.utils', 'torch.utils.data',
    'tensorflow', 'tensorflow.keras', 'tensorflow.keras.models', 'tensorflow.keras.layers',
    'xgboost', 'sklearn.ensemble'
]

for module_name in heavy_ml_modules:
    if module_name not in sys.modules:
        sys.modules[module_name] = MagicMock()

import asyncio
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
import io
import json
import logging
import os
from pathlib import Path
import random
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
# IMPORTANT: Import and apply RobustTestClient fix for CancelledError issues
try:
    from tests.helpers.robust_testclient import patch_testclient_globally
    patch_testclient_globally()
    print("✅ Applied RobustTestClient fix globally - TestClient CancelledError resolved")
except ImportError:
    print("⚠️  RobustTestClient not available - TestClient may have CancelledError issues")
# from freezegun import freeze_time  # Removed to avoid ML conflicts
import numpy as np
import pandas as pd
from prometheus_client import CollectorRegistry
import pytest

from backend.api.factory import create_app
from backend.config import Settings
from backend.infra.logging import get_logger
from backend.risk.types import Side

# from backend.features.types import FeatureFrame  # Commented out to avoid import issues
from backend.strategies.types import ExecutionPlan, TradingSignal

# Global test seed for deterministic behavior
TEST_SEED = int(os.environ.get("TEST_SEED", 42))
DEFAULT_TEST_TIMESTAMP = "2025-01-15 09:30:00"

# Set global seeds for deterministic tests
random.seed(TEST_SEED)
np.random.seed(TEST_SEED)


@pytest.fixture(autouse=True)
def deterministic_setup(request):
    """Ensure deterministic test behavior with global seeding and simple time mock."""
    # Reset seeds before each test for isolation
    random.seed(TEST_SEED)
    np.random.seed(TEST_SEED)

    # Simple time mocking without freezegun to avoid ML library conflicts
    from unittest.mock import patch
    import datetime
    
    # Check if this is a performance test - skip time mocking for perf tests
    is_performance_test = (
        "performance" in request.keywords
        or "perf" in request.keywords
        or "test_micro_predict" in request.node.name
        or "TestMicroPredictPerformance" in str(request.node)
    )

    if not is_performance_test:
        # Skip datetime mocking for now - causing issues with async libraries
        yield
    else:
        # Skip time mocking for performance tests
        yield


@pytest.fixture
def test_seed():
    """Provide the test seed for tests that need explicit seeding."""
    return TEST_SEED


@pytest.fixture
def custom_time():
    """Allow tests to override the frozen time."""

    def _freeze_time(timestamp):
        # Simple time mock without freezegun
        from unittest.mock import patch
        import datetime
        
        if isinstance(timestamp, str):
            fixed_time = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        else:
            fixed_time = timestamp
            
        return patch('datetime.datetime', wraps=datetime.datetime, now=lambda: fixed_time, utcnow=lambda: fixed_time)

    return _freeze_time


# Import fixture data generators
from tests.fixtures.broker_responses import get_broker_response
from tests.fixtures.market_data import (
    SAMPLE_TRADES,
    generate_synthetic_ohlcv,
)


@pytest.fixture
def sample_price_data():
    """Sample price data for testing"""
    dates = pd.date_range(start="2024-01-01", end="2024-01-31", freq="D")
    np.random.seed(42)

    # Generate realistic stock price data
    base_price = 100.0
    returns = np.random.normal(
        0.001, 0.02, len(dates)
    )  # 0.1% daily return, 2% volatility
    prices = [base_price]

    for ret in returns[1:]:
        prices.append(prices[-1] * (1 + ret))

    data = pd.DataFrame(
        {
            "timestamp": dates,
            "open": [p * np.random.uniform(0.99, 1.01) for p in prices],
            "high": [p * np.random.uniform(1.005, 1.02) for p in prices],
            "low": [p * np.random.uniform(0.98, 0.995) for p in prices],
            "close": prices,
            "volume": np.random.randint(100000, 1000000, len(dates)),
        }
    )

    return data.set_index("timestamp")


# ===== ENHANCED FIXTURES FOR COMPREHENSIVE TESTING =====


@pytest.fixture
def test_config():
    """Test configuration with safe defaults."""
    return Settings(
        environment="test",
        database_url="sqlite:///test.db",
        alpaca_api_key="test_key",
        alpaca_secret="test_secret",
        alpaca_base_url="https://paper-api.alpaca.markets",
        jwt_secret_key="test_jwt_secret_key_for_testing_only",
        redis_url="redis://localhost:6379/0",
        log_level="DEBUG",
        trading_mode="DRY_RUN",
        enable_paper_trading=True,
    )


@pytest.fixture
def mock_database():
    """Mock database session for testing."""
    db_mock = Mock()
    db_mock.execute = AsyncMock()
    db_mock.fetch_all = AsyncMock(return_value=[])
    db_mock.fetch_one = AsyncMock(return_value=None)
    db_mock.commit = AsyncMock()
    db_mock.rollback = AsyncMock()
    db_mock.close = AsyncMock()
    return db_mock


@pytest.fixture
def mock_alpaca_client():
    """Mock Alpaca API client."""
    client = Mock()
    client.submit_order = AsyncMock(
        return_value=get_broker_response("filled_buy_order")
    )
    client.cancel_order = AsyncMock(return_value=get_broker_response("canceled_order"))
    client.get_account = AsyncMock(return_value=get_broker_response("account_response"))
    client.get_positions = AsyncMock(
        return_value=[get_broker_response("position_response")]
    )
    client.get_orders = AsyncMock(return_value=[])
    client.stream_trades = AsyncMock()
    client.stream_quotes = AsyncMock()
    return client


@pytest.fixture
def sample_market_data():
    """Generate comprehensive market data for testing."""
    return {
        "ohlcv": generate_synthetic_ohlcv("AAPL", days=30),
        "trades": pd.DataFrame(SAMPLE_TRADES),
        "quotes": pd.DataFrame(
            [
                {
                    "timestamp": "2024-01-02T09:30:00.123456Z",
                    "symbol": "AAPL",
                    "bid_price": 185.48,
                    "bid_size": 100,
                    "ask_price": 185.52,
                    "ask_size": 200,
                }
            ]
        ),
    }


# @pytest.fixture
# def sample_features():
#     """Sample feature vectors for ML testing - temporarily disabled."""
#     pass


@pytest.fixture
def sample_signals():
    """Sample trading signals for strategy testing."""
    return [
        TradingSignal(
            symbol="AAPL",
            source="momentum_strategy",
            ts=datetime.now(),
            target_exposure=0.8,  # 80% long position
            confidence=0.8,
            metadata={"target_price": 186.0, "stop_loss": 183.0},
        ),
        TradingSignal(
            symbol="GOOGL",
            source="mean_reversion_strategy",
            ts=datetime.now(),
            target_exposure=-0.7,  # 70% short position
            confidence=0.7,
            metadata={"target_price": 2780.0, "stop_loss": 2820.0},
        ),
    ]


@pytest.fixture
def sample_execution_plans():
    """Sample execution plans for order testing."""
    return [
        ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            notional=Decimal("18500"),
            order_type="market",
            time_in_force="day",
            strategy_id="momentum_001",
        ),
        ExecutionPlan(
            symbol="GOOGL",
            side=Side.SELL,
            qty=Decimal("10"),
            notional=Decimal("28000"),
            order_type="limit",
            limit_price=Decimal("2780.00"),
            time_in_force="day",
            strategy_id="mean_reversion_001",
        ),
    ]


@pytest.fixture
def mock_risk_manager():
    """Mock risk manager for testing."""
    risk_manager = Mock()
    risk_manager.check_trade_risk = Mock(
        return_value={
            "approved": True,
            "risk_score": 0.3,
            "position_limit_used": 0.15,
            "message": "Trade approved",
        }
    )
    risk_manager.before_order = AsyncMock(
        return_value={
            "approved": True,
            "risk_score": 0.3,
        }
    )
    risk_manager.get_portfolio_metrics = Mock(
        return_value={
            "total_value": 100000.0,
            "cash": 50000.0,
            "positions_value": 50000.0,
            "daily_pnl": 1250.0,
            "unrealized_pnl": 2500.0,
        }
    )
    return risk_manager


@pytest.fixture
def mock_ml_model():
    """Mock ML model for prediction testing."""
    model = Mock()
    model.predict = Mock(return_value=np.array([0.75, 0.85, 0.65]))  # Confidence scores
    model.predict_proba = Mock(
        return_value=np.array([[0.2, 0.8], [0.15, 0.85], [0.35, 0.65]])
    )
    model.feature_importance_ = np.array([0.3, 0.25, 0.2, 0.15, 0.1])
    model.is_trained = True
    model.version = "1.0.0"
    return model


@pytest.fixture
def mock_strategy_engine():
    """Mock strategy engine for testing."""
    engine = Mock()
    engine.generate_signals = AsyncMock(return_value=[])
    engine.execute_plan = AsyncMock(
        return_value={
            "success": True,
            "order_id": "test_order_123",
            "filled_qty": 100,
            "avg_fill_price": 185.50,
        }
    )
    engine.get_active_positions = Mock(return_value=[])
    engine.min_notional = Decimal("1000")
    return engine


@pytest.fixture
def mock_websocket_manager():
    """Mock WebSocket manager for real-time testing."""
    manager = Mock()
    manager.add_client = AsyncMock()
    manager.remove_client = AsyncMock()
    manager.broadcast = AsyncMock()
    manager.send_to_client = AsyncMock()
    manager.get_client_count = Mock(return_value=0)
    manager.clients = {}
    return manager


@pytest.fixture
async def mock_websocket():
    """Mock WebSocket connection for testing."""
    websocket = Mock()
    websocket.accept = AsyncMock()
    websocket.close = AsyncMock()
    websocket.send_text = AsyncMock()
    websocket.send_json = AsyncMock()
    websocket.receive_text = AsyncMock()
    websocket.receive_json = AsyncMock()
    return websocket


@pytest.fixture
def sample_backtest_config():
    """Sample backtesting configuration."""
    return {
        "start_date": "2024-01-01",
        "end_date": "2024-03-31",
        "initial_capital": 100000.0,
        "symbols": ["AAPL", "GOOGL", "MSFT"],
        "strategies": ["momentum", "mean_reversion"],
        "benchmark": "SPY",
        "commission": 0.001,  # 0.1% per trade
        "slippage": 0.0005,  # 0.05% slippage
        "max_position_size": 0.1,  # 10% max position
    }


@pytest.fixture
def sample_portfolio_state():
    """Sample portfolio state for testing."""
    return {
        "cash": 50000.0,
        "total_value": 100000.0,
        "positions": {
            "AAPL": {
                "qty": 100,
                "avg_price": 185.0,
                "market_value": 18650.0,
                "unrealized_pnl": 150.0,
            },
            "GOOGL": {
                "qty": 10,
                "avg_price": 2800.0,
                "market_value": 28050.0,
                "unrealized_pnl": 50.0,
            },
        },
        "daily_pnl": 1250.0,
        "total_pnl": 2500.0,
        "max_drawdown": -0.05,
        "sharpe_ratio": 1.8,
    }


@pytest.fixture
def mock_feature_engineer():
    """Mock feature engineering pipeline."""
    engineer = Mock()
    engineer.compute_features = Mock(
        return_value=pd.DataFrame(
            {
                "rsi_14": [45.2, 55.8, 62.1],
                "macd": [0.5, -0.2, 1.1],
                "bb_upper": [187.5, 188.2, 189.0],
                "bb_lower": [182.5, 183.1, 184.0],
                "volume_sma": [1200000, 1150000, 1300000],
            }
        )
    )
    engineer.validate_features = Mock(return_value=True)
    engineer.get_feature_names = Mock(
        return_value=["rsi_14", "macd", "bb_upper", "bb_lower", "volume_sma"]
    )
    return engineer


@pytest.fixture
def mock_news_data():
    """Mock news/sentiment data for testing."""
    return [
        {
            "timestamp": "2024-01-02T08:00:00Z",
            "headline": "Apple Reports Strong Q4 Earnings Beat Expectations",
            "sentiment_score": 0.75,
            "relevance": 0.95,
            "symbols": ["AAPL"],
            "source": "Reuters",
        },
        {
            "timestamp": "2024-01-02T10:30:00Z",
            "headline": "Google Cloud Wins Major Enterprise Contract",
            "sentiment_score": 0.85,
            "relevance": 0.90,
            "symbols": ["GOOGL"],
            "source": "Bloomberg",
        },
    ]


@pytest.fixture
def fixture_data_loader():
    """Helper to load test fixture data from files."""

    def _load_fixture(filename: str) -> dict[str, Any]:
        fixture_path = Path(__file__).parent / "fixtures" / filename
        with open(fixture_path) as f:
            return json.load(f)

    return _load_fixture


# ===== PERFORMANCE TESTING FIXTURES =====


@pytest.fixture
def performance_test_data():
    """Large dataset for performance testing."""
    symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA", "AMZN", "META", "NFLX"]
    data = {}

    for symbol in symbols:
        data[symbol] = generate_synthetic_ohlcv(
            symbol=symbol,
            days=252,  # 1 year of data
            freq="1min",
            volatility=0.02,
        )

    return data


@pytest.fixture
def benchmark_thresholds():
    """Performance benchmarks and thresholds."""
    return {
        "feature_calculation_ms": 100,  # Max 100ms per batch
        "model_inference_ms": 50,  # Max 50ms per prediction
        "risk_evaluation_ms": 20,  # Max 20ms per risk check
        "order_submission_ms": 200,  # Max 200ms order latency
        "websocket_message_ms": 10,  # Max 10ms message processing
        "backtest_throughput_per_sec": 1000,  # Min 1000 samples/sec
        "memory_usage_mb": 512,  # Max 512MB memory usage
    }


# ===== CHAOS/FUZZ TESTING FIXTURES =====


@pytest.fixture
def corrupted_market_data():
    """Corrupted market data for chaos testing."""
    return [
        # Missing required fields
        {"timestamp": "2024-01-02T09:30:00Z", "symbol": "AAPL"},  # No price data
        # Invalid data types
        {"timestamp": "invalid_date", "symbol": "AAPL", "close": "not_a_number"},
        # Out-of-order timestamps
        {"timestamp": "2024-01-02T09:35:00Z", "symbol": "AAPL", "close": 185.0},
        {
            "timestamp": "2024-01-02T09:30:00Z",
            "symbol": "AAPL",
            "close": 184.0,
        },  # Earlier
        # Extreme values
        {"timestamp": "2024-01-02T09:30:00Z", "symbol": "AAPL", "close": -999999},
        {"timestamp": "2024-01-02T09:30:00Z", "symbol": "AAPL", "close": float("inf")},
        # Clock jumps
        {"timestamp": "2024-01-02T09:30:00Z", "symbol": "AAPL", "close": 185.0},
        {
            "timestamp": "2025-12-31T23:59:59Z",
            "symbol": "AAPL",
            "close": 186.0,
        },  # Future
    ]


@pytest.fixture
def network_failure_scenarios():
    """Network failure scenarios for resilience testing."""
    return {
        "connection_timeout": {"error": "timeout", "retry_after": 30},
        "rate_limit": {"error": "rate_limit", "retry_after": 60},
        "service_unavailable": {"error": "service_unavailable", "retry_after": 300},
        "authentication_failure": {"error": "auth_failed", "retry_after": None},
        "invalid_response": {"error": "malformed_json", "response": "{invalid json}"},
    }


@pytest.fixture
def sample_features():
    """Sample feature data for testing"""
    np.random.seed(42)
    dates = pd.date_range(start="2024-01-01", end="2024-01-31", freq="D")

    return pd.DataFrame(
        {
            "sma_20": np.random.uniform(95, 105, len(dates)),
            "sma_50": np.random.uniform(95, 105, len(dates)),
            "ema_12": np.random.uniform(95, 105, len(dates)),
            "ema_26": np.random.uniform(95, 105, len(dates)),
            "rsi": np.random.uniform(30, 70, len(dates)),
            "macd": np.random.uniform(-2, 2, len(dates)),
            "macd_signal": np.random.uniform(-2, 2, len(dates)),
            "bb_upper": np.random.uniform(102, 108, len(dates)),
            "bb_lower": np.random.uniform(92, 98, len(dates)),
            "atr": np.random.uniform(1, 3, len(dates)),
            "volume_sma": np.random.uniform(200000, 800000, len(dates)),
        },
        index=dates,
    )


@pytest.fixture
def mock_alpaca_client():
    """Mock Alpaca client for testing"""
    client = AsyncMock()
    client.get_historical_data.return_value = pd.DataFrame(
        {
            "open": [100, 101, 102],
            "high": [101, 102, 103],
            "low": [99, 100, 101],
            "close": [100.5, 101.5, 102.5],
            "volume": [100000, 120000, 90000],
        }
    )
    client.submit_order.return_value = {"id": "test_order_123", "status": "accepted"}
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
        "environment": "test",
        "max_position_size": 1000,
        "max_portfolio_risk": 0.02,
        "var_confidence_level": 0.95,
        "lookback_period": 252,
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
    from unittest.mock import Mock

    from fastapi.testclient import TestClient

    from backend.api.main import app
    from backend.infra.users import UserRepository

    # Mock all the app state dependencies that endpoints need
    mock_risk_manager = Mock()
    mock_risk_manager.get_risk_metrics.return_value = {
        "status": "healthy",
        "risk_level": "low",
    }
    mock_risk_manager.get_portfolio_risk.return_value = {"var": 0.05, "sharpe": 1.2}

    mock_model_manager = Mock()
    mock_model_manager.get_model_status.return_value = {
        "status": "ready",
        "accuracy": 0.85,
    }
    mock_model_manager.get_predictions.return_value = {
        "symbol": "AAPL",
        "prediction": "buy",
    }

    mock_strategy_manager = Mock()
    mock_strategy_manager.get_signals.return_value = {
        "signal": "buy",
        "confidence": 0.8,
    }
    mock_strategy_manager.get_strategy_status.return_value = {
        "active": True,
        "pnl": 1250.0,
    }

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


# =============================================================================
# METRICS AND APP FACTORY FIXTURES
# =============================================================================


@pytest.fixture
def isolated_metrics_registry():
    """Create an isolated Prometheus CollectorRegistry for test isolation"""
    from prometheus_client import CollectorRegistry

    return CollectorRegistry()


@pytest.fixture
def test_app(isolated_metrics_registry):
    """Create a test FastAPI app with isolated metrics registry"""
    # Import the main app which has all routes registered
    from backend.api.main import app
    
    # Override the metrics registry for testing
    app.state.metrics_registry = isolated_metrics_registry
    
    # Re-initialize metrics with isolated registry
    from backend.infra.metrics import initialize_metrics_registry
    app.state.metrics = initialize_metrics_registry(
        namespace="intraday", registry=isolated_metrics_registry
    )

    return app


@pytest.fixture
def main_app():
    """Provide the main FastAPI app with all routes registered"""
    from backend.api.main import app
    return app


@pytest.fixture
def client(test_app):
    """Create a test client for synchronous endpoint testing"""
    from fastapi.testclient import TestClient

    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
async def async_client(test_app):
    """Create an async test client for asynchronous endpoint testing"""
    from httpx import AsyncClient

    async with AsyncClient(app=test_app, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def mock_dependencies(test_app):
    """Mock all external dependencies for isolated testing"""
    from unittest.mock import AsyncMock, Mock

    from prometheus_client import CollectorRegistry

    from backend.infra.metrics import MetricsRegistry

    # Mock database components
    mock_db_session = AsyncMock()
    mock_outbox_service = AsyncMock()

    # Mock trading components
    mock_alpaca_client = Mock()
    mock_risk_manager = AsyncMock()
    mock_strategy_engine = Mock()
    mock_model_manager = Mock()

    # Mock WebSocket manager with isolated metrics
    mock_ws_manager = Mock()
    mock_ws_manager.metrics_registry = MetricsRegistry(
        namespace="test", registry=CollectorRegistry()
    )

    # Apply mocks to app state
    test_app.state.db_session = mock_db_session
    test_app.state.outbox_service = mock_outbox_service
    test_app.state.alpaca_client = mock_alpaca_client
    test_app.state.risk_manager = mock_risk_manager
    test_app.state.strategy_engine = mock_strategy_engine
    test_app.state.model_manager = mock_model_manager
    test_app.state.ws_manager = mock_ws_manager

    return {
        "db_session": mock_db_session,
        "outbox_service": mock_outbox_service,
        "alpaca_client": mock_alpaca_client,
        "risk_manager": mock_risk_manager,
        "strategy_engine": mock_strategy_engine,
        "model_manager": mock_model_manager,
        "ws_manager": mock_ws_manager,
    }


@pytest.fixture
def app_with_metrics(isolated_metrics_registry):
    """Create app specifically for metrics testing with isolated registry"""
    # Import the main app which has all routes registered
    from backend.api.main import app
    
    # Override the metrics registry for testing
    app.state.metrics_registry = isolated_metrics_registry
    
    # Re-initialize metrics with isolated registry
    from backend.infra.metrics import initialize_metrics_registry
    app.state.metrics = initialize_metrics_registry(
        namespace="intraday", registry=isolated_metrics_registry
    )

    # Verify metrics isolation
    assert hasattr(app.state, "metrics")
    assert app.state.metrics.registry is isolated_metrics_registry

    return app


@pytest.fixture
def metrics_test_client(app_with_metrics):
    """Create test client specifically for metrics testing"""
    from fastapi.testclient import TestClient

    with TestClient(app_with_metrics) as client:
        yield client


class MetricsTestHelper:
    """Helper class for metrics testing"""

    @staticmethod
    def get_metric_value(registry, metric_name: str, labels: dict = None):
        """Extract metric value from registry for testing"""
        for collector in registry._collector_to_names.keys():
            if hasattr(collector, "_name") and collector._name == metric_name:
                if labels:
                    return collector.labels(**labels)._value._value
                else:
                    return collector._value._value
        return None

    @staticmethod
    def get_counter_value(registry, metric_name: str, labels: dict = None):
        """Get counter metric value"""
        return MetricsTestHelper.get_metric_value(registry, metric_name, labels)


@pytest.fixture
def metrics_helper():
    """Provide metrics testing helper"""
    return MetricsTestHelper


# ============================================================================
# Middleware Isolation Fixtures
# ============================================================================


@pytest.fixture
def isolated_registry():
    """Create an isolated Prometheus registry for testing."""
    return CollectorRegistry()


@pytest.fixture
def test_logger_handler():
    """Create a test logger handler that writes to StringIO."""
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)

    # Return both handler and stream for test access
    return handler, log_stream


@pytest.fixture
def app_with_metrics(isolated_registry, test_logger_handler):
    """
    Create a FastAPI app with isolated metrics registry and logger.

    This fixture ensures complete test isolation by:
    - Using a separate Prometheus registry per test
    - Providing a test-specific logger handler
    - Patching global logger to use test handler
    """
    handler, log_stream = test_logger_handler

    # Import the main app which has all routes registered
    from backend.api.main import app
    
    # Override the metrics registry for testing
    app.state.metrics_registry = isolated_registry
    
    # Re-initialize metrics with isolated registry  
    from backend.infra.metrics import initialize_metrics_registry
    app.state.metrics = initialize_metrics_registry(
        namespace="intraday", registry=isolated_registry
    )

    # Patch the global logger getter to use our test handler
    original_get_logger = get_logger

    def mock_get_logger(name=None):
        """Mock logger that uses our test handler."""
        logger = original_get_logger(name)

        # Create a test logger that captures output
        test_logger = logging.getLogger(f"test_{name or 'root'}")
        test_logger.handlers.clear()
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)
        test_logger.propagate = False

        # Add the log_http_request method for middleware compatibility
        def log_http_request(method, path, status_code, duration_ms, request_id):
            test_logger.info(
                f"HTTP {method} {path} - Status: {status_code}, "
                f"Duration: {duration_ms:.2f}ms, Request ID: {request_id}"
            )

        test_logger.log_http_request = log_http_request
        return test_logger

    with patch("backend.infra.logging.get_logger", mock_get_logger):
        yield app, log_stream

    # Cleanup
    handler.close()


@pytest.fixture
def client_with_metrics(app_with_metrics):
    """Create a TestClient with isolated metrics and logging."""
    app, log_stream = app_with_metrics
    client = TestClient(app)

    # Attach the log stream to the client for test assertions
    client.log_stream = log_stream

    return client


@pytest.fixture
def mock_structured_logger():
    """Create a mock structured logger for testing."""
    logger = Mock()
    logger.log_http_request = Mock()
    logger.info = Mock()
    logger.error = Mock()
    logger.warning = Mock()
    logger.debug = Mock()
    return logger


@contextmanager
def patch_middleware_globals(test_logger=None, test_metrics=None):
    """
    Context manager to patch global dependencies in middleware.
    Useful for granular testing of middleware components.
    """
    patches = []

    if test_logger:
        patches.append(
            patch("backend.infra.logging.get_logger", return_value=test_logger)
        )

    if test_metrics:
        patches.append(
            patch(
                "backend.infra.metrics.get_metrics_registry", return_value=test_metrics
            )
        )

    # Start all patches
    for p in patches:
        p.start()

    try:
        yield
    finally:
        # Stop all patches
        for p in patches:
            p.stop()


class TestMetricsRegistry:
    """Mock metrics registry for testing."""

    def __init__(self):
        self.counters = {}
        self.histograms = {}
        self.gauges = {}

    def counter(self, name, labels=None):
        """Create or get a mock counter."""
        key = (name, str(labels or {}))
        if key not in self.counters:
            counter_mock = Mock()
            counter_mock.inc = Mock()
            self.counters[key] = counter_mock
        return self.counters[key]

    def histogram(self, name, labels=None):
        """Create or get a mock histogram."""
        key = (name, str(labels or {}))
        if key not in self.histograms:
            histogram_mock = Mock()
            histogram_mock.observe = Mock()
            self.histograms[key] = histogram_mock
        return self.histograms[key]

    def gauge(self, name, labels=None):
        """Create or get a mock gauge."""
        key = (name, str(labels or {}))
        if key not in self.gauges:
            gauge_mock = Mock()
            gauge_mock.set = Mock()
            self.gauges[key] = gauge_mock
        return self.gauges[key]

    def inc_counter(self, name, labels=None):
        """Increment a counter."""
        return self.counter(name, labels).inc()

    def observe_histogram(self, name, value, labels=None):
        """Record histogram observation."""
        return self.histogram(name, labels).observe(value)


@pytest.fixture
def test_metrics_registry():
    """Create a test metrics registry for assertions."""
    return TestMetricsRegistry()


# Sample fixtures for middleware testing
@pytest.fixture
def sample_http_request():
    """Sample HTTP request data for testing."""
    return {
        "method": "GET",
        "path": "/api/v1/test",
        "headers": {"User-Agent": "test-client"},
        "query_params": {},
    }


@pytest.fixture
def sample_http_response():
    """Sample HTTP response data for testing."""
    return {
        "status_code": 200,
        "headers": {"Content-Type": "application/json"},
        "body": '{"status": "success"}',
    }


pytest_plugins = [
    "tests.plugins.leak_guard",
    "tests.plugins.leak_guard_session",
    "tests.plugins.light_mode",
    "tests.plugins.respx_compat",
]
