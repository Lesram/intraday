"""
Helper utilities for the Algorithmic Trading Platform.
Contains common mathematical, financial, and utility functions.
"""

from datetime import datetime
import hashlib
from typing import Any
import uuid
import warnings

# Suppress NumPy reload warning
warnings.filterwarnings("ignore", message="The NumPy module was reloaded")

import numpy as np
import pandas as pd


def align_for_pandas_arithmetic(other: Any, index: pd.Index) -> pd.Series:
    """
    Align other data with DataFrame index for safe pandas arithmetic operations.

    Prevents "ValueError: other must be a DataFrame or Series" by normalizing
    inputs to properly aligned pandas Series before subtract/compare operations.

    Args:
        other: Data to align (scalar, list, Series, DataFrame, etc.)
        index: pandas Index to align with

    Returns:
        pandas Series aligned with the provided index

    Examples:
        >>> df = pd.DataFrame({'col': [1, 2, 3]}, index=[0, 1, 2])
        >>> df['col'] - align_for_pandas_arithmetic(5, df.index)  # scalar
        >>> df['col'] - align_for_pandas_arithmetic([1, 2, 3], df.index)  # list
        >>> df['col'] - align_for_pandas_arithmetic(other_series, df.index)  # series
    """
    if isinstance(other, (int, float)):
        return pd.Series([other] * len(index), index=index)
    if isinstance(other, pd.Series):
        return other.reindex(index, fill_value=0)
    if isinstance(other, pd.DataFrame):
        return other.iloc[:, 0].reindex(index, fill_value=0)
    if isinstance(other, (list, tuple, np.ndarray)):
        # Ensure the data fits the index
        other_list = list(other)
        if len(other_list) > len(index):
            other_list = other_list[:len(index)]
        elif len(other_list) < len(index):
            # Pad with last value or zero
            pad_value = other_list[-1] if other_list else 0
            other_list.extend([pad_value] * (len(index) - len(other_list)))
        return pd.Series(other_list, index=index)
    # Fallback: try to convert to Series
    try:
        return pd.Series(other, index=index)
    except Exception:
        return pd.Series([other] * len(index), index=index)


def calculate_returns(
    prices: pd.Series | np.ndarray, method: str = "simple"
) -> pd.Series | np.ndarray:
    """
    Calculate returns from price series.

    Args:
        prices: Price series
        method: "simple" or "log" returns

    Returns:
        Returns series
    """
    if isinstance(prices, pd.Series):
        if method == "log":
            return np.log(prices / prices.shift(1))
        else:
            return prices.pct_change()
    elif method == "log":
        return np.log(prices[1:] / prices[:-1])
    else:
        return np.diff(prices) / prices[:-1]


def calculate_sharpe_ratio(
    returns: pd.Series | np.ndarray, risk_free_rate: float = 0.02
) -> float:
    """
    Calculate Sharpe ratio.

    Args:
        returns: Return series
        risk_free_rate: Annual risk-free rate

    Returns:
        Sharpe ratio
    """
    try:
        if isinstance(returns, pd.Series):
            mean_return = float(returns.mean())
            std_return = float(returns.std())
        else:
            mean_return = float(np.mean(returns))
            std_return = float(np.std(returns))
    except (TypeError, ValueError):
        # Fallback for numpy compatibility issues
        returns_array = np.array(returns, dtype=float)
        mean_return = float(np.mean(returns_array))
        std_return = float(np.std(returns_array))

    # Annualize (assuming daily returns)
    annual_return = mean_return * 252
    annual_std = std_return * np.sqrt(252)

    return (annual_return - risk_free_rate) / annual_std if annual_std != 0 else 0


def calculate_max_drawdown(equity_curve: pd.Series | np.ndarray) -> float:
    """
    Calculate maximum drawdown from equity curve.

    Args:
        equity_curve: Equity values over time

    Returns:
        Maximum drawdown as a fraction
    """
    try:
        if isinstance(equity_curve, pd.Series):
            cumulative_max = equity_curve.expanding().max()
            drawdown = (equity_curve - cumulative_max) / cumulative_max
            return float(drawdown.min())
        else:
            cumulative_max = np.maximum.accumulate(equity_curve)
            drawdown = (equity_curve - cumulative_max) / cumulative_max
            return float(np.min(drawdown))
    except (TypeError, ValueError):
        # Fallback for numpy compatibility issues
        equity_array = np.array(equity_curve, dtype=float)
        cumulative_max = np.maximum.accumulate(equity_array)
        drawdown = (equity_array - cumulative_max) / cumulative_max
        return float(np.min(drawdown))


def calculate_var(
    returns: pd.Series | np.ndarray, confidence: float = 0.95
) -> float:
    """
    Calculate Value at Risk (VaR).

    Args:
        returns: Return series
        confidence: Confidence level (e.g., 0.95 for 95%)

    Returns:
        VaR value (negative number indicating loss)
    """
    try:
        if isinstance(returns, pd.Series):
            return float(returns.quantile(1 - confidence))
        else:
            return float(np.percentile(returns, (1 - confidence) * 100))
    except (TypeError, ValueError):
        # Fallback for numpy compatibility issues
        returns_array = np.array(returns, dtype=float)
        percentile_val = (1 - confidence) * 100
        sorted_returns = np.sort(returns_array)
        idx = int(np.ceil(percentile_val / 100.0 * len(sorted_returns))) - 1
        idx = max(0, min(idx, len(sorted_returns) - 1))
        return float(sorted_returns[idx])


def calculate_cvar(
    returns: pd.Series | np.ndarray, confidence: float = 0.95
) -> float:
    """
    Calculate Conditional Value at Risk (CVaR) or Expected Shortfall.

    Args:
        returns: Return series
        confidence: Confidence level (e.g., 0.95 for 95%)

    Returns:
        CVaR value (negative number indicating expected loss beyond VaR)
    """
    var = calculate_var(returns, confidence)

    try:
        if isinstance(returns, pd.Series):
            tail_returns = returns[returns <= var]
            return float(tail_returns.mean()) if len(tail_returns) > 0 else var
        else:
            tail_returns = returns[returns <= var]
            return float(np.mean(tail_returns)) if len(tail_returns) > 0 else var
    except (TypeError, ValueError):
        # Fallback for numpy compatibility issues
        returns_array = np.array(returns, dtype=float)
        tail_returns = returns_array[returns_array <= var]
        return float(np.mean(tail_returns)) if len(tail_returns) > 0 else var


def kelly_criterion(win_probability: float, win_loss_ratio: float) -> float:
    """
    Calculate optimal position size using Kelly criterion.

    Args:
        win_probability: Probability of winning trade (0-1)
        win_loss_ratio: Ratio of average win to average loss

    Returns:
        Optimal fraction of capital to risk (0-1)
    """
    if win_loss_ratio <= 0 or win_probability <= 0 or win_probability >= 1:
        return 0.0

    kelly_fraction = win_probability - ((1 - win_probability) / win_loss_ratio)
    return max(0, min(kelly_fraction, 0.25))  # Cap at 25% for safety


def normalize_data(
    data: pd.DataFrame | pd.Series | np.ndarray, method: str = "zscore"
) -> pd.DataFrame | pd.Series | np.ndarray:
    """
    Normalize data using various methods.

    Args:
        data: Data to normalize
        method: "zscore", "minmax", or "robust"

    Returns:
        Normalized data
    """
    try:
        if method == "zscore":
            if isinstance(data, (pd.DataFrame, pd.Series)):
                return (data - data.mean()) / data.std()
            else:
                return (data - np.mean(data)) / np.std(data)
        elif method == "minmax":
            if isinstance(data, (pd.DataFrame, pd.Series)):
                return (data - data.min()) / (data.max() - data.min())
            else:
                return (data - np.min(data)) / (np.max(data) - np.min(data))
        elif method == "robust":
            if isinstance(data, (pd.DataFrame, pd.Series)):
                median = data.median()
                mad = (data - median).abs().median()
                return (data - median) / mad
            else:
                median = np.median(data)
                mad = np.median(np.abs(data - median))
                return (data - median) / mad
        else:
            raise ValueError(f"Unknown normalization method: {method}")
    except (TypeError, ValueError) as e:
        if "Unknown normalization method" in str(e):
            raise e
        # Fallback for numpy compatibility issues
        data_array = np.array(data, dtype=float)
        if method == "zscore":
            return (data_array - np.mean(data_array)) / np.std(data_array)
        elif method == "minmax":
            return (data_array - np.min(data_array)) / (np.max(data_array) - np.min(data_array))
        elif method == "robust":
            median = np.median(data_array)
            mad = np.median(np.abs(data_array - median))
            return (data_array - median) / mad


def correlation_matrix(returns: pd.DataFrame, method: str = "pearson") -> pd.DataFrame:
    """
    Calculate correlation matrix for multiple return series.

    Args:
        returns: DataFrame with return series as columns
        method: "pearson", "spearman", or "kendall"

    Returns:
        Correlation matrix
    """
    return returns.corr(method=method)


def generate_trade_id() -> str:
    """Generate a unique trade ID."""
    return str(uuid.uuid4())


def hash_string(text: str) -> str:
    """Generate SHA-256 hash of a string."""
    return hashlib.sha256(text.encode()).hexdigest()


def is_market_hours(
    dt: datetime | None = None, timezone_name: str = "America/New_York"
) -> bool:
    """Check if given datetime is during market hours.

    Delegates to :mod:`backend.utils.market_hours` canonical implementation
    (handles holidays, early closes, weekends).
    """
    from backend.utils.market_hours import is_market_open
    return is_market_open(dt)


def round_to_tick_size(price: float, tick_size: float = 0.01) -> float:
    """Round price to nearest tick size."""
    return round(price / tick_size) * tick_size


def calculate_position_value(quantity: float, price: float) -> float:
    """Calculate the market value of a position."""
    return abs(quantity) * price


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, returning default if denominator is zero."""
    return numerator / denominator if denominator != 0 else default


def exponential_moving_average(
    data: pd.Series | np.ndarray, span: int
) -> pd.Series | np.ndarray:
    """Calculate exponential moving average."""
    if isinstance(data, pd.Series):
        return data.ewm(span=span).mean()
    else:
        alpha = 2 / (span + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
        return ema


def bollinger_bands(
    prices: pd.Series | np.ndarray, period: int = 20, std_dev: float = 2.0
) -> tuple:
    """
    Calculate Bollinger Bands.

    Args:
        prices: Price series
        period: Moving average period
        std_dev: Standard deviation multiplier

    Returns:
        Tuple of (upper_band, middle_band, lower_band)
    """
    if isinstance(prices, pd.Series):
        middle_band = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band
    else:
        middle_band = pd.Series(prices).rolling(window=period).mean().values
        std = pd.Series(prices).rolling(window=period).std().values
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        return upper_band, middle_band, lower_band


def rsi(
    prices: pd.Series | np.ndarray, period: int = 14
) -> pd.Series | np.ndarray:
    """
    Calculate Relative Strength Index (RSI).

    Args:
        prices: Price series
        period: RSI period

    Returns:
        RSI values
    """
    try:
        if isinstance(prices, np.ndarray):
            prices = pd.Series(prices)

        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi_values = 100 - (100 / (1 + rs))

        return rsi_values if isinstance(prices, pd.Series) else rsi_values.values
    except (TypeError, ValueError):
        # Fallback for numpy compatibility issues
        prices_array = np.array(prices, dtype=float)
        if len(prices_array) < period + 1:
            return np.full(len(prices_array), np.nan)

        delta = np.diff(prices_array)
        gains = np.where(delta > 0, delta, 0)
        losses = np.where(delta < 0, -delta, 0)

        # Simple moving average for the first calculation
        avg_gain = np.convolve(gains, np.ones(period)/period, mode='valid')
        avg_loss = np.convolve(losses, np.ones(period)/period, mode='valid')

        # Calculate RSI
        avg_loss = np.where(avg_loss == 0, 1e-10, avg_loss)  # Avoid division by zero
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        # Pad with NaN for the initial period
        result = np.full(len(prices_array), np.nan)
        result[period:] = rsi

        return result


def validate_symbol(symbol: str) -> bool:
    """Validate if symbol format is correct."""
    if not symbol or not isinstance(symbol, str):
        return False

    # Basic validation - alphanumeric characters, slash for crypto pairs
    allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/")
    return all(c in allowed_chars for c in symbol.upper())


def format_currency(amount: float, currency: str = "USD") -> str:
    """Format amount as currency string."""
    if currency == "USD":
        return f"${amount:,.2f}"
    else:
        return f"{amount:,.2f} {currency}"


def time_to_market_open() -> int | None:
    """Calculate seconds until next market open, or None if open now.

    Delegates to :mod:`backend.utils.market_hours`.
    """
    from backend.utils.market_hours import is_market_open, get_next_market_open, ET
    from datetime import timezone

    now = datetime.now(timezone.utc)
    if is_market_open(now):
        return None
    next_open = get_next_market_open(now)
    return int((next_open - now).total_seconds())
