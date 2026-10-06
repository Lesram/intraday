"""Audit 2026-10-05: session revocation, login lockout, admin reset, log redaction.

A2-01  refresh re-reads the user (exists, active, roles from the database);
       a password change or deactivation ends earlier sessions; rotation.
A2-02  logout ends the login session (refresh token included); revocations
       outlive the clock-skew leeway.
A2-03/04  bcrypt runs off the event loop; attempts are counted atomically
       before the password check; an expired lock restarts the counter.
A2-07  scripts/db/create_admin_user.py --force resets the password in place.
A1-02/A6-07/A1-04  no access tokens or Redis passwords in logs.
A1-03  token-blacklist Redis lookups are bounded and fail open.

In-process only: throwaway passwords and in-process signing keys, SQLite files
under tmp_path, fake Redis objects, and an in-process RESP server on a Unix
socket for the timeout tests.
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
import importlib.util
import json
import logging
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace

import bcrypt
from fastapi import FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.requests import Request

from backend.api.routes import auth
import backend.infra.db as db_module
from backend.infra import security
import backend.infra.users as users_module

REPO = Path(__file__).resolve().parents[1]
UserRepository = users_module.UserRepository

# Mirrors the users table of Alembic 706e00fe1a28 (types adapted to SQLite)
# plus one child table with the ON DELETE CASCADE foreign key the admin
# script must never trigger.
USERS_DDL = """
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username VARCHAR(50) NOT NULL UNIQUE,
  email VARCHAR(255) NOT NULL UNIQUE,
  hashed_password VARCHAR(255) NOT NULL,
  is_active BOOLEAN DEFAULT 1,
  is_superuser BOOLEAN DEFAULT 0,
  roles TEXT NOT NULL DEFAULT '[]',
  failed_login_attempts INTEGER DEFAULT 0,
  locked_until TIMESTAMP NULL,
  last_login TIMESTAMP NULL
)"""
WATCHLISTS_DDL = """
CREATE TABLE watchlists (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT
)"""


def new_password() -> str:
    return "Aa1!" + secrets.token_urlsafe(12)


def _enable_foreign_keys(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture(autouse=True)
def isolated_auth_state(monkeypatch):
    """Fresh revocation store, no Redis backend, and cheap bcrypt (cost 4)."""
    monkeypatch.setattr(security, "_memory_blacklist", {})
    monkeypatch.setattr(security, "_token_blacklist_redis", None)
    real_gensalt = bcrypt.gensalt
    monkeypatch.setattr(bcrypt, "gensalt", lambda *a, **k: real_gensalt(rounds=4))


@pytest.fixture
async def users_db(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path / 'users.sqlite3'}"
    engine = create_async_engine(url)
    event.listen(engine.sync_engine, "connect", _enable_foreign_keys)
    async with engine.begin() as conn:
        await conn.execute(text(USERS_DDL))
        await conn.execute(text(WATCHLISTS_DDL))
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    # /auth/token/refresh reads the account through the module sessionmaker.
    monkeypatch.setattr(db_module, "_sessionmaker", sessionmaker)
    yield SimpleNamespace(url=url, engine=engine, sessionmaker=sessionmaker)
    await engine.dispose()


async def add_user(db, username, password, roles=("admin", "trader"), *, active=True,
                   failed=0, locked_until=None) -> int:
    async with db.sessionmaker() as session:
        row = (await session.execute(text(
            "INSERT INTO users (username, email, hashed_password, roles, is_active,"
            " failed_login_attempts, locked_until)"
            " VALUES (:u, :e, :h, :r, :a, :f, :l) RETURNING id"), {
                "u": username, "e": f"{username}@example.test",
                "h": security.hash_password(password), "r": json.dumps(list(roles)),
                "a": active, "f": failed, "l": locked_until,
        })).fetchone()
        await session.commit()
    return row[0]


async def run_sql(db, statement, **params):
    async with db.sessionmaker() as session:
        result = await session.execute(text(statement), params)
        rows = result.fetchall() if result.returns_rows else None
        await session.commit()
    return rows


async def user_row(db, username):
    rows = await run_sql(
        db, "SELECT id, email, hashed_password, roles, is_active, failed_login_attempts,"
            " locked_until FROM users WHERE username = :u", u=username)
    if not rows:
        return None
    r = rows[0]
    return SimpleNamespace(id=r[0], email=r[1], hashed_password=r[2], roles=json.loads(r[3]),
                           is_active=bool(r[4]), failed=r[5] or 0,
                           locked_until=UserRepository._normalize_datetime(r[6]))


async def login(db, username, password):
    async with db.sessionmaker() as session:
        return await auth.login(auth.LoginRequest(username=username, password=password), db=session)


async def authenticate(db, username, password):
    async with db.sessionmaker() as session:
        return await UserRepository(db_session=session).authenticate_user(username, password)


async def refresh(token):
    return await auth.refresh_token(auth.TokenRefreshRequest(refresh_token=token))


async def refresh_refusal(token) -> str:
    try:
        await refresh(token)
    except HTTPException as exc:
        assert exc.status_code == 401
        return exc.detail
    pytest.fail("refresh was accepted")


def http_request(path="/api/v1/auth/me", token=None, method="GET"):
    headers = [(b"authorization", f"Bearer {token}".encode())] if token else []
    return Request({"type": "http", "method": method, "path": path,
                    "headers": headers, "query_string": b""})


async def current_user(token):
    return await security.get_current_user(
        http_request(token=token), HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))


async def access_refusal(token) -> str:
    with pytest.raises(HTTPException) as exc:
        await current_user(token)
    assert exc.value.status_code == 401
    return exc.value.detail


class FakeRedis:
    """Async in-memory subset of the Redis client API; every call yields."""

    def __init__(self):
        self.data: dict[str, object] = {}
        self.ttl: dict[str, int] = {}

    async def get(self, key):
        await asyncio.sleep(0.001)
        return self.data.get(key)

    async def mget(self, keys):
        await asyncio.sleep(0.001)
        return [self.data.get(key) for key in keys]

    async def setex(self, key, ttl, value):
        await asyncio.sleep(0.001)
        self.data[key], self.ttl[key] = value, ttl

    async def set(self, key, value, ex=None, nx=False):
        await asyncio.sleep(0.001)
        if nx and key in self.data:
            return None
        self.data[key], self.ttl[key] = value, ex
        return True


# ─────────────────────────────────────────────────────────────────────
# A2-01 — refresh re-checks the user; credential changes end sessions
# ─────────────────────────────────────────────────────────────────────


async def test_refresh_issues_the_roles_stored_in_the_database(users_db):
    password = new_password()
    await add_user(users_db, "ops", password, ("admin", "trader"))
    tokens = await login(users_db, "ops", password)
    await run_sql(users_db, "UPDATE users SET roles = :r WHERE username = 'ops'",
                  r=json.dumps(["viewer"]))

    renewed = await refresh(tokens.refresh_token)

    assert security.verify_token(renewed.access_token).roles == ["viewer"]
    assert security.decode_refresh_token(renewed.refresh_token)["roles"] == ["viewer"]


@pytest.mark.parametrize("change", ["deactivated", "deleted"])
async def test_refresh_refuses_inactive_or_missing_accounts(users_db, change):
    password = new_password()
    await add_user(users_db, "ops", password)
    tokens = await login(users_db, "ops", password)
    if change == "deactivated":
        await run_sql(users_db, "UPDATE users SET is_active = 0 WHERE username = 'ops'")
    else:
        await run_sql(users_db, "DELETE FROM users WHERE username = 'ops'")

    assert await refresh_refusal(tokens.refresh_token) == "invalid_token"


async def test_password_change_ends_sessions_issued_before_it(users_db):
    password, replacement = new_password(), new_password()
    await add_user(users_db, "ops", password)
    tokens = await login(users_db, "ops", password)
    assert (await current_user(tokens.access_token)).username == "ops"

    async with users_db.sessionmaker() as session:
        assert await UserRepository(db_session=session).change_password("ops", password, replacement)

    assert await access_refusal(tokens.access_token) == "token_revoked"
    assert await refresh_refusal(tokens.refresh_token) == "refresh_token_revoked"
    fresh = await login(users_db, "ops", replacement)
    assert (await current_user(fresh.access_token)).username == "ops"
    assert security.verify_token((await refresh(fresh.refresh_token)).access_token).sub == "ops"


async def test_out_of_band_password_reset_ends_refresh_chains(users_db):
    """A hash replaced directly in the database (no API call) still ends refresh."""
    password = new_password()
    await add_user(users_db, "ops", password)
    tokens = await login(users_db, "ops", password)
    await run_sql(users_db, "UPDATE users SET hashed_password = :h WHERE username = 'ops'",
                  h=security.hash_password(new_password()))

    assert await refresh_refusal(tokens.refresh_token) == "refresh_token_revoked"


async def test_deactivation_through_the_repository_rejects_live_access_tokens(users_db):
    password = new_password()
    await add_user(users_db, "ops", password)
    tokens = await login(users_db, "ops", password)

    async with users_db.sessionmaker() as session:
        assert await UserRepository(db_session=session).deactivate_user("ops")

    assert await access_refusal(tokens.access_token) == "token_revoked"
    assert await refresh_refusal(tokens.refresh_token) in {"invalid_token", "refresh_token_revoked"}


async def test_refresh_rotates_within_the_session_and_is_single_use(users_db):
    password = new_password()
    await add_user(users_db, "ops", password)
    tokens = await login(users_db, "ops", password)

    renewed = await refresh(tokens.refresh_token)

    old_claims = security.decode_refresh_token(tokens.refresh_token)
    new_claims = security.decode_refresh_token(renewed.refresh_token)
    assert new_claims["sid"] == old_claims["sid"] and new_claims["jti"] != old_claims["jti"]
    assert await refresh_refusal(tokens.refresh_token) == "refresh_token_already_used"
    assert (await refresh(renewed.refresh_token)).access_token


async def test_concurrent_redemption_of_one_refresh_token_succeeds_once(users_db, monkeypatch):
    monkeypatch.setattr(security, "_token_blacklist_redis", FakeRedis())
    password = new_password()
    await add_user(users_db, "ops", password)
    tokens = await login(users_db, "ops", password)

    results = await asyncio.gather(*(refresh(tokens.refresh_token) for _ in range(3)),
                                   return_exceptions=True)

    issued = [r for r in results if not isinstance(r, BaseException)]
    refused = [r for r in results if isinstance(r, HTTPException)]
    assert len(issued) == 1 and len(refused) == 2
    assert {r.detail for r in refused} == {"refresh_token_already_used"}


async def test_refresh_tokens_without_session_binding_are_refused(users_db):
    """Tokens minted before this release carry no sid/cfp: log in again."""
    await add_user(users_db, "ops", new_password())
    legacy = security.create_refresh_token("ops", ["admin", "trader"])

    assert await refresh_refusal(legacy) == "invalid_token"


# ─────────────────────────────────────────────────────────────────────
# A2-02 — logout ends the session; revocation outlives the leeway
# ─────────────────────────────────────────────────────────────────────


async def test_logout_ends_the_whole_login_session(users_db):
    password = new_password()
    await add_user(users_db, "ops", password)
    tokens = await login(users_db, "ops", password)
    renewed = await refresh(tokens.refresh_token)  # same session, new pair

    out = await auth.logout(http_request("/api/v1/auth/logout", renewed.access_token, "POST"))

    assert out.ok is True and out.message == "Logged out: ops"
    assert await access_refusal(renewed.access_token) == "token_revoked"
    # The access token from before the refresh shares the session.
    assert await access_refusal(tokens.access_token) == "token_revoked"
    assert await refresh_refusal(renewed.refresh_token) == "refresh_token_revoked"


async def test_logout_revokes_a_refresh_token_sent_in_the_body(users_db):
    password = new_password()
    await add_user(users_db, "ops", password)
    tokens = await login(users_db, "ops", password)

    out = await auth.logout(http_request("/api/v1/auth/logout", None, "POST"),
                            auth.LogoutRequest(refresh_token=tokens.refresh_token))

    assert out.ok is True
    # Both its jti and its session are revoked; either refusal ends it.
    assert await refresh_refusal(tokens.refresh_token) in {
        "refresh_token_already_used", "refresh_token_revoked"}
    assert await access_refusal(tokens.access_token) == "token_revoked"  # same session


def test_logout_endpoint_body_is_optional_over_http():
    app = FastAPI()
    app.include_router(auth.router)
    client = TestClient(app)
    session_id, other_session = security.new_session_id(), security.new_session_id()
    access = security.create_access_token("ops", ["admin"], session_id=session_id)
    other_refresh = security.create_refresh_token("ops", ["admin"], session_id=other_session)

    assert client.post("/auth/logout").json() == {"ok": True, "message": "Logged out"}
    response = client.post("/auth/logout", headers={"Authorization": f"Bearer {access}"},
                           json={"refresh_token": other_refresh})

    assert response.status_code == 200 and response.json()["message"] == "Logged out: ops"
    assert f"sid:{session_id}" in security._memory_blacklist
    assert f"sid:{other_session}" in security._memory_blacklist
    assert security.decode_refresh_token(other_refresh)["jti"] in security._memory_blacklist


async def test_logout_of_an_expired_access_token_still_ends_its_session():
    session_id = security.new_session_id()
    expired = security.create_access_token("ops", ["admin"], expires_minutes=-5,
                                           session_id=session_id)

    out = await auth.logout(http_request("/api/v1/auth/logout", expired, "POST"))

    assert out.message == "Logged out"
    assert await security.token_revocation_reason("other-jti", session_id=session_id) == "session"


async def test_revocations_outlive_the_clock_skew_leeway(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(security, "_token_blacklist_redis", fake)
    access = security.create_access_token("ops", ["admin"])
    claims = security.decode_token(access)

    await auth.logout(http_request("/api/v1/auth/logout", access, "POST"))

    assert security._memory_blacklist[claims["jti"]] >= claims["exp"] + security.JWT_CLOCK_SKEW
    ttl = fake.ttl[f"{security.TOKEN_BLACKLIST_PREFIX}{claims['jti']}"]
    assert time.time() + ttl >= claims["exp"] + security.JWT_CLOCK_SKEW


# ─────────────────────────────────────────────────────────────────────
# A2-03 / A2-04 — off-loop bcrypt, atomic counting, lock expiry
# ─────────────────────────────────────────────────────────────────────


async def test_password_hashing_runs_off_the_event_loop(users_db, monkeypatch):
    password = new_password()
    await add_user(users_db, "ops", password)
    on_loop_thread: list[bool] = []
    real_verify, real_hash = users_module.verify_password, users_module.hash_password

    def slow_verify(plain, hashed):
        on_loop_thread.append(threading.current_thread() is threading.main_thread())
        time.sleep(0.5)
        return real_verify(plain, hashed)

    def slow_hash(plain):
        on_loop_thread.append(threading.current_thread() is threading.main_thread())
        time.sleep(0.5)
        return real_hash(plain)

    monkeypatch.setattr(users_module, "verify_password", slow_verify)
    monkeypatch.setattr(users_module, "hash_password", slow_hash)
    gaps: list[float] = []
    stop = asyncio.Event()

    async def ticker():
        last = time.perf_counter()
        while not stop.is_set():
            await asyncio.sleep(0.01)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now

    task = asyncio.create_task(ticker())
    await asyncio.sleep(0.03)
    async with users_db.sessionmaker() as session:
        repo = UserRepository(db_session=session)
        assert await repo.authenticate_user("ops", password) is not None
        assert await repo.change_password("ops", password, new_password())
    stop.set()
    await task

    assert on_loop_thread == [False, False, False]  # login verify, change verify, new hash
    assert max(gaps) < 0.35


async def test_concurrent_wrong_passwords_cannot_exceed_the_limit(users_db, monkeypatch):
    await add_user(users_db, "ops", new_password())
    checks: list[str] = []

    def counting_verify(plain, hashed):
        checks.append(plain)
        time.sleep(0.02)
        return False

    monkeypatch.setattr(users_module, "verify_password", counting_verify)

    results = await asyncio.gather(*(authenticate(users_db, "ops", f"wrong-{i}") for i in range(8)))

    assert results == [None] * 8
    assert len(checks) == UserRepository.MAX_FAILED_ATTEMPTS
    row = await user_row(users_db, "ops")
    assert row.failed == UserRepository.MAX_FAILED_ATTEMPTS
    assert row.locked_until is not None and row.locked_until > datetime.now(UTC)


async def test_fifth_failure_locks_for_fifteen_minutes_and_refuses_the_right_password(
        users_db, monkeypatch):
    assert (UserRepository.MAX_FAILED_ATTEMPTS, UserRepository.LOCKOUT_DURATION_MINUTES) == (5, 15)
    password = new_password()
    await add_user(users_db, "ops", password)
    for attempt in range(5):
        assert await authenticate(users_db, "ops", f"typo-{attempt}") is None

    row = await user_row(users_db, "ops")
    remaining = (row.locked_until - datetime.now(UTC)).total_seconds() / 60
    assert row.failed == 5 and 14 < remaining <= 15

    checks = []
    monkeypatch.setattr(users_module, "verify_password", lambda *a: checks.append(a) or True)
    assert await authenticate(users_db, "ops", password) is None
    assert checks == []  # refused without a password check
    assert (await user_row(users_db, "ops")).failed == 5


async def test_expired_lock_restarts_the_counter_and_accepts_the_right_password(users_db):
    password = new_password()
    expired = datetime.now(UTC) - timedelta(seconds=1)
    await add_user(users_db, "ops", password, failed=5, locked_until=expired)

    assert await authenticate(users_db, "ops", "one-typo") is None
    row = await user_row(users_db, "ops")
    assert row.failed == 1 and row.locked_until is None

    await run_sql(users_db, "UPDATE users SET failed_login_attempts = 5, locked_until = :l"
                            " WHERE username = 'ops'", l=expired)
    assert (await authenticate(users_db, "ops", password)).username == "ops"
    row = await user_row(users_db, "ops")
    assert row.failed == 0 and row.locked_until is None


async def test_wrong_current_password_on_password_change_counts_toward_lockout(users_db):
    password = new_password()
    await add_user(users_db, "ops", password)
    async with users_db.sessionmaker() as session:
        repo = UserRepository(db_session=session)
        for _ in range(5):
            assert await repo.change_password("ops", "wrong-current", new_password()) is False
        row = await user_row(users_db, "ops")
        assert row.failed == 5 and row.locked_until is not None
        assert await repo.change_password("ops", password, new_password()) is False  # locked


# ─────────────────────────────────────────────────────────────────────
# A2-07 — admin script resets in place, never deletes
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def admin_script(users_db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", users_db.url)
    monkeypatch.delenv("REDIS_URL", raising=False)
    # init_db() replaces the module-level engine/sessionmaker; restore after.
    monkeypatch.setattr(db_module, "_engine", db_module._engine)
    monkeypatch.setattr(db_module, "_sessionmaker", db_module._sessionmaker)
    sqlite3.register_adapter(list, json.dumps)  # Postgres binds roles as ARRAY
    spec = importlib.util.spec_from_file_location(
        "create_admin_user_under_test", REPO / "scripts/db/create_admin_user.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    sqlite3.adapters.pop((list, sqlite3.PrepareProtocol), None)


async def test_admin_script_force_resets_the_password_in_place(users_db, admin_script):
    old_password, password = new_password(), new_password()
    locked = datetime.now(UTC) + timedelta(minutes=10)
    user_id = await add_user(users_db, "opsadmin", old_password, failed=5, locked_until=locked)
    await run_sql(users_db, "INSERT INTO watchlists (user_id, name) VALUES (:u, 'core')", u=user_id)
    tokens = await login_after_unlock(users_db, "opsadmin", old_password)

    assert await admin_script.create_admin_user("opsadmin", password, force=True) is True

    row = await user_row(users_db, "opsadmin")
    assert (row.id, row.email, row.roles) == (user_id, "opsadmin@example.test", ["admin", "trader"])
    assert row.failed == 0 and row.locked_until is None and row.is_active
    assert (await run_sql(users_db, "SELECT count(*) FROM watchlists"))[0][0] == 1
    assert await authenticate(users_db, "opsadmin", old_password) is None
    assert (await authenticate(users_db, "opsadmin", password)).id == user_id
    assert await refresh_refusal(tokens.refresh_token) == "refresh_token_revoked"


async def login_after_unlock(db, username, password):
    """Log in once (clearing the seeded lock first), then re-apply the lock."""
    row = await user_row(db, username)
    await run_sql(db, "UPDATE users SET failed_login_attempts = 0, locked_until = NULL"
                      " WHERE username = :u", u=username)
    tokens = await login(db, username, password)
    await run_sql(db, "UPDATE users SET failed_login_attempts = :f, locked_until = :l"
                      " WHERE username = :u", f=row.failed, l=row.locked_until, u=username)
    return tokens


async def test_admin_script_rejects_passwords_bcrypt_would_truncate(users_db, admin_script, capsys):
    old_password = new_password()
    user_id = await add_user(users_db, "opsadmin", old_password)
    too_long = "Aa1!" + "x" * 80  # passes the 12-character minimum

    assert await admin_script.create_admin_user("opsadmin", too_long, force=True) is False

    assert "72 bytes" in capsys.readouterr().err
    assert (await user_row(users_db, "opsadmin")).id == user_id
    assert (await authenticate(users_db, "opsadmin", old_password)).id == user_id


async def test_admin_script_creates_a_new_user_with_a_default_email(users_db, admin_script):
    password = new_password()

    assert await admin_script.create_admin_user("firstadmin", password) is True

    row = await user_row(users_db, "firstadmin")
    assert row.email == "firstadmin@localhost" and row.roles == ["admin", "trader"]
    assert (await authenticate(users_db, "firstadmin", password)).username == "firstadmin"


async def test_admin_script_without_force_leaves_an_existing_user_alone(
        users_db, admin_script, capsys):
    old_password = new_password()
    await add_user(users_db, "opsadmin", old_password)
    before = await user_row(users_db, "opsadmin")

    assert await admin_script.create_admin_user("opsadmin", new_password()) is False

    assert "--force" in capsys.readouterr().err
    assert await user_row(users_db, "opsadmin") == before


async def test_create_user_requires_an_email_before_any_write(users_db):
    async with users_db.sessionmaker() as session:
        with pytest.raises(ValueError, match="email"):
            await UserRepository(db_session=session).create_user("nomail", new_password(), ["admin"])
    assert await user_row(users_db, "nomail") is None


def test_runbook_points_at_the_in_place_reset():
    runbook = (REPO / "docs/setup/AUTHENTICATION.md").read_text()
    assert "scripts/create_admin_user.py" not in runbook
    assert "python scripts/db/create_admin_user.py --username admin --force" in runbook
    assert "unlock_admin.py" not in (REPO / "docs/setup/QUICK_START.md").read_text()


# ─────────────────────────────────────────────────────────────────────
# A1-02 / A6-07 / A1-04 — no credentials in logs
# ─────────────────────────────────────────────────────────────────────


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


@contextlib.contextmanager
def captured(logger_name, level=logging.DEBUG):
    """Capture records of one logger (independent of root/caplog configuration)."""
    target = logging.getLogger(logger_name)
    handler, old_level, old_filters = Capture(), target.level, list(target.filters)
    old_disable = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    target.addHandler(handler)
    target.setLevel(level)
    try:
        yield handler
    finally:
        target.removeHandler(handler)
        target.setLevel(old_level)
        target.filters[:] = old_filters
        logging.disable(old_disable)


def test_socketio_packet_logging_is_off():
    from backend.api import socketio_server

    assert socketio_server.sio.logger.getEffectiveLevel() > logging.INFO
    assert socketio_server.sio.eio.logger.getEffectiveLevel() > logging.INFO


def test_uvicorn_and_engineio_records_do_not_carry_tokens():
    from backend.api import logging_setup

    sentinel = "SENTINEL-" + secrets.token_hex(8)
    with captured("uvicorn.error") as ws, captured("uvicorn.access") as access, \
            captured("engineio.server") as eio:
        logging_setup.install_log_redaction()
        logging.getLogger("uvicorn.error").info(
            '%s - "WebSocket %s" [accepted]', "127.0.0.1:50000",
            f"/api/v1/market-data/ws?token={sentinel}")
        logging.getLogger("uvicorn.error").info(
            '%s - "WebSocket %s" 403', "127.0.0.1:50001", f"/api/v1/scanner/ws?token={sentinel}")
        logging.getLogger("uvicorn.access").info(
            '%s - "%s %s HTTP/%s" %d', "127.0.0.1:50002", "GET",
            f"/api/v1/market-data/ws?symbols=AAPL&token={sentinel}", "1.1", 403)
        logging.getLogger("engineio.server").error(
            "%s: Received packet %s data %s", "sid-1", "MESSAGE", f'0{{"token":"{sentinel}"}}')

    records = ws.records + access.records + eio.records
    assert len(records) == 4
    assert all(sentinel not in r.getMessage() for r in records)
    assert "token=***REDACTED***" in ws.records[0].getMessage()
    assert "symbols=AAPL" in access.records[0].getMessage()
    assert len(access.records[0].args) == 5  # uvicorn's AccessFormatter unpacks five args


def test_configure_api_logging_installs_redaction_even_when_it_skips_the_rest(monkeypatch):
    from backend.api import logging_setup

    monkeypatch.setenv("INTRA_CONFIGURE_STRUCTURED_LOGGING", "0")
    saved = {name: list(logging.getLogger(name).filters) for name in logging_setup.REDACTED_LOGGERS}
    try:
        for name in saved:
            logging.getLogger(name).filters[:] = [
                f for f in saved[name] if not isinstance(f, logging_setup.SecretRedactionFilter)]
        assert logging_setup.configure_api_logging(None) is False
        logging_setup.install_log_redaction()  # idempotent
        for name in saved:
            installed = [f for f in logging.getLogger(name).filters
                         if isinstance(f, logging_setup.SecretRedactionFilter)]
            assert len(installed) == 1
        assert set(logging_setup.REDACTED_LOGGERS) >= {"uvicorn.error", "uvicorn.access"}
    finally:
        for name, filters in saved.items():
            logging.getLogger(name).filters[:] = filters


async def test_blacklist_startup_log_omits_the_redis_password(monkeypatch):
    from backend.api import lifespan
    import redis.asyncio as redis_async

    sentinel = "SENTINEL-" + secrets.token_hex(8)

    class Client:
        async def ping(self):
            return True

    built = []
    monkeypatch.setattr(redis_async, "from_url",
                        lambda url, **kwargs: built.append((url, kwargs)) or Client())
    monkeypatch.setenv("REDIS_URL", f"redis://:{sentinel}@redis:6379/0")
    app = SimpleNamespace(state=SimpleNamespace())

    with captured("backend.api.lifespan", logging.INFO) as log:
        await lifespan._step_token_blacklist(app)

    assert isinstance(app.state.redis, Client)
    text_logged = " ".join(r.getMessage() for r in log.records)
    assert "redis://redis:6379/0" in text_logged and sentinel not in text_logged
    url, kwargs = built[0]
    assert kwargs["socket_timeout"] == kwargs["socket_connect_timeout"] == 1.0


def test_log_scrubber_masks_credentials_in_urls():
    from backend.utils.logger import _scrub_string, scrub_sensitive_data

    sentinel = "SENTINEL-" + secrets.token_hex(8)
    for line in (f"connecting to postgresql+asyncpg://trading_user:{sentinel}@postgres:5432/db",
                 f"backend at redis://:{sentinel}@redis:6379/0",
                 f"open /api/v1/market-data/ws?token={sentinel}&symbols=AAPL"):
        assert sentinel not in _scrub_string(line)
    event_dict = scrub_sensitive_data(None, "info", {"event": f"at redis://:{sentinel}@redis:6379/0"})
    assert sentinel not in event_dict["event"] and "@redis:6379/0" in event_dict["event"]


# ─────────────────────────────────────────────────────────────────────
# A1-03 — bounded token-blacklist Redis lookups (fail open)
# ─────────────────────────────────────────────────────────────────────


def _parse_command(buffer: bytes):
    """Parse one RESP array of bulk strings; None when incomplete."""
    if not buffer.startswith(b"*") or b"\r\n" not in buffer:
        return None
    end = buffer.index(b"\r\n")
    position, args = end + 2, []
    for _ in range(int(buffer[1:end])):
        if not buffer.startswith(b"$", position):
            return None
        line_end = buffer.find(b"\r\n", position)
        if line_end < 0:
            return None
        start = line_end + 2
        stop = start + int(buffer[position + 1:line_end])
        if len(buffer) < stop + 2:
            return None
        args.append(buffer[start:stop])
        position = stop + 2
    return args, position


def _bulk(value):
    return b"$-1\r\n" if value is None else b"$%d\r\n%s\r\n" % (len(value), value)


class RespServer:
    """In-process Redis protocol subset on a Unix socket; stops answering when silent."""

    def __init__(self, *, silent=False):
        self.silent = silent
        self.data: dict[bytes, bytes] = {}
        self._dir = tempfile.mkdtemp(prefix="resp")
        self.path = os.path.join(self._dir, "r.sock")
        self.url = f"unix://{self.path}?db=0"
        self._writers: set = set()

    async def __aenter__(self):
        self._server = await asyncio.start_unix_server(self._handle, path=self.path)
        return self

    async def __aexit__(self, *exc):
        self._server.close()
        for writer in list(self._writers):
            writer.close()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._server.wait_closed(), 2)
        shutil.rmtree(self._dir, ignore_errors=True)

    async def _handle(self, reader, writer):
        self._writers.add(writer)
        buffer = b""
        try:
            while chunk := await reader.read(65536):
                if self.silent:
                    continue
                buffer += chunk
                while (parsed := _parse_command(buffer)) is not None:
                    args, used = parsed
                    buffer = buffer[used:]
                    writer.write(self._reply(args))
                await writer.drain()
        except (ConnectionError, OSError):
            return
        finally:
            self._writers.discard(writer)
            writer.close()

    def _reply(self, args):
        command = args[0].upper()
        if command == b"PING":
            return b"+PONG\r\n"
        if command == b"GET":
            return _bulk(self.data.get(args[1]))
        if command == b"MGET":
            return b"*%d\r\n" % (len(args) - 1) + b"".join(_bulk(self.data.get(k)) for k in args[1:])
        if command == b"SETEX":
            self.data[args[1]] = args[3]
        elif command == b"SET":
            if b"NX" in (a.upper() for a in args[3:]) and args[1] in self.data:
                return b"$-1\r\n"
            self.data[args[1]] = args[2]
        return b"+OK\r\n"


async def _start_blacklist(monkeypatch, server):
    from backend.api import lifespan

    monkeypatch.setenv("REDIS_URL", server.url)
    app = SimpleNamespace(state=SimpleNamespace())
    await asyncio.wait_for(lifespan._step_token_blacklist(app), 10)
    return app


async def _close(client):
    if client is not None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(client.aclose(), 2)


async def test_blacklist_client_has_timeouts_and_fails_open_when_redis_stalls(monkeypatch):
    async with RespServer() as server:
        app = await _start_blacklist(monkeypatch, server)
        client = app.state.redis
        try:
            assert client is not None and security._token_blacklist_redis is client
            kwargs = client.connection_pool.connection_kwargs
            assert kwargs["socket_timeout"] == kwargs["socket_connect_timeout"] == 1.0
            assert await security.is_token_blacklisted("jti-live") is False

            server.silent = True
            started = time.monotonic()
            with captured(security.__name__, logging.ERROR) as log:
                assert await asyncio.wait_for(
                    security.is_token_blacklisted("jti-stalled"), 10) is False
            assert time.monotonic() - started < 3.0
            assert any("Failed to check token blacklist in Redis" in r.getMessage()
                       for r in log.records)

            # Revocations recorded by this process still apply during the stall.
            await asyncio.wait_for(security.blacklist_token("jti-revoked", expires_in=60), 10)
            assert await asyncio.wait_for(security.is_token_blacklisted("jti-revoked"), 10) is True
        finally:
            await _close(client)


async def test_blacklist_startup_gives_up_on_a_redis_that_never_answers(monkeypatch):
    async with RespServer(silent=True) as server:
        started = time.monotonic()
        app = await _start_blacklist(monkeypatch, server)
        assert app.state.redis is None
        assert time.monotonic() - started < 6.0
    assert security._token_blacklist_redis is None


async def test_socketio_tick_broadcast_is_bounded_when_redis_stalls(monkeypatch):
    from backend.api import socketio_server as server_mod

    fake = FakeSio()
    monkeypatch.setattr(server_mod, "sio", fake)
    monkeypatch.setattr(server_mod, "client_subscriptions", {"a": {"organism"}})
    monkeypatch.setattr(server_mod, "topic_subscribers", {"organism": {"a"}})
    fake.values["a"] = {"authenticated": True, "user_id": "ops", "roles": ["admin"],
                        "expires_at": time.time() + 600, "token_id": "jti-a",
                        "session_id": "sid-a", "credential_fingerprint": "cfp-a"}
    async with RespServer() as server:
        app = await _start_blacklist(monkeypatch, server)
        try:
            server.silent = True
            started = time.monotonic()
            await asyncio.wait_for(
                server_mod.broadcast_to_topic("organism", "organism_tick", {"tick": 1}), 10)
            assert time.monotonic() - started < 3.0
            assert fake.emits == [("organism_tick", {"tick": 1}, {"to": "a"})]
        finally:
            await _close(app.state.redis)


# ─────────────────────────────────────────────────────────────────────
# Socket.IO access-token validation follows the same revocations
# ─────────────────────────────────────────────────────────────────────


class FakeSio:
    def __init__(self):
        self.values: dict[str, dict] = {}
        self.rooms: list = []
        self.emits: list = []

    @contextlib.asynccontextmanager
    async def session(self, sid):
        yield self.values.setdefault(sid, {})

    async def disconnect(self, sid):
        self.values.pop(sid, None)

    async def enter_room(self, sid, room):
        self.rooms.append((sid, room))

    async def emit(self, event_name, data, **kwargs):
        self.emits.append((event_name, data, kwargs))


async def test_socketio_sessions_follow_logout_and_password_change(users_db, monkeypatch):
    from backend.api import socketio_server as server_mod

    fake = FakeSio()
    monkeypatch.setattr(server_mod, "sio", fake)
    monkeypatch.setattr(server_mod, "client_subscriptions", {})
    monkeypatch.setattr(server_mod, "topic_subscribers", {})
    password, replacement = new_password(), new_password()
    await add_user(users_db, "ops", password)

    tokens = await login(users_db, "ops", password)
    assert await server_mod.connect("a", {}, {"token": tokens.access_token}) is True
    await server_mod.subscribe("a", {"topic": "organism"})
    async with users_db.sessionmaker() as session:
        assert await UserRepository(db_session=session).change_password("ops", password, replacement)
    fake.emits.clear()
    await server_mod.broadcast_to_topic("organism", "organism_tick", {"tick": 1})
    assert fake.emits == [] and "a" not in server_mod.client_subscriptions

    first = await login(users_db, "ops", replacement)
    second = await refresh(first.refresh_token)
    await auth.logout(http_request("/api/v1/auth/logout", second.access_token, "POST"))
    assert await server_mod.connect("b", {}, {"token": first.access_token}) is False
