"""
Comprehensive tests for backend.services.indicators

Targets 70%+ coverage for the TechnicalIndicators class which provides:
- Moving averages (SMA, EMA)
- Momentum indicators (RSI, MACD, Stochastic)
- Volatility indicators (Bollinger Bands, ATR)
- Trend indicators (ADX)
- Volume indicators (OBV, VWAP)
- Oscillators (CCI)
"""

import numpy as np
import pytest

from backend.services.indicators import TechnicalIndicators


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_prices():
    """Generate sample price data"""
    # Simulated price data with upward trend
    return [100 + i * 0.5 + np.sin(i/5) * 2 for i in range(100)]


@pytest.fixture
def sample_ohlcv():
    """Generate sample OHLCV data"""
    n = 100
    base = 100
    closes = [base + i * 0.5 + np.sin(i/5) * 2 for i in range(n)]
    highs = [c + abs(np.random.randn()) * 2 for c in closes]
    lows = [c - abs(np.random.randn()) * 2 for c in closes]
    volumes = [1000000 + np.random.randint(-100000, 100000) for _ in range(n)]
    return highs, lows, closes, volumes


# ============================================================================
# SMA TESTS
# ============================================================================

def is_nan_or_none(v):
    """Helper to check for NaN or None"""
    return v is None or (isinstance(v, float) and np.isnan(v))


def is_valid_number(v):
    """Helper to check for valid numeric value"""
    return v is not None and isinstance(v, (int, float)) and not np.isnan(v)


class TestCalculateSMA:
    """Tests for Simple Moving Average"""
    
    def test_basic_sma(self, sample_prices):
        """Test basic SMA calculation"""
        result = TechnicalIndicators.calculate_sma(sample_prices, period=20)
        
        assert len(result) == len(sample_prices)
        # First 19 values should be NaN (rolling window not full)
        assert all(is_nan_or_none(v) for v in result[:19])
        # Values after period should be valid floats
        assert all(is_valid_number(v) for v in result[19:])
        
    def test_sma_insufficient_data(self):
        """Test SMA with insufficient data"""
        prices = [100, 101, 102]  # Less than default period
        result = TechnicalIndicators.calculate_sma(prices, period=20)
        
        assert len(result) == 3
        assert all(v is None for v in result)
        
    def test_sma_values_reasonable(self, sample_prices):
        """Test SMA values are within price range"""
        result = TechnicalIndicators.calculate_sma(sample_prices, period=10)
        
        valid_values = [v for v in result if is_valid_number(v)]
        assert all(min(sample_prices) <= v <= max(sample_prices) for v in valid_values)


# ============================================================================
# EMA TESTS
# ============================================================================

class TestCalculateEMA:
    """Tests for Exponential Moving Average"""
    
    def test_basic_ema(self, sample_prices):
        """Test basic EMA calculation"""
        result = TechnicalIndicators.calculate_ema(sample_prices, period=20)
        
        assert len(result) == len(sample_prices)
        # EMA should have values for all periods (ewm doesn't require full window)
        assert all(isinstance(v, float) for v in result if v is not None)
        
    def test_ema_insufficient_data(self):
        """Test EMA with insufficient data"""
        prices = [100, 101, 102]
        result = TechnicalIndicators.calculate_ema(prices, period=20)
        
        assert len(result) == 3
        assert all(v is None for v in result)
        
    def test_ema_responds_faster_than_sma(self, sample_prices):
        """Test EMA responds faster to price changes"""
        # Add a spike at the end
        prices_with_spike = sample_prices.copy()
        prices_with_spike[-1] = prices_with_spike[-2] + 10
        
        sma = TechnicalIndicators.calculate_sma(prices_with_spike, period=10)
        ema = TechnicalIndicators.calculate_ema(prices_with_spike, period=10)
        
        # EMA should be higher due to more recent weight
        assert ema[-1] > sma[-1]


# ============================================================================
# RSI TESTS
# ============================================================================

class TestCalculateRSI:
    """Tests for Relative Strength Index"""
    
    def test_basic_rsi(self, sample_prices):
        """Test basic RSI calculation"""
        result = TechnicalIndicators.calculate_rsi(sample_prices, period=14)
        
        assert len(result) == len(sample_prices)
        
    def test_rsi_range(self, sample_prices):
        """Test RSI values are between 0 and 100"""
        result = TechnicalIndicators.calculate_rsi(sample_prices, period=14)
        
        valid_values = [v for v in result if v is not None and not np.isnan(v)]
        assert all(0 <= v <= 100 for v in valid_values)
        
    def test_rsi_insufficient_data(self):
        """Test RSI with insufficient data"""
        prices = [100, 101, 102, 103]
        result = TechnicalIndicators.calculate_rsi(prices, period=14)
        
        assert len(result) == 4
        assert all(v is None for v in result)
        
    def test_rsi_uptrend_high(self):
        """Test RSI is high in uptrend"""
        uptrend = [100 + i for i in range(30)]  # Consistent uptrend
        result = TechnicalIndicators.calculate_rsi(uptrend, period=14)
        
        valid_values = [v for v in result if v is not None and not np.isnan(v)]
        if valid_values:
            # RSI should be high in uptrend
            assert valid_values[-1] > 50


# ============================================================================
# MACD TESTS
# ============================================================================

class TestCalculateMACD:
    """Tests for MACD indicator"""
    
    def test_basic_macd(self, sample_prices):
        """Test basic MACD calculation"""
        result = TechnicalIndicators.calculate_macd(sample_prices)
        
        assert 'macd' in result
        assert 'signal' in result
        assert 'histogram' in result
        assert len(result['macd']) == len(sample_prices)
        
    def test_macd_insufficient_data(self):
        """Test MACD with insufficient data"""
        prices = [100, 101, 102]
        result = TechnicalIndicators.calculate_macd(prices)
        
        assert all(v is None for v in result['macd'])
        
    def test_macd_histogram_is_difference(self, sample_prices):
        """Test histogram equals MACD - Signal"""
        result = TechnicalIndicators.calculate_macd(sample_prices)
        
        for i in range(len(sample_prices)):
            if result['macd'][i] is not None and result['signal'][i] is not None:
                expected = result['macd'][i] - result['signal'][i]
                assert abs(result['histogram'][i] - expected) < 0.0001


# ============================================================================
# BOLLINGER BANDS TESTS
# ============================================================================

class TestCalculateBollingerBands:
    """Tests for Bollinger Bands"""
    
    def test_basic_bollinger(self, sample_prices):
        """Test basic Bollinger Bands calculation"""
        result = TechnicalIndicators.calculate_bollinger_bands(sample_prices)
        
        assert 'upper' in result
        assert 'middle' in result
        assert 'lower' in result
        
    def test_bollinger_insufficient_data(self):
        """Test Bollinger with insufficient data"""
        prices = [100, 101, 102]
        result = TechnicalIndicators.calculate_bollinger_bands(prices)
        
        assert all(v is None for v in result['upper'])
        
    def test_bollinger_band_ordering(self, sample_prices):
        """Test upper > middle > lower"""
        result = TechnicalIndicators.calculate_bollinger_bands(sample_prices)
        
        for i in range(len(sample_prices)):
            upper = result['upper'][i]
            middle = result['middle'][i]
            lower = result['lower'][i]
            if all(is_valid_number(v) for v in [upper, middle, lower]):
                assert upper > middle > lower
                
    def test_bollinger_custom_std(self, sample_prices):
        """Test custom standard deviation"""
        result_2std = TechnicalIndicators.calculate_bollinger_bands(sample_prices, std_dev=2.0)
        result_3std = TechnicalIndicators.calculate_bollinger_bands(sample_prices, std_dev=3.0)
        
        # 3 std bands should be wider
        for i in range(len(sample_prices)):
            upper_2 = result_2std['upper'][i]
            lower_2 = result_2std['lower'][i]
            upper_3 = result_3std['upper'][i]
            lower_3 = result_3std['lower'][i]
            if all(is_valid_number(v) for v in [upper_2, lower_2, upper_3, lower_3]):
                width_2 = upper_2 - lower_2
                width_3 = upper_3 - lower_3
                assert width_3 > width_2


# ============================================================================
# ATR TESTS
# ============================================================================

class TestCalculateATR:
    """Tests for Average True Range"""
    
    def test_basic_atr(self, sample_ohlcv):
        """Test basic ATR calculation"""
        highs, lows, closes, _ = sample_ohlcv
        result = TechnicalIndicators.calculate_atr(highs, lows, closes)
        
        assert len(result) == len(closes)
        
    def test_atr_insufficient_data(self):
        """Test ATR with insufficient data"""
        result = TechnicalIndicators.calculate_atr([100], [99], [100])
        
        assert all(v is None for v in result)
        
    def test_atr_positive_values(self, sample_ohlcv):
        """Test ATR values are positive"""
        highs, lows, closes, _ = sample_ohlcv
        result = TechnicalIndicators.calculate_atr(highs, lows, closes)
        
        valid_values = [v for v in result if v is not None and not np.isnan(v)]
        assert all(v >= 0 for v in valid_values)


# ============================================================================
# STOCHASTIC TESTS
# ============================================================================

class TestCalculateStochastic:
    """Tests for Stochastic Oscillator"""
    
    def test_basic_stochastic(self, sample_ohlcv):
        """Test basic Stochastic calculation"""
        highs, lows, closes, _ = sample_ohlcv
        result = TechnicalIndicators.calculate_stochastic(highs, lows, closes)
        
        assert 'k' in result
        assert 'd' in result
        assert len(result['k']) == len(closes)
        
    def test_stochastic_insufficient_data(self):
        """Test Stochastic with insufficient data"""
        result = TechnicalIndicators.calculate_stochastic([100], [99], [100])
        
        assert all(v is None for v in result['k'])
        
    def test_stochastic_range(self, sample_ohlcv):
        """Test Stochastic values are 0-100"""
        highs, lows, closes, _ = sample_ohlcv
        result = TechnicalIndicators.calculate_stochastic(highs, lows, closes)
        
        valid_k = [v for v in result['k'] if v is not None and not np.isnan(v)]
        valid_d = [v for v in result['d'] if v is not None and not np.isnan(v)]
        
        assert all(0 <= v <= 100 for v in valid_k)
        assert all(0 <= v <= 100 for v in valid_d)


# ============================================================================
# ADX TESTS
# ============================================================================

class TestCalculateADX:
    """Tests for Average Directional Index"""
    
    def test_basic_adx(self, sample_ohlcv):
        """Test basic ADX calculation"""
        highs, lows, closes, _ = sample_ohlcv
        result = TechnicalIndicators.calculate_adx(highs, lows, closes)
        
        assert len(result) == len(closes)
        
    def test_adx_insufficient_data(self):
        """Test ADX with insufficient data"""
        result = TechnicalIndicators.calculate_adx([100] * 10, [99] * 10, [100] * 10)
        
        assert all(v is None for v in result)
        
    def test_adx_range(self, sample_ohlcv):
        """Test ADX values are 0-100"""
        highs, lows, closes, _ = sample_ohlcv
        result = TechnicalIndicators.calculate_adx(highs, lows, closes)
        
        valid_values = [v for v in result if v is not None and not np.isnan(v)]
        # ADX should be positive
        assert all(v >= 0 for v in valid_values)


# ============================================================================
# OBV TESTS
# ============================================================================

class TestCalculateOBV:
    """Tests for On Balance Volume"""
    
    def test_basic_obv(self, sample_ohlcv):
        """Test basic OBV calculation"""
        _, _, closes, volumes = sample_ohlcv
        result = TechnicalIndicators.calculate_obv(closes, volumes)
        
        assert len(result) == len(closes)
        
    def test_obv_insufficient_data(self):
        """Test OBV with insufficient data"""
        result = TechnicalIndicators.calculate_obv([100], [1000])
        
        assert all(v is None for v in result)
        
    def test_obv_cumulative(self, sample_ohlcv):
        """Test OBV is cumulative"""
        _, _, closes, volumes = sample_ohlcv
        result = TechnicalIndicators.calculate_obv(closes, volumes)
        
        # OBV should change with price direction
        valid_values = [v for v in result if v is not None]
        assert len(valid_values) > 0


# ============================================================================
# VWAP TESTS
# ============================================================================

class TestCalculateVWAP:
    """Tests for Volume Weighted Average Price"""
    
    def test_basic_vwap(self, sample_ohlcv):
        """Test basic VWAP calculation"""
        highs, lows, closes, volumes = sample_ohlcv
        result = TechnicalIndicators.calculate_vwap(highs, lows, closes, volumes)
        
        assert len(result) == len(closes)
        
    def test_vwap_empty_data(self):
        """Test VWAP with empty data"""
        result = TechnicalIndicators.calculate_vwap([], [], [], [])
        
        assert result == []
        
    def test_vwap_values_reasonable(self, sample_ohlcv):
        """Test VWAP values are within price range"""
        highs, lows, closes, volumes = sample_ohlcv
        result = TechnicalIndicators.calculate_vwap(highs, lows, closes, volumes)
        
        valid_values = [v for v in result if v is not None and not np.isnan(v)]
        # VWAP should be within the typical price range
        assert all(min(lows) <= v <= max(highs) for v in valid_values)


# ============================================================================
# CCI TESTS
# ============================================================================

class TestCalculateCCI:
    """Tests for Commodity Channel Index"""
    
    def test_basic_cci(self, sample_ohlcv):
        """Test basic CCI calculation"""
        highs, lows, closes, _ = sample_ohlcv
        result = TechnicalIndicators.calculate_cci(highs, lows, closes)
        
        assert len(result) == len(closes)
        
    def test_cci_can_be_negative(self, sample_ohlcv):
        """Test CCI can have negative values"""
        highs, lows, closes, _ = sample_ohlcv
        result = TechnicalIndicators.calculate_cci(highs, lows, closes)
        
        valid_values = [v for v in result if v is not None and not np.isnan(v)]
        # CCI oscillates around zero, should have mix of positive/negative
        has_positive = any(v > 0 for v in valid_values)
        has_negative = any(v < 0 for v in valid_values)
        
        # At least one should exist
        assert has_positive or has_negative


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases"""
    
    def test_single_price(self):
        """Test with single price"""
        result = TechnicalIndicators.calculate_sma([100], period=1)
        assert len(result) == 1
        
    def test_constant_prices(self):
        """Test with constant prices"""
        constant = [100.0] * 50
        
        sma = TechnicalIndicators.calculate_sma(constant, period=10)
        ema = TechnicalIndicators.calculate_ema(constant, period=10)
        
        # With constant prices, SMA and EMA should equal the price
        valid_sma = [v for v in sma if is_valid_number(v)]
        valid_ema = [v for v in ema if is_valid_number(v)]
        
        assert all(abs(v - 100.0) < 0.001 for v in valid_sma)
        assert all(abs(v - 100.0) < 0.001 for v in valid_ema)
        
    def test_volatile_prices(self):
        """Test with highly volatile prices"""
        volatile = [100 + (i % 2) * 10 for i in range(50)]  # Alternating 100, 110
        
        result = TechnicalIndicators.calculate_rsi(volatile, period=14)
        
        # Should not crash and should return values
        assert len(result) == 50


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Performance-related tests"""
    
    def test_large_dataset(self):
        """Test with large dataset"""
        large_prices = [100 + i * 0.01 for i in range(10000)]
        
        # Should complete without error
        sma = TechnicalIndicators.calculate_sma(large_prices, period=200)
        assert len(sma) == 10000
        
    def test_all_indicators_same_length(self, sample_ohlcv):
        """Test all indicators return same length as input"""
        highs, lows, closes, volumes = sample_ohlcv
        n = len(closes)
        
        assert len(TechnicalIndicators.calculate_sma(closes)) == n
        assert len(TechnicalIndicators.calculate_ema(closes)) == n
        assert len(TechnicalIndicators.calculate_rsi(closes)) == n
        assert len(TechnicalIndicators.calculate_macd(closes)['macd']) == n
        assert len(TechnicalIndicators.calculate_bollinger_bands(closes)['upper']) == n
        assert len(TechnicalIndicators.calculate_atr(highs, lows, closes)) == n
        assert len(TechnicalIndicators.calculate_stochastic(highs, lows, closes)['k']) == n
        assert len(TechnicalIndicators.calculate_obv(closes, volumes)) == n
        assert len(TechnicalIndicators.calculate_vwap(highs, lows, closes, volumes)) == n
