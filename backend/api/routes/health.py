"""
Optimized health check endpoints with performance improvements.

- /health: Trivial check (<5ms) with just status and version
- /livez: Same as health (liveness)
- /readyz: Deep checks with micro-caching (2s TTL) and timeouts
"""

import asyncio
from datetime import UTC, datetime
import time

from fastapi import Response
from pydantic import BaseModel

from backend.config import get_settings


class HealthResponse(BaseModel):
    """Trivial health check response."""
    status: str = "ok"
    version: str
    timestamp: str


class ReadinessResponse(BaseModel):
    """Readiness check response with detailed status."""
    status: str
    checks: dict[str, bool]
    problems: dict[str, str]
    timestamp: str
    cached: bool = False


# Module-level cache for readiness checks (2s TTL)
_readiness_cache: tuple[float, ReadinessResponse] | None = None
_CACHE_TTL_SECONDS = 2.0

# Performance thresholds
_DB_TIMEOUT_MS = 100
_BROKER_TIMEOUT_MS = 200


def get_trivial_health() -> HealthResponse:
    """
    Ultra-fast health check without any I/O operations.
    Target: <5ms response time.
    """
    settings = get_settings()
    build_version = getattr(settings, 'BUILD_VERSION', '1.0.0')

    return HealthResponse(
        status="ok",
        version=build_version,
        timestamp=datetime.now(UTC).isoformat()
    )


async def check_database_health() -> tuple[bool, float]:
    """
    Check database health with strict timeout.

    Returns:
        Tuple of (is_healthy, response_time_ms)
    """
    start_time = time.perf_counter()

    try:
        # Import here to avoid startup dependency issues
        from backend.infra.db import db_health_check

        # Use asyncio.wait_for with strict timeout
        healthy = await asyncio.wait_for(
            db_health_check(),
            timeout=_DB_TIMEOUT_MS / 1000.0  # Convert to seconds
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return bool(healthy), elapsed_ms

    except TimeoutError:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return False, elapsed_ms
    except Exception:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return False, elapsed_ms


async def check_broker_health() -> tuple[bool, float]:
    """
    Check broker health with strict timeout.

    Returns:
        Tuple of (is_healthy, response_time_ms)
    """
    start_time = time.perf_counter()

    try:
        # Import here to avoid startup dependency issues
        from backend.infra.broker import broker_health_check

        # Use asyncio.wait_for with strict timeout
        healthy = await asyncio.wait_for(
            broker_health_check(),
            timeout=_BROKER_TIMEOUT_MS / 1000.0  # Convert to seconds
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return bool(healthy), elapsed_ms

    except TimeoutError:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return False, elapsed_ms
    except Exception:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return False, elapsed_ms


async def get_readiness_status(metrics_registry=None) -> ReadinessResponse:
    """
    Get readiness status with micro-caching and performance metrics.

    Cache TTL: 2 seconds to smooth request bursts.
    Timeouts: DB ≤100ms, Broker ≤200ms
    """
    global _readiness_cache

    current_time = time.time()

    # Check cache first
    if _readiness_cache:
        cache_timestamp, cached_result = _readiness_cache
        if current_time - cache_timestamp < _CACHE_TTL_SECONDS:
            # Return cached result with cache indicator
            cached_result.cached = True
            cached_result.timestamp = datetime.now(UTC).isoformat()
            return cached_result

    # Perform actual checks
    timestamp = datetime.now(UTC).isoformat()
    checks = {}
    problems = {}
    all_healthy = True

    # Check database with timeout and metrics
    db_healthy, db_time_ms = await check_database_health()
    checks["database"] = db_healthy

    if not db_healthy:
        all_healthy = False
        if db_time_ms >= _DB_TIMEOUT_MS:
            problems["database"] = f"Database timeout ({db_time_ms:.1f}ms > {_DB_TIMEOUT_MS}ms)"
        else:
            problems["database"] = "Database connection failed"

    # Record DB metrics
    if metrics_registry:
        try:
            if hasattr(metrics_registry, 'record_readyz_db_time'):
                metrics_registry.record_readyz_db_time(db_time_ms)
        except Exception:
            pass  # Don't fail health checks on metrics errors

    # Check broker with timeout and metrics
    broker_healthy, broker_time_ms = await check_broker_health()
    checks["broker"] = broker_healthy

    if not broker_healthy:
        all_healthy = False
        if broker_time_ms >= _BROKER_TIMEOUT_MS:
            problems["broker"] = f"Broker timeout ({broker_time_ms:.1f}ms > {_BROKER_TIMEOUT_MS}ms)"
        else:
            problems["broker"] = "Broker connection failed"

    # Record broker metrics
    if metrics_registry:
        try:
            if hasattr(metrics_registry, 'record_readyz_broker_time'):
                metrics_registry.record_readyz_broker_time(broker_time_ms)
        except Exception:
            pass  # Don't fail health checks on metrics errors

    # V10 YY-5 / Wave-52 (2026-05-03): include brain + tick-loop checks.
    # /readyz previously returned 200 even when brain was unloaded or
    # the live engine tick loop was dead.  Now: probe both via
    # app.state references, fail-soft if either subsystem is not yet
    # initialized (early startup) but fail-hard once we know they
    # should be running.
    try:
        from backend.api import lifespan as _lifespan_mod
        _engine = getattr(_lifespan_mod, "_LIVE_ENGINE_REF", None)
        if _engine is not None:
            brain = getattr(_engine, "brain", None)
            brain_loaded = bool(getattr(brain, "_loaded", False)) if brain else False
            checks["brain_loaded"] = brain_loaded
            if not brain_loaded:
                all_healthy = False
                problems["brain"] = "Brain not loaded"
            # Tick liveness: last successful tick within 5x scheduler interval.
            import time as _time
            _last_tick = getattr(_engine, "_last_tick_completed_ts", None)
            if _last_tick is not None:
                age = _time.time() - _last_tick
                if age > 60:  # 5x 10s scheduler
                    all_healthy = False
                    problems["tick_loop"] = f"Last tick {age:.0f}s ago (>60s)"
                checks["tick_recent"] = age <= 60
        # If _engine is None we're still in startup — do not fail-hard.
    except Exception as _ready_err:
        # Don't fail health checks on diagnostic errors.
        problems["readiness_diag"] = f"check error: {_ready_err}"

    # Create response
    result = ReadinessResponse(
        status="ready" if all_healthy else "not ready",
        checks=checks,
        problems=problems,
        timestamp=timestamp,
        cached=False
    )

    # Cache the result
    _readiness_cache = (current_time, result)

    return result


def create_health_endpoints():
    """
    Factory function to create optimized health check endpoints.

    Returns endpoint functions that can be registered with FastAPI.
    """

    async def health_check():
        """
        Trivial health check - no I/O operations.
        Target response time: <5ms
        """
        return get_trivial_health().model_dump()

    async def liveness_check():
        """
        Liveness check - same as health for Kubernetes compatibility.
        """
        return get_trivial_health().model_dump()

    async def readiness_check(request=None):
        """
        Readiness check with micro-caching and deep validation.

        - 2s cache TTL to smooth bursts
        - DB timeout: 100ms
        - Broker timeout: 200ms
        - Returns 503 if not ready
        """
        # Get metrics registry if available
        metrics_registry = None
        if request and hasattr(request.app, 'state'):
            metrics_registry = getattr(request.app.state, 'metrics_registry', None)

        result = await get_readiness_status(metrics_registry)

        if result.status != "ready":
            return Response(
                content=result.model_dump_json(),
                status_code=503,
                media_type="application/json"
            )

        return result.model_dump()

    return health_check, liveness_check, readiness_check
