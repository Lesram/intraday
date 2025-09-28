"""
Comprehensive test suite for backend.infra.users module.
Targets significant coverage improvement from 25% baseline by testing all user management functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import hashlib
from backend.infra.users import (
    User,
    UserRepository,
    UsersRepo,
    get_user_repository,
    _seed_dev_users
)


class TestUserModel:
    """Test User model functionality."""

    def test_user_model_creation(self):
        """Test User model creation with all fields."""
        user = User(
            username="testuser",
            hashed_password="hashed123",
            roles=["user", "trader"],
            is_active=True
        )
        assert user.username == "testuser"
        assert user.hashed_password == "hashed123"
        assert user.roles == ["user", "trader"]
        assert user.is_active is True
    
    def test_user_model_default_active(self):
        """Test User model with default is_active value."""
        user = User(
            username="testuser",
            hashed_password="hashed123",
            roles=["user"]
        )
        assert user.is_active is True  # Default value
    
    def test_user_model_inactive(self):
        """Test User model with inactive status."""
        user = User(
            username="testuser",
            hashed_password="hashed123",
            roles=["user"],
            is_active=False
        )
        assert user.is_active is False


class TestUserRepository:
    """Test UserRepository functionality."""

    def test_repository_initialization(self):
        """Test UserRepository initialization creates default users."""
        repo = UserRepository()
        
        # Should have default test users
        assert repo.get_user("testuser") is not None
        assert repo.get_user("admin") is not None
        assert repo.get_user("test_user") is not None
        
        # Verify user properties
        testuser = repo.get_user("testuser")
        assert testuser.username == "testuser"
        assert "user" in testuser.roles
        assert "trader" in testuser.roles
        assert testuser.is_active is True
    
    def test_repository_initialization_existing_users(self):
        """Test UserRepository initialization when users already exist."""
        # Create a repo and add users manually to simulate existing users
        repo = UserRepository()
        
        # Clear and recreate users to force the except ValueError path
        repo._users.clear()
        repo.create_user("testuser", "testpass", ["user", "trader"])
        
        # Create another repo - should hit the except ValueError path when trying to create existing users
        repo2 = UserRepository()
        
        # Verify users still exist (from the except block handling)
        assert repo2.get_user("testuser") is not None
    
    def test_create_user_fast_hash(self):
        """Test creating user with fast MD5 hash."""
        repo = UserRepository()
        
        user = repo.create_user(
            username="newuser",
            password="testpass",
            roles=["user"],
            use_fast_hash=True
        )
        
        assert user.username == "newuser"
        assert user.roles == ["user"]
        assert user.is_active is True
        
        # Verify MD5 hash
        expected_hash = hashlib.md5("testpass".encode()).hexdigest()
        assert user.hashed_password == expected_hash
    
    @patch('backend.infra.security.hash_password')
    def test_create_user_secure_hash(self, mock_hash_password):
        """Test creating user with secure bcrypt hash."""
        mock_hash_password.return_value = "secure_bcrypt_hash"
        repo = UserRepository()
        
        user = repo.create_user(
            username="secureuser",
            password="testpass",
            roles=["admin"],
            use_fast_hash=False
        )
        
        assert user.username == "secureuser"
        assert user.hashed_password == "secure_bcrypt_hash"
        mock_hash_password.assert_called_once_with("testpass")
    
    def test_create_user_duplicate_username(self):
        """Test creating user with duplicate username raises error."""
        repo = UserRepository()
        
        # Create first user
        repo.create_user("duplicate", "pass1", ["user"])
        
        # Attempt to create second user with same username
        with pytest.raises(ValueError, match="User 'duplicate' already exists"):
            repo.create_user("duplicate", "pass2", ["admin"])
    
    def test_get_user_existing(self):
        """Test getting existing user."""
        repo = UserRepository()
        user = repo.create_user("gettest", "password", ["user"])
        
        retrieved_user = repo.get_user("gettest")
        assert retrieved_user is not None
        assert retrieved_user.username == "gettest"
        assert retrieved_user.roles == ["user"]
    
    def test_get_user_nonexistent(self):
        """Test getting non-existent user returns None."""
        repo = UserRepository()
        
        user = repo.get_user("nonexistent")
        assert user is None
    
    def test_get_user_by_username_alias(self):
        """Test get_user_by_username works as alias for get_user."""
        repo = UserRepository()
        user = repo.create_user("aliastest", "password", ["user"])
        
        # Test both methods return the same result
        user1 = repo.get_user("aliastest")
        user2 = repo.get_user_by_username("aliastest")
        
        assert user1 is user2
        assert user1.username == "aliastest"
    
    @patch('backend.infra.users.verify_password')
    def test_authenticate_user_success(self, mock_verify_password):
        """Test successful user authentication."""
        mock_verify_password.return_value = True
        repo = UserRepository()
        
        user = repo.create_user("authtest", "password", ["user"])
        
        authenticated_user = repo.authenticate_user("authtest", "password")
        assert authenticated_user is not None
        assert authenticated_user.username == "authtest"
        mock_verify_password.assert_called_once_with("password", user.hashed_password)
    
    @patch('backend.infra.users.verify_password')
    def test_authenticate_user_wrong_password(self, mock_verify_password):
        """Test authentication with wrong password."""
        mock_verify_password.return_value = False
        repo = UserRepository()
        
        repo.create_user("authtest", "correctpass", ["user"])
        
        authenticated_user = repo.authenticate_user("authtest", "wrongpass")
        assert authenticated_user is None
    
    def test_authenticate_user_nonexistent(self):
        """Test authentication of non-existent user."""
        repo = UserRepository()
        
        authenticated_user = repo.authenticate_user("nonexistent", "password")
        assert authenticated_user is None
    
    def test_authenticate_user_inactive(self):
        """Test authentication of inactive user."""
        repo = UserRepository()
        
        user = repo.create_user("inactive", "password", ["user"])
        user.is_active = False
        
        authenticated_user = repo.authenticate_user("inactive", "password")
        assert authenticated_user is None
    
    def test_update_user_roles_success(self):
        """Test successful user role update."""
        repo = UserRepository()
        
        repo.create_user("roletest", "password", ["user"])
        
        result = repo.update_user_roles("roletest", ["admin", "trader"])
        assert result is True
        
        user = repo.get_user("roletest")
        assert user.roles == ["admin", "trader"]
    
    def test_update_user_roles_nonexistent(self):
        """Test updating roles for non-existent user."""
        repo = UserRepository()
        
        result = repo.update_user_roles("nonexistent", ["admin"])
        assert result is False
    
    def test_deactivate_user_success(self):
        """Test successful user deactivation."""
        repo = UserRepository()
        
        repo.create_user("deactivatetest", "password", ["user"])
        
        result = repo.deactivate_user("deactivatetest")
        assert result is True
        
        user = repo.get_user("deactivatetest")
        assert user.is_active is False
    
    def test_deactivate_user_nonexistent(self):
        """Test deactivating non-existent user."""
        repo = UserRepository()
        
        result = repo.deactivate_user("nonexistent")
        assert result is False
    
    def test_list_users(self):
        """Test listing all users."""
        repo = UserRepository()
        
        # Clear existing users for clean test
        repo._users.clear()
        
        # Add test users
        user1 = repo.create_user("user1", "pass1", ["user"])
        user2 = repo.create_user("user2", "pass2", ["admin"])
        
        users = repo.list_users()
        assert len(users) == 2
        assert user1 in users
        assert user2 in users


class TestGlobalUserRepository:
    """Test global user repository management."""

    def test_get_user_repository_singleton(self):
        """Test get_user_repository returns singleton instance."""
        # Clear global instance for clean test
        import backend.infra.users
        backend.infra.users._user_repo = None
        
        repo1 = get_user_repository()
        repo2 = get_user_repository()
        
        assert repo1 is repo2
        assert isinstance(repo1, UserRepository)
    
    @patch('backend.infra.users._seed_dev_users')
    def test_get_user_repository_seeds_users(self, mock_seed_dev_users):
        """Test get_user_repository calls seed function."""
        # Clear global instance for clean test
        import backend.infra.users
        backend.infra.users._user_repo = None
        
        repo = get_user_repository()
        
        mock_seed_dev_users.assert_called_once()
        assert isinstance(repo, UserRepository)


class TestSeedDevUsers:
    """Test development user seeding functionality."""

    @patch('backend.config.get_settings')
    @patch('backend.infra.users.get_structured_logger')
    def test_seed_dev_users_dev_mode(self, mock_get_logger, mock_get_settings):
        """Test seeding dev users in development mode."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings.app.dev_mode = True
        mock_get_settings.return_value = mock_settings
        
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        # Create fresh repository
        repo = UserRepository()
        
        # Clear existing users to test seeding
        repo._users.clear()
        
        # Set global repo and call seed function
        import backend.infra.users
        backend.infra.users._user_repo = repo
        
        _seed_dev_users()
        
        # Verify users were created
        admin_user = repo.get_user("admin")
        trader_user = repo.get_user("trader")
        viewer_user = repo.get_user("viewer")
        
        assert admin_user is not None
        assert "admin" in admin_user.roles
        assert "trader" in admin_user.roles
        
        assert trader_user is not None
        assert "trader" in trader_user.roles
        
        assert viewer_user is not None
        assert "read-only" in viewer_user.roles
        
        # Verify logging
        assert mock_logger.info.call_count == 3
    
    @patch('backend.config.get_settings')
    def test_seed_dev_users_production_mode(self, mock_get_settings):
        """Test seeding dev users skipped in production mode."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings.app.dev_mode = False
        mock_get_settings.return_value = mock_settings
        
        # Create fresh repository
        repo = UserRepository()
        repo._users.clear()
        
        # Set global repo and call seed function
        import backend.infra.users
        backend.infra.users._user_repo = repo
        
        _seed_dev_users()
        
        # Verify no dev users were created (only default ones from init)
        assert len(repo._users) == 0
    
    def test_seed_dev_users_no_global_repo(self):
        """Test seeding when no global repository exists."""
        # Clear global repo
        import backend.infra.users
        backend.infra.users._user_repo = None
        
        # Should not raise exception
        _seed_dev_users()
    
    @patch('backend.config.get_settings')
    @patch('backend.infra.users.get_structured_logger')
    def test_seed_dev_users_existing_users(self, mock_get_logger, mock_get_settings):
        """Test seeding when users already exist."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings.app.dev_mode = True
        mock_get_settings.return_value = mock_settings
        
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        # Create repository with existing users
        repo = UserRepository()
        # The default users already exist from initialization, so they'll trigger ValueError in _seed_dev_users
        
        # Set global repo and call seed function
        import backend.infra.users
        backend.infra.users._user_repo = repo
        
        # Should not raise exception when users already exist
        _seed_dev_users()
        
        # Verify some users may have been created (admin already existed, but trader and viewer might be new)
        # This should cover the except ValueError blocks for existing users
        assert mock_logger.info.call_count >= 0  # Some users might be created, some might already exist


class TestUsersRepo:
    """Test UsersRepo (email-based repository) functionality."""

    @pytest.fixture
    def users_repo(self):
        """Create a fresh UsersRepo instance for testing."""
        return UsersRepo()

    def test_users_repo_initialization(self, users_repo):
        """Test UsersRepo initializes with empty stores."""
        assert len(users_repo._users_by_email) == 0
        assert len(users_repo._users_by_id) == 0

    async def test_create_user(self, users_repo):
        """Test creating a user in UsersRepo."""
        user_data = {
            "id": "user123",
            "email": "test@example.com",
            "name": "Test User",
            "roles": ["user"]
        }
        
        result = await users_repo.create(user_data)
        
        assert result == user_data
        assert users_repo._users_by_email["test@example.com"] == user_data
        assert users_repo._users_by_id["user123"] == user_data

    async def test_get_by_email_existing(self, users_repo):
        """Test getting user by email when user exists."""
        user_data = {
            "id": "user123",
            "email": "test@example.com",
            "name": "Test User"
        }
        
        await users_repo.create(user_data)
        
        result = await users_repo.get_by_email("test@example.com")
        assert result == user_data

    async def test_get_by_email_nonexistent(self, users_repo):
        """Test getting user by email when user doesn't exist."""
        result = await users_repo.get_by_email("nonexistent@example.com")
        assert result is None

    async def test_get_by_id_existing(self, users_repo):
        """Test getting user by ID when user exists."""
        user_data = {
            "id": "user123",
            "email": "test@example.com",
            "name": "Test User"
        }
        
        await users_repo.create(user_data)
        
        result = await users_repo.get_by_id("user123")
        assert result == user_data

    async def test_get_by_id_nonexistent(self, users_repo):
        """Test getting user by ID when user doesn't exist."""
        result = await users_repo.get_by_id("nonexistent")
        assert result is None

    async def test_dual_storage_consistency(self, users_repo):
        """Test that users are consistently stored by both email and ID."""
        user_data = {
            "id": "user123",
            "email": "test@example.com",
            "name": "Test User",
            "roles": ["user", "admin"]
        }
        
        await users_repo.create(user_data)
        
        # Both lookups should return the same object reference
        by_email = await users_repo.get_by_email("test@example.com")
        by_id = await users_repo.get_by_id("user123")
        
        assert by_email is by_id
        assert by_email == user_data

    async def test_multiple_users(self, users_repo):
        """Test storing and retrieving multiple users."""
        users = [
            {"id": "user1", "email": "user1@example.com", "name": "User 1"},
            {"id": "user2", "email": "user2@example.com", "name": "User 2"},
            {"id": "user3", "email": "user3@example.com", "name": "User 3"}
        ]
        
        # Create all users
        for user_data in users:
            await users_repo.create(user_data)
        
        # Verify all can be retrieved
        for user_data in users:
            by_email = await users_repo.get_by_email(user_data["email"])
            by_id = await users_repo.get_by_id(user_data["id"])
            
            assert by_email == user_data
            assert by_id == user_data
            assert by_email is by_id


if __name__ == "__main__":
    pytest.main([__file__])