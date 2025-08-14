"""
Database Manager Module

Provides unified database management interface for the intraday trading platform.
This module wraps the existing db.py functionality with additional management capabilities.
"""

"""
Database Manager Module

Provides unified database management interface for the intraday trading platform.
This module wraps the existing db.py functionality with additional management capabilities.
"""

from backend.infra.db import (
    get_session_from,
    get_session,
    init_db,
    get_engine,
    get_sessionmaker,
    close_db,
    db_health_check,
)

# Simple class wrapper for compatibility
class DatabaseManager:
    """Simple wrapper class for database management compatibility."""
    
    @staticmethod
    def get_engine():
        return get_engine()
    
    @staticmethod
    def get_sessionmaker():
        return get_sessionmaker()
    
    @staticmethod
    def init_db(database_url=None):
        return init_db(database_url)
    
    @staticmethod
    async def close_db():
        return await close_db()
    
    @staticmethod
    async def db_health_check():
        return await db_health_check()

__all__ = [
    "DatabaseManager",
    "get_session_from",
    "get_session",
    "init_db",
    "get_engine", 
    "get_sessionmaker",
    "close_db",
    "db_health_check",
]
