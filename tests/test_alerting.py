"""
Tests for the alerting integration module.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from backend.infra.alerting import (
    AlertManager,
    AlertConfig,
    AlertSeverity,
    AlertCategory,
    AlertDeduplicator,
    AlertRateLimiter,
)


class TestAlertDeduplicator:
    """Tests for alert deduplication."""

    @pytest.mark.asyncio
    async def test_first_alert_passes(self):
        """First alert should always be sent."""
        dedup = AlertDeduplicator(window_seconds=60)
        
        result = await dedup.should_send(
            AlertCategory.RISK_VIOLATION,
            AlertSeverity.WARNING,
            "Test Alert"
        )
        
        assert result is True

    @pytest.mark.asyncio
    async def test_duplicate_alert_blocked(self):
        """Same alert within window should be blocked."""
        dedup = AlertDeduplicator(window_seconds=60)
        
        # First call passes
        await dedup.should_send(
            AlertCategory.RISK_VIOLATION,
            AlertSeverity.WARNING,
            "Test Alert"
        )
        
        # Second call blocked
        result = await dedup.should_send(
            AlertCategory.RISK_VIOLATION,
            AlertSeverity.WARNING,
            "Test Alert"
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_different_alerts_pass(self):
        """Different alerts should not be deduplicated."""
        dedup = AlertDeduplicator(window_seconds=60)
        
        result1 = await dedup.should_send(
            AlertCategory.RISK_VIOLATION,
            AlertSeverity.WARNING,
            "Alert 1"
        )
        
        result2 = await dedup.should_send(
            AlertCategory.ORDER_FAILURE,
            AlertSeverity.ERROR,
            "Alert 2"
        )
        
        assert result1 is True
        assert result2 is True


class TestAlertRateLimiter:
    """Tests for alert rate limiting."""

    @pytest.mark.asyncio
    async def test_under_limit_passes(self):
        """Alerts under rate limit should pass."""
        limiter = AlertRateLimiter(max_per_minute=10)
        
        for _ in range(5):
            result = await limiter.acquire()
            assert result is True

    @pytest.mark.asyncio
    async def test_over_limit_blocked(self):
        """Alerts over rate limit should be blocked."""
        limiter = AlertRateLimiter(max_per_minute=3)
        
        # First 3 pass
        for _ in range(3):
            await limiter.acquire()
        
        # 4th blocked
        result = await limiter.acquire()
        assert result is False


class TestAlertManager:
    """Tests for AlertManager."""

    @pytest.fixture
    def alert_config(self):
        """Create test config."""
        return AlertConfig(
            slack_webhook_url="https://hooks.slack.com/test",
            pagerduty_routing_key="test-routing-key",
            environment="test",
            dedup_window_seconds=60,
            rate_limit_per_minute=100,
        )

    @pytest.fixture
    def alert_manager(self, alert_config):
        """Create test alert manager."""
        return AlertManager(alert_config)

    @pytest.mark.asyncio
    async def test_send_alert_to_slack(self, alert_manager):
        """Test Slack alert delivery."""
        with patch.object(alert_manager, "_send_slack", new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = True
            
            # Bypass PagerDuty for INFO level
            result = await alert_manager.send_alert(
                category=AlertCategory.SYSTEM_ERROR,
                severity=AlertSeverity.INFO,
                title="Test Alert",
                description="Test description",
                dedup=False,  # Disable dedup for test
            )
            
            assert result is True
            mock_slack.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_alert_to_pagerduty(self, alert_manager):
        """Test PagerDuty alert delivery for critical alerts."""
        with patch.object(alert_manager, "_send_slack", new_callable=AsyncMock) as mock_slack, \
             patch.object(alert_manager, "_send_pagerduty", new_callable=AsyncMock) as mock_pd:
            mock_slack.return_value = True
            mock_pd.return_value = True
            
            result = await alert_manager.send_alert(
                category=AlertCategory.RISK_VIOLATION,
                severity=AlertSeverity.CRITICAL,
                title="Critical Alert",
                description="Critical description",
                dedup=False,
            )
            
            assert result is True
            mock_slack.assert_called_once()
            mock_pd.assert_called_once()

    @pytest.mark.asyncio
    async def test_risk_violation_helper(self, alert_manager):
        """Test risk_violation convenience method."""
        with patch.object(alert_manager, "send_alert", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            
            await alert_manager.risk_violation(
                user_id=123,
                metric_name="daily_loss",
                current_value=Decimal("4500.00"),
                limit_value=Decimal("5000.00"),
                severity=AlertSeverity.WARNING,
            )
            
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[1]["category"] == AlertCategory.RISK_VIOLATION
            assert call_args[1]["severity"] == AlertSeverity.WARNING
            assert "daily_loss" in call_args[1]["title"]

    @pytest.mark.asyncio
    async def test_order_failure_helper(self, alert_manager):
        """Test order_failure convenience method."""
        with patch.object(alert_manager, "send_alert", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            
            await alert_manager.order_failure(
                order_id="order-123",
                symbol="AAPL",
                error="Insufficient buying power",
                user_id=456,
            )
            
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[1]["category"] == AlertCategory.ORDER_FAILURE
            assert call_args[1]["severity"] == AlertSeverity.ERROR
            assert "AAPL" in call_args[1]["title"]

    @pytest.mark.asyncio
    async def test_deduplication_works(self, alert_manager):
        """Test that deduplication prevents duplicate alerts."""
        with patch.object(alert_manager, "_send_slack", new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = True
            
            # First alert sent
            await alert_manager.send_alert(
                category=AlertCategory.SYSTEM_ERROR,
                severity=AlertSeverity.INFO,
                title="Duplicate Test",
                description="Test",
                dedup=True,
            )
            
            # Second alert (same content) blocked
            result = await alert_manager.send_alert(
                category=AlertCategory.SYSTEM_ERROR,
                severity=AlertSeverity.INFO,
                title="Duplicate Test",
                description="Test",
                dedup=True,
            )
            
            # Only called once due to dedup
            assert mock_slack.call_count == 1
            assert result is False

    @pytest.mark.asyncio
    async def test_no_channels_configured(self):
        """Test behavior when no channels are configured."""
        config = AlertConfig()  # No webhook URLs
        manager = AlertManager(config)
        
        result = await manager.send_alert(
            category=AlertCategory.SYSTEM_ERROR,
            severity=AlertSeverity.ERROR,
            title="Test",
            description="Test",
            dedup=False,
        )
        
        assert result is False


class TestSlackPayload:
    """Test Slack message formatting."""

    @pytest.fixture
    def alert_manager(self):
        config = AlertConfig(
            slack_webhook_url="https://hooks.slack.com/test",
            environment="test",
        )
        return AlertManager(config)

    def test_severity_emoji(self, alert_manager):
        """Test emoji mapping for severities."""
        assert ":information_source:" in alert_manager._severity_emoji(AlertSeverity.INFO)
        assert ":warning:" in alert_manager._severity_emoji(AlertSeverity.WARNING)
        assert ":x:" in alert_manager._severity_emoji(AlertSeverity.ERROR)
        assert ":rotating_light:" in alert_manager._severity_emoji(AlertSeverity.CRITICAL)

    def test_severity_color(self, alert_manager):
        """Test color mapping for severities."""
        # Green for info
        assert alert_manager._severity_color(AlertSeverity.INFO) == "#36a64f"
        # Red for error
        assert alert_manager._severity_color(AlertSeverity.ERROR) == "#dc3545"
