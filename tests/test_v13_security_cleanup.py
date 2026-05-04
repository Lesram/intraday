from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from backend.infra.security import AuthenticatedUser


def _admin_dependency_calls() -> list:
    from backend.api.routes.audit import router

    calls = []
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        for dependency in route.dependant.dependencies:
            if getattr(dependency.call, "required_roles", None) == ["admin"]:
                calls.append(dependency.call)
                break
        else:
            pytest.fail(f"{route.path} is missing an admin role dependency")
    assert len(calls) >= 7
    return calls


@pytest.mark.asyncio
async def test_aa2_new_1_audit_admin_dependencies_reject_trader_role():
    """AA2-NEW-1: audit route dependencies must enforce admin-only access."""
    trader = AuthenticatedUser(
        username="security-test-trader",
        roles=["trader"],
        token_id="tok-trader",
    )
    admin = AuthenticatedUser(
        username="security-test-admin",
        roles=["admin"],
        token_id="tok-admin",
    )

    for dependency_call in _admin_dependency_calls():
        with pytest.raises(HTTPException) as exc_info:
            await dependency_call(trader)
        assert exc_info.value.status_code == 403

        accepted = await dependency_call(admin)
        assert accepted.username == "security-test-admin"


def test_aa2_new_2_verify_token_malformed_claims_raise_401(monkeypatch):
    """AA2-NEW-2: malformed signed claims must be auth failure, not 500."""
    import backend.infra.security as security

    monkeypatch.setattr(
        security,
        "decode_token",
        lambda token: {
            "sub": "malformed-user",
            "iss": security.JWT_ISSUER,
            "aud": security.JWT_AUDIENCE,
            "exp": 4_102_444_800,
            "iat": 1_767_225_600,
            "jti": "malformed-jti",
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        security.verify_token("signed-but-malformed")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "invalid_token"


def test_aa3_2_decode_token_rejects_refresh_token_as_access():
    """AA3-2: refresh tokens must not authenticate access-token endpoints."""
    from backend.infra.security import create_refresh_token, decode_token

    refresh_token = create_refresh_token("refresh-user", ["admin"])

    with pytest.raises(HTTPException) as exc_info:
        decode_token(refresh_token)

    assert exc_info.value.status_code == 401
