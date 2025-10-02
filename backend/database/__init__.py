"""Lightweight database manager shim for tests.

Provides init_database returning an object with a session_maker and close().
Avoids real DB connections for integration tests using in-memory engines.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class _SessionMaker:
	def __call__(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
		return None


class DatabaseManager:
	def __init__(self, database_url: str | None = None, session_maker: Callable[..., Any] | None = None) -> None:
		self.database_url = database_url
		# Handle session_maker initialization - auto-create _SessionMaker if None or non-callable
		if session_maker is None or not callable(session_maker):
			self.session_maker = _SessionMaker()
		else:
			self.session_maker = session_maker
		self.engine = None
		self._is_healthy = False
		self._is_initialized = False

	@property
	def is_healthy(self) -> bool:
		return self._is_healthy

	def initialize(self):
		"""Initialize database manager (sync version)."""
		self._is_initialized = True
		self.engine = "mock_engine"
		# session_maker already set in __init__
		return True

	def create_session(self):
		"""Create a mock session."""
		return type('MockSession', (), {'id': 'mock_session'})()

	def get_connection(self):
		"""Get a mock connection."""
		return type('MockConnection', (), {'id': 'mock_connection'})()

	def close(self):
		"""Close database manager (sync version)."""
		self.engine = None
		self.session_maker = None
		self._is_healthy = False
		self._is_initialized = False

	async def close_async(self) -> None:  # pragma: no cover
		"""Async close method."""
		self.close()  # Delegate to sync version


async def init_database(database_url: str) -> DatabaseManager:
	# Return a manager with a dummy session_maker; tests patch session dependency
	return DatabaseManager()


async def get_database() -> Any:  # pragma: no cover
	return None


# Import and expose submodules for proper package structure
try:
	from . import connection, models, repositories
	from .connection import connection as connection_func

	# Expose key functions at package level
	from .connection import get_database_session
	from .models import MockModel, Order, Position, Trade, User, create_mock_model
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

class QueryBuilder:
	"""SQL query builder utility."""
	
	def __init__(self):
		self.reset()
		
	def reset(self):
		"""Reset query builder state."""
		self._select_fields = []
		self._from_table = None
		self._where_conditions = []
		self._joins = []
		self._order_by = []
		self._group_by = []
		self._having = []
		self._limit_value = None
		self._offset_value = None
		
	def select(self, *fields):
		"""Add SELECT fields."""
		self._select_fields.extend(fields)
		return self
		
	def from_table(self, table):
		"""Set FROM table."""
		self._from_table = table
		return self
		
	def where(self, condition):
		"""Add WHERE condition."""
		self._where_conditions.append(condition)
		return self
		
	def join(self, join_clause):
		"""Add JOIN clause."""
		self._joins.append(join_clause)
		return self
		
	def order_by(self, order_clause):
		"""Add ORDER BY clause."""
		self._order_by.append(order_clause)
		return self
		
	def limit(self, count):
		"""Set LIMIT."""
		self._limit_value = count
		return self
		
	def offset(self, count):
		"""Set OFFSET."""
		self._offset_value = count
		return self
		
	def build(self):
		"""Build SQL query string."""
		if not self._select_fields:
			raise DatabaseError("No SELECT fields specified")
		if not self._from_table:
			raise DatabaseError("No FROM table specified")
			
		query_parts = []
		
		# SELECT
		fields = ", ".join(self._select_fields)
		query_parts.append(f"SELECT {fields}")
		
		# FROM
		query_parts.append(f"FROM {self._from_table}")
		
		# JOINs
		if self._joins:
			query_parts.extend(self._joins)
			
		# WHERE
		if self._where_conditions:
			conditions = " AND ".join(self._where_conditions)
			query_parts.append(f"WHERE {conditions}")
			
		# ORDER BY
		if self._order_by:
			order_cols = ", ".join(self._order_by)
			query_parts.append(f"ORDER BY {order_cols}")
			
		# LIMIT and OFFSET
		if self._limit_value is not None:
			query_parts.append(f"LIMIT {self._limit_value}")
		if self._offset_value is not None:
			query_parts.append(f"OFFSET {self._offset_value}")
			
		return " ".join(query_parts)


class DatabaseError(Exception):
	"""Base database exception."""
	pass

# Additional database classes for test compatibility
class ConnectionPool:
	"""Database connection pool stub."""
	def __init__(self, *args, **kwargs):
		pass

class SessionManager:
	"""Database session manager stub."""
	def __init__(self, *args, **kwargs):
		pass

class TransactionManager:
	"""Database transaction manager stub."""
	def __init__(self, *args, **kwargs):
		pass

class DatabaseMigrator:
	"""Database migrator stub."""
	def __init__(self, *args, **kwargs):
		pass

class DatabaseMonitor:
	"""Database monitor stub."""
	def __init__(self, *args, **kwargs):
		pass

class DatabaseConfig:
	"""Database configuration - requires PostgreSQL."""
	def __init__(self, url: str = None, *args, **kwargs):
		import os
		
		# Use provided URL or get from environment
		if url is None:
			url = os.getenv("DATABASE_URL")
		
		# Enforce PostgreSQL requirement
		if not url:
			raise DatabaseError(
				"DATABASE_URL environment variable required.\n"
				"Set DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname\n"
				"SQLite is not supported for production use.\n"
				"For local development, use docker-compose to start PostgreSQL:\n"
				"  docker-compose up -d postgres"
			)
		
		# Validate it's PostgreSQL
		if not url.startswith("postgresql"):
			raise DatabaseError(
				f"Only PostgreSQL supported in production, got: {url}\n"
				f"Expected: postgresql+asyncpg://... or postgresql+psycopg2://...\n"
				f"SQLite cannot validate production behavior (connection pooling, "
				f"locking, JSON types, SELECT FOR UPDATE)."
			)
		
		self.url = url
		self.pool_size = kwargs.get('pool_size', 20)
		self.max_overflow = kwargs.get('max_overflow', 10)

# Exception classes
class ConnectionError(DatabaseError):
	"""Database connection exception."""
	pass

class TransactionError(DatabaseError):
	"""Database transaction exception."""
	pass

class MigrationError(DatabaseError):
	"""Database migration exception."""
	pass

# Stub functions
def create_engine(*args, **kwargs):
	return "mock_engine"

def create_session(*args, **kwargs):
	return None

def get_session(*args, **kwargs):
	return None

def close_session(*args, **kwargs):
	pass

def execute_query(*args, **kwargs):
	return []

def execute_async_query(*args, **kwargs):
	return []

def begin_transaction(*args, **kwargs):
	pass

def commit_transaction(*args, **kwargs):
	pass

def rollback_transaction(*args, **kwargs):
	pass

def create_tables(*args, **kwargs):
	pass

def drop_tables(*args, **kwargs):
	pass

def migrate_database(*args, **kwargs):
	pass

def backup_database(*args, **kwargs):
	pass

def restore_database(*args, **kwargs):
	pass

def get_connection_info(*args, **kwargs):
	return {}

def test_connection(*args, **kwargs):
	return True

def health_check(*args, **kwargs):
	return {"status": "healthy"}

def get_database_stats(*args, **kwargs):
	return {}

def setup_database(*args, **kwargs):
	pass

def teardown_database(*args, **kwargs):
	pass

def initialize_database(*args, **kwargs):
	pass

# Additional stubs
SessionFactory = None
AsyncSessionFactory = None
DatabaseURL = str
ModelBase = object
IsolationLevel = None
