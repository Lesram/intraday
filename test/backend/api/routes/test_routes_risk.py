"""
Comprehensive test suite for Module 9: backend.api.routes.risk

This module provides complete test coverage for the risk API routes including:
- Risk metrics retrieval with authentication
- Risk limits management and validation
- Role-based access control (admin, risk_manager, read-only)
- Legacy route compatibility
- Pydantic model validation
- Mock risk manager and service integration
- Error handling and edge cases

Target: 100% statement and branch coverage
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any

from fastapi import HTTPException, status, Request
from pydantic import ValidationError

# Configure pytest to ignore Google protobuf deprecation warnings
pytestmark = pytest.mark.filterwarnings("ignore:.*PyType_Spec.*:DeprecationWarning")

# Import the module under test
import backend.api.routes.risk as risk_module
from backend.api.routes.risk import (
    # Models
    RiskLimitsPayload,
    # Dependencies
    get_risk_manager,
    get_risk_service,
    # Endpoints
    risk_metrics,
    set_limits,
    get_risk_metrics_legacy,
    update_limits_legacy,
    router
)


class TestModule9RiskComponents:
    """Test core components of the risk module."""
    
    def test_router_configuration(self):
        """Test FastAPI router configuration."""
        assert router.prefix == "/risk"
        assert "risk" in router.tags
    
    def test_risk_limits_payload_model(self):
        """Test RiskLimitsPayload Pydantic model."""
        # Valid payload
        payload = RiskLimitsPayload(
            max_position_value=100000.0,
            max_symbol_exposure=0.25,
            circuit_breaker_pct=0.10
        )
        
        assert payload.max_position_value == 100000.0
        assert payload.max_symbol_exposure == 0.25
        assert payload.circuit_breaker_pct == 0.10
        
    def test_risk_limits_payload_validation_max_position_value(self):
        """Test RiskLimitsPayload validation for max_position_value."""
        # Must be greater than 0
        with pytest.raises(ValidationError):
            RiskLimitsPayload(
                max_position_value=0,  # Should fail (must be > 0)
                max_symbol_exposure=0.25,
                circuit_breaker_pct=0.10
            )
            
        with pytest.raises(ValidationError):
            RiskLimitsPayload(
                max_position_value=-1000,  # Should fail (must be > 0)
                max_symbol_exposure=0.25,
                circuit_breaker_pct=0.10
            )
            
    def test_risk_limits_payload_validation_max_symbol_exposure(self):
        """Test RiskLimitsPayload validation for max_symbol_exposure."""
        # Must be between 0 and 1.0
        with pytest.raises(ValidationError):
            RiskLimitsPayload(
                max_position_value=100000.0,
                max_symbol_exposure=-0.1,  # Should fail (must be >= 0)
                circuit_breaker_pct=0.10
            )
            
        with pytest.raises(ValidationError):
            RiskLimitsPayload(
                max_position_value=100000.0,
                max_symbol_exposure=1.5,  # Should fail (must be <= 1.0)
                circuit_breaker_pct=0.10
            )
            
        # Valid boundary values
        payload_min = RiskLimitsPayload(
            max_position_value=100000.0,
            max_symbol_exposure=0.0,  # Valid minimum
            circuit_breaker_pct=0.10
        )
        assert payload_min.max_symbol_exposure == 0.0
        
        payload_max = RiskLimitsPayload(
            max_position_value=100000.0,
            max_symbol_exposure=1.0,  # Valid maximum
            circuit_breaker_pct=0.10
        )
        assert payload_max.max_symbol_exposure == 1.0
        
    def test_risk_limits_payload_validation_circuit_breaker_pct(self):
        """Test RiskLimitsPayload validation for circuit_breaker_pct."""
        # Must be greater than 0 and less than or equal to 0.5
        with pytest.raises(ValidationError):
            RiskLimitsPayload(
                max_position_value=100000.0,
                max_symbol_exposure=0.25,
                circuit_breaker_pct=0  # Should fail (must be > 0)
            )
            
        with pytest.raises(ValidationError):
            RiskLimitsPayload(
                max_position_value=100000.0,
                max_symbol_exposure=0.25,
                circuit_breaker_pct=0.6  # Should fail (must be <= 0.5)
            )
            
        # Valid boundary value
        payload_max = RiskLimitsPayload(
            max_position_value=100000.0,
            max_symbol_exposure=0.25,
            circuit_breaker_pct=0.5  # Valid maximum
        )
        assert payload_max.circuit_breaker_pct == 0.5


class TestModule9MockRiskService:
    """Test the mock risk service implementation."""
    
    def test_get_risk_service(self):
        """Test risk service dependency function."""
        service = get_risk_service()
        
        assert service is not None
        assert hasattr(service, 'update_limits')
        assert hasattr(service, 'get_metrics')
        
    def test_mock_risk_service_update_limits(self):
        """Test mock risk service update_limits method."""
        service = get_risk_service()
        
        payload = {"max_position_value": 100000.0}
        result = service.update_limits(payload)
        
        assert isinstance(result, dict)
        assert result["status"] == "updated"
        
    def test_mock_risk_service_get_metrics(self):
        """Test mock risk service get_metrics method."""
        service = get_risk_service()
        
        result = service.get_metrics()
        
        assert isinstance(result, dict)
        assert result["status"] == "ok"
        assert "metrics" in result


class TestModule9RiskManagerDependency:
    """Test the risk manager dependency functionality."""
    
    def test_get_risk_manager_with_app_state(self):
        """Test get_risk_manager when manager exists in app state."""
        mock_request = Mock(spec=Request)
        mock_app_state = Mock()
        mock_risk_manager = Mock()
        mock_risk_manager.get_metrics.return_value = {"test": "data"}
        
        mock_app_state.risk_manager = mock_risk_manager
        mock_request.app.state = mock_app_state
        
        result = get_risk_manager(mock_request)
        
        assert result is mock_risk_manager
        
    def test_get_risk_manager_without_app_state(self):
        """Test get_risk_manager when no manager in app state."""
        mock_request = Mock(spec=Request)
        mock_app_state = Mock()
        mock_app_state.risk_manager = None
        mock_request.app.state = mock_app_state
        
        with patch('backend.risk.risk_manager.RiskManager') as mock_manager_class:
            mock_manager_instance = Mock()
            mock_manager_class.return_value = mock_manager_instance
            
            result = get_risk_manager(mock_request)
            
            assert result is mock_manager_instance
            mock_manager_class.assert_called_once()
            
    def test_get_risk_manager_getattr_none(self):
        """Test get_risk_manager when getattr returns None."""
        mock_request = Mock(spec=Request)
        
        # Mock getattr to return None
        with patch('backend.api.routes.risk.getattr', return_value=None):
            with patch('backend.risk.risk_manager.RiskManager') as mock_manager_class:
                mock_manager_instance = Mock()
                mock_manager_class.return_value = mock_manager_instance
                
                result = get_risk_manager(mock_request)
                
                assert result is mock_manager_instance
                mock_manager_class.assert_called_once()


class TestModule9RiskMetricsEndpoint:
    """Test the risk metrics endpoint functionality."""
    
    @pytest.mark.asyncio
    async def test_risk_metrics_success_get_metrics_method(self):
        """Test successful risk metrics retrieval with get_metrics method."""
        mock_user = Mock()
        mock_user.roles = ["trader"]
        
        mock_manager = Mock()
        mock_manager.get_metrics.return_value = {
            "status": "ok",
            "current_var": 0.05,
            "portfolio_risk": {
                "current_exposure": 0.15,
                "max_drawdown": 0.08,
                "var_95": 0.12
            }
        }
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["trader"]
            
            result = await risk_metrics(mgr=mock_manager, user=mock_user)
            
            assert isinstance(result, dict)
            assert result["status"] == "ok"
            assert "portfolio_risk" in result
            assert result["portfolio_risk"]["current_exposure"] == 0.15
            mock_manager.get_metrics.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_risk_metrics_success_metrics_callable(self):
        """Test successful risk metrics retrieval with callable metrics method."""
        mock_user = Mock()
        mock_user.roles = ["admin"]
        
        mock_manager = Mock()
        # Remove get_metrics but add callable metrics
        del mock_manager.get_metrics
        mock_manager.metrics = Mock(return_value={
            "status": "ok",
            "risk_score": 0.3
        })
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["admin"]
            
            result = await risk_metrics(mgr=mock_manager, user=mock_user)
            
            assert isinstance(result, dict)
            assert result["status"] == "ok"
            assert "portfolio_risk" in result  # Should be added automatically
            mock_manager.metrics.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_risk_metrics_fallback_default(self):
        """Test risk metrics fallback to default when no methods available."""
        mock_user = Mock()
        mock_user.roles = ["risk_manager"]
        
        mock_manager = Mock()
        # Remove both get_metrics and metrics methods
        del mock_manager.get_metrics
        mock_manager.metrics = "not_callable"  # Not callable
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["risk_manager"]
            
            result = await risk_metrics(mgr=mock_manager, user=mock_user)
            
            assert isinstance(result, dict)
            assert result["status"] == "ok"
            assert "metrics" in result
            assert "portfolio_risk" in result
            
    @pytest.mark.asyncio
    async def test_risk_metrics_adds_portfolio_risk_when_missing(self):
        """Test that portfolio_risk is added when missing from result."""
        mock_user = Mock()
        mock_user.roles = ["trader"]
        
        mock_manager = Mock()
        mock_manager.get_metrics.return_value = {
            "status": "ok",
            "other_metric": 0.25
            # No portfolio_risk
        }
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["trader"]
            
            result = await risk_metrics(mgr=mock_manager, user=mock_user)
            
            assert "portfolio_risk" in result
            assert result["portfolio_risk"]["current_exposure"] == 0.0
            assert result["portfolio_risk"]["max_drawdown"] == 0.0
            assert result["portfolio_risk"]["var_95"] == 0.0
            
    @pytest.mark.asyncio
    async def test_risk_metrics_preserves_existing_portfolio_risk(self):
        """Test that existing portfolio_risk is preserved."""
        mock_user = Mock()
        mock_user.roles = ["admin"]
        
        mock_manager = Mock()
        mock_manager.get_metrics.return_value = {
            "status": "ok",
            "portfolio_risk": {
                "current_exposure": 0.30,
                "max_drawdown": 0.15,
                "var_95": 0.20,
                "custom_metric": 123
            }
        }
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["admin"]
            
            result = await risk_metrics(mgr=mock_manager, user=mock_user)
            
            assert result["portfolio_risk"]["current_exposure"] == 0.30
            assert result["portfolio_risk"]["max_drawdown"] == 0.15
            assert result["portfolio_risk"]["var_95"] == 0.20
            assert result["portfolio_risk"]["custom_metric"] == 123
            
    @pytest.mark.asyncio
    async def test_risk_metrics_read_only_user_forbidden(self):
        """Test risk metrics access denied for read-only users."""
        mock_user = Mock()
        mock_user.roles = ["read-only"]
        
        mock_manager = Mock()
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["read-only"]
            
            with pytest.raises(HTTPException) as exc_info:
                await risk_metrics(mgr=mock_manager, user=mock_user)
                
            assert exc_info.value.status_code == 403
            assert "Insufficient permissions" in str(exc_info.value.detail)


class TestModule9SetLimitsEndpoint:
    """Test the set limits endpoint functionality."""
    
    @pytest.mark.asyncio
    async def test_set_limits_success(self):
        """Test successful limits setting."""
        mock_user = Mock()
        mock_user.roles = ["admin"]
        
        mock_manager = Mock()
        mock_manager.set_limits.return_value = {"status": "limits_updated"}
        
        payload = RiskLimitsPayload(
            max_position_value=50000.0,
            max_symbol_exposure=0.30,
            circuit_breaker_pct=0.15
        )
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["admin"]
            
            result = await set_limits(payload=payload, mgr=mock_manager, user=mock_user)
            
            assert result["status"] == "limits_updated"
            mock_manager.set_limits.assert_called_once()
            
            # Verify the dict() method was called on payload
            call_args = mock_manager.set_limits.call_args[0][0]
            assert isinstance(call_args, dict)
            
    @pytest.mark.asyncio
    async def test_set_limits_non_admin_forbidden(self):
        """Test set limits access denied for non-admin users."""
        mock_user = Mock()
        mock_user.roles = ["trader"]
        
        mock_manager = Mock()
        
        payload = RiskLimitsPayload(
            max_position_value=50000.0,
            max_symbol_exposure=0.30,
            circuit_breaker_pct=0.15
        )
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["trader"]
            
            with pytest.raises(HTTPException) as exc_info:
                await set_limits(payload=payload, mgr=mock_manager, user=mock_user)
                
            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert "Insufficient permissions" in str(exc_info.value.detail)
            
    @pytest.mark.asyncio
    async def test_set_limits_read_only_forbidden(self):
        """Test set limits access denied for read-only users."""
        mock_user = Mock()
        mock_user.roles = ["read-only"]
        
        mock_manager = Mock()
        
        payload = RiskLimitsPayload(
            max_position_value=50000.0,
            max_symbol_exposure=0.30,
            circuit_breaker_pct=0.15
        )
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["read-only"]
            
            with pytest.raises(HTTPException) as exc_info:
                await set_limits(payload=payload, mgr=mock_manager, user=mock_user)
                
            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert "Insufficient permissions" in str(exc_info.value.detail)


class TestModule9LegacyRiskMetricsEndpoint:
    """Test the legacy risk metrics endpoint functionality."""
    
    @pytest.mark.asyncio
    async def test_get_risk_metrics_legacy_success(self):
        """Test successful legacy risk metrics retrieval."""
        mock_user = {"user_id": "user123", "roles": ["trader"]}
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["trader"]
            
            result = await get_risk_metrics_legacy(user=mock_user)
            
            assert isinstance(result, dict)
            assert result["status"] == "ok"
            assert "metrics" in result
            
    @pytest.mark.asyncio
    async def test_get_risk_metrics_legacy_no_user(self):
        """Test legacy risk metrics with no user authentication."""
        with pytest.raises(HTTPException) as exc_info:
            await get_risk_metrics_legacy(user=None)
            
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in str(exc_info.value.detail)
        
    @pytest.mark.asyncio
    async def test_get_risk_metrics_legacy_read_only_forbidden(self):
        """Test legacy risk metrics access denied for read-only users."""
        mock_user = {"user_id": "user123", "roles": ["read-only"]}
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["read-only"]
            
            with pytest.raises(HTTPException) as exc_info:
                await get_risk_metrics_legacy(user=mock_user)
                
            assert exc_info.value.status_code == 403
            assert "Insufficient permissions" in str(exc_info.value.detail)


class TestModule9LegacyUpdateLimitsEndpoint:
    """Test the legacy update limits endpoint functionality."""
    
    @pytest.mark.asyncio
    async def test_update_limits_legacy_success_admin(self):
        """Test successful legacy limits update with admin user."""
        mock_user = {"user_id": "admin123", "roles": ["admin"]}
        
        payload = RiskLimitsPayload(
            max_position_value=75000.0,
            max_symbol_exposure=0.40,
            circuit_breaker_pct=0.20
        )
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.side_effect = lambda user, attr, default: {
                "roles": ["admin"]
            }.get(attr, default)
            
            result = await update_limits_legacy(payload=payload, user=mock_user)
            
            assert isinstance(result, dict)
            assert result["status"] == "updated"
            assert "limits" in result
            assert result["limits"]["max_position_value"] == 75000.0
            
    @pytest.mark.asyncio
    async def test_update_limits_legacy_success_risk_manager(self):
        """Test successful legacy limits update with risk_manager user."""
        mock_user = {"user_id": "risk123", "roles": ["risk_manager"]}
        
        payload = RiskLimitsPayload(
            max_position_value=60000.0,
            max_symbol_exposure=0.35,
            circuit_breaker_pct=0.12
        )
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.side_effect = lambda user, attr, default: {
                "roles": ["risk_manager"]
            }.get(attr, default)
            
            result = await update_limits_legacy(payload=payload, user=mock_user)
            
            assert isinstance(result, dict)
            assert result["status"] == "updated"
            assert "limits" in result
            assert result["limits"]["max_symbol_exposure"] == 0.35
            
    @pytest.mark.asyncio
    async def test_update_limits_legacy_success_admin_and_risk_manager(self):
        """Test successful legacy limits update with both admin and risk_manager roles."""
        mock_user = {"user_id": "super123", "roles": ["admin", "risk_manager"]}
        
        payload = RiskLimitsPayload(
            max_position_value=80000.0,
            max_symbol_exposure=0.45,
            circuit_breaker_pct=0.25
        )
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.side_effect = lambda user, attr, default: {
                "roles": ["admin", "risk_manager"]
            }.get(attr, default)
            
            result = await update_limits_legacy(payload=payload, user=mock_user)
            
            assert isinstance(result, dict)
            assert result["status"] == "updated"
            assert "limits" in result
            
    @pytest.mark.asyncio
    async def test_update_limits_legacy_no_user(self):
        """Test legacy update limits with no user authentication."""
        payload = RiskLimitsPayload(
            max_position_value=50000.0,
            max_symbol_exposure=0.30,
            circuit_breaker_pct=0.15
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await update_limits_legacy(payload=payload, user=None)
            
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in str(exc_info.value.detail)
        
    @pytest.mark.asyncio
    async def test_update_limits_legacy_read_only_forbidden(self):
        """Test legacy update limits access denied for read-only users."""
        mock_user = {"user_id": "readonly123", "roles": ["read-only"]}
        
        payload = RiskLimitsPayload(
            max_position_value=50000.0,
            max_symbol_exposure=0.30,
            circuit_breaker_pct=0.15
        )
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["read-only"]
            
            with pytest.raises(HTTPException) as exc_info:
                await update_limits_legacy(payload=payload, user=mock_user)
                
            assert exc_info.value.status_code == 403
            assert "Insufficient permissions" in str(exc_info.value.detail)
            
    @pytest.mark.asyncio
    async def test_update_limits_legacy_trader_forbidden(self):
        """Test legacy update limits access denied for trader users without admin/risk_manager roles."""
        mock_user = {"user_id": "trader123", "roles": ["trader"]}
        
        payload = RiskLimitsPayload(
            max_position_value=50000.0,
            max_symbol_exposure=0.30,
            circuit_breaker_pct=0.15
        )
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["trader"]
            
            with pytest.raises(HTTPException) as exc_info:
                await update_limits_legacy(payload=payload, user=mock_user)
                
            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert "Admin or risk manager privileges required" in str(exc_info.value.detail)


class TestModule9EdgeCasesAndErrorHandling:
    """Test edge cases and comprehensive error handling."""
    
    @pytest.mark.asyncio
    async def test_risk_metrics_user_attribute_empty_roles(self):
        """Test risk metrics with user having empty roles."""
        mock_user = Mock()
        mock_user.roles = []
        
        mock_manager = Mock()
        mock_manager.get_metrics.return_value = {"status": "ok"}
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = []  # Empty roles
            
            result = await risk_metrics(mgr=mock_manager, user=mock_user)
            
            # Should succeed with empty roles (not read-only)
            assert result["status"] == "ok"
            
    @pytest.mark.asyncio
    async def test_risk_metrics_user_attribute_default_fallback(self):
        """Test risk metrics with user attribute fallback to default."""
        mock_user = Mock()
        
        mock_manager = Mock()
        mock_manager.get_metrics.return_value = {"status": "ok"}
        
        # Fix: Use 'backend.api.routes.risk.get_user_attribute' for proper patching
        with patch('backend.api.routes.risk.get_user_attribute') as mock_get_attr:
            # Return default value (empty list)
            mock_get_attr.return_value = []
            
            result = await risk_metrics(mgr=mock_manager, user=mock_user)
            
            assert result["status"] == "ok"
            mock_get_attr.assert_called_with(mock_user, "roles", [])
            
    @pytest.mark.asyncio
    async def test_set_limits_user_attribute_default_fallback(self):
        """Test set limits with user attribute fallback to default."""
        mock_user = Mock()
        mock_manager = Mock()
        
        payload = RiskLimitsPayload(
            max_position_value=50000.0,
            max_symbol_exposure=0.30,
            circuit_breaker_pct=0.15
        )
        
        # Fix: Use 'backend.api.routes.risk.get_user_attribute' for proper patching
        with patch('backend.api.routes.risk.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = []  # Empty roles (no admin)
            
            with pytest.raises(HTTPException) as exc_info:
                await set_limits(payload=payload, mgr=mock_manager, user=mock_user)
                
            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            mock_get_attr.assert_called_with(mock_user, "roles", [])
            
    def test_risk_limits_payload_model_dump_method(self):
        """Test RiskLimitsPayload model_dump method usage."""
        payload = RiskLimitsPayload(
            max_position_value=25000.0,
            max_symbol_exposure=0.20,
            circuit_breaker_pct=0.08
        )
        
        # Test model_dump method (used in legacy update)
        dumped = payload.model_dump()
        
        assert isinstance(dumped, dict)
        assert dumped["max_position_value"] == 25000.0
        assert dumped["max_symbol_exposure"] == 0.20
        assert dumped["circuit_breaker_pct"] == 0.08
        
    def test_risk_limits_payload_model_dump_alternative_method(self):
        """Test RiskLimitsPayload model_dump method usage (replaces deprecated dict method)."""
        payload = RiskLimitsPayload(
            max_position_value=35000.0,
            max_symbol_exposure=0.28,
            circuit_breaker_pct=0.18
        )
        
        # Test model_dump() method (used in set_limits) - replaces deprecated dict()
        dumped = payload.model_dump()
        
        assert isinstance(dumped, dict)
        assert dumped["max_position_value"] == 35000.0
        assert dumped["max_symbol_exposure"] == 0.28
        assert dumped["circuit_breaker_pct"] == 0.18
        
    @pytest.mark.asyncio
    async def test_manager_hasattr_get_metrics_false(self):
        """Test risk metrics when manager doesn't have get_metrics method."""
        mock_user = Mock()
        mock_user.roles = ["trader"]
        
        mock_manager = Mock()
        # Ensure hasattr returns False for get_metrics
        del mock_manager.get_metrics
        mock_manager.metrics = Mock(return_value={"status": "callable_metrics"})
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["trader"]
            
            result = await risk_metrics(mgr=mock_manager, user=mock_user)
            
            assert result["status"] == "callable_metrics"
            mock_manager.metrics.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_manager_hasattr_metrics_false(self):
        """Test risk metrics when manager doesn't have metrics attribute."""
        mock_user = Mock()
        mock_user.roles = ["admin"]
        
        mock_manager = Mock()
        # Remove both get_metrics and metrics
        del mock_manager.get_metrics
        del mock_manager.metrics
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["admin"]
            
            result = await risk_metrics(mgr=mock_manager, user=mock_user)
            
            # Should fall back to default
            assert result["status"] == "ok"
            assert "metrics" in result
            assert "portfolio_risk" in result
            
    @pytest.mark.asyncio
    async def test_manager_metrics_not_callable(self):
        """Test risk metrics when manager has metrics attribute but it's not callable."""
        mock_user = Mock()
        mock_user.roles = ["risk_manager"]
        
        mock_manager = Mock()
        # Remove get_metrics but add non-callable metrics
        del mock_manager.get_metrics
        mock_manager.metrics = "not_a_function"
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = ["risk_manager"]
            
            result = await risk_metrics(mgr=mock_manager, user=mock_user)
            
            # Should fall back to default
            assert result["status"] == "ok"
            assert "metrics" in result
            assert "portfolio_risk" in result
            
    @pytest.mark.asyncio
    async def test_comprehensive_role_validation_matrix(self):
        """Test comprehensive role validation across all endpoints."""
        test_cases = [
            # (roles, endpoint, should_succeed)
            ([], "risk_metrics", True),  # Empty roles allowed for metrics
            (["trader"], "risk_metrics", True),
            (["admin"], "risk_metrics", True),
            (["risk_manager"], "risk_metrics", True),
            (["read-only"], "risk_metrics", False),  # Read-only blocked
            (["read-only", "trader"], "risk_metrics", False),  # Read-only blocks
            
            ([], "set_limits", False),  # No admin role
            (["trader"], "set_limits", False),  # No admin role
            (["admin"], "set_limits", True),  # Admin allowed
            (["admin", "trader"], "set_limits", True),  # Admin allowed
            (["read-only"], "set_limits", False),  # Read-only blocked
            
            (["trader"], "legacy_metrics", True),  # Non-empty roles allowed
            (["read-only"], "legacy_metrics", False),  # Read-only blocked
            
            (["trader"], "legacy_update", False),  # No admin/risk_manager
            (["admin"], "legacy_update", True),  # Admin allowed
            (["risk_manager"], "legacy_update", True),  # Risk manager allowed
            (["admin", "risk_manager"], "legacy_update", True),  # Both allowed
            (["read-only"], "legacy_update", False),  # Read-only blocked
        ]
        
        for roles, endpoint, should_succeed in test_cases:
            mock_user = Mock()
            mock_user.roles = roles
            
            mock_manager = Mock()
            mock_manager.get_metrics.return_value = {"status": "ok"}
            mock_manager.set_limits.return_value = {"status": "updated"}
            
            payload = RiskLimitsPayload(
                max_position_value=50000.0,
                max_symbol_exposure=0.30,
                circuit_breaker_pct=0.15
            )
            
            with patch('backend.api.routes.risk.get_user_attribute') as mock_get_attr:
                mock_get_attr.return_value = roles
                
                try:
                    if endpoint == "risk_metrics":
                        result = await risk_metrics(mgr=mock_manager, user=mock_user)
                    elif endpoint == "set_limits":
                        result = await set_limits(payload=payload, mgr=mock_manager, user=mock_user)
                    elif endpoint == "legacy_metrics":
                        user_dict = {"user_id": f"user_{roles}", "roles": roles} if roles else None
                        result = await get_risk_metrics_legacy(user=user_dict)
                    elif endpoint == "legacy_update":
                        user_dict = {"user_id": f"user_{roles}", "roles": roles} if roles else None
                        result = await update_limits_legacy(payload=payload, user=user_dict)
                    
                    if should_succeed:
                        assert isinstance(result, dict)
                    else:
                        pytest.fail(f"Expected HTTPException for roles {roles} on {endpoint}")
                        
                except HTTPException as e:
                    if should_succeed:
                        pytest.fail(f"Unexpected HTTPException for roles {roles} on {endpoint}: {e.detail}")
                    else:
                        # Expected exception
                        assert e.status_code in [401, 403]