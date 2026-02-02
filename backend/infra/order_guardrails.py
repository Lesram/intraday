"""
Critical Order Guardrails Implementation
Phase 1: Timeouts, Confirmation, and Stale Detection

This module implements immediate safety measures to prevent orders
from lingering indefinitely without confirmation from Alpaca.
"""

import asyncio
from datetime import UTC, datetime, timedelta
import logging
from typing import Any
import uuid

logger = logging.getLogger(__name__)

# Configuration
ALPACA_ORDER_TIMEOUT = 30  # seconds - timeout for order submission
ALPACA_VERIFY_TIMEOUT = 10  # seconds - timeout for order verification
STALE_PENDING_THRESHOLD = 5  # minutes - mark pending orders as failed after this
STALE_ACCEPTED_THRESHOLD = 24  # hours - check accepted orders after this


class OrderConfirmationError(Exception):
    """Raised when order cannot be confirmed on Alpaca."""
    pass


class AlpacaTimeoutError(Exception):
    """Raised when Alpaca API call times out."""
    pass


class OrderGuardrails:
    """
    Critical guardrails for order submission and confirmation.

    Features:
    1. Timeout on Alpaca API calls
    2. Immediate confirmation check after submission
    3. Stale order detection and cleanup
    4. Order status validation
    """

    def __init__(self, alpaca_client, db_session):
        """
        Initialize guardrails.

        Args:
            alpaca_client: Alpaca API client
            db_session: Database session
        """
        self.alpaca_client = alpaca_client
        self.db_session = db_session

    async def submit_order_with_confirmation(
        self,
        order_data: dict[str, Any],
        order_id: uuid.UUID
    ) -> dict[str, Any]:
        """
        Submit order to Alpaca with timeout and immediate confirmation.

        This is the main entry point for submitting orders with guardrails.

        Steps:
        1. Submit order to Alpaca (with timeout)
        2. Extract broker_order_id from response
        3. VERIFY order exists on Alpaca
        4. Return confirmed order details

        Args:
            order_data: Order data to submit
            order_id: Internal order ID

        Returns:
            Dict with broker_order_id and order details

        Raises:
            AlpacaTimeoutError: If submission times out
            OrderConfirmationError: If order cannot be confirmed
        """
        logger.info(f"Submitting order {order_id} with confirmation guardrails")

        # Step 1: Submit with timeout
        try:
            response = await asyncio.wait_for(
                self._submit_to_alpaca(order_data),
                timeout=ALPACA_ORDER_TIMEOUT
            )
        except TimeoutError:
            logger.error(f"Order {order_id} submission timed out after {ALPACA_ORDER_TIMEOUT}s")
            await self._mark_order_failed(order_id, "Alpaca submission timeout")
            raise AlpacaTimeoutError(f"Order submission exceeded {ALPACA_ORDER_TIMEOUT}s")
        except Exception as e:
            logger.error(f"Order {order_id} submission failed: {e}")
            await self._mark_order_failed(order_id, f"Submission error: {str(e)}")
            raise

        # Step 2: Extract broker_order_id
        broker_order_id = response.get('id')
        if not broker_order_id:
            logger.error(f"Order {order_id} response missing broker_order_id")
            await self._mark_order_failed(order_id, "No broker_order_id in response")
            raise OrderConfirmationError("Alpaca response missing order ID")

        logger.info(f"Order {order_id} got broker_order_id: {broker_order_id}")

        # Step 3: VERIFY order exists on Alpaca
        verified = await self._verify_order_exists(broker_order_id)
        if not verified:
            logger.error(f"Order {order_id} confirmation failed - not found on Alpaca")
            await self._mark_order_failed(
                order_id,
                f"Order not confirmed on Alpaca (broker_id: {broker_order_id})"
            )
            raise OrderConfirmationError(
                f"Order {broker_order_id} not found on Alpaca after submission"
            )

        logger.info(f"Order {order_id} confirmed on Alpaca ✅")

        # Step 4: Return confirmed order details
        return {
            'broker_order_id': broker_order_id,
            'status': response.get('status', 'accepted'),
            'symbol': response.get('symbol'),
            'qty': response.get('qty'),
            'side': response.get('side'),
            'order_type': response.get('order_type'),
            'submitted_at': response.get('submitted_at'),
            'confirmed': True
        }

    async def _submit_to_alpaca(self, order_data: dict[str, Any]) -> dict[str, Any]:
        """
        Submit order to Alpaca API.

        Args:
            order_data: Order data

        Returns:
            Alpaca order response
        """
        # Use existing Alpaca client method
        response = await self.alpaca_client.post("/v2/orders", json=order_data)

        if response.status_code not in [200, 201]:
            raise Exception(f"Alpaca returned {response.status_code}: {response.text}")

        return response.json()

    async def _verify_order_exists(self, broker_order_id: str) -> bool:
        """
        Verify order exists on Alpaca after submission.

        Args:
            broker_order_id: Broker order ID to verify

        Returns:
            True if order found, False otherwise
        """
        try:
            response = await asyncio.wait_for(
                self.alpaca_client.get(f"/v2/orders/{broker_order_id}"),
                timeout=ALPACA_VERIFY_TIMEOUT
            )

            if response.status_code == 200:
                logger.info(f"Order {broker_order_id} verified on Alpaca")
                return True
            elif response.status_code == 404:
                logger.warning(f"Order {broker_order_id} not found on Alpaca")
                return False
            else:
                logger.error(f"Unexpected response verifying {broker_order_id}: {response.status_code}")
                return False

        except TimeoutError:
            logger.error(f"Timeout verifying order {broker_order_id}")
            return False
        except Exception as e:
            logger.error(f"Error verifying order {broker_order_id}: {e}")
            return False

    async def _mark_order_failed(
        self,
        order_id: uuid.UUID,
        reason: str
    ) -> None:
        """
        Mark order as failed in database.

        Args:
            order_id: Order ID
            reason: Failure reason
        """
        from sqlalchemy import select

        from backend.infra.schemas import Order

        try:
            query = select(Order).where(Order.id == order_id)
            result = await self.db_session.execute(query)
            order = result.scalar_one_or_none()

            if order:
                order.status = 'failed'
                order.failure_reason = reason
                order.updated_at = datetime.now(UTC)

                self.db_session.add(order)
                await self.db_session.commit()

                logger.info(f"Marked order {order_id} as failed: {reason}")
            else:
                logger.warning(f"Order {order_id} not found in database")

        except Exception as e:
            logger.error(f"Failed to mark order {order_id} as failed: {e}")
            await self.db_session.rollback()

    async def detect_and_cleanup_stale_orders(self) -> dict[str, int]:
        """
        Find and mark stale orders as failed.

        Checks:
        1. Orders in "pending" > 5 minutes → Mark as failed
        2. Orders in "accepted" > 24 hours without broker_order_id → Mark as failed
        3. Orders in "pending" without broker_order_id > 1 minute → Mark as failed

        Returns:
            Dict with counts of orders cleaned up
        """
        from sqlalchemy import and_, select

        from backend.infra.schemas import Order

        logger.info("Starting stale order detection")

        now = datetime.now(UTC)
        pending_cutoff = now - timedelta(minutes=STALE_PENDING_THRESHOLD)
        accepted_cutoff = now - timedelta(hours=STALE_ACCEPTED_THRESHOLD)

        counts = {
            'stale_pending': 0,
            'stale_accepted': 0,
            'no_broker_id': 0
        }

        try:
            # Find stale pending orders
            stale_pending_query = select(Order).where(
                and_(
                    Order.status == 'pending',
                    Order.created_at < pending_cutoff
                )
            )
            result = await self.db_session.execute(stale_pending_query)
            stale_pending = result.scalars().all()

            for order in stale_pending:
                logger.warning(
                    f"Stale pending order detected: {order.id} "
                    f"(created {order.created_at}, age: {now - order.created_at})"
                )
                order.status = 'failed'
                order.failure_reason = f"Order stuck in pending > {STALE_PENDING_THRESHOLD} minutes"
                order.updated_at = now
                self.db_session.add(order)
                counts['stale_pending'] += 1

            # Find accepted orders without broker_order_id
            no_broker_id_query = select(Order).where(
                and_(
                    Order.status.in_(['pending', 'accepted']),
                    Order.broker_order_id.is_(None),
                    Order.created_at < pending_cutoff
                )
            )
            result = await self.db_session.execute(no_broker_id_query)
            no_broker_id_orders = result.scalars().all()

            for order in no_broker_id_orders:
                logger.warning(
                    f"Order without broker_order_id: {order.id} "
                    f"(status: {order.status}, created: {order.created_at})"
                )
                order.status = 'failed'
                order.failure_reason = f"No broker_order_id after {STALE_PENDING_THRESHOLD} minutes"
                order.updated_at = now
                self.db_session.add(order)
                counts['no_broker_id'] += 1

            # Find old accepted orders (may need reconciliation)
            old_accepted_query = select(Order).where(
                and_(
                    Order.status == 'accepted',
                    Order.created_at < accepted_cutoff,
                    Order.broker_order_id.is_not(None)
                )
            )
            result = await self.db_session.execute(old_accepted_query)
            old_accepted = result.scalars().all()

            if old_accepted:
                logger.warning(
                    f"Found {len(old_accepted)} orders accepted > {STALE_ACCEPTED_THRESHOLD}h - "
                    f"may need reconciliation"
                )
                counts['stale_accepted'] = len(old_accepted)

            # Commit changes
            await self.db_session.commit()

            logger.info(
                f"Stale order cleanup complete: "
                f"{counts['stale_pending']} pending, "
                f"{counts['no_broker_id']} without broker_id, "
                f"{counts['stale_accepted']} old accepted"
            )

            return counts

        except Exception as e:
            logger.error(f"Error during stale order detection: {e}")
            await self.db_session.rollback()
            raise


# Standalone function for scheduled job
async def run_stale_order_cleanup():
    """
    Scheduled job to detect and cleanup stale orders.
    Run this every 15 minutes via cron or background task.
    """
    from backend.infra.unified_database import get_db_session
    from backend.integrations.alpaca_client import get_alpaca_client

    async with get_db_session() as session:
        alpaca_client = get_alpaca_client()
        guardrails = OrderGuardrails(alpaca_client, session)

        try:
            counts = await guardrails.detect_and_cleanup_stale_orders()

            # Alert if significant number of stale orders found
            total = counts['stale_pending'] + counts['no_broker_id']
            if total > 0:
                logger.warning(
                    f"⚠️  Stale orders cleaned up: {total} orders marked as failed"
                )
                # Send alert notification
                try:
                    from backend.infra.alerting import AlertSeverity, get_alert_manager
                    alert_manager = get_alert_manager()
                    await alert_manager.send_alert(
                        severity=AlertSeverity.WARNING,
                        title="Stale Orders Detected",
                        message=f"Stale order cleanup: {total} orders marked as failed "
                                f"(stale_pending={counts['stale_pending']}, "
                                f"no_broker_id={counts['no_broker_id']})",
                        source="order_guardrails",
                        metadata={"counts": counts},
                    )
                except Exception as alert_err:
                    logger.debug(f"Could not send alert: {alert_err}")

            return counts

        except Exception as e:
            logger.error(f"Stale order cleanup job failed: {e}")
            raise


if __name__ == "__main__":
    # Test/manual run
    asyncio.run(run_stale_order_cleanup())
