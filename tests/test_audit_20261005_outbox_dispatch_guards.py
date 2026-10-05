"""Audit 2026-10-05 C01-01: the outbox exit guard (exit sells cannot open a short).

Offline: SQLite (with ck_orders_status enforced by triggers built from the
migration's allowed set) and a fake broker client. No network, no credentials.
Orders are created through the real OrderService (or, for events queued before
this release, in the old payload shape), dispatched by the real OutboxWorker
and AlpacaOutboxDispatcher, and acknowledgements are persisted by the real
_update_order_status. Entries must dispatch exactly as before.
"""
from __future__ import annotations

import ast
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import uuid

from fastapi import HTTPException
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import backend.infra.outbox_worker as worker_mod
from backend.infra.outbox import OutboxRepo
from backend.infra.outbox_worker import OutboxWorker
from backend.infra.repositories.orders import OrdersRepo
from backend.infra.schemas import AuditLog, Execution, Order, OutboxEvent, PositionLot, RealizedTrade
from backend.integrations import alpaca_outbox
from backend.integrations.alpaca_broker import AlpacaBrokerClient, BrokerAcknowledgementUnresolved
from backend.services import order_service as order_service_mod
from backend.services.order_service import OrderService

REPO = Path(__file__).resolve().parents[1]
BROKER_ID = "0f6b8c1e-2d4a-4c5b-9e7f-8a9b0c1d2e3f"
DUPLICATE = "DUPLICATE EXIT SUPPRESSED AT DISPATCH"
REFUSED = "EXIT ORDER REFUSED AT DISPATCH"
INSUFFICIENT_QTY = HTTPException(
    status_code=403,
    detail='Alpaca API error: {"code":40310000,"message":"insufficient qty available '
           'for order (requested: 100, available: 0)"}',
)


def _allowed_order_statuses() -> tuple[str, ...]:
    """The production ck_orders_status set, read from the migration source."""
    path = REPO / "backend/migrations/versions/20260503_000002_xx_2_widen_orders_status_check.py"
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "_WIDENED_STATUSES":
            return tuple(ast.literal_eval(node.value))
    raise AssertionError("ck_orders_status set not found")


@pytest_asyncio.fixture
async def sessions(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "guards.sqlite"))
    allowed = ", ".join(f"'{status}'" for status in _allowed_order_statuses())
    async with engine.begin() as conn:
        for table in (Order, Execution, PositionLot, RealizedTrade, AuditLog, OutboxEvent):
            await conn.run_sync(lambda c, t=table.__table__: t.create(c))
        for when in ("INSERT", "UPDATE"):
            await conn.execute(text(
                f"CREATE TRIGGER ck_orders_status_{when.lower()} BEFORE {when} ON orders "
                f"WHEN NEW.status NOT IN ({allowed}) "
                "BEGIN SELECT RAISE(ABORT, 'violates check constraint ck_orders_status'); END"
            ))
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


class FakeBroker:
    """Records every broker call; answers like Alpaca for the guarded paths."""

    def __init__(self, *, position=None, position_error=None, existing=None,
                 lookup_error=None, place_error=None):
        self.position, self.position_error = position, position_error
        self.existing, self.lookup_error = existing, lookup_error
        self.place_error = place_error
        self.calls: list[tuple] = []

    async def find_order_by_client_order_id(self, client_order_id):
        self.calls.append(("lookup", client_order_id))
        if self.lookup_error is not None:
            raise self.lookup_error
        return self.existing

    async def get_position(self, symbol):
        self.calls.append(("position", symbol))
        if self.position_error is not None:
            raise self.position_error
        return self.position

    async def place_order(self, **order):
        self.calls.append(("POST", order))
        if self.place_error is not None:
            raise self.place_error
        return ack(order["client_order_id"], order["symbol"], order["side"], order["qty"])

    async def reconcile_order_acknowledgement(self, client_order_id):
        raise AssertionError("lookup-only reconciliation is not part of these flows")

    def kinds(self):
        return [call[0] for call in self.calls]


def ack(key, symbol, side, qty, status="accepted"):
    return {"id": BROKER_ID, "client_order_id": key, "symbol": symbol, "side": side,
            "qty": str(qty), "status": status, "filled_qty": "0", "filled_avg_price": None}


def long_position(qty, available=None, symbol="AAPL"):
    return {"symbol": symbol, "qty": str(qty), "side": "long",
            "qty_available": str(qty if available is None else available)}


@pytest.fixture
def wired(monkeypatch, sessions):
    """A real worker and dispatcher bound to the SQLite store and a fake broker."""
    from backend import websocket
    from backend.integrations import alpaca_broker
    from backend.services import trading_execution_mode

    monkeypatch.setenv("ORGANISM_LONG_ONLY", "true")
    monkeypatch.setattr(order_service_mod, "_circuit_breaker", None)
    dispatcher = alpaca_outbox.AlpacaOutboxDispatcher.__new__(alpaca_outbox.AlpacaOutboxDispatcher)
    dispatcher.use_mock_broker = False
    monkeypatch.setattr(alpaca_outbox, "get_alpaca_outbox_dispatcher", lambda: dispatcher)
    monkeypatch.setattr(trading_execution_mode, "get_trading_execution_mode", lambda: SimpleNamespace(
        mode="execute", source="offline-test", overridden=True))
    notices = AsyncMock()
    monkeypatch.setattr(websocket, "broadcaster", SimpleNamespace(broadcast_to_topic=notices))
    log = MagicMock()
    monkeypatch.setattr(worker_mod, "logger", log)

    @asynccontextmanager
    async def context():
        async with sessions() as session:
            yield session

    monkeypatch.setattr("backend.infra.db.get_session_context", context)

    def bind(broker):
        monkeypatch.setattr(alpaca_broker, "get_alpaca_broker_client", lambda: broker)
        worker = OutboxWorker(sessions, initial_backoff=0, jitter_factor=0, max_retries=3)
        worker.use_mock_broker = False
        return worker

    return SimpleNamespace(bind=bind, notices=notices, log=log, sessions=sessions)


async def submit_exit(sessions, qty=100, symbol="AAPL"):
    """What OrganismLiveEngine._submit_exit_order sends to OrderService."""
    result = await OrderService(sessionmaker=sessions).submit_symbol_order(
        symbol=symbol, side="sell", qty=qty, order_type="market", tif="day", reduce_only=True,
        idempotency_key=f"organism_exit_{symbol}_20261005_s1_t200_stop_loss_q{qty}_{uuid.uuid4().hex[:6]}",
        attributes={"source": "organism", "reason": "stop_loss", "tick": 200},
    )
    return result["order_id"]


async def submit_entry(sessions, qty=10, symbol="AAPL"):
    """What OrganismLiveEngine._submit_entry_order sends to OrderService."""
    result = await OrderService(sessionmaker=sessions).submit_symbol_order(
        symbol=symbol, side="buy", qty=qty, order_type="limit", tif="day", limit_price=101.25,
        idempotency_key=f"organism_{symbol}_20261005_s1_t10_organism_entry_buy_q{qty}_{uuid.uuid4().hex[:6]}",
        attributes={"source": "organism", "reason": "organism_entry", "tick": 10,
                    "entry_source": "alpha", "strategy_id": "alpha_baseline", "evidence_tier": 0},
    )
    return result["order_id"]


async def enqueue_legacy(sessions, *, side, qty, symbol="AAPL", nested=False, attempts=0,
                         last_error=None, age=timedelta(0)):
    """An event queued by the pre-release OrderService: no reduce_only or intent.

    Same order row and the old ``add_order_submit_event`` keyword set; ``age``
    backdates the order and the outbox row (an event stranded across a deploy).
    """
    exit_order = side == "sell"
    key = (f"organism_exit_{symbol}_20261002_s0_t90_eod_flatten_q{qty}" if exit_order
           else f"organism_{symbol}_20261002_s0_t40_organism_entry_buy_q{qty}")
    attributes = ({"source": "organism", "reason": "eod_flatten", "tick": 90} if exit_order else
                  {"source": "organism", "reason": "organism_entry", "tick": 40})
    async with sessions() as session:
        order = await OrdersRepo(session).upsert_by_idempotency(
            client_key=key, symbol=symbol, side=side, qty=Decimal(qty), order_type="market",
            tif="day", attributes=attributes, user_id="system")
        payload = {"symbol": symbol, "side": side, "qty": str(qty), "order_type": "market",
                   "tif": "day", "client_key": key, "attributes": attributes}
        if nested:
            event_id = await OutboxRepo(session).enqueue(
                topic="order.submitted", payload={"payload": {"order_id": str(order.id), **payload}})
        else:
            event_id = await OutboxRepo(session).add_order_submit_event(order_id=str(order.id), **payload)
        then = datetime.now(UTC) - age
        await session.execute(update(OutboxEvent).where(OutboxEvent.id == uuid.UUID(str(event_id)))
                              .values(attempts=attempts, last_error=last_error, created_at=then,
                                      next_attempt_at=datetime.now(UTC) - timedelta(seconds=1)))
        await session.execute(update(Order).where(Order.id == order.id)
                              .values(submitted_at=then, created_at=then))
        await session.commit()
        return str(order.id)


async def process_one(worker):
    claimed = await worker._get_pending_events()
    assert len(claimed) == 1
    await worker._process_event(claimed[0])
    return claimed[0]


async def state(sessions, order_id):
    async with sessions() as session:
        order = await session.get(Order, uuid.UUID(order_id))
        event = (await session.execute(select(OutboxEvent))).scalars().one()
        return order, event


def criticals(log):
    return [call.args[0] for call in log.critical.call_args_list]


async def assert_refused(wired, worker, order_id, reason, headline):
    order, event = await state(wired.sessions, order_id)
    assert (order.status, order.broker_order_id, order.filled_qty) == ("rejected", None, Decimal(0))
    refusal = order.attributes["dispatch_refusal"]
    assert refusal["reason"] == reason and refusal["outbox_event_id"] == str(event.id)
    assert event.status == "failed" and event.last_error.startswith(f"DISPATCH_REFUSED:{reason}")
    [message] = criticals(wired.log)
    assert message.startswith(headline)
    assert wired.log.critical.call_args.kwargs["outcome"] == "order_marked_rejected"
    assert wired.notices.await_args.args[1]["type"] == "order.rejected"
    assert await worker._get_pending_events() == []  # never retried
    return order, event


# ── OrderService declares the intent ──────────────────────────────────────────
async def test_order_service_declares_exit_and_entry_intent(sessions, monkeypatch):
    monkeypatch.setattr(order_service_mod, "_circuit_breaker", None)
    exit_id = await submit_exit(sessions)
    entry_id = await submit_entry(sessions)
    manual = await OrderService(sessionmaker=sessions).submit_symbol_order(
        symbol="AAPL", side="sell", qty=5, idempotency_key="close-abc12345-def67890",
        attributes={"close_position": True, "close_type": "manual"},
    )
    async with sessions() as session:
        events = {e.payload["order_id"]: e.payload
                  for e in (await session.execute(select(OutboxEvent))).scalars()}
    assert (events[exit_id]["intent"], events[exit_id]["reduce_only"]) == ("exit", True)
    assert (events[entry_id]["intent"], events[entry_id]["reduce_only"]) == ("entry", False)
    # Undeclared callers stay undeclared; the dispatcher's fallback decides.
    assert "intent" not in events[manual["order_id"]]
    assert events[manual["order_id"]]["reduce_only"] is False
    assert all("created_at" not in payload for payload in events.values())


# ── C01-01: exits never go beyond the broker's free long position ─────────────
async def test_exit_with_sufficient_long_position_is_sent(wired):
    broker = FakeBroker(position=long_position(100))  # free == order qty is enough
    worker = wired.bind(broker)
    order_id = await submit_exit(wired.sessions, qty=100)
    await process_one(worker)
    assert broker.kinds() == ["lookup", "position", "POST"]
    assert broker.calls[2][1]["side"] == "sell" and broker.calls[2][1]["qty"] == 100
    order, event = await state(wired.sessions, order_id)
    assert event.status == "sent"
    assert (order.status, order.broker_order_id) == ("accepted", BROKER_ID)
    assert criticals(wired.log) == []


@pytest.mark.parametrize("position,reason,headline", [
    (None, "exit_position_flat", DUPLICATE),  # 404: an earlier exit already filled
    ({"symbol": "AAPL", "qty": "-100", "side": "short", "qty_available": "-100"},
     "exit_position_short", REFUSED),
    (long_position(100, available=40), "exit_exceeds_free_long_position", REFUSED),
], ids=["flat_duplicate", "short", "shares_held_by_open_sell"])
async def test_exit_beyond_free_long_position_is_not_sent_and_is_terminal(
        wired, position, reason, headline):
    broker = FakeBroker(position=position)
    worker = wired.bind(broker)
    order_id = await submit_exit(wired.sessions, qty=100)
    await process_one(worker)
    assert broker.kinds() == ["lookup", "position"]  # client key looked up first, no POST
    order, event = await assert_refused(wired, worker, order_id, reason, headline)
    assert order.attributes["dispatch_refusal"]["intent"] == "exit" and event.attempts == 0
    if reason == "exit_position_flat":
        assert REFUSED not in criticals(wired.log)[0]


@pytest.mark.parametrize("failure", ["position_read", "client_order_lookup"])
async def test_exit_when_broker_read_fails_is_not_sent_and_stays_retryable(wired, failure):
    # The text carries every validation keyword: it must still be retried.
    error = HTTPException(503, "Alpaca API unavailable: invalid gateway, not found, require retry")
    broker = FakeBroker(position=long_position(100),
                        position_error=error if failure == "position_read" else None,
                        lookup_error=error if failure == "client_order_lookup" else None)
    worker = wired.bind(broker)
    order_id = await submit_exit(wired.sessions, qty=100)
    await process_one(worker)
    assert "POST" not in broker.kinds()
    order, event = await state(wired.sessions, order_id)
    assert (order.status, order.broker_order_id) == ("accepted", None)  # untouched
    assert event.status == "pending" and event.attempts == 1
    assert event.last_error == f"dispatch_guard_unavailable:{failure}:HTTPException"
    assert criticals(wired.log) == []
    # Once the broker answers again, the next attempt sends it.
    broker.position_error = broker.lookup_error = None
    async with wired.sessions() as session:
        stored = await session.get(OutboxEvent, event.id)
        stored.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    await process_one(worker)
    assert broker.kinds().count("POST") == 1
    order, event = await state(wired.sessions, order_id)
    assert (event.status, order.broker_order_id) == ("sent", BROKER_ID)


async def test_exit_already_at_broker_is_attached_not_resent(wired):
    broker = FakeBroker(position=None)  # flat now: the earlier POST filled it
    worker = wired.bind(broker)
    order_id = await submit_exit(wired.sessions, qty=100)
    async with wired.sessions() as session:
        key = (await session.get(Order, uuid.UUID(order_id))).client_idempotency_key
    broker.existing = ack(key, "AAPL", "sell", 100)
    await process_one(worker)
    assert broker.kinds() == ["lookup"]  # no position read, no POST
    order, event = await state(wired.sessions, order_id)
    assert event.status == "sent"
    assert (order.status, order.broker_order_id) == ("accepted", BROKER_ID)
    assert "dispatch_refusal" not in (order.attributes or {})
    assert criticals(wired.log) == []


async def test_insufficient_qty_rejection_is_terminal_not_retried(wired):
    broker = FakeBroker(position=long_position(100), place_error=INSUFFICIENT_QTY)
    worker = wired.bind(broker)
    order_id = await submit_exit(wired.sessions, qty=100)
    await process_one(worker)
    assert broker.kinds() == ["lookup", "position", "POST"]
    await assert_refused(wired, worker, order_id, "broker_rejected_insufficient_qty",
                         "ORDER REJECTED BY BROKER (insufficient qty)")
    assert broker.kinds().count("POST") == 1


async def test_lookup_body_that_does_not_confirm_the_key_is_never_sent(wired):
    broker = FakeBroker(position=long_position(100),
                        existing={"id": BROKER_ID, "status": "accepted", "client_order_id": "other"})
    worker = wired.bind(broker)
    order_id = await submit_exit(wired.sessions, qty=100)
    await process_one(worker)
    assert broker.kinds() == ["lookup"]
    order, event = await state(wired.sessions, order_id)
    # Treated as an unresolved acknowledgement: lookup-only from now on.
    assert event.status == "pending" and event.last_error.startswith("INTRA_BROKER_ACK:")
    assert order.status == "accepted"


async def test_refusal_pages_only_after_its_commit(wired, monkeypatch):
    broker = FakeBroker(position=None)
    worker = wired.bind(broker)
    order_id = await submit_exit(wired.sessions, qty=100)
    claimed = await worker._get_pending_events()
    original_commit, calls = AsyncSession.commit, {"n": 0}

    async def fail_first_commit(session):
        calls["n"] += 1
        if calls["n"] == 1:  # the refusal's transaction
            raise RuntimeError("offline injected commit failure")
        return await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", fail_first_commit)
    await worker._process_event(claimed[0])
    assert calls["n"] == 2  # refusal commit failed; the retry schedule committed
    order, event = await state(wired.sessions, order_id)
    assert order.status == "accepted" and event.status == "pending" and event.attempts == 1
    assert criticals(wired.log) == []
    assert "POST" not in broker.kinds()


async def test_refusal_never_overwrites_a_row_with_broker_evidence(wired):
    worker = wired.bind(FakeBroker())
    order_id = await submit_exit(wired.sessions, qty=100)
    async with wired.sessions() as session:
        row = await session.get(Order, uuid.UUID(order_id))
        row.broker_order_id = BROKER_ID
        await session.commit()
    claimed = await worker._get_pending_events()
    await worker._finalize_refused_dispatch(claimed[0], alpaca_outbox._refused(
        {"order_id": order_id}, reason="exit_position_flat", detail="synthetic", intent="exit"))
    order, event = await state(wired.sessions, order_id)
    assert (order.status, order.broker_order_id) == ("accepted", BROKER_ID)
    assert event.status == "failed"
    assert wired.log.critical.call_args.kwargs["outcome"] == "order_row_has_broker_evidence"
    assert criticals(wired.log)[0].startswith("EXIT REFUSAL CONFLICTS WITH BROKER EVIDENCE")


# ── Entries are dispatched exactly as before ──────────────────────────────────
@pytest.mark.parametrize("legacy", [False, True], ids=["declared", "pre_release_payload"])
async def test_entries_are_dispatched_as_before_even_late_and_after_hours(wired, monkeypatch, legacy):
    monkeypatch.setattr(alpaca_outbox, "is_market_open", lambda *a, **k: False)
    broker = FakeBroker()
    worker = wired.bind(broker)
    if legacy:
        order_id = await enqueue_legacy(wired.sessions, side="buy", qty=10, age=timedelta(minutes=10))
    else:
        order_id = await submit_entry(wired.sessions)
        async with wired.sessions() as session:
            await session.execute(update(OutboxEvent).values(
                created_at=datetime.now(UTC) - timedelta(minutes=10)))
            await session.commit()
    await process_one(worker)
    assert broker.kinds() == ["POST"]  # no guard reads, no refusal
    assert broker.calls[0][1]["side"] == "buy" and broker.calls[0][1]["tif"] == "day"
    order, event = await state(wired.sessions, order_id)
    assert (event.status, order.status, order.broker_order_id) == ("sent", "accepted", BROKER_ID)
    assert criticals(wired.log) == []


# ── In-flight events queued before this release (no reduce_only / intent) ─────
@pytest.mark.parametrize("position,sent", [(None, False), (long_position(12), True)],
                         ids=["flat_duplicate_refused", "held_long_sent"])
async def test_pre_release_exit_payload_is_guarded_by_the_long_only_rule(wired, position, sent):
    broker = FakeBroker(position=position)
    worker = wired.bind(broker)
    order_id = await enqueue_legacy(wired.sessions, side="sell", qty=12, age=timedelta(minutes=31))
    await process_one(worker)
    if sent:
        assert broker.kinds() == ["lookup", "position", "POST"]
        order, event = await state(wired.sessions, order_id)
        assert (event.status, order.broker_order_id) == ("sent", BROKER_ID)
    else:
        assert broker.kinds() == ["lookup", "position"]
        order, _ = await assert_refused(wired, worker, order_id, "exit_position_flat", DUPLICATE)
        assert order.attributes["dispatch_refusal"]["intent"] == "exit"


async def test_pre_release_exit_is_guarded_when_long_only_is_unset(wired, monkeypatch):
    monkeypatch.delenv("ORGANISM_LONG_ONLY", raising=False)  # the default is long-only
    broker = FakeBroker(position=None)
    worker = wired.bind(broker)
    order_id = await enqueue_legacy(wired.sessions, side="sell", qty=12)
    await process_one(worker)
    assert "POST" not in broker.kinds()
    await assert_refused(wired, worker, order_id, "exit_position_flat", DUPLICATE)


async def test_undeclared_sell_is_not_guarded_when_long_only_is_off(wired, monkeypatch):
    monkeypatch.setenv("ORGANISM_LONG_ONLY", "false")  # a sell may then open a short on purpose
    broker = FakeBroker(position=None)
    worker = wired.bind(broker)
    order_id = await enqueue_legacy(wired.sessions, side="sell", qty=12)
    await process_one(worker)
    assert broker.kinds() == ["POST"]
    order, event = await state(wired.sessions, order_id)
    assert (event.status, order.broker_order_id) == ("sent", BROKER_ID)


async def test_pre_release_nested_exit_payload_is_guarded(wired):
    broker = FakeBroker(position=None)
    worker = wired.bind(broker)
    order_id = await enqueue_legacy(wired.sessions, side="sell", qty=12, nested=True)
    await process_one(worker)
    assert broker.kinds() == ["lookup", "position"]
    await assert_refused(wired, worker, order_id, "exit_position_flat", DUPLICATE)
    assert wired.log.critical.call_args.kwargs["symbol"] == "AAPL"


async def test_pre_release_exit_already_retrying_is_guarded(wired):
    broker = FakeBroker(position=long_position(12, available=0))  # an earlier sell holds them
    worker = wired.bind(broker)
    order_id = await enqueue_legacy(wired.sessions, side="sell", qty=12, attempts=2,
                                    last_error="503: Alpaca API unavailable after 3 retries")
    await process_one(worker)
    assert broker.kinds() == ["lookup", "position"]
    _, event = await assert_refused(wired, worker, order_id, "exit_exceeds_free_long_position", REFUSED)
    assert event.attempts == 2


async def test_retryable_result_is_retried_even_with_validation_words(wired):
    """The worker's retryable branch runs before its validation-keyword dead-letter check."""
    worker = wired.bind(FakeBroker())
    order_id = await submit_exit(wired.sessions)
    text_with_keywords = "422: invalid order, not found, require, validation"
    worker._process_order_submitted = AsyncMock(return_value={
        "success": False, "retryable": True, "status": "failed", "error": text_with_keywords})
    await process_one(worker)
    order, event = await state(wired.sessions, order_id)
    assert (event.status, event.attempts, event.last_error) == ("pending", 1, text_with_keywords)
    assert order.status == "accepted" and criticals(wired.log) == []


async def test_status_constraint_fixture_rejects_statuses_outside_the_migration(sessions, monkeypatch):
    """'rejected' passes the real ck_orders_status set; 'shadow' would not."""
    from sqlalchemy.exc import IntegrityError
    monkeypatch.setattr(order_service_mod, "_circuit_breaker", None)
    order_id = await submit_exit(sessions)
    assert "rejected" in _allowed_order_statuses()
    async with sessions() as session:
        row = await session.get(Order, uuid.UUID(order_id))
        row.status = "shadow"
        with pytest.raises(IntegrityError, match="ck_orders_status"):
            await session.commit()


async def test_lookup_only_events_skip_the_exit_guard(monkeypatch):
    monkeypatch.setenv("ORGANISM_LONG_ONLY", "true")

    class LookupBroker(FakeBroker):
        async def reconcile_order_acknowledgement(self, client_order_id):
            self.calls.append(("reconcile", client_order_id))
            return ack(client_order_id, "AAPL", "sell", 100)

    broker = LookupBroker(position=None)
    monkeypatch.setattr("backend.integrations.alpaca_broker.get_alpaca_broker_client", lambda: broker)
    dispatcher = alpaca_outbox.AlpacaOutboxDispatcher.__new__(alpaca_outbox.AlpacaOutboxDispatcher)
    dispatcher.use_mock_broker = False
    result = await dispatcher._dispatch_to_alpaca_broker({
        "order_id": "x", "symbol": "AAPL", "side": "sell", "qty": "100", "reduce_only": True,
        "intent": "exit", "client_key": "organism_exit_AAPL_y", "_broker_ack_lookup_only": True})
    assert result["success"] is True and broker.kinds() == ["reconcile"]


async def test_declared_entry_sell_skips_the_exit_guard(monkeypatch):
    """A declared short entry (strong-short path) is not treated as an exit."""
    monkeypatch.setenv("ORGANISM_LONG_ONLY", "true")
    broker = FakeBroker()
    outcome = await alpaca_outbox._exit_send_guard(
        broker, {"order_id": "x", "side": "sell", "intent": "entry", "reduce_only": False},
        symbol="SPY", side="sell", qty=5, client_key="organism_SPY_x")
    assert outcome == alpaca_outbox._GuardOutcome() and broker.calls == []


# ── Pure rules ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("payload,long_only,expected", [
    ({"side": "sell", "reduce_only": True}, "true", ("exit", "declared")),
    ({"side": "buy", "intent": "exit"}, "true", ("exit", "declared")),  # buy-to-cover
    ({"side": "sell", "intent": "entry", "reduce_only": False}, "true", ("entry", "declared")),
    ({"side": "buy", "attributes": {"close_position": True}}, "true", ("exit", "declared")),
    ({"side": "sell"}, "true", ("exit", "long_only_side")),
    ({"side": "SELL", "reduce_only": False}, "true", ("exit", "long_only_side")),
    ({"side": "buy"}, "true", (None, "undeclared")),
    ({"side": "sell", "reduce_only": False}, "false", (None, "undeclared")),
    ({"side": "sell", "reduce_only": True}, "false", ("exit", "declared")),
])
def test_intent_resolution(monkeypatch, payload, long_only, expected):
    monkeypatch.setenv("ORGANISM_LONG_ONLY", long_only)
    assert alpaca_outbox.resolve_order_intent(payload) == expected


@pytest.mark.parametrize("position,expected", [
    (None, ("flat", Decimal(0))),
    ({"qty": "0", "side": "long"}, ("flat", Decimal(0))),
    ({"qty": "100", "side": "long", "qty_available": "40"}, ("long", Decimal(40))),
    ({"qty": "100", "side": "long"}, ("long", Decimal(100))),
    ({"qty": "100", "side": "long", "qty_available": "250"}, ("long", Decimal(100))),
    ({"qty": "12.5", "side": "long", "qty_available": "12.5"}, ("long", Decimal("12.5"))),
    ({"qty": "-100", "side": "short", "qty_available": "-100"}, ("short", Decimal(0))),
    ({"qty": "7"}, ("long", Decimal(7))),
    ({"qty": "-7"}, ("short", Decimal(0))),
])
def test_broker_long_position(position, expected):
    assert alpaca_outbox.broker_long_position(position) == expected


@pytest.mark.parametrize("position", [[], {"side": "long"}, {"qty": "x", "side": "long"},
                                      {"qty": "10", "side": "sideways"}, {"qty": True},
                                      {"qty": "NaN", "side": "long"}])
def test_malformed_position_is_a_failed_read(position):
    with pytest.raises(ValueError):
        alpaca_outbox.broker_long_position(position)


def test_insufficient_qty_classification():
    assert alpaca_outbox.is_insufficient_qty_rejection(INSUFFICIENT_QTY)
    assert not alpaca_outbox.is_insufficient_qty_rejection(HTTPException(429, "insufficient qty"))
    assert not alpaca_outbox.is_insufficient_qty_rejection(HTTPException(503, "insufficient qty"))
    assert not alpaca_outbox.is_insufficient_qty_rejection(HTTPException(403, "insufficient buying power"))
    assert not alpaca_outbox.is_insufficient_qty_rejection(RuntimeError("insufficient qty"))


# ── Strict client-key lookup on the real broker client ────────────────────────
def _client(*responses):
    broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
    broker.base_url = "https://broker.invalid"
    broker.is_paper = True
    broker._make_request_with_retry = AsyncMock(side_effect=responses)
    return broker


async def test_strict_client_order_lookup_separates_absent_from_unavailable():
    key = "organism_exit_AAPL_x"
    assert await _client(HTTPException(404, "order not found")).find_order_by_client_order_id(key) is None
    found = ack(key, "AAPL", "sell", 1)
    client = _client(httpx.Response(200, json=found))
    assert await client.find_order_by_client_order_id(key) == found
    assert client._make_request_with_retry.await_args.args[1].endswith("/v2/orders:by_client_order_id")
    assert client._make_request_with_retry.await_args.kwargs == {"params": {"client_order_id": key}}
    with pytest.raises(BrokerAcknowledgementUnresolved):
        await _client(httpx.Response(200, json=ack("other", "AAPL", "sell", 1))).find_order_by_client_order_id(key)
    for failure in (HTTPException(503, "unavailable"), HTTPException(422, "unprocessable")):
        with pytest.raises(HTTPException) as raised:
            await _client(failure).find_order_by_client_order_id(key)
        assert not isinstance(raised.value, BrokerAcknowledgementUnresolved)
    with pytest.raises(BrokerAcknowledgementUnresolved):
        await _client().find_order_by_client_order_id("")
