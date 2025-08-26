"""Compatibility forwarding module.

Allows importing `backend.observability.metrics` while using the implementation
from `backend.infra.metrics`.
"""

from ..infra.metrics import *  # noqa: F401,F403 - deliberate re-export

# Provide a default no-op symbol for tests that patch it
def track_model_prediction(*args, **kwargs):  # pragma: no cover - test hook
	return None
