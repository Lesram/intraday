def test_import_api_main_has_app():
    from backend.api.main import app
    assert app is not None
