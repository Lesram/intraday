"""
Cursor-Based Pagination (L-07)

Provides cursor-based pagination for high-volume endpoints like orders and trades.
Uses created_at + id as a composite cursor for stable pagination.

Usage:
    from backend.api.pagination import CursorPagination, encode_cursor, decode_cursor
    
    @router.get("/orders")
    async def list_orders(
        cursor: str | None = None,
        limit: int = Query(default=100, le=500),
    ):
        pagination = CursorPagination(cursor=cursor, limit=limit)
        
        # Apply to query
        query = select(Order).order_by(Order.created_at.desc(), Order.id.desc())
        if pagination.cursor_data:
            query = query.where(
                (Order.created_at, Order.id) < (pagination.cursor_data.created_at, pagination.cursor_data.id)
            )
        query = query.limit(pagination.limit + 1)  # Fetch one extra to check for next page
        
        # Execute and paginate
        results = list(await db.execute(query))
        return pagination.paginate(results, id_field="id", created_at_field="created_at")
"""

import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class CursorData:
    """Decoded cursor containing pagination position."""
    created_at: datetime
    id: str
    
    def to_tuple(self) -> tuple[datetime, str]:
        """Return as tuple for SQL comparison."""
        return (self.created_at, self.id)


class PaginationMeta(BaseModel):
    """Pagination metadata for response."""
    limit: int
    has_next: bool
    next_cursor: str | None = None
    has_prev: bool = False
    prev_cursor: str | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response with cursor information."""
    items: list[Any]
    pagination: PaginationMeta


def encode_cursor(created_at: datetime, id: str) -> str:
    """
    Encode a cursor from created_at timestamp and id.
    
    Args:
        created_at: Timestamp for ordering
        id: Unique identifier for tie-breaking
        
    Returns:
        Base64-encoded cursor string
    """
    cursor_data = {
        "c": created_at.isoformat(),
        "i": str(id),
    }
    cursor_json = json.dumps(cursor_data, separators=(",", ":"))
    return base64.urlsafe_b64encode(cursor_json.encode()).decode()


def decode_cursor(cursor: str) -> CursorData | None:
    """
    Decode a cursor string into its components.
    
    Args:
        cursor: Base64-encoded cursor string
        
    Returns:
        CursorData with created_at and id, or None if invalid
    """
    try:
        cursor_json = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(cursor_json)
        return CursorData(
            created_at=datetime.fromisoformat(data["c"]),
            id=data["i"],
        )
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        logger.warning(f"Invalid cursor: {cursor}, error: {e}")
        return None


class CursorPagination:
    """
    Cursor-based pagination helper.
    
    Advantages over offset pagination:
    - Stable results even when data is inserted/deleted
    - Efficient for large datasets (no OFFSET scan)
    - Works well with infinite scroll UIs
    """

    def __init__(
        self,
        cursor: str | None = None,
        limit: int = 100,
        max_limit: int = 500,
    ):
        """
        Initialize pagination.
        
        Args:
            cursor: Encoded cursor from previous request
            limit: Number of items to return
            max_limit: Maximum allowed limit
        """
        self.cursor = cursor
        self.limit = min(limit, max_limit)
        self.cursor_data = decode_cursor(cursor) if cursor else None

    def paginate(
        self,
        items: list[Any],
        id_field: str = "id",
        created_at_field: str = "created_at",
    ) -> dict[str, Any]:
        """
        Process query results and generate pagination response.
        
        Args:
            items: List of items (should include limit + 1 for next page check)
            id_field: Name of the ID field
            created_at_field: Name of the created_at field
            
        Returns:
            Dict with 'items' and 'pagination' keys
        """
        has_next = len(items) > self.limit
        
        # Trim to actual limit
        if has_next:
            items = items[:self.limit]

        # Generate next cursor from last item
        next_cursor = None
        if has_next and items:
            last_item = items[-1]
            
            # Handle both dict and object access
            if isinstance(last_item, dict):
                last_created_at = last_item[created_at_field]
                last_id = last_item[id_field]
            else:
                last_created_at = getattr(last_item, created_at_field)
                last_id = getattr(last_item, id_field)
            
            # Ensure datetime
            if isinstance(last_created_at, str):
                last_created_at = datetime.fromisoformat(last_created_at.replace("Z", "+00:00"))
            
            next_cursor = encode_cursor(last_created_at, str(last_id))

        return {
            "items": items,
            "pagination": {
                "limit": self.limit,
                "has_next": has_next,
                "next_cursor": next_cursor,
                "has_prev": self.cursor is not None,
            },
        }

    def apply_to_query(self, query, model, descending: bool = True):
        """
        Apply cursor pagination to a SQLAlchemy query.
        
        Args:
            query: SQLAlchemy select query
            model: SQLAlchemy model class
            descending: Whether to order descending (newest first)
            
        Returns:
            Modified query with ordering and cursor filter
        """
        from sqlalchemy import and_, or_, tuple_

        # Apply ordering
        if descending:
            query = query.order_by(model.created_at.desc(), model.id.desc())
        else:
            query = query.order_by(model.created_at.asc(), model.id.asc())

        # Apply cursor filter
        if self.cursor_data:
            if descending:
                # For descending: get items older than cursor
                query = query.where(
                    or_(
                        model.created_at < self.cursor_data.created_at,
                        and_(
                            model.created_at == self.cursor_data.created_at,
                            model.id < self.cursor_data.id,
                        ),
                    )
                )
            else:
                # For ascending: get items newer than cursor
                query = query.where(
                    or_(
                        model.created_at > self.cursor_data.created_at,
                        and_(
                            model.created_at == self.cursor_data.created_at,
                            model.id > self.cursor_data.id,
                        ),
                    )
                )

        # Fetch one extra to check for next page
        query = query.limit(self.limit + 1)

        return query


# Type alias for common use
CursorParam = str | None


class CursorPaginationParams(BaseModel):
    """Pydantic model for cursor pagination query parameters."""
    
    cursor: str | None = Field(
        default=None,
        description="Pagination cursor from previous response",
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Number of items to return (max 500)",
    )
