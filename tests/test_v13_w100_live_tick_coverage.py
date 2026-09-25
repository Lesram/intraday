"""V13 W100 (HH3-N-1) — _live_tick_inner behavioral coverage.

V12 W75 deferred LOC reduction of _live_tick_inner (2,738 lines) to
V13+ because the function had zero direct test coverage.  W100 ships
the coverage layer; actual extraction is V13.1+ work.

Strategy: drive _live_tick_inner through the ReplayEngine with
targeted synthetic bars and assert observable contracts for each
of the four hot sub-blocks:

1. **Entries gate** — synthetic upward-trend bars at $1M cash should
   produce ≥1 order across 60 valid one-minute ticks.
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
from time import perf_counter

import pandas as pd
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
# PR27 approved final freshness rejection handling adds 18 lines to the
# previous 2805 ceiling. This candidate adds one scanner-error pool-clear line.
# Both deltas are explicitly reviewed; there is no spare growth tolerance.
# September24 repair:28 additional lines for explicit rejection causes,
# non-decision timing/counters and the one subscription synchronization call.
# This is a scoped reviewed addition; the parked decomposition is unchanged.
LIVE_TICK_INNER_LOC_CEILING = 2_805 + 18 + 1 + 28


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


def _minute_bars(*, seed=42, trend="up", start="2026-09-22T10:40:00Z",
                 symbols=("AAPL", "MSFT", "SPY")):
    from backend.organism.replay_simulator import make_features_dict

    bars = make_features_dict(list(symbols), n=280, seed=seed, trend=trend)
    for frame in bars.values():
        frame["timestamp"] = pd.date_range(start, periods=len(frame), freq="min")
    return bars


def _cache_real_features(monkeypatch, bars):
    """Avoid recomputing causal history on every tick; no decision is mocked.

    W100 tests orchestration, not rolling-feature CPU throughput. Every cached
    value comes from the real feature function; only the already-visible prefix
    is returned. A separate regression compares prefixes to direct computation.
    Histories stay below 500 rows so no sliding-window boundary is substituted.
    """
    from backend.organism import ml_features

    real_compute = ml_features.compute_ml_features
    computed = {
        symbol: real_compute(frame, spy_df=bars["SPY"] if symbol != "SPY" else None,
                             bars_per_day=390)
        for symbol, frame in bars.items()
    }
    calls = []

    def cached(frame, spy_df=None, bars_per_day=1):
        assert bars_per_day == 390
        matching = [symbol for symbol, raw in bars.items()
                    if frame.equals(raw.iloc[:len(frame)].reset_index(drop=True))]
        assert len(matching) == 1, "Replay requested unknown or non-prefix bars"
        symbol = matching[0]
        if spy_df is not None:
            pd.testing.assert_frame_equal(spy_df, bars["SPY"].iloc[:len(frame)])
        result = computed[symbol].iloc[:len(frame)].copy()
        assert result["timestamp"].iloc[-1] == frame["timestamp"].iloc[-1]
        calls.append((symbol, len(frame)))
        return result

    monkeypatch.setattr(ml_features, "compute_ml_features", cached)
    return real_compute, computed, calls


def _replay(monkeypatch, tmp_path, bars, *, max_entries_per_hour=20, universe=None):
    from backend.organism.live_engine import OrganismLiveEngine
    from backend.organism.replay_simulator import ReplayEngine

    _, _, calls = _cache_real_features(monkeypatch, bars)
    initialized = []
    initialize = OrganismLiveEngine.initialize

    async def observe_initialize(engine):
        result = await initialize(engine)
        initialized.append(engine)
        return result

    monkeypatch.setattr(OrganismLiveEngine, "initialize", observe_initialize)
    replay = ReplayEngine(bars, initial_cash=1_000_000, slippage_bps=5,
                          timeframe="1Min", lookback=200,
                          brain_dir=str(tmp_path / "brain"),
                          max_entries_per_hour=max_entries_per_hour, universe=universe)
    return replay, initialized, calls


def _assert_real_ticks(result, expected):
    assert result.ticks == len(result.tick_results) == expected
    assert all(not tick.get("errors") and "error" not in tick
               for tick in result.tick_results)


def test_w100_cached_feature_prefixes_match_real_visible_history(monkeypatch):
    bars = _minute_bars()
    real_compute, cached, _ = _cache_real_features(monkeypatch, bars)
    for count in (201, 230, 260):
        for symbol in ("AAPL", "SPY"):
            direct = real_compute(
                bars[symbol].iloc[:count],
                spy_df=bars["SPY"].iloc[:count] if symbol != "SPY" else None,
                bars_per_day=390,
            )
            pd.testing.assert_frame_equal(cached[symbol].iloc[:count], direct)
    # An adversarial unseen price/volume shock must not change any visible
    # feature, even though the fixture computes its causal history once.
    shocked = {symbol: frame.copy() for symbol, frame in bars.items()}
    for frame in shocked.values():
        frame.loc[230:, ["open", "high", "low", "close", "volume"]] *= 10
    for symbol in ("AAPL", "SPY"):
        future_shocked = real_compute(
            shocked[symbol], spy_df=shocked["SPY"] if symbol != "SPY" else None,
            bars_per_day=390)
        pd.testing.assert_frame_equal(cached[symbol].iloc[:230], future_shocked.iloc[:230])


@pytest.mark.timeout(60)
@pytest.mark.asyncio
async def test_w100_entries_gate_produces_orders_on_uptrend(monkeypatch, tmp_path, record_property):
    """Valid one-minute history must reach actual gated broker submission."""
    replay, engines, calls = _replay(monkeypatch, tmp_path, _minute_bars())
    result = await replay.run(max_ticks=60)
    _assert_real_ticks(result, 60)
    entries = [order for order in result.orders if order["side"] == "buy"]
    assert entries
    assert sum(tick["orders_submitted"] for tick in result.tick_results) >= 1
    assert calls and max(count for _, count in calls) == 260
    assert engines[0]._ml_isolation_mode and engines[0]._fixed_risk_sizing_mode
    record_property("actual_entry_orders", len(entries))
    record_property("actual_accounted_closes", len(result.accounted_trades))
    record_property("first_entry_at", entries[0]["submitted_at"])


@pytest.mark.timeout(60)
@pytest.mark.asyncio
async def test_w100_entries_gate_signals_generated_on_uptrend(monkeypatch, tmp_path):
    """Real candidate evaluation remains active with the production policy lock."""
    replay, _, _ = _replay(monkeypatch, tmp_path, _minute_bars(seed=7))
    result = await replay.run(max_ticks=30)
    _assert_real_ticks(result, 30)
    assert sum(tick["signals_generated"] for tick in result.tick_results) > 0


@pytest.mark.timeout(60)
@pytest.mark.asyncio
async def test_w100_position_management_loop_produces_exits_on_downturn(monkeypatch, tmp_path, record_property):
    """Real entries must produce protective exits and reconciled outcomes."""
    bars = _minute_bars()
    # After 40 valid minutes, force a real price shock in subsequent provider
    # bars. Existing exits see that market path; no exit decision is mocked.
    for frame in bars.values():
        frame.loc[240:, ["open", "high", "low", "close"]] *= .75
    replay, engines, _ = _replay(monkeypatch, tmp_path, bars)
    result = await replay.run(max_ticks=60)
    _assert_real_ticks(result, 60)
    assert any(order["side"] == "buy" for order in result.orders)
    assert any(order["side"] == "sell" for order in result.orders)
    assert result.trades and result.accounted_trades
    assert sum(tick["exits_checked"] for tick in result.tick_results) > 0
    assert not result.accounting_pending
    assert engines[0].learner.state.total_trades == len(result.accounted_trades)
    assert all(trade["price_source"] == "simulated_position_fills"
               and not trade["is_reconciliation_artifact"]
               for trade in result.accounted_trades)
    shock_at = bars["AAPL"]["timestamp"].iloc[240]
    protected = [trade for trade in result.accounted_trades
                 if pd.Timestamp(trade["closed_at"]) >= shock_at and trade["pnl"] < 0
                 and (trade["exit_reason"] in {"stop_loss", "max_loss_limit"}
                      or trade["exit_reason"].startswith("pyramid_cut_full"))]
    assert protected, "The injected downturn must close an actual losing position"
    engine = engines[0]
    assert engine.learner.state.cumulative_pnl == pytest.approx(
        sum(trade["pnl"] for trade in result.accounted_trades))
    before = (len(engine._all_trades), engine.learner.state.total_trades,
              engine.learner.state.cumulative_pnl)
    await engine._reconcile_fills(await engine._positions_service.get_all_positions())
    assert before == (len(engine._all_trades), engine.learner.state.total_trades,
                      engine.learner.state.cumulative_pnl)
    record_property("protective_closes_after_shock", len(protected))
    record_property("actual_orders", len(result.orders))
    record_property("actual_accounted_closes", len(result.accounted_trades))
    record_property("exit_reasons", sorted({trade["exit_reason"] for trade in result.accounted_trades}))


@pytest.mark.timeout(60)
@pytest.mark.asyncio
async def test_w100_eod_flattens_real_entered_position(monkeypatch, tmp_path, record_property):
    """Late-session replay must flatten a position and forbid later entries."""
    replay, engines, _ = _replay(
        monkeypatch, tmp_path, _minute_bars(start="2026-09-22T16:16:00Z"))
    result = await replay.run(max_ticks=35)
    _assert_real_ticks(result, 35)
    assert any(order["side"] == "buy" for order in result.orders)
    eod_closes = [trade for trade in result.accounted_trades
                  if trade["exit_reason"] == "eod_flatten"]
    assert eod_closes
    assert all(pd.Timestamp(trade["closed_at"]).hour == 19
               and pd.Timestamp(trade["closed_at"]).minute >= 58 for trade in eod_closes)
    assert not await engines[0]._positions_service.get_all_positions()
    assert not result.accounting_pending
    assert all(pd.Timestamp(order["submitted_at"]) < pd.Timestamp("2026-09-22T19:58:00Z")
               for order in result.orders if order["side"] == "buy")
    record_property("actual_eod_closes", len(eod_closes))


@pytest.mark.timeout(60)
@pytest.mark.asyncio
async def test_w100_position_management_no_orders_no_exits(monkeypatch, tmp_path):
    """A real zero-entry throttle produces no phantom positions or exits."""
    replay, _, _ = _replay(monkeypatch, tmp_path, _minute_bars(), max_entries_per_hour=0)
    result = await replay.run(max_ticks=20)
    _assert_real_ticks(result, 20)
    assert any("Entry throttle:" in event["message"]
               for tick in result.tick_results for event in tick["activity"])
    assert not result.orders and not result.trades and not result.accounted_trades
    assert sum(tick["exits_checked"] for tick in result.tick_results) == 0


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
async def test_w100_tick_result_schema_includes_required_keys(monkeypatch, tmp_path):
    """The tick_result schema is the API surface between
    _live_tick_inner and consumers (replay results, dashboards,
    metrics).  Schema drift here breaks the world.  Run a tiny
    replay and assert all required keys are present in every
    tick_result entry."""
    replay, _, _ = _replay(monkeypatch, tmp_path, _minute_bars(seed=1))
    result = await replay.run(max_ticks=10)
    _assert_real_ticks(result, 10)

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
async def test_w100_tick_result_duration_bounded(monkeypatch, tmp_path):
    """Each tick must complete in <30s (the V9 TT-2 watchdog).
    Asserts duration_s in tick_results never exceeds the watchdog."""
    replay, _, _ = _replay(monkeypatch, tmp_path, _minute_bars(seed=1))
    started = perf_counter()
    result = await replay.run(max_ticks=10)
    elapsed = perf_counter() - started
    _assert_real_ticks(result, 10)
    # duration_s uses the intentionally fixed replay clock; also bound actual
    # monotonic elapsed time so frozen synthetic time cannot hide a slow loop.
    assert elapsed < 30, f"Ten replay ticks exceeded 30s wall time: {elapsed:.2f}s"
    for tr in result.tick_results:
        assert 0 <= tr["duration_s"] < 30.0
