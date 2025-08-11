"""
Outbox pattern implementation for exactly-once side-effects.
Provides transactional outbox with exponential backoff and comprehensive observability.
Enhanced with OpenTelemetry tracing, structured logging, and Prometheus metrics.
"""
import asyncio
from datetime import datetime, timedelta
import logging
import random
import time
from typing import Any
import uuid

from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.infra.logging import get_logger as get_structured_logger

# B2.5 - Observability imports
from backend.infra.observability import record_database_operation, record_outbox_metrics, trace_span

from ..config import get_settings
from .schemas import OutboxEvent

logger = logging.getLogger(__name__)

# Prometheus metrics
outbox_polled_total = Counter("outbox_polled_total", "Total outbox polling operations")

outbox_dispatched_total = Counter(
    "outbox_dispatched_total", "Total outbox dispatching operations", ["topic", "status"]
)

outbox_dispatch_latency_seconds = Histogram(
    "outbox_dispatch_latency_seconds",
    "Outbox dispatch latency",
    ["topic"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

outbox_queue_gauge = Gauge("outbox_queue_gauge", "Current outbox queue size", ["status"])

broker_submit_total = Counter("broker_submit_total", "Total broker submissions", ["result"])

broker_submit_latency_seconds = Histogram(
    "broker_submit_latency_seconds",
    "Broker submission latency",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)


class OutboxRepo:
    """Repository for outbox event operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def enqueue(
        self, *, topic: str, payload: dict[str, Any], session: AsyncSession | None = None
    ) -> uuid.UUID:
        """
        Enqueue an outbox event for processing.

        Args:
            topic: Event topic for routing
            payload: Event payload data
            session: Optional session (uses self.session if not provided)

        Returns:
            UUID of the created outbox event
        """
        session = session or self.session

        event = OutboxEvent(
            topic=topic,
            payload=payload,
            status="pending",
            attempts=0,
            next_attempt_at=datetime.utcnow(),
        )

        session.add(event)
        await session.flush()  # Get the ID

        logger.info(
            "Outbox event enqueued",
            extra={
                "outbox_id": str(event.id),
                "topic": topic,
                "payload_keys": list(payload.keys()),
            },
        )

        return event.id

    async def claim_batch(
        self, *, limit: int = 100, session: AsyncSession | None = None
    ) -> list[OutboxEvent]:
        """
        Claim a batch of pending events for processing.
        Uses FOR UPDATE SKIP LOCKED for concurrency safety.

        Args:
            limit: Maximum number of events to claim
            session: Optional session

        Returns:
            List of claimed outbox events
        """
        session = session or self.session

        # Query with FOR UPDATE SKIP LOCKED for concurrency safety
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status == "pending", OutboxEvent.next_attempt_at <= datetime.utcnow()
            )
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        result = await session.execute(stmt)
        events = list(result.scalars().all())

        logger.debug("Outbox batch claimed", extra={"batch_size": len(events), "limit": limit})

        return events

    async def mark_sent(self, event_id: uuid.UUID, *, session: AsyncSession | None = None) -> None:
        """Mark an event as successfully sent."""
        session = session or self.session

        stmt = (
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(status="sent", sent_at=datetime.utcnow(), last_error=None)
        )

        await session.execute(stmt)

        logger.info("Outbox event marked as sent", extra={"outbox_id": str(event_id)})

    async def mark_retry(
        self,
        event_id: uuid.UUID,
        *,
        attempts: int,
        next_attempt_at: datetime,
        error_message: str | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        """Mark an event for retry with backoff."""
        session = session or self.session

        stmt = (
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(attempts=attempts, next_attempt_at=next_attempt_at, last_error=error_message)
        )

        await session.execute(stmt)

        logger.warning(
            "Outbox event scheduled for retry",
            extra={
                "outbox_id": str(event_id),
                "attempts": attempts,
                "next_attempt_at": next_attempt_at.isoformat(),
                "error": error_message,
            },
        )

    async def mark_failed(
        self,
        event_id: uuid.UUID,
        *,
        attempts: int,
        error_message: str | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        """Mark an event as permanently failed."""
        session = session or self.session

        stmt = (
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(status="failed", attempts=attempts, last_error=error_message)
        )

        await session.execute(stmt)

        logger.error(
            "Outbox event permanently failed",
            extra={"outbox_id": str(event_id), "attempts": attempts, "error": error_message},
        )

    async def get_queue_stats(self) -> dict[str, int]:
        """Get current queue statistics."""
        # Count by status
        pending_stmt = select(OutboxEvent).where(OutboxEvent.status == "pending")
        sent_stmt = select(OutboxEvent).where(OutboxEvent.status == "sent")
        failed_stmt = select(OutboxEvent).where(OutboxEvent.status == "failed")

        pending_result = await self.session.execute(pending_stmt)
        sent_result = await self.session.execute(sent_stmt)
        failed_result = await self.session.execute(failed_stmt)

        stats = {
            "pending": len(list(pending_result.scalars().all())),
            "sent": len(list(sent_result.scalars().all())),
            "failed": len(list(failed_result.scalars().all())),
        }

        # Update Prometheus gauge
        for status, count in stats.items():
            outbox_queue_gauge.labels(status=status).set(count)

        return stats


class BackoffCalculator:
    """Calculates exponential backoff with jitter."""

    def __init__(self, base_delay_ms: int = 200, max_delay_ms: int = 10000, jitter_ms: int = 150):
        self.base_delay_ms = base_delay_ms
        self.max_delay_ms = max_delay_ms
        self.jitter_ms = jitter_ms

    def calculate_delay(self, attempts: int) -> int:
        """
        Calculate delay in milliseconds for given attempt number.

        Args:
            attempts: Number of attempts (1-based)

        Returns:
            Delay in milliseconds
        """
        if attempts <= 0:
            return self.base_delay_ms

        # Exponential backoff: base * 2^(attempts-1)
        exponential_delay = self.base_delay_ms * (2 ** (attempts - 1))

        # Cap at max delay
        delay = min(exponential_delay, self.max_delay_ms)

        # Add jitter to avoid thundering herd
        jitter = random.uniform(0, self.jitter_ms)

        return int(delay + jitter)

    def next_attempt_time(self, attempts: int) -> datetime:
        """Calculate next attempt timestamp."""
        delay_ms = self.calculate_delay(attempts)
        return datetime.utcnow() + timedelta(milliseconds=delay_ms)


class OutboxDispatcher:
    """Background dispatcher for outbox events."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        alpaca_client,  # Will be properly typed when we update alpaca_client
        settings=None,
    ):
        self.sessionmaker = sessionmaker
        self.alpaca_client = alpaca_client
        self.settings = settings or get_settings()
        self.backoff_calculator = BackoffCalculator(
            base_delay_ms=self.settings.outbox.base_delay_ms,
            max_delay_ms=self.settings.outbox.max_delay_ms,
            jitter_ms=self.settings.outbox.jitter_ms,
        )

        # Concurrency control
        self._dispatch_semaphore = asyncio.Semaphore(8)  # Max 8 concurrent dispatches
        self._running = False

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        """
        Main dispatcher loop with comprehensive observability.

        Args:
            stop_event: Event to signal shutdown
        """
        self._running = True
        structured_logger = get_structured_logger(__name__)

        logger.info(
            "Outbox dispatcher starting",
            extra={
                "poll_interval_ms": self.settings.outbox.poll_interval_ms,
                "batch_size": self.settings.outbox.batch_size,
                "max_attempts": self.settings.outbox.max_attempts,
            },
        )

        with trace_span(
            "outbox_dispatcher_lifecycle",
            {
                "outbox.operation": "run_forever",
                "outbox.poll_interval_ms": self.settings.outbox.poll_interval_ms,
                "outbox.batch_size": self.settings.outbox.batch_size,
            },
        ) as lifecycle_span:
            try:
                batch_count = 0
                total_events_processed = 0

                while not stop_event.is_set():
                    try:
                        batch_start_time = time.time()

                        # Process batch with tracing
                        with trace_span(
                            "outbox_process_batch",
                            {
                                "outbox.batch_number": batch_count,
                                "outbox.batch_size_limit": self.settings.outbox.batch_size,
                            },
                        ) as batch_span:
                            events_processed = await self._process_batch()

                            # Update span with batch results
                            batch_span.set_attribute("outbox.events_processed", events_processed)
                            batch_span.set_attribute(
                                "outbox.batch_duration_seconds", time.time() - batch_start_time
                            )

                            # Record outbox metrics
                            if events_processed > 0:
                                record_outbox_metrics(
                                    polled_count=1,  # One polling operation
                                    dispatched_count=events_processed,
                                    failed_count=0,  # Will be updated in _dispatch_event if failures occur
                                    queue_size=0,  # Will be updated with actual queue size
                                    dispatch_duration_seconds=time.time() - batch_start_time,
                                )

                                # Log structured outbox event
                                structured_logger.log_outbox_event(
                                    event="batch_processed",
                                    message_id=f"batch_{batch_count}",
                                    topic="orders",
                                )

                            total_events_processed += events_processed

                        outbox_polled_total.inc()
                        batch_count += 1

                        # Wait for next poll interval
                        poll_interval_sec = self.settings.outbox.poll_interval_ms / 1000
                        await asyncio.wait_for(stop_event.wait(), timeout=poll_interval_sec)

                    except TimeoutError:
                        # Expected timeout for polling interval
                        continue
                    except Exception as e:
                        # Update lifecycle span with error
                        lifecycle_span.set_attribute("error", True)
                        lifecycle_span.set_attribute("error.type", type(e).__name__)
                        lifecycle_span.set_attribute("error.message", str(e))

                        # Log structured error
                        structured_logger.log_outbox_event(
                            event="dispatcher_error",
                            message_id=f"batch_{batch_count}",
                            topic="orders",
                            error=str(e),
                        )

                        logger.error(
                            "Error in outbox dispatcher loop",
                            extra={
                                "error": str(e),
                                "error_type": type(e).__name__,
                                "batch_count": batch_count,
                                "total_events_processed": total_events_processed,
                            },
                            exc_info=True,
                        )

                        # Short delay before retrying to avoid tight loop
                        await asyncio.sleep(1.0)

                # Update final lifecycle metrics
                lifecycle_span.set_attribute("outbox.total_batches", batch_count)
                lifecycle_span.set_attribute(
                    "outbox.total_events_processed", total_events_processed
                )

            finally:
                self._running = False

                # Log final dispatcher statistics
                structured_logger.info(
                    "Outbox dispatcher stopped",
                    {
                        "total_batches": batch_count,
                        "total_events_processed": total_events_processed,
                    },
                )

                logger.info("Outbox dispatcher stopped")

    async def _process_batch(self) -> int:
        """
        Process a batch of outbox events with comprehensive observability.

        Returns:
            Number of events processed
        """
        async with self.sessionmaker() as session:
            try:
                repo = OutboxRepo(session)

                # Claim batch with database operation tracing
                start_time = time.time()
                events = await repo.claim_batch(
                    limit=self.settings.outbox.batch_size, session=session
                )

                # Record database operation metrics
                record_database_operation(
                    operation="select", duration_seconds=time.time() - start_time, success=True
                )

                if not events:
                    return 0

                logger.debug(f"Processing outbox batch of {len(events)} events")

                # Update queue size metrics
                stats = await repo.get_queue_stats()
                outbox_queue_gauge.labels(status="pending").set(stats.get("pending", 0))
                outbox_queue_gauge.labels(status="retry").set(stats.get("retry", 0))

                # Process events concurrently with semaphore
                dispatch_tasks = [
                    self._dispatch_event_with_semaphore(event, session) for event in events
                ]

                await asyncio.gather(*dispatch_tasks, return_exceptions=True)
                await session.commit()

                return len(events)

            except Exception as e:
                logger.error(
                    "Error processing outbox batch",
                    extra={"error": str(e), "error_type": type(e).__name__},
                    exc_info=True,
                )
                await session.rollback()
                return 0

            except Exception as e:
                await session.rollback()
                logger.error(
                    "Error processing outbox batch",
                    extra={"error": str(e), "error_type": type(e).__name__},
                    exc_info=True,
                )

    async def _dispatch_event_with_semaphore(
        self, event: OutboxEvent, session: AsyncSession
    ) -> None:
        """Dispatch event with concurrency control."""
        async with self._dispatch_semaphore:
            await self._dispatch_event(event, session)

    async def _dispatch_event(self, event: OutboxEvent, session: AsyncSession) -> None:
        """
        Dispatch a single outbox event with comprehensive observability.

        Args:
            event: Outbox event to dispatch
            session: Database session
        """
        start_time = time.time()
        repo = OutboxRepo(session)
        structured_logger = get_structured_logger(__name__)

        with trace_span(
            "outbox_dispatch_event",
            {
                "outbox.event_id": str(event.id),
                "outbox.topic": event.topic,
                "outbox.attempt": event.attempts + 1,
                "outbox.max_attempts": self.settings.outbox.max_attempts,
            },
        ) as span:
            try:
                # Route by topic with tracing
                if event.topic == "order_submitted":
                    await self._handle_order_submitted(event)
                else:
                    raise ValueError(f"Unknown outbox topic: {event.topic}")

                # Mark as sent
                db_start_time = time.time()
                await repo.mark_sent(event.id, session=session)
                db_duration = time.time() - db_start_time

                # Record database operation
                record_database_operation(
                    operation="update", duration_seconds=db_duration, success=True
                )

                # Update span with success info
                span.set_attribute("outbox.status", "sent")
                span.set_attribute("outbox.dispatch_duration_seconds", time.time() - start_time)

                outbox_dispatched_total.labels(topic=event.topic, status="success").inc()

                # Record dispatch latency
                dispatch_duration = time.time() - start_time
                outbox_dispatch_latency_seconds.labels(topic=event.topic).observe(dispatch_duration)

                # Log structured success event
                structured_logger.log_outbox_event(
                    event="message_dispatched",
                    message_id=str(event.id),
                    topic=event.topic,
                    attempt=event.attempts + 1,
                )

                logger.info(
                    "Outbox event dispatched successfully",
                    extra={
                        "outbox_id": str(event.id),
                        "topic": event.topic,
                        "attempts": event.attempts + 1,
                        "dispatch_duration_ms": dispatch_duration * 1000,
                    },
                )

            except Exception as e:
                # Update span with error info
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))

                # Increment attempts
                new_attempts = event.attempts + 1

                if new_attempts >= self.settings.outbox.max_attempts:
                    # Mark as permanently failed
                    db_start_time = time.time()
                    await repo.mark_failed(
                        event.id, attempts=new_attempts, error_message=str(e), session=session
                    )
                    db_duration = time.time() - db_start_time

                    record_database_operation(
                        operation="update", duration_seconds=db_duration, success=True
                    )

                    span.set_attribute("outbox.status", "failed")
                    span.set_attribute("outbox.final_attempt", True)

                    outbox_dispatched_total.labels(topic=event.topic, status="failed").inc()

                    # Log structured failure event
                    structured_logger.log_outbox_event(
                        event="message_failed",
                        message_id=str(event.id),
                        topic=event.topic,
                        attempt=new_attempts,
                        max_attempts=self.settings.outbox.max_attempts,
                        error=str(e),
                    )

                else:
                    # Schedule retry with backoff
                    next_attempt = self.backoff_calculator.next_attempt_time(new_attempts)

                    db_start_time = time.time()
                    await repo.mark_retry(
                        event.id,
                        attempts=new_attempts,
                        next_attempt_at=next_attempt,
                        error_message=str(e),
                        session=session,
                    )
                    db_duration = time.time() - db_start_time

                    record_database_operation(
                        operation="update", duration_seconds=db_duration, success=True
                    )

                    span.set_attribute("outbox.status", "retry")
                    span.set_attribute("outbox.next_retry", next_attempt.isoformat())

                    outbox_dispatched_total.labels(topic=event.topic, status="retry").inc()

                    # Log structured retry event
                    structured_logger.log_outbox_event(
                        event="message_retry_scheduled",
                        message_id=str(event.id),
                        topic=event.topic,
                        attempt=new_attempts,
                        max_attempts=self.settings.outbox.max_attempts,
                        next_retry=next_attempt,
                        error=str(e),
                    )

    async def _handle_order_submitted(self, event: OutboxEvent) -> None:
        """Handle order_submitted events."""
        payload = event.payload

        # Extract order details from payload
        order_id = payload.get("order_id")
        client_idempotency_key = payload.get("client_idempotency_key")
        symbol = payload.get("symbol")
        side = payload.get("side")
        qty = payload.get("qty")
        order_type = payload.get("order_type", "market")
        tif = payload.get("tif", "gtc")

        if not all([order_id, client_idempotency_key, symbol, side, qty]):
            raise ValueError("Missing required order fields in payload")

        # Prepare headers with idempotency key
        headers = {self.settings.outbox.broker_idempotency_header: client_idempotency_key}

        # Submit to broker
        start_time = asyncio.get_event_loop().time()

        try:
            # Submit order to Alpaca (this will be updated when we modify alpaca_client)
            result = await self.alpaca_client.submit_order(
                symbol=symbol,
                side=side,
                quantity=float(qty),
                order_type=order_type,
                time_in_force=tif,
                headers=headers,
            )

            broker_submit_total.labels(result="success").inc()

            logger.info(
                "Order submitted to broker successfully",
                extra={
                    "order_id": order_id,
                    "client_idempotency_key": client_idempotency_key,
                    "symbol": symbol,
                    "broker_order_id": result.get("id") if result else None,
                },
            )

        except Exception as e:
            # Categorize error for metrics
            error_category = self._categorize_broker_error(e)
            broker_submit_total.labels(result=error_category).inc()

            logger.error(
                "Failed to submit order to broker",
                extra={
                    "order_id": order_id,
                    "client_idempotency_key": client_idempotency_key,
                    "symbol": symbol,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )

            raise

        finally:
            duration = asyncio.get_event_loop().time() - start_time
            broker_submit_latency_seconds.observe(duration)

    def _categorize_broker_error(self, error: Exception) -> str:
        """Categorize broker errors for metrics."""
        error_str = str(error).lower()

        if "timeout" in error_str:
            return "timeout"
        elif "4" in error_str and "error" in error_str:
            return "4xx"
        elif "5" in error_str and "error" in error_str:
            return "5xx"
        else:
            return "exception"

    @property
    def is_running(self) -> bool:
        """Check if dispatcher is running."""
        return self._running
