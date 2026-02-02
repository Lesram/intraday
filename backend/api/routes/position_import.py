"""
Position Import API Routes
Endpoints for importing pre-existing Alpaca positions as historical orders.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db import get_db_session
from backend.infra.security import get_current_user
from backend.integrations.alpaca_broker import AlpacaBrokerClient
from backend.services.position_import_service import PositionImportService
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/positions", tags=["Portfolio", "Protected"])


# Response Models

class PositionInfo(BaseModel):
    """Position information"""
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_plpc: float


class ImportPreviewResponse(BaseModel):
    """Import preview response"""
    to_import: list[PositionInfo]
    to_import_count: int
    already_imported: list[PositionInfo]
    already_imported_count: int
    total_positions: int


class ImportedPosition(BaseModel):
    """Imported position info"""
    symbol: str
    qty: float
    avg_price: float
    value: float


class ImportResponse(BaseModel):
    """Import operation response"""
    success: bool
    imported: int
    skipped: int
    positions: list[ImportedPosition]
    skipped_symbols: list[str]


# API Endpoints

@router.get(
    "/import/preview",
    response_model=ImportPreviewResponse,
    summary="Preview Position Import",
    description="Preview which Alpaca positions would be imported without actually importing them."
)
async def preview_import(
    db: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user)
) -> ImportPreviewResponse:
    """
    Preview positions that would be imported from Alpaca.

    Shows:
    - Positions that will be imported (new)
    - Positions already imported (existing)

    No changes are made to the database.
    """
    try:
        logger.info("Previewing position import")

        alpaca_client = AlpacaBrokerClient()
        import_service = PositionImportService(db, alpaca_client)

        preview = await import_service.get_import_preview()

        return ImportPreviewResponse(**preview)

    except Exception as e:
        logger.error(f"Error previewing import: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/import",
    response_model=ImportResponse,
    summary="Import Alpaca Positions",
    description="Import pre-existing Alpaca positions as historical orders. Positions are marked as 'imported'."
)
async def import_positions(
    db: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user)
) -> ImportResponse:
    """
    Import all pre-existing Alpaca positions as historical orders.

    This creates order records for positions that existed before the platform,
    enabling:
    - Complete portfolio visibility
    - Unified trade history
    - Accurate analytics including all holdings

    Imported positions are marked with:
    - `imported: true` flag
    - `import_source: alpaca`
    - Original purchase details

    Already imported positions are skipped automatically.
    """
    try:
        logger.info("Starting position import")

        alpaca_client = AlpacaBrokerClient()
        import_service = PositionImportService(db, alpaca_client)

        # Get user ID from auth
        user_id = user.email if hasattr(user, 'email') else "demo"

        result = await import_service.import_existing_positions(user_id=user_id)

        logger.info(f"Import complete: {result['imported']} imported, {result['skipped']} skipped")

        return ImportResponse(**result)

    except Exception as e:
        logger.error(f"Error importing positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/import/{symbol}",
    summary="Remove Imported Position",
    description="Remove a specific imported position from the database."
)
async def remove_imported_position(
    symbol: str,
    db: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user)
) -> dict:
    """
    Remove a specific imported position from the database.

    This only removes the order record created by the import process.
    The actual Alpaca position is not affected.
    """
    try:
        from sqlalchemy import delete

        from backend.infra.schemas import Order

        # Delete only imported orders for this symbol
        stmt = delete(Order).where(
            Order.symbol == symbol.upper(),
            Order.attributes['imported'].astext == 'true'
        )

        result = await db.execute(stmt)
        await db.commit()

        if result.rowcount > 0:
            logger.info(f"Removed imported position: {symbol}")
            return {"success": True, "message": f"Removed imported position for {symbol}"}
        else:
            logger.warning(f"No imported position found for {symbol}")
            raise HTTPException(status_code=404, detail=f"No imported position found for {symbol}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing imported position: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
