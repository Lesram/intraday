def _admin_auth_headers():
    from backend.infra.security import create_access_token

    token = create_access_token("admin@example.com", ["admin", "trader"])
    return {"Authorization": f"Bearer {token}"}


def _trader_auth_headers():
    from backend.infra.security import create_access_token

    token = create_access_token("trader@example.com", ["trader"])
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_get_and_set_execution_mode(client):
    r = client.get("/api/v1/admin/trading/execution-mode", headers=_admin_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] in {"execute", "shadow", "dry_run"}
    assert "allowed_modes" in body

    r2 = client.put(
        "/api/v1/admin/trading/execution-mode",
        json={"mode": "shadow"},
        headers=_admin_auth_headers(),
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["mode"] == "shadow"
    assert body2["overridden"] is True
    assert body2["source"] == "override"

    r3 = client.delete("/api/v1/admin/trading/execution-mode", headers=_admin_auth_headers())
    assert r3.status_code == 200
    body3 = r3.json()
    assert body3["mode"] in {"execute", "shadow", "dry_run"}


def test_trader_cannot_set_execution_mode(client):
    r = client.put(
        "/api/v1/admin/trading/execution-mode",
        json={"mode": "shadow"},
        headers=_trader_auth_headers(),
    )
    assert r.status_code in (401, 403)
