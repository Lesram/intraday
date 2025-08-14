"""
Broker mock helpers for testing Alpaca integration.
Provides respx-based mocking for Alpaca API endpoints.
"""

from datetime import UTC, datetime
from decimal import Decimal
import json
from typing import Any
import uuid

from httpx import Response
import respx


class AlpacaMockResponder:
    """Mock responder for Alpaca API endpoints."""

    def __init__(self, base_url: str = "https://paper-api.alpaca.markets"):
        self.base_url = base_url.rstrip("/")
        self.orders_db: dict[str, dict[str, Any]] = {}
        self.positions_db: dict[str, dict[str, Any]] = {}
        self.account_data = self._default_account()

    def _default_account(self) -> dict[str, Any]:
        """Default account data for mocking."""
        return {
            "id": "test-account-123",
            "account_number": "123456789",
            "status": "ACTIVE",
            "currency": "USD",
            "buying_power": "100000.00",
            "cash": "100000.00",
            "portfolio_value": "100000.00",
            "equity": "100000.00",
            "last_equity": "100000.00",
            "multiplier": "4",
            "created_at": "2023-01-01T00:00:00Z",
            "trading_blocked": False,
            "transfers_blocked": False,
            "account_blocked": False,
            "trade_suspended_by_user": False,
            "pattern_day_trader": False,
            "day_trading_buying_power": "400000.00",
            "max_day_trading_buying_power": "400000.00",
        }

    def setup_responders(self, respx_mock: respx.MockRouter) -> None:
        """Set up all mock responders."""
        self.setup_account_responders(respx_mock)
        self.setup_orders_responders(respx_mock)
        self.setup_positions_responders(respx_mock)
        self.setup_market_data_responders(respx_mock)

    def setup_account_responders(self, respx_mock: respx.MockRouter) -> None:
        """Set up account-related mock responders."""

        # GET /v2/account
        respx_mock.get(f"{self.base_url}/v2/account").mock(
            return_value=Response(200, json=self.account_data)
        )

        # Health check endpoint
        respx_mock.get(f"{self.base_url}/v2/clock").mock(
            return_value=Response(
                200,
                json={
                    "timestamp": datetime.now(UTC).isoformat(),
                    "is_open": True,
                    "next_open": "2023-12-04T14:30:00-05:00",
                    "next_close": "2023-12-04T21:00:00-05:00",
                },
            )
        )

    def setup_orders_responders(self, respx_mock: respx.MockRouter) -> None:
        """Set up order-related mock responders."""

        # POST /v2/orders - Submit order
        def submit_order_handler(request):
            try:
                order_data = json.loads(request.content.decode())
                order_id = str(uuid.uuid4())

                # Create order record
                order = {
                    "id": order_id,
                    "client_order_id": order_data.get(
                        "client_order_id", str(uuid.uuid4())
                    ),
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                    "submitted_at": datetime.now(UTC).isoformat(),
                    "filled_at": None,
                    "expired_at": None,
                    "canceled_at": None,
                    "failed_at": None,
                    "asset_id": f"asset-{order_data['symbol']}",
                    "symbol": order_data["symbol"],
                    "asset_class": "us_equity",
                    "qty": order_data["qty"],
                    "filled_qty": "0",
                    "type": order_data["type"],
                    "side": order_data["side"],
                    "time_in_force": order_data.get("time_in_force", "day"),
                    "limit_price": order_data.get("limit_price"),
                    "stop_price": order_data.get("stop_price"),
                    "status": "submitted",
                    "extended_hours": order_data.get("extended_hours", False),
                    "legs": None,
                }

                # Store in mock database
                self.orders_db[order_id] = order

                return Response(201, json=order)

            except Exception as e:
                return Response(
                    400,
                    json={"code": 40010001, "message": f"Invalid order data: {str(e)}"},
                )

        respx_mock.post(f"{self.base_url}/v2/orders").mock(
            side_effect=submit_order_handler
        )

        # GET /v2/orders/{order_id} - Get order by ID
        def get_order_handler(request):
            order_id = request.url.path.split("/")[-1]
            if order_id in self.orders_db:
                return Response(200, json=self.orders_db[order_id])
            else:
                return Response(
                    404, json={"code": 40410000, "message": "Order not found"}
                )

        respx_mock.get(f"{self.base_url}/v2/orders").mock(
            return_value=Response(200, json=list(self.orders_db.values()))
        )

        respx_mock.get(f"{self.base_url}/v2/orders/{respx.patterns.STR}").mock(
            side_effect=get_order_handler
        )

        # DELETE /v2/orders/{order_id} - Cancel order
        def cancel_order_handler(request):
            order_id = request.url.path.split("/")[-1]
            if order_id in self.orders_db:
                order = self.orders_db[order_id]
                if order["status"] in ["submitted", "accepted", "pending_new"]:
                    order["status"] = "canceled"
                    order["canceled_at"] = datetime.now(UTC).isoformat()
                    order["updated_at"] = datetime.now(UTC).isoformat()
                    return Response(204)
                else:
                    return Response(
                        422,
                        json={"code": 42210000, "message": "Order cannot be canceled"},
                    )
            else:
                return Response(
                    404, json={"code": 40410000, "message": "Order not found"}
                )

        respx_mock.delete(f"{self.base_url}/v2/orders/{respx.patterns.STR}").mock(
            side_effect=cancel_order_handler
        )

    def setup_positions_responders(self, respx_mock: respx.MockRouter) -> None:
        """Set up positions-related mock responders."""

        # GET /v2/positions
        respx_mock.get(f"{self.base_url}/v2/positions").mock(
            return_value=Response(200, json=list(self.positions_db.values()))
        )

        # GET /v2/positions/{symbol}
        def get_position_handler(request):
            symbol = request.url.path.split("/")[-1]
            if symbol in self.positions_db:
                return Response(200, json=self.positions_db[symbol])
            else:
                return Response(
                    404, json={"code": 40410000, "message": "Position not found"}
                )

        respx_mock.get(f"{self.base_url}/v2/positions/{respx.patterns.STR}").mock(
            side_effect=get_position_handler
        )

    def setup_market_data_responders(self, respx_mock: respx.MockRouter) -> None:
        """Set up market data mock responders."""

        # GET /v2/stocks/{symbol}/quotes/latest
        def get_quote_handler(request):
            symbol = request.url.path.split("/")[-3]  # Extract symbol from path
            return Response(
                200,
                json={
                    "quote": {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "bid": 100.50,
                        "ask": 100.52,
                        "bid_size": 100,
                        "ask_size": 200,
                        "exchange": "NASDAQ",
                    },
                    "symbol": symbol,
                },
            )

        respx_mock.get(
            f"{self.base_url}/v2/stocks/{respx.patterns.STR}/quotes/latest"
        ).mock(side_effect=get_quote_handler)

    def add_order(self, order_data: dict[str, Any]) -> str:
        """Add a mock order to the database."""
        order_id = str(uuid.uuid4())
        order = {
            "id": order_id,
            "client_order_id": order_data.get("client_order_id", str(uuid.uuid4())),
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "submitted_at": datetime.now(UTC).isoformat(),
            "filled_at": None,
            "expired_at": None,
            "canceled_at": None,
            "failed_at": None,
            "asset_id": f"asset-{order_data['symbol']}",
            "symbol": order_data["symbol"],
            "asset_class": "us_equity",
            "qty": str(order_data["qty"]),
            "filled_qty": "0",
            "type": order_data.get("type", "market"),
            "side": order_data["side"],
            "time_in_force": order_data.get("time_in_force", "day"),
            "limit_price": order_data.get("limit_price"),
            "stop_price": order_data.get("stop_price"),
            "status": "submitted",
            "extended_hours": order_data.get("extended_hours", False),
            "legs": None,
        }

        self.orders_db[order_id] = order
        return order_id

    def fill_order(
        self, order_id: str, fill_qty: str | None = None, fill_price: str | None = None
    ) -> None:
        """Mark an order as filled."""
        if order_id not in self.orders_db:
            raise ValueError(f"Order {order_id} not found")

        order = self.orders_db[order_id]
        fill_qty = fill_qty or order["qty"]
        fill_price = fill_price or "100.50"

        order["status"] = "filled"
        order["filled_qty"] = fill_qty
        order["filled_at"] = datetime.now(UTC).isoformat()
        order["updated_at"] = datetime.now(UTC).isoformat()

        # Update positions
        symbol = order["symbol"]
        qty_change = Decimal(fill_qty) * (1 if order["side"] == "buy" else -1)

        if symbol in self.positions_db:
            position = self.positions_db[symbol]
            current_qty = Decimal(position["qty"])
            new_qty = current_qty + qty_change
            position["qty"] = str(new_qty)
            position["market_value"] = str(new_qty * Decimal(fill_price))
        else:
            self.positions_db[symbol] = {
                "asset_id": f"asset-{symbol}",
                "symbol": symbol,
                "exchange": "NASDAQ",
                "asset_class": "us_equity",
                "qty": str(qty_change),
                "avg_entry_price": fill_price,
                "side": "long" if qty_change > 0 else "short",
                "market_value": str(qty_change * Decimal(fill_price)),
                "cost_basis": str(abs(qty_change) * Decimal(fill_price)),
                "unrealized_pl": "0.00",
                "unrealized_plpc": "0.0000",
                "unrealized_intraday_pl": "0.00",
                "unrealized_intraday_plpc": "0.0000",
                "current_price": fill_price,
                "lastday_price": fill_price,
                "change_today": "0.00",
            }

    def add_position(self, symbol: str, qty: str, avg_price: str = "100.50") -> None:
        """Add a mock position."""
        qty_decimal = Decimal(qty)
        price_decimal = Decimal(avg_price)

        self.positions_db[symbol] = {
            "asset_id": f"asset-{symbol}",
            "symbol": symbol,
            "exchange": "NASDAQ",
            "asset_class": "us_equity",
            "qty": qty,
            "avg_entry_price": avg_price,
            "side": "long" if qty_decimal > 0 else "short",
            "market_value": str(qty_decimal * price_decimal),
            "cost_basis": str(abs(qty_decimal) * price_decimal),
            "unrealized_pl": "0.00",
            "unrealized_plpc": "0.0000",
            "unrealized_intraday_pl": "0.00",
            "unrealized_intraday_plpc": "0.0000",
            "current_price": avg_price,
            "lastday_price": avg_price,
            "change_today": "0.00",
        }

    def reset(self) -> None:
        """Reset all mock data."""
        self.orders_db.clear()
        self.positions_db.clear()
        self.account_data = self._default_account()


# Factory functions for common test scenarios


def create_fault_responder(
    base_url: str = "https://paper-api.alpaca.markets",
) -> respx.MockRouter:
    """Create a responder that simulates various broker faults."""
    mock = respx.MockRouter()
    base_url = base_url.rstrip("/")

    # Always return 502 Bad Gateway
    mock.post(f"{base_url}/v2/orders").mock(
        return_value=Response(502, json={"message": "Bad Gateway"})
    )

    # Timeout simulation (very slow response)
    mock.get(f"{base_url}/v2/account").mock(
        return_value=Response(200, json={"status": "timeout_simulation"})
    )

    return mock


def create_flaky_responder(
    base_url: str = "https://paper-api.alpaca.markets", success_rate: float = 0.7
) -> respx.MockRouter:
    """Create a responder that succeeds only some percentage of the time."""
    import random

    mock = respx.MockRouter()
    base_url = base_url.rstrip("/")

    def flaky_handler(request):
        if random.random() < success_rate:
            # Success case
            order_id = str(uuid.uuid4())
            return Response(
                201,
                json={
                    "id": order_id,
                    "status": "submitted",
                    "symbol": "AAPL",
                    "qty": "100",
                    "side": "buy",
                    "type": "market",
                    "created_at": datetime.now(UTC).isoformat(),
                },
            )
        else:
            # Failure case
            return Response(500, json={"message": "Internal Server Error"})

    mock.post(f"{base_url}/v2/orders").mock(side_effect=flaky_handler)

    return mock


def create_backoff_responder(
    base_url: str = "https://paper-api.alpaca.markets", fail_count: int = 2
) -> respx.MockRouter:
    """Create a responder that fails N times then succeeds (for backoff testing)."""
    mock = respx.MockRouter()
    base_url = base_url.rstrip("/")

    call_count = {"count": 0}

    def backoff_handler(request):
        call_count["count"] += 1

        if call_count["count"] <= fail_count:
            # Fail with 502
            return Response(
                502, json={"message": f"Failure attempt {call_count['count']}"}
            )
        else:
            # Success
            order_id = str(uuid.uuid4())
            return Response(
                201,
                json={
                    "id": order_id,
                    "status": "submitted",
                    "symbol": "AAPL",
                    "qty": "100",
                    "side": "buy",
                    "type": "market",
                    "created_at": datetime.now(UTC).isoformat(),
                },
            )

    mock.post(f"{base_url}/v2/orders").mock(side_effect=backoff_handler)

    return mock
