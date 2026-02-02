"""
ML Data Processing Module
Comprehensive data processing pipeline for machine learning in trading applications.
Handles data cleaning, preprocessing, feature engineering, and transformations.
"""

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class SimpleScaler:
    """Simple scaler implementation to replace sklearn dependency."""

    def __init__(self, method='standard'):
        self.method = method
        self.mean_ = None
        self.std_ = None
        self.min_ = None
        self.max_ = None
        self.median_ = None
        self.mad_ = None
        self.fitted = False

    def fit(self, X):
        """Fit the scaler to data."""
        if self.method == 'standard':
            self.mean_ = np.mean(X, axis=0)
            self.std_ = np.std(X, axis=0)
            self.scale_ = self.std_  # For compatibility
        elif self.method == 'minmax':
            self.min_ = np.min(X, axis=0)
            self.max_ = np.max(X, axis=0)
            self.scale_ = self.max_ - self.min_  # For compatibility
        elif self.method == 'robust':
            self.median_ = np.median(X, axis=0)
            self.mad_ = np.median(np.abs(X - self.median_), axis=0)
            self.scale_ = self.mad_  # For compatibility
        self.fitted = True
        return self

    def transform(self, X):
        """Transform data using fitted scaler."""
        if not self.fitted:
            raise ValueError("Scaler not fitted. Call fit() first.")

        if self.method == 'standard':
            return (X - self.mean_) / (self.std_ + 1e-8)
        elif self.method == 'minmax':
            return (X - self.min_) / (self.max_ - self.min_ + 1e-8)
        elif self.method == 'robust':
            return (X - self.median_) / (self.mad_ + 1e-8)

    def fit_transform(self, X):
        """Fit and transform in one step."""
        return self.fit(X).transform(X)


class SimpleImputer:
    """Simple imputer implementation to replace sklearn dependency."""

    def __init__(self, strategy='mean'):
        self.strategy = strategy
        self.fill_value_ = None
        self.fitted = False

    def fit(self, X):
        """Fit the imputer to data."""
        if X.ndim == 1:
            X = X.reshape(-1, 1)

        if self.strategy == 'mean':
            # Use simple mean calculation to avoid numpy compatibility issues
            self.fill_value_ = []
            for i in range(X.shape[1]):
                col_data = X[:, i]
                valid_data = col_data[~np.isnan(col_data)]
                if len(valid_data) > 0:
                    self.fill_value_.append(np.mean(valid_data))
                else:
                    self.fill_value_.append(0.0)
            self.fill_value_ = np.array(self.fill_value_)
        elif self.strategy == 'median':
            # Use simple median calculation
            self.fill_value_ = []
            for i in range(X.shape[1]):
                col_data = X[:, i]
                valid_data = col_data[~np.isnan(col_data)]
                if len(valid_data) > 0:
                    self.fill_value_.append(np.median(valid_data))
                else:
                    self.fill_value_.append(0.0)
            self.fill_value_ = np.array(self.fill_value_)
        elif self.strategy == 'most_frequent':
            # For simplicity, use median for numeric data
            self.fill_value_ = []
            for i in range(X.shape[1]):
                col_data = X[:, i]
                valid_data = col_data[~np.isnan(col_data)]
                if len(valid_data) > 0:
                    self.fill_value_.append(np.median(valid_data))
                else:
                    self.fill_value_.append(0.0)
            self.fill_value_ = np.array(self.fill_value_)
        self.fitted = True
        return self

    def transform(self, X):
        """Transform data using fitted imputer."""
        if not self.fitted:
            raise ValueError("Imputer not fitted. Call fit() first.")

        original_shape = X.shape
        if X.ndim == 1:
            X = X.reshape(-1, 1)

        X_filled = X.copy()
        for i in range(X.shape[1]):
            col_mask = np.isnan(X[:, i])
            if np.any(col_mask):
                X_filled[col_mask, i] = self.fill_value_[i]

        if len(original_shape) == 1:
            return X_filled.flatten()
        return X_filled

    def fit_transform(self, X):
        """Fit and transform in one step."""
        return self.fit(X).transform(X)


class DataProcessor:
    """Main data processor for ML pipelines."""

    def __init__(self, config: dict | None = None):
        """Initialize data processor with configuration."""
        self.config = config or {}
        self.scaler = None
        self.imputer = None
        self.feature_columns = []
        self.is_fitted = False

    def clean_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Clean raw market data."""
        if data is None or data.empty:
            raise ValueError("Data cannot be None or empty")

        cleaned = data.copy()

        # Remove duplicates
        initial_shape = cleaned.shape
        cleaned = cleaned.drop_duplicates()

        # Handle missing values in price columns
        price_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in price_columns:
            if col in cleaned.columns:
                # Forward fill then backward fill
                cleaned[col] = cleaned[col].fillna(method='ffill').fillna(method='bfill')

        # Remove rows with negative prices
        for col in ['open', 'high', 'low', 'close']:
            if col in cleaned.columns:
                cleaned = cleaned[cleaned[col] > 0]

        # Remove rows with zero volume
        if 'volume' in cleaned.columns:
            cleaned = cleaned[cleaned['volume'] >= 0]

        logger.info(f"Data cleaning: {initial_shape} -> {cleaned.shape}")
        return cleaned

    def preprocess_data(self, data: pd.DataFrame, fit: bool = True) -> pd.DataFrame:
        """Preprocess data for ML models."""
        if data is None or data.empty:
            raise ValueError("Data cannot be None or empty")

        processed = data.copy()

        # Handle datetime index
        if not isinstance(processed.index, pd.DatetimeIndex):
            if 'timestamp' in processed.columns:
                processed['timestamp'] = pd.to_datetime(processed['timestamp'])
                processed = processed.set_index('timestamp')
            elif 'date' in processed.columns:
                processed['date'] = pd.to_datetime(processed['date'])
                processed = processed.set_index('date')

        # Sort by timestamp
        processed = processed.sort_index()

        # Handle scaling
        numeric_columns = processed.select_dtypes(include=[np.number]).columns.tolist()
        if len(numeric_columns) > 0:
            if fit:
                self.scaler = SimpleScaler(method='standard')
                scaled_values = self.scaler.fit_transform(processed[numeric_columns].values)
                for i, col in enumerate(numeric_columns):
                    processed[col] = scaled_values[:, i]
                self.is_fitted = True
            elif self.scaler is not None:
                scaled_values = self.scaler.transform(processed[numeric_columns].values)
                for i, col in enumerate(numeric_columns):
                    processed[col] = scaled_values[:, i]
            else:
                raise ValueError("Scaler not fitted. Set fit=True for initial preprocessing.")

        return processed

    def engineer_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """Create technical indicators and features."""
        if data is None or data.empty:
            return data

        features = data.copy()

        # Price-based features
        if 'close' in features.columns:
            # Returns
            features['returns'] = features['close'].pct_change()
            features['log_returns'] = np.log(features['close'] / features['close'].shift(1))

            # Moving averages
            for window in [5, 10, 20, 50]:
                features[f'sma_{window}'] = features['close'].rolling(window=window).mean()
                features[f'ema_{window}'] = features['close'].ewm(span=window).mean()

            # Volatility
            features['volatility_10'] = features['returns'].rolling(window=10).std()
            features['volatility_20'] = features['returns'].rolling(window=20).std()

            # RSI
            features['rsi'] = self._calculate_rsi(features['close'])

        # Volume-based features
        if 'volume' in features.columns and 'close' in features.columns:
            features['volume_sma_10'] = features['volume'].rolling(window=10).mean()
            features['volume_ratio'] = features['volume'] / features['volume_sma_10']
            features['price_volume'] = features['close'] * features['volume']

        # OHLC-based features
        if all(col in features.columns for col in ['open', 'high', 'low', 'close']):
            # True Range
            features['true_range'] = self._calculate_true_range(features)
            # ATR
            features['atr'] = features['true_range'].rolling(window=14).mean()
            # Price position within range
            features['price_position'] = (features['close'] - features['low']) / (features['high'] - features['low'])

        self.feature_columns = features.columns.tolist()
        return features

    def _calculate_rsi(self, prices: pd.Series, window: int = 14) -> pd.Series:
        """Calculate Relative Strength Index."""
        delta = prices.diff()
        # Use mask-based approach to avoid the pandas 'where' issue
        gain = delta.copy()
        gain[gain < 0] = 0
        gain = gain.rolling(window=window).mean()

        loss = -delta.copy()
        loss[loss < 0] = 0
        loss = loss.rolling(window=window).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _calculate_true_range(self, data: pd.DataFrame) -> pd.Series:
        """Calculate True Range for ATR calculation."""
        high_low = data['high'] - data['low']
        high_close_prev = np.abs(data['high'] - data['close'].shift(1))
        low_close_prev = np.abs(data['low'] - data['close'].shift(1))
        true_range = np.maximum(high_low, np.maximum(high_close_prev, low_close_prev))
        return true_range

    def normalize_data(self, data: pd.DataFrame, method: str = 'standard') -> pd.DataFrame:
        """Normalize data using different scaling methods."""
        if data is None or data.empty:
            raise ValueError("Data cannot be None or empty")

        normalized = data.copy()
        numeric_columns = normalized.select_dtypes(include=[np.number]).columns.tolist()

        if len(numeric_columns) == 0:
            return normalized

        if method not in ['standard', 'minmax', 'robust']:
            raise ValueError(f"Unknown normalization method: {method}")

        scaler = SimpleScaler(method=method)
        scaled_values = scaler.fit_transform(normalized[numeric_columns].values)
        for i, col in enumerate(numeric_columns):
            normalized[col] = scaled_values[:, i]
        return normalized

    def validate_data(self, data: pd.DataFrame) -> dict[str, Any]:
        """Validate data quality and return metrics."""
        if data is None:
            return {"valid": False, "error": "Data is None"}

        if data.empty:
            return {"valid": False, "error": "Data is empty"}

        # Calculate missing values safely
        missing_values = {}
        for col in data.columns:
            missing_values[col] = int(data[col].isnull().sum())

        # Calculate duplicates safely
        try:
            duplicate_count = int(data.duplicated().sum())
        except (ValueError, TypeError, AttributeError):
            duplicate_count = 0

        validation_result = {
            "valid": True,
            "shape": data.shape,
            "missing_values": missing_values,
            "duplicates": duplicate_count,
            "data_types": {col: str(dtype) for col, dtype in data.dtypes.items()}
        }

        # Check for negative prices
        price_columns = ['open', 'high', 'low', 'close']
        negative_prices = {}
        for col in price_columns:
            if col in data.columns:
                negative_count = (data[col] < 0).sum()
                if negative_count > 0:
                    negative_prices[col] = negative_count

        if negative_prices:
            validation_result["negative_prices"] = negative_prices
            validation_result["valid"] = False

        # Check for infinite values
        infinite_values = {}
        numeric_columns = data.select_dtypes(include=[np.number]).columns
        for col in numeric_columns:
            inf_count = np.isinf(data[col]).sum()
            if inf_count > 0:
                infinite_values[col] = inf_count

        if infinite_values:
            validation_result["infinite_values"] = infinite_values
            validation_result["valid"] = False

        return validation_result

    def transform_data(self, data: pd.DataFrame, transformations: list[str]) -> pd.DataFrame:
        """Apply data transformations."""
        if data is None or data.empty:
            raise ValueError("Data cannot be None or empty")

        if not transformations:
            return data

        transformed = data.copy()

        for transformation in transformations:
            if transformation == 'log':
                numeric_columns = transformed.select_dtypes(include=[np.number]).columns
                for col in numeric_columns:
                    if (transformed[col] > 0).all():
                        transformed[f'{col}_log'] = np.log(transformed[col])

            elif transformation == 'diff':
                numeric_columns = transformed.select_dtypes(include=[np.number]).columns
                for col in numeric_columns:
                    transformed[f'{col}_diff'] = transformed[col].diff()

            elif transformation == 'pct_change':
                numeric_columns = transformed.select_dtypes(include=[np.number]).columns
                for col in numeric_columns:
                    transformed[f'{col}_pct'] = transformed[col].pct_change()

            else:
                logger.warning(f"Unknown transformation: {transformation}")

        return transformed


class DataPipeline:
    """End-to-end data processing pipeline."""

    def __init__(self, steps: list[str] | None = None):
        """Initialize pipeline with processing steps."""
        self.steps = steps or ['clean', 'preprocess', 'engineer_features']
        self.processor = DataProcessor()
        self.pipeline_fitted = False

    def fit(self, data: pd.DataFrame) -> 'DataPipeline':
        """Fit the pipeline on training data."""
        processed_data = data.copy()

        for step in self.steps:
            if step == 'clean':
                processed_data = self.processor.clean_data(processed_data)
            elif step == 'preprocess':
                processed_data = self.processor.preprocess_data(processed_data, fit=True)
            elif step == 'engineer_features':
                processed_data = self.processor.engineer_features(processed_data)

        self.pipeline_fitted = True
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Transform data using fitted pipeline."""
        if not self.pipeline_fitted:
            raise ValueError("Pipeline not fitted. Call fit() first.")

        processed_data = data.copy()

        for step in self.steps:
            if step == 'clean':
                processed_data = self.processor.clean_data(processed_data)
            elif step == 'preprocess':
                processed_data = self.processor.preprocess_data(processed_data, fit=False)
            elif step == 'engineer_features':
                processed_data = self.processor.engineer_features(processed_data)

        return processed_data

    def fit_transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Fit pipeline and transform data in one step."""
        return self.fit(data).transform(data)


def create_sample_data(n_rows: int = 100, start_date: str = '2023-01-01') -> pd.DataFrame:
    """Create sample market data for testing."""
    if n_rows <= 0:
        raise ValueError("n_rows must be positive")

    dates = pd.date_range(start=start_date, periods=n_rows, freq='1h')  # Use 'h' instead of deprecated 'H'

    # Generate realistic price data
    np.random.seed(42)
    base_price = 100.0
    returns = np.random.normal(0, 0.02, n_rows)
    prices = [base_price]

    for i in range(1, n_rows):
        prices.append(prices[-1] * (1 + returns[i]))

    # Create data with timestamp as index from the start
    data = pd.DataFrame({
        'open': prices,
        'high': [p * (1 + abs(np.random.normal(0, 0.01))) for p in prices],
        'low': [p * (1 - abs(np.random.normal(0, 0.01))) for p in prices],
        'close': prices,
        'volume': np.random.randint(1000, 10000, n_rows)
    }, index=dates)

    # Name the index
    data.index.name = 'timestamp'

    return data


def batch_process_data(data_batches: list[pd.DataFrame], pipeline: DataPipeline) -> list[pd.DataFrame]:
    """Process multiple data batches using the same pipeline."""
    if not data_batches:
        return []

    if not pipeline.pipeline_fitted:
        raise ValueError("Pipeline must be fitted before batch processing")

    processed_batches = []
    for batch in data_batches:
        try:
            processed_batch = pipeline.transform(batch)
            processed_batches.append(processed_batch)
        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            processed_batches.append(pd.DataFrame())  # Empty dataframe for failed batch

    return processed_batches
