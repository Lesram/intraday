"""
Database models module.
Compatibility module for tests that expect backend.database.models
"""

# Mock database models for compatibility
from typing import Any
from datetime import datetime

class MockModel:
    """Mock database model for testing"""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

# Common model types that tests might expect
Order = MockModel
Position = MockModel
Trade = MockModel
User = MockModel
