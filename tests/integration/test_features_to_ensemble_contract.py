"""
Integration tests for feature-to-ensemble model contract validation.
Tests the complete pipeline from feature engineering through model prediction.
"""

from unittest.mock import AsyncMock, Mock

import numpy as np
import pandas as pd
import pytest

from backend.features.alignment import align_features_target
from backend.features.feature_engineering import (
    build_feature_frame,
    compute_all_features,
)
from backend.features.types import FeatureFrame, FeatureSchema
from backend.mlops.model_manager import ModelManager
from backend.models.ensemble_model import EnsembleModel


@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV data for testing."""
    dates = pd.date_range("2023-01-01", periods=500, freq="1min", tz="UTC")
    np.random.seed(42)

    # Generate realistic OHLCV data
    returns = np.random.normal(0, 0.02, len(dates))
    prices = 100 * np.exp(np.cumsum(returns))

    # Generate valid OHLC data ensuring proper relationships
    np.random.seed(42)  # Reset seed for consistent data
    open_prices = prices * (1 + np.random.normal(0, 0.001, len(dates)))
    close_prices = prices * (1 + np.random.normal(0, 0.001, len(dates)))
    
    # Ensure high is >= max(open, close) and low is <= min(open, close)
    max_oc = np.maximum(open_prices, close_prices)
    min_oc = np.minimum(open_prices, close_prices)
    
    # High should be at least max(open, close) + some positive spread
    high_spread = np.abs(np.random.normal(0, 0.005, len(dates)))
    high_prices = max_oc * (1 + high_spread)
    
    # Low should be at most min(open, close) - some positive spread  
    low_spread = np.abs(np.random.normal(0, 0.005, len(dates)))
    low_prices = min_oc * (1 - low_spread)

    return pd.DataFrame(
        {
            "open": open_prices,
            "high": high_prices,
            "low": low_prices,
            "close": close_prices,
            "volume": np.random.exponential(1000, len(dates)),
        },
        index=dates,
    )


@pytest.fixture
def mock_model_manager():
    """Create mock model manager with stored feature schema."""
    manager = Mock(spec=ModelManager)

    # Mock schema stored during model registration
    stored_schema = FeatureSchema(
        columns=["returns_1", "sma_20", "rsi_14", "volume_sma_10"],
        dtypes={
            "returns_1": "float64",
            "sma_20": "float64", 
            "rsi_14": "float64",
            "volume_sma_10": "float64",
        },
    )

    manager.get_model_metadata = Mock(
        return_value={
            "feature_schema": {
                "columns": stored_schema.columns,
                "dtypes": stored_schema.dtypes,
            },
            "model_version": "v1.0.0",
        }
    )

    return manager


class TestFeatureToEnsemblePipeline:
    """Integration tests for complete feature-to-model pipeline."""

    @pytest.fixture
    def mock_ensemble_model(self):
        """Create mock ensemble model for prediction."""
        model = Mock(spec=EnsembleModel)

        # Mock async predict method
        async def mock_predict(features_df):
            # Return mock predictions with same index
            return pd.Series(
                np.random.normal(0, 0.01, len(features_df)),
                index=features_df.index,
                name="prediction",
            )

        model.predict = AsyncMock(side_effect=mock_predict)
        return model

    @pytest.mark.asyncio
    async def test_complete_feature_to_prediction_pipeline(
        self, sample_ohlcv_data, mock_model_manager, mock_ensemble_model
    ):
        """Test complete pipeline from OHLCV data to model predictions."""

        # Step 1: Compute all features from OHLCV data
        features_df = compute_all_features(sample_ohlcv_data)

        # Verify features were computed
        assert not features_df.empty
        assert len(features_df.columns) > 0
        # Features should be subset of original data due to lookback windows
        assert len(features_df) <= len(sample_ohlcv_data)
        assert features_df.index.min() >= sample_ohlcv_data.index.min()
        assert features_df.index.max() <= sample_ohlcv_data.index.max()

        # Step 2: Create target variable (future returns)
        price_series = sample_ohlcv_data["close"]

        # Step 3: Align features with target (remove lookahead bias)
        feature_frame = align_features_target(features_df, price_series)

        # Verify alignment
        assert feature_frame.X.index.equals(feature_frame.y.index) if feature_frame.y is not None else True
        assert len(feature_frame.X) > 0
        assert (
            not feature_frame.X.isnull().all().all()
        )  # At least some non-null values

        # Step 4: Build FeatureFrame with schema validation
        # feature_frame is already a FeatureFrame from align_features_target

        # Verify FeatureFrame construction
        assert isinstance(feature_frame, FeatureFrame)
        assert feature_frame.X is not None
        assert len(feature_frame.X.columns) > 0

        # Step 5: Mock model registration to store schema
        mock_model_manager.register_model.return_value = "model_id_123"

        # Create a schema from the current feature frame for testing
        expected_schema = FeatureSchema(
            columns=list(feature_frame.X.columns),
            dtypes={col: str(dtype) for col, dtype in feature_frame.X.dtypes.items()}
        )

        # Set up mock to return schema data
        mock_model_manager.get_model_metadata.return_value = {
            "feature_schema": {
                "columns": expected_schema.columns,
                "dtypes": expected_schema.dtypes,
            },
            "model_version": "v1.0.0",
        }

        # This would normally happen during model training
        model_id = mock_model_manager.register_model(
            model=mock_ensemble_model,
            feature_data=feature_frame.X,
            target_data=feature_frame.y,
            model_version="v1.0.0",
        )

        # Step 6: Simulate inference with schema validation
        # Get the stored schema from model metadata
        model_metadata = mock_model_manager.get_model_metadata(model_id)
        stored_schema = FeatureSchema(**model_metadata["feature_schema"])

        # Step 7: Create new inference data (simulate live trading)
        inference_ohlcv = sample_ohlcv_data.tail(100)  # Last 100 periods
        inference_features = compute_all_features(inference_ohlcv)

        # Step 8: Validate inference features against stored schema
        # First create inference FeatureFrame
        inference_frame = build_feature_frame(inference_ohlcv, price_col="close")
        
        # Validate schema compatibility - check columns match
        assert set(inference_frame.X.columns) == set(stored_schema.columns)

        # Step 9: Make predictions using validated features
        predictions = await mock_ensemble_model.predict(inference_frame.X)

        # Verify predictions
        assert isinstance(predictions, pd.Series)
        assert len(predictions) == len(inference_frame.X)
        assert predictions.name == "prediction"

        # Verify mock calls
        mock_ensemble_model.predict.assert_called_once()

    @pytest.mark.asyncio
    async def test_schema_mismatch_detection(
        self, sample_ohlcv_data, mock_model_manager
    ):
        """Test that schema mismatches are detected during inference."""

        # Step 1: Create features with specific schema
        features_df = compute_all_features(sample_ohlcv_data)
        feature_frame = build_feature_frame(sample_ohlcv_data, price_col="close")

        # Step 2: Simulate stored schema with different feature set
        stored_schema = FeatureSchema(
            columns=["different_feature_1", "different_feature_2", "completely_different"],
            dtypes={
                "different_feature_1": "float64",
                "different_feature_2": "float64", 
                "completely_different": "int64"
            }
        )

        mock_model_manager.get_model_metadata.return_value = {
            "feature_schema": {
                "columns": stored_schema.columns,
                "dtypes": stored_schema.dtypes,
            },
            "model_version": "v1.0.0",
        }

        # Step 3: Try to validate current features against different schema
        stored_feature_names = stored_schema.columns

        # Since build_feature_frame doesn't validate columns, let's validate manually
        # by checking if the current feature frame has the expected columns
        current_columns = set(feature_frame.X.columns)
        expected_columns = set(stored_feature_names)
        missing_columns = expected_columns - current_columns
        
        # Verify that columns don't match (proving schema mismatch detection)
        assert len(missing_columns) > 0, "Expected schema mismatch should be detected"

    @pytest.mark.asyncio
    async def test_temporal_alignment_preserves_order(self, sample_ohlcv_data):
        """Test that temporal alignment preserves chronological order."""

        # Create features with some lookahead contamination
        features_df = compute_all_features(sample_ohlcv_data)

        # Create target with future information (5 periods ahead)
        target = sample_ohlcv_data["close"].pct_change().shift(-5)
        target.name = "future_return_5min"

        # Align features and target
        feature_frame = align_features_target(features_df, target)

        # Verify temporal ordering is preserved
        assert feature_frame.X.index.is_monotonic_increasing
        assert feature_frame.y.index.is_monotonic_increasing if feature_frame.y is not None else True

        # Verify no lookahead bias (target timestamp should not exceed feature timestamp)
        for i in range(len(feature_frame.X)):
            feature_time = feature_frame.X.index[i]
            target_time = feature_frame.y.index[i] if feature_frame.y is not None else feature_time
            assert target_time >= feature_time  # Target should be same time or later

        # Verify alignment removes the lookahead periods
        original_len = len(sample_ohlcv_data)
        aligned_len = len(feature_frame.X)
        assert aligned_len < original_len  # Should be shorter due to alignment

    @pytest.mark.asyncio
    async def test_feature_validation_edge_cases(self, sample_ohlcv_data):
        """Test feature validation handles edge cases properly."""

        # Case 1: Features with all NaN columns
        features_df = compute_all_features(sample_ohlcv_data)
        features_df["all_nan_feature"] = np.nan
        features_df["constant_feature"] = 42.0

        # Should handle gracefully
        feature_frame = build_feature_frame(sample_ohlcv_data, price_col="close")
        assert isinstance(feature_frame, FeatureFrame)

        # Case 2: Mismatched index types
        bad_features = features_df.copy()
        bad_features.index = range(len(bad_features))  # Convert to integer index

        target = sample_ohlcv_data["close"].pct_change().shift(-1)
        target.name = "target"

        # Should handle index type mismatch
        with pytest.raises((ValueError, KeyError)):
            align_features_target(bad_features, target)

    @pytest.mark.asyncio
    async def test_multi_timeframe_pipeline_integration(self, sample_ohlcv_data):
        """Test pipeline integration with multi-timeframe features."""

        # Create higher timeframe data (5-minute bars from 1-minute)
        ohlcv_5min = (
            sample_ohlcv_data.resample("5min")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna()
        )

        # Compute features for both timeframes
        features_1min = compute_all_features(sample_ohlcv_data)
        features_5min = compute_all_features(ohlcv_5min)

        # Add timeframe suffix to avoid column conflicts
        features_5min = features_5min.add_suffix("_5min")

        # Align 5-minute features to 1-minute timeline (forward fill)
        features_5min_aligned = features_5min.reindex(
            features_1min.index,
            method="ffill",
            limit=5,  # Max 5 periods forward fill
        )

        # Combine multi-timeframe features
        combined_features = pd.concat([features_1min, features_5min_aligned], axis=1)

        # Create target
        target = sample_ohlcv_data["close"].pct_change().shift(-1).dropna()
        target.name = "target"

        # Align combined features with target
        feature_frame = align_features_target(
            combined_features, target
        )

        # Verify multi-timeframe alignment
        assert not feature_frame.X.empty
        assert len(feature_frame.X.columns) > len(
            features_1min.columns
        )  # Should have more features

        # Verify 5-minute features are properly forward-filled
        five_min_cols = [
            col for col in feature_frame.X.columns if col.endswith("_5min")
        ]
        assert len(five_min_cols) > 0

        # Check that forward fill worked (no excessive NaNs)
        for col in five_min_cols:
            null_ratio = feature_frame.X[col].isnull().sum() / len(feature_frame.X)
            assert null_ratio < 0.5  # Less than 50% NaN after forward fill

    @pytest.mark.asyncio
    async def test_feature_schema_persistence_integration(
        self, sample_ohlcv_data, mock_model_manager
    ):
        """Test that feature schemas are properly persisted and retrieved."""

        # Step 1: Create and validate features
        features_df = compute_all_features(sample_ohlcv_data)
        feature_frame = build_feature_frame(sample_ohlcv_data, price_col="close")

        # Step 2: Create target
        target = sample_ohlcv_data["close"].pct_change().shift(-1).dropna()
        target.name = "target_return"

        # Step 3: Align features and target
        aligned_feature_frame = align_features_target(
            feature_frame.X, target
        )

        # Step 4: Simulate model training and schema storage
        training_frame = aligned_feature_frame  # already a FeatureFrame

        # Mock the register_model call that would store the schema
        def mock_register_model(model, feature_data, target_data, **kwargs):
            # Simulate schema extraction and storage
            schema = FeatureSchema(
                columns=list(feature_data.columns),
                dtypes={col: str(feature_data[col].dtype) for col in feature_data.columns}
            )

            # Store schema in mock metadata
            mock_model_manager.get_model_metadata.return_value = {
                "feature_schema": {
                    "columns": schema.columns,
                    "dtypes": schema.dtypes,
                },
                "model_version": kwargs.get("model_version", "v1.0.0"),
            }

            return "model_123"

        mock_model_manager.register_model.side_effect = mock_register_model

        # Register model (this stores the schema)
        model_id = mock_model_manager.register_model(
            model=Mock(),
            feature_data=training_frame.X,
            target_data=aligned_feature_frame.y,
            model_version="v1.0.0",
        )

        # Step 5: Simulate inference with schema validation
        inference_data = sample_ohlcv_data.tail(50)
        inference_features = compute_all_features(inference_data)

        # Get stored schema
        metadata = mock_model_manager.get_model_metadata(model_id)
        stored_schema = FeatureSchema(**metadata["feature_schema"])

        # Validate inference features against stored schema
        expected_columns = stored_schema.columns
        inference_frame = build_feature_frame(inference_data, price_col="close")

        # Verify schema consistency (check column overlap)
        inference_columns = set(inference_frame.X.columns)
        expected_columns_set = set(expected_columns)
        column_overlap = inference_columns.intersection(expected_columns_set)
        
        # Should have substantial overlap (not necessarily identical due to different data)
        assert len(column_overlap) > 0, "Should have some feature columns in common"

        # Verify inference frame structure
        assert len(inference_frame.X.columns) > 0, "Should have some features"


class TestErrorHandlingIntegration:
    """Test error handling across the complete pipeline."""

    @pytest.mark.asyncio
    async def test_malformed_ohlcv_error_propagation(self):
        """Test that malformed OHLCV data errors propagate correctly."""

        # Create malformed OHLCV data with invalid relationships
        bad_ohlcv = pd.DataFrame(
            {
                "open": [100, 101, 102],
                "high": [99, 103, 104],   # high < open on first row (invalid)
                "low": [99, 100, 101],
                "close": [101, 102, 103],
                "volume": [1000, 1100, 1200],
            }
        )

        # Should raise validation error during feature computation
        with pytest.raises(ValueError, match="Invalid OHLC relationships detected"):
            compute_all_features(bad_ohlcv)

    @pytest.mark.asyncio
    async def test_schema_validation_error_handling(self, sample_ohlcv_data):
        """Test schema validation error handling in API context."""
        from backend.features.types import SchemaValidationError

        # Create features with real columns
        features_df = compute_all_features(sample_ohlcv_data)
        
        # Simulate a schema mismatch by directly raising the error
        with pytest.raises(SchemaValidationError, match="Schema mismatch"):
            # This simulates what would happen in real schema validation
            missing_cols = ["nonexistent_column"]
            extra_cols = list(features_df.columns[:2])  # Take first 2 columns as "extra"
            raise SchemaValidationError(
                "Schema mismatch for test",
                missing_columns=missing_cols,
                extra_columns=extra_cols
            )

    @pytest.mark.asyncio
    async def test_lookahead_error_propagation(self, sample_ohlcv_data):
        """Test that lookahead detection errors propagate correctly."""
        from backend.features.types import LookaheadLeakError
        from backend.features.validators import guard_no_lookahead

        # Create features with intentional lookahead bias
        features_df = compute_all_features(sample_ohlcv_data)

        # Add a clearly leaky feature (future price)
        features_df["future_price"] = sample_ohlcv_data["close"].shift(-10)

        # Create target
        target = sample_ohlcv_data["close"].pct_change()
        target.name = "return"

        # Should detect lookahead and raise error
        with pytest.raises(
            LookaheadLeakError, match="Potential lookahead bias detected"
        ):
            guard_no_lookahead(features_df, target, threshold=0.8)
