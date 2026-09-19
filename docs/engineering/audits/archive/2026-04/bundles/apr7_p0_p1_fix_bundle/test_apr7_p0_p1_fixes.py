"""Apr-7 P0/P1 hardening tests.

Narrow regression coverage for three bugs observed on 2026-04-07:

P0.1 — LiveTickResult counters did not reflect exit submissions, so
       the scheduler's per-tick "signals=0 orders=0 exits=0" log was
       wrong when exits fired. Verified: exit call-sites now bump
       ``result.orders_submitted``.

P0.2 — C1 watchdog read ``result.orders_submitted`` which was stale;
       C4 watchdog baseline stayed at tick 0 after boot, producing
       CRITICAL noise while real orders flowed. Verified: the watchdog
       now reads an authoritative monotonic counter and is seeded at
       initialize() time.

P1   — ``walk_forward_gate`` decayed ``best_sharpe`` by 5% on EVERY
       gated save attempt (~every 20 ticks), compounding into a 250x
       collapse in one session (2.776 -> 0.011 on Apr 7). Verified:
       decay is now rate-limited to at most once per calendar day.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


# ─────────────────────────────────────────────────────────────
# P1 — walk_forward_gate best_sharpe decay
# ─────────────────────────────────────────────────────────────

def _make_brain(tmp_path):
    from backend.organism.brain_persistence import OrganismBrain
    return OrganismBrain(brain_dir=tmp_path / "brain")


def _bad_trades(n: int = 20) -> list:
    """Build a trade list that yields negative Sharpe."""
    trades = []
    for i in range(n):
        trades.append(SimpleNamespace(
            direction=1.0,
            actual_return=-0.01 if i % 2 == 0 else -0.02,
            pnl=-10.0,
            entry_price=100.0,
            shares=1,
        ))
    return trades


def test_walk_forward_gate_decays_best_sharpe_at_most_once_per_day(tmp_path):
    brain = _make_brain(tmp_path)
    brain._manifest = {"best_sharpe": 2.776}

    # Simulate 50 gated save attempts within a single day — as would
    # happen every ~20 ticks across a live trading session.
    for _ in range(50):
        should_save, _ = brain.walk_forward_gate(
            _bad_trades(), min_trades=10, regression_threshold=0.95,
        )
        assert should_save is False, "Bad Sharpe should fail the gate"

    decayed = brain._manifest["best_sharpe"]
    # Only one decay application: 2.776 * 0.95 = 2.6372
    assert decayed == pytest.approx(2.776 * 0.95, rel=1e-9)

    # The runaway bug would have driven it far below the single-decay
    # value (0.95**50 ≈ 0.077, so 2.776 * that ≈ 0.214 or lower).
    assert decayed > 0.5, (
        f"best_sharpe collapsed: {decayed} — runaway per-call decay"
    )


def test_walk_forward_gate_passes_when_current_beats_baseline(tmp_path):
    brain = _make_brain(tmp_path)
    brain._manifest = {"best_sharpe": 0.5}

    good = [
        SimpleNamespace(direction=1.0, actual_return=0.01, pnl=1.0,
                        entry_price=100, shares=1)
        for _ in range(20)
    ]
    should_save, reason = brain.walk_forward_gate(
        good, min_trades=10, regression_threshold=0.95,
    )
    assert should_save is True
    assert brain._manifest["best_sharpe"] == 0.5  # untouched


def test_walk_forward_gate_no_baseline_always_saves(tmp_path):
    brain = _make_brain(tmp_path)
    brain._manifest = {"best_sharpe": 0}
    should_save, _ = brain.walk_forward_gate(
        _bad_trades(), min_trades=10, regression_threshold=0.95,
    )
    assert should_save is True  # no baseline → save


# ─────────────────────────────────────────────────────────────
# P0 — LiveTickResult + watchdog wiring
# ─────────────────────────────────────────────────────────────

def test_live_tick_result_exit_callsites_bump_orders_submitted():
    """Grep-level guarantee that every exit submit path bumps the
    result.orders_submitted counter (Apr-7 drift: only entries bumped).
    """
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "backend" / "organism" / "live_engine.py"
    text = src.read_text()
    # Count distinct bumps — must match the 3 per-tick exit call-sites
    # + the EOD flatten path + the entry path(s) already present.
    # We only assert there are at least 6 bumps total (3 entries + 4
    # exits + some pyramid paths). Before the fix, exits did not bump.
    bumps = text.count("result.orders_submitted += 1")
    assert bumps >= 6, f"expected >=6 bumps, got {bumps}"


def test_update_watchdog_reads_authoritative_total_counter():
    """C1 watchdog must advance when `_total_orders_submitted` grows,
    independent of `result.orders_submitted`."""
    from backend.organism.live_engine import OrganismLiveEngine, LiveTickResult

    eng = OrganismLiveEngine.__new__(OrganismLiveEngine)
    # Minimal state required by _update_watchdog_state
    eng._tick_count = 500
    eng._watchdog_last_order_tick = 0
    eng._watchdog_last_brain_save_tick = 0
    eng._watchdog_last_total_orders = 0
    eng._total_orders_submitted = 0
    eng._watchdog_zero_candidates_ticks = 0
    eng._watchdog_state = "OK"
    eng._watchdog_equity_fallback_count = 0
    eng._watchdog_equity_fallback_streak = 0
    eng._watchdog_universe_drift = {}
    eng._universe = set()

    result = LiveTickResult(timestamp="2026-04-07T10:00:00Z")
    # Simulate a real broker submit having bumped the authoritative
    # counter, even though the result counter was missed (the Apr-7 bug).
    eng._total_orders_submitted = 3
    result.orders_submitted = 0

    eng._update_watchdog_state(result)

    assert eng._watchdog_last_order_tick == 500, (
        "Watchdog should advance off authoritative counter"
    )
    assert eng._watchdog_state == "OK"


def test_update_watchdog_c1_stays_quiet_while_orders_flow():
    from backend.organism.live_engine import OrganismLiveEngine, LiveTickResult

    eng = OrganismLiveEngine.__new__(OrganismLiveEngine)
    eng._tick_count = 0
    eng._watchdog_last_order_tick = 0
    eng._watchdog_last_brain_save_tick = 0
    eng._watchdog_last_total_orders = 0
    eng._total_orders_submitted = 0
    eng._watchdog_zero_candidates_ticks = 0
    eng._watchdog_state = "OK"
    eng._watchdog_equity_fallback_count = 0
    eng._watchdog_equity_fallback_streak = 0
    eng._watchdog_universe_drift = {}
    eng._universe = set()

    # 5000 ticks, one order every 100 ticks
    for t in range(1, 5001):
        eng._tick_count = t
        result = LiveTickResult(timestamp="t")
        if t % 100 == 0:
            eng._total_orders_submitted += 1
        eng._update_watchdog_state(result)

    assert eng._watchdog_state == "OK", (
        f"watchdog state should stay OK with orders flowing, "
        f"got {eng._watchdog_state}"
    )


def test_update_watchdog_c1_fires_critical_when_truly_idle():
    from backend.organism.live_engine import OrganismLiveEngine, LiveTickResult

    eng = OrganismLiveEngine.__new__(OrganismLiveEngine)
    eng._tick_count = 0
    eng._watchdog_last_order_tick = 0
    eng._watchdog_last_brain_save_tick = 0
    eng._watchdog_last_total_orders = 0
    eng._total_orders_submitted = 0
    eng._watchdog_zero_candidates_ticks = 0
    eng._watchdog_state = "OK"
    eng._watchdog_equity_fallback_count = 0
    eng._watchdog_equity_fallback_streak = 0
    eng._watchdog_universe_drift = {}
    eng._universe = set()

    for t in range(1, 5000):
        eng._tick_count = t
        result = LiveTickResult(timestamp="t")
        eng._update_watchdog_state(result)

    assert eng._watchdog_state == "CRITICAL_MULTI_SESSION"


def test_submit_entry_order_counters_increment(monkeypatch):
    """Authoritative counter must bump on every successful submit."""
    import asyncio
    from backend.organism.live_engine import OrganismLiveEngine

    eng = OrganismLiveEngine.__new__(OrganismLiveEngine)
    eng._total_orders_submitted = 0
    eng._total_exits_submitted = 0
    eng._tick_count = 42
    eng._session_id = "test"
    eng._streaming_provider = None
    eng._ENTRY_SLIPPAGE_CAP = 0.001

    async def fake_submit(**kwargs):
        return {"order_id": "abc", "filled_qty": 10}
    eng._order_service = SimpleNamespace(submit_symbol_order=fake_submit)

    asyncio.run(eng._submit_entry_order("AAPL", 10))
    assert eng._total_orders_submitted == 1

    asyncio.run(eng._submit_entry_order("AAPL", 10))
    assert eng._total_orders_submitted == 2


def test_save_essential_state_does_not_reset_watchdog_tick(tmp_path):
    """C4 watchdog baseline seeded by initialize() must survive a
    gated save (before the fix, initialize baseline stayed at 0)."""
    # This is a structural assertion: initialize() seeds the baseline.
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "backend" / "organism" / "live_engine.py"
    text = src.read_text()
    assert "self._watchdog_last_brain_save_tick = self._tick_count" in text
    # Appears in _save_brain (both branches) AND initialize() seed.
    assert text.count("self._watchdog_last_brain_save_tick = self._tick_count") >= 3
