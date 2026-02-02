"""
Comprehensive tests for SLO Alerts
Target: 90%+ coverage of backend/monitoring/slo_alerts.py
"""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock, mock_open
import pytest
import json

from backend.monitoring.slo_alerts import (
    AlertRule,
    AlertNotification,
    SLOBurnRateAlertManager,
    get_alert_manager,
    start_alert_monitoring,
)


class TestAlertRuleDataclass:
    """Tests for AlertRule dataclass"""
    
    def test_create_alert_rule(self):
        """Test creating AlertRule"""
        rule = AlertRule(
            name="test_rule",
            slo_name="order_latency",
            burn_rate_threshold=2.0,
            window_minutes=5,
            severity="critical",
            cooldown_minutes=15,
            notification_channels=["slack", "email"],
            escalation_delay_minutes=5
        )
        assert rule.name == "test_rule"
        assert rule.slo_name == "order_latency"
        assert rule.burn_rate_threshold == 2.0
        assert rule.window_minutes == 5
        assert rule.severity == "critical"
        assert rule.cooldown_minutes == 15
        assert rule.notification_channels == ["slack", "email"]
        assert rule.escalation_delay_minutes == 5
        
    def test_alert_rule_default_escalation(self):
        """Test AlertRule with default escalation delay"""
        rule = AlertRule(
            name="test_rule",
            slo_name="test_slo",
            burn_rate_threshold=1.0,
            window_minutes=10,
            severity="warning",
            cooldown_minutes=30,
            notification_channels=["email"]
        )
        assert rule.escalation_delay_minutes == 0


class TestAlertNotificationDataclass:
    """Tests for AlertNotification dataclass"""
    
    def test_create_alert_notification(self):
        """Test creating AlertNotification"""
        notification = AlertNotification(
            timestamp=datetime.now(),
            rule_name="test_rule",
            slo_name="order_latency",
            severity="critical",
            message="Test alert message",
            burn_rate=2.5,
            error_budget_remaining=0.3,
            context={"threshold": 2.0}
        )
        assert notification.rule_name == "test_rule"
        assert notification.slo_name == "order_latency"
        assert notification.severity == "critical"
        assert notification.burn_rate == 2.5
        assert notification.error_budget_remaining == 0.3


class TestSLOBurnRateAlertManagerInit:
    """Tests for SLOBurnRateAlertManager initialization"""
    
    def test_init_creates_instance(self):
        """Test manager initializes correctly"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            assert manager is not None
            
    def test_init_has_notification_channels(self):
        """Test manager has notification channel handlers"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            assert 'email' in manager.notification_channels
            assert 'slack' in manager.notification_channels
            assert 'pagerduty' in manager.notification_channels
            assert 'webhook' in manager.notification_channels
            
    def test_init_empty_state(self):
        """Test manager initializes with empty state"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            assert manager.last_alert_times == {}
            assert manager.active_alerts == {}
            assert manager.alert_history == []


class TestLoadAlertConfiguration:
    """Tests for load_alert_configuration"""
    
    def test_load_creates_defaults_when_no_file(self):
        """Test loading creates default rules when no config file"""
        with patch.object(Path, 'exists', return_value=False):
            with patch.object(SLOBurnRateAlertManager, 'save_alert_configuration'):
                manager = SLOBurnRateAlertManager()
                assert len(manager.alert_rules) > 0
                
    def test_load_from_existing_config_file(self):
        """Test loading from existing config file"""
        config_data = {
            "alert_rules": {
                "test_rule": {
                    "name": "test_rule",
                    "slo_name": "test_slo",
                    "burn_rate_threshold": 1.5,
                    "window_minutes": 10,
                    "severity": "warning",
                    "cooldown_minutes": 20,
                    "notification_channels": ["slack"]
                }
            }
        }
        
        with patch.object(Path, 'exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(config_data))):
                manager = SLOBurnRateAlertManager()
                assert "test_rule" in manager.alert_rules
                
    def test_load_handles_invalid_json(self):
        """Test loading handles invalid JSON gracefully"""
        with patch.object(Path, 'exists', return_value=True):
            with patch('builtins.open', mock_open(read_data="invalid json{")):
                manager = SLOBurnRateAlertManager()
                # Should fall back to defaults
                assert len(manager.alert_rules) > 0
                
    def test_load_handles_file_error(self):
        """Test loading handles file read error"""
        with patch.object(Path, 'exists', return_value=True):
            with patch('builtins.open', side_effect=IOError("Read error")):
                manager = SLOBurnRateAlertManager()
                # Should fall back to defaults
                assert len(manager.alert_rules) > 0


class TestSaveAlertConfiguration:
    """Tests for save_alert_configuration"""
    
    def test_save_creates_config_file(self):
        """Test saving creates config file"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            manager.alert_rules = {
                "test_rule": AlertRule(
                    name="test_rule",
                    slo_name="test_slo",
                    burn_rate_threshold=1.0,
                    window_minutes=5,
                    severity="warning",
                    cooldown_minutes=10,
                    notification_channels=["email"]
                )
            }
            
            m = mock_open()
            with patch('builtins.open', m):
                with patch.object(Path, 'mkdir'):
                    manager.save_alert_configuration()
                    
            # Check file was opened for writing
            m.assert_called()
            
    def test_save_handles_write_error(self):
        """Test saving handles write error gracefully"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            
            with patch.object(Path, 'mkdir'):
                with patch('builtins.open', side_effect=IOError("Write error")):
                    # Should not raise
                    manager.save_alert_configuration()


class TestEvaluateAlertRules:
    """Tests for evaluate_alert_rules"""
    
    def test_evaluate_returns_notifications_list(self):
        """Test evaluate returns list of notifications"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            manager.alert_rules = {}
            
            result = manager.evaluate_alert_rules()
            assert isinstance(result, list)
            
    def test_evaluate_skips_rule_in_cooldown(self):
        """Test evaluate skips rules in cooldown period"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            rule = AlertRule(
                name="test_rule",
                slo_name="test_slo",
                burn_rate_threshold=1.0,
                window_minutes=5,
                severity="warning",
                cooldown_minutes=30,
                notification_channels=["email"]
            )
            manager.alert_rules = {"test_rule": rule}
            # Set recent alert time
            manager.last_alert_times["test_rule"] = datetime.now()
            
            with patch.object(manager.slo_collector, 'calculate_slo_compliance', return_value={"burn_rate": 2.0}):
                result = manager.evaluate_alert_rules()
                # Should be empty due to cooldown
                assert len(result) == 0
                
    def test_evaluate_triggers_alert_above_threshold(self):
        """Test evaluate triggers alert when above threshold"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            rule = AlertRule(
                name="test_rule",
                slo_name="test_slo",
                burn_rate_threshold=1.0,
                window_minutes=5,
                severity="critical",
                cooldown_minutes=30,
                notification_channels=["email"]
            )
            manager.alert_rules = {"test_rule": rule}
            
            compliance_data = {
                "burn_rate": 2.0,
                "error_budget_remaining": 0.3,
                "compliance_ratio": 0.95
            }
            
            with patch.object(manager.slo_collector, 'calculate_slo_compliance', return_value=compliance_data):
                result = manager.evaluate_alert_rules()
                assert len(result) == 1
                assert result[0].rule_name == "test_rule"
                
    def test_evaluate_clears_resolved_alert(self):
        """Test evaluate clears alert when resolved"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            rule = AlertRule(
                name="test_rule",
                slo_name="test_slo",
                burn_rate_threshold=2.0,
                window_minutes=5,
                severity="warning",
                cooldown_minutes=30,
                notification_channels=["email"]
            )
            manager.alert_rules = {"test_rule": rule}
            
            # Set existing active alert
            manager.active_alerts["test_rule"] = AlertNotification(
                timestamp=datetime.now() - timedelta(minutes=35),
                rule_name="test_rule",
                slo_name="test_slo",
                severity="warning",
                message="Old alert",
                burn_rate=2.5,
                error_budget_remaining=0.3,
                context={}
            )
            
            # Now burn rate is below threshold
            compliance_data = {"burn_rate": 1.0, "error_budget_remaining": 0.8}
            
            with patch.object(manager.slo_collector, 'calculate_slo_compliance', return_value=compliance_data):
                manager.evaluate_alert_rules()
                # Alert should be cleared
                assert "test_rule" not in manager.active_alerts
                
    def test_evaluate_handles_no_compliance_data(self):
        """Test evaluate handles missing compliance data"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            rule = AlertRule(
                name="test_rule",
                slo_name="test_slo",
                burn_rate_threshold=1.0,
                window_minutes=5,
                severity="warning",
                cooldown_minutes=30,
                notification_channels=["email"]
            )
            manager.alert_rules = {"test_rule": rule}
            
            with patch.object(manager.slo_collector, 'calculate_slo_compliance', return_value=None):
                result = manager.evaluate_alert_rules()
                assert len(result) == 0
                
    def test_evaluate_handles_exception_in_rule(self):
        """Test evaluate handles exception in rule evaluation"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            rule = AlertRule(
                name="test_rule",
                slo_name="test_slo",
                burn_rate_threshold=1.0,
                window_minutes=5,
                severity="warning",
                cooldown_minutes=30,
                notification_channels=["email"]
            )
            manager.alert_rules = {"test_rule": rule}
            
            with patch.object(manager.slo_collector, 'calculate_slo_compliance', side_effect=Exception("Test error")):
                result = manager.evaluate_alert_rules()
                # Should return empty list without raising
                assert isinstance(result, list)


class TestFormatAlertMessage:
    """Tests for _format_alert_message"""
    
    def test_format_critical_alert(self):
        """Test formatting critical alert message"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            rule = AlertRule(
                name="test_rule",
                slo_name="order_latency",
                burn_rate_threshold=2.0,
                window_minutes=5,
                severity="critical",
                cooldown_minutes=15,
                notification_channels=["email"]
            )
            
            message = manager._format_alert_message(rule, burn_rate=3.0, error_budget=0.2)
            assert "CRITICAL" in message
            assert "order_latency" in message
            assert "3.00" in message
            assert "IMMEDIATE ACTION REQUIRED" in message
            
    def test_format_warning_alert(self):
        """Test formatting warning alert message"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            rule = AlertRule(
                name="test_rule",
                slo_name="fill_rate",
                burn_rate_threshold=1.0,
                window_minutes=10,
                severity="warning",
                cooldown_minutes=30,
                notification_channels=["slack"]
            )
            
            message = manager._format_alert_message(rule, burn_rate=1.5, error_budget=0.5)
            assert "WARNING" in message
            assert "fill_rate" in message
            assert "investigate" in message.lower()
            
    def test_format_info_alert(self):
        """Test formatting info alert message"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            rule = AlertRule(
                name="test_rule",
                slo_name="system_health",
                burn_rate_threshold=0.5,
                window_minutes=15,
                severity="info",
                cooldown_minutes=60,
                notification_channels=["email"]
            )
            
            message = manager._format_alert_message(rule, burn_rate=0.6, error_budget=0.9)
            assert "INFO" in message
            assert "system_health" in message


class TestSendNotifications:
    """Tests for send_notifications"""
    
    @pytest.mark.asyncio
    async def test_send_notifications_calls_channels(self):
        """Test sending notifications calls appropriate channels"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            rule = AlertRule(
                name="test_rule",
                slo_name="test_slo",
                burn_rate_threshold=1.0,
                window_minutes=5,
                severity="warning",
                cooldown_minutes=10,
                notification_channels=["email", "slack"]
            )
            manager.alert_rules = {"test_rule": rule}
            
            # Ensure notification_channels dict has our mocks
            mock_email = AsyncMock()
            mock_slack = AsyncMock()
            manager.notification_channels = {
                'email': mock_email,
                'slack': mock_slack
            }
            
            notification = AlertNotification(
                timestamp=datetime.now(),
                rule_name="test_rule",
                slo_name="test_slo",
                severity="warning",
                message="Test message",
                burn_rate=1.5,
                error_budget_remaining=0.5,
                context={}
            )
            
            await manager.send_notifications([notification])
            mock_email.assert_called_once()
            mock_slack.assert_called_once()
                    
    @pytest.mark.asyncio
    async def test_send_notifications_handles_channel_error(self):
        """Test sending handles channel error gracefully"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            rule = AlertRule(
                name="test_rule",
                slo_name="test_slo",
                burn_rate_threshold=1.0,
                window_minutes=5,
                severity="warning",
                cooldown_minutes=10,
                notification_channels=["email"]
            )
            manager.alert_rules = {"test_rule": rule}
            
            notification = AlertNotification(
                timestamp=datetime.now(),
                rule_name="test_rule",
                slo_name="test_slo",
                severity="warning",
                message="Test message",
                burn_rate=1.5,
                error_budget_remaining=0.5,
                context={}
            )
            
            with patch.object(manager, '_send_email_notification', new_callable=AsyncMock, side_effect=Exception("Send failed")):
                # Should not raise
                await manager.send_notifications([notification])
                
    @pytest.mark.asyncio
    async def test_send_notifications_skips_unknown_rule(self):
        """Test sending skips notification for unknown rule"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            manager.alert_rules = {}  # No rules
            
            notification = AlertNotification(
                timestamp=datetime.now(),
                rule_name="unknown_rule",
                slo_name="test_slo",
                severity="warning",
                message="Test message",
                burn_rate=1.5,
                error_budget_remaining=0.5,
                context={}
            )
            
            # Should not raise
            await manager.send_notifications([notification])


class TestNotificationChannels:
    """Tests for individual notification channels"""
    
    @pytest.mark.asyncio
    async def test_send_email_notification(self):
        """Test email notification"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            notification = AlertNotification(
                timestamp=datetime.now(),
                rule_name="test_rule",
                slo_name="test_slo",
                severity="warning",
                message="Test email",
                burn_rate=1.5,
                error_budget_remaining=0.5,
                context={}
            )
            # Should not raise
            await manager._send_email_notification(notification)
            
    @pytest.mark.asyncio
    async def test_send_slack_notification(self):
        """Test Slack notification"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            notification = AlertNotification(
                timestamp=datetime.now(),
                rule_name="test_rule",
                slo_name="test_slo",
                severity="critical",
                message="Test slack",
                burn_rate=2.5,
                error_budget_remaining=0.3,
                context={}
            )
            # Should not raise
            await manager._send_slack_notification(notification)
            
    @pytest.mark.asyncio
    async def test_send_pagerduty_notification(self):
        """Test PagerDuty notification"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            notification = AlertNotification(
                timestamp=datetime.now(),
                rule_name="test_rule",
                slo_name="test_slo",
                severity="critical",
                message="Test pagerduty",
                burn_rate=3.0,
                error_budget_remaining=0.1,
                context={}
            )
            # Should not raise
            await manager._send_pagerduty_notification(notification)
            
    @pytest.mark.asyncio
    async def test_send_webhook_notification(self):
        """Test webhook notification"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            notification = AlertNotification(
                timestamp=datetime.now(),
                rule_name="test_rule",
                slo_name="test_slo",
                severity="info",
                message="Test webhook",
                burn_rate=0.5,
                error_budget_remaining=0.9,
                context={}
            )
            # Should not raise
            await manager._send_webhook_notification(notification)


class TestRunAlertLoop:
    """Tests for run_alert_loop"""
    
    @pytest.mark.asyncio
    async def test_alert_loop_evaluates_rules(self):
        """Test alert loop evaluates rules"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            
            call_count = 0
            original_evaluate = manager.evaluate_alert_rules
            
            def mock_evaluate():
                nonlocal call_count
                call_count += 1
                if call_count >= 1:
                    raise asyncio.CancelledError()
                return []
                
            with patch.object(manager, 'evaluate_alert_rules', side_effect=mock_evaluate):
                try:
                    await manager.run_alert_loop(check_interval=0.01)
                except asyncio.CancelledError:
                    pass
                    
            assert call_count >= 1
            
    @pytest.mark.asyncio
    async def test_alert_loop_handles_exception(self):
        """Test alert loop handles exceptions in evaluation"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            
            call_count = 0
            
            def mock_evaluate():
                nonlocal call_count
                call_count += 1
                if call_count >= 2:
                    raise asyncio.CancelledError()
                raise Exception("Test error")
                
            with patch.object(manager, 'evaluate_alert_rules', side_effect=mock_evaluate):
                try:
                    await manager.run_alert_loop(check_interval=0.01)
                except asyncio.CancelledError:
                    pass
                    
            assert call_count >= 1


class TestGetAlertStatus:
    """Tests for get_alert_status"""
    
    def test_get_status_returns_dict(self):
        """Test get_alert_status returns status dict"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            manager.alert_rules = {"rule1": MagicMock()}
            
            status = manager.get_alert_status()
            assert isinstance(status, dict)
            assert 'timestamp' in status
            assert 'active_alerts' in status
            assert 'alert_rules_count' in status
            assert 'recent_alerts_24h' in status
            
    def test_get_status_includes_active_alerts(self):
        """Test get_alert_status includes active alerts"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            manager.active_alerts["test_rule"] = AlertNotification(
                timestamp=datetime.now(),
                rule_name="test_rule",
                slo_name="test_slo",
                severity="critical",
                message="Test",
                burn_rate=2.0,
                error_budget_remaining=0.3,
                context={}
            )
            
            status = manager.get_alert_status()
            assert "test_rule" in status['active_alerts']
            assert status['active_alerts']['test_rule']['severity'] == "critical"
            
    def test_get_status_counts_recent_alerts(self):
        """Test get_alert_status counts recent alerts"""
        with patch.object(SLOBurnRateAlertManager, 'load_alert_configuration'):
            manager = SLOBurnRateAlertManager()
            
            # Add recent alert
            manager.alert_history.append(AlertNotification(
                timestamp=datetime.now() - timedelta(hours=1),
                rule_name="recent_rule",
                slo_name="test_slo",
                severity="warning",
                message="Recent",
                burn_rate=1.5,
                error_budget_remaining=0.5,
                context={}
            ))
            
            # Add old alert
            manager.alert_history.append(AlertNotification(
                timestamp=datetime.now() - timedelta(days=2),
                rule_name="old_rule",
                slo_name="test_slo",
                severity="warning",
                message="Old",
                burn_rate=1.5,
                error_budget_remaining=0.5,
                context={}
            ))
            
            status = manager.get_alert_status()
            assert status['recent_alerts_24h'] == 1


class TestGetAlertManager:
    """Tests for get_alert_manager singleton"""
    
    def test_get_alert_manager_returns_instance(self):
        """Test get_alert_manager returns manager instance"""
        with patch('backend.monitoring.slo_alerts._alert_manager', None):
            with patch.object(SLOBurnRateAlertManager, '__init__', return_value=None):
                manager = get_alert_manager()
                # Should return an instance (even if mocked)
                assert manager is not None
                
    def test_get_alert_manager_returns_same_instance(self):
        """Test get_alert_manager returns singleton"""
        manager1 = get_alert_manager()
        manager2 = get_alert_manager()
        assert manager1 is manager2


class TestStartAlertMonitoring:
    """Tests for start_alert_monitoring"""
    
    @pytest.mark.asyncio
    async def test_start_alert_monitoring_calls_loop(self):
        """Test start_alert_monitoring starts the alert loop"""
        with patch('backend.monitoring.slo_alerts.get_alert_manager') as mock_get:
            mock_manager = MagicMock()
            mock_manager.run_alert_loop = AsyncMock(side_effect=asyncio.CancelledError())
            mock_get.return_value = mock_manager
            
            try:
                await start_alert_monitoring(check_interval=1)
            except asyncio.CancelledError:
                pass
                
            mock_manager.run_alert_loop.assert_called_once_with(1)


class TestDefaultAlertRules:
    """Tests for default alert rule configuration"""
    
    def test_has_order_latency_critical_rule(self):
        """Test has order latency critical rule"""
        with patch.object(Path, 'exists', return_value=False):
            with patch.object(SLOBurnRateAlertManager, 'save_alert_configuration'):
                manager = SLOBurnRateAlertManager()
                assert "order_latency_p99_critical" in manager.alert_rules
                
    def test_has_order_latency_warning_rule(self):
        """Test has order latency warning rule"""
        with patch.object(Path, 'exists', return_value=False):
            with patch.object(SLOBurnRateAlertManager, 'save_alert_configuration'):
                manager = SLOBurnRateAlertManager()
                assert "order_latency_p99_warning" in manager.alert_rules
                
    def test_has_order_accuracy_critical_rule(self):
        """Test has order accuracy critical rule"""
        with patch.object(Path, 'exists', return_value=False):
            with patch.object(SLOBurnRateAlertManager, 'save_alert_configuration'):
                manager = SLOBurnRateAlertManager()
                assert "order_accuracy_critical" in manager.alert_rules
                
    def test_has_fill_rate_warning_rule(self):
        """Test has fill rate warning rule"""
        with patch.object(Path, 'exists', return_value=False):
            with patch.object(SLOBurnRateAlertManager, 'save_alert_configuration'):
                manager = SLOBurnRateAlertManager()
                assert "fill_rate_warning" in manager.alert_rules
                
    def test_has_system_availability_critical_rule(self):
        """Test has system availability critical rule"""
        with patch.object(Path, 'exists', return_value=False):
            with patch.object(SLOBurnRateAlertManager, 'save_alert_configuration'):
                manager = SLOBurnRateAlertManager()
                assert "system_availability_critical" in manager.alert_rules
