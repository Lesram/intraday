import argparse
import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.infra.security import hash_password


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create or reset an admin user in the configured database. "
            "Uses DATABASE_URL env var by default."
        )
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="Database URL (defaults to env DATABASE_URL)",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("ADMIN_USERNAME", "admin@example.com"),
        help="Admin username/email (default: admin@example.com)",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("ADMIN_PASSWORD", "Admin123!@#"),
        help="Admin password (default: Admin123!@#)",
    )
    return parser.parse_args()


async def ensure_admin_user(database_url: str, username: str, password: str) -> None:
    if not database_url:
        raise SystemExit(
            "DATABASE_URL is required. Set env DATABASE_URL or pass --database-url."
        )

    hashed = hash_password(password)

    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        # If user exists, reset password and unlock.
        update = text(
            """
            UPDATE users
            SET hashed_password = :hashed,
                failed_login_attempts = 0,
                locked_until = NULL,
                is_active = TRUE
            WHERE username = :username
            """
        )
        result = await conn.execute(update, {"hashed": hashed, "username": username})

        # If no row updated, create the user.
        if getattr(result, "rowcount", 0) == 0:
            # Use ARRAY constructor for PostgreSQL array literal
            insert = text(
                """
                INSERT INTO users (
                    username, email, hashed_password, roles, is_active,
                    failed_login_attempts, locked_until, last_login
                ) VALUES (
                    :username, :email, :hashed_password, ARRAY['admin', 'trader']::varchar[], TRUE,
                    0, NULL, NULL
                )
                """
            )
            await conn.execute(
                insert,
                {
                    "username": username,
                    "email": username,
                    "hashed_password": hashed,
                },
            )

        check = text(
            """
            SELECT username, roles, is_active, failed_login_attempts, locked_until
            FROM users
            WHERE username = :username
            """
        )
        row = (await conn.execute(check, {"username": username})).fetchone()

    await engine.dispose()

    if not row:
        raise SystemExit("Failed to create/reset admin user (no row found after write).")

    print("Admin user is ready.")
    print(f"- username: {row[0]}")
    print(f"- roles: {row[1]}")
    print(f"- is_active: {row[2]}")
    print(f"- failed_login_attempts: {row[3]}")
    print(f"- locked_until: {row[4]}")


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(ensure_admin_user(args.database_url, args.username, args.password))
