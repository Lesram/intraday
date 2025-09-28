"""
Integration Service for Trading Platform

This module provides comprehensive third-party integration capabilities including:
- Third-party API integration with rate limiting and retries
- Webhook handling with verification and processing
- Data transformation and mapping between different formats
- Protocol adaptation (REST, GraphQL, SOAP, etc.)
- Connector management for various external services
- Event processing and routing
- Integration monitoring and health checks
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
import threading
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Union, Set
from urllib.parse import urlparse, parse_qs
from uuid import uuid4
import aiohttp
import ssl


class IntegrationType(Enum):
    """Integration types."""
    REST_API = "rest_api"
    GRAPHQL = "graphql"
    WEBHOOK = "webhook"
    SOAP = "soap"
    FTP = "ftp"
    SFTP = "sftp"
    DATABASE = "database"
    MESSAGE_QUEUE = "message_queue"
    CUSTOM = "custom"


class DataFormat(Enum):
    """Data formats."""
    JSON = "json"
    XML = "xml"
    CSV = "csv"
    YAML = "yaml"
    BINARY = "binary"
    TEXT = "text"
    FORM_DATA = "form_data"


class AuthenticationType(Enum):
    """Authentication types."""
    NONE = "none"
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    BASIC_AUTH = "basic_auth"
    OAUTH2 = "oauth2"
    JWT = "jwt"
    CUSTOM_HEADER = "custom_header"
    SIGNATURE = "signature"


class WebhookStatus(Enum):
    """Webhook processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class AuthenticationConfig:
    """Authentication configuration."""
    type: AuthenticationType
    api_key: Optional[str] = None
    token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    header_name: Optional[str] = None
    header_value: Optional[str] = None
    signature_secret: Optional[str] = None
    oauth2_config: Optional[Dict[str, Any]] = None


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    burst_limit: int = 10
    backoff_factor: float = 1.5
    max_retry_delay: float = 300.0  # 5 minutes


@dataclass
class RetryConfig:
    """Retry configuration."""
    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    retry_on_status_codes: Set[int] = field(default_factory=lambda: {429, 500, 502, 503, 504})


@dataclass
class WebhookConfig:
    """Webhook configuration."""
    id: str
    url: str
    secret: Optional[str] = None
    events: List[str] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    signature_header: str = "X-Signature"
    timestamp_header: str = "X-Timestamp"
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 5.0


@dataclass
class DataMapping:
    """Data transformation mapping."""
    source_field: str
    target_field: str
    transformation: Optional[str] = None  # Function name or expression
    default_value: Any = None
    required: bool = True


@dataclass
class IntegrationConfig:
    """Integration configuration."""
    id: str
    name: str
    type: IntegrationType
    base_url: str
    authentication: AuthenticationConfig
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    data_format: DataFormat = DataFormat.JSON
    headers: Dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    verify_ssl: bool = True
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class IntegrationRequest:
    """Integration request."""
    id: str
    integration_id: str
    method: str
    endpoint: str
    data: Optional[Any] = None
    headers: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    timeout: Optional[float] = None
    retry_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IntegrationResponse:
    """Integration response."""
    request_id: str
    status_code: int
    data: Any
    headers: Dict[str, str]
    duration: float
    success: bool
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class WebhookEvent:
    """Webhook event."""
    id: str
    webhook_id: str
    event_type: str
    payload: Dict[str, Any]
    headers: Dict[str, str]
    signature: Optional[str] = None
    status: WebhookStatus = WebhookStatus.PENDING
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None
    retry_count: int = 0
    error_message: Optional[str] = None


@dataclass
class IntegrationMetrics:
    """Integration metrics."""
    integration_id: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_response_time: float = 0.0
    last_request_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    rate_limit_hits: int = 0
    total_retries: int = 0


class RateLimiter:
    """Rate limiter for API requests."""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._request_times: Dict[str, deque] = defaultdict(lambda: deque())
        self._lock = threading.RLock()
    
    def can_make_request(self, integration_id: str) -> bool:
        """Check if a request can be made."""
        with self._lock:
            now = time.time()
            times = self._request_times[integration_id]
            
            # Remove old entries
            minute_ago = now - 60
            hour_ago = now - 3600
            day_ago = now - 86400
            
            # Check minute limit
            minute_count = sum(1 for t in times if t > minute_ago)
            if minute_count >= self.config.requests_per_minute:
                return False
            
            # Check hour limit
            hour_count = sum(1 for t in times if t > hour_ago)
            if hour_count >= self.config.requests_per_hour:
                return False
            
            # Check day limit
            day_count = sum(1 for t in times if t > day_ago)
            if day_count >= self.config.requests_per_day:
                return False
            
            # Check burst limit
            recent_times = [t for t in times if t > now - 10]  # Last 10 seconds
            if len(recent_times) >= self.config.burst_limit:
                return False
            
            return True
    
    def record_request(self, integration_id: str):
        """Record a request."""
        with self._lock:
            now = time.time()
            times = self._request_times[integration_id]
            times.append(now)
            
            # Keep only recent entries
            cutoff = now - 86400  # Keep 24 hours
            while times and times[0] < cutoff:
                times.popleft()
    
    def get_wait_time(self, integration_id: str) -> float:
        """Get time to wait before next request."""
        with self._lock:
            if self.can_make_request(integration_id):
                return 0.0
            
            now = time.time()
            times = self._request_times[integration_id]
            
            # Find earliest time we can make next request
            minute_ago = now - 60
            recent_times = [t for t in times if t > minute_ago]
            
            if len(recent_times) >= self.config.requests_per_minute:
                # Wait until oldest recent request is older than 1 minute
                return recent_times[0] + 60 - now
            
            return 1.0  # Default wait time


class DataTransformer:
    """Data transformation engine."""
    
    def __init__(self):
        self._transformations: Dict[str, Callable] = {
            'uppercase': lambda x: str(x).upper(),
            'lowercase': lambda x: str(x).lower(),
            'strip': lambda x: str(x).strip(),
            'int': lambda x: int(x),
            'float': lambda x: float(x),
            'str': lambda x: str(x),
            'bool': lambda x: bool(x),
            'timestamp': lambda x: datetime.fromisoformat(str(x)) if isinstance(x, str) else x,
            'iso_timestamp': lambda x: x.isoformat() if isinstance(x, datetime) else x,
        }
    
    def register_transformation(self, name: str, func: Callable):
        """Register a custom transformation function."""
        self._transformations[name] = func
    
    def transform_data(self, data: Dict[str, Any], mappings: List[DataMapping]) -> Dict[str, Any]:
        """Transform data using mappings."""
        result = {}
        
        for mapping in mappings:
            try:
                # Get source value
                value = self._get_nested_value(data, mapping.source_field)
                
                if value is None and mapping.default_value is not None:
                    value = mapping.default_value
                elif value is None and mapping.required:
                    raise ValueError(f"Required field {mapping.source_field} is missing")
                
                # Apply transformation
                if mapping.transformation and value is not None:
                    if mapping.transformation in self._transformations:
                        value = self._transformations[mapping.transformation](value)
                    else:
                        # Try to evaluate as expression
                        try:
                            value = eval(mapping.transformation, {"value": value, "data": data})
                        except Exception as e:
                            logging.warning(f"Transformation failed for {mapping.source_field}: {e}")
                
                # Set target value
                self._set_nested_value(result, mapping.target_field, value)
                
            except Exception as e:
                if mapping.required:
                    raise
                logging.warning(f"Failed to transform {mapping.source_field}: {e}")
        
        return result
    
    def _get_nested_value(self, data: Dict[str, Any], field_path: str) -> Any:
        """Get nested value using dot notation."""
        parts = field_path.split('.')
        current = data
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        
        return current
    
    def _set_nested_value(self, data: Dict[str, Any], field_path: str, value: Any):
        """Set nested value using dot notation."""
        parts = field_path.split('.')
        current = data
        
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        current[parts[-1]] = value


class WebhookValidator:
    """Webhook signature validator."""
    
    @staticmethod
    def validate_signature(payload: bytes, signature: str, secret: str, 
                          algorithm: str = "sha256") -> bool:
        """Validate webhook signature."""
        try:
            if algorithm == "sha256":
                expected = hmac.new(
                    secret.encode(),
                    payload,
                    hashlib.sha256
                ).hexdigest()
                
                # Handle different signature formats
                if signature.startswith("sha256="):
                    signature = signature[7:]
                
                return hmac.compare_digest(expected, signature)
            
            return False
        except Exception:
            return False
    
    @staticmethod
    def validate_timestamp(timestamp_str: str, max_age_seconds: int = 300) -> bool:
        """Validate webhook timestamp."""
        try:
            timestamp = float(timestamp_str)
            now = time.time()
            age = now - timestamp
            return 0 <= age <= max_age_seconds
        except Exception:
            return False


class IntegrationConnector(ABC):
    """Abstract base class for integration connectors."""
    
    def __init__(self, config: IntegrationConfig):
        self.config = config
        self.rate_limiter = RateLimiter(config.rate_limit)
        self.metrics = IntegrationMetrics(integration_id=config.id)
    
    @abstractmethod
    async def execute_request(self, request: IntegrationRequest) -> IntegrationResponse:
        """Execute an integration request."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the integration is healthy."""
        pass
    
    def _prepare_headers(self, request: IntegrationRequest) -> Dict[str, str]:
        """Prepare request headers."""
        headers = self.config.headers.copy()
        headers.update(request.headers)
        
        # Add authentication headers
        auth = self.config.authentication
        if auth.type == AuthenticationType.API_KEY and auth.api_key:
            headers["X-API-Key"] = auth.api_key
        elif auth.type == AuthenticationType.BEARER_TOKEN and auth.token:
            headers["Authorization"] = f"Bearer {auth.token}"
        elif auth.type == AuthenticationType.BASIC_AUTH and auth.username and auth.password:
            import base64
            credentials = base64.b64encode(f"{auth.username}:{auth.password}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
        elif auth.type == AuthenticationType.CUSTOM_HEADER and auth.header_name and auth.header_value:
            headers[auth.header_name] = auth.header_value
        
        return headers
    
    def _update_metrics(self, response: IntegrationResponse):
        """Update integration metrics."""
        self.metrics.total_requests += 1
        self.metrics.last_request_time = response.timestamp
        
        if response.success:
            self.metrics.successful_requests += 1
            self.metrics.last_success_time = response.timestamp
        else:
            self.metrics.failed_requests += 1
            self.metrics.last_failure_time = response.timestamp
        
        # Update average response time
        total_time = (self.metrics.average_response_time * 
                     (self.metrics.total_requests - 1) + response.duration)
        self.metrics.average_response_time = total_time / self.metrics.total_requests


class RestApiConnector(IntegrationConnector):
    """REST API connector."""
    
    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                ssl=ssl.create_default_context() if self.config.verify_ssl else False
            )
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )
        return self._session
    
    async def execute_request(self, request: IntegrationRequest) -> IntegrationResponse:
        """Execute REST API request."""
        start_time = time.time()
        
        try:
            # Check rate limit
            if not self.rate_limiter.can_make_request(self.config.id):
                wait_time = self.rate_limiter.get_wait_time(self.config.id)
                await asyncio.sleep(wait_time)
                self.metrics.rate_limit_hits += 1
            
            # Record request
            self.rate_limiter.record_request(self.config.id)
            
            # Prepare request
            session = await self._get_session()
            url = f"{self.config.base_url.rstrip('/')}/{request.endpoint.lstrip('/')}"
            headers = self._prepare_headers(request)
            timeout = request.timeout or self.config.timeout
            
            # Execute request
            async with session.request(
                method=request.method,
                url=url,
                json=request.data if self.config.data_format == DataFormat.JSON else None,
                data=request.data if self.config.data_format != DataFormat.JSON else None,
                headers=headers,
                params=request.params,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                
                response_headers = dict(response.headers)
                response_text = await response.text()
                
                # Parse response data
                try:
                    if self.config.data_format == DataFormat.JSON:
                        response_data = await response.json()
                    else:
                        response_data = response_text
                except Exception:
                    response_data = response_text
                
                duration = time.time() - start_time
                success = 200 <= response.status < 300
                
                result = IntegrationResponse(
                    request_id=request.id,
                    status_code=response.status,
                    data=response_data,
                    headers=response_headers,
                    duration=duration,
                    success=success,
                    error_message=None if success else f"HTTP {response.status}: {response_text}"
                )
                
                self._update_metrics(result)
                return result
                
        except Exception as e:
            duration = time.time() - start_time
            result = IntegrationResponse(
                request_id=request.id,
                status_code=0,
                data=None,
                headers={},
                duration=duration,
                success=False,
                error_message=str(e)
            )
            
            self._update_metrics(result)
            return result
    
    async def health_check(self) -> bool:
        """Check REST API health."""
        try:
            request = IntegrationRequest(
                id=str(uuid4()),
                integration_id=self.config.id,
                method="GET",
                endpoint="/health",
                timeout=5.0
            )
            
            response = await self.execute_request(request)
            return response.success
        except Exception:
            return False
    
    async def close(self):
        """Close the connector."""
        if self._session:
            await self._session.close()


class WebhookProcessor:
    """Webhook event processor."""
    
    def __init__(self):
        self.handlers: Dict[str, List[Callable]] = defaultdict(list)
        self.validator = WebhookValidator()
        self.transformer = DataTransformer()
    
    def register_handler(self, event_type: str, handler: Callable[[WebhookEvent], None]):
        """Register a webhook event handler."""
        self.handlers[event_type].append(handler)
    
    def unregister_handler(self, event_type: str, handler: Callable[[WebhookEvent], None]):
        """Unregister a webhook event handler."""
        if event_type in self.handlers and handler in self.handlers[event_type]:
            self.handlers[event_type].remove(handler)
    
    async def process_webhook(self, webhook_config: WebhookConfig, 
                            headers: Dict[str, str], payload: bytes) -> WebhookEvent:
        """Process incoming webhook."""
        webhook_event = WebhookEvent(
            id=str(uuid4()),
            webhook_id=webhook_config.id,
            event_type="webhook",  # Will be determined from payload
            payload={},
            headers=headers,
            status=WebhookStatus.PENDING
        )
        
        try:
            # Validate signature if secret is configured
            if webhook_config.secret:
                signature = headers.get(webhook_config.signature_header, "")
                if not self.validator.validate_signature(payload, signature, webhook_config.secret):
                    webhook_event.status = WebhookStatus.FAILED
                    webhook_event.error_message = "Invalid signature"
                    return webhook_event
            
            # Validate timestamp if present
            timestamp_header = headers.get(webhook_config.timestamp_header)
            if timestamp_header:
                if not self.validator.validate_timestamp(timestamp_header):
                    webhook_event.status = WebhookStatus.FAILED
                    webhook_event.error_message = "Timestamp too old"
                    return webhook_event
            
            # Parse payload
            try:
                webhook_event.payload = json.loads(payload.decode())
            except Exception as e:
                webhook_event.status = WebhookStatus.FAILED
                webhook_event.error_message = f"Failed to parse payload: {e}"
                return webhook_event
            
            # Determine event type
            event_type = webhook_event.payload.get("type", "unknown")
            webhook_event.event_type = event_type
            
            # Process event
            webhook_event.status = WebhookStatus.PROCESSING
            await self._handle_event(webhook_event)
            
            webhook_event.status = WebhookStatus.COMPLETED
            webhook_event.processed_at = datetime.now(timezone.utc)
            
        except Exception as e:
            webhook_event.status = WebhookStatus.FAILED
            webhook_event.error_message = str(e)
        
        return webhook_event
    
    async def _handle_event(self, webhook_event: WebhookEvent):
        """Handle webhook event."""
        handlers = self.handlers.get(webhook_event.event_type, [])
        handlers.extend(self.handlers.get("*", []))  # Wildcard handlers
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(webhook_event)
                else:
                    handler(webhook_event)
            except Exception as e:
                logging.error(f"Error in webhook handler: {e}")


class IntegrationService:
    """Main integration service."""
    
    def __init__(self, health_check_interval: int = 300):
        self.connectors: Dict[str, IntegrationConnector] = {}
        self.webhook_processor = WebhookProcessor()
        self.transformer = DataTransformer()
        self.configurations: Dict[str, IntegrationConfig] = {}
        self.webhook_configs: Dict[str, WebhookConfig] = {}
        
        # Background tasks
        self._health_check_task: Optional[asyncio.Task] = None
        self._health_check_interval = health_check_interval  # configurable for testing
        self._running = False
    
    async def start(self, enable_health_check: bool = True):
        """Start the integration service."""
        self._running = True
        if enable_health_check and self._health_check_interval > 0:
            self._health_check_task = asyncio.create_task(self._health_check_loop())
    
    async def stop(self):
        """Stop the integration service."""
        self._running = False
        
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Close all connectors
        for connector in self.connectors.values():
            if hasattr(connector, 'close'):
                await connector.close()
    
    async def _health_check_loop(self):
        """Background health check loop."""
        while self._running:
            try:
                await asyncio.sleep(self._health_check_interval)
                if self._running:
                    await self._check_all_integrations()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in health check loop: {e}")
    
    async def _check_all_integrations(self):
        """Check health of all integrations."""
        for integration_id, connector in self.connectors.items():
            try:
                healthy = await connector.health_check()
                logging.info(f"Integration {integration_id} health: {'OK' if healthy else 'FAILED'}")
            except Exception as e:
                logging.error(f"Health check failed for {integration_id}: {e}")
    
    def register_integration(self, config: IntegrationConfig) -> bool:
        """Register a new integration."""
        try:
            self.configurations[config.id] = config
            
            # Create appropriate connector
            if config.type == IntegrationType.REST_API:
                connector = RestApiConnector(config)
            else:
                # For now, only REST API is implemented
                # Other types would be implemented similarly
                logging.warning(f"Integration type {config.type} not yet implemented")
                return False
            
            self.connectors[config.id] = connector
            return True
            
        except Exception as e:
            logging.error(f"Failed to register integration {config.id}: {e}")
            return False
    
    def unregister_integration(self, integration_id: str) -> bool:
        """Unregister an integration."""
        try:
            if integration_id in self.connectors:
                connector = self.connectors[integration_id]
                if hasattr(connector, 'close'):
                    asyncio.create_task(connector.close())
                del self.connectors[integration_id]
            
            if integration_id in self.configurations:
                del self.configurations[integration_id]
            
            return True
        except Exception as e:
            logging.error(f"Failed to unregister integration {integration_id}: {e}")
            return False
    
    async def execute_request(self, request: IntegrationRequest) -> IntegrationResponse:
        """Execute an integration request."""
        connector = self.connectors.get(request.integration_id)
        if not connector:
            return IntegrationResponse(
                request_id=request.id,
                status_code=0,
                data=None,
                headers={},
                duration=0.0,
                success=False,
                error_message=f"Integration {request.integration_id} not found"
            )
        
        config = self.configurations[request.integration_id]
        if not config.enabled:
            return IntegrationResponse(
                request_id=request.id,
                status_code=0,
                data=None,
                headers={},
                duration=0.0,
                success=False,
                error_message=f"Integration {request.integration_id} is disabled"
            )
        
        # Execute with retries
        last_response = None
        for attempt in range(config.retry_config.max_attempts):
            try:
                response = await connector.execute_request(request)
                
                # Check if we should retry
                if (response.success or 
                    response.status_code not in config.retry_config.retry_on_status_codes):
                    return response
                
                last_response = response
                
                # Calculate retry delay
                delay = min(
                    config.retry_config.initial_delay * (config.retry_config.backoff_factor ** attempt),
                    config.retry_config.max_delay
                )
                
                if attempt < config.retry_config.max_attempts - 1:
                    await asyncio.sleep(delay)
                    request.retry_count += 1
                    connector.metrics.total_retries += 1
                
            except Exception as e:
                last_response = IntegrationResponse(
                    request_id=request.id,
                    status_code=0,
                    data=None,
                    headers={},
                    duration=0.0,
                    success=False,
                    error_message=str(e)
                )
        
        return last_response or IntegrationResponse(
            request_id=request.id,
            status_code=0,
            data=None,
            headers={},
            duration=0.0,
            success=False,
            error_message="All retry attempts failed"
        )
    
    def register_webhook(self, config: WebhookConfig):
        """Register a webhook configuration."""
        self.webhook_configs[config.id] = config
    
    def unregister_webhook(self, webhook_id: str):
        """Unregister a webhook configuration."""
        if webhook_id in self.webhook_configs:
            del self.webhook_configs[webhook_id]
    
    async def process_webhook(self, webhook_id: str, headers: Dict[str, str], 
                            payload: bytes) -> WebhookEvent:
        """Process an incoming webhook."""
        config = self.webhook_configs.get(webhook_id)
        if not config:
            raise ValueError(f"Webhook {webhook_id} not found")
        
        return await self.webhook_processor.process_webhook(config, headers, payload)
    
    def register_webhook_handler(self, event_type: str, handler: Callable[[WebhookEvent], None]):
        """Register a webhook event handler."""
        self.webhook_processor.register_handler(event_type, handler)
    
    def get_integration_metrics(self, integration_id: Optional[str] = None) -> Dict[str, Dict]:
        """Get integration metrics."""
        if integration_id:
            connector = self.connectors.get(integration_id)
            if connector:
                return {integration_id: asdict(connector.metrics)}
            return {}
        
        result = {}
        for int_id, connector in self.connectors.items():
            result[int_id] = asdict(connector.metrics)
        return result
    
    def transform_data(self, data: Dict[str, Any], mappings: List[DataMapping]) -> Dict[str, Any]:
        """Transform data using mappings."""
        return self.transformer.transform_data(data, mappings)
    
    def register_transformation(self, name: str, func: Callable):
        """Register a custom transformation function."""
        self.transformer.register_transformation(name, func)


# Global service instance
_integration_service: Optional[IntegrationService] = None


def get_integration_service() -> IntegrationService:
    """Get the global integration service instance."""
    global _integration_service
    if _integration_service is None:
        # Use shorter health check interval in test environments
        import os
        health_check_interval = 1 if os.environ.get('PYTEST_CURRENT_TEST') else 300
        _integration_service = IntegrationService(health_check_interval=health_check_interval)
    return _integration_service


def set_integration_service(service: IntegrationService):
    """Set the global integration service instance."""
    global _integration_service
    _integration_service = service


# Convenience functions
async def make_api_request(integration_id: str, method: str, endpoint: str, 
                          data: Optional[Any] = None, **kwargs) -> IntegrationResponse:
    """Make an API request through an integration."""
    service = get_integration_service()
    request = IntegrationRequest(
        id=str(uuid4()),
        integration_id=integration_id,
        method=method,
        endpoint=endpoint,
        data=data,
        **kwargs
    )
    return await service.execute_request(request)


def register_api_integration(integration_id: str, base_url: str, 
                           auth_config: AuthenticationConfig, **kwargs) -> bool:
    """Register a REST API integration."""
    service = get_integration_service()
    # Extract name to avoid duplicate keyword argument
    name = kwargs.pop('name', integration_id)
    config = IntegrationConfig(
        id=integration_id,
        name=name,
        type=IntegrationType.REST_API,
        base_url=base_url,
        authentication=auth_config,
        **kwargs
    )
    return service.register_integration(config)


async def process_webhook_data(webhook_id: str, headers: Dict[str, str], 
                             payload: bytes) -> WebhookEvent:
    """Process webhook data."""
    service = get_integration_service()
    return await service.process_webhook(webhook_id, headers, payload)