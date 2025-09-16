"""
Phase 3.1 - REAL API Routes Coverage Testing
Comprehensive tests for actual FastAPI route implementations
Target: 100% line and branch coverage for orders.py (164 statements)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from fastapi.testclient import TestClient
from fastapi import FastAPI, status
from datetime import datetime, timezone
import json
import uuid

# Import the actual route components
try:
    from backend.api.routes.orders import router as orders_router
    from backend.api.routes.orders import (
        OrderSubmissionRequest, 
        OrderSubmissionResponse,
        OrderStatusResponse,
        get_order_service,
        get_risk_manager,
        require_trader
    )
    ROUTES_AVAILABLE = True
except ImportError:
    ROUTES_AVAILABLE = False


class TestOrdersRouteRealCoverage:
    """Comprehensive coverage testing for backend/api/routes/orders.py"""
    
    @classmethod
    def setup_class(cls):
        """Setup test FastAPI app with orders router"""
        if not ROUTES_AVAILABLE:
            pytest.skip("Routes not available for testing")
        
        cls.app = FastAPI()
        cls.app.include_router(orders_router)
        cls.client = TestClient(cls.app)
        
        # Override authentication dependency for testing
        def mock_get_current_user():
            return {"user_id": "test_user", "username": "test"}
        
        from backend.infra.security import get_current_user
        cls.app.dependency_overrides[get_current_user] = mock_get_current_user
        cls.app.dependency_overrides[require_trader] = mock_get_current_user
    
    def setup_method(self):
        """Reset any global state before each test"""
        # Reset the mock order service instance
        import backend.api.routes.orders
        backend.api.routes.orders._mock_order_service_instance = None
    
    @patch('backend.api.routes.orders.require_trader')
    @patch('backend.api.routes.orders.get_risk_manager')
    @patch('backend.api.routes.orders.get_order_service')
    def test_submit_order_success_main_path(self, mock_get_order_service, mock_get_risk_manager, mock_require_trader):
        """Test POST /orders/ - successful order submission (main execution path)"""
        
        # Setup authentication mock
        mock_user = {"user_id": "test_user_123", "role": "trader"}
        mock_require_trader.return_value = mock_user
        
        # Setup risk manager mock - approval path
        mock_risk_manager = Mock()
        mock_risk_manager.check_trade_risk.return_value = {"approved": True}
        mock_get_risk_manager.return_value = mock_risk_manager
        
        # Setup order service mock - success path  
        mock_order_service = AsyncMock()
        expected_response = OrderSubmissionResponse(
            order_id="order_123",
            client_order_id="client_123",
            status="submitted",
            symbol="AAPL",
            side="buy",
            qty=100.0,
            submitted_at=datetime.now().isoformat()
        )
        mock_order_service.submit_order.return_value = expected_response
        mock_get_order_service.return_value = mock_order_service
        
        # Test data
        order_data = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100.0,
            "order_type": "market",
            "client_order_id": "client_123"
        }
        
        # Execute request
        response = self.client.post("/orders/", json=order_data)
        
        # Verify response - covers success return path
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["order_id"] == "order_123"
        assert response_data["symbol"] == "AAPL"
        assert response_data["status"] == "submitted"
        
        # Verify risk check was called - covers risk management branch
        mock_risk_manager.check_trade_risk.assert_called_once_with("AAPL", "BUY", 100.0)
        
        # Verify order service was called - covers service integration branch
        mock_order_service.submit_order.assert_called_once()
    
    @patch('backend.api.routes.orders.require_trader')
    def test_submit_order_validation_error_branches(self, mock_require_trader):
        """Test POST /orders/ - validation error branches"""
        
        mock_user = {"user_id": "test_user_123"}
        mock_require_trader.return_value = mock_user
        
        # Test case 1: Empty symbol - covers symbol validation branch
        response = self.client.post("/orders/", json={"symbol": "", "side": "buy", "qty": 100})
        assert response.status_code == 422
        error_detail = response.json()["detail"]
        assert any("symbol" in str(error).lower() for error in error_detail)
        
        # Test case 2: Invalid side - covers side validation branch
        response = self.client.post("/orders/", json={"symbol": "AAPL", "side": "invalid", "qty": 100})
        assert response.status_code == 422
        error_detail = response.json()["detail"]
        assert any("side" in str(error).lower() for error in error_detail)
        
        # Test case 3: Negative quantity - covers quantity validation branch
        response = self.client.post("/orders/", json={"symbol": "AAPL", "side": "buy", "qty": -10})
        assert response.status_code == 422
        error_detail = response.json()["detail"]
        assert any("quantity" in str(error).lower() for error in error_detail)
        
        # Test case 4: Non-numeric quantity - covers type validation branch
        response = self.client.post("/orders/", json={"symbol": "AAPL", "side": "buy", "qty": "invalid"})
        assert response.status_code == 422
        error_detail = response.json()["detail"]
        assert any("quantity" in str(error).lower() for error in error_detail)
        
        # Test case 5: Symbol too long - covers symbol length validation branch
        response = self.client.post("/orders/", json={"symbol": "VERYLONGSYMBOL", "side": "buy", "qty": 100})
        assert response.status_code == 422
    
    @patch('backend.api.routes.orders.require_trader')
    @patch('backend.api.routes.orders.get_risk_manager')
    def test_submit_order_risk_rejection_branch(self, mock_get_risk_manager, mock_require_trader):
        """Test POST /orders/ - risk management rejection branch"""
        
        mock_user = {"user_id": "test_user_123"}
        mock_require_trader.return_value = mock_user
        
        # Setup risk manager to reject - covers risk rejection branch
        mock_risk_manager = Mock()
        mock_risk_manager.check_trade_risk.return_value = {
            "approved": False, 
            "reason": "Quantity too large"
        }
        mock_get_risk_manager.return_value = mock_risk_manager
        
        order_data = {
            "symbol": "AAPL",
            "side": "buy", 
            "qty": 1500  # Large quantity to trigger risk rejection
        }
        
        response = self.client.post("/orders/", json=order_data)
        
        # Verify risk rejection response - covers risk failure branch
        assert response.status_code == 400
        assert "Risk check failed" in response.json()["detail"]
        assert "Quantity too large" in response.json()["detail"]
    
    @patch('backend.api.routes.orders.require_trader')
    @patch('backend.api.routes.orders.get_risk_manager')
    @patch('backend.api.routes.orders.get_order_service')
    def test_submit_order_service_exception_branch(self, mock_get_order_service, mock_get_risk_manager, mock_require_trader):
        """Test POST /orders/ - service exception handling branch"""
        
        mock_user = {"user_id": "test_user_123"}
        mock_require_trader.return_value = mock_user
        
        # Setup risk manager approval
        mock_risk_manager = Mock()
        mock_risk_manager.check_trade_risk.return_value = {"approved": True}
        mock_get_risk_manager.return_value = mock_risk_manager
        
        # Setup order service to raise exception - covers exception handling branch
        mock_order_service = AsyncMock()
        mock_order_service.submit_order.side_effect = Exception("Database connection failed")
        mock_get_order_service.return_value = mock_order_service
        
        order_data = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100
        }
        
        response = self.client.post("/orders/", json=order_data)
        
        # Verify exception handling - covers exception branch
        assert response.status_code == 500
        assert "Internal Server Error" in response.json()["detail"]
    
    @patch('backend.services.order_service.submit_order')
    @patch('backend.api.routes.orders.require_trader')
    def test_submit_order_backend_service_patch_exception(self, mock_require_trader, mock_backend_submit):
        """Test POST /orders/ - backend service patch exception branch"""
        
        mock_user = {"user_id": "test_user_123"}
        mock_require_trader.return_value = mock_user
        
        # Setup backend service to raise exception - covers patched service exception branch
        mock_backend_submit.side_effect = RuntimeError("Backend service error")
        
        order_data = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100
        }
        
        response = self.client.post("/orders/", json=order_data)
        
        # Verify backend service exception handling - covers patch exception branch
        assert response.status_code == 500
        assert "Internal Server Error" in response.json()["detail"]
    
    @patch('backend.api.routes.orders.require_trader')
    @patch('backend.api.routes.orders.get_order_service')
    def test_submit_order_submit_endpoint(self, mock_get_order_service, mock_require_trader):
        """Test POST /orders/submit - compatibility endpoint coverage"""
        
        mock_user = {"user_id": "test_user_123"}
        mock_require_trader.return_value = mock_user
        
        # Setup order service mock
        mock_order_service = AsyncMock()
        expected_response = OrderSubmissionResponse(
            order_id="order_456",
            status="submitted",
            symbol="GOOGL",
            side="sell",
            qty=50.0,
            submitted_at=datetime.now().isoformat()
        )
        mock_order_service.submit_order.return_value = expected_response
        mock_get_order_service.return_value = mock_order_service
        
        order_data = {
            "symbol": "GOOGL",
            "side": "sell",
            "qty": 50
        }
        
        response = self.client.post("/orders/submit", json=order_data)
        
        # Verify compatibility endpoint - covers /submit path
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["order_id"] == "order_456"
        assert response_data["symbol"] == "GOOGL"
    
    @patch('backend.api.routes.orders.require_trader')
    @patch('backend.api.routes.orders.get_order_service')
    def test_get_order_status_success(self, mock_get_order_service, mock_require_trader):
        """Test GET /orders/{order_id} - successful order status retrieval"""
        
        mock_user = {"user_id": "test_user_123"}
        mock_require_trader.return_value = mock_user
        
        # Setup order service mock - successful retrieval path
        mock_order_service = AsyncMock()
        expected_response = OrderStatusResponse(
            order_id="test_order_123",
            status="filled",
            symbol="AAPL",
            side="buy",
            qty=100.0,
            filled_qty=100.0,
            avg_fill_price=150.0,
            submitted_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        mock_order_service.get_order_status.return_value = expected_response
        mock_get_order_service.return_value = mock_order_service
        
        response = self.client.get("/orders/test_order_123")
        
        # Verify successful retrieval - covers success path
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["order_id"] == "test_order_123"
        assert response_data["status"] == "filled"
        assert response_data["symbol"] == "AAPL"
    
    @patch('backend.api.routes.orders.require_trader')
    @patch('backend.api.routes.orders.get_order_service')
    def test_get_order_status_not_found(self, mock_get_order_service, mock_require_trader):
        """Test GET /orders/{order_id} - order not found branch"""
        
        mock_user = {"user_id": "test_user_123"}
        mock_require_trader.return_value = mock_user
        
        # Setup order service mock - not found path
        mock_order_service = AsyncMock()
        mock_order_service.get_order_status.return_value = None
        mock_get_order_service.return_value = mock_order_service
        
        response = self.client.get("/orders/nonexistent_order")
        
        # Verify not found handling - covers not found branch
        assert response.status_code == 404
        assert "Order not found" in response.json()["detail"]
    
    @patch('backend.api.routes.orders.require_trader')
    @patch('backend.api.routes.orders.get_order_service')
    def test_get_order_status_service_exception(self, mock_get_order_service, mock_require_trader):
        """Test GET /orders/{order_id} - service exception branch"""
        
        mock_user = {"user_id": "test_user_123"}
        mock_require_trader.return_value = mock_user
        
        # Setup order service mock - exception path
        mock_order_service = AsyncMock()
        mock_order_service.get_order_status.side_effect = Exception("Database error")
        mock_get_order_service.return_value = mock_order_service
        
        response = self.client.get("/orders/test_order_123")
        
        # Verify exception handling - covers exception branch
        assert response.status_code == 500
        assert "Failed to get order status" in response.json()["detail"]
    
    @patch('backend.api.routes.orders.require_trader')
    @patch('backend.api.routes.orders.get_order_service')
    def test_cancel_order_success(self, mock_get_order_service, mock_require_trader):
        """Test POST /orders/{order_id}/cancel - successful cancellation"""
        
        mock_user = {"user_id": "test_user_123"}
        mock_require_trader.return_value = mock_user
        
        # Setup order service mock - successful cancellation path
        mock_order_service = AsyncMock()
        mock_order_service.cancel_order.return_value = {
            "order_id": "test_order_123",
            "status": "cancelled",
            "updated_at": datetime.now().isoformat()
        }
        mock_get_order_service.return_value = mock_order_service
        
        response = self.client.post("/orders/test_order_123/cancel")
        
        # Verify successful cancellation - covers success path
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["order_id"] == "test_order_123"
        assert response_data["status"] == "cancelled"
        assert "cancelled_at" in response_data
    
    @patch('backend.api.routes.orders.require_trader')
    @patch('backend.api.routes.orders.get_order_service')
    def test_cancel_order_not_found(self, mock_get_order_service, mock_require_trader):
        """Test POST /orders/{order_id}/cancel - order not found branch"""
        
        mock_user = {"user_id": "test_user_123"}
        mock_require_trader.return_value = mock_user
        
        # Setup order service mock - not found path
        mock_order_service = AsyncMock()
        mock_order_service.cancel_order.return_value = None
        mock_get_order_service.return_value = mock_order_service
        
        response = self.client.post("/orders/nonexistent_order/cancel")
        
        # Verify not found handling - covers not found branch
        assert response.status_code == 404
        assert "Order not found" in response.json()["detail"]
    
    @patch('backend.api.routes.orders.require_trader')
    @patch('backend.api.routes.orders.get_order_service')
    def test_cancel_order_service_exception(self, mock_get_order_service, mock_require_trader):
        """Test POST /orders/{order_id}/cancel - service exception branch"""
        
        mock_user = {"user_id": "test_user_123"}
        mock_require_trader.return_value = mock_user
        
        # Setup order service mock - exception path
        mock_order_service = AsyncMock()
        mock_order_service.cancel_order.side_effect = Exception("Cancellation failed")
        mock_get_order_service.return_value = mock_order_service
        
        response = self.client.post("/orders/test_order_123/cancel")
        
        # Verify exception handling - covers exception branch
        assert response.status_code == 500
        assert "Failed to cancel order" in response.json()["detail"]
    
    def test_get_order_audit_trail(self):
        """Test GET /orders/{order_id}/audit - audit trail retrieval"""
        
        response = self.client.get("/orders/test_order_123/audit")
        
        # Verify audit trail response - covers audit endpoint
        assert response.status_code == 200
        response_data = response.json()
        assert "entries" in response_data
        assert len(response_data["entries"]) >= 2
        
        # Verify audit entry structure
        for entry in response_data["entries"]:
            assert "timestamp" in entry
            assert "event_type" in entry
            assert "order_id" in entry
            assert entry["order_id"] == "test_order_123"
    
    def test_authentication_required_branches(self):
        """Test authentication requirement across all endpoints"""
        
        # Test POST /orders/ without authentication
        with patch('backend.api.routes.orders.require_trader') as mock_require_trader:
            mock_require_trader.side_effect = Exception("Authentication required")
            
            response = self.client.post("/orders/", json={"symbol": "AAPL", "side": "buy", "qty": 100})
            assert response.status_code == 500  # Exception handling
        
        # Test GET /orders/{order_id} without authentication
        with patch('backend.api.routes.orders.require_trader') as mock_require_trader:
            mock_require_trader.side_effect = Exception("Authentication required")
            
            response = self.client.get("/orders/test_order_123")
            assert response.status_code == 500  # Exception handling
        
        # Test POST /orders/{order_id}/cancel without authentication
        with patch('backend.api.routes.orders.require_trader') as mock_require_trader:
            mock_require_trader.side_effect = Exception("Authentication required")
            
            response = self.client.post("/orders/test_order_123/cancel")
            assert response.status_code == 500  # Exception handling


class TestOrderServiceDependencies:
    """Test the dependency injection system and mock services"""
    
    def test_get_order_service_singleton(self):
        """Test order service singleton behavior"""
        from backend.api.routes.orders import get_order_service
        
        # First call creates instance
        service1 = get_order_service()
        # Second call returns same instance
        service2 = get_order_service()
        
        assert service1 is service2  # Singleton behavior
    
    def test_get_risk_manager_instantiation(self):
        """Test risk manager dependency instantiation"""
        from backend.api.routes.orders import get_risk_manager
        
        risk_manager = get_risk_manager()
        
        # Test risk check functionality
        result = risk_manager.check_trade_risk("AAPL", "buy", 100)
        assert result["approved"] is True
        
        # Test quantity limit
        result = risk_manager.check_trade_risk("AAPL", "buy", 1500)
        assert result["approved"] is False
        assert "Quantity too large" in result["reason"]
    
    @patch('backend.api.routes.orders.get_current_user')
    def test_require_trader_dependency(self, mock_get_current_user):
        """Test trader authentication dependency"""
        from backend.api.routes.orders import require_trader
        
        # Test with authenticated user
        mock_get_current_user.return_value = {"user_id": "test_user", "role": "trader"}
        user = require_trader()
        assert user["user_id"] == "test_user"
        
        # Test with no user - should raise HTTPException
        mock_get_current_user.return_value = None
        with pytest.raises(Exception):  # HTTPException
            require_trader()


class TestOrderModels:
    """Test Pydantic models used in order routes"""
    
    def test_order_submission_request_validation(self):
        """Test OrderSubmissionRequest model validation"""
        from backend.api.routes.orders import OrderSubmissionRequest
        
        # Valid request
        valid_request = OrderSubmissionRequest(
            symbol="AAPL",
            side="buy", 
            qty=100.0,
            order_type="market",
            time_in_force="day"
        )
        assert valid_request.symbol == "AAPL"
        assert valid_request.qty == 100.0
        
        # Test validation - negative quantity should fail
        with pytest.raises(Exception):  # Pydantic validation error
            OrderSubmissionRequest(
                symbol="AAPL",
                side="buy",
                qty=-10.0  # Invalid negative quantity
            )
    
    def test_order_response_models(self):
        """Test response model serialization"""
        from backend.api.routes.orders import OrderSubmissionResponse, OrderStatusResponse
        
        # Test OrderSubmissionResponse
        submission_response = OrderSubmissionResponse(
            order_id="order_123",
            status="submitted",
            symbol="AAPL",
            side="buy",
            qty=100.0,
            submitted_at=datetime.now().isoformat()
        )
        
        # Test OrderStatusResponse
        status_response = OrderStatusResponse(
            order_id="order_123",
            status="filled",
            symbol="AAPL",
            side="buy",
            qty=100.0,
            filled_qty=100.0,
            avg_fill_price=150.0,
            submitted_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        assert submission_response.order_id == "order_123"
        assert status_response.filled_qty == 100.0


# Edge case and integration tests
class TestOrdersEdgeCaseCoverage:
    """Edge case testing for maximum branch coverage"""
    
    @classmethod
    def setup_class(cls):
        """Setup test FastAPI app"""
        if not ROUTES_AVAILABLE:
            pytest.skip("Routes not available for testing")
        
        cls.app = FastAPI()
        cls.app.include_router(orders_router)
        cls.client = TestClient(cls.app)
    
    @patch('backend.api.routes.orders.require_trader')
    def test_empty_request_body(self, mock_require_trader):
        """Test handling of empty request body"""
        mock_user = {"user_id": "test_user_123"}
        mock_require_trader.return_value = mock_user
        
        # Test with None body
        response = self.client.post("/orders/", json=None)
        assert response.status_code == 422
        
        # Test with empty dict body
        response = self.client.post("/orders/", json={})
        assert response.status_code == 422
    
    @patch('backend.api.routes.orders.require_trader')
    def test_malformed_json_handling(self, mock_require_trader):
        """Test handling of malformed JSON"""
        mock_user = {"user_id": "test_user_123"}
        mock_require_trader.return_value = mock_user
        
        # FastAPI will handle JSON parsing errors before reaching our code
        # This test ensures our validation handles missing fields
        response = self.client.post("/orders/", json={"invalid": "data"})
        assert response.status_code == 422
    
    @patch('backend.api.routes.orders.require_trader')
    def test_special_characters_in_order_id(self, mock_require_trader):
        """Test order ID handling with special characters"""
        mock_user = {"user_id": "test_user_123"}
        mock_require_trader.return_value = mock_user
        
        # Test with special characters in order ID
        special_order_id = "order-123_test.special"
        response = self.client.get(f"/orders/{special_order_id}")
        
        # Should handle gracefully (will return 404 since order doesn't exist)
        assert response.status_code == 404


if __name__ == "__main__":
    print("🚀 Phase 3.1 - Orders Route Coverage Testing")
    print("Target: 100% coverage for backend/api/routes/orders.py (164 statements)")
    
    # Run the tests
    pytest.main([__file__, "-v", "--tb=short"])