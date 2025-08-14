"""
Database schema creation utility for tests.
Creates tables dynamically for testing purposes.
"""

from sqlalchemy.ext.asyncio import AsyncEngine

from backend.infra.schemas import Base


async def create_all_tables(engine: AsyncEngine) -> None:
    """Create all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_all_tables(engine: AsyncEngine) -> None:
    """Drop all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
