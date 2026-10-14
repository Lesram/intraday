"""
Watchlist management routes
"""
from datetime import UTC, datetime
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.dependencies import get_current_db_user
from backend.api.schemas.watchlists import (
    WatchlistCreate,
    WatchlistResponse,
    WatchlistSymbolAdd,
    WatchlistSymbolReorder,
    WatchlistUpdate,
)
from backend.infra.db import get_db_session
from backend.infra.schemas import User, Watchlist, WatchlistSymbol
from backend.services import dashboard_market_data

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watchlists", tags=["watchlists"])

# Audit 2026-10-05 A8-01: most symbols one quotes request looks up (one batched
# latest-quote request; further symbols are answered with error "symbol_limit").
WATCHLIST_QUOTE_SYMBOL_LIMIT = 50
# US equity tickers as the latest-quote endpoint accepts them (e.g. BRK.B).
_QUOTABLE_SYMBOL = re.compile(r"[A-Z][A-Z0-9.\-]{0,9}")


@router.get("/", response_model=list[WatchlistResponse])
async def get_watchlists(
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get all watchlists for the current user
    """
    result = await db.execute(
        select(Watchlist)
        .filter(Watchlist.user_id == current_user.id)
        .order_by(Watchlist.is_default.desc(), Watchlist.created_at)
        .options(selectinload(Watchlist.symbols))
    )
    watchlists = result.scalars().all()

    logger.info(f"User {current_user.id} retrieved {len(watchlists)} watchlists")

    return [wl.to_dict() for wl in watchlists]


@router.post("/", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    request: WatchlistCreate,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Create a new watchlist
    """
    # Create watchlist
    watchlist = Watchlist(
        user_id=current_user.id,
        name=request.name,
        description=request.description,
        is_default=False
    )
    db.add(watchlist)
    await db.flush()  # Get the ID

    # Add symbols
    for i, symbol in enumerate(request.symbols):
        db_symbol = WatchlistSymbol(
            watchlist_id=watchlist.id,
            symbol=symbol.upper(),
            order=i
        )
        db.add(db_symbol)

    await db.commit()

    # Re-query with eager loading to get symbols
    result = await db.execute(
        select(Watchlist)
        .filter(Watchlist.id == watchlist.id)
        .options(selectinload(Watchlist.symbols))
    )
    watchlist = result.scalar_one()

    logger.info(f"User {current_user.id} created watchlist '{request.name}' with {len(request.symbols)} symbols")

    return watchlist.to_dict()


@router.get("/{watchlist_id}", response_model=WatchlistResponse)
async def get_watchlist(
    watchlist_id: int,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get a specific watchlist
    """
    result = await db.execute(
        select(Watchlist)
        .filter(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == current_user.id
        )
        .options(selectinload(Watchlist.symbols))
    )
    watchlist = result.scalar_one_or_none()

    if not watchlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Watchlist {watchlist_id} not found"
        )

    return watchlist.to_dict()


@router.put("/{watchlist_id}", response_model=WatchlistResponse)
async def update_watchlist(
    watchlist_id: int,
    request: WatchlistUpdate,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Update a watchlist
    """
    result = await db.execute(
        select(Watchlist)
        .filter(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == current_user.id
        )
    )
    watchlist = result.scalar_one_or_none()

    if not watchlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Watchlist {watchlist_id} not found"
        )

    # Update fields
    if request.name is not None:
        watchlist.name = request.name
    if request.description is not None:
        watchlist.description = request.description

    # Update symbols if provided
    if request.symbols is not None:
        # Remove old symbols
        await db.execute(
            delete(WatchlistSymbol).where(
                WatchlistSymbol.watchlist_id == watchlist_id
            )
        )

        # Add new symbols
        for i, symbol in enumerate(request.symbols):
            db_symbol = WatchlistSymbol(
                watchlist_id=watchlist_id,
                symbol=symbol.upper(),
                order=i
            )
            db.add(db_symbol)

    watchlist.updated_at = datetime.now(UTC)
    await db.commit()

    # Re-query with eager loading to get updated symbols
    result = await db.execute(
        select(Watchlist)
        .filter(Watchlist.id == watchlist_id)
        .options(selectinload(Watchlist.symbols))
    )
    watchlist = result.scalar_one()

    logger.info(f"User {current_user.id} updated watchlist {watchlist_id}")

    return watchlist.to_dict()


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    watchlist_id: int,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Delete a watchlist
    """
    result = await db.execute(
        select(Watchlist)
        .filter(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == current_user.id
        )
    )
    watchlist = result.scalar_one_or_none()

    if not watchlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Watchlist {watchlist_id} not found"
        )

    if watchlist.is_default:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete default watchlist"
        )

    # Delete the watchlist (cascade will delete symbols)
    await db.delete(watchlist)
    await db.commit()

    logger.info(f"User {current_user.id} deleted watchlist {watchlist_id}")


@router.post("/{watchlist_id}/symbols", response_model=WatchlistResponse)
async def add_symbol_to_watchlist(
    watchlist_id: int,
    request: WatchlistSymbolAdd,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Add a symbol to a watchlist
    """
    result = await db.execute(
        select(Watchlist)
        .filter(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == current_user.id
        )
    )
    watchlist = result.scalar_one_or_none()

    if not watchlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Watchlist {watchlist_id} not found"
        )

    # Check if symbol already exists
    result = await db.execute(
        select(WatchlistSymbol)
        .filter(
            WatchlistSymbol.watchlist_id == watchlist_id,
            WatchlistSymbol.symbol == request.symbol.upper()
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Symbol {request.symbol} already in watchlist"
        )

    # Get max order
    result = await db.execute(
        select(WatchlistSymbol)
        .filter(WatchlistSymbol.watchlist_id == watchlist_id)
    )
    symbols = result.scalars().all()
    max_order = len(symbols)

    # Add symbol
    db_symbol = WatchlistSymbol(
        watchlist_id=watchlist_id,
        symbol=request.symbol.upper(),
        order=max_order
    )
    db.add(db_symbol)

    watchlist.updated_at = datetime.now(UTC)
    await db.commit()

    # Re-query with eager loading to get updated symbols
    result = await db.execute(
        select(Watchlist)
        .filter(Watchlist.id == watchlist_id)
        .options(selectinload(Watchlist.symbols))
    )
    watchlist = result.scalar_one()

    logger.info(f"User {current_user.id} added symbol {request.symbol} to watchlist {watchlist_id}")

    return watchlist.to_dict()


@router.delete("/{watchlist_id}/symbols/{symbol}", response_model=WatchlistResponse)
async def remove_symbol_from_watchlist(
    watchlist_id: int,
    symbol: str,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Remove a symbol from a watchlist
    """
    result = await db.execute(
        select(Watchlist)
        .filter(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == current_user.id
        )
    )
    watchlist = result.scalar_one_or_none()

    if not watchlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Watchlist {watchlist_id} not found"
        )

    # Delete symbol
    result = await db.execute(
        delete(WatchlistSymbol).where(
            WatchlistSymbol.watchlist_id == watchlist_id,
            WatchlistSymbol.symbol == symbol.upper()
        )
    )

    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol {symbol} not found in watchlist"
        )

    watchlist.updated_at = datetime.now(UTC)
    await db.commit()

    # Re-query with eager loading to get updated symbols
    result = await db.execute(
        select(Watchlist)
        .filter(Watchlist.id == watchlist_id)
        .options(selectinload(Watchlist.symbols))
    )
    watchlist = result.scalar_one()

    logger.info(f"User {current_user.id} removed symbol {symbol} from watchlist {watchlist_id}")

    return watchlist.to_dict()


@router.put("/{watchlist_id}/symbols/reorder", response_model=WatchlistResponse)
async def reorder_watchlist_symbols(
    watchlist_id: int,
    request: WatchlistSymbolReorder,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Reorder symbols in a watchlist
    """
    result = await db.execute(
        select(Watchlist)
        .filter(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == current_user.id
        )
    )
    watchlist = result.scalar_one_or_none()

    if not watchlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Watchlist {watchlist_id} not found"
        )

    # Delete all symbols and re-add in new order
    await db.execute(
        delete(WatchlistSymbol).where(
            WatchlistSymbol.watchlist_id == watchlist_id
        )
    )

    for i, symbol in enumerate(request.symbols):
        db_symbol = WatchlistSymbol(
            watchlist_id=watchlist_id,
            symbol=symbol.upper(),
            order=i
        )
        db.add(db_symbol)

    watchlist.updated_at = datetime.now(UTC)
    await db.commit()

    # Re-query with eager loading to get updated symbols
    result = await db.execute(
        select(Watchlist)
        .filter(Watchlist.id == watchlist_id)
        .options(selectinload(Watchlist.symbols))
    )
    watchlist = result.scalar_one()

    logger.info(f"User {current_user.id} reordered symbols in watchlist {watchlist_id}")

    return watchlist.to_dict()


@router.get("/{watchlist_id}/quotes")
async def get_watchlist_quotes(
    watchlist_id: int,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get the latest quotes for the symbols in a watchlist.

    Returns a map keyed by symbol, the shape the Trading page reads:
    ``{symbol: {symbol, price, change, changePercent, bid, ask, timestamp[, error]}}``.
    ``price`` is the midpoint of the latest two-sided quote and ``timestamp`` is
    that quote's own exchange time; ``change``/``changePercent`` are null (a
    latest quote has no previous close). ``error`` explains a null price:
    ``no_quote``, ``no_two_sided_quote``, ``market_data_unavailable``,
    ``symbol_limit`` or ``unsupported_symbol``.

    Audit 2026-10-05 A8-01: no AlpacaClient is built per request (its
    constructor called get_account and logged account data) and no blocking
    call runs on the event loop. All symbols share ONE batched latest-quote
    request on the dashboard pool (timeout, no SDK retry sleeps) behind a
    process-wide 10 s cache, and at most WATCHLIST_QUOTE_SYMBOL_LIMIT symbols
    are looked up per request. The DB session is closed before the fetch is
    awaited.
    """
    result = await db.execute(
        select(Watchlist)
        .filter(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == current_user.id
        )
        .options(selectinload(Watchlist.symbols))
    )
    watchlist = result.scalar_one_or_none()

    if not watchlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Watchlist {watchlist_id} not found"
        )

    symbols = list(dict.fromkeys(
        s.symbol.strip().upper() for s in watchlist.symbols if s.symbol and s.symbol.strip()
    ))
    # The symbols are copied: end the read transaction and hand the pooled
    # connection (the pool the trading engine uses too) back before awaiting
    # market data, so a stalled quote fetch never holds a DB connection.
    await db.close()
    quotable = [s for s in symbols if _QUOTABLE_SYMBOL.fullmatch(s)]
    requested = quotable[:WATCHLIST_QUOTE_SYMBOL_LIMIT]
    batch = await dashboard_market_data.get_latest_quotes(requested) if requested else None
    requested_set = set(requested)

    quotes: dict[str, dict] = {}
    for symbol in symbols:
        quote = None
        if symbol not in requested_set:
            error = "symbol_limit" if _QUOTABLE_SYMBOL.fullmatch(symbol) else "unsupported_symbol"
        else:
            quote = batch.quotes.get(symbol)
            if quote is None:
                error = "market_data_unavailable" if symbol in batch.unavailable else "no_quote"
            else:
                error = None if quote.price is not None else "no_two_sided_quote"
        quotes[symbol] = _quote_entry(symbol, quote, error)
    return quotes


def _quote_entry(symbol: str, quote, error: str | None) -> dict:
    entry = {
        "symbol": symbol,
        "price": quote.price if quote is not None else None,
        # A latest quote carries no previous close; the card shows price only.
        "change": None,
        "changePercent": None,
        "bid": quote.bid if quote is not None else None,
        "ask": quote.ask if quote is not None else None,
        "timestamp": quote.timestamp if quote is not None else None,
    }
    if error:
        entry["error"] = error
    return entry
