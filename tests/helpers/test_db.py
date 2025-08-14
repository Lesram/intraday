"""Test database utilities for SQLite testing."""

import tempfile
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.infra.db import init_db


class TestDatabase:
    """Manages SQLite test database lifecycle."""
    
    def __init__(self):
        self.temp_dir = None
        self.db_path = None
        self.engine = None
        self.sessionmaker = None
        
    def create_temp_db(self) -> str:
        """Create temporary SQLite database file and return URL."""
        # Create temporary directory
        self.temp_dir = tempfile.mkdtemp()
        
        # Create SQLite database path
        self.db_path = Path(self.temp_dir) / "test.db"
        
        # Return SQLite URL
        return f"sqlite+aiosqlite:///{self.db_path}"
    
    async def initialize(self) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
        """Initialize test database and return engine/sessionmaker."""
        db_url = self.create_temp_db()
        self.engine, self.sessionmaker = init_db(database_url=db_url)
        return self.engine, self.sessionmaker
    
    async def cleanup(self):
        """Clean up database resources."""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.sessionmaker = None
        
        # Clean up temp files
        if self.db_path and self.db_path.exists():
            try:
                os.unlink(self.db_path)
            except OSError:
                pass  # File might already be deleted
                
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                os.rmdir(self.temp_dir)
            except OSError:
                pass  # Directory might not be empty


@asynccontextmanager
async def test_database() -> AsyncGenerator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]], None]:
    """
    Async context manager for test database.
    
    Usage:
        async with test_database() as (engine, sessionmaker):
            async with sessionmaker() as session:
                # Use session for testing
                pass
    """
    db = TestDatabase()
    try:
        engine, sessionmaker = await db.initialize()
        yield engine, sessionmaker
    finally:
        await db.cleanup()


@asynccontextmanager
async def test_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for test database session.
    
    Usage:
        async with test_session() as session:
            # Use session for testing
            pass
    """
    async with test_database() as (engine, sessionmaker):
        async with sessionmaker() as session:
            yield session
