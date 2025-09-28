"""
Email Service Module

This module provides comprehensive email functionality including:
- Email sending with various providers (SMTP, cloud services)
- Template management and rendering
- Email delivery tracking and status monitoring
- Bounce and complaint handling
- Email queue management
- Email configuration and validation
"""

import asyncio
import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import uuid
import json
import jinja2
from jinja2 import Environment, FileSystemLoader, BaseLoader

logger = logging.getLogger(__name__)


class EmailStatus(Enum):
    """Email delivery status."""
    PENDING = "pending"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"
    COMPLAINED = "complained"
    REJECTED = "rejected"


class EmailPriority(Enum):
    """Email priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TemplateEngine(Enum):
    """Template rendering engines."""
    JINJA2 = "jinja2"
    SIMPLE = "simple"


@dataclass
class EmailAddress:
    """Email address with optional name."""
    email: str
    name: Optional[str] = None
    
    def __str__(self) -> str:
        if self.name:
            return f'"{self.name}" <{self.email}>'
        return self.email
    
    def to_dict(self) -> Dict[str, str]:
        result = {"email": self.email}
        if self.name:
            result["name"] = self.name
        return result


@dataclass
class EmailAttachment:
    """Email attachment."""
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"
    content_disposition: str = "attachment"


@dataclass
class EmailTemplate:
    """Email template definition."""
    id: str
    name: str
    subject_template: str
    html_template: Optional[str] = None
    text_template: Optional[str] = None
    variables: List[str] = field(default_factory=list)
    engine: TemplateEngine = TemplateEngine.JINJA2
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def render_subject(self, variables: Dict[str, Any]) -> str:
        """Render subject template with variables."""
        if self.engine == TemplateEngine.JINJA2:
            template = jinja2.Template(self.subject_template)
            return template.render(**variables)
        else:
            # Simple string formatting
            return self.subject_template.format(**variables)
    
    def render_html(self, variables: Dict[str, Any]) -> Optional[str]:
        """Render HTML template with variables."""
        if not self.html_template:
            return None
            
        if self.engine == TemplateEngine.JINJA2:
            template = jinja2.Template(self.html_template)
            return template.render(**variables)
        else:
            return self.html_template.format(**variables)
    
    def render_text(self, variables: Dict[str, Any]) -> Optional[str]:
        """Render text template with variables."""
        if not self.text_template:
            return None
            
        if self.engine == TemplateEngine.JINJA2:
            template = jinja2.Template(self.text_template)
            return template.render(**variables)
        else:
            return self.text_template.format(**variables)


@dataclass
class EmailMessage:
    """Email message definition."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    to_addresses: List[EmailAddress] = field(default_factory=list)
    from_address: Optional[EmailAddress] = None
    reply_to: Optional[EmailAddress] = None
    cc_addresses: List[EmailAddress] = field(default_factory=list)
    bcc_addresses: List[EmailAddress] = field(default_factory=list)
    subject: str = ""
    html_content: Optional[str] = None
    text_content: Optional[str] = None
    attachments: List[EmailAttachment] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    priority: EmailPriority = EmailPriority.NORMAL
    template_id: Optional[str] = None
    template_variables: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    scheduled_at: Optional[datetime] = None
    
    def add_to(self, email: str, name: Optional[str] = None) -> None:
        """Add recipient."""
        self.to_addresses.append(EmailAddress(email, name))
    
    def add_cc(self, email: str, name: Optional[str] = None) -> None:
        """Add CC recipient."""
        self.cc_addresses.append(EmailAddress(email, name))
    
    def add_bcc(self, email: str, name: Optional[str] = None) -> None:
        """Add BCC recipient."""
        self.bcc_addresses.append(EmailAddress(email, name))
    
    def add_attachment(self, filename: str, content: bytes, content_type: str = "application/octet-stream") -> None:
        """Add attachment."""
        self.attachments.append(EmailAttachment(filename, content, content_type))


@dataclass
class EmailDeliveryAttempt:
    """Email delivery attempt record."""
    id: str
    email_id: str
    attempted_at: datetime
    provider: str
    status: EmailStatus
    error_message: Optional[str] = None
    response_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmailDeliveryStatus:
    """Comprehensive email delivery status."""
    email_id: str
    current_status: EmailStatus
    delivery_attempts: List[EmailDeliveryAttempt] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    delivered_at: Optional[datetime] = None
    bounced_at: Optional[datetime] = None
    complained_at: Optional[datetime] = None
    bounce_reason: Optional[str] = None
    complaint_reason: Optional[str] = None
    
    def add_attempt(self, provider: str, status: EmailStatus, error: Optional[str] = None) -> None:
        """Add delivery attempt."""
        attempt = EmailDeliveryAttempt(
            id=str(uuid.uuid4()),
            email_id=self.email_id,
            attempted_at=datetime.now(timezone.utc),
            provider=provider,
            status=status,
            error_message=error
        )
        self.delivery_attempts.append(attempt)
        self.current_status = status
        self.updated_at = datetime.now(timezone.utc)
        
        if status == EmailStatus.DELIVERED:
            self.delivered_at = datetime.now(timezone.utc)
        elif status == EmailStatus.BOUNCED:
            self.bounced_at = datetime.now(timezone.utc)
            self.bounce_reason = error
        elif status == EmailStatus.COMPLAINED:
            self.complained_at = datetime.now(timezone.utc)
            self.complaint_reason = error


class EmailProvider(ABC):
    """Abstract base class for email providers."""
    
    @abstractmethod
    async def send_email(self, message: EmailMessage) -> bool:
        """Send email message."""
        pass
    
    @abstractmethod
    async def get_delivery_status(self, message_id: str) -> Optional[EmailStatus]:
        """Get delivery status for a message."""
        pass
    
    @abstractmethod
    def validate_configuration(self) -> bool:
        """Validate provider configuration."""
        pass


class SMTPProvider(EmailProvider):
    """SMTP email provider implementation."""
    
    def __init__(
        self,
        host: str,
        port: int = 587,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = True,
        use_ssl: bool = False,
        timeout: int = 30
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.use_ssl = use_ssl
        self.timeout = timeout
    
    async def send_email(self, message: EmailMessage) -> bool:
        """Send email via SMTP."""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = message.subject
            msg['From'] = str(message.from_address) if message.from_address else ""
            msg['To'] = ", ".join(str(addr) for addr in message.to_addresses)
            
            if message.cc_addresses:
                msg['Cc'] = ", ".join(str(addr) for addr in message.cc_addresses)
            
            if message.reply_to:
                msg['Reply-To'] = str(message.reply_to)
            
            # Add custom headers
            for key, value in message.headers.items():
                msg[key] = value
            
            # Add text content
            if message.text_content:
                text_part = MIMEText(message.text_content, 'plain', 'utf-8')
                msg.attach(text_part)
            
            # Add HTML content
            if message.html_content:
                html_part = MIMEText(message.html_content, 'html', 'utf-8')
                msg.attach(html_part)
            
            # Add attachments
            for attachment in message.attachments:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.content)
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'{attachment.content_disposition}; filename= {attachment.filename}'
                )
                msg.attach(part)
            
            # Send email
            await self._send_smtp(msg, message)
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email via SMTP: {e}")
            return False
    
    async def _send_smtp(self, msg: MIMEMultipart, message: EmailMessage) -> None:
        """Send email using SMTP connection."""
        # Get all recipients
        recipients = []
        recipients.extend(addr.email for addr in message.to_addresses)
        recipients.extend(addr.email for addr in message.cc_addresses)
        recipients.extend(addr.email for addr in message.bcc_addresses)
        
        # Create connection
        if self.use_ssl:
            server = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout)
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
        
        try:
            if self.use_tls and not self.use_ssl:
                server.starttls(context=ssl.create_default_context())
            
            if self.username and self.password:
                server.login(self.username, self.password)
            
            server.send_message(msg, to_addrs=recipients)
            
        finally:
            server.quit()
    
    async def get_delivery_status(self, message_id: str) -> Optional[EmailStatus]:
        """SMTP doesn't provide delivery status tracking."""
        return None
    
    def validate_configuration(self) -> bool:
        """Validate SMTP configuration."""
        try:
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout)
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            
            try:
                if self.use_tls and not self.use_ssl:
                    server.starttls(context=ssl.create_default_context())
                
                if self.username and self.password:
                    server.login(self.username, self.password)
                
                return True
                
            finally:
                server.quit()
                
        except Exception as e:
            logger.error(f"SMTP configuration validation failed: {e}")
            return False


class MockEmailProvider(EmailProvider):
    """Mock email provider for testing."""
    
    def __init__(self):
        self.sent_emails: List[EmailMessage] = []
        self.delivery_statuses: Dict[str, EmailStatus] = {}
        self.should_fail = False
    
    async def send_email(self, message: EmailMessage) -> bool:
        """Mock send email."""
        if self.should_fail:
            return False
        
        self.sent_emails.append(message)
        self.delivery_statuses[message.id] = EmailStatus.SENT
        return True
    
    async def get_delivery_status(self, message_id: str) -> Optional[EmailStatus]:
        """Get mock delivery status."""
        return self.delivery_statuses.get(message_id)
    
    def validate_configuration(self) -> bool:
        """Mock validation always succeeds."""
        return True


class EmailQueue:
    """Email queue for managing email delivery."""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self.processing = False
    
    async def enqueue(self, message: EmailMessage) -> bool:
        """Add email to queue."""
        try:
            self.queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            logger.error("Email queue is full")
            return False
    
    async def dequeue(self) -> Optional[EmailMessage]:
        """Get next email from queue."""
        try:
            message = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            return message
        except asyncio.TimeoutError:
            return None
    
    def size(self) -> int:
        """Get queue size."""
        return self.queue.qsize()
    
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return self.queue.empty()


class EmailService:
    """Comprehensive email service."""
    
    def __init__(
        self,
        default_provider: Optional[EmailProvider] = None,
        default_from_address: Optional[EmailAddress] = None,
        queue_size: int = 1000
    ):
        self.providers: Dict[str, EmailProvider] = {}
        self.default_provider = default_provider
        self.default_from_address = default_from_address
        self.templates: Dict[str, EmailTemplate] = {}
        self.delivery_statuses: Dict[str, EmailDeliveryStatus] = {}
        self.queue = EmailQueue(queue_size)
        self._processing_task: Optional[asyncio.Task] = None
        
        # Add mock provider by default for testing
        if default_provider is None:
            self.default_provider = MockEmailProvider()
        self.providers["mock"] = self.default_provider
    
    def add_provider(self, name: str, provider: EmailProvider) -> None:
        """Add email provider."""
        self.providers[name] = provider
        
        # Set as default if it's the first provider
        if self.default_provider is None:
            self.default_provider = provider
    
    def set_default_provider(self, name: str) -> bool:
        """Set default email provider."""
        if name in self.providers:
            self.default_provider = self.providers[name]
            return True
        return False
    
    def add_template(self, template: EmailTemplate) -> None:
        """Add email template."""
        self.templates[template.id] = template
    
    def get_template(self, template_id: str) -> Optional[EmailTemplate]:
        """Get email template."""
        return self.templates.get(template_id)
    
    def delete_template(self, template_id: str) -> bool:
        """Delete email template."""
        if template_id in self.templates:
            del self.templates[template_id]
            return True
        return False
    
    async def send_email(
        self,
        message: EmailMessage,
        provider_name: Optional[str] = None
    ) -> bool:
        """Send email immediately."""
        try:
            # Select provider
            provider = self._get_provider(provider_name)
            if not provider:
                logger.error("No email provider available")
                return False
            
            # Set default from address if not provided
            if not message.from_address and self.default_from_address:
                message.from_address = self.default_from_address
            
            # Render template if specified
            if message.template_id:
                template = self.get_template(message.template_id)
                if template:
                    message.subject = template.render_subject(message.template_variables)
                    if template.html_template:
                        message.html_content = template.render_html(message.template_variables)
                    if template.text_template:
                        message.text_content = template.render_text(message.template_variables)
            
            # Create delivery status
            status = EmailDeliveryStatus(
                email_id=message.id,
                current_status=EmailStatus.SENDING
            )
            self.delivery_statuses[message.id] = status
            
            # Send email
            success = await provider.send_email(message)
            
            # Update status
            if success:
                status.add_attempt(provider_name or "default", EmailStatus.SENT)
                logger.info(f"Email {message.id} sent successfully")
            else:
                status.add_attempt(provider_name or "default", EmailStatus.FAILED, "Send failed")
                logger.error(f"Failed to send email {message.id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending email {message.id}: {e}")
            if message.id in self.delivery_statuses:
                self.delivery_statuses[message.id].add_attempt(
                    provider_name or "default", EmailStatus.FAILED, str(e)
                )
            return False
    
    async def queue_email(self, message: EmailMessage) -> bool:
        """Add email to queue for later processing."""
        # Set default from address if not provided
        if not message.from_address and self.default_from_address:
            message.from_address = self.default_from_address
        
        # Create delivery status
        status = EmailDeliveryStatus(
            email_id=message.id,
            current_status=EmailStatus.QUEUED
        )
        self.delivery_statuses[message.id] = status
        
        success = await self.queue.enqueue(message)
        if not success:
            status.current_status = EmailStatus.FAILED
            status.add_attempt("queue", EmailStatus.FAILED, "Queue is full")
        
        return success
    
    async def start_queue_processing(self) -> None:
        """Start processing email queue."""
        if self._processing_task and not self._processing_task.done():
            return
        
        self._processing_task = asyncio.create_task(self._process_queue())
        self.queue.processing = True
        logger.info("Email queue processing started")
    
    async def stop_queue_processing(self) -> None:
        """Stop processing email queue."""
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        
        self.queue.processing = False
        logger.info("Email queue processing stopped")
    
    async def _process_queue(self) -> None:
        """Process emails in queue."""
        while True:
            try:
                message = await self.queue.dequeue()
                if message:
                    await self.send_email(message)
                await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing email queue: {e}")
                await asyncio.sleep(1)  # Longer delay on error
    
    def _get_provider(self, provider_name: Optional[str]) -> Optional[EmailProvider]:
        """Get email provider by name or default."""
        if provider_name and provider_name in self.providers:
            return self.providers[provider_name]
        return self.default_provider
    
    async def get_delivery_status(self, email_id: str) -> Optional[EmailDeliveryStatus]:
        """Get email delivery status."""
        return self.delivery_statuses.get(email_id)
    
    async def get_queue_size(self) -> int:
        """Get current queue size."""
        return self.queue.size()
    
    async def validate_email_address(self, email: str) -> bool:
        """Basic email address validation."""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    async def send_template_email(
        self,
        template_id: str,
        to_addresses: List[str],
        variables: Dict[str, Any],
        from_address: Optional[str] = None,
        subject_override: Optional[str] = None
    ) -> List[str]:
        """Send templated email to multiple recipients."""
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")
        
        sent_ids = []
        
        for email_addr in to_addresses:
            if not await self.validate_email_address(email_addr):
                logger.warning(f"Invalid email address: {email_addr}")
                continue
            
            message = EmailMessage(
                template_id=template_id,
                template_variables=variables
            )
            message.add_to(email_addr)
            
            if from_address:
                message.from_address = EmailAddress(from_address)
            
            if subject_override:
                message.subject = subject_override
            
            success = await self.send_email(message)
            if success:
                sent_ids.append(message.id)
        
        return sent_ids
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get email service statistics."""
        total_emails = len(self.delivery_statuses)
        status_counts = {}
        
        for status_obj in self.delivery_statuses.values():
            status = status_obj.current_status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total_emails": total_emails,
            "status_counts": status_counts,
            "queue_size": self.queue.size(),
            "processing": self.queue.processing,
            "providers": list(self.providers.keys()),
            "templates": len(self.templates)
        }


# Utility functions
def get_email_service() -> EmailService:
    """Get singleton email service instance."""
    if not hasattr(get_email_service, '_instance'):
        get_email_service._instance = EmailService()
    return get_email_service._instance


async def send_simple_email(
    to_email: str,
    subject: str,
    content: str,
    from_email: Optional[str] = None,
    is_html: bool = False
) -> bool:
    """Send a simple email."""
    service = get_email_service()
    
    message = EmailMessage(subject=subject)
    message.add_to(to_email)
    
    if from_email:
        message.from_address = EmailAddress(from_email)
    
    if is_html:
        message.html_content = content
    else:
        message.text_content = content
    
    return await service.send_email(message)


async def send_notification_email(
    recipient: str,
    notification_type: str,
    data: Dict[str, Any]
) -> bool:
    """Send notification email using predefined templates."""
    service = get_email_service()
    
    # Check if template exists for notification type
    template = service.get_template(f"notification_{notification_type}")
    if not template:
        # Create a simple template
        subject = f"Notification: {notification_type.replace('_', ' ').title()}"
        content = f"You have a new {notification_type} notification.\n\nDetails: {data}"
        return await send_simple_email(recipient, subject, content)
    
    # Use template
    message = EmailMessage(
        template_id=template.id,
        template_variables=data
    )
    message.add_to(recipient)
    
    return await service.send_email(message)