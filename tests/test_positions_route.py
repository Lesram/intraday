"""
Tests for positions API routes.
Validates authentication requirements and response schema.
"""

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.api.routes.positions import router as positions_router


@pytest.fixture
def app():
    """Create FastAPI app with positions router for testing."""
    app = FastAPI()
    app.include_router(positions_router, prefix="/api/v1")
    return app


@pytest.fixture 
def client(app):
    """Create test client."""
    return TestClient(app)


def test_positions_without_auth_returns_401(client):
    """Test that positions endpoint returns 401 without authentication."""
    response = client.get("/api/v1/positions/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_positions_with_auth_returns_200(client):
    """Test that positions endpoint returns 200 with valid authentication."""
    from backend.infra.security import AuthenticatedUser, get_authenticated_user
    
    # Mock authenticated user using dependency override
    def mock_auth():
        return AuthenticatedUser(
            username="test_user",
            roles=["trader"],
            token_id="test-token"
        )
    
    # Override the dependency
    client.app.dependency_overrides[get_authenticated_user] = mock_auth
    
    try:
        response = client.get("/api/v1/positions/")
        assert response.status_code == status.HTTP_200_OK
    finally:
        # Clean up
        client.app.dependency_overrides.clear()


@patch("backend.api.routes.positions.get_settings")
def test_positions_response_schema_mock_data(mock_settings, client):
    """Test positions response contains all required DTO fields with mock data."""
    from backend.infra.security import AuthenticatedUser, get_authenticated_user
    
    # Mock authenticated user using dependency override
    def mock_auth():
        return AuthenticatedUser(
            username="test_user",
            roles=["trader"], 
            token_id="test-token"
        )
    
    # Mock settings to use mock data
    mock_settings.return_value.USE_MOCK_DATA = True
    
    # Override the dependency
    client.app.dependency_overrides[get_authenticated_user] = mock_auth
    
    try:
        response = client.get("/api/v1/positions/")
        assert response.status_code == status.HTTP_200_OK
        
        positions = response.json()
        assert isinstance(positions, list)
        assert len(positions) > 0
        
        # Validate schema for each position
        for position in positions:
            assert "symbol" in position
            assert "qty" in position
            assert "avg_price" in position
            assert "market_price" in position
            assert "market_value" in position
            assert "unrealized_pl" in position
            assert "updated_at" in position
            
            # Type validation
            assert isinstance(position["symbol"], str)
            assert isinstance(position["qty"], (int, float))
            assert isinstance(position["avg_price"], (int, float))
            assert isinstance(position["updated_at"], str)
            
            # Optional fields can be None
            assert position["market_price"] is None or isinstance(position["market_price"], (int, float))
            assert position["market_value"] is None or isinstance(position["market_value"], (int, float))
            assert position["unrealized_pl"] is None or isinstance(position["unrealized_pl"], (int, float))
    finally:
        # Clean up
        client.app.dependency_overrides.clear()


@patch("backend.api.routes.positions.get_settings")
def test_positions_mock_data_content(mock_settings, client):
    """Test that mock data returns expected deterministic positions."""
    from backend.infra.security import AuthenticatedUser, get_authenticated_user
    
    # Mock authenticated user using dependency override
    def mock_auth():
        return AuthenticatedUser(
            username="test_user",
            roles=["trader"],
            token_id="test-token"
        )
    
    # Mock settings to use mock data
    mock_settings.return_value.USE_MOCK_DATA = True
    
    # Override the dependency
    client.app.dependency_overrides[get_authenticated_user] = mock_auth
    
    try:
        response = client.get("/api/v1/positions/")
        positions = response.json()
        
        # Should have deterministic mock positions
        symbols = [pos["symbol"] for pos in positions]
        assert "AAPL" in symbols
        assert "GOOGL" in symbols
        assert "MSFT" in symbols
        
        # Verify AAPL position details (from mock data)
        aapl_position = next(pos for pos in positions if pos["symbol"] == "AAPL")
        assert aapl_position["qty"] == 10.0
        assert aapl_position["avg_price"] == 180.0
        assert aapl_position["market_price"] == 185.50
        assert aapl_position["unrealized_pl"] == 55.0
    finally:
        # Clean up
        client.app.dependency_overrides.clear()


@patch("backend.api.routes.positions.get_settings")
def test_positions_alpaca_mode(mock_settings, client):
    """Test positions endpoint in Alpaca mode.
    
    When Alpaca trading client is not available (no credentials), 
    the service gracefully falls back to mock data.
    """
    from backend.infra.security import AuthenticatedUser, get_authenticated_user
    
    # Mock authenticated user using dependency override
    def mock_auth():
        return AuthenticatedUser(
            username="test_user",
            roles=["trader"],
            token_id="test-token"
        )
    
    # Mock settings for Alpaca mode
    mock_settings.return_value.USE_MOCK_DATA = False
    mock_settings.return_value.USE_MOCK_BROKER = False
    
    # Override the dependency
    client.app.dependency_overrides[get_authenticated_user] = mock_auth
    
    try:
        response = client.get("/api/v1/positions/")
        assert response.status_code == status.HTTP_200_OK
        
        positions = response.json()
        # Should still return positions (falls back to mock when Alpaca unavailable)
        assert len(positions) > 0
        
        # Verify positions have required fields (real or mock)
        for position in positions:
            assert "symbol" in position
            assert "qty" in position
            assert "avg_price" in position
    finally:
        # Clean up
        client.app.dependency_overrides.clear()


@patch("backend.api.routes.positions.get_settings")
def test_positions_database_mode(mock_settings, client):
    """Test positions endpoint in database mode."""
    from backend.infra.security import AuthenticatedUser, get_authenticated_user
    
    # Mock authenticated user using dependency override
    def mock_auth():
        return AuthenticatedUser(
            username="test_user",
            roles=["trader"],
            token_id="test-token"
        )
    
    # Mock settings for database mode
    mock_settings.return_value.USE_MOCK_DATA = False
    mock_settings.return_value.USE_MOCK_BROKER = True
    
    # Override the dependency
    client.app.dependency_overrides[get_authenticated_user] = mock_auth
    
    try:
        response = client.get("/api/v1/positions/")
        assert response.status_code == status.HTTP_200_OK
        
        positions = response.json()
        # Should return positions (database or fallback to mock)
        assert len(positions) > 0
    finally:
        # Clean up
        client.app.dependency_overrides.clear()