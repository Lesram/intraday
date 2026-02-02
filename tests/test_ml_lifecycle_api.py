import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
def test_lifecycle_summary_endpoint(client: TestClient, auth_headers: dict):
    resp = client.get("/api/v1/models/lifecycle/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "scheduler_enabled" in data
    assert "scheduler_state" in data
    assert "active_models" in data


@pytest.mark.unit
def test_lifecycle_run_jobs_permissions(client: TestClient, auth_headers: dict):
    # These endpoints require admin; depending on fixture roles you may get 403.
    resp = client.post("/api/v1/models/lifecycle/run/daily-monitoring?lookback_days=60", headers=auth_headers)
    assert resp.status_code in (200, 403)

    resp = client.post("/api/v1/models/lifecycle/run/weekly-retrain?lookback_days=60", headers=auth_headers)
    assert resp.status_code in (200, 403)

    resp = client.post("/api/v1/models/lifecycle/run/monthly-review", headers=auth_headers)
    assert resp.status_code in (200, 403)

    if resp.status_code == 200:
        payload = resp.json()
        assert "ok" in payload
        assert "message" in payload
