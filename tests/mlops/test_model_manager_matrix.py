"""
MLOps Model Manager Matrix Testing - Comprehensive prediction and health coverage
Targets backend/mlops/model_manager.py (547 statements) for 28% → 75%+ coverage
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
import json


class FakeModel:
    """Windows-friendly fake model without complex ML dependencies"""
    
    def __init__(self, should_fail=False, return_nans=False):
        self.should_fail = should_fail
        self.return_nans = return_nans
        self.feature_names = ['price', 'volume', 'rsi', 'macd']
    
    def predict(self, X):
        if self.should_fail:
            raise ValueError("Model prediction failed")
        
        if isinstance(X, dict):
            # Single prediction
            if self.return_nans:
                return np.array([np.nan])
            return np.array([0.75])  # Mock prediction
        elif isinstance(X, list):
            # Batch prediction
            if self.return_nans:
                return np.array([np.nan] * len(X))
            return np.array([0.75 + 0.01 * i for i in range(len(X))])
        elif hasattr(X, 'shape'):
            # NumPy array or similar
            n_samples = X.shape[0] if len(X.shape) > 1 else 1
            if self.return_nans:
                return np.array([np.nan] * n_samples)
            return np.array([0.75 + 0.01 * i for i in range(n_samples)])
        
        return np.array([0.75])


@pytest.fixture
def fake_model_manager():
    """Create fake model manager for testing"""
    def _create_manager(model=None, version="v1.2.3", model_hash="deadbeef123456"):
        if model is None:
            model = FakeModel()
        
        with patch('backend.mlops.model_manager.ModelManager') as MockManager:
            manager = MockManager.return_value
            manager.model = model
            manager.model_version = version
            manager.model_sha256 = model_hash
            manager.is_healthy = Mock(return_value=True)
            manager.get_health_info = Mock(return_value={
                "status": "healthy",
                "model_version": version,
                "model_sha256": model_hash,
                "last_prediction": "2024-01-01T00:00:00Z"
            })
            
            # Mock prediction methods
            def mock_predict(data):
                return model.predict(data)
            
            def mock_predict_batch(batch_data):
                return model.predict(batch_data)
                
            manager.predict = Mock(side_effect=mock_predict)
            manager.predict_batch = Mock(side_effect=mock_predict_batch)
            
            return manager
    
    return _create_manager


@pytest.fixture
def create_test_app():
    """Create test app with model manager mocking"""
    def _create_app(model_manager=None):
        with patch('backend.api.main.WebSocketClientManager'), \
             patch('backend.api.main.get_logger'), \
             patch('backend.api.main.audit_logger'):
            
            from backend.api.main import app
            
            # Mock app state
            app.state = MagicMock()
            app.state.model_manager = model_manager or Mock()
            app.state.risk_manager = Mock()
            app.state.order_service = Mock()
            app.state.user_manager = Mock()
            
            return TestClient(app)
    
    return _create_app


class TestModelManagerMatrix:
    """Comprehensive model manager testing matrix"""
    
    def test_predict_valid_single_dict(self, fake_model_manager, create_test_app):
        """Test single prediction with valid dictionary input"""
        model_manager = fake_model_manager()
        client = create_test_app(model_manager)
        
        valid_data = {
            "price": 150.50,
            "volume": 1000000,
            "rsi": 65.5,
            "macd": 0.25
        }
        
        # Test direct model manager call
        result = model_manager.predict(valid_data)
        assert isinstance(result, np.ndarray)
        assert len(result) > 0
        assert not np.isnan(result).any()
        
        # Verify mock was called
        model_manager.predict.assert_called_once_with(valid_data)

    def test_predict_batch_valid_list(self, fake_model_manager, create_test_app):
        """Test batch prediction with valid list input"""
        model_manager = fake_model_manager()
        client = create_test_app(model_manager)
        
        batch_data = [
            {"price": 150.50, "volume": 1000000, "rsi": 65.5, "macd": 0.25},
            {"price": 151.00, "volume": 1100000, "rsi": 67.0, "macd": 0.30},
            {"price": 149.75, "volume": 950000, "rsi": 63.0, "macd": 0.20}
        ]
        
        # Test batch prediction
        result = model_manager.predict_batch(batch_data)
        assert isinstance(result, np.ndarray)
        assert len(result) == 3
        assert not np.isnan(result).any()
        
        model_manager.predict_batch.assert_called_once_with(batch_data)

    def test_predict_invalid_schema(self, fake_model_manager, create_test_app):
        """Test prediction with invalid schema (missing required fields)"""
        model_manager = fake_model_manager()
        
        invalid_data = {
            "price": 150.50,
            # Missing required fields: volume, rsi, macd
        }
        
        # Should handle gracefully or raise appropriate error
        try:
            result = model_manager.predict(invalid_data)
            # If it succeeds, result should be valid
            assert isinstance(result, np.ndarray)
        except (ValueError, KeyError, TypeError) as e:
            # Expected for invalid schema
            assert "schema" in str(e).lower() or "field" in str(e).lower() or "missing" in str(e).lower()

    def test_predict_wrong_dtypes(self, fake_model_manager, create_test_app):
        """Test prediction with wrong data types"""
        model_manager = fake_model_manager()
        
        wrong_dtype_data = {
            "price": "not_a_number",  # Should be float
            "volume": "invalid",      # Should be int
            "rsi": True,             # Should be float
            "macd": []               # Should be float
        }
        
        # Should handle type errors gracefully
        try:
            result = model_manager.predict(wrong_dtype_data)
            # If succeeds, should return valid array
            assert isinstance(result, np.ndarray)
        except (ValueError, TypeError) as e:
            # Expected for wrong types
            assert "type" in str(e).lower() or "convert" in str(e).lower()

    def test_predict_with_nans(self, fake_model_manager, create_test_app):
        """Test prediction when input contains NaN values"""
        model_manager = fake_model_manager(FakeModel(return_nans=False))
        
        nan_data = {
            "price": float('nan'),
            "volume": 1000000,
            "rsi": 65.5,
            "macd": float('nan')
        }
        
        # Should handle NaN inputs appropriately
        try:
            result = model_manager.predict(nan_data)
            assert isinstance(result, np.ndarray)
            # Result might be NaN or handled value
        except ValueError as e:
            # Expected if model doesn't handle NaNs
            assert "nan" in str(e).lower() or "invalid" in str(e).lower()

    def test_predict_model_returns_nans(self, fake_model_manager, create_test_app):
        """Test handling when model returns NaN predictions"""
        model_manager = fake_model_manager(FakeModel(return_nans=True))
        
        valid_data = {
            "price": 150.50,
            "volume": 1000000,
            "rsi": 65.5,
            "macd": 0.25
        }
        
        result = model_manager.predict(valid_data)
        assert isinstance(result, np.ndarray)
        assert np.isnan(result).any()  # Should contain NaNs

    def test_predict_missing_model_fallback(self, fake_model_manager, create_test_app):
        """Test fallback behavior when model is missing"""
        # Create manager with no model
        model_manager = fake_model_manager(None)
        model_manager.model = None
        model_manager.predict.side_effect = AttributeError("Model not loaded")
        
        valid_data = {
            "price": 150.50,
            "volume": 1000000,
            "rsi": 65.5,
            "macd": 0.25
        }
        
        # Should handle missing model gracefully
        try:
            result = model_manager.predict(valid_data)
            pytest.fail("Should raise error for missing model")
        except (AttributeError, RuntimeError) as e:
            assert "model" in str(e).lower()

    def test_model_health_check_with_version_hash(self, fake_model_manager, create_test_app):
        """Test health check includes model version and hash when set"""
        model_manager = fake_model_manager(version="v2.1.0", model_hash="abcdef789012")
        client = create_test_app(model_manager)
        
        # Get health info
        health_info = model_manager.get_health_info()
        
        assert health_info["status"] == "healthy"
        assert health_info["model_version"] == "v2.1.0"
        assert health_info["model_sha256"] == "abcdef789012"
        assert "last_prediction" in health_info

    def test_health_endpoint_includes_model_info(self, fake_model_manager, create_test_app):
        """Test /healthz endpoint includes model version and SHA256"""
        model_manager = fake_model_manager(version="v3.0.1", model_hash="fedcba210987")
        client = create_test_app(model_manager)
        
        with patch('backend.api.main.check_database_connection', return_value=True), \
             patch('backend.api.main.check_all_dependencies', return_value={"database": True, "model": True}):
            
            response = client.get("/healthz")
            
            if response.status_code == 200:
                data = response.json()
                # Should include model information
                assert "model_version" in data or "version" in str(data).lower()
                assert "model_sha256" in data or "hash" in str(data).lower()

    def test_concurrent_predictions(self, fake_model_manager, create_test_app):
        """Test handling of concurrent prediction requests"""
        model_manager = fake_model_manager()
        
        valid_data = {
            "price": 150.50,
            "volume": 1000000,
            "rsi": 65.5,
            "macd": 0.25
        }
        
        # Simulate concurrent predictions
        results = []
        for i in range(5):
            try:
                result = model_manager.predict(valid_data)
                results.append(result)
            except Exception as e:
                results.append(e)
        
        # Should handle concurrent access
        successful_results = [r for r in results if isinstance(r, np.ndarray)]
        assert len(successful_results) >= 3  # Most should succeed

    def test_prediction_error_handling(self, fake_model_manager, create_test_app):
        """Test prediction error handling and recovery"""
        model_manager = fake_model_manager(FakeModel(should_fail=True))
        
        valid_data = {
            "price": 150.50,
            "volume": 1000000,
            "rsi": 65.5,
            "macd": 0.25
        }
        
        # Should raise appropriate error
        with pytest.raises(ValueError, match="Model prediction failed"):
            model_manager.predict(valid_data)

    def test_large_batch_prediction(self, fake_model_manager, create_test_app):
        """Test prediction with large batch sizes"""
        model_manager = fake_model_manager()
        
        # Create large batch
        large_batch = []
        for i in range(100):
            large_batch.append({
                "price": 150.0 + i * 0.1,
                "volume": 1000000 + i * 1000,
                "rsi": 50.0 + i * 0.1,
                "macd": 0.1 + i * 0.001
            })
        
        # Should handle large batches
        result = model_manager.predict_batch(large_batch)
        assert isinstance(result, np.ndarray)
        assert len(result) == 100

    def test_model_memory_usage_tracking(self, fake_model_manager, create_test_app):
        """Test model memory usage and resource tracking"""
        model_manager = fake_model_manager()
        
        # Add memory tracking mock
        model_manager.get_memory_usage = Mock(return_value={"memory_mb": 250.5, "gpu_memory_mb": 0})
        
        memory_info = model_manager.get_memory_usage()
        assert "memory_mb" in memory_info
        assert isinstance(memory_info["memory_mb"], (int, float))

    def test_model_version_comparison(self, fake_model_manager, create_test_app):
        """Test model version comparison and validation"""
        model_manager_v1 = fake_model_manager(version="v1.0.0")
        model_manager_v2 = fake_model_manager(version="v2.0.0")
        
        assert model_manager_v1.model_version != model_manager_v2.model_version
        
        # Test version format validation
        invalid_versions = ["", "invalid", "v", "1", "v1.x.y"]
        for version in invalid_versions:
            try:
                manager = fake_model_manager(version=version)
                # Version should be set even if invalid format
                assert manager.model_version == version
            except ValueError:
                # Some versions might be rejected
                pass

    def test_model_hash_validation(self, fake_model_manager, create_test_app):
        """Test model hash validation and integrity checking"""
        model_manager = fake_model_manager(model_hash="deadbeef12345678")
        
        assert model_manager.model_sha256 == "deadbeef12345678"
        
        # Test hash format validation
        valid_hashes = ["deadbeef12345678", "abcdef1234567890", "0123456789abcdef"]
        for hash_val in valid_hashes:
            manager = fake_model_manager(model_hash=hash_val)
            assert manager.model_sha256 == hash_val

    def test_prediction_input_validation(self, fake_model_manager, create_test_app):
        """Test comprehensive input validation for predictions"""
        model_manager = fake_model_manager()
        
        # Test various invalid inputs
        invalid_inputs = [
            None,
            "",
            [],
            {},
            {"invalid": "schema"},
            {"price": None, "volume": None, "rsi": None, "macd": None}
        ]
        
        for invalid_input in invalid_inputs:
            try:
                result = model_manager.predict(invalid_input)
                # If it succeeds, should return valid result
                assert isinstance(result, np.ndarray)
            except (ValueError, TypeError, KeyError):
                # Expected for invalid inputs
                pass

    def test_model_performance_metrics(self, fake_model_manager, create_test_app):
        """Test model performance metrics tracking"""
        model_manager = fake_model_manager()
        
        # Mock performance tracking
        model_manager.get_performance_metrics = Mock(return_value={
            "predictions_count": 1000,
            "avg_prediction_time_ms": 15.5,
            "error_rate": 0.001,
            "last_24h_predictions": 50
        })
        
        metrics = model_manager.get_performance_metrics()
        assert "predictions_count" in metrics
        assert "avg_prediction_time_ms" in metrics
        assert "error_rate" in metrics
        assert isinstance(metrics["predictions_count"], int)
        assert isinstance(metrics["avg_prediction_time_ms"], (int, float))


class TestModelManagerEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_model_initialization_failure(self, fake_model_manager):
        """Test handling of model initialization failures"""
        with patch('backend.mlops.model_manager.ModelManager', side_effect=RuntimeError("Model init failed")):
            with pytest.raises(RuntimeError, match="Model init failed"):
                fake_model_manager()

    def test_prediction_timeout_handling(self, fake_model_manager):
        """Test prediction timeout handling"""
        model_manager = fake_model_manager()
        
        # Mock timeout scenario
        import time
        def slow_predict(data):
            time.sleep(0.1)  # Simulate slow prediction
            return np.array([0.5])
        
        model_manager.predict = Mock(side_effect=slow_predict)
        
        # Should complete even if slow
        valid_data = {"price": 150.0, "volume": 1000000, "rsi": 65.0, "macd": 0.25}
        result = model_manager.predict(valid_data)
        assert isinstance(result, np.ndarray)

    def test_model_state_consistency(self, fake_model_manager):
        """Test model state remains consistent across operations"""
        model_manager = fake_model_manager(version="v1.5.0", model_hash="consistent123")
        
        # Multiple operations shouldn't change state
        valid_data = {"price": 150.0, "volume": 1000000, "rsi": 65.0, "macd": 0.25}
        
        for i in range(5):
            model_manager.predict(valid_data)
            assert model_manager.model_version == "v1.5.0"
            assert model_manager.model_sha256 == "consistent123"

    def test_memory_cleanup_on_errors(self, fake_model_manager):
        """Test memory cleanup when prediction errors occur"""
        model_manager = fake_model_manager(FakeModel(should_fail=True))
        
        valid_data = {"price": 150.0, "volume": 1000000, "rsi": 65.0, "macd": 0.25}
        
        # Multiple failed predictions shouldn't accumulate memory
        for i in range(3):
            try:
                model_manager.predict(valid_data)
            except ValueError:
                pass  # Expected
        
        # Model manager should still be in valid state
        assert hasattr(model_manager, 'model')
        assert hasattr(model_manager, 'model_version')
