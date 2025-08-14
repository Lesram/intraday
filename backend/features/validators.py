"""
Feature validation and lookahead detection utilities.
Provides validation for OHLCV data and guards against lookahead bias.
"""

import numpy as np
import pandas as pd

from .types import LookaheadLeakError


def validate_ohlcv(df: pd.DataFrame) -> None:
    """
    Validate OHLCV DataFrame structure and data quality.

    Args:
        df: DataFrame to validate

    Raises:
        ValueError: If validation fails with specific reason
    """
    required_cols = ["open", "high", "low", "close", "volume"]

    # Check required columns
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required OHLCV columns: {missing_cols}")

    # Check numeric dtypes
    for col in required_cols:
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise ValueError(f"Column '{col}' must be numeric, got {df[col].dtype}")

    # Check for negative volumes
    if (df["volume"] < 0).any():
        raise ValueError("Volume cannot be negative")

    # Check OHLC relationships
    invalid_ohlc = (
        (df["high"] < df["low"])
        | (df["high"] < df["open"])
        | (df["high"] < df["close"])
        | (df["low"] > df["open"])
        | (df["low"] > df["close"])
    )
    if invalid_ohlc.any():
        raise ValueError("Invalid OHLC relationships detected (high < low, etc.)")

    # Check timestamp index if present
    if isinstance(df.index, pd.DatetimeIndex):
        if not df.index.is_monotonic_increasing:
            raise ValueError("Timestamps must be strictly increasing")

        if df.index.tz is None:
            raise ValueError("Timestamps must be timezone-aware (UTC preferred)")


def guard_no_lookahead(
    features: pd.DataFrame,
    price: pd.Series,
    feature_cols: list[str] | None = None,
    threshold: float = 0.7,
    window_size: int = 100,
) -> None:
    """
    Guard against lookahead bias in features.

    Detects if features have suspiciously high correlation with future returns,
    indicating potential lookahead bias.

    Args:
        features: Feature DataFrame
        price: Price series (same index as features)
        feature_cols: Specific columns to check, defaults to all
        threshold: Correlation threshold for flagging (0.7 = very suspicious)
        window_size: Rolling window size for correlation analysis

    Raises:
        LookaheadLeakError: If lookahead bias is detected
    """
    if feature_cols is None:
        feature_cols = list(features.columns)

    # Align data
    common_index = features.index.intersection(price.index)
    if len(common_index) < window_size:
        raise ValueError(
            f"Insufficient data for lookahead detection (need {window_size}, got {len(common_index)})"
        )

    features_aligned = features.loc[common_index]
    price_aligned = price.loc[common_index]

    # Calculate returns
    returns = price_aligned.pct_change().fillna(0)
    future_returns = returns.shift(-1).fillna(0)  # Next period return
    past_returns = returns.shift(1).fillna(0)  # Previous period return

    suspicious_features = []

    for col in feature_cols:
        if col not in features_aligned.columns:
            continue

        feature_series = features_aligned[col]
        if feature_series.isna().all():
            continue

        # Rolling correlation analysis
        future_corr_rolling = feature_series.rolling(window_size).corr(
            future_returns.rolling(window_size)
        )
        past_corr_rolling = feature_series.rolling(window_size).corr(
            past_returns.rolling(window_size)
        )

        # Remove NaN values
        future_corr = future_corr_rolling.dropna()
        past_corr = past_corr_rolling.dropna()

        if len(future_corr) == 0 or len(past_corr) == 0:
            continue

        # Check if correlation with future is significantly higher than with past
        avg_future_corr = abs(future_corr.mean())
        avg_past_corr = abs(past_corr.mean())

        # Flag if future correlation is much higher than past correlation
        if avg_future_corr > threshold and avg_future_corr > avg_past_corr * 1.5:
            suspicious_features.append(col)

    if suspicious_features:
        message = (
            f"Potential lookahead bias detected in features: {suspicious_features}"
        )
        raise LookaheadLeakError(message, suspicious_features)


def guard_no_lookahead_synthetic(
    features: pd.DataFrame,
    feature_cols: list[str] | None = None,
    accuracy_threshold: float = 0.8,
) -> None:
    """
    Alternative lookahead detection using synthetic monotone series.

    Creates a strictly increasing synthetic price series and tests if features
    can predict it unreasonably well, indicating lookahead bias.

    Args:
        features: Feature DataFrame
        feature_cols: Specific columns to check
        accuracy_threshold: Accuracy threshold for flagging

    Raises:
        LookaheadLeakError: If lookahead bias is detected
    """
    if feature_cols is None:
        feature_cols = list(features.columns)

    if len(features) < 50:  # Need minimum data for reliable test
        return

    # Create synthetic monotone price series
    synthetic_price = pd.Series(
        np.arange(len(features)) + np.random.normal(0, 0.01, len(features)),
        index=features.index,
    )
    synthetic_returns = synthetic_price.pct_change().fillna(0)
    synthetic_future_returns = synthetic_returns.shift(-1).fillna(0)

    # Convert to binary classification (up/down)
    target = (synthetic_future_returns > 0).astype(int)

    suspicious_features = []

    for col in feature_cols:
        if col not in features.columns:
            continue

        feature_series = features[col].fillna(0)  # Fill NaN with neutral value

        # Simple correlation-based prediction
        correlation = abs(feature_series.corr(target))

        # If correlation is suspiciously high with synthetic monotone series
        if correlation > accuracy_threshold:
            suspicious_features.append(col)

    if suspicious_features:
        message = f"Features show suspicious correlation with synthetic monotone series: {suspicious_features}"
        raise LookaheadLeakError(message, suspicious_features)


def validate_feature_alignment(features: pd.DataFrame, target: pd.Series) -> None:
    """
    Validate that features and target are properly aligned.

    Args:
        features: Feature DataFrame
        target: Target series

    Raises:
        ValueError: If alignment is incorrect
    """
    if not features.index.equals(target.index):
        raise ValueError("Features and target must have identical indices")

    if len(features) != len(target):
        raise ValueError("Features and target must have same length")

    # Check for proper target construction (no lookahead)
    # Target should be future returns, so first value should be NaN after shift
    if not pd.isna(target.iloc[-1]):  # Last target value should be NaN (no future data)
        raise ValueError(
            "Target appears to use future information (last value not NaN)"
        )


def detect_forward_fill_leakage(
    df: pd.DataFrame, max_consecutive_fill: int = 5
) -> list[str]:
    """
    Detect columns that might have problematic forward-filling.

    Args:
        df: DataFrame to analyze
        max_consecutive_fill: Maximum allowed consecutive identical values

    Returns:
        List of suspicious column names
    """
    suspicious_cols = []

    for col in df.columns:
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue

        series = df[col]

        # Find consecutive identical values
        consecutive_same = (series == series.shift(1)).astype(int)
        consecutive_counts = consecutive_same.groupby(
            (consecutive_same != consecutive_same.shift()).cumsum()
        ).sum()

        if (consecutive_counts > max_consecutive_fill).any():
            suspicious_cols.append(col)

    return suspicious_cols
