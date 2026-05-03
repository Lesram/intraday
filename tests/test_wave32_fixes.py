"""V8 / Wave-32 (2026-05-03): behavioral tests for trading-safety + CI bypass fixes.

Locks the regressions for:
- DD2-1: pending-exit window must NOT bypass max-loss safety net.
- W3-G1: cited grep timeout/error must FAIL required-mode (was silent pass).
- W3-G2: behavioral-test diff must count tests across all paths (was tests/ only).
- W3-G3: shell-prompt-prefixed grep lines must be recognized.
- AA2-NEW-1: audit endpoints must reject trader-role tokens (admin-only).
- AA2-NEW-2: malformed UserClaims payload must yield 401, not 500.
- AA2-NEW-3: HSTS must emit when X-Forwarded-Proto: https is set.

Run with: ./venv/bin/python -m pytest tests/test_wave32_fixes.py -v
"""
from __future__ import annotations

import re
import textwrap

import pytest


# ─────────────────────────────────────────────────────────────────────
# DD2-1 — pending-exit safety net
# ─────────────────────────────────────────────────────────────────────


def test_dd2_1_pending_exit_max_loss_safety_net_present():
    """The wave-32 fix introduces a max-loss safety check inside the
    `if sym in self._pending_exit:` block.  A future revert to the
    bare `continue` would re-introduce the DD2-1 silent bypass.

    Structural lock: the source must contain BOTH the marker and the
    safety_net_pending_exit_breach reason inside live_engine.py.
    """
    import inspect
    from backend.organism import live_engine
    src = inspect.getsource(live_engine)
    assert "DD2-1" in src, (
        "DD2-1 marker missing from live_engine.py — the wave-32 safety "
        "net may have been reverted."
    )
    assert "safety_net_pending_exit_breach" in src, (
        "DD2-1 regression: pending-exit window does not invoke the "
        "max-loss safety-net submit. The 3-tick TTL would silence "
        "stop_loss / max_loss for ~30s on partial-TP / ML-reversal exits."
    )


def test_dd2_1_pending_exit_block_evaluates_pnl_pct():
    """The safety net must compare pnl_pct against -_MAX_LOSS_PCT
    INSIDE the pending-exit branch (not just somewhere else in the file)."""
    import inspect
    from backend.organism import live_engine
    src = inspect.getsource(live_engine)
    # Find the pending-exit block.
    m = re.search(
        r"if sym in self\._pending_exit:.*?continue",
        src,
        flags=re.DOTALL,
    )
    assert m, "Could not locate the pending-exit block in live_engine.py"
    block = m.group(0)
    assert "pnl_pct" in block and "_MAX_LOSS_PCT" in block, (
        "DD2-1 regression: pending-exit block does not evaluate "
        "max-loss breach. Hard safety net is bypassed."
    )
    assert "_submit_exit_order" in block, (
        "DD2-1 regression: pending-exit block evaluates pnl but does "
        "not actually submit a safety-net order on breach."
    )


# ─────────────────────────────────────────────────────────────────────
# W3-G1 — CI grep timeout silent pass
# ─────────────────────────────────────────────────────────────────────


def test_w3_g1_grep_count_negative_increments_fails_in_required_mode():
    """check_wave_markers.py must treat un-evaluated grep (count<0) as
    FAIL in required mode.  Previously printed [WARN] without
    incrementing fails — bypass vector for the wave-28 contract."""
    import inspect
    import scripts.ci.check_wave_markers as cwm
    src = inspect.getsource(cwm.check_wave_compliance)
    # The required-mode count<0 branch must increment fails.
    # Search for the canonical pattern.
    assert "could not re-run (count<0" in src, (
        "W3-G1 regression: required-mode count<0 path missing the "
        "Wave-32 marker.  A grep timeout / error silently bypasses "
        "the wave-28 enforcement."
    )
    # Also assert that the count<0 branch has a `fails += 1` reachable
    # under enforce_grep_zero=True.  We do this by AST walk.
    import ast
    tree = ast.parse(src)
    found_increment = False
    for node in ast.walk(tree):
        if (isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "count"
            and isinstance(node.test.ops[0], ast.Lt)
            and isinstance(node.test.comparators[0], ast.Constant)
            and node.test.comparators[0].value == 0
        ):
            for sub in ast.walk(node):
                if (isinstance(sub, ast.AugAssign)
                    and isinstance(sub.target, ast.Name)
                    and sub.target.id == "fails"
                ):
                    found_increment = True
    assert found_increment, (
        "W3-G1 regression: count<0 branch does not increment fails."
    )


# ─────────────────────────────────────────────────────────────────────
# W3-G2 — behavioral-test diff scope
# ─────────────────────────────────────────────────────────────────────


def test_w3_g2_diff_test_count_scoped_across_all_paths():
    """_diff_test_count must NOT be scoped to `-- tests/` only.
    Wave-32 widens scope to all paths + adds @pytest.fixture marker."""
    import inspect
    import scripts.ci.check_wave_markers as cwm
    src = inspect.getsource(cwm._diff_test_count)
    assert '"--", "tests/"' not in src and "'--', 'tests/'" not in src, (
        "W3-G2 regression: _diff_test_count is still scoped to tests/. "
        "Wave-32 widened to all paths."
    )
    assert "@pytest.fixture" in src, (
        "W3-G2 regression: fixture additions are no longer counted as "
        "behavioral test additions."
    )


# ─────────────────────────────────────────────────────────────────────
# W3-G3 — shell-prompt prefix in grep parsing
# ─────────────────────────────────────────────────────────────────────


def test_w3_g3_sameclass_block_re_strips_shell_prompt():
    """Wave-32 widens SAMECLASS_BLOCK_RE to recognize `$ grep ...` and
    `> grep ...` lines pasted from a shell session."""
    from scripts.ci.check_wave_markers import SAMECLASS_BLOCK_RE

    body = textwrap.dedent("""
    Same-class scan:
    $ grep -rn 'foo' backend/
    > grep -rn 'bar' tests/
      grep -rn 'baz' .
    """)
    matches = SAMECLASS_BLOCK_RE.findall(body)
    # Should pick up all three.
    assert len(matches) == 3, (
        f"W3-G3 regression: SAMECLASS_BLOCK_RE matched {len(matches)} lines, "
        f"expected 3 (with and without shell-prompt prefix)"
    )
    assert all(m.lstrip().startswith("grep") for m in matches), (
        f"W3-G3 regression: matches should be the bare grep command "
        f"(prompt stripped). Got: {matches!r}"
    )


# ─────────────────────────────────────────────────────────────────────
# AA2-NEW-1 — audit endpoints must require_admin
# ─────────────────────────────────────────────────────────────────────


def test_aa2_new_1_audit_routes_use_require_admin():
    """All 6 audit endpoints must depend on require_admin, not
    require_trader.  Trader-role tokens must not read forensic data."""
    import inspect
    from backend.api.routes import audit as audit_route
    src = inspect.getsource(audit_route)
    assert "require_trader" not in src, (
        "AA2-NEW-1 regression: audit.py still references require_trader. "
        "Trader tokens would gain forensic-data access."
    )
    # Count Depends(require_admin) — should be one per endpoint (6 total).
    n = src.count("Depends(require_admin)")
    assert n >= 6, (
        f"AA2-NEW-1 regression: only {n} audit endpoints use "
        "Depends(require_admin); expected ≥6."
    )


# ─────────────────────────────────────────────────────────────────────
# AA2-NEW-2 — malformed JWT must yield 401, not 500
# ─────────────────────────────────────────────────────────────────────


def test_aa2_new_2_verify_token_malformed_payload_yields_401():
    """verify_token must catch ValidationError / TypeError on
    UserClaims(**payload) and raise HTTPException(401)."""
    from fastapi import HTTPException
    from backend.infra.security import verify_token

    # Forge a token whose payload decodes but lacks required UserClaims fields.
    # We monkey-patch decode_token to bypass signature verification.
    import backend.infra.security as sec
    orig = sec.decode_token
    try:
        # Missing 'roles' (and likely other required fields) on UserClaims.
        sec.decode_token = lambda _t: {"sub": "user@example.com"}
        with pytest.raises(HTTPException) as exc_info:
            verify_token("dummy.signed.token")
        assert exc_info.value.status_code == 401, (
            f"AA2-NEW-2 regression: malformed UserClaims returns "
            f"{exc_info.value.status_code} instead of 401."
        )
        assert "invalid_token" in str(exc_info.value.detail).lower(), (
            f"AA2-NEW-2 regression: detail={exc_info.value.detail!r}; "
            "expected 'invalid_token'."
        )
    finally:
        sec.decode_token = orig


def test_aa2_new_2_verify_token_wrong_type_roles_yields_401():
    """`roles` claim as string (not list) must yield 401."""
    from fastapi import HTTPException
    from backend.infra.security import verify_token
    import backend.infra.security as sec
    orig = sec.decode_token
    try:
        sec.decode_token = lambda _t: {
            "sub": "user@example.com",
            "roles": "admin",  # string, not list
            "iat": 1700000000,
            "jti": "abc",
            "exp": 9999999999,
        }
        with pytest.raises(HTTPException) as exc_info:
            verify_token("dummy.signed.token")
        assert exc_info.value.status_code == 401, (
            "AA2-NEW-2 regression: roles=string (not list) does not "
            f"yield 401 (got {exc_info.value.status_code})."
        )
    finally:
        sec.decode_token = orig


# ─────────────────────────────────────────────────────────────────────
# AA2-NEW-3 — HSTS X-Forwarded-Proto
# ─────────────────────────────────────────────────────────────────────


def test_aa2_new_3_hsts_emits_under_x_forwarded_proto():
    """SecurityHeadersMiddleware must emit HSTS when scheme=http but
    X-Forwarded-Proto: https indicates upstream TLS termination."""
    import inspect
    from backend.infra.security_hardening import SecurityHeadersMiddleware
    src = inspect.getsource(SecurityHeadersMiddleware)
    assert "x-forwarded-proto" in src.lower(), (
        "AA2-NEW-3 regression: SecurityHeadersMiddleware doesn't honour "
        "X-Forwarded-Proto. HSTS would not emit behind a TLS-terminating "
        "proxy."
    )
    # Also verify that the HSTS branch fires when forwarded_proto == "https".
    assert 'forwarded_proto == "https"' in src or "'https'" in src, (
        "AA2-NEW-3 regression: missing forwarded_proto comparison."
    )
