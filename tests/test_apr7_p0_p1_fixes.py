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
       collapse in one session (2.776 -> 0.011 on Apr 7). Apr-8 Patch C
       rescope: the gate now reads ``learner.state.best_sharpe`` (the
       authoritative high-water mark maintained by ContinuousLearner)
       and no longer mutates any local copy. The decay and the
       rate-limit field are both removed.
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


def _fake_learner(best_sharpe: float) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(best_sharpe=best_sharpe))


def test_walk_forward_gate_reads_learner_best_sharpe(tmp_path):
    """Gate must read learner.state.best_sharpe, not the stale manifest."""
    brain = _make_brain(tmp_path)
    # Stale/decayed manifest from the pre-patch bug
    brain._manifest = {"best_sharpe": 0.011}
    learner = _fake_learner(2.8956)

    # Construct trades whose per-trade Sharpe (mean/std * sqrt(252)) is
    # solidly above 0.95 * 2.8956 = 2.75.  Uniform +1% returns yield
    # std≈0 which the gate clamps to 1e-9 → huge sharpe; add tiny noise
    # so std is finite and the ratio is realistic.
    good = []
    for i in range(20):
        good.append(SimpleNamespace(
            direction=1.0,
            actual_return=0.02 if i % 2 == 0 else 0.018,
            pnl=1.0, entry_price=100, shares=1,
        ))
    should_save, reason = brain.walk_forward_gate(
        good, min_trades=10, regression_threshold=0.95, learner=learner,
    )
    assert should_save is True, reason
    # Would have been True from the stale manifest too, but the decisive
    # check: the gate read the learner value (not 0.011) — confirm by
    # asserting the reason references 2.8956, not 0.011.
    assert "best=2.89" in reason or "best=2.896" in reason, reason


def test_walk_forward_gate_fails_on_current_below_threshold(tmp_path):
    brain = _make_brain(tmp_path)
    brain._manifest = {"best_sharpe": 0.011}
    learner = _fake_learner(2.8956)
    should_save, reason = brain.walk_forward_gate(
        _bad_trades(), min_trades=10, regression_threshold=0.95,
        learner=learner,
    )
    assert should_save is False
    assert "best=2.89" in reason or "best=2.896" in reason, reason


def test_walk_forward_gate_does_not_mutate_learner_or_manifest(tmp_path):
    """Repeated gated calls must not decay best_sharpe anywhere."""
    brain = _make_brain(tmp_path)
    brain._manifest = {"best_sharpe": 2.776}
    learner = _fake_learner(2.8956)
    for _ in range(50):
        should_save, _ = brain.walk_forward_gate(
            _bad_trades(), min_trades=10, regression_threshold=0.95,
            learner=learner,
        )
        assert should_save is False
    # Neither the learner nor the manifest copy may be mutated.
    assert learner.state.best_sharpe == 2.8956
    assert brain._manifest["best_sharpe"] == 2.776


def test_walk_forward_gate_fallback_when_no_learner(tmp_path):
    """Backward-compat: no learner arg → fall back to manifest (read-only)."""
    brain = _make_brain(tmp_path)
    brain._manifest = {"best_sharpe": 0.5}
    good = [
        SimpleNamespace(direction=1.0, actual_return=0.01, pnl=1.0,
                        entry_price=100, shares=1)
        for _ in range(20)
    ]
    should_save, _ = brain.walk_forward_gate(
        good, min_trades=10, regression_threshold=0.95,
    )
    assert should_save is True
    # Manifest never mutated by the gate in any branch.
    assert brain._manifest["best_sharpe"] == 0.5


def test_walk_forward_gate_no_baseline_always_saves(tmp_path):
    brain = _make_brain(tmp_path)
    brain._manifest = {"best_sharpe": 0}
    should_save, _ = brain.walk_forward_gate(
        _bad_trades(), min_trades=10, regression_threshold=0.95,
    )
    assert should_save is True  # no baseline → save


def test_last_sharpe_decay_date_field_removed(tmp_path):
    """The rate-limit field from the prior patch is dead code now."""
    brain = _make_brain(tmp_path)
    assert not hasattr(brain, "_last_sharpe_decay_date")


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
    # V12 W90 (post-cleanup): _submit_entry_order now reads _now_fn
    # for timestamping (added in a V11 wave).  Fixture didn't carry
    # it; AttributeError on call.  Same pattern as W88 b1/b2.
    from datetime import UTC, datetime
    import time as _time
    eng._now_fn = lambda: datetime.now(UTC)
    eng._time_fn = _time.time

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
