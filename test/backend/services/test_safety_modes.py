#!/usr/bin/env python3
"""
Module 113: Backend Services Safety Modes Test
Comprehensive test suite for backend.services.safety_modes module to achieve 100% coverage.

Test Target: backend/services/safety_modes.py
Focus: Trading safety modes, feature flags, kill switches, risk management
"""

import pytest
import asyncio
import sys
import os
from datetime import datetime, time, UTC, timedelta
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from typing import Any, Dict

# Add project root to Python path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

try:
    from backend.services.safety_modes import (
        SafetyMode, RiskLevel, TradingSafety, TradingMode, FeatureFlagScope,
        KillSwitchScope, FeatureFlag, KillSwitch, TradingModeConfig,
        TradeExecutionResult, SafetyModeManager
    )
    SAFETY_MODES_MODULE_EXISTS = True
except ImportError as e:
    SAFETY_MODES_MODULE_EXISTS = False
    IMPORT_ERROR = str(e)


class TestModule113BackendServicesSafetyModes:
    """Comprehensive test suite for backend.services.safety_modes functionality."""

    def test_safety_modes_module_availability(self):
        """Test that the safety_modes module can be imported."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"backend.services.safety_modes not importable: {IMPORT_ERROR}")
        
        # Test that we can import the main components
        assert SafetyMode is not None
        assert RiskLevel is not None
        assert TradingSafety is not None
        assert TradingMode is not None
        assert SafetyModeManager is not None

    # Test SafetyMode Enum
    def test_safety_mode_enum(self):
        """Test SafetyMode enum values."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        assert SafetyMode.NORMAL.value == "normal"
        assert SafetyMode.RESTRICTED.value == "restricted"
        assert SafetyMode.HALT.value == "halt"

    # Test RiskLevel Enum
    def test_risk_level_enum(self):
        """Test RiskLevel enum values."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    # Test TradingMode Enum
    def test_trading_mode_enum(self):
        """Test TradingMode enum values and properties."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        assert TradingMode.SHADOW.value == "shadow"
        assert TradingMode.DRY_RUN.value == "dry_run"
        assert TradingMode.LIVE.value == "live"
        
        # Test risk levels
        assert TradingMode.SHADOW.risk_level == 0
        assert TradingMode.DRY_RUN.risk_level == 1
        assert TradingMode.LIVE.risk_level == 2
        
        # Test allows_real_execution
        assert not TradingMode.SHADOW.allows_real_execution
        assert not TradingMode.DRY_RUN.allows_real_execution
        assert TradingMode.LIVE.allows_real_execution

    # Test FeatureFlagScope Enum
    def test_feature_flag_scope_enum(self):
        """Test FeatureFlagScope enum values."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        assert FeatureFlagScope.GLOBAL.value == "global"
        assert FeatureFlagScope.SYMBOL.value == "symbol"
        assert FeatureFlagScope.USER.value == "user"
        assert FeatureFlagScope.STRATEGY.value == "strategy"

    # Test KillSwitchScope Enum
    def test_kill_switch_scope_enum(self):
        """Test KillSwitchScope enum values."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        assert KillSwitchScope.GLOBAL.value == "global"
        assert KillSwitchScope.SYMBOL.value == "symbol"
        assert KillSwitchScope.USER.value == "user"
        assert KillSwitchScope.STRATEGY.value == "strategy"

    # Test TradingSafety Class
    def test_trading_safety_init(self):
        """Test TradingSafety initialization."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        safety = TradingSafety()
        assert safety.get_safety_mode() == SafetyMode.NORMAL
        assert safety._position_limits['max_position_value'] == 100000
        assert safety._position_limits['max_portfolio_concentration'] == 0.20

    def test_trading_safety_set_get_mode(self):
        """Test setting and getting safety mode."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        safety = TradingSafety()
        
        safety.set_safety_mode(SafetyMode.RESTRICTED)
        assert safety.get_safety_mode() == SafetyMode.RESTRICTED
        
        safety.set_safety_mode(SafetyMode.HALT)
        assert safety.get_safety_mode() == SafetyMode.HALT

    def test_trading_safety_is_trading_allowed(self):
        """Test is_trading_allowed logic."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        safety = TradingSafety()
        
        safety.set_safety_mode(SafetyMode.NORMAL)
        assert safety.is_trading_allowed() is True
        
        safety.set_safety_mode(SafetyMode.RESTRICTED)
        assert safety.is_trading_allowed() is True
        
        safety.set_safety_mode(SafetyMode.HALT)
        assert safety.is_trading_allowed() is False

    def test_trading_safety_max_position_size(self):
        """Test get_max_position_size logic."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        safety = TradingSafety()
        
        safety.set_safety_mode(SafetyMode.NORMAL)
        assert safety.get_max_position_size() == 100000
        
        safety.set_safety_mode(SafetyMode.RESTRICTED)
        assert safety.get_max_position_size() == 50000  # 50% of normal
        
        safety.set_safety_mode(SafetyMode.HALT)
        assert safety.get_max_position_size() == 0

    def test_trading_safety_adjusted_position_size(self):
        """Test get_adjusted_position_size logic."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        safety = TradingSafety()
        
        safety.set_safety_mode(SafetyMode.NORMAL)
        assert safety.get_adjusted_position_size(1000) == 1000
        
        safety.set_safety_mode(SafetyMode.RESTRICTED)
        assert safety.get_adjusted_position_size(1000) == 500  # 50% reduction

    def test_trading_safety_assess_risk_level(self):
        """Test assess_risk_level logic."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        safety = TradingSafety()
        
        # Low risk
        assert safety.assess_risk_level(100000, 500, 0.01) == RiskLevel.LOW
        
        # Medium risk
        assert safety.assess_risk_level(100000, 1500, 0.025) == RiskLevel.MEDIUM
        
        # High risk  
        assert safety.assess_risk_level(100000, 3500, 0.08) == RiskLevel.HIGH
        
        # Critical risk
        assert safety.assess_risk_level(100000, 6000, 0.12) == RiskLevel.CRITICAL
        
        # Edge case: zero portfolio value (daily_pnl_pct = 0, only max_drawdown matters)
        assert safety.assess_risk_level(0, 1000, 0.05) == RiskLevel.MEDIUM  # 5% drawdown -> medium

    def test_trading_safety_circuit_breaker(self):
        """Test check_circuit_breaker logic."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        safety = TradingSafety()
        
        # High risk should trigger restricted mode
        safety.check_circuit_breaker(100000, 3500, 0.08)
        assert safety.get_safety_mode() == SafetyMode.RESTRICTED
        
        # Reset to normal for next test
        safety.set_safety_mode(SafetyMode.NORMAL)
        
        # Critical risk should trigger halt
        safety.check_circuit_breaker(100000, 6000, 0.12)
        assert safety.get_safety_mode() == SafetyMode.HALT

    def test_trading_safety_position_limits(self):
        """Test position limits functionality."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        safety = TradingSafety()
        
        # Test setting limits
        safety.set_position_limits(200000, 0.30)
        assert safety._position_limits['max_position_value'] == 200000
        assert safety._position_limits['max_portfolio_concentration'] == 0.30

    def test_trading_safety_is_position_allowed(self):
        """Test is_position_allowed logic."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        safety = TradingSafety()
        
        # Within limits
        assert safety.is_position_allowed("AAPL", 50000, 1000000) is True
        
        # Exceeds value limit
        assert safety.is_position_allowed("AAPL", 150000, 1000000) is False
        
        # Exceeds concentration limit (>20%)
        assert safety.is_position_allowed("AAPL", 250000, 1000000) is False
        
        # Edge case: zero portfolio value (concentration = 0, so position allowed)
        assert safety.is_position_allowed("AAPL", 50000, 0) is True

    @patch('backend.services.safety_modes.datetime')
    def test_trading_safety_is_trading_time_allowed(self, mock_datetime):
        """Test is_trading_time_allowed logic."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        safety = TradingSafety()
        
        # Mock weekday during market hours
        mock_now = Mock()
        mock_now.weekday.return_value = 2  # Wednesday
        mock_now.time.return_value = time(10, 30)  # 10:30 AM
        mock_datetime.now.return_value = mock_now
        
        assert safety.is_trading_time_allowed() is True
        
        # Mock weekend
        mock_now.weekday.return_value = 5  # Saturday
        assert safety.is_trading_time_allowed() is False
        
        # Mock after hours
        mock_now.weekday.return_value = 2  # Wednesday
        mock_now.time.return_value = time(17, 0)  # 5:00 PM
        assert safety.is_trading_time_allowed() is False

    # Test FeatureFlag Class
    def test_feature_flag_creation(self):
        """Test FeatureFlag creation and basic properties."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        flag = FeatureFlag(
            name="test_flag",
            enabled=True,
            scope=FeatureFlagScope.GLOBAL,
            rollout_percentage=50.0
        )
        
        assert flag.name == "test_flag"
        assert flag.enabled is True
        assert flag.scope == FeatureFlagScope.GLOBAL
        assert flag.rollout_percentage == 50.0
        assert flag.target is None

    def test_feature_flag_is_enabled_for_global(self):
        """Test FeatureFlag.is_enabled_for with global scope."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        # Enabled global flag
        flag = FeatureFlag(
            name="global_flag",
            enabled=True,
            scope=FeatureFlagScope.GLOBAL
        )
        
        context = {"symbol": "AAPL", "user_id": "user123"}
        assert flag.is_enabled_for(context) is True
        
        # Disabled flag
        flag.enabled = False
        assert flag.is_enabled_for(context) is False

    def test_feature_flag_is_enabled_for_symbol(self):
        """Test FeatureFlag.is_enabled_for with symbol scope."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        flag = FeatureFlag(
            name="symbol_flag",
            enabled=True,
            scope=FeatureFlagScope.SYMBOL,
            target="AAPL"
        )
        
        # Matching symbol
        context = {"symbol": "AAPL", "user_id": "user123"}
        assert flag.is_enabled_for(context) is True
        
        # Non-matching symbol
        context = {"symbol": "GOOGL", "user_id": "user123"}
        assert flag.is_enabled_for(context) is False

    def test_feature_flag_is_enabled_for_user(self):
        """Test FeatureFlag.is_enabled_for with user scope."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        flag = FeatureFlag(
            name="user_flag",
            enabled=True,
            scope=FeatureFlagScope.USER,
            target="user123"
        )
        
        # Matching user
        context = {"symbol": "AAPL", "user_id": "user123"}
        assert flag.is_enabled_for(context) is True
        
        # Non-matching user
        context = {"symbol": "AAPL", "user_id": "user456"}
        assert flag.is_enabled_for(context) is False

    def test_feature_flag_is_enabled_for_strategy(self):
        """Test FeatureFlag.is_enabled_for with strategy scope."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        flag = FeatureFlag(
            name="strategy_flag",
            enabled=True,
            scope=FeatureFlagScope.STRATEGY,
            target="momentum"
        )
        
        # Matching strategy
        context = {"strategy": "momentum", "user_id": "user123"}
        assert flag.is_enabled_for(context) is True
        
        # Non-matching strategy
        context = {"strategy": "mean_reversion", "user_id": "user123"}
        assert flag.is_enabled_for(context) is False

    def test_feature_flag_rollout_percentage(self):
        """Test FeatureFlag rollout percentage logic."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        # 0% rollout should always be disabled
        flag = FeatureFlag(
            name="rollout_flag",
            enabled=True,
            scope=FeatureFlagScope.GLOBAL,
            rollout_percentage=0.0
        )
        
        context = {"user_id": "user123", "symbol": "AAPL"}
        assert flag.is_enabled_for(context) is False
        
        # 100% rollout should always be enabled (when flag is enabled)
        flag.rollout_percentage = 100.0
        assert flag.is_enabled_for(context) is True

    def test_feature_flag_expiration(self):
        """Test FeatureFlag expiration logic."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        # Expired flag
        past_time = datetime.now(UTC) - timedelta(hours=1)
        flag = FeatureFlag(
            name="expired_flag",
            enabled=True,
            scope=FeatureFlagScope.GLOBAL,
            expires_at=past_time
        )
        
        context = {"user_id": "user123"}
        assert flag.is_enabled_for(context) is False
        
        # Future expiration
        future_time = datetime.now(UTC) + timedelta(hours=1)
        flag.expires_at = future_time
        assert flag.is_enabled_for(context) is True

    # Test KillSwitch Class
    def test_kill_switch_creation(self):
        """Test KillSwitch creation and basic properties."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        kill_switch = KillSwitch(
            name="emergency_stop",
            active=True,
            scope=KillSwitchScope.GLOBAL,
            reason="Market volatility"
        )
        
        assert kill_switch.name == "emergency_stop"
        assert kill_switch.active is True
        assert kill_switch.scope == KillSwitchScope.GLOBAL
        assert kill_switch.reason == "Market volatility"

    def test_kill_switch_is_active_for_global(self):
        """Test KillSwitch.is_active_for with global scope."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        # Active global kill switch
        kill_switch = KillSwitch(
            name="global_stop",
            active=True,
            scope=KillSwitchScope.GLOBAL
        )
        
        context = {"symbol": "AAPL", "user_id": "user123"}
        assert kill_switch.is_active_for(context) is True
        
        # Inactive kill switch
        kill_switch.active = False
        assert kill_switch.is_active_for(context) is False

    def test_kill_switch_is_active_for_symbol(self):
        """Test KillSwitch.is_active_for with symbol scope."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        kill_switch = KillSwitch(
            name="symbol_stop",
            active=True,
            scope=KillSwitchScope.SYMBOL,
            target="AAPL"
        )
        
        # Matching symbol
        context = {"symbol": "AAPL", "user_id": "user123"}
        assert kill_switch.is_active_for(context) is True
        
        # Non-matching symbol
        context = {"symbol": "GOOGL", "user_id": "user123"}
        assert kill_switch.is_active_for(context) is False

    def test_kill_switch_auto_reset(self):
        """Test KillSwitch auto-reset functionality."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        # Auto-reset in the past
        past_time = datetime.now(UTC) - timedelta(minutes=30)
        kill_switch = KillSwitch(
            name="auto_reset_stop",
            active=True,
            scope=KillSwitchScope.GLOBAL,
            auto_reset_at=past_time
        )
        
        context = {"user_id": "user123"}
        assert kill_switch.is_active_for(context) is False
        
        # Auto-reset in the future
        future_time = datetime.now(UTC) + timedelta(minutes=30)
        kill_switch.auto_reset_at = future_time
        assert kill_switch.is_active_for(context) is True

    # Test TradingModeConfig Class
    def test_trading_mode_config_creation(self):
        """Test TradingModeConfig creation."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        config = TradingModeConfig(
            mode=TradingMode.LIVE,
            max_order_value=10000.0,
            live_mode_confirmations=2
        )
        
        assert config.mode == TradingMode.LIVE
        assert config.max_order_value == 10000.0
        assert config.live_mode_confirmations == 2

    def test_trading_mode_config_validation(self):
        """Test TradingModeConfig validation."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        # Valid live mode config
        config = TradingModeConfig(
            mode=TradingMode.LIVE,
            live_mode_confirmations=1
        )
        assert config.live_mode_confirmations == 1
        
        # Invalid live mode config (should raise ValidationError)
        with pytest.raises(Exception):  # Pydantic ValidationError
            TradingModeConfig(
                mode=TradingMode.LIVE,
                live_mode_confirmations=0
            )

    # Test TradeExecutionResult Class
    def test_trade_execution_result_creation(self):
        """Test TradeExecutionResult creation."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        result = TradeExecutionResult(
            order_id="order123",
            mode=TradingMode.LIVE,
            executed=True,
            execution_time_ms=150.5
        )
        
        assert result.order_id == "order123"
        assert result.mode == TradingMode.LIVE
        assert result.executed is True
        assert result.execution_time_ms == 150.5
        assert result.blocked_by is None

    # Test SafetyModeManager Class
    def test_safety_mode_manager_init(self):
        """Test SafetyModeManager initialization."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        # Default initialization
        manager = SafetyModeManager()
        assert manager.get_current_mode() == TradingMode.DRY_RUN
        
        # Initialize with specific mode
        manager = SafetyModeManager(mode=TradingMode.SHADOW)
        assert manager.get_current_mode() == TradingMode.SHADOW

    def test_safety_mode_manager_get_mode_config(self):
        """Test SafetyModeManager.get_mode_config."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager()
        
        # Test shadow mode config
        shadow_config = manager.get_mode_config(TradingMode.SHADOW)
        assert shadow_config.mode == TradingMode.SHADOW
        assert shadow_config.shadow_mode_comparison is True
        assert shadow_config.max_order_value is None
        
        # Test live mode config
        live_config = manager.get_mode_config(TradingMode.LIVE)
        assert live_config.mode == TradingMode.LIVE
        assert live_config.max_order_value == 50000.0
        assert live_config.live_mode_confirmations == 2

    @pytest.mark.asyncio
    async def test_safety_mode_manager_set_trading_mode(self):
        """Test SafetyModeManager.set_trading_mode."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager()
        
        # Should succeed setting to same or lower risk
        result = await manager.set_trading_mode(TradingMode.SHADOW, "admin")
        assert result is True
        assert manager.get_current_mode() == TradingMode.SHADOW

    def test_safety_mode_manager_feature_flags(self):
        """Test SafetyModeManager feature flag management."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager()
        
        # Create feature flag
        flag = FeatureFlag(
            name="test_feature",
            enabled=True,
            scope=FeatureFlagScope.GLOBAL
        )
        
        # Create feature flag (correct method name)
        manager.create_feature_flag(flag)
        
        # Check if feature is enabled
        context = {"user_id": "user123"}
        assert manager.is_feature_enabled("test_feature", context) is True
        
        # Test non-existent flag (defaults to enabled if not found per implementation)
        assert manager.is_feature_enabled("non_existent", context) is True

    def test_safety_mode_manager_kill_switches(self):
        """Test SafetyModeManager kill switch management."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager()
        
        # Activate kill switch
        result = manager.activate_kill_switch(
            "emergency_stop",
            KillSwitchScope.GLOBAL,
            "Market crash",
            "admin"
        )
        assert result is True
        
        # Check if blocked
        context = {"symbol": "AAPL", "user_id": "user123"}
        blocking_switch = manager.is_blocked_by_kill_switch(context)
        assert blocking_switch is not None
        assert blocking_switch.name == "emergency_stop"
        
        # Deactivate kill switch
        result = manager.deactivate_kill_switch("emergency_stop", "admin")
        assert result is True
        
        # Should not be blocked anymore
        blocking_switch = manager.is_blocked_by_kill_switch(context)
        assert blocking_switch is None

    def test_safety_mode_manager_list_active_kill_switches(self):
        """Test SafetyModeManager.list_active_kill_switches."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager()
        
        # Initially no active switches
        active_switches = manager.list_active_kill_switches()
        assert len(active_switches) == 0
        
        # Activate a switch (fix parameter order)
        manager.activate_kill_switch(
            "test_switch",
            KillSwitchScope.SYMBOL,
            "Testing",
            target="AAPL",
            activated_by="admin"
        )
        
        # Should have one active switch
        active_switches = manager.list_active_kill_switches()
        assert len(active_switches) == 1
        assert active_switches[0].name == "test_switch"

    @pytest.mark.asyncio 
    async def test_safety_mode_manager_execute_order_with_safety(self):
        """Test SafetyModeManager.execute_order_with_safety."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager()
        
        # Mock execution function
        async def mock_execution_func():
            return {"status": "executed", "order_id": "test123"}
        
        order_data = {
            "symbol": "AAPL",
            "quantity": 100,
            "price": 150.0,
            "strategy": "momentum"
        }
        
        # Should execute normally
        result = await manager.execute_order_with_safety(
            "test123",
            order_data,
            "user123",
            mock_execution_func
        )
        
        assert result.order_id == "test123"
        assert result.mode == manager.get_current_mode()

    @pytest.mark.asyncio
    async def test_safety_mode_manager_execute_order_blocked_by_kill_switch(self):
        """Test order execution blocked by kill switch."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager()
        
        # Activate global kill switch
        manager.activate_kill_switch("test_block", KillSwitchScope.GLOBAL, "Testing")
        
        order_data = {"symbol": "AAPL", "quantity": 100, "price": 150.0}
        
        async def mock_execution_func():
            return {"status": "executed"}
        
        result = await manager.execute_order_with_safety(
            "blocked_order", order_data, "user123", mock_execution_func
        )
        
        assert result.executed is False
        assert "Kill switch" in result.blocked_by

    @pytest.mark.asyncio
    async def test_safety_mode_manager_execute_order_blocked_by_feature_flag(self):
        """Test order execution blocked by feature flag."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager()
        
        # Create disabled feature flag for order submission
        flag = FeatureFlag(
            name="order_submission",
            enabled=False,
            scope=FeatureFlagScope.GLOBAL
        )
        manager.create_feature_flag(flag)
        
        order_data = {"symbol": "AAPL", "quantity": 100, "price": 150.0}
        
        async def mock_execution_func():
            return {"status": "executed"}
        
        result = await manager.execute_order_with_safety(
            "blocked_order", order_data, "user123", mock_execution_func
        )
        
        assert result.executed is False
        assert "Feature flag" in result.blocked_by

    @pytest.mark.asyncio
    async def test_safety_mode_manager_shadow_mode_execution(self):
        """Test execution in shadow mode."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager(mode=TradingMode.SHADOW)
        
        order_data = {"symbol": "AAPL", "quantity": 100, "price": 150.0}
        
        async def mock_execution_func():
            return {"status": "executed"}
        
        result = await manager.execute_order_with_safety(
            "shadow_order", order_data, "user123", mock_execution_func
        )
        
        assert result.mode == TradingMode.SHADOW
        assert result.executed is True
        assert result.simulation_result is not None

    @pytest.mark.asyncio
    async def test_safety_mode_manager_dry_run_mode_execution(self):
        """Test execution in dry run mode."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager(mode=TradingMode.DRY_RUN)
        
        order_data = {"symbol": "AAPL", "quantity": 10, "price": 150.0}  # $1.5k - within limit
        
        async def mock_execution_func():
            return {"status": "executed"}
        
        result = await manager.execute_order_with_safety(
            "dry_run_order", order_data, "user123", mock_execution_func
        )
        
        assert result.mode == TradingMode.DRY_RUN
        assert result.executed is True
        assert result.simulation_result is not None

    @pytest.mark.asyncio
    async def test_safety_mode_manager_dry_run_value_limit(self):
        """Test dry run mode value limits."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager(mode=TradingMode.DRY_RUN)
        
        # Order exceeding dry run limit ($10k default)
        order_data = {"symbol": "AAPL", "quantity": 1000, "price": 150.0}  # $150k
        
        async def mock_execution_func():
            return {"status": "executed"}
        
        result = await manager.execute_order_with_safety(
            "large_order", order_data, "user123", mock_execution_func
        )
        
        assert result.executed is False
        assert "exceeds limit" in result.blocked_by

    @pytest.mark.asyncio 
    async def test_safety_mode_manager_live_mode_execution(self):
        """Test execution in live mode."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager(mode=TradingMode.LIVE)
        
        # Use allowed symbol from default config
        order_data = {"symbol": "AAPL", "quantity": 10, "price": 150.0}  # $1.5k
        
        async def mock_execution_func(data):
            return {"status": "filled", "order_id": "live123"}
        
        # Mock the resilience manager
        with patch('backend.services.safety_modes.resilience_manager') as mock_resilience:
            mock_caller = AsyncMock()
            mock_caller.execute = AsyncMock(return_value={"status": "filled"})
            mock_resilience.resilient_call.return_value.__aenter__ = AsyncMock(return_value=mock_caller)
            mock_resilience.resilient_call.return_value.__aexit__ = AsyncMock(return_value=None)
            
            result = await manager.execute_order_with_safety(
                "live_order", order_data, "user123", mock_execution_func
            )
            
            assert result.mode == TradingMode.LIVE
            assert result.executed is True
            assert result.real_result is not None

    @pytest.mark.asyncio
    async def test_safety_mode_manager_live_mode_symbol_blocked(self):
        """Test live mode blocking non-allowed symbols."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager(mode=TradingMode.LIVE)
        
        # Use non-allowed symbol
        order_data = {"symbol": "BADSTOCK", "quantity": 10, "price": 150.0}
        
        async def mock_execution_func():
            return {"status": "executed"}
        
        result = await manager.execute_order_with_safety(
            "blocked_symbol", order_data, "user123", mock_execution_func
        )
        
        assert result.executed is False
        assert "not in allowed list" in result.blocked_by

    @pytest.mark.asyncio
    async def test_safety_mode_manager_live_mode_value_limit(self):
        """Test live mode value limits."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager(mode=TradingMode.LIVE)
        
        # Order exceeding live mode limit ($50k default)
        order_data = {"symbol": "AAPL", "quantity": 1000, "price": 150.0}  # $150k
        
        async def mock_execution_func():
            return {"status": "executed"}
        
        result = await manager.execute_order_with_safety(
            "large_live_order", order_data, "user123", mock_execution_func
        )
        
        assert result.executed is False
        assert "exceeds limit" in result.blocked_by

    @pytest.mark.asyncio
    async def test_safety_mode_manager_live_mode_execution_error(self):
        """Test live mode execution error handling."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager(mode=TradingMode.LIVE)
        
        order_data = {"symbol": "AAPL", "quantity": 10, "price": 150.0}
        
        async def mock_execution_func():
            raise Exception("Broker connection failed")
        
        # Mock the resilience manager to raise an exception
        with patch('backend.services.safety_modes.resilience_manager') as mock_resilience:
            mock_caller = AsyncMock()
            mock_caller.execute = AsyncMock(side_effect=Exception("Broker error"))
            mock_resilience.resilient_call.return_value.__aenter__ = AsyncMock(return_value=mock_caller)
            mock_resilience.resilient_call.return_value.__aexit__ = AsyncMock(return_value=None)
            
            result = await manager.execute_order_with_safety(
                "error_order", order_data, "user123", mock_execution_func
            )
            
            assert result.executed is False
            assert "Execution error" in result.blocked_by

    def test_safety_mode_manager_get_safety_status(self):
        """Test SafetyModeManager.get_safety_status."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager()
        
        # Add some feature flags and kill switches
        flag = FeatureFlag(name="test_flag", enabled=True, scope=FeatureFlagScope.GLOBAL)
        manager.create_feature_flag(flag)
        
        manager.activate_kill_switch("test_switch", KillSwitchScope.GLOBAL, "Testing")
        
        status = manager.get_safety_status()
        
        assert "current_mode" in status
        assert "mode_risk_level" in status
        assert "active_feature_flags" in status
        assert "active_kill_switches" in status
        assert status["active_feature_flags"] >= 1
        assert status["active_kill_switches"] >= 1

    def test_safety_mode_manager_list_feature_flags(self):
        """Test SafetyModeManager.list_feature_flags."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager()
        
        # Initially no flags
        flags = manager.list_feature_flags()
        initial_count = len(flags)
        
        # Add a flag
        flag = FeatureFlag(name="test_flag", enabled=True, scope=FeatureFlagScope.GLOBAL)
        manager.create_feature_flag(flag)
        
        # Should have one more flag
        flags = manager.list_feature_flags()
        assert len(flags) == initial_count + 1

    @pytest.mark.asyncio
    async def test_safety_mode_manager_set_trading_mode_risk_validation(self):
        """Test trading mode validation with risk levels."""
        if not SAFETY_MODES_MODULE_EXISTS:
            pytest.skip(f"Module not available: {IMPORT_ERROR}")
        
        manager = SafetyModeManager(mode=TradingMode.SHADOW)  # Start at risk level 0
        
        # Should allow going to dry run (higher risk)
        result = await manager.set_trading_mode(TradingMode.DRY_RUN, "admin")
        assert result is True
        assert manager.get_current_mode() == TradingMode.DRY_RUN


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])