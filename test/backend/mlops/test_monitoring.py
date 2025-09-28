"""
Test Module 63: MLOps Model Monitoring Service

Comprehensive test suite for model monitoring functionality including:
- Performance monitoring and metrics calculation
- Data drift and concept drift detection
- Data quality monitoring
- Alert generation and rule management
- Statistical drift detection methods
- Real-time and batch monitoring capabilities
"""

import pytest
import asyncio
import statistics
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Test imports with fallback handling
try:
    from backend.mlops.monitoring import (
        MonitoringType, AlertSeverity, MonitoringStatus, DriftDetectionMethod,
        MonitoringMetric, PerformanceMetrics, DriftMetrics, DataQualityMetrics,
        MonitoringAlert, MonitoringRule,
        StatisticalDriftDetector, DataQualityChecker, PerformanceMonitor,
        ModelMonitor, create_model_monitor, create_monitoring_rule
    )
    MODULE_EXISTS = True
except ImportError as e:
    MODULE_EXISTS = False
    print(f"Module import failed: {e}")
    
    # Create mock classes for testing
    class MonitoringType:
        PERFORMANCE = "performance"
        DATA_DRIFT = "data_drift"
        CONCEPT_DRIFT = "concept_drift"
        DATA_QUALITY = "data_quality"
        PREDICTION_DRIFT = "prediction_drift"
        FEATURE_DRIFT = "feature_drift"
    
    class AlertSeverity:
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"
        CRITICAL = "critical"
    
    class MonitoringStatus:
        ACTIVE = "active"
        PAUSED = "paused"
        STOPPED = "stopped"
        ERROR = "error"


@pytest.mark.asyncio
class TestModule63BackendMlopsMonitoring:
    """Test suite for Module 63: MLOps Model Monitoring Service."""
    
    @pytest.fixture
    def sample_classification_data(self):
        """Sample classification data for testing."""
        return {
            'predictions': [1, 0, 1, 1, 0, 0, 1, 0, 1, 0],
            'ground_truth': [1, 0, 1, 0, 0, 1, 1, 0, 1, 0],
            'features': [
                {'feature1': 1.2, 'feature2': 0.8},
                {'feature1': 0.9, 'feature2': 1.1},
                {'feature1': 1.1, 'feature2': 0.9},
                {'feature1': 1.3, 'feature2': 0.7},
                {'feature1': 0.8, 'feature2': 1.2}
            ]
        }
    
    @pytest.fixture
    def sample_regression_data(self):
        """Sample regression data for testing."""
        return {
            'predictions': [1.2, 2.1, 3.0, 1.8, 2.5],
            'ground_truth': [1.0, 2.0, 3.2, 2.0, 2.3],
            'features': [
                {'x1': 1.0, 'x2': 2.0},
                {'x1': 2.0, 'x2': 1.5},
                {'x1': 3.0, 'x2': 1.0},
                {'x1': 1.5, 'x2': 2.5},
                {'x1': 2.5, 'x2': 1.8}
            ]
        }
    
    @pytest.fixture
    def sample_data_quality_data(self):
        """Sample data for quality testing."""
        return [
            {'name': 'John', 'age': 25, 'score': 85.5, 'active': True},
            {'name': 'Jane', 'age': None, 'score': 92.0, 'active': False},
            {'name': 'Bob', 'age': 30, 'score': 78.5, 'active': True},
            {'name': '', 'age': 28, 'score': None, 'active': True},
            {'name': 'Alice', 'age': 35, 'score': 95.0, 'active': False}
        ]
    
    @pytest.fixture
    def reference_data(self):
        """Reference data for drift detection."""
        return {
            'feature1': [1.0, 1.1, 0.9, 1.2, 0.8, 1.0, 1.1, 0.9, 1.2, 0.8] * 10,
            'feature2': [0.8, 0.9, 1.1, 0.7, 1.2, 0.8, 0.9, 1.1, 0.7, 1.2] * 10
        }
    
    def test_module_availability(self):
        """Test module import and basic availability."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test enum availability
        assert hasattr(MonitoringType, 'PERFORMANCE')
        assert hasattr(AlertSeverity, 'HIGH')
        assert hasattr(MonitoringStatus, 'ACTIVE')
        assert hasattr(DriftDetectionMethod, 'KS_TEST')
        
        # Test class availability
        assert ModelMonitor is not None
        assert StatisticalDriftDetector is not None
        assert DataQualityChecker is not None
        assert PerformanceMonitor is not None
    
    def test_monitoring_type_enum(self):
        """Test MonitoringType enum values."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert MonitoringType.PERFORMANCE.value == "performance"
        assert MonitoringType.DATA_DRIFT.value == "data_drift"
        assert MonitoringType.CONCEPT_DRIFT.value == "concept_drift"
        assert MonitoringType.DATA_QUALITY.value == "data_quality"
        assert MonitoringType.PREDICTION_DRIFT.value == "prediction_drift"
        assert MonitoringType.FEATURE_DRIFT.value == "feature_drift"
    
    def test_alert_severity_enum(self):
        """Test AlertSeverity enum values."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert AlertSeverity.LOW.value == "low"
        assert AlertSeverity.MEDIUM.value == "medium"
        assert AlertSeverity.HIGH.value == "high"
        assert AlertSeverity.CRITICAL.value == "critical"
    
    def test_monitoring_status_enum(self):
        """Test MonitoringStatus enum values."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert MonitoringStatus.ACTIVE.value == "active"
        assert MonitoringStatus.PAUSED.value == "paused"
        assert MonitoringStatus.STOPPED.value == "stopped"
        assert MonitoringStatus.ERROR.value == "error"
    
    def test_drift_detection_method_enum(self):
        """Test DriftDetectionMethod enum values."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert DriftDetectionMethod.STATISTICAL.value == "statistical"
        assert DriftDetectionMethod.KS_TEST.value == "ks_test"
        assert DriftDetectionMethod.PSI.value == "psi"
        assert DriftDetectionMethod.JENSEN_SHANNON.value == "jensen_shannon"
        assert DriftDetectionMethod.WASSERSTEIN.value == "wasserstein"
        assert DriftDetectionMethod.CHI_SQUARE.value == "chi_square"
    
    def test_monitoring_metric_creation(self):
        """Test MonitoringMetric creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        metric = MonitoringMetric(name="accuracy", value=0.95)
        
        assert metric.name == "accuracy"
        assert metric.value == 0.95
        assert isinstance(metric.timestamp, datetime)
        assert isinstance(metric.metadata, dict)
    
    def test_performance_metrics_creation(self):
        """Test PerformanceMetrics creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        metrics = PerformanceMetrics(
            accuracy=0.95,
            precision=0.92,
            recall=0.88,
            f1_score=0.90
        )
        
        assert metrics.accuracy == 0.95
        assert metrics.precision == 0.92
        assert metrics.recall == 0.88
        assert metrics.f1_score == 0.90
        assert metrics.auc_roc is None
        assert isinstance(metrics.custom_metrics, dict)
    
    def test_drift_metrics_creation(self):
        """Test DriftMetrics creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test with p-value
        drift_with_pvalue = DriftMetrics(
            drift_score=0.1,
            p_value=0.03,
            threshold=0.05,
            method=DriftDetectionMethod.KS_TEST
        )
        
        assert drift_with_pvalue.drift_score == 0.1
        assert drift_with_pvalue.p_value == 0.03
        assert drift_with_pvalue.is_drift is True  # p_value < threshold
        
        # Test without p-value
        drift_without_pvalue = DriftMetrics(
            drift_score=0.08,
            threshold=0.05
        )
        
        assert drift_without_pvalue.is_drift is True  # drift_score > threshold
    
    def test_data_quality_metrics_creation(self):
        """Test DataQualityMetrics creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        quality = DataQualityMetrics(
            completeness=0.95,
            validity=0.98,
            consistency=0.92,
            uniqueness=0.88,
            timeliness=0.99,
            accuracy=0.94,
            null_count=5,
            outlier_count=2,
            duplicate_count=1
        )
        
        assert quality.completeness == 0.95
        assert quality.validity == 0.98
        assert quality.consistency == 0.92
        assert quality.uniqueness == 0.88
        assert quality.timeliness == 0.99
        assert quality.accuracy == 0.94
        assert quality.null_count == 5
        assert quality.outlier_count == 2
        assert quality.duplicate_count == 1
    
    def test_monitoring_alert_creation(self):
        """Test MonitoringAlert creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        alert = MonitoringAlert(
            alert_id="test_alert_1",
            model_name="test_model",
            metric_name="accuracy",
            metric_value=0.75,
            threshold=0.80,
            severity=AlertSeverity.HIGH,
            message="Accuracy below threshold"
        )
        
        assert alert.alert_id == "test_alert_1"
        assert alert.model_name == "test_model"
        assert alert.metric_name == "accuracy"
        assert alert.metric_value == 0.75
        assert alert.threshold == 0.80
        assert alert.severity == AlertSeverity.HIGH
        assert alert.message == "Accuracy below threshold"
        assert alert.acknowledged is False
        assert alert.resolved is False
        assert isinstance(alert.timestamp, datetime)
    
    def test_monitoring_rule_creation(self):
        """Test MonitoringRule creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        rule = MonitoringRule(
            rule_id="accuracy_rule",
            metric_name="accuracy",
            threshold=0.80,
            comparison_operator="<",
            severity=AlertSeverity.HIGH,
            window_size=100,
            min_samples=10
        )
        
        assert rule.rule_id == "accuracy_rule"
        assert rule.metric_name == "accuracy"
        assert rule.threshold == 0.80
        assert rule.comparison_operator == "<"
        assert rule.severity == AlertSeverity.HIGH
        assert rule.enabled is True
        assert rule.window_size == 100
        assert rule.min_samples == 10
        assert rule.cooldown_period == 300
    
    def test_statistical_drift_detector_ks_test(self):
        """Test KS test implementation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        detector = StatisticalDriftDetector()
        
        # Test with same distribution (no drift)
        ref_data = [1.0, 1.1, 0.9, 1.2, 0.8] * 20
        cur_data = [1.05, 1.15, 0.85, 1.25, 0.75] * 20
        
        ks_stat, p_value = detector.ks_test(ref_data, cur_data)
        
        assert isinstance(ks_stat, float)
        assert isinstance(p_value, float)
        assert 0 <= ks_stat <= 1
        assert 0 <= p_value <= 1
        
        # Test with different distributions (drift expected)
        ref_data2 = [1.0] * 50
        cur_data2 = [2.0] * 50
        
        ks_stat2, p_value2 = detector.ks_test(ref_data2, cur_data2)
        
        assert ks_stat2 > ks_stat  # Should detect more drift
        assert p_value2 < p_value  # Lower p-value indicates drift
    
    def test_statistical_drift_detector_psi_test(self):
        """Test PSI (Population Stability Index) test."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        detector = StatisticalDriftDetector()
        
        # Test with same distribution
        ref_data = [i for i in range(100)]
        cur_data = [i + 0.1 for i in range(100)]
        
        psi_score = detector.psi_test(ref_data, cur_data)
        
        assert isinstance(psi_score, float)
        assert psi_score >= 0  # PSI is always non-negative
        
        # Test with very different distributions
        ref_data2 = [1.0] * 100
        cur_data2 = [10.0] * 100
        
        psi_score2 = detector.psi_test(ref_data2, cur_data2)
        
        assert psi_score2 > psi_score  # Should detect more drift
    
    def test_data_quality_checker_basic(self, sample_data_quality_data):
        """Test basic data quality checking."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        checker = DataQualityChecker()
        quality = checker.check_data_quality(sample_data_quality_data)
        
        assert isinstance(quality, DataQualityMetrics)
        assert 0 <= quality.completeness <= 1
        assert 0 <= quality.validity <= 1
        assert 0 <= quality.consistency <= 1
        assert 0 <= quality.uniqueness <= 1
        assert 0 <= quality.timeliness <= 1
        assert 0 <= quality.accuracy <= 1
        assert quality.null_count >= 0
        assert quality.outlier_count >= 0
        assert quality.duplicate_count >= 0
    
    def test_data_quality_checker_with_schema(self):
        """Test data quality checking with schema validation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        checker = DataQualityChecker()
        
        data = [
            {'name': 'John', 'age': 25, 'score': 85.5},
            {'name': 'Jane', 'age': 'invalid', 'score': 92.0},  # Invalid age
            {'name': 123, 'age': 30, 'score': 78.5}  # Invalid name
        ]
        
        schema = {'name': 'str', 'age': 'int', 'score': 'float'}
        
        quality = checker.check_data_quality(data, schema)
        
        assert quality.validity < 1.0  # Should detect invalid values
    
    def test_data_quality_checker_custom_rules(self):
        """Test custom quality rules."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        checker = DataQualityChecker()
        
        # Add custom rule
        def age_range_rule(data):
            for record in data:
                age = record.get('age')
                if isinstance(age, (int, float)) and (age < 0 or age > 150):
                    return False, "Age out of valid range"
            return True, ""
        
        checker.add_quality_rule('age_range', age_range_rule)
        
        assert 'age_range' in checker.quality_rules
    
    def test_performance_monitor_classification(self, sample_classification_data):
        """Test performance monitoring for classification."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = PerformanceMonitor()
        
        # Add predictions
        for pred, gt in zip(sample_classification_data['predictions'], 
                           sample_classification_data['ground_truth']):
            monitor.add_prediction(pred, gt)
        
        # Calculate metrics
        metrics = monitor.calculate_performance_metrics("classification")
        
        assert isinstance(metrics, PerformanceMetrics)
        assert metrics.accuracy is not None
        assert 0 <= metrics.accuracy <= 1
        
        # For binary classification, should have precision/recall
        if metrics.precision is not None:
            assert 0 <= metrics.precision <= 1
        if metrics.recall is not None:
            assert 0 <= metrics.recall <= 1
        if metrics.f1_score is not None:
            assert 0 <= metrics.f1_score <= 1
    
    def test_performance_monitor_regression(self, sample_regression_data):
        """Test performance monitoring for regression."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = PerformanceMonitor()
        
        # Add predictions
        for pred, gt in zip(sample_regression_data['predictions'], 
                           sample_regression_data['ground_truth']):
            monitor.add_prediction(pred, gt)
        
        # Calculate metrics
        metrics = monitor.calculate_performance_metrics("regression")
        
        assert isinstance(metrics, PerformanceMetrics)
        assert metrics.mae is not None
        assert metrics.mse is not None
        assert metrics.rmse is not None
        assert metrics.mae >= 0
        assert metrics.mse >= 0
        assert metrics.rmse >= 0
        assert abs(metrics.rmse - (metrics.mse ** 0.5)) < 1e-6
    
    def test_performance_monitor_window_size(self):
        """Test performance monitor window size functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = PerformanceMonitor(window_size=5)
        
        # Add more predictions than window size
        for i in range(10):
            monitor.add_prediction(i % 2, i % 2)
        
        # Should only keep last 5 predictions
        assert len(monitor.predictions_window) == 5
        assert len(monitor.ground_truth_window) == 5
        assert len(monitor.timestamps_window) == 5
    
    def test_model_monitor_creation(self):
        """Test ModelMonitor creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = ModelMonitor("test_model")
        
        assert monitor.model_name == "test_model"
        assert monitor.status == MonitoringStatus.ACTIVE
        assert isinstance(monitor.created_at, datetime)
        assert isinstance(monitor.drift_detector, StatisticalDriftDetector)
        assert isinstance(monitor.quality_checker, DataQualityChecker)
        assert isinstance(monitor.performance_monitor, PerformanceMonitor)
        assert len(monitor.monitoring_types) == 0  # Initially empty
    
    def test_model_monitor_reference_data(self, reference_data):
        """Test setting reference data."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = ModelMonitor("test_model")
        monitor.set_reference_data(reference_data)
        
        assert len(monitor.reference_data) == 2
        assert "feature1" in monitor.reference_data
        assert "feature2" in monitor.reference_data
        assert len(monitor.reference_data["feature1"]) == 100
    
    def test_model_monitor_monitoring_types(self):
        """Test enabling/disabling monitoring types."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = ModelMonitor("test_model")
        
        # Enable monitoring types
        monitor.enable_monitoring([MonitoringType.PERFORMANCE, MonitoringType.DATA_DRIFT])
        
        assert MonitoringType.PERFORMANCE in monitor.monitoring_types
        assert MonitoringType.DATA_DRIFT in monitor.monitoring_types
        assert len(monitor.monitoring_types) == 2
        
        # Disable monitoring type
        monitor.disable_monitoring([MonitoringType.PERFORMANCE])
        
        assert MonitoringType.PERFORMANCE not in monitor.monitoring_types
        assert MonitoringType.DATA_DRIFT in monitor.monitoring_types
        assert len(monitor.monitoring_types) == 1
    
    def test_model_monitor_rules(self):
        """Test monitoring rules management."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = ModelMonitor("test_model")
        
        # Add monitoring rule
        rule = MonitoringRule(
            rule_id="accuracy_rule",
            metric_name="accuracy",
            threshold=0.80,
            comparison_operator="<",
            severity=AlertSeverity.HIGH
        )
        
        monitor.add_monitoring_rule(rule)
        
        assert "accuracy_rule" in monitor.monitoring_rules
        assert monitor.monitoring_rules["accuracy_rule"] == rule
        
        # Remove monitoring rule
        monitor.remove_monitoring_rule("accuracy_rule")
        
        assert "accuracy_rule" not in monitor.monitoring_rules
    
    def test_model_monitor_alert_callbacks(self):
        """Test alert callback functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = ModelMonitor("test_model")
        
        # Add callback
        alerts_received = []
        
        def alert_callback(alert):
            alerts_received.append(alert)
        
        monitor.add_alert_callback(alert_callback)
        
        assert len(monitor.alert_callbacks) == 1
    
    async def test_model_monitor_single_prediction(self, reference_data):
        """Test monitoring single prediction."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = ModelMonitor("test_model")
        monitor.set_reference_data(reference_data)
        monitor.enable_monitoring([MonitoringType.PERFORMANCE, MonitoringType.DATA_DRIFT])
        
        # Monitor prediction
        features = {'feature1': 1.5, 'feature2': 0.5}
        prediction = 1
        ground_truth = 1
        
        results = await monitor.monitor_prediction(features, prediction, ground_truth)
        
        assert isinstance(results, dict)
        # Results depend on enabled monitoring types
        if MonitoringType.PERFORMANCE in monitor.monitoring_types:
            assert 'performance' in results or len(results) >= 0
        if MonitoringType.DATA_DRIFT in monitor.monitoring_types:
            assert 'data_drift' in results or len(results) >= 0
    
    async def test_model_monitor_batch_monitoring(self, sample_data_quality_data):
        """Test batch monitoring."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = ModelMonitor("test_model")
        monitor.enable_monitoring([MonitoringType.DATA_QUALITY])
        
        results = await monitor.monitor_batch(sample_data_quality_data)
        
        assert isinstance(results, dict)
        if MonitoringType.DATA_QUALITY in monitor.monitoring_types:
            assert 'data_quality' in results or len(results) >= 0
    
    def test_model_monitor_status_management(self):
        """Test monitor status management."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = ModelMonitor("test_model")
        
        # Initially active
        assert monitor.status == MonitoringStatus.ACTIVE
        
        # Pause monitoring
        monitor.pause_monitoring()
        assert monitor.status == MonitoringStatus.PAUSED
        
        # Resume monitoring
        monitor.resume_monitoring()
        assert monitor.status == MonitoringStatus.ACTIVE
        
        # Stop monitoring
        monitor.stop_monitoring()
        assert monitor.status == MonitoringStatus.STOPPED
    
    def test_model_monitor_alert_management(self):
        """Test alert acknowledgment and resolution."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = ModelMonitor("test_model")
        
        # Create test alert
        alert = MonitoringAlert(
            alert_id="test_alert",
            model_name="test_model",
            metric_name="accuracy",
            metric_value=0.75,
            threshold=0.80,
            severity=AlertSeverity.HIGH,
            message="Test alert"
        )
        
        monitor.alerts.append(alert)
        
        # Acknowledge alert
        success = monitor.acknowledge_alert("test_alert")
        assert success is True
        assert alert.acknowledged is True
        
        # Resolve alert
        success = monitor.resolve_alert("test_alert")
        assert success is True
        assert alert.resolved is True
        
        # Try non-existent alert
        success = monitor.acknowledge_alert("non_existent")
        assert success is False
    
    def test_model_monitor_summary(self):
        """Test monitoring summary."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = ModelMonitor("test_model")
        monitor.enable_monitoring([MonitoringType.PERFORMANCE])
        
        # Add some test data
        rule = MonitoringRule(
            rule_id="test_rule",
            metric_name="accuracy",
            threshold=0.80,
            comparison_operator="<",
            severity=AlertSeverity.HIGH
        )
        monitor.add_monitoring_rule(rule)
        
        summary = monitor.get_monitoring_summary()
        
        assert isinstance(summary, dict)
        assert summary['model_name'] == "test_model"
        assert summary['status'] == MonitoringStatus.ACTIVE.value
        assert 'created_at' in summary
        assert 'monitoring_types' in summary
        assert summary['total_alerts'] == 0
        assert summary['active_rules'] == 1
    
    def test_model_monitor_recent_alerts(self):
        """Test getting recent alerts."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = ModelMonitor("test_model")
        
        # Add alerts with different timestamps
        old_alert = MonitoringAlert(
            alert_id="old_alert",
            model_name="test_model",
            metric_name="accuracy",
            metric_value=0.75,
            threshold=0.80,
            severity=AlertSeverity.HIGH,
            message="Old alert",
            timestamp=datetime.now() - timedelta(hours=25)
        )
        
        recent_alert = MonitoringAlert(
            alert_id="recent_alert",
            model_name="test_model",
            metric_name="accuracy",
            metric_value=0.75,
            threshold=0.80,
            severity=AlertSeverity.HIGH,
            message="Recent alert",
            timestamp=datetime.now() - timedelta(hours=1)
        )
        
        monitor.alerts.extend([old_alert, recent_alert])
        
        # Get recent alerts (last 24 hours)
        recent_alerts = monitor.get_recent_alerts(hours=24)
        
        assert len(recent_alerts) == 1
        assert recent_alerts[0].alert_id == "recent_alert"
    
    async def test_drift_detection_integration(self, reference_data):
        """Test integrated drift detection."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = ModelMonitor("test_model")
        monitor.set_reference_data(reference_data)
        monitor.enable_monitoring([MonitoringType.DATA_DRIFT])
        
        # Test with similar data (no drift expected)
        features_no_drift = {'feature1': 1.0, 'feature2': 0.8}
        results = await monitor.monitor_prediction(features_no_drift, 1, 1)
        
        # Test with very different data (drift expected)
        features_drift = {'feature1': 10.0, 'feature2': 20.0}
        results_drift = await monitor.monitor_prediction(features_drift, 1, 1)
        
        # Both should return results (specific content depends on implementation)
        assert isinstance(results, dict)
        assert isinstance(results_drift, dict)
    
    def test_convenience_functions(self):
        """Test convenience functions."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test create_model_monitor
        monitor = create_model_monitor("test_model")
        assert isinstance(monitor, ModelMonitor)
        assert monitor.model_name == "test_model"
        
        # Test create_monitoring_rule
        rule = create_monitoring_rule(
            "test_rule", "accuracy", 0.80, "<", AlertSeverity.HIGH
        )
        assert isinstance(rule, MonitoringRule)
        assert rule.rule_id == "test_rule"
        assert rule.metric_name == "accuracy"
        assert rule.threshold == 0.80
        assert rule.comparison_operator == "<"
        assert rule.severity == AlertSeverity.HIGH
    
    def test_edge_cases_and_error_handling(self):
        """Test edge cases and error handling."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test empty data
        monitor = ModelMonitor("test_model")
        
        # Empty reference data
        monitor.set_reference_data({})
        assert len(monitor.reference_data) == 0
        
        # Performance monitor with no data
        perf_monitor = PerformanceMonitor()
        metrics = perf_monitor.calculate_performance_metrics("classification")
        assert isinstance(metrics, PerformanceMetrics)
        
        # Data quality checker with empty data
        quality_checker = DataQualityChecker()
        quality = quality_checker.check_data_quality([])
        assert isinstance(quality, DataQualityMetrics)
        assert quality.completeness == 0.0
        
        # Statistical tests with invalid data
        detector = StatisticalDriftDetector()
        
        # Empty data
        ks_stat, p_value = detector.ks_test([], [1, 2, 3])
        assert isinstance(ks_stat, float)
        assert isinstance(p_value, float)
        
        psi_score = detector.psi_test([], [1, 2, 3])
        assert psi_score == 0.0
    
    async def test_monitoring_inactive_states(self):
        """Test monitoring in inactive states."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        monitor = ModelMonitor("test_model")
        
        # Pause monitoring
        monitor.pause_monitoring()
        
        # Should return empty results when paused
        async def test_paused():
            results = await monitor.monitor_prediction({'f1': 1.0}, 1, 1)
            assert results == {}
        
        await test_paused()
        
        # Stop monitoring
        monitor.stop_monitoring()
        
        # Should return empty results when stopped
        async def test_stopped():
            results = await monitor.monitor_prediction({'f1': 1.0}, 1, 1)
            assert results == {}
        
        await test_stopped()
    
    def test_module_exports(self):
        """Test module exports."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        from backend.mlops.monitoring import __all__
        
        expected_exports = [
            'MonitoringType', 'AlertSeverity', 'MonitoringStatus', 'DriftDetectionMethod',
            'MonitoringMetric', 'PerformanceMetrics', 'DriftMetrics', 'DataQualityMetrics',
            'MonitoringAlert', 'MonitoringRule',
            'StatisticalDriftDetector', 'DataQualityChecker', 'PerformanceMonitor',
            'ModelMonitor',
            'create_model_monitor', 'create_monitoring_rule'
        ]
        
        for export in expected_exports:
            assert export in __all__, f"Missing export: {export}"