"""
Enhanced app helper for comprehensive testing.
Provides ASGI client with lifespan, dependency overrides, startup/shutdown helpers, and database setup.
"""

from contextlib import asynccontextmanager
from typing import Optional
from unittest.mock import MagicMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from backend.api.main import app as main_app
from backend.infra.db import init_db
from tests.helpers.db_setup import create_all_tables


class TestAppContext:
    """Test context for managing app lifecycle and dependencies."""

    def __init__(self):
        self.app: Optional[FastAPI] = None
        self.client: Optional[AsyncClient] = None
        self.dependency_overrides: dict = {}
        self.startup_called = 0
        self.shutdown_called = 0
        self.resources_created = {}
        self.resources_closed = {}
        self._lifespan_context = None
        self._patches = []

    async def __aenter__(self):
        """Initialize test app with mocked dependencies."""
        self.app = main_app

        # Set up test patches and simplified lifespan
        await self._setup_test_patches()

        # Create ASGI client - this will trigger lifespan events during first request
        self.client = AsyncClient(transport=ASGITransport(app=self.app), base_url="http://test")

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up test app."""
        if self.client:
            await self.client.aclose()

        # Clean up patches
        self._cleanup_patches()

        # Clear dependency overrides
        if self.app:
            self.app.dependency_overrides.clear()

    async def _setup_test_patches(self):
        """Set up patches to mock expensive operations during testing and create database tables."""

        # First ensure database tables are created
        try:
            # Initialize database if not already done
            engine, sessionmaker = init_db()
            # Create all tables for testing
            await create_all_tables(engine)
        except Exception as e:
            # Log but don't fail the test setup for database issues
            print(f"Warning: Could not setup database tables: {e}")

        # Create a simplified test lifespan function that doesn't initialize real components
        @asynccontextmanager
        async def test_lifespan(app: FastAPI):
            """Simplified lifespan for testing that avoids expensive initialization."""
            self.startup_called = 1

            # Mock app state components that tests expect
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

            # Store mock resources for validation
            self.resources_created = {
                "alpaca_client": app.state.alpaca_client,
                "feature_engineer": app.state.feature_engineer,
                "model_manager": app.state.model_manager,
                "risk_manager": app.state.risk_manager,
                "strategy_manager": app.state.strategy_manager,
                "strategy_engine": app.state.strategy_engine,
            }

            try:
                yield
            finally:
                self.shutdown_called = 1
                # Track cleanup
                for name, resource in self.resources_created.items():
                    self.resources_closed[name] = resource

        # Replace the app's lifespan with our test version
        self.app.router.lifespan_context = test_lifespan

    def _cleanup_patches(self):
        """Clean up all patches."""
        for p in self._patches:
            p.stop()
        self._patches.clear()

    def override_dependency(self, dependency, override):
        """Add a dependency override."""
        self.dependency_overrides[dependency] = override
        if self.app:
            self.app.dependency_overrides[dependency] = override

    def get_resource(self, name: str):
        """Get a created resource by name."""
        return self.resources_created.get(name)


@pytest.fixture
async def app_context():
    """Fixture providing a test app context with lifespan management."""
    async with TestAppContext() as context:
        yield context


@pytest.fixture
async def test_client(app_context):
    """Fixture providing an HTTP test client."""
    return app_context.client
