"""
Alpaca Market Data WebSocket Stream Client

This module provides real-time market data streaming from Alpaca's Data API v2.
Separate from the order update stream, this handles quotes, trades, and bars.

Features:
- Real-time quote streaming
- Real-time trade streaming
- Real-time bar streaming (1Min, 5Min, etc.)
- Automatic reconnection with exponential backoff
- Message deduplication
- Error classification and handling
- Integration with MarketDataService

Alpaca Market Data API v2:
- Base URL: wss://stream.data.alpaca.markets/v2/iex (IEX feed)
- Alternative: wss://stream.data.alpaca.markets/v2/sip (SIP feed, more comprehensive)
- Authentication: API key/secret in auth message
- Message types: quotes (q), trades (t), bars (b)

Created: October 16, 2025 - Phase 7 Day 1
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
import json
import logging
import random
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

logger = logging.getLogger(__name__)


class AlpacaMarketDataStream:
    """
    WebSocket client for Alpaca Market Data API v2.

    Handles real-time streaming of:
    - Quotes (bid/ask prices)
    - Trades (executed trades)
    - Bars (OHLCV candlesticks)

    Architecture:
    - Single WebSocket connection to Alpaca
    - Subscribes to symbols dynamically
    - Forwards data to MarketDataService for broadcasting
    """

    # Configuration
    MAX_RECONNECT_ATTEMPTS = 10  # Max reconnection attempts before giving up
    INITIAL_BACKOFF = 1.0  # Initial reconnect delay (seconds)
    MAX_BACKOFF = 300.0  # Max reconnect delay (5 minutes)
    BACKOFF_MULTIPLIER = 1.5  # Exponential backoff multiplier
    HEARTBEAT_INTERVAL = 30  # Seconds between heartbeats

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        paper: bool = True,
        feed: str = "sip"  # "sip" (full consolidated) or "iex" (single exchange)
    ):
        """
        Initialize Alpaca market data stream.

        Args:
            api_key: Alpaca API key
            api_secret: Alpaca API secret
            paper: Use paper trading endpoint (True) or live (False)
            feed: Data feed ("iex" = free, "sip" = paid, more comprehensive)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper = paper
        self.feed = feed

        # WebSocket URL
        # Note: Market data URL is same for paper and live (authentication determines access)
        self.base_url = f"wss://stream.data.alpaca.markets/v2/{feed}"

        # Connection state
        self.websocket: websockets.WebSocketClientProtocol | None = None
        self.is_connected = False
        self.is_authenticated = False
        self.should_reconnect = True

        # Reconnection state
        self.reconnect_attempts = 0
        self.current_backoff = self.INITIAL_BACKOFF

        # Subscriptions
        self.quote_subscriptions: set[str] = set()  # Symbols subscribed to quotes
        self.trade_subscriptions: set[str] = set()  # Symbols subscribed to trades
        self.bar_subscriptions: dict[str, set[str]] = {}  # {timeframe: {symbols}}

        # Callbacks
        self.on_quote: Callable[[str, dict], Any] | None = None
        self.on_trade: Callable[[str, dict], Any] | None = None
        self.on_bar: Callable[[str, dict], Any] | None = None
        self.on_error: Callable[[str], Any] | None = None

        # Statistics
        self.connection_count = 0
        self.total_messages_received = 0
        self.last_heartbeat: datetime | None = None

        # Background tasks
        self.background_tasks: list[asyncio.Task] = []

        logger.info(
            "AlpacaMarketDataStream initialized: base_url=%s paper=%s feed=%s",
            self.base_url, paper, feed,
        )

    async def connect(self) -> bool:
        """
        Connect to Alpaca market data stream.

        Returns:
            bool: True if connected successfully
        """
        if self.is_connected:
            logger.warning("Already connected")
            return True

        try:
            logger.info(f"Connecting to Alpaca market data stream: {self.base_url}")

            # Connect to WebSocket
            self.websocket = await websockets.connect(
                self.base_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )

            self.is_connected = True
            self.connection_count += 1
            self.reconnect_attempts = 0
            self.current_backoff = self.INITIAL_BACKOFF

            logger.info(f"Connected to Alpaca (connection #{self.connection_count})")

            # Authenticate
            if await self._authenticate():
                # Resubscribe to symbols (if reconnecting)
                await self._resubscribe_all()

                # Start background tasks
                self._start_background_tasks()

                return True
            else:
                await self.disconnect()
                return False

        except Exception as e:
            logger.error(f"Failed to connect to Alpaca: {e}", exc_info=True)
            self.is_connected = False
            return False

    async def disconnect(self):
        """Disconnect from Alpaca market data stream"""
        logger.info("Disconnecting from Alpaca market data stream")

        self.should_reconnect = False
        self.is_connected = False
        self.is_authenticated = False

        # Cancel background tasks
        for task in self.background_tasks:
            task.cancel()

        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)

        self.background_tasks.clear()

        # Close WebSocket
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")

            self.websocket = None

        logger.info("Disconnected from Alpaca")

    async def _authenticate(self) -> bool:
        """
        Authenticate with Alpaca.

        Returns:
            bool: True if authenticated successfully
        """
        try:
            auth_message = {
                "action": "auth",
                "key": self.api_key,
                "secret": self.api_secret
            }

            # Consume the initial welcome message before sending auth.
            # Alpaca sends [{"T":"success","msg":"connected"}] on connect.
            welcome = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
            welcome_data = json.loads(welcome)
            if isinstance(welcome_data, list):
                welcome_data = welcome_data[0] if welcome_data else {}
            if welcome_data.get("msg") == "connected":
                logger.debug("Received welcome message from Alpaca")
            else:
                logger.warning("Unexpected first message: %s", welcome_data)

            await self.websocket.send(json.dumps(auth_message))
            logger.debug("Sent authentication message")

            # Wait for authentication response
            response = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=10.0
            )

            auth_data = json.loads(response)

            # Check authentication status
            # Alpaca Data API v2 format: [{"T": "success", "msg": "authenticated"}]
            if isinstance(auth_data, list):
                auth_data = auth_data[0] if auth_data else {}

            if auth_data.get("T") == "success" and auth_data.get("msg") == "authenticated":
                self.is_authenticated = True
                logger.info("Authenticated with Alpaca successfully")
                return True
            else:
                logger.error(f"Authentication failed: {auth_data}")
                if self.on_error:
                    await self.on_error(f"Authentication failed: {auth_data.get('msg', 'Unknown error')}")
                return False

        except TimeoutError:
            logger.error("Authentication timeout")
            return False
        except Exception as e:
            logger.error(f"Authentication error: {e}", exc_info=True)
            return False

    async def subscribe_quotes(self, symbols: list[str]) -> bool:
        """
        Subscribe to real-time quote updates for symbols.

        Args:
            symbols: List of stock symbols (e.g., ["AAPL", "TSLA"])

        Returns:
            bool: True if subscribed successfully
        """
        if not self.is_authenticated:
            logger.error("Not authenticated, cannot subscribe")
            return False

        # Normalize symbols (uppercase)
        symbols = [s.upper() for s in symbols]

        # Filter out already subscribed symbols
        new_symbols = [s for s in symbols if s not in self.quote_subscriptions]

        if not new_symbols:
            logger.debug(f"Already subscribed to quotes for: {symbols}")
            return True

        try:
            subscribe_message = {
                "action": "subscribe",
                "quotes": new_symbols
            }

            await self.websocket.send(json.dumps(subscribe_message))

            # Add to subscriptions
            self.quote_subscriptions.update(new_symbols)

            logger.info(f"Subscribed to quotes for: {new_symbols}")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe to quotes: {e}", exc_info=True)
            return False

    async def subscribe_trades(self, symbols: list[str]) -> bool:
        """
        Subscribe to real-time trade updates for symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            bool: True if subscribed successfully
        """
        if not self.is_authenticated:
            logger.error("Not authenticated, cannot subscribe")
            return False

        symbols = [s.upper() for s in symbols]
        new_symbols = [s for s in symbols if s not in self.trade_subscriptions]

        if not new_symbols:
            return True

        try:
            subscribe_message = {
                "action": "subscribe",
                "trades": new_symbols
            }

            await self.websocket.send(json.dumps(subscribe_message))

            self.trade_subscriptions.update(new_symbols)

            logger.info(f"Subscribed to trades for: {new_symbols}")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe to trades: {e}", exc_info=True)
            return False

    async def subscribe_bars(self, symbols: list[str], timeframe: str = "1Min") -> bool:
        """
        Subscribe to real-time bar (candlestick) updates for symbols.

        Args:
            symbols: List of stock symbols
            timeframe: Bar timeframe (e.g., "1Min", "5Min", "15Min", "1Hour", "1Day")

        Returns:
            bool: True if subscribed successfully
        """
        if not self.is_authenticated:
            logger.error("Not authenticated, cannot subscribe")
            return False

        symbols = [s.upper() for s in symbols]

        # Initialize timeframe set if needed
        if timeframe not in self.bar_subscriptions:
            self.bar_subscriptions[timeframe] = set()

        # Filter out already subscribed symbols
        new_symbols = [s for s in symbols if s not in self.bar_subscriptions[timeframe]]

        if not new_symbols:
            return True

        try:
            subscribe_message = {
                "action": "subscribe",
                "bars": new_symbols
            }

            await self.websocket.send(json.dumps(subscribe_message))

            self.bar_subscriptions[timeframe].update(new_symbols)

            logger.info(f"Subscribed to {timeframe} bars for: {new_symbols}")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe to bars: {e}", exc_info=True)
            return False

    async def unsubscribe(self, symbols: list[str]) -> bool:
        """
        Unsubscribe from all data types for symbols.

        Args:
            symbols: List of stock symbols to unsubscribe from

        Returns:
            bool: True if unsubscribed successfully
        """
        if not self.is_authenticated:
            return False

        symbols = [s.upper() for s in symbols]

        try:
            unsubscribe_message = {
                "action": "unsubscribe",
                "quotes": symbols,
                "trades": symbols,
                "bars": symbols
            }

            await self.websocket.send(json.dumps(unsubscribe_message))

            # Remove from subscriptions
            for symbol in symbols:
                self.quote_subscriptions.discard(symbol)
                self.trade_subscriptions.discard(symbol)
                for timeframe_subs in self.bar_subscriptions.values():
                    timeframe_subs.discard(symbol)

            logger.info(f"Unsubscribed from: {symbols}")
            return True

        except Exception as e:
            logger.error(f"Failed to unsubscribe: {e}", exc_info=True)
            return False

    async def _resubscribe_all(self):
        """Resubscribe to all symbols after reconnection"""
        if self.quote_subscriptions:
            await self.subscribe_quotes(list(self.quote_subscriptions))

        if self.trade_subscriptions:
            await self.subscribe_trades(list(self.trade_subscriptions))

        for timeframe, symbols in self.bar_subscriptions.items():
            if symbols:
                await self.subscribe_bars(list(symbols), timeframe)

    async def listen(self):
        """
        Main listening loop for processing messages.
        This should be run as a background task.
        """
        if not self.is_connected or not self.is_authenticated:
            logger.error("Cannot listen - not connected or authenticated")
            return

        logger.info("Starting to listen for market data")

        try:
            async for message in self.websocket:
                try:
                    await self._handle_message(message)

                except json.JSONDecodeError as e:
                    logger.warning("Invalid JSON received: %s error=%s", message[:200], e)
                    continue

                except Exception as e:
                    logger.error(
                        f"Error processing message: {e}",
                        message=message[:200],
                        exc_info=True
                    )
                    continue

        except ConnectionClosed as e:
            logger.warning(f"WebSocket connection closed: {e}")
            self.is_connected = False
            self.is_authenticated = False

            if self.should_reconnect:
                await self._reconnect()

        except WebSocketException as e:
            logger.error(f"WebSocket error: {e}", exc_info=True)
            self.is_connected = False
            self.is_authenticated = False

            if self.should_reconnect:
                await self._reconnect()

        except Exception as e:
            logger.error(f"Unexpected error in listen loop: {e}", exc_info=True)
            self.is_connected = False
            self.is_authenticated = False

    async def _handle_message(self, raw_message: str):
        """
        Handle incoming message from Alpaca.

        Alpaca Data API v2 message format:
        [
            {
                "T": "q",  # Message type: q=quote, t=trade, b=bar
                "S": "AAPL",  # Symbol
                "bx": "K",  # Bid exchange
                "bp": 150.25,  # Bid price
                "bs": 100,  # Bid size
                "ax": "K",  # Ask exchange
                "ap": 150.30,  # Ask price
                "as": 100,  # Ask size
                "t": "2025-10-16T14:30:00.123456Z"  # Timestamp
            }
        ]
        """
        messages = json.loads(raw_message)

        # Messages are always in an array
        if not isinstance(messages, list):
            messages = [messages]

        for message in messages:
            self.total_messages_received += 1

            msg_type = message.get("T")

            if msg_type == "success":
                # Subscription confirmation
                logger.debug(f"Subscription confirmed: {message.get('msg')}")
                continue

            elif msg_type == "subscription":
                # Subscription status update
                logger.debug(f"Subscription update: {message}")
                continue

            elif msg_type == "error":
                # Error message
                error_msg = message.get("msg", "Unknown error")
                logger.error(f"Alpaca error: {error_msg}")
                if self.on_error:
                    await self.on_error(error_msg)
                continue

            elif msg_type == "q":
                # Quote message
                await self._handle_quote(message)

            elif msg_type == "t":
                # Trade message
                await self._handle_trade(message)

            elif msg_type == "b":
                # Bar message
                await self._handle_bar(message)

            else:
                logger.debug(f"Unknown message type: {msg_type}")

    async def _handle_quote(self, message: dict[str, Any]):
        """Handle quote message"""
        try:
            symbol = message.get("S")

            # Parse quote data
            quote_data = {
                "bid": message.get("bp"),
                "ask": message.get("ap"),
                "bid_size": message.get("bs"),
                "ask_size": message.get("as"),
                "bid_exchange": message.get("bx"),
                "ask_exchange": message.get("ax"),
                "timestamp": message.get("t"),
                "conditions": message.get("c", [])
            }

            # Calculate mid-price and spread
            if quote_data["bid"] and quote_data["ask"]:
                quote_data["mid"] = (quote_data["bid"] + quote_data["ask"]) / 2
                quote_data["spread"] = quote_data["ask"] - quote_data["bid"]

            # Call callback
            if self.on_quote:
                await self.on_quote(symbol, quote_data)

        except Exception as e:
            logger.error(f"Error handling quote: {e}", exc_info=True)

    async def _handle_trade(self, message: dict[str, Any]):
        """Handle trade message"""
        try:
            symbol = message.get("S")

            trade_data = {
                "price": message.get("p"),
                "size": message.get("s"),
                "exchange": message.get("x"),
                "timestamp": message.get("t"),
                "conditions": message.get("c", []),
                "tape": message.get("z")
            }

            if self.on_trade:
                await self.on_trade(symbol, trade_data)

        except Exception as e:
            logger.error(f"Error handling trade: {e}", exc_info=True)

    async def _handle_bar(self, message: dict[str, Any]):
        """Handle bar (OHLCV) message"""
        try:
            symbol = message.get("S")

            bar_data = {
                "open": message.get("o"),
                "high": message.get("h"),
                "low": message.get("l"),
                "close": message.get("c"),
                "volume": message.get("v"),
                "timestamp": message.get("t"),
                "trade_count": message.get("n"),
                "vwap": message.get("vw")
            }

            if self.on_bar:
                await self.on_bar(symbol, bar_data)

        except Exception as e:
            logger.error(f"Error handling bar: {e}", exc_info=True)

    async def _reconnect(self):
        """Reconnect with exponential backoff"""
        if self.reconnect_attempts >= self.MAX_RECONNECT_ATTEMPTS:
            logger.error(f"Max reconnect attempts ({self.MAX_RECONNECT_ATTEMPTS}) reached, giving up")
            if self.on_error:
                await self.on_error("Max reconnect attempts reached")
            return

        self.reconnect_attempts += 1

        # Calculate backoff with jitter
        jitter = random.uniform(-0.1, 0.1)
        delay = self.current_backoff * (1 + jitter)

        logger.info(
            f"Reconnecting in {delay:.1f}s (attempt {self.reconnect_attempts}/{self.MAX_RECONNECT_ATTEMPTS})"
        )

        await asyncio.sleep(delay)

        # Increase backoff for next attempt
        self.current_backoff = min(
            self.current_backoff * self.BACKOFF_MULTIPLIER,
            self.MAX_BACKOFF
        )

        # Attempt reconnection
        try:
            success = await self.connect()
        except Exception as e:
            logger.error(f"Reconnection attempt raised exception: {e}")
            success = False

        if success:
            logger.info("Reconnected successfully")
            # Start listening again
            asyncio.create_task(self.listen())
        elif self.reconnect_attempts < self.MAX_RECONNECT_ATTEMPTS:
            await self._reconnect()
        else:
            logger.error("Max reconnect attempts exhausted")

    def _start_background_tasks(self):
        """Start background tasks for heartbeat monitoring"""
        # Listen task
        listen_task = asyncio.create_task(self.listen())
        self.background_tasks.append(listen_task)

        # Heartbeat task
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self.background_tasks.append(heartbeat_task)

    async def _heartbeat_loop(self):
        """Send periodic heartbeat to track connection health"""
        while self.is_connected:
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            self.last_heartbeat = datetime.now(UTC)
            logger.debug("Heartbeat connection_count=%d", self.connection_count)

    def get_stats(self) -> dict[str, Any]:
        """Get stream statistics"""
        return {
            "connected": self.is_connected,
            "authenticated": self.is_authenticated,
            "connection_count": self.connection_count,
            "total_messages": self.total_messages_received,
            "quote_subscriptions": len(self.quote_subscriptions),
            "trade_subscriptions": len(self.trade_subscriptions),
            "bar_subscriptions": sum(len(s) for s in self.bar_subscriptions.values()),
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None
        }
