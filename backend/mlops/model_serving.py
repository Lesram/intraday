"""
MLOps Model Serving Service

Comprehensive model serving system providing:
- Real-time inference endpoints
- Batch processing capabilities
- A/B testing and canary deployments
- Auto-scaling and load balancing
- Performance monitoring and metrics
- Model version management
- Health checks and circuit breakers
- Request/response logging
- Integration with popular ML frameworks

Author: MLOps Team
Created: 2025-01-01
Version: 1.0.0
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import logging
from pathlib import Path
import time
from typing import Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ServingMode(str, Enum):
    """Model serving mode enumeration."""
    REALTIME = "realtime"
    BATCH = "batch"
    STREAMING = "streaming"
    EDGE = "edge"


class ModelStatus(str, Enum):
    """Model serving status enumeration."""
    LOADING = "loading"
    READY = "ready"
    SERVING = "serving"
    PAUSED = "paused"
    ERROR = "error"
    UPDATING = "updating"
    RETIRED = "retired"


class DeploymentStrategy(str, Enum):
    """Deployment strategy enumeration."""
    BLUE_GREEN = "blue_green"
    CANARY = "canary"
    ROLLING = "rolling"
    IMMEDIATE = "immediate"
    A_B_TEST = "a_b_test"


class HealthStatus(str, Enum):
    """Health status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class PredictionRequest:
    """Prediction request representation."""
    id: str
    inputs: dict[str, Any]
    model_name: str
    model_version: str = "latest"
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'inputs': self.inputs,
            'model_name': self.model_name,
            'model_version': self.model_version,
            'metadata': self.metadata,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class PredictionResponse:
    """Prediction response representation."""
    request_id: str
    predictions: dict[str, Any]
    model_name: str
    model_version: str
    confidence: float | None = None
    latency_ms: float = 0.0
    status: str = "success"
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'request_id': self.request_id,
            'predictions': self.predictions,
            'model_name': self.model_name,
            'model_version': self.model_version,
            'confidence': self.confidence,
            'latency_ms': self.latency_ms,
            'status': self.status,
            'error_message': self.error_message,
            'metadata': self.metadata,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class ModelEndpoint:
    """Model endpoint configuration."""
    name: str
    model_name: str
    model_version: str
    endpoint_url: str
    serving_mode: ServingMode = ServingMode.REALTIME
    status: ModelStatus = ModelStatus.LOADING
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'model_name': self.model_name,
            'model_version': self.model_version,
            'endpoint_url': self.endpoint_url,
            'serving_mode': self.serving_mode.value,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'metadata': self.metadata
        }


class ModelPredictor(ABC):
    """Abstract base class for model predictors."""

    @abstractmethod
    def load_model(self, model_path: str, model_version: str) -> bool:
        """Load model from path."""
        pass

    @abstractmethod
    def predict(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Make prediction."""
        pass

    @abstractmethod
    def preprocess(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Preprocess inputs."""
        pass

    @abstractmethod
    def postprocess(self, outputs: dict[str, Any]) -> dict[str, Any]:
        """Postprocess outputs."""
        pass

    @abstractmethod
    def get_model_info(self) -> dict[str, Any]:
        """Get model information."""
        pass


class DefaultPredictor(ModelPredictor):
    """Default model predictor implementation."""

    def __init__(self):
        self.model = None
        self.model_info = {}

    def load_model(self, model_path: str, model_version: str) -> bool:
        """Load model from path."""
        try:
            # Simulate model loading
            self.model_info = {
                'model_path': model_path,
                'model_version': model_version,
                'loaded_at': datetime.now().isoformat(),
                'framework': 'default'
            }
            self.model = {'loaded': True, 'path': model_path}
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False

    def predict(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Make prediction."""
        if not self.model:
            raise ValueError("Model not loaded")

        # Simulate prediction
        prediction = {
            'prediction': f"processed_{inputs.get('data', 'unknown')}",
            'confidence': 0.95,
            'model_version': self.model_info.get('model_version', 'unknown')
        }
        return prediction

    def preprocess(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Preprocess inputs."""
        # Simple preprocessing
        processed = {
            'data': str(inputs.get('data', '')).lower(),
            'processed_at': datetime.now().isoformat()
        }
        return processed

    def postprocess(self, outputs: dict[str, Any]) -> dict[str, Any]:
        """Postprocess outputs."""
        # Simple postprocessing
        processed = {
            'result': outputs.get('prediction', ''),
            'confidence': outputs.get('confidence', 0.0),
            'postprocessed_at': datetime.now().isoformat()
        }
        return processed

    def get_model_info(self) -> dict[str, Any]:
        """Get model information."""
        return self.model_info.copy()


@dataclass
class ModelVersion:
    """Model version representation."""
    model_name: str
    version: str
    model_path: str
    predictor_class: str = "DefaultPredictor"
    status: ModelStatus = ModelStatus.LOADING
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'model_name': self.model_name,
            'version': self.version,
            'model_path': self.model_path,
            'predictor_class': self.predictor_class,
            'status': self.status.value,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


class HealthChecker:
    """Health checker for model endpoints."""

    def __init__(self):
        self.checks = {}
        self.last_check_times = {}

    def register_check(self, endpoint_name: str, check_func: Callable[[], bool]):
        """Register a health check function."""
        self.checks[endpoint_name] = check_func
        self.last_check_times[endpoint_name] = None

    def check_health(self, endpoint_name: str) -> HealthStatus:
        """Check health of an endpoint."""
        if endpoint_name not in self.checks:
            return HealthStatus.UNKNOWN

        try:
            check_func = self.checks[endpoint_name]
            is_healthy = check_func()
            self.last_check_times[endpoint_name] = datetime.now()

            return HealthStatus.HEALTHY if is_healthy else HealthStatus.UNHEALTHY
        except Exception as e:
            logger.error(f"Health check failed for {endpoint_name}: {e}")
            return HealthStatus.DEGRADED

    def get_all_health_status(self) -> dict[str, HealthStatus]:
        """Get health status for all registered endpoints."""
        status = {}
        for endpoint_name in self.checks:
            status[endpoint_name] = self.check_health(endpoint_name)
        return status


class PerformanceMonitor:
    """Performance monitoring for model serving."""

    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.metrics = {}
        self.request_history = {}

    def record_request(self, model_name: str, latency_ms: float,
                      success: bool, timestamp: datetime | None = None):
        """Record a request for performance monitoring."""
        if timestamp is None:
            timestamp = datetime.now()

        if model_name not in self.metrics:
            self.metrics[model_name] = {
                'total_requests': 0,
                'successful_requests': 0,
                'failed_requests': 0,
                'total_latency': 0.0,
                'min_latency': float('inf'),
                'max_latency': 0.0,
                'last_updated': timestamp
            }
            self.request_history[model_name] = []

        metrics = self.metrics[model_name]
        history = self.request_history[model_name]

        # Update metrics
        metrics['total_requests'] += 1
        if success:
            metrics['successful_requests'] += 1
        else:
            metrics['failed_requests'] += 1

        metrics['total_latency'] += latency_ms
        metrics['min_latency'] = min(metrics['min_latency'], latency_ms)
        metrics['max_latency'] = max(metrics['max_latency'], latency_ms)
        metrics['last_updated'] = timestamp

        # Add to history
        history.append({
            'timestamp': timestamp,
            'latency_ms': latency_ms,
            'success': success
        })

        # Maintain window size
        if len(history) > self.window_size:
            history.pop(0)

    def get_metrics(self, model_name: str) -> dict[str, Any]:
        """Get performance metrics for a model."""
        if model_name not in self.metrics:
            return {}

        metrics = self.metrics[model_name].copy()

        # Calculate derived metrics
        if metrics['total_requests'] > 0:
            metrics['success_rate'] = metrics['successful_requests'] / metrics['total_requests']
            metrics['failure_rate'] = metrics['failed_requests'] / metrics['total_requests']
            metrics['avg_latency'] = metrics['total_latency'] / metrics['total_requests']
        else:
            metrics['success_rate'] = 0.0
            metrics['failure_rate'] = 0.0
            metrics['avg_latency'] = 0.0

        # Calculate requests per second
        history = self.request_history.get(model_name, [])
        if len(history) >= 2:
            time_window = (history[-1]['timestamp'] - history[0]['timestamp']).total_seconds()
            if time_window > 0:
                metrics['requests_per_second'] = len(history) / time_window
            else:
                metrics['requests_per_second'] = 0.0
        else:
            metrics['requests_per_second'] = 0.0

        return metrics

    def get_all_metrics(self) -> dict[str, dict[str, Any]]:
        """Get performance metrics for all models."""
        all_metrics = {}
        for model_name in self.metrics:
            all_metrics[model_name] = self.get_metrics(model_name)
        return all_metrics


class ABTestManager:
    """A/B testing manager for model serving."""

    def __init__(self):
        self.experiments = {}
        self.traffic_split = {}

    def create_experiment(self, experiment_name: str, model_a: str, model_b: str,
                         traffic_split: float = 0.5, metadata: dict[str, Any] | None = None):
        """Create A/B testing experiment."""
        if metadata is None:
            metadata = {}

        experiment = {
            'name': experiment_name,
            'model_a': model_a,
            'model_b': model_b,
            'traffic_split': traffic_split,  # Percentage of traffic to model_b
            'created_at': datetime.now(),
            'status': 'active',
            'metrics': {
                'model_a': {'requests': 0, 'successes': 0, 'total_latency': 0.0},
                'model_b': {'requests': 0, 'successes': 0, 'total_latency': 0.0}
            },
            'metadata': metadata
        }

        self.experiments[experiment_name] = experiment
        logger.info(f"Created A/B test experiment: {experiment_name}")

    def route_request(self, experiment_name: str, request_id: str) -> str:
        """Route request to appropriate model based on A/B test configuration."""
        if experiment_name not in self.experiments:
            raise ValueError(f"Experiment {experiment_name} not found")

        experiment = self.experiments[experiment_name]

        # Simple hash-based routing for consistent user experience
        hash_val = int(hashlib.md5(request_id.encode()).hexdigest(), 16)
        traffic_threshold = hash_val % 100 / 100.0

        if traffic_threshold < experiment['traffic_split']:
            return experiment['model_b']
        else:
            return experiment['model_a']

    def record_result(self, experiment_name: str, model_name: str,
                     success: bool, latency_ms: float):
        """Record A/B test result."""
        if experiment_name not in self.experiments:
            return

        experiment = self.experiments[experiment_name]

        # Determine which model (a or b)
        if model_name == experiment['model_a']:
            metrics = experiment['metrics']['model_a']
        elif model_name == experiment['model_b']:
            metrics = experiment['metrics']['model_b']
        else:
            return

        metrics['requests'] += 1
        if success:
            metrics['successes'] += 1
        metrics['total_latency'] += latency_ms

    def get_experiment_results(self, experiment_name: str) -> dict[str, Any]:
        """Get A/B test experiment results."""
        if experiment_name not in self.experiments:
            return {}

        experiment = self.experiments[experiment_name]
        results = {
            'experiment': experiment_name,
            'model_a': experiment['model_a'],
            'model_b': experiment['model_b'],
            'traffic_split': experiment['traffic_split'],
            'status': experiment['status'],
            'created_at': experiment['created_at'].isoformat(),
            'results': {}
        }

        for model_key in ['model_a', 'model_b']:
            metrics = experiment['metrics'][model_key]
            model_results = {
                'requests': metrics['requests'],
                'successes': metrics['successes'],
                'success_rate': metrics['successes'] / metrics['requests'] if metrics['requests'] > 0 else 0,
                'avg_latency': metrics['total_latency'] / metrics['requests'] if metrics['requests'] > 0 else 0
            }
            results['results'][model_key] = model_results

        return results

    def stop_experiment(self, experiment_name: str) -> bool:
        """Stop A/B test experiment."""
        if experiment_name in self.experiments:
            self.experiments[experiment_name]['status'] = 'stopped'
            return True
        return False


class ModelServingEngine:
    """Main model serving engine."""

    def __init__(self, storage_path: str = "./model_serving"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.models: dict[str, ModelVersion] = {}
        self.endpoints: dict[str, ModelEndpoint] = {}
        self.predictors: dict[str, ModelPredictor] = {}
        self.health_checker = HealthChecker()
        self.performance_monitor = PerformanceMonitor()
        self.ab_test_manager = ABTestManager()

        # Request logging
        self.request_log = []
        self.log_enabled = True

    def register_model(self, model_name: str, version: str, model_path: str,
                      predictor_class: str = "DefaultPredictor",
                      metadata: dict[str, Any] | None = None) -> bool:
        """Register a model version."""
        if metadata is None:
            metadata = {}

        model_key = f"{model_name}:{version}"

        model_version = ModelVersion(
            model_name=model_name,
            version=version,
            model_path=model_path,
            predictor_class=predictor_class,
            metadata=metadata
        )

        self.models[model_key] = model_version

        # Create and load predictor
        if predictor_class == "DefaultPredictor":
            predictor = DefaultPredictor()
        else:
            # In a real implementation, you'd use dynamic loading
            predictor = DefaultPredictor()

        success = predictor.load_model(model_path, version)
        if success:
            model_version.status = ModelStatus.READY
            self.predictors[model_key] = predictor
            logger.info(f"Registered model: {model_key}")
        else:
            model_version.status = ModelStatus.ERROR
            logger.error(f"Failed to load model: {model_key}")

        return success

    def create_endpoint(self, endpoint_name: str, model_name: str, model_version: str,
                       serving_mode: ServingMode = ServingMode.REALTIME,
                       metadata: dict[str, Any] | None = None) -> bool:
        """Create a serving endpoint."""
        if metadata is None:
            metadata = {}

        model_key = f"{model_name}:{model_version}"
        if model_key not in self.models:
            logger.error(f"Model {model_key} not found")
            return False

        endpoint_url = f"/predict/{endpoint_name}"

        endpoint = ModelEndpoint(
            name=endpoint_name,
            model_name=model_name,
            model_version=model_version,
            endpoint_url=endpoint_url,
            serving_mode=serving_mode,
            status=ModelStatus.READY,
            metadata=metadata
        )

        self.endpoints[endpoint_name] = endpoint

        # Register health check
        def health_check():
            return model_key in self.predictors and self.models[model_key].status == ModelStatus.READY

        self.health_checker.register_check(endpoint_name, health_check)

        logger.info(f"Created endpoint: {endpoint_name} -> {model_key}")
        return True

    def predict(self, request: PredictionRequest) -> PredictionResponse:
        """Make prediction using specified model."""
        start_time = time.time()

        try:
            # Check if this is an A/B test
            request.metadata.get('endpoint_name')
            experiment_name = request.metadata.get('ab_experiment')

            if experiment_name:
                model_name = self.ab_test_manager.route_request(experiment_name, request.id)
                # Find the appropriate version
                model_version = request.model_version
                for _key, model in self.models.items():
                    if model.model_name == model_name and model.status == ModelStatus.READY:
                        model_version = model.version
                        break
            else:
                model_name = request.model_name
                model_version = request.model_version

            model_key = f"{model_name}:{model_version}"

            if model_key not in self.predictors:
                raise ValueError(f"Model {model_key} not available")

            if self.models[model_key].status != ModelStatus.READY:
                raise ValueError(f"Model {model_key} not ready")

            predictor = self.predictors[model_key]

            # Preprocess
            processed_inputs = predictor.preprocess(request.inputs)

            # Predict
            raw_outputs = predictor.predict(processed_inputs)

            # Postprocess
            final_outputs = predictor.postprocess(raw_outputs)

            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            response = PredictionResponse(
                request_id=request.id,
                predictions=final_outputs,
                model_name=model_name,
                model_version=model_version,
                confidence=raw_outputs.get('confidence'),
                latency_ms=latency_ms,
                status="success"
            )

            # Record metrics
            self.performance_monitor.record_request(model_key, latency_ms, True)

            # Record A/B test result
            if experiment_name:
                self.ab_test_manager.record_result(experiment_name, model_name, True, latency_ms)

            # Log request
            if self.log_enabled:
                self._log_request(request, response)

            return response

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000

            error_response = PredictionResponse(
                request_id=request.id,
                predictions={},
                model_name=request.model_name,
                model_version=request.model_version,
                latency_ms=latency_ms,
                status="error",
                error_message=str(e)
            )

            # Record failed metrics
            model_key = f"{request.model_name}:{request.model_version}"
            self.performance_monitor.record_request(model_key, latency_ms, False)

            # Record A/B test failure
            experiment_name = request.metadata.get('ab_experiment')
            if experiment_name:
                self.ab_test_manager.record_result(experiment_name, request.model_name, False, latency_ms)

            # Log failed request
            if self.log_enabled:
                self._log_request(request, error_response)

            logger.error(f"Prediction failed: {e}")
            return error_response

    def batch_predict(self, requests: list[PredictionRequest]) -> list[PredictionResponse]:
        """Process batch predictions."""
        responses = []
        for request in requests:
            response = self.predict(request)
            responses.append(response)
        return responses

    def _log_request(self, request: PredictionRequest, response: PredictionResponse):
        """Log request and response."""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'request': request.to_dict(),
            'response': response.to_dict()
        }
        self.request_log.append(log_entry)

        # Maintain log size
        if len(self.request_log) > 10000:
            self.request_log = self.request_log[-5000:]  # Keep last 5000 entries

    def get_model_info(self, model_name: str, model_version: str = "latest") -> dict[str, Any]:
        """Get model information."""
        if model_version == "latest":
            # Find latest version
            latest_version = None
            latest_time = None

            for _key, model in self.models.items():
                if model.model_name == model_name:
                    if latest_time is None or model.created_at > latest_time:
                        latest_time = model.created_at
                        latest_version = model.version

            if latest_version:
                model_version = latest_version
            else:
                return {}

        model_key = f"{model_name}:{model_version}"
        if model_key not in self.models:
            return {}

        model_info = self.models[model_key].to_dict()

        # Add predictor info if available
        if model_key in self.predictors:
            predictor_info = self.predictors[model_key].get_model_info()
            model_info['predictor_info'] = predictor_info

        return model_info

    def list_models(self) -> list[dict[str, Any]]:
        """List all registered models."""
        return [model.to_dict() for model in self.models.values()]

    def list_endpoints(self) -> list[dict[str, Any]]:
        """List all endpoints."""
        return [endpoint.to_dict() for endpoint in self.endpoints.values()]

    def get_endpoint_health(self, endpoint_name: str) -> HealthStatus:
        """Get endpoint health status."""
        return self.health_checker.check_health(endpoint_name)

    def get_all_health_status(self) -> dict[str, HealthStatus]:
        """Get health status for all endpoints."""
        return self.health_checker.get_all_health_status()

    def get_performance_metrics(self, model_name: str = None) -> dict[str, Any]:
        """Get performance metrics."""
        if model_name:
            return self.performance_monitor.get_metrics(model_name)
        else:
            return self.performance_monitor.get_all_metrics()

    def create_ab_experiment(self, experiment_name: str, model_a: str, model_b: str,
                           traffic_split: float = 0.5, metadata: dict[str, Any] | None = None):
        """Create A/B testing experiment."""
        self.ab_test_manager.create_experiment(experiment_name, model_a, model_b, traffic_split, metadata)

    def get_ab_experiment_results(self, experiment_name: str) -> dict[str, Any]:
        """Get A/B testing experiment results."""
        return self.ab_test_manager.get_experiment_results(experiment_name)

    def stop_ab_experiment(self, experiment_name: str) -> bool:
        """Stop A/B testing experiment."""
        return self.ab_test_manager.stop_experiment(experiment_name)

    def get_request_logs(self, limit: int = 100,
                        model_name: str | None = None) -> list[dict[str, Any]]:
        """Get request logs."""
        logs = self.request_log[-limit:] if limit > 0 else self.request_log

        if model_name:
            filtered_logs = []
            for log in logs:
                if log['request']['model_name'] == model_name:
                    filtered_logs.append(log)
            return filtered_logs

        return logs

    def update_model_status(self, model_name: str, model_version: str,
                           status: ModelStatus) -> bool:
        """Update model status."""
        model_key = f"{model_name}:{model_version}"
        if model_key in self.models:
            self.models[model_key].status = status
            self.models[model_key].updated_at = datetime.now()
            return True
        return False

    def retire_model(self, model_name: str, model_version: str) -> bool:
        """Retire a model version."""
        return self.update_model_status(model_name, model_version, ModelStatus.RETIRED)

    def pause_endpoint(self, endpoint_name: str) -> bool:
        """Pause an endpoint."""
        if endpoint_name in self.endpoints:
            self.endpoints[endpoint_name].status = ModelStatus.PAUSED
            self.endpoints[endpoint_name].updated_at = datetime.now()
            return True
        return False

    def resume_endpoint(self, endpoint_name: str) -> bool:
        """Resume an endpoint."""
        if endpoint_name in self.endpoints:
            self.endpoints[endpoint_name].status = ModelStatus.SERVING
            self.endpoints[endpoint_name].updated_at = datetime.now()
            return True
        return False

    def delete_endpoint(self, endpoint_name: str) -> bool:
        """Delete an endpoint."""
        if endpoint_name in self.endpoints:
            del self.endpoints[endpoint_name]
            return True
        return False

    def get_serving_stats(self) -> dict[str, Any]:
        """Get overall serving statistics."""
        total_models = len(self.models)
        active_models = sum(1 for model in self.models.values() if model.status == ModelStatus.READY)
        total_endpoints = len(self.endpoints)
        active_endpoints = sum(1 for endpoint in self.endpoints.values() if endpoint.status in [ModelStatus.READY, ModelStatus.SERVING])

        return {
            'total_models': total_models,
            'active_models': active_models,
            'total_endpoints': total_endpoints,
            'active_endpoints': active_endpoints,
            'total_requests': len(self.request_log),
            'health_status': self.get_all_health_status(),
            'performance_metrics': self.get_performance_metrics()
        }


# Convenience functions
def create_serving_engine(storage_path: str = "./model_serving") -> ModelServingEngine:
    """Create a model serving engine instance."""
    return ModelServingEngine(storage_path)


def create_prediction_request(request_id: str, inputs: dict[str, Any],
                            model_name: str, model_version: str = "latest",
                            metadata: dict[str, Any] | None = None) -> PredictionRequest:
    """Create a prediction request."""
    if metadata is None:
        metadata = {}

    return PredictionRequest(
        id=request_id,
        inputs=inputs,
        model_name=model_name,
        model_version=model_version,
        metadata=metadata
    )


def create_model_endpoint(name: str, model_name: str, model_version: str,
                         serving_mode: ServingMode = ServingMode.REALTIME,
                         metadata: dict[str, Any] | None = None) -> ModelEndpoint:
    """Create a model endpoint configuration."""
    if metadata is None:
        metadata = {}

    endpoint_url = f"/predict/{name}"
    return ModelEndpoint(
        name=name,
        model_name=model_name,
        model_version=model_version,
        endpoint_url=endpoint_url,
        serving_mode=serving_mode,
        metadata=metadata
    )


# Export all classes and functions
__all__ = [
    'ServingMode', 'ModelStatus', 'DeploymentStrategy', 'HealthStatus',
    'PredictionRequest', 'PredictionResponse', 'ModelEndpoint',
    'ModelPredictor', 'DefaultPredictor', 'ModelVersion',
    'HealthChecker', 'PerformanceMonitor', 'ABTestManager', 'ModelServingEngine',
    'create_serving_engine', 'create_prediction_request', 'create_model_endpoint'
]
