"""
Module 63: MLOps Model Monitoring Service

This module provides comprehensive model monitoring functionality for tracking
model performance, data drift, concept drift, and operational metrics in production.
Includes real-time monitoring, alerting, and automated responses.
"""

from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
import math
import statistics
from typing import Any

logger = logging.getLogger(__name__)


class MonitoringType(Enum):
    """Types of model monitoring."""
    PERFORMANCE = "performance"
    DATA_DRIFT = "data_drift"
    CONCEPT_DRIFT = "concept_drift"
    DATA_QUALITY = "data_quality"
    PREDICTION_DRIFT = "prediction_drift"
    FEATURE_DRIFT = "feature_drift"


class AlertSeverity(Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MonitoringStatus(Enum):
    """Monitoring status."""
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class DriftDetectionMethod(Enum):
    """Drift detection methods."""
    STATISTICAL = "statistical"
    KS_TEST = "ks_test"
    PSI = "psi"  # Population Stability Index
    JENSEN_SHANNON = "jensen_shannon"
    WASSERSTEIN = "wasserstein"
    CHI_SQUARE = "chi_square"


@dataclass
class MonitoringMetric:
    """Monitoring metric data."""
    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceMetrics:
    """Model performance metrics."""
    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1_score: float | None = None
    auc_roc: float | None = None
    mae: float | None = None  # Mean Absolute Error
    mse: float | None = None  # Mean Squared Error
    rmse: float | None = None  # Root Mean Squared Error
    custom_metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class DriftMetrics:
    """Data/concept drift metrics."""
    drift_score: float
    p_value: float | None = None
    threshold: float = 0.05
    is_drift: bool = field(init=False)
    method: DriftDetectionMethod = DriftDetectionMethod.STATISTICAL
    features_drift: dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        if self.p_value is not None:
            self.is_drift = self.p_value < self.threshold
        else:
            self.is_drift = self.drift_score > self.threshold


@dataclass
class DataQualityMetrics:
    """Data quality metrics."""
    completeness: float  # Percentage of non-null values
    validity: float  # Percentage of valid values
    consistency: float  # Consistency score
    uniqueness: float  # Percentage of unique values
    timeliness: float  # Timeliness score
    accuracy: float  # Data accuracy score
    null_count: int = 0
    outlier_count: int = 0
    duplicate_count: int = 0


@dataclass
class MonitoringAlert:
    """Monitoring alert."""
    alert_id: str
    model_name: str
    metric_name: str
    metric_value: float
    threshold: float
    severity: AlertSeverity
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    resolved: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MonitoringRule:
    """Monitoring rule configuration."""
    rule_id: str
    metric_name: str
    threshold: float
    comparison_operator: str  # >, <, >=, <=, ==, !=
    severity: AlertSeverity
    enabled: bool = True
    window_size: int = 100  # Number of samples to consider
    min_samples: int = 10  # Minimum samples before triggering
    cooldown_period: int = 300  # Seconds between alerts
    last_triggered: datetime | None = None


class StatisticalDriftDetector:
    """Statistical drift detection methods."""

    @staticmethod
    def ks_test(reference_data: list[float], current_data: list[float]) -> tuple[float, float]:
        """Kolmogorov-Smirnov test for drift detection."""
        try:
            from scipy import stats
            statistic, p_value = stats.ks_2samp(reference_data, current_data)
            return statistic, p_value
        except Exception:
            # If SciPy is unavailable or raises at import/runtime (e.g., incompatible numpy),
            # fall back to a simple pure-Python KS implementation to keep monitoring robust.
            return StatisticalDriftDetector._simple_ks_test(reference_data, current_data)

    @staticmethod
    def _simple_ks_test(reference_data: list[float], current_data: list[float]) -> tuple[float, float]:
        """Simple KS test implementation."""
        # Handle empty data
        if not reference_data or not current_data:
            return 0.0, 1.0

        # Sort data
        ref_sorted = sorted(reference_data)
        cur_sorted = sorted(current_data)

        # Calculate empirical CDFs
        n1, n2 = len(ref_sorted), len(cur_sorted)
        all_values = sorted(set(ref_sorted + cur_sorted))

        max_diff = 0
        for value in all_values:
            cdf1 = sum(1 for x in ref_sorted if x <= value) / n1
            cdf2 = sum(1 for x in cur_sorted if x <= value) / n2
            max_diff = max(max_diff, abs(cdf1 - cdf2))

        # Approximate p-value calculation
        1.36 * ((n1 + n2) / (n1 * n2)) ** 0.5
        p_value = 2 * (2.718281828 ** (-2 * max_diff ** 2 * n1 * n2 / (n1 + n2)))

        return max_diff, min(p_value, 1.0)

    @staticmethod
    def psi_test(reference_data: list[float], current_data: list[float],
                 bins: int = 10) -> float:
        """Population Stability Index (PSI) test."""
        if not reference_data or not current_data:
            return 0.0

        # Use simple implementation to avoid numpy complications
        return StatisticalDriftDetector._simple_psi(reference_data, current_data, bins)

    @staticmethod
    def _simple_psi(reference_data: list[float], current_data: list[float], bins: int) -> float:
        """Simple PSI implementation without numpy."""
        if not reference_data or not current_data:
            return 0.0

        # Create bins using reference data quantiles
        ref_sorted = sorted(reference_data)
        n_ref = len(ref_sorted)

        # Calculate bin edges based on quantiles
        bin_edges = []
        for i in range(bins + 1):
            quantile = i / bins
            if quantile == 0:
                bin_edges.append(ref_sorted[0] - 1e-10)  # Slightly below minimum
            elif quantile == 1:
                bin_edges.append(ref_sorted[-1] + 1e-10)  # Slightly above maximum
            else:
                idx = int(quantile * (n_ref - 1))
                bin_edges.append(ref_sorted[idx])

        # Ensure unique and ascending bin edges
        bin_edges = sorted(list(set(bin_edges)))
        if len(bin_edges) < 2:
            return 0.0

        # Count occurrences in each bin
        def count_in_bins(data, edges):
            counts = [0] * (len(edges) - 1)
            for value in data:
                for i in range(len(edges) - 1):
                    if edges[i] <= value < edges[i + 1]:
                        counts[i] += 1
                        break
                else:
                    # Handle edge case where value equals the last edge
                    if value == edges[-1]:
                        counts[-1] += 1
            return counts

        ref_counts = count_in_bins(reference_data, bin_edges)
        cur_counts = count_in_bins(current_data, bin_edges)

        # Calculate probabilities with Laplace smoothing
        epsilon = 1e-10
        ref_len = len(reference_data)
        cur_len = len(current_data)

        psi = 0.0
        for i in range(len(ref_counts)):
            ref_prob = (ref_counts[i] + epsilon) / (ref_len + epsilon * len(ref_counts))
            cur_prob = (cur_counts[i] + epsilon) / (cur_len + epsilon * len(cur_counts))

            if ref_prob > 0 and cur_prob > 0:
                psi += (cur_prob - ref_prob) * math.log(cur_prob / ref_prob)

        return abs(psi)  # PSI should always be positive


class DataQualityChecker:
    """Data quality monitoring."""

    def __init__(self):
        self.quality_rules = {}

    def add_quality_rule(self, name: str, rule_func: Callable):
        """Add custom quality rule."""
        self.quality_rules[name] = rule_func

    def check_data_quality(self, data: list[dict[str, Any]],
                          schema: dict[str, str] | None = None) -> DataQualityMetrics:
        """Check data quality metrics."""
        if not data:
            return DataQualityMetrics(
                completeness=0.0, validity=0.0, consistency=0.0,
                uniqueness=0.0, timeliness=1.0, accuracy=0.0
            )

        total_fields = 0
        null_count = 0
        valid_count = 0
        unique_values = set()
        duplicates = 0
        outliers = 0

        # Get all possible fields
        all_fields = set()
        for record in data:
            all_fields.update(record.keys())

        # Check each record
        for _i, record in enumerate(data):
            record_str = str(sorted(record.items()))
            if record_str in unique_values:
                duplicates += 1
            else:
                unique_values.add(record_str)

            for field in all_fields:
                total_fields += 1
                value = record.get(field)

                # Check completeness (non-null)
                if value is None or value == "":
                    null_count += 1

                # Check validity (basic type checking)
                if schema and field in schema:
                    expected_type = schema[field]
                    if self._is_valid_type(value, expected_type):
                        valid_count += 1
                else:
                    valid_count += 1  # Assume valid if no schema

                # Simple outlier detection for numeric values
                if isinstance(value, (int, float)):
                    # Get all numeric values for this field
                    field_values = [r.get(field) for r in data
                                   if isinstance(r.get(field), (int, float))]
                    if len(field_values) > 10:
                        mean_val = statistics.mean(field_values)
                        std_val = statistics.stdev(field_values) if len(field_values) > 1 else 0
                        if std_val > 0 and abs(value - mean_val) > 3 * std_val:
                            outliers += 1

        # Calculate metrics
        completeness = (total_fields - null_count) / total_fields if total_fields > 0 else 1.0
        validity = valid_count / total_fields if total_fields > 0 else 1.0
        consistency = 0.95  # Placeholder - would need specific business rules
        uniqueness = len(unique_values) / len(data) if data else 1.0
        timeliness = 1.0  # Placeholder - would need timestamp analysis
        accuracy = 0.95  # Placeholder - would need ground truth

        return DataQualityMetrics(
            completeness=completeness,
            validity=validity,
            consistency=consistency,
            uniqueness=uniqueness,
            timeliness=timeliness,
            accuracy=accuracy,
            null_count=null_count,
            outlier_count=outliers,
            duplicate_count=duplicates
        )

    def _is_valid_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type."""
        if value is None:
            return False

        type_mapping = {
            'int': int,
            'float': (int, float),
            'str': str,
            'bool': bool,
            'list': list,
            'dict': dict
        }

        expected = type_mapping.get(expected_type.lower())
        if expected:
            return isinstance(value, expected)

        return True  # Unknown type, assume valid


class PerformanceMonitor:
    """Model performance monitoring."""

    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.predictions_window = deque(maxlen=window_size)
        self.ground_truth_window = deque(maxlen=window_size)
        self.timestamps_window = deque(maxlen=window_size)

    def add_prediction(self, prediction: Any, ground_truth: Any = None,
                      timestamp: datetime | None = None):
        """Add prediction for monitoring."""
        if timestamp is None:
            timestamp = datetime.now()

        self.predictions_window.append(prediction)
        self.ground_truth_window.append(ground_truth)
        self.timestamps_window.append(timestamp)

    def calculate_performance_metrics(self, task_type: str = "classification") -> PerformanceMetrics:
        """Calculate performance metrics."""
        if not self.predictions_window or not any(gt is not None for gt in self.ground_truth_window):
            return PerformanceMetrics()

        # Filter out None ground truth values
        valid_pairs = [(p, gt) for p, gt in zip(self.predictions_window, self.ground_truth_window, strict=False)
                      if gt is not None]

        if not valid_pairs:
            return PerformanceMetrics()

        predictions, ground_truths = zip(*valid_pairs, strict=False)

        if task_type == "classification":
            return self._calculate_classification_metrics(predictions, ground_truths)
        elif task_type == "regression":
            return self._calculate_regression_metrics(predictions, ground_truths)
        else:
            return PerformanceMetrics()

    def _calculate_classification_metrics(self, predictions: list, ground_truths: list) -> PerformanceMetrics:
        """Calculate classification metrics."""
        if not predictions or not ground_truths:
            return PerformanceMetrics()

        # Simple accuracy calculation
        correct = sum(1 for p, gt in zip(predictions, ground_truths, strict=False) if p == gt)
        accuracy = correct / len(predictions)

        # Calculate precision, recall, f1 for binary classification
        if all(isinstance(x, (int, bool)) or x in [0, 1] for x in ground_truths):
            tp = sum(1 for p, gt in zip(predictions, ground_truths, strict=False) if p == 1 and gt == 1)
            fp = sum(1 for p, gt in zip(predictions, ground_truths, strict=False) if p == 1 and gt == 0)
            fn = sum(1 for p, gt in zip(predictions, ground_truths, strict=False) if p == 0 and gt == 1)

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

            return PerformanceMetrics(
                accuracy=accuracy,
                precision=precision,
                recall=recall,
                f1_score=f1_score
            )

        return PerformanceMetrics(accuracy=accuracy)

    def _calculate_regression_metrics(self, predictions: list, ground_truths: list) -> PerformanceMetrics:
        """Calculate regression metrics."""
        if not predictions or not ground_truths:
            return PerformanceMetrics()

        try:
            # Convert to numeric values
            pred_nums = [float(p) for p in predictions if p is not None]
            gt_nums = [float(gt) for gt in ground_truths if gt is not None]

            if len(pred_nums) != len(gt_nums) or not pred_nums:
                return PerformanceMetrics()

            # Calculate metrics
            errors = [abs(p - gt) for p, gt in zip(pred_nums, gt_nums, strict=False)]
            squared_errors = [(p - gt) ** 2 for p, gt in zip(pred_nums, gt_nums, strict=False)]

            mae = statistics.mean(errors)
            mse = statistics.mean(squared_errors)
            rmse = mse ** 0.5

            return PerformanceMetrics(mae=mae, mse=mse, rmse=rmse)

        except (ValueError, TypeError):
            return PerformanceMetrics()


class ModelMonitor:
    """Main model monitoring service."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.status = MonitoringStatus.ACTIVE
        self.created_at = datetime.now()

        # Components
        self.drift_detector = StatisticalDriftDetector()
        self.quality_checker = DataQualityChecker()
        self.performance_monitor = PerformanceMonitor()

        # Data storage
        self.reference_data = {}  # Feature name -> reference values
        self.current_metrics = {}
        self.alerts = []
        self.monitoring_rules = {}

        # Configuration
        self.monitoring_types = set()
        self.alert_callbacks = []

        # Metrics history
        self.metrics_history = defaultdict(list)

    def set_reference_data(self, feature_data: dict[str, list[float]]):
        """Set reference data for drift detection."""
        self.reference_data = feature_data.copy()
        logger.info(f"Reference data set for {len(feature_data)} features")

    def add_monitoring_rule(self, rule: MonitoringRule):
        """Add monitoring rule."""
        self.monitoring_rules[rule.rule_id] = rule
        logger.info(f"Added monitoring rule: {rule.rule_id}")

    def remove_monitoring_rule(self, rule_id: str):
        """Remove monitoring rule."""
        if rule_id in self.monitoring_rules:
            del self.monitoring_rules[rule_id]
            logger.info(f"Removed monitoring rule: {rule_id}")

    def add_alert_callback(self, callback: Callable[[MonitoringAlert], None]):
        """Add alert callback function."""
        self.alert_callbacks.append(callback)

    def enable_monitoring(self, monitoring_types: list[MonitoringType]):
        """Enable specific monitoring types."""
        self.monitoring_types.update(monitoring_types)
        logger.info(f"Enabled monitoring types: {[mt.value for mt in monitoring_types]}")

    def disable_monitoring(self, monitoring_types: list[MonitoringType]):
        """Disable specific monitoring types."""
        for mt in monitoring_types:
            self.monitoring_types.discard(mt)
        logger.info(f"Disabled monitoring types: {[mt.value for mt in monitoring_types]}")

    async def monitor_prediction(self, features: dict[str, float],
                               prediction: Any, ground_truth: Any = None,
                               timestamp: datetime | None = None) -> dict[str, Any]:
        """Monitor a single prediction."""
        if self.status != MonitoringStatus.ACTIVE:
            return {}

        if timestamp is None:
            timestamp = datetime.now()

        monitoring_results = {}

        # Performance monitoring
        if MonitoringType.PERFORMANCE in self.monitoring_types and ground_truth is not None:
            self.performance_monitor.add_prediction(prediction, ground_truth, timestamp)
            perf_metrics = self.performance_monitor.calculate_performance_metrics()
            monitoring_results['performance'] = perf_metrics

            # Store metrics
            if perf_metrics.accuracy is not None:
                self._store_metric('accuracy', perf_metrics.accuracy, timestamp)
            if perf_metrics.precision is not None:
                self._store_metric('precision', perf_metrics.precision, timestamp)
            if perf_metrics.recall is not None:
                self._store_metric('recall', perf_metrics.recall, timestamp)

        # Data drift monitoring
        if MonitoringType.DATA_DRIFT in self.monitoring_types and self.reference_data:
            drift_results = await self._check_data_drift(features, timestamp)
            monitoring_results['data_drift'] = drift_results

        # Feature drift monitoring
        if MonitoringType.FEATURE_DRIFT in self.monitoring_types:
            feature_drift = await self._check_feature_drift(features, timestamp)
            monitoring_results['feature_drift'] = feature_drift

        # Check rules and generate alerts
        await self._check_monitoring_rules(monitoring_results, timestamp)

        return monitoring_results

    async def monitor_batch(self, batch_data: list[dict[str, Any]],
                          task_type: str = "classification") -> dict[str, Any]:
        """Monitor a batch of predictions."""
        if self.status != MonitoringStatus.ACTIVE:
            return {}

        monitoring_results = {}
        timestamp = datetime.now()

        # Data quality monitoring
        if MonitoringType.DATA_QUALITY in self.monitoring_types:
            quality_metrics = self.quality_checker.check_data_quality(batch_data)
            monitoring_results['data_quality'] = quality_metrics

            # Store quality metrics
            self._store_metric('completeness', quality_metrics.completeness, timestamp)
            self._store_metric('validity', quality_metrics.validity, timestamp)
            self._store_metric('consistency', quality_metrics.consistency, timestamp)

        # Batch drift detection
        if MonitoringType.DATA_DRIFT in self.monitoring_types and self.reference_data:
            batch_drift = await self._check_batch_drift(batch_data, timestamp)
            monitoring_results['batch_drift'] = batch_drift

        # Check rules and generate alerts
        await self._check_monitoring_rules(monitoring_results, timestamp)

        return monitoring_results

    async def _check_data_drift(self, features: dict[str, float],
                              timestamp: datetime) -> dict[str, DriftMetrics]:
        """Check for data drift."""
        drift_results = {}

        for feature_name, current_value in features.items():
            if feature_name in self.reference_data:
                reference_values = self.reference_data[feature_name]
                current_values = [current_value]  # Single value for now

                # Use KS test for drift detection
                try:
                    ks_stat, p_value = self.drift_detector.ks_test(reference_values, current_values)

                    drift_metrics = DriftMetrics(
                        drift_score=ks_stat,
                        p_value=p_value,
                        method=DriftDetectionMethod.KS_TEST
                    )

                    drift_results[feature_name] = drift_metrics

                    # Store drift metric
                    self._store_metric(f'drift_{feature_name}', ks_stat, timestamp)

                except Exception as e:
                    logger.error(f"Error calculating drift for {feature_name}: {e}")

        return drift_results

    async def _check_feature_drift(self, features: dict[str, float],
                                 timestamp: datetime) -> dict[str, float]:
        """Check for feature-level drift."""
        feature_drift = {}

        for feature_name, value in features.items():
            # Simple feature drift based on historical values
            if feature_name in self.metrics_history:
                historical_values = [m.value for m in self.metrics_history[feature_name][-100:]]
                if historical_values:
                    mean_historical = statistics.mean(historical_values)
                    drift_score = abs(value - mean_historical) / (statistics.stdev(historical_values) + 1e-6)
                    feature_drift[feature_name] = drift_score

                    # Store feature drift
                    self._store_metric(f'feature_drift_{feature_name}', drift_score, timestamp)

        return feature_drift

    async def _check_batch_drift(self, batch_data: list[dict[str, Any]],
                               timestamp: datetime) -> dict[str, DriftMetrics]:
        """Check drift for batch data."""
        batch_drift = {}

        if not batch_data or not self.reference_data:
            return batch_drift

        # Extract features from batch
        batch_features = defaultdict(list)
        for record in batch_data:
            for feature_name, value in record.items():
                if isinstance(value, (int, float)):
                    batch_features[feature_name].append(float(value))

        # Check drift for each feature
        for feature_name, current_values in batch_features.items():
            if feature_name in self.reference_data and current_values:
                reference_values = self.reference_data[feature_name]

                try:
                    # KS test
                    ks_stat, p_value = self.drift_detector.ks_test(reference_values, current_values)

                    # PSI test
                    psi_score = self.drift_detector.psi_test(reference_values, current_values)

                    drift_metrics = DriftMetrics(
                        drift_score=max(ks_stat, psi_score),
                        p_value=p_value,
                        method=DriftDetectionMethod.KS_TEST
                    )

                    batch_drift[feature_name] = drift_metrics

                    # Store drift metrics
                    self._store_metric(f'batch_drift_{feature_name}', drift_metrics.drift_score, timestamp)

                except Exception as e:
                    logger.error(f"Error calculating batch drift for {feature_name}: {e}")

        return batch_drift

    def _store_metric(self, metric_name: str, value: float, timestamp: datetime):
        """Store metric value."""
        metric = MonitoringMetric(name=metric_name, value=value, timestamp=timestamp)
        self.metrics_history[metric_name].append(metric)

        # Keep only recent metrics (last 10000 values)
        if len(self.metrics_history[metric_name]) > 10000:
            self.metrics_history[metric_name] = self.metrics_history[metric_name][-10000:]

        self.current_metrics[metric_name] = metric

    async def _check_monitoring_rules(self, monitoring_results: dict[str, Any],
                                    timestamp: datetime):
        """Check monitoring rules and generate alerts."""
        for _rule_id, rule in self.monitoring_rules.items():
            if not rule.enabled:
                continue

            # Check cooldown period
            if (rule.last_triggered and
                (timestamp - rule.last_triggered).total_seconds() < rule.cooldown_period):
                continue

            # Get metric value
            metric_value = self._extract_metric_value(rule.metric_name, monitoring_results)
            if metric_value is None:
                continue

            # Check if rule is violated
            if self._evaluate_rule(metric_value, rule.threshold, rule.comparison_operator):
                # Check if we have enough samples
                metric_history = self.metrics_history.get(rule.metric_name, [])
                if len(metric_history) < rule.min_samples:
                    continue

                # Generate alert
                alert = self._create_alert(rule, metric_value, timestamp)
                self.alerts.append(alert)

                # Update rule
                rule.last_triggered = timestamp

                # Trigger callbacks
                for callback in self.alert_callbacks:
                    try:
                        callback(alert)
                    except Exception as e:
                        logger.error(f"Error in alert callback: {e}")

                logger.warning(f"Alert generated: {alert.message}")

    def _extract_metric_value(self, metric_name: str, monitoring_results: dict[str, Any]) -> float | None:
        """Extract metric value from monitoring results."""
        # Try direct metric lookup first
        if metric_name in self.current_metrics:
            return self.current_metrics[metric_name].value

        # Try nested lookup in monitoring results
        for _result_type, result_data in monitoring_results.items():
            if hasattr(result_data, metric_name):
                value = getattr(result_data, metric_name)
                if isinstance(value, (int, float)):
                    return float(value)

            if isinstance(result_data, dict) and metric_name in result_data:
                value = result_data[metric_name]
                if isinstance(value, (int, float)):
                    return float(value)

        return None

    def _evaluate_rule(self, value: float, threshold: float, operator: str) -> bool:
        """Evaluate monitoring rule."""
        operators = {
            '>': lambda x, y: x > y,
            '<': lambda x, y: x < y,
            '>=': lambda x, y: x >= y,
            '<=': lambda x, y: x <= y,
            '==': lambda x, y: abs(x - y) < 1e-9,
            '!=': lambda x, y: abs(x - y) >= 1e-9
        }

        op_func = operators.get(operator)
        if op_func:
            return op_func(value, threshold)

        return False

    def _create_alert(self, rule: MonitoringRule, metric_value: float,
                     timestamp: datetime) -> MonitoringAlert:
        """Create monitoring alert."""
        alert_id = f"{self.model_name}_{rule.rule_id}_{int(timestamp.timestamp())}"

        message = (f"Monitoring alert for model '{self.model_name}': "
                  f"{rule.metric_name} = {metric_value:.4f} {rule.comparison_operator} {rule.threshold}")

        return MonitoringAlert(
            alert_id=alert_id,
            model_name=self.model_name,
            metric_name=rule.metric_name,
            metric_value=metric_value,
            threshold=rule.threshold,
            severity=rule.severity,
            message=message,
            timestamp=timestamp
        )

    def get_monitoring_summary(self) -> dict[str, Any]:
        """Get monitoring summary."""
        return {
            'model_name': self.model_name,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'monitoring_types': [mt.value for mt in self.monitoring_types],
            'total_alerts': len(self.alerts),
            'active_rules': len([r for r in self.monitoring_rules.values() if r.enabled]),
            'metrics_tracked': len(self.current_metrics),
            'last_update': max([m.timestamp for m in self.current_metrics.values()]).isoformat()
                          if self.current_metrics else None
        }

    def get_recent_alerts(self, hours: int = 24) -> list[MonitoringAlert]:
        """Get recent alerts."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [alert for alert in self.alerts if alert.timestamp >= cutoff_time]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                logger.info(f"Alert {alert_id} acknowledged")
                return True
        return False

    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert."""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                logger.info(f"Alert {alert_id} resolved")
                return True
        return False

    def pause_monitoring(self):
        """Pause monitoring."""
        self.status = MonitoringStatus.PAUSED
        logger.info(f"Monitoring paused for model {self.model_name}")

    def resume_monitoring(self):
        """Resume monitoring."""
        self.status = MonitoringStatus.ACTIVE
        logger.info(f"Monitoring resumed for model {self.model_name}")

    def stop_monitoring(self):
        """Stop monitoring."""
        self.status = MonitoringStatus.STOPPED
        logger.info(f"Monitoring stopped for model {self.model_name}")


# Convenience functions
def create_model_monitor(model_name: str) -> ModelMonitor:
    """Create a new model monitor."""
    return ModelMonitor(model_name)


def create_monitoring_rule(rule_id: str, metric_name: str, threshold: float,
                         operator: str, severity: AlertSeverity = AlertSeverity.MEDIUM) -> MonitoringRule:
    """Create a monitoring rule."""
    return MonitoringRule(
        rule_id=rule_id,
        metric_name=metric_name,
        threshold=threshold,
        comparison_operator=operator,
        severity=severity
    )


# Module exports
__all__ = [
    'MonitoringType', 'AlertSeverity', 'MonitoringStatus', 'DriftDetectionMethod',
    'MonitoringMetric', 'PerformanceMetrics', 'DriftMetrics', 'DataQualityMetrics',
    'MonitoringAlert', 'MonitoringRule',
    'StatisticalDriftDetector', 'DataQualityChecker', 'PerformanceMonitor',
    'ModelMonitor',
    'create_model_monitor', 'create_monitoring_rule'
]
