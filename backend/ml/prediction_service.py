"""
Module 58: ML Prediction Service
Comprehensive prediction service for machine learning models.
"""

import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


class PredictionStatus(Enum):
    """Prediction status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CACHED = "cached"


class PredictionType(Enum):
    """Type of prediction."""
    CLASSIFICATION = "classification"
    REGRESSION = "regression"
    FORECAST = "forecast"
    ANOMALY_DETECTION = "anomaly_detection"


@dataclass
class PredictionRequest:
    """Prediction request structure."""
    request_id: str
    input_data: dict | list | np.ndarray | pd.DataFrame
    model_name: str
    model_version: str = "latest"
    prediction_type: PredictionType = PredictionType.CLASSIFICATION
    confidence_threshold: float = 0.5
    return_probabilities: bool = False
    cache_enabled: bool = True
    timeout: float = 30.0
    metadata: dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class PredictionResult:
    """Prediction result structure."""
    request_id: str
    predictions: list | np.ndarray | float | int
    confidence: list[float] | float | None = None
    probabilities: list[list[float]] | list[float] | None = None
    status: PredictionStatus = PredictionStatus.COMPLETED
    processing_time: float = 0.0
    model_name: str = ""
    model_version: str = ""
    timestamp: datetime = None
    error_message: str | None = None
    metadata: dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.metadata is None:
            self.metadata = {}


@dataclass
class BatchPredictionJob:
    """Batch prediction job structure."""
    job_id: str
    requests: list[PredictionRequest]
    status: PredictionStatus = PredictionStatus.PENDING
    progress: float = 0.0
    total_requests: int = 0
    completed_requests: int = 0
    failed_requests: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    results: list[PredictionResult] = None
    
    def __post_init__(self):
        if self.results is None:
            self.results = []
        self.total_requests = len(self.requests)


class PredictionCache:
    """Caching system for predictions."""
    
    def __init__(self, max_size: int = 10000, ttl_hours: int = 24):
        self.max_size = max_size
        self.ttl_hours = ttl_hours
        self.cache = {}
        self.access_times = {}
        self.lock = threading.RLock()
    
    def _generate_cache_key(self, request: PredictionRequest) -> str:
        """Generate cache key for a prediction request."""
        # Create a deterministic hash of the request
        cache_data = {
            'input_data': self._serialize_input(request.input_data),
            'model_name': request.model_name,
            'model_version': request.model_version,
            'prediction_type': request.prediction_type.value,
            'confidence_threshold': request.confidence_threshold,
            'return_probabilities': request.return_probabilities
        }
        
        cache_str = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def _serialize_input(self, input_data: Any) -> str:
        """Serialize input data for hashing."""
        try:
            if isinstance(input_data, pd.DataFrame):
                # Use values and column names for hashing instead of to_json
                return str(input_data.values.tolist()) + str(input_data.columns.tolist())
            elif isinstance(input_data, np.ndarray):
                return str(input_data.tolist())
            elif isinstance(input_data, (dict, list)):
                return json.dumps(input_data, sort_keys=True)
            else:
                return str(input_data)
        except Exception:
            # Fallback to string representation
            return str(input_data)
    
    def _is_expired(self, timestamp: datetime) -> bool:
        """Check if cache entry is expired."""
        return datetime.now() - timestamp > timedelta(hours=self.ttl_hours)
    
    def _evict_lru(self):
        """Evict least recently used entries."""
        with self.lock:
            if len(self.cache) >= self.max_size:
                # Find oldest access time
                oldest_key = min(self.access_times.keys(), 
                               key=lambda k: self.access_times[k])
                del self.cache[oldest_key]
                del self.access_times[oldest_key]
    
    def get(self, request: PredictionRequest) -> PredictionResult | None:
        """Get cached prediction result."""
        if not request.cache_enabled:
            return None
        
        cache_key = self._generate_cache_key(request)
        
        with self.lock:
            if cache_key in self.cache:
                result, timestamp = self.cache[cache_key]
                
                if not self._is_expired(timestamp):
                    self.access_times[cache_key] = datetime.now()
                    result.status = PredictionStatus.CACHED
                    return result
                else:
                    # Remove expired entry
                    del self.cache[cache_key]
                    del self.access_times[cache_key]
        
        return None
    
    def put(self, request: PredictionRequest, result: PredictionResult):
        """Store prediction result in cache."""
        if not request.cache_enabled:
            return
        
        cache_key = self._generate_cache_key(request)
        
        with self.lock:
            self._evict_lru()
            self.cache[cache_key] = (result, datetime.now())
            self.access_times[cache_key] = datetime.now()
    
    def clear(self):
        """Clear all cache entries."""
        with self.lock:
            self.cache.clear()
            self.access_times.clear()
    
    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self.lock:
            now = datetime.now()
            expired_count = sum(1 for _, timestamp in self.cache.values()
                              if self._is_expired(timestamp))
            
            return {
                'total_entries': len(self.cache),
                'expired_entries': expired_count,
                'valid_entries': len(self.cache) - expired_count,
                'max_size': self.max_size,
                'ttl_hours': self.ttl_hours
            }


class PredictionValidator:
    """Validation for prediction inputs and outputs."""
    
    @staticmethod
    def validate_input(input_data: Any, expected_features: list[str] = None) -> tuple[bool, str]:
        """Validate prediction input data."""
        try:
            if input_data is None:
                return False, "Input data cannot be None"
            
            if isinstance(input_data, pd.DataFrame):
                if expected_features:
                    missing_features = set(expected_features) - set(input_data.columns)
                    if missing_features:
                        return False, f"Missing features: {missing_features}"
                
                if input_data.empty:
                    return False, "Input DataFrame is empty"
                
                # Check for infinite or NaN values
                if input_data.isin([np.inf, -np.inf, np.nan]).any().any():
                    return False, "Input contains infinite or NaN values"
            
            elif isinstance(input_data, np.ndarray):
                if input_data.size == 0:
                    return False, "Input array is empty"
                
                if np.isnan(input_data).any() or np.isinf(input_data).any():
                    return False, "Input contains infinite or NaN values"
            
            elif isinstance(input_data, (list, dict)):
                if not input_data:
                    return False, "Input data is empty"
            
            return True, "Input validation passed"
        
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    @staticmethod
    def validate_prediction(prediction: Any, prediction_type: PredictionType) -> tuple[bool, str]:
        """Validate prediction output."""
        try:
            if prediction is None:
                return False, "Prediction cannot be None"
            
            if prediction_type == PredictionType.CLASSIFICATION:
                if isinstance(prediction, (list, np.ndarray)):
                    if len(prediction) == 0:
                        return False, "Prediction array is empty"
                elif not isinstance(prediction, (int, float, str)):
                    return False, "Invalid classification prediction type"
            
            elif prediction_type == PredictionType.REGRESSION:
                if isinstance(prediction, (list, np.ndarray)):
                    if len(prediction) == 0:
                        return False, "Prediction array is empty"
                    if np.isnan(prediction).any() or np.isinf(prediction).any():
                        return False, "Prediction contains invalid values"
                elif not isinstance(prediction, (int, float)):
                    return False, "Invalid regression prediction type"
            
            return True, "Prediction validation passed"
        
        except Exception as e:
            return False, f"Prediction validation error: {str(e)}"


class PredictionLogger:
    """Logging for prediction service."""
    
    def __init__(self, log_file: str = "predictions.log"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger("prediction_service")
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.FileHandler(self.log_file)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def log_prediction_request(self, request: PredictionRequest):
        """Log prediction request."""
        self.logger.info(
            f"Prediction request: {request.request_id} - "
            f"Model: {request.model_name}:{request.model_version} - "
            f"Type: {request.prediction_type.value}"
        )
    
    def log_prediction_result(self, result: PredictionResult):
        """Log prediction result."""
        self.logger.info(
            f"Prediction result: {result.request_id} - "
            f"Status: {result.status.value} - "
            f"Processing time: {result.processing_time:.3f}s"
        )
    
    def log_error(self, request_id: str, error: str):
        """Log prediction error."""
        self.logger.error(f"Prediction error: {request_id} - {error}")
    
    def log_batch_job(self, job: BatchPredictionJob):
        """Log batch prediction job."""
        self.logger.info(
            f"Batch job: {job.job_id} - "
            f"Status: {job.status.value} - "
            f"Progress: {job.progress:.1%} - "
            f"Completed: {job.completed_requests}/{job.total_requests}"
        )


def timeout_handler(timeout: float):
    """Decorator for handling prediction timeouts."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Prediction timed out after {timeout} seconds")
            
            # Set up timeout for Unix systems
            if hasattr(signal, 'SIGALRM'):
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(int(timeout))
                
                try:
                    result = func(*args, **kwargs)
                    signal.alarm(0)  # Cancel alarm
                    return result
                except TimeoutError:
                    raise
                finally:
                    signal.signal(signal.SIGALRM, old_handler)
            else:
                # Fallback for Windows (no timeout handling)
                return func(*args, **kwargs)
        
        return wrapper
    return decorator


class PredictionService:
    """Main prediction service orchestrator."""
    
    def __init__(self, 
                 cache_size: int = 10000,
                 cache_ttl_hours: int = 24,
                 max_workers: int = 4,
                 log_file: str = "predictions.log"):
        
        self.cache = PredictionCache(cache_size, cache_ttl_hours)
        self.validator = PredictionValidator()
        self.logger = PredictionLogger(log_file)
        self.max_workers = max_workers
        
        self.batch_jobs = {}
        self.job_lock = threading.RLock()
        
        # Mock model registry (in practice, this would connect to model management)
        self.models = {}
        self._setup_mock_models()
    
    def _setup_mock_models(self):
        """Setup mock models for testing."""
        # Simple classification model
        def mock_classifier(X):
            try:
                if isinstance(X, pd.DataFrame):
                    X = X.values
                elif isinstance(X, list):
                    X = np.array(X)
                
                if X.ndim == 1:
                    X = X.reshape(1, -1)
                
                # Ensure X has valid numeric values
                X = np.nan_to_num(X, nan=0.0, posinf=1.0, neginf=-1.0)
                
                # Mock prediction based on sum of features
                predictions = (X.sum(axis=1) > 0).astype(int)
                
                # Generate probabilities that sum to 1
                n_samples = len(predictions)
                prob_class_1 = np.random.uniform(0.1, 0.9, size=n_samples)
                prob_class_0 = 1.0 - prob_class_1
                probabilities = np.column_stack([prob_class_0, prob_class_1])
                
                return predictions, probabilities
            except Exception:
                # Fallback predictions
                n_samples = 1 if np.isscalar(X) else len(X) if hasattr(X, '__len__') else 1
                predictions = np.zeros(n_samples, dtype=int)
                probabilities = np.full((n_samples, 2), 0.5)
                return predictions, probabilities
        
        # Simple regression model
        def mock_regressor(X):
            try:
                if isinstance(X, pd.DataFrame):
                    X = X.values
                elif isinstance(X, list):
                    X = np.array(X)
                
                if X.ndim == 1:
                    X = X.reshape(1, -1)
                
                # Ensure X has valid numeric values
                X = np.nan_to_num(X, nan=0.0, posinf=1.0, neginf=-1.0)
                
                # Mock prediction based on weighted sum
                predictions = X.mean(axis=1) * 2.5 + np.random.normal(0, 0.1, X.shape[0])
                return predictions
            except Exception:
                # Fallback prediction
                n_samples = 1 if np.isscalar(X) else len(X) if hasattr(X, '__len__') else 1
                return np.full(n_samples, 1.0)
        
        self.models = {
            'classifier:1.0': {
                'model': mock_classifier,
                'type': PredictionType.CLASSIFICATION,
                'features': ['feature_1', 'feature_2', 'feature_3']
            },
            'regressor:1.0': {
                'model': mock_regressor,
                'type': PredictionType.REGRESSION,
                'features': ['feature_1', 'feature_2']
            }
        }
    
    def _get_model(self, model_name: str, model_version: str = "latest"):
        """Get model from registry."""
        model_key = f"{model_name}:{model_version}"
        if model_version == "latest":
            # Find latest version (simplified)
            available_versions = [key for key in self.models.keys() 
                                if key.startswith(f"{model_name}:")]
            if available_versions:
                model_key = max(available_versions)  # Simple string comparison
            else:
                return None
        
        return self.models.get(model_key)
    
    def predict(self, request: PredictionRequest) -> PredictionResult:
        """Generate single prediction."""
        start_time = time.time()
        self.logger.log_prediction_request(request)
        
        try:
            # Check cache first
            cached_result = self.cache.get(request)
            if cached_result:
                cached_result.request_id = request.request_id
                self.logger.log_prediction_result(cached_result)
                return cached_result
            
            # Validate input
            model_info = self._get_model(request.model_name, request.model_version)
            if not model_info:
                raise ValueError(f"Model {request.model_name}:{request.model_version} not found")
            
            expected_features = model_info.get('features', [])
            is_valid, validation_message = self.validator.validate_input(
                request.input_data, expected_features
            )
            
            if not is_valid:
                raise ValueError(f"Input validation failed: {validation_message}")
            
            # Generate prediction
            model = model_info['model']
            model_type = model_info['type']
            
            if model_type == PredictionType.CLASSIFICATION:
                predictions, probabilities = model(request.input_data)
                
                # Calculate confidence
                if request.return_probabilities:
                    confidence = np.max(probabilities, axis=1) if probabilities.ndim > 1 else np.max(probabilities)
                else:
                    confidence = np.random.uniform(0.7, 0.95, size=len(predictions) if hasattr(predictions, '__len__') else 1)
                    probabilities = probabilities if request.return_probabilities else None
                
            elif model_type == PredictionType.REGRESSION:
                predictions = model(request.input_data)
                # For regression, confidence could be prediction interval
                confidence = np.random.uniform(0.8, 0.95, size=len(predictions) if hasattr(predictions, '__len__') else 1)
                probabilities = None
            
            else:
                raise ValueError(f"Unsupported prediction type: {model_type}")
            
            # Validate predictions
            is_valid, validation_message = self.validator.validate_prediction(
                predictions, model_type
            )
            
            if not is_valid:
                raise ValueError(f"Prediction validation failed: {validation_message}")
            
            # Create result
            processing_time = time.time() - start_time
            result = PredictionResult(
                request_id=request.request_id,
                predictions=predictions.tolist() if hasattr(predictions, 'tolist') else predictions,
                confidence=confidence.tolist() if hasattr(confidence, 'tolist') else confidence,
                probabilities=probabilities.tolist() if probabilities is not None and hasattr(probabilities, 'tolist') else probabilities,
                status=PredictionStatus.COMPLETED,
                processing_time=processing_time,
                model_name=request.model_name,
                model_version=request.model_version
            )
            
            # Cache result
            self.cache.put(request, result)
            
            self.logger.log_prediction_result(result)
            return result
        
        except Exception as e:
            processing_time = time.time() - start_time
            error_message = str(e)
            self.logger.log_error(request.request_id, error_message)
            
            return PredictionResult(
                request_id=request.request_id,
                predictions=[],
                status=PredictionStatus.FAILED,
                processing_time=processing_time,
                model_name=request.model_name,
                model_version=request.model_version,
                error_message=error_message
            )
    
    def predict_batch(self, requests: list[PredictionRequest], 
                     job_id: str = None) -> BatchPredictionJob:
        """Generate batch predictions."""
        if job_id is None:
            job_id = f"batch_{int(time.time())}_{len(requests)}"
        
        job = BatchPredictionJob(job_id=job_id, requests=requests)
        job.started_at = datetime.now()
        job.status = PredictionStatus.PROCESSING
        
        with self.job_lock:
            self.batch_jobs[job_id] = job
        
        self.logger.log_batch_job(job)
        
        try:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all prediction tasks
                future_to_request = {
                    executor.submit(self.predict, req): req 
                    for req in requests
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_request):
                    request = future_to_request[future]
                    try:
                        result = future.result()
                        job.results.append(result)
                        
                        if result.status == PredictionStatus.COMPLETED:
                            job.completed_requests += 1
                        else:
                            job.failed_requests += 1
                        
                        job.progress = (job.completed_requests + job.failed_requests) / job.total_requests
                        
                    except Exception as e:
                        error_result = PredictionResult(
                            request_id=request.request_id,
                            predictions=[],
                            status=PredictionStatus.FAILED,
                            model_name=request.model_name,
                            model_version=request.model_version,
                            error_message=str(e)
                        )
                        job.results.append(error_result)
                        job.failed_requests += 1
                        job.progress = (job.completed_requests + job.failed_requests) / job.total_requests
            
            job.status = PredictionStatus.COMPLETED
            job.completed_at = datetime.now()
            
        except Exception as e:
            job.status = PredictionStatus.FAILED
            job.completed_at = datetime.now()
            self.logger.log_error(job_id, f"Batch job failed: {str(e)}")
        
        self.logger.log_batch_job(job)
        return job
    
    def get_batch_job_status(self, job_id: str) -> BatchPredictionJob | None:
        """Get batch job status."""
        with self.job_lock:
            return self.batch_jobs.get(job_id)
    
    def predict_realtime(self, input_data: Any, model_name: str, 
                        model_version: str = "latest",
                        timeout: float = 5.0) -> PredictionResult:
        """Generate real-time prediction with timeout."""
        request_id = f"realtime_{int(time.time() * 1000)}"
        request = PredictionRequest(
            request_id=request_id,
            input_data=input_data,
            model_name=model_name,
            model_version=model_version,
            timeout=timeout,
            cache_enabled=True
        )
        
        @timeout_handler(timeout)
        def _predict():
            return self.predict(request)
        
        try:
            return _predict()
        except TimeoutError:
            return PredictionResult(
                request_id=request_id,
                predictions=[],
                status=PredictionStatus.FAILED,
                model_name=model_name,
                model_version=model_version,
                error_message=f"Prediction timed out after {timeout} seconds"
            )
    
    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return self.cache.get_stats()
    
    def clear_cache(self):
        """Clear prediction cache."""
        self.cache.clear()
    
    def get_service_stats(self) -> dict[str, Any]:
        """Get service statistics."""
        with self.job_lock:
            active_jobs = sum(1 for job in self.batch_jobs.values() 
                            if job.status == PredictionStatus.PROCESSING)
            completed_jobs = sum(1 for job in self.batch_jobs.values() 
                               if job.status == PredictionStatus.COMPLETED)
            failed_jobs = sum(1 for job in self.batch_jobs.values() 
                            if job.status == PredictionStatus.FAILED)
        
        cache_stats = self.get_cache_stats()
        
        return {
            'total_batch_jobs': len(self.batch_jobs),
            'active_batch_jobs': active_jobs,
            'completed_batch_jobs': completed_jobs,
            'failed_batch_jobs': failed_jobs,
            'available_models': list(self.models.keys()),
            'cache_stats': cache_stats,
            'max_workers': self.max_workers
        }


# Utility functions for testing and examples
def create_sample_classification_data(n_samples: int = 100, n_features: int = 3) -> pd.DataFrame:
    """Create sample classification data."""
    np.random.seed(42)
    data = np.random.randn(n_samples, n_features)
    columns = [f'feature_{i+1}' for i in range(n_features)]
    return pd.DataFrame(data, columns=columns)


def create_sample_regression_data(n_samples: int = 100, n_features: int = 2) -> pd.DataFrame:
    """Create sample regression data."""
    np.random.seed(42)
    data = np.random.randn(n_samples, n_features)
    columns = [f'feature_{i+1}' for i in range(n_features)]
    return pd.DataFrame(data, columns=columns)


def create_sample_prediction_requests(n_requests: int = 10) -> list[PredictionRequest]:
    """Create sample prediction requests."""
    requests = []
    for i in range(n_requests):
        data = create_sample_classification_data(1)
        request = PredictionRequest(
            request_id=f"request_{i}",
            input_data=data,
            model_name="classifier",
            model_version="1.0",
            prediction_type=PredictionType.CLASSIFICATION
        )
        requests.append(request)
    return requests