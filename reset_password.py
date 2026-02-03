#!/usr/bin/env python
"""Reset admin password directly in the database."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def reset_admin_password():
    """Reset the admin@example.com password."""
    from passlib.context import CryptContext
    
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    new_hash = pwd_context.hash("Admin@123!")
    
    print(f"Generated hash: {new_hash[:20]}...")
    
    # Connect to database
    DATABASE_URL = "postgresql+asyncpg://trading:trading123@localhost:5432/algotrading"
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        # Update password
        result = await conn.execute(
            text("""
                UPDATE users 
                SET hashed_password = :hash, 
                    failed_login_attempts = 0, 
                    locked_until = NULL 
                WHERE username = :username
            """),
            {"hash": new_hash, "username": "admin@example.com"}
        )
        print(f"Updated {result.rowcount} row(s)")
        
        # Verify
        result = await conn.execute(
            text("SELECT username, hashed_password FROM users WHERE username = :username"),
            {"username": "admin@example.com"}
        )
        row = result.fetchone()
        if row:
            print(f"Verified: {row[0]} has hash starting with {row[1][:20]}...")
    
    await engine.dispose()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(reset_admin_password())
