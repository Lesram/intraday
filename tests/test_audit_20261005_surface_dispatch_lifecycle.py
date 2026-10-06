"""Audit 2026-10-05 C04-01 / C01-04: dispatch lifecycle of dead-lettered and late entries.

C04-01: a dead-lettered order is recorded on its row in the dead-letter
transaction; after a settle delay, and only while no other delivery of the order
is pending, the outbox worker looks it up by its client key. Two of Alpaca's
order-not-found answers, at least DEAD_LETTER_CONFIRM_SECONDS apart and with no
other answer between them, finalize the row ('rejected', or 'expired' for a
refused entry) with the absence proof, and only that proof lets the engine's
hashed pending-entry resolution (operator_cancellation) release the identity,
never on the tick that registered it. Any other 404 is not absence. C01-04: a
stale or after-session entry is refused at dispatch and goes through the same
lifecycle; exits never are. Review follow-ups: a fill on a finalized row pages,
one failing row never stops the sweep, refusals are counted and page once per
session above the threshold.

Offline: SQLite with ck_orders_status enforced by triggers built from the
migration's allowed set, and a fake broker client. The real OrderService,
OutboxWorker, AlpacaOutboxDispatcher, operator_cancellation and the real
OrganismLiveEngine (initialized offline, its own reconciliation methods) are
used. No network, no credentials, no saved brain state.
"""
from __future__ import annotations

import ast
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import uuid

from fastapi import HTTPException
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import backend.infra.outbox_worker as worker_mod
from backend.infra.outbox import OutboxRepo
from backend.infra.outbox_worker import OutboxWorker, entry_dispatch_refusal
from backend.infra.repositories.orders import OrdersRepo
from backend.infra.schemas import (
    AuditLog, Execution, Order, OutboxEvent, Position, PositionLot, RealizedTrade,
)
from backend.integrations import alpaca_outbox, alpaca_stream
from backend.integrations.alpaca_broker import (
    BROKER_ACK_STATE_PREFIX,
    BrokerAcknowledgementUnresolved,
    ClientOrderNotFoundUnconfirmed,
)
from backend.organism import operator_cancellation as cancellation
from backend.organism.live_engine import OrganismLiveEngine
from backend.organism.live_engine_fills import ACCOUNTABLE_TERMINAL_STATUSES
from backend.services import order_service as order_service_mod
from backend.services.order_service import OrderService
from backend.utils.market_hours import ET

REPO = Path(__file__).resolve().parents[1]
PAPER = "https://paper-api.alpaca.markets"
BROKER_ID = "0f6b8c1e-2d4a-4c5b-9e7f-8a9b0c1d2e3f"
# Tuesday 2026-10-06 10:30 ET: inside a regular NYSE session.
T0 = datetime(2026, 10, 6, 14, 30, tzinfo=UTC)
SETTLED = timedelta(seconds=worker_mod.DEAD_LETTER_SETTLE_SECONDS + 1)
CONFIRMED = timedelta(seconds=worker_mod.DEAD_LETTER_CONFIRM_SECONDS)
# Alpaca's order-not-found answer to GET /v2/orders:by_client_order_id, as evidence.
NOT_FOUND = {"http_status": 404, "code": 40410000, "message": "order not found for organism_test"}


def endpoint_404():
    """A 404 that is not Alpaca's order-not-found answer (an unknown route)."""
    return ClientOrderNotFoundUnconfirmed(
        "message_mismatch", {"http_status": 404, "body": '{"code":40410000,"message":"endpoint not found"}'})


BREAKER_OPEN = HTTPException(503, "Alpaca broker circuit breaker OPEN — refusing to submit; "
                                  "will resume after cooldown.")
BUSINESS_403 = HTTPException(403, 'Alpaca API error: {"code":40310000,"message":"insufficient buying power"}')
UNPROCESSABLE_422 = HTTPException(422, 'Alpaca API error: {"code":42210000,"message":"qty must be > 0"}')


def _allowed_order_statuses() -> tuple[str, ...]:
    """The production ck_orders_status set, read from the migration source."""
    path = REPO / "backend/migrations/versions/20260503_000002_xx_2_widen_orders_status_check.py"
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "_WIDENED_STATUSES":
            return tuple(ast.literal_eval(node.value))
    raise AssertionError("ck_orders_status set not found")


@pytest_asyncio.fixture
async def sessions(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "lifecycle.sqlite"))
    allowed = ", ".join(f"'{status}'" for status in _allowed_order_statuses())
    async with engine.begin() as conn:
        for table in (Order, Execution, PositionLot, RealizedTrade, AuditLog, OutboxEvent, Position):
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
    """Records every call; a paper broker as far as operator_cancellation can tell."""

    is_paper = True
    base_url = PAPER

    def __init__(self, *, place_error=None, lookups=None, position=None):
        self.place_error = place_error
        self.lookups = list(lookups or [])  # consumed per client-key lookup; default 404
        self.position = position
        self.calls: list[tuple] = []

    async def place_order(self, **order):
        self.calls.append(("POST", order["client_order_id"]))
        if self.place_error is not None:
            raise self.place_error
        return ack(order["client_order_id"], order["symbol"], order["side"], order["qty"])

    async def find_order_by_client_order_id(self, client_order_id):
        self.calls.append(("lookup", client_order_id))
        outcome = self.lookups.pop(0) if self.lookups else None
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            return await outcome(client_order_id)
        return outcome

    async def lookup_order_by_client_order_id(self, client_order_id):
        """The absence check's strict lookup: None in ``lookups`` is Alpaca's order-not-found answer."""
        found = await self.find_order_by_client_order_id(client_order_id)
        return (found, None) if found is not None else (None, dict(NOT_FOUND))

    async def get_position(self, symbol):
        self.calls.append(("position", symbol))
        return self.position

    async def reconcile_order_acknowledgement(self, client_order_id):
        self.calls.append(("reconcile", client_order_id))
        return ack(client_order_id, "MSFT", "buy", 3)

    async def get_order(self, order_id):
        self.calls.append(("get_order", order_id))
        raise AssertionError("an undelivered order has no broker id to confirm")

    async def cancel_order(self, order_id):
        self.calls.append(("cancel", order_id))

    def kinds(self):
        return [call[0] for call in self.calls]


def ack(key, symbol, side, qty, status="accepted"):
    return {"id": BROKER_ID, "client_order_id": key, "symbol": symbol, "side": side,
            "qty": str(qty), "status": status, "filled_qty": "0", "filled_avg_price": None}


@pytest.fixture
def wired(monkeypatch, sessions):
    """A real worker and dispatcher bound to the SQLite store, a fake broker and a clock."""
    from backend import websocket
    from backend.integrations import alpaca_broker
    from backend.services import trading_execution_mode

    monkeypatch.setenv("ORGANISM_LONG_ONLY", "true")
    monkeypatch.setattr(order_service_mod, "_circuit_breaker", None)
    dispatcher = alpaca_outbox.AlpacaOutboxDispatcher.__new__(alpaca_outbox.AlpacaOutboxDispatcher)
    dispatcher.use_mock_broker = False
    monkeypatch.setattr(alpaca_outbox, "get_alpaca_outbox_dispatcher", lambda: dispatcher)
    state = SimpleNamespace(now=T0, mode="execute", broker=None)
    monkeypatch.setattr(trading_execution_mode, "get_trading_execution_mode", lambda: SimpleNamespace(
        mode=state.mode, source="offline-test", overridden=True))
    monkeypatch.setattr(worker_mod, "_now_utc", lambda: state.now)
    monkeypatch.setattr(alpaca_broker, "get_alpaca_broker_client", lambda: state.broker)
    notices = AsyncMock()
    monkeypatch.setattr(websocket, "broadcaster", SimpleNamespace(broadcast_to_topic=notices))
    log = MagicMock()
    monkeypatch.setattr(worker_mod, "logger", log)

    @asynccontextmanager
    async def context():
        async with sessions() as session:
            yield session

    monkeypatch.setattr("backend.infra.db.get_session_context", context)

    def bind(broker, max_retries=2):
        state.broker = broker
        worker = OutboxWorker(sessions, initial_backoff=0, jitter_factor=0, max_retries=max_retries)
        worker.use_mock_broker = False
        return worker

    return SimpleNamespace(bind=bind, notices=notices, log=log, sessions=sessions, state=state)


async def set_event_time(sessions, order_id, created_at, **values):
    """Give the order's outbox event its intent time (OutboxEvent.created_at).

    Stored in UTC, as the app writes it: SQLite keeps no offset (PostgreSQL
    timestamptz does), so an ET-aware stamp would otherwise read back shifted.
    """
    async with sessions() as session:
        events = [e for e in (await session.execute(select(OutboxEvent))).scalars()
                  if worker_mod._flat_payload(e.payload).get("order_id") == order_id]
        assert len(events) == 1
        await session.execute(update(OutboxEvent).where(OutboxEvent.id == events[0].id).values(
            created_at=created_at.astimezone(UTC),
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1), **values))
        await session.commit()


async def submit_entry(wired, symbol="MSFT", qty=3, *, created_at=None):
    """What OrganismLiveEngine._submit_entry_order sends to OrderService."""
    result = await OrderService(sessionmaker=wired.sessions).submit_symbol_order(
        symbol=symbol, side="buy", qty=qty, order_type="limit", tif="day", limit_price=500.25,
        idempotency_key=f"organism_{symbol}_20261006_s1_t10_organism_entry_buy_q{qty}_{uuid.uuid4().hex[:6]}",
        attributes={"source": "organism", "reason": "organism_entry", "tick": 10,
                    "entry_source": "alpha", "strategy_id": "alpha_baseline"},
    )
    await set_event_time(wired.sessions, result["order_id"],
                         created_at or wired.state.now - timedelta(seconds=1))
    return result["order_id"]


async def submit_exit(wired, symbol="MSFT", qty=3, *, created_at=None):
    """What OrganismLiveEngine._submit_exit_order sends to OrderService."""
    result = await OrderService(sessionmaker=wired.sessions).submit_symbol_order(
        symbol=symbol, side="sell", qty=qty, order_type="market", tif="day", reduce_only=True,
        idempotency_key=f"organism_exit_{symbol}_20261006_s1_t200_stop_loss_q{qty}_{uuid.uuid4().hex[:6]}",
        attributes={"source": "organism", "reason": "stop_loss", "tick": 200},
    )
    await set_event_time(wired.sessions, result["order_id"],
                         created_at or wired.state.now - timedelta(seconds=1))
    return result["order_id"]


async def drive(worker, limit=10):
    """Process due events until none is due (retries are due at once: zero backoff)."""
    for _ in range(limit):
        claimed = await worker._get_pending_events()
        if not claimed:
            return
        for event in claimed:
            await worker._process_event(event)


async def load(sessions, order_id):
    async with sessions() as session:
        order = await session.get(Order, uuid.UUID(order_id))
        events = [e for e in (await session.execute(select(OutboxEvent))).scalars()
                  if worker_mod._flat_payload(e.payload).get("order_id") == order_id]
        return order, (events[0] if events else None)


def criticals(log):
    return [call.args[0] for call in log.critical.call_args_list]


def record_of(order):
    return (order.attributes or {}).get("outbox_dead_letter")


async def lifecycle_engine(wired, tmp_path, *, symbol, order_id, tick=500, registered=495,
                           brain="brain", metadata=True):
    """A real engine initialized offline (shadow mode only while it starts), tracking one entry."""
    from tests.test_operator_controls import initialize_offline

    wired.state.mode = "shadow"
    engine = OrganismLiveEngine(
        data_client=MagicMock(), order_service=SimpleNamespace(submit_symbol_order=AsyncMock()),
        positions_service=SimpleNamespace(get_all_positions=AsyncMock(return_value={})),
        brain_dir=str(tmp_path / brain), universe=[symbol, "SPY"], sessionmaker=wired.sessions,
    )
    engine.market_scanner = None
    engine._streaming_provider = None
    await initialize_offline(engine)
    wired.state.mode = "execute"
    engine._passes_liquidity_gate = lambda *a, **k: True
    if order_id is not None:
        engine._tick_count = tick
        engine._pending_entry = {symbol: registered}
        engine._pending_entry_order_ids = {symbol: order_id}
        if metadata:
            engine._entry_metadata[symbol] = {
                "entry_order_id": order_id, "entry_price": 500.25, "entry_tick": registered,
                "direction": 1.0, "entry_source": "alpha", "strategy_id": "alpha_baseline",
                "filled_shares": 3, "entry_time": datetime.now(UTC).timestamp(), "confidence": 0.6,
            }
    return engine


def gate(engine, symbol):
    return engine._passes_entry_gates(symbol, 1.0, {}, set(), set(),
                                      fitness_gate=0.0, min_trades_for_fitness=10**6)


async def advance_ticks(engine, n=1):
    for _ in range(n):
        engine._tick_count += 1
        await engine._reconcile_fills({})
        await engine._reconcile_pending_entry_orders()


async def finalize(worker, wired, at=None):
    """The absence check to its end: an order-not-found answer, then its confirmation."""
    wired.state.now = at or T0 + SETTLED
    [first] = await worker.resolve_dead_letters()
    assert first["outcome"] == "absence_awaiting_confirmation"
    wired.state.now += CONFIRMED
    [outcome] = await worker.resolve_dead_letters()
    return outcome


# ── C04-01: a dead-lettered entry is finalized, proven absent and released ─────
@pytest.mark.parametrize("failure,posts,reason", [
    (BREAKER_OPEN, 3, "retries_exhausted"),
    (BUSINESS_403, 3, "retries_exhausted"),
    (UNPROCESSABLE_422, 1, "non_retryable_error"),
], ids=["breaker_open", "business_403", "unprocessable_422"])
async def test_dead_lettered_entry_is_finalized_proven_absent_released_and_trades_again(
        wired, tmp_path, failure, posts, reason):
    broker = FakeBroker(place_error=failure)
    worker = wired.bind(broker)
    order_id = await submit_entry(wired)
    await drive(worker)
    order, event = await load(wired.sessions, order_id)
    assert event.status == "failed" and broker.kinds() == ["POST"] * posts
    assert (order.status, order.broker_order_id) == ("accepted", None)  # not finalized yet
    record = record_of(order)
    assert record["state"] == "absence_check_pending" and record["terminal_status"] == "rejected"
    assert record["reason"] == reason and record["outbox_event_id"] == str(event.id)
    assert record["client_order_id"] == order.client_idempotency_key
    assert criticals(wired.log) == []  # a dead-lettered entry does not page
    assert wired.notices.await_args.args[1]["type"] == "order.rejected"

    engine = await lifecycle_engine(wired, tmp_path, symbol="MSFT", order_id=order_id)
    await advance_ticks(engine, 4)  # a pending record is not proof
    assert engine._pending_entry_order_ids == {"MSFT": order_id}
    assert engine._last_pending_entry_resolution["issues"] == ["broker_dispatch_unresolved"]
    assert gate(engine, "MSFT") == (False, "pending_entry")

    assert await worker.resolve_dead_letters() == []  # within the settle delay: no lookup
    assert broker.kinds() == ["POST"] * posts
    wired.state.now = T0 + SETTLED
    [outcome] = await worker.resolve_dead_letters()  # one order-not-found answer is not proof
    assert outcome["outcome"] == "absence_awaiting_confirmation" and broker.kinds()[-1] == "lookup"
    order, _ = await load(wired.sessions, order_id)
    assert (order.status, record_of(order)["state"]) == ("accepted", "absence_check_pending")
    await advance_ticks(engine, 2)
    assert engine._pending_entry_order_ids == {"MSFT": order_id}
    wired.state.now += CONFIRMED - timedelta(seconds=1)
    assert await worker.resolve_dead_letters() == []  # the confirming lookup is not due yet
    assert broker.kinds().count("lookup") == 1
    wired.state.now += timedelta(seconds=1)
    [outcome] = await worker.resolve_dead_letters()
    assert outcome["outcome"] == "finalized" and broker.kinds().count("lookup") == 2
    order, _ = await load(wired.sessions, order_id)
    assert (order.status, order.broker_order_id, order.filled_qty) == ("rejected", None, Decimal(0))
    record = record_of(order)
    assert record["state"] == "finalized"
    assert record["absence"]["result"] == "not_found"
    assert record["absence"]["client_order_id"] == order.client_idempotency_key
    first, second = record["absence"]["answers"]  # both answers, as Alpaca gave them
    assert first == {"checked_at": (T0 + SETTLED).isoformat(), **NOT_FOUND}
    assert second == {"checked_at": (T0 + SETTLED + CONFIRMED).isoformat(), **NOT_FOUND}
    assert worker.dispatch_lifecycle_status()["counts"]["finalized"] == {"rejected": 1}

    await advance_ticks(engine, 4)
    assert engine._pending_entry_order_ids == {} and "MSFT" not in engine._pending_entry
    assert "MSFT" not in engine._entry_metadata
    [receipt] = engine._last_pending_entry_resolution["orders"]
    assert receipt["resolution"] == "verified_unfilled" and receipt["never_sent"] is True
    assert gate(engine, "MSFT") == (True, "")
    assert "get_order" not in broker.kinds()  # never a broker confirmation without a broker id

    # The symbol trades again: a new entry is dispatched normally.
    broker.place_error = None
    again = await submit_entry(wired, created_at=wired.state.now)
    await drive(worker)
    order, event = await load(wired.sessions, again)
    assert event.status == "sent" and (order.status, order.broker_order_id) == ("accepted", BROKER_ID)


async def test_a_dead_lettered_entry_proven_absent_completes_the_emergency_inventory_receipt(wired):
    worker = wired.bind(FakeBroker(place_error=UNPROCESSABLE_422))
    order_id = await submit_entry(wired)
    await drive(worker)
    assert (await finalize(worker, wired))["outcome"] == "finalized"
    broker = FakeBroker()
    order, _ = await load(wired.sessions, order_id)
    receipt = await cancellation._one_order(broker, order)
    assert "issue" not in receipt and receipt["never_sent"] is True
    assert (receipt["dispatch_status"], receipt["filled_qty"]) == ("rejected", "0")
    assert broker.calls == []  # nothing to confirm or cancel at the broker


# ── A 404 alone never releases ────────────────────────────────────────────────
@pytest.mark.parametrize("variant", [
    "not_dispatched_yet", "status_set_by_hand", "awaiting_lookup",
    "proof_for_another_key", "proof_without_finalization",
])
async def test_a_404_alone_never_releases(wired, tmp_path, variant):
    broker = FakeBroker(place_error=UNPROCESSABLE_422)
    worker = wired.bind(broker)
    order_id = await submit_entry(wired)
    if variant != "not_dispatched_yet":
        await drive(worker)  # dead-lettered and recorded, absence not yet checked
    async with wired.sessions() as session:
        row = await session.get(Order, uuid.UUID(order_id))
        attributes = dict(row.attributes)
        record = dict(attributes.get("outbox_dead_letter") or {})
        proof = {"result": "not_found", "client_order_id": row.client_idempotency_key}
        if variant == "status_set_by_hand":  # e.g. a remediation script or a manual edit
            row.status = "rejected"
        elif variant == "proof_for_another_key":
            row.status = "rejected"
            attributes["outbox_dead_letter"] = {**record, "state": "finalized",
                                                "absence": {**proof, "client_order_id": "organism_other"}}
        elif variant == "proof_without_finalization":
            row.status = "rejected"
            attributes["outbox_dead_letter"] = {**record, "absence": proof}  # state still pending
        row.attributes = attributes
        await session.commit()
    broker.calls.clear()
    engine = await lifecycle_engine(wired, tmp_path, symbol="MSFT", order_id=order_id)
    await advance_ticks(engine, 4)
    assert engine._pending_entry_order_ids == {"MSFT": order_id}
    assert engine._last_pending_entry_resolution["issues"] == ["broker_dispatch_unresolved"]
    assert gate(engine, "MSFT") == (False, "pending_entry")
    assert broker.calls == []  # the engine never looks an undelivered order up
    order, _ = await load(wired.sessions, order_id)
    assert cancellation._never_sent(order) is False


async def test_only_dead_letters_are_looked_up(wired):
    """A queued, never-dispatched entry is not a candidate: a 404 would prove nothing."""
    broker = FakeBroker()
    worker = wired.bind(broker)
    order_id = await submit_entry(wired)
    wired.state.now = T0 + SETTLED
    assert await worker.resolve_dead_letters() == [] and broker.calls == []
    order, event = await load(wired.sessions, order_id)
    assert (order.status, event.status, record_of(order)) == ("accepted", "pending", None)


# ── A transport error never releases ──────────────────────────────────────────
async def test_transport_error_never_releases_and_is_retried_with_backoff(wired, tmp_path, monkeypatch):
    monkeypatch.setattr(worker_mod, "DEAD_LETTER_LOOKUP_TIMEOUT_SECONDS", 0.05)

    async def hangs(_key):
        await asyncio.sleep(1)

    broker = FakeBroker(place_error=UNPROCESSABLE_422, lookups=[
        HTTPException(503, "Alpaca broker circuit breaker OPEN — refusing to submit"),
        BrokerAcknowledgementUnresolved("x", "lookup_not_confirmed"),  # a 200 that does not confirm
        hangs,  # a lookup that times out
        None,   # finally Alpaca's order-not-found answer, then its confirmation
        None,
    ])
    worker = wired.bind(broker)
    order_id = await submit_entry(wired)
    await drive(worker)
    engine = await lifecycle_engine(wired, tmp_path, symbol="MSFT", order_id=order_id)
    wired.state.now = T0 + SETTLED
    expected_delays = [worker_mod.DEAD_LETTER_SWEEP_SECONDS * 2 ** n for n in range(3)]
    for delay in expected_delays:
        [outcome] = await worker.resolve_dead_letters()
        assert outcome["outcome"] == "absence_unverified"
        order, _ = await load(wired.sessions, order_id)
        assert (order.status, record_of(order)["state"]) == ("accepted", "absence_check_pending")
        await advance_ticks(engine, 2)
        assert engine._pending_entry_order_ids == {"MSFT": order_id}
        lookups = broker.kinds().count("lookup")
        assert await worker.resolve_dead_letters() == []  # backing off: no lookup
        wired.state.now += timedelta(seconds=delay - 1)
        assert await worker.resolve_dead_letters() == [] and broker.kinds().count("lookup") == lookups
        wired.state.now += timedelta(seconds=1)
    [outcome] = await worker.resolve_dead_letters()
    assert outcome["outcome"] == "absence_awaiting_confirmation"
    wired.state.now += CONFIRMED
    [outcome] = await worker.resolve_dead_letters()
    assert outcome["outcome"] == "finalized" and broker.kinds().count("lookup") == 5
    await advance_ticks(engine, 4)
    assert engine._pending_entry_order_ids == {}
    assert worker.dispatch_lifecycle_status()["counts"]["absence_unverified"] == {
        "lookup_failed": 1, "lookup_not_confirmed": 1, "lookup_timeout": 1}


def test_backoff_is_capped():
    cap = worker_mod.DEAD_LETTER_MAX_BACKOFF_SECONDS
    assert min(worker_mod.DEAD_LETTER_SWEEP_SECONDS * 2 ** 10, cap) == cap == 300.0
    # Driven through the retry state: the delay doubles to the cap and stays there,
    # however long the broker stays unreachable (no float overflow).
    worker = OutboxWorker.__new__(OutboxWorker)
    delays = [worker._back_off_dead_letter("row", T0) for _ in range(1500)]
    assert delays[:6] == [15.0, 30.0, 60.0, 120.0, 240.0, 300.0] and set(delays[5:]) == {cap}


# ── Nothing is released on the submission tick ────────────────────────────────
async def test_nothing_is_released_on_the_tick_that_registered_the_identity(wired, tmp_path):
    worker = wired.bind(FakeBroker(place_error=UNPROCESSABLE_422))
    order_id = await submit_entry(wired)
    await drive(worker)
    assert (await finalize(worker, wired))["outcome"] == "finalized"  # with the absence proof
    # The engine registers the identity on tick 600 (as _live_tick_inner does at
    # submission) and reconciles at the end of the same tick, then runs the EOD
    # cancellation in it: neither may release.
    engine = await lifecycle_engine(wired, tmp_path, symbol="MSFT", order_id=order_id,
                                    tick=600, registered=600)
    await engine._reconcile_pending_entry_orders()
    await engine._cancel_pending_entry_orders()
    assert engine._pending_entry_order_ids == {"MSFT": order_id}
    assert engine._last_pending_entry_resolution["issues"] == ["never_sent_release_waits_for_next_tick"]
    engine._tick_count += 1
    await engine._reconcile_pending_entry_orders()
    assert engine._pending_entry_order_ids == {}
    assert engine._last_pending_entry_resolution["orders"][0]["resolution"] == "verified_unfilled"


async def test_a_missing_registration_tick_never_releases(wired, tmp_path):
    worker = wired.bind(FakeBroker(place_error=UNPROCESSABLE_422))
    order_id = await submit_entry(wired)
    await drive(worker)
    assert (await finalize(worker, wired))["outcome"] == "finalized"
    engine = await lifecycle_engine(wired, tmp_path, symbol="MSFT", order_id=order_id)
    engine._pending_entry = {}  # identity without its registration tick
    await engine._reconcile_pending_entry_orders()
    assert engine._pending_entry_order_ids == {"MSFT": order_id}
    assert "never_sent_release_waits_for_next_tick" in engine._last_pending_entry_resolution["issues"]


# ── C01-04: a stale or after-session entry is expired at dispatch ─────────────
@pytest.mark.parametrize("created,dispatched,reason", [
    (T0 - timedelta(seconds=121), T0, "entry_stale"),
    # 15:59:30 ET created, 16:00:10 ET dispatched: young, but its session closed.
    (datetime(2026, 10, 6, 15, 59, 30, tzinfo=ET), datetime(2026, 10, 6, 16, 0, 10, tzinfo=ET),
     "entry_session_closed"),
], ids=["stale", "session_closed"])
async def test_stale_or_after_session_entry_is_expired_at_dispatch_and_released(
        wired, tmp_path, created, dispatched, reason):
    broker = FakeBroker()
    worker = wired.bind(broker)
    wired.state.now = dispatched
    order_id = await submit_entry(wired, created_at=created)
    await drive(worker)
    assert broker.calls == []  # nothing sent, nothing looked up at dispatch
    order, event = await load(wired.sessions, order_id)
    assert (event.status, event.attempts) == ("failed", 0)
    assert event.last_error.startswith(f"DISPATCH_EXPIRED:{reason}")
    assert (order.status, order.broker_order_id) == ("accepted", None)
    record = record_of(order)
    assert (record["state"], record["terminal_status"], record["reason"]) == (
        "absence_check_pending", "expired", reason)
    assert wired.notices.await_args.args[1]["type"] == "order.expired"
    assert criticals(wired.log) == []
    warnings = [call.args[0] for call in wired.log.warning.call_args_list]
    assert any(message.startswith("Entry not sent: refused at dispatch") for message in warnings)

    engine = await lifecycle_engine(wired, tmp_path, symbol="MSFT", order_id=order_id)
    outcome = await finalize(worker, wired, at=dispatched + SETTLED)
    assert outcome["outcome"] == "finalized" and broker.kinds() == ["lookup", "lookup"]
    order, _ = await load(wired.sessions, order_id)
    assert order.status == "expired" and record_of(order)["absence"]["result"] == "not_found"
    status = worker.dispatch_lifecycle_status()  # review NB4: counted, one refusal does not page
    assert status["entry_refusals"] == 1 and status["counts"]["entry_refused"] == {reason: 1}
    assert status["counts"]["finalized"] == {"expired": 1} and status["refusal_paged"] is False
    await advance_ticks(engine, 4)
    assert engine._pending_entry_order_ids == {} and "MSFT" not in engine._entry_metadata
    assert gate(engine, "MSFT") == (True, "")


async def test_a_refused_short_entry_does_not_page_as_an_exit(wired):
    """A declared short entry (strong-short path) is a sell, but never an exit."""
    broker = FakeBroker()
    worker = wired.bind(broker)
    result = await OrderService(sessionmaker=wired.sessions).submit_symbol_order(
        symbol="MSFT", side="sell", qty=3, order_type="limit", tif="day", limit_price=500.25,
        idempotency_key=f"organism_MSFT_20261006_s1_t10_organism_entry_sell_q3_{uuid.uuid4().hex[:6]}",
        attributes={"source": "organism", "reason": "organism_entry", "tick": 10})
    await set_event_time(wired.sessions, result["order_id"], T0 - timedelta(minutes=5))
    await drive(worker)
    order, event = await load(wired.sessions, result["order_id"])
    assert event.last_error.startswith("DISPATCH_EXPIRED:entry_stale") and broker.calls == []
    assert record_of(order)["terminal_status"] == "expired"
    assert criticals(wired.log) == []
    exit_event = {"payload": {"side": "sell", "client_key": "organism_exit_MSFT_x"}}
    assert worker_mod.dlq_exposure_alert(exit_event, {"dispatch_expired": True}) is None
    assert worker_mod.dlq_exposure_alert(exit_event, {"error": "timeout"}) is not None


async def test_entry_within_the_limits_is_dispatched_as_before(wired):
    broker = FakeBroker()
    worker = wired.bind(broker)
    order_id = await submit_entry(wired, created_at=T0 - timedelta(seconds=120))  # at the limit
    await drive(worker)
    assert broker.kinds() == ["POST"]  # no guard read for an entry
    order, event = await load(wired.sessions, order_id)
    assert (event.status, order.broker_order_id, record_of(order)) == ("sent", BROKER_ID, None)


async def test_stale_entry_that_reached_the_broker_earlier_is_attached_not_expired(wired, tmp_path):
    """A retry whose earlier POST did reach Alpaca (a lost response) is found and attached."""
    broker = FakeBroker()
    worker = wired.bind(broker)
    order_id = await submit_entry(wired, created_at=T0 - timedelta(minutes=10))
    order, _ = await load(wired.sessions, order_id)
    key = order.client_idempotency_key
    await set_event_time(wired.sessions, order_id, T0 - timedelta(minutes=10), attempts=2,
                         last_error="503: Alpaca API connection error: connection reset")
    await drive(worker)
    broker.lookups = [ack(key, "MSFT", "buy", 3, status="new")]
    wired.state.now = T0 + SETTLED
    [outcome] = await worker.resolve_dead_letters()
    assert outcome["outcome"] == "found_at_broker"
    order, event = await load(wired.sessions, order_id)
    assert event.status == "failed"  # delivery stays stopped; nothing was sent again
    assert (order.status, order.broker_order_id) == ("submitted", BROKER_ID)  # broker "new"
    assert record_of(order)["state"] == "found_at_broker"
    assert record_of(order)["absence"]["broker_order_id"] == BROKER_ID
    assert broker.kinds() == ["lookup"]
    [message] = criticals(wired.log)
    assert message.startswith("DEAD-LETTERED ORDER FOUND AT THE BROKER, attached")
    assert cancellation._never_sent(order) is False  # resolved by broker confirmation from here


async def test_found_order_that_cannot_be_attached_pages_and_is_not_finalized(wired):
    broker = FakeBroker(place_error=UNPROCESSABLE_422)
    worker = wired.bind(broker)
    order_id = await submit_entry(wired)
    await drive(worker)
    order, _ = await load(wired.sessions, order_id)
    # The client key matches (so the strict lookup returns it) but the quantity does not.
    broker.lookups = [ack(order.client_idempotency_key, "MSFT", "buy", 5)]
    wired.state.now = T0 + SETTLED
    [outcome] = await worker.resolve_dead_letters()
    assert outcome["outcome"] == "found_unattached"
    order, _ = await load(wired.sessions, order_id)
    assert (order.status, order.broker_order_id) == ("accepted", None)
    assert record_of(order)["state"] == "found_unattached"
    assert criticals(wired.log)[0].startswith("DEAD-LETTERED ORDER FOUND AT THE BROKER, could not")
    assert await worker.resolve_dead_letters() == []  # an operator takes over; no more lookups


# ── Exits are never expired ───────────────────────────────────────────────────
@pytest.mark.parametrize("created,dispatched", [
    (T0 - timedelta(minutes=31), T0),
    (datetime(2026, 10, 6, 15, 59, 30, tzinfo=ET), datetime(2026, 10, 6, 16, 0, 10, tzinfo=ET)),
], ids=["stale_exit", "after_session_exit"])
async def test_exits_are_never_expired(wired, created, dispatched):
    broker = FakeBroker(position={"symbol": "MSFT", "qty": "3", "side": "long", "qty_available": "3"})
    worker = wired.bind(broker)
    wired.state.now = dispatched
    order_id = await submit_exit(wired, created_at=created)
    await drive(worker)
    assert broker.kinds() == ["lookup", "position", "POST"]  # the exit guard, then sent
    order, event = await load(wired.sessions, order_id)
    assert (event.status, order.broker_order_id, record_of(order)) == ("sent", BROKER_ID, None)


async def test_lookup_only_events_are_never_refused_for_age(wired):
    broker = FakeBroker()
    worker = wired.bind(broker)
    order_id = await submit_entry(wired, created_at=T0 - timedelta(hours=2))
    order, _ = await load(wired.sessions, order_id)
    marker = BROKER_ACK_STATE_PREFIX + '{"version":1,"client_order_id":"%s"}' % order.client_idempotency_key
    await set_event_time(wired.sessions, order_id, T0 - timedelta(hours=2), attempts=1, last_error=marker)
    await drive(worker)
    assert broker.kinds() == ["reconcile"]
    order, event = await load(wired.sessions, order_id)
    assert (event.status, order.broker_order_id) == ("sent", BROKER_ID)


async def test_an_unexpected_check_failure_holds_the_entry(wired, monkeypatch):
    broker = FakeBroker()
    worker = wired.bind(broker)

    def broken(*_a, **_k):
        raise RuntimeError("calendar unavailable")

    monkeypatch.setattr(worker_mod, "entry_dispatch_refusal", broken)
    order_id = await submit_entry(wired)
    claimed = await worker._get_pending_events()
    await worker._process_event(claimed[0])
    order, event = await load(wired.sessions, order_id)
    assert broker.calls == [] and (event.status, event.attempts) == ("pending", 1)
    assert event.last_error == "entry_dispatch_check_unavailable:RuntimeError"
    assert order.status == "accepted"


@pytest.mark.parametrize("payload,created,now,expected", [
    ({"side": "buy", "intent": "entry"}, T0 - timedelta(seconds=120), T0, None),
    ({"side": "buy", "intent": "entry"}, T0 - timedelta(seconds=120.5), T0, "entry_stale"),
    ({"side": "buy"}, T0 - timedelta(minutes=5), T0, "entry_stale"),  # undeclared (manual) buy
    ({"side": "sell", "intent": "entry"}, T0 - timedelta(minutes=5), T0, "entry_stale"),  # short entry
    ({"payload": {"side": "buy", "intent": "entry"}}, T0 - timedelta(minutes=5), T0, "entry_stale"),
    ({"side": "buy", "intent": "entry"}, T0 + timedelta(seconds=5), T0, None),  # clock skew
    ({"side": "sell", "reduce_only": True}, T0 - timedelta(hours=3), T0, None),
    ({"side": "buy", "intent": "exit"}, T0 - timedelta(hours=3), T0, None),  # buy-to-cover
    ({"side": "sell"}, T0 - timedelta(hours=3), T0, None),  # undeclared sell under long-only
    ({"side": "buy", "attributes": {"close_position": True}}, T0 - timedelta(hours=3), T0, None),
    ({"side": "buy", "intent": "entry"}, None, T0, None),
    # Session rule: created in the session, sent after its close.
    ({"side": "buy", "intent": "entry"}, datetime(2026, 10, 6, 15, 59, 59, tzinfo=ET),
     datetime(2026, 10, 6, 16, 0, 0, tzinfo=ET), "entry_session_closed"),
    ({"side": "buy", "intent": "entry"}, datetime(2026, 10, 6, 15, 58, 30, tzinfo=ET),
     datetime(2026, 10, 6, 15, 59, 59, tzinfo=ET), None),
    # Early close (Friday 2026-11-27, 13:00 ET).
    ({"side": "buy", "intent": "entry"}, datetime(2026, 11, 27, 12, 59, 30, tzinfo=ET),
     datetime(2026, 11, 27, 13, 0, 5, tzinfo=ET), "entry_session_closed"),
    # Created outside a regular session (after hours, or a holiday): age only.
    ({"side": "buy"}, datetime(2026, 10, 6, 17, 0, tzinfo=ET),
     datetime(2026, 10, 6, 17, 1, 30, tzinfo=ET), None),
    ({"side": "buy"}, datetime(2026, 11, 26, 11, 0, tzinfo=ET),
     datetime(2026, 11, 26, 11, 1, tzinfo=ET), None),
    # Naive and ISO-string stamps are UTC.
    ({"side": "buy", "intent": "entry"}, (T0 - timedelta(minutes=3)).replace(tzinfo=None), T0, "entry_stale"),
    ({"side": "buy", "intent": "entry"}, (T0 - timedelta(minutes=3)).isoformat(), T0, "entry_stale"),
])
def test_entry_dispatch_refusal_rules(monkeypatch, payload, created, now, expected):
    monkeypatch.setenv("ORGANISM_LONG_ONLY", "true")
    refusal = entry_dispatch_refusal(payload, created, now=now.astimezone(UTC))
    assert (refusal[0] if refusal else None) == expected


# ── A restart preserves the outcome ───────────────────────────────────────────
async def test_restart_preserves_the_outcome(wired, tmp_path):
    broker = FakeBroker(place_error=BREAKER_OPEN)
    worker = wired.bind(broker)
    order_id = await submit_entry(wired)
    await drive(worker)  # dead-lettered and recorded; the process stops before the lookup
    first = await lifecycle_engine(wired, tmp_path, symbol="MSFT", order_id=order_id,
                                   tick=500, registered=500, metadata=False)
    first._tick_count += 1
    await first._reconcile_pending_entry_orders()
    assert first._pending_entry_order_ids == {"MSFT": order_id}
    assert first.force_save_brain()["success"] is True

    restarted_worker = wired.bind(broker)  # fresh process: no in-memory state
    assert (await finalize(restarted_worker, wired))["outcome"] == "finalized"

    second = await lifecycle_engine(wired, tmp_path, symbol="MSFT", order_id=None)
    # initialize() restored the identity and ran the startup cancellation on the
    # restore tick: kept until the next tick.
    assert second._pending_entry_order_ids == {"MSFT": order_id}
    assert second._last_pending_entry_resolution["issues"] == ["never_sent_release_waits_for_next_tick"]
    second._tick_count += 1
    await second._reconcile_pending_entry_orders()
    assert second._pending_entry_order_ids == {} and "MSFT" not in second._pending_entry
    assert second.force_save_brain()["success"] is True

    third = await lifecycle_engine(wired, tmp_path, symbol="MSFT", order_id=None)
    assert third._pending_entry_order_ids == {} and "MSFT" not in third._pending_entry
    order, _ = await load(wired.sessions, order_id)
    assert order.status == "rejected" and record_of(order)["state"] == "finalized"
    assert await restarted_worker.resolve_dead_letters() == []  # nothing left to settle


async def test_a_failed_dead_letter_commit_records_nothing_and_looks_nothing_up(wired, monkeypatch):
    broker = FakeBroker(place_error=UNPROCESSABLE_422)
    worker = wired.bind(broker)
    order_id = await submit_entry(wired)
    claimed = await worker._get_pending_events()
    original_commit = AsyncSession.commit

    async def failing_commit(session):
        raise RuntimeError("offline injected dead-letter commit failure")

    monkeypatch.setattr(AsyncSession, "commit", failing_commit)
    await worker._process_event(claimed[0])  # 422: straight to the dead letter, whose commit fails
    monkeypatch.setattr(AsyncSession, "commit", original_commit)
    order, event = await load(wired.sessions, order_id)
    assert event.status == "pending"  # left for redelivery after its lease, as before
    assert record_of(order) is None and order.status == "accepted"
    wired.state.now = T0 + SETTLED
    assert await worker.resolve_dead_letters() == [] and broker.kinds() == ["POST"]


# ── Dead-lettered sells are finalized too ─────────────────────────────────────
async def test_dead_lettered_sell_is_finalized_too(wired):
    broker = FakeBroker(place_error=BREAKER_OPEN,
                        position={"symbol": "MSFT", "qty": "3", "side": "long", "qty_available": "3"})
    worker = wired.bind(broker)
    order_id = await submit_exit(wired)
    await drive(worker)
    order, event = await load(wired.sessions, order_id)
    assert event.status == "failed" and broker.kinds().count("POST") == 3
    assert criticals(wired.log)[0].startswith("EXIT ORDER DEAD-LETTERED")  # EXE-04 page unchanged
    assert record_of(order)["state"] == "absence_check_pending" and order.status == "accepted"
    assert (await finalize(worker, wired))["outcome"] == "finalized"
    order, _ = await load(wired.sessions, order_id)
    assert order.status == "rejected" and order.status in ACCOUNTABLE_TERMINAL_STATUSES
    assert record_of(order)["absence"]["result"] == "not_found"


# ── Guards of the absence check ───────────────────────────────────────────────
async def test_ambiguous_dead_letter_is_never_finalized(wired):
    broker = FakeBroker()
    worker = wired.bind(broker, max_retries=0)
    order_id = await submit_entry(wired)
    order, _ = await load(wired.sessions, order_id)
    marker = BROKER_ACK_STATE_PREFIX + '{"version":1,"client_order_id":"%s"}' % order.client_idempotency_key

    async def unresolved(_key):
        raise BrokerAcknowledgementUnresolved(order.client_idempotency_key, "lookup_unavailable")

    broker.reconcile_order_acknowledgement = unresolved
    await set_event_time(wired.sessions, order_id, T0 - timedelta(seconds=1), last_error=marker)
    await drive(worker)
    order, event = await load(wired.sessions, order_id)
    assert event.status == "failed" and event.last_error == marker
    assert record_of(order) is None and order.status == "accepted"  # may be live: unchanged
    wired.state.now = T0 + SETTLED
    assert await worker.resolve_dead_letters() == []


async def test_a_pending_delivery_blocks_the_absence_check(wired):
    broker = FakeBroker(place_error=UNPROCESSABLE_422)
    worker = wired.bind(broker)
    order_id = await submit_entry(wired)
    await drive(worker)
    order, _ = await load(wired.sessions, order_id)
    async with wired.sessions() as session:  # e.g. an operator re-queued the order
        await OutboxRepo(session).add_order_submit_event(
            order_id=order_id, symbol="MSFT", side="buy", qty="3", client_key=order.client_idempotency_key)
        await session.commit()
    wired.state.now = T0 + SETTLED
    [outcome] = await worker.resolve_dead_letters()
    assert outcome["outcome"] == "pending_delivery_exists"
    assert broker.kinds() == ["POST"]  # no lookup
    order, _ = await load(wired.sessions, order_id)
    assert order.status == "accepted" and record_of(order)["state"] == "absence_check_pending"


async def test_finalization_rechecks_the_row_under_its_lock(wired):
    broker = FakeBroker(place_error=UNPROCESSABLE_422)
    worker = wired.bind(broker)
    order_id = await submit_entry(wired)
    await drive(worker)

    async def attached_meanwhile(_key):
        # The trade-update stream matched the client key while the lookup ran.
        async with wired.sessions() as session:
            await OrdersRepo(session).attach_broker_result(uuid.UUID(order_id), broker_order_id=BROKER_ID)
            await session.commit()
        return None

    broker.lookups = [None, attached_meanwhile]  # during the confirming lookup
    assert (await finalize(worker, wired))["outcome"] == "order_row_changed"
    order, _ = await load(wired.sessions, order_id)
    assert (order.status, order.broker_order_id) == ("accepted", BROKER_ID)
    assert record_of(order)["state"] == "absence_check_pending"


async def test_a_requeued_event_blocks_finalization(wired, monkeypatch):
    broker = FakeBroker(place_error=UNPROCESSABLE_422)
    worker = wired.bind(broker)
    order_id = await submit_entry(wired)
    await drive(worker)
    _, event = await load(wired.sessions, order_id)

    async def requeued(_key):
        async with wired.sessions() as session:
            await session.execute(update(OutboxEvent).where(OutboxEvent.id == event.id)
                                  .values(status="sent"))
            await session.commit()
        return None

    broker.lookups = [None, requeued]  # during the confirming lookup
    assert (await finalize(worker, wired))["outcome"] == "event_not_dead_lettered"
    order, _ = await load(wired.sessions, order_id)
    assert order.status == "accepted"


async def test_sweep_bounds_lookups_per_run(wired, monkeypatch):
    monkeypatch.setattr(worker_mod, "DEAD_LETTER_SWEEP_BATCH", 2)
    broker = FakeBroker(place_error=UNPROCESSABLE_422)
    worker = wired.bind(broker)
    for symbol in ("MSFT", "AAPL", "XLE"):
        await submit_entry(wired, symbol=symbol)
    await drive(worker)
    wired.state.now = T0 + SETTLED
    awaiting = "absence_awaiting_confirmation"
    assert [o["outcome"] for o in await worker.resolve_dead_letters()] == [awaiting] * 2
    assert [o["outcome"] for o in await worker.resolve_dead_letters()] == [awaiting]
    wired.state.now += CONFIRMED
    assert [o["outcome"] for o in await worker.resolve_dead_letters()] == ["finalized"] * 2
    assert [o["outcome"] for o in await worker.resolve_dead_letters()] == ["finalized"]
    assert broker.kinds().count("lookup") == 6


async def test_dead_letter_loop_runs_and_stops(wired, monkeypatch):
    monkeypatch.setattr(worker_mod, "DEAD_LETTER_CONFIRM_SECONDS", 0.0)  # the clock is frozen here
    worker = wired.bind(FakeBroker(place_error=UNPROCESSABLE_422))
    order_id = await submit_entry(wired)
    await drive(worker)
    wired.state.now = T0 + SETTLED
    worker._running = True
    await worker.start_dead_letter_loop(interval_seconds=0.01)
    task = worker._dead_letter_task
    await worker.start_dead_letter_loop(interval_seconds=0.01)
    assert worker._dead_letter_task is task  # idempotent
    for _ in range(200):
        order, _ = await load(wired.sessions, order_id)
        if order.status == "rejected":
            break
        await asyncio.sleep(0.01)
    assert order.status == "rejected"
    await worker.stop()
    assert worker._dead_letter_task is None and task.done()


async def test_start_outbox_worker_wires_the_dead_letter_loop(sessions, monkeypatch):
    import backend.infra.outbox_worker as obw

    monkeypatch.setattr(obw, "_outbox_worker", None, raising=False)
    monkeypatch.setenv("OUTBOX_PRUNE_INTERVAL_SECONDS", "3600")
    worker = await obw.start_outbox_worker(sessions)
    try:
        assert worker._dead_letter_task is not None and not worker._dead_letter_task.done()
    finally:
        await worker.stop()
    assert worker._dead_letter_task is None


# ── Review NB1: only Alpaca's order-not-found answer, twice, is absence ───────
KEY = "organism_MSFT_20261006_s1_t10_organism_entry_buy_q3_abc123"


def _no_breaker(_name):
    raise RuntimeError("no shared breaker state in this test")


@pytest.mark.parametrize("status,body,state,detail", [
    (404, '{"code":40410000,"message":"order not found for %s"}' % KEY, "absent", "not_found"),
    (404, '{"code": 40410000, "message": "Order not found"}', "absent", "not_found"),
    (404, '{"code":40410000,"message":"endpoint not found"}', "unknown",
     "not_found_unconfirmed:message_mismatch"),
    (404, '{"code":40410000,"message":"position does not exist"}', "unknown",
     "not_found_unconfirmed:message_mismatch"),
    (404, '{"code":40410000,"message":null}', "unknown", "not_found_unconfirmed:message_mismatch"),
    (404, "<html>404 page not found</html>", "unknown", "not_found_unconfirmed:non_json_body"),
    (404, "404 page not found", "unknown", "not_found_unconfirmed:non_json_body"),
    (404, "", "unknown", "not_found_unconfirmed:no_body"),
    (404, '{"code":40410001,"message":"order not found"}', "unknown", "not_found_unconfirmed:code_mismatch"),
    (404, '{"code":"40410000","message":"order not found"}', "unknown", "not_found_unconfirmed:code_mismatch"),
    (404, '{"message":"order not found"}', "unknown", "not_found_unconfirmed:code_mismatch"),
    (404, '[{"code":40410000,"message":"order not found"}]', "unknown", "not_found_unconfirmed:not_an_object"),
    (200, json.dumps(ack(KEY, "MSFT", "buy", 3)), "present", "found"),
    (200, json.dumps(ack("organism_other", "MSFT", "buy", 3)), "unknown",
     "lookup_not_confirmed:lookup_not_confirmed"),
    (422, '{"code":42210000,"message":"invalid client_order_id"}', "unknown", "lookup_failed:HTTPException"),
], ids=["order_not_found", "order_not_found_any_case", "endpoint_not_found", "other_resource",
        "no_message", "html_page", "plain_text", "empty", "other_code", "code_as_string", "no_code",
        "not_an_object", "found", "other_key", "other_4xx"])
async def test_only_alpacas_order_not_found_answer_is_absence(monkeypatch, status, body, state, detail):
    """Probe P4 on the real AlpacaBrokerClient: no other 404 counts (one GET, never a POST)."""
    from backend.infra import resilience
    from backend.integrations import alpaca_broker

    monkeypatch.setattr(resilience, "get_or_create_circuit_breaker", _no_breaker)
    requests = []

    def answer(request):
        requests.append(request)
        return httpx.Response(status, text=body)

    client = alpaca_broker.AlpacaBrokerClient.__new__(alpaca_broker.AlpacaBrokerClient)
    client.api_key, client.api_secret, client.is_paper, client.base_url = "synthetic", "synthetic", True, PAPER
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(answer))
    monkeypatch.setattr(alpaca_broker, "get_alpaca_broker_client", lambda: client)
    try:
        probe = await alpaca_outbox.probe_order_absence(KEY)
    finally:
        await client.client.aclose()
    assert (probe.state, probe.detail) == (state, detail)
    [request] = requests
    assert (request.method, request.url.path) == ("GET", "/v2/orders:by_client_order_id")
    assert request.url.params["client_order_id"] == KEY
    if state == "absent":
        assert probe.evidence == {"http_status": 404, "code": 40410000,
                                  "message": json.loads(body)["message"]}
    elif detail.startswith("not_found_unconfirmed"):
        assert probe.evidence == {"http_status": 404, "body": body[:120]}
    if state == "present":
        assert probe.order["client_order_id"] == KEY


@pytest.mark.parametrize("interruption", [
    "restart", "unconfirmed_404", "transport_error", "pending_delivery", "new_dead_letter",
])
async def test_the_two_answers_must_be_consecutive(wired, interruption):
    """Anything between the two order-not-found answers makes absence start over."""
    broker = FakeBroker(place_error=UNPROCESSABLE_422)
    worker = wired.bind(broker)
    order_id = await submit_entry(wired)
    await drive(worker)
    wired.state.now = T0 + SETTLED
    [outcome] = await worker.resolve_dead_letters()
    assert outcome["outcome"] == "absence_awaiting_confirmation"
    wired.state.now += CONFIRMED
    if interruption == "restart":
        worker = wired.bind(broker)  # a fresh process has no first answer
    elif interruption in ("unconfirmed_404", "transport_error"):
        broker.lookups = [endpoint_404() if interruption == "unconfirmed_404"
                          else HTTPException(503, "Alpaca API unavailable after 3 retries")]
        [outcome] = await worker.resolve_dead_letters()
        assert outcome["outcome"] == "absence_unverified"
        log = wired.log.error if interruption == "unconfirmed_404" else wired.log.warning
        assert any(call.args[0].startswith("Dead-lettered order: broker absence unverified")
                   for call in log.call_args_list)
        wired.state.now += timedelta(seconds=worker_mod.DEAD_LETTER_SWEEP_SECONDS)
    elif interruption == "pending_delivery":
        order, _ = await load(wired.sessions, order_id)
        async with wired.sessions() as session:  # an operator re-queued the order meanwhile
            await OutboxRepo(session).add_order_submit_event(
                order_id=order_id, symbol="MSFT", side="buy", qty="3", client_key=order.client_idempotency_key)
            await session.commit()
        [outcome] = await worker.resolve_dead_letters()
        assert outcome["outcome"] == "pending_delivery_exists"
        async with wired.sessions() as session:  # that delivery is over too
            await session.execute(update(OutboxEvent).where(OutboxEvent.status == "pending")
                                  .values(status="failed"))
            await session.commit()
    else:  # the order was dead-lettered again, by another event
        async with wired.sessions() as session:
            row = await session.get(Order, uuid.UUID(order_id))
            attributes = dict(row.attributes)
            attributes["outbox_dead_letter"] = {**attributes["outbox_dead_letter"],
                                                "outbox_event_id": str(uuid.uuid4())}
            row.attributes = attributes
            await session.commit()
    [outcome] = await worker.resolve_dead_letters()
    assert outcome["outcome"] == "absence_awaiting_confirmation"  # a new first answer
    first_at = wired.state.now
    order, _ = await load(wired.sessions, order_id)
    assert (order.status, record_of(order)["state"]) == ("accepted", "absence_check_pending")
    wired.state.now += CONFIRMED - timedelta(seconds=1)
    assert await worker.resolve_dead_letters() == []
    wired.state.now += timedelta(seconds=1)
    [outcome] = await worker.resolve_dead_letters()
    assert outcome["outcome"] == "finalized"
    order, _ = await load(wired.sessions, order_id)
    assert record_of(order)["absence"]["answers"][0]["checked_at"] == first_at.isoformat()


async def test_an_order_found_on_the_confirming_lookup_is_attached_not_finalized(wired):
    """A POST the broker processed after the first answer (the race the second lookup is for)."""
    broker = FakeBroker(place_error=UNPROCESSABLE_422)
    worker = wired.bind(broker)
    order_id = await submit_entry(wired)
    await drive(worker)
    order, _ = await load(wired.sessions, order_id)
    broker.lookups = [None, ack(order.client_idempotency_key, "MSFT", "buy", 3, status="new")]
    assert (await finalize(worker, wired))["outcome"] == "found_at_broker"
    order, _ = await load(wired.sessions, order_id)
    assert (order.status, order.broker_order_id) == ("submitted", BROKER_ID)
    assert record_of(order)["state"] == "found_at_broker" and cancellation._never_sent(order) is False
    [message] = criticals(wired.log)
    assert message.startswith("DEAD-LETTERED ORDER FOUND AT THE BROKER, attached")


def _stream_client(monkeypatch, wired):
    """The real trade-update handler on the test store, with a recording logger."""
    @asynccontextmanager
    async def context():
        async with wired.sessions() as session:
            yield session

    monkeypatch.setattr(alpaca_stream, "get_session_context", context)
    monkeypatch.setitem(sys.modules, "backend.api.socketio_server",
                        SimpleNamespace(broadcast_order_update=AsyncMock()))
    log = MagicMock()
    monkeypatch.setattr(alpaca_stream, "logger", log)
    stream = alpaca_stream.AlpacaStreamClient.__new__(alpaca_stream.AlpacaStreamClient)
    stream._terminal_order_ids = set()
    return stream, log


async def test_a_fill_on_a_finalized_order_pages(wired, monkeypatch):
    """The residual race (a POST the broker processes after the proof) does not stay silent."""
    broker = FakeBroker(place_error=UNPROCESSABLE_422)
    worker = wired.bind(broker)
    monkeypatch.setattr(worker_mod, "_outbox_worker", worker)
    order_id = await submit_entry(wired)
    await drive(worker)
    assert (await finalize(worker, wired))["outcome"] == "finalized"
    order, _ = await load(wired.sessions, order_id)
    stream, log = _stream_client(monkeypatch, wired)
    late = {**ack(order.client_idempotency_key, "MSFT", "buy", 3, status="partially_filled"),
            "filled_qty": "1", "filled_avg_price": "500.20"}
    await stream._process_trade_update({"data": {"event": "partial_fill", "order": late}})
    [page] = log.critical.call_args_list
    assert page.args[0].startswith("FILL ATTACHED TO A FINALIZED ORDER")
    assert page.kwargs["order_id"] == order_id and page.kwargs["broker_order_id"] == BROKER_ID
    assert (page.kwargs["previous_filled_qty"], page.kwargs["cumulative_filled_qty"]) == ("0", "1")
    assert page.kwargs["finalized_status"] == "rejected"
    order, _ = await load(wired.sessions, order_id)  # broker truth is still recorded
    assert (order.status, order.broker_order_id, order.filled_qty) == ("partially_filled", BROKER_ID, Decimal(1))
    assert worker.dispatch_lifecycle_status()["counts"]["finalized_order_attached"] == {"fill": 1}
    await stream._process_trade_update({"data": {"event": "partial_fill", "order": late}})
    assert len(log.critical.call_args_list) == 1  # the same snapshot again adds nothing


@pytest.mark.parametrize("case,expected", [
    ("acknowledgement", "BROKER ORDER ATTACHED TO A FINALIZED ORDER"),
    ("no_new_information", None),
    ("not_finalized", None),
])
async def test_only_new_broker_activity_on_a_finalized_order_pages(wired, monkeypatch, case, expected):
    broker = FakeBroker(place_error=UNPROCESSABLE_422)
    worker = wired.bind(broker)
    order_id = await submit_entry(wired)
    await drive(worker)
    if case != "not_finalized":
        assert (await finalize(worker, wired))["outcome"] == "finalized"
    _stream, log = _stream_client(monkeypatch, wired)
    async with wired.sessions() as session:
        order = await session.get(Order, uuid.UUID(order_id))
        await alpaca_stream.apply_order_fill_snapshot(
            session, order, status="rejected" if case == "no_new_information" else "submitted",
            cumulative_filled_qty="0", avg_fill_price=None,
            broker_order_id=None if case == "no_new_information" else BROKER_ID,
        )
        await session.commit()
    pages = [call.args[0] for call in log.critical.call_args_list]
    if expected is None:
        assert pages == []
    else:
        assert len(pages) == 1 and pages[0].startswith(expected)


# ── Review NB2: fill evidence blocks a never-sent release (mutant M07) ────────
@pytest.mark.parametrize("evidence", ["execution", "position_lot"])
async def test_fill_evidence_blocks_a_never_sent_release(wired, tmp_path, evidence):
    worker = wired.bind(FakeBroker(place_error=UNPROCESSABLE_422))
    order_id = await submit_entry(wired)
    await drive(worker)
    assert (await finalize(worker, wired))["outcome"] == "finalized"
    async with wired.sessions() as session:
        if evidence == "execution":
            session.add(Execution(id=uuid.uuid4(), order_id=uuid.UUID(order_id), fill_qty=Decimal(1),
                                  fill_price=Decimal("500.25"), ts=datetime.now(UTC), venue="alpaca"))
        else:
            session.add(PositionLot(id=uuid.uuid4(), user_id="system", symbol="MSFT",
                                    order_id=uuid.UUID(order_id), qty=Decimal(1), remaining_qty=Decimal(1),
                                    cost_basis=Decimal("500.25"), open_date=datetime.now(UTC)))
        await session.commit()
    order, _ = await load(wired.sessions, order_id)
    assert cancellation._never_sent(order) is True  # the row alone carries the proof
    engine = await lifecycle_engine(wired, tmp_path, symbol="MSFT", order_id=order_id)
    await advance_ticks(engine, 3)
    assert engine._pending_entry_order_ids == {"MSFT": order_id}
    [receipt] = engine._last_pending_entry_resolution["orders"]
    assert receipt["never_sent"] is True and receipt["release_pending"] is False
    assert receipt["resolution"] == "unverified"
    assert gate(engine, "MSFT") == (False, "pending_entry")


# ── Review NB3: one row never stops the sweep, and the page is never lost ─────
async def test_an_outcome_write_failure_after_the_attach_still_pages_and_the_sweep_goes_on(
        wired, monkeypatch):
    """Probe P3: the attach commits, then recording the outcome fails."""
    broker = FakeBroker(place_error=UNPROCESSABLE_422)
    worker = wired.bind(broker)
    found_id = await submit_entry(wired)
    other_id = await submit_entry(wired, symbol="AAPL")
    await drive(worker)
    found, _ = await load(wired.sessions, found_id)

    async def by_key(key):
        return ack(key, "MSFT", "buy", 3, status="new") if key == found.client_idempotency_key else None

    broker.lookups = [by_key] * 4
    original = worker._write_dead_letter_outcome

    async def failing_for_found(order_uuid, record, **kwargs):
        if str(order_uuid) == found_id:
            raise RuntimeError("injected outcome-write failure")
        return await original(order_uuid, record, **kwargs)

    monkeypatch.setattr(worker, "_write_dead_letter_outcome", failing_for_found)
    wired.state.now = T0 + SETTLED
    outcomes = {o["order_id"]: o["outcome"] for o in await worker.resolve_dead_letters()}
    assert outcomes == {found_id: "check_failed", other_id: "absence_awaiting_confirmation"}
    [page] = wired.log.critical.call_args_list
    assert page.args[0].startswith("DEAD-LETTERED ORDER FOUND AT THE BROKER, attached")
    assert page.kwargs["outcome"] == "outcome_not_recorded"
    assert any(call.args[0].startswith("Dead-lettered order: absence check failed")
               for call in wired.log.error.call_args_list)
    found, _ = await load(wired.sessions, found_id)
    assert found.broker_order_id == BROKER_ID  # attached: broker confirmation takes over
    wired.state.now += CONFIRMED
    [outcome] = await worker.resolve_dead_letters()
    assert (outcome["order_id"], outcome["outcome"]) == (other_id, "finalized")


async def test_a_failing_row_is_backed_off_and_never_starves_the_rows_behind_it(wired, monkeypatch):
    broker = FakeBroker(place_error=UNPROCESSABLE_422)
    worker = wired.bind(broker)
    bad_id = await submit_entry(wired)
    good_id = await submit_entry(wired, symbol="AAPL")
    await drive(worker)
    original = worker._other_pending_delivery

    async def broken_for_bad(order_uuid):
        if str(order_uuid) == bad_id:
            raise RuntimeError("injected read failure")
        return await original(order_uuid)

    monkeypatch.setattr(worker, "_other_pending_delivery", broken_for_bad)
    wired.state.now = T0 + SETTLED
    outcomes = {o["order_id"]: o["outcome"] for o in await worker.resolve_dead_letters()}
    assert outcomes == {bad_id: "check_failed", good_id: "absence_awaiting_confirmation"}
    assert await worker.resolve_dead_letters() == []  # backed off, and awaiting confirmation
    wired.state.now += timedelta(seconds=worker_mod.DEAD_LETTER_SWEEP_SECONDS)
    assert [o["outcome"] for o in await worker.resolve_dead_letters()] == ["check_failed"]
    wired.state.now = T0 + SETTLED + CONFIRMED
    outcomes = {o["order_id"]: o["outcome"] for o in await worker.resolve_dead_letters()}
    assert outcomes == {bad_id: "check_failed", good_id: "finalized"}


# ── Review NB4: refusals are counted and page once per session ────────────────
async def test_refusals_above_the_threshold_page_once_per_session(wired):
    broker = FakeBroker()
    worker = wired.bind(broker)
    threshold = worker_mod.ENTRY_REFUSAL_PAGE_THRESHOLD
    headline = "ENTRY DISPATCH REFUSALS ABOVE THRESHOLD"
    symbols = iter(["MSFT", "AAPL", "XLE", "SPY", "QQQ", "IWM", "DIA", "XLF"])
    for n in range(1, threshold + 3):
        await submit_entry(wired, symbol=next(symbols), created_at=T0 - timedelta(minutes=5))
        await drive(worker)
        pages = [m for m in criticals(wired.log) if m.startswith(headline)]
        assert len(pages) == (1 if n > threshold else 0)  # once, on the first refusal above it
    assert broker.calls == []  # nothing was sent
    status = worker.dispatch_lifecycle_status()
    assert (status["session_date"], status["entry_refusals"], status["refusal_paged"]) == (
        "2026-10-06", threshold + 2, True)
    assert status["counts"]["entry_refused"] == status["counts"]["dead_lettered"] == {
        "entry_stale": threshold + 2}
    wired.state.now = T0 + timedelta(days=1)  # a new session date starts from zero
    for _ in range(threshold + 1):
        await submit_entry(wired, symbol=next(symbols), created_at=wired.state.now - timedelta(minutes=5))
        await drive(worker)
    assert len([m for m in criticals(wired.log) if m.startswith(headline)]) == 2
    status = worker.dispatch_lifecycle_status()
    assert (status["session_date"], status["entry_refusals"]) == ("2026-10-07", threshold + 1)


async def test_engine_status_carries_the_dispatch_lifecycle_counts(wired, tmp_path, monkeypatch):
    worker = wired.bind(FakeBroker())
    monkeypatch.setattr(worker_mod, "_outbox_worker", worker)
    await submit_entry(wired, created_at=T0 - timedelta(minutes=5))
    await drive(worker)
    engine = await lifecycle_engine(wired, tmp_path, symbol="MSFT", order_id=None)
    lifecycle = engine.status()["order_dispatch_lifecycle"]
    assert lifecycle == worker.dispatch_lifecycle_status()
    assert lifecycle["entry_refusals"] == 1 and lifecycle["counts"]["entry_refused"] == {"entry_stale": 1}
    assert json.loads(json.dumps(lifecycle)) == lifecycle
    monkeypatch.setattr(worker_mod, "_outbox_worker", None)  # no worker running
    assert engine.status()["order_dispatch_lifecycle"] is None


# ── The status constraint and the remediation script ──────────────────────────
async def test_statuses_written_are_allowed_by_the_constraint(sessions, monkeypatch):
    monkeypatch.setattr(order_service_mod, "_circuit_breaker", None)
    allowed = _allowed_order_statuses()
    assert {worker_mod.DEAD_LETTER_ORDER_STATUS, worker_mod.EXPIRED_ENTRY_ORDER_STATUS} <= set(allowed)
    assert set(cancellation.NEVER_SENT_STATUSES) <= set(cancellation.DB_TERMINAL)
    assert set(cancellation.NEVER_SENT_STATUSES) <= ACCOUNTABLE_TERMINAL_STATUSES
    result = await OrderService(sessionmaker=sessions).submit_symbol_order(
        symbol="MSFT", side="buy", qty=1, idempotency_key=f"constraint-{uuid.uuid4().hex[:8]}",
        attributes={"source": "organism", "reason": "organism_entry"})
    async with sessions() as session:
        row = await session.get(Order, uuid.UUID(result["order_id"]))
        row.status = "shadow"
        with pytest.raises(IntegrityError, match="ck_orders_status"):
            await session.commit()


def _phase7():
    path = REPO / "scripts" / "db" / "phase7_data_integrity_remediation.py"
    spec = importlib.util.spec_from_file_location("phase7_remediation_lifecycle", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def test_phase7_remediation_writes_rejected_never_failed_and_skips_live_or_owned_rows(sessions):
    remediate = _phase7()
    now = datetime(2026, 5, 6, tzinfo=UTC)
    old = now - timedelta(days=7)

    def stale_row(attributes=None):
        return Order(id=uuid.uuid4(), user_id="system", client_idempotency_key=f"p7-{uuid.uuid4()}",
                     symbol="XLE", side="sell", qty=Decimal(5), order_type="market", tif="day",
                     status="accepted", filled_qty=Decimal(0), broker_order_id=None,
                     submitted_at=old, created_at=old, attributes=attributes or {})

    def failed_event(row, last_error):
        return OutboxEvent(id=uuid.uuid4(), topic="order.submitted", status="failed", attempts=5,
                           payload={"order_id": str(row.id), "symbol": row.symbol},
                           created_at=old, next_attempt_at=old, last_error=last_error)

    plain = stale_row()
    ambiguous = stale_row()
    owned = stale_row({"outbox_dead_letter": {"state": "absence_check_pending"}})
    marker = BROKER_ACK_STATE_PREFIX + '{"version":1,"client_order_id":"x"}'
    async with sessions() as session:
        session.add_all([plain, ambiguous, owned,
                         failed_event(plain, "403: potential wash trade detected"),
                         failed_event(ambiguous, marker), failed_event(owned, "503: unavailable")])
        await session.commit()
        report = await remediate.collect_report(session, now=now)
        assert [r.order_id for r in report.stale_accepted_orders] == [str(plain.id)]
        assert [r.order_id for r in report.ambiguous_stale_orders] == [str(ambiguous.id)]
        applied = await remediate.run_remediation(session, apply=True, confirm=remediate.CONFIRM_TOKEN)
        assert applied.marked_failed_order_ids == [str(plain.id)]
    async with sessions() as session:
        rows = {str(r.id): r for r in (await session.execute(select(Order))).scalars()}
    assert rows[str(plain.id)].status == "rejected"  # accountable terminal, allowed by the constraint
    assert rows[str(plain.id)].attributes["phase7_data_integrity_cleanup"]["new_status"] == "rejected"
    assert cancellation._never_sent(rows[str(plain.id)]) is False  # no absence proof: no release
    assert rows[str(ambiguous.id)].status == "accepted" and rows[str(owned.id)].status == "accepted"
