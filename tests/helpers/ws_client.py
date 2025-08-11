"""
WebSocket test client helper with heartbeat support.
Provides async WebSocket client for testing real-time data flows and backpressure scenarios.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
import json
import logging
from typing import Any, Union

import websockets
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class WSTestClient:
    """
    Async WebSocket test client with configurable behavior for testing.

    Features:
    - Automatic ping/pong handling
    - Configurable read delays for backpressure testing
    - Message buffering and filtering
    - Connection health monitoring
    - Graceful shutdown handling
    """

    def __init__(
        self,
        uri: str,
        read_delay_ms: int = 0,
        max_message_buffer: int = 1000,
        ping_interval: float = 30.0,
        ping_timeout: float = 10.0,
        auto_reconnect: bool = False,
        reconnect_delay: float = 5.0,
        extra_headers: dict[str, str] | None = None,
    ):
        self.uri = uri
        self.read_delay_ms = read_delay_ms
        self.max_message_buffer = max_message_buffer
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.auto_reconnect = auto_reconnect
        self.reconnect_delay = reconnect_delay
        self.extra_headers = extra_headers or {}

        # Connection state
        self.websocket: WebSocketClientProtocol | None = None
        self.connected = False
        self.connection_id = 0

        # Message handling
        self.message_buffer: list[dict[str, Any]] = []
        self.message_handlers: list[Callable[[dict[str, Any]], None]] = []
        self.dropped_messages = 0

        # Background tasks
        self._background_tasks: set = set()
        self._shutdown_event = asyncio.Event()

        # Stats
        self.stats = {
            "messages_received": 0,
            "messages_sent": 0,
            "connection_count": 0,
            "reconnection_count": 0,
            "ping_sent": 0,
            "pong_received": 0,
            "errors": 0,
        }

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        try:
            self.websocket = await websockets.connect(
                self.uri,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout,
                extra_headers=self.extra_headers,
            )

            self.connected = True
            self.connection_id += 1
            self.stats["connection_count"] += 1

            logger.info(f"WebSocket connected to {self.uri} (connection #{self.connection_id})")

            # Start background tasks
            self._start_background_tasks()

        except Exception as e:
            logger.error(f"Failed to connect to {self.uri}: {e}")
            self.stats["errors"] += 1
            raise

    async def disconnect(self) -> None:
        """Close WebSocket connection gracefully."""
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()

        self.connected = False
        self._shutdown_event.set()

        # Wait for background tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()

        logger.info(f"WebSocket disconnected from {self.uri}")

    async def send_message(self, message: Union[str, dict[str, Any]]) -> None:
        """Send a message through the WebSocket."""
        if not self.websocket or self.websocket.closed:
            raise ConnectionError("WebSocket is not connected")

        if isinstance(message, dict):
            message = json.dumps(message)

        await self.websocket.send(message)
        self.stats["messages_sent"] += 1
        logger.debug(f"Sent message: {message}")

    async def wait_for_message(
        self, timeout: float | None = None, filter_fn: Callable | None = None
    ) -> dict[str, Any]:
        """
        Wait for a specific message matching the filter function.

        Args:
            timeout: Maximum time to wait in seconds
            filter_fn: Function to filter messages, return True to match

        Returns:
            The first message matching the filter

        Raises:
            asyncio.TimeoutError: If timeout is reached
            ConnectionClosed: If connection is lost
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check buffer first
            for i, message in enumerate(self.message_buffer):
                if filter_fn is None or filter_fn(message):
                    return self.message_buffer.pop(i)

            # Check timeout
            if timeout is not None:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    raise TimeoutError(f"No matching message received within {timeout}s")

            # Wait a bit before checking again
            await asyncio.sleep(0.01)

    async def wait_for_messages(
        self, count: int, timeout: float | None = None
    ) -> list[dict[str, Any]]:
        """
        Wait for a specific number of messages.

        Args:
            count: Number of messages to wait for
            timeout: Maximum time to wait in seconds

        Returns:
            List of received messages
        """
        messages = []
        start_time = asyncio.get_event_loop().time()

        while len(messages) < count:
            # Check buffer
            while self.message_buffer and len(messages) < count:
                messages.append(self.message_buffer.pop(0))

            if len(messages) >= count:
                break

            # Check timeout
            if timeout is not None:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    raise TimeoutError(
                        f"Only received {len(messages)}/{count} messages within {timeout}s"
                    )

            await asyncio.sleep(0.01)

        return messages

    def add_message_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Add a message handler function."""
        self.message_handlers.append(handler)

    def remove_message_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Remove a message handler function."""
        if handler in self.message_handlers:
            self.message_handlers.remove(handler)

    def clear_message_buffer(self) -> list[dict[str, Any]]:
        """Clear and return the current message buffer."""
        messages = self.message_buffer.copy()
        self.message_buffer.clear()
        return messages

    def _start_background_tasks(self) -> None:
        """Start background tasks for message handling and connection monitoring."""
        # Message receiver task
        task = asyncio.create_task(self._message_receiver())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        # Auto-reconnect task if enabled
        if self.auto_reconnect:
            task = asyncio.create_task(self._reconnection_monitor())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def _message_receiver(self) -> None:
        """Background task to receive and buffer messages."""
        try:
            while self.connected and not self._shutdown_event.is_set():
                if not self.websocket or self.websocket.closed:
                    break

                try:
                    # Apply read delay if configured (for backpressure testing)
                    if self.read_delay_ms > 0:
                        await asyncio.sleep(self.read_delay_ms / 1000.0)

                    # Receive message with timeout
                    message_raw = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)

                    # Parse message
                    try:
                        message = json.loads(message_raw)
                    except json.JSONDecodeError:
                        message = {"raw": message_raw, "timestamp": datetime.now(UTC).isoformat()}

                    self.stats["messages_received"] += 1

                    # Add timestamp if not present
                    if "timestamp" not in message:
                        message["timestamp"] = datetime.now(UTC).isoformat()

                    # Handle message buffer overflow
                    if len(self.message_buffer) >= self.max_message_buffer:
                        # Drop oldest message
                        dropped = self.message_buffer.pop(0)
                        self.dropped_messages += 1
                        logger.warning(f"Message buffer full, dropped message: {dropped}")

                    # Add to buffer
                    self.message_buffer.append(message)

                    # Call registered handlers
                    for handler in self.message_handlers:
                        try:
                            handler(message)
                        except Exception as e:
                            logger.error(f"Message handler error: {e}")

                    logger.debug(f"Received message: {message}")

                except TimeoutError:
                    # Timeout is expected, just continue
                    continue

                except ConnectionClosed as e:
                    logger.info(f"WebSocket connection closed: {e}")
                    self.connected = False
                    break

                except Exception as e:
                    logger.error(f"Error receiving message: {e}")
                    self.stats["errors"] += 1

        except Exception as e:
            logger.error(f"Message receiver task failed: {e}")
            self.stats["errors"] += 1

    async def _reconnection_monitor(self) -> None:
        """Background task to monitor connection and auto-reconnect if needed."""
        while not self._shutdown_event.is_set():
            await asyncio.sleep(1.0)

            if not self.connected and self.auto_reconnect:
                try:
                    logger.info(f"Attempting to reconnect to {self.uri}")
                    await self.connect()
                    self.stats["reconnection_count"] += 1
                    logger.info("Reconnection successful")

                except Exception as e:
                    logger.warning(f"Reconnection failed: {e}")
                    await asyncio.sleep(self.reconnect_delay)

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()


class WSTestClientPool:
    """
    Pool of WebSocket test clients for load testing scenarios.
    """

    def __init__(self, uri: str, pool_size: int = 10, **client_kwargs):
        self.uri = uri
        self.pool_size = pool_size
        self.client_kwargs = client_kwargs
        self.clients: list[WSTestClient] = []
        self.connected_clients = 0

    async def connect_all(self) -> None:
        """Connect all clients in the pool."""
        self.clients = []

        for i in range(self.pool_size):
            client = WSTestClient(self.uri, **self.client_kwargs)
            try:
                await client.connect()
                self.clients.append(client)
                self.connected_clients += 1
            except Exception as e:
                logger.error(f"Failed to connect client {i}: {e}")

        logger.info(f"Connected {self.connected_clients}/{self.pool_size} clients")

    async def disconnect_all(self) -> None:
        """Disconnect all clients in the pool."""
        tasks = []
        for client in self.clients:
            tasks.append(client.disconnect())

        await asyncio.gather(*tasks, return_exceptions=True)
        self.connected_clients = 0
        self.clients.clear()

    async def broadcast_message(self, message: Union[str, dict[str, Any]]) -> int:
        """
        Send a message to all connected clients.

        Returns:
            Number of clients that successfully sent the message
        """
        tasks = []
        for client in self.clients:
            if client.connected:
                tasks.append(client.send_message(message))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        success_count = sum(1 for result in results if not isinstance(result, Exception))

        return success_count

    def get_aggregate_stats(self) -> dict[str, Any]:
        """Get aggregated statistics from all clients."""
        total_stats = {
            "messages_received": 0,
            "messages_sent": 0,
            "connection_count": 0,
            "reconnection_count": 0,
            "errors": 0,
            "dropped_messages": 0,
        }

        for client in self.clients:
            for key in total_stats:
                if key == "dropped_messages":
                    total_stats[key] += client.dropped_messages
                else:
                    total_stats[key] += client.stats.get(key, 0)

        total_stats["connected_clients"] = self.connected_clients
        total_stats["total_clients"] = len(self.clients)

        return total_stats

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect_all()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect_all()


# Utility functions for testing


async def simulate_slow_consumer(
    client: WSTestClient, delay_ms: int = 100, duration_seconds: int = 10
) -> dict[str, Any]:
    """
    Simulate a slow WebSocket consumer for backpressure testing.

    Args:
        client: WebSocket client to slow down
        delay_ms: Delay between message reads
        duration_seconds: How long to be slow

    Returns:
        Statistics about the simulation
    """
    start_time = asyncio.get_event_loop().time()
    original_delay = client.read_delay_ms

    # Set the client to be slow
    client.read_delay_ms = delay_ms

    stats = {
        "start_buffer_size": len(client.message_buffer),
        "max_buffer_size": len(client.message_buffer),
        "messages_dropped": client.dropped_messages,
    }

    try:
        while (asyncio.get_event_loop().time() - start_time) < duration_seconds:
            await asyncio.sleep(0.1)

            # Track max buffer size
            current_buffer_size = len(client.message_buffer)
            stats["max_buffer_size"] = max(stats["max_buffer_size"], current_buffer_size)

    finally:
        # Restore original delay
        client.read_delay_ms = original_delay

        stats["end_buffer_size"] = len(client.message_buffer)
        stats["total_dropped"] = client.dropped_messages - stats["messages_dropped"]
        stats["duration"] = asyncio.get_event_loop().time() - start_time

    return stats


async def wait_for_client_health(
    client: WSTestClient, expected_messages: int, timeout: float = 10.0
) -> bool:
    """
    Wait for a client to reach a healthy state.

    Args:
        client: Client to monitor
        expected_messages: Minimum number of messages expected
        timeout: Maximum time to wait

    Returns:
        True if client becomes healthy, False on timeout
    """
    start_time = asyncio.get_event_loop().time()

    while (asyncio.get_event_loop().time() - start_time) < timeout:
        if (
            client.connected
            and client.stats["messages_received"] >= expected_messages
            and len(client.message_buffer) > 0
        ):
            return True

        await asyncio.sleep(0.1)

    return False
