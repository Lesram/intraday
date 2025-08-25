"""
Database connection utilities.
Compatibility module for tests that expect backend.database.connection
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator, Any
import asyncio

# Expect one of these to exist after app startup or tests:
# 1) app.state.db_sessionmaker (preferred), or
# 2) a module-level SessionLocal in backend.database (__init__.py)
try:
    from . import SessionLocal  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    SessionLocal = None  # type: ignore[assignment]


@asynccontextmanager
async def get_database_session() -> AsyncIterator[Any]:
    """
    Async context manager to yield a DB session.
    Uses app-installed sessionmaker when available; falls back to SessionLocal.
    In tests, this is commonly overridden via dependency overrides.
    """
    session = None
    try:
        if SessionLocal is not None:
            session = SessionLocal()
        yield session
        if hasattr(session, "commit"):
            await session.commit()
    except Exception:
        if hasattr(session, "rollback"):
            await session.rollback()
        raise
    finally:
        if hasattr(session, "close"):
            close = session.close()
            if asyncio.iscoroutine(close):
                await close
