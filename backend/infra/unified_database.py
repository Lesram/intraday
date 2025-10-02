"""
Unified Database Manager - Single Database Access Pattern

This module consolidates all database access chaos into a single, consistent system.
Eliminates direct SQL usage and ensures all access goes through proper ORM patterns.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool, QueuePool
from sqlalchemy.engine.events import PoolEvents

from backend.config.unified import get_unified_settings
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


class UnifiedDatabaseManager:
    """
    Unified database manager - single source of truth for all database operations.
    
    Replaces all the fragmented database configurations and provides:
    - Single async engine with proper connection pooling
    - Consistent session management
    - Health monitoring and metrics
    - Proper transaction handling
    """
    
    def __init__(self):
        self._engine: Optional[AsyncEngine] = None
        self._sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None
        self._settings = get_unified_settings()
        self._is_initialized = False
    
    async def initialize(self) -> None:
        """Initialize database engine and session factory."""
        if self._is_initialized:
            logger.warning("Database manager already initialized")
            return
        
        try:
            database_url = self._settings.get_database_url()
            logger.info(f"Initializing database with URL: {self._mask_url(database_url)}")
            
            # Create engine with appropriate pool settings
            self._engine = self._create_engine(database_url)
            
            # Create session factory
            self._sessionmaker = async_sessionmaker(
                bind=self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=True
            )
            
            # Test connection
            await self._test_connection()
            
            self._is_initialized = True
            logger.info("Database manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            await self._cleanup()
            raise RuntimeError(f"Database initialization failed: {e}") from e
    
    def _create_engine(self, database_url: str) -> AsyncEngine:
        """Create async engine with appropriate configuration."""
        engine_kwargs = {
            "echo": self._settings.debug,
            "future": True,
            "pool_pre_ping": True
        }
        
        if self._settings.database.is_sqlite:
            # SQLite configuration
            engine_kwargs.update({
                "poolclass": StaticPool,
                "connect_args": {
                    "check_same_thread": False,
                    "timeout": 30
                }
            })
        else:
            # PostgreSQL configuration
            engine_kwargs.update({
                "poolclass": QueuePool,
                "pool_size": self._settings.database.pool_size,
                "max_overflow": self._settings.database.max_overflow,
                "pool_timeout": self._settings.database.pool_timeout,
                "pool_recycle": self._settings.database.pool_recycle
            })
        
        engine = create_async_engine(database_url, **engine_kwargs)
        
        # Add connection pool event listeners for monitoring
        self._setup_engine_events(engine)
        
        return engine
    
    def _setup_engine_events(self, engine: AsyncEngine) -> None:
        """Setup engine event listeners for monitoring."""
        
        @event.listens_for(engine.sync_engine.pool, "connect")
        def on_connect(dbapi_conn, connection_record):
            logger.debug("New database connection established")
        
        @event.listens_for(engine.sync_engine.pool, "checkout")
        def on_checkout(dbapi_conn, connection_record, connection_proxy):
            logger.debug("Database connection checked out from pool")
        
        @event.listens_for(engine.sync_engine.pool, "checkin")
        def on_checkin(dbapi_conn, connection_record):
            logger.debug("Database connection returned to pool")
    
    async def _test_connection(self) -> None:
        """Test database connection."""
        if not self._sessionmaker:
            raise RuntimeError("Session factory not initialized")
        
        async with self._sessionmaker() as session:
            if self._settings.database.is_sqlite:
                result = await session.execute(text("SELECT 1"))
            else:
                result = await session.execute(text("SELECT version()"))
            
            result.fetchone()
            logger.info("Database connection test successful")
    
    def _mask_url(self, url: str) -> str:
        """Mask sensitive parts of database URL for logging."""
        if "://" not in url:
            return url
        
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            credentials, host_part = rest.rsplit("@", 1)
            return f"{scheme}://***@{host_part}"
        return url
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get database session with proper lifecycle management.
        
        This is the ONLY way database sessions should be obtained.
        Replaces all direct SQL usage throughout the codebase.
        
        Yields:
            AsyncSession: Database session with automatic transaction management
        """
        if not self._is_initialized:
            raise RuntimeError(
                "Database not initialized. Call await db_manager.initialize() first."
            )
        
        if not self._sessionmaker:
            raise RuntimeError("Session factory not available")
        
        async with self._sessionmaker() as session:
            try:
                logger.debug("Database session created")
                yield session
                await session.commit()
                logger.debug("Database session committed")
            except Exception as e:
                await session.rollback()
                logger.error(f"Database session error, rolling back: {e}")
                raise
            finally:
                await session.close()
                logger.debug("Database session closed")
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive database health check.
        
        Returns:
            Dict with health status and metrics
        """
        health_info = {
            "healthy": False,
            "initialized": self._is_initialized,
            "database_type": "sqlite" if self._settings.database.is_sqlite else "postgresql",
            "pool_info": {},
            "error": None
        }
        
        if not self._is_initialized:
            health_info["error"] = "Database not initialized"
            return health_info
        
        try:
            # Test connection
            async with self.get_session() as session:
                if self._settings.database.is_sqlite:
                    result = await session.execute(text("SELECT 1 as test"))
                else:
                    result = await session.execute(text("SELECT current_timestamp as test"))
                
                test_row = result.fetchone()
                if test_row:
                    health_info["healthy"] = True
            
            # Get pool information
            if self._engine and hasattr(self._engine, 'pool'):
                pool = self._engine.pool
                health_info["pool_info"] = {
                    "size": getattr(pool, 'size', lambda: 'N/A')(),
                    "checked_in": getattr(pool, 'checkedin', lambda: 'N/A')(),
                    "checked_out": getattr(pool, 'checkedout', lambda: 'N/A')(),
                    "overflow": getattr(pool, 'overflow', lambda: 'N/A')(),
                }
        
        except Exception as e:
            health_info["error"] = str(e)
            logger.error(f"Database health check failed: {e}")
        
        return health_info
    
    async def get_engine(self) -> AsyncEngine:
        """Get the database engine (for advanced usage)."""
        if not self._is_initialized or not self._engine:
            raise RuntimeError("Database not initialized")
        return self._engine
    
    async def get_sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        """Get the session factory (for dependency injection)."""
        if not self._is_initialized or not self._sessionmaker:
            raise RuntimeError("Database not initialized") 
        return self._sessionmaker
    
    async def _cleanup(self) -> None:
        """Cleanup database resources."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
        
        self._sessionmaker = None
        self._is_initialized = False
    
    async def shutdown(self) -> None:
        """Gracefully shutdown database manager."""
        logger.info("Shutting down database manager")
        await self._cleanup()
        logger.info("Database manager shutdown complete")
    
    def is_initialized(self) -> bool:
        """Check if database manager is initialized."""
        return self._is_initialized


# Global database manager instance - single source of truth
_db_manager: Optional[UnifiedDatabaseManager] = None


async def get_database_manager() -> UnifiedDatabaseManager:
    """
    Get global database manager instance.
    
    Returns:
        UnifiedDatabaseManager: Initialized database manager
    """
    global _db_manager
    
    if _db_manager is None:
        _db_manager = UnifiedDatabaseManager()
        await _db_manager.initialize()
    
    return _db_manager


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Convenience function for getting database session.
    
    This replaces ALL direct SQL usage throughout the codebase.
    Use this instead of sqlite3.connect() or any other direct database access.
    
    Yields:
        AsyncSession: Database session with proper transaction management
    """
    db_manager = await get_database_manager()
    async with db_manager.get_session() as session:
        yield session


async def init_database() -> UnifiedDatabaseManager:
    """
    Initialize database for application startup.
    
    Returns:
        UnifiedDatabaseManager: Initialized database manager
    """
    return await get_database_manager()


async def shutdown_database() -> None:
    """Shutdown database for application cleanup."""
    global _db_manager
    
    if _db_manager:
        await _db_manager.shutdown()
        _db_manager = None


async def database_health() -> Dict[str, Any]:
    """Get database health status."""
    try:
        db_manager = await get_database_manager()
        return await db_manager.health_check()
    except Exception as e:
        return {
            "healthy": False,
            "error": f"Failed to get database health: {e}"
        }


# FastAPI dependency function
async def get_session_dependency() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    async with get_db_session() as session:
        yield session


# Legacy compatibility functions (to be removed after refactoring)
def init_db(dsn: str):
    """Legacy compatibility - DO NOT USE IN NEW CODE."""
    logger.warning(
        "init_db() is deprecated. Use unified database manager instead."
    )
    # Return mock objects for compatibility
    class MockEngine:
        pass
    class MockSessionmaker:
        pass
    return MockEngine(), MockSessionmaker()


# Backwards compatibility exports
get_session = get_db_session
DatabaseManager = UnifiedDatabaseManager