"""Paper runtime configuration regressions.

The paper container uses APP_ENVIRONMENT=development for local runtime
ergonomics, but it still must honor explicit live-data toggles from
docker-compose.paper.yml. These tests protect the May 12 post-close
finding where AppSettings resolved USE_MOCK_DATA=True despite the
container environment setting USE_MOCK_DATA=false.
"""

from __future__ import annotations


def test_app_settings_respects_explicit_use_mock_data_false_in_development(monkeypatch):
    from backend.config.settings import AppSettings

    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("USE_MOCK_DATA", "false")

    settings = AppSettings()

    assert settings.USE_MOCK_DATA is False
    assert settings.use_mock_data is False


def test_app_settings_keeps_development_mock_default_when_unspecified(monkeypatch):
    from backend.config.settings import AppSettings

    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.delenv("USE_MOCK_DATA", raising=False)

    settings = AppSettings()

    assert settings.USE_MOCK_DATA is True


def test_app_settings_respects_explicit_alpaca_paper_false_in_development(monkeypatch):
    from backend.config.settings import AppSettings

    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("ALPACA_PAPER", "false")

    settings = AppSettings()

    assert settings.ALPACA_PAPER is False
    assert settings.alpaca_paper is False


def test_base_data_config_respects_explicit_use_mock_data_false(monkeypatch):
    from backend.config.base_settings import DataConfig

    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("USE_MOCK_DATA", "false")

    settings = DataConfig()

    assert settings.use_mock_data is False


def test_base_alpaca_config_respects_explicit_paper_false(monkeypatch):
    from backend.config.base_settings import AlpacaConfig

    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("ALPACA_PAPER", "false")

    settings = AlpacaConfig()

    assert settings.paper is False


def test_base_legacy_settings_maps_flat_runtime_toggles(monkeypatch):
    from backend.config.base_settings import get_settings

    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("USE_MOCK_DATA", "false")
    monkeypatch.setenv("USE_MOCK_BROKER", "false")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.USE_MOCK_DATA is False
        assert settings.USE_MOCK_BROKER is False
        assert settings.ALPACA_PAPER is True
    finally:
        get_settings.cache_clear()


def test_signals_market_data_client_uses_real_client_when_mock_false(monkeypatch):
    from backend.api.routes import signals
    import backend.integrations.alpaca_data as alpaca_data
    from backend.config import settings as app_settings

    sentinel = object()

    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("USE_MOCK_DATA", "false")
    monkeypatch.setattr(alpaca_data, "get_alpaca_data_client", lambda: sentinel)
    app_settings._settings_manager.reset()

    try:
        assert signals.get_market_data_client() is sentinel
    finally:
        app_settings._settings_manager.reset()
