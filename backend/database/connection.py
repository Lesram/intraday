"""
Database connection utilities.
Compatibility module for tests that expect backend.database.connection
"""

from backend.database import DatabaseManager, get_database

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
