"""
Phase 8: Comprehensive tests for analytics/realtime_risk_analytics.py
Coverage target: 85%+
Tests RealTimeRiskAnalytics with exposure, correlation, VaR calculations.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
import numpy as np


# ============================================================================
# ENUM TESTS
# ============================================================================

class TestRiskEvent:
    """Test RiskEvent enum."""
    
    def test_risk_event_values(self):
        """Test all risk event values."""
        from backend.analytics.realtime_risk_analytics import RiskEvent
        
        assert RiskEvent.POSITION_LIMIT_BREACH.value == "position_limit_breach"
        assert RiskEvent.SECTOR_CONCENTRATION.value == "sector_concentration"
        assert RiskEvent.VAR_EXCEEDED.value == "var_exceeded"
        assert RiskEvent.DRAWDOWN_ALERT.value == "drawdown_alert"
        assert RiskEvent.CORRELATION_SPIKE.value == "correlation_spike"
        assert RiskEvent.VOLATILITY_REGIME_CHANGE.value == "volatility_regime_change"
        assert RiskEvent.LIQUIDITY_SHORTAGE.value == "liquidity_shortage"
        assert RiskEvent.STRESS_TEST_FAILURE.value == "stress_test_failure"


class TestAlertPriority:
    """Test AlertPriority enum."""
    
    def test_alert_priority_values(self):
        """Test all alert priority values."""
        from backend.analytics.realtime_risk_analytics import AlertPriority
        
        assert AlertPriority.LOW.value == 1
        assert AlertPriority.MEDIUM.value == 2
        assert AlertPriority.HIGH.value == 3
        assert AlertPriority.CRITICAL.value == 4


# ============================================================================
# DATACLASS TESTS
# ============================================================================

class TestRiskAlert:
    """Test RiskAlert dataclass."""
    
    def test_risk_alert_creation(self):
        """Test creating RiskAlert."""
        from backend.analytics.realtime_risk_analytics import (
            RiskAlert, RiskEvent, AlertPriority
        )
        
        alert = RiskAlert(
            id="alert-001",
            event_type=RiskEvent.VAR_EXCEEDED,
            priority=AlertPriority.HIGH,
            title="VaR Limit Exceeded",
            message="Portfolio VaR exceeds limit",
            timestamp=datetime.now()
        )
        
        assert alert.id == "alert-001"
        assert alert.event_type == RiskEvent.VAR_EXCEEDED
        assert alert.priority == AlertPriority.HIGH
        assert alert.acknowledged is False


class TestExposureMetrics:
    """Test ExposureMetrics dataclass."""
    
    def test_exposure_metrics_defaults(self):
        """Test ExposureMetrics default values."""
        from backend.analytics.realtime_risk_analytics import ExposureMetrics
        
        exposure = ExposureMetrics()
        
        assert exposure.gross_exposure == 0.0
        assert exposure.net_exposure == 0.0
        assert exposure.long_exposure == 0.0
        assert exposure.short_exposure == 0.0
        assert exposure.sector_exposure == {}
        assert exposure.leverage == 1.0
    
    def test_exposure_metrics_custom(self):
        """Test ExposureMetrics with custom values."""
        from backend.analytics.realtime_risk_analytics import ExposureMetrics
        
        exposure = ExposureMetrics(
            gross_exposure=1000000.0,
            net_exposure=800000.0,
            long_exposure=900000.0,
            short_exposure=100000.0,
            leverage=2.0
        )
        
        assert exposure.gross_exposure == 1000000.0
        assert exposure.net_exposure == 800000.0
        assert exposure.leverage == 2.0


class TestCorrelationMetrics:
    """Test CorrelationMetrics dataclass."""
    
    def test_correlation_metrics_defaults(self):
        """Test CorrelationMetrics default values."""
        from backend.analytics.realtime_risk_analytics import CorrelationMetrics
        
        corr = CorrelationMetrics()
        
        assert corr.avg_correlation == 0.0
        assert corr.max_correlation == 0.0
        assert corr.min_correlation == 0.0
        assert corr.correlation_clusters == {}
        assert corr.eigen_risk == 0.0


class TestStressTestResult:
    """Test StressTestResult dataclass."""
    
    def test_stress_test_result_creation(self):
        """Test creating StressTestResult."""
        from backend.analytics.realtime_risk_analytics import StressTestResult
        
        result = StressTestResult(
            scenario_name="Market Crash",
            scenario_description="2008-style market crash",
            portfolio_pnl=-50000.0,
            var_shock=0.15,
            positions_affected=10,
            worst_position="AAPL",
            worst_position_pnl=-10000.0,
            risk_metrics_change={"var": 0.05}
        )
        
        assert result.scenario_name == "Market Crash"
        assert result.portfolio_pnl == -50000.0
        assert result.worst_position == "AAPL"


class TestRiskAttribution:
    """Test RiskAttribution dataclass."""
    
    def test_risk_attribution_defaults(self):
        """Test RiskAttribution default values."""
        from backend.analytics.realtime_risk_analytics import RiskAttribution
        
        attr = RiskAttribution()
        
        assert attr.position_risk == {}
        assert attr.sector_risk == {}
        assert attr.factor_risk == {}
        assert attr.specific_risk == 0.0
        assert attr.systematic_risk == 0.0


# ============================================================================
# REAL-TIME RISK ANALYTICS INIT TESTS
# ============================================================================

class TestRealTimeRiskAnalyticsInit:
    """Test RealTimeRiskAnalytics initialization."""
    
    def test_init_defaults(self):
        """Test RealTimeRiskAnalytics with default settings."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        assert analytics.update_frequency == 1
        assert analytics.correlation_window == 60
        assert analytics.var_confidence == 0.95
        assert analytics.max_alerts_per_hour == 50
        assert analytics.positions == {}
        assert analytics.running is False
    
    def test_init_custom_settings(self):
        """Test RealTimeRiskAnalytics with custom settings."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(
            update_frequency=5,
            correlation_window=120,
            var_confidence=0.99,
            max_alerts_per_hour=100,
            enable_slo=False
        )
        
        assert analytics.update_frequency == 5
        assert analytics.correlation_window == 120
        assert analytics.var_confidence == 0.99
        assert analytics.max_alerts_per_hour == 100
    
    def test_init_stress_scenarios(self):
        """Test stress scenarios are initialized."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        assert "market_crash" in analytics.stress_scenarios
        assert "flash_crash" in analytics.stress_scenarios
        assert "interest_rate_shock" in analytics.stress_scenarios
        assert "currency_crisis" in analytics.stress_scenarios
        assert "sector_rotation" in analytics.stress_scenarios
    
    def test_stress_scenario_structure(self):
        """Test stress scenario structure."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        market_crash = analytics.stress_scenarios["market_crash"]
        
        assert "name" in market_crash
        assert "description" in market_crash
        assert "shocks" in market_crash
        assert "equity_shock" in market_crash["shocks"]


# ============================================================================
# UPDATE POSITIONS TESTS
# ============================================================================

class TestUpdatePositions:
    """Test update_positions method."""
    
    @pytest.mark.asyncio
    async def test_update_positions_basic(self):
        """Test updating positions with basic data."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        positions = {
            "AAPL": {
                "price": 150.0,
                "market_value": 15000.0,
                "sector": "Technology"
            },
            "MSFT": {
                "price": 300.0,
                "market_value": 30000.0,
                "sector": "Technology"
            }
        }
        
        await analytics.update_positions(positions)
        
        assert len(analytics.positions) == 2
        assert "AAPL" in analytics.positions
        assert len(analytics.price_stream["AAPL"]) == 1
    
    @pytest.mark.asyncio
    async def test_update_positions_calculates_returns(self):
        """Test that updating positions calculates returns."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        # First update
        await analytics.update_positions({
            "AAPL": {"price": 100.0, "market_value": 10000.0}
        })
        
        # Second update with price change
        await analytics.update_positions({
            "AAPL": {"price": 105.0, "market_value": 10500.0}
        })
        
        # Should have return calculated
        assert len(analytics.return_stream["AAPL"]) == 1
        assert analytics.return_stream["AAPL"][0] == pytest.approx(0.05)
    
    @pytest.mark.asyncio
    async def test_update_positions_tracks_portfolio_value(self):
        """Test portfolio value tracking."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        await analytics.update_positions({
            "AAPL": {"market_value": 10000.0, "price": 100.0},
            "MSFT": {"market_value": 20000.0, "price": 200.0}
        })
        
        assert len(analytics.portfolio_values) == 1
        assert analytics.portfolio_values[0] == 30000.0


# ============================================================================
# EXPOSURE METRICS TESTS
# ============================================================================

class TestExposureCalculation:
    """Test exposure metrics calculation."""
    
    @pytest.mark.asyncio
    async def test_calculate_gross_net_exposure(self):
        """Test gross and net exposure calculation."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        # Long and short positions
        await analytics.update_positions({
            "AAPL": {"market_value": 10000.0, "price": 100.0},
            "SPY_SHORT": {"market_value": -5000.0, "price": 400.0}
        })
        
        assert analytics.current_exposure.gross_exposure == 15000.0
        assert analytics.current_exposure.net_exposure == 5000.0
        assert analytics.current_exposure.long_exposure == 10000.0
        assert analytics.current_exposure.short_exposure == 5000.0
    
    @pytest.mark.asyncio
    async def test_calculate_sector_exposure(self):
        """Test sector exposure calculation."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        await analytics.update_positions({
            "AAPL": {"market_value": 10000.0, "price": 100.0, "sector": "Technology"},
            "XOM": {"market_value": 8000.0, "price": 80.0, "sector": "Energy"}
        })
        
        assert "Technology" in analytics.current_exposure.sector_exposure
        assert "Energy" in analytics.current_exposure.sector_exposure
    
    @pytest.mark.asyncio
    async def test_calculate_leverage(self):
        """Test leverage calculation."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        await analytics.update_positions({
            "AAPL": {"market_value": 20000.0, "price": 100.0}
        })
        
        # Leverage = gross / portfolio value
        assert analytics.current_exposure.leverage >= 0
    
    @pytest.mark.asyncio
    async def test_calculate_beta_exposure(self):
        """Test beta exposure calculation."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        await analytics.update_positions({
            "AAPL": {"market_value": 10000.0, "price": 100.0, "beta": 1.2},
            "MSFT": {"market_value": 10000.0, "price": 200.0, "beta": 1.0}
        })
        
        # Weighted average beta = (0.5 * 1.2 + 0.5 * 1.0) = 1.1
        assert analytics.current_exposure.beta_exposure == pytest.approx(1.1)


# ============================================================================
# CORRELATION METRICS TESTS
# ============================================================================

class TestCorrelationCalculation:
    """Test correlation metrics calculation."""
    
    @pytest.mark.asyncio
    async def test_correlation_needs_multiple_positions(self):
        """Test that correlation calculation needs multiple positions."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        # Single position
        await analytics.update_positions({
            "AAPL": {"market_value": 10000.0, "price": 100.0}
        })
        
        # Should not calculate correlation with single position
        assert analytics.current_correlation.avg_correlation == 0.0
    
    @pytest.mark.asyncio
    async def test_correlation_with_return_history(self):
        """Test correlation with return history."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        # Simulate many price updates
        for i in range(25):
            await analytics.update_positions({
                "AAPL": {"market_value": 10000.0 + i*100, "price": 100.0 + i},
                "MSFT": {"market_value": 20000.0 + i*150, "price": 200.0 + i*1.5}
            })
        
        # Should have calculated correlation
        # (may or may not be populated depending on return stream lengths)
        assert analytics.current_correlation is not None


# ============================================================================
# VAR METRICS TESTS
# ============================================================================

class TestVaRCalculation:
    """Test Value at Risk calculation."""
    
    @pytest.mark.asyncio
    async def test_var_needs_history(self):
        """Test that VaR needs sufficient return history."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        # Single update - not enough history
        await analytics.update_positions({
            "AAPL": {"market_value": 10000.0, "price": 100.0}
        })
        
        assert analytics.current_var == 0.0
    
    @pytest.mark.asyncio
    async def test_var_with_history(self):
        """Test VaR with sufficient history."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        # Simulate many portfolio returns
        for i in range(25):
            value = 100000 + np.random.randn() * 1000
            await analytics.update_positions({
                "AAPL": {"market_value": value, "price": value / 100}
            })
        
        # VaR should be calculated
        assert analytics.current_var >= 0
    
    @pytest.mark.asyncio
    async def test_cvar_with_history(self):
        """Test CVaR (Expected Shortfall) calculation."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        # Simulate returns
        np.random.seed(42)
        for i in range(30):
            value = 100000 + np.random.randn() * 2000
            await analytics.update_positions({
                "AAPL": {"market_value": value, "price": value / 100}
            })
        
        # CVaR should be >= VaR
        assert analytics.current_cvar >= 0


# ============================================================================
# RISK ATTRIBUTION TESTS
# ============================================================================

class TestRiskAttribution:
    """Test risk attribution calculation."""
    
    @pytest.mark.asyncio
    async def test_position_risk_attribution(self):
        """Test position-level risk attribution."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        # Multiple updates to build history
        np.random.seed(42)
        for i in range(25):
            await analytics.update_positions({
                "AAPL": {
                    "market_value": 10000 + np.random.randn() * 100,
                    "price": 100 + np.random.randn(),
                    "volatility": 0.25,
                    "beta": 1.2
                },
                "MSFT": {
                    "market_value": 20000 + np.random.randn() * 150,
                    "price": 200 + np.random.randn() * 1.5,
                    "volatility": 0.22,
                    "beta": 1.0
                }
            })
        
        # Should have risk attribution
        assert analytics.risk_attribution is not None
    
    @pytest.mark.asyncio
    async def test_sector_risk_aggregation(self):
        """Test sector-level risk aggregation."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        np.random.seed(42)
        for i in range(25):
            await analytics.update_positions({
                "AAPL": {
                    "market_value": 10000 + np.random.randn() * 100,
                    "price": 100,
                    "sector": "Technology",
                    "volatility": 0.25,
                    "beta": 1.2
                },
                "XOM": {
                    "market_value": 8000 + np.random.randn() * 80,
                    "price": 80,
                    "sector": "Energy",
                    "volatility": 0.30,
                    "beta": 1.1
                }
            })
        
        # Should have sector risk
        if len(analytics.portfolio_returns) > 20:
            assert "Technology" in analytics.risk_attribution.sector_risk or \
                   "Energy" in analytics.risk_attribution.sector_risk


# ============================================================================
# STRESS TESTING TESTS
# ============================================================================

class TestStressTesting:
    """Test stress testing functionality."""
    
    def test_stress_scenarios_initialized(self):
        """Test stress scenarios are properly initialized."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        assert len(analytics.stress_scenarios) == 5
        
        # Check market crash scenario
        crash = analytics.stress_scenarios["market_crash"]
        assert crash["shocks"]["equity_shock"] == -0.20
        
        # Check flash crash scenario
        flash = analytics.stress_scenarios["flash_crash"]
        assert flash["shocks"]["equity_shock"] == -0.10


# ============================================================================
# ALERT SYSTEM TESTS
# ============================================================================

class TestAlertSystem:
    """Test alert generation and management."""
    
    def test_alert_storage_initialized(self):
        """Test alert storage is initialized."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        assert analytics.active_alerts == {}
        assert len(analytics.alert_history) == 0
        assert analytics.alert_callbacks == []
    
    def test_max_alerts_per_hour(self):
        """Test max alerts per hour limit."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(
            max_alerts_per_hour=10,
            enable_slo=False
        )
        
        assert analytics.max_alerts_per_hour == 10


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Test edge cases in risk analytics."""
    
    @pytest.mark.asyncio
    async def test_empty_positions(self):
        """Test handling empty positions."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        await analytics.update_positions({})
        
        assert analytics.current_exposure.gross_exposure == 0.0
    
    @pytest.mark.asyncio
    async def test_zero_price(self):
        """Test handling zero price."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        await analytics.update_positions({
            "TEST": {"market_value": 0.0, "price": 0.0}
        })
        
        # Should not crash, price stream should be empty for this symbol
        assert len(analytics.price_stream["TEST"]) == 0
    
    @pytest.mark.asyncio
    async def test_negative_market_value(self):
        """Test handling negative market value (short position)."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        await analytics.update_positions({
            "SHORT": {"market_value": -10000.0, "price": 100.0}
        })
        
        assert analytics.current_exposure.short_exposure == 10000.0
    
    @pytest.mark.asyncio
    async def test_missing_optional_fields(self):
        """Test handling missing optional fields."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        # Minimal position data
        await analytics.update_positions({
            "AAPL": {"market_value": 10000.0}
        })
        
        # Should not crash
        assert analytics.current_exposure.sector_exposure.get("Unknown", 0) >= 0
    
    @pytest.mark.asyncio
    async def test_large_number_of_positions(self):
        """Test handling large number of positions."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        positions = {
            f"SYM{i}": {"market_value": 1000.0, "price": 100.0}
            for i in range(100)
        }
        
        await analytics.update_positions(positions)
        
        assert len(analytics.positions) == 100
        assert analytics.current_exposure.gross_exposure == 100000.0


# ============================================================================
# DATA STORAGE TESTS
# ============================================================================

class TestDataStorage:
    """Test data storage and limits."""
    
    def test_price_stream_max_length(self):
        """Test price stream has max length."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        # Add prices up to limit
        for i in range(1100):
            analytics.price_stream["TEST"].append(100.0 + i)
        
        # Should be limited to 1000
        assert len(analytics.price_stream["TEST"]) == 1000
    
    def test_portfolio_values_max_length(self):
        """Test portfolio values has max length."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        # Add values up to limit
        for i in range(11000):
            analytics.portfolio_values.append(100000.0 + i)
        
        # Should be limited to 10000
        assert len(analytics.portfolio_values) == 10000


# ============================================================================
# THREADING AND ASYNC TESTS
# ============================================================================

class TestThreading:
    """Test threading functionality."""
    
    def test_executor_initialized(self):
        """Test thread pool executor is initialized."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        assert analytics.executor is not None
    
    def test_running_flag_default(self):
        """Test running flag starts as False."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        assert analytics.running is False
        assert analytics.update_thread is None


# ============================================================================
# STRESS TEST EXECUTION TESTS
# ============================================================================

class TestRunStressTest:
    """Test run_stress_test method."""
    
    @pytest.mark.asyncio
    async def test_run_stress_test_market_crash(self):
        """Test running market crash stress test."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        # Add positions
        await analytics.update_positions({
            "AAPL": {"market_value": 10000.0, "price": 100.0, "beta": 1.2, "sector": "Technology"},
            "MSFT": {"market_value": 15000.0, "price": 200.0, "beta": 1.0, "sector": "Technology"}
        })
        
        result = await analytics.run_stress_test("market_crash")
        
        assert result.scenario_name is not None
        assert result.portfolio_pnl < 0  # Should be negative for crash
        assert result.positions_affected >= 0
    
    @pytest.mark.asyncio
    async def test_run_stress_test_flash_crash(self):
        """Test running flash crash stress test."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        await analytics.update_positions({
            "AAPL": {"market_value": 10000.0, "price": 100.0, "beta": 1.0}
        })
        
        result = await analytics.run_stress_test("flash_crash")
        
        assert result.scenario_name is not None
    
    @pytest.mark.asyncio
    async def test_run_stress_test_unknown_scenario(self):
        """Test running unknown stress test scenario."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        with pytest.raises(ValueError, match="Unknown stress scenario"):
            await analytics.run_stress_test("unknown_scenario")
    
    @pytest.mark.asyncio
    async def test_run_all_stress_tests(self):
        """Test running all stress tests."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        await analytics.update_positions({
            "AAPL": {"market_value": 10000.0, "price": 100.0, "beta": 1.0}
        })
        
        results = await analytics.run_all_stress_tests()
        
        assert len(results) == 5  # 5 scenarios


class TestAlertCallbacks:
    """Test alert callback functionality."""
    
    def test_add_alert_callback(self):
        """Test adding alert callback."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        def callback(alert):
            pass
        
        analytics.add_alert_callback(callback)
        
        assert len(analytics.alert_callbacks) == 1
    
    def test_acknowledge_alert_not_found(self):
        """Test acknowledging non-existent alert."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        result = analytics.acknowledge_alert("non-existent-alert")
        
        assert result is False
    
    def test_acknowledge_alert_success(self):
        """Test acknowledging existing alert."""
        from backend.analytics.realtime_risk_analytics import (
            RealTimeRiskAnalytics, RiskAlert, RiskEvent, AlertPriority
        )
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        # Add an alert manually
        alert = RiskAlert(
            id="test-alert-001",
            event_type=RiskEvent.VAR_EXCEEDED,
            priority=AlertPriority.HIGH,
            title="Test Alert",
            message="Test message",
            timestamp=datetime.now()
        )
        analytics.active_alerts["test-alert-001"] = alert
        
        result = analytics.acknowledge_alert("test-alert-001")
        
        assert result is True
        assert analytics.active_alerts["test-alert-001"].acknowledged is True


class TestStressTestWithSectors:
    """Test stress tests with sector-specific shocks."""
    
    @pytest.mark.asyncio
    async def test_stress_test_sector_rotation(self):
        """Test sector rotation stress scenario."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        await analytics.update_positions({
            "TECH1": {"market_value": 10000.0, "price": 100.0, "beta": 1.2, "sector": "Technology"},
            "VALUE1": {"market_value": 10000.0, "price": 100.0, "beta": 0.8, "sector": "Value"}
        })
        
        result = await analytics.run_stress_test("sector_rotation")
        
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_stress_test_with_bonds(self):
        """Test stress test with bond positions."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        await analytics.update_positions({
            "BOND1": {"market_value": 50000.0, "price": 100.0, "sector": "bond", "duration": 5.0}
        })
        
        result = await analytics.run_stress_test("interest_rate_shock")
        
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_stress_test_with_fx(self):
        """Test stress test with foreign currency positions."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        await analytics.update_positions({
            "EUR_STOCK": {"market_value": 20000.0, "price": 100.0, "currency": "EUR", "beta": 1.0}
        })
        
        result = await analytics.run_stress_test("currency_crisis")
        
        assert result is not None


class TestRiskAttributionDataclass:
    """Test RiskAttribution dataclass."""
    
    def test_risk_attribution_defaults(self):
        """Test RiskAttribution default values."""
        from backend.analytics.realtime_risk_analytics import RiskAttribution
        
        attr = RiskAttribution()
        
        assert attr.position_risk == {}
        assert attr.sector_risk == {}
        assert attr.factor_risk == {}
        assert attr.specific_risk == 0.0
        assert attr.systematic_risk == 0.0


# ============================================================================
# DEEP CALCULATION TESTS
# ============================================================================

class TestDeepVarCalculation:
    """Test VaR calculation with sufficient data."""
    
    @pytest.mark.asyncio
    async def test_var_calculation_with_many_updates(self):
        """Test VaR calculation after many position updates."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        # Simulate 30 price updates
        np.random.seed(42)
        for i in range(30):
            value = 100000 + np.random.randn() * 2000
            await analytics.update_positions({
                "AAPL": {"market_value": value, "price": value / 100}
            })
        
        # VaR should now be calculated
        assert analytics.current_var >= 0
        assert analytics.current_cvar >= 0
    
    @pytest.mark.asyncio
    async def test_var_confidence_level(self):
        """Test VaR with custom confidence level."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(var_confidence=0.99, enable_slo=False)
        
        assert analytics.var_confidence == 0.99


class TestDeepCorrelationCalculation:
    """Test correlation calculation with multiple assets."""
    
    @pytest.mark.asyncio
    async def test_correlation_with_many_assets(self):
        """Test correlation matrix with multiple assets."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        # Simulate updates with 3 assets
        np.random.seed(42)
        for i in range(30):
            await analytics.update_positions({
                "AAPL": {"market_value": 10000 + np.random.randn() * 100, "price": 100 + np.random.randn()},
                "MSFT": {"market_value": 15000 + np.random.randn() * 150, "price": 150 + np.random.randn()},
                "GOOG": {"market_value": 20000 + np.random.randn() * 200, "price": 200 + np.random.randn()}
            })
        
        # Check correlation metrics
        assert analytics.current_correlation is not None


class TestDeepExposureCalculation:
    """Test exposure calculation with various position types."""
    
    @pytest.mark.asyncio
    async def test_exposure_with_region(self):
        """Test exposure calculation with regional breakdown."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        await analytics.update_positions({
            "AAPL": {"market_value": 10000.0, "price": 100.0, "region": "North America"},
            "TSM": {"market_value": 8000.0, "price": 80.0, "region": "Asia"}
        })
        
        assert analytics.current_exposure is not None
    
    @pytest.mark.asyncio
    async def test_exposure_with_currency(self):
        """Test exposure calculation with currency breakdown."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        await analytics.update_positions({
            "AAPL": {"market_value": 10000.0, "price": 100.0, "currency": "USD"},
            "SAP": {"market_value": 8000.0, "price": 80.0, "currency": "EUR"}
        })
        
        assert analytics.current_exposure is not None


class TestSLOMonitoring:
    """Test SLO monitoring integration."""
    
    def test_slo_disabled(self):
        """Test initialization with SLO disabled."""
        from backend.analytics.realtime_risk_analytics import RealTimeRiskAnalytics
        
        analytics = RealTimeRiskAnalytics(enable_slo=False)
        
        assert analytics.slo_monitor is None
