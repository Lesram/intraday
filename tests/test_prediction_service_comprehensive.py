"""
Comprehensive tests for backend/ml/prediction_service.py

Tests the ML Prediction Service including:
- PredictionStatus and PredictionType enums
- PredictionRequest and PredictionResult dataclasses
- BatchPredictionJob
- PredictionCache (caching, eviction, TTL)
- PredictionValidator (input and output validation)
- PredictionLogger
- PredictionService (single and batch predictions)
- Utility functions
"""

from datetime import datetime, timedelta
import os
from pathlib import Path
import time
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from backend.ml.prediction_service import (
    PredictionStatus,
    PredictionType,
    PredictionRequest,
    PredictionResult,
    BatchPredictionJob,
    PredictionCache,
    PredictionValidator,
    PredictionLogger,
    PredictionService,
    create_sample_classification_data,
    create_sample_regression_data,
    create_sample_prediction_requests,
)


# =============================================================================
# Test Enums
# =============================================================================

class TestPredictionStatusEnum:
    """Tests for PredictionStatus enum."""

    def test_all_statuses(self):
        """Test all prediction statuses are defined."""
        assert PredictionStatus.PENDING.value == "pending"
        assert PredictionStatus.PROCESSING.value == "processing"
        assert PredictionStatus.COMPLETED.value == "completed"
        assert PredictionStatus.FAILED.value == "failed"
        assert PredictionStatus.CACHED.value == "cached"


class TestPredictionTypeEnum:
    """Tests for PredictionType enum."""

    def test_all_types(self):
        """Test all prediction types are defined."""
        assert PredictionType.CLASSIFICATION.value == "classification"
        assert PredictionType.REGRESSION.value == "regression"
        assert PredictionType.FORECAST.value == "forecast"
        assert PredictionType.ANOMALY_DETECTION.value == "anomaly_detection"


# =============================================================================
# Test Dataclasses
# =============================================================================

class TestPredictionRequest:
    """Tests for PredictionRequest dataclass."""

    def test_basic_creation(self):
        """Test basic request creation."""
        request = PredictionRequest(
            request_id="test_001",
            input_data={"feature1": 1.0},
            model_name="test_model"
        )

        assert request.request_id == "test_001"
        assert request.input_data == {"feature1": 1.0}
        assert request.model_name == "test_model"
        assert request.model_version == "latest"
        assert request.prediction_type == PredictionType.CLASSIFICATION
        assert request.confidence_threshold == 0.5
        assert request.return_probabilities is False
        assert request.cache_enabled is True
        assert request.timeout == 30.0
        assert request.metadata == {}

    def test_custom_creation(self):
        """Test request with custom values."""
        request = PredictionRequest(
            request_id="test_002",
            input_data=np.array([1.0, 2.0, 3.0]),
            model_name="regressor",
            model_version="2.0",
            prediction_type=PredictionType.REGRESSION,
            confidence_threshold=0.7,
            return_probabilities=True,
            cache_enabled=False,
            timeout=10.0,
            metadata={"source": "api"}
        )

        assert request.model_version == "2.0"
        assert request.prediction_type == PredictionType.REGRESSION
        assert request.confidence_threshold == 0.7
        assert request.return_probabilities is True
        assert request.cache_enabled is False
        assert request.timeout == 10.0
        assert request.metadata == {"source": "api"}


class TestPredictionResult:
    """Tests for PredictionResult dataclass."""

    def test_basic_creation(self):
        """Test basic result creation."""
        result = PredictionResult(
            request_id="test_001",
            predictions=[1, 0, 1]
        )

        assert result.request_id == "test_001"
        assert result.predictions == [1, 0, 1]
        assert result.confidence is None
        assert result.probabilities is None
        assert result.status == PredictionStatus.COMPLETED
        assert result.processing_time == 0.0
        assert result.model_name == ""
        assert result.model_version == ""
        assert result.timestamp is not None
        assert result.error_message is None
        assert result.metadata == {}

    def test_failed_result(self):
        """Test failed result."""
        result = PredictionResult(
            request_id="test_002",
            predictions=[],
            status=PredictionStatus.FAILED,
            error_message="Model not found"
        )

        assert result.status == PredictionStatus.FAILED
        assert result.error_message == "Model not found"


class TestBatchPredictionJob:
    """Tests for BatchPredictionJob dataclass."""

    def test_creation(self):
        """Test batch job creation."""
        requests = [
            PredictionRequest(request_id=f"req_{i}", input_data={}, model_name="test")
            for i in range(5)
        ]

        job = BatchPredictionJob(
            job_id="batch_001",
            requests=requests
        )

        assert job.job_id == "batch_001"
        assert len(job.requests) == 5
        assert job.status == PredictionStatus.PENDING
        assert job.progress == 0.0
        assert job.total_requests == 5
        assert job.completed_requests == 0
        assert job.failed_requests == 0
        assert job.started_at is None
        assert job.completed_at is None
        assert job.results == []


# =============================================================================
# Test PredictionCache
# =============================================================================

class TestPredictionCache:
    """Tests for PredictionCache class."""

    @pytest.fixture
    def cache(self):
        """Create a prediction cache."""
        return PredictionCache(max_size=100, ttl_hours=24)

    @pytest.fixture
    def sample_request(self):
        """Create a sample prediction request."""
        return PredictionRequest(
            request_id="test_001",
            input_data={"feature1": 1.0, "feature2": 2.0},
            model_name="classifier",
            model_version="1.0"
        )

    @pytest.fixture
    def sample_result(self):
        """Create a sample prediction result."""
        return PredictionResult(
            request_id="test_001",
            predictions=[1],
            confidence=[0.95]
        )

    def test_init(self, cache):
        """Test cache initialization."""
        assert cache.max_size == 100
        assert cache.ttl_hours == 24
        assert cache.cache == {}
        assert cache.access_times == {}

    def test_generate_cache_key(self, cache, sample_request):
        """Test cache key generation."""
        key = cache._generate_cache_key(sample_request)

        assert isinstance(key, str)
        assert len(key) == 32  # MD5 hash length

    def test_generate_cache_key_deterministic(self, cache, sample_request):
        """Test cache key is deterministic."""
        key1 = cache._generate_cache_key(sample_request)
        key2 = cache._generate_cache_key(sample_request)

        assert key1 == key2

    def test_serialize_input_dict(self, cache):
        """Test serializing dict input."""
        result = cache._serialize_input({"a": 1, "b": 2})
        assert isinstance(result, str)

    def test_serialize_input_dataframe(self, cache):
        """Test serializing DataFrame input."""
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        result = cache._serialize_input(df)
        assert isinstance(result, str)

    def test_serialize_input_array(self, cache):
        """Test serializing numpy array input."""
        arr = np.array([1.0, 2.0, 3.0])
        result = cache._serialize_input(arr)
        assert isinstance(result, str)

    def test_put_and_get(self, cache, sample_request, sample_result):
        """Test storing and retrieving from cache."""
        cache.put(sample_request, sample_result)

        retrieved = cache.get(sample_request)

        assert retrieved is not None
        assert retrieved.request_id == sample_result.request_id
        assert retrieved.status == PredictionStatus.CACHED

    def test_get_miss(self, cache, sample_request):
        """Test cache miss."""
        result = cache.get(sample_request)
        assert result is None

    def test_cache_disabled(self, cache, sample_result):
        """Test cache disabled for request."""
        request = PredictionRequest(
            request_id="test",
            input_data={},
            model_name="test",
            cache_enabled=False
        )

        cache.put(request, sample_result)
        result = cache.get(request)

        assert result is None

    def test_is_expired(self, cache):
        """Test expiration check."""
        old_time = datetime.now() - timedelta(hours=25)
        recent_time = datetime.now() - timedelta(hours=1)

        assert cache._is_expired(old_time) is True
        assert cache._is_expired(recent_time) is False

    def test_evict_lru(self, cache):
        """Test LRU eviction."""
        # Fill cache to max
        small_cache = PredictionCache(max_size=3, ttl_hours=24)

        for i in range(3):
            request = PredictionRequest(
                request_id=f"test_{i}",
                input_data={"feature": i},
                model_name="test"
            )
            result = PredictionResult(request_id=f"test_{i}", predictions=[i])
            small_cache.put(request, result)

        # Verify cache is full
        assert len(small_cache.cache) == 3

        # Add another entry (should evict oldest)
        request = PredictionRequest(
            request_id="test_new",
            input_data={"feature": 999},
            model_name="test"
        )
        result = PredictionResult(request_id="test_new", predictions=[999])
        small_cache.put(request, result)

        # Cache should still be at max
        assert len(small_cache.cache) <= 3

    def test_clear(self, cache, sample_request, sample_result):
        """Test clearing cache."""
        cache.put(sample_request, sample_result)
        assert len(cache.cache) > 0

        cache.clear()

        assert len(cache.cache) == 0
        assert len(cache.access_times) == 0

    def test_get_stats(self, cache, sample_request, sample_result):
        """Test getting cache statistics."""
        cache.put(sample_request, sample_result)

        stats = cache.get_stats()

        assert 'total_entries' in stats
        assert 'expired_entries' in stats
        assert 'valid_entries' in stats
        assert 'max_size' in stats
        assert 'ttl_hours' in stats
        assert stats['total_entries'] == 1


# =============================================================================
# Test PredictionValidator
# =============================================================================

class TestPredictionValidator:
    """Tests for PredictionValidator class."""

    def test_validate_input_none(self):
        """Test validation rejects None input."""
        is_valid, message = PredictionValidator.validate_input(None)
        assert is_valid is False
        assert "None" in message

    def test_validate_input_empty_dataframe(self):
        """Test validation rejects empty DataFrame."""
        is_valid, message = PredictionValidator.validate_input(pd.DataFrame())
        assert is_valid is False
        assert "empty" in message.lower()

    def test_validate_input_empty_array(self):
        """Test validation rejects empty array."""
        is_valid, message = PredictionValidator.validate_input(np.array([]))
        assert is_valid is False
        assert "empty" in message.lower()

    def test_validate_input_empty_dict(self):
        """Test validation rejects empty dict."""
        is_valid, message = PredictionValidator.validate_input({})
        assert is_valid is False
        assert "empty" in message.lower()

    def test_validate_input_valid_dataframe(self):
        """Test validation accepts valid DataFrame."""
        df = pd.DataFrame({"feature1": [1.0, 2.0], "feature2": [3.0, 4.0]})
        is_valid, message = PredictionValidator.validate_input(df)
        assert is_valid is True

    def test_validate_input_missing_features(self):
        """Test validation rejects DataFrame with missing features."""
        df = pd.DataFrame({"feature1": [1.0]})
        is_valid, message = PredictionValidator.validate_input(
            df, expected_features=["feature1", "feature2"]
        )
        assert is_valid is False
        assert "Missing features" in message

    def test_validate_input_nan_values(self):
        """Test validation rejects DataFrame with NaN values."""
        df = pd.DataFrame({"feature1": [1.0, np.nan]})
        is_valid, message = PredictionValidator.validate_input(df)
        assert is_valid is False
        assert "NaN" in message or "infinite" in message

    def test_validate_input_inf_values(self):
        """Test validation rejects DataFrame with infinite values."""
        df = pd.DataFrame({"feature1": [1.0, np.inf]})
        is_valid, message = PredictionValidator.validate_input(df)
        assert is_valid is False
        assert "infinite" in message

    def test_validate_input_valid_array(self):
        """Test validation accepts valid numpy array."""
        arr = np.array([1.0, 2.0, 3.0])
        is_valid, message = PredictionValidator.validate_input(arr)
        assert is_valid is True

    def test_validate_input_array_with_nan(self):
        """Test validation rejects array with NaN."""
        arr = np.array([1.0, np.nan, 3.0])
        is_valid, message = PredictionValidator.validate_input(arr)
        assert is_valid is False

    def test_validate_prediction_none(self):
        """Test prediction validation rejects None."""
        is_valid, message = PredictionValidator.validate_prediction(
            None, PredictionType.CLASSIFICATION
        )
        assert is_valid is False

    def test_validate_prediction_empty_array(self):
        """Test prediction validation rejects empty array."""
        is_valid, message = PredictionValidator.validate_prediction(
            [], PredictionType.CLASSIFICATION
        )
        assert is_valid is False
        assert "empty" in message.lower()

    def test_validate_prediction_valid_classification(self):
        """Test prediction validation accepts valid classification."""
        is_valid, message = PredictionValidator.validate_prediction(
            [0, 1, 1, 0], PredictionType.CLASSIFICATION
        )
        assert is_valid is True

    def test_validate_prediction_valid_regression(self):
        """Test prediction validation accepts valid regression."""
        is_valid, message = PredictionValidator.validate_prediction(
            [1.5, 2.3, 3.1], PredictionType.REGRESSION
        )
        assert is_valid is True

    def test_validate_prediction_regression_with_nan(self):
        """Test prediction validation rejects regression with NaN."""
        is_valid, message = PredictionValidator.validate_prediction(
            np.array([1.5, np.nan, 3.1]), PredictionType.REGRESSION
        )
        assert is_valid is False


# =============================================================================
# Test PredictionLogger
# =============================================================================

class TestPredictionLogger:
    """Tests for PredictionLogger class."""

    @pytest.fixture
    def logger(self, tmp_path):
        """Create a prediction logger."""
        log_file = tmp_path / "test_predictions.log"
        return PredictionLogger(str(log_file))

    def test_init(self, logger):
        """Test logger initialization."""
        assert logger.logger is not None

    def test_log_prediction_request(self, logger):
        """Test logging prediction request."""
        request = PredictionRequest(
            request_id="test_001",
            input_data={},
            model_name="classifier",
            model_version="1.0"
        )

        # Should not raise
        logger.log_prediction_request(request)

    def test_log_prediction_result(self, logger):
        """Test logging prediction result."""
        result = PredictionResult(
            request_id="test_001",
            predictions=[1],
            processing_time=0.5
        )

        logger.log_prediction_result(result)

    def test_log_error(self, logger):
        """Test logging error."""
        logger.log_error("test_001", "Test error message")

    def test_log_batch_job(self, logger):
        """Test logging batch job."""
        job = BatchPredictionJob(
            job_id="batch_001",
            requests=[]
        )

        logger.log_batch_job(job)


# =============================================================================
# Test PredictionService
# =============================================================================

class TestPredictionService:
    """Tests for PredictionService class."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create a prediction service with mock models."""
        with patch.dict(os.environ, {"ALLOW_MOCK_ML": "1"}):
            return PredictionService(
                cache_size=100,
                cache_ttl_hours=1,
                max_workers=2,
                log_file=str(tmp_path / "test.log")
            )

    def test_init(self, service):
        """Test service initialization."""
        assert service.cache is not None
        assert service.validator is not None
        assert service.logger is not None
        assert service.max_workers == 2
        assert len(service.models) > 0  # Mock models loaded

    def test_predict_success(self, service):
        """Test successful prediction."""
        request = PredictionRequest(
            request_id="test_001",
            input_data=pd.DataFrame({
                "feature_1": [1.0],
                "feature_2": [2.0],
                "feature_3": [3.0]
            }),
            model_name="classifier",
            model_version="1.0",
            prediction_type=PredictionType.CLASSIFICATION
        )

        result = service.predict(request)

        assert result.status == PredictionStatus.COMPLETED
        assert len(result.predictions) > 0
        assert result.processing_time > 0

    def test_predict_model_not_found(self, service):
        """Test prediction with non-existent model."""
        request = PredictionRequest(
            request_id="test_002",
            input_data={"feature": 1.0},
            model_name="nonexistent_model",
            model_version="1.0"
        )

        result = service.predict(request)

        assert result.status == PredictionStatus.FAILED
        assert "not found" in result.error_message

    def test_predict_invalid_input(self, service):
        """Test prediction with invalid input."""
        request = PredictionRequest(
            request_id="test_003",
            input_data=pd.DataFrame({"feature_1": [np.nan]}),
            model_name="classifier",
            model_version="1.0"
        )

        result = service.predict(request)

        assert result.status == PredictionStatus.FAILED

    def test_predict_cached(self, service):
        """Test prediction caching."""
        request = PredictionRequest(
            request_id="test_004",
            input_data=pd.DataFrame({
                "feature_1": [1.0],
                "feature_2": [2.0],
                "feature_3": [3.0]
            }),
            model_name="classifier",
            model_version="1.0",
            cache_enabled=True
        )

        # First prediction
        result1 = service.predict(request)
        assert result1.status == PredictionStatus.COMPLETED

        # Second prediction should be cached
        request.request_id = "test_004_v2"  # Same data, different request ID
        result2 = service.predict(request)
        assert result2.status == PredictionStatus.CACHED

    def test_predict_regression(self, service):
        """Test regression prediction."""
        request = PredictionRequest(
            request_id="test_005",
            input_data=pd.DataFrame({
                "feature_1": [1.0],
                "feature_2": [2.0]
            }),
            model_name="regressor",
            model_version="1.0",
            prediction_type=PredictionType.REGRESSION
        )

        result = service.predict(request)

        assert result.status == PredictionStatus.COMPLETED
        assert len(result.predictions) > 0

    def test_predict_batch(self, service):
        """Test batch predictions."""
        requests = []
        for i in range(5):
            requests.append(PredictionRequest(
                request_id=f"batch_req_{i}",
                input_data=pd.DataFrame({
                    "feature_1": [float(i)],
                    "feature_2": [float(i + 1)],
                    "feature_3": [float(i + 2)]
                }),
                model_name="classifier",
                model_version="1.0"
            ))

        job = service.predict_batch(requests)

        assert job.status == PredictionStatus.COMPLETED
        assert job.total_requests == 5
        assert job.completed_requests + job.failed_requests == 5
        assert len(job.results) == 5

    def test_get_batch_job_status(self, service):
        """Test getting batch job status."""
        requests = [PredictionRequest(
            request_id="test",
            input_data=pd.DataFrame({"feature_1": [1.0], "feature_2": [2.0], "feature_3": [3.0]}),
            model_name="classifier"
        )]

        job = service.predict_batch(requests, job_id="custom_job_001")

        status = service.get_batch_job_status("custom_job_001")

        assert status is not None
        assert status.job_id == "custom_job_001"

    def test_get_batch_job_status_not_found(self, service):
        """Test getting non-existent batch job status."""
        status = service.get_batch_job_status("nonexistent")
        assert status is None

    def test_predict_realtime(self, service):
        """Test real-time prediction."""
        input_data = pd.DataFrame({
            "feature_1": [1.0],
            "feature_2": [2.0],
            "feature_3": [3.0]
        })

        result = service.predict_realtime(
            input_data=input_data,
            model_name="classifier",
            timeout=5.0
        )

        assert result.status in [PredictionStatus.COMPLETED, PredictionStatus.CACHED]

    def test_get_cache_stats(self, service):
        """Test getting cache statistics."""
        stats = service.get_cache_stats()

        assert 'total_entries' in stats
        assert 'max_size' in stats

    def test_clear_cache(self, service):
        """Test clearing cache."""
        # Add something to cache first
        request = PredictionRequest(
            request_id="test",
            input_data=pd.DataFrame({"feature_1": [1.0], "feature_2": [2.0], "feature_3": [3.0]}),
            model_name="classifier"
        )
        service.predict(request)

        service.clear_cache()

        stats = service.get_cache_stats()
        assert stats['total_entries'] == 0

    def test_get_service_stats(self, service):
        """Test getting service statistics."""
        stats = service.get_service_stats()

        assert 'total_batch_jobs' in stats
        assert 'active_batch_jobs' in stats
        assert 'completed_batch_jobs' in stats
        assert 'failed_batch_jobs' in stats
        assert 'available_models' in stats
        assert 'cache_stats' in stats
        assert 'max_workers' in stats

    def test_get_model_latest_version(self, service):
        """Test getting latest model version."""
        model_info = service._get_model("classifier", "latest")
        assert model_info is not None

    def test_get_model_specific_version(self, service):
        """Test getting specific model version."""
        model_info = service._get_model("classifier", "1.0")
        assert model_info is not None

    def test_get_model_not_found(self, service):
        """Test getting non-existent model."""
        model_info = service._get_model("nonexistent", "1.0")
        assert model_info is None


# =============================================================================
# Test Utility Functions
# =============================================================================

class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_create_sample_classification_data(self):
        """Test creating sample classification data."""
        data = create_sample_classification_data(n_samples=50, n_features=4)

        assert isinstance(data, pd.DataFrame)
        assert len(data) == 50
        assert len(data.columns) == 4
        assert all(f"feature_{i+1}" in data.columns for i in range(4))

    def test_create_sample_regression_data(self):
        """Test creating sample regression data."""
        data = create_sample_regression_data(n_samples=30, n_features=3)

        assert isinstance(data, pd.DataFrame)
        assert len(data) == 30
        assert len(data.columns) == 3

    def test_create_sample_prediction_requests(self):
        """Test creating sample prediction requests."""
        requests = create_sample_prediction_requests(n_requests=5)

        assert len(requests) == 5
        for i, request in enumerate(requests):
            assert isinstance(request, PredictionRequest)
            assert request.request_id == f"request_{i}"
            assert request.model_name == "classifier"


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases for the prediction service."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create a prediction service."""
        with patch.dict(os.environ, {"ALLOW_MOCK_ML": "1"}):
            return PredictionService(
                log_file=str(tmp_path / "test.log")
            )

    def test_predict_with_list_input(self, service):
        """Test prediction with list input."""
        request = PredictionRequest(
            request_id="test",
            input_data=[[1.0, 2.0, 3.0]],
            model_name="classifier",
            model_version="1.0"
        )

        result = service.predict(request)
        assert result.status in [PredictionStatus.COMPLETED, PredictionStatus.FAILED]

    def test_predict_with_dict_input(self, service):
        """Test prediction with dict input."""
        request = PredictionRequest(
            request_id="test",
            input_data={"feature_1": 1.0, "feature_2": 2.0, "feature_3": 3.0},
            model_name="classifier",
            model_version="1.0"
        )

        result = service.predict(request)
        # Dict input might fail validation but shouldn't crash
        assert result is not None

    def test_predict_with_numpy_input(self, service):
        """Test prediction with numpy array input."""
        request = PredictionRequest(
            request_id="test",
            input_data=np.array([[1.0, 2.0, 3.0]]),
            model_name="classifier",
            model_version="1.0"
        )

        result = service.predict(request)
        assert result.status in [PredictionStatus.COMPLETED, PredictionStatus.FAILED]

    def test_batch_prediction_empty_list(self, service):
        """Test batch prediction with empty request list."""
        job = service.predict_batch([])

        assert job.total_requests == 0
        assert job.status == PredictionStatus.COMPLETED

    def test_service_without_mock_models(self, tmp_path):
        """Test service initialization without mock models."""
        with patch.dict(os.environ, {"ALLOW_MOCK_ML": "0"}):
            service = PredictionService(
                log_file=str(tmp_path / "test.log")
            )
            assert len(service.models) == 0

    def test_concurrent_predictions(self, service):
        """Test concurrent predictions."""
        import concurrent.futures

        requests = []
        for i in range(10):
            requests.append(PredictionRequest(
                request_id=f"concurrent_{i}",
                input_data=pd.DataFrame({
                    "feature_1": [float(i)],
                    "feature_2": [float(i + 1)],
                    "feature_3": [float(i + 2)]
                }),
                model_name="classifier"
            ))

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(service.predict, req) for req in requests]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 10
        for result in results:
            assert result is not None
