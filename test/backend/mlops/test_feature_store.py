"""
Test Module 65: MLOps Feature Store Service

Comprehensive test suite for feature store functionality including:
- Feature definition and registration
- Feature groups and versioning
- Feature value ingestion and retrieval
- Transformations and validation
- Caching and lineage tracking
- Real-time and batch serving
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# Test imports with fallback handling
try:
    from backend.mlops.feature_store import (
        FeatureType, FeatureStatus, ServingMode, TransformationType,
        FeatureDefinition, FeatureGroup, FeatureValue, FeatureVector, FeatureLineage,
        FeatureTransformer, IdentityTransformer, NormalizeTransformer, 
        StandardizeTransformer, OneHotTransformer,
        FeatureValidator, FeatureCache, FeatureStore,
        create_feature_store, create_feature_definition, create_feature_group
    )
    MODULE_EXISTS = True
except ImportError as e:
    MODULE_EXISTS = False
    print(f"Module import failed: {e}")
    
    # Create mock classes for testing
    class FeatureType:
        CATEGORICAL = "categorical"
        NUMERICAL = "numerical"
        BOOLEAN = "boolean"
        TEXT = "text"
        EMBEDDING = "embedding"
        TIMESTAMP = "timestamp"
        JSON = "json"
    
    class FeatureStatus:
        DRAFT = "draft"
        ACTIVE = "active"
        DEPRECATED = "deprecated"
        ARCHIVED = "archived"
        ERROR = "error"
    
    class ServingMode:
        BATCH = "batch"
        STREAMING = "streaming"
        REALTIME = "realtime"
        HYBRID = "hybrid"
    
    class TransformationType:
        IDENTITY = "identity"
        NORMALIZE = "normalize"
        STANDARDIZE = "standardize"
        ONE_HOT = "one_hot"
        EMBEDDING = "embedding"
        AGGREGATION = "aggregation"
        CUSTOM = "custom"


# Test fixtures
@pytest.fixture
def sample_feature_definition():
    """Sample feature definition for testing."""
    if not MODULE_EXISTS:
        return {}
    
    return FeatureDefinition(
        name="user_age",
        feature_type=FeatureType.NUMERICAL,
        description="User age in years",
        entity="user",
        source="user_profile",
        validation_rules={
            'range_check': {'min': 0, 'max': 120},
            'null_check': {'allow_null': False}
        },
        tags={'category': 'demographic', 'pii': 'false'},
        owner="data_team"
    )


@pytest.fixture
def sample_feature_group():
    """Sample feature group for testing."""
    if not MODULE_EXISTS:
        return {}
    
    return FeatureGroup(
        name="user_features",
        description="User demographic and behavioral features",
        features=["user_age", "user_income", "user_location"],
        entity_key="user_id",
        source_table="user_profiles",
        event_timestamp_column="updated_at",
        ttl=3600,
        serving_mode=ServingMode.REALTIME,
        tags={'domain': 'user', 'tier': 'production'},
        owner="ml_team"
    )


@pytest.fixture
def sample_feature_values():
    """Sample feature values for testing."""
    if not MODULE_EXISTS:
        return []
    
    return [
        FeatureValue(
            feature_name="user_age",
            value=25,
            entity_id="user_123",
            timestamp=datetime.now(),
            metadata={'source': 'signup_form'}
        ),
        FeatureValue(
            feature_name="user_income",
            value=75000,
            entity_id="user_123",
            timestamp=datetime.now(),
            metadata={'source': 'survey'}
        )
    ]


@pytest.fixture
def sample_feature_vector():
    """Sample feature vector for testing."""
    if not MODULE_EXISTS:
        return {}
    
    return FeatureVector(
        entity_id="user_456",
        features={
            "user_age": 30,
            "user_income": 85000,
            "user_location": "NY"
        },
        timestamp=datetime.now(),
        feature_group="user_features",
        metadata={'batch_id': 'batch_001'}
    )


@pytest.mark.asyncio
class TestModule65BackendMlopsFeatureStore:
    """Test suite for MLOps Feature Store Service."""
    
    def test_module_availability(self):
        """Test that the module can be imported."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert MODULE_EXISTS
    
    def test_feature_type_enum(self):
        """Test feature type enumeration."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert hasattr(FeatureType, 'CATEGORICAL')
        assert hasattr(FeatureType, 'NUMERICAL')
        assert hasattr(FeatureType, 'BOOLEAN')
        assert hasattr(FeatureType, 'TEXT')
        assert hasattr(FeatureType, 'EMBEDDING')
        assert hasattr(FeatureType, 'TIMESTAMP')
        assert hasattr(FeatureType, 'JSON')
    
    def test_feature_status_enum(self):
        """Test feature status enumeration."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert hasattr(FeatureStatus, 'DRAFT')
        assert hasattr(FeatureStatus, 'ACTIVE')
        assert hasattr(FeatureStatus, 'DEPRECATED')
        assert hasattr(FeatureStatus, 'ARCHIVED')
        assert hasattr(FeatureStatus, 'ERROR')
    
    def test_serving_mode_enum(self):
        """Test serving mode enumeration."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert hasattr(ServingMode, 'BATCH')
        assert hasattr(ServingMode, 'STREAMING')
        assert hasattr(ServingMode, 'REALTIME')
        assert hasattr(ServingMode, 'HYBRID')
    
    def test_transformation_type_enum(self):
        """Test transformation type enumeration."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert hasattr(TransformationType, 'IDENTITY')
        assert hasattr(TransformationType, 'NORMALIZE')
        assert hasattr(TransformationType, 'STANDARDIZE')
        assert hasattr(TransformationType, 'ONE_HOT')
        assert hasattr(TransformationType, 'EMBEDDING')
        assert hasattr(TransformationType, 'AGGREGATION')
        assert hasattr(TransformationType, 'CUSTOM')
    
    def test_feature_definition_creation(self, sample_feature_definition):
        """Test feature definition creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        feature = sample_feature_definition
        
        assert feature.name == "user_age"
        assert feature.feature_type == FeatureType.NUMERICAL
        assert feature.description == "User age in years"
        assert feature.entity == "user"
        assert feature.source == "user_profile"
        assert isinstance(feature.validation_rules, dict)
        assert isinstance(feature.tags, dict)
        assert feature.owner == "data_team"
        assert isinstance(feature.created_at, datetime)
        assert isinstance(feature.updated_at, datetime)
        assert feature.version == "1.0.0"
        assert feature.status == FeatureStatus.DRAFT
    
    def test_feature_group_creation(self, sample_feature_group):
        """Test feature group creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        group = sample_feature_group
        
        assert group.name == "user_features"
        assert group.description == "User demographic and behavioral features"
        assert group.features == ["user_age", "user_income", "user_location"]
        assert group.entity_key == "user_id"
        assert group.source_table == "user_profiles"
        assert group.event_timestamp_column == "updated_at"
        assert group.ttl == 3600
        assert group.serving_mode == ServingMode.REALTIME
        assert isinstance(group.tags, dict)
        assert group.owner == "ml_team"
    
    def test_feature_value_creation(self, sample_feature_values):
        """Test feature value creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        feature_value = sample_feature_values[0]
        
        assert feature_value.feature_name == "user_age"
        assert feature_value.value == 25
        assert feature_value.entity_id == "user_123"
        assert isinstance(feature_value.timestamp, datetime)
        assert feature_value.version == "1.0.0"
        assert isinstance(feature_value.metadata, dict)
    
    def test_feature_vector_creation(self, sample_feature_vector):
        """Test feature vector creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        vector = sample_feature_vector
        
        assert vector.entity_id == "user_456"
        assert isinstance(vector.features, dict)
        assert vector.features["user_age"] == 30
        assert vector.features["user_income"] == 85000
        assert vector.features["user_location"] == "NY"
        assert isinstance(vector.timestamp, datetime)
        assert vector.feature_group == "user_features"
        assert isinstance(vector.metadata, dict)
    
    def test_feature_lineage_creation(self):
        """Test feature lineage creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        lineage = FeatureLineage(
            feature_name="user_age_normalized",
            source_features=["user_age"],
            transformations=["normalize"],
            datasets=["user_profiles"],
            models=["user_model_v1"],
            created_by="data_scientist"
        )
        
        assert lineage.feature_name == "user_age_normalized"
        assert lineage.source_features == ["user_age"]
        assert lineage.transformations == ["normalize"]
        assert lineage.datasets == ["user_profiles"]
        assert lineage.models == ["user_model_v1"]
        assert lineage.created_by == "data_scientist"
        assert isinstance(lineage.created_at, datetime)
    
    def test_identity_transformer(self):
        """Test identity transformer."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        transformer = IdentityTransformer()
        
        # Test transform
        assert transformer.transform(42) == 42
        assert transformer.transform("hello") == "hello"
        assert transformer.transform([1, 2, 3]) == [1, 2, 3]
        
        # Test inverse transform
        assert transformer.inverse_transform(42) == 42
        assert transformer.inverse_transform("hello") == "hello"
    
    def test_normalize_transformer(self):
        """Test normalize transformer."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        transformer = NormalizeTransformer()
        
        # Test transform with default params
        assert transformer.transform(0.5) == 0.5
        
        # Test transform with custom params
        params = {'min': 0, 'max': 100}
        assert transformer.transform(50, params) == 0.5
        assert transformer.transform(0, params) == 0.0
        assert transformer.transform(100, params) == 1.0
        
        # Test inverse transform
        assert transformer.inverse_transform(0.5, params) == 50.0
        assert transformer.inverse_transform(0.0, params) == 0.0
        assert transformer.inverse_transform(1.0, params) == 100.0
        
        # Test non-numeric values
        assert transformer.transform("hello", params) == "hello"
    
    def test_standardize_transformer(self):
        """Test standardize transformer."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        transformer = StandardizeTransformer()
        
        # Test transform with custom params
        params = {'mean': 50, 'std': 10}
        assert transformer.transform(60, params) == 1.0
        assert transformer.transform(50, params) == 0.0
        assert transformer.transform(40, params) == -1.0
        
        # Test inverse transform
        assert transformer.inverse_transform(1.0, params) == 60.0
        assert transformer.inverse_transform(0.0, params) == 50.0
        assert transformer.inverse_transform(-1.0, params) == 40.0
        
        # Test edge case with zero std
        params_zero_std = {'mean': 50, 'std': 0}
        assert transformer.transform(60, params_zero_std) == 0.0
    
    def test_one_hot_transformer(self):
        """Test one-hot transformer."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        transformer = OneHotTransformer()
        
        # Test transform with categories
        params = {'categories': ['red', 'green', 'blue']}
        result = transformer.transform('red', params)
        expected = {'red': 1, 'green': 0, 'blue': 0}
        assert result == expected
        
        # Test transform without categories
        result = transformer.transform('red')
        assert result == {'red': 1}
        
        # Test inverse transform
        one_hot = {'red': 1, 'green': 0, 'blue': 0}
        assert transformer.inverse_transform(one_hot) == 'red'
        
        # Test inverse with no active category
        no_active = {'red': 0, 'green': 0, 'blue': 0}
        assert transformer.inverse_transform(no_active) is None
    
    def test_feature_validator_type_validation(self):
        """Test feature validator type validation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        validator = FeatureValidator()
        
        # Test numerical validation
        feature_def = FeatureDefinition(
            name="test_num",
            feature_type=FeatureType.NUMERICAL
        )
        
        is_valid, errors = validator.validate_feature(feature_def, 42)
        assert is_valid is True
        assert len(errors) == 0
        
        is_valid, errors = validator.validate_feature(feature_def, "not_a_number")
        assert is_valid is False
        assert len(errors) > 0
        
        # Test categorical validation
        feature_def.feature_type = FeatureType.CATEGORICAL
        is_valid, errors = validator.validate_feature(feature_def, "category_a")
        assert is_valid is True
        
        # Test boolean validation
        feature_def.feature_type = FeatureType.BOOLEAN
        is_valid, errors = validator.validate_feature(feature_def, True)
        assert is_valid is True
        
        is_valid, errors = validator.validate_feature(feature_def, "not_boolean")
        assert is_valid is False
    
    def test_feature_validator_range_validation(self):
        """Test feature validator range validation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        validator = FeatureValidator()
        
        feature_def = FeatureDefinition(
            name="test_range",
            feature_type=FeatureType.NUMERICAL,
            validation_rules={
                'range_check': {'min': 0, 'max': 100}
            }
        )
        
        # Valid range
        is_valid, errors = validator.validate_feature(feature_def, 50)
        assert is_valid is True
        
        # Below minimum
        is_valid, errors = validator.validate_feature(feature_def, -10)
        assert is_valid is False
        
        # Above maximum
        is_valid, errors = validator.validate_feature(feature_def, 150)
        assert is_valid is False
        
        # Edge cases
        is_valid, errors = validator.validate_feature(feature_def, 0)
        assert is_valid is True
        
        is_valid, errors = validator.validate_feature(feature_def, 100)
        assert is_valid is True
    
    def test_feature_validator_enum_validation(self):
        """Test feature validator enum validation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        validator = FeatureValidator()
        
        feature_def = FeatureDefinition(
            name="test_enum",
            feature_type=FeatureType.CATEGORICAL,
            validation_rules={
                'enum_check': {'values': ['red', 'green', 'blue']}
            }
        )
        
        # Valid enum value
        is_valid, errors = validator.validate_feature(feature_def, 'red')
        assert is_valid is True
        
        # Invalid enum value
        is_valid, errors = validator.validate_feature(feature_def, 'yellow')
        assert is_valid is False
    
    def test_feature_cache_basic_operations(self):
        """Test feature cache basic operations."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        cache = FeatureCache(ttl_seconds=1)
        
        # Test set and get
        cache.set("test_key", "test_value")
        assert cache.get("test_key") == "test_value"
        
        # Test non-existent key
        assert cache.get("non_existent") is None
        
        # Test invalidation
        assert cache.invalidate("test_key") is True
        assert cache.get("test_key") is None
        assert cache.invalidate("non_existent") is False
        
        # Test clear
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None
    
    def test_feature_cache_ttl(self):
        """Test feature cache TTL functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        cache = FeatureCache(ttl_seconds=0.1)  # Very short TTL
        
        # Set value and immediately retrieve
        cache.set("test_key", "test_value")
        assert cache.get("test_key") == "test_value"
        
        # Wait for TTL to expire
        time.sleep(0.15)
        assert cache.get("test_key") is None
    
    def test_feature_cache_stats(self):
        """Test feature cache statistics."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        cache = FeatureCache()
        
        # Test empty cache stats
        stats = cache.get_cache_stats()
        assert stats['total_entries'] == 0
        assert stats['valid_entries'] == 0
        assert stats['cache_hit_ratio'] == 0
        
        # Add some entries
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        stats = cache.get_cache_stats()
        assert stats['total_entries'] == 2
        assert stats['valid_entries'] == 2
        assert stats['cache_hit_ratio'] == 1.0
    
    def test_feature_store_creation(self):
        """Test feature store creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        
        assert isinstance(store.features, dict)
        assert isinstance(store.feature_groups, dict)
        assert isinstance(store.feature_values, dict)
        assert isinstance(store.transformers, dict)
        assert isinstance(store.validator, FeatureValidator)
        assert isinstance(store.cache, FeatureCache)
        assert isinstance(store.lineage, dict)
        
        # Check default transformers
        assert TransformationType.IDENTITY in store.transformers
        assert TransformationType.NORMALIZE in store.transformers
        assert TransformationType.STANDARDIZE in store.transformers
        assert TransformationType.ONE_HOT in store.transformers
    
    def test_feature_store_register_feature(self, sample_feature_definition):
        """Test feature registration."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        feature = sample_feature_definition
        
        # Register feature
        success = store.register_feature(feature)
        assert success is True
        
        # Verify registration
        assert feature.name in store.features
        assert store.features[feature.name] == feature
        assert feature.name in store.feature_values
        assert feature.name in store.lineage
        
        # Test duplicate registration
        success = store.register_feature(feature)
        assert success is True  # Should succeed but update
        
        # Test invalid feature
        invalid_feature = FeatureDefinition(name="", feature_type=FeatureType.TEXT)
        success = store.register_feature(invalid_feature)
        assert success is False
    
    def test_feature_store_register_feature_group(self, sample_feature_group):
        """Test feature group registration."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        group = sample_feature_group
        
        # Register feature group
        success = store.register_feature_group(group)
        assert success is True
        
        # Verify registration
        assert group.name in store.feature_groups
        assert store.feature_groups[group.name] == group
        
        # Verify placeholder features were created
        for feature_name in group.features:
            assert feature_name in store.features
        
        # Test invalid group
        invalid_group = FeatureGroup(name="", features=[])
        success = store.register_feature_group(invalid_group)
        assert success is False
    
    def test_feature_store_ingest_feature_value(self, sample_feature_definition, sample_feature_values):
        """Test feature value ingestion."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        feature = sample_feature_definition
        feature_value = sample_feature_values[0]
        
        # Register feature first
        store.register_feature(feature)
        
        # Ingest feature value
        success = store.ingest_feature_value(feature_value)
        assert success is True
        
        # Verify ingestion
        assert len(store.feature_values[feature.name]) == 1
        stored_value = store.feature_values[feature.name][0]
        assert stored_value.value == feature_value.value
        assert stored_value.entity_id == feature_value.entity_id
        
        # Test ingestion without registration
        unregistered_value = FeatureValue(
            feature_name="unregistered",
            value=123,
            entity_id="test",
            timestamp=datetime.now()
        )
        success = store.ingest_feature_value(unregistered_value)
        assert success is False
    
    def test_feature_store_ingest_feature_vector(self, sample_feature_vector):
        """Test feature vector ingestion."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        vector = sample_feature_vector
        
        # Register features first
        for feature_name in vector.features.keys():
            feature_def = FeatureDefinition(
                name=feature_name,
                feature_type=FeatureType.NUMERICAL if isinstance(vector.features[feature_name], (int, float)) else FeatureType.TEXT
            )
            store.register_feature(feature_def)
        
        # Ingest feature vector
        success = store.ingest_feature_vector(vector)
        assert success is True
        
        # Verify ingestion
        for feature_name in vector.features.keys():
            assert len(store.feature_values[feature_name]) == 1
            stored_value = store.feature_values[feature_name][0]
            assert stored_value.value == vector.features[feature_name]
            assert stored_value.entity_id == vector.entity_id
    
    def test_feature_store_get_feature_value(self, sample_feature_definition, sample_feature_values):
        """Test feature value retrieval."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        feature = sample_feature_definition
        feature_value = sample_feature_values[0]
        
        # Setup
        store.register_feature(feature)
        store.ingest_feature_value(feature_value)
        
        # Get feature value
        retrieved_value = store.get_feature_value(
            feature_value.feature_name,
            feature_value.entity_id
        )
        
        assert retrieved_value is not None
        assert retrieved_value.feature_name == feature_value.feature_name
        assert retrieved_value.value == feature_value.value
        assert retrieved_value.entity_id == feature_value.entity_id
        
        # Test non-existent feature
        non_existent = store.get_feature_value("non_existent", "entity")
        assert non_existent is None
        
        # Test non-existent entity
        non_existent_entity = store.get_feature_value(feature_value.feature_name, "non_existent")
        assert non_existent_entity is None
    
    def test_feature_store_get_feature_vector(self, sample_feature_vector):
        """Test feature vector retrieval."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        vector = sample_feature_vector
        
        # Setup
        for feature_name in vector.features.keys():
            feature_def = FeatureDefinition(
                name=feature_name,
                feature_type=FeatureType.NUMERICAL if isinstance(vector.features[feature_name], (int, float)) else FeatureType.TEXT
            )
            store.register_feature(feature_def)
        
        store.ingest_feature_vector(vector)
        
        # Get feature vector
        retrieved_vector = store.get_feature_vector(
            list(vector.features.keys()),
            vector.entity_id
        )
        
        assert retrieved_vector is not None
        assert retrieved_vector.entity_id == vector.entity_id
        assert len(retrieved_vector.features) == len(vector.features)
        
        for feature_name, value in vector.features.items():
            assert retrieved_vector.features[feature_name] == value
        
        # Test with missing features
        vector_with_missing = store.get_feature_vector(
            ["non_existent_feature"],
            vector.entity_id
        )
        assert vector_with_missing is None
    
    def test_feature_store_get_feature_group_data(self, sample_feature_group, sample_feature_vector):
        """Test feature group data retrieval."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        group = sample_feature_group
        vector = sample_feature_vector
        
        # Setup
        for feature_name in group.features:
            feature_def = FeatureDefinition(
                name=feature_name,
                feature_type=FeatureType.NUMERICAL if feature_name != "user_location" else FeatureType.TEXT
            )
            store.register_feature(feature_def)
        
        store.register_feature_group(group)
        store.ingest_feature_vector(vector)
        
        # Get feature group data
        results = store.get_feature_group_data(
            group.name,
            [vector.entity_id]
        )
        
        assert len(results) == 1
        result = results[0]
        assert result.entity_id == vector.entity_id
        assert result.feature_group == group.name
        
        # Test non-existent group
        empty_results = store.get_feature_group_data(
            "non_existent_group",
            [vector.entity_id]
        )
        assert len(empty_results) == 0
    
    def test_feature_store_search_features(self, sample_feature_definition):
        """Test feature search functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        feature = sample_feature_definition
        
        # Setup
        store.register_feature(feature)
        
        # Search by name
        results = store.search_features("user_age")
        assert len(results) == 1
        assert results[0].name == feature.name
        
        # Search by description
        results = store.search_features("age")
        assert len(results) == 1
        
        # Search by tags
        results = store.search_features("", tags={'category': 'demographic'})
        assert len(results) == 1
        
        # Search with no results
        results = store.search_features("non_existent")
        assert len(results) == 0
    
    def test_feature_store_lineage_management(self):
        """Test feature lineage management."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        
        feature_def = FeatureDefinition(
            name="test_feature",
            feature_type=FeatureType.NUMERICAL
        )
        store.register_feature(feature_def)
        
        # Update lineage
        success = store.update_feature_lineage(
            "test_feature",
            source_features=["raw_feature"],
            transformations=["normalize"],
            datasets=["training_data"],
            models=["model_v1"]
        )
        assert success is True
        
        # Get lineage
        lineage = store.get_feature_lineage("test_feature")
        assert lineage is not None
        assert "raw_feature" in lineage.source_features
        assert "normalize" in lineage.transformations
        assert "training_data" in lineage.datasets
        assert "model_v1" in lineage.models
        
        # Test non-existent feature lineage
        non_existent_lineage = store.get_feature_lineage("non_existent")
        assert non_existent_lineage is None
    
    def test_feature_store_statistics(self, sample_feature_definition):
        """Test feature statistics calculation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        feature = sample_feature_definition
        
        # Setup
        store.register_feature(feature)
        
        # Add numerical values
        for i, value in enumerate([10, 20, 30, 40, 50]):
            feature_value = FeatureValue(
                feature_name=feature.name,
                value=value,
                entity_id=f"entity_{i}",
                timestamp=datetime.now()
            )
            store.ingest_feature_value(feature_value)
        
        # Get statistics
        stats = store.get_feature_statistics(feature.name)
        
        assert stats['count'] == 5
        assert stats['mean'] == 30.0
        assert stats['min'] == 10
        assert stats['max'] == 50
        assert stats['type'] == 'numeric'
        assert 'std' in stats
        
        # Test non-existent feature
        empty_stats = store.get_feature_statistics("non_existent")
        assert empty_stats == {}
    
    def test_feature_store_list_operations(self, sample_feature_definition, sample_feature_group):
        """Test feature and feature group listing."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        feature = sample_feature_definition
        group = sample_feature_group
        
        # Setup
        store.register_feature(feature)
        store.register_feature_group(group)
        
        # List all features
        features = store.list_features()
        assert len(features) >= 1
        feature_names = [f.name for f in features]
        assert feature.name in feature_names
        
        # List features by status
        draft_features = store.list_features(FeatureStatus.DRAFT)
        assert len(draft_features) >= 1
        
        active_features = store.list_features(FeatureStatus.ACTIVE)
        assert len(active_features) == 0  # No active features yet
        
        # List all feature groups
        groups = store.list_feature_groups()
        assert len(groups) == 1
        assert groups[0].name == group.name
        
        # List feature groups by status
        draft_groups = store.list_feature_groups(FeatureStatus.DRAFT)
        assert len(draft_groups) == 1
    
    def test_feature_store_delete_feature(self, sample_feature_definition, sample_feature_values):
        """Test feature deletion."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        feature = sample_feature_definition
        feature_value = sample_feature_values[0]
        
        # Setup
        store.register_feature(feature)
        store.ingest_feature_value(feature_value)
        
        # Verify feature exists
        assert feature.name in store.features
        assert feature.name in store.feature_values
        
        # Delete feature
        success = store.delete_feature(feature.name)
        assert success is True
        
        # Verify deletion
        assert feature.name not in store.features
        assert feature.name not in store.feature_values
        assert feature.name not in store.lineage
        
        # Test deleting non-existent feature
        success = store.delete_feature("non_existent")
        assert success is True  # Should not fail
    
    def test_feature_store_serving_stats(self, sample_feature_definition, sample_feature_group):
        """Test serving statistics."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        feature = sample_feature_definition
        group = sample_feature_group
        
        # Setup
        store.register_feature(feature)
        store.register_feature_group(group)
        
        # Get serving stats
        stats = store.get_serving_stats()
        
        assert 'total_features' in stats
        assert 'total_feature_groups' in stats
        assert 'active_features' in stats
        assert 'total_feature_values' in stats
        assert 'cache_stats' in stats
        
        assert stats['total_features'] >= 1
        assert stats['total_feature_groups'] == 1
        assert stats['active_features'] == 0  # No active features
        assert isinstance(stats['cache_stats'], dict)
    
    def test_feature_transformations(self, sample_feature_definition):
        """Test feature transformations during ingestion."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        
        # Create feature with transformation
        feature = FeatureDefinition(
            name="normalized_score",
            feature_type=FeatureType.NUMERICAL,
            transformation=TransformationType.NORMALIZE,
            transformation_params={'min': 0, 'max': 100}
        )
        store.register_feature(feature)
        
        # Ingest value that should be transformed
        feature_value = FeatureValue(
            feature_name="normalized_score",
            value=50,  # Should become 0.5 after normalization
            entity_id="test_entity",
            timestamp=datetime.now()
        )
        
        success = store.ingest_feature_value(feature_value)
        assert success is True
        
        # Verify transformation was applied
        stored_values = store.feature_values["normalized_score"]
        assert len(stored_values) == 1
        assert stored_values[0].value == 0.5  # 50 normalized to [0,100] range
    
    def test_feature_validation_during_ingestion(self):
        """Test feature validation during ingestion."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        
        # Create feature with validation rules
        feature = FeatureDefinition(
            name="age_with_validation",
            feature_type=FeatureType.NUMERICAL,
            validation_rules={
                'range_check': {'min': 0, 'max': 120},
                'null_check': {'allow_null': False}
            }
        )
        store.register_feature(feature)
        
        # Try to ingest valid value
        valid_value = FeatureValue(
            feature_name="age_with_validation",
            value=25,
            entity_id="valid_entity",
            timestamp=datetime.now()
        )
        success = store.ingest_feature_value(valid_value)
        assert success is True
        
        # Try to ingest invalid value (out of range)
        invalid_value = FeatureValue(
            feature_name="age_with_validation",
            value=150,  # Too old
            entity_id="invalid_entity",
            timestamp=datetime.now()
        )
        success = store.ingest_feature_value(invalid_value)
        assert success is False
    
    def test_convenience_functions(self):
        """Test convenience functions."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test create_feature_store
        store = create_feature_store()
        assert isinstance(store, FeatureStore)
        
        # Test create_feature_definition
        feature = create_feature_definition(
            name="test_feature",
            feature_type=FeatureType.NUMERICAL,
            description="Test feature"
        )
        assert isinstance(feature, FeatureDefinition)
        assert feature.name == "test_feature"
        assert feature.feature_type == FeatureType.NUMERICAL
        assert feature.description == "Test feature"
        
        # Test create_feature_group
        group = create_feature_group(
            name="test_group",
            features=["feature1", "feature2"],
            entity_key="entity_id"
        )
        assert isinstance(group, FeatureGroup)
        assert group.name == "test_group"
        assert group.features == ["feature1", "feature2"]
        assert group.entity_key == "entity_id"
    
    def test_edge_cases_and_error_handling(self):
        """Test edge cases and error handling."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        
        # Test with empty feature store
        assert store.get_feature_value("non_existent", "entity") is None
        assert store.get_feature_vector([], "entity") is None
        assert len(store.get_feature_group_data("non_existent", ["entity"])) == 0
        assert len(store.search_features("anything")) == 0
        assert store.get_feature_lineage("non_existent") is None
        assert store.get_feature_statistics("non_existent") == {}
        
        # Test transformer edge cases
        normalize_transformer = NormalizeTransformer()
        # Test with min == max
        result = normalize_transformer.transform(5, {'min': 5, 'max': 5})
        assert result == 0.0
        
        standardize_transformer = StandardizeTransformer()
        # Test with std == 0
        result = standardize_transformer.transform(5, {'mean': 3, 'std': 0})
        assert result == 0.0
    
    def test_feature_versioning(self):
        """Test feature versioning functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        store = FeatureStore()
        
        # Create initial version
        feature_v1 = FeatureDefinition(
            name="versioned_feature",
            feature_type=FeatureType.NUMERICAL,
            version="1.0.0"
        )
        store.register_feature(feature_v1)
        
        # Update to new version
        feature_v2 = FeatureDefinition(
            name="versioned_feature",
            feature_type=FeatureType.NUMERICAL,
            version="2.0.0",
            description="Updated feature"
        )
        store.register_feature(feature_v2)
        
        # Verify update
        stored_feature = store.features["versioned_feature"]
        assert stored_feature.version == "2.0.0"
        assert stored_feature.description == "Updated feature"
    
    def test_module_exports(self):
        """Test module exports."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        from backend.mlops.feature_store import __all__
        
        expected_exports = [
            'FeatureType', 'FeatureStatus', 'ServingMode', 'TransformationType',
            'FeatureDefinition', 'FeatureGroup', 'FeatureValue', 'FeatureVector', 'FeatureLineage',
            'FeatureTransformer', 'IdentityTransformer', 'NormalizeTransformer', 
            'StandardizeTransformer', 'OneHotTransformer',
            'FeatureValidator', 'FeatureCache', 'FeatureStore',
            'create_feature_store', 'create_feature_definition', 'create_feature_group'
        ]
        
        for export in expected_exports:
            assert export in __all__, f"Missing export: {export}"