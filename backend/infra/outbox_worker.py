"""
Unified Outbox Background Worker

This module implements an async background worker that processes outbox events
in FIFO order using proper ORM patterns instead of direct SQL connections.

ARCHITECTURAL FIX: Eliminates direct sqlite3.connect() usage that bypassed ORM.
Now uses unified database manager and repository pattern for all database access.

Audit 2026-10-05 (C04-01, C01-04): a dead-lettered order, and an entry refused
at dispatch because it is stale or its regular session has closed, is recorded
on its order row (``attributes.outbox_dead_letter``) in the dead-letter
transaction. Once that commit has settled, and only while no other delivery of
the order is pending, read-only client-key lookups decide: two of Alpaca's
order-not-found answers (HTTP 404, code 40410000, "order not found...") at
least DEAD_LETTER_CONFIRM_SECONDS apart, with no other answer between them,
finalize the row ('rejected', or 'expired' for a refused entry) with the
absence proof; an order found at the broker is attached by its client key; any
other answer, including any other 404, is retried later. The organism engine
releases a pending entry identity only for a row finalized this way. Refusals
and outcomes are counted per session (``dispatch_lifecycle_status``).
"""

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import os
import random
import time
from typing import Any
import uuid

# §2.1 FIX: Use canonical config instead of separate UnifiedSettings
from backend.config.settings import get_settings
from backend.infra.observability import trace_span
from backend.integrations.alpaca_broker import BROKER_ACK_STATE_PREFIX
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


# V13 W95 (Lens 4): Prometheus observability for the outbox prune loop.
# `outbox_pruned_total` increments by every batch's pruned-row count;
# `outbox_prune_last_run_timestamp_seconds` lets alerts fire if the
# loop hasn't run in >36h.  Both are guarded against duplicate
# registration (test envs reimport this module).
try:
    from prometheus_client import Counter as _PCounter, Gauge as _PGauge
    try:
        OUTBOX_PRUNED_TOTAL = _PCounter(
            "outbox_pruned_total",
            "V13 W95: total outbox events pruned (BB5-F1 retention).",
        )
    except ValueError:  # already registered (re-import in tests)
        OUTBOX_PRUNED_TOTAL = None
    try:
        OUTBOX_PRUNE_LAST_RUN_TS = _PGauge(
            "outbox_prune_last_run_timestamp_seconds",
            "V13 W95: unix timestamp of the most-recent outbox prune "
            "completion.  Alert if (now - this) > 36h.",
        )
    except ValueError:
        OUTBOX_PRUNE_LAST_RUN_TS = None
except ImportError:  # prometheus_client not installed
    OUTBOX_PRUNED_TOTAL = None
    OUTBOX_PRUNE_LAST_RUN_TS = None


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

        # Audit 2026-10-05 C04-01: and the dead-letter absence loop.
        dead_letter_task = getattr(self, "_dead_letter_task", None)
        if dead_letter_task is not None:
            dead_letter_task.cancel()
            try:
                await dead_letter_task
            except asyncio.CancelledError:
                pass
            self._dead_letter_task = None

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
        # V13 W95: emit metrics regardless of pruned count so the
        # last-run timestamp updates even on no-op runs.
        if OUTBOX_PRUNED_TOTAL is not None and total_pruned > 0:
            try:
                OUTBOX_PRUNED_TOTAL.inc(total_pruned)
            except Exception as _e:  # noqa: BLE001
                logger.debug("V13 W95: prune metric emit suppressed: %s", _e)
        if OUTBOX_PRUNE_LAST_RUN_TS is not None:
            try:
                OUTBOX_PRUNE_LAST_RUN_TS.set(time.time())
            except Exception as _e:  # noqa: BLE001
                logger.debug("V13 W95: prune metric emit suppressed: %s", _e)
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

    async def start_dead_letter_loop(self, *, interval_seconds: float | None = None) -> None:
        """Audit 2026-10-05 C04-01: run ``resolve_dead_letters`` periodically.

        A separate task, so broker lookups never hold up order dispatch.
        Idempotent; ``stop()`` cancels it.
        """
        if getattr(self, "_dead_letter_task", None) is not None:
            return
        interval = DEAD_LETTER_SWEEP_SECONDS if interval_seconds is None else interval_seconds

        async def _loop() -> None:
            while self._running:
                try:
                    await self.resolve_dead_letters()
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001 - retried on the next sweep
                    logger.warning("Dead-letter absence sweep failed: %s", e)
                await asyncio.sleep(interval)

        self._dead_letter_task = asyncio.create_task(_loop())
        logger.info("Dead-letter absence loop started (interval=%ss)", interval)

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
                        "next_attempt_at": event.next_attempt_at,
                        "last_error": getattr(event, "last_error", None),
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
        payload = dict(event.get("payload", {}))
        retry_count = event.get("retry_count", 0)
        prior_error = event.get("last_error")
        lookup_only = isinstance(prior_error, str) and prior_error.startswith("INTRA_BROKER_ACK")
        nested = payload.get("payload")
        client_key = (nested if isinstance(nested, dict) else payload).get("client_key")

        if lookup_only:
            try:
                state = json.loads(prior_error.removeprefix(BROKER_ACK_STATE_PREFIX))
                valid_state = (
                    isinstance(state, dict) and state.get("version") == 1
                    and isinstance(client_key, str) and bool(client_key.strip())
                    and state.get("client_order_id") == client_key
                )
            except (TypeError, ValueError):
                valid_state = False
            if not valid_state:
                # Never turn corrupt/unsupported durable state into a fresh
                # order. Stop delivery while retaining its original identity.
                await self._move_to_dlq(event, {
                    "success": False, "submission_ambiguous": True,
                    "status": "reconciliation_required", "error": prior_error,
                })
                return
            payload["_broker_ack_lookup_only"] = True
            if isinstance(nested, dict):
                payload["payload"] = {**nested, "_broker_ack_lookup_only": True}
        elif topic == "order.submitted":
            # Audit 2026-10-05 C01-04: an entry is never sent late. Exits and
            # lookup-only events are never refused here.
            try:
                refusal = entry_dispatch_refusal(payload, event.get("created_at"), now=_now_utc())
            except Exception as exc:  # noqa: BLE001 - an unchecked order is held, not sent
                logger.error("Entry dispatch check failed; order not sent", event_id=event_id,
                             error=str(exc), error_type=type(exc).__name__)
                await self._handle_event_failure(event, {
                    "success": False, "retryable": True,
                    "error": f"entry_dispatch_check_unavailable:{type(exc).__name__}",
                })
                return
            if refusal is not None:
                await self._expire_entry_at_dispatch(event, *refusal)
                return

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
                if result.get("broker") == "alpaca":
                    # A known real acknowledgement remains lookup-only if
                    # marking delivery sent fails after order persistence.
                    lookup_only = True
                    prior_error = BROKER_ACK_STATE_PREFIX + json.dumps({
                        "version": 1, "client_order_id": client_key,
                    }, separators=(",", ":"))
                # Mark event as succeeded
                await self._mark_event_succeeded(event_id, result)
                logger.info("Event processed successfully",
                           event_id=event_id,
                           topic=topic)
            else:
                if lookup_only or result.get("submission_ambiguous"):
                    # Preserve the marker even when an unexpected downstream
                    # lookup failure returns an ordinary error dictionary.
                    marker = prior_error if lookup_only else BROKER_ACK_STATE_PREFIX + json.dumps({
                        "version": 1, "client_order_id": client_key,
                    }, separators=(",", ":"))
                    identity_invalid = (
                        not isinstance(client_key, str) or not client_key.strip()
                        or (not lookup_only and result.get("client_order_id") != client_key)
                    )
                    # Latch uncertainty before any persistence await. If the
                    # first retry commit fails, the outer failure path must
                    # persist this same marker, never an ordinary retry error.
                    lookup_only, prior_error = True, marker
                    result = {**result, "submission_ambiguous": True,
                              "status": "reconciliation_required", "error": marker}
                    if identity_invalid:
                        await self._move_to_dlq(event, result)
                    else:
                        await self._handle_event_failure(event, result)
                    return
                if result.get("dispatch_refused"):
                    # Audit 2026-10-05 C01-01: the exit guard (or the broker)
                    # refused the order definitively; never retried.
                    await self._finalize_refused_dispatch(event, result)
                    return
                if result.get("retryable"):
                    # The exit guard could not confirm the order is safe to
                    # send, so nothing was sent: retry it, whatever the text.
                    await self._handle_event_failure(event, result)
                    return
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

            if lookup_only:
                await self._handle_event_failure(event, {
                    "success": False, "submission_ambiguous": True,
                    "status": "reconciliation_required", "error": prior_error,
                })
                return

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

        real_acknowledged = False
        acknowledged_broker_id = None
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
                if payload.get("_broker_ack_lookup_only"):
                    # A mode flip cannot turn an unresolved real submission
                    # into a successful mock/shadow acknowledgement.
                    result = await self._submit_real_broker_order(payload)
                elif mode == "shadow":
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
                real_acknowledged = result.get("broker") == "alpaca"
                acknowledged_broker_id = result.get("broker_order_id")
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
            logger.error("Acknowledged order persistence failed" if real_acknowledged else "Order submission failed",
                        order_id=order_id,
                        error=str(e),
                        error_type=type(e).__name__)
            if real_acknowledged:
                return {
                    "success": False, "submission_ambiguous": True,
                    "status": "reconciliation_required",
                    "client_order_id": payload.get("client_key"),
                    "broker_order_id": acknowledged_broker_id,
                    "error": "broker_acknowledgement_persistence_failed",
                    "order_id": order_id,
                }
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
        details: dict[str, Any] | None = None,
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

            logger.info(
                "Updating order status via ORM repository",
                order_id=order_id,
                status=status,
                broker_order_id=broker_order_id,
            )

            # Use proper async session and repository pattern
            async with get_session_context() as session:
                order_repo = OrdersRepo(session)

                # Parse order ID (handle both UUID formats)
                try:
                    if "-" in order_id:
                        order_uuid = uuid.UUID(order_id)
                    else:
                        # Database format without hyphens
                        formatted_id = f"{order_id[:8]}-{order_id[8:12]}-{order_id[12:16]}-{order_id[16:20]}-{order_id[20:]}"
                        order_uuid = uuid.UUID(formatted_id)
                except (ValueError, IndexError) as e:
                    logger.error(f"Invalid order ID format: {order_id}", error=str(e))
                    raise ValueError(f"Invalid order ID format: {order_id}") from e

                # Serialize this acknowledgement with stream/recovery fill
                # writers, then reread the row after acquiring its lock.
                from sqlalchemy import select
                from backend.infra.schemas import Order

                order = (
                    await session.execute(
                        select(Order)
                        .where(Order.id == order_uuid)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                ).scalar_one_or_none()
                if order is None:
                    raise ValueError(f"Order not found: {order_id}")
                if (
                    broker_order_id is not None
                    and order.broker_order_id is not None
                    and broker_order_id != order.broker_order_id
                ):
                    raise ValueError("Broker acknowledgement identity changed")

                update_attributes = {
                    key: str(value)
                    for key, value in (details or {}).items()
                    if key not in {"filled_qty", "avg_fill_price"}
                }
                snapshot_accounting = None
                if details and (details.get("broker") == "alpaca" or "alpaca_response" in details):
                    from backend.integrations.alpaca_stream import apply_order_fill_snapshot
                    from backend.services.order_recovery_service import (
                        OrderIdentity,
                        validate_order_snapshot,
                    )

                    # Real dispatcher fills are nested, not the mock response's
                    # top-level fields. Never infer a fill from status alone.
                    if (
                        not isinstance(broker_order_id, str)
                        or str(uuid.UUID(broker_order_id)) != broker_order_id
                    ):
                        raise ValueError("Invalid broker acknowledgement identity")
                    snapshot = details.get("alpaca_response")
                    identity = OrderIdentity(
                        order.id,
                        broker_order_id,
                        order.client_idempotency_key,
                        order.symbol,
                        order.side,
                        order.qty,
                    )
                    final_status, quantity, price = validate_order_snapshot(identity, snapshot)
                    if status != snapshot["status"]:
                        raise ValueError("Broker acknowledgement status mismatch")
                    accounting = await apply_order_fill_snapshot(
                        session,
                        order,
                        status=final_status,
                        cumulative_filled_qty=quantity,
                        avg_fill_price=price,
                        broker_order_id=broker_order_id,
                        broker_order_data=snapshot,
                    )
                    if accounting.get("reason") == "stale_snapshot":
                        logger.info("Ignored stale broker acknowledgement", order_id=order_id)
                        return
                    status = accounting["status"]
                    snapshot_accounting = accounting
                    await order_repo.attach_broker_result(
                        order_uuid,
                        attributes=update_attributes or None,
                    )
                else:
                    # Preserve mock/shadow attachment behavior, but no delayed
                    # acknowledgement may roll back established fill evidence.
                    def number(value):
                        if isinstance(value, bool):
                            raise ValueError("Invalid acknowledgement fill number")
                        value = Decimal(str(value))
                        if not value.is_finite():
                            raise ValueError("Invalid acknowledgement fill number")
                        return value

                    try:
                        real_identity = (
                            order.broker_order_id is not None
                            and str(uuid.UUID(order.broker_order_id)) == order.broker_order_id
                        )
                    except (ValueError, TypeError, AttributeError):
                        real_identity = False
                    if (
                        real_identity
                        and details
                        and (
                            details.get("broker") in {"mock", "dry_run", "shadow", "none"}
                            or details.get("shadow") is True
                        )
                    ):
                        raise ValueError("Synthetic acknowledgement cannot change a real broker order")
                    previous = number(order.filled_qty or 0)
                    quantity = (
                        number(details["filled_qty"]) if details and "filled_qty" in details else None
                    )
                    price = (
                        number(details["avg_fill_price"])
                        if details and "avg_fill_price" in details
                        else None
                    )
                    if quantity is not None and (quantity < 0 or quantity > order.qty):
                        raise ValueError("Invalid acknowledgement fill quantity")
                    if price is not None and price <= 0:
                        raise ValueError("Invalid acknowledgement fill price")
                    if quantity is not None and quantity < previous:
                        logger.info("Ignored stale broker acknowledgement", order_id=order_id)
                        return
                    terminal = {"filled", "canceled", "cancelled", "expired", "rejected", "replaced"}
                    if order.status in terminal:
                        if quantity is not None and quantity > previous:
                            raise ValueError("Terminal fill change requires broker reconciliation")
                        status = order.status
                    if previous > 0 and (quantity is None or quantity == previous):
                        # An acknowledgement without new fill evidence cannot
                        # demote a partial fill to accepted/submitted/shadow.
                        status = order.status
                        if price is not None and price != order.avg_fill_price:
                            raise ValueError("Fill cash correction requires broker reconciliation")
                    await order_repo.attach_broker_result(
                        order_id=order_uuid,
                        broker_order_id=broker_order_id,
                        status=status,
                        filled_qty=quantity,
                        avg_fill_price=price,
                        attributes=update_attributes or None,
                    )

                await session.commit()
                if snapshot_accounting is not None:
                    from backend.integrations.alpaca_stream import log_lot_accounting_discrepancy

                    log_lot_accounting_discrepancy(
                        snapshot_accounting, ingress="outbox_acknowledgement"
                    )

                logger.info(
                    "Order status updated successfully via ORM",
                    order_id=order_id,
                    status=status,
                    broker_order_id=broker_order_id,
                )

        except Exception as e:
            logger.error(
                "Failed to update order status via ORM",
                order_id=order_id,
                status=status,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
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

    async def _move_to_dlq(self, event: dict[str, Any], error_result: dict[str, Any],
                           *, terminal_status: str | None = None):
        """
        Move event to dead letter queue.

        Args:
            event: Failed event
            error_result: Final error details
            terminal_status: Order status once the broker confirms the order was
                never placed (audit 2026-10-05 C04-01); 'rejected' by default,
                'expired' for an entry refused at dispatch.
        """
        event_id = event.get("id")

        try:
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
                    # Audit 2026-10-05 C04-01: in the same transaction, record
                    # the dead letter on its order row for the absence check.
                    dead_letter = await self._record_dead_letter(
                        session, event, error_result,
                        terminal_status or DEAD_LETTER_ORDER_STATUS,
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
                    alert = dlq_exposure_alert(event, error_result)

                    await session.commit()
                    # Page only once the dead-letter state is committed: a failed
                    # commit leaves the event for retry and must not page.
                    if alert is not None:
                        logger.critical(alert["message"], **alert["fields"])
                    if dead_letter is not None:
                        logger.info(
                            "Dead-lettered order recorded; the broker absence check follows "
                            "(audit 2026-10-05 C04-01)",
                            event_id=event_id, order_id=dead_letter["order_id"],
                            symbol=dead_letter["symbol"], side=dead_letter["side"],
                            reason=dead_letter["reason"],
                            terminal_status=dead_letter["terminal_status"],
                        )
                        self._count_lifecycle("dead_lettered", dead_letter["reason"])
                    if error_result.get("dispatch_expired"):
                        # Review NB4: a refused entry counts (and may page) once committed.
                        self._note_entry_refusal(event, error_result)

                    # Uncertain acknowledgement is not broker rejection. The
                    # outbox delivery stops, while the order stays unresolved
                    # and normal client-key fill reconciliation remains valid.
                    try:
                        from backend.websocket import broadcaster
                        if broadcaster:
                            payload = event.get("payload", {})
                            await broadcaster.broadcast_to_topic("orders", {
                                "type": ("order.reconciliation_required"
                                         if error_result.get("submission_ambiguous")
                                         else "order.expired"
                                         if error_result.get("dispatch_expired")
                                         else "order.rejected"),
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

    async def _finalize_refused_dispatch(self, event: dict[str, Any], result: dict[str, Any]):
        """Audit 2026-10-05 C01-01: record an exit that was refused at dispatch.

        The dispatcher refuses only once the persisted client key is not found
        at the broker, or when the broker rejected the order outright, so the
        order is not live. In one transaction the order row becomes 'rejected'
        (an accountable terminal status) with the reason in
        ``attributes.dispatch_refusal``, and the event is dead-lettered without
        retry. A row that already shows broker evidence (a broker id or fills)
        or a terminal status is left as it is. The CRITICAL page follows the
        commit; if the commit fails the error propagates and the event is
        retried, which repeats the guard.
        """
        import uuid

        from sqlalchemy import select

        from backend.infra.outbox import OutboxRepo
        from backend.infra.repositories.orders import OrdersRepo
        from backend.infra.schemas import Order

        event_id = event.get("id")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if isinstance(payload.get("payload"), dict):
            payload = {**payload, **payload["payload"]}
        order_id = result.get("order_id") or payload.get("order_id")
        status = _REFUSED_ORDER_STATUS
        reason = str(result.get("refusal_reason") or "dispatch_refused")
        detail = str(result.get("refusal_detail") or result.get("error") or reason)
        error_message = str(result.get("error") or f"DISPATCH_REFUSED:{reason}")
        record = {
            "reason": reason,
            "detail": detail[:500],
            "intent": result.get("intent"),
            "outbox_event_id": event_id,
            "refused_at": datetime.now(UTC).isoformat(),
        }
        outcome = "order_row_missing"

        async with self.sessionmaker() as session:
            try:
                try:
                    order_uuid = uuid.UUID(str(order_id))
                except (TypeError, ValueError):
                    order_uuid = None
                row = None
                if order_uuid is not None:
                    row = (
                        await session.execute(
                            select(Order)
                            .where(Order.id == order_uuid)
                            .with_for_update()
                            .execution_options(populate_existing=True)
                        )
                    ).scalar_one_or_none()
                if row is not None:
                    if row.broker_order_id or Decimal(str(row.filled_qty or 0)) != 0:
                        outcome = "order_row_has_broker_evidence"
                    elif str(row.status or "").lower() in _TERMINAL_ORDER_STATUSES:
                        outcome = "order_row_already_terminal"
                    else:
                        await OrdersRepo(session).attach_broker_result(
                            row.id,
                            status=status,
                            attributes={"dispatch_refusal": record},
                        )
                        outcome = f"order_marked_{status}"
                await OutboxRepo(session).mark_failed(
                    event_id=uuid.UUID(str(event_id)),
                    attempts=event.get("retry_count", 0),
                    error_message=error_message,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

        message = _refusal_headline(reason, outcome) + ": " + detail + _OUTCOME_NOTES.get(outcome, "")
        logger.critical(
            message,
            event_id=event_id,
            order_id=order_id,
            symbol=payload.get("symbol"),
            side=payload.get("side"),
            qty=payload.get("qty"),
            client_key=payload.get("client_key"),
            reason=reason,
            order_status=status,
            outcome=outcome,
        )
        try:
            from backend.websocket import broadcaster
            if broadcaster:
                await broadcaster.broadcast_to_topic("orders", {
                    "type": "order.rejected",
                    "order_id": order_id or event_id,
                    "symbol": payload.get("symbol"),
                    "reason": error_message[:500],
                    "event_id": event_id,
                })
        except Exception as ws_err:  # noqa: BLE001 - the notice is best-effort
            logger.debug("WebSocket notification failed (non-critical)", error=str(ws_err))

    # ── Audit 2026-10-05 C01-04 / C04-01: refused entries and dead letters ──

    async def _expire_entry_at_dispatch(self, event: dict[str, Any], reason: str, detail: str):
        """Audit 2026-10-05 C01-04: an entry too old, or whose session has closed, is not sent.

        It is dead-lettered without a dispatch attempt, and its row is recorded
        for the absence check like any other dead letter; once the broker
        confirms it never received the order the row becomes 'expired', which
        lets the engine release the pending entry identity. An earlier attempt
        that did reach the broker is found by its client key and attached.
        """
        payload = _flat_payload(event.get("payload"))
        logger.warning(
            "Entry not sent: refused at dispatch (audit 2026-10-05 C01-04)",
            event_id=event.get("id"), order_id=payload.get("order_id"),
            symbol=payload.get("symbol"), side=payload.get("side"),
            qty=payload.get("qty"), reason=reason, detail=detail,
        )
        await self._move_to_dlq(event, {
            "success": False,
            "dispatch_expired": True,
            "refusal_reason": reason,
            "error": f"DISPATCH_EXPIRED:{reason}: {detail}",
        }, terminal_status=EXPIRED_ENTRY_ORDER_STATUS)

    async def _record_dead_letter(self, session, event: dict[str, Any],
                                  error_result: dict[str, Any], terminal_status: str):
        """Audit 2026-10-05 C04-01: mark a dead-lettered order row for the absence check.

        Runs inside the dead-letter transaction, so the record exists exactly
        when the event is dead-lettered. Only an order.submitted event with an
        unambiguous outcome qualifies: an ambiguous submission (lookup-only
        marker) may be live at the broker and keeps its existing handling. Only
        a row still awaiting the broker (no broker id, no fills, not terminal,
        same client key) is recorded; its status is left as it is. Returns a
        summary for the log, or None.
        """
        if event.get("topic") != "order.submitted" or _ambiguous_dead_letter(event, error_result):
            return None
        payload = _flat_payload(event.get("payload"))
        client_key = payload.get("client_key")
        try:
            order_uuid = uuid.UUID(str(payload.get("order_id")))
        except (TypeError, ValueError):
            return None
        if not isinstance(client_key, str) or not client_key.strip():
            return None

        from sqlalchemy import select

        from backend.infra.repositories.orders import OrdersRepo
        from backend.infra.schemas import Order

        row = (
            await session.execute(
                select(Order)
                .where(Order.id == order_uuid)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if (row is None or row.broker_order_id
                or Decimal(str(row.filled_qty or 0)) != 0
                or str(row.status or "").lower() in _TERMINAL_ORDER_STATUSES
                or row.client_idempotency_key != client_key):
            return None
        attempts = int(event.get("retry_count") or 0)
        reason = str(error_result.get("refusal_reason") or (
            "retries_exhausted" if attempts >= getattr(self, "max_retries", 5)
            else "non_retryable_error"))
        record = {
            "state": DEAD_LETTER_STATE_PENDING,
            "reason": reason,
            "error": str(error_result.get("error") or "")[:300],
            "outbox_event_id": str(event.get("id")),
            "client_order_id": client_key,
            "attempts": attempts,
            "dead_lettered_at": _now_utc().isoformat(),
            "terminal_status": terminal_status,
        }
        await OrdersRepo(session).attach_broker_result(
            row.id, attributes={DEAD_LETTER_ATTRIBUTE: record},
        )
        return {"order_id": str(row.id), "symbol": row.symbol, "side": row.side, **record}

    async def resolve_dead_letters(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        """Audit 2026-10-05 C04-01: settle recorded dead letters against the broker.

        For each recorded row whose dead letter is at least
        DEAD_LETTER_SETTLE_SECONDS old (a late-processed POST of the last
        attempt has time to show) and is due under its retry backoff, and
        only while no other delivery of the order is pending, the order is
        looked up by its client key. Absence takes two of Alpaca's
        order-not-found answers at least DEAD_LETTER_CONFIRM_SECONDS apart,
        with no other answer between them (review NB1); the second finalizes
        the row with the absence proof. An order found at the broker is
        attached, and any other answer is retried with a capped backoff. A row
        whose check raises is logged and backed off, and the sweep goes on
        (review NB3). Returns one outcome per row it acted on. Never submits
        an order.
        """
        now = now or _now_utc()
        outcomes = []
        lookups = 0
        for order_id, record in await self._dead_letter_candidates():
            if lookups >= DEAD_LETTER_SWEEP_BATCH:
                break
            try:
                outcome = await self._resolve_dead_letter(order_id, record, now)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - one row never stops the sweep
                outcome = self._dead_letter_check_failed(order_id, now, exc)
            if outcome is not None:
                lookups += int(bool(outcome.get("lookup")))
                outcomes.append(outcome)
        return outcomes

    def _dead_letter_check_failed(self, order_id: Any, now: datetime,
                                  exc: Exception) -> dict[str, Any]:
        """Review NB3: a row whose check raised is backed off, so the rows behind it still run.

        Counted as a lookup (it may have made one). A first order-not-found
        answer it had is dropped: absence is proven afresh.
        """
        key = str(order_id)
        self._dead_letter_first_answers().pop(key, None)
        delay = self._back_off_dead_letter(key, now)
        error = f"{type(exc).__name__}: {exc}"[:300]
        logger.error(
            "Dead-lettered order: absence check failed, backing off (audit 2026-10-05 C04-01)",
            order_id=key, error=error, retry_in_seconds=delay,
        )
        return {"order_id": key, "outcome": "check_failed", "detail": error, "lookup": True}

    def _dead_letter_retries(self) -> dict[str, tuple[datetime, int]]:
        """Per-row retry state: ``order id -> (next due time, attempts)``; in memory."""
        retries = getattr(self, "_dead_letter_retry", None)
        if not isinstance(retries, dict):
            retries = self._dead_letter_retry = {}
        return retries

    def _dead_letter_first_answers(self) -> dict[str, dict[str, Any]]:
        """Review NB1: the first order-not-found answer per row, awaiting its confirmation.

        ``order id -> {outbox_event_id, checked_at, answer}``; in memory, so a
        restart proves absence afresh.
        """
        answers = getattr(self, "_dead_letter_absence", None)
        if not isinstance(answers, dict):
            answers = self._dead_letter_absence = {}
        return answers

    def _back_off_dead_letter(self, key: str, now: datetime) -> float:
        """Schedule the row's next lookup: 15 s doubling to the 300 s cap."""
        retries = self._dead_letter_retries()
        retry = retries.get(key)
        attempts = (retry[1] if retry is not None else 0) + 1
        # The exponent is bounded: the delay is capped long before, and an
        # unbounded power would overflow the float after about 1,000 attempts.
        delay = min(DEAD_LETTER_SWEEP_SECONDS * 2 ** min(attempts - 1, 16),
                    DEAD_LETTER_MAX_BACKOFF_SECONDS)
        retries[key] = (now + timedelta(seconds=delay), attempts)
        return delay

    async def _dead_letter_candidates(self) -> list[tuple[Any, Any]]:
        """Rows recorded by ``_record_dead_letter`` still awaiting the absence check."""
        from sqlalchemy import func, select

        from backend.infra.schemas import Order

        async with self.sessionmaker() as session:
            rows = (
                await session.execute(
                    select(Order.id, Order.attributes)
                    .where(
                        Order.broker_order_id.is_(None),
                        func.lower(Order.status).not_in(sorted(_TERMINAL_ORDER_STATUSES)),
                        Order.attributes[(DEAD_LETTER_ATTRIBUTE, "state")].as_string()
                        == DEAD_LETTER_STATE_PENDING,
                    )
                    .order_by(Order.updated_at, Order.id)
                    .limit(DEAD_LETTER_CANDIDATE_LIMIT)
                )
            ).all()
        return [(order_id, (attributes or {}).get(DEAD_LETTER_ATTRIBUTE))
                for order_id, attributes in rows if isinstance(attributes, dict)]

    async def _resolve_dead_letter(self, order_id: Any, record: Any,
                                   now: datetime) -> dict[str, Any] | None:
        """One recorded dead letter; None when it is not due yet."""
        key = str(order_id)
        try:
            order_uuid = uuid.UUID(key)
            client_key = record["client_order_id"]
            dead_lettered_at = _as_utc(record["dead_lettered_at"])
            terminal_status = record["terminal_status"]
            uuid.UUID(str(record["outbox_event_id"]))
        except (TypeError, ValueError, KeyError):
            return {"order_id": key, "outcome": "record_invalid"}
        if (not isinstance(client_key, str) or not client_key.strip() or dead_lettered_at is None
                or terminal_status not in (DEAD_LETTER_ORDER_STATUS, EXPIRED_ENTRY_ORDER_STATUS)):
            return {"order_id": key, "outcome": "record_invalid"}
        if (now - dead_lettered_at).total_seconds() < DEAD_LETTER_SETTLE_SECONDS:
            return None
        retries = self._dead_letter_retries()
        retry = retries.get(key)
        if retry is not None and now < retry[0]:
            return None
        answers = self._dead_letter_first_answers()
        first = answers.get(key)
        if first is not None and first["outbox_event_id"] != record.get("outbox_event_id"):
            answers.pop(key, None)  # another dead letter of the order: prove absence afresh
            first = None
        if first is not None and (now - first["checked_at"]).total_seconds() < DEAD_LETTER_CONFIRM_SECONDS:
            return None  # review NB1: the confirming lookup is not due yet
        if await self._other_pending_delivery(order_uuid):
            # Another delivery could still place the order: absence now proves nothing.
            answers.pop(key, None)
            return {"order_id": key, "outcome": "pending_delivery_exists"}

        from backend.integrations import alpaca_outbox

        try:
            probe = await asyncio.wait_for(
                alpaca_outbox.probe_order_absence(client_key), DEAD_LETTER_LOOKUP_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            probe = alpaca_outbox.AbsenceProbe("unknown", None, "lookup_timeout")
        checked_at = now.isoformat()
        if probe.state == "absent":
            retries.pop(key, None)
            answer = dict(probe.evidence or {})
            if first is None:
                # Review NB1: one answer is not proof. Confirm it later, with no
                # other answer between (a POST the broker processes late, or a
                # read-path 404 during an incident, would then show).
                answers[key] = {"outbox_event_id": record.get("outbox_event_id"),
                                "checked_at": now, "answer": answer}
                logger.info(
                    "Dead-lettered order: the broker answered order not found; confirming "
                    "with a second lookup (audit 2026-10-05 C04-01)",
                    order_id=key, client_order_id=client_key, answer=answer,
                    confirm_after_seconds=DEAD_LETTER_CONFIRM_SECONDS,
                )
                return {"order_id": key, "outcome": "absence_awaiting_confirmation",
                        "detail": probe.detail, "lookup": True}
            answers.pop(key, None)
            outcome = await self._write_dead_letter_outcome(
                order_uuid, record, state=DEAD_LETTER_STATE_FINALIZED, status=terminal_status,
                require_unsent=True, absence={
                    "result": "not_found", "checked_at": checked_at,
                    "client_order_id": client_key,
                    "lookup": "GET /v2/orders:by_client_order_id",
                    "answers": [
                        {"checked_at": first["checked_at"].isoformat(), **first["answer"]},
                        {"checked_at": checked_at, **answer},
                    ],
                },
            )
            if outcome == DEAD_LETTER_STATE_FINALIZED:
                self._count_lifecycle("finalized", terminal_status)
                logger.warning(
                    "Dead-lettered order finalized: the broker confirmed twice that it was never "
                    "placed (audit 2026-10-05 C04-01)",
                    order_id=key, client_order_id=client_key, status=terminal_status,
                    reason=record.get("reason"), outbox_event_id=record.get("outbox_event_id"),
                    first_checked_at=first["checked_at"].isoformat(), checked_at=checked_at,
                )
            return {"order_id": key, "outcome": outcome, "detail": probe.detail, "lookup": True}
        answers.pop(key, None)  # any other answer: a first order-not-found answer no longer counts
        if probe.state == "present":
            retries.pop(key, None)
            outcome = await self._attach_dead_letter(order_uuid, record, probe.order, checked_at)
            return {"order_id": key, "outcome": outcome, "detail": probe.detail, "lookup": True}
        delay = self._back_off_dead_letter(key, now)
        self._count_lifecycle("absence_unverified", probe.detail.split(":", 1)[0] or "unknown")
        # A 404 that is not Alpaca's order-not-found answer (an unknown route, an
        # HTML page) is a contract mismatch an operator must look at.
        log = logger.error if probe.detail.startswith("not_found_unconfirmed") else logger.warning
        log(
            "Dead-lettered order: broker absence unverified, retrying (audit 2026-10-05 C04-01)",
            order_id=key, client_order_id=client_key, detail=probe.detail,
            evidence=probe.evidence, attempts=retries[key][1], retry_in_seconds=delay,
        )
        return {"order_id": key, "outcome": "absence_unverified", "detail": probe.detail, "lookup": True}

    async def _other_pending_delivery(self, order_uuid: uuid.UUID) -> bool:
        """True when a pending order.submitted event for this order exists (or cannot be ruled out)."""
        from sqlalchemy import select

        from backend.infra.schemas import OutboxEvent

        async with self.sessionmaker() as session:
            rows = (
                await session.execute(
                    select(OutboxEvent.payload)
                    .where(OutboxEvent.status == "pending", OutboxEvent.topic == "order.submitted")
                    .limit(DEAD_LETTER_PENDING_SCAN_LIMIT + 1)
                )
            ).all()
        if len(rows) > DEAD_LETTER_PENDING_SCAN_LIMIT:
            return True
        for (payload,) in rows:
            try:
                if uuid.UUID(str(_flat_payload(payload).get("order_id"))) == order_uuid:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    async def _write_dead_letter_outcome(self, order_uuid: uuid.UUID, record: dict[str, Any], *,
                                         state: str, absence: dict[str, Any],
                                         status: str | None = None, require_unsent: bool) -> str:
        """Record the absence-check outcome (and the terminal status) under the row lock.

        Nothing is written when the row's record is no longer the pending one
        for this dead letter. Finalizing (``require_unsent``) also needs the row
        still unsent (no broker id, no fills, not terminal) and its event still
        dead-lettered (or already pruned, which only removes failed or sent
        events).
        """
        from sqlalchemy import select

        from backend.infra.repositories.orders import OrdersRepo
        from backend.infra.schemas import Order, OutboxEvent

        async with self.sessionmaker() as session:
            try:
                row = (
                    await session.execute(
                        select(Order)
                        .where(Order.id == order_uuid)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                ).scalar_one_or_none()
                attributes = row.attributes if row is not None and isinstance(row.attributes, dict) else {}
                current = attributes.get(DEAD_LETTER_ATTRIBUTE)
                if (not isinstance(current, dict) or current.get("state") != DEAD_LETTER_STATE_PENDING
                        or current.get("outbox_event_id") != record.get("outbox_event_id")):
                    await session.rollback()
                    return "record_changed"
                if require_unsent:
                    if (row.broker_order_id or Decimal(str(row.filled_qty or 0)) != 0
                            or str(row.status or "").lower() in _TERMINAL_ORDER_STATUSES):
                        await session.rollback()
                        return "order_row_changed"
                    event = await session.get(OutboxEvent, uuid.UUID(str(record["outbox_event_id"])))
                    if event is not None and event.status != "failed":
                        await session.rollback()
                        return "event_not_dead_lettered"
                await OrdersRepo(session).attach_broker_result(
                    row.id, status=status,
                    attributes={DEAD_LETTER_ATTRIBUTE: {**current, "state": state, "absence": absence}},
                )
                await session.commit()
                return state
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def _attach_dead_letter(self, order_uuid: uuid.UUID, record: dict[str, Any],
                                  order: dict[str, Any], checked_at: str) -> str:
        """A dead-lettered order is live at the broker: attach it by its client key and page.

        The acknowledgement is persisted through ``_update_order_status``, the
        same validated path as a normal acknowledgement (identity checks, fill
        accounting), so normal recovery and the engine's broker confirmation
        apply from here on. The outbox event stays dead-lettered; nothing is
        sent.
        """
        error = None
        try:
            await self._update_order_status(
                order_id=str(order_uuid), status=str(order.get("status")),
                broker_order_id=order.get("id"),
                details={"broker": "alpaca", "alpaca_response": order,
                         "message": "Dead-lettered order found at the broker by its client key"},
            )
        except Exception as exc:  # noqa: BLE001 - recorded and paged below
            error = f"{type(exc).__name__}: {exc}"[:300]
        state = DEAD_LETTER_STATE_FOUND if error is None else DEAD_LETTER_STATE_FOUND_UNATTACHED
        absence = {"result": "found", "checked_at": checked_at,
                   "client_order_id": record.get("client_order_id"),
                   "broker_order_id": order.get("id"), "broker_status": order.get("status")}
        if error is not None:
            absence["error"] = error
        outcome = "outcome_not_recorded"
        try:
            outcome = await self._write_dead_letter_outcome(
                order_uuid, record, state=state, absence=absence, require_unsent=False,
            )
        finally:
            # Review NB3: the page never depends on recording the outcome. Should
            # that write fail, the CRITICAL still goes out (outcome
            # 'outcome_not_recorded') and the sweep backs the row off.
            logger.critical(
                ("DEAD-LETTERED ORDER FOUND AT THE BROKER, attached by its client key"
                 if error is None else
                 "DEAD-LETTERED ORDER FOUND AT THE BROKER, could not be attached")
                + ": the outbox stopped delivery but the order is live; reconcile it",
                order_id=str(order_uuid), client_order_id=record.get("client_order_id"),
                broker_order_id=order.get("id"), broker_status=order.get("status"),
                reason=record.get("reason"), outcome=outcome, error=error,
            )
            self._count_lifecycle("found_at_broker", state)
        return outcome

    # ── Review NB4: process-local counts of the dispatch lifecycle ──

    def _lifecycle_session(self) -> dict[str, Any]:
        """This worker's counts for the current ET date; a new date starts from zero."""
        from backend.utils.market_hours import ET

        day = _now_utc().astimezone(ET).date().isoformat()
        session = getattr(self, "_lifecycle_counts", None)
        if not isinstance(session, dict) or session.get("session_date") != day:
            session = self._lifecycle_counts = {"session_date": day, "counts": {},
                                                "refusal_paged": False}
        return session

    def _count_lifecycle(self, kind: str, label: str) -> int:
        """Count one lifecycle event; returns the session's total for ``kind``.

        Monitoring only: a failure here never affects the lifecycle (returns 0).
        """
        try:
            bucket = self._lifecycle_session()["counts"].setdefault(kind, {})
            bucket[label] = bucket.get(label, 0) + 1
            return sum(bucket.values())
        except Exception as exc:  # noqa: BLE001 - counting is best-effort
            logger.debug("Dispatch lifecycle count failed", kind=kind, error=str(exc))
            return 0

    def _note_entry_refusal(self, event: dict[str, Any], error_result: dict[str, Any]) -> None:
        """Review NB4: count a committed entry refusal (C01-04) and page once per session.

        A healthy outbox refuses nothing; refusals above
        ENTRY_REFUSAL_PAGE_THRESHOLD in one session mean a slow outbox, a clock
        or a calendar fault is dropping entries, which would otherwise show only
        as missing trades.
        """
        reason = str(error_result.get("refusal_reason") or "unknown")
        total = self._count_lifecycle("entry_refused", reason)
        try:
            session = self._lifecycle_session()
            if total <= ENTRY_REFUSAL_PAGE_THRESHOLD or session.get("refusal_paged"):
                return
            session["refusal_paged"] = True
            payload = _flat_payload(event.get("payload"))
            logger.critical(
                "ENTRY DISPATCH REFUSALS ABOVE THRESHOLD: entries are being refused at dispatch "
                "(stale, or sent after their session closed) and are not traded; check outbox "
                "latency, the clocks and the market calendar",
                session_date=session.get("session_date"), refusals=total,
                threshold=ENTRY_REFUSAL_PAGE_THRESHOLD,
                by_reason=dict(session["counts"].get("entry_refused", {})),
                last_order_id=payload.get("order_id"), last_symbol=payload.get("symbol"),
                last_reason=reason,
            )
        except Exception as exc:  # noqa: BLE001 - monitoring never affects the dead letter
            logger.debug("Entry refusal page failed", error=str(exc))

    def dispatch_lifecycle_status(self) -> dict[str, Any]:
        """Review NB4: this worker's lifecycle counts for its current session date."""
        session = getattr(self, "_lifecycle_counts", None)
        session = session if isinstance(session, dict) else {}
        counts = {kind: dict(labels) for kind, labels in (session.get("counts") or {}).items()}
        return {
            "session_date": session.get("session_date"),
            "scope": "process_local_et_date_reset_on_restart",
            "entry_refusals": sum(counts.get("entry_refused", {}).values()),
            "finalized": sum(counts.get("finalized", {}).values()),
            "counts": counts,
            "refusal_page_threshold": ENTRY_REFUSAL_PAGE_THRESHOLD,
            "refusal_paged": bool(session.get("refusal_paged")),
        }


# Audit 2026-10-05 C01-04 / C04-01: entry dispatch limits and dead-letter
# finalization (see the module docstring).
DEAD_LETTER_ORDER_STATUS = "rejected"     # a dead letter the broker confirmed it never received
EXPIRED_ENTRY_ORDER_STATUS = "expired"    # an entry refused at dispatch, likewise confirmed
ENTRY_DISPATCH_MAX_AGE_SECONDS = 120.0    # measured from OutboxEvent.created_at (intent time)
DEAD_LETTER_SETTLE_SECONDS = 60.0         # dead letter to its first broker lookup
DEAD_LETTER_CONFIRM_SECONDS = 300.0       # first order-not-found answer to its confirming lookup
ENTRY_REFUSAL_PAGE_THRESHOLD = 1          # more entry refusals than this in one session page once
DEAD_LETTER_SWEEP_SECONDS = 15.0          # sweep interval and first retry backoff
DEAD_LETTER_MAX_BACKOFF_SECONDS = 300.0   # cap of the doubling retry backoff
DEAD_LETTER_LOOKUP_TIMEOUT_SECONDS = 5.0  # per client-key lookup
DEAD_LETTER_SWEEP_BATCH = 5               # lookups per sweep at most
DEAD_LETTER_CANDIDATE_LIMIT = 50          # recorded rows read per sweep
DEAD_LETTER_PENDING_SCAN_LIMIT = 1000     # pending events scanned; more is "cannot rule out"
DEAD_LETTER_ATTRIBUTE = "outbox_dead_letter"
DEAD_LETTER_STATE_PENDING = "absence_check_pending"
DEAD_LETTER_STATE_FINALIZED = "finalized"
DEAD_LETTER_STATE_FOUND = "found_at_broker"
DEAD_LETTER_STATE_FOUND_UNATTACHED = "found_unattached"


def _now_utc() -> datetime:
    """Clock of the entry dispatch limits and the dead-letter records (patched in tests)."""
    return datetime.now(UTC)


def _as_utc(value: Any) -> datetime | None:
    """A datetime or ISO string as aware UTC (naive values are UTC), else None."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _flat_payload(payload: Any) -> dict[str, Any]:
    """An order.submitted payload with a nested ``payload`` merged in, as the dispatcher sees it."""
    flat = dict(payload) if isinstance(payload, dict) else {}
    if isinstance(flat.get("payload"), dict):
        flat = {**flat, **flat["payload"]}
    return flat


def _ambiguous_dead_letter(event: dict[str, Any], error_result: dict[str, Any]) -> bool:
    """An ambiguous submission: the order may be live, so it is never finalized here."""
    return bool(error_result.get("submission_ambiguous")) or any(
        str(value or "").startswith("INTRA_BROKER_ACK")
        for value in (error_result.get("error"), event.get("last_error"))
    )


def entry_dispatch_refusal(payload: Any, created_at: Any, *, now: datetime) -> tuple[str, str] | None:
    """Audit 2026-10-05 C01-04: ``(reason, detail)`` when an entry must not be sent now.

    Every order that is not an exit is checked (exits are never refused for
    age; the exit guard covers them). ``created_at`` is the outbox row's
    creation time, the original intent time that retries do not change. The
    order is refused when it is older than ENTRY_DISPATCH_MAX_AGE_SECONDS, or
    when it was created during a regular session that has since closed: sent
    now, a DAY order would be queued for the next session. An order created
    outside a regular session is checked for age only. An unknown creation
    time is not refused (the worker reads it from the event row).
    """
    from backend.integrations.alpaca_outbox import resolve_order_intent
    from backend.utils.market_hours import ET, is_market_open, market_close_time

    intent, _basis = resolve_order_intent(_flat_payload(payload))
    created = _as_utc(created_at)
    if intent == "exit" or created is None:
        return None
    age = max(0.0, (now - created).total_seconds())
    if age > ENTRY_DISPATCH_MAX_AGE_SECONDS:
        return ("entry_stale",
                f"order age {age:.0f}s exceeds the {ENTRY_DISPATCH_MAX_AGE_SECONDS:.0f}s "
                "entry dispatch limit")
    if is_market_open(created):
        day = created.astimezone(ET).date()
        session_end = datetime.combine(day, market_close_time(day), tzinfo=ET)
        if now >= session_end:
            return ("entry_session_closed",
                    f"created in the regular session that closed at {session_end.isoformat()}")
    return None


def dispatch_lifecycle_status() -> dict[str, Any] | None:
    """Review NB4: the running outbox worker's lifecycle counts, None when none runs.

    The organism engine's status carries it (``order_dispatch_lifecycle``), so
    the paper monitor, the live-process runtime snapshot and the daily evidence
    read it.
    """
    worker = _outbox_worker
    return worker.dispatch_lifecycle_status() if worker is not None else None


def finalized_order_attachment_alert(order: Any, *, previous_filled_qty: Decimal,
                                     cumulative_filled_qty: Decimal,
                                     broker_order_id: Any) -> dict[str, Any] | None:
    """Audit 2026-10-05 C04-01 (review NB1): broker activity on a row this lifecycle finalized.

    The absence proof leaves a residual race: a POST the broker processes even
    later than the confirming lookup. Such an order surfaces as a fill, or a
    broker order id, for a row finalized as never placed, after the engine may
    have released its entry. ``apply_order_fill_snapshot`` (every fill
    ingress) calls this before it stages the update; it returns the CRITICAL to
    log, or None. Only new information pages: a larger cumulative fill, or the
    first broker id.
    """
    attributes = getattr(order, "attributes", None)
    record = attributes.get(DEAD_LETTER_ATTRIBUTE) if isinstance(attributes, dict) else None
    if not isinstance(record, dict) or record.get("state") != DEAD_LETTER_STATE_FINALIZED:
        return None
    if cumulative_filled_qty > previous_filled_qty:
        kind, headline = "fill", "FILL ATTACHED TO A FINALIZED ORDER"
    elif broker_order_id and not getattr(order, "broker_order_id", None):
        kind, headline = "acknowledgement", "BROKER ORDER ATTACHED TO A FINALIZED ORDER"
    else:
        return None
    worker = _outbox_worker
    if worker is not None:
        worker._count_lifecycle("finalized_order_attached", kind)
    absence = record.get("absence") if isinstance(record.get("absence"), dict) else {}
    return {
        "message": (headline + ": the outbox finalized this order as never placed after two "
                    "order-not-found answers, but the broker reports it; the engine may have "
                    "released its entry; reconcile the order and the position"),
        "fields": {
            "order_id": str(getattr(order, "id", "")), "symbol": getattr(order, "symbol", None),
            "side": getattr(order, "side", None),
            "client_order_id": getattr(order, "client_idempotency_key", None),
            "broker_order_id": broker_order_id, "row_status": getattr(order, "status", None),
            "finalized_status": record.get("terminal_status"),
            "finalized_checked_at": absence.get("checked_at"),
            "outbox_event_id": record.get("outbox_event_id"),
            "previous_filled_qty": str(previous_filled_qty),
            "cumulative_filled_qty": str(cumulative_filled_qty),
        },
    }


# Audit 2026-10-05 C01-01: a refused exit's row status, and the statuses a
# refusal never overwrites.
_REFUSED_ORDER_STATUS = "rejected"
_TERMINAL_ORDER_STATUSES = frozenset({
    "filled", "canceled", "cancelled", "expired", "rejected", "replaced", "failed",
})
_OUTCOME_NOTES = {
    "order_row_already_terminal": " (order row was already terminal and is unchanged)",
    "order_row_missing": " (no order row found for this event)",
}


def _refusal_headline(reason: str, outcome: str) -> str:
    """CRITICAL headline for a refused exit (the watchdog pages on CRITICAL).

    A duplicate exit (position already flat, normally because an earlier exit
    filled) reads differently from refusals where shares or a short position
    remain, so an operator can tell "already done" from "needs a look".
    """
    if outcome == "order_row_has_broker_evidence":
        return ("EXIT REFUSAL CONFLICTS WITH BROKER EVIDENCE, order row left unchanged: "
                "reconcile it against the broker")
    if reason == "exit_position_flat":
        return "DUPLICATE EXIT SUPPRESSED AT DISPATCH, not sent (position already flat)"
    if reason == "broker_rejected_insufficient_qty":
        return "ORDER REJECTED BY BROKER (insufficient qty), not retried"
    return "EXIT ORDER REFUSED AT DISPATCH, not sent"


def dlq_exposure_alert(event: dict[str, Any], error_result: dict[str, Any]) -> dict[str, Any] | None:
    """Audit 2026-09-30 EXE-04: page on dead-lettered exits and ambiguous submissions.

    A dead-lettered sell (an exit in long-only mode) can leave a position open,
    and an ambiguous submission may still be live at the broker. Both need an
    operator; ordinary rejected entries do not. The returned message is logged
    at CRITICAL, which the paper watchdog's critical-log monitor turns into an
    attention event. Client-key reconciliation of the order row is unchanged.
    """
    if (error_result or {}).get("dispatch_expired"):
        # Audit 2026-10-05 C01-04: an entry refused before dispatch (never an
        # exit) was not sent; a declared short entry must not page as an exit.
        return None
    payload = event.get("payload") if isinstance(event, dict) else None
    payload = payload if isinstance(payload, dict) else {}
    if isinstance(payload.get("payload"), dict):
        payload = {**payload, **payload["payload"]}
    side = str(payload.get("side") or "").lower()
    key = str(payload.get("client_key") or payload.get("client_order_id") or "")
    lowered = key.lower()
    is_exit = side == "sell" or any(tag in lowered for tag in ("exit", "flatten", "close"))
    ambiguous = bool((error_result or {}).get("submission_ambiguous"))
    if not (is_exit or ambiguous):
        return None
    headline = "EXIT ORDER DEAD-LETTERED" if is_exit else "ORDER SUBMISSION AMBIGUOUS"
    return {
        "message": f"{headline}: reconcile against the broker; the position may still be open",
        "fields": {
            "event_id": event.get("id") if isinstance(event, dict) else None,
            "symbol": payload.get("symbol"),
            "side": side or None,
            "qty": payload.get("qty"),
            "client_key": key or None,
            "ambiguous": ambiguous,
            "error": str((error_result or {}).get("error", ""))[:200],
        },
    }


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
    # V12 W80 (BB5-F1): also start the periodic prune loop.  The
    # prune helper was added in W74 but never wired into the
    # production startup path — the V12 external auditor caught
    # this exactly: helper-plus-passing-test, one layer above the
    # actual wiring gap, leaving the live outbox at 1398 rows.
    # Retention default 30 days; interval 24h; both env-overrideable.
    try:
        max_age_days = int(os.environ.get(
            "OUTBOX_RETENTION_DAYS", "30",
        ))
    except (ValueError, TypeError):
        max_age_days = 30
    try:
        interval_seconds = float(os.environ.get(
            "OUTBOX_PRUNE_INTERVAL_SECONDS", str(24 * 60 * 60),
        ))
    except (ValueError, TypeError):
        interval_seconds = 24 * 60 * 60
    await worker.start_prune_loop(
        max_age_days=max_age_days,
        interval_seconds=interval_seconds,
    )
    # Audit 2026-10-05 C04-01: dead letters are settled against the broker.
    await worker.start_dead_letter_loop()
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
