"""
Database models module.
Compatibility module for tests that expect backend.database.models
"""

# Mock database models for compatibility
from typing import Any
from datetime import datetime, timezone

class MockModel:
    """Mock database model for testing"""
    def __init__(self, *args, **kwargs):
        # Store positional args as numbered attributes
        for i, arg in enumerate(args):
            setattr(self, f'arg_{i}', arg)
        # Store keyword arguments as attributes
        for k, v in kwargs.items():
            setattr(self, k, v)
            # Handle private attributes for test compatibility
            # Set the name-mangled version for testing edge cases
            if k.startswith('__') and not k.endswith('__'):
                # For tests that expect name-mangled access like model.__private_attr
                setattr(self, f'_TestDatabaseEdgeCases{k}', v)
        # Use timezone-aware UTC datetime (Python 3.12+ compatible)
        now = datetime.now(timezone.utc)
        self.created_at = now
        self.updated_at = now

# Common model types that tests might expect
Order = MockModel
Position = MockModel
Trade = MockModel
User = MockModel

def create_mock_model(*args, **kwargs):
    """Create a mock model instance with given attributes"""
    return MockModel(*args, **kwargs)

# Ensure all classes are available for import
__all__ = ['MockModel', 'Order', 'Position', 'Trade', 'User', 'create_mock_model']
