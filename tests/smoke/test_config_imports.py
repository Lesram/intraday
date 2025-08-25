def test_config_imports():
    # legacy form
    import backend.config as C
    assert hasattr(C, "__dict__")
    # package form
    from backend.config.settings import settings
    assert settings is not None
