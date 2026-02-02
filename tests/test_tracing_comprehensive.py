"""
Comprehensive tests for backend.observability.tracing module.

Tests:
- SpanMetrics and TraceAnalysis dataclasses
- TraceStorage (add, get, cleanup)
- TracingCollector (span export)
- TraceAnalyzer (analysis, performance summary)
- TracingService (initialization, operations, decorators)
- Global functions and convenience methods
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest

from backend.observability.tracing import (
    # Dataclasses
    SpanMetrics,
    TraceAnalysis,
    # Classes
    TraceStorage,
    TracingCollector,
    TraceAnalyzer,
    TracingService,
    # Global instance and functions
    get_tracing_service,
    initialize_tracing,
    trace_operation,
    trace_async_operation,
    trace_function,
    get_current_trace_id,
    add_trace_event,
    set_trace_attribute,
)


# ============================================================================
# DATACLASS TESTS
# ============================================================================

class TestSpanMetrics:
    """Tests for SpanMetrics dataclass."""
    
    def test_default_values(self):
        """Test SpanMetrics with default values."""
        metrics = SpanMetrics(duration_ms=100.0, status="ok")
        
        assert metrics.duration_ms == 100.0
        assert metrics.status == "ok"
        assert metrics.error_count == 0
        assert metrics.child_count == 0
        assert metrics.attributes == {}
        
    def test_with_all_values(self):
        """Test SpanMetrics with all values."""
        metrics = SpanMetrics(
            duration_ms=250.5,
            status="error",
            error_count=1,
            child_count=3,
            attributes={"operation.name": "test_op"}
        )
        
        assert metrics.duration_ms == 250.5
        assert metrics.status == "error"
        assert metrics.error_count == 1
        assert metrics.attributes["operation.name"] == "test_op"


class TestTraceAnalysis:
    """Tests for TraceAnalysis dataclass."""
    
    def test_default_values(self):
        """Test TraceAnalysis with default values."""
        analysis = TraceAnalysis(
            trace_id="abc123",
            root_span_name="root",
            total_duration_ms=500.0,
            span_count=5,
            error_count=0,
            critical_path_ms=300.0
        )
        
        assert analysis.trace_id == "abc123"
        assert analysis.root_span_name == "root"
        assert analysis.total_duration_ms == 500.0
        assert analysis.bottlenecks == []
        assert analysis.error_spans == []
        assert analysis.performance_metrics == {}
        
    def test_with_all_values(self):
        """Test TraceAnalysis with all values."""
        analysis = TraceAnalysis(
            trace_id="def456",
            root_span_name="main",
            total_duration_ms=1000.0,
            span_count=10,
            error_count=2,
            critical_path_ms=600.0,
            bottlenecks=["db_query: 400ms"],
            error_spans=["api_call"],
            performance_metrics={"avg_span_duration_ms": 100.0}
        )
        
        assert analysis.error_count == 2
        assert len(analysis.bottlenecks) == 1
        assert analysis.performance_metrics["avg_span_duration_ms"] == 100.0


# ============================================================================
# TRACE STORAGE TESTS
# ============================================================================

class TestTraceStorage:
    """Tests for TraceStorage class."""
    
    @pytest.fixture
    def storage(self):
        """Create a test storage instance."""
        return TraceStorage(max_traces=5)
        
    def test_init(self, storage):
        """Test storage initialization."""
        assert storage.max_traces == 5
        assert storage.traces == {}
        assert storage.trace_metadata == {}
        
    def test_add_span_creates_trace(self, storage):
        """Test adding first span creates trace entry."""
        span = SpanMetrics(duration_ms=100.0, status="ok")
        storage.add_span("trace_001", span)
        
        assert "trace_001" in storage.traces
        assert len(storage.traces["trace_001"]) == 1
        assert "trace_001" in storage.trace_metadata
        assert storage.trace_metadata["trace_001"]["span_count"] == 1
        
    def test_add_span_appends(self, storage):
        """Test adding multiple spans to same trace."""
        span1 = SpanMetrics(duration_ms=100.0, status="ok")
        span2 = SpanMetrics(duration_ms=200.0, status="ok")
        
        storage.add_span("trace_001", span1)
        storage.add_span("trace_001", span2)
        
        assert len(storage.traces["trace_001"]) == 2
        assert storage.trace_metadata["trace_001"]["span_count"] == 2
        
    def test_max_traces_cleanup(self, storage):
        """Test old traces are removed when max exceeded."""
        for i in range(7):  # Add more than max_traces=5
            span = SpanMetrics(duration_ms=100.0, status="ok")
            storage.add_span(f"trace_{i:03d}", span)
            
        # Should have only last 5 traces
        assert len(storage.traces) == 5
        assert "trace_000" not in storage.traces
        assert "trace_001" not in storage.traces
        assert "trace_006" in storage.traces
        
    def test_get_trace_existing(self, storage):
        """Test getting existing trace."""
        span = SpanMetrics(duration_ms=100.0, status="ok")
        storage.add_span("trace_001", span)
        
        result = storage.get_trace("trace_001")
        assert result is not None
        assert len(result) == 1
        
    def test_get_trace_nonexistent(self, storage):
        """Test getting nonexistent trace returns None."""
        result = storage.get_trace("nonexistent")
        assert result is None
        
    def test_get_recent_traces(self, storage):
        """Test getting recent traces."""
        for i in range(3):
            span = SpanMetrics(duration_ms=100.0, status="ok")
            storage.add_span(f"trace_{i:03d}", span)
            
        recent = storage.get_recent_traces(limit=2)
        assert len(recent) == 2
        assert recent == ["trace_001", "trace_002"]
        
    def test_get_recent_traces_empty(self, storage):
        """Test getting recent traces when empty."""
        recent = storage.get_recent_traces()
        assert recent == []
        
    def test_mark_trace_complete(self, storage):
        """Test marking trace as complete."""
        span = SpanMetrics(duration_ms=100.0, status="ok")
        storage.add_span("trace_001", span)
        
        storage.mark_trace_complete("trace_001")
        
        assert storage.trace_metadata["trace_001"]["status"] == "complete"
        assert "end_time" in storage.trace_metadata["trace_001"]
        
    def test_mark_trace_complete_nonexistent(self, storage):
        """Test marking nonexistent trace does nothing."""
        storage.mark_trace_complete("nonexistent")  # Should not raise


# ============================================================================
# TRACING COLLECTOR TESTS
# ============================================================================

class TestTracingCollector:
    """Tests for TracingCollector class."""
    
    @pytest.fixture
    def collector(self):
        """Create a test collector."""
        storage = TraceStorage()
        return TracingCollector(storage)
        
    def test_export_empty_list(self, collector):
        """Test exporting empty span list."""
        from opentelemetry.sdk.trace.export import SpanExportResult
        
        result = collector.export([])
        assert result == SpanExportResult.SUCCESS
        
    def test_export_with_mock_spans(self, collector):
        """Test exporting mock spans."""
        from opentelemetry.sdk.trace.export import SpanExportResult
        from opentelemetry.trace import StatusCode
        
        # Create mock span
        mock_span = MagicMock()
        mock_span.context = MagicMock()
        mock_span.context.trace_id = 12345
        mock_span.start_time = 1000000000  # 1 second in ns
        mock_span.end_time = 1100000000    # 1.1 seconds in ns
        mock_span.status = MagicMock()
        mock_span.status.status_code = StatusCode.OK
        mock_span.attributes = {"test": "value"}
        
        result = collector.export([mock_span])
        assert result == SpanExportResult.SUCCESS
        
        # Check span was stored
        trace_id = f"{12345:032x}"
        assert trace_id in collector.storage.traces
        
    def test_export_error_span(self, collector):
        """Test exporting error span."""
        from opentelemetry.sdk.trace.export import SpanExportResult
        from opentelemetry.trace import StatusCode
        
        mock_span = MagicMock()
        mock_span.context = MagicMock()
        mock_span.context.trace_id = 54321
        mock_span.start_time = 1000000000
        mock_span.end_time = 1050000000
        mock_span.status = MagicMock()
        mock_span.status.status_code = StatusCode.ERROR
        mock_span.attributes = {}
        
        result = collector.export([mock_span])
        assert result == SpanExportResult.SUCCESS
        
        # Check error was recorded
        trace_id = f"{54321:032x}"
        spans = collector.storage.get_trace(trace_id)
        assert spans[0].status == "error"
        assert spans[0].error_count == 1
        
    def test_shutdown(self, collector):
        """Test shutdown does nothing but exists."""
        collector.shutdown()  # Should not raise


# ============================================================================
# TRACE ANALYZER TESTS
# ============================================================================

class TestTraceAnalyzer:
    """Tests for TraceAnalyzer class."""
    
    @pytest.fixture
    def analyzer(self):
        """Create an analyzer with test data."""
        storage = TraceStorage()
        
        # Add test spans
        spans = [
            SpanMetrics(duration_ms=100.0, status="ok", attributes={"operation.name": "root"}),
            SpanMetrics(duration_ms=200.0, status="ok", attributes={"operation.name": "child1"}),
            SpanMetrics(duration_ms=50.0, status="error", error_count=1, attributes={"operation.name": "child2"}),
        ]
        
        for span in spans:
            storage.add_span("test_trace", span)
            
        return TraceAnalyzer(storage)
        
    def test_analyze_trace_success(self, analyzer):
        """Test analyzing a trace."""
        analysis = analyzer.analyze_trace("test_trace")
        
        assert analysis is not None
        assert analysis.trace_id == "test_trace"
        assert analysis.span_count == 3
        assert analysis.error_count == 1
        assert analysis.total_duration_ms == 350.0
        
    def test_analyze_trace_nonexistent(self, analyzer):
        """Test analyzing nonexistent trace returns None."""
        result = analyzer.analyze_trace("nonexistent")
        assert result is None
        
    def test_analyze_finds_root_span(self, analyzer):
        """Test analysis finds root span (longest span)."""
        analysis = analyzer.analyze_trace("test_trace")
        
        # Root span is the longest (200ms child1)
        assert analysis.root_span_name == "child1"
        assert analysis.critical_path_ms == 200.0
        
    def test_analyze_finds_error_spans(self, analyzer):
        """Test analysis finds error spans."""
        analysis = analyzer.analyze_trace("test_trace")
        
        assert "child2" in analysis.error_spans
        
    def test_analyze_calculates_performance_metrics(self, analyzer):
        """Test analysis calculates performance metrics."""
        analysis = analyzer.analyze_trace("test_trace")
        
        assert "avg_span_duration_ms" in analysis.performance_metrics
        assert analysis.performance_metrics["avg_span_duration_ms"] == pytest.approx(116.67, rel=0.01)
        assert analysis.performance_metrics["max_span_duration_ms"] == 200.0
        assert analysis.performance_metrics["min_span_duration_ms"] == 50.0
        
    def test_get_performance_summary_no_traces(self, analyzer):
        """Test performance summary with no recent traces."""
        # Create fresh analyzer with empty storage
        empty_storage = TraceStorage()
        empty_analyzer = TraceAnalyzer(empty_storage)
        
        result = empty_analyzer.get_performance_summary()
        assert result["message"] == "No recent traces found"


# ============================================================================
# TRACING SERVICE TESTS
# ============================================================================

class TestTracingService:
    """Tests for TracingService class."""
    
    @pytest.fixture
    def service(self):
        """Create a test tracing service."""
        return TracingService("test-service")
        
    def test_init(self, service):
        """Test service initialization."""
        assert service.service_name == "test-service"
        assert service._initialized is False
        assert isinstance(service.storage, TraceStorage)
        assert isinstance(service.collector, TracingCollector)
        assert isinstance(service.analyzer, TraceAnalyzer)
        
    def test_initialize(self, service):
        """Test service initialization."""
        service.initialize(sampling_rate=1.0)
        
        assert service._initialized is True
        assert service._tracer is not None
        
    def test_initialize_idempotent(self, service):
        """Test initialize only runs once."""
        service.initialize(sampling_rate=1.0)
        service.initialize(sampling_rate=0.5)  # Should not re-initialize
        
        assert service._initialized is True
        
    def test_get_tracer(self, service):
        """Test getting tracer auto-initializes."""
        tracer = service.get_tracer()
        assert tracer is not None
        assert service._initialized is True
        
    def test_trace_operation_context_manager(self, service):
        """Test trace_operation as context manager."""
        service.initialize(sampling_rate=1.0)
        
        with service.trace_operation("test_operation") as span:
            assert span is not None
            span.set_attribute("test", "value")
            
    def test_trace_operation_with_attributes(self, service):
        """Test trace_operation with custom attributes."""
        service.initialize(sampling_rate=1.0)
        
        with service.trace_operation("test_operation", attributes={"custom": "attr"}) as span:
            assert span is not None
            
    def test_trace_operation_handles_exception(self, service):
        """Test trace_operation handles exceptions."""
        service.initialize(sampling_rate=1.0)
        
        with pytest.raises(ValueError):
            with service.trace_operation("failing_operation"):
                raise ValueError("Test error")
                
    @pytest.mark.asyncio
    async def test_trace_async_operation(self, service):
        """Test trace_async_operation as context manager."""
        service.initialize(sampling_rate=1.0)
        
        async with service.trace_async_operation("async_operation") as span:
            assert span is not None
            
    @pytest.mark.asyncio
    async def test_trace_async_operation_with_attributes(self, service):
        """Test trace_async_operation with custom attributes."""
        service.initialize(sampling_rate=1.0)
        
        async with service.trace_async_operation("async_op", attributes={"key": "value"}) as span:
            assert span is not None
            
    @pytest.mark.asyncio
    async def test_trace_async_operation_handles_exception(self, service):
        """Test trace_async_operation handles exceptions."""
        service.initialize(sampling_rate=1.0)
        
        with pytest.raises(ValueError):
            async with service.trace_async_operation("failing_async_op"):
                raise ValueError("Async error")
                
    def test_trace_decorator_sync(self, service):
        """Test trace_decorator on sync function."""
        service.initialize(sampling_rate=1.0)
        
        @service.trace_decorator("decorated_func")
        def test_func():
            return "result"
            
        result = test_func()
        assert result == "result"
        
    @pytest.mark.asyncio
    async def test_trace_decorator_async(self, service):
        """Test trace_decorator on async function."""
        service.initialize(sampling_rate=1.0)
        
        @service.trace_decorator("decorated_async_func")
        async def test_async_func():
            return "async_result"
            
        result = await test_async_func()
        assert result == "async_result"
        
    def test_get_trace_analysis(self, service):
        """Test getting trace analysis."""
        # Add test data
        span = SpanMetrics(duration_ms=100.0, status="ok", attributes={"operation.name": "test"})
        service.storage.add_span("test_trace_123", span)
        
        analysis = service.get_trace_analysis("test_trace_123")
        assert analysis is not None
        assert analysis.trace_id == "test_trace_123"
        
    def test_get_performance_summary(self, service):
        """Test getting performance summary."""
        result = service.get_performance_summary(hours=1)
        assert isinstance(result, dict)
        
    def test_get_active_traces(self, service):
        """Test getting active traces."""
        # Add active trace
        span = SpanMetrics(duration_ms=100.0, status="ok")
        service.storage.add_span("active_trace", span)
        
        active = service.get_active_traces()
        assert "active_trace" in active
        
    def test_get_trace_stats(self, service):
        """Test getting trace statistics."""
        # Add some traces
        for i in range(3):
            span = SpanMetrics(duration_ms=100.0, status="ok")
            service.storage.add_span(f"trace_{i}", span)
            
        stats = service.get_trace_stats()
        
        assert stats["total_traces"] == 3
        assert stats["total_spans"] == 3
        assert stats["avg_spans_per_trace"] == 1.0


# ============================================================================
# GLOBAL FUNCTIONS TESTS
# ============================================================================

class TestGlobalFunctions:
    """Tests for global tracing functions."""
    
    def test_get_tracing_service_creates_singleton(self):
        """Test get_tracing_service returns singleton."""
        service1 = get_tracing_service()
        service2 = get_tracing_service()
        
        assert service1 is service2
        
    def test_initialize_tracing(self):
        """Test initialize_tracing function."""
        initialize_tracing("test-init-service", sampling_rate=1.0)
        
        service = get_tracing_service()
        assert service._initialized is True
        
    def test_trace_operation_convenience(self):
        """Test trace_operation convenience function."""
        initialize_tracing(sampling_rate=1.0)
        
        with trace_operation("convenience_op") as span:
            assert span is not None
            
    @pytest.mark.asyncio
    async def test_trace_async_operation_convenience(self):
        """Test trace_async_operation convenience function."""
        initialize_tracing(sampling_rate=1.0)
        
        async with trace_async_operation("async_convenience_op") as span:
            assert span is not None
            
    def test_trace_function_decorator_convenience(self):
        """Test trace_function convenience decorator."""
        initialize_tracing(sampling_rate=1.0)
        
        @trace_function("decorated_convenience")
        def test_func():
            return "done"
            
        result = test_func()
        assert result == "done"
        
    def test_get_current_trace_id_no_span(self):
        """Test get_current_trace_id when no active span."""
        # This might raise or return None depending on context
        # Just verify it handles the call gracefully
        try:
            result = get_current_trace_id()
            # Just verify it doesn't raise unexpectedly
            assert result is None or isinstance(result, str)
        except AttributeError:
            # NonRecordingSpan may not have context attribute
            pass
        
    def test_add_trace_event(self):
        """Test add_trace_event function."""
        initialize_tracing(sampling_rate=1.0)
        
        with trace_operation("event_test"):
            # Should not raise
            add_trace_event("test_event", {"key": "value"})
            
    def test_set_trace_attribute(self):
        """Test set_trace_attribute function."""
        initialize_tracing(sampling_rate=1.0)
        
        with trace_operation("attr_test"):
            # Should not raise
            set_trace_attribute("custom_key", "custom_value")
            set_trace_attribute("numeric_key", 42)
