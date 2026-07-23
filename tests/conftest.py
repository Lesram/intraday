"""
Pytest configuration and fixtures for tests/ directory.

This conftest.py provides fixtures for testing API routes and endpoints
with proper database initialization and mocking.
"""

import pytest
import os
import concurrent.futures
import asyncio
import pathlib
import glob
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

# ── Brain-volume isolation (2026-07-23 ops work order follow-up) ─────────────
# Tests that construct an engine/brain with the default brain_dir resolve it via
# ORGANISM_BRAIN_DIR (read at IMPORT time in backend/organism/live_engine.py) and
# default to the REAL organism_brain/ — the live Docker volume. Un-isolated runs
# have destroyed data twice (qty=0 shadow pollution; four 07-07 corrupt-head
# forensic dirs evicted via the keep-5 retention cap on 2026-07-23). This
# module-level redirect runs before any test module imports live_engine, so the
# import-time BRAIN_DIR pickup lands on a scratch dir. An explicit
# ORGANISM_BRAIN_DIR from the caller is respected (CI / manual overrides).
# Tests that intentionally read the real volume (test_v12_baseline_invariants,
# test_audit_1_3_edge_monitor, …) build explicit absolute paths and are
# unaffected by this env var.
if "ORGANISM_BRAIN_DIR" not in os.environ:
    os.environ["ORGANISM_BRAIN_DIR"] = tempfile.mkdtemp(
        prefix="test_organism_brain_"
    )

# Global flag to track if database has been initialized
_db_initialized = False
_db_engine = None
_db_sessionmaker = None


@pytest.fixture(autouse=True)
def reset_module_caches():
    """
    Autouse fixture to reset module-level caches between tests.
    This prevents test pollution from cached database connections.
    """
    yield
    # After each test, clear any cached imports that might hold stale state
    import sys
    modules_to_clear = [
        'backend.infra.db',
        'backend.database',
    ]
    for mod in modules_to_clear:
        if mod in sys.modules:
            module = sys.modules[mod]
            # Reset any module-level state
            if hasattr(module, '_engine'):
                module._engine = None
            if hasattr(module, '_sessionmaker'):
                module._sessionmaker = None


def pytest_configure(config):
    """
    Set test environment variables before any tests run.
    Also clean up any leftover test database files.
    """
    # Clean up any leftover test database files from previous runs
    test_results_dir = pathlib.Path("./test_results")
    if test_results_dir.exists():
        for db_file in test_results_dir.glob("test_db_*.sqlite3*"):
            try:
                db_file.unlink()
            except Exception:
                pass  # Ignore cleanup errors
    
    # Test admin credentials
    os.environ.setdefault("TEST_ADMIN_USERNAME", "testadmin")
    os.environ.setdefault("TEST_ADMIN_PASSWORD", "TestP@ssw0rd123")
    
    # Database configuration for tests - USE POSTGRESQL FROM .env
    # Tests should use the actual PostgreSQL database like production
    # The .env file already has: DATABASE_URL=postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading
    
    # Mock configuration
    os.environ.setdefault("USE_MOCK_BROKER", "true")
    os.environ.setdefault("USE_MOCK_DATA", "true")
    os.environ.setdefault("APP_ENVIRONMENT", "testing")
    os.environ.setdefault("ENVIRONMENT", "testing")

    # Ensure JWT secret exists for token creation in tests
    os.environ.setdefault("SECURITY_JWT_SECRET", "test-jwt-secret-not-for-production")
    os.environ.setdefault("PICKLE_HMAC_SECRET", "test-pickle-hmac-secret-not-for-production")

    # Default test DB to SQLite unless explicitly provided.
    # Use a session-unique database to avoid conflicts between test runs
    import uuid as _uuid
    unique_session_id = _uuid.uuid4().hex[:8]
    os.environ.setdefault(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///./test_results/test_db_{unique_session_id}.sqlite3",
    )
    
    # Other settings
    os.environ.setdefault("DEBUG", "false")
    os.environ.setdefault("LOG_LEVEL", "WARNING")


@pytest.fixture
async def mock_db_session():
    """
    Fixture that provides a mocked database session.
    
    This prevents 'DB not initialized' errors during testing.
    """
    from sqlalchemy.ext.asyncio import AsyncSession
    
    # Create a mock session
    session = AsyncMock(spec=AsyncSession)
    
    # Mock common session methods
    session.execute = AsyncMock(return_value=MagicMock())
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = MagicMock()
    session.query = MagicMock()
    
    return session


@pytest.fixture
def client():
    """
    Create a test client for the FastAPI app with proper initialization.
    
    Uses the actual PostgreSQL database from .env file.
    Assumes the database is already running via Docker and has the users table created.
    """
    import uuid as _uuid
    
    # Set test environment before any imports
    os.environ["APP_ENVIRONMENT"] = "testing"
    os.environ["USE_MOCK_BROKER"] = "true"
    os.environ["USE_MOCK_DATA"] = "true"
    
    # Load DATABASE_URL from .env file (PostgreSQL connection)
    from dotenv import load_dotenv
    load_dotenv()
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        # Fall back to a unique file-based SQLite DB for test isolation
        # Each test function gets its own database file to avoid lock contention
        import tempfile as _tempfile
        _test_dir = os.path.join(os.path.dirname(__file__), "..", "test_results")
        os.makedirs(_test_dir, exist_ok=True)
        unique_id = _uuid.uuid4().hex[:8]
        database_url = f"sqlite+aiosqlite:///{_test_dir}/test_db_{unique_id}.sqlite3"
        os.environ["DATABASE_URL"] = database_url
    
    # Initialize database before creating app
    from backend.infra.db import init_db
    engine, sessionmaker = init_db(database_url)

    async def _ensure_sqlite_schema_and_seed() -> None:
        """Ensure minimal schema exists for auth tests when using SQLite."""
        if not str(database_url).startswith("sqlite"):
            return

        from sqlalchemy import text as sql_text

        async with sessionmaker() as session:
            # Minimal users table required by backend.infra.users
            await session.execute(
                sql_text(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        email TEXT NULL,
                        hashed_password TEXT NOT NULL,
                        roles TEXT NOT NULL,
                        is_active BOOLEAN NOT NULL DEFAULT 1,
                        failed_login_attempts INTEGER NOT NULL DEFAULT 0,
                        locked_until TEXT NULL,
                        last_login TEXT NULL
                    );
                    """
                )
            )
            
            # model_registry table for ML model tests
            await session.execute(
                sql_text(
                    """
                    CREATE TABLE IF NOT EXISTS model_registry (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        version TEXT NOT NULL,
                        path TEXT,
                        metrics TEXT,
                        active BOOLEAN NOT NULL DEFAULT 0,
                        trained_at TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    """
                )
            )

            # Seed expected admin user for tests using bcrypt password hash
            import bcrypt
            username = "admin@example.com"
            password = "Admin123!@#"
            # Use bcrypt for proper password hashing (matches production auth system)
            hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

            # Use INSERT OR REPLACE to reset any locked accounts from previous test runs
            await session.execute(
                sql_text(
                    """
                    INSERT OR REPLACE INTO users (
                        username, email, hashed_password, roles, is_active,
                        failed_login_attempts, locked_until, last_login
                    ) VALUES (
                        :username, :email, :hashed_password, :roles, :is_active,
                        0, NULL, NULL
                    );
                    """
                ),
                {
                    "username": username,
                    "email": username,
                    "hashed_password": hashed_password,
                    "roles": '["admin","trader"]',
                    "is_active": 1,
                },
            )
            await session.commit()

    # Ensure local schema is available before app starts
    asyncio.run(_ensure_sqlite_schema_and_seed())
    
    # Import here to avoid circular imports
    from backend.api.factory import create_app
    
    # Create app (will use DATABASE_URL from environment)
    app = create_app()
    
    # Store sessionmaker in app state for dependency injection
    app.state.sessionmaker = sessionmaker
    app.state.db_sessionmaker = sessionmaker
    
    # Create TestClient - manually manage lifecycle to handle teardown errors
    test_client = TestClient(app, raise_server_exceptions=True)
    test_client.__enter__()
    
    yield test_client
    
    # Manual teardown with error suppression
    try:
        test_client.__exit__(None, None, None)
    except (concurrent.futures.CancelledError, Exception):
        # Suppress teardown errors - background tasks may be cancelled during shutdown
        # This is expected behavior and doesn't affect test validity
        pass
    
    # Clean up unique SQLite database file if it was created
    if database_url.startswith("sqlite") and "test_db_" in database_url:
        import pathlib
        db_path = database_url.replace("sqlite+aiosqlite:///", "")
        db_file = pathlib.Path(db_path)
        try:
            if db_file.exists():
                db_file.unlink()
        except Exception:
            pass  # Ignore cleanup errors


@pytest.fixture
def mock_get_db_session(mock_db_session):
    """
    Fixture that patches get_db_session to return a mock session.
    
    Use this to avoid database initialization errors in tests.
    """
    async def _mock_get_db():
        yield mock_db_session
    
    with patch('backend.infra.db.get_db_session', _mock_get_db):
        yield _mock_get_db


@pytest.fixture
def test_credentials():
    """
    Fixture that provides test admin credentials.
    
    Returns:
        tuple: (username, password)
    """
    username = os.getenv("TEST_ADMIN_USERNAME", "testadmin")
    password = os.getenv("TEST_ADMIN_PASSWORD", "TestP@ssw0rd123")
    return username, password


@pytest.fixture
def test_login_data(test_credentials):
    """
    Fixture that provides test login data as a dictionary.
    
    Returns:
        dict: Login data with username and password
    """
    username, password = test_credentials
    return {"username": username, "password": password}


@pytest.fixture
def token(client):
    """
    Fixture that provides a JWT access token for API tests.
    
    Returns:
        str: JWT access token
    """
    try:
        response = client.post("/auth/login", json={
            "username": "admin@example.com",
            "password": "Admin123!@#"
        })
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            if token:
                return token
        else:
            print(f"Warning: Login failed with status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Warning: Could not get auth token: {e}")
    
    raise RuntimeError(
        "Failed to authenticate for tests. "
        "Ensure PostgreSQL is running and admin@example.com user exists with password Admin123!@#"
    )


@pytest.fixture
def auth_headers(client):
    """
    Fixture that provides authentication headers for API tests.
    
    Uses the actual PostgreSQL admin user credentials.
    
    Returns:
        dict: Headers with Authorization token
    """
    try:
        # Use actual PostgreSQL admin credentials
        response = client.post("/auth/login", json={
            "username": "admin@example.com",
            "password": "Admin123!@#"
        })
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            if token:
                return {"Authorization": f"Bearer {token}"}
        else:
            print(f"Warning: Login failed with status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Warning: Could not get auth token: {e}")
        import traceback
        traceback.print_exc()
    
    # Raise error if authentication fails - tests should not run with mock tokens
    raise RuntimeError(
        "Failed to authenticate for tests. "
        "Ensure PostgreSQL is running and admin@example.com user exists with password Admin123!@#"
    )
