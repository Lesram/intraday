"""
Comprehensive test suite for Module 61: backend.mlops.deployment
Tests MLOps deployment functionality including deployment strategies, blue-green deployment,
canary deployment, rollback management, monitoring, health checks, and automation.
"""

import pytest
import asyncio
import numpy as np
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

try:
    from backend.mlops.deployment import (
        MLOpsDeploymentService, DeploymentOrchestrator, HealthChecker,
        ModelVersionManager, DeploymentMonitor, DeploymentAutomation,
        DeploymentConfig, DeploymentResult, HealthCheckResult, RollbackConfig,
        ModelEndpoint, DeploymentMetrics, DeploymentStrategy, DeploymentStatus,
        HealthStatus, Environment, ModelVersionStatus, create_deployment_service,
        create_deployment_config, MockDocker, MockKubernetes
    )
    MODULE_EXISTS = True
except ImportError:
    MODULE_EXISTS = False


@pytest.mark.asyncio
class TestModule61BackendMlopsDeployment:
    """Comprehensive test suite for MLOps deployment functionality."""

    @pytest.fixture
    def deployment_config(self):
        """Create sample deployment configuration."""
        return DeploymentConfig(
            strategy=DeploymentStrategy.ROLLING,
            environment=Environment.STAGING,
            model_name="test_model",
            model_version="v1.0.0",
            image_tag="test_model:v1.0.0",
            replicas=3
        )

    @pytest.fixture
    def mock_orchestrator(self):
        """Create deployment orchestrator with mock clients."""
        return DeploymentOrchestrator(
            docker_client=MockDocker(),
            k8s_client=MockKubernetes()
        )

    @pytest.fixture
    def sample_endpoint(self):
        """Create sample model endpoint."""
        return ModelEndpoint(
            name="test-endpoint",
            url="http://test-model.staging",
            model_version="v1.0.0",
            traffic_percentage=100.0,
            status=ModelVersionStatus.ACTIVE,
            health_status=HealthStatus.HEALTHY,
            created_time=datetime.now()
        )

    def test_module_availability(self):
        """Test module availability."""
        if MODULE_EXISTS:
            import backend.mlops.deployment as module
            assert module is not None
            assert hasattr(module, 'MLOpsDeploymentService')
            assert hasattr(module, 'DeploymentOrchestrator')
            assert hasattr(module, 'HealthChecker')
        else:
            pytest.skip("Module not available")

    def test_deployment_config_creation(self):
        """Test DeploymentConfig creation and defaults."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        config = DeploymentConfig(
            strategy=DeploymentStrategy.BLUE_GREEN,
            environment=Environment.PRODUCTION,
            model_name="test_model",
            model_version="v2.0.0",
            image_tag="test_model:v2.0.0"
        )
        
        assert config.strategy == DeploymentStrategy.BLUE_GREEN
        assert config.environment == Environment.PRODUCTION
        assert config.model_name == "test_model"
        assert config.replicas == 3  # Default value
        assert config.auto_rollback is True  # Default value

    def test_deployment_result_creation(self):
        """Test DeploymentResult creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        config = DeploymentConfig(
            strategy=DeploymentStrategy.CANARY,
            environment=Environment.STAGING,
            model_name="test",
            model_version="v1.0",
            image_tag="test:v1.0"
        )
        
        result = DeploymentResult(
            deployment_id="test_123",
            config=config,
            status=DeploymentStatus.DEPLOYED,
            message="Deployment successful",
            start_time=datetime.now()
        )
        
        assert result.deployment_id == "test_123"
        assert result.status == DeploymentStatus.DEPLOYED
        assert result.config == config

    def test_mock_docker_operations(self):
        """Test mock Docker client operations."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        docker = MockDocker()
        
        # Test build
        build_result = docker.build("/path/to/code", "test:v1.0")
        assert 'Id' in build_result
        assert "test:v1.0" in docker.images
        
        # Test run
        run_result = docker.run("test:v1.0", name="test-container")
        assert 'Id' in run_result
        container_id = run_result['Id']
        assert container_id in docker.containers
        
        # Test stop and remove
        docker.stop(container_id)
        assert docker.containers[container_id]['status'] == 'stopped'
        
        docker.remove(container_id)
        assert container_id not in docker.containers

    def test_mock_kubernetes_operations(self):
        """Test mock Kubernetes client operations."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        k8s = MockKubernetes()
        
        # Test create deployment
        deployment = k8s.create_deployment("test-deploy", "test:v1.0", replicas=2)
        assert deployment['name'] == "test-deploy"
        assert deployment['replicas'] == 2
        assert "test-deploy" in k8s.deployments
        
        # Test update deployment
        updated = k8s.update_deployment("test-deploy", replicas=5)
        assert updated['replicas'] == 5
        
        # Test create service
        service = k8s.create_service("test-service", "test-deploy")
        assert service['name'] == "test-service"
        
        # Test delete deployment
        k8s.delete_deployment("test-deploy")
        assert "test-deploy" not in k8s.deployments

    async def test_deployment_orchestrator_creation(self, mock_orchestrator):
        """Test DeploymentOrchestrator creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        assert mock_orchestrator.docker is not None
        assert mock_orchestrator.k8s is not None
        assert mock_orchestrator.active_deployments == {}
        assert mock_orchestrator.deployment_history == []

    async def test_blue_green_deployment(self, mock_orchestrator, deployment_config):
        """Test blue-green deployment strategy."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        deployment_config.strategy = DeploymentStrategy.BLUE_GREEN
        
        result = await mock_orchestrator.deploy_model(deployment_config)
        
        assert isinstance(result, DeploymentResult)
        assert result.config.strategy == DeploymentStrategy.BLUE_GREEN
        assert result.status == DeploymentStatus.DEPLOYED
        assert len(result.logs) > 0
        assert "Green environment deployed" in result.logs
        assert "Blue environment removed" in result.logs
        assert result.health_status == HealthStatus.HEALTHY

    async def test_canary_deployment(self, mock_orchestrator, deployment_config):
        """Test canary deployment strategy."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        deployment_config.strategy = DeploymentStrategy.CANARY
        deployment_config.canary_percentage = 20.0
        
        result = await mock_orchestrator.deploy_model(deployment_config)
        
        assert isinstance(result, DeploymentResult)
        assert result.config.strategy == DeploymentStrategy.CANARY
        # Canary deployments can either succeed or fail based on performance thresholds
        assert result.status in [DeploymentStatus.DEPLOYED, DeploymentStatus.FAILED]
        assert 'canary_success_rate' in result.metrics
        assert any("Canary deployment created" in log for log in result.logs)

    async def test_rolling_deployment(self, mock_orchestrator, deployment_config):
        """Test rolling deployment strategy."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        deployment_config.strategy = DeploymentStrategy.ROLLING
        
        result = await mock_orchestrator.deploy_model(deployment_config)
        
        assert isinstance(result, DeploymentResult)
        assert result.config.strategy == DeploymentStrategy.ROLLING
        assert result.status == DeploymentStatus.DEPLOYED
        assert "Rolling deployment completed" in result.logs

    async def test_recreate_deployment(self, mock_orchestrator, deployment_config):
        """Test recreate deployment strategy."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        deployment_config.strategy = DeploymentStrategy.RECREATE
        
        result = await mock_orchestrator.deploy_model(deployment_config)
        
        assert isinstance(result, DeploymentResult)
        assert result.config.strategy == DeploymentStrategy.RECREATE
        assert result.status == DeploymentStatus.DEPLOYED
        assert "Existing deployment stopped" in result.logs
        assert "New deployment created" in result.logs

    async def test_deployment_rollback(self, mock_orchestrator, deployment_config):
        """Test deployment rollback functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        # First deploy
        result = await mock_orchestrator.deploy_model(deployment_config)
        deployment_id = result.deployment_id
        
        # Rollback
        rollback_config = RollbackConfig(
            target_version="v0.9.0",
            reason="Critical bug found"
        )
        
        rollback_result = await mock_orchestrator.rollback_deployment(deployment_id, rollback_config)
        
        assert isinstance(rollback_result, DeploymentResult)
        assert rollback_result.status == DeploymentStatus.ROLLED_BACK
        assert rollback_result.rollback_version == "v0.9.0"
        assert "Critical bug found" in rollback_result.message

    async def test_deployment_error_handling(self, mock_orchestrator):
        """Test deployment error handling."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        # Create invalid config
        invalid_config = DeploymentConfig(
            strategy=DeploymentStrategy.ROLLING,  # Use valid enum but trigger error differently
            environment=Environment.STAGING,
            model_name="test",
            model_version="v1.0",
            image_tag="test:v1.0"
        )
        
        # Mock a failure by using invalid strategy string
        invalid_config.strategy = "INVALID_STRATEGY"  # Overwrite with invalid value after creation
        
        result = await mock_orchestrator.deploy_model(invalid_config)
        
        assert result.status == DeploymentStatus.FAILED
        assert result.message is not None

    async def test_health_checker_creation(self):
        """Test HealthChecker creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        health_checker = HealthChecker()
        assert health_checker is not None
        assert health_checker.health_history == []

    async def test_health_check_execution(self):
        """Test health check execution."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        health_checker = HealthChecker()
        
        result = await health_checker.check_health("http://test-service/health")
        
        assert isinstance(result, HealthCheckResult)
        assert result.endpoint == "http://test-service/health"
        assert result.status in [HealthStatus.HEALTHY, HealthStatus.UNHEALTHY]
        assert result.response_time > 0
        assert len(health_checker.health_history) == 1

    async def test_health_summary(self):
        """Test health summary generation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        health_checker = HealthChecker()
        endpoint = "http://test-service/health"
        
        # Generate some health check history
        for _ in range(5):
            await health_checker.check_health(endpoint)
        
        summary = health_checker.get_health_summary(endpoint)
        
        assert 'endpoint' in summary
        assert 'uptime_percentage' in summary
        assert 'total_checks' in summary
        assert summary['total_checks'] == 5

    def test_model_version_manager_creation(self):
        """Test ModelVersionManager creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        manager = ModelVersionManager()
        assert manager is not None
        assert manager.endpoints == {}
        assert manager.version_history == []

    def test_endpoint_registration(self, sample_endpoint):
        """Test endpoint registration."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        manager = ModelVersionManager()
        manager.register_endpoint(sample_endpoint)
        
        assert sample_endpoint.name in manager.endpoints
        assert manager.endpoints[sample_endpoint.name] == sample_endpoint

    def test_traffic_split_update(self, sample_endpoint):
        """Test traffic split updates."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        manager = ModelVersionManager()
        manager.register_endpoint(sample_endpoint)
        
        # Test valid traffic split
        traffic_config = {sample_endpoint.name: 80.0}
        # Add another endpoint to make it sum to 100%
        endpoint2 = ModelEndpoint(
            name="test-endpoint-2",
            url="http://test-model-2.staging",
            model_version="v2.0.0",
            traffic_percentage=20.0,
            status=ModelVersionStatus.ACTIVE,
            health_status=HealthStatus.HEALTHY,
            created_time=datetime.now()
        )
        manager.register_endpoint(endpoint2)
        traffic_config["test-endpoint-2"] = 20.0
        
        manager.update_traffic_split(traffic_config)
        
        assert manager.endpoints[sample_endpoint.name].traffic_percentage == 80.0
        assert manager.endpoints["test-endpoint-2"].traffic_percentage == 20.0

    def test_version_promotion(self, sample_endpoint):
        """Test model version promotion."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        manager = ModelVersionManager()
        manager.register_endpoint(sample_endpoint)
        
        manager.promote_version(sample_endpoint.name, "v2.0.0")
        
        assert manager.endpoints[sample_endpoint.name].model_version == "v2.0.0"
        assert len(manager.version_history) == 1
        assert manager.version_history[0]['action'] == 'promotion'

    def test_version_deprecation(self, sample_endpoint):
        """Test model version deprecation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        manager = ModelVersionManager()
        manager.register_endpoint(sample_endpoint)
        
        manager.deprecate_version(sample_endpoint.name)
        
        assert manager.endpoints[sample_endpoint.name].status == ModelVersionStatus.DEPRECATED
        assert manager.endpoints[sample_endpoint.name].traffic_percentage == 0.0
        assert len(manager.version_history) == 1

    def test_endpoint_metrics(self, sample_endpoint):
        """Test endpoint metrics retrieval."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        manager = ModelVersionManager()
        sample_endpoint.request_count = 1000
        sample_endpoint.error_count = 25
        manager.register_endpoint(sample_endpoint)
        
        metrics = manager.get_endpoint_metrics(sample_endpoint.name)
        
        assert metrics['name'] == sample_endpoint.name
        assert metrics['request_count'] == 1000
        assert metrics['error_count'] == 25
        assert metrics['error_rate'] == 2.5  # 25/1000 * 100

    async def test_deployment_monitor_creation(self):
        """Test DeploymentMonitor creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        monitor = DeploymentMonitor()
        assert monitor is not None
        assert monitor.metrics_history == []
        assert 'cpu_usage' in monitor.alert_thresholds

    async def test_metrics_collection(self):
        """Test metrics collection."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        monitor = DeploymentMonitor()
        
        metrics = await monitor.collect_metrics("test_deployment")
        
        assert isinstance(metrics, DeploymentMetrics)
        assert metrics.deployment_id == "test_deployment"
        assert 0 <= metrics.cpu_usage <= 100
        assert 0 <= metrics.memory_usage <= 100
        assert len(monitor.metrics_history) == 1

    async def test_metrics_summary(self):
        """Test metrics summary generation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        monitor = DeploymentMonitor()
        deployment_id = "test_deployment"
        
        # Collect some metrics
        for _ in range(3):
            await monitor.collect_metrics(deployment_id)
        
        summary = monitor.get_metrics_summary(deployment_id)
        
        assert summary['deployment_id'] == deployment_id
        assert 'avg_cpu_usage' in summary
        assert 'avg_memory_usage' in summary
        assert summary['data_points'] == 3

    def test_alert_threshold_setting(self):
        """Test alert threshold configuration."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        monitor = DeploymentMonitor()
        
        monitor.set_alert_threshold('cpu_usage', 90.0)
        
        assert monitor.alert_thresholds['cpu_usage'] == 90.0

    async def test_deployment_automation_creation(self):
        """Test DeploymentAutomation creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        orchestrator = DeploymentOrchestrator()
        health_checker = HealthChecker()
        monitor = DeploymentMonitor()
        
        automation = DeploymentAutomation(orchestrator, health_checker, monitor)
        
        assert automation.orchestrator == orchestrator
        assert automation.health_checker == health_checker
        assert automation.monitor == monitor
        assert automation.automation_rules == {}

    async def test_automation_rule_addition(self):
        """Test automation rule addition."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        orchestrator = DeploymentOrchestrator()
        health_checker = HealthChecker()
        monitor = DeploymentMonitor()
        automation = DeploymentAutomation(orchestrator, health_checker, monitor)
        
        def test_condition():
            return True
        
        def test_action():
            pass
        
        automation.add_automation_rule("test_rule", test_condition, test_action)
        
        assert "test_rule" in automation.automation_rules
        assert automation.automation_rules["test_rule"]["condition"] == test_condition

    async def test_auto_scaling(self):
        """Test auto-scaling functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        orchestrator = DeploymentOrchestrator()
        health_checker = HealthChecker()
        monitor = DeploymentMonitor()
        automation = DeploymentAutomation(orchestrator, health_checker, monitor)
        
        # This will trigger metrics collection and potentially scaling
        await automation.auto_scale_deployment("test_deployment")
        
        # Test should complete without errors
        assert True

    async def test_auto_rollback(self):
        """Test auto-rollback functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        orchestrator = DeploymentOrchestrator()
        health_checker = HealthChecker()
        monitor = DeploymentMonitor()
        automation = DeploymentAutomation(orchestrator, health_checker, monitor)
        
        # This will trigger metrics collection and potentially rollback
        await automation.auto_rollback_on_failure("test_deployment")
        
        # Test should complete without errors
        assert True

    async def test_automated_pipeline(self, deployment_config):
        """Test automated deployment pipeline."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        orchestrator = DeploymentOrchestrator()
        health_checker = HealthChecker()
        monitor = DeploymentMonitor()
        automation = DeploymentAutomation(orchestrator, health_checker, monitor)
        
        result = await automation.automated_deployment_pipeline(deployment_config)
        
        assert isinstance(result, DeploymentResult)
        assert result.status == DeploymentStatus.DEPLOYED

    async def test_mlops_deployment_service_creation(self):
        """Test MLOpsDeploymentService creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = MLOpsDeploymentService()
        
        assert service.orchestrator is not None
        assert service.health_checker is not None
        assert service.version_manager is not None
        assert service.monitor is not None
        assert service.automation is not None

    async def test_model_deployment_with_strategy(self, deployment_config):
        """Test model deployment with comprehensive monitoring."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = MLOpsDeploymentService()
        
        result = await service.deploy_model_with_strategy(deployment_config)
        
        assert isinstance(result, DeploymentResult)
        assert result.status == DeploymentStatus.DEPLOYED
        
        # Check that endpoint was registered
        active_endpoints = service.version_manager.get_active_endpoints()
        assert len(active_endpoints) > 0

    async def test_blue_green_service_deployment(self, deployment_config):
        """Test blue-green deployment through service."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = MLOpsDeploymentService()
        
        result = await service.blue_green_deployment(deployment_config)
        
        assert isinstance(result, DeploymentResult)
        assert result.config.strategy == DeploymentStrategy.BLUE_GREEN

    async def test_canary_service_deployment(self, deployment_config):
        """Test canary deployment through service."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = MLOpsDeploymentService()
        
        result = await service.canary_deployment(deployment_config, canary_percentage=15.0)
        
        assert isinstance(result, DeploymentResult)
        assert result.config.strategy == DeploymentStrategy.CANARY
        assert result.config.canary_percentage == 15.0

    async def test_service_rollback(self, deployment_config):
        """Test rollback through service."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = MLOpsDeploymentService()
        
        # First deploy
        result = await service.deploy_model_with_strategy(deployment_config)
        
        # Then rollback
        rollback_result = await service.perform_rollback(
            result.deployment_id, 
            "v0.9.0", 
            "Testing rollback"
        )
        
        assert isinstance(rollback_result, DeploymentResult)
        assert rollback_result.status == DeploymentStatus.ROLLED_BACK

    def test_deployment_dashboard(self):
        """Test deployment dashboard data."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = MLOpsDeploymentService()
        
        dashboard = service.get_deployment_dashboard()
        
        assert 'summary' in dashboard
        assert 'deployments' in dashboard
        assert 'endpoints' in dashboard
        assert 'total_deployments' in dashboard['summary']
        assert 'timestamp' in dashboard['summary']

    def test_convenience_functions(self):
        """Test convenience functions."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        # Test create_deployment_service
        service = create_deployment_service()
        assert isinstance(service, MLOpsDeploymentService)
        
        # Test create_deployment_config
        config = create_deployment_config(
            "test_model", 
            "v1.0.0", 
            Environment.PRODUCTION,
            DeploymentStrategy.CANARY
        )
        assert isinstance(config, DeploymentConfig)
        assert config.model_name == "test_model"
        assert config.environment == Environment.PRODUCTION

    def test_enum_values(self):
        """Test enum values and types."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        # Test DeploymentStrategy enum
        assert DeploymentStrategy.BLUE_GREEN.value == "blue_green"
        assert DeploymentStrategy.CANARY.value == "canary"
        assert DeploymentStrategy.ROLLING.value == "rolling"
        
        # Test DeploymentStatus enum
        assert DeploymentStatus.PENDING.value == "pending"
        assert DeploymentStatus.DEPLOYED.value == "deployed"
        assert DeploymentStatus.FAILED.value == "failed"
        
        # Test HealthStatus enum
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        
        # Test Environment enum
        assert Environment.DEVELOPMENT.value == "development"
        assert Environment.STAGING.value == "staging"
        assert Environment.PRODUCTION.value == "production"

    async def test_edge_cases_and_error_handling(self):
        """Test edge cases and error handling."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = MLOpsDeploymentService()
        
        # Test rollback of non-existent deployment
        try:
            await service.perform_rollback("non_existent", "v1.0.0")
        except Exception as e:
            assert "not found" in str(e).lower()
        
        # Test invalid traffic split
        manager = ModelVersionManager()
        try:
            manager.update_traffic_split({"endpoint1": 60.0, "endpoint2": 50.0})  # Sums to 110%
        except ValueError as e:
            assert "100%" in str(e)

    def test_health_check_result_creation(self):
        """Test HealthCheckResult creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        result = HealthCheckResult(
            endpoint="http://test/health",
            status=HealthStatus.HEALTHY,
            response_time=0.125,
            status_code=200,
            message="OK",
            timestamp=datetime.now()
        )
        
        assert result.endpoint == "http://test/health"
        assert result.status == HealthStatus.HEALTHY
        assert result.response_time == 0.125

    def test_deployment_metrics_creation(self):
        """Test DeploymentMetrics creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        metrics = DeploymentMetrics(
            deployment_id="test_deploy",
            cpu_usage=45.5,
            memory_usage=62.3,
            request_rate=150.0,
            error_rate=1.2,
            response_time_p95=245.0,
            uptime_percentage=99.9,
            active_connections=42,
            timestamp=datetime.now()
        )
        
        assert metrics.deployment_id == "test_deploy"
        assert metrics.cpu_usage == 45.5
        assert metrics.error_rate == 1.2

    def test_module_exports(self):
        """Test that all expected symbols are exported."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        import backend.mlops.deployment as module
        
        expected_exports = [
            'MLOpsDeploymentService', 'DeploymentOrchestrator', 'HealthChecker',
            'ModelVersionManager', 'DeploymentMonitor', 'DeploymentAutomation',
            'DeploymentConfig', 'DeploymentResult', 'HealthCheckResult', 'RollbackConfig',
            'ModelEndpoint', 'DeploymentMetrics', 'DeploymentStrategy', 'DeploymentStatus',
            'HealthStatus', 'Environment', 'ModelVersionStatus', 'create_deployment_service',
            'create_deployment_config'
        ]
        
        for export in expected_exports:
            assert hasattr(module, export), f"Missing export: {export}"