"""V12 W78: behavioral tests for /api/v1/health/deploy.

Closes EXT-8 (no deploy verification endpoint).  Operators couldn't
detect "container running OLD image while host code is current"
without ssh'ing in — exactly the V11 wave-47 JWT regression failure
mode.

Run with:
    ./venv/bin/python -m pytest tests/test_v12_w78_deploy_health.py -v
"""
from __future__ import annotations

import asyncio


def test_w78_endpoint_returns_all_required_fields():
    """The endpoint payload must carry the 7 deploy-state fields."""
    from backend.api.routes.deploy_health import deploy_health
    payload = asyncio.run(deploy_health())
    required = {
        "source_sha", "migration_head", "build_time", "image_sha",
        "runtime_config_hash", "container_hostname", "app_environment",
    }
    missing = required - set(payload.keys())
    assert not missing, f"deploy_health missing fields: {missing}"


def test_w78_runtime_config_hash_changes_when_risk_cap_env_changes(monkeypatch):
    """The runtime_config_hash must DIFFER when ORGANISM_DRAWDOWN_KILL_PCT
    changes — operators rely on this to detect risk-cap drift across
    deploys."""
    from backend.api.routes.deploy_health import _runtime_config_hash
    monkeypatch.setenv("ORGANISM_DRAWDOWN_KILL_PCT", "0.05")
    h1 = _runtime_config_hash()
    monkeypatch.setenv("ORGANISM_DRAWDOWN_KILL_PCT", "0.10")
    h2 = _runtime_config_hash()
    assert h1 != h2, (
        "EXT-8 regression: runtime_config_hash insensitive to risk-cap "
        "env changes — operators wouldn't detect cap drift between deploys"
    )


def test_w78_container_hostname_is_resolvable():
    """``container_hostname`` is real (non-empty); can be used by ops
    to identify which container produced the response."""
    from backend.api.routes.deploy_health import deploy_health
    payload = asyncio.run(deploy_health())
    assert isinstance(payload["container_hostname"], str)
    assert len(payload["container_hostname"]) > 0


def test_w78_source_sha_resolves_or_returns_unknown(monkeypatch):
    """When ``GIT_SHA`` env is set, endpoint reports it; otherwise it
    falls back to a git-resolved SHA or ``"unknown"``.  Behavioral:
    set the env, hit the resolver, observe."""
    from backend.api.routes.deploy_health import _resolve_git_sha
    monkeypatch.setenv("GIT_SHA", "deadbeef" * 5)
    assert _resolve_git_sha() == "deadbeef" * 5
    # Without env, falls through to git CLI or "unknown".
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("VCS_SHA", raising=False)
    sha = _resolve_git_sha()
    # Either a real 40-char SHA or "unknown" — both are correct.
    assert sha == "unknown" or len(sha) >= 7


def test_w78_endpoint_mounted_under_protected_v1():
    """``/api/v1/health/deploy`` must be registered by the FastAPI app."""
    from backend.api.factory import create_app
    app = create_app()
    paths = {r.path for r in app.routes}
    assert "/api/v1/health/deploy" in paths, (
        f"V12 W78 regression: /api/v1/health/deploy not mounted. "
        f"Health paths: {[p for p in paths if p.startswith('/api/v1/health')]}"
    )


def test_w78_endpoint_does_not_leak_secrets():
    """The endpoint must NOT include credentials, tokens, or DB
    connection strings in its output."""
    from backend.api.routes.deploy_health import deploy_health
    payload = asyncio.run(deploy_health())
    serialized = str(payload).lower()
    forbidden = ("password", "secret", "api_key", "postgres://",
                 "mysql://", "alpaca_secret", "bearer ")
    for bad in forbidden:
        assert bad not in serialized, (
            f"EXT-8 regression: deploy endpoint leaks {bad!r} in response"
        )


def test_w78_migration_head_resolves_to_string():
    """``migration_head`` must always be a string (never None) — even
    when DB is unreachable, returns ``"unknown"``."""
    from backend.api.routes.deploy_health import _resolve_migration_head
    head = _resolve_migration_head()
    assert isinstance(head, str)
    assert len(head) > 0


def test_w83_migration_head_translates_asyncpg_url(monkeypatch):
    """V12 W83 (post-rebuild verification): the migration_head resolver
    must translate ``postgresql+asyncpg://`` URLs to a sync-compatible
    scheme.  Pre-W83 it always raised because sqlalchemy.create_engine
    (sync) doesn't accept an async-only driver — endpoint reported
    ``migration_head=unknown`` even with a healthy DB.

    Behavioral: set DATABASE_URL to a fake asyncpg URL, monkeypatch
    create_engine to capture the URL the resolver passed, assert it's
    been translated."""
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://user:pw@host:5432/db",
    )
    captured: dict[str, str] = {}

    def _fake_engine(url, **_kw):
        captured["url"] = str(url)

        class _Conn:
            def __enter__(self_):
                return self_

            def __exit__(self_, *_a):
                return False

            def execute(self_, _q):
                # Pretend the row exists so the resolver returns a
                # non-"unknown" value.
                class _Row:
                    def first(self_inner):
                        return ("test_head_value",)
                return _Row()

        class _Engine:
            def connect(self_):
                return _Conn()

            def dispose(self_):
                pass

        return _Engine()

    import sqlalchemy
    monkeypatch.setattr(sqlalchemy, "create_engine", _fake_engine)
    # Also patch the imported reference inside the module.
    from backend.api.routes import deploy_health as dh
    monkeypatch.setattr(dh, "_resolve_migration_head", dh._resolve_migration_head)

    head = dh._resolve_migration_head()
    # The resolver should have called create_engine with a sync URL,
    # not the asyncpg one.
    assert "+asyncpg" not in captured.get("url", ""), (
        f"V12 W83 regression: asyncpg URL leaked to sync engine: "
        f"{captured.get('url', '')}"
    )
    assert captured.get("url", "").startswith("postgresql://"), (
        f"V12 W83 regression: URL not translated to plain postgresql:// — "
        f"got {captured.get('url', '')!r}"
    )
    assert head == "test_head_value"
