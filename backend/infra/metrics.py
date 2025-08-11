"""
Standardized metrics infrastructure with bounded label sets and centralized validation.
Provides type-safe metric factories and enforces label allow-lists for cardinality control.
"""
from collections.abc import Sequence
import logging
from typing import Final, Union

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Import observability contracts for consistent buckets
try:
    from .observability_contracts import ObservabilityContract, get_histogram_buckets

    OBSERVABILITY_CONTRACTS_AVAILABLE = True
except ImportError:
    OBSERVABILITY_CONTRACTS_AVAILABLE = False

    # Fallback function for when contracts aren't available
    def get_histogram_buckets(metric_name: str) -> tuple[float, ...]:
        # Return default Prometheus buckets
        return (
            0.005,
            0.01,
            0.025,
            0.05,
            0.075,
            0.1,
            0.25,
            0.5,
            0.75,
            1.0,
            2.5,
            5.0,
            7.5,
            10.0,
            float("inf"),
        )


logger = logging.getLogger(__name__)

# Bounded label allow-list to prevent high cardinality issues
LABEL_ALLOWLIST: Final[dict[str, tuple[str, ...]]] = {
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
    # Strategy engine metrics (Branch 2.7)
    "strategy_signals_total": ("source",),
    "strategy_netting_decisions_total": ("symbol_bucket",),
    "strategy_throttled_total": (),
    "strategy_blocked_total": ("reason",),
    "strategy_planned_notional_A-F": (),
    "strategy_planned_notional_G-M": (),
    "strategy_planned_notional_N-S": (),
    "strategy_planned_notional_T-Z": (),
    "strategy_planned_notional_other": (),
    # Risk manager metrics (Branch 2.8)
    "risk_allows_total": (),
    "risk_blocks_total": ("reason",),
    "risk_decision_latency_seconds": (),
    # Feature pipeline metrics (Branch 2.9)
    "feature_compute_latency_seconds": ("path",),
    "feature_no_lookahead_violations_total": ("bucket",),
    "feature_rows_dropped_total": ("reason",),
    "feature_schema_validations_total": ("result",),
}

# Allowed label values for specific labels (bounded sets)
LABEL_VALUE_ALLOWLIST: Final[dict[str, tuple[str, ...]]] = {
    "status": ("success", "retry", "failed", "timeout", "error"),
    "result": ("success", "error", "timeout", "unauthorized", "forbidden"),
    "method": ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"),
    "operation": ("select", "insert", "update", "delete", "health_check"),
    "client_type": ("trading", "monitoring", "admin"),
    "message_type": ("signal", "portfolio", "heartbeat", "error"),
    "direction": ("inbound", "outbound"),
    # Strategy engine label values
    "source": ("momentum", "mean_reversion", "ml_ensemble", "sentiment", "other"),
    "symbol_bucket": ("A-F", "G-M", "N-S", "T-Z", "other"),
    # Risk manager label values (bounded reasons)
    "reason": (
        "window",
        "halt",
        "whitelist",
        "pos_cap",
        "notional_cap",
        "var",
        "cvar",
        "kelly",
        "correlation",
        "sector",
        "heat",
        "leverage",
        "risk_limit",
        "position_limit",
        "volatility",
        "other",
        # Feature pipeline reasons
        "nan",
        "ffill_limit",
        "misalign",
        "validation_error",
    ),
    # Feature pipeline label values (Branch 2.9)
    "path": ("compute_all", "align_single", "align_multi", "validate_schema"),
    "bucket": ("price_based", "oscillator", "regime", "other"),
}

# Route templates to prevent high cardinality from path parameters
ROUTE_TEMPLATES: Final[dict[str, str]] = {
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
ALPACA_ENDPOINT_TEMPLATES: Final[dict[str, str]] = {
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

    def __init__(self, namespace: str = "intraday", registry: CollectorRegistry | None = None):
        self.namespace = namespace
        self.registry = registry or REGISTRY
        self._metrics: dict[str, Union[Counter, Histogram, Gauge]] = {}

        # Initialize observability contract if available
        if OBSERVABILITY_CONTRACTS_AVAILABLE:
            self.observability_contract = ObservabilityContract(self.registry)
        else:
            self.observability_contract = None

        logger.info(f"Initialized metrics registry with namespace '{namespace}'")

    def _validate_metric_name(self, name: str) -> None:
        """Validate metric name against allow-list."""
        if name not in LABEL_ALLOWLIST:
            raise ValueError(
                f"Metric '{name}' not found in LABEL_ALLOWLIST. "
                f"Add it to prevent high cardinality issues."
            )

    def _validate_labels(self, name: str, labels: dict[str, str]) -> dict[str, str]:
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
            raise ValueError(f"Missing required labels for metric '{name}': {missing_labels}")

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
        self, name: str, labels: dict[str, str] | None = None, documentation: str = ""
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
                registry=self.registry,
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
        labels: dict[str, str] | None = None,
        buckets: Sequence[float] | None = None,
        documentation: str = "",
    ) -> Histogram:
        """
        Get or create a Histogram metric with label validation and fixed buckets.

        Args:
            name: Metric name (must be in LABEL_ALLOWLIST)
            labels: Label dictionary (validated against allow-list)
            buckets: Histogram buckets (optional, uses standardized buckets if available)
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

            # Determine buckets to use
            if buckets is not None:
                # Use explicitly provided buckets
                final_buckets = buckets
            else:
                # Try to get standardized buckets from observability contracts
                try:
                    final_buckets = get_histogram_buckets(name)
                    logger.debug(f"Using standardized buckets for {name}: {final_buckets}")
                except (ValueError, NameError):
                    # Fall back to default Prometheus buckets
                    final_buckets = None
                    logger.debug(f"Using default Prometheus buckets for {name}")

            # Create histogram with appropriate buckets
            if final_buckets is not None:
                histogram = Histogram(
                    full_name,
                    documentation or f"Histogram metric: {name}",
                    labelnames=label_names,
                    buckets=final_buckets,
                    registry=self.registry,
                )
            else:
                histogram = Histogram(
                    full_name,
                    documentation or f"Histogram metric: {name}",
                    labelnames=label_names,
                    registry=self.registry,
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
        self, name: str, labels: dict[str, str] | None = None, documentation: str = ""
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
                registry=self.registry,
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
        self, name: str, labels: dict[str, str] | None = None, amount: float = 1.0
    ) -> None:
        """Convenience method to increment a counter."""
        counter = self.counter(name, labels)
        counter.inc(amount)

    def observe_histogram(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """Convenience method to observe a histogram value."""
        histogram = self.histogram(name, labels)
        histogram.observe(value)

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Convenience method to set a gauge value."""
        gauge = self.gauge(name, labels)
        gauge.set(value)

    # Strategy engine convenience methods

    def inc_strategy_signals(self, source: str, amount: float = 1.0) -> None:
        """Increment strategy signals counter."""
        self.inc_counter("strategy_signals_total", {"source": source}, amount)

    def inc_strategy_netting_decisions(self, symbol: str, amount: float = 1.0) -> None:
        """Increment strategy netting decisions counter with symbol bucket."""
        bucket = self._get_symbol_bucket(symbol)
        self.inc_counter("strategy_netting_decisions_total", {"symbol_bucket": bucket}, amount)

    def inc_strategy_throttled(self, amount: float = 1.0) -> None:
        """Increment strategy throttled counter."""
        self.inc_counter("strategy_throttled_total", {}, amount)

    def inc_strategy_blocked(self, reason: str, amount: float = 1.0) -> None:
        """Increment strategy blocked counter."""
        self.inc_counter("strategy_blocked_total", {"reason": reason}, amount)

    def set_strategy_planned_notional(self, symbol: str, notional: float) -> None:
        """Set strategy planned notional gauge for symbol bucket."""
        bucket = self._get_symbol_bucket(symbol)
        metric_name = f"strategy_planned_notional_{bucket}"
        self.set_gauge(metric_name, notional, {})

    def _get_symbol_bucket(self, symbol: str) -> str:
        """Get symbol bucket for bounded labeling."""
        if not symbol:
            return "other"
        first_char = symbol[0].upper()
        if "A" <= first_char <= "F":
            return "A-F"
        elif "G" <= first_char <= "M":
            return "G-M"
        elif "N" <= first_char <= "S":
            return "N-S"
        elif "T" <= first_char <= "Z":
            return "T-Z"
        else:
            return "other"

    def get_metrics_data(self) -> bytes:
        """Get Prometheus exposition format data."""
        return generate_latest(self.registry)

    def get_content_type(self) -> str:
        """Get Prometheus content type."""
        return CONTENT_TYPE_LATEST

    def validate_route_template(self, route_path: str) -> str:
        """
        Validate and normalize route path using observability contracts.

        Args:
            route_path: The actual request path

        Returns:
            Normalized route template
        """
        if self.observability_contract:
            return self.observability_contract.validate_route_labeling(route_path, ROUTE_TEMPLATES)
        else:
            # Fallback to legacy normalization
            return normalize_route(route_path)

    def check_duplicate_metrics(self) -> list[str]:
        """
        Check for duplicate metric names in the registry.

        Returns:
            List of duplicate metric names
        """
        if self.observability_contract:
            return self.observability_contract.check_for_duplicate_metrics()
        else:
            # Basic duplicate check without observability contracts
            metric_names = []
            for collector in self.registry._collector_to_names:
                for metric_family in collector.collect():
                    metric_names.append(metric_family.name)

            seen = set()
            duplicates = []
            for name in metric_names:
                if name in seen:
                    duplicates.append(name)
                else:
                    seen.add(name)
            return duplicates

    def get_observability_summary(self) -> dict[str, any]:
        """
        Get observability validation summary.

        Returns:
            Dictionary with validation statistics
        """
        if self.observability_contract:
            return self.observability_contract.get_validation_summary()
        else:
            duplicates = self.check_duplicate_metrics()
            return {
                "duplicate_metrics": duplicates,
                "duplicate_count": len(duplicates),
                "observability_contracts_enabled": False,
            }


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
    uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    normalized = re.sub(uuid_pattern, "{id}", path, flags=re.IGNORECASE)

    # Replace numeric IDs with {id}
    numeric_id_pattern = r"/\d+(?=/|$)"
    normalized = re.sub(numeric_id_pattern, "/{id}", normalized)

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
    normalized = re.sub(r"/orders/[^/]+", "/orders/{id}", endpoint)

    # Replace symbols with {symbol}
    normalized = re.sub(r"/positions/[A-Z]+", "/positions/{symbol}", normalized)

    # Check if normalized endpoint exists in templates
    if normalized in ALPACA_ENDPOINT_TEMPLATES:
        return ALPACA_ENDPOINT_TEMPLATES[normalized]

    return normalized if normalized != endpoint else "/unknown"


# Global metrics registry instance
_registry: MetricsRegistry | None = None


def get_metrics_registry() -> MetricsRegistry:
    """Get the global metrics registry instance."""
    global _registry
    if _registry is None:
        _registry = MetricsRegistry()
    return _registry


def initialize_metrics_registry(
    namespace: str = "intraday", registry: CollectorRegistry | None = None
) -> MetricsRegistry:
    """Initialize the global metrics registry."""
    global _registry
    _registry = MetricsRegistry(namespace=namespace, registry=registry)
    return _registry
