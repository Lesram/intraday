"""
Module 61: Comprehensive MLOps Deployment Service
Provides comprehensive deployment functionality for machine learning models in production.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
import time
from typing import Any
import warnings

import numpy as np

warnings.filterwarnings('ignore')

# Mock container/orchestration imports
class MockDocker:
    """Mock Docker client for container operations."""

    def __init__(self):
        self.containers = {}
        self.images = {}

    def build(self, path, tag, **kwargs):
        """Mock docker build."""
        self.images[tag] = {'path': path, 'created': datetime.now()}
        return {'Id': f'img_{hash(tag)}'}

    def run(self, image, name=None, ports=None, environment=None, **kwargs):
        """Mock docker run."""
        container_id = f'cont_{hash(name or image)}'
        self.containers[container_id] = {
            'image': image,
            'name': name,
            'ports': ports or {},
            'environment': environment or {},
            'status': 'running',
            'created': datetime.now()
        }
        return {'Id': container_id}

    def stop(self, container_id):
        """Mock docker stop."""
        if container_id in self.containers:
            self.containers[container_id]['status'] = 'stopped'
        return True

    def remove(self, container_id):
        """Mock docker remove."""
        if container_id in self.containers:
            del self.containers[container_id]
        return True

    def list_containers(self):
        """Mock list containers."""
        return list(self.containers.values())

class MockKubernetes:
    """Mock Kubernetes client for orchestration."""

    def __init__(self):
        self.deployments = {}
        self.services = {}
        self.pods = {}

    def create_deployment(self, name, image, replicas=1, **kwargs):
        """Mock create deployment."""
        self.deployments[name] = {
            'name': name,
            'image': image,
            'replicas': replicas,
            'status': 'running',
            'created': datetime.now(),
            **kwargs
        }

        # Create mock pods
        for i in range(replicas):
            pod_name = f'{name}-{i}'
            self.pods[pod_name] = {
                'name': pod_name,
                'deployment': name,
                'status': 'running',
                'created': datetime.now()
            }
        return self.deployments[name]

    def update_deployment(self, name, image=None, replicas=None, **kwargs):
        """Mock update deployment."""
        if name in self.deployments:
            if image:
                self.deployments[name]['image'] = image
            if replicas:
                self.deployments[name]['replicas'] = replicas
            self.deployments[name]['updated'] = datetime.now()
        return self.deployments.get(name)

    def delete_deployment(self, name):
        """Mock delete deployment."""
        if name in self.deployments:
            del self.deployments[name]
            # Remove associated pods
            pods_to_remove = [pod_name for pod_name, pod in self.pods.items()
                            if pod['deployment'] == name]
            for pod_name in pods_to_remove:
                del self.pods[pod_name]
        return True

    def get_deployment_status(self, name):
        """Mock get deployment status."""
        return self.deployments.get(name)

    def create_service(self, name, deployment, port=80, target_port=8080):
        """Mock create service."""
        self.services[name] = {
            'name': name,
            'deployment': deployment,
            'port': port,
            'target_port': target_port,
            'created': datetime.now()
        }
        return self.services[name]

# Enums
class DeploymentStrategy(Enum):
    """Deployment strategies."""
    BLUE_GREEN = "blue_green"
    CANARY = "canary"
    ROLLING = "rolling"
    RECREATE = "recreate"
    A_B_TESTING = "a_b_testing"

class DeploymentStatus(Enum):
    """Deployment status."""
    PENDING = "pending"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    TERMINATED = "terminated"

class HealthStatus(Enum):
    """Health check status."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"

class Environment(Enum):
    """Deployment environments."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"

class ModelVersionStatus(Enum):
    """Model version status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    FAILED = "failed"

# Data Classes
@dataclass
class DeploymentConfig:
    """Deployment configuration."""
    strategy: DeploymentStrategy
    environment: Environment
    model_name: str
    model_version: str
    image_tag: str
    replicas: int = 3
    cpu_request: str = "100m"
    memory_request: str = "128Mi"
    cpu_limit: str = "500m"
    memory_limit: str = "512Mi"
    health_check_path: str = "/health"
    health_check_interval: int = 30
    max_unavailable: int = 1
    max_surge: int = 1
    canary_percentage: float = 10.0
    rollback_threshold: float = 95.0
    auto_rollback: bool = True
    environment_variables: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)

@dataclass
class DeploymentResult:
    """Deployment result."""
    deployment_id: str
    config: DeploymentConfig
    status: DeploymentStatus
    message: str
    start_time: datetime
    end_time: datetime | None = None
    rollback_version: str | None = None
    health_status: HealthStatus = HealthStatus.UNKNOWN
    metrics: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)

@dataclass
class HealthCheckResult:
    """Health check result."""
    endpoint: str
    status: HealthStatus
    response_time: float
    status_code: int
    message: str
    timestamp: datetime
    metrics: dict[str, Any] = field(default_factory=dict)

@dataclass
class RollbackConfig:
    """Rollback configuration."""
    target_version: str
    reason: str
    rollback_strategy: DeploymentStrategy = DeploymentStrategy.ROLLING
    timeout_seconds: int = 300
    preserve_data: bool = True
    notify_stakeholders: bool = True

@dataclass
class ModelEndpoint:
    """Model endpoint configuration."""
    name: str
    url: str
    model_version: str
    traffic_percentage: float
    status: ModelVersionStatus
    health_status: HealthStatus
    created_time: datetime
    last_health_check: datetime | None = None
    request_count: int = 0
    error_count: int = 0
    avg_response_time: float = 0.0

@dataclass
class DeploymentMetrics:
    """Deployment metrics."""
    deployment_id: str
    cpu_usage: float
    memory_usage: float
    request_rate: float
    error_rate: float
    response_time_p95: float
    uptime_percentage: float
    active_connections: int
    timestamp: datetime

# Main Classes
class DeploymentOrchestrator:
    """Orchestrates deployment operations."""

    def __init__(self, docker_client=None, k8s_client=None):
        self.docker = docker_client or MockDocker()
        self.k8s = k8s_client or MockKubernetes()
        self.logger = logging.getLogger(__name__)
        self.active_deployments = {}
        self.deployment_history = []

    async def deploy_model(self, config: DeploymentConfig) -> DeploymentResult:
        """Deploy a model using the specified strategy."""
        deployment_id = f"deploy_{int(time.time())}_{hash(config.model_name)}"
        start_time = datetime.now()

        result = DeploymentResult(
            deployment_id=deployment_id,
            config=config,
            status=DeploymentStatus.DEPLOYING,
            message="Deployment started",
            start_time=start_time
        )

        try:
            self.logger.info(f"Starting deployment {deployment_id} with strategy {config.strategy.value}")

            self.active_deployments[deployment_id] = result

            if config.strategy == DeploymentStrategy.BLUE_GREEN:
                await self._blue_green_deploy(config, result)
            elif config.strategy == DeploymentStrategy.CANARY:
                await self._canary_deploy(config, result)
            elif config.strategy == DeploymentStrategy.ROLLING:
                await self._rolling_deploy(config, result)
            elif config.strategy == DeploymentStrategy.RECREATE:
                await self._recreate_deploy(config, result)
            else:
                raise ValueError(f"Unsupported deployment strategy: {config.strategy}")

            result.status = DeploymentStatus.DEPLOYED
            result.message = "Deployment completed successfully"
            result.end_time = datetime.now()

            self.deployment_history.append(result)

            return result

        except Exception as e:
            self.logger.error(f"Deployment {deployment_id} failed: {str(e)}")
            result.status = DeploymentStatus.FAILED
            result.message = f"Deployment failed: {str(e)}"
            result.end_time = datetime.now()
            return result

    async def _blue_green_deploy(self, config: DeploymentConfig, result: DeploymentResult):
        """Execute blue-green deployment."""
        self.logger.info("Executing blue-green deployment")

        # Step 1: Build new image
        await asyncio.sleep(0.1)  # Simulate build time
        result.logs.append("Building new container image")

        # Step 2: Deploy green environment
        await asyncio.sleep(0.2)  # Simulate deployment time
        self.k8s.create_deployment(
            name=f"{config.model_name}-green",
            image=config.image_tag,
            replicas=config.replicas
        )
        result.logs.append("Green environment deployed")

        # Step 3: Health checks
        await asyncio.sleep(0.1)  # Simulate health check time
        result.logs.append("Health checks passed")

        # Step 4: Switch traffic
        await asyncio.sleep(0.05)  # Simulate traffic switch
        result.logs.append("Traffic switched to green environment")

        # Step 5: Remove blue environment
        await asyncio.sleep(0.05)  # Simulate cleanup
        result.logs.append("Blue environment removed")

        result.health_status = HealthStatus.HEALTHY

    async def _canary_deploy(self, config: DeploymentConfig, result: DeploymentResult):
        """Execute canary deployment."""
        self.logger.info(f"Executing canary deployment with {config.canary_percentage}% traffic")

        # Step 1: Deploy canary version
        await asyncio.sleep(0.1)
        canary_replicas = max(1, int(config.replicas * config.canary_percentage / 100))
        self.k8s.create_deployment(
            name=f"{config.model_name}-canary",
            image=config.image_tag,
            replicas=canary_replicas
        )
        result.logs.append(f"Canary deployment created with {canary_replicas} replicas")

        # Step 2: Monitor canary metrics
        await asyncio.sleep(0.2)  # Simulate monitoring period
        canary_success_rate = np.random.uniform(0.85, 0.99)  # Mock success rate
        result.metrics['canary_success_rate'] = canary_success_rate
        result.logs.append(f"Canary success rate: {canary_success_rate:.2%}")

        # Step 3: Decision based on metrics
        if canary_success_rate >= config.rollback_threshold / 100:
            # Promote canary
            await asyncio.sleep(0.1)
            self.k8s.update_deployment(
                name=config.model_name,
                image=config.image_tag,
                replicas=config.replicas
            )
            result.logs.append("Canary promoted to full deployment")
            result.health_status = HealthStatus.HEALTHY
        else:
            # Rollback canary
            self.k8s.delete_deployment(f"{config.model_name}-canary")
            result.logs.append("Canary rolled back due to poor performance")
            result.health_status = HealthStatus.DEGRADED
            raise Exception("Canary deployment failed performance thresholds")

    async def _rolling_deploy(self, config: DeploymentConfig, result: DeploymentResult):
        """Execute rolling deployment."""
        self.logger.info("Executing rolling deployment")

        # Simulate rolling update
        for i in range(config.replicas):
            await asyncio.sleep(0.1)
            result.logs.append(f"Updated replica {i+1}/{config.replicas}")

        result.logs.append("Rolling deployment completed")
        result.health_status = HealthStatus.HEALTHY

    async def _recreate_deploy(self, config: DeploymentConfig, result: DeploymentResult):
        """Execute recreate deployment."""
        self.logger.info("Executing recreate deployment")

        # Step 1: Stop existing deployment
        await asyncio.sleep(0.1)
        result.logs.append("Existing deployment stopped")

        # Step 2: Deploy new version
        await asyncio.sleep(0.2)
        self.k8s.create_deployment(
            name=config.model_name,
            image=config.image_tag,
            replicas=config.replicas
        )
        result.logs.append("New deployment created")

        result.health_status = HealthStatus.HEALTHY

    async def rollback_deployment(self, deployment_id: str, rollback_config: RollbackConfig) -> DeploymentResult:
        """Rollback a deployment."""
        try:
            self.logger.info(f"Rolling back deployment {deployment_id}")

            original_deployment = self.active_deployments.get(deployment_id)
            if not original_deployment:
                raise ValueError(f"Deployment {deployment_id} not found")

            # Create rollback deployment config
            rollback_deployment_config = DeploymentConfig(
                strategy=rollback_config.rollback_strategy,
                environment=original_deployment.config.environment,
                model_name=original_deployment.config.model_name,
                model_version=rollback_config.target_version,
                image_tag=f"{original_deployment.config.model_name}:{rollback_config.target_version}",
                replicas=original_deployment.config.replicas
            )

            # Execute rollback
            rollback_result = await self.deploy_model(rollback_deployment_config)
            rollback_result.rollback_version = rollback_config.target_version
            rollback_result.status = DeploymentStatus.ROLLED_BACK
            rollback_result.message = f"Rolled back to version {rollback_config.target_version}: {rollback_config.reason}"

            return rollback_result

        except Exception as e:
            self.logger.error(f"Rollback failed: {str(e)}")
            raise

    def get_deployment_status(self, deployment_id: str) -> DeploymentResult | None:
        """Get deployment status."""
        return self.active_deployments.get(deployment_id)

    def list_active_deployments(self) -> list[DeploymentResult]:
        """List all active deployments."""
        return list(self.active_deployments.values())

class HealthChecker:
    """Performs health checks on deployed models."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.health_history = []

    async def check_health(self, endpoint: str, timeout: float = 5.0) -> HealthCheckResult:
        """Perform health check on an endpoint."""
        start_time = time.time()

        try:
            # Mock HTTP request
            await asyncio.sleep(np.random.uniform(0.01, 0.1))  # Simulate request time

            # Mock response
            status_code = np.random.choice([200, 200, 200, 500], p=[0.95, 0.03, 0.01, 0.01])
            response_time = time.time() - start_time

            if status_code == 200:
                status = HealthStatus.HEALTHY
                message = "Service healthy"
            else:
                status = HealthStatus.UNHEALTHY
                message = f"Service unhealthy: HTTP {status_code}"

            result = HealthCheckResult(
                endpoint=endpoint,
                status=status,
                response_time=response_time,
                status_code=status_code,
                message=message,
                timestamp=datetime.now(),
                metrics={
                    'cpu_usage': np.random.uniform(10, 80),
                    'memory_usage': np.random.uniform(20, 90),
                    'disk_usage': np.random.uniform(5, 60)
                }
            )

            self.health_history.append(result)
            return result

        except Exception as e:
            self.logger.error(f"Health check failed for {endpoint}: {str(e)}")
            return HealthCheckResult(
                endpoint=endpoint,
                status=HealthStatus.UNKNOWN,
                response_time=timeout,
                status_code=0,
                message=f"Health check failed: {str(e)}",
                timestamp=datetime.now()
            )

    async def continuous_health_monitoring(self, endpoints: list[str], interval: int = 30) -> None:
        """Continuously monitor endpoint health."""
        self.logger.info(f"Starting continuous health monitoring for {len(endpoints)} endpoints")

        while True:
            for endpoint in endpoints:
                try:
                    await self.check_health(endpoint)
                except Exception as e:
                    self.logger.error(f"Health monitoring error for {endpoint}: {str(e)}")

            await asyncio.sleep(interval)

    def get_health_summary(self, endpoint: str, hours: int = 24) -> dict[str, Any]:
        """Get health summary for an endpoint."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_checks = [
            check for check in self.health_history
            if check.endpoint == endpoint and check.timestamp >= cutoff_time
        ]

        if not recent_checks:
            return {'status': 'no_data', 'message': 'No recent health check data'}

        healthy_count = sum(1 for check in recent_checks if check.status == HealthStatus.HEALTHY)
        total_count = len(recent_checks)
        uptime_percentage = (healthy_count / total_count) * 100

        avg_response_time = np.mean([check.response_time for check in recent_checks])

        return {
            'endpoint': endpoint,
            'uptime_percentage': uptime_percentage,
            'total_checks': total_count,
            'healthy_checks': healthy_count,
            'avg_response_time': avg_response_time,
            'last_check': recent_checks[-1].timestamp.isoformat(),
            'current_status': recent_checks[-1].status.value
        }

class ModelVersionManager:
    """Manages model versions and endpoints."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.endpoints = {}
        self.version_history = []

    def register_endpoint(self, endpoint: ModelEndpoint) -> None:
        """Register a model endpoint."""
        self.endpoints[endpoint.name] = endpoint
        self.logger.info(f"Registered endpoint {endpoint.name} for model version {endpoint.model_version}")

    def update_traffic_split(self, traffic_config: dict[str, float]) -> None:
        """Update traffic split between model versions."""
        total_percentage = sum(traffic_config.values())
        if abs(total_percentage - 100.0) > 0.1:
            raise ValueError(f"Traffic percentages must sum to 100%, got {total_percentage}")

        for endpoint_name, percentage in traffic_config.items():
            if endpoint_name in self.endpoints:
                self.endpoints[endpoint_name].traffic_percentage = percentage
                self.logger.info(f"Updated traffic for {endpoint_name} to {percentage}%")

    def promote_version(self, endpoint_name: str, new_version: str) -> None:
        """Promote a model version to active status."""
        if endpoint_name in self.endpoints:
            old_version = self.endpoints[endpoint_name].model_version
            self.endpoints[endpoint_name].model_version = new_version
            self.endpoints[endpoint_name].status = ModelVersionStatus.ACTIVE

            self.version_history.append({
                'endpoint': endpoint_name,
                'old_version': old_version,
                'new_version': new_version,
                'timestamp': datetime.now(),
                'action': 'promotion'
            })

            self.logger.info(f"Promoted {endpoint_name} from {old_version} to {new_version}")

    def deprecate_version(self, endpoint_name: str) -> None:
        """Deprecate a model version."""
        if endpoint_name in self.endpoints:
            self.endpoints[endpoint_name].status = ModelVersionStatus.DEPRECATED
            self.endpoints[endpoint_name].traffic_percentage = 0.0

            self.version_history.append({
                'endpoint': endpoint_name,
                'version': self.endpoints[endpoint_name].model_version,
                'timestamp': datetime.now(),
                'action': 'deprecation'
            })

            self.logger.info(f"Deprecated endpoint {endpoint_name}")

    def get_active_endpoints(self) -> list[ModelEndpoint]:
        """Get all active model endpoints."""
        return [
            endpoint for endpoint in self.endpoints.values()
            if endpoint.status == ModelVersionStatus.ACTIVE
        ]

    def get_endpoint_metrics(self, endpoint_name: str) -> dict[str, Any]:
        """Get metrics for a specific endpoint."""
        if endpoint_name not in self.endpoints:
            return {'error': 'Endpoint not found'}

        endpoint = self.endpoints[endpoint_name]
        return {
            'name': endpoint.name,
            'model_version': endpoint.model_version,
            'status': endpoint.status.value,
            'health_status': endpoint.health_status.value,
            'traffic_percentage': endpoint.traffic_percentage,
            'request_count': endpoint.request_count,
            'error_count': endpoint.error_count,
            'error_rate': (endpoint.error_count / max(endpoint.request_count, 1)) * 100,
            'avg_response_time': endpoint.avg_response_time,
            'uptime': (datetime.now() - endpoint.created_time).total_seconds()
        }

class DeploymentMonitor:
    """Monitors deployment metrics and performance."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.metrics_history = []
        self.alert_thresholds = {
            'cpu_usage': 80.0,
            'memory_usage': 85.0,
            'error_rate': 5.0,
            'response_time_p95': 2000.0  # milliseconds
        }

    async def collect_metrics(self, deployment_id: str) -> DeploymentMetrics:
        """Collect metrics for a deployment."""
        # Mock metrics collection
        metrics = DeploymentMetrics(
            deployment_id=deployment_id,
            cpu_usage=np.random.uniform(10, 90),
            memory_usage=np.random.uniform(20, 80),
            request_rate=np.random.uniform(100, 1000),
            error_rate=np.random.uniform(0, 10),
            response_time_p95=np.random.uniform(50, 500),
            uptime_percentage=np.random.uniform(95, 100),
            active_connections=np.random.randint(10, 100),
            timestamp=datetime.now()
        )

        self.metrics_history.append(metrics)
        await self._check_alerts(metrics)

        return metrics

    async def _check_alerts(self, metrics: DeploymentMetrics) -> None:
        """Check metrics against alert thresholds."""
        alerts = []

        if metrics.cpu_usage > self.alert_thresholds['cpu_usage']:
            alerts.append(f"High CPU usage: {metrics.cpu_usage:.1f}%")

        if metrics.memory_usage > self.alert_thresholds['memory_usage']:
            alerts.append(f"High memory usage: {metrics.memory_usage:.1f}%")

        if metrics.error_rate > self.alert_thresholds['error_rate']:
            alerts.append(f"High error rate: {metrics.error_rate:.1f}%")

        if metrics.response_time_p95 > self.alert_thresholds['response_time_p95']:
            alerts.append(f"High response time: {metrics.response_time_p95:.1f}ms")

        for alert in alerts:
            self.logger.warning(f"ALERT for {metrics.deployment_id}: {alert}")

    def get_metrics_summary(self, deployment_id: str, hours: int = 24) -> dict[str, Any]:
        """Get metrics summary for a deployment."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_metrics = [
            m for m in self.metrics_history
            if m.deployment_id == deployment_id and m.timestamp >= cutoff_time
        ]

        if not recent_metrics:
            return {'status': 'no_data', 'message': 'No recent metrics data'}

        return {
            'deployment_id': deployment_id,
            'period_hours': hours,
            'avg_cpu_usage': np.mean([m.cpu_usage for m in recent_metrics]),
            'avg_memory_usage': np.mean([m.memory_usage for m in recent_metrics]),
            'avg_request_rate': np.mean([m.request_rate for m in recent_metrics]),
            'avg_error_rate': np.mean([m.error_rate for m in recent_metrics]),
            'avg_response_time_p95': np.mean([m.response_time_p95 for m in recent_metrics]),
            'min_uptime': min([m.uptime_percentage for m in recent_metrics]),
            'max_connections': max([m.active_connections for m in recent_metrics]),
            'data_points': len(recent_metrics)
        }

    def set_alert_threshold(self, metric: str, threshold: float) -> None:
        """Set alert threshold for a metric."""
        if metric in self.alert_thresholds:
            self.alert_thresholds[metric] = threshold
            self.logger.info(f"Updated alert threshold for {metric} to {threshold}")

class DeploymentAutomation:
    """Automates deployment workflows."""

    def __init__(self, orchestrator: DeploymentOrchestrator,
                 health_checker: HealthChecker,
                 monitor: DeploymentMonitor):
        self.orchestrator = orchestrator
        self.health_checker = health_checker
        self.monitor = monitor
        self.logger = logging.getLogger(__name__)
        self.automation_rules = {}

    def add_automation_rule(self, name: str, condition: Callable, action: Callable) -> None:
        """Add an automation rule."""
        self.automation_rules[name] = {
            'condition': condition,
            'action': action,
            'created': datetime.now(),
            'triggered_count': 0
        }
        self.logger.info(f"Added automation rule: {name}")

    async def auto_scale_deployment(self, deployment_id: str, target_cpu: float = 70.0) -> None:
        """Automatically scale deployment based on CPU usage."""
        try:
            metrics = await self.monitor.collect_metrics(deployment_id)

            if metrics.cpu_usage > target_cpu * 1.2:  # Scale up
                self.logger.info(f"Auto-scaling up deployment {deployment_id} due to high CPU")
                # Mock scale up logic
                await asyncio.sleep(0.1)

            elif metrics.cpu_usage < target_cpu * 0.5:  # Scale down
                self.logger.info(f"Auto-scaling down deployment {deployment_id} due to low CPU")
                # Mock scale down logic
                await asyncio.sleep(0.1)

        except Exception as e:
            self.logger.error(f"Auto-scaling failed for {deployment_id}: {str(e)}")

    async def auto_rollback_on_failure(self, deployment_id: str, error_threshold: float = 10.0) -> None:
        """Automatically rollback deployment on high error rate."""
        try:
            metrics = await self.monitor.collect_metrics(deployment_id)

            if metrics.error_rate > error_threshold:
                self.logger.warning(f"Auto-rollback triggered for {deployment_id} due to high error rate")

                # Find previous stable version (mock)
                previous_version = "v1.0.0"  # In practice, would lookup from history

                rollback_config = RollbackConfig(
                    target_version=previous_version,
                    reason=f"Auto-rollback due to error rate {metrics.error_rate:.1f}%"
                )

                await self.orchestrator.rollback_deployment(deployment_id, rollback_config)

        except Exception as e:
            self.logger.error(f"Auto-rollback failed for {deployment_id}: {str(e)}")

    async def automated_deployment_pipeline(self, config: DeploymentConfig) -> DeploymentResult:
        """Execute fully automated deployment pipeline."""
        try:
            self.logger.info("Starting automated deployment pipeline")

            # Step 1: Deploy
            result = await self.orchestrator.deploy_model(config)

            if result.status != DeploymentStatus.DEPLOYED:
                raise Exception(f"Deployment failed: {result.message}")

            # Step 2: Health checks
            await asyncio.sleep(0.1)  # Wait for deployment to stabilize
            health_result = await self.health_checker.check_health(
                f"http://{config.model_name}.{config.environment.value}/health"
            )

            if health_result.status != HealthStatus.HEALTHY:
                raise Exception(f"Health check failed: {health_result.message}")

            # Step 3: Initial metrics collection
            await asyncio.sleep(0.1)
            metrics = await self.monitor.collect_metrics(result.deployment_id)

            # Step 4: Validation
            if metrics.error_rate > 5.0:  # Threshold check
                rollback_config = RollbackConfig(
                    target_version="previous",
                    reason="Initial validation failed"
                )
                await self.orchestrator.rollback_deployment(result.deployment_id, rollback_config)
                raise Exception("Deployment failed validation checks")

            self.logger.info("Automated deployment pipeline completed successfully")
            return result

        except Exception as e:
            self.logger.error(f"Automated deployment pipeline failed: {str(e)}")
            raise

# Main MLOps Deployment Service
class MLOpsDeploymentService:
    """Main MLOps deployment service orchestrating all components."""

    def __init__(self):
        self.orchestrator = DeploymentOrchestrator()
        self.health_checker = HealthChecker()
        self.version_manager = ModelVersionManager()
        self.monitor = DeploymentMonitor()
        self.automation = DeploymentAutomation(
            self.orchestrator, self.health_checker, self.monitor
        )
        self.logger = logging.getLogger(__name__)

    async def deploy_model_with_strategy(self, config: DeploymentConfig) -> DeploymentResult:
        """Deploy model with comprehensive monitoring and automation."""
        try:
            self.logger.info(f"Deploying model {config.model_name} v{config.model_version}")

            # Execute deployment
            result = await self.orchestrator.deploy_model(config)

            # Register endpoint
            endpoint = ModelEndpoint(
                name=f"{config.model_name}-{config.environment.value}",
                url=f"http://{config.model_name}.{config.environment.value}",
                model_version=config.model_version,
                traffic_percentage=100.0,
                status=ModelVersionStatus.ACTIVE,
                health_status=HealthStatus.HEALTHY,
                created_time=datetime.now()
            )
            self.version_manager.register_endpoint(endpoint)

            # Start monitoring
            asyncio.create_task(self._start_monitoring(result.deployment_id))

            return result

        except Exception as e:
            self.logger.error(f"Model deployment failed: {str(e)}")
            raise

    async def _start_monitoring(self, deployment_id: str) -> None:
        """Start monitoring for a deployment."""
        try:
            while True:
                await self.monitor.collect_metrics(deployment_id)
                await asyncio.sleep(30)  # Monitor every 30 seconds
        except Exception as e:
            self.logger.error(f"Monitoring failed for {deployment_id}: {str(e)}")

    async def blue_green_deployment(self, config: DeploymentConfig) -> DeploymentResult:
        """Execute blue-green deployment with comprehensive checks."""
        config.strategy = DeploymentStrategy.BLUE_GREEN
        return await self.deploy_model_with_strategy(config)

    async def canary_deployment(self, config: DeploymentConfig,
                              canary_percentage: float = 10.0) -> DeploymentResult:
        """Execute canary deployment with gradual rollout."""
        config.strategy = DeploymentStrategy.CANARY
        config.canary_percentage = canary_percentage
        return await self.deploy_model_with_strategy(config)

    async def perform_rollback(self, deployment_id: str, target_version: str,
                             reason: str = "Manual rollback") -> DeploymentResult:
        """Perform deployment rollback."""
        rollback_config = RollbackConfig(
            target_version=target_version,
            reason=reason
        )
        return await self.orchestrator.rollback_deployment(deployment_id, rollback_config)

    def get_deployment_dashboard(self) -> dict[str, Any]:
        """Get comprehensive deployment dashboard data."""
        active_deployments = self.orchestrator.list_active_deployments()
        active_endpoints = self.version_manager.get_active_endpoints()

        return {
            'summary': {
                'total_deployments': len(active_deployments),
                'active_endpoints': len(active_endpoints),
                'healthy_endpoints': len([e for e in active_endpoints
                                        if e.health_status == HealthStatus.HEALTHY]),
                'timestamp': datetime.now().isoformat()
            },
            'deployments': [
                {
                    'deployment_id': d.deployment_id,
                    'model_name': d.config.model_name,
                    'version': d.config.model_version,
                    'environment': d.config.environment.value,
                    'status': d.status.value,
                    'health_status': d.health_status.value,
                    'start_time': d.start_time.isoformat()
                }
                for d in active_deployments
            ],
            'endpoints': [
                {
                    'name': e.name,
                    'model_version': e.model_version,
                    'traffic_percentage': e.traffic_percentage,
                    'status': e.status.value,
                    'health_status': e.health_status.value,
                    'request_count': e.request_count,
                    'error_count': e.error_count
                }
                for e in active_endpoints
            ]
        }

# Convenience functions
def create_deployment_service() -> MLOpsDeploymentService:
    """Create MLOps deployment service instance."""
    return MLOpsDeploymentService()

def create_deployment_config(model_name: str, model_version: str,
                           environment: Environment = Environment.STAGING,
                           strategy: DeploymentStrategy = DeploymentStrategy.ROLLING) -> DeploymentConfig:
    """Create deployment configuration with defaults."""
    return DeploymentConfig(
        strategy=strategy,
        environment=environment,
        model_name=model_name,
        model_version=model_version,
        image_tag=f"{model_name}:{model_version}"
    )

# Export main classes and functions
__all__ = [
    'MLOpsDeploymentService', 'DeploymentOrchestrator', 'HealthChecker',
    'ModelVersionManager', 'DeploymentMonitor', 'DeploymentAutomation',
    'DeploymentConfig', 'DeploymentResult', 'HealthCheckResult', 'RollbackConfig',
    'ModelEndpoint', 'DeploymentMetrics', 'DeploymentStrategy', 'DeploymentStatus',
    'HealthStatus', 'Environment', 'ModelVersionStatus', 'create_deployment_service',
    'create_deployment_config'
]
