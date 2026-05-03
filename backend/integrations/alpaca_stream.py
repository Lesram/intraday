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
from datetime import UTC, datetime
import json
import os
import time
from pathlib import Path
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from backend.config import get_settings
from backend.infra.db import get_session_context
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
        # §12.8 FIX: Accept both ALPACA_API_KEY_ID and ALPACA_API_KEY for compatibility
        self.api_key = os.getenv("ALPACA_API_KEY_ID") or os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
        self.api_secret = os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
        self.is_paper = os.getenv("ALPACA_PAPER", "true").lower() in ("true", "1", "yes")

        # WebSocket URL
        if self.is_paper:
            self.ws_url = os.getenv("ALPACA_STREAM_URL", "wss://paper-api.alpaca.markets/stream")
        else:
            self.ws_url = os.getenv("ALPACA_STREAM_URL", "wss://api.alpaca.markets/stream")

        # Connection management
        self.websocket: websockets.WebSocketClientProtocol | None = None
        self.is_connected = False
        self.is_authenticated = False
        self.should_reconnect = True

        # Reconnection configuration
        self.reconnect_delay = 1.0
        self.max_reconnect_delay = 60.0
        self.reconnect_multiplier = 2.0
        self.max_reconnect_attempts = 10
        self.reconnect_attempts = 0

        # Update queue for backpressure handling.
        # UNBOUNDED for trade updates — we must NEVER drop fill/cancel/reject
        # messages as that causes state divergence and missed exits.
        # Non-critical messages (heartbeats, etc.) are not queued.
        self.update_queue: asyncio.Queue = asyncio.Queue()
        self.queue_processor_task = None
        self._queue_high_water_mark = 0
        self._queue_overflow_count = 0

        # REMEDIATION: Track order IDs that reached terminal state
        # (rejected/cancelled/expired) so the engine can clear pending entries early.
        self._terminal_order_ids: set[str] = set()

        # B1: Dead-letter queue for permanently failed trade updates
        self._dlq_path = Path(os.getenv("INTRA_DLQ_PATH", "/tmp/intra_trade_update_dlq.jsonl"))
        self._dlq_count: int = 0

        # B2: Track connection timestamps and reconnect count for gap-fill
        self._last_connected_at: float = 0.0
        self._reconnect_count: int = 0

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
            self._last_connected_at = time.time()

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

            # Handle both old and new Alpaca API response formats
            # Old format: {"T": "success", "msg": "authenticated"}
            # New format: {"stream": "authorization", "data": {"action": "authenticate", "status": "authorized"}}
            is_authenticated = False

            if auth_data.get("T") == "success" and auth_data.get("msg") == "authenticated":
                # Old API format
                is_authenticated = True
            elif (auth_data.get("stream") == "authorization" and
                  auth_data.get("data", {}).get("status") == "authorized"):
                # New API format
                is_authenticated = True

            if is_authenticated:
                self.is_authenticated = True
                logger.info("Successfully authenticated with Alpaca stream",
                           response_format="new_api" if "stream" in auth_data else "old_api")
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

            # Handle both old and new Alpaca API response formats
            # Old format: {"T": "listening", "data": {"streams": ["trade_updates"]}}
            # New format: {"stream": "listening", "data": {"streams": ["trade_updates"]}}
            is_subscribed = False

            if sub_data.get("T") == "listening":
                # Old API format
                is_subscribed = True
            elif sub_data.get("stream") == "listening":
                # New API format
                is_subscribed = True

            if is_subscribed:
                logger.info("Successfully subscribed to trade_updates stream",
                           streams=sub_data.get("data", {}).get("streams", []),
                           response_format="new_api" if "stream" in sub_data else "old_api")
                return True
            else:
                logger.error("Subscription failed - unexpected response format", response=sub_data)
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

    async def _handle_message(self, data: dict[str, Any]):
        """
        Handle incoming WebSocket message.

        Args:
            data: Parsed message data
        """
        # Handle both old and new Alpaca API message formats
        # Old format: {"T": "trade_updates", ...}
        # New format: {"stream": "trade_updates", ...}
        msg_type = data.get("T") or data.get("stream")

        if msg_type == "trade_updates":
            # Queue trade update for processing.
            # The queue is unbounded — trade updates must NEVER be dropped
            # because missed fills/cancels/rejects cause state divergence.
            await self.update_queue.put(data)
            qsize = self.update_queue.qsize()
            self._queue_high_water_mark = max(self._queue_high_water_mark, qsize)
            if qsize > 500:
                self._queue_overflow_count += 1
                logger.warning(
                    "Trade update queue depth high: %d (hwm=%d, overflow_events=%d)",
                    qsize, self._queue_high_water_mark, self._queue_overflow_count,
                )
            logger.info("Queued trade update for processing",
                       order_id=data.get("data", {}).get("id"),
                       status=data.get("data", {}).get("status"))

        elif msg_type == "success":
            logger.debug("Success message received", msg=data.get("msg"))

        elif msg_type == "error":
            logger.error("Error message from stream", error=data)

        else:
            logger.debug("Unknown message type", msg_type=msg_type, data=data)

    async def _process_update_queue(self):
        """
        Process queued trade updates with retry on failure.

        This runs in a separate task to handle backpressure and ensure
        database updates don't block the WebSocket message loop.
        EXEC-001 FIX: Retries failed updates up to 3 times with backoff.
        """
        logger.info("Starting update queue processor")
        MAX_RETRIES = 3

        while True:
            try:
                # Get update from queue with timeout
                update = await asyncio.wait_for(
                    self.update_queue.get(),
                    timeout=0.5
                )

                # EXEC-001: Retry loop for transient failures
                last_error = None
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        await self._process_trade_update(update)
                        last_error = None
                        break
                    except Exception as e:
                        last_error = e
                        if attempt < MAX_RETRIES:
                            backoff = 0.5 * (2 ** (attempt - 1))  # 0.5s, 1s
                            logger.warning(
                                "Trade update processing failed (attempt %d/%d), retrying in %.1fs",
                                attempt, MAX_RETRIES, backoff,
                                error=str(e),
                                error_type=type(e).__name__,
                            )
                            await asyncio.sleep(backoff)

                if last_error is not None:
                    logger.error(
                        "Trade update PERMANENTLY FAILED after %d attempts — writing to DLQ",
                        MAX_RETRIES,
                        error=str(last_error),
                        error_type=type(last_error).__name__,
                        update_summary=str(update)[:200],
                    )
                    # B1: Write to dead-letter queue file
                    self._write_to_dlq(update, MAX_RETRIES, last_error)

            except TimeoutError:
                # No update in queue, continue
                continue

            except Exception as e:
                logger.error("Unexpected error in update queue processor",
                           error=str(e),
                           error_type=type(e).__name__)
                continue

    def _write_to_dlq(self, update: dict[str, Any], attempts: int, error: Exception) -> None:
        """B1: Append a permanently failed trade update to the dead-letter queue file."""
        try:
            dlq_record = {
                "timestamp": datetime.now(UTC).isoformat(),
                "attempt_count": attempts,
                "error": str(error),
                "error_type": type(error).__name__,
                "update": update,
            }
            with open(self._dlq_path, "a") as f:
                f.write(json.dumps(dlq_record, default=str) + "\n")
            self._dlq_count += 1
            logger.warning(
                "Trade update written to DLQ (total=%d): %s",
                self._dlq_count,
                self._dlq_path,
            )
        except Exception as dlq_err:
            logger.error("Failed to write to DLQ file: %s", dlq_err)

    async def _process_trade_update(self, update: dict[str, Any]):
        """
        Process a single trade update and update database.

        Args:
            update: Trade update data from Alpaca
        """
        try:
            # Extract order information
            # Alpaca v2 format: {"data": {"event": "fill", "order": {"id": ..., "status": ...}}}
            event_data = update.get("data", {})
            if not event_data:
                logger.warning("Empty order data in trade update", update=update)
                return

            # Order fields are nested under the "order" key
            order_data = event_data.get("order", event_data)

            broker_order_id = order_data.get("id")
            client_order_id = order_data.get("client_order_id")
            status = order_data.get("status")
            # V7 FF-3 / Wave-25 (2026-05-03): the previous
            # `float(order_data.get("filled_qty", 0))` raised TypeError
            # when the broker sent JSON `null` for filled_qty (Python
            # `None`). The outer `except Exception` swallowed the
            # message → state divergence (DB never learns about the
            # update). Coerce explicitly: None / "" / missing → 0.
            _raw_qty = order_data.get("filled_qty")
            if _raw_qty is None or _raw_qty == "":
                filled_qty = 0.0
            else:
                try:
                    filled_qty = float(_raw_qty)
                except (TypeError, ValueError):
                    logger.warning(
                        "FF-3: malformed filled_qty in trade update — "
                        "defaulting to 0; raw=%r broker_oid=%s",
                        _raw_qty, broker_order_id,
                    )
                    filled_qty = 0.0
            _raw_price = order_data.get("filled_avg_price") or order_data.get("avg_fill_price")
            try:
                avg_fill_price = float(_raw_price or 0) or None
            except (TypeError, ValueError):
                avg_fill_price = None

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
                       client_order_id=client_order_id,
                       alpaca_status=status,
                       internal_status=internal_status,
                       filled_qty=filled_qty,
                       avg_fill_price=avg_fill_price)

            # Update database
            async with get_session_context() as session:
                orders_repo = OrdersRepo(session)

                # Find order by broker_order_id, with fallback to client_order_id.
                # The outbox worker may not have written broker_order_id to DB yet
                # (race condition), but client_idempotency_key is written *before*
                # the order is sent to Alpaca, so it's always available.
                order = await orders_repo.get_by_broker_order_id(broker_order_id)
                if not order and client_order_id:
                    order = await orders_repo.get_by_client_key(client_order_id)
                    if order:
                        # Backfill broker_order_id so future lookups succeed
                        await orders_repo.attach_broker_result(
                            order.id, broker_order_id=broker_order_id
                        )
                        logger.info(
                            "Order matched via client_order_id fallback, backfilled broker_order_id",
                            order_id=order.id,
                            broker_order_id=broker_order_id,
                            client_order_id=client_order_id,
                        )
                if not order:
                    logger.warning("Order not found for broker_order_id or client_order_id",
                                 broker_order_id=broker_order_id,
                                 client_order_id=client_order_id)
                    return

                # V9 DD3-2 / Wave-43 (2026-05-03): capture previous cumulative
                # filled_qty BEFORE updating, so the LotTracker block below
                # can compute the INCREMENTAL fill (filled_qty is cumulative
                # in Alpaca's semantics; calling create_lot with the cumulative
                # value on every partially_filled event creates duplicate
                # position_lots rows).
                _prev_filled_qty_raw = getattr(order, "filled_qty", None) or 0
                try:
                    _prev_filled_qty = float(_prev_filled_qty_raw)
                except (TypeError, ValueError):
                    _prev_filled_qty = 0.0

                # Update order status and fill information
                from decimal import Decimal
                await orders_repo.attach_broker_result(
                    order.id,
                    status=internal_status,
                    filled_qty=Decimal(str(filled_qty)) if filled_qty else None,
                    avg_fill_price=Decimal(str(avg_fill_price)) if avg_fill_price else None,
                )
                await session.commit()

                logger.info("Order updated in database",
                           order_id=order.id,
                           broker_order_id=broker_order_id,
                           new_status=internal_status,
                           filled_qty=filled_qty)

                # V8 BB-8 / Wave-30 (2026-05-03): wire LotTracker on the
                # live stream path. V7 Track BB found that
                # `LotTracker.create_lot` was only called from
                # `alpaca_stream_production.py` (not loaded in lifespan);
                # `position_lots` and `realized_trades` were 0 rows
                # despite 1,369 orders. Mirror the production-stream
                # logic here so cost basis and realized P&L tables
                # populate from the live path.
                if (
                    internal_status in ("filled", "partially_filled")
                    and filled_qty
                    and avg_fill_price
                    and getattr(order, "symbol", None)
                    and getattr(order, "side", None)
                ):
                    try:
                        from backend.services.lot_tracker_service import LotTracker
                        _lot_tracker = LotTracker(session)
                        _user_id = (
                            (order.attributes or {}).get("user_id")
                            if hasattr(order, "attributes") and order.attributes
                            else None
                        ) or getattr(order, "user_id", None) or "system"
                        # V9 DD3-2 / Wave-43 (2026-05-03): use INCREMENTAL
                        # qty (filled_qty is cumulative in Alpaca's
                        # semantics).  Previously each partially_filled
                        # event called create_lot with the cumulative
                        # value, producing duplicate rows on multi-event
                        # fills.  If the increment is <= 0 (duplicate
                        # event or stale data), skip the lot op entirely.
                        _filled_now_f = float(filled_qty)
                        _incremental = _filled_now_f - _prev_filled_qty
                        _qty_dec = Decimal(str(_incremental))
                        _price_dec = Decimal(str(avg_fill_price))
                        _open_dt = (
                            getattr(order, "filled_at", None)
                            or getattr(order, "submitted_at", None)
                            or datetime.now(UTC)
                        )

                        if _incremental <= 0:
                            # V9 DD3-2: duplicate or stale event; skip
                            # the lot op but continue with the rest of
                            # _process_trade_update (terminal-id tracking).
                            logger.debug(
                                "DD3-2: skipping LotTracker op for order=%s "
                                "(incremental_qty=%.4f cum=%.4f prev=%.4f)",
                                order.id, _incremental, _filled_now_f,
                                _prev_filled_qty,
                            )
                        elif order.side == "buy":
                            await _lot_tracker.create_lot(
                                user_id=_user_id,
                                symbol=order.symbol,
                                qty=_qty_dec,
                                cost_basis=_price_dec,
                                order_id=order.id,
                                open_date=_open_dt,
                            )
                            logger.info(
                                "BB-8 / DD3-2: created position lot for buy "
                                "fill: %s %s @ $%s order=%s "
                                "(incremental; cum=%s prev=%s)",
                                _qty_dec, order.symbol, _price_dec,
                                order.id, _filled_now_f, _prev_filled_qty,
                            )
                            await session.commit()
                        elif order.side == "sell":
                            realized = await _lot_tracker.close_lots_fifo(
                                user_id=_user_id,
                                symbol=order.symbol,
                                qty_to_close=_qty_dec,
                                close_price=_price_dec,
                                close_order_id=order.id,
                                close_date=_open_dt,
                            )
                            _total_pnl = sum(t.realized_pnl for t in realized)
                            logger.info(
                                "BB-8 / DD3-2: closed %d lot(s) for sell "
                                "fill: %s %s @ $%s pnl=$%s "
                                "(incremental; cum=%s prev=%s)",
                                len(realized), _qty_dec, order.symbol,
                                _price_dec, _total_pnl,
                                _filled_now_f, _prev_filled_qty,
                            )
                            await session.commit()
                            # V10 YY-2 / Wave-52 (2026-05-03): emit
                            # ORDER_FILLED audit row.  Previously the
                            # audit_logs table only had user.login rows
                            # — every order/position lifecycle event was
                            # silent despite the helper being live.  We
                            # write directly through the live session
                            # already in scope (no sessionmaker dance).
                            try:
                                from backend.services.audit_service import (
                                    AuditAction, AuditEntity,
                                    ComplianceAuditService,
                                )
                                _audit = ComplianceAuditService(session)
                                await _audit.log(
                                    action=AuditAction.ORDER_FILLED,
                                    entity=AuditEntity.ORDER,
                                    entity_id=str(order.id),
                                    actor="system:alpaca_stream",
                                    payload={
                                        "symbol": order.symbol,
                                        "side": order.side,
                                        "qty": float(_incremental),
                                        "price": float(_price_dec),
                                        "status": internal_status,
                                        "broker_order_id": broker_order_id,
                                    },
                                )
                                await session.commit()
                            except Exception as _audit_err:
                                logger.debug(
                                    "YY-2: ORDER_FILLED audit dispatch "
                                    "skipped: %s", _audit_err,
                                )
                    except Exception as _lot_err:
                        # Don't fail order processing on lot-tracking error.
                        logger.warning(
                            "BB-8: lot-tracking failed for order %s: %s",
                            order.id, _lot_err,
                            exc_info=True,
                        )
                        # V10 UU2-C / Wave-51 (2026-05-03): same pattern as
                        # wave-41 UU-2 / wave-51 UU2-A.  Surface rollback
                        # failure so a poisoned session doesn't silently
                        # propagate to the next order event.
                        try:
                            await session.rollback()
                        except Exception as _rb_err:
                            logger.error(
                                "UU2-C: db.rollback() after LotTracker "
                                "failure also failed for order %s: %s — "
                                "session may be poisoned",
                                order.id, _rb_err,
                            )

                # REMEDIATION: Track terminal order statuses for early pending-entry cleanup.
                # V4 H-1 / Wave-16d (2026-05-02): record BOTH the broker
                # `order_data["id"]` AND the internal DB UUID
                # `str(order.id)`. The previous code only stored the
                # broker id, but live_engine._pending_entry_order_ids[sym]
                # tracks the internal DB UUID — `is_order_terminal(uuid)`
                # therefore never matched, and the early-clear path was
                # dead. Symbols stayed locked for the full 30-tick
                # cooldown after every reject. With both ids in the
                # set, `is_order_terminal()` answers correctly regardless
                # of which id the caller has. The cap doubles to 2000-keep-1000
                # to preserve the previous effective horizon (~500 orders).
                if internal_status in ("rejected", "cancelled", "expired"):
                    broker_oid = order_data.get("id", "")
                    if broker_oid:
                        self._terminal_order_ids.add(broker_oid)
                    try:
                        # `order.id` is the internal DB UUID. Store as
                        # str so set lookups by either form match.
                        if order is not None and getattr(order, "id", None):
                            self._terminal_order_ids.add(str(order.id))
                    except Exception:
                        # Defensive: never let a tracking failure break
                        # the WS handler.
                        pass
                    # Cap set size to prevent unbounded growth.
                    if len(self._terminal_order_ids) > 2000:
                        self._terminal_order_ids = set(
                            list(self._terminal_order_ids)[-1000:]
                        )

                # ✅ FIX: Broadcast order update to frontend via WebSocket
                try:
                    import os

                    from backend.api.socketio_server import broadcast_order_update

                    # Get user_id - try order.user_id first, then DEFAULT_USER_ID from env
                    user_id = getattr(order, 'user_id', None) or os.getenv('DEFAULT_USER_ID', 'demo')

                    logger.info(f"🔔 Preparing to broadcast order update for user_id: '{user_id}'",
                               order_id=order.id,
                               status=internal_status)

                    # Prepare order data for broadcast
                    order_data = {
                        'order_id': str(order.id),
                        'broker_order_id': broker_order_id,
                        'symbol': order.symbol,
                        'side': order.side,
                        'qty': float(order.qty),
                        'filled_qty': filled_qty,
                        'avg_fill_price': avg_fill_price,
                        'status': internal_status,
                        'order_type': order.order_type,
                        'submitted_at': order.submitted_at.isoformat() if order.submitted_at else None,
                        'updated_at': datetime.now(UTC).isoformat()
                    }

                    # Broadcast to user's WebSocket clients
                    await broadcast_order_update(user_id, order_data)

                    logger.info(f"✅ Broadcasted order update to user {user_id} via WebSocket",
                               order_id=order.id,
                               status=internal_status)

                except Exception as broadcast_error:
                    # Don't fail order update if broadcast fails
                    logger.warning(f"⚠️ Failed to broadcast order update (order still updated in DB): {broadcast_error}")

        except Exception as e:
            logger.error("Failed to process trade update",
                        update=update,
                        error=str(e),
                        error_type=type(e).__name__)

    def is_order_terminal(self, order_id: str) -> bool:
        """Check if an order reached terminal state (rejected/cancelled/expired).

        Accepts EITHER the broker `order_id` (Alpaca's id) or the internal
        DB UUID (`Order.id`). V4 H-1 / Wave-16d (2026-05-02): the
        `_on_trade_update` recorder pushes both forms into
        `_terminal_order_ids` so this lookup answers correctly regardless
        of which form the caller has — `live_engine` carries the internal
        UUID; broker / API consumers carry the broker id. Parameter
        renamed from `broker_order_id` to `order_id` to reflect the
        unified semantics.
        """
        return order_id in self._terminal_order_ids

    async def _gap_fill_after_reconnect(self) -> None:
        """EXEC-002: Poll recent orders for missed fills after WebSocket reconnect.

        B2: Uses actual gap duration (time since last connection) instead of
        a fixed 5-minute window. Minimum 5 minutes, capped at 1 hour.
        """
        try:
            from datetime import timedelta

            # B2: Compute actual gap duration
            if self._last_connected_at > 0:
                gap_seconds = time.time() - self._last_connected_at
            else:
                gap_seconds = 300  # Default 5 minutes if no prior connection

            # Minimum 5 min, extend to cover gap + 1 min buffer, cap at 1 hour
            lookback_seconds = min(max(gap_seconds + 60, 300), 3600)

            logger.info(
                "EXEC-002 gap-fill: gap_duration=%.0fs, lookback_window=%.0fs",
                gap_seconds, lookback_seconds,
            )

            cutoff = datetime.now(UTC) - timedelta(seconds=lookback_seconds)
            async with get_session_context() as session:
                orders_repo = OrdersRepo(session)
                # Fetch orders that may have changed during the gap
                recent_orders = await orders_repo.get_orders_since(cutoff)
                if not recent_orders:
                    logger.info("EXEC-002 gap-fill: no recent orders to reconcile")
                    return

                reconciled = 0
                for order in recent_orders:
                    if not order.broker_order_id:
                        continue
                    try:
                        # Query broker for current status
                        import httpx
                        base_url = "https://paper-api.alpaca.markets" if self.is_paper else "https://api.alpaca.markets"
                        async with httpx.AsyncClient() as client:
                            resp = await client.get(
                                f"{base_url}/v2/orders/{order.broker_order_id}",
                                headers={
                                    "APCA-API-KEY-ID": self.api_key,
                                    "APCA-API-SECRET-KEY": self.api_secret,
                                },
                                timeout=10.0,
                            )
                            if resp.status_code == 200:
                                broker_data = resp.json()
                                broker_status = self._map_alpaca_status(broker_data.get("status", ""))
                                current_db_status = order.status
                                if broker_status != current_db_status:
                                    filled_qty = float(broker_data.get("filled_qty", 0))
                                    avg_price = float(broker_data.get("filled_avg_price", 0) or 0) or None
                                    from decimal import Decimal
                                    await orders_repo.attach_broker_result(
                                        order.id,
                                        status=broker_status,
                                        filled_qty=Decimal(str(filled_qty)) if filled_qty else None,
                                        avg_fill_price=Decimal(str(avg_price)) if avg_price else None,
                                    )
                                    await session.commit()
                                    reconciled += 1
                                    logger.warning(
                                        "EXEC-002 gap-fill: reconciled order %s: %s -> %s",
                                        order.broker_order_id, current_db_status, broker_status,
                                    )

                                    # V5 S-WS-GAP-1 / Wave-17c (2026-05-03):
                                    # the steady-state path
                                    # (`_on_trade_update`) records terminal
                                    # ids into `_terminal_order_ids` so
                                    # live_engine's early-clear path can
                                    # un-stick rejected symbols. Across a
                                    # WS gap, that path doesn't fire — the
                                    # terminal status was discovered by
                                    # gap-fill REST polling instead. We
                                    # must re-populate `_terminal_order_ids`
                                    # here too, otherwise wave-16d's
                                    # H-1 unification holds in-process but
                                    # regresses across every WS reconnect:
                                    # the symbol stays locked for the full
                                    # 30-tick TTL after a gap-window reject.
                                    if broker_status in (
                                        "rejected", "cancelled", "expired"
                                    ):
                                        broker_oid = order.broker_order_id
                                        if broker_oid:
                                            self._terminal_order_ids.add(broker_oid)
                                        try:
                                            if order.id is not None:
                                                self._terminal_order_ids.add(str(order.id))
                                        except Exception:
                                            pass
                                        if len(self._terminal_order_ids) > 2000:
                                            self._terminal_order_ids = set(
                                                list(self._terminal_order_ids)[-1000:]
                                            )
                    except Exception as e:
                        logger.warning("EXEC-002 gap-fill: failed to reconcile order %s: %s",
                                      order.broker_order_id, e)
                        continue

                logger.info("EXEC-002 gap-fill complete: %d orders reconciled out of %d checked",
                           reconciled, len(recent_orders))

        except Exception as e:
            logger.error("EXEC-002 gap-fill failed (non-fatal): %s", e)

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

                # Send ping if connection is active
                if self.websocket and self.is_connected:
                    try:
                        await self.websocket.ping()
                        self.last_heartbeat = current_time
                    except Exception as ping_error:
                        logger.warning("Ping failed, connection may be closed", error=str(ping_error))
                        break

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
                    # P&L-033: Reset slow-retry counter on successful connection
                    self._slow_retry_cycles = 0

                    # EXEC-002: Gap-fill after reconnect — check for missed fills
                    await self._gap_fill_after_reconnect()

                    # Listen for messages
                    await self.listen()

                # Connection lost, attempt reconnection
                if self.should_reconnect:
                    self.reconnect_attempts += 1

                    # B2: Track total reconnect count across the session
                    self._reconnect_count += 1
                    if self._reconnect_count > 10:
                        logger.critical(
                            "Stream instability: %d reconnects this session — "
                            "order update reliability degraded",
                            self._reconnect_count,
                        )

                    if self.reconnect_attempts >= self.max_reconnect_attempts:
                        logger.error("Max reconnection attempts reached, entering cooldown before retry cycle")
                        # H-09 FIX: Emit critical alert when max reconnects reached
                        await self._emit_max_reconnect_alert()
                        # P&L-033: Slow-retry mode — after exhausting fast retries,
                        # switch to progressively longer cooldowns (5m → 10m → 20m,
                        # capped at 30m).  This avoids hammering a flaky endpoint
                        # while still eventually recovering.
                        slow_cycles = getattr(self, "_slow_retry_cycles", 0)
                        slow_delay = min(1800, 300 * (2 ** slow_cycles))  # 5m, 10m, 20m, 30m
                        self._slow_retry_cycles = slow_cycles + 1
                        logger.info(
                            "Slow-retry cooldown activated",
                            extra={"delay_s": slow_delay, "cycle": self._slow_retry_cycles},
                        )
                        await asyncio.sleep(slow_delay)
                        self.reconnect_attempts = 0
                        self.reconnect_delay = 1.0
                        logger.info("Cooldown complete, restarting reconnection cycle")
                        continue

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

    async def _emit_max_reconnect_alert(self) -> None:
        """
        H-09 FIX: Emit critical alert when max WebSocket reconnection attempts reached.
        
        This indicates potential order update loss and requires immediate attention.
        """
        try:
            # V4 P-P0-4 (2026-05-02): the previous code imported
            # `emit_alert` from backend.monitoring.slo_monitor and
            # `increment_counter` from backend.observability.metrics —
            # neither symbol exists. Both `except ImportError: pass`
            # branches always fired, dropping the alert and skipping
            # the metric on every WS max-reconnect event. Use the
            # canonical send_alert API; metric becomes a Prometheus
            # Counter declared on the global REGISTRY (visible at
            # /metrics post wave-12e).
            try:
                from backend.infra.alerting import (
                    AlertCategory, AlertSeverity, send_alert,
                )
                await send_alert(
                    AlertCategory.CONNECTIVITY,
                    AlertSeverity.CRITICAL,
                    "Alpaca WebSocket Max Reconnects Reached",
                    (
                        f"WebSocket connection to Alpaca failed after {self.max_reconnect_attempts} "
                        "reconnection attempts. Order updates may be lost. "
                        "Manual intervention required."
                    ),
                    details={
                        "attempts": self.reconnect_attempts,
                        "max_attempts": self.max_reconnect_attempts,
                        "last_reconnect_delay": self.reconnect_delay,
                        "is_paper": self.is_paper,
                    },
                )
            except Exception as _alert_err:
                logger.warning(
                    "WS max-reconnect alert dispatch failed: %s",
                    _alert_err,
                )

            try:
                from prometheus_client import Counter
                global _WS_MAX_RECONNECT_COUNTER
                try:
                    _WS_MAX_RECONNECT_COUNTER  # type: ignore[name-defined]
                except NameError:
                    _WS_MAX_RECONNECT_COUNTER = Counter(
                        "websocket_max_reconnects_total",
                        "Total times the Alpaca WS gave up after max reconnects",
                        ["stream_type", "is_paper"],
                    )
                _WS_MAX_RECONNECT_COUNTER.labels(
                    stream_type="alpaca_trades",
                    is_paper=str(self.is_paper),
                ).inc()
            except Exception:
                pass
            
            # Log at critical level for log-based alerting
            logger.critical(
                "ALERT: Alpaca WebSocket max reconnects reached - order updates may be lost",
                extra={
                    "alert_type": "WebSocketMaxReconnects",
                    "severity": "critical",
                    "attempts": self.reconnect_attempts,
                    "max_attempts": self.max_reconnect_attempts,
                    "is_paper": self.is_paper,
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to emit max reconnect alert: {e}")

    async def stop(self):
        """Stop the stream client."""
        logger.info("Stopping Alpaca stream client")
        self.should_reconnect = False
        await self._disconnect()


# Global stream client instance
_stream_client: AlpacaStreamClient | None = None


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
