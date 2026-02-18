"""Legacy auth compatibility helpers.

This module preserves historical import paths used by older tests and tools:
`backend.api.auth.{create_access_token,hash_password,verify_password}`.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from backend.infra.security import hash_password, verify_password


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
    secret = os.getenv("JWT_SECRET", "test_secret")
    return jwt.encode(payload, secret, algorithm="HS256")


__all__ = ["create_access_token", "hash_password", "verify_password"]
