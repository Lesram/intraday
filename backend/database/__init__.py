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
		self.session_maker = session_maker or _SessionMaker()

	async def close(self) -> None:  # pragma: no cover
		return None


async def init_database(database_url: str) -> DatabaseManager:
	# Return a manager with a dummy session_maker; tests patch session dependency
	return DatabaseManager()


async def get_database() -> Any:  # pragma: no cover
	return None
