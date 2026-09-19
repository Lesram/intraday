"""V11 / Wave-67 (2026-05-03): URGENT — AA5-1 broken JWT decode.

Wave-47 (V10 cleanup) passed `leeway=JWT_CLOCK_SKEW` as a top-level
kwarg to `jwt.decode()` (PyJWT-style).  python-jose 3.5 — what's
actually installed — only accepts leeway INSIDE the options dict.
The TypeError was swallowed by `decode_token`'s catch-all and
returned as 401 invalid_token.  ALL JWT-authenticated endpoints
were broken in the wave-50-66 image.

V11 AA5 caught this in production; wave-67 fixes by moving leeway
into options.  This test BEHAVIORALLY decodes a valid token to
prove the path doesn't raise.

The wave-47 regression test was a SOURCE GREP that asserted the
literal string "leeway=JWT_CLOCK_SKEW" — passed despite breaking
production.  Lesson: behavioral tests beat literal-string asserts.

Run with: ./venv/bin/python -m pytest tests/test_wave67_fixes.py -v
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta


def test_aa5_1_jwt_decode_actually_succeeds_with_valid_token():
    """Mint a valid JWT and decode it.  Passes only if leeway is inside
    `options` dict (python-jose API) not as a top-level kwarg
    (PyJWT API)."""
    from backend.infra.security import (
        create_access_token, decode_token,
    )

    token = create_access_token(
        sub="testuser@example.com",
        roles=["user"],
        expires_minutes=5,
    )
    # If decode_token still uses the broken kwarg form, this raises
    # HTTPException(401, "invalid_token") via the catch-all.  After
    # wave-67 the leeway goes into the options dict and decoding
    # succeeds.
    payload = decode_token(token)
    assert payload["sub"] == "testuser@example.com"
    assert "iat" in payload
    assert "exp" in payload
    assert payload.get("token_type") == "access"


def test_aa5_1_marker_present():
    import inspect
    from backend.infra import security
    src = inspect.getsource(security.decode_token)
    assert "AA5-1" in src or "Wave-67" in src, "AA5-1 fix marker missing"
    assert '"leeway": JWT_CLOCK_SKEW' in src, (
        "AA5-1 regression: leeway is not inside options dict; "
        "python-jose will raise TypeError again."
    )
    # And the broken kwarg form must be gone (strip comment lines first
    # so the wave-67 marker comment doesn't trip the assertion on
    # itself).
    code_only = "\n".join(
        line for line in src.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "leeway=JWT_CLOCK_SKEW" not in code_only, (
        "AA5-1 regression: PyJWT-style top-level kwarg restored in code."
    )
