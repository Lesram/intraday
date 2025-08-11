"""
Database infrastructure for async PostgreSQL operations.
Provides engine, session management, health checks, and FastAPI dependencies.
Enhanced with comprehensive observability including tracing and metrics.
"""
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

from backend.infra.logging import get_logger as get_structured_logger

# B2.5 - Observability imports
from backend.infra.observability import record_database_operation, trace_span

from ..config import get_settings

logger = logging.getLogger(__name__)

# Global variables for engine and sessionmaker
_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get the async database engine."""
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_db() first.")
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Get the async sessionmaker."""
    if _sessionmaker is None:
        raise RuntimeError("Database sessionmaker not initialized. Call init_db() first.")
    return _sessionmaker


def init_db() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """
    Initialize database engine and sessionmaker from settings.

    Returns:
        Tuple of (engine, sessionmaker)
    """
    global _engine, _sessionmaker

    settings = get_settings()

    # Use data.database_url from the nested config
    database_url = settings.data.database_url

    # Convert sqlite URL to async postgres if needed for production
    if database_url.startswith("sqlite"):
        logger.warning("SQLite detected. For production, use PostgreSQL with asyncpg driver.")
        # For SQLite, use aiosqlite
        if not database_url.startswith("sqlite+aiosqlite"):
            database_url = database_url.replace("sqlite:", "sqlite+aiosqlite:")

    # Create async engine with connection pool settings
    _engine = create_async_engine(
        database_url,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
        pool_timeout=settings.database.pool_timeout,
        echo=settings.database.echo,
        # Important for async operations
        future=True,
    )

    # Create sessionmaker
    _sessionmaker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    logger.info(
        "Database initialized",
        extra={
            "database_url": database_url.split("@")[-1] if "@" in database_url else database_url,  # Hide credentials
            "pool_size": settings.database.pool_size,
            "max_overflow": settings.database.max_overflow,
            "echo": settings.database.echo,
        }
    )

    return _engine, _sessionmaker


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
        {
            "db.operation": "health_check",
            "db.system": "postgresql"
        }
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
                        success=True
                    )

                    # Update span with success info
                    span.set_attribute("db.health_check_result", "success")
                    span.set_attribute("db.duration_seconds", duration_seconds)

                    # Log structured event
                    structured_logger.log_database_operation(
                        operation="health_check",
                        duration_ms=duration_seconds * 1000
                    )

                    logger.debug("Database health check passed")
                    return True
                else:
                    raise RuntimeError("Database health check failed: unexpected result")
        except Exception as e:
            duration_seconds = time.time() - start_time

            # Record failed health check metrics
            record_database_operation(
                operation="health_check",
                duration_seconds=duration_seconds,
                success=False
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
                error=str(e)
            )

            logger.error("Database health check failed", extra={"error": str(e)})
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
