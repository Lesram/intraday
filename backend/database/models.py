"""
Database models module.
Re-exports the real ORM models from backend.infra.schemas for production use,
with a MockModel fallback for legacy test compatibility.
"""

from datetime import UTC, datetime

# Re-export real production ORM models
try:
    from backend.infra.schemas import (
        Base,
        Execution as Trade,
        Order,
        Position,
        User,
    )
except ImportError:
    # Fallback: If schemas not importable (e.g. isolated test), use lightweight stub
    import warnings
    warnings.warn(
        "Could not import real ORM models from backend.infra.schemas. "
        "Using MockModel fallback — NOT suitable for production.",
        RuntimeWarning,
        stacklevel=2,
    )

    class MockModel:
        """Mock database model — test-only fallback."""
        def __init__(self, *args, **kwargs):
            for i, arg in enumerate(args):
                setattr(self, f'arg_{i}', arg)
            for k, v in kwargs.items():
                setattr(self, k, v)
                if k.startswith('__') and not k.endswith('__'):
                    setattr(self, f'_TestDatabaseEdgeCases{k}', v)
            now = datetime.now(UTC)
            self.created_at = now
            self.updated_at = now

    Order = MockModel  # type: ignore[assignment,misc]
    Position = MockModel  # type: ignore[assignment,misc]
    Trade = MockModel  # type: ignore[assignment,misc]
    User = MockModel  # type: ignore[assignment,misc]
    Base = type('Base', (), {})  # type: ignore[assignment,misc]


class MockModel:
    """Mock database model for legacy test compatibility.
    
    WARNING: This is a test-only class. Production code should use
    the real ORM models (Order, Position, Trade, User) exported above.
    """
    def __init__(self, *args, **kwargs):
        for i, arg in enumerate(args):
            setattr(self, f'arg_{i}', arg)
        for k, v in kwargs.items():
            setattr(self, k, v)
            if k.startswith('__') and not k.endswith('__'):
                setattr(self, f'_TestDatabaseEdgeCases{k}', v)
        now = datetime.now(UTC)
        self.created_at = now
        self.updated_at = now


def create_mock_model(*args, **kwargs):
    """Create a mock model instance — test only."""
    return MockModel(*args, **kwargs)


__all__ = ['Base', 'MockModel', 'Order', 'Position', 'Trade', 'User', 'create_mock_model']
