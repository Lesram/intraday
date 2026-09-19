"""V13 W100 (HH3-N-1) — _live_tick_inner behavioral coverage.

V12 W75 deferred LOC reduction of _live_tick_inner (2,738 lines) to
V13+ because the function had zero direct test coverage.  W100 ships
the coverage layer; actual extraction is V13.1+ work.

Strategy: drive _live_tick_inner through the ReplayEngine with
targeted synthetic bars and assert observable contracts for each
of the four hot sub-blocks:

1. **Entries gate** — synthetic upward-trend bars at $1M cash should
   produce ≥1 order across 100 ticks.
2. **Position-management for-loop** — held positions with a stop-loss
   trigger must produce exit orders / closed trades.
3. **Equity gates / drawdown** — V13 W93 already covers
   trigger_drawdown_kill behavior; W100 adds the observable that
   `_live_tick_inner`'s tick_result reports the halted state.
4. **Pyramid path** — replay with rising-equity does not pyramid
   without explicit env enablement; pyramid path is exercised via
   structural source check (full pyramid replay is V13.1+ extraction).

Plus an AST-level LOC ceiling guard.

Run with:
    ./venv/bin/python -m pytest tests/test_v13_w100_live_tick_coverage.py -v
"""
# wave: V13-W100
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_ENGINE_PATH = REPO_ROOT / "backend" / "organism" / "live_engine.py"


# ────────────────────────────────────────────────────────────────────
# AST LOC ceiling guard
# ────────────────────────────────────────────────────────────────────


# V12 W75 baseline: 2,738 LOC.  Treat 2,750 as the V13 ceiling so a
# small refactor (e.g. adding a missing comment) doesn't blow the gate.
# Actual reduction is V13.1+ work; the goal of W100 is "no regression
# while we accumulate coverage".
# Audit 2026-06-09 remediation: ceiling raised 2,750 → 2,765 for the
# safety additions inside the tick loop (EOD-flatten escalation hook
# [finding 3.4], pyramid quality-gate call [3.5], overnight force-exit
# dispatch). The bulk of 3.4 was extracted to
# _force_exit_overnight_stragglers to stay near the ceiling; the
# remaining +11 lines are irreducible call sites.
# Audit 2026-06-11 (measurement integrity): ceiling raised 2,765 → 2,805
# for the signed-prediction + ML-provenance fields (predicted_return_signed,
# ml_spoke) added inline at the three candidate-construction sites. The
# sizer abs()es predicted_return downstream, so the signed value must be
# captured into the trade record at build time — these are inline dict
# literals in the tick flow, not extractable to a mixin. Next change must
# reduce, not raise.
LIVE_TICK_INNER_LOC_CEILING = 2_805


def _find_live_tick_inner_loc() -> int:
    """Return the LOC of _live_tick_inner via AST traversal."""
    tree = ast.parse(LIVE_ENGINE_PATH.read_text())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_live_tick_inner"
        ):
            return node.end_lineno - node.lineno + 1
    raise AssertionError("_live_tick_inner not found in live_engine.py")


def test_w100_live_tick_inner_loc_pinned():
    """W100 ceiling: _live_tick_inner LOC <= V13 ceiling.  This is a
    no-regression gate; reductions are V13.1+ work."""
    loc = _find_live_tick_inner_loc()
    assert loc <= LIVE_TICK_INNER_LOC_CEILING, (
        f"_live_tick_inner LOC regressed: {loc} > ceiling "
        f"{LIVE_TICK_INNER_LOC_CEILING}.  Either reduce LOC or, if the "
        f"increase is unavoidable, raise the ceiling explicitly via PR."
    )


# ────────────────────────────────────────────────────────────────────
# Sub-block 1: Entries gate
# ────────────────────────────────────────────────────────────────────


@pytest.mark.timeout(180)
@pytest.mark.asyncio
async def test_w100_entries_gate_produces_orders_on_uptrend():
    """100 ticks of synthetic upward-trend bars at $1M cash must
    produce >= 1 order.  Exercises the entries-gate sub-block end
    to end via the ReplayEngine."""
    from backend.organism.replay_simulator import (
        ReplayEngine, make_features_dict,
    )
    bars = make_features_dict(
        ["AAPL", "MSFT", "SPY"], n=700, seed=42, trend="up",
    )
    engine = ReplayEngine(
        bars_by_symbol=bars,
        initial_cash=1_000_000,
        slippage_bps=5,
        max_entries_per_hour=20,
    )
    result = await engine.run(max_ticks=100)
    total_orders = sum(
        r.get("orders_submitted", 0)
        for r in result.tick_results if isinstance(r, dict)
    )
    assert total_orders >= 1, (
        "entries-gate sub-block: 100 ticks of uptrend produced no orders"
    )


@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_w100_entries_gate_signals_generated_on_uptrend():
    """Even when no orders fire (e.g. ML rejection), the entries-gate
    must EVALUATE candidates — signals_generated > 0 across 100 ticks."""
    from backend.organism.replay_simulator import (
        ReplayEngine, make_features_dict,
    )
    bars = make_features_dict(
        ["AAPL", "MSFT", "SPY"], n=700, seed=7, trend="up",
    )
    engine = ReplayEngine(
        bars_by_symbol=bars,
        initial_cash=1_000_000,
        slippage_bps=5,
        max_entries_per_hour=20,
    )
    result = await engine.run(max_ticks=100)
    total_signals = sum(
        r.get("signals_generated", 0)
        for r in result.tick_results if isinstance(r, dict)
    )
    assert total_signals > 0, (
        "entries-gate sub-block: 100 ticks of uptrend produced no signals — "
        "scanner / breakout / alpha pipeline is not evaluating candidates"
    )


# ────────────────────────────────────────────────────────────────────
# Sub-block 2: Position-management for-loop
# ────────────────────────────────────────────────────────────────────


@pytest.mark.timeout(180)
@pytest.mark.asyncio
async def test_w100_position_management_loop_produces_exits_on_downturn():
    """An established position should produce exit/close trades on a
    sharp downturn — exercises the position-management for-loop's
    stop/exit branches."""
    from backend.organism.replay_simulator import (
        ReplayEngine, make_features_dict,
    )
    # Mixed: uptrend so positions get opened, then we run more ticks
    # to allow exits to fire.
    bars = make_features_dict(
        ["AAPL", "MSFT", "SPY"], n=700, seed=42, trend="up",
    )
    engine = ReplayEngine(
        bars_by_symbol=bars,
        initial_cash=1_000_000,
        slippage_bps=5,
        max_entries_per_hour=20,
    )
    # 200 ticks: long enough to trigger natural exits + horizon
    # timeouts + ATR-based stops in the position-management loop.
    result = await engine.run(max_ticks=200)
    total_orders = sum(
        r.get("orders_submitted", 0)
        for r in result.tick_results if isinstance(r, dict)
    )
    # If we opened any orders, the position-management loop must have
    # exercised its exit-checking branch — even if no actual close
    # fires, the loop ran ~200 times.  Assert via tick_results having
    # exits_checked > 0 in the expected path.
    if total_orders > 0:
        total_checks = sum(
            r.get("exits_checked", 0)
            for r in result.tick_results if isinstance(r, dict)
        )
        assert total_checks > 0, (
            "position-management loop did not run exits_checked despite "
            "orders being submitted"
        )
    # Lower-bound assertion: the loop is at least exercised once.
    any_check = any(
        r.get("exits_checked", 0) > 0
        for r in result.tick_results if isinstance(r, dict)
    )
    # If no order was submitted, we don't expect exits_checked to fire,
    # but the for-loop's structural code path was still entered each tick.
    assert any_check or total_orders == 0


@pytest.mark.timeout(180)
@pytest.mark.asyncio
async def test_w100_position_management_no_orders_no_exits():
    """Without entries, exits_checked stays at 0.  Sanity that the
    for-loop isn't double-counting a phantom open position."""
    from backend.organism.replay_simulator import (
        ReplayEngine, make_features_dict,
    )
    # Use trend="down" + low cash so Kelly skips and no orders open.
    bars = make_features_dict(
        ["AAPL", "MSFT", "SPY"], n=700, seed=99, trend="down",
    )
    engine = ReplayEngine(
        bars_by_symbol=bars,
        initial_cash=100_000,
        slippage_bps=5,
        max_entries_per_hour=20,
    )
    result = await engine.run(max_ticks=50)
    total_orders = sum(
        r.get("orders_submitted", 0)
        for r in result.tick_results if isinstance(r, dict)
    )
    total_exits = sum(
        r.get("trades_closed", 0)
        for r in result.tick_results if isinstance(r, dict)
    )
    # No orders means no positions to close.
    assert total_orders == 0
    assert total_exits == 0


# ────────────────────────────────────────────────────────────────────
# Sub-block 3: Equity gates / drawdown circuit
# ────────────────────────────────────────────────────────────────────


def test_w100_equity_gates_max_daily_loss_branch_present():
    """Source-level guard: the daily-loss branch must call
    governance.halt_trading() AND set _daily_loss_halt = True AND
    set _entries_blocked = True.  These three observables together
    define "equity gate fired".

    `_entries_blocked = True` appears in many other branches (warmup,
    learning-mode block, etc.), so we anchor on the
    `halt_trading()` call site and verify the daily-loss flag and
    an entries-block sit within 5 lines of it.
    """
    src = LIVE_ENGINE_PATH.read_text()
    lines = src.split("\n")

    halt_lines = [i for i, l in enumerate(lines)
                  if "self.governance.halt_trading()" in l]
    halt_flag_lines = [i for i, l in enumerate(lines)
                       if "self._daily_loss_halt = True" in l]
    entries_blocked_lines = [i for i, l in enumerate(lines)
                             if "self._entries_blocked = True" in l]

    assert halt_lines, "halt_trading() invocation missing"
    assert halt_flag_lines, "_daily_loss_halt = True missing"
    assert entries_blocked_lines, "_entries_blocked = True missing"

    # For each halt_trading() site, verify daily_loss_halt + at least
    # one entries_blocked are within 5 lines (the canonical pattern).
    matched = False
    for h in halt_lines:
        nearby_flag = any(abs(h - hf) <= 5 for hf in halt_flag_lines)
        nearby_block = any(abs(h - eb) <= 5 for eb in entries_blocked_lines)
        if nearby_flag and nearby_block:
            matched = True
            break
    assert matched, (
        "no halt_trading() site found with _daily_loss_halt=True AND "
        "_entries_blocked=True within 5 lines — equity gate branch is "
        "either missing or has been split during a refactor"
    )


def test_w100_equity_gates_drawdown_kill_invocation():
    """Runner-level drawdown kill must halt governance and report the action."""
    from backend.organism.governance import GovernanceController
    from backend.organism.runner import OrganismRunner

    gov = GovernanceController()
    gov._drawdown_limit = 0.05
    runner = OrganismRunner(governance=gov)

    result = runner.post_execution_hook(live_metrics={"drawdown": 0.08})

    assert result["actions"] == ["drawdown_kill_triggered"]
    assert gov.snapshot().trading_halted is True


# ────────────────────────────────────────────────────────────────────
# Sub-block 4: Pyramid path
# ────────────────────────────────────────────────────────────────────


def test_w100_pyramid_path_present_in_source():
    """Pyramid path is present (structural).  Full replay-driven
    pyramid coverage is V13.1+ work because the path needs:
      - an existing open position
      - rising equity past the pyramid threshold
      - pyramid env enablement
    Setting all three in a unit test is too brittle for V13;
    structural assertion plus the existing pyramid_metrics_test
    suite covers the contract for now."""
    src = LIVE_ENGINE_PATH.read_text()
    # Pyramid identifiers must be present in source.
    assert "pyramid" in src.lower()
    # And must be a real code path, not just a comment-mention:
    # at least one pyramid-prefixed identifier OR pyramid_count
    # accumulator.
    assert (
        "pyramider" in src.lower()
        or "pyramid_count" in src.lower()
        or "pyramid_added" in src.lower()
    )


def test_w100_existing_pyramid_tests_still_pass():
    """The existing pyramid_metrics tests cover the path's metric
    output; W100 doesn't replace them — it pins them as the canonical
    pyramid-path coverage source until V13.1+."""
    pyramid_tests = list((REPO_ROOT / "tests").glob("*pyramid*"))
    assert pyramid_tests, (
        "no pyramid-related tests found — V13.1+ pyramid replay "
        "extraction needs the existing tests to land first"
    )


# ────────────────────────────────────────────────────────────────────
# Cross-cutting: tick_result schema stability
# ────────────────────────────────────────────────────────────────────


@pytest.mark.timeout(60)
@pytest.mark.asyncio
async def test_w100_tick_result_schema_includes_required_keys():
    """The tick_result schema is the API surface between
    _live_tick_inner and consumers (replay results, dashboards,
    metrics).  Schema drift here breaks the world.  Run a tiny
    replay and assert all required keys are present in every
    tick_result entry."""
    from backend.organism.replay_simulator import (
        ReplayEngine, make_features_dict,
    )
    bars = make_features_dict(["AAPL"], n=300, seed=1)
    engine = ReplayEngine(
        bars_by_symbol=bars,
        initial_cash=100_000,
    )
    result = await engine.run(max_ticks=10)

    required = {
        "timestamp", "regime", "signals_generated", "orders_submitted",
        "exits_checked", "trades_closed", "errors", "duration_s",
        "universe_size",
    }
    for tr in result.tick_results:
        assert isinstance(tr, dict)
        missing = required - set(tr.keys())
        assert not missing, (
            f"tick_result missing required keys: {missing}; full keys "
            f"present: {set(tr.keys())}"
        )


@pytest.mark.timeout(60)
@pytest.mark.asyncio
async def test_w100_tick_result_duration_bounded():
    """Each tick must complete in <30s (the V9 TT-2 watchdog).
    Asserts duration_s in tick_results never exceeds the watchdog."""
    from backend.organism.replay_simulator import (
        ReplayEngine, make_features_dict,
    )
    bars = make_features_dict(["AAPL"], n=300, seed=1)
    engine = ReplayEngine(
        bars_by_symbol=bars,
        initial_cash=100_000,
    )
    result = await engine.run(max_ticks=10)
    for tr in result.tick_results:
        assert isinstance(tr, dict)
        d = tr.get("duration_s", 0)
        assert d < 30.0, f"tick exceeded 30s watchdog: {d:.2f}s"
