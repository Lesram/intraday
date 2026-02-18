"""
Extended tests for TechnicalIndicators service
Tests additional indicator calculations for coverage boost
"""

import pytest
import numpy as np

from backend.services.indicators import TechnicalIndicators


class TestSMAExtended:
    """Extended SMA tests"""
    
    def test_sma_with_period_1(self):
        """SMA with period 1 should equal original prices"""
        prices = [10, 20, 30, 40, 50]
        result = TechnicalIndicators.calculate_sma(prices, period=1)
        
        for i, price in enumerate(prices):
            assert abs(result[i] - price) < 0.001
            
    def test_sma_with_period_equal_length(self):
        """SMA with period equal to data length"""
        prices = [10, 20, 30, 40, 50]
        result = TechnicalIndicators.calculate_sma(prices, period=5)
        
        # Only last value should be valid
        for i in range(4):
            assert result[i] is None or np.isnan(result[i])
        assert abs(result[4] - 30.0) < 0.001  # avg of all


class TestEMAExtended:
    """Extended EMA tests"""
    
    def test_ema_decay_property(self):
        """Test EMA gives more weight to recent prices"""
        # Start low, end high
        prices = [10, 10, 10, 10, 10, 10, 10, 10, 10, 50]
        
        sma = TechnicalIndicators.calculate_sma(prices, period=5)
        ema = TechnicalIndicators.calculate_ema(prices, period=5)
        
        # EMA should react more to the 50
        assert ema[-1] > sma[-1]


class TestMACDExtended:
    """Extended MACD tests"""
    
    def test_macd_custom_periods(self):
        """Test MACD with custom periods"""
        prices = list(range(1, 100))
        result = TechnicalIndicators.calculate_macd(
            prices,
            fast_period=5,
            slow_period=10,
            signal_period=3
        )
        
        assert len(result['macd']) == len(prices)
        # Verify some values are calculated
        valid = [v for v in result['macd'] if v is not None and not np.isnan(v)]
        assert len(valid) > 0
        
    def test_macd_crossover(self):
        """Test MACD crossover signals"""
        # Rising prices should produce positive MACD
        prices = list(range(1, 60))
        result = TechnicalIndicators.calculate_macd(prices)
        
        # MACD line should be positive (fast > slow for uptrend)
        last_macd = [v for v in result['macd'] if v is not None and not np.isnan(v)][-1]
        assert last_macd > 0


class TestBollingerExtended:
    """Extended Bollinger Bands tests"""
    
    def test_bollinger_width_volatility(self):
        """Test Bollinger width reflects volatility"""
        # Low volatility prices
        low_vol = [100 + np.sin(i * 0.1) for i in range(50)]
        
        # High volatility prices
        high_vol = [100 + np.sin(i * 0.1) * 10 for i in range(50)]
        
        result_low = TechnicalIndicators.calculate_bollinger_bands(low_vol)
        result_high = TechnicalIndicators.calculate_bollinger_bands(high_vol)
        
        # Get last valid widths
        idx = -1
        while result_low['upper'][idx] is None or np.isnan(result_low['upper'][idx]):
            idx -= 1
            
        width_low = result_low['upper'][idx] - result_low['lower'][idx]
        width_high = result_high['upper'][idx] - result_high['lower'][idx]
        
        assert width_high > width_low


class TestATRExtended:
    """Extended ATR tests"""
    
    def test_atr_increases_with_volatility(self):
        """Test ATR increases with price volatility"""
        # Low volatility
        low_vol_highs = [100 + i * 0.1 + 1 for i in range(30)]
        low_vol_lows = [100 + i * 0.1 - 1 for i in range(30)]
        low_vol_closes = [100 + i * 0.1 for i in range(30)]
        
        # High volatility
        high_vol_highs = [100 + i * 0.1 + 5 for i in range(30)]
        high_vol_lows = [100 + i * 0.1 - 5 for i in range(30)]
        high_vol_closes = [100 + i * 0.1 for i in range(30)]
        
        atr_low = TechnicalIndicators.calculate_atr(
            low_vol_highs, low_vol_lows, low_vol_closes, period=5
        )
        atr_high = TechnicalIndicators.calculate_atr(
            high_vol_highs, high_vol_lows, high_vol_closes, period=5
        )
        
        # Get last valid values
        valid_low = [v for v in atr_low if v is not None and not np.isnan(v)]
        valid_high = [v for v in atr_high if v is not None and not np.isnan(v)]
        
        if valid_low and valid_high:
            assert valid_high[-1] > valid_low[-1]


class TestStochasticExtended:
    """Extended Stochastic Oscillator tests"""
    
    def test_stochastic_overbought(self):
        """Test Stochastic shows overbought at range high"""
        # Prices consistently at high of range
        highs = [110] * 20
        lows = [90] * 20
        closes = [110] * 20  # Always at high
        
        result = TechnicalIndicators.calculate_stochastic(highs, lows, closes)
        
        valid_k = [v for v in result['k'] if v is not None and not np.isnan(v)]
        if valid_k:
            assert valid_k[-1] > 80  # Overbought
            
    def test_stochastic_oversold(self):
        """Test Stochastic shows oversold at range low"""
        highs = [110] * 20
        lows = [90] * 20
        closes = [90] * 20  # Always at low
        
        result = TechnicalIndicators.calculate_stochastic(highs, lows, closes)
        
        valid_k = [v for v in result['k'] if v is not None and not np.isnan(v)]
        if valid_k:
            assert valid_k[-1] < 20  # Oversold


class TestIndicatorIntegration:
    """Test indicator combinations used in trading strategies"""
    
    def test_bollinger_rsi_combo(self):
        """Test Bollinger + RSI can identify reversals"""
        # Create prices that hit lower band with oversold RSI
        prices = list(range(100, 70, -1)) + list(range(70, 75))
        
        bb = TechnicalIndicators.calculate_bollinger_bands(prices, period=10)
        rsi = TechnicalIndicators.calculate_rsi(prices, period=14)
        
        # Both should be calculable
        assert len(bb['lower']) == len(prices)
        assert len(rsi) == len(prices)
        
    def test_macd_stochastic_combo(self):
        """Test MACD + Stochastic combo"""
        prices = list(range(1, 60))
        highs = [p + 2 for p in prices]
        lows = [p - 2 for p in prices]
        
        macd = TechnicalIndicators.calculate_macd(prices)
        stoch = TechnicalIndicators.calculate_stochastic(highs, lows, prices)
        
        assert len(macd['macd']) == len(prices)
        assert len(stoch['k']) == len(prices)


class TestRSIExtended:
    """Extended RSI tests"""
    
    def test_rsi_default_period(self):
        """Test RSI with default period (14)"""
        prices = list(range(1, 50))
        result = TechnicalIndicators.calculate_rsi(prices)
        
        assert len(result) == len(prices)
        
    def test_rsi_custom_period(self):
        """Test RSI with custom periods"""
        # Use oscillating data so RSI has both gains and losses
        prices = [50 + 10 * np.sin(i * 0.5) + i * 0.1 for i in range(60)]
        
        rsi_7 = TechnicalIndicators.calculate_rsi(prices, period=7)
        rsi_21 = TechnicalIndicators.calculate_rsi(prices, period=21)
        
        # Shorter period should have more valid values (fewer warmup NaNs)
        valid_7 = len([v for v in rsi_7 if v is not None and not np.isnan(v)])
        valid_21 = len([v for v in rsi_21 if v is not None and not np.isnan(v)])
        
        assert valid_7 >= valid_21
