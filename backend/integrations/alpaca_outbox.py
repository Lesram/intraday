"""
Outbox Event Dispatcher for Alpaca Integration

This module handles outbox events for order submission and routing them to
the appropriate broker (mock or Alpaca) based on configuration flags.

Audit 2026-10-05 (C01-01): exit guard in the real-broker path. An exit sell is
never sent beyond the long position the broker still has free, because a
delayed or retried exit could otherwise open a short. The exit is first looked
up by its persisted client key; one that already reached the broker is
attached and never sent again. A refused exit is returned as
``dispatch_refused`` and the outbox worker finalizes it; a guard read that
fails returns ``retryable`` and nothing is sent. Entries that reach this
dispatcher are sent exactly as before; the outbox worker refuses stale or
after-session entries before they get here (C01-04).

Audit 2026-10-05 (C04-01): ``probe_order_absence`` is the read-only client-key
lookup the outbox worker uses to prove that a dead-lettered order never reached
the broker. Only a definitive 404 counts as absent.
"""

import asyncio
from datetime import datetime
from decimal import Decimal, InvalidOperation
import os
from typing import Any, NamedTuple

from backend.config import get_settings
from backend.integrations.alpaca_broker import (
    BrokerAcknowledgementUnresolved,
    _valid_order_acknowledgement,
)
from backend.utils.logger import get_structured_logger
from backend.utils.market_hours import ET, is_market_open

logger = get_structured_logger(__name__)

# Audit 2026-10-05 C01-01: order row status of a refused exit. Allowed by
# ck_orders_status and an accountable terminal state for close accounting.
REFUSED_ORDER_STATUS = "rejected"


def _long_only() -> bool:
    """``ORGANISM_LONG_ONLY``, parsed exactly as the organism engine parses it."""
    return os.getenv("ORGANISM_LONG_ONLY", "True").lower() in ("1", "true", "yes")


def resolve_order_intent(event_data: dict[str, Any]) -> tuple[str | None, str]:
    """Return ``(intent, basis)``: intent is 'exit', 'entry' or None (undeclared).

    Declared intent wins. OrderService writes ``reduce_only`` and ``intent``
    (``entry`` marks the organism's own non-exit orders, such as a declared
    short entry), and the close-position routes mark
    ``attributes.close_position``. An order that declares nothing (a manual
    API order, or an event queued before these fields existed) falls back to
    the long-only rule: a sell can only reduce a long.
    """
    attributes = event_data.get("attributes")
    if (event_data.get("reduce_only") is True or event_data.get("intent") == "exit"
            or (isinstance(attributes, dict) and attributes.get("close_position") is True)):
        return "exit", "declared"
    if event_data.get("intent") == "entry":
        return "entry", "declared"
    if _long_only() and str(event_data.get("side") or "").strip().lower() == "sell":
        return "exit", "long_only_side"
    return None, "undeclared"


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("invalid quantity")
    parsed = Decimal(str(value))
    if not parsed.is_finite():
        raise ValueError("invalid quantity")
    return parsed


def broker_long_position(position: Any) -> tuple[str, Decimal]:
    """``(state, free_long_qty)`` for the broker's position in one symbol.

    ``state`` is 'flat' (no position, which the broker reports as a 404, or a
    zero quantity), 'long' or 'short'. The free long quantity is Alpaca's
    ``qty_available`` (shares not held by open sell orders), else ``qty``,
    capped at ``qty``; it is 0 unless the position is long. A malformed body
    raises ValueError, so the caller treats it as a failed read.
    """
    if position is None:
        return "flat", Decimal(0)
    if not isinstance(position, dict):
        raise ValueError("malformed position")
    try:
        qty = _decimal(position.get("qty"))
        raw_available = position.get("qty_available")
        available = qty if raw_available in (None, "") else _decimal(raw_available)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("malformed position quantity") from exc
    side = position.get("side")
    if side is not None and (not isinstance(side, str) or side.lower() not in ("long", "short")):
        raise ValueError("malformed position side")
    if qty == 0:
        return "flat", Decimal(0)
    if qty > 0 and (side is None or side.lower() == "long"):
        return "long", max(Decimal(0), min(qty, available))
    return "short", Decimal(0)


def _exit_refusal(symbol: Any, qty: int, position: Any, state: str,
                  available: Decimal) -> tuple[str, str]:
    """``(reason, detail)`` for an exit whose order qty exceeds the free long qty."""
    if state == "flat":
        return ("exit_position_flat",
                f"the broker has no {symbol} position (already flat, so an earlier exit has "
                f"most likely filled); order qty {qty}")
    if state == "short":
        return ("exit_position_short",
                f"the broker {symbol} position is short (qty={position.get('qty')}); "
                f"selling {qty} would add to it")
    return ("exit_exceeds_free_long_position",
            f"free long {symbol} shares {available} < order qty {qty} (broker qty="
            f"{position.get('qty')}, qty_available={position.get('qty_available')}); other "
            "open orders hold the rest or the position is smaller; sending it could open a short")


def is_insufficient_qty_rejection(exc: BaseException) -> bool:
    """Alpaca's definitive 'insufficient qty' rejection (a non-429 4xx)."""
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int) or not 400 <= status < 500 or status == 429:
        return False
    return "insufficient qty" in str(getattr(exc, "detail", None) or exc).lower()


def _refused(event_data: dict[str, Any], *, reason: str, detail: str, intent: str | None,
             message: str | None = None) -> dict[str, Any]:
    """Definitive outcome: nothing is live at the broker and nothing is retried."""
    return {
        "success": False,
        "dispatch_refused": True,
        "status": REFUSED_ORDER_STATUS,
        "broker": "alpaca",
        "broker_order_id": None,
        "order_id": event_data.get("order_id"),
        "intent": intent,
        "refusal_reason": reason,
        "refusal_detail": detail,
        "error": f"DISPATCH_REFUSED:{reason}: {detail}",
        "message": message or f"Order not sent: {detail}",
    }


def _guard_unavailable(event_data: dict[str, Any], stage: str, exc: Exception) -> dict[str, Any]:
    """Nothing was sent and the event stays retryable.

    The error names only the stage and exception type, never broker text, so
    the worker's validation-keyword check cannot dead-letter it.
    """
    logger.error("Exit guard could not confirm the order is safe to send; not sent",
                 order_id=event_data.get("order_id"), symbol=event_data.get("symbol"),
                 side=event_data.get("side"), stage=stage, error=str(exc),
                 error_type=type(exc).__name__)
    return {
        "success": False,
        "retryable": True,
        "status": "failed",
        "broker": "alpaca",
        "broker_order_id": None,
        "order_id": event_data.get("order_id"),
        "error": f"dispatch_guard_unavailable:{stage}:{type(exc).__name__}",
        "message": "Order held: the broker could not confirm that it is safe to send",
    }


class _GuardOutcome(NamedTuple):
    result: dict[str, Any] | None = None  # return this instead of sending
    existing: dict[str, Any] | None = None  # already at the broker: attach it


async def _exit_send_guard(broker_client: Any, event_data: dict[str, Any], *, symbol: Any,
                           side: Any, qty: int, client_key: str) -> _GuardOutcome:
    """Audit 2026-10-05 C01-01: right before the POST, an exit sell must not open a short.

    Orders that are not exit sells (entries, buy-to-cover) pass untouched.
    """
    intent, basis = resolve_order_intent(event_data)
    if intent != "exit" or str(side or "").strip().lower() != "sell":
        return _GuardOutcome()

    # Client key first: an earlier attempt may have reached the broker (a lost
    # response, or a crash mid-request). Such an order is attached, never
    # refused or sent again. Only a definitive 404 means it was never placed.
    try:
        existing = await broker_client.find_order_by_client_order_id(client_key)
    except BrokerAcknowledgementUnresolved:
        raise
    except Exception as exc:  # noqa: BLE001 - any lookup failure holds the exit
        return _GuardOutcome(result=_guard_unavailable(event_data, "client_order_lookup", exc))
    if existing is not None:
        if not _valid_order_acknowledgement(existing, client_key, lookup=True):
            raise BrokerAcknowledgementUnresolved(client_key, "lookup_not_confirmed")
        logger.info("Exit already at the broker; attaching it without a new submission",
                    order_id=event_data.get("order_id"), client_order_id=client_key,
                    broker_order_id=existing.get("id"), status=existing.get("status"))
        return _GuardOutcome(existing=existing)

    # Never more than the long position the broker still has free. Refused,
    # not clamped: a smaller order would no longer match its order row.
    try:
        position = await broker_client.get_position(symbol)
        state, available = broker_long_position(position)
    except Exception as exc:  # noqa: BLE001 - an unknown position holds the exit
        return _GuardOutcome(result=_guard_unavailable(event_data, "position_read", exc))
    if available < qty:
        reason, detail = _exit_refusal(symbol, qty, position, state, available)
        logger.warning("Exit refused at dispatch", order_id=event_data.get("order_id"),
                       symbol=symbol, qty=qty, position_state=state,
                       available=str(available), reason=reason, basis=basis)
        return _GuardOutcome(result=_refused(event_data, reason=reason, detail=detail,
                                             intent=intent))
    return _GuardOutcome()


async def probe_order_absence(client_order_id: str) -> tuple[str, dict[str, Any] | None, str]:
    """Audit 2026-10-05 C04-01: is the order with this persisted client key at the broker?

    Returns ``(state, order, detail)``. ``state`` is 'absent' only on a
    definitive 404 for the exact client key; 'present' (with the broker's
    order) when the broker confirms that key; 'unknown' for anything else: a
    transport error or timeout, the open breaker, a 5xx, missing credentials,
    or a 200 that does not confirm the key. Read-only: never submits.
    """
    from backend.integrations.alpaca_broker import get_alpaca_broker_client

    try:
        found = await get_alpaca_broker_client().find_order_by_client_order_id(client_order_id)
    except BrokerAcknowledgementUnresolved as exc:
        return "unknown", None, f"lookup_not_confirmed:{exc.reason}"
    except Exception as exc:  # noqa: BLE001 - only a definitive 404 proves absence
        return "unknown", None, f"lookup_failed:{type(exc).__name__}"
    if found is None:
        return "absent", None, "not_found"
    return "present", found, "found"


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

            if event_data.get("_broker_ack_lookup_only"):
                # A mock toggle cannot acknowledge an unresolved real order.
                result = await self._dispatch_to_alpaca_broker(event_data)
            elif self.use_mock_broker:
                # Use mock broker processing
                result = await self._dispatch_to_mock_broker(event_data)
            else:
                # Use real Alpaca broker
                result = await self._dispatch_to_alpaca_broker(event_data)

            logger.info("Order event dispatch completed",
                       order_id=order_id,
                       success=result.get("success", False),
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

            lookup_only = bool(event_data.get("_broker_ack_lookup_only"))
            logger.info("Reconciling Alpaca order acknowledgement" if lookup_only else "Placing order with Alpaca",
                       operation="lookup_only" if lookup_only else "submit",
                       symbol=symbol,
                       side=side,
                       qty=qty,
                       order_type=order_type,
                       limit_price=limit_price,
                       stop_price=stop_price,
                       requested_tif=requested_tif,
                       selected_tif=tif)

            if not isinstance(client_key, str) or not client_key.strip():
                raise BrokerAcknowledgementUnresolved(None, "missing_persisted_client_order_id")

            # Once acknowledgement is uncertain, retries only read the exact
            # persisted identity; neither restart nor lookup failure may POST.
            already_at_broker = False
            if event_data.get("_broker_ack_lookup_only"):
                alpaca_result = await broker_client.reconcile_order_acknowledgement(client_key)
            else:
                # Audit 2026-10-05 C01-01: exit sells must not open a short.
                guard = await _exit_send_guard(
                    broker_client, event_data,
                    symbol=symbol, side=side, qty=qty, client_key=client_key,
                )
                if guard.result is not None:
                    return guard.result
                if guard.existing is not None:
                    already_at_broker = True
                    alpaca_result = guard.existing
                else:
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

            logger.info("Alpaca broker acknowledgement confirmed",
                       operation="lookup_only" if lookup_only else "submit",
                       order_id=event_data.get("order_id"),
                       broker_order_id=broker_order_id,
                       status=status,
                       symbol=symbol,
                       tif=tif)

            if lookup_only:
                message = "Order acknowledgement reconciled"
            elif already_at_broker:
                message = "Order already at Alpaca; attached without a new submission"
            else:
                message = "Order submitted to Alpaca"
            return {
                "success": True,
                "broker_order_id": broker_order_id,
                "status": status,
                "broker": "alpaca",
                "message": message,
                "alpaca_response": alpaca_result
            }

        except BrokerAcknowledgementUnresolved as e:
            return {
                "success": False,
                "submission_ambiguous": True,
                "client_order_id": e.client_order_id,
                "broker_order_id": None,
                "status": "reconciliation_required",
                "broker": "alpaca",
                "error": e.reason,
            }
        except Exception as e:
            logger.error("Alpaca broker dispatch failed",
                        order_id=event_data.get("order_id"),
                        error=str(e),
                        error_type=type(e).__name__)

            intent, _ = resolve_order_intent(event_data)
            exit_sell = (intent == "exit"
                         and str(event_data.get("side") or "").strip().lower() == "sell")
            if exit_sell and is_insufficient_qty_rejection(e):
                # Audit 2026-10-05 C01-01: a definitive rejection of an exit sell.
                # Retrying it turns into a short sale once another sell for the
                # same shares fills, so the order is finalized and never retried.
                # Entries and buy-to-cover keep the normal failure flow below.
                detail = f"the broker rejected the order: {str(getattr(e, 'detail', None) or e)[:300]}"
                return _refused(event_data,
                                reason="broker_rejected_insufficient_qty",
                                detail=detail, intent=intent,
                                message=f"Order rejected by Alpaca, not retried: {detail}")

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
