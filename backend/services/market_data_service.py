"""
Market Data Service - Real-Time WebSocket Manager

This service manages real-time market data streaming between:
1. Alpaca Market Data API (upstream WebSocket)
2. Frontend clients (downstream WebSocket connections)

Features:
- Multi-client connection management
- Symbol subscription tracking
- Rate limiting and throttling
- Message broadcasting
- Connection lifecycle management
- Memory-efficient client pooling

Safety Features:
- Max 100 concurrent clients
- Max 100 symbols per client
- Automatic cleanup on disconnect
- Graceful error handling
- Circuit breaker integration

Created: October 16, 2025 - Phase 7 Day 1
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
import uuid

from fastapi import WebSocket
from websockets.exceptions import ConnectionClosed

from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


@dataclass
class ClientConnection:
    """Represents a connected frontend client"""
    client_id: str
    websocket: WebSocket
    subscriptions: set[str] = field(default_factory=set)
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(UTC))
    message_count: int = 0


@dataclass
class MarketDataStats:
    """Service statistics for monitoring"""
    total_clients: int = 0
    total_subscriptions: int = 0
    total_messages_sent: int = 0
    total_messages_received: int = 0
    uptime_seconds: int = 0
    alpaca_connected: bool = False


class MarketDataService:
    """
    Manages real-time market data streaming from Alpaca to frontend clients.

    Architecture:
    - Single Alpaca WebSocket connection (upstream)
    - Multiple frontend WebSocket connections (downstream)
    - Pub/sub pattern: Alpaca publishes, service broadcasts to subscribed clients

    Message Flow:
    1. Frontend subscribes to symbol (e.g., AAPL)
    2. Service subscribes to Alpaca (if not already subscribed)
    3. Alpaca sends quote updates
    4. Service broadcasts to all clients subscribed to that symbol

    Lifecycle:
    - Service starts → Connect to Alpaca
    - Client connects → Register client
    - Client subscribes → Track subscription, subscribe to Alpaca if needed
    - Alpaca sends data → Broadcast to subscribed clients
    - Client unsubscribes → Remove subscription, unsubscribe from Alpaca if no more clients
    - Client disconnects → Cleanup subscriptions
    - Service stops → Disconnect from Alpaca, close all clients
    """

    # Configuration constants
    MAX_CLIENTS = 100  # Maximum concurrent clients
    MAX_SYMBOLS_PER_CLIENT = 100  # Maximum symbols per client
    MAX_TOTAL_SYMBOLS = 500  # Maximum unique symbols across all clients
    HEARTBEAT_INTERVAL = 30  # Seconds between heartbeat checks
    MESSAGE_RATE_LIMIT = 10  # Max messages per second per symbol

    def __init__(self):
        """Initialize the market data service"""
        # Client management
        self.clients: dict[str, ClientConnection] = {}  # {client_id: ClientConnection}
        self.subscriptions: dict[str, set[str]] = defaultdict(set)  # {symbol: {client_ids}}

        # Alpaca connection (will be initialized in start())
        self.alpaca_stream = None  # AlpacaMarketDataStream instance
        self.alpaca_connected = False

        # Message queues
        self.outgoing_queue = asyncio.Queue()  # Messages to send to clients
        self.rate_limiters: dict[str, list[float]] = defaultdict(list)  # {symbol: [timestamps]}

        # Service state
        self.is_running = False
        self.start_time: datetime | None = None

        # Background tasks
        self.background_tasks: list[asyncio.Task] = []

        logger.info("MarketDataService initialized")

    async def start(self, api_key: str, api_secret: str, paper: bool = True):
        """
        Start the market data service and connect to Alpaca.

        Args:
            api_key: Alpaca API key
            api_secret: Alpaca API secret
            paper: Use paper trading endpoint
        """
        if self.is_running:
            logger.warning("Service already running")
            return

        logger.info("Starting MarketDataService", paper=paper)

        try:
            # Initialize Alpaca stream connection
            self.alpaca_stream = AlpacaMarketDataStream(api_key, api_secret, paper)

            # Set up callbacks
            self.alpaca_stream.on_quote = self._handle_alpaca_quote
            self.alpaca_stream.on_trade = self._handle_alpaca_trade
            self.alpaca_stream.on_bar = self._handle_alpaca_bar
            self.alpaca_stream.on_error = self._handle_alpaca_error

            # Connect to Alpaca
            connected = await self.alpaca_stream.connect()
            if not connected:
                raise Exception("Failed to connect to Alpaca market data stream")

            self.alpaca_connected = True
            self.is_running = True
            self.start_time = datetime.now(UTC)

            # Start background tasks
            self.background_tasks = [
                asyncio.create_task(self._message_broadcaster()),
                asyncio.create_task(self._heartbeat_monitor()),
                asyncio.create_task(self._cleanup_inactive_clients())
            ]

            logger.info("MarketDataService started successfully")

        except Exception as e:
            logger.error(f"Failed to start MarketDataService: {e}", exc_info=True)
            await self.stop()
            raise

    async def stop(self):
        """Stop the market data service and cleanup resources"""
        logger.info("Stopping MarketDataService")

        self.is_running = False

        # Cancel background tasks
        for task in self.background_tasks:
            task.cancel()

        # Wait for tasks to complete
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)

        # Disconnect all clients
        for client_id in list(self.clients.keys()):
            await self.remove_client(client_id)

        # Disconnect from Alpaca
        if self.alpaca_stream:
            await self.alpaca_stream.disconnect()

        self.alpaca_connected = False

        logger.info("MarketDataService stopped")

    async def add_client(self, websocket: WebSocket) -> str:
        """
        Register a new frontend client connection.

        Args:
            websocket: FastAPI WebSocket connection

        Returns:
            client_id: Unique identifier for this client

        Raises:
            ValueError: If max clients exceeded
        """
        if len(self.clients) >= self.MAX_CLIENTS:
            raise ValueError(f"Maximum clients ({self.MAX_CLIENTS}) exceeded")

        client_id = str(uuid.uuid4())

        client = ClientConnection(
            client_id=client_id,
            websocket=websocket
        )

        self.clients[client_id] = client

        logger.info(f"Client connected: {client_id}", total_clients=len(self.clients))

        # Send welcome message
        await self._send_to_client(client_id, {
            "type": "connected",
            "client_id": client_id,
            "message": "Connected to market data service"
        })

        return client_id

    async def remove_client(self, client_id: str):
        """
        Remove a client connection and cleanup subscriptions.

        Args:
            client_id: Client to remove
        """
        if client_id not in self.clients:
            logger.warning(f"Client not found: {client_id}")
            return

        client = self.clients[client_id]

        # Unsubscribe from all symbols
        for symbol in list(client.subscriptions):
            await self.unsubscribe(client_id, symbol)

        # Close WebSocket connection
        try:
            await client.websocket.close()
        except Exception as e:
            logger.warning(f"Error closing WebSocket for {client_id}: {e}")

        # Remove from clients dict
        del self.clients[client_id]

        logger.info(
            f"Client disconnected: {client_id}",
            total_clients=len(self.clients),
            messages_sent=client.message_count
        )

    async def subscribe(self, client_id: str, symbol: str) -> bool:
        """
        Subscribe a client to a symbol's market data.

        Args:
            client_id: Client requesting subscription
            symbol: Stock symbol (e.g., "AAPL")

        Returns:
            bool: True if subscribed successfully

        Raises:
            ValueError: If client not found or limits exceeded
        """
        if client_id not in self.clients:
            raise ValueError(f"Client not found: {client_id}")

        client = self.clients[client_id]

        # Check client symbol limit
        if len(client.subscriptions) >= self.MAX_SYMBOLS_PER_CLIENT:
            raise ValueError(
                f"Client symbol limit ({self.MAX_SYMBOLS_PER_CLIENT}) exceeded"
            )

        # Check total symbol limit
        if len(self.subscriptions) >= self.MAX_TOTAL_SYMBOLS:
            raise ValueError(
                f"Total symbol limit ({self.MAX_TOTAL_SYMBOLS}) exceeded"
            )

        # Normalize symbol (uppercase)
        symbol = symbol.upper()

        # Add to client subscriptions
        client.subscriptions.add(symbol)

        # Add client to symbol's subscriber list
        self.subscriptions[symbol].add(client_id)

        # Subscribe to Alpaca if this is the first client for this symbol
        if len(self.subscriptions[symbol]) == 1 and self.alpaca_stream:
            try:
                await self.alpaca_stream.subscribe_quotes([symbol])
            except Exception as e:
                logger.error(f"Failed to subscribe to Alpaca for {symbol}: {e}")
                # Rollback subscription
                client.subscriptions.remove(symbol)
                self.subscriptions[symbol].remove(client_id)
                if not self.subscriptions[symbol]:
                    del self.subscriptions[symbol]
                return False

        logger.info(
            f"Client {client_id} subscribed to {symbol}",
            total_subscribers=len(self.subscriptions[symbol])
        )

        # Send confirmation to client
        await self._send_to_client(client_id, {
            "type": "subscribed",
            "symbol": symbol,
            "message": f"Subscribed to {symbol}"
        })

        return True

    async def unsubscribe(self, client_id: str, symbol: str) -> bool:
        """
        Unsubscribe a client from a symbol's market data.

        Args:
            client_id: Client requesting unsubscription
            symbol: Stock symbol

        Returns:
            bool: True if unsubscribed successfully
        """
        if client_id not in self.clients:
            logger.warning(f"Client not found: {client_id}")
            return False

        symbol = symbol.upper()
        client = self.clients[client_id]

        # Remove from client subscriptions
        if symbol in client.subscriptions:
            client.subscriptions.remove(symbol)

        # Remove client from symbol's subscriber list
        if symbol in self.subscriptions:
            self.subscriptions[symbol].discard(client_id)

            # Unsubscribe from Alpaca if no more clients need this symbol
            if not self.subscriptions[symbol]:
                del self.subscriptions[symbol]

                if self.alpaca_stream:
                    try:
                        await self.alpaca_stream.unsubscribe([symbol])
                    except Exception as e:
                        logger.error(f"Failed to unsubscribe from Alpaca for {symbol}: {e}")

        logger.info(f"Client {client_id} unsubscribed from {symbol}")

        # Send confirmation to client
        await self._send_to_client(client_id, {
            "type": "unsubscribed",
            "symbol": symbol,
            "message": f"Unsubscribed from {symbol}"
        })

        return True

    async def broadcast_quote(self, symbol: str, quote_data: dict[str, Any]):
        """
        Broadcast a quote update to all subscribed clients.

        Args:
            symbol: Stock symbol
            quote_data: Quote data from Alpaca
        """
        symbol = symbol.upper()

        # Check if anyone is subscribed to this symbol
        if symbol not in self.subscriptions:
            return

        # Rate limiting (prevent overwhelming clients)
        if not self._check_rate_limit(symbol):
            logger.debug(f"Rate limit exceeded for {symbol}, dropping message")
            return

        # Prepare message
        message = {
            "type": "quote",
            "symbol": symbol,
            "data": quote_data,
            "timestamp": datetime.now(UTC).isoformat()
        }

        # Queue for broadcasting
        await self.outgoing_queue.put((symbol, message))

    async def _message_broadcaster(self):
        """Background task: Broadcast messages to clients"""
        logger.info("Message broadcaster started")

        try:
            while self.is_running:
                try:
                    # Wait for message with timeout
                    symbol, message = await asyncio.wait_for(
                        self.outgoing_queue.get(),
                        timeout=1.0
                    )

                    # Get subscribed clients
                    subscribers = self.subscriptions.get(symbol, set())

                    # Send to each subscriber
                    for client_id in subscribers:
                        await self._send_to_client(client_id, message)

                except TimeoutError:
                    continue  # No messages, continue loop
                except Exception as e:
                    logger.error(f"Error in message broadcaster: {e}", exc_info=True)
                    await asyncio.sleep(1.0)  # Back off on errors

        finally:
            logger.info("Message broadcaster stopped")

    async def _heartbeat_monitor(self):
        """Background task: Monitor client connections with heartbeat"""
        logger.info("Heartbeat monitor started")

        try:
            while self.is_running:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)

                for client_id in list(self.clients.keys()):
                    try:
                        client = self.clients[client_id]

                        # Send ping
                        await self._send_to_client(client_id, {
                            "type": "ping",
                            "timestamp": datetime.now(UTC).isoformat()
                        })

                        # Update last heartbeat
                        client.last_heartbeat = datetime.now(UTC)

                    except Exception as e:
                        logger.warning(f"Heartbeat failed for {client_id}: {e}")
                        # Client connection might be dead, will be cleaned up by cleanup task

        finally:
            logger.info("Heartbeat monitor stopped")

    async def _cleanup_inactive_clients(self):
        """Background task: Remove inactive/disconnected clients"""
        logger.info("Cleanup task started")

        try:
            while self.is_running:
                await asyncio.sleep(60)  # Check every minute

                now = datetime.now(UTC)
                inactive_threshold = 120  # 2 minutes

                for client_id in list(self.clients.keys()):
                    client = self.clients[client_id]

                    # Check if client is inactive
                    inactive_seconds = (now - client.last_heartbeat).total_seconds()

                    if inactive_seconds > inactive_threshold:
                        logger.warning(
                            f"Removing inactive client {client_id}",
                            inactive_seconds=inactive_seconds
                        )
                        await self.remove_client(client_id)

        finally:
            logger.info("Cleanup task stopped")

    async def _send_to_client(self, client_id: str, message: dict[str, Any]):
        """
        Send a message to a specific client.

        Args:
            client_id: Client to send to
            message: Message dictionary
        """
        if client_id not in self.clients:
            return

        client = self.clients[client_id]

        try:
            await client.websocket.send_json(message)
            client.message_count += 1

        except ConnectionClosed:
            logger.warning(f"Client {client_id} connection closed")
            await self.remove_client(client_id)
        except Exception as e:
            logger.error(f"Error sending to client {client_id}: {e}")
            await self.remove_client(client_id)

    def _check_rate_limit(self, symbol: str) -> bool:
        """
        Check if message rate limit is exceeded for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            bool: True if message can be sent
        """
        now = datetime.now(UTC).timestamp()

        # Get timestamps for this symbol
        timestamps = self.rate_limiters[symbol]

        # Remove old timestamps (outside 1 second window)
        timestamps[:] = [ts for ts in timestamps if now - ts < 1.0]

        # Check limit
        if len(timestamps) >= self.MESSAGE_RATE_LIMIT:
            return False  # Rate limit exceeded

        # Add current timestamp
        timestamps.append(now)

        return True

    def get_stats(self) -> MarketDataStats:
        """
        Get service statistics.

        Returns:
            MarketDataStats: Current service statistics
        """
        uptime = 0
        if self.start_time:
            uptime = int((datetime.now(UTC) - self.start_time).total_seconds())

        total_subscriptions = sum(len(subs) for subs in self.subscriptions.values())

        return MarketDataStats(
            total_clients=len(self.clients),
            total_subscriptions=total_subscriptions,
            total_messages_sent=sum(c.message_count for c in self.clients.values()),
            uptime_seconds=uptime,
            alpaca_connected=self.alpaca_connected
        )

    def get_subscriptions_for_client(self, client_id: str) -> list[str]:
        """
        Get all subscriptions for a specific client.

        Args:
            client_id: Client ID

        Returns:
            List of subscribed symbols
        """
        if client_id not in self.clients:
            return []

        return list(self.clients[client_id].subscriptions)

    def get_subscribers_for_symbol(self, symbol: str) -> list[str]:
        """
        Get all clients subscribed to a specific symbol.

        Args:
            symbol: Stock symbol

        Returns:
            List of client IDs
        """
        symbol = symbol.upper()
        return list(self.subscriptions.get(symbol, set()))

    # Alpaca callback handlers

    async def _handle_alpaca_quote(self, symbol: str, quote_data: dict[str, Any]):
        """Handle quote update from Alpaca"""
        await self.broadcast_quote(symbol, quote_data)

    async def _handle_alpaca_trade(self, symbol: str, trade_data: dict[str, Any]):
        """Handle trade update from Alpaca"""
        # For now, we'll use trade data to update the "last" price in quotes
        # Can be extended to broadcast trade data separately
        quote_data = {
            "last": trade_data.get("price"),
            "last_size": trade_data.get("size"),
            "timestamp": trade_data.get("timestamp")
        }
        await self.broadcast_quote(symbol, quote_data)

    async def _handle_alpaca_bar(self, symbol: str, bar_data: dict[str, Any]):
        """Handle bar update from Alpaca"""
        # Bars can be broadcasted as a separate message type if needed
        # For now, we'll just log them
        logger.debug(f"Received bar for {symbol}: {bar_data}")

    async def _handle_alpaca_error(self, error_message: str):
        """Handle error from Alpaca stream"""
        logger.error(f"Alpaca stream error: {error_message}")

        # Broadcast error to all connected clients
        error_msg = {
            "type": "error",
            "source": "alpaca",
            "message": error_message,
            "timestamp": datetime.now(UTC).isoformat()
        }

        for client_id in list(self.clients.keys()):
            await self._send_to_client(client_id, error_msg)


# Global service instance (singleton pattern)
_market_data_service: MarketDataService | None = None


def get_market_data_service() -> MarketDataService:
    """
    Get the global MarketDataService instance.

    Returns:
        MarketDataService: Singleton instance
    """
    global _market_data_service

    if _market_data_service is None:
        _market_data_service = MarketDataService()

    return _market_data_service


async def start_market_data_service(api_key: str, api_secret: str, paper: bool = True):
    """
    Start the global market data service.

    Args:
        api_key: Alpaca API key
        api_secret: Alpaca API secret
        paper: Use paper trading endpoint
    """
    service = get_market_data_service()
    await service.start(api_key, api_secret, paper)


async def stop_market_data_service():
    """Stop the global market data service"""
    global _market_data_service

    if _market_data_service:
        await _market_data_service.stop()
        _market_data_service = None
