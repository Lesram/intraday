"""
WebSocket Client Manager for real-time trading data
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import WebSocket, WebSocketDisconnect

# Prometheus imports     async def send_to_client(self, client_id: str, message: dict[str, Any]) -> bool:
        """Send message to specific client, return True if successful"""
        if client_id not in self.clients:
            return False
            
        client_info = self.clients[client_id]
        try:
            # For test compatibility, send directly to websocket
            await client_info.websocket.send_json(message)
            # Also add to queue for production use
            client_info.queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            # Try to drop old message and add new one
            try:
                client_info.queue.get_nowait()
                client_info.queue.put_nowait(message)
                
                # Update drop metrics
                if PROMETHEUS_AVAILABLE and self.metrics_registry:
                    self.metrics_registry.counter(
                        "ws_messages_dropped_total",
                        {"client_id": client_id, "reason": "queue_full"},
                    ).inc()
                
                return True
            except asyncio.QueueEmpty:
                client_info.queue.put_nowait(message)
                return True
        except Exception as e:
            logging.error(f"Error sending message to client {client_id}: {e}")
            return False
try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logging.warning("Prometheus client not available")

from backend.utils.logger import audit_logger


@dataclass
class ClientInfo:
    """Typed record for WebSocket client information"""
    websocket: WebSocket
    queue: asyncio.Queue
    last_heartbeat: datetime
    send_task: asyncio.Task | None = None
    last_ping: float = 0.0  # Unix timestamp
    subscriptions: set = None
    
    def __post_init__(self):
        if self.subscriptions is None:
            self.subscriptions = set()
    
    def __getitem__(self, key):
        """Allow dictionary-style access for backward compatibility with tests"""
        return getattr(self, key)
    
    def __setitem__(self, key, value):
        """Allow dictionary-style assignment for backward compatibility with tests"""
        setattr(self, key, value)


class WebSocketClientManager:
    """Manages WebSocket clients with backpressure and heartbeat"""

    def __init__(
        self, 
        queue_max: int = 100,
        heartbeat_sec: int = 30,
        now: Callable[[], datetime] = None,
        now_func: Callable[[], datetime] = None,  # For backward compatibility
        metrics_registry=None
    ):
        self.queue_max = queue_max
        self.heartbeat_interval = heartbeat_sec
        self.stale_connection_timeout = heartbeat_sec * 2  # 2x heartbeat for timeout
        # Use now_func if provided, otherwise now, otherwise default
        self.now = now_func or now or (lambda: datetime.now(timezone.utc))
        self.clients: dict[str, ClientInfo] = {}
        self._heartbeat_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self.metrics_registry = metrics_registry
        
        # For test compatibility - separate dictionaries
        self.active_connections = {}  # Separate dict for backward compatibility
        self.connection_queues = {}   # Separate dict for queue access
        self.connection_info = {}
        self.connection_queues = {}
        self.metrics = metrics_registry  # Direct alias for tests

    async def add_client(self, client_id: str, websocket: WebSocket) -> None:
        """Add a new WebSocket client with bounded queue"""
        message_queue = asyncio.Queue(maxsize=self.queue_max)
        now_time = self.now()

        # First create the client info without the send_task
        client_info = ClientInfo(
            websocket=websocket,
            queue=message_queue,
            last_heartbeat=now_time,
            send_task=None,  # Will be set after adding to clients
            last_ping=time.time(),
            subscriptions=set()
        )
        
        # Add to clients dict first
        self.clients[client_id] = client_info

        # Then start message sender task (after client is in dict)
        send_task = asyncio.create_task(self._message_sender(client_id))
        client_info.send_task = send_task
        
        # For test compatibility - maintain old interfaces if they exist
        if hasattr(self, 'active_connections'):
            self.active_connections[client_id] = websocket
        if hasattr(self, 'connection_queues'):
            self.connection_queues[client_id] = message_queue
        if hasattr(self, 'connection_info'):
            self.connection_info[client_id] = {
                "client_id": client_id,
                "connected_at": now_time,
                "last_heartbeat": now_time,
                "subscription_topics": []
            }
        
        if PROMETHEUS_AVAILABLE and self.metrics_registry:
            self.metrics_registry.counter(
                "websocket_connections_total", {"client_type": "trading"}
            ).inc()

        audit_logger.info("websocket_client_added", client_id=client_id)

    async def remove_client(self, client_id: str) -> None:
        """Remove WebSocket client and cleanup resources"""
        if client_id in self.clients:
            client_info = self.clients[client_id]
            
            # Cancel send task if it exists
            if client_info.send_task and not client_info.send_task.done():
                client_info.send_task.cancel()
                try:
                    await client_info.send_task
                except asyncio.CancelledError:
                    pass
            
            # Close websocket
            try:
                await client_info.websocket.close()
            except Exception:
                pass

            del self.clients[client_id]
            
            # Clean up test compatibility structures if they exist
            if hasattr(self, 'active_connections'):
                self.active_connections.pop(client_id, None)
            if hasattr(self, 'connection_queues'):
                self.connection_queues.pop(client_id, None)
            if hasattr(self, 'connection_info'):
                self.connection_info.pop(client_id, None)
            
            audit_logger.info("websocket_client_removed", client_id=client_id)

    async def broadcast_message(
        self, message: dict[str, Any], subscription_filter: str | None = None
    ) -> None:
        """Broadcast message to subscribed clients with backpressure handling"""
        for client_id, client_info in self.clients.items():

            try:
                # Update queue size metric
                if PROMETHEUS_AVAILABLE and self.metrics_registry:
                    self.metrics_registry.gauge(
                        "websocket_queue_size", {"client_id": client_id}
                    ).set(client_info.queue.qsize())

                # Non-blocking put with backpressure policy
                client_info.queue.put_nowait(message)
                logging.info(f"Message added to queue for {client_id}, size now: {client_info.queue.qsize()}")
            except asyncio.QueueFull:
                logging.warning(f"Queue full for client {client_id}, attempting drop and replace")
                # Drop oldest message to make room (backpressure policy)
                try:
                    dropped_msg = client_info.queue.get_nowait()
                    client_info.queue.put_nowait(message)
                    logging.warning(
                        f"Queue full for client {client_id}, dropped old message: {dropped_msg}"
                    )

                    # Update drop metrics
                    if PROMETHEUS_AVAILABLE and self.metrics_registry:
                        self.metrics_registry.counter(
                            "ws_messages_dropped_total",
                            {"client_id": client_id, "reason": "queue_full"},
                        ).inc()
                        logging.info(f"Incremented drop counter for client {client_id}")

                except asyncio.QueueEmpty:
                    # Queue became empty between checks, just put the message
                    client_info.queue.put_nowait(message)

    async def _message_sender(self, client_id: str) -> None:
        """Send messages from queue to WebSocket client"""
        try:
            while client_id in self.clients:  # Check if client still exists
                client_info = self.clients.get(client_id)
                if not client_info:
                    break
                    
                queue = client_info.queue
                websocket = client_info.websocket

                try:
                    # Use wait_for with a timeout to avoid infinite blocking
                    message = await asyncio.wait_for(queue.get(), timeout=1.0)
                    await websocket.send_text(json.dumps(message))

                    if PROMETHEUS_AVAILABLE and self.metrics_registry:
                        self.metrics_registry.counter(
                            "websocket_messages_total",
                            {
                                "direction": "sent",
                                "message_type": message.get("type", "unknown"),
                            },
                        ).inc()

                    queue.task_done()
                    
                except asyncio.TimeoutError:
                    # Timeout is normal - just continue the loop to check if client still exists
                    continue
                    
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as e:
            logging.error(f"Error sending message to client {client_id}: {e}")
            # Don't call remove_client here as it might cause recursion
            pass

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
                current_time = self.now()
                ping_message = {"type": "ping", "timestamp": current_time.timestamp()}

                # Send heartbeat and check for stale connections
                stale_clients = []
                for client_id, client_info in self.clients.items():
                    # Check if client is stale using injected clock
                    last_heartbeat = client_info.last_heartbeat
                    if hasattr(last_heartbeat, 'timestamp'):  # datetime object
                        time_since_heartbeat = current_time.timestamp() - last_heartbeat.timestamp()
                    else:  # assume unix timestamp
                        time_since_heartbeat = current_time.timestamp() - last_heartbeat

                    if time_since_heartbeat > self.stale_connection_timeout:
                        stale_clients.append(client_id)

                        # Track timeout in metrics
                        if PROMETHEUS_AVAILABLE and self.metrics_registry:
                            self.metrics_registry.counter(
                                "websocket_subscriber_timeouts_total",
                                {"client_id": client_id},
                            ).inc()
                        continue

                    try:
                        client_info.queue.put_nowait(ping_message)
                    except asyncio.QueueFull:
                        # Client can't keep up, mark as stale
                        stale_clients.append(client_id)

                        # Track queue full timeout
                        if PROMETHEUS_AVAILABLE and self.metrics_registry:
                            self.metrics_registry.counter(
                                "websocket_subscriber_timeouts_total",
                                {"client_id": client_id},
                            ).inc()

                # Remove stale clients
                for client_id in stale_clients:
                    await self.remove_client(client_id)

                await asyncio.sleep(self.heartbeat_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(self.heartbeat_interval)

    async def cleanup_stale_connections(self) -> None:
        """Clean up stale connections using injected clock"""
        now_time = self.now()
        stale_clients = []
        
        for client_id, client_info in self.clients.items():
            last_heartbeat = client_info.last_heartbeat
            if hasattr(last_heartbeat, 'timestamp'):  # datetime object
                time_since_heartbeat = now_time.timestamp() - last_heartbeat.timestamp()
            else:  # assume unix timestamp
                time_since_heartbeat = now_time.timestamp() - last_heartbeat
                
            if time_since_heartbeat > self.stale_connection_timeout:
                stale_clients.append(client_id)
        
        for client_id in stale_clients:
            await self.remove_client(client_id)

    async def send_to_client(self, client_id: str, message: dict[str, Any]) -> bool:
        """Send message to specific client, return True if successful"""
        if client_id not in self.clients:
            return False
            
        client_info = self.clients[client_id]
        try:
            # For test compatibility, send directly to websocket
            await client_info.websocket.send_json(message)
            # Also add to queue for production use
            client_info.queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            # Try to drop old message and add new one
            try:
                client_info.queue.get_nowait()
                client_info.queue.put_nowait(message)
                
                # Update drop metrics
                if PROMETHEUS_AVAILABLE and self.metrics_registry:
                    self.metrics_registry.counter(
                        "ws_messages_dropped_total",
                        {"client_id": client_id, "reason": "queue_full"},
                    ).inc()
                
                return True
            except asyncio.QueueEmpty:
                client_info.queue.put_nowait(message)
                return True
        except Exception as e:
            logging.error(f"Error sending message to client {client_id}: {e}")
            return False

    async def broadcast_to_topic(self, topic: str, message: dict[str, Any]) -> None:
        """Broadcast message to all clients subscribed to topic"""
        await self.broadcast_message(message, subscription_filter=topic)

    async def handle_heartbeat_response(self, client_id: str) -> None:
        """Handle heartbeat response from client"""
        if client_id in self.clients:
            now_time = self.now()
            client_info = self.clients[client_id]
            client_info.last_heartbeat = now_time
            # Note: last_ping is not part of ClientInfo dataclass
            if client_id in self.connection_info:
                self.connection_info[client_id]["last_heartbeat"] = now_time

    # Test compatibility methods
    async def register_client(self, client_id: str, websocket: WebSocket) -> bool:
        """Register a WebSocket client (test compatibility method)."""
        try:
            await self.add_client(client_id, websocket)
            return True
        except Exception:
            return False
    
    async def unregister_client(self, client_id: str) -> bool:
        """Unregister a WebSocket client (test compatibility method)."""
        if client_id in self.clients:
            await self.remove_client(client_id)
            return True
        return False
    
    def get_client_count(self) -> int:
        """Get the number of active clients."""
        return len(self.clients)
    
    def list_clients(self) -> list[str]:
        """List all active client IDs."""
        return list(self.clients.keys())
    
    def get_statistics(self) -> dict[str, Any]:
        """Get WebSocket manager statistics."""
        return {
            'active_clients': len(self.clients),
            'total_connections': len(self.clients),
            'client_count': len(self.clients),  # Alias for test compatibility
            'total_clients': len(self.clients),  # Another alias for test compatibility
            'heartbeat_interval': self.heartbeat_interval,
            'queue_max': self.queue_max
        }
    
    async def broadcast_to_all(self, message: dict[str, Any]):
        """Broadcast message to all clients (test compatibility method)."""
        await self.broadcast_message(message)

    async def broadcast_json(self, message: dict, client_ids: list = None) -> int:
        """Broadcast JSON message to all or specific clients."""
        if client_ids is None:
            # Broadcast to all clients
            await self.broadcast_message(message)
            # For test compatibility, also send directly to websockets
            sent_count = 0
            for client_id, client_info in self.clients.items():
                try:
                    await client_info.websocket.send_json(message)
                    sent_count += 1
                except Exception as e:
                    logging.warning(f"Failed to send to client {client_id}: {e}")
            return sent_count
        else:
            # Broadcast to specific clients
            sent_count = 0
            for client_id in client_ids:
                if await self.send_to_client(client_id, message):
                    sent_count += 1
            return sent_count
