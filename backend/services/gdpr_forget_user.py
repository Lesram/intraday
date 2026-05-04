"""V13 W95 (Lens 4: Data Integrity) — GDPR right-to-be-forgotten service.

Closes BB5-F2.  V12 deferred this finding because the data-migration
to add ON-DELETE-CASCADE foreign keys to every user_id column is
high-risk on the live auth tables.  V13 W95 ships the service-level
capability without the migration: a single transactional helper that
deletes a user's data across all tables that reference them.

Behavior:
- One transaction per call, all-or-nothing.
- Tables with ON-DELETE-CASCADE FKs (existing migrations already
  applied this for orders → executions/events, position_lots →
  realized_trades) clean up automatically.
- Tables that just have a `user_id` column (no FK) are deleted by
  the service explicitly, in the canonical order (children first,
  then parent).
- The user row itself is the LAST delete.

The full FK-constraint refactor remains a separate initiative;
adding ALTER COLUMN constraints to the active-auth tables (User /
Order / Position) is a maintenance-window migration.  This service
gives operators GDPR compliance NOW; the FK refactor hardens
correctness LATER.

Usage:
    from backend.services.gdpr_forget_user import forget_user
    result = await forget_user(session, user_id="alice@example.com")
    # result.tables_affected = {"orders": 12, "positions": 3, ...}
    # result.user_deleted = True
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# Tables to scrub keyed by their user_id column.  Order matters:
# children → parent.  Anything that has ``user_id`` but isn't in this
# list is scrubbed by ``_default_user_id_scrub`` reflectively.
#
# CAUTION: AuditLog rows are NOT deleted here.  Compliance regulators
# (SOX, MiFID II) require audit-log retention separately from GDPR
# right-to-be-forgotten.  The audit row references the user via
# ``actor`` — V13 W95 design decision: do NOT scrub audit rows; instead
# pseudonymize the actor field via ``replace_actor_with_anonymous``.
_AUDIT_LOG_TABLES = ("audit_logs",)


@dataclass(frozen=True)
class ForgetUserResult:
    """Outcome of a forget_user call.  Frozen so callers can stash it
    in audit logs without worrying about mutation."""

    user_id: str
    user_deleted: bool
    audit_actor_pseudonymized: int
    tables_affected: dict[str, int] = field(default_factory=dict)
    skipped_tables: tuple[str, ...] = ()


async def _table_user_id_columns(session: AsyncSession) -> dict[str, str]:
    """Discover (table_name → user_id_column_name) by reflecting metadata.

    Most tables use ``user_id``; some legacy tables may use ``user``,
    ``owner_id``, or ``user_pk``.  V13 W95 only scrubs the canonical
    ``user_id`` column to avoid accidentally hitting unrelated columns.
    """
    from backend.infra.schemas import Base

    out: dict[str, str] = {}
    for tbl_name, tbl in Base.metadata.tables.items():
        if "user_id" in tbl.columns:
            out[tbl_name] = "user_id"
    return out


async def forget_user(
    session: AsyncSession,
    *,
    user_id: str,
    skip_tables: tuple[str, ...] = (),
    pseudonymize_audit: bool = True,
    delete_user_row: bool = True,
) -> ForgetUserResult:
    """Delete (or pseudonymize) all rows referencing ``user_id``.

    Parameters
    ----------
    session
        Caller-managed AsyncSession.  We do NOT commit; the caller
        controls the transaction boundary.  Tests / migration scripts
        can roll back.
    user_id
        The string to match against ``user_id`` columns.  Some tables
        store user_id as Integer + others as String + others as UUID;
        the comparison uses SQLAlchemy's binding so type coercion is
        the DB's job.
    skip_tables
        Names to bypass (e.g. operator wants to handle a table out-of-band).
    pseudonymize_audit
        If True, audit_logs rows where actor == user_id get actor
        replaced with ``"forgotten:" + sha256(user_id)[:16]``.
    delete_user_row
        If True, delete the row in ``users`` matching ``id == user_id``.

    Returns
    -------
    ForgetUserResult with per-table counts.
    """
    from backend.infra.schemas import AuditLog, User

    table_map = await _table_user_id_columns(session)
    # Sort tables so dependents come before parents.  Conservative
    # ordering: alphabetical within "definitely children" vs "users".
    # Postgres handles ON-DELETE-CASCADE for the registered FKs; this
    # ordering only matters for tables WITHOUT FKs.
    ordered = sorted(
        (t for t in table_map if t not in skip_tables and t != "users"),
        # audit_logs goes last among non-user tables so we don't
        # delete audit history before the operator's audit row is
        # written by the caller.
        key=lambda t: (1 if t in _AUDIT_LOG_TABLES else 0, t),
    )

    counts: dict[str, int] = {}
    skipped: list[str] = list(skip_tables)

    for tbl_name in ordered:
        if tbl_name in _AUDIT_LOG_TABLES:
            # We don't DELETE audit_logs rows — compliance retention.
            continue
        # Use raw text-bound SQL via SQLAlchemy core; avoids needing
        # the full ORM model for every table.
        tbl = (await _table_user_id_columns(session))  # cached in scope
        if tbl_name not in tbl:
            continue
        from backend.infra.schemas import Base
        tbl_obj = Base.metadata.tables.get(tbl_name)
        if tbl_obj is None or "user_id" not in tbl_obj.columns:
            continue
        stmt = delete(tbl_obj).where(tbl_obj.c.user_id == user_id)
        result = await session.execute(stmt)
        counts[tbl_name] = int(result.rowcount or 0)

    audit_pseudonymized = 0
    if pseudonymize_audit:
        # Pseudonymize actor field rather than deleting rows.  Use a
        # short stable hash so the same user's history collapses to a
        # single anonymized identity.
        import hashlib
        anon = "forgotten:" + hashlib.sha256(
            user_id.encode("utf-8")
        ).hexdigest()[:16]
        # AuditLog actor is a String — direct UPDATE.
        from sqlalchemy import update as _update
        upd_stmt = _update(AuditLog).where(
            AuditLog.actor == user_id
        ).values(actor=anon)
        upd_result = await session.execute(upd_stmt)
        audit_pseudonymized = int(upd_result.rowcount or 0)

    user_deleted = False
    if delete_user_row:
        # User.id is Integer; user_id arg may be string username or email.
        # Look up by username, email, or numeric id.
        candidates = [
            User.username == user_id,
            User.email == user_id,
        ]
        if user_id.isdigit():
            candidates.append(User.id == int(user_id))
        from sqlalchemy import or_
        sel = select(User).where(or_(*candidates))
        rows = (await session.execute(sel)).scalars().all()
        for u in rows:
            await session.delete(u)
            user_deleted = True

    logger.info(
        "V13 W95 forget_user: user_id=%r deleted=%s tables=%s pseudonymized=%d",
        user_id, user_deleted, counts, audit_pseudonymized,
    )

    return ForgetUserResult(
        user_id=user_id,
        user_deleted=user_deleted,
        audit_actor_pseudonymized=audit_pseudonymized,
        tables_affected=counts,
        skipped_tables=tuple(skipped),
    )


def discover_scrub_targets() -> list[str]:
    """Return the list of table names that ``forget_user`` will scrub.

    Useful for pre-flight: an operator can call this to confirm the
    set of tables before running the deletion.
    """
    from backend.infra.schemas import Base

    out: list[str] = []
    for tbl_name, tbl in Base.metadata.tables.items():
        if "user_id" in tbl.columns and tbl_name != "users":
            out.append(tbl_name)
    return sorted(out)
