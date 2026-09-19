"""V11 / Wave-68 (2026-05-03): URGENT deploy-gate security closures.

Locks regressions for:
- AAA-F1 (HIGH): /test/http-* debug endpoints no longer registered in
  paper image. Gate now requires BOTH dev/local env AND explicit
  EXPOSE_TEST_ERROR_ENDPOINTS=1 opt-in.
- AAA-F2 (HIGH): orders.py require_trader actually enforces roles.
  Self-registered users (default ["user"]) can no longer place orders.
- CCC-2 (P0/Critical): paper compose explicitly wires drawdown_kill +
  daily_max_loss + max_notional so a missing .env doesn't silently
  disable risk caps.

Run with: ./venv/bin/python -m pytest tests/test_wave68_fixes.py -v
"""
from __future__ import annotations

import inspect
import os


def test_aaa_f1_debug_endpoints_gated():
    from backend.api import errors
    src = inspect.getsource(errors)
    assert "AAA-F1" in src, "AAA-F1 marker missing"
    assert "EXPOSE_TEST_ERROR_ENDPOINTS" in src, (
        "AAA-F1 regression: explicit opt-in env var removed; debug "
        "endpoints would re-expose in paper image."
    )


def test_aaa_f1_default_router_is_empty_stub():
    """Without EXPOSE_TEST_ERROR_ENDPOINTS=1, the imported router has no /http-* paths."""
    # Set env so the gate's both-conditions-must-hold evaluates as we test.
    # Default in tests: var unset → empty stub.
    if "EXPOSE_TEST_ERROR_ENDPOINTS" in os.environ:
        del os.environ["EXPOSE_TEST_ERROR_ENDPOINTS"]
    # Re-import to pick up env state.
    import importlib
    import backend.api.errors as _errors
    importlib.reload(_errors)
    paths = {r.path for r in _errors.router.routes}
    # The stub router has no /http-* paths.
    assert not any(p.endswith("/http-401") for p in paths)
    assert not any(p.endswith("/http-500") for p in paths)


def test_aaa_f2_orders_require_trader_enforces_roles():
    from backend.api.routes.orders import require_trader
    from fastapi import HTTPException

    class _UserNoRole:
        roles = ["user"]
        username = "u"

    class _TraderUser:
        roles = ["trader"]
        username = "t"

    class _AdminUser:
        roles = ["admin"]
        username = "a"

    # User-only token → 403
    try:
        require_trader(current_user=_UserNoRole())
    except HTTPException as e:
        assert e.status_code == 403, (
            f"AAA-F2 regression: user-only role got {e.status_code}, expected 403"
        )
    else:
        raise AssertionError(
            "AAA-F2 regression: user-only role allowed through require_trader; "
            "self-reg users can place orders again."
        )

    # Trader allowed
    out = require_trader(current_user=_TraderUser())
    assert out.username == "t"

    # Admin allowed
    out = require_trader(current_user=_AdminUser())
    assert out.username == "a"


def test_ccc_2_paper_compose_wires_risk_caps():
    """docker-compose.paper.yml must explicitly wire the risk caps so a
    missing .env doesn't silently disable them."""
    src = open("docker-compose.paper.yml").read()
    assert "ORGANISM_DRAWDOWN_KILL_PCT=" in src, (
        "CCC-2 regression: paper compose no longer wires drawdown_kill_pct."
    )
    assert "ORGANISM_MAX_DAILY_LOSS=" in src, (
        "CCC-2 regression: paper compose no longer wires max_daily_loss."
    )
    assert "ORGANISM_MAX_NOTIONAL=" in src, (
        "CCC-2 regression: paper compose no longer wires max_notional."
    )


def test_ccc_2_default_compose_wires_risk_caps():
    """docker-compose.yml (default) gets the same explicit wiring."""
    src = open("docker-compose.yml").read()
    assert "ORGANISM_MAX_DAILY_LOSS=" in src, (
        "CCC-2 regression: default compose no longer wires max_daily_loss."
    )
    assert "ORGANISM_MAX_NOTIONAL=" in src, (
        "CCC-2 regression: default compose no longer wires max_notional."
    )
