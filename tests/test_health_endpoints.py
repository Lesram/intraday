"""
Tests for Health Check API Endpoints.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, UTC

from backend.api.health import router
from backend.infra.production import (
    ProductionReadiness,
    HealthStatus,
    ReadinessStatus,
    HealthCheckResult,
    SystemHealth,
)


class TestHealthEndpoints:
    """Tests for health check endpoints."""
    
    @pytest.fixture
    def mock_prod(self):
        """Create a mock production readiness instance."""
        prod = ProductionReadiness(environment="test")
        
        # Register a basic application check
        @prod.health.register("application", critical=True)
        def check_app():
            return {"status": "running"}
        
        return prod
    
    @pytest.mark.asyncio
    async def test_liveness_probe(self, mock_prod):
        """Test liveness probe returns alive status."""
        with patch("backend.api.health.get_production_readiness", return_value=mock_prod):
            from backend.api.health import liveness_probe
            
            result = await liveness_probe()
            
            assert result.status == "alive"
            assert result.timestamp is not None
    
    @pytest.mark.asyncio
    async def test_readiness_probe_starting(self, mock_prod):
        """Test readiness probe when starting."""
        mock_response = MagicMock()
        
        with patch("backend.api.health.get_production_readiness", return_value=mock_prod):
            from backend.api.health import readiness_probe
            
            result = await readiness_probe(mock_response)
            
            assert result.ready is False
            assert result.status == "starting"
            assert mock_response.status_code == 503
    
    @pytest.mark.asyncio
    async def test_readiness_probe_ready(self, mock_prod):
        """Test readiness probe when ready."""
        # Mark as ready and run health checks
        await mock_prod.health.run_all()
        mock_prod.set_ready()
        
        mock_response = MagicMock()
        
        with patch("backend.api.health.get_production_readiness", return_value=mock_prod):
            from backend.api.health import readiness_probe
            
            result = await readiness_probe(mock_response)
            
            assert result.ready is True
            assert result.status == "ready"
    
    @pytest.mark.asyncio
    async def test_full_health_check_healthy(self, mock_prod):
        """Test full health check with healthy system."""
        await mock_prod.health.run_all()
        mock_prod.set_ready()
        
        mock_response = MagicMock()
        
        with patch("backend.api.health.get_production_readiness", return_value=mock_prod):
            from backend.api.health import full_health_check
            
            result = await full_health_check(mock_response)
            
            assert result.status == "healthy"
            assert "application" in result.checks
            assert result.checks["application"].status == "healthy"
    
    @pytest.mark.asyncio
    async def test_full_health_check_unhealthy(self, mock_prod):
        """Test full health check with unhealthy system."""
        @mock_prod.health.register("failing", critical=True)
        async def check_failing():
            raise Exception("Component failed")
        
        await mock_prod.health.run_all()
        
        mock_response = MagicMock()
        
        with patch("backend.api.health.get_production_readiness", return_value=mock_prod):
            from backend.api.health import full_health_check
            
            result = await full_health_check(mock_response)
            
            assert result.status == "unhealthy"
            assert mock_response.status_code == 503
    
    @pytest.mark.asyncio
    async def test_deployment_info(self, mock_prod):
        """Test deployment info endpoint."""
        with patch("backend.api.health.get_production_readiness", return_value=mock_prod):
            from backend.api.health import deployment_info
            
            result = await deployment_info()
            
            assert "version" in result
            assert "environment" in result
            assert "uptime_seconds" in result
            assert "instance_id" in result


class TestHealthCheckDetail:
    """Tests for health check detail model."""
    
    def test_health_check_detail_creation(self):
        """Test creating health check detail."""
        from backend.api.health import HealthCheckDetail
        
        detail = HealthCheckDetail(
            status="healthy",
            latency_ms=5.2,
            message="OK",
        )
        
        assert detail.status == "healthy"
        assert detail.latency_ms == 5.2
        assert detail.message == "OK"
    
    def test_health_check_detail_no_message(self):
        """Test health check detail without message."""
        from backend.api.health import HealthCheckDetail
        
        detail = HealthCheckDetail(
            status="healthy",
            latency_ms=1.0,
        )
        
        assert detail.message is None


class TestSetupHealthChecks:
    """Tests for setup_health_checks function."""
    
    def test_setup_registers_checks(self):
        """Test that setup registers expected checks."""
        mock_prod = ProductionReadiness(environment="test")
        
        with patch("backend.api.health.get_production_readiness", return_value=mock_prod):
            from backend.api.health import setup_health_checks
            
            setup_health_checks()
            
            # Verify checks are registered
            assert "database" in mock_prod.health._checks
            assert "application" in mock_prod.health._checks
            
            # Verify critical flags
            assert mock_prod.health._checks["database"]["critical"] is True
            assert mock_prod.health._checks["application"]["critical"] is True
