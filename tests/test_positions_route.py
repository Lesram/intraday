"""
Tests for positions API routes.
Validates authentication requirements and response schema.

The positions endpoint fetches data from Alpaca API or database depending on
USE_MOCK_BROKER setting.  In tests we mock the underlying fetch functions
(get_alpaca_positions / get_database_positions) so that we get deterministic
data without needing real broker credentials.
"""

import pytest
from datetime import UTC, datetime
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from backend.api.routes.positions import PositionDTO, router as positions_router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_POSITIONS = [
    PositionDTO(
        symbol="AAPL",
        qty=10.0,
        avg_price=180.0,
        market_price=185.50,
        market_value=1855.0,
        unrealized_pl=55.0,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    ),
    PositionDTO(
        symbol="GOOGL",
        qty=5.0,
        avg_price=140.0,
        market_price=145.0,
        market_value=725.0,
        unrealized_pl=25.0,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    ),
    PositionDTO(
        symbol="MSFT",
        qty=8.0,
        avg_price=370.0,
        market_price=380.0,
        market_value=3040.0,
        unrealized_pl=80.0,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    ),
]


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


def _override_auth(client):
    """Install a dependency override that bypasses real authentication."""
    from backend.infra.security import AuthenticatedUser, get_authenticated_user

    def mock_auth():
        return AuthenticatedUser(
            username="test_user",
            roles=["trader"],
            token_id="test-token",
        )

    client.app.dependency_overrides[get_authenticated_user] = mock_auth


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_positions_without_auth_returns_401(client):
    """Test that positions endpoint returns 401 without authentication."""
    response = client.get("/api/v1/positions/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_positions_with_auth_returns_200(client):
    """Test that positions endpoint returns 200 with valid authentication."""
    _override_auth(client)
    try:
        response = client.get("/api/v1/positions/")
        assert response.status_code == status.HTTP_200_OK
    finally:
        client.app.dependency_overrides.clear()


@patch("backend.api.routes.positions.get_alpaca_positions", new_callable=AsyncMock, return_value=MOCK_POSITIONS)
@patch("backend.api.routes.positions.get_settings")
def test_positions_response_schema_mock_data(mock_settings, mock_alpaca, client):
    """Test positions response contains all required DTO fields with mock data."""
    mock_settings.return_value.USE_MOCK_BROKER = False

    _override_auth(client)
    try:
        response = client.get("/api/v1/positions/")
        assert response.status_code == status.HTTP_200_OK

        positions = response.json()
        assert isinstance(positions, list)
        assert len(positions) > 0

        # Validate schema for each position.
        # V12 W87 (post-cleanup): the V11 wave-54 VV-1 fix changed
        # PositionResponse to serialize camelCase (matching the
        # frontend's TS contract).  This test still asserted on the
        # snake_case input field names — that's the V11 VV-1 finding
        # showing up in tests.  Now: assert on the wire-format keys.
        for position in positions:
            assert "symbol" in position
            assert "qty" in position
            assert "averagePrice" in position
            assert "currentPrice" in position
            assert "marketValue" in position
            assert "unrealizedPnL" in position
            assert "updatedAt" in position

            # Type validation
            assert isinstance(position["symbol"], str)
            assert isinstance(position["qty"], (int, float))
            assert isinstance(position["averagePrice"], (int, float))
            assert isinstance(position["updatedAt"], str)

            # Optional fields can be None
            assert position["currentPrice"] is None or isinstance(position["currentPrice"], (int, float))
            assert position["marketValue"] is None or isinstance(position["marketValue"], (int, float))
            assert position["unrealizedPnL"] is None or isinstance(position["unrealizedPnL"], (int, float))
    finally:
        client.app.dependency_overrides.clear()


@patch("backend.api.routes.positions.get_alpaca_positions", new_callable=AsyncMock, return_value=MOCK_POSITIONS)
@patch("backend.api.routes.positions.get_settings")
def test_positions_mock_data_content(mock_settings, mock_alpaca, client):
    """Test that mocked positions return expected deterministic data."""
    mock_settings.return_value.USE_MOCK_BROKER = False

    _override_auth(client)
    try:
        response = client.get("/api/v1/positions/")
        positions = response.json()

        # Should have deterministic mock positions
        symbols = [pos["symbol"] for pos in positions]
        assert "AAPL" in symbols
        assert "GOOGL" in symbols
        assert "MSFT" in symbols

        # Verify AAPL position details (V11 wave-54 VV-1: camelCase wire keys)
        aapl_position = next(pos for pos in positions if pos["symbol"] == "AAPL")
        assert aapl_position["qty"] == 10.0
        assert aapl_position["averagePrice"] == 180.0
        assert aapl_position["currentPrice"] == 185.50
        assert aapl_position["unrealizedPnL"] == 55.0
    finally:
        client.app.dependency_overrides.clear()


@patch("backend.api.routes.positions.get_alpaca_positions", new_callable=AsyncMock, return_value=MOCK_POSITIONS)
@patch("backend.api.routes.positions.get_settings")
def test_positions_alpaca_mode(mock_settings, mock_alpaca, client):
    """Test positions endpoint in Alpaca mode.

    When USE_MOCK_BROKER is False the endpoint delegates to get_alpaca_positions.
    We mock that function so no real credentials are needed.
    """
    mock_settings.return_value.USE_MOCK_BROKER = False

    _override_auth(client)
    try:
        response = client.get("/api/v1/positions/")
        assert response.status_code == status.HTTP_200_OK

        positions = response.json()
        assert len(positions) > 0

        for position in positions:
            assert "symbol" in position
            assert "qty" in position
            # V11 wave-54 VV-1: camelCase wire keys.
            assert "averagePrice" in position
    finally:
        client.app.dependency_overrides.clear()


@patch("backend.api.routes.positions.get_database_positions", new_callable=AsyncMock, return_value=MOCK_POSITIONS)
@patch("backend.api.routes.positions.get_settings")
def test_positions_database_mode(mock_settings, mock_db, client):
    """Test positions endpoint in database mode.

    When USE_MOCK_BROKER is True the endpoint delegates to
    get_database_positions.  We mock that function to return test data.
    """
    mock_settings.return_value.USE_MOCK_BROKER = True

    _override_auth(client)
    try:
        response = client.get("/api/v1/positions/")
        assert response.status_code == status.HTTP_200_OK

        positions = response.json()
        assert len(positions) > 0
    finally:
        client.app.dependency_overrides.clear()