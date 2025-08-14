"""
Tests for portfolio positions endpoint.
Tests /api/v1/positions endpoint functionality including authentication and data retrieval.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from fastapi import status
from fastapi.testclient import TestClient
from backend.api.factory import create_app


class FakeJwtVerifier:
    """Fake JWT verifier for testing authentication."""
    
    def __init__(self, valid_users=None):
        self.valid_users = valid_users or {}
        
    def verify_token(self, token: str):
        """Verify JWT token and return user info."""
        if token in self.valid_users:
            return self.valid_users[token]
        return None


class FakePortfolioRepo:
    """Fake portfolio repository for testing."""
    
    def __init__(self):
        self.positions = {}  # user_id -> positions list mapping
        self.current_user_id = None  # Will be set by the mock
        
    async def get_positions_by_user_id(self, user_id: str):
        """Get positions for a specific user."""
        return self.positions.get(user_id, [])
    
    def get_all_positions(self):
        """Get all positions (filtered by current user in test context)."""
        # Return positions for the current user context
        if self.current_user_id:
            return self.positions.get(self.current_user_id, [])
        else:
            return self.positions.get("user123", [])  # Default for backwards compatibility
    
    def set_positions(self, user_id: str, positions: list):
        """Set positions for a user (test helper)."""
        self.positions[user_id] = positions
        
    def set_current_user(self, user_id: str):
        """Set current user context (test helper)."""
        self.current_user_id = user_id


@pytest.fixture
def fake_jwt_verifier():
    """Create fake JWT verifier with test users."""
    valid_users = {
        "valid_token_123": {"user_id": "user123", "email": "test@example.com"},
        "valid_token_456": {"user_id": "user456", "email": "other@example.com"}
    }
    return FakeJwtVerifier(valid_users)


@pytest.fixture
def fake_portfolio_repo():
    """Create fake portfolio repository."""
    repo = FakePortfolioRepo()
    
    # Set up test positions for user123
    test_positions = [
        {
            "symbol": "AAPL",
            "qty": 100,  # Fixed field name from quantity to qty
            "avg_price": 150.25,
            "market_value": 15125.50,
            "unrealized_pnl": 75.50
        },
        {
            "symbol": "GOOGL",
            "qty": 50,  # Fixed field name from quantity to qty
            "avg_price": 2750.80,
            "market_value": 138000.00,
            "unrealized_pnl": -500.00
        }
    ]
    repo.set_positions("user123", test_positions)
    
    # Empty positions for user456
    repo.set_positions("user456", [])
    
    return repo


@pytest.fixture
def app_with_mocks(fake_jwt_verifier, fake_portfolio_repo):
    """Create app with mocked dependencies."""
    
    # Mock get_current_user dependency
    def mock_get_current_user():
        from fastapi import Depends, HTTPException, status
        from fastapi.security import HTTPBearer
        
        security = HTTPBearer()
        
        def verify_user(credentials=Depends(security)):
            if not credentials:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="No authorization token provided"
                )
            
            user = fake_jwt_verifier.verify_token(credentials.credentials)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token"
                )
            
            # Set current user context in the fake repo
            fake_portfolio_repo.set_current_user(user["user_id"])
            
            return user
        
        return verify_user
    
    # Mock get_portfolio_repo dependency
    def mock_get_portfolio_repo():
        return fake_portfolio_repo
    
    # Create app and override dependencies
    app = create_app()
    
    from backend.infra.security import get_current_user
    from backend.api.portfolio import get_portfolio_repo
    
    app.dependency_overrides[get_current_user] = mock_get_current_user()
    app.dependency_overrides[get_portfolio_repo] = mock_get_portfolio_repo
    
    return app


@pytest.fixture
def test_client(app_with_mocks):
    """Create test client with mocked dependencies."""
    return TestClient(app_with_mocks)


class TestPositions:
    """Test cases for /api/v1/positions endpoint."""
    
    def test_get_positions_without_auth_returns_403(self, test_client):
        """Test that accessing positions without authentication returns 403."""
        response = test_client.get("/api/v1/positions")
        
        # Should return 403 Forbidden
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        data = response.json()
        assert "error" in data
        assert data["error"]["type"] == "http_error"
    
    def test_get_positions_with_invalid_token_returns_401(self, test_client):
        """Test that accessing positions with invalid token returns 401."""
        headers = {"Authorization": "Bearer invalid_token"}
        response = test_client.get("/api/v1/positions", headers=headers)
        
        # Should return 401 Unauthorized
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        
        data = response.json()
        assert "error" in data
        assert data["error"]["type"] == "http_error"
    
    def test_get_positions_with_valid_auth_returns_positions(self, test_client):
        """Test that authenticated user can retrieve their positions."""
        headers = {"Authorization": "Bearer valid_token_123"}
        response = test_client.get("/api/v1/positions", headers=headers)
        
        # Should return 200 OK
        assert response.status_code == status.HTTP_200_OK
        
        # Check response structure
        positions = response.json()
        assert isinstance(positions, list)
        assert len(positions) == 2
        
        # Verify first position
        aapl_position = positions[0]
        assert aapl_position["symbol"] == "AAPL"
        assert aapl_position["qty"] == "100"  # Decimal fields are serialized as strings
        assert aapl_position["avg_price"] == "150.25"
        assert aapl_position["market_value"] == "15125.5"
        assert aapl_position["unrealized_pnl"] == "75.5"
        
        # Verify second position
        googl_position = positions[1]
        assert googl_position["symbol"] == "GOOGL"
        assert googl_position["qty"] == "50"  # Decimal fields are serialized as strings
        assert googl_position["avg_price"] == "2750.8"
        assert googl_position["market_value"] == "138000.0"
        assert googl_position["unrealized_pnl"] == "-500.0"
    
    def test_get_positions_empty_portfolio_returns_empty_list(self, test_client):
        """Test that user with no positions gets empty list."""
        headers = {"Authorization": "Bearer valid_token_456"}
        response = test_client.get("/api/v1/positions", headers=headers)
        
        # Should return 200 OK
        assert response.status_code == status.HTTP_200_OK
        
        # Should be empty list
        positions = response.json()
        assert isinstance(positions, list)
        assert len(positions) == 0
    
    def test_get_positions_response_schema(self, test_client):
        """Test that position response has all expected fields."""
        headers = {"Authorization": "Bearer valid_token_123"}
        response = test_client.get("/api/v1/positions", headers=headers)
        
        assert response.status_code == status.HTTP_200_OK
        
        positions = response.json()
        if len(positions) > 0:
            position = positions[0]
            
            # Verify all required fields are present
            required_fields = ["symbol", "qty", "avg_price", "market_value", "unrealized_pnl"]
            for field in required_fields:
                assert field in position, f"Missing required field: {field}"
            
            # Verify field types (Decimal fields are serialized as strings in JSON)
            assert isinstance(position["symbol"], str)
            assert isinstance(position["qty"], str)  # Decimal serialized as string
            assert isinstance(position["avg_price"], str)  # Decimal serialized as string
            assert isinstance(position["market_value"], str)  # Decimal serialized as string
            assert isinstance(position["unrealized_pnl"], str)  # Decimal serialized as string
    
    def test_get_positions_malformed_auth_header_returns_403(self, test_client):
        """Test that malformed authorization header returns 403."""
        # Missing Bearer prefix
        headers = {"Authorization": "valid_token_123"}
        response = test_client.get("/api/v1/positions", headers=headers)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_get_positions_empty_auth_header_returns_403(self, test_client):
        """Test that empty authorization header returns 403."""
        headers = {"Authorization": ""}
        response = test_client.get("/api/v1/positions", headers=headers)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
