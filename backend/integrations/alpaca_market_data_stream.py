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
    SUBSCRIPTION_ACK_TIMEOUT_S = 2.0
    SUBSCRIPTION_RETRY_INTERVAL_S = 5.0

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

        # Desired state survives reconnect; public subscription sets contain only
        # server-confirmed state from this connection generation.
        self._desired = {channel: set() for channel in ("quotes", "trades", "bars")}
        self._desired_bar_timeframes: set[str] = set()
        self.connection_generation = 0
        self._channel_versions = {channel: 0 for channel in self._desired}
        self._subscription_error = 0
        # Audit 2026-09-29 (MDP-04a/MDP-12): keep the provider's error code so
        # a symbol-cap refusal (405) is handled as a refusal, not retried and
        # replayed wholesale on every reconnect.
        self.last_error_code: int | None = None
        self.symbol_limit_exceeded = False
        self.refused_symbols = 0
        self._subscription_changed = asyncio.Event()
        self._subscription_lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()
        self._retry_after: dict[tuple, float] = {}
        self._listener: asyncio.Task | None = None

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
        """Open one authenticated generation and start its reader before ACK waits."""
        async with self._connect_lock:
            if self.is_connected and self.is_authenticated:
                return True
            if not self.should_reconnect:
                return False
            generation = self.connection_generation
            try:
                socket = await websockets.connect(
                    self.base_url, ping_interval=20, ping_timeout=10, close_timeout=10,
                )
                if not self.should_reconnect or generation != self.connection_generation:
                    await socket.close()
                    return False
                self.websocket = socket
                self.connection_generation += 1
                generation = self.connection_generation
                self._clear_confirmations()
                self.is_connected = True
                if not await self._authenticate():
                    await self._cleanup_connection()
                    return False
                if not self.should_reconnect or generation != self.connection_generation:
                    return False
                self.connection_count += 1
                self._start_background_tasks()
                await self._resubscribe_all()
                if (generation != self.connection_generation or not self.is_authenticated
                        or not self.should_reconnect):
                    return False
                self.reconnect_attempts = 0
                self.current_backoff = self.INITIAL_BACKOFF
                return True
            except asyncio.CancelledError:
                await self._cleanup_connection()
                raise
            except Exception:
                logger.exception("Failed to connect to Alpaca market data")
                await self._cleanup_connection()
                return False

    def _clear_confirmations(self) -> None:
        self.quote_subscriptions.clear()
        self.trade_subscriptions.clear()
        for names in self.bar_subscriptions.values():
            names.clear()
        self._channel_versions = {channel: 0 for channel in self._desired}
        self._retry_after.clear()
        self._subscription_changed.set()

    async def _cleanup_connection(self) -> None:
        """Clean up connection resources without changing reconnect intent.

        Safe to call from within a listen() task — skips cancelling the
        current task to avoid self-cancellation.
        """
        self.is_connected = False
        self.is_authenticated = False
        self.connection_generation += 1
        self._clear_confirmations()

        # Cancel background tasks (skip the current task if called from within)
        current = asyncio.current_task()
        to_cancel = [t for t in self.background_tasks if t is not current and not t.done()]
        for task in to_cancel:
            task.cancel()
        if to_cancel:
            await asyncio.gather(*to_cancel, return_exceptions=True)

        # Remove completed/cancelled tasks
        self.background_tasks = [t for t in self.background_tasks if not t.done() and t is current]

        # Close WebSocket
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
            self.websocket = None

    async def disconnect(self):
        """Disconnect from Alpaca market data stream permanently."""
        logger.info("Disconnecting from Alpaca market data stream")
        self.should_reconnect = False
        await self._cleanup_connection()
        logger.info("Disconnected from Alpaca")

    async def _authenticate(self) -> bool:
        """
        Authenticate with Alpaca.

        Returns:
            bool: True if authenticated successfully
        """
        socket, generation = self.websocket, self.connection_generation
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
                if (socket is not self.websocket or generation != self.connection_generation
                        or not self.should_reconnect):
                    return False
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

    @property
    def desired_symbols(self) -> set[str]:
        """Union of symbols this client wants across channels (may be unconfirmed)."""
        return set().union(*self._desired.values())

    @property
    def reconnecting(self) -> bool:
        """True while this client's own bounded reconnect loop still owns recovery."""
        listener = self._listener
        return bool(
            self.should_reconnect
            and not self.is_authenticated
            and listener is not None
            and not listener.done()
            and self.reconnect_attempts < self.MAX_RECONNECT_ATTEMPTS
        )

    def _confirmed(self, channel: str) -> set[str]:
        if channel == "quotes":
            return set(self.quote_subscriptions)
        if channel == "trades":
            return set(self.trade_subscriptions)
        return set().union(*self.bar_subscriptions.values()) if self.bar_subscriptions else set()

    async def _change_subscriptions(self, action: str, channels: dict[str, set[str]]) -> bool:
        """A send is only a request. Await supplied channel snapshots in this session."""
        async with self._subscription_lock:
            if not self.is_authenticated or self.websocket is None:
                return False
            generation = self.connection_generation
            socket = self.websocket
            if action == "subscribe":
                for channel, names in channels.items():
                    self._desired[channel].update(names)
                channels = {channel: names - self._confirmed(channel)
                            for channel, names in channels.items()}
                channels = {channel: names for channel, names in channels.items() if names}
                if not channels:
                    return True
            key = (action, tuple(sorted(channels)))
            loop = asyncio.get_running_loop()
            if loop.time() < self._retry_after.get(key, 0):
                return False
            versions = dict(self._channel_versions)
            error = self._subscription_error
            self._retry_after[key] = loop.time() + self.SUBSCRIPTION_RETRY_INTERVAL_S
            self._subscription_changed.clear()
            deadline = loop.time() + self.SUBSCRIPTION_ACK_TIMEOUT_S
            try:
                await asyncio.wait_for(socket.send(json.dumps({"action": action, **{
                    channel: sorted(names) for channel, names in channels.items()
                }})), timeout=self.SUBSCRIPTION_ACK_TIMEOUT_S)
                while (generation == self.connection_generation and self.is_authenticated
                       and self.should_reconnect and error == self._subscription_error):
                    supplied = all(self._channel_versions[c] > versions[c] for c in channels)
                    matched = all(
                        names <= self._confirmed(channel) if action == "subscribe"
                        else not names.intersection(self._confirmed(channel))
                        for channel, names in channels.items()
                    )
                    if supplied:
                        if matched:
                            if action == "unsubscribe":
                                for channel, names in channels.items():
                                    self._desired[channel].difference_update(names)
                            self._retry_after.pop(key, None)
                            return True
                        # A complete but partial/rejected snapshot is not success.
                        return False
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        break
                    await asyncio.wait_for(self._subscription_changed.wait(), timeout=remaining)
                    self._subscription_changed.clear()
                if (action == "subscribe" and error != self._subscription_error
                        and self.last_error_code == 405
                        and generation == self.connection_generation):
                    # Provider symbol cap: refused names are dropped from the
                    # desired set so they are neither retried every call nor
                    # replayed (and refused as a whole) after a reconnect.
                    refused = 0
                    for channel, names in channels.items():
                        rejected = names - self._confirmed(channel)
                        self._desired[channel].difference_update(rejected)
                        refused += len(rejected)
                    self.symbol_limit_exceeded = True
                    self.refused_symbols += refused
                    logger.warning(
                        "Market-data subscription refused by provider symbol limit: "
                        "%d symbol-channel request(s) dropped from desired set", refused,
                    )
            except (TimeoutError, WebSocketException, OSError):
                logger.warning("Market-data subscription %s incomplete", action)
            except Exception:
                logger.exception("Market-data subscription request failed")
            return False

    async def subscribe_quotes(self, symbols: list[str]) -> bool:
        return await self._change_subscriptions("subscribe", {"quotes": {s.upper() for s in symbols}})

    async def subscribe_trades(self, symbols: list[str]) -> bool:
        return await self._change_subscriptions("subscribe", {"trades": {s.upper() for s in symbols}})

    async def subscribe_bars(self, symbols: list[str], timeframe: str = "1Min") -> bool:
        self._desired_bar_timeframes.add(timeframe)
        self.bar_subscriptions.setdefault(timeframe, self._confirmed("bars"))
        return await self._change_subscriptions("subscribe", {"bars": {s.upper() for s in symbols}})

    async def unsubscribe(self, symbols: list[str]) -> bool:
        names = {s.upper() for s in symbols}
        return await self._change_subscriptions("unsubscribe", {c: names for c in self._desired})

    async def _resubscribe_all(self):
        # The reader is already active, so these confirmation waits cannot deadlock.
        for channel, names in self._desired.items():
            if names:
                await self._change_subscriptions("subscribe", {channel: set(names)})

    async def listen(self):
        """Read exactly one socket generation; normal closure is a disconnect too."""
        if not self.is_connected or not self.is_authenticated:
            return
        socket, generation = self.websocket, self.connection_generation
        try:
            async for message in socket:
                if socket is not self.websocket or generation != self.connection_generation:
                    return
                try:
                    await self._handle_message(message, generation=generation)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON received from market data stream")
                except Exception:
                    logger.exception("Error processing market data message")
        except (ConnectionClosed, WebSocketException):
            logger.warning("Market data websocket disconnected")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unexpected error in market data listener")
        finally:
            if socket is self.websocket and generation == self.connection_generation:
                await self._cleanup_connection()
                if self.should_reconnect:
                    await self._reconnect()

    async def _handle_message(self, raw_message: str, *, generation: int | None = None):
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
        if generation is not None and generation != self.connection_generation:
            return
        messages = json.loads(raw_message)

        # Messages are always in an array
        if not isinstance(messages, list):
            messages = [messages]

        for message in messages:
            if generation is not None and generation != self.connection_generation:
                return
            if not isinstance(message, dict):
                continue
            self.total_messages_received += 1

            msg_type = message.get("T")

            if msg_type == "success":
                # Subscription confirmation
                logger.debug(f"Subscription confirmed: {message.get('msg')}")
                continue

            elif msg_type == "subscription":
                for channel in self._desired:
                    if channel not in message:
                        continue  # Omitted is not an empty channel snapshot.
                    names = message[channel]
                    if not isinstance(names, list) or any(
                        not isinstance(name, str) or not name for name in names
                    ):
                        self._subscription_error += 1
                        continue
                    confirmed = {name.upper() for name in names}
                    if channel == "quotes":
                        self.quote_subscriptions = confirmed
                    elif channel == "trades":
                        self.trade_subscriptions = confirmed
                    else:
                        for timeframe in self._desired_bar_timeframes or {"1Min"}:
                            self.bar_subscriptions[timeframe] = set(confirmed)
                    self._channel_versions[channel] += 1
                self._subscription_changed.set()
                continue

            elif msg_type == "error":
                # Error message
                code = message.get("code")
                self.last_error_code = code if isinstance(code, int) else None
                self._subscription_error += 1
                self._subscription_changed.set()
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
        """Bounded backoff, preserving explicit-stop intent across every await."""
        while self.should_reconnect and self.reconnect_attempts < self.MAX_RECONNECT_ATTEMPTS:
            self.reconnect_attempts += 1
            delay = self.current_backoff * (1 + random.uniform(-0.1, 0.1))
            await asyncio.sleep(delay)
            if not self.should_reconnect:
                return
            self.current_backoff = min(self.current_backoff * self.BACKOFF_MULTIPLIER, self.MAX_BACKOFF)
            await self._cleanup_connection()
            if not self.should_reconnect:
                return
            if await self.connect():
                return
        if self.should_reconnect and self.on_error:
            await self.on_error("Max reconnect attempts reached")

    def _start_background_tasks(self):
        """At most one listener for the current generation."""
        self.background_tasks = [t for t in self.background_tasks if not t.done()]
        if self._listener is not None and not self._listener.done() and self._listener is not asyncio.current_task():
            return
        self._listener = asyncio.create_task(self.listen())
        self.background_tasks.append(self._listener)
        self.background_tasks.append(asyncio.create_task(self._heartbeat_loop()))

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
            "connection_generation": self.connection_generation,
            "subscriptions_confirmed": all(names <= self._confirmed(c) for c, names in self._desired.items()),
            "desired_subscriptions": {c: len(names) for c, names in self._desired.items()},
            "authenticated": self.is_authenticated,
            "connection_count": self.connection_count,
            "total_messages": self.total_messages_received,
            "quote_subscriptions": len(self.quote_subscriptions),
            "trade_subscriptions": len(self.trade_subscriptions),
            "bar_subscriptions": sum(len(s) for s in self.bar_subscriptions.values()),
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "last_error_code": self.last_error_code,
            "symbol_limit_exceeded": self.symbol_limit_exceeded,
            "refused_symbols": self.refused_symbols,
        }
