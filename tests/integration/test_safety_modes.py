"""
Integration tests for trading safety modes system.

Tests comprehensive safety controls including:
- Mode transitions and restrictions
- Feature flag behavior across scopes
- Kill switch activation and blocking
- Order execution safety in all modes
- Emergency procedures and recovery
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

from backend.services.safety_modes import (
    SafetyModeManager,
    TradingMode,
    FeatureFlag,
    FeatureFlagScope,
    KillSwitch,
    KillSwitchScope,
    TradingModeConfig,
    submit_order_safely,
    emergency_halt,
    halt_symbol,
    enable_gradual_rollout
)


@pytest.fixture
def safety_manager():
    """Create fresh safety manager for each test."""
    return SafetyModeManager()


@pytest.fixture
def sample_order():
    """Sample order data for testing."""
    return {
        'symbol': 'AAPL',
        'quantity': 100,
        'price': 150.0,
        'order_type': 'market',
        'strategy': 'momentum'
    }


@pytest.fixture
def mock_execution_func():
    """Mock order execution function."""
    async def mock_exec(order_data):
        return {
            'status': 'filled',
            'filled_quantity': order_data['quantity'],
            'average_price': order_data['price'],
            'commission': 5.0,
            'execution_id': 'mock_12345'
        }
    
    return mock_exec


class TestTradingModes:
    """Test trading mode management and transitions."""
    
    def test_initial_mode_is_safe(self, safety_manager):
        """System should start in DRY_RUN mode for safety."""
        assert safety_manager.get_current_mode() == TradingMode.DRY_RUN
    
    async def test_mode_transitions(self, safety_manager):
        """Test valid mode transitions."""
        
        # Can move from DRY_RUN to SHADOW (safer)
        result = await safety_manager.set_trading_mode(TradingMode.SHADOW, "admin")
        assert result is True
        assert safety_manager.get_current_mode() == TradingMode.SHADOW
        
        # Can move to LIVE (riskier, but allowed)
        result = await safety_manager.set_trading_mode(TradingMode.LIVE, "admin")
        assert result is True
        assert safety_manager.get_current_mode() == TradingMode.LIVE
        
        # Can move back to safer modes
        result = await safety_manager.set_trading_mode(TradingMode.DRY_RUN, "admin")
        assert result is True
        assert safety_manager.get_current_mode() == TradingMode.DRY_RUN
    
    def test_mode_risk_levels(self):
        """Test mode risk level assignment."""
        assert TradingMode.SHADOW.risk_level == 0
        assert TradingMode.DRY_RUN.risk_level == 1
        assert TradingMode.LIVE.risk_level == 2
    
    def test_mode_execution_permissions(self):
        """Test which modes allow real execution."""
        assert not TradingMode.SHADOW.allows_real_execution
        assert not TradingMode.DRY_RUN.allows_real_execution
        assert TradingMode.LIVE.allows_real_execution
    
    def test_mode_configurations(self, safety_manager):
        """Test mode-specific configurations."""
        
        # Shadow mode should have no limits
        shadow_config = safety_manager.get_mode_config(TradingMode.SHADOW)
        assert shadow_config.max_order_value is None
        assert shadow_config.shadow_mode_comparison is True
        
        # Live mode should have strict limits
        live_config = safety_manager.get_mode_config(TradingMode.LIVE)
        assert live_config.max_order_value == 50000.0
        assert live_config.live_mode_confirmations >= 1
        assert live_config.allowed_symbols is not None


class TestFeatureFlags:
    """Test feature flag system."""
    
    def test_create_global_feature_flag(self, safety_manager):
        """Test global feature flag creation."""
        
        flag = FeatureFlag(
            name="new_algorithm",
            enabled=True,
            scope=FeatureFlagScope.GLOBAL,
            rollout_percentage=50.0
        )
        
        safety_manager.create_feature_flag(flag)
        flags = safety_manager.list_feature_flags()
        assert len(flags) == 1
        assert flags[0].name == "new_algorithm"
    
    def test_symbol_specific_feature_flag(self, safety_manager):
        """Test symbol-specific feature flags."""
        
        flag = FeatureFlag(
            name="options_trading",
            enabled=True,
            scope=FeatureFlagScope.SYMBOL,
            target="TSLA"
        )
        
        safety_manager.create_feature_flag(flag)
        
        # Should be enabled for TSLA
        context = {'symbol': 'TSLA', 'user_id': 'user123'}
        assert safety_manager.is_feature_enabled("options_trading", context) is True
        
        # Should be disabled for other symbols
        context = {'symbol': 'AAPL', 'user_id': 'user123'}
        assert safety_manager.is_feature_enabled("options_trading", context) is False
    
    def test_rollout_percentage(self, safety_manager):
        """Test percentage-based rollout."""
        
        # Create flag with 0% rollout
        flag = FeatureFlag(
            name="zero_rollout",
            enabled=True,
            scope=FeatureFlagScope.GLOBAL,
            rollout_percentage=0.0
        )
        
        safety_manager.create_feature_flag(flag)
        
        context = {'user_id': 'test_user'}
        # Should always be disabled with 0% rollout
        assert safety_manager.is_feature_enabled("zero_rollout", context) is False
        
        # Create flag with 100% rollout
        flag = FeatureFlag(
            name="full_rollout",
            enabled=True,
            scope=FeatureFlagScope.GLOBAL,
            rollout_percentage=100.0
        )
        
        safety_manager.create_feature_flag(flag)
        
        # Should always be enabled with 100% rollout
        assert safety_manager.is_feature_enabled("full_rollout", context) is True
    
    def test_expired_feature_flag(self, safety_manager):
        """Test expired feature flags."""
        
        # Create expired flag
        flag = FeatureFlag(
            name="expired_feature",
            enabled=True,
            scope=FeatureFlagScope.GLOBAL,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1)  # Already expired
        )
        
        safety_manager.create_feature_flag(flag)
        
        context = {'user_id': 'test_user'}
        assert safety_manager.is_feature_enabled("expired_feature", context) is False
    
    def test_nonexistent_feature_flag_defaults_enabled(self, safety_manager):
        """Non-existent feature flags should default to enabled."""
        
        context = {'user_id': 'test_user'}
        assert safety_manager.is_feature_enabled("nonexistent_flag", context) is True


class TestKillSwitches:
    """Test kill switch system."""
    
    def test_global_kill_switch(self, safety_manager):
        """Test global kill switch activation."""
        
        result = safety_manager.activate_kill_switch(
            name="emergency_stop",
            scope=KillSwitchScope.GLOBAL,
            reason="Market volatility",
            activated_by="admin"
        )
        
        assert result is True
        
        # Should block all contexts
        context = {'symbol': 'AAPL', 'user_id': 'user123'}
        blocking_switch = safety_manager.is_blocked_by_kill_switch(context)
        assert blocking_switch is not None
        assert blocking_switch.name == "emergency_stop"
    
    def test_symbol_kill_switch(self, safety_manager):
        """Test symbol-specific kill switch."""
        
        result = safety_manager.activate_kill_switch(
            name="halt_TSLA",
            scope=KillSwitchScope.SYMBOL,
            target="TSLA",
            reason="News event",
            activated_by="admin"
        )
        
        assert result is True
        
        # Should block TSLA
        context = {'symbol': 'TSLA'}
        blocking_switch = safety_manager.is_blocked_by_kill_switch(context)
        assert blocking_switch is not None
        
        # Should not block other symbols
        context = {'symbol': 'AAPL'}
        blocking_switch = safety_manager.is_blocked_by_kill_switch(context)
        assert blocking_switch is None
    
    def test_kill_switch_deactivation(self, safety_manager):
        """Test kill switch deactivation."""
        
        safety_manager.activate_kill_switch(
            name="test_switch",
            scope=KillSwitchScope.GLOBAL,
            reason="Testing",
            activated_by="admin"
        )
        
        # Initially blocked
        context = {'symbol': 'AAPL'}
        assert safety_manager.is_blocked_by_kill_switch(context) is not None
        
        # Deactivate
        result = safety_manager.deactivate_kill_switch("test_switch", "admin")
        assert result is True
        
        # Should no longer be blocked
        assert safety_manager.is_blocked_by_kill_switch(context) is None
    
    def test_auto_reset_kill_switch(self, safety_manager):
        """Test automatic kill switch reset."""
        
        # Create kill switch that expires in the past
        kill_switch = KillSwitch(
            name="auto_reset",
            active=True,
            scope=KillSwitchScope.GLOBAL,
            reason="Testing",
            auto_reset_at=datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        
        safety_manager._kill_switches["auto_reset"] = kill_switch
        
        # Should not block due to expiration
        context = {'symbol': 'AAPL'}
        blocking_switch = safety_manager.is_blocked_by_kill_switch(context)
        assert blocking_switch is None
    
    def test_list_active_kill_switches(self, safety_manager):
        """Test listing active kill switches."""
        
        # Initially no active switches
        active = safety_manager.list_active_kill_switches()
        assert len(active) == 0
        
        # Activate some switches
        safety_manager.activate_kill_switch("switch1", KillSwitchScope.GLOBAL, "reason1")
        safety_manager.activate_kill_switch("switch2", KillSwitchScope.SYMBOL, "reason2", target="AAPL")
        
        active = safety_manager.list_active_kill_switches()
        assert len(active) == 2
        
        # Deactivate one
        safety_manager.deactivate_kill_switch("switch1", "admin")
        
        active = safety_manager.list_active_kill_switches()
        assert len(active) == 1
        assert active[0].name == "switch2"


class TestOrderExecution:
    """Test order execution with safety controls."""
    
    async def test_shadow_mode_execution(self, safety_manager, sample_order, mock_execution_func):
        """Test order execution in shadow mode."""
        
        await safety_manager.set_trading_mode(TradingMode.SHADOW, "admin")
        
        result = await safety_manager.execute_order_with_safety(
            order_id="order123",
            order_data=sample_order,
            user_id="user123",
            execution_func=mock_execution_func
        )
        
        assert result.executed is True
        assert result.mode == TradingMode.SHADOW
        assert result.simulation_result is not None
        assert result.real_result is None  # No real execution in shadow mode
        assert result.blocked_by is None
    
    async def test_dry_run_mode_execution(self, safety_manager, sample_order, mock_execution_func):
        """Test order execution in dry run mode."""
        
        await safety_manager.set_trading_mode(TradingMode.DRY_RUN, "admin")
        
        result = await safety_manager.execute_order_with_safety(
            order_id="order123",
            order_data=sample_order,
            user_id="user123",
            execution_func=mock_execution_func
        )
        
        assert result.executed is True
        assert result.mode == TradingMode.DRY_RUN
        assert result.simulation_result is not None
        assert result.real_result is None
        assert result.execution_time_ms > 0
    
    async def test_live_mode_execution(self, safety_manager, sample_order, mock_execution_func):
        """Test order execution in live mode."""
        
        await safety_manager.set_trading_mode(TradingMode.LIVE, "admin")
        
        with patch('backend.infra.resilience.resilience_manager') as mock_resilience:
            mock_resilience.resilient_call.return_value.__aenter__.return_value.execute = AsyncMock(
                return_value={'status': 'filled', 'execution_id': 'real_12345'}
            )
            
            result = await safety_manager.execute_order_with_safety(
                order_id="order123",
                order_data=sample_order,
                user_id="user123",
                execution_func=mock_execution_func
            )
        
        assert result.executed is True
        assert result.mode == TradingMode.LIVE
        assert result.real_result is not None
        assert result.real_result['execution_id'] == 'real_12345'
    
    async def test_order_blocked_by_kill_switch(self, safety_manager, sample_order, mock_execution_func):
        """Test order blocked by kill switch."""
        
        # Activate global kill switch
        safety_manager.activate_kill_switch(
            "emergency", KillSwitchScope.GLOBAL, "Testing", activated_by="admin"
        )
        
        result = await safety_manager.execute_order_with_safety(
            order_id="order123",
            order_data=sample_order,
            user_id="user123",
            execution_func=mock_execution_func
        )
        
        assert result.executed is False
        assert "Kill switch" in result.blocked_by
        assert result.execution_time_ms == 0
    
    async def test_order_blocked_by_feature_flag(self, safety_manager, sample_order, mock_execution_func):
        """Test order blocked by disabled feature flag."""
        
        # Create disabled feature flag
        flag = FeatureFlag(
            name="order_submission",
            enabled=False,
            scope=FeatureFlagScope.GLOBAL
        )
        
        safety_manager.create_feature_flag(flag)
        
        result = await safety_manager.execute_order_with_safety(
            order_id="order123",
            order_data=sample_order,
            user_id="user123",
            execution_func=mock_execution_func
        )
        
        assert result.executed is False
        assert "Feature flag" in result.blocked_by
    
    async def test_live_mode_value_limits(self, safety_manager, mock_execution_func):
        """Test live mode order value limits."""
        
        await safety_manager.set_trading_mode(TradingMode.LIVE, "admin")
        
        # Create order exceeding value limit
        large_order = {
            'symbol': 'AAPL',
            'quantity': 1000,
            'price': 1000.0,  # $1M order, exceeds $50k limit
            'strategy': 'test'
        }
        
        result = await safety_manager.execute_order_with_safety(
            order_id="large_order",
            order_data=large_order,
            user_id="user123",
            execution_func=mock_execution_func
        )
        
        assert result.executed is False
        assert "exceeds limit" in result.blocked_by
    
    async def test_live_mode_symbol_whitelist(self, safety_manager, mock_execution_func):
        """Test live mode symbol whitelist."""
        
        await safety_manager.set_trading_mode(TradingMode.LIVE, "admin")
        
        # Try to trade symbol not in whitelist
        banned_order = {
            'symbol': 'MEME_COIN',  # Not in allowed symbols
            'quantity': 10,
            'price': 1.0,
            'strategy': 'test'
        }
        
        result = await safety_manager.execute_order_with_safety(
            order_id="banned_order",
            order_data=banned_order,
            user_id="user123",
            execution_func=mock_execution_func
        )
        
        assert result.executed is False
        assert "not in allowed list" in result.blocked_by


class TestConvenienceFunctions:
    """Test high-level convenience functions."""
    
    async def test_submit_order_safely(self, sample_order, mock_execution_func):
        """Test safe order submission function."""
        
        result = await submit_order_safely(
            order_id="order123",
            order_data=sample_order,
            user_id="user123",
            execution_func=mock_execution_func
        )
        
        # Should succeed in default DRY_RUN mode
        assert result.executed is True
        assert result.mode == TradingMode.DRY_RUN
    
    def test_emergency_halt(self):
        """Test emergency halt function."""
        
        result = emergency_halt("Market crash", "admin")
        assert result is True
        
        # Should create global kill switch
        from backend.services.safety_modes import safety_manager
        active_switches = safety_manager.list_active_kill_switches()
        assert len(active_switches) >= 1
        assert any(ks.name == "emergency_halt" for ks in active_switches)
    
    def test_halt_symbol(self):
        """Test symbol halt function."""
        
        result = halt_symbol("TSLA", "News event", "admin")
        assert result is True
        
        # Should create symbol-specific kill switch
        from backend.services.safety_modes import safety_manager
        active_switches = safety_manager.list_active_kill_switches()
        symbol_switches = [ks for ks in active_switches if ks.target == "TSLA"]
        assert len(symbol_switches) >= 1
    
    def test_enable_gradual_rollout(self):
        """Test gradual rollout function."""
        
        result = enable_gradual_rollout("NVDA", 25.0)
        assert result is True
        
        # Should create rollout feature flag
        from backend.services.safety_modes import safety_manager
        flags = safety_manager.list_feature_flags()
        rollout_flags = [f for f in flags if f.name == "rollout_NVDA"]
        assert len(rollout_flags) == 1
        assert rollout_flags[0].rollout_percentage == 25.0


class TestSafetyStatus:
    """Test safety system status and health checks."""
    
    def test_get_safety_status(self, safety_manager):
        """Test comprehensive safety status."""
        
        # Add some flags and switches
        flag = FeatureFlag("test_flag", True, FeatureFlagScope.GLOBAL)
        safety_manager.create_feature_flag(flag)
        
        safety_manager.activate_kill_switch("test_switch", KillSwitchScope.SYMBOL, "Testing", target="AAPL")
        
        status = safety_manager.get_safety_status()
        
        assert status['current_mode'] == TradingMode.DRY_RUN.value
        assert status['mode_risk_level'] == 1
        assert status['active_feature_flags'] == 1
        assert status['active_kill_switches'] == 1
        assert len(status['feature_flags']) == 1
        assert len(status['kill_switches']) == 1
        assert 'timestamp' in status
    
    def test_empty_safety_status(self, safety_manager):
        """Test safety status with no active controls."""
        
        status = safety_manager.get_safety_status()
        
        assert status['active_feature_flags'] == 0
        assert status['active_kill_switches'] == 0
        assert status['feature_flags'] == []
        assert status['kill_switches'] == []


@pytest.mark.asyncio
class TestIntegrationScenarios:
    """Test realistic integration scenarios."""
    
    async def test_production_deployment_scenario(self, safety_manager, mock_execution_func):
        """Test realistic production deployment with gradual rollout."""
        
        # 1. Start in shadow mode for new feature
        await safety_manager.set_trading_mode(TradingMode.SHADOW, "devops")
        
        # 2. Enable feature for limited rollout
        flag = FeatureFlag("new_algorithm", True, FeatureFlagScope.GLOBAL, rollout_percentage=10.0)
        safety_manager.create_feature_flag(flag)
        
        # 3. Test orders execute in shadow mode
        order = {'symbol': 'AAPL', 'quantity': 100, 'price': 150.0}
        result = await safety_manager.execute_order_with_safety("order1", order, "user1", mock_execution_func)
        
        assert result.executed is True
        assert result.mode == TradingMode.SHADOW
        
        # 4. Graduate to dry run
        await safety_manager.set_trading_mode(TradingMode.DRY_RUN, "devops")
        
        # 5. Increase rollout
        flag.rollout_percentage = 50.0
        safety_manager.create_feature_flag(flag)
        
        # 6. Final graduation to live mode
        await safety_manager.set_trading_mode(TradingMode.LIVE, "devops")
        
        assert safety_manager.get_current_mode() == TradingMode.LIVE
    
    async def test_emergency_response_scenario(self, safety_manager, mock_execution_func):
        """Test emergency response and recovery."""
        
        # Start in live mode
        await safety_manager.set_trading_mode(TradingMode.LIVE, "admin")
        
        # Simulate normal trading
        order = {'symbol': 'AAPL', 'quantity': 10, 'price': 150.0}
        
        with patch('backend.infra.resilience.resilience_manager') as mock_resilience:
            mock_resilience.resilient_call.return_value.__aenter__.return_value.execute = AsyncMock(
                return_value={'status': 'filled'}
            )
            
            result = await safety_manager.execute_order_with_safety("order1", order, "user1", mock_execution_func)
            assert result.executed is True
        
        # EMERGENCY: Market crash detected
        safety_manager.activate_kill_switch(
            "market_crash",
            KillSwitchScope.GLOBAL,
            "Extreme volatility detected",
            activated_by="risk_system"
        )
        
        # All orders should now be blocked
        result = await safety_manager.execute_order_with_safety("order2", order, "user1", mock_execution_func)
        assert result.executed is False
        assert "Kill switch" in result.blocked_by
        
        # Gradual recovery: first disable kill switch
        safety_manager.deactivate_kill_switch("market_crash", "admin")
        
        # Move to dry run for testing
        await safety_manager.set_trading_mode(TradingMode.DRY_RUN, "admin")
        
        # Test orders work again
        result = await safety_manager.execute_order_with_safety("order3", order, "user1", mock_execution_func)
        assert result.executed is True
        assert result.mode == TradingMode.DRY_RUN
        
        # Final recovery to live mode
        await safety_manager.set_trading_mode(TradingMode.LIVE, "admin")
    
    async def test_symbol_specific_incident(self, safety_manager, mock_execution_func):
        """Test symbol-specific incident handling."""
        
        await safety_manager.set_trading_mode(TradingMode.LIVE, "admin")
        
        # TSLA has earnings announcement - halt trading
        safety_manager.activate_kill_switch(
            "tsla_earnings",
            KillSwitchScope.SYMBOL,
            "Earnings announcement",
            target="TSLA",
            activated_by="compliance"
        )
        
        # TSLA orders blocked
        tsla_order = {'symbol': 'TSLA', 'quantity': 10, 'price': 200.0}
        result = await safety_manager.execute_order_with_safety("tsla1", tsla_order, "user1", mock_execution_func)
        assert result.executed is False
        
        # Other symbols still work
        aapl_order = {'symbol': 'AAPL', 'quantity': 10, 'price': 150.0}
        
        with patch('backend.infra.resilience.resilience_manager') as mock_resilience:
            mock_resilience.resilient_call.return_value.__aenter__.return_value.execute = AsyncMock(
                return_value={'status': 'filled'}
            )
            
            result = await safety_manager.execute_order_with_safety("aapl1", aapl_order, "user1", mock_execution_func)
            assert result.executed is True
        
        # Resume TSLA trading after announcement
        safety_manager.deactivate_kill_switch("tsla_earnings", "compliance")
        
        with patch('backend.infra.resilience.resilience_manager') as mock_resilience:
            mock_resilience.resilient_call.return_value.__aenter__.return_value.execute = AsyncMock(
                return_value={'status': 'filled'}
            )
            
            result = await safety_manager.execute_order_with_safety("tsla2", tsla_order, "user1", mock_execution_func)
            assert result.executed is True


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
