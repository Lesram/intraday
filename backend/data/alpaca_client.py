"""
Alpaca API Client Module for Market Data & Trading.
Handles all interactions with Alpaca's trading and market data APIs.
Enhanced with comprehensive observability including tracing and metrics.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import time
from typing import Any

import pandas as pd

from backend.infra.logging import get_logger as get_structured_logger

# B2.5 - Observability imports
from backend.infra.observability import (
    record_alpaca_request,
    record_latency,
    trace_span,
)

try:
    from alpaca.data.historical import (
        CryptoHistoricalDataClient,
        StockHistoricalDataClient,
    )
    from alpaca.data.live import CryptoDataStream, StockDataStream
    from alpaca.data.requests import (
        CryptoBarsRequest,
        StockBarsRequest,
        StockLatestQuoteRequest,
    )
    from alpaca.data.timeframe import TimeFrame
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import (
        GetOrdersRequest,
        LimitOrderRequest,
        MarketOrderRequest,
    )

    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False

    # Mock classes for development
    class TradingClient:
        pass

    class StockHistoricalDataClient:
        pass

    class CryptoHistoricalDataClient:
        pass

    class StockDataStream:
        pass

    class CryptoDataStream:
        pass


from ..utils.helpers import validate_symbol
from ..utils.logger import audit_logger


@dataclass
class MarketData:
    """Market data structure."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None


@dataclass
class OrderResult:
    """Order execution result."""

    order_id: str
    symbol: str
    side: str
    quantity: float
    filled_quantity: float
    price: float | None
    status: str
    timestamp: datetime


class AlpacaClient:
    """
    Alpaca API client for market data and trading operations.
    Supports both paper and live trading modes.
    """

    def __init__(
        self, api_key: str, secret_key: str, paper: bool = True, test_mode: bool = False
    ):
        """
        Initialize Alpaca trading and data client.

        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            paper: Whether to use paper trading (True) or live trading (False)
            test_mode: Whether to skip real API calls for testing (True) or not (False)
        """
        if not ALPACA_AVAILABLE:
            raise ImportError(
                "alpaca-py library is not installed. Run: pip install alpaca-py"
            )

        self.logger = get_structured_logger("alpaca_client")
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self.test_mode = test_mode
        self.connected = False

        # Initialize clients
        self._init_clients()

        # Data streams
        self.stock_stream: StockDataStream | None = None
        self.crypto_stream: CryptoDataStream | None = None

        # Callbacks for real-time data
        self.data_callbacks: list[Callable] = []

    # Connection status is determined during client initialization

        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.2  # 200ms between requests

        self.logger.info(
            "Alpaca client initialized",
            paper_trading=self.paper,
            api_key_prefix=api_key[:8] + "...",
        )

    def _init_clients(self):
        """Initialize Alpaca API clients."""
        try:
            # Trading client
            self.trading_client = TradingClient(
                api_key=self.api_key, secret_key=self.secret_key, paper=self.paper
            )

            # Historical data clients
            self.stock_data_client = StockHistoricalDataClient(
                api_key=self.api_key, secret_key=self.secret_key
            )

            self.crypto_data_client = CryptoHistoricalDataClient(
                api_key=self.api_key, secret_key=self.secret_key
            )

            # Attempt a lightweight connection test unless in test mode
            if not self.test_mode:
                try:
                    account = self.trading_client.get_account()
                    self.connected = True

                    # Handle buying_power safely for both real and mock objects
                    buying_power_raw = getattr(account, "buying_power", 0.0) or 0.0
                    try:
                        buying_power = float(buying_power_raw)
                    except (TypeError, ValueError):
                        # Handle Mock objects or invalid values in test mode
                        buying_power = 0.0

                    self.logger.info(
                        "Connected to Alpaca",
                        account_number=getattr(account, "account_number", "unknown"),
                        buying_power=buying_power,
                    )
                except Exception as conn_err:
                    self.connected = False
                    msg = "Connection test failed"
                    self.logger.warning(msg, error=str(conn_err))
            else:
                # In test mode, default to disconnected state
                self.connected = False

        except Exception as e:
            self.logger.error("Failed to initialize Alpaca clients", error=str(e))
            if not self.test_mode:
                raise
            else:
                # In test mode, log error but continue with disconnected state
                self.connected = False
                self.logger.warning(
                    "Test mode: continuing despite initialization error; marked as disconnected"
                )

    async def connect_data_stream(
        self,
        symbols: list[str],
        on_bar: Callable | None = None,
        on_quote: Callable | None = None,
    ):
        """
        Subscribe to real-time market data for given symbols.

        Args:
            symbols: List of symbols to subscribe to
            on_bar: Callback function for bar data
            on_quote: Callback function for quote data
        """
        try:
            # Separate stock and crypto symbols
            stock_symbols = [s for s in symbols if "/" not in s]
            crypto_symbols = [s for s in symbols if "/" in s]

            # Stock data stream
            if stock_symbols:
                self.stock_stream = StockDataStream(
                    api_key=self.api_key,
                    secret_key=self.secret_key,
                    feed="iex",  # or 'sip' for more comprehensive data
                )

                if on_bar:
                    self.stock_stream.subscribe_bars(on_bar, *stock_symbols)
                if on_quote:
                    self.stock_stream.subscribe_quotes(on_quote, *stock_symbols)

            # Crypto data stream
            if crypto_symbols:
                self.crypto_stream = CryptoDataStream(
                    api_key=self.api_key, secret_key=self.secret_key
                )

                if on_bar:
                    self.crypto_stream.subscribe_bars(on_bar, *crypto_symbols)
                if on_quote:
                    self.crypto_stream.subscribe_quotes(on_quote, *crypto_symbols)

            # Start streams
            tasks = []
            if self.stock_stream:
                tasks.append(asyncio.create_task(self.stock_stream._run_forever()))
            if self.crypto_stream:
                tasks.append(asyncio.create_task(self.crypto_stream._run_forever()))

            if tasks:
                self.connected = True
                self.logger.info(
                    "Started data streams",
                    stock_symbols=stock_symbols,
                    crypto_symbols=crypto_symbols,
                )
                await asyncio.gather(*tasks)

        except Exception as e:
            self.logger.error("Failed to connect data stream", error=str(e))
            raise

    def get_historical_data(
        self,
        symbol: str,
        timeframe: str = "1Day",
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data for a symbol.

        Args:
            symbol: Symbol to fetch data for
            timeframe: Timeframe (1Min, 5Min, 15Min, 1Hour, 1Day)
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)
            limit: Maximum number of bars

        Returns:
            DataFrame with OHLCV data
        """
        try:
            if not validate_symbol(symbol):
                raise ValueError(f"Invalid symbol format: {symbol}")

            # Rate limiting
            self._rate_limit()

            # Convert timeframe string to TimeFrame object
            tf_map = {
                "1Min": TimeFrame.Minute,
                "5Min": TimeFrame(5, "Minute"),
                "15Min": TimeFrame(15, "Minute"),
                "1Hour": TimeFrame.Hour,
                "1Day": TimeFrame.Day,
            }

            if timeframe not in tf_map:
                raise ValueError(f"Unsupported timeframe: {timeframe}")

            timeframe_obj = tf_map[timeframe]

            # Default date range if not provided
            if not start:
                start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            if not end:
                end = datetime.now().strftime("%Y-%m-%d")

            # Determine if crypto or stock
            if "/" in symbol:
                # Crypto
                request = CryptoBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=timeframe_obj,
                    start=datetime.strptime(start, "%Y-%m-%d"),
                    end=datetime.strptime(end, "%Y-%m-%d"),
                    limit=limit,
                )
                bars = self.crypto_data_client.get_crypto_bars(request)
            else:
                # Stock
                request = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=timeframe_obj,
                    start=datetime.strptime(start, "%Y-%m-%d"),
                    end=datetime.strptime(end, "%Y-%m-%d"),
                    limit=limit,
                )
                bars = self.stock_data_client.get_stock_bars(request)

            # Convert to DataFrame
            df = bars.df

            if df.empty:
                self.logger.warning(
                    "No data returned",
                    symbol=symbol,
                    timeframe=timeframe,
                    start=start,
                    end=end,
                )
                return pd.DataFrame()

            # Reset index and clean up
            df = df.reset_index()
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            self.logger.info(
                "Retrieved historical data",
                symbol=symbol,
                timeframe=timeframe,
                rows=len(df),
                start=start,
                end=end,
            )

            return df

        except Exception as e:
            self.logger.error(
                "Failed to get historical data", symbol=symbol, error=str(e)
            )
            raise

    @record_latency(
        "alpaca_http_latency_seconds",
        method="POST",
        extra_labels={"endpoint": "/v2/orders"},
    )
    async def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        time_in_force: str = "gtc",
        limit_price: float | None = None,
    ) -> OrderResult:
        """
        Place an order and return the submitted order object.
        Enhanced with comprehensive tracing and metrics.

        Args:
            symbol: Symbol to trade
            qty: Quantity to trade
            side: "buy" or "sell"
            order_type: "market" or "limit"
            time_in_force: "gtc", "ioc", "fok", etc.
            limit_price: Limit price (required for limit orders)

        Returns:
            OrderResult object with order details
        """
        start_time = time.time()
        structured_logger = get_structured_logger(__name__)

        with trace_span(
            "alpaca_submit_order",
            {
                "alpaca.operation": "submit_order",
                "alpaca.symbol": symbol,
                "alpaca.side": side,
                "alpaca.order_type": order_type,
                "alpaca.quantity": qty,
                "alpaca.limit_price": limit_price,
            },
        ) as span:
            try:
                if not validate_symbol(symbol):
                    raise ValueError(f"Invalid symbol format: {symbol}")

                # Rate limiting
                self._rate_limit()

                # Convert string enums
                side_enum = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
                tif_enum = getattr(TimeInForce, time_in_force.upper())

                # Create order request
                if order_type.lower() == "market":
                    order_request = MarketOrderRequest(
                        symbol=symbol, qty=qty, side=side_enum, time_in_force=tif_enum
                    )
                elif order_type.lower() == "limit":
                    if limit_price is None:
                        raise ValueError("Limit price required for limit orders")
                    order_request = LimitOrderRequest(
                        symbol=symbol,
                        qty=qty,
                        side=side_enum,
                        time_in_force=tif_enum,
                        limit_price=limit_price,
                    )
                else:
                    raise ValueError(f"Unsupported order type: {order_type}")

                # Submit order with API call timing (async wrapper for sync API)
                api_start_time = time.time()
                order = await asyncio.to_thread(self.trading_client.submit_order, order_request)
                api_duration = time.time() - api_start_time

                # Record Alpaca API metrics
                record_alpaca_request(
                    endpoint="/v2/orders",
                    method="POST",
                    status_code=201,  # Assume success if no exception
                    duration_seconds=api_duration,
                )

                # Create result object
                result = OrderResult(
                    order_id=str(order.id),
                    symbol=order.symbol,
                    side=order.side.value,
                    quantity=float(order.qty),
                    filled_quantity=float(order.filled_qty or 0),
                    price=(
                        float(order.filled_avg_price)
                        if order.filled_avg_price
                        else None
                    ),
                    status=order.status.value,
                    timestamp=order.created_at,
                )

                # Update span with success info
                span.set_attribute("alpaca.order_id", str(order.id))
                span.set_attribute("alpaca.status", order.status.value)
                span.set_attribute("alpaca.api_duration_seconds", api_duration)

                # Log structured order event (use standard info method)
                structured_logger.info(
                    "order_submitted",
                    order_id=str(order.id),
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    price=limit_price,
                    status=order.status.value,
                )

                # Log to audit trail
                audit_logger.log_trade_execution(
                    strategy="manual",
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    price=limit_price or 0,  # Will be updated when filled
                    order_id=str(order.id),
                )

                self.logger.info(
                    "Order submitted",
                    order_id=str(order.id),
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    order_type=order_type,
                )

                return result

            except Exception as e:
                # Calculate error timing
                error_duration = time.time() - start_time

                # Record error in Alpaca metrics
                record_alpaca_request(
                    endpoint="/v2/orders",
                    method="POST",
                    status_code=500,  # Assume server error for exceptions
                    duration_seconds=error_duration,
                )

                # Update span with error info
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))

                # Log structured error event (use standard info/error methods)
                structured_logger.error(
                    "order_submit_failed",
                    order_id="unknown",
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    price=limit_price,
                    error=str(e),
                )

                self.logger.error(
                    "Failed to submit order",
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    error=str(e),
                )
                raise

    @record_latency(
        "alpaca_http_latency_seconds",
        method="DELETE",
        extra_labels={"endpoint": "/v2/orders/{id}"},
    )
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order by ID.
        Enhanced with comprehensive tracing and metrics.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if successfully cancelled
        """
        start_time = time.time()
        structured_logger = get_structured_logger(__name__)

        with trace_span(
            "alpaca_cancel_order",
            {"alpaca.operation": "cancel_order", "alpaca.order_id": order_id},
        ) as span:
            try:
                self._rate_limit()

                # Cancel order with API call timing (async wrapper for sync API)
                api_start_time = time.time()
                await asyncio.to_thread(self.trading_client.cancel_order_by_id, order_id)
                api_duration = time.time() - api_start_time

                # Record Alpaca API metrics
                record_alpaca_request(
                    endpoint="/v2/orders/{id}",
                    method="DELETE",
                    status_code=200,  # Assume success if no exception
                    duration_seconds=api_duration,
                )

                # Update span with success info
                span.set_attribute("alpaca.api_duration_seconds", api_duration)
                span.set_attribute("alpaca.cancelled", True)

                # Log structured order event (use standard info)
                structured_logger.info("order_cancelled", order_id=order_id, status="cancelled")

                self.logger.info("Order cancelled", order_id=order_id)
                audit_logger.log_system_event(
                    "order_cancelled",
                    f"Order {order_id} cancelled",
                    data={"order_id": order_id},
                )

                return True

            except Exception as e:
                # Calculate error timing
                error_duration = time.time() - start_time

                # Record error in Alpaca metrics
                record_alpaca_request(
                    endpoint="/v2/orders/{id}",
                    method="DELETE",
                    status_code=500,  # Assume server error for exceptions
                    duration_seconds=error_duration,
                )

                # Update span with error info
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_attribute("alpaca.cancelled", False)

                # Log structured error event
                structured_logger.error("order_cancel_failed", order_id=order_id, error=str(e))

                self.logger.error(
                    "Failed to cancel order", order_id=order_id, error=str(e)
                )
                return False

    async def get_account_status(self) -> dict[str, Any]:
        """
        Retrieve current account balance, equity, and open positions.

        Returns:
            Dictionary with account information
        """
        try:
            self._rate_limit()

            # Get account info (async wrapper for sync API)
            account = await asyncio.to_thread(self.trading_client.get_account)

            # Get positions (async wrapper for sync API)
            positions = await asyncio.to_thread(self.trading_client.get_all_positions)

            # Format positions - handle Mock objects in test mode
            position_data = {}
            try:
                # Check if positions is iterable (not a Mock object)
                positions_iter = iter(positions) if not self.test_mode else []
                for pos in positions_iter:
                    try:
                        position_data[pos.symbol] = {
                            "quantity": float(pos.qty),
                            "market_value": float(pos.market_value),
                            "avg_entry_price": float(pos.avg_entry_price),
                            "unrealized_pl": float(pos.unrealized_pl),
                            "unrealized_plpc": float(pos.unrealized_plpc),
                        }
                    except (AttributeError, TypeError, ValueError):
                        # Skip invalid position objects in test mode
                        continue
            except (TypeError, AttributeError):
                # Handle non-iterable positions (e.g., Mock objects) in test mode
                if self.test_mode:
                    position_data = {}  # Empty positions for test mode
                else:
                    raise

            # Helper function to safely get account attributes (dict or object)
            def safe_get_account_attr(account, attr, default=0):
                try:
                    if isinstance(account, dict):
                        return account.get(attr, default)
                    else:
                        return getattr(account, attr, default)
                except (AttributeError, KeyError, TypeError):
                    return default

            result = {
                "account_number": safe_get_account_attr(account, "account_number", "unknown"),
                "equity": float(safe_get_account_attr(account, "equity", 0) or 0),
                "cash": float(safe_get_account_attr(account, "cash", 0) or 0),
                "buying_power": float(safe_get_account_attr(account, "buying_power", 0) or 0),
                "portfolio_value": float(safe_get_account_attr(account, "portfolio_value", 0) or 0),
                "day_trade_count": int(safe_get_account_attr(account, "daytrade_count", 0) or 0),
                "positions": position_data,
                "timestamp": datetime.now(UTC),
            }

            self.logger.info(
                "Retrieved account status",
                equity=result["equity"],
                cash=result["cash"],
                positions_count=len(position_data),
            )

            return result

        except Exception as e:
            self.logger.error("Failed to get account status", error=str(e))
            raise

    async def get_recent_orders(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Get recent orders.

        Args:
            limit: Maximum number of orders to retrieve

        Returns:
            List of order dictionaries
        """
        try:
            self._rate_limit()

            # Get orders (async wrapper for sync API)
            # Some test doubles expect simple kwargs; keep it minimal/compatible
            try:
                request = GetOrdersRequest(status=None, limit=limit)
            except TypeError:
                # Fallback to only limit if signature differs in mocks
                request = GetOrdersRequest(limit=limit)
            orders = await asyncio.to_thread(self.trading_client.get_orders, request)

            # Helper function for safe enum value extraction
            def safe_get_enum_value(obj, default="Unknown"):
                """Safely get .value from enum or return obj if it's already a string."""
                if hasattr(obj, 'value'):
                    return obj.value
                return str(obj) if obj is not None else default

            # Format orders
            order_list = []
            for order in orders:
                order_dict = {
                    "id": str(order.id),
                    "symbol": order.symbol,
                    "side": safe_get_enum_value(order.side),
                    "quantity": float(order.qty),
                    "filled_quantity": float(order.filled_qty or 0),
                    "order_type": safe_get_enum_value(order.order_type),
                    "status": safe_get_enum_value(order.status),
                    "submitted_at": order.submitted_at,
                    "filled_at": order.filled_at,
                    "limit_price": (
                        float(order.limit_price) if order.limit_price else None
                    ),
                    "filled_avg_price": (
                        float(order.filled_avg_price)
                        if order.filled_avg_price
                        else None
                    ),
                }
                order_list.append(order_dict)

            self.logger.info("Retrieved recent orders", count=len(order_list))
            return order_list

        except Exception as e:
            self.logger.error("Failed to get recent orders", error=str(e))
            raise

    def get_current_price(self, symbol: str) -> float | None:
        """
        Get current price for a symbol.

        Args:
            symbol: Symbol to get price for

        Returns:
            Current price or None if not available
        """
        try:
            self._rate_limit()

            if "/" in symbol:
                # Crypto - use latest bar
                bars = self.crypto_data_client.get_crypto_latest_bar(
                    symbol_or_symbols=symbol
                )
                if symbol in bars:
                    return float(bars[symbol].close)
            else:
                # Stock - use latest quote; guard against missing fields
                try:
                    request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
                    quotes = self.stock_data_client.get_stock_latest_quote(request)
                    if symbol in quotes:
                        quote = quotes[symbol]
                        bid = float(getattr(quote, "bid_price", 0) or 0)
                        ask = float(getattr(quote, "ask_price", 0) or 0)
                        if bid > 0 and ask > 0:
                            return (bid + ask) / 2
                except Exception:
                    pass
                # Fallback: try latest bar close
                try:
                    bars = self.stock_data_client.get_stock_latest_bar(symbol_or_symbols=symbol)
                    if symbol in bars:
                        return float(bars[symbol].close)
                except Exception:
                    pass

            return None

        except Exception as e:
            self.logger.error(
                "Failed to get current price", symbol=symbol, error=str(e)
            )
            return None

    def _rate_limit(self):
        """
        Implement rate limiting to avoid API limits.

        NOTE: This is a synchronous rate limiter for sync code paths.
        For async code, use _async_rate_limit() instead.
        """
        import time

        current_time = time.time()
        elapsed = current_time - self.last_request_time

        if elapsed < self.min_request_interval:
            sleep_time = self.min_request_interval - elapsed
            # Only sleep in sync context - async callers should use _async_rate_limit
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    async def _async_rate_limit(self):
        """
        Async-friendly rate limiting using asyncio.sleep.

        Use this in async code paths instead of _rate_limit() to avoid
        blocking the event loop.
        """
        current_time = time.time()
        elapsed = current_time - self.last_request_time

        if elapsed < self.min_request_interval:
            sleep_time = self.min_request_interval - elapsed
            await asyncio.sleep(sleep_time)

        self.last_request_time = time.time()

    def add_data_callback(self, callback: Callable):
        """Add a callback for real-time data updates."""
        self.data_callbacks.append(callback)

    def disconnect(self):
        """Disconnect from data streams."""
        if self.stock_stream:
            self.stock_stream.close()
        if self.crypto_stream:
            self.crypto_stream.close()

        self.connected = False
        self.logger.info("Disconnected from data streams")

    def __del__(self):
        """Cleanup on destruction."""
        if self.connected:
            self.disconnect()

    def get_bars(self, *args, **kwargs) -> pd.DataFrame:
        """Compatibility alias for get_historical_data - for Mock objects in tests."""
        # Extract common parameters from args/kwargs
        symbol = args[0] if len(args) > 0 else kwargs.get('symbol')
        timeframe = kwargs.get('timeframe', '1Day')
        start = kwargs.get('start')
        end = kwargs.get('end')
        limit = kwargs.get('limit', 1000)

        if symbol:
            return self.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                limit=limit
            )

        # Return empty DataFrame if no symbol provided
        return pd.DataFrame()
