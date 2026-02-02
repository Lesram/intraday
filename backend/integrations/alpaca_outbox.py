"""
Outbox Event Dispatcher for Alpaca Integration

This module handles outbox events for order submission and routing them to
the appropriate broker (mock or Alpaca) based on configuration flags.
"""

import asyncio
from datetime import datetime
import os
from typing import Any
from zoneinfo import ZoneInfo

from backend.config import get_settings
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


def get_smart_tif(requested_tif: str | None = None) -> str:
    """
    Determine appropriate Time In Force based on market hours.

    During regular market hours (9:30 AM - 4:00 PM ET Mon-Fri), use 'day'.
    Outside market hours, use 'gtc' to prevent orders from expiring before they can fill.

    Args:
        requested_tif: TIF explicitly requested by user (if any)

    Returns:
        'day' or 'gtc' based on market hours
    """
    # If user explicitly requested a TIF, honor it
    if requested_tif and requested_tif.lower() != 'day':
        return requested_tif.lower()

    try:
        # Get current time in Eastern Time
        et_tz = ZoneInfo('America/New_York')
        now_et = datetime.now(et_tz)

        # Check if weekend
        weekday = now_et.weekday()
        if weekday >= 5:  # Saturday (5) or Sunday (6)
            logger.debug("Market closed (weekend), using TIF=gtc")
            return 'gtc'

        # Check market hours (9:30 AM - 4:00 PM ET)
        current_time = now_et.time()
        market_open = current_time.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = current_time.replace(hour=16, minute=0, second=0, microsecond=0)

        is_market_hours = market_open <= current_time <= market_close

        tif = 'day' if is_market_hours else 'gtc'

        logger.debug("Smart TIF selection",
                    current_time_et=current_time.isoformat(),
                    is_market_hours=is_market_hours,
                    selected_tif=tif)

        return tif

    except Exception as e:
        # Fallback to 'gtc' if anything goes wrong (safer option)
        logger.warning("Error determining smart TIF, defaulting to gtc",
                      error=str(e))
        return 'gtc'


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
