"""
Comprehensive tests for backend/ml/pipeline.py

Tests the ML Pipeline Orchestrator including:
- PipelineStage and PipelineStatus enums
- PipelineConfig dataclass
- FeatureCacheEntry with expiration
- PipelineRunResult
- FeaturePipeline (feature registration, caching, validation)
- InferencePipeline (model selection, A/B testing, predictions)
- PipelineOrchestrator (full training and inference workflows)
- create_pipeline factory function
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from backend.ml.pipeline import (
    FeatureCacheEntry,
    FeaturePipeline,
    InferencePipeline,
    PipelineConfig,
    PipelineOrchestrator,
    PipelineRunResult,
    PipelineStage,
    PipelineStatus,
    create_pipeline,
)


# =============================================================================
# Test PipelineStage Enum
# =============================================================================

class TestPipelineStageEnum:
    """Tests for PipelineStage enum."""

    def test_all_stages_defined(self):
        """Test all pipeline stages are defined."""
        stages = [
            PipelineStage.DATA_INGESTION,
            PipelineStage.FEATURE_ENGINEERING,
            PipelineStage.FEATURE_VALIDATION,
            PipelineStage.MODEL_TRAINING,
            PipelineStage.MODEL_VALIDATION,
            PipelineStage.MODEL_DEPLOYMENT,
            PipelineStage.INFERENCE,
            PipelineStage.MONITORING,
        ]
        assert len(stages) == 8

    def test_stage_values(self):
        """Test stage string values."""
        assert PipelineStage.DATA_INGESTION.value == "data_ingestion"
        assert PipelineStage.FEATURE_ENGINEERING.value == "feature_engineering"
        assert PipelineStage.MODEL_TRAINING.value == "model_training"
        assert PipelineStage.INFERENCE.value == "inference"


# =============================================================================
# Test PipelineStatus Enum
# =============================================================================

class TestPipelineStatusEnum:
    """Tests for PipelineStatus enum."""

    def test_all_statuses_defined(self):
        """Test all pipeline statuses are defined."""
        statuses = [
            PipelineStatus.PENDING,
            PipelineStatus.RUNNING,
            PipelineStatus.COMPLETED,
            PipelineStatus.FAILED,
            PipelineStatus.CANCELLED,
        ]
        assert len(statuses) == 5

    def test_status_values(self):
        """Test status string values."""
        assert PipelineStatus.PENDING.value == "pending"
        assert PipelineStatus.RUNNING.value == "running"
        assert PipelineStatus.COMPLETED.value == "completed"
        assert PipelineStatus.FAILED.value == "failed"
        assert PipelineStatus.CANCELLED.value == "cancelled"


# =============================================================================
# Test PipelineConfig
# =============================================================================

class TestPipelineConfig:
    """Tests for PipelineConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = PipelineConfig()
        
        assert config.feature_cache_ttl_seconds == 3600
        assert config.feature_cache_dir == ".cache/features"
        assert config.validation_split == 0.2
        assert config.early_stopping_patience == 10
        assert config.max_training_time_seconds == 3600
        assert config.batch_size == 32
        assert config.inference_timeout_ms == 100.0
        assert config.drift_threshold == 0.1
        assert config.performance_window_days == 7
        assert config.enable_ab_testing is False
        assert config.challenger_traffic_pct == 0.1

    def test_custom_values(self):
        """Test custom configuration values."""
        config = PipelineConfig(
            feature_cache_ttl_seconds=7200,
            validation_split=0.3,
            batch_size=64,
            enable_ab_testing=True,
            challenger_traffic_pct=0.2,
        )
        
        assert config.feature_cache_ttl_seconds == 7200
        assert config.validation_split == 0.3
        assert config.batch_size == 64
        assert config.enable_ab_testing is True
        assert config.challenger_traffic_pct == 0.2


# =============================================================================
# Test FeatureCacheEntry
# =============================================================================

class TestFeatureCacheEntry:
    """Tests for FeatureCacheEntry dataclass."""

    def test_creation(self):
        """Test cache entry creation."""
        now = datetime.now(UTC)
        expires = now + timedelta(hours=1)
        features = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        
        entry = FeatureCacheEntry(
            cache_key="test_key",
            features=features,
            created_at=now,
            expires_at=expires,
        )
        
        assert entry.cache_key == "test_key"
        assert len(entry.features) == 2
        assert entry.created_at == now
        assert entry.expires_at == expires

    def test_is_expired_not_expired(self):
        """Test is_expired when entry is still valid."""
        entry = FeatureCacheEntry(
            cache_key="test",
            features=pd.DataFrame(),
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert entry.is_expired is False

    def test_is_expired_expired(self):
        """Test is_expired when entry has expired."""
        entry = FeatureCacheEntry(
            cache_key="test",
            features=pd.DataFrame(),
            created_at=datetime.now(UTC) - timedelta(hours=2),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert entry.is_expired is True

    def test_metadata_default(self):
        """Test default metadata is empty dict."""
        entry = FeatureCacheEntry(
            cache_key="test",
            features=pd.DataFrame(),
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert entry.metadata == {}

    def test_metadata_custom(self):
        """Test custom metadata."""
        entry = FeatureCacheEntry(
            cache_key="test",
            features=pd.DataFrame(),
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            metadata={"version": "1.0", "source": "test"},
        )
        assert entry.metadata["version"] == "1.0"
        assert entry.metadata["source"] == "test"


# =============================================================================
# Test PipelineRunResult
# =============================================================================

class TestPipelineRunResult:
    """Tests for PipelineRunResult dataclass."""

    def test_creation_minimal(self):
        """Test minimal run result."""
        result = PipelineRunResult(
            run_id="test_run_001",
            status=PipelineStatus.PENDING,
            stage=PipelineStage.DATA_INGESTION,
            started_at=datetime.now(UTC),
        )
        
        assert result.run_id == "test_run_001"
        assert result.status == PipelineStatus.PENDING
        assert result.stage == PipelineStage.DATA_INGESTION
        assert result.completed_at is None
        assert result.duration_seconds == 0.0
        assert result.output is None
        assert result.error is None
        assert result.metrics == {}

    def test_creation_full(self):
        """Test full run result."""
        now = datetime.now(UTC)
        result = PipelineRunResult(
            run_id="test_run_002",
            status=PipelineStatus.COMPLETED,
            stage=PipelineStage.MODEL_DEPLOYMENT,
            started_at=now,
            completed_at=now + timedelta(minutes=5),
            duration_seconds=300.0,
            output={"model": "trained"},
            error=None,
            metrics={"accuracy": 0.95, "f1": 0.92},
        )
        
        assert result.duration_seconds == 300.0
        assert result.output == {"model": "trained"}
        assert result.metrics["accuracy"] == 0.95

    def test_failed_run(self):
        """Test failed run result."""
        result = PipelineRunResult(
            run_id="test_run_003",
            status=PipelineStatus.FAILED,
            stage=PipelineStage.MODEL_TRAINING,
            started_at=datetime.now(UTC),
            error="Training diverged",
        )
        
        assert result.status == PipelineStatus.FAILED
        assert result.error == "Training diverged"


# =============================================================================
# Test FeaturePipeline
# =============================================================================

class TestFeaturePipeline:
    """Tests for FeaturePipeline class."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create a test config with temp cache dir."""
        return PipelineConfig(
            feature_cache_dir=str(tmp_path / "cache"),
            feature_cache_ttl_seconds=3600,
        )

    @pytest.fixture
    def pipeline(self, config):
        """Create a feature pipeline."""
        return FeaturePipeline(config)

    def test_init(self, pipeline, config):
        """Test pipeline initialization."""
        assert pipeline.config == config
        assert pipeline._cache == {}
        assert pipeline._feature_registry == {}

    def test_register_feature(self, pipeline):
        """Test feature registration."""
        def compute_sma(df):
            return df["close"].rolling(window=5).mean()
        
        pipeline.register_feature("sma_5", compute_sma)
        
        assert "sma_5" in pipeline._feature_registry
        assert pipeline._feature_registry["sma_5"]["compute"] == compute_sma
        assert pipeline._feature_registry["sma_5"]["dependencies"] == []

    def test_register_feature_with_dependencies(self, pipeline):
        """Test feature registration with dependencies."""
        def compute_derived(df):
            return df["sma_5"] * 2
        
        pipeline.register_feature("derived_feature", compute_derived, dependencies=["sma_5"])
        
        assert "derived_feature" in pipeline._feature_registry
        assert pipeline._feature_registry["derived_feature"]["dependencies"] == ["sma_5"]

    def test_compute_cache_key(self, pipeline):
        """Test cache key computation."""
        key1 = pipeline._compute_cache_key(
            symbols=["AAPL", "GOOG"],
            feature_names=["sma", "rsi"],
            start_time=datetime(2024, 1, 1, tzinfo=UTC),
            end_time=datetime(2024, 1, 31, tzinfo=UTC),
        )
        
        # Same inputs should produce same key
        key2 = pipeline._compute_cache_key(
            symbols=["GOOG", "AAPL"],  # Different order
            feature_names=["rsi", "sma"],  # Different order
            start_time=datetime(2024, 1, 1, tzinfo=UTC),
            end_time=datetime(2024, 1, 31, tzinfo=UTC),
        )
        
        assert key1 == key2  # Keys should match due to sorting

    def test_compute_cache_key_different_inputs(self, pipeline):
        """Test different inputs produce different cache keys."""
        key1 = pipeline._compute_cache_key(
            symbols=["AAPL"],
            feature_names=["sma"],
            start_time=datetime(2024, 1, 1, tzinfo=UTC),
            end_time=datetime(2024, 1, 31, tzinfo=UTC),
        )
        
        key2 = pipeline._compute_cache_key(
            symbols=["GOOG"],
            feature_names=["sma"],
            start_time=datetime(2024, 1, 1, tzinfo=UTC),
            end_time=datetime(2024, 1, 31, tzinfo=UTC),
        )
        
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_get_features_computes_registered(self, pipeline):
        """Test feature computation."""
        # Register a simple feature
        pipeline.register_feature("return", lambda df: df["close"].pct_change())
        
        data = pd.DataFrame({
            "close": [100.0, 101.0, 102.0, 101.0, 103.0],
            "symbol": ["AAPL"] * 5,
        })
        
        features = await pipeline.get_features(data, ["return"], use_cache=False)
        
        assert "return" in features.columns
        assert len(features) == 5

    @pytest.mark.asyncio
    async def test_get_features_caching(self, pipeline):
        """Test feature caching."""
        pipeline.register_feature("tracked_feature", lambda df: df["close"].pct_change())
        
        # Create data with datetime index
        dates = pd.date_range(start="2024-01-01", periods=3, freq="D", tz=UTC)
        data = pd.DataFrame({
            "close": [100.0, 101.0, 102.0],
            "symbol": ["AAPL"] * 3,
        }, index=dates)
        
        # First call should compute and cache
        result1 = await pipeline.get_features(data, ["tracked_feature"], use_cache=True)
        assert "tracked_feature" in result1.columns
        
        # Verify cache has entry
        assert len(pipeline._cache) > 0

    @pytest.mark.asyncio
    async def test_get_features_unregistered(self, pipeline):
        """Test handling of unregistered features logs warning."""
        dates = pd.date_range(start="2024-01-01", periods=3, freq="D", tz=UTC)
        data = pd.DataFrame({
            "close": [100.0, 101.0, 102.0],
            "symbol": ["AAPL"] * 3,
        }, index=dates)
        
        # Should handle gracefully - warning is logged for unregistered feature
        # The pipeline will fail to select the unregistered feature column,
        # so we expect a KeyError when no features are actually computed
        with pytest.raises(KeyError):
            await pipeline.get_features(data, ["nonexistent"], use_cache=False)

    @pytest.mark.asyncio
    async def test_get_features_computation_error(self, pipeline):
        """Test feature computation error handling."""
        def failing_compute(df):
            raise ValueError("Computation failed")
        
        pipeline.register_feature("failing_feature", failing_compute)
        
        data = pd.DataFrame({"close": [100.0, 101.0]})
        
        features = await pipeline.get_features(data, ["failing_feature"], use_cache=False)
        
        # Should have NaN for failed feature
        assert "failing_feature" in features.columns
        assert features["failing_feature"].isna().all()

    def test_sort_by_dependencies_no_deps(self, pipeline):
        """Test topological sort with no dependencies."""
        pipeline.register_feature("a", lambda df: df)
        pipeline.register_feature("b", lambda df: df)
        
        sorted_features = pipeline._sort_by_dependencies(["a", "b"])
        
        assert set(sorted_features) == {"a", "b"}

    def test_sort_by_dependencies_with_deps(self, pipeline):
        """Test topological sort with dependencies."""
        pipeline.register_feature("base", lambda df: df)
        pipeline.register_feature("derived", lambda df: df, dependencies=["base"])
        
        sorted_features = pipeline._sort_by_dependencies(["derived", "base"])
        
        # base should come before derived
        assert sorted_features.index("base") < sorted_features.index("derived")

    def test_validate_features_valid(self, pipeline):
        """Test feature validation with valid data."""
        features = pd.DataFrame({
            "price": [100.0, 101.0, 102.0],
            "volume": [1000, 2000, 3000],
        })
        
        schema = {
            "price": {"dtype": np.floating, "min": 0},
            "volume": {"dtype": np.integer, "min": 0},
        }
        
        is_valid, errors = pipeline.validate_features(features, schema)
        
        assert is_valid is True
        assert errors == []

    def test_validate_features_missing_column(self, pipeline):
        """Test feature validation with missing column."""
        features = pd.DataFrame({
            "price": [100.0, 101.0],
        })
        
        schema = {
            "price": {},
            "volume": {},
        }
        
        is_valid, errors = pipeline.validate_features(features, schema)
        
        assert is_valid is False
        assert "Missing required feature: volume" in errors

    def test_validate_features_below_min(self, pipeline):
        """Test feature validation with value below minimum."""
        features = pd.DataFrame({
            "price": [100.0, -1.0, 102.0],
        })
        
        schema = {
            "price": {"min": 0},
        }
        
        is_valid, errors = pipeline.validate_features(features, schema)
        
        assert is_valid is False
        assert any("below minimum" in e for e in errors)

    def test_validate_features_above_max(self, pipeline):
        """Test feature validation with value above maximum."""
        features = pd.DataFrame({
            "ratio": [0.5, 1.5, 0.8],
        })
        
        schema = {
            "ratio": {"max": 1.0},
        }
        
        is_valid, errors = pipeline.validate_features(features, schema)
        
        assert is_valid is False
        assert any("above maximum" in e for e in errors)

    def test_validate_features_null_values(self, pipeline):
        """Test feature validation with null values in non-nullable column."""
        features = pd.DataFrame({
            "price": [100.0, np.nan, 102.0],
        })
        
        schema = {
            "price": {"nullable": False},
        }
        
        is_valid, errors = pipeline.validate_features(features, schema)
        
        assert is_valid is False
        assert any("null values" in e for e in errors)

    def test_clear_cache_all(self, pipeline):
        """Test clearing all cache."""
        # Add some cache entries
        now = datetime.now(UTC)
        pipeline._cache["key1"] = FeatureCacheEntry(
            cache_key="key1",
            features=pd.DataFrame(),
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        
        pipeline.clear_cache(expired_only=False)
        
        assert len(pipeline._cache) == 0

    def test_clear_cache_expired_only(self, pipeline):
        """Test clearing only expired cache entries."""
        now = datetime.now(UTC)
        
        # Add expired entry
        pipeline._cache["expired"] = FeatureCacheEntry(
            cache_key="expired",
            features=pd.DataFrame(),
            created_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
        
        # Add valid entry
        pipeline._cache["valid"] = FeatureCacheEntry(
            cache_key="valid",
            features=pd.DataFrame(),
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        
        pipeline.clear_cache(expired_only=True)
        
        assert "expired" not in pipeline._cache
        assert "valid" in pipeline._cache


# =============================================================================
# Test InferencePipeline
# =============================================================================

class TestInferencePipeline:
    """Tests for InferencePipeline class."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config."""
        return PipelineConfig(
            feature_cache_dir=str(tmp_path / "cache"),
            inference_timeout_ms=100.0,
            enable_ab_testing=False,
        )

    @pytest.fixture
    def feature_pipeline(self, config):
        """Create feature pipeline."""
        return FeaturePipeline(config)

    @pytest.fixture
    def inference_pipeline(self, config, feature_pipeline):
        """Create inference pipeline."""
        return InferencePipeline(config, feature_pipeline)

    def test_init(self, inference_pipeline, config, feature_pipeline):
        """Test pipeline initialization."""
        assert inference_pipeline.config == config
        assert inference_pipeline.feature_pipeline == feature_pipeline
        assert inference_pipeline._champion_model is None
        assert inference_pipeline._challenger_model is None
        assert inference_pipeline._fallback_model is None
        assert inference_pipeline._request_counter == 0

    def test_set_champion_model(self, inference_pipeline):
        """Test setting champion model."""
        mock_model = MagicMock()
        
        inference_pipeline.set_champion_model(mock_model)
        
        assert inference_pipeline._champion_model == mock_model

    def test_set_challenger_model(self, inference_pipeline):
        """Test setting challenger model."""
        mock_model = MagicMock()
        
        inference_pipeline.set_challenger_model(mock_model)
        
        assert inference_pipeline._challenger_model == mock_model

    def test_set_fallback_model(self, inference_pipeline):
        """Test setting fallback model."""
        mock_model = MagicMock()
        
        inference_pipeline.set_fallback_model(mock_model)
        
        assert inference_pipeline._fallback_model == mock_model

    def test_select_model_no_ab_testing(self, inference_pipeline):
        """Test model selection without A/B testing."""
        mock_champion = MagicMock()
        inference_pipeline.set_champion_model(mock_champion)
        
        model, variant = inference_pipeline._select_model()
        
        assert model == mock_champion
        assert variant == "champion"

    def test_select_model_ab_testing_champion(self, config, feature_pipeline):
        """Test model selection with A/B testing routing to champion."""
        config.enable_ab_testing = True
        config.challenger_traffic_pct = 0.1
        
        pipeline = InferencePipeline(config, feature_pipeline)
        mock_champion = MagicMock()
        mock_challenger = MagicMock()
        
        pipeline.set_champion_model(mock_champion)
        pipeline.set_challenger_model(mock_challenger)
        
        # Most requests should go to champion
        champion_count = 0
        challenger_count = 0
        
        for _ in range(100):
            _, variant = pipeline._select_model()
            if variant == "champion":
                champion_count += 1
            else:
                challenger_count += 1
        
        # Roughly 90% should go to champion
        assert champion_count > challenger_count

    @pytest.mark.asyncio
    async def test_predict_with_sync_model(self, inference_pipeline):
        """Test prediction with synchronous model."""
        # Create a proper model class without predict_async
        class SyncModel:
            def predict(self, features):
                return np.array([0.75])
        
        mock_model = SyncModel()
        inference_pipeline.set_champion_model(mock_model)
        
        result = await inference_pipeline.predict({"feature1": 1.0, "feature2": 2.0})
        
        assert "prediction" in result
        assert "model_variant" in result
        assert result["model_variant"] == "champion"
        assert "latency_ms" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_predict_with_async_model(self, inference_pipeline):
        """Test prediction with asynchronous model."""
        mock_model = MagicMock()
        mock_model.predict_async = AsyncMock(return_value=np.array([0.85]))
        
        inference_pipeline.set_champion_model(mock_model)
        
        result = await inference_pipeline.predict({"feature1": 1.0})
        
        assert result["prediction"] is not None
        mock_model.predict_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_predict_with_dataframe(self, inference_pipeline):
        """Test prediction with DataFrame input."""
        class SyncModel:
            def predict(self, features):
                return np.array([0.5])
        
        inference_pipeline.set_champion_model(SyncModel())
        
        features_df = pd.DataFrame({"feature1": [1.0], "feature2": [2.0]})
        result = await inference_pipeline.predict(features_df)
        
        assert "prediction" in result

    @pytest.mark.asyncio
    async def test_predict_no_model_uses_fallback(self, inference_pipeline):
        """Test prediction falls back when no champion."""
        class FallbackModel:
            def predict(self, features):
                return np.array([0.5])
        
        inference_pipeline.set_fallback_model(FallbackModel())
        
        result = await inference_pipeline.predict({"feature1": 1.0})
        
        assert result["model_variant"] == "fallback"

    @pytest.mark.asyncio
    async def test_predict_no_model_raises(self, inference_pipeline):
        """Test prediction raises when no model available."""
        with pytest.raises(RuntimeError, match="No model available"):
            await inference_pipeline.predict({"feature1": 1.0})

    @pytest.mark.asyncio
    async def test_predict_timeout(self, inference_pipeline):
        """Test prediction timeout."""
        async def slow_predict(features):
            await asyncio.sleep(1.0)
            return np.array([0.5])
        
        mock_model = MagicMock()
        mock_model.predict_async = slow_predict
        
        inference_pipeline.set_champion_model(mock_model)
        inference_pipeline.config.inference_timeout_ms = 10.0  # 10ms timeout
        
        with pytest.raises(asyncio.TimeoutError):
            await inference_pipeline.predict({"feature1": 1.0})

    @pytest.mark.asyncio
    async def test_predict_batch(self, inference_pipeline):
        """Test batch predictions."""
        class BatchModel:
            def predict(self, features):
                return np.array([0.5, 0.6, 0.7])
        
        inference_pipeline.set_champion_model(BatchModel())
        
        features_batch = pd.DataFrame({
            "feature1": [1.0, 2.0, 3.0],
            "feature2": [4.0, 5.0, 6.0],
        })
        
        results = await inference_pipeline.predict_batch(features_batch)
        
        assert len(results) == 3
        for result in results:
            assert "prediction" in result
            assert "model_variant" in result

    @pytest.mark.asyncio
    async def test_predict_batch_no_model(self, inference_pipeline):
        """Test batch prediction raises when no model."""
        features_batch = pd.DataFrame({"feature1": [1.0, 2.0]})
        
        with pytest.raises(RuntimeError, match="No model available"):
            await inference_pipeline.predict_batch(features_batch)

    @pytest.mark.asyncio
    async def test_run_prediction_invalid_model(self, inference_pipeline):
        """Test _run_prediction with model lacking predict method."""
        invalid_model = object()  # No predict method
        
        with pytest.raises(ValueError, match="must have predict"):
            await inference_pipeline._run_prediction(invalid_model, pd.DataFrame())


# =============================================================================
# Test PipelineOrchestrator
# =============================================================================

class TestPipelineOrchestrator:
    """Tests for PipelineOrchestrator class."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create test config."""
        return PipelineConfig(
            feature_cache_dir=str(tmp_path / "cache"),
            validation_split=0.2,
        )

    @pytest.fixture
    def orchestrator(self, config):
        """Create pipeline orchestrator."""
        return PipelineOrchestrator(config)

    def test_init(self, orchestrator, config):
        """Test orchestrator initialization."""
        assert orchestrator.config == config
        assert isinstance(orchestrator.feature_pipeline, FeaturePipeline)
        assert isinstance(orchestrator.inference_pipeline, InferencePipeline)
        assert orchestrator._runs == []
        assert orchestrator._current_run is None

    def test_register_features(self, orchestrator):
        """Test registering multiple features."""
        features = {
            "sma": lambda df: df["close"].rolling(5).mean(),
            "rsi": lambda df: df["close"].pct_change(),
        }
        
        orchestrator.register_features(features)
        
        assert "sma" in orchestrator.feature_pipeline._feature_registry
        assert "rsi" in orchestrator.feature_pipeline._feature_registry

    @pytest.mark.asyncio
    async def test_run_training_pipeline_success(self, orchestrator):
        """Test successful training pipeline execution."""
        # Create mock model instance
        mock_model_instance = MagicMock()
        mock_model_instance.fit.return_value = None
        # Return array matching validation set size (20% of 20 = 4 samples)
        mock_model_instance.predict.return_value = np.array([1.0, 2.0, 3.0, 4.0])
        
        class MockModelClass:
            def __new__(cls, **kwargs):
                return mock_model_instance
        
        # Register features - need to return valid columns
        orchestrator.register_features({
            "feature1": lambda df: df["close"],
            "target": lambda df: df["close"].shift(-1).fillna(0),  # Fill NaN to avoid issues
        })
        
        # Create training data with datetime index (required by pipeline)
        # Need enough rows for train/val split: 20 rows, 80/20 = 16 train, 4 val
        dates = pd.date_range(start="2024-01-01", periods=20, freq="D", tz=UTC)
        training_data = pd.DataFrame({
            "close": np.random.randn(20).cumsum() + 100,
            "symbol": ["AAPL"] * 20,
        }, index=dates)
        
        result = await orchestrator.run_training_pipeline(
            training_data=training_data,
            feature_names=["feature1", "target"],
            model_class=MockModelClass,
            model_params={},
        )
        
        assert result.status == PipelineStatus.COMPLETED
        assert result.run_id is not None
        assert result.duration_seconds > 0
        assert "mse" in result.metrics or "mae" in result.metrics

    @pytest.mark.asyncio
    async def test_run_training_pipeline_failure(self, orchestrator):
        """Test training pipeline with failure."""
        # Create failing model
        class FailingModelClass:
            def __init__(self, **kwargs):
                raise ValueError("Training initialization failed")
        
        training_data = pd.DataFrame({
            "close": [100.0, 101.0, 102.0],
        })
        
        result = await orchestrator.run_training_pipeline(
            training_data=training_data,
            feature_names=["close"],
            model_class=FailingModelClass,
            model_params={},
        )
        
        assert result.status == PipelineStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_run_inference(self, orchestrator):
        """Test inference through orchestrator."""
        # Set up model with sync predict only
        class SyncModel:
            def predict(self, features):
                return np.array([0.75])
        
        orchestrator.inference_pipeline.set_champion_model(SyncModel())
        
        # Register features
        orchestrator.register_features({
            "feature1": lambda df: df["close"],
        })
        
        # Run inference with datetime index
        dates = pd.date_range(start="2024-01-01", periods=1, freq="D", tz=UTC)
        data = pd.DataFrame({"close": [100.0], "symbol": ["AAPL"]}, index=dates)
        result = await orchestrator.run_inference(data, ["feature1"])
        
        assert "prediction" in result

    @pytest.mark.asyncio
    async def test_run_inference_with_dict(self, orchestrator):
        """Test inference with pre-computed features as dict."""
        class SyncModel:
            def predict(self, features):
                return np.array([0.5])
        
        orchestrator.inference_pipeline.set_champion_model(SyncModel())
        
        result = await orchestrator.run_inference(
            data={"feature1": 1.0, "feature2": 2.0},
            feature_names=[],  # Pre-computed
        )
        
        assert "prediction" in result

    def test_get_pipeline_status_no_runs(self, orchestrator):
        """Test pipeline status with no runs."""
        status = orchestrator.get_pipeline_status()
        
        assert status["current_run"] is None
        assert status["recent_runs"] == []
        assert status["feature_cache_size"] == 0
        assert status["champion_model_loaded"] is False
        assert status["challenger_model_loaded"] is False

    def test_get_pipeline_status_with_model(self, orchestrator):
        """Test pipeline status with model loaded."""
        mock_model = MagicMock()
        orchestrator.inference_pipeline.set_champion_model(mock_model)
        
        status = orchestrator.get_pipeline_status()
        
        assert status["champion_model_loaded"] is True

    def test_get_pipeline_status_recent_runs(self, orchestrator):
        """Test pipeline status shows recent runs."""
        # Add some runs
        for i in range(3):
            orchestrator._runs.append(
                PipelineRunResult(
                    run_id=f"run_{i}",
                    status=PipelineStatus.COMPLETED,
                    stage=PipelineStage.MODEL_DEPLOYMENT,
                    started_at=datetime.now(UTC),
                    duration_seconds=float(i * 10),
                    metrics={"accuracy": 0.9 + i * 0.01},
                )
            )
        
        status = orchestrator.get_pipeline_status()
        
        assert len(status["recent_runs"]) == 3
        assert status["recent_runs"][-1]["run_id"] == "run_2"


# =============================================================================
# Test create_pipeline factory
# =============================================================================

class TestCreatePipeline:
    """Tests for create_pipeline factory function."""

    def test_create_default_pipeline(self):
        """Test creating pipeline with default config."""
        pipeline = create_pipeline()
        
        assert isinstance(pipeline, PipelineOrchestrator)
        assert pipeline.config.feature_cache_ttl_seconds == 3600
        assert pipeline.config.enable_ab_testing is False

    def test_create_pipeline_custom_ttl(self):
        """Test creating pipeline with custom TTL."""
        pipeline = create_pipeline(feature_cache_ttl=7200)
        
        assert pipeline.config.feature_cache_ttl_seconds == 7200

    def test_create_pipeline_ab_testing(self):
        """Test creating pipeline with A/B testing enabled."""
        pipeline = create_pipeline(enable_ab_testing=True)
        
        assert pipeline.config.enable_ab_testing is True


# =============================================================================
# Integration Tests
# =============================================================================

class TestPipelineIntegration:
    """Integration tests for the complete pipeline workflow."""

    @pytest.fixture
    def full_pipeline(self, tmp_path):
        """Create a fully configured pipeline."""
        config = PipelineConfig(
            feature_cache_dir=str(tmp_path / "cache"),
            validation_split=0.2,
            inference_timeout_ms=1000.0,
        )
        return PipelineOrchestrator(config)

    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self, full_pipeline):
        """Test complete training and inference workflow."""
        # 1. Register features
        full_pipeline.register_features({
            "returns": lambda df: df["close"].pct_change(),
            "volatility": lambda df: df["close"].rolling(5).std(),
            "target": lambda df: (df["close"].shift(-1) > df["close"]).astype(float),
        })
        
        # 2. Create training data with datetime index
        np.random.seed(42)
        dates = pd.date_range(start="2024-01-01", periods=100, freq="D", tz=UTC)
        training_data = pd.DataFrame({
            "close": np.random.randn(100).cumsum() + 100,
            "symbol": ["AAPL"] * 100,
        }, index=dates)
        
        # 3. Create simple model class for testing
        class SimpleModel:
            def __init__(self, **kwargs):
                self.mean_prediction = None
            
            def fit(self, X, y):
                self.mean_prediction = y.mean()
            
            def predict(self, X):
                return np.full(len(X), self.mean_prediction)
        
        # 4. Run training
        result = await full_pipeline.run_training_pipeline(
            training_data=training_data,
            feature_names=["returns", "volatility", "target"],
            model_class=SimpleModel,
            model_params={},
        )
        
        assert result.status == PipelineStatus.COMPLETED
        
        # 5. Verify model is deployed
        assert full_pipeline.inference_pipeline._champion_model is not None
        
        # 6. Run inference with datetime index
        dates = pd.date_range(start="2024-05-01", periods=5, freq="D", tz=UTC)
        test_data = pd.DataFrame({
            "close": [100.0, 101.0, 102.0, 101.5, 103.0],
            "symbol": ["AAPL"] * 5,
        }, index=dates)
        
        inference_result = await full_pipeline.run_inference(
            test_data, 
            ["returns", "volatility"],
        )
        
        assert "prediction" in inference_result
        assert inference_result["model_variant"] == "champion"

    def test_feature_caching_integration(self, full_pipeline):
        """Test feature caching works across operations."""
        # Register feature
        call_count = 0
        
        def counted_feature(df):
            nonlocal call_count
            call_count += 1
            return df["close"] * 2
        
        full_pipeline.feature_pipeline.register_feature("doubled", counted_feature)
        
        # Add to cache
        now = datetime.now(UTC)
        full_pipeline.feature_pipeline._cache["test_key"] = FeatureCacheEntry(
            cache_key="test_key",
            features=pd.DataFrame({"doubled": [200.0, 202.0]}),
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        
        # Verify cache entry exists
        assert len(full_pipeline.feature_pipeline._cache) == 1
        
        # Verify status reflects cache
        status = full_pipeline.get_pipeline_status()
        assert status["feature_cache_size"] == 1
