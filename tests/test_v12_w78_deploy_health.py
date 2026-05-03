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
