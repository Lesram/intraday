"""
Database connection and session management.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages database connections and sessions."""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = None
        self.session_maker = None
        self._is_healthy = False
    
    async def initialize(self):
        """Initialize the database engine and session maker."""
        try:
            self.engine = create_async_engine(
                self.database_url,
                echo=False,
                pool_pre_ping=True,
                pool_recycle=3600
            )
            self.session_maker = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            await self.health_check()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    async def health_check(self) -> bool:
        """Check database health."""
        if not self.engine:
            self._is_healthy = False
            return False
        
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            self._is_healthy = True
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            self._is_healthy = False
            return False
    
    @property
    def is_healthy(self) -> bool:
        """Get database health status."""
        return self._is_healthy
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        if not self.session_maker:
            raise RuntimeError("Database not initialized")
        
        async with self.session_maker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def close(self):
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed")

# Global database instance
db_manager: Optional[DatabaseManager] = None

async def get_database() -> DatabaseManager:
    """Get the global database manager."""
    global db_manager
    if not db_manager:
        raise RuntimeError("Database not initialized")
    return db_manager

async def init_database(database_url: str) -> DatabaseManager:
    """Initialize the global database manager."""
    global db_manager
    db_manager = DatabaseManager(database_url)
    await db_manager.initialize()
    return db_manager

async def close_database():
    """Close the global database manager."""
    global db_manager
    if db_manager:
        await db_manager.close()
        db_manager = None

# For backwards compatibility
from sqlalchemy import text

class Database:
    """Legacy database class for compatibility."""
    
    def __init__(self):
        self.is_connected = False
    
    async def connect(self):
        """Connect to database."""
        self.is_connected = True
    
    async def disconnect(self):
        """Disconnect from database."""
        self.is_connected = False
    
    async def health_check(self) -> bool:
        """Check database health."""
        return self.is_connected

# Default instance for import compatibility
database = Database()
