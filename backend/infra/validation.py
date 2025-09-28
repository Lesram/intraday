"""
Input validation utilities with comprehensive edge case handling.
Provides validation functions for trading platform inputs.
"""

import re
from decimal import Decimal
from typing import Any


def validate_symbol(symbol: str) -> str:
    """
    Validate trading symbol format.

    Args:
        symbol: Trading symbol to validate

    Returns:
        Normalized symbol string

    Raises:
        ValueError: If symbol is invalid
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")

    if len(symbol) > 10:
        raise ValueError("Symbol too long (maximum 10 characters)")

    # Check for valid characters (letters, numbers, dots, hyphens)
    if not re.match(r"^[A-Za-z][A-Za-z0-9.-]*$", symbol):
        if symbol[0].isdigit():
            raise ValueError("Symbol cannot start with number")
        else:
            raise ValueError("Invalid characters in symbol")

    return symbol.upper()


def validate_price(price: float) -> float:
    """
    Validate price value.

    Args:
        price: Price to validate

    Returns:
        Validated price

    Raises:
        ValueError: If price is invalid
    """
    if price <= 0:
        raise ValueError("Price must be positive")

    if price > 1e8:  # $100 million per share
        raise ValueError("Price too large")

    # Check decimal places (maximum 4)
    decimal_price = Decimal(str(price))
    if decimal_price.as_tuple().exponent < -4:
        raise ValueError("Too many decimal places (maximum 4)")

    return float(decimal_price.quantize(Decimal("0.0001")))


def validate_quantity(quantity: int | float, allow_fractional: bool = True) -> float:
    """
    Validate quantity value.

    Args:
        quantity: Quantity to validate
        allow_fractional: Whether to allow fractional shares

    Returns:
        Validated quantity

    Raises:
        ValueError: If quantity is invalid
    """
    if quantity == 0:
        raise ValueError("Quantity cannot be zero")

    if abs(quantity) > 1e8:  # 100 million shares
        raise ValueError("Quantity too large")

    if not allow_fractional and quantity != int(quantity):
        raise ValueError("Fractional shares not allowed for this symbol")

    return float(quantity)


def validate_order(order_data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate order data structure.

    Args:
        order_data: Order data dictionary

    Returns:
        Validated order data

    Raises:
        ValueError: If order data is invalid
    """
    required_fields = ["symbol", "quantity"]

    for field in required_fields:
        if field not in order_data:
            raise ValueError(f"{field.title()} is required")

    # Validate symbol
    order_data["symbol"] = validate_symbol(order_data["symbol"])

    # Validate quantity
    order_data["quantity"] = validate_quantity(order_data["quantity"])

    # Validate price if provided
    if "price" in order_data:
        order_data["price"] = validate_price(order_data["price"])

    # Validate order type
    valid_order_types = ["market", "limit", "stop", "stop_limit"]
    order_type = order_data.get("order_type", "market").lower()

    if order_type not in valid_order_types:
        raise ValueError(f"Invalid order type: {order_type}")

    order_data["order_type"] = order_type

    return order_data


def validate_portfolio_constraints(portfolio_data: dict[str, Any]) -> list[str]:
    """
    Validate portfolio constraints and return violations.

    Args:
        portfolio_data: Portfolio data dictionary

    Returns:
        List of constraint violations
    """
    violations = []

    positions = portfolio_data.get("positions", {})

    # Check concentration limits
    max_position_weight = 0.0
    total_weight = 0.0

    for symbol, position in positions.items():
        weight = position.get("weight", 0.0)
        total_weight += abs(weight)
        max_position_weight = max(max_position_weight, abs(weight))

    # Maximum single position concentration (30%)
    if max_position_weight > 0.30:
        violations.append(
            f"Excessive concentration in single position: {max_position_weight:.1%}"
        )

    # Total portfolio exposure (should not exceed 100% for long positions)
    if total_weight > 1.0:
        violations.append(f"Total portfolio exposure exceeds 100%: {total_weight:.1%}")

    # Minimum diversification (at least 5 positions if portfolio > $10k)
    portfolio_value = portfolio_data.get("total_value", 0)
    if portfolio_value > 10000 and len(positions) < 5:
        violations.append(
            "Portfolio lacks diversification (minimum 5 positions for portfolios > $10k)"
        )

    return violations


def validate_risk_limits(risk_limits: dict[str, Any]) -> dict[str, Any]:
    """
    Validate risk limit configuration.

    Args:
        risk_limits: Risk limits dictionary

    Returns:
        Validated risk limits

    Raises:
        ValueError: If risk limits are invalid
    """
    # Check for conflicting limits
    max_pos = risk_limits.get("max_position_size", 1.0)
    min_pos = risk_limits.get("min_position_size", 0.0)

    if min_pos > max_pos:
        raise ValueError(
            f"Conflicting risk limits: min_position_size ({min_pos}) > "
            f"max_position_size ({max_pos})"
        )

    # Validate VaR limits
    max_var = risk_limits.get("max_var", 0.05)  # 5%
    if max_var <= 0 or max_var > 1.0:
        raise ValueError("max_var must be between 0 and 1")

    # Validate drawdown limits
    max_drawdown = risk_limits.get("max_drawdown", 0.20)  # 20%
    if max_drawdown <= 0 or max_drawdown > 1.0:
        raise ValueError("max_drawdown must be between 0 and 1")

    return risk_limits


def validate_market_data(market_data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate market data structure.

    Args:
        market_data: Market data dictionary

    Returns:
        Validated market data

    Raises:
        ValueError: If market data is invalid
    """
    required_fields = ["symbol", "price", "timestamp"]

    for field in required_fields:
        if field not in market_data:
            raise ValueError(f"{field.title()} is required in market data")

    # Validate symbol
    market_data["symbol"] = validate_symbol(market_data["symbol"])

    # Validate price
    market_data["price"] = validate_price(market_data["price"])

    # Validate volume if present
    if "volume" in market_data:
        volume = market_data["volume"]
        if volume < 0:
            raise ValueError("Volume cannot be negative")
        if volume > 1e12:  # 1 trillion shares
            raise ValueError("Volume too large")

    return market_data
