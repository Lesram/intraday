"""
Module 59: ML Training Service
Comprehensive ML training functionality with hyperparameter tuning, cross-validation, and monitoring.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import logging
import os
import pickle
import threading
import time
import traceback
from typing import Any

import numpy as np
import pandas as pd

from ..utils.secure_pickle import PickleSecurityError, secure_load

# sklearn is a hard requirement for ML training
try:
    from sklearn.base import BaseEstimator
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.linear_model import LinearRegression, LogisticRegression
    from sklearn.metrics import (
        accuracy_score,
        classification_report,
        confusion_matrix,
        f1_score,
        mean_absolute_error,
        mean_squared_error,
        precision_score,
        r2_score,
        recall_score,
    )
    from sklearn.model_selection import (
        GridSearchCV,
        KFold,
        RandomizedSearchCV,
        StratifiedKFold,
        TimeSeriesSplit,
        cross_val_score,
        train_test_split,
    )
    from sklearn.svm import SVC, SVR
except ImportError as e:
    raise RuntimeError(
        "scikit-learn is required for ML training. "
        "Install it with: pip install scikit-learn"
    ) from e


class TrainingStatus(Enum):
    """Training job status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrainingType(Enum):
    """Training type enumeration."""
    CLASSIFICATION = "classification"
    REGRESSION = "regression"
    CLUSTERING = "clustering"


class ValidationStrategy(Enum):
    """Cross-validation strategy enumeration."""
    K_FOLD = "k_fold"
    STRATIFIED_K_FOLD = "stratified_k_fold"
    TIME_SERIES_SPLIT = "time_series_split"
    HOLDOUT = "holdout"


@dataclass
class TrainingRequest:
    """Training request data structure."""
    model_type: str
    training_data: pd.DataFrame
    target_column: str
    features: list[str] | None = None
    validation_strategy: str = "k_fold"
    test_size: float = 0.2
    # IMPORTANT: for time-series style data, shuffling can leak future information
    # into training and inflate metrics. Default to False for safer results.
    shuffle: bool = False
    random_state: int = 42
    hyperparameters: dict[str, Any] | None = None
    tune_hyperparameters: bool = False
    tuning_params: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class TrainingResult:
    """Training result data structure."""
    job_id: str
    status: str
    model: BaseEstimator | None
    scores: dict[str, float]
    training_time: float
    validation_scores: dict[str, list[float]] | None = None
    best_parameters: dict[str, Any] | None = None
    feature_importance: dict[str, float] | None = None
    model_path: str | None = None
    error_message: str | None = None
    created_at: datetime = None
    completed_at: datetime | None = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class TrainingJob:
    """Training job data structure."""
    job_id: str
    request: TrainingRequest
    status: str = TrainingStatus.PENDING.value
    result: TrainingResult | None = None
    created_at: datetime = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class TrainingMonitor:
    """Training monitoring and logging."""

    def __init__(self):
        self.metrics = {}
        self.start_time = None
        self.logger = logging.getLogger(__name__)

    def start_monitoring(self, job_id: str):
        """Start monitoring a training job."""
        self.start_time = time.time()
        self.metrics[job_id] = {
            'start_time': self.start_time,
            'status': TrainingStatus.RUNNING.value,
            'progress': 0.0
        }
        self.logger.info(f"Started monitoring training job {job_id}")

    def update_progress(self, job_id: str, progress: float):
        """Update training progress."""
        if job_id in self.metrics:
            self.metrics[job_id]['progress'] = progress
            self.logger.debug(f"Training job {job_id} progress: {progress:.2%}")

    def log_training_step(self, job_id: str, step: str, details: dict[str, Any]):
        """Log a training step."""
        self.logger.info(f"Training job {job_id} - {step}: {details}")

    def finish_monitoring(self, job_id: str, status: str):
        """Finish monitoring a training job."""
        if job_id in self.metrics:
            end_time = time.time()
            self.metrics[job_id]['end_time'] = end_time
            self.metrics[job_id]['status'] = status
            self.metrics[job_id]['duration'] = end_time - self.metrics[job_id]['start_time']
            self.logger.info(f"Finished monitoring training job {job_id} with status {status}")

    def get_metrics(self, job_id: str) -> dict[str, Any]:
        """Get training metrics."""
        return self.metrics.get(job_id, {})


class HyperparameterTuner:
    """Hyperparameter tuning functionality."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.default_param_grids = {
            'RandomForestClassifier': {
                'n_estimators': [50, 100, 200],
                'max_depth': [3, 5, 10, None],
                'min_samples_split': [2, 5, 10],
                'min_samples_leaf': [1, 2, 4]
            },
            'RandomForestRegressor': {
                'n_estimators': [50, 100, 200],
                'max_depth': [3, 5, 10, None],
                'min_samples_split': [2, 5, 10],
                'min_samples_leaf': [1, 2, 4]
            },
            'LogisticRegression': {
                'C': [0.1, 1.0, 10.0],
                'penalty': ['l1', 'l2'],
                'solver': ['liblinear', 'lbfgs']
            },
            'SVC': {
                'C': [0.1, 1, 10],
                'kernel': ['linear', 'rbf'],
                'gamma': ['scale', 'auto']
            }
        }

    def tune_hyperparameters(
        self,
        model: BaseEstimator,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        param_grid: dict[str, Any] | None = None,
        cv: int = 5,
        search_type: str = 'grid',
        n_iter: int = 10
    ) -> tuple[BaseEstimator, dict[str, Any]]:
        """Tune hyperparameters using grid search or random search."""

        # Use default param grid if none provided
        if param_grid is None:
            model_name = model.__class__.__name__
            param_grid = self.default_param_grids.get(model_name, {})

        if not param_grid:
            self.logger.warning(f"No parameter grid found for {model.__class__.__name__}")
            return model, {}

        try:
            if search_type == 'grid':
                search = GridSearchCV(
                    model, param_grid, cv=cv, scoring='accuracy',
                    n_jobs=-1, verbose=1
                )
            else:  # random search
                search = RandomizedSearchCV(
                    model, param_grid, cv=cv, scoring='accuracy',
                    n_iter=n_iter, n_jobs=-1, verbose=1, random_state=42
                )

            self.logger.info(f"Starting {search_type} search with {len(param_grid)} parameters")
            search.fit(X_train, y_train)

            self.logger.info(f"Best score: {search.best_score_:.4f}")
            self.logger.info(f"Best parameters: {search.best_params_}")

            return search.best_estimator_, search.best_params_

        except Exception as e:
            self.logger.error(f"Hyperparameter tuning failed: {str(e)}")
            return model, {}


class CrossValidator:
    """Cross-validation functionality."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_cv_strategy(self, strategy: str, n_splits: int = 5, **kwargs):
        """Get cross-validation strategy."""
        if strategy == ValidationStrategy.K_FOLD.value:
            return KFold(n_splits=n_splits, shuffle=True, random_state=42)
        elif strategy == ValidationStrategy.STRATIFIED_K_FOLD.value:
            return StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        elif strategy == ValidationStrategy.TIME_SERIES_SPLIT.value:
            return TimeSeriesSplit(n_splits=n_splits)
        else:
            return KFold(n_splits=n_splits, shuffle=True, random_state=42)

    def perform_cross_validation(
        self,
        model: BaseEstimator,
        X: pd.DataFrame,
        y: pd.Series,
        strategy: str = "k_fold",
        n_splits: int = 5,
        scoring: list[str] | None = None
    ) -> dict[str, list[float]]:
        """Perform cross-validation."""

        cv_strategy = self.get_cv_strategy(strategy, n_splits)

        if scoring is None:
            scoring = ['accuracy'] if hasattr(model, 'predict_proba') else ['r2']

        results = {}

        try:
            for score_name in scoring:
                scores = cross_val_score(model, X, y, cv=cv_strategy, scoring=score_name)
                results[score_name] = scores.tolist()

                self.logger.info(f"{score_name} scores: {scores}")
                self.logger.info(f"Mean {score_name}: {scores.mean():.4f} (+/- {scores.std() * 2:.4f})")

            return results

        except Exception as e:
            self.logger.error(f"Cross-validation failed: {str(e)}")
            return {}


class ModelEvaluator:
    """Model evaluation functionality."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def evaluate_classification_model(
        self,
        model: BaseEstimator,
        X_test: pd.DataFrame,
        y_test: pd.Series
    ) -> dict[str, float]:
        """Evaluate classification model."""
        try:
            y_pred = model.predict(X_test)

            scores = {
                'accuracy': accuracy_score(y_test, y_pred),
                'precision': precision_score(y_test, y_pred, average='weighted', zero_division=0),
                'recall': recall_score(y_test, y_pred, average='weighted', zero_division=0),
                'f1': f1_score(y_test, y_pred, average='weighted', zero_division=0)
            }

            self.logger.info(f"Classification scores: {scores}")
            return scores

        except Exception as e:
            self.logger.error(f"Classification evaluation failed: {str(e)}")
            return {}

    def evaluate_regression_model(
        self,
        model: BaseEstimator,
        X_test: pd.DataFrame,
        y_test: pd.Series
    ) -> dict[str, float]:
        """Evaluate regression model."""
        try:
            y_pred = model.predict(X_test)

            scores = {
                'mse': mean_squared_error(y_test, y_pred),
                'mae': mean_absolute_error(y_test, y_pred),
                'r2': r2_score(y_test, y_pred),
                'rmse': np.sqrt(mean_squared_error(y_test, y_pred))
            }

            self.logger.info(f"Regression scores: {scores}")
            return scores

        except Exception as e:
            self.logger.error(f"Regression evaluation failed: {str(e)}")
            return {}

    def get_feature_importance(self, model: BaseEstimator, feature_names: list[str]) -> dict[str, float]:
        """Get feature importance from model."""
        try:
            if hasattr(model, 'feature_importances_'):
                importance = model.feature_importances_
                return dict(zip(feature_names, importance.tolist(), strict=False))
            elif hasattr(model, 'coef_'):
                importance = np.abs(model.coef_).flatten()
                return dict(zip(feature_names, importance.tolist(), strict=False))
            else:
                return {}
        except Exception as e:
            self.logger.error(f"Feature importance extraction failed: {str(e)}")
            return {}


class TrainingService:
    """Main ML training service."""

    def __init__(self, model_storage_path: str = "models"):
        self.monitor = TrainingMonitor()
        self.tuner = HyperparameterTuner()
        self.cv = CrossValidator()
        self.evaluator = ModelEvaluator()
        self.model_storage_path = model_storage_path
        self.jobs = {}
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()

        # Ensure model storage directory exists
        os.makedirs(model_storage_path, exist_ok=True)

        # Available models
        self.available_models = {
            'RandomForestClassifier': RandomForestClassifier,
            'RandomForestRegressor': RandomForestRegressor,
            'LogisticRegression': LogisticRegression,
            'LinearRegression': LinearRegression,
            'SVC': SVC,
            'SVR': SVR
        }

    def create_model(self, model_type: str, hyperparameters: dict[str, Any] | None = None) -> BaseEstimator:
        """Create a model instance."""
        if model_type not in self.available_models:
            raise ValueError(f"Unsupported model type: {model_type}")

        model_class = self.available_models[model_type]

        if hyperparameters:
            return model_class(**hyperparameters)
        else:
            return model_class(random_state=42)

    def submit_training_job(self, request: TrainingRequest) -> str:
        """Submit a training job."""
        job_id = f"training_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.jobs)}"

        job = TrainingJob(
            job_id=job_id,
            request=request,
            status=TrainingStatus.PENDING.value
        )

        with self._lock:
            self.jobs[job_id] = job

        self.logger.info(f"Created training job {job_id}")
        return job_id

    def train_model(self, job_id: str) -> TrainingResult:
        """Train a model for a specific job."""
        if job_id not in self.jobs:
            raise ValueError(f"Job {job_id} not found")

        job = self.jobs[job_id]
        request = job.request

        try:
            # Start monitoring
            self.monitor.start_monitoring(job_id)
            job.status = TrainingStatus.RUNNING.value
            job.started_at = datetime.now()

            # Prepare data
            self.monitor.log_training_step(job_id, "Data Preparation", {"rows": len(request.training_data)})

            # Convert to numpy arrays to avoid pandas compatibility issues
            if hasattr(request.training_data, 'values'):
                # If it's a DataFrame, extract values and column names
                data_values = request.training_data.values
                column_names = list(request.training_data.columns)

                if request.features:
                    # Get feature indices
                    feature_indices = [column_names.index(col) for col in request.features if col in column_names]
                    X = data_values[:, feature_indices]
                    feature_names = request.features
                else:
                    # Get all columns except target column
                    target_index = column_names.index(request.target_column)
                    feature_indices = [i for i in range(len(column_names)) if i != target_index]
                    X = data_values[:, feature_indices]
                    feature_names = [col for col in column_names if col != request.target_column]

                # Get target values
                target_index = column_names.index(request.target_column)
                y = data_values[:, target_index]

                # Convert back to DataFrame for compatibility
                X = pd.DataFrame(X, columns=feature_names)
                y = pd.Series(y, name=request.target_column)

            else:
                # Handle numpy array input
                if request.features:
                    X = request.training_data[request.features]
                else:
                    all_columns = list(request.training_data.columns)
                    feature_columns = [col for col in all_columns if col != request.target_column]
                    X = request.training_data[feature_columns]

                y = request.training_data[request.target_column]

            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X,
                y,
                test_size=request.test_size,
                random_state=request.random_state,
                shuffle=request.shuffle,
            )

            self.monitor.update_progress(job_id, 0.2)

            # Create model
            model = self.create_model(request.model_type, request.hyperparameters)

            # Hyperparameter tuning
            best_params = {}
            if request.tune_hyperparameters:
                self.monitor.log_training_step(job_id, "Hyperparameter Tuning", {"started": True})
                tuning_params = request.tuning_params or {}
                model, best_params = self.tuner.tune_hyperparameters(
                    model, X_train, y_train, **tuning_params
                )
                self.monitor.update_progress(job_id, 0.5)

            # Train model
            self.monitor.log_training_step(job_id, "Model Training", {"model": request.model_type})
            start_time = time.time()
            model.fit(X_train, y_train)
            training_time = time.time() - start_time

            self.monitor.update_progress(job_id, 0.7)

            # Cross-validation
            cv_scores = self.cv.perform_cross_validation(
                model, X_train, y_train, request.validation_strategy
            )

            self.monitor.update_progress(job_id, 0.8)

            # Evaluation
            is_classification = (hasattr(model, 'predict_proba') or
                               'Classifier' in model.__class__.__name__) and \
                               'Regressor' not in model.__class__.__name__
            if is_classification:
                scores = self.evaluator.evaluate_classification_model(model, X_test, y_test)
            else:
                scores = self.evaluator.evaluate_regression_model(model, X_test, y_test)

            # Feature importance
            feature_importance = self.evaluator.get_feature_importance(model, X.columns.tolist())

            self.monitor.update_progress(job_id, 0.9)

            # Save model
            model_path = os.path.join(self.model_storage_path, f"{job_id}_model.pkl")
            with open(model_path, 'wb') as f:
                pickle.dump(model, f)

            # Create result
            result = TrainingResult(
                job_id=job_id,
                status=TrainingStatus.COMPLETED.value,
                model=model,
                scores=scores,
                training_time=training_time,
                validation_scores=cv_scores,
                best_parameters=best_params,
                feature_importance=feature_importance,
                model_path=model_path,
                completed_at=datetime.now()
            )

            # Update job
            job.result = result
            job.status = TrainingStatus.COMPLETED.value
            job.completed_at = datetime.now()

            self.monitor.finish_monitoring(job_id, TrainingStatus.COMPLETED.value)
            self.monitor.update_progress(job_id, 1.0)

            self.logger.info(f"Training job {job_id} completed successfully")
            return result

        except Exception as e:
            error_msg = f"Training failed: {str(e)}"
            self.logger.error(f"Job {job_id} failed: {error_msg}")
            self.logger.error(traceback.format_exc())

            # Create failed result
            result = TrainingResult(
                job_id=job_id,
                status=TrainingStatus.FAILED.value,
                model=None,
                scores={},
                training_time=0.0,
                error_message=error_msg,
                completed_at=datetime.now()
            )

            # Update job
            job.result = result
            job.status = TrainingStatus.FAILED.value
            job.completed_at = datetime.now()
            job.error_message = error_msg

            self.monitor.finish_monitoring(job_id, TrainingStatus.FAILED.value)

            return result

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Get training job status."""
        if job_id not in self.jobs:
            return {"error": f"Job {job_id} not found"}

        job = self.jobs[job_id]
        metrics = self.monitor.get_metrics(job_id)

        return {
            "job_id": job_id,
            "status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "progress": metrics.get('progress', 0.0),
            "error_message": job.error_message
        }

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all training jobs."""
        return [self.get_job_status(job_id) for job_id in self.jobs.keys()]

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a training job."""
        if job_id not in self.jobs:
            return False

        job = self.jobs[job_id]
        if job.status == TrainingStatus.PENDING.value:
            job.status = TrainingStatus.CANCELLED.value
            job.completed_at = datetime.now()
            self.monitor.finish_monitoring(job_id, TrainingStatus.CANCELLED.value)
            return True

        return False

    def load_model(self, job_id: str) -> BaseEstimator | None:
        """Load a trained model with secure pickle verification."""
        if job_id not in self.jobs:
            return None

        job = self.jobs[job_id]
        if job.result and job.result.model_path:
            try:
                with open(job.result.model_path, 'rb') as f:
                    # Use secure pickle with migration support
                    return secure_load(f, allow_unsigned=True)
            except PickleSecurityError as e:
                self.logger.error(f"Security error loading model for job {job_id}: {str(e)}")
                raise
            except Exception as e:
                self.logger.error(f"Failed to load model for job {job_id}: {str(e)}")

        return None

    def get_training_statistics(self) -> dict[str, Any]:
        """Get training service statistics."""
        total_jobs = len(self.jobs)
        status_counts = {}

        for job in self.jobs.values():
            status = job.status
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_jobs": total_jobs,
            "status_distribution": status_counts,
            "available_models": list(self.available_models.keys())
        }


# Utility functions
def generate_sample_data(n_samples: int = 1000, task_type: str = "classification") -> tuple[pd.DataFrame, str]:
    """Generate sample training data."""
    np.random.seed(42)

    if task_type == "classification":
        X = np.random.randn(n_samples, 5)
        y = (X[:, 0] + X[:, 1] > 0).astype(int)

        df = pd.DataFrame(X, columns=['feature_1', 'feature_2', 'feature_3', 'feature_4', 'feature_5'])
        df['target'] = y

        return df, 'target'

    else:  # regression
        X = np.random.randn(n_samples, 5)
        y = X[:, 0] * 2 + X[:, 1] * 1.5 + np.random.randn(n_samples) * 0.1

        df = pd.DataFrame(X, columns=['feature_1', 'feature_2', 'feature_3', 'feature_4', 'feature_5'])
        df['target'] = y

        return df, 'target'


def create_training_request_from_dict(config: dict[str, Any]) -> TrainingRequest:
    """Create training request from dictionary."""
    return TrainingRequest(**config)


# Export main classes and functions
__all__ = [
    'TrainingService', 'TrainingRequest', 'TrainingResult', 'TrainingJob',
    'TrainingStatus', 'TrainingType', 'ValidationStrategy',
    'TrainingMonitor', 'HyperparameterTuner', 'CrossValidator', 'ModelEvaluator',
    'generate_sample_data', 'create_training_request_from_dict'
]
