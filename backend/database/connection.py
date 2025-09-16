"""
Database connection utilities.
Compatibility module for tests that expect backend.database.connection
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator, Any
import asyncio

# Define SessionLocal directly in this module to avoid circular imports
# This can be overridden by tests or app initialization
SessionLocal = None  # type: ignore[assignment]


def connection():
    """
    Simple connection function for test compatibility.
    Returns a mock connection object that tests can use.
    """
    class MockConnection:
        def close(self):
            pass
        def commit(self):
            pass
        def rollback(self):
            pass
    return MockConnection()


@asynccontextmanager
async def get_database_session() -> AsyncIterator[Any]:
    """
    Async context manager to yield a DB session.
    Uses app-installed sessionmaker when available; falls back to SessionLocal.
    In tests, this is commonly overridden via dependency overrides.
    """
    # Import globals to allow for runtime patching
    global SessionLocal
    session = None
    try:
        if SessionLocal is not None:
            session = SessionLocal()
        yield session
        if session is not None and hasattr(session, "commit"):
            commit_method = session.commit()
            if asyncio.iscoroutine(commit_method):
                await commit_method
    except Exception:
        if session is not None and hasattr(session, "rollback"):
            rollback_method = session.rollback()
            if asyncio.iscoroutine(rollback_method):
                await rollback_method
        raise
    finally:
        if session is not None and hasattr(session, "close"):
            close_method = session.close()
            if asyncio.iscoroutine(close_method):
                await close_method
