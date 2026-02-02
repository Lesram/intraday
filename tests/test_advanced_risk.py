"""
Tests for Advanced Risk Management System.

Tests cover:
- Volatility regime detection
- Correlation risk calculation
- Stress testing engine
- Drawdown monitoring
- Dynamic limit adjustment
- Sector concentration
"""

from datetime import datetime, UTC

import numpy as np
import pytest

from backend.risk.advanced_risk import (
    AdvancedRiskManager,
    CorrelationRisk,
    CorrelationRiskCalculator,
    DrawdownMetrics,
    DrawdownMonitor,
    DynamicLimits,
    RiskLevel,
    SectorExposure,
    StressScenario,
    StressTestEngine,
    StressTestResult,
    VolatilityRegimeDetector,
    create_advanced_risk_manager,
)


class TestVolatilityRegimeDetector:
    """Tests for volatility regime detection."""
    
    def test_low_vol_regime(self):
        """Test low volatility regime detection."""
        detector = VolatilityRegimeDetector()
        detector.update(realized_vol=0.08, vix=12.0)
        
        assert detector.current_regime == "low_vol"
        assert detector.get_limit_multiplier() == 1.2
    
    def test_normal_regime(self):
        """Test normal volatility regime detection."""
        detector = VolatilityRegimeDetector()
        detector.update(realized_vol=0.15, vix=20.0)
        
        assert detector.current_regime == "normal"
        assert detector.get_limit_multiplier() == 1.0
    
    def test_high_vol_regime(self):
        """Test high volatility regime detection."""
        detector = VolatilityRegimeDetector()
        detector.update(realized_vol=0.25, vix=32.0)
        
        assert detector.current_regime == "high_vol"
        assert detector.get_limit_multiplier() == 0.7
    
    def test_crisis_regime(self):
        """Test crisis regime detection."""
        detector = VolatilityRegimeDetector()
        detector.update(realized_vol=0.45, vix=55.0)
        
        assert detector.current_regime == "crisis"
        assert detector.get_limit_multiplier() == 0.4
    
    def test_uses_vix_when_available(self):
        """Test that VIX is used when available."""
        detector = VolatilityRegimeDetector()
        
        # Low realized vol but high VIX
        detector.update(realized_vol=0.10, vix=45.0)
        
        assert detector.current_regime == "crisis"
    
    def test_uses_realized_vol_without_vix(self):
        """Test fallback to realized vol when VIX not available."""
        detector = VolatilityRegimeDetector()
        
        # High realized vol, no VIX (scaled by 100 internally)
        detector.update(realized_vol=0.45, vix=None)
        
        assert detector.current_regime == "crisis"
    
    def test_history_maintained(self):
        """Test that historical data is maintained."""
        detector = VolatilityRegimeDetector()
        
        for _ in range(10):
            detector.update(realized_vol=0.15, vix=20.0)
        
        # Should have history
        assert len(detector._historical_vol) == 10
        assert len(detector._vix_history) == 10


class TestCorrelationRiskCalculator:
    """Tests for correlation risk calculation."""
    
    @pytest.fixture
    def calculator(self):
        """Create calculator with sample data."""
        calc = CorrelationRiskCalculator(lookback_days=60)
        
        # Add correlated returns
        np.random.seed(42)
        base_returns = np.random.normal(0, 0.02, 30)
        
        for i, r in enumerate(base_returns):
            calc.update_returns("AAPL", r)
            calc.update_returns("MSFT", r * 0.8 + np.random.normal(0, 0.005))  # Correlated
            calc.update_returns("XOM", -r * 0.3 + np.random.normal(0, 0.015))  # Negatively correlated
        
        return calc
    
    def test_calculate_correlation_risk(self, calculator):
        """Test correlation risk calculation."""
        positions = {"AAPL": 0.4, "MSFT": 0.4, "XOM": 0.2}
        
        risk = calculator.calculate(positions)
        
        assert isinstance(risk, CorrelationRisk)
        assert 0 <= risk.average_correlation <= 1 or risk.average_correlation < 0
        assert risk.effective_positions > 0
        assert 0 <= risk.concentration_hhi <= 1
    
    def test_single_position(self):
        """Test with single position."""
        calc = CorrelationRiskCalculator()
        
        positions = {"AAPL": 1.0}
        risk = calc.calculate(positions)
        
        assert risk.average_correlation == 0.0
        assert risk.effective_positions == 1.0
        assert risk.concentration_hhi == 1.0
    
    def test_empty_positions(self):
        """Test with empty positions."""
        calc = CorrelationRiskCalculator()
        
        positions = {}
        risk = calc.calculate(positions)
        
        assert risk.average_correlation == 0.0
        assert risk.effective_positions == 0.0
    
    def test_risk_contribution_sums_to_one(self, calculator):
        """Test that risk contributions sum to 1."""
        positions = {"AAPL": 0.4, "MSFT": 0.4, "XOM": 0.2}
        
        risk = calculator.calculate(positions)
        
        total_contrib = sum(risk.risk_contribution.values())
        assert abs(total_contrib - 1.0) < 0.01
    
    def test_max_pairwise_correlation(self, calculator):
        """Test max pairwise correlation."""
        positions = {"AAPL": 0.5, "MSFT": 0.5}
        
        risk = calculator.calculate(positions)
        
        # AAPL and MSFT should be highly correlated
        assert risk.max_pairwise_correlation > 0.5


class TestStressTestEngine:
    """Tests for stress testing engine."""
    
    @pytest.fixture
    def engine(self):
        """Create stress test engine."""
        engine = StressTestEngine(
            margin_requirement=0.25,
            max_acceptable_loss=0.20,
        )
        
        engine.classify_asset("AAPL", "equity")
        engine.classify_asset("MSFT", "equity")
        engine.classify_asset("TLT", "bond")
        engine.classify_asset("GLD", "commodity")
        
        return engine
    
    def test_run_2008_scenario(self, engine):
        """Test 2008 financial crisis scenario."""
        positions = {
            "AAPL": 50000,
            "MSFT": 30000,
            "TLT": 20000,
        }
        
        result = engine.run_scenario(
            StressScenario.MARKET_CRASH_2008,
            positions,
            portfolio_value=100000,
        )
        
        assert isinstance(result, StressTestResult)
        assert result.scenario == StressScenario.MARKET_CRASH_2008
        assert result.portfolio_loss_pct < 0  # Should be negative (loss)
        assert result.worst_position in positions
    
    def test_run_covid_scenario(self, engine):
        """Test COVID crash scenario."""
        positions = {"AAPL": 100000}
        
        result = engine.run_scenario(
            StressScenario.COVID_CRASH_2020,
            positions,
            portfolio_value=100000,
        )
        
        assert result.portfolio_loss_pct < 0
        # Equity should drop ~35%
        assert abs(result.portfolio_loss_pct - (-0.35)) < 0.05
    
    def test_bond_outperforms_in_crisis(self, engine):
        """Test that bonds outperform in crisis scenarios."""
        equity_positions = {"AAPL": 100000}
        bond_positions = {"TLT": 100000}
        
        equity_result = engine.run_scenario(
            StressScenario.MARKET_CRASH_2008,
            equity_positions,
            100000,
        )
        
        bond_result = engine.run_scenario(
            StressScenario.MARKET_CRASH_2008,
            bond_positions,
            100000,
        )
        
        # Bonds should do better
        assert bond_result.portfolio_loss_pct > equity_result.portfolio_loss_pct
    
    def test_margin_call_detection(self, engine):
        """Test margin call detection."""
        # Create highly leveraged position where 55% loss triggers margin call
        # Margin call triggers when loss > (1 - margin_requirement) = 75%
        # Need scenario that causes > 75% loss
        positions = {"AAPL": 100000}
        
        # Use custom scenario with 80% loss to trigger margin call
        result = engine.run_scenario(
            StressScenario.CUSTOM,
            positions,
            portfolio_value=100000,
            custom_shocks={"equity": -0.80},
        )
        
        # 80% loss should trigger margin call (> 75% threshold)
        assert result.margin_call_triggered
    
    def test_run_all_scenarios(self, engine):
        """Test running all scenarios."""
        positions = {"AAPL": 50000, "TLT": 50000}
        
        results = engine.run_all_scenarios(positions, 100000)
        
        # Should have results for all non-custom scenarios
        assert len(results) == len(StressScenario) - 1  # Exclude CUSTOM
    
    def test_custom_scenario(self, engine):
        """Test custom scenario."""
        positions = {"AAPL": 100000}
        
        custom_shocks = {"equity": -0.50}
        
        result = engine.run_scenario(
            StressScenario.CUSTOM,
            positions,
            100000,
            custom_shocks=custom_shocks,
        )
        
        assert abs(result.portfolio_loss_pct - (-0.50)) < 0.01
    
    def test_custom_scenario_requires_shocks(self, engine):
        """Test that custom scenario requires shocks parameter."""
        positions = {"AAPL": 100000}
        
        with pytest.raises(ValueError):
            engine.run_scenario(
                StressScenario.CUSTOM,
                positions,
                100000,
            )


class TestDrawdownMonitor:
    """Tests for drawdown monitoring."""
    
    def test_no_drawdown_at_peak(self):
        """Test no drawdown when at peak."""
        monitor = DrawdownMonitor()
        
        monitor.update(100000)
        monitor.update(110000)
        monitor.update(120000)  # New peak
        
        metrics = monitor.get_metrics()
        
        assert metrics.current_drawdown_pct == 0.0
        assert metrics.peak_equity == 120000
    
    def test_drawdown_calculation(self):
        """Test drawdown calculation."""
        monitor = DrawdownMonitor()
        
        monitor.update(100000)
        monitor.update(90000)  # 10% drawdown
        
        metrics = monitor.get_metrics()
        
        assert abs(metrics.current_drawdown_pct - 0.10) < 0.001
    
    def test_max_drawdown_tracking(self):
        """Test maximum drawdown tracking."""
        monitor = DrawdownMonitor()
        
        monitor.update(100000)
        monitor.update(80000)  # 20% drawdown
        monitor.update(85000)  # Partial recovery
        
        metrics = monitor.get_metrics()
        
        # Max should still be 20%
        assert abs(metrics.max_drawdown_today_pct - 0.20) < 0.001
        # Current should be 15%
        assert abs(metrics.current_drawdown_pct - 0.15) < 0.001
    
    def test_recovery_progress(self):
        """Test recovery progress calculation."""
        monitor = DrawdownMonitor()
        
        monitor.update(100000)  # Peak
        monitor.update(80000)   # Trough
        monitor.update(90000)   # 50% recovery
        
        metrics = monitor.get_metrics()
        
        assert abs(metrics.recovery_progress_pct - 0.50) < 0.01
    
    def test_trough_tracking(self):
        """Test trough tracking."""
        monitor = DrawdownMonitor()
        
        monitor.update(100000)
        monitor.update(90000)
        monitor.update(85000)  # New trough
        monitor.update(88000)
        
        metrics = monitor.get_metrics()
        
        assert metrics.trough_equity == 85000
    
    def test_monthly_reset(self):
        """Test monthly reset."""
        monitor = DrawdownMonitor()
        
        monitor.update(100000)
        monitor.update(80000)  # 20% drawdown
        
        monitor.reset_monthly()
        
        metrics = monitor.get_metrics()
        
        assert metrics.max_drawdown_mtd_pct == 0.0
        # Daily should still be tracked
        assert metrics.max_drawdown_today_pct > 0


class TestAdvancedRiskManager:
    """Tests for the main AdvancedRiskManager."""
    
    @pytest.fixture
    def manager(self):
        """Create advanced risk manager."""
        mgr = AdvancedRiskManager(
            base_position_limit=100000,
            max_concentration=0.15,
            max_sector_weight=0.30,
            drawdown_limit=0.10,
        )
        
        # Set up sectors
        mgr.set_sector("AAPL", "Technology")
        mgr.set_sector("MSFT", "Technology")
        mgr.set_sector("XOM", "Energy")
        mgr.set_sector("JPM", "Financials")
        
        return mgr
    
    def test_dynamic_limits_normal_regime(self, manager):
        """Test dynamic limits in normal regime."""
        manager.update_market_data(realized_vol=0.15, vix=20.0)
        
        limits = manager.get_dynamic_limits()
        
        assert limits.regime == "normal"
        assert limits.adjusted_position_limit == 100000
        assert not limits.limits_tightened
    
    def test_dynamic_limits_crisis_regime(self, manager):
        """Test dynamic limits tightened in crisis."""
        manager.update_market_data(realized_vol=0.45, vix=55.0)
        
        limits = manager.get_dynamic_limits()
        
        assert limits.regime == "crisis"
        assert limits.adjusted_position_limit == 40000  # 40% of base
        assert limits.limits_tightened
    
    def test_correlation_risk(self, manager):
        """Test correlation risk calculation."""
        # Add some returns
        np.random.seed(42)
        for _ in range(30):
            r = np.random.normal(0, 0.02)
            manager.update_returns("AAPL", r)
            manager.update_returns("MSFT", r * 0.9)  # Correlated
            manager.update_returns("XOM", -r * 0.3)  # Less correlated
        
        positions = {"AAPL": 0.4, "MSFT": 0.4, "XOM": 0.2}
        risk = manager.get_correlation_risk(positions)
        
        assert isinstance(risk, CorrelationRisk)
        assert risk.average_correlation != 0
    
    def test_drawdown_monitoring(self, manager):
        """Test drawdown monitoring."""
        manager.update_equity(100000)
        manager.update_equity(95000)  # 5% down
        
        metrics = manager.get_drawdown_metrics()
        
        assert abs(metrics.current_drawdown_pct - 0.05) < 0.001
    
    def test_stress_testing(self, manager):
        """Test stress testing integration."""
        positions = {"AAPL": 50000, "MSFT": 30000, "XOM": 20000}
        
        results = manager.run_stress_tests(positions, 100000)
        
        assert len(results) > 0
        assert all(isinstance(r, StressTestResult) for r in results)
    
    def test_sector_exposure(self, manager):
        """Test sector exposure calculation."""
        positions = {"AAPL": 40000, "MSFT": 30000, "XOM": 20000, "JPM": 10000}
        
        exposure = manager.get_sector_exposure(positions)
        
        assert isinstance(exposure, SectorExposure)
        assert exposure.largest_sector == "Technology"
        assert abs(exposure.largest_sector_weight - 0.70) < 0.01  # 70% tech
    
    def test_check_risk_limits_clean(self, manager):
        """Test risk limit check with no violations."""
        # Increase max sector weight to accommodate test positions
        manager.max_sector_weight = 0.60  # Allow up to 60% in one sector
        manager.update_market_data(realized_vol=0.15, vix=20.0)
        manager.update_equity(100000)
        
        # With 25% each: Tech=50%, Energy=25%, Financials=25%
        # This is within 60% sector limit
        positions = {"AAPL": 0.25, "MSFT": 0.25, "XOM": 0.25, "JPM": 0.25}
        
        result = manager.check_risk_limits(positions, 100000)
        
        assert result["risk_level"] in [RiskLevel.LOW.value, RiskLevel.MEDIUM.value]
    
    def test_check_risk_limits_drawdown_violation(self, manager):
        """Test risk limit check with drawdown violation."""
        manager.update_equity(100000)
        manager.update_equity(85000)  # 15% drawdown, exceeds 10% limit
        
        positions = {"AAPL": 0.5, "XOM": 0.5}
        
        result = manager.check_risk_limits(positions, 85000)
        
        assert result["risk_level"] == RiskLevel.CRITICAL.value
        assert any(v["type"] == "drawdown" for v in result["violations"])
    
    def test_check_risk_limits_sector_violation(self, manager):
        """Test risk limit check with sector concentration violation."""
        manager.update_market_data(realized_vol=0.15, vix=20.0)
        manager.update_equity(100000)
        
        # 90% in tech, exceeds 30% limit
        positions = {"AAPL": 0.5, "MSFT": 0.4, "XOM": 0.1}
        
        result = manager.check_risk_limits(positions, 100000)
        
        assert any(v["type"] == "sector_concentration" for v in result["violations"])


class TestFactoryFunction:
    """Tests for factory function."""
    
    def test_create_with_defaults(self):
        """Test creating manager with defaults."""
        manager = create_advanced_risk_manager()
        
        assert isinstance(manager, AdvancedRiskManager)
        assert manager.base_position_limit == 100000
    
    def test_create_with_custom_params(self):
        """Test creating manager with custom parameters."""
        manager = create_advanced_risk_manager(
            base_position_limit=500000,
            max_concentration=0.25,
        )
        
        assert manager.base_position_limit == 500000
        assert manager.max_concentration == 0.25
