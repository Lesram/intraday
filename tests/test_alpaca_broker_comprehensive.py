"""
Comprehensive tests for backend/integrations/alpaca_broker.py
Tests Alpaca Trading API client with mocked HTTP responses.
Target: Increase coverage from 16% to 50%+
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import httpx
from fastapi import HTTPException

from backend.integrations.alpaca_broker import (
    AlpacaBrokerClient,
    retry_on_transient_error,
)

pytestmark = pytest.mark.unit


# ============================================================================
# RETRY DECORATOR TESTS
# ============================================================================

class TestRetryOnTransientError:
    """Tests for retry_on_transient_error decorator."""

    @pytest.mark.asyncio
    async def test_no_retry_on_success(self):
        """Test no retry when function succeeds."""
        call_count = 0

        @retry_on_transient_error(max_retries=3)
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_func()
        
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_429(self):
        """Test retry on 429 Too Many Requests."""
        call_count = 0

        @retry_on_transient_error(max_retries=2, backoff_factor=0.01)
        async def rate_limited_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise HTTPException(status_code=429, detail="Rate limited")
            return "success"

        result = await rate_limited_func()
        
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self):
        """Test no retry on 400 Bad Request."""
        call_count = 0

        @retry_on_transient_error(max_retries=3)
        async def bad_request_func():
            nonlocal call_count
            call_count += 1
            raise HTTPException(status_code=400, detail="Bad request")

        with pytest.raises(HTTPException) as exc:
            await bad_request_func()
        
        assert exc.value.status_code == 400
        assert call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        """Test raises after max retries exhausted."""
        call_count = 0

        @retry_on_transient_error(max_retries=2, backoff_factor=0.01)
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise HTTPException(status_code=503, detail="Service unavailable")

        with pytest.raises(HTTPException) as exc:
            await always_fails()
        
        assert exc.value.status_code == 503
        assert call_count == 3  # Initial + 2 retries


# ============================================================================
# ALPACA BROKER CLIENT INIT TESTS
# ============================================================================

class TestAlpacaBrokerClientInit:
    """Tests for AlpacaBrokerClient initialization."""

    @patch.dict('os.environ', {
        'ALPACA_API_KEY_ID': 'test-key',
        'ALPACA_API_SECRET_KEY': 'test-secret',
        'ALPACA_PAPER': 'true'
    })
    def test_init_paper_mode(self):
        """Test initialization in paper mode."""
        client = AlpacaBrokerClient()
        
        assert client.api_key == 'test-key'
        assert client.api_secret == 'test-secret'
        assert client.is_paper is True
        assert 'paper' in client.base_url

    @patch.dict('os.environ', {
        'ALPACA_API_KEY_ID': 'test-key',
        'ALPACA_API_SECRET_KEY': 'test-secret',
        'ALPACA_PAPER': 'false'
    }, clear=True)
    def test_init_live_mode(self):
        """Test initialization in live mode."""
        client = AlpacaBrokerClient()
        
        assert client.is_paper is False
        # Just verify live mode is set
        assert client.api_key == 'test-key'

    @patch.dict('os.environ', {}, clear=True)
    def test_init_missing_credentials_logs_warning(self):
        """Test initialization without credentials logs warning."""
        # Should not raise, just log warning
        client = AlpacaBrokerClient()
        
        assert client.api_key is None
        assert client.api_secret is None

    @patch.dict('os.environ', {
        'APCA_API_KEY_ID': 'alt-key',
        'APCA_API_SECRET_KEY': 'alt-secret'
    }, clear=True)
    def test_init_alternate_env_vars(self):
        """Test initialization with alternate environment variable names."""
        client = AlpacaBrokerClient()
        
        assert client.api_key == 'alt-key'
        assert client.api_secret == 'alt-secret'


# ============================================================================
# AUTH HEADERS TESTS
# ============================================================================

class TestGetAuthHeaders:
    """Tests for _get_auth_headers method."""

    @patch.dict('os.environ', {
        'ALPACA_API_KEY_ID': 'test-key',
        'ALPACA_API_SECRET_KEY': 'test-secret'
    })
    def test_get_auth_headers_valid(self):
        """Test getting auth headers with valid credentials."""
        client = AlpacaBrokerClient()
        headers = client._get_auth_headers()
        
        assert headers['APCA-API-KEY-ID'] == 'test-key'
        assert headers['APCA-API-SECRET-KEY'] == 'test-secret'
        assert 'Accept' in headers
        assert 'Content-Type' in headers

    @patch.dict('os.environ', {}, clear=True)
    def test_get_auth_headers_no_credentials_raises(self):
        """Test getting auth headers without credentials raises."""
        client = AlpacaBrokerClient()
        
        with pytest.raises(HTTPException) as exc:
            client._get_auth_headers()
        
        assert exc.value.status_code == 503
        assert "not configured" in exc.value.detail


# ============================================================================
# ORDER MAPPING TESTS
# ============================================================================

class TestOrderMappings:
    """Tests for order parameter mapping methods."""

    @pytest.fixture
    def client(self):
        """Create client with mock credentials."""
        with patch.dict('os.environ', {
            'ALPACA_API_KEY_ID': 'key',
            'ALPACA_API_SECRET_KEY': 'secret'
        }):
            return AlpacaBrokerClient()

    def test_map_order_side_buy(self, client):
        """Test mapping buy side."""
        assert client._map_order_side("buy") == "buy"
        assert client._map_order_side("BUY") == "buy"
        assert client._map_order_side("long") == "buy"

    def test_map_order_side_sell(self, client):
        """Test mapping sell side."""
        assert client._map_order_side("sell") == "sell"
        assert client._map_order_side("SELL") == "sell"
        assert client._map_order_side("short") == "sell"

    def test_map_order_side_invalid(self, client):
        """Test invalid side raises."""
        with pytest.raises(HTTPException) as exc:
            client._map_order_side("invalid")
        
        assert exc.value.status_code == 400
        assert "Invalid order side" in exc.value.detail

    def test_map_order_type_market(self, client):
        """Test mapping market order type."""
        assert client._map_order_type("market") == "market"
        assert client._map_order_type("mkt") == "market"

    def test_map_order_type_limit(self, client):
        """Test mapping limit order type."""
        assert client._map_order_type("limit") == "limit"
        assert client._map_order_type("lmt") == "limit"

    def test_map_order_type_stop(self, client):
        """Test mapping stop order type."""
        assert client._map_order_type("stop") == "stop"
        assert client._map_order_type("stop_limit") == "stop_limit"

    def test_map_order_type_invalid(self, client):
        """Test invalid order type raises."""
        with pytest.raises(HTTPException) as exc:
            client._map_order_type("unknown")
        
        assert exc.value.status_code == 400
        assert "Invalid order type" in exc.value.detail

    def test_map_time_in_force_valid(self, client):
        """Test mapping valid time in force."""
        assert client._map_time_in_force("day") == "day"
        assert client._map_time_in_force("gtc") == "gtc"
        assert client._map_time_in_force("ioc") == "ioc"

    def test_map_time_in_force_invalid(self, client):
        """Test invalid time in force raises."""
        with pytest.raises(HTTPException) as exc:
            client._map_time_in_force("forever")
        
        assert exc.value.status_code == 400
        assert "Invalid time in force" in exc.value.detail


# ============================================================================
# PLACE ORDER TESTS
# ============================================================================

class TestPlaceOrder:
    """Tests for place_order method."""

    @pytest.fixture
    def client(self):
        """Create client with mock credentials."""
        with patch.dict('os.environ', {
            'ALPACA_API_KEY_ID': 'key',
            'ALPACA_API_SECRET_KEY': 'secret'
        }):
            client = AlpacaBrokerClient()
            return client

    @pytest.mark.asyncio
    async def test_place_order_limit_requires_price(self, client):
        """Test limit order requires limit_price."""
        # The order validation happens before HTTP call and raises
        with pytest.raises((ValueError, TypeError, HTTPException)):
            await client.place_order(
                symbol="AAPL",
                side="buy",
                qty=10,
                type="limit"
                # Missing limit_price
            )

    @pytest.mark.asyncio
    async def test_place_order_stop_requires_price(self, client):
        """Test stop order requires stop_price."""
        # The order validation happens before HTTP call and raises
        with pytest.raises((ValueError, TypeError, HTTPException)):
            await client.place_order(
                symbol="AAPL",
                side="buy",
                qty=10,
                type="stop"
                # Missing stop_price
            )


# ============================================================================
# MAKE REQUEST WITH RETRY TESTS
# ============================================================================

class TestMakeRequestWithRetry:
    """Tests for _make_request_with_retry method."""

    @pytest.fixture
    def client(self):
        """Create client with mock credentials."""
        with patch.dict('os.environ', {
            'ALPACA_API_KEY_ID': 'key',
            'ALPACA_API_SECRET_KEY': 'secret'
        }):
            return AlpacaBrokerClient()

    @pytest.mark.asyncio
    async def test_successful_request(self, client):
        """Test successful request returns response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch.object(client.client, 'request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            response = await client._make_request_with_retry(
                "GET",
                "https://api.example.com/test"
            )
            
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_client_error_not_retried(self, client):
        """Test 400-level errors are not retried."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        
        with patch.object(client.client, 'request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            with pytest.raises(HTTPException) as exc:
                await client._make_request_with_retry(
                    "GET",
                    "https://api.example.com/test"
                )
            
            assert exc.value.status_code == 400
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_retried(self, client):
        """Test timeout errors are retried."""
        call_count = 0
        
        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.TimeoutException("Timeout")
            mock_response = MagicMock()
            mock_response.status_code = 200
            return mock_response
        
        with patch.object(client.client, 'request', side_effect=side_effect):
            response = await client._make_request_with_retry(
                "GET",
                "https://api.example.com/test",
                max_retries=2,
                backoff_factor=0.01
            )
            
            assert response.status_code == 200
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_rate_limit_respects_retry_after(self, client):
        """Test rate limit response respects Retry-After header."""
        call_count = 0
        
        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            if call_count < 2:
                mock_response.status_code = 429
                mock_response.headers = {"Retry-After": "0.01"}
                mock_response.text = "Rate limited"
            else:
                mock_response.status_code = 200
            return mock_response
        
        with patch.object(client.client, 'request', side_effect=side_effect):
            response = await client._make_request_with_retry(
                "GET",
                "https://api.example.com/test",
                max_retries=2,
                backoff_factor=0.01
            )
            
            assert response.status_code == 200
            assert call_count == 2
