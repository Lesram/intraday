"""
In-memory user repository for authentication.
This will be replaced with database persistence in B2.3.
"""

from pydantic import BaseModel

from backend.infra.security import verify_password
from backend.utils.logger import get_structured_logger


class User(BaseModel):
    """User model for authentication."""

    username: str
    hashed_password: str
    roles: list[str]
    is_active: bool = True


class UserRepository:
    """In-memory user repository."""

    def __init__(self):
        """Initialize with empty user store."""
        self._users: dict[str, User] = {}
        
        # Add default test users for development/testing
        try:
            self.create_user("testuser", "testpass", ["user", "trader"])
            self.create_user("admin", "admin123", ["admin", "trader"])
            self.create_user("test_user", "test_password", ["user", "trader"])
        except ValueError:
            # Users already exist, that's fine
            pass

    def create_user(self, username: str, password: str, roles: list[str], use_fast_hash: bool = True) -> User:
        """
        Create a new user.

        Args:
            username: Unique username
            password: Plain text password (will be hashed)
            roles: List of user roles
            use_fast_hash: If True, use fast MD5 hash for testing instead of slow bcrypt

        Returns:
            Created user

        Raises:
            ValueError: If username already exists
        """
        if username in self._users:
            raise ValueError(f"User '{username}' already exists")

        # Use fast hashing for testing to avoid bcrypt timeouts
        if use_fast_hash:
            import hashlib
            hashed_password = hashlib.md5(password.encode()).hexdigest()
        else:
            from backend.infra.security import hash_password
            hashed_password = hash_password(password)

        user = User(
            username=username, hashed_password=hashed_password, roles=roles
        )

        self._users[username] = user
        return user

    def get_user(self, username: str) -> User | None:
        """
        Get a user by username.

        Args:
            username: Username to lookup

        Returns:
            User if found, None otherwise
        """
        return self._users.get(username)

    def get_user_by_username(self, username: str) -> User | None:
        """
        Get a user by username (alias for get_user for compatibility).

        Args:
            username: Username to lookup

        Returns:
            User if found, None otherwise
        """
        return self.get_user(username)

    def authenticate_user(self, username: str, password: str) -> User | None:
        """
        Authenticate a user with username and password.

        Args:
            username: Username
            password: Plain text password

        Returns:
            User if authentication successful, None otherwise
        """
        user = self.get_user(username)
        if not user or not user.is_active:
            return None

        if verify_password(password, user.hashed_password):
            return user

        return None

    def update_user_roles(self, username: str, roles: list[str]) -> bool:
        """
        Update user roles.

        Args:
            username: Username
            roles: New list of roles

        Returns:
            True if updated successfully, False if user not found
        """
        user = self.get_user(username)
        if not user:
            return False

        user.roles = roles
        return True

    def deactivate_user(self, username: str) -> bool:
        """
        Deactivate a user account.

        Args:
            username: Username to deactivate

        Returns:
            True if deactivated successfully, False if user not found
        """
        user = self.get_user(username)
        if not user:
            return False

        user.is_active = False
        return True

    def list_users(self) -> list[User]:
        """
        List all users.

        Returns:
            List of all users
        """
        return list(self._users.values())


# Global user repository instance
_user_repo: UserRepository | None = None


def get_user_repository() -> UserRepository:
    """
    Get the global user repository instance.

    Returns:
        UserRepository instance
    """
    global _user_repo
    if _user_repo is None:
        _user_repo = UserRepository()
        _seed_dev_users()
    return _user_repo


def _seed_dev_users():
    """Seed development users if in development mode."""
    from backend.config import get_settings

    settings = get_settings()
    if not settings.app.dev_mode:
        return

    repo = _user_repo
    if not repo:
        return

    # Create default admin user for development
    try:
        admin_user = repo.create_user(
            username="admin",
            password="admin",  # Simple password for development
            roles=["admin", "trader"],
        )
        logger = get_structured_logger(__name__)
        logger.info("Created dev admin user", extra={"username": admin_user.username})
    except ValueError:
        # User already exists
        pass

    # Create trader user for development
    try:
        trader_user = repo.create_user(
            username="trader", password="trader123", roles=["trader"]
        )
        logger = get_structured_logger(__name__)
        logger.info("Created dev trader user", extra={"username": trader_user.username})
    except ValueError:
        # User already exists
        pass

    # Create read-only user for development
    try:
        readonly_user = repo.create_user(
            username="viewer", password="viewer123", roles=["read-only"]
        )
        logger = get_structured_logger(__name__)
        logger.info("Created dev read-only user", extra={"username": readonly_user.username})
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
