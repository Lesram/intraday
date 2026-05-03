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


# ─────────────────────────────────────────────────────────────────────
# DD3-2 — LotTracker incremental fill semantics
# ─────────────────────────────────────────────────────────────────────


def test_dd3_2_alpaca_stream_uses_incremental_qty():
    """alpaca_stream._process_trade_update must capture
    `_prev_filled_qty` BEFORE updating, then pass `_incremental` to
    LotTracker.create_lot, NOT the cumulative filled_qty."""
    from backend.integrations import alpaca_stream
    src = inspect.getsource(alpaca_stream)
    assert "DD3-2" in src, "DD3-2 marker missing from alpaca_stream"
    assert "_prev_filled_qty" in src, (
        "DD3-2 regression: alpaca_stream no longer captures previous "
        "cumulative filled_qty before updating."
    )
    assert "_incremental" in src, (
        "DD3-2 regression: alpaca_stream no longer computes incremental "
        "fill quantity — duplicates would resurface on multi-event fills."
    )


def test_dd3_2_zero_or_negative_increment_skipped():
    """If _incremental <= 0 (duplicate or stale event), the LotTracker
    op must be skipped (debug log only)."""
    from backend.integrations import alpaca_stream
    src = inspect.getsource(alpaca_stream)
    assert "if _incremental <= 0:" in src, (
        "DD3-2 regression: zero/negative incremental check removed. "
        "Duplicate Alpaca events would create duplicate lots."
    )


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
