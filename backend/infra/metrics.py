"""
Standardized metrics infrastructure with bounded label sets and centralized validation.
Provides type-safe metric factories and enforces label allow-lists for cardinality control.
"""
import logging
from typing import Any, Dict, Final, Optional, Sequence, Union
from collections.abc import Mapping

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY
)

logger = logging.getLogger(__name__)

# Bounded label allow-list to prevent high cardinality issues
LABEL_ALLOWLIST: Final[Dict[str, tuple[str, ...]]] = {
    # HTTP metrics
    "http_requests_total": ("route", "method", "status"),
    "http_request_duration_seconds": ("route", "method"),
    
    # Alpaca broker metrics
    "alpaca_http_requests_total": ("endpoint", "method", "status"),
    "alpaca_http_latency_seconds": ("endpoint", "method"),
    
    # Outbox pattern metrics
    "outbox_polled_total": (),
    "outbox_dispatched_total": ("topic", "status"),
    "outbox_dispatch_latency_seconds": ("topic",),
    "outbox_queue_gauge": ("status",),
    
    # Database metrics
    "db_health_checks_total": ("result",),
    "db_query_duration_seconds": ("operation",),
    
    # WebSocket metrics
    "websocket_connections_total": ("client_type",),
    "websocket_messages_total": ("message_type", "direction"),
    
    # Authentication metrics
    "auth_attempts_total": ("result",),
    "auth_token_validations_total": ("result",),
}

# Allowed label values for specific labels (bounded sets)
LABEL_VALUE_ALLOWLIST: Final[Dict[str, tuple[str, ...]]] = {
    "status": ("success", "retry", "failed", "timeout", "error"),
    "result": ("success", "error", "timeout", "unauthorized", "forbidden"),
    "method": ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"),
    "operation": ("select", "insert", "update", "delete", "health_check"),
    "client_type": ("trading", "monitoring", "admin"),
    "message_type": ("signal", "portfolio", "heartbeat", "error"),
    "direction": ("inbound", "outbound"),
}

# Route templates to prevent high cardinality from path parameters
ROUTE_TEMPLATES: Final[Dict[str, str]] = {
    # API v1 routes
    "/api/v1/orders/submit": "/api/v1/orders/submit",
    "/api/v1/orders/{order_id}": "/api/v1/orders/{id}",
    "/api/v1/orders/{order_id}/cancel": "/api/v1/orders/{id}/cancel",
    "/api/v1/signals/{symbol}": "/api/v1/signals/{symbol}",
    "/api/v1/trades/execute": "/api/v1/trades/execute",
    "/api/v1/trades/history": "/api/v1/trades/history",
    "/api/v1/models/train": "/api/v1/models/train",
    "/api/v1/models/status": "/api/v1/models/status",
    "/api/v1/risk/limits": "/api/v1/risk/limits",
    "/api/v1/risk/metrics": "/api/v1/risk/metrics",
    
    # Health and system routes
    "/health": "/health",
    "/metrics": "/metrics",
    "/auth/login": "/auth/login",
    "/auth/token/validate": "/auth/token/validate",
    "/auth/me": "/auth/me",
    
    # System status routes
    "/api/v1/system/status": "/api/v1/system/status",
}

# Alpaca endpoint templates
ALPACA_ENDPOINT_TEMPLATES: Final[Dict[str, str]] = {
    "/v2/orders": "/v2/orders",
    "/v2/orders/{order_id}": "/v2/orders/{id}",
    "/v2/positions": "/v2/positions",
    "/v2/positions/{symbol}": "/v2/positions/{symbol}",
    "/v2/account": "/v2/account",
    "/v1/bars/{timeframe}": "/v1/bars/{timeframe}",
}


class MetricsRegistry:
    """
    Centralized metrics registry with validation and bounded label enforcement.
    Provides type-safe metric creation with cardinality protection.
    """
    
    def __init__(
        self, 
        namespace: str = "intraday",
        registry: Optional[CollectorRegistry] = None
    ):
        self.namespace = namespace
        self.registry = registry or REGISTRY
        self._metrics: Dict[str, Union[Counter, Histogram, Gauge]] = {}
        
        logger.info(
            f"Initialized metrics registry with namespace '{namespace}'"
        )
    
    def _validate_metric_name(self, name: str) -> None:
        """Validate metric name against allow-list."""
        if name not in LABEL_ALLOWLIST:
            raise ValueError(
                f"Metric '{name}' not found in LABEL_ALLOWLIST. "
                f"Add it to prevent high cardinality issues."
            )
    
    def _validate_labels(self, name: str, labels: Dict[str, str]) -> Dict[str, str]:
        """Validate labels against allow-list and bounded values."""
        allowed_labels = LABEL_ALLOWLIST[name]
        
        # Check for unexpected labels
        unexpected_labels = set(labels.keys()) - set(allowed_labels)
        if unexpected_labels:
            raise ValueError(
                f"Unexpected labels for metric '{name}': {unexpected_labels}. "
                f"Allowed labels: {allowed_labels}"
            )
        
        # Check for missing required labels
        missing_labels = set(allowed_labels) - set(labels.keys())
        if missing_labels:
            raise ValueError(
                f"Missing required labels for metric '{name}': {missing_labels}"
            )
        
        # Validate label values against bounded sets
        validated_labels = {}
        for key, value in labels.items():
            if key in LABEL_VALUE_ALLOWLIST:
                allowed_values = LABEL_VALUE_ALLOWLIST[key]
                if value not in allowed_values:
                    # Log warning but allow - might be a new valid value
                    logger.warning(
                        f"Label '{key}' has unexpected value '{value}'. "
                        f"Expected one of: {allowed_values}"
                    )
            validated_labels[key] = str(value)  # Ensure string type
        
        return validated_labels
    
    def _get_metric_name(self, name: str) -> str:
        """Get fully qualified metric name with namespace."""
        return f"{self.namespace}_{name}" if self.namespace else name
    
    def counter(
        self, 
        name: str, 
        labels: Optional[Dict[str, str]] = None,
        documentation: str = ""
    ) -> Counter:
        """
        Get or create a Counter metric with label validation.
        
        Args:
            name: Metric name (must be in LABEL_ALLOWLIST)
            labels: Label dictionary (validated against allow-list)
            documentation: Metric documentation
            
        Returns:
            Prometheus Counter instance
            
        Raises:
            ValueError: If metric name or labels are invalid
        """
        self._validate_metric_name(name)
        labels = labels or {}
        labels = self._validate_labels(name, labels)
        
        metric_key = f"{name}:{sorted(labels.items())}"
        
        if metric_key not in self._metrics:
            full_name = self._get_metric_name(name)
            
            # Create metric with all possible label names
            label_names = LABEL_ALLOWLIST[name]
            counter = Counter(
                full_name,
                documentation or f"Counter metric: {name}",
                labelnames=label_names,
                registry=self.registry
            )
            self._metrics[metric_key] = counter
            
            logger.debug(f"Created counter metric: {full_name} with labels: {label_names}")
        
        metric = self._metrics[metric_key]
        
        # Return labeled metric instance
        if labels:
            # Ensure all label names have values (use empty string for missing)
            all_labels = {}
            for label_name in LABEL_ALLOWLIST[name]:
                all_labels[label_name] = labels.get(label_name, "")
            return metric.labels(**all_labels)
        else:
            return metric
    
    def histogram(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
        buckets: Optional[Sequence[float]] = None,
        documentation: str = ""
    ) -> Histogram:
        """
        Get or create a Histogram metric with label validation.
        
        Args:
            name: Metric name (must be in LABEL_ALLOWLIST)
            labels: Label dictionary (validated against allow-list)
            buckets: Histogram buckets (optional, uses default if not provided)
            documentation: Metric documentation
            
        Returns:
            Prometheus Histogram instance
            
        Raises:
            ValueError: If metric name or labels are invalid
        """
        self._validate_metric_name(name)
        labels = labels or {}
        labels = self._validate_labels(name, labels)
        
        metric_key = f"{name}:{sorted(labels.items())}"
        
        if metric_key not in self._metrics:
            full_name = self._get_metric_name(name)
            
            # Create metric with all possible label names
            label_names = LABEL_ALLOWLIST[name]
            
            # Use provided buckets or default Prometheus buckets
            if buckets is not None:
                histogram = Histogram(
                    full_name,
                    documentation or f"Histogram metric: {name}",
                    labelnames=label_names,
                    buckets=buckets,
                    registry=self.registry
                )
            else:
                histogram = Histogram(
                    full_name,
                    documentation or f"Histogram metric: {name}",
                    labelnames=label_names,
                    registry=self.registry
                )
            self._metrics[metric_key] = histogram
            
            logger.debug(f"Created histogram metric: {full_name} with labels: {label_names}")
        
        metric = self._metrics[metric_key]
        
        # Return labeled metric instance
        if labels:
            # Ensure all label names have values
            all_labels = {}
            for label_name in LABEL_ALLOWLIST[name]:
                all_labels[label_name] = labels.get(label_name, "")
            return metric.labels(**all_labels)
        else:
            return metric
    
    def gauge(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
        documentation: str = ""
    ) -> Gauge:
        """
        Get or create a Gauge metric with label validation.
        
        Args:
            name: Metric name (must be in LABEL_ALLOWLIST)  
            labels: Label dictionary (validated against allow-list)
            documentation: Metric documentation
            
        Returns:
            Prometheus Gauge instance
            
        Raises:
            ValueError: If metric name or labels are invalid
        """
        self._validate_metric_name(name)
        labels = labels or {}
        labels = self._validate_labels(name, labels)
        
        metric_key = f"{name}:{sorted(labels.items())}"
        
        if metric_key not in self._metrics:
            full_name = self._get_metric_name(name)
            
            # Create metric with all possible label names
            label_names = LABEL_ALLOWLIST[name]
            gauge = Gauge(
                full_name,
                documentation or f"Gauge metric: {name}",
                labelnames=label_names,
                registry=self.registry
            )
            self._metrics[metric_key] = gauge
            
            logger.debug(f"Created gauge metric: {full_name} with labels: {label_names}")
        
        metric = self._metrics[metric_key]
        
        # Return labeled metric instance
        if labels:
            # Ensure all label names have values
            all_labels = {}
            for label_name in LABEL_ALLOWLIST[name]:
                all_labels[label_name] = labels.get(label_name, "")
            return metric.labels(**all_labels)
        else:
            return metric
    
    def inc_counter(
        self, 
        name: str, 
        labels: Optional[Dict[str, str]] = None,
        amount: float = 1.0
    ) -> None:
        """Convenience method to increment a counter."""
        counter = self.counter(name, labels)
        counter.inc(amount)
    
    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Convenience method to observe a histogram value."""
        histogram = self.histogram(name, labels)
        histogram.observe(value)
    
    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Convenience method to set a gauge value."""
        gauge = self.gauge(name, labels)
        gauge.set(value)
    
    def get_metrics_data(self) -> bytes:
        """Get Prometheus exposition format data."""
        return generate_latest(self.registry)
    
    def get_content_type(self) -> str:
        """Get Prometheus content type."""
        return CONTENT_TYPE_LATEST


def normalize_route(path: str) -> str:
    """
    Normalize route path to prevent high cardinality from path parameters.
    
    Args:
        path: Original request path
        
    Returns:
        Normalized route template
    """
    # Check for exact matches first
    if path in ROUTE_TEMPLATES:
        return ROUTE_TEMPLATES[path]
    
    # Check for pattern matches (replace UUIDs and other IDs)
    import re
    
    # Replace UUIDs with {id}
    uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    normalized = re.sub(uuid_pattern, '{id}', path, flags=re.IGNORECASE)
    
    # Replace numeric IDs with {id}
    numeric_id_pattern = r'/\d+(?=/|$)'
    normalized = re.sub(numeric_id_pattern, '/{id}', normalized)
    
    # Check if normalized path exists in templates
    if normalized in ROUTE_TEMPLATES:
        return ROUTE_TEMPLATES[normalized]
    
    # Return original path if no normalization needed, otherwise return normalized
    return normalized if normalized != path else path


def normalize_alpaca_endpoint(endpoint: str) -> str:
    """
    Normalize Alpaca endpoint to prevent high cardinality.
    
    Args:
        endpoint: Original Alpaca endpoint path
        
    Returns:
        Normalized endpoint template
    """
    # Check for exact matches
    if endpoint in ALPACA_ENDPOINT_TEMPLATES:
        return ALPACA_ENDPOINT_TEMPLATES[endpoint]
    
    # Pattern matching for Alpaca endpoints
    import re
    
    # Replace order IDs with {id}
    normalized = re.sub(r'/orders/[^/]+', '/orders/{id}', endpoint)
    
    # Replace symbols with {symbol} 
    normalized = re.sub(r'/positions/[A-Z]+', '/positions/{symbol}', normalized)
    
    # Check if normalized endpoint exists in templates
    if normalized in ALPACA_ENDPOINT_TEMPLATES:
        return ALPACA_ENDPOINT_TEMPLATES[normalized]
    
    return normalized if normalized != endpoint else "/unknown"


# Global metrics registry instance
_registry: Optional[MetricsRegistry] = None


def get_metrics_registry() -> MetricsRegistry:
    """Get the global metrics registry instance."""
    global _registry
    if _registry is None:
        _registry = MetricsRegistry()
    return _registry


def initialize_metrics_registry(
    namespace: str = "intraday",
    registry: Optional[CollectorRegistry] = None
) -> MetricsRegistry:
    """Initialize the global metrics registry."""
    global _registry
    _registry = MetricsRegistry(namespace=namespace, registry=registry)
    return _registry
