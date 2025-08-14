"""
Database models module.
Compatibility module for tests that expect backend.database.models with a SQLAlchemy Base.
"""

from sqlalchemy.orm import declarative_base

# Provide a declarative Base so tests can run `Base.metadata.create_all(...)`
Base = declarative_base()

__all__ = ["Base"]
