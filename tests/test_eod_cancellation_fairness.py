"""Bounded entry confirmation makes progress without forgetting uncertainty."""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.infra.schemas import Order
from backend.organism import operator_cancellation as cancellation
from tests.test_eod_pending_cancellation import (
    bare_engine,
    observed,
    run_confirmation,
    store as _shared_store,
)

store = _shared_store  # Register the existing real SQLite fixture in this module.


async def inventory(store, count):
    rows = [Order(
        id=uuid4(), symbol=f'TEST{i}', side='buy', qty=Decimal(10),
        filled_qty=Decimal(0), order_type='market', tif='day', status='new',
        user_id='synthetic', client_idempotency_key=f'organism_TEST{i}_{uuid4().hex}',
        broker_order_id=str(uuid4()),
        attributes={'source': 'organism', 'reason': 'organism_entry'},
    ) for i in range(count)]
    async with store() as db:
        db.add_all(rows)
        await db.commit()
    engine = bare_engine()
    engine._sessionmaker = store
    engine._pending_entry = {row.symbol: 1 for row in rows}
    engine._pending_entry_order_ids = {row.symbol: str(row.id) for row in rows}
    broker = SimpleNamespace(
        is_paper=True, base_url='https://paper-api.alpaca.markets',
        get_order=AsyncMock(), cancel_order=AsyncMock(), get_positions=AsyncMock(),
    )
    return engine, rows, broker


@pytest.mark.asyncio
async def test_bounded_passes_reach_healthy_tail_after_persistent_slow_prefix(store, monkeypatch):
    engine, rows, broker = await inventory(store, 5)
    identities = dict(engine._pending_entry_order_ids)
    monkeypatch.setattr(cancellation, 'CALL_TIMEOUT', 0.1)
    monkeypatch.setattr(cancellation, 'TOTAL_TIMEOUT', 0.27)
    healthy = rows[-1]
    attempts = []

    async def get_order(identity):
        attempts.append(identity)
        if identity != healthy.broker_order_id:
            await asyncio.sleep(10)  # actual per-call/whole-pass timeout, no transport
        return observed(healthy, 'canceled')

    broker.get_order.side_effect = get_order
    receipts = [await run_confirmation(monkeypatch, engine, broker) for _ in range(3)]
    assert healthy.broker_order_id in attempts, 'slow prefix starved healthy tail'
    assert set(attempts) == {row.broker_order_id for row in rows}
    assert engine._pending_entry_order_ids == {k: v for k, v in identities.items() if k != healthy.symbol}
    assert engine._pending_entry == {row.symbol: 1 for row in rows[:-1]}
    assert any(item.get('release_pending') is True and item['entry_order_id'] == str(healthy.id)
               for receipt in receipts for item in receipt['orders'])
    assert all(receipt['db_modified'] is False for receipt in receipts)
    assert any('cancellation_deadline_exceeded' in receipt['issues'] for receipt in receipts)
    async with store() as db:
        for row in rows:
            current = await db.get(Order, row.id)
            assert current.status == 'new' and current.filled_qty == 0
    broker.cancel_order.assert_not_awaited()
    engine._order_service.cancel_order.assert_not_awaited()
    assert engine._pending_exit == {'MSFT': 500}


@pytest.mark.asyncio
async def test_external_cancellation_advances_cursor_before_await_and_retains_identity(store, monkeypatch):
    engine, rows, broker = await inventory(store, 2)
    pending, identities = dict(engine._pending_entry), dict(engine._pending_entry_order_ids)
    entered = asyncio.Event()

    async def held_get(identity):
        assert identity == rows[0].broker_order_id
        entered.set()
        await asyncio.Event().wait()

    broker.get_order.side_effect = held_get
    task = asyncio.create_task(run_confirmation(monkeypatch, engine, broker))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        cursor_during_await = getattr(engine, '_pending_entry_confirmation_cursor', None)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert cursor_during_await == str(rows[0].id)
    assert engine._pending_entry == pending and engine._pending_entry_order_ids == identities
    by_id = {row.broker_order_id: row for row in rows}
    broker.get_order.reset_mock()
    broker.get_order.side_effect = lambda identity: observed(by_id[identity], 'expired')
    await run_confirmation(monkeypatch, engine, broker)
    assert [call.args[0] for call in broker.get_order.await_args_list] == [
        rows[1].broker_order_id, rows[0].broker_order_id,
    ]
    assert not engine._pending_entry and not engine._pending_entry_order_ids
    broker.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_removed_cursor_wraps_without_skipping_remaining_exact_identities(store, monkeypatch):
    engine, rows, broker = await inventory(store, 3)
    engine._pending_entry_confirmation_cursor = str(rows[1].id)
    del engine._pending_entry[rows[1].symbol]
    del engine._pending_entry_order_ids[rows[1].symbol]
    by_id = {row.broker_order_id: row for row in rows}
    broker.get_order.side_effect = lambda identity: observed(by_id[identity], 'rejected')
    await run_confirmation(monkeypatch, engine, broker)
    assert [call.args[0] for call in broker.get_order.await_args_list] == [
        rows[0].broker_order_id, rows[2].broker_order_id,
    ]
    assert not engine._pending_entry and not engine._pending_entry_order_ids
    assert engine._pending_entry_confirmation_cursor == str(rows[2].id)


@pytest.mark.asyncio
async def test_cursor_cannot_authorize_wrong_symbol_identity(store, monkeypatch):
    engine, rows, broker = await inventory(store, 2)
    engine._pending_entry_confirmation_cursor = str(rows[0].id)
    engine._pending_entry_order_ids = {'WRONG': str(rows[1].id), rows[0].symbol: str(rows[0].id)}
    engine._pending_entry = {symbol: 1 for symbol in engine._pending_entry_order_ids}
    broker.get_order.return_value = observed(rows[0], 'canceled')
    receipt = await run_confirmation(monkeypatch, engine, broker)
    assert 'tracked_entry_attribution_unverified' in receipt['issues']
    assert engine._pending_entry_order_ids == {'WRONG': str(rows[1].id)}
    assert engine._pending_entry == {'WRONG': 1}
    broker.get_order.assert_awaited_once_with(rows[0].broker_order_id)
    broker.cancel_order.assert_not_awaited()
