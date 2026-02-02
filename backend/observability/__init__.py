"""Compatibility shim for legacy imports.

Some older code refers to `backend.observability.*` while the actual
implementation lives under `backend.infra.metrics`.

We forward attribute access to `backend.infra.metrics` to keep patch targets
stable without using star imports.
"""

from __future__ import annotations

from ..infra import metrics as _metrics


def __getattr__(name: str):
    return getattr(_metrics, name)


def __dir__():
    return sorted(set(globals().keys()) | set(dir(_metrics)))


def track_model_prediction(*args, **kwargs):  # pragma: no cover - test hook
    return None
