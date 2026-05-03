"""
Audit Trail API Routes.

Provides endpoints for:
- Querying audit logs with filters
- Verifying chain integrity (compliance check)
- Exporting audit data for regulatory reporting
- Audit statistics and monitoring

M-09 FIX: Added authentication requirement to all audit endpoints.
Audit data is sensitive and should only be accessible to authorized users.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session as get_db
from backend.infra.security import require_admin  # V8 AA2-NEW-1 / Wave-32: forensic audit data is admin-only
from backend.services.audit_service import (
    AuditAction,
    AuditEntity,
    ComplianceAuditService,
)

router = APIRouter(prefix="/audit", tags=["Audit", "Protected"])


# Pydantic models for API responses

class AuditLogResponse(BaseModel):
    """Audit log entry response."""

    id: str
    timestamp: datetime
    action: str
    entity: str
    entity_id: str
    actor: str
    payload: dict[str, Any] | None = None
    hash: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AuditTrailResponse(BaseModel):
    """Paginated audit trail response."""

    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int


class IntegrityCheckResponse(BaseModel):
    """Chain integrity verification response."""

    valid: bool
    records_checked: int
    message: str | None = None
    first_invalid_id: str | None = None
    error: str | None = None


class AuditStatisticsResponse(BaseModel):
    """Audit statistics response."""

    total_records: int
    by_entity: dict[str, int]
    by_action: dict[str, int]
    period: dict[str, str | None]


class AuditExportResponse(BaseModel):
    """Audit export response for compliance."""

    export_date: datetime
    start_date: datetime
    end_date: datetime
    record_count: int
    records: list[dict[str, Any]]


class AuditActionItem(BaseModel):
    """Audit action item."""
    value: str
    name: str


class AuditActionsResponse(BaseModel):
    """Response for listing audit actions."""
    actions: list[AuditActionItem]
    entities: list[AuditActionItem]


# API Routes

@router.get(
    "/trail",
    response_model=AuditTrailResponse,
    summary="Query Audit Trail",
    description="Query audit logs with optional filters for entity, action, actor, and time range.",
)
async def get_audit_trail(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(require_admin),  # V8 AA2-NEW-1 / Wave-32: admin-only audit access
    entity: str | None = Query(None, description="Filter by entity type (order, position, user, etc.)"),
    entity_id: str | None = Query(None, description="Filter by specific entity ID"),
    action: str | None = Query(None, description="Filter by action type"),
    actor: str | None = Query(None, description="Filter by actor (user:123, system:risk_manager, etc.)"),
    start_time: datetime | None = Query(None, description="Start of time range"),
    end_time: datetime | None = Query(None, description="End of time range"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    Query the audit trail with optional filters.

    Supports pagination and filtering by:
    - Entity type (order, position, strategy, etc.)
    - Entity ID
    - Action type
    - Actor
    - Time range
    """
    service = ComplianceAuditService(db)

    # Convert string to enum if provided
    entity_enum = None
    if entity:
        try:
            entity_enum = AuditEntity(entity)
        except ValueError:
            pass  # Use string matching if not a valid enum

    action_enum = None
    if action:
        try:
            action_enum = AuditAction(action)
        except ValueError:
            pass

    records = await service.get_audit_trail(
        entity_type=entity_enum,
        entity_id=entity_id,
        action=action_enum,
        actor=actor,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )

    # Get actual total count for pagination
    total_count = await service.count_audit_trail(
        entity_type=entity_enum,
        entity_id=entity_id,
        action=action_enum,
        actor=actor,
        start_time=start_time,
        end_time=end_time,
    )

    items = [
        AuditLogResponse(
            id=str(r.id),
            timestamp=r.ts,
            action=r.action,
            entity=r.entity,
            entity_id=r.entity_id,
            actor=r.actor,
            payload=r.payload,
            hash=r.hash_chain,
        )
        for r in records
    ]

    return AuditTrailResponse(
        items=items,
        total=total_count,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/entity/{entity_type}/{entity_id}",
    response_model=AuditTrailResponse,
    summary="Get Entity Audit History",
    description="Get complete audit history for a specific entity.",
)
async def get_entity_audit_history(
    entity_type: str,
    entity_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(require_admin),  # V8 AA2-NEW-1 / Wave-32: admin-only audit access
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Get complete audit history for a specific entity."""
    service = ComplianceAuditService(db)

    try:
        entity_enum = AuditEntity(entity_type)
    except ValueError:
        entity_enum = None

    records = await service.get_audit_trail(
        entity_type=entity_enum,
        entity_id=entity_id,
        limit=limit,
        offset=offset,
    )

    # Get actual total count for pagination
    total_count = await service.count_audit_trail(
        entity_type=entity_enum,
        entity_id=entity_id,
    )

    items = [
        AuditLogResponse(
            id=str(r.id),
            timestamp=r.ts,
            action=r.action,
            entity=r.entity,
            entity_id=r.entity_id,
            actor=r.actor,
            payload=r.payload,
            hash=r.hash_chain,
        )
        for r in records
    ]

    return AuditTrailResponse(
        items=items,
        total=total_count,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/verify",
    response_model=IntegrityCheckResponse,
    summary="Verify Chain Integrity",
    description="Verify the cryptographic integrity of the audit hash chain.",
)
async def verify_chain_integrity(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(require_admin),  # V8 AA2-NEW-1 / Wave-32: admin-only audit access
    start_time: datetime | None = Query(None, description="Start of time range to verify"),
    end_time: datetime | None = Query(None, description="End of time range to verify"),
    limit: int = Query(10000, ge=1, le=100000, description="Maximum records to verify"),
):
    """
    Verify the cryptographic integrity of the audit hash chain.

    This endpoint checks that each audit record's hash correctly
    chains to the previous record. Any tampering with historical
    records will cause this verification to fail.

    Use for:
    - Compliance audits
    - Tamper detection
    - Regulatory reporting
    """
    service = ComplianceAuditService(db)

    result = await service.verify_chain_integrity(
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )

    return IntegrityCheckResponse(**result)


@router.get(
    "/chain-detail",
    summary="Per-Row Audit Chain Detail",
    description=(
        "V12 W74 (EXT-4): per-row chain link detail.  "
        "Each row exposes prev_hash + current_hash + expected_hash + "
        "valid flag so an external auditor can independently verify "
        "the chain without trusting the aggregate /verify result."
    ),
)
async def get_chain_detail(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(require_admin),
    start_time: datetime | None = Query(None, description="Start of time range"),
    end_time: datetime | None = Query(None, description="End of time range"),
    limit: int = Query(1000, ge=1, le=10000, description="Max records"),
):
    """
    Per-row audit chain inspection.  V12 W74 (EXT-4): the schema
    stores only ``hash_chain``, not separate prev/current columns —
    this endpoint reconstructs both sides of each chain link so an
    independent auditor (running outside the application) can verify
    the chain without re-implementing the hash function.
    """
    service = ComplianceAuditService(db)
    result = await service.get_chain_detail(
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    return result


@router.get(
    "/statistics",
    response_model=AuditStatisticsResponse,
    summary="Get Audit Statistics",
    description="Get aggregate statistics about the audit trail.",
)
async def get_audit_statistics(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(require_admin),  # V8 AA2-NEW-1 / Wave-32: admin-only audit access
    start_time: datetime | None = Query(None, description="Start of time range"),
    end_time: datetime | None = Query(None, description="End of time range"),
):
    """Get aggregate statistics about the audit trail."""
    service = ComplianceAuditService(db)

    stats = await service.get_statistics(
        start_time=start_time,
        end_time=end_time,
    )

    return AuditStatisticsResponse(**stats)


@router.get(
    "/export",
    response_model=AuditExportResponse,
    summary="Export Audit Data",
    description="Export audit data for regulatory reporting (SEC/FINRA compliance).",
)
async def export_audit_data(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(require_admin),  # V8 AA2-NEW-1 / Wave-32: admin-only audit access
    start_date: datetime = Query(..., description="Start date for export"),
    end_date: datetime = Query(..., description="End date for export"),
):
    """
    Export audit data for regulatory reporting.

    Returns audit records in a format suitable for SEC Rule 17a-4
    and FINRA compliance requirements.
    """
    service = ComplianceAuditService(db)

    records = await service.export_for_compliance(
        start_date=start_date,
        end_date=end_date,
    )

    return AuditExportResponse(
        export_date=datetime.now(),
        start_date=start_date,
        end_date=end_date,
        record_count=len(records),
        records=records,
    )


# Action reference endpoint

@router.get(
    "/actions",
    response_model=AuditActionsResponse,
    summary="List Available Actions",
    description="List all available audit action types.",
)
async def list_audit_actions(
    current_user=Depends(require_admin),  # V8 AA2-NEW-1 / Wave-32: admin-only audit access
) -> AuditActionsResponse:
    """List all available audit action types for reference."""
    return AuditActionsResponse(
        actions=[
            AuditActionItem(value=a.value, name=a.name)
            for a in AuditAction
        ],
        entities=[
            AuditActionItem(value=e.value, name=e.name)
            for e in AuditEntity
        ],
    )
