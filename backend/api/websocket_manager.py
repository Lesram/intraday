"""
WebSocket Client Manager for real-time trading data
"""

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

# Prometheus imports - using centralized metrics registry
try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logging.warning("Prometheus client not available")

from backend.utils.logger import audit_logger


class WebSocketClientManager:
    """Manages WebSocket clients with backpressure and heartbeat"""

    def __init__(self, max_queue_size: int = 100, metrics_registry=None):
        self.max_queue_size = max_queue_size
        self.clients: dict[str, dict[str, Any]] = {}
        self._heartbeat_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self.metrics_registry = metrics_registry

    async def add_client(self, client_id: str, websocket: WebSocket) -> None:
        """Add a new WebSocket client with bounded queue"""
        message_queue = asyncio.Queue(maxsize=self.max_queue_size)

        self.clients[client_id] = {
            "websocket": websocket,
            "queue": message_queue,
            "last_ping": time.time(),
            "subscriptions": set(),
            "send_task": None,
        }

        # Start message sender task for this client
        send_task = asyncio.create_task(self._message_sender(client_id))
        self.clients[client_id]["send_task"] = send_task

        if PROMETHEUS_AVAILABLE and self.metrics_registry:
            self.metrics_registry.counter(
                "websocket_connections_total", {"client_type": "trading"}
            ).inc()

        audit_logger.info("websocket_client_added", client_id=client_id)

    async def remove_client(self, client_id: str) -> None:
        """Remove WebSocket client and cleanup resources"""
        if client_id in self.clients:
            client_info = self.clients[client_id]

            # Cancel send task
            if client_info["send_task"]:
                client_info["send_task"].cancel()
                try:
                    await client_info["send_task"]
                except asyncio.CancelledError:
                    pass

            # Close websocket
            try:
                await client_info["websocket"].close()
            except Exception:
                pass

            del self.clients[client_id]
            audit_logger.info("websocket_client_removed", client_id=client_id)

    async def broadcast_message(
        self, message: dict[str, Any], subscription_filter: str | None = None
    ) -> None:
        """Broadcast message to subscribed clients with backpressure handling"""
        for client_id, client_info in self.clients.items():
            if subscription_filter and subscription_filter not in client_info["subscriptions"]:
                continue

            try:
                # Update queue size metric
                if PROMETHEUS_AVAILABLE and self.metrics_registry:
                    self.metrics_registry.gauge(
                        "websocket_queue_size", {"client_id": client_id}
                    ).set(client_info["queue"].qsize())

                # Non-blocking put with backpressure policy
                client_info["queue"].put_nowait(message)
            except asyncio.QueueFull:
                # Drop oldest message to make room (backpressure policy)
                try:
                    client_info["queue"].get_nowait()
                    client_info["queue"].put_nowait(message)
                    logging.warning(f"Queue full for client {client_id}, dropped old message")

                    # Update metrics
                    if PROMETHEUS_AVAILABLE and self.metrics_registry:
                        self.metrics_registry.counter(
                            "websocket_messages_dropped_total",
                            {"client_id": client_id, "reason": "queue_full"},
                        ).inc()

                except asyncio.QueueEmpty:
                    # Queue became empty between checks, just put the message
                    client_info["queue"].put_nowait(message)
                    pass

    async def _message_sender(self, client_id: str) -> None:
        """Send messages from queue to WebSocket client"""
        client_info = self.clients.get(client_id)
        if not client_info:
            return

        websocket = client_info["websocket"]
        queue = client_info["queue"]

        try:
            while True:
                message = await queue.get()
                await websocket.send_text(json.dumps(message))

                if PROMETHEUS_AVAILABLE and self.metrics_registry:
                    self.metrics_registry.counter(
                        "websocket_messages_total",
                        {"direction": "sent", "message_type": message.get("type", "unknown")},
                    ).inc()

                queue.task_done()

        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as e:
            logging.error(f"Error sending message to client {client_id}: {e}")
            await self.remove_client(client_id)

    async def start_heartbeat(self) -> None:
        """Start heartbeat task"""
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop_heartbeat(self) -> None:
        """Stop heartbeat task"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat to all clients"""
        while True:
            try:
                current_time = time.time()
                ping_message = {"type": "ping", "timestamp": current_time}

                # Send heartbeat and check for stale connections
                stale_clients = []
                for client_id, client_info in self.clients.items():
                    # Check if client is stale (no pong for 60 seconds)
                    if current_time - client_info["last_ping"] > 60:
                        stale_clients.append(client_id)

                        # Track timeout in metrics
                        if PROMETHEUS_AVAILABLE and self.metrics_registry:
                            self.metrics_registry.counter(
                                "websocket_subscriber_timeouts_total", {"client_id": client_id}
                            ).inc()
                        continue

                    try:
                        client_info["queue"].put_nowait(ping_message)
                    except asyncio.QueueFull:
                        # Client can't keep up, mark as stale
                        stale_clients.append(client_id)

                        # Track queue full timeout
                        if PROMETHEUS_AVAILABLE and self.metrics_registry:
                            self.metrics_registry.counter(
                                "websocket_subscriber_timeouts_total", {"client_id": client_id}
                            ).inc()

                # Remove stale clients
                for client_id in stale_clients:
                    await self.remove_client(client_id)

                await asyncio.sleep(30)  # Heartbeat every 30 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(30)
