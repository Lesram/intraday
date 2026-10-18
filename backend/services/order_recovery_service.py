"""Bounded recovery of attributable unresolved orders; never submits an order.

Progress is process-local. A restart begins a new sweep; repeated restarts can
delay later rows. Old terminal history and unowned legacy records are excluded.
"""

import asyncio
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import uuid
import weakref

from backend.infra.repositories.orders import OrdersRepo
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)
MAX_REQUESTS = 20
PASS_BUDGET_SECONDS = 10.0
LOOKUP_BUDGET_SECONDS = 2.0
_TERMINAL = {"filled", "canceled", "cancelled", "expired", "rejected", "replaced"}
_STATUS = {
    "new": "submitted",
    "accepted": "accepted",
    "pending_new": "submitting",
    "partially_filled": "partially_filled",
    "filled": "filled",
    "canceled": "cancelled",
    "cancelled": "cancelled",
    "expired": "expired",
    "rejected": "rejected",
    "replaced": "replaced",
    "pending_cancel": "pending_cancel",
    "pending_replace": "pending_replace",
    "held": "held",
    "stopped": "stopped",
    "suspended": "suspended",
    "calculated": "calculated",
    "done_for_day": "done_for_day",
}


@dataclass(frozen=True)
class OrderIdentity:
    id: uuid.UUID
    broker_id: str
    client_key: str
    symbol: str
    side: str
    qty: Decimal

    @classmethod
    def from_order(cls, row):
        return cls(
            row.id, row.broker_order_id, row.client_idempotency_key, row.symbol, row.side, row.qty
        )


def _number(value):
    if isinstance(value, bool):
        raise ValueError("Invalid broker number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid broker number") from None
    if not result.is_finite():
        raise ValueError("Nonfinite broker number")
    return result


def validate_order_snapshot(identity, data):
    """Validate an exact broker snapshot without changing or inferring its state."""
    if not isinstance(data, dict) or (
        data.get("id") != identity.broker_id
        or data.get("client_order_id") != identity.client_key
        or data.get("symbol") != identity.symbol
        or data.get("side") != identity.side
        or _number(data.get("qty")) != identity.qty
    ):
        raise ValueError("Broker snapshot identity mismatch")
    status = _STATUS.get(data.get("status"))
    if status is None or status == "replaced":
        raise ValueError("Unsupported broker status")
    filled = _number(data.get("filled_qty"))
    if filled < 0 or filled > identity.qty:
        raise ValueError("Invalid cumulative fill quantity")
    if status == "filled" and filled != identity.qty:
        raise ValueError("Incomplete quantity for filled status")
    price = data.get("filled_avg_price")
    if filled > 0 and _number(price) <= 0:
        raise ValueError("Invalid cumulative fill price")
    return status, filled, price


class OrderRecoveryService:
    def __init__(self):
        self.cursor = None
        self._lock = asyncio.Lock()

    async def recover(self, session_factory, fetch_order):
        if self._lock.locked():
            return {"state": "already_running", "backlog": True, "attempted": 0}
        async with self._lock:
            result = {
                "state": "complete",
                "attempted": 0,
                "applied": 0,
                "reconciled": 0,
                "errors": 0,
                "changed": 0,
                "unresolved_in_pass": 0,
                "backlog": True,
                "sweep_complete": False,
            }
            try:
                # The wall budget includes DB page reads, row locks and commits,
                # as well as broker lookups. Context exit rolls back cancellation.
                async with asyncio.timeout(PASS_BUDGET_SECONDS):
                    async with session_factory() as session:
                        rows = await OrdersRepo(session).get_recovery_orders_page(
                            after_id=self.cursor,
                            limit=MAX_REQUESTS + 1,
                        )
                        identities = [OrderIdentity.from_order(row) for row in rows]
                    for identity in identities[:MAX_REQUESTS]:
                        # Advance even on unavailable/invalid/timeout snapshots so
                        # old errors cannot starve later rows in this process.
                        self.cursor = identity.id
                        result["attempted"] += 1
                        try:
                            if (
                                not isinstance(identity.broker_id, str)
                                or str(uuid.UUID(identity.broker_id)) != identity.broker_id
                                or not identity.client_key.strip()
                                or identity.side not in ("buy", "sell")
                                or not identity.qty.is_finite()
                                or identity.qty <= 0
                            ):
                                raise ValueError("Invalid persisted broker identity")
                            async with asyncio.timeout(LOOKUP_BUDGET_SECONDS):
                                data = await fetch_order(identity.broker_id)
                            status, filled, price = validate_order_snapshot(identity, data)
                            async with session_factory() as session:
                                current = await OrdersRepo(session).lock_recovery_order(identity.id)
                                if current is None or OrderIdentity.from_order(current) != identity:
                                    result["changed"] += 1
                                    continue
                                from backend.integrations.alpaca_stream import (
                                    apply_order_fill_snapshot,
                                    log_lot_accounting_discrepancy,
                                )

                                accounting = await apply_order_fill_snapshot(
                                    session,
                                    current,
                                    status=status,
                                    cumulative_filled_qty=filled,
                                    avg_fill_price=price,
                                    broker_order_id=identity.broker_id,
                                    broker_order_data=data,
                                )
                                await session.commit()
                                log_lot_accounting_discrepancy(
                                    accounting, ingress="persisted_order_recovery"
                                )
                            result["applied"] += int(accounting["applied"])
                            result["reconciled"] += 1
                            result["unresolved_in_pass"] += int(
                                accounting["status"] not in _TERMINAL
                            )
                        except Exception as exc:  # noqa: BLE001 - unknown failures stay unresolved; continue other rows.
                            result["errors"] += 1
                            logger.warning(
                                "Persisted order recovery unresolved",
                                order_id=str(identity.id),
                                reason=type(exc).__name__,
                            )
                    if len(identities) <= MAX_REQUESTS:
                        self.cursor = None
                        result["sweep_complete"] = True
                        result["backlog"] = False
            except TimeoutError:
                result["state"] = "deadline"
            except Exception as exc:  # noqa: BLE001 - report unavailable without mutating or inferring broker state.
                result["state"] = "unavailable"
                result["errors"] += 1
                logger.warning("Persisted order recovery unavailable", reason=type(exc).__name__)
            if result["state"] == "complete" and (result["errors"] or result["unresolved_in_pass"]):
                result["state"] = "unresolved"
            logger.info("Persisted order recovery pass", **result)
            return result


_services = weakref.WeakKeyDictionary()


async def recover_persisted_orders(session_factory=None, broker_client=None):
    """Use the same advancing cursor across startup, reconnect and periodic calls."""
    loop = asyncio.get_running_loop()
    service = _services.setdefault(loop, OrderRecoveryService())
    if session_factory is None:
        from backend.infra.db import get_session_context

        session_factory = get_session_context

    async def fetch_order(broker_id):
        client = broker_client
        if client is None:
            from backend.integrations.alpaca_broker import get_alpaca_broker_client

            client = get_alpaca_broker_client()
        # UUID validation above makes this an exact resource lookup. Do not use
        # get_order's capped-list fallback and never convert404 to terminal.
        response = await client.client.get(
            f"{client.base_url}/v2/orders/{broker_id}",
            headers=client._get_auth_headers(),
            timeout=LOOKUP_BUDGET_SECONDS,
        )
        if response.status_code != 200:
            raise ValueError("Broker order lookup unavailable")
        return response.json()

    return await service.recover(session_factory, fetch_order)
