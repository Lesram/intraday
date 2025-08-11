"""
Test Configuration and Fixtures
Provides fixtures for testing with isolated metrics registries and loggers.
"""
import asyncio
from contextlib import contextmanager
import io
import logging
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
import numpy as np
import pandas as pd
from prometheus_client import CollectorRegistry
import pytest

from backend.api.factory import create_app
from backend.infra.logging import get_logger


# Test data fixtures
@pytest.fixture
def sample_price_data():
    """Sample price data for testing"""
    dates = pd.date_range(start="2024-01-01", end="2024-01-31", freq="D")
    np.random.seed(42)

    # Generate realistic stock price data
    base_price = 100.0
    returns = np.random.normal(0.001, 0.02, len(dates))  # 0.1% daily return, 2% volatility
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

    return create_access_token(data={"sub": "admin@algotrading.com", "roles": ["admin"]})


@pytest.fixture
def trader_token():
    """Create trader token for testing."""
    from backend.infra.security import create_access_token

    return create_access_token(data={"sub": "trader@algotrading.com", "roles": ["trader"]})


@pytest.fixture
def readonly_token():
    """Create read-only token for testing."""
    from backend.infra.security import create_access_token

    return create_access_token(data={"sub": "viewer@algotrading.com", "roles": ["read-only"]})


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
    from backend.api.factory import create_app

    return create_app(registry=isolated_metrics_registry)


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
    from backend.api.factory import create_app

    app = create_app(registry=isolated_metrics_registry)

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
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
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

    # Create app with isolated registry
    app = create_app(registry=isolated_registry)

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
        patches.append(patch("backend.infra.logging.get_logger", return_value=test_logger))

    if test_metrics:
        patches.append(
            patch("backend.infra.metrics.get_metrics_registry", return_value=test_metrics)
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
