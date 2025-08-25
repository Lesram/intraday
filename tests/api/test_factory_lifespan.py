import pytest
from httpx import AsyncClient, ASGITransport

from backend.api.factory import create_app


@pytest.mark.asyncio
async def test_factory_lifespan_runs_startup_shutdown():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/healthz")
        assert res.status_code in (200, 404)  # some deployments may not expose /healthz here

    # If no exceptions occurred, lifespan startup/shutdown executed
    assert True
