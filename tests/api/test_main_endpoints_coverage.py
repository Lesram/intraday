"""
Comprehensive API Main Endpoints Coverage Tests
Targets backend.api.main.py (955 statements) for maximum coverage impact
"""

import json
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import status


class TestMainAPIEndpointsCoverage:
    """Comprehensive coverage tests for main API endpoints"""

    @pytest.fixture
    def mock_dependencies(self):
        """Mock all major dependencies"""
        with patch('backend.api.main.WebSocketClientManager') as mock_ws_manager, \
             patch('backend.api.main.get_logger') as mock_logger, \
             patch('backend.api.main.audit_logger') as mock_audit_logger, \
             patch('backend.api.main.PROMETHEUS_AVAILABLE', True), \
             patch('backend.api.main.generate_latest') as mock_generate_latest:
            
            # Setup WebSocket manager mock
            mock_ws_manager.return_value = Mock()
            mock_ws_manager.return_value.disconnect_client = AsyncMock()
            mock_ws_manager.return_value.broadcast_message = AsyncMock()
            
            # Setup logger mocks
            mock_logger.return_value = Mock()
            mock_audit_logger.info = Mock()
            mock_audit_logger.error = Mock()
            
            # Setup Prometheus mock
            mock_generate_latest.return_value = b"# Prometheus metrics\n"
            
            yield {
                'ws_manager': mock_ws_manager,
                'logger': mock_logger,
                'audit_logger': mock_audit_logger,
                'prometheus': mock_generate_latest
            }

    @pytest.fixture
    def test_client(self, mock_dependencies):
        """Create test client with mocked dependencies"""
        # Import after mocking to ensure mocks are in place
        from backend.api.main import app
        return TestClient(app)

    def test_metrics_endpoint_success(self, test_client, mock_dependencies):
        """Test /metrics endpoint returns Prometheus format"""
        response = test_client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
        assert b"Prometheus metrics" in response.content

    def test_metrics_endpoint_prometheus_unavailable(self, mock_dependencies):
        """Test /metrics when Prometheus is unavailable"""
        with patch('backend.api.main.PROMETHEUS_AVAILABLE', False):
            from backend.api.main import app
            client = TestClient(app)
            response = client.get("/metrics")
            assert response.status_code == 503
            assert "Prometheus not available" in response.json()["detail"]

    @patch('backend.api.main.authenticate_user')
    def test_login_endpoint_success(self, mock_auth, test_client, mock_dependencies):
        """Test /auth/login endpoint success path"""
        mock_auth.return_value = {
            "access_token": "test_token_123",
            "token_type": "bearer",
            "user_id": "test_user"
        }
        
        response = test_client.post("/auth/login", data={
            "username": "test_user",
            "password": "test_password"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "test_token_123"
        assert data["token_type"] == "bearer"

    @patch('backend.api.main.authenticate_user')
    def test_login_endpoint_invalid_credentials(self, mock_auth, test_client, mock_dependencies):
        """Test /auth/login endpoint with invalid credentials"""
        mock_auth.side_effect = ValueError("Invalid credentials")
        
        response = test_client.post("/auth/login", data={
            "username": "invalid_user",
            "password": "wrong_password"
        })
        assert response.status_code == 401
        assert "Invalid credentials" in response.json()["detail"]

    @patch('backend.api.main.create_user_account')
    def test_register_endpoint_success(self, mock_create_user, test_client, mock_dependencies):
        """Test user registration endpoint success"""
        mock_create_user.return_value = {
            "user_id": "new_user_123",
            "username": "test_user",
            "created_at": "2024-01-01T00:00:00Z"
        }
        
        response = test_client.post("/auth/register", json={
            "username": "test_user",
            "email": "test@example.com",
            "password": "secure_password123"
        })
        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == "new_user_123"
        assert data["username"] == "test_user"

    @patch('backend.api.main.create_user_account')
    def test_register_endpoint_user_exists(self, mock_create_user, test_client, mock_dependencies):
        """Test user registration when user already exists"""
        mock_create_user.side_effect = ValueError("User already exists")
        
        response = test_client.post("/auth/register", json={
            "username": "existing_user",
            "email": "existing@example.com",
            "password": "password123"
        })
        assert response.status_code == 400
        assert "User already exists" in response.json()["detail"]

    @patch('backend.api.main.get_current_user')
    def test_auth_me_endpoint_success(self, mock_get_user, test_client, mock_dependencies):
        """Test /auth/me endpoint with valid token"""
        mock_get_user.return_value = {
            "user_id": "test_user_123",
            "username": "test_user",
            "email": "test@example.com",
            "roles": ["trader"]
        }
        
        response = test_client.get("/auth/me", headers={
            "Authorization": "Bearer valid_token_123"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "test_user_123"
        assert data["username"] == "test_user"

    def test_health_endpoint_success(self, test_client, mock_dependencies):
        """Test /health endpoint basic functionality"""
        with patch('backend.api.main.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.isoformat.return_value = "2024-01-01T00:00:00Z"
            
            response = test_client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "timestamp" in data

    @patch('backend.api.main.check_database_connection')
    def test_healthz_endpoint_database_healthy(self, mock_db_check, test_client, mock_dependencies):
        """Test /healthz endpoint when database is healthy"""
        mock_db_check.return_value = True
        
        response = test_client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @patch('backend.api.main.check_database_connection')
    def test_healthz_endpoint_database_unhealthy(self, mock_db_check, test_client, mock_dependencies):
        """Test /healthz endpoint when database is down"""
        mock_db_check.return_value = False
        
        response = test_client.get("/healthz")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"

    @patch('backend.api.main.check_all_dependencies')
    def test_readyz_endpoint_all_ready(self, mock_deps_check, test_client, mock_dependencies):
        """Test /readyz endpoint when all dependencies ready"""
        mock_deps_check.return_value = {"database": True, "redis": True, "broker": True}
        
        response = test_client.get("/readyz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"

    @patch('backend.api.main.check_all_dependencies')
    def test_readyz_endpoint_dependencies_not_ready(self, mock_deps_check, test_client, mock_dependencies):
        """Test /readyz endpoint when dependencies not ready"""
        mock_deps_check.return_value = {"database": True, "redis": False, "broker": False}
        
        response = test_client.get("/readyz")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not ready"

    @patch('backend.api.main.get_positions_summary')
    @patch('backend.api.main.get_current_user')
    def test_positions_endpoint_success(self, mock_get_user, mock_get_positions, test_client, mock_dependencies):
        """Test positions endpoint with valid authentication"""
        mock_get_user.return_value = {"user_id": "test_user"}
        mock_get_positions.return_value = {
            "total_positions": 5,
            "total_value": 50000.00,
            "positions": [
                {"symbol": "AAPL", "quantity": 100, "value": 15000.00},
                {"symbol": "GOOGL", "quantity": 25, "value": 35000.00}
            ]
        }
        
        response = test_client.get("/api/v1/positions", headers={
            "Authorization": "Bearer valid_token"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total_positions"] == 5
        assert len(data["positions"]) == 2

    @patch('backend.api.main.create_order')
    @patch('backend.api.main.get_current_user')
    def test_orders_create_success(self, mock_get_user, mock_create_order, test_client, mock_dependencies):
        """Test order creation endpoint success"""
        mock_get_user.return_value = {"user_id": "test_user"}
        mock_create_order.return_value = {
            "order_id": "order_123",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 100,
            "status": "pending"
        }
        
        response = test_client.post("/api/v1/orders", 
            headers={"Authorization": "Bearer valid_token"},
            json={
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 100,
                "order_type": "market"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["order_id"] == "order_123"
        assert data["status"] == "pending"

    @patch('backend.api.main.cancel_order')
    @patch('backend.api.main.get_current_user')
    def test_orders_cancel_success(self, mock_get_user, mock_cancel_order, test_client, mock_dependencies):
        """Test order cancellation endpoint success"""
        mock_get_user.return_value = {"user_id": "test_user"}
        mock_cancel_order.return_value = {
            "order_id": "order_123",
            "status": "cancelled",
            "cancelled_at": "2024-01-01T00:00:00Z"
        }
        
        response = test_client.post("/api/v1/orders/order_123/cancel",
            headers={"Authorization": "Bearer valid_token"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

    @patch('backend.api.main.execute_trade')
    @patch('backend.api.main.get_current_user')
    def test_trades_execute_deprecated(self, mock_get_user, mock_execute_trade, test_client, mock_dependencies):
        """Test deprecated trade execution endpoint"""
        mock_get_user.return_value = {"user_id": "test_user"}
        mock_execute_trade.return_value = {
            "trade_id": "trade_123",
            "symbol": "AAPL",
            "executed_at": "2024-01-01T00:00:00Z",
            "warning": "This endpoint is deprecated"
        }
        
        response = test_client.post("/api/v1/trades/execute",
            headers={"Authorization": "Bearer valid_token"},
            json={
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 100
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "warning" in data
        assert "deprecated" in data["warning"].lower()

    @patch('backend.api.main.get_trade_history')
    @patch('backend.api.main.get_current_user')
    def test_trades_history_success(self, mock_get_user, mock_get_history, test_client, mock_dependencies):
        """Test trade history endpoint success"""
        mock_get_user.return_value = {"user_id": "test_user"}
        mock_get_history.return_value = {
            "trades": [
                {"trade_id": "trade_1", "symbol": "AAPL", "side": "buy"},
                {"trade_id": "trade_2", "symbol": "GOOGL", "side": "sell"}
            ],
            "total": 2
        }
        
        response = test_client.get("/api/v1/trades/history",
            headers={"Authorization": "Bearer valid_token"},
            params={"limit": 10, "offset": 0}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["trades"]) == 2
        assert data["total"] == 2

    @patch('backend.api.main.train_model')
    @patch('backend.api.main.get_current_user')
    def test_models_train_success(self, mock_get_user, mock_train_model, test_client, mock_dependencies):
        """Test ML model training endpoint success"""
        mock_get_user.return_value = {"user_id": "test_user"}
        mock_train_model.return_value = {
            "job_id": "training_job_123",
            "status": "started",
            "estimated_completion": "2024-01-01T01:00:00Z"
        }
        
        response = test_client.post("/api/v1/models/train",
            headers={"Authorization": "Bearer valid_token"},
            json={
                "model_type": "price_predictor",
                "dataset": "historical_prices",
                "parameters": {"epochs": 100}
            }
        )
        assert response.status_code == 202
        data = response.json()
        assert data["job_id"] == "training_job_123"
        assert data["status"] == "started"

    @patch('backend.api.main.get_model_status')
    @patch('backend.api.main.get_current_user')
    def test_models_status_success(self, mock_get_user, mock_get_status, test_client, mock_dependencies):
        """Test ML model status endpoint success"""
        mock_get_user.return_value = {"user_id": "test_user"}
        mock_get_status.return_value = {
            "models": [
                {"model_id": "model_1", "status": "trained", "accuracy": 0.85},
                {"model_id": "model_2", "status": "training", "progress": 0.65}
            ]
        }
        
        response = test_client.get("/api/v1/models/status",
            headers={"Authorization": "Bearer valid_token"}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["models"]) == 2
        assert data["models"][0]["accuracy"] == 0.85

    @patch('backend.api.main.update_risk_limits')
    @patch('backend.api.main.get_current_user')
    def test_risk_limits_update_success(self, mock_get_user, mock_update_limits, test_client, mock_dependencies):
        """Test risk limits update endpoint success"""
        mock_get_user.return_value = {"user_id": "test_user"}
        mock_update_limits.return_value = {
            "max_position_size": 10000,
            "daily_loss_limit": 5000,
            "updated_at": "2024-01-01T00:00:00Z"
        }
        
        response = test_client.put("/api/v1/risk/limits",
            headers={"Authorization": "Bearer valid_token"},
            json={
                "max_position_size": 10000,
                "daily_loss_limit": 5000
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["max_position_size"] == 10000
        assert data["daily_loss_limit"] == 5000

    @patch('backend.api.main.get_risk_metrics')
    @patch('backend.api.main.get_current_user')
    def test_risk_metrics_success(self, mock_get_user, mock_get_metrics, test_client, mock_dependencies):
        """Test risk metrics endpoint success"""
        mock_get_user.return_value = {"user_id": "test_user"}
        mock_get_metrics.return_value = {
            "current_exposure": 25000.00,
            "var_95": 2500.00,
            "sharpe_ratio": 1.85,
            "max_drawdown": 0.12
        }
        
        response = test_client.get("/api/v1/risk/metrics",
            headers={"Authorization": "Bearer valid_token"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["current_exposure"] == 25000.00
        assert data["var_95"] == 2500.00


class TestMainAPIErrorHandling:
    """Test comprehensive error handling in main API"""

    @pytest.fixture
    def test_client(self):
        """Create test client for error handling tests"""
        with patch('backend.api.main.WebSocketClientManager'), \
             patch('backend.api.main.get_logger'), \
             patch('backend.api.main.audit_logger'):
            from backend.api.main import app
            return TestClient(app)

    def test_validation_error_handling(self, test_client):
        """Test that validation errors return 422"""
        response = test_client.post("/auth/register", json={
            "username": "",  # Invalid empty username
            "email": "invalid-email",  # Invalid email format
            "password": "123"  # Too short password
        })
        assert response.status_code == 422

    def test_authentication_error_handling(self, test_client):
        """Test that unauthenticated requests return 401"""
        response = test_client.get("/api/v1/positions")  # Protected endpoint
        assert response.status_code == 401

    @patch('backend.api.main.get_current_user')
    def test_authorization_error_handling(self, mock_get_user, test_client):
        """Test that unauthorized requests return 403"""
        mock_get_user.side_effect = PermissionError("Insufficient permissions")
        
        response = test_client.get("/api/v1/positions", headers={
            "Authorization": "Bearer invalid_token"
        })
        assert response.status_code in [401, 403]

    def test_not_found_error_handling(self, test_client):
        """Test that non-existent endpoints return 404"""
        response = test_client.get("/api/v1/nonexistent-endpoint")
        assert response.status_code == 404

    def test_method_not_allowed_error_handling(self, test_client):
        """Test that wrong HTTP methods return 405"""
        response = test_client.delete("/health")  # Health endpoint only supports GET
        assert response.status_code == 405


class TestMainAPIWebSocketConnections:
    """Test WebSocket connection handling in main API"""

    @pytest.fixture
    def mock_websocket_dependencies(self):
        """Mock WebSocket related dependencies"""
        with patch('backend.api.main.WebSocketClientManager') as mock_manager, \
             patch('backend.api.main.get_logger') as mock_logger, \
             patch('backend.api.main.audit_logger') as mock_audit_logger:
            
            mock_manager_instance = Mock()
            mock_manager.return_value = mock_manager_instance
            mock_manager_instance.connect_client = AsyncMock()
            mock_manager_instance.disconnect_client = AsyncMock()
            mock_manager_instance.send_message = AsyncMock()
            
            yield {
                'manager': mock_manager,
                'manager_instance': mock_manager_instance,
                'logger': mock_logger,
                'audit_logger': mock_audit_logger
            }

    @pytest.fixture
    def test_client(self, mock_websocket_dependencies):
        """Create test client with WebSocket mocks"""
        from backend.api.main import app
        return TestClient(app)

    def test_websocket_endpoint_exists(self, test_client, mock_websocket_dependencies):
        """Test that WebSocket endpoint is accessible"""
        # WebSocket testing requires special handling in FastAPI TestClient
        # This is a basic structure test to ensure the endpoint exists
        from backend.api.main import app
        
        # Check that the WebSocket route exists in the app
        websocket_routes = [route for route in app.routes if hasattr(route, 'path') and '/ws/' in route.path]
        assert len(websocket_routes) > 0
        
        # Verify the specific route pattern exists
        realtime_routes = [route for route in websocket_routes if '/ws/realtime/' in route.path]
        assert len(realtime_routes) > 0


class TestMainAPILifecycleManagement:
    """Test application lifecycle and startup/shutdown handling"""

    @pytest.fixture
    def mock_lifecycle_dependencies(self):
        """Mock lifecycle related dependencies"""
        with patch('backend.api.main.WebSocketClientManager') as mock_ws_manager, \
             patch('backend.api.main.get_logger') as mock_logger, \
             patch('backend.api.main.initialize_database') as mock_init_db, \
             patch('backend.api.main.cleanup_resources') as mock_cleanup:
            
            yield {
                'ws_manager': mock_ws_manager,
                'logger': mock_logger,
                'init_db': mock_init_db,
                'cleanup': mock_cleanup
            }

    def test_application_startup_lifecycle(self, mock_lifecycle_dependencies):
        """Test application startup initialization"""
        from backend.api.main import app
        
        # Create test client to trigger startup
        with TestClient(app) as client:
            # Basic request to ensure app started successfully
            response = client.get("/health")
            assert response.status_code in [200, 503]  # Either healthy or dependencies not mocked
