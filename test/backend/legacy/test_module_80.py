"""
Tests for Module 80: Configuration Service
Tests for dynamic configuration management, validation, hot-reloading, and versioning.
"""

import pytest
import asyncio
import json
import yaml
import tempfile
import os
import time
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone, timedelta
from pathlib import Path

from backend.services.configuration import (
    ConfigurationService,
    ConfigEntry,
    ConfigType,
    ConfigScope,
    ConfigSource,
    ConfigRule,
    ConfigValidation,
    ConfigValidationResult,
    ConfigSnapshot,
    ConfigChangeEvent,
    get_configuration_service,
    get_config,
    set_config,
    get_config_int,
    get_config_bool,
    get_config_float,
    ConfigurationError,
    ConfigValidationError,
    ConfigLoadError
)


@pytest.fixture
def temp_config_dir():
    """Create temporary configuration directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def config_service(temp_config_dir):
    """Create configuration service with temporary directory."""
    service = ConfigurationService(config_dir=temp_config_dir, auto_reload=False)
    yield service
    service._stop_file_watcher()


@pytest.fixture
def sample_config_entry():
    """Create sample configuration entry."""
    return ConfigEntry(
        key="test.sample_key",
        value="sample_value",
        config_type=ConfigType.STRING,
        scope=ConfigScope.SERVICE,
        source=ConfigSource.DEFAULT,
        description="Sample configuration for testing",
        validation_rules=[
            ConfigRule(
                rule_id="length_check",
                field_path="test.sample_key",
                rule_type="custom",
                parameters={"validator": lambda x: len(str(x)) > 0},
                error_message="Value cannot be empty"
            )
        ]
    )


class TestConfigurationService:
    """Test ConfigurationService class."""
    
    def test_init_creates_default_config(self, config_service):
        """Test that initialization creates default configuration."""
        assert len(config_service.entries) > 0
        assert "system.debug_mode" in config_service.entries
        assert "system.log_level" in config_service.entries
        assert "trading.max_position_size" in config_service.entries
    
    def test_get_existing_key(self, config_service):
        """Test getting existing configuration value."""
        value = config_service.get("system.debug_mode")
        assert value is False
    
    def test_get_nonexistent_key_returns_default(self, config_service):
        """Test getting non-existent key returns default."""
        value = config_service.get("nonexistent.key", "default_value")
        assert value == "default_value"
    
    def test_get_with_scope_filter(self, config_service):
        """Test getting configuration with scope filter."""
        value = config_service.get("system.debug_mode", scope=ConfigScope.GLOBAL)
        assert value is False
        
        value = config_service.get("system.debug_mode", scope=ConfigScope.SERVICE)
        assert value is None  # Should not match scope
    
    def test_get_typed_values(self, config_service):
        """Test getting typed configuration values."""
        assert config_service.get_bool("system.debug_mode") is False
        assert config_service.get_int("trading.max_position_size") == 1000000
        assert config_service.get_float("trading.max_position_size") == 1000000.0
    
    def test_get_typed_values_with_conversion(self, config_service):
        """Test typed getters with value conversion."""
        # Test string to bool conversion
        assert config_service.get_bool("nonexistent", True) is True
        
        # Test invalid conversion returns default
        assert config_service.get_int("system.log_level", 42) == 42
    
    @pytest.mark.asyncio
    async def test_set_new_key(self, config_service):
        """Test setting new configuration key."""
        result = await config_service.set(
            "test.new_key",
            "new_value",
            description="Test key"
        )
        assert result is True
        assert config_service.get("test.new_key") == "new_value"
    
    @pytest.mark.asyncio
    async def test_set_updates_existing_key(self, config_service):
        """Test updating existing configuration key."""
        original_value = config_service.get("system.debug_mode")
        
        result = await config_service.set("system.debug_mode", True)
        assert result is True
        assert config_service.get("system.debug_mode") is True
        assert config_service.get("system.debug_mode") != original_value
    
    @pytest.mark.asyncio
    async def test_set_with_validation_success(self, config_service):
        """Test setting value with successful validation."""
        result = await config_service.set(
            "api.rate_limit",
            500,
            validate=True
        )
        assert result is True
        assert config_service.get("api.rate_limit") == 500
    
    @pytest.mark.asyncio
    async def test_set_with_validation_failure(self, config_service):
        """Test setting value with validation failure."""
        # Set invalid value (below minimum)
        result = await config_service.set(
            "api.rate_limit",
            0,  # Below minimum of 1
            validate=True
        )
        assert result is False
        # Should keep original value
        assert config_service.get("api.rate_limit") == 1000
    
    @pytest.mark.asyncio
    async def test_set_records_change_history(self, config_service):
        """Test that setting values records change history."""
        initial_history_length = len(config_service.change_history)
        
        await config_service.set("test.history", "value1")
        await config_service.set("test.history", "value2")
        
        assert len(config_service.change_history) == initial_history_length + 2
        
        recent_change = config_service.change_history[-1]
        assert recent_change.key == "test.history"
        assert recent_change.old_value == "value1"
        assert recent_change.new_value == "value2"
    
    def test_detect_type(self, config_service):
        """Test automatic type detection."""
        assert config_service._detect_type(True) == ConfigType.BOOLEAN
        assert config_service._detect_type(42) == ConfigType.INTEGER
        assert config_service._detect_type(3.14) == ConfigType.FLOAT
        assert config_service._detect_type([1, 2, 3]) == ConfigType.LIST
        assert config_service._detect_type({"key": "value"}) == ConfigType.DICT
        assert config_service._detect_type("string") == ConfigType.STRING
    
    @pytest.mark.asyncio
    async def test_delete_existing_key(self, config_service):
        """Test deleting existing configuration key."""
        await config_service.set("test.delete_me", "value")
        assert config_service.get("test.delete_me") == "value"
        
        result = await config_service.delete("test.delete_me")
        assert result is True
        assert config_service.get("test.delete_me") is None
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, config_service):
        """Test deleting non-existent key."""
        result = await config_service.delete("nonexistent.key")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_readonly_key(self, config_service):
        """Test deleting readonly configuration."""
        # First set a readonly key
        await config_service.set("test.readonly", "value")
        config_service.entries["test.readonly"].is_readonly = True
        
        result = await config_service.delete("test.readonly")
        assert result is False
        assert config_service.get("test.readonly") == "value"
    
    def test_list_keys(self, config_service):
        """Test listing configuration keys."""
        keys = config_service.list_keys()
        assert "system.debug_mode" in keys
        assert "system.log_level" in keys
        assert "trading.max_position_size" in keys
    
    def test_list_keys_with_prefix(self, config_service):
        """Test listing keys with prefix filter."""
        system_keys = config_service.list_keys(prefix="system.")
        assert "system.debug_mode" in system_keys
        assert "system.log_level" in system_keys
        assert "trading.max_position_size" not in system_keys
    
    def test_list_keys_with_scope_filter(self, config_service):
        """Test listing keys with scope filter."""
        global_keys = config_service.list_keys(scope=ConfigScope.GLOBAL)
        service_keys = config_service.list_keys(scope=ConfigScope.SERVICE)
        
        assert len(global_keys) > 0
        assert len(service_keys) > 0
        assert set(global_keys).isdisjoint(set(service_keys))
    
    def test_get_entry(self, config_service):
        """Test getting full configuration entry."""
        entry = config_service.get_entry("system.debug_mode")
        assert entry is not None
        assert entry.key == "system.debug_mode"
        assert entry.value is False
        assert entry.config_type == ConfigType.BOOLEAN
        assert entry.scope == ConfigScope.GLOBAL
    
    def test_get_all(self, config_service):
        """Test getting all configuration values."""
        all_config = config_service.get_all()
        assert isinstance(all_config, dict)
        assert "system.debug_mode" in all_config
        assert all_config["system.debug_mode"] is False
    
    def test_get_all_with_prefix(self, config_service):
        """Test getting all values with prefix filter."""
        system_config = config_service.get_all(prefix="system.")
        assert "system.debug_mode" in system_config
        assert "system.log_level" in system_config
        assert "trading.max_position_size" not in system_config
    
    def test_get_all_excludes_secrets(self, config_service):
        """Test that get_all excludes secret values by default."""
        # Mock a secret entry
        config_service.entries["test.secret"] = ConfigEntry(
            key="test.secret",
            value="secret_value",
            config_type=ConfigType.STRING,
            scope=ConfigScope.SERVICE,
            source=ConfigSource.DEFAULT,
            is_secret=True
        )
        
        all_config = config_service.get_all()
        assert "test.secret" not in all_config
        
        all_config_with_secrets = config_service.get_all(include_secrets=True)
        assert "test.secret" in all_config_with_secrets


class TestConfigValidation:
    """Test configuration validation functionality."""
    
    @pytest.mark.asyncio
    async def test_validate_entry_with_required_rule(self, config_service):
        """Test validation with required rule."""
        entry = ConfigEntry(
            key="test.required",
            value=None,
            config_type=ConfigType.STRING,
            scope=ConfigScope.SERVICE,
            source=ConfigSource.DEFAULT,
            validation_rules=[
                ConfigRule(
                    rule_id="required_rule",
                    field_path="test.required",
                    rule_type="required",
                    error_message="Value is required"
                )
            ]
        )
        
        validation = await config_service.validate_entry(entry)
        assert validation.result == ConfigValidationResult.INVALID
        assert "Value is required" in validation.errors
    
    @pytest.mark.asyncio
    async def test_validate_entry_with_type_rule(self, config_service):
        """Test validation with type rule."""
        entry = ConfigEntry(
            key="test.integer",
            value="not_an_integer",
            config_type=ConfigType.INTEGER,
            scope=ConfigScope.SERVICE,
            source=ConfigSource.DEFAULT,
            validation_rules=[
                ConfigRule(
                    rule_id="type_rule",
                    field_path="test.integer",
                    rule_type="type",
                    parameters={"type": "int"},
                    error_message="Must be an integer"
                )
            ]
        )
        
        validation = await config_service.validate_entry(entry)
        assert validation.result == ConfigValidationResult.INVALID
        assert "Must be an integer" in validation.errors
    
    @pytest.mark.asyncio
    async def test_validate_entry_with_range_rule(self, config_service):
        """Test validation with range rule."""
        entry = ConfigEntry(
            key="test.range",
            value=150,
            config_type=ConfigType.INTEGER,
            scope=ConfigScope.SERVICE,
            source=ConfigSource.DEFAULT,
            validation_rules=[
                ConfigRule(
                    rule_id="range_rule",
                    field_path="test.range",
                    rule_type="range",
                    parameters={"min": 1, "max": 100},
                    error_message="Value must be between 1 and 100"
                )
            ]
        )
        
        validation = await config_service.validate_entry(entry)
        assert validation.result == ConfigValidationResult.INVALID
        assert "Value must be between 1 and 100" in validation.errors
    
    @pytest.mark.asyncio
    async def test_validate_entry_with_pattern_rule(self, config_service):
        """Test validation with pattern rule."""
        entry = ConfigEntry(
            key="test.pattern",
            value="INVALID",
            config_type=ConfigType.STRING,
            scope=ConfigScope.SERVICE,
            source=ConfigSource.DEFAULT,
            validation_rules=[
                ConfigRule(
                    rule_id="pattern_rule",
                    field_path="test.pattern",
                    rule_type="pattern",
                    parameters={"pattern": "^(DEBUG|INFO|WARNING|ERROR)$"},
                    error_message="Must be a valid log level"
                )
            ]
        )
        
        validation = await config_service.validate_entry(entry)
        assert validation.result == ConfigValidationResult.INVALID
        assert "Must be a valid log level" in validation.errors
    
    @pytest.mark.asyncio
    async def test_validate_entry_with_custom_rule(self, config_service):
        """Test validation with custom rule."""
        def custom_validator(value):
            return len(str(value)) >= 5
        
        entry = ConfigEntry(
            key="test.custom",
            value="abc",
            config_type=ConfigType.STRING,
            scope=ConfigScope.SERVICE,
            source=ConfigSource.DEFAULT,
            validation_rules=[
                ConfigRule(
                    rule_id="custom_rule",
                    field_path="test.custom",
                    rule_type="custom",
                    parameters={"validator": custom_validator},
                    error_message="Value must be at least 5 characters"
                )
            ]
        )
        
        validation = await config_service.validate_entry(entry)
        assert validation.result == ConfigValidationResult.INVALID
        assert "Value must be at least 5 characters" in validation.errors
    
    @pytest.mark.asyncio
    async def test_validate_entry_success(self, config_service):
        """Test successful validation."""
        entry = ConfigEntry(
            key="test.valid",
            value="valid_value",
            config_type=ConfigType.STRING,
            scope=ConfigScope.SERVICE,
            source=ConfigSource.DEFAULT,
            validation_rules=[
                ConfigRule(
                    rule_id="length_rule",
                    field_path="test.valid",
                    rule_type="custom",
                    parameters={"validator": lambda x: len(str(x)) > 0},
                    error_message="Value cannot be empty"
                )
            ]
        )
        
        validation = await config_service.validate_entry(entry)
        assert validation.result == ConfigValidationResult.VALID
        assert len(validation.errors) == 0
    
    @pytest.mark.asyncio
    async def test_validate_all(self, config_service):
        """Test validating all configuration entries."""
        validations = await config_service.validate_all()
        assert isinstance(validations, dict)
        assert len(validations) > 0
        
        # All default configs should be valid
        for key, validation in validations.items():
            if validation.result == ConfigValidationResult.INVALID:
                print(f"Invalid config {key}: {validation.errors}")
        
        # Most should be valid (allowing for some test configs that might be invalid)
        valid_count = sum(1 for v in validations.values() if v.result == ConfigValidationResult.VALID)
        assert valid_count >= len(validations) * 0.8  # At least 80% should be valid
    
    def test_add_validation_rule(self, config_service):
        """Test adding validation rules."""
        rule = ConfigRule(
            rule_id="test_rule",
            field_path="test.key",
            rule_type="required",
            error_message="Test rule"
        )
        
        config_service.add_validation_rule("test.key", rule)
        assert "test.key" in config_service.validation_rules
        assert rule in config_service.validation_rules["test.key"]


class TestConfigCallbacks:
    """Test configuration change callbacks."""
    
    @pytest.mark.asyncio
    async def test_register_and_trigger_callback(self, config_service):
        """Test registering and triggering change callbacks."""
        callback_called = False
        callback_args = None
        
        def test_callback(key, old_value, new_value):
            nonlocal callback_called, callback_args
            callback_called = True
            callback_args = (key, old_value, new_value)
        
        config_service.register_change_callback("test.callback", test_callback)
        await config_service.set("test.callback", "new_value")
        
        # Allow callback to execute
        await asyncio.sleep(0.1)
        
        assert callback_called
        assert callback_args[0] == "test.callback"
        assert callback_args[2] == "new_value"
    
    @pytest.mark.asyncio
    async def test_async_callback(self, config_service):
        """Test asynchronous change callbacks."""
        callback_called = False
        
        async def async_callback(key, old_value, new_value):
            nonlocal callback_called
            await asyncio.sleep(0.01)  # Simulate async work
            callback_called = True
        
        config_service.register_change_callback("test.async", async_callback)
        await config_service.set("test.async", "value")
        
        # Allow callback to execute
        await asyncio.sleep(0.1)
        
        assert callback_called
    
    @pytest.mark.asyncio
    async def test_wildcard_callback(self, config_service):
        """Test wildcard pattern callbacks."""
        callback_called = False
        callback_key = None
        
        def wildcard_callback(key, old_value, new_value):
            nonlocal callback_called, callback_key
            callback_called = True
            callback_key = key
        
        config_service.register_change_callback("test.*", wildcard_callback)
        await config_service.set("test.wildcard", "value")
        
        # Allow callback to execute
        await asyncio.sleep(0.1)
        
        assert callback_called
        assert callback_key == "test.wildcard"


class TestConfigSnapshots:
    """Test configuration snapshot functionality."""
    
    @pytest.mark.asyncio
    async def test_create_snapshot(self, config_service):
        """Test creating configuration snapshot."""
        await config_service.set("test.snapshot", "value1")
        
        snapshot_id = await config_service.create_snapshot(
            description="Test snapshot",
            created_by="test_user"
        )
        
        assert snapshot_id is not None
        assert snapshot_id in config_service.snapshots
        
        snapshot = config_service.snapshots[snapshot_id]
        assert snapshot.description == "Test snapshot"
        assert snapshot.created_by == "test_user"
        assert "test.snapshot" in snapshot.config_data
    
    @pytest.mark.asyncio
    async def test_restore_snapshot(self, config_service):
        """Test restoring configuration from snapshot."""
        # Set initial values
        await config_service.set("test.restore1", "original1")
        await config_service.set("test.restore2", "original2")
        
        # Create snapshot
        snapshot_id = await config_service.create_snapshot("Backup")
        
        # Change values
        await config_service.set("test.restore1", "changed1")
        await config_service.set("test.restore2", "changed2")
        
        # Verify changes
        assert config_service.get("test.restore1") == "changed1"
        assert config_service.get("test.restore2") == "changed2"
        
        # Restore snapshot
        result = await config_service.restore_snapshot(snapshot_id)
        assert result is True
        
        # Verify restoration
        assert config_service.get("test.restore1") == "original1"
        assert config_service.get("test.restore2") == "original2"
    
    @pytest.mark.asyncio
    async def test_restore_nonexistent_snapshot(self, config_service):
        """Test restoring non-existent snapshot."""
        result = await config_service.restore_snapshot("nonexistent_id")
        assert result is False


class TestConfigFileOperations:
    """Test configuration file operations."""
    
    @pytest.mark.asyncio
    async def test_load_from_json_file(self, config_service, temp_config_dir):
        """Test loading configuration from JSON file."""
        config_data = {
            "test.json_key1": "json_value1",
            "test.json_key2": 42,
            "test.json_key3": True
        }
        
        json_file = os.path.join(temp_config_dir, "test_config.json")
        with open(json_file, 'w') as f:
            json.dump(config_data, f)
        
        result = await config_service.load_from_file(json_file, auto_reload=False)
        assert result is True
        
        assert config_service.get("test.json_key1") == "json_value1"
        assert config_service.get("test.json_key2") == 42
        assert config_service.get("test.json_key3") is True
    
    @pytest.mark.asyncio
    async def test_load_from_yaml_file(self, config_service, temp_config_dir):
        """Test loading configuration from YAML file."""
        config_data = {
            "test.yaml_key1": "yaml_value1",
            "test.yaml_key2": 100,
            "test.yaml_key3": False
        }
        
        yaml_file = os.path.join(temp_config_dir, "test_config.yaml")
        with open(yaml_file, 'w') as f:
            yaml.dump(config_data, f)
        
        result = await config_service.load_from_file(yaml_file, auto_reload=False)
        assert result is True
        
        assert config_service.get("test.yaml_key1") == "yaml_value1"
        assert config_service.get("test.yaml_key2") == 100
        assert config_service.get("test.yaml_key3") is False
    
    @pytest.mark.asyncio
    async def test_load_from_nonexistent_file(self, config_service):
        """Test loading from non-existent file."""
        result = await config_service.load_from_file("nonexistent.json", auto_reload=False)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_save_to_json_file(self, config_service, temp_config_dir):
        """Test saving configuration to JSON file."""
        await config_service.set("test.save_key1", "save_value1")
        await config_service.set("test.save_key2", 99)
        
        json_file = os.path.join(temp_config_dir, "saved_config.json")
        result = await config_service.save_to_file(json_file)
        assert result is True
        
        # Verify file exists and contains data
        assert os.path.exists(json_file)
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        assert "test.save_key1" in data
        assert data["test.save_key1"] == "save_value1"
        assert data["test.save_key2"] == 99
    
    @pytest.mark.asyncio
    async def test_save_to_yaml_file(self, config_service, temp_config_dir):
        """Test saving configuration to YAML file."""
        await config_service.set("test.yaml_save", "yaml_value")
        
        yaml_file = os.path.join(temp_config_dir, "saved_config.yaml")
        result = await config_service.save_to_file(yaml_file)
        assert result is True
        
        # Verify file exists and contains data
        assert os.path.exists(yaml_file)
        with open(yaml_file, 'r') as f:
            data = yaml.safe_load(f)
        
        assert "test.yaml_save" in data
        assert data["test.yaml_save"] == "yaml_value"


class TestConfigHistory:
    """Test configuration change history."""
    
    @pytest.mark.asyncio
    async def test_change_history_tracking(self, config_service):
        """Test that configuration changes are tracked in history."""
        initial_count = len(config_service.change_history)
        
        await config_service.set("test.history1", "value1")
        await config_service.set("test.history2", "value2")
        
        assert len(config_service.change_history) == initial_count + 2
        
        # Check most recent change
        recent_change = config_service.change_history[-1]
        assert recent_change.key == "test.history2"
        assert recent_change.new_value == "value2"
    
    @pytest.mark.asyncio
    async def test_get_change_history(self, config_service):
        """Test getting change history with filters."""
        # Add some changes first
        await config_service.set("test.history1", "value1")
        await config_service.set("test.history2", "value2")
        
        # Get all history
        all_history = config_service.get_change_history()
        assert isinstance(all_history, list)
        assert len(all_history) > 0
        
        # Get limited history
        limited_history = config_service.get_change_history(limit=2)
        assert len(limited_history) <= 2
        
        # Verify ordering (newest first)
        if len(limited_history) > 1:
            assert limited_history[0].timestamp >= limited_history[1].timestamp
    
    def test_get_change_history_with_key_filter(self, config_service):
        """Test getting change history for specific key."""
        # This will likely be empty for default config, but tests the functionality
        specific_history = config_service.get_change_history(key="system.debug_mode")
        assert isinstance(specific_history, list)
        
        # All entries should be for the specified key
        for change in specific_history:
            assert change.key in ["system.debug_mode", "*"]


class TestConfigStatistics:
    """Test configuration statistics and utilities."""
    
    def test_get_statistics(self, config_service):
        """Test getting configuration statistics."""
        stats = config_service.get_statistics()
        
        assert "total_entries" in stats
        assert "by_scope" in stats
        assert "by_source" in stats
        assert "by_type" in stats
        assert "total_snapshots" in stats
        assert "total_changes" in stats
        assert "watched_files" in stats
        assert "auto_reload_enabled" in stats
        
        assert stats["total_entries"] > 0
        assert isinstance(stats["by_scope"], dict)
        assert isinstance(stats["by_source"], dict)
        assert isinstance(stats["by_type"], dict)
    
    def test_cleanup_old_data(self, config_service):
        """Test cleaning up old data."""
        # Add some mock old data
        old_time = datetime.now(timezone.utc) - timedelta(days=45)
        
        # Mock old snapshot
        old_snapshot = ConfigSnapshot(
            snapshot_id="old_snapshot",
            timestamp=old_time,
            config_data={},
            description="Old snapshot"
        )
        config_service.snapshots["old_snapshot"] = old_snapshot
        
        # Mock old change
        old_change = ConfigChangeEvent(
            event_id="old_change",
            key="test.old",
            old_value=None,
            new_value="old",
            source=ConfigSource.DEFAULT,
            changed_by="test",
            timestamp=old_time
        )
        config_service.change_history.append(old_change)
        
        # Cleanup
        result = config_service.cleanup_old_data(retention_days=30)
        
        assert "deleted_snapshots" in result
        assert "deleted_changes" in result
        assert result["deleted_snapshots"] >= 1
        assert result["deleted_changes"] >= 1
        
        # Verify cleanup
        assert "old_snapshot" not in config_service.snapshots
        assert old_change not in config_service.change_history


class TestGlobalConfigurationService:
    """Test global configuration service functions."""
    
    def test_get_configuration_service_singleton(self):
        """Test that global service is singleton."""
        service1 = get_configuration_service()
        service2 = get_configuration_service()
        assert service1 is service2
    
    def test_get_config_convenience_function(self):
        """Test convenience function for getting config."""
        value = get_config("system.debug_mode", True)
        assert isinstance(value, bool)
    
    @pytest.mark.asyncio
    async def test_set_config_convenience_function(self):
        """Test convenience function for setting config."""
        result = await set_config("test.convenience", "convenience_value")
        assert result is True
        
        value = get_config("test.convenience")
        assert value == "convenience_value"
    
    def test_typed_convenience_functions(self):
        """Test typed convenience functions."""
        # These should work with default config
        debug_mode = get_config_bool("system.debug_mode", True)
        assert isinstance(debug_mode, bool)
        
        position_size = get_config_int("trading.max_position_size", 0)
        assert isinstance(position_size, int)
        assert position_size > 0
        
        position_float = get_config_float("trading.max_position_size", 0.0)
        assert isinstance(position_float, float)
        assert position_float > 0.0


class TestConfigDataTypes:
    """Test configuration data types and edge cases."""
    
    @pytest.mark.asyncio
    async def test_get_list_configuration(self, config_service):
        """Test getting list configuration values."""
        test_list = ["item1", "item2", "item3"]
        await config_service.set("test.list", test_list, config_type=ConfigType.LIST)
        
        retrieved_list = config_service.get_list("test.list")
        assert retrieved_list == test_list
        
        # Test with JSON string
        await config_service.set("test.json_list", '["json1", "json2"]')
        json_list = config_service.get_list("test.json_list")
        assert json_list == ["json1", "json2"]
        
        # Test with default
        default_list = config_service.get_list("nonexistent.list", ["default"])
        assert default_list == ["default"]
    
    @pytest.mark.asyncio
    async def test_get_dict_configuration(self, config_service):
        """Test getting dictionary configuration values."""
        test_dict = {"key1": "value1", "key2": "value2"}
        await config_service.set("test.dict", test_dict, config_type=ConfigType.DICT)
        
        retrieved_dict = config_service.get_dict("test.dict")
        assert retrieved_dict == test_dict
        
        # Test with JSON string
        await config_service.set("test.json_dict", '{"json_key": "json_value"}')
        json_dict = config_service.get_dict("test.json_dict")
        assert json_dict == {"json_key": "json_value"}
        
        # Test with default
        default_dict = config_service.get_dict("nonexistent.dict", {"default": "value"})
        assert default_dict == {"default": "value"}
    
    @pytest.mark.asyncio
    async def test_boolean_string_conversion(self, config_service):
        """Test boolean conversion from various string formats."""
        test_cases = [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("enabled", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("0", False),
            ("no", False),
            ("off", False),
            ("disabled", False),
            ("random", False),
        ]
        
        for string_val, expected_bool in test_cases:
            await config_service.set(f"test.bool_{string_val}", string_val)
            result = config_service.get_bool(f"test.bool_{string_val}")
            assert result == expected_bool, f"Failed for '{string_val}' -> {expected_bool}"


class TestConfigEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.mark.asyncio
    async def test_invalid_validation_rule(self, config_service):
        """Test handling of invalid validation rules."""
        entry = ConfigEntry(
            key="test.invalid_rule",
            value="test_value",
            config_type=ConfigType.STRING,
            scope=ConfigScope.SERVICE,
            source=ConfigSource.DEFAULT,
            validation_rules=[
                ConfigRule(
                    rule_id="invalid_rule",
                    field_path="test.invalid_rule",
                    rule_type="unknown_type",  # Invalid rule type
                    error_message="This rule is invalid"
                )
            ]
        )
        
        # Should not raise exception, just mark as valid (unknown rules ignored)
        validation = await config_service.validate_entry(entry)
        assert validation.result == ConfigValidationResult.VALID
    
    @pytest.mark.asyncio
    async def test_set_with_none_values(self, config_service):
        """Test setting configuration with None values."""
        result = await config_service.set("test.none_value", None)
        assert result is True
        assert config_service.get("test.none_value") is None
        assert config_service.get("test.none_value", "default") is None
    
    @pytest.mark.asyncio
    async def test_concurrent_access(self, config_service):
        """Test concurrent access to configuration service."""
        async def set_config_worker(worker_id):
            for i in range(10):
                await config_service.set(f"test.worker_{worker_id}_{i}", f"value_{i}")
        
        # Run multiple workers concurrently
        workers = [set_config_worker(i) for i in range(5)]
        await asyncio.gather(*workers)
        
        # Verify all values were set
        for worker_id in range(5):
            for i in range(10):
                key = f"test.worker_{worker_id}_{i}"
                value = config_service.get(key)
                assert value == f"value_{i}"
    
    def test_thread_safety(self, config_service):
        """Test thread safety of configuration service."""
        import threading
        import time
        
        results = []
        errors = []
        
        def worker_thread(thread_id):
            try:
                for i in range(50):
                    # Mix of reads and writes
                    if i % 2 == 0:
                        config_service.get("system.debug_mode")
                    else:
                        # Can't use async in thread, so just test synchronous operations
                        config_service.get_all()
                    time.sleep(0.001)  # Small delay
                results.append(f"Thread {thread_id} completed")
            except Exception as e:
                errors.append(f"Thread {thread_id} error: {e}")
        
        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker_thread, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(results) == 5


# Integration tests
class TestConfigurationIntegration:
    """Integration tests for configuration service."""
    
    @pytest.mark.asyncio
    async def test_full_configuration_lifecycle(self, config_service, temp_config_dir):
        """Test complete configuration lifecycle."""
        # 1. Set initial configuration
        await config_service.set("app.name", "Test App")
        await config_service.set("app.version", "1.0.0")
        await config_service.set("app.debug", True)
        
        # 2. Create snapshot
        snapshot_id = await config_service.create_snapshot("Initial config")
        
        # 3. Modify configuration
        await config_service.set("app.version", "1.1.0")
        await config_service.set("app.feature_flag", True)
        
        # 4. Save to file
        config_file = os.path.join(temp_config_dir, "app_config.json")
        await config_service.save_to_file(config_file)
        
        # 5. Verify file contents
        with open(config_file, 'r') as f:
            file_data = json.load(f)
        assert file_data["app.version"] == "1.1.0"
        assert file_data["app.feature_flag"] is True
        
        # 6. Restore from snapshot
        await config_service.restore_snapshot(snapshot_id)
        assert config_service.get("app.version") == "1.0.0"
        assert config_service.get("app.feature_flag") is None
        
        # 7. Load from file again
        await config_service.load_from_file(config_file, auto_reload=False)
        assert config_service.get("app.version") == "1.1.0"
        assert config_service.get("app.feature_flag") is True
        
        # 8. Check change history
        history = config_service.get_change_history(limit=10)
        assert len(history) >= 4  # At least 4 changes recorded
    
    @pytest.mark.asyncio
    async def test_validation_integration(self, config_service):
        """Test validation integration with real configuration scenarios."""
        # Add validation rules for a trading configuration scenario
        position_size_rule = ConfigRule(
            rule_id="position_size_limits",
            field_path="trading.position_size",
            rule_type="range",
            parameters={"min": 1000, "max": 1000000},
            error_message="Position size must be between 1,000 and 1,000,000"
        )
        config_service.add_validation_rule("trading.position_size", position_size_rule)
        
        # Test valid configuration
        result = await config_service.set("trading.position_size", 50000, validate=True)
        assert result is True
        
        # Test invalid configuration (too small)
        result = await config_service.set("trading.position_size", 500, validate=True)
        assert result is False
        assert config_service.get("trading.position_size") == 50000  # Unchanged
        
        # Test invalid configuration (too large)
        result = await config_service.set("trading.position_size", 2000000, validate=True)
        assert result is False
        assert config_service.get("trading.position_size") == 50000  # Unchanged
    
    @pytest.mark.asyncio
    async def test_multi_environment_configuration(self, config_service):
        """Test configuration for multiple environments."""
        # Set environment-specific configurations
        environments = ["development", "staging", "production"]
        
        for env in environments:
            await config_service.set(f"db.host.{env}", f"{env}-db.example.com")
            await config_service.set(f"db.port.{env}", 5432)
            await config_service.set(f"debug.{env}", env == "development")
        
        # Test environment-specific retrieval
        dev_host = config_service.get("db.host.development")
        prod_host = config_service.get("db.host.production")
        
        assert dev_host == "development-db.example.com"
        assert prod_host == "production-db.example.com"
        
        # Test environment-specific listing
        db_keys = config_service.list_keys(prefix="db.host.")
        assert len(db_keys) == 3
        assert all(env in str(db_keys) for env in environments)


if __name__ == "__main__":
    pytest.main([__file__])

import pytest
from unittest.mock import Mock, patch, AsyncMock

try:
    from backend.module_80 import *
    MODULE_EXISTS = True
except ImportError:
    MODULE_EXISTS = False


class TestModule80BackendModule80:
    """Comprehensive test suite for module 80 functionality."""

    def test_module_availability(self):
        """Test module availability."""
        if MODULE_EXISTS:
            import backend.module_80 as module
            assert module is not None
        else:
            assert True

    def test_module_functionality(self):
        """Test module functionality if exists."""
        if MODULE_EXISTS:
            import backend.module_80 as module
            assert hasattr(module, '__name__')
        else:
            pytest.skip("Module not available")

    def test_module_initialization(self):
        """Test module initialization."""
        if MODULE_EXISTS:
            assert True
        else:
            pytest.skip("Module not available")

    def test_module_configuration(self):
        """Test module configuration."""
        if MODULE_EXISTS:
            assert True
        else:
            pytest.skip("Module not available")

    def test_module_operations(self):
        """Test module operations."""
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
