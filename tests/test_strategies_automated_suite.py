"""Strategy schema/service contracts against an isolated, migrated PostgreSQL DB.

Set INTRA_TEST_DATABASE_URL to a test-named database/user and run Alembic first.
Every test owns its engine, event loop connection, savepoint and strategy rows.
SQLite's limited API fixture is deliberately not migration evidence.
"""

import os
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from tests.conftest import _isolated_postgres_url

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("INTRA_TEST_DATABASE_URL"),
        reason="Requires explicit INTRA_TEST_DATABASE_URL and Alembic-migrated PostgreSQL",
    ),
]


@pytest.fixture
async def strategy_session():
    url = _isolated_postgres_url(os.environ["INTRA_TEST_DATABASE_URL"])
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            # Assert migrations were applied; never manufacture a passing schema.
            from alembic.config import Config
            from alembic.script import ScriptDirectory
            heads = set(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())
            actual = set((await connection.execute(text("SELECT version_num FROM alembic_version"))).scalars())
            assert actual == heads, "Isolated PostgreSQL database is not at Alembic head"
            await connection.rollback()
            transaction = await connection.begin()
            try:
                async with AsyncSession(
                    bind=connection, expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    yield session
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
async def owned_strategy(strategy_session):
    from backend.infra.repositories.strategies import StrategyRepo
    strategy = await StrategyRepo(strategy_session).create({
        "name": f"fixture-{uuid.uuid4().hex}", "strategy_type": "technical",
        "description": "Owned by one test; outer transaction rolls back",
        "symbols": ["TEST"], "parameters": {"period": 20}, "status": "inactive",
    })
    await strategy_session.commit()
    return strategy


@pytest.fixture
async def strategy_service(strategy_session, monkeypatch):
    from backend.services.strategy_service import StrategyService
    # No socket clients or external channels participate in DB/service tests.
    monkeypatch.setattr(
        "backend.services.strategy_service.broadcast_strategy_update", AsyncMock()
    )
    return StrategyService(strategy_session, user_id="isolated-test-user")


class TestPhase1Database:
    async def test_01_strategies_table_exists(self, strategy_session):
        connection = await strategy_session.connection()
        assert await connection.run_sync(lambda c: inspect(c).has_table("strategies"))

    async def test_02_table_structure(self, strategy_session):
        connection = await strategy_session.connection()
        columns = await connection.run_sync(lambda c: inspect(c).get_columns("strategies"))
        actual = {column["name"]: column for column in columns}
        expected = {
            "id", "name", "strategy_type", "description", "status", "symbols",
            "parameters", "total_pnl", "total_trades", "winning_trades",
            "losing_trades", "win_rate", "max_position_size", "max_daily_loss",
            "max_drawdown_pct", "last_executed_at", "last_signal_at",
            "error_message", "error_count", "model_id", "created_at",
            "updated_at", "started_at", "stopped_at",
        }
        assert set(actual) == expected
        from sqlalchemy.dialects.postgresql import JSONB, UUID
        assert isinstance(actual["id"]["type"], UUID)
        assert isinstance(actual["model_id"]["type"], UUID)
        for name in ("symbols", "parameters"):
            assert isinstance(actual[name]["type"], JSONB)
            assert actual[name]["nullable"] is False
        for name in ("created_at", "updated_at", "last_executed_at", "last_signal_at", "started_at", "stopped_at"):
            assert actual[name]["type"].timezone is True
        assert actual["name"]["type"].length == 100
        assert actual["status"]["nullable"] is False
        assert actual["total_pnl"]["type"].precision == 18
        assert actual["total_pnl"]["type"].scale == 6

    async def test_03_indexes(self, strategy_session):
        connection = await strategy_session.connection()
        indexes = await connection.run_sync(lambda c: inspect(c).get_indexes("strategies"))
        actual = {i["name"]: (i["column_names"], i["unique"]) for i in indexes}
        for name, columns in {
            "ix_strategies_model_id": ["model_id"],
            "ix_strategies_status": ["status"],
            "ix_strategies_status_type": ["status", "strategy_type"],
            "ix_strategies_strategy_type": ["strategy_type"],
            "ix_strategies_updated_at": ["updated_at"],
        }.items():
            assert actual[name] == (columns, False)
        assert actual["ix_strategies_name"] == (["name"], True)
        pk = await connection.run_sync(lambda c: inspect(c).get_pk_constraint("strategies"))
        assert pk["constrained_columns"] == ["id"]

    async def test_04_foreign_keys(self, strategy_session):
        connection = await strategy_session.connection()
        keys = await connection.run_sync(lambda c: inspect(c).get_foreign_keys("strategies"))
        assert {(tuple(k["constrained_columns"]), k["referred_table"], tuple(k["referred_columns"])) for k in keys} == {
            (("model_id",), "model_registry", ("id",))
        }

    async def test_05_test_data_exists(self, strategy_session, owned_strategy):
        row = (await strategy_session.execute(
            text("SELECT name, status FROM strategies WHERE id=:id"),
            {"id": owned_strategy.id},
        )).one()
        assert tuple(row) == (owned_strategy.name, "inactive")


class TestPhase2ServiceLayer:
    async def test_01_repository_get_all(self, strategy_service, owned_strategy):
        strategies = await strategy_service.repo.get_all()
        owned = [s for s in strategies if s.id == owned_strategy.id]
        assert len(owned) == 1
        assert owned[0].name == owned_strategy.name
        assert owned[0].status == "inactive"

    async def test_02_repository_get_by_id(self, strategy_service, owned_strategy):
        strategy = await strategy_service.repo.get_by_id(owned_strategy.id)
        assert strategy.id == owned_strategy.id
        assert strategy.name == owned_strategy.name
        assert strategy.strategy_type == "technical"

    async def test_03_service_create(self, strategy_service):
        data = {"name": f"create-{uuid.uuid4().hex}", "strategy_type": "technical",
                "symbols": ["TEST", "AUTO"], "parameters": {"period": 12}}
        created = await strategy_service.create_strategy(data)
        assert isinstance(created, dict)
        assert uuid.UUID(created["id"])
        assert created["name"] == data["name"]
        assert created["status"] == "inactive"
        assert (await strategy_service.get_strategy(created["id"]))["parameters"]["period"] == 12

    async def test_04_service_update(self, strategy_service, owned_strategy):
        updates = {"description": "updated by owning test", "parameters": {"period": 25}}
        updated = await strategy_service.update_strategy(str(owned_strategy.id), updates)
        assert updated["description"] == updates["description"]
        assert updated["parameters"]["period"] == 25
        assert (await strategy_service.get_strategy(updated["id"]))["description"] == updates["description"]

    async def test_05_service_start(self, strategy_service, owned_strategy):
        started = await strategy_service.start_strategy(str(owned_strategy.id))
        assert started["status"] == "active"
        assert started["started_at"] is not None
        assert started["stopped_at"] is None

    async def test_06_service_pause(self, strategy_service, owned_strategy):
        identity = str(owned_strategy.id)
        await strategy_service.start_strategy(identity)
        paused = await strategy_service.pause_strategy(identity)
        assert paused["id"] == identity
        assert paused["status"] == "paused"
        assert (await strategy_service.get_strategy(identity))["status"] == "paused"

    async def test_07_service_stop(self, strategy_service, owned_strategy):
        identity = str(owned_strategy.id)
        await strategy_service.start_strategy(identity)
        await strategy_service.pause_strategy(identity)
        stopped = await strategy_service.stop_strategy(identity)
        assert stopped["status"] == "inactive"
        assert stopped["stopped_at"] is not None
        assert (await strategy_service.get_strategy(identity))["status"] == "inactive"

    async def test_inactive_cannot_pause(self, strategy_service, owned_strategy):
        from backend.infra.repositories.strategies import InvalidStatusTransitionError
        identity = str(owned_strategy.id)
        with pytest.raises(InvalidStatusTransitionError):
            await strategy_service.pause_strategy(identity)
        assert (await strategy_service.get_strategy(identity))["status"] == "inactive"

    async def test_service_commit_is_rolled_back_by_fixture(self, strategy_session, strategy_service):
        """A service commit releases only a savepoint, not the fixture transaction."""
        created = await strategy_service.create_strategy({
            "name": f"savepoint-{uuid.uuid4().hex}", "strategy_type": "technical",
            "symbols": ["TEST"], "parameters": {},
        })
        # An independent connection cannot see even a service-committed row.
        engine = create_async_engine(_isolated_postgres_url(os.environ["INTRA_TEST_DATABASE_URL"]), poolclass=NullPool)
        try:
            async with engine.connect() as observer:
                count = (await observer.execute(text("SELECT count(*) FROM strategies WHERE id=:id"), {"id": uuid.UUID(created["id"])})).scalar_one()
                assert count == 0
        finally:
            await engine.dispose()


class TestPhase3API:
    def test_01_api_list_strategies(self, client, auth_headers):
        """The real authenticated API replaces the old permanently skipped stub."""
        response = client.get("/api/v1/strategies", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
