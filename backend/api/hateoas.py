"""
HATEOAS Links Helper (L-06)

Provides utilities for adding HATEOAS (Hypermedia as the Engine of Application State)
links to API responses, enabling discoverability and navigation of the REST API.

Usage:
    from backend.api.hateoas import HATEOASLinks, add_hateoas_links
    
    @router.get("/orders/{order_id}")
    async def get_order(order_id: str):
        order = await fetch_order(order_id)
        return add_hateoas_links(
            order,
            HATEOASLinks.for_order(order_id)
        )
"""

from typing import Any
from urllib.parse import urljoin

from pydantic import BaseModel


class Link(BaseModel):
    """HATEOAS link representation."""
    href: str
    rel: str
    method: str = "GET"
    title: str | None = None


class HATEOASResponse(BaseModel):
    """Base response with HATEOAS links."""
    _links: dict[str, Link | list[Link]] = {}


# API base path
API_V1_PREFIX = "/api/v1"


class HATEOASLinks:
    """Factory for creating HATEOAS links for different resources."""

    @staticmethod
    def _build_url(path: str) -> str:
        """Build full API URL from path."""
        return f"{API_V1_PREFIX}{path}"

    # =========================================================================
    # Order Links
    # =========================================================================

    @classmethod
    def for_order(cls, order_id: str) -> dict[str, Any]:
        """Generate HATEOAS links for a single order."""
        return {
            "_links": {
                "self": {
                    "href": cls._build_url(f"/orders/{order_id}"),
                    "method": "GET",
                },
                "cancel": {
                    "href": cls._build_url(f"/orders/{order_id}/cancel"),
                    "method": "POST",
                    "title": "Cancel this order",
                },
                "collection": {
                    "href": cls._build_url("/orders"),
                    "method": "GET",
                    "title": "All orders",
                },
                "trades": {
                    "href": cls._build_url(f"/trades?order_id={order_id}"),
                    "method": "GET",
                    "title": "Trades for this order",
                },
            }
        }

    @classmethod
    def for_orders_collection(
        cls,
        limit: int = 100,
        cursor: str | None = None,
        next_cursor: str | None = None,
    ) -> dict[str, Any]:
        """Generate HATEOAS links for orders collection."""
        links: dict[str, Any] = {
            "self": {
                "href": cls._build_url(f"/orders?limit={limit}" + (f"&cursor={cursor}" if cursor else "")),
                "method": "GET",
            },
            "create": {
                "href": cls._build_url("/orders"),
                "method": "POST",
                "title": "Create new order",
            },
        }

        if next_cursor:
            links["next"] = {
                "href": cls._build_url(f"/orders?limit={limit}&cursor={next_cursor}"),
                "method": "GET",
                "title": "Next page",
            }

        return {"_links": links}

    # =========================================================================
    # Position Links
    # =========================================================================

    @classmethod
    def for_position(cls, symbol: str) -> dict[str, Any]:
        """Generate HATEOAS links for a single position."""
        return {
            "_links": {
                "self": {
                    "href": cls._build_url(f"/positions/{symbol}"),
                    "method": "GET",
                },
                "close": {
                    "href": cls._build_url(f"/positions/{symbol}/close"),
                    "method": "POST",
                    "title": "Close this position",
                },
                "collection": {
                    "href": cls._build_url("/positions"),
                    "method": "GET",
                    "title": "All positions",
                },
                "orders": {
                    "href": cls._build_url(f"/orders?symbol={symbol}"),
                    "method": "GET",
                    "title": "Orders for this symbol",
                },
                "trades": {
                    "href": cls._build_url(f"/trades?symbol={symbol}"),
                    "method": "GET",
                    "title": "Trades for this symbol",
                },
                "quote": {
                    "href": cls._build_url(f"/market/quotes/{symbol}"),
                    "method": "GET",
                    "title": "Current quote",
                },
            }
        }

    @classmethod
    def for_positions_collection(cls) -> dict[str, Any]:
        """Generate HATEOAS links for positions collection."""
        return {
            "_links": {
                "self": {
                    "href": cls._build_url("/positions"),
                    "method": "GET",
                },
                "portfolio": {
                    "href": cls._build_url("/portfolio"),
                    "method": "GET",
                    "title": "Portfolio summary",
                },
                "close_all": {
                    "href": cls._build_url("/positions/close-all"),
                    "method": "POST",
                    "title": "Close all positions",
                },
            }
        }

    # =========================================================================
    # Strategy Links
    # =========================================================================

    @classmethod
    def for_strategy(cls, strategy_id: str) -> dict[str, Any]:
        """Generate HATEOAS links for a single strategy."""
        return {
            "_links": {
                "self": {
                    "href": cls._build_url(f"/strategies/{strategy_id}"),
                    "method": "GET",
                },
                "update": {
                    "href": cls._build_url(f"/strategies/{strategy_id}"),
                    "method": "PUT",
                    "title": "Update strategy",
                },
                "delete": {
                    "href": cls._build_url(f"/strategies/{strategy_id}"),
                    "method": "DELETE",
                    "title": "Delete strategy",
                },
                "start": {
                    "href": cls._build_url(f"/strategies/{strategy_id}/start"),
                    "method": "POST",
                    "title": "Start strategy",
                },
                "stop": {
                    "href": cls._build_url(f"/strategies/{strategy_id}/stop"),
                    "method": "POST",
                    "title": "Stop strategy",
                },
                "collection": {
                    "href": cls._build_url("/strategies"),
                    "method": "GET",
                    "title": "All strategies",
                },
                "orders": {
                    "href": cls._build_url(f"/orders?strategy_id={strategy_id}"),
                    "method": "GET",
                    "title": "Orders from this strategy",
                },
                "performance": {
                    "href": cls._build_url(f"/strategies/{strategy_id}/performance"),
                    "method": "GET",
                    "title": "Strategy performance metrics",
                },
                "backtest": {
                    "href": cls._build_url(f"/strategies/{strategy_id}/backtest"),
                    "method": "POST",
                    "title": "Run backtest",
                },
            }
        }

    @classmethod
    def for_strategies_collection(cls) -> dict[str, Any]:
        """Generate HATEOAS links for strategies collection."""
        return {
            "_links": {
                "self": {
                    "href": cls._build_url("/strategies"),
                    "method": "GET",
                },
                "create": {
                    "href": cls._build_url("/strategies"),
                    "method": "POST",
                    "title": "Create new strategy",
                },
                "templates": {
                    "href": cls._build_url("/strategies/templates"),
                    "method": "GET",
                    "title": "Strategy templates",
                },
            }
        }

    # =========================================================================
    # Trade Links
    # =========================================================================

    @classmethod
    def for_trade(cls, trade_id: str) -> dict[str, Any]:
        """Generate HATEOAS links for a single trade."""
        return {
            "_links": {
                "self": {
                    "href": cls._build_url(f"/trades/{trade_id}"),
                    "method": "GET",
                },
                "collection": {
                    "href": cls._build_url("/trades"),
                    "method": "GET",
                    "title": "All trades",
                },
            }
        }

    @classmethod
    def for_trades_collection(
        cls,
        limit: int = 100,
        cursor: str | None = None,
        next_cursor: str | None = None,
    ) -> dict[str, Any]:
        """Generate HATEOAS links for trades collection."""
        links: dict[str, Any] = {
            "self": {
                "href": cls._build_url(f"/trades?limit={limit}" + (f"&cursor={cursor}" if cursor else "")),
                "method": "GET",
            },
            "analytics": {
                "href": cls._build_url("/trades/analytics"),
                "method": "GET",
                "title": "Trade analytics",
            },
            "export": {
                "href": cls._build_url("/trades/export"),
                "method": "GET",
                "title": "Export trades",
            },
        }

        if next_cursor:
            links["next"] = {
                "href": cls._build_url(f"/trades?limit={limit}&cursor={next_cursor}"),
                "method": "GET",
                "title": "Next page",
            }

        return {"_links": links}

    # =========================================================================
    # Portfolio Links
    # =========================================================================

    @classmethod
    def for_portfolio(cls) -> dict[str, Any]:
        """Generate HATEOAS links for portfolio."""
        return {
            "_links": {
                "self": {
                    "href": cls._build_url("/portfolio"),
                    "method": "GET",
                },
                "positions": {
                    "href": cls._build_url("/positions"),
                    "method": "GET",
                    "title": "All positions",
                },
                "orders": {
                    "href": cls._build_url("/orders"),
                    "method": "GET",
                    "title": "All orders",
                },
                "trades": {
                    "href": cls._build_url("/trades"),
                    "method": "GET",
                    "title": "Trade history",
                },
                "history": {
                    "href": cls._build_url("/portfolio/history"),
                    "method": "GET",
                    "title": "Portfolio value history",
                },
            }
        }


def add_hateoas_links(data: dict[str, Any], links: dict[str, Any]) -> dict[str, Any]:
    """
    Add HATEOAS links to a response dictionary.
    
    Args:
        data: The response data dictionary
        links: HATEOAS links from HATEOASLinks factory
        
    Returns:
        Combined dictionary with data and _links
    """
    return {**data, **links}


def add_collection_hateoas(
    items: list[dict],
    collection_links: dict[str, Any],
    item_link_fn: callable,
    id_field: str = "id",
) -> dict[str, Any]:
    """
    Add HATEOAS links to a collection response.
    
    Args:
        items: List of item dictionaries
        collection_links: Links for the collection itself
        item_link_fn: Function to generate links for each item
        id_field: Field name containing the item ID
        
    Returns:
        Response with items and collection links
    """
    # Add links to each item
    items_with_links = []
    for item in items:
        item_id = item.get(id_field, item.get("order_id", item.get("strategy_id")))
        if item_id:
            item_links = item_link_fn(item_id)
            items_with_links.append({**item, **item_links})
        else:
            items_with_links.append(item)

    return {
        "items": items_with_links,
        **collection_links,
    }
