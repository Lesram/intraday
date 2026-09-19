"""V9 / Wave-46 (2026-05-03): tests for tick watchdog (TT-2).

Locks the regression for:
- TT-2 (HIGH): live_tick() wraps _live_tick_inner in asyncio.wait_for
  with a 30s watchdog so stream-reconnect / DB-query hangs no longer
  stall the scheduler indefinitely (production data showed 1987s and
  1256s outliers).

Note on TT-1 (tick budget reduction): the 30s watchdog provides a hard
upper bound; further p99 reduction (currently ~13s on a 10s scheduler)
is performance optimization tracked for V10.

Run with: ./venv/bin/python -m pytest tests/test_wave46_fixes.py -v
"""
from __future__ import annotations

import asyncio
import inspect

import pytest


def test_tt_2_watchdog_constant_present():
    """OrganismLiveEngine._TICK_WATCHDOG_SECONDS must exist."""
    from backend.organism.live_engine import OrganismLiveEngine
    assert hasattr(OrganismLiveEngine, "_TICK_WATCHDOG_SECONDS"), (
        "TT-2 regression: _TICK_WATCHDOG_SECONDS removed."
    )
    assert OrganismLiveEngine._TICK_WATCHDOG_SECONDS > 0


def test_tt_2_live_tick_uses_wait_for():
    """live_tick must wrap _live_tick_inner in asyncio.wait_for."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine.live_tick)
    assert "TT-2" in src, "TT-2 marker missing"
    assert "asyncio.wait_for" in src, (
        "TT-2 regression: live_tick no longer wraps inner in wait_for; "
        "stream-reconnect hangs can stall scheduler indefinitely."
    )
    assert "TimeoutError" in src, (
        "TT-2 regression: TimeoutError handler removed."
    )


@pytest.mark.asyncio
async def test_tt_2_watchdog_fires_on_hung_inner(monkeypatch):
    """If _live_tick_inner hangs longer than the watchdog, live_tick
    returns a degraded LiveTickResult and increments the counter."""
    from backend.organism.live_engine import OrganismLiveEngine, LiveTickResult

    # Build a minimal fake engine instance with the bare attrs needed.
    eng = OrganismLiveEngine.__new__(OrganismLiveEngine)
    eng._tick_lock = asyncio.Lock()
    eng._tick_watchdog_timeouts = 0
    from datetime import UTC, datetime
    eng._now_fn = lambda: datetime.now(UTC)
    # Override watchdog to 0.1s for a fast test.
    eng._TICK_WATCHDOG_SECONDS = 0.1

    async def hang(*_args, **_kwargs):
        await asyncio.sleep(5.0)
        return LiveTickResult(timestamp="never")

    eng._live_tick_inner = hang  # type: ignore[assignment]

    result = await OrganismLiveEngine.live_tick(eng)
    assert isinstance(result, LiveTickResult)
    assert any("watchdog" in e.lower() for e in result.errors), (
        f"TT-2 regression: degraded result errors don't mention watchdog: "
        f"{result.errors}"
    )
    assert eng._tick_watchdog_timeouts == 1
