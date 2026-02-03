"""
Shared fixtures and configuration for real integration tests.

This module provides:
- Real database connections (test PostgreSQL or SQLite)
- Real HTTP client for API testing
- Real broker client (paper trading mode)
- Test data factories that create valid trading data
- Cleanup utilities
"""

import asyncio
import os
import uuid
from datetime import datetime, UTC, timedelta
from decimal import Decimal
from typing import AsyncGenerator, Generator
import pytest
import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Force test mode
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DISABLE_ML", "0")  # Enable ML for real tests

# Load .env file for DATABASE_URL
from dotenv import load_dotenv
load_dotenv()


# =============================================================================
# DATABASE FIXTURES - Real database, no mocks
# =============================================================================

@pytest.fixture(scope="session")
def test_database_url() -> str:
    """
    Get real test database URL.
    
    Real integration tests REQUIRE PostgreSQL - they test actual database behavior.
    SQLite is NOT supported for real_tests as it lacks PostgreSQL-specific features.
    """
    # Load from .env or environment
    pg_url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    
    if not pg_url or pg_url.startswith("sqlite"):
        pytest.skip(
            "Real integration tests require PostgreSQL. "
            "Set DATABASE_URL in .env or start Docker: docker-compose up -d db"
        )
    
    # Ensure we use sync driver for sync engine
    if pg_url.startswith("postgresql+asyncpg://"):
        pg_url = pg_url.replace("postgresql+asyncpg://", "postgresql://")
    
    return pg_url


@pytest.fixture(scope="session")
def async_test_database_url(test_database_url: str) -> str:
    """Convert sync URL to async URL for PostgreSQL."""
    if test_database_url.startswith("postgresql://"):
        return test_database_url.replace("postgresql://", "postgresql+asyncpg://")
    # SQLite not supported for real tests
    pytest.skip("Real integration tests require PostgreSQL, not SQLite")
    return test_database_url


@pytest.fixture(scope="session")
def sync_engine(test_database_url: str):
    """Create real sync database engine."""
    engine = create_engine(test_database_url, echo=False)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def sync_session_factory(sync_engine) -> sessionmaker:
    """Create real session factory."""
    return sessionmaker(bind=sync_engine, expire_on_commit=False)


@pytest.fixture
def db_session(sync_session_factory) -> Generator[Session, None, None]:
    """
    Provide a real database session for each test.
    Rolls back after each test to keep database clean.
    """
    session = sync_session_factory()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture(scope="session")
def async_engine(async_test_database_url: str):
    """Create real async database engine."""
    engine = create_async_engine(async_test_database_url, echo=False)
    yield engine
    # Cleanup handled by event loop


@pytest.fixture
async def async_db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a real async database session."""
    async_session_maker = async_sessionmaker(
        async_engine, 
        class_=AsyncSession,
        expire_on_commit=False
    )
    async with async_session_maker() as session:
        try:
            yield session
            await session.rollback()
        finally:
            await session.close()


# =============================================================================
# HTTP CLIENT FIXTURES - Real API calls
# =============================================================================

@pytest.fixture(scope="session")
def api_base_url() -> str:
    """Base URL for API testing."""
    return os.environ.get("TEST_API_URL", "http://localhost:8000")


@pytest.fixture
async def http_client(api_base_url: str) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Real HTTP client for API integration tests.
    No mocking - makes actual HTTP requests.
    """
    async with httpx.AsyncClient(
        base_url=api_base_url,
        timeout=30.0,
        follow_redirects=True
    ) as client:
        yield client


# Module-level cache for auth token
_auth_cache = {"token": None, "email": None, "password": None}


@pytest.fixture
async def authenticated_client(http_client: httpx.AsyncClient) -> httpx.AsyncClient:
    """
    HTTP client with real authentication.
    Creates a test user once and reuses the token.
    """
    global _auth_cache
    
    # If we already have a valid token, reuse it
    if _auth_cache["token"]:
        http_client.headers["Authorization"] = f"Bearer {_auth_cache['token']}"
        return http_client
    
    # Create test user credentials (once)
    if not _auth_cache["email"]:
        _auth_cache["email"] = f"test_{uuid.uuid4().hex[:8]}@test.com"
        _auth_cache["password"] = "TestPassword123!"
    
    test_email = _auth_cache["email"]
    test_password = _auth_cache["password"]
    
    # Register user
    register_response = await http_client.post("/api/v1/auth/register", json={
        "email": test_email,
        "password": test_password,
        "username": f"testuser_{uuid.uuid4().hex[:8]}"
    })
    
    if register_response.status_code not in (200, 201, 409):  # 409 = already exists
        pytest.skip(f"Could not register test user: {register_response.text}")
    
    # Login to get token - use email as username since registration uses email as username
    login_response = await http_client.post("/api/v1/auth/login", json={
        "username": test_email,
        "password": test_password
    })
    
    if login_response.status_code != 200:
        pytest.skip(f"Could not login test user: {login_response.text}")
    
    token = login_response.json().get("access_token")
    _auth_cache["token"] = token
    http_client.headers["Authorization"] = f"Bearer {token}"
    
    return http_client


# =============================================================================
# BROKER FIXTURES - Real paper trading
# =============================================================================

@pytest.fixture(scope="session")
def alpaca_paper_config() -> dict:
    """
    Real Alpaca paper trading configuration.
    Supports multiple environment variable naming conventions:
    - ALPACA_API_KEY / ALPACA_SECRET_KEY
    - ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY
    """
    # Support both naming conventions
    api_key = os.environ.get("ALPACA_API_KEY") or os.environ.get("ALPACA_API_KEY_ID")
    secret_key = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET_KEY")
    
    if not api_key or not secret_key:
        pytest.skip("Alpaca credentials not configured for real broker tests")
    
    return {
        "api_key": api_key,
        "secret_key": secret_key,
        "paper": True,
        "base_url": os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    }


@pytest.fixture
async def paper_broker(alpaca_paper_config: dict):
    """
    Real Alpaca paper trading broker client.
    Makes actual API calls to Alpaca paper trading.
    """
    from backend.integrations.alpaca_broker import AlpacaBrokerClient
    
    # AlpacaBrokerClient reads from environment variables, which we've already verified
    broker = AlpacaBrokerClient()
    
    # Verify connection
    try:
        account = await broker.get_account()
        assert account is not None, "Failed to connect to Alpaca paper trading"
    except Exception as e:
        pytest.skip(f"Could not connect to Alpaca: {e}")
    
    yield broker


# =============================================================================
# TEST DATA FACTORIES - Generate valid trading data
# =============================================================================

class OrderFactory:
    """Factory for creating valid order data."""
    
    @staticmethod
    def market_buy(symbol: str = "AAPL", qty: int = 1) -> dict:
        return {
            "symbol": symbol,
            "qty": qty,
            "side": "buy",
            "type": "market",
            "time_in_force": "day"
        }
    
    @staticmethod
    def market_sell(symbol: str = "AAPL", qty: int = 1) -> dict:
        return {
            "symbol": symbol,
            "qty": qty,
            "side": "sell",
            "type": "market",
            "time_in_force": "day"
        }
    
    @staticmethod
    def limit_buy(symbol: str = "AAPL", qty: int = 1, price: float = 150.0) -> dict:
        return {
            "symbol": symbol,
            "qty": qty,
            "side": "buy",
            "type": "limit",
            "limit_price": price,
            "time_in_force": "day"
        }
    
    @staticmethod
    def limit_sell(symbol: str = "AAPL", qty: int = 1, price: float = 200.0) -> dict:
        return {
            "symbol": symbol,
            "qty": qty,
            "side": "sell",
            "type": "limit",
            "limit_price": price,
            "time_in_force": "day"
        }


class PositionFactory:
    """Factory for creating valid position data."""
    
    @staticmethod
    def long_position(symbol: str = "AAPL", qty: int = 100, avg_price: float = 150.0) -> dict:
        return {
            "symbol": symbol,
            "qty": Decimal(str(qty)),
            "side": "long",
            "avg_entry_price": Decimal(str(avg_price)),
            "market_value": Decimal(str(qty * avg_price)),
            "cost_basis": Decimal(str(qty * avg_price)),
            "unrealized_pl": Decimal("0"),
            "unrealized_plpc": Decimal("0")
        }


class StrategyFactory:
    """Factory for creating valid strategy configurations."""
    
    @staticmethod
    def momentum_strategy() -> dict:
        return {
            "name": f"test_momentum_{uuid.uuid4().hex[:8]}",
            "type": "momentum",
            "symbols": ["AAPL", "MSFT", "GOOGL"],
            "parameters": {
                "lookback_period": 20,
                "momentum_threshold": 0.02,
                "max_position_size": 0.1
            },
            "risk_limits": {
                "max_position_value": 10000,
                "max_daily_loss": 500,
                "max_drawdown": 0.05
            },
            "enabled": True
        }
    
    @staticmethod
    def mean_reversion_strategy() -> dict:
        return {
            "name": f"test_mean_reversion_{uuid.uuid4().hex[:8]}",
            "type": "mean_reversion",
            "symbols": ["SPY", "QQQ"],
            "parameters": {
                "lookback_period": 14,
                "std_threshold": 2.0,
                "hold_period": 5
            },
            "risk_limits": {
                "max_position_value": 5000,
                "max_daily_loss": 250
            },
            "enabled": True
        }


@pytest.fixture
def order_factory() -> OrderFactory:
    return OrderFactory()


@pytest.fixture
def position_factory() -> PositionFactory:
    return PositionFactory()


@pytest.fixture
def strategy_factory() -> StrategyFactory:
    return StrategyFactory()


# =============================================================================
# CLEANUP UTILITIES
# =============================================================================

@pytest.fixture
async def cleanup_test_orders(paper_broker):
    """
    Cancel any test orders after each test.
    Only runs for tests that use the paper_broker fixture.
    """
    yield
    
    try:
        # Cancel all open orders
        await paper_broker.cancel_all_orders()
    except Exception:
        pass  # Ignore cleanup errors


@pytest.fixture(scope="session", autouse=True)
def setup_test_database(sync_engine):
    """
    Initialize test database schema.
    For real integration tests, we assume the database is already set up
    via Docker/migrations. We just verify the connection works.
    """
    from sqlalchemy import text
    
    # Just verify the connection works - don't try to create tables
    # as they should already exist from Docker migrations
    with sync_engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
    
    yield
    
    # Do NOT drop tables - we're using the real database


# =============================================================================
# MARKET HOURS UTILITIES
# =============================================================================

def is_market_open() -> bool:
    """Check if US stock market is currently open."""
    from datetime import datetime
    import pytz
    
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    
    # Check if weekday
    if now.weekday() >= 5:
        return False
    
    # Check market hours (9:30 AM - 4:00 PM ET)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return market_open <= now <= market_close


@pytest.fixture
def require_market_open():
    """Skip test if market is closed."""
    if not is_market_open():
        pytest.skip("Test requires market to be open")


# =============================================================================
# PERFORMANCE TIMING
# =============================================================================

@pytest.fixture
def timing():
    """Utility for measuring test execution time."""
    import time
    
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = time.perf_counter()
        
        def stop(self) -> float:
            self.end_time = time.perf_counter()
            return self.elapsed
        
        @property
        def elapsed(self) -> float:
            if self.start_time is None:
                return 0
            end = self.end_time or time.perf_counter()
            return end - self.start_time
        
        def assert_under(self, max_seconds: float, operation: str = "Operation"):
            elapsed = self.elapsed
            assert elapsed < max_seconds, f"{operation} took {elapsed:.3f}s, expected < {max_seconds}s"
    
    return Timer()
