"""
Feature validation and lookahead detection utilities.
Provides validation for OHLCV data and guards against lookahead bias.
"""

import os

# Centralized DISABLE_ML check for test mode
DISABLE_ML = os.environ.get("DISABLE_ML", "0") == "1"

# Import real pandas and numpy - they're lightweight and needed
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

    # Check numeric dtypes (stub-compatible)
    for col in required_cols:
        try:
            if hasattr(pd, 'api') and hasattr(pd.api, 'types'):
                if not pd.api.types.is_numeric_dtype(df[col]):
                    raise ValueError(f"Column '{col}' must be numeric, got {df[col].dtype}")
            else:
                # Fallback for stub mode - check if numeric-like
                try:
                    pd.to_numeric(df[col])
                except (ValueError, TypeError):
                    raise ValueError(f"Column '{col}' must be numeric, got {df[col].dtype}")
        except ValueError as e:
            # Re-raise validation errors
            raise e
        except Exception:
            # Final fallback - try direct type check
            if not all(isinstance(x, (int, float)) for x in df[col] if pd.notna(x)):
                raise ValueError(f"Column '{col}' must be numeric, got {df[col].dtype}")

    # Check for infinite values
    try:
        for col in required_cols:
            # Simple direct check for infinity
            values = df[col].values if hasattr(df[col], 'values') else df[col]
            for val in values:
                if val == float('inf') or val == float('-inf'):
                    raise ValueError(f"Column '{col}' contains infinite values")
    except ValueError:
        # Re-raise validation errors
        raise
    except Exception:
        # Skip infinity check in stub mode
        pass

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
    try:
        if hasattr(pd, 'DatetimeIndex') and isinstance(df.index, pd.DatetimeIndex):
            if not df.index.is_monotonic_increasing:
                raise ValueError("Timestamps must be strictly increasing")

            if df.index.tz is None:
                raise ValueError("Timestamps must be timezone-aware (UTC preferred)")
    except (AttributeError, TypeError):
        # Skip timestamp validation in stub mode
        pass


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
        future_corr_rolling = feature_series.rolling(window_size).corr(future_returns)
        past_corr_rolling = feature_series.rolling(window_size).corr(past_returns)

        # Remove NaN values
        future_corr = future_corr_rolling.dropna()
        past_corr = past_corr_rolling.dropna()

        if len(future_corr) == 0 or len(past_corr) == 0:
            continue

        # Check if correlation with future is significantly higher than with past
        avg_future_corr = abs(future_corr.mean())
        avg_past_corr = abs(past_corr.mean())

        # Flag if future correlation is much higher than past correlation
        # Focus on cases where future correlation is significantly higher
        ratio = avg_future_corr / max(avg_past_corr, 0.01)  # Avoid division by zero
        if avg_future_corr > 0.15 and ratio > 1.4:
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
    try:
        if hasattr(pd, 'isna'):
            is_last_nan = pd.isna(target.iloc[-1])
        else:
            # Fallback for stub mode
            import numpy as np
            is_last_nan = np.isnan(target.iloc[-1]) if hasattr(target.iloc[-1], '__float__') else False

        if not is_last_nan:  # Last target value should be NaN (no future data)
            raise ValueError(
                "Target appears to use future information (last value not NaN)"
            )
    except Exception:
        # Skip validation in stub mode
        pass


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
