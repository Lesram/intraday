from __future__ import annotations
import asyncio, threading, time, sys, faulthandler

def _non_daemon_ids():
    return {t.ident for t in threading.enumerate()
            if t and t.is_alive() and not t.daemon and t.name!="MainThread"}

def pytest_sessionstart(session):
    try: faulthandler.enable(file=sys.stderr)
    except Exception: pass
    session._baseline_threads = _non_daemon_ids()
    try:
        loop = asyncio.get_event_loop()
        session._baseline_tasks = set(asyncio.all_tasks(loop))
    except RuntimeError:
        session._baseline_tasks = set()

def pytest_sessionfinish(session, exitstatus):
    import time  # Import time module
    base = getattr(session,"_baseline_threads",set())
    deadline = time.time()+2.0
    for t in list(threading.enumerate()):
        if not t or not t.is_alive(): continue
        if t.daemon or t.name=="MainThread" or t.ident in base: continue
        try:
            stop = getattr(t,"stop",None)
            if callable(stop): stop()
        except Exception: pass
    while time.time()<deadline:
        alive=[t for t in threading.enumerate()
               if t and t.is_alive() and not t.daemon and t.name!="MainThread" and t.ident not in base]
        if not alive: break
        time.sleep(0.05)
    try:
        loop = asyncio.get_event_loop()
        current=set(asyncio.all_tasks(loop))
        new=[t for t in current - getattr(session,"_baseline_tasks",set()) if not t.done() and not t.cancelled()]
        for t in new:
            try: t.cancel()
            except Exception: pass
        if new:
            try:
                # FIXED: Don't use gather() with cancelled tasks - causes recursion  
                import time
                time.sleep(0.1)
            except Exception: pass
    except RuntimeError:
        pass
