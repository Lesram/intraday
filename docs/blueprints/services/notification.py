"""
Module 79: Notification Service
Comprehensive multi-channel notification system for trading platform alerts.
"""

import asyncio
import json
import smtplib
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Set, Callable
import logging
import uuid
import re
from pathlib import Path
from urllib.parse import urlencode
import hashlib
import hmac
import base64

# For HTTP requests - use urllib for simplicity instead of aiohttp
import urllib.request
import urllib.parse
import urllib.error

# Configure logging
logger = logging.getLogger(__name__)


class NotificationChannel(Enum):
    """Notification delivery channels."""
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"
    SLACK = "slack"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    IN_APP = "in_app"


class NotificationPriority(Enum):
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
    CRITICAL = "critical"


class NotificationStatus(Enum):
    """Notification delivery status."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRY = "retry"
    CANCELLED = "cancelled"


class NotificationType(Enum):
    """Types of notifications."""
    TRADE_ALERT = "trade_alert"
    RISK_WARNING = "risk_warning"
    COMPLIANCE_VIOLATION = "compliance_violation"
    SYSTEM_ALERT = "system_alert"
    PRICE_ALERT = "price_alert"
    POSITION_ALERT = "position_alert"
    MARGIN_CALL = "margin_call"
    AUTHENTICATION_ALERT = "authentication_alert"
    MAINTENANCE_NOTICE = "maintenance_notice"
    REPORT_READY = "report_ready"
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    CUSTOM = "custom"


@dataclass
class NotificationTemplate:
    """Notification template structure."""
    template_id: str
    name: str
    channel: NotificationChannel
    notification_type: NotificationType
    subject_template: str
    body_template: str
    variables: List[str] = field(default_factory=list)
    is_html: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class NotificationRecipient:
    """Notification recipient information."""
    recipient_id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    push_tokens: List[str] = field(default_factory=list)
    webhook_url: Optional[str] = None
    slack_channel: Optional[str] = None
    discord_channel: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    preferences: Dict[NotificationChannel, bool] = field(default_factory=dict)
    timezone: str = "UTC"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class NotificationMessage:
    """Notification message structure."""
    message_id: str
    recipient: NotificationRecipient
    channel: NotificationChannel
    notification_type: NotificationType
    priority: NotificationPriority
    subject: str
    body: str
    variables: Dict[str, Any] = field(default_factory=dict)
    attachments: List[str] = field(default_factory=list)
    scheduled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    status: NotificationStatus = NotificationStatus.PENDING
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class NotificationConfig:
    """Notification service configuration."""
    # Email configuration
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    from_email: str = "noreply@tradingplatform.com"
    from_name: str = "Trading Platform"
    
    # SMS configuration
    sms_provider: str = "twilio"  # twilio, aws_sns, etc.
    sms_api_key: str = ""
    sms_api_secret: str = ""
    sms_from_number: str = ""
    
    # Push notification configuration
    push_provider: str = "firebase"  # firebase, apns, etc.
    push_api_key: str = ""
    push_project_id: str = ""
    
    # Webhook configuration
    webhook_timeout: int = 30
    webhook_retries: int = 3
    
    # Rate limiting
    rate_limit_per_minute: int = 100
    rate_limit_per_hour: int = 1000
    
    # Retry configuration
    retry_delay_seconds: int = 60
    max_retry_delay: int = 3600


class NotificationProvider(ABC):
    """Abstract base class for notification providers."""
    
    @abstractmethod
    async def send(self, message: NotificationMessage) -> bool:
        """Send a notification message."""
        pass
    
    @abstractmethod
    async def validate_config(self) -> bool:
        """Validate provider configuration."""
        pass


class EmailProvider(NotificationProvider):
    """Email notification provider."""
    
    def __init__(self, config: NotificationConfig):
        self.config = config
    
    async def send(self, message: NotificationMessage) -> bool:
        """Send email notification."""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = message.subject
            msg['From'] = f"{self.config.from_name} <{self.config.from_email}>"
            msg['To'] = message.recipient.email
            
            # Add body
            if message.body:
                if '<html>' in message.body.lower() or '<body>' in message.body.lower():
                    msg.attach(MIMEText(message.body, 'html'))
                else:
                    msg.attach(MIMEText(message.body, 'plain'))
            
            # Add attachments
            for attachment_path in message.attachments:
                if Path(attachment_path).exists():
                    with open(attachment_path, "rb") as attachment:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(attachment.read())
                    
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= {Path(attachment_path).name}'
                    )
                    msg.attach(part)
            
            # Send email
            context = ssl.create_default_context()
            
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                if self.config.smtp_use_tls:
                    server.starttls(context=context)
                
                if self.config.smtp_username and self.config.smtp_password:
                    server.login(self.config.smtp_username, self.config.smtp_password)
                
                server.send_message(msg)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    async def validate_config(self) -> bool:
        """Validate email configuration."""
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                if self.config.smtp_use_tls:
                    server.starttls(context=context)
                
                if self.config.smtp_username and self.config.smtp_password:
                    server.login(self.config.smtp_username, self.config.smtp_password)
            
            return True
        except Exception as e:
            logger.error(f"Email config validation failed: {e}")
            return False


class SMSProvider(NotificationProvider):
    """SMS notification provider."""
    
    def __init__(self, config: NotificationConfig):
        self.config = config
    
    async def send(self, message: NotificationMessage) -> bool:
        """Send SMS notification."""
        try:
            if self.config.sms_provider == "twilio":
                return await self._send_twilio_sms(message)
            elif self.config.sms_provider == "aws_sns":
                return await self._send_aws_sns_sms(message)
            else:
                logger.error(f"Unknown SMS provider: {self.config.sms_provider}")
                return False
        except Exception as e:
            logger.error(f"Failed to send SMS: {e}")
            return False
    
    async def _send_twilio_sms(self, message: NotificationMessage) -> bool:
        """Send SMS via Twilio."""
        try:
            # Simulate Twilio API call (in real implementation, use Twilio SDK)
            if all([message.recipient.phone, self.config.sms_from_number, message.body]):
                logger.info(f"Would send SMS to {message.recipient.phone}: {message.body[:50]}...")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Twilio SMS failed: {e}")
            return False
    
    async def _send_aws_sns_sms(self, message: NotificationMessage) -> bool:
        """Send SMS via AWS SNS."""
        try:
            # Simulate AWS SNS call (in real implementation, use boto3)
            if all([message.recipient.phone, message.body]):
                logger.info(f"Would send AWS SNS SMS to {message.recipient.phone}: {message.body[:50]}...")
                return True
            return False
        except Exception as e:
            logger.error(f"AWS SNS SMS failed: {e}")
            return False
    
    async def validate_config(self) -> bool:
        """Validate SMS configuration."""
        required_fields = [
            self.config.sms_api_key,
            self.config.sms_api_secret,
            self.config.sms_from_number
        ]
        return all(required_fields)


class PushProvider(NotificationProvider):
    """Push notification provider."""
    
    def __init__(self, config: NotificationConfig):
        self.config = config
    
    async def send(self, message: NotificationMessage) -> bool:
        """Send push notification."""
        try:
            if not message.recipient.push_tokens:
                logger.warning(f"No push tokens for recipient {message.recipient.recipient_id}")
                return False
            
            if self.config.push_provider == "firebase":
                return await self._send_firebase_push(message)
            else:
                logger.error(f"Unknown push provider: {self.config.push_provider}")
                return False
        except Exception as e:
            logger.error(f"Failed to send push notification: {e}")
            return False
    
    async def _send_firebase_push(self, message: NotificationMessage) -> bool:
        """Send push notification via Firebase."""
        try:
            # Simulate Firebase FCM call
            for token in message.recipient.push_tokens:
                payload = {
                    "to": token,
                    "notification": {
                        "title": message.subject,
                        "body": message.body,
                        "priority": message.priority.value
                    },
                    "data": message.variables
                }
                
                logger.info(f"Would send Firebase push to token {token[:20]}...: {message.subject}")
            
            return True
        except Exception as e:
            logger.error(f"Firebase push failed: {e}")
            return False
    
    async def validate_config(self) -> bool:
        """Validate push configuration."""
        return bool(self.config.push_api_key and self.config.push_project_id)


class WebhookProvider(NotificationProvider):
    """Webhook notification provider."""
    
    def __init__(self, config: NotificationConfig):
        self.config = config
    
    async def send(self, message: NotificationMessage) -> bool:
        """Send webhook notification."""
        try:
            if not message.recipient.webhook_url:
                logger.warning(f"No webhook URL for recipient {message.recipient.recipient_id}")
                return False
            
            payload = {
                "message_id": message.message_id,
                "type": message.notification_type.value,
                "priority": message.priority.value,
                "subject": message.subject,
                "body": message.body,
                "recipient": message.recipient.recipient_id,
                "timestamp": message.created_at.isoformat(),
                "variables": message.variables
            }
            
            # For testing purposes, simulate webhook call
            logger.info(f"Would send webhook to {message.recipient.webhook_url}")
            logger.info(f"Payload: {json.dumps(payload, indent=2)}")
            
            # In real implementation, this would make an actual HTTP request
            return True
                    
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")
            return False
    
    async def validate_config(self) -> bool:
        """Validate webhook configuration."""
        return True  # No specific config validation needed


class NotificationService:
    """Comprehensive notification service."""
    
    def __init__(self, config: Optional[NotificationConfig] = None):
        self.config = config or NotificationConfig()
        self.providers: Dict[NotificationChannel, NotificationProvider] = {}
        self.templates: Dict[str, NotificationTemplate] = {}
        self.recipients: Dict[str, NotificationRecipient] = {}
        self.messages: Dict[str, NotificationMessage] = {}
        self.rate_limiter: Dict[str, List[datetime]] = {}
        
        # Initialize providers
        self._initialize_providers()
        self._load_default_templates()
    
    def _initialize_providers(self):
        """Initialize notification providers."""
        self.providers[NotificationChannel.EMAIL] = EmailProvider(self.config)
        self.providers[NotificationChannel.SMS] = SMSProvider(self.config)
        self.providers[NotificationChannel.PUSH] = PushProvider(self.config)
        self.providers[NotificationChannel.WEBHOOK] = WebhookProvider(self.config)
    
    def _load_default_templates(self):
        """Load default notification templates."""
        # Trade alert template
        self.templates["trade_alert_email"] = NotificationTemplate(
            template_id="trade_alert_email",
            name="Trade Alert Email",
            channel=NotificationChannel.EMAIL,
            notification_type=NotificationType.TRADE_ALERT,
            subject_template="Trade Alert: {symbol} - {action}",
            body_template="""
            Dear {recipient_name},
            
            A trade has been executed on your account:
            
            Symbol: {symbol}
            Action: {action}
            Quantity: {quantity}
            Price: {price}
            Total Value: {total_value}
            Timestamp: {timestamp}
            
            Best regards,
            Trading Platform Team
            """,
            variables=["recipient_name", "symbol", "action", "quantity", "price", "total_value", "timestamp"]
        )
        
        # Risk warning template
        self.templates["risk_warning_sms"] = NotificationTemplate(
            template_id="risk_warning_sms",
            name="Risk Warning SMS",
            channel=NotificationChannel.SMS,
            notification_type=NotificationType.RISK_WARNING,
            subject_template="Risk Alert",
            body_template="RISK ALERT: {risk_type} limit exceeded. Current: {current_value}, Limit: {limit_value}. Take action immediately.",
            variables=["risk_type", "current_value", "limit_value"]
        )
        
        # System alert template
        self.templates["system_alert_push"] = NotificationTemplate(
            template_id="system_alert_push",
            name="System Alert Push",
            channel=NotificationChannel.PUSH,
            notification_type=NotificationType.SYSTEM_ALERT,
            subject_template="System Alert",
            body_template="{alert_message}",
            variables=["alert_message"]
        )
    
    async def add_recipient(self, recipient: NotificationRecipient) -> bool:
        """Add a notification recipient."""
        try:
            self.recipients[recipient.recipient_id] = recipient
            return True
        except Exception as e:
            logger.error(f"Failed to add recipient: {e}")
            return False
    
    async def update_recipient(self, recipient_id: str, **updates) -> bool:
        """Update recipient information."""
        try:
            if recipient_id not in self.recipients:
                return False
            
            recipient = self.recipients[recipient_id]
            for key, value in updates.items():
                if hasattr(recipient, key):
                    setattr(recipient, key, value)
            
            return True
        except Exception as e:
            logger.error(f"Failed to update recipient: {e}")
            return False
    
    async def add_template(self, template: NotificationTemplate) -> bool:
        """Add a notification template."""
        try:
            self.templates[template.template_id] = template
            return True
        except Exception as e:
            logger.error(f"Failed to add template: {e}")
            return False
    
    def _render_template(self, template: NotificationTemplate, variables: Dict[str, Any]) -> tuple[str, str]:
        """Render template with variables."""
        try:
            subject = template.subject_template
            body = template.body_template
            
            for var_name, var_value in variables.items():
                placeholder = f"{{{var_name}}}"
                subject = subject.replace(placeholder, str(var_value))
                body = body.replace(placeholder, str(var_value))
            
            return subject, body
        except Exception as e:
            logger.error(f"Failed to render template: {e}")
            return template.subject_template, template.body_template
    
    def _check_rate_limit(self, recipient_id: str) -> bool:
        """Check if recipient is within rate limits."""
        now = datetime.now(timezone.utc)
        
        if recipient_id not in self.rate_limiter:
            self.rate_limiter[recipient_id] = []
        
        # Clean old entries
        cutoff_time = now - timedelta(minutes=1)
        self.rate_limiter[recipient_id] = [
            ts for ts in self.rate_limiter[recipient_id] if ts > cutoff_time
        ]
        
        # Check rate limit
        if len(self.rate_limiter[recipient_id]) >= self.config.rate_limit_per_minute:
            return False
        
        # Add current timestamp
        self.rate_limiter[recipient_id].append(now)
        return True
    
    async def send_notification(
        self,
        recipient_id: str,
        channel: NotificationChannel,
        notification_type: NotificationType,
        subject: str,
        body: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        variables: Optional[Dict[str, Any]] = None,
        template_id: Optional[str] = None,
        scheduled_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
        attachments: Optional[List[str]] = None
    ) -> Optional[str]:
        """Send a notification."""
        try:
            # Get recipient
            if recipient_id not in self.recipients:
                logger.error(f"Recipient {recipient_id} not found")
                return None
            
            recipient = self.recipients[recipient_id]
            
            # Check rate limit
            if not self._check_rate_limit(recipient_id):
                logger.warning(f"Rate limit exceeded for recipient {recipient_id}")
                return None
            
            # Check recipient preferences
            if channel in recipient.preferences and not recipient.preferences[channel]:
                logger.info(f"Recipient {recipient_id} has disabled {channel.value} notifications")
                return None
            
            # Use template if provided
            if template_id and template_id in self.templates:
                template = self.templates[template_id]
                if template.channel == channel and template.notification_type == notification_type:
                    rendered_subject, rendered_body = self._render_template(
                        template, variables or {}
                    )
                    subject = rendered_subject
                    body = rendered_body
            
            # Create message
            message = NotificationMessage(
                message_id=str(uuid.uuid4()),
                recipient=recipient,
                channel=channel,
                notification_type=notification_type,
                priority=priority,
                subject=subject,
                body=body,
                variables=variables or {},
                attachments=attachments or [],
                scheduled_at=scheduled_at,
                expires_at=expires_at
            )
            
            # Store message
            self.messages[message.message_id] = message
            
            # Send immediately if not scheduled
            if not scheduled_at or scheduled_at <= datetime.now(timezone.utc):
                await self._send_message(message)
            
            return message.message_id
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return None
    
    async def _send_message(self, message: NotificationMessage) -> bool:
        """Send a message via the appropriate provider."""
        try:
            # Check if message has expired
            if message.expires_at and datetime.now(timezone.utc) > message.expires_at:
                message.status = NotificationStatus.CANCELLED
                return False
            
            # Check channel availability and recipient contact info
            if message.channel == NotificationChannel.EMAIL and not message.recipient.email:
                logger.warning(f"No email address for recipient {message.recipient.recipient_id}")
                message.status = NotificationStatus.FAILED
                message.error_message = "No email address"
                return False
            
            if message.channel == NotificationChannel.SMS and not message.recipient.phone:
                logger.warning(f"No phone number for recipient {message.recipient.recipient_id}")
                message.status = NotificationStatus.FAILED
                message.error_message = "No phone number"
                return False
            
            # Get provider
            provider = self.providers.get(message.channel)
            if not provider:
                logger.error(f"No provider for channel {message.channel.value}")
                message.status = NotificationStatus.FAILED
                message.error_message = f"No provider for {message.channel.value}"
                return False
            
            # Send message
            success = await provider.send(message)
            
            if success:
                message.status = NotificationStatus.SENT
                message.sent_at = datetime.now(timezone.utc)
                return True
            else:
                message.status = NotificationStatus.FAILED
                message.error_message = "Provider send failed"
                
                # Retry logic
                if message.retry_count < message.max_retries:
                    message.retry_count += 1
                    message.status = NotificationStatus.RETRY
                    # Schedule retry (implement retry queue in production)
                    logger.info(f"Scheduling retry {message.retry_count} for message {message.message_id}")
                
                return False
                
        except Exception as e:
            logger.error(f"Failed to send message {message.message_id}: {e}")
            message.status = NotificationStatus.FAILED
            message.error_message = str(e)
            return False
    
    async def send_bulk_notification(
        self,
        recipient_ids: List[str],
        channel: NotificationChannel,
        notification_type: NotificationType,
        subject: str,
        body: str,
        **kwargs
    ) -> List[Optional[str]]:
        """Send notification to multiple recipients."""
        tasks = []
        for recipient_id in recipient_ids:
            task = self.send_notification(
                recipient_id, channel, notification_type, subject, body, **kwargs
            )
            tasks.append(task)
        
        return await asyncio.gather(*tasks, return_exceptions=True)
    
    async def get_message_status(self, message_id: str) -> Optional[NotificationStatus]:
        """Get message delivery status."""
        if message_id in self.messages:
            return self.messages[message_id].status
        return None
    
    async def get_message_history(
        self,
        recipient_id: Optional[str] = None,
        channel: Optional[NotificationChannel] = None,
        notification_type: Optional[NotificationType] = None,
        status: Optional[NotificationStatus] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[NotificationMessage]:
        """Get message history with filtering."""
        messages = list(self.messages.values())
        
        # Apply filters
        if recipient_id:
            messages = [m for m in messages if m.recipient.recipient_id == recipient_id]
        if channel:
            messages = [m for m in messages if m.channel == channel]
        if notification_type:
            messages = [m for m in messages if m.notification_type == notification_type]
        if status:
            messages = [m for m in messages if m.status == status]
        if start_date:
            messages = [m for m in messages if m.created_at >= start_date]
        if end_date:
            messages = [m for m in messages if m.created_at <= end_date]
        
        # Sort by creation time and limit
        messages.sort(key=lambda m: m.created_at, reverse=True)
        return messages[:limit]
    
    async def get_delivery_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get notification delivery statistics."""
        messages = list(self.messages.values())
        
        if start_date:
            messages = [m for m in messages if m.created_at >= start_date]
        if end_date:
            messages = [m for m in messages if m.created_at <= end_date]
        
        if not messages:
            return {
                "total_messages": 0,
                "by_status": {},
                "by_channel": {},
                "by_type": {},
                "by_priority": {},
                "success_rate": 0.0
            }
        
        # Calculate statistics
        by_status = {}
        by_channel = {}
        by_type = {}
        by_priority = {}
        
        for message in messages:
            # Status stats
            status = message.status.value
            by_status[status] = by_status.get(status, 0) + 1
            
            # Channel stats
            channel = message.channel.value
            by_channel[channel] = by_channel.get(channel, 0) + 1
            
            # Type stats
            msg_type = message.notification_type.value
            by_type[msg_type] = by_type.get(msg_type, 0) + 1
            
            # Priority stats
            priority = message.priority.value
            by_priority[priority] = by_priority.get(priority, 0) + 1
        
        # Calculate success rate
        successful = by_status.get(NotificationStatus.SENT.value, 0) + by_status.get(NotificationStatus.DELIVERED.value, 0)
        success_rate = (successful / len(messages)) * 100 if messages else 0
        
        return {
            "total_messages": len(messages),
            "by_status": by_status,
            "by_channel": by_channel,
            "by_type": by_type,
            "by_priority": by_priority,
            "success_rate": round(success_rate, 2)
        }
    
    async def cancel_message(self, message_id: str) -> bool:
        """Cancel a scheduled message."""
        try:
            if message_id in self.messages:
                message = self.messages[message_id]
                if message.status == NotificationStatus.PENDING:
                    message.status = NotificationStatus.CANCELLED
                    return True
            return False
        except Exception as e:
            logger.error(f"Failed to cancel message: {e}")
            return False
    
    async def retry_failed_messages(self, max_retries: Optional[int] = None) -> int:
        """Retry failed messages."""
        retry_count = 0
        for message in self.messages.values():
            if message.status == NotificationStatus.RETRY:
                if max_retries is None or message.retry_count <= max_retries:
                    success = await self._send_message(message)
                    if success:
                        retry_count += 1
        
        return retry_count
    
    async def validate_providers(self) -> Dict[NotificationChannel, bool]:
        """Validate all notification providers."""
        results = {}
        for channel, provider in self.providers.items():
            try:
                results[channel] = await provider.validate_config()
            except Exception as e:
                logger.error(f"Provider validation failed for {channel.value}: {e}")
                results[channel] = False
        
        return results


# Global notification service instance
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get the global notification service instance."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service


# Convenience functions
async def send_notification(
    recipient_id: str,
    channel: NotificationChannel,
    notification_type: NotificationType,
    subject: str,
    body: str,
    **kwargs
) -> Optional[str]:
    """Convenience function to send a notification."""
    service = get_notification_service()
    return await service.send_notification(
        recipient_id, channel, notification_type, subject, body, **kwargs
    )


async def send_email(
    recipient_id: str,
    subject: str,
    body: str,
    **kwargs
) -> Optional[str]:
    """Convenience function to send an email."""
    return await send_notification(
        recipient_id,
        NotificationChannel.EMAIL,
        NotificationType.CUSTOM,
        subject,
        body,
        **kwargs
    )


async def send_sms(
    recipient_id: str,
    message: str,
    **kwargs
) -> Optional[str]:
    """Convenience function to send an SMS."""
    return await send_notification(
        recipient_id,
        NotificationChannel.SMS,
        NotificationType.CUSTOM,
        "SMS",
        message,
        **kwargs
    )


async def send_push(
    recipient_id: str,
    title: str,
    message: str,
    **kwargs
) -> Optional[str]:
    """Convenience function to send a push notification."""
    return await send_notification(
        recipient_id,
        NotificationChannel.PUSH,
        NotificationType.CUSTOM,
        title,
        message,
        **kwargs
    )


# Exception classes
class NotificationError(Exception):
    """Base notification service exception."""
    pass


class NotificationConfigError(NotificationError):
    """Notification configuration exception."""
    pass


class NotificationDeliveryError(NotificationError):
    """Notification delivery exception."""
    pass