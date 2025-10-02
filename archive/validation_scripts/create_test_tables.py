"""
Initialize basic database tables for optimization testing
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from backend.database.database_config import db_config
from sqlalchemy import text


async def create_basic_tables():
    """Create basic tables for optimization testing."""
    
    engine = db_config.get_async_engine()
    
    async with engine.begin() as conn:
        # Create basic tables for testing
        # Drop existing table if it exists to update schema
        await conn.execute(text("DROP TABLE IF EXISTS orders"))
        
        await conn.execute(text("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                user_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        await conn.execute(text("DROP TABLE IF EXISTS positions"))
        
        await conn.execute(text("""
            CREATE TABLE positions (
                id INTEGER PRIMARY KEY,
                user_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                quantity REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        await conn.execute(text("DROP TABLE IF EXISTS daily_ledger"))
        
        await conn.execute(text("""
            CREATE TABLE daily_ledger (
                id INTEGER PRIMARY KEY,
                account_id TEXT NOT NULL,
                date DATE NOT NULL,
                daily_orders INTEGER DEFAULT 0,
                daily_notional_usd REAL DEFAULT 0.0
            )
        """))
        
        await conn.execute(text("DROP TABLE IF EXISTS order_events"))
        
        await conn.execute(text("""
            CREATE TABLE order_events (
                id INTEGER PRIMARY KEY,
                broker_order_id TEXT NOT NULL,
                event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL
            )
        """))
        
        await conn.execute(text("DROP TABLE IF EXISTS trades"))
        
        await conn.execute(text("""
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                price REAL NOT NULL,
                quantity REAL NOT NULL
            )
        """))
        
        print("✅ Basic tables created successfully")


if __name__ == "__main__":
    asyncio.run(create_basic_tables())