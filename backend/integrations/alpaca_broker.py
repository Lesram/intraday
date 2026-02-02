"""
Alpaca Broker Client Implementation

This module provides integration with Alpaca's Trading API for paper and live trading.
Used when USE_MOCK_BROKER=False to place real orders through Alpaca.
"""

import asyncio
from collections.abc import Callable
from functools import wraps
import os
from typing import Any, TypeVar
import uuid

from fastapi import HTTPException
import httpx

from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)

T = TypeVar('T')


# L-23: Use tuple constant for status codes to avoid dynamic list overhead
RETRYABLE_STATUS_CODES: tuple[int, ...] = (429, 500, 502, 503, 504)


def retry_on_transient_error(
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    retryable_status_codes: tuple[int, ...] = RETRYABLE_STATUS_CODES
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to retry async functions on transient HTTP errors.
    
    Args:
        max_retries: Maximum number of retry attempts
        backoff_factor: Base delay multiplier (exponential backoff)
        retryable_status_codes: HTTP status codes to retry on
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except HTTPException as e:
                    if e.status_code not in retryable_status_codes:
                        raise
                    last_exception = e
                    if attempt < max_retries:
                        delay = backoff_factor * (2 ** attempt)
                        logger.warning(
                            f"Retrying {func.__name__} after {delay:.1f}s",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            status_code=e.status_code
                        )
                        await asyncio.sleep(delay)
                except (httpx.TransportError, httpx.TimeoutException) as e:
                    last_exception = HTTPException(status_code=503, detail=str(e))
                    if attempt < max_retries:
                        delay = backoff_factor * (2 ** attempt)
                        logger.warning(
                            f"Retrying {func.__name__} after transport error",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            error=str(e)
                        )
                        await asyncio.sleep(delay)
            raise last_exception
        return wrapper
    return decorator


class AlpacaBrokerClient:
    """
    Alpaca Trading API client for order management.

    Provides methods to place, retrieve, and cancel orders through Alpaca's trading API.
    Automatically routes to paper or live trading based on ALPACA_PAPER setting.
    """

    def __init__(self):
        """Initialize Alpaca Broker Client with configuration from environment."""
        # Try both naming conventions for backward compatibility
        self.api_key = (os.getenv("ALPACA_API_KEY_ID") or
                       os.getenv("ALPACA_API_KEY") or
                       os.getenv("APCA_API_KEY_ID"))
        self.api_secret = (os.getenv("ALPACA_API_SECRET_KEY") or
                          os.getenv("ALPACA_SECRET_KEY") or
                          os.getenv("APCA_API_SECRET_KEY"))
        self.is_paper = os.getenv("ALPACA_PAPER", "true").lower() in ("true", "1", "yes")

        # Set base URL based on paper/live mode
        if self.is_paper:
            self.base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        else:
            self.base_url = os.getenv("ALPACA_BASE_URL", "https://api.alpaca.markets")

        if not self.api_key or not self.api_secret:
            logger.warning("Alpaca API credentials not configured",
                         api_key_present=bool(self.api_key),
                         api_secret_present=bool(self.api_secret),
                         is_paper=self.is_paper)

        logger.info("Alpaca broker client initialized",
                   is_paper=self.is_paper,
                   base_url=self.base_url)

        # HTTP client with timeout and connection limits
        # L-20: Enable HTTP/2 for better performance
        # L-21: Increased connection pool for HFT workloads
        self.client = httpx.AsyncClient(
            timeout=30.0,
            http2=True,  # L-20: Enable HTTP/2 multiplexing for reduced latency
            limits=httpx.Limits(max_keepalive_connections=50, max_connections=100)
        )

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
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    async def _make_request_with_retry(
        self,
        method: str,
        url: str,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        **kwargs
    ) -> httpx.Response:
        """Make an HTTP request with automatic retry on transient errors.
        
        Retries on:
        - 429 Too Many Requests (rate limiting)
        - 500, 502, 503, 504 Server errors
        - Connection errors and timeouts
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            url: Full URL to request
            max_retries: Maximum number of retry attempts
            backoff_factor: Base delay multiplier for exponential backoff
            **kwargs: Additional arguments passed to httpx request
            
        Returns:
            httpx.Response on success
            
        Raises:
            HTTPException: After all retries exhausted or on non-retryable error
        """
        retryable_status_codes = (429, 500, 502, 503, 504)
        last_exception: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = await self.client.request(
                    method,
                    url,
                    headers=self._get_auth_headers(),
                    **kwargs
                )

                # Success - return immediately
                if response.status_code < 400:
                    return response

                # Non-retryable client error
                if 400 <= response.status_code < 500 and response.status_code not in retryable_status_codes:
                    error_detail = response.text
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Alpaca API error: {error_detail}"
                    )

                # Retryable status code
                if response.status_code in retryable_status_codes:
                    if attempt < max_retries:
                        delay = backoff_factor * (2 ** attempt)
                        # Check for Retry-After header (rate limiting)
                        if response.status_code == 429:
                            retry_after = response.headers.get("Retry-After")
                            if retry_after:
                                delay = max(delay, float(retry_after))
                        logger.warning(
                            "Retryable Alpaca API error",
                            status_code=response.status_code,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            delay=delay
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        raise HTTPException(
                            status_code=response.status_code,
                            detail=f"Alpaca API error after {max_retries} retries: {response.text}"
                        )

            except httpx.TimeoutException as e:
                last_exception = e
                if attempt < max_retries:
                    delay = backoff_factor * (2 ** attempt)
                    logger.warning(
                        "Alpaca request timeout, retrying",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay=delay
                    )
                    await asyncio.sleep(delay)
                    continue

            except httpx.ConnectError as e:
                last_exception = e
                if attempt < max_retries:
                    delay = backoff_factor * (2 ** attempt)
                    logger.warning(
                        "Alpaca connection error, retrying",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay=delay,
                        error=str(e)
                    )
                    await asyncio.sleep(delay)
                    continue

            except HTTPException:
                # Re-raise HTTP exceptions (non-retryable)
                raise

            except Exception as e:
                last_exception = e
                logger.error("Unexpected error in Alpaca request", error=str(e))
                raise HTTPException(
                    status_code=503,
                    detail=f"Alpaca API connection error: {e}"
                )

        # All retries exhausted
        raise HTTPException(
            status_code=503,
            detail=f"Alpaca API unavailable after {max_retries} retries: {last_exception}"
        )

    def _map_order_side(self, side: str) -> str:
        """Map internal order side to Alpaca format."""
        side_lower = side.lower()
        if side_lower in ("buy", "long"):
            return "buy"
        elif side_lower in ("sell", "short"):
            return "sell"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid order side: {side}. Must be 'buy' or 'sell'"
            )

    def _map_order_type(self, order_type: str) -> str:
        """Map internal order type to Alpaca format."""
        type_lower = order_type.lower()
        alpaca_types = ["market", "limit", "stop", "stop_limit", "trailing_stop"]

        if type_lower in alpaca_types:
            return type_lower
        elif type_lower == "mkt":
            return "market"
        elif type_lower == "lmt":
            return "limit"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid order type: {order_type}. Must be one of {alpaca_types}"
            )

    def _map_time_in_force(self, tif: str) -> str:
        """Map time in force to Alpaca format."""
        tif_lower = tif.lower()
        alpaca_tifs = ["day", "gtc", "opg", "cls", "ioc", "fok"]

        if tif_lower in alpaca_tifs:
            return tif_lower
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid time in force: {tif}. Must be one of {alpaca_tifs}"
            )

    async def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        type: str = "market",
        tif: str = "day",
        limit_price: float | None = None,
        stop_price: float | None = None,
        client_order_id: str | None = None
    ) -> dict:
        """
        Place an order with Alpaca.

        Args:
            symbol: Stock symbol (e.g., 'AAPL', 'MSFT')
            side: Order side ('buy' or 'sell')
            qty: Order quantity (number of shares)
            type: Order type ('market', 'limit', 'stop', 'stop_limit')
            tif: Time in force ('day', 'gtc', etc.)
            limit_price: Limit price for limit/stop_limit orders
            stop_price: Stop price for stop/stop_limit orders
            client_order_id: Optional client order ID for idempotency

        Returns:
            Dict containing order details from Alpaca API

        Raises:
            HTTPException: On API errors or validation failures
            ValueError: On missing required parameters for order type
        """
        try:
            # Validate and map parameters
            alpaca_side = self._map_order_side(side)
            alpaca_type = self._map_order_type(type)
            alpaca_tif = self._map_time_in_force(tif)

            # Validate order type requirements
            if type in ["limit", "stop_limit"]:
                if limit_price is None:
                    raise ValueError(
                        f"Limit orders require a limit_price. "
                        f"Order: {symbol} {side} {qty} shares"
                    )

            if type in ["stop", "stop_limit"]:
                if stop_price is None:
                    raise ValueError(
                        f"Stop orders require a stop_price. "
                        f"Order: {symbol} {side} {qty} shares"
                    )

            # Generate client order ID if not provided
            if not client_order_id:
                client_order_id = f"order_{uuid.uuid4().hex[:8]}"

            # IDEMPOTENCY CHECK: Before placing order, check if it already exists
            # This prevents "422: client_order_id must be unique" errors on retries
            try:
                existing_order = await self.get_order(client_order_id)
                if existing_order:
                    logger.info("Order already exists (idempotent response)",
                               client_order_id=client_order_id,
                               alpaca_order_id=existing_order.get("id"),
                               status=existing_order.get("status"))
                    return existing_order
            except HTTPException as e:
                # 404, 422, or 502 means order doesn't exist - proceed with placement
                # 422 occurs when client_order_id format isn't recognized as valid Alpaca order ID
                # 502 is how get_order() wraps Alpaca 422 errors
                if e.status_code not in [404, 422, 502]:
                    # Other errors should be raised
                    raise
                # 404/422/502 is expected - order doesn't exist yet, proceed with placement
                logger.debug("Order does not exist yet, proceeding with placement",
                            client_order_id=client_order_id,
                            status_code=e.status_code)

            # Build order payload
            order_data = {
                "symbol": symbol.upper(),
                "side": alpaca_side,
                "type": alpaca_type,
                "time_in_force": alpaca_tif,
                "qty": str(qty),  # Alpaca expects string
                "client_order_id": client_order_id
            }

            # Add limit_price if provided
            if limit_price is not None:
                order_data["limit_price"] = str(limit_price)

            # Add stop_price if provided
            if stop_price is not None:
                order_data["stop_price"] = str(stop_price)

            logger.info("Placing order with Alpaca",
                       symbol=symbol,
                       side=alpaca_side,
                       qty=qty,
                       type=alpaca_type,
                       client_order_id=client_order_id,
                       is_paper=self.is_paper)

            # Make API request with retry for transient errors
            response = await self._make_request_with_retry(
                "POST",
                f"{self.base_url}/v2/orders",
                json=order_data
            )

            # Handle API response
            if response.status_code in (200, 201):
                order_result = response.json()
                logger.info("Order placed successfully",
                           order_id=order_result.get("id"),
                           status_code=response.status_code,
                           client_order_id=client_order_id,
                           status=order_result.get("status"))
                return order_result

            elif response.status_code in (400, 422):
                # Client error - invalid request
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": response.text}
                error_msg = error_data.get("message", "Invalid order request")

                # Special handling for duplicate client_order_id
                if response.status_code == 422 and "client_order_id" in error_msg.lower() and "unique" in error_msg.lower():
                    logger.warning("Duplicate client_order_id detected (should have been caught by idempotency check)",
                                 status_code=response.status_code,
                                 error=error_msg,
                                 client_order_id=client_order_id)
                    # Try to fetch the existing order
                    try:
                        existing_order = await self.get_order(client_order_id)
                        logger.info("Retrieved existing order after duplicate error",
                                   client_order_id=client_order_id,
                                   order_id=existing_order.get("id"))
                        return existing_order
                    except Exception as fetch_err:
                        logger.error("Failed to fetch existing order after duplicate error",
                                    client_order_id=client_order_id,
                                    error=str(fetch_err))

                logger.warning("Order rejected by Alpaca",
                             status_code=response.status_code,
                             error=error_msg,
                             client_order_id=client_order_id)
                raise HTTPException(status_code=response.status_code, detail=error_msg)

            else:
                # Server error or other issues
                error_msg = f"Alpaca API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg += f" - {error_data['message']}"
                except Exception:
                    error_msg += f" - {response.text[:200]}"

                logger.error("Order placement failed",
                           status_code=response.status_code,
                           error=error_msg,
                           client_order_id=client_order_id)
                raise HTTPException(status_code=502, detail=error_msg)

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error("Unexpected error placing order",
                        symbol=symbol,
                        side=side,
                        qty=qty,
                        error=str(e),
                        error_type=type(e).__name__)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to place order: {str(e)}"
            )

    async def get_order(self, order_id: str) -> dict:
        """
        Retrieve order details by order ID.

        Args:
            order_id: Alpaca order ID or client order ID

        Returns:
            Dict containing order details

        Raises:
            HTTPException: On API errors or if order not found
        """
        try:
            logger.info("Retrieving order from Alpaca", order_id=order_id)

            # Try to get order by Alpaca order ID first
            url = f"{self.base_url}/v2/orders/{order_id}"

            try:
                response = await self._make_request_with_retry("GET", url)
            except HTTPException as e:
                if e.status_code != 404:
                    raise
                response = None

            if response and response.status_code == 200:
                order_data = response.json()
                logger.info("Order retrieved successfully",
                           order_id=order_id,
                           status=order_data.get("status"),
                           symbol=order_data.get("symbol"))
                return order_data

            if response is None or response.status_code == 404:
                # Try by client_order_id if direct lookup failed
                try:
                    list_url = f"{self.base_url}/v2/orders"
                    params = {"status": "all", "limit": 100}
                    list_response = await self._make_request_with_retry("GET", list_url, params=params)

                    if list_response.status_code == 200:
                        orders = list_response.json()
                        for order in orders:
                            if order.get("client_order_id") == order_id:
                                logger.info("Order found by client_order_id",
                                           client_order_id=order_id,
                                           alpaca_order_id=order.get("id"))
                                return order
                except Exception as e:
                    logger.warning("Failed to search by client_order_id", error=str(e))

                logger.warning("Order not found", order_id=order_id)
                raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")

            else:
                error_msg = f"Alpaca API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg += f" - {error_data['message']}"
                except Exception:
                    error_msg += f" - {response.text[:200]}"

                logger.error("Failed to retrieve order",
                           order_id=order_id,
                           status_code=response.status_code,
                           error=error_msg)
                raise HTTPException(status_code=502, detail=error_msg)

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error("Unexpected error retrieving order",
                        order_id=order_id,
                        error=str(e),
                        error_type=type(e).__name__)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to retrieve order: {str(e)}"
            )

    async def cancel_order(self, order_id: str) -> None:
        """
        Cancel an order by order ID.

        Args:
            order_id: Alpaca order ID or client order ID

        Raises:
            HTTPException: On API errors or if order cannot be canceled
        """
        try:
            logger.info("Canceling order with Alpaca", order_id=order_id)

            url = f"{self.base_url}/v2/orders/{order_id}"

            response = await self._make_request_with_retry("DELETE", url)

            if response.status_code == 204:
                logger.info("Order canceled successfully", order_id=order_id)
                return

            elif response.status_code == 404:
                logger.warning("Order not found for cancellation", order_id=order_id)
                raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")

            elif response.status_code == 422:
                # Order cannot be canceled (already filled, etc.)
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": "Cannot cancel order"}
                error_msg = error_data.get("message", "Order cannot be canceled")
                logger.warning("Order cancellation rejected",
                             order_id=order_id,
                             error=error_msg)
                raise HTTPException(status_code=422, detail=error_msg)

            else:
                error_msg = f"Alpaca API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg += f" - {error_data['message']}"
                except Exception:
                    error_msg += f" - {response.text[:200]}"

                logger.error("Order cancellation failed",
                           order_id=order_id,
                           status_code=response.status_code,
                           error=error_msg)
                raise HTTPException(status_code=502, detail=error_msg)

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error("Unexpected error canceling order",
                        order_id=order_id,
                        error=str(e),
                        error_type=type(e).__name__)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to cancel order: {str(e)}"
            )

    async def get_account(self) -> dict:
        """
        Get account information from Alpaca.

        Returns:
            Dict containing account details:
            - account_number: Account identifier
            - cash: Cash balance
            - portfolio_value: Total portfolio value
            - buying_power: Available buying power
            - equity: Total equity
            - last_equity: Previous day's equity
            - multiplier: Buying power multiplier
            - currency: Account currency
            - status: Account status

        Raises:
            HTTPException: On API errors
        """
        try:
            logger.info("Fetching account data from Alpaca", is_paper=self.is_paper)

            url = f"{self.base_url}/v2/account"

            response = await self._make_request_with_retry("GET", url)

            if response.status_code == 200:
                account_data = response.json()
                logger.info("Account data retrieved successfully",
                           account_number=account_data.get("account_number"),
                           cash=account_data.get("cash"),
                           portfolio_value=account_data.get("portfolio_value"),
                           buying_power=account_data.get("buying_power"))
                return account_data

            else:
                error_msg = f"Alpaca API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg += f" - {error_data['message']}"
                except Exception:
                    error_msg += f" - {response.text[:200]}"

                logger.error("Failed to retrieve account data",
                           status_code=response.status_code,
                           error=error_msg)
                raise HTTPException(status_code=502, detail=error_msg)

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Unexpected error retrieving account data",
                        error=str(e),
                        error_type=type(e).__name__)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to retrieve account data: {str(e)}"
            )

    async def get_positions(self) -> list[dict]:
        """
        Get all open positions from Alpaca.

        Returns:
            List of dicts containing position details:
            - symbol: Stock symbol
            - qty: Quantity (shares held)
            - avg_entry_price: Average entry price
            - current_price: Current market price
            - market_value: Current market value
            - cost_basis: Total cost basis
            - unrealized_pl: Unrealized profit/loss
            - unrealized_plpc: Unrealized P&L percentage
            - side: Position side (long/short)

        Raises:
            HTTPException: On API errors
        """
        try:
            logger.info("Fetching positions from Alpaca", is_paper=self.is_paper)

            url = f"{self.base_url}/v2/positions"

            response = await self._make_request_with_retry("GET", url)

            if response.status_code == 200:
                positions = response.json()
                logger.info("Positions retrieved successfully",
                           position_count=len(positions),
                           symbols=[p.get("symbol") for p in positions[:5]])  # Log first 5
                return positions

            else:
                error_msg = f"Alpaca API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg += f" - {error_data['message']}"
                except Exception:
                    error_msg += f" - {response.text[:200]}"

                logger.error("Failed to retrieve positions",
                           status_code=response.status_code,
                           error=error_msg)
                raise HTTPException(status_code=502, detail=error_msg)

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Unexpected error retrieving positions",
                        error=str(e),
                        error_type=type(e).__name__)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to retrieve positions: {str(e)}"
            )

    async def get_position(self, symbol: str) -> dict | None:
        """
        Get current position for a specific symbol from Alpaca.

        Args:
            symbol: Stock symbol (e.g., "AAPL")

        Returns:
            Dict containing position details or None if no position exists:
            - symbol: Stock symbol
            - qty: Quantity (shares held, can be negative for short)
            - avg_entry_price: Average entry price
            - current_price: Current market price
            - market_value: Current market value
            - cost_basis: Total cost basis
            - unrealized_pl: Unrealized profit/loss
            - unrealized_plpc: Unrealized P&L percentage
            - side: Position side (long/short)

        Raises:
            HTTPException: On API errors (except 404 which returns None)
        """
        try:
            logger.info(f"Fetching position for {symbol} from Alpaca", is_paper=self.is_paper)

            url = f"{self.base_url}/v2/positions/{symbol}"

            try:
                response = await self._make_request_with_retry("GET", url)
            except HTTPException as e:
                if e.status_code == 404:
                    # No position found - this is expected and not an error
                    logger.info(f"No position found for {symbol}")
                    return None
                raise

            if response.status_code == 200:
                position = response.json()
                logger.info(f"Position retrieved for {symbol}",
                           qty=position.get("qty"),
                           side=position.get("side"),
                           avg_entry=position.get("avg_entry_price"))
                return position

            elif response.status_code == 404:
                # No position found - this is expected and not an error
                logger.info(f"No position found for {symbol}")
                return None

            else:
                error_msg = f"Alpaca API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg += f" - {error_data['message']}"
                except Exception:
                    error_msg += f" - {response.text[:200]}"

                logger.error(f"Failed to retrieve position for {symbol}",
                           status_code=response.status_code,
                           error=error_msg)
                raise HTTPException(status_code=502, detail=error_msg)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving position for {symbol}",
                        error=str(e),
                        error_type=type(e).__name__)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to retrieve position: {str(e)}"
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
_broker_client: AlpacaBrokerClient | None = None


def get_alpaca_broker_client() -> AlpacaBrokerClient:
    """
    Get or create global AlpacaBrokerClient instance.

    Returns:
        AlpacaBrokerClient instance for making trading API requests
    """
    global _broker_client
    if _broker_client is None:
        _broker_client = AlpacaBrokerClient()
    return _broker_client


async def cleanup_alpaca_broker_client():
    """Clean up global broker client resources."""
    global _broker_client
    if _broker_client:
        await _broker_client.close()
        _broker_client = None
