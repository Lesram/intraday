from __future__ import annotations

import ast
import logging
from pathlib import Path
from types import SimpleNamespace

from backend.infra.production import ConfigValidator


REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = REPO_ROOT / "backend" / "api" / "main.py"


def test_ccc_1_production_validator_accepts_runtime_env_names(monkeypatch):
    """CCC-1: production validator must accept the env names runtime uses."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")
    monkeypatch.setenv("SECURITY_JWT_SECRET", "x" * 40)
    monkeypatch.setenv("ALPACA_API_KEY_ID", "PK" + "A" * 24)
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "S" * 40)
    for legacy in (
        "JWT_SECRET",
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
    ):
        monkeypatch.delenv(legacy, raising=False)

    errors = ConfigValidator(environment="production").validate()

    error_keys = {e.key for e in errors if e.severity == "error"}
    assert "SECURITY_JWT_SECRET" not in error_keys
    assert "ALPACA_API_KEY_ID" not in error_keys
    assert "ALPACA_API_SECRET_KEY" not in error_keys


def test_ccc_1_production_validator_reports_canonical_missing_names(monkeypatch):
    """Missing production config should name canonical keys, not stale aliases."""
    for name in (
        "DATABASE_URL",
        "SECURITY_JWT_SECRET",
        "JWT_SECRET_KEY",
        "JWT_SECRET",
        "ALPACA_API_KEY_ID",
        "ALPACA_API_SECRET_KEY",
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    errors = ConfigValidator(environment="production").validate()
    error_keys = {e.key for e in errors if e.severity == "error"}

    assert {"DATABASE_URL", "SECURITY_JWT_SECRET"}.issubset(error_keys)
    assert {"ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY"}.issubset(error_keys)
    assert "ALPACA_API_KEY" not in error_keys
    assert "ALPACA_SECRET_KEY" not in error_keys


def test_ccc_1_validator_keeps_legacy_alias_compatibility(monkeypatch):
    """Compatibility aliases may pass, but the validator no longer demands them."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("ALPACA_API_KEY", "PK" + "A" * 24)
    monkeypatch.setenv("ALPACA_SECRET_KEY", "S" * 40)
    for canonical in (
        "SECURITY_JWT_SECRET",
        "ALPACA_API_KEY_ID",
        "ALPACA_API_SECRET_KEY",
    ):
        monkeypatch.delenv(canonical, raising=False)

    errors = ConfigValidator(environment="production").validate()

    assert not [e for e in errors if e.severity == "error"]


def test_iii_f1_configure_api_logging_calls_structured_runtime(monkeypatch):
    """III-F1: the API logging bootstrap calls the structured logger setup."""
    calls = []

    def fake_configure(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        "backend.infra.logging.configure_structured_logging",
        fake_configure,
    )
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    monkeypatch.setenv("APP_VERSION", "test-version")
    monkeypatch.delenv("INTRA_CONFIGURE_STRUCTURED_LOGGING", raising=False)

    from backend.api.logging_setup import configure_api_logging

    configured = configure_api_logging(
        SimpleNamespace(logging=SimpleNamespace(json_format=True))
    )

    assert configured is True
    assert calls == [{
        "level": "DEBUG",
        "service_name": "intraday-backend",
        "service_version": "test-version",
        "enable_trace_correlation": True,
        "json_format": True,
        "extra_fields": {"environment": "production"},
    }]


def test_iii_f1_structured_logging_installs_trace_filter(monkeypatch):
    """Structured logging should install JSON formatting and trace filtering."""
    from backend.infra.logging import JSONFormatter, TraceIdFilter
    from backend.api.logging_setup import configure_api_logging

    original_handlers = logging.getLogger().handlers[:]
    try:
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        monkeypatch.setenv("LOG_JSON_FORMAT", "true")
        monkeypatch.setenv("APP_ENVIRONMENT", "production")

        assert configure_api_logging(
            SimpleNamespace(logging=SimpleNamespace(json_format=True))
        )

        root = logging.getLogger()
        assert root.handlers
        handler = root.handlers[0]
        assert isinstance(handler.formatter, JSONFormatter)
        assert any(isinstance(f, TraceIdFilter) for f in handler.filters)
        assert logging.getLogger("uvicorn.access").level == logging.WARNING
    finally:
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        for handler in original_handlers:
            root.addHandler(handler)


def test_iii_f1_main_configures_logging_before_app_creation():
    """The container entrypoint imports backend.api.main, so main must wire logging."""
    tree = ast.parse(MAIN_PATH.read_text())
    call_order: list[str] = []

    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name) and func.id == "create_app":
                call_order.append("create_app")
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name) and func.id == "configure_api_logging":
                call_order.append("configure_api_logging")

    assert call_order[:2] == ["configure_api_logging", "create_app"]
