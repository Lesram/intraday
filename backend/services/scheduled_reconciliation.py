"""
H-20 FIX: Scheduled Position Reconciliation Job

This module provides scheduled execution of position reconciliation
to catch discrepancies between database orders and broker positions.

Usage:
    # In your app startup (main.py or FastAPI lifespan):
    from backend.services.scheduled_reconciliation import start_reconciliation_scheduler
    
    await start_reconciliation_scheduler()
    
    # To stop (on shutdown):
    from backend.services.scheduled_reconciliation import stop_reconciliation_scheduler
    
    await stop_reconciliation_scheduler()

Configuration via environment variables:
    RECONCILIATION_INTERVAL_MINUTES: How often to run (default: 15)
    RECONCILIATION_ENABLED: Set to "false" to disable (default: "true")
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

from backend.infra.db import get_sessionmaker
from backend.integrations.alpaca_broker import AlpacaBrokerClient
from backend.services.position_reconciliation_service import PositionReconciliationService
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Module-level state
_reconciliation_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None


async def run_scheduled_reconciliation() -> dict[str, Any]:
    """
    Execute a single reconciliation check.
    
    Returns summary of reconciliation results.
    """
    try:
        logger.info("H-20: Starting scheduled position reconciliation")
        
        # Create database session
        async_session_maker = get_sessionmaker()
        async with async_session_maker() as session:
            # Create Alpaca client
            alpaca_client = AlpacaBrokerClient()
            
            # Create reconciliation service
            service = PositionReconciliationService(
                db=session,
                alpaca_client=alpaca_client
            )
            
            # Run reconciliation
            summary = await service.get_reconciliation_summary()
            
            # Log results
            logger.info(
                f"H-20: Reconciliation complete - "
                f"Total orders: {summary.get('total_filled_buys', 0)}, "
                f"Open: {summary.get('open_positions', 0)}, "
                f"Closed: {summary.get('closed_positions', 0)}, "
                f"Discrepancies: {summary.get('discrepancy_count', 0)}"
            )
            
            # Alert on discrepancies
            discrepancies = summary.get('discrepancies', [])
            if discrepancies:
                logger.warning(
                    f"H-20: Position discrepancies detected! "
                    f"Count: {len(discrepancies)}"
                )
                for disc in discrepancies[:5]:  # Log first 5
                    logger.warning(
                        f"  - {disc['symbol']}: {disc['reason']} "
                        f"(Order: {disc['order_id']}, Qty: {disc['qty']})"
                    )
                if len(discrepancies) > 5:
                    logger.warning(f"  ... and {len(discrepancies) - 5} more")
            
            return summary
            
    except Exception as e:
        logger.error(f"H-20: Reconciliation job failed: {e}")
        return {"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}


async def _reconciliation_loop(interval_minutes: int) -> None:
    """
    Internal loop that runs reconciliation at specified intervals.

    Audit-J finding J-4 (2026-05-02): _stop_event must be initialized
    by start_reconciliation_scheduler BEFORE create_task, not in the
    loop body. If stop is called between create_task and the loop's
    first line, _stop_event was None → stop_event.set() was a no-op
    → wait_for(timeout=interval) burned the full interval before
    canceling. Now: just enter the loop; _stop_event is already set up.
    """
    global _stop_event

    logger.info(f"H-20: Reconciliation scheduler started (interval: {interval_minutes} minutes)")
    
    while not _stop_event.is_set():
        try:
            await run_scheduled_reconciliation()
        except Exception as e:
            logger.error(f"H-20: Error in reconciliation loop: {e}")
        
        # Wait for interval or stop signal
        try:
            await asyncio.wait_for(
                _stop_event.wait(),
                timeout=interval_minutes * 60
            )
        except asyncio.TimeoutError:
            # Timeout means interval elapsed, continue to next iteration
            pass
    
    logger.info("H-20: Reconciliation scheduler stopped")


async def start_reconciliation_scheduler() -> bool:
    """
    Start the background reconciliation scheduler.
    
    Returns True if scheduler was started, False if disabled or already running.
    """
    global _reconciliation_task
    
    # Check if enabled
    enabled = os.environ.get('RECONCILIATION_ENABLED', 'true').lower()
    if enabled in ('false', '0', 'no'):
        logger.info("H-20: Position reconciliation scheduler is disabled")
        return False
    
    # Check if already running
    if _reconciliation_task is not None and not _reconciliation_task.done():
        logger.warning("H-20: Reconciliation scheduler already running")
        return False
    
    # Get interval from environment
    try:
        interval = int(os.environ.get('RECONCILIATION_INTERVAL_MINUTES', '15'))
    except ValueError:
        interval = 15
        logger.warning(f"H-20: Invalid RECONCILIATION_INTERVAL_MINUTES, using default: {interval}")
    
    # Audit-J finding J-4 (2026-05-02): initialize _stop_event BEFORE
    # create_task so a fast stop_*() right after start_*() works.
    global _stop_event
    _stop_event = asyncio.Event()

    # Start background task
    _reconciliation_task = asyncio.create_task(
        _reconciliation_loop(interval),
        name="position_reconciliation_scheduler"
    )
    
    logger.info(f"H-20: Position reconciliation scheduler started (every {interval} minutes)")
    return True


async def stop_reconciliation_scheduler() -> None:
    """
    Stop the background reconciliation scheduler gracefully.
    """
    global _reconciliation_task, _stop_event
    
    if _stop_event is not None:
        _stop_event.set()
    
    if _reconciliation_task is not None:
        try:
            # Wait for task to complete with timeout
            await asyncio.wait_for(_reconciliation_task, timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("H-20: Reconciliation scheduler did not stop gracefully, cancelling")
            _reconciliation_task.cancel()
            try:
                await _reconciliation_task
            except asyncio.CancelledError:
                pass
        
        _reconciliation_task = None
        _stop_event = None
        
    logger.info("H-20: Position reconciliation scheduler stopped")


def get_scheduler_status() -> dict[str, Any]:
    """
    Get the current status of the reconciliation scheduler.
    """
    global _reconciliation_task
    
    if _reconciliation_task is None:
        return {"status": "not_started", "running": False}
    
    if _reconciliation_task.done():
        exception = _reconciliation_task.exception() if not _reconciliation_task.cancelled() else None
        return {
            "status": "stopped",
            "running": False,
            "error": str(exception) if exception else None
        }
    
    return {"status": "running", "running": True}
