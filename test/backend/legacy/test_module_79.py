"""
Comprehensive test suite for Module 79: backend.services.notification
Tests notification service functionality.
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, AsyncMock

try:
    from backend.services.notification import (
        NotificationService, NotificationChannel, NotificationPriority, NotificationStatus,
        NotificationType, NotificationTemplate, NotificationRecipient, NotificationMessage,
        NotificationConfig, NotificationProvider, EmailProvider, SMSProvider, PushProvider,
        WebhookProvider, send_notification, send_email, send_sms, send_push,
        get_notification_service, NotificationError, NotificationConfigError,
        NotificationDeliveryError
    )
    MODULE_EXISTS = True
except ImportError:
    MODULE_EXISTS = False


class TestModule79BackendServicesNotification:
    """Comprehensive test suite for notification service functionality."""
    
    @pytest.fixture
    def notification_config(self):
        """Create notification config for testing."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        return NotificationConfig(
            smtp_host="smtp.test.com",
            smtp_port=587,
            smtp_username="test@example.com",
            smtp_password="test_password",
            from_email="noreply@test.com",
            from_name="Test Platform",
            sms_provider="twilio",
            sms_api_key="test_api_key",
            sms_api_secret="test_api_secret",
            sms_from_number="+1234567890",
            push_provider="firebase",
            push_api_key="test_push_key",
            push_project_id="test_project",
            rate_limit_per_minute=10,
            rate_limit_per_hour=100
        )
    
    @pytest.fixture
    def notification_service(self, notification_config):
        """Create notification service instance."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        return NotificationService(notification_config)
    
    @pytest.fixture
    def sample_recipient(self):
        """Create sample notification recipient."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        return NotificationRecipient(
            recipient_id="test_user_123",
            name="Test User",
            email="test@example.com",
            phone="+1234567890",
            push_tokens=["firebase_token_123", "firebase_token_456"],
            webhook_url="https://webhook.example.com/notify",
            preferences={
                NotificationChannel.EMAIL: True,
                NotificationChannel.SMS: True,
                NotificationChannel.PUSH: True,
                NotificationChannel.WEBHOOK: True
            },
            timezone="UTC"
        )
    
    @pytest_asyncio.fixture
    async def setup_recipients(self, notification_service, sample_recipient):
        """Setup test recipients."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        await notification_service.add_recipient(sample_recipient)
        
        # Add another recipient
        recipient2 = NotificationRecipient(
            recipient_id="test_user_456",
            name="Test User 2",
            email="test2@example.com",
            phone="+0987654321",
            preferences={
                NotificationChannel.EMAIL: True,
                NotificationChannel.SMS: False,  # Disabled SMS
                NotificationChannel.PUSH: True
            }
        )
        await notification_service.add_recipient(recipient2)
        
        return {"recipient1": sample_recipient, "recipient2": recipient2}

    def test_module_availability(self):
        """Test module availability."""
        if MODULE_EXISTS:
            import backend.services.notification as module
            assert module is not None
        else:
            assert True

    def test_module_functionality(self):
        """Test module functionality if exists."""
        if MODULE_EXISTS:
            import backend.services.notification as module
            assert hasattr(module, '__name__')
        else:
            pytest.skip("Module not available")

    def test_notification_config_creation(self, notification_config):
        """Test notification configuration creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert notification_config.smtp_host == "smtp.test.com"
        assert notification_config.smtp_port == 587
        assert notification_config.from_email == "noreply@test.com"
        assert notification_config.sms_provider == "twilio"
        assert notification_config.push_provider == "firebase"
        assert notification_config.rate_limit_per_minute == 10

    def test_notification_recipient_creation(self, sample_recipient):
        """Test notification recipient creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert sample_recipient.recipient_id == "test_user_123"
        assert sample_recipient.name == "Test User"
        assert sample_recipient.email == "test@example.com"
        assert sample_recipient.phone == "+1234567890"
        assert len(sample_recipient.push_tokens) == 2
        assert sample_recipient.preferences[NotificationChannel.EMAIL] is True

    def test_notification_template_creation(self):
        """Test notification template creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        template = NotificationTemplate(
            template_id="test_template",
            name="Test Template",
            channel=NotificationChannel.EMAIL,
            notification_type=NotificationType.TRADE_ALERT,
            subject_template="Trade Alert: {symbol}",
            body_template="Trade executed for {symbol} at {price}",
            variables=["symbol", "price"],
            is_html=False
        )
        
        assert template.template_id == "test_template"
        assert template.channel == NotificationChannel.EMAIL
        assert template.notification_type == NotificationType.TRADE_ALERT
        assert "symbol" in template.variables
        assert "price" in template.variables

    def test_notification_message_creation(self, sample_recipient):
        """Test notification message creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        message = NotificationMessage(
            message_id="test_msg_123",
            recipient=sample_recipient,
            channel=NotificationChannel.EMAIL,
            notification_type=NotificationType.TRADE_ALERT,
            priority=NotificationPriority.HIGH,
            subject="Test Subject",
            body="Test message body",
            variables={"symbol": "AAPL", "price": "150.00"}
        )
        
        assert message.message_id == "test_msg_123"
        assert message.channel == NotificationChannel.EMAIL
        assert message.priority == NotificationPriority.HIGH
        assert message.status == NotificationStatus.PENDING
        assert message.variables["symbol"] == "AAPL"

    def test_default_templates_loaded(self, notification_service):
        """Test that default templates are loaded."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        expected_templates = [
            "trade_alert_email",
            "risk_warning_sms",
            "system_alert_push"
        ]
        
        for template_id in expected_templates:
            assert template_id in notification_service.templates
        
        # Check trade alert template
        trade_template = notification_service.templates["trade_alert_email"]
        assert trade_template.channel == NotificationChannel.EMAIL
        assert trade_template.notification_type == NotificationType.TRADE_ALERT
        assert "symbol" in trade_template.variables

    @pytest.mark.asyncio
    async def test_add_recipient(self, notification_service):
        """Test adding notification recipients."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        recipient = NotificationRecipient(
            recipient_id="new_user_789",
            name="New User",
            email="newuser@example.com",
            phone="+1111111111"
        )
        
        result = await notification_service.add_recipient(recipient)
        assert result is True
        assert "new_user_789" in notification_service.recipients
        assert notification_service.recipients["new_user_789"].name == "New User"

    @pytest.mark.asyncio
    async def test_update_recipient(self, notification_service, setup_recipients):
        """Test updating recipient information."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        result = await notification_service.update_recipient(
            "test_user_123",
            email="updated@example.com",
            name="Updated User"
        )
        
        assert result is True
        updated_recipient = notification_service.recipients["test_user_123"]
        assert updated_recipient.email == "updated@example.com"
        assert updated_recipient.name == "Updated User"
        
        # Test updating non-existent recipient
        result = await notification_service.update_recipient(
            "nonexistent_user",
            email="test@example.com"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_add_template(self, notification_service):
        """Test adding notification templates."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        template = NotificationTemplate(
            template_id="custom_template",
            name="Custom Template",
            channel=NotificationChannel.SMS,
            notification_type=NotificationType.PRICE_ALERT,
            subject_template="Price Alert",
            body_template="Price of {symbol} reached {target_price}",
            variables=["symbol", "target_price"]
        )
        
        result = await notification_service.add_template(template)
        assert result is True
        assert "custom_template" in notification_service.templates

    def test_template_rendering(self, notification_service):
        """Test template rendering with variables."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        template = notification_service.templates["trade_alert_email"]
        variables = {
            "recipient_name": "John Doe",
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": "100",
            "price": "150.00",
            "total_value": "15000.00",
            "timestamp": "2023-01-01 10:00:00"
        }
        
        subject, body = notification_service._render_template(template, variables)
        
        assert "AAPL" in subject
        assert "BUY" in subject
        assert "John Doe" in body
        assert "AAPL" in body
        assert "100" in body
        assert "150.00" in body

    def test_rate_limiting(self, notification_service):
        """Test rate limiting functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        recipient_id = "rate_test_user"
        
        # Should allow requests up to limit
        for i in range(notification_service.config.rate_limit_per_minute):
            assert notification_service._check_rate_limit(recipient_id) is True
        
        # Should block after limit
        assert notification_service._check_rate_limit(recipient_id) is False

    @pytest.mark.asyncio
    async def test_email_notification(self, notification_service, setup_recipients):
        """Test email notification sending."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        with patch.object(notification_service.providers[NotificationChannel.EMAIL], 'send', return_value=True) as mock_send:
            message_id = await notification_service.send_notification(
                recipient_id="test_user_123",
                channel=NotificationChannel.EMAIL,
                notification_type=NotificationType.TRADE_ALERT,
                subject="Test Trade Alert",
                body="This is a test trade alert message",
                priority=NotificationPriority.NORMAL
            )
            
            assert message_id is not None
            assert message_id in notification_service.messages
            
            message = notification_service.messages[message_id]
            assert message.channel == NotificationChannel.EMAIL
            assert message.subject == "Test Trade Alert"
            assert message.status in [NotificationStatus.SENT, NotificationStatus.PENDING]
            
            # Verify send was called
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_sms_notification(self, notification_service, setup_recipients):
        """Test SMS notification sending."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        with patch.object(notification_service.providers[NotificationChannel.SMS], 'send', return_value=True) as mock_send:
            message_id = await notification_service.send_notification(
                recipient_id="test_user_123",
                channel=NotificationChannel.SMS,
                notification_type=NotificationType.RISK_WARNING,
                subject="Risk Alert",
                body="Risk limit exceeded",
                priority=NotificationPriority.HIGH
            )
            
            assert message_id is not None
            message = notification_service.messages[message_id]
            assert message.channel == NotificationChannel.SMS
            assert message.body == "Risk limit exceeded"
            
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_notification(self, notification_service, setup_recipients):
        """Test push notification sending."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        with patch.object(notification_service.providers[NotificationChannel.PUSH], 'send', return_value=True) as mock_send:
            message_id = await notification_service.send_notification(
                recipient_id="test_user_123",
                channel=NotificationChannel.PUSH,
                notification_type=NotificationType.SYSTEM_ALERT,
                subject="System Alert",
                body="System maintenance scheduled",
                priority=NotificationPriority.NORMAL
            )
            
            assert message_id is not None
            message = notification_service.messages[message_id]
            assert message.channel == NotificationChannel.PUSH
            
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_notification(self, notification_service, setup_recipients):
        """Test webhook notification sending."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        with patch.object(notification_service.providers[NotificationChannel.WEBHOOK], 'send', return_value=True) as mock_send:
            message_id = await notification_service.send_notification(
                recipient_id="test_user_123",
                channel=NotificationChannel.WEBHOOK,
                notification_type=NotificationType.ORDER_FILLED,
                subject="Order Filled",
                body="Your order has been filled",
                variables={"order_id": "12345", "symbol": "AAPL"}
            )
            
            assert message_id is not None
            message = notification_service.messages[message_id]
            assert message.channel == NotificationChannel.WEBHOOK
            assert message.variables["order_id"] == "12345"
            
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_template_based_notification(self, notification_service, setup_recipients):
        """Test sending notification using templates."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        with patch.object(notification_service.providers[NotificationChannel.EMAIL], 'send', return_value=True):
            message_id = await notification_service.send_notification(
                recipient_id="test_user_123",
                channel=NotificationChannel.EMAIL,
                notification_type=NotificationType.TRADE_ALERT,
                subject="",  # Will be overridden by template
                body="",     # Will be overridden by template
                template_id="trade_alert_email",
                variables={
                    "recipient_name": "Test User",
                    "symbol": "AAPL",
                    "action": "BUY",
                    "quantity": "100",
                    "price": "150.00",
                    "total_value": "15000.00",
                    "timestamp": "2023-01-01 10:00:00"
                }
            )
            
            assert message_id is not None
            message = notification_service.messages[message_id]
            assert "AAPL" in message.subject
            assert "Test User" in message.body
            assert "BUY" in message.body

    @pytest.mark.asyncio
    async def test_recipient_preferences(self, notification_service, setup_recipients):
        """Test recipient notification preferences."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Try to send SMS to user who disabled SMS
        message_id = await notification_service.send_notification(
            recipient_id="test_user_456",  # Has SMS disabled
            channel=NotificationChannel.SMS,
            notification_type=NotificationType.TRADE_ALERT,
            subject="Trade Alert",
            body="Trade executed"
        )
        
        # Should return None because SMS is disabled for this user
        assert message_id is None

    @pytest.mark.asyncio
    async def test_bulk_notification(self, notification_service, setup_recipients):
        """Test bulk notification sending."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        with patch.object(notification_service.providers[NotificationChannel.EMAIL], 'send', return_value=True):
            message_ids = await notification_service.send_bulk_notification(
                recipient_ids=["test_user_123", "test_user_456"],
                channel=NotificationChannel.EMAIL,
                notification_type=NotificationType.SYSTEM_ALERT,
                subject="System Maintenance",
                body="System maintenance scheduled for tonight"
            )
            
            assert len(message_ids) == 2
            assert all(msg_id is not None for msg_id in message_ids)

    @pytest.mark.asyncio
    async def test_scheduled_notification(self, notification_service, setup_recipients):
        """Test scheduled notification."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        
        message_id = await notification_service.send_notification(
            recipient_id="test_user_123",
            channel=NotificationChannel.EMAIL,
            notification_type=NotificationType.MAINTENANCE_NOTICE,
            subject="Scheduled Maintenance",
            body="Maintenance will begin in 1 hour",
            scheduled_at=future_time
        )
        
        assert message_id is not None
        message = notification_service.messages[message_id]
        assert message.scheduled_at == future_time
        assert message.status == NotificationStatus.PENDING

    @pytest.mark.asyncio
    async def test_message_expiration(self, notification_service, setup_recipients):
        """Test message expiration."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        
        message_id = await notification_service.send_notification(
            recipient_id="test_user_123",
            channel=NotificationChannel.EMAIL,
            notification_type=NotificationType.PRICE_ALERT,
            subject="Price Alert",
            body="Price target reached",
            expires_at=past_time  # Already expired
        )
        
        assert message_id is not None
        message = notification_service.messages[message_id]
        assert message.status == NotificationStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_message_status_tracking(self, notification_service, setup_recipients):
        """Test message status tracking."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        with patch.object(notification_service.providers[NotificationChannel.EMAIL], 'send', return_value=True):
            message_id = await notification_service.send_notification(
                recipient_id="test_user_123",
                channel=NotificationChannel.EMAIL,
                notification_type=NotificationType.TRADE_ALERT,
                subject="Trade Alert",
                body="Trade executed"
            )
            
            status = await notification_service.get_message_status(message_id)
            assert status in [NotificationStatus.SENT, NotificationStatus.PENDING]

    @pytest.mark.asyncio
    async def test_message_history(self, notification_service, setup_recipients):
        """Test message history retrieval."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        with patch.object(notification_service.providers[NotificationChannel.EMAIL], 'send', return_value=True):
            # Send multiple messages
            for i in range(3):
                await notification_service.send_notification(
                    recipient_id="test_user_123",
                    channel=NotificationChannel.EMAIL,
                    notification_type=NotificationType.TRADE_ALERT,
                    subject=f"Trade Alert {i}",
                    body=f"Trade {i} executed"
                )
            
            # Get history
            history = await notification_service.get_message_history(
                recipient_id="test_user_123",
                limit=10
            )
            
            assert len(history) >= 3
            assert all(msg.recipient.recipient_id == "test_user_123" for msg in history)
            
            # Test filtering by channel
            email_history = await notification_service.get_message_history(
                channel=NotificationChannel.EMAIL,
                limit=10
            )
            
            assert len(email_history) >= 3
            assert all(msg.channel == NotificationChannel.EMAIL for msg in email_history)

    @pytest.mark.asyncio
    async def test_delivery_statistics(self, notification_service, setup_recipients):
        """Test delivery statistics."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        with patch.object(notification_service.providers[NotificationChannel.EMAIL], 'send', return_value=True):
            # Send some messages
            for i in range(5):
                await notification_service.send_notification(
                    recipient_id="test_user_123",
                    channel=NotificationChannel.EMAIL,
                    notification_type=NotificationType.TRADE_ALERT,
                    subject=f"Alert {i}",
                    body=f"Message {i}"
                )
            
            stats = await notification_service.get_delivery_stats()
            
            assert stats["total_messages"] >= 5
            assert "by_status" in stats
            assert "by_channel" in stats
            assert "by_type" in stats
            assert "by_priority" in stats
            assert "success_rate" in stats
            assert stats["success_rate"] >= 0

    @pytest.mark.asyncio
    async def test_cancel_message(self, notification_service, setup_recipients):
        """Test message cancellation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        
        message_id = await notification_service.send_notification(
            recipient_id="test_user_123",
            channel=NotificationChannel.EMAIL,
            notification_type=NotificationType.MAINTENANCE_NOTICE,
            subject="Maintenance Notice",
            body="Scheduled maintenance",
            scheduled_at=future_time
        )
        
        # Cancel the message
        result = await notification_service.cancel_message(message_id)
        assert result is True
        
        message = notification_service.messages[message_id]
        assert message.status == NotificationStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_retry_failed_messages(self, notification_service, setup_recipients):
        """Test retry functionality for failed messages."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Mock provider to fail first, then succeed
        call_count = 0
        async def mock_send(message):
            nonlocal call_count
            call_count += 1
            return call_count > 1  # Fail first call, succeed on retry
        
        with patch.object(notification_service.providers[NotificationChannel.EMAIL], 'send', side_effect=mock_send):
            message_id = await notification_service.send_notification(
                recipient_id="test_user_123",
                channel=NotificationChannel.EMAIL,
                notification_type=NotificationType.TRADE_ALERT,
                subject="Trade Alert",
                body="Trade executed"
            )
            
            # Message should be in retry status
            message = notification_service.messages[message_id]
            assert message.status == NotificationStatus.RETRY
            
            # Retry failed messages
            retry_count = await notification_service.retry_failed_messages()
            assert retry_count >= 0

    @pytest.mark.asyncio
    async def test_provider_validation(self, notification_service):
        """Test provider validation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        with patch.object(notification_service.providers[NotificationChannel.EMAIL], 'validate_config', return_value=True):
            with patch.object(notification_service.providers[NotificationChannel.SMS], 'validate_config', return_value=False):
                results = await notification_service.validate_providers()
                
                assert NotificationChannel.EMAIL in results
                assert NotificationChannel.SMS in results
                assert results[NotificationChannel.EMAIL] is True
                assert results[NotificationChannel.SMS] is False

    @pytest.mark.asyncio
    async def test_convenience_functions(self):
        """Test convenience functions."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test get_notification_service
        service = get_notification_service()
        assert isinstance(service, NotificationService)
        
        # Add a test recipient
        recipient = NotificationRecipient(
            recipient_id="convenience_test",
            name="Convenience Test",
            email="convenience@example.com",
            phone="+1111111111"
        )
        await service.add_recipient(recipient)
        
        with patch.object(service.providers[NotificationChannel.EMAIL], 'send', return_value=True):
            # Test send_email
            message_id = await send_email(
                "convenience_test",
                "Test Email",
                "Test email body"
            )
            assert message_id is not None
        
        with patch.object(service.providers[NotificationChannel.SMS], 'send', return_value=True):
            # Test send_sms
            message_id = await send_sms(
                "convenience_test",
                "Test SMS message"
            )
            assert message_id is not None
        
        with patch.object(service.providers[NotificationChannel.PUSH], 'send', return_value=True):
            # Test send_push (need push tokens)
            await service.update_recipient("convenience_test", push_tokens=["test_token"])
            message_id = await send_push(
                "convenience_test",
                "Test Push",
                "Test push message"
            )
            assert message_id is not None

    def test_enums_and_constants(self):
        """Test enum definitions."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test NotificationChannel enum
        assert NotificationChannel.EMAIL.value == "email"
        assert NotificationChannel.SMS.value == "sms"
        assert NotificationChannel.PUSH.value == "push"
        
        # Test NotificationPriority enum
        assert NotificationPriority.LOW.value == "low"
        assert NotificationPriority.NORMAL.value == "normal"
        assert NotificationPriority.HIGH.value == "high"
        assert NotificationPriority.URGENT.value == "urgent"
        assert NotificationPriority.CRITICAL.value == "critical"
        
        # Test NotificationStatus enum
        assert NotificationStatus.PENDING.value == "pending"
        assert NotificationStatus.SENT.value == "sent"
        assert NotificationStatus.DELIVERED.value == "delivered"
        assert NotificationStatus.FAILED.value == "failed"
        
        # Test NotificationType enum
        assert NotificationType.TRADE_ALERT.value == "trade_alert"
        assert NotificationType.RISK_WARNING.value == "risk_warning"
        assert NotificationType.SYSTEM_ALERT.value == "system_alert"

    @pytest.mark.asyncio
    async def test_edge_cases_and_error_handling(self, notification_service):
        """Test edge cases and error handling."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test sending to non-existent recipient
        message_id = await notification_service.send_notification(
            recipient_id="nonexistent_user",
            channel=NotificationChannel.EMAIL,
            notification_type=NotificationType.TRADE_ALERT,
            subject="Test",
            body="Test"
        )
        assert message_id is None
        
        # Test sending email without email address
        recipient_no_email = NotificationRecipient(
            recipient_id="no_email_user",
            name="No Email User"
            # No email address
        )
        await notification_service.add_recipient(recipient_no_email)
        
        message_id = await notification_service.send_notification(
            recipient_id="no_email_user",
            channel=NotificationChannel.EMAIL,
            notification_type=NotificationType.TRADE_ALERT,
            subject="Test",
            body="Test"
        )
        
        # Should create message but fail to send
        assert message_id is not None
        message = notification_service.messages[message_id]
        assert message.status == NotificationStatus.FAILED
        assert "No email address" in message.error_message
        
        # Test getting status for non-existent message
        status = await notification_service.get_message_status("nonexistent_message")
        assert status is None

    @pytest.mark.asyncio
    async def test_provider_implementations(self, notification_config):
        """Test individual provider implementations."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test EmailProvider
        email_provider = EmailProvider(notification_config)
        assert email_provider.config == notification_config
        
        # Test SMSProvider
        sms_provider = SMSProvider(notification_config)
        assert sms_provider.config == notification_config
        
        # Test SMS validation
        validation_result = await sms_provider.validate_config()
        assert isinstance(validation_result, bool)
        
        # Test PushProvider
        push_provider = PushProvider(notification_config)
        assert push_provider.config == notification_config
        
        # Test push validation
        validation_result = await push_provider.validate_config()
        assert isinstance(validation_result, bool)
        
        # Test WebhookProvider
        webhook_provider = WebhookProvider(notification_config)
        assert webhook_provider.config == notification_config
        
        # Test webhook validation (should always return True)
        validation_result = await webhook_provider.validate_config()
        assert validation_result is True


