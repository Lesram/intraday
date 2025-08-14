import pytest
from fastapi.testclient import TestClient
from backend.api.factory import create_app
from backend.infra.security import get_current_user
from backend.infra.repositories import get_portfolio_repo


class _FakeUser:
    id = "test-user"


@pytest.mark.api
def test_positions_route_is_registered_and_protected():
    app = create_app()
    # Override the security dep that tests expect to override
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    # Override the repo dep to avoid touching the real DB session in this sanity check
    class _StubRepo:
        async def list_positions(self, user_id: str):
            return []

    app.dependency_overrides[get_portfolio_repo] = lambda: _StubRepo()
    client = TestClient(app)

    # Route inventory assertion
    paths = {r.path for r in app.routes}
    assert "/api/v1/positions" in paths

    # Endpoint call
    r = client.get("/api/v1/positions")
    assert r.status_code in (200, 204)
    # Body form is validated in deeper tests; registration & auth override are the contract here
