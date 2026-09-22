"""Regression tests for isolated DB selection and real portal-owned API auth."""
import asyncio

import pytest
from sqlalchemy import text

from tests.conftest import _isolated_postgres_url, _seed_api_test_user


@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://trading:secret@localhost:5432/algotrading",
    "postgresql+asyncpg://testuser:secret@remote.example/testdb",
    "postgresql+asyncpg://testuser:secret@localhost/production",
    "postgresql+asyncpg://admin:secret@localhost/testdb",
    "sqlite+aiosqlite:///production.sqlite3",
    "postgresql+asyncpg://testuser:secret@localhost/testdb?host=remote.example",
    "not-a-database-url",
])
def test_test_database_validator_rejects_application_targets(url):
    with pytest.raises(ValueError):
        _isolated_postgres_url(url)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]", "postgres"])
def test_test_database_validator_accepts_explicit_isolated_postgres(host):
    url = f"postgresql+asyncpg://testuser:testpass@{host}:55439/test_session_evidence"
    assert _isolated_postgres_url(url) == url


def test_sqlite_fixture_never_inherits_ambient_database(monkeypatch, tmp_path):
    from tests.conftest import isolated_database_url
    monkeypatch.delenv("INTRA_TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://trading:secret@localhost/algotrading")
    result = isolated_database_url.__wrapped__(tmp_path)
    assert result == f"sqlite+aiosqlite:///{tmp_path / 'api.sqlite3'}"


def test_portal_seed_and_login_use_the_app_pool(client, test_login_data):
    async def read_user():
        loop = asyncio.get_running_loop()
        async with client.app.state.sessionmaker() as session:
            user = (await session.execute(text(
                "SELECT username, failed_login_attempts, last_login FROM users WHERE username=:username"
            ), {"username": test_login_data["username"]})).one()
            return id(loop), tuple(user)

    loop_before, before = client.portal.call(read_user)
    assert before == (test_login_data["username"], 0, None)
    response = client.post("/auth/login", json=test_login_data)
    assert response.status_code == 200
    token = response.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == test_login_data["username"]
    assert set(me.json()["roles"]) == {"admin", "trader"}
    loop_after, after = client.portal.call(read_user)
    assert loop_after == loop_before
    assert after[1] == 0
    assert after[2] is not None  # Real authentication updated the DB.


def test_real_login_rejects_bad_password_and_records_attempt(client, test_login_data):
    bad = {**test_login_data, "password": "deliberately-wrong-password"}
    response = client.post("/auth/login", json=bad)
    assert response.status_code == 401
    assert "access_token" not in response.json()

    async def attempts():
        async with client.app.state.sessionmaker() as session:
            return (await session.execute(text(
                "SELECT failed_login_attempts FROM users WHERE username=:username"
            ), {"username": test_login_data["username"]})).scalar_one()
    assert client.portal.call(attempts) == 1


def test_seeding_existing_test_account_preserves_id_and_clears_lock(client, test_credentials):
    async def lock_and_read():
        async with client.app.state.sessionmaker() as session:
            await session.execute(text(
                "UPDATE users SET failed_login_attempts=5 WHERE username=:username"
            ), {"username": test_credentials[0]})
            await session.commit()
            return (await session.execute(text("SELECT id FROM users WHERE username=:username"),
                                          {"username": test_credentials[0]})).scalar_one()
    identity = client.portal.call(lock_and_read)
    client.portal.call(_seed_api_test_user, client.app, test_credentials)
    assert client.portal.call(lock_and_read) == identity
    # Re-seed once more and verify the same record can authenticate normally.
    client.portal.call(_seed_api_test_user, client.app, test_credentials)
    assert client.post("/auth/login", json=dict(zip(("username", "password"), test_credentials))).status_code == 200


def test_client_shutdown_errors_are_not_hidden():
    from tests.conftest import _close_test_client
    from unittest.mock import Mock
    import concurrent.futures
    for error in (RuntimeError("shutdown failed"), ValueError("bad cleanup")):
        adapter = Mock()
        adapter.__exit__ = Mock(side_effect=error)
        with pytest.raises(type(error)):
            _close_test_client(adapter)
    adapter = Mock()
    adapter.__exit__ = Mock(side_effect=concurrent.futures.CancelledError())
    _close_test_client(adapter)
