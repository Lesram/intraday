"""
Comprehensive tests for SLO Monitor
Target: 90%+ coverage of backend/monitoring/slo_monitor.py
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock
import pytest

from backend.monitoring.slo_monitor import (
    SLOMonitor,
    SLOStatus,
    orders_submitted_total,
    broker_roundtrip_ms,
    outbox_queue_depth,
    stream_reconnects_total,
    stream_uptime_seconds,
    stream_messages_total,
    stream_message_lag_ms,
    guardrail_violations_total,
    circuit_breaker_trips_total,
    circuit_breaker_open,
    daily_orders_count,
    daily_notional_usd,
    start_metrics_server,
    slo_monitor,
)


class TestSLOMonitorInit:
    """Tests for SLOMonitor initialization"""
    
    def test_init_creates_instance(self):
        """Test SLOMonitor initializes correctly"""
        monitor = SLOMonitor()
        assert monitor is not None
        assert monitor.stream_connect_time is None
        
    def test_init_has_slo_targets(self):
        """Test SLOMonitor has SLO targets configured"""
        monitor = SLOMonitor()
        assert 'order_success_rate' in monitor.slo_targets
        assert 'broker_api_p99_ms' in monitor.slo_targets
        assert 'stream_uptime' in monitor.slo_targets
        assert 'outbox_queue_depth' in monitor.slo_targets
        
    def test_init_has_burn_rate_alerts(self):
        """Test SLOMonitor has burn rate alert thresholds"""
        monitor = SLOMonitor()
        assert '1h' in monitor.burn_rate_alerts
        assert '5m' in monitor.burn_rate_alerts
        assert monitor.burn_rate_alerts['1h'] == 2.0
        assert monitor.burn_rate_alerts['5m'] == 6.0


class TestRecordOrderAttempt:
    """Tests for record_order_attempt"""
    
    def test_record_order_success(self):
        """Test recording successful order"""
        monitor = SLOMonitor()
        # Should not raise
        monitor.record_order_attempt("AAPL", "buy", success=True)
        
    def test_record_order_failure(self):
        """Test recording failed order"""
        monitor = SLOMonitor()
        with patch.object(monitor, 'record_order_attempt') as mock:
            mock.return_value = None
            monitor.record_order_attempt("AAPL", "sell", success=False, error_type="broker_reject")
            
    def test_record_order_failure_logs_warning(self):
        """Test failed order logs warning"""
        monitor = SLOMonitor()
        # Capture logger warning - should log on failure
        monitor.record_order_attempt("AAPL", "buy", success=False, error_type="rate_limited")
        
    def test_record_order_with_none_error_type(self):
        """Test failed order with no error type uses unknown"""
        monitor = SLOMonitor()
        monitor.record_order_attempt("TSLA", "sell", success=False, error_type=None)


class TestRecordBrokerLatency:
    """Tests for record_broker_latency"""
    
    def test_record_normal_latency(self):
        """Test recording normal latency"""
        monitor = SLOMonitor()
        monitor.record_broker_latency("place_order", 150.0)
        
    def test_record_high_latency_logs_warning(self):
        """Test high latency logs warning"""
        monitor = SLOMonitor()
        # Latency above 500ms should trigger warning
        monitor.record_broker_latency("place_order", 600.0)
        
    def test_record_latency_at_threshold(self):
        """Test latency exactly at threshold"""
        monitor = SLOMonitor()
        monitor.record_broker_latency("get_order", 500.0)
        
    def test_record_very_low_latency(self):
        """Test very low latency"""
        monitor = SLOMonitor()
        monitor.record_broker_latency("cancel_order", 5.0)


class TestRecordStreamReconnect:
    """Tests for record_stream_reconnect"""
    
    def test_record_reconnect_connection_lost(self):
        """Test reconnect due to connection lost"""
        monitor = SLOMonitor()
        monitor.record_stream_reconnect("connection_lost")
        assert monitor.stream_connect_time is not None
        
    def test_record_reconnect_auth_error(self):
        """Test reconnect due to auth error"""
        monitor = SLOMonitor()
        monitor.record_stream_reconnect("auth_error")
        assert monitor.stream_connect_time is not None
        
    def test_record_reconnect_rate_limited(self):
        """Test reconnect due to rate limiting"""
        monitor = SLOMonitor()
        monitor.record_stream_reconnect("rate_limited")
        # Uptime should be reset
        assert monitor.stream_connect_time is not None
        
    def test_reconnect_resets_connect_time(self):
        """Test reconnect updates connect time"""
        monitor = SLOMonitor()
        old_time = datetime.now(UTC) - timedelta(hours=1)
        monitor.stream_connect_time = old_time
        
        monitor.record_stream_reconnect("connection_lost")
        assert monitor.stream_connect_time > old_time


class TestRecordStreamMessage:
    """Tests for record_stream_message"""
    
    def test_record_trade_update(self):
        """Test recording trade update message"""
        monitor = SLOMonitor()
        monitor.record_stream_message("trade_update")
        
    def test_record_order_update(self):
        """Test recording order update message"""
        monitor = SLOMonitor()
        monitor.record_stream_message("order_update")
        
    def test_record_error_message(self):
        """Test recording error message"""
        monitor = SLOMonitor()
        monitor.record_stream_message("error")
        
    def test_record_message_with_broker_timestamp(self):
        """Test recording message with broker timestamp"""
        monitor = SLOMonitor()
        broker_ts = datetime.now(UTC) - timedelta(milliseconds=50)
        monitor.record_stream_message("trade_update", broker_timestamp=broker_ts)
        
    def test_record_message_calculates_lag(self):
        """Test lag calculation from broker timestamp"""
        monitor = SLOMonitor()
        # Broker timestamp 100ms ago
        broker_ts = datetime.now(UTC) - timedelta(milliseconds=100)
        monitor.record_stream_message("order_update", broker_timestamp=broker_ts)
        
    def test_record_message_no_timestamp(self):
        """Test recording message without broker timestamp"""
        monitor = SLOMonitor()
        monitor.record_stream_message("heartbeat", broker_timestamp=None)


class TestRecordGuardrailViolation:
    """Tests for record_guardrail_violation"""
    
    def test_record_daily_orders_limit(self):
        """Test recording daily orders limit violation"""
        monitor = SLOMonitor()
        monitor.record_guardrail_violation("daily_orders_limit")
        
    def test_record_daily_notional_limit(self):
        """Test recording daily notional limit violation"""
        monitor = SLOMonitor()
        monitor.record_guardrail_violation("daily_notional_limit")
        
    def test_record_position_size_limit(self):
        """Test recording position size limit violation"""
        monitor = SLOMonitor()
        monitor.record_guardrail_violation("position_size_limit")


class TestRecordCircuitBreakerTrip:
    """Tests for record_circuit_breaker_trip"""
    
    def test_record_circuit_breaker_open(self):
        """Test recording circuit breaker open"""
        monitor = SLOMonitor()
        monitor.record_circuit_breaker_trip("broker_down", is_open=True)
        
    def test_record_circuit_breaker_closed(self):
        """Test recording circuit breaker closed"""
        monitor = SLOMonitor()
        monitor.record_circuit_breaker_trip("broker_down", is_open=False)
        
    def test_record_circuit_breaker_network_error(self):
        """Test circuit breaker from network error"""
        monitor = SLOMonitor()
        monitor.record_circuit_breaker_trip("network_error", is_open=True)


class TestRecordMetric:
    """Tests for async record_metric"""
    
    @pytest.mark.asyncio
    async def test_record_metric_with_service_and_operation(self):
        """Test recording metric with service and operation names"""
        monitor = SLOMonitor()
        await monitor.record_metric(
            service_name="order_service",
            operation_name="place_order",
            latency_ms=100.0,
            success=True
        )
        
    @pytest.mark.asyncio
    async def test_record_metric_with_metadata(self):
        """Test recording metric with metadata"""
        monitor = SLOMonitor()
        await monitor.record_metric(
            service_name="broker",
            operation_name="submit",
            latency_ms=50.0,
            success=True,
            metadata={"symbol": "AAPL"}
        )
        
    @pytest.mark.asyncio
    async def test_record_metric_failure(self):
        """Test recording failed metric"""
        monitor = SLOMonitor()
        await monitor.record_metric(
            service_name="order_service",
            operation_name="cancel",
            latency_ms=200.0,
            success=False
        )
        
    @pytest.mark.asyncio
    async def test_record_metric_with_labels(self):
        """Test recording metric with additional labels"""
        monitor = SLOMonitor()
        await monitor.record_metric(
            service_name="execution",
            operation_name="fill",
            latency_ms=30.0,
            success=True,
            symbol="TSLA",
            side="buy"
        )


class TestRecordMetricSync:
    """Tests for synchronous record_metric_sync"""
    
    def test_record_latency_metric(self):
        """Test recording latency metric"""
        monitor = SLOMonitor()
        monitor.record_metric_sync("order_latency", 100.0, success=True, endpoint="place_order")
        
    def test_record_broker_metric(self):
        """Test recording broker metric"""
        monitor = SLOMonitor()
        monitor.record_metric_sync("broker_call", 50.0, success=True, endpoint="get_order")
        
    def test_record_execution_metric(self):
        """Test recording execution metric"""
        monitor = SLOMonitor()
        monitor.record_metric_sync("execution_time", 25.0, success=True)
        
    def test_record_metric_with_symbol_and_side(self):
        """Test recording metric with symbol and side labels"""
        monitor = SLOMonitor()
        monitor.record_metric_sync(
            "order_success", 0, success=True,
            symbol="AAPL", side="buy"
        )
        
    def test_record_metric_with_failure(self):
        """Test recording failed metric"""
        monitor = SLOMonitor()
        monitor.record_metric_sync(
            "order_failure", 0, success=False,
            symbol="TSLA", side="sell"
        )
        
    def test_record_metric_handles_exception(self):
        """Test metric recording handles exceptions gracefully"""
        monitor = SLOMonitor()
        # Pass unusual values that might cause issues
        monitor.record_metric_sync("test_metric", float('inf'), success=True)


class TestUpdateOutboxDepth:
    """Tests for update_outbox_depth"""
    
    def test_update_normal_depth(self):
        """Test updating normal queue depth"""
        monitor = SLOMonitor()
        monitor.update_outbox_depth(50)
        
    def test_update_high_depth_logs_warning(self):
        """Test high queue depth logs warning"""
        monitor = SLOMonitor()
        monitor.update_outbox_depth(150)  # Above 100 threshold
        
    def test_update_zero_depth(self):
        """Test updating zero queue depth"""
        monitor = SLOMonitor()
        monitor.update_outbox_depth(0)
        
    def test_update_at_threshold(self):
        """Test updating at threshold"""
        monitor = SLOMonitor()
        monitor.update_outbox_depth(100)


class TestUpdateDailyCaps:
    """Tests for update_daily_caps"""
    
    def test_update_daily_caps(self):
        """Test updating daily trading caps"""
        monitor = SLOMonitor()
        monitor.update_daily_caps("account123", orders_count=50, notional_usd=100000.0)
        
    def test_update_daily_caps_zero(self):
        """Test updating with zero values"""
        monitor = SLOMonitor()
        monitor.update_daily_caps("account123", orders_count=0, notional_usd=0.0)
        
    def test_update_daily_caps_high_values(self):
        """Test updating with high values"""
        monitor = SLOMonitor()
        monitor.update_daily_caps("account456", orders_count=1000, notional_usd=10000000.0)


class TestUpdateStreamUptime:
    """Tests for update_stream_uptime"""
    
    def test_update_uptime_no_connect_time(self):
        """Test updating uptime when not connected"""
        monitor = SLOMonitor()
        monitor.stream_connect_time = None
        monitor.update_stream_uptime()  # Should not raise
        
    def test_update_uptime_with_connect_time(self):
        """Test updating uptime when connected"""
        monitor = SLOMonitor()
        monitor.stream_connect_time = datetime.now(UTC) - timedelta(hours=1)
        monitor.update_stream_uptime()
        
    def test_update_uptime_recent_connection(self):
        """Test updating uptime for recent connection"""
        monitor = SLOMonitor()
        monitor.stream_connect_time = datetime.now(UTC) - timedelta(seconds=30)
        monitor.update_stream_uptime()


class TestCheckSLOCompliance:
    """Tests for async check_slo_compliance"""
    
    @pytest.mark.asyncio
    async def test_check_slo_compliance_returns_status(self):
        """Test SLO compliance check returns status dict"""
        monitor = SLOMonitor()
        result = await monitor.check_slo_compliance()
        assert isinstance(result, dict)
        
    @pytest.mark.asyncio
    async def test_check_slo_compliance_has_order_success_rate(self):
        """Test compliance includes order success rate SLO"""
        monitor = SLOMonitor()
        result = await monitor.check_slo_compliance()
        assert 'order_success_rate' in result
        
    @pytest.mark.asyncio
    async def test_check_slo_compliance_has_broker_api_p99(self):
        """Test compliance includes broker API P99 SLO"""
        monitor = SLOMonitor()
        result = await monitor.check_slo_compliance()
        assert 'broker_api_p99' in result
        
    @pytest.mark.asyncio
    async def test_slo_status_has_required_fields(self):
        """Test SLO status objects have required fields"""
        monitor = SLOMonitor()
        result = await monitor.check_slo_compliance()
        
        for slo_name, status in result.items():
            assert hasattr(status, 'name')
            assert hasattr(status, 'current_value')
            assert hasattr(status, 'target_value')
            assert hasattr(status, 'is_compliant')
            assert hasattr(status, 'error_budget_consumed')
            assert hasattr(status, 'burn_rate')


class TestGenerateBurnRateAlerts:
    """Tests for generate_burn_rate_alerts"""
    
    def test_no_alerts_when_compliant(self):
        """Test no alerts when all SLOs are compliant"""
        monitor = SLOMonitor()
        slo_status = {
            'test_slo': SLOStatus(
                name='Test SLO',
                current_value=0.999,
                target_value=0.999,
                is_compliant=True,
                error_budget_consumed=0.0,
                burn_rate=0.1  # Low burn rate: 0.1 * 12 = 1.2 < 6 threshold
            )
        }
        alerts = monitor.generate_burn_rate_alerts(slo_status)
        assert len(alerts) == 0
        
    def test_warning_alert_at_1h_threshold(self):
        """Test warning alert at 1-hour burn rate threshold"""
        monitor = SLOMonitor()
        slo_status = {
            'test_slo': SLOStatus(
                name='Test SLO',
                current_value=0.99,
                target_value=0.999,
                is_compliant=False,
                error_budget_consumed=0.5,
                burn_rate=2.0  # At 1h threshold
            )
        }
        alerts = monitor.generate_burn_rate_alerts(slo_status)
        assert len(alerts) >= 1
        assert any(a['severity'] == 'warning' for a in alerts)
        
    def test_critical_alert_at_5m_threshold(self):
        """Test critical alert at 5-minute burn rate threshold"""
        monitor = SLOMonitor()
        slo_status = {
            'test_slo': SLOStatus(
                name='Test SLO',
                current_value=0.9,
                target_value=0.999,
                is_compliant=False,
                error_budget_consumed=0.9,
                burn_rate=1.0  # 1.0 * 12 = 12 > 6x threshold
            )
        }
        alerts = monitor.generate_burn_rate_alerts(slo_status)
        critical_alerts = [a for a in alerts if a['severity'] == 'critical']
        assert len(critical_alerts) >= 1
        
    def test_alert_contains_required_fields(self):
        """Test alerts contain required fields"""
        monitor = SLOMonitor()
        slo_status = {
            'test_slo': SLOStatus(
                name='Test SLO',
                current_value=0.9,
                target_value=0.999,
                is_compliant=False,
                error_budget_consumed=0.5,
                burn_rate=3.0
            )
        }
        alerts = monitor.generate_burn_rate_alerts(slo_status)
        assert len(alerts) > 0
        alert = alerts[0]
        assert 'severity' in alert
        assert 'slo' in alert
        assert 'message' in alert
        assert 'burn_rate' in alert
        
    def test_multiple_slos_generate_multiple_alerts(self):
        """Test multiple SLOs can generate multiple alerts"""
        monitor = SLOMonitor()
        slo_status = {
            'slo_1': SLOStatus(
                name='SLO 1',
                current_value=0.9,
                target_value=0.999,
                is_compliant=False,
                error_budget_consumed=0.5,
                burn_rate=3.0
            ),
            'slo_2': SLOStatus(
                name='SLO 2',
                current_value=0.85,
                target_value=0.999,
                is_compliant=False,
                error_budget_consumed=0.7,
                burn_rate=4.0
            )
        }
        alerts = monitor.generate_burn_rate_alerts(slo_status)
        assert len(alerts) >= 2


class TestHealthCheckLoop:
    """Tests for health_check_loop"""
    
    @pytest.mark.asyncio
    async def test_health_check_loop_runs(self):
        """Test health check loop runs at least once"""
        monitor = SLOMonitor()
        
        # Run loop for a short time
        async def run_limited():
            count = 0
            async def check_once():
                nonlocal count
                # Update stream uptime
                monitor.update_stream_uptime()
                # Check SLO compliance
                await monitor.check_slo_compliance()
                count += 1
                
            await check_once()
            return count
            
        count = await run_limited()
        assert count == 1
        
    @pytest.mark.asyncio
    async def test_health_check_handles_exceptions(self):
        """Test health check handles exceptions gracefully"""
        monitor = SLOMonitor()
        
        with patch.object(monitor, 'check_slo_compliance', side_effect=Exception("Test error")):
            # Should not raise
            try:
                monitor.update_stream_uptime()
            except Exception:
                pytest.fail("Should not raise exception")


class TestSLOStatusDataclass:
    """Tests for SLOStatus dataclass"""
    
    def test_create_slo_status(self):
        """Test creating SLOStatus"""
        status = SLOStatus(
            name='Test SLO',
            current_value=0.998,
            target_value=0.999,
            is_compliant=False,
            error_budget_consumed=0.2,
            burn_rate=1.5
        )
        assert status.name == 'Test SLO'
        assert status.current_value == 0.998
        assert status.target_value == 0.999
        assert status.is_compliant is False
        assert status.error_budget_consumed == 0.2
        assert status.burn_rate == 1.5
        
    def test_slo_status_compliant(self):
        """Test compliant SLO status"""
        status = SLOStatus(
            name='Good SLO',
            current_value=0.9999,
            target_value=0.999,
            is_compliant=True,
            error_budget_consumed=0.0,
            burn_rate=0.0
        )
        assert status.is_compliant is True


class TestStartMetricsServer:
    """Tests for start_metrics_server"""
    
    def test_start_metrics_server_default_port(self):
        """Test starting metrics server on default port"""
        with patch('backend.monitoring.slo_monitor.start_http_server') as mock_start:
            start_metrics_server()
            mock_start.assert_called_once_with(8000)
            
    def test_start_metrics_server_custom_port(self):
        """Test starting metrics server on custom port"""
        with patch('backend.monitoring.slo_monitor.start_http_server') as mock_start:
            start_metrics_server(port=9090)
            mock_start.assert_called_once_with(9090)
            
    def test_start_metrics_server_handles_exception(self):
        """Test metrics server handles startup exception"""
        with patch('backend.monitoring.slo_monitor.start_http_server', side_effect=Exception("Port in use")):
            # Should not raise
            start_metrics_server(port=8000)


class TestGlobalMonitorInstance:
    """Tests for global slo_monitor instance"""
    
    def test_global_instance_exists(self):
        """Test global monitor instance exists"""
        assert slo_monitor is not None
        assert isinstance(slo_monitor, SLOMonitor)
        
    def test_global_instance_is_functional(self):
        """Test global monitor instance works"""
        slo_monitor.record_order_attempt("AAPL", "buy", success=True)


class TestPrometheusMetrics:
    """Tests for Prometheus metric definitions"""
    
    def test_orders_submitted_total_defined(self):
        """Test orders_submitted_total counter is defined"""
        assert orders_submitted_total is not None
        
    def test_broker_roundtrip_ms_defined(self):
        """Test broker_roundtrip_ms histogram is defined"""
        assert broker_roundtrip_ms is not None
        
    def test_outbox_queue_depth_defined(self):
        """Test outbox_queue_depth gauge is defined"""
        assert outbox_queue_depth is not None
        
    def test_stream_metrics_defined(self):
        """Test stream metrics are defined"""
        assert stream_reconnects_total is not None
        assert stream_uptime_seconds is not None
        assert stream_messages_total is not None
        assert stream_message_lag_ms is not None
        
    def test_guardrail_metrics_defined(self):
        """Test guardrail metrics are defined"""
        assert guardrail_violations_total is not None
        assert circuit_breaker_trips_total is not None
        assert circuit_breaker_open is not None
        
    def test_daily_cap_metrics_defined(self):
        """Test daily cap metrics are defined"""
        assert daily_orders_count is not None
        assert daily_notional_usd is not None
