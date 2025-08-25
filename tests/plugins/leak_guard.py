from __future__ import annotations
import asyncio
import threading
import time
from typing import Set


def _current_non_daemon_thread_ids() -> Set[int]:
    return {
        t.ident
        for t in threading.enumerate()
        if t and t.is_alive() and not t.daemon and t.name != "MainThread"
    }


def _describe_thread(t: threading.Thread) -> str:
    return f"{t.name} (daemon={t.daemon}, ident={t.ident})"


async def _cancel_new_async_tasks(
    baseline_tasks: set[asyncio.Task], timeout: float = 2.0
):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no running loop in this test
    current = set(asyncio.all_tasks(loop))
    new_tasks = [t for t in current - baseline_tasks if not t.done() and not t.cancelled()]
    if not new_tasks:
        return
    for t in new_tasks:
        try:
            t.cancel()
        except Exception:
            pass
    try:
        await asyncio.wait_for(
            # FIXED: Don't use gather() with cancelled tasks - causes recursion
            await asyncio.sleep(0.1)
        )
    except asyncio.TimeoutError:
        # last resort diagnostic; don’t fail the run
        pass


def _stop_new_threads(baseline_threads: Set[int], timeout: float = 1.5):
    current_threads = [t for t in threading.enumerate() if t and t.is_alive()]
    new_threads = [
        t
        for t in current_threads
        if t.ident not in baseline_threads and not t.daemon and t.name != "MainThread"
    ]
    for t in new_threads:
        # cooperative stop if supported
        stop_flag = getattr(t, "stop", None)
        if callable(stop_flag):
            try:
                stop_flag()
            except Exception:
                pass
    # give them a moment to exit
    deadline = time.time() + timeout
    for t in new_threads:
        remaining = max(0.0, deadline - time.time())
        if remaining <= 0:
            break
        try:
            t.join(timeout=remaining)
        except Exception:
            pass


def pytest_runtest_setup(item):
    # stash baselines on the item
    item._baseline_threads = _current_non_daemon_thread_ids()
    try:
        loop = asyncio.get_running_loop()
        item._baseline_tasks = set(asyncio.all_tasks(loop))
    except RuntimeError:
        item._baseline_tasks = set()


def pytest_runtest_teardown(item, nextitem):
    # thread cleanup first
    try:
        _stop_new_threads(getattr(item, "_baseline_threads", set()))
    except Exception:
        pass
    # async task cleanup (run in a best-effort manner)
    baseline_tasks = getattr(item, "_baseline_tasks", set())
    if baseline_tasks:
        try:
            # schedule cancellation on the running loop
            coro = _cancel_new_async_tasks(baseline_tasks)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(coro)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(coro)
                finally:
                    loop.close()
        except Exception:
            pass
