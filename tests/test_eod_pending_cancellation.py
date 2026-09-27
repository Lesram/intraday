"""EOD cancellation must retain unresolved broker identity across time/restart."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from backend.organism import operator_cancellation as cancellation
from backend.organism.live_engine import OrganismLiveEngine


def bare_engine():
    engine = object.__new__(OrganismLiveEngine)
    engine._tick_count = 500
    engine._PENDING_ENTRY_TICKS = 30
    engine._PENDING_EXIT_TICKS = 3
    engine._EXIT_COOLDOWN_TICKS = 10
    engine._pending_entry = {'AAPL': 1}
    engine._pending_entry_order_ids = {'AAPL': str(uuid4())}
    engine._pending_exit = {'MSFT': 500}
    engine._exit_cooldown = {}
    engine._accounting_completed_entries = {}
    engine._order_service = SimpleNamespace(cancel_order=AsyncMock(return_value={'status': 'cancelled'}))
    return engine


@pytest.mark.asyncio
@pytest.mark.parametrize('issue', ['broker_confirmation_unavailable', 'cancellation_not_confirmed', 'fill_reconciliation_required'])
async def test_unverified_cancel_never_forgets_entry(monkeypatch, issue):
    engine = bare_engine()
    identity = engine._pending_entry_order_ids['AAPL']
    confirm = AsyncMock(return_value={'orders': [{'symbol': 'AAPL', 'entry_order_id': identity,
                                                'release_pending': False, 'issue': issue}], 'issues': [issue]})
    monkeypatch.setattr(cancellation, 'confirm_tracked_entries', confirm)
    await engine._cancel_pending_entry_orders()
    assert engine._pending_entry == {'AAPL': 1}
    assert engine._pending_entry_order_ids == {'AAPL': identity}
    assert engine._pending_exit == {'MSFT': 500}
    engine._order_service.cancel_order.assert_not_awaited()
    confirm.assert_awaited_once_with(engine, cancel=True)


def test_ttl_and_stream_terminal_boolean_cannot_erase_attribution(monkeypatch):
    engine = bare_engine()
    identity = engine._pending_entry_order_ids['AAPL']
    engine._pending_entry['NO_ID'] = 0
    stream = SimpleNamespace(is_order_terminal=MagicMock(return_value=True))
    monkeypatch.setattr('backend.integrations.alpaca_stream.get_stream_client', lambda: stream)
    engine._stage_expire_cooldowns()
    assert engine._pending_entry == {'AAPL': 1, 'NO_ID': 0}
    assert engine._pending_entry_order_ids == {'AAPL': identity}
    stream.is_order_terminal.assert_not_called()

from datetime import UTC, datetime
from decimal import Decimal
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.infra.schemas import Order, Execution, PositionLot, RealizedTrade, AuditLog


@pytest.fixture
async def store():
    db_engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with db_engine.begin() as connection:
        for table in (Order.__table__, Execution.__table__, PositionLot.__table__, RealizedTrade.__table__, AuditLog.__table__):
            await connection.run_sync(lambda conn, table=table: table.create(conn))
    try:
        yield async_sessionmaker(db_engine, expire_on_commit=False)
    finally:
        await db_engine.dispose()


async def seeded(store, *, filled=0, status='new', execution=True, lot=True, remaining=None):
    engine = bare_engine()
    row = Order(id=uuid4(), symbol='AAPL', side='buy', qty=Decimal(10),
                filled_qty=Decimal(filled), avg_fill_price=Decimal(100) if filled else None,
                order_type='market', tif='day', status=status, user_id='synthetic',
                client_idempotency_key='organism_AAPL_' + uuid4().hex,
                broker_order_id=str(uuid4()), attributes={'source': 'organism', 'reason': 'organism_entry'})
    async with store() as db:
        db.add(row)
        await db.flush()
        if filled and execution:
            db.add(Execution(order_id=row.id, fill_qty=Decimal(filled), fill_price=Decimal(100),
                             ts=datetime.now(UTC), venue='synthetic'))
        if filled and lot:
            db.add(PositionLot(order_id=row.id, symbol='AAPL', user_id='synthetic', qty=Decimal(filled),
                               remaining_qty=Decimal(filled if remaining is None else remaining),
                               cost_basis=Decimal(100), open_date=datetime.now(UTC)))
        await db.commit()
    engine._sessionmaker = store
    engine._pending_entry_order_ids['AAPL'] = str(row.id)
    engine._exit_levels = {'AAPL': SimpleNamespace(symbol='AAPL', direction=1)}
    engine._entry_metadata = {'AAPL': {'entry_order_id': str(row.id), 'direction': 1}}
    engine._positions_service = SimpleNamespace(get_all_positions=AsyncMock(
        return_value={'AAPL': {'qty': filled, 'side': 'long'}}))
    broker = SimpleNamespace(is_paper=True, base_url='https://paper-api.alpaca.markets',
                             get_order=AsyncMock(), cancel_order=AsyncMock(), get_positions=AsyncMock(return_value=[
                                 {'symbol': 'AAPL', 'qty': str(filled if remaining is None else remaining), 'side': 'long'}
                             ] if filled else []))
    return engine, row, broker


def observed(row, state='new', filled='0', **changes):
    return {'id': row.broker_order_id, 'client_order_id': row.client_idempotency_key,
            'symbol': row.symbol, 'side': row.side, 'qty': str(row.qty),
            'filled_qty': str(filled), 'filled_avg_price': '100' if Decimal(filled) else None,
            'status': state, **changes}


async def run_confirmation(monkeypatch, engine, broker, *, cancel=True):
    monkeypatch.setattr('backend.integrations.alpaca_broker.get_alpaca_broker_client', lambda: broker)
    await engine._reconcile_pending_entry_orders(cancel=cancel)
    return engine._last_pending_entry_resolution


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['canceled', 'cancelled', 'expired', 'rejected'])
async def test_actual_sql_confirmed_zero_fill_terminal_releases_without_mutating_db(store, monkeypatch, state):
    engine, row, broker = await seeded(store)
    broker.get_order.return_value = observed(row, state)
    receipt = await run_confirmation(monkeypatch, engine, broker)
    assert not engine._pending_entry and not engine._pending_entry_order_ids
    assert receipt['orders'][0]['release_pending'] is True
    broker.cancel_order.assert_not_awaited()
    async with store() as db:
        persisted = await db.get(Order, row.id)
        assert persisted.status == 'new' and persisted.filled_qty == 0
    assert engine._pending_exit == {'MSFT': 500} and 'AAPL' in engine._exit_levels


@pytest.mark.asyncio
@pytest.mark.parametrize('transport_error', [None, TimeoutError, RuntimeError])
async def test_delete_ack_or_transport_error_requires_terminal_get(store, monkeypatch, transport_error):
    engine, row, broker = await seeded(store)
    broker.get_order.side_effect = [observed(row), observed(row, 'canceled')]
    broker.cancel_order.side_effect = transport_error
    await run_confirmation(monkeypatch, engine, broker)
    broker.cancel_order.assert_awaited_once_with(row.broker_order_id)
    assert broker.get_order.await_count == 2 and not engine._pending_entry


@pytest.mark.asyncio
@pytest.mark.parametrize('state,filled', [('new', 0), ('pending_cancel', 0), ('partially_filled', 3),
                                          ('filled', 10), ('canceled', 3), ('replaced', 0), ('unknown', 0)])
async def test_unconfirmed_or_unaccounted_snapshot_retains_identity(store, monkeypatch, state, filled):
    engine, row, broker = await seeded(store)
    broker.get_order.return_value = observed(row, state, filled)
    receipt = await run_confirmation(monkeypatch, engine, broker)
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}
    assert engine._pending_entry == {'AAPL': 1} and receipt['issues']
    assert engine._pending_exit == {'MSFT': 500}


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [TimeoutError, RuntimeError])
async def test_confirmation_read_failure_keeps_exact_identity(store, monkeypatch, error):
    engine, row, broker = await seeded(store)
    broker.get_order.side_effect = error('private transport detail')
    receipt = await run_confirmation(monkeypatch, engine, broker)
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}
    assert 'private transport' not in str(receipt)
    broker.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_task_cancellation_preserves_maps_and_does_not_submit(store, monkeypatch):
    engine, row, broker = await seeded(store)
    broker.get_order.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await run_confirmation(monkeypatch, engine, broker)
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}
    engine._order_service.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('changes', [{'id': str(uuid4())}, {'client_order_id': 'foreign'},
                                     {'side': 'sell'}, {'symbol': 'MSFT'}, {'qty': '9'},
                                     {'replaced_by': str(uuid4())}, {'legs': [{}]}])
async def test_foreign_or_replacement_snapshot_never_cancelled(store, monkeypatch, changes):
    engine, row, broker = await seeded(store)
    broker.get_order.return_value = observed(row, **changes)
    await run_confirmation(monkeypatch, engine, broker)
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}
    broker.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('filled,status', [(10, 'filled'), (3, 'canceled')])
async def test_accounted_terminal_fill_releases_only_after_original_cooldown(store, monkeypatch, filled, status):
    engine, row, broker = await seeded(store, filled=filled, status=status, remaining=1)
    broker.get_order.return_value = observed(row, status, filled)
    engine._pending_entry['AAPL'] = engine._tick_count - engine._PENDING_ENTRY_TICKS + 1
    await run_confirmation(monkeypatch, engine, broker, cancel=False)
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}
    engine._tick_count += 1
    receipt = await run_confirmation(monkeypatch, engine, broker, cancel=False)
    assert not engine._pending_entry and receipt['orders'][0]['resolution'] == 'accounted_fill'
    assert engine._entry_metadata['AAPL']['entry_order_id'] == str(row.id)
    assert 'AAPL' in engine._exit_levels and engine._pending_exit == {'MSFT': 500}
    broker.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('missing', ['execution', 'lot', 'protection', 'position', 'price', 'db_qty'])
async def test_terminal_filled_needs_accounting_and_protection(store, monkeypatch, missing):
    engine, row, broker = await seeded(store, filled=10, status='filled',
                                     execution=missing != 'execution', lot=missing != 'lot')
    broker.get_order.return_value = observed(row, 'filled', 10)
    if missing == 'protection': engine._exit_levels.clear()
    if missing == 'position': broker.get_positions.return_value = []
    if missing == 'price': broker.get_order.return_value['filled_avg_price'] = '101'
    if missing == 'db_qty':
        async with store() as db:
            (await db.get(Order, row.id)).filled_qty = Decimal(9)
            await db.commit()
    await run_confirmation(monkeypatch, engine, broker, cancel=False)
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}


@pytest.mark.asyncio
@pytest.mark.parametrize('local_evidence', ['summary', 'execution', 'lot'])
async def test_zero_fill_broker_cannot_erase_contradictory_local_fill(store, monkeypatch, local_evidence):
    engine, row, broker = await seeded(store, filled=1, execution=local_evidence == 'execution',
                                     lot=local_evidence == 'lot')
    if local_evidence != 'summary':
        async with store() as db:
            (await db.get(Order, row.id)).filled_qty = Decimal(0)
            await db.commit()
    broker.get_order.return_value = observed(row, 'canceled')
    await run_confirmation(monkeypatch, engine, broker)
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}


@pytest.mark.asyncio
async def test_timeout_is_bounded_and_original_identity_survives(store, monkeypatch):
    engine, row, broker = await seeded(store)
    async def pending(_): await asyncio.Event().wait()
    broker.get_order.side_effect = pending
    monkeypatch.setattr(cancellation, 'CALL_TIMEOUT', .01)
    await asyncio.wait_for(run_confirmation(monkeypatch, engine, broker), .5)
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}


@pytest.mark.asyncio
async def test_closed_filled_portion_cannot_hide_open_entry_remainder(store, monkeypatch):
    engine, row, broker = await seeded(store, filled=3, status='canceled', remaining=0)
    broker.get_positions.return_value = []
    engine._entry_metadata.clear()
    engine._exit_levels.clear()
    engine._accounting_completed_entries[str(row.id)] = '2026-09-22T19:00:00+00:00'
    engine._all_trades = [SimpleNamespace(entry_order_id=str(row.id), closed_at='2026-09-22T19:00:00+00:00',
                                        is_reconciliation_artifact=False, shares=3, entry_price=100)]
    broker.get_order.return_value = observed(row, 'partially_filled', 3)
    engine._stage_expire_cooldowns()
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}
    await run_confirmation(monkeypatch, engine, broker, cancel=False)
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}
    broker.get_order.return_value = observed(row, 'canceled', 3)
    receipt = await run_confirmation(monkeypatch, engine, broker, cancel=False)
    assert not engine._pending_entry_order_ids and not receipt['issues']
    assert 'issue' not in receipt['orders'][0]


def test_db_only_verified_unfilled_close_does_not_authorize_forgetting():
    engine = bare_engine()
    identity = engine._pending_entry_order_ids['AAPL']
    engine._accounting_completed_entries[identity] = 'verified_unfilled'
    engine._stage_expire_cooldowns()
    assert engine._pending_entry_order_ids['AAPL'] == identity


@pytest.mark.asyncio
async def test_actual_full_save_and_initialize_keep_unresolved_identity(tmp_path, monkeypatch):
    from tests.test_operator_controls import actual_engine, initialize_offline
    engine = actual_engine(tmp_path)
    await initialize_offline(engine)
    identity = str(uuid4())
    engine._pending_entry_order_ids = {'AAPL': identity}
    engine._pending_entry = {'AAPL': 0, 'NO_ID': 0}
    engine._tick_count = 500
    assert engine.force_save_brain()['success'] is True
    saved = engine.brain.brain_dir / 'extra_counters.json'
    assert saved.exists()
    restarted = actual_engine(tmp_path)
    await initialize_offline(restarted)
    assert restarted._pending_entry_order_ids == {'AAPL': identity}
    assert set(restarted._pending_entry) == {'AAPL', 'NO_ID'}
    restarted._tick_count += 1000
    restarted._stage_expire_cooldowns()
    assert restarted._pending_entry_order_ids == {'AAPL': identity}
    assert set(restarted._pending_entry) == {'AAPL', 'NO_ID'}
    assert restarted._last_pending_entry_resolution['issues'] == ['entry_database_unavailable', 'pending_entry_identity_missing']
    assert restarted.force_save_brain()['success'] is True
    third = actual_engine(tmp_path)
    await initialize_offline(third)
    assert third._pending_entry_order_ids == {'AAPL': identity}


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_real_eod_tick_uses_supported_cancel_retains_uncertain_and_flattens(store, tmp_path, monkeypatch):
    from backend.organism.adaptive_exits import ExitLevels
    from backend.organism.replay_simulator import SimulatedBroker, make_price_df
    from tests.test_organism_engine_scenarios import MockDataClient
    _, row, transport = await seeded(store)
    # Broker accepted DELETE but has not confirmed terminal; this ID must survive.
    transport.get_order.return_value = observed(row, 'new')
    monkeypatch.setattr('backend.integrations.alpaca_broker.get_alpaca_broker_client', lambda: transport)
    frames = {symbol: make_price_df(n=250, base=100) for symbol in ('AAPL', 'MSFT', 'SPY')}
    broker = SimulatedBroker(initial_cash=100_000)
    engine = OrganismLiveEngine(data_client=MockDataClient(frames), order_service=broker,
                                positions_service=broker, brain_dir=str(tmp_path / 'eod-brain'),
                                timeframe='1Min', universe=['AAPL', 'MSFT', 'SPY'])
    engine.market_scanner = None
    now = datetime(2026, 9, 22, 19, 59, tzinfo=UTC)
    engine._now_fn = lambda: now
    engine._time_fn = now.timestamp
    await engine.initialize()
    engine._sessionmaker = store
    engine._pending_entry_order_ids = {'AAPL': str(row.id)}
    engine._pending_entry = {'AAPL': 0}
    broker.add_position('MSFT', qty=10, avg_entry_price=100)
    broker.set_price('MSFT', 100)
    engine._exit_levels['MSFT'] = ExitLevels(symbol='MSFT', direction=1., entry_price=100,
        stop_loss=90, take_profit=120, trailing_stop=90, atr_at_entry=2,
        regime_at_entry='unknown', highest_favorable=100)
    engine._entry_metadata['MSFT'] = {'entry_price': 100., 'entry_tick': 0, 'direction': 1.,
        'confidence': .6, 'predicted_return': .02, 'filled_shares': 10, 'entry_source': 'alpha'}
    result = await engine.live_tick()
    assert engine._alpha_breakout_late_blocked
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}
    assert 'AAPL' in engine._pending_entry
    assert transport.get_order.await_count >= 4
    transport.cancel_order.assert_awaited_once_with(row.broker_order_id)
    assert result.orders_submitted >= 1
    assert 'MSFT' not in await broker.get_all_positions()
    assert broker.trade_log and all(order['side'] == 'sell' for order in broker.trade_log)
    assert engine._ml_isolation_mode and engine._fixed_risk_sizing_mode


@pytest.mark.asyncio
async def test_filled_status_cannot_contradict_requested_quantity(store, monkeypatch):
    engine, row, broker = await seeded(store, filled=4, status='filled')
    broker.get_order.return_value = observed(row, 'filled', 4)
    receipt = await run_confirmation(monkeypatch, engine, broker, cancel=False)
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}
    assert receipt['issues'] == ['invalid_order_quantity']
    broker.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_completed_close_cannot_release_later_filled_exposure(store, monkeypatch):
    engine, row, broker = await seeded(store, filled=10, status='filled', remaining=7)
    engine._entry_metadata.clear()
    engine._exit_levels.clear()
    engine._accounting_completed_entries[str(row.id)] = '2026-09-22T19:00:00+00:00'
    engine._all_trades = [SimpleNamespace(entry_order_id=str(row.id), closed_at='2026-09-22T19:00:00+00:00',
                                        is_reconciliation_artifact=False, shares=3, entry_price=100)]
    broker.get_order.return_value = observed(row, 'filled', 10)
    await run_confirmation(monkeypatch, engine, broker, cancel=False)
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}
    # Even a lagging flat service snapshot cannot excuse leftover lot exposure.
    broker.get_positions.return_value = []
    await run_confirmation(monkeypatch, engine, broker, cancel=False)
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}


@pytest.mark.asyncio
async def test_unbounded_inventory_stops_before_broker_or_db(store, monkeypatch):
    engine, _, broker = await seeded(store)
    engine._pending_entry_order_ids = {str(i): str(uuid4()) for i in range(cancellation.INVENTORY_LIMIT + 1)}
    receipt = await run_confirmation(monkeypatch, engine, broker)
    assert 'entry_inventory_limit' in receipt['issues']
    broker.get_order.assert_not_awaited()
    assert len(engine._pending_entry_order_ids) == cancellation.INVENTORY_LIMIT + 1


@pytest.mark.asyncio
@pytest.mark.parametrize('defect', ['lagging_qty', 'opposite_meta', 'opposite_level', 'opposite_position',
                                    'missing_position_symbol', 'duplicate_position', 'position_error',
                                    'pyramid_foreign_anchor'])
async def test_protected_fill_release_requires_exact_remaining_exposure(store, monkeypatch, defect):
    engine, row, broker = await seeded(store, filled=10, status='filled')
    broker.get_order.return_value = observed(row, 'filled', 10)
    if defect == 'lagging_qty': broker.get_positions.return_value[0]['qty'] = '3'
    if defect == 'opposite_meta': engine._entry_metadata['AAPL']['direction'] = -1
    if defect == 'opposite_level': engine._exit_levels['AAPL'].direction = -1
    if defect == 'opposite_position': broker.get_positions.return_value[0]['side'] = 'short'
    if defect == 'missing_position_symbol': broker.get_positions.return_value = [{}]
    if defect == 'duplicate_position': broker.get_positions.return_value *= 2
    if defect == 'position_error': broker.get_positions.side_effect = TimeoutError
    if defect == 'pyramid_foreign_anchor':
        engine._entry_metadata['AAPL']['entry_order_id'] = str(uuid4())
        async with store() as db:
            (await db.get(Order, row.id)).attributes = {'source': 'organism', 'reason': 'pyramid_add'}
            await db.commit()
    await run_confirmation(monkeypatch, engine, broker, cancel=False)
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}


async def simulated_entry():
    from functools import partial
    from backend.organism.replay_simulator import SimulatedBroker
    engine = bare_engine()
    broker = SimulatedBroker(initial_cash=100_000)
    broker.set_price('AAPL', 100)
    row = await broker.submit_symbol_order(symbol='AAPL', side='buy', qty=10,
        idempotency_key='organism_AAPL_synthetic',
        attributes={'source': 'organism', 'reason': 'organism_entry'})
    engine._pending_entry_order_ids = {'AAPL': row['id']}
    engine._entry_metadata = {'AAPL': {'entry_order_id': row['id'], 'direction': 1}}
    engine._exit_levels = {'AAPL': SimpleNamespace(symbol='AAPL', direction=1)}
    engine._all_trades = []
    engine._confirm_pending_entry_orders = partial(broker.confirm_pending_entries, engine)
    return engine, broker, row


@pytest.mark.asyncio
async def test_explicit_simulation_adapter_reconciles_actual_fill_and_cooldown():
    engine, broker, row = await simulated_entry()
    engine._pending_entry['AAPL'] = 499
    await engine._reconcile_pending_entry_orders()
    assert engine._pending_entry_order_ids == {'AAPL': row['id']}
    engine._tick_count = 529
    await engine._reconcile_pending_entry_orders()
    assert not engine._pending_entry_order_ids
    assert engine._last_pending_entry_resolution['execution_environment'] == 'simulation'
    assert broker.cash == 99_000 and broker._positions['AAPL']['qty'] == 10
    assert len(broker.filled_orders) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('defect', ['open_remainder', 'partial_filled_status', 'missing_accounting',
                                    'duplicate_identity', 'foreign_identity', 'inventory_mismatch',
                                    'unprotected', 'opposite_metadata', 'missing_completed_close',
                                    'malformed_fill'])
async def test_simulation_confirmation_cannot_bypass_terminal_accounting(defect):
    engine, broker, row = await simulated_entry()
    if defect == 'open_remainder': row['status'] = 'partially_filled'
    if defect == 'partial_filled_status': row['filled_qty'] = '4'
    if defect == 'missing_accounting': broker.filled_orders.clear()
    if defect == 'duplicate_identity': broker.filled_orders.append(dict(row))
    if defect == 'foreign_identity': engine._pending_entry_order_ids['AAPL'] = str(uuid4())
    if defect == 'inventory_mismatch': broker._positions['AAPL']['qty'] = 9
    if defect == 'unprotected': engine._exit_levels.clear()
    if defect == 'opposite_metadata': engine._entry_metadata['AAPL']['direction'] = -1
    if defect == 'malformed_fill': row['filled_qty'] = 'NaN'
    if defect == 'missing_completed_close':
        await broker.submit_symbol_order(symbol='AAPL', side='sell', qty=10,
            attributes={'source': 'organism', 'reason': 'stop_loss'})
        assert not broker._positions and broker.trade_log
    before = dict(engine._pending_entry_order_ids)
    await engine._cancel_pending_entry_orders()
    assert engine._pending_entry_order_ids == before
    assert engine._last_pending_entry_resolution['issues'] == ['simulated_entry_resolution_unverified']


@pytest.mark.asyncio
async def test_uninjected_production_engine_never_uses_simulated_evidence():
    engine = bare_engine()
    await engine._reconcile_pending_entry_orders()
    assert engine._pending_entry_order_ids
    assert engine._last_pending_entry_resolution['issues'] == ['entry_database_unavailable']


@pytest.mark.asyncio
@pytest.mark.parametrize('pending_leg', ['base', 'add'])
async def test_base_add_atomic_close_retains_ambiguous_anchor_only_receipt(store, monkeypatch, pending_leg):
    from backend.integrations.alpaca_stream import apply_incremental_fill_accounting
    _, base, _ = await seeded(store, filled=10, status='filled')
    engine, addition, broker = await seeded(store, filled=2, status='filled')
    async with store() as db:
        (await db.get(Order, addition.id)).qty = Decimal(2)
        (await db.get(Order, addition.id)).attributes = {'source': 'organism', 'reason': 'pyramid_add'}
        await db.commit()
    addition.qty = Decimal(2)
    tracked = base if pending_leg == 'base' else addition
    engine._pending_entry_order_ids = {'AAPL': str(tracked.id)}
    engine._entry_metadata['AAPL']['entry_order_id'] = str(base.id)
    broker.get_positions.return_value = [{'symbol': 'AAPL', 'qty': '12', 'side': 'long'}]
    broker.get_order.return_value = observed(tracked, 'filled', tracked.filled_qty)
    # Exact current position protection permits the real entry/add when cooldown elapsed.
    await run_confirmation(monkeypatch, engine, broker, cancel=False)
    assert not engine._pending_entry_order_ids
    # Recreate the under-cooldown state, then close all actual DB lots atomically.
    engine._pending_entry_order_ids = {'AAPL': str(tracked.id)}
    engine._pending_entry = {'AAPL': engine._tick_count - 29}
    async with store() as db:
        exit_order = Order(id=uuid4(), symbol='AAPL', side='sell', qty=Decimal(12), filled_qty=0,
            order_type='market', tif='day', status='new', user_id='synthetic',
            client_idempotency_key='organism_exit_AAPL_' + uuid4().hex, broker_order_id=str(uuid4()),
            attributes={'source': 'organism', 'reason': 'eod_flatten'})
        db.add(exit_order)
        await db.flush()
        await apply_incremental_fill_accounting(db, exit_order, previous_filled_qty=0,
            cumulative_filled_qty=12, avg_fill_price=105, status='filled')
        await db.commit()
        from sqlalchemy import select
        lots = list((await db.execute(select(PositionLot))).scalars())
        assert sum(lot.qty for lot in lots) == 12 and all(lot.remaining_qty == 0 for lot in lots)
        assert len(list((await db.execute(select(RealizedTrade))).scalars())) == 2
    broker.get_positions.return_value = []
    engine._exit_levels.clear()
    engine._entry_metadata.clear()
    closed_at = '2026-09-22T19:58:00+00:00'
    engine._accounting_completed_entries = {str(base.id): closed_at}
    engine._all_trades = [SimpleNamespace(entry_order_id=str(base.id), closed_at=closed_at,
                                        is_reconciliation_artifact=False, shares=12, entry_price=100)]
    engine._tick_count += 100
    engine._stage_expire_cooldowns()
    await run_confirmation(monkeypatch, engine, broker, cancel=False)
    # No explicit immutable per-add closed-cycle link exists: never guess it.
    assert engine._pending_entry_order_ids == {'AAPL': str(tracked.id)}
    assert engine._last_pending_entry_resolution['issues'] == ['fill_reconciliation_required']
