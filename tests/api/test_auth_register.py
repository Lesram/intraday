"""
Tests for auth registration endpoint.
Tests /auth/register endpoint functionality including happy path, conflicts, and validation.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from fastapi import status


class FakeUserRepo:
    """Fake in-memory user repository for testing."""
    
    def __init__(self):
        self.users = {}  # email -> user_data mapping
        
    def user_exists(self, email: str) -> bool:
        """Check if user exists by email."""
        return email in self.users
        
    async def exists_by_email(self, email: str) -> bool:
        """Check if user exists by email (async version for compatibility)."""
        return email in self.users
        
    async def get_by_email(self, email: str):
        """Get user by email, returns None if not found."""
        return self.users.get(email)
        
    def create_user(self, username: str, password: str, roles: list[str]) -> dict:
        """Create a new user with username, password, and roles to match real UserRepository interface."""
        import uuid
        
        user_data = {
            "id": str(uuid.uuid4()),  # Use 'id' key to match get_user_id() expectations
            "user_id": str(uuid.uuid4()),  # Also include user_id for compatibility
            "username": username,
            "email": username,  # Use username as email for compatibility
            "password_hash": f"hashed_{password}",  # Simple mock hash format for tests
            "roles": roles
        }
        # Store by email for compatibility with exists_by_email and get_by_email
        self.users[username] = user_data
        return user_data
        
    async def create(self, user_data: dict):
        """Create a new user (legacy method)."""
        self.users[user_data["email"]] = user_data
        return user_data


class TestAuthRegister:
    """Test cases for /auth/register endpoint."""
    
    def test_register_happy_path(self):
        """Test successful user registration."""
        from backend.api.factory import create_app
        from fastapi.testclient import TestClient
        from backend.api.auth import get_user_repo  # Import from auth module, not repositories
        from unittest.mock import patch
        
        # Create fresh instances for this test
        fake_user_repo = FakeUserRepo()
        
        # Create app first
        app = create_app()
        
        # Override dependencies
        app.dependency_overrides[get_user_repo] = lambda: fake_user_repo
        
        with patch('backend.api.auth.hash_password') as mock_hash:
            mock_hash.side_effect = lambda pwd: f"hashed_{pwd}"
            
            test_client = TestClient(app)
            
            payload = {
                "email": "test@example.com",
                "password": "password123"
            }
            
            response = test_client.post("/auth/register", json=payload)
            
            # Should return 201 Created
            assert response.status_code == status.HTTP_201_CREATED
            
            # Check response structure
            data = response.json()
            assert "user_id" in data
            assert "email" in data
            assert data["email"] == payload["email"]
            assert isinstance(data["user_id"], str)
            assert len(data["user_id"]) > 0
            
            # Verify user was actually created in repo
            assert payload["email"] in fake_user_repo.users
            created_user = fake_user_repo.users[payload["email"]]
            assert created_user["email"] == payload["email"]
            assert created_user["password_hash"] == f"hashed_{payload['password']}"
    
    def test_register_duplicate_email_returns_409(self):
        """Test that registering duplicate email returns 409 conflict."""
        from backend.api.factory import create_app
        from fastapi.testclient import TestClient
        from backend.api.auth import get_user_repo  # Import from auth module, not repositories
        from unittest.mock import patch
        
        # Create fake repository with existing user
        fake_repo = FakeUserRepo()
        existing_email = "existing@example.com"
        fake_repo.users[existing_email] = {
            "id": "existing-id", 
            "email": existing_email,
            "password_hash": "existing_hash"
        }
        
        # Create app first
        app = create_app()
        
        # Override dependencies
        app.dependency_overrides[get_user_repo] = lambda: fake_repo
        
        with patch('backend.api.auth.hash_password') as mock_hash:
            mock_hash.side_effect = lambda pwd: f"hashed_{pwd}"
            
            # Create test client
            test_client = TestClient(app)
            
            # Make request
            payload = {
                "email": existing_email,
                "password": "newpassword123"
            }
            
            response = test_client.post("/auth/register", json=payload)
            
            # Should return 409 Conflict
            assert response.status_code == status.HTTP_409_CONFLICT
            
            # Check error response format (FastAPI standard format)
            data = response.json()
            assert "detail" in data
            assert data["detail"] == "Email already registered"
    
    def test_register_invalid_email_returns_422(self):
        """Test that invalid email format returns 422 validation error."""
        from backend.api.factory import create_app
        from fastapi.testclient import TestClient
        
        # Create test client (no mocking needed for validation errors)
        app = create_app()
        test_client = TestClient(app)
        
        payload = {
            "email": "not-an-email",
            "password": "password123"
        }
        
        response = test_client.post("/auth/register", json=payload)
        
        # Should return 422 Unprocessable Entity
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Check that response contains validation error details
        data = response.json()
        assert "detail" in data  # FastAPI validation errors use 'detail' directly
        assert isinstance(data["detail"], list)  # List of validation errors
        assert len(data["detail"]) > 0
        # Check that email validation failed - using actual response format
        assert any("email" in error.get("field", "") for error in data["detail"])
    
    def test_register_password_too_short_returns_422(self):
        """Test that password shorter than 8 characters returns 422."""
        from backend.api.factory import create_app
        from fastapi.testclient import TestClient
        
        # Create test client (no mocking needed for validation errors)
        app = create_app()
        test_client = TestClient(app)
        
        payload = {
            "email": "test@example.com",
            "password": "short"  # Less than 8 characters
        }
        
        response = test_client.post("/auth/register", json=payload)
        
        # Should return 422 Unprocessable Entity
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Check that response contains validation error details
        data = response.json()
        assert "detail" in data  # FastAPI validation errors use 'detail' directly
        assert isinstance(data["detail"], list)
        assert len(data["detail"]) > 0
        # Check that password validation failed - using actual response format
        assert any("password" in error.get("field", "") for error in data["detail"])
    
    def test_register_password_too_long_returns_422(self):
        """Test that password longer than 128 characters returns 422."""
        from backend.api.factory import create_app
        from fastapi.testclient import TestClient
        
        # Create test client
        app = create_app()
        test_client = TestClient(app)
        
        payload = {
            "email": "test@example.com",
            "password": "a" * 129  # More than 128 characters
        }
        
        response = test_client.post("/auth/register", json=payload)
        
        # Should return 422 Unprocessable Entity  
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Check that response contains validation error details
        data = response.json()
        assert "detail" in data  # FastAPI validation errors use 'detail' directly
        assert isinstance(data["detail"], list)
        assert len(data["detail"]) > 0
        # Check that password validation failed (too long) - using actual response format
        assert any("password" in error.get("field", "") for error in data["detail"])
    
    def test_register_missing_email_returns_422(self):
        """Test that missing email field returns 422."""
        from backend.api.factory import create_app
        from fastapi.testclient import TestClient
        
        # Create test client
        app = create_app()
        test_client = TestClient(app)
        
        payload = {
            "password": "password123"
            # Missing email field
        }
        
        response = test_client.post("/auth/register", json=payload)
        
        # Should return 422 Unprocessable Entity
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        data = response.json()
        assert "detail" in data  # FastAPI validation errors use 'detail' directly
        assert isinstance(data["detail"], list)
        assert len(data["detail"]) > 0
        # Check that email validation failed (missing) - using actual response format
        assert any("email" in error.get("field", "") for error in data["detail"])
    
    def test_register_missing_password_returns_422(self):
        """Test that missing password field returns 422."""
        from backend.api.factory import create_app
        from fastapi.testclient import TestClient
        
        # Create test client
        app = create_app()
        test_client = TestClient(app)
        
        payload = {
            "email": "test@example.com"
            # Missing password field
        }
        
        response = test_client.post("/auth/register", json=payload)
        
        # Should return 422 Unprocessable Entity
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        data = response.json()
        assert "detail" in data  # FastAPI validation errors use 'detail' directly
        assert isinstance(data["detail"], list)
        assert len(data["detail"]) > 0
        # Check that password validation failed (missing) - using actual response format
        assert any("password" in error.get("field", "") for error in data["detail"])
    
    def test_register_empty_payload_returns_422(self):
        """Test that empty payload returns 422."""
        from backend.api.factory import create_app
        from fastapi.testclient import TestClient
        
        # Create test client
        app = create_app()
        test_client = TestClient(app)
        
        response = test_client.post("/auth/register", json={})
        
        # Should return 422 Unprocessable Entity
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        data = response.json()
        assert "detail" in data  # FastAPI validation errors use 'detail' directly
        assert isinstance(data["detail"], list)
        assert len(data["detail"]) > 0
        # Check that both email and password are missing - using actual response format
        fields = [error.get("field", "") for error in data["detail"]]
        assert any("email" in field for field in fields)
        assert any("password" in field for field in fields)
