"""
Alpaca Data Client Implementation

This module provides integration with Alpaca's Market Data API v2 for fetching
historical market data. Used when USE_MOCK_DATA=False to get real market data.
"""

import asyncio
from datetime import datetime, timedelta, timezone
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

    async def _latest_historical_bars(
        self, symbol: str, lookback: int, timeframe: str,
    ) -> list[dict]:
        """Read the latest requested bars, then expose chronological history.

        Alpaca limits each page, not the entire time window. Starting at the
        newest end prevents a large intraday window from selecting an old first
        page. Follow tokens when the provider returns fewer rows than requested.
        """
        if lookback <= 0:
            return []
        tf_lower = timeframe.lower()
        if "min" in tf_lower or "hour" in tf_lower:
            bars_per_day = 26 if "15" in tf_lower else (390 if "1min" in tf_lower else 78)
            buffer_days = max(int((lookback / bars_per_day) * 1.6) + 2, 5)
        else:
            buffer_days = max(int(lookback * 1.4), 1)
        end = datetime.now(timezone.utc)
        params = {
            "start": (end - timedelta(days=buffer_days)).isoformat(),
            "end": end.isoformat(),
            "timeframe": timeframe,
            "adjustment": "split",
            "limit": min(lookback * 2, 10000),
            "sort": "desc",
            "feed": os.getenv("ALPACA_DATA_FEED", "sip"),
        }
        url = f"{self.base_url}/stocks/{symbol.upper()}/bars"
        headers = self._get_auth_headers()
        by_timestamp: dict[pd.Timestamp, dict] = {}
        seen_tokens: set[str] = set()
        # A broken provider must not create an unbounded request loop.
        for _ in range(100):
            response = await self._request_with_retry(
                "GET", url, params=dict(params), headers=headers,
            )
            if response.status_code != 200:
                error_detail = f"Alpaca API error: {response.status_code}"
                try:
                    message = response.json().get("message")
                    if message:
                        error_detail += f" - {message}"
                except Exception:
                    error_detail += f" - {response.text[:200]}"
                raise HTTPException(status_code=502, detail=error_detail)
            data = response.json()
            for bar in data.get("bars") or []:
                timestamp = pd.Timestamp(bar.get("t"))
                if pd.isna(timestamp) or timestamp.tzinfo is None:
                    raise ValueError("historical bar timestamp must be timezone-aware")
                timestamp = timestamp.tz_convert("UTC")
                if timestamp > end:
                    raise ValueError("historical bar timestamp is after request end")
                # Overlapping pages must not duplicate bars. Keep the newest
                # page's representation if the provider repeats a boundary.
                by_timestamp.setdefault(timestamp, {**bar, "t": timestamp.isoformat()})
            token = data.get("next_page_token")
            if len(by_timestamp) >= lookback or not token:
                timestamps = sorted(by_timestamp)[-lookback:]
                return [by_timestamp[timestamp] for timestamp in timestamps]
            if not isinstance(token, str) or token in seen_tokens:
                raise ValueError("invalid or repeated historical page token")
            seen_tokens.add(token)
            params["page_token"] = token
        raise ValueError("historical pagination exceeded 100 pages")

    async def get_historical_closes(
        self, symbol: str, lookback: int = 200, timeframe: str = "1Day",
    ) -> list[float]:
        """Return up to lookback latest closing prices, oldest first."""
        try:
            bars = await self._latest_historical_bars(symbol, lookback, timeframe)
            return [float(bar["c"]) for bar in bars]
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Unexpected error fetching historical data", symbol=symbol,
                         error=str(exc), error_type=type(exc).__name__)
            raise HTTPException(status_code=502, detail=f"Failed to fetch historical data: {exc}")

    async def get_historical_bars_df(
        self, symbol: str, lookback: int = 200, timeframe: str = "1Day",
    ) -> pd.DataFrame:
        """Return latest normalized OHLCV bars in chronological UTC order."""
        columns = ["timestamp", "open", "high", "low", "close", "volume"]
        try:
            bars = await self._latest_historical_bars(symbol, lookback, timeframe)
            rows = [{
                "timestamp": bar["t"],
                **{name: float(bar[key]) if bar.get(key) is not None else None
                   for name, key in (("open", "o"), ("high", "h"), ("low", "l"),
                                     ("close", "c"), ("volume", "v"))},
            } for bar in bars]
            return pd.DataFrame(rows, columns=columns)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Unexpected error fetching historical bars", symbol=symbol,
                         error=str(exc), error_type=type(exc).__name__)
            raise HTTPException(status_code=502, detail=f"Failed to fetch historical bars: {exc}")

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
