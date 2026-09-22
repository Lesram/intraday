"""Operator endpoints control the live engine without disabling risk exits."""
from __future__ import annotations

import asyncio
import json
import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from backend.infra.security import require_admin
from backend.organism import operator_controls, research_policy
from backend.organism.governance import GovernanceController
from backend.organism.live_engine import LiveTickResult, OrganismLiveEngine
from backend.organism.routes import router


@pytest.fixture
def control_file(tmp_path, monkeypatch):
    path = tmp_path / "controls" / "operator.json"
    monkeypatch.setenv(operator_controls.STATE_ENV, str(path))
    operator_controls.initialize_control_state(path, operator_halted=False, reason="verified_test_baseline")
    return path


def make_app(engine=None):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: {"role": "admin"}
    if engine is None:
        engine = SimpleNamespace(governance=GovernanceController(), _tick_lock=asyncio.Lock(), _tick_count=0, _initialized=True)
    app.state.organism_governance = GovernanceController()
    app.state.organism_runner = SimpleNamespace(governance=GovernanceController(), _last_regime="unknown", _tick_count=0)
    app.state.organism_scheduler = SimpleNamespace(
        _engine=engine, is_running=True, _stop=asyncio.Event(), state=lambda: {"engine": {"governance": engine.governance.to_dict()}},
    )
    return app, engine


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def initialize_offline(engine):
    from backend.organism.diagnostics import DiagnosticReport
    engine._reconstruct_position_state = AsyncMock()
    with patch("backend.organism.diagnostics.diagnostics.run", new=AsyncMock(
            return_value=DiagnosticReport(mode="test", timestamp=engine._now_fn().isoformat()))):
        await engine.initialize()
    assert engine._initialized is True


async def await_latch(engine):
    async with asyncio.timeout(2):
        while not engine.governance._operator_halted:
            await asyncio.sleep(0)


def actual_engine(tmp_path):
    orders = SimpleNamespace(submit_symbol_order=AsyncMock(return_value={"order_id": "test-order"}))
    positions = SimpleNamespace(get_all_positions=AsyncMock(return_value={
        "AAPL": {"qty": 10, "side": "long", "avg_entry_price": 100},
    }))
    engine = OrganismLiveEngine(data_client=MagicMock(), order_service=orders,
                                positions_service=positions, brain_dir=str(tmp_path / "brain"),
                                universe=["AAPL", "MSFT", "SPY"])
    engine.market_scanner = None
    engine._streaming_provider = None
    return engine


async def test_admin_halt_reaches_distinct_live_engine_governance(control_file):
    app, engine = make_app()
    assert engine.governance is not app.state.organism_governance
    async with client_for(app) as client:
        response = await client.post("/organism/halt")
        assert response.status_code == 200
        assert response.json()["drained"] is True
        assert response.json()["orders_cancelled"] is False
        assert all(gov.is_trading_halted for gov in operator_controls.governance_targets(app))
        assert operator_controls.read_record(control_file)["operator_halted"] is True
        status = (await client.get("/organism/status")).json()
        assert status["governance"]["halted"] is True
        assert status["live_engine"]["engine"]["governance"]["halted"] is True
        assert status["governance"]["operator_control"]["path"] == str(control_file)


async def test_live_engine_is_authoritative_even_without_legacy_governance(control_file):
    app, engine = make_app()
    del app.state.organism_governance
    engine.governance.halt_trading()
    async with client_for(app) as client:
        status = (await client.get("/organism/status")).json()
        assert status["enabled"] is True
        assert status["governance"]["automatic_halted"] is True
        assert (await client.get("/organism/runs")).json()["enabled"] is True
        assert (await client.post("/organism/halt")).status_code == 200


@pytest.mark.parametrize("protection", ["daily_loss", "drawdown", "environment", "none"])
async def test_resume_clears_only_operator_halt(control_file, protection):
    app, engine = make_app()
    async with client_for(app) as client:
        assert (await client.post("/organism/halt")).status_code == 200
        if protection == "daily_loss":
            engine._daily_loss_halt = True
            engine.governance.halt_trading()
        elif protection == "drawdown":
            engine.governance.trigger_drawdown_kill(.10)
        elif protection == "environment":
            engine.governance._environment_halted = True
        response = await client.post("/organism/resume")
        assert response.status_code == 200
        assert response.json()["status"] == ("resumed" if protection == "none" else "still_halted")
        assert not engine.governance._operator_halted
        assert engine.governance.is_trading_halted is (protection != "none")
        assert all(not gov._operator_halted for gov in operator_controls.governance_targets(app))
        assert operator_controls.read_record(control_file)["operator_halted"] is False
        assert research_policy.RESEARCH_POLICY_LOCKED is True


async def test_daily_recovery_and_legacy_restore_cannot_clear_operator_halt(control_file):
    app, engine = make_app()
    await operator_controls.halt_entries(app)
    engine.governance.halt_trading()
    engine.governance.resume_trading()  # exact call used by frozen date-roll code
    engine.governance.from_persistence_dict({"trading_halted": False, "operator_halted": False})
    assert engine.governance.is_trading_halted
    assert engine.governance._operator_halted


async def test_unfreeze_keeps_research_lock_and_halt(control_file, tmp_path):
    engine = actual_engine(tmp_path)
    await initialize_offline(engine)
    app, _ = make_app(engine)
    await operator_controls.halt_entries(app)
    async with client_for(app) as client:
        assert (await client.post("/organism/freeze")).status_code == 200
        assert all(g.is_frozen for g in operator_controls.governance_targets(app))
        response = await client.post("/organism/unfreeze")
        assert response.status_code == 200 and response.json()["research_policy_locked"] is True
        assert all(not g.is_frozen for g in operator_controls.governance_targets(app))
        assert engine.governance.is_trading_halted
        await client.post("/organism/resume")
        assert engine._ml_isolation_mode and engine._fixed_risk_sizing_mode
        assert engine._trading_phase["policy_lock"]["locked"] is True


@pytest.mark.parametrize("reason", ["organism_entry", "pyramid_add"])
async def test_halt_before_submission_after_tick_await_blocks_entries_but_allows_exit(control_file, tmp_path, reason):
    engine = actual_engine(tmp_path)
    await initialize_offline(engine)
    app, _ = make_app(engine)
    reached = asyncio.Event()
    release = asyncio.Event()
    async def tick_body():
        reached.set()
        await release.wait()
        with pytest.raises(RuntimeError, match="Governance halted"):
            await engine._submit_entry_order("AAPL", 1, reason=reason)
        await engine._submit_exit_order("AAPL", 1, reason="stop_loss")
        return LiveTickResult(timestamp=engine._now_fn().isoformat())
    engine._live_tick_inner = tick_body
    tick = asyncio.create_task(engine.live_tick())
    await reached.wait()
    async with client_for(app) as client:
        halt = asyncio.create_task(client.post("/organism/halt"))
        await await_latch(engine)
        assert engine.governance._operator_halted
        assert operator_controls.read_record(control_file)["operator_halted"] is True
        assert not halt.done()
        release.set()
        await tick
        assert (await halt).status_code == 200
    calls = engine._order_service.submit_symbol_order.call_args_list
    assert len(calls) == 1 and calls[0].kwargs["reduce_only"] is True


@pytest.mark.parametrize("reason", ["organism_entry", "pyramid_add"])
async def test_halt_acknowledgement_drains_already_admitted_order(control_file, tmp_path, reason):
    engine = actual_engine(tmp_path)
    await initialize_offline(engine)
    app, _ = make_app(engine)
    admitted = asyncio.Event()
    release = asyncio.Event()
    async def submit(**kwargs):
        if not kwargs.get("reduce_only"):
            admitted.set()
            await release.wait()
        return {"order_id": "already-admitted"}
    engine._order_service.submit_symbol_order.side_effect = submit
    async def tick_body():
        # Capture the real frame at the current tick before direct admission.
        import pandas as pd
        from backend.organism.entry_evidence import _frame_receipt
        engine._timeframe = "1Min"
        engine._entry_evidence_tick = engine._tick_count
        engine._entry_evidence_frames = {("AAPL", 1.): _frame_receipt(
            engine, "AAPL", 1., pd.DataFrame({"timestamp": [engine._now_fn()], "close": [100.]}))}
        await engine._submit_entry_order("AAPL", 1, reason=reason)
        # Even a later same-symbol add inside the already-entered tick is denied.
        with pytest.raises(RuntimeError, match="Governance halted"):
            await engine._submit_entry_order("AAPL", 1, reason="pyramid_add")
        await engine._submit_exit_order("AAPL", 1, reason="stop_loss")
        return LiveTickResult(timestamp=engine._now_fn().isoformat())
    engine._live_tick_inner = tick_body
    tick = asyncio.create_task(engine.live_tick())
    await admitted.wait()
    async with client_for(app) as client:
        halt = asyncio.create_task(client.post("/organism/halt"))
        await await_latch(engine)
        assert not halt.done() and engine.governance._operator_halted
        release.set()
        await tick
        assert (await halt).json()["drained"] is True
    calls = engine._order_service.submit_symbol_order.call_args_list
    assert len(calls) == 2
    assert sum(bool(c.kwargs.get("reduce_only")) for c in calls) == 1


async def test_drain_timeout_is_unsuccessful_and_never_cancels_tick(control_file, monkeypatch):
    app, engine = make_app()
    monkeypatch.setattr(operator_controls, "DRAIN_TIMEOUT_SECONDS", .01)
    await engine._tick_lock.acquire()
    try:
        async with client_for(app) as client:
            response = await client.post("/organism/halt")
        assert response.status_code == 503
        assert response.json()["detail"]["drained"] is False
        assert engine._tick_lock.locked()
        assert engine.governance.is_trading_halted
        assert operator_controls.read_record(control_file)["operator_halted"] is True
    finally:
        engine._tick_lock.release()


@pytest.mark.parametrize("action", ["halt", "resume"])
async def test_persistence_error_cannot_report_success_or_clear_latch(control_file, monkeypatch, action):
    app, engine = make_app()
    await operator_controls.halt_entries(app)
    original = control_file.read_bytes()
    monkeypatch.setattr(operator_controls.os, "replace", MagicMock(side_effect=OSError("disk unavailable")))
    async with client_for(app) as client:
        response = await client.post("/organism/" + action)
    assert response.status_code == 503
    assert engine.governance.is_trading_halted
    assert engine.governance._operator_control_fault
    assert control_file.read_bytes() == original


async def test_resume_interrupted_by_new_halt_cannot_clear_it(control_file):
    app, engine = make_app()
    await operator_controls.halt_entries(app)
    await engine._tick_lock.acquire()
    resume = asyncio.create_task(operator_controls.resume_entries(app))
    await asyncio.sleep(0)
    halt = asyncio.create_task(operator_controls.halt_entries(app))
    await asyncio.sleep(0)
    engine._tick_lock.release()
    with pytest.raises(operator_controls.OperatorControlError):
        await resume
    assert (await halt)["drained"] is True
    assert engine.governance._operator_halted
    assert operator_controls.read_record(control_file)["operator_halted"] is True


@pytest.mark.parametrize("invalid", ["missing", "corrupt", "wrong_type", "bad_checksum", "relative", "inside_brain"])
def test_invalid_control_authority_fails_closed(control_file, tmp_path, monkeypatch, invalid):
    engine = actual_engine(tmp_path)
    if invalid == "missing":
        control_file.unlink()
    elif invalid == "corrupt":
        control_file.write_text("{")
    elif invalid in {"wrong_type", "bad_checksum"}:
        record = json.loads(control_file.read_text())
        record["operator_halted" if invalid == "wrong_type" else "checksum"] = "invalid"
        control_file.write_text(json.dumps(record))
    elif invalid == "relative":
        monkeypatch.setenv(operator_controls.STATE_ENV, "relative.json")
    else:
        monkeypatch.setenv(operator_controls.STATE_ENV, str(engine.brain.brain_dir / "operator.json"))
    operator_controls.restore_engine_controls(engine)
    assert engine.governance.is_trading_halted
    assert engine.governance._operator_control_fault
    engine.governance.from_persistence_dict({"trading_halted": False})
    assert engine.governance.is_trading_halted


def test_operator_record_survives_legacy_directory_replacement(control_file, tmp_path):
    engine = actual_engine(tmp_path)
    operator_controls.write_record(control_file, operator_halted=True, reason="operator_halt")
    saved = control_file.read_bytes()
    engine.brain.brain_dir.mkdir(parents=True, exist_ok=True)
    (engine.brain.brain_dir / "governance_state.json").write_text('{"trading_halted":false}')
    shutil.rmtree(engine.brain.brain_dir)
    engine.brain.brain_dir.mkdir()
    restarted = actual_engine(tmp_path)
    operator_controls.restore_engine_controls(restarted)
    restarted.governance.from_persistence_dict({"trading_halted": False})
    assert restarted.governance.is_trading_halted
    assert control_file.read_bytes() == saved


async def test_actual_initialize_loads_operator_authority_before_legacy_recovery(control_file, tmp_path, monkeypatch):
    engine = actual_engine(tmp_path)
    operator_controls.write_record(control_file, operator_halted=True, reason="operator_halt")
    engine.brain.brain_dir.mkdir(parents=True, exist_ok=True)
    # Cause initialize to enter legacy load, then simulate a failed/old recovery.
    monkeypatch.setattr(type(engine.brain), "exists", property(lambda self: True))
    def legacy_load():
        assert engine.governance._operator_halted
        engine.governance.from_persistence_dict({"trading_halted": False})
        return False
    monkeypatch.setattr(engine.brain, "load", legacy_load)
    engine._reconstruct_position_state = AsyncMock()
    engine._bg_trainer.start = AsyncMock()
    engine._data_client = MagicMock()
    assert await engine.initialize() is False
    assert engine._initialized and engine.governance.is_trading_halted
    engine._reconstruct_position_state.assert_awaited_once()


async def test_status_disabled_and_controls_unavailable_without_governance():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: {"role": "admin"}
    async with client_for(app) as client:
        assert (await client.get("/organism/status")).json()["enabled"] is False
        assert (await client.post("/organism/halt")).status_code == 503


async def test_non_admin_cannot_mutate_governance(control_file):
    app, engine = make_app()
    def denied():
        raise HTTPException(status_code=403, detail="admin required")
    app.dependency_overrides[require_admin] = denied
    before = control_file.read_bytes()
    async with client_for(app) as client:
        for action in ("halt", "resume", "freeze", "unfreeze"):
            assert (await client.post("/organism/" + action)).status_code == 403
    assert not engine.governance.is_trading_halted
    assert control_file.read_bytes() == before


def test_rollout_seed_never_overwrites_existing_state(control_file):
    before = control_file.read_bytes()
    with pytest.raises(FileExistsError):
        operator_controls.initialize_control_state(control_file, operator_halted=True, reason="no_overwrite")
    assert control_file.read_bytes() == before


@pytest.mark.parametrize("exit_case", ["stop_loss_with_date_roll", "eod_flatten"])
async def test_full_live_tick_keeps_protective_exit_and_date_roll_cannot_resume(control_file, tmp_path, exit_case):
    from datetime import UTC, datetime
    from backend.organism.adaptive_exits import ExitLevels
    from backend.organism.replay_simulator import SimulatedBroker, make_price_df
    from tests.test_organism_engine_scenarios import MockDataClient, _make_engine

    frame = make_price_df(n=600, base=80)
    for col in ("open", "close", "high", "low"):
        frame[col] = {"open": 80, "close": 80, "high": 81, "low": 79}[col]
    broker = SimulatedBroker(initial_cash=100_000)
    engine = _make_engine(broker, MockDataClient({s: frame.copy() for s in ("AAPL", "MSFT", "SPY")}),
                          brain_dir=str(tmp_path / "actual-brain"))
    now = datetime(2026, 9, 21, 19 if exit_case == "eod_flatten" else 15,
                   56 if exit_case == "eod_flatten" else 0, tzinfo=UTC)
    engine._now_fn = lambda: now
    engine._time_fn = now.timestamp
    await engine.initialize()
    broker.add_position("AAPL", qty=10, avg_entry_price=100)
    broker.set_price("AAPL", 80)
    engine._exit_levels["AAPL"] = ExitLevels(
        symbol="AAPL", direction=1., entry_price=100, stop_loss=90, take_profit=120,
        trailing_stop=90, atr_at_entry=2, regime_at_entry="unknown", highest_favorable=100,
    )
    engine._entry_metadata["AAPL"] = {
        "entry_price": 100., "entry_tick": 0, "direction": 1., "confidence": .6,
        "predicted_return": .02, "filled_shares": 10, "entry_source": "alpha",
    }
    engine._daily_loss_halt = True
    engine._daily_loss_date = "2026-09-18"
    engine.governance.halt_trading()
    app, _ = make_app(engine)
    async with client_for(app) as client:
        assert (await client.post("/organism/halt")).status_code == 200
    result = await engine.live_tick()
    assert engine.governance._operator_halted and engine.governance.is_trading_halted
    assert engine._daily_loss_halt is False
    assert result.orders_submitted >= 1
    assert "AAPL" not in await broker.get_all_positions()
    assert broker.trade_log and all(t["side"] == "sell" for t in broker.trade_log)
    assert engine._ml_isolation_mode and engine._fixed_risk_sizing_mode


def test_new_legacy_controller_restores_persisted_operator_halt(control_file):
    operator_controls.write_record(control_file, operator_halted=True, reason="operator_halt")
    legacy = GovernanceController()
    assert legacy._operator_halted and legacy.is_trading_halted
    assert legacy._operator_control_state["persistence"] == "verified"
    legacy.halt_trading()
    legacy.resume_trading()
    legacy.from_persistence_dict({"trading_halted": False})
    assert legacy.is_trading_halted


def test_new_legacy_controller_fails_closed_on_missing_configured_authority(control_file):
    control_file.unlink()
    legacy = GovernanceController()
    assert legacy._operator_halted and legacy._operator_control_fault
    legacy.resume_trading()
    assert legacy.is_trading_halted


@pytest.mark.parametrize("lifecycle", ["legacy_only", "engine_missing", "uninitialized", "stopped", "stopping"])
@pytest.mark.parametrize("action", ["halt", "resume"])
async def test_unavailable_live_protection_is_degraded_never_acknowledged(control_file, lifecycle, action):
    app, engine = make_app()
    if lifecycle == "legacy_only":
        del app.state.organism_scheduler
    elif lifecycle == "engine_missing":
        app.state.organism_scheduler._engine = None
    elif lifecycle == "uninitialized":
        engine._initialized = False
    elif lifecycle == "stopped":
        app.state.organism_scheduler.is_running = False
    else:
        app.state.organism_scheduler._stop.set()
    async with client_for(app) as client:
        response = await client.post("/organism/" + action)
    assert response.status_code == 503
    result = response.json()["detail"]
    assert result["operator_halted"] is True
    assert result["drained"] is False
    assert result["runtime_ready"] is False
    assert result["protective_exits_active"] is False
    assert all(gov._operator_halted for gov in operator_controls.governance_targets(app))
    assert operator_controls.read_record(control_file)["operator_halted"] is True


async def test_scheduler_stops_while_halt_waits_for_tick_returns_degraded(control_file):
    app, engine = make_app()
    await engine._tick_lock.acquire()
    halt = asyncio.create_task(operator_controls.halt_entries(app))
    await await_latch(engine)
    app.state.organism_scheduler.is_running = False
    engine._tick_lock.release()
    with pytest.raises(operator_controls.OperatorControlError) as exc:
        await halt
    assert exc.value.result["protective_exits_active"] is False
    assert exc.value.result["drained"] is False
    assert engine.governance.is_trading_halted
