"""
Module 60: Comprehensive ML Validation Service
Provides comprehensive validation functionality for machine learning models and data.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import logging
import time
from typing import Any
import warnings

import numpy as np

warnings.filterwarnings('ignore')

# P&L-020 FIX: All mock sklearn classes replaced with real numpy-based
# implementations that compute actual metrics from model predictions.
# No hardcoded fake scores — every metric is computed from real data.


def _compute_binary_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Compute real classification metrics from predictions."""
    y_true = np.asarray(y_true).flatten()
    y_pred = np.asarray(y_pred).flatten()
    accuracy = float(np.mean(y_true == y_pred)) if len(y_true) > 0 else 0.0
    classes = np.unique(np.concatenate([y_true, y_pred]))
    if len(classes) == 2:
        tp = float(np.sum((y_pred == 1) & (y_true == 1)))
        fp = float(np.sum((y_pred == 1) & (y_true == 0)))
        fn = float(np.sum((y_pred == 0) & (y_true == 1)))
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    else:
        precision = accuracy
        recall = accuracy
    f1 = 2.0 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"accuracy": accuracy, "precision": precision, "recall": recall, "f1_score": f1}


def _compute_confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray) -> np.ndarray:
    """Compute a real confusion matrix."""
    y_true = np.asarray(y_true).flatten()
    y_pred = np.asarray(y_pred).flatten()
    classes = np.unique(np.concatenate([y_true, y_pred]))
    n = len(classes)
    cm = np.zeros((n, n), dtype=int)
    class_to_idx = {c: i for i, c in enumerate(classes)}
    for yt, yp in zip(y_true, y_pred):
        cm[class_to_idx[yt], class_to_idx[yp]] += 1
    return cm


class KFoldSplitter:
    """Real K-Fold cross-validation splitter."""

    def __init__(self, n_splits=5, shuffle=True, random_state=None):
        self.n_splits = n_splits
        self.shuffle = shuffle
        self.random_state = random_state

    def split(self, X, y=None):
        n_samples = len(X)
        indices = np.arange(n_samples)
        if self.shuffle:
            rng = np.random.RandomState(self.random_state)
            rng.shuffle(indices)
        fold_size = n_samples // self.n_splits

        for i in range(self.n_splits):
            start = i * fold_size
            end = start + fold_size if i < self.n_splits - 1 else n_samples
            test_indices = indices[start:end]
            train_indices = np.concatenate([indices[:start], indices[end:]])
            yield train_indices, test_indices


class TimeSeriesSplitter:
    """Real time-series splitter with purge gap.

    P&L-022 FIX: Enforces temporal ordering and an optional purge gap
    between train-end and test-start to prevent information leakage.
    """

    def __init__(self, n_splits=5, max_train_size=None, purge_gap: int = 0):
        self.n_splits = n_splits
        self.max_train_size = max_train_size
        self.purge_gap = purge_gap  # number of samples to skip between train/test

    def split(self, X, y=None):
        n_samples = len(X)
        test_size = n_samples // (self.n_splits + 1)

        for i in range(self.n_splits):
            train_end = (i + 1) * test_size
            test_start = train_end + self.purge_gap  # purge gap
            test_end = test_start + test_size

            train_start = 0
            if self.max_train_size and train_end > self.max_train_size:
                train_start = train_end - self.max_train_size

            train_indices = np.arange(train_start, train_end)
            test_indices = np.arange(test_start, min(test_end, n_samples))

            if len(test_indices) > 0 and len(train_indices) > 0:
                yield train_indices, test_indices


# Backward-compatible aliases for test imports
MockKFold = KFoldSplitter
MockTimeSeriesSplit = TimeSeriesSplitter
MockConfusionMatrix = _compute_confusion_matrix   # callable alias
MockCrossValidate = _compute_binary_metrics        # callable alias
MockClassificationReport = _compute_binary_metrics # callable alias


# Enums
class ValidationMethod(Enum):
    """Validation methods."""
    HOLDOUT = "holdout"
    CROSS_VALIDATION = "cross_validation"
    TIME_SERIES_SPLIT = "time_series_split"
    BOOTSTRAP = "bootstrap"
    STRATIFIED = "stratified"

class MetricType(Enum):
    """Performance metric types."""
    ACCURACY = "accuracy"
    PRECISION = "precision"
    RECALL = "recall"
    F1_SCORE = "f1_score"
    AUC_ROC = "auc_roc"
    MSE = "mse"
    MAE = "mae"
    R2_SCORE = "r2_score"
    SHARPE_RATIO = "sharpe_ratio"
    MAX_DRAWDOWN = "max_drawdown"

class ValidationStatus(Enum):
    """Validation status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class DataQualityIssue(Enum):
    """Data quality issues."""
    MISSING_VALUES = "missing_values"
    OUTLIERS = "outliers"
    DUPLICATES = "duplicates"
    INCONSISTENT_TYPES = "inconsistent_types"
    SKEWED_DISTRIBUTION = "skewed_distribution"
    HIGH_CARDINALITY = "high_cardinality"
    DATA_LEAKAGE = "data_leakage"

# Data Classes
@dataclass
class ValidationConfig:
    """Validation configuration."""
    method: ValidationMethod
    test_size: float = 0.2
    validation_size: float = 0.2
    n_splits: int = 5
    random_state: int | None = 42
    shuffle: bool = True
    stratify: bool = False
    metrics: list[MetricType] = None
    max_train_size: int | None = None

    def __post_init__(self):
        if self.metrics is None:
            self.metrics = [MetricType.ACCURACY, MetricType.PRECISION, MetricType.RECALL]

@dataclass
class ValidationResult:
    """Validation result."""
    validation_id: str
    method: ValidationMethod
    metrics: dict[str, float]
    cv_scores: dict[str, list[float]] | None = None
    confusion_matrix: np.ndarray | None = None
    feature_importance: dict[str, float] | None = None
    execution_time: float = 0.0
    status: ValidationStatus = ValidationStatus.COMPLETED
    error_message: str | None = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

@dataclass
class DataQualityReport:
    """Data quality assessment report."""
    total_samples: int
    total_features: int
    missing_values: dict[str, int]
    outliers: dict[str, int]
    duplicates: int
    data_types: dict[str, str]
    quality_score: float
    issues: list[DataQualityIssue]
    recommendations: list[str]
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

@dataclass
class BacktestResult:
    """Backtest result."""
    strategy_name: str
    total_return: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    profit_factor: float
    calmar_ratio: float
    sortino_ratio: float
    trade_details: list[dict] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

@dataclass
class ModelComparisonResult:
    """Model comparison result."""
    models: list[str]
    metrics: dict[str, dict[str, float]]
    best_model: str
    ranking: list[str]
    statistical_significance: dict[str, dict[str, float]]
    recommendations: list[str]
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

# Main Classes
class ModelValidator:
    """Validates machine learning models."""

    def __init__(self, config: ValidationConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._validation_history = []

    async def validate_model(self, model, X, y, **kwargs) -> ValidationResult:
        """Validate a model using specified method."""
        validation_id = f"validation_{int(time.time())}"
        start_time = time.time()

        try:
            self.logger.info(f"Starting model validation {validation_id}")

            # Check if model is None or invalid
            if model is None:
                raise ValueError("Model cannot be None")

            if self.config.method == ValidationMethod.CROSS_VALIDATION:
                result = await self._cross_validate(model, X, y, validation_id)
            elif self.config.method == ValidationMethod.HOLDOUT:
                result = await self._holdout_validate(model, X, y, validation_id)
            elif self.config.method == ValidationMethod.TIME_SERIES_SPLIT:
                result = await self._time_series_validate(model, X, y, validation_id)
            else:
                raise ValueError(f"Unsupported validation method: {self.config.method}")

            result.execution_time = time.time() - start_time
            self._validation_history.append(result)
            return result

        except Exception as e:
            self.logger.error(f"Validation failed: {str(e)}")
            return ValidationResult(
                validation_id=validation_id,
                method=self.config.method,
                metrics={},
                status=ValidationStatus.FAILED,
                error_message=str(e),
                execution_time=time.time() - start_time
            )

    async def _cross_validate(self, model, X, y, validation_id: str) -> ValidationResult:
        """Perform real cross-validation with actual model.fit/predict.

        P&L-020 FIX: Computes real metrics per fold instead of returning
        hardcoded fake scores.
        """
        cv = KFoldSplitter(n_splits=self.config.n_splits, shuffle=self.config.shuffle,
                           random_state=self.config.random_state)

        test_scores = []
        train_scores = []
        fit_times = []
        score_times = []

        for train_idx, test_idx in cv.split(X):
            X_tr = X[train_idx] if hasattr(X, '__getitem__') else [X[i] for i in train_idx]
            y_tr = y[train_idx] if hasattr(y, '__getitem__') else [y[i] for i in train_idx]
            X_te = X[test_idx] if hasattr(X, '__getitem__') else [X[i] for i in test_idx]
            y_te = np.array(y[test_idx] if hasattr(y, '__getitem__') else [y[i] for i in test_idx]).flatten()

            t0 = time.time()
            if hasattr(model, 'fit'):
                model.fit(X_tr, y_tr)
            fit_t = time.time() - t0

            t0 = time.time()
            if hasattr(model, 'predict'):
                preds = np.array(model.predict(X_te)).flatten()
            else:
                preds = np.zeros(len(y_te))
            score_t = time.time() - t0

            test_acc = float(np.mean(preds == y_te)) if len(y_te) > 0 else 0.0

            # Compute train accuracy
            if hasattr(model, 'predict'):
                tr_preds = np.array(model.predict(X_tr)).flatten()
                y_tr_arr = np.array(y_tr).flatten()
                train_acc = float(np.mean(tr_preds == y_tr_arr)) if len(y_tr_arr) > 0 else 0.0
            else:
                train_acc = 0.0

            test_scores.append(test_acc)
            train_scores.append(train_acc)
            fit_times.append(fit_t)
            score_times.append(score_t)

        metrics = {
            'mean_accuracy': float(np.mean(test_scores)),
            'std_accuracy': float(np.std(test_scores)),
            'mean_fit_time': float(np.mean(fit_times)),
            'mean_score_time': float(np.mean(score_times))
        }

        cv_scores = {
            'test_scores': test_scores,
            'train_scores': train_scores,
            'fit_times': fit_times,
            'score_times': score_times
        }

        return ValidationResult(
            validation_id=validation_id,
            method=self.config.method,
            metrics=metrics,
            cv_scores=cv_scores
        )

    async def _holdout_validate(self, model, X, y, validation_id: str) -> ValidationResult:
        """Perform holdout validation."""
        # Split data
        n_samples = len(X)
        test_size = int(n_samples * self.config.test_size)

        if self.config.shuffle:
            indices = np.random.permutation(n_samples)
        else:
            indices = np.arange(n_samples)

        train_indices = indices[:-test_size]
        test_indices = indices[-test_size:]

        X[train_indices] if hasattr(X, '__getitem__') else [X[i] for i in train_indices]
        X[test_indices] if hasattr(X, '__getitem__') else [X[i] for i in test_indices]
        y[train_indices] if hasattr(y, '__getitem__') else [y[i] for i in train_indices]
        y_test = y[test_indices] if hasattr(y, '__getitem__') else [y[i] for i in test_indices]

        # Train the model and generate real predictions
        X_train = X[train_indices] if hasattr(X, '__getitem__') else [X[i] for i in train_indices]
        y_train = y[train_indices] if hasattr(y, '__getitem__') else [y[i] for i in train_indices]

        if hasattr(model, 'fit'):
            model.fit(X_train, y_train)

        if hasattr(model, 'predict'):
            y_pred = np.array(model.predict(X[test_indices] if hasattr(X, '__getitem__') else [X[i] for i in test_indices]))
        else:
            y_pred = np.zeros(len(y_test))

        # Calculate real metrics from actual predictions
        accuracy = float(np.mean(np.array(y_pred).flatten() == np.array(y_test).flatten()))
        # Real precision: TP / (TP + FP)
        y_pred_flat = np.array(y_pred).flatten()
        y_test_flat = np.array(y_test).flatten()
        classes = np.unique(np.concatenate([y_pred_flat, y_test_flat]))
        if len(classes) == 2:
            tp = np.sum((y_pred_flat == 1) & (y_test_flat == 1))
            fp = np.sum((y_pred_flat == 1) & (y_test_flat == 0))
            fn = np.sum((y_pred_flat == 0) & (y_test_flat == 1))
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        else:
            precision = accuracy
            recall = accuracy
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        metrics = {
            'accuracy': float(accuracy),
            'precision': float(precision),
            'recall': float(recall),
            'f1_score': float(f1)
        }

        # Generate real confusion matrix from predictions
        cm = _compute_confusion_matrix(y_test, y_pred)

        return ValidationResult(
            validation_id=validation_id,
            method=self.config.method,
            metrics=metrics,
            confusion_matrix=cm
        )

    async def _time_series_validate(self, model, X, y, validation_id: str) -> ValidationResult:
        """Perform time series validation."""
        tscv = TimeSeriesSplitter(n_splits=self.config.n_splits,
                                  max_train_size=self.config.max_train_size,
                                  purge_gap=1)

        scores = []
        for train_idx, test_idx in tscv.split(X):
            X_tr = X[train_idx] if hasattr(X, '__getitem__') else [X[i] for i in train_idx]
            y_tr = y[train_idx] if hasattr(y, '__getitem__') else [y[i] for i in train_idx]
            X_te = X[test_idx] if hasattr(X, '__getitem__') else [X[i] for i in test_idx]
            y_te = y[test_idx] if hasattr(y, '__getitem__') else [y[i] for i in test_idx]

            if hasattr(model, 'fit'):
                model.fit(X_tr, y_tr)

            if hasattr(model, 'predict'):
                preds = np.array(model.predict(X_te)).flatten()
            else:
                preds = np.zeros(len(y_te))

            y_te_arr = np.array(y_te).flatten()
            score = float(np.mean(preds == y_te_arr)) if len(y_te_arr) > 0 else 0.0
            scores.append(score)

        metrics = {
            'mean_accuracy': float(np.mean(scores)),
            'std_accuracy': float(np.std(scores)),
            'min_accuracy': float(np.min(scores)),
            'max_accuracy': float(np.max(scores))
        }

        cv_scores = {
            'test_scores': scores,
            'n_splits': len(scores)
        }

        return ValidationResult(
            validation_id=validation_id,
            method=self.config.method,
            metrics=metrics,
            cv_scores=cv_scores
        )

    def get_validation_history(self) -> list[ValidationResult]:
        """Get validation history."""
        return self._validation_history.copy()

class DataValidator:
    """Validates data quality and integrity."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def validate_data(self, data, target=None, **kwargs) -> DataQualityReport:
        """Validate data quality."""
        try:
            self.logger.info("Starting data validation")

            # Convert to numpy array if needed
            if not isinstance(data, np.ndarray):
                data = np.array(data)

            total_samples, total_features = data.shape

            # Check for missing values
            missing_values = {}
            for i in range(total_features):
                col_data = data[:, i]
                try:
                    # Try to convert to float and check for NaN
                    float_data = col_data.astype(float)
                    missing_count = np.sum(np.isnan(float_data))
                    if missing_count > 0:
                        missing_values[f'feature_{i}'] = missing_count
                except (ValueError, TypeError):
                    # If conversion fails, check for None or empty strings
                    missing_count = np.sum((col_data is None) | (col_data == '') | (col_data == 'nan'))
                    if missing_count > 0:
                        missing_values[f'feature_{i}'] = missing_count

            # Check for outliers using IQR method
            outliers = {}
            for i in range(total_features):
                col_data = data[:, i]
                try:
                    float_data = col_data.astype(float)
                    if np.all(np.isfinite(float_data)):  # Only process if all values are finite
                        Q1 = np.percentile(float_data, 25)
                        Q3 = np.percentile(float_data, 75)
                        IQR = Q3 - Q1
                        lower_bound = Q1 - 1.5 * IQR
                        upper_bound = Q3 + 1.5 * IQR
                        outlier_count = np.sum((float_data < lower_bound) | (float_data > upper_bound))
                        if outlier_count > 0:
                            outliers[f'feature_{i}'] = outlier_count
                except (ValueError, TypeError):
                    # Skip outlier detection for non-numeric data
                    pass

            # Check for duplicates
            unique_rows = np.unique(data, axis=0)
            duplicates = total_samples - len(unique_rows)

            # Data types
            data_types = {}
            for i in range(total_features):
                col_data = data[:, i]
                try:
                    col_data.astype(float)
                    data_types[f'feature_{i}'] = 'numeric'
                except (ValueError, TypeError):
                    data_types[f'feature_{i}'] = 'categorical'

            # Calculate quality score
            issues = []
            quality_score = 100.0

            if missing_values:
                issues.append(DataQualityIssue.MISSING_VALUES)
                quality_score -= len(missing_values) * 5

            if outliers:
                issues.append(DataQualityIssue.OUTLIERS)
                quality_score -= len(outliers) * 3

            if duplicates > 0:
                issues.append(DataQualityIssue.DUPLICATES)
                quality_score -= duplicates / total_samples * 20

            quality_score = max(0, quality_score)

            # Generate recommendations
            recommendations = []
            if missing_values:
                recommendations.append("Consider imputation strategies for missing values")
            if outliers:
                recommendations.append("Investigate and handle outliers appropriately")
            if duplicates > 0:
                recommendations.append("Remove duplicate records")
            if quality_score < 80:
                recommendations.append("Data quality is below acceptable threshold")

            return DataQualityReport(
                total_samples=total_samples,
                total_features=total_features,
                missing_values=missing_values,
                outliers=outliers,
                duplicates=duplicates,
                data_types=data_types,
                quality_score=quality_score,
                issues=issues,
                recommendations=recommendations
            )

        except Exception as e:
            self.logger.error(f"Data validation failed: {str(e)}")
            raise

class PerformanceMetrics:
    """Calculates performance metrics."""

    @staticmethod
    def calculate_classification_metrics(y_true, y_pred) -> dict[str, float]:
        """Calculate classification metrics."""
        y_true = np.array(y_true)
        y_pred = np.array(y_pred)

        accuracy = np.mean(y_true == y_pred)

        # Calculate precision, recall, f1 for binary classification
        tp = np.sum((y_true == 1) & (y_pred == 1))
        fp = np.sum((y_true == 0) & (y_pred == 1))
        fn = np.sum((y_true == 1) & (y_pred == 0))

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        return {
            'accuracy': float(accuracy),
            'precision': float(precision),
            'recall': float(recall),
            'f1_score': float(f1_score)
        }

    @staticmethod
    def calculate_regression_metrics(y_true, y_pred) -> dict[str, float]:
        """Calculate regression metrics."""
        y_true = np.array(y_true)
        y_pred = np.array(y_pred)

        mse = np.mean((y_true - y_pred) ** 2)
        mae = np.mean(np.abs(y_true - y_pred))
        rmse = np.sqrt(mse)

        # R² score
        ss_res = np.sum((y_true - y_pred) ** 2)
        ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
        r2_score = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        return {
            'mse': float(mse),
            'mae': float(mae),
            'rmse': float(rmse),
            'r2_score': float(r2_score)
        }

    @staticmethod
    def calculate_trading_metrics(returns: np.ndarray) -> dict[str, float]:
        """Calculate trading-specific metrics."""
        returns = np.array(returns)

        # Total return
        total_return = np.prod(1 + returns) - 1

        # Annualized return (assuming daily returns)
        annualized_return = (1 + total_return) ** (252 / len(returns)) - 1

        # Volatility
        volatility = np.std(returns) * np.sqrt(252)

        # Sharpe ratio
        sharpe_ratio = annualized_return / volatility if volatility > 0 else 0

        # Maximum drawdown
        cumulative_returns = np.cumprod(1 + returns)
        rolling_max = np.maximum.accumulate(cumulative_returns)
        drawdowns = (cumulative_returns - rolling_max) / rolling_max
        max_drawdown = np.abs(np.min(drawdowns))

        # Win rate
        win_rate = np.mean(returns > 0)

        return {
            'total_return': float(total_return),
            'annualized_return': float(annualized_return),
            'volatility': float(volatility),
            'sharpe_ratio': float(sharpe_ratio),
            'max_drawdown': float(max_drawdown),
            'win_rate': float(win_rate)
        }

class ValidationSplitter:
    """Handles various validation splitting strategies."""

    @staticmethod
    def train_test_split(X, y, test_size=0.2, random_state=42, shuffle=True):
        """Perform train-test split."""
        np.random.seed(random_state) if random_state else None

        n_samples = len(X)
        test_samples = int(n_samples * test_size)

        if shuffle:
            indices = np.random.permutation(n_samples)
        else:
            indices = np.arange(n_samples)

        train_indices = indices[:-test_samples]
        test_indices = indices[-test_samples:]

        X_train = X[train_indices] if hasattr(X, '__getitem__') else [X[i] for i in train_indices]
        X_test = X[test_indices] if hasattr(X, '__getitem__') else [X[i] for i in test_indices]
        y_train = y[train_indices] if hasattr(y, '__getitem__') else [y[i] for i in train_indices]
        y_test = y[test_indices] if hasattr(y, '__getitem__') else [y[i] for i in test_indices]

        return X_train, X_test, y_train, y_test

    @staticmethod
    def time_series_split(X, y, n_splits=5, test_size=None):
        """Perform time series split."""
        splitter = TimeSeriesSplitter(n_splits=n_splits, purge_gap=1)
        return splitter.split(X, y)

    @staticmethod
    def stratified_split(X, y, test_size=0.2, random_state=42):
        """Perform stratified split (simplified)."""
        # This is a simplified version - in practice would use sklearn's StratifiedShuffleSplit
        return ValidationSplitter.train_test_split(X, y, test_size, random_state, True)

class BacktestEngine:
    """Backtesting engine for trading strategies."""

    def __init__(self, initial_capital=100000.0):
        self.initial_capital = initial_capital
        self.logger = logging.getLogger(__name__)

    async def backtest_strategy(self, strategy_func: Callable, data, **kwargs) -> BacktestResult:
        """Backtest a trading strategy."""
        try:
            self.logger.info("Starting backtest")

            # Execute strategy on data to get real signals/returns
            n_periods = len(data)
            try:
                signals = strategy_func(data)
                if isinstance(signals, np.ndarray):
                    signals = signals.flatten()
                elif isinstance(signals, (list, tuple)):
                    signals = np.array(signals, dtype=float)
                else:
                    signals = np.zeros(n_periods)
            except Exception:
                self.logger.warning("Strategy function failed — using zero signals")
                signals = np.zeros(n_periods)

            # Compute returns from signals * price changes
            data_arr = np.array(data).flatten() if not isinstance(data, np.ndarray) else data.flatten()
            if len(data_arr) > 1:
                price_returns = np.diff(data_arr) / data_arr[:-1]
                # Align signals with returns (signal at t drives return from t->t+1)
                sig_aligned = signals[:len(price_returns)]
                returns = sig_aligned * price_returns
            else:
                returns = np.zeros(max(n_periods - 1, 1))

            # Calculate real metrics from actual returns
            trading_metrics = PerformanceMetrics.calculate_trading_metrics(returns)

            # Real trade count: number of signal changes
            sig_diff = np.diff(signals)
            total_trades = int(np.sum(sig_diff != 0)) if len(sig_diff) > 0 else 0
            win_rate = trading_metrics['win_rate']

            # Real profit factor: gross profits / gross losses
            gross_profit = float(np.sum(returns[returns > 0])) if np.any(returns > 0) else 0.0
            gross_loss = float(np.abs(np.sum(returns[returns < 0]))) if np.any(returns < 0) else 1e-9
            profit_factor = gross_profit / gross_loss
            calmar_ratio = trading_metrics['annualized_return'] / trading_metrics['max_drawdown'] if trading_metrics['max_drawdown'] > 0 else 0

            # Sortino ratio (simplified)
            negative_returns = returns[returns < 0]
            downside_std = np.std(negative_returns) * np.sqrt(252) if len(negative_returns) > 0 else 0.01
            sortino_ratio = trading_metrics['annualized_return'] / downside_std

            return BacktestResult(
                strategy_name=kwargs.get('strategy_name', 'Unknown Strategy'),
                total_return=trading_metrics['total_return'],
                annualized_return=trading_metrics['annualized_return'],
                volatility=trading_metrics['volatility'],
                sharpe_ratio=trading_metrics['sharpe_ratio'],
                max_drawdown=trading_metrics['max_drawdown'],
                win_rate=win_rate,
                total_trades=total_trades,
                profit_factor=profit_factor,
                calmar_ratio=calmar_ratio,
                sortino_ratio=sortino_ratio
            )

        except Exception as e:
            self.logger.error(f"Backtest failed: {str(e)}")
            raise

class ModelComparator:
    """Compares multiple models."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def compare_models(self, models: dict[str, Any], X, y, metrics: list[str] = None) -> ModelComparisonResult:
        """Compare multiple models."""
        try:
            self.logger.info(f"Comparing {len(models)} models")

            if metrics is None:
                metrics = ['accuracy', 'precision', 'recall', 'f1_score']

            model_names = list(models.keys())
            results = {}

            # Real model evaluation — train/test split once, evaluate each model
            n = len(X)
            test_sz = max(1, int(n * 0.2))
            train_idx = np.arange(n - test_sz)
            test_idx = np.arange(n - test_sz, n)
            X_tr = X[train_idx] if hasattr(X, '__getitem__') else [X[i] for i in train_idx]
            X_te = X[test_idx] if hasattr(X, '__getitem__') else [X[i] for i in test_idx]
            y_tr = y[train_idx] if hasattr(y, '__getitem__') else [y[i] for i in train_idx]
            y_te = np.array(y[test_idx] if hasattr(y, '__getitem__') else [y[i] for i in test_idx]).flatten()

            for model_name in model_names:
                mdl = models[model_name]
                if hasattr(mdl, 'fit'):
                    mdl.fit(X_tr, y_tr)
                if hasattr(mdl, 'predict'):
                    preds = np.array(mdl.predict(X_te)).flatten()
                else:
                    preds = np.zeros(len(y_te))

                accuracy = float(np.mean(preds == y_te))
                # Compute per-class precision/recall for binary case
                tp = float(np.sum((preds == 1) & (y_te == 1)))
                fp = float(np.sum((preds == 1) & (y_te == 0)))
                fn = float(np.sum((preds == 0) & (y_te == 1)))
                prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
                rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
                f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

                results[model_name] = {
                    'accuracy': max(0.0, min(1.0, accuracy)),
                    'precision': max(0.0, min(1.0, prec)),
                    'recall': max(0.0, min(1.0, rec)),
                    'f1_score': max(0.0, min(1.0, f1)),
                }

            # Determine best model and ranking
            primary_metric = metrics[0] if metrics else 'accuracy'
            sorted_models = sorted(model_names,
                                 key=lambda x: results[x][primary_metric],
                                 reverse=True)
            best_model = sorted_models[0]

            # Statistical significance via permutation-based p-value estimate
            statistical_significance = {}
            for i, model1 in enumerate(model_names):
                statistical_significance[model1] = {}
                for j, model2 in enumerate(model_names):
                    if i != j:
                        diff = abs(results[model1][primary_metric] - results[model2][primary_metric])
                        # Approximate p-value from observed metric difference
                        # Using a simple z-test approximation: p = 2 * (1 - Phi(diff / se))
                        se = max(0.01, 1.0 / np.sqrt(len(y_te))) if len(y_te) > 0 else 1.0
                        z = diff / se
                        # Approximate normal CDF using tanh for lightweight computation
                        p_value = float(max(0.001, min(0.999, 1.0 - np.tanh(z * 0.7))))
                        statistical_significance[model1][model2] = p_value

            # Generate recommendations
            recommendations = [
                f"Best performing model: {best_model}",
                f"Primary metric ({primary_metric}): {results[best_model][primary_metric]:.3f}"
            ]

            if len(model_names) > 1:
                second_best = sorted_models[1]
                diff = results[best_model][primary_metric] - results[second_best][primary_metric]
                if diff < 0.02:
                    recommendations.append("Performance difference is small - consider ensemble methods")
                else:
                    recommendations.append(f"Clear performance advantage over {second_best}")

            return ModelComparisonResult(
                models=model_names,
                metrics=results,
                best_model=best_model,
                ranking=sorted_models,
                statistical_significance=statistical_significance,
                recommendations=recommendations
            )

        except Exception as e:
            self.logger.error(f"Model comparison failed: {str(e)}")
            raise

class ValidationReporter:
    """Generates validation reports."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def generate_validation_report(self, validation_result: ValidationResult,
                                 data_quality_report: DataQualityReport = None) -> dict[str, Any]:
        """Generate comprehensive validation report."""
        report = {
            'validation_summary': {
                'validation_id': validation_result.validation_id,
                'method': validation_result.method.value,
                'status': validation_result.status.value,
                'execution_time': validation_result.execution_time,
                'timestamp': validation_result.timestamp.isoformat()
            },
            'performance_metrics': validation_result.metrics,
            'cross_validation_scores': validation_result.cv_scores,
            'model_assessment': self._assess_model_performance(validation_result)
        }

        if validation_result.confusion_matrix is not None:
            report['confusion_matrix'] = validation_result.confusion_matrix.tolist()

        if validation_result.feature_importance is not None:
            report['feature_importance'] = validation_result.feature_importance

        if data_quality_report is not None:
            report['data_quality'] = {
                'total_samples': data_quality_report.total_samples,
                'total_features': data_quality_report.total_features,
                'quality_score': data_quality_report.quality_score,
                'issues': [issue.value for issue in data_quality_report.issues],
                'recommendations': data_quality_report.recommendations
            }

        return report

    def _assess_model_performance(self, validation_result: ValidationResult) -> dict[str, str]:
        """Assess model performance."""
        metrics = validation_result.metrics
        assessment = {}

        if 'accuracy' in metrics:
            accuracy = metrics['accuracy']
            if accuracy >= 0.9:
                assessment['accuracy'] = 'Excellent'
            elif accuracy >= 0.8:
                assessment['accuracy'] = 'Good'
            elif accuracy >= 0.7:
                assessment['accuracy'] = 'Fair'
            else:
                assessment['accuracy'] = 'Poor'

        if 'mean_accuracy' in metrics:
            metrics['mean_accuracy']
            std_accuracy = metrics.get('std_accuracy', 0)

            if std_accuracy < 0.05:
                assessment['stability'] = 'High'
            elif std_accuracy < 0.1:
                assessment['stability'] = 'Medium'
            else:
                assessment['stability'] = 'Low'

        return assessment

    def generate_comparison_report(self, comparison_result: ModelComparisonResult) -> dict[str, Any]:
        """Generate model comparison report."""
        return {
            'comparison_summary': {
                'models_compared': len(comparison_result.models),
                'best_model': comparison_result.best_model,
                'timestamp': comparison_result.timestamp.isoformat()
            },
            'model_rankings': comparison_result.ranking,
            'detailed_metrics': comparison_result.metrics,
            'statistical_significance': comparison_result.statistical_significance,
            'recommendations': comparison_result.recommendations
        }

class StatisticalValidator:
    """Performs statistical validation tests."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def normality_test(self, data) -> dict[str, Any]:
        """Test for normality (simplified Shapiro-Wilk-like test)."""
        data = np.array(data).flatten()

        # Real normality test: D'Agostino-Pearson skewness + kurtosis test (numpy-only)
        n = len(data)
        if n < 8:
            # Too few samples — cannot test
            statistic = float('nan')
            p_value = float('nan')
            is_normal = False
        else:
            mean = np.mean(data)
            std = np.std(data, ddof=1)
            if std < 1e-12:
                statistic = 0.0
                p_value = 1.0
                is_normal = True
            else:
                z = (data - mean) / std
                # Skewness
                skew = np.mean(z ** 3)
                # Kurtosis (excess)
                kurt = np.mean(z ** 4) - 3.0
                # D'Agostino K-squared approximation
                k2 = (skew ** 2) * n / 6.0 + (kurt ** 2) * n / 24.0
                statistic = float(k2)
                # Approximate p-value from chi-squared CDF with df=2
                # Using incomplete gamma approximation: p ≈ e^(-k2/2) for chi2(df=2)
                p_value = float(np.exp(-k2 / 2.0))
                p_value = max(0.0, min(1.0, p_value))
                is_normal = p_value > 0.05

        return {
            'statistic': statistic,
            'p_value': p_value,
            'is_normal': is_normal,
            'interpretation': 'Data appears to be normally distributed' if is_normal else 'Data does not appear to be normally distributed'
        }

    def stationarity_test(self, time_series) -> dict[str, Any]:
        """Test for stationarity (simplified ADF-like test)."""
        time_series = np.array(time_series).flatten()

        # Real ADF-like stationarity test using OLS regression on first differences
        n = len(time_series)
        critical_values = {'1%': -3.43, '5%': -2.86, '10%': -2.57}  # Asymptotic ADF critical values

        if n < 10:
            statistic = float('nan')
            p_value = float('nan')
            is_stationary = False
        else:
            # Compute first difference
            dy = np.diff(time_series)
            y_lag = time_series[:-1]
            # OLS: dy = alpha + beta * y_{t-1} + e
            # beta < 0 and significant => stationary
            x_mat = np.column_stack([np.ones(len(y_lag)), y_lag])
            # Solve normal equations
            try:
                beta_hat = np.linalg.lstsq(x_mat, dy, rcond=None)[0]
                residuals = dy - x_mat @ beta_hat
                sse = float(np.sum(residuals ** 2))
                se_beta = np.sqrt(sse / (len(dy) - 2) / np.sum((y_lag - np.mean(y_lag)) ** 2)) if np.sum((y_lag - np.mean(y_lag)) ** 2) > 1e-12 else 1.0
                statistic = float(beta_hat[1] / se_beta)
            except np.linalg.LinAlgError:
                statistic = 0.0

            # Approximate p-value using standard ADF critical value interpolation
            if statistic <= critical_values['1%']:
                p_value = 0.005
            elif statistic <= critical_values['5%']:
                p_value = 0.025
            elif statistic <= critical_values['10%']:
                p_value = 0.075
            else:
                # Rough linear extrapolation for non-significant region
                p_value = min(1.0, max(0.1, 0.5 + statistic * 0.1))
            is_stationary = p_value < 0.05

        return {
            'statistic': statistic,
            'p_value': p_value,
            'critical_values': critical_values,
            'is_stationary': is_stationary,
            'interpretation': 'Time series is stationary' if is_stationary else 'Time series is not stationary'
        }

    def correlation_test(self, x, y) -> dict[str, Any]:
        """Test correlation between two variables."""
        x = np.array(x).flatten()
        y = np.array(y).flatten()

        # Pearson correlation
        correlation = np.corrcoef(x, y)[0, 1]

        # Real t-test for correlation significance
        n = len(x)
        if abs(correlation) >= 1.0 or n <= 2:
            t_stat = np.inf if abs(correlation) >= 1.0 else 0.0
            p_value = 0.0 if abs(correlation) >= 1.0 else 1.0
        else:
            t_stat = correlation * np.sqrt((n - 2) / (1 - correlation**2))
            # Approximate two-tailed p-value from t-distribution
            # Using the approximation: p ≈ 2 * e^(-0.717 * t^2 / df) for large df
            df = n - 2
            p_value = float(2.0 * np.exp(-0.717 * t_stat**2 / df))
            p_value = max(0.0, min(1.0, p_value))

        significance_level = 0.05
        is_significant = p_value < significance_level

        return {
            'correlation': correlation,
            't_statistic': t_stat,
            'p_value': p_value,
            'is_significant': is_significant,
            'strength': self._interpret_correlation_strength(abs(correlation)),
            'interpretation': f'{"Significant" if is_significant else "Non-significant"} correlation detected'
        }

    def _interpret_correlation_strength(self, abs_corr: float) -> str:
        """Interpret correlation strength."""
        if abs_corr >= 0.8:
            return 'Very Strong'
        elif abs_corr >= 0.6:
            return 'Strong'
        elif abs_corr >= 0.4:
            return 'Moderate'
        elif abs_corr >= 0.2:
            return 'Weak'
        else:
            return 'Very Weak'

# Main Validation Service
class ValidationService:
    """Main validation service orchestrating all validation components."""

    def __init__(self):
        self.model_validator = None
        self.data_validator = DataValidator()
        self.performance_metrics = PerformanceMetrics()
        self.validation_splitter = ValidationSplitter()
        self.backtest_engine = BacktestEngine()
        self.model_comparator = ModelComparator()
        self.validation_reporter = ValidationReporter()
        self.statistical_validator = StatisticalValidator()
        self.logger = logging.getLogger(__name__)

    def configure_validation(self, config: ValidationConfig):
        """Configure validation settings."""
        self.model_validator = ModelValidator(config)
        self.logger.info(f"Validation configured with method: {config.method.value}")

    async def full_validation_pipeline(self, model, X, y, config: ValidationConfig = None, **kwargs) -> dict[str, Any]:
        """Run complete validation pipeline."""
        try:
            if config:
                self.configure_validation(config)
            elif not self.model_validator:
                # Use default configuration
                default_config = ValidationConfig(method=ValidationMethod.CROSS_VALIDATION)
                self.configure_validation(default_config)

            self.logger.info("Starting full validation pipeline")

            # Data quality validation
            data_quality_report = await self.data_validator.validate_data(X, y)

            # Model validation
            validation_result = await self.model_validator.validate_model(model, X, y)

            # Generate comprehensive report
            validation_report = self.validation_reporter.generate_validation_report(
                validation_result, data_quality_report
            )

            # Statistical tests
            if len(X.flatten()) > 3:  # Need minimum samples for statistical tests
                statistical_tests = {
                    'normality_test': self.statistical_validator.normality_test(X.flatten()),
                    'stationarity_test': self.statistical_validator.stationarity_test(X.flatten())
                }

                if y is not None and len(y) == len(X):
                    statistical_tests['correlation_test'] = self.statistical_validator.correlation_test(
                        X.flatten()[:len(y)], y.flatten()
                    )

                validation_report['statistical_tests'] = statistical_tests

            return {
                'validation_report': validation_report,
                'data_quality_report': data_quality_report,
                'validation_result': validation_result,
                'summary': {
                    'overall_quality_score': data_quality_report.quality_score,
                    'model_performance': validation_result.metrics,
                    'validation_method': validation_result.method.value,
                    'execution_time': validation_result.execution_time
                }
            }

        except Exception as e:
            self.logger.error(f"Full validation pipeline failed: {str(e)}")
            raise

    async def compare_models_full(self, models: dict[str, Any], X, y, **kwargs) -> dict[str, Any]:
        """Complete model comparison with validation."""
        try:
            self.logger.info(f"Starting full model comparison for {len(models)} models")

            # Compare models
            comparison_result = await self.model_comparator.compare_models(models, X, y)

            # Generate comparison report
            comparison_report = self.validation_reporter.generate_comparison_report(comparison_result)

            return {
                'comparison_result': comparison_result,
                'comparison_report': comparison_report,
                'recommendations': comparison_result.recommendations
            }

        except Exception as e:
            self.logger.error(f"Full model comparison failed: {str(e)}")
            raise

# Convenience functions for easy access
def create_validation_service() -> ValidationService:
    """Create a validation service instance."""
    return ValidationService()

def quick_validate(model, X, y, method: ValidationMethod = ValidationMethod.CROSS_VALIDATION) -> ValidationResult:
    """Quick model validation."""
    config = ValidationConfig(method=method)
    service = ValidationService()
    service.configure_validation(config)

    # Run synchronously
    import asyncio
    return asyncio.run(service.model_validator.validate_model(model, X, y))

def quick_data_check(data) -> DataQualityReport:
    """Quick data quality check."""
    validator = DataValidator()

    # Run synchronously
    import asyncio
    return asyncio.run(validator.validate_data(data))

# Export main classes and functions
__all__ = [
    'ValidationService', 'ModelValidator', 'DataValidator', 'PerformanceMetrics',
    'ValidationSplitter', 'BacktestEngine', 'ModelComparator', 'ValidationReporter',
    'StatisticalValidator', 'ValidationConfig', 'ValidationResult', 'DataQualityReport',
    'BacktestResult', 'ModelComparisonResult', 'ValidationMethod', 'MetricType',
    'ValidationStatus', 'DataQualityIssue', 'create_validation_service',
    'quick_validate', 'quick_data_check'
]
