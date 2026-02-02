"""
Health Check API Endpoints for Production Deployment.

Provides Kubernetes-compatible health probes:
- /health/live - Liveness probe
- /health/ready - Readiness probe
- /health/full - Detailed health status

These endpoints integrate with the production readiness infrastructure.
"""


from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from backend.infra.production import (
    HealthStatus,
    get_production_readiness,
)

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    """Response model for liveness probe."""

    status: str
    timestamp: str


class ReadinessResponse(BaseModel):
    """Response model for readiness probe."""

    ready: bool
    status: str
    timestamp: str


class HealthCheckDetail(BaseModel):
    """Detail of a single health check."""

    status: str
    latency_ms: float
    message: str | None = None


class FullHealthResponse(BaseModel):
    """Response model for full health check."""

    status: str
    readiness: str
    uptime_seconds: float
    version: str
    environment: str
    checks: dict[str, HealthCheckDetail]
    timestamp: str


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Liveness Probe",
    description="Kubernetes liveness probe. Returns 200 if the application is running.",
    responses={
        200: {"description": "Application is alive"},
        503: {"description": "Application is not responding"},
    },
)
async def liveness_probe() -> LivenessResponse:
    """
    Check if the application is alive.

    This endpoint is used by Kubernetes to determine if the container
    should be restarted. It should return quickly and only check that
    the application is running, not its dependencies.
    """
    prod = get_production_readiness()
    result = await prod.liveness_check()

    return LivenessResponse(
        status=result["status"],
        timestamp=result["timestamp"],
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness Probe",
    description="Kubernetes readiness probe. Returns 200 if ready to receive traffic.",
    responses={
        200: {"description": "Application is ready"},
        503: {"description": "Application is not ready"},
    },
)
async def readiness_probe(response: Response) -> ReadinessResponse:
    """
    Check if the application is ready to receive traffic.

    This endpoint is used by Kubernetes to determine if the pod
    should receive traffic. It checks that all critical dependencies
    are healthy.
    """
    prod = get_production_readiness()
    result = await prod.readiness_check()

    if not result["ready"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        ready=result["ready"],
        status=result["status"],
        timestamp=result["timestamp"],
    )


@router.get(
    "/full",
    response_model=FullHealthResponse,
    summary="Full Health Check",
    description="Detailed health status of all components.",
    responses={
        200: {"description": "System is healthy"},
        503: {"description": "System has unhealthy components"},
    },
)
async def full_health_check(response: Response) -> FullHealthResponse:
    """
    Get comprehensive health status.

    Returns detailed information about all health checks,
    including latency and status of each component.
    """
    prod = get_production_readiness()
    health = await prod.get_system_health()

    if health.status == HealthStatus.UNHEALTHY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return FullHealthResponse(
        status=health.status.value,
        readiness=health.readiness.value,
        uptime_seconds=health.uptime_seconds,
        version=health.version,
        environment=health.environment,
        checks={
            name: HealthCheckDetail(
                status=check.status.value,
                latency_ms=check.latency_ms,
                message=check.message,
            )
            for name, check in health.checks.items()
        },
        timestamp=health.timestamp.isoformat(),
    )


@router.get(
    "/info",
    summary="Deployment Info",
    description="Get deployment metadata including version and build info.",
)
async def deployment_info() -> dict:
    """
    Get deployment information.

    Returns version, build ID, environment, and other metadata.
    """
    prod = get_production_readiness()
    return prod.deployment.get_info()


def setup_health_checks():
    """
    Register health checks for critical components.

    Call this during application startup to register
    health checks for database, Redis, etc.
    """
    prod = get_production_readiness()

    @prod.health.register("database", critical=True, timeout_seconds=5.0)
    async def check_database():
        """Check database connectivity."""
        # Import here to avoid circular imports
        from backend.db.database import get_db_session

        async for session in get_db_session():
            await session.execute("SELECT 1")
            return {"connected": True}

    @prod.health.register("application", critical=True)
    def check_application():
        """Check application is running."""
        return {"status": "running"}
