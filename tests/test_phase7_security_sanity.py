"""Phase 7.8 access-control wiring tests.

These tests inspect the actual FastAPI dependency graph.  They are stronger
than source-grep tests because they verify the mounted route carries a role
dependency after router nesting has been applied.
"""
from __future__ import annotations

from fastapi.routing import APIRoute


def _build_app():
    from backend.api.factory import create_app

    return create_app()


def _route(app, *, path: str, method: str) -> APIRoute:
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path == path and method.upper() in route.methods:
            return route
    raise AssertionError(f"route not found: {method} {path}")


def _role_dependencies(route: APIRoute) -> list[tuple[str, ...]]:
    roles: list[tuple[str, ...]] = []

    def walk(dependant) -> None:
        call = getattr(dependant, "call", None)
        required = getattr(call, "required_roles", None)
        if required:
            roles.append(tuple(required))
        for child in getattr(dependant, "dependencies", []) or []:
            walk(child)

    walk(route.dependant)
    return roles


def _assert_has_roles(app, *, path: str, method: str, allowed: set[str]) -> None:
    route = _route(app, path=path, method=method)
    role_sets = [set(item) for item in _role_dependencies(route)]
    assert allowed in role_sets, (
        f"{method} {path} missing role dependency {sorted(allowed)}; "
        f"found {[sorted(item) for item in role_sets]}"
    )


def test_phase7_operator_surfaces_reject_default_user_role():
    app = _build_app()

    trader_or_admin = {"trader", "admin"}
    admin_only = {"admin"}

    _assert_has_roles(
        app,
        path="/api/v1/health/strategy",
        method="GET",
        allowed=trader_or_admin,
    )
    _assert_has_roles(
        app,
        path="/api/v1/orders/",
        method="GET",
        allowed=trader_or_admin,
    )
    _assert_has_roles(
        app,
        path="/api/v1/health/deploy",
        method="GET",
        allowed=admin_only,
    )
    _assert_has_roles(
        app,
        path="/api/v1/health/data-integrity",
        method="GET",
        allowed=admin_only,
    )
    _assert_has_roles(
        app,
        path="/api/v1/organism/brain",
        method="GET",
        allowed=admin_only,
    )
