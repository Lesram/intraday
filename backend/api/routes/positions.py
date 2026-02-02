"""
Positions API routes for portfolio management.
Provides GET /positions endpoint with support for mock data, Alpaca API, and database.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.infra.db import get_db_session
from backend.infra.security import AuthenticatedUser, get_authenticated_user
from backend.services.positions_service import create_positions_service

router = APIRouter(prefix="/positions", tags=["Positions"])


def _compute_etag(data: Any) -> str:
    """Compute ETag from response data for cache validation (L-08)."""
    content = json.dumps(data, sort_keys=True, default=str)
    return f'"{hashlib.md5(content.encode()).hexdigest()}"'


class PositionDTO(BaseModel):
    """Position data transfer object."""
    symbol: str
    qty: float
    avg_price: float
    market_price: float | None = None
    market_value: float | None = None
    unrealized_pl: float | None = None
    updated_at: datetime


def get_mock_positions() -> list[PositionDTO]:
    """Return deterministic demo positions for testing and development."""
    now = datetime.now(UTC)

    return [
        PositionDTO(
            symbol="AAPL",
            qty=10.0,
            avg_price=180.0,
            market_price=185.50,
            market_value=1855.0,
            unrealized_pl=55.0,
            updated_at=now
        ),
        PositionDTO(
            symbol="GOOGL",
            qty=5.0,
            avg_price=2750.0,
            market_price=2800.25,
            market_value=14001.25,
            unrealized_pl=251.25,
            updated_at=now
        ),
        PositionDTO(
            symbol="MSFT",
            qty=15.0,
            avg_price=420.0,
            market_price=415.75,
            market_value=6236.25,
            unrealized_pl=-63.75,
            updated_at=now
        ),
    ]


async def get_alpaca_positions() -> list[PositionDTO]:
    """Fetch positions from Alpaca API using PositionsService."""
    try:
        # Use the PositionsService for actual Alpaca API integration
        positions_service = create_positions_service()
        positions_dict = await positions_service.get_all_positions()

        now = datetime.now(UTC)
        positions = []

        for symbol, pos_data in positions_dict.items():
            if pos_data.get('qty', 0) != 0:  # Only include actual positions
                positions.append(PositionDTO(
                    symbol=symbol,
                    qty=float(pos_data.get('qty', 0)),
                    avg_price=float(pos_data.get('avg_entry_price', 0)),
                    market_price=float(pos_data.get('market_value', 0)) / float(pos_data.get('qty', 1)) if pos_data.get('qty', 0) != 0 else 0,
                    market_value=float(pos_data.get('market_value', 0)),
                    unrealized_pl=float(pos_data.get('unrealized_pl', 0)),
                    updated_at=now
                ))

        return positions if positions else get_mock_positions()  # Fallback if no positions

    except Exception as e:
        # Fallback to mock data if Alpaca unavailable
        import logging
        logging.getLogger(__name__).warning(f"Alpaca API unavailable, using mock data: {e}")
        return get_mock_positions()


async def get_database_positions() -> list[PositionDTO]:
    """
    Fetch positions from database.

    Note: This function is designed for future database integration.
    Currently returns mock data. When implementing full database storage,
    this would query the positions table and map to DTOs.
    """
    try:
        # For now, return mock data indicating database source
        positions = get_mock_positions()

        # Mark as database-sourced for identification
        for position in positions:
            position.symbol = f"{position.symbol}_DB"

        return positions

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to fetch positions from database: {str(e)}"
        )


@router.get("/", response_model=list[PositionDTO])
async def get_positions(
    request: Request,
    response: Response,
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> list[PositionDTO]:
    """
    Get current portfolio positions.

    Returns positions from different sources based on configuration:
    - Mock data if USE_MOCK_DATA=true
    - Alpaca API if USE_MOCK_BROKER=false
    - Database if USE_MOCK_BROKER=true and database available

    Requires authentication - returns 401 without valid token.
    """
    settings = get_settings()

    # Check USE_MOCK_DATA setting first
    use_mock_data = getattr(settings, 'USE_MOCK_DATA', False)
    if use_mock_data:
        positions = get_mock_positions()
    else:
        # Check USE_MOCK_BROKER setting - default to False (use real Alpaca)
        use_mock_broker = getattr(settings, 'USE_MOCK_BROKER', False)

        if not use_mock_broker:
            # Use Alpaca API for real trading
            positions = await get_alpaca_positions()
        else:
            # Use database or fallback to mock
            try:
                positions = await get_database_positions()
            except HTTPException:
                # Fallback to mock data if database unavailable
                positions = get_mock_positions()

    # L-08: Add ETag support for cache validation on frequently-polled endpoint
    positions_data = [p.model_dump() for p in positions]
    etag = _compute_etag(positions_data)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=1"

    # Check If-None-Match for conditional request
    if_none_match = request.headers.get("If-None-Match")
    if if_none_match and if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})

    return positions


# ============================================================================
# POSITION IMPORT ENDPOINTS
# ============================================================================

class PositionInfo(BaseModel):
    """Detailed position information for import operations"""
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


@router.get("/import/preview", response_model=ImportPreviewResponse)
async def preview_import(
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
) -> ImportPreviewResponse:
    """
    Preview which Alpaca positions would be imported without actually importing them.

    Shows:
    - Positions that will be imported (new)
    - Positions already imported (existing)

    No changes are made to the database.
    """
    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    from backend.infra.db import get_db_session
    from backend.integrations.alpaca_broker import AlpacaBrokerClient
    from backend.services.position_import_service import PositionImportService

    async def _preview(db: AsyncSession = Depends(get_db_session)):
        try:
            alpaca_client = AlpacaBrokerClient()
            import_service = PositionImportService(db, alpaca_client)
            preview = await import_service.get_import_preview()
            return ImportPreviewResponse(**preview)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Call the inner function with proper dependency injection
    from backend.infra.db import get_db_session as get_session
    async for db in get_session():
        try:
            alpaca_client = AlpacaBrokerClient()
            import_service = PositionImportService(db, alpaca_client)
            preview = await import_service.get_import_preview()
            return ImportPreviewResponse(**preview)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/import", response_model=ImportResponse)
async def import_positions_endpoint(
    current_user: AuthenticatedUser = Depends(get_authenticated_user)
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
    from backend.infra.db import get_db_session as get_session
    from backend.integrations.alpaca_broker import AlpacaBrokerClient
    from backend.services.position_import_service import PositionImportService

    async for db in get_session():
        try:
            alpaca_client = AlpacaBrokerClient()
            import_service = PositionImportService(db, alpaca_client)

            # Get user email from authenticated user
            user_id = current_user.email if hasattr(current_user, 'email') else "demo"

            result = await import_service.import_existing_positions(user_id=user_id)
            return ImportResponse(**result)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


class ClosePositionRequest(BaseModel):
    """Request to close a position (full or partial)."""
    quantity: float | None = None  # If None, close entire position


class ClosePositionResponse(BaseModel):
    """Response from closing a position."""
    success: bool
    message: str
    order_id: str | None = None
    symbol: str
    quantity: float
    remaining_quantity: float


@router.post("/{symbol}/close", response_model=ClosePositionResponse)
async def close_position(
    symbol: str,
    current_user: AuthenticatedUser = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db_session),
    body: dict[str, Any] | None = Body(None)
) -> ClosePositionResponse:
    """
    Close a position by creating a market sell order.

    Supports both full and partial position closes:
    - **Full close**: Omit quantity or set to None to sell entire position
    - **Partial close**: Specify quantity to sell only portion of position

    Args:
        symbol: Stock symbol (e.g., "AAPL")
        body: Optional request body with quantity field
        current_user: Authenticated user
        db: Database session

    Returns:
        ClosePositionResponse with order details

    Raises:
        404: Position not found
        400: Invalid quantity (exceeds position size)
        500: Order submission failed
    """
    import logging

    from backend.integrations.alpaca_broker import AlpacaBrokerClient
    from backend.services.order_service import OrderService

    logger = logging.getLogger(__name__)
    symbol = symbol.upper()

    # Parse quantity from body
    quantity = body.get("quantity") if body else None

    try:
        # Get Alpaca broker client
        broker = AlpacaBrokerClient()

        # Get current position from Alpaca
        alpaca_position = await broker.get_position(symbol)

        if not alpaca_position:
            raise HTTPException(
                status_code=404,
                detail=f"No open position found for {symbol}"
            )

        # Get position quantity (negative for shorts, positive for longs)
        position_qty = float(alpaca_position.get("qty", 0))
        is_short = position_qty < 0
        abs_position_qty = abs(position_qty)

        if abs_position_qty == 0:
            raise HTTPException(
                status_code=400,
                detail=f"Position for {symbol} has no shares (qty={position_qty})"
            )

        # Determine quantity to close (use absolute value)
        qty_to_close = quantity if quantity is not None else abs_position_qty

        # Validate quantity
        if qty_to_close <= 0:
            raise HTTPException(
                status_code=400,
                detail="Quantity must be greater than 0"
            )

        if qty_to_close > abs_position_qty:
            position_type = "short" if is_short else "long"
            raise HTTPException(
                status_code=400,
                detail=f"Cannot close {qty_to_close} shares. {position_type.capitalize()} position only has {abs_position_qty} shares."
            )

        # Create market sell order using OrderService
        from backend.infra.outbox import OutboxRepo
        from backend.infra.repositories.orders import OrdersRepo

        orders_repo = OrdersRepo(db)
        outbox_repo = OutboxRepo(db)
        order_service = OrderService(
            db_session=db,
            orders_repo=orders_repo,
            outbox_repo=outbox_repo
        )

        user_id = current_user.email if hasattr(current_user, 'email') else "admin"

        # To close a position: sell for long, buy for short
        close_side = "buy" if is_short else "sell"
        position_type = "short" if is_short else "long"

        logger.info(f"Creating {close_side} order to close {position_type} position for {symbol}: "
                   f"{qty_to_close} shares (position has {abs_position_qty})")

        # Prepare order data for OrderService
        order_data = {
            "user_id": user_id,
            "symbol": symbol,
            "side": close_side,
            "qty": qty_to_close,
            "order_type": "market",
            "time_in_force": "day",
            "extended_hours": False,
            "client_order_id": None,
            "limit_price": None,
            "stop_price": None,
            "attributes": {
                "close_position": True,
                "position_type": position_type,
                "partial_close": qty_to_close < abs_position_qty,
                "original_position_qty": position_qty
            }
        }

        # Submit order through OrderService
        try:
            result = await order_service.submit_order_async(order_data)

            # Check if order was rejected during validation
            if result.get("status") == "rejected":
                raise HTTPException(
                    status_code=400,
                    detail=f"Order rejected: {result.get('reason', 'Unknown reason')}"
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to submit close order for {symbol}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to submit {close_side} order: {str(e)}"
            )

        order_id = result.get("order_id", "unknown")
        remaining_qty = abs_position_qty - qty_to_close

        logger.info(f"Close {position_type} position order created: symbol={symbol}, order_id={order_id}, "
                   f"side={close_side}, quantity={qty_to_close}, remaining={remaining_qty}")

        action = "Buy-to-cover" if is_short else "Sell"
        return ClosePositionResponse(
            success=True,
            message=f"{action} order submitted for {qty_to_close} shares of {symbol}" +
                   (f" ({remaining_qty} shares remaining)" if remaining_qty > 0 else f" ({position_type} position fully closed)"),
            order_id=order_id,
            symbol=symbol,
            quantity=qty_to_close,
            remaining_quantity=remaining_qty
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to close position for {symbol}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to close position: {str(e)}"
        )
