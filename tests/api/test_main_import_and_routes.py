import importlib


def test_main_import_and_routes():
    main = importlib.import_module('backend.api.main')

    assert hasattr(main, 'app')
    app = main.app

    paths = sorted({r.path for r in app.routes})

    expected = [
        "/api/v1/positions",
        "/metrics",
        "/healthz",
        "/readyz",
    ]

    for p in expected:
        assert p in paths, f"Missing route: {p}. Got: {paths}"

    assert any(p.startswith("/auth") or p.startswith("/api/v1/auth") for p in paths)
