"""
Distributed tracing service with OpenTelemetry integration, span management,
trace analysis, and performance profiling capabilities.
"""

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import functools
import logging
from typing import Any, TypeVar

from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)

# Type hints
F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class SpanMetrics:
    """Metrics calculated from span data."""
    duration_ms: float
    status: str
    error_count: int = 0
    child_count: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceAnalysis:
    """Analysis results for a complete trace."""
    trace_id: str
    root_span_name: str
    total_duration_ms: float
    span_count: int
    error_count: int
    critical_path_ms: float
    bottlenecks: list[str] = field(default_factory=list)
    error_spans: list[str] = field(default_factory=list)
    performance_metrics: dict[str, float] = field(default_factory=dict)


class TraceStorage:
    """In-memory storage for trace data and analysis.
    
    H-18 NOTE: For production, configure OTLP exporter to send traces to 
    Jaeger, Tempo, or other persistent trace backends instead of relying 
    on in-memory storage. Set OTEL_EXPORTER_OTLP_ENDPOINT environment variable.
    
    This in-memory storage should only be used for development/testing.
    Production should use:
    - Jaeger: OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
    - Tempo: OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317
    - Honeycomb: OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io
    """

    def __init__(self, max_traces: int = 1000):
        import os
        # H-18 FIX: Warn if using in-memory storage in production
        env = os.environ.get('ENVIRONMENT', 'development')
        otlp_endpoint = os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT', '')
        
        if env == 'production' and not otlp_endpoint:
            logger.warning(
                "H-18 WARNING: Using in-memory trace storage in production. "
                "Configure OTEL_EXPORTER_OTLP_ENDPOINT for persistent trace storage."
            )
        
        self.max_traces = max_traces
        self.traces: dict[str, list[SpanMetrics]] = {}
        self.trace_metadata: dict[str, dict[str, Any]] = {}
        self._trace_order: list[str] = []

    def add_span(self, trace_id: str, span_metrics: SpanMetrics) -> None:
        """Add span metrics to trace storage."""
        if trace_id not in self.traces:
            self.traces[trace_id] = []
            self.trace_metadata[trace_id] = {
                "start_time": datetime.utcnow(),
                "span_count": 0,
                "status": "active"
            }
            self._trace_order.append(trace_id)

            # Cleanup old traces if limit exceeded
            if len(self._trace_order) > self.max_traces:
                old_trace_id = self._trace_order.pop(0)
                self.traces.pop(old_trace_id, None)
                self.trace_metadata.pop(old_trace_id, None)

        self.traces[trace_id].append(span_metrics)
        self.trace_metadata[trace_id]["span_count"] += 1

    def get_trace(self, trace_id: str) -> list[SpanMetrics] | None:
        """Get all spans for a trace."""
        return self.traces.get(trace_id)

    def get_recent_traces(self, limit: int = 10) -> list[str]:
        """Get most recent trace IDs."""
        return self._trace_order[-limit:] if self._trace_order else []

    def mark_trace_complete(self, trace_id: str) -> None:
        """Mark a trace as complete."""
        if trace_id in self.trace_metadata:
            self.trace_metadata[trace_id]["status"] = "complete"
            self.trace_metadata[trace_id]["end_time"] = datetime.utcnow()


class TracingCollector(SpanExporter):
    """Custom span exporter for collecting tracing data."""

    def __init__(self, storage: TraceStorage):
        self.storage = storage

    def export(self, spans: list[ReadableSpan]) -> SpanExportResult:
        """Export spans to trace storage."""
        try:
            for span in spans:
                trace_id = f"{span.context.trace_id:032x}"

                # Calculate span metrics
                duration_ms = 0
                if span.start_time and span.end_time:
                    duration_ms = (span.end_time - span.start_time) / 1_000_000  # Convert ns to ms

                status = "ok"
                error_count = 0
                if span.status and span.status.status_code == StatusCode.ERROR:
                    status = "error"
                    error_count = 1

                # Extract attributes
                attributes = {}
                if span.attributes:
                    attributes = dict(span.attributes)

                span_metrics = SpanMetrics(
                    duration_ms=duration_ms,
                    status=status,
                    error_count=error_count,
                    attributes=attributes
                )

                self.storage.add_span(trace_id, span_metrics)

            return SpanExportResult.SUCCESS
        except Exception as e:
            logger.error(f"Failed to export spans: {e}")
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        """Shutdown the exporter."""
        pass


class TraceAnalyzer:
    """Analyzer for trace performance and bottleneck detection."""

    def __init__(self, storage: TraceStorage):
        self.storage = storage

    def analyze_trace(self, trace_id: str) -> TraceAnalysis | None:
        """Analyze a complete trace for performance insights."""
        spans = self.storage.get_trace(trace_id)
        if not spans:
            return None

        total_duration = sum(span.duration_ms for span in spans)
        error_count = sum(span.error_count for span in spans)
        span_count = len(spans)

        # Find root span (assume first span or longest span)
        root_span = max(spans, key=lambda s: s.duration_ms)
        root_span_name = root_span.attributes.get("operation.name", "unknown")

        # Calculate critical path (longest sequence)
        critical_path_ms = root_span.duration_ms

        # Identify bottlenecks (spans taking >50% of total time)
        bottlenecks = []
        for span in spans:
            if span.duration_ms > (total_duration * 0.5):
                operation_name = span.attributes.get("operation.name", "unknown")
                bottlenecks.append(f"{operation_name}: {span.duration_ms:.2f}ms")

        # Collect error spans
        error_spans = []
        for span in spans:
            if span.status == "error":
                operation_name = span.attributes.get("operation.name", "unknown")
                error_spans.append(operation_name)

        # Performance metrics
        performance_metrics = {
            "avg_span_duration_ms": total_duration / span_count if span_count > 0 else 0,
            "max_span_duration_ms": max(span.duration_ms for span in spans) if spans else 0,
            "min_span_duration_ms": min(span.duration_ms for span in spans) if spans else 0,
            "error_rate": error_count / span_count if span_count > 0 else 0
        }

        return TraceAnalysis(
            trace_id=trace_id,
            root_span_name=root_span_name,
            total_duration_ms=total_duration,
            span_count=span_count,
            error_count=error_count,
            critical_path_ms=critical_path_ms,
            bottlenecks=bottlenecks,
            error_spans=error_spans,
            performance_metrics=performance_metrics
        )

    def get_performance_summary(self, hours: int = 1) -> dict[str, Any]:
        """Get performance summary for recent traces."""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        recent_traces = []
        for trace_id in self.storage.get_recent_traces(100):
            metadata = self.storage.trace_metadata.get(trace_id)
            if metadata and metadata.get("start_time", datetime.min) > cutoff_time:
                recent_traces.append(trace_id)

        if not recent_traces:
            return {"message": "No recent traces found"}

        # Analyze all recent traces
        analyses = []
        for trace_id in recent_traces:
            analysis = self.analyze_trace(trace_id)
            if analysis:
                analyses.append(analysis)

        if not analyses:
            return {"message": "No analyzable traces found"}

        # Calculate summary statistics
        total_traces = len(analyses)
        avg_duration = sum(a.total_duration_ms for a in analyses) / total_traces
        total_errors = sum(a.error_count for a in analyses)
        error_rate = total_errors / sum(a.span_count for a in analyses) if analyses else 0

        # Most common bottlenecks
        bottleneck_counts = defaultdict(int)
        for analysis in analyses:
            for bottleneck in analysis.bottlenecks:
                operation = bottleneck.split(":")[0]
                bottleneck_counts[operation] += 1

        top_bottlenecks = sorted(bottleneck_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "summary_period_hours": hours,
            "total_traces": total_traces,
            "avg_trace_duration_ms": avg_duration,
            "total_errors": total_errors,
            "error_rate": error_rate,
            "top_bottlenecks": top_bottlenecks,
            "trace_ids": recent_traces
        }


class TracingService:
    """Main tracing service with span management and analysis."""

    def __init__(self, service_name: str = "intraday-trading"):
        self.service_name = service_name
        self.storage = TraceStorage()
        self.collector = TracingCollector(self.storage)
        self.analyzer = TraceAnalyzer(self.storage)
        self._tracer: trace.Tracer | None = None
        self._initialized = False

    def initialize(self, sampling_rate: float = 0.1) -> None:
        """Initialize the tracing service."""
        if self._initialized:
            return

        # Create tracer provider with sampling
        sampler = TraceIdRatioBased(sampling_rate)
        tracer_provider = TracerProvider(sampler=sampler)
        trace.set_tracer_provider(tracer_provider)

        # Add our custom collector
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        span_processor = BatchSpanProcessor(self.collector)
        tracer_provider.add_span_processor(span_processor)

        # Get tracer instance
        self._tracer = trace.get_tracer(self.service_name)
        self._initialized = True

        logger.info(f"Tracing service initialized for {self.service_name}")

    def get_tracer(self) -> trace.Tracer:
        """Get the tracer instance."""
        if not self._initialized:
            self.initialize()
        return self._tracer or trace.get_tracer(self.service_name)

    @contextmanager
    def trace_operation(
        self,
        operation_name: str,
        attributes: dict[str, str | int | float | bool] | None = None
    ) -> Iterator[trace.Span]:
        """Create a traced operation span."""
        tracer = self.get_tracer()

        with tracer.start_as_current_span(operation_name) as span:
            try:
                # Set operation name attribute
                span.set_attribute("operation.name", operation_name)

                # Set additional attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                yield span

                # Mark as successful
                span.set_status(Status(StatusCode.OK))

            except Exception as e:
                # Record exception
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise

    @asynccontextmanager
    async def trace_async_operation(
        self,
        operation_name: str,
        attributes: dict[str, str | int | float | bool] | None = None
    ) -> AsyncIterator[trace.Span]:
        """Create a traced async operation span."""
        tracer = self.get_tracer()

        with tracer.start_as_current_span(operation_name) as span:
            try:
                # Set operation name attribute
                span.set_attribute("operation.name", operation_name)

                # Set additional attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                yield span

                # Mark as successful
                span.set_status(Status(StatusCode.OK))

            except Exception as e:
                # Record exception
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise

    def trace_decorator(
        self,
        operation_name: str | None = None,
        attributes: dict[str, str | int | float | bool] | None = None
    ):
        """Decorator to trace function execution."""
        def decorator(func: F) -> F:
            op_name = operation_name or f"{func.__module__}.{func.__name__}"

            if asyncio.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    async with self.trace_async_operation(op_name, attributes) as span:
                        # Add function metadata
                        span.set_attribute("function.name", func.__name__)
                        span.set_attribute("function.module", func.__module__)

                        result = await func(*args, **kwargs)

                        # Record result metadata if available
                        if hasattr(result, '__len__'):
                            try:
                                span.set_attribute("result.size", len(result))
                            except TypeError:
                                pass

                        return result
                return async_wrapper
            else:
                @functools.wraps(func)
                def sync_wrapper(*args, **kwargs):
                    with self.trace_operation(op_name, attributes) as span:
                        # Add function metadata
                        span.set_attribute("function.name", func.__name__)
                        span.set_attribute("function.module", func.__module__)

                        result = func(*args, **kwargs)

                        # Record result metadata if available
                        if hasattr(result, '__len__'):
                            try:
                                span.set_attribute("result.size", len(result))
                            except TypeError:
                                pass

                        return result
                return sync_wrapper

        return decorator

    def get_trace_analysis(self, trace_id: str) -> TraceAnalysis | None:
        """Get analysis for a specific trace."""
        return self.analyzer.analyze_trace(trace_id)

    def get_performance_summary(self, hours: int = 1) -> dict[str, Any]:
        """Get performance summary for recent traces."""
        return self.analyzer.get_performance_summary(hours)

    def get_active_traces(self) -> list[str]:
        """Get list of currently active trace IDs."""
        active_traces = []
        for trace_id, metadata in self.storage.trace_metadata.items():
            if metadata.get("status") == "active":
                active_traces.append(trace_id)
        return active_traces

    def get_trace_stats(self) -> dict[str, Any]:
        """Get general tracing statistics."""
        total_traces = len(self.storage.traces)
        active_traces = len(self.get_active_traces())

        # Calculate total spans
        total_spans = sum(len(spans) for spans in self.storage.traces.values())

        return {
            "total_traces": total_traces,
            "active_traces": active_traces,
            "total_spans": total_spans,
            "avg_spans_per_trace": total_spans / total_traces if total_traces > 0 else 0,
            "storage_utilization": total_traces / self.storage.max_traces
        }


# Global tracing service instance
_tracing_service: TracingService | None = None


def get_tracing_service() -> TracingService:
    """Get the global tracing service instance."""
    global _tracing_service
    if _tracing_service is None:
        _tracing_service = TracingService()
    return _tracing_service


def configure_otlp_exporter() -> bool:
    """
    H-18 FIX: Configure OTLP exporter for production trace persistence.
    
    Set OTEL_EXPORTER_OTLP_ENDPOINT environment variable to enable.
    Examples:
        - Jaeger: http://jaeger:4317
        - Tempo: http://tempo:4317
        - Honeycomb: https://api.honeycomb.io
    
    Returns True if OTLP exporter was configured, False otherwise.
    """
    import os
    
    endpoint = os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT', '')
    if not endpoint:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set, using in-memory trace storage")
        return False
    
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        
        provider = trace.get_tracer_provider()
        if isinstance(provider, TracerProvider):
            otlp_exporter = OTLPSpanExporter(endpoint=endpoint)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info(f"H-18: Configured OTLP trace exporter to {endpoint}")
            return True
        else:
            logger.warning("TracerProvider not available for OTLP configuration")
            return False
    except ImportError:
        logger.warning(
            "opentelemetry-exporter-otlp not installed. "
            "Install with: pip install opentelemetry-exporter-otlp"
        )
        return False
    except Exception as e:
        logger.error(f"Failed to configure OTLP exporter: {e}")
        return False


# M-34 FIX: Increased default sampling rate from 0.1 to 0.5 for HFT visibility
def initialize_tracing(service_name: str = "intraday-trading", sampling_rate: float = 0.5) -> None:
    """Initialize the global tracing service."""
    service = get_tracing_service()
    service.service_name = service_name
    service.initialize(sampling_rate)
    # H-18: Attempt to configure OTLP exporter for production trace persistence
    configure_otlp_exporter()


# Convenience functions for common tracing operations
def trace_operation(operation_name: str, attributes: dict[str, Any] | None = None):
    """Context manager for tracing operations."""
    return get_tracing_service().trace_operation(operation_name, attributes)


def trace_async_operation(operation_name: str, attributes: dict[str, Any] | None = None):
    """Async context manager for tracing operations."""
    return get_tracing_service().trace_async_operation(operation_name, attributes)


def trace_function(operation_name: str | None = None, attributes: dict[str, Any] | None = None):
    """Decorator for tracing function execution."""
    return get_tracing_service().trace_decorator(operation_name, attributes)


def get_current_trace_id() -> str | None:
    """Get the current trace ID."""
    current_span = trace.get_current_span()
    if current_span and current_span.context:
        return f"{current_span.context.trace_id:032x}"
    return None


def add_trace_event(name: str, attributes: dict[str, Any] | None = None) -> None:
    """Add an event to the current span."""
    current_span = trace.get_current_span()
    if current_span:
        current_span.add_event(name, attributes or {})


def set_trace_attribute(key: str, value: str | int | float | bool) -> None:
    """Set an attribute on the current span."""
    current_span = trace.get_current_span()
    if current_span:
        current_span.set_attribute(key, value)
