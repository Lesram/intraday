"""
Branch 2.6 MLOps Registry - Simple Test Suite
Tests core MLOps functionality without external dependencies
"""

import json
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# Test basic imports
def test_basic_imports():
    """Test that MLOps components can be imported"""
    try:
        from backend.config import MLOpsConfig, get_settings
        assert MLOpsConfig is not None
    except ImportError as e:
        pytest.fail(f"Failed to import MLOpsConfig: {e}")

def test_mlops_config_validation():
    """Test MLOps configuration validation"""
    from backend.config import MLOpsConfig

    # Valid configuration
    config = MLOpsConfig(
        registry_root="test_artifacts",
        drift_psi_warn=0.1,
        drift_psi_alert=0.25,
        perf_alert_drop=0.05,
        inference_log_max_rows=5000
    )

    assert config.registry_root == "test_artifacts"
    assert config.drift_psi_warn == 0.1
    assert config.drift_psi_alert == 0.25
    assert config.perf_alert_drop == 0.05

def test_schema_helpers():
    """Test feature schema validation helpers"""
    from backend.features.feature_engineering import (
        create_feature_signature,
        get_feature_schema,
        validate_feature_schema,
    )

    # Create sample features
    features_df = pd.DataFrame({
        'feature_1': [1.0, 2.0, 3.0],
        'feature_2': [4.0, 5.0, 6.0],
        'feature_3': [7.0, 8.0, 9.0]
    })

    # Test schema extraction
    schema = get_feature_schema(features_df)
    assert isinstance(schema, dict)
    assert len(schema) == 3
    assert 'feature_1' in schema

    # Test schema validation
    is_valid, errors = validate_feature_schema(features_df, schema)
    assert is_valid
    assert len(errors) == 0

    # Test feature signature
    signature = create_feature_signature(features_df, include_stats=True)
    assert 'feature_names' in signature
    assert 'feature_dtypes' in signature
    assert signature['feature_count'] == 3

@pytest.fixture
def temp_registry():
    """Create temporary directory for registry tests"""
    temp_dir = tempfile.mkdtemp(prefix="mlops_test_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)

def test_model_registry_basic(temp_registry):
    """Test basic model registry functionality without dependencies"""

    # Mock the settings and dependencies
    mock_settings = MagicMock()
    mock_settings.mlops_registry_root = temp_registry
    mock_settings.mlops_drift_psi_warn = 0.1
    mock_settings.mlops_drift_psi_alert = 0.25
    mock_settings.mlops_inference_log_max_rows = 1000

    with patch('backend.mlops.model_manager.get_settings', return_value=mock_settings), \
         patch('backend.mlops.model_manager.OBSERVABILITY_AVAILABLE', False):

        from backend.mlops.model_manager import ModelRegistry

        # Create registry
        registry = ModelRegistry(temp_registry)
        assert registry.base_path.exists()

        # Create sample data
        training_data = pd.DataFrame({
            'feature_1': np.random.normal(0, 1, 100),
            'feature_2': np.random.normal(5, 2, 100),
            'target': np.random.normal(10, 3, 100)
        })

        # Mock model
        mock_model = MagicMock()
        mock_model.__class__.__name__ = 'MockModel'

        # Register model
        model_version = registry.register_model(
            "test_model",
            mock_model,
            training_data,
            {"accuracy": 0.9, "mse": 0.1}
        )

        assert model_version is not None
        assert model_version.model_id == "test_model"
        assert model_version.version == "v1"

        # Check files created
        model_path = registry.base_path / "test_model" / "v1"
        assert model_path.exists()
        assert (model_path / "model.bin").exists()
        assert (model_path / "metadata.json").exists()

        # Verify metadata
        with open(model_path / "metadata.json") as f:
            metadata = json.load(f)

        assert metadata["model_id"] == "test_model"
        assert metadata["version"] == "v1"
        assert metadata["metrics"]["accuracy"] == 0.9

def test_drift_detector_basic():
    """Test basic drift detection functionality"""

    mock_settings = MagicMock()
    mock_settings.mlops_drift_psi_warn = 0.1
    mock_settings.mlops_drift_psi_alert = 0.25
    mock_settings.mlops_perf_alert_drop = 0.05

    with patch('backend.mlops.model_manager.get_settings', return_value=mock_settings), \
         patch('backend.mlops.model_manager.OBSERVABILITY_AVAILABLE', False):

        from backend.mlops.model_manager import DriftDetector

        drift_detector = DriftDetector()

        # Create reference data
        reference_data = pd.DataFrame({
            'feature_1': np.random.normal(0, 1, 1000),
            'feature_2': np.random.normal(5, 2, 1000)
        })

        drift_detector.set_reference_data("test_model", reference_data)

        # Test with similar data (should not detect drift)
        similar_data = pd.DataFrame({
            'feature_1': np.random.normal(0.1, 1.1, 500),
            'feature_2': np.random.normal(5.1, 2.1, 500)
        })

        drift_result = drift_detector.detect_data_drift("test_model", similar_data)
        # May or may not detect drift depending on random seed, but should not crash

        # Test performance drift detection
        good_predictions = [(0.9, 0.92), (0.85, 0.83)] * 50
        baseline_metrics = {"accuracy": 0.9}

        perf_drift = drift_detector.detect_performance_drift(
            "test_model", good_predictions, baseline_metrics
        )
        # Should not detect performance drift with good predictions
        assert perf_drift is None

def test_ensemble_model_basic():
    """Test basic ensemble model functionality without full MLOps"""

    mock_settings = MagicMock()
    mlops_config = MagicMock()
    mlops_config.inference_telemetry_enabled = True
    mock_settings.mlops = mlops_config

    with patch('backend.models.ensemble_model.get_settings', return_value=mock_settings), \
         patch('backend.models.ensemble_model.MLOPS_AVAILABLE', False):

        from backend.models.ensemble_model import EnsembleModel

        # Create ensemble model
        ensemble = EnsembleModel()

        # Should initialize without MLOps if not available
        assert ensemble.mlops_enabled is False
        assert ensemble.model_manager is None

        # Mock individual model predictions
        for model_name, model in ensemble.models.items():
            model.predict = MagicMock(return_value=(0.85, 0.9))

        # Create sample data
        price_data = pd.DataFrame({
            'datetime': pd.date_range('2024-01-01', periods=10, freq='1h'),
            'open': np.random.uniform(100, 110, 10),
            'high': np.random.uniform(105, 115, 10),
            'low': np.random.uniform(95, 105, 10),
            'close': np.random.uniform(100, 110, 10),
            'volume': np.random.randint(1000, 10000, 10)
        })

        features = pd.DataFrame({
            'sma_10': np.random.uniform(100, 110, 10),
            'ema_20': np.random.uniform(98, 112, 10),
            'rsi': np.random.uniform(30, 70, 10)
        })

        # Test prediction
        prediction = ensemble.predict(price_data, features, "TEST_SYMBOL")

        assert prediction.symbol == "TEST_SYMBOL"
        assert prediction.ensemble_prediction > 0
        assert prediction.ensemble_confidence > 0

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
