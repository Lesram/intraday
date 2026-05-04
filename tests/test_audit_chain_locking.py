from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services.audit_service import (
    AuditAction,
    AuditEntity,
    ComplianceAuditService,
    _AUDIT_CHAIN_LOCK_CLASS,
    _AUDIT_CHAIN_LOCK_OBJECT,
    _compute_hash,
)


class _ScalarResult:
    def __init__(self, value: str | None):
        self._value = value

    def scalar_one_or_none(self) -> str | None:
        return self._value


class _PostgresAuditSession:
    is_active = True

    def __init__(self, last_hash: str | None):
        self.last_hash = last_hash
        self.calls: list[str] = []
        self.lock_params: dict[str, int] | None = None
        self.added = None

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    async def execute(self, statement, params=None):
        statement_text = str(statement)
        if "pg_advisory_xact_lock" in statement_text:
            self.calls.append("lock")
            self.lock_params = dict(params or {})
            return _ScalarResult(None)
        self.calls.append("select_last_hash")
        return _ScalarResult(self.last_hash)

    def add(self, row) -> None:
        self.added = row

    async def flush(self) -> None:
        self.calls.append("flush")


@pytest.mark.asyncio
async def test_audit_log_takes_postgres_lock_before_reading_last_hash():
    session = _PostgresAuditSession(last_hash="fresh-db-hash")
    service = ComplianceAuditService(session)
    service._last_hash_cache = "stale-cache-hash"

    row = await service.log(
        action=AuditAction.USER_LOGIN,
        entity=AuditEntity.USER,
        entity_id="admin@example.com",
        actor="user:admin@example.com",
        payload={"roles": ["admin"]},
    )
    assert session.calls == ["lock", "select_last_hash", "flush"]
    assert session.lock_params == {
        "class_id": _AUDIT_CHAIN_LOCK_CLASS,
        "object_id": _AUDIT_CHAIN_LOCK_OBJECT,
    }
    assert row is session.added
    assert row.hash_chain == _compute_hash(
        previous_hash="fresh-db-hash",
        timestamp=row.ts,
        action="user.login",
        entity="user",
        entity_id="admin@example.com",
        actor="user:admin@example.com",
        payload={"roles": ["admin"]},
    )
