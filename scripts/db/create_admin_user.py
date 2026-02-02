#!/usr/bin/env python3
"""
Admin User Creation Script

This script creates an admin user in the database with credentials from environment variables.
Run this script once during initial deployment or when you need to reset admin credentials.

Usage:
    # Using environment variables
    export ADMIN_USERNAME=admin
    export ADMIN_PASSWORD=your_strong_password
    python scripts/create_admin_user.py

    # Or with command-line arguments
    python scripts/create_admin_user.py --username admin --password your_strong_password

Security Notes:
- Password must be at least 12 characters
- Password will be hashed using bcrypt before storage
- Script will fail if user already exists (use --force to recreate)
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
from backend.infra.db import init_db
from backend.infra.users import UserRepository
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


async def create_admin_user(
    username: str,
    password: str,
    force: bool = False,
    roles: list[str] = None
) -> bool:
    """
    Create an admin user in the database.

    Args:
        username: Admin username
        password: Admin password (plain text, will be hashed)
        force: If True, delete existing user and recreate
        roles: List of roles (default: ["admin", "trader"])

    Returns:
        True if user created successfully, False otherwise
    """
    if roles is None:
        roles = ["admin", "trader"]

    # Validate password strength
    if len(password) < 12:
        logger.error("Password must be at least 12 characters long")
        return False

    # Get database URL from environment
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"
    )

    logger.info(f"Initializing database connection: {database_url.split('@')[1] if '@' in database_url else 'local'}")

    # Initialize database
    try:
        engine, sessionmaker = init_db(database_url)
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False

    # Create user
    async with sessionmaker() as session:
        user_repo = UserRepository(db_session=session)

        try:
            # Check if user exists
            existing_user = await user_repo.get_user(username)

            if existing_user:
                if force:
                    logger.warning(f"User '{username}' already exists. Force flag set, deleting and recreating...")
                    # Delete and recreate (simplified - in production you might want UPDATE)
                    from sqlalchemy import text
                    await session.execute(text("DELETE FROM users WHERE username = :username"), {"username": username})
                    await session.commit()
                else:
                    logger.error(f"User '{username}' already exists. Use --force to recreate.")
                    return False

            # Create user (use bcrypt hashing in production)
            logger.info(f"Creating admin user: {username}")
            user = await user_repo.create_user(
                username=username,
                password=password,
                roles=roles,
                use_fast_hash=False  # Use bcrypt for production security
            )

            logger.info(f"✅ Admin user created successfully: {user.username}")
            logger.info(f"   Roles: {', '.join(user.roles)}")
            logger.info(f"   Status: {'Active' if user.is_active else 'Inactive'}")
            logger.info("")
            logger.info("⚠️  IMPORTANT: Store credentials securely!")
            logger.info(f"   Username: {username}")
            logger.info(f"   Password: (hidden for security)")
            
            return True

        except ValueError as e:
            logger.error(f"Failed to create user: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # Close engine
            await engine.dispose()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create admin user for algorithmic trading platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using environment variables
  export ADMIN_USERNAME=admin
  export ADMIN_PASSWORD=MyStr0ng!P@ssw0rd
  python scripts/create_admin_user.py

  # Using command-line arguments
  python scripts/create_admin_user.py --username admin --password MyStr0ng!P@ssw0rd

  # Force recreate existing user
  python scripts/create_admin_user.py --force

  # Custom roles
  python scripts/create_admin_user.py --roles admin,trader,developer
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
        help="Admin password (default: from ADMIN_PASSWORD env var)"
    )
    parser.add_argument(
        "--roles",
        type=str,
        default="admin,trader",
        help="Comma-separated list of roles (default: admin,trader)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force recreate user if already exists"
    )

    args = parser.parse_args()

    # Get credentials from args or environment
    username = args.username or os.getenv("ADMIN_USERNAME")
    password = args.password or os.getenv("ADMIN_PASSWORD")
    roles = [role.strip() for role in args.roles.split(",")]

    # Validate inputs
    if not username:
        print("ERROR: Username not provided. Use --username or set ADMIN_USERNAME environment variable.")
        sys.exit(1)

    if not password:
        print("ERROR: Password not provided. Use --password or set ADMIN_PASSWORD environment variable.")
        sys.exit(1)

    # Security warning for command-line password
    if args.password:
        print("⚠️  WARNING: Password provided via command-line is visible in process list!")
        print("   Consider using environment variables instead.")
        print("")

    # Run async creation
    success = asyncio.run(create_admin_user(
        username=username,
        password=password,
        force=args.force,
        roles=roles
    ))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
