"""
Simple test app context that actually works with lifespan events.
Uses FastAPI's TestClient which properly handles lifespan.
"""

from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class SimpleTestAppContext:
    """Simple test context that uses synchronous TestClient with proper lifespan."""

    def __init__(self):
        self.client: TestClient | None = None
        self.app: FastAPI | None = None
        self.startup_called = 0
        self.shutdown_called = 0
        self.resources_created = {}

    def __enter__(self):
        """Context manager entry."""
        # Import the app
        from backend.api.main import app as main_app
        self.app = main_app

        # Create a test lifespan function that tracks calls and creates mocks
        @asynccontextmanager
        async def test_lifespan(app: FastAPI):
            """Test lifespan that mocks all components."""
            self.startup_called += 1

            # Mock all app state components that tests expect
            app.state.alpaca_client = MagicMock()
            app.state.sentiment_analyzer = MagicMock()
            app.state.feature_engineer = MagicMock()
            app.state.model_manager = MagicMock()
            app.state.ensemble_model = MagicMock()
            app.state.risk_manager = MagicMock()
            app.state.strategy_manager = MagicMock()
            app.state.strategy_engine = MagicMock()
            app.state.ws_manager = MagicMock()
            app.state.metrics_registry = MagicMock()
            app.state.background_tasks = {}

            # Store in resources_created for validation
            self.resources_created = {
                'alpaca_client': app.state.alpaca_client,
                'feature_engineer': app.state.feature_engineer,
                'model_manager': app.state.model_manager,
                'risk_manager': app.state.risk_manager,
                'strategy_manager': app.state.strategy_manager,
                'strategy_engine': app.state.strategy_engine,
            }

            try:
                yield
            finally:
                self.shutdown_called += 1

        # Replace the app's lifespan with our test version
        original_lifespan = self.app.router.lifespan_context
        self.app.router.lifespan_context = test_lifespan

        # Create TestClient which properly handles lifespan
        self.client = TestClient(self.app)

        # Store original lifespan to restore later
        self._original_lifespan = original_lifespan

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.client:
            self.client.close()

        # Restore original lifespan
        if self.app and hasattr(self, '_original_lifespan'):
            self.app.router.lifespan_context = self._original_lifespan


@pytest.fixture
def simple_app_context():
    """Fixture providing a simple test app context."""
    with SimpleTestAppContext() as context:
        yield context
