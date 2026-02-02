"""Compatibility forwarding module.

Allows importing `backend.observability.metrics` while using the implementation
from `backend.infra.metrics`.
"""

from __future__ import annotations

from ..infra import metrics as _metrics


def __getattr__(name: str):
    return getattr(_metrics, name)


def __dir__():
    return sorted(set(globals().keys()) | set(dir(_metrics)))


def track_model_prediction(*args, **kwargs):  # pragma: no cover - test hook
    return None
