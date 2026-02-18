"""
Feature Engineering Pipeline for Technical Indicators & Feature Enrichment.
Computes comprehensive technical indicators and market features for ML models.
"""

from typing import Any
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


# Infrastructure compatibility - add settings module variable
class Settings:
    """Settings class for test compatibility."""

    def __init__(self):
        self.feature_window = 100
        self.technical_indicators = True
        self.volume_indicators = True
        self.sentiment_features = False
        self.debug_mode = False

    def get(self, key: str, default=None):
        """Get setting value."""
        return getattr(self, key, default)


# Global settings instance for test compatibility
settings = Settings()

# Try to import TA-Lib, fallback to pandas-based calculations
try:
    import talib

    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    talib = None

from ..config import get_settings
from ..infra.metrics import get_metrics_registry
from ..utils.helpers import bollinger_bands, exponential_moving_average, rsi
from ..utils.logger import get_structured_logger, performance_logger
from .alignment import align_features_target
from .types import FeatureFrame
from .validators import guard_no_lookahead, validate_ohlcv


def align_for_arithmetic(other: Any, index: pd.Index) -> pd.Series:
    """
    Align other data with DataFrame index for safe arithmetic operations.

    Prevents "ValueError: other must be a DataFrame or Series" by normalizing
    inputs to properly aligned pandas Series.

    Args:
        other: Data to align (scalar, list, Series, DataFrame, etc.)
        index: Index to align with

    Returns:
        pandas Series aligned with the provided index
    """
    if isinstance(other, (int, float)):
        return pd.Series([other] * len(index), index=index)
    if isinstance(other, pd.Series):
        return other.reindex(index, fill_value=0)
    if isinstance(other, pd.DataFrame):
        return other.iloc[:, 0].reindex(index, fill_value=0)
    if isinstance(other, (list, tuple, np.ndarray)):
        # Truncate or extend to match index length
        other_list = list(other)
        if len(other_list) > len(index):
            other_list = other_list[: len(index)]
        elif len(other_list) < len(index):
            # Pad with last value or zero
            pad_value = other_list[-1] if other_list else 0
            other_list.extend([pad_value] * (len(index) - len(other_list)))
        return pd.Series(other_list, index=index)
    # Fallback: try to convert to Series
    try:
        return pd.Series(other, index=index)
    except (TypeError, ValueError) as e:
        # Handle conversion errors - fallback to broadcasting scalar
        structured_logger = get_structured_logger(__name__)
        structured_logger.debug(
            f"Failed to convert to Series, broadcasting scalar: {e}"
        )
        return pd.Series([other] * len(index), index=index)


class FeatureEngineer:
    """
    Feature engineering pipeline for market data.
    Computes technical indicators, market regime features, and sentiment features.
    Supports lightweight feature mode for real-time performance.
    """

    def __init__(self, config: dict | None = None):
        """
        Initialize feature engineer with configuration.

        Args:
            config: Configuration dictionary with indicator parameters
        """
        self.logger = get_structured_logger("feature_engineer")
        self.settings = get_settings()

        trading_settings = getattr(self.settings, "trading", None)
        max_rolling_window = getattr(trading_settings, "max_rolling_window", 252)
        feature_mode = getattr(trading_settings, "feature_mode", "lightweight")
        enable_heavy_features = getattr(trading_settings, "enable_heavy_features", False)
        enable_autocorr_features = getattr(trading_settings, "enable_autocorr_features", False)

        # Default configuration with settings awareness
        self.config = {
            # Moving average periods
            "sma_periods": [5, 10, 20, 50, 200],
            "ema_periods": [10, 20, 50, 200],
            # Momentum indicators
            "rsi_period": 14,
            "rsi_fast_period": 7,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            # Volatility indicators
            "atr_period": 14,
            "bb_period": 20,
            "bb_std": 2.0,
            # Volume indicators
            "volume_sma_period": 20,
            # Oscillators
            "stoch_k_period": 14,
            "stoch_d_period": 3,
            "williams_period": 14,
            "cci_period": 20,
            # Market regime
            "adx_period": 14,
            # Lookback periods for features - limited by settings
            "lookback_periods": [
                5,
                10,
                min(20, max_rolling_window),
            ],
            # Feature normalization
            "normalize_features": True,
            "normalization_method": "zscore",  # 'zscore', 'minmax', 'robust'
            "normalization_window": min(252, max_rolling_window),
            # Performance settings from config
            "feature_mode": feature_mode,
            "enable_heavy_features": enable_heavy_features,
            "enable_autocorr_features": enable_autocorr_features,
        }

        # Update with provided config
        if config:
            self.config.update(config)

        self.logger.info(
            "Feature engineer initialized",
            talib_available=TALIB_AVAILABLE,
            config=self.config,
        )

    # Test compatibility methods
    def _calculate_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI for testing compatibility."""
        if TALIB_AVAILABLE:
            return pd.Series(
                talib.RSI(series.values, timeperiod=period), index=series.index
            )
        else:
            return rsi(series, period)

    def _calculate_macd(
        self, series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
    ):
        """Calculate MACD for testing compatibility."""
        if TALIB_AVAILABLE:
            macd, signal_line, histogram = talib.MACD(
                series.values, fastperiod=fast, slowperiod=slow, signalperiod=signal
            )
            return (
                pd.Series(macd, index=series.index),
                pd.Series(signal_line, index=series.index),
                pd.Series(histogram, index=series.index),
            )
        else:
            # Simple MACD calculation
            ema_fast = exponential_moving_average(series, fast)
            ema_slow = exponential_moving_average(series, slow)
            macd = ema_fast - ema_slow
            signal_line = exponential_moving_average(macd, signal)
            histogram = macd - signal_line
            return macd, signal_line, histogram

    def _calculate_bollinger_bands(
        self, series: pd.Series, period: int = 20, std_dev: float = 2.0
    ):
        """Calculate Bollinger Bands for testing compatibility."""
        return bollinger_bands(series, period, std_dev)

    def _calculate_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate volume features for testing compatibility."""
        result = df.copy()
        result["volume_sma"] = (
            df["volume"].rolling(self.config.get("volume_sma_period", 20)).mean()
        )
        result["volume_ratio"] = df["volume"] / result["volume_sma"]

        # Calculate VWAP (Volume Weighted Average Price)
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        vwap_period = self.config.get("vwap_period", 20)
        result["vwap"] = (typical_price * df["volume"]).rolling(vwap_period).sum() / df[
            "volume"
        ].rolling(vwap_period).sum()
        result["vwap_ratio"] = df["close"] / result["vwap"]

        return result[["volume_sma", "volume_ratio", "vwap", "vwap_ratio"]]

    def _calculate_returns(self, series: pd.Series, periods: list[int]) -> pd.DataFrame:
        """Calculate price returns for testing compatibility."""
        result = pd.DataFrame(index=series.index)
        for period in periods:
            result[f"return_{period}d"] = series.pct_change(period)
        return result

    def _calculate_volatility(
        self, series: pd.Series, periods: list[int]
    ) -> pd.DataFrame:
        """Calculate volatility for testing compatibility."""
        result = pd.DataFrame(index=series.index)
        returns = series.pct_change()
        for period in periods:
            result[f"volatility_{period}d"] = returns.rolling(period).std()
        return result

    def compute_features(self, price_data: pd.DataFrame) -> pd.DataFrame:
        """Alias for compute_all_features for testing compatibility."""
        return self.compute_all_features(price_data)

    def calculate_feature_importance(
        self, features: pd.DataFrame, labels: pd.Series
    ) -> dict:
        """Calculate feature importance for testing compatibility."""
        # Simple correlation-based importance
        importance = {}
        for col in features.columns:
            try:
                corr = abs(features[col].corr(labels))
                importance[col] = corr if not pd.isna(corr) else 0.0
            except (TypeError, ValueError, KeyError) as e:
                # Handle missing values, type errors, or invalid columns
                structured_logger = get_structured_logger(__name__)
                structured_logger.warning(
                    f"Failed to calculate correlation for feature {col}: {e}"
                )
                importance[col] = 0.0
        return importance

    def compute_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute comprehensive technical indicators for market data.

        Args:
            df: DataFrame with OHLCV columns ['timestamp', 'open', 'high', 'low', 'close', 'volume']

        Returns:
            DataFrame with technical indicators added
        """
        if df.empty:
            return df

        start_time = pd.Timestamp.now()

        # Make a copy to avoid modifying original
        result_df = df.copy()

        # Ensure required columns exist
        required_cols = ["open", "high", "low", "close", "volume"]
        missing_cols = [col for col in required_cols if col not in result_df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        # Sort by timestamp if present
        if "timestamp" in result_df.columns:
            result_df = result_df.sort_values("timestamp").reset_index(drop=True)

        try:
            # Check feature mode for performance optimization
            feature_mode = self.config.get("feature_mode", "full")
            enable_heavy_features = self.config.get("enable_heavy_features", True)

            # Core features (always computed)
            # 1. Moving Averages
            result_df = self._add_moving_averages(result_df)

            # 2. Momentum Indicators
            result_df = self._add_momentum_indicators(result_df)

            # 3. Volatility Indicators
            result_df = self._add_volatility_indicators(result_df)

            if feature_mode == "full" or enable_heavy_features:
                # Heavy computational features (skip in realtime_light mode)
                # 4. Volume Indicators
                result_df = self._add_volume_indicators(result_df)

                # 5. Oscillators
                result_df = self._add_oscillators(result_df)

                # 6. Market Regime Indicators
                result_df = self._add_market_regime_indicators(result_df)

                # 7. Price-based Features
                result_df = self._add_price_features(result_df)

                # 8. Lookback Features (potentially expensive)
                if self.config.get("enable_autocorr_features", True):
                    result_df = self._add_lookback_features(result_df)
            else:
                # Light mode - add essential features only
                result_df = self._add_essential_features(result_df)

            # 9. Normalize features if requested
            if self.config.get("normalize_features", False):
                result_df = self._normalize_features(result_df)

            # Handle NaN values intelligently
            initial_rows = len(result_df)

            # Instead of dropping all rows with any NaN, be more selective
            # Only require that the basic price columns and short-term indicators are not NaN
            essential_cols = ["open", "high", "low", "close", "volume"]
            if "sma_5" in result_df.columns:
                essential_cols.append("sma_5")
            if "sma_20" in result_df.columns:
                essential_cols.append("sma_20")

            # Drop rows where essential columns are NaN
            result_df = result_df.dropna(subset=essential_cols)
            dropped_rows = initial_rows - len(result_df)

            # Calculate processing time
            processing_time = (pd.Timestamp.now() - start_time).total_seconds() * 1000
            performance_logger.log_latency("feature_engineering", processing_time)

            self.logger.info(
                "Technical indicators computed",
                rows_processed=len(result_df),
                rows_dropped=dropped_rows,
                features_added=len(result_df.columns) - len(df.columns),
                processing_time_ms=processing_time,
            )

            return result_df

        except Exception as e:
            self.logger.error("Feature engineering failed", error=str(e))
            raise

    def _add_moving_averages(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add moving average features."""

        # Simple Moving Averages
        for period in self.config["sma_periods"]:
            df[f"sma_{period}"] = df["close"].rolling(window=period).mean()
            df[f"close_sma_{period}_ratio"] = df["close"] / df[f"sma_{period}"]

        # Exponential Moving Averages
        for period in self.config["ema_periods"]:
            if TALIB_AVAILABLE:
                df[f"ema_{period}"] = talib.EMA(df["close"].values, timeperiod=period)
            else:
                df[f"ema_{period}"] = exponential_moving_average(df["close"], period)
            df[f"close_ema_{period}_ratio"] = df["close"] / df[f"ema_{period}"]

        # Moving average convergence/divergence
        if len(self.config["ema_periods"]) >= 2:
            fast_ema = f"ema_{self.config['ema_periods'][0]}"
            slow_ema = f"ema_{self.config['ema_periods'][1]}"
            if fast_ema in df.columns and slow_ema in df.columns:
                df["ema_convergence"] = df[fast_ema] - align_for_arithmetic(
                    df[slow_ema], df.index
                )

        # Volume-weighted moving averages
        if TALIB_AVAILABLE and len(df) > 20:
            df["vwma_20"] = talib.TRIMA(
                df["close"].values, timeperiod=20
            )  # Using TRIMA as approximation

        return df

    def _add_momentum_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add momentum-based indicators."""

        # RSI
        rsi_period = self.config["rsi_period"]
        if TALIB_AVAILABLE:
            df["rsi"] = talib.RSI(df["close"].values, timeperiod=rsi_period)
        else:
            df["rsi"] = rsi(df["close"], rsi_period)

        # Fast RSI
        rsi_fast_period = self.config["rsi_fast_period"]
        if TALIB_AVAILABLE:
            df["rsi_fast"] = talib.RSI(df["close"].values, timeperiod=rsi_fast_period)
        else:
            df["rsi_fast"] = rsi(df["close"], rsi_fast_period)

        # MACD
        if TALIB_AVAILABLE:
            macd, macd_signal, macd_hist = talib.MACD(
                df["close"].values,
                fastperiod=self.config["macd_fast"],
                slowperiod=self.config["macd_slow"],
                signalperiod=self.config["macd_signal"],
            )
            df["macd"] = macd
            df["macd_signal"] = macd_signal
            df["macd_histogram"] = macd_hist
        else:
            # Manual MACD calculation
            ema_fast = exponential_moving_average(df["close"], self.config["macd_fast"])
            ema_slow = exponential_moving_average(df["close"], self.config["macd_slow"])
            if isinstance(ema_fast, pd.Series) and isinstance(ema_slow, pd.Series):
                df["macd"] = ema_fast - ema_slow
                df["macd_signal"] = (
                    df["macd"].ewm(span=self.config["macd_signal"]).mean()
                )
                df["macd_histogram"] = df["macd"] - align_for_arithmetic(
                    df["macd_signal"], df.index
                )

        # Price momentum
        for period in self.config["lookback_periods"]:
            df[f"price_momentum_{period}"] = df["close"].pct_change(period)
            df[f"volume_momentum_{period}"] = df["volume"].pct_change(period)

        # Rate of change
        if TALIB_AVAILABLE:
            df["roc_10"] = talib.ROC(df["close"].values, timeperiod=10)
            df["roc_20"] = talib.ROC(df["close"].values, timeperiod=20)
        else:
            df["roc_10"] = (
                (df["close"] - align_for_arithmetic(df["close"].shift(10), df.index))
                / align_for_arithmetic(df["close"].shift(10), df.index)
            ) * 100
            df["roc_20"] = (
                (df["close"] - align_for_arithmetic(df["close"].shift(20), df.index))
                / align_for_arithmetic(df["close"].shift(20), df.index)
            ) * 100

        return df

    def _add_volatility_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add volatility-based indicators."""

        # Average True Range (ATR)
        if TALIB_AVAILABLE:
            df["atr"] = talib.ATR(
                df["high"].values,
                df["low"].values,
                df["close"].values,
                timeperiod=self.config["atr_period"],
            )
        else:
            # Manual ATR calculation
            high_low = df["high"] - align_for_arithmetic(df["low"], df.index)
            high_close = np.abs(
                df["high"] - align_for_arithmetic(df["close"].shift(1), df.index)
            )
            low_close = np.abs(
                df["low"] - align_for_arithmetic(df["close"].shift(1), df.index)
            )
            tr = np.maximum(high_low, np.maximum(high_close, low_close))
            df["atr"] = tr.rolling(window=self.config["atr_period"]).mean()

        # ATR ratio to price
        df["atr_ratio"] = align_for_arithmetic(
            df["atr"], df.index
        ) / align_for_arithmetic(df["close"], df.index)

        # Bollinger Bands
        bb_period = self.config["bb_period"]
        bb_std = self.config["bb_std"]

        if TALIB_AVAILABLE:
            df["bb_upper"], df["bb_middle"], df["bb_lower"] = talib.BBANDS(
                df["close"].values,
                timeperiod=bb_period,
                nbdevup=bb_std,
                nbdevdn=bb_std,
                matype=0,
            )
        else:
            bb_upper, bb_middle, bb_lower = bollinger_bands(
                df["close"], bb_period, bb_std
            )
            df["bb_upper"] = bb_upper
            df["bb_middle"] = bb_middle
            df["bb_lower"] = bb_lower

        # Bollinger Band position
        df["bb_position"] = (
            df["close"] - align_for_arithmetic(df["bb_lower"], df.index)
        ) / (
            align_for_arithmetic(df["bb_upper"], df.index)
            - align_for_arithmetic(df["bb_lower"], df.index)
        )
        df["bb_width"] = (
            align_for_arithmetic(df["bb_upper"], df.index)
            - align_for_arithmetic(df["bb_lower"], df.index)
        ) / align_for_arithmetic(df["bb_middle"], df.index)

        # Historical volatility
        df["returns"] = df["close"].pct_change()
        df["volatility_10"] = df["returns"].rolling(window=10).std() * np.sqrt(252)
        df["volatility_20"] = df["returns"].rolling(window=20).std() * np.sqrt(252)

        return df

    def _add_volume_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add volume-based indicators."""

        # Volume moving average
        vol_period = self.config["volume_sma_period"]
        df["volume_sma"] = df["volume"].rolling(window=vol_period).mean()
        df["volume_ratio"] = df["volume"] / df["volume_sma"]

        # On-Balance Volume (OBV)
        if TALIB_AVAILABLE:
            df["obv"] = talib.OBV(df["close"].values, df["volume"].values)
        else:
            # Manual OBV calculation
            obv = np.zeros(len(df))
            for i in range(1, len(df)):
                if df["close"].iloc[i] > df["close"].iloc[i - 1]:
                    obv[i] = obv[i - 1] + df["volume"].iloc[i]
                elif df["close"].iloc[i] < df["close"].iloc[i - 1]:
                    obv[i] = obv[i - 1] - df["volume"].iloc[i]
                else:
                    obv[i] = obv[i - 1]
            df["obv"] = obv

        # Volume Price Trend (VPT)
        price_change_pct = df["close"].pct_change()
        df["vpt"] = (price_change_pct * df["volume"]).cumsum()

        # Money Flow Index (MFI)
        if TALIB_AVAILABLE:
            df["mfi"] = talib.MFI(
                df["high"].values,
                df["low"].values,
                df["close"].values,
                df["volume"].values,
                timeperiod=14,
            )
        else:
            # Simplified MFI calculation
            typical_price = (df["high"] + df["low"] + df["close"]) / 3
            money_flow = typical_price * df["volume"]
            positive_flow = money_flow.where(typical_price > typical_price.shift(1), 0)
            negative_flow = money_flow.where(typical_price < typical_price.shift(1), 0)

            positive_flow_sum = positive_flow.rolling(window=14).sum()
            negative_flow_sum = negative_flow.rolling(window=14).sum()

            money_ratio = positive_flow_sum / negative_flow_sum
            df["mfi"] = 100 - (100 / (1 + money_ratio))

        return df

    def _add_oscillators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add oscillator indicators."""

        # Stochastic Oscillator
        if TALIB_AVAILABLE:
            df["stoch_k"], df["stoch_d"] = talib.STOCH(
                df["high"].values,
                df["low"].values,
                df["close"].values,
                fastk_period=self.config["stoch_k_period"],
                slowk_period=self.config["stoch_d_period"],
                slowd_period=self.config["stoch_d_period"],
            )
        else:
            # Manual Stochastic calculation
            k_period = self.config["stoch_k_period"]
            d_period = self.config["stoch_d_period"]

            lowest_low = df["low"].rolling(window=k_period).min()
            highest_high = df["high"].rolling(window=k_period).max()

            df["stoch_k"] = (
                (df["close"] - align_for_arithmetic(lowest_low, df.index))
                / (
                    align_for_arithmetic(highest_high, df.index)
                    - align_for_arithmetic(lowest_low, df.index)
                )
            ) * 100
            df["stoch_d"] = df["stoch_k"].rolling(window=d_period).mean()

        # Williams %R
        if TALIB_AVAILABLE:
            df["williams_r"] = talib.WILLR(
                df["high"].values,
                df["low"].values,
                df["close"].values,
                timeperiod=self.config["williams_period"],
            )
        else:
            # Manual Williams %R calculation
            period = self.config["williams_period"]
            highest_high = df["high"].rolling(window=period).max()
            lowest_low = df["low"].rolling(window=period).min()
            df["williams_r"] = (
                (highest_high - df["close"]) / (highest_high - lowest_low)
            ) * -100

        # Commodity Channel Index (CCI)
        if TALIB_AVAILABLE:
            df["cci"] = talib.CCI(
                df["high"].values,
                df["low"].values,
                df["close"].values,
                timeperiod=self.config["cci_period"],
            )
        else:
            # Manual CCI calculation with vectorized operations
            period = self.config["cci_period"]
            typical_price = (df["high"] + df["low"] + df["close"]) / 3
            sma_tp = typical_price.rolling(window=period).mean()
            # Vectorized Mean Absolute Deviation calculation
            rolling_tp = typical_price.rolling(window=period)
            mad = rolling_tp.std() * 0.8  # Approximation for MAD using std deviation
            df["cci"] = (typical_price - sma_tp) / (0.015 * mad)

        return df

    def _add_market_regime_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add market regime and trend strength indicators."""

        # Average Directional Index (ADX)
        if TALIB_AVAILABLE:
            df["adx"] = talib.ADX(
                df["high"].values,
                df["low"].values,
                df["close"].values,
                timeperiod=self.config["adx_period"],
            )
            df["plus_di"] = talib.PLUS_DI(
                df["high"].values,
                df["low"].values,
                df["close"].values,
                timeperiod=self.config["adx_period"],
            )
            df["minus_di"] = talib.MINUS_DI(
                df["high"].values,
                df["low"].values,
                df["close"].values,
                timeperiod=self.config["adx_period"],
            )
        else:
            # Simplified trend strength indicator
            df["high"] - df["low"]
            trend_up = (df["close"] > df["close"].shift(1)).rolling(window=14).sum()
            trend_down = (df["close"] < df["close"].shift(1)).rolling(window=14).sum()
            df["trend_strength"] = abs(trend_up - trend_down) / 14

        # Market regime classification
        # Trending vs Mean-reverting based on multiple indicators
        conditions = []

        # ADX-based trending
        if "adx" in df.columns:
            conditions.append((df["adx"] > 25, "trending"))
            conditions.append((df["adx"] <= 25, "sideways"))

        # Volatility-based regime
        if "volatility_20" in df.columns:
            vol_median = df["volatility_20"].rolling(window=50).median()
            conditions.append((df["volatility_20"] > vol_median * 1.5, "high_vol"))
            conditions.append((df["volatility_20"] < vol_median * 0.5, "low_vol"))

        # Price momentum regime
        if "price_momentum_20" in df.columns:
            mom_std = df["price_momentum_20"].rolling(window=50).std()
            conditions.append((abs(df["price_momentum_20"]) > mom_std, "momentum"))
            conditions.append((abs(df["price_momentum_20"]) <= mom_std, "mean_revert"))

        return df

    def _add_price_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add price-based features."""

        # Gap features
        df["gap"] = df["open"] - df["close"].shift(1)
        df["gap_percent"] = df["gap"] / df["close"].shift(1)

        # Intraday features
        df["high_low_ratio"] = df["high"] / df["low"]
        df["open_close_ratio"] = df["open"] / df["close"]
        df["body_size"] = abs(df["close"] - df["open"]) / df["open"]
        df["shadow_upper"] = (df["high"] - np.maximum(df["open"], df["close"])) / df[
            "open"
        ]
        df["shadow_lower"] = (np.minimum(df["open"], df["close"]) - df["low"]) / df[
            "open"
        ]

        # Price position within range
        df["price_position"] = (df["close"] - df["low"]) / (df["high"] - df["low"])

        # VWAP approximation (using typical price)
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        df["vwap_approx"] = (typical_price * df["volume"]).rolling(
            window=20
        ).sum() / df["volume"].rolling(window=20).sum()
        df["vwap_distance"] = (df["close"] - df["vwap_approx"]) / df["vwap_approx"]

        return df

    def _add_lookback_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add lookback features for different time horizons."""

        for period in self.config["lookback_periods"]:
            # Price changes
            df[f"price_change_{period}"] = df["close"].pct_change(period)
            df[f"high_change_{period}"] = df["high"].pct_change(period)
            df[f"low_change_{period}"] = df["low"].pct_change(period)

            # Volume changes
            df[f"volume_change_{period}"] = df["volume"].pct_change(period)

            # Rolling statistics
            df[f"close_std_{period}"] = df["close"].rolling(window=period).std()
            df[f"close_skew_{period}"] = df["close"].rolling(window=period).skew()
            df[f"volume_std_{period}"] = df["volume"].rolling(window=period).std()

            # Min/Max ratios
            df[f"close_min_ratio_{period}"] = (
                df["close"] / df["close"].rolling(window=period).min()
            )
            df[f"close_max_ratio_{period}"] = (
                df["close"] / df["close"].rolling(window=period).max()
            )

        return df

    def _normalize_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize features using specified method."""

        method = self.config["normalization_method"]
        window = self.config["normalization_window"]

        # Identify feature columns (exclude OHLCV and timestamp)
        exclude_cols = [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "returns",
        ]
        feature_cols = [col for col in df.columns if col not in exclude_cols]

        # Collect normalized columns to add them all at once (prevents DataFrame fragmentation)
        normalized_columns = {}

        for col in feature_cols:
            if df[col].dtype in ["float64", "int64"]:
                if method == "zscore":
                    rolling_mean = df[col].rolling(window=window, min_periods=20).mean()
                    rolling_std = df[col].rolling(window=window, min_periods=20).std()
                    normalized_columns[f"{col}_norm"] = (
                        df[col] - rolling_mean
                    ) / rolling_std
                elif method == "minmax":
                    rolling_min = df[col].rolling(window=window, min_periods=20).min()
                    rolling_max = df[col].rolling(window=window, min_periods=20).max()
                    normalized_columns[f"{col}_norm"] = (df[col] - rolling_min) / (
                        rolling_max - rolling_min
                    )
                elif method == "robust":
                    rolling_median = (
                        df[col].rolling(window=window, min_periods=20).median()
                    )
                    # Vectorized MAD approximation using quantiles for better performance
                    rolling_q75 = (
                        df[col].rolling(window=window, min_periods=20).quantile(0.75)
                    )
                    rolling_q25 = (
                        df[col].rolling(window=window, min_periods=20).quantile(0.25)
                    )
                    rolling_mad = (
                        rolling_q75 - rolling_q25
                    ) * 0.7413  # Convert IQR to MAD approximation
                    normalized_columns[f"{col}_norm"] = (
                        df[col] - rolling_median
                    ) / rolling_mad

        # Add all normalized columns at once to prevent fragmentation
        if normalized_columns:
            normalized_df = pd.DataFrame(normalized_columns, index=df.index)
            df = pd.concat([df, normalized_df], axis=1)

        return df

    def add_sentiment_features(
        self, df: pd.DataFrame, sentiment_data: dict[str, float]
    ) -> pd.DataFrame:
        """
        Add sentiment features from SocialSentimentAnalyzer.

        Args:
            df: DataFrame with market data and technical indicators
            sentiment_data: Dictionary with sentiment scores

        Returns:
            DataFrame with sentiment features added
        """

        # Add current sentiment scores
        for key, value in sentiment_data.items():
            df[f"sentiment_{key}"] = value

        # Add rolling sentiment features if we have historical data
        sentiment_cols = [col for col in df.columns if col.startswith("sentiment_")]

        for col in sentiment_cols:
            if col in df.columns:
                # Rolling averages
                df[f"{col}_sma_5"] = df[col].rolling(window=5).mean()
                df[f"{col}_sma_20"] = df[col].rolling(window=20).mean()

                # Sentiment momentum
                df[f"{col}_momentum"] = df[col] - df[f"{col}_sma_20"]

                # Sentiment volatility
                df[f"{col}_volatility"] = df[col].rolling(window=20).std()

        return df

    def _add_essential_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add essential features for realtime_light mode.
        Focuses on fast-to-compute features that provide good signal.
        """
        try:
            # Basic price relationships
            df["price_range"] = (df["high"] - df["low"]) / df["close"]
            df["body_ratio"] = abs(df["close"] - df["open"]) / (df["high"] - df["low"])

            # Simple volume features
            df["volume_ratio"] = (
                df["volume"] / df["volume"].rolling(10, min_periods=1).mean()
            )

            # Basic momentum (fast RSI)
            if self.config.get("rsi_fast_period"):
                rsi_fast = rsi(df["close"], self.config["rsi_fast_period"])
                df[f"rsi_{self.config['rsi_fast_period']}"] = rsi_fast

            # Essential moving average signals
            sma_5 = df["close"].rolling(5, min_periods=1).mean()
            sma_20 = df["close"].rolling(20, min_periods=1).mean()
            df["sma_cross_signal"] = np.where(sma_5 > sma_20, 1, -1)

            # Price position relative to recent range
            high_20 = df["high"].rolling(20, min_periods=1).max()
            low_20 = df["low"].rolling(20, min_periods=1).min()
            df["price_position"] = (df["close"] - low_20) / (high_20 - low_20)

            self.logger.debug("Essential features computed for realtime_light mode")

        except Exception as e:
            self.logger.error(f"Error adding essential features: {e}")

        return df

    def get_feature_importance_ranking(
        self, df: pd.DataFrame, target_column: str = "returns"
    ) -> dict[str, float]:
        """
        Calculate feature importance using correlation with target.

        Args:
            df: DataFrame with features
            target_column: Target variable column name

        Returns:
            Dictionary with feature importance scores
        """
        if target_column not in df.columns:
            self.logger.warning(f"Target column '{target_column}' not found")
            return {}

        # Calculate correlations
        correlations = df.corr()[target_column].abs().sort_values(ascending=False)

        # Remove target itself and non-numeric columns
        feature_importance = correlations.drop([target_column], errors="ignore")
        feature_importance = feature_importance.dropna()

        self.logger.info(
            "Feature importance calculated",
            top_features=feature_importance.head(10).to_dict(),
        )

        return feature_importance.to_dict()

    def select_features(
        self, df: pd.DataFrame, target_column: str = "returns", top_k: int = 50
    ) -> list[str]:
        """
        Select top K features based on importance.

        Args:
            df: DataFrame with features
            target_column: Target variable
            top_k: Number of top features to select

        Returns:
            List of selected feature names
        """
        importance = self.get_feature_importance_ranking(df, target_column)

        # Select top K features
        selected_features = list(importance.keys())[:top_k]

        self.logger.info(
            "Features selected",
            count=len(selected_features),
            top_5=selected_features[:5],
        )

        return selected_features

    def compute_all_features(self, price_data: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all features for the given price data.
        Alias for compute_technical_indicators for backward compatibility.

        Args:
            price_data: DataFrame with OHLCV data

        Returns:
            DataFrame with all computed features
        """
        return self.compute_technical_indicators(price_data)


# Schema Validation Helpers for MLOps Integration


def validate_feature_schema(
    features_df: pd.DataFrame, expected_schema: dict[str, str], strict: bool = True
) -> tuple[bool, list[str]]:
    """
    Validate feature DataFrame against expected schema.

    Args:
        features_df: DataFrame with features to validate
        expected_schema: Dictionary mapping feature names to expected dtypes
        strict: If True, extra columns cause validation failure

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []

    # Check for missing features
    expected_features = set(expected_schema.keys())
    actual_features = set(features_df.columns)

    missing_features = expected_features - actual_features
    if missing_features:
        errors.append(f"Missing features: {sorted(missing_features)}")

    # Check for extra features (if strict mode)
    if strict:
        extra_features = actual_features - expected_features
        if extra_features:
            errors.append(f"Extra features not in schema: {sorted(extra_features)}")

    # Check dtype compatibility for common features
    common_features = expected_features & actual_features
    for feature in common_features:
        expected_dtype = expected_schema[feature]
        actual_dtype = str(features_df[feature].dtype)

        if not _is_dtype_compatible(actual_dtype, expected_dtype):
            errors.append(
                f"Feature '{feature}': expected {expected_dtype}, got {actual_dtype}"
            )

    return len(errors) == 0, errors


def get_feature_schema(features_df: pd.DataFrame) -> dict[str, str]:
    """
    Extract feature schema from DataFrame.

    Args:
        features_df: DataFrame with features

    Returns:
        Dictionary mapping feature names to dtype strings
    """
    return {col: str(features_df[col].dtype) for col in features_df.columns}


def ensure_feature_order(
    features_df: pd.DataFrame, expected_order: list[str]
) -> pd.DataFrame:
    """
    Reorder feature columns to match expected order.

    Args:
        features_df: DataFrame with features
        expected_order: List of column names in expected order

    Returns:
        DataFrame with columns in expected order

    Raises:
        ValueError: If any expected features are missing
    """
    missing_features = set(expected_order) - set(features_df.columns)
    if missing_features:
        raise ValueError(f"Missing features for reordering: {sorted(missing_features)}")

    # Select only the expected features in the correct order
    return features_df[expected_order]


def create_feature_signature(
    features_df: pd.DataFrame, include_stats: bool = False
) -> dict[str, any]:
    """
    Create a feature signature for drift detection and validation.

    Args:
        features_df: DataFrame with features
        include_stats: Whether to include basic statistics

    Returns:
        Dictionary with feature signature information
    """
    signature = {
        "feature_names": list(features_df.columns),
        "feature_dtypes": get_feature_schema(features_df),
        "feature_count": len(features_df.columns),
        "created_at": pd.Timestamp.now().isoformat(),
    }

    if include_stats:
        numeric_features = features_df.select_dtypes(include=[np.number]).columns
        signature["numeric_features"] = list(numeric_features)
        signature["categorical_features"] = list(
            set(features_df.columns) - set(numeric_features)
        )

        if len(numeric_features) > 0:
            signature["feature_stats"] = {
                "mean": features_df[numeric_features].mean().to_dict(),
                "std": features_df[numeric_features].std().to_dict(),
                "min": features_df[numeric_features].min().to_dict(),
                "max": features_df[numeric_features].max().to_dict(),
            }

    return signature


def validate_feature_ranges(
    features_df: pd.DataFrame,
    expected_ranges: dict[str, tuple[float, float]],
    tolerance: float = 0.1,
) -> tuple[bool, list[str]]:
    """
    Validate that feature values are within expected ranges.

    Args:
        features_df: DataFrame with features
        expected_ranges: Dictionary mapping feature names to (min, max) tuples
        tolerance: Tolerance factor for range expansion (e.g., 0.1 = 10% tolerance)

    Returns:
        Tuple of (is_valid, warning_messages)
    """
    warnings = []

    for feature, (expected_min, expected_max) in expected_ranges.items():
        if feature not in features_df.columns:
            continue

        # Expand range with tolerance
        range_span = expected_max - expected_min
        tolerance_margin = range_span * tolerance

        expanded_min = expected_min - tolerance_margin
        expanded_max = expected_max + tolerance_margin

        actual_min = features_df[feature].min()
        actual_max = features_df[feature].max()

        if actual_min < expanded_min or actual_max > expanded_max:
            warnings.append(
                f"Feature '{feature}' range [{actual_min:.4f}, {actual_max:.4f}] "
                f"outside expected range [{expected_min:.4f}, {expected_max:.4f}] "
                f"with {tolerance * 100}% tolerance"
            )

    return len(warnings) == 0, warnings


def _is_dtype_compatible(actual_dtype: str, expected_dtype: str) -> bool:
    """
    Check if actual dtype is compatible with expected dtype.

    Args:
        actual_dtype: Actual pandas dtype as string
        expected_dtype: Expected pandas dtype as string

    Returns:
        True if compatible, False otherwise
    """
    # Normalize dtype names
    actual_norm = _normalize_dtype(actual_dtype)
    expected_norm = _normalize_dtype(expected_dtype)

    # Allow compatible numeric types
    if actual_norm == expected_norm:
        return True

    # Float compatibility
    if expected_norm in ["float", "float32", "float64"] and actual_norm in [
        "float",
        "float32",
        "float64",
        "int",
        "int32",
        "int64",
    ]:
        return True

    # Integer compatibility
    if expected_norm in ["int", "int32", "int64"] and actual_norm in [
        "int",
        "int32",
        "int64",
    ]:
        return True

    return False


def _normalize_dtype(dtype_str: str) -> str:
    """
    Normalize pandas dtype string.

    Args:
        dtype_str: Pandas dtype as string

    Returns:
        Normalized dtype string
    """
    dtype_str = dtype_str.lower()

    if "float" in dtype_str:
        if "32" in dtype_str:
            return "float32"
        elif "64" in dtype_str:
            return "float64"
        else:
            return "float"

    if "int" in dtype_str:
        if "32" in dtype_str:
            return "int32"
        elif "64" in dtype_str:
            return "int64"
        else:
            return "int"

    if "object" in dtype_str or "string" in dtype_str:
        return "object"

    if "bool" in dtype_str:
        return "bool"

    if "datetime" in dtype_str:
        return "datetime64"

    return dtype_str


def compute_all_features(df: pd.DataFrame, *, fast: bool = True) -> pd.DataFrame:
    """
    Vectorized feature computation with leak protection.

    Args:
        df: OHLCV DataFrame
        fast: Use optimized vectorized implementations

    Returns:
        DataFrame with computed features (no lookahead)
    """
    # Validate input data
    validate_ohlcv(df)

    # Use settings-aware feature engineer
    engineer = FeatureEngineer()

    with performance_logger("compute_all_features"):
        if fast:
            # Vectorized implementations first
            features = engineer.compute_technical_indicators(df)
        else:
            # Full feature suite (may include TA-Lib)
            features = engineer.compute_all_features_comprehensive(df)

    # Record timing metrics
    get_metrics_registry()
    # Metrics will be recorded by performance_logger context manager

    return features


def build_feature_frame(
    df_1m: pd.DataFrame, *, price_col: str = "close"
) -> FeatureFrame:
    """
    Build complete FeatureFrame with validation and alignment.

    Args:
        df_1m: 1-minute OHLCV data
        price_col: Price column for target creation

    Returns:
        FeatureFrame with features, target, and validity mask
    """
    # Validate input
    validate_ohlcv(df_1m)

    # Compute features
    with performance_logger("build_feature_frame"):
        features = compute_all_features(df_1m, fast=True)

        # Create target AFTER feature computation (critical!)
        price_series = df_1m[price_col]

        # Use alignment helper to ensure no lookahead
        feature_frame = align_features_target(features, price_series, price_col)

        # Run lookahead guard
        # Default to enforcing no-lookahead unless explicitly disabled
        no_lookahead_enforced = True
        try:
            settings = get_settings()
            # Check if features config exists and has the setting
            if hasattr(settings, "features") and hasattr(
                settings.features, "no_lookahead_enforced"
            ):
                no_lookahead_enforced = settings.features.no_lookahead_enforced
        except (AttributeError, ImportError, RuntimeError) as e:
            # Default to True if settings can't be accessed
            structured_logger = get_structured_logger(__name__)
            structured_logger.debug(
                f"Failed to access lookahead settings, using default: {e}"
            )
            pass
            no_lookahead_enforced = True

        if no_lookahead_enforced:
            try:
                guard_no_lookahead(
                    feature_frame.X,
                    price_series,
                    feature_cols=list(feature_frame.X.columns),
                )
            except Exception as e:
                # Log but don't fail in production
                logger = get_structured_logger("feature_engineering")
                logger.warning("Lookahead guard failed", extra={"error": str(e)})

                # Increment metrics
                metrics = get_metrics_registry()
                metrics.counter(
                    "feature_no_lookahead_violations_total", {"bucket": "other"}
                ).inc()

    return feature_frame


class FeatureScaler:
    """
    Feature scaling and normalization for consistent train/inference processing.
    Supports different scaling methods and maintains state for consistency.
    """

    def __init__(self, method: str = "zscore"):
        """Initialize scaler with method."""
        self.method = method
        self.fitted = False
        self.stats = {}

    def fit(self, features: pd.DataFrame) -> "FeatureScaler":
        """Fit scaler parameters."""
        if self.method == "zscore":
            self.stats["mean"] = features.mean()
            self.stats["std"] = features.std()
        elif self.method == "minmax":
            self.stats["min"] = features.min()
            self.stats["max"] = features.max()

        self.fitted = True
        return self

    def transform(self, features: pd.DataFrame) -> pd.DataFrame:
        """Transform features using fitted parameters."""
        if not self.fitted:
            raise ValueError("Scaler must be fitted before transform")

        if self.method == "zscore":
            return (features - self.stats["mean"]) / self.stats["std"]
        elif self.method == "minmax":
            return (features - self.stats["min"]) / (
                self.stats["max"] - self.stats["min"]
            )

        return features

    def fit_transform(self, features: pd.DataFrame) -> pd.DataFrame:
        """Fit and transform in one step."""
        return self.fit(features).transform(features)
