"""
Margin Calculator Module

Calculates margin requirements and available margin for trading positions.
Implements standard margin calculations for equity and options trading.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class MarginRequirement:
    """Margin requirement details for a position."""
    initial_margin: Decimal
    maintenance_margin: Decimal
    buying_power_used: Decimal
    excess_liquidity: Decimal


class MarginCalculator:
    """Calculates margin requirements for trading positions."""

    def __init__(self, account_equity: Decimal = Decimal('100000')):
        """Initialize with account equity."""
        self.account_equity = account_equity
        self.initial_margin_rate = Decimal('0.5')  # 50% for stocks
        self.maintenance_margin_rate = Decimal('0.25')  # 25% for stocks

    def calculate_stock_margin(self, symbol: str, quantity: int, price: Decimal) -> MarginRequirement:
        """Calculate margin requirement for stock position."""
        position_value = abs(quantity) * price
        initial_margin = position_value * self.initial_margin_rate
        maintenance_margin = position_value * self.maintenance_margin_rate

        return MarginRequirement(
            initial_margin=initial_margin,
            maintenance_margin=maintenance_margin,
            buying_power_used=initial_margin,
            excess_liquidity=self.account_equity - initial_margin
        )

    def calculate_option_margin(self, symbol: str, quantity: int, premium: Decimal,
                              underlying_price: Decimal, strike: Decimal,
                              option_type: str) -> MarginRequirement:
        """Calculate margin requirement for option position."""
        # Simplified option margin calculation
        position_value = abs(quantity) * premium * 100  # Options are per 100 shares

        if option_type.upper() in ['CALL', 'PUT']:
            # For long options, margin = premium paid
            initial_margin = position_value
            maintenance_margin = Decimal('0')
        else:
            # For short options, use simplified calculation
            underlying_value = abs(quantity) * underlying_price * 100
            initial_margin = max(
                position_value + underlying_value * Decimal('0.2'),
                position_value + underlying_value * Decimal('0.1')
            )
            maintenance_margin = initial_margin * Decimal('0.5')

        return MarginRequirement(
            initial_margin=initial_margin,
            maintenance_margin=maintenance_margin,
            buying_power_used=initial_margin,
            excess_liquidity=self.account_equity - initial_margin
        )

    def calculate_portfolio_margin(self, positions: dict) -> MarginRequirement:
        """Calculate total margin requirement for all positions."""
        total_initial = Decimal('0')
        total_maintenance = Decimal('0')

        for position in positions.values():
            if position.get('type') == 'stock':
                margin = self.calculate_stock_margin(
                    position['symbol'],
                    position['quantity'],
                    Decimal(str(position['price']))
                )
            elif position.get('type') == 'option':
                margin = self.calculate_option_margin(
                    position['symbol'],
                    position['quantity'],
                    Decimal(str(position['premium'])),
                    Decimal(str(position['underlying_price'])),
                    Decimal(str(position['strike'])),
                    position['option_type']
                )
            else:
                continue

            total_initial += margin.initial_margin
            total_maintenance += margin.maintenance_margin

        return MarginRequirement(
            initial_margin=total_initial,
            maintenance_margin=total_maintenance,
            buying_power_used=total_initial,
            excess_liquidity=self.account_equity - total_initial
        )

    def get_available_buying_power(self, current_positions: dict | None = None) -> Decimal:
        """Get available buying power for new positions."""
        if current_positions:
            portfolio_margin = self.calculate_portfolio_margin(current_positions)
            return portfolio_margin.excess_liquidity
        return self.account_equity

    def validate_new_position(self, symbol: str, quantity: int, price: Decimal,
                            current_positions: dict | None = None) -> bool:
        """Validate if new position can be opened with available margin."""
        new_margin = self.calculate_stock_margin(symbol, quantity, price)
        available_bp = self.get_available_buying_power(current_positions)

        return new_margin.initial_margin <= available_bp


# Factory function for easy instantiation
def create_margin_calculator(account_equity: Decimal = Decimal('100000')) -> MarginCalculator:
    """Create a new margin calculator instance."""
    return MarginCalculator(account_equity)
