"""Admin execution-mode routes against the real app.

Audit 2026-10-05 A3-01: setting the runtime override is refused while the
research policy lock is on (hard-coded for the research period), unknown modes
are a 422, and reading/clearing stay available to admins.
"""


def _admin_auth_headers():
    from backend.infra.security import create_access_token

    token = create_access_token("admin@example.com", ["admin", "trader"])
    return {"Authorization": f"Bearer {token}"}


def _trader_auth_headers():
    from backend.infra.security import create_access_token

    token = create_access_token("trader@example.com", ["trader"])
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_read_execution_mode_but_override_is_refused_under_research_lock(client):
    r = client.get("/api/v1/admin/trading/execution-mode", headers=_admin_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] in {"execute", "shadow", "dry_run"}
    assert "allowed_modes" in body
    assert body["override_allowed"] is False
    assert "research policy lock" in body["override_blocked_reason"]

    r2 = client.put(
        "/api/v1/admin/trading/execution-mode",
        json={"mode": "shadow"},
        headers=_admin_auth_headers(),
    )
    assert r2.status_code == 423
    assert r2.json()["detail"]["code"] == "research_policy_locked"

    r3 = client.get("/api/v1/admin/trading/execution-mode", headers=_admin_auth_headers())
    assert r3.json()["overridden"] is False
    assert r3.json()["source"] == "env"

    r4 = client.delete("/api/v1/admin/trading/execution-mode", headers=_admin_auth_headers())
    assert r4.status_code == 200
    assert r4.json()["mode"] in {"execute", "shadow", "dry_run"}


def test_unknown_execution_mode_is_a_validation_error(client):
    r = client.put(
        "/api/v1/admin/trading/execution-mode",
        json={"mode": "pause"},
        headers=_admin_auth_headers(),
    )
    assert r.status_code == 422


def test_trader_cannot_set_execution_mode(client):
    r = client.put(
        "/api/v1/admin/trading/execution-mode",
        json={"mode": "shadow"},
        headers=_trader_auth_headers(),
    )
    assert r.status_code in (401, 403)
