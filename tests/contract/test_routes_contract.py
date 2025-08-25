from backend.api.factory import create_app


def test_routes_contract_contains_core_paths():
    app = create_app()
    paths = sorted({r.path for r in app.routes})

    # Expected core endpoints
    expected_any = [
        "/api/v1/positions",
        "/metrics",
        "/healthz",
        "/readyz",
    ]

    for p in expected_any:
        assert p in paths, f"Missing route: {p}. Got: {paths}"

    # At least one auth route exists (either legacy or v1)
    assert any(p.startswith("/auth") or p.startswith("/api/v1/auth") for p in paths)
