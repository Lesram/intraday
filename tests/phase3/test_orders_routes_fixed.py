"""
Phase 3.1 - Fixed API Routes Coverage Testing
Target: Real coverage of orders.py with proper FastAPI testing setup
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from fastapi.testclient import TestClient
from fastapi import FastAPI, status, HTTPException
from datetime import datetime, timezone
import json

# Create a test app that bypasses authentication
def create_test_app():
    """Create test FastAPI app with authentication bypassed"""
    app = FastAPI()
    
    # Mock the authentication dependency to always return a test user
    def override_require_trader():
        return {"user_id": "test_user_123", "role": "trader"}
    
    # Mock the get_current_user dependency
    def override_get_current_user():
        return {"user_id": "test_user_123", "role": "trader"}
    
    # Override dependencies
    from backend.api.routes.orders import require_trader
    from backend.infra.security import get_current_user
    
    app.dependency_overrides[require_trader] = override_require_trader
    app.dependency_overrides[get_current_user] = override_get_current_user
    
    # Import and include the router
    try:
        from backend.api.routes.orders import router as orders_router
        app.include_router(orders_router)
        return app
    except ImportError:
        return None


class TestOrdersRouteCoverageFixed:
    """Fixed comprehensive coverage testing for orders.py"""
    
    @classmethod
    def setup_class(cls):
        """Setup test app with authentication bypassed"""
        cls.app = create_test_app()
        if cls.app is None:
            pytest.skip("Orders router not available")
        cls.client = TestClient(cls.app)
    
    def setup_method(self):
        """Reset global state before each test"""
        import backend.api.routes.orders
        backend.api.routes.orders._mock_order_service_instance = None
    
    @patch('backend.api.routes.orders.get_risk_manager')
    @patch('backend.api.routes.orders.get_order_service')
    def test_submit_order_success_main_execution_path(self, mock_get_order_service, mock_get_risk_manager):
        """Test POST /orders/ - main success path coverage"""
        
        # Setup risk manager mock - approval path
        mock_risk_manager = Mock()
        mock_risk_manager.check_trade_risk.return_value = {"approved": True}
        mock_get_risk_manager.return_value = mock_risk_manager
        
        # Setup order service mock - success path
        from backend.api.routes.orders import OrderSubmissionResponse
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
        
        # Execute request - covers main execution path
        response = self.client.post("/orders/", json=order_data)
        
        # Verify response - covers success return path
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["order_id"] == "order_123"
        assert response_data["symbol"] == "AAPL"
        assert response_data["status"] == "submitted"
        
        # Verify interactions - covers service integration branches
        mock_risk_manager.check_trade_risk.assert_called_once_with("AAPL", "BUY", 100.0)
        mock_order_service.submit_order.assert_called_once()
    
    def test_submit_order_validation_error_branches(self):
        """Test validation error branches - covers all validation paths"""
        
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
        
        # Test case 5: Symbol too long - covers length validation branch
        response = self.client.post("/orders/", json={"symbol": "VERYLONGSYMBOL", "side": "buy", "qty": 100})
        assert response.status_code == 422
    
    @patch('backend.api.routes.orders.get_risk_manager')
    def test_submit_order_risk_rejection_branch(self, mock_get_risk_manager):
        """Test risk management rejection branch"""
        
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
    
    @patch('backend.api.routes.orders.get_risk_manager')
    @patch('backend.api.routes.orders.get_order_service')
    def test_submit_order_service_exception_branch(self, mock_get_order_service, mock_get_risk_manager):
        """Test service exception handling branch"""
        
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
    def test_submit_order_backend_service_exception_branch(self, mock_backend_submit):
        """Test backend service exception handling branch"""
        
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
    
    @patch('backend.api.routes.orders.get_order_service')
    def test_submit_order_submit_endpoint_coverage(self, mock_get_order_service):
        """Test POST /orders/submit - compatibility endpoint coverage"""
        
        # Setup order service mock
        from backend.api.routes.orders import OrderSubmissionResponse
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
    
    @patch('backend.api.routes.orders.get_order_service')
    def test_get_order_status_success_path(self, mock_get_order_service):
        """Test GET /orders/{order_id} - successful retrieval path"""
        
        # Setup order service mock - successful retrieval path
        from backend.api.routes.orders import OrderStatusResponse
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
    
    @patch('backend.api.routes.orders.get_order_service')
    def test_get_order_status_not_found_branch(self, mock_get_order_service):
        """Test GET /orders/{order_id} - not found branch"""
        
        # Setup order service mock - not found path
        mock_order_service = AsyncMock()
        mock_order_service.get_order_status.return_value = None
        mock_get_order_service.return_value = mock_order_service
        
        response = self.client.get("/orders/nonexistent_order")
        
        # Verify not found handling - covers not found branch
        assert response.status_code == 404
        assert "Order not found" in response.json()["detail"]
    
    @patch('backend.api.routes.orders.get_order_service')
    def test_get_order_status_exception_branch(self, mock_get_order_service):
        """Test GET /orders/{order_id} - service exception branch"""
        
        # Setup order service mock - exception path
        mock_order_service = AsyncMock()
        mock_order_service.get_order_status.side_effect = Exception("Database error")
        mock_get_order_service.return_value = mock_order_service
        
        response = self.client.get("/orders/test_order_123")
        
        # Verify exception handling - covers exception branch
        assert response.status_code == 500
        assert "Failed to get order status" in response.json()["detail"]
    
    @patch('backend.api.routes.orders.get_order_service')
    def test_cancel_order_success_path(self, mock_get_order_service):
        """Test POST /orders/{order_id}/cancel - successful cancellation"""
        
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
    
    @patch('backend.api.routes.orders.get_order_service')
    def test_cancel_order_not_found_branch(self, mock_get_order_service):
        """Test POST /orders/{order_id}/cancel - not found branch"""
        
        # Setup order service mock - not found path
        mock_order_service = AsyncMock()
        mock_order_service.cancel_order.return_value = None
        mock_get_order_service.return_value = mock_order_service
        
        response = self.client.post("/orders/nonexistent_order/cancel")
        
        # Verify not found handling - covers not found branch
        assert response.status_code == 404
        assert "Order not found" in response.json()["detail"]
    
    @patch('backend.api.routes.orders.get_order_service')
    def test_cancel_order_exception_branch(self, mock_get_order_service):
        """Test POST /orders/{order_id}/cancel - service exception branch"""
        
        # Setup order service mock - exception path
        mock_order_service = AsyncMock()
        mock_order_service.cancel_order.side_effect = Exception("Cancellation failed")
        mock_get_order_service.return_value = mock_order_service
        
        response = self.client.post("/orders/test_order_123/cancel")
        
        # Verify exception handling - covers exception branch
        assert response.status_code == 500
        assert "Failed to cancel order" in response.json()["detail"]
    
    def test_get_order_audit_trail_coverage(self):
        """Test GET /orders/{order_id}/audit - audit trail endpoint"""
        
        response = self.client.get("/orders/test_order_123/audit")
        
        # Verify audit trail response - covers audit endpoint
        assert response.status_code == 200
        response_data = response.json()
        assert "entries" in response_data
        assert len(response_data["entries"]) >= 2
        
        # Verify audit entry structure - covers audit data model
        for entry in response_data["entries"]:
            assert "timestamp" in entry
            assert "event_type" in entry
            assert "order_id" in entry
            assert entry["order_id"] == "test_order_123"


class TestOrderServiceComponents:
    """Test order service components for coverage"""
    
    def test_order_service_singleton_behavior(self):
        """Test get_order_service singleton implementation"""
        from backend.api.routes.orders import get_order_service
        
        # Reset singleton
        import backend.api.routes.orders
        backend.api.routes.orders._mock_order_service_instance = None
        
        # First call creates instance
        service1 = get_order_service()
        # Second call returns same instance
        service2 = get_order_service()
        
        assert service1 is service2  # Covers singleton branch
    
    def test_risk_manager_approval_logic(self):
        """Test risk manager check_trade_risk logic"""
        from backend.api.routes.orders import get_risk_manager
        
        risk_manager = get_risk_manager()
        
        # Test approval for normal quantity - covers approval branch
        result = risk_manager.check_trade_risk("AAPL", "buy", 100)
        assert result["approved"] is True
        
        # Test rejection for large quantity - covers rejection branch
        result = risk_manager.check_trade_risk("AAPL", "buy", 1500)
        assert result["approved"] is False
        assert "Quantity too large" in result["reason"]


class TestOrderModelsValidation:
    """Test Pydantic model validation for coverage"""
    
    def test_order_submission_request_valid_data(self):
        """Test OrderSubmissionRequest with valid data"""
        from backend.api.routes.orders import OrderSubmissionRequest
        
        # Test valid request - covers validation success path
        valid_request = OrderSubmissionRequest(
            symbol="AAPL",
            side="buy",
            qty=100.0,
            order_type="market",
            time_in_force="day",
            client_order_id="client_123"
        )
        
        assert valid_request.symbol == "AAPL"
        assert valid_request.qty == 100.0
        assert valid_request.client_order_id == "client_123"
    
    def test_order_submission_request_defaults(self):
        """Test OrderSubmissionRequest default values"""
        from backend.api.routes.orders import OrderSubmissionRequest
        
        # Test with minimal required fields - covers default value paths
        minimal_request = OrderSubmissionRequest(
            symbol="GOOGL",
            side="sell",
            qty=50.0
        )
        
        assert minimal_request.order_type == "market"  # Default value
        assert minimal_request.time_in_force == "day"  # Default value
        assert minimal_request.client_order_id is None  # Default value
    
    def test_order_submission_request_validation_errors(self):
        """Test OrderSubmissionRequest validation failures"""
        from backend.api.routes.orders import OrderSubmissionRequest
        import pytest
        
        # Test negative quantity validation - covers validation error path
        with pytest.raises(Exception):  # Pydantic ValidationError
            OrderSubmissionRequest(
                symbol="AAPL",
                side="buy",
                qty=-10.0  # Invalid negative quantity
            )
    
    def test_response_model_serialization(self):
        """Test response model creation and serialization"""
        from backend.api.routes.orders import OrderSubmissionResponse, OrderStatusResponse, AuditEntry, AuditResponse
        
        # Test OrderSubmissionResponse
        submission_response = OrderSubmissionResponse(
            order_id="order_123",
            client_order_id="client_123",
            status="submitted",
            symbol="AAPL",
            side="buy",
            qty=100.0,
            submitted_at=datetime.now().isoformat()
        )
        assert submission_response.order_id == "order_123"
        
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
        assert status_response.filled_qty == 100.0
        
        # Test AuditEntry
        audit_entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            event_type="order_submitted",
            order_id="order_123",
            details={"status": "submitted"}
        )
        assert audit_entry.event_type == "order_submitted"
        
        # Test AuditResponse
        audit_response = AuditResponse(entries=[audit_entry])
        assert len(audit_response.entries) == 1


class TestEdgeCasesAndBranches:
    """Test edge cases for maximum branch coverage"""
    
    @classmethod
    def setup_class(cls):
        """Setup test app with authentication bypassed"""
        cls.app = create_test_app()
        if cls.app is None:
            pytest.skip("Orders router not available")
        cls.client = TestClient(cls.app)
    
    def test_empty_and_null_request_bodies(self):
        """Test empty/null request body handling"""
        
        # Test with None body - covers null body branch
        response = self.client.post("/orders/", json=None)
        assert response.status_code == 422
        
        # Test with empty dict body - covers empty body branch
        response = self.client.post("/orders/", json={})
        assert response.status_code == 422
    
    def test_special_characters_and_edge_values(self):
        """Test special characters and edge values"""
        
        # Test with special characters in order ID - covers ID parsing
        special_order_id = "order-123_test.special"
        response = self.client.get(f"/orders/{special_order_id}")
        # Should handle gracefully (404 since order doesn't exist)
        assert response.status_code == 404
        
        # Test with zero quantity - covers boundary validation
        response = self.client.post("/orders/", json={"symbol": "AAPL", "side": "buy", "qty": 0})
        assert response.status_code == 422


if __name__ == "__main__":
    print("🚀 Phase 3.1 - Fixed Orders Route Coverage Testing")
    print("Target: Maximum coverage for backend/api/routes/orders.py")
    
    # Run the tests
    pytest.main([__file__, "-v", "--tb=short"])