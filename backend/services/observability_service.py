"""
Enhanced Observability Service for Trading Platform.

Provides unified observability capabilities:
- System health monitoring
- Performance metrics aggregation
- Trading metrics dashboard
- Alert threshold monitoring
- Historical metrics storage

This service consolidates observability data from multiple sources
into a single API for dashboards and monitoring.
"""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
import logging
from typing import Any

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Component health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class MetricType(Enum):
    """Types of metrics tracked."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMING = "timing"


@dataclass
class MetricPoint:
    """A single metric data point."""

    timestamp: datetime
    value: float
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class HealthCheck:
    """Health check result for a component."""

    component: str
    status: HealthStatus
    latency_ms: float
    message: str | None = None
    last_checked: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemMetrics:
    """Aggregated system metrics snapshot."""

    timestamp: datetime

    # API metrics
    requests_per_second: float = 0.0
    avg_response_time_ms: float = 0.0
    error_rate_pct: float = 0.0

    # Trading metrics
    orders_per_minute: float = 0.0
    fills_per_minute: float = 0.0
    avg_fill_latency_ms: float = 0.0

    # System resources
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    db_connection_pool_used: int = 0
    db_connection_pool_available: int = 0

    # WebSocket metrics
    websocket_connections: int = 0
    websocket_messages_per_second: float = 0.0

    # ML metrics
    predictions_per_second: float = 0.0
    avg_prediction_latency_ms: float = 0.0
    model_cache_hit_rate: float = 0.0


@dataclass
class TradingMetrics:
    """Trading-specific metrics."""

    timestamp: datetime

    # Order metrics
    orders_submitted: int = 0
    orders_filled: int = 0
    orders_rejected: int = 0
    orders_cancelled: int = 0

    # Position metrics
    total_positions: int = 0
    long_positions: int = 0
    short_positions: int = 0
    total_exposure: float = 0.0

    # P&L metrics
    unrealized_pnl: float = 0.0
    realized_pnl_today: float = 0.0
    total_pnl: float = 0.0

    # Risk metrics
    daily_loss_used_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    margin_used_pct: float = 0.0

    # Strategy metrics
    active_strategies: int = 0
    signals_generated: int = 0


class MetricsBuffer:
    """
    Time-series buffer for metrics with automatic aggregation.

    Maintains rolling windows for different time granularities:
    - 1-second granularity for last 5 minutes
    - 1-minute granularity for last hour
    - 1-hour granularity for last 24 hours
    """

    def __init__(self, max_points: int = 3600):
        self._points: deque[MetricPoint] = deque(maxlen=max_points)

    def record(self, value: float, labels: dict[str, str] | None = None):
        """Record a new data point."""
        self._points.append(MetricPoint(
            timestamp=datetime.now(UTC),
            value=value,
            labels=labels or {},
        ))

    def get_recent(self, seconds: int = 60) -> list[MetricPoint]:
        """Get points from the last N seconds."""
        cutoff = datetime.now(UTC) - timedelta(seconds=seconds)
        return [p for p in self._points if p.timestamp > cutoff]

    def get_rate(self, seconds: int = 60) -> float:
        """Calculate rate (events per second) over time window."""
        points = self.get_recent(seconds)
        if not points or seconds == 0:
            return 0.0
        return len(points) / seconds

    def get_average(self, seconds: int = 60) -> float:
        """Calculate average value over time window."""
        points = self.get_recent(seconds)
        if not points:
            return 0.0
        return sum(p.value for p in points) / len(points)

    def get_percentile(self, percentile: float, seconds: int = 60) -> float:
        """Calculate percentile value over time window."""
        points = self.get_recent(seconds)
        if not points:
            return 0.0

        values = sorted(p.value for p in points)
        idx = int(len(values) * percentile / 100)
        return values[min(idx, len(values) - 1)]


class ObservabilityService:
    """
    Central observability service for the trading platform.

    Aggregates metrics from various sources and provides:
    - Unified health status
    - System and trading metrics
    - Historical data for dashboards
    - Alert threshold monitoring

    Usage:
        obs = ObservabilityService()

        # Record metrics
        obs.record_api_request("/api/orders", 45.5, 200)
        obs.record_order_event("submitted")

        # Get dashboard data
        health = await obs.get_system_health()
        metrics = obs.get_trading_metrics()
    """

    def __init__(self):
        # Metric buffers
        self._api_latency = MetricsBuffer(max_points=10000)
        self._api_errors = MetricsBuffer(max_points=10000)
        self._order_events = MetricsBuffer(max_points=10000)
        self._fill_latency = MetricsBuffer(max_points=10000)
        self._predictions = MetricsBuffer(max_points=10000)
        self._ws_messages = MetricsBuffer(max_points=10000)

        # Health check results
        self._health_checks: dict[str, HealthCheck] = {}

        # Alert thresholds
        self._thresholds = {
            "error_rate_pct": 5.0,
            "avg_response_time_ms": 500.0,
            "fill_latency_ms": 100.0,
            "prediction_latency_ms": 50.0,
        }

        # Current state
        self._websocket_connections = 0
        self._active_strategies = 0

    # Metric recording methods

    def record_api_request(
        self,
        endpoint: str,
        latency_ms: float,
        status_code: int,
    ):
        """Record an API request."""
        self._api_latency.record(latency_ms, {"endpoint": endpoint})

        if status_code >= 400:
            self._api_errors.record(1.0, {
                "endpoint": endpoint,
                "status": str(status_code),
            })

    def record_order_event(
        self,
        event_type: str,
        symbol: str | None = None,
    ):
        """Record an order event (submitted, filled, rejected, cancelled)."""
        self._order_events.record(1.0, {
            "event_type": event_type,
            "symbol": symbol or "unknown",
        })

    def record_fill_latency(self, latency_ms: float):
        """Record order fill latency."""
        self._fill_latency.record(latency_ms)

    def record_prediction(self, latency_ms: float, model_name: str):
        """Record ML prediction."""
        self._predictions.record(latency_ms, {"model": model_name})

    def record_websocket_message(self, direction: str, message_type: str):
        """Record WebSocket message."""
        self._ws_messages.record(1.0, {
            "direction": direction,
            "type": message_type,
        })

    def set_websocket_connections(self, count: int):
        """Update WebSocket connection count."""
        self._websocket_connections = count

    def set_active_strategies(self, count: int):
        """Update active strategy count."""
        self._active_strategies = count

    # Health check methods

    async def check_component_health(
        self,
        component: str,
        check_fn,
        timeout_seconds: float = 5.0,
    ) -> HealthCheck:
        """
        Run a health check for a component.

        Args:
            component: Component name
            check_fn: Async function that raises on failure
            timeout_seconds: Check timeout

        Returns:
            HealthCheck result
        """
        start = datetime.now(UTC)

        try:
            await asyncio.wait_for(check_fn(), timeout=timeout_seconds)

            latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000

            result = HealthCheck(
                component=component,
                status=HealthStatus.HEALTHY,
                latency_ms=latency_ms,
                message="OK",
            )

        except TimeoutError:
            result = HealthCheck(
                component=component,
                status=HealthStatus.UNHEALTHY,
                latency_ms=timeout_seconds * 1000,
                message=f"Timeout after {timeout_seconds}s",
            )

        except Exception as e:
            latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
            result = HealthCheck(
                component=component,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message=str(e),
            )

        self._health_checks[component] = result
        return result

    async def get_system_health(self) -> dict[str, Any]:
        """
        Get overall system health status.

        Returns aggregated health from all components.
        """
        # Determine overall status.
        # V7 EE-2 / Wave-25 (2026-05-03): empty `_health_checks` (no
        # components opted in to reporting) was returning UNKNOWN, which
        # made `/health/ready` answer `{"ready": false}` for a healthy
        # process. Treat empty as HEALTHY — the API process IS up
        # (this code is executing); UNKNOWN is reserved for actual
        # ambiguity. The fallback K8s liveness probe is `/healthz`.
        statuses = [hc.status for hc in self._health_checks.values()]

        if not statuses:
            overall = HealthStatus.HEALTHY
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            overall = HealthStatus.HEALTHY
        elif any(s == HealthStatus.UNHEALTHY for s in statuses):
            overall = HealthStatus.UNHEALTHY
        else:
            overall = HealthStatus.DEGRADED

        return {
            "status": overall.value,
            "timestamp": datetime.now(UTC).isoformat(),
            "components": {
                name: {
                    "status": hc.status.value,
                    "latency_ms": hc.latency_ms,
                    "message": hc.message,
                    "last_checked": hc.last_checked.isoformat(),
                }
                for name, hc in self._health_checks.items()
            },
        }

    # Metrics aggregation methods

    def get_system_metrics(self, window_seconds: int = 60) -> SystemMetrics:
        """Get aggregated system metrics."""
        return SystemMetrics(
            timestamp=datetime.now(UTC),

            # API metrics
            requests_per_second=self._api_latency.get_rate(window_seconds),
            avg_response_time_ms=self._api_latency.get_average(window_seconds),
            error_rate_pct=self._calculate_error_rate(window_seconds),

            # Trading metrics
            orders_per_minute=self._order_events.get_rate(window_seconds) * 60,
            fills_per_minute=self._count_events("filled", window_seconds) * 60 / max(window_seconds, 1),
            avg_fill_latency_ms=self._fill_latency.get_average(window_seconds),

            # WebSocket
            websocket_connections=self._websocket_connections,
            websocket_messages_per_second=self._ws_messages.get_rate(window_seconds),

            # ML
            predictions_per_second=self._predictions.get_rate(window_seconds),
            avg_prediction_latency_ms=self._predictions.get_average(window_seconds),
        )

    def get_trading_metrics(self, window_seconds: int = 300) -> TradingMetrics:
        """Get trading-specific metrics."""
        return TradingMetrics(
            timestamp=datetime.now(UTC),

            # Order counts
            orders_submitted=self._count_events("submitted", window_seconds),
            orders_filled=self._count_events("filled", window_seconds),
            orders_rejected=self._count_events("rejected", window_seconds),
            orders_cancelled=self._count_events("cancelled", window_seconds),

            # Strategy
            active_strategies=self._active_strategies,
            signals_generated=self._count_events("signal", window_seconds),
        )

    def _calculate_error_rate(self, window_seconds: int) -> float:
        """Calculate error rate percentage."""
        total = len(self._api_latency.get_recent(window_seconds))
        errors = len(self._api_errors.get_recent(window_seconds))

        if total == 0:
            return 0.0

        return (errors / total) * 100

    def _count_events(self, event_type: str, window_seconds: int) -> int:
        """Count events of a specific type."""
        points = self._order_events.get_recent(window_seconds)
        return sum(1 for p in points if p.labels.get("event_type") == event_type)

    # Alert threshold methods

    def check_alerts(self) -> list[dict[str, Any]]:
        """Check for threshold violations and return active alerts."""
        alerts = []
        metrics = self.get_system_metrics()

        # Error rate check
        if metrics.error_rate_pct > self._thresholds["error_rate_pct"]:
            alerts.append({
                "metric": "error_rate_pct",
                "current": metrics.error_rate_pct,
                "threshold": self._thresholds["error_rate_pct"],
                "severity": "warning",
                "message": f"Error rate {metrics.error_rate_pct:.1f}% exceeds threshold",
            })

        # Response time check
        if metrics.avg_response_time_ms > self._thresholds["avg_response_time_ms"]:
            alerts.append({
                "metric": "avg_response_time_ms",
                "current": metrics.avg_response_time_ms,
                "threshold": self._thresholds["avg_response_time_ms"],
                "severity": "warning",
                "message": f"Avg response time {metrics.avg_response_time_ms:.0f}ms exceeds threshold",
            })

        # Fill latency check
        if metrics.avg_fill_latency_ms > self._thresholds["fill_latency_ms"]:
            alerts.append({
                "metric": "fill_latency_ms",
                "current": metrics.avg_fill_latency_ms,
                "threshold": self._thresholds["fill_latency_ms"],
                "severity": "critical",
                "message": f"Fill latency {metrics.avg_fill_latency_ms:.0f}ms exceeds threshold",
            })

        # Prediction latency check
        if metrics.avg_prediction_latency_ms > self._thresholds["prediction_latency_ms"]:
            alerts.append({
                "metric": "prediction_latency_ms",
                "current": metrics.avg_prediction_latency_ms,
                "threshold": self._thresholds["prediction_latency_ms"],
                "severity": "warning",
                "message": f"Prediction latency {metrics.avg_prediction_latency_ms:.0f}ms exceeds threshold",
            })

        return alerts

    def set_threshold(self, metric: str, value: float):
        """Update an alert threshold."""
        if metric in self._thresholds:
            self._thresholds[metric] = value
            logger.info(f"Updated threshold {metric} to {value}")

    # Dashboard data methods

    def get_dashboard_data(self) -> dict[str, Any]:
        """Get all data needed for observability dashboard."""
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "health": {
                name: {
                    "status": hc.status.value,
                    "latency_ms": hc.latency_ms,
                }
                for name, hc in self._health_checks.items()
            },
            "system_metrics": {
                "requests_per_second": self._api_latency.get_rate(60),
                "avg_latency_ms": self._api_latency.get_average(60),
                "p99_latency_ms": self._api_latency.get_percentile(99, 60),
                "error_rate_pct": self._calculate_error_rate(60),
            },
            "trading_metrics": {
                "orders_per_minute": self._order_events.get_rate(60) * 60,
                "fills_per_minute": self._count_events("filled", 60),
                "avg_fill_latency_ms": self._fill_latency.get_average(60),
            },
            "websocket": {
                "connections": self._websocket_connections,
                "messages_per_second": self._ws_messages.get_rate(60),
            },
            "ml": {
                "predictions_per_second": self._predictions.get_rate(60),
                "avg_latency_ms": self._predictions.get_average(60),
            },
            "alerts": self.check_alerts(),
        }


# Global singleton
_observability_service: ObservabilityService | None = None


def get_observability_service() -> ObservabilityService:
    """Get or create the global observability service."""
    global _observability_service
    if _observability_service is None:
        _observability_service = ObservabilityService()
    return _observability_service
