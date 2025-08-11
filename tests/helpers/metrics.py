"""
Enhanced metrics helper for parsing and validating Prometheus metrics.
"""

from collections import defaultdict

import httpx


class MetricSample:
    """Represents a single metric sample."""

    def __init__(self, name: str, labels: dict[str, str], value: float, timestamp=None):
        self.name = name
        self.labels = labels
        self.value = value
        self.timestamp = timestamp

    def __repr__(self):
        return f"MetricSample(name='{self.name}', labels={self.labels}, value={self.value})"


class MetricsParser:
    """Parser for Prometheus exposition format."""

    # Label allow-list to prevent high-cardinality issues
    LABEL_ALLOWLIST = {
        # HTTP metrics
        "http_requests_total": {"method", "endpoint", "status"},
        "http_request_duration_seconds": {"method", "endpoint"},
        # Alpaca broker metrics
        "alpaca_http_requests_total": {"endpoint", "method", "status"},
        "alpaca_http_latency_seconds": {"endpoint", "method"},
        # Outbox pattern metrics
        "outbox_dispatched_total": {"topic", "status"},
        "outbox_dispatch_latency_seconds": {"topic"},
        "outbox_queue_gauge": {"status"},
        # Database metrics
        "db_health_checks_total": {"result"},
        "db_query_duration_seconds": {"operation"},
        # WebSocket metrics
        "websocket_connections_total": {"client_type"},
        "websocket_messages_total": {"message_type", "direction"},
        "ws_messages_dropped_total": {"client_id", "reason"},
        "ws_subscriber_timeouts_total": {"client_id"},
        # Authentication metrics
        "auth_attempts_total": {"result"},
        "auth_token_validations_total": {"result"},
        # Strategy engine metrics
        "strategy_signals_total": {"source"},
        # Model inference metrics
        "model_inferences_total": {"model", "version"},
        "model_inference_latency_seconds": {"model"},
        # Risk manager metrics
        "risk_checks_total": {"result", "reason"},
        "risk_check_latency_seconds": {},
    }

    @staticmethod
    def parse(text: str) -> dict[str, list[MetricSample]]:
        """Parse Prometheus exposition format into structured metrics."""
        metrics = defaultdict(list)
        current_metric_name = None

        for line in text.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                # Extract metric name from HELP/TYPE comments
                if line.startswith("# HELP") or line.startswith("# TYPE"):
                    parts = line.split()
                    if len(parts) >= 3:
                        current_metric_name = parts[2]
                continue

            # Parse metric line: metric_name{label="value"} value timestamp?
            if "{" in line:
                # Metric with labels
                name_end = line.index("{")
                labels_end = line.rindex("}")

                name = line[:name_end]
                labels_str = line[name_end + 1 : labels_end]
                value_part = line[labels_end + 1 :].strip()

                # Parse labels
                labels = {}
                if labels_str:
                    for label_pair in labels_str.split(","):
                        if "=" in label_pair:
                            key, value = label_pair.split("=", 1)
                            key = key.strip()
                            value = value.strip().strip('"')
                            labels[key] = value
            else:
                # Metric without labels
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0]
                    value_part = parts[1]
                    labels = {}
                else:
                    continue

            # Parse value and optional timestamp
            value_parts = value_part.split()
            try:
                value = float(value_parts[0])
                timestamp = float(value_parts[1]) if len(value_parts) > 1 else None
            except (ValueError, IndexError):
                continue

            metrics[name].append(MetricSample(name, labels, value, timestamp))

        return dict(metrics)

    @classmethod
    def validate_labels(cls, metrics: dict[str, list[MetricSample]]) -> list[str]:
        """Validate that metrics don't have high-cardinality labels."""
        violations = []

        for metric_name, samples in metrics.items():
            allowed_labels = cls.LABEL_ALLOWLIST.get(metric_name, set())

            for sample in samples:
                extra_labels = set(sample.labels.keys()) - allowed_labels
                if extra_labels:
                    violations.append(
                        f"Metric '{metric_name}' has unauthorized labels: {extra_labels}. "
                        f"Allowed: {allowed_labels}"
                    )

        return violations


class MetricsClient:
    """Client for fetching and parsing metrics from the /metrics endpoint."""

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.parser = MetricsParser()

    async def scrape(self) -> dict[str, list[MetricSample]]:
        """Scrape metrics from /metrics endpoint."""
        response = await self.client.get("/metrics")
        response.raise_for_status()

        return self.parser.parse(response.text)

    async def get_metric(self, name: str) -> list[MetricSample]:
        """Get samples for a specific metric."""
        metrics = await self.scrape()
        return metrics.get(name, [])

    async def assert_metric_exists(self, name: str, expected_labels: dict[str, str] = None):
        """Assert that a metric exists with optional label matching."""
        samples = await self.get_metric(name)
        assert samples, f"Metric '{name}' not found"

        if expected_labels:
            matching_samples = [
                s for s in samples if all(s.labels.get(k) == v for k, v in expected_labels.items())
            ]
            assert matching_samples, f"No samples found for '{name}' with labels {expected_labels}"

    async def assert_no_high_cardinality_labels(self):
        """Assert that no metrics have high-cardinality labels."""
        metrics = await self.scrape()
        violations = self.parser.validate_labels(metrics)
        assert not violations, f"High-cardinality label violations: {violations}"

    async def get_histogram_buckets(self, name: str) -> dict[str, float]:
        """Get histogram bucket values for a metric."""
        bucket_name = f"{name}_bucket"
        samples = await self.get_metric(bucket_name)

        buckets = {}
        for sample in samples:
            le = sample.labels.get("le")
            if le:
                buckets[le] = sample.value

        return buckets
