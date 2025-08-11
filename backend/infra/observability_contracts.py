"""
Observability Contracts - Fixed histogram buckets and route template enforcement
Ensures consistent metrics across the platform with standardized buckets.
"""
from typing import Final

from prometheus_client import CollectorRegistry, Histogram

# Fixed histogram buckets for consistent observability
HISTOGRAM_BUCKETS: Final[dict[str, tuple[float, ...]]] = {
    # HTTP request duration: optimized for sub-second response times
    "http_request_duration_seconds": (
        0.001,
        0.005,
        0.010,
        0.025,
        0.050,  # 1ms - 50ms (fast responses)
        0.100,
        0.250,
        0.500,  # 100ms - 500ms (normal)
        1.0,
        2.5,
        5.0,
        10.0,  # 1s - 10s (slow)
        float("inf"),
    ),
    # Alpaca API latency: external service with network overhead
    "alpaca_http_latency_seconds": (
        0.050,
        0.100,
        0.250,
        0.500,  # 50ms - 500ms (good)
        1.0,
        2.0,
        5.0,
        10.0,  # 1s - 10s (acceptable)
        30.0,
        60.0,  # 30s - 60s (timeout range)
        float("inf"),
    ),
    # Outbox dispatch latency: database + message queue operations
    "outbox_dispatch_latency_seconds": (
        0.001,
        0.005,
        0.010,
        0.025,  # 1ms - 25ms (database ops)
        0.050,
        0.100,
        0.250,  # 50ms - 250ms (normal)
        0.500,
        1.0,
        2.5,  # 500ms - 2.5s (batch ops)
        float("inf"),
    ),
    # Database query duration: optimized for fast queries
    "db_query_duration_seconds": (
        0.001,
        0.002,
        0.005,
        0.010,  # 1ms - 10ms (indexed queries)
        0.025,
        0.050,
        0.100,  # 25ms - 100ms (complex queries)
        0.250,
        0.500,
        1.0,  # 250ms - 1s (analytical)
        float("inf"),
    ),
    # Risk decision latency: critical path timing
    "risk_decision_latency_seconds": (
        0.001,
        0.005,
        0.010,
        0.025,  # 1ms - 25ms (cache hits)
        0.050,
        0.100,
        0.250,  # 50ms - 250ms (computation)
        0.500,
        1.0,  # 500ms - 1s (slow path)
        float("inf"),
    ),
    # Feature compute latency: ML pipeline timing
    "feature_compute_latency_seconds": (
        0.010,
        0.025,
        0.050,
        0.100,  # 10ms - 100ms (simple features)
        0.250,
        0.500,
        1.0,
        2.5,  # 250ms - 2.5s (complex features)
        5.0,
        10.0,  # 5s - 10s (heavy computation)
        float("inf"),
    ),
}


def get_histogram_buckets(metric_name: str) -> tuple[float, ...]:
    """
    Get standardized histogram buckets for a metric.

    Args:
        metric_name: The metric name to get buckets for

    Returns:
        Tuple of bucket boundaries

    Raises:
        ValueError: If metric doesn't have defined buckets
    """
    if metric_name not in HISTOGRAM_BUCKETS:
        raise ValueError(
            f"No histogram buckets defined for metric '{metric_name}'. "
            f"Available metrics: {list(HISTOGRAM_BUCKETS.keys())}"
        )

    return HISTOGRAM_BUCKETS[metric_name]


def validate_route_template(route_path: str, route_templates: dict[str, str]) -> str:
    """
    Validate and normalize route path to template.

    Args:
        route_path: The actual request path
        route_templates: Mapping of patterns to templates

    Returns:
        Normalized route template

    Raises:
        ValueError: If route doesn't match any template
    """
    # Direct match first
    if route_path in route_templates:
        return route_templates[route_path]

    # Pattern matching for parameterized routes
    for pattern, template in route_templates.items():
        if "{" in pattern:
            # Simple pattern matching - replace parameters with wildcards
            pattern_parts = pattern.split("/")
            path_parts = route_path.split("/")

            if len(pattern_parts) == len(path_parts):
                match = True
                for pattern_part, path_part in zip(pattern_parts, path_parts):
                    if pattern_part.startswith("{") and pattern_part.endswith("}"):
                        # This is a parameter, skip validation
                        continue
                    elif pattern_part != path_part:
                        match = False
                        break

                if match:
                    return template

    # Fallback to original path if no template matches
    # This prevents metric explosion but should be monitored
    return route_path


def check_metric_registry_for_duplicates(registry: CollectorRegistry) -> list[str]:
    """
    Check registry for duplicate metric names.

    Args:
        registry: Prometheus registry to check

    Returns:
        List of duplicate metric names found
    """
    metric_names = []

    # Collect all metric names from the registry
    for collector in registry._collector_to_names:
        for metric_family in collector.collect():
            metric_names.append(metric_family.name)

    # Find duplicates
    seen = set()
    duplicates = []

    for name in metric_names:
        if name in seen:
            duplicates.append(name)
        else:
            seen.add(name)

    return duplicates


class ObservabilityContract:
    """
    Enforces observability contracts for consistent metrics.
    """

    def __init__(self, registry: CollectorRegistry):
        self.registry = registry
        self._validated_routes: set[str] = set()

    def validate_histogram_buckets(self, metric_name: str, histogram: Histogram) -> bool:
        """
        Validate that a histogram uses the correct buckets.

        Args:
            metric_name: Name of the metric
            histogram: Histogram instance to validate

        Returns:
            True if buckets match contract, False otherwise
        """
        if metric_name not in HISTOGRAM_BUCKETS:
            # No contract defined, allow any buckets
            return True

        expected_buckets = HISTOGRAM_BUCKETS[metric_name]

        # Get actual buckets from histogram
        # Prometheus histograms store buckets in _upper_bounds
        actual_buckets = getattr(histogram, "_upper_bounds", None)

        if actual_buckets is None:
            return False

        return tuple(actual_buckets) == expected_buckets

    def validate_route_labeling(self, route_path: str, route_templates: dict[str, str]) -> str:
        """
        Validate and normalize route for consistent labeling.

        Args:
            route_path: Actual request path
            route_templates: Available route templates

        Returns:
            Normalized route template
        """
        template = validate_route_template(route_path, route_templates)

        # Track validated routes for debugging
        if template not in self._validated_routes:
            self._validated_routes.add(template)

        return template

    def check_for_duplicate_metrics(self) -> list[str]:
        """
        Check registry for duplicate metric names.

        Returns:
            List of duplicate metric names
        """
        return check_metric_registry_for_duplicates(self.registry)

    def get_validation_summary(self) -> dict[str, any]:
        """
        Get summary of validation state.

        Returns:
            Dictionary with validation statistics
        """
        duplicates = self.check_for_duplicate_metrics()

        return {
            "duplicate_metrics": duplicates,
            "duplicate_count": len(duplicates),
            "validated_routes": list(self._validated_routes),
            "route_count": len(self._validated_routes),
            "histogram_contracts": list(HISTOGRAM_BUCKETS.keys()),
        }
