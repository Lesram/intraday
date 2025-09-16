"""
Comprehensive test suite for backend.api.auth module
Tests authentication flows, JWT handling, and security validation
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from fastapi import HTTPException, status, Request
from fastapi.testclient import TestClient
import json

# Import authentication module
from backend.api.auth import (
    router,
    get_user_repo,
    get_security_current_user,
    hash_password,
    UserRegistrationRequest,
    UserRegistrationResponse,
    UserInfo,
    LoginResponse,
    get_current_user,
    create_test_user
)


class TestAuthModels:
    """Test authentication data models."""

    def test_user_registration_request_valid(self):
        """Test valid UserRegistrationRequest creation."""
        request = UserRegistrationRequest(
            email="test@example.com",
            password="validpass123"
        )
        
        assert request.email == "test@example.com"
        assert request.password == "validpass123"

    def test_user_registration_request_invalid_email(self):
        """Test UserRegistrationRequest with invalid email."""
        with pytest.raises(ValueError):
            UserRegistrationRequest(
                email="invalid-email",
                password="validpass123"
            )

    def test_user_registration_request_short_password(self):
        """Test UserRegistrationRequest with short password."""
        with pytest.raises(ValueError):
            UserRegistrationRequest(
                email="test@example.com",
                password="short"
            )

    def test_user_registration_request_long_password(self):
        """Test UserRegistrationRequest with too long password."""
        long_password = "a" * 129  # Exceeds 128 character limit
        with pytest.raises(ValueError):
            UserRegistrationRequest(
                email="test@example.com",
                password=long_password
            )

    def test_user_registration_response(self):
        """Test UserRegistrationResponse creation."""
        response = UserRegistrationResponse(
            user_id="user123",
            email="test@example.com"
        )
        
        assert response.user_id == "user123"
        assert response.email == "test@example.com"

    def test_user_info(self):
        """Test UserInfo model creation."""
        user_info = UserInfo(
            username="testuser",
            roles=["trader", "admin"]
        )
        
        assert user_info.username == "testuser"
        assert user_info.roles == ["trader", "admin"]

    def test_login_response(self):
        """Test LoginResponse model creation."""
        user_info = UserInfo(username="testuser", roles=["trader"])
        login_response = LoginResponse(
            access_token="test_token",
            token_type="bearer",
            expires_in=3600,
            user_id="user123",
            user=user_info
        )
        
        assert login_response.access_token == "test_token"
        assert login_response.token_type == "bearer"
        assert login_response.expires_in == 3600
        assert login_response.user_id == "user123"
        assert login_response.user.username == "testuser"


class TestAuthUtilities:
    """Test authentication utility functions."""

    def test_hash_password(self):
        """Test password hashing function."""
        password = "testpassword123"
        hashed = hash_password(password)
        
        assert hashed == f"hashed_{password}"
        assert hashed != password

    def test_hash_password_different_inputs(self):
        """Test password hashing with different inputs."""
        passwords = ["password1", "password2", "different_pass"]
        hashes = [hash_password(p) for p in passwords]
        
        # All hashes should be different
        assert len(set(hashes)) == len(passwords)

    def test_get_user_repo(self):
        """Test get_user_repo dependency function."""
        repo = get_user_repo()
        # Should return a UserRepository instance
        assert repo is not None

    def test_get_security_current_user(self):
        """Test get_security_current_user function."""
        current_user_func = get_security_current_user()
        assert current_user_func is not None

    @pytest.mark.asyncio
    async def test_get_current_user(self):
        """Test get_current_user mock function."""
        user = await get_current_user()
        
        assert user["user_id"] == "test_user_123"
        assert user["email"] == "test@example.com"
        assert "trader" in user["roles"]

    def test_create_test_user(self):
        """Test create_test_user utility function."""
        user = create_test_user()
        
        assert user["user_id"] == "test_user_123"
        assert user["email"] == "test@example.com"
        assert user["password_hash"] == "hashed_testpass123"
        assert "trader" in user["roles"]
        assert user["active"] is True


class TestLoginEndpoint:
    """Test login endpoint functionality."""

    @pytest.fixture
    def mock_user_repo(self):
        """Create mock user repository."""
        repo = Mock()
        repo.get_user_by_username.return_value = Mock(
            hashed_password="hashed_password123",
            is_active=True,
            roles=["trader"]
        )
        return repo

    @pytest.fixture
    def mock_request(self):
        """Create mock request object."""
        request = Mock(spec=Request)
        request.json = AsyncMock(return_value={
            "username": "testuser",
            "password": "testpass123"
        })
        return request

    @patch('backend.api.auth.get_user_repo')
    @patch('backend.infra.security.verify_password')
    @patch('backend.infra.security.create_access_token')
    @pytest.mark.asyncio
    async def test_login_form_data_success(self, mock_create_token, mock_verify_password, mock_get_repo):
        """Test successful login with form data."""
        # Setup mocks
        mock_user = Mock()
        mock_user.hashed_password = "hashed_password123"
        mock_user.is_active = True
        mock_user.roles = ["trader"]
        
        mock_repo = Mock()
        mock_repo.get_user_by_username.return_value = mock_user
        mock_get_repo.return_value = mock_repo
        
        mock_verify_password.return_value = True
        mock_create_token.return_value = "mock_access_token"
        
        mock_request = Mock(spec=Request)
        mock_request.json = AsyncMock(side_effect=Exception("No JSON"))
        
        # Import the login function
        from backend.api.auth import login
        
        # Call login function
        result = await login(
            request=mock_request,
            username="testuser",
            password="testpass123",
            user_repo=mock_repo
        )
        
        # Verify result
        assert isinstance(result, LoginResponse)
        assert result.access_token == "mock_access_token"
        assert result.token_type == "bearer"
        assert result.expires_in == 3600
        assert result.user_id == "testuser"
        assert result.user.username == "testuser"
        assert result.user.roles == ["trader"]
        
        # Verify calls
        mock_repo.get_user_by_username.assert_called_once_with("testuser")
        mock_verify_password.assert_called_once_with("testpass123", "hashed_password123")
        mock_create_token.assert_called_once_with("testuser", ["trader"])

    @patch('backend.api.auth.get_user_repo')
    @pytest.mark.asyncio
    async def test_login_json_body_success(self, mock_get_repo):
        """Test successful login with JSON body."""
        # Setup mocks
        mock_user = Mock()
        mock_user.hashed_password = "hashed_password123"
        mock_user.is_active = True
        mock_user.roles = ["trader"]
        
        mock_repo = Mock()
        mock_repo.get_user_by_username.return_value = mock_user
        mock_get_repo.return_value = mock_repo
        
        mock_request = Mock(spec=Request)
        mock_request.json = AsyncMock(return_value={
            "username": "testuser",
            "password": "testpass123"
        })
        
        with patch('backend.infra.security.verify_password', return_value=True), \
             patch('backend.infra.security.create_access_token', return_value="mock_token"):
            
            from backend.api.auth import login
            
            result = await login(
                request=mock_request,
                username=None,
                password=None,
                user_repo=mock_repo
            )
            
            assert isinstance(result, LoginResponse)
            assert result.access_token == "mock_token"

    @patch('backend.api.auth.get_user_repo')
    @pytest.mark.asyncio
    async def test_login_missing_credentials(self, mock_get_repo):
        """Test login with missing credentials."""
        mock_request = Mock(spec=Request)
        mock_request.json = AsyncMock(side_effect=Exception("No JSON"))
        
        from backend.api.auth import login
        
        with pytest.raises(HTTPException) as exc_info:
            await login(
                request=mock_request,
                username=None,
                password=None,
                user_repo=mock_get_repo.return_value
            )
        
        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "Username and password are required" in str(exc_info.value.detail)

    @patch('backend.api.auth.get_user_repo')
    @pytest.mark.asyncio
    async def test_login_user_not_found(self, mock_get_repo):
        """Test login with non-existent user."""
        mock_repo = Mock()
        mock_repo.get_user_by_username.return_value = None
        mock_get_repo.return_value = mock_repo
        
        mock_request = Mock(spec=Request)
        mock_request.json = AsyncMock(side_effect=Exception("No JSON"))
        
        from backend.api.auth import login
        
        with pytest.raises(HTTPException) as exc_info:
            await login(
                request=mock_request,
                username="nonexistent",
                password="password123",
                user_repo=mock_repo
            )
        
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid username or password" in str(exc_info.value.detail)

    @patch('backend.api.auth.get_user_repo')
    @patch('backend.infra.security.verify_password')
    @pytest.mark.asyncio
    async def test_login_invalid_password(self, mock_verify_password, mock_get_repo):
        """Test login with invalid password."""
        mock_user = Mock()
        mock_user.hashed_password = "hashed_password123"
        mock_user.is_active = True
        mock_user.roles = ["trader"]
        
        mock_repo = Mock()
        mock_repo.get_user_by_username.return_value = mock_user
        mock_get_repo.return_value = mock_repo
        
        mock_verify_password.return_value = False
        
        mock_request = Mock(spec=Request)
        mock_request.json = AsyncMock(side_effect=Exception("No JSON"))
        
        from backend.api.auth import login
        
        with pytest.raises(HTTPException) as exc_info:
            await login(
                request=mock_request,
                username="testuser",
                password="wrongpassword",
                user_repo=mock_repo
            )
        
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid username or password" in str(exc_info.value.detail)

    @patch('backend.api.auth.get_user_repo')
    @patch('backend.infra.security.verify_password')
    @pytest.mark.asyncio
    async def test_login_inactive_user(self, mock_verify_password, mock_get_repo):
        """Test login with inactive user."""
        mock_user = Mock()
        mock_user.hashed_password = "hashed_password123"
        mock_user.is_active = False  # Inactive user
        mock_user.roles = ["trader"]
        
        mock_repo = Mock()
        mock_repo.get_user_by_username.return_value = mock_user
        mock_get_repo.return_value = mock_repo
        
        mock_verify_password.return_value = True
        
        mock_request = Mock(spec=Request)
        mock_request.json = AsyncMock(side_effect=Exception("No JSON"))
        
        from backend.api.auth import login
        
        with pytest.raises(HTTPException) as exc_info:
            await login(
                request=mock_request,
                username="testuser",
                password="testpass123",
                user_repo=mock_repo
            )
        
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Account is disabled" in str(exc_info.value.detail)

    @patch('backend.api.auth.get_user_repo')
    @pytest.mark.asyncio
    async def test_login_internal_error(self, mock_get_repo):
        """Test login with internal server error."""
        mock_repo = Mock()
        mock_repo.get_user_by_username.side_effect = Exception("Database error")
        mock_get_repo.return_value = mock_repo
        
        mock_request = Mock(spec=Request)
        mock_request.json = AsyncMock(side_effect=Exception("No JSON"))
        
        from backend.api.auth import login
        
        with pytest.raises(HTTPException) as exc_info:
            await login(
                request=mock_request,
                username="testuser",
                password="testpass123",
                user_repo=mock_repo
            )
        
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Login failed" in str(exc_info.value.detail)


class TestRegisterEndpoint:
    """Test register endpoint functionality."""

    @patch('backend.api.auth.get_user_repo')
    @pytest.mark.asyncio
    async def test_register_success(self, mock_get_repo):
        """Test successful user registration."""
        mock_repo = Mock()
        mock_repo.user_exists.return_value = False
        mock_repo.create_user.return_value = {
            "user_id": "new_user_123",
            "email": "newuser@example.com"
        }
        mock_get_repo.return_value = mock_repo
        
        # Import register function
        from backend.api.auth import register
        
        request = UserRegistrationRequest(
            email="newuser@example.com",
            password="ValidPass123!"  # Strong password
        )
        
        result = await register(request, mock_repo)
        
        assert isinstance(result, UserRegistrationResponse)
        assert result.user_id == "new_user_123"
        assert result.email == "newuser@example.com"
        
        mock_repo.user_exists.assert_called_once_with("newuser@example.com")
        mock_repo.create_user.assert_called_once()

    @patch('backend.api.auth.get_user_repo')
    @pytest.mark.asyncio
    async def test_register_user_exists(self, mock_get_repo):
        """Test registration with existing user."""
        mock_repo = Mock()
        mock_repo.user_exists.return_value = True
        mock_get_repo.return_value = mock_repo
        
        from backend.api.auth import register
        
        request = UserRegistrationRequest(
            email="existing@example.com",
            password="ValidPass123!"  # Strong password
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await register(request, mock_repo)
        
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "Email already registered" in str(exc_info.value.detail)

    @patch('backend.api.auth.get_user_repo')
    @pytest.mark.asyncio
    async def test_register_weak_password(self, mock_get_repo):
        """Test registration with weak password."""
        mock_repo = Mock()
        mock_repo.user_exists.return_value = False
        mock_get_repo.return_value = mock_repo
        
        from backend.api.auth import register
        
        request = UserRegistrationRequest(
            email="test@example.com",
            password="weakpass"  # Weak password - no uppercase, numbers, special chars
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await register(request, mock_repo)
        
        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "Password validation failed" in str(exc_info.value.detail)

    @patch('backend.api.auth.get_user_repo')
    @pytest.mark.asyncio
    async def test_register_internal_error(self, mock_get_repo):
        """Test registration with internal error."""
        mock_repo = Mock()
        mock_repo.user_exists.side_effect = Exception("Database error")
        mock_get_repo.return_value = mock_repo
        
        from backend.api.auth import register
        
        request = UserRegistrationRequest(
            email="test@example.com",
            password="ValidPass123!"  # Strong password
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await register(request, mock_repo)
        
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Registration failed" in str(exc_info.value.detail)


class TestAuthRouter:
    """Test authentication router configuration."""

    def test_router_prefix(self):
        """Test router has correct prefix."""
        assert router.prefix == "/auth"

    def test_router_tags(self):
        """Test router has correct tags."""
        assert "authentication" in router.tags

    def test_router_routes(self):
        """Test router has expected routes."""
        route_paths = [route.path for route in router.routes]
        
        # Check for routes with /auth prefix
        assert "/auth/login" in route_paths or "/login" in route_paths
        assert "/auth/register" in route_paths or "/register" in route_paths

    def test_login_route_methods(self):
        """Test login route accepts POST method."""
        login_route = next((route for route in router.routes 
                           if "/login" in route.path), None)
        assert login_route is not None
        assert "POST" in login_route.methods

    def test_register_route_methods(self):
        """Test register route accepts POST method."""
        register_route = next((route for route in router.routes 
                              if "/register" in route.path), None)
        assert register_route is not None
        assert "POST" in register_route.methods


class TestAuthIntegration:
    """Test authentication module integration."""

    def test_all_imports_available(self):
        """Test all authentication components can be imported."""
        from backend.api.auth import (
            router, get_user_repo, hash_password,
            UserRegistrationRequest, UserRegistrationResponse,
            UserInfo, LoginResponse, get_current_user, create_test_user
        )
        
        assert router is not None
        assert get_user_repo is not None
        assert hash_password is not None
        assert UserRegistrationRequest is not None
        assert UserRegistrationResponse is not None
        assert UserInfo is not None
        assert LoginResponse is not None
        assert get_current_user is not None
        assert create_test_user is not None

    def test_model_serialization(self):
        """Test models can be serialized to JSON."""
        user_info = UserInfo(username="test", roles=["trader"])
        login_response = LoginResponse(
            access_token="token",
            token_type="bearer", 
            expires_in=3600,
            user_id="user123",
            user=user_info
        )
        
        # Should be able to serialize to dict
        response_dict = login_response.model_dump()
        assert isinstance(response_dict, dict)
        assert response_dict["access_token"] == "token"

    @pytest.mark.asyncio
    async def test_full_auth_workflow(self):
        """Test complete authentication workflow."""
        # Create test user
        test_user = create_test_user()
        assert test_user["user_id"] == "test_user_123"
        
        # Get current user
        current_user = await get_current_user()
        assert current_user["user_id"] == "test_user_123"
        
        # Hash password
        hashed = hash_password("testpass123")
        assert hashed.startswith("hashed_")


class TestAuthEdgeCases:
    """Test edge cases and error conditions."""

    def test_hash_password_empty_string(self):
        """Test password hashing with empty string."""
        hashed = hash_password("")
        assert hashed == "hashed_"

    def test_hash_password_special_characters(self):
        """Test password hashing with special characters."""
        password = "p@ssw0rd!@#$%^&*()"
        hashed = hash_password(password)
        assert hashed == f"hashed_{password}"

    def test_user_info_empty_roles(self):
        """Test UserInfo with empty roles list."""
        user_info = UserInfo(username="test", roles=[])
        assert user_info.roles == []

    def test_user_info_multiple_roles(self):
        """Test UserInfo with multiple roles."""
        roles = ["trader", "admin", "analyst", "manager"]
        user_info = UserInfo(username="test", roles=roles)
        assert user_info.roles == roles

    @pytest.mark.asyncio
    async def test_login_with_special_characters(self):
        """Test login with special characters in username/password."""
        mock_request = Mock(spec=Request)
        mock_request.json = AsyncMock(return_value={
            "username": "user@domain.com",
            "password": "p@ssw0rd!123"
        })
        
        mock_repo = Mock()
        mock_repo.get_user_by_username.return_value = None
        
        from backend.api.auth import login
        
        with pytest.raises(HTTPException):
            await login(
                request=mock_request,
                username=None,
                password=None,
                user_repo=mock_repo
            )

    def test_registration_request_edge_cases(self):
        """Test UserRegistrationRequest with edge case inputs."""
        # Minimum valid password length
        request = UserRegistrationRequest(
            email="test@example.com",
            password="a1234567"  # 8 characters minimum
        )
        assert len(request.password) == 8
        
        # Maximum valid password length
        max_password = "a" * 127 + "1"  # 128 characters maximum
        request = UserRegistrationRequest(
            email="test@example.com",
            password=max_password
        )
        assert len(request.password) == 128