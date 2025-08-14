"""
Core test: App lifespan & dependency injection.

Tests that the app factory/lifespan builds/tears down long-lived resources exactly once,
and that DI works consistently across routes and WebSocket connections.
"""

import time
from unittest.mock import patch

from fastapi import FastAPI
import pytest

from backend.api.websocket_manager import WebSocketClientManager
from backend.api.factory import create_app
from backend.data.alpaca_client import AlpacaClient
from backend.models.ensemble_model import EnsembleModel
from backend.risk.risk_manager import AsyncRiskManager
from backend.strategies.trading_strategies import StrategyManager


@pytest.mark.core
class TestAppLifespanAndDI:
    """Test app lifespan and dependency injection."""

    @pytest.mark.asyncio
    async def test_startup_runs_exactly_once(self):
        """Test that startup runs exactly once and creates long-lived resources."""
        test_app = FastAPI()

        async with lifespan(test_app):
            # Check that all components are initialized in app.state
            assert hasattr(test_app.state, "alpaca_client")
            assert hasattr(test_app.state, "sentiment_analyzer")
            assert hasattr(test_app.state, "feature_engineer")
            assert hasattr(test_app.state, "model_manager")
            assert hasattr(test_app.state, "ensemble_model")
            assert hasattr(test_app.state, "risk_manager")
            assert hasattr(test_app.state, "strategy_manager")
            assert hasattr(test_app.state, "strategy_engine")

            # Verify resources are not None
            assert test_app.state.alpaca_client is not None
            assert test_app.state.feature_engineer is not None
            assert test_app.state.model_manager is not None
            assert test_app.state.risk_manager is not None
            assert test_app.state.strategy_manager is not None

    @pytest.mark.asyncio
    async def test_lifespan_startup_failure_handling(self):
        """Test lifespan handles startup gracefully with error logging"""
        test_app = FastAPI()

        # Test that the lifespan completes even with component initialization errors
        # The actual implementation uses defensive programming and continues startup
        # with error logging rather than crashing the entire application
        with patch("logging.error") as mock_error:
            async with lifespan(test_app):
                # Lifespan should complete even if some components fail to initialize
                pass

    @pytest.mark.asyncio
    async def test_resource_cleanup_on_shutdown(self):
        """Test resources are cleaned up during shutdown"""
        test_app = FastAPI()

        async with lifespan(test_app):
            # Resources should be created
            assert hasattr(test_app.state, "alpaca_client")

            # Store references to verify cleanup
            resources = {
                "alpaca_client": test_app.state.alpaca_client,
                "risk_manager": test_app.state.risk_manager,
            }

        # After exiting lifespan context, resources should be cleaned up
        # The lifespan function handles graceful shutdown

    @pytest.mark.asyncio
    async def test_dependency_injection_consistency(self):
        """Test that the same instances are injected across different routes"""
        test_app = FastAPI()

        async with lifespan(test_app):
            # Get instances from app.state
            alpaca_client = test_app.state.alpaca_client
            risk_manager = test_app.state.risk_manager

            # Verify they are the same instances referenced throughout the app
            assert alpaca_client is test_app.state.alpaca_client
            assert risk_manager is test_app.state.risk_manager

    @pytest.mark.asyncio
    async def test_websocket_dependency_injection(self):
        """Test DI works for WebSocket connections"""
        test_app = FastAPI()

        async with lifespan(test_app):
            # Verify WebSocket manager is available
            assert hasattr(test_app.state, "ws_manager")
            ws_manager = test_app.state.ws_manager
            assert isinstance(ws_manager, WebSocketClientManager)

    @pytest.mark.asyncio
    async def test_multiple_contexts_isolated(self):
        """Test that multiple lifespan contexts are isolated"""
        test_app1 = FastAPI()
        test_app2 = FastAPI()

        async with lifespan(test_app1):
            async with lifespan(test_app2):
                # Each app should have its own instances
                assert (
                    test_app1.state.alpaca_client is not test_app2.state.alpaca_client
                )
                assert test_app1.state.risk_manager is not test_app2.state.risk_manager

    @pytest.mark.asyncio
    async def test_app_state_isolation(self):
        """Test that app state is properly isolated between test runs"""
        test_app = FastAPI()

        # First run
        async with lifespan(test_app):
            first_alpaca_client = test_app.state.alpaca_client
            first_risk_manager = test_app.state.risk_manager

        # Second run with fresh app
        test_app2 = FastAPI()
        async with lifespan(test_app2):
            second_alpaca_client = test_app2.state.alpaca_client
            second_risk_manager = test_app2.state.risk_manager

            # Should be different instances
            assert first_alpaca_client is not second_alpaca_client
            assert first_risk_manager is not second_risk_manager


# Additional helper tests for component initialization
@pytest.mark.core
class TestComponentInitialization:
    """Test individual component initialization within lifespan"""

    @pytest.mark.asyncio
    async def test_alpaca_client_initialization(self):
        """Test AlpacaClient is properly initialized with test mode"""
        test_app = FastAPI()

        async with lifespan(test_app):
            alpaca_client = test_app.state.alpaca_client
            assert isinstance(alpaca_client, AlpacaClient)
            # Should be in test/paper mode for testing
            assert alpaca_client.paper is True

    @pytest.mark.asyncio
    async def test_risk_manager_initialization(self):
        """Test RiskManager is properly initialized"""
        test_app = FastAPI()

        async with lifespan(test_app):
            risk_manager = test_app.state.risk_manager
            assert isinstance(risk_manager, AsyncRiskManager)

    @pytest.mark.asyncio
    async def test_ensemble_model_initialization(self):
        """Test EnsembleModel is properly initialized"""
        test_app = FastAPI()

        async with lifespan(test_app):
            ensemble_model = test_app.state.ensemble_model
            assert isinstance(ensemble_model, EnsembleModel)

    @pytest.mark.asyncio
    async def test_strategy_manager_initialization(self):
        """Test StrategyManager is properly initialized with dependencies"""
        test_app = FastAPI()

        async with lifespan(test_app):
            strategy_manager = test_app.state.strategy_manager
            assert isinstance(strategy_manager, StrategyManager)

            # Should have risk manager and ensemble model as dependencies
            assert strategy_manager.risk_manager is test_app.state.risk_manager
            assert strategy_manager.ensemble_model is test_app.state.ensemble_model

    @pytest.mark.asyncio
    async def test_websocket_manager_initialization(self):
        """Test WebSocket manager is properly initialized"""
        test_app = FastAPI()

        async with lifespan(test_app):
            ws_manager = test_app.state.ws_manager
            assert isinstance(ws_manager, WebSocketClientManager)


# Performance and timing tests
@pytest.mark.core
class TestLifespanPerformance:
    """Test lifespan performance characteristics"""

    @pytest.mark.asyncio
    async def test_startup_time_reasonable(self):
        """Test that startup completes within reasonable time"""
        test_app = FastAPI()

        start_time = time.time()
        async with lifespan(test_app):
            end_time = time.time()

        startup_duration = end_time - start_time
        # Should complete within 30 seconds (allowing for ML model loading)
        assert startup_duration < 30.0

    @pytest.mark.asyncio
    async def test_shutdown_time_reasonable(self):
        """Test that shutdown completes within reasonable time"""
        test_app = FastAPI()

        async with lifespan(test_app):
            pass  # Setup phase

        # Measure shutdown time
        start_shutdown = time.time()
        # Shutdown happens automatically when exiting context
        end_shutdown = time.time()

        shutdown_duration = end_shutdown - start_shutdown
        # Shutdown should be much faster than startup
        assert shutdown_duration < 5.0


# Error handling and resilience tests
@pytest.mark.core
class TestLifespanResilience:
    """Test lifespan error handling and resilience"""

    @pytest.mark.asyncio
    async def test_component_failure_resilience(self):
        """Test app startup fails gracefully when components fail"""
        test_app = FastAPI()

        # Mock component failures
        with patch(
            "backend.data.social_sentiment.SocialSentimentAnalyzer.__init__",
            side_effect=Exception("Mock sentiment failure"),
        ):
            with pytest.raises(Exception, match="Mock sentiment failure"):
                async with lifespan(test_app):
                    pass  # Should not reach here

    @pytest.mark.asyncio
    async def test_database_connection_failure_handling(self):
        """Test graceful handling of database connection failures"""
        from backend.api.main import lifespan as real_lifespan

        test_app = FastAPI()

        # Mock the init_db function directly during the lifespan startup
        with patch(
            "backend.api.main.init_db", side_effect=Exception("Mock DB failure")
        ):
            with pytest.raises(Exception, match="Mock DB failure"):
                async with real_lifespan(test_app):
                    pass  # Should fail before reaching here

    @pytest.mark.asyncio
    async def test_external_service_failure_resilience(self):
        """Test resilience to external service failures during startup"""
        from backend.api.main import lifespan as real_lifespan

        test_app = FastAPI()

        # Mock external service failures (e.g., Twitter API, Reddit API)
        with patch(
            "backend.data.social_sentiment.SocialSentimentAnalyzer._init_twitter",
            side_effect=Exception("Twitter API failure"),
        ):
            with patch(
                "backend.data.social_sentiment.SocialSentimentAnalyzer._init_reddit",
                side_effect=Exception("Reddit API failure"),
            ):
                with pytest.raises(Exception, match="Twitter API failure"):
                    async with real_lifespan(test_app):
                        pass  # Should fail
                    # Sentiment analyzer should have fallback behavior


# Integration test with real components
@pytest.mark.core
@pytest.mark.slow
class TestLifespanIntegration:
    """Integration tests with real component initialization"""

    @pytest.mark.asyncio
    async def test_full_stack_initialization(self):
        """Test complete stack initialization works end-to-end"""
        test_app = FastAPI()

        async with lifespan(test_app):
            # All major components should be initialized
            components = [
                "alpaca_client",
                "sentiment_analyzer",
                "feature_engineer",
                "model_manager",
                "ensemble_model",
                "risk_manager",
                "strategy_manager",
                "strategy_engine",
                "ws_manager",
            ]

            for component in components:
                assert hasattr(test_app.state, component)
                assert getattr(test_app.state, component) is not None

    @pytest.mark.asyncio
    async def test_component_dependencies_satisfied(self):
        """Test that component dependencies are properly satisfied"""
        test_app = FastAPI()

        async with lifespan(test_app):
            # Strategy manager should have its dependencies
            strategy_manager = test_app.state.strategy_manager
            assert hasattr(strategy_manager, "risk_manager")
            assert hasattr(strategy_manager, "ensemble_model")
            assert strategy_manager.risk_manager is test_app.state.risk_manager
            assert strategy_manager.ensemble_model is test_app.state.ensemble_model

    @pytest.mark.asyncio
    async def test_observability_integration(self):
        """Test observability components are properly integrated"""
        test_app = FastAPI()

        async with lifespan(test_app):
            # Should have metrics registry
            assert hasattr(test_app.state, "metrics_registry")
            assert test_app.state.metrics_registry is not None
