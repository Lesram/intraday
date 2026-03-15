"""Legacy auth compatibility helpers.

This module preserves historical import paths used by older tests and tools:
`backend.api.auth.{create_access_token,hash_password,verify_password}`.

NOTE: Production auth uses `backend.infra.security` which reads
``settings.security.secret_key`` / ``SECURITY_JWT_SECRET``.
This legacy module checks ``JWT_SECRET_KEY`` then ``JWT_SECRET`` for
backwards compatibility with older .env files and test fixtures.

In development (APP_ENVIRONMENT=development), a hard-coded dev-only secret
is used as a last resort so that tests can run without explicit env config.
In all other environments, a missing secret raises RuntimeError.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from backend.infra.security import hash_password, verify_password

_logger = logging.getLogger(__name__)

_FALLBACK_SECRET = "dev_only_secret_" + "do_not_use_in_production"


def _get_jwt_secret() -> str:
    """Return JWT secret, checking JWT_SECRET_KEY then JWT_SECRET.

    Falls back to a hard-coded dev-only value **only** when
    APP_ENVIRONMENT is ``development`` (the default).
    """
    secret = os.getenv("JWT_SECRET_KEY") or os.getenv("JWT_SECRET")
    if secret:
        return secret
    env = os.getenv("APP_ENVIRONMENT", "development")
    if env == "development":
        _logger.debug("Using dev-only fallback JWT secret (APP_ENVIRONMENT=development)")
        return _FALLBACK_SECRET
    raise RuntimeError(
        "JWT_SECRET_KEY (or JWT_SECRET) environment variable is required "
        "when APP_ENVIRONMENT != 'development'"
    )


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create JWT access token using legacy signature.

    This wrapper intentionally accepts ``data`` and ``expires_delta`` to remain
    compatible with existing tests/importers.
    """
    payload = dict(data)
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=60))
    payload.update({"exp": expire})
    secret = _get_jwt_secret()
    return jwt.encode(payload, secret, algorithm="HS256")


__all__ = ["create_access_token", "hash_password", "verify_password"]
