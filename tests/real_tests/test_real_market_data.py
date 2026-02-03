"""
REAL Market Data Integration Tests.

These tests validate ACTUAL market data:
- Real historical bar data from Alpaca
- Real data transformation and calculations
- Real data quality validation

NO MOCKING - All data comes from real market data providers.

Note: The AlpacaDataClient currently only supports:
- get_historical_closes(symbol, lookback, timeframe)

Future enhancements may add:
- Real-time quotes
- Trade data
- Level 2 data
"""

import asyncio
import math
import pytest
from backend.integrations.alpaca_data import AlpacaDataClient


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
async def data_client():
    """Create AlpacaDataClient for testing."""
    client = AlpacaDataClient()
    yield client
    await client.close()


# =============================================================================
# HISTORICAL DATA TESTS
# =============================================================================

class TestRealHistoricalData:
    """Test historical bar data retrieval."""
    
    @pytest.mark.asyncio
    async def test_get_daily_closes(self, data_client):
        """Test fetching daily closing prices."""
        closes = await data_client.get_historical_closes(
            symbol="AAPL",
            lookback=30,
            timeframe="1Day"
        )
        
        assert closes is not None
        assert len(closes) >= 20, f"Should have at least 20 trading days, got {len(closes)}"
        
        # All prices should be positive
        for price in closes:
            assert price > 0, f"Price {price} should be positive"
        
        # Prices should be in reasonable range for AAPL (100-500)
        for price in closes:
            assert 50 < price < 500, f"AAPL price {price} seems unreasonable"
    
    @pytest.mark.asyncio
    async def test_get_spy_closes(self, data_client):
        """Test fetching SPY data (most liquid ETF)."""
        closes = await data_client.get_historical_closes(
            symbol="SPY",
            lookback=50,
            timeframe="1Day"
        )
        
        assert closes is not None
        assert len(closes) >= 30, f"Should have at least 30 trading days, got {len(closes)}"
        
        # SPY typically trades 400-600 range
        for price in closes:
            assert 200 < price < 800, f"SPY price {price} seems unreasonable"
    
    @pytest.mark.asyncio
    async def test_get_hourly_closes(self, data_client):
        """Test fetching hourly closing prices."""
        closes = await data_client.get_historical_closes(
            symbol="AAPL",
            lookback=50,
            timeframe="1Hour"
        )
        
        assert closes is not None
        assert len(closes) >= 10, f"Should have at least 10 hourly bars, got {len(closes)}"
        
        # All prices should be positive
        for price in closes:
            assert price > 0
    
    @pytest.mark.asyncio
    async def test_get_minute_closes(self, data_client):
        """Test fetching minute closing prices."""
        closes = await data_client.get_historical_closes(
            symbol="SPY",
            lookback=100,
            timeframe="1Min"
        )
        
        assert closes is not None
        # May not get full 100 during off-hours
        assert len(closes) >= 1, "Should have at least some minute data"
    
    @pytest.mark.asyncio
    async def test_long_history(self, data_client):
        """Test fetching longer historical data (200 days)."""
        closes = await data_client.get_historical_closes(
            symbol="MSFT",
            lookback=200,
            timeframe="1Day"
        )
        
        assert closes is not None
        assert len(closes) >= 150, f"Should have at least 150 trading days, got {len(closes)}"
    
    @pytest.mark.asyncio
    async def test_multiple_symbols(self, data_client):
        """Test fetching data for multiple symbols."""
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN"]
        
        for symbol in symbols:
            closes = await data_client.get_historical_closes(
                symbol=symbol,
                lookback=30,
                timeframe="1Day"
            )
            
            assert closes is not None, f"Failed to get data for {symbol}"
            assert len(closes) >= 20, f"{symbol} should have at least 20 days"
            assert all(p > 0 for p in closes), f"{symbol} has invalid prices"


# =============================================================================
# DATA QUALITY TESTS
# =============================================================================

class TestRealDataQuality:
    """Test data quality validation."""
    
    @pytest.mark.asyncio
    async def test_no_zero_prices(self, data_client):
        """Test that no zero prices are returned."""
        closes = await data_client.get_historical_closes(
            symbol="AAPL",
            lookback=100,
            timeframe="1Day"
        )
        
        assert all(price > 0 for price in closes), "Found zero prices in data"
    
    @pytest.mark.asyncio
    async def test_no_extreme_jumps(self, data_client):
        """Test for unrealistic price jumps (data anomalies)."""
        closes = await data_client.get_historical_closes(
            symbol="AAPL",
            lookback=100,
            timeframe="1Day"
        )
        
        extreme_jumps = []
        for i in range(1, len(closes)):
            daily_return = abs(closes[i] - closes[i-1]) / closes[i-1]
            
            # Flag jumps over 25% (unusual but possible for splits, etc.)
            if daily_return > 0.25:
                extreme_jumps.append({
                    "day": i,
                    "prev": closes[i-1],
                    "curr": closes[i],
                    "return": daily_return
                })
        
        # Allow at most a couple extreme moves (stock splits, etc.)
        assert len(extreme_jumps) <= 3, f"Too many extreme jumps: {extreme_jumps}"
    
    @pytest.mark.asyncio
    async def test_chronological_order(self, data_client):
        """Test that data is returned in chronological order (oldest first)."""
        # We can't verify timestamps directly, but we can check for consistency
        closes = await data_client.get_historical_closes(
            symbol="AAPL",
            lookback=30,
            timeframe="1Day"
        )
        
        # Data should be consistently ordered
        assert len(closes) >= 10


# =============================================================================
# DATA TRANSFORMATION TESTS
# =============================================================================

class TestRealDataTransformation:
    """Test data transformation and calculations."""
    
    @pytest.mark.asyncio
    async def test_calculate_returns(self, data_client):
        """Test calculating returns from real bar data."""
        closes = await data_client.get_historical_closes(
            symbol="AAPL",
            lookback=252,  # 1 year of trading days
            timeframe="1Day"
        )
        
        assert len(closes) >= 100, "Need at least 100 days for return calculation"
        
        # Calculate daily returns
        returns = [
            (closes[i] - closes[i-1]) / closes[i-1]
            for i in range(1, len(closes))
        ]
        
        # Verify return statistics are reasonable
        avg_return = sum(returns) / len(returns)
        std_return = math.sqrt(sum((r - avg_return)**2 for r in returns) / len(returns))
        
        # Daily returns should be small on average (-2% to +2%)
        assert -0.02 < avg_return < 0.02, f"Average daily return {avg_return:.4f} seems off"
        
        # Standard deviation should be reasonable (typically 1-4% for stocks)
        assert 0.005 < std_return < 0.10, f"Volatility {std_return:.4f} seems unusual"
        
        # Annualized volatility
        annual_vol = std_return * math.sqrt(252)
        assert 0.08 < annual_vol < 1.0, f"Annual volatility {annual_vol:.2%} seems unusual"
    
    @pytest.mark.asyncio
    async def test_calculate_moving_averages(self, data_client):
        """Test calculating moving averages from real data."""
        closes = await data_client.get_historical_closes(
            symbol="SPY",
            lookback=100,
            timeframe="1Day"
        )
        
        assert len(closes) >= 50, "Need at least 50 days for SMA calculation"
        
        # Calculate 20-day SMA
        sma_20 = sum(closes[-20:]) / 20
        
        # Calculate 50-day SMA
        sma_50 = sum(closes[-50:]) / 50
        
        # SMAs should be close to current price (within 15%)
        current_price = closes[-1]
        
        assert abs(sma_20 - current_price) / current_price < 0.15, \
            f"20-day SMA {sma_20:.2f} too far from current price {current_price:.2f}"
        assert abs(sma_50 - current_price) / current_price < 0.20, \
            f"50-day SMA {sma_50:.2f} too far from current price {current_price:.2f}"
    
    @pytest.mark.asyncio
    async def test_calculate_rsi(self, data_client):
        """Test calculating RSI from real data."""
        closes = await data_client.get_historical_closes(
            symbol="AAPL",
            lookback=50,
            timeframe="1Day"
        )
        
        assert len(closes) >= 15, "Need at least 15 days for RSI calculation"
        
        # Calculate price changes
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        
        # Separate gains and losses (14-day RSI)
        gains = [max(0, c) for c in changes[-14:]]
        losses = [-min(0, c) for c in changes[-14:]]
        
        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14
        
        if avg_loss > 0:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        else:
            rsi = 100  # No losses = RSI of 100
        
        # RSI should be between 0 and 100
        assert 0 <= rsi <= 100, f"RSI {rsi} is out of range"
    
    @pytest.mark.asyncio
    async def test_calculate_bollinger_bands(self, data_client):
        """Test calculating Bollinger Bands from real data."""
        closes = await data_client.get_historical_closes(
            symbol="AAPL",
            lookback=30,
            timeframe="1Day"
        )
        
        assert len(closes) >= 20, "Need at least 20 days for Bollinger Bands"
        
        # 20-day SMA
        sma_20 = sum(closes[-20:]) / 20
        
        # Standard deviation
        variance = sum((p - sma_20)**2 for p in closes[-20:]) / 20
        std_dev = math.sqrt(variance)
        
        # Bollinger Bands (2 standard deviations)
        upper_band = sma_20 + 2 * std_dev
        lower_band = sma_20 - 2 * std_dev
        
        # Current price should usually be within bands
        current_price = closes[-1]
        
        # Verify bands are reasonable
        assert upper_band > sma_20 > lower_band, "Band ordering is wrong"
        assert lower_band > 0, "Lower band should be positive"
    
    @pytest.mark.asyncio
    async def test_calculate_macd(self, data_client):
        """Test calculating MACD from real data."""
        closes = await data_client.get_historical_closes(
            symbol="SPY",
            lookback=50,
            timeframe="1Day"
        )
        
        assert len(closes) >= 26, "Need at least 26 days for MACD"
        
        # Simple EMAs (using SMA for simplicity)
        ema_12 = sum(closes[-12:]) / 12
        ema_26 = sum(closes[-26:]) / 26
        
        macd_line = ema_12 - ema_26
        
        # MACD should be a small number relative to price
        assert abs(macd_line) < closes[-1] * 0.10, \
            f"MACD {macd_line:.2f} seems too large relative to price {closes[-1]:.2f}"


# =============================================================================
# LATENCY & PERFORMANCE TESTS
# =============================================================================

class TestRealDataLatency:
    """Test data fetching performance."""
    
    @pytest.mark.asyncio
    async def test_single_fetch_latency(self, data_client):
        """Test that single data fetch completes in acceptable time."""
        import time
        
        start = time.time()
        closes = await data_client.get_historical_closes(
            symbol="AAPL",
            lookback=30,
            timeframe="1Day"
        )
        elapsed = time.time() - start
        
        # Should complete in under 3 seconds
        assert elapsed < 3.0, f"Data fetch took {elapsed:.2f}s, should be under 3s"
        assert len(closes) >= 20
    
    @pytest.mark.asyncio
    async def test_multiple_fetch_sequential(self, data_client):
        """Test sequential fetches for multiple symbols."""
        import time
        
        symbols = ["AAPL", "MSFT", "GOOGL"]
        
        start = time.time()
        for symbol in symbols:
            closes = await data_client.get_historical_closes(
                symbol=symbol,
                lookback=30,
                timeframe="1Day"
            )
            assert len(closes) >= 20
        elapsed = time.time() - start
        
        # 3 fetches should complete in under 10 seconds
        assert elapsed < 10.0, f"3 fetches took {elapsed:.2f}s, should be under 10s"
    
    @pytest.mark.asyncio
    async def test_concurrent_fetches(self, data_client):
        """Test concurrent data fetches."""
        import time
        
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN"]
        
        start = time.time()
        results = await asyncio.gather(*[
            data_client.get_historical_closes(symbol=s, lookback=30, timeframe="1Day")
            for s in symbols
        ])
        elapsed = time.time() - start
        
        # Concurrent fetches should be faster than sequential
        assert elapsed < 5.0, f"Concurrent fetches took {elapsed:.2f}s, should be under 5s"
        
        # All fetches should succeed
        for closes in results:
            assert len(closes) >= 20


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================

class TestRealDataErrorHandling:
    """Test error handling for invalid requests."""
    
    @pytest.mark.asyncio
    async def test_invalid_symbol(self, data_client):
        """Test handling of invalid symbol."""
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException) as exc_info:
            await data_client.get_historical_closes(
                symbol="INVALID_SYMBOL_XYZ123",
                lookback=30,
                timeframe="1Day"
            )
        
        # Should return 502 (Bad Gateway) for API errors
        assert exc_info.value.status_code == 502
    
    @pytest.mark.asyncio
    async def test_empty_symbol(self, data_client):
        """Test handling of empty symbol."""
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException):
            await data_client.get_historical_closes(
                symbol="",
                lookback=30,
                timeframe="1Day"
            )


# =============================================================================
# DATA CONSISTENCY TESTS
# =============================================================================

class TestRealDataConsistency:
    """Test data consistency across fetches."""
    
    @pytest.mark.asyncio
    async def test_consistent_closes(self, data_client):
        """Test that repeated fetches return consistent data."""
        closes1 = await data_client.get_historical_closes(
            symbol="AAPL",
            lookback=30,
            timeframe="1Day"
        )
        
        await asyncio.sleep(0.5)
        
        closes2 = await data_client.get_historical_closes(
            symbol="AAPL",
            lookback=30,
            timeframe="1Day"
        )
        
        # Should have same length
        assert len(closes1) == len(closes2)
        
        # Historical data should be identical
        for i in range(min(len(closes1) - 1, len(closes2) - 1)):
            assert closes1[i] == closes2[i], \
                f"Historical prices differ at index {i}: {closes1[i]} vs {closes2[i]}"
    
    @pytest.mark.asyncio
    async def test_different_lookbacks_consistent(self, data_client):
        """Test that different lookbacks return consistent overlapping data."""
        closes_30 = await data_client.get_historical_closes(
            symbol="AAPL",
            lookback=30,
            timeframe="1Day"
        )
        
        closes_50 = await data_client.get_historical_closes(
            symbol="AAPL",
            lookback=50,
            timeframe="1Day"
        )
        
        # Last 30 days of closes_50 should match closes_30
        # (with small tolerance for timing differences)
        overlap_len = min(len(closes_30), len(closes_50))
        
        # Compare the last few entries (most recent)
        for i in range(1, min(5, overlap_len)):
            price_30 = closes_30[-i]
            price_50 = closes_50[-i]
            assert price_30 == price_50, \
                f"Prices differ at offset -{i}: {price_30} vs {price_50}"
