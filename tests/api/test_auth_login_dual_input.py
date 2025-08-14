import pytest
from fastapi.testclient import TestClient

from backend.api.factory import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_login_accepts_json(client):
    resp = client.post("/auth/login", json={"username": "u", "password": "p"})
    assert resp.status_code in (200, 401)
    if resp.status_code == 200:
        data = resp.json()
        assert data["token_type"] == "bearer"
        assert data["user_id"] == "user_u"


def test_login_accepts_form(client):
    resp = client.post("/auth/login", data={"username": "u", "password": "p"})
    assert resp.status_code in (200, 401)
    if resp.status_code == 200:
        data = resp.json()
        assert data["token_type"] == "bearer"
        assert data["user_id"] == "user_u"
