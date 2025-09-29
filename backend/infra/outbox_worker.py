"""
Outbox Background Worker

This module implements an async background worker that processes outbox events
in FIFO order, handling broker order submissions and status updates.
"""

import asyncio
import json
import random
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from backend.config import get_settings
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


class OutboxWorker:
    """
    Background worker for processing outbox events.
    
    Polls outbox_events table for pending events and processes them in FIFO order.
    Supports exponential backoff, jitter, and dead letter queue (DLQ) handling.
    """
    
    def __init__(
        self, 
        sessionmaker,
        poll_interval: float = 1.0,
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
        self._task: Optional[asyncio.Task] = None
        self.settings = get_settings()
        self.use_mock_broker = getattr(self.settings, 'USE_MOCK_BROKER', True)
        
        logger.info("OutboxWorker initialized",
                   poll_interval=poll_interval,
                   max_retries=max_retries,
                   use_mock_broker=self.use_mock_broker)
    
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
        
        logger.info("OutboxWorker stopped")
    
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
                
                # Back off on errors to avoid tight error loops
                await asyncio.sleep(self.poll_interval * 2)
        
        logger.info("Outbox dispatcher stopped")
    
    async def _get_pending_events(self) -> List[Dict[str, Any]]:
        """
        Get pending outbox events in FIFO order.
        
        Returns:
            List of pending events, oldest first
        """
        try:
            # Create session and outbox repo for this operation
            async with self.sessionmaker() as session:
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
            logger.error("Failed to get pending events",
                        error=str(e),
                        error_type=type(e).__name__)
            return []
    
    async def _process_event(self, event: Dict[str, Any]):
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
                # Handle failure with retry logic
                await self._handle_event_failure(event, result)
                
        except Exception as e:
            logger.error("Error processing event",
                        event_id=event_id,
                        topic=topic,
                        error=str(e),
                        error_type=type(e).__name__)
            
            # Handle unexpected errors
            await self._handle_event_failure(event, {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            })
    
    async def _process_order_submitted(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process order.submitted event by calling broker.
        
        Args:
            payload: Order submission payload
            
        Returns:
            Processing result
        """
        order_id = payload.get("order_id")
        symbol = payload.get("symbol")
        side = payload.get("side")
        qty = payload.get("qty")
        
        logger.info("Processing order submission",
                   order_id=order_id,
                   symbol=symbol,
                   side=side,
                   qty=qty,
                   use_mock_broker=self.use_mock_broker)
        
        try:
            if self.use_mock_broker:
                # Simulate broker order submission
                result = await self._simulate_broker_order(payload)
            else:
                # Real broker order submission
                result = await self._submit_real_broker_order(payload)
            
            # Update order status in database
            if result.get("success", False):
                await self._update_order_status(
                    order_id=order_id,
                    status="submitted",
                    broker_order_id=result.get("broker_order_id"),
                    details=result
                )
            
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
    
    async def _simulate_broker_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate broker order submission for testing.
        
        Args:
            payload: Order payload
            
        Returns:
            Simulated broker result
        """
        # Simulate processing time
        await asyncio.sleep(0.1)
        
        order_id = payload.get("order_id")
        symbol = payload.get("symbol")
        
        # Generate mock broker order ID
        broker_order_id = f"MOCK_{symbol}_{int(time.time())}"
        
        # Simulate occasional failures for testing
        if random.random() < 0.05:  # 5% failure rate
            return {
                "success": False,
                "error": "Simulated broker error",
                "order_id": order_id
            }
        
        logger.info("Mock broker order submitted",
                   order_id=order_id,
                   broker_order_id=broker_order_id,
                   symbol=symbol)
        
        return {
            "success": True,
            "broker_order_id": broker_order_id,
            "status": "accepted",
            "broker": "mock"
        }
    
    async def _submit_real_broker_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
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
        broker_order_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Update order status in database.
        
        Args:
            order_id: Internal order ID
            status: New order status
            broker_order_id: Broker order ID (if available)
            details: Additional status details
        """
        try:
            # This would typically update the orders table
            # For now, just log the status update
            logger.info("Order status updated",
                       order_id=order_id,
                       status=status,
                       broker_order_id=broker_order_id,
                       details=details)
            
            # In a real implementation, you'd do something like:
            # await self.orders_repo.update_status(order_id, status, broker_order_id, details)
            
        except Exception as e:
            logger.error("Failed to update order status",
                        order_id=order_id,
                        status=status,
                        error=str(e))
    
    async def _mark_event_succeeded(self, event_id: str, result: Dict[str, Any]):
        """
        Mark outbox event as successfully processed.
        
        Args:
            event_id: Event ID
            result: Processing result
        """
        try:
            import uuid
            event_uuid = uuid.UUID(event_id)
            
            async with self.sessionmaker() as session:
                from backend.infra.outbox import OutboxRepo
                outbox_repo = OutboxRepo(session)
                await outbox_repo.mark_sent(event_id=event_uuid)
                await session.commit()
            
        except Exception as e:
            logger.error("Failed to mark event as succeeded",
                        event_id=event_id,
                        error=str(e))
    
    async def _handle_event_failure(self, event: Dict[str, Any], error_result: Dict[str, Any]):
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
            
            next_retry_at = datetime.utcnow() + timedelta(seconds=total_delay)
            
            try:
                import uuid
                event_uuid = uuid.UUID(event_id)
                error_message = error_result.get("error", "Unknown error")
                
                async with self.sessionmaker() as session:
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
                logger.error("Failed to schedule retry",
                            event_id=event_id,
                            error=str(e))
    
    async def _move_to_dlq(self, event: Dict[str, Any], error_result: Dict[str, Any]):
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
                from backend.infra.outbox import OutboxRepo
                outbox_repo = OutboxRepo(session)
                await outbox_repo.mark_failed(
                    event_id=event_uuid,
                    attempts=attempts,
                    error_message=error_message
                )
                
                # Optionally, create a DLQ entry for manual inspection
                dlq_payload = {
                    "original_event": event,
                    "final_error": error_result,
                    "failed_at": datetime.utcnow().isoformat(),
                    "retry_count": attempts
                }
                
                await outbox_repo.enqueue(
                    topic="dlq.failed_event",
                    payload=dlq_payload
                )
                await session.commit()
            
        except Exception as e:
            logger.error("Failed to move event to DLQ",
                        event_id=event_id,
                        error=str(e))


# Global worker instance
_outbox_worker: Optional[OutboxWorker] = None


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
    
    _outbox_worker = OutboxWorker(
        sessionmaker=sessionmaker,
        poll_interval=1.0,  # Poll every second
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


def get_outbox_worker() -> Optional[OutboxWorker]:
    """Get the global outbox worker instance."""
    return _outbox_worker