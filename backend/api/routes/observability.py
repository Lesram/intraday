"""
Observability API Routes.

Provides endpoints for:
- System health checks
- Metrics dashboard data
- Alert management
- Historical metrics
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.services.observability_service import (
    HealthStatus,
    ObservabilityService,
    get_observability_service,
)

router = APIRouter(prefix="/observability", tags=["observability"])


def get_service() -> ObservabilityService:
    """Dependency for observability service."""
    return get_observability_service()


@router.get("/health")
async def get_health(
    service: ObservabilityService = Depends(get_service),
) -> dict[str, Any]:
    """
    Get overall system health status.

    Returns health status for all monitored components.
    """
    return await service.get_system_health()


@router.get("/health/live")
async def liveness_probe() -> dict[str, Any]:
    """
    Kubernetes liveness probe endpoint.

    Simple check that the service is running.
    """
    return {
        "status": "alive",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/health/ready")
async def readiness_probe(
    service: ObservabilityService = Depends(get_service),
) -> dict[str, Any]:
    """
    Kubernetes readiness probe endpoint.

    Checks if the service is ready to accept traffic.
    """
    health = await service.get_system_health()

    is_ready = health["status"] in [
        HealthStatus.HEALTHY.value,
        HealthStatus.DEGRADED.value,
    ]

    return {
        "ready": is_ready,
        "status": health["status"],
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/metrics")
async def get_metrics(
    window: int = Query(
        default=60,
        ge=10,
        le=3600,
        description="Time window in seconds",
    ),
    service: ObservabilityService = Depends(get_service),
) -> dict[str, Any]:
    """
    Get system metrics for the specified time window.

    Returns aggregated metrics including:
    - API performance (requests/sec, latency, error rate)
    - Trading activity (orders, fills)
    - WebSocket metrics
    - ML inference metrics
    """
    metrics = service.get_system_metrics(window)

    return {
        "timestamp": metrics.timestamp.isoformat(),
        "window_seconds": window,
        "api": {
            "requests_per_second": round(metrics.requests_per_second, 2),
            "avg_response_time_ms": round(metrics.avg_response_time_ms, 2),
            "error_rate_pct": round(metrics.error_rate_pct, 2),
        },
        "trading": {
            "orders_per_minute": round(metrics.orders_per_minute, 2),
            "fills_per_minute": round(metrics.fills_per_minute, 2),
            "avg_fill_latency_ms": round(metrics.avg_fill_latency_ms, 2),
        },
        "websocket": {
            "connections": metrics.websocket_connections,
            "messages_per_second": round(metrics.websocket_messages_per_second, 2),
        },
        "ml": {
            "predictions_per_second": round(metrics.predictions_per_second, 2),
            "avg_prediction_latency_ms": round(metrics.avg_prediction_latency_ms, 2),
        },
    }


@router.get("/trading")
async def get_trading_metrics(
    window: int = Query(
        default=300,
        ge=60,
        le=86400,
        description="Time window in seconds",
    ),
    service: ObservabilityService = Depends(get_service),
) -> dict[str, Any]:
    """
    Get trading-specific metrics.

    Returns metrics focused on trading operations:
    - Order counts by status
    - Position metrics
    - Strategy metrics
    """
    metrics = service.get_trading_metrics(window)

    return {
        "timestamp": metrics.timestamp.isoformat(),
        "window_seconds": window,
        "orders": {
            "submitted": metrics.orders_submitted,
            "filled": metrics.orders_filled,
            "rejected": metrics.orders_rejected,
            "cancelled": metrics.orders_cancelled,
        },
        "strategies": {
            "active": metrics.active_strategies,
            "signals_generated": metrics.signals_generated,
        },
    }


@router.get("/dashboard")
async def get_dashboard_data(
    service: ObservabilityService = Depends(get_service),
) -> dict[str, Any]:
    """
    Get all data needed for the observability dashboard.

    Returns a comprehensive snapshot including:
    - Component health status
    - System metrics
    - Trading metrics
    - Active alerts
    """
    return service.get_dashboard_data()


@router.get("/alerts")
async def get_alerts(
    service: ObservabilityService = Depends(get_service),
) -> dict[str, Any]:
    """
    Get active alerts based on threshold violations.

    Returns alerts for metrics that exceed configured thresholds.
    """
    alerts = service.check_alerts()

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "alert_count": len(alerts),
        "alerts": alerts,
    }


@router.put("/thresholds/{metric}")
async def update_threshold(
    metric: str,
    value: float = Query(..., gt=0, description="New threshold value"),
    service: ObservabilityService = Depends(get_service),
) -> dict[str, Any]:
    """
    Update an alert threshold.

    Supported metrics:
    - error_rate_pct
    - avg_response_time_ms
    - fill_latency_ms
    - prediction_latency_ms
    """
    valid_metrics = [
        "error_rate_pct",
        "avg_response_time_ms",
        "fill_latency_ms",
        "prediction_latency_ms",
    ]

    if metric not in valid_metrics:
        return {
            "success": False,
            "error": f"Invalid metric. Valid options: {valid_metrics}",
        }

    service.set_threshold(metric, value)

    return {
        "success": True,
        "metric": metric,
        "new_value": value,
    }
