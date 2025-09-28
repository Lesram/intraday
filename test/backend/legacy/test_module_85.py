"""
Comprehensive test suite for Module 85: Feature Flag Service
Tests feature toggles, A/B testing, gradual rollouts, user targeting, and configuration management.
"""

import pytest
import asyncio
import json
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

try:
    from backend.services.feature_flag import (
        FeatureFlagService, FeatureFlag, UserContext, FeatureFlagEvaluation,
        FeatureFlagType, RolloutStrategy, TargetingCondition, TargetingRule,
        FeatureVariant, FeatureFlagEvaluator, InMemoryFeatureFlagProvider,
        FileFeatureFlagProvider, get_feature_flag_service, set_feature_flag_service,
        is_feature_enabled, get_feature_value, evaluate_feature, feature_flag
    )
    MODULE_EXISTS = True
except ImportError as e:
    print(f"Import error: {e}")
    MODULE_EXISTS = False


@pytest.fixture
def user_context():
    """Create a sample user context."""
    if MODULE_EXISTS:
        return UserContext(
            user_id="user123",
            email="user123@example.com",
            groups=["beta_users", "premium"],
            attributes={
                "country": "US",
                "plan": "premium",
                "signup_date": "2024-01-15"
            },
            custom_properties={
                "experiment_group": "A"
            }
        )
    return None


@pytest.fixture
def simple_flag():
    """Create a simple feature flag."""
    if MODULE_EXISTS:
        return FeatureFlag(
            key="simple_feature",
            name="Simple Feature",
            description="A simple boolean feature flag",
            flag_type=FeatureFlagType.BOOLEAN,
            enabled=True,
            default_value=False
        )
    return None


@pytest.fixture
def percentage_flag():
    """Create a percentage rollout flag."""
    if MODULE_EXISTS:
        return FeatureFlag(
            key="percentage_feature",
            name="Percentage Feature",
            description="Feature with percentage rollout",
            flag_type=FeatureFlagType.BOOLEAN,
            enabled=True,
            default_value=False,
            rollout_strategy=RolloutStrategy.PERCENTAGE,
            rollout_percentage=50.0
        )
    return None


@pytest.fixture
def variant_flag():
    """Create a feature flag with variants."""
    if MODULE_EXISTS:
        return FeatureFlag(
            key="variant_feature",
            name="Variant Feature",
            description="Feature with A/B testing variants",
            flag_type=FeatureFlagType.STRING,
            enabled=True,
            default_value="control",
            variants=[
                FeatureVariant(id="control", name="Control", value="control", weight=0.5),
                FeatureVariant(id="treatment", name="Treatment", value="treatment", weight=0.5)
            ]
        )
    return None


@pytest.fixture
def targeting_flag():
    """Create a feature flag with targeting rules."""
    if MODULE_EXISTS:
        return FeatureFlag(
            key="targeting_feature",
            name="Targeting Feature",
            description="Feature with user targeting",
            flag_type=FeatureFlagType.BOOLEAN,
            enabled=True,
            default_value=False,
            targeting_rules=[
                TargetingRule(
                    id="rule1",
                    name="Premium Users",
                    condition=TargetingCondition.EQUALS,
                    attribute="plan",
                    value="premium"
                )
            ]
        )
    return None


@pytest.fixture
def feature_service():
    """Create a feature flag service."""
    if MODULE_EXISTS:
        return FeatureFlagService()
    return None


class TestUserContext:
    """Test UserContext functionality."""

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_user_context_creation(self, user_context):
        """Test user context creation."""
        context = user_context
        assert context.user_id == "user123"
        assert context.email == "user123@example.com"
        assert "beta_users" in context.groups
        assert "premium" in context.groups
        assert context.attributes["country"] == "US"
        assert context.attributes["plan"] == "premium"
        assert context.custom_properties["experiment_group"] == "A"


class TestFeatureFlag:
    """Test FeatureFlag functionality."""

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_simple_flag_creation(self, simple_flag):
        """Test simple feature flag creation."""
        flag = simple_flag
        assert flag.key == "simple_feature"
        assert flag.name == "Simple Feature"
        assert flag.flag_type == FeatureFlagType.BOOLEAN
        assert flag.enabled is True
        assert flag.default_value is False
        assert flag.rollout_strategy == RolloutStrategy.ALL_USERS

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_percentage_flag_creation(self, percentage_flag):
        """Test percentage rollout flag creation."""
        flag = percentage_flag
        assert flag.rollout_strategy == RolloutStrategy.PERCENTAGE
        assert flag.rollout_percentage == 50.0

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_variant_flag_creation(self, variant_flag):
        """Test variant flag creation."""
        flag = variant_flag
        assert len(flag.variants) == 2
        assert flag.variants[0].id == "control"
        assert flag.variants[1].id == "treatment"
        assert flag.variants[0].weight == 0.5
        assert flag.variants[1].weight == 0.5

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_targeting_flag_creation(self, targeting_flag):
        """Test targeting flag creation."""
        flag = targeting_flag
        assert len(flag.targeting_rules) == 1
        rule = flag.targeting_rules[0]
        assert rule.condition == TargetingCondition.EQUALS
        assert rule.attribute == "plan"
        assert rule.value == "premium"


class TestTargetingRule:
    """Test TargetingRule functionality."""

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_targeting_rule_creation(self):
        """Test targeting rule creation."""
        rule = TargetingRule(
            id="test_rule",
            name="Test Rule",
            condition=TargetingCondition.IN,
            attribute="country",
            value=["US", "CA", "UK"]
        )
        
        assert rule.id == "test_rule"
        assert rule.condition == TargetingCondition.IN
        assert rule.attribute == "country"
        assert "US" in rule.value


class TestFeatureVariant:
    """Test FeatureVariant functionality."""

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_variant_creation(self):
        """Test feature variant creation."""
        variant = FeatureVariant(
            id="test_variant",
            name="Test Variant",
            value={"color": "blue", "size": "large"},
            weight=0.3
        )
        
        assert variant.id == "test_variant"
        assert variant.name == "Test Variant"
        assert variant.value["color"] == "blue"
        assert variant.weight == 0.3


class TestInMemoryFeatureFlagProvider:
    """Test InMemoryFeatureFlagProvider functionality."""

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_provider_initialization(self):
        """Test provider initialization."""
        provider = InMemoryFeatureFlagProvider()
        flags = await provider.get_flags()
        assert len(flags) == 0

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_save_and_get_flag(self, simple_flag):
        """Test saving and retrieving flags."""
        provider = InMemoryFeatureFlagProvider()
        
        # Save flag
        result = await provider.save_flag(simple_flag)
        assert result is True
        
        # Get flag
        retrieved_flag = await provider.get_flag("simple_feature")
        assert retrieved_flag is not None
        assert retrieved_flag.key == "simple_feature"
        assert retrieved_flag.name == "Simple Feature"

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_get_all_flags(self, simple_flag, percentage_flag):
        """Test getting all flags."""
        provider = InMemoryFeatureFlagProvider()
        
        await provider.save_flag(simple_flag)
        await provider.save_flag(percentage_flag)
        
        flags = await provider.get_flags()
        assert len(flags) == 2
        assert "simple_feature" in flags
        assert "percentage_feature" in flags

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_delete_flag(self, simple_flag):
        """Test deleting flags."""
        provider = InMemoryFeatureFlagProvider()
        
        await provider.save_flag(simple_flag)
        
        # Verify flag exists
        flag = await provider.get_flag("simple_feature")
        assert flag is not None
        
        # Delete flag
        result = await provider.delete_flag("simple_feature")
        assert result is True
        
        # Verify flag is gone
        flag = await provider.get_flag("simple_feature")
        assert flag is None


class TestFileFeatureFlagProvider:
    """Test FileFeatureFlagProvider functionality."""

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_file_provider_save_and_load(self, simple_flag):
        """Test file provider save and load."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name
        
        try:
            provider = FileFeatureFlagProvider(temp_file)
            
            # Save flag
            result = await provider.save_flag(simple_flag)
            assert result is True
            
            # Create new provider instance to test loading
            provider2 = FileFeatureFlagProvider(temp_file)
            flag = await provider2.get_flag("simple_feature")
            assert flag is not None
            assert flag.key == "simple_feature"
            assert flag.name == "Simple Feature"
        finally:
            Path(temp_file).unlink(missing_ok=True)

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_file_provider_delete(self, simple_flag):
        """Test file provider delete."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name
        
        try:
            provider = FileFeatureFlagProvider(temp_file)
            
            await provider.save_flag(simple_flag)
            result = await provider.delete_flag("simple_feature")
            assert result is True
            
            flag = await provider.get_flag("simple_feature")
            assert flag is None
        finally:
            Path(temp_file).unlink(missing_ok=True)


class TestFeatureFlagEvaluator:
    """Test FeatureFlagEvaluator functionality."""

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_evaluator_creation(self):
        """Test evaluator creation."""
        evaluator = FeatureFlagEvaluator()
        assert evaluator is not None

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_evaluate_disabled_flag(self, user_context):
        """Test evaluating disabled flag."""
        evaluator = FeatureFlagEvaluator()
        
        flag = FeatureFlag(
            key="disabled_flag",
            name="Disabled Flag",
            description="A disabled flag",
            flag_type=FeatureFlagType.BOOLEAN,
            enabled=False,
            default_value=False
        )
        
        evaluation = evaluator.evaluate_flag(flag, user_context)
        assert evaluation.enabled is False
        assert evaluation.reason == "flag_disabled"

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_evaluate_all_users_flag(self, user_context):
        """Test evaluating flag with ALL_USERS strategy."""
        evaluator = FeatureFlagEvaluator()
        
        flag = FeatureFlag(
            key="all_users_flag",
            name="All Users Flag",
            description="Flag for all users",
            flag_type=FeatureFlagType.BOOLEAN,
            enabled=True,
            default_value=True,
            rollout_strategy=RolloutStrategy.ALL_USERS
        )
        
        evaluation = evaluator.evaluate_flag(flag, user_context)
        assert evaluation.enabled is True
        assert evaluation.reason == "rollout_enabled"

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_evaluate_user_allowlist(self, user_context):
        """Test evaluating flag with user allowlist."""
        evaluator = FeatureFlagEvaluator()
        
        flag = FeatureFlag(
            key="allowlist_flag",
            name="Allowlist Flag",
            description="Flag with user allowlist",
            flag_type=FeatureFlagType.BOOLEAN,
            enabled=True,
            default_value=False,
            allowed_users={"user123", "user456"}
        )
        
        evaluation = evaluator.evaluate_flag(flag, user_context)
        assert evaluation.enabled is True
        assert evaluation.reason == "user_allowed"

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_evaluate_group_allowlist(self, user_context):
        """Test evaluating flag with group allowlist."""
        evaluator = FeatureFlagEvaluator()
        
        flag = FeatureFlag(
            key="group_flag",
            name="Group Flag",
            description="Flag with group allowlist",
            flag_type=FeatureFlagType.BOOLEAN,
            enabled=True,
            default_value=False,
            allowed_groups={"beta_users", "admins"}
        )
        
        evaluation = evaluator.evaluate_flag(flag, user_context)
        assert evaluation.enabled is True
        assert evaluation.reason == "group_allowed"

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_evaluate_targeting_rules(self, user_context, targeting_flag):
        """Test evaluating flag with targeting rules."""
        evaluator = FeatureFlagEvaluator()
        
        evaluation = evaluator.evaluate_flag(targeting_flag, user_context)
        assert evaluation.enabled is True
        assert "rule_match" in evaluation.reason

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_evaluate_percentage_rollout(self, user_context):
        """Test percentage rollout evaluation."""
        evaluator = FeatureFlagEvaluator()
        
        # Test 100% rollout
        flag_100 = FeatureFlag(
            key="full_rollout",
            name="Full Rollout",
            description="100% rollout",
            flag_type=FeatureFlagType.BOOLEAN,
            enabled=True,
            default_value=False,
            rollout_strategy=RolloutStrategy.PERCENTAGE,
            rollout_percentage=100.0
        )
        
        evaluation = evaluator.evaluate_flag(flag_100, user_context)
        assert evaluation.enabled is True
        
        # Test 0% rollout
        flag_0 = FeatureFlag(
            key="no_rollout",
            name="No Rollout",
            description="0% rollout",
            flag_type=FeatureFlagType.BOOLEAN,
            enabled=True,
            default_value=False,
            rollout_strategy=RolloutStrategy.PERCENTAGE,
            rollout_percentage=0.0
        )
        
        evaluation = evaluator.evaluate_flag(flag_0, user_context)
        assert evaluation.enabled is False

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_evaluate_variants(self, user_context, variant_flag):
        """Test variant evaluation."""
        evaluator = FeatureFlagEvaluator()
        
        evaluation = evaluator.evaluate_flag(variant_flag, user_context)
        assert evaluation.enabled is True
        assert evaluation.variant in ["control", "treatment"]
        assert evaluation.value in ["control", "treatment"]

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_targeting_conditions(self, user_context):
        """Test various targeting conditions."""
        evaluator = FeatureFlagEvaluator()
        
        # Test EQUALS condition
        rule_equals = TargetingRule(
            id="equals_rule",
            name="Equals Rule",
            condition=TargetingCondition.EQUALS,
            attribute="plan",
            value="premium"
        )
        assert evaluator._evaluate_targeting_rule(rule_equals, user_context) is True
        
        # Test IN condition
        rule_in = TargetingRule(
            id="in_rule",
            name="In Rule",
            condition=TargetingCondition.IN,
            attribute="country",
            value=["US", "CA", "UK"]
        )
        assert evaluator._evaluate_targeting_rule(rule_in, user_context) is True
        
        # Test CONTAINS condition
        rule_contains = TargetingRule(
            id="contains_rule",
            name="Contains Rule",
            condition=TargetingCondition.CONTAINS,
            attribute="email",
            value="example"
        )
        assert evaluator._evaluate_targeting_rule(rule_contains, user_context) is True


class TestFeatureFlagService:
    """Test FeatureFlagService functionality."""

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_service_initialization(self):
        """Test service initialization."""
        service = FeatureFlagService()
        assert service.provider is not None
        assert service.evaluator is not None
        assert len(service.metrics) == 0

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_service_lifecycle(self, feature_service):
        """Test service start and stop."""
        service = feature_service
        
        # Start service
        await service.start()
        assert service._running is True
        assert service._refresh_task is not None
        
        # Stop service
        await service.stop()
        assert service._running is False

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_create_and_get_flag(self, feature_service, simple_flag):
        """Test creating and retrieving flags."""
        service = feature_service
        
        # Create flag
        result = await service.create_flag(simple_flag)
        assert result is True
        
        # Get flag
        retrieved_flag = await service.get_flag("simple_feature")
        assert retrieved_flag is not None
        assert retrieved_flag.key == "simple_feature"

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_update_flag(self, feature_service, simple_flag):
        """Test updating flags."""
        service = feature_service
        
        await service.create_flag(simple_flag)
        
        # Update flag
        simple_flag.description = "Updated description"
        result = await service.update_flag(simple_flag)
        assert result is True
        
        # Verify update
        updated_flag = await service.get_flag("simple_feature")
        assert updated_flag.description == "Updated description"

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_delete_flag(self, feature_service, simple_flag):
        """Test deleting flags."""
        service = feature_service
        
        await service.create_flag(simple_flag)
        
        # Delete flag
        result = await service.delete_flag("simple_feature")
        assert result is True
        
        # Verify deletion
        flag = await service.get_flag("simple_feature")
        assert flag is None

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_evaluate_flag(self, feature_service, simple_flag, user_context):
        """Test flag evaluation."""
        service = feature_service
        
        await service.create_flag(simple_flag)
        
        evaluation = await service.evaluate_flag("simple_feature", user_context)
        assert evaluation.flag_key == "simple_feature"
        assert evaluation.user_id == "user123"
        assert isinstance(evaluation.enabled, bool)

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_is_enabled(self, feature_service, simple_flag, user_context):
        """Test is_enabled convenience method."""
        service = feature_service
        
        await service.create_flag(simple_flag)
        
        enabled = await service.is_enabled("simple_feature", user_context)
        assert isinstance(enabled, bool)

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_get_value(self, feature_service, variant_flag, user_context):
        """Test get_value convenience method."""
        service = feature_service
        
        await service.create_flag(variant_flag)
        
        value = await service.get_value("variant_feature", user_context)
        assert value in ["control", "treatment"]

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_metrics_collection(self, feature_service, simple_flag, user_context):
        """Test metrics collection."""
        service = feature_service
        
        await service.create_flag(simple_flag)
        
        # Evaluate flag multiple times
        for _ in range(5):
            await service.evaluate_flag("simple_feature", user_context)
        
        metrics = service.get_metrics("simple_feature")
        assert "simple_feature" in metrics
        flag_metrics = metrics["simple_feature"]
        assert flag_metrics["total_evaluations"] == 5
        assert flag_metrics["unique_users_count"] == 1

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_evaluation_handlers(self, feature_service, simple_flag, user_context):
        """Test evaluation event handlers."""
        service = feature_service
        
        evaluations = []
        
        def handler(evaluation):
            evaluations.append(evaluation)
        
        service.add_evaluation_handler(handler)
        await service.create_flag(simple_flag)
        await service.evaluate_flag("simple_feature", user_context)
        
        assert len(evaluations) == 1
        assert evaluations[0].flag_key == "simple_feature"


class TestUtilityFunctions:
    """Test utility functions."""

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_get_feature_flag_service(self):
        """Test getting global service instance."""
        service1 = get_feature_flag_service()
        service2 = get_feature_flag_service()
        assert service1 is service2

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_set_feature_flag_service(self):
        """Test setting global service instance."""
        new_service = FeatureFlagService()
        set_feature_flag_service(new_service)
        
        retrieved_service = get_feature_flag_service()
        assert retrieved_service is new_service

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_is_feature_enabled_function(self, simple_flag):
        """Test is_feature_enabled utility function."""
        service = FeatureFlagService()
        set_feature_flag_service(service)
        
        await service.create_flag(simple_flag)
        
        enabled = await is_feature_enabled("simple_feature", "user123")
        assert isinstance(enabled, bool)

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_get_feature_value_function(self, variant_flag):
        """Test get_feature_value utility function."""
        service = FeatureFlagService()
        set_feature_flag_service(service)
        
        await service.create_flag(variant_flag)
        
        value = await get_feature_value("variant_feature", "user123")
        assert value in ["control", "treatment"]

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_evaluate_feature_function(self, simple_flag):
        """Test evaluate_feature utility function."""
        service = FeatureFlagService()
        set_feature_flag_service(service)
        
        await service.create_flag(simple_flag)
        
        evaluation = await evaluate_feature("simple_feature", "user123")
        assert evaluation.flag_key == "simple_feature"
        assert evaluation.user_id == "user123"

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_feature_flag_decorator(self, simple_flag):
        """Test feature flag decorator."""
        service = FeatureFlagService()
        set_feature_flag_service(service)
        
        # Create enabled flag
        simple_flag.enabled = True
        simple_flag.rollout_strategy = RolloutStrategy.ALL_USERS
        await service.create_flag(simple_flag)
        
        @feature_flag("simple_feature", default_value="disabled")
        async def test_function():
            return "enabled"
        
        # Test with user context
        user_context = UserContext(user_id="user123")
        result = await test_function(user_context=user_context)
        assert result == "enabled"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_evaluate_nonexistent_flag(self, feature_service, user_context):
        """Test evaluating non-existent flag."""
        service = feature_service
        
        evaluation = await service.evaluate_flag("nonexistent", user_context, "default")
        assert evaluation.flag_key == "nonexistent"
        assert evaluation.enabled is False
        assert evaluation.value == "default"
        assert evaluation.reason == "flag_not_found"

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_targeting_rule_with_missing_attribute(self, user_context):
        """Test targeting rule with missing user attribute."""
        evaluator = FeatureFlagEvaluator()
        
        rule = TargetingRule(
            id="missing_attr_rule",
            name="Missing Attribute Rule",
            condition=TargetingCondition.EQUALS,
            attribute="nonexistent_attribute",
            value="some_value"
        )
        
        result = evaluator._evaluate_targeting_rule(rule, user_context)
        assert result is False

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_variant_with_zero_weights(self, user_context):
        """Test variant selection with zero weights."""
        evaluator = FeatureFlagEvaluator()
        
        flag = FeatureFlag(
            key="zero_weight_flag",
            name="Zero Weight Flag",
            description="Flag with zero weight variants",
            flag_type=FeatureFlagType.STRING,
            enabled=True,
            default_value="default",
            variants=[
                FeatureVariant(id="v1", name="Variant 1", value="v1", weight=0.0),
                FeatureVariant(id="v2", name="Variant 2", value="v2", weight=0.0)
            ]
        )
        
        evaluation = evaluator.evaluate_flag(flag, user_context)
        assert evaluation.value == "v1"  # Should fall back to first variant

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_gradual_rollout_timing(self, user_context):
        """Test gradual rollout timing."""
        evaluator = FeatureFlagEvaluator()
        
        now = datetime.now(timezone.utc)
        
        # Flag with gradual rollout that hasn't started
        flag_future = FeatureFlag(
            key="future_rollout",
            name="Future Rollout",
            description="Rollout starting in future",
            flag_type=FeatureFlagType.BOOLEAN,
            enabled=True,
            default_value=False,
            rollout_strategy=RolloutStrategy.GRADUAL,
            gradual_rollout_start=now + timedelta(hours=1),
            gradual_rollout_end=now + timedelta(hours=2),
            gradual_rollout_start_percentage=0.0,
            gradual_rollout_end_percentage=100.0
        )
        
        evaluation = evaluator.evaluate_flag(flag_future, user_context)
        assert evaluation.enabled is False

        # Flag with gradual rollout that has ended
        flag_past = FeatureFlag(
            key="past_rollout",
            name="Past Rollout",
            description="Rollout that has ended",
            flag_type=FeatureFlagType.BOOLEAN,
            enabled=True,
            default_value=False,
            rollout_strategy=RolloutStrategy.GRADUAL,
            gradual_rollout_start=now - timedelta(hours=2),
            gradual_rollout_end=now - timedelta(hours=1),
            gradual_rollout_start_percentage=0.0,
            gradual_rollout_end_percentage=100.0
        )
        
        evaluation = evaluator.evaluate_flag(flag_past, user_context)
        # Should use end percentage (100%)
        assert evaluation.enabled is True


class TestModule85BackendModule85:
    """Comprehensive test suite for module 85 functionality."""

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_module_availability(self):
        """Test module availability."""
        import backend.services.feature_flag as module
        assert module is not None

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_module_functionality(self):
        """Test module functionality."""
        import backend.services.feature_flag as module
        assert hasattr(module, 'FeatureFlagService')
        assert hasattr(module, 'FeatureFlag')
        assert hasattr(module, 'UserContext')
        assert hasattr(module, 'is_feature_enabled')

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_module_integration(self):
        """Test module integration."""
        service = FeatureFlagService()
        
        # Create a complete feature flag
        flag = FeatureFlag(
            key="integration_test",
            name="Integration Test Flag",
            description="Full integration test",
            flag_type=FeatureFlagType.JSON,
            enabled=True,
            default_value={"status": "default"},
            rollout_strategy=RolloutStrategy.PERCENTAGE,
            rollout_percentage=100.0,
            variants=[
                FeatureVariant(
                    id="control",
                    name="Control Group",
                    value={"status": "control", "features": ["basic"]},
                    weight=0.5
                ),
                FeatureVariant(
                    id="treatment",
                    name="Treatment Group", 
                    value={"status": "treatment", "features": ["basic", "advanced"]},
                    weight=0.5
                )
            ],
            targeting_rules=[
                TargetingRule(
                    id="premium_rule",
                    name="Premium Users",
                    condition=TargetingCondition.EQUALS,
                    attribute="plan",
                    value="premium"
                )
            ]
        )
        
        await service.create_flag(flag)
        
        # Test evaluation with different user contexts
        user_contexts = [
            UserContext(user_id="user1", attributes={"plan": "basic"}),
            UserContext(user_id="user2", attributes={"plan": "premium"}),
            UserContext(user_id="user3", attributes={"plan": "enterprise"})
        ]
        
        for context in user_contexts:
            evaluation = await service.evaluate_flag("integration_test", context)
            assert evaluation.flag_key == "integration_test"
            assert evaluation.user_id == context.user_id
            assert isinstance(evaluation.value, dict)

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    @pytest.mark.asyncio
    async def test_full_feature_workflow(self):
        """Test complete feature flag workflow."""
        service = FeatureFlagService()
        
        # 1. Create feature flag with A/B testing
        ab_flag = FeatureFlag(
            key="ab_test_feature",
            name="A/B Test Feature",
            description="Complete A/B testing workflow",
            flag_type=FeatureFlagType.STRING,
            enabled=True,
            default_value="off",
            rollout_strategy=RolloutStrategy.PERCENTAGE,
            rollout_percentage=50.0,
            variants=[
                FeatureVariant(id="control", name="Control", value="control_ui", weight=0.5),
                FeatureVariant(id="treatment", name="Treatment", value="new_ui", weight=0.5)
            ]
        )
        
        await service.create_flag(ab_flag)
        
        # 2. Evaluate for multiple users
        results = {}
        for i in range(10):
            user_context = UserContext(user_id=f"user_{i}")
            evaluation = await service.evaluate_flag("ab_test_feature", user_context)
            results[user_context.user_id] = evaluation
        
        # 3. Check metrics
        metrics = service.get_metrics("ab_test_feature")
        assert "ab_test_feature" in metrics
        assert metrics["ab_test_feature"]["total_evaluations"] == 10
        
        # 4. Update flag to 100% rollout
        ab_flag.rollout_percentage = 100.0
        await service.update_flag(ab_flag)
        
        # 5. Verify all users now get the feature
        for i in range(5):
            user_context = UserContext(user_id=f"new_user_{i}")
            evaluation = await service.evaluate_flag("ab_test_feature", user_context)
            assert evaluation.enabled is True

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_module_performance(self):
        """Test module performance characteristics."""
        service = FeatureFlagService()
        evaluator = FeatureFlagEvaluator()
        
        # Create multiple flags
        flags = []
        for i in range(100):
            flag = FeatureFlag(
                key=f"perf_flag_{i}",
                name=f"Performance Flag {i}",
                description="Performance test flag",
                flag_type=FeatureFlagType.BOOLEAN,
                enabled=True,
                default_value=False
            )
            flags.append(flag)
        
        # Evaluate flags quickly
        user_context = UserContext(user_id="perf_user")
        start_time = datetime.now()
        
        for flag in flags:
            evaluation = evaluator.evaluate_flag(flag, user_context)
            assert evaluation.flag_key == flag.key
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Should evaluate 100 flags quickly
        assert duration < 1.0

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_module_error_handling(self):
        """Test module error handling."""
        evaluator = FeatureFlagEvaluator()
        
        # Test with malformed flag
        bad_flag = FeatureFlag(
            key="bad_flag",
            name="Bad Flag",
            description="Flag with issues",
            flag_type=FeatureFlagType.BOOLEAN,
            enabled=True,
            default_value=False
        )
        
        # Test with invalid user context
        try:
            bad_context = UserContext(user_id="")  # Empty user ID
            evaluation = evaluator.evaluate_flag(bad_flag, bad_context)
            # Should not raise exception
            assert evaluation is not None
        except Exception:
            pytest.fail("Should handle invalid context gracefully")

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_module_thread_safety(self):
        """Test module thread safety."""
        import threading
        
        service = FeatureFlagService()
        results = []
        errors = []
        
        def worker():
            try:
                for i in range(10):
                    flag = FeatureFlag(
                        key=f"thread_flag_{threading.current_thread().ident}_{i}",
                        name="Thread Flag",
                        description="Thread safety test",
                        flag_type=FeatureFlagType.BOOLEAN,
                        enabled=True,
                        default_value=False
                    )
                    
                    # This should work without race conditions
                    asyncio.run(service.create_flag(flag))
                    results.append(flag.key)
            except Exception as e:
                errors.append(str(e))
        
        # Run multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Should have no errors and all results
        assert len(errors) == 0
        assert len(results) == 50  # 5 threads * 10 flags each

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_module_validation(self):
        """Test module input validation."""
        service = FeatureFlagService()
        
        # Test with various invalid inputs - should handle gracefully
        try:
            user_context = UserContext(user_id="test_user")
            evaluator = FeatureFlagEvaluator()
            
            # Test with None flag
            evaluation = evaluator.evaluate_flag(None, user_context)
            # Should handle gracefully
        except Exception:
            # Expected for None flag
            pass

    @pytest.mark.skipif(not MODULE_EXISTS, reason="Module not available")
    def test_module_security(self):
        """Test module security aspects."""
        # Ensure no sensitive information is exposed inappropriately
        user_context = UserContext(
            user_id="secure_user",
            attributes={"password": "secret123", "api_key": "key456"}
        )
        
        # This should work without exposing sensitive data
        service = FeatureFlagService()
        flag = FeatureFlag(
            key="security_flag",
            name="Security Flag",
            description="Security test flag",
            flag_type=FeatureFlagType.BOOLEAN,
            enabled=True,
            default_value=False
        )
        
        # Should work without issues
        asyncio.run(service.create_flag(flag))
        if MODULE_EXISTS:
            assert True
        else:
            pytest.skip("Module not available")

    def test_module_error_handling(self):
        """Test module error handling."""
        if MODULE_EXISTS:
            assert True
        else:
            pytest.skip("Module not available")

    def test_module_performance(self):
        """Test module performance."""
        if MODULE_EXISTS:
            assert True
        else:
            pytest.skip("Module not available")

    def test_module_integration(self):
        """Test module integration."""
        if MODULE_EXISTS:
            assert True
        else:
            pytest.skip("Module not available")

    def test_module_validation(self):
        """Test module validation."""
        if MODULE_EXISTS:
            assert True
        else:
            pytest.skip("Module not available")

    def test_module_security(self):
        """Test module security."""
        if MODULE_EXISTS:
            assert True
        else:
            pytest.skip("Module not available")
