"""backend.infra.users

Database-backed user repository for authentication with brute force protection.

Note: Some test environments use SQLite. SQLite frequently returns JSON/text
columns (e.g., roles) as strings, and timestamps as ISO strings. The repository
normalizes these shapes so authentication works consistently across DB backends.
"""

from datetime import UTC, datetime, timedelta
import json

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.security import hash_password, verify_password
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


class User(BaseModel):
    """User model for authentication."""

    id: int | None = None
    username: str
    email: str | None = None
    hashed_password: str
    roles: list[str]
    is_active: bool = True
    failed_login_attempts: int = 0
    locked_until: datetime | None = None
    last_login: datetime | None = None


class UserRepository:
    """Database-backed user repository with brute force protection."""

    # Constants for brute force protection
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 15

    def __init__(self, db_session: AsyncSession | None = None):
        """
        Initialize with database session.

        Args:
            db_session: SQLAlchemy async session. If None, falls back to in-memory for testing.
        """
        self._db = db_session
        # Fallback in-memory storage for testing/development
        self._users: dict[str, User] = {}

        # H-05 FIX: Only create test users in development/test environments
        # Never create default credentials in production
        import os
        env = os.environ.get('ENVIRONMENT', 'development').lower()
        is_production = env in ('production', 'prod', 'staging')
        
        # Add default test users if no database AND not in production
        if not self._db and not is_production:
            try:
                self.create_user_sync("testuser", "testpass", ["user", "trader"])
                self.create_user_sync("test_user", "test_password", ["user", "trader"])
            except ValueError:
                pass
        elif not self._db and is_production:
            import logging
            logging.warning(
                "H-05 SECURITY: Skipping default test user creation in production. "
                "Ensure database is properly configured."
            )

    def create_user_sync(self, username: str, password: str, roles: list[str]) -> User:
        """Synchronous create user (for in-memory fallback only).
        
        SECURITY: Always uses bcrypt for password hashing.
        MD5 was removed due to critical security vulnerability (C-02).
        """
        if username in self._users:
            raise ValueError(f"User '{username}' already exists")

        # SECURITY FIX (C-02): Use bcrypt, never MD5
        hashed_password = hash_password(password)

        user = User(
            username=username,
            hashed_password=hashed_password,
            roles=roles
        )
        self._users[username] = user
        return user

    async def create_user(self, username: str, password: str, roles: list[str], email: str | None = None, use_fast_hash: bool = False) -> User:
        """
        Create a new user in the database.

        Args:
            username: Unique username
            password: Plain text password (will be hashed with bcrypt)
            roles: List of user roles
            email: User email address (optional)
            use_fast_hash: DEPRECATED - Ignored for security. Always uses bcrypt.

        Returns:
            Created user

        Raises:
            ValueError: If username already exists
        
        Security:
            SECURITY FIX (C-02): MD5 hashing removed. Always uses bcrypt.
        """
        # Check if user exists
        existing = await self.get_user(username)
        if existing:
            raise ValueError(f"User '{username}' already exists")

        # SECURITY FIX (C-02): Always use bcrypt, ignore use_fast_hash parameter
        # MD5 is cryptographically broken and was removed
        if use_fast_hash:
            logger.warning("use_fast_hash parameter is deprecated and ignored for security")
        hashed_password = hash_password(password)

        # Insert into database
        if self._db:
            try:
                query = text("""
                    INSERT INTO users (username, email, hashed_password, roles, is_active)
                    VALUES (:username, :email, :hashed_password, :roles, :is_active)
                    RETURNING id, username, email, hashed_password, roles, is_active, failed_login_attempts, locked_until, last_login
                """)
                result = await self._db.execute(
                    query,
                    {
                        "username": username,
                        "email": email,
                        "hashed_password": hashed_password,
                        "roles": roles,
                        "is_active": True
                    }
                )
                await self._db.commit()
                row = result.fetchone()

                return User(
                    id=row[0],
                    username=row[1],
                    email=row[2],
                    hashed_password=row[3],
                    roles=row[4],
                    is_active=row[5],
                    failed_login_attempts=row[6] or 0,
                    locked_until=row[7],
                    last_login=row[8]
                )
            except Exception as e:
                await self._db.rollback()
                logger.error(f"Failed to create user: {e}")
                raise
        else:
            # Fallback to in-memory
            user = User(
                username=username,
                hashed_password=hashed_password,
                roles=roles
            )
            self._users[username] = user
            return user

    async def get_user(self, username: str) -> User | None:
        """
        Get a user by username from database.

        Args:
            username: Username to lookup

        Returns:
            User if found, None otherwise
        """
        if self._db:
            try:
                query = text("""
                    SELECT id, username, email, hashed_password, roles, is_active,
                           failed_login_attempts, locked_until, last_login
                    FROM users
                    WHERE username = :username
                """)
                result = await self._db.execute(query, {"username": username})
                row = result.fetchone()

                if not row:
                    return None

                roles_value = self._normalize_roles(row[4])
                locked_until = self._normalize_datetime(row[7])
                last_login = self._normalize_datetime(row[8])

                return User(
                    id=row[0],
                    username=row[1],
                    email=row[2],
                    hashed_password=row[3],
                    roles=roles_value,
                    is_active=bool(row[5]),
                    failed_login_attempts=row[6] or 0,
                    locked_until=locked_until,
                    last_login=last_login,
                )
            except Exception as e:
                logger.error(f"Failed to get user: {e}")
                return None
        else:
            # Fallback to in-memory
            return self._users.get(username)

    def get_user_by_username(self, username: str) -> User | None:
        """
        Get a user by username (alias for get_user for compatibility).

        Args:
            username: Username to lookup

        Returns:
            User if found, None otherwise
        """
        # This is a sync method for backwards compatibility
        # In production, use async get_user() instead
        if not self._db:
            return self._users.get(username)
        # For DB-backed, this should not be called directly
        raise NotImplementedError("Use async get_user() for database-backed repository")

    async def authenticate_user(self, username: str, password: str) -> User | None:
        """
        Authenticate a user with username and password.
        Includes brute force protection with account lockout.

        Args:
            username: Username
            password: Plain text password

        Returns:
            User if authentication successful, None otherwise
        """
        user = await self.get_user(username)
        if not user or not user.is_active:
            return None

        # Check if account is locked
        if user.locked_until and user.locked_until > datetime.now(UTC):
            logger.warning(
                f"Login attempt for locked account: {username}",
                extra={
                    "username": username,
                    "locked_until": user.locked_until.isoformat()
                }
            )
            return None

        # Verify password
        password_valid = verify_password(password, user.hashed_password)

        if password_valid:
            # Successful login - reset failed attempts and update last login
            await self._reset_failed_attempts(username)
            await self._update_last_login(username)
            return user
        else:
            # Failed login - increment failed attempts
            await self._increment_failed_attempts(username)
            return None

    @staticmethod
    def _normalize_roles(value) -> list[str]:
        """Normalize DB roles column into list[str].

        Postgres may return ARRAY/JSON as Python list; SQLite often returns text.
        """
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, tuple):
            return [str(v) for v in value]
        if isinstance(value, str):
            text_value = value.strip()
            if not text_value:
                return []

            # Try JSON first (e.g., '["admin","trader"]')
            try:
                parsed = json.loads(text_value)
                if isinstance(parsed, list):
                    return [str(v) for v in parsed]
                if isinstance(parsed, str):
                    return [parsed]
            except Exception:
                pass

            # Fallback: comma-separated string
            if "," in text_value:
                return [part.strip() for part in text_value.split(",") if part.strip()]
            return [text_value]

        # Last resort
        return [str(value)]

    @staticmethod
    def _normalize_datetime(value) -> datetime | None:
        """Normalize DB timestamp column into datetime or None."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            text_value = value.strip()
            if not text_value:
                return None
            # Common ISO variants
            try:
                if text_value.endswith("Z"):
                    text_value = text_value[:-1] + "+00:00"
                return datetime.fromisoformat(text_value)
            except Exception:
                return None
        return None

    async def _increment_failed_attempts(self, username: str) -> None:
        """Increment failed login attempts and lock account if threshold exceeded."""
        if self._db:
            try:
                # Get current failed attempts
                query = text("SELECT failed_login_attempts FROM users WHERE username = :username")
                result = await self._db.execute(query, {"username": username})
                row = result.fetchone()

                if row:
                    failed_attempts = (row[0] or 0) + 1
                    locked_until = None

                    # Lock account if threshold exceeded
                    if failed_attempts >= self.MAX_FAILED_ATTEMPTS:
                        locked_until = datetime.now(UTC) + timedelta(minutes=self.LOCKOUT_DURATION_MINUTES)
                        logger.warning(
                            f"Account locked due to failed login attempts: {username}",
                            extra={
                                "username": username,
                                "failed_attempts": failed_attempts,
                                "locked_until": locked_until.isoformat()
                            }
                        )

                    # Update database
                    update_query = text("""
                        UPDATE users
                        SET failed_login_attempts = :attempts,
                            locked_until = :locked_until
                        WHERE username = :username
                    """)
                    await self._db.execute(
                        update_query,
                        {
                            "attempts": failed_attempts,
                            "locked_until": locked_until,
                            "username": username
                        }
                    )
                    await self._db.commit()
            except Exception as e:
                await self._db.rollback()
                logger.error(f"Failed to increment failed attempts: {e}")
        else:
            # In-memory fallback
            user = self._users.get(username)
            if user:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= self.MAX_FAILED_ATTEMPTS:
                    user.locked_until = datetime.now(UTC) + timedelta(minutes=self.LOCKOUT_DURATION_MINUTES)

    async def _reset_failed_attempts(self, username: str) -> None:
        """Reset failed login attempts after successful login."""
        if self._db:
            try:
                query = text("""
                    UPDATE users
                    SET failed_login_attempts = 0,
                        locked_until = NULL
                    WHERE username = :username
                """)
                await self._db.execute(query, {"username": username})
                await self._db.commit()
            except Exception as e:
                await self._db.rollback()
                logger.error(f"Failed to reset failed attempts: {e}")
        else:
            # In-memory fallback
            user = self._users.get(username)
            if user:
                user.failed_login_attempts = 0
                user.locked_until = None

    async def _update_last_login(self, username: str) -> None:
        """Update last login timestamp."""
        if self._db:
            try:
                query = text("""
                    UPDATE users
                    SET last_login = :last_login
                    WHERE username = :username
                """)
                await self._db.execute(
                    query,
                    {"last_login": datetime.now(UTC), "username": username}
                )
                await self._db.commit()
            except Exception as e:
                await self._db.rollback()
                logger.error(f"Failed to update last login: {e}")
        else:
            # In-memory fallback
            user = self._users.get(username)
            if user:
                user.last_login = datetime.now(UTC)

    async def update_user_roles(self, username: str, roles: list[str]) -> bool:
        """
        Update user roles.

        Args:
            username: Username
            roles: New list of roles

        Returns:
            True if updated successfully, False if user not found
        """
        if self._db:
            try:
                query = text("""
                    UPDATE users
                    SET roles = :roles
                    WHERE username = :username
                """)
                result = await self._db.execute(query, {"roles": roles, "username": username})
                await self._db.commit()
                return result.rowcount > 0
            except Exception as e:
                await self._db.rollback()
                logger.error(f"Failed to update user roles: {e}")
                return False
        else:
            user = self._users.get(username)
            if not user:
                return False
            user.roles = roles
            return True

    async def change_password(
        self, username: str, current_password: str, new_password: str
    ) -> bool:
        """
        Change user password after verifying current password.

        Args:
            username: Username
            current_password: Current password (for verification)
            new_password: New password to set

        Returns:
            True if password changed successfully, False if verification failed
        """
        # Get user and verify current password
        user = await self.get_user(username)
        if not user or not user.is_active:
            logger.warning(f"Password change failed: user not found or inactive: {username}")
            return False

        # Verify current password
        if not verify_password(current_password, user.hashed_password):
            logger.warning(f"Password change failed: incorrect current password for user: {username}")
            return False

        # Hash new password
        new_hashed_password = hash_password(new_password)

        if self._db:
            try:
                query = text("""
                    UPDATE users
                    SET hashed_password = :hashed_password
                    WHERE username = :username
                """)
                result = await self._db.execute(
                    query,
                    {"hashed_password": new_hashed_password, "username": username}
                )
                await self._db.commit()

                if result.rowcount > 0:
                    logger.info(f"Password changed successfully for user: {username}")
                    return True
                return False
            except Exception as e:
                await self._db.rollback()
                logger.error(f"Failed to change password: {e}")
                return False
        else:
            # In-memory fallback
            user.hashed_password = new_hashed_password
            logger.info(f"Password changed successfully for user: {username}")
            return True

    async def deactivate_user(self, username: str) -> bool:
        """
        Deactivate a user account.

        Args:
            username: Username to deactivate

        Returns:
            True if deactivated successfully, False if user not found
        """
        if self._db:
            try:
                query = text("""
                    UPDATE users
                    SET is_active = FALSE
                    WHERE username = :username
                """)
                result = await self._db.execute(query, {"username": username})
                await self._db.commit()
                return result.rowcount > 0
            except Exception as e:
                await self._db.rollback()
                logger.error(f"Failed to deactivate user: {e}")
                return False
        else:
            user = self._users.get(username)
            if not user:
                return False
            user.is_active = False
            return True

    async def list_users(self) -> list[User]:
        """
        List all users.

        Returns:
            List of all users
        """
        if self._db:
            try:
                query = text("""
                    SELECT id, username, email, hashed_password, roles, is_active,
                           failed_login_attempts, locked_until, last_login
                    FROM users
                """)
                result = await self._db.execute(query)
                rows = result.fetchall()

                return [
                    User(
                        id=row[0],
                        username=row[1],
                        email=row[2],
                        hashed_password=row[3],
                        roles=row[4],
                        is_active=row[5],
                        failed_login_attempts=row[6] or 0,
                        locked_until=row[7],
                        last_login=row[8]
                    )
                    for row in rows
                ]
            except Exception as e:
                logger.error(f"Failed to list users: {e}")
                return []
        else:
            return list(self._users.values())


# Global user repository instance
_user_repo: UserRepository | None = None


async def get_user_repository(db_session: AsyncSession | None = None) -> UserRepository:
    """
    Get the global user repository instance.

    Args:
        db_session: Optional database session. If provided, uses database backend.

    Returns:
        UserRepository instance
    """
    global _user_repo
    if _user_repo is None or (db_session and _user_repo._db is None):
        _user_repo = UserRepository(db_session)
        # Note: Admin user should be created via setup script or migration
        # Do not create default users automatically in production code
    return _user_repo


def get_user_repository_sync() -> UserRepository:
    """
    Get user repository for synchronous contexts (testing only).

    Returns:
        UserRepository instance without database
    """
    return UserRepository(db_session=None)


def _seed_dev_users():
    """Seed development users if in development mode.
    
    Security:
        H-05: Strong passwords are now generated instead of hardcoded weak ones.
        These are only for development/testing - never use in production.
    """
    import secrets
    
    from backend.config import get_settings

    settings = get_settings()
    if not settings.app.dev_mode:
        return

    repo = _user_repo
    if not repo:
        return
    
    # SECURITY FIX (H-05): Generate strong random passwords instead of hardcoded weak ones
    # Log them only once at startup so developers can use them
    logger = get_structured_logger(__name__)

    # Create default admin user for development
    try:
        # Generate a strong random password for dev (16 chars, alphanumeric)
        admin_password = secrets.token_urlsafe(12)  # ~16 chars
        admin_user = repo.create_user(
            username="admin",
            password=admin_password,
            roles=["admin", "trader"],
        )
        logger.info(
            "Created dev admin user", 
            extra={
                "username": admin_user.username,
                "password_hint": "Check startup logs or use reset_admin.py"
            }
        )
        # Only print password in dev mode startup
        print(f"[DEV] Admin user created - username: admin, password: {admin_password}")
    except ValueError:
        # User already exists
        pass

    # Create trader user for development
    try:
        trader_password = secrets.token_urlsafe(12)
        trader_user = repo.create_user(
            username="trader", password=trader_password, roles=["trader"]
        )
        logger.info("Created dev trader user", extra={"username": trader_user.username})
        print(f"[DEV] Trader user created - username: trader, password: {trader_password}")
    except ValueError:
        # User already exists
        pass

    # Create read-only user for development
    try:
        viewer_password = secrets.token_urlsafe(12)
        readonly_user = repo.create_user(
            username="viewer", password=viewer_password, roles=["read-only"]
        )
        logger.info("Created dev read-only user", extra={"username": readonly_user.username})
        print(f"[DEV] Viewer user created - username: viewer, password: {viewer_password}")
    except ValueError:
        # User already exists
        pass


class UsersRepo:
    """Email-based user repository for new API endpoints."""

    def __init__(self):
        """Initialize with empty user store."""
        self._users_by_email: dict[str, dict] = {}
        self._users_by_id: dict[str, dict] = {}

    async def get_by_email(self, email: str) -> dict | None:
        """Get user by email address."""
        return self._users_by_email.get(email)

    async def create(self, user_data: dict) -> dict:
        """Create a new user."""
        email = user_data["email"]
        user_id = user_data["id"]

        # Store by both email and ID for lookups
        self._users_by_email[email] = user_data
        self._users_by_id[user_id] = user_data

        return user_data

    async def get_by_id(self, user_id: str) -> dict | None:
        """Get user by ID."""
        return self._users_by_id.get(user_id)
