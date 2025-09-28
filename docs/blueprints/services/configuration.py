"""
Module 80: Configuration Service
Dynamic configuration management with hot-reloading, validation, and versioning.
"""

import asyncio
import json
import yaml
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Union, Set, Callable, Type
from enum import Enum
from pathlib import Path
import logging
import uuid
import hashlib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import copy

# Configure logging
logger = logging.getLogger(__name__)


class ConfigType(Enum):
    """Configuration value types."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"
    JSON = "json"


class ConfigScope(Enum):
    """Configuration scope levels."""
    GLOBAL = "global"
    SERVICE = "service"
    USER = "user"
    SESSION = "session"
    ENVIRONMENT = "environment"


class ConfigSource(Enum):
    """Configuration sources."""
    FILE = "file"
    DATABASE = "database"
    ENVIRONMENT = "environment"
    REMOTE = "remote"
    DEFAULT = "default"
    OVERRIDE = "override"


class ConfigValidationResult(Enum):
    """Configuration validation results."""
    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"


@dataclass
class ConfigRule:
    """Configuration validation rule."""
    rule_id: str
    field_path: str
    rule_type: str  # required, type, range, pattern, custom
    parameters: Dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    severity: str = "error"  # error, warning, info


@dataclass
class ConfigValidation:
    """Configuration validation result."""
    result: ConfigValidationResult
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    field_results: Dict[str, ConfigValidationResult] = field(default_factory=dict)


@dataclass
class ConfigEntry:
    """Single configuration entry."""
    key: str
    value: Any
    config_type: ConfigType
    scope: ConfigScope
    source: ConfigSource
    description: str = ""
    default_value: Any = None
    is_secret: bool = False
    is_readonly: bool = False
    validation_rules: List[ConfigRule] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1


@dataclass
class ConfigSnapshot:
    """Configuration snapshot for versioning."""
    snapshot_id: str
    timestamp: datetime
    config_data: Dict[str, Any]
    description: str = ""
    created_by: str = ""


@dataclass
class ConfigChangeEvent:
    """Configuration change event."""
    event_id: str
    key: str
    old_value: Any
    new_value: Any
    source: ConfigSource
    changed_by: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = ""


class ConfigWatcher(FileSystemEventHandler):
    """File system watcher for configuration files."""
    
    def __init__(self, config_service: 'ConfigurationService', watched_files: Set[str]):
        super().__init__()
        self.config_service = config_service
        self.watched_files = watched_files
        self.last_modified = {}
    
    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return
        
        file_path = os.path.normpath(event.src_path)
        if file_path in self.watched_files:
            # Debounce rapid file changes
            current_time = time.time()
            if file_path in self.last_modified:
                if current_time - self.last_modified[file_path] < 1.0:  # 1 second debounce
                    return
            
            self.last_modified[file_path] = current_time
            
            # Trigger configuration reload
            asyncio.create_task(self.config_service._reload_file(file_path))


class ConfigurationService:
    """Comprehensive configuration management service."""
    
    def __init__(self, config_dir: str = "config", auto_reload: bool = True):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        
        self.entries: Dict[str, ConfigEntry] = {}
        self.snapshots: Dict[str, ConfigSnapshot] = {}
        self.change_history: List[ConfigChangeEvent] = []
        self.validation_rules: Dict[str, List[ConfigRule]] = {}
        self.change_callbacks: Dict[str, List[Callable]] = {}
        
        # File watching
        self.auto_reload = auto_reload
        self.watched_files: Set[str] = set()
        self.observer: Optional[Observer] = None
        self.watcher: Optional[ConfigWatcher] = None
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Load default configuration
        self._load_default_config()
        
        if auto_reload:
            self._start_file_watcher()
    
    def _load_default_config(self):
        """Load default configuration entries."""
        default_configs = [
            ConfigEntry(
                key="system.debug_mode",
                value=False,
                config_type=ConfigType.BOOLEAN,
                scope=ConfigScope.GLOBAL,
                source=ConfigSource.DEFAULT,
                description="Enable debug mode for the system",
                default_value=False
            ),
            ConfigEntry(
                key="system.log_level",
                value="INFO",
                config_type=ConfigType.STRING,
                scope=ConfigScope.GLOBAL,
                source=ConfigSource.DEFAULT,
                description="System logging level",
                default_value="INFO",
                validation_rules=[
                    ConfigRule(
                        rule_id="log_level_values",
                        field_path="system.log_level",
                        rule_type="pattern",
                        parameters={"pattern": "^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"},
                        error_message="Log level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL"
                    )
                ]
            ),
            ConfigEntry(
                key="trading.max_position_size",
                value=1000000,
                config_type=ConfigType.INTEGER,
                scope=ConfigScope.SERVICE,
                source=ConfigSource.DEFAULT,
                description="Maximum position size for trading",
                default_value=1000000,
                validation_rules=[
                    ConfigRule(
                        rule_id="position_size_range",
                        field_path="trading.max_position_size",
                        rule_type="range",
                        parameters={"min": 1000, "max": 10000000},
                        error_message="Position size must be between 1,000 and 10,000,000"
                    )
                ]
            ),
            ConfigEntry(
                key="api.rate_limit",
                value=1000,
                config_type=ConfigType.INTEGER,
                scope=ConfigScope.SERVICE,
                source=ConfigSource.DEFAULT,
                description="API rate limit per minute",
                default_value=1000,
                validation_rules=[
                    ConfigRule(
                        rule_id="rate_limit_min",
                        field_path="api.rate_limit",
                        rule_type="range",
                        parameters={"min": 1},
                        error_message="Rate limit must be at least 1"
                    )
                ]
            ),
            ConfigEntry(
                key="database.connection_timeout",
                value=30,
                config_type=ConfigType.INTEGER,
                scope=ConfigScope.SERVICE,
                source=ConfigSource.DEFAULT,
                description="Database connection timeout in seconds",
                default_value=30
            )
        ]
        
        with self._lock:
            for config in default_configs:
                self.entries[config.key] = config
                # Copy validation rules to global validation rules
                if config.validation_rules:
                    if config.key not in self.validation_rules:
                        self.validation_rules[config.key] = []
                    self.validation_rules[config.key].extend(config.validation_rules)
    
    def _start_file_watcher(self):
        """Start file system watcher for configuration files."""
        if self.observer is None:
            self.watcher = ConfigWatcher(self, self.watched_files)
            self.observer = Observer()
            self.observer.schedule(self.watcher, str(self.config_dir), recursive=True)
            self.observer.start()
    
    def _stop_file_watcher(self):
        """Stop file system watcher."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            self.watcher = None
    
    async def _reload_file(self, file_path: str):
        """Reload configuration from a specific file."""
        try:
            logger.info(f"Reloading configuration from {file_path}")
            await self.load_from_file(file_path, auto_reload=False)
        except Exception as e:
            logger.error(f"Failed to reload configuration from {file_path}: {e}")
    
    def get(self, key: str, default: Any = None, scope: Optional[ConfigScope] = None) -> Any:
        """Get configuration value."""
        with self._lock:
            if key in self.entries:
                entry = self.entries[key]
                if scope is None or entry.scope == scope:
                    return entry.value
            
            return default
    
    def get_int(self, key: str, default: int = 0) -> int:
        """Get configuration value as integer."""
        value = self.get(key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get configuration value as float."""
        value = self.get(key, default)
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get configuration value as boolean."""
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on', 'enabled')
        return bool(value)
    
    def get_list(self, key: str, default: List[Any] = None) -> List[Any]:
        """Get configuration value as list."""
        value = self.get(key, default or [])
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return default or []
        return default or []
    
    def get_dict(self, key: str, default: Dict[str, Any] = None) -> Dict[str, Any]:
        """Get configuration value as dictionary."""
        value = self.get(key, default or {})
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return default or {}
        return default or {}
    
    async def set(
        self,
        key: str,
        value: Any,
        config_type: Optional[ConfigType] = None,
        scope: ConfigScope = ConfigScope.SERVICE,
        source: ConfigSource = ConfigSource.OVERRIDE,
        description: str = "",
        changed_by: str = "system",
        validate: bool = True
    ) -> bool:
        """Set configuration value."""
        try:
            # Auto-detect type if not provided
            if config_type is None:
                config_type = self._detect_type(value)
            
            # Create or update entry
            old_value = None
            if key in self.entries:
                old_value = self.entries[key].value
            
            entry = ConfigEntry(
                key=key,
                value=value,
                config_type=config_type,
                scope=scope,
                source=source,
                description=description
            )
            
            # Validate if requested
            if validate:
                validation = await self.validate_entry(entry)
                if validation.result == ConfigValidationResult.INVALID:
                    logger.error(f"Configuration validation failed for {key}: {validation.errors}")
                    return False
            
            with self._lock:
                # Update entry
                if key in self.entries:
                    entry.version = self.entries[key].version + 1
                
                self.entries[key] = entry
                
                # Record change
                change_event = ConfigChangeEvent(
                    event_id=str(uuid.uuid4()),
                    key=key,
                    old_value=old_value,
                    new_value=value,
                    source=source,
                    changed_by=changed_by
                )
                self.change_history.append(change_event)
            
            # Trigger callbacks
            await self._trigger_change_callbacks(key, old_value, value)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to set configuration {key}: {e}")
            return False
    
    def _detect_type(self, value: Any) -> ConfigType:
        """Auto-detect configuration type from value."""
        if isinstance(value, bool):
            return ConfigType.BOOLEAN
        elif isinstance(value, int):
            return ConfigType.INTEGER
        elif isinstance(value, float):
            return ConfigType.FLOAT
        elif isinstance(value, list):
            return ConfigType.LIST
        elif isinstance(value, dict):
            return ConfigType.DICT
        else:
            return ConfigType.STRING
    
    async def delete(self, key: str, changed_by: str = "system") -> bool:
        """Delete configuration entry."""
        try:
            with self._lock:
                if key not in self.entries:
                    return False
                
                entry = self.entries[key]
                if entry.is_readonly:
                    logger.warning(f"Cannot delete readonly configuration: {key}")
                    return False
                
                old_value = entry.value
                del self.entries[key]
                
                # Record change
                change_event = ConfigChangeEvent(
                    event_id=str(uuid.uuid4()),
                    key=key,
                    old_value=old_value,
                    new_value=None,
                    source=ConfigSource.OVERRIDE,
                    changed_by=changed_by,
                    description="Configuration deleted"
                )
                self.change_history.append(change_event)
            
            # Trigger callbacks
            await self._trigger_change_callbacks(key, old_value, None)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete configuration {key}: {e}")
            return False
    
    def list_keys(
        self,
        prefix: str = "",
        scope: Optional[ConfigScope] = None,
        source: Optional[ConfigSource] = None
    ) -> List[str]:
        """List configuration keys with optional filtering."""
        with self._lock:
            keys = []
            for key, entry in self.entries.items():
                if prefix and not key.startswith(prefix):
                    continue
                if scope is not None and entry.scope != scope:
                    continue
                if source is not None and entry.source != source:
                    continue
                keys.append(key)
            
            return sorted(keys)
    
    def get_entry(self, key: str) -> Optional[ConfigEntry]:
        """Get full configuration entry."""
        with self._lock:
            return copy.deepcopy(self.entries.get(key))
    
    def get_all(
        self,
        prefix: str = "",
        scope: Optional[ConfigScope] = None,
        include_secrets: bool = False
    ) -> Dict[str, Any]:
        """Get all configuration values as dictionary."""
        with self._lock:
            result = {}
            for key, entry in self.entries.items():
                if prefix and not key.startswith(prefix):
                    continue
                if scope is not None and entry.scope != scope:
                    continue
                if entry.is_secret and not include_secrets:
                    continue
                
                result[key] = entry.value
            
            return result
    
    async def validate_entry(self, entry: ConfigEntry) -> ConfigValidation:
        """Validate a single configuration entry."""
        validation = ConfigValidation(result=ConfigValidationResult.VALID)
        
        try:
            # Check validation rules
            for rule in entry.validation_rules:
                rule_result = await self._apply_validation_rule(entry, rule)
                if rule_result == ConfigValidationResult.INVALID:
                    validation.result = ConfigValidationResult.INVALID
                    validation.errors.append(rule.error_message or f"Validation failed for rule {rule.rule_id}")
                elif rule_result == ConfigValidationResult.WARNING:
                    if validation.result == ConfigValidationResult.VALID:
                        validation.result = ConfigValidationResult.WARNING
                    validation.warnings.append(rule.error_message or f"Validation warning for rule {rule.rule_id}")
                
                validation.field_results[rule.field_path] = rule_result
            
            # Check global rules
            if entry.key in self.validation_rules:
                for rule in self.validation_rules[entry.key]:
                    rule_result = await self._apply_validation_rule(entry, rule)
                    if rule_result == ConfigValidationResult.INVALID:
                        validation.result = ConfigValidationResult.INVALID
                        validation.errors.append(rule.error_message)
                    elif rule_result == ConfigValidationResult.WARNING:
                        if validation.result == ConfigValidationResult.VALID:
                            validation.result = ConfigValidationResult.WARNING
                        validation.warnings.append(rule.error_message)
        
        except Exception as e:
            validation.result = ConfigValidationResult.INVALID
            validation.errors.append(f"Validation error: {str(e)}")
        
        return validation
    
    async def _apply_validation_rule(self, entry: ConfigEntry, rule: ConfigRule) -> ConfigValidationResult:
        """Apply a single validation rule."""
        try:
            if rule.rule_type == "required":
                if entry.value is None or entry.value == "":
                    return ConfigValidationResult.INVALID
            
            elif rule.rule_type == "type":
                expected_type = rule.parameters.get("type")
                if expected_type == "int" and not isinstance(entry.value, int):
                    return ConfigValidationResult.INVALID
                elif expected_type == "float" and not isinstance(entry.value, (int, float)):
                    return ConfigValidationResult.INVALID
                elif expected_type == "bool" and not isinstance(entry.value, bool):
                    return ConfigValidationResult.INVALID
                elif expected_type == "str" and not isinstance(entry.value, str):
                    return ConfigValidationResult.INVALID
            
            elif rule.rule_type == "range":
                min_val = rule.parameters.get("min")
                max_val = rule.parameters.get("max")
                
                if min_val is not None and entry.value < min_val:
                    return ConfigValidationResult.INVALID
                if max_val is not None and entry.value > max_val:
                    return ConfigValidationResult.INVALID
            
            elif rule.rule_type == "pattern":
                import re
                pattern = rule.parameters.get("pattern")
                if pattern and isinstance(entry.value, str):
                    if not re.match(pattern, entry.value):
                        return ConfigValidationResult.INVALID
            
            elif rule.rule_type == "custom":
                # Custom validation function
                validator = rule.parameters.get("validator")
                if validator and callable(validator):
                    result = validator(entry.value)
                    if not result:
                        return ConfigValidationResult.INVALID
            
            return ConfigValidationResult.VALID
            
        except Exception as e:
            logger.error(f"Error applying validation rule {rule.rule_id}: {e}")
            return ConfigValidationResult.INVALID
    
    async def validate_all(self) -> Dict[str, ConfigValidation]:
        """Validate all configuration entries."""
        results = {}
        
        with self._lock:
            entries = list(self.entries.values())
        
        for entry in entries:
            results[entry.key] = await self.validate_entry(entry)
        
        return results
    
    def add_validation_rule(self, key: str, rule: ConfigRule):
        """Add a validation rule for a configuration key."""
        if key not in self.validation_rules:
            self.validation_rules[key] = []
        self.validation_rules[key].append(rule)
    
    def register_change_callback(self, key: str, callback: Callable[[str, Any, Any], None]):
        """Register a callback for configuration changes."""
        if key not in self.change_callbacks:
            self.change_callbacks[key] = []
        self.change_callbacks[key].append(callback)
    
    async def _trigger_change_callbacks(self, key: str, old_value: Any, new_value: Any):
        """Trigger registered change callbacks."""
        callbacks = []
        
        # Exact key match
        if key in self.change_callbacks:
            callbacks.extend(self.change_callbacks[key])
        
        # Wildcard patterns
        for pattern, pattern_callbacks in self.change_callbacks.items():
            if '*' in pattern:
                import fnmatch
                if fnmatch.fnmatch(key, pattern):
                    callbacks.extend(pattern_callbacks)
        
        # Execute callbacks
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(key, old_value, new_value)
                else:
                    callback(key, old_value, new_value)
            except Exception as e:
                logger.error(f"Error in configuration change callback: {e}")
    
    async def create_snapshot(self, description: str = "", created_by: str = "system") -> str:
        """Create a configuration snapshot."""
        snapshot_id = str(uuid.uuid4())
        
        with self._lock:
            config_data = {}
            for key, entry in self.entries.items():
                config_data[key] = {
                    'value': entry.value,
                    'type': entry.config_type.value,
                    'scope': entry.scope.value,
                    'source': entry.source.value,
                    'version': entry.version
                }
            
            snapshot = ConfigSnapshot(
                snapshot_id=snapshot_id,
                timestamp=datetime.now(timezone.utc),
                config_data=config_data,
                description=description,
                created_by=created_by
            )
            
            self.snapshots[snapshot_id] = snapshot
        
        return snapshot_id
    
    async def restore_snapshot(self, snapshot_id: str, changed_by: str = "system") -> bool:
        """Restore configuration from snapshot."""
        try:
            if snapshot_id not in self.snapshots:
                logger.error(f"Snapshot {snapshot_id} not found")
                return False
            
            snapshot = self.snapshots[snapshot_id]
            
            with self._lock:
                # Clear current configuration
                self.entries.clear()
                
                # Restore from snapshot
                for key, config_data in snapshot.config_data.items():
                    entry = ConfigEntry(
                        key=key,
                        value=config_data['value'],
                        config_type=ConfigType(config_data['type']),
                        scope=ConfigScope(config_data['scope']),
                        source=ConfigSource(config_data['source']),
                        version=config_data['version']
                    )
                    self.entries[key] = entry
                
                # Record change
                change_event = ConfigChangeEvent(
                    event_id=str(uuid.uuid4()),
                    key="*",
                    old_value="<full_config>",
                    new_value=f"<restored_from_snapshot_{snapshot_id}>",
                    source=ConfigSource.OVERRIDE,
                    changed_by=changed_by,
                    description=f"Restored from snapshot: {snapshot.description}"
                )
                self.change_history.append(change_event)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore snapshot {snapshot_id}: {e}")
            return False
    
    async def load_from_file(self, file_path: str, auto_reload: bool = True) -> bool:
        """Load configuration from file."""
        try:
            file_path = str(Path(file_path).resolve())
            
            if not os.path.exists(file_path):
                logger.error(f"Configuration file not found: {file_path}")
                return False
            
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                if file_path.endswith('.json'):
                    data = json.load(f)
                elif file_path.endswith(('.yml', '.yaml')):
                    data = yaml.safe_load(f)
                else:
                    # Try JSON first, then YAML
                    content = f.read()
                    try:
                        data = json.loads(content)
                    except json.JSONDecodeError:
                        data = yaml.safe_load(content)
            
            # Load configuration entries
            if isinstance(data, dict):
                for key, value in data.items():
                    await self.set(
                        key=key,
                        value=value,
                        source=ConfigSource.FILE,
                        changed_by="file_loader"
                    )
            
            # Add to watched files for auto-reload
            if auto_reload and self.auto_reload:
                self.watched_files.add(file_path)
            
            logger.info(f"Loaded configuration from {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load configuration from {file_path}: {e}")
            return False
    
    async def save_to_file(self, file_path: str, scope: Optional[ConfigScope] = None) -> bool:
        """Save configuration to file."""
        try:
            config_data = self.get_all(scope=scope, include_secrets=False)
            
            file_path = Path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                if file_path.suffix == '.json':
                    json.dump(config_data, f, indent=2, default=str)
                else:
                    yaml.dump(config_data, f, default_flow_style=False)
            
            logger.info(f"Saved configuration to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save configuration to {file_path}: {e}")
            return False
    
    def get_change_history(
        self,
        key: Optional[str] = None,
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[ConfigChangeEvent]:
        """Get configuration change history."""
        with self._lock:
            changes = list(self.change_history)
        
        # Apply filters
        if key:
            changes = [c for c in changes if c.key == key or c.key == "*"]
        if start_time:
            changes = [c for c in changes if c.timestamp >= start_time]
        if end_time:
            changes = [c for c in changes if c.timestamp <= end_time]
        
        # Sort by timestamp (newest first) and limit
        changes.sort(key=lambda c: c.timestamp, reverse=True)
        return changes[:limit]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get configuration service statistics."""
        with self._lock:
            total_entries = len(self.entries)
            by_scope = {}
            by_source = {}
            by_type = {}
            
            for entry in self.entries.values():
                # By scope
                scope = entry.scope.value
                by_scope[scope] = by_scope.get(scope, 0) + 1
                
                # By source
                source = entry.source.value
                by_source[source] = by_source.get(source, 0) + 1
                
                # By type
                config_type = entry.config_type.value
                by_type[config_type] = by_type.get(config_type, 0) + 1
            
            return {
                "total_entries": total_entries,
                "by_scope": by_scope,
                "by_source": by_source,
                "by_type": by_type,
                "total_snapshots": len(self.snapshots),
                "total_changes": len(self.change_history),
                "watched_files": len(self.watched_files),
                "auto_reload_enabled": self.auto_reload
            }
    
    def cleanup_old_data(self, retention_days: int = 30) -> Dict[str, int]:
        """Clean up old snapshots and change history."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=retention_days)
        
        with self._lock:
            # Clean old snapshots
            old_snapshots = [
                sid for sid, snapshot in self.snapshots.items()
                if snapshot.timestamp < cutoff_time
            ]
            for sid in old_snapshots:
                del self.snapshots[sid]
            
            # Clean old change history
            old_changes = [
                change for change in self.change_history
                if change.timestamp < cutoff_time
            ]
            for change in old_changes:
                self.change_history.remove(change)
        
        return {
            "deleted_snapshots": len(old_snapshots),
            "deleted_changes": len(old_changes)
        }
    
    def __del__(self):
        """Cleanup when service is destroyed."""
        self._stop_file_watcher()


# Global configuration service instance
_config_service: Optional[ConfigurationService] = None


def get_configuration_service() -> ConfigurationService:
    """Get the global configuration service instance."""
    global _config_service
    if _config_service is None:
        _config_service = ConfigurationService()
    return _config_service


# Convenience functions
def get_config(key: str, default: Any = None) -> Any:
    """Convenience function to get configuration value."""
    service = get_configuration_service()
    return service.get(key, default)


async def set_config(key: str, value: Any, **kwargs) -> bool:
    """Convenience function to set configuration value."""
    service = get_configuration_service()
    return await service.set(key, value, **kwargs)


def get_config_int(key: str, default: int = 0) -> int:
    """Convenience function to get configuration as integer."""
    service = get_configuration_service()
    return service.get_int(key, default)


def get_config_bool(key: str, default: bool = False) -> bool:
    """Convenience function to get configuration as boolean."""
    service = get_configuration_service()
    return service.get_bool(key, default)


def get_config_float(key: str, default: float = 0.0) -> float:
    """Convenience function to get configuration as float."""
    service = get_configuration_service()
    return service.get_float(key, default)


# Exception classes
class ConfigurationError(Exception):
    """Base configuration service exception."""
    pass


class ConfigValidationError(ConfigurationError):
    """Configuration validation exception."""
    pass


class ConfigLoadError(ConfigurationError):
    """Configuration loading exception."""
    pass