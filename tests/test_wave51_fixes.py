"""V10 / Wave-51 (2026-05-03): tests for persistence + login completeness.

Locks regressions for:
- WW-1 (HIGH): save_essential_state mints a backup snapshot at most
  once per WW1_BACKUP_INTERVAL_SECONDS (default 1h), so production gets
  a populated backups/ dir and PP-2 corrupt-HEAD fallback has snapshots.
- PP2-1 (HIGH): lifespan does an outer-block SELECT 1 smoke check so
  unreachable host / bad creds / wrong DB trigger fail-fast (or
  ALLOW_NO_DB warn), instead of being swallowed by the prewarm's
  inner except.
- UU2-A (HIGH): successful-login rollback now logs at ERROR (mirrors
  failed-login branch from wave-41 UU-2).
- UU2-C (MEDIUM): LotTracker rollback in alpaca_stream now logs at
  ERROR.

Run with: ./venv/bin/python -m pytest tests/test_wave51_fixes.py -v
"""
from __future__ import annotations

import inspect

import pytest

from tests.test_fill_accounting_integrity import sessions as sessions


def test_ww_1_essential_save_creates_backup():
    """save_essential_state must call _create_backup with cadence."""
    from backend.organism.brain_persistence import OrganismBrain
    src = inspect.getsource(OrganismBrain.save_essential_state)
    assert "WW-1" in src, "WW-1 marker missing"
    assert "_create_backup" in src, (
        "WW-1 regression: essential-save no longer mints backups; "
        "PP-2 corrupt-HEAD fallback safety net empty in prod."
    )
    assert "WW1_BACKUP_INTERVAL_SECONDS" in src, (
        "WW-1 regression: cadence env-var removed."
    )


def test_pp2_1_lifespan_smoke_select_in_outer_block():
    """lifespan must SELECT 1 in the outer try, not just the prewarm."""
    from backend.api import lifespan
    src = inspect.getsource(lifespan)
    assert "PP2-1" in src, "PP2-1 marker missing"
    # The smoke session must precede pool prewarm.
    smoke_idx = src.find("PP2-1")
    prewarm_idx = src.find("Pre-warm connection pool")
    assert 0 < smoke_idx < prewarm_idx, (
        "PP2-1 regression: smoke check no longer precedes prewarm."
    )


def test_uu2_a_successful_login_rollback_logs_error():
    """The successful-login branch in auth.py must log rollback failure
    at ERROR (was bare `except: pass`)."""
    from backend.api.routes import auth
    src = inspect.getsource(auth)
    assert "UU2-A" in src, "UU2-A marker missing"
    # Both successful + failed login paths must use logger.error on rollback.
    # Count `logger.error` mentions of rollback-related context.
    assert src.count("UU-2") >= 1 and "UU2-A" in src, (
        "UU2-A regression: marker missing"
    )
    # The bare `except Exception: pass` shape after `await db.rollback()`
    # must be gone.
    assert (
        "await db.rollback()\n            except Exception:\n                pass"
        not in src
    ), (
        "UU2-A regression: bare except: pass on db.rollback() restored "
        "in successful-login branch."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("rollback_fails", [False, True])
async def test_uu2_c_lot_tracker_rollback_logs_error(sessions, monkeypatch, caplog, rollback_fails):
    """Real transaction failures roll back, remain retryable and log at ERROR."""
    import json
    import logging

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from backend.infra import db
    from backend.infra.schemas import Execution, Order, PositionLot
    from backend.integrations import alpaca_stream
    from backend.services.lot_tracker_service import LotTracker
    from tests.test_fill_accounting_integrity import make_order

    row = make_order()
    async with sessions() as session:
        session.add(row)
        await session.commit()
    monkeypatch.setattr(db, "get_sessionmaker", lambda: sessions)
    monkeypatch.setattr(alpaca_stream, "get_session_context", db.get_session_context)
    original_create, original_rollback = LotTracker.create_lot, AsyncSession.rollback
    lot_error = RuntimeError("synthetic lot persistence failure")
    rollback_error = RuntimeError("synthetic rollback failure")
    rollback_attempts = []

    async def fail_after_create(tracker, *args, **kwargs):
        await original_create(tracker, *args, **kwargs)
        # Both rows really reached SQLite before the injected failure; merely
        # discarding unflushed Python objects would not prove rollback.
        assert (await tracker.session.execute(select(Execution))).scalar_one()
        assert (await tracker.session.execute(select(PositionLot))).scalar_one()
        raise lot_error

    async def observed_rollback(session):
        rollback_attempts.append(session)
        if rollback_fails:
            raise rollback_error
        await original_rollback(session)

    monkeypatch.setattr(LotTracker, "create_lot", fail_after_create)
    monkeypatch.setattr(AsyncSession, "rollback", observed_rollback)
    update = {"data": {"event": "fill", "order": {
        "id": row.broker_order_id, "client_order_id": row.client_idempotency_key,
        "status": "filled", "filled_qty": "10", "filled_avg_price": "100",
    }}}
    client = alpaca_stream.AlpacaStreamClient.__new__(alpaca_stream.AlpacaStreamClient)
    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError) as caught:
        await client._process_trade_update(update)
    expected = rollback_error if rollback_fails else lot_error
    assert caught.value is expected and len(rollback_attempts) == 1
    if rollback_fails:
        assert caught.value.__context__ is lot_error
    events = [json.loads(record.getMessage()) for record in caplog.records
              if record.name == alpaca_stream.__name__ and record.levelno == logging.ERROR]
    assert any(event.get("event") == "Failed to process trade update"
               and event.get("error") == str(expected) for event in events)
    # The shared context rolls back; on rollback failure its session-close
    # cleanup still removes the uncommitted rows. Neither failure is swallowed.
    async with sessions() as session:
        saved = await session.get(Order, row.id)
        assert saved.status == "accepted" and saved.filled_qty == 0
        assert not list((await session.execute(select(Execution))).scalars())
        assert not list((await session.execute(select(PositionLot))).scalars())
