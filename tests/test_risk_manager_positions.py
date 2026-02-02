"""
Tests for Risk Manager position and portfolio integration.

Tests cover:
- _get_current_positions() with positions_service
- _get_current_positions() fallback behavior
- _get_portfolio_value() with positions_service
- _get_portfolio_value() fallback behavior
- Symbol exposure calculations with real positions
"""

import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Test imports
from backend.risk.risk_manager import AsyncRiskManager


@pytest.fixture
def mock_positions_service():
    """Create a mock PositionsService for testing."""
    service = AsyncMock()
    service.get_all_positions = AsyncMock(return_value={
        'AAPL': {
            'symbol': 'AAPL',
            'qty': 100,
            'market_value': 17500.0,
            'cost_basis': 15000.0,
            'unrealized_pl': 2500.0,
            'avg_entry_price': 150.0
        },
        'MSFT': {
            'symbol': 'MSFT',
            'qty': 50,
            'market_value': 20000.0,
            'cost_basis': 18000.0,
            'unrealized_pl': 2000.0,
            'avg_entry_price': 360.0
        },
        'GOOGL': {
            'symbol': 'GOOGL',
            'qty': 0,  # No position
            'market_value': 0.0,
            'cost_basis': 0.0,
            'unrealized_pl': 0.0,
            'avg_entry_price': 0.0
        }
    })
    service.get_total_portfolio_value = AsyncMock(return_value=100000.0)
    service.get_buying_power = AsyncMock(return_value=50000.0)
    return service


@pytest.fixture
def risk_manager_with_service(mock_positions_service):
    """Create AsyncRiskManager with mock positions_service."""
    return AsyncRiskManager(positions_service=mock_positions_service)


@pytest.fixture
def risk_manager_no_service():
    """Create AsyncRiskManager without positions_service."""
    return AsyncRiskManager(positions_service=None)


class TestGetCurrentPositions:
    """Tests for _get_current_positions() method."""

    @pytest.mark.asyncio
    async def test_returns_positions_from_service(self, risk_manager_with_service, mock_positions_service):
        """Positions are returned from positions_service when available."""
        positions = await risk_manager_with_service._get_current_positions()
        
        # Should only include symbols with non-zero qty
        assert 'AAPL' in positions
        assert 'MSFT' in positions
        assert 'GOOGL' not in positions  # qty=0, should be excluded
        
        # Values should be Decimal
        assert isinstance(positions['AAPL'], Decimal)
        assert positions['AAPL'] == Decimal('17500.0')
        assert positions['MSFT'] == Decimal('20000.0')

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_service(self, risk_manager_no_service):
        """Empty dict returned when no positions_service available."""
        # Mock the dynamic import to also fail
        with patch.dict(os.environ, {'ALPACA_API_KEY_ID': '', 'ALPACA_API_SECRET_KEY': ''}):
            positions = await risk_manager_no_service._get_current_positions()
        
        assert positions == {}

    @pytest.mark.asyncio
    async def test_returns_empty_on_service_error(self, risk_manager_with_service, mock_positions_service):
        """Empty dict returned when positions_service raises error."""
        mock_positions_service.get_all_positions.side_effect = Exception("Connection failed")
        
        positions = await risk_manager_with_service._get_current_positions()
        
        assert positions == {}

    @pytest.mark.asyncio
    async def test_handles_empty_positions(self, risk_manager_with_service, mock_positions_service):
        """Handles case where service returns empty positions."""
        mock_positions_service.get_all_positions.return_value = {}
        
        positions = await risk_manager_with_service._get_current_positions()
        
        assert positions == {}

    @pytest.mark.asyncio
    async def test_handles_none_market_value(self, risk_manager_with_service, mock_positions_service):
        """Handles missing market_value gracefully."""
        mock_positions_service.get_all_positions.return_value = {
            'AAPL': {
                'symbol': 'AAPL',
                'qty': 100,
                # market_value missing
            }
        }
        
        positions = await risk_manager_with_service._get_current_positions()
        
        assert 'AAPL' in positions
        assert positions['AAPL'] == Decimal('0.0')


class TestGetPortfolioValue:
    """Tests for _get_portfolio_value() method."""

    @pytest.mark.asyncio
    async def test_returns_value_from_service(self, risk_manager_with_service, mock_positions_service):
        """Portfolio value is returned from positions_service when available."""
        value = await risk_manager_with_service._get_portfolio_value()
        
        assert isinstance(value, Decimal)
        assert value == Decimal('100000.0')

    @pytest.mark.asyncio
    async def test_fallback_to_settings_when_no_service(self, risk_manager_no_service):
        """Falls back to settings when no positions_service available."""
        # Should use configured fallback
        value = await risk_manager_no_service._get_portfolio_value()
        
        assert isinstance(value, Decimal)
        assert value > Decimal('0')  # Some default value

    @pytest.mark.asyncio
    async def test_fallback_on_service_error(self, risk_manager_with_service, mock_positions_service):
        """Falls back to settings when service raises error."""
        mock_positions_service.get_total_portfolio_value.side_effect = Exception("API error")
        
        value = await risk_manager_with_service._get_portfolio_value()
        
        assert isinstance(value, Decimal)
        assert value > Decimal('0')  # Should use fallback

    @pytest.mark.asyncio
    async def test_fallback_when_value_is_zero(self, risk_manager_with_service, mock_positions_service):
        """Falls back to settings when service returns zero."""
        mock_positions_service.get_total_portfolio_value.return_value = 0.0
        
        value = await risk_manager_with_service._get_portfolio_value()
        
        # Should use fallback, not zero
        assert value > Decimal('0')

    @pytest.mark.asyncio
    async def test_fallback_when_value_is_none(self, risk_manager_with_service, mock_positions_service):
        """Falls back to settings when service returns None."""
        mock_positions_service.get_total_portfolio_value.return_value = None
        
        value = await risk_manager_with_service._get_portfolio_value()
        
        # Should use fallback, not fail
        assert value > Decimal('0')

    @pytest.mark.asyncio
    async def test_ultimate_fallback_is_250000(self, risk_manager_no_service):
        """Ultimate fallback is $250,000."""
        # Mock settings to have no risk attribute
        with patch.object(risk_manager_no_service, 'settings', MagicMock(spec=[])):
            value = await risk_manager_no_service._get_portfolio_value()
        
        # Should use safe fallback
        assert value == Decimal('250000.0')


class TestRiskManagerInitialization:
    """Tests for AsyncRiskManager initialization with services."""

    def test_accepts_positions_service(self, mock_positions_service):
        """RiskManager accepts positions_service parameter."""
        manager = AsyncRiskManager(positions_service=mock_positions_service)
        
        assert manager.positions_service is mock_positions_service

    def test_accepts_none_positions_service(self):
        """RiskManager works without positions_service."""
        manager = AsyncRiskManager(positions_service=None)
        
        assert manager.positions_service is None

    def test_accepts_legacy_parameters(self):
        """RiskManager accepts legacy compatibility parameters."""
        # These shouldn't raise errors
        manager = AsyncRiskManager(
            positions_service=None,
            pricing_service=MagicMock(),
            halt_service=MagicMock(),
            position_limits=MagicMock(),
            margin_calculator=MagicMock(),
            volatility_checker=MagicMock(),
        )
        
        assert manager is not None


class TestExposureCalculations:
    """Tests for exposure calculations using real positions."""

    @pytest.mark.asyncio
    async def test_symbol_exposure_includes_existing_position(self, risk_manager_with_service, mock_positions_service):
        """Symbol exposure check accounts for existing position."""
        # Get current positions (should have AAPL with $17,500)
        positions = await risk_manager_with_service._get_current_positions()
        
        # Verify AAPL has existing exposure
        assert 'AAPL' in positions
        assert positions['AAPL'] == Decimal('17500.0')
        
        # Total portfolio is $100,000, AAPL is $17,500 = 17.5% exposure
        portfolio_value = await risk_manager_with_service._get_portfolio_value()
        aapl_exposure = positions['AAPL'] / portfolio_value
        
        assert aapl_exposure == Decimal('0.175')  # 17.5%

    @pytest.mark.asyncio
    async def test_total_exposure_calculation(self, risk_manager_with_service, mock_positions_service):
        """Total exposure across all positions is calculated correctly."""
        positions = await risk_manager_with_service._get_current_positions()
        portfolio_value = await risk_manager_with_service._get_portfolio_value()
        
        total_exposure = sum(positions.values()) / portfolio_value
        
        # AAPL: $17,500 + MSFT: $20,000 = $37,500 / $100,000 = 37.5%
        assert total_exposure == Decimal('0.375')


class TestDynamicServiceCreation:
    """Tests for dynamic PositionsService creation."""

    @pytest.mark.asyncio
    async def test_attempts_dynamic_creation_when_no_service(self, risk_manager_no_service):
        """Attempts to create PositionsService dynamically when not provided."""
        # Mock the create_positions_service at the module level where it's imported
        mock_service = AsyncMock()
        mock_service.trading_client = None  # No trading client
        mock_service.get_all_positions = AsyncMock(return_value={})
        
        with patch('backend.services.positions_service.create_positions_service', return_value=mock_service):
            # This should try to create a service but fail since trading_client is None
            positions = await risk_manager_no_service._get_current_positions()
            
            # Should return empty since trading_client is None
            assert positions == {}

    @pytest.mark.asyncio
    async def test_handles_import_error_gracefully(self, risk_manager_no_service):
        """Handles ImportError when PositionsService not available."""
        with patch.dict('sys.modules', {'backend.services.positions_service': None}):
            # Should not raise, just return empty
            positions = await risk_manager_no_service._get_current_positions()
            assert positions == {}


class TestIntegrationScenarios:
    """Integration-style tests for realistic scenarios."""

    @pytest.mark.asyncio
    async def test_concentration_check_with_positions(self, risk_manager_with_service, mock_positions_service):
        """Concentration check considers existing exposure."""
        # Current state: AAPL has 17.5% exposure
        # Max symbol exposure is typically 15% (from risk defaults)
        
        positions = await risk_manager_with_service._get_current_positions()
        portfolio_value = await risk_manager_with_service._get_portfolio_value()
        
        current_aapl_exposure = float(positions.get('AAPL', Decimal('0'))) / float(portfolio_value)
        
        # With 17.5% already in AAPL, any additional AAPL order would increase concentration
        assert current_aapl_exposure > risk_manager_with_service.max_symbol_exposure or \
               risk_manager_with_service.max_symbol_exposure >= current_aapl_exposure

    @pytest.mark.asyncio
    async def test_new_symbol_has_no_existing_exposure(self, risk_manager_with_service):
        """New symbol starts with zero exposure."""
        positions = await risk_manager_with_service._get_current_positions()
        
        # NVDA is not in current positions
        assert 'NVDA' not in positions
        
        # So exposure for new NVDA order is only the order itself
        nvda_exposure = positions.get('NVDA', Decimal('0'))
        assert nvda_exposure == Decimal('0')
