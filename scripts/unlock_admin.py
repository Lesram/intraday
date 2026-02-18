"""Unlock the admin account (reset failed login attempts and locked_until)."""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text


async def unlock():
    engine = create_async_engine(
        "postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"
    )
    async with engine.begin() as conn:
        r = await conn.execute(
            text("SELECT username, failed_login_attempts, locked_until FROM users WHERE username = 'admin'")
        )
        row = r.first()
        if row:
            print(f"Before: username={row[0]}, failed_attempts={row[1]}, locked_until={row[2]}")
        else:
            print("No admin user found")
            return

        await conn.execute(
            text("UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE username = 'admin'")
        )

        r = await conn.execute(
            text("SELECT username, failed_login_attempts, locked_until FROM users WHERE username = 'admin'")
        )
        row = r.first()
        print(f"After:  username={row[0]}, failed_attempts={row[1]}, locked_until={row[2]}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(unlock())
