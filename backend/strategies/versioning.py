"""
Strategy Versioning System (M-41)

Provides version tracking for strategies, enabling:
- Snapshot creation of strategy configurations
- Version comparison and rollback
- Change history tracking
- Parameter evolution analysis

Follows the existing project patterns with async/await and proper logging.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4
import hashlib
import json
import logging
import os

logger = logging.getLogger(__name__)


class VersionChangeType(Enum):
    """Types of changes that trigger versioning."""
    PARAMETERS_CHANGED = "parameters_changed"
    SYMBOLS_CHANGED = "symbols_changed"
    RISK_LIMITS_CHANGED = "risk_limits_changed"
    STATUS_CHANGED = "status_changed"
    MODEL_CHANGED = "model_changed"
    MANUAL_SNAPSHOT = "manual_snapshot"


@dataclass
class StrategyVersion:
    """Represents a versioned snapshot of a strategy configuration."""
    version_id: str
    strategy_id: str
    version_number: int
    created_at: datetime
    change_type: VersionChangeType
    change_description: str
    
    # Snapshot of configuration at this version
    name: str
    strategy_type: str
    symbols: list[str]
    parameters: dict[str, Any]
    risk_limits: dict[str, Any] = field(default_factory=dict)
    
    # Performance at time of snapshot
    performance_snapshot: dict[str, Any] = field(default_factory=dict)
    
    # Optional metadata
    created_by: str | None = None
    parent_version_id: str | None = None
    config_hash: str = ""
    
    def __post_init__(self):
        """Calculate config hash if not provided."""
        if not self.config_hash:
            self.config_hash = self._calculate_hash()
    
    def _calculate_hash(self) -> str:
        """Calculate a hash of the configuration for change detection."""
        config = {
            "name": self.name,
            "strategy_type": self.strategy_type,
            "symbols": sorted(self.symbols),
            "parameters": self.parameters,
            "risk_limits": self.risk_limits,
        }
        config_json = json.dumps(config, sort_keys=True, default=str)
        return hashlib.sha256(config_json.encode()).hexdigest()[:16]


@dataclass
class VersionComparison:
    """Result of comparing two strategy versions."""
    version_a: str
    version_b: str
    
    parameters_changed: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    symbols_added: list[str] = field(default_factory=list)
    symbols_removed: list[str] = field(default_factory=list)
    risk_limits_changed: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    
    performance_delta: dict[str, float] = field(default_factory=dict)
    
    @property
    def has_changes(self) -> bool:
        """Check if there are any differences."""
        return bool(
            self.parameters_changed or
            self.symbols_added or
            self.symbols_removed or
            self.risk_limits_changed
        )


class StrategyVersionManager:
    """
    Manages strategy version history and snapshots.
    
    Provides functionality to:
    - Create version snapshots when strategies change
    - Compare versions to identify differences
    - Rollback to previous versions
    - Track version lineage
    
    Usage:
        manager = StrategyVersionManager()
        
        # Create initial version
        version = manager.create_version(strategy_dict, VersionChangeType.MANUAL_SNAPSHOT)
        
        # Compare versions
        diff = manager.compare_versions(version_a, version_b)
        
        # Get version history
        history = manager.get_version_history(strategy_id)
    """
    
    def __init__(self):
        """Initialize version manager with in-memory storage.

        WARNING: All data is lost on restart.  For production deployments,
        back this with a persistent store (database or Redis).
        """
        import warnings
        app_env = os.getenv("APP_ENVIRONMENT", "development").lower()
        emit_warning = os.getenv("BACKEND_EMIT_RUNTIME_WARNINGS", "0") == "1"
        if emit_warning or app_env not in {"testing", "test"}:
            warnings.warn(
                "StrategyVersionManager uses in-memory storage — versions will be lost on restart. "
                "Wire to database before production deployment.",
                RuntimeWarning,
                stacklevel=2,
            )
        self._versions: dict[str, StrategyVersion] = {}  # version_id -> version
        self._strategy_versions: dict[str, list[str]] = {}  # strategy_id -> [version_ids]
        self._latest_version: dict[str, str] = {}  # strategy_id -> latest_version_id
    
    def create_version(
        self,
        strategy: dict[str, Any],
        change_type: VersionChangeType,
        change_description: str = "",
        created_by: str | None = None,
        performance_snapshot: dict[str, Any] | None = None,
    ) -> StrategyVersion:
        """
        Create a new version snapshot of a strategy.
        
        Args:
            strategy: Strategy dictionary with current configuration
            change_type: Type of change triggering this version
            change_description: Human-readable description of the change
            created_by: User/system that created this version
            performance_snapshot: Optional current performance metrics
            
        Returns:
            StrategyVersion object representing the new snapshot
        """
        strategy_id = str(strategy.get("id", ""))
        if not strategy_id:
            raise ValueError("Strategy must have an 'id' field")
        
        # Get next version number
        current_versions = self._strategy_versions.get(strategy_id, [])
        version_number = len(current_versions) + 1
        
        # Get parent version
        parent_version_id = self._latest_version.get(strategy_id)
        
        # Extract risk limits from parameters or separate field
        risk_limits = strategy.get("risk_limits", {})
        if not risk_limits:
            # Extract from parameters if nested there
            params = strategy.get("parameters", {})
            risk_limits = {
                "max_position_size": params.get("max_position_size", strategy.get("max_position_size")),
                "max_daily_loss": params.get("max_daily_loss", strategy.get("max_daily_loss")),
                "max_drawdown_pct": params.get("max_drawdown_pct", strategy.get("max_drawdown_pct")),
            }
            risk_limits = {k: v for k, v in risk_limits.items() if v is not None}
        
        # Create version
        version = StrategyVersion(
            version_id=str(uuid4()),
            strategy_id=strategy_id,
            version_number=version_number,
            created_at=datetime.now(UTC),
            change_type=change_type,
            change_description=change_description or f"Version {version_number}",
            name=strategy.get("name", ""),
            strategy_type=strategy.get("strategy_type", ""),
            symbols=strategy.get("symbols", []),
            parameters=strategy.get("parameters", {}),
            risk_limits=risk_limits,
            performance_snapshot=performance_snapshot or {
                "total_pnl": strategy.get("total_pnl", 0.0),
                "total_trades": strategy.get("total_trades", 0),
                "win_rate": strategy.get("win_rate", 0.0),
            },
            created_by=created_by,
            parent_version_id=parent_version_id,
        )
        
        # Store version
        self._versions[version.version_id] = version
        
        if strategy_id not in self._strategy_versions:
            self._strategy_versions[strategy_id] = []
        self._strategy_versions[strategy_id].append(version.version_id)
        self._latest_version[strategy_id] = version.version_id
        
        logger.info(
            "Strategy version created",
            extra={
                "strategy_id": strategy_id,
                "version_id": version.version_id,
                "version_number": version_number,
                "change_type": change_type.value,
            }
        )
        
        return version
    
    def get_version(self, version_id: str) -> StrategyVersion | None:
        """Get a specific version by ID."""
        return self._versions.get(version_id)
    
    def get_latest_version(self, strategy_id: str) -> StrategyVersion | None:
        """Get the latest version for a strategy."""
        latest_id = self._latest_version.get(strategy_id)
        if latest_id:
            return self._versions.get(latest_id)
        return None
    
    def get_version_history(
        self,
        strategy_id: str,
        limit: int | None = None,
    ) -> list[StrategyVersion]:
        """
        Get version history for a strategy, newest first.
        
        Args:
            strategy_id: Strategy to get history for
            limit: Optional limit on number of versions
            
        Returns:
            List of StrategyVersion objects, newest first
        """
        version_ids = self._strategy_versions.get(strategy_id, [])
        versions = [self._versions[vid] for vid in reversed(version_ids)]
        
        if limit:
            versions = versions[:limit]
        
        return versions
    
    def compare_versions(
        self,
        version_a_id: str,
        version_b_id: str,
    ) -> VersionComparison:
        """
        Compare two versions to identify differences.
        
        Args:
            version_a_id: First version ID (typically older)
            version_b_id: Second version ID (typically newer)
            
        Returns:
            VersionComparison detailing the differences
        """
        version_a = self._versions.get(version_a_id)
        version_b = self._versions.get(version_b_id)
        
        if not version_a or not version_b:
            raise ValueError("One or both versions not found")
        
        comparison = VersionComparison(
            version_a=version_a_id,
            version_b=version_b_id,
        )
        
        # Compare parameters
        all_params = set(version_a.parameters.keys()) | set(version_b.parameters.keys())
        for param in all_params:
            val_a = version_a.parameters.get(param)
            val_b = version_b.parameters.get(param)
            if val_a != val_b:
                comparison.parameters_changed[param] = (val_a, val_b)
        
        # Compare symbols
        symbols_a = set(version_a.symbols)
        symbols_b = set(version_b.symbols)
        comparison.symbols_added = list(symbols_b - symbols_a)
        comparison.symbols_removed = list(symbols_a - symbols_b)
        
        # Compare risk limits
        all_limits = set(version_a.risk_limits.keys()) | set(version_b.risk_limits.keys())
        for limit in all_limits:
            val_a = version_a.risk_limits.get(limit)
            val_b = version_b.risk_limits.get(limit)
            if val_a != val_b:
                comparison.risk_limits_changed[limit] = (val_a, val_b)
        
        # Calculate performance delta
        for metric in ["total_pnl", "total_trades", "win_rate"]:
            val_a = version_a.performance_snapshot.get(metric, 0) or 0
            val_b = version_b.performance_snapshot.get(metric, 0) or 0
            try:
                comparison.performance_delta[metric] = float(val_b) - float(val_a)
            except (TypeError, ValueError):
                comparison.performance_delta[metric] = 0.0
        
        logger.debug(
            "Version comparison completed",
            extra={
                "version_a": version_a_id,
                "version_b": version_b_id,
                "has_changes": comparison.has_changes,
            }
        )
        
        return comparison
    
    def get_rollback_config(self, version_id: str) -> dict[str, Any]:
        """
        Get configuration from a version for rollback purposes.
        
        Args:
            version_id: Version to extract configuration from
            
        Returns:
            Dictionary suitable for updating a strategy
        """
        version = self._versions.get(version_id)
        if not version:
            raise ValueError(f"Version {version_id} not found")
        
        return {
            "name": version.name,
            "strategy_type": version.strategy_type,
            "symbols": version.symbols,
            "parameters": version.parameters,
            "max_position_size": version.risk_limits.get("max_position_size"),
            "max_daily_loss": version.risk_limits.get("max_daily_loss"),
            "max_drawdown_pct": version.risk_limits.get("max_drawdown_pct"),
        }
    
    def should_create_version(
        self,
        strategy_id: str,
        new_config: dict[str, Any],
    ) -> tuple[bool, VersionChangeType | None]:
        """
        Determine if a config change warrants a new version.
        
        Args:
            strategy_id: Strategy being updated
            new_config: New configuration to compare
            
        Returns:
            Tuple of (should_create, change_type)
        """
        latest = self.get_latest_version(strategy_id)
        if not latest:
            return True, VersionChangeType.MANUAL_SNAPSHOT
        
        # Check for parameter changes
        new_params = new_config.get("parameters", {})
        if new_params != latest.parameters:
            return True, VersionChangeType.PARAMETERS_CHANGED
        
        # Check for symbol changes
        new_symbols = set(new_config.get("symbols", []))
        if new_symbols != set(latest.symbols):
            return True, VersionChangeType.SYMBOLS_CHANGED
        
        # Check for risk limit changes
        for limit in ["max_position_size", "max_daily_loss", "max_drawdown_pct"]:
            if new_config.get(limit) != latest.risk_limits.get(limit):
                return True, VersionChangeType.RISK_LIMITS_CHANGED
        
        return False, None
    
    def to_dict(self, version: StrategyVersion) -> dict[str, Any]:
        """Convert a StrategyVersion to a dictionary."""
        return {
            "version_id": version.version_id,
            "strategy_id": version.strategy_id,
            "version_number": version.version_number,
            "created_at": version.created_at.isoformat(),
            "change_type": version.change_type.value,
            "change_description": version.change_description,
            "name": version.name,
            "strategy_type": version.strategy_type,
            "symbols": version.symbols,
            "parameters": version.parameters,
            "risk_limits": version.risk_limits,
            "performance_snapshot": version.performance_snapshot,
            "created_by": version.created_by,
            "parent_version_id": version.parent_version_id,
            "config_hash": version.config_hash,
        }


# Singleton instance for service use
_version_manager: StrategyVersionManager | None = None


def get_version_manager() -> StrategyVersionManager:
    """Get or create the strategy version manager singleton."""
    global _version_manager
    if _version_manager is None:
        _version_manager = StrategyVersionManager()
    return _version_manager
