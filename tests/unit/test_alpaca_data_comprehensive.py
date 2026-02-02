"""
Comprehensive tests for backend/integrations/alpaca_data.py

Tests the AlpacaDataClient for fetching historical market data from Alpaca API.
Covers: initialization, authentication, API requests, error handling, and response parsing.

Phase 3: Alpaca Integrations - Data Client Tests
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set environment variables for Alpaca data client."""
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test_key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "test_secret")
    monkeypatch.setenv("ALPACA_DATA_URL", "https://data.alpaca.markets/v2")


@pytest.fixture
def mock_http_client():
    """Mock httpx async client."""
    client = AsyncMock()
    client.get = AsyncMock()
    client.aclose = AsyncMock()
    return client


@pytest.fixture
def sample_bars_response():
    """Sample bars response from Alpaca API."""
    return {
        "bars": [
            {"t": "2025-01-01T00:00:00Z", "o": 100.0, "h": 102.0, "l": 99.0, "c": 101.0, "v": 1000},
            {"t": "2025-01-02T00:00:00Z", "o": 101.0, "h": 103.0, "l": 100.0, "c": 102.0, "v": 1100},
            {"t": "2025-01-03T00:00:00Z", "o": 102.0, "h": 104.0, "l": 101.0, "c": 103.0, "v": 1200},
            {"t": "2025-01-04T00:00:00Z", "o": 103.0, "h": 105.0, "l": 102.0, "c": 104.0, "v": 1300},
            {"t": "2025-01-05T00:00:00Z", "o": 104.0, "h": 106.0, "l": 103.0, "c": 105.0, "v": 1400},
        ],
        "symbol": "AAPL",
        "next_page_token": None
    }


# ============================================================================
# AlpacaDataClient INITIALIZATION TESTS
# ============================================================================

class TestAlpacaDataClientInit:
    """Tests for AlpacaDataClient initialization."""

    def test_init_with_env_vars(self, mock_env_vars):
        """Test initialization with environment variables."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        
        assert client.api_key == "test_key"
        assert client.api_secret == "test_secret"
        assert client.base_url == "https://data.alpaca.markets/v2"

    def test_init_without_credentials(self, monkeypatch):
        """Test initialization without credentials logs warning."""
        monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
        monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
        
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        
        assert client.api_key is None
        assert client.api_secret is None

    def test_init_default_base_url(self, monkeypatch):
        """Test initialization uses default base URL."""
        monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
        monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
        monkeypatch.delenv("ALPACA_DATA_URL", raising=False)
        
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        
        assert "data.alpaca.markets/v2" in client.base_url


# ============================================================================
# AUTHENTICATION HEADER TESTS
# ============================================================================

class TestAlpacaDataClientAuthHeaders:
    """Tests for authentication header generation."""

    def test_get_auth_headers_success(self, mock_env_vars):
        """Test getting auth headers with valid credentials."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        headers = client._get_auth_headers()
        
        assert headers["APCA-API-KEY-ID"] == "test_key"
        assert headers["APCA-API-SECRET-KEY"] == "test_secret"
        assert headers["Accept"] == "application/json"

    def test_get_auth_headers_no_key_raises(self, monkeypatch):
        """Test getting auth headers without key raises HTTPException."""
        monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
        monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
        
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        
        with pytest.raises(HTTPException) as exc_info:
            client._get_auth_headers()
        
        assert exc_info.value.status_code == 503
        assert "credentials not configured" in exc_info.value.detail

    def test_get_auth_headers_no_secret_raises(self, monkeypatch):
        """Test getting auth headers without secret raises HTTPException."""
        monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
        monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
        
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        
        with pytest.raises(HTTPException) as exc_info:
            client._get_auth_headers()
        
        assert exc_info.value.status_code == 503


# ============================================================================
# GET HISTORICAL CLOSES TESTS
# ============================================================================

class TestAlpacaDataClientGetHistoricalCloses:
    """Tests for get_historical_closes method."""

    @pytest.mark.asyncio
    async def test_get_historical_closes_success(self, mock_env_vars, mock_http_client, sample_bars_response):
        """Test successful historical closes retrieval."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_bars_response
        mock_http_client.get.return_value = mock_response
        
        closes = await client.get_historical_closes("AAPL", lookback=5)
        
        assert len(closes) == 5
        assert closes == [101.0, 102.0, 103.0, 104.0, 105.0]

    @pytest.mark.asyncio
    async def test_get_historical_closes_default_params(self, mock_env_vars, mock_http_client, sample_bars_response):
        """Test get_historical_closes with default parameters."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_bars_response
        mock_http_client.get.return_value = mock_response
        
        await client.get_historical_closes("MSFT")
        
        # Check API was called with correct URL pattern
        call_args = mock_http_client.get.call_args
        assert "/stocks/MSFT/bars" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_historical_closes_custom_timeframe(self, mock_env_vars, mock_http_client, sample_bars_response):
        """Test get_historical_closes with custom timeframe."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_bars_response
        mock_http_client.get.return_value = mock_response
        
        await client.get_historical_closes("AAPL", timeframe="1Hour")
        
        # Verify params include timeframe
        call_args = mock_http_client.get.call_args
        assert call_args[1]["params"]["timeframe"] == "1Hour"

    @pytest.mark.asyncio
    async def test_get_historical_closes_symbol_uppercase(self, mock_env_vars, mock_http_client, sample_bars_response):
        """Test symbol is converted to uppercase."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_bars_response
        mock_http_client.get.return_value = mock_response
        
        await client.get_historical_closes("aapl")
        
        call_args = mock_http_client.get.call_args
        assert "/stocks/AAPL/bars" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_historical_closes_limits_to_lookback(self, mock_env_vars, mock_http_client):
        """Test result is limited to lookback count."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        # Response with more bars than requested
        many_bars = {
            "bars": [
                {"t": f"2025-01-{i:02d}T00:00:00Z", "c": 100.0 + i, "o": 99, "h": 101, "l": 98, "v": 1000}
                for i in range(1, 11)  # 10 bars
            ]
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = many_bars
        mock_http_client.get.return_value = mock_response
        
        closes = await client.get_historical_closes("AAPL", lookback=5)
        
        # Should return only last 5
        assert len(closes) == 5

    @pytest.mark.asyncio
    async def test_get_historical_closes_empty_response(self, mock_env_vars, mock_http_client):
        """Test handling of empty bars response."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"bars": []}
        mock_http_client.get.return_value = mock_response
        
        closes = await client.get_historical_closes("AAPL")
        
        assert closes == []

    @pytest.mark.asyncio
    async def test_get_historical_closes_no_bars_key(self, mock_env_vars, mock_http_client):
        """Test handling of response without bars key."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # No bars key
        mock_http_client.get.return_value = mock_response
        
        closes = await client.get_historical_closes("AAPL")
        
        assert closes == []


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestAlpacaDataClientErrors:
    """Tests for error handling in AlpacaDataClient."""

    @pytest.mark.asyncio
    async def test_get_historical_closes_api_error(self, mock_env_vars, mock_http_client):
        """Test handling of API error response."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_response.json.return_value = {"message": "Invalid symbol"}
        mock_http_client.get.return_value = mock_response
        
        with pytest.raises(HTTPException) as exc_info:
            await client.get_historical_closes("INVALID")
        
        assert exc_info.value.status_code == 502
        assert "Alpaca API error: 400" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_historical_closes_server_error(self, mock_env_vars, mock_http_client):
        """Test handling of 500 server error."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.json.side_effect = Exception("Not JSON")
        mock_http_client.get.return_value = mock_response
        
        with pytest.raises(HTTPException) as exc_info:
            await client.get_historical_closes("AAPL")
        
        assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_get_historical_closes_rate_limit_error(self, mock_env_vars, mock_http_client):
        """Test handling of rate limit (429) error."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Too Many Requests"
        mock_response.json.return_value = {"message": "Rate limit exceeded"}
        mock_http_client.get.return_value = mock_response
        
        with pytest.raises(HTTPException) as exc_info:
            await client.get_historical_closes("AAPL")
        
        assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_get_historical_closes_network_error(self, mock_env_vars, mock_http_client):
        """Test handling of network error."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_http_client.get.side_effect = Exception("Network error")
        
        with pytest.raises(HTTPException) as exc_info:
            await client.get_historical_closes("AAPL")
        
        assert exc_info.value.status_code == 502
        assert "Failed to fetch historical data" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_historical_closes_no_credentials(self, monkeypatch, mock_http_client):
        """Test error when no credentials configured."""
        monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
        monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
        
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        with pytest.raises(HTTPException) as exc_info:
            await client.get_historical_closes("AAPL")
        
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_get_historical_closes_unauthorized(self, mock_env_vars, mock_http_client):
        """Test handling of 401 unauthorized error."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.json.return_value = {"message": "Invalid API key"}
        mock_http_client.get.return_value = mock_response
        
        with pytest.raises(HTTPException) as exc_info:
            await client.get_historical_closes("AAPL")
        
        assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_get_historical_closes_forbidden(self, mock_env_vars, mock_http_client):
        """Test handling of 403 forbidden error."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_response.json.return_value = {"message": "Access denied"}
        mock_http_client.get.return_value = mock_response
        
        with pytest.raises(HTTPException) as exc_info:
            await client.get_historical_closes("AAPL")
        
        assert exc_info.value.status_code == 502


# ============================================================================
# CLOSE AND CLEANUP TESTS
# ============================================================================

class TestAlpacaDataClientCleanup:
    """Tests for cleanup and resource management."""

    @pytest.mark.asyncio
    async def test_close_client(self, mock_env_vars, mock_http_client):
        """Test closing HTTP client."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        await client.close()
        
        mock_http_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_entry(self, mock_env_vars):
        """Test async context manager entry."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        
        result = await client.__aenter__()
        
        assert result is client

    @pytest.mark.asyncio
    async def test_context_manager_exit(self, mock_env_vars, mock_http_client):
        """Test async context manager exit."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        await client.__aexit__(None, None, None)
        
        mock_http_client.aclose.assert_called_once()


# ============================================================================
# GLOBAL INSTANCE TESTS
# ============================================================================

class TestAlpacaDataClientGlobalInstance:
    """Tests for global client instance functions."""

    def test_get_alpaca_data_client_singleton(self, mock_env_vars):
        """Test get_alpaca_data_client returns singleton."""
        from backend.integrations import alpaca_data
        
        # Reset global
        alpaca_data._data_client = None
        
        client1 = alpaca_data.get_alpaca_data_client()
        client2 = alpaca_data.get_alpaca_data_client()
        
        assert client1 is client2
        
        # Cleanup
        alpaca_data._data_client = None

    def test_get_alpaca_data_client_creates_new(self, mock_env_vars):
        """Test get_alpaca_data_client creates new instance when None."""
        from backend.integrations import alpaca_data
        
        alpaca_data._data_client = None
        
        client = alpaca_data.get_alpaca_data_client()
        
        assert client is not None
        
        # Cleanup
        alpaca_data._data_client = None

    @pytest.mark.asyncio
    async def test_cleanup_alpaca_data_client(self, mock_env_vars, mock_http_client):
        """Test cleanup_alpaca_data_client cleans up properly."""
        from backend.integrations import alpaca_data
        
        # Create and store client
        alpaca_data._data_client = None
        client = alpaca_data.get_alpaca_data_client()
        client.client = mock_http_client
        
        await alpaca_data.cleanup_alpaca_data_client()
        
        assert alpaca_data._data_client is None
        mock_http_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_when_no_client(self, mock_env_vars):
        """Test cleanup when no client exists."""
        from backend.integrations import alpaca_data
        
        alpaca_data._data_client = None
        
        # Should not raise
        await alpaca_data.cleanup_alpaca_data_client()


# ============================================================================
# PARAMETER VALIDATION TESTS
# ============================================================================

class TestAlpacaDataClientParamValidation:
    """Tests for parameter validation."""

    @pytest.mark.asyncio
    async def test_lookback_calculation(self, mock_env_vars, mock_http_client, sample_bars_response):
        """Test lookback affects request parameters."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_bars_response
        mock_http_client.get.return_value = mock_response
        
        await client.get_historical_closes("AAPL", lookback=50)
        
        call_args = mock_http_client.get.call_args
        # Limit should be lookback * 2
        assert call_args[1]["params"]["limit"] == 100

    @pytest.mark.asyncio
    async def test_different_timeframes(self, mock_env_vars, mock_http_client, sample_bars_response):
        """Test different timeframe values."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_bars_response
        mock_http_client.get.return_value = mock_response
        
        for timeframe in ["1Day", "1Hour", "5Min", "15Min"]:
            await client.get_historical_closes("AAPL", timeframe=timeframe)
            
            call_args = mock_http_client.get.call_args
            assert call_args[1]["params"]["timeframe"] == timeframe

    @pytest.mark.asyncio
    async def test_sort_is_ascending(self, mock_env_vars, mock_http_client, sample_bars_response):
        """Test sort parameter is set to asc."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_bars_response
        mock_http_client.get.return_value = mock_response
        
        await client.get_historical_closes("AAPL")
        
        call_args = mock_http_client.get.call_args
        assert call_args[1]["params"]["sort"] == "asc"

    @pytest.mark.asyncio
    async def test_adjustment_is_raw(self, mock_env_vars, mock_http_client, sample_bars_response):
        """Test adjustment parameter is set to raw."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_bars_response
        mock_http_client.get.return_value = mock_response
        
        await client.get_historical_closes("AAPL")
        
        call_args = mock_http_client.get.call_args
        assert call_args[1]["params"]["adjustment"] == "raw"


# ============================================================================
# DATE RANGE TESTS
# ============================================================================

class TestAlpacaDataClientDateRange:
    """Tests for date range calculations."""

    @pytest.mark.asyncio
    async def test_date_range_format(self, mock_env_vars, mock_http_client, sample_bars_response):
        """Test date range is properly formatted."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_bars_response
        mock_http_client.get.return_value = mock_response
        
        await client.get_historical_closes("AAPL", lookback=200)
        
        call_args = mock_http_client.get.call_args
        params = call_args[1]["params"]
        
        # Start and end should be date strings
        assert "start" in params
        assert "end" in params
        # Format should be YYYY-MM-DD
        assert len(params["start"]) == 10
        assert len(params["end"]) == 10

    @pytest.mark.asyncio
    async def test_buffer_days_for_weekends(self, mock_env_vars, mock_http_client, sample_bars_response):
        """Test buffer days account for weekends/holidays."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_bars_response
        mock_http_client.get.return_value = mock_response
        
        await client.get_historical_closes("AAPL", lookback=100)
        
        call_args = mock_http_client.get.call_args
        params = call_args[1]["params"]
        
        # Start date should be well before lookback trading days
        start_date = datetime.strptime(params["start"], "%Y-%m-%d")
        end_date = datetime.strptime(params["end"], "%Y-%m-%d")
        
        # With 1.4 buffer factor, should request ~140 days for 100 lookback
        days_diff = (end_date - start_date).days
        assert days_diff >= 100  # At least lookback days


# ============================================================================
# RESPONSE PARSING TESTS
# ============================================================================

class TestAlpacaDataClientResponseParsing:
    """Tests for response parsing."""

    @pytest.mark.asyncio
    async def test_parse_closing_prices(self, mock_env_vars, mock_http_client):
        """Test closing prices are correctly extracted."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        response_data = {
            "bars": [
                {"t": "2025-01-01", "c": 150.50, "o": 149, "h": 151, "l": 148, "v": 1000},
                {"t": "2025-01-02", "c": 151.25, "o": 150, "h": 152, "l": 149, "v": 1100},
            ]
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_data
        mock_http_client.get.return_value = mock_response
        
        closes = await client.get_historical_closes("AAPL", lookback=10)
        
        assert closes == [150.50, 151.25]

    @pytest.mark.asyncio
    async def test_parse_with_float_conversion(self, mock_env_vars, mock_http_client):
        """Test closing prices are converted to float."""
        from backend.integrations.alpaca_data import AlpacaDataClient
        
        client = AlpacaDataClient()
        client.client = mock_http_client
        
        response_data = {
            "bars": [
                {"t": "2025-01-01", "c": 150, "o": 149, "h": 151, "l": 148, "v": 1000},  # Integer
            ]
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_data
        mock_http_client.get.return_value = mock_response
        
        closes = await client.get_historical_closes("AAPL")
        
        assert all(isinstance(c, float) for c in closes)
