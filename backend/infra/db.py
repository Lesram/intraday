"""
Database infrastructure for async PostgreSQL operations.
Provides engine, session management, health checks, and FastAPI dependencies.
Enhanced with comprehensive observability including tracing and metrics.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging
import time

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from backend.infra.logging import get_logger as get_structured_logger

# B2.5 - Observability imports
from backend.infra.observability import record_database_operation, trace_span

logger = logging.getLogger(__name__)

# Global variables for engine and sessionmaker
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_engine = None


def build_engine(dsn: str):
    global _engine
    kw = dict(
        pool_pre_ping=True,
        connect_args={},
    )

    # Configure connection pool based on database type
    if dsn.startswith("sqlite"):
        # SQLite: Use NullPool to prevent connection sharing issues
        kw["poolclass"] = NullPool
        kw["connect_args"] = {
            "check_same_thread": False,
            "timeout": 20,
        }
        logger.info("Using NullPool for SQLite database")
    else:
        # PostgreSQL: Production-ready connection pooling
        kw.update(
            pool_size=10,        # Base connection pool size
            max_overflow=20,     # Additional connections under load
            pool_recycle=3600,   # Recycle connections every hour
            pool_reset_on_return="commit",  # Clean state on return
            pool_timeout=30,     # Pool checkout timeout
        )

        # PostgreSQL-specific connection parameters
        kw["connect_args"] = {
            "server_settings": {
                "application_name": "trading_platform",
                "jit": "off",  # Disable JIT for predictable performance
            },
            "command_timeout": 60,
        }

        logger.info("Using production PostgreSQL connection pool",
                   extra={
                       "pool_size": 10,
                       "max_overflow": 20,
                       "pool_recycle": 3600,
                       "pool_reset_on_return": "commit"
                   })

    _engine = create_async_engine(dsn, echo=False, **kw)
    return _engine


def build_sessionmaker(engine):
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
        autoflush=True,     # Auto-flush pending changes
        autocommit=False,   # Explicit transaction control
    )


def init_db(dsn: str):
    global _sessionmaker
    engine = build_engine(dsn)
    _sessionmaker = build_sessionmaker(engine)
    return engine, _sessionmaker


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Production-ready database session with proper lifecycle management.
    Ensures connections are properly returned to the pool.
    """
    assert _sessionmaker is not None, "DB not initialized"

    session = _sessionmaker()
    try:
        with trace_span("database_session"):
            yield session
            # Commit transaction if no exception occurred
            await session.commit()
    except Exception as e:
        # Rollback on any exception
        await session.rollback()
        logger.error(f"Database session error, rolling back: {e}")
        raise
    finally:
        # Always close session to return connection to pool
        try:
            await session.close()
        except Exception as close_error:
            logger.error(f"Error closing database session: {close_error}")
            # Don't re-raise close errors as they mask the original error


async def dispose_engine():
    await _engine.dispose()


def get_engine() -> AsyncEngine:
    """Get the async database engine."""
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_db() first.")
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Get the async sessionmaker."""
    if _sessionmaker is None:
        raise RuntimeError(
            "Database sessionmaker not initialized. Call init_db() first."
        )
    return _sessionmaker



@asynccontextmanager
async def get_session_from(app_state) -> AsyncGenerator[AsyncSession, None]:
    """Get AsyncSession from app state db_sessionmaker"""
    async with app_state.db_sessionmaker() as session:
        yield session


async def db_health_check() -> bool:
    """
    Perform database health check with comprehensive observability.

    Returns:
        True if database is healthy

    Raises:
        Exception if database is not accessible
    """
    if _engine is None:
        raise RuntimeError("Database engine not initialized")

    start_time = time.time()
    structured_logger = get_structured_logger(__name__)

    with trace_span(
        "database_health_check",
        {"db.operation": "health_check", "db.system": "postgresql"},
    ) as span:
        try:
            async with _engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                row = result.fetchone()

                duration_seconds = time.time() - start_time

                if row and row[0] == 1:
                    # Record successful health check metrics
                    record_database_operation(
                        operation="health_check",
                        duration_seconds=duration_seconds,
                        success=True,
                    )

                    # Update span with success info
                    span.set_attribute("db.health_check_result", "success")
                    span.set_attribute("db.duration_seconds", duration_seconds)

                    # Log structured event
                    structured_logger.log_database_operation(
                        operation="health_check", duration_ms=duration_seconds * 1000
                    )

                    logger.debug("Database health check passed")
                    return True
                else:
                    raise RuntimeError(
                        "Database health check failed: unexpected result"
                    )
        except Exception as e:
            duration_seconds = time.time() - start_time

            # Record failed health check metrics
            record_database_operation(
                operation="health_check",
                duration_seconds=duration_seconds,
                success=False,
            )

            # Update span with error info
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))
            span.set_attribute("db.health_check_result", "failed")
            span.set_attribute("db.duration_seconds", duration_seconds)

            # Log structured error event
            structured_logger.log_database_operation(
                operation="health_check",
                duration_ms=duration_seconds * 1000,
                error=str(e),
            )

            logger.error("Database health check failed", extra={"error": str(e)})
            raise


async def quick_ping(session: AsyncSession) -> bool:
    """
    Quick database ping for readiness checks with 100ms timeout.

    Args:
        session: Database session to ping with

    Returns:
        True if ping succeeds within timeout

    Raises:
        asyncio.TimeoutError: If ping takes longer than 100ms
        Exception: If ping fails for other reasons
    """
    try:
        # Execute simple SELECT 1 with 100ms timeout
        result = await asyncio.wait_for(
            session.execute(text("SELECT 1")),
            timeout=0.1  # 100ms timeout
        )
        row = result.fetchone()
        return row is not None and row[0] == 1
    except TimeoutError:
        logger.warning("Database ping timed out after 100ms")
        raise
    except Exception as e:
        logger.warning("Database ping failed", extra={"error": str(e)})
        raise


async def close_db() -> None:
    """Close database engine and cleanup resources."""
    global _engine, _sessionmaker

    if _engine:
        await _engine.dispose()
        logger.info("Database engine disposed")

    _engine = None
    _sessionmaker = None


# FastAPI Dependency
async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency to provide database session.

    Args:
        request: FastAPI request object containing app state

    Yields:
        AsyncSession: Database session
    """
    sessionmaker = request.app.state.db_sessionmaker
    async with sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for getting database session outside FastAPI.

    Yields:
        AsyncSession: Database session
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
