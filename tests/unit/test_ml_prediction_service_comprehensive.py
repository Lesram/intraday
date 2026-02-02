"""
Comprehensive tests for backend.ml.prediction_service module.
Target: 294 missing statements -> high coverage
"""
import os
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest
import numpy as np
import pandas as pd

# Set mock ML environment to enable test models
os.environ["ALLOW_MOCK_ML"] = "1"

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
    timeout_handler,
    create_sample_classification_data,
    create_sample_regression_data,
    create_sample_prediction_requests,
)


# =============================================================================
# Enum Tests
# =============================================================================

class TestPredictionStatus:
    """Test PredictionStatus enum."""

    def test_all_values(self):
        """Test all status values."""
        assert PredictionStatus.PENDING.value == "pending"
        assert PredictionStatus.PROCESSING.value == "processing"
        assert PredictionStatus.COMPLETED.value == "completed"
        assert PredictionStatus.FAILED.value == "failed"
        assert PredictionStatus.CACHED.value == "cached"


class TestPredictionType:
    """Test PredictionType enum."""

    def test_all_values(self):
        """Test all prediction type values."""
        assert PredictionType.CLASSIFICATION.value == "classification"
        assert PredictionType.REGRESSION.value == "regression"
        assert PredictionType.FORECAST.value == "forecast"
        assert PredictionType.ANOMALY_DETECTION.value == "anomaly_detection"


# =============================================================================
# Data Class Tests
# =============================================================================

class TestPredictionRequest:
    """Test PredictionRequest dataclass."""

    def test_creation_minimal(self):
        """Test minimal creation."""
        request = PredictionRequest(
            request_id="req_001",
            input_data={"feature_1": 1.0},
            model_name="classifier"
        )
        
        assert request.request_id == "req_001"
        assert request.model_name == "classifier"
        assert request.model_version == "latest"
        assert request.confidence_threshold == 0.5
        assert request.metadata == {}

    def test_creation_full(self):
        """Test full creation."""
        request = PredictionRequest(
            request_id="req_002",
            input_data=np.array([[1, 2, 3]]),
            model_name="regressor",
            model_version="2.0",
            prediction_type=PredictionType.REGRESSION,
            confidence_threshold=0.8,
            return_probabilities=True,
            cache_enabled=False,
            timeout=10.0,
            metadata={"user_id": "user_123"}
        )
        
        assert request.model_version == "2.0"
        assert request.prediction_type == PredictionType.REGRESSION
        assert request.timeout == 10.0
        assert request.metadata["user_id"] == "user_123"


class TestPredictionResult:
    """Test PredictionResult dataclass."""

    def test_creation_minimal(self):
        """Test minimal creation."""
        result = PredictionResult(
            request_id="req_001",
            predictions=[1, 0, 1]
        )
        
        assert result.request_id == "req_001"
        assert result.status == PredictionStatus.COMPLETED
        assert result.timestamp is not None
        assert result.metadata == {}

    def test_creation_full(self):
        """Test full creation."""
        result = PredictionResult(
            request_id="req_002",
            predictions=[0.5, 0.7, 0.3],
            confidence=[0.9, 0.85, 0.95],
            probabilities=[[0.3, 0.7], [0.2, 0.8], [0.6, 0.4]],
            status=PredictionStatus.COMPLETED,
            processing_time=0.5,
            model_name="classifier",
            model_version="1.0",
            timestamp=datetime.now(),
            error_message=None,
            metadata={"batch_id": "batch_1"}
        )
        
        assert result.confidence is not None
        assert result.processing_time == 0.5


class TestBatchPredictionJob:
    """Test BatchPredictionJob dataclass."""

    def test_creation(self):
        """Test batch job creation."""
        requests = [
            PredictionRequest(
                request_id=f"req_{i}",
                input_data={"x": i},
                model_name="model"
            )
            for i in range(3)
        ]
        
        job = BatchPredictionJob(
            job_id="job_001",
            requests=requests
        )
        
        assert job.job_id == "job_001"
        assert job.total_requests == 3
        assert job.status == PredictionStatus.PENDING
        assert job.progress == 0.0
        assert job.results == []


# =============================================================================
# PredictionCache Tests
# =============================================================================

class TestPredictionCache:
    """Test PredictionCache class."""

    @pytest.fixture
    def cache(self):
        """Create cache instance."""
        return PredictionCache(max_size=100, ttl_hours=1)

    @pytest.fixture
    def sample_request(self):
        """Create sample request."""
        return PredictionRequest(
            request_id="req_001",
            input_data={"feature_1": 1.0, "feature_2": 2.0},
            model_name="classifier",
            model_version="1.0"
        )

    @pytest.fixture
    def sample_result(self):
        """Create sample result."""
        return PredictionResult(
            request_id="req_001",
            predictions=[1],
            confidence=[0.9],
            status=PredictionStatus.COMPLETED
        )

    def test_put_and_get(self, cache, sample_request, sample_result):
        """Test storing and retrieving from cache."""
        cache.put(sample_request, sample_result)
        
        retrieved = cache.get(sample_request)
        
        assert retrieved is not None
        assert retrieved.predictions == [1]
        assert retrieved.status == PredictionStatus.CACHED

    def test_cache_disabled(self, cache, sample_result):
        """Test cache disabled on request."""
        request = PredictionRequest(
            request_id="req_001",
            input_data={"x": 1},
            model_name="model",
            cache_enabled=False
        )
        
        cache.put(request, sample_result)
        retrieved = cache.get(request)
        
        assert retrieved is None

    def test_cache_miss(self, cache):
        """Test cache miss for unknown request."""
        request = PredictionRequest(
            request_id="req_new",
            input_data={"x": 100},
            model_name="unknown"
        )
        
        result = cache.get(request)
        
        assert result is None

    def test_cache_eviction_lru(self, cache):
        """Test LRU eviction when cache is full."""
        small_cache = PredictionCache(max_size=2, ttl_hours=1)
        
        for i in range(3):
            request = PredictionRequest(
                request_id=f"req_{i}",
                input_data={"x": i},
                model_name="model"
            )
            result = PredictionResult(
                request_id=f"req_{i}",
                predictions=[i]
            )
            small_cache.put(request, result)
        
        # Cache should have evicted first entry
        assert len(small_cache.cache) <= 2

    def test_clear(self, cache, sample_request, sample_result):
        """Test clearing cache."""
        cache.put(sample_request, sample_result)
        cache.clear()
        
        assert cache.get(sample_request) is None
        assert len(cache.cache) == 0

    def test_get_stats(self, cache, sample_request, sample_result):
        """Test getting cache statistics."""
        cache.put(sample_request, sample_result)
        
        stats = cache.get_stats()
        
        assert 'total_entries' in stats
        assert 'max_size' in stats
        assert stats['total_entries'] >= 1

    def test_serialize_input_dataframe(self, cache):
        """Test serializing DataFrame input."""
        df = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})
        serialized = cache._serialize_input(df)
        
        assert isinstance(serialized, str)

    def test_serialize_input_numpy(self, cache):
        """Test serializing numpy array input."""
        arr = np.array([1, 2, 3])
        serialized = cache._serialize_input(arr)
        
        assert isinstance(serialized, str)
        assert "[1, 2, 3]" in serialized

    def test_serialize_input_dict(self, cache):
        """Test serializing dict input."""
        data = {"a": 1, "b": 2}
        serialized = cache._serialize_input(data)
        
        assert isinstance(serialized, str)


# =============================================================================
# PredictionValidator Tests
# =============================================================================

class TestPredictionValidator:
    """Test PredictionValidator class."""

    def test_validate_input_none(self):
        """Test validation rejects None input."""
        is_valid, msg = PredictionValidator.validate_input(None)
        
        assert not is_valid
        assert "None" in msg

    def test_validate_input_empty_dataframe(self):
        """Test validation rejects empty DataFrame."""
        df = pd.DataFrame()
        
        is_valid, msg = PredictionValidator.validate_input(df)
        
        assert not is_valid
        assert "empty" in msg.lower()

    def test_validate_input_dataframe_with_nan(self):
        """Test validation rejects DataFrame with NaN."""
        df = pd.DataFrame({'a': [1, np.nan], 'b': [3, 4]})
        
        is_valid, msg = PredictionValidator.validate_input(df)
        
        assert not is_valid
        assert "NaN" in msg

    def test_validate_input_valid_dataframe(self):
        """Test validation accepts valid DataFrame."""
        df = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})
        
        is_valid, msg = PredictionValidator.validate_input(df)
        
        assert is_valid

    def test_validate_input_missing_features(self):
        """Test validation detects missing features."""
        df = pd.DataFrame({'a': [1, 2]})
        expected = ['a', 'b', 'c']
        
        is_valid, msg = PredictionValidator.validate_input(df, expected)
        
        assert not is_valid
        assert "Missing" in msg

    def test_validate_input_empty_array(self):
        """Test validation rejects empty array."""
        arr = np.array([])
        
        is_valid, msg = PredictionValidator.validate_input(arr)
        
        assert not is_valid

    def test_validate_input_array_with_inf(self):
        """Test validation rejects array with inf."""
        arr = np.array([1, np.inf, 3])
        
        is_valid, msg = PredictionValidator.validate_input(arr)
        
        assert not is_valid

    def test_validate_input_empty_list(self):
        """Test validation rejects empty list."""
        is_valid, msg = PredictionValidator.validate_input([])
        
        assert not is_valid

    def test_validate_prediction_none(self):
        """Test prediction validation rejects None."""
        is_valid, msg = PredictionValidator.validate_prediction(
            None, PredictionType.CLASSIFICATION
        )
        
        assert not is_valid

    def test_validate_prediction_empty_array(self):
        """Test prediction validation rejects empty array."""
        is_valid, msg = PredictionValidator.validate_prediction(
            [], PredictionType.CLASSIFICATION
        )
        
        assert not is_valid

    def test_validate_prediction_valid_classification(self):
        """Test prediction validation accepts valid classification."""
        is_valid, msg = PredictionValidator.validate_prediction(
            [0, 1, 1], PredictionType.CLASSIFICATION
        )
        
        assert is_valid

    def test_validate_prediction_regression_with_nan(self):
        """Test prediction validation rejects regression with NaN."""
        is_valid, msg = PredictionValidator.validate_prediction(
            np.array([1.0, np.nan, 3.0]), PredictionType.REGRESSION
        )
        
        assert not is_valid


# =============================================================================
# PredictionLogger Tests
# =============================================================================

class TestPredictionLogger:
    """Test PredictionLogger class."""

    @pytest.fixture
    def logger(self, tmp_path):
        """Create logger with temp file."""
        log_file = tmp_path / "test_predictions.log"
        return PredictionLogger(str(log_file))

    def test_log_prediction_request(self, logger):
        """Test logging prediction request."""
        request = PredictionRequest(
            request_id="req_001",
            input_data={"x": 1},
            model_name="model"
        )
        
        # Should not raise
        logger.log_prediction_request(request)

    def test_log_prediction_result(self, logger):
        """Test logging prediction result."""
        result = PredictionResult(
            request_id="req_001",
            predictions=[1],
            processing_time=0.5
        )
        
        # Should not raise
        logger.log_prediction_result(result)

    def test_log_error(self, logger):
        """Test logging error."""
        # Should not raise
        logger.log_error("req_001", "Test error message")

    def test_log_batch_job(self, logger):
        """Test logging batch job."""
        job = BatchPredictionJob(
            job_id="job_001",
            requests=[]
        )
        
        # Should not raise
        logger.log_batch_job(job)


# =============================================================================
# timeout_handler Tests
# =============================================================================

class TestTimeoutHandler:
    """Test timeout_handler decorator."""

    def test_function_completes_in_time(self):
        """Test function that completes before timeout."""
        @timeout_handler(5.0)
        def fast_function():
            return "success"
        
        result = fast_function()
        
        assert result == "success"


# =============================================================================
# PredictionService Tests
# =============================================================================

class TestPredictionService:
    """Test PredictionService class."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create prediction service."""
        log_file = tmp_path / "predictions.log"
        return PredictionService(
            cache_size=100,
            cache_ttl_hours=1,
            max_workers=2,
            log_file=str(log_file)
        )

    def test_init(self, service):
        """Test service initialization."""
        assert service.cache is not None
        assert service.validator is not None
        assert len(service.models) > 0  # Mock models set up

    def test_predict_classification(self, service):
        """Test classification prediction."""
        request = PredictionRequest(
            request_id="req_001",
            input_data=pd.DataFrame({'feature_1': [1.0], 'feature_2': [2.0], 'feature_3': [3.0]}),
            model_name="classifier",
            model_version="1.0",
            prediction_type=PredictionType.CLASSIFICATION
        )
        
        result = service.predict(request)
        
        assert result.status == PredictionStatus.COMPLETED
        assert len(result.predictions) > 0

    def test_predict_regression(self, service):
        """Test regression prediction."""
        request = PredictionRequest(
            request_id="req_002",
            input_data=pd.DataFrame({'feature_1': [1.0], 'feature_2': [2.0]}),
            model_name="regressor",
            model_version="1.0",
            prediction_type=PredictionType.REGRESSION
        )
        
        result = service.predict(request)
        
        assert result.status == PredictionStatus.COMPLETED

    def test_predict_with_probabilities(self, service):
        """Test prediction with probabilities."""
        request = PredictionRequest(
            request_id="req_003",
            input_data=pd.DataFrame({'feature_1': [1.0], 'feature_2': [2.0], 'feature_3': [3.0]}),
            model_name="classifier",
            model_version="1.0",
            return_probabilities=True
        )
        
        result = service.predict(request)
        
        assert result.status == PredictionStatus.COMPLETED
        assert result.probabilities is not None

    def test_predict_model_not_found(self, service):
        """Test prediction with non-existent model."""
        request = PredictionRequest(
            request_id="req_004",
            input_data={"x": 1},
            model_name="nonexistent_model",
            model_version="99.0"
        )
        
        result = service.predict(request)
        
        assert result.status == PredictionStatus.FAILED
        assert "not found" in result.error_message

    def test_predict_invalid_input(self, service):
        """Test prediction with invalid input."""
        request = PredictionRequest(
            request_id="req_005",
            input_data=pd.DataFrame(),  # Empty DataFrame
            model_name="classifier",
            model_version="1.0"
        )
        
        result = service.predict(request)
        
        assert result.status == PredictionStatus.FAILED

    def test_predict_caching(self, service):
        """Test prediction caching."""
        data = pd.DataFrame({'feature_1': [1.0], 'feature_2': [2.0], 'feature_3': [3.0]})
        request = PredictionRequest(
            request_id="req_006",
            input_data=data,
            model_name="classifier",
            model_version="1.0",
            cache_enabled=True
        )
        
        # First prediction
        result1 = service.predict(request)
        
        # Second prediction (should be cached)
        request.request_id = "req_007"  # Different request ID
        result2 = service.predict(request)
        
        assert result2.status == PredictionStatus.CACHED

    def test_predict_batch(self, service):
        """Test batch prediction."""
        requests = []
        for i in range(3):
            data = pd.DataFrame({'feature_1': [float(i)], 'feature_2': [float(i+1)], 'feature_3': [float(i+2)]})
            req = PredictionRequest(
                request_id=f"batch_req_{i}",
                input_data=data,
                model_name="classifier",
                model_version="1.0"
            )
            requests.append(req)
        
        job = service.predict_batch(requests)
        
        assert job.status == PredictionStatus.COMPLETED
        assert len(job.results) == 3

    def test_predict_batch_with_job_id(self, service):
        """Test batch prediction with custom job ID."""
        requests = [
            PredictionRequest(
                request_id="req_1",
                input_data=pd.DataFrame({'feature_1': [1.0], 'feature_2': [2.0], 'feature_3': [3.0]}),
                model_name="classifier",
                model_version="1.0"
            )
        ]
        
        job = service.predict_batch(requests, job_id="custom_job_123")
        
        assert job.job_id == "custom_job_123"

    def test_get_batch_job_status(self, service):
        """Test getting batch job status."""
        requests = [
            PredictionRequest(
                request_id="req_1",
                input_data=pd.DataFrame({'feature_1': [1.0], 'feature_2': [2.0], 'feature_3': [3.0]}),
                model_name="classifier",
                model_version="1.0"
            )
        ]
        
        job = service.predict_batch(requests, job_id="status_test")
        
        status = service.get_batch_job_status("status_test")
        
        assert status is not None
        assert status.job_id == "status_test"

    def test_get_batch_job_status_not_found(self, service):
        """Test getting non-existent batch job."""
        status = service.get_batch_job_status("nonexistent")
        
        assert status is None

    def test_predict_realtime(self, service):
        """Test real-time prediction."""
        data = pd.DataFrame({'feature_1': [1.0], 'feature_2': [2.0], 'feature_3': [3.0]})
        
        result = service.predict_realtime(
            data,
            model_name="classifier",
            model_version="1.0",
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
        # Make a prediction to populate cache
        request = PredictionRequest(
            request_id="cache_test",
            input_data=pd.DataFrame({'feature_1': [1.0], 'feature_2': [2.0], 'feature_3': [3.0]}),
            model_name="classifier",
            model_version="1.0"
        )
        service.predict(request)
        
        service.clear_cache()
        
        stats = service.get_cache_stats()
        assert stats['total_entries'] == 0

    def test_get_service_stats(self, service):
        """Test getting service statistics."""
        stats = service.get_service_stats()
        
        assert 'total_batch_jobs' in stats
        assert 'available_models' in stats
        assert 'cache_stats' in stats

    def test_get_model_latest_version(self, service):
        """Test getting latest model version."""
        model = service._get_model("classifier", "latest")
        
        assert model is not None


# =============================================================================
# Utility Function Tests
# =============================================================================

class TestUtilityFunctions:
    """Test utility functions."""

    def test_create_sample_classification_data(self):
        """Test creating sample classification data."""
        data = create_sample_classification_data(n_samples=50, n_features=3)
        
        assert isinstance(data, pd.DataFrame)
        assert len(data) == 50
        assert len(data.columns) == 3

    def test_create_sample_regression_data(self):
        """Test creating sample regression data."""
        data = create_sample_regression_data(n_samples=100, n_features=5)
        
        assert isinstance(data, pd.DataFrame)
        assert len(data) == 100
        assert len(data.columns) == 5

    def test_create_sample_prediction_requests(self):
        """Test creating sample prediction requests."""
        requests = create_sample_prediction_requests(n_requests=5)
        
        assert len(requests) == 5
        assert all(isinstance(r, PredictionRequest) for r in requests)


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create prediction service."""
        log_file = tmp_path / "predictions.log"
        return PredictionService(log_file=str(log_file))

    def test_predict_with_numpy_array(self, service):
        """Test prediction with numpy array input."""
        request = PredictionRequest(
            request_id="numpy_test",
            input_data=np.array([[1.0, 2.0, 3.0]]),
            model_name="classifier",
            model_version="1.0"
        )
        
        result = service.predict(request)
        
        # Should complete or fail gracefully
        assert result.status in [PredictionStatus.COMPLETED, PredictionStatus.FAILED]

    def test_predict_with_list_input(self, service):
        """Test prediction with list input."""
        request = PredictionRequest(
            request_id="list_test",
            input_data=[[1.0, 2.0, 3.0]],
            model_name="classifier",
            model_version="1.0"
        )
        
        result = service.predict(request)
        
        assert result.status in [PredictionStatus.COMPLETED, PredictionStatus.FAILED]

    def test_batch_with_failing_requests(self, service):
        """Test batch prediction with some failing requests."""
        requests = [
            PredictionRequest(
                request_id="good_req",
                input_data=pd.DataFrame({'feature_1': [1.0], 'feature_2': [2.0], 'feature_3': [3.0]}),
                model_name="classifier",
                model_version="1.0"
            ),
            PredictionRequest(
                request_id="bad_req",
                input_data={"x": 1},  # Will fail validation
                model_name="nonexistent",
                model_version="99.0"
            )
        ]
        
        job = service.predict_batch(requests)
        
        assert job.status == PredictionStatus.COMPLETED
        assert job.completed_requests + job.failed_requests == 2

# =============================================================================
# Additional Coverage Tests for 100%
# =============================================================================

class TestPredictionCacheExtended:
    """Extended tests for PredictionCache."""

    def test_cache_evict_lru(self):
        """Test LRU eviction when cache is full."""
        cache = PredictionCache(max_size=2, ttl_hours=1)
        
        # Create 3 requests that will exceed max_size
        req1 = PredictionRequest(
            request_id="req1",
            input_data=pd.DataFrame({'f1': [1.0]}),
            model_name="model1",
            model_version="1.0",
            cache_enabled=True
        )
        res1 = PredictionResult(
            request_id="req1",
            predictions=[0.5],
            status=PredictionStatus.COMPLETED,
            model_name="model1",
            model_version="1.0"
        )
        
        req2 = PredictionRequest(
            request_id="req2",
            input_data=pd.DataFrame({'f1': [2.0]}),
            model_name="model2",
            model_version="1.0",
            cache_enabled=True
        )
        res2 = PredictionResult(
            request_id="req2",
            predictions=[0.6],
            status=PredictionStatus.COMPLETED,
            model_name="model2",
            model_version="1.0"
        )
        
        req3 = PredictionRequest(
            request_id="req3",
            input_data=pd.DataFrame({'f1': [3.0]}),
            model_name="model3",
            model_version="1.0",
            cache_enabled=True
        )
        res3 = PredictionResult(
            request_id="req3",
            predictions=[0.7],
            status=PredictionStatus.COMPLETED,
            model_name="model3",
            model_version="1.0"
        )
        
        # Add entries
        cache.put(req1, res1)
        cache.put(req2, res2)
        cache.put(req3, res3)  # Should evict req1 (oldest)
        
        # req1 should be evicted
        assert cache.get(req1) is None
        # req2 and req3 should still be there
        assert cache.get(req2) is not None or cache.get(req3) is not None

    def test_cache_key_generation_fallback(self):
        """Test cache key generation fallback for unusual types."""
        cache = PredictionCache()
        
        class UnserializableObject:
            pass
        
        key = cache._generate_cache_key(PredictionRequest(
            request_id="test",
            input_data=UnserializableObject(),
            model_name="model",
            model_version="1.0"
        ))
        
        # Should not raise and return a string
        assert isinstance(key, str)

    def test_cache_expired_entry_removal(self):
        """Test expired entries are removed on access."""
        cache = PredictionCache(ttl_hours=0)  # Immediate expiry
        
        req = PredictionRequest(
            request_id="expire_test",
            input_data=pd.DataFrame({'f1': [1.0]}),
            model_name="model",
            model_version="1.0",
            cache_enabled=True
        )
        res = PredictionResult(
            request_id="expire_test",
            predictions=[0.5],
            status=PredictionStatus.COMPLETED,
            model_name="model",
            model_version="1.0"
        )
        
        cache.put(req, res)
        
        # With 0 TTL, entry should be expired
        import time
        time.sleep(0.01)  # Small delay to ensure expiry
        
        # Get should return None for expired entry
        result = cache.get(req)
        assert result is None


class TestBatchPredictionExtended:
    """Extended batch prediction tests."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create prediction service."""
        log_file = tmp_path / "predictions.log"
        return PredictionService(log_file=str(log_file))

    def test_batch_prediction_outer_exception(self, service):
        """Test batch prediction handles outer exceptions."""
        # Create requests that will cause outer exception
        with patch.object(service, 'predict', side_effect=Exception("Outer failure")):
            requests = [
                PredictionRequest(
                    request_id="fail_req",
                    input_data=pd.DataFrame({'f1': [1.0]}),
                    model_name="model",
                    model_version="1.0"
                )
            ]
            
            job = service.predict_batch(requests)
        
        # Job should complete but with failures
        assert job.status in [PredictionStatus.COMPLETED, PredictionStatus.FAILED]

    def test_get_batch_job_nonexistent(self, service):
        """Test getting non-existent batch job."""
        result = service.get_batch_job_status("nonexistent_job_id")
        assert result is None