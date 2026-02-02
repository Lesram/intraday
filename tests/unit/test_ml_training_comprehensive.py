"""
Comprehensive tests for backend.ml.training module.
Target: 376 missing statements -> 100% coverage
"""
import os
import pickle
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest
import numpy as np
import pandas as pd

# Import target module
from backend.ml.training import (
    TrainingStatus,
    TrainingType,
    ValidationStrategy,
    TrainingRequest,
    TrainingResult,
    TrainingJob,
    TrainingMonitor,
    HyperparameterTuner,
    CrossValidator,
    ModelEvaluator,
    TrainingService,
    generate_sample_data,
    create_training_request_from_dict,
    SKLEARN_AVAILABLE,
)

# Import models conditionally based on sklearn availability
if SKLEARN_AVAILABLE:
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.linear_model import LinearRegression, LogisticRegression
    from sklearn.svm import SVC, SVR
    from sklearn.model_selection import KFold, StratifiedKFold, TimeSeriesSplit
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
else:
    from backend.ml.training import (
        RandomForestClassifier,
        RandomForestRegressor,
        LinearRegression,
        LogisticRegression,
        SVC,
        SVR,
        KFold,
        StratifiedKFold,
        TimeSeriesSplit,
        accuracy_score,
        precision_score,
        recall_score,
        f1_score,
        mean_squared_error,
        mean_absolute_error,
        r2_score,
    )


# =============================================================================
# Enum Tests
# =============================================================================

class TestTrainingStatus:
    """Test TrainingStatus enum."""

    def test_all_values(self):
        """Test all status values exist."""
        assert TrainingStatus.PENDING.value == "pending"
        assert TrainingStatus.RUNNING.value == "running"
        assert TrainingStatus.COMPLETED.value == "completed"
        assert TrainingStatus.FAILED.value == "failed"
        assert TrainingStatus.CANCELLED.value == "cancelled"


class TestTrainingType:
    """Test TrainingType enum."""

    def test_all_values(self):
        """Test all training type values."""
        assert TrainingType.CLASSIFICATION.value == "classification"
        assert TrainingType.REGRESSION.value == "regression"
        assert TrainingType.CLUSTERING.value == "clustering"


class TestValidationStrategy:
    """Test ValidationStrategy enum."""

    def test_all_values(self):
        """Test all validation strategy values."""
        assert ValidationStrategy.K_FOLD.value == "k_fold"
        assert ValidationStrategy.STRATIFIED_K_FOLD.value == "stratified_k_fold"
        assert ValidationStrategy.TIME_SERIES_SPLIT.value == "time_series_split"
        assert ValidationStrategy.HOLDOUT.value == "holdout"


# =============================================================================
# Data Class Tests
# =============================================================================

class TestTrainingRequest:
    """Test TrainingRequest dataclass."""

    def test_creation_minimal(self):
        """Test minimal creation."""
        df = pd.DataFrame({"f1": [1, 2, 3], "target": [0, 1, 0]})
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=df,
            target_column="target"
        )
        
        assert request.model_type == "RandomForestClassifier"
        assert request.target_column == "target"
        assert request.test_size == 0.2
        assert request.shuffle is False  # Default is False for time-series safety
        assert request.random_state == 42

    def test_creation_full(self):
        """Test full creation."""
        df = pd.DataFrame({"f1": [1, 2], "f2": [3, 4], "y": [0, 1]})
        request = TrainingRequest(
            model_type="LogisticRegression",
            training_data=df,
            target_column="y",
            features=["f1", "f2"],
            validation_strategy="stratified_k_fold",
            test_size=0.3,
            shuffle=True,
            random_state=123,
            hyperparameters={"C": 1.0},
            tune_hyperparameters=True,
            tuning_params={"cv": 3},
            metadata={"experiment": "test"}
        )
        
        assert request.features == ["f1", "f2"]
        assert request.validation_strategy == "stratified_k_fold"
        assert request.test_size == 0.3
        assert request.shuffle is True
        assert request.hyperparameters == {"C": 1.0}
        assert request.tune_hyperparameters is True


class TestTrainingResult:
    """Test TrainingResult dataclass."""

    def test_creation(self):
        """Test result creation."""
        result = TrainingResult(
            job_id="job_001",
            status="completed",
            model=MagicMock(),
            scores={"accuracy": 0.95},
            training_time=5.5
        )
        
        assert result.job_id == "job_001"
        assert result.status == "completed"
        assert result.scores["accuracy"] == 0.95
        assert result.training_time == 5.5
        assert result.created_at is not None

    def test_creation_with_optionals(self):
        """Test result with optional fields."""
        result = TrainingResult(
            job_id="job_002",
            status="completed",
            model=None,
            scores={},
            training_time=0.0,
            validation_scores={"accuracy": [0.8, 0.9]},
            best_parameters={"n_estimators": 100},
            feature_importance={"f1": 0.5},
            model_path="/path/to/model",
            error_message=None
        )
        
        assert result.validation_scores == {"accuracy": [0.8, 0.9]}
        assert result.best_parameters["n_estimators"] == 100


class TestTrainingJob:
    """Test TrainingJob dataclass."""

    def test_creation(self):
        """Test job creation."""
        df = pd.DataFrame({"f1": [1, 2], "y": [0, 1]})
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=df,
            target_column="y"
        )
        
        job = TrainingJob(job_id="job_001", request=request)
        
        assert job.job_id == "job_001"
        assert job.status == TrainingStatus.PENDING.value
        assert job.created_at is not None


# =============================================================================
# Mock Model Tests (only run when sklearn is not available)
# =============================================================================

@pytest.mark.skipif(SKLEARN_AVAILABLE, reason="Tests mock classes only when sklearn unavailable")
class TestBaseEstimator:
    """Test BaseEstimator mock class."""

    def test_init(self):
        """Test initialization with kwargs."""
        from backend.ml.training import BaseEstimator
        estimator = BaseEstimator(param1=10, param2="value")
        assert estimator.param1 == 10
        assert estimator.param2 == "value"

    def test_fit(self):
        """Test fit method."""
        from backend.ml.training import BaseEstimator
        estimator = BaseEstimator()
        X = np.array([[1, 2], [3, 4]])
        y = np.array([0, 1])
        
        result = estimator.fit(X, y)
        
        assert result is estimator

    def test_predict(self):
        """Test predict method."""
        from backend.ml.training import BaseEstimator
        estimator = BaseEstimator()
        X = np.array([[1, 2], [3, 4]])
        
        result = estimator.predict(X)
        
        assert len(result) == 2

    def test_predict_proba(self):
        """Test predict_proba method."""
        from backend.ml.training import BaseEstimator
        estimator = BaseEstimator()
        X = np.array([[1, 2], [3, 4]])
        
        result = estimator.predict_proba(X)
        
        assert result.shape == (2, 2)


class TestRandomForestClassifier:
    """Test RandomForestClassifier class."""

    def test_init_defaults(self):
        """Test default initialization."""
        rf = RandomForestClassifier()
        assert rf.n_estimators == 100

    def test_init_custom(self):
        """Test custom initialization."""
        rf = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
        assert rf.n_estimators == 50
        assert rf.max_depth == 5
        assert rf.random_state == 42

    def test_fit_sets_feature_importances(self):
        """Test fit sets feature_importances_."""
        rf = RandomForestClassifier(random_state=42)
        X = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]])
        y = np.array([0, 1, 0, 1])
        
        rf.fit(X, y)
        
        assert rf.feature_importances_ is not None
        assert len(rf.feature_importances_) == 3


class TestRandomForestRegressor:
    """Test RandomForestRegressor class."""

    def test_init(self):
        """Test initialization."""
        rf = RandomForestRegressor(n_estimators=200, max_depth=10)
        assert rf.n_estimators == 200
        assert rf.max_depth == 10

    def test_fit_sets_feature_importances(self):
        """Test fit sets feature_importances_."""
        rf = RandomForestRegressor(random_state=42)
        X = np.array([[1, 2], [3, 4], [5, 6], [7, 8]])
        y = np.array([1.0, 2.0, 3.0, 4.0])
        
        rf.fit(X, y)
        
        assert len(rf.feature_importances_) == 2

    def test_predict(self):
        """Test predict returns continuous values."""
        rf = RandomForestRegressor(random_state=42)
        X = np.array([[1, 2], [3, 4], [5, 6], [7, 8]])
        y = np.array([1.0, 2.0, 3.0, 4.0])
        rf.fit(X, y)
        
        result = rf.predict(X)
        
        assert len(result) == 4


class TestLogisticRegression:
    """Test LogisticRegression class."""

    def test_init(self):
        """Test initialization."""
        lr = LogisticRegression(C=0.5, solver='liblinear')
        assert lr.C == 0.5
        assert lr.solver == 'liblinear'

    def test_fit_sets_coef(self):
        """Test fit sets coef_."""
        lr = LogisticRegression(random_state=42)
        X = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]])
        y = np.array([0, 1, 0, 1])
        
        lr.fit(X, y)
        
        assert lr.coef_ is not None


class TestLinearRegression:
    """Test LinearRegression class."""

    def test_fit(self):
        """Test fit sets coef_."""
        lr = LinearRegression()
        X = np.array([[1, 2], [3, 4], [5, 6], [7, 8]])
        y = np.array([1.0, 2.0, 3.0, 4.0])
        
        lr.fit(X, y)
        
        assert lr.coef_ is not None
        assert len(lr.coef_) == 2

    def test_predict(self):
        """Test predict returns values."""
        lr = LinearRegression()
        X = np.array([[1, 2], [3, 4], [5, 6], [7, 8]])
        y = np.array([1.0, 2.0, 3.0, 4.0])
        lr.fit(X, y)
        
        result = lr.predict(X)
        
        assert len(result) == 4


class TestSVC:
    """Test SVC class."""

    def test_init(self):
        """Test initialization."""
        svc = SVC(C=10, kernel='linear')
        assert svc.C == 10
        assert svc.kernel == 'linear'


class TestSVR:
    """Test SVR class."""

    def test_init(self):
        """Test initialization."""
        svr = SVR(C=5, kernel='poly')
        assert svr.C == 5
        assert svr.kernel == 'poly'

    def test_predict(self):
        """Test predict returns values."""
        svr = SVR()
        X = np.array([[1, 2], [3, 4], [5, 6], [7, 8]])
        y = np.array([1.0, 2.0, 3.0, 4.0])
        svr.fit(X, y)
        
        result = svr.predict(X)
        
        assert len(result) == 4


# =============================================================================
# CV Classes Tests
# =============================================================================

class TestKFold:
    """Test KFold class."""

    def test_init(self):
        """Test initialization."""
        kf = KFold(n_splits=10, shuffle=False)
        assert kf.n_splits == 10


class TestStratifiedKFold:
    """Test StratifiedKFold class."""

    def test_init(self):
        """Test initialization."""
        skf = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
        assert skf.n_splits == 3


class TestTimeSeriesSplit:
    """Test TimeSeriesSplit class."""

    def test_init(self):
        """Test initialization."""
        tss = TimeSeriesSplit(n_splits=5)
        assert tss.n_splits == 5


# =============================================================================
# Utility Functions Tests
# =============================================================================

class TestTrainTestSplit:
    """Test train_test_split function."""

    def test_split_arrays(self):
        """Test splitting numpy arrays."""
        from sklearn.model_selection import train_test_split
        X = np.array([[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]])
        y = np.array([0, 1, 0, 1, 0])
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.4, random_state=42)
        
        assert len(X_train) == 3
        assert len(X_test) == 2
        assert len(y_train) == 3
        assert len(y_test) == 2

    def test_split_dataframes(self):
        """Test splitting pandas DataFrames."""
        from sklearn.model_selection import train_test_split
        X = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [5, 4, 3, 2, 1]})
        y = pd.Series([0, 1, 0, 1, 0], name="target")
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.4, random_state=42)
        
        assert len(X_train) == 3
        assert len(X_test) == 2


class TestCrossValScore:
    """Test cross_val_score function."""

    def test_returns_scores(self):
        """Test returns array of scores."""
        from sklearn.model_selection import cross_val_score
        model = RandomForestClassifier(random_state=42)
        X = np.array([[1, 2], [3, 4], [5, 6], [7, 8], [9, 10], [11, 12]])
        y = np.array([0, 1, 0, 1, 0, 1])
        
        scores = cross_val_score(model, X, y, cv=2)
        
        assert len(scores) == 2


class TestMetricFunctions:
    """Test metric functions."""

    def test_accuracy_score(self):
        """Test accuracy_score."""
        result = accuracy_score([1, 0, 1, 0], [1, 0, 1, 0])
        assert result == 1.0

    def test_precision_score(self):
        """Test precision_score."""
        result = precision_score([1, 0, 1, 0], [1, 0, 1, 1], average='binary')
        assert 0 <= result <= 1

    def test_recall_score(self):
        """Test recall_score."""
        result = recall_score([1, 0, 1, 0], [1, 0, 1, 1], average='binary')
        assert 0 <= result <= 1

    def test_f1_score(self):
        """Test f1_score."""
        result = f1_score([1, 0, 1, 0], [1, 0, 1, 1], average='binary')
        assert 0 <= result <= 1

    def test_mean_squared_error(self):
        """Test mean_squared_error."""
        result = mean_squared_error([1.0, 2.0, 3.0], [1.1, 2.1, 3.1])
        assert result >= 0

    def test_mean_absolute_error(self):
        """Test mean_absolute_error."""
        result = mean_absolute_error([1.0, 2.0, 3.0], [1.1, 2.1, 3.1])
        assert result >= 0

    def test_r2_score(self):
        """Test r2_score."""
        result = r2_score([1.0, 2.0, 3.0], [1.1, 2.0, 2.9])
        assert result <= 1


# =============================================================================
# TrainingMonitor Tests
# =============================================================================

class TestTrainingMonitor:
    """Test TrainingMonitor class."""

    def test_init(self):
        """Test initialization."""
        monitor = TrainingMonitor()
        assert monitor.metrics == {}
        assert monitor.start_time is None

    def test_start_monitoring(self):
        """Test start_monitoring."""
        monitor = TrainingMonitor()
        
        monitor.start_monitoring("job_001")
        
        assert "job_001" in monitor.metrics
        assert monitor.metrics["job_001"]["status"] == TrainingStatus.RUNNING.value
        assert monitor.metrics["job_001"]["progress"] == 0.0

    def test_update_progress(self):
        """Test update_progress."""
        monitor = TrainingMonitor()
        monitor.start_monitoring("job_001")
        
        monitor.update_progress("job_001", 0.5)
        
        assert monitor.metrics["job_001"]["progress"] == 0.5

    def test_log_training_step(self):
        """Test log_training_step."""
        monitor = TrainingMonitor()
        monitor.log_training_step("job_001", "Data Prep", {"rows": 100})

    def test_finish_monitoring(self):
        """Test finish_monitoring."""
        monitor = TrainingMonitor()
        monitor.start_monitoring("job_001")
        
        monitor.finish_monitoring("job_001", "completed")
        
        assert monitor.metrics["job_001"]["status"] == "completed"
        assert "end_time" in monitor.metrics["job_001"]
        assert "duration" in monitor.metrics["job_001"]

    def test_get_metrics(self):
        """Test get_metrics."""
        monitor = TrainingMonitor()
        monitor.start_monitoring("job_001")
        
        metrics = monitor.get_metrics("job_001")
        
        assert "start_time" in metrics
        assert metrics["status"] == TrainingStatus.RUNNING.value

    def test_get_metrics_not_found(self):
        """Test get_metrics for unknown job."""
        monitor = TrainingMonitor()
        
        metrics = monitor.get_metrics("unknown")
        
        assert metrics == {}


# =============================================================================
# HyperparameterTuner Tests
# =============================================================================

class TestHyperparameterTuner:
    """Test HyperparameterTuner class."""

    def test_init(self):
        """Test initialization."""
        tuner = HyperparameterTuner()
        assert "RandomForestClassifier" in tuner.default_param_grids
        assert "LogisticRegression" in tuner.default_param_grids

    def test_tune_hyperparameters_grid_search(self):
        """Test tuning with grid search."""
        tuner = HyperparameterTuner()
        model = RandomForestClassifier()
        X_train = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [5, 4, 3, 2, 1]})
        y_train = pd.Series([0, 1, 0, 1, 0])
        
        best_model, best_params = tuner.tune_hyperparameters(
            model, X_train, y_train, search_type='grid', cv=3
        )
        
        assert best_model is not None
        assert isinstance(best_params, dict)

    def test_tune_hyperparameters_random_search(self):
        """Test tuning with random search."""
        tuner = HyperparameterTuner()
        model = LogisticRegression()
        X_train = pd.DataFrame({"a": [1, 2, 3], "b": [3, 2, 1]})
        y_train = pd.Series([0, 1, 0])
        
        best_model, best_params = tuner.tune_hyperparameters(
            model, X_train, y_train, search_type='random', cv=2, n_iter=5
        )
        
        assert best_model is not None

    def test_tune_no_param_grid(self):
        """Test tuning with no param grid returns original model."""
        tuner = HyperparameterTuner()
        
        # Custom model with no default param grid
        from sklearn.base import BaseEstimator as SklearnBaseEstimator
        
        class CustomModel(SklearnBaseEstimator):
            def fit(self, X, y):
                return self
            def predict(self, X):
                return np.zeros(len(X))
        
        model = CustomModel()
        X_train = pd.DataFrame({"a": [1, 2, 3]})
        y_train = pd.Series([0, 1, 0])
        
        result_model, result_params = tuner.tune_hyperparameters(model, X_train, y_train)
        
        assert result_model is model
        assert result_params == {}


# =============================================================================
# CrossValidator Tests
# =============================================================================

class TestCrossValidator:
    """Test CrossValidator class."""

    def test_init(self):
        """Test initialization."""
        cv = CrossValidator()
        assert cv.logger is not None

    def test_get_cv_strategy_kfold(self):
        """Test getting k-fold strategy."""
        cv = CrossValidator()
        
        strategy = cv.get_cv_strategy(ValidationStrategy.K_FOLD.value, n_splits=5)
        
        assert isinstance(strategy, KFold)
        assert strategy.n_splits == 5

    def test_get_cv_strategy_stratified(self):
        """Test getting stratified k-fold strategy."""
        cv = CrossValidator()
        
        strategy = cv.get_cv_strategy(ValidationStrategy.STRATIFIED_K_FOLD.value, n_splits=3)
        
        assert isinstance(strategy, StratifiedKFold)

    def test_get_cv_strategy_timeseries(self):
        """Test getting time series split strategy."""
        cv = CrossValidator()
        
        strategy = cv.get_cv_strategy(ValidationStrategy.TIME_SERIES_SPLIT.value, n_splits=4)
        
        assert isinstance(strategy, TimeSeriesSplit)

    def test_get_cv_strategy_default(self):
        """Test default strategy is k-fold."""
        cv = CrossValidator()
        
        strategy = cv.get_cv_strategy("unknown", n_splits=5)
        
        assert isinstance(strategy, KFold)

    def test_perform_cross_validation(self):
        """Test performing cross validation."""
        cv = CrossValidator()
        model = RandomForestClassifier()
        X = pd.DataFrame({"a": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
        y = pd.Series([0, 1, 0, 1, 0, 1, 0, 1, 0, 1])
        
        results = cv.perform_cross_validation(model, X, y, n_splits=3)
        
        assert "accuracy" in results
        assert len(results["accuracy"]) == 3


# =============================================================================
# ModelEvaluator Tests
# =============================================================================

class TestModelEvaluator:
    """Test ModelEvaluator class."""

    def test_init(self):
        """Test initialization."""
        evaluator = ModelEvaluator()
        assert evaluator.logger is not None

    def test_evaluate_classification_model(self):
        """Test evaluating classification model."""
        evaluator = ModelEvaluator()
        model = RandomForestClassifier(random_state=42)
        X_train = pd.DataFrame({"a": [1, 2, 3, 4, 5, 6], "b": [6, 5, 4, 3, 2, 1]})
        y_train = pd.Series([0, 1, 0, 1, 0, 1])
        model.fit(X_train, y_train)
        X_test = pd.DataFrame({"a": [1, 2, 3], "b": [3, 2, 1]})
        y_test = pd.Series([0, 1, 0])
        
        scores = evaluator.evaluate_classification_model(model, X_test, y_test)
        
        assert "accuracy" in scores
        assert "precision" in scores
        assert "recall" in scores
        assert "f1" in scores

    def test_evaluate_regression_model(self):
        """Test evaluating regression model."""
        evaluator = ModelEvaluator()
        model = LinearRegression()
        X_train = pd.DataFrame({"a": [1, 2, 3, 4, 5]})
        y_train = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        model.fit(X_train, y_train)
        X_test = pd.DataFrame({"a": [1, 2, 3]})
        y_test = pd.Series([1.0, 2.0, 3.0])
        
        scores = evaluator.evaluate_regression_model(model, X_test, y_test)
        
        assert "mse" in scores
        assert "mae" in scores
        assert "r2" in scores
        assert "rmse" in scores

    def test_get_feature_importance_tree(self):
        """Test feature importance from tree-based model."""
        evaluator = ModelEvaluator()
        model = RandomForestClassifier(random_state=42)
        X = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]])
        y = np.array([0, 1, 0, 1])
        model.fit(X, y)
        
        importance = evaluator.get_feature_importance(model, ["f1", "f2", "f3"])
        
        assert "f1" in importance
        assert "f2" in importance
        assert "f3" in importance

    def test_get_feature_importance_linear(self):
        """Test feature importance from linear model."""
        evaluator = ModelEvaluator()
        model = LogisticRegression(random_state=42)
        X = np.array([[1, 2], [3, 4], [5, 6], [7, 8]])
        y = np.array([0, 1, 0, 1])
        model.fit(X, y)
        
        importance = evaluator.get_feature_importance(model, ["f1", "f2"])
        
        assert len(importance) == 2

    def test_get_feature_importance_no_support(self):
        """Test feature importance when model doesn't support it."""
        evaluator = ModelEvaluator()
        # Create a mock model without feature_importances_ or coef_
        model = MagicMock()
        del model.feature_importances_
        del model.coef_
        
        importance = evaluator.get_feature_importance(model, ["f1", "f2"])
        
        assert importance == {}


# =============================================================================
# TrainingService Tests
# =============================================================================

class TestTrainingService:
    """Test TrainingService class."""

    @pytest.fixture
    def temp_model_path(self):
        """Create temporary model storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def service(self, temp_model_path):
        """Create TrainingService instance."""
        return TrainingService(model_storage_path=temp_model_path)

    def test_init(self, temp_model_path):
        """Test initialization."""
        service = TrainingService(model_storage_path=temp_model_path)
        
        assert service.model_storage_path == temp_model_path
        assert os.path.exists(temp_model_path)
        assert "RandomForestClassifier" in service.available_models

    def test_create_model_classifier(self, service):
        """Test creating classifier model."""
        model = service.create_model("RandomForestClassifier")
        
        assert isinstance(model, RandomForestClassifier)
        assert model.random_state == 42

    def test_create_model_regressor(self, service):
        """Test creating regressor model - RandomForestRegressor."""
        model = service.create_model("RandomForestRegressor")
        
        assert isinstance(model, RandomForestRegressor)

    def test_create_model_with_hyperparameters(self, service):
        """Test creating model with custom hyperparameters."""
        model = service.create_model(
            "RandomForestClassifier",
            hyperparameters={"n_estimators": 50, "max_depth": 5, "random_state": 42}
        )
        
        assert model.n_estimators == 50
        assert model.max_depth == 5

    def test_create_model_unsupported(self, service):
        """Test creating unsupported model raises error."""
        with pytest.raises(ValueError, match="Unsupported model type"):
            service.create_model("UnsupportedModel")

    def test_submit_training_job(self, service):
        """Test submitting a training job."""
        df = pd.DataFrame({"f1": [1, 2, 3, 4, 5], "target": [0, 1, 0, 1, 0]})
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=df,
            target_column="target"
        )
        
        job_id = service.submit_training_job(request)
        
        assert job_id.startswith("training_")
        assert job_id in service.jobs

    def test_train_model_classification(self, service):
        """Test training a classification model."""
        df = pd.DataFrame({
            "f1": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "f2": [10, 9, 8, 7, 6, 5, 4, 3, 2, 1],
            "target": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
        })
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=df,
            target_column="target",
            features=["f1", "f2"]
        )
        
        job_id = service.submit_training_job(request)
        result = service.train_model(job_id)
        
        assert result.status == TrainingStatus.COMPLETED.value
        assert result.model is not None
        assert "accuracy" in result.scores

    def test_train_model_regression(self, service):
        """Test training a regression model."""
        df = pd.DataFrame({
            "f1": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            "target": [1.1, 2.2, 3.3, 4.4, 5.5, 6.6, 7.7, 8.8, 9.9, 11.0]
        })
        request = TrainingRequest(
            model_type="RandomForestRegressor",
            training_data=df,
            target_column="target"
        )
        
        job_id = service.submit_training_job(request)
        result = service.train_model(job_id)
        
        assert result.status == TrainingStatus.COMPLETED.value
        assert "mse" in result.scores

    def test_train_model_with_tuning(self, service):
        """Test training with hyperparameter tuning."""
        df = pd.DataFrame({
            "f1": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "target": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
        })
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=df,
            target_column="target",
            tune_hyperparameters=True,
            tuning_params={"cv": 2}
        )
        
        job_id = service.submit_training_job(request)
        result = service.train_model(job_id)
        
        assert result.status == TrainingStatus.COMPLETED.value
        assert result.best_parameters is not None

    def test_train_model_job_not_found(self, service):
        """Test training with unknown job raises error."""
        with pytest.raises(ValueError, match="not found"):
            service.train_model("unknown_job")

    def test_get_job_status(self, service):
        """Test getting job status."""
        df = pd.DataFrame({"f1": [1, 2, 3], "target": [0, 1, 0]})
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=df,
            target_column="target"
        )
        job_id = service.submit_training_job(request)
        
        status = service.get_job_status(job_id)
        
        assert status["job_id"] == job_id
        assert status["status"] == TrainingStatus.PENDING.value

    def test_get_job_status_not_found(self, service):
        """Test getting status for unknown job."""
        status = service.get_job_status("unknown")
        
        assert "error" in status

    def test_list_jobs(self, service):
        """Test listing all jobs."""
        df = pd.DataFrame({"f1": [1, 2], "target": [0, 1]})
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=df,
            target_column="target"
        )
        
        service.submit_training_job(request)
        service.submit_training_job(request)
        
        jobs = service.list_jobs()
        
        assert len(jobs) == 2

    def test_cancel_job(self, service):
        """Test cancelling a pending job."""
        df = pd.DataFrame({"f1": [1, 2], "target": [0, 1]})
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=df,
            target_column="target"
        )
        job_id = service.submit_training_job(request)
        
        result = service.cancel_job(job_id)
        
        assert result is True
        assert service.jobs[job_id].status == TrainingStatus.CANCELLED.value

    def test_cancel_job_not_found(self, service):
        """Test cancelling unknown job."""
        result = service.cancel_job("unknown")
        assert result is False

    def test_load_model(self, service):
        """Test loading a trained model."""
        df = pd.DataFrame({
            "f1": [1, 2, 3, 4, 5],
            "target": [0, 1, 0, 1, 0]
        })
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=df,
            target_column="target"
        )
        job_id = service.submit_training_job(request)
        service.train_model(job_id)
        
        model = service.load_model(job_id)
        
        assert model is not None

    def test_load_model_job_not_found(self, service):
        """Test loading model for unknown job."""
        result = service.load_model("unknown")
        assert result is None

    def test_get_training_statistics(self, service):
        """Test getting training statistics."""
        df = pd.DataFrame({"f1": [1, 2], "target": [0, 1]})
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=df,
            target_column="target"
        )
        service.submit_training_job(request)
        
        stats = service.get_training_statistics()
        
        assert stats["total_jobs"] == 1
        assert "pending" in stats["status_distribution"]
        assert "RandomForestClassifier" in stats["available_models"]


# =============================================================================
# Utility Functions Tests
# =============================================================================

class TestGenerateSampleData:
    """Test generate_sample_data function."""

    def test_classification_data(self):
        """Test generating classification data."""
        df, target_col = generate_sample_data(n_samples=100, task_type="classification")
        
        assert len(df) == 100
        assert target_col == "target"
        assert "target" in df.columns
        assert set(df["target"].unique()).issubset({0, 1})

    def test_regression_data(self):
        """Test generating regression data."""
        df, target_col = generate_sample_data(n_samples=50, task_type="regression")
        
        assert len(df) == 50
        assert target_col == "target"
        assert df["target"].dtype in [np.float64, np.float32]


class TestCreateTrainingRequestFromDict:
    """Test create_training_request_from_dict function."""

    def test_create_request(self):
        """Test creating request from dict."""
        df = pd.DataFrame({"f1": [1, 2], "target": [0, 1]})
        config = {
            "model_type": "LogisticRegression",
            "training_data": df,
            "target_column": "target",
            "test_size": 0.3
        }
        
        request = create_training_request_from_dict(config)
        
        assert request.model_type == "LogisticRegression"
        assert request.test_size == 0.3

# =============================================================================
# Error Handling and Edge Cases
# =============================================================================

class TestHyperparameterTunerErrors:
    """Test error handling in HyperparameterTuner."""

    def test_tune_hyperparameters_grid_search_exception(self):
        """Test error handling when tuning fails due to GridSearchCV exception."""
        tuner = HyperparameterTuner()
        
        # Create a simple model
        model = RandomForestClassifier(n_estimators=10)
        
        X = pd.DataFrame({"f1": [1, 2, 3, 4, 5]})
        y = pd.Series([0, 1, 0, 1, 0])
        
        param_grid = {"n_estimators": [10, 20]}
        
        # Patch GridSearchCV to raise exception
        with patch("backend.ml.training.GridSearchCV") as mock_grid:
            mock_grid.return_value.fit.side_effect = Exception("Search failed")
            
            result_model, best_params = tuner.tune_hyperparameters(
                model, X, y, param_grid, search_type="grid"
            )
        
        # Should return original model and empty params on failure
        assert result_model is model
        assert best_params == {}


class TestCrossValidatorErrors:
    """Test error handling in CrossValidator."""

    def test_cross_validation_exception(self):
        """Test error handling when CV fails."""
        cv = CrossValidator()
        
        model = MagicMock()
        X = pd.DataFrame({"f1": [1, 2, 3]})
        y = pd.Series([0, 1, 0])
        
        with patch("backend.ml.training.cross_val_score", side_effect=Exception("CV failed")):
            results = cv.perform_cross_validation(model, X, y)
        
        # Should return empty dict on failure
        assert results == {}


class TestModelEvaluatorErrors:
    """Test error handling in ModelEvaluator."""

    def test_classification_evaluation_exception(self):
        """Test error handling when classification evaluation fails."""
        evaluator = ModelEvaluator()
        
        model = MagicMock()
        model.predict.side_effect = Exception("Prediction failed")
        
        X = pd.DataFrame({"f1": [1, 2, 3]})
        y = pd.Series([0, 1, 0])
        
        scores = evaluator.evaluate_classification_model(model, X, y)
        
        # Should return empty dict on failure
        assert scores == {}

    def test_regression_evaluation_exception(self):
        """Test error handling when regression evaluation fails."""
        evaluator = ModelEvaluator()
        
        model = MagicMock()
        model.predict.side_effect = Exception("Prediction failed")
        
        X = pd.DataFrame({"f1": [1, 2, 3]})
        y = pd.Series([1.0, 2.0, 3.0])
        
        scores = evaluator.evaluate_regression_model(model, X, y)
        
        # Should return empty dict on failure
        assert scores == {}

    def test_feature_importance_exception(self):
        """Test error handling when feature importance extraction fails."""
        evaluator = ModelEvaluator()
        
        model = MagicMock()
        # Property access that raises
        type(model).feature_importances_ = property(lambda x: (_ for _ in ()).throw(Exception("No importances")))
        
        scores = evaluator.get_feature_importance(model, ["f1", "f2"])
        
        # Should return empty dict on failure
        assert scores == {}


class TestTrainingServiceErrors:
    """Test error handling in TrainingService."""

    def test_cancel_running_job(self, tmp_path):
        """Test cancelling a running job fails."""
        service = TrainingService(model_storage_path=str(tmp_path))
        
        df = pd.DataFrame({"f1": [1, 2, 3], "target": [0, 1, 0]})
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=df,
            target_column="target"
        )
        
        job_id = service.submit_training_job(request)
        
        # Change job status to running
        service.jobs[job_id].status = TrainingStatus.RUNNING.value
        
        # Cancel should fail for running job
        result = service.cancel_job(job_id)
        assert result is False

    def test_load_model_no_model_path(self, tmp_path):
        """Test loading model when no model path exists."""
        service = TrainingService(model_storage_path=str(tmp_path))
        
        df = pd.DataFrame({"f1": [1, 2, 3], "target": [0, 1, 0]})
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=df,
            target_column="target"
        )
        
        job_id = service.submit_training_job(request)
        
        # Result exists but no model_path
        service.jobs[job_id].result = MagicMock()
        service.jobs[job_id].result.model_path = None
        
        model = service.load_model(job_id)
        assert model is None

    def test_load_model_file_error(self, tmp_path):
        """Test loading model when file read fails."""
        service = TrainingService(model_storage_path=str(tmp_path))
        
        df = pd.DataFrame({"f1": [1, 2, 3], "target": [0, 1, 0]})
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=df,
            target_column="target"
        )
        
        job_id = service.submit_training_job(request)
        
        # Result exists with invalid model_path
        service.jobs[job_id].result = MagicMock()
        service.jobs[job_id].result.model_path = str(tmp_path / "nonexistent.pkl")
        
        model = service.load_model(job_id)
        assert model is None

    def test_train_model_with_exception(self, tmp_path):
        """Test training model that raises exception during fit."""
        service = TrainingService(model_storage_path=str(tmp_path))
        
        df = pd.DataFrame({"f1": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], "target": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]})
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=df,
            target_column="target"
        )
        
        job_id = service.submit_training_job(request)
        
        # Patch the model to raise during fit
        with patch.object(service, 'create_model') as mock_create:
            mock_model = MagicMock()
            mock_model.fit.side_effect = Exception("Training explosion")
            mock_create.return_value = mock_model
            
            result = service.train_model(job_id)
        
        assert result.status == TrainingStatus.FAILED.value
        assert "Training explosion" in result.error_message or "Training failed" in result.error_message

    def test_load_model_pickle_security_error(self, tmp_path):
        """Test loading model with pickle security error."""
        from backend.utils.secure_pickle import PickleSecurityError
        
        service = TrainingService(model_storage_path=str(tmp_path))
        
        df = pd.DataFrame({"f1": [1, 2, 3], "target": [0, 1, 0]})
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=df,
            target_column="target"
        )
        
        job_id = service.submit_training_job(request)
        
        # Create a mock result with a model path
        model_file = tmp_path / "model.pkl"
        model_file.write_bytes(b"malicious content")
        
        service.jobs[job_id].result = MagicMock()
        service.jobs[job_id].result.model_path = str(model_file)
        
        with patch("backend.ml.training.secure_load", side_effect=PickleSecurityError("Signature mismatch")):
            with pytest.raises(PickleSecurityError):
                service.load_model(job_id)
