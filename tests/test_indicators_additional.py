"""
Additional comprehensive tests for backend/services/indicators.py

Tests the remaining technical indicators that are not covered:
- CCI (Commodity Channel Index)
- Williams %R
- MFI (Money Flow Index)
- Parabolic SAR
- Aroon
- Chaikin Money Flow
- TRIX
- VWMA (Volume Weighted Moving Average)
- KST (Know Sure Thing)
- Ultimate Oscillator
- Awesome Oscillator
- Donchian Channel
- Keltner Channel
- Ichimoku Cloud
- WMA (Weighted Moving Average)
- Pivot Points (all types)
"""

import numpy as np
import pytest

from backend.services.indicators import TechnicalIndicators, get_indicators_service


class TestGetIndicatorsService:
    """Test get_indicators_service function."""

    def test_returns_singleton(self):
        """Test that get_indicators_service returns singleton."""
        service1 = get_indicators_service()
        service2 = get_indicators_service()
        assert service1 is service2
        assert isinstance(service1, TechnicalIndicators)


class TestCalculateCCI:
    """Tests for calculate_cci (Commodity Channel Index)."""

    def test_cci_basic(self):
        """Test basic CCI calculation."""
        highs = [45.0, 46.0, 47.0, 48.0, 49.0, 50.0, 51.0, 52.0, 53.0, 54.0,
                 55.0, 56.0, 57.0, 58.0, 59.0, 60.0, 61.0, 62.0, 63.0, 64.0, 65.0]
        lows = [43.0, 44.0, 45.0, 46.0, 47.0, 48.0, 49.0, 50.0, 51.0, 52.0,
                53.0, 54.0, 55.0, 56.0, 57.0, 58.0, 59.0, 60.0, 61.0, 62.0, 63.0]
        closes = [44.0, 45.0, 46.0, 47.0, 48.0, 49.0, 50.0, 51.0, 52.0, 53.0,
                  54.0, 55.0, 56.0, 57.0, 58.0, 59.0, 60.0, 61.0, 62.0, 63.0, 64.0]

        result = TechnicalIndicators.calculate_cci(highs, lows, closes, period=14)

        assert len(result) == len(closes)
        # First (period-1) values should be None or NaN
        assert result[-1] is not None or not np.isnan(result[-1])

    def test_cci_insufficient_data(self):
        """Test CCI with insufficient data."""
        highs = [10.0, 11.0, 12.0]
        lows = [9.0, 10.0, 11.0]
        closes = [9.5, 10.5, 11.5]

        result = TechnicalIndicators.calculate_cci(highs, lows, closes, period=14)

        assert len(result) == 3
        assert all(v is None for v in result)


class TestCalculateWilliamsR:
    """Tests for calculate_williams_r."""

    def test_williams_r_basic(self):
        """Test basic Williams %R calculation."""
        highs = [50.0 + i for i in range(20)]
        lows = [48.0 + i for i in range(20)]
        closes = [49.0 + i for i in range(20)]

        result = TechnicalIndicators.calculate_williams_r(highs, lows, closes, period=14)

        assert len(result) == 20
        # Williams %R should be between -100 and 0
        valid_values = [v for v in result if v is not None and not np.isnan(v)]
        for val in valid_values:
            assert -100 <= val <= 0

    def test_williams_r_insufficient_data(self):
        """Test Williams %R with insufficient data."""
        result = TechnicalIndicators.calculate_williams_r([10, 11], [9, 10], [9.5, 10.5], period=14)
        assert all(v is None for v in result)


class TestCalculateMFI:
    """Tests for calculate_mfi (Money Flow Index)."""

    def test_mfi_basic(self):
        """Test basic MFI calculation."""
        n = 20
        highs = [100.0 + i for i in range(n)]
        lows = [98.0 + i for i in range(n)]
        closes = [99.0 + i for i in range(n)]
        volumes = [1000000.0 + i * 10000 for i in range(n)]

        result = TechnicalIndicators.calculate_mfi(highs, lows, closes, volumes, period=14)

        assert len(result) == n
        # MFI should be between 0 and 100
        valid_values = [v for v in result if v is not None and not np.isnan(v)]
        for val in valid_values:
            assert 0 <= val <= 100

    def test_mfi_insufficient_data(self):
        """Test MFI with insufficient data."""
        result = TechnicalIndicators.calculate_mfi([10, 11], [9, 10], [9.5, 10.5], [1000, 1100], period=14)
        assert all(v is None for v in result)


class TestCalculateParabolicSAR:
    """Tests for calculate_parabolic_sar."""

    def test_parabolic_sar_uptrend(self):
        """Test Parabolic SAR in uptrend."""
        # Simulate uptrend
        highs = [100.0 + i * 2 for i in range(20)]
        lows = [98.0 + i * 2 for i in range(20)]

        result = TechnicalIndicators.calculate_parabolic_sar(highs, lows)

        assert len(result) == 20
        assert result[0] is None  # First value is None
        # SAR values should be below price in uptrend
        for i, val in enumerate(result[1:], 1):
            if val is not None:
                assert isinstance(val, (int, float))

    def test_parabolic_sar_downtrend(self):
        """Test Parabolic SAR in downtrend."""
        # Simulate downtrend
        highs = [100.0 - i for i in range(20)]
        lows = [98.0 - i for i in range(20)]

        result = TechnicalIndicators.calculate_parabolic_sar(highs, lows)

        assert len(result) == 20

    def test_parabolic_sar_insufficient_data(self):
        """Test Parabolic SAR with insufficient data."""
        result = TechnicalIndicators.calculate_parabolic_sar([10, 11], [9, 10])
        assert all(v is None for v in result)

    def test_parabolic_sar_custom_params(self):
        """Test Parabolic SAR with custom parameters."""
        highs = [100.0 + i for i in range(10)]
        lows = [98.0 + i for i in range(10)]

        result = TechnicalIndicators.calculate_parabolic_sar(
            highs, lows, af_start=0.01, af_increment=0.01, af_max=0.1
        )

        assert len(result) == 10


class TestCalculateAroon:
    """Tests for calculate_aroon."""

    def test_aroon_basic(self):
        """Test basic Aroon calculation."""
        n = 30
        highs = [100.0 + i for i in range(n)]
        lows = [98.0 + i for i in range(n)]

        result = TechnicalIndicators.calculate_aroon(highs, lows, period=25)

        assert 'aroon_up' in result
        assert 'aroon_down' in result
        assert 'aroon_oscillator' in result
        assert len(result['aroon_up']) == n
        assert len(result['aroon_down']) == n
        assert len(result['aroon_oscillator']) == n

    def test_aroon_range(self):
        """Test Aroon values are in valid range."""
        n = 30
        highs = [100.0 + np.sin(i) * 5 for i in range(n)]
        lows = [98.0 + np.sin(i) * 5 for i in range(n)]

        result = TechnicalIndicators.calculate_aroon(highs, lows, period=14)

        for v in result['aroon_up']:
            if v is not None and not np.isnan(v):
                assert 0 <= v <= 100

        for v in result['aroon_down']:
            if v is not None and not np.isnan(v):
                assert 0 <= v <= 100

    def test_aroon_insufficient_data(self):
        """Test Aroon with insufficient data."""
        result = TechnicalIndicators.calculate_aroon([10, 11], [9, 10], period=25)
        assert all(v is None for v in result['aroon_up'])
        assert all(v is None for v in result['aroon_down'])


class TestCalculateChaikinMoneyFlow:
    """Tests for calculate_chaikin_money_flow."""

    def test_cmf_basic(self):
        """Test basic CMF calculation."""
        n = 25
        highs = [100.0 + i for i in range(n)]
        lows = [98.0 + i for i in range(n)]
        closes = [99.5 + i for i in range(n)]
        volumes = [1000000.0 for _ in range(n)]

        result = TechnicalIndicators.calculate_chaikin_money_flow(highs, lows, closes, volumes, period=20)

        assert len(result) == n
        # CMF should be between -1 and 1
        valid_values = [v for v in result if v is not None and not np.isnan(v)]
        for val in valid_values:
            assert -1 <= val <= 1

    def test_cmf_insufficient_data(self):
        """Test CMF with insufficient data."""
        result = TechnicalIndicators.calculate_chaikin_money_flow([10], [9], [9.5], [1000], period=20)
        assert all(v is None for v in result)


class TestCalculateTrix:
    """Tests for calculate_trix."""

    def test_trix_basic(self):
        """Test basic TRIX calculation."""
        n = 50
        prices = [100.0 + i * 0.5 for i in range(n)]

        result = TechnicalIndicators.calculate_trix(prices, period=15)

        assert len(result) == n
        # At least some values should be calculated
        valid_values = [v for v in result if v is not None and not np.isnan(v)]
        assert len(valid_values) > 0

    def test_trix_insufficient_data(self):
        """Test TRIX with insufficient data."""
        result = TechnicalIndicators.calculate_trix([100, 101, 102], period=15)
        assert all(v is None for v in result)


class TestCalculateVWMA:
    """Tests for calculate_volume_weighted_ma."""

    def test_vwma_basic(self):
        """Test basic VWMA calculation."""
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
        volumes = [1000, 1500, 2000, 1500, 1000, 1200, 1800, 1600, 1400, 1000]

        result = TechnicalIndicators.calculate_volume_weighted_ma(prices, volumes, period=5)

        assert len(result) == 10
        # First 4 values should be None
        assert result[0] is None or np.isnan(result[0])
        # Later values should be calculated
        assert result[-1] is not None and not np.isnan(result[-1])

    def test_vwma_insufficient_data(self):
        """Test VWMA with insufficient data."""
        result = TechnicalIndicators.calculate_volume_weighted_ma([100, 101], [1000, 1100], period=20)
        assert all(v is None for v in result)


class TestCalculateKST:
    """Tests for calculate_know_sure_thing."""

    def test_kst_basic(self):
        """Test basic KST calculation."""
        n = 60
        prices = [100.0 + i * 0.5 + np.sin(i/3) * 2 for i in range(n)]

        result = TechnicalIndicators.calculate_know_sure_thing(prices)

        assert 'kst' in result
        assert 'signal' in result
        assert len(result['kst']) == n
        assert len(result['signal']) == n

    def test_kst_insufficient_data(self):
        """Test KST with insufficient data."""
        result = TechnicalIndicators.calculate_know_sure_thing([100, 101, 102])
        assert all(v is None for v in result['kst'])
        assert all(v is None for v in result['signal'])


class TestCalculateUltimateOscillator:
    """Tests for calculate_ultimate_oscillator."""

    def test_uo_basic(self):
        """Test basic Ultimate Oscillator calculation."""
        n = 35
        highs = [100.0 + i + np.sin(i/3) for i in range(n)]
        lows = [98.0 + i + np.sin(i/3) for i in range(n)]
        closes = [99.0 + i + np.sin(i/3) for i in range(n)]

        result = TechnicalIndicators.calculate_ultimate_oscillator(highs, lows, closes)

        assert len(result) == n
        # UO should be between 0 and 100
        valid_values = [v for v in result if v is not None and not np.isnan(v)]
        for val in valid_values:
            assert 0 <= val <= 100

    def test_uo_insufficient_data(self):
        """Test Ultimate Oscillator with insufficient data."""
        result = TechnicalIndicators.calculate_ultimate_oscillator([100], [99], [99.5])
        assert all(v is None for v in result)


class TestCalculateAwesomeOscillator:
    """Tests for calculate_awesome_oscillator."""

    def test_ao_basic(self):
        """Test basic Awesome Oscillator calculation."""
        n = 40
        highs = [100.0 + i for i in range(n)]
        lows = [98.0 + i for i in range(n)]

        result = TechnicalIndicators.calculate_awesome_oscillator(highs, lows)

        assert len(result) == n
        # At least some values should be calculated
        valid_values = [v for v in result if v is not None and not np.isnan(v)]
        assert len(valid_values) > 0

    def test_ao_insufficient_data(self):
        """Test Awesome Oscillator with insufficient data."""
        result = TechnicalIndicators.calculate_awesome_oscillator([100, 101], [99, 100])
        assert all(v is None for v in result)


class TestCalculateDonchianChannel:
    """Tests for calculate_donchian_channel."""

    def test_donchian_basic(self):
        """Test basic Donchian Channel calculation."""
        n = 25
        highs = [100.0 + i + np.sin(i) * 2 for i in range(n)]
        lows = [98.0 + i + np.sin(i) * 2 for i in range(n)]

        result = TechnicalIndicators.calculate_donchian_channel(highs, lows, period=20)

        assert 'upper' in result
        assert 'middle' in result
        assert 'lower' in result
        assert len(result['upper']) == n

        # Upper should be >= middle >= lower
        for i in range(n):
            if result['upper'][i] is not None and not np.isnan(result['upper'][i]):
                assert result['upper'][i] >= result['middle'][i]
                assert result['middle'][i] >= result['lower'][i]

    def test_donchian_insufficient_data(self):
        """Test Donchian Channel with insufficient data."""
        result = TechnicalIndicators.calculate_donchian_channel([100, 101], [99, 100], period=20)
        assert all(v is None for v in result['upper'])


class TestCalculateKeltnerChannel:
    """Tests for calculate_keltner_channel."""

    def test_keltner_basic(self):
        """Test basic Keltner Channel calculation."""
        n = 30
        highs = [100.0 + i for i in range(n)]
        lows = [98.0 + i for i in range(n)]
        closes = [99.0 + i for i in range(n)]

        result = TechnicalIndicators.calculate_keltner_channel(highs, lows, closes, period=20)

        assert 'upper' in result
        assert 'middle' in result
        assert 'lower' in result
        assert len(result['upper']) == n

    def test_keltner_bands_relationship(self):
        """Test Keltner bands are in correct order."""
        n = 30
        highs = [100.0 + i for i in range(n)]
        lows = [98.0 + i for i in range(n)]
        closes = [99.0 + i for i in range(n)]

        result = TechnicalIndicators.calculate_keltner_channel(highs, lows, closes, period=20)

        # Upper >= Middle >= Lower
        for i in range(20, n):
            if result['upper'][i] is not None and not np.isnan(result['upper'][i]):
                assert result['upper'][i] >= result['middle'][i]
                assert result['middle'][i] >= result['lower'][i]

    def test_keltner_insufficient_data(self):
        """Test Keltner Channel with insufficient data."""
        result = TechnicalIndicators.calculate_keltner_channel([100, 101], [99, 100], [99.5, 100.5], period=20)
        assert all(v is None for v in result['upper'])


class TestCalculateIchimokuCloud:
    """Tests for calculate_ichimoku_cloud."""

    def test_ichimoku_basic(self):
        """Test basic Ichimoku Cloud calculation."""
        n = 80
        highs = [100.0 + i * 0.5 for i in range(n)]
        lows = [98.0 + i * 0.5 for i in range(n)]
        closes = [99.0 + i * 0.5 for i in range(n)]

        result = TechnicalIndicators.calculate_ichimoku_cloud(highs, lows, closes)

        assert 'tenkan' in result
        assert 'kijun' in result
        assert 'senkou_a' in result
        assert 'senkou_b' in result
        assert 'chikou' in result
        assert len(result['tenkan']) == n

    def test_ichimoku_insufficient_data(self):
        """Test Ichimoku Cloud with insufficient data."""
        result = TechnicalIndicators.calculate_ichimoku_cloud([100, 101], [99, 100], [99.5, 100.5])
        assert all(v is None for v in result['tenkan'])


class TestCalculateWMA:
    """Tests for calculate_wma (Weighted Moving Average)."""

    def test_wma_basic(self):
        """Test basic WMA calculation."""
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]

        result = TechnicalIndicators.calculate_wma(prices, period=5)

        assert len(result) == 10
        # First 4 values should be None
        assert result[0] is None or np.isnan(result[0])
        # Later values should be calculated
        assert result[-1] is not None and not np.isnan(result[-1])

    def test_wma_higher_weight_to_recent(self):
        """Test that WMA gives higher weight to recent prices."""
        # Sharp increase at end
        prices = [100.0] * 4 + [110.0]

        result = TechnicalIndicators.calculate_wma(prices, period=5)

        # WMA should be higher than SMA due to higher weight on recent 110
        sma = sum(prices) / 5  # = 102
        wma = result[-1]
        assert wma is not None and not np.isnan(wma)
        assert wma > sma  # WMA should be higher than SMA

    def test_wma_insufficient_data(self):
        """Test WMA with insufficient data."""
        result = TechnicalIndicators.calculate_wma([100, 101], period=20)
        assert all(v is None for v in result)


class TestCalculatePivotPoints:
    """Tests for calculate_pivot_points."""

    def test_pivot_standard(self):
        """Test standard pivot points."""
        highs = [105.0, 106.0, 107.0, 108.0, 109.0]
        lows = [100.0, 101.0, 102.0, 103.0, 104.0]
        closes = [103.0, 104.0, 105.0, 106.0, 107.0]

        result = TechnicalIndicators.calculate_pivot_points(highs, lows, closes, pivot_type='standard')

        assert 'pivot' in result
        assert 's1' in result
        assert 's2' in result
        assert 's3' in result
        assert 'r1' in result
        assert 'r2' in result
        assert 'r3' in result
        assert len(result['pivot']) == 5

        # R1 > Pivot > S1
        for i in range(1, 5):
            if result['pivot'][i] is not None and not np.isnan(result['pivot'][i]):
                assert result['r1'][i] > result['pivot'][i]
                assert result['pivot'][i] > result['s1'][i]

    def test_pivot_fibonacci(self):
        """Test Fibonacci pivot points."""
        highs = [105.0, 106.0, 107.0, 108.0, 109.0]
        lows = [100.0, 101.0, 102.0, 103.0, 104.0]
        closes = [103.0, 104.0, 105.0, 106.0, 107.0]

        result = TechnicalIndicators.calculate_pivot_points(highs, lows, closes, pivot_type='fibonacci')

        assert 'pivot' in result
        # Fibonacci uses 0.382 and 0.618 ratios
        assert len(result['r1']) == 5

    def test_pivot_woodie(self):
        """Test Woodie pivot points."""
        highs = [105.0, 106.0, 107.0, 108.0, 109.0]
        lows = [100.0, 101.0, 102.0, 103.0, 104.0]
        closes = [103.0, 104.0, 105.0, 106.0, 107.0]

        result = TechnicalIndicators.calculate_pivot_points(highs, lows, closes, pivot_type='woodie')

        assert 'pivot' in result
        assert len(result['pivot']) == 5

    def test_pivot_camarilla(self):
        """Test Camarilla pivot points."""
        highs = [105.0, 106.0, 107.0, 108.0, 109.0]
        lows = [100.0, 101.0, 102.0, 103.0, 104.0]
        closes = [103.0, 104.0, 105.0, 106.0, 107.0]

        result = TechnicalIndicators.calculate_pivot_points(highs, lows, closes, pivot_type='camarilla')

        assert 'pivot' in result
        assert len(result['pivot']) == 5

    def test_pivot_unknown_type_uses_standard(self):
        """Test unknown pivot type defaults to standard."""
        highs = [105.0, 106.0, 107.0, 108.0, 109.0]
        lows = [100.0, 101.0, 102.0, 103.0, 104.0]
        closes = [103.0, 104.0, 105.0, 106.0, 107.0]

        result_unknown = TechnicalIndicators.calculate_pivot_points(highs, lows, closes, pivot_type='unknown')
        result_standard = TechnicalIndicators.calculate_pivot_points(highs, lows, closes, pivot_type='standard')

        # Should produce same results - compare non-NaN values
        for i in range(1, 5):
            if result_unknown['pivot'][i] is not None and not np.isnan(result_unknown['pivot'][i]):
                assert np.isclose(result_unknown['pivot'][i], result_standard['pivot'][i])

    def test_pivot_insufficient_data(self):
        """Test pivot points with insufficient data."""
        result = TechnicalIndicators.calculate_pivot_points([100], [99], [99.5])
        assert all(v is None for v in result['pivot'])


class TestEdgeCases:
    """Test edge cases for indicators."""

    def test_empty_list_cci(self):
        """Test CCI with empty list."""
        result = TechnicalIndicators.calculate_cci([], [], [], period=14)
        assert result == []

    def test_empty_list_williams_r(self):
        """Test Williams %R with empty list."""
        result = TechnicalIndicators.calculate_williams_r([], [], [], period=14)
        assert result == []

    def test_zero_volume_mfi(self):
        """Test MFI with zero volume."""
        highs = [100.0 + i for i in range(20)]
        lows = [98.0 + i for i in range(20)]
        closes = [99.0 + i for i in range(20)]
        volumes = [0.0 for _ in range(20)]  # Zero volume

        result = TechnicalIndicators.calculate_mfi(highs, lows, closes, volumes, period=14)
        
        assert len(result) == 20

    def test_constant_prices_cmf(self):
        """Test CMF with constant prices."""
        n = 25
        highs = [100.0 for _ in range(n)]
        lows = [100.0 for _ in range(n)]
        closes = [100.0 for _ in range(n)]
        volumes = [1000.0 for _ in range(n)]

        result = TechnicalIndicators.calculate_chaikin_money_flow(highs, lows, closes, volumes, period=20)
        
        assert len(result) == n

    def test_volatile_prices_parabolic_sar(self):
        """Test Parabolic SAR with volatile prices."""
        n = 30
        highs = [100.0 + 10 * np.sin(i/2) for i in range(n)]
        lows = [95.0 + 10 * np.sin(i/2) for i in range(n)]

        result = TechnicalIndicators.calculate_parabolic_sar(highs, lows)
        
        assert len(result) == n
        # Should have some reversals
        valid_count = sum(1 for v in result if v is not None)
        assert valid_count >= n - 1
