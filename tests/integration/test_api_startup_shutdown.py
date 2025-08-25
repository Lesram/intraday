"""
Integration tests for API startup, shutdown, and readiness probes.
Tests the complete application lifecycle with ephemeral database.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import respx

# Test infrastructure
from tests.helpers.broker_mock import AlpacaMockResponder


@pytest.mark.integration
class TestAPIStartupShutdown:
    """Integration tests for API startup and shutdown procedures."""

    @pytest.fixture
    async def ephemeral_app(self):
        """Create ephemeral app instance with test database."""
        # Import here to avoid circular imports during collection
        from backend.api.main import app
        from backend.settings import settings
        from backend.database.connection import get_database_session

        # Override database URL for testing
        test_db_url = "sqlite+aiosqlite:///:memory:"

        with patch.object(settings, "DATABASE_URL", test_db_url):
            # Initialize in-memory database
            from sqlalchemy.ext.asyncio import create_async_engine

            from backend.database.models import Base

            engine = create_async_engine(test_db_url, echo=False)

            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # Override dependency
            async def get_test_session():
                from sqlalchemy.ext.asyncio import AsyncSession

                async with AsyncSession(engine) as session:
                    yield session

            app.dependency_overrides[get_database_session] = get_test_session

            yield app

            # Cleanup
            app.dependency_overrides.clear()
            await engine.dispose()

    @pytest.fixture
    async def mock_broker_service(self):
        """Mock broker service for testing."""
        with patch("backend.services.broker_service.BrokerService") as mock_service:
            # Create mock instance
            mock_instance = AsyncMock()
            mock_instance.health_check.return_value = True
            mock_instance.reconcile_open_orders.return_value = None
            mock_service.return_value = mock_instance

            yield mock_instance

    @pytest.mark.asyncio
    async def test_app_startup_sequence(self, ephemeral_app, mock_broker_service):
        """Test that the application starts up correctly with all dependencies."""
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=ephemeral_app), base_url="http://test"
        ) as client:
            # Test that startup completed successfully by checking health
            response = await client.get("/health")

            assert response.status_code == 200
            health_data = response.json()
            assert health_data["status"] == "healthy"
            assert "timestamp" in health_data
            assert "uptime_seconds" in health_data

    @pytest.mark.asyncio
    async def test_readiness_probe_checks_dependencies(
        self, ephemeral_app, mock_broker_service
    ):
        """Test readiness probe validates all dependencies."""
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=ephemeral_app), base_url="http://test"
        ) as client:
            # Test readiness when all dependencies are healthy
            mock_broker_service.health_check.return_value = True

            response = await client.get("/readyz")

            assert response.status_code == 200
            readiness_data = response.json()
            assert readiness_data["status"] == "ready"
            assert readiness_data["checks"]["database"] is True
            assert readiness_data["checks"]["broker"] is True
            # Validate new schema fields
            assert "problems" in readiness_data
            assert readiness_data["problems"] == {}  # No problems when healthy

    @pytest.mark.asyncio
    async def test_readiness_probe_fails_on_unhealthy_broker(
        self, ephemeral_app, mock_broker_service
    ):
        """Test readiness probe fails when broker is unhealthy."""
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=ephemeral_app), base_url="http://test"
        ) as client:
            # Simulate broker health check failure
            mock_broker_service.health_check.return_value = False

            response = await client.get("/readyz")

            assert response.status_code == 503  # Service Unavailable
            readiness_data = response.json()
            assert readiness_data["status"] == "degraded"  # Modern status: ready/degraded
            assert readiness_data["legacy_status"] == "not_ready"  # Legacy status: ready/not_ready
            assert (
                readiness_data["checks"]["database"] is True
            )  # DB should still be healthy
            assert readiness_data["checks"]["broker"] is False  # Broker is unhealthy
            # Validate new schema fields
            assert "problems" in readiness_data
            assert "broker" in readiness_data["problems"]  # Broker should be in problems
            assert readiness_data["problems"]["broker"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_liveness_probe_basic_functionality(self, ephemeral_app):
        """Test liveness probe responds when process is alive."""
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=ephemeral_app), base_url="http://test"
        ) as client:
            response = await client.get("/healthz")

            assert response.status_code == 200
            liveness_data = response.json()
            assert liveness_data["status"] == "alive"
            assert "timestamp" in liveness_data

    @pytest.mark.asyncio
    async def test_graceful_shutdown_with_background_tasks(
        self, ephemeral_app, mock_broker_service
    ):
        """Test that background tasks are cancelled gracefully on shutdown."""
        # Track background task lifecycle
        task_started = asyncio.Event()
        task_cancelled = asyncio.Event()

        async def mock_background_task():
            """Mock background task that tracks its lifecycle."""
            task_started.set()
            try:
                # Simulate long-running task
                await asyncio.sleep(10)  # Would run for 10s if not cancelled
            except asyncio.CancelledError:
                task_cancelled.set()
                raise

        # Use the actual lifespan context to test shutdown behavior
        async with ephemeral_app.router.lifespan_context(ephemeral_app):
            # Start a background task and register it
            task = asyncio.create_task(mock_background_task())
            ephemeral_app.state.register_task(task)

            # Wait for task to start
            await asyncio.wait_for(task_started.wait(), timeout=1.0)

            # Verify task is running
            assert not task.done(), "Task should be running"

        # Lifespan context has exited - task should be cancelled
        # Give it a moment to cancel
        await asyncio.sleep(0.1)

        # Verify task was cancelled
        assert task_cancelled.is_set(), "Background task should have been cancelled"
        assert task.done(), "Task should be completed"
        assert task.cancelled(), "Task should be cancelled"

    @pytest.mark.asyncio
    async def test_app_handles_database_connection_errors(self, mock_broker_service):
        """Test app startup behavior when database connection fails."""
        from backend.api.main import app

        # Simulate database connection failure
        with patch("backend.database.connection.get_database_session") as mock_db:
            mock_db.side_effect = Exception("Database connection failed")

            from httpx import ASGITransport, AsyncClient

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # Readiness check should fail
                response = await client.get("/readyz")

                assert response.status_code == 503
                readiness_data = response.json()
                assert readiness_data["status"] == "degraded"  # Modern status format
                assert readiness_data["legacy_status"] == "not_ready"  # Legacy status format
                assert readiness_data["checks"]["database"] is False

    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self, ephemeral_app, mock_broker_service):
        """Test that multiple concurrent health checks work correctly."""
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=ephemeral_app), base_url="http://test"
        ) as client:
            # Make multiple concurrent requests to health endpoints
            tasks = []

            for _ in range(10):
                tasks.append(client.get("/health"))
                tasks.append(client.get("/readyz"))
                tasks.append(client.get("/healthz"))

            responses = await asyncio.gather(*tasks)

            # All responses should be successful
            for response in responses:
                assert response.status_code in [200, 503]  # 503 is valid for readiness
                assert "status" in response.json()

    @pytest.mark.asyncio
    async def test_metrics_endpoint_availability(self, ephemeral_app):
        """Test that metrics endpoint is available during startup."""
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=ephemeral_app), base_url="http://test"
        ) as client:
            response = await client.get("/metrics")

            assert response.status_code == 200
            assert "text/plain" in response.headers.get("content-type", "")

            # Should contain basic Prometheus metrics
            metrics_text = response.text
            assert "http_requests_total" in metrics_text or "process_" in metrics_text

    @pytest.mark.asyncio
    async def test_app_startup_with_broker_mock(self, ephemeral_app):
        """Test application startup with mocked broker responses."""

        # Set up comprehensive Alpaca mock
        mock_responder = AlpacaMockResponder()

        with respx.mock(assert_all_called=False) as respx_mock:  # Don't require all mocks to be called
            mock_responder.setup_responders(respx_mock)

            from httpx import ASGITransport, AsyncClient

            async with AsyncClient(
                transport=ASGITransport(app=ephemeral_app), base_url="http://test"
            ) as client:
                # Test health endpoint
                response = await client.get("/health")
                assert response.status_code == 200

                # Test that broker mock is working by checking readiness
                response = await client.get("/readyz")
                # Should be ready if broker mock is responding correctly
                assert response.status_code in [
                    200,
                    503,
                ]  # May depend on broker health check implementation

    @pytest.mark.asyncio
    async def test_startup_with_environment_variables(self, ephemeral_app):
        """Test startup behavior with various environment variable configurations."""
        import os

        # Save original env vars
        original_env = {
            "LOG_LEVEL": os.environ.get("LOG_LEVEL"),
            "TESTING": os.environ.get("TESTING"),
        }

        try:
            # Set test environment variables
            os.environ["LOG_LEVEL"] = "DEBUG"
            os.environ["TESTING"] = "true"

            from httpx import ASGITransport, AsyncClient

            async with AsyncClient(
                transport=ASGITransport(app=ephemeral_app), base_url="http://test"
            ) as client:
                response = await client.get("/health")
                assert response.status_code == 200

                health_data = response.json()
                assert health_data["status"] == "healthy"

        finally:
            # Restore original environment
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


@pytest.mark.integration
class TestApplicationLifecycleEdgeCases:
    """Test edge cases in application lifecycle management."""

    @pytest.mark.asyncio
    async def test_rapid_startup_shutdown_cycles(self):
        """Test that rapid startup/shutdown cycles don't cause resource leaks."""
        from httpx import ASGITransport, AsyncClient

        from backend.api.main import app

        for i in range(5):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # Quick health check
                response = await client.get("/health")
                assert response.status_code == 200

                # Small delay between cycles
                await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_shutdown_timeout_handling(self):
        """Test that shutdown timeouts are handled gracefully."""
        from backend.api.main import app

        # Mock a task that takes too long to shutdown
        long_running_task_started = asyncio.Event()

        async def stubborn_background_task():
            long_running_task_started.set()
            # Simulate a task that doesn't respond to cancellation quickly
            try:
                await asyncio.sleep(30)  # Very long task
            except asyncio.CancelledError:
                # Simulate slow cleanup
                await asyncio.sleep(0.5)  # Takes time to cleanup
                raise

        # Use the actual lifespan context to test shutdown behavior
        async with app.router.lifespan_context(app):
            # Start stubborn task and register it
            task = asyncio.create_task(stubborn_background_task())
            app.state.register_task(task)

            # Wait for task to start
            await asyncio.wait_for(long_running_task_started.wait(), timeout=1.0)

            # Verify task is running
            assert not task.done(), "Task should be running"

        # Context manager exit should handle cancellation
        # Task should eventually be cancelled even if it's slow
        await asyncio.sleep(1.0)  # Give it time to cancel
        assert task.done()  # Task should be done (cancelled)
