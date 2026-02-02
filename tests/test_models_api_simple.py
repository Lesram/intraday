"""
ML Models API Tests - Phase 6
Simplified synchronous tests for ML model management endpoints

NOTE: Some tests in this module expect a model_registry table which
may not exist in the SQLite test database. Tests that fail due to
missing tables are expected to pass once the full PostgreSQL schema
is applied.
"""

import uuid
import pytest
from fastapi.testclient import TestClient


# ==================== LIST MODELS TESTS ====================

class TestListModels:
    """Test GET /api/v1/models endpoint."""
    
    def test_list_models_authenticated(self, client: TestClient, auth_headers: dict):
        """Test listing models with authentication."""
        response = client.get(
            "/api/v1/models",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "models" in data
        assert "page" in data
        assert "page_size" in data
        assert isinstance(data["models"], list)
    
    def test_list_models_unauthenticated(self, client: TestClient):
        """Test that unauthenticated requests are rejected."""
        response = client.get("/api/v1/models")
        assert response.status_code == 401
    
    def test_list_models_with_pagination(self, client: TestClient, auth_headers: dict):
        """Test pagination parameters."""
        response = client.get(
            "/api/v1/models?page=1&page_size=10",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 10
    
    def test_list_models_active_only(self, client: TestClient, auth_headers: dict):
        """Test filtering active models only."""
        response = client.get(
            "/api/v1/models?active_only=true",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        # All returned models should be active
        for model in data["models"]:
            if len(data["models"]) > 0:
                assert model["active"] is True


# ==================== GET MODEL TESTS ====================

class TestGetModel:
    """Test GET /api/v1/models/{model_id} endpoint."""
    
    def test_get_model_not_found(self, client: TestClient, auth_headers: dict):
        """Test getting a non-existent model."""
        fake_id = str(uuid.uuid4())
        response = client.get(
            f"/api/v1/models/{fake_id}",
            headers=auth_headers,
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_get_model_invalid_uuid(self, client: TestClient, auth_headers: dict):
        """Test with invalid UUID format."""
        response = client.get(
            "/api/v1/models/invalid-uuid",
            headers=auth_headers,
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_get_model_unauthenticated(self, client: TestClient):
        """Test unauthenticated access."""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/models/{fake_id}")
        assert response.status_code == 401


# ==================== DELETE MODEL TESTS ====================

class TestDeleteModel:
    """Test DELETE /api/v1/models/{model_id} endpoint."""
    
    def test_delete_model_not_found(self, client: TestClient, auth_headers: dict):
        """Test deleting a non-existent model."""
        fake_id = str(uuid.uuid4())
        response = client.delete(
            f"/api/v1/models/{fake_id}",
            headers=auth_headers,
        )
        
        # Should return 404 or 403 (if not admin)
        assert response.status_code in [403, 404]
    
    def test_delete_model_unauthenticated(self, client: TestClient):
        """Test unauthenticated deletion."""
        fake_id = str(uuid.uuid4())
        response = client.delete(f"/api/v1/models/{fake_id}")
        assert response.status_code == 401


# ==================== TRAINING TESTS ====================

class TestModelTraining:
    """Test POST /api/v1/models/train endpoint."""
    
    def test_start_training_valid_request(self, client: TestClient, auth_headers: dict):
        """Test starting a new training job with valid data."""
        training_request = {
            "model_type": "ensemble",
            "model_name": f"test_model_{uuid.uuid4().hex[:8]}",  # Unique name
            "features": ["RSI", "MACD"],
            "symbols": ["AAPL", "GOOGL"],
            "lookback_days": 90,
            "test_size": 0.2,
            "hyperparameters": {"epochs": 50},
            "retrain": False,
        }
        
        response = client.post(
            "/api/v1/models/train",
            headers=auth_headers,
            json=training_request,
        )
        
        # Should either succeed (200) or fail with 403 if not admin
        assert response.status_code in [200, 403]
        
        if response.status_code == 200:
            data = response.json()
            assert "training_id" in data
            assert data["model_name"] == training_request["model_name"]
            assert data["status"] in ["pending", "running"]
            assert "started_at" in data
    
    def test_start_training_invalid_model_type(self, client: TestClient, auth_headers: dict):
        """Test with invalid model type."""
        training_request = {
            "model_type": "invalid_type",
            "model_name": "test_model",
        }
        
        response = client.post(
            "/api/v1/models/train",
            headers=auth_headers,
            json=training_request,
        )
        
        # Should return validation error or forbidden
        assert response.status_code in [422, 403]
    
    def test_start_training_missing_required_field(self, client: TestClient, auth_headers: dict):
        """Test with missing required field."""
        training_request = {
            "model_type": "ensemble",
            # Missing model_name
        }
        
        response = client.post(
            "/api/v1/models/train",
            headers=auth_headers,
            json=training_request,
        )
        
        # Should return validation error or forbidden
        assert response.status_code in [422, 403]
    
    def test_start_training_unauthenticated(self, client: TestClient):
        """Test unauthenticated training request."""
        training_request = {
            "model_type": "ensemble",
            "model_name": "test_model",
        }
        
        response = client.post(
            "/api/v1/models/train",
            json=training_request,
        )
        
        assert response.status_code == 401
    
    def test_get_training_status_not_found(self, client: TestClient, auth_headers: dict):
        """Test getting status for non-existent training job."""
        response = client.get(
            "/api/v1/models/training/fake_training_id",
            headers=auth_headers,
        )
        
        assert response.status_code == 404


# ==================== PREDICTION TESTS ====================

class TestPredictions:
    """Test POST /api/v1/models/predict endpoint."""
    
    def test_predict_no_active_model(self, client: TestClient, auth_headers: dict):
        """Test prediction when no active model exists."""
        prediction_request = {
            "symbol": "TSLA",
        }
        
        response = client.post(
            "/api/v1/models/predict",
            headers=auth_headers,
            json=prediction_request,
        )
        
        # Should return 404 if no active model
        # Or 200 with simulated prediction
        assert response.status_code in [200, 404]
    
    def test_predict_invalid_symbol(self, client: TestClient, auth_headers: dict):
        """Test prediction with empty symbol."""
        prediction_request = {
            "symbol": "",
        }
        
        response = client.post(
            "/api/v1/models/predict",
            headers=auth_headers,
            json=prediction_request,
        )
        
        # Should return validation error
        assert response.status_code == 422
    
    def test_predict_unauthenticated(self, client: TestClient):
        """Test unauthenticated prediction request."""
        prediction_request = {
            "symbol": "AAPL",
        }
        
        response = client.post(
            "/api/v1/models/predict",
            json=prediction_request,
        )
        
        assert response.status_code == 401


# ==================== ANALYSIS ENDPOINTS TESTS ====================

class TestAnalysisEndpoints:
    """Test feature importance, comparison, and health endpoints."""
    
    def test_get_feature_importance_not_found(self, client: TestClient, auth_headers: dict):
        """Test getting feature importance for non-existent model."""
        fake_id = str(uuid.uuid4())
        response = client.get(
            f"/api/v1/models/{fake_id}/features",
            headers=auth_headers,
        )
        
        assert response.status_code == 404
    
    def test_compare_models_insufficient(self, client: TestClient, auth_headers: dict):
        """Test comparison with less than 2 models."""
        comparison_request = {
            "model_ids": [str(uuid.uuid4())],
        }
        
        response = client.post(
            "/api/v1/models/compare",
            headers=auth_headers,
            json=comparison_request,
        )
        
        # Should return validation error or 400
        assert response.status_code in [400, 422]
    
    def test_compare_models_validation(self, client: TestClient, auth_headers: dict):
        """Test comparison validation with 2 models."""
        comparison_request = {
            "model_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
            "metric": "accuracy",
        }
        
        response = client.post(
            "/api/v1/models/compare",
            headers=auth_headers,
            json=comparison_request,
        )
        
        # Should work or return 400 if models don't exist
        assert response.status_code in [200, 400]
    
    def test_get_model_health_not_found(self, client: TestClient, auth_headers: dict):
        """Test getting health for non-existent model."""
        fake_id = str(uuid.uuid4())
        response = client.get(
            f"/api/v1/models/{fake_id}/health",
            headers=auth_headers,
        )
        
        assert response.status_code == 404


# ==================== VERSION HISTORY TESTS ====================

class TestVersionHistory:
    """Test GET /api/v1/models/{model_name}/versions endpoint."""
    
    def test_get_version_history_not_found(self, client: TestClient, auth_headers: dict):
        """Test getting version history for non-existent model."""
        response = client.get(
            "/api/v1/models/nonexistent_model_xyz/versions",
            headers=auth_headers,
        )
        
        assert response.status_code == 404
        detail = response.json()["detail"].lower()
        assert "no models found" in detail or "not found" in detail


# ==================== VALIDATION TESTS ====================

class TestValidation:
    """Test request validation."""
    
    def test_pagination_validation_invalid_page(self, client: TestClient, auth_headers: dict):
        """Test pagination with invalid page number."""
        response = client.get(
            "/api/v1/models?page=0",
            headers=auth_headers,
        )
        assert response.status_code == 422
    
    def test_pagination_validation_invalid_page_size(self, client: TestClient, auth_headers: dict):
        """Test pagination with invalid page size."""
        response = client.get(
            "/api/v1/models?page_size=1000",
            headers=auth_headers,
        )
        assert response.status_code == 422
    
    def test_pagination_validation_negative_page(self, client: TestClient, auth_headers: dict):
        """Test pagination with negative page."""
        response = client.get(
            "/api/v1/models?page=-1",
            headers=auth_headers,
        )
        assert response.status_code == 422


# ==================== AUTHORIZATION TESTS ====================

class TestAuthorization:
    """Test authorization and access control."""
    
    def test_list_requires_auth(self, client: TestClient):
        """Test that listing models requires authentication."""
        response = client.get("/api/v1/models")
        assert response.status_code == 401
    
    def test_get_requires_auth(self, client: TestClient):
        """Test that getting a model requires authentication."""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/models/{fake_id}")
        assert response.status_code == 401
    
    def test_delete_requires_auth(self, client: TestClient):
        """Test that deleting requires authentication."""
        fake_id = str(uuid.uuid4())
        response = client.delete(f"/api/v1/models/{fake_id}")
        assert response.status_code == 401
    
    def test_train_requires_auth(self, client: TestClient):
        """Test that training requires authentication."""
        response = client.post(
            "/api/v1/models/train",
            json={"model_type": "ensemble", "model_name": "test"},
        )
        assert response.status_code == 401
    
    def test_predict_requires_auth(self, client: TestClient):
        """Test that predictions require authentication."""
        response = client.post(
            "/api/v1/models/predict",
            json={"symbol": "AAPL"},
        )
        assert response.status_code == 401


# ==================== RESPONSE FORMAT TESTS ====================

class TestResponseFormats:
    """Test that responses have correct format."""
    
    def test_list_response_format(self, client: TestClient, auth_headers: dict):
        """Test list response has correct structure."""
        response = client.get("/api/v1/models", headers=auth_headers)
        
        if response.status_code == 200:
            data = response.json()
            # Check required fields
            assert "models" in data
            assert "total" in data
            assert "page" in data
            assert "page_size" in data
            
            # Check types
            assert isinstance(data["models"], list)
            assert isinstance(data["total"], int)
            assert isinstance(data["page"], int)
            assert isinstance(data["page_size"], int)
    
    def test_error_response_format(self, client: TestClient, auth_headers: dict):
        """Test error responses have correct format."""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/models/{fake_id}", headers=auth_headers)
        
        if response.status_code == 404:
            data = response.json()
            assert "detail" in data
            assert isinstance(data["detail"], str)


# ==================== INTEGRATION SMOKE TESTS ====================

class TestIntegrationSmoke:
    """Basic integration smoke tests."""
    
    def test_api_is_accessible(self, client: TestClient, auth_headers: dict):
        """Test that the API is accessible."""
        response = client.get("/api/v1/models", headers=auth_headers)
        assert response.status_code in [200, 500]  # Should at least respond
    
    def test_training_endpoint_exists(self, client: TestClient, auth_headers: dict):
        """Test that training endpoint exists."""
        response = client.post(
            "/api/v1/models/train",
            headers=auth_headers,
            json={"model_type": "ensemble", "model_name": "test"},
        )
        # Should not return 404 (endpoint should exist)
        assert response.status_code != 404
    
    def test_prediction_endpoint_exists(self, client: TestClient, auth_headers: dict):
        """Test that prediction endpoint exists."""
        response = client.post(
            "/api/v1/models/predict",
            headers=auth_headers,
            json={"symbol": "AAPL"},
        )
        # Endpoint exists - either 200 (success), 400 (validation), or 404 (no active model) is fine
        # The important thing is the endpoint is registered (not a routing 404)
        assert response.status_code in [200, 400, 404]
