"""API process logging bootstrap.

This module is intentionally small so the runtime entrypoint can wire
structured logging before the FastAPI app is created, while tests can
exercise the decision logic without importing ``backend.api.main``.
"""
from __future__ import annotations

from enum import Enum
import os
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _normalize_level(value: Any) -> str | int:
    if isinstance(value, Enum):
        return str(value.value)
    if value is None:
        return "INFO"
    return value


def configure_api_logging(settings: Any | None = None) -> bool:
    """Configure structured root logging for the API process.

    Returns ``True`` when configuration ran and ``False`` only when
    explicitly disabled via ``INTRA_CONFIGURE_STRUCTURED_LOGGING=0``.
    """
    if not _env_bool("INTRA_CONFIGURE_STRUCTURED_LOGGING", True):
        return False

    logging_settings = getattr(settings, "logging", None)
    level = os.environ.get(
        "LOG_LEVEL",
        _normalize_level(getattr(logging_settings, "level", "INFO")),
    )
    json_format = _env_bool(
        "LOG_JSON_FORMAT",
        bool(getattr(logging_settings, "json_format", True)),
    )
    service_name = (
        os.environ.get("OTEL_SERVICE_NAME")
        or os.environ.get("SERVICE_NAME")
        or "intraday-backend"
    )
    service_version = (
        os.environ.get("APP_VERSION")
        or os.environ.get("GIT_SHA")
        or "unknown"
    )

    from backend.infra.logging import configure_structured_logging

    configure_structured_logging(
        level=level,
        service_name=service_name,
        service_version=service_version,
        enable_trace_correlation=True,
        json_format=json_format,
        extra_fields={
            "environment": os.environ.get(
                "APP_ENVIRONMENT",
                os.environ.get("ENVIRONMENT", "development"),
            )
        },
    )
    return True
