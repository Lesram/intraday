"""V12 W74 behavioral tests for data-integrity fixes.

Findings closed by W74:
- BB5-F1 (HIGH): outbox_events unbounded → ``prune_old_events`` +
  periodic ``start_prune_loop`` on ``OutboxWorker``.
- EXT-4 (MED): audit_logs only stores ``hash_chain``; auditors can't
  independently verify per-row chain.  New
  ``ComplianceAuditService.get_chain_detail`` + ``GET /audit/chain-detail``
  exposes prev/current/expected per row.

V12 commitment: every assertion here is behavioral.  The prune tests
mint real OutboxEvent rows in an in-memory SQLite, call the real
``prune_old_events`` method, and assert on observed row counts.  The
chain-detail tests insert real audit rows, call the real service
method, and assert on the per-row return shape and chain progression.

Run with:
    ./venv/bin/python -m pytest tests/test_v12_w74_data_integrity.py -v
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio


# ────────────────────────────────────────────────────────────────────
# BB5-F1 — Outbox retention prune.
# ────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def sqlite_outbox_session():
    """In-memory SQLite session with the OutboxEvent table created.

    SQLite doesn't natively support PG UUID/Enum/JSON, but SQLAlchemy
    falls back to TEXT/JSON-as-TEXT, which works for the prune logic
    (all the prune cares about is ``id``, ``status``, ``created_at``).
    """
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import (
        async_sessionmaker, create_async_engine,
    )
    from sqlalchemy.pool import StaticPool

    from backend.infra.schemas import Base, OutboxEvent  # noqa: F401 — registers metadata

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        # StaticPool ensures the in-memory DB is shared across the
        # session's connections; without this, aiosqlite's pool gives
        # multiple short-lived connections each with its own ":memory:"
        # state, and table creation collides on parallel attempts.
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        # Only create the outbox table to keep the fixture cheap.
        await conn.run_sync(
            lambda sync_conn: OutboxEvent.__table__.create(sync_conn)
        )

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    yield sessionmaker, OutboxEvent
    await engine.dispose()


def _make_event(*, status: str, age_days: int, OutboxEvent):
    return OutboxEvent(
        id=uuid.uuid4(),
        topic="test.event",
        payload={"k": "v"},
        status=status,
        attempts=0,
        created_at=datetime.now(UTC) - timedelta(days=age_days),
    )


@pytest.mark.asyncio
async def test_bb5_f1_prune_deletes_old_sent_events(sqlite_outbox_session):
    """Sent events older than retention are pruned; pending preserved."""
    sessionmaker, OutboxEvent = sqlite_outbox_session
    from backend.infra.outbox_worker import OutboxWorker
    from sqlalchemy import select

    # Seed: 3 old sent (40d), 2 fresh sent (1d), 2 old pending (40d), 1 old failed (40d)
    async with sessionmaker() as s:
        for _ in range(3):
            s.add(_make_event(status="sent", age_days=40, OutboxEvent=OutboxEvent))
        for _ in range(2):
            s.add(_make_event(status="sent", age_days=1, OutboxEvent=OutboxEvent))
        for _ in range(2):
            s.add(_make_event(status="pending", age_days=40, OutboxEvent=OutboxEvent))
        s.add(_make_event(status="failed", age_days=40, OutboxEvent=OutboxEvent))
        await s.commit()

    worker = OutboxWorker.__new__(OutboxWorker)
    worker.sessionmaker = sessionmaker

    pruned = await worker.prune_old_events(max_age_days=30)
    # 3 sent + 1 failed = 4 deleted; 2 fresh sent + 2 old pending = 4 preserved.
    assert pruned == 4

    async with sessionmaker() as s:
        rows = (await s.execute(select(OutboxEvent))).scalars().all()
        assert len(rows) == 4
        # All remaining either pending (any age) or sent <30d.
        for r in rows:
            if r.status == "pending":
                continue
            assert r.status == "sent"
            age = (datetime.now(UTC) - r.created_at.replace(tzinfo=UTC)).days
            assert age < 30


@pytest.mark.asyncio
async def test_bb5_f1_prune_never_deletes_pending(sqlite_outbox_session):
    """Even very old pending events are preserved — they represent
    unfinished work."""
    sessionmaker, OutboxEvent = sqlite_outbox_session
    from backend.infra.outbox_worker import OutboxWorker
    from sqlalchemy import select

    async with sessionmaker() as s:
        for _ in range(5):
            s.add(_make_event(status="pending", age_days=365, OutboxEvent=OutboxEvent))
        await s.commit()

    worker = OutboxWorker.__new__(OutboxWorker)
    worker.sessionmaker = sessionmaker

    pruned = await worker.prune_old_events(max_age_days=30)
    assert pruned == 0
    async with sessionmaker() as s:
        rows = (await s.execute(select(OutboxEvent))).scalars().all()
        assert len(rows) == 5


@pytest.mark.asyncio
async def test_bb5_f1_prune_returns_zero_when_nothing_to_prune(sqlite_outbox_session):
    """No sent/failed older than cutoff → 0 pruned, no errors."""
    sessionmaker, OutboxEvent = sqlite_outbox_session
    from backend.infra.outbox_worker import OutboxWorker

    async with sessionmaker() as s:
        for _ in range(3):
            s.add(_make_event(status="sent", age_days=2, OutboxEvent=OutboxEvent))
        await s.commit()

    worker = OutboxWorker.__new__(OutboxWorker)
    worker.sessionmaker = sessionmaker

    pruned = await worker.prune_old_events(max_age_days=30)
    assert pruned == 0


@pytest.mark.asyncio
async def test_bb5_f1_prune_loop_can_be_started_and_stopped(sqlite_outbox_session):
    """``start_prune_loop`` is idempotent and ``stop`` cancels it."""
    sessionmaker, OutboxEvent = sqlite_outbox_session
    from backend.infra.outbox_worker import OutboxWorker

    worker = OutboxWorker.__new__(OutboxWorker)
    worker.sessionmaker = sessionmaker
    worker._running = True
    worker._task = None
    worker._prune_task = None

    # Use a tiny interval so we can verify the loop runs at least once.
    await worker.start_prune_loop(max_age_days=30, interval_seconds=0.05)
    assert worker._prune_task is not None
    # Calling again must not start a second task.
    first_task = worker._prune_task
    await worker.start_prune_loop(max_age_days=30, interval_seconds=0.05)
    assert worker._prune_task is first_task
    # Stop tears it down.
    await worker.stop()
    assert worker._prune_task is None


@pytest.mark.asyncio
async def test_bb5_f1_start_outbox_worker_wires_prune_loop(sqlite_outbox_session, monkeypatch):
    """V12 W80 (post-audit cleanup): the public ``start_outbox_worker``
    entrypoint must wire ``start_prune_loop()`` automatically — not
    just the helper.  V12 W74 left the loop unwired, leaving the live
    DB with 1398 unrupned rows (auditor's BB5-F1 'fix didn't fix' callout)."""
    sessionmaker, _ = sqlite_outbox_session
    import backend.infra.outbox_worker as obw

    # Reset the module-level singleton so we get a clean construction.
    monkeypatch.setattr(obw, "_outbox_worker", None, raising=False)
    # Tiny interval so the test doesn't sleep 24h.
    monkeypatch.setenv("OUTBOX_PRUNE_INTERVAL_SECONDS", "0.05")
    monkeypatch.setenv("OUTBOX_RETENTION_DAYS", "30")

    worker = await obw.start_outbox_worker(sessionmaker)
    try:
        assert worker._running is True
        # The auditor's specific point: the prune loop MUST be running
        # after start_outbox_worker() returns, not just available as
        # a helper.
        assert worker._prune_task is not None, (
            "BB5-F1 regression: start_outbox_worker did not call "
            "start_prune_loop. Live outbox would grow unbounded again."
        )
    finally:
        await worker.stop()


# ────────────────────────────────────────────────────────────────────
# EXT-4 — Audit chain per-row detail endpoint.
# ────────────────────────────────────────────────────────────────────

class _FakeAuditSession:
    """Minimal DB session that returns a pre-built list of AuditLog
    objects on query execution.  Behavioral approach: the
    ComplianceAuditService.get_chain_detail logic is exercised against
    real AuditLog instances; only the SQL layer is faked because the
    AuditLog schema has a duplicate ``ix_audit_logs_ts`` index
    declaration (column-level ``index=True`` plus explicit ``Index()``
    in ``__table_args__``) that collides on SQLite ``CREATE INDEX``.

    Filed as a follow-up V12 finding (W74-FOLLOWUP-1) — fixing it is a
    schema migration outside this wave's scope; the fake-session
    approach lets us still test the chain-detail logic behaviorally.
    """

    def __init__(self, rows):
        self._rows = list(rows)

    async def execute(self, _query):
        # Return a result whose ``scalars().all()`` yields our rows.
        rows = self._rows

        class _Scalars:
            def all(self_inner):
                return rows

        class _Result:
            def scalars(self_inner):
                return _Scalars()

        return _Result()


@pytest_asyncio.fixture
async def sqlite_audit_session():
    """Yield (fake-session, AuditLog cls).  See _FakeAuditSession docstring
    for why this is a fake instead of a real SQLite DB."""
    from backend.infra.schemas import AuditLog
    sess = _FakeAuditSession(rows=[])
    yield sess, AuditLog


def _seed_chain(sess, AuditLog, n: int = 5):
    """Build n audit rows with a valid hash chain and inject them into
    the (fake) session's row buffer.  Each row's ``hash_chain`` is
    computed from the previous row's hash + this row's content via the
    same ``_compute_hash`` function used by the service."""
    from backend.services.audit_service import _compute_hash

    rows = []
    prev = None
    base_ts = datetime.now(UTC) - timedelta(minutes=n)
    for i in range(n):
        ts = base_ts + timedelta(minutes=i)
        action = f"test.action.{i}"
        entity = "test_entity"
        entity_id = str(uuid.uuid4())
        actor = f"user{i}"
        payload = {"step": i}
        h = _compute_hash(
            previous_hash=prev, timestamp=ts, action=action,
            entity=entity, entity_id=entity_id, actor=actor, payload=payload,
        )
        row = AuditLog(
            id=uuid.uuid4(), ts=ts, actor=actor, action=action,
            entity=entity, entity_id=entity_id, payload=payload,
            hash_chain=h,
        )
        rows.append(row)
        prev = h
    sess._rows = rows
    return rows


@pytest.mark.asyncio
async def test_ext_4_chain_detail_returns_all_valid_for_clean_chain(sqlite_audit_session):
    """A clean chain returns all rows valid; first row is the anchor."""
    sess, AuditLog = sqlite_audit_session
    _seed_chain(sess, AuditLog, n=5)

    from backend.services.audit_service import ComplianceAuditService
    service = ComplianceAuditService(sess)
    result = await service.get_chain_detail(limit=100)

    assert result["row_count"] == 5
    assert result["all_valid"] is True
    rows = result["rows"]
    assert rows[0]["anchor"] is True
    assert rows[0]["expected_hash"] is None  # anchor has no expected
    for r in rows[1:]:
        assert r["anchor"] is False
        assert r["valid"] is True
        # prev_hash + current_hash both populated and non-empty.
        assert r["prev_hash"]
        assert r["current_hash"]
        assert r["expected_hash"] == r["current_hash"]


@pytest.mark.asyncio
async def test_ext_4_chain_detail_flags_tampered_row(sqlite_audit_session):
    """Mutate one row's payload in-place; chain detail flags THAT row
    invalid but anchors back to stored hash so subsequent rows aren't
    cascade-invalidated."""
    sess, AuditLog = sqlite_audit_session
    rows = _seed_chain(sess, AuditLog, n=5)

    # Tamper with row index 2 (the third row).  Change the payload but
    # leave the stored hash_chain unchanged — that's the tampering
    # signature: someone modified the data after the chain was sealed.
    rows[2].payload = {"tampered": True}

    from backend.services.audit_service import ComplianceAuditService
    service = ComplianceAuditService(sess)
    result = await service.get_chain_detail(limit=100)

    assert result["all_valid"] is False
    rows_out = result["rows"]
    # Anchor (row 0) and row 1 are still valid (no tampering before).
    assert rows_out[0]["valid"] is True
    assert rows_out[1]["valid"] is True
    # Row 2 — the tampered one — must be flagged invalid.
    assert rows_out[2]["valid"] is False
    assert rows_out[2]["expected_hash"] != rows_out[2]["current_hash"]
    # Rows after: chain progression uses STORED hash so they re-anchor.
    # That means rows 3 and 4 are individually still valid against their
    # OWN stored chain (we computed expected from row 2's stored hash).
    # This is the desired behavior — auditors want to localize the
    # break, not see false-positive cascade.
    assert rows_out[3]["valid"] is True
    assert rows_out[4]["valid"] is True


@pytest.mark.asyncio
async def test_ext_4_chain_detail_anchor_for_first_row(sqlite_audit_session):
    """The first row in the queried window is treated as the anchor —
    we cannot independently verify it without the previous row."""
    sess, AuditLog = sqlite_audit_session
    _seed_chain(sess, AuditLog, n=1)

    from backend.services.audit_service import ComplianceAuditService
    service = ComplianceAuditService(sess)
    result = await service.get_chain_detail(limit=100)

    assert result["row_count"] == 1
    assert result["rows"][0]["anchor"] is True
    assert result["rows"][0]["expected_hash"] is None
    assert result["all_valid"] is True


# ────────────────────────────────────────────────────────────────────
# EXT-4 endpoint registration: lock the route in the FastAPI app.
# ────────────────────────────────────────────────────────────────────

def test_ext_4_chain_detail_endpoint_is_registered():
    """``GET /api/v1/audit/chain-detail`` must be mounted by the app
    factory.  AST/route-table assertion — not a string grep."""
    from backend.api.factory import create_app

    app = create_app()
    paths = {r.path for r in app.routes}
    assert "/api/v1/audit/chain-detail" in paths, (
        f"EXT-4 regression: chain-detail endpoint not mounted. "
        f"Got audit paths: {[p for p in paths if 'audit' in p]}"
    )
