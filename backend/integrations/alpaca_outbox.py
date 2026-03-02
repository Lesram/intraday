"""
Outbox Event Dispatcher for Alpaca Integration

This module handles outbox events for order submission and routing them to
the appropriate broker (mock or Alpaca) based on configuration flags.
"""

import asyncio
from datetime import datetime
import os
from typing import Any

from backend.config import get_settings
from backend.utils.logger import get_structured_logger
from backend.utils.market_hours import ET, is_market_open

logger = get_structured_logger(__name__)


def get_smart_tif(requested_tif: str | None = None) -> str:
    """
    Determine appropriate Time In Force based on market hours.

    During regular market hours (9:30 AM - 4:00 PM ET Mon-Fri), use 'day'.
    Outside market hours, also default to 'day' for an intraday system to
    prevent unwanted overnight exposure.  GTC is only used when explicitly
    requested via ``requested_tif``.

    Args:
        requested_tif: TIF explicitly requested by caller (if any).
                       Pass 'gtc' explicitly to allow GTC orders.

    Returns:
        'day' (default) or 'gtc' (only when explicitly requested)
    """
    # If caller explicitly requested a TIF, honor it
    if requested_tif and requested_tif.lower() != 'day':
        return requested_tif.lower()

    try:
        now_et = datetime.now(ET)
        in_market = is_market_open()

        # For an intraday system, ALWAYS default to 'day' to prevent
        # unwanted overnight exposure.  Outside hours the order will be
        # queued by the broker for the next session.
        tif = 'day'

        if not in_market:
            logger.info(
                "Off-hours order: using TIF=day to prevent overnight exposure "
                "(time=%s, weekday=%d). Pass requested_tif='gtc' to override.",
                now_et.time().isoformat(), now_et.weekday(),
            )

        logger.debug("Smart TIF selection",
                    current_time_et=now_et.time().isoformat(),
                    is_market_hours=in_market,
                    selected_tif=tif)

        return tif

    except Exception as e:
        # Fallback to 'day' (safer for intraday — no overnight exposure)
        logger.warning("Error determining smart TIF, defaulting to day",
                      error=str(e))
        return 'day'


class AlpacaOutboxDispatcher:
    """
    Dispatcher for routing outbox events to Alpaca broker or mock.

    Handles order.submitted events from the outbox and routes them to the
    appropriate broker based on USE_MOCK_BROKER setting.
    """

    def __init__(self):
        """Initialize the outbox dispatcher."""
        self.settings = get_settings()

        # Check environment variable directly to avoid cached settings issues
        use_mock_env = os.getenv('USE_MOCK_BROKER', 'false').lower() in ('true', '1', 'yes')
        use_mock_setting = getattr(self.settings, 'USE_MOCK_BROKER', False)

        # Prefer environment variable over settings
        self.use_mock_broker = use_mock_env or use_mock_setting

        logger.info("AlpacaOutboxDispatcher initialized",
                   use_mock_broker=self.use_mock_broker,
                   from_env=use_mock_env,
                   from_settings=use_mock_setting)

    async def dispatch_order_event(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """
        Dispatch order submission event to appropriate broker.

        Args:
            event_data: Order event data from outbox

        Returns:
            Dict with dispatch result
        """
        try:
            order_id = event_data.get("order_id")
            symbol = event_data.get("symbol")
            side = event_data.get("side")
            qty = event_data.get("qty")
            event_data.get("order_type", "market")
            event_data.get("tif", "day")
            event_data.get("client_key")

            logger.info("Dispatching order event",
                       order_id=order_id,
                       symbol=symbol,
                       side=side,
                       qty=qty,
                       use_mock_broker=self.use_mock_broker)

            if self.use_mock_broker:
                # Use mock broker processing
                result = await self._dispatch_to_mock_broker(event_data)
            else:
                # Use real Alpaca broker
                result = await self._dispatch_to_alpaca_broker(event_data)

            logger.info("Order event dispatched successfully",
                       order_id=order_id,
                       broker_order_id=result.get("broker_order_id"),
                       status=result.get("status"))

            return result

        except Exception as e:
            logger.error("Failed to dispatch order event",
                        event_data=event_data,
                        error=str(e),
                        error_type=type(e).__name__)
            return {
                "success": False,
                "error": str(e),
                "broker_order_id": None,
                "status": "failed"
            }

    async def _dispatch_to_mock_broker(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """
        Mock broker dispatch for testing/development.

        Args:
            event_data: Order event data

        Returns:
            Mock broker response
        """
        # Simulate processing delay
        await asyncio.sleep(0.1)

        order_id = event_data.get("order_id")
        symbol = event_data.get("symbol")

        # Generate mock broker order ID
        mock_broker_id = f"MOCK_{symbol}_{order_id[:8]}"

        logger.info("Mock broker order processed",
                   order_id=order_id,
                   mock_broker_id=mock_broker_id,
                   symbol=symbol)

        return {
            "success": True,
            "broker_order_id": mock_broker_id,
            "status": "accepted",
            "broker": "mock",
            "message": "Order submitted to mock broker"
        }

    async def _dispatch_to_alpaca_broker(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """
        Real Alpaca broker dispatch.

        Args:
            event_data: Order event data

        Returns:
            Alpaca broker response
        """
        try:
            from backend.integrations.alpaca_broker import get_alpaca_broker_client

            # Get Alpaca broker client
            broker_client = get_alpaca_broker_client()

            # Extract order parameters
            symbol = event_data.get("symbol")
            side = event_data.get("side")
            qty = int(float(event_data.get("qty", 0)))  # Convert to int shares
            order_type = event_data.get("order_type", "market")
            limit_price = event_data.get("limit_price")
            stop_price = event_data.get("stop_price")

            # Use smart TIF selection based on market hours
            requested_tif = event_data.get("tif")
            tif = get_smart_tif(requested_tif)

            client_key = event_data.get("client_key")

            logger.info("Placing order with Alpaca",
                       symbol=symbol,
                       side=side,
                       qty=qty,
                       order_type=order_type,
                       limit_price=limit_price,
                       stop_price=stop_price,
                       requested_tif=requested_tif,
                       selected_tif=tif)

            # Place order with Alpaca
            alpaca_result = await broker_client.place_order(
                symbol=symbol,
                side=side,
                qty=qty,
                type=order_type,
                tif=tif,
                limit_price=limit_price,
                stop_price=stop_price,
                client_order_id=client_key
            )

            broker_order_id = alpaca_result.get("id")
            status = alpaca_result.get("status", "unknown")

            logger.info("Alpaca broker order placed",
                       order_id=event_data.get("order_id"),
                       broker_order_id=broker_order_id,
                       status=status,
                       symbol=symbol,
                       tif=tif)

            return {
                "success": True,
                "broker_order_id": broker_order_id,
                "status": status,
                "broker": "alpaca",
                "message": "Order submitted to Alpaca",
                "alpaca_response": alpaca_result
            }

        except Exception as e:
            logger.error("Alpaca broker dispatch failed",
                        order_id=event_data.get("order_id"),
                        error=str(e),
                        error_type=type(e).__name__)

            return {
                "success": False,
                "broker_order_id": None,
                "status": "failed",
                "broker": "alpaca",
                "error": str(e),
                "message": f"Alpaca order submission failed: {str(e)}"
            }


# Global dispatcher instance
_outbox_dispatcher: AlpacaOutboxDispatcher | None = None


def get_alpaca_outbox_dispatcher() -> AlpacaOutboxDispatcher:
    """
    Get or create global AlpacaOutboxDispatcher instance.

    Returns:
        AlpacaOutboxDispatcher instance
    """
    global _outbox_dispatcher
    if _outbox_dispatcher is None:
        _outbox_dispatcher = AlpacaOutboxDispatcher()
    return _outbox_dispatcher


# Event handler function for outbox processing
async def handle_order_submitted_event(event_data: dict[str, Any]) -> dict[str, Any]:
    """
    Handle order.submitted outbox event.

    This function is called by the outbox processor when an order.submitted
    event needs to be processed.

    Args:
        event_data: Order event data from outbox

    Returns:
        Processing result
    """
    dispatcher = get_alpaca_outbox_dispatcher()
    return await dispatcher.dispatch_order_event(event_data)
