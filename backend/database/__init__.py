"""Lightweight database manager shim for tests.

Provides init_database returning an object with a session_maker and close().
Avoids real DB connections for integration tests using in-memory engines.
"""

from __future__ import annotations

from typing import Any, Callable


class _SessionMaker:
	def __call__(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
		return None


class DatabaseManager:
	def __init__(self, session_maker: Callable[..., Any] | None = None) -> None:
		self.session_maker = session_maker if callable(session_maker) else _SessionMaker()

	async def close(self) -> None:  # pragma: no cover
		return None


async def init_database(database_url: str) -> DatabaseManager:
	# Return a manager with a dummy session_maker; tests patch session dependency
	return DatabaseManager()


async def get_database() -> Any:  # pragma: no cover
	return None


# Import and expose submodules for proper package structure
try:
	from . import connection
	from . import models
	from . import repositories
	# Expose key functions at package level
	from .connection import get_database_session, connection as connection_func
	from .models import MockModel, create_mock_model, Order, Position, Trade, User
except ImportError:  # pragma: no cover
	# Fallback if modules can't be imported
	connection = None  # type: ignore
	models = None  # type: ignore  
	repositories = None  # type: ignore
	get_database_session = None  # type: ignore
	connection_func = None  # type: ignore
	MockModel = None  # type: ignore
	create_mock_model = None  # type: ignore
	Order = None  # type: ignore
	Position = None  # type: ignore
	Trade = None  # type: ignore
	User = None  # type: ignore

# Define SessionLocal here to avoid circular imports
SessionLocal = None  # type: ignore[assignment]
