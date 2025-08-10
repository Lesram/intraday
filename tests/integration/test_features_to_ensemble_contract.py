"""
Integration tests for feature-to-ensemble model contract validation.
Tests the complete pipeline from feature engineering through model prediction.
"""

from unittest.mock import AsyncMock, Mock

import numpy as np
import pandas as pd
import pytest

from backend.features.alignment import align_features_target
from backend.features.feature_engineering import build_feature_frame, compute_all_features
from backend.features.types import FeatureFrame, FeatureSchema
from backend.mlops.model_manager import ModelManager
from backend.models.ensemble_model import EnsembleModel


class TestFeatureToEnsemblePipeline:
    """Integration tests for complete feature-to-model pipeline."""

    @pytest.fixture
    def sample_ohlcv_data(self):
        """Create sample OHLCV data for testing."""
        dates = pd.date_range('2023-01-01', periods=500, freq='1min', tz='UTC')
        np.random.seed(42)

        # Generate realistic OHLCV data
        returns = np.random.normal(0, 0.02, len(dates))
        prices = 100 * np.exp(np.cumsum(returns))

        return pd.DataFrame({
            'open': prices * (1 + np.random.normal(0, 0.001, len(dates))),
            'high': prices * (1 + np.abs(np.random.normal(0, 0.005, len(dates)))),
            'low': prices * (1 - np.abs(np.random.normal(0, 0.005, len(dates)))),
            'close': prices,
            'volume': np.random.exponential(1000, len(dates)),
        }, index=dates)

    @pytest.fixture
    def mock_model_manager(self):
        """Create mock model manager with stored feature schema."""
        manager = Mock(spec=ModelManager)

        # Mock schema stored during model registration
        stored_schema = FeatureSchema(
            features=[
                {"name": "returns_1", "dtype": "float64", "nullable": True},
                {"name": "sma_20", "dtype": "float64", "nullable": True},
                {"name": "rsi_14", "dtype": "float64", "nullable": True},
                {"name": "volume_sma_10", "dtype": "float64", "nullable": True},
            ],
            target_name="future_return_5min",
            created_at="2023-01-01T00:00:00Z"
        )

        manager.get_model_metadata = Mock(return_value={
            "feature_schema": stored_schema.model_dump(),
            "model_version": "v1.0.0"
        })

        return manager

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
                name="prediction"
            )

        model.predict = AsyncMock(side_effect=mock_predict)
        return model

    @pytest.mark.asyncio
    async def test_complete_feature_to_prediction_pipeline(self, sample_ohlcv_data, mock_model_manager, mock_ensemble_model):
        """Test complete pipeline from OHLCV data to model predictions."""

        # Step 1: Compute all features from OHLCV data
        features_df = await compute_all_features(sample_ohlcv_data)

        # Verify features were computed
        assert not features_df.empty
        assert len(features_df.columns) > 0
        assert features_df.index.equals(sample_ohlcv_data.index)

        # Step 2: Create target variable (future returns)
        target = sample_ohlcv_data['close'].pct_change().shift(-5).dropna()  # 5-period future return
        target.name = "future_return_5min"

        # Step 3: Align features with target (remove lookahead bias)
        aligned_features, aligned_target = align_features_target(features_df, target)

        # Verify alignment
        assert aligned_features.index.equals(aligned_target.index)
        assert len(aligned_features) > 0
        assert not aligned_features.isnull().all().all()  # At least some non-null values

        # Step 4: Build FeatureFrame with schema validation
        feature_frame = build_feature_frame(aligned_features, expected_columns=None)

        # Verify FeatureFrame construction
        assert isinstance(feature_frame, FeatureFrame)
        assert feature_frame.schema is not None
        assert len(feature_frame.schema.features) > 0

        # Step 5: Mock model registration to store schema
        mock_model_manager.register_model.return_value = "model_id_123"

        # This would normally happen during model training
        model_id = mock_model_manager.register_model(
            model=mock_ensemble_model,
            feature_data=feature_frame.data,
            target_data=aligned_target,
            model_version="v1.0.0"
        )

        # Step 6: Simulate inference with schema validation
        # Get the stored schema from model metadata
        model_metadata = mock_model_manager.get_model_metadata(model_id)
        stored_schema = FeatureSchema.model_validate(model_metadata["feature_schema"])

        # Step 7: Create new inference data (simulate live trading)
        inference_ohlcv = sample_ohlcv_data.tail(100)  # Last 100 periods
        inference_features = await compute_all_features(inference_ohlcv)

        # Step 8: Validate inference features against stored schema
        inference_frame = build_feature_frame(
            inference_features,
            expected_columns=[f["name"] for f in stored_schema.features]
        )

        # Verify schema compatibility
        assert inference_frame.schema.features == stored_schema.features

        # Step 9: Make predictions using validated features
        predictions = await mock_ensemble_model.predict(inference_frame.data)

        # Verify predictions
        assert isinstance(predictions, pd.Series)
        assert len(predictions) == len(inference_frame.data)
        assert predictions.name == "prediction"

        # Verify mock calls
        mock_ensemble_model.predict.assert_called_once()

    @pytest.mark.asyncio
    async def test_schema_mismatch_detection(self, sample_ohlcv_data, mock_model_manager):
        """Test that schema mismatches are detected during inference."""

        # Step 1: Create features with specific schema
        features_df = await compute_all_features(sample_ohlcv_data)
        feature_frame = build_feature_frame(features_df, expected_columns=None)

        # Step 2: Simulate stored schema with different feature set
        stored_schema = FeatureSchema(
            features=[
                {"name": "different_feature_1", "dtype": "float64", "nullable": True},
                {"name": "different_feature_2", "dtype": "float64", "nullable": True},
                {"name": "completely_different", "dtype": "int64", "nullable": False},
            ],
            target_name="future_return_5min",
            created_at="2023-01-01T00:00:00Z"
        )

        mock_model_manager.get_model_metadata.return_value = {
            "feature_schema": stored_schema.model_dump(),
            "model_version": "v1.0.0"
        }

        # Step 3: Try to validate current features against different schema
        stored_feature_names = [f["name"] for f in stored_schema.features]

        with pytest.raises(ValueError, match="Expected columns.*not found"):
            build_feature_frame(features_df, expected_columns=stored_feature_names)

    @pytest.mark.asyncio
    async def test_temporal_alignment_preserves_order(self, sample_ohlcv_data):
        """Test that temporal alignment preserves chronological order."""

        # Create features with some lookahead contamination
        features_df = await compute_all_features(sample_ohlcv_data)

        # Create target with future information (5 periods ahead)
        target = sample_ohlcv_data['close'].pct_change().shift(-5)
        target.name = "future_return_5min"

        # Align features and target
        aligned_features, aligned_target = align_features_target(features_df, target)

        # Verify temporal ordering is preserved
        assert aligned_features.index.is_monotonic_increasing
        assert aligned_target.index.is_monotonic_increasing

        # Verify no lookahead bias (target timestamp should not exceed feature timestamp)
        for i in range(len(aligned_features)):
            feature_time = aligned_features.index[i]
            target_time = aligned_target.index[i]
            assert target_time >= feature_time  # Target should be same time or later

        # Verify alignment removes the lookahead periods
        original_len = len(sample_ohlcv_data)
        aligned_len = len(aligned_features)
        assert aligned_len < original_len  # Should be shorter due to alignment

    @pytest.mark.asyncio
    async def test_feature_validation_edge_cases(self, sample_ohlcv_data):
        """Test feature validation handles edge cases properly."""

        # Case 1: Features with all NaN columns
        features_df = await compute_all_features(sample_ohlcv_data)
        features_df['all_nan_feature'] = np.nan
        features_df['constant_feature'] = 42.0

        # Should handle gracefully
        feature_frame = build_feature_frame(features_df, expected_columns=None)
        assert isinstance(feature_frame, FeatureFrame)

        # Case 2: Mismatched index types
        bad_features = features_df.copy()
        bad_features.index = range(len(bad_features))  # Convert to integer index

        target = sample_ohlcv_data['close'].pct_change().shift(-1)
        target.name = "target"

        # Should handle index type mismatch
        with pytest.raises((ValueError, KeyError)):
            align_features_target(bad_features, target)

    @pytest.mark.asyncio
    async def test_multi_timeframe_pipeline_integration(self, sample_ohlcv_data):
        """Test pipeline integration with multi-timeframe features."""

        # Create higher timeframe data (5-minute bars from 1-minute)
        ohlcv_5min = sample_ohlcv_data.resample('5min').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()

        # Compute features for both timeframes
        features_1min = await compute_all_features(sample_ohlcv_data)
        features_5min = await compute_all_features(ohlcv_5min)

        # Add timeframe suffix to avoid column conflicts
        features_5min = features_5min.add_suffix('_5min')

        # Align 5-minute features to 1-minute timeline (forward fill)
        features_5min_aligned = features_5min.reindex(
            features_1min.index,
            method='ffill',
            limit=5  # Max 5 periods forward fill
        )

        # Combine multi-timeframe features
        combined_features = pd.concat([features_1min, features_5min_aligned], axis=1)

        # Create target
        target = sample_ohlcv_data['close'].pct_change().shift(-1).dropna()
        target.name = "target"

        # Align combined features with target
        aligned_features, aligned_target = align_features_target(combined_features, target)

        # Verify multi-timeframe alignment
        assert not aligned_features.empty
        assert len(aligned_features.columns) > len(features_1min.columns)  # Should have more features

        # Verify 5-minute features are properly forward-filled
        five_min_cols = [col for col in aligned_features.columns if col.endswith('_5min')]
        assert len(five_min_cols) > 0

        # Check that forward fill worked (no excessive NaNs)
        for col in five_min_cols:
            null_ratio = aligned_features[col].isnull().sum() / len(aligned_features)
            assert null_ratio < 0.5  # Less than 50% NaN after forward fill

    @pytest.mark.asyncio
    async def test_feature_schema_persistence_integration(self, sample_ohlcv_data, mock_model_manager):
        """Test that feature schemas are properly persisted and retrieved."""

        # Step 1: Create and validate features
        features_df = await compute_all_features(sample_ohlcv_data)
        feature_frame = build_feature_frame(features_df, expected_columns=None)

        # Step 2: Create target
        target = sample_ohlcv_data['close'].pct_change().shift(-1).dropna()
        target.name = "target_return"

        # Step 3: Align features and target
        aligned_features, aligned_target = align_features_target(feature_frame.data, target)

        # Step 4: Simulate model training and schema storage
        training_frame = build_feature_frame(aligned_features, expected_columns=None)

        # Mock the register_model call that would store the schema
        def mock_register_model(model, feature_data, target_data, **kwargs):
            # Simulate schema extraction and storage
            schema = FeatureSchema(
                features=[
                    {"name": col, "dtype": str(feature_data[col].dtype), "nullable": True}
                    for col in feature_data.columns
                ],
                target_name=target_data.name,
                created_at="2023-01-01T00:00:00Z"
            )

            # Store schema in mock metadata
            mock_model_manager.get_model_metadata.return_value = {
                "feature_schema": schema.model_dump(),
                "model_version": kwargs.get("model_version", "v1.0.0")
            }

            return "model_123"

        mock_model_manager.register_model.side_effect = mock_register_model

        # Register model (this stores the schema)
        model_id = mock_model_manager.register_model(
            model=Mock(),
            feature_data=training_frame.data,
            target_data=aligned_target,
            model_version="v1.0.0"
        )

        # Step 5: Simulate inference with schema validation
        inference_data = sample_ohlcv_data.tail(50)
        inference_features = await compute_all_features(inference_data)

        # Get stored schema
        metadata = mock_model_manager.get_model_metadata(model_id)
        stored_schema = FeatureSchema.model_validate(metadata["feature_schema"])

        # Validate inference features against stored schema
        expected_columns = [f["name"] for f in stored_schema.features]
        inference_frame = build_feature_frame(inference_features, expected_columns=expected_columns)

        # Verify schema consistency
        assert inference_frame.schema.features == stored_schema.features
        assert len(inference_frame.data.columns) == len(stored_schema.features)

        # Verify all expected columns are present
        for expected_col in expected_columns:
            assert expected_col in inference_frame.data.columns


class TestErrorHandlingIntegration:
    """Test error handling across the complete pipeline."""

    @pytest.mark.asyncio
    async def test_malformed_ohlcv_error_propagation(self):
        """Test that malformed OHLCV data errors propagate correctly."""

        # Create malformed OHLCV data
        bad_ohlcv = pd.DataFrame({
            'open': [100, 101, np.nan],  # NaN in OHLCV
            'high': [102, 103, 104],
            'low': [99, 100, 101],
            'close': [101, 102, 103],
            'volume': [1000, 1100, 1200],
        })

        # Should raise validation error during feature computation
        with pytest.raises(ValueError, match="OHLCV validation failed"):
            await compute_all_features(bad_ohlcv)

    @pytest.mark.asyncio
    async def test_schema_validation_error_handling(self, sample_ohlcv_data):
        """Test schema validation error handling in API context."""
        from backend.features.types import SchemaValidationError

        # Create features
        features_df = await compute_all_features(sample_ohlcv_data)

        # Try to build with impossible expected columns
        with pytest.raises(SchemaValidationError, match="Schema validation failed"):
            build_feature_frame(features_df, expected_columns=["nonexistent_column"])

    @pytest.mark.asyncio
    async def test_lookahead_error_propagation(self, sample_ohlcv_data):
        """Test that lookahead detection errors propagate correctly."""
        from backend.features.types import LookaheadLeakError
        from backend.features.validators import guard_no_lookahead

        # Create features with intentional lookahead bias
        features_df = await compute_all_features(sample_ohlcv_data)

        # Add a clearly leaky feature (future price)
        features_df['future_price'] = sample_ohlcv_data['close'].shift(-10)

        # Create target
        target = sample_ohlcv_data['close'].pct_change()
        target.name = "return"

        # Should detect lookahead and raise error
        with pytest.raises(LookaheadLeakError, match="Potential lookahead bias detected"):
            guard_no_lookahead(features_df, target, threshold=0.8)
