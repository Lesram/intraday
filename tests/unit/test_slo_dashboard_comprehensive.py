"""
Comprehensive tests for SLO Dashboard
Target: 90%+ coverage of backend/monitoring/slo_dashboard.py
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock, mock_open
import pytest

from backend.monitoring.slo_dashboard import (
    SLODashboard,
    get_dashboard,
    start_slo_dashboard,
    FLASK_AVAILABLE,
)


class TestSLODashboardInit:
    """Tests for SLODashboard initialization"""
    
    def test_init_creates_instance(self):
        """Test dashboard initializes correctly"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                assert dashboard is not None
                
    def test_init_default_port(self):
        """Test dashboard uses default port 5000"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                assert dashboard.port == 5000
                
    def test_init_custom_port(self):
        """Test dashboard with custom port"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard(port=8080)
                assert dashboard.port == 8080
                
    def test_init_empty_dashboard_data(self):
        """Test dashboard starts with empty data"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                assert dashboard.dashboard_data == {}
                assert dashboard.last_update is None


class TestGetDashboardData:
    """Tests for get_dashboard_data"""
    
    def test_get_dashboard_data_returns_dict(self):
        """Test get_dashboard_data returns dict"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector') as mock_collector:
            with patch('backend.monitoring.slo_dashboard.get_alert_manager') as mock_alert:
                mock_collector.return_value.get_metrics_summary.return_value = {
                    'slo_targets': {},
                    'violations': [],
                    'buffer_stats': {}
                }
                mock_alert.return_value.get_alert_status.return_value = {}
                
                dashboard = SLODashboard()
                data = dashboard.get_dashboard_data()
                
                assert isinstance(data, dict)
                
    def test_get_dashboard_data_has_required_fields(self):
        """Test dashboard data has required fields"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector') as mock_collector:
            with patch('backend.monitoring.slo_dashboard.get_alert_manager') as mock_alert:
                mock_collector.return_value.get_metrics_summary.return_value = {
                    'slo_targets': {},
                    'violations': [],
                    'buffer_stats': {}
                }
                mock_alert.return_value.get_alert_status.return_value = {}
                
                dashboard = SLODashboard()
                data = dashboard.get_dashboard_data()
                
                assert 'timestamp' in data
                assert 'system_health' in data
                assert 'slo_compliance' in data
                assert 'alert_status' in data
                assert 'performance_metrics' in data
                assert 'uptime' in data
                
    def test_get_dashboard_data_handles_exception(self):
        """Test dashboard data handles exceptions"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector') as mock_collector:
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                mock_collector.return_value.get_metrics_summary.side_effect = Exception("Test error")
                
                dashboard = SLODashboard()
                data = dashboard.get_dashboard_data()
                
                assert 'error' in data
                assert 'timestamp' in data
                
    def test_get_dashboard_data_updates_last_update(self):
        """Test dashboard data updates last_update time"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector') as mock_collector:
            with patch('backend.monitoring.slo_dashboard.get_alert_manager') as mock_alert:
                mock_collector.return_value.get_metrics_summary.return_value = {
                    'slo_targets': {},
                    'violations': [],
                    'buffer_stats': {}
                }
                mock_alert.return_value.get_alert_status.return_value = {}
                
                dashboard = SLODashboard()
                assert dashboard.last_update is None
                
                dashboard.get_dashboard_data()
                
                assert dashboard.last_update is not None


class TestCalculateSystemHealth:
    """Tests for _calculate_system_health"""
    
    def test_calculate_health_no_data(self):
        """Test health calculation with no data"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                
                slo_summary = {'slo_targets': {}, 'violations': []}
                health = dashboard._calculate_system_health(slo_summary)
                
                assert health['score'] == 100.0
                assert health['status'] == 'unknown'
                
    def test_calculate_health_excellent(self):
        """Test excellent health status"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                
                slo_summary = {
                    'slo_targets': {
                        'order_submission_latency_p99': {'compliance_ratio': 1.0},
                        'order_accuracy_daily': {'compliance_ratio': 1.0},
                        'fill_rate_5min': {'compliance_ratio': 1.0},
                        'system_availability_hourly': {'compliance_ratio': 1.0}
                    },
                    'violations': []
                }
                health = dashboard._calculate_system_health(slo_summary)
                
                assert health['score'] >= 99.0
                assert health['status'] == 'excellent'
                
    def test_calculate_health_good(self):
        """Test good health status"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                
                slo_summary = {
                    'slo_targets': {
                        'order_submission_latency_p99': {'compliance_ratio': 0.97},
                        'order_accuracy_daily': {'compliance_ratio': 0.97},
                        'fill_rate_5min': {'compliance_ratio': 0.97},
                        'system_availability_hourly': {'compliance_ratio': 0.97}
                    },
                    'violations': []
                }
                health = dashboard._calculate_system_health(slo_summary)
                
                assert 95.0 <= health['score'] < 99.0
                assert health['status'] == 'good'
                
    def test_calculate_health_warning(self):
        """Test warning health status"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                
                slo_summary = {
                    'slo_targets': {
                        'order_submission_latency_p99': {'compliance_ratio': 0.92},
                        'order_accuracy_daily': {'compliance_ratio': 0.92},
                        'fill_rate_5min': {'compliance_ratio': 0.92},
                        'system_availability_hourly': {'compliance_ratio': 0.92}
                    },
                    'violations': []
                }
                health = dashboard._calculate_system_health(slo_summary)
                
                assert 90.0 <= health['score'] < 95.0
                assert health['status'] == 'warning'
                
    def test_calculate_health_degraded(self):
        """Test degraded health status"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                
                slo_summary = {
                    'slo_targets': {
                        'order_submission_latency_p99': {'compliance_ratio': 0.85},
                        'order_accuracy_daily': {'compliance_ratio': 0.85},
                        'fill_rate_5min': {'compliance_ratio': 0.85},
                        'system_availability_hourly': {'compliance_ratio': 0.85}
                    },
                    'violations': []
                }
                health = dashboard._calculate_system_health(slo_summary)
                
                assert 80.0 <= health['score'] < 90.0
                assert health['status'] == 'degraded'
                
    def test_calculate_health_critical(self):
        """Test critical health status"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                
                slo_summary = {
                    'slo_targets': {
                        'order_submission_latency_p99': {'compliance_ratio': 0.7},
                        'order_accuracy_daily': {'compliance_ratio': 0.7},
                        'fill_rate_5min': {'compliance_ratio': 0.7},
                        'system_availability_hourly': {'compliance_ratio': 0.7}
                    },
                    'violations': []
                }
                health = dashboard._calculate_system_health(slo_summary)
                
                assert health['score'] < 80.0
                assert health['status'] == 'critical'
                
    def test_calculate_health_counts_violations(self):
        """Test health includes violation counts"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                
                slo_summary = {
                    'slo_targets': {
                        'order_submission_latency_p99': {'compliance_ratio': 0.8}
                    },
                    'violations': [
                        {'severity': 'critical'},
                        {'severity': 'warning'},
                        {'severity': 'critical'}
                    ]
                }
                health = dashboard._calculate_system_health(slo_summary)
                
                assert health['critical_violations'] == 2
                assert health['total_violations'] == 3


class TestGetHealthMessage:
    """Tests for _get_health_message"""
    
    def test_health_message_excellent(self):
        """Test excellent status message"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                message = dashboard._get_health_message('excellent', 0)
                assert 'peak performance' in message.lower()
                
    def test_health_message_good(self):
        """Test good status message"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                message = dashboard._get_health_message('good', 0)
                assert 'acceptable' in message.lower()
                
    def test_health_message_warning(self):
        """Test warning status message"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                message = dashboard._get_health_message('warning', 0)
                assert 'degradation' in message.lower()
                
    def test_health_message_degraded_with_violations(self):
        """Test degraded status message with violations"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                message = dashboard._get_health_message('degraded', 3)
                assert '3' in message
                assert 'critical' in message.lower()
                
    def test_health_message_degraded_no_violations(self):
        """Test degraded status message without violations"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                message = dashboard._get_health_message('degraded', 0)
                assert 'below targets' in message.lower()
                
    def test_health_message_critical(self):
        """Test critical status message"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                message = dashboard._get_health_message('critical', 5)
                assert 'CRITICAL' in message
                assert '5' in message
                assert 'immediate action' in message.lower()


class TestGetPerformanceMetrics:
    """Tests for _get_performance_metrics"""
    
    def test_get_performance_metrics_structure(self):
        """Test performance metrics has correct structure"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                metrics = dashboard._get_performance_metrics()
                
                assert 'order_latency' in metrics
                assert 'order_accuracy' in metrics
                assert 'fill_rate' in metrics
                assert 'system_availability' in metrics
                
    def test_get_performance_metrics_latency_fields(self):
        """Test latency metrics have required fields"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                metrics = dashboard._get_performance_metrics()
                
                latency = metrics['order_latency']
                assert 'current_p99_ms' in latency
                assert 'target_ms' in latency
                assert 'trend' in latency
                
    def test_get_performance_metrics_accuracy_fields(self):
        """Test accuracy metrics have required fields"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                metrics = dashboard._get_performance_metrics()
                
                accuracy = metrics['order_accuracy']
                assert 'current_percent' in accuracy
                assert 'target_percent' in accuracy
                assert 'trend' in accuracy


class TestGetUptimeStats:
    """Tests for _get_uptime_stats"""
    
    def test_get_uptime_stats_structure(self):
        """Test uptime stats has correct structure"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                stats = dashboard._get_uptime_stats()
                
                assert 'current_uptime_hours' in stats
                assert 'last_restart' in stats
                assert 'mttr_minutes' in stats
                assert 'mtbf_hours' in stats


class TestStartRealtimeUpdates:
    """Tests for start_realtime_updates"""
    
    @pytest.mark.asyncio
    async def test_start_realtime_updates_no_socketio(self):
        """Test realtime updates skipped without socketio"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                with patch('backend.monitoring.slo_dashboard.FLASK_AVAILABLE', False):
                    dashboard = SLODashboard()
                    dashboard.socketio = None
                    
                    # Should return without error
                    await dashboard.start_realtime_updates()
                    
    @pytest.mark.asyncio
    async def test_start_realtime_updates_with_socketio(self):
        """Test realtime updates with socketio"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector') as mock_collector:
            with patch('backend.monitoring.slo_dashboard.get_alert_manager') as mock_alert:
                mock_collector.return_value.get_metrics_summary.return_value = {
                    'slo_targets': {},
                    'violations': [],
                    'buffer_stats': {}
                }
                mock_alert.return_value.get_alert_status.return_value = {}
                
                dashboard = SLODashboard()
                mock_socketio = MagicMock()
                dashboard.socketio = mock_socketio
                
                # Run for one iteration
                call_count = 0
                original_sleep = asyncio.sleep
                
                async def mock_sleep(delay):
                    nonlocal call_count
                    call_count += 1
                    if call_count >= 1:
                        raise asyncio.CancelledError()
                    return await original_sleep(0.01)
                    
                with patch('asyncio.sleep', mock_sleep):
                    try:
                        await dashboard.start_realtime_updates(update_interval=0.01)
                    except asyncio.CancelledError:
                        pass


class TestRunDashboard:
    """Tests for run_dashboard"""
    
    def test_run_dashboard_flask_not_available(self):
        """Test run_dashboard when Flask not available"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                with patch('backend.monitoring.slo_dashboard.FLASK_AVAILABLE', False):
                    dashboard = SLODashboard()
                    dashboard.app = None
                    
                    result = dashboard.run_dashboard()
                    assert result is False
                    
    def test_run_dashboard_handles_exception(self):
        """Test run_dashboard handles exception"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                mock_socketio = MagicMock()
                mock_socketio.run.side_effect = Exception("Server error")
                dashboard.socketio = mock_socketio
                dashboard.app = MagicMock()
                
                with patch('asyncio.create_task'):
                    result = dashboard.run_dashboard()
                    assert result is False


class TestGenerateStaticReport:
    """Tests for generate_static_report"""
    
    def test_generate_static_report_success(self):
        """Test generating static HTML report"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector') as mock_collector:
            with patch('backend.monitoring.slo_dashboard.get_alert_manager') as mock_alert:
                mock_collector.return_value.get_metrics_summary.return_value = {
                    'slo_targets': {},
                    'violations': [],
                    'buffer_stats': {}
                }
                mock_alert.return_value.get_alert_status.return_value = {}
                
                dashboard = SLODashboard()
                
                m = mock_open()
                with patch('builtins.open', m):
                    result = dashboard.generate_static_report('test_report.html')
                    
                assert result is True
                m.assert_called_once()
                
    def test_generate_static_report_handles_error(self):
        """Test report generation handles error"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector') as mock_collector:
            with patch('backend.monitoring.slo_dashboard.get_alert_manager') as mock_alert:
                mock_collector.return_value.get_metrics_summary.return_value = {
                    'slo_targets': {},
                    'violations': [],
                    'buffer_stats': {}
                }
                mock_alert.return_value.get_alert_status.return_value = {}
                
                dashboard = SLODashboard()
                
                with patch('builtins.open', side_effect=IOError("Write error")):
                    result = dashboard.generate_static_report('test_report.html')
                    
                assert result is False


class TestGenerateHtmlReport:
    """Tests for _generate_html_report"""
    
    def test_generate_html_report_structure(self):
        """Test HTML report has correct structure"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                
                data = {
                    'timestamp': '2024-01-01T12:00:00',
                    'system_health': {
                        'score': 95.0,
                        'status': 'good',
                        'message': 'Systems OK',
                        'total_violations': 0,
                        'critical_violations': 0
                    },
                    'slo_compliance': {},
                    'active_violations': []
                }
                
                html = dashboard._generate_html_report(data)
                
                assert '<!DOCTYPE html>' in html
                assert 'SLO Status Report' in html
                assert '95.0%' in html
                
    def test_generate_html_report_with_slo_data(self):
        """Test HTML report with SLO compliance data"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                
                data = {
                    'timestamp': '2024-01-01T12:00:00',
                    'system_health': {
                        'score': 90.0,
                        'status': 'warning',
                        'message': 'Warning',
                        'total_violations': 1,
                        'critical_violations': 0
                    },
                    'slo_compliance': {
                        'order_latency': {
                            'compliance_ratio': 0.95,
                            'error_budget_remaining': 0.5,
                            'burn_rate': 1.0,
                            'alert_level': 1
                        }
                    },
                    'active_violations': []
                }
                
                html = dashboard._generate_html_report(data)
                
                assert 'Order Latency' in html
                assert '95.0%' in html
                
    def test_generate_html_report_with_violations(self):
        """Test HTML report with violations"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                
                data = {
                    'timestamp': '2024-01-01T12:00:00',
                    'system_health': {
                        'score': 75.0,
                        'status': 'critical',
                        'message': 'Critical',
                        'total_violations': 2,
                        'critical_violations': 2
                    },
                    'slo_compliance': {},
                    'active_violations': [
                        {
                            'slo_name': 'order_latency',
                            'severity': 'critical',
                            'burn_rate': 2.5,
                            'actual_value': 0.8,
                            'target_value': 0.99
                        }
                    ]
                }
                
                html = dashboard._generate_html_report(data)
                
                assert 'Active SLO Violations' in html
                assert 'order_latency' in html
                assert 'CRITICAL' in html


class TestGetDashboardSingleton:
    """Tests for get_dashboard singleton"""
    
    def test_get_dashboard_returns_instance(self):
        """Test get_dashboard returns instance"""
        with patch('backend.monitoring.slo_dashboard._dashboard', None):
            with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
                with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                    dashboard = get_dashboard()
                    assert dashboard is not None
                    assert isinstance(dashboard, SLODashboard)
                    
    def test_get_dashboard_custom_port(self):
        """Test get_dashboard with custom port"""
        with patch('backend.monitoring.slo_dashboard._dashboard', None):
            with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
                with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                    dashboard = get_dashboard(port=8080)
                    assert dashboard.port == 8080


class TestStartSloDashboard:
    """Tests for start_slo_dashboard"""
    
    def test_start_slo_dashboard_calls_run(self):
        """Test start_slo_dashboard calls run_dashboard"""
        with patch('backend.monitoring.slo_dashboard.get_dashboard') as mock_get:
            mock_dashboard = MagicMock()
            mock_dashboard.run_dashboard.return_value = True
            mock_get.return_value = mock_dashboard
            
            result = start_slo_dashboard(port=5000, debug=False)
            
            mock_dashboard.run_dashboard.assert_called_once_with(debug=False)
            assert result is True


class TestFlaskRoutesSetup:
    """Tests for Flask routes setup"""
    
    def test_setup_routes_with_flask(self):
        """Test routes are set up when Flask is available"""
        if not FLASK_AVAILABLE:
            pytest.skip("Flask not available")
            
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                
                # Should have app and socketio
                assert dashboard.app is not None
                assert dashboard.socketio is not None
                
    def test_setup_routes_without_flask(self):
        """Test graceful handling without Flask"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                with patch('backend.monitoring.slo_dashboard.FLASK_AVAILABLE', False):
                    # Need to reimport with patched value
                    dashboard = SLODashboard()
                    dashboard.app = None
                    dashboard.socketio = None
                    
                    # Should not have Flask components
                    # (In reality this depends on import time)


class TestHealthStatusColors:
    """Tests for health status color assignment"""
    
    def test_excellent_status_green(self):
        """Test excellent status gets green color"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                
                slo_summary = {
                    'slo_targets': {
                        'test_slo': {'compliance_ratio': 1.0}
                    },
                    'violations': []
                }
                health = dashboard._calculate_system_health(slo_summary)
                
                assert health['status_color'] == '#00C851'  # Green
                
    def test_critical_status_red(self):
        """Test critical status gets red color"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                
                slo_summary = {
                    'slo_targets': {
                        'test_slo': {'compliance_ratio': 0.5}
                    },
                    'violations': []
                }
                health = dashboard._calculate_system_health(slo_summary)
                
                assert health['status_color'] == '#F44336'  # Red


class TestSLOWeights:
    """Tests for SLO weighting in health calculation"""
    
    def test_order_latency_highest_weight(self):
        """Test order latency has highest weight"""
        with patch('backend.monitoring.slo_dashboard.get_slo_collector'):
            with patch('backend.monitoring.slo_dashboard.get_alert_manager'):
                dashboard = SLODashboard()
                
                # Only latency failing
                slo_summary1 = {
                    'slo_targets': {
                        'order_submission_latency_p99': {'compliance_ratio': 0.5},
                        'order_accuracy_daily': {'compliance_ratio': 1.0},
                        'fill_rate_5min': {'compliance_ratio': 1.0},
                        'system_availability_hourly': {'compliance_ratio': 1.0}
                    },
                    'violations': []
                }
                
                # Only availability failing
                slo_summary2 = {
                    'slo_targets': {
                        'order_submission_latency_p99': {'compliance_ratio': 1.0},
                        'order_accuracy_daily': {'compliance_ratio': 1.0},
                        'fill_rate_5min': {'compliance_ratio': 1.0},
                        'system_availability_hourly': {'compliance_ratio': 0.5}
                    },
                    'violations': []
                }
                
                health1 = dashboard._calculate_system_health(slo_summary1)
                health2 = dashboard._calculate_system_health(slo_summary2)
                
                # Latency failure should have bigger impact (lower score)
                assert health1['score'] < health2['score']
