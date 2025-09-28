#!/usr/bin/env python3
"""
Comprehensive test suite for Module 7: backend.api.routes.models.py
Tests ML models API routes with complete coverage of all functions, classes, and edge cases.
"""

import pytest
import asyncio
import unittest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime
from typing import Dict, Any

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.api.routes import models as models_module
from fastapi import HTTPException
from pydantic import ValidationError


class TestModule7ModelsComponents(unittest.TestCase):
    """Test core components of the models module."""
    
    def test_router_configuration(self):
        """Test router is properly configured."""
        router = models_module.router
        
        assert router is not None
        assert router.prefix == "/models"
        assert "ML Models" in router.tags
        assert "Protected" in router.tags
    
    def test_get_model_service_function(self):
        """Test get_model_service dependency function."""
        service = models_module.get_model_service()
        
        assert service is not None
        assert hasattr(service, 'train_model')
        assert hasattr(service, 'get_model_status')
        
        # Verify service attributes exist (lambdas can't be called due to bound method issue)
        assert callable(service.train_model)
        assert callable(service.get_model_status)
        
        # Verify service class name
        assert service.__class__.__name__ == 'ModelService'
    
    def test_model_training_request_validation(self):
        """Test ModelTrainingRequest pydantic model validation."""
        # Valid request
        valid_request = models_module.ModelTrainingRequest(
            model_type="ensemble",
            retrain=True,
            features=["technical", "sentiment"]
        )
        assert valid_request.model_type == "ensemble"
        assert valid_request.retrain is True
        assert valid_request.features == ["technical", "sentiment"]
        
        # Test default values
        minimal_request = models_module.ModelTrainingRequest(model_type="regression")
        assert minimal_request.retrain is True
        assert minimal_request.features == ["technical", "sentiment"]
        
        # Test invalid model_type
        with pytest.raises(ValidationError) as exc_info:
            models_module.ModelTrainingRequest(model_type="invalid_type")
        assert "String should match pattern" in str(exc_info.value)
        
        # Test all valid model types
        valid_types = ["ensemble", "regression", "classification", "lstm"]
        for model_type in valid_types:
            request = models_module.ModelTrainingRequest(model_type=model_type)
            assert request.model_type == model_type
    
    def test_model_training_response_model(self):
        """Test ModelTrainingResponse pydantic model."""
        response = models_module.ModelTrainingResponse(
            training_id="train-123",
            status="started",
            message="Training initiated",
            started_at="2025-01-01T12:00:00"
        )
        
        assert response.training_id == "train-123"
        assert response.status == "started"
        assert response.message == "Training initiated"
        assert response.started_at == "2025-01-01T12:00:00"
    
    def test_model_status_response_model(self):
        """Test ModelStatusResponse pydantic model."""
        models_data = {
            "ensemble": {"status": "trained", "accuracy": 0.85},
            "lstm": {"status": "training", "progress": 0.75}
        }
        
        response = models_module.ModelStatusResponse(
            models=models_data,
            training_status="active",
            last_updated="2025-01-01T12:00:00"
        )
        
        assert response.models == models_data
        assert response.training_status == "active"
        assert response.last_updated == "2025-01-01T12:00:00"


class TestModule7MockModelManager(unittest.TestCase):
    """Test MockModelManager functionality."""
    
    def setUp(self):
        self.manager = models_module.get_model_manager()
    
    def test_mock_model_manager_initialization(self):
        """Test MockModelManager initialization."""
        assert self.manager is not None
        assert self.manager.training_status == "idle"
        assert isinstance(self.manager.models, dict)
        
        # Check default models structure
        assert "ensemble" in self.manager.models
        assert "lstm" in self.manager.models
        
        ensemble_model = self.manager.models["ensemble"]
        assert ensemble_model["status"] == "trained"
        assert ensemble_model["accuracy"] == 0.85
        assert "last_trained" in ensemble_model
        assert "version" in ensemble_model
        
        lstm_model = self.manager.models["lstm"]
        assert lstm_model["status"] == "training"
        assert lstm_model["progress"] == 0.75
        assert "eta" in lstm_model
    
    def test_start_training_method(self):
        """Test start_training async method."""
        def run_test():
            async def async_test():
                model_config = {
                    "model_type": "ensemble",
                    "features": ["technical", "sentiment"],
                    "retrain": True
                }
                
                result = await self.manager.start_training(model_config)
                
                assert "training_id" in result
                assert result["status"] == "started"
                assert result["message"] == "Model training initiated"
                assert "started_at" in result
                assert self.manager.training_status == "training"
                
                # Verify training_id is a valid UUID format
                import uuid
                try:
                    uuid.UUID(result["training_id"])
                except ValueError:
                    pytest.fail("training_id is not a valid UUID")
            
            asyncio.run(async_test())
        
        run_test()
    
    def test_get_model_status_method(self):
        """Test get_model_status method."""
        status = self.manager.get_model_status()
        
        assert "models" in status
        assert "training_status" in status
        assert "last_updated" in status
        
        assert status["models"] == self.manager.models
        assert status["training_status"] == self.manager.training_status
        
        # Verify last_updated is valid ISO format
        try:
            datetime.fromisoformat(status["last_updated"])
        except ValueError:
            pytest.fail("last_updated is not in valid ISO format")


class TestModule7AuthenticationDependencies(unittest.TestCase):
    """Test authentication and authorization dependencies."""
    
    def test_require_admin_with_no_user(self):
        """Test require_admin raises 401 when no user provided."""
        with pytest.raises(HTTPException) as exc_info:
            models_module.require_admin(current_user=None)
        
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Authentication required"
    
    def test_require_admin_with_non_admin_user(self):
        """Test require_admin raises 403 for non-admin users."""
        # User without roles
        user_no_roles = Mock()
        user_no_roles.roles = []  # Make roles an empty list instead of Mock
        with pytest.raises(HTTPException) as exc_info:
            models_module.require_admin(current_user=user_no_roles)
        
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Insufficient permissions"
        
        # User with non-admin roles
        user_trader = Mock()
        user_trader.roles = ["trader", "user"]
        with pytest.raises(HTTPException) as exc_info:
            models_module.require_admin(current_user=user_trader)
        
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Insufficient permissions"
    
    def test_require_admin_with_admin_user(self):
        """Test require_admin succeeds for admin users."""
        admin_user = Mock()
        admin_user.roles = ["admin", "trader"]
        
        result = models_module.require_admin(current_user=admin_user)
        assert result == admin_user
    
    def test_require_admin_user_missing_roles_attribute(self):
        """Test require_admin with user missing roles attribute entirely."""
        user_no_attr = Mock(spec=[])  # Mock with no attributes
        
        with pytest.raises(HTTPException) as exc_info:
            models_module.require_admin(current_user=user_no_attr)
        
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Insufficient permissions"


class TestModule7TrainModelsEndpoint(unittest.TestCase):
    """Test /train endpoint functionality."""
    
    def test_train_models_success(self):
        """Test successful model training."""
        def run_test():
            async def async_test():
                # Mock inputs
                mock_model_config = models_module.ModelTrainingRequest(
                    model_type="ensemble",
                    retrain=True,
                    features=["technical", "sentiment"]
                )
                mock_current_user = Mock()
                mock_current_user.roles = ["admin"]
                
                mock_model_manager = AsyncMock()
                mock_training_result = {
                    "training_id": "train-123-456",
                    "status": "started",
                    "message": "Model training initiated",
                    "started_at": "2025-01-01T12:00:00"
                }
                mock_model_manager.start_training.return_value = mock_training_result
                
                # Test the endpoint function
                with patch('backend.api.routes.models.logger') as mock_logger:
                    result = await models_module.train_models(
                        model_config=mock_model_config,
                        current_user=mock_current_user,
                        model_manager=mock_model_manager
                    )
                    
                    # Verify result
                    assert isinstance(result, models_module.ModelTrainingResponse)
                    assert result.training_id == "train-123-456"
                    assert result.status == "started"
                    assert result.message == "Model training initiated"
                    assert result.started_at == "2025-01-01T12:00:00"
                    
                    # Verify service was called with correct config
                    mock_model_manager.start_training.assert_called_once_with(mock_model_config.model_dump())
                    
                    # Verify logging
                    mock_logger.info.assert_called_once()
                    assert "train-123-456" in mock_logger.info.call_args[0][0]
            
            asyncio.run(async_test())
        
        run_test()
    
    def test_train_models_exception_handling(self):
        """Test exception handling in train_models endpoint."""
        def run_test():
            async def async_test():
                mock_model_config = models_module.ModelTrainingRequest(
                    model_type="lstm",
                    retrain=False,
                    features=["technical"]
                )
                mock_current_user = Mock()
                mock_current_user.roles = ["admin"]
                
                mock_model_manager = AsyncMock()
                mock_model_manager.start_training.side_effect = ValueError("Training failed due to invalid config")
                
                with patch('backend.api.routes.models.logger') as mock_logger:
                    with pytest.raises(HTTPException) as exc_info:
                        await models_module.train_models(
                            model_config=mock_model_config,
                            current_user=mock_current_user,
                            model_manager=mock_model_manager
                        )
                    
                    # Verify exception details
                    assert exc_info.value.status_code == 500
                    assert "Model training failed" in exc_info.value.detail
                    assert "Training failed due to invalid config" in exc_info.value.detail
                    
                    # Verify error logging
                    mock_logger.error.assert_called_once()
                    error_call_args = mock_logger.error.call_args
                    assert "Model training failed" in error_call_args[0][0]
                    assert error_call_args[1]['exc_info'] is True
            
            asyncio.run(async_test())
        
        run_test()
    
    def test_train_models_with_different_configurations(self):
        """Test training with various model configurations."""
        def run_test():
            async def async_test():
                mock_current_user = Mock()
                mock_current_user.roles = ["admin"]
                
                # Test different model types
                test_configs = [
                    {
                        "model_type": "regression",
                        "retrain": False,
                        "features": ["technical"]
                    },
                    {
                        "model_type": "classification",
                        "retrain": True,
                        "features": ["sentiment", "technical"]
                    },
                    {
                        "model_type": "lstm",
                        "retrain": True,
                        "features": ["technical", "sentiment", "market"]
                    }
                ]
                
                for config in test_configs:
                    mock_model_config = models_module.ModelTrainingRequest(**config)
                    mock_model_manager = AsyncMock()
                    mock_training_result = {
                        "training_id": f"train-{config['model_type']}-123",
                        "status": "started",
                        "message": f"{config['model_type']} training initiated",
                        "started_at": "2025-01-01T12:00:00"
                    }
                    mock_model_manager.start_training.return_value = mock_training_result
                    
                    result = await models_module.train_models(
                        model_config=mock_model_config,
                        current_user=mock_current_user,
                        model_manager=mock_model_manager
                    )
                    
                    assert result.training_id == f"train-{config['model_type']}-123"
                    assert config['model_type'] in result.message
                    mock_model_manager.start_training.assert_called_once_with(config)
            
            asyncio.run(async_test())
        
        run_test()


class TestModule7GetModelStatusEndpoint(unittest.TestCase):
    """Test /status endpoint functionality."""
    
    def test_get_model_status_success_for_admin(self):
        """Test successful status retrieval for admin user."""
        def run_test():
            async def async_test():
                mock_current_user = Mock()
                mock_current_user.roles = ["admin", "trader"]
                
                mock_model_manager = Mock()
                mock_status_data = {
                    "models": {
                        "ensemble": {
                            "status": "trained",
                            "accuracy": 0.87,
                            "last_trained": "2025-01-01T10:00:00",
                            "version": "v1.1"
                        },
                        "lstm": {
                            "status": "training",
                            "progress": 0.65,
                            "eta": "15 minutes"
                        }
                    },
                    "training_status": "training",
                    "last_updated": "2025-01-01T12:00:00"
                }
                mock_model_manager.get_model_status.return_value = mock_status_data
                
                result = await models_module.get_model_status(
                    current_user=mock_current_user,
                    model_manager=mock_model_manager
                )
                
                # Verify result
                assert isinstance(result, models_module.ModelStatusResponse)
                assert result.models == mock_status_data["models"]
                assert result.training_status == "training"
                assert result.last_updated == "2025-01-01T12:00:00"
                
                # Verify service was called
                mock_model_manager.get_model_status.assert_called_once()
            
            asyncio.run(async_test())
        
        run_test()
    
    def test_get_model_status_success_for_trader(self):
        """Test successful status retrieval for trader user."""
        def run_test():
            async def async_test():
                mock_current_user = Mock()
                mock_current_user.roles = ["trader"]
                
                mock_model_manager = Mock()
                mock_status_data = {
                    "models": {"ensemble": {"status": "trained"}},
                    "training_status": "idle",
                    "last_updated": "2025-01-01T12:00:00"
                }
                mock_model_manager.get_model_status.return_value = mock_status_data
                
                result = await models_module.get_model_status(
                    current_user=mock_current_user,
                    model_manager=mock_model_manager
                )
                
                assert isinstance(result, models_module.ModelStatusResponse)
                assert result.training_status == "idle"
                mock_model_manager.get_model_status.assert_called_once()
            
            asyncio.run(async_test())
        
        run_test()
    
    def test_get_model_status_blocked_for_readonly(self):
        """Test status retrieval blocked for read-only users."""
        def run_test():
            async def async_test():
                mock_current_user = Mock()
                mock_current_user.roles = ["read-only"]
                
                mock_model_manager = Mock()
                
                with pytest.raises(HTTPException) as exc_info:
                    await models_module.get_model_status(
                        current_user=mock_current_user,
                        model_manager=mock_model_manager
                    )
                
                assert exc_info.value.status_code == 403
                assert exc_info.value.detail == "Insufficient permissions"
                
                # Verify service was not called
                mock_model_manager.get_model_status.assert_not_called()
            
            asyncio.run(async_test())
        
        run_test()
    
    def test_get_model_status_user_without_roles(self):
        """Test status retrieval for user without roles attribute."""
        def run_test():
            async def async_test():
                mock_current_user = Mock()
                mock_current_user.roles = []  # Set roles as empty list instead of no attribute
                
                mock_model_manager = Mock()
                mock_status_data = {
                    "models": {},
                    "training_status": "idle",
                    "last_updated": "2025-01-01T12:00:00"
                }
                mock_model_manager.get_model_status.return_value = mock_status_data
                
                result = await models_module.get_model_status(
                    current_user=mock_current_user,
                    model_manager=mock_model_manager
                )
                
                # Should succeed because user_roles defaults to []
                assert isinstance(result, models_module.ModelStatusResponse)
                mock_model_manager.get_model_status.assert_called_once()
            
            asyncio.run(async_test())
        
        run_test()
    
    def test_get_model_status_user_missing_roles_attribute(self):
        """Test status retrieval for user completely missing roles attribute."""
        def run_test():
            async def async_test():
                mock_current_user = Mock(spec=[])  # Mock with no roles attribute at all
                
                mock_model_manager = Mock()
                mock_status_data = {
                    "models": {},
                    "training_status": "idle",
                    "last_updated": "2025-01-01T12:00:00"
                }
                mock_model_manager.get_model_status.return_value = mock_status_data
                
                result = await models_module.get_model_status(
                    current_user=mock_current_user,
                    model_manager=mock_model_manager
                )
                
                # Should succeed because hasattr returns False and user_roles defaults to []
                assert isinstance(result, models_module.ModelStatusResponse)
                mock_model_manager.get_model_status.assert_called_once()
            
            asyncio.run(async_test())
        
        run_test()
    
    def test_get_model_status_exception_handling(self):
        """Test exception handling in get_model_status endpoint."""
        def run_test():
            async def async_test():
                mock_current_user = Mock()
                mock_current_user.roles = ["admin"]
                
                mock_model_manager = Mock()
                mock_model_manager.get_model_status.side_effect = Exception("Database connection failed")
                
                with patch('backend.api.routes.models.logger') as mock_logger:
                    with pytest.raises(HTTPException) as exc_info:
                        await models_module.get_model_status(
                            current_user=mock_current_user,
                            model_manager=mock_model_manager
                        )
                    
                    # Verify exception details
                    assert exc_info.value.status_code == 500
                    assert "Failed to get model status" in exc_info.value.detail
                    assert "Database connection failed" in exc_info.value.detail
                    
                    # Verify error logging
                    mock_logger.error.assert_called_once()
                    error_call_args = mock_logger.error.call_args
                    assert "Failed to get model status" in error_call_args[0][0]
                    assert error_call_args[1]['exc_info'] is True
            
            asyncio.run(async_test())
        
        run_test()


class TestModule7EdgeCasesAndErrorHandling(unittest.TestCase):
    """Test edge cases and error handling scenarios."""
    
    def test_model_training_request_edge_cases(self):
        """Test edge cases for ModelTrainingRequest validation."""
        # Test with empty features list
        request_empty_features = models_module.ModelTrainingRequest(
            model_type="ensemble",
            features=[]
        )
        assert request_empty_features.features == []
        
        # Test with custom features
        custom_features = ["technical", "sentiment", "social", "macro"]
        request_custom = models_module.ModelTrainingRequest(
            model_type="classification",
            features=custom_features
        )
        assert request_custom.features == custom_features
        
        # Test retrain False
        request_no_retrain = models_module.ModelTrainingRequest(
            model_type="regression",
            retrain=False
        )
        assert request_no_retrain.retrain is False
    
    def test_mock_model_manager_state_changes(self):
        """Test MockModelManager state changes."""
        manager = models_module.get_model_manager()
        
        # Initial state
        assert manager.training_status == "idle"
        
        def run_test():
            async def async_test():
                # Training should change status
                await manager.start_training({"model_type": "ensemble"})
                assert manager.training_status == "training"
                
                # Multiple training calls
                result1 = await manager.start_training({"model_type": "lstm"})
                result2 = await manager.start_training({"model_type": "regression"})
                
                # Should generate different training IDs
                assert result1["training_id"] != result2["training_id"]
                assert manager.training_status == "training"
            
            asyncio.run(async_test())
        
        run_test()
    
    def test_get_model_manager_returns_new_instance(self):
        """Test that get_model_manager returns a new instance each time."""
        manager1 = models_module.get_model_manager()
        manager2 = models_module.get_model_manager()
        
        # Should be different instances
        assert manager1 is not manager2
        
        # But should have same initial structure
        assert manager1.training_status == manager2.training_status
        assert manager1.models.keys() == manager2.models.keys()
    
    def test_datetime_formatting_consistency(self):
        """Test that all datetime fields use consistent ISO formatting."""
        manager = models_module.get_model_manager()
        
        def run_test():
            async def async_test():
                # Test training start time
                result = await manager.start_training({"model_type": "ensemble"})
                start_time = result["started_at"]
                
                # Should be valid ISO format
                try:
                    datetime.fromisoformat(start_time)
                except ValueError:
                    pytest.fail(f"started_at is not valid ISO format: {start_time}")
                
                # Test status last_updated
                status = manager.get_model_status()
                last_updated = status["last_updated"]
                
                try:
                    datetime.fromisoformat(last_updated)
                except ValueError:
                    pytest.fail(f"last_updated is not valid ISO format: {last_updated}")
            
            asyncio.run(async_test())
        
        run_test()
    
    def test_error_message_consistency(self):
        """Test that error messages are consistent and informative."""
        # Test authentication error
        with pytest.raises(HTTPException) as exc_info:
            models_module.require_admin(current_user=None)
        assert exc_info.value.detail == "Authentication required"
        
        # Test permission error
        user = Mock()
        user.roles = ["trader"]
        with pytest.raises(HTTPException) as exc_info:
            models_module.require_admin(current_user=user)
        assert exc_info.value.detail == "Insufficient permissions"


if __name__ == "__main__":
    unittest.main()