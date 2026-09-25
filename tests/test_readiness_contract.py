"""Contract of factory-registered /readyz, without network or app startup."""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
import httpx
import pytest

from backend.api.factory import _register_health_endpoints
from backend.api.routes import health
from backend.organism import scheduler as scheduler_module


@pytest.fixture(autouse=True)
def reset_readiness(monkeypatch):
    monkeypatch.setattr(health, "_readiness_cache", None)
    monkeypatch.setenv("ENABLE_ORGANISM_SCHEDULER", "true")


@pytest.fixture
def clock(monkeypatch):
    current = [1000.0]
    monkeypatch.setattr(health, "time", SimpleNamespace(monotonic=lambda: current[0]))
    return current


@pytest.fixture
def app(monkeypatch, clock):
    result = FastAPI()
    _register_health_endpoints(result)
    result.state.organism_scheduler = SimpleNamespace(
        is_running=True, _stop=asyncio.Event(), _tick_interval=10,
        _engine=SimpleNamespace(_initialized=True, brain=SimpleNamespace(_loaded=True)),
        _readiness_started_at=100.0, _readiness_last_loop_at=990.0,
        _readiness_tick_expected_since=500.0, _readiness_last_tick_completed_at=980.0,
    )
    monkeypatch.setattr(scheduler_module, "_is_market_tick_window", lambda: True)
    return result


@pytest.fixture
def probes(monkeypatch):
    db = AsyncMock(return_value=True)
    redis = AsyncMock(return_value=True)
    monkeypatch.setitem(sys.modules, "backend.infra.db", SimpleNamespace(db_health_check=db))
    monkeypatch.setitem(sys.modules, "backend.infra.broker", SimpleNamespace(broker_health_check=redis))
    return db, redis


async def get(app, path="/readyz"):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_actual_route_identifies_redis_and_preserves_budgets(app, probes):
    response = await get(app)
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ready"
    assert body["dependencies"]["database"]["component"] == "postgresql"
    assert body["dependencies"]["broker"]["component"] == "redis"
    assert body["dependencies"]["database"]["budget_ms"] == 100
    assert body["dependencies"]["broker"]["budget_ms"] == 200
    assert body["runtime"]["state"] == "tick_recent"
    assert body["checks"]["engine_initialized"] is True
    assert body["checks"]["tick_recent"] is True
    for probe in probes:
        probe.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("index,component", [(0, "database"), (1, "broker")])
@pytest.mark.parametrize("failure,outcome", [(False, "false"), (RuntimeError("private-url?token=never"), "error"), (TimeoutError("private-host"), "error")])
async def test_false_exception_and_inner_timeout_are_distinct(app, probes, index, component, failure, outcome):
    if isinstance(failure, Exception):
        probes[index].side_effect = failure
    else:
        probes[index].return_value = failure
    response = await get(app)
    assert response.status_code == 503
    body = response.json()
    assert body["dependencies"][component]["outcome"] == outcome
    assert body["checks"][component] is False
    assert "timeout" not in body["problems"][component].lower()
    assert "private" not in response.text and "never" not in response.text


@pytest.mark.asyncio
async def test_elapsed_exception_never_inferred_as_timeout(app, probes, clock):
    async def delayed_exception():
        clock[0] += 1  # Wall work can exceed budget without its cancellation firing.
        raise RuntimeError("secret reflected by transport")

    probes[0].side_effect = delayed_exception
    response = await get(app)
    assert response.json()["dependencies"]["database"]["elapsed_ms"] == 1000
    assert response.json()["dependencies"]["database"]["outcome"] == "error"
    assert response.json()["problems"]["database"] == "Database connection failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("index,component", [(0, "database"), (1, "broker")])
@pytest.mark.parametrize("suppress", [False, True])
async def test_actual_probe_deadline_and_cleanup(app, probes, index, component, suppress):
    cleanup = []

    async def blocked():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            if not suppress:
                raise
            return True
        finally:
            cleanup.append("closed")

    probes[index].side_effect = blocked
    response = await get(app)
    assert response.status_code == 503
    assert response.json()["dependencies"][component]["outcome"] == "timeout"
    assert "timeout" in response.json()["problems"][component]
    assert cleanup == ["closed"]


@pytest.mark.asyncio
async def test_parent_cancellation_propagates_without_cached_ready(app, probes):
    entered = asyncio.Event()
    cleaned = asyncio.Event()

    async def blocked():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    probes[0].side_effect = blocked
    task = asyncio.create_task(get(app))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()
    assert health._readiness_cache is None


@pytest.mark.asyncio
async def test_cache_keeps_observation_time_does_not_mutate_and_never_caches_runtime(app, probes, clock):
    first = await health.get_readiness_status(app_state=app.state)
    original = first.model_dump()
    first.dependencies["database"].outcome = "error"  # Responses cannot poison cache.
    clock[0] += 1
    app.state.organism_scheduler._stop.set()
    second = await get(app)
    body = second.json()
    assert second.status_code == 503 and body["cached"] is True
    assert body["cache_age_ms"] == 1000
    assert body["runtime"]["state"] == "scheduler_stopped"
    assert body["dependencies"] == original["dependencies"]
    assert first.cached is False and first.timestamp == original["timestamp"]
    assert all(p.await_count == 1 for p in probes)
    clock[0] += 1
    await get(app)
    assert all(p.await_count == 2 for p in probes)


@pytest.mark.asyncio
async def test_monotonic_rollback_invalidates_cache(app, probes, clock):
    await get(app)
    clock[0] -= 1
    response = await get(app)
    assert response.json()["cached"] is False
    assert all(p.await_count == 2 for p in probes)


@pytest.mark.asyncio
@pytest.mark.parametrize("state,expected", [
    ("missing", "missing_scheduler"), ("stopped", "scheduler_stopped"),
    ("stopping", "scheduler_stopped"), ("uninitialized", "engine_uninitialized"),
    ("unloaded", "brain_unloaded"), ("missing_clock", "invalid_timing"),
])
async def test_enabled_runtime_failure_is_not_healthy(app, probes, state, expected):
    sched = app.state.organism_scheduler
    if state == "missing":
        app.state.organism_scheduler = None
    elif state == "stopped":
        sched.is_running = False
    elif state == "stopping":
        sched._stop.set()
    elif state == "uninitialized":
        sched._engine._initialized = False
    elif state == "unloaded":
        sched._engine.brain._loaded = False
    else:
        sched._readiness_started_at = None
    response = await get(app)
    assert response.status_code == 503
    assert response.json()["runtime"]["state"] == expected


@pytest.mark.asyncio
async def test_disabled_scheduler_is_explicit_and_existing_scheduler_cannot_be_waived(app, probes, monkeypatch):
    monkeypatch.setenv("ENABLE_ORGANISM_SCHEDULER", "false")
    app.state.organism_scheduler.is_running = False
    assert (await get(app)).status_code == 503
    app.state.organism_scheduler = None
    response = await get(app)
    assert response.status_code == 200
    assert response.json()["runtime"]["state"] == "disabled"
    assert "tick_recent" not in response.json()["checks"]


@pytest.mark.asyncio
@pytest.mark.parametrize("expected,loop,first,complete,status,reason", [
    (False, 990, 500, 501, 200, "market_closed"),
    (False, 900, None, 501, 503, "loop_stale"),
    (True, 990, None, None, 200, "warming_up"),
    (True, 900, None, None, 503, "loop_stale"),
    (True, 990, 980, None, 200, "warming_up"),
    (True, 990, 900, None, 503, "tick_stale"),
    (True, 990, 980, 500, 200, "warming_up"),
    (True, 990, 500, 930, 200, "tick_recent"),
    (True, 990, 500, 929.99, 503, "tick_stale"),
])
async def test_market_closed_warmup_and_stale_boundaries(app, probes, monkeypatch, expected, loop, first, complete, status, reason):
    sched = app.state.organism_scheduler
    sched._readiness_last_loop_at = loop
    sched._readiness_tick_expected_since = first
    sched._readiness_last_tick_completed_at = complete
    monkeypatch.setattr(scheduler_module, "_is_market_tick_window", lambda: expected)
    response = await get(app)
    assert response.status_code == status
    body = response.json()
    assert body["runtime"]["state"] == reason
    assert body["runtime"]["budget_seconds"] == 70
    if reason == "market_closed":
        assert "tick_recent" not in body["checks"]


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, "990", 1001])
async def test_invalid_clock_metadata_fails_closed_without_nonfinite_json(app, probes, value):
    app.state.organism_scheduler._readiness_last_loop_at = value
    response = await get(app)
    assert response.status_code == 503
    assert response.json()["runtime"]["state"] == "invalid_timing"
    assert "NaN" not in response.text and "Infinity" not in response.text


@pytest.mark.asyncio
async def test_diagnostic_failure_is_fixed_and_metrics_cannot_fail_readiness(app, probes, monkeypatch):
    app.state.metrics_registry = SimpleNamespace(record_readyz_db_time=lambda _: 1 / 0)
    assert (await get(app)).status_code == 200

    def broken_window():
        raise RuntimeError("https://private-url?token=never")

    monkeypatch.setattr(scheduler_module, "_is_market_tick_window", broken_window)
    response = await get(app)
    assert response.status_code == 503
    assert response.json()["runtime"]["state"] == "diagnostic_error"
    assert "private" not in response.text and "never" not in response.text


@pytest.mark.asyncio
async def test_readiness_503_cannot_grant_watchdog_restart(app, probes):
    probes[1].return_value = False
    response = await get(app)
    spec = importlib.util.spec_from_file_location("readiness_watchdog", Path(__file__).parents[1] / "scripts/ops/paper_watchdog.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    diagnostics = module._readiness_diagnostics(SimpleNamespace(status=503), response.json())
    assert diagnostics["reasons"]["broker"] == "connection_failed"
    observation = {"daemon": True, "containers": {name: {"verified": True, "running": True, "health": "healthy", "age_seconds": 900} for name in ("api", "db", "redis")},
                   "readiness": {"reachable": True, "status": "not_ready"}, "problems": ["api_not_ready"]}
    assert module.choose_recovery(observation, False) is None


@pytest.mark.asyncio
async def test_liveness_stays_trivial_during_readiness_failure(app, probes):
    app.state.organism_scheduler = None
    assert (await get(app)).status_code == 503
    for path in ("/health", "/livez", "/healthz"):
        assert (await get(app, path)).status_code == 200
    assert all(p.await_count == 1 for p in probes)


@pytest.mark.asyncio
@pytest.mark.parametrize("market_open,tick_fails", [(False, False), (True, False), (True, True)])
async def test_actual_scheduler_loop_records_observations_without_faking_completion(tmp_path, monkeypatch, market_open, tick_fails):
    sched = scheduler_module.OrganismScheduler(data_client=None, order_service=None, positions_service=None, brain_dir=str(tmp_path))
    clock = [100.0]
    monkeypatch.setattr(scheduler_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(scheduler_module, "_is_market_tick_window", lambda: market_open)
    sched._readiness_started_at = 90.0

    async def diagnostic(_engine):
        assert sched._readiness_last_loop_at == 100.0
        clock[0] = 105.0
        if not market_open:
            sched._stop.set()

    result = SimpleNamespace(errors=[], regime="unknown", signals_generated=0, orders_submitted=0, trades_closed=0, duration_s=1.0, to_dict=lambda: {"timestamp": "old-start-time"})

    async def tick():
        assert sched._readiness_tick_expected_since == 105.0
        clock[0] = 110.0
        sched._stop.set()
        if tick_fails:
            raise RuntimeError("offline tick failure")
        return result

    sched._engine = SimpleNamespace(live_tick=tick)
    sched._diag_runner = SimpleNamespace(check_and_run=diagnostic)
    sched._broadcast_tick = AsyncMock()
    await sched._run_loop()
    assert sched._readiness_last_loop_at == 100.0
    assert sched._readiness_tick_expected_since == (105.0 if market_open else None)
    assert sched._readiness_last_tick_completed_at == (110.0 if market_open and not tick_fails else None)
    assert sched._last_tick_result == ({"timestamp": "old-start-time"} if market_open and not tick_fails else None)


@pytest.mark.asyncio
async def test_actual_scheduler_start_resets_old_session_clocks(tmp_path, monkeypatch):
    from backend.organism import live_engine

    engine = SimpleNamespace(initialize=AsyncMock(return_value=True), shutdown=AsyncMock())
    monkeypatch.setattr(live_engine, "OrganismLiveEngine", lambda **_: engine)
    sched = scheduler_module.OrganismScheduler(data_client=None, order_service=None, positions_service=None, brain_dir=str(tmp_path))
    sched._readiness_started_at = sched._readiness_last_loop_at = 1.0
    sched._readiness_tick_expected_since = sched._readiness_last_tick_completed_at = 1.0
    monkeypatch.setattr(scheduler_module, "time", SimpleNamespace(monotonic=lambda: 200.0))

    async def idle():
        await sched._stop.wait()

    sched._run_loop = idle
    await sched.start()
    assert sched.is_running
    assert sched._readiness_started_at == 200.0
    assert sched._readiness_last_loop_at is None
    assert sched._readiness_tick_expected_since is None
    assert sched._readiness_last_tick_completed_at is None
    await sched.stop()
    assert not sched.is_running
