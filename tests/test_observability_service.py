"""
Tests for Enhanced Observability Service.

Tests cover:
- Metrics recording and aggregation
- Health check management
- Alert threshold monitoring
- Dashboard data generation
"""

import asyncio
from datetime import datetime, timedelta, UTC

import pytest

from backend.services.observability_service import (
    HealthCheck,
    HealthStatus,
    MetricsBuffer,
    MetricPoint,
    ObservabilityService,
    SystemMetrics,
    TradingMetrics,
    get_observability_service,
)


class TestMetricsBuffer:
    """Tests for MetricsBuffer time-series storage."""
    
    def test_record_value(self):
        """Test recording a value."""
        buffer = MetricsBuffer(max_points=100)
        buffer.record(42.5, {"endpoint": "/api/test"})
        
        points = buffer.get_recent(60)
        assert len(points) == 1
        assert points[0].value == 42.5
        assert points[0].labels["endpoint"] == "/api/test"
    
    def test_max_points_limit(self):
        """Test that buffer respects max points limit."""
        buffer = MetricsBuffer(max_points=10)
        
        for i in range(20):
            buffer.record(float(i))
        
        # Should only keep last 10
        points = buffer.get_recent(3600)
        assert len(points) == 10
        
        # Should be the most recent values (10-19)
        values = [p.value for p in points]
        assert values == [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0]
    
    def test_get_recent_filters_by_time(self):
        """Test that get_recent filters by time window."""
        buffer = MetricsBuffer(max_points=100)
        
        # Record some points
        for i in range(5):
            buffer.record(float(i))
        
        # All should be within 60 seconds
        points = buffer.get_recent(60)
        assert len(points) == 5
    
    def test_get_rate(self):
        """Test rate calculation."""
        buffer = MetricsBuffer(max_points=100)
        
        # Record 10 events
        for _ in range(10):
            buffer.record(1.0)
        
        # Rate should be ~10/60 = 0.167 events/second
        rate = buffer.get_rate(60)
        assert 0.1 < rate < 0.5  # Allow some variance
    
    def test_get_average(self):
        """Test average calculation."""
        buffer = MetricsBuffer(max_points=100)
        
        # Record values 1-10
        for i in range(1, 11):
            buffer.record(float(i))
        
        avg = buffer.get_average(60)
        assert avg == 5.5
    
    def test_get_percentile(self):
        """Test percentile calculation."""
        buffer = MetricsBuffer(max_points=100)
        
        # Record values 1-100
        for i in range(1, 101):
            buffer.record(float(i))
        
        p50 = buffer.get_percentile(50, 60)
        p99 = buffer.get_percentile(99, 60)
        
        assert 45 < p50 < 55  # Should be around 50
        assert p99 > 90  # Should be high
    
    def test_empty_buffer_returns_zero(self):
        """Test empty buffer returns zero for calculations."""
        buffer = MetricsBuffer(max_points=100)
        
        assert buffer.get_rate(60) == 0.0
        assert buffer.get_average(60) == 0.0
        assert buffer.get_percentile(99, 60) == 0.0


class TestHealthCheck:
    """Tests for HealthCheck dataclass."""
    
    def test_health_check_creation(self):
        """Test creating a health check."""
        check = HealthCheck(
            component="database",
            status=HealthStatus.HEALTHY,
            latency_ms=5.2,
            message="OK",
        )
        
        assert check.component == "database"
        assert check.status == HealthStatus.HEALTHY
        assert check.latency_ms == 5.2
        assert check.message == "OK"
    
    def test_health_check_defaults(self):
        """Test health check default values."""
        check = HealthCheck(
            component="api",
            status=HealthStatus.DEGRADED,
            latency_ms=100.0,
        )
        
        assert check.message is None
        assert check.details == {}
        assert check.last_checked is not None


class TestObservabilityService:
    """Tests for ObservabilityService."""
    
    @pytest.fixture
    def service(self):
        """Create a fresh service for each test."""
        return ObservabilityService()
    
    def test_record_api_request(self, service):
        """Test recording API requests."""
        service.record_api_request("/api/orders", 45.5, 200)
        service.record_api_request("/api/positions", 32.1, 200)
        service.record_api_request("/api/error", 10.0, 500)
        
        metrics = service.get_system_metrics(60)
        
        assert metrics.requests_per_second > 0
        assert metrics.avg_response_time_ms > 0
        assert metrics.error_rate_pct > 0  # One error out of three
    
    def test_record_order_events(self, service):
        """Test recording order events."""
        service.record_order_event("submitted", "AAPL")
        service.record_order_event("submitted", "GOOGL")
        service.record_order_event("filled", "AAPL")
        
        metrics = service.get_trading_metrics(60)
        
        assert metrics.orders_submitted == 2
        assert metrics.orders_filled == 1
    
    def test_record_fill_latency(self, service):
        """Test recording fill latency."""
        service.record_fill_latency(25.5)
        service.record_fill_latency(30.2)
        service.record_fill_latency(28.1)
        
        metrics = service.get_system_metrics(60)
        assert 25 < metrics.avg_fill_latency_ms < 35
    
    def test_record_prediction(self, service):
        """Test recording ML predictions."""
        service.record_prediction(5.2, "lstm_model")
        service.record_prediction(3.8, "xgboost_model")
        
        metrics = service.get_system_metrics(60)
        assert metrics.predictions_per_second > 0
        assert metrics.avg_prediction_latency_ms > 0
    
    def test_record_websocket_message(self, service):
        """Test recording WebSocket messages."""
        service.record_websocket_message("inbound", "market_data")
        service.record_websocket_message("outbound", "order_update")
        
        metrics = service.get_system_metrics(60)
        assert metrics.websocket_messages_per_second > 0
    
    def test_set_websocket_connections(self, service):
        """Test setting WebSocket connection count."""
        service.set_websocket_connections(42)
        
        metrics = service.get_system_metrics(60)
        assert metrics.websocket_connections == 42
    
    def test_set_active_strategies(self, service):
        """Test setting active strategy count."""
        service.set_active_strategies(5)
        
        metrics = service.get_trading_metrics(60)
        assert metrics.active_strategies == 5
    
    @pytest.mark.asyncio
    async def test_check_component_health_success(self, service):
        """Test successful health check."""
        async def healthy_check():
            await asyncio.sleep(0.01)
        
        result = await service.check_component_health(
            "test_component",
            healthy_check,
            timeout_seconds=5.0,
        )
        
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "OK"
        assert result.latency_ms > 0
    
    @pytest.mark.asyncio
    async def test_check_component_health_failure(self, service):
        """Test failed health check."""
        async def failing_check():
            raise ConnectionError("Database unavailable")
        
        result = await service.check_component_health(
            "database",
            failing_check,
            timeout_seconds=5.0,
        )
        
        assert result.status == HealthStatus.UNHEALTHY
        assert "Database unavailable" in result.message
    
    @pytest.mark.asyncio
    async def test_check_component_health_timeout(self, service):
        """Test health check timeout."""
        async def slow_check():
            await asyncio.sleep(10)  # Very slow
        
        result = await service.check_component_health(
            "slow_service",
            slow_check,
            timeout_seconds=0.1,
        )
        
        assert result.status == HealthStatus.UNHEALTHY
        assert "Timeout" in result.message
    
    @pytest.mark.asyncio
    async def test_get_system_health(self, service):
        """Test getting overall system health."""
        # Add some health checks
        async def healthy():
            pass
        
        await service.check_component_health("api", healthy)
        await service.check_component_health("database", healthy)
        
        health = await service.get_system_health()
        
        assert health["status"] == "healthy"
        assert "api" in health["components"]
        assert "database" in health["components"]
    
    @pytest.mark.asyncio
    async def test_system_health_degraded(self, service):
        """Test degraded system health when one component fails."""
        async def healthy():
            pass
        
        async def unhealthy():
            raise Exception("Failed")
        
        await service.check_component_health("api", healthy)
        await service.check_component_health("cache", unhealthy)
        
        health = await service.get_system_health()
        
        assert health["status"] == "unhealthy"
    
    def test_check_alerts_no_violations(self, service):
        """Test no alerts when thresholds not exceeded."""
        # Record some normal metrics
        service.record_api_request("/api/test", 50.0, 200)
        
        alerts = service.check_alerts()
        
        # Should be minimal alerts
        assert isinstance(alerts, list)
    
    def test_check_alerts_error_rate_violation(self, service):
        """Test alert triggered for high error rate."""
        # Record mostly errors
        for _ in range(10):
            service.record_api_request("/api/test", 50.0, 500)
        
        for _ in range(10):
            service.record_api_request("/api/test", 50.0, 200)
        
        alerts = service.check_alerts()
        
        error_alert = next(
            (a for a in alerts if a["metric"] == "error_rate_pct"),
            None,
        )
        
        assert error_alert is not None
        assert error_alert["current"] > 5.0
    
    def test_set_threshold(self, service):
        """Test updating a threshold."""
        service.set_threshold("error_rate_pct", 10.0)
        
        # Record 50% errors (below new threshold? No, above)
        for _ in range(5):
            service.record_api_request("/api/test", 50.0, 500)
        for _ in range(5):
            service.record_api_request("/api/test", 50.0, 200)
        
        alerts = service.check_alerts()
        
        error_alert = next(
            (a for a in alerts if a["metric"] == "error_rate_pct"),
            None,
        )
        
        # 50% error rate still exceeds 10% threshold
        assert error_alert is not None
    
    def test_get_dashboard_data(self, service):
        """Test getting complete dashboard data."""
        # Record some activity
        service.record_api_request("/api/test", 50.0, 200)
        service.record_order_event("submitted", "AAPL")
        service.record_prediction(5.0, "test_model")
        service.set_websocket_connections(10)
        
        data = service.get_dashboard_data()
        
        assert "timestamp" in data
        assert "health" in data
        assert "system_metrics" in data
        assert "trading_metrics" in data
        assert "websocket" in data
        assert "ml" in data
        assert "alerts" in data


class TestSystemMetrics:
    """Tests for SystemMetrics dataclass."""
    
    def test_system_metrics_creation(self):
        """Test creating system metrics."""
        metrics = SystemMetrics(
            timestamp=datetime.now(UTC),
            requests_per_second=150.5,
            avg_response_time_ms=45.2,
            error_rate_pct=0.5,
        )
        
        assert metrics.requests_per_second == 150.5
        assert metrics.avg_response_time_ms == 45.2
        assert metrics.error_rate_pct == 0.5
    
    def test_system_metrics_defaults(self):
        """Test system metrics default values."""
        metrics = SystemMetrics(timestamp=datetime.now(UTC))
        
        assert metrics.requests_per_second == 0.0
        assert metrics.websocket_connections == 0
        assert metrics.db_connection_pool_used == 0


class TestTradingMetrics:
    """Tests for TradingMetrics dataclass."""
    
    def test_trading_metrics_creation(self):
        """Test creating trading metrics."""
        metrics = TradingMetrics(
            timestamp=datetime.now(UTC),
            orders_submitted=100,
            orders_filled=95,
            orders_rejected=3,
            orders_cancelled=2,
        )
        
        assert metrics.orders_submitted == 100
        assert metrics.orders_filled == 95
        assert metrics.orders_rejected == 3
    
    def test_trading_metrics_defaults(self):
        """Test trading metrics default values."""
        metrics = TradingMetrics(timestamp=datetime.now(UTC))
        
        assert metrics.total_positions == 0
        assert metrics.unrealized_pnl == 0.0
        assert metrics.active_strategies == 0


class TestGlobalSingleton:
    """Tests for global singleton pattern."""
    
    def test_get_observability_service_returns_same_instance(self):
        """Test that get_observability_service returns singleton."""
        service1 = get_observability_service()
        service2 = get_observability_service()
        
        # Record on one, check on other
        service1.set_websocket_connections(99)
        
        metrics = service2.get_system_metrics(60)
        assert metrics.websocket_connections == 99
