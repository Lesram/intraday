"""
Unified Outbox Background Worker

This module implements an async background worker that processes outbox events
in FIFO order using proper ORM patterns instead of direct SQL connections.

ARCHITECTURAL FIX: Eliminates direct sqlite3.connect() usage that bypassed ORM.
Now uses unified database manager and repository pattern for all database access.
"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import os
import random
import time
from typing import Any

# §2.1 FIX: Use canonical config instead of separate UnifiedSettings
from backend.config.settings import get_settings
from backend.infra.observability import trace_span
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


def serialize_datetime_recursive(obj: Any) -> Any:
    """
    Recursively convert datetime objects to ISO strings for JSON serialization.

    This is critical for DLQ (Dead Letter Queue) payloads that get stored in
    PostgreSQL JSONB columns, which cannot serialize Python datetime objects.

    Args:
        obj: Object to serialize (can be dict, list, datetime, or primitive)

    Returns:
        Serialized object with all datetime objects converted to ISO strings

    Example:
        >>> data = {"timestamp": datetime.now(), "nested": {"date": date.today()}}
        >>> serialize_datetime_recursive(data)
        {"timestamp": "2025-10-09T20:30:45.123456", "nested": {"date": "2025-10-09"}}
    """
    if isinstance(obj, datetime) or isinstance(obj, date):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: serialize_datetime_recursive(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return type(obj)(serialize_datetime_recursive(item) for item in obj)
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj


class OutboxWorker:
    """
    Background worker for processing outbox events.

    Polls outbox_events table for pending events and processes them in FIFO order.
    Supports exponential backoff, jitter, and dead letter queue (DLQ) handling.
    """

    def __init__(
        self,
        sessionmaker,
        poll_interval: float = 0.1,  # L-18: Reduced from 1.0s for HFT latency
        max_retries: int = 5,
        initial_backoff: float = 1.0,
        max_backoff: float = 300.0,
        jitter_factor: float = 0.1
    ):
        """
        Initialize outbox worker.

        Args:
            sessionmaker: Async sessionmaker for database access
            poll_interval: Polling interval in seconds
            max_retries: Maximum retry attempts before DLQ
            initial_backoff: Initial backoff delay in seconds
            max_backoff: Maximum backoff delay in seconds
            jitter_factor: Jitter factor for backoff randomization
        """
        self.sessionmaker = sessionmaker
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.jitter_factor = jitter_factor

        self._running = False
        self._task: asyncio.Task | None = None
        self.settings = get_settings()
        self.use_mock_broker = getattr(self.settings, 'USE_MOCK_BROKER', False)  # Default to FALSE - use real Alpaca
        # NOTE: execution mode is read dynamically per event to allow runtime flips.

        logger.info("OutboxWorker initialized",
                   poll_interval=poll_interval,
                   max_retries=max_retries,
                   use_mock_broker=self.use_mock_broker,
                   trading_execution_mode=getattr(self.settings, "trading_execution_mode", "execute"))

    async def start(self):
        """Start the background worker."""
        if self._running:
            logger.warning("OutboxWorker already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._dispatcher())
        logger.info("OutboxWorker started")

    async def stop(self):
        """Stop the background worker."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # V12 W74 (BB5-F1): also stop the prune task if it is running.
        prune_task = getattr(self, "_prune_task", None)
        if prune_task is not None:
            prune_task.cancel()
            try:
                await prune_task
            except asyncio.CancelledError:
                pass
            self._prune_task = None

        logger.info("OutboxWorker stopped")

    async def prune_old_events(
        self,
        *,
        max_age_days: int = 30,
        statuses: tuple[str, ...] = ("sent", "failed"),
        batch_size: int = 1000,
        now: datetime | None = None,
    ) -> int:
        """V12 W74 (BB5-F1): retention prune for outbox_events.

        External auditor counted 1398 rows spanning 60 days with no
        auto-prune.  Without retention the table grows unbounded —
        partial-failure DLQ rows from a year ago still take up space
        in every query plan.

        Deletes events older than ``max_age_days`` whose status is in
        ``statuses``.  PENDING events are NEVER pruned regardless of
        age — they represent unfinished work.  Returns the count of
        rows pruned.

        Run in batches of ``batch_size`` so a backlog cleanup doesn't
        hold one giant transaction.
        """
        from sqlalchemy import delete, select

        from backend.infra.schemas import OutboxEvent

        cutoff = (now or datetime.now(UTC)) - timedelta(days=max_age_days)
        total_pruned = 0
        while True:
            async with self.sessionmaker() as session:
                # Subquery to grab a batch of IDs to delete (avoids
                # hitting the LIMIT-on-DELETE quirk on Postgres).
                ids_q = (
                    select(OutboxEvent.id)
                    .where(OutboxEvent.status.in_(statuses))
                    .where(OutboxEvent.created_at < cutoff)
                    .limit(batch_size)
                )
                ids_result = await session.execute(ids_q)
                ids = [r[0] for r in ids_result.all()]
                if not ids:
                    break
                await session.execute(
                    delete(OutboxEvent).where(OutboxEvent.id.in_(ids))
                )
                await session.commit()
                total_pruned += len(ids)
                if len(ids) < batch_size:
                    break
        if total_pruned > 0:
            logger.info(
                "BB5-F1 outbox prune: removed %d events older than %d days "
                "(statuses=%s)",
                total_pruned, max_age_days, list(statuses),
            )
        return total_pruned

    async def start_prune_loop(
        self,
        *,
        max_age_days: int = 30,
        interval_seconds: float = 24 * 60 * 60,  # 24h
    ) -> None:
        """V12 W74 (BB5-F1): kick off the periodic prune task.

        Idempotent — calling twice will not start a second loop.  Use
        ``stop()`` to cancel.
        """
        if getattr(self, "_prune_task", None) is not None:
            logger.debug("Outbox prune loop already running")
            return

        async def _loop() -> None:
            while self._running:
                try:
                    await self.prune_old_events(max_age_days=max_age_days)
                except Exception as e:
                    logger.warning("Outbox prune loop error: %s", e)
                # Sleep in 60s slices so cancellation is responsive.
                slept = 0.0
                while self._running and slept < interval_seconds:
                    await asyncio.sleep(min(60.0, interval_seconds - slept))
                    slept += 60.0

        self._prune_task = asyncio.create_task(_loop())
        logger.info(
            "BB5-F1: outbox prune loop started (retention=%dd, interval=%ds)",
            max_age_days, int(interval_seconds),
        )

    async def _dispatcher(self):
        """
        Main dispatcher loop that polls and processes outbox events.
        """
        logger.info("Outbox dispatcher started")

        while self._running:
            try:
                # Poll for pending events
                events = await self._get_pending_events()

                if events:
                    logger.debug(f"Processing {len(events)} outbox events")

                    for event in events:
                        if not self._running:
                            break

                        await self._process_event(event)

                # Wait before next poll
                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                logger.info("Outbox dispatcher cancelled")
                break
            except Exception as e:
                logger.error("Unexpected error in outbox dispatcher",
                           error=str(e),
                           error_type=type(e).__name__,
                           exc_info=True)

                # V6 V-T-4 / Wave-21 (2026-05-03): outbox worker errors
                # were log-only — operators saw no Slack/PagerDuty when
                # the broker submission pipeline broke. Wire a HIGH-
                # severity alert. Worker runs in the main loop so we
                # can use canonical send_alert; still gate on dispatcher
                # for safety.
                try:
                    from backend.infra.alerting import (
                        AlertCategory, AlertSeverity, send_alert,
                        dispatch_alert_from_thread,
                    )
                    _err = e
                    dispatch_alert_from_thread(
                        lambda: send_alert(
                            AlertCategory.SYSTEM_ERROR,
                            AlertSeverity.WARNING,
                            "Outbox Dispatcher Error",
                            f"Outbox loop raised: {_err}",
                            details={"error_type": type(_err).__name__},
                        )
                    )
                except Exception:
                    pass

                # Back off on errors to avoid tight error loops
                await asyncio.sleep(self.poll_interval * 2)

        logger.info("Outbox dispatcher stopped")

    async def _get_pending_events(self) -> list[dict[str, Any]]:
        """
        Get pending outbox events in FIFO order.

        Returns:
            List of pending events, oldest first
        """
        # Create fresh session per iteration with explicit exception handling
        async with self.sessionmaker() as session:
            try:
                from backend.infra.outbox import OutboxRepo
                outbox_repo = OutboxRepo(session)
                events = await outbox_repo.claim_batch(limit=10)

                # Convert OutboxEvent objects to dictionaries
                event_dicts = []
                for event in events:
                    event_dict = {
                        "id": str(event.id),
                        "topic": event.topic,
                        "payload": event.payload,
                        "retry_count": event.attempts,
                        "status": event.status,
                        "created_at": event.created_at,
                        "next_attempt_at": event.next_attempt_at
                    }
                    event_dicts.append(event_dict)

                # Commit the claimed events
                await session.commit()
                return event_dicts
            except Exception as e:
                await session.rollback()
                logger.error("Failed to get pending events",
                            error=str(e),
                            error_type=type(e).__name__)
                return []
            finally:
                await session.close()


    async def _process_event(self, event: dict[str, Any]):
        """
        Process a single outbox event.

        Args:
            event: Outbox event data
        """
        event_id = event.get("id")
        topic = event.get("topic")
        payload = event.get("payload", {})
        retry_count = event.get("retry_count", 0)

        logger.info("Processing outbox event",
                   event_id=event_id,
                   topic=topic,
                   retry_count=retry_count)

        try:
            # Process based on topic
            if topic == "order.submitted":
                result = await self._process_order_submitted(payload)
            else:
                logger.warning(f"Unknown topic: {topic}")
                result = {"success": False, "error": f"Unknown topic: {topic}"}

            if result.get("success", False):
                # Mark event as succeeded
                await self._mark_event_succeeded(event_id, result)
                logger.info("Event processed successfully",
                           event_id=event_id,
                           topic=topic)
            else:
                # Check if this is a validation error that should not be retried
                error_msg = result.get("error", "")
                is_validation_error = (
                    "422:" in error_msg or
                    "not found" in error_msg.lower() or
                    "invalid" in error_msg.lower() or
                    "require" in error_msg.lower() or
                    "validation" in error_msg.lower()
                )

                if is_validation_error:
                    # Don't retry validation errors - move directly to DLQ
                    logger.warning("Validation error detected, moving to DLQ without retry",
                                  event_id=event_id,
                                  error=error_msg)
                    await self._move_to_dlq(event, result)
                else:
                    # Handle failure with retry logic for transient errors
                    await self._handle_event_failure(event, result)

        except Exception as e:
            logger.error("Error processing event",
                        event_id=event_id,
                        topic=topic,
                        error=str(e),
                        error_type=type(e).__name__)

            # Check if this is a validation exception
            error_type = type(e).__name__
            error_str = str(e)
            is_validation_exception = (
                error_type == "ValueError" or
                error_type == "ValidationError" or
                "validation" in error_str.lower() or
                "invalid" in error_str.lower()
            )

            if is_validation_exception:
                # Don't retry validation exceptions
                logger.warning("Validation exception detected, moving to DLQ without retry",
                              event_id=event_id,
                              error=error_str,
                              error_type=error_type)
                await self._move_to_dlq(event, {
                    "success": False,
                    "error": error_str,
                    "error_type": error_type
                })
            else:
                # Handle unexpected errors with retry
                await self._handle_event_failure(event, {
                    "success": False,
                    "error": str(e),
                    "error_type": type(e).__name__
                })

    async def _process_order_submitted(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Process order.submitted event by calling broker.

        Args:
            payload: Order submission payload

        Returns:
            Processing result
        """
        # BUGFIX: Handle nested payload structure
        # If payload has a "payload" key, unwrap it
        if "payload" in payload and isinstance(payload["payload"], dict):
            logger.warning("Detected nested payload structure, unwrapping",
                         original_keys=list(payload.keys()))
            # Merge the nested payload with top-level keys
            nested = payload.pop("payload")
            payload = {**payload, **nested}

        order_id = payload.get("order_id")
        symbol = payload.get("symbol")
        side = payload.get("side")
        qty = payload.get("qty")
        payload.get("order_type", "market")

        logger.info(
            "Processing order submission",
            order_id=order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            use_mock_broker=self.use_mock_broker,
            trading_execution_mode=None,
        )

        try:
            from backend.services.trading_execution_mode import get_trading_execution_mode

            mode_state = get_trading_execution_mode()
            mode = (mode_state.mode or "execute").strip().lower()

            logger.info(
                "Resolved trading execution mode",
                order_id=order_id,
                trading_execution_mode=mode,
                source=mode_state.source,
                overridden=mode_state.overridden,
            )

            with trace_span("order.broker_dispatch", {"order_id": order_id or "", "mode": mode, "symbol": symbol or ""}):
                if mode == "shadow":
                    # Shadow mode: record intent but do not submit to broker.
                    result = {
                        "success": True,
                        "status": "shadow",
                        "execution_mode": "shadow",
                        "broker": "none",
                        "shadow": True,
                        "skipped": True,
                        "order_id": order_id,
                        "symbol": symbol,
                        "side": side,
                        "qty": qty,
                    }
                elif mode == "dry_run":
                    # Dry-run mode: simulate broker behavior (no real submission).
                    result = await self._simulate_broker_order(payload)
                    # Make it explicit this came from dry-run, not the mock broker toggle.
                    result = {**result, "broker": "dry_run", "dry_run": True, "execution_mode": "dry_run"}
                elif self.use_mock_broker:
                    # Simulate broker order submission
                    result = await self._simulate_broker_order(payload)
                else:
                    # Real broker order submission
                    result = await self._submit_real_broker_order(payload)

            # Update order status in database
            if result.get("success", False):
                final_status = result.get("status", "submitted")
                logger.info("About to update order status",
                           order_id=order_id,
                           final_status=final_status,
                           broker_order_id=result.get("broker_order_id"),
                           result_success=result.get("success"))

                with trace_span("order.status_update", {"order_id": order_id or "", "status": final_status}):
                    await self._update_order_status(
                        order_id=order_id,
                        status=final_status,
                        broker_order_id=result.get("broker_order_id"),
                        details=result
                    )

                logger.info("Completed order status update",
                           order_id=order_id,
                           final_status=final_status)
            else:
                logger.warning("Not updating order status - result not successful",
                              order_id=order_id,
                              result=result)

            return result

        except Exception as e:
            logger.error("Order submission failed",
                        order_id=order_id,
                        error=str(e),
                        error_type=type(e).__name__)
            return {
                "success": False,
                "error": str(e),
                "order_id": order_id
            }

    async def _simulate_broker_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Simulate broker order submission for testing / paper-trading only.

        PRODUCTION GUARD: This method must never be invoked when
        ENVIRONMENT=production. If it is, we raise immediately.

        Args:
            payload: Order payload

        Returns:
            Simulated broker result
        """
        env = os.environ.get("ENVIRONMENT", "").lower()
        if env == "production":
            raise RuntimeError(
                "CRITICAL: _simulate_broker_order called in PRODUCTION environment. "
                "This indicates a configuration error — mock broker must never run in production."
            )

        logger.warning(
            "Using simulated broker (paper-trading mode)",
            extra={"order_id": payload.get("order_id"), "environment": env},
        )

        # Simulate processing time
        await asyncio.sleep(0.1)

        order_id = payload.get("order_id")
        symbol = payload.get("symbol")
        order_type = payload.get("order_type", "market")
        qty = payload.get("qty")
        payload.get("side")

        # Generate mock broker order ID
        broker_order_id = f"MOCK_{symbol}_{int(time.time())}"

        # Simulate occasional failures for testing (only when explicitly enabled)
        import os
        mock_failure_rate = float(os.getenv("MOCK_BROKER_FAILURE_RATE", "0"))
        if mock_failure_rate > 0 and random.random() < mock_failure_rate:
            return {
                "success": False,
                "error": "Simulated broker error",
                "order_id": order_id
            }

        logger.info("Mock broker order submitted",
                   order_id=order_id,
                   broker_order_id=broker_order_id,
                   symbol=symbol)

        # In paper trading, market orders are immediately filled
        if order_type.lower() == "market":
            # Simulate immediate fill after brief delay
            await asyncio.sleep(0.2)

            # Mock fill price (use simple simulation)
            base_prices = {"SPY": 400, "AAPL": 150, "TSLA": 200, "MSFT": 300}
            mock_price = base_prices.get(symbol, 100) + random.uniform(-2, 2)

            # Store fill details for the main processing to use
            # Don't update database here - let main processing handle it
            fill_details = {
                "filled_qty": float(qty),
                "avg_fill_price": mock_price,
                "fill_time": time.time(),
                "broker": "mock"
            }

            logger.info("Mock order filled",
                       order_id=order_id,
                       broker_order_id=broker_order_id,
                       symbol=symbol,
                       qty=qty,
                       price=mock_price)

        # Return the result with proper status and fill details
        if order_type.lower() == "market":
            return {
                "success": True,
                "broker_order_id": broker_order_id,
                "status": "filled",
                "broker": "mock",
                **fill_details  # Include fill details
            }
        else:
            return {
                "success": True,
                "broker_order_id": broker_order_id,
                "status": "accepted",
                "broker": "mock"
            }

    async def _submit_real_broker_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Submit order to real broker (Alpaca).

        Args:
            payload: Order payload

        Returns:
            Broker submission result
        """
        try:
            from backend.integrations.alpaca_outbox import handle_order_submitted_event

            # Use the Alpaca outbox handler
            result = await handle_order_submitted_event(payload)
            return result

        except ImportError as e:
            logger.error("Alpaca integration not available",
                        error=str(e))
            return {
                "success": False,
                "error": "Alpaca integration not available",
                "order_id": payload.get("order_id")
            }

    async def _update_order_status(
        self,
        order_id: str,
        status: str,
        broker_order_id: str | None = None,
        details: dict[str, Any] | None = None
    ):
        """
        Update order status using proper ORM repository pattern.

        This replaces the previous direct SQL implementation that bypassed
        the ORM and caused transaction isolation issues.

        Args:
            order_id: Internal order ID
            status: New order status
            broker_order_id: Broker order ID (if available)
            details: Additional status details
        """
        try:
            from decimal import Decimal
            import uuid

            from backend.infra.repositories import OrdersRepo
            from backend.infra.db import get_session_context

            logger.info("Updating order status via ORM repository",
                       order_id=order_id,
                       status=status,
                       broker_order_id=broker_order_id)

            # Use proper async session and repository pattern
            async with get_session_context() as session:
                order_repo = OrdersRepo(session)

                # Parse order ID (handle both UUID formats)
                try:
                    if '-' in order_id:
                        order_uuid = uuid.UUID(order_id)
                    else:
                        # Database format without hyphens
                        formatted_id = f"{order_id[:8]}-{order_id[8:12]}-{order_id[12:16]}-{order_id[16:20]}-{order_id[20:]}"
                        order_uuid = uuid.UUID(formatted_id)
                except (ValueError, IndexError) as e:
                    logger.error(f"Invalid order ID format: {order_id}", error=str(e))
                    raise ValueError(f"Invalid order ID format: {order_id}") from e

                # Get existing order
                order = await order_repo.get_by_id(order_uuid)
                if not order:
                    logger.warning("Order not found for status update",
                                 order_id=order_id,
                                 order_uuid=str(order_uuid))
                    raise ValueError(f"Order not found: {order_id}")

                # Prepare attributes to update
                update_attributes = {}
                filled_qty_value = None
                avg_fill_price_value = None

                if details:
                    # Extract fill details for dedicated columns
                    if 'filled_qty' in details:
                        try:
                            filled_qty_value = Decimal(str(details['filled_qty']))
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid filled_qty value: {details['filled_qty']}")

                    if 'avg_fill_price' in details:
                        try:
                            avg_fill_price_value = Decimal(str(details['avg_fill_price']))
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid avg_fill_price value: {details['avg_fill_price']}")

                    # Store other details in attributes
                    for key, value in details.items():
                        if key not in ['filled_qty', 'avg_fill_price']:
                            update_attributes[key] = str(value)

                # Use attach_broker_result method with new parameters
                await order_repo.attach_broker_result(
                    order_id=order_uuid,
                    broker_order_id=broker_order_id,
                    status=status,
                    filled_qty=filled_qty_value,
                    avg_fill_price=avg_fill_price_value,
                    attributes=update_attributes if update_attributes else None
                )

                await session.commit()

                logger.info("Order status updated successfully via ORM",
                           order_id=order_id,
                           status=status,
                           broker_order_id=broker_order_id)

        except Exception as e:
            logger.error("Failed to update order status via ORM",
                        order_id=order_id,
                        status=status,
                        error=str(e),
                        error_type=type(e).__name__,
                        exc_info=True)
            # Re-raise to ensure failure is propagated
            # This prevents marking events as "sent" when database update fails
            raise

    async def _mark_event_succeeded(self, event_id: str, result: dict[str, Any]):
        """
        Mark outbox event as successfully processed.

        Args:
            event_id: Event ID
            result: Processing result
        """
        import uuid
        event_uuid = uuid.UUID(event_id)

        async with self.sessionmaker() as session:
            try:
                from backend.infra.outbox import OutboxRepo
                outbox_repo = OutboxRepo(session)
                await outbox_repo.mark_sent(event_id=event_uuid)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error("Failed to mark event as succeeded",
                            event_id=event_id,
                            error=str(e))
                raise
            finally:
                await session.close()

    async def _handle_event_failure(self, event: dict[str, Any], error_result: dict[str, Any]):
        """
        Handle event processing failure with retry logic.

        Args:
            event: Failed event
            error_result: Error details
        """
        event_id = event.get("id")
        retry_count = event.get("retry_count", 0)

        if retry_count >= self.max_retries:
            # Move to dead letter queue
            await self._move_to_dlq(event, error_result)
            logger.warning("Event moved to DLQ after max retries",
                          event_id=event_id,
                          retry_count=retry_count,
                          max_retries=self.max_retries)
        else:
            # Schedule retry with exponential backoff
            next_retry = retry_count + 1
            backoff_delay = min(
                self.initial_backoff * (2 ** retry_count),
                self.max_backoff
            )

            # Add jitter to prevent thundering herd
            jitter = backoff_delay * self.jitter_factor * random.random()
            total_delay = backoff_delay + jitter

            next_retry_at = datetime.now(UTC) + timedelta(seconds=total_delay)

            import uuid
            event_uuid = uuid.UUID(event_id)
            error_message = error_result.get("error", "Unknown error")

            async with self.sessionmaker() as session:
                try:
                    from backend.infra.outbox import OutboxRepo
                    outbox_repo = OutboxRepo(session)
                    await outbox_repo.mark_retry(
                        event_id=event_uuid,
                        attempts=next_retry,
                        next_attempt_at=next_retry_at,
                        error_message=error_message
                    )
                    await session.commit()

                    logger.info("Event scheduled for retry",
                               event_id=event_id,
                               retry_count=next_retry,
                               backoff_delay=backoff_delay,
                               next_retry_at=next_retry_at.isoformat())
                except Exception as e:
                    await session.rollback()
                    logger.error("Failed to schedule retry",
                                event_id=event_id,
                                error=str(e))
                    raise
                finally:
                    await session.close()

    async def _move_to_dlq(self, event: dict[str, Any], error_result: dict[str, Any]):
        """
        Move event to dead letter queue.

        Args:
            event: Failed event
            error_result: Final error details
        """
        event_id = event.get("id")

        try:
            import uuid
            event_uuid = uuid.UUID(event_id)
            error_message = error_result.get("error", "Max retries exceeded")
            attempts = event.get("retry_count", 0)

            async with self.sessionmaker() as session:
                try:
                    from backend.infra.outbox import OutboxRepo
                    outbox_repo = OutboxRepo(session)
                    await outbox_repo.mark_failed(
                        event_id=event_uuid,
                        attempts=attempts,
                        error_message=error_message
                    )

                    # Log DLQ details for manual inspection — do NOT re-enqueue
                    # into the same outbox table (that would create an infinite loop)
                    dlq_payload_raw = {
                        "original_event": event,
                        "final_error": error_result,
                        "failed_at": datetime.now(UTC).isoformat(),
                        "retry_count": attempts
                    }

                    # Apply recursive datetime serialization
                    dlq_payload = serialize_datetime_recursive(dlq_payload_raw)

                    logger.warning("Event moved to DLQ (marked as failed)",
                               event_id=event_id,
                               attempts=attempts,
                               error=error_message[:200],
                               dlq_payload=dlq_payload)

                    await session.commit()

                    # §4.4 FIX: Notify connected clients via WebSocket about broker rejection
                    try:
                        from backend.websocket import broadcaster
                        if broadcaster:
                            payload = event.get("payload", {})
                            await broadcaster.broadcast_to_topic("orders", {
                                "type": "order.rejected",
                                "order_id": payload.get("order_id", event_id),
                                "symbol": payload.get("symbol"),
                                "reason": error_message[:500],
                                "event_id": event_id,
                            })
                    except Exception as ws_err:
                        logger.debug(f"WebSocket notification failed (non-critical): {ws_err}")
                except Exception as e:
                    await session.rollback()
                    logger.error("Failed to move event to DLQ",
                                event_id=event_id,
                                error=str(e))
                    raise
                finally:
                    await session.close()

        except Exception as e:
            logger.error("Failed to move event to DLQ",
                        event_id=event_id,
                        error=str(e))


# Global worker instance
_outbox_worker: OutboxWorker | None = None


async def create_outbox_worker(sessionmaker) -> OutboxWorker:
    """
    Create and configure outbox worker.

    Args:
        sessionmaker: Async sessionmaker for database access

    Returns:
        Configured OutboxWorker instance
    """
    global _outbox_worker

    if _outbox_worker is not None:
        logger.warning("OutboxWorker already exists, stopping previous instance")
        await _outbox_worker.stop()

    try:
        poll_interval = float(os.environ.get("OUTBOX_POLL_INTERVAL", "0.1"))
    except (ValueError, TypeError):
        logger.warning("Invalid OUTBOX_POLL_INTERVAL value, using default 0.1s")
        poll_interval = 0.1

    _outbox_worker = OutboxWorker(
        sessionmaker=sessionmaker,
        poll_interval=poll_interval,  # 100ms default for HFT
        max_retries=5,      # Max 5 retries before DLQ
        initial_backoff=1.0, # Start with 1 second backoff
        max_backoff=300.0,   # Max 5 minute backoff
        jitter_factor=0.1    # 10% jitter
    )

    return _outbox_worker


async def start_outbox_worker(sessionmaker) -> OutboxWorker:
    """
    Create and start outbox worker.

    Args:
        sessionmaker: Async sessionmaker for database access

    Returns:
        Started OutboxWorker instance
    """
    worker = await create_outbox_worker(sessionmaker)
    await worker.start()
    return worker


async def stop_outbox_worker():
    """Stop the global outbox worker."""
    global _outbox_worker

    if _outbox_worker:
        await _outbox_worker.stop()
        _outbox_worker = None


def get_outbox_worker() -> OutboxWorker | None:
    """Get the global outbox worker instance."""
    return _outbox_worker
