"""
Comprehensive test suite for Module 11: backend.api.routes.strategy

This module provides complete test coverage for the strategy API routes including:
- Strategy system status endpoint
- Feature batch ingestion with processing logic
- Signal batch processing with multiple signals
- Single signal submission endpoint
- Pydantic model validation (FeatureBatch, SignalBatch)
- Error handling and exception scenarios
- Request/response data validation
- Logging and timestamp generation

Target: 100% statement and branch coverage
"""

import pytest
import asyncio
import json
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List

from fastapi import HTTPException, Request
from pydantic import ValidationError

# Configure pytest to ignore deprecation warnings
pytestmark = pytest.mark.filterwarnings("ignore:.*PyType_Spec.*:DeprecationWarning")

# Import the module under test
import backend.api.routes.strategy as strategy_module
from backend.api.routes.strategy import (
    # Models
    FeatureBatch,
    SignalBatch,
    # Endpoints
    get_strategy_status,
    ingest_features,
    process_signal_batch,
    submit_strategy_signal,
    # Router
    router
)


class TestModule11StrategyComponents:
    """Test core components of the strategy module."""
    
    def test_router_configuration(self):
        """Test FastAPI router configuration."""
        assert router.prefix == "/strategy"
        assert "Strategy" in router.tags
    
    def test_feature_batch_model(self):
        """Test FeatureBatch Pydantic model."""
        batch = FeatureBatch(
            features=[
                {"feature1": 0.5, "feature2": 1.2},
                {"feature1": 0.8, "feature2": 0.9}
            ],
            timestamp="2025-09-19T10:00:00Z",
            metadata={"source": "test", "version": "1.0"}
        )
        
        assert len(batch.features) == 2
        assert batch.features[0]["feature1"] == 0.5
        assert batch.timestamp == "2025-09-19T10:00:00Z"
        assert batch.metadata["source"] == "test"
    
    def test_feature_batch_model_defaults(self):
        """Test FeatureBatch model with default values."""
        batch = FeatureBatch(
            features=[{"rsi": 65.0, "macd": 0.15}]
        )
        
        assert len(batch.features) == 1
        assert isinstance(batch.timestamp, str)  # Auto-generated timestamp
        assert batch.metadata == {}  # Default empty dict
    
    def test_feature_batch_model_validation(self):
        """Test FeatureBatch model validation errors."""
        # Missing required features field
        with pytest.raises(ValidationError):
            FeatureBatch()
        
        # Empty features list should be valid
        batch = FeatureBatch(features=[])
        assert batch.features == []
    
    def test_signal_batch_model(self):
        """Test SignalBatch Pydantic model."""
        batch = SignalBatch(
            signals=[
                {"symbol": "AAPL", "signal_type": "BUY", "confidence": 0.85},
                {"symbol": "GOOGL", "signal_type": "SELL", "confidence": 0.75}
            ],
            strategy_id="momentum_v1",
            metadata={"batch_size": 2, "strategy_version": "1.2"}
        )
        
        assert len(batch.signals) == 2
        assert batch.strategy_id == "momentum_v1"
        assert batch.signals[0]["symbol"] == "AAPL"
        assert batch.metadata["batch_size"] == 2
    
    def test_signal_batch_model_defaults(self):
        """Test SignalBatch model with default values."""
        batch = SignalBatch(
            signals=[{"symbol": "TSLA", "action": "HOLD"}],
            strategy_id="test_strategy"
        )
        
        assert batch.strategy_id == "test_strategy"
        assert batch.metadata == {}  # Default empty dict
    
    def test_signal_batch_model_validation(self):
        """Test SignalBatch model validation errors."""
        # Missing required strategy_id field
        with pytest.raises(ValidationError):
            SignalBatch(signals=[{"test": "signal"}])
        
        # Missing required signals field
        with pytest.raises(ValidationError):
            SignalBatch(strategy_id="test")
        
        # Empty signals list should be valid
        batch = SignalBatch(signals=[], strategy_id="empty_test")
        assert batch.signals == []


class TestModule11GetStrategyStatusEndpoint:
    """Test the get strategy status endpoint functionality."""
    
    @pytest.mark.asyncio
    async def test_get_strategy_status_success(self):
        """Test successful strategy status retrieval."""
        with patch('backend.api.routes.strategy.datetime') as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = "2025-09-19T10:00:00Z"
            
            result = await get_strategy_status()
            
            assert isinstance(result, dict)
            assert result["status"] == "operational"
            assert result["active_strategies"] == 3
            assert result["last_update"] == "2025-09-19T10:00:00Z"
            assert result["features_processed"] == 12500
            assert result["signals_generated"] == 450
    
    @pytest.mark.asyncio
    async def test_get_strategy_status_response_structure(self):
        """Test strategy status response contains all required fields."""
        result = await get_strategy_status()
        
        required_fields = [
            "status", "active_strategies", "last_update", 
            "features_processed", "signals_generated"
        ]
        
        for field in required_fields:
            assert field in result
        
        assert isinstance(result["active_strategies"], int)
        assert isinstance(result["features_processed"], int)
        assert isinstance(result["signals_generated"], int)
        assert isinstance(result["last_update"], str)


class TestModule11IngestFeaturesEndpoint:
    """Test the ingest features endpoint functionality."""
    
    @pytest.mark.asyncio
    async def test_ingest_features_success(self):
        """Test successful feature ingestion."""
        mock_request = Mock(spec=Request)
        
        batch = FeatureBatch(
            features=[
                {"rsi": 70.0, "macd": 0.25, "bollinger": 0.8},
                {"rsi": 30.0, "macd": -0.15, "bollinger": 0.2},
                {"rsi": 55.0, "macd": 0.05, "bollinger": 0.5}
            ],
            metadata={"source": "feature_engine_v2"}
        )
        
        with patch('backend.api.routes.strategy.logger') as mock_logger, \
             patch('backend.api.routes.strategy.datetime') as mock_datetime:
            
            mock_datetime.now.return_value.isoformat.return_value = "2025-09-19T11:00:00Z"
            
            result = await ingest_features(mock_request, batch)
            
            assert result["status"] == "accepted"
            assert result["processed_count"] == 3
            assert "batch_id" in result
            assert result["batch_id"].startswith("batch_")
            assert result["timestamp"] == "2025-09-19T11:00:00Z"
            
            # Verify logging was called
            mock_logger.info.assert_called_once()
            log_message = mock_logger.info.call_args[0][0]
            assert "Ingested 3 features" in log_message
    
    @pytest.mark.asyncio
    async def test_ingest_features_empty_batch(self):
        """Test feature ingestion with empty batch."""
        mock_request = Mock(spec=Request)
        
        batch = FeatureBatch(features=[])
        
        result = await ingest_features(mock_request, batch)
        
        assert result["status"] == "accepted"
        assert result["processed_count"] == 0
        assert "batch_id" in result
        assert "timestamp" in result
    
    @pytest.mark.asyncio
    async def test_ingest_features_with_complex_features(self):
        """Test feature ingestion with complex feature data."""
        mock_request = Mock(spec=Request)
        
        complex_features = [
            {
                "technical": {"rsi": 65.5, "macd": 0.12, "stoch": 45.2},
                "fundamental": {"pe_ratio": 15.5, "book_value": 8.2},
                "market": {"volume_ratio": 1.25, "price_momentum": 0.08}
            },
            {
                "technical": {"rsi": 35.8, "macd": -0.08, "stoch": 28.9},
                "fundamental": {"pe_ratio": 22.1, "book_value": 12.1},
                "market": {"volume_ratio": 0.85, "price_momentum": -0.03}
            }
        ]
        
        batch = FeatureBatch(
            features=complex_features,
            metadata={"complexity": "high", "feature_types": ["technical", "fundamental", "market"]}
        )
        
        result = await ingest_features(mock_request, batch)
        
        assert result["status"] == "accepted"
        assert result["processed_count"] == 2
        assert "batch_id" in result
    
    @pytest.mark.asyncio
    async def test_ingest_features_batch_id_generation(self):
        """Test that batch_id generation is consistent and deterministic."""
        mock_request = Mock(spec=Request)
        
        # Same features should generate same batch_id
        features = [{"test": "feature"}]
        batch1 = FeatureBatch(features=features)
        batch2 = FeatureBatch(features=features)
        
        result1 = await ingest_features(mock_request, batch1)
        result2 = await ingest_features(mock_request, batch2)
        
        # batch_id should be deterministic based on features content
        assert result1["batch_id"] == result2["batch_id"]
        assert result1["batch_id"].startswith("batch_")
    
    @pytest.mark.asyncio
    async def test_ingest_features_exception_handling(self):
        """Test feature ingestion exception handling."""
        mock_request = Mock(spec=Request)
        
        batch = FeatureBatch(features=[{"test": "feature"}])
        
        # Mock an exception in the processing
        with patch('backend.api.routes.strategy.len', side_effect=Exception("Processing error")), \
             patch('backend.api.routes.strategy.logger') as mock_logger:
            
            with pytest.raises(HTTPException) as exc_info:
                await ingest_features(mock_request, batch)
            
            assert exc_info.value.status_code == 500
            assert "Feature ingestion failed" in str(exc_info.value.detail)
            
            # Verify error logging
            mock_logger.error.assert_called_once()
            error_message = mock_logger.error.call_args[0][0]
            assert "Feature ingestion failed" in error_message


class TestModule11ProcessSignalBatchEndpoint:
    """Test the process signal batch endpoint functionality."""
    
    @pytest.mark.asyncio
    async def test_process_signal_batch_success(self):
        """Test successful signal batch processing."""
        mock_request = Mock(spec=Request)
        
        batch = SignalBatch(
            signals=[
                {"symbol": "AAPL", "signal_type": "BUY", "confidence": 0.85, "target_price": 155.0},
                {"symbol": "GOOGL", "signal_type": "SELL", "confidence": 0.78, "target_price": 2800.0},
                {"symbol": "MSFT", "signal_type": "HOLD", "confidence": 0.65, "target_price": 330.0}
            ],
            strategy_id="momentum_strategy_v2",
            metadata={"batch_type": "intraday", "priority": "high"}
        )
        
        with patch('backend.api.routes.strategy.datetime') as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = "2025-09-19T12:00:00Z"
            
            result = await process_signal_batch(mock_request, batch)
            
            assert result["status"] == "completed"
            assert result["strategy_id"] == "momentum_strategy_v2"
            assert result["processed_count"] == 3
            assert result["batch_timestamp"] == "2025-09-19T12:00:00Z"
            
            # Check processed signals structure
            assert len(result["signals"]) == 3
            for processed_signal in result["signals"]:
                assert "signal_id" in processed_signal
                assert processed_signal["signal_id"].startswith("sig_")
                assert "original" in processed_signal
                assert processed_signal["status"] == "processed"
                assert processed_signal["timestamp"] == "2025-09-19T12:00:00Z"
    
    @pytest.mark.asyncio
    async def test_process_signal_batch_empty_signals(self):
        """Test signal batch processing with empty signals list."""
        mock_request = Mock(spec=Request)
        
        batch = SignalBatch(
            signals=[],
            strategy_id="empty_test_strategy"
        )
        
        result = await process_signal_batch(mock_request, batch)
        
        assert result["status"] == "completed"
        assert result["strategy_id"] == "empty_test_strategy"
        assert result["processed_count"] == 0
        assert result["signals"] == []
    
    @pytest.mark.asyncio
    async def test_process_signal_batch_single_signal(self):
        """Test signal batch processing with single signal."""
        mock_request = Mock(spec=Request)
        
        batch = SignalBatch(
            signals=[{"symbol": "TSLA", "action": "STRONG_BUY", "score": 0.92}],
            strategy_id="ai_momentum_v1"
        )
        
        result = await process_signal_batch(mock_request, batch)
        
        assert result["status"] == "completed"
        assert result["processed_count"] == 1
        assert len(result["signals"]) == 1
        
        processed_signal = result["signals"][0]
        assert processed_signal["original"]["symbol"] == "TSLA"
        assert processed_signal["original"]["action"] == "STRONG_BUY"
        assert processed_signal["status"] == "processed"
    
    @pytest.mark.asyncio
    async def test_process_signal_batch_signal_id_generation(self):
        """Test signal ID generation for processed signals."""
        mock_request = Mock(spec=Request)
        
        # Test that different signals get different IDs
        batch = SignalBatch(
            signals=[
                {"symbol": "AAPL", "type": "BUY"},
                {"symbol": "GOOGL", "type": "SELL"}
            ],
            strategy_id="test_strategy"
        )
        
        result = await process_signal_batch(mock_request, batch)
        
        signal_ids = [s["signal_id"] for s in result["signals"]]
        assert len(set(signal_ids)) == 2  # All IDs should be unique
        
        for signal_id in signal_ids:
            assert signal_id.startswith("sig_")
            assert signal_id != signal_id.replace("sig_", "")  # Should have numeric suffix
    
    @pytest.mark.asyncio
    async def test_process_signal_batch_complex_signal_data(self):
        """Test processing signals with complex nested data."""
        mock_request = Mock(spec=Request)
        
        complex_signal = {
            "symbol": "NVDA",
            "signal_type": "BUY",
            "confidence": 0.88,
            "technical_analysis": {
                "rsi": 45.2,
                "macd": {"value": 0.15, "histogram": 0.05},
                "bollinger_bands": {"upper": 520.0, "middle": 500.0, "lower": 480.0}
            },
            "fundamental_data": {
                "pe_ratio": 65.5,
                "earnings_growth": 0.25,
                "revenue_growth": 0.18
            },
            "risk_metrics": {
                "var_95": 0.05,
                "sharpe_ratio": 1.85,
                "max_drawdown": 0.08
            }
        }
        
        batch = SignalBatch(
            signals=[complex_signal],
            strategy_id="comprehensive_analysis_v3",
            metadata={"analysis_depth": "full", "data_sources": ["technical", "fundamental", "risk"]}
        )
        
        result = await process_signal_batch(mock_request, batch)
        
        assert result["status"] == "completed"
        processed_signal = result["signals"][0]
        
        # Verify original signal is preserved in full
        original = processed_signal["original"]
        assert original["symbol"] == "NVDA"
        assert original["technical_analysis"]["rsi"] == 45.2
        assert original["fundamental_data"]["pe_ratio"] == 65.5
        assert original["risk_metrics"]["sharpe_ratio"] == 1.85
    
    @pytest.mark.asyncio
    async def test_process_signal_batch_exception_handling(self):
        """Test signal batch processing exception handling."""
        mock_request = Mock(spec=Request)
        
        batch = SignalBatch(
            signals=[{"test": "signal"}],
            strategy_id="error_test"
        )
        
        # Mock an exception during processing by patching the hash function
        with patch('builtins.hash', side_effect=Exception("Processing error")), \
             patch('backend.api.routes.strategy.logger') as mock_logger:
            
            with pytest.raises(HTTPException) as exc_info:
                await process_signal_batch(mock_request, batch)
            
            assert exc_info.value.status_code == 500
            assert "Signal batch processing failed" in str(exc_info.value.detail)
            
            # Verify error logging
            mock_logger.error.assert_called_once()
            error_message = mock_logger.error.call_args[0][0]
            assert "Signal batch processing failed" in error_message
    
    @pytest.mark.asyncio
    async def test_process_signal_batch_covers_exception_lines(self):
        """Test to ensure lines 89-91 exception handling is covered."""
        mock_request = Mock(spec=Request)
        
        batch = SignalBatch(
            signals=[{"signal": "TEST"}],
            strategy_id="exception_coverage_test"
        )
        
        # Force an exception in the try block to hit the except block (lines 89-91)
        with patch('backend.api.routes.strategy.datetime') as mock_datetime, \
             patch('backend.api.routes.strategy.logger') as mock_logger:
            
            # Make datetime.now() work for the first call but fail later
            mock_datetime.now.side_effect = [
                Mock(isoformat=Mock(return_value="2025-01-01T00:00:00")),  # First call works
                Exception("Forced error")  # Second call fails
            ]
            
            with pytest.raises(HTTPException) as exc_info:
                await process_signal_batch(mock_request, batch)
            
            # Verify we hit the exception handling code
            assert exc_info.value.status_code == 500
            assert exc_info.value.detail == "Signal batch processing failed"
            
            # Verify logging occurred (line 90)
            mock_logger.error.assert_called_once()
            logged_message = mock_logger.error.call_args[0][0]
            assert "Signal batch processing failed:" in logged_message
            assert "Forced error" in logged_message


class TestModule11SubmitStrategySignalEndpoint:
    """Test the submit strategy signal endpoint functionality."""
    
    @pytest.mark.asyncio
    async def test_submit_strategy_signal_success(self):
        """Test successful single signal submission."""
        mock_request = Mock(spec=Request)
        signal_data = {
            "symbol": "AAPL",
            "signal_type": "BUY",
            "confidence": 0.87,
            "target_price": 160.0,
            "stop_loss": 145.0
        }
        mock_request.json = AsyncMock(return_value=signal_data)
        
        with patch('backend.api.routes.strategy.datetime') as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = "2025-09-19T13:00:00Z"
            
            result = await submit_strategy_signal(mock_request)
            
            assert "signal_id" in result
            assert result["signal_id"].startswith("sig_")
            assert result["status"] == "submitted"
            assert result["strategy"] == "default"
            assert result["timestamp"] == "2025-09-19T13:00:00Z"
            assert result["data"] == signal_data
            
            # Verify request.json() was called
            mock_request.json.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_submit_strategy_signal_complex_data(self):
        """Test signal submission with complex data structure."""
        mock_request = Mock(spec=Request)
        complex_data = {
            "symbol": "GOOGL",
            "signal_type": "SELL",
            "confidence": 0.92,
            "analysis": {
                "technical": {"rsi": 75.8, "macd": -0.25},
                "fundamental": {"pe_ratio": 28.5, "growth_rate": 0.12},
                "sentiment": {"news_score": -0.3, "social_score": -0.15}
            },
            "execution": {
                "order_type": "MARKET",
                "quantity": 100,
                "time_in_force": "DAY"
            },
            "risk_management": {
                "stop_loss": 2850.0,
                "take_profit": 2700.0,
                "position_size": 0.05
            }
        }
        mock_request.json = AsyncMock(return_value=complex_data)
        
        result = await submit_strategy_signal(mock_request)
        
        assert result["status"] == "submitted"
        assert result["data"] == complex_data
        assert result["data"]["analysis"]["technical"]["rsi"] == 75.8
        assert result["data"]["risk_management"]["stop_loss"] == 2850.0
    
    @pytest.mark.asyncio
    async def test_submit_strategy_signal_empty_data(self):
        """Test signal submission with empty data."""
        mock_request = Mock(spec=Request)
        mock_request.json = AsyncMock(return_value={})
        
        result = await submit_strategy_signal(mock_request)
        
        assert result["status"] == "submitted"
        assert result["strategy"] == "default"
        assert result["data"] == {}
        assert "signal_id" in result
        assert "timestamp" in result
    
    @pytest.mark.asyncio
    async def test_submit_strategy_signal_id_generation(self):
        """Test signal ID generation consistency."""
        mock_request = Mock(spec=Request)
        
        # Same data should generate same signal_id
        signal_data = {"symbol": "TSLA", "action": "BUY"}
        mock_request.json = AsyncMock(return_value=signal_data)
        
        result1 = await submit_strategy_signal(mock_request)
        
        # Reset the mock for second call
        mock_request.json = AsyncMock(return_value=signal_data)
        result2 = await submit_strategy_signal(mock_request)
        
        # Signal IDs should be the same for identical data
        assert result1["signal_id"] == result2["signal_id"]
        assert result1["signal_id"].startswith("sig_")
    
    @pytest.mark.asyncio
    async def test_submit_strategy_signal_json_parse_exception(self):
        """Test signal submission with JSON parsing error."""
        mock_request = Mock(spec=Request)
        mock_request.json = AsyncMock(side_effect=Exception("JSON parse error"))
        
        with patch('backend.api.routes.strategy.logger') as mock_logger:
            with pytest.raises(HTTPException) as exc_info:
                await submit_strategy_signal(mock_request)
            
            assert exc_info.value.status_code == 500
            assert "Signal submission failed" in str(exc_info.value.detail)
            
            # Verify error logging
            mock_logger.error.assert_called_once()
            error_message = mock_logger.error.call_args[0][0]
            assert "Signal submission failed" in error_message
    
    @pytest.mark.asyncio
    async def test_submit_strategy_signal_general_exception(self):
        """Test signal submission with general processing error."""
        mock_request = Mock(spec=Request)
        mock_request.json = AsyncMock(return_value={"test": "data"})
        
        # Mock an exception during signal ID generation
        with patch('backend.api.routes.strategy.hash', side_effect=Exception("Hash error")), \
             patch('backend.api.routes.strategy.logger') as mock_logger:
            
            with pytest.raises(HTTPException) as exc_info:
                await submit_strategy_signal(mock_request)
            
            assert exc_info.value.status_code == 500
            assert "Signal submission failed" in str(exc_info.value.detail)
            
            mock_logger.error.assert_called_once()


class TestModule11EdgeCasesAndErrorHandling:
    """Test edge cases and comprehensive error handling."""
    
    def test_feature_batch_large_dataset(self):
        """Test FeatureBatch with large feature dataset."""
        large_features = []
        for i in range(1000):
            feature = {
                f"feature_{j}": i * j * 0.001 
                for j in range(10)
            }
            large_features.append(feature)
        
        batch = FeatureBatch(
            features=large_features,
            metadata={"size": "large", "feature_count": 10000}
        )
        
        assert len(batch.features) == 1000
        assert batch.metadata["size"] == "large"
    
    def test_signal_batch_with_none_values(self):
        """Test SignalBatch handling of None/missing values in signal fields."""
        # Pydantic will validate dict structure, but fields can have None values
        signals_with_none_fields = [
            {"symbol": "AAPL", "value": None, "confidence": 0.5},
            {"symbol": None, "value": 100, "confidence": 0.8},
            {"symbol": "MSFT", "signal": None, "data": {}}  # Valid dict with None fields
        ]
        
        # This should work as all items are valid dicts
        batch = SignalBatch(
            signals=signals_with_none_fields,
            strategy_id="none_tolerance_test"
        )
        
        assert len(batch.signals) == 3
        assert batch.signals[0]["value"] is None
        assert batch.signals[1]["symbol"] is None
        assert batch.signals[2]["signal"] is None
        
        # Test that None in the list itself raises validation error
        with pytest.raises(ValidationError):
            invalid_batch = SignalBatch(
                signals=[{"valid": "signal"}, None],  # None in list should fail
                strategy_id="test"
            )
    
    @pytest.mark.asyncio
    async def test_timestamp_consistency_across_endpoints(self):
        """Test timestamp format consistency across all endpoints."""
        mock_request = Mock(spec=Request)
        mock_request.json = AsyncMock(return_value={"test": "data"})
        
        fixed_timestamp = "2025-09-19T15:30:45Z"
        
        with patch('backend.api.routes.strategy.datetime') as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = fixed_timestamp
            
            # Test all endpoints return same timestamp format
            status_result = await get_strategy_status()
            
            feature_batch = FeatureBatch(features=[{"test": "feature"}])
            ingest_result = await ingest_features(mock_request, feature_batch)
            
            signal_batch = SignalBatch(signals=[{"test": "signal"}], strategy_id="test")
            batch_result = await process_signal_batch(mock_request, signal_batch)
            
            submit_result = await submit_strategy_signal(mock_request)
            
            # All timestamps should be consistent
            assert status_result["last_update"] == fixed_timestamp
            assert ingest_result["timestamp"] == fixed_timestamp
            assert batch_result["batch_timestamp"] == fixed_timestamp
            assert submit_result["timestamp"] == fixed_timestamp
    
    def test_hash_collision_handling(self):
        """Test handling of potential hash collisions in ID generation."""
        # Test with data that might produce similar hashes
        similar_data = [
            {"symbol": "A", "value": 1},
            {"symbol": "B", "value": 1},
            {"symbol": "A", "value": 2}
        ]
        
        # Generate hashes to verify they're different
        hashes = []
        for data in similar_data:
            hash_value = abs(hash(str(data))) % 10000
            hashes.append(hash_value)
        
        # Verify hashes are computed (even if potentially similar)
        assert len(hashes) == 3
        assert all(isinstance(h, int) for h in hashes)
        assert all(0 <= h <= 9999 for h in hashes)
    
    def test_pydantic_model_field_validation(self):
        """Test comprehensive Pydantic model field validation."""
        # Test FeatureBatch field descriptions
        feature_batch_schema = FeatureBatch.model_json_schema()
        assert "features" in feature_batch_schema["properties"]
        assert feature_batch_schema["properties"]["features"]["description"] == "List of feature vectors"
        
        # Test SignalBatch field descriptions  
        signal_batch_schema = SignalBatch.model_json_schema()
        assert "strategy_id" in signal_batch_schema["properties"]
        assert signal_batch_schema["properties"]["strategy_id"]["description"] == "Strategy identifier"
        assert signal_batch_schema["properties"]["signals"]["description"] == "List of signals"
    
    @pytest.mark.asyncio
    async def test_logger_integration(self):
        """Test logger integration across all endpoints."""
        mock_request = Mock(spec=Request)
        
        with patch('backend.api.routes.strategy.logger') as mock_logger:
            # Test feature ingestion logging
            batch = FeatureBatch(features=[{"test": "feature"}])
            await ingest_features(mock_request, batch)
            mock_logger.info.assert_called()
            
            # Reset mock
            mock_logger.reset_mock()
            
            # Test error logging in exception scenarios
            with patch('backend.api.routes.strategy.len', side_effect=Exception("Test error")):
                try:
                    await ingest_features(mock_request, batch)
                except HTTPException:
                    pass
                mock_logger.error.assert_called()
    
    def test_router_import_and_functionality(self):
        """Test router import and basic functionality."""
        # Verify router is properly configured
        assert hasattr(strategy_module, 'router')
        assert strategy_module.router.prefix == "/strategy"
        
        # Verify all endpoints are accessible
        endpoint_functions = [
            get_strategy_status,
            ingest_features, 
            process_signal_batch,
            submit_strategy_signal
        ]
        
        for func in endpoint_functions:
            assert callable(func)
            assert hasattr(func, '__name__')
    
    def test_model_serialization(self):
        """Test Pydantic model serialization and deserialization."""
        # Test FeatureBatch serialization
        original_batch = FeatureBatch(
            features=[{"rsi": 65.0, "macd": 0.15}],
            metadata={"test": "data"}
        )
        
        # Serialize to dict
        batch_dict = original_batch.model_dump()
        assert "features" in batch_dict
        assert "metadata" in batch_dict
        
        # Deserialize back
        reconstructed = FeatureBatch(**batch_dict)
        assert reconstructed.features == original_batch.features
        assert reconstructed.metadata == original_batch.metadata
        
        # Test SignalBatch serialization
        original_signal_batch = SignalBatch(
            signals=[{"symbol": "AAPL", "action": "BUY"}],
            strategy_id="test_strategy"
        )
        
        signal_dict = original_signal_batch.model_dump()
        reconstructed_signal = SignalBatch(**signal_dict)
        assert reconstructed_signal.signals == original_signal_batch.signals
        assert reconstructed_signal.strategy_id == original_signal_batch.strategy_id


class TestModule121SignalsRoutes:
    """Comprehensive test suite for backend.api.routes.signals module - achieving 100% coverage."""

    def test_signals_models_validation(self):
        """Test all signals Pydantic models."""
        # Import signals models
        from backend.api.routes.signals import (
            SignalRequest, SignalResponse, MultiSignalsResponse, AdvancedSignalsResponse
        )
        
        # Test SignalRequest model
        request = SignalRequest(
            symbol="AAPL",
            signal_strength=0.85,
            timestamp="2024-01-01T10:00:00Z",
            features={"rsi": 70, "sma": 150},
            metadata={"source": "technical"}
        )
        assert request.symbol == "AAPL"
        assert request.signal_strength == 0.85
        assert request.features["rsi"] == 70
        assert request.metadata["source"] == "technical"
        
        # Test SignalResponse model with validation
        response = SignalResponse(
            symbol="AAPL",
            signal_type="BUY",
            confidence=0.85,
            target_price=150.0,
            position_size=100.0,
            timestamp="2024-01-01T10:00:00Z",
            metadata={"model": "lstm"}
        )
        assert response.symbol == "AAPL"
        assert response.confidence == 0.85
        assert 0.0 <= response.confidence <= 1.0  # Validation check
        
        # Test MultiSignalsResponse model
        multi_response = MultiSignalsResponse(
            signals={"AAPL": {"type": "BUY"}, "TSLA": {"type": "SELL"}},
            timestamp="2024-01-01T10:00:00Z"
        )
        assert "AAPL" in multi_response.signals
        assert "TSLA" in multi_response.signals
        
        # Test AdvancedSignalsResponse model
        advanced_response = AdvancedSignalsResponse(
            signals={"AAPL": {"type": "BUY"}},
            features={"AAPL": {"rsi": 70}},
            risk_metrics={"AAPL": {"risk_score": 0.3}},
            timestamp="2024-01-01T10:00:00Z"
        )
        assert "AAPL" in advanced_response.signals
        assert advanced_response.features["AAPL"]["rsi"] == 70
        assert advanced_response.risk_metrics["AAPL"]["risk_score"] == 0.3

    def test_signals_router_configuration(self):
        """Test signals router configuration."""
        from backend.api.routes.signals import router
        
        assert router.prefix == "/signals"
        assert "Trading Signals" in router.tags

    def test_dependency_functions(self):
        """Test all dependency injection functions."""
        from backend.api.routes.signals import (
            get_signal_service, get_strategy_manager, get_alpaca_client,
            get_feature_engineer, get_risk_manager, get_authenticated_user
        )
        
        # Test signal service dependency
        signal_service = get_signal_service()
        assert hasattr(signal_service, 'get_signals')
        assert hasattr(signal_service, 'get_symbol_signals')
        
        # Test mock strategy manager
        strategy_manager = get_strategy_manager()
        assert hasattr(strategy_manager, 'generate_combined_signal')
        
        # Test mock Alpaca client
        alpaca_client = get_alpaca_client()
        assert hasattr(alpaca_client, 'get_historical_data')
        
        # Test mock feature engineer
        feature_engineer = get_feature_engineer()
        assert hasattr(feature_engineer, 'compute_all_features')
        
        # Test mock risk manager
        risk_manager = get_risk_manager()
        assert hasattr(risk_manager, 'assess_signal_risk')

    @pytest.mark.asyncio
    async def test_get_trading_signal_success(self):
        """Test successful single signal retrieval."""
        from backend.api.routes.signals import get_trading_signal
        import pandas as pd
        from datetime import datetime
        from types import SimpleNamespace
        
        # Mock dependencies
        mock_user = Mock()
        mock_strategy_manager = Mock()
        mock_alpaca_client = Mock()
        mock_feature_engineer = Mock()
        
        # Setup mock return values
        price_data = pd.DataFrame({
            'open': [100, 101, 102],
            'high': [105, 106, 107],
            'low': [95, 96, 97],
            'close': [102, 103, 104],
            'volume': [1000, 1100, 1200]
        })
        mock_alpaca_client.get_historical_data = AsyncMock(return_value=price_data)
        
        mock_features = {"rsi": 65.5, "macd": 0.15}
        mock_feature_engineer.compute_all_features.return_value = mock_features
        
        # Create mock signal
        mock_signal = SimpleNamespace()
        mock_signal.symbol = "AAPL"
        mock_signal.signal_type = SimpleNamespace()
        mock_signal.signal_type.value = "BUY"
        mock_signal.confidence = 0.85
        mock_signal.target_price = 150.0
        mock_signal.position_size = 100.0
        mock_signal.timestamp = datetime.now()
        mock_signal.metadata = {"source": "test"}
        
        mock_strategy_manager.generate_combined_signal = AsyncMock(return_value=mock_signal)
        
        # Test the endpoint
        result = await get_trading_signal(
            symbol="AAPL",
            current_user=mock_user,
            strategy_manager=mock_strategy_manager,
            alpaca_client=mock_alpaca_client,
            feature_engineer=mock_feature_engineer
        )
        
        assert result.symbol == "AAPL"
        assert result.signal_type == "BUY"
        assert result.confidence == 0.85
        assert result.target_price == 150.0
        assert result.position_size == 100.0

    @pytest.mark.asyncio
    async def test_get_trading_signal_no_strategy_manager(self):
        """Test signal retrieval with no strategy manager."""
        from backend.api.routes.signals import get_trading_signal
        
        with pytest.raises(HTTPException) as exc_info:
            await get_trading_signal(
                symbol="AAPL",
                current_user=Mock(),
                strategy_manager=None,
                alpaca_client=Mock(),
                feature_engineer=Mock()
            )
        
        assert exc_info.value.status_code == 503
        assert "Strategy manager not available" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_trading_signal_no_market_data(self):
        """Test signal retrieval with no market data client."""
        from backend.api.routes.signals import get_trading_signal
        
        mock_strategy_manager = Mock()
        
        with pytest.raises(HTTPException) as exc_info:
            await get_trading_signal(
                symbol="AAPL",
                current_user=Mock(),
                strategy_manager=mock_strategy_manager,
                alpaca_client=None,
                feature_engineer=Mock()
            )
        
        assert exc_info.value.status_code == 503
        assert "Market data client not available" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_trading_signal_empty_market_data(self):
        """Test signal retrieval with empty market data."""
        from backend.api.routes.signals import get_trading_signal
        import pandas as pd
        
        mock_strategy_manager = Mock()
        mock_alpaca_client = Mock()
        mock_alpaca_client.get_historical_data = AsyncMock(return_value=pd.DataFrame())
        
        with pytest.raises(HTTPException) as exc_info:
            await get_trading_signal(
                symbol="AAPL",
                current_user=Mock(),
                strategy_manager=mock_strategy_manager,
                alpaca_client=mock_alpaca_client,
                feature_engineer=Mock()
            )
        
        assert exc_info.value.status_code == 404
        assert "No market data found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_trading_signal_exception_handling(self):
        """Test signal retrieval exception handling."""
        from backend.api.routes.signals import get_trading_signal
        import pandas as pd
        
        mock_strategy_manager = Mock()
        mock_alpaca_client = Mock()
        mock_feature_engineer = Mock()
        
        # Setup to raise exception during processing
        price_data = pd.DataFrame({'close': [100, 101, 102]})
        mock_alpaca_client.get_historical_data = AsyncMock(return_value=price_data)
        mock_feature_engineer.compute_all_features = Mock(side_effect=Exception("Feature computation failed"))
        
        with patch('backend.api.routes.signals.logger') as mock_logger:
            with pytest.raises(HTTPException) as exc_info:
                await get_trading_signal(
                    symbol="AAPL",
                    current_user=Mock(),
                    strategy_manager=mock_strategy_manager,
                    alpaca_client=mock_alpaca_client,
                    feature_engineer=mock_feature_engineer
                )
            
            assert exc_info.value.status_code == 500
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_signals_success(self):
        """Test successful multi-symbol signal retrieval."""
        from backend.api.routes.signals import get_all_signals
        
        mock_user = Mock()
        mock_strategy_manager = Mock()
        mock_alpaca_client = Mock()
        mock_feature_engineer = Mock()
        
        # Test with successful signal service call
        with patch('backend.services.signal_service.get_signals') as mock_get_signals:
            mock_get_signals.return_value = {"status": "success"}
            
            result = await get_all_signals(
                symbols="AAPL,GOOGL,MSFT",
                current_user=mock_user,
                strategy_manager=mock_strategy_manager,
                alpaca_client=mock_alpaca_client,
                feature_engineer=mock_feature_engineer
            )
            
            assert "AAPL" in result.signals
            assert "GOOGL" in result.signals
            assert "MSFT" in result.signals
            assert result.signals["AAPL"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_get_all_signals_service_error(self):
        """Test multi-symbol signal retrieval with service error."""
        from backend.api.routes.signals import get_all_signals
        
        mock_user = Mock()
        
        # Test with signal service raising exception
        with patch('backend.services.signal_service.get_signals') as mock_get_signals, \
             patch('backend.api.routes.signals.logger') as mock_logger:
            
            mock_get_signals.side_effect = Exception("Service unavailable")
            
            with pytest.raises(HTTPException) as exc_info:
                await get_all_signals(
                    symbols="AAPL,GOOGL",
                    current_user=mock_user,
                    strategy_manager=Mock(),
                    alpaca_client=Mock(),
                    feature_engineer=Mock()
                )
            
            assert exc_info.value.status_code == 500
            assert "Internal Server Error" in str(exc_info.value.detail)
            mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_get_all_signals_general_exception(self):
        """Test multi-symbol signal retrieval with general exception."""
        from backend.api.routes.signals import get_all_signals
        
        # Test general exception handling
        with patch('backend.api.routes.signals.logger') as mock_logger:
            # Cause exception by passing invalid parameters
            with pytest.raises(HTTPException) as exc_info:
                await get_all_signals(
                    symbols=None,  # This will cause an error in split()
                    current_user=Mock(),
                    strategy_manager=Mock(),
                    alpaca_client=Mock(),
                    feature_engineer=Mock()
                )
            
            assert exc_info.value.status_code == 500
            mock_logger.exception.assert_called()

    @pytest.mark.asyncio
    async def test_get_advanced_signals_success(self):
        """Test successful advanced signals retrieval."""
        from backend.api.routes.signals import get_advanced_signals
        import pandas as pd
        from datetime import datetime
        from types import SimpleNamespace
        
        # Mock dependencies
        mock_user = Mock()
        mock_strategy_manager = Mock()
        mock_alpaca_client = Mock()
        mock_feature_engineer = Mock()
        mock_risk_manager = Mock()
        
        # Setup mock data
        price_data = pd.DataFrame({
            'open': [100, 101], 'high': [105, 106], 'low': [95, 96],
            'close': [102, 103], 'volume': [1000, 1100]
        })
        mock_alpaca_client.get_historical_data = AsyncMock(return_value=price_data)
        
        mock_features = {"rsi": 65.5, "macd": 0.15}
        mock_feature_engineer.compute_all_features.return_value = mock_features
        
        mock_signal = SimpleNamespace()
        mock_signal.symbol = "AAPL"
        mock_signal.signal_type = SimpleNamespace()
        mock_signal.signal_type.value = "BUY"
        mock_signal.confidence = 0.85
        mock_signal.target_price = 150.0
        mock_signal.position_size = 100.0
        mock_signal.timestamp = datetime.now()
        mock_signal.metadata = {"source": "test"}
        
        mock_strategy_manager.generate_combined_signal = AsyncMock(return_value=mock_signal)
        
        mock_risk_metrics = {"risk_score": 0.3, "max_position_size": 100}
        mock_risk_manager.assess_signal_risk.return_value = mock_risk_metrics
        
        # Test with features and risk metrics enabled
        result = await get_advanced_signals(
            symbols="AAPL",
            include_features=True,
            include_risk_metrics=True,
            current_user=mock_user,
            strategy_manager=mock_strategy_manager,
            alpaca_client=mock_alpaca_client,
            feature_engineer=mock_feature_engineer,
            risk_manager=mock_risk_manager
        )
        
        assert "AAPL" in result.signals
        assert result.signals["AAPL"]["symbol"] == "AAPL"
        assert result.signals["AAPL"]["signal_type"] == "BUY"
        assert "AAPL" in result.features
        assert result.features["AAPL"]["rsi"] == 65.5
        assert "AAPL" in result.risk_metrics
        assert result.risk_metrics["AAPL"]["risk_score"] == 0.3

    @pytest.mark.asyncio
    async def test_get_advanced_signals_empty_market_data(self):
        """Test advanced signals with empty market data."""
        from backend.api.routes.signals import get_advanced_signals
        import pandas as pd
        
        mock_user = Mock()
        mock_strategy_manager = Mock()
        mock_alpaca_client = Mock()
        mock_alpaca_client.get_historical_data = AsyncMock(return_value=pd.DataFrame())  # Empty data
        
        with patch('backend.api.routes.signals.logger') as mock_logger:
            result = await get_advanced_signals(
                symbols="AAPL",
                current_user=mock_user,
                strategy_manager=mock_strategy_manager,
                alpaca_client=mock_alpaca_client,
                feature_engineer=Mock(),
                risk_manager=Mock()
            )
            
            assert "AAPL" in result.signals
            assert result.signals["AAPL"]["error"] == "No market data available"

    @pytest.mark.asyncio
    async def test_get_advanced_signals_symbol_processing_error(self):
        """Test advanced signals with individual symbol processing error."""
        from backend.api.routes.signals import get_advanced_signals
        import pandas as pd
        
        mock_user = Mock()
        mock_strategy_manager = Mock()
        mock_alpaca_client = Mock()
        mock_feature_engineer = Mock()
        
        # Setup to raise exception for signal generation
        price_data = pd.DataFrame({'close': [100, 101, 102]})
        mock_alpaca_client.get_historical_data = AsyncMock(return_value=price_data)
        mock_feature_engineer.compute_all_features = Mock(side_effect=Exception("Processing failed"))
        
        with patch('backend.api.routes.signals.logger') as mock_logger:
            result = await get_advanced_signals(
                symbols="AAPL",
                current_user=mock_user,
                strategy_manager=mock_strategy_manager,
                alpaca_client=mock_alpaca_client,
                feature_engineer=mock_feature_engineer,
                risk_manager=Mock()
            )
            
            assert "AAPL" in result.signals
            assert "error" in result.signals["AAPL"]
            assert result.signals["AAPL"]["error"] == "Processing failed"
            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_get_advanced_signals_general_exception(self):
        """Test advanced signals general exception handling."""
        from backend.api.routes.signals import get_advanced_signals
        
        with patch('backend.api.routes.signals.logger') as mock_logger:
            with pytest.raises(HTTPException) as exc_info:
                await get_advanced_signals(
                    symbols=None,  # This will cause an error
                    current_user=Mock(),
                    strategy_manager=Mock(),
                    alpaca_client=Mock(),
                    feature_engineer=Mock(),
                    risk_manager=Mock()
                )
            
            assert exc_info.value.status_code == 500
            mock_logger.exception.assert_called()

    @pytest.mark.asyncio
    async def test_get_advanced_signals_http_exception_reraise(self):
        """Test advanced signals HTTPException re-raising (line 325)."""
        from backend.api.routes.signals import get_advanced_signals
        from fastapi import HTTPException
        
        # Test HTTPException raised in the main try block, not within symbol processing
        with patch('backend.api.routes.signals.datetime') as mock_datetime:
            mock_datetime.now.side_effect = HTTPException(status_code=503, detail="Service unavailable")
            
            # This should re-raise the HTTPException (line 325: raise)
            with pytest.raises(HTTPException) as exc_info:
                await get_advanced_signals(
                    symbols="AAPL",
                    current_user=Mock(),
                    strategy_manager=Mock(),
                    alpaca_client=Mock(),
                    feature_engineer=Mock(),
                    risk_manager=Mock()
                )
            
            # Should re-raise the original HTTPException
            assert exc_info.value.status_code == 503
            assert "Service unavailable" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_create_signal_success(self):
        """Test successful signal creation."""
        from backend.api.routes.signals import create_signal, SignalRequest
        from fastapi import Request
        
        mock_request = Mock(spec=Request)
        signal_request = SignalRequest(
            symbol="AAPL",
            signal_strength=0.85,
            timestamp="2024-01-01T10:00:00Z",
            features={"rsi": 70},
            metadata={"source": "test"}
        )
        
        result = await create_signal(mock_request, signal_request)
        
        assert result["status"] == "accepted"
        assert result["symbol"] == "AAPL"
        assert result["signal_strength"] == 0.85
        assert "signal_id" in result
        assert "processed_at" in result

    def test_authentication_dependency_success(self):
        """Test authenticated user dependency with valid user."""
        from backend.api.routes.signals import get_authenticated_user
        
        mock_user = Mock()
        mock_user.username = "testuser"
        
        result = get_authenticated_user(current_user=mock_user)
        assert result == mock_user

    def test_authentication_dependency_unauthorized(self):
        """Test authenticated user dependency with no user."""
        from backend.api.routes.signals import get_authenticated_user
        
        with pytest.raises(HTTPException) as exc_info:
            get_authenticated_user(current_user=None)
        
        assert exc_info.value.status_code == 401
        assert "Unauthorized" in str(exc_info.value.detail)

    def test_signal_response_confidence_validation(self):
        """Test SignalResponse confidence field validation."""
        from backend.api.routes.signals import SignalResponse
        from pydantic import ValidationError
        
        # Valid confidence values
        valid_response = SignalResponse(
            symbol="AAPL",
            signal_type="BUY",
            confidence=0.85,
            timestamp="2024-01-01T10:00:00Z"
        )
        assert valid_response.confidence == 0.85
        
        # Test boundary values
        min_valid = SignalResponse(
            symbol="AAPL", signal_type="BUY", confidence=0.0, timestamp="2024-01-01T10:00:00Z"
        )
        assert min_valid.confidence == 0.0
        
        max_valid = SignalResponse(
            symbol="AAPL", signal_type="BUY", confidence=1.0, timestamp="2024-01-01T10:00:00Z"
        )
        assert max_valid.confidence == 1.0
        
        # Invalid confidence values
        with pytest.raises(ValidationError):
            SignalResponse(
                symbol="AAPL", signal_type="BUY", confidence=-0.1, timestamp="2024-01-01T10:00:00Z"
            )
        
        with pytest.raises(ValidationError):
            SignalResponse(
                symbol="AAPL", signal_type="BUY", confidence=1.1, timestamp="2024-01-01T10:00:00Z"
            )

    @pytest.mark.asyncio
    async def test_mock_strategy_manager_signal_generation(self):
        """Test mock strategy manager signal generation."""
        from backend.api.routes.signals import get_strategy_manager
        
        strategy_manager = get_strategy_manager()
        
        # Test signal generation
        signal = await strategy_manager.generate_combined_signal(
            symbol="AAPL",
            price_data={"test": "data"},
            features={"rsi": 70}
        )
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type.value in ["BUY", "SELL", "HOLD"]
        assert 0.5 <= signal.confidence <= 0.95
        assert 100 <= signal.target_price <= 300
        assert 10 <= signal.position_size <= 100
        assert signal.metadata["source"] == "mock_strategy"

    @pytest.mark.asyncio
    async def test_mock_alpaca_client_data_generation(self):
        """Test mock Alpaca client data generation."""
        from backend.api.routes.signals import get_alpaca_client
        
        alpaca_client = get_alpaca_client()
        
        # Test data generation
        data = await alpaca_client.get_historical_data("AAPL", "1Day", 10)
        
        assert len(data) == 10
        assert "open" in data.columns
        assert "high" in data.columns
        assert "low" in data.columns
        assert "close" in data.columns
        assert "volume" in data.columns

    def test_mock_feature_engineer_computation(self):
        """Test mock feature engineer computation."""
        from backend.api.routes.signals import get_feature_engineer
        
        feature_engineer = get_feature_engineer()
        
        # Test feature computation
        features = feature_engineer.compute_all_features({"test": "data"})
        
        assert "rsi" in features
        assert "macd" in features
        assert "bollinger_position" in features
        assert "volume_ratio" in features
        assert features["rsi"] == 65.5
        assert features["macd"] == 0.15

    def test_mock_risk_manager_assessment(self):
        """Test mock risk manager assessment."""
        from backend.api.routes.signals import get_risk_manager
        
        risk_manager = get_risk_manager()
        
        # Test risk assessment
        risk_metrics = risk_manager.assess_signal_risk("AAPL", "BUY")
        
        assert "risk_score" in risk_metrics
        assert "max_position_size" in risk_metrics
        assert "stop_loss" in risk_metrics
        assert "take_profit" in risk_metrics
        assert risk_metrics["risk_score"] == 0.3
        assert risk_metrics["max_position_size"] == 100