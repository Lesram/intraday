"""
Comprehensive test suite for services layer - safety modes and managers.
Targets critical business logic and safety systems.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal
from datetime import datetime, timedelta
from backend.services.safety_modes import (
    SafetyModeManager,
    TradingMode,
    FeatureFlag,
    KillSwitch,
)


class TestSafetyModesCoverage:
    """High-coverage tests for safety mode systems."""

    @pytest.fixture
    def safety_manager(self):
        """Create safety mode manager instance."""
        return SafetyModeManager()

    @pytest.mark.unit
    def test_safety_mode_initialization(self, safety_manager):
        """Test safety mode manager initialization."""
        assert safety_manager is not None
        assert hasattr(safety_manager, 'mode')

    @pytest.mark.unit
    def test_trading_mode_enum(self):
        """Test TradingMode enum values."""
        assert TradingMode.SHADOW is not None
        assert TradingMode.DRY_RUN is not None
        assert TradingMode.LIVE is not None
        
        # Enum should have expected values
        modes = [mode.value for mode in TradingMode]
        assert len(modes) == 3

    @pytest.mark.unit
    def test_feature_flag_creation(self):
        """Test FeatureFlag creation and properties."""
        flag = FeatureFlag(
            name="test_feature",
            enabled=True,
            description="Test feature flag"
        )
        
        assert flag.name == "test_feature"
        assert flag.enabled is True
        assert flag.description == "Test feature flag"

    @pytest.mark.unit
    def test_kill_switch_creation(self):
        """Test KillSwitch creation and properties.""" 
        kill_switch = KillSwitch(
            name="emergency_stop",
            active=False,
            reason="System maintenance"
        )
        
        assert kill_switch.name == "emergency_stop"
        assert kill_switch.active is False
        assert kill_switch.reason == "System maintenance"

    @pytest.mark.unit
    def test_safety_manager_mode_setting(self, safety_manager):
        """Test setting trading mode in safety manager."""
        # Set to shadow mode
        safety_manager.set_mode(TradingMode.SHADOW)
        assert safety_manager.mode == TradingMode.SHADOW
        
        # Set to live mode
        safety_manager.set_mode(TradingMode.LIVE)
        assert safety_manager.mode == TradingMode.LIVE

    @pytest.mark.unit 
    def test_feature_flag_evaluation(self, safety_manager):
        """Test feature flag evaluation logic."""
        # Create feature flag
        flag = FeatureFlag(
            name="new_algorithm",
            enabled=True,
            description="New trading algorithm"
        )
        
        # Add to safety manager
        safety_manager.add_feature_flag(flag)
        
        # Check if enabled
        is_enabled = safety_manager.is_feature_enabled("new_algorithm")
        assert is_enabled is True

    @pytest.mark.unit
    def test_kill_switch_activation(self, safety_manager):
        """Test kill switch activation."""
        # Create kill switch
        kill_switch = KillSwitch(
            name="market_halt",
            active=True,
            reason="Unusual market conditions"
        )
        
        # Add to safety manager
        safety_manager.add_kill_switch(kill_switch)
        
        # Check if active
        is_active = safety_manager.is_kill_switch_active("market_halt")
        assert is_active is True

    @pytest.mark.unit
    def test_safety_manager_integration(self, safety_manager):
        """Test safety manager integration with multiple components."""
        # Set up feature flag
        feature = FeatureFlag(name="test", enabled=True, description="Test")
        safety_manager.add_feature_flag(feature)
        
        # Set up kill switch
        switch = KillSwitch(name="emergency", active=False, reason="None")
        safety_manager.add_kill_switch(switch)
        
        # Test combined state
        status = safety_manager.get_status()
        assert "mode" in status
        assert "features" in status
        assert "kill_switches" in status

    @pytest.mark.unit
    def test_safety_manager_logging(self, safety_manager):
        """Test safety manager logging functionality."""
        with patch('backend.services.safety_modes.logger') as mock_logger:
            # Trigger an operation that should log
            safety_manager.set_mode(TradingMode.LIVE)
            
            # Should log mode change
            assert mock_logger.info.called or mock_logger.warning.called

    @pytest.mark.unit
    def test_feature_flag_scoping(self):
        """Test feature flag scoping by symbol."""
        # Global flag
        global_flag = FeatureFlag(
            name="global_feature",
            enabled=True,
            description="Global feature"
        )
        
        # Symbol-specific flag
        symbol_flag = FeatureFlag(
            name="symbol_feature",
            enabled=True,
            description="Symbol specific feature",
            symbols=["AAPL", "MSFT"]
        )
        
        assert global_flag.symbols is None or len(global_flag.symbols) == 0
        assert "AAPL" in symbol_flag.symbols

    @pytest.mark.unit
    def test_kill_switch_scoping(self):
        """Test kill switch scoping."""
        # Global kill switch
        global_switch = KillSwitch(
            name="global_halt",
            active=True,
            reason="System maintenance"
        )
        
        # Symbol-specific kill switch  
        symbol_switch = KillSwitch(
            name="symbol_halt",
            active=True,
            reason="Symbol-specific issue",
            symbols=["TSLA"]
        )
        
        assert global_switch.symbols is None or len(global_switch.symbols) == 0
        assert "TSLA" in symbol_switch.symbols

    @pytest.mark.unit
    def test_safety_manager_metrics(self, safety_manager):
        """Test safety manager metrics collection."""
        # Enable metrics collection if available
        if hasattr(safety_manager, 'metrics'):
            # Perform operations
            safety_manager.set_mode(TradingMode.SHADOW)
            
            # Check metrics
            metrics = safety_manager.get_metrics()
            assert isinstance(metrics, dict)

    @pytest.mark.unit
    def test_error_handling(self, safety_manager):
        """Test error handling in safety manager."""
        # Test invalid mode
        with pytest.raises((ValueError, TypeError)):
            safety_manager.set_mode("INVALID_MODE")
        
        # Test invalid feature flag
        with pytest.raises((ValueError, TypeError)):
            invalid_flag = FeatureFlag(name="", enabled=True, description="")
            safety_manager.add_feature_flag(invalid_flag)

    @pytest.mark.unit
    def test_concurrent_access(self, safety_manager):
        """Test thread-safe operations."""
        import threading
        import time
        
        results = []
        
        def worker():
            """Worker thread function."""
            safety_manager.set_mode(TradingMode.SHADOW)
            results.append(safety_manager.mode)
        
        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # All should have the same result
        assert all(result == TradingMode.SHADOW for result in results)

    @pytest.mark.unit
    def test_configuration_validation(self):
        """Test configuration validation."""
        # Valid feature flag
        valid_flag = FeatureFlag(
            name="valid_feature",
            enabled=True,
            description="Valid feature flag"
        )
        assert valid_flag.name == "valid_feature"
        
        # Valid kill switch
        valid_switch = KillSwitch(
            name="valid_switch", 
            active=False,
            reason="Test switch"
        )
        assert valid_switch.name == "valid_switch"

    @pytest.mark.unit
    def test_state_persistence(self, safety_manager):
        """Test state persistence functionality."""
        # Set initial state
        safety_manager.set_mode(TradingMode.DRY_RUN)
        
        # Save state if available
        if hasattr(safety_manager, 'save_state'):
            safety_manager.save_state()
            
        # Load state if available
        if hasattr(safety_manager, 'load_state'):
            safety_manager.load_state()
            
        # State should be preserved
        assert safety_manager.mode == TradingMode.DRY_RUN

    @pytest.mark.unit
    def test_safety_manager_cleanup(self, safety_manager):
        """Test safety manager cleanup operations."""
        # Add some state
        flag = FeatureFlag(name="temp_flag", enabled=True, description="Temp")
        safety_manager.add_feature_flag(flag)
        
        # Cleanup if available
        if hasattr(safety_manager, 'cleanup'):
            safety_manager.cleanup()
        
        # State should be cleaned up
        if hasattr(safety_manager, 'feature_flags'):
            assert len(safety_manager.feature_flags) == 0
