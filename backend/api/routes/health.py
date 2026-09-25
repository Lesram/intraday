"""Bounded dependency and actual scheduler readiness diagnostics.

The legacy ``broker`` key means Redis, never Alpaca. Probe elapsed time includes
setup, query and cleanup; it is not server-side query latency.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import math
import os
import time
from typing import Literal

from fastapi import Response
from pydantic import BaseModel, Field

from backend.config import get_settings


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    timestamp: str


class DependencyCheck(BaseModel):
    """Only fixed outcomes and timings, never exception text or URLs."""

    component: Literal["postgresql", "redis"]
    outcome: Literal["ok", "timeout", "error", "false"]
    elapsed_ms: float = Field(ge=0, allow_inf_nan=False)
    budget_ms: int
    measured_at: str


class RuntimeCheck(BaseModel):
    state: Literal[
        "disabled", "missing_scheduler", "scheduler_stopped", "engine_uninitialized",
        "brain_unloaded", "invalid_timing", "diagnostic_error", "loop_stale",
        "tick_stale", "warming_up", "market_closed", "tick_recent",
    ]
    tick_expected: bool | None = None
    budget_seconds: float | None = None
    loop_age_seconds: float | None = None
    tick_age_seconds: float | None = None


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, bool]
    problems: dict[str, str]
    timestamp: str
    cached: bool = False
    cache_age_ms: float = 0.0
    dependencies: dict[str, DependencyCheck]
    runtime: RuntimeCheck


# Only dependencies are cached. A stopped scheduler cannot inherit a ready result.
_readiness_cache: tuple[float, dict[str, DependencyCheck]] | None = None
_CACHE_TTL_SECONDS = 2.0
_DB_TIMEOUT_MS = 100
_BROKER_TIMEOUT_MS = 200
_TICK_EXECUTION_BUDGET_SECONDS = 60.0  # Existing scheduler wait_for budget.


def get_trivial_health() -> HealthResponse:
    return HealthResponse(
        version=getattr(get_settings(), "BUILD_VERSION", "1.0.0"),
        timestamp=datetime.now(UTC).isoformat(),
    )


async def _dependency_check(
    component: Literal["postgresql", "redis"],
    budget_ms: int,
    load_check: Callable[[], Callable[[], Awaitable[bool]]],
) -> DependencyCheck:
    start = time.monotonic()
    measured_at = datetime.now(UTC).isoformat()
    timeout = asyncio.timeout(budget_ms / 1000)
    try:
        async with timeout:
            healthy = await load_check()()
        # Cleanup may suppress cancellation. An expired deadline is not success.
        outcome = "timeout" if timeout.expired() else ("ok" if healthy else "false")
    except TimeoutError:
        # An inner transport TimeoutError is not proof our probe budget expired.
        outcome = "timeout" if timeout.expired() else "error"
    except Exception:
        outcome = "timeout" if timeout.expired() else "error"
    return DependencyCheck(
        component=component, outcome=outcome,
        elapsed_ms=round(max(0.0, time.monotonic() - start) * 1000, 3),
        budget_ms=budget_ms, measured_at=measured_at,
    )


async def check_database_health() -> DependencyCheck:
    def load_check():
        from backend.infra.db import db_health_check
        return db_health_check

    return await _dependency_check("postgresql", _DB_TIMEOUT_MS, load_check)


async def check_broker_health() -> DependencyCheck:
    """Probe Redis; retain the historical name for existing callers."""
    def load_check():
        from backend.infra.broker import broker_health_check
        return broker_health_check

    return await _dependency_check("redis", _BROKER_TIMEOUT_MS, load_check)


def _finite_number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _runtime_check(app_state, now: float) -> tuple[dict[str, bool], RuntimeCheck]:
    checks = {}
    try:
        scheduler = getattr(app_state, "organism_scheduler", None)
        enabled = os.getenv("ENABLE_ORGANISM_SCHEDULER", "0").lower() in ("1", "true", "yes")
        if scheduler is None:
            if not enabled:
                return checks, RuntimeCheck(state="disabled")
            return {"scheduler_running": False}, RuntimeCheck(state="missing_scheduler")
        running = scheduler.is_running is True and not scheduler._stop.is_set()
        checks["scheduler_running"] = running
        if not running:
            return checks, RuntimeCheck(state="scheduler_stopped")
        engine = scheduler._engine
        checks["engine_initialized"] = getattr(engine, "_initialized", None) is True
        if not checks["engine_initialized"]:
            return checks, RuntimeCheck(state="engine_uninitialized")
        checks["brain_loaded"] = getattr(getattr(engine, "brain", None), "_loaded", None) is True
        if not checks["brain_loaded"]:
            return checks, RuntimeCheck(state="brain_unloaded")

        from backend.organism.scheduler import _is_market_tick_window

        expected = _is_market_tick_window()
        if type(expected) is not bool:
            raise ValueError("Invalid market window")
        started = scheduler._readiness_started_at
        loop = scheduler._readiness_last_loop_at
        first_expected = scheduler._readiness_tick_expected_since
        completed = scheduler._readiness_last_tick_completed_at
        interval = scheduler._tick_interval
        clocks = (started, loop, first_expected, completed)
        if (
            not _finite_number(now) or not _finite_number(interval) or interval <= 0
            or started is None
            or any(v is not None and (not _finite_number(v) or v < 0 or v > now) for v in clocks)
            or any(v is not None and v < started for v in clocks[1:])
        ):
            checks["tick_recent"] = False
            return checks, RuntimeCheck(state="invalid_timing", tick_expected=expected)
        budget = max(_TICK_EXECUTION_BUDGET_SECONDS, interval + _TICK_EXECUTION_BUDGET_SECONDS)
        loop_age = now - (started if loop is None else loop)
        details = {"tick_expected": expected, "budget_seconds": budget,
                   "loop_age_seconds": round(loop_age, 3)}
        checks["scheduler_loop_recent"] = loop_age <= budget
        if not checks["scheduler_loop_recent"]:
            checks["tick_recent"] = False
            return checks, RuntimeCheck(state="loop_stale", **details)
        if not expected:
            return checks, RuntimeCheck(state="market_closed", **details)
        # Closed->open may not have reached the next scheduler iteration yet.
        # This grace is bounded by the independently observed loop clock.
        if first_expected is None:
            return checks, RuntimeCheck(state="warming_up", **details)
        reference = max(first_expected, completed) if completed is not None else first_expected
        age = now - reference
        details["tick_age_seconds"] = round(age, 3)
        checks["tick_recent"] = age <= budget
        state = "tick_stale" if age > budget else (
            "tick_recent" if completed is not None and completed >= first_expected else "warming_up"
        )
        return checks, RuntimeCheck(state=state, **details)
    except Exception:
        checks["runtime_diagnostics"] = False
        return checks, RuntimeCheck(state="diagnostic_error")


async def get_readiness_status(metrics_registry=None, *, app_state=None) -> ReadinessResponse:
    """Preserve 100/200ms probe budgets; inspect actual scheduler every time."""
    global _readiness_cache
    now = time.monotonic()
    cached = _readiness_cache is not None and 0 <= now - _readiness_cache[0] < _CACHE_TTL_SECONDS
    if cached:
        cache_at, dependencies = _readiness_cache
        cache_age_ms = round((now - cache_at) * 1000, 3)
    else:
        dependencies = {"database": await check_database_health(), "broker": await check_broker_health()}
        _readiness_cache = (time.monotonic(), dependencies)
        cache_age_ms = 0.0
        if metrics_registry is not None:
            for key, name in (("database", "record_readyz_db_time"), ("broker", "record_readyz_broker_time")):
                try:
                    record = getattr(metrics_registry, name, None)
                    if record is not None:
                        record(dependencies[key].elapsed_ms)
                except Exception:
                    pass  # Metrics must not change readiness.

    checks = {key: value.outcome == "ok" for key, value in dependencies.items()}
    problems = {}
    for key, value in dependencies.items():
        if value.outcome == "ok":
            continue
        label = "Database" if key == "database" else "Broker"
        # Preserve legacy watchdog classification. Typed diagnostics distinguish
        # false returns, exceptions and actual expired probe deadlines.
        problems[key] = (
            f"{label} timeout ({value.elapsed_ms:.1f}ms > {value.budget_ms}ms)"
            if value.outcome == "timeout" else f"{label} connection failed"
        )
    runtime_checks, runtime = _runtime_check(app_state, time.monotonic())
    checks.update(runtime_checks)
    if not all(runtime_checks.values()):
        problems["runtime"] = runtime.state
    return ReadinessResponse(
        status="ready" if all(checks.values()) else "not ready",
        checks=checks, problems=problems, timestamp=datetime.now(UTC).isoformat(),
        cached=cached, cache_age_ms=cache_age_ms,
        dependencies={key: value.model_copy() for key, value in dependencies.items()},
        runtime=runtime,
    )


def create_health_endpoints():
    """Factory used by the actual /readyz registration in api.factory."""
    async def health_check():
        return get_trivial_health().model_dump()

    async def liveness_check():
        return get_trivial_health().model_dump()

    async def readiness_check(request=None):
        state = getattr(getattr(request, "app", None), "state", None)
        result = await get_readiness_status(getattr(state, "metrics_registry", None), app_state=state)
        if result.status != "ready":
            return Response(content=result.model_dump_json(), status_code=503, media_type="application/json")
        return result.model_dump()

    return health_check, liveness_check, readiness_check
