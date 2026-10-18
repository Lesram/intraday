#!/usr/bin/env python3
"""
Admin User Creation / Password Reset Script

Creates an admin user, or resets an existing user's password in place.
Run it where ``DATABASE_URL`` points at the platform database (inside the api
container: ``docker compose -f docker-compose.paper.yml exec api ...``).

Usage:
    # Prompted for the password (not echoed, not kept in shell history)
    python scripts/db/create_admin_user.py --username admin --email admin@example.com

    # Non-interactive: credentials from the environment
    ADMIN_USERNAME=admin ADMIN_PASSWORD=... python scripts/db/create_admin_user.py

    # Reset an existing user's password in place
    python scripts/db/create_admin_user.py --username admin --force

Behaviour:
- New user: created with ``--roles`` (default admin,trader) and an email from
  ``--email`` / ``ADMIN_EMAIL`` (default: the username if it is an email
  address, else ``<username>@localhost``).
- Existing user: refused unless ``--force``. With ``--force`` the password is
  replaced in place by one UPDATE in one transaction: the row, its id, email
  and linked data are kept, the lockout is cleared and the account is active;
  roles change only when ``--roles`` is given. If anything fails, nothing is
  changed. Sessions issued under the old password stop working: refresh
  tokens at once, access tokens at once when ``REDIS_URL`` is reachable from
  this process (otherwise when they expire, at most 60 minutes).
- Password: at least 12 characters and at most 72 bytes of UTF-8 (bcrypt's
  limit; longer passwords are rejected, never truncated).
"""

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

# Repository root (scripts/db/ -> repo) so `backend` imports without PYTHONPATH.
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from sqlalchemy.exc import SQLAlchemyError

from backend.infra.db import init_db
from backend.infra.users import UserRepository
from backend.utils.log_redaction import safe_url

MIN_PASSWORD_LENGTH = 12
BCRYPT_MAX_PASSWORD_BYTES = 72
MAX_USERNAME_LENGTH = 50   # users.username VARCHAR(50)
MAX_EMAIL_LENGTH = 255     # users.email VARCHAR(255)
DEFAULT_ROLES = ["admin", "trader"]
REDIS_TIMEOUT_S = 1.0


def password_problem(password: str) -> str | None:
    """Return why ``password`` cannot be used, or None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
    size = len(password.encode("utf-8"))
    if size > BCRYPT_MAX_PASSWORD_BYTES:
        return (
            f"Password is {size} bytes in UTF-8, but bcrypt uses at most "
            f"{BCRYPT_MAX_PASSWORD_BYTES} bytes; longer passwords are rejected rather than "
            "truncated. Use a shorter password (at most 72 ASCII characters, fewer with "
            "non-ASCII characters)."
        )
    return None


def resolve_email(username: str, email: str | None) -> str:
    """Email for a new user: explicit value, else the username or <username>@localhost."""
    explicit = (email or "").strip()
    if explicit:
        return explicit
    return username if "@" in username else f"{username}@localhost"


def email_problem(email: str) -> str | None:
    """Return why ``email`` cannot be stored, or None."""
    local, sep, domain = email.partition("@")
    if not sep or not local or not domain or "@" in domain or any(c.isspace() for c in email):
        return f"Invalid email address: {email!r}"
    if len(email) > MAX_EMAIL_LENGTH:
        return f"Email address is longer than {MAX_EMAIL_LENGTH} characters."
    return None


async def _close_quietly(client) -> None:
    from redis.exceptions import RedisError

    try:
        await asyncio.wait_for(client.aclose(), timeout=REDIS_TIMEOUT_S)
    except (RedisError, OSError, RuntimeError, AttributeError):
        return  # best-effort cleanup of a client that is no longer used


async def _connect_revocation_store():
    """Point the token blacklist at Redis so a reset also revokes access tokens.

    Returns the client, or None when REDIS_URL is unset or unreachable.
    """
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    import redis.asyncio as redis_async
    from redis.exceptions import RedisError

    from backend.infra.security import init_token_blacklist

    client = redis_async.from_url(
        url, decode_responses=False,
        socket_timeout=REDIS_TIMEOUT_S, socket_connect_timeout=REDIS_TIMEOUT_S,
    )
    try:
        await asyncio.wait_for(client.ping(), timeout=3 * REDIS_TIMEOUT_S)
    except (RedisError, OSError):
        await _close_quietly(client)
        return None
    await init_token_blacklist(client)
    return client


async def create_admin_user(
    username: str,
    password: str,
    force: bool = False,
    roles: list[str] | None = None,
    email: str | None = None,
) -> bool:
    """
    Create a user, or with ``force`` reset an existing user's password in place.

    Args:
        username: Username
        password: Plain text password (hashed with bcrypt)
        force: Reset the password of an existing user (never deletes it)
        roles: Roles; default admin,trader for a new user, unchanged on reset
        email: Email for a new user (see resolve_email)

    Returns:
        True on success, False otherwise (nothing was changed)
    """
    problem = password_problem(password)
    if problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return False

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"
    )
    print(f"Database: {safe_url(database_url)}")
    try:
        engine, sessionmaker = init_db(database_url)
    except (SQLAlchemyError, ImportError, ValueError) as e:
        print(f"ERROR: cannot initialize the database connection ({type(e).__name__})",
              file=sys.stderr)
        return False

    redis_client = None
    try:
        async with sessionmaker() as session:
            repo = UserRepository(db_session=session)
            existing_user = await repo.get_user(username)

            if existing_user is None:
                if len(username) > MAX_USERNAME_LENGTH:
                    print(f"ERROR: username is longer than {MAX_USERNAME_LENGTH} characters.",
                          file=sys.stderr)
                    return False
                address = resolve_email(username, email)
                problem = email_problem(address)
                if problem:
                    print(f"ERROR: {problem}", file=sys.stderr)
                    return False
                user = await repo.create_user(
                    username=username,
                    password=password,
                    roles=roles or list(DEFAULT_ROLES),
                    email=address,
                )
                print(f"Created user {user.username!r} "
                      f"(roles: {', '.join(user.roles)}; email: {address}).")
                print("Store the credentials securely; the password is not shown.")
                return True

            if not force:
                print(f"ERROR: user {username!r} already exists. Re-run with --force to reset "
                      "its password in place (the account and its data are kept).",
                      file=sys.stderr)
                return False

            redis_client = await _connect_revocation_store()
            if not await repo.set_password(username, password, roles=roles, activate=True):
                print("ERROR: password reset failed; the user was not changed.", file=sys.stderr)
                return False
            print(f"Password reset in place for {username!r}: account, id, email and data "
                  "kept; lockout cleared; account active.")
            if roles is not None:
                print(f"Roles set to: {', '.join(roles)}")
            print("Refresh tokens issued under the previous password no longer work.")
            if redis_client is not None:
                print("Access tokens issued under the previous password are revoked.")
            else:
                print("Redis is not reachable from here: access tokens issued under the previous "
                      "password stay valid until they expire (at most 60 minutes).")
            return True

    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return False
    except SQLAlchemyError as e:
        # The exception text can embed SQL parameters, such as a password hash.
        print(f"ERROR: database operation failed ({type(e).__name__}); nothing was changed.",
              file=sys.stderr)
        return False
    finally:
        if redis_client is not None:
            await _close_quietly(redis_client)
        await engine.dispose()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create an admin user, or reset an existing user's password in place",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Prompted for the password
  python scripts/db/create_admin_user.py --username admin --email admin@example.com

  # Credentials from the environment
  export ADMIN_USERNAME=admin ADMIN_PASSWORD='...' ADMIN_EMAIL=admin@example.com
  python scripts/db/create_admin_user.py

  # Reset an existing user's password in place (account and data kept)
  python scripts/db/create_admin_user.py --username admin --force

  # Custom roles
  python scripts/db/create_admin_user.py --username ops --roles admin,trader,developer
        """
    )

    parser.add_argument(
        "--username",
        type=str,
        help="Admin username (default: from ADMIN_USERNAME env var)"
    )
    parser.add_argument(
        "--password",
        type=str,
        help="Admin password (discouraged: visible in the process list; default: "
             "ADMIN_PASSWORD env var, else an interactive prompt)"
    )
    parser.add_argument(
        "--email",
        type=str,
        help="Email for a new user (default: ADMIN_EMAIL env var, else the username if it "
             "is an email address, else <username>@localhost)"
    )
    parser.add_argument(
        "--roles",
        type=str,
        default=None,
        help="Comma-separated roles (new user default: admin,trader; --force keeps the "
             "existing roles unless given)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reset the password of an existing user in place (never deletes the user)"
    )

    args = parser.parse_args()

    username = args.username or os.getenv("ADMIN_USERNAME")
    if not username:
        print("ERROR: Username not provided. Use --username or set ADMIN_USERNAME environment variable.")
        sys.exit(1)

    password = args.password or os.getenv("ADMIN_PASSWORD")
    if args.password:
        print("WARNING: a password given on the command line is visible in the process list.")
        print("   Prefer the interactive prompt or the ADMIN_PASSWORD environment variable.")
        print("")
    if not password:
        if not sys.stdin.isatty():
            print("ERROR: Password not provided. Use ADMIN_PASSWORD or run interactively.")
            sys.exit(1)
        password = getpass.getpass("New password: ")
        if getpass.getpass("Repeat new password: ") != password:
            print("ERROR: the passwords do not match.")
            sys.exit(1)

    roles = None
    if args.roles:
        roles = [role.strip() for role in args.roles.split(",") if role.strip()]

    success = asyncio.run(create_admin_user(
        username=username,
        password=password,
        force=args.force,
        roles=roles,
        email=args.email or os.getenv("ADMIN_EMAIL"),
    ))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
