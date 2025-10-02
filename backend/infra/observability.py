"""
Core observability infrastructure with OpenTelemetry tracing, Prometheus metrics,
and standardized latency instrumentation decorators.
"""

import asyncio
import functools
import logging
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, TypeVar

from opentelemetry import metrics as otel_metrics
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ALWAYS_ON, TraceIdRatioBased
from opentelemetry.semconv.resource import ResourceAttributes

from .metrics import (
    MetricsRegistry,
    get_metrics_registry,
    normalize_alpaca_endpoint,
    normalize_route,
)

logger = logging.getLogger(__name__)

# Type hints
F = TypeVar("F", bound=Callable[..., Any])
AsyncF = TypeVar("AsyncF", bound=Callable[..., Any])

# Global observability instances
_tracer: trace.Tracer | None = None
_meter: otel_metrics.Meter | None = None
_metrics_registry: MetricsRegistry | None = None


class ObservabilityConfig:
    """Configuration container for observability setup."""

    def __init__(
        self,
        service_name: str = "intraday-trading",
        service_version: str = "2.0.0",
        otel_enabled: bool = True,
        otel_exporter_otlp_endpoint: str | None = None,
        otel_exporter_protocol: str = "grpc",
        otel_sampler: str = "traceidratio",
        otel_sampler_arg: float = 0.1,
        prometheus_enabled: bool = True,
        prometheus_path: str = "/metrics",
        metric_namespace: str = "intraday",
        latency_buckets_ms: str = "1,5,10,25,50,100,250,500,1000,2500,5000,10000",
    ):
        self.service_name = service_name
        self.service_version = service_version
        self.otel_enabled = otel_enabled
        self.otel_exporter_otlp_endpoint = otel_exporter_otlp_endpoint
        self.otel_exporter_protocol = otel_exporter_protocol
        self.otel_sampler = otel_sampler
        self.otel_sampler_arg = otel_sampler_arg
        self.prometheus_enabled = prometheus_enabled
        self.prometheus_path = prometheus_path
        self.metric_namespace = metric_namespace
        self.latency_buckets_ms = latency_buckets_ms

    @property
    def latency_buckets(self) -> list[float]:
        """Parse latency buckets from string to float list in seconds."""
        buckets_ms = [float(x.strip()) for x in self.latency_buckets_ms.split(",")]
        return [b / 1000.0 for b in buckets_ms]  # Convert ms to seconds


def initialize_observability(config: ObservabilityConfig) -> None:
    """
    Initialize OpenTelemetry tracing, metrics, and instrumentation.

    Args:
        config: Observability configuration object
    """
    global _tracer, _meter, _metrics_registry

    logger.info(f"Initializing observability for service: {config.service_name}")

    # Create resource with service information
    resource = Resource.create(
        {
            ResourceAttributes.SERVICE_NAME: config.service_name,
            ResourceAttributes.SERVICE_VERSION: config.service_version,
            ResourceAttributes.DEPLOYMENT_ENVIRONMENT: "production",
        }
    )

    # Initialize tracing if enabled
    if config.otel_enabled:
        _setup_tracing(config, resource)

    # Initialize metrics
    if config.prometheus_enabled:
        _setup_prometheus_metrics(config, resource)

    # Initialize OTEL metrics if OTLP endpoint provided
    if config.otel_enabled and config.otel_exporter_otlp_endpoint:
        _setup_otel_metrics(config, resource)

    # Setup instrumentation
    _setup_instrumentation()

    # Initialize metrics registry with custom buckets
    _metrics_registry = get_metrics_registry()

    logger.info("Observability initialization complete")


def _setup_tracing(config: ObservabilityConfig, resource: Resource) -> None:
    """Setup OpenTelemetry tracing with OTLP exporter."""
    global _tracer

    # Configure sampler
    if config.otel_sampler == "always_on":
        sampler = ALWAYS_ON
    elif config.otel_sampler == "always_off":
        sampler = ALWAYS_OFF
    elif config.otel_sampler == "traceidratio":
        sampler = TraceIdRatioBased(config.otel_sampler_arg)
    else:
        logger.warning(f"Unknown sampler: {config.otel_sampler}, using traceidratio")
        sampler = TraceIdRatioBased(0.1)

    # Create tracer provider
    tracer_provider = TracerProvider(resource=resource, sampler=sampler)
    trace.set_tracer_provider(tracer_provider)

    # Add OTLP span exporter if endpoint provided
    if config.otel_exporter_otlp_endpoint:
        otlp_exporter = OTLPSpanExporter(
            endpoint=config.otel_exporter_otlp_endpoint,
            insecure=True,  # Use TLS in production
        )
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)

        logger.info(
            f"OTLP trace exporter configured: {config.otel_exporter_otlp_endpoint}"
        )

    # Get tracer instance
    _tracer = trace.get_tracer(__name__)

    logger.info("OpenTelemetry tracing initialized")


def _setup_prometheus_metrics(config: ObservabilityConfig, resource: Resource) -> None:
    """Setup Prometheus metrics with custom buckets."""
    global _meter

    # Create Prometheus metric reader
    prometheus_reader = PrometheusMetricReader()

    # Create meter provider with Prometheus reader
    meter_provider = MeterProvider(
        resource=resource, metric_readers=[prometheus_reader]
    )
    otel_metrics.set_meter_provider(meter_provider)

    # Get meter instance
    _meter = otel_metrics.get_meter(__name__)

    logger.info("Prometheus metrics initialized")


def _setup_otel_metrics(config: ObservabilityConfig, resource: Resource) -> None:
    """Setup OpenTelemetry metrics with OTLP exporter."""
    if not config.otel_exporter_otlp_endpoint:
        return

    # Create OTLP metric exporter
    otlp_metric_exporter = OTLPMetricExporter(
        endpoint=config.otel_exporter_otlp_endpoint,
        insecure=True,  # Use TLS in production
    )

    # Create periodic exporting metric reader
    otlp_reader = PeriodicExportingMetricReader(
        exporter=otlp_metric_exporter,
        export_interval_millis=30000,  # Export every 30 seconds
    )

    # Get existing meter provider or create new one
    try:
        meter_provider = otel_metrics.get_meter_provider()
        if hasattr(meter_provider, "_metric_readers"):
            meter_provider._metric_readers.append(otlp_reader)
        logger.info(
            f"OTLP metrics exporter added: {config.otel_exporter_otlp_endpoint}"
        )
    except Exception as e:
        logger.warning(f"Could not add OTLP metrics exporter: {e}")


def _setup_instrumentation() -> None:
    """Setup automatic instrumentation for common libraries."""
    # Auto-instrument FastAPI (will be applied when FastAPI app is created)
    FastAPIInstrumentor().instrument()

    # Auto-instrument HTTP requests library
    RequestsInstrumentor().instrument()

    # Auto-instrument SQLAlchemy
    SQLAlchemyInstrumentor().instrument()

    # Auto-instrument asyncpg (PostgreSQL driver)
    AsyncPGInstrumentor().instrument()

    logger.info("Auto-instrumentation configured")


def get_tracer() -> trace.Tracer:
    """Get the global tracer instance."""
    global _tracer
    if _tracer is None:
        # Fallback tracer if not initialized
        _tracer = trace.get_tracer(__name__)
    return _tracer


def get_meter() -> otel_metrics.Meter:
    """Get the global meter instance."""
    global _meter
    if _meter is None:
        # Fallback meter if not initialized
        _meter = otel_metrics.get_meter(__name__)
    return _meter


@contextmanager
def trace_span(
    name: str, attributes: dict[str, str | int | float | bool] | None = None
):
    """
    Context manager for creating traced spans with automatic error handling.

    Args:
        name: Span name
        attributes: Optional span attributes

    Yields:
        OpenTelemetry Span object

    Example:
        with trace_span("alpaca_order_submit", {"symbol": "AAPL"}) as span:
            # Perform operation
            span.set_attribute("order_id", order_id)
    """
    tracer = get_tracer()

    with tracer.start_as_current_span(name) as span:
        try:
            # Set initial attributes
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)

            yield span

        except Exception as e:
            # Record exception in span
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            raise


def record_latency(
    metric_name: str,
    route: str | None = None,
    method: str | None = None,
    extra_labels: dict[str, str] | None = None,
):
    """
    Decorator to record operation latency in both OpenTelemetry and Prometheus metrics.

    Args:
        metric_name: Name of the metric to record latency
        route: HTTP route (normalized automatically)
        method: HTTP method
        extra_labels: Additional metric labels

    Example:
        @record_latency("alpaca_http_latency_seconds", method="POST")
        async def submit_order(...):
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()

            # Build labels
            labels = extra_labels.copy() if extra_labels else {}
            if route:
                labels["route"] = normalize_route(route)
            if method:
                labels["method"] = method

            # Start span
            span_name = f"{func.__name__}"
            with trace_span(span_name, labels) as span:
                try:
                    # Execute function
                    result = await func(*args, **kwargs)

                    # Record success metrics
                    duration = time.time() - start_time

                    # Record in Prometheus
                    metrics = get_metrics_registry()
                    metrics.observe_histogram(metric_name, duration, labels)

                    # Add latency to span
                    span.set_attribute("duration_seconds", duration)
                    span.set_attribute("success", True)

                    return result

                except Exception as e:
                    # Record error metrics
                    duration = time.time() - start_time
                    error_labels = labels.copy()
                    # Only add status if allowed for this histogram metric
                    try:
                        from .metrics import LABEL_ALLOWLIST as _ALLOW
                        if "status" in _ALLOW.get(metric_name, ()):  # type: ignore[arg-type]
                            error_labels["status"] = "error"
                    except Exception:
                        # If metrics allowlist unavailable, fall back to base labels
                        pass

                    metrics = get_metrics_registry()
                    metrics.observe_histogram(metric_name, duration, error_labels)

                    # Add error info to span
                    span.set_attribute("duration_seconds", duration)
                    span.set_attribute("success", False)
                    span.set_attribute("error_type", type(e).__name__)

                    raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()

            # Build labels
            labels = extra_labels.copy() if extra_labels else {}
            if route:
                labels["route"] = normalize_route(route)
            if method:
                labels["method"] = method

            # Start span
            span_name = f"{func.__name__}"
            with trace_span(span_name, labels) as span:
                try:
                    # Execute function
                    result = func(*args, **kwargs)

                    # Record success metrics
                    duration = time.time() - start_time

                    # Record in Prometheus
                    metrics = get_metrics_registry()
                    metrics.observe_histogram(metric_name, duration, labels)

                    # Add latency to span
                    span.set_attribute("duration_seconds", duration)
                    span.set_attribute("success", True)

                    return result

                except Exception as e:
                    # Record error metrics
                    duration = time.time() - start_time
                    error_labels = labels.copy()
                    # Only add status if allowed for this histogram metric
                    try:
                        from .metrics import LABEL_ALLOWLIST as _ALLOW
                        if "status" in _ALLOW.get(metric_name, ()):  # type: ignore[arg-type]
                            error_labels["status"] = "error"
                    except Exception:
                        # If metrics allowlist unavailable, fall back to base labels
                        pass

                    metrics = get_metrics_registry()
                    metrics.observe_histogram(metric_name, duration, error_labels)

                    # Add error info to span
                    span.set_attribute("duration_seconds", duration)
                    span.set_attribute("success", False)
                    span.set_attribute("error_type", type(e).__name__)

                    raise

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def record_operation(
    operation: str, success: bool = True, extra_labels: dict[str, str] | None = None
) -> None:
    """
    Record a business operation with standardized metrics and tracing.

    Args:
        operation: Operation name (e.g., "order_submit", "signal_generate")
        success: Whether operation succeeded
        extra_labels: Additional metric labels

    Example:
        record_operation("order_submit", True, {"symbol": "AAPL", "side": "buy"})
    """
    # Build labels
    labels = extra_labels.copy() if extra_labels else {}
    labels["result"] = "success" if success else "error"

    # Record counter metric
    metrics = get_metrics_registry()
    counter_name = f"{operation}_total"

    # Only record if metric is in allowlist
    from .metrics import LABEL_ALLOWLIST

    if counter_name in LABEL_ALLOWLIST:
        metrics.inc_counter(counter_name, labels)

    # Add span event
    current_span = trace.get_current_span()
    if current_span:
        current_span.add_event(
            f"operation_{operation}", attributes={"success": success, **labels}
        )


def record_alpaca_request(
    endpoint: str, method: str, status_code: int, duration_seconds: float
) -> None:
    """
    Record Alpaca API request metrics with normalized endpoints.

    Args:
        endpoint: Alpaca API endpoint path
        method: HTTP method
        status_code: Response status code
        duration_seconds: Request duration in seconds
    """
    # Normalize endpoint to prevent high cardinality
    normalized_endpoint = normalize_alpaca_endpoint(endpoint)

    # Determine status category
    if 200 <= status_code < 300:
        status = "success"
    elif 400 <= status_code < 500 or 500 <= status_code <= 599:
        status = "error"
    else:
        status = "error"

    # Record metrics
    metrics = get_metrics_registry()

    # Counter for total requests
    metrics.inc_counter(
        "alpaca_http_requests_total",
        {"endpoint": normalized_endpoint, "method": method, "status": status},
    )

    # Histogram for latency
    metrics.observe_histogram(
        "alpaca_http_latency_seconds",
        duration_seconds,
        {"endpoint": normalized_endpoint, "method": method},
    )


def record_database_operation(
    operation: str, duration_seconds: float, success: bool = True
) -> None:
    """
    Record database operation metrics.

    Args:
        operation: Database operation type (select, insert, update, delete, health_check)
        duration_seconds: Operation duration in seconds
        success: Whether operation succeeded
    """
    metrics = get_metrics_registry()

    # Record latency
    metrics.observe_histogram(
        "db_query_duration_seconds", duration_seconds, {"operation": operation}
    )

    # Record health check results if applicable
    if operation == "health_check":
        result = "success" if success else "error"
        metrics.inc_counter("db_health_checks_total", {"result": result})


def record_outbox_metrics(
    polled_count: int,
    dispatched_count: int,
    failed_count: int,
    queue_size: int,
    dispatch_duration_seconds: float | None = None,
) -> None:
    """
    Record outbox pattern metrics.

    Args:
        polled_count: Number of messages polled from outbox
        dispatched_count: Number of messages successfully dispatched
        failed_count: Number of messages that failed dispatch
        queue_size: Current outbox queue size
        dispatch_duration_seconds: Optional dispatch duration
    """
    metrics = get_metrics_registry()

    # Record polling
    if polled_count > 0:
        metrics.inc_counter("outbox_polled_total", amount=polled_count)

    # Record dispatches
    if dispatched_count > 0:
        metrics.inc_counter(
            "outbox_dispatched_total",
            {"topic": "orders", "status": "success"},
            amount=dispatched_count,
        )

    # Record failures
    if failed_count > 0:
        metrics.inc_counter(
            "outbox_dispatched_total",
            {"topic": "orders", "status": "failed"},
            amount=failed_count,
        )

    # Record queue size
    metrics.set_gauge("outbox_queue_gauge", queue_size, {"status": "pending"})

    # Record dispatch latency
    if dispatch_duration_seconds is not None:
        metrics.observe_histogram(
            "outbox_dispatch_latency_seconds",
            dispatch_duration_seconds,
            {"topic": "orders"},
        )


def record_auth_metrics(operation: str, success: bool, metrics: MetricsRegistry = None) -> None:
    """
    Record authentication metrics.

    Args:
        operation: Auth operation (attempt, token_validation)
        success: Whether operation succeeded
        metrics: Optional metrics registry to use (defaults to global registry)
    """
    registry = metrics if metrics is not None else get_metrics_registry()
    result = "success" if success else "error"

    if operation == "attempt":
        registry.inc_counter("auth_attempts_total", {"result": result})
    elif operation == "token_validation":
        registry.inc_counter("auth_token_validations_total", {"result": result})


def record_websocket_metrics(
    event: str,
    client_type: str = "trading",
    message_type: str | None = None,
    direction: str | None = None,
) -> None:
    """
    Record WebSocket metrics.

    Args:
        event: Event type (connection, message)
        client_type: Type of WebSocket client
        message_type: Type of message (for message events)
        direction: Message direction (for message events)
    """
    metrics = get_metrics_registry()

    if event == "connection":
        metrics.inc_counter("websocket_connections_total", {"client_type": client_type})
    elif event == "message" and message_type and direction:
        metrics.inc_counter(
            "websocket_messages_total",
            {"message_type": message_type, "direction": direction},
        )
