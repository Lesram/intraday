"""
Alpaca API Client Module for Market Data & Trading.
Handles all interactions with Alpaca's trading and market data APIs.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typi, timezoneng import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

try:
    from alpaca.common.exceptions import APIError
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
    from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
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


from ..utils.helpers import generate_trade_id, validate_symbol
from ..utils.logger import audit_logger, get_structured_logger


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
    vwap: Optional[float] = None


@dataclass
class OrderResult:
    """Order execution result."""

    order_id: str
    symbol: str
    side: str
    quantity: float
    filled_quantity: float
    price: Optional[float]
    status: str
    timestamp: datetime


class AlpacaClient:
    """
    Alpaca API client for market data and trading operations.
    Supports both paper and live trading modes.
    """

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        """
        Initialize Alpaca trading and data client.

        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            paper: Whether to use paper trading (True) or live trading (False)
        """
        if not ALPACA_AVAILABLE:
            raise ImportError(
                "alpaca-py library is not installed. Run: pip install alpaca-py"
            )

        self.logger = get_structured_logger("alpaca_client")
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper

        # Initialize clients
        self._init_clients()

        # Data streams
        self.stock_stream: Optional[StockDataStream] = None
        self.crypto_stream: Optional[CryptoDataStream] = None

        # Callbacks for real-time data
        self.data_callbacks: List[Callable] = []

        # Connection status
        self.connected = False

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

            # Test connection
            account = self.trading_client.get_account()
            self.logger.info(
                "Connected to Alpaca",
                account_number=account.account_number,
                buying_power=float(account.buying_power),
            )

        except Exception as e:
            self.logger.error("Failed to initialize Alpaca clients", error=str(e))
            raise

    async def connect_data_stream(
        self,
        symbols: List[str],
        on_bar: Optional[Callable] = None,
        on_quote: Optional[Callable] = None,
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
        start: Optional[str] = None,
        end: Optional[str] = None,
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

    def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        time_in_force: str = "gtc",
        limit_price: Optional[float] = None,
    ) -> OrderResult:
        """
        Place an order and return the submitted order object.

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

            # Submit order
            order = self.trading_client.submit_order(order_request)

            # Create result object
            result = OrderResult(
                order_id=str(order.id),
                symbol=order.symbol,
                side=order.side.value,
                quantity=float(order.qty),
                filled_quantity=float(order.filled_qty or 0),
                price=float(order.filled_avg_price) if order.filled_avg_price else None,
                status=order.status.value,
                timestamp=order.created_at,
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
            self.logger.error(
                "Failed to submit order",
                symbol=symbol,
                side=side,
                quantity=qty,
                error=str(e),
            )
            raise

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order by ID.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if successfully cancelled
        """
        try:
            self._rate_limit()

            self.trading_client.cancel_order_by_id(order_id)

            self.logger.info("Order cancelled", order_id=order_id)
            audit_logger.log_system_event(
                "order_cancelled",
                f"Order {order_id} cancelled",
                data={"order_id": order_id},
            )

            return True

        except Exception as e:
            self.logger.error("Failed to cancel order", order_id=order_id, error=str(e))
            return False

    def get_account_status(self) -> Dict[str, Any]:
        """
        Retrieve current account balance, equity, and open positions.

        Returns:
            Dictionary with account information
        """
        try:
            self._rate_limit()

            # Get account info
            account = self.trading_client.get_account()

            # Get positions
            positions = self.trading_client.get_all_positions()

            # Format positions
            position_data = {}
            for pos in positions:
                position_data[pos.symbol] = {
                    "quantity": float(pos.qty),
                    "market_value": float(pos.market_value),
                    "avg_entry_price": float(pos.avg_entry_price),
                    "unrealized_pl": float(pos.unrealized_pl),
                    "unrealized_plpc": float(pos.unrealized_plpc),
                }

            result = {
                "account_number": account.account_number,
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "portfolio_value": float(account.portfolio_value),
                "day_trade_count": int(account.daytrade_count),
                "positions": position_data,
                "timestamp": datetime.now(timezone.utc),
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

    def get_recent_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent orders.

        Args:
            limit: Maximum number of orders to retrieve

        Returns:
            List of order dictionaries
        """
        try:
            self._rate_limit()

            # Get orders
            request = GetOrdersRequest(status=None, limit=limit)  # All statuses
            orders = self.trading_client.get_orders(request)

            # Format orders
            order_list = []
            for order in orders:
                order_dict = {
                    "id": str(order.id),
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "quantity": float(order.qty),
                    "filled_quantity": float(order.filled_qty or 0),
                    "order_type": order.order_type.value,
                    "status": order.status.value,
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

    def get_current_price(self, symbol: str) -> Optional[float]:
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
                # Stock - use latest quote
                request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
                quotes = self.stock_data_client.get_stock_latest_quote(request)
                if symbol in quotes:
                    quote = quotes[symbol]
                    return (float(quote.bid_price) + float(quote.ask_price)) / 2

            return None

        except Exception as e:
            self.logger.error(
                "Failed to get current price", symbol=symbol, error=str(e)
            )
            return None

    def _rate_limit(self):
        """Implement rate limiting to avoid API limits."""
        import time

        current_time = time.time()
        elapsed = current_time - self.last_request_time

        if elapsed < self.min_request_interval:
            sleep_time = self.min_request_interval - elapsed
            time.sleep(sleep_time)

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
