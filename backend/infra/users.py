"""
In-memory user repository for authentication.
This will be replaced with database persistence in B2.3.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel

from backend.infra.security import hash_password, verify_password


class User(BaseModel):
    """User model for authentication."""
    
    username: str
    hashed_password: str
    roles: List[str]
    is_active: bool = True


class UserRepository:
    """In-memory user repository."""
    
    def __init__(self):
        """Initialize with empty user store."""
        self._users: Dict[str, User] = {}
    
    def create_user(self, username: str, password: str, roles: List[str]) -> User:
        """
        Create a new user.
        
        Args:
            username: Unique username
            password: Plain text password (will be hashed)
            roles: List of user roles
            
        Returns:
            Created user
            
        Raises:
            ValueError: If username already exists
        """
        if username in self._users:
            raise ValueError(f"User '{username}' already exists")
        
        user = User(
            username=username,
            hashed_password=hash_password(password),
            roles=roles
        )
        
        self._users[username] = user
        return user
    
    def get_user(self, username: str) -> Optional[User]:
        """
        Get a user by username.
        
        Args:
            username: Username to lookup
            
        Returns:
            User if found, None otherwise
        """
        return self._users.get(username)
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
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
    
    def update_user_roles(self, username: str, roles: List[str]) -> bool:
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
    
    def list_users(self) -> List[User]:
        """
        List all users.
        
        Returns:
            List of all users
        """
        return list(self._users.values())


# Global user repository instance
_user_repo: Optional[UserRepository] = None


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
    if not settings.security_dev_mode:
        return
    
    repo = _user_repo
    if not repo:
        return
    
    # Create default admin user for development
    try:
        admin_user = repo.create_user(
            username="admin",
            password="admin",  # Simple password for development
            roles=["admin", "trader"]
        )
        print(f"Created dev admin user: {admin_user.username}")
    except ValueError:
        # User already exists
        pass
    
    # Create trader user for development
    try:
        trader_user = repo.create_user(
            username="trader",
            password="trader123",
            roles=["trader"]
        )
        print(f"Created dev trader user: {trader_user.username}")
    except ValueError:
        # User already exists
        pass
    
    # Create read-only user for development
    try:
        readonly_user = repo.create_user(
            username="viewer",
            password="viewer123",
            roles=["read-only"]
        )
        print(f"Created dev read-only user: {readonly_user.username}")
    except ValueError:
        # User already exists
        pass
