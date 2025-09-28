"""
Module 65: MLOps Feature Store Service

This module provides comprehensive feature store functionality for managing
ML features, versioning, serving, lineage tracking, and real-time feature computation.
Supports both batch and streaming feature serving with advanced caching and transformation.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FeatureType(Enum):
    """Feature data types."""
    CATEGORICAL = "categorical"
    NUMERICAL = "numerical"
    BOOLEAN = "boolean"
    TEXT = "text"
    EMBEDDING = "embedding"
    TIMESTAMP = "timestamp"
    JSON = "json"


class FeatureStatus(Enum):
    """Feature lifecycle status."""
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    ERROR = "error"


class ServingMode(Enum):
    """Feature serving modes."""
    BATCH = "batch"
    STREAMING = "streaming"
    REALTIME = "realtime"
    HYBRID = "hybrid"


class TransformationType(Enum):
    """Feature transformation types."""
    IDENTITY = "identity"
    NORMALIZE = "normalize"
    STANDARDIZE = "standardize"
    ONE_HOT = "one_hot"
    EMBEDDING = "embedding"
    AGGREGATION = "aggregation"
    CUSTOM = "custom"


@dataclass
class FeatureDefinition:
    """Feature definition schema."""
    name: str
    feature_type: FeatureType
    description: str = ""
    entity: str = ""
    source: str = ""
    transformation: TransformationType | None = None
    transformation_params: dict[str, Any] = field(default_factory=dict)
    validation_rules: dict[str, Any] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)
    owner: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    version: str = "1.0.0"
    status: FeatureStatus = FeatureStatus.DRAFT


@dataclass
class FeatureGroup:
    """Feature group definition."""
    name: str
    description: str = ""
    features: list[str] = field(default_factory=list)
    entity_key: str = ""
    source_table: str = ""
    event_timestamp_column: str = ""
    created_timestamp_column: str = ""
    ttl: int | None = None  # Time to live in seconds
    serving_mode: ServingMode = ServingMode.BATCH
    tags: dict[str, str] = field(default_factory=dict)
    owner: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    version: str = "1.0.0"
    status: FeatureStatus = FeatureStatus.DRAFT


@dataclass
class FeatureValue:
    """Individual feature value."""
    feature_name: str
    value: Any
    timestamp: datetime
    entity_id: str
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeatureVector:
    """Feature vector containing multiple features."""
    entity_id: str
    features: dict[str, Any]
    timestamp: datetime
    feature_group: str = ""
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeatureLineage:
    """Feature lineage tracking."""
    feature_name: str
    source_features: list[str] = field(default_factory=list)
    transformations: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = ""


class FeatureTransformer(ABC):
    """Abstract base class for feature transformations."""
    
    @abstractmethod
    def transform(self, value: Any, params: dict[str, Any] = None) -> Any:
        """Transform a feature value."""
        pass
    
    @abstractmethod
    def inverse_transform(self, value: Any, params: dict[str, Any] = None) -> Any:
        """Inverse transform a feature value."""
        pass


class IdentityTransformer(FeatureTransformer):
    """Identity transformation (no change)."""
    
    def transform(self, value: Any, params: dict[str, Any] = None) -> Any:
        """Return value unchanged."""
        return value
    
    def inverse_transform(self, value: Any, params: dict[str, Any] = None) -> Any:
        """Return value unchanged."""
        return value


class NormalizeTransformer(FeatureTransformer):
    """Min-max normalization transformer."""
    
    def transform(self, value: Any, params: dict[str, Any] = None) -> Any:
        """Normalize value to [0, 1] range."""
        if params is None:
            params = {}
        
        if not isinstance(value, (int, float)):
            return value
        
        min_val = params.get('min', 0.0)
        max_val = params.get('max', 1.0)
        
        if max_val == min_val:
            return 0.0
        
        return (value - min_val) / (max_val - min_val)
    
    def inverse_transform(self, value: Any, params: dict[str, Any] = None) -> Any:
        """Denormalize value from [0, 1] range."""
        if params is None:
            params = {}
        
        if not isinstance(value, (int, float)):
            return value
        
        min_val = params.get('min', 0.0)
        max_val = params.get('max', 1.0)
        
        return value * (max_val - min_val) + min_val


class StandardizeTransformer(FeatureTransformer):
    """Z-score standardization transformer."""
    
    def transform(self, value: Any, params: dict[str, Any] = None) -> Any:
        """Standardize value using z-score."""
        if params is None:
            params = {}
        
        if not isinstance(value, (int, float)):
            return value
        
        mean = params.get('mean', 0.0)
        std = params.get('std', 1.0)
        
        if std == 0:
            return 0.0
        
        return (value - mean) / std
    
    def inverse_transform(self, value: Any, params: dict[str, Any] = None) -> Any:
        """Inverse standardize value."""
        if params is None:
            params = {}
        
        if not isinstance(value, (int, float)):
            return value
        
        mean = params.get('mean', 0.0)
        std = params.get('std', 1.0)
        
        return value * std + mean


class OneHotTransformer(FeatureTransformer):
    """One-hot encoding transformer."""
    
    def transform(self, value: Any, params: dict[str, Any] = None) -> Any:
        """One-hot encode categorical value."""
        if params is None:
            params = {}
        
        categories = params.get('categories', [])
        if not categories:
            return {str(value): 1}
        
        result = {cat: 0 for cat in categories}
        if str(value) in result:
            result[str(value)] = 1
        
        return result
    
    def inverse_transform(self, value: Any, params: dict[str, Any] = None) -> Any:
        """Inverse one-hot encoding."""
        if not isinstance(value, dict):
            return value
        
        for key, val in value.items():
            if val == 1:
                return key
        
        return None


class FeatureValidator:
    """Feature validation service."""
    
    def __init__(self):
        self.validation_rules = {
            'type_check': self._validate_type,
            'range_check': self._validate_range,
            'enum_check': self._validate_enum,
            'null_check': self._validate_null,
            'pattern_check': self._validate_pattern
        }
    
    def validate_feature(self, feature_def: FeatureDefinition, 
                        value: Any) -> tuple[bool, list[str]]:
        """Validate a feature value against its definition."""
        errors = []
        
        # Type validation
        if not self._validate_type(value, feature_def.feature_type):
            errors.append(f"Type mismatch for {feature_def.name}: expected {feature_def.feature_type}")
        
        # Custom validation rules
        for rule_name, rule_params in feature_def.validation_rules.items():
            if rule_name in self.validation_rules:
                validator = self.validation_rules[rule_name]
                if not validator(value, rule_params):
                    errors.append(f"Validation failed for {feature_def.name}: {rule_name}")
        
        return len(errors) == 0, errors
    
    def _validate_type(self, value: Any, expected_type: Any) -> bool:
        """Validate value type."""
        if isinstance(expected_type, FeatureType):
            if expected_type == FeatureType.NUMERICAL:
                return isinstance(value, (int, float))
            elif expected_type == FeatureType.CATEGORICAL:
                return isinstance(value, str)
            elif expected_type == FeatureType.BOOLEAN:
                return isinstance(value, bool)
            elif expected_type == FeatureType.TEXT:
                return isinstance(value, str)
            elif expected_type == FeatureType.TIMESTAMP:
                return isinstance(value, (datetime, str))
            elif expected_type == FeatureType.JSON:
                return isinstance(value, (dict, list))
            elif expected_type == FeatureType.EMBEDDING:
                return isinstance(value, list)
        
        return True
    
    def _validate_range(self, value: Any, params: dict[str, Any]) -> bool:
        """Validate value is within specified range."""
        if not isinstance(value, (int, float)):
            return True
        
        min_val = params.get('min')
        max_val = params.get('max')
        
        if min_val is not None and value < min_val:
            return False
        if max_val is not None and value > max_val:
            return False
        
        return True
    
    def _validate_enum(self, value: Any, params: dict[str, Any]) -> bool:
        """Validate value is in allowed enum values."""
        allowed_values = params.get('values', [])
        return value in allowed_values
    
    def _validate_null(self, value: Any, params: dict[str, Any]) -> bool:
        """Validate null constraints."""
        allow_null = params.get('allow_null', True)
        if not allow_null and value is None:
            return False
        return True
    
    def _validate_pattern(self, value: Any, params: dict[str, Any]) -> bool:
        """Validate value matches pattern."""
        if not isinstance(value, str):
            return True
        
        import re
        pattern = params.get('pattern')
        if pattern:
            return bool(re.match(pattern, value))
        
        return True


class FeatureCache:
    """Feature caching service."""
    
    def __init__(self, ttl_seconds: int = 3600):
        self.cache: dict[str, tuple[Any, datetime]] = {}
        self.ttl_seconds = ttl_seconds
    
    def get(self, key: str) -> Any | None:
        """Get cached feature value."""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl_seconds):
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, value: Any) -> None:
        """Cache feature value."""
        self.cache[key] = (value, datetime.now())
    
    def invalidate(self, key: str) -> bool:
        """Invalidate cached value."""
        if key in self.cache:
            del self.cache[key]
            return True
        return False
    
    def clear(self) -> None:
        """Clear entire cache."""
        self.cache.clear()
    
    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        now = datetime.now()
        valid_entries = 0
        expired_entries = 0
        
        for key, (value, timestamp) in self.cache.items():
            if now - timestamp < timedelta(seconds=self.ttl_seconds):
                valid_entries += 1
            else:
                expired_entries += 1
        
        return {
            'total_entries': len(self.cache),
            'valid_entries': valid_entries,
            'expired_entries': expired_entries,
            'cache_hit_ratio': valid_entries / len(self.cache) if self.cache else 0
        }


class FeatureStore:
    """Main feature store service."""
    
    def __init__(self):
        self.features: dict[str, FeatureDefinition] = {}
        self.feature_groups: dict[str, FeatureGroup] = {}
        self.feature_values: dict[str, list[FeatureValue]] = {}
        self.transformers: dict[TransformationType, FeatureTransformer] = {
            TransformationType.IDENTITY: IdentityTransformer(),
            TransformationType.NORMALIZE: NormalizeTransformer(),
            TransformationType.STANDARDIZE: StandardizeTransformer(),
            TransformationType.ONE_HOT: OneHotTransformer()
        }
        self.validator = FeatureValidator()
        self.cache = FeatureCache()
        self.lineage: dict[str, FeatureLineage] = {}
    
    def register_feature(self, feature_def: FeatureDefinition) -> bool:
        """Register a new feature definition."""
        try:
            # Validate feature definition
            if not feature_def.name:
                raise ValueError("Feature name is required")
            
            # Check for duplicates
            if feature_def.name in self.features:
                logger.warning(f"Feature {feature_def.name} already exists, updating...")
            
            # Set timestamps
            if feature_def.name in self.features:
                feature_def.updated_at = datetime.now()
            else:
                feature_def.created_at = datetime.now()
                feature_def.updated_at = datetime.now()
            
            self.features[feature_def.name] = feature_def
            self.feature_values[feature_def.name] = []
            
            # Create lineage entry
            if feature_def.name not in self.lineage:
                self.lineage[feature_def.name] = FeatureLineage(
                    feature_name=feature_def.name,
                    created_by=feature_def.owner
                )
            
            logger.info(f"Feature {feature_def.name} registered successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register feature {feature_def.name}: {e}")
            return False
    
    def register_feature_group(self, group: FeatureGroup) -> bool:
        """Register a new feature group."""
        try:
            if not group.name:
                raise ValueError("Feature group name is required")
            
            # Validate features exist
            for feature_name in group.features:
                if feature_name not in self.features:
                    logger.warning(f"Feature {feature_name} not found, creating placeholder")
                    placeholder = FeatureDefinition(
                        name=feature_name,
                        feature_type=FeatureType.TEXT,
                        description=f"Placeholder for {feature_name}",
                        status=FeatureStatus.DRAFT
                    )
                    self.register_feature(placeholder)
            
            if group.name in self.feature_groups:
                group.updated_at = datetime.now()
            else:
                group.created_at = datetime.now()
                group.updated_at = datetime.now()
            
            self.feature_groups[group.name] = group
            logger.info(f"Feature group {group.name} registered successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register feature group {group.name}: {e}")
            return False
    
    def ingest_feature_value(self, feature_value: FeatureValue) -> bool:
        """Ingest a single feature value."""
        try:
            if feature_value.feature_name not in self.features:
                logger.error(f"Feature {feature_value.feature_name} not registered")
                return False
            
            feature_def = self.features[feature_value.feature_name]
            
            # Validate feature value
            is_valid, errors = self.validator.validate_feature(feature_def, feature_value.value)
            if not is_valid:
                logger.error(f"Feature validation failed: {errors}")
                return False
            
            # Apply transformation if configured
            if feature_def.transformation:
                transformer = self.transformers.get(feature_def.transformation)
                if transformer:
                    feature_value.value = transformer.transform(
                        feature_value.value, 
                        feature_def.transformation_params
                    )
            
            # Store feature value
            self.feature_values[feature_value.feature_name].append(feature_value)
            
            # Update cache
            cache_key = f"{feature_value.feature_name}:{feature_value.entity_id}"
            self.cache.set(cache_key, feature_value.value)
            
            logger.debug(f"Feature value ingested: {feature_value.feature_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to ingest feature value: {e}")
            return False
    
    def ingest_feature_vector(self, feature_vector: FeatureVector) -> bool:
        """Ingest a feature vector (multiple features for one entity)."""
        try:
            success_count = 0
            total_count = len(feature_vector.features)
            
            for feature_name, value in feature_vector.features.items():
                feature_value = FeatureValue(
                    feature_name=feature_name,
                    value=value,
                    entity_id=feature_vector.entity_id,
                    timestamp=feature_vector.timestamp,
                    version=feature_vector.version,
                    metadata=feature_vector.metadata
                )
                
                if self.ingest_feature_value(feature_value):
                    success_count += 1
            
            logger.info(f"Ingested {success_count}/{total_count} features for entity {feature_vector.entity_id}")
            return success_count == total_count
            
        except Exception as e:
            logger.error(f"Failed to ingest feature vector: {e}")
            return False
    
    def get_feature_value(self, feature_name: str, entity_id: str, 
                         timestamp: datetime | None = None) -> FeatureValue | None:
        """Get latest feature value for entity."""
        try:
            # Check cache first
            cache_key = f"{feature_name}:{entity_id}"
            cached_value = self.cache.get(cache_key)
            if cached_value is not None:
                return FeatureValue(
                    feature_name=feature_name,
                    value=cached_value,
                    entity_id=entity_id,
                    timestamp=datetime.now()
                )
            
            # Get from storage
            if feature_name not in self.feature_values:
                return None
            
            values = self.feature_values[feature_name]
            
            # Filter by entity and optionally by timestamp
            entity_values = [v for v in values if v.entity_id == entity_id]
            
            if timestamp:
                entity_values = [v for v in entity_values if v.timestamp <= timestamp]
            
            if not entity_values:
                return None
            
            # Return most recent value
            latest_value = max(entity_values, key=lambda x: x.timestamp)
            
            # Cache the result
            self.cache.set(cache_key, latest_value.value)
            
            return latest_value
            
        except Exception as e:
            logger.error(f"Failed to get feature value: {e}")
            return None
    
    def get_feature_vector(self, feature_names: list[str], entity_id: str,
                          timestamp: datetime | None = None) -> FeatureVector | None:
        """Get feature vector for entity."""
        try:
            features = {}
            
            for feature_name in feature_names:
                feature_value = self.get_feature_value(feature_name, entity_id, timestamp)
                if feature_value:
                    features[feature_name] = feature_value.value
                else:
                    logger.warning(f"Feature {feature_name} not found for entity {entity_id}")
            
            if not features:
                return None
            
            return FeatureVector(
                entity_id=entity_id,
                features=features,
                timestamp=timestamp or datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Failed to get feature vector: {e}")
            return None
    
    def get_feature_group_data(self, group_name: str, entity_ids: list[str],
                              timestamp: datetime | None = None) -> list[FeatureVector]:
        """Get feature group data for multiple entities."""
        try:
            if group_name not in self.feature_groups:
                logger.error(f"Feature group {group_name} not found")
                return []
            
            group = self.feature_groups[group_name]
            results = []
            
            for entity_id in entity_ids:
                feature_vector = self.get_feature_vector(group.features, entity_id, timestamp)
                if feature_vector:
                    feature_vector.feature_group = group_name
                    results.append(feature_vector)
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get feature group data: {e}")
            return []
    
    def search_features(self, query: str, tags: dict[str, str] | None = None) -> list[FeatureDefinition]:
        """Search features by name, description, or tags."""
        results = []
        query_lower = query.lower()
        
        for feature in self.features.values():
            # Search in name and description
            if (query_lower in feature.name.lower() or 
                query_lower in feature.description.lower()):
                results.append(feature)
                continue
            
            # Search in tags
            if tags:
                match_tags = True
                for key, value in tags.items():
                    if key not in feature.tags or feature.tags[key] != value:
                        match_tags = False
                        break
                if match_tags:
                    results.append(feature)
        
        return results
    
    def get_feature_lineage(self, feature_name: str) -> FeatureLineage | None:
        """Get feature lineage information."""
        return self.lineage.get(feature_name)
    
    def update_feature_lineage(self, feature_name: str, 
                              source_features: list[str] | None = None,
                              transformations: list[str] | None = None,
                              datasets: list[str] | None = None,
                              models: list[str] | None = None) -> bool:
        """Update feature lineage information."""
        try:
            if feature_name not in self.lineage:
                self.lineage[feature_name] = FeatureLineage(feature_name=feature_name)
            
            lineage = self.lineage[feature_name]
            
            if source_features:
                lineage.source_features.extend(source_features)
            if transformations:
                lineage.transformations.extend(transformations)
            if datasets:
                lineage.datasets.extend(datasets)
            if models:
                lineage.models.extend(models)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update feature lineage: {e}")
            return False
    
    def get_feature_statistics(self, feature_name: str) -> dict[str, Any]:
        """Get feature statistics."""
        try:
            if feature_name not in self.feature_values:
                return {}
            
            values = [v.value for v in self.feature_values[feature_name] 
                     if isinstance(v.value, (int, float))]
            
            if not values:
                return {
                    'count': len(self.feature_values[feature_name]),
                    'type': 'non_numeric'
                }
            
            stats = {
                'count': len(values),
                'mean': sum(values) / len(values),
                'min': min(values),
                'max': max(values),
                'type': 'numeric'
            }
            
            # Calculate standard deviation
            mean = stats['mean']
            variance = sum((x - mean) ** 2 for x in values) / len(values)
            stats['std'] = variance ** 0.5
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get feature statistics: {e}")
            return {}
    
    def list_features(self, status: FeatureStatus | None = None) -> list[FeatureDefinition]:
        """List all features, optionally filtered by status."""
        if status:
            return [f for f in self.features.values() if f.status == status]
        return list(self.features.values())
    
    def list_feature_groups(self, status: FeatureStatus | None = None) -> list[FeatureGroup]:
        """List all feature groups, optionally filtered by status."""
        if status:
            return [g for g in self.feature_groups.values() if g.status == status]
        return list(self.feature_groups.values())
    
    def delete_feature(self, feature_name: str) -> bool:
        """Delete a feature and its data."""
        try:
            if feature_name in self.features:
                del self.features[feature_name]
            
            if feature_name in self.feature_values:
                del self.feature_values[feature_name]
            
            if feature_name in self.lineage:
                del self.lineage[feature_name]
            
            # Invalidate cache entries
            keys_to_remove = [k for k in self.cache.cache.keys() if k.startswith(f"{feature_name}:")]
            for key in keys_to_remove:
                self.cache.invalidate(key)
            
            logger.info(f"Feature {feature_name} deleted successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete feature {feature_name}: {e}")
            return False
    
    def get_serving_stats(self) -> dict[str, Any]:
        """Get feature serving statistics."""
        cache_stats = self.cache.get_cache_stats()
        
        return {
            'total_features': len(self.features),
            'total_feature_groups': len(self.feature_groups),
            'active_features': len([f for f in self.features.values() if f.status == FeatureStatus.ACTIVE]),
            'total_feature_values': sum(len(values) for values in self.feature_values.values()),
            'cache_stats': cache_stats
        }


# Convenience functions
def create_feature_store() -> FeatureStore:
    """Create a new feature store instance."""
    return FeatureStore()


def create_feature_definition(name: str, feature_type: FeatureType, 
                            description: str = "", **kwargs) -> FeatureDefinition:
    """Create a feature definition with defaults."""
    return FeatureDefinition(
        name=name,
        feature_type=feature_type,
        description=description,
        **kwargs
    )


def create_feature_group(name: str, features: list[str], entity_key: str,
                        **kwargs) -> FeatureGroup:
    """Create a feature group with defaults."""
    return FeatureGroup(
        name=name,
        features=features,
        entity_key=entity_key,
        **kwargs
    )


# Module exports
__all__ = [
    'FeatureType', 'FeatureStatus', 'ServingMode', 'TransformationType',
    'FeatureDefinition', 'FeatureGroup', 'FeatureValue', 'FeatureVector', 'FeatureLineage',
    'FeatureTransformer', 'IdentityTransformer', 'NormalizeTransformer', 
    'StandardizeTransformer', 'OneHotTransformer',
    'FeatureValidator', 'FeatureCache', 'FeatureStore',
    'create_feature_store', 'create_feature_definition', 'create_feature_group'
]