"""
Database connection utilities.
Compatibility module for tests that expect backend.database.connection
"""

from backend.database import DatabaseManager, get_database
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

# For backward compatibility
connection = None

async def get_connection():
    """Get database connection"""
    return await get_database()

def initialize_connection():
    """Initialize database connection"""
    global connection
    connection = DatabaseManager()
    return connection


async def get_database_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency provider yielding an AsyncSession.

    Tests override this dependency; default implementation raises to avoid
    accidental usage without proper initialization.
    """
    raise RuntimeError("get_database_session must be overridden in tests or app startup")
