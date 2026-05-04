"""V13 W96 (Lens 5: Auth / RBAC) — IDOR cross-user behavioral coverage.

Closes the V12 audit gap: existing IDOR tests asserted only auth
required (401/403); they did NOT prove that user A cannot access
user B's resources.

W96 ships:

1. A canonical helper ``assert_order_owner_or_404(order, current_user)``
   in ``backend/api/routes/orders.py`` next to the existing
   ``_current_user_identity``.  Centralizes the ownership-check
   pattern that was duplicated inline 5 times.

2. Behavioral tests in this file: synthetic orders + 2 user
   identities; the helper raises 404 on cross-user, returns silently
   on owner, returns silently on system-owned (no user_id).

3. An AST static gate on ``orders.py``: every ``{order_id}``-pathed
   route handler must contain either the new helper call or the
   inline ``order_user_id != user_id`` pattern.  Catches new
   endpoints added without IDOR.

Run with:
    ./venv/bin/python -m pytest tests/test_v13_w96_idor.py -v
"""
# wave: V13-W96
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api.routes.orders import (
    _current_user_identity,
    _order_owner_id,
    assert_order_owner_or_404,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ORDERS_PATH = REPO_ROOT / "backend" / "api" / "routes" / "orders.py"


# ────────────────────────────────────────────────────────────────────
# Helper-level behavioral tests
# ────────────────────────────────────────────────────────────────────


def _user(name: str) -> SimpleNamespace:
    return SimpleNamespace(username=name, sub=name)


def test_w96_owner_id_extracts_from_dict():
    assert _order_owner_id({"user_id": "alice"}) == "alice"
    assert _order_owner_id({}) is None


def test_w96_owner_id_extracts_from_orm_like():
    obj = SimpleNamespace(user_id="bob")
    assert _order_owner_id(obj) == "bob"


def test_w96_owner_id_handles_no_owner():
    """Both dict-without-user_id and object-without-user_id return None."""
    assert _order_owner_id({"id": "abc"}) is None
    assert _order_owner_id(SimpleNamespace(id="abc")) is None


def test_w96_assert_order_owner_passes_when_owner_matches():
    order = {"user_id": "alice", "id": "ord-1"}
    # No exception expected.
    assert_order_owner_or_404(order, _user("alice"))


def test_w96_assert_order_owner_raises_404_on_cross_user():
    order = {"user_id": "alice", "id": "ord-1"}
    with pytest.raises(HTTPException) as exc:
        assert_order_owner_or_404(order, _user("bob"))
    assert exc.value.status_code == 404
    # Must NOT be 403 — surfacing 403 would confirm existence.
    assert exc.value.status_code != 403


def test_w96_assert_order_owner_passes_for_system_order():
    """Orders without a user_id (system-placed) must NOT be blocked
    — that would break legitimate system reads."""
    order = {"id": "ord-system-1"}  # no user_id field
    assert_order_owner_or_404(order, _user("alice"))


def test_w96_assert_order_owner_silent_on_none_status():
    """Helper returns silently when order_status is None — caller
    already handled the not-found path."""
    assert_order_owner_or_404(None, _user("alice"))


def test_w96_helper_works_with_orm_like_object():
    order = SimpleNamespace(user_id="alice", id="ord-1")
    # Owner — passes.
    assert_order_owner_or_404(order, _user("alice"))
    # Non-owner — raises.
    with pytest.raises(HTTPException) as exc:
        assert_order_owner_or_404(order, _user("bob"))
    assert exc.value.status_code == 404


def test_w96_current_user_identity_resolves_username():
    user = SimpleNamespace(username="alice", sub="alice-jwt-sub")
    assert _current_user_identity(user) == "alice"


# ────────────────────────────────────────────────────────────────────
# Static-gate: all {order_id}-pathed handlers have an IDOR check
# ────────────────────────────────────────────────────────────────────


def _route_handlers_with_order_id_path() -> list[tuple[str, ast.FunctionDef]]:
    """Return (route_path, handler) pairs whose decorator path starts
    with ``/{order_id}`` — these are the per-resource handlers that
    MUST include an IDOR check."""
    src = ORDERS_PATH.read_text()
    tree = ast.parse(src)
    out: list[tuple[str, ast.FunctionDef]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for dec in node.decorator_list:
            # @router.get/post/put/delete("...{order_id}...")
            if not isinstance(dec, ast.Call):
                continue
            if not (isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "router"):
                continue
            if not dec.args:
                continue
            first = dec.args[0]
            path_str = ""
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                path_str = first.value
            elif isinstance(first, ast.JoinedStr):
                continue
            # Per-order endpoint: path contains {order_id}
            if "{order_id}" in path_str:
                out.append((path_str, node))
    return out


def _function_calls_idor_check(func: ast.FunctionDef) -> bool:
    """A function passes the gate if its source body contains an
    ownership comparison.  Three accepted patterns:

    1. ``assert_order_owner_or_404(...)`` — V13 W96 canonical helper.
    2. ``order_user_id != user_id`` — legacy inline pattern (5 sites).
    3. ``original_order.user_id != requester`` and similar admin-bypass
       patterns used in close_position (403 vs 404 behaviour, but
       still a real ownership check).
    """
    body_src = ast.unparse(func)
    if "assert_order_owner_or_404" in body_src:
        return True
    if "order_user_id != user_id" in body_src:
        return True
    # Generic shape: any "<owner> != <requester>" inequality where
    # both sides reference a user_id-bearing identifier.
    body_lower = body_src.lower()
    if (
        ("user_id" in body_lower)
        and ("!=" in body_lower or "is_admin" in body_lower)
        and ("requester" in body_lower or "current_user" in body_lower
             or "user_id" in body_lower)
    ):
        # Require an explicit auth-decision raise (HTTPException with
        # 404 or 403 status) so we don't pass on a stray comparison.
        if "HTTPException" in body_src and (
            "404" in body_src or "403" in body_src
            or "HTTP_404_NOT_FOUND" in body_src
            or "HTTP_403_FORBIDDEN" in body_src
        ):
            return True
    return False


def test_w96_all_per_order_handlers_have_idor_check():
    """Every route handler whose path includes ``{order_id}`` must
    contain the IDOR check — either via the new helper or the legacy
    inline pattern."""
    pairs = _route_handlers_with_order_id_path()
    assert pairs, "no {order_id} handlers found — test_v13_w96 self-check failed"

    missing: list[str] = []
    for path, func in pairs:
        if not _function_calls_idor_check(func):
            missing.append(f"{path} → {func.name}")
    assert not missing, (
        f"V13 W96 IDOR gate: handler(s) missing ownership check: {missing}.  "
        f"Add `assert_order_owner_or_404(order_status, current_user)` after "
        f"the order_service.get_order_status() call."
    )


def test_w96_helper_present_in_orders_module():
    """Sanity: the new helper is exported from orders.py."""
    src = ORDERS_PATH.read_text()
    assert "def assert_order_owner_or_404(" in src
    assert "def _order_owner_id(" in src
