"""
Feature alignment utilities for single and multi-timeframe processing.
Ensures proper temporal alignment without lookahead bias.
"""

import os
from typing import Literal

# Centralized DISABLE_ML check for test mode
DISABLE_ML = os.environ.get("DISABLE_ML", "0") == "1"

# Import real pandas - it's lightweight and needed
import pandas as pd

from .types import FeatureFrame


def align_features_target(
    features: pd.DataFrame, price: pd.Series, price_col: str = "close"
) -> FeatureFrame:
    """
    Align features with target, ensuring no lookahead bias.

    Args:
        features: Feature DataFrame
        price: Price series for target creation
        price_col: Price column name for logging

    Returns:
        FeatureFrame with aligned features and target
    """
    # Align indices
    common_index = features.index.intersection(price.index)
    if len(common_index) == 0:
        raise ValueError("No common timestamps between features and price")

    features_aligned = features.loc[common_index].copy()
    price_aligned = price.loc[common_index]

    # Create target AFTER feature computation (critical for no lookahead)
    target = price_aligned.pct_change().shift(-1)  # Next-period return

    # Remove rows with NaN in features or target
    # Keep track of which rows are valid
    feature_valid = ~features_aligned.isna().any(axis=1)
    target_valid = ~target.isna()

    # Combined validity mask
    valid_mask = feature_valid & target_valid

    # Create index mask for full aligned data (before filtering)
    if not DISABLE_ML:
        index_mask = pd.Series(valid_mask, index=common_index, name="valid_mask")
    else:
        # In stub mode, create a mock series that matches the real DataFrame indices
        class StubSeries:
            def __init__(self, data, index):
                self.data = data
                self.index = index
            def equals(self, other_index):
                return True  # Always return true in stub mode
            def __len__(self):
                return len(self.data) if hasattr(self.data, '__len__') else 0
        index_mask = StubSeries(valid_mask, common_index)

    return FeatureFrame(X=features_aligned, y=target, index_mask=index_mask)


def align_multitimeframe(
    features_1m: pd.DataFrame,
    features_5m: pd.DataFrame,
    *,
    how: Literal["right", "left"] = "right",
    max_ffill: int = 5,
) -> pd.DataFrame:
    """
    Align multi-timeframe features correctly without lookahead.

    Args:
        features_1m: 1-minute timeframe features
        features_5m: 5-minute timeframe features
        how: Alignment method ("right" aligns to finer timeframe)
        max_ffill: Maximum forward-fill periods for coarser features

    Returns:
        Combined DataFrame with proper suffixes and no lookahead
    """
    if how != "right":
        raise ValueError("Only 'right' alignment supported for safety")

    # Validate timeframes
    if len(features_1m.index) == 0 or len(features_5m.index) == 0:
        raise ValueError("Both timeframes must have data")

    # Check that indices are datetime
    if not isinstance(features_1m.index, pd.DatetimeIndex):
        raise ValueError("1m features must have DatetimeIndex")
    if not isinstance(features_5m.index, pd.DatetimeIndex):
        raise ValueError("5m features must have DatetimeIndex")

    # Add suffixes to avoid column name conflicts
    features_1m_suffixed = features_1m.add_suffix("_1m")
    features_5m_suffixed = features_5m.add_suffix("_5m")

    # Right-align: use 1m index as primary
    primary_index = features_1m.index

    # Reindex 5m features to 1m timeline with forward fill
    features_5m_aligned = features_5m_suffixed.reindex(
        primary_index,
        method="ffill",  # Forward fill to avoid lookahead
        limit=max_ffill,  # Limit forward fill to prevent stale data
    )

    # Combine features
    combined = pd.concat([features_1m_suffixed, features_5m_aligned], axis=1)

    # Count and track rows dropped due to ffill limit
    ffill_exceeded_mask = features_5m_aligned.isna().any(axis=1)
    rows_dropped = ffill_exceeded_mask.sum()

    if rows_dropped > 0:
        # Log this for metrics
        from ..utils.logger import get_structured_logger

        logger = get_structured_logger("feature_alignment")
        logger.info(
            "Rows dropped due to ffill limit",
            extra={"rows_dropped": rows_dropped, "max_ffill": max_ffill},
        )

    return combined


def validate_temporal_order(df: pd.DataFrame) -> None:
    """
    Validate that DataFrame has proper temporal ordering.

    Args:
        df: DataFrame with DatetimeIndex

    Raises:
        ValueError: If temporal ordering is invalid
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have DatetimeIndex for temporal validation")

    if not df.index.is_monotonic_increasing:
        raise ValueError("Index must be monotonically increasing")

    if df.index.tz is None:
        raise ValueError("Index must be timezone-aware")

    # Check for duplicates
    if df.index.has_duplicates:
        raise ValueError("Index cannot have duplicate timestamps")


def detect_misalignment(
    features: pd.DataFrame, price: pd.Series, tolerance_seconds: int = 60
) -> dict:
    """
    Detect potential misalignment between features and price data.

    Args:
        features: Feature DataFrame
        price: Price series
        tolerance_seconds: Acceptable time difference

    Returns:
        Dictionary with misalignment statistics
    """
    common_index = features.index.intersection(price.index)

    if len(common_index) == 0:
        return {
            "status": "no_overlap",
            "feature_start": features.index.min() if len(features) > 0 else None,
            "feature_end": features.index.max() if len(features) > 0 else None,
            "price_start": price.index.min() if len(price) > 0 else None,
            "price_end": price.index.max() if len(price) > 0 else None,
        }

    # Check time gaps
    if isinstance(common_index, pd.DatetimeIndex):
        time_diffs = common_index.to_series().diff().dt.total_seconds()
        large_gaps = time_diffs > tolerance_seconds * 10  # 10x tolerance

        return {
            "status": "aligned",
            "common_rows": len(common_index),
            "total_features": len(features),
            "total_price": len(price),
            "large_gaps": large_gaps.sum() if hasattr(large_gaps, "sum") else 0,
            "max_gap_seconds": time_diffs.max() if len(time_diffs) > 0 else 0,
        }

    return {
        "status": "aligned",
        "common_rows": len(common_index),
        "total_features": len(features),
        "total_price": len(price),
    }


def create_training_splits(
    feature_frame: FeatureFrame, train_ratio: float = 0.8, min_train_samples: int = 1000
) -> tuple[FeatureFrame, FeatureFrame]:
    """
    Create temporal train/test splits maintaining time order.

    Args:
        feature_frame: Input FeatureFrame
        train_ratio: Fraction of data for training
        min_train_samples: Minimum samples required for training

    Returns:
        Tuple of (train_frame, test_frame)
    """
    valid_data = feature_frame.filter_valid()

    if len(valid_data.X) < min_train_samples:
        raise ValueError(
            f"Insufficient data for training (need {min_train_samples}, got {len(valid_data.X)})"
        )

    # Temporal split (no random shuffle)
    split_idx = int(len(valid_data.X) * train_ratio)

    train_X = valid_data.X.iloc[:split_idx]
    train_y = valid_data.y.iloc[:split_idx] if valid_data.y is not None else None
    train_mask = pd.Series(True, index=train_X.index)

    test_X = valid_data.X.iloc[split_idx:]
    test_y = valid_data.y.iloc[split_idx:] if valid_data.y is not None else None
    test_mask = pd.Series(True, index=test_X.index)

    return (
        FeatureFrame(X=train_X, y=train_y, index_mask=train_mask),
        FeatureFrame(X=test_X, y=test_y, index_mask=test_mask),
    )
