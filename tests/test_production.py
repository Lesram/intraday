"""
Tests for Production Deployment Readiness Infrastructure.

Tests:
- Health check registry
- Graceful shutdown handling
- Configuration validation
- Feature flags
- Deployment info
- Production readiness orchestration
"""

import asyncio
import os
import pytest
from datetime import datetime, UTC
from unittest.mock import patch, AsyncMock, MagicMock

from backend.infra.production import (
    HealthStatus,
    ReadinessStatus,
    HealthCheckResult,
    SystemHealth,
    HealthCheckRegistry,
    GracefulShutdown,
    ConfigValidationError,
    ConfigValidator,
    FeatureFlags,
    DeploymentInfo,
    ProductionReadiness,
    get_production_readiness,
)


class TestHealthStatus:
    """Tests for HealthStatus enum."""
    
    def test_health_status_values(self):
        """Test health status enum values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"
    
    def test_readiness_status_values(self):
        """Test readiness status enum values."""
        assert ReadinessStatus.READY.value == "ready"
        assert ReadinessStatus.NOT_READY.value == "not_ready"
        assert ReadinessStatus.STARTING.value == "starting"
        assert ReadinessStatus.STOPPING.value == "stopping"


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""
    
    def test_health_check_result_creation(self):
        """Test creating a health check result."""
        result = HealthCheckResult(
            component="database",
            status=HealthStatus.HEALTHY,
            latency_ms=5.2,
            message="OK",
        )
        
        assert result.component == "database"
        assert result.status == HealthStatus.HEALTHY
        assert result.latency_ms == 5.2
        assert result.message == "OK"
        assert isinstance(result.timestamp, datetime)
    
    def test_health_check_result_with_details(self):
        """Test health check result with extra details."""
        result = HealthCheckResult(
            component="cache",
            status=HealthStatus.HEALTHY,
            latency_ms=0.5,
            details={"connections": 10, "memory_mb": 256},
        )
        
        assert result.details["connections"] == 10
        assert result.details["memory_mb"] == 256


class TestHealthCheckRegistry:
    """Tests for HealthCheckRegistry."""
    
    @pytest.fixture
    def registry(self):
        """Create a fresh registry for each test."""
        return HealthCheckRegistry()
    
    def test_register_sync_check(self, registry):
        """Test registering a synchronous health check."""
        @registry.register("test_sync", critical=True)
        def check():
            return {"status": "ok"}
        
        assert "test_sync" in registry._checks
        assert registry._checks["test_sync"]["critical"] is True
    
    def test_register_async_check(self, registry):
        """Test registering an async health check."""
        @registry.register("test_async", timeout_seconds=10)
        async def check():
            return {"status": "ok"}
        
        assert "test_async" in registry._checks
        assert registry._checks["test_async"]["timeout"] == 10
    
    @pytest.mark.asyncio
    async def test_run_check_healthy(self, registry):
        """Test running a healthy check."""
        @registry.register("healthy")
        async def check():
            return {"connections": 5}
        
        result = await registry.run_check("healthy")
        
        assert result.component == "healthy"
        assert result.status == HealthStatus.HEALTHY
        assert result.latency_ms >= 0
        assert result.details["connections"] == 5
    
    @pytest.mark.asyncio
    async def test_run_check_unhealthy(self, registry):
        """Test running an unhealthy check."""
        @registry.register("unhealthy")
        async def check():
            raise ConnectionError("Database unavailable")
        
        result = await registry.run_check("unhealthy")
        
        assert result.component == "unhealthy"
        assert result.status == HealthStatus.UNHEALTHY
        assert "Database unavailable" in result.message
    
    @pytest.mark.asyncio
    async def test_run_check_timeout(self, registry):
        """Test check that times out."""
        @registry.register("slow", timeout_seconds=0.1)
        async def check():
            await asyncio.sleep(1)
            return {}
        
        result = await registry.run_check("slow")
        
        assert result.status == HealthStatus.UNHEALTHY
        assert "Timeout" in result.message
    
    @pytest.mark.asyncio
    async def test_run_check_unknown(self, registry):
        """Test running an unregistered check."""
        result = await registry.run_check("nonexistent")
        
        assert result.status == HealthStatus.UNKNOWN
        assert "not registered" in result.message
    
    @pytest.mark.asyncio
    async def test_run_check_with_cache(self, registry):
        """Test check result caching."""
        call_count = 0
        
        @registry.register("cached", cache_seconds=60)
        async def check():
            nonlocal call_count
            call_count += 1
            return {"calls": call_count}
        
        # First call
        result1 = await registry.run_check("cached")
        # Second call (should be cached)
        result2 = await registry.run_check("cached")
        
        assert call_count == 1
        assert result1.details["calls"] == result2.details["calls"]
    
    @pytest.mark.asyncio
    async def test_run_all_checks(self, registry):
        """Test running all registered checks."""
        @registry.register("check1")
        async def check1():
            return {"id": 1}
        
        @registry.register("check2")
        async def check2():
            return {"id": 2}
        
        results = await registry.run_all()
        
        assert len(results) == 2
        assert "check1" in results
        assert "check2" in results
    
    def test_get_critical_checks(self, registry):
        """Test getting critical checks."""
        @registry.register("critical1", critical=True)
        def check1():
            return {}
        
        @registry.register("noncritical", critical=False)
        def check2():
            return {}
        
        @registry.register("critical2", critical=True)
        def check3():
            return {}
        
        critical = registry.get_critical_checks()
        
        assert len(critical) == 2
        assert "critical1" in critical
        assert "critical2" in critical
        assert "noncritical" not in critical
    
    @pytest.mark.asyncio
    async def test_is_healthy(self, registry):
        """Test overall health determination."""
        @registry.register("db", critical=True)
        async def check_db():
            return {}
        
        @registry.register("cache", critical=False)
        async def check_cache():
            return {}
        
        await registry.run_all()
        
        assert registry.is_healthy() is True
    
    @pytest.mark.asyncio
    async def test_is_healthy_critical_failure(self, registry):
        """Test health with critical failure."""
        @registry.register("db", critical=True)
        async def check_db():
            raise Exception("DB down")
        
        await registry.run_all()
        
        assert registry.is_healthy() is False


class TestGracefulShutdown:
    """Tests for GracefulShutdown."""
    
    @pytest.fixture
    def shutdown(self):
        """Create a fresh shutdown handler."""
        return GracefulShutdown(timeout_seconds=5)
    
    def test_initial_state(self, shutdown):
        """Test initial shutdown state."""
        assert shutdown.is_shutting_down is False
    
    def test_register_callback_decorator(self, shutdown):
        """Test registering callback with decorator."""
        @shutdown.on_shutdown
        def cleanup():
            pass
        
        assert len(shutdown._callbacks) == 1
    
    def test_register_callback_method(self, shutdown):
        """Test registering callback with method."""
        def cleanup():
            pass
        
        shutdown.register_callback(cleanup)
        
        assert len(shutdown._callbacks) == 1
    
    @pytest.mark.asyncio
    async def test_shutdown_runs_callbacks(self, shutdown):
        """Test shutdown runs all callbacks."""
        results = []
        
        @shutdown.on_shutdown
        async def cleanup1():
            results.append(1)
        
        @shutdown.on_shutdown
        async def cleanup2():
            results.append(2)
        
        await shutdown.shutdown()
        
        assert shutdown.is_shutting_down is True
        assert 1 in results
        assert 2 in results
    
    @pytest.mark.asyncio
    async def test_shutdown_reverse_order(self, shutdown):
        """Test callbacks run in reverse order (LIFO)."""
        order = []
        
        @shutdown.on_shutdown
        def first():
            order.append("first")
        
        @shutdown.on_shutdown
        def second():
            order.append("second")
        
        await shutdown.shutdown()
        
        assert order == ["second", "first"]
    
    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self, shutdown):
        """Test shutdown only runs once."""
        count = 0
        
        @shutdown.on_shutdown
        def cleanup():
            nonlocal count
            count += 1
        
        await shutdown.shutdown()
        await shutdown.shutdown()
        
        assert count == 1
    
    @pytest.mark.asyncio
    async def test_shutdown_continues_on_error(self, shutdown):
        """Test shutdown continues even if callback fails."""
        results = []
        
        @shutdown.on_shutdown
        def good1():
            results.append("good1")
        
        @shutdown.on_shutdown
        def bad():
            raise Exception("Failed")
        
        @shutdown.on_shutdown
        def good2():
            results.append("good2")
        
        await shutdown.shutdown()
        
        # Both good callbacks should have run (in reverse order)
        assert "good2" in results
        assert "good1" in results


class TestConfigValidator:
    """Tests for ConfigValidator."""
    
    def test_validate_development(self):
        """Test validation in development mode."""
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://localhost/db",
            "SECURITY_JWT_SECRET": "supersecretkeythatisatleast32chars",
        }, clear=True):
            validator = ConfigValidator(environment="development")
            errors = validator.validate()
            
            # Should have no errors
            error_messages = [e.message for e in errors if e.severity == "error"]
            assert len(error_messages) == 0
    
    def test_validate_missing_required(self):
        """Test validation with missing required vars."""
        with patch.dict(os.environ, {}, clear=True):
            validator = ConfigValidator(environment="development")
            errors = validator.validate()
            
            required_errors = [
                e for e in errors
                if e.key in ["DATABASE_URL", "SECURITY_JWT_SECRET"]
            ]
            assert len(required_errors) >= 2
    
    def test_validate_production_missing_alpaca(self):
        """Test production validation missing Alpaca keys."""
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://localhost/db",
            "SECURITY_JWT_SECRET": "supersecretkeythatisatleast32chars",
        }, clear=True):
            validator = ConfigValidator(environment="production")
            errors = validator.validate()
            
            alpaca_errors = [e for e in errors if "ALPACA" in e.key]
            assert len(alpaca_errors) >= 2
    
    def test_validate_short_jwt_secret(self):
        """Test warning for short JWT secret."""
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://localhost/db",
            "SECURITY_JWT_SECRET": "short",
        }, clear=True):
            validator = ConfigValidator(environment="development")
            errors = validator.validate()
            
            jwt_warnings = [
                e for e in errors
                if e.key == "SECURITY_JWT_SECRET" and e.severity == "warning"
            ]
            assert len(jwt_warnings) == 1
    
    def test_validate_development_secret_in_production(self):
        """Test error for development secret in production."""
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://localhost/db",
            "SECURITY_JWT_SECRET": "development-secret",
            "ALPACA_API_KEY_ID": "key",
            "ALPACA_API_SECRET_KEY": "secret",
        }, clear=True):
            validator = ConfigValidator(environment="production")
            errors = validator.validate()
            
            secret_errors = [e for e in errors if "development" in e.message.lower()]
            assert len(secret_errors) >= 1
    
    def test_is_valid_success(self):
        """Test is_valid returns True when valid."""
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://localhost/db",
            "SECURITY_JWT_SECRET": "supersecretkeythatisatleast32chars",
        }, clear=True):
            validator = ConfigValidator(environment="development")
            assert validator.is_valid() is True
    
    def test_is_valid_failure(self):
        """Test is_valid returns False when invalid."""
        with patch.dict(os.environ, {}, clear=True):
            validator = ConfigValidator(environment="development")
            assert validator.is_valid() is False


class TestFeatureFlags:
    """Tests for FeatureFlags."""
    
    @pytest.fixture
    def flags(self):
        """Create a fresh feature flag instance."""
        return FeatureFlags()
    
    def test_set_and_check_flag(self, flags):
        """Test setting and checking a flag."""
        flags.set("new_feature", enabled=True)
        
        assert flags.is_enabled("new_feature") is True
    
    def test_disabled_flag(self, flags):
        """Test disabled flag returns False."""
        flags.set("disabled_feature", enabled=False)
        
        assert flags.is_enabled("disabled_feature") is False
    
    def test_unknown_flag(self, flags):
        """Test unknown flag returns False."""
        assert flags.is_enabled("nonexistent") is False
    
    def test_rollout_percentage(self, flags):
        """Test percentage-based rollout."""
        flags.set("partial_rollout", enabled=True, rollout_pct=50)
        
        # With user_id, should be deterministic
        result1 = flags.is_enabled("partial_rollout", user_id="user1")
        result2 = flags.is_enabled("partial_rollout", user_id="user1")
        
        # Same user should get same result
        assert result1 == result2
    
    def test_rollout_zero_percent(self, flags):
        """Test 0% rollout."""
        flags.set("no_rollout", enabled=True, rollout_pct=0)
        
        assert flags.is_enabled("no_rollout", user_id="any_user") is False
    
    def test_rollout_hundred_percent(self, flags):
        """Test 100% rollout."""
        flags.set("full_rollout", enabled=True, rollout_pct=100)
        
        assert flags.is_enabled("full_rollout", user_id="any_user") is True
    
    def test_user_override(self, flags):
        """Test user-specific override."""
        flags.set("feature", enabled=True, rollout_pct=0)
        flags.set_override("feature", "special_user", enabled=True)
        
        assert flags.is_enabled("feature", user_id="special_user") is True
        assert flags.is_enabled("feature", user_id="normal_user") is False
    
    def test_override_disable(self, flags):
        """Test override to disable for specific user."""
        flags.set("feature", enabled=True, rollout_pct=100)
        flags.set_override("feature", "blocked_user", enabled=False)
        
        assert flags.is_enabled("feature", user_id="blocked_user") is False
        assert flags.is_enabled("feature", user_id="normal_user") is True
    
    def test_get_all_flags(self, flags):
        """Test getting all flags."""
        flags.set("feature1", enabled=True)
        flags.set("feature2", enabled=False)
        
        all_flags = flags.get_all()
        
        assert len(all_flags) == 2
        assert "feature1" in all_flags
        assert "feature2" in all_flags


class TestDeploymentInfo:
    """Tests for DeploymentInfo."""
    
    def test_default_values(self):
        """Test default deployment info values."""
        with patch.dict(os.environ, {}, clear=True):
            info = DeploymentInfo()
            
            assert info.version == "unknown"
            assert info.build_id == "local"
            assert info.environment == "development"
            assert len(info.instance_id) == 8
    
    def test_environment_values(self):
        """Test deployment info from environment."""
        with patch.dict(os.environ, {
            "APP_VERSION": "1.2.3",
            "BUILD_ID": "abc123",
            "APP_ENVIRONMENT": "production",
            "INSTANCE_ID": "pod-xyz",
        }):
            info = DeploymentInfo()
            
            assert info.version == "1.2.3"
            assert info.build_id == "abc123"
            assert info.environment == "production"
            assert info.instance_id == "pod-xyz"
    
    def test_uptime(self):
        """Test uptime calculation."""
        info = DeploymentInfo()
        
        assert info.uptime_seconds >= 0
        assert info.uptime_seconds < 1  # Should be very small
    
    def test_is_production(self):
        """Test production detection."""
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "production"}):
            info = DeploymentInfo()
            assert info.is_production() is True
        
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "development"}):
            info = DeploymentInfo()
            assert info.is_production() is False
    
    def test_get_info(self):
        """Test getting all info."""
        info = DeploymentInfo()
        data = info.get_info()
        
        assert "version" in data
        assert "build_id" in data
        assert "environment" in data
        assert "instance_id" in data
        assert "uptime_seconds" in data
        assert "start_time" in data
        assert "python_version" in data


class TestProductionReadiness:
    """Tests for ProductionReadiness orchestrator."""
    
    @pytest.fixture
    def prod(self):
        """Create a fresh production readiness instance."""
        return ProductionReadiness(environment="development")
    
    def test_initial_state(self, prod):
        """Test initial production readiness state."""
        assert prod._readiness == ReadinessStatus.STARTING
    
    def test_set_ready(self, prod):
        """Test setting ready status."""
        prod.set_ready()
        assert prod._readiness == ReadinessStatus.READY
    
    def test_set_stopping(self, prod):
        """Test setting stopping status."""
        prod.set_stopping()
        assert prod._readiness == ReadinessStatus.STOPPING
    
    @pytest.mark.asyncio
    async def test_get_system_health_all_healthy(self, prod):
        """Test system health with all healthy checks."""
        @prod.health.register("db", critical=True)
        async def check_db():
            return {}
        
        @prod.health.register("cache")
        async def check_cache():
            return {}
        
        health = await prod.get_system_health()
        
        assert health.status == HealthStatus.HEALTHY
        assert len(health.checks) == 2
    
    @pytest.mark.asyncio
    async def test_get_system_health_degraded(self, prod):
        """Test system health with non-critical failure."""
        @prod.health.register("db", critical=True)
        async def check_db():
            return {}
        
        @prod.health.register("cache", critical=False)
        async def check_cache():
            raise Exception("Cache down")
        
        health = await prod.get_system_health()
        
        assert health.status == HealthStatus.DEGRADED
    
    @pytest.mark.asyncio
    async def test_get_system_health_unhealthy(self, prod):
        """Test system health with critical failure."""
        @prod.health.register("db", critical=True)
        async def check_db():
            raise Exception("DB down")
        
        health = await prod.get_system_health()
        
        assert health.status == HealthStatus.UNHEALTHY
    
    @pytest.mark.asyncio
    async def test_liveness_check(self, prod):
        """Test liveness probe."""
        result = await prod.liveness_check()
        
        assert result["status"] == "alive"
        assert "timestamp" in result
    
    @pytest.mark.asyncio
    async def test_readiness_check_not_ready(self, prod):
        """Test readiness when not ready."""
        result = await prod.readiness_check()
        
        assert result["ready"] is False
        assert result["status"] == "starting"
    
    @pytest.mark.asyncio
    async def test_readiness_check_ready(self, prod):
        """Test readiness when ready."""
        @prod.health.register("db", critical=True)
        async def check_db():
            return {}
        
        await prod.health.run_all()
        prod.set_ready()
        
        result = await prod.readiness_check()
        
        assert result["ready"] is True
        assert result["status"] == "ready"


class TestGetProductionReadiness:
    """Tests for global production readiness singleton."""
    
    def test_get_production_readiness(self):
        """Test getting the global instance."""
        import backend.infra.production as prod_module
        prod_module._production_readiness = None
        
        instance1 = get_production_readiness()
        instance2 = get_production_readiness()
        
        assert instance1 is instance2
