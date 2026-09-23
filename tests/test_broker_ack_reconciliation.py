"""Offline acknowledgement/retry contracts; no credentials or broker I/O."""
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.infra.outbox_worker import OutboxWorker
from backend.infra.schemas import OutboxEvent
from backend.integrations.alpaca_broker import (
    BROKER_ACK_STATE_PREFIX,
    AlpacaBrokerClient,
    BrokerAcknowledgementUnresolved,
)
from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher

KEY = "persisted-original-client-key"


def ack(key=KEY, **changes):
    return {"id": "broker-confirmed-id", "status": "accepted", "client_order_id": key, **changes}


def broker_with(*responses):
    broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
    broker.base_url = "https://broker.invalid"
    broker.is_paper = True
    broker.get_order = AsyncMock(side_effect=HTTPException(404, "not found"))
    broker._make_request_with_retry = AsyncMock(side_effect=responses)
    return broker


async def submit(broker, key=KEY):
    return await broker.place_order("AAPL", "buy", 1, client_order_id=key)


def marker(key=KEY):
    return BROKER_ACK_STATE_PREFIX + json.dumps(
        {"version": 1, "client_order_id": key}, separators=(",", ":")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 201])
@pytest.mark.parametrize("body", [b"", b"{", b"null", b"[]", b"{}", b'{"status":"accepted"}',
                                   b'{"id":"x"}', b'{"id":null,"status":"accepted"}',
                                   pytest.param(b"[" * 10000 + b"]" * 10000, id="json_recursion")])
async def test_ambiguous_success_resolves_with_exact_client_get_only(status, body):
    broker = broker_with(httpx.Response(status, content=body), httpx.Response(200, json=ack()))
    assert await submit(broker) == ack()
    calls = broker._make_request_with_retry.await_args_list
    assert [call.args[0] for call in calls] == ["POST", "GET"]
    assert calls[0].kwargs["json"]["client_order_id"] == KEY
    assert calls[1].args[1].endswith("/v2/orders:by_client_order_id")
    assert calls[1].kwargs == {"params": {"client_order_id": KEY}}


@pytest.mark.asyncio
@pytest.mark.parametrize("lookup", [
    httpx.Response(404), httpx.Response(503), httpx.Response(200, content=b""),
    httpx.Response(200, json=[]), httpx.Response(200, json=ack("wrong-client")),
    httpx.Response(200, json={"id": "x", "status": "accepted"}),
    httpx.Response(200, json=ack(id="")), HTTPException(503, "unavailable"),
    httpx.ReadTimeout("offline timeout"), RuntimeError("unexpected lookup failure"),
])
async def test_unconfirmed_lookup_retains_uncertainty_without_second_post(lookup):
    broker = broker_with(httpx.Response(201, content=b""), lookup)
    with pytest.raises(BrokerAcknowledgementUnresolved) as failure:
        await submit(broker)
    assert failure.value.client_order_id == KEY
    assert [call.args[0] for call in broker._make_request_with_retry.await_args_list] == ["POST", "GET"]


@pytest.mark.asyncio
async def test_valid_post_response_is_unchanged():
    result = ack()
    broker = broker_with(httpx.Response(201, json=result))
    assert await submit(broker) == result
    assert [call.args[0] for call in broker._make_request_with_retry.await_args_list] == ["POST"]


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [{}, [], {"status": "accepted"}, ack("wrong-client")])
async def test_invalid_existing_order_uses_validated_lookup_never_post(existing):
    broker = broker_with(httpx.Response(200, json=ack()))
    broker.get_order = AsyncMock(return_value=existing)
    assert await submit(broker) == ack()
    assert [call.args[0] for call in broker._make_request_with_retry.await_args_list] == ["GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize("resolved", [True, False])
async def test_duplicate_recovery_uses_same_validated_ack_contract(resolved):
    broker = broker_with(HTTPException(422, "client_order_id must be unique"),
                         httpx.Response(200, json=ack() if resolved else {"status": "accepted"}))
    if resolved:
        assert await submit(broker) == ack()
    else:
        with pytest.raises(BrokerAcknowledgementUnresolved):
            await submit(broker)
    assert [call.args[0] for call in broker._make_request_with_retry.await_args_list] == ["POST", "GET"]


@pytest.mark.asyncio
async def test_missing_lookup_identity_does_not_invent_key():
    broker = broker_with()
    with pytest.raises(BrokerAcknowledgementUnresolved):
        await broker.reconcile_order_acknowledgement("")
    broker._make_request_with_retry.assert_not_awaited()


@pytest_asyncio.fixture
async def database(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "ack.sqlite"))
    async with engine.begin() as conn:
        await conn.run_sync(OutboxEvent.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    yield sessions
    await engine.dispose()


def wired_worker(database, monkeypatch, broker, *, mode="execute", use_mock=False, retries=3):
    from backend.integrations import alpaca_broker, alpaca_outbox
    from backend.services import trading_execution_mode
    from backend import websocket
    dispatcher = AlpacaOutboxDispatcher.__new__(AlpacaOutboxDispatcher)
    dispatcher.use_mock_broker = use_mock
    dispatcher._dispatch_to_mock_broker = AsyncMock(side_effect=AssertionError("must not mock real acknowledgement"))
    monkeypatch.setattr(alpaca_broker, "get_alpaca_broker_client", lambda: broker)
    monkeypatch.setattr(alpaca_outbox, "get_alpaca_outbox_dispatcher", lambda: dispatcher)
    monkeypatch.setattr(trading_execution_mode, "get_trading_execution_mode", lambda: SimpleNamespace(
        mode=mode, source="offline-test", overridden=True))
    notices = AsyncMock()
    monkeypatch.setattr(websocket, "broadcaster", SimpleNamespace(broadcast_to_topic=notices))
    worker = OutboxWorker(database, initial_backoff=0, jitter_factor=0, max_retries=retries)
    worker.use_mock_broker = use_mock
    worker._update_order_status = AsyncMock()
    worker._simulate_broker_order = AsyncMock(side_effect=AssertionError("must not simulate real acknowledgement"))
    return worker, notices


async def enqueue(database, *, key=KEY, last_error=None, nested=False):
    event_id = uuid.uuid4()
    payload = {"order_id": str(uuid.uuid4()), "symbol": "AAPL", "side": "buy",
               "qty": "1", "order_type": "market", "client_key": key}
    if nested:
        payload = {"payload": payload}
    async with database() as session:
        session.add(OutboxEvent(id=event_id, topic="order.submitted", payload=payload,
                               status="pending", attempts=0, last_error=last_error,
                               next_attempt_at=datetime.now(UTC) - timedelta(seconds=1)))
        await session.commit()
    return event_id


async def saved(database, event_id):
    async with database() as session:
        return await session.get(OutboxEvent, event_id)


async def process_one(worker):
    claimed = await worker._get_pending_events()
    assert len(claimed) == 1
    await worker._process_event(claimed[0])
    return claimed[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("nested", [False, True])
async def test_restart_preserves_full_marker_and_original_key(database, monkeypatch, nested):
    # Stress the TEXT persistence contract past common error truncation lengths;
    # no claim that this artificial long key is accepted by the real broker.
    key = "original-" + "x" * 600
    broker = broker_with(httpx.Response(200, content=b""), httpx.Response(404),
                         RuntimeError("lookup subsystem unavailable"), httpx.Response(200, json=ack(key)))
    event_id = await enqueue(database, key=key, nested=nested)
    for attempt in range(3):
        worker, _ = wired_worker(database, monkeypatch, broker)
        claimed = await process_one(worker)
        row = await saved(database, event_id)
        assert (row.payload.get("payload", row.payload))["client_key"] == key
        assert "_broker_ack_lookup_only" not in row.payload
        if attempt < 2:
            assert row.status == "pending"
            assert row.last_error == marker(key)
            assert len(row.last_error) > 500
            assert row.attempts == attempt + 1
            worker._update_order_status.assert_not_awaited()
        else:
            assert claimed["last_error"] == marker(key)
            assert row.status == "sent"
            assert worker._update_order_status.await_args.kwargs["broker_order_id"] == "broker-confirmed-id"
    calls = broker._make_request_with_retry.await_args_list
    assert [call.args[0] for call in calls] == ["POST", "GET", "GET", "GET"]
    assert all(call.kwargs["params"]["client_order_id"] == key for call in calls[1:])
    broker.get_order.assert_awaited_once_with(key)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["execute", "shadow", "dry_run"])
async def test_lookup_only_overrides_both_execution_and_mock_routes(database, monkeypatch, mode):
    broker = broker_with(httpx.Response(200, json=ack()))
    event_id = await enqueue(database, last_error=marker())
    worker, _ = wired_worker(database, monkeypatch, broker, mode=mode, use_mock=True)
    await process_one(worker)
    assert (await saved(database, event_id)).status == "sent"
    assert [call.args[0] for call in broker._make_request_with_retry.await_args_list] == ["GET"]
    broker.get_order.assert_not_awaited()
    assert worker._update_order_status.await_args.kwargs["broker_order_id"] == "broker-confirmed-id"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_marker,key", [
    (BROKER_ACK_STATE_PREFIX + "{", KEY), ("INTRA_BROKER_ACK", KEY),
    (BROKER_ACK_STATE_PREFIX + '{"version":2,"client_order_id":"x"}', KEY),
    (marker("different"), KEY), (marker(), None), (marker(), ""),
])
async def test_corrupt_unsupported_or_missing_identity_is_held_without_io(database, monkeypatch, bad_marker, key):
    broker = broker_with()
    event_id = await enqueue(database, key=key, last_error=bad_marker)
    worker, notices = wired_worker(database, monkeypatch, broker)
    await process_one(worker)
    row = await saved(database, event_id)
    assert row.status == "failed"  # Delivery held; actual order status untouched.
    assert row.last_error == bad_marker
    broker._make_request_with_retry.assert_not_awaited()
    broker.get_order.assert_not_awaited()
    worker._update_order_status.assert_not_awaited()
    assert notices.await_args.args[1]["type"] == "order.reconciliation_required"


@pytest.mark.asyncio
async def test_exhaustion_reports_reconciliation_never_rejection(database, monkeypatch):
    broker = broker_with(httpx.Response(200, content=b""), httpx.Response(404))
    event_id = await enqueue(database)
    worker, notices = wired_worker(database, monkeypatch, broker, retries=0)
    await process_one(worker)
    row = await saved(database, event_id)
    assert row.status == "failed"
    assert row.last_error == marker()
    worker._update_order_status.assert_not_awaited()
    assert notices.await_args.args[1]["type"] == "order.reconciliation_required"
    assert notices.await_args.args[1]["reason"] == marker()


@pytest.mark.asyncio
async def test_missing_persisted_key_never_generates_submission(database, monkeypatch):
    broker = broker_with()
    event_id = await enqueue(database, key=None)
    worker, notices = wired_worker(database, monkeypatch, broker)
    await process_one(worker)
    assert (await saved(database, event_id)).status == "failed"
    broker._make_request_with_retry.assert_not_awaited()
    broker.get_order.assert_not_awaited()
    worker._update_order_status.assert_not_awaited()
    assert notices.await_args.args[1]["type"] == "order.reconciliation_required"


@pytest.mark.asyncio
async def test_first_marker_commit_failure_cannot_downgrade_retry(database, monkeypatch):
    broker = broker_with(httpx.Response(201, content=b""), httpx.Response(404),
                         httpx.Response(200, json=ack()))
    event_id = await enqueue(database)
    worker, _ = wired_worker(database, monkeypatch, broker)
    claimed = await worker._get_pending_events()
    original_commit = AsyncSession.commit
    attempts = 0

    async def fail_first_commit(session):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("offline injected first marker commit failure")
        return await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", fail_first_commit)
    await worker._process_event(claimed[0])
    assert attempts == 2
    row = await saved(database, event_id)
    assert row.last_error == marker()
    assert row.status == "pending"
    restarted, _ = wired_worker(database, monkeypatch, broker)
    await process_one(restarted)
    assert (await saved(database, event_id)).status == "sent"
    assert [call.args[0] for call in broker._make_request_with_retry.await_args_list] == ["POST", "GET", "GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize("order_type", ["market", "limit"])
async def test_simulated_broker_uses_module_environment_and_returns_expected_result(monkeypatch, order_type):
    """Exercise the real mock branch, including its production-environment guard."""
    from backend.infra import outbox_worker
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("MOCK_BROKER_FAILURE_RATE", "0")
    sleep = AsyncMock()
    monkeypatch.setattr(outbox_worker.asyncio, "sleep", sleep)
    monkeypatch.setattr(outbox_worker.random, "uniform", lambda _low, _high: 0)
    worker = OutboxWorker.__new__(OutboxWorker)
    payload = {"order_id": "offline-id", "symbol": "AAPL", "side": "buy",
               "qty": "2", "order_type": order_type}
    result = await worker._simulate_broker_order(payload)
    assert result["success"] is True
    assert result["broker"] == "mock"
    assert result["broker_order_id"].startswith("MOCK_AAPL_")
    assert result["status"] == ("filled" if order_type == "market" else "accepted")
    if order_type == "market":
        assert result["filled_qty"] == 2.0
        assert result["avg_fill_price"] == 150
    else:
        assert "filled_qty" not in result
    sleep.reset_mock()
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="PRODUCTION"):
        await worker._simulate_broker_order(payload)
    sleep.assert_not_awaited()
