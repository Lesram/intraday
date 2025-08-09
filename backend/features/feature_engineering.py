"""
Feature Engineering Pipeline for Technical Indicators & Feature Enrichment.
Computes comprehensive technical indicators and market features for ML models.
"""

import warnings
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# Try to import TA-Lib, fallback to pandas-based calculations
try:
    import talib

    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    talib = None

from ..utils.helpers import (
    bollinger_bands,
    exponential_moving_average,
    rsi,
    safe_divide,
)
from ..utils.logger import get_structured_logger, performance_logger


class FeatureEngineer:
    """
    Feature engineering pipeline for market data.
    Computes technical indicators, market regime features, and sentiment features.
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize feature engineer with configuration.

        Args:
            config: Configuration dictionary with indicator parameters
        """
        self.logger = get_structured_logger("feature_engineer")

        # Default configuration
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
            # Lookback periods for features
            "lookback_periods": [5, 10, 20],
            # Feature normalization
            "normalize_features": True,
            "normalization_method": "zscore",  # 'zscore', 'minmax', 'robust'
            "normalization_window": 252,  # 1 year
        }

        # Update with provided config
        if config:
            self.config.update(config)

        self.logger.info(
            "Feature engineer initialized",
            talib_available=TALIB_AVAILABLE,
            config=self.config,
        )

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
            # 1. Moving Averages
            result_df = self._add_moving_averages(result_df)

            # 2. Momentum Indicators
            result_df = self._add_momentum_indicators(result_df)

            # 3. Volatility Indicators
            result_df = self._add_volatility_indicators(result_df)

            # 4. Volume Indicators
            result_df = self._add_volume_indicators(result_df)

            # 5. Oscillators
            result_df = self._add_oscillators(result_df)

            # 6. Market Regime Indicators
            result_df = self._add_market_regime_indicators(result_df)

            # 7. Price-based Features
            result_df = self._add_price_features(result_df)

            # 8. Lookback Features
            result_df = self._add_lookback_features(result_df)

            # 9. Normalize features if requested
            if self.config.get("normalize_features", False):
                result_df = self._normalize_features(result_df)

            # Drop rows with NaN values (from indicator calculations)
            initial_rows = len(result_df)
            result_df = result_df.dropna()
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
                df["ema_convergence"] = df[fast_ema] - df[slow_ema]

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
                df["macd_histogram"] = df["macd"] - df["macd_signal"]

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
                (df["close"] - df["close"].shift(10)) / df["close"].shift(10)
            ) * 100
            df["roc_20"] = (
                (df["close"] - df["close"].shift(20)) / df["close"].shift(20)
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
            high_low = df["high"] - df["low"]
            high_close = np.abs(df["high"] - df["close"].shift(1))
            low_close = np.abs(df["low"] - df["close"].shift(1))
            tr = np.maximum(high_low, np.maximum(high_close, low_close))
            df["atr"] = tr.rolling(window=self.config["atr_period"]).mean()

        # ATR ratio to price
        df["atr_ratio"] = df["atr"] / df["close"]

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
        df["bb_position"] = (df["close"] - df["bb_lower"]) / (
            df["bb_upper"] - df["bb_lower"]
        )
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]

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
                (df["close"] - lowest_low) / (highest_high - lowest_low)
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
            # Manual CCI calculation
            period = self.config["cci_period"]
            typical_price = (df["high"] + df["low"] + df["close"]) / 3
            sma_tp = typical_price.rolling(window=period).mean()
            mad = typical_price.rolling(window=period).apply(
                lambda x: np.mean(np.abs(x - x.mean()))
            )
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
            price_range = df["high"] - df["low"]
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

        for col in feature_cols:
            if df[col].dtype in ["float64", "int64"]:
                if method == "zscore":
                    rolling_mean = df[col].rolling(window=window, min_periods=20).mean()
                    rolling_std = df[col].rolling(window=window, min_periods=20).std()
                    df[f"{col}_norm"] = (df[col] - rolling_mean) / rolling_std
                elif method == "minmax":
                    rolling_min = df[col].rolling(window=window, min_periods=20).min()
                    rolling_max = df[col].rolling(window=window, min_periods=20).max()
                    df[f"{col}_norm"] = (df[col] - rolling_min) / (
                        rolling_max - rolling_min
                    )
                elif method == "robust":
                    rolling_median = (
                        df[col].rolling(window=window, min_periods=20).median()
                    )
                    rolling_mad = (
                        df[col]
                        .rolling(window=window, min_periods=20)
                        .apply(lambda x: np.median(np.abs(x - np.median(x))))
                    )
                    df[f"{col}_norm"] = (df[col] - rolling_median) / rolling_mad

        return df

    def add_sentiment_features(
        self, df: pd.DataFrame, sentiment_data: Dict[str, float]
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

    def get_feature_importance_ranking(
        self, df: pd.DataFrame, target_column: str = "returns"
    ) -> Dict[str, float]:
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
    ) -> List[str]:
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
