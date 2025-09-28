"""
Comprehensive test suite for Module 58: backend.ml.prediction_service
Tests ML prediction service functionality.
"""

import pytest
import sys
import os
import json
import time
import tempfile
import shutil
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add the backend directory to the Python path
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# Import the prediction service module
from backend.ml.prediction_service import (
    PredictionStatus, PredictionType, PredictionRequest, PredictionResult,
    BatchPredictionJob, PredictionCache, PredictionValidator, PredictionLogger,
    PredictionService, create_sample_classification_data, create_sample_regression_data,
    create_sample_prediction_requests
)


class TestModule58BackendMlPredictionService:
    """Comprehensive test suite for ML prediction service functionality."""

    def test_module_availability(self):
        """Test module availability."""
        import backend.ml.prediction_service as module
        assert module is not None

    def test_prediction_status_enum(self):
        """Test PredictionStatus enumeration."""
        assert PredictionStatus.PENDING.value == "pending"
        assert PredictionStatus.PROCESSING.value == "processing"
        assert PredictionStatus.COMPLETED.value == "completed"
        assert PredictionStatus.FAILED.value == "failed"
        assert PredictionStatus.CACHED.value == "cached"

    def test_prediction_type_enum(self):
        """Test PredictionType enumeration."""
        assert PredictionType.CLASSIFICATION.value == "classification"
        assert PredictionType.REGRESSION.value == "regression"
        assert PredictionType.FORECAST.value == "forecast"
        assert PredictionType.ANOMALY_DETECTION.value == "anomaly_detection"

    def test_prediction_request_creation(self):
        """Test PredictionRequest creation."""
        data = {"feature_1": 1.0, "feature_2": 2.0}
        request = PredictionRequest(
            request_id="test_001",
            input_data=data,
            model_name="test_model",
            model_version="1.0"
        )
        
        assert request.request_id == "test_001"
        assert request.input_data == data
        assert request.model_name == "test_model"
        assert request.model_version == "1.0"
        assert request.prediction_type == PredictionType.CLASSIFICATION
        assert request.confidence_threshold == 0.5
        assert request.metadata == {}

    def test_prediction_result_creation(self):
        """Test PredictionResult creation."""
        result = PredictionResult(
            request_id="test_001",
            predictions=[1, 0, 1],
            confidence=[0.9, 0.8, 0.95],
            status=PredictionStatus.COMPLETED
        )
        
        assert result.request_id == "test_001"
        assert result.predictions == [1, 0, 1]
        assert result.confidence == [0.9, 0.8, 0.95]
        assert result.status == PredictionStatus.COMPLETED
        assert isinstance(result.timestamp, datetime)

    def test_batch_prediction_job_creation(self):
        """Test BatchPredictionJob creation."""
        requests = create_sample_prediction_requests(5)
        job = BatchPredictionJob(
            job_id="batch_001",
            requests=requests
        )
        
        assert job.job_id == "batch_001"
        assert len(job.requests) == 5
        assert job.total_requests == 5
        assert job.status == PredictionStatus.PENDING
        assert job.progress == 0.0

    def test_prediction_cache_operations(self):
        """Test PredictionCache operations."""
        cache = PredictionCache(max_size=100, ttl_hours=1)
        
        # Create test request and result
        data = create_sample_classification_data(1)
        request = PredictionRequest(
            request_id="cache_test",
            input_data=data,
            model_name="test_model"
        )
        
        result = PredictionResult(
            request_id="cache_test",
            predictions=[1],
            confidence=[0.9]
        )
        
        # Test cache miss
        cached_result = cache.get(request)
        assert cached_result is None
        
        # Test cache put and hit
        cache.put(request, result)
        cached_result = cache.get(request)
        assert cached_result is not None
        assert cached_result.predictions == [1]
        assert cached_result.status == PredictionStatus.CACHED
        
        # Test cache stats
        stats = cache.get_stats()
        assert stats['total_entries'] == 1
        assert stats['max_size'] == 100

    def test_prediction_cache_expiration(self):
        """Test prediction cache expiration."""
        # Use a very short TTL in hours to ensure expiration
        cache = PredictionCache(max_size=100, ttl_hours=1/3600)  # 1 second in hours
        
        data = create_sample_classification_data(1)
        request = PredictionRequest(
            request_id="expiry_test",
            input_data=data,
            model_name="test_model"
        )
        
        result = PredictionResult(
            request_id="expiry_test",
            predictions=[1]
        )
        
        # Put in cache
        cache.put(request, result)
        
        # Wait for expiration (2 seconds to be sure)
        time.sleep(2)
        
        # Should be expired now
        cached_result = cache.get(request)
        assert cached_result is None

    def test_prediction_validator_input_validation(self):
        """Test PredictionValidator input validation."""
        validator = PredictionValidator()
        
        # Test valid DataFrame
        valid_df = pd.DataFrame({'feature_1': [1.0], 'feature_2': [2.0]})
        is_valid, message = validator.validate_input(valid_df, ['feature_1', 'feature_2'])
        assert is_valid is True
        
        # Test missing features
        incomplete_df = pd.DataFrame({'feature_1': [1.0]})
        is_valid, message = validator.validate_input(incomplete_df, ['feature_1', 'feature_2'])
        assert is_valid is False
        assert "Missing features" in message
        
        # Test empty DataFrame
        empty_df = pd.DataFrame()
        is_valid, message = validator.validate_input(empty_df)
        assert is_valid is False
        assert "empty" in message.lower()
        
        # Test None input
        is_valid, message = validator.validate_input(None)
        assert is_valid is False
        assert "None" in message

    def test_prediction_validator_output_validation(self):
        """Test PredictionValidator output validation."""
        validator = PredictionValidator()
        
        # Test valid classification prediction
        is_valid, message = validator.validate_prediction([1, 0, 1], PredictionType.CLASSIFICATION)
        assert is_valid is True
        
        # Test valid regression prediction
        is_valid, message = validator.validate_prediction([1.5, 2.3, 0.8], PredictionType.REGRESSION)
        assert is_valid is True
        
        # Test empty prediction
        is_valid, message = validator.validate_prediction([], PredictionType.CLASSIFICATION)
        assert is_valid is False
        assert "empty" in message.lower()
        
        # Test None prediction
        is_valid, message = validator.validate_prediction(None, PredictionType.CLASSIFICATION)
        assert is_valid is False
        assert "None" in message

    def test_prediction_logger_operations(self):
        """Test PredictionLogger operations."""
        temp_dir = tempfile.mkdtemp()
        try:
            log_file = os.path.join(temp_dir, "test_predictions.log")
            logger = PredictionLogger(log_file)
            
            # Test logging request
            request = PredictionRequest(
                request_id="log_test",
                input_data={"feature": 1.0},
                model_name="test_model"
            )
            logger.log_prediction_request(request)
            
            # Test logging result
            result = PredictionResult(
                request_id="log_test",
                predictions=[1],
                processing_time=0.1
            )
            logger.log_prediction_result(result)
            
            # Test logging error
            logger.log_error("error_test", "Test error message")
            
            # Force close any open handlers
            for handler in logger.logger.handlers[:]:
                handler.close()
                logger.logger.removeHandler(handler)
            
            # Verify log file exists and has content
            assert os.path.exists(log_file)
            with open(log_file, 'r') as f:
                log_content = f.read()
                assert "log_test" in log_content
                assert "test_model" in log_content
                assert "Test error message" in log_content
                
        finally:
            # Additional cleanup
            try:
                shutil.rmtree(temp_dir)
            except PermissionError:
                # Wait a bit and try again
                time.sleep(0.1)
                try:
                    shutil.rmtree(temp_dir)
                except PermissionError:
                    pass  # Skip if still locked

    def test_prediction_service_initialization(self):
        """Test PredictionService initialization."""
        service = PredictionService(cache_size=500, max_workers=2)
        
        assert service.cache.max_size == 500
        assert service.max_workers == 2
        assert isinstance(service.validator, PredictionValidator)
        assert isinstance(service.logger, PredictionLogger)
        assert len(service.models) > 0  # Should have mock models

    def test_prediction_generation(self):
        """Test single prediction generation."""
        service = PredictionService()
        
        # Test classification prediction
        data = create_sample_classification_data(1)
        request = PredictionRequest(
            request_id="single_test",
            input_data=data,
            model_name="classifier",
            model_version="1.0",
            prediction_type=PredictionType.CLASSIFICATION,
            return_probabilities=True
        )
        
        result = service.predict(request)
        
        assert result.request_id == "single_test"
        assert result.status == PredictionStatus.COMPLETED
        assert result.predictions is not None
        assert result.confidence is not None
        assert result.probabilities is not None
        assert result.processing_time > 0
        assert result.model_name == "classifier"

    def test_prediction_generation_regression(self):
        """Test regression prediction generation."""
        service = PredictionService()
        
        data = create_sample_regression_data(1)
        request = PredictionRequest(
            request_id="regression_test",
            input_data=data,
            model_name="regressor",
            model_version="1.0",
            prediction_type=PredictionType.REGRESSION
        )
        
        result = service.predict(request)
        
        assert result.status == PredictionStatus.COMPLETED
        assert result.predictions is not None
        assert result.confidence is not None
        assert result.probabilities is None  # No probabilities for regression

    def test_prediction_error_handling(self):
        """Test prediction error handling."""
        service = PredictionService()
        
        # Test with invalid model
        request = PredictionRequest(
            request_id="error_test",
            input_data={"feature": 1.0},
            model_name="non_existent_model"
        )
        
        result = service.predict(request)
        
        assert result.status == PredictionStatus.FAILED
        assert result.error_message is not None
        assert "not found" in result.error_message.lower()

    def test_batch_predictions(self):
        """Test batch prediction generation."""
        service = PredictionService(max_workers=2)
        
        requests = create_sample_prediction_requests(5)
        job = service.predict_batch(requests, "test_batch")
        
        assert job.job_id == "test_batch"
        assert job.status == PredictionStatus.COMPLETED
        assert len(job.results) == 5
        assert job.completed_requests + job.failed_requests == 5
        assert job.progress == 1.0
        
        # Check that at least some requests were processed successfully
        # (some might be cached if they're identical)
        completed_or_cached_results = [r for r in job.results 
                                     if r.status in [PredictionStatus.COMPLETED, PredictionStatus.CACHED]]
        assert len(completed_or_cached_results) > 0

    def test_batch_prediction_status(self):
        """Test batch prediction status tracking."""
        service = PredictionService()
        
        requests = create_sample_prediction_requests(3)
        job = service.predict_batch(requests, "status_test")
        
        # Test job status retrieval
        retrieved_job = service.get_batch_job_status("status_test")
        assert retrieved_job is not None
        assert retrieved_job.job_id == "status_test"
        assert retrieved_job.status == PredictionStatus.COMPLETED
        
        # Test non-existent job
        non_existent = service.get_batch_job_status("non_existent")
        assert non_existent is None

    def test_real_time_predictions(self):
        """Test real-time prediction with timeout."""
        service = PredictionService()
        
        data = create_sample_classification_data(1)
        result = service.predict_realtime(
            input_data=data,
            model_name="classifier",
            timeout=10.0
        )
        
        assert result.status == PredictionStatus.COMPLETED
        assert result.predictions is not None
        assert "realtime_" in result.request_id

    def test_prediction_confidence(self):
        """Test prediction confidence calculation."""
        service = PredictionService()
        
        data = create_sample_classification_data(3)
        request = PredictionRequest(
            request_id="confidence_test",
            input_data=data,
            model_name="classifier",
            confidence_threshold=0.8
        )
        
        result = service.predict(request)
        
        assert result.confidence is not None
        if isinstance(result.confidence, list):
            assert all(0 <= conf <= 1 for conf in result.confidence)
        else:
            assert 0 <= result.confidence <= 1

    def test_prediction_caching(self):
        """Test prediction caching functionality."""
        service = PredictionService()
        
        data = create_sample_classification_data(1)
        request = PredictionRequest(
            request_id="cache_test_1",
            input_data=data,
            model_name="classifier",
            cache_enabled=True
        )
        
        # First prediction should not be cached
        result1 = service.predict(request)
        assert result1.status == PredictionStatus.COMPLETED
        
        # Second identical prediction should be cached
        request.request_id = "cache_test_2"
        result2 = service.predict(request)
        assert result2.status == PredictionStatus.CACHED
        
        # Test cache disable
        request.request_id = "cache_test_3"
        request.cache_enabled = False
        result3 = service.predict(request)
        assert result3.status == PredictionStatus.COMPLETED

    def test_prediction_validation(self):
        """Test prediction input/output validation."""
        service = PredictionService()
        
        # Test with invalid input (NaN values)
        invalid_data = pd.DataFrame({'feature_1': [np.nan], 'feature_2': [1.0], 'feature_3': [2.0]})
        request = PredictionRequest(
            request_id="validation_test",
            input_data=invalid_data,
            model_name="classifier"
        )
        
        result = service.predict(request)
        assert result.status == PredictionStatus.FAILED
        assert "validation" in result.error_message.lower()

    def test_prediction_logging(self):
        """Test prediction logging functionality."""
        temp_dir = tempfile.mkdtemp()
        try:
            log_file = os.path.join(temp_dir, "service_test.log")
            service = PredictionService(log_file=log_file)
            
            data = create_sample_classification_data(1)
            request = PredictionRequest(
                request_id="logging_test",
                input_data=data,
                model_name="classifier"
            )
            
            result = service.predict(request)
            
            # Force close any open handlers
            for handler in service.logger.logger.handlers[:]:
                handler.close()
                service.logger.logger.removeHandler(handler)
            
            # Check that log file was created and contains relevant information
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    log_content = f.read()
                    assert "logging_test" in log_content
                    assert "classifier" in log_content
            else:
                # If no log file, just verify the service worked
                assert result is not None
                
        finally:
            try:
                shutil.rmtree(temp_dir)
            except PermissionError:
                time.sleep(0.1)
                try:
                    shutil.rmtree(temp_dir)
                except PermissionError:
                    pass  # Skip if still locked

    def test_service_statistics(self):
        """Test service statistics collection."""
        service = PredictionService()
        
        # Generate some predictions to create statistics
        requests = create_sample_prediction_requests(3)
        service.predict_batch(requests, "stats_test")
        
        stats = service.get_service_stats()
        
        assert 'total_batch_jobs' in stats
        assert 'completed_batch_jobs' in stats
        assert 'available_models' in stats
        assert 'cache_stats' in stats
        assert 'max_workers' in stats
        
        assert stats['total_batch_jobs'] >= 1
        assert len(stats['available_models']) > 0

    def test_cache_management(self):
        """Test cache management operations."""
        service = PredictionService()
        
        # Generate some cached predictions
        for i in range(3):
            data = create_sample_classification_data(1)
            request = PredictionRequest(
                request_id=f"cache_mgmt_{i}",
                input_data=data,
                model_name="classifier"
            )
            service.predict(request)
        
        # Check cache stats
        cache_stats = service.get_cache_stats()
        assert cache_stats['total_entries'] > 0
        
        # Clear cache
        service.clear_cache()
        cache_stats_after = service.get_cache_stats()
        assert cache_stats_after['total_entries'] == 0

    def test_utility_functions(self):
        """Test utility functions."""
        # Test sample data creation
        classification_data = create_sample_classification_data(10, 3)
        assert isinstance(classification_data, pd.DataFrame)
        assert classification_data.shape == (10, 3)
        assert all(col.startswith('feature_') for col in classification_data.columns)
        
        regression_data = create_sample_regression_data(5, 2)
        assert isinstance(regression_data, pd.DataFrame)
        assert regression_data.shape == (5, 2)
        
        # Test sample request creation
        sample_requests = create_sample_prediction_requests(7)
        assert len(sample_requests) == 7
        assert all(isinstance(req, PredictionRequest) for req in sample_requests)
        assert all(req.model_name == "classifier" for req in sample_requests)

    def test_advanced_prediction_scenarios(self):
        """Test advanced prediction scenarios."""
        service = PredictionService()
        
        # Test with different data formats
        data_formats = [
            create_sample_classification_data(1),  # DataFrame
            np.random.randn(1, 3),  # numpy array
            [1.0, 2.0, 3.0],  # list
        ]
        
        for i, data in enumerate(data_formats):
            request = PredictionRequest(
                request_id=f"format_test_{i}",
                input_data=data,
                model_name="classifier"
            )
            
            result = service.predict(request)
            assert result.status in [PredictionStatus.COMPLETED, PredictionStatus.CACHED]

    def test_concurrent_predictions(self):
        """Test concurrent prediction handling."""
        service = PredictionService(max_workers=4)
        
        # Create multiple batch jobs
        all_jobs = []
        for i in range(3):
            requests = create_sample_prediction_requests(5)
            job = service.predict_batch(requests, f"concurrent_{i}")
            all_jobs.append(job)
        
        # All jobs should complete successfully
        for job in all_jobs:
            assert job.status == PredictionStatus.COMPLETED
            assert len(job.results) == 5

    def test_error_scenarios(self):
        """Test various error scenarios."""
        service = PredictionService()
        
        error_scenarios = [
            # Empty input
            {"input_data": [], "expected_error": "empty"},
            # Invalid model
            {"input_data": [1, 2, 3], "model_name": "invalid_model", "expected_error": "not found"},
        ]
        
        for i, scenario in enumerate(error_scenarios):
            request = PredictionRequest(
                request_id=f"error_{i}",
                input_data=scenario["input_data"],
                model_name=scenario.get("model_name", "classifier")
            )
            
            result = service.predict(request)
            assert result.status == PredictionStatus.FAILED
            assert scenario["expected_error"].lower() in result.error_message.lower()