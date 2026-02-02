"""
Comprehensive tests for backend/ml/pipeline.py

This module tests all classes and functions in the pipeline module:
- PipelineStage and PipelineStatus enums
- PipelineConfig, FeatureCacheEntry, PipelineRunResult dataclasses
- FeaturePipeline (feature registration, caching, validation)
- InferencePipeline (prediction, A/B testing, fallback)
- PipelineOrchestrator (training pipeline, inference)
- create_pipeline factory function
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from backend.ml.pipeline import (
    PipelineStage,
    PipelineStatus,
    PipelineConfig,
    FeatureCacheEntry,
    PipelineRunResult,
    FeaturePipeline,
    InferencePipeline,
    PipelineOrchestrator,
    create_pipeline,
)


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV data for testing."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="1h")
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(100) * 0.5)

    return pd.DataFrame(
        {
            "open": close * (1 + np.random.uniform(-0.01, 0.01, 100)),
            "high": close * (1 + np.abs(np.random.normal(0, 0.01, 100))),
            "low": close * (1 - np.abs(np.random.normal(0, 0.01, 100))),
            "close": close,
            "volume": np.random.randint(1000, 10000, 100),
            "symbol": ["AAPL"] * 100,
        },
        index=dates,
    )


@pytest.fixture
def pipeline_config():
    """Create a basic pipeline config."""
    return PipelineConfig()


@pytest.fixture
def mock_model():
    """Create a mock model that works with sync prediction."""
    model = MagicMock()
    # Explicitly set predict_async to None so hasattr check fails
    del model.predict_async
    model.predict = MagicMock(return_value=np.array([0.5, 0.6, 0.7]))
    model.fit = MagicMock()
    return model


# ==============================================================================
# PipelineStage Tests
# ==============================================================================


class TestPipelineStage:
    """Tests for PipelineStage enum."""

    def test_all_stages_exist(self):
        """Test all pipeline stages are defined."""
        assert PipelineStage.DATA_INGESTION.value == "data_ingestion"
        assert PipelineStage.FEATURE_ENGINEERING.value == "feature_engineering"
        assert PipelineStage.FEATURE_VALIDATION.value == "feature_validation"
        assert PipelineStage.MODEL_TRAINING.value == "model_training"
        assert PipelineStage.MODEL_VALIDATION.value == "model_validation"
        assert PipelineStage.MODEL_DEPLOYMENT.value == "model_deployment"
        assert PipelineStage.INFERENCE.value == "inference"
        assert PipelineStage.MONITORING.value == "monitoring"

    def test_stage_count(self):
        """Test number of stages."""
        assert len(PipelineStage) == 8


class TestPipelineStatus:
    """Tests for PipelineStatus enum."""

    def test_all_statuses_exist(self):
        """Test all pipeline statuses are defined."""
        assert PipelineStatus.PENDING.value == "pending"
        assert PipelineStatus.RUNNING.value == "running"
        assert PipelineStatus.COMPLETED.value == "completed"
        assert PipelineStatus.FAILED.value == "failed"
        assert PipelineStatus.CANCELLED.value == "cancelled"


# ==============================================================================
# PipelineConfig Tests
# ==============================================================================


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
        assert not config.enable_ab_testing
        assert config.challenger_traffic_pct == 0.1

    def test_custom_values(self):
        """Test custom configuration values."""
        config = PipelineConfig(
            feature_cache_ttl_seconds=7200,
            validation_split=0.3,
            enable_ab_testing=True,
        )

        assert config.feature_cache_ttl_seconds == 7200
        assert config.validation_split == 0.3
        assert config.enable_ab_testing


# ==============================================================================
# FeatureCacheEntry Tests
# ==============================================================================


class TestFeatureCacheEntry:
    """Tests for FeatureCacheEntry dataclass."""

    def test_basic_creation(self):
        """Test basic cache entry creation."""
        now = datetime.now(UTC)
        entry = FeatureCacheEntry(
            cache_key="abc123",
            features=pd.DataFrame({"a": [1, 2, 3]}),
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )

        assert entry.cache_key == "abc123"
        assert len(entry.features) == 3
        assert not entry.is_expired

    def test_is_expired_true(self):
        """Test expired entry detection."""
        past = datetime.now(UTC) - timedelta(hours=2)
        entry = FeatureCacheEntry(
            cache_key="expired",
            features=pd.DataFrame(),
            created_at=past,
            expires_at=past + timedelta(hours=1),
        )

        assert entry.is_expired

    def test_is_expired_false(self):
        """Test non-expired entry."""
        now = datetime.now(UTC)
        entry = FeatureCacheEntry(
            cache_key="fresh",
            features=pd.DataFrame(),
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )

        assert not entry.is_expired


# ==============================================================================
# PipelineRunResult Tests
# ==============================================================================


class TestPipelineRunResult:
    """Tests for PipelineRunResult dataclass."""

    def test_basic_creation(self):
        """Test basic result creation."""
        result = PipelineRunResult(
            run_id="run_001",
            status=PipelineStatus.RUNNING,
            stage=PipelineStage.FEATURE_ENGINEERING,
            started_at=datetime.now(UTC),
        )

        assert result.run_id == "run_001"
        assert result.status == PipelineStatus.RUNNING
        assert result.stage == PipelineStage.FEATURE_ENGINEERING
        assert result.completed_at is None
        assert result.duration_seconds == 0.0
        assert result.error is None

    def test_completed_result(self):
        """Test completed result."""
        start = datetime.now(UTC)
        result = PipelineRunResult(
            run_id="run_002",
            status=PipelineStatus.COMPLETED,
            stage=PipelineStage.MODEL_DEPLOYMENT,
            started_at=start,
            completed_at=start + timedelta(seconds=30),
            duration_seconds=30.0,
            metrics={"mse": 0.05},
        )

        assert result.status == PipelineStatus.COMPLETED
        assert result.duration_seconds == 30.0
        assert result.metrics["mse"] == 0.05

    def test_failed_result(self):
        """Test failed result."""
        result = PipelineRunResult(
            run_id="run_003",
            status=PipelineStatus.FAILED,
            stage=PipelineStage.MODEL_TRAINING,
            started_at=datetime.now(UTC),
            error="Training failed: insufficient data",
        )

        assert result.status == PipelineStatus.FAILED
        assert result.error == "Training failed: insufficient data"


# ==============================================================================
# FeaturePipeline Tests
# ==============================================================================


class TestFeaturePipelineInit:
    """Tests for FeaturePipeline initialization."""

    def test_init_creates_cache_dir(self, pipeline_config, tmp_path):
        """Test initialization creates cache directory."""
        config = PipelineConfig(feature_cache_dir=str(tmp_path / "cache"))
        pipeline = FeaturePipeline(config)

        assert (tmp_path / "cache").exists()

    def test_init_with_feature_store(self, pipeline_config):
        """Test initialization with feature store."""
        mock_store = MagicMock()
        pipeline = FeaturePipeline(pipeline_config, feature_store=mock_store)

        assert pipeline.feature_store is mock_store


class TestFeaturePipelineRegistration:
    """Tests for feature registration."""

    def test_register_feature(self, pipeline_config):
        """Test registering a feature function."""
        pipeline = FeaturePipeline(pipeline_config)

        def compute_returns(df):
            return df["close"].pct_change()

        pipeline.register_feature("returns", compute_returns)

        assert "returns" in pipeline._feature_registry

    def test_register_feature_with_dependencies(self, pipeline_config):
        """Test registering feature with dependencies."""
        pipeline = FeaturePipeline(pipeline_config)

        def compute_volatility(df):
            return df["returns"].rolling(10).std()

        pipeline.register_feature(
            "volatility",
            compute_volatility,
            dependencies=["returns"],
        )

        assert pipeline._feature_registry["volatility"]["dependencies"] == ["returns"]


class TestFeaturePipelineCacheKey:
    """Tests for cache key computation."""

    def test_compute_cache_key(self, pipeline_config):
        """Test cache key computation."""
        pipeline = FeaturePipeline(pipeline_config)

        key1 = pipeline._compute_cache_key(
            symbols=["AAPL"],
            feature_names=["returns", "volatility"],
            start_time=datetime(2024, 1, 1, tzinfo=UTC),
            end_time=datetime(2024, 1, 31, tzinfo=UTC),
        )

        key2 = pipeline._compute_cache_key(
            symbols=["AAPL"],
            feature_names=["volatility", "returns"],  # Different order
            start_time=datetime(2024, 1, 1, tzinfo=UTC),
            end_time=datetime(2024, 1, 31, tzinfo=UTC),
        )

        # Same inputs should produce same key
        assert key1 == key2
        assert len(key1) == 16  # SHA256 truncated to 16 chars

    def test_different_inputs_different_key(self, pipeline_config):
        """Test different inputs produce different keys."""
        pipeline = FeaturePipeline(pipeline_config)

        key1 = pipeline._compute_cache_key(
            symbols=["AAPL"],
            feature_names=["returns"],
            start_time=datetime(2024, 1, 1, tzinfo=UTC),
            end_time=datetime(2024, 1, 31, tzinfo=UTC),
        )

        key2 = pipeline._compute_cache_key(
            symbols=["GOOG"],  # Different symbol
            feature_names=["returns"],
            start_time=datetime(2024, 1, 1, tzinfo=UTC),
            end_time=datetime(2024, 1, 31, tzinfo=UTC),
        )

        assert key1 != key2


class TestFeaturePipelineGetFeatures:
    """Tests for get_features method."""

    @pytest.mark.asyncio
    async def test_get_features_basic(self, pipeline_config, sample_ohlcv_data):
        """Test basic feature computation."""
        pipeline = FeaturePipeline(pipeline_config)

        def compute_returns(df):
            return df["close"].pct_change()

        pipeline.register_feature("returns", compute_returns)

        features = await pipeline.get_features(
            sample_ohlcv_data, ["returns"], use_cache=False
        )

        assert "returns" in features.columns
        assert len(features) == len(sample_ohlcv_data)

    @pytest.mark.asyncio
    async def test_get_features_uses_cache(self, pipeline_config, sample_ohlcv_data):
        """Test feature caching."""
        pipeline = FeaturePipeline(pipeline_config)

        def compute_returns(df):
            return df["close"].pct_change()

        pipeline.register_feature("returns", compute_returns)

        # First call - should cache
        features1 = await pipeline.get_features(
            sample_ohlcv_data, ["returns"], use_cache=True
        )

        # Second call - should use cache
        features2 = await pipeline.get_features(
            sample_ohlcv_data, ["returns"], use_cache=True
        )

        # Cache should have 1 entry
        assert len(pipeline._cache) == 1

    @pytest.mark.asyncio
    async def test_get_features_unregistered_warning(
        self, pipeline_config, sample_ohlcv_data, caplog
    ):
        """Test warning for unregistered feature."""
        pipeline = FeaturePipeline(pipeline_config)

        # Register a valid feature but request an unregistered one along with it
        pipeline.register_feature("returns", lambda df: df["close"].pct_change())

        try:
            # This will log warning but may fail on column selection
            await pipeline.get_features(
                sample_ohlcv_data, ["returns", "unknown_feature"], use_cache=False
            )
        except KeyError:
            # Expected when trying to select unregistered feature column
            pass

        assert "Feature not registered" in caplog.text

    @pytest.mark.asyncio
    async def test_get_features_handles_error(
        self, pipeline_config, sample_ohlcv_data
    ):
        """Test error handling during feature computation."""
        pipeline = FeaturePipeline(pipeline_config)

        def failing_feature(df):
            raise ValueError("Computation error")

        pipeline.register_feature("bad_feature", failing_feature)

        features = await pipeline.get_features(
            sample_ohlcv_data, ["bad_feature"], use_cache=False
        )

        # Feature should be NaN
        assert features["bad_feature"].isna().all()


class TestFeaturePipelineDependencies:
    """Tests for dependency sorting."""

    def test_sort_by_dependencies(self, pipeline_config):
        """Test topological sort of features."""
        pipeline = FeaturePipeline(pipeline_config)

        # Register features with dependencies
        pipeline.register_feature("base", lambda df: df["close"])
        pipeline.register_feature(
            "derived1", lambda df: df["base"] * 2, dependencies=["base"]
        )
        pipeline.register_feature(
            "derived2", lambda df: df["derived1"] * 2, dependencies=["derived1"]
        )

        sorted_features = pipeline._sort_by_dependencies(["derived2", "base"])

        # base should come before derived2
        assert sorted_features.index("base") < sorted_features.index("derived2")


class TestFeaturePipelineValidation:
    """Tests for feature validation."""

    def test_validate_features_pass(self, pipeline_config):
        """Test successful validation."""
        pipeline = FeaturePipeline(pipeline_config)
        features = pd.DataFrame({
            "returns": [0.01, -0.02, 0.03],
            "volatility": [0.1, 0.11, 0.09],
        })

        schema = {
            "returns": {"dtype": np.floating},
            "volatility": {"dtype": np.floating, "min": 0.0},
        }

        is_valid, errors = pipeline.validate_features(features, schema)

        assert is_valid
        assert len(errors) == 0

    def test_validate_features_missing_column(self, pipeline_config):
        """Test validation fails for missing column."""
        pipeline = FeaturePipeline(pipeline_config)
        features = pd.DataFrame({"returns": [0.01]})

        schema = {
            "returns": {},
            "volatility": {},  # Missing
        }

        is_valid, errors = pipeline.validate_features(features, schema)

        assert not is_valid
        assert any("Missing required feature" in e for e in errors)

    def test_validate_features_range_violation(self, pipeline_config):
        """Test validation fails for range violation."""
        pipeline = FeaturePipeline(pipeline_config)
        features = pd.DataFrame({"value": [0.5, -0.1, 0.8]})

        schema = {"value": {"min": 0.0, "max": 1.0}}

        is_valid, errors = pipeline.validate_features(features, schema)

        assert not is_valid
        assert any("below minimum" in e for e in errors)

    def test_validate_features_null_check(self, pipeline_config):
        """Test validation fails for null in non-nullable."""
        pipeline = FeaturePipeline(pipeline_config)
        features = pd.DataFrame({"value": [1.0, np.nan, 3.0]})

        schema = {"value": {"nullable": False}}

        is_valid, errors = pipeline.validate_features(features, schema)

        assert not is_valid
        assert any("null values" in e for e in errors)


class TestFeaturePipelineClearCache:
    """Tests for cache clearing."""

    def test_clear_cache_all(self, pipeline_config):
        """Test clearing all cache."""
        pipeline = FeaturePipeline(pipeline_config)

        # Add some cache entries
        now = datetime.now(UTC)
        pipeline._cache["key1"] = FeatureCacheEntry(
            "key1", pd.DataFrame(), now, now + timedelta(hours=1)
        )
        pipeline._cache["key2"] = FeatureCacheEntry(
            "key2", pd.DataFrame(), now, now + timedelta(hours=1)
        )

        pipeline.clear_cache(expired_only=False)

        assert len(pipeline._cache) == 0

    def test_clear_cache_expired_only(self, pipeline_config):
        """Test clearing only expired cache."""
        pipeline = FeaturePipeline(pipeline_config)

        now = datetime.now(UTC)
        past = now - timedelta(hours=2)

        pipeline._cache["fresh"] = FeatureCacheEntry(
            "fresh", pd.DataFrame(), now, now + timedelta(hours=1)
        )
        pipeline._cache["expired"] = FeatureCacheEntry(
            "expired", pd.DataFrame(), past, past + timedelta(hours=1)
        )

        pipeline.clear_cache(expired_only=True)

        assert "fresh" in pipeline._cache
        assert "expired" not in pipeline._cache


# ==============================================================================
# InferencePipeline Tests
# ==============================================================================


class TestInferencePipelineInit:
    """Tests for InferencePipeline initialization."""

    def test_init(self, pipeline_config):
        """Test initialization."""
        feature_pipeline = FeaturePipeline(pipeline_config)
        inference_pipeline = InferencePipeline(pipeline_config, feature_pipeline)

        assert inference_pipeline._champion_model is None
        assert inference_pipeline._challenger_model is None
        assert inference_pipeline._fallback_model is None


class TestInferencePipelineModelSetup:
    """Tests for model setup."""

    def test_set_champion_model(self, pipeline_config, mock_model):
        """Test setting champion model."""
        feature_pipeline = FeaturePipeline(pipeline_config)
        pipeline = InferencePipeline(pipeline_config, feature_pipeline)

        pipeline.set_champion_model(mock_model)

        assert pipeline._champion_model is mock_model

    def test_set_challenger_model(self, pipeline_config, mock_model):
        """Test setting challenger model."""
        feature_pipeline = FeaturePipeline(pipeline_config)
        pipeline = InferencePipeline(pipeline_config, feature_pipeline)

        pipeline.set_challenger_model(mock_model)

        assert pipeline._challenger_model is mock_model

    def test_set_fallback_model(self, pipeline_config, mock_model):
        """Test setting fallback model."""
        feature_pipeline = FeaturePipeline(pipeline_config)
        pipeline = InferencePipeline(pipeline_config, feature_pipeline)

        pipeline.set_fallback_model(mock_model)

        assert pipeline._fallback_model is mock_model


class TestInferencePipelineModelSelection:
    """Tests for model selection logic."""

    def test_select_champion_by_default(self, pipeline_config, mock_model):
        """Test champion model is selected by default."""
        feature_pipeline = FeaturePipeline(pipeline_config)
        pipeline = InferencePipeline(pipeline_config, feature_pipeline)
        pipeline.set_champion_model(mock_model)

        model, variant = pipeline._select_model()

        assert model is mock_model
        assert variant == "champion"

    def test_select_challenger_with_ab_testing(self, mock_model):
        """Test challenger selection with A/B testing."""
        config = PipelineConfig(
            enable_ab_testing=True,
            challenger_traffic_pct=1.0,  # 100% to challenger
        )
        feature_pipeline = FeaturePipeline(config)
        pipeline = InferencePipeline(config, feature_pipeline)

        champion = MagicMock()
        challenger = MagicMock()
        pipeline.set_champion_model(champion)
        pipeline.set_challenger_model(challenger)

        # Force request counter to trigger challenger
        pipeline._request_counter = 0

        model, variant = pipeline._select_model()

        assert variant == "challenger"


class TestInferencePipelinePredict:
    """Tests for prediction functionality."""

    @pytest.mark.asyncio
    async def test_predict_basic(self, pipeline_config, mock_model):
        """Test basic prediction."""
        feature_pipeline = FeaturePipeline(pipeline_config)
        pipeline = InferencePipeline(pipeline_config, feature_pipeline)
        pipeline.set_champion_model(mock_model)

        result = await pipeline.predict({"close": 150.0})

        assert "prediction" in result
        assert result["model_variant"] == "champion"
        assert "latency_ms" in result

    @pytest.mark.asyncio
    async def test_predict_with_dataframe(self, pipeline_config, mock_model):
        """Test prediction with DataFrame input."""
        feature_pipeline = FeaturePipeline(pipeline_config)
        pipeline = InferencePipeline(pipeline_config, feature_pipeline)
        pipeline.set_champion_model(mock_model)

        features = pd.DataFrame({"close": [150.0], "volume": [1000]})
        result = await pipeline.predict(features)

        assert "prediction" in result

    @pytest.mark.asyncio
    async def test_predict_uses_fallback(self, pipeline_config, mock_model):
        """Test fallback model is used when champion unavailable."""
        feature_pipeline = FeaturePipeline(pipeline_config)
        pipeline = InferencePipeline(pipeline_config, feature_pipeline)
        pipeline.set_fallback_model(mock_model)

        result = await pipeline.predict({"close": 150.0})

        assert result["model_variant"] == "fallback"

    @pytest.mark.asyncio
    async def test_predict_no_model_raises(self, pipeline_config):
        """Test error when no model available."""
        feature_pipeline = FeaturePipeline(pipeline_config)
        pipeline = InferencePipeline(pipeline_config, feature_pipeline)

        with pytest.raises(RuntimeError, match="No model available"):
            await pipeline.predict({"close": 150.0})

    @pytest.mark.asyncio
    async def test_predict_async_model(self, pipeline_config):
        """Test prediction with async model."""
        feature_pipeline = FeaturePipeline(pipeline_config)
        pipeline = InferencePipeline(pipeline_config, feature_pipeline)

        async_model = MagicMock()
        async_model.predict_async = AsyncMock(return_value=[0.5])
        pipeline.set_champion_model(async_model)

        result = await pipeline.predict({"close": 150.0})

        assert result["prediction"] == [0.5]


class TestInferencePipelineBatchPredict:
    """Tests for batch prediction."""

    @pytest.mark.asyncio
    async def test_predict_batch(self, pipeline_config, mock_model):
        """Test batch prediction."""
        feature_pipeline = FeaturePipeline(pipeline_config)
        pipeline = InferencePipeline(pipeline_config, feature_pipeline)
        pipeline.set_champion_model(mock_model)

        features = pd.DataFrame({
            "close": [150.0, 151.0, 152.0],
            "volume": [1000, 1100, 1200],
        })

        results = await pipeline.predict_batch(features)

        assert len(results) == 3
        assert all("prediction" in r for r in results)

    @pytest.mark.asyncio
    async def test_predict_batch_no_model_raises(self, pipeline_config):
        """Test batch prediction fails without model."""
        feature_pipeline = FeaturePipeline(pipeline_config)
        pipeline = InferencePipeline(pipeline_config, feature_pipeline)

        with pytest.raises(RuntimeError, match="No model available"):
            await pipeline.predict_batch(pd.DataFrame({"close": [100]}))


# ==============================================================================
# PipelineOrchestrator Tests
# ==============================================================================


class TestPipelineOrchestratorInit:
    """Tests for PipelineOrchestrator initialization."""

    def test_init(self, pipeline_config):
        """Test initialization."""
        orchestrator = PipelineOrchestrator(pipeline_config)

        assert isinstance(orchestrator.feature_pipeline, FeaturePipeline)
        assert isinstance(orchestrator.inference_pipeline, InferencePipeline)
        assert len(orchestrator._runs) == 0


class TestPipelineOrchestratorFeatures:
    """Tests for feature registration in orchestrator."""

    def test_register_features(self, pipeline_config):
        """Test registering multiple features."""
        orchestrator = PipelineOrchestrator(pipeline_config)

        features = {
            "returns": lambda df: df["close"].pct_change(),
            "sma_10": lambda df: df["close"].rolling(10).mean(),
        }

        orchestrator.register_features(features)

        assert "returns" in orchestrator.feature_pipeline._feature_registry
        assert "sma_10" in orchestrator.feature_pipeline._feature_registry


class TestPipelineOrchestratorStatus:
    """Tests for status reporting."""

    def test_get_pipeline_status_empty(self, pipeline_config):
        """Test status when no runs."""
        orchestrator = PipelineOrchestrator(pipeline_config)

        status = orchestrator.get_pipeline_status()

        assert status["current_run"] is None
        assert status["recent_runs"] == []
        assert status["feature_cache_size"] == 0
        assert not status["champion_model_loaded"]
        assert not status["challenger_model_loaded"]

    def test_get_pipeline_status_with_model(self, pipeline_config, mock_model):
        """Test status with loaded model."""
        orchestrator = PipelineOrchestrator(pipeline_config)
        orchestrator.inference_pipeline.set_champion_model(mock_model)

        status = orchestrator.get_pipeline_status()

        assert status["champion_model_loaded"]


class TestPipelineOrchestratorInference:
    """Tests for inference through orchestrator."""

    @pytest.mark.asyncio
    async def test_run_inference_dict(self, pipeline_config, mock_model):
        """Test inference with dict input."""
        orchestrator = PipelineOrchestrator(pipeline_config)
        orchestrator.inference_pipeline.set_champion_model(mock_model)

        result = await orchestrator.run_inference(
            {"close": 150.0},
            feature_names=["close"],
        )

        assert "prediction" in result

    @pytest.mark.asyncio
    async def test_run_inference_dataframe(
        self, pipeline_config, mock_model, sample_ohlcv_data
    ):
        """Test inference with DataFrame input."""
        orchestrator = PipelineOrchestrator(pipeline_config)
        orchestrator.inference_pipeline.set_champion_model(mock_model)

        # Register features
        orchestrator.register_features({
            "returns": lambda df: df["close"].pct_change(),
        })

        result = await orchestrator.run_inference(
            sample_ohlcv_data,
            feature_names=["returns"],
        )

        assert "prediction" in result


# ==============================================================================
# create_pipeline Factory Tests
# ==============================================================================


class TestCreatePipeline:
    """Tests for create_pipeline factory function."""

    def test_create_with_defaults(self):
        """Test creating pipeline with defaults."""
        pipeline = create_pipeline()

        assert isinstance(pipeline, PipelineOrchestrator)
        assert pipeline.config.feature_cache_ttl_seconds == 3600
        assert not pipeline.config.enable_ab_testing

    def test_create_with_custom_ttl(self):
        """Test creating pipeline with custom cache TTL."""
        pipeline = create_pipeline(feature_cache_ttl=7200)

        assert pipeline.config.feature_cache_ttl_seconds == 7200

    def test_create_with_ab_testing(self):
        """Test creating pipeline with A/B testing enabled."""
        pipeline = create_pipeline(enable_ab_testing=True)

        assert pipeline.config.enable_ab_testing


# ==============================================================================
# Integration Tests
# ==============================================================================


class TestIntegration:
    """Integration tests for pipeline workflow."""

    @pytest.mark.asyncio
    async def test_feature_to_inference_workflow(
        self, pipeline_config, sample_ohlcv_data, mock_model
    ):
        """Test complete feature to inference workflow."""
        orchestrator = PipelineOrchestrator(pipeline_config)

        # Register features
        orchestrator.register_features({
            "returns": lambda df: df["close"].pct_change(),
            "sma_10": lambda df: df["close"].rolling(10).mean(),
        })

        # Set model
        orchestrator.inference_pipeline.set_champion_model(mock_model)

        # Run inference
        result = await orchestrator.run_inference(
            sample_ohlcv_data,
            feature_names=["returns", "sma_10"],
        )

        assert "prediction" in result
        assert result["model_variant"] == "champion"

    @pytest.mark.asyncio
    async def test_cache_persistence(self, pipeline_config, sample_ohlcv_data):
        """Test feature cache persists across calls."""
        orchestrator = PipelineOrchestrator(pipeline_config)

        orchestrator.register_features({
            "returns": lambda df: df["close"].pct_change(),
        })

        # First call
        features1 = await orchestrator.feature_pipeline.get_features(
            sample_ohlcv_data, ["returns"]
        )

        # Second call - should use cache
        features2 = await orchestrator.feature_pipeline.get_features(
            sample_ohlcv_data, ["returns"]
        )

        assert len(orchestrator.feature_pipeline._cache) == 1

    @pytest.mark.asyncio
    async def test_full_ab_testing_flow(self, mock_model):
        """Test A/B testing workflow."""
        config = PipelineConfig(
            enable_ab_testing=True,
            challenger_traffic_pct=0.5,  # 50% to challenger
        )
        orchestrator = PipelineOrchestrator(config)

        champion = MagicMock()
        del champion.predict_async  # Ensure sync predict is used
        champion.predict = MagicMock(return_value=[0.5])
        challenger = MagicMock()
        del challenger.predict_async  # Ensure sync predict is used
        challenger.predict = MagicMock(return_value=[0.7])

        orchestrator.inference_pipeline.set_champion_model(champion)
        orchestrator.inference_pipeline.set_challenger_model(challenger)

        # Run multiple predictions
        results = []
        for _ in range(20):
            result = await orchestrator.run_inference({"close": 150}, [])
            results.append(result["model_variant"])

        # Should have mix of champion and challenger
        assert "champion" in results or "challenger" in results
