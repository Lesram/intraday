"""
Symbol Validation Service

Validates stock symbols before order submission to prevent invalid symbol errors.
"""
import logging

import httpx

logger = logging.getLogger(__name__)


class SymbolValidator:
    """Validates stock symbols using Alpaca API."""

    def __init__(self, alpaca_api_key: str, alpaca_secret_key: str, is_paper: bool = True):
        """
        Initialize symbol validator.

        Args:
            alpaca_api_key: Alpaca API key
            alpaca_secret_key: Alpaca secret key
            is_paper: Whether using paper trading (default: True)
        """
        self.api_key = alpaca_api_key
        self.secret_key = alpaca_secret_key
        self.is_paper = is_paper
        self.base_url = "https://paper-api.alpaca.markets" if is_paper else "https://api.alpaca.markets"

        # Cache for validated symbols (to avoid repeated API calls)
        self._valid_symbols: set[str] = set()
        self._invalid_symbols: set[str] = set()

    def _get_headers(self) -> dict:
        """Get authentication headers for Alpaca API."""
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key
        }

    async def validate_symbol(self, symbol: str) -> tuple[bool, str | None]:
        """
        Validate a stock symbol using Alpaca API.

        Args:
            symbol: Stock symbol to validate (e.g., 'AAPL', 'MSFT')

        Returns:
            Tuple of (is_valid, error_message)
            - (True, None) if symbol is valid
            - (False, error_message) if symbol is invalid
        """
        symbol = symbol.upper().strip()

        # Check cache first
        if symbol in self._valid_symbols:
            return True, None

        if symbol in self._invalid_symbols:
            return False, f"Invalid symbol: {symbol} (cached)"

        # Basic validation
        if not symbol:
            return False, "Symbol cannot be empty"

        if len(symbol) > 5:
            return False, f"Symbol too long: {symbol} (max 5 characters)"

        # Query Alpaca API to check if asset exists
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/v2/assets/{symbol}"
                headers = self._get_headers()

                response = await client.get(url, headers=headers, timeout=5.0)

                if response.status_code == 200:
                    asset_data = response.json()

                    # Check if asset is tradable
                    if not asset_data.get("tradable", False):
                        error = f"Asset {symbol} is not tradable"
                        self._invalid_symbols.add(symbol)
                        logger.warning(f"Symbol not tradable: {symbol}")
                        return False, error

                    # Check if asset is active
                    if asset_data.get("status") != "active":
                        error = f"Asset {symbol} is not active (status: {asset_data.get('status')})"
                        self._invalid_symbols.add(symbol)
                        logger.warning(f"Symbol not active: {symbol} (status: {asset_data.get('status')})")
                        return False, error

                    # Valid symbol
                    self._valid_symbols.add(symbol)
                    logger.debug(f"Symbol validated successfully: {symbol}")
                    return True, None

                elif response.status_code == 404:
                    # Asset not found
                    error = f"Asset {symbol} not found"
                    self._invalid_symbols.add(symbol)
                    logger.warning(f"Symbol not found: {symbol}")
                    return False, error

                else:
                    # Other error
                    error = f"Failed to validate symbol {symbol}: HTTP {response.status_code}"
                    logger.error(f"Symbol validation failed: {symbol} (status: {response.status_code})")
                    return False, error

        except httpx.TimeoutException:
            # Timeout - assume valid to avoid blocking orders
            logger.warning(f"Symbol validation timeout, allowing order: {symbol}")
            return True, None

        except Exception as e:
            # Other error - assume valid to avoid blocking orders
            logger.error(f"Symbol validation error, allowing order: {symbol} - {str(e)}")
            return True, None

    def clear_cache(self):
        """Clear the symbol validation cache."""
        self._valid_symbols.clear()
        self._invalid_symbols.clear()
        logger.info("Symbol validation cache cleared")


# Global validator instance (initialized on first use)
_validator_instance: SymbolValidator | None = None


def get_symbol_validator() -> SymbolValidator:
    """
    Get the global SymbolValidator instance.

    Returns:
        SymbolValidator instance
    """
    global _validator_instance

    if _validator_instance is None:
        import os

        from backend.settings import settings

        # Access alpaca config from settings
        # Try settings.alpaca first (new structure), fallback to direct attributes (legacy)
        if hasattr(settings, 'alpaca'):
            alpaca_config = settings.alpaca
            api_key = alpaca_config.api_key
            secret_key = alpaca_config.secret_key
            is_paper = alpaca_config.paper
        else:
            # Fallback to direct attributes or environment variables
            api_key = getattr(settings, 'alpaca_api_key', '') or os.getenv('ALPACA_API_KEY_ID', '')
            secret_key = getattr(settings, 'alpaca_secret_key', '') or os.getenv('ALPACA_API_SECRET_KEY', '')
            is_paper = getattr(settings, 'alpaca_paper', True)

        logger.info(f"Symbol validator initializing - has key: {bool(api_key)}, has secret: {bool(secret_key)}, is_paper: {is_paper}")

        _validator_instance = SymbolValidator(
            alpaca_api_key=api_key,
            alpaca_secret_key=secret_key,
            is_paper=is_paper
        )
        logger.info("Symbol validator initialized")

    return _validator_instance


async def validate_symbol(symbol: str) -> tuple[bool, str | None]:
    """
    Convenience function to validate a symbol.

    Args:
        symbol: Stock symbol to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    validator = get_symbol_validator()
    return await validator.validate_symbol(symbol)
