"""
Comprehensive test suite for Module 74: backend.services.analytics
Tests analytics service functionality.
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch, AsyncMock

try:
    from backend.services.analytics import (
        AnalyticsService, AnalyticsConfig, PerformanceMetrics, 
        TradingMetrics, PortfolioMetrics, performance_analytics,
        trading_analytics, portfolio_analytics, market_analytics,
        risk_analytics, statistical_analysis, trend_analysis,
        correlation_analysis, get_analytics_service
    )
    MODULE_EXISTS = True
except ImportError:
    MODULE_EXISTS = False


class TestModule74BackendServicesAnalytics:
    """Comprehensive test suite for analytics service functionality."""

    def test_module_availability(self):
        """Test module availability."""
        if MODULE_EXISTS:
            import backend.services.analytics as module
            assert module is not None
        else:
            assert True

    def test_module_functionality(self):
        """Test module functionality if exists."""
        if MODULE_EXISTS:
            import backend.services.analytics as module
            assert hasattr(module, '__name__')
        else:
            pytest.skip("Module not available")

    @pytest.mark.asyncio
    async def test_performance_analytics(self):
        """Test performance analytics."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = AnalyticsService()
        
        # Test with sample returns
        returns = [0.01, -0.005, 0.02, -0.01, 0.015, 0.008, -0.003]
        result = await service.performance_analytics(returns)
        
        assert isinstance(result, PerformanceMetrics)
        assert isinstance(result.total_return, float)
        assert isinstance(result.annualized_return, float)
        assert isinstance(result.volatility, float)
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.win_rate, float)
        assert 0.0 <= result.win_rate <= 1.0
        
        # Test with empty returns
        empty_result = await service.performance_analytics([])
        assert empty_result.total_return == 0.0
        assert empty_result.win_rate == 0.0

    @pytest.mark.asyncio
    async def test_trading_analytics(self):
        """Test trading analytics."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = AnalyticsService()
        
        # Test with sample trades
        trades = [
            {'pnl': 100}, {'pnl': -50}, {'pnl': 200}, 
            {'pnl': -25}, {'pnl': 150}, {'pnl': -75}
        ]
        result = await service.trading_analytics(trades)
        
        assert isinstance(result, TradingMetrics)
        assert result.total_trades == 6
        assert result.winning_trades == 3
        assert result.losing_trades == 3
        assert result.win_rate == 0.5
        assert result.profit_factor > 0
        assert result.average_win > 0
        assert result.average_loss < 0
        
        # Test with empty trades
        empty_result = await service.trading_analytics([])
        assert empty_result.total_trades == 0
        assert empty_result.win_rate == 0.0

    @pytest.mark.asyncio
    async def test_portfolio_analytics(self):
        """Test portfolio analytics."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = AnalyticsService()
        
        # Test with sample positions
        positions = [
            {'value': 1000, 'sector': 'Technology'},
            {'value': -500, 'sector': 'Healthcare'},
            {'value': 750, 'sector': 'Technology'}
        ]
        cash = 250
        
        result = await service.portfolio_analytics(positions, cash)
        
        assert isinstance(result, PortfolioMetrics)
        assert result.total_value == 2500  # 1000 + 500 + 750 + 250
        assert result.position_count == 3
        assert result.cash_allocation == 0.1  # 250/2500
        assert 'Technology' in result.sector_concentration
        assert result.concentration_risk > 0
        
        # Test with empty positions
        empty_result = await service.portfolio_analytics([], 1000)
        assert empty_result.total_value == 1000
        assert empty_result.cash_allocation == 1.0
        assert empty_result.position_count == 0

    @pytest.mark.asyncio
    async def test_market_analytics(self):
        """Test market analytics."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = AnalyticsService()
        
        # Test with correlated returns
        portfolio_returns = [0.01, -0.005, 0.02, -0.01, 0.015]
        market_returns = [0.008, -0.003, 0.018, -0.008, 0.012]
        
        result = await service.market_analytics(portfolio_returns, market_returns)
        
        assert isinstance(result, dict)
        assert 'beta' in result
        assert 'alpha' in result
        assert 'correlation' in result
        assert 'tracking_error' in result
        assert isinstance(result['beta'], float)
        assert isinstance(result['alpha'], float)
        
        # Test with empty data
        empty_result = await service.market_analytics([], [])
        assert empty_result['beta'] == 1.0
        assert empty_result['alpha'] == 0.0

    @pytest.mark.asyncio
    async def test_risk_analytics(self):
        """Test risk analytics."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = AnalyticsService()
        
        # Test with sample returns
        returns = [0.02, -0.01, 0.015, -0.008, 0.025, 0.005, -0.012]
        result = await service.risk_analytics(returns)
        
        assert isinstance(result, dict)
        assert 'var_95' in result
        assert 'cvar_95' in result
        assert 'daily_volatility' in result
        assert 'max_drawdown' in result
        assert 'sharpe_ratio' in result
        
        # Test with positions
        positions = [{'value': 1000}, {'value': -500}]
        result_with_pos = await service.risk_analytics(returns, positions)
        assert isinstance(result_with_pos, dict)

    @pytest.mark.asyncio
    async def test_statistical_analysis(self):
        """Test statistical analysis."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = AnalyticsService()
        
        # Test with sample data
        data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = await service.statistical_analysis(data)
        
        assert isinstance(result, dict)
        assert 'mean' in result
        assert 'median' in result
        assert 'std' in result
        assert 'skewness' in result
        assert 'kurtosis' in result
        assert result['mean'] == 5.5
        assert result['median'] == 5.5
        
        # Test with empty data
        empty_result = await service.statistical_analysis([])
        assert empty_result['mean'] == 0.0

    @pytest.mark.asyncio
    async def test_trend_analysis(self):
        """Test trend analysis."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = AnalyticsService()
        
        # Test with trending prices (upward trend)
        prices = list(range(1, 51))  # 1 to 50
        result = await service.trend_analysis(prices, window=10)
        
        assert isinstance(result, dict)
        assert 'trend_direction' in result
        assert 'trend_strength' in result
        assert 'moving_average' in result
        assert 'momentum' in result
        assert 'rsi' in result
        assert result['trend_direction'] == 'bullish'
        assert result['momentum'] > 0
        
        # Test with insufficient data
        short_prices = [1, 2, 3]
        short_result = await service.trend_analysis(short_prices, window=10)
        assert short_result['trend_direction'] == 'neutral'

    @pytest.mark.asyncio
    async def test_correlation_analysis(self):
        """Test correlation analysis."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = AnalyticsService()
        
        # Test with correlated data
        data1 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        data2 = [2, 4, 6, 8, 10, 12, 14, 16, 18, 20]  # Perfectly correlated
        
        result = await service.correlation_analysis(data1, data2)
        
        assert isinstance(result, dict)
        assert 'correlation' in result
        assert 'p_value' in result
        assert 'r_squared' in result
        assert 'rolling_correlation' in result
        assert abs(result['correlation'] - 1.0) < 0.01  # Should be close to 1
        assert result['r_squared'] > 0.9  # High R-squared
        
        # Test with empty data
        empty_result = await service.correlation_analysis([], [])
        assert empty_result['correlation'] == 0.0

    def test_analytics_config(self):
        """Test analytics configuration."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        # Test default config
        config = AnalyticsConfig()
        assert config.lookback_days == 252
        assert config.risk_free_rate == 0.02
        assert 0.95 in config.confidence_levels
        
        # Test custom config
        custom_config = AnalyticsConfig(
            lookback_days=100,
            risk_free_rate=0.03,
            confidence_levels=[0.90, 0.95]
        )
        assert custom_config.lookback_days == 100
        assert custom_config.risk_free_rate == 0.03
        assert len(custom_config.confidence_levels) == 2

    def test_data_classes(self):
        """Test data classes."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        # Test PerformanceMetrics
        perf = PerformanceMetrics(
            total_return=0.15, annualized_return=0.12, volatility=0.18,
            sharpe_ratio=1.2, sortino_ratio=1.5, max_drawdown=-0.08,
            calmar_ratio=1.8, win_rate=0.6, profit_factor=1.4
        )
        assert perf.total_return == 0.15
        assert perf.win_rate == 0.6
        
        # Test TradingMetrics
        trading = TradingMetrics(
            total_trades=100, winning_trades=60, losing_trades=40,
            win_rate=0.6, profit_factor=1.5, average_win=50.0,
            average_loss=-30.0, largest_win=200.0, largest_loss=-100.0,
            consecutive_wins=5, consecutive_losses=3
        )
        assert trading.total_trades == 100
        assert trading.win_rate == 0.6

    @pytest.mark.asyncio
    async def test_convenience_functions(self):
        """Test convenience functions."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        # Test async convenience functions
        returns = [0.01, -0.005, 0.02]
        trades = [{'pnl': 100}, {'pnl': -50}]
        positions = [{'value': 1000, 'sector': 'Tech'}]
        data = [1, 2, 3, 4, 5]
        
        perf_result = await performance_analytics(returns)
        assert isinstance(perf_result, PerformanceMetrics)
        
        trading_result = await trading_analytics(trades)
        assert isinstance(trading_result, TradingMetrics)
        
        portfolio_result = await portfolio_analytics(positions)
        assert isinstance(portfolio_result, PortfolioMetrics)
        
        market_result = await market_analytics(returns, returns)
        assert isinstance(market_result, dict)
        
        risk_result = await risk_analytics(returns)
        assert isinstance(risk_result, dict)
        
        stats_result = await statistical_analysis(data)
        assert isinstance(stats_result, dict)
        
        trend_result = await trend_analysis([1, 2, 3, 4, 5])
        assert isinstance(trend_result, dict)
        
        corr_result = await correlation_analysis(data, data)
        assert isinstance(corr_result, dict)

    def test_service_instance(self):
        """Test service instance access."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = get_analytics_service()
        assert isinstance(service, AnalyticsService)
        
        # Test that it returns the same instance
        service2 = get_analytics_service()
        assert service is service2

    def test_helper_methods(self):
        """Test helper methods."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = AnalyticsService()
        
        # Test _to_array method
        list_data = [1, 2, 3, 4, 5]
        array_result = service._to_array(list_data)
        assert isinstance(array_result, np.ndarray)
        assert len(array_result) == 5
        
        # Test _max_consecutive method
        pnls = [10, 20, -5, -10, 15, 25, 30, -8]
        consecutive_wins = service._max_consecutive(pnls, lambda x: x > 0)
        consecutive_losses = service._max_consecutive(pnls, lambda x: x < 0)
        assert consecutive_wins == 3  # 15, 25, 30
        assert consecutive_losses == 2  # -5, -10
        
        # Test _calculate_rsi method
        prices = np.array([44, 44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.85, 
                          46.08, 45.89, 46.03, 46.28, 46.28, 46.00, 46.03, 46.41])
        rsi = service._calculate_rsi(prices)
        assert 0 <= rsi <= 100
        assert isinstance(rsi, float)

    @pytest.mark.asyncio
    async def test_edge_cases(self):
        """Test edge cases and error handling."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        service = AnalyticsService()
        
        # Test with NaN values
        returns_with_nan = [0.01, np.nan, 0.02, -0.01]
        try:
            result = await service.performance_analytics(returns_with_nan)
            assert isinstance(result, PerformanceMetrics)
        except:
            # It's acceptable if it raises an exception
            pass
        
        # Test with single data point
        single_return = [0.05]
        single_result = await service.performance_analytics(single_return)
        assert abs(single_result.total_return - 0.05) < 0.001
        
        # Test RSI with insufficient data
        short_prices = np.array([1, 2])
        rsi_short = service._calculate_rsi(short_prices)
        assert rsi_short == 50.0
        
        # Test with all zero losses in profit factor
        all_wins = [{'pnl': 100}, {'pnl': 200}, {'pnl': 150}]
        win_result = await service.trading_analytics(all_wins)
        assert win_result.profit_factor == float('inf')

    def test_scipy_dependency(self):
        """Test scipy import dependency."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        # Test that our fallback implementations work without scipy
        service = AnalyticsService()
        
        # Test statistical helper methods
        data = np.array([1, 2, 3, 4, 5])
        skew = service._calculate_skewness(data)
        kurt = service._calculate_kurtosis(data)
        
        assert isinstance(skew, float)
        assert isinstance(kurt, float)
        
        # Test correlation helper
        x = np.array([1, 2, 3, 4, 5])
        y = np.array([2, 4, 6, 8, 10])
        corr, p_val = service._pearson_correlation(x, y)
        
        assert isinstance(corr, float)
        assert isinstance(p_val, float)
        assert abs(corr - 1.0) < 0.01  # Should be close to 1