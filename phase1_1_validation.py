#!/usr/bin/env python3
"""
Phase 1.1 Validation Script: Mock Object Alignment
Tests that the new standardized mocks resolve AttributeError issues.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.mocks.base_mocks import (
    StandardEnsembleModelMock,
    StandardModelRegistryMock,
    StandardOrderMock,
    create_standard_registry_mock,
    generate_sample_data
)
from backend.mlops.model_manager import InMemoryModelRegistry
from unittest.mock import patch, Mock


def test_in_memory_registry_get_method():
    """Test that InMemoryModelRegistry now has get method"""
    print("🧪 Testing InMemoryModelRegistry.get() method...")
    
    registry = InMemoryModelRegistry()
    
    # Create mock ensemble
    ensemble = StandardEnsembleModelMock()
    
    # Register model
    metadata = {"accuracy": 0.85, "training_samples": 1000}
    mv = registry.register(
        name="test_ensemble", 
        version="1.0.0",
        model=ensemble,
        metadata=metadata
    )
    
    # Test get method (this was causing AttributeError before)
    result = registry.get("test_ensemble", "1.0.0")
    assert result is not None, "get() method should return result"
    assert result[0] == ensemble, "Should return the model object"
    assert result[1].metadata["accuracy"] == 0.85, "Should return correct metadata"
    
    print("✅ InMemoryModelRegistry.get() method works correctly")
    return True


def test_mlops_integration_mocks():
    """Test MLOps integration test compatibility"""
    print("🧪 Testing MLOps integration mock compatibility...")
    
    registry = StandardModelRegistryMock()
    
    # Create mock ensemble with proper settings mock
    with patch('backend.models.ensemble_model.get_settings') as mock_settings:
        mock_settings.return_value = Mock(mlops={"inference_telemetry_enabled": False})
        ensemble = StandardEnsembleModelMock()
    
    # Test registration
    metadata = {
        "training_date": "2023-01-01T00:00:00",
        "accuracy": 0.85,
        "features": ["close", "volume", "sma_20"],
        "model_type": "ensemble"
    }
    
    feature_schema = {
        "close": {"type": "float", "required": True},
        "volume": {"type": "int", "required": True},
        "sma_20": {"type": "float", "required": True}
    }
    
    # This should work without AttributeError
    mv = registry.register(
        name="test_ensemble",
        version="1.0.0", 
        model=ensemble,
        metadata=metadata,
        feature_schema=feature_schema
    )
    
    # Test get method
    retrieved = registry.get("test_ensemble", "1.0.0")
    assert retrieved is not None
    assert retrieved[0] == ensemble  # Model object
    assert retrieved[1].metadata["accuracy"] == 0.85
    
    print("✅ MLOps integration mocks work correctly")
    return True


def test_ensemble_model_mock_completeness():
    """Test that EnsembleModel mock has all expected attributes"""
    print("🧪 Testing EnsembleModel mock completeness...")
    
    ensemble = StandardEnsembleModelMock()
    
    # Test all attributes that were causing AttributeErrors
    required_attributes = [
        'models', 'weights', 'performance_history', 'settings',
        'model_manager', 'mlops_enabled'
    ]
    
    for attr in required_attributes:
        assert hasattr(ensemble, attr), f"Missing attribute: {attr}"
        value = getattr(ensemble, attr)
        # model_manager can be None when MLOps is disabled
        if attr != 'model_manager':
            assert value is not None, f"Attribute {attr} should not be None"
    
    # Test model sub-objects
    assert 'lstm' in ensemble.models
    assert 'xgboost' in ensemble.models  
    assert 'random_forest' in ensemble.models
    
    # Test weights
    assert isinstance(ensemble.weights, dict)
    assert abs(sum(ensemble.weights.values()) - 1.0) < 0.001
    
    print("✅ EnsembleModel mock has complete interface")
    return True


def test_order_mock_completeness():
    """Test that Order mock has all expected attributes"""
    print("🧪 Testing Order mock completeness...")
    
    order = StandardOrderMock()
    
    # Test all attributes that were causing AttributeErrors
    required_attributes = [
        'symbol', 'quantity', 'side', 'order_type', 'price', 'status',
        'timestamp', 'filled_quantity', 'remaining_quantity', 'fees'
    ]
    
    for attr in required_attributes:
        assert hasattr(order, attr), f"Missing attribute: {attr}"
    
    # Test methods
    assert callable(order.to_dict)
    assert callable(order.validate)
    assert callable(order.is_filled)
    
    # Test method returns
    assert isinstance(order.to_dict(), dict)
    assert isinstance(order.validate(), bool)
    assert isinstance(order.is_filled(), bool)
    
    print("✅ Order mock has complete interface")
    return True


def simulate_failing_test_fix():
    """Simulate fixing a real failing test scenario"""
    print("🧪 Simulating failing test fix...")
    
    # This simulates the exact pattern from failing tests
    registry = InMemoryModelRegistry()
    
    # Mock settings like in the failing test
    with patch('backend.models.ensemble_model.get_settings') as mock_settings:
        mock_settings.return_value = Mock(mlops={"inference_telemetry_enabled": False})
        ensemble = StandardEnsembleModelMock()
    
    # Register model like in failing test
    metadata = {
        "training_date": "2023-01-01T00:00:00", 
        "accuracy": 0.85,
        "features": ["close", "volume", "sma_20"],
        "model_type": "ensemble"
    }
    
    feature_schema = {
        "close": {"type": "float", "required": True},
        "volume": {"type": "int", "required": True}, 
        "sma_20": {"type": "float", "required": True}
    }
    
    # Register model
    registry.register(
        name="test_ensemble",
        version="1.0.0",
        model=ensemble,
        metadata=metadata,
        feature_schema=feature_schema
    )
    
    # This was the exact failing line - should work now
    retrieved = registry.get("test_ensemble", "1.0.0")
    assert retrieved is not None
    assert retrieved[0] == ensemble  # Model object  
    assert retrieved[1].metadata["accuracy"] == 0.85
    
    print("✅ Simulated failing test now passes")
    return True


def main():
    """Run all Phase 1.1 validation tests"""
    print("🎯 Phase 1.1 Validation: Mock Object Alignment")
    print("=" * 50)
    
    tests = [
        test_in_memory_registry_get_method,
        test_mlops_integration_mocks,
        test_ensemble_model_mock_completeness,
        test_order_mock_completeness,
        simulate_failing_test_fix
    ]
    
    passed = 0
    for test in tests:
        try:
            result = test()
            if result:
                passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} failed: {e}")
    
    print("=" * 50)
    print(f"✅ Phase 1.1 Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎊 Phase 1.1 Mock Alignment: READY FOR DEPLOYMENT")
        return True
    else:
        print("⚠️ Phase 1.1: Some issues remain, review failures")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
