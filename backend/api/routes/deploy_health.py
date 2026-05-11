"""V12 W78 (EXT-8): /api/v1/health/deploy — deploy state verification.

External auditor recommendation #4: "Add a deploy verification
endpoint or startup log containing source SHA, migration head,
runtime config snapshot hash, and container build time."

V11 wave-47 JWT regression went undetected for ~24h partly because
operators couldn't tell at-a-glance whether the running container
matched the latest deploy.  This endpoint exposes:

- ``source_sha``: git HEAD captured at build time (env GIT_SHA), or
  resolved from ``git rev-parse HEAD`` if running from source tree.
- ``migration_head``: current alembic head per the database — the
  most operationally important version skew indicator.
- ``build_time``: container image build timestamp (env BUILD_TIME).
- ``image_sha``: container image digest (env IMAGE_SHA).
- ``runtime_config_hash``: stable hash of the resolved settings —
  catches "build is current but config changed" cases.
- ``container_hostname``: ``socket.gethostname()`` for fleet ops.

Auth: protected (mounted under /api/v1).
"""
from __future__ import annotations

import os
import socket
from typing import Any

from fastapi import APIRouter, Depends

from backend.infra.runtime_identity import resolve_git_sha, runtime_config_hash
from backend.infra.security import AuthenticatedUser, require_admin


router = APIRouter(prefix="/health", tags=["Health"])

_resolve_git_sha = resolve_git_sha
_runtime_config_hash = runtime_config_hash


def _resolve_migration_head() -> str:
    """Read the migration HEAD from the running DB.

    Best-effort: if the DB layer isn't initialized yet (early startup),
    return ``"unknown"`` rather than 500.

    V12 W83 (post-rebuild verification): translate asyncpg URLs to a
    sync driver before opening the engine.  The app's DATABASE_URL is
    typically ``postgresql+asyncpg://...`` for the async runtime, but
    SQLAlchemy ``create_engine`` (sync) needs ``postgresql://`` or
    ``postgresql+psycopg2://``.  Without this translation the resolver
    raised on every call — endpoint reported migration_head=unknown
    even with a healthy DB.
    """
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import SQLAlchemyError
        from backend.config import get_settings
        s = get_settings()
        url = getattr(s, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")
        if not url:
            return "unknown"
        # Translate async-only schemes to a sync-compatible scheme.
        for async_prefix in ("postgresql+asyncpg://", "postgresql+psycopg_async://"):
            if url.startswith(async_prefix):
                url = "postgresql://" + url[len(async_prefix):]
                break
        # Sync engine for a one-shot read.
        engine = create_engine(url, future=True)
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                ).first()
                return row[0] if row else "unknown"
        finally:
            engine.dispose()
    except (SQLAlchemyError, OSError, ImportError):
        return "unknown"


@router.get("/deploy")
async def deploy_health(
    _current_user: AuthenticatedUser = Depends(require_admin),
) -> dict[str, Any]:
    """V12 W78 (EXT-8): deploy state — source SHA + migration head +
    build time + runtime config hash + image SHA + container hostname.

    Always returns 200 (informational).  Operators can compare across
    fleet members to detect skew.
    """
    return {
        "source_sha": resolve_git_sha(),
        "migration_head": _resolve_migration_head(),
        "build_time": os.environ.get("BUILD_TIME", "unknown"),
        "image_sha": os.environ.get("IMAGE_SHA", "unknown"),
        "runtime_config_hash": runtime_config_hash(),
        "container_hostname": socket.gethostname(),
        "app_environment": os.environ.get("APP_ENVIRONMENT", "unknown"),
    }
