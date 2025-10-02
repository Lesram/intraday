"""
Alpaca WebSocket Stream Integration for Real-time Order Updates

This module provides real-time order status updates via Alpaca's WebSocket stream.
Handles trade_updates events and updates the local database with order status changes.

Key Features:
- Real-time order status updates (new -> filled -> etc)
- Automatic reconnection with exponential backoff
- Backpressure handling for high-frequency updates
- Comprehensive error handling and logging
- Integration with existing order repository
"""

import asyncio
import json
import os
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.infra.db import get_db_session
from backend.infra.repositories.orders import OrdersRepo
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


class AlpacaStreamClient:
    """
    WebSocket client for Alpaca trade updates stream.
    
    Connects to Alpaca's trade_updates WebSocket and processes order status changes
    in real-time, updating the local database with the latest order information.
    """
    
    def __init__(self):
        """Initialize the Alpaca stream client."""
        self.settings = get_settings()
        
        # Alpaca WebSocket configuration
        self.api_key = os.getenv("ALPACA_API_KEY_ID")
        self.api_secret = os.getenv("ALPACA_API_SECRET_KEY")
        self.is_paper = os.getenv("ALPACA_PAPER", "true").lower() in ("true", "1", "yes")
        
        # WebSocket URL
        if self.is_paper:
            self.ws_url = os.getenv("ALPACA_STREAM_URL", "wss://paper-api.alpaca.markets/stream")
        else:
            self.ws_url = os.getenv("ALPACA_STREAM_URL", "wss://api.alpaca.markets/stream")
        
        # Connection management
        self.websocket = None
        self.is_connected = False
        self.is_authenticated = False
        self.should_reconnect = True
        
        # Reconnection configuration
        self.reconnect_delay = 1.0
        self.max_reconnect_delay = 60.0
        self.reconnect_multiplier = 2.0
        self.max_reconnect_attempts = 10
        self.reconnect_attempts = 0
        
        # Update queue for backpressure handling
        self.update_queue = asyncio.Queue(maxsize=1000)
        self.queue_processor_task = None
        
        # Heartbeat configuration
        self.heartbeat_interval = 30.0
        self.last_heartbeat = time.time()
        self.heartbeat_task = None
        
        logger.info("AlpacaStreamClient initialized",
                   is_paper=self.is_paper,
                   ws_url=self.ws_url)
    
    async def connect(self) -> bool:
        """
        Connect to Alpaca WebSocket stream.
        
        Returns:
            bool: True if connected successfully, False otherwise
        """
        if not self.api_key or not self.api_secret:
            logger.error("Alpaca API credentials not configured")
            return False
        
        try:
            logger.info("Connecting to Alpaca WebSocket stream", url=self.ws_url)
            
            # Connect to WebSocket
            self.websocket = await websockets.connect(
                self.ws_url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=10
            )
            
            self.is_connected = True
            self.reconnect_attempts = 0
            
            logger.info("Connected to Alpaca WebSocket stream")
            
            # Authenticate
            if await self._authenticate():
                # Subscribe to trade updates
                await self._subscribe_to_trade_updates()
                
                # Start background tasks
                await self._start_background_tasks()
                
                return True
            else:
                await self._disconnect()
                return False
                
        except Exception as e:
            logger.error("Failed to connect to Alpaca WebSocket",
                        error=str(e),
                        error_type=type(e).__name__)
            self.is_connected = False
            return False
    
    async def _authenticate(self) -> bool:
        """
        Authenticate with Alpaca WebSocket stream.
        
        Returns:
            bool: True if authenticated successfully, False otherwise
        """
        try:
            auth_message = {
                "action": "auth",
                "key": self.api_key,
                "secret": self.api_secret
            }
            
            await self.websocket.send(json.dumps(auth_message))
            
            # Wait for authentication response
            response = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
            auth_data = json.loads(response)
            
            if auth_data.get("T") == "success" and auth_data.get("msg") == "authenticated":
                self.is_authenticated = True
                logger.info("Successfully authenticated with Alpaca stream")
                return True
            else:
                logger.error("Authentication failed", response=auth_data)
                return False
                
        except Exception as e:
            logger.error("Authentication error",
                        error=str(e),
                        error_type=type(e).__name__)
            return False
    
    async def _subscribe_to_trade_updates(self) -> bool:
        """
        Subscribe to trade_updates stream.
        
        Returns:
            bool: True if subscribed successfully, False otherwise
        """
        try:
            subscribe_message = {
                "action": "listen",
                "data": {
                    "streams": ["trade_updates"]
                }
            }
            
            await self.websocket.send(json.dumps(subscribe_message))
            
            # Wait for subscription confirmation
            response = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
            sub_data = json.loads(response)
            
            if sub_data.get("T") == "listening":
                logger.info("Successfully subscribed to trade_updates stream",
                           streams=sub_data.get("data", {}).get("streams", []))
                return True
            else:
                logger.error("Subscription failed", response=sub_data)
                return False
                
        except Exception as e:
            logger.error("Subscription error",
                        error=str(e),
                        error_type=type(e).__name__)
            return False
    
    async def _start_background_tasks(self):
        """Start background tasks for message processing and heartbeat."""
        # Start queue processor
        if not self.queue_processor_task:
            self.queue_processor_task = asyncio.create_task(self._process_update_queue())
        
        # Start heartbeat
        if not self.heartbeat_task:
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    async def _stop_background_tasks(self):
        """Stop background tasks."""
        if self.queue_processor_task:
            self.queue_processor_task.cancel()
            try:
                await self.queue_processor_task
            except asyncio.CancelledError:
                pass
            self.queue_processor_task = None
        
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
            self.heartbeat_task = None
    
    async def listen(self):
        """
        Main listening loop for processing WebSocket messages.
        
        This method handles incoming trade_updates and queues them for processing.
        """
        if not self.is_connected or not self.is_authenticated:
            logger.error("Cannot listen - not connected or authenticated")
            return
        
        try:
            logger.info("Starting to listen for trade updates")
            
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                    
                except json.JSONDecodeError as e:
                    logger.warning("Invalid JSON received", message=message[:200], error=str(e))
                    continue
                    
                except Exception as e:
                    logger.error("Error processing message",
                               message=message[:200],
                               error=str(e),
                               error_type=type(e).__name__)
                    continue
                    
        except ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self.is_connected = False
            self.is_authenticated = False
            
        except WebSocketException as e:
            logger.error("WebSocket error", error=str(e))
            self.is_connected = False
            self.is_authenticated = False
            
        except Exception as e:
            logger.error("Unexpected error in listen loop",
                        error=str(e),
                        error_type=type(e).__name__)
            self.is_connected = False
            self.is_authenticated = False
    
    async def _handle_message(self, data: Dict[str, Any]):
        """
        Handle incoming WebSocket message.
        
        Args:
            data: Parsed message data
        """
        msg_type = data.get("T")
        
        if msg_type == "trade_updates":
            # Queue trade update for processing
            try:
                await asyncio.wait_for(
                    self.update_queue.put(data),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                logger.warning("Update queue full, dropping message", data=data)
                
        elif msg_type == "success":
            logger.debug("Success message received", msg=data.get("msg"))
            
        elif msg_type == "error":
            logger.error("Error message from stream", error=data)
            
        else:
            logger.debug("Unknown message type", msg_type=msg_type, data=data)
    
    async def _process_update_queue(self):
        """
        Process queued trade updates.
        
        This runs in a separate task to handle backpressure and ensure
        database updates don't block the WebSocket message loop.
        """
        logger.info("Starting update queue processor")
        
        while True:
            try:
                # Get update from queue with timeout
                update = await asyncio.wait_for(
                    self.update_queue.get(),
                    timeout=0.5
                )
                
                # Process the update
                await self._process_trade_update(update)
                
            except asyncio.TimeoutError:
                # No update in queue, continue
                continue
                
            except Exception as e:
                logger.error("Error processing trade update",
                           error=str(e),
                           error_type=type(e).__name__)
                continue
    
    async def _process_trade_update(self, update: Dict[str, Any]):
        """
        Process a single trade update and update database.
        
        Args:
            update: Trade update data from Alpaca
        """
        try:
            # Extract order information
            order_data = update.get("data", {})
            if not order_data:
                logger.warning("Empty order data in trade update", update=update)
                return
            
            broker_order_id = order_data.get("id")
            status = order_data.get("status")
            filled_qty = float(order_data.get("filled_qty", 0))
            avg_fill_price = float(order_data.get("avg_fill_price", 0)) if order_data.get("avg_fill_price") else None
            
            if not broker_order_id or not status:
                logger.warning("Missing required fields in trade update",
                             broker_order_id=broker_order_id,
                             status=status,
                             update=update)
                return
            
            # Map Alpaca status to internal status
            internal_status = self._map_alpaca_status(status)
            
            logger.info("Processing trade update",
                       broker_order_id=broker_order_id,
                       alpaca_status=status,
                       internal_status=internal_status,
                       filled_qty=filled_qty,
                       avg_fill_price=avg_fill_price)
            
            # Update database
            async with get_db_session() as session:
                orders_repo = OrdersRepo(session)
                
                # Find order by broker_order_id
                order = await orders_repo.get_by_broker_order_id(broker_order_id)
                if not order:
                    logger.warning("Order not found for broker_order_id",
                                 broker_order_id=broker_order_id)
                    return
                
                # Update order status and fill information
                update_data = {
                    "status": internal_status,
                    "filled_qty": filled_qty,
                    "updated_at": datetime.now(timezone.utc)
                }
                
                if avg_fill_price is not None:
                    update_data["avg_fill_price"] = avg_fill_price
                
                await orders_repo.update(order.id, update_data)
                await session.commit()
                
                logger.info("Order updated in database",
                           order_id=order.id,
                           broker_order_id=broker_order_id,
                           new_status=internal_status,
                           filled_qty=filled_qty)
                
        except Exception as e:
            logger.error("Failed to process trade update",
                        update=update,
                        error=str(e),
                        error_type=type(e).__name__)
    
    def _map_alpaca_status(self, alpaca_status: str) -> str:
        """
        Map Alpaca order status to internal status.
        
        Args:
            alpaca_status: Alpaca order status
            
        Returns:
            Internal order status
        """
        status_mapping = {
            "new": "submitted",
            "accepted": "accepted",
            "partially_filled": "partially_filled",
            "filled": "filled",
            "canceled": "cancelled",
            "expired": "expired",
            "rejected": "rejected",
            "pending_new": "pending",
            "pending_cancel": "pending_cancel",
            "pending_replace": "pending_replace"
        }
        
        return status_mapping.get(alpaca_status.lower(), alpaca_status)
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeat to keep connection alive."""
        while self.is_connected:
            try:
                current_time = time.time()
                
                # Check if we've received any messages recently
                if current_time - self.last_heartbeat > self.heartbeat_interval * 2:
                    logger.warning("No heartbeat received, connection may be stale")
                
                # Send ping
                if self.websocket and not self.websocket.closed:
                    await self.websocket.ping()
                    self.last_heartbeat = current_time
                
                await asyncio.sleep(self.heartbeat_interval)
                
            except Exception as e:
                logger.error("Heartbeat error", error=str(e))
                break
    
    async def _disconnect(self):
        """Disconnect from WebSocket stream."""
        logger.info("Disconnecting from Alpaca stream")
        
        self.is_connected = False
        self.is_authenticated = False
        
        # Stop background tasks
        await self._stop_background_tasks()
        
        # Close WebSocket connection
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.warning("Error closing websocket", error=str(e))
            finally:
                self.websocket = None
    
    async def start_with_reconnect(self):
        """
        Start the stream client with automatic reconnection.
        
        This method will attempt to maintain a connection to the Alpaca stream,
        automatically reconnecting if the connection is lost.
        """
        logger.info("Starting Alpaca stream with reconnect capability")
        
        while self.should_reconnect:
            try:
                # Attempt connection
                if await self.connect():
                    # Reset reconnection delay on successful connect
                    self.reconnect_delay = 1.0
                    self.reconnect_attempts = 0
                    
                    # Listen for messages
                    await self.listen()
                
                # Connection lost, attempt reconnection
                if self.should_reconnect:
                    self.reconnect_attempts += 1
                    
                    if self.reconnect_attempts >= self.max_reconnect_attempts:
                        logger.error("Max reconnection attempts reached, stopping")
                        break
                    
                    logger.info("Attempting reconnection",
                              attempt=self.reconnect_attempts,
                              delay=self.reconnect_delay)
                    
                    await asyncio.sleep(self.reconnect_delay)
                    
                    # Exponential backoff
                    self.reconnect_delay = min(
                        self.reconnect_delay * self.reconnect_multiplier,
                        self.max_reconnect_delay
                    )
            
            except Exception as e:
                logger.error("Unexpected error in stream client",
                           error=str(e),
                           error_type=type(e).__name__)
                
                if self.should_reconnect:
                    await asyncio.sleep(self.reconnect_delay)
                else:
                    break
        
        logger.info("Alpaca stream client stopped")
    
    async def stop(self):
        """Stop the stream client."""
        logger.info("Stopping Alpaca stream client")
        self.should_reconnect = False
        await self._disconnect()


# Global stream client instance
_stream_client: Optional[AlpacaStreamClient] = None


def get_stream_client() -> AlpacaStreamClient:
    """
    Get the global stream client instance.
    
    Returns:
        AlpacaStreamClient: The stream client instance
    """
    global _stream_client
    if _stream_client is None:
        _stream_client = AlpacaStreamClient()
    return _stream_client


async def start_stream_client():
    """Start the global stream client."""
    client = get_stream_client()
    await client.start_with_reconnect()


async def stop_stream_client():
    """Stop the global stream client."""
    global _stream_client
    if _stream_client:
        await _stream_client.stop()
        _stream_client = None