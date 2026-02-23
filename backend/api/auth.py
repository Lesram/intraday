"""Legacy auth compatibility helpers.

This module preserves historical import paths used by older tests and tools:
`backend.api.auth.{create_access_token,hash_password,verify_password}`.

NOTE: Production auth uses `backend.infra.security` which requires JWT_SECRET_KEY
or raises ValueError. This module is only imported by tests.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from backend.infra.security import hash_password, verify_password

_logger = logging.getLogger(__name__)

_FALLBACK_SECRET = "test_secret_NOT_FOR_PRODUCTION"


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
    secret = os.getenv("JWT_SECRET")
    if not secret:
        secret = _FALLBACK_SECRET
        _logger.warning(
            "JWT_SECRET not set — using fallback. "
            "This module is for tests only; production must use backend.infra.security."
        )
    return jwt.encode(payload, secret, algorithm="HS256")


__all__ = ["create_access_token", "hash_password", "verify_password"]
