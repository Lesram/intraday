"""
Market data fixtures for testing.

These fixtures provide realistic but deterministic market data for testing
ingestion, feature engineering, ML models, and backtesting components.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

# Sample OHLCV data for AAPL spanning 100 days
SAMPLE_OHLCV = [
    {
        "timestamp": "2024-01-02T09:30:00Z",
        "symbol": "AAPL",
        "open": 185.64,
        "high": 186.95,
        "low": 185.00,
        "close": 185.64,
        "volume": 46249300,
        "trade_count": 245678,
        "vwap": 185.43,
    },
    {
        "timestamp": "2024-01-02T09:31:00Z",
        "symbol": "AAPL",
        "open": 185.64,
        "high": 186.12,
        "low": 185.20,
        "close": 185.89,
        "volume": 1234567,
        "trade_count": 5432,
        "vwap": 185.67,
    },
    # Add more sample data...
]

# Sample trades data
SAMPLE_TRADES = [
    {
        "timestamp": "2024-01-02T09:30:15.123456Z",
        "symbol": "AAPL",
        "price": 185.50,
        "size": 100,
        "side": "buy",
        "trade_id": "t_001",
        "conditions": ["@", "F"],
    },
    {
        "timestamp": "2024-01-02T09:30:16.456789Z",
        "symbol": "AAPL",
        "price": 185.52,
        "size": 50,
        "side": "sell",
        "trade_id": "t_002",
        "conditions": ["@"],
    },
]

# Sample quotes data (Level 1 BBO)
SAMPLE_QUOTES = [
    {
        "timestamp": "2024-01-02T09:30:00.123456Z",
        "symbol": "AAPL",
        "bid_price": 185.48,
        "bid_size": 100,
        "ask_price": 185.52,
        "ask_size": 200,
        "bid_exchange": "NASDAQ",
        "ask_exchange": "NASDAQ",
    },
]

# Sample news data for sentiment analysis
SAMPLE_NEWS = [
    {
        "timestamp": "2024-01-02T08:00:00Z",
        "headline": "Apple Reports Strong Q4 Earnings Beat Expectations",
        "summary": "Apple Inc. reported quarterly earnings that exceeded analyst expectations...",
        "sentiment_score": 0.75,
        "relevance": 0.95,
        "symbols": ["AAPL"],
        "source": "Reuters",
    },
    {
        "timestamp": "2024-01-02T10:30:00Z",
        "headline": "Apple Faces Supply Chain Challenges in Asia",
        "summary": "Manufacturing delays reported at key supplier facilities...",
        "sentiment_score": -0.35,
        "relevance": 0.80,
        "symbols": ["AAPL"],
        "source": "Bloomberg",
    },
]

# Sample social sentiment data
SAMPLE_SOCIAL_SENTIMENT = [
    {
        "timestamp": "2024-01-02T09:00:00Z",
        "symbol": "AAPL",
        "platform": "twitter",
        "sentiment_score": 0.65,
        "volume": 1250,
        "reach": 50000,
        "engagement": 2500,
    },
    {
        "timestamp": "2024-01-02T10:00:00Z",
        "symbol": "AAPL",
        "platform": "reddit",
        "sentiment_score": 0.45,
        "volume": 89,
        "reach": 15000,
        "engagement": 456,
    },
]


def generate_synthetic_ohlcv(
    symbol: str = "AAPL",
    start_date: str = "2024-01-01",
    days: int = 100,
    freq: str = "1min",
    volatility: float = 0.02,
    trend: float = 0.0001,
) -> pd.DataFrame:
    """
    Generate synthetic OHLCV data using geometric Brownian motion.

    Args:
        symbol: Trading symbol
        start_date: Start date in YYYY-MM-DD format
        days: Number of days to generate
        freq: Frequency (1min, 5min, 1h, 1d)
        volatility: Daily volatility (sigma)
        trend: Drift rate (mu)

    Returns:
        DataFrame with OHLCV data
    """
    start = pd.Timestamp(start_date)

    # Generate time index
    if freq == "1min":
        periods = days * 390  # Market hours 9:30-16:00 = 390 minutes
        index = pd.date_range(
            start=start.replace(hour=9, minute=30),
            periods=periods,
            freq="1min",
        )
        # Filter to market hours only
        index = index[index.indexer_between_time("09:30", "16:00")][:periods]
        dt = 1 / (252 * 390)  # Fraction of trading year
    elif freq == "5min":
        periods = days * 78  # 390/5 = 78 five-minute bars per day
        index = pd.date_range(
            start=start.replace(hour=9, minute=30),
            periods=periods,
            freq="5min",
        )
        dt = 5 / (252 * 390)
    elif freq == "1h":
        periods = days * 6.5  # 6.5 hours per trading day
        index = pd.date_range(
            start=start.replace(hour=9, minute=30),
            periods=int(periods),
            freq="1h",
        )
        dt = 1 / (252 * 6.5)
    else:  # 1d
        periods = days
        index = pd.date_range(start=start, periods=periods, freq="1D")
        dt = 1 / 252

    # Generate price series using GBM
    np.random.seed(42)  # For reproducible results
    returns = np.random.normal(trend * dt, volatility * np.sqrt(dt), len(index))

    # Starting price
    initial_price = 185.0
    prices = [initial_price]

    for ret in returns:
        prices.append(prices[-1] * np.exp(ret))

    prices = np.array(prices[1:])  # Remove initial price

    # Generate OHLC from prices
    data = []
    for i, (ts, price) in enumerate(zip(index, prices, strict=False)):
        # Add some intraday noise for OHLC
        noise = np.random.normal(0, 0.001, 4)  # Small random variations

        open_price = price * (1 + noise[0])
        close_price = price * (1 + noise[1])
        high_price = max(open_price, close_price) * (1 + abs(noise[2]))
        low_price = min(open_price, close_price) * (1 - abs(noise[3]))

        # Generate volume with some patterns
        base_volume = 1000000
        volume_noise = np.random.lognormal(0, 0.5)
        # Higher volume at market open/close
        if freq == "1min":
            hour = ts.hour
            if hour in [9, 15]:  # 9:30-10:30 and 3:00-4:00 PM
                volume_multiplier = 2.0
            else:
                volume_multiplier = 1.0
        else:
            volume_multiplier = 1.0

        volume = int(base_volume * volume_multiplier * volume_noise)

        data.append(
            {
                "timestamp": ts,
                "symbol": symbol,
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
                "volume": volume,
                "trade_count": max(1, volume // 100),
                "vwap": round(
                    (open_price + high_price + low_price + close_price) / 4, 2
                ),
            }
        )

    return pd.DataFrame(data)


def save_fixtures():
    """Save all fixture data to JSON files."""
    fixtures_dir = Path(__file__).parent

    # Save sample data
    with open(fixtures_dir / "sample_ohlcv.json", "w") as f:
        json.dump(SAMPLE_OHLCV, f, indent=2)

    with open(fixtures_dir / "sample_trades.json", "w") as f:
        json.dump(SAMPLE_TRADES, f, indent=2)

    with open(fixtures_dir / "sample_quotes.json", "w") as f:
        json.dump(SAMPLE_QUOTES, f, indent=2)

    with open(fixtures_dir / "sample_news.json", "w") as f:
        json.dump(SAMPLE_NEWS, f, indent=2, default=str)

    with open(fixtures_dir / "sample_social_sentiment.json", "w") as f:
        json.dump(SAMPLE_SOCIAL_SENTIMENT, f, indent=2)

    # Generate and save synthetic datasets
    symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"]

    for symbol in symbols:
        # Daily data for backtesting (252 days = 1 year)
        daily_data = generate_synthetic_ohlcv(
            symbol=symbol,
            days=252,
            freq="1d",
            volatility=0.02,
            trend=0.0005,  # Slight upward trend
        )
        daily_data.to_csv(fixtures_dir / f"{symbol}_daily.csv", index=False)

        # Minute data for short-term testing (5 days)
        minute_data = generate_synthetic_ohlcv(
            symbol=symbol,
            days=5,
            freq="1min",
            volatility=0.02,
        )
        minute_data.to_csv(fixtures_dir / f"{symbol}_minute.csv", index=False)

    print(f"Fixtures saved to {fixtures_dir}")


if __name__ == "__main__":
    save_fixtures()
