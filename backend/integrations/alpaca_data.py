"""
Alpaca Data Client Implementation

This module provides integration with Alpaca's Market Data API v2 for fetching
historical market data. Used when USE_MOCK_DATA=False to get real market data.
"""

import asyncio
from datetime import datetime, timedelta
import os

from fastapi import HTTPException
import httpx

import pandas as pd

from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)

# §14.3 FIX: Retry configuration for transient failures
_DATA_CLIENT_MAX_RETRIES = 2      # HFT: fewer retries, fail fast (was 3)
_DATA_CLIENT_RETRY_BACKOFF = 0.2  # HFT: 200ms base (was 500ms)
_RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class AlpacaDataClient:
    """
    Alpaca Market Data API v2 client for historical data retrieval.

    Provides methods to fetch historical market data using Alpaca's v2 bars endpoint.
    Requires ALPACA_API_KEY_ID (or ALPACA_API_KEY) and ALPACA_API_SECRET_KEY for authentication.
    """

    def __init__(self):
        """Initialize Alpaca Data Client with configuration from environment."""
        self.base_url = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets/v2")
        # §12.8 FIX: Accept both ALPACA_API_KEY_ID and ALPACA_API_KEY for compatibility
        self.api_key = os.getenv("ALPACA_API_KEY_ID") or os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
        self.api_secret = os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")

        if not self.api_key or not self.api_secret:
            logger.warning("Alpaca API credentials not configured",
                         api_key_present=bool(self.api_key),
                         api_secret_present=bool(self.api_secret))

        # HTTP client with timeout and connection limits
        # L-21: Increased connection pool for HFT workloads
        self.client = httpx.AsyncClient(
            timeout=10.0,  # HFT: fail fast (was 30s)
            limits=httpx.Limits(max_keepalive_connections=50, max_connections=100)
        )

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        """§14.3 FIX: Make HTTP request with exponential backoff retry.

        Retries on transient status codes (429, 5xx) up to MAX_RETRIES times.
        """
        last_exc: Exception | None = None
        for attempt in range(_DATA_CLIENT_MAX_RETRIES):
            try:
                response = await self.client.request(
                    method, url, params=params, headers=headers
                )
                if response.status_code not in _RETRIABLE_STATUS_CODES:
                    return response
                # Retriable status — log and retry
                logger.warning(
                    "Alpaca data API returned retriable status",
                    status_code=response.status_code,
                    attempt=attempt + 1,
                    max_retries=_DATA_CLIENT_MAX_RETRIES,
                )
                if attempt < _DATA_CLIENT_MAX_RETRIES - 1:
                    backoff = _DATA_CLIENT_RETRY_BACKOFF * (2 ** attempt)
                    await asyncio.sleep(backoff)
                else:
                    return response  # Return last response on final attempt
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
                last_exc = exc
                logger.warning(
                    "Alpaca data API transient error",
                    error=str(exc),
                    attempt=attempt + 1,
                )
                if attempt < _DATA_CLIENT_MAX_RETRIES - 1:
                    backoff = _DATA_CLIENT_RETRY_BACKOFF * (2 ** attempt)
                    await asyncio.sleep(backoff)
        # Should not reach here, but safety net
        raise last_exc or HTTPException(status_code=502, detail="Data client retry exhausted")

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers for Alpaca API requests."""
        if not self.api_key or not self.api_secret:
            raise HTTPException(
                status_code=503,
                detail="Alpaca API credentials not configured"
            )

        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
            "Accept": "application/json"
        }

    async def get_historical_closes(
        self,
        symbol: str,
        lookback: int = 200,
        timeframe: str = "1Day"
    ) -> list[float]:
        """
        Fetch historical closing prices for a symbol.

        Args:
            symbol: Stock symbol (e.g., 'AAPL', 'MSFT')
            lookback: Number of periods to look back (default: 200)
            timeframe: Data timeframe - '1Day', '1Hour', '5Min' etc. (default: '1Day')

        Returns:
            List of closing prices in chronological order (oldest first)

        Raises:
            HTTPException(502): If Alpaca API returns non-200 response
            HTTPException(503): If API credentials are not configured
        """
        try:
            # Calculate start date based on lookback period
            # Intraday timeframes need more calendar days to get enough bars
            tf_lower = timeframe.lower()
            if "min" in tf_lower or "hour" in tf_lower:
                bars_per_day = 26 if "15" in tf_lower else (390 if "1min" in tf_lower else 78)
                buffer_days = max(int((lookback / bars_per_day) * 1.6) + 2, 5)
            else:
                buffer_days = int(lookback * 1.4)  # ~40% buffer for non-trading days
            start_date = datetime.now() - timedelta(days=buffer_days)
            end_date = datetime.now()

            # Format dates for API (ISO format)
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")

            # Build API URL for v2 bars endpoint
            url = f"{self.base_url}/stocks/{symbol.upper()}/bars"

            # API parameters
            # Use SIP feed for Algo Trader Plus (full market coverage, all US exchanges)
            feed = os.getenv("ALPACA_DATA_FEED", "sip")
            params = {
                "start": start_str,
                "end": end_str,
                "timeframe": timeframe,
                "adjustment": "split",  # Use split-adjusted prices for correct return calculations
                "limit": lookback * 2,  # Request more than needed to account for filtering
                "sort": "asc",  # Chronological order (oldest first)
                "feed": feed  # SIP for Algo Trader Plus, IEX for free accounts
            }

            logger.info("Fetching historical data from Alpaca",
                       symbol=symbol,
                       lookback=lookback,
                       timeframe=timeframe,
                       start_date=start_str,
                       end_date=end_str)

            # Make API request with retry (§14.3 FIX)
            headers = self._get_auth_headers()
            response = await self._request_with_retry("GET", url, params=params, headers=headers)

            # Check for API errors
            if response.status_code != 200:
                error_detail = f"Alpaca API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_detail += f" - {error_data['message']}"
                except Exception:
                    error_detail += f" - {response.text[:200]}"

                logger.error("Alpaca API request failed",
                           status_code=response.status_code,
                           symbol=symbol,
                           error=error_detail)

                raise HTTPException(status_code=502, detail=error_detail)

            # Parse response data
            data = response.json()
            bars = data.get("bars", [])

            if not bars:
                logger.warning("No historical data returned from Alpaca",
                             symbol=symbol,
                             lookback=lookback)
                return []

            # Extract closing prices (already in chronological order due to sort=asc)
            closes = [float(bar["c"]) for bar in bars]

            # Limit to requested lookback count (take most recent)
            if len(closes) > lookback:
                closes = closes[-lookback:]

            logger.info("Successfully fetched historical data",
                       symbol=symbol,
                       bars_received=len(bars),
                       closes_returned=len(closes),
                       date_range=f"{bars[0]['t']} to {bars[-1]['t']}" if bars else "N/A")

            return closes

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error("Unexpected error fetching historical data",
                        symbol=symbol,
                        error=str(e),
                        error_type=type(e).__name__)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch historical data: {str(e)}"
            )

    async def get_historical_bars_df(
        self,
        symbol: str,
        lookback: int = 200,
        timeframe: str = "1Day",
    ) -> pd.DataFrame:
        """Fetch historical bars and return a normalized OHLCV DataFrame.

        The returned DataFrame has columns: ['timestamp','open','high','low','close','volume']
        sorted ascending by timestamp.
        """
        try:
            # Calculate buffer days based on timeframe
            # Intraday: ~26 bars/day (6.5h * 4 per hour for 15Min), need more calendar days
            # Daily: ~1 bar/day, need ~1.4x buffer for weekends/holidays
            tf_lower = timeframe.lower()
            if "min" in tf_lower or "hour" in tf_lower:
                bars_per_day = 26 if "15" in tf_lower else (390 if "1min" in tf_lower else 78)
                buffer_days = max(int((lookback / bars_per_day) * 1.6) + 2, 5)
            else:
                buffer_days = int(lookback * 1.4)
            start_date = datetime.now() - timedelta(days=buffer_days)
            end_date = datetime.now()

            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")

            url = f"{self.base_url}/stocks/{symbol.upper()}/bars"
            feed = os.getenv("ALPACA_DATA_FEED", "sip")
            params = {
                "start": start_str,
                "end": end_str,
                "timeframe": timeframe,
                "adjustment": "split",  # Use split-adjusted prices
                "limit": lookback * 2,
                "sort": "asc",
                "feed": feed,
            }

            headers = self._get_auth_headers()
            response = await self._request_with_retry("GET", url, params=params, headers=headers)
            if response.status_code != 200:
                error_detail = f"Alpaca API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_detail += f" - {error_data['message']}"
                except Exception:
                    error_detail += f" - {response.text[:200]}"
                raise HTTPException(status_code=502, detail=error_detail)

            data = response.json()
            bars = data.get("bars", [])
            if not bars:
                return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

            rows = []
            for bar in bars:
                rows.append(
                    {
                        "timestamp": bar.get("t"),
                        "open": float(bar.get("o")) if bar.get("o") is not None else None,
                        "high": float(bar.get("h")) if bar.get("h") is not None else None,
                        "low": float(bar.get("l")) if bar.get("l") is not None else None,
                        "close": float(bar.get("c")) if bar.get("c") is not None else None,
                        "volume": float(bar.get("v")) if bar.get("v") is not None else None,
                    }
                )

            df = pd.DataFrame(rows)
            if df.empty:
                return df

            df = df.sort_values("timestamp").reset_index(drop=True)
            if len(df) > lookback:
                df = df.iloc[-lookback:].reset_index(drop=True)
            return df

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Unexpected error fetching historical bars",
                symbol=symbol,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch historical bars: {str(e)}",
            )

    async def close(self):
        """Close the HTTP client connection."""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Global client instance for dependency injection
_data_client: AlpacaDataClient | None = None


def get_alpaca_data_client() -> AlpacaDataClient:
    """
    Get or create global AlpacaDataClient instance.

    Returns:
        AlpacaDataClient instance for making data API requests
    """
    global _data_client
    if _data_client is None:
        _data_client = AlpacaDataClient()
    return _data_client


async def cleanup_alpaca_data_client():
    """Clean up global data client resources."""
    global _data_client
    if _data_client:
        await _data_client.close()
        _data_client = None
