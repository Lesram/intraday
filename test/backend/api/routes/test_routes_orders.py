"""
Comprehensive test suite for Module 8: backend.api.routes.orders

This module provides complete test coverage for the orders API routes including:
- Order submission with outbox pattern and idempotency
- Order status retrieval and management
- Order cancellation operations
- Audit trail functionality
- Risk management integration
- Authentication and authorization
- Mock services and dependencies
- Error handling and edge cases

Target: 100% statement and branch coverage
"""

import pytest
import asyncio
import uuid
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any

from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from pydantic import ValidationError

# Configure pytest to ignore Google protobuf deprecation warnings
pytestmark = pytest.mark.filterwarnings("ignore:.*PyType_Spec.*:DeprecationWarning")

# Import the module under test
import backend.api.routes.orders as orders_module
from backend.api.routes.orders import (
    # Models
    OrderSubmissionRequest,
    OrderSubmissionResponse, 
    OrderStatusResponse,
    AuditEntry,
    AuditResponse,
    # Dependencies
    get_order_service,
    get_risk_manager,
    require_trader,
    # Endpoints
    submit_order,
    submit_order_submit,
    get_order_status,
    cancel_order,
    get_order_audit_trail,
    router
)


class TestModule8OrdersComponents:
    """Test core components of the orders module."""
    
    def test_router_configuration(self):
        """Test FastAPI router configuration."""
        assert router.prefix == "/orders"
        assert "Trading" in router.tags
        assert "Protected" in router.tags 
        assert "Outbox" in router.tags
    
    def test_order_submission_request_model(self):
        """Test OrderSubmissionRequest Pydantic model."""
        # Valid request
        request = OrderSubmissionRequest(
            symbol="AAPL",
            side="buy",
            qty=100.0,
            order_type="market",
            time_in_force="day",
            client_order_id="client_123"
        )
        
        assert request.symbol == "AAPL"
        assert request.side == "buy"
        assert request.qty == 100.0
        assert request.order_type == "market"
        assert request.time_in_force == "day"
        assert request.client_order_id == "client_123"
        
    def test_order_submission_request_defaults(self):
        """Test OrderSubmissionRequest default values."""
        request = OrderSubmissionRequest(
            symbol="TSLA",
            side="sell", 
            qty=50.0
        )
        
        assert request.order_type == "market"
        assert request.time_in_force == "day"
        assert request.client_order_id is None
        
    def test_order_submission_request_validation(self):
        """Test OrderSubmissionRequest validation."""
        # Test quantity validation (must be > 0)
        with pytest.raises(ValidationError):
            OrderSubmissionRequest(
                symbol="AAPL",
                side="buy",
                qty=0  # Should fail
            )
            
        with pytest.raises(ValidationError):
            OrderSubmissionRequest(
                symbol="AAPL", 
                side="buy",
                qty=-100  # Should fail
            )
    
    def test_order_submission_response_model(self):
        """Test OrderSubmissionResponse Pydantic model."""
        response = OrderSubmissionResponse(
            order_id="order_123",
            client_order_id="client_456",
            status="submitted",
            symbol="GOOGL",
            side="sell",
            qty=25.0,
            submitted_at="2025-09-19T10:00:00"
        )
        
        assert response.order_id == "order_123"
        assert response.client_order_id == "client_456"
        assert response.status == "submitted"
        assert response.symbol == "GOOGL"
        assert response.side == "sell"
        assert response.qty == 25.0
        assert response.submitted_at == "2025-09-19T10:00:00"
        
    def test_order_status_response_model(self):
        """Test OrderStatusResponse Pydantic model."""
        response = OrderStatusResponse(
            order_id="order_789",
            client_order_id=None,
            status="filled",
            symbol="NVDA",
            side="buy",
            qty=10.0,
            filled_qty=10.0,
            avg_fill_price=500.0,
            submitted_at="2025-09-19T09:00:00",
            updated_at="2025-09-19T09:05:00"
        )
        
        assert response.order_id == "order_789"
        assert response.client_order_id is None
        assert response.status == "filled"
        assert response.symbol == "NVDA"
        assert response.side == "buy"
        assert response.qty == 10.0
        assert response.filled_qty == 10.0
        assert response.avg_fill_price == 500.0
        assert response.submitted_at == "2025-09-19T09:00:00"
        assert response.updated_at == "2025-09-19T09:05:00"
        
    def test_audit_entry_model(self):
        """Test AuditEntry Pydantic model."""
        entry = AuditEntry(
            timestamp="2025-09-19T10:30:00",
            event_type="order_submitted",
            order_id="order_audit_123",
            details={"broker": "alpaca", "status": "submitted"}
        )
        
        assert entry.timestamp == "2025-09-19T10:30:00"
        assert entry.event_type == "order_submitted"
        assert entry.order_id == "order_audit_123"
        assert entry.details["broker"] == "alpaca"
        assert entry.details["status"] == "submitted"
        
    def test_audit_entry_default_details(self):
        """Test AuditEntry default details factory."""
        entry = AuditEntry(
            timestamp="2025-09-19T10:30:00",
            event_type="order_filled",
            order_id="order_default_123"
        )
        
        assert entry.details == {}
        
    def test_audit_response_model(self):
        """Test AuditResponse Pydantic model."""
        entries = [
            AuditEntry(
                timestamp="2025-09-19T10:00:00",
                event_type="order_submitted",
                order_id="order_multi_123"
            ),
            AuditEntry(
                timestamp="2025-09-19T10:05:00", 
                event_type="order_filled",
                order_id="order_multi_123"
            )
        ]
        
        response = AuditResponse(entries=entries)
        assert len(response.entries) == 2
        assert response.entries[0].event_type == "order_submitted"
        assert response.entries[1].event_type == "order_filled"


class TestModule8MockOrderService:
    """Test the mock order service implementation."""
    
    def setup_method(self):
        """Reset mock service instance before each test."""
        orders_module._mock_order_service_instance = None
        
    def test_get_order_service_singleton(self):
        """Test order service singleton pattern."""
        service1 = get_order_service()
        service2 = get_order_service()
        
        assert service1 is service2
        assert hasattr(service1, 'orders')
        assert hasattr(service1, 'submit_order')
        assert hasattr(service1, 'get_order_status')
        assert hasattr(service1, 'cancel_order')
        
    @pytest.mark.asyncio
    async def test_mock_order_service_submit_order(self):
        """Test mock order service submit_order method."""
        service = get_order_service()
        
        request = OrderSubmissionRequest(
            symbol="AAPL",
            side="buy",
            qty=100.0,
            client_order_id="client_test_123"
        )
        
        result = await service.submit_order(request, "test_user")
        
        assert isinstance(result, OrderSubmissionResponse)
        assert result.order_id == "order_123"  # Predictable ID from client_order_id
        assert result.client_order_id == "client_test_123"
        assert result.status == "submitted"
        assert result.symbol == "AAPL"
        assert result.side == "buy"
        assert result.qty == 100.0
        
        # Verify order stored in service
        assert result.order_id in service.orders
        
    @pytest.mark.asyncio
    async def test_mock_order_service_submit_order_uuid(self):
        """Test mock order service with UUID generation."""
        service = get_order_service()
        
        request = OrderSubmissionRequest(
            symbol="GOOGL",
            side="sell",
            qty=50.0
            # No client_order_id - should generate UUID
        )
        
        result = await service.submit_order(request, "test_user")
        
        assert isinstance(result, OrderSubmissionResponse)
        assert result.client_order_id is None
        # Should be valid UUID format
        uuid.UUID(result.order_id)  # Raises ValueError if invalid
        
    @pytest.mark.asyncio
    async def test_mock_order_service_submit_order_exception_handling(self):
        """Test mock order service exception handling in submit_order."""
        service = get_order_service()
        
        request = OrderSubmissionRequest(
            symbol="ERROR",
            side="buy", 
            qty=1.0
        )
        
        # Mock the submit function to raise an exception
        with patch('backend.services.order_service.submit_order') as mock_submit:
            mock_submit.side_effect = Exception("Test error")
            
            with pytest.raises(RuntimeError, match="Test error"):
                await service.submit_order(request, "test_user")
                
    @pytest.mark.asyncio
    async def test_mock_order_service_submit_order_not_implemented(self):
        """Test mock order service NotImplementedError handling."""
        service = get_order_service()
        
        request = OrderSubmissionRequest(
            symbol="TEST",
            side="buy",
            qty=1.0
        )
        
        # Mock to raise NotImplementedError
        with patch('backend.services.order_service.submit_order') as mock_submit:
            mock_submit.side_effect = NotImplementedError()
            
            # Should fall back to built-in behavior
            result = await service.submit_order(request, "test_user")
            assert isinstance(result, OrderSubmissionResponse)
        
    @pytest.mark.asyncio
    async def test_mock_order_service_get_order_status_known_order(self):
        """Test mock order service get_order_status with known order."""
        service = get_order_service()
        
        result = await service.get_order_status("test-123")
        
        assert isinstance(result, OrderStatusResponse)
        assert result.order_id == "test-123"
        assert result.client_order_id is None
        assert result.status == "filled"
        assert result.symbol == "AAPL"
        assert result.side == "buy"
        assert result.qty == 100.0
        assert result.filled_qty == 100.0
        assert result.avg_fill_price == 150.0
        
    @pytest.mark.asyncio
    async def test_mock_order_service_get_order_status_stored_order(self):
        """Test mock order service get_order_status with stored order."""
        service = get_order_service()
        
        # First submit an order
        request = OrderSubmissionRequest(
            symbol="TSLA",
            side="sell",
            qty=25.0,
            client_order_id="client_stored_123"
        )
        
        submit_result = await service.submit_order(request, "test_user")
        
        # Now get its status
        status_result = await service.get_order_status(submit_result.order_id)
        
        assert isinstance(status_result, OrderStatusResponse)
        assert status_result.order_id == submit_result.order_id
        assert status_result.symbol == "TSLA"
        assert status_result.side == "sell"
        assert status_result.qty == 25.0
        
    @pytest.mark.asyncio
    async def test_mock_order_service_get_order_status_not_found(self):
        """Test mock order service get_order_status with unknown order."""
        service = get_order_service()
        
        result = await service.get_order_status("unknown_order_123")
        
        assert result is None
        
    @pytest.mark.asyncio
    async def test_mock_order_service_cancel_order_known_order(self):
        """Test mock order service cancel_order with known order."""
        service = get_order_service()
        
        result = await service.cancel_order("test-123")
        
        assert isinstance(result, dict)
        assert result["order_id"] == "test-123"
        assert result["status"] == "cancelled"
        assert "updated_at" in result
        
    @pytest.mark.asyncio
    async def test_mock_order_service_cancel_order_stored_order(self):
        """Test mock order service cancel_order with stored order."""
        service = get_order_service()
        
        # First submit an order
        request = OrderSubmissionRequest(
            symbol="NVDA",
            side="buy",
            qty=10.0,
            client_order_id="client_cancel_123"
        )
        
        submit_result = await service.submit_order(request, "test_user")
        
        # Now cancel it
        cancel_result = await service.cancel_order(submit_result.order_id)
        
        assert isinstance(cancel_result, dict)
        assert cancel_result["order_id"] == submit_result.order_id
        assert cancel_result["status"] == "cancelled"
        
        # Verify order status was updated
        stored_order = service.orders[submit_result.order_id]
        assert stored_order["status"] == "cancelled"
        
    @pytest.mark.asyncio
    async def test_mock_order_service_cancel_order_not_found(self):
        """Test mock order service cancel_order with unknown order."""
        service = get_order_service()
        
        result = await service.cancel_order("unknown_cancel_123")
        
        assert result is None


class TestModule8MockRiskManager:
    """Test the mock risk manager implementation."""
    
    def test_get_risk_manager(self):
        """Test risk manager dependency function."""
        risk_manager = get_risk_manager()
        
        assert risk_manager is not None
        assert hasattr(risk_manager, 'check_trade_risk')
        
    def test_risk_manager_check_trade_risk_approved(self):
        """Test risk manager trade approval."""
        risk_manager = get_risk_manager()
        
        result = risk_manager.check_trade_risk("AAPL", "buy", 100.0)
        
        assert isinstance(result, dict)
        assert result["approved"] is True
        
    def test_risk_manager_check_trade_risk_rejected(self):
        """Test risk manager trade rejection."""
        risk_manager = get_risk_manager()
        
        result = risk_manager.check_trade_risk("AAPL", "buy", 1500.0)  # > 1000 limit
        
        assert isinstance(result, dict)
        assert result["approved"] is False
        assert result["reason"] == "Quantity too large"
        
    def test_risk_manager_check_trade_risk_boundary(self):
        """Test risk manager boundary conditions."""
        risk_manager = get_risk_manager()
        
        # Exactly at limit
        result = risk_manager.check_trade_risk("AAPL", "sell", 1000.0)
        assert result["approved"] is True
        
        # Just over limit
        result = risk_manager.check_trade_risk("AAPL", "sell", 1000.1)
        assert result["approved"] is False
        assert result["reason"] == "Quantity too large"


class TestModule8AuthenticationDependencies:
    """Test authentication and authorization dependencies."""
    
    def test_require_trader_with_valid_user(self):
        """Test require_trader dependency with authenticated user."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        mock_user.roles = ["trader"]
        
        result = require_trader(current_user=mock_user)
        
        assert result is mock_user
        
    def test_require_trader_with_no_user(self):
        """Test require_trader dependency with no user."""
        with pytest.raises(HTTPException) as exc_info:
            require_trader(current_user=None)
            
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in str(exc_info.value.detail)
        
    def test_require_trader_with_false_user(self):
        """Test require_trader dependency with falsy user."""
        with pytest.raises(HTTPException) as exc_info:
            require_trader(current_user=False)
            
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in str(exc_info.value.detail)


class TestModule8SubmitOrderEndpoint:
    """Test the submit order endpoint functionality."""
    
    def setup_method(self):
        """Reset mock service instance before each test."""
        orders_module._mock_order_service_instance = None
        
    @pytest.mark.asyncio
    async def test_submit_order_success(self):
        """Test successful order submission."""
        # Mock dependencies
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_order_service.submit_order.return_value = OrderSubmissionResponse(
            order_id="order_success_123",
            client_order_id="client_success_123",
            status="submitted",
            symbol="AAPL",
            side="buy",
            qty=100.0,
            submitted_at="2025-09-19T10:00:00"
        )
        
        mock_risk_manager = Mock()
        mock_risk_manager.check_trade_risk.return_value = {"approved": True}
        
        # Mock get_user_attribute
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = "trader_123"
            
            # Mock backend.services.order_service.submit_order to raise NotImplementedError
            with patch('backend.services.order_service.submit_order') as mock_submit:
                mock_submit.side_effect = NotImplementedError()
                
                body = {
                    "symbol": "AAPL",
                    "side": "buy",
                    "qty": 100.0,
                    "client_order_id": "client_success_123"
                }
                
                result = await submit_order(
                    body=body,
                    current_user=mock_user,
                    order_service=mock_order_service,
                    risk_manager=mock_risk_manager
                )
                
                assert isinstance(result, OrderSubmissionResponse)
                assert result.order_id == "order_success_123"
                assert result.symbol == "AAPL"
                
    @pytest.mark.asyncio
    async def test_submit_order_validation_errors(self):
        """Test order submission with validation errors."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_risk_manager = Mock()
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = "trader_123"
            
            with patch('backend.services.order_service.submit_order') as mock_submit:
                mock_submit.side_effect = NotImplementedError()
                
                # Test missing symbol
                body = {"side": "buy", "qty": 100.0}
                
                with pytest.raises(HTTPException) as exc_info:
                    await submit_order(
                        body=body,
                        current_user=mock_user,
                        order_service=mock_order_service,
                        risk_manager=mock_risk_manager
                    )
                    
                assert exc_info.value.status_code == 422
                assert any("symbol" in str(error).lower() for error in exc_info.value.detail)
                
    @pytest.mark.asyncio
    async def test_submit_order_invalid_side(self):
        """Test order submission with invalid side."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_risk_manager = Mock()
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = "trader_123"
            
            with patch('backend.services.order_service.submit_order') as mock_submit:
                mock_submit.side_effect = NotImplementedError()
                
                body = {
                    "symbol": "AAPL",
                    "side": "invalid_side",  # Invalid
                    "qty": 100.0
                }
                
                with pytest.raises(HTTPException) as exc_info:
                    await submit_order(
                        body=body,
                        current_user=mock_user,
                        order_service=mock_order_service,
                        risk_manager=mock_risk_manager
                    )
                    
                assert exc_info.value.status_code == 422
                assert any("side" in str(error).lower() for error in exc_info.value.detail)
                
    @pytest.mark.asyncio
    async def test_submit_order_invalid_quantity(self):
        """Test order submission with invalid quantity."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_risk_manager = Mock()
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = "trader_123"
            
            with patch('backend.services.order_service.submit_order') as mock_submit:
                mock_submit.side_effect = NotImplementedError()
                
                # Test negative quantity
                body = {
                    "symbol": "AAPL",
                    "side": "buy",
                    "qty": -100.0  # Invalid
                }
                
                with pytest.raises(HTTPException) as exc_info:
                    await submit_order(
                        body=body,
                        current_user=mock_user,
                        order_service=mock_order_service,
                        risk_manager=mock_risk_manager
                    )
                    
                assert exc_info.value.status_code == 422
                assert any("qty" in str(error).lower() for error in exc_info.value.detail)
                
    @pytest.mark.asyncio
    async def test_submit_order_symbol_too_long(self):
        """Test order submission with symbol too long."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_risk_manager = Mock()
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = "trader_123"
            
            with patch('backend.services.order_service.submit_order') as mock_submit:
                mock_submit.side_effect = NotImplementedError()
                
                body = {
                    "symbol": "VERYLONGSYMBOL",  # > 10 chars
                    "side": "buy",
                    "qty": 100.0
                }
                
                with pytest.raises(HTTPException) as exc_info:
                    await submit_order(
                        body=body,
                        current_user=mock_user,
                        order_service=mock_order_service,
                        risk_manager=mock_risk_manager
                    )
                    
                assert exc_info.value.status_code == 422
                assert any("symbol" in str(error).lower() for error in exc_info.value.detail)
                
    @pytest.mark.asyncio
    async def test_submit_order_risk_rejection(self):
        """Test order submission with risk rejection."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_risk_manager = Mock()
        mock_risk_manager.check_trade_risk.return_value = {
            "approved": False,
            "reason": "Risk limit exceeded"
        }
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = "trader_123"
            
            with patch('backend.services.order_service.submit_order') as mock_submit:
                mock_submit.side_effect = NotImplementedError()
                
                body = {
                    "symbol": "AAPL",
                    "side": "buy",
                    "qty": 100.0
                }
                
                with pytest.raises(HTTPException) as exc_info:
                    await submit_order(
                        body=body,
                        current_user=mock_user,
                        order_service=mock_order_service,
                        risk_manager=mock_risk_manager
                    )
                    
                assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
                assert "Risk limit exceeded" in str(exc_info.value.detail)
                
    @pytest.mark.asyncio
    async def test_submit_order_service_exception(self):
        """Test order submission with service exception."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_order_service.submit_order.side_effect = Exception("Service error")
        
        mock_risk_manager = Mock()
        mock_risk_manager.check_trade_risk.return_value = {"approved": True}
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = "trader_123"
            
            with patch('backend.services.order_service.submit_order') as mock_submit:
                mock_submit.side_effect = NotImplementedError()
                
                body = {
                    "symbol": "AAPL",
                    "side": "buy",
                    "qty": 100.0
                }
                
                with pytest.raises(HTTPException) as exc_info:
                    await submit_order(
                        body=body,
                        current_user=mock_user,
                        order_service=mock_order_service,
                        risk_manager=mock_risk_manager
                    )
                    
                assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
                assert "Internal Server Error" in str(exc_info.value.detail)
                
    @pytest.mark.asyncio
    async def test_submit_order_patched_service_exception(self):
        """Test order submission with patched service exception."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_risk_manager = Mock()
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = "trader_123"
            
            # Mock the patched service to raise an exception
            with patch('backend.services.order_service.submit_order') as mock_submit:
                mock_submit.side_effect = Exception("Patched service error")
                
                body = {
                    "symbol": "AAPL",
                    "side": "buy",
                    "qty": 100.0
                }
                
                with pytest.raises(HTTPException) as exc_info:
                    await submit_order(
                        body=body,
                        current_user=mock_user,
                        order_service=mock_order_service,
                        risk_manager=mock_risk_manager
                    )
                    
                assert exc_info.value.status_code == 500
                assert "Internal Server Error" in str(exc_info.value.detail)
                
    @pytest.mark.asyncio
    async def test_submit_order_submit_compatibility_endpoint(self):
        """Test the /submit compatibility endpoint."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_order_service.submit_order.return_value = OrderSubmissionResponse(
            order_id="order_compat_123",
            client_order_id=None,
            status="submitted",
            symbol="TSLA",
            side="sell",
            qty=50.0,
            submitted_at="2025-09-19T11:00:00"
        )
        
        mock_risk_manager = Mock()
        mock_risk_manager.check_trade_risk.return_value = {"approved": True}
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = "trader_123"
            
            with patch('backend.services.order_service.submit_order') as mock_submit:
                mock_submit.side_effect = NotImplementedError()
                
                body = {
                    "symbol": "TSLA",
                    "side": "sell",
                    "qty": 50.0
                }
                
                result = await submit_order_submit(
                    body=body,
                    current_user=mock_user,
                    order_service=mock_order_service,
                    risk_manager=mock_risk_manager
                )
                
                assert isinstance(result, OrderSubmissionResponse)
                assert result.order_id == "order_compat_123"
                assert result.symbol == "TSLA"


class TestModule8GetOrderStatusEndpoint:
    """Test the get order status endpoint functionality."""
    
    def setup_method(self):
        """Reset mock service instance before each test."""
        orders_module._mock_order_service_instance = None
        
    @pytest.mark.asyncio
    async def test_get_order_status_success(self):
        """Test successful order status retrieval."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_order_service.get_order_status.return_value = OrderStatusResponse(
            order_id="order_status_123",
            client_order_id="client_status_123",
            status="filled",
            symbol="GOOGL",
            side="buy",
            qty=25.0,
            filled_qty=25.0,
            avg_fill_price=2500.0,
            submitted_at="2025-09-19T09:00:00",
            updated_at="2025-09-19T09:15:00"
        )
        
        result = await get_order_status(
            order_id="order_status_123",
            current_user=mock_user,
            order_service=mock_order_service
        )
        
        assert isinstance(result, OrderStatusResponse)
        assert result.order_id == "order_status_123"
        assert result.status == "filled"
        assert result.symbol == "GOOGL"
        
    @pytest.mark.asyncio
    async def test_get_order_status_not_found(self):
        """Test order status retrieval with order not found."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_order_service.get_order_status.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await get_order_status(
                order_id="nonexistent_order",
                current_user=mock_user,
                order_service=mock_order_service
            )
            
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Order not found: nonexistent_order" in str(exc_info.value.detail)
        
    @pytest.mark.asyncio
    async def test_get_order_status_service_exception(self):
        """Test order status retrieval with service exception."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_order_service.get_order_status.side_effect = Exception("Service error")
        
        with pytest.raises(HTTPException) as exc_info:
            await get_order_status(
                order_id="error_order",
                current_user=mock_user,
                order_service=mock_order_service
            )
            
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Failed to get order status" in str(exc_info.value.detail)


class TestModule8CancelOrderEndpoint:
    """Test the cancel order endpoint functionality."""
    
    def setup_method(self):
        """Reset mock service instance before each test."""
        orders_module._mock_order_service_instance = None
        
    @pytest.mark.asyncio
    async def test_cancel_order_success(self):
        """Test successful order cancellation."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_order_service.cancel_order.return_value = {
            "order_id": "order_cancel_123",
            "status": "cancelled",
            "updated_at": "2025-09-19T10:30:00"
        }
        
        result = await cancel_order(
            order_id="order_cancel_123",
            idempotency_key="idem_123",
            current_user=mock_user,
            order_service=mock_order_service
        )
        
        assert isinstance(result, dict)
        assert result["order_id"] == "order_cancel_123"
        assert result["status"] == "cancelled"
        assert "cancelled_at" in result
        
    @pytest.mark.asyncio
    async def test_cancel_order_without_idempotency_key(self):
        """Test order cancellation without idempotency key."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_order_service.cancel_order.return_value = {
            "order_id": "order_cancel_no_key",
            "status": "cancelled",
            "updated_at": "2025-09-19T10:35:00"
        }
        
        result = await cancel_order(
            order_id="order_cancel_no_key",
            current_user=mock_user,
            order_service=mock_order_service
        )
        
        assert isinstance(result, dict)
        assert result["order_id"] == "order_cancel_no_key"
        assert result["status"] == "cancelled"
        
    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self):
        """Test order cancellation with order not found."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_order_service.cancel_order.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await cancel_order(
                order_id="nonexistent_cancel_order",
                current_user=mock_user,
                order_service=mock_order_service
            )
            
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Order not found: nonexistent_cancel_order" in str(exc_info.value.detail)
        
    @pytest.mark.asyncio
    async def test_cancel_order_service_exception(self):
        """Test order cancellation with service exception."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_order_service.cancel_order.side_effect = Exception("Cancel service error")
        
        with pytest.raises(HTTPException) as exc_info:
            await cancel_order(
                order_id="error_cancel_order",
                current_user=mock_user,
                order_service=mock_order_service
            )
            
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Failed to cancel order" in str(exc_info.value.detail)


class TestModule8AuditTrailEndpoint:
    """Test the audit trail endpoint functionality."""
    
    @pytest.mark.asyncio
    async def test_get_order_audit_trail_success(self):
        """Test successful audit trail retrieval."""
        result = await get_order_audit_trail("audit_order_123")
        
        assert isinstance(result, AuditResponse)
        assert len(result.entries) == 2
        
        # Check first entry
        first_entry = result.entries[0]
        assert first_entry.event_type == "order_submitted"
        assert first_entry.order_id == "audit_order_123"
        assert first_entry.details["status"] == "submitted"
        
        # Check second entry
        second_entry = result.entries[1]
        assert second_entry.event_type == "order_sent_to_broker"
        assert second_entry.order_id == "audit_order_123"
        assert second_entry.details["broker"] == "alpaca"
        
    @pytest.mark.asyncio
    async def test_get_order_audit_trail_different_order_id(self):
        """Test audit trail with different order ID."""
        result = await get_order_audit_trail("different_audit_order")
        
        assert isinstance(result, AuditResponse)
        assert len(result.entries) == 2
        assert all(entry.order_id == "different_audit_order" for entry in result.entries)


class TestModule8EdgeCasesAndErrorHandling:
    """Test edge cases and comprehensive error handling."""
    
    def setup_method(self):
        """Reset mock service instance before each test."""
        orders_module._mock_order_service_instance = None
        
    @pytest.mark.asyncio
    async def test_submit_order_with_none_body(self):
        """Test order submission with None body."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_risk_manager = Mock()
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = "trader_123"
            
            with patch('backend.services.order_service.submit_order') as mock_submit:
                mock_submit.side_effect = NotImplementedError()
                
                with pytest.raises(HTTPException) as exc_info:
                    await submit_order(
                        body=None,
                        current_user=mock_user,
                        order_service=mock_order_service,
                        risk_manager=mock_risk_manager
                    )
                    
                assert exc_info.value.status_code == 422
                
    @pytest.mark.asyncio
    async def test_submit_order_with_empty_symbol(self):
        """Test order submission with empty symbol."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_risk_manager = Mock()
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = "trader_123"
            
            with patch('backend.services.order_service.submit_order') as mock_submit:
                mock_submit.side_effect = NotImplementedError()
                
                body = {
                    "symbol": "",  # Empty symbol
                    "side": "buy",
                    "qty": 100.0
                }
                
                with pytest.raises(HTTPException) as exc_info:
                    await submit_order(
                        body=body,
                        current_user=mock_user,
                        order_service=mock_order_service,
                        risk_manager=mock_risk_manager
                    )
                    
                assert exc_info.value.status_code == 422
                
    @pytest.mark.asyncio
    async def test_submit_order_with_string_quantity(self):
        """Test order submission with invalid string quantity."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_risk_manager = Mock()
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = "trader_123"
            
            with patch('backend.services.order_service.submit_order') as mock_submit:
                mock_submit.side_effect = NotImplementedError()
                
                body = {
                    "symbol": "AAPL",
                    "side": "buy",
                    "qty": "invalid_number"  # Invalid quantity
                }
                
                with pytest.raises(HTTPException) as exc_info:
                    await submit_order(
                        body=body,
                        current_user=mock_user,
                        order_service=mock_order_service,
                        risk_manager=mock_risk_manager
                    )
                    
                assert exc_info.value.status_code == 422
                assert any("qty" in str(error).lower() for error in exc_info.value.detail)
                
    @pytest.mark.asyncio
    async def test_submit_order_risk_check_no_reason(self):
        """Test order submission with risk rejection but no reason."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_risk_manager = Mock()
        mock_risk_manager.check_trade_risk.return_value = {
            "approved": False
            # No "reason" key
        }
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = "trader_123"
            
            with patch('backend.services.order_service.submit_order') as mock_submit:
                mock_submit.side_effect = NotImplementedError()
                
                body = {
                    "symbol": "AAPL",
                    "side": "buy",
                    "qty": 100.0
                }
                
                with pytest.raises(HTTPException) as exc_info:
                    await submit_order(
                        body=body,
                        current_user=mock_user,
                        order_service=mock_order_service,
                        risk_manager=mock_risk_manager
                    )
                    
                assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
                assert "Unknown reason" in str(exc_info.value.detail)
                
    def test_mock_order_service_multiple_instantiation(self):
        """Test that multiple calls to get_order_service return same instance."""
        service1 = get_order_service()
        service2 = get_order_service()
        service3 = get_order_service()
        
        assert service1 is service2 is service3
        
    @pytest.mark.asyncio
    async def test_datetime_formatting_consistency(self):
        """Test that datetime formatting is consistent across responses."""
        service = get_order_service()
        
        request = OrderSubmissionRequest(
            symbol="TIME_TEST",
            side="buy",
            qty=1.0,
            client_order_id="client_time_123"
        )
        
        result = await service.submit_order(request, "test_user")
        
        # Verify timestamp format
        submitted_time = datetime.fromisoformat(result.submitted_at)
        assert isinstance(submitted_time, datetime)
        
        # Test audit trail timestamp format
        audit_result = await get_order_audit_trail("time_test_order")
        for entry in audit_result.entries:
            audit_time = datetime.fromisoformat(entry.timestamp)
            assert isinstance(audit_time, datetime)
            
    @pytest.mark.asyncio
    async def test_error_message_consistency(self):
        """Test that error messages are consistent and informative."""
        # Test 404 error format
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_order_service.get_order_status.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await get_order_status(
                order_id="test_error_consistency",
                current_user=mock_user,
                order_service=mock_order_service
            )
            
        error_detail = str(exc_info.value.detail)
        assert "Order not found: test_error_consistency" == error_detail
        
    def test_global_mock_instance_reset(self):
        """Test that the global mock instance can be properly reset."""
        # Get initial instance
        service1 = get_order_service()
        assert service1 is not None
        
        # Reset the global instance
        orders_module._mock_order_service_instance = None
        
        # Get new instance
        service2 = get_order_service()
        assert service2 is not None
        assert service2 is not service1  # Should be different instance
        
    @pytest.mark.asyncio
    async def test_comprehensive_validation_matrix(self):
        """Test comprehensive validation matrix for all field combinations."""
        mock_user = Mock()
        mock_user.user_id = "trader_123"
        
        mock_order_service = AsyncMock()
        mock_risk_manager = Mock()
        
        validation_cases = [
            # (body, expected_error_field)
            ({}, "symbol"),  # Missing all
            ({"symbol": "AAPL"}, "side"),  # Missing side and qty
            ({"symbol": "AAPL", "side": "buy"}, "qty"),  # Missing qty
            ({"symbol": 123, "side": "buy", "qty": 100.0}, "symbol"),  # Non-string symbol
            ({"symbol": "AAPL", "side": 123, "qty": 100.0}, "side"),  # Non-string side
            ({"symbol": "AAPL", "side": "buy", "qty": 0}, "qty"),  # Zero qty
            ({"symbol": "AAPL", "side": "INVALID", "qty": 100.0}, "side"),  # Invalid side
        ]
        
        with patch('backend.infra.security.get_user_attribute') as mock_get_attr:
            mock_get_attr.return_value = "trader_123"
            
            with patch('backend.services.order_service.submit_order') as mock_submit:
                mock_submit.side_effect = NotImplementedError()
                
                for body, expected_field in validation_cases:
                    with pytest.raises(HTTPException) as exc_info:
                        await submit_order(
                            body=body,
                            current_user=mock_user,
                            order_service=mock_order_service,
                            risk_manager=mock_risk_manager
                        )
                        
                    assert exc_info.value.status_code == 422
                    # Verify the expected field is mentioned in error details
                    error_details = str(exc_info.value.detail)
                    assert expected_field in error_details.lower()
