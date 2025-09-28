"""
Feature Flag Service for Trading Platform

This module provides comprehensive feature flag management including:
- Feature toggles with dynamic enabling/disabling
- A/B testing capabilities with user targeting
- Gradual rollouts with percentage-based deployment
- User targeting based on attributes and conditions
- Configuration management with hot reloading
- Metrics and analytics for feature usage
- Integration with external feature flag providers
"""

import asyncio
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Callable, Union
from uuid import uuid4


class FeatureFlagType(Enum):
    """Feature flag types."""
    BOOLEAN = "boolean"
    STRING = "string"
    NUMBER = "number"
    JSON = "json"


class RolloutStrategy(Enum):
    """Rollout strategy types."""
    ALL_USERS = "all_users"
    PERCENTAGE = "percentage"
    USER_LIST = "user_list"
    USER_ATTRIBUTES = "user_attributes"
    GRADUAL = "gradual"


class TargetingCondition(Enum):
    """Targeting condition operators."""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    REGEX_MATCH = "regex_match"


@dataclass
class UserContext:
    """User context for feature flag evaluation."""
    user_id: str
    email: Optional[str] = None
    groups: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    custom_properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TargetingRule:
    """Rule for targeting specific users or groups."""
    id: str
    name: str
    condition: TargetingCondition
    attribute: str
    value: Any
    enabled: bool = True
    description: Optional[str] = None


@dataclass
class FeatureVariant:
    """Feature flag variant for A/B testing."""
    id: str
    name: str
    value: Any
    weight: float  # 0.0 to 1.0
    enabled: bool = True
    description: Optional[str] = None


@dataclass
class FeatureFlag:
    """Feature flag configuration."""
    key: str
    name: str
    description: str
    flag_type: FeatureFlagType
    enabled: bool = True
    default_value: Any = False
    
    # Rollout configuration
    rollout_strategy: RolloutStrategy = RolloutStrategy.ALL_USERS
    rollout_percentage: float = 100.0  # 0.0 to 100.0
    
    # Targeting
    targeting_rules: List[TargetingRule] = field(default_factory=list)
    allowed_users: Set[str] = field(default_factory=set)
    allowed_groups: Set[str] = field(default_factory=set)
    
    # A/B Testing
    variants: List[FeatureVariant] = field(default_factory=list)
    
    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    tags: Set[str] = field(default_factory=set)
    
    # Gradual rollout
    gradual_rollout_start: Optional[datetime] = None
    gradual_rollout_end: Optional[datetime] = None
    gradual_rollout_start_percentage: float = 0.0
    gradual_rollout_end_percentage: float = 100.0


@dataclass
class FeatureFlagEvaluation:
    """Result of feature flag evaluation."""
    flag_key: str
    user_id: str
    enabled: bool
    value: Any
    variant: Optional[str] = None
    reason: str = "default"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    evaluation_time_ms: float = 0.0


@dataclass
class FeatureFlagMetrics:
    """Metrics for feature flag usage."""
    flag_key: str
    total_evaluations: int = 0
    enabled_count: int = 0
    disabled_count: int = 0
    variant_counts: Dict[str, int] = field(default_factory=dict)
    unique_users: Set[str] = field(default_factory=set)
    last_evaluation: Optional[datetime] = None
    first_evaluation: Optional[datetime] = None


class FeatureFlagProvider(ABC):
    """Abstract base class for feature flag providers."""
    
    @abstractmethod
    async def get_flags(self) -> Dict[str, FeatureFlag]:
        """Get all feature flags."""
        pass
    
    @abstractmethod
    async def get_flag(self, key: str) -> Optional[FeatureFlag]:
        """Get a specific feature flag."""
        pass
    
    @abstractmethod
    async def save_flag(self, flag: FeatureFlag) -> bool:
        """Save a feature flag."""
        pass
    
    @abstractmethod
    async def delete_flag(self, key: str) -> bool:
        """Delete a feature flag."""
        pass


class InMemoryFeatureFlagProvider(FeatureFlagProvider):
    """In-memory feature flag provider."""
    
    def __init__(self):
        self.flags: Dict[str, FeatureFlag] = {}
        self._lock = threading.RLock()
    
    async def get_flags(self) -> Dict[str, FeatureFlag]:
        """Get all feature flags."""
        with self._lock:
            return self.flags.copy()
    
    async def get_flag(self, key: str) -> Optional[FeatureFlag]:
        """Get a specific feature flag."""
        with self._lock:
            return self.flags.get(key)
    
    async def save_flag(self, flag: FeatureFlag) -> bool:
        """Save a feature flag."""
        try:
            with self._lock:
                flag.updated_at = datetime.now(timezone.utc)
                self.flags[flag.key] = flag
            return True
        except Exception:
            return False
    
    async def delete_flag(self, key: str) -> bool:
        """Delete a feature flag."""
        try:
            with self._lock:
                if key in self.flags:
                    del self.flags[key]
                    return True
            return False
        except Exception:
            return False


class FileFeatureFlagProvider(FeatureFlagProvider):
    """File-based feature flag provider."""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self._lock = threading.RLock()
        self._cache: Dict[str, FeatureFlag] = {}
        self._last_modified: Optional[float] = None
    
    async def _load_flags(self) -> Dict[str, FeatureFlag]:
        """Load flags from file."""
        if not self.file_path.exists():
            return {}
        
        try:
            stat = self.file_path.stat()
            if self._last_modified != stat.st_mtime:
                with open(self.file_path, 'r') as f:
                    data = json.load(f)
                
                flags = {}
                for flag_data in data.get('flags', []):
                    flag = self._deserialize_flag(flag_data)
                    if flag:
                        flags[flag.key] = flag
                
                self._cache = flags
                self._last_modified = stat.st_mtime
            
            return self._cache.copy()
        except Exception as e:
            logging.error(f"Error loading flags from file: {e}")
            return {}
    
    def _deserialize_flag(self, data: Dict) -> Optional[FeatureFlag]:
        """Deserialize flag from dictionary."""
        try:
            # Convert datetime strings back to datetime objects
            if 'created_at' in data and isinstance(data['created_at'], str):
                data['created_at'] = datetime.fromisoformat(data['created_at'])
            if 'updated_at' in data and isinstance(data['updated_at'], str):
                data['updated_at'] = datetime.fromisoformat(data['updated_at'])
            
            # Convert sets and enums
            if 'tags' in data:
                data['tags'] = set(data['tags'])
            if 'allowed_users' in data:
                data['allowed_users'] = set(data['allowed_users'])
            if 'allowed_groups' in data:
                data['allowed_groups'] = set(data['allowed_groups'])
            
            if 'flag_type' in data:
                data['flag_type'] = FeatureFlagType(data['flag_type'])
            if 'rollout_strategy' in data:
                data['rollout_strategy'] = RolloutStrategy(data['rollout_strategy'])
            
            # Convert targeting rules
            if 'targeting_rules' in data:
                rules = []
                for rule_data in data['targeting_rules']:
                    if 'condition' in rule_data:
                        rule_data['condition'] = TargetingCondition(rule_data['condition'])
                    rules.append(TargetingRule(**rule_data))
                data['targeting_rules'] = rules
            
            # Convert variants
            if 'variants' in data:
                variants = []
                for variant_data in data['variants']:
                    variants.append(FeatureVariant(**variant_data))
                data['variants'] = variants
            
            return FeatureFlag(**data)
        except Exception as e:
            logging.error(f"Error deserializing flag: {e}")
            return None
    
    async def get_flags(self) -> Dict[str, FeatureFlag]:
        """Get all feature flags."""
        with self._lock:
            return await self._load_flags()
    
    async def get_flag(self, key: str) -> Optional[FeatureFlag]:
        """Get a specific feature flag."""
        flags = await self.get_flags()
        return flags.get(key)
    
    async def save_flag(self, flag: FeatureFlag) -> bool:
        """Save a feature flag."""
        try:
            with self._lock:
                flags = await self._load_flags()
                flag.updated_at = datetime.now(timezone.utc)
                flags[flag.key] = flag
                
                # Serialize flags to file
                data = {'flags': []}
                for f in flags.values():
                    flag_dict = asdict(f)
                    # Convert datetime objects to strings
                    if 'created_at' in flag_dict:
                        flag_dict['created_at'] = f.created_at.isoformat()
                    if 'updated_at' in flag_dict:
                        flag_dict['updated_at'] = f.updated_at.isoformat()
                    # Convert sets to lists
                    if 'tags' in flag_dict:
                        flag_dict['tags'] = list(f.tags)
                    if 'allowed_users' in flag_dict:
                        flag_dict['allowed_users'] = list(f.allowed_users)
                    if 'allowed_groups' in flag_dict:
                        flag_dict['allowed_groups'] = list(f.allowed_groups)
                    # Convert enums to strings
                    if 'flag_type' in flag_dict:
                        flag_dict['flag_type'] = f.flag_type.value
                    if 'rollout_strategy' in flag_dict:
                        flag_dict['rollout_strategy'] = f.rollout_strategy.value
                    
                    data['flags'].append(flag_dict)
                
                # Ensure directory exists
                self.file_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(self.file_path, 'w') as file:
                    json.dump(data, file, indent=2, default=str)
                
                self._last_modified = None  # Force reload
            return True
        except Exception as e:
            logging.error(f"Error saving flag to file: {e}")
            return False
    
    async def delete_flag(self, key: str) -> bool:
        """Delete a feature flag."""
        try:
            with self._lock:
                flags = await self._load_flags()
                if key in flags:
                    del flags[key]
                    
                    # Save updated flags
                    data = {'flags': []}
                    for f in flags.values():
                        flag_dict = asdict(f)
                        data['flags'].append(flag_dict)
                    
                    with open(self.file_path, 'w') as file:
                        json.dump(data, file, indent=2, default=str)
                    
                    self._last_modified = None  # Force reload
                    return True
            return False
        except Exception as e:
            logging.error(f"Error deleting flag from file: {e}")
            return False


class FeatureFlagEvaluator:
    """Evaluates feature flags for users."""
    
    def __init__(self):
        self._hash_cache: Dict[str, int] = {}
    
    def evaluate_flag(self, flag: FeatureFlag, user_context: UserContext) -> FeatureFlagEvaluation:
        """Evaluate a feature flag for a user."""
        start_time = time.time()
        
        try:
            result = self._evaluate_flag_internal(flag, user_context)
            result.evaluation_time_ms = (time.time() - start_time) * 1000
            return result
        except Exception as e:
            logging.error(f"Error evaluating flag {flag.key}: {e}")
            return FeatureFlagEvaluation(
                flag_key=flag.key,
                user_id=user_context.user_id,
                enabled=False,
                value=flag.default_value,
                reason=f"evaluation_error: {str(e)}",
                evaluation_time_ms=(time.time() - start_time) * 1000
            )
    
    def _evaluate_flag_internal(self, flag: FeatureFlag, user_context: UserContext) -> FeatureFlagEvaluation:
        """Internal flag evaluation logic."""
        # Check if flag is enabled globally
        if not flag.enabled:
            return FeatureFlagEvaluation(
                flag_key=flag.key,
                user_id=user_context.user_id,
                enabled=False,
                value=flag.default_value,
                reason="flag_disabled"
            )
        
        # Check user-specific allow list
        if flag.allowed_users and user_context.user_id in flag.allowed_users:
            value, variant = self._get_flag_value(flag, user_context)
            return FeatureFlagEvaluation(
                flag_key=flag.key,
                user_id=user_context.user_id,
                enabled=True,
                value=value,
                variant=variant,
                reason="user_allowed"
            )
        
        # Check group-specific allow list
        user_groups = set(user_context.groups)
        if flag.allowed_groups and user_groups.intersection(flag.allowed_groups):
            value, variant = self._get_flag_value(flag, user_context)
            return FeatureFlagEvaluation(
                flag_key=flag.key,
                user_id=user_context.user_id,
                enabled=True,
                value=value,
                variant=variant,
                reason="group_allowed"
            )
        
        # Check targeting rules
        if flag.targeting_rules:
            for rule in flag.targeting_rules:
                if rule.enabled and self._evaluate_targeting_rule(rule, user_context):
                    value, variant = self._get_flag_value(flag, user_context)
                    return FeatureFlagEvaluation(
                        flag_key=flag.key,
                        user_id=user_context.user_id,
                        enabled=True,
                        value=value,
                        variant=variant,
                        reason=f"rule_match: {rule.name}"
                    )
        
        # Check rollout strategy
        rollout_enabled = self._evaluate_rollout(flag, user_context)
        if rollout_enabled:
            value, variant = self._get_flag_value(flag, user_context)
            return FeatureFlagEvaluation(
                flag_key=flag.key,
                user_id=user_context.user_id,
                enabled=True,
                value=value,
                variant=variant,
                reason="rollout_enabled"
            )
        
        return FeatureFlagEvaluation(
            flag_key=flag.key,
            user_id=user_context.user_id,
            enabled=False,
            value=flag.default_value,
            reason="rollout_disabled"
        )
    
    def _evaluate_targeting_rule(self, rule: TargetingRule, user_context: UserContext) -> bool:
        """Evaluate a targeting rule against user context."""
        try:
            # Get attribute value from user context
            if rule.attribute in user_context.attributes:
                user_value = user_context.attributes[rule.attribute]
            elif rule.attribute in user_context.custom_properties:
                user_value = user_context.custom_properties[rule.attribute]
            elif hasattr(user_context, rule.attribute):
                user_value = getattr(user_context, rule.attribute)
            else:
                return False
            
            # Evaluate condition
            if rule.condition == TargetingCondition.EQUALS:
                return user_value == rule.value
            elif rule.condition == TargetingCondition.NOT_EQUALS:
                return user_value != rule.value
            elif rule.condition == TargetingCondition.IN:
                return user_value in rule.value
            elif rule.condition == TargetingCondition.NOT_IN:
                return user_value not in rule.value
            elif rule.condition == TargetingCondition.CONTAINS:
                return str(rule.value) in str(user_value)
            elif rule.condition == TargetingCondition.STARTS_WITH:
                return str(user_value).startswith(str(rule.value))
            elif rule.condition == TargetingCondition.ENDS_WITH:
                return str(user_value).endswith(str(rule.value))
            elif rule.condition == TargetingCondition.GREATER_THAN:
                return float(user_value) > float(rule.value)
            elif rule.condition == TargetingCondition.LESS_THAN:
                return float(user_value) < float(rule.value)
            elif rule.condition == TargetingCondition.REGEX_MATCH:
                import re
                return bool(re.match(rule.value, str(user_value)))
            
            return False
        except Exception:
            return False
    
    def _evaluate_rollout(self, flag: FeatureFlag, user_context: UserContext) -> bool:
        """Evaluate rollout strategy."""
        if flag.rollout_strategy == RolloutStrategy.ALL_USERS:
            return True
        elif flag.rollout_strategy == RolloutStrategy.PERCENTAGE:
            return self._is_user_in_percentage(flag.key, user_context.user_id, flag.rollout_percentage)
        elif flag.rollout_strategy == RolloutStrategy.GRADUAL:
            return self._evaluate_gradual_rollout(flag, user_context)
        
        return False
    
    def _evaluate_gradual_rollout(self, flag: FeatureFlag, user_context: UserContext) -> bool:
        """Evaluate gradual rollout based on time."""
        if not flag.gradual_rollout_start or not flag.gradual_rollout_end:
            return False
        
        now = datetime.now(timezone.utc)
        if now < flag.gradual_rollout_start:
            return False
        elif now > flag.gradual_rollout_end:
            percentage = flag.gradual_rollout_end_percentage
        else:
            # Calculate current percentage based on time progress
            total_duration = (flag.gradual_rollout_end - flag.gradual_rollout_start).total_seconds()
            elapsed = (now - flag.gradual_rollout_start).total_seconds()
            progress = elapsed / total_duration
            
            percentage_range = flag.gradual_rollout_end_percentage - flag.gradual_rollout_start_percentage
            percentage = flag.gradual_rollout_start_percentage + (progress * percentage_range)
        
        return self._is_user_in_percentage(flag.key, user_context.user_id, percentage)
    
    def _is_user_in_percentage(self, flag_key: str, user_id: str, percentage: float) -> bool:
        """Check if user falls within percentage rollout."""
        if percentage >= 100.0:
            return True
        if percentage <= 0.0:
            return False
        
        # Use consistent hashing to ensure same user always gets same result
        hash_key = f"{flag_key}:{user_id}"
        if hash_key not in self._hash_cache:
            self._hash_cache[hash_key] = hash(hash_key) % 10000
        
        user_hash = self._hash_cache[hash_key]
        threshold = int(percentage * 100)  # Convert to 0-10000 range
        return user_hash < threshold
    
    def _get_flag_value(self, flag: FeatureFlag, user_context: UserContext) -> tuple[Any, Optional[str]]:
        """Get flag value and variant."""
        if not flag.variants:
            return flag.default_value, None
        
        # Select variant based on user hash
        hash_key = f"{flag.key}:variant:{user_context.user_id}"
        if hash_key not in self._hash_cache:
            self._hash_cache[hash_key] = hash(hash_key) % 10000
        
        user_hash = self._hash_cache[hash_key] / 10000.0  # Normalize to 0-1
        
        # Find variant based on cumulative weights
        cumulative_weight = 0.0
        enabled_variants = [v for v in flag.variants if v.enabled]
        
        if not enabled_variants:
            return flag.default_value, None
        
        # Normalize weights
        total_weight = sum(v.weight for v in enabled_variants)
        if total_weight == 0:
            return enabled_variants[0].value, enabled_variants[0].id
        
        for variant in enabled_variants:
            cumulative_weight += variant.weight / total_weight
            if user_hash <= cumulative_weight:
                return variant.value, variant.id
        
        # Fallback to last variant
        return enabled_variants[-1].value, enabled_variants[-1].id


class FeatureFlagService:
    """Main feature flag service."""
    
    def __init__(self, provider: Optional[FeatureFlagProvider] = None):
        self.provider = provider or InMemoryFeatureFlagProvider()
        self.evaluator = FeatureFlagEvaluator()
        self.metrics: Dict[str, FeatureFlagMetrics] = {}
        self._cache: Dict[str, FeatureFlag] = {}
        self._cache_lock = threading.RLock()
        self._cache_expiry: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=5)  # Cache TTL
        
        # Event handlers
        self.evaluation_handlers: List[Callable[[FeatureFlagEvaluation], None]] = []
        
        # Background refresh
        self._refresh_task: Optional[asyncio.Task] = None
        self._refresh_interval = 60  # seconds
        self._running = False
    
    async def start(self):
        """Start the feature flag service."""
        self._running = True
        await self._refresh_cache()
        self._refresh_task = asyncio.create_task(self._refresh_loop())
    
    async def stop(self):
        """Stop the feature flag service."""
        self._running = False
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
    
    async def _refresh_loop(self):
        """Background cache refresh loop."""
        while self._running:
            try:
                await asyncio.sleep(self._refresh_interval)
                if self._running:
                    await self._refresh_cache()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in refresh loop: {e}")
    
    async def _refresh_cache(self):
        """Refresh the feature flag cache."""
        try:
            flags = await self.provider.get_flags()
            with self._cache_lock:
                self._cache = flags
                self._cache_expiry = datetime.now(timezone.utc) + self._cache_ttl
        except Exception as e:
            logging.error(f"Error refreshing cache: {e}")
    
    async def get_flags(self) -> Dict[str, FeatureFlag]:
        """Get all feature flags."""
        with self._cache_lock:
            if (not self._cache_expiry or 
                datetime.now(timezone.utc) > self._cache_expiry):
                await self._refresh_cache()
            return self._cache.copy()
    
    async def get_flag(self, key: str) -> Optional[FeatureFlag]:
        """Get a specific feature flag."""
        flags = await self.get_flags()
        return flags.get(key)
    
    async def create_flag(self, flag: FeatureFlag) -> bool:
        """Create a new feature flag."""
        result = await self.provider.save_flag(flag)
        if result:
            await self._refresh_cache()
        return result
    
    async def update_flag(self, flag: FeatureFlag) -> bool:
        """Update an existing feature flag."""
        result = await self.provider.save_flag(flag)
        if result:
            await self._refresh_cache()
        return result
    
    async def delete_flag(self, key: str) -> bool:
        """Delete a feature flag."""
        result = await self.provider.delete_flag(key)
        if result:
            await self._refresh_cache()
        return result
    
    async def evaluate_flag(self, key: str, user_context: UserContext, default_value: Any = False) -> FeatureFlagEvaluation:
        """Evaluate a feature flag for a user."""
        flag = await self.get_flag(key)
        if not flag:
            evaluation = FeatureFlagEvaluation(
                flag_key=key,
                user_id=user_context.user_id,
                enabled=False,
                value=default_value,
                reason="flag_not_found"
            )
        else:
            evaluation = self.evaluator.evaluate_flag(flag, user_context)
        
        # Update metrics
        self._update_metrics(evaluation)
        
        # Notify handlers
        for handler in self.evaluation_handlers:
            try:
                handler(evaluation)
            except Exception as e:
                logging.error(f"Error in evaluation handler: {e}")
        
        return evaluation
    
    async def is_enabled(self, key: str, user_context: UserContext, default_value: bool = False) -> bool:
        """Check if a feature flag is enabled for a user."""
        evaluation = await self.evaluate_flag(key, user_context, default_value)
        return evaluation.enabled
    
    async def get_value(self, key: str, user_context: UserContext, default_value: Any = None) -> Any:
        """Get the value of a feature flag for a user."""
        evaluation = await self.evaluate_flag(key, user_context, default_value)
        return evaluation.value
    
    def _update_metrics(self, evaluation: FeatureFlagEvaluation):
        """Update feature flag metrics."""
        if evaluation.flag_key not in self.metrics:
            self.metrics[evaluation.flag_key] = FeatureFlagMetrics(flag_key=evaluation.flag_key)
        
        metrics = self.metrics[evaluation.flag_key]
        metrics.total_evaluations += 1
        
        if evaluation.enabled:
            metrics.enabled_count += 1
        else:
            metrics.disabled_count += 1
        
        if evaluation.variant:
            metrics.variant_counts[evaluation.variant] = metrics.variant_counts.get(evaluation.variant, 0) + 1
        
        metrics.unique_users.add(evaluation.user_id)
        metrics.last_evaluation = evaluation.timestamp
        if not metrics.first_evaluation:
            metrics.first_evaluation = evaluation.timestamp
    
    def get_metrics(self, flag_key: Optional[str] = None) -> Dict[str, Dict]:
        """Get metrics for feature flags."""
        if flag_key:
            metrics = self.metrics.get(flag_key)
            if metrics:
                return {
                    flag_key: {
                        'total_evaluations': metrics.total_evaluations,
                        'enabled_count': metrics.enabled_count,
                        'disabled_count': metrics.disabled_count,
                        'variant_counts': metrics.variant_counts,
                        'unique_users_count': len(metrics.unique_users),
                        'first_evaluation': metrics.first_evaluation,
                        'last_evaluation': metrics.last_evaluation,
                    }
                }
            return {}
        
        result = {}
        for key, metrics in self.metrics.items():
            result[key] = {
                'total_evaluations': metrics.total_evaluations,
                'enabled_count': metrics.enabled_count,
                'disabled_count': metrics.disabled_count,
                'variant_counts': metrics.variant_counts,
                'unique_users_count': len(metrics.unique_users),
                'first_evaluation': metrics.first_evaluation,
                'last_evaluation': metrics.last_evaluation,
            }
        return result
    
    def add_evaluation_handler(self, handler: Callable[[FeatureFlagEvaluation], None]):
        """Add an evaluation event handler."""
        self.evaluation_handlers.append(handler)
    
    def remove_evaluation_handler(self, handler: Callable[[FeatureFlagEvaluation], None]):
        """Remove an evaluation event handler."""
        if handler in self.evaluation_handlers:
            self.evaluation_handlers.remove(handler)


# Global service instance
_feature_flag_service: Optional[FeatureFlagService] = None


def get_feature_flag_service() -> FeatureFlagService:
    """Get the global feature flag service instance."""
    global _feature_flag_service
    if _feature_flag_service is None:
        _feature_flag_service = FeatureFlagService()
    return _feature_flag_service


def set_feature_flag_service(service: FeatureFlagService):
    """Set the global feature flag service instance."""
    global _feature_flag_service
    _feature_flag_service = service


# Convenience functions
async def is_feature_enabled(flag_key: str, user_id: str, **user_attributes) -> bool:
    """Check if a feature is enabled for a user."""
    service = get_feature_flag_service()
    user_context = UserContext(user_id=user_id, attributes=user_attributes)
    return await service.is_enabled(flag_key, user_context)


async def get_feature_value(flag_key: str, user_id: str, default_value: Any = None, **user_attributes) -> Any:
    """Get the value of a feature for a user."""
    service = get_feature_flag_service()
    user_context = UserContext(user_id=user_id, attributes=user_attributes)
    return await service.get_value(flag_key, user_context, default_value)


async def evaluate_feature(flag_key: str, user_id: str, **user_attributes) -> FeatureFlagEvaluation:
    """Evaluate a feature flag for a user."""
    service = get_feature_flag_service()
    user_context = UserContext(user_id=user_id, attributes=user_attributes)
    return await service.evaluate_flag(flag_key, user_context)


def feature_flag(flag_key: str, default_value: Any = False):
    """Decorator for feature flag controlled functions."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            # Try to extract user context from args/kwargs
            user_context = None
            if 'user_context' in kwargs:
                user_context = kwargs.pop('user_context')
            elif 'user_id' in kwargs:
                user_id = kwargs.pop('user_id')
                user_context = UserContext(user_id=user_id)
            
            if user_context:
                service = get_feature_flag_service()
                evaluation = await service.evaluate_flag(flag_key, user_context, default_value)
                if evaluation.enabled:
                    return await func(*args, **kwargs)
                else:
                    return default_value
            else:
                # No user context, use default behavior
                return await func(*args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator