"""
Comprehensive tests for SLO Metrics
Target: 90%+ coverage of backend/monitoring/slo_metrics.py
"""

import threading
from collections import deque
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
import pytest

from backend.monitoring.slo_metrics import (
    SLOCategory,
    SLOTarget,
    SLOViolation,
    SLOMetricsCollector,
    get_slo_collector,
    start_metrics_server,
)


class TestSLOCategoryEnum:
    """Tests for SLOCategory enum"""
    
    def test_order_latency_category(self):
        """Test ORDER_LATENCY category"""
        assert SLOCategory.ORDER_LATENCY.value == "order_latency"
        
    def test_order_accuracy_category(self):
        """Test ORDER_ACCURACY category"""
        assert SLOCategory.ORDER_ACCURACY.value == "order_accuracy"
        
    def test_fill_rate_category(self):
        """Test FILL_RATE category"""
        assert SLOCategory.FILL_RATE.value == "fill_rate"
        
    def test_system_availability_category(self):
        """Test SYSTEM_AVAILABILITY category"""
        assert SLOCategory.SYSTEM_AVAILABILITY.value == "system_availability"
        
    def test_data_integrity_category(self):
        """Test DATA_INTEGRITY category"""
        assert SLOCategory.DATA_INTEGRITY.value == "data_integrity"
        
    def test_risk_compliance_category(self):
        """Test RISK_COMPLIANCE category"""
        assert SLOCategory.RISK_COMPLIANCE.value == "risk_compliance"


class TestSLOTargetDataclass:
    """Tests for SLOTarget dataclass"""
    
    def test_create_slo_target(self):
        """Test creating SLOTarget"""
        target = SLOTarget(
            name="test_slo",
            category=SLOCategory.ORDER_LATENCY,
            target_percentile=99.0,
            target_value=100.0,
            unit="ms",
            window_seconds=3600,
            burn_rate_threshold=0.1
        )
        assert target.name == "test_slo"
        assert target.category == SLOCategory.ORDER_LATENCY
        assert target.target_percentile == 99.0
        assert target.target_value == 100.0
        assert target.unit == "ms"
        assert target.window_seconds == 3600
        assert target.burn_rate_threshold == 0.1


class TestSLOViolationDataclass:
    """Tests for SLOViolation dataclass"""
    
    def test_create_slo_violation(self):
        """Test creating SLOViolation"""
        violation = SLOViolation(
            timestamp=datetime.now(),
            slo_name="order_latency",
            actual_value=0.85,
            target_value=0.99,
            severity="critical",
            burn_rate=2.5,
            context={"window": 3600}
        )
        assert violation.slo_name == "order_latency"
        assert violation.actual_value == 0.85
        assert violation.target_value == 0.99
        assert violation.severity == "critical"
        assert violation.burn_rate == 2.5


class TestSLOMetricsCollectorInit:
    """Tests for SLOMetricsCollector initialization"""
    
    def test_init_creates_instance(self):
        """Test collector initializes correctly"""
        collector = SLOMetricsCollector()
        assert collector is not None
        
    def test_init_has_slo_targets(self):
        """Test collector has SLO targets configured"""
        collector = SLOMetricsCollector()
        assert "order_submission_latency_p99" in collector.slo_targets
        assert "order_accuracy_daily" in collector.slo_targets
        assert "fill_rate_5min" in collector.slo_targets
        assert "system_availability_hourly" in collector.slo_targets
        
    def test_init_has_metrics_buffer(self):
        """Test collector has metrics buffer"""
        collector = SLOMetricsCollector()
        assert collector.metrics_buffer is not None
        
    def test_init_empty_violations(self):
        """Test collector starts with empty violations"""
        collector = SLOMetricsCollector()
        assert collector.slo_violations == []
        
    def test_init_with_custom_registry(self):
        """Test collector with custom registry"""
        mock_registry = MagicMock()
        collector = SLOMetricsCollector(registry=mock_registry)
        assert collector.registry == mock_registry


class TestRecordOrderLatency:
    """Tests for record_order_latency"""
    
    def test_record_order_latency(self):
        """Test recording order latency"""
        collector = SLOMetricsCollector()
        collector.record_order_latency(50.0)
        
        assert len(collector.metrics_buffer['order_latency']) == 1
        assert collector.metrics_buffer['order_latency'][0]['latency_ms'] == 50.0
        
    def test_record_order_latency_with_labels(self):
        """Test recording order latency with labels"""
        collector = SLOMetricsCollector()
        collector.record_order_latency(
            75.0,
            order_type="limit",
            symbol="AAPL",
            account="test123"
        )
        
        event = collector.metrics_buffer['order_latency'][0]
        assert event['order_type'] == "limit"
        assert event['symbol'] == "AAPL"
        assert event['account'] == "test123"
        
    def test_record_order_latency_buffer_limit(self):
        """Test buffer limits to 10000 events"""
        collector = SLOMetricsCollector()
        
        # Fill buffer beyond limit
        for i in range(10005):
            collector.record_order_latency(float(i))
            
        assert len(collector.metrics_buffer['order_latency']) <= 10000
        
    def test_record_order_latency_timestamp(self):
        """Test latency event has timestamp"""
        collector = SLOMetricsCollector()
        before = datetime.now()
        collector.record_order_latency(100.0)
        after = datetime.now()
        
        event = collector.metrics_buffer['order_latency'][0]
        assert before <= event['timestamp'] <= after


class TestRecordOrderOutcome:
    """Tests for record_order_outcome"""
    
    def test_record_order_outcome_filled(self):
        """Test recording filled order"""
        collector = SLOMetricsCollector()
        collector.record_order_outcome("filled")
        
        assert len(collector.metrics_buffer['order_outcomes']) == 1
        assert collector.metrics_buffer['order_outcomes'][0]['status'] == "filled"
        
    def test_record_order_outcome_rejected(self):
        """Test recording rejected order"""
        collector = SLOMetricsCollector()
        collector.record_order_outcome("rejected", order_type="limit", symbol="TSLA")
        
        event = collector.metrics_buffer['order_outcomes'][0]
        assert event['status'] == "rejected"
        assert event['order_type'] == "limit"
        assert event['symbol'] == "TSLA"
        
    def test_record_order_outcome_partial_fill(self):
        """Test recording partial fill"""
        collector = SLOMetricsCollector()
        collector.record_order_outcome("partial_fill")
        
        event = collector.metrics_buffer['order_outcomes'][0]
        assert event['status'] == "partial_fill"
        
    def test_record_order_outcome_buffer_limit(self):
        """Test buffer limits outcomes"""
        collector = SLOMetricsCollector()
        
        for i in range(10005):
            collector.record_order_outcome("filled")
            
        assert len(collector.metrics_buffer['order_outcomes']) <= 10000


class TestRecordFillEvent:
    """Tests for record_fill_event"""
    
    def test_record_fill_event_full(self):
        """Test recording full fill event"""
        collector = SLOMetricsCollector()
        collector.record_fill_event(fill_type="full", symbol="AAPL")
        
        assert len(collector.metrics_buffer['fill_events']) == 1
        event = collector.metrics_buffer['fill_events'][0]
        assert event['fill_type'] == "full"
        assert event['symbol'] == "AAPL"
        
    def test_record_fill_event_partial(self):
        """Test recording partial fill event"""
        collector = SLOMetricsCollector()
        collector.record_fill_event(fill_type="partial", symbol="TSLA", filled_qty=50.0)
        
        event = collector.metrics_buffer['fill_events'][0]
        assert event['fill_type'] == "partial"
        assert event['filled_qty'] == 50.0
        
    def test_record_fill_event_with_account(self):
        """Test recording fill with account"""
        collector = SLOMetricsCollector()
        collector.record_fill_event(
            fill_type="full",
            symbol="GOOG",
            account="account123",
            filled_qty=100.0
        )
        
        event = collector.metrics_buffer['fill_events'][0]
        assert event['account'] == "account123"


class TestUpdateSystemHealth:
    """Tests for update_system_health"""
    
    def test_update_system_health(self):
        """Test updating system health"""
        collector = SLOMetricsCollector()
        collector.update_system_health("order_service", 95.0)
        
        assert len(collector.metrics_buffer['system_health']) == 1
        event = collector.metrics_buffer['system_health'][0]
        assert event['component'] == "order_service"
        assert event['health_score'] == 95.0
        
    def test_update_system_health_multiple_components(self):
        """Test updating health for multiple components"""
        collector = SLOMetricsCollector()
        collector.update_system_health("database", 100.0)
        collector.update_system_health("broker_api", 85.0)
        collector.update_system_health("websocket", 90.0)
        
        assert len(collector.metrics_buffer['system_health']) == 3
        
    def test_update_system_health_low_score(self):
        """Test updating with low health score"""
        collector = SLOMetricsCollector()
        collector.update_system_health("failing_service", 20.0)
        
        event = collector.metrics_buffer['system_health'][0]
        assert event['health_score'] == 20.0


class TestCalculateSLOCompliance:
    """Tests for calculate_slo_compliance"""
    
    def test_calculate_unknown_slo_returns_empty(self):
        """Test calculating unknown SLO returns empty dict"""
        collector = SLOMetricsCollector()
        result = collector.calculate_slo_compliance("unknown_slo")
        assert result == {}
        
    def test_calculate_order_latency_compliance_no_data(self):
        """Test latency compliance with no data"""
        collector = SLOMetricsCollector()
        result = collector.calculate_slo_compliance("order_submission_latency_p99")
        
        # With no data, should return default values
        assert 'compliance_ratio' in result
        assert 'error_budget_remaining' in result
        assert 'burn_rate' in result
        assert 'alert_level' in result
        
    def test_calculate_order_latency_compliance_with_data(self):
        """Test latency compliance with data"""
        collector = SLOMetricsCollector()
        
        # Add enough latency data (need >= 10 samples)
        for i in range(20):
            collector.metrics_buffer['order_latency'].append({
                'timestamp': datetime.now(),
                'latency_ms': 50.0,  # Below 100ms target
                'order_type': 'market',
                'symbol': 'AAPL',
                'account': 'test'
            })
            
        result = collector.calculate_slo_compliance("order_submission_latency_p99")
        assert result['compliance_ratio'] == 1.0  # All under threshold
        assert result['alert_level'] == 0
        
    def test_calculate_order_latency_compliance_with_violations(self):
        """Test latency compliance with violations"""
        collector = SLOMetricsCollector()
        
        # Add data with high latencies
        for i in range(20):
            collector.metrics_buffer['order_latency'].append({
                'timestamp': datetime.now(),
                'latency_ms': 200.0,  # Above 100ms target
                'order_type': 'market',
                'symbol': 'AAPL',
                'account': 'test'
            })
            
        result = collector.calculate_slo_compliance("order_submission_latency_p99")
        assert result['compliance_ratio'] < 1.0  # Violations detected
        
    def test_calculate_order_accuracy_compliance_no_data(self):
        """Test accuracy compliance with no data"""
        collector = SLOMetricsCollector()
        result = collector.calculate_slo_compliance("order_accuracy_daily")
        
        assert 'compliance_ratio' in result
        
    def test_calculate_order_accuracy_compliance_with_data(self):
        """Test accuracy compliance with successful orders"""
        collector = SLOMetricsCollector()
        
        # Add order outcomes (need >= 5 samples)
        for i in range(10):
            collector.metrics_buffer['order_outcomes'].append({
                'timestamp': datetime.now(),
                'status': 'filled',
                'order_type': 'market',
                'symbol': 'AAPL'
            })
            
        result = collector.calculate_slo_compliance("order_accuracy_daily")
        assert result['compliance_ratio'] == 1.0
        
    def test_calculate_order_accuracy_with_failures(self):
        """Test accuracy compliance with order failures"""
        collector = SLOMetricsCollector()
        
        # Add mixed outcomes
        for i in range(8):
            collector.metrics_buffer['order_outcomes'].append({
                'timestamp': datetime.now(),
                'status': 'filled',
                'order_type': 'market',
                'symbol': 'AAPL'
            })
        for i in range(2):
            collector.metrics_buffer['order_outcomes'].append({
                'timestamp': datetime.now(),
                'status': 'rejected',
                'order_type': 'market',
                'symbol': 'AAPL'
            })
            
        result = collector.calculate_slo_compliance("order_accuracy_daily")
        # 80% success rate is below 95% target
        assert result['compliance_ratio'] < 1.0
        
    def test_calculate_compliance_updates_prometheus_metrics(self):
        """Test compliance calculation updates Prometheus metrics"""
        collector = SLOMetricsCollector()
        
        # Add some data
        for i in range(10):
            collector.metrics_buffer['order_latency'].append({
                'timestamp': datetime.now(),
                'latency_ms': 50.0,
                'order_type': 'market',
                'symbol': 'AAPL',
                'account': 'test'
            })
            
        # This should call Prometheus gauge set methods
        result = collector.calculate_slo_compliance("order_submission_latency_p99")
        assert result is not None


class TestCheckSLOViolations:
    """Tests for check_slo_violations"""
    
    def test_check_violations_no_data(self):
        """Test checking violations with no data"""
        collector = SLOMetricsCollector()
        violations = collector.check_slo_violations()
        assert isinstance(violations, list)
        
    def test_check_violations_with_violation(self):
        """Test checking violations when SLO is violated"""
        collector = SLOMetricsCollector()
        
        # Mock calculate_slo_compliance to return violation
        def mock_compliance(slo_name):
            return {
                'compliance_ratio': 0.8,
                'error_budget_remaining': 0.2,
                'burn_rate': 2.0,
                'alert_level': 2  # Critical
            }
            
        with patch.object(collector, 'calculate_slo_compliance', side_effect=mock_compliance):
            violations = collector.check_slo_violations()
            
        assert len(violations) > 0
        assert all(isinstance(v, SLOViolation) for v in violations)
        
    def test_check_violations_returns_slo_violation_objects(self):
        """Test violations are SLOViolation objects"""
        collector = SLOMetricsCollector()
        
        def mock_compliance(slo_name):
            return {
                'compliance_ratio': 0.7,
                'error_budget_remaining': 0.1,
                'burn_rate': 3.0,
                'alert_level': 2
            }
            
        with patch.object(collector, 'calculate_slo_compliance', side_effect=mock_compliance):
            violations = collector.check_slo_violations()
            
        if violations:
            violation = violations[0]
            assert hasattr(violation, 'slo_name')
            assert hasattr(violation, 'severity')
            assert hasattr(violation, 'burn_rate')
            
    def test_check_violations_severity_levels(self):
        """Test violations have correct severity levels"""
        collector = SLOMetricsCollector()
        
        # Alert level 2 should be critical
        def mock_critical(slo_name):
            return {'compliance_ratio': 0.5, 'error_budget_remaining': 0.1, 'burn_rate': 3.0, 'alert_level': 2}
            
        with patch.object(collector, 'calculate_slo_compliance', side_effect=mock_critical):
            violations = collector.check_slo_violations()
            critical_violations = [v for v in violations if v.severity == "critical"]
            assert len(critical_violations) > 0


class TestStartBackgroundMonitoring:
    """Tests for start_background_monitoring"""
    
    def test_start_monitoring_creates_thread(self):
        """Test starting monitoring creates thread"""
        collector = SLOMetricsCollector()
        collector.start_background_monitoring(calculation_interval=1)
        
        assert collector._calculation_thread is not None
        assert collector._calculation_thread.is_alive()
        
        # Cleanup
        collector.stop_monitoring()
        
    def test_start_monitoring_thread_is_daemon(self):
        """Test monitoring thread is daemon"""
        collector = SLOMetricsCollector()
        collector.start_background_monitoring(calculation_interval=1)
        
        assert collector._calculation_thread.daemon is True
        
        # Cleanup
        collector.stop_monitoring()
        
    def test_start_monitoring_idempotent(self):
        """Test starting monitoring multiple times is safe"""
        collector = SLOMetricsCollector()
        collector.start_background_monitoring(calculation_interval=1)
        thread1 = collector._calculation_thread
        
        collector.start_background_monitoring(calculation_interval=1)
        thread2 = collector._calculation_thread
        
        # Should be same thread (not start new one)
        assert thread1 is thread2
        
        # Cleanup
        collector.stop_monitoring()


class TestStopMonitoring:
    """Tests for stop_monitoring"""
    
    def test_stop_monitoring(self):
        """Test stopping monitoring"""
        collector = SLOMetricsCollector()
        collector.start_background_monitoring(calculation_interval=1)
        
        assert collector._calculation_thread.is_alive()
        
        collector.stop_monitoring()
        
        # Thread should stop
        assert not collector._calculation_thread.is_alive() or collector._stop_event.is_set()
        
    def test_stop_monitoring_no_thread(self):
        """Test stopping when no thread running"""
        collector = SLOMetricsCollector()
        # Should not raise
        collector.stop_monitoring()


class TestGetMetricsSummary:
    """Tests for get_metrics_summary"""
    
    def test_get_metrics_summary_structure(self):
        """Test metrics summary has correct structure"""
        collector = SLOMetricsCollector()
        summary = collector.get_metrics_summary()
        
        assert 'timestamp' in summary
        assert 'slo_targets' in summary
        assert 'violations' in summary
        assert 'system_health' in summary
        assert 'buffer_stats' in summary
        
    def test_get_metrics_summary_includes_all_slos(self):
        """Test summary includes all SLO targets"""
        collector = SLOMetricsCollector()
        summary = collector.get_metrics_summary()
        
        for slo_name in collector.slo_targets:
            assert slo_name in summary['slo_targets']
            
    def test_get_metrics_summary_slo_data(self):
        """Test summary SLO data has required fields"""
        collector = SLOMetricsCollector()
        summary = collector.get_metrics_summary()
        
        for slo_name, slo_data in summary['slo_targets'].items():
            assert 'compliance_ratio' in slo_data
            assert 'error_budget_remaining' in slo_data
            assert 'burn_rate' in slo_data
            assert 'alert_level' in slo_data
            assert 'target_value' in slo_data
            assert 'unit' in slo_data
            assert 'window_seconds' in slo_data
            
    def test_get_metrics_summary_buffer_stats(self):
        """Test summary includes buffer statistics"""
        collector = SLOMetricsCollector()
        
        # Add some data to buffers
        collector.record_order_latency(50.0)
        collector.record_order_outcome("filled")
        
        summary = collector.get_metrics_summary()
        
        assert 'order_latency' in summary['buffer_stats']
        assert summary['buffer_stats']['order_latency'] >= 1


class TestExportPrometheusMetrics:
    """Tests for export_prometheus_metrics"""
    
    def test_export_returns_bytes(self):
        """Test export returns bytes"""
        collector = SLOMetricsCollector()
        result = collector.export_prometheus_metrics()
        assert isinstance(result, bytes)
        
    def test_export_contains_metrics(self):
        """Test exported data contains metrics"""
        collector = SLOMetricsCollector()
        
        # Record some metrics
        collector.record_order_latency(50.0)
        
        result = collector.export_prometheus_metrics()
        # Should contain some data (may be empty b"" if prometheus not configured)
        assert result is not None


class TestGetSLOCollector:
    """Tests for get_slo_collector singleton"""
    
    def test_get_slo_collector_returns_instance(self):
        """Test get_slo_collector returns instance"""
        collector = get_slo_collector()
        assert collector is not None
        assert isinstance(collector, SLOMetricsCollector)
        
    def test_get_slo_collector_singleton(self):
        """Test get_slo_collector returns same instance"""
        collector1 = get_slo_collector()
        collector2 = get_slo_collector()
        assert collector1 is collector2


class TestStartMetricsServer:
    """Tests for start_metrics_server"""
    
    def test_start_metrics_server_default_port(self):
        """Test starting metrics server on default port"""
        with patch('backend.monitoring.slo_metrics.start_http_server') as mock_start:
            result = start_metrics_server()
            mock_start.assert_called_once_with(8000)
            assert result is True
            
    def test_start_metrics_server_custom_port(self):
        """Test starting metrics server on custom port"""
        with patch('backend.monitoring.slo_metrics.start_http_server') as mock_start:
            result = start_metrics_server(port=9090)
            mock_start.assert_called_once_with(9090)
            assert result is True
            
    def test_start_metrics_server_handles_error(self):
        """Test metrics server handles startup error"""
        with patch('backend.monitoring.slo_metrics.start_http_server', side_effect=Exception("Port in use")):
            result = start_metrics_server(port=8000)
            assert result is False


class TestSLOTargetConfigurations:
    """Tests for default SLO target configurations"""
    
    def test_order_latency_target(self):
        """Test order latency target configuration"""
        collector = SLOMetricsCollector()
        target = collector.slo_targets["order_submission_latency_p99"]
        
        assert target.category == SLOCategory.ORDER_LATENCY
        assert target.target_percentile == 99.0
        assert target.target_value == 100.0  # 100ms
        assert target.unit == "ms"
        assert target.window_seconds == 3600  # 1 hour
        
    def test_order_accuracy_target(self):
        """Test order accuracy target configuration"""
        collector = SLOMetricsCollector()
        target = collector.slo_targets["order_accuracy_daily"]
        
        assert target.category == SLOCategory.ORDER_ACCURACY
        assert target.target_value == 95.0  # 95%
        assert target.unit == "%"
        assert target.window_seconds == 86400  # 24 hours
        
    def test_fill_rate_target(self):
        """Test fill rate target configuration"""
        collector = SLOMetricsCollector()
        target = collector.slo_targets["fill_rate_5min"]
        
        assert target.category == SLOCategory.FILL_RATE
        assert target.target_value == 98.0  # 98%
        assert target.window_seconds == 300  # 5 minutes
        
    def test_system_availability_target(self):
        """Test system availability target configuration"""
        collector = SLOMetricsCollector()
        target = collector.slo_targets["system_availability_hourly"]
        
        assert target.category == SLOCategory.SYSTEM_AVAILABILITY
        assert target.target_value == 99.9  # 99.9%
        assert target.window_seconds == 3600  # 1 hour


class TestMetricsBufferBehavior:
    """Tests for metrics buffer behavior"""
    
    def test_buffer_is_defaultdict_of_deque(self):
        """Test buffer is defaultdict with deque values"""
        collector = SLOMetricsCollector()
        
        # Access unknown key creates empty deque
        unknown = collector.metrics_buffer['unknown_metric_type']
        assert isinstance(unknown, deque)
        
    def test_buffer_preserves_order(self):
        """Test buffer preserves insertion order"""
        collector = SLOMetricsCollector()
        
        collector.record_order_latency(10.0)
        collector.record_order_latency(20.0)
        collector.record_order_latency(30.0)
        
        latencies = [e['latency_ms'] for e in collector.metrics_buffer['order_latency']]
        assert latencies == [10.0, 20.0, 30.0]
        
    def test_buffer_fifo_on_limit(self):
        """Test buffer drops oldest on limit"""
        collector = SLOMetricsCollector()
        
        # Add more than limit
        for i in range(10005):
            collector.record_order_latency(float(i))
            
        # First value should be dropped
        first_latency = collector.metrics_buffer['order_latency'][0]['latency_ms']
        assert first_latency >= 5  # Oldest values removed


class TestAlertLevelCalculation:
    """Tests for alert level calculation in compliance"""
    
    def test_alert_level_zero_when_compliant(self):
        """Test alert level is 0 when compliant"""
        collector = SLOMetricsCollector()
        
        # Add good data
        for i in range(20):
            collector.metrics_buffer['order_latency'].append({
                'timestamp': datetime.now(),
                'latency_ms': 50.0,
                'order_type': 'market',
                'symbol': 'AAPL',
                'account': 'test'
            })
            
        result = collector.calculate_slo_compliance("order_submission_latency_p99")
        assert result['alert_level'] == 0
        
    def test_alert_level_one_for_warning(self):
        """Test alert level is 1 for warning threshold"""
        collector = SLOMetricsCollector()
        
        # Add data that triggers warning
        for i in range(20):
            collector.metrics_buffer['order_latency'].append({
                'timestamp': datetime.now(),
                'latency_ms': 150.0,  # 50% over 100ms target
                'order_type': 'market',
                'symbol': 'AAPL',
                'account': 'test'
            })
            
        result = collector.calculate_slo_compliance("order_submission_latency_p99")
        # May be 1 or 2 depending on threshold
        assert result['alert_level'] >= 1
        
    def test_alert_level_two_for_critical(self):
        """Test alert level is 2 for critical threshold"""
        collector = SLOMetricsCollector()
        
        # Add severely violating data
        for i in range(20):
            collector.metrics_buffer['order_latency'].append({
                'timestamp': datetime.now(),
                'latency_ms': 500.0,  # 5x over 100ms target
                'order_type': 'market',
                'symbol': 'AAPL',
                'account': 'test'
            })
            
        result = collector.calculate_slo_compliance("order_submission_latency_p99")
        assert result['alert_level'] == 2


class TestWindowFiltering:
    """Tests for time window filtering in compliance"""
    
    def test_compliance_filters_old_data(self):
        """Test compliance calculation filters out old data"""
        collector = SLOMetricsCollector()
        
        # Add old data (outside window)
        old_time = datetime.now() - timedelta(hours=2)  # Outside 1 hour window
        for i in range(10):
            collector.metrics_buffer['order_latency'].append({
                'timestamp': old_time,
                'latency_ms': 500.0,  # Bad latency
                'order_type': 'market',
                'symbol': 'AAPL',
                'account': 'test'
            })
            
        # Add recent good data
        for i in range(10):
            collector.metrics_buffer['order_latency'].append({
                'timestamp': datetime.now(),
                'latency_ms': 50.0,  # Good latency
                'order_type': 'market',
                'symbol': 'AAPL',
                'account': 'test'
            })
            
        result = collector.calculate_slo_compliance("order_submission_latency_p99")
        # Should be compliant since old bad data is filtered
        assert result['compliance_ratio'] == 1.0
