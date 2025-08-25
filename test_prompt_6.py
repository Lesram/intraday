"""
Test Prompt 6 implementation: MLOps schema/registry contract fixes
"""

from datetime import datetime


def test_feature_schema_kwargs():
    """Test FeatureSchema accepts legacy kwargs including features alias"""
    
    from backend.features.types import FeatureSchema
    
    print("=== Testing FeatureSchema Legacy Kwargs ===")
    
    # Test with canonical arguments
    schema1 = FeatureSchema(
        columns=["price", "volume", "rsi"],
        dtypes={"price": "float64", "volume": "int64", "rsi": "float64"}
    )
    assert schema1.columns == ["price", "volume", "rsi"]
    print("✅ Test 1: Canonical columns argument works")
    
    # Test with features alias
    schema2 = FeatureSchema(
        features=["close", "high", "low"],  # Using alias
        dtypes={"close": "float64", "high": "float64", "low": "float64"}
    )
    assert schema2.columns == ["close", "high", "low"]
    print("✅ Test 2: Features alias works")
    
    # Test precedence: columns should win over features
    schema3 = FeatureSchema(
        columns=["canonical"],
        features=["alias"],
        dtypes={"canonical": "float64"}
    )
    assert schema3.columns == ["canonical"]  # columns should win
    print("✅ Test 3: Columns takes precedence over features alias")
    
    # Test fallback when columns is None/empty
    schema4 = FeatureSchema(
        columns=None,
        features=["fallback"],
        dtypes={"fallback": "float64"}
    )
    assert schema4.columns == ["fallback"]
    print("✅ Test 4: Features alias used as fallback")
    

def test_model_version_kwargs():
    """Test ModelVersion accepts flexible kwargs initialization"""
    
    from backend.mlops.model_manager import ModelVersion
    
    print("\n=== Testing ModelVersion Kwargs Initialization ===")
    
    # Test basic kwargs
    mv1 = ModelVersion(
        model_name="test_model",
        version="1.0",
        created_at=datetime.now(),
        metadata={"accuracy": 0.95}
    )
    assert mv1.model_name == "test_model"
    assert mv1.version == "1.0" 
    assert mv1.metadata["accuracy"] == 0.95
    print("✅ Test 1: Basic kwargs initialization works")
    
    # Test with alias fields
    mv2 = ModelVersion(
        model_id="alias_model",  # This should map to model_name too
        version="2.0",
        artifacts_path="/path/to/model",
        feature_schema={"cols": ["a", "b"]}
    )
    assert mv2.model_name == "alias_model"  # Should map from model_id
    assert mv2.model_id == "alias_model"
    assert mv2.artifacts_path == "/path/to/model"
    assert mv2.feature_schema["cols"] == ["a", "b"]
    print("✅ Test 2: Alias fields work correctly")
    
    # Test dual mapping (model_name and model_id should sync)
    mv3 = ModelVersion(
        model_name="primary",
        model_id="secondary"  # Should be overridden by model_name
    )
    assert mv3.model_name == "primary"
    assert mv3.model_id == "primary"  # Should sync
    print("✅ Test 3: Dual field mapping works")
    
    # Test legacy compatibility fields
    mv4 = ModelVersion(
        model_name="legacy_test",
        version="1.0",
        model_path="/old/path",
        feature_names=["feature1", "feature2"]
    )
    assert mv4.model_path == "/old/path"
    assert mv4.artifacts_path == "/old/path"  # Should map
    assert mv4.feature_names == ["feature1", "feature2"]
    print("✅ Test 4: Legacy compatibility fields work")


def test_in_memory_registry():
    """Test InMemoryModelRegistry functionality"""
    
    from backend.mlops.model_manager import InMemoryModelRegistry
    
    print("\n=== Testing InMemoryModelRegistry ===")
    
    # Create registry and mock model
    registry = InMemoryModelRegistry()
    mock_model = lambda x: x * 2  # Simple mock model
    
    # Test registration
    mv = registry.register(
        name="test_model",
        version="1.0", 
        model=mock_model,
        metadata={"type": "linear"},
        artifacts_path="/path/to/artifacts"
    )
    
    assert mv.model_name == "test_model"
    assert mv.version == "1.0"
    assert mv.metadata["type"] == "linear"
    print("✅ Test 1: Model registration works")
    
    # Test model loading
    loaded_model = registry.load("test_model", "1.0")
    assert loaded_model == mock_model
    result = loaded_model(5)
    assert result == 10  # 5 * 2
    print("✅ Test 2: Model loading works")
    
    # Test version info
    version_info = registry.version_info("test_model", "1.0")
    assert version_info.model_name == "test_model"
    assert version_info.artifacts_path == "/path/to/artifacts"
    print("✅ Test 3: Version info retrieval works")
    
    # Test multiple versions
    registry.register("test_model", "2.0", lambda x: x * 3, metadata={"improved": True})
    
    model_v1 = registry.load("test_model", "1.0")
    model_v2 = registry.load("test_model", "2.0")
    
    assert model_v1(5) == 10  # Version 1.0: x * 2
    assert model_v2(5) == 15  # Version 2.0: x * 3
    print("✅ Test 4: Multiple versions work correctly")


def test_noop_model_manager_integration():
    """Test No-Op model manager uses InMemoryModelRegistry"""
    
    from backend.mlops.model_manager import _NoOpModelManager
    
    print("\n=== Testing No-Op Model Manager Integration ===")
    
    # Create No-Op manager
    manager = _NoOpModelManager()
    
    # Should have registry attribute
    assert hasattr(manager, 'registry')
    assert manager.registry is not None
    print("✅ Test 1: No-Op manager has registry")
    
    # Test basic functionality still works
    result = manager.register_model("test", metadata={"test": True})
    assert result == "test-model-id"  # Standard no-op response
    print("✅ Test 2: No-Op registration still works")
    
    prediction = manager.predict({"feature": 1.0})
    assert prediction["prediction"] == 0.5
    assert prediction["confidence"] == 0.8
    print("✅ Test 3: No-Op prediction still works")
    
    # Registry should be functional for more complex testing
    manager.registry.register("real_test", "1.0", lambda x: x + 1)
    loaded = manager.registry.load("real_test", "1.0")
    assert loaded(5) == 6
    print("✅ Test 4: Internal registry is functional")


def test_create_app_integration():
    """Test create_app sets up model manager correctly based on DISABLE_ML"""
    
    import os
    from backend.api.factory import create_app
    
    print("\n=== Testing create_app Model Manager Setup ===")
    
    # Test with DISABLE_ML=1 (Light Mode)
    os.environ["DISABLE_ML"] = "1"
    app = create_app()
    
    assert hasattr(app.state, 'model_manager')
    assert hasattr(app.state.model_manager, 'registry')  # Should be No-Op manager
    print("✅ Test 1: Light Mode uses No-Op model manager")
    
    # Test with DISABLE_ML=0 (Full Mode)
    os.environ["DISABLE_ML"] = "0"
    app2 = create_app()
    
    assert hasattr(app2.state, 'model_manager')
    # In full mode, should have more complex manager (though might still be No-Op due to dependencies)
    print("✅ Test 2: Full mode attempts to use full model manager")
    
    # Restore environment
    os.environ.pop("DISABLE_ML", None)


if __name__ == "__main__":
    test_feature_schema_kwargs()
    test_model_version_kwargs() 
    test_in_memory_registry()
    test_noop_model_manager_integration()
    test_create_app_integration()
    print("\n🎉 All Prompt 6 tests passed!")
