"""Production WebSocket stream client with gap-filling and robustness

Enhanced features:
1. Persistent last_event_ts to track message gaps
2. Gap-fill via REST API when reconnecting
3. Event deduplication using order_events table
4. Jittered exponential backoff for reconnections
5. Comprehensive error classification and circuit breaker integration
"""
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import logging
import random
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
import websockets
from websockets.exceptions import ConnectionClosed, InvalidURI

from backend.database.models_production import OrderEvent
from backend.infra.db import get_db_session
from backend.infra.guardrails_production import TransactionalGuardrails
from backend.infra.repositories.orders import OrdersRepo
from backend.integrations.alpaca_broker import AlpacaBrokerClient
from backend.monitoring.slo_monitor import slo_monitor
from backend.services.lot_tracker_service import LotTracker

logger = logging.getLogger(__name__)


class StreamState:
    """Persistent stream state for gap detection and recovery"""

    def __init__(self):
        self.last_event_ts: datetime | None = None
        self.connection_count = 0
        self.total_messages_processed = 0
        self.last_heartbeat: datetime | None = None

    async def load_from_db(self) -> None:
        """Load last processed event timestamp from database"""
        async for session in get_db_session():
            # Get the most recent event timestamp
            query = select(OrderEvent.event_time).order_by(OrderEvent.event_time.desc()).limit(1)
            result = await session.execute(query)
            last_event = result.scalar_one_or_none()

            if last_event:
                self.last_event_ts = last_event
                logger.info(f"Loaded last event timestamp: {self.last_event_ts}")
            else:
                # Start from 1 hour ago if no events exist
                self.last_event_ts = datetime.now(UTC) - timedelta(hours=1)
                logger.info(f"No previous events found, starting from: {self.last_event_ts}")

    async def update_last_event(self, event_time: datetime) -> None:
        """Update last processed event timestamp"""
        if not self.last_event_ts or event_time > self.last_event_ts:
            self.last_event_ts = event_time
            self.total_messages_processed += 1


class RobustAlpacaStream:
    """Production-grade WebSocket client with gap-filling and resilience"""

    def __init__(self,
                 api_key: str,
                 api_secret: str,
                 base_url: str = "wss://stream.data.alpaca.markets/v2/sip",
                 paper: bool = True):

        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.paper = paper

        self.websocket: websockets.WebSocketClientProtocol | None = None
        self.is_running = False
        self.should_stop = False

        # Reconnection parameters with jittered exponential backoff
        self.min_backoff = 1.0      # Start with 1 second
        self.max_backoff = 300.0    # Cap at 5 minutes
        self.backoff_multiplier = 1.5
        self.jitter_factor = 0.1    # ±10% jitter
        self.current_backoff = self.min_backoff

        # Dependencies — defer OrdersRepo creation until we have a session
        self.orders_repo: OrdersRepo | None = None
        self.alpaca_client = AlpacaBrokerClient(api_key, api_secret, paper=paper)
        self.stream_state = StreamState()
        self.guardrails: TransactionalGuardrails | None = None

        # Connection tracking
        self.connect_time: datetime | None = None
        self.reconnect_count = 0

    async def start(self, guardrails: TransactionalGuardrails | None = None) -> None:
        """Start the WebSocket client with gap-filling"""
        self.guardrails = guardrails
        self.should_stop = False

        # Load previous state
        await self.stream_state.load_from_db()

        # Fill any gaps since last connection
        await self._fill_gaps()

        # Start main connection loop
        await self._connection_loop()

    async def stop(self) -> None:
        """Gracefully stop the WebSocket client"""
        logger.info("Stopping Alpaca WebSocket stream...")
        self.should_stop = True

        if self.websocket:
            await self.websocket.close()

        self.is_running = False

    async def _connection_loop(self) -> None:
        """Main connection loop with automatic reconnection"""
        while not self.should_stop:
            try:
                await self._connect_and_listen()

            except Exception as e:
                await self._handle_connection_error(e)

                if not self.should_stop:
                    # Apply jittered exponential backoff
                    jitter = random.uniform(-self.jitter_factor, self.jitter_factor)
                    delay = self.current_backoff * (1 + jitter)

                    logger.warning(f"Reconnecting in {delay:.1f}s (attempt #{self.reconnect_count + 1})")
                    await asyncio.sleep(delay)

                    # Increase backoff for next attempt
                    self.current_backoff = min(
                        self.current_backoff * self.backoff_multiplier,
                        self.max_backoff
                    )

                    self.reconnect_count += 1

    async def _connect_and_listen(self) -> None:
        """Establish WebSocket connection and listen for messages"""
        logger.info(f"Connecting to Alpaca stream: {self.base_url}")

        # Reset backoff on successful connection
        self.current_backoff = self.min_backoff
        self.connect_time = datetime.now(UTC)

        async with websockets.connect(
            self.base_url,
            extra_headers={"Authorization": f"Bearer {self.api_key}"}
        ) as websocket:

            self.websocket = websocket
            self.is_running = True

            # Record successful connection
            slo_monitor.record_stream_reconnect("successful_connect")
            self.stream_state.connection_count += 1

            logger.info(f"WebSocket connected (connection #{self.stream_state.connection_count})")

            # Subscribe to trade updates
            await self._subscribe_to_trade_updates()

            # Listen for messages
            async for message in websocket:
                if self.should_stop:
                    break

                await self._process_message(message)

    async def _subscribe_to_trade_updates(self) -> None:
        """Subscribe to trade update messages"""
        auth_message = {
            "action": "auth",
            "key": self.api_key,
            "secret": self.api_secret
        }

        await self.websocket.send(json.dumps(auth_message))
        logger.debug("Sent authentication message")

        # Subscribe to trade updates
        subscribe_message = {
            "action": "listen",
            "data": {
                "streams": ["trade_updates"]
            }
        }

        await self.websocket.send(json.dumps(subscribe_message))
        logger.info("Subscribed to trade updates")

    async def _process_message(self, raw_message: str) -> None:
        """Process incoming WebSocket message with deduplication"""
        try:
            message = json.loads(raw_message)
            message_type = message.get("stream", "unknown")

            # Record message for monitoring
            slo_monitor.record_stream_message(message_type)

            # Update heartbeat
            self.stream_state.last_heartbeat = datetime.now(UTC)

            if message_type == "trade_updates":
                await self._process_trade_update(message["data"])
            elif message_type == "authorization":
                logger.info(f"Authorization status: {message.get('data', {}).get('status', 'unknown')}")
            elif message_type == "listening":
                logger.info(f"Listening to streams: {message.get('data', {}).get('streams', [])}")
            else:
                logger.debug(f"Received {message_type} message: {message}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode WebSocket message: {e}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")

    async def _process_trade_update(self, trade_data: dict[str, Any]) -> None:
        """Process trade update with database persistence and deduplication"""
        try:
            broker_order_id = trade_data.get("order", {}).get("id")
            event_type = trade_data.get("event")  # fill, partial_fill, canceled, etc.

            if not broker_order_id or not event_type:
                logger.warning(f"Invalid trade update: missing order ID or event type: {trade_data}")
                return

            # Parse event timestamp
            event_time_str = trade_data.get("timestamp")
            if event_time_str:
                # Alpaca timestamps are usually in RFC3339 format
                event_time = datetime.fromisoformat(event_time_str.replace('Z', '+00:00'))
            else:
                event_time = datetime.now(UTC)

            # Record message lag for monitoring
            broker_timestamp = event_time
            slo_monitor.record_stream_message("trade_update", broker_timestamp)

            # Find the order in our database
            async for session in get_db_session():
                order = await self.orders_repo.get_by_broker_order_id(session, broker_order_id)

                if not order:
                    logger.warning(f"Received trade update for unknown order: {broker_order_id}")
                    return

                # Record event with deduplication via guardrails
                if self.guardrails:
                    event_recorded = await self.guardrails.record_trade_event(
                        order_id=str(order.id),
                        broker_order_id=broker_order_id,
                        event_type=event_type,
                        event_time=event_time,
                        event_data=trade_data
                    )

                    if not event_recorded:
                        # Duplicate event - skip processing
                        return

                # Update order status based on event
                await self._update_order_from_trade_event(session, order, trade_data)

                # ✅ FIX: Broadcast order update to frontend via WebSocket
                try:
                    import os

                    from backend.api.socketio_server import broadcast_order_update

                    # Get user_id from order or use default from environment
                    user_id = getattr(order, 'user_id', None) or os.getenv('DEFAULT_USER_ID', 'demo')

                    # Prepare order data for broadcast
                    order_data = {
                        'order_id': str(order.id),
                        'broker_order_id': broker_order_id,
                        'symbol': order.symbol,
                        'side': order.side,
                        'qty': float(order.qty),
                        'filled_qty': float(order.filled_qty) if order.filled_qty else 0.0,
                        'avg_fill_price': float(getattr(order, 'filled_price', None) or getattr(order, 'avg_fill_price', None) or 0),
                        'status': order.status,
                        'order_type': order.order_type,
                        'submitted_at': order.submitted_at.isoformat() if order.submitted_at else None,
                        'updated_at': datetime.now(UTC).isoformat()
                    }

                    # Broadcast to user's WebSocket clients
                    await broadcast_order_update(user_id, order_data)

                    logger.info(f"✅ Broadcasted order update to user {user_id}",
                               order_id=order.id,
                               status=order.status,
                               event_type=event_type)

                except Exception as broadcast_error:
                    # Don't fail order update if broadcast fails
                    logger.warning(f"⚠️ Failed to broadcast order update: {broadcast_error}")

                # Update stream state
                await self.stream_state.update_last_event(event_time)

                logger.info(f"Processed {event_type} event for order {broker_order_id}")

        except Exception as e:
            logger.error(f"Error processing trade update: {e}")
            if self.guardrails:
                # This might indicate a broker error or data format issue
                self.guardrails.record_broker_error(Exception(f"Stream processing error: {e}"))

    async def _update_order_from_trade_event(self, session: Session, order: Any, trade_data: dict[str, Any]) -> None:
        """Update order status based on trade event and track position lots"""
        event_type = trade_data.get("event")

        # Initialize LotTracker for cost basis tracking
        lot_tracker = LotTracker(session)

        if event_type == "fill":
            order.status = "filled"
            order.filled_at = datetime.now(UTC)

            # Update filled quantity and average price if available
            filled_qty = trade_data.get("qty")
            filled_price = trade_data.get("price")

            if filled_qty:
                order.filled_qty = float(filled_qty)
            if filled_price:
                order.filled_price = float(filled_price)

            # Track position lots for cost basis
            if filled_qty and filled_price and hasattr(order, 'symbol') and hasattr(order, 'side'):
                try:
                    qty_decimal = Decimal(str(filled_qty))
                    price_decimal = Decimal(str(filled_price))

                    # Get user_id from order attributes or default to 'admin'
                    user_id = order.attributes.get('user_id', 'admin') if hasattr(order, 'attributes') else 'admin'

                    if order.side == "buy":
                        # Create lot on buy order fill
                        await lot_tracker.create_lot(
                            user_id=user_id,
                            symbol=order.symbol,
                            qty=qty_decimal,
                            cost_basis=price_decimal,
                            order_id=order.id,
                            open_date=order.filled_at or datetime.now(UTC)
                        )
                        logger.info(f"Created position lot for buy order {order.id}: {filled_qty} {order.symbol} @ ${filled_price}")

                    elif order.side == "sell":
                        # Close lots on sell order fill (FIFO)
                        realized_trades = await lot_tracker.close_lots_fifo(
                            user_id=user_id,
                            symbol=order.symbol,
                            qty_to_close=qty_decimal,
                            close_price=price_decimal,
                            close_order_id=order.id,
                            close_date=order.filled_at or datetime.now(UTC)
                        )
                        total_pnl = sum(t.realized_pnl for t in realized_trades)
                        logger.info(
                            f"Closed {len(realized_trades)} lot(s) for sell order {order.id}: "
                            f"{filled_qty} {order.symbol} @ ${filled_price}, realized P&L: ${total_pnl}"
                        )

                except Exception as e:
                    # Log error but don't fail order processing
                    logger.error(f"Error tracking position lot for order {order.id}: {e}", exc_info=True)

        elif event_type == "partial_fill":
            order.status = "partially_filled"

            # Accumulate partial fills
            filled_qty = trade_data.get("qty", 0)
            filled_price = trade_data.get("price")

            previous_filled_qty = order.filled_qty or 0
            order.filled_qty = previous_filled_qty + float(filled_qty)

            # Track position lots for partial fills
            if filled_qty and filled_price and hasattr(order, 'symbol') and hasattr(order, 'side'):
                try:
                    qty_decimal = Decimal(str(filled_qty))
                    price_decimal = Decimal(str(filled_price))
                    user_id = order.attributes.get('user_id', 'admin') if hasattr(order, 'attributes') else 'admin'

                    if order.side == "buy":
                        # Create lot for partial buy fill
                        await lot_tracker.create_lot(
                            user_id=user_id,
                            symbol=order.symbol,
                            qty=qty_decimal,
                            cost_basis=price_decimal,
                            order_id=order.id,
                            open_date=datetime.now(UTC)
                        )
                        logger.info(f"Created lot for partial buy fill: {filled_qty} {order.symbol} @ ${filled_price}")

                    elif order.side == "sell":
                        # Close lots for partial sell fill (FIFO)
                        realized_trades = await lot_tracker.close_lots_fifo(
                            user_id=user_id,
                            symbol=order.symbol,
                            qty_to_close=qty_decimal,
                            close_price=price_decimal,
                            close_order_id=order.id,
                            close_date=datetime.now(UTC)
                        )
                        total_pnl = sum(t.realized_pnl for t in realized_trades)
                        logger.info(
                            f"Closed {len(realized_trades)} lot(s) for partial sell fill: "
                            f"{filled_qty} {order.symbol} @ ${filled_price}, realized P&L: ${total_pnl}"
                        )

                except Exception as e:
                    logger.error(f"Error tracking lot for partial fill {order.id}: {e}", exc_info=True)

        elif event_type in ["canceled", "cancelled"]:
            order.status = "canceled"
            order.canceled_at = datetime.now(UTC)

        elif event_type == "rejected":
            order.status = "rejected"
            order.error_message = trade_data.get("reason", "Order rejected by broker")

        await session.commit()

    async def _fill_gaps(self) -> None:
        """Fill gaps in trade updates using REST API"""
        if not self.stream_state.last_event_ts:
            logger.info("No previous events to gap-fill from")
            return

        try:
            logger.info(f"Filling gaps since {self.stream_state.last_event_ts}")

            # Get all orders created since last event
            async for session in get_db_session():
                query = select(self.orders_repo.model).where(
                    self.orders_repo.model.created_at >= self.stream_state.last_event_ts
                ).order_by(self.orders_repo.model.created_at)

                result = await session.execute(query)
                orders_to_check = result.scalars().all()

                logger.info(f"Found {len(orders_to_check)} orders to check for gap-fill")

                # Check each order's current status via REST API
                for order in orders_to_check:
                    if order.broker_order_id:
                        await self._gap_fill_single_order(session, order)

                        # Rate limit the API calls
                        await asyncio.sleep(0.1)  # 10 requests/second

        except Exception as e:
            logger.error(f"Error during gap-fill: {e}")

    async def _gap_fill_single_order(self, session: Session, order: Any) -> None:
        """Gap-fill a single order using REST API"""
        try:
            # Get current order status from broker
            broker_order = await self.alpaca_client.get_order(order.broker_order_id)

            if not broker_order:
                return

            # Compare with our database status
            broker_status = broker_order.get("status", "").lower()
            our_status = order.status.lower()

            if broker_status != our_status:
                logger.info(f"Gap-fill update: Order {order.broker_order_id} {our_status} -> {broker_status}")

                # Update order status
                order.status = broker_status

                # Update filled information if available
                if broker_status in ["filled", "partially_filled"]:
                    filled_qty = broker_order.get("filled_qty")
                    filled_avg_price = broker_order.get("filled_avg_price")

                    if filled_qty:
                        order.filled_qty = float(filled_qty)
                    if filled_avg_price:
                        order.filled_price = float(filled_avg_price)

                    if broker_status == "filled":
                        order.filled_at = datetime.now(UTC)

                await session.commit()

                # Record synthetic trade event for consistency
                if self.guardrails:
                    await self.guardrails.record_trade_event(
                        order_id=str(order.id),
                        broker_order_id=order.broker_order_id,
                        event_type=f"gap_fill_{broker_status}",
                        event_time=datetime.now(UTC),
                        event_data={
                            "gap_fill": True,
                            "broker_order": broker_order
                        }
                    )

        except Exception as e:
            logger.error(f"Error gap-filling order {order.broker_order_id}: {e}")

    async def _handle_connection_error(self, error: Exception) -> None:
        """Handle WebSocket connection errors with classification"""
        self.is_running = False

        # Classify error for circuit breaker
        if isinstance(error, ConnectionClosed):
            reason = "connection_closed"
        elif isinstance(error, InvalidURI):
            reason = "invalid_uri"
        elif isinstance(error, asyncio.TimeoutError):
            reason = "timeout"
        else:
            reason = "unknown_error"

        # Record reconnection for monitoring
        slo_monitor.record_stream_reconnect(reason)

        # Notify guardrails of potential broker connectivity issue
        if self.guardrails and reason in ["connection_closed", "timeout"]:
            self.guardrails.record_broker_error(Exception(f"Stream connection error: {reason}"))

        logger.error(f"WebSocket connection error ({reason}): {error}")

    def get_status(self) -> dict[str, Any]:
        """Get stream client status for monitoring"""
        uptime = None
        if self.connect_time:
            uptime = (datetime.now(UTC) - self.connect_time).total_seconds()

        return {
            "is_running": self.is_running,
            "should_stop": self.should_stop,
            "connection_count": self.stream_state.connection_count,
            "reconnect_count": self.reconnect_count,
            "total_messages_processed": self.stream_state.total_messages_processed,
            "current_backoff": self.current_backoff,
            "uptime_seconds": uptime,
            "last_event_ts": self.stream_state.last_event_ts.isoformat() if self.stream_state.last_event_ts else None,
            "last_heartbeat": self.stream_state.last_heartbeat.isoformat() if self.stream_state.last_heartbeat else None
        }
