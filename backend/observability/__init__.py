"""Compatibility shim for legacy imports.

Some older tests refer to `backend.observability.metrics` while the actual
implementation lives under `backend.infra.metrics`. This package provides
compatibility by re-exporting the metrics module so patch targets remain valid.
"""

from ..infra.metrics import *  # re-export everything

# Provide a default no-op for tests that patch this symbol
def track_model_prediction(*args, **kwargs):  # pragma: no cover - test hook
	return None
