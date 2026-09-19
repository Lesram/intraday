"""Offline reconciliation acceptance cases; no database or broker credentials.

This required suite used to be a manual script collecting zero pytest cases.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.position_reconciliation_service import PositionReconciliationService


def service_with(orders, positions):
    result = MagicMock()
    result.scalars.return_value.all.return_value = orders
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    broker = SimpleNamespace(get_positions=AsyncMock(return_value=positions))
    return PositionReconciliationService(db, broker)


def buy(identity, quantity):
    return SimpleNamespace(id=identity, symbol="AAPL", side="buy", status="filled", filled_qty=quantity)


@pytest.mark.asyncio
async def test_multiple_entry_orders_use_combined_symbol_quantity():
    service = service_with(
        [buy("entry-one", 5), buy("entry-two", 5)],
        [{"symbol": "AAPL", "qty": "7", "current_price": "100", "unrealized_pl": "3"}],
    )
    statuses = await service.get_position_status_for_orders(["entry-one", "entry-two"])
    assert set(statuses) == {"entry-one", "entry-two"}
    assert all(row["position_status"] == "partially_closed" for row in statuses.values())
    assert all("7.0 of 10.0" in row["note"] for row in statuses.values())


@pytest.mark.asyncio
async def test_database_failure_cannot_mark_requested_positions_closed():
    service = service_with([], [])
    service.db.execute.side_effect = RuntimeError("database unavailable")
    statuses = await service.get_position_status_for_orders(["first", "second"])
    assert set(statuses) == {"first", "second"}
    assert all(row["position_status"] == "unknown" for row in statuses.values())


@pytest.mark.asyncio
async def test_invalid_broker_quantity_is_unknown_instead_of_flat():
    service = service_with([buy("entry", 5)], [{"symbol": "AAPL", "qty": "unavailable"}])
    statuses = await service.get_position_status_for_orders(["entry"])
    assert statuses["entry"]["position_status"] == "unknown"
    assert statuses["entry"]["current_qty"] is None


@pytest.mark.asyncio
async def test_summary_preserves_unknown_positions_during_broker_failure():
    service = service_with([buy("entry", 5)], [])
    service.alpaca_client.get_positions.side_effect = TimeoutError("broker unavailable")
    summary = await service.get_reconciliation_summary()
    assert summary["total_filled_buys"] == 1
    assert summary["unknown"] == 1
    assert summary["open_positions"] == 0
    assert summary["closed_positions"] == 0
