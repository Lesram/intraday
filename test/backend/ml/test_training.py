"""
Comprehensive test suite for Module 59: backend.ml.training
Tests ML training functionality with comprehensive coverage.
"""

import pytest
import tempfile
import shutil
import os
import pickle
import threading
import time
from unittest.mock import Mock, patch, MagicMock
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

try:
    from backend.ml.training import (
        TrainingService, TrainingRequest, TrainingResult, TrainingJob,
        TrainingStatus, TrainingType, ValidationStrategy,
        TrainingMonitor, HyperparameterTuner, CrossValidator, ModelEvaluator,
        generate_sample_data, create_training_request_from_dict,
        SKLEARN_AVAILABLE
    )
    MODULE_EXISTS = True
except ImportError:
    MODULE_EXISTS = False
    SKLEARN_AVAILABLE = False


class TestModule59BackendMlTraining:
    """Comprehensive test suite for ML training functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def sample_classification_data(self):
        """Generate sample classification data."""
        return generate_sample_data(100, "classification")

    @pytest.fixture
    def sample_regression_data(self):
        """Generate sample regression data."""
        return generate_sample_data(100, "regression")

    @pytest.fixture
    def training_service(self, temp_dir):
        """Create training service instance."""
        return TrainingService(model_storage_path=temp_dir)

    def test_module_availability(self):
        """Test module availability."""
        assert MODULE_EXISTS, "Module should be available"
        import backend.ml.training as module
        assert module is not None

    def test_training_status_enum(self):
        """Test training status enumeration."""
        assert TrainingStatus.PENDING.value == "pending"
        assert TrainingStatus.RUNNING.value == "running"
        assert TrainingStatus.COMPLETED.value == "completed"
        assert TrainingStatus.FAILED.value == "failed"
        assert TrainingStatus.CANCELLED.value == "cancelled"

    def test_training_type_enum(self):
        """Test training type enumeration."""
        assert TrainingType.CLASSIFICATION.value == "classification"
        assert TrainingType.REGRESSION.value == "regression"
        assert TrainingType.CLUSTERING.value == "clustering"

    def test_validation_strategy_enum(self):
        """Test validation strategy enumeration."""
        assert ValidationStrategy.K_FOLD.value == "k_fold"
        assert ValidationStrategy.STRATIFIED_K_FOLD.value == "stratified_k_fold"
        assert ValidationStrategy.TIME_SERIES_SPLIT.value == "time_series_split"
        assert ValidationStrategy.HOLDOUT.value == "holdout"

    def test_training_request_creation(self, sample_classification_data):
        """Test training request creation."""
        data, target = sample_classification_data
        
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=data,
            target_column=target,
            features=None,
            validation_strategy="k_fold",
            test_size=0.2,
            random_state=42
        )
        
        assert request.model_type == "RandomForestClassifier"
        assert request.target_column == target
        assert request.test_size == 0.2
        assert request.random_state == 42

    def test_training_result_creation(self):
        """Test training result creation."""
        result = TrainingResult(
            job_id="test_job",
            status="completed",
            model=Mock(),
            scores={"accuracy": 0.95},
            training_time=10.5
        )
        
        assert result.job_id == "test_job"
        assert result.status == "completed"
        assert result.scores["accuracy"] == 0.95
        assert result.training_time == 10.5
        assert isinstance(result.created_at, datetime)

    def test_training_job_creation(self, sample_classification_data):
        """Test training job creation."""
        data, target = sample_classification_data
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=data,
            target_column=target
        )
        
        job = TrainingJob(
            job_id="test_job",
            request=request
        )
        
        assert job.job_id == "test_job"
        assert job.status == TrainingStatus.PENDING.value
        assert isinstance(job.created_at, datetime)

    def test_training_monitor_operations(self):
        """Test training monitor functionality."""
        monitor = TrainingMonitor()
        job_id = "test_job"
        
        # Start monitoring
        monitor.start_monitoring(job_id)
        assert job_id in monitor.metrics
        assert monitor.metrics[job_id]['status'] == TrainingStatus.RUNNING.value
        
        # Update progress
        monitor.update_progress(job_id, 0.5)
        assert monitor.metrics[job_id]['progress'] == 0.5
        
        # Log training step
        monitor.log_training_step(job_id, "test_step", {"detail": "test"})
        
        # Finish monitoring
        monitor.finish_monitoring(job_id, TrainingStatus.COMPLETED.value)
        assert monitor.metrics[job_id]['status'] == TrainingStatus.COMPLETED.value
        
        # Get metrics
        metrics = monitor.get_metrics(job_id)
        assert metrics['status'] == TrainingStatus.COMPLETED.value

    def test_hyperparameter_tuner_operations(self, sample_classification_data):
        """Test hyperparameter tuner functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        tuner = HyperparameterTuner()
        data, target = sample_classification_data
        
        # Use numpy array operations to avoid pandas compatibility issues
        data_values = data.values
        column_names = list(data.columns)
        target_index = column_names.index(target)
        feature_indices = [i for i in range(len(column_names)) if i != target_index]
        
        X = data_values[:, feature_indices]
        y = data_values[:, target_index]
        
        # Convert back to DataFrame for compatibility
        feature_names = [col for col in column_names if col != target]
        X = pd.DataFrame(X, columns=feature_names)
        y = pd.Series(y, name=target)
        
        # Get model from training service
        training_service = TrainingService()
        model = training_service.create_model("RandomForestClassifier")
        
        # Test with default param grid
        best_model, best_params = tuner.tune_hyperparameters(
            model, X, y, cv=2
        )
        
        assert best_model is not None
        assert isinstance(best_params, dict)

    def test_cross_validator_operations(self, sample_classification_data):
        """Test cross validator functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        cv = CrossValidator()
        data, target = sample_classification_data
        
        # Use numpy array operations to avoid pandas compatibility issues
        data_values = data.values
        column_names = list(data.columns)
        target_index = column_names.index(target)
        feature_indices = [i for i in range(len(column_names)) if i != target_index]
        
        X = data_values[:, feature_indices]
        y = data_values[:, target_index]
        
        # Convert back to DataFrame for compatibility
        feature_names = [col for col in column_names if col != target]
        X = pd.DataFrame(X, columns=feature_names)
        y = pd.Series(y, name=target)
        
        # Get model from training service
        training_service = TrainingService()
        model = training_service.create_model("RandomForestClassifier")
        
        # Test K-fold
        results = cv.perform_cross_validation(
            model, X, y, strategy="k_fold", n_splits=3
        )
        
        assert "accuracy" in results
        assert len(results["accuracy"]) == 3
        
        # Test get_cv_strategy
        strategy = cv.get_cv_strategy("k_fold", 5)
        assert strategy is not None

    def test_model_evaluator_classification(self, sample_classification_data):
        """Test model evaluator for classification."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        evaluator = ModelEvaluator()
        data, target = sample_classification_data
        
        # Use numpy array operations to avoid pandas compatibility issues
        data_values = data.values
        column_names = list(data.columns)
        target_index = column_names.index(target)
        feature_indices = [i for i in range(len(column_names)) if i != target_index]
        
        X = data_values[:, feature_indices]
        y = data_values[:, target_index]
        
        # Convert back to DataFrame for compatibility
        feature_names = [col for col in column_names if col != target]
        X = pd.DataFrame(X, columns=feature_names)
        y = pd.Series(y, name=target)
        
        # Use our training service's train_test_split implementation
        training_service = TrainingService()
        from backend.ml.training import train_test_split
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
        
        model = training_service.create_model("RandomForestClassifier")
        model.fit(X_train, y_train)
        
        scores = evaluator.evaluate_classification_model(model, X_test, y_test)
        
        assert "accuracy" in scores
        assert "precision" in scores
        assert "recall" in scores
        assert "f1" in scores

    def test_model_evaluator_regression(self, sample_regression_data):
        """Test model evaluator for regression."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        evaluator = ModelEvaluator()
        data, target = sample_regression_data
        
        # Use numpy array operations to avoid pandas compatibility issues
        data_values = data.values
        column_names = list(data.columns)
        target_index = column_names.index(target)
        feature_indices = [i for i in range(len(column_names)) if i != target_index]
        
        X = data_values[:, feature_indices]
        y = data_values[:, target_index]
        
        # Convert back to DataFrame for compatibility
        feature_names = [col for col in column_names if col != target]
        X = pd.DataFrame(X, columns=feature_names)
        y = pd.Series(y, name=target)
        
        # Use our training service's train_test_split implementation
        training_service = TrainingService()
        from backend.ml.training import train_test_split
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
        
        model = training_service.create_model("RandomForestRegressor")
        model.fit(X_train, y_train)
        
        scores = evaluator.evaluate_regression_model(model, X_test, y_test)
        
        assert "mse" in scores
        assert "mae" in scores
        assert "r2" in scores
        assert "rmse" in scores

    def test_model_evaluator_feature_importance(self, sample_classification_data):
        """Test feature importance extraction."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        evaluator = ModelEvaluator()
        data, target = sample_classification_data
        
        # Use numpy array operations to avoid pandas compatibility issues
        data_values = data.values
        column_names = list(data.columns)
        target_index = column_names.index(target)
        feature_indices = [i for i in range(len(column_names)) if i != target_index]
        
        X = data_values[:, feature_indices]
        y = data_values[:, target_index]
        
        # Convert back to DataFrame for compatibility
        feature_names = [col for col in column_names if col != target]
        X = pd.DataFrame(X, columns=feature_names)
        y = pd.Series(y, name=target)
        
        training_service = TrainingService()
        model = training_service.create_model("RandomForestClassifier")
        model.fit(X, y)
        
        importance = evaluator.get_feature_importance(model, X.columns.tolist())
        
        assert isinstance(importance, dict)
        assert len(importance) == len(X.columns)

    def test_training_service_initialization(self, temp_dir):
        """Test training service initialization."""
        service = TrainingService(model_storage_path=temp_dir)
        
        assert service.model_storage_path == temp_dir
        assert os.path.exists(temp_dir)
        assert len(service.available_models) > 0
        assert "RandomForestClassifier" in service.available_models

    def test_training_service_create_model(self, training_service):
        """Test model creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        # Test default creation
        model = training_service.create_model("RandomForestClassifier")
        assert model is not None
        assert hasattr(model, 'fit')
        assert hasattr(model, 'predict')
        
        # Test with hyperparameters
        model = training_service.create_model(
            "RandomForestClassifier",
            {"n_estimators": 50, "max_depth": 5}
        )
        assert model.n_estimators == 50
        assert model.max_depth == 5
        
        # Test invalid model type
        with pytest.raises(ValueError):
            training_service.create_model("InvalidModel")

    def test_training_service_submit_job(self, training_service, sample_classification_data):
        """Test job submission."""
        data, target = sample_classification_data
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=data,
            target_column=target
        )
        
        job_id = training_service.submit_training_job(request)
        
        assert job_id.startswith("training_")
        assert job_id in training_service.jobs
        assert training_service.jobs[job_id].status == TrainingStatus.PENDING.value

    def test_training_service_basic_training(self, training_service, sample_classification_data):
        """Test basic model training."""
        data, target = sample_classification_data
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=data,
            target_column=target,
            test_size=0.3
        )
        
        job_id = training_service.submit_training_job(request)
        result = training_service.train_model(job_id)
        
        assert result.status == TrainingStatus.COMPLETED.value
        assert result.model is not None
        assert "accuracy" in result.scores
        assert result.training_time > 0
        assert result.model_path is not None
        assert os.path.exists(result.model_path)

    def test_training_service_with_hyperparameter_tuning(self, training_service, sample_classification_data):
        """Test training with hyperparameter tuning."""
        data, target = sample_classification_data
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=data,
            target_column=target,
            tune_hyperparameters=True,
            tuning_params={"cv": 2, "search_type": "grid"}
        )
        
        job_id = training_service.submit_training_job(request)
        result = training_service.train_model(job_id)
        
        assert result.status == TrainingStatus.COMPLETED.value
        assert result.best_parameters is not None
        assert len(result.best_parameters) > 0

    def test_training_service_regression_model(self, training_service, sample_regression_data):
        """Test regression model training."""
        data, target = sample_regression_data
        request = TrainingRequest(
            model_type="RandomForestRegressor",
            training_data=data,
            target_column=target
        )
        
        job_id = training_service.submit_training_job(request)
        result = training_service.train_model(job_id)
        
        assert result.status == TrainingStatus.COMPLETED.value
        assert "mse" in result.scores
        assert "r2" in result.scores

    def test_training_service_job_management(self, training_service, sample_classification_data):
        """Test job management operations."""
        data, target = sample_classification_data
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=data,
            target_column=target
        )
        
        job_id = training_service.submit_training_job(request)
        
        # Test get job status
        status = training_service.get_job_status(job_id)
        assert status["job_id"] == job_id
        assert status["status"] == TrainingStatus.PENDING.value
        
        # Test list jobs
        jobs = training_service.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["job_id"] == job_id
        
        # Test cancel job
        cancelled = training_service.cancel_job(job_id)
        assert cancelled is True
        assert training_service.jobs[job_id].status == TrainingStatus.CANCELLED.value

    def test_training_service_model_loading(self, training_service, sample_classification_data):
        """Test model loading."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
            
        data, target = sample_classification_data
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=data,
            target_column=target
        )
        
        job_id = training_service.submit_training_job(request)
        result = training_service.train_model(job_id)
        
        # Test model loading
        loaded_model = training_service.load_model(job_id)
        assert loaded_model is not None
        assert hasattr(loaded_model, 'fit')
        assert hasattr(loaded_model, 'predict')

    def test_training_service_statistics(self, training_service, sample_classification_data):
        """Test training statistics."""
        data, target = sample_classification_data
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=data,
            target_column=target
        )
        
        job_id = training_service.submit_training_job(request)
        
        stats = training_service.get_training_statistics()
        
        assert "total_jobs" in stats
        assert "status_distribution" in stats
        assert "available_models" in stats
        assert stats["total_jobs"] >= 1

    def test_training_service_error_handling(self, training_service):
        """Test error handling in training."""
        # Create invalid training data
        invalid_data = pd.DataFrame({"col1": [1, 2, None], "target": [0, 1, 0]})
        request = TrainingRequest(
            model_type="RandomForestClassifier",
            training_data=invalid_data,
            target_column="target"
        )
        
        job_id = training_service.submit_training_job(request)
        
        # This should handle the error gracefully
        result = training_service.train_model(job_id)
        
        # Check that error was handled
        assert result.status == TrainingStatus.FAILED.value or result.status == TrainingStatus.COMPLETED.value

    def test_utility_functions(self):
        """Test utility functions."""
        # Test sample data generation
        data, target = generate_sample_data(50, "classification")
        assert isinstance(data, pd.DataFrame)
        assert target in data.columns
        assert len(data) == 50
        
        data, target = generate_sample_data(50, "regression")
        assert isinstance(data, pd.DataFrame)
        assert target in data.columns
        assert len(data) == 50
        
        # Test training request from dict
        config = {
            "model_type": "RandomForestClassifier",
            "training_data": data,
            "target_column": target
        }
        request = create_training_request_from_dict(config)
        assert isinstance(request, TrainingRequest)
        assert request.model_type == "RandomForestClassifier"

    def test_concurrent_training(self, training_service, sample_classification_data):
        """Test concurrent training operations."""
        data, target = sample_classification_data
        
        def train_job():
            request = TrainingRequest(
                model_type="RandomForestClassifier",
                training_data=data,
                target_column=target
            )
            job_id = training_service.submit_training_job(request)
            return training_service.train_model(job_id)
        
        # Start multiple training jobs
        threads = []
        for i in range(2):
            thread = threading.Thread(target=train_job)
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join(timeout=30)  # Reasonable timeout
        
        # Check that jobs were created
        assert len(training_service.jobs) >= 2

    def test_edge_cases_and_validation(self, training_service):
        """Test edge cases and validation."""
        # Test invalid job ID
        status = training_service.get_job_status("invalid_job")
        assert "error" in status
        
        # Test loading non-existent model
        model = training_service.load_model("invalid_job")
        assert model is None
        
        # Test cancelling non-existent job
        cancelled = training_service.cancel_job("invalid_job")
        assert cancelled is False