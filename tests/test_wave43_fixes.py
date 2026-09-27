"""V9 / Wave-43 (2026-05-03): tests for LotTracker partial-fill + oversell race.

Locks the regressions for:
- DD3-2 (HIGH): LotTracker.create_lot now uses INCREMENTAL fill qty
  (filled_now - filled_previously) per partially_filled event, not
  cumulative. Eliminates duplicate position_lots rows on multi-event
  fills.
- DD3-3 (HIGH): exit path consults _exit_cooldown so an expired
  _pending_exit (3-tick TTL) doesn't trigger an oversell when the
  broker fill is still pending.

Run with: ./venv/bin/python -m pytest tests/test_wave43_fixes.py -v
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


# ─────────────────────────────────────────────────────────────────────
# DD3-2 — LotTracker incremental fill semantics
# ─────────────────────────────────────────────────────────────────────


async def test_dd3_2_alpaca_stream_uses_incremental_qty():
    """A prior cumulative summary must not masquerade as accounted executions."""
    from decimal import Decimal
    from unittest.mock import patch
    from backend.integrations.alpaca_stream import apply_incremental_fill_accounting

    results = [SimpleNamespace(scalar_one_or_none=lambda: "order-1"),
               SimpleNamespace(scalar_one_or_none=lambda: 5),
               SimpleNamespace(scalar_one_or_none=lambda: 500)]
    session = SimpleNamespace(execute=AsyncMock(side_effect=results), add=MagicMock(), flush=AsyncMock())
    order = SimpleNamespace(id="order-1", symbol="AAPL", side="buy", submitted_at=None,
                            filled_at=None, user_id="test", attributes={})
    with patch("backend.services.lot_tracker_service.LotTracker.create_lot", new_callable=AsyncMock) as lot:
        result = await apply_incremental_fill_accounting(session, order, previous_filled_qty=10,
            cumulative_filled_qty=10, avg_fill_price=110, status="filled")
    assert result["applied"] and lot.await_args.kwargs["qty"] == Decimal(5)
    assert lot.await_args.kwargs["cost_basis"] == Decimal(120)
    execution = session.add.call_args.args[0]
    assert execution.fill_qty == 5 and execution.fill_price == 120


async def test_dd3_2_zero_or_negative_increment_skipped_behaviorally():
    """Duplicate/stale cumulative fills must not create lots or executions."""
    from backend.integrations.alpaca_stream import apply_incremental_fill_accounting

    results = [SimpleNamespace(scalar_one_or_none=lambda: "order-1"),
               SimpleNamespace(scalar_one_or_none=lambda: 10),
               SimpleNamespace(scalar_one_or_none=lambda: 1000)]
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=results),
        add=AsyncMock(),
        flush=AsyncMock(),
    )
    order = SimpleNamespace(
        id="order-1",
        symbol="AAPL",
        side="buy",
        submitted_at=None,
        filled_at=None,
    )

    result = await apply_incremental_fill_accounting(
        session,
        order,
        previous_filled_qty=10,
        cumulative_filled_qty=10,
        avg_fill_price=100,
        status="partially_filled",
    )

    assert result["applied"] is False
    assert result["reason"] == "duplicate_or_stale_fill"
    session.add.assert_not_called()
    session.flush.assert_not_called()


# ─────────────────────────────────────────────────────────────────────
# DD3-3 — _exit_cooldown consultation on exit path
# ─────────────────────────────────────────────────────────────────────


def test_dd3_3_exit_path_consults_exit_cooldown():
    """The exit-loop tick path must check _exit_cooldown so an
    expired _pending_exit (3-tick TTL) followed by a still-unfilled
    broker order doesn't trigger an oversell on the next exit-check."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    assert "DD3-3" in src, "DD3-3 marker missing from _live_tick_inner"
    # The new gate must reference _exit_cooldown and skip routine exits
    # when within the cooldown window AND not already pending.
    assert "_exit_cooldown[sym]" in src, (
        "DD3-3 regression: exit path no longer reads _exit_cooldown. "
        "Oversell race window after _pending_exit TTL expiry."
    )
    # The new gate is BEFORE the V8 DD2-1 pending_exit safety check.
    dd3_idx = src.find("DD3-3")
    dd2_idx = src.find("DD2-1")
    assert 0 < dd3_idx < dd2_idx, (
        "DD3-3 regression: cooldown gate must precede the DD2-1 safety "
        f"net (DD3-3 at {dd3_idx}, DD2-1 at {dd2_idx})."
    )
