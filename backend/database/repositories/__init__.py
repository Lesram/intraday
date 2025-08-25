"""
Repository shims for backward-compatibility in tests.

These modules provide minimal class definitions so tests can patch them.
"""

# Re-export commonly referenced repository modules for convenience
from . import execution_repository as execution_repository  # noqa: F401
from . import order_repository as order_repository  # noqa: F401

__all__ = ["execution_repository", "order_repository"]
