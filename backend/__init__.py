"""Backend package initializer.
Ensures nested subpackages like `backend.services` are importable as attributes.
"""

from importlib import import_module as _import_module

# Eagerly expose the `services` subpackage so `getattr(backend, 'services')` works
try:  # pragma: no cover - simple import surface shim
	services = _import_module(".services", __name__)
except Exception:  # pragma: no cover
	services = None
