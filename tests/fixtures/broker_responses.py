"""
Broker response fixtures for testing order execution flows.
"""

import json
from typing import Any

# Alpaca API response samples
ALPACA_ORDER_RESPONSES = {
    "filled_buy_order": {
        "id": "61766bed-9ec6-4ad6-b96e-55d0a9db0c96",
        "client_order_id": "my_order_001",
        "created_at": "2024-01-02T09:30:15Z",
        "updated_at": "2024-01-02T09:30:16Z",
        "submitted_at": "2024-01-02T09:30:15Z",
        "filled_at": "2024-01-02T09:30:16Z",
        "expired_at": None,
        "canceled_at": None,
        "failed_at": None,
        "replaced_at": None,
        "replaced_by": None,
        "replaces": None,
        "asset_id": "904837e3-3b76-47ec-b432-046db621571b",
        "symbol": "AAPL",
        "asset_class": "us_equity",
        "notional": None,
        "qty": "100",
        "filled_qty": "100",
        "filled_avg_price": "185.50",
        "order_class": "",
        "order_type": "market",
        "type": "market",
        "side": "buy",
        "time_in_force": "day",
        "limit_price": None,
        "stop_price": None,
        "status": "filled",
        "extended_hours": False,
        "legs": None,
        "trail_percent": None,
        "trail_price": None,
        "hwm": None,
    },
    "partial_fill": {
        "id": "61766bed-9ec6-4ad6-b96e-55d0a9db0c97",
        "client_order_id": "my_order_002",
        "created_at": "2024-01-02T10:30:15Z",
        "updated_at": "2024-01-02T10:30:18Z",
        "submitted_at": "2024-01-02T10:30:15Z",
        "filled_at": None,
        "symbol": "AAPL",
        "qty": "1000",
        "filled_qty": "250",
        "filled_avg_price": "186.25",
        "order_type": "limit",
        "side": "sell",
        "time_in_force": "day",
        "limit_price": "186.50",
        "status": "partially_filled",
    },
    "rejected_order": {
        "id": "61766bed-9ec6-4ad6-b96e-55d0a9db0c98",
        "client_order_id": "my_order_003",
        "created_at": "2024-01-02T11:30:15Z",
        "updated_at": "2024-01-02T11:30:15Z",
        "submitted_at": "2024-01-02T11:30:15Z",
        "failed_at": "2024-01-02T11:30:15Z",
        "symbol": "AAPL",
        "qty": "10000",
        "filled_qty": "0",
        "order_type": "market",
        "side": "buy",
        "status": "rejected",
        "rejected_reason": "insufficient_buying_power",
    },
    "canceled_order": {
        "id": "61766bed-9ec6-4ad6-b96e-55d0a9db0c99",
        "client_order_id": "my_order_004",
        "created_at": "2024-01-02T12:30:15Z",
        "updated_at": "2024-01-02T12:35:20Z",
        "submitted_at": "2024-01-02T12:30:15Z",
        "canceled_at": "2024-01-02T12:35:20Z",
        "symbol": "AAPL",
        "qty": "500",
        "filled_qty": "0",
        "order_type": "limit",
        "side": "sell",
        "limit_price": "190.00",
        "status": "canceled",
    },
}

ALPACA_ACCOUNT_RESPONSE = {
    "id": "e6fe16f3-64a4-4921-8928-cadf02f92f98",
    "account_number": "123456789",
    "status": "ACTIVE",
    "crypto_status": "ACTIVE",
    "currency": "USD",
    "buying_power": "50000.00",
    "regt_buying_power": "50000.00",
    "daytrading_buying_power": "100000.00",
    "non_marginable_buying_power": "25000.00",
    "cash": "25000.00",
    "accrued_fees": "0.00",
    "pending_transfer_in": "0.00",
    "pending_transfer_out": "0.00",
    "portfolio_value": "75000.00",
    "pattern_day_trader": True,
    "trading_blocked": False,
    "transfers_blocked": False,
    "account_blocked": False,
    "created_at": "2023-01-15T12:00:00Z",
    "trade_suspended_by_user": False,
    "multiplier": "2",
    "shorting_enabled": True,
    "equity": "75000.00",
    "last_equity": "74500.00",
    "long_market_value": "50000.00",
    "short_market_value": "0.00",
    "initial_margin": "25000.00",
    "maintenance_margin": "15000.00",
    "sma": "0.00",
    "daytrade_count": "2",
}

ALPACA_POSITION_RESPONSE = {
    "asset_id": "904837e3-3b76-47ec-b432-046db621571b",
    "symbol": "AAPL",
    "exchange": "NASDAQ",
    "asset_class": "us_equity",
    "avg_entry_price": "185.75",
    "qty": "100",
    "side": "long",
    "market_value": "18650.00",
    "cost_basis": "18575.00",
    "unrealized_pl": "75.00",
    "unrealized_plpc": "0.004",
    "unrealized_intraday_pl": "25.00",
    "unrealized_intraday_plpc": "0.0013",
    "current_price": "186.50",
    "lastday_price": "186.25",
    "change_today": "0.25",
    "swap_rate": None,
    "avg_entry_swap_rate": None,
    "usd": None,
    "qty_available": "100",
}

# Mock broker adapter responses for different scenarios
MOCK_BROKER_RESPONSES = {
    "connection_success": {
        "status": "connected",
        "timestamp": "2024-01-02T09:30:00Z",
        "account_id": "test_account_123",
        "broker": "mock_broker",
    },
    "connection_failure": {
        "status": "error",
        "timestamp": "2024-01-02T09:30:00Z",
        "error": "authentication_failed",
        "message": "Invalid API credentials",
    },
    "rate_limit": {
        "status": "error",
        "timestamp": "2024-01-02T09:30:00Z",
        "error": "rate_limit_exceeded",
        "message": "Too many requests. Retry after 60 seconds.",
        "retry_after": 60,
    },
    "market_closed": {
        "status": "error",
        "timestamp": "2024-01-02T20:30:00Z",
        "error": "market_closed",
        "message": "Market is closed. Orders will be queued for next session.",
    },
    "symbol_not_found": {
        "status": "error",
        "error": "invalid_symbol",
        "message": "Symbol 'INVALID' not found",
        "symbol": "INVALID",
    },
}

# WebSocket message samples
WEBSOCKET_MESSAGES = {
    "trade_update": {
        "stream": "trade_updates",
        "data": {
            "event": "fill",
            "order": {
                "id": "61766bed-9ec6-4ad6-b96e-55d0a9db0c96",
                "client_order_id": "my_order_001",
                "symbol": "AAPL",
                "side": "buy",
                "qty": "100",
                "filled_qty": "100",
                "filled_avg_price": "185.50",
                "status": "filled",
                "timestamp": "2024-01-02T09:30:16Z",
            },
        },
    },
    "market_data": {
        "stream": "trade",
        "data": {
            "symbol": "AAPL",
            "price": 185.50,
            "size": 100,
            "timestamp": "2024-01-02T09:30:16.123456Z",
            "conditions": ["@"],
            "exchange": "NASDAQ",
        },
    },
    "quote_update": {
        "stream": "quote",
        "data": {
            "symbol": "AAPL",
            "bid_price": 185.48,
            "bid_size": 100,
            "ask_price": 185.52,
            "ask_size": 200,
            "timestamp": "2024-01-02T09:30:16.123456Z",
        },
    },
}

# Risk manager responses
RISK_RESPONSES = {
    "approved": {
        "approved": True,
        "risk_score": 0.25,
        "checks_passed": ["position_size", "concentration", "volatility"],
        "position_limit_used": 0.15,
        "portfolio_impact": 0.02,
        "message": "Trade approved",
    },
    "rejected_position_limit": {
        "approved": False,
        "risk_score": 0.95,
        "checks_failed": ["position_size"],
        "position_limit_used": 1.1,
        "portfolio_impact": 0.25,
        "message": "Position size exceeds risk limits",
        "reason": "position_size_exceeded",
    },
    "rejected_concentration": {
        "approved": False,
        "risk_score": 0.85,
        "checks_failed": ["concentration"],
        "sector_exposure": 0.6,
        "symbol_exposure": 0.15,
        "message": "Trade would exceed concentration limits",
        "reason": "concentration_limit_exceeded",
    },
}


def get_broker_response(scenario: str) -> dict[str, Any]:
    """Get a broker response for a specific scenario."""
    responses = {
        **ALPACA_ORDER_RESPONSES,
        **MOCK_BROKER_RESPONSES,
        **RISK_RESPONSES,
    }
    return responses.get(scenario, {})


def get_websocket_message(msg_type: str) -> dict[str, Any]:
    """Get a WebSocket message for testing."""
    return WEBSOCKET_MESSAGES.get(msg_type, {})


def save_broker_fixtures():
    """Save broker fixtures to JSON files."""
    from pathlib import Path

    fixtures_dir = Path(__file__).parent

    with open(fixtures_dir / "alpaca_responses.json", "w") as f:
        json.dump(ALPACA_ORDER_RESPONSES, f, indent=2)

    with open(fixtures_dir / "mock_broker_responses.json", "w") as f:
        json.dump(MOCK_BROKER_RESPONSES, f, indent=2)

    with open(fixtures_dir / "websocket_messages.json", "w") as f:
        json.dump(WEBSOCKET_MESSAGES, f, indent=2)

    with open(fixtures_dir / "risk_responses.json", "w") as f:
        json.dump(RISK_RESPONSES, f, indent=2)

    print(f"Broker fixtures saved to {fixtures_dir}")


if __name__ == "__main__":
    save_broker_fixtures()
