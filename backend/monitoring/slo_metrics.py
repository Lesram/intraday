#!/usr/bin/env python3
"""
Production SLO Metrics Collection System
Hedge Fund Grade Monitoring with Prometheus Integration
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import logging
import threading
from typing import Any

# Prometheus client for metrics export
try:
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        Summary,
        generate_latest,
        start_http_server,
    )
except ImportError:
    # If prometheus_client not installed, create mock classes
    class MetricMock:
        def __init__(self, *args, **kwargs): pass
        def inc(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
        def set(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def time(self): return self
        def __enter__(self): return self
        def __exit__(self, *args): pass

    Counter = Histogram = Gauge = Summary = MetricMock
    def CollectorRegistry():
        return None
    def start_http_server(*args):
        return None
    def generate_latest(*args):
        return b""

class SLOCategory(Enum):
    """SLO Categories for hedge fund operations"""
    ORDER_LATENCY = "order_latency"
    ORDER_ACCURACY = "order_accuracy"
    FILL_RATE = "fill_rate"
    SYSTEM_AVAILABILITY = "system_availability"
    DATA_INTEGRITY = "data_integrity"
    RISK_COMPLIANCE = "risk_compliance"

@dataclass
class SLOTarget:
    """SLO Target Definition"""
    name: str
    category: SLOCategory
    target_percentile: float  # e.g., 99.0 for P99
    target_value: float       # e.g., 100.0 for 100ms
    unit: str                 # e.g., "ms", "%", "ratio"
    window_seconds: int       # e.g., 3600 for 1 hour
    burn_rate_threshold: float # e.g., 0.1 for 10% error budget consumption

@dataclass
class SLOViolation:
    """SLO Violation Event"""
    timestamp: datetime
    slo_name: str
    actual_value: float
    target_value: float
    severity: str
    burn_rate: float
    context: dict[str, Any]

class SLOMetricsCollector:
    """
    Production-grade SLO metrics collection with Prometheus integration
    Designed for hedge fund operational requirements
    """

    def __init__(self, registry = None):
        """Initialize SLO metrics collector"""
        self.registry = registry or CollectorRegistry()
        self.logger = logging.getLogger(__name__)

        # SLO Targets Configuration (Hedge Fund Grade)
        self.slo_targets = {
            "order_submission_latency_p99": SLOTarget(
                name="order_submission_latency_p99",
                category=SLOCategory.ORDER_LATENCY,
                target_percentile=99.0,
                target_value=100.0,  # 100ms P99
                unit="ms",
                window_seconds=3600,  # 1 hour
                burn_rate_threshold=0.1  # 10% error budget per hour
            ),
            "order_accuracy_daily": SLOTarget(
                name="order_accuracy_daily",
                category=SLOCategory.ORDER_ACCURACY,
                target_percentile=100.0,
                target_value=95.0,  # 95% accuracy
                unit="%",
                window_seconds=86400,  # 24 hours
                burn_rate_threshold=0.05  # 5% error budget per day
            ),
            "fill_rate_5min": SLOTarget(
                name="fill_rate_5min",
                category=SLOCategory.FILL_RATE,
                target_percentile=100.0,
                target_value=98.0,  # 98% fill rate
                unit="%",
                window_seconds=300,  # 5 minutes
                burn_rate_threshold=0.2  # 20% error budget per 5min
            ),
            "system_availability_hourly": SLOTarget(
                name="system_availability_hourly",
                category=SLOCategory.SYSTEM_AVAILABILITY,
                target_percentile=100.0,
                target_value=99.9,  # 99.9% uptime
                unit="%",
                window_seconds=3600,  # 1 hour
                burn_rate_threshold=0.1  # 10% error budget per hour
            )
        }

        # Initialize Prometheus metrics
        self._init_prometheus_metrics()

        # SLO state tracking
        self.slo_violations: list[SLOViolation] = []
        self.metrics_buffer = defaultdict(deque)
        self.last_calculation = {}

        # Background thread for SLO calculations
        self._calculation_thread = None
        self._stop_event = threading.Event()

    def _init_prometheus_metrics(self):
        """Initialize Prometheus metrics for SLO monitoring"""

        # Order Latency Metrics
        self.order_latency_histogram = Histogram(
            'trading_order_latency_seconds',
            'Order submission latency in seconds',
            ['order_type', 'symbol', 'account'],
            registry=self.registry,
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
        )

        # Order Accuracy Metrics
        self.order_accuracy_counter = Counter(
            'trading_orders_total',
            'Total orders by outcome',
            ['status', 'order_type', 'symbol'],
            registry=self.registry
        )

        # Fill Rate Metrics
        self.fill_events_counter = Counter(
            'trading_fills_total',
            'Total fill events',
            ['fill_type', 'symbol', 'account'],
            registry=self.registry
        )

        # System Health Metrics
        self.system_health_gauge = Gauge(
            'trading_system_health_score',
            'Overall system health score (0-100)',
            ['component'],
            registry=self.registry
        )

        # SLO Compliance Metrics
        self.slo_compliance_gauge = Gauge(
            'trading_slo_compliance_ratio',
            'SLO compliance ratio (0-1)',
            ['slo_name', 'window'],
            registry=self.registry
        )

        # Error Budget Metrics
        self.error_budget_gauge = Gauge(
            'trading_slo_error_budget_remaining',
            'Remaining error budget (0-1)',
            ['slo_name', 'window'],
            registry=self.registry
        )

        # Burn Rate Metrics
        self.burn_rate_gauge = Gauge(
            'trading_slo_burn_rate',
            'Current SLO error budget burn rate',
            ['slo_name', 'window'],
            registry=self.registry
        )

        # Alert Status Metrics
        self.alert_status_gauge = Gauge(
            'trading_slo_alert_active',
            'SLO alert status (0=ok, 1=warning, 2=critical)',
            ['slo_name', 'severity'],
            registry=self.registry
        )

    def record_order_latency(self, latency_ms: float, order_type: str = "market",
                            symbol: str = "unknown", account: str = "default"):
        """Record order submission latency"""
        latency_seconds = latency_ms / 1000.0

        # Record in Prometheus
        self.order_latency_histogram.labels(
            order_type=order_type,
            symbol=symbol,
            account=account
        ).observe(latency_seconds)

        # Buffer for SLO calculation
        self.metrics_buffer['order_latency'].append({
            'timestamp': datetime.now(),
            'latency_ms': latency_ms,
            'order_type': order_type,
            'symbol': symbol,
            'account': account
        })

        # Keep buffer size manageable (last 10,000 events)
        if len(self.metrics_buffer['order_latency']) > 10000:
            self.metrics_buffer['order_latency'].popleft()

    def record_order_outcome(self, status: str, order_type: str = "market", symbol: str = "unknown"):
        """Record order execution outcome"""

        # Record in Prometheus
        self.order_accuracy_counter.labels(
            status=status,
            order_type=order_type,
            symbol=symbol
        ).inc()

        # Buffer for SLO calculation
        self.metrics_buffer['order_outcomes'].append({
            'timestamp': datetime.now(),
            'status': status,
            'order_type': order_type,
            'symbol': symbol
        })

        # Keep buffer manageable
        if len(self.metrics_buffer['order_outcomes']) > 10000:
            self.metrics_buffer['order_outcomes'].popleft()

    def record_fill_event(self, fill_type: str = "full", symbol: str = "unknown",
                         account: str = "default", filled_qty: float = 0):
        """Record order fill event"""

        # Record in Prometheus
        self.fill_events_counter.labels(
            fill_type=fill_type,
            symbol=symbol,
            account=account
        ).inc()

        # Buffer for SLO calculation
        self.metrics_buffer['fill_events'].append({
            'timestamp': datetime.now(),
            'fill_type': fill_type,
            'symbol': symbol,
            'account': account,
            'filled_qty': filled_qty
        })

    def update_system_health(self, component: str, health_score: float):
        """Update system health score (0-100)"""

        self.system_health_gauge.labels(component=component).set(health_score)

        # Buffer for SLO calculation
        self.metrics_buffer['system_health'].append({
            'timestamp': datetime.now(),
            'component': component,
            'health_score': health_score
        })

    def calculate_slo_compliance(self, slo_name: str) -> dict[str, float]:
        """Calculate current SLO compliance and burn rate"""

        if slo_name not in self.slo_targets:
            return {}

        target = self.slo_targets[slo_name]
        now = datetime.now()
        window_start = now - timedelta(seconds=target.window_seconds)

        result = {
            'compliance_ratio': 1.0,
            'error_budget_remaining': 1.0,
            'burn_rate': 0.0,
            'alert_level': 0  # 0=ok, 1=warning, 2=critical
        }

        if slo_name == "order_submission_latency_p99":
            # Calculate P99 latency from buffer
            recent_latencies = [
                event['latency_ms']
                for event in self.metrics_buffer['order_latency']
                if event['timestamp'] >= window_start
            ]

            if len(recent_latencies) >= 10:  # Need minimum samples
                recent_latencies.sort()
                p99_index = int(len(recent_latencies) * 0.99)
                p99_latency = recent_latencies[p99_index]

                if p99_latency <= target.target_value:
                    result['compliance_ratio'] = 1.0
                else:
                    # Calculate compliance ratio
                    violation_ratio = min(1.0, (p99_latency - target.target_value) / target.target_value)
                    result['compliance_ratio'] = 1.0 - violation_ratio

                # Calculate error budget and burn rate
                error_rate = 1.0 - result['compliance_ratio']
                result['error_budget_remaining'] = max(0.0, 1.0 - (error_rate / target.burn_rate_threshold))
                result['burn_rate'] = error_rate / target.burn_rate_threshold

                # Determine alert level
                if result['burn_rate'] > 1.0:
                    result['alert_level'] = 2  # Critical
                elif result['burn_rate'] > 0.5:
                    result['alert_level'] = 1  # Warning

        elif slo_name == "order_accuracy_daily":
            # Calculate accuracy from recent orders
            recent_orders = [
                event for event in self.metrics_buffer['order_outcomes']
                if event['timestamp'] >= window_start
            ]

            if len(recent_orders) >= 5:  # Need minimum samples
                successful_orders = len([o for o in recent_orders if o['status'] in ['filled', 'partial_fill']])
                accuracy = (successful_orders / len(recent_orders)) * 100

                result['compliance_ratio'] = min(1.0, accuracy / target.target_value)
                error_rate = max(0.0, 1.0 - result['compliance_ratio'])
                result['error_budget_remaining'] = max(0.0, 1.0 - (error_rate / target.burn_rate_threshold))
                result['burn_rate'] = error_rate / target.burn_rate_threshold

                # Alert levels
                if accuracy < target.target_value * 0.9:  # <85.5% for 95% target
                    result['alert_level'] = 2
                elif accuracy < target.target_value * 0.95:  # <90.25% for 95% target
                    result['alert_level'] = 1

        # Update Prometheus metrics
        self.slo_compliance_gauge.labels(slo_name=slo_name, window=f"{target.window_seconds}s").set(result['compliance_ratio'])
        self.error_budget_gauge.labels(slo_name=slo_name, window=f"{target.window_seconds}s").set(result['error_budget_remaining'])
        self.burn_rate_gauge.labels(slo_name=slo_name, window=f"{target.window_seconds}s").set(result['burn_rate'])
        self.alert_status_gauge.labels(slo_name=slo_name, severity="current").set(result['alert_level'])

        return result

    def check_slo_violations(self) -> list[SLOViolation]:
        """Check for SLO violations and return list of current violations"""

        violations = []

        for slo_name in self.slo_targets:
            compliance_data = self.calculate_slo_compliance(slo_name)

            if compliance_data.get('alert_level', 0) > 0:
                violation = SLOViolation(
                    timestamp=datetime.now(),
                    slo_name=slo_name,
                    actual_value=compliance_data['compliance_ratio'],
                    target_value=1.0,
                    severity="critical" if compliance_data['alert_level'] == 2 else "warning",
                    burn_rate=compliance_data['burn_rate'],
                    context={
                        'error_budget_remaining': compliance_data['error_budget_remaining'],
                        'window_seconds': self.slo_targets[slo_name].window_seconds
                    }
                )
                violations.append(violation)

        return violations

    def start_background_monitoring(self, calculation_interval: int = 30):
        """Start background thread for continuous SLO monitoring"""

        def monitoring_loop():
            while not self._stop_event.is_set():
                try:
                    # Calculate SLO compliance for all targets
                    for slo_name in self.slo_targets:
                        self.calculate_slo_compliance(slo_name)

                    # Check for violations
                    violations = self.check_slo_violations()

                    if violations:
                        self.logger.warning(f"SLO violations detected: {len(violations)} active violations")
                        for violation in violations:
                            self.logger.warning(f"  {violation.slo_name}: {violation.severity} "
                                              f"(burn rate: {violation.burn_rate:.2f})")

                    # Wait for next calculation
                    self._stop_event.wait(calculation_interval)

                except Exception as e:
                    self.logger.error(f"Error in SLO monitoring loop: {e}")
                    self._stop_event.wait(calculation_interval)

        if self._calculation_thread is None or not self._calculation_thread.is_alive():
            self._calculation_thread = threading.Thread(target=monitoring_loop, daemon=True)
            self._calculation_thread.start()
            self.logger.info(f"SLO monitoring started with {calculation_interval}s interval")

    def stop_monitoring(self):
        """Stop background monitoring"""
        if self._calculation_thread and self._calculation_thread.is_alive():
            self._stop_event.set()
            self._calculation_thread.join(timeout=5)
            self.logger.info("SLO monitoring stopped")

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get comprehensive metrics summary"""

        summary = {
            'timestamp': datetime.now().isoformat(),
            'slo_targets': {},
            'violations': [],
            'system_health': {}
        }

        # Calculate current SLO status
        for slo_name in self.slo_targets:
            compliance_data = self.calculate_slo_compliance(slo_name)
            target = self.slo_targets[slo_name]

            summary['slo_targets'][slo_name] = {
                'compliance_ratio': compliance_data.get('compliance_ratio', 1.0),
                'error_budget_remaining': compliance_data.get('error_budget_remaining', 1.0),
                'burn_rate': compliance_data.get('burn_rate', 0.0),
                'alert_level': compliance_data.get('alert_level', 0),
                'target_value': target.target_value,
                'unit': target.unit,
                'window_seconds': target.window_seconds
            }

        # Current violations
        violations = self.check_slo_violations()
        summary['violations'] = [
            {
                'slo_name': v.slo_name,
                'severity': v.severity,
                'burn_rate': v.burn_rate,
                'actual_value': v.actual_value,
                'target_value': v.target_value
            }
            for v in violations
        ]

        # Buffer statistics
        summary['buffer_stats'] = {
            metric_type: len(buffer)
            for metric_type, buffer in self.metrics_buffer.items()
        }

        return summary

    def export_prometheus_metrics(self) -> bytes:
        """Export current metrics in Prometheus format"""
        return generate_latest(self.registry)

# Global SLO collector instance
_slo_collector = None

def get_slo_collector() -> SLOMetricsCollector:
    """Get global SLO collector instance"""
    global _slo_collector
    if _slo_collector is None:
        _slo_collector = SLOMetricsCollector()
    return _slo_collector

def start_metrics_server(port: int = 8000):
    """Start Prometheus metrics HTTP server"""
    try:
        start_http_server(port)
        logging.info(f"Prometheus metrics server started on port {port}")
        return True
    except Exception as e:
        logging.error(f"Failed to start metrics server: {e}")
        return False
