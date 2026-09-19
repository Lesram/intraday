"""V9 / Wave-42 (2026-05-03): behavioral tests for JWT lifecycle.

Locks the regressions for:
- AA3-1 (HIGH): /auth/logout calls blacklist_token; get_current_user
  rejects blacklisted jti.
- AA3-2 (HIGH): decode_token rejects token_type != "access" on
  resource paths; create_access_token now sets token_type="access"
  explicitly so the gate works.
- AA3-3 (MEDIUM): /token/refresh blacklists the redeemed jti before
  issuing the new pair (single-use).

Run with: ./venv/bin/python -m pytest tests/test_wave42_fixes.py -v
"""
from __future__ import annotations

import inspect

import pytest


# ─────────────────────────────────────────────────────────────────────
# AA3-1 — logout blacklists JWT
# ─────────────────────────────────────────────────────────────────────


def test_aa3_1_logout_calls_blacklist_token():
    """The /auth/logout handler must call blacklist_token on the
    presented bearer token's jti."""
    from backend.api.routes import auth
    src = inspect.getsource(auth.logout)
    assert "blacklist_token" in src, (
        "AA3-1 regression: /auth/logout no longer calls blacklist_token. "
        "Stolen tokens remain valid for full TTL after logout."
    )
    assert "AA3-1" in src, "AA3-1 marker missing from logout handler"


def test_aa3_1_get_current_user_consults_blacklist():
    """get_current_user must call is_token_blacklisted on the jti."""
    from backend.infra import security
    src = inspect.getsource(security.get_current_user)
    assert "is_token_blacklisted" in src, (
        "AA3-1 regression: get_current_user no longer consults blacklist. "
        "Blacklisted tokens would still authenticate."
    )
    assert "token_revoked" in src, (
        "AA3-1 regression: blacklist hit no longer raises 401 "
        "with token_revoked detail."
    )


# ─────────────────────────────────────────────────────────────────────
# AA3-2 — token_type access gate
# ─────────────────────────────────────────────────────────────────────


def test_aa3_2_decode_token_rejects_non_access_token_type():
    """decode_token must reject any token whose token_type is not
    "access" (refresh tokens were previously accepted as access)."""
    from backend.infra import security
    src = inspect.getsource(security.decode_token)
    assert "token_type" in src, (
        "AA3-2 regression: decode_token no longer checks token_type. "
        "Refresh tokens (7-day TTL) accepted as access on /auth/me etc."
    )
    assert "invalid_token_type" in src, (
        "AA3-2 regression: token_type mismatch no longer raises 401."
    )


def test_aa3_2_create_access_token_sets_token_type():
    """create_access_token must include token_type="access" so the
    decode_token gate has something to compare against."""
    from backend.infra import security
    src = inspect.getsource(security.create_access_token)
    assert '"token_type": "access"' in src, (
        "AA3-2 regression: create_access_token no longer sets "
        "token_type=\"access\". The decode-time gate is toothless."
    )


# ─────────────────────────────────────────────────────────────────────
# AA3-3 — refresh single-use
# ─────────────────────────────────────────────────────────────────────


def test_aa3_3_refresh_blacklists_redeemed_jti():
    """/token/refresh must blacklist the redeemed refresh-token jti
    so it can't be reused (single-use)."""
    from backend.api.routes import auth
    src = inspect.getsource(auth)
    # Find the refresh handler.
    assert "AA3-3" in src, "AA3-3 marker missing from refresh handler"
    assert "is_token_blacklisted" in src and "blacklist_token" in src, (
        "AA3-3 regression: refresh handler no longer enforces single-use. "
        "Old refresh tokens stay valid forever."
    )


def test_aa3_3_refresh_replay_returns_401():
    """Code path: if is_token_blacklisted returns True for old_jti,
    handler must raise 401 with refresh_token_already_used detail."""
    from backend.api.routes import auth
    src = inspect.getsource(auth)
    assert "refresh_token_already_used" in src, (
        "AA3-3 regression: refresh-replay path no longer raises with "
        "refresh_token_already_used detail."
    )
