"""backend.infra.users

Database-backed user repository for authentication with brute force protection.

Note: Some test environments use SQLite. SQLite frequently returns JSON/text
columns (e.g., roles) as strings, and timestamps as ISO strings. The repository
normalizes these shapes so authentication works consistently across DB backends.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.security import (
    credential_fingerprint,
    hash_password,
    revoke_credential_fingerprint,
    verify_password,
)
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)

# bcrypt (cost 12, roughly 0.3 s per call) runs in this small dedicated pool,
# never on the event loop that also runs the trading scheduler. Two workers
# bound the CPU a burst of logins can take; further calls queue.
_PASSWORD_HASH_WORKERS = 2
_password_hash_executor: ThreadPoolExecutor | None = None


async def _run_password_hash(func, *args):
    """Run a bcrypt hash or verify call in the password-hash thread pool."""
    global _password_hash_executor
    if _password_hash_executor is None:
        _password_hash_executor = ThreadPoolExecutor(
            max_workers=_PASSWORD_HASH_WORKERS, thread_name_prefix="password-hash",
        )
    return await asyncio.get_running_loop().run_in_executor(_password_hash_executor, func, *args)


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
            email: User email address (required with a database: users.email
                is NOT NULL and unique)
            use_fast_hash: DEPRECATED - Ignored for security. Always uses bcrypt.

        Returns:
            Created user

        Raises:
            ValueError: If username already exists, the email is missing (with a
                database), or the password exceeds bcrypt's 72-byte limit.
                Raised before any database write.

        Security:
            SECURITY FIX (C-02): MD5 hashing removed. Always uses bcrypt.
        """
        if self._db and not (isinstance(email, str) and email.strip()):
            raise ValueError("An email address is required to create a user")

        # Check if user exists
        existing = await self.get_user(username)
        if existing:
            raise ValueError(f"User '{username}' already exists")

        # SECURITY FIX (C-02): Always use bcrypt, ignore use_fast_hash parameter
        # MD5 is cryptographically broken and was removed
        if use_fast_hash:
            logger.warning("use_fast_hash parameter is deprecated and ignored for security")
        hashed_password = await _run_password_hash(hash_password, password)

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
                row = result.fetchone()
                await self._db.commit()

                return User(
                    id=row[0],
                    username=row[1],
                    email=row[2],
                    hashed_password=row[3],
                    roles=self._normalize_roles(row[4]),
                    is_active=bool(row[5]),
                    failed_login_attempts=row[6] or 0,
                    locked_until=self._normalize_datetime(row[7]),
                    last_login=self._normalize_datetime(row[8]),
                )
            except Exception as e:
                await self._db.rollback()
                # Exception text can embed the bound parameters (the new hash).
                logger.error("Failed to create user: %s", type(e).__name__)
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

        Every attempt is first counted as a failure by one atomic UPDATE that
        also performs the lock check (_reserve_login_attempt), and the bcrypt
        check only runs for attempts that were counted. Concurrent wrong
        passwords therefore cannot all reach the bcrypt check: at most
        MAX_FAILED_ATTEMPTS run before the account is locked for
        LOCKOUT_DURATION_MINUTES. A correct password resets the counter. Once a
        lock has expired the counter restarts and the correct password is
        accepted again.

        Args:
            username: Username
            password: Plain text password

        Returns:
            User if authentication successful, None otherwise
        """
        user = await self.get_user(username)
        if not user or not user.is_active:
            return None

        attempt = await self._reserve_login_attempt(username)
        if attempt is None:
            logger.warning(
                "Login attempt for locked account: %s", username,
                extra={"username": username},
            )
            return None
        attempt_number, current_hash = attempt

        # Verify password (off the event loop) against the hash read by the
        # same statement that counted the attempt.
        password_valid = await _run_password_hash(verify_password, password, current_hash)

        if password_valid:
            # Successful login - reset failed attempts and update last login
            await self._reset_failed_attempts(username)
            await self._update_last_login(username)
            if current_hash != user.hashed_password:
                user = user.model_copy(update={"hashed_password": current_hash})
            return user
        if attempt_number >= self.MAX_FAILED_ATTEMPTS:
            logger.warning(
                "Account locked due to failed login attempts: %s", username,
                extra={"username": username, "failed_attempts": attempt_number},
            )
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

    async def _reserve_login_attempt(self, username: str) -> tuple[int, str] | None:
        """Count a password attempt before it is checked.

        One UPDATE checks the lock and increments failed_login_attempts
        atomically (the row lock serializes concurrent attempts), restarting
        the counter when a previous lock has expired. The attempt that reaches
        MAX_FAILED_ATTEMPTS sets locked_until in the same transaction, so later
        attempts are refused without a password check. A successful check
        resets the counter (_reset_failed_attempts).

        Returns:
            (attempt number, current password hash), or None when the account
            is locked or missing, or the attempt could not be recorded (the
            password is then not checked).
        """
        now = datetime.now(UTC)
        lock_until = now + timedelta(minutes=self.LOCKOUT_DURATION_MINUTES)
        if not self._db:
            user = self._users.get(username)
            if user is None or (user.locked_until is not None and user.locked_until > now):
                return None
            if user.locked_until is not None:  # lock expired: start counting again
                user.failed_login_attempts, user.locked_until = 0, None
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= self.MAX_FAILED_ATTEMPTS:
                user.locked_until = lock_until
            return user.failed_login_attempts, user.hashed_password
        try:
            result = await self._db.execute(
                text("""
                    UPDATE users
                    SET failed_login_attempts = CASE
                            WHEN locked_until IS NOT NULL AND locked_until <= :now THEN 1
                            ELSE COALESCE(failed_login_attempts, 0) + 1
                        END,
                        locked_until = CASE
                            WHEN locked_until IS NOT NULL AND locked_until <= :now THEN NULL
                            ELSE locked_until
                        END
                    WHERE username = :username
                      AND (locked_until IS NULL OR locked_until <= :now)
                    RETURNING failed_login_attempts, hashed_password
                """),
                {"now": now, "username": username},
            )
            row = result.fetchone()
            if row is not None and int(row[0] or 0) >= self.MAX_FAILED_ATTEMPTS:
                await self._db.execute(
                    text("UPDATE users SET locked_until = :locked_until WHERE username = :username"),
                    {"locked_until": lock_until, "username": username},
                )
            await self._db.commit()
        except SQLAlchemyError as e:
            await self._db.rollback()
            logger.error("Failed to record login attempt: %s", type(e).__name__)
            return None
        if row is None:
            return None
        return int(row[0] or 0), row[1]

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

        The current-password check counts toward the login lockout like a
        login attempt. After a change, every token issued under the previous
        password is revoked (refresh compares the credential fingerprint with
        the database; access tokens are rejected via the revoked fingerprint).
        """
        # Get user and verify current password
        user = await self.get_user(username)
        if not user or not user.is_active:
            logger.warning("Password change failed: user not found or inactive: %s", username)
            return False

        attempt = await self._reserve_login_attempt(username)
        if attempt is None:
            logger.warning("Password change refused: account locked: %s", username)
            return False
        _, current_hash = attempt

        # Verify current password
        if not await _run_password_hash(verify_password, current_password, current_hash):
            logger.warning("Password change failed: incorrect current password for user: %s", username)
            return False
        await self._reset_failed_attempts(username)

        # Hash new password (ValueError above bcrypt's 72-byte limit)
        new_hashed_password = await _run_password_hash(hash_password, new_password)

        if self._db:
            try:
                # Only replace the hash that was just verified.
                query = text("""
                    UPDATE users
                    SET hashed_password = :hashed_password
                    WHERE username = :username AND hashed_password = :current_hash
                """)
                result = await self._db.execute(
                    query,
                    {"hashed_password": new_hashed_password, "username": username,
                     "current_hash": current_hash}
                )
                await self._db.commit()
            except SQLAlchemyError as e:
                await self._db.rollback()
                logger.error("Failed to change password: %s", type(e).__name__)
                return False
            if result.rowcount != 1:
                return False
        else:
            # In-memory fallback
            user.hashed_password = new_hashed_password
        await revoke_credential_fingerprint(credential_fingerprint(username, current_hash))
        logger.info("Password changed successfully for user: %s", username)
        return True

    async def set_password(
        self,
        username: str,
        new_password: str,
        *,
        roles: list[str] | None = None,
        activate: bool = True,
    ) -> bool:
        """Replace a user's password in place (administrative reset).

        One UPDATE in one transaction: the row (id, email, foreign-key data) is
        kept, the lockout is cleared, and optionally the roles are replaced and
        the account is (re)activated. The new password is hashed before the
        database is touched, so a ValueError (over bcrypt's 72-byte limit)
        leaves the row unchanged. Tokens issued under the previous password
        stop working (see change_password).

        The UPDATE replaces only the hash read just before it (compare and
        swap, as in change_password). If a concurrent password change lands in
        between, the reset re-reads the account and tries again, up to three
        times, so the fingerprint it revokes is always the one it replaced.

        Returns:
            True if exactly one row was updated, False otherwise.
        """
        new_hashed_password = await _run_password_hash(hash_password, new_password)
        for _attempt in range(3):
            user = await self.get_user(username)
            if user is None:
                return False
            old_hash = user.hashed_password
            if not self._db:
                # No await between the read above and these writes.
                user.hashed_password = new_hashed_password
                user.failed_login_attempts, user.locked_until = 0, None
                if roles is not None:
                    user.roles = list(roles)
                if activate:
                    user.is_active = True
            else:
                assignments = [
                    "hashed_password = :hashed_password",
                    "failed_login_attempts = 0",
                    "locked_until = NULL",
                ]
                params: dict = {"hashed_password": new_hashed_password, "username": username,
                                "old_hash": old_hash}
                if roles is not None:
                    assignments.append("roles = :roles")
                    params["roles"] = list(roles)
                if activate:
                    assignments.append("is_active = TRUE")
                try:
                    # Fixed column assignments only; every value is a bound parameter.
                    result = await self._db.execute(
                        text(f"UPDATE users SET {', '.join(assignments)}"
                             " WHERE username = :username AND hashed_password = :old_hash"),
                        params,
                    )
                    if result.rowcount != 1:
                        await self._db.rollback()
                        continue  # the hash changed since it was read: re-read and retry
                    await self._db.commit()
                except SQLAlchemyError as e:
                    await self._db.rollback()
                    logger.error("Failed to set password: %s", type(e).__name__)
                    return False
            await revoke_credential_fingerprint(credential_fingerprint(username, old_hash))
            return True
        logger.warning("Password reset not applied for %s: the password kept changing during the reset",
                       username)
        return False

    async def deactivate_user(self, username: str) -> bool:
        """
        Deactivate a user account.

        Args:
            username: Username to deactivate

        Returns:
            True if deactivated successfully, False if user not found

        Tokens already issued to the user stop working: refresh requires an
        active account, and access tokens are rejected via the revoked
        credential fingerprint.
        """
        user = await self.get_user(username)
        if user is None:
            return False
        if self._db:
            try:
                query = text("""
                    UPDATE users
                    SET is_active = FALSE
                    WHERE username = :username
                """)
                result = await self._db.execute(query, {"username": username})
                await self._db.commit()
            except SQLAlchemyError as e:
                await self._db.rollback()
                logger.error("Failed to deactivate user: %s", type(e).__name__)
                return False
            if result.rowcount <= 0:
                return False
        else:
            user.is_active = False
        await revoke_credential_fingerprint(credential_fingerprint(username, user.hashed_password))
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
        # Log password through structured logging (never print to stdout)
        logger.debug(
            "Dev admin credentials generated — use reset_admin.py to retrieve",
            extra={"username": "admin"},
        )
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
        logger.debug("Dev trader credentials generated — use reset_admin.py to retrieve", extra={"username": "trader"})
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
        logger.debug("Dev viewer credentials generated — use reset_admin.py to retrieve", extra={"username": "viewer"})
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
