"""
Pytest configuration and fixtures for tests/ directory.

This conftest.py provides fixtures for testing API routes and endpoints
with proper database initialization and mocking.
"""

import pytest
import concurrent.futures
import os
import pathlib
import json
import re
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

# Third isolation hole (found 2026-07-29 during the activation rebuild): the
# shadow-exit recorder path is a SEPARATE env with its own literal default
# (live_engine.py ORGANISM_SHADOW_EXIT_TELEMETRY_PATH), so the brain-dir
# redirect above did not cover it — replay/test runs with
# ORGANISM_SHADOW_EXIT_POLICY set (loaded from .env by pydantic settings) wrote
# qty>0 Jan-replay rows into the REAL organism_brain/shadow_exit_telemetry.jsonl.
# Redirect it into the scratch brain dir; an explicit caller value is respected.
if "ORGANISM_SHADOW_EXIT_TELEMETRY_PATH" not in os.environ:
    os.environ["ORGANISM_SHADOW_EXIT_TELEMETRY_PATH"] = os.path.join(
        os.environ["ORGANISM_BRAIN_DIR"], "shadow_exit_telemetry.jsonl"
    )

def _isolated_postgres_url(value: str) -> str:
    """Only an explicit, test-named local/service PostgreSQL DB may be seeded.

    DATABASE_URL alone is deliberately not authorization: a developer shell or
    dotenv file may contain the installed platform's database connection.
    """
    from sqlalchemy.engine import make_url

    try:
        url = make_url(value)
    except Exception:
        raise ValueError("Invalid INTRA_TEST_DATABASE_URL") from None
    if (
        url.drivername != "postgresql+asyncpg"
        or url.host not in {"localhost", "127.0.0.1", "::1", "postgres"}
        or not re.fullmatch(r"test(?:db|_[a-z0-9_]+)", url.database or "")
        or not re.fullmatch(r"test(?:user|_[a-z0-9_]+)", url.username or "")
        or url.query
    ):
        raise ValueError(
            "INTRA_TEST_DATABASE_URL must identify an isolated local PostgreSQL "
            "test database and test user; arbitrary application databases are refused"
        )
    return value


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
    Set isolated test defaults before any test modules are imported.
    """
    # Never delete another test process's files or inherit a platform DSN.
    os.environ.setdefault("TEST_ADMIN_USERNAME", "admin@example.com")
    os.environ.setdefault("TEST_ADMIN_PASSWORD", "Admin123!@#")

    # Mock configuration
    os.environ.setdefault("USE_MOCK_BROKER", "true")
    os.environ.setdefault("USE_MOCK_DATA", "true")
    os.environ.setdefault("APP_ENVIRONMENT", "testing")
    os.environ.setdefault("ENVIRONMENT", "testing")

    # Ensure JWT secret exists for token creation in tests
    os.environ.setdefault("SECURITY_JWT_SECRET", "test-jwt-secret-not-for-production")
    os.environ.setdefault("PICKLE_HMAC_SECRET", "test-pickle-hmac-secret-not-for-production")

    explicit_test_url = os.environ.get("INTRA_TEST_DATABASE_URL")
    if explicit_test_url:
        os.environ["DATABASE_URL"] = _isolated_postgres_url(explicit_test_url)
    else:
        scratch = pathlib.Path(tempfile.mkdtemp(prefix="intra_pytest_db_"))
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{scratch / 'session.sqlite3'}"

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
def isolated_database_url(tmp_path):
    """A caller-owned migrated PostgreSQL DB, or this test's private SQLite file."""
    explicit_test_url = os.environ.get("INTRA_TEST_DATABASE_URL")
    if explicit_test_url:
        return _isolated_postgres_url(explicit_test_url)
    return f"sqlite+aiosqlite:///{tmp_path / 'api.sqlite3'}"


async def _seed_api_test_user(app, credentials):
    """Run on TestClient's portal, using the pool created by app startup.

    PostgreSQL must already have the real Alembic schema. SQLite supplies only
    the auth/model tables needed by the lightweight API tests; it is not used
    as evidence for PostgreSQL migrations or strategy schema correctness.
    """
    from sqlalchemy import bindparam, text
    from sqlalchemy.dialects.postgresql import ARRAY
    from sqlalchemy import String
    from backend.infra.security import hash_password

    factory = app.state.sessionmaker
    assert factory is app.state.db_sessionmaker, "App database factories diverged"
    async with factory() as session:
        is_sqlite = session.bind.dialect.name == "sqlite"
        if is_sqlite:
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL, roles TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until TEXT NULL, last_login TEXT NULL
                )
            """))
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS model_registry (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL,
                    path TEXT, metrics TEXT, active BOOLEAN NOT NULL DEFAULT 0,
                    trained_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )
            """))
        username, password = credentials
        statement = text("""
            INSERT INTO users (
                username, email, hashed_password, roles, is_active,
                failed_login_attempts, locked_until, last_login
            ) VALUES (:username, :email, :hashed_password, :roles, :active, 0, NULL, NULL)
            ON CONFLICT (username) DO UPDATE SET
                email = excluded.email, hashed_password = excluded.hashed_password,
                roles = excluded.roles, is_active = excluded.is_active,
                failed_login_attempts = 0, locked_until = NULL, last_login = NULL
        """)
        roles = ["admin", "trader"]
        if not is_sqlite:
            statement = statement.bindparams(bindparam("roles", type_=ARRAY(String)))
        await session.execute(statement, {
            "username": username,
            "email": username if "@" in username else f"{username}@example.test",
            "hashed_password": hash_password(password),
            "roles": json.dumps(roles) if is_sqlite else roles,
            "active": True,
        })
        await session.commit()


@pytest.fixture
def client(monkeypatch, isolated_database_url, test_credentials):
    """Real in-process API/authentication against an explicitly isolated DB.

    Startup creates the pool on TestClient's event loop. Seed through that same
    portal *after* startup; a separate asyncio.run() creates asyncpg connections
    attached to a closed/wrong event loop and is intentionally not used here.
    """
    for name, value in {
        "DATABASE_URL": isolated_database_url,
        "APP_ENVIRONMENT": "testing", "ENVIRONMENT": "testing",
        "USE_MOCK_BROKER": "true", "USE_MOCK_DATA": "true",
    }.items():
        monkeypatch.setenv(name, value)
    from backend.config.settings import AppSettings
    from backend.api.factory import create_app

    settings = AppSettings()
    assert settings.database.url == isolated_database_url
    app = create_app(settings=settings)
    test_client = TestClient(app, raise_server_exceptions=True)
    test_client.__enter__()
    try:
        assert test_client.portal is not None
        test_client.portal.call(_seed_api_test_user, app, test_credentials)
        yield test_client
    finally:
        _close_test_client(test_client)


def _close_test_client(test_client):
    try:
        test_client.__exit__(None, None, None)
    except concurrent.futures.CancelledError:
        # Existing application task sweeping cancels TestClient's wait_shutdown
        # portal task after DB disposal. Preserve only this known adapter case;
        # arbitrary shutdown exceptions must fail the test (the old fixture
        # suppressed every Exception).
        pass


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
    username = os.getenv("TEST_ADMIN_USERNAME", "admin@example.com")
    password = os.getenv("TEST_ADMIN_PASSWORD", "Admin123!@#")
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
def token(client, test_login_data):
    """Obtain a real signed token via database-backed password authentication."""
    response = client.post("/auth/login", json=test_login_data)
    assert response.status_code == 200, (
        f"Isolated test-user login failed with HTTP {response.status_code}"
    )
    token = response.json().get("access_token")
    assert isinstance(token, str) and token, "Login response omitted the access token"
    return token


@pytest.fixture
def auth_headers(token):
    """Share the real login fixture without a second login or synthetic JWT."""
    return {"Authorization": f"Bearer {token}"}
