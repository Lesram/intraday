"""V5 S-J3-1 / Wave-17a (2026-05-03): tests for cross-thread alert dispatch.

Wave-8c's J-3 fix wrapped the alert path in
`get_running_loop()` + `except RuntimeError`, but `get_running_loop()`
always raises in worker threads — by definition. Every alert from a
worker thread (asyncio.to_thread, ThreadPoolExecutor) was silently
routed to logger.warning. These tests verify the new dispatcher
actually reaches the captured main loop.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from backend.infra.alerting import (
    dispatch_alert_from_thread,
    set_main_event_loop,
    get_main_event_loop,
)


@pytest.mark.asyncio
async def test_dispatch_from_main_loop_uses_create_task():
    """When already on the captured main loop, dispatch creates a task
    directly rather than using run_coroutine_threadsafe."""
    loop = asyncio.get_running_loop()
    set_main_event_loop(loop)
    delivered = asyncio.Event()

    async def _coro():
        delivered.set()

    ok = dispatch_alert_from_thread(_coro)
    assert ok is True

    # Wait briefly for the task to run.
    await asyncio.wait_for(delivered.wait(), timeout=1.0)


@pytest.mark.asyncio
async def test_dispatch_from_worker_thread_reaches_main_loop():
    """The actual S-J3-1 path: a worker thread (no running loop) must
    still successfully schedule the coroutine on the captured main loop."""
    loop = asyncio.get_running_loop()
    set_main_event_loop(loop)
    delivered = asyncio.Event()

    async def _coro():
        delivered.set()

    # Run dispatch from a fresh worker thread — there is no running loop
    # in that thread, exactly the failure mode of the wave-8c "fix".
    result_holder: dict[str, bool] = {}

    def _worker():
        result_holder["ok"] = dispatch_alert_from_thread(_coro)

    t = threading.Thread(target=_worker)
    t.start()
    t.join(timeout=2.0)
    assert result_holder.get("ok") is True

    # The main loop is still running this test; the scheduled coroutine
    # should fire as the loop processes its callback queue.
    await asyncio.wait_for(delivered.wait(), timeout=2.0)


def test_dispatch_without_captured_loop_returns_false():
    """If set_main_event_loop has not been called (or the captured loop
    is closed), dispatch returns False and does not raise."""
    set_main_event_loop(None)

    async def _coro():
        pass

    assert dispatch_alert_from_thread(_coro) is False


def test_get_main_event_loop_returns_captured_value():
    """Round-trip: set_main_event_loop / get_main_event_loop."""
    set_main_event_loop(None)
    assert get_main_event_loop() is None

    sentinel_loop = asyncio.new_event_loop()
    try:
        set_main_event_loop(sentinel_loop)
        assert get_main_event_loop() is sentinel_loop
    finally:
        set_main_event_loop(None)
        sentinel_loop.close()
