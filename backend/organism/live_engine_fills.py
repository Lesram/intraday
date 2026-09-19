"""DB fill-lookup helpers for the live engine.

Extracted from ``live_engine.py`` (2026-06-08 decomposition) as a mixin to
shrink the ``OrganismLiveEngine`` god-object. These two methods are a clean,
self-contained seam: their only engine coupling is ``self._sessionmaker``, all
SQLAlchemy/schema imports are local, and no structural-guard test inspects
their source by content (only ``test_phase3_candidate_shadow_telemetry`` calls
``_lookup_entry_fill_from_db`` behaviourally on an instance, which inheritance
preserves).

``OrganismLiveEngine`` inherits ``_FillLookupMixin`` so
``inspect.getsource(OrganismLiveEngine._lookup_entry_fill_from_db)`` still
resolves via the MRO. Behaviour is byte-for-byte identical to the prior inline
methods.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


class _FillLookupMixin:
    """Authoritative broker fill lookups from the orders table.

    Requires the host class to provide ``self._sessionmaker`` (an async
    SQLAlchemy sessionmaker or ``None``).
    """

    async def _lookup_entry_fill_from_db(
        self,
        symbol: str,
        meta: dict[str, Any] | None = None,
    ) -> tuple[float, float] | None:
        """Look up actual entry fill price/quantity for a trade record.

        Entry orders are submitted asynchronously, so the live tick only has a
        decision-time quote when it creates exit state.  At close/reconcile time
        the DB order row has the broker's authoritative fill; use it so brain
        trade PnL matches order/execution accounting.
        """
        if not self._sessionmaker:
            return None
        meta = meta or {}
        if meta.get("entry_source") == "reconciliation_orphan":
            return None

        order_id = str(meta.get("entry_order_id") or "").strip()
        entry_since: datetime | None = None
        raw_submitted_at = str(meta.get("entry_submitted_at") or "").strip()
        if raw_submitted_at:
            try:
                entry_since = datetime.fromisoformat(
                    raw_submitted_at.replace("Z", "+00:00"),
                )
            except ValueError:
                entry_since = None
        if entry_since is None:
            try:
                raw_entry_time = float(meta.get("entry_time", 0) or 0)
                if raw_entry_time > 0:
                    entry_since = datetime.fromtimestamp(raw_entry_time, tz=UTC)
            except (TypeError, ValueError, OSError):
                entry_since = None

        try:
            from sqlalchemy import select, text as sa_text
            from backend.infra.schemas import Order

            async with self._sessionmaker() as session:
                rows = []
                if entry_since is not None:
                    entry_side = (
                        "sell"
                        if float(meta.get("direction", 1.0) or 1.0) < 0
                        else "buy"
                    )
                    stmt = (
                        select(Order.avg_fill_price, Order.filled_qty)
                        .where(
                            Order.symbol == symbol,
                            Order.side == entry_side,
                            Order.status == "filled",
                            Order.submitted_at
                            >= entry_since - timedelta(minutes=2),
                            sa_text("attributes->>'source' = 'organism'"),
                        )
                        .order_by(Order.submitted_at.asc())
                    )
                    rows = list((await session.execute(stmt)).all())

                if not rows and order_id:
                    try:
                        order_uuid = uuid.UUID(order_id)
                    except ValueError:
                        order_uuid = None
                    if order_uuid is not None:
                        stmt = (
                            select(Order.avg_fill_price, Order.filled_qty)
                            .where(
                                Order.id == order_uuid,
                                Order.symbol == symbol,
                                Order.status == "filled",
                                sa_text("attributes->>'source' = 'organism'"),
                            )
                        )
                        rows = list((await session.execute(stmt)).all())

                total_qty = 0.0
                total_notional = 0.0
                for price_raw, qty_raw in rows:
                    if price_raw is None or qty_raw is None:
                        continue
                    price = float(price_raw)
                    qty = float(qty_raw)
                    if price <= 0 or qty <= 0:
                        continue
                    total_qty += qty
                    total_notional += price * qty
                if total_qty > 0:
                    avg_price = total_notional / total_qty
                    logger.info(
                        "DB fill price for %s entry: $%.2f qty=%.4f",
                        symbol,
                        avg_price,
                        total_qty,
                    )
                    return avg_price, total_qty
        except Exception as e:
            logger.debug("DB entry fill lookup failed for %s: %s", symbol, e)
        return None

    async def _lookup_exit_fill_from_db(self, symbol: str) -> float | None:
        """Look up actual exit fill price from DB for a recently closed position.

        Queries the most recent filled sell order for this symbol with
        organism source attribution.  Returns the avg_fill_price if found,
        or None if no DB session is available or no matching order exists.
        """
        if not self._sessionmaker:
            return None
        try:
            from sqlalchemy import select, text as sa_text
            from backend.infra.schemas import Order

            async with self._sessionmaker() as session:
                stmt = (
                    select(Order.avg_fill_price)
                    .where(
                        Order.symbol == symbol,
                        Order.side == "sell",
                        Order.status == "filled",
                        sa_text("attributes->>'source' = 'organism'"),
                    )
                    .order_by(Order.updated_at.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if row is not None and float(row) > 0:
                    price = float(row)
                    logger.info(
                        "DB fill price for %s exit: $%.2f", symbol, price,
                    )
                    return price
        except Exception as e:
            logger.debug("DB exit fill lookup failed for %s: %s", symbol, e)
        return None
