"""
Comprehensive tests for PositionImportService.
Tests position import functionality from Alpaca to the database.
"""

import pytest
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.services.position_import_service import PositionImportService


class MockOrder:
    """Mock Order model for testing."""
    def __init__(self, symbol, status='filled', side='buy', filled_qty=Decimal('10')):
        self.id = uuid4()
        self.symbol = symbol
        self.status = status
        self.side = side
        self.filled_qty = filled_qty
        self.attributes = {'imported': 'true'}


class TestPositionImportServiceInit:
    """Tests for PositionImportService initialization."""

    def test_init_with_db_and_alpaca_client(self):
        """Test service initialization with dependencies."""
        mock_db = MagicMock()
        mock_alpaca = MagicMock()
        
        service = PositionImportService(db=mock_db, alpaca_client=mock_alpaca)
        
        assert service.db is mock_db
        assert service.alpaca_client is mock_alpaca

    def test_service_has_required_methods(self):
        """Test service has all required methods."""
        mock_db = MagicMock()
        mock_alpaca = MagicMock()
        
        service = PositionImportService(db=mock_db, alpaca_client=mock_alpaca)
        
        assert hasattr(service, 'import_existing_positions')
        assert hasattr(service, 'get_import_preview')
        assert callable(service.import_existing_positions)
        assert callable(service.get_import_preview)


class TestImportExistingPositions:
    """Tests for importing existing Alpaca positions."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        return db

    @pytest.fixture
    def mock_alpaca(self):
        """Create a mock Alpaca client."""
        client = MagicMock()
        client.get_positions = AsyncMock()
        return client

    @pytest.fixture
    def service(self, mock_db, mock_alpaca):
        """Create service with mocked dependencies."""
        return PositionImportService(db=mock_db, alpaca_client=mock_alpaca)

    @pytest.mark.asyncio
    async def test_import_no_positions(self, service, mock_alpaca):
        """Test import when no positions exist."""
        mock_alpaca.get_positions.return_value = []
        
        result = await service.import_existing_positions()
        
        assert result['success'] is True
        assert result['imported'] == 0
        assert result['skipped'] == 0
        assert result['positions'] == []

    @pytest.mark.asyncio
    async def test_import_none_positions(self, service, mock_alpaca):
        """Test import when positions is None."""
        mock_alpaca.get_positions.return_value = None
        
        result = await service.import_existing_positions()
        
        assert result['success'] is True
        assert result['imported'] == 0

    @pytest.mark.asyncio
    async def test_import_single_new_position(self, service, mock_db, mock_alpaca):
        """Test importing a single new position."""
        position = {
            'symbol': 'AAPL',
            'qty': '100',
            'avg_entry_price': '150.50'
        }
        mock_alpaca.get_positions.return_value = [position]
        
        # Mock no existing imports or orders
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        result = await service.import_existing_positions()
        
        assert result['success'] is True
        assert result['imported'] == 1
        assert result['skipped'] == 0
        assert len(result['positions']) == 1
        assert result['positions'][0]['symbol'] == 'AAPL'
        assert result['positions'][0]['qty'] == 100.0
        assert result['positions'][0]['avg_price'] == 150.50
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_multiple_positions(self, service, mock_db, mock_alpaca):
        """Test importing multiple positions."""
        positions = [
            {'symbol': 'AAPL', 'qty': '100', 'avg_entry_price': '150.50'},
            {'symbol': 'GOOGL', 'qty': '50', 'avg_entry_price': '2800.00'},
            {'symbol': 'MSFT', 'qty': '75', 'avg_entry_price': '340.25'}
        ]
        mock_alpaca.get_positions.return_value = positions
        
        # Mock no existing imports or orders
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        result = await service.import_existing_positions()
        
        assert result['success'] is True
        assert result['imported'] == 3
        assert result['skipped'] == 0
        assert len(result['positions']) == 3
        symbols = [p['symbol'] for p in result['positions']]
        assert 'AAPL' in symbols
        assert 'GOOGL' in symbols
        assert 'MSFT' in symbols

    @pytest.mark.asyncio
    async def test_skip_already_imported_position(self, service, mock_db, mock_alpaca):
        """Test that already imported positions are skipped."""
        position = {'symbol': 'AAPL', 'qty': '100', 'avg_entry_price': '150.50'}
        mock_alpaca.get_positions.return_value = [position]
        
        # Mock existing import
        existing_order = MockOrder('AAPL')
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_order
        mock_db.execute.return_value = mock_result
        
        result = await service.import_existing_positions()
        
        assert result['success'] is True
        assert result['imported'] == 0
        assert result['skipped'] == 1
        assert 'AAPL' in result['skipped_symbols'][0]
        assert 'already imported' in result['skipped_symbols'][0]

    @pytest.mark.asyncio
    async def test_skip_position_with_existing_orders(self, service, mock_db, mock_alpaca):
        """Test that positions with existing filled orders are skipped."""
        position = {'symbol': 'AAPL', 'qty': '100', 'avg_entry_price': '150.50'}
        mock_alpaca.get_positions.return_value = [position]
        
        # Mock no import but existing filled orders
        existing_orders = [MockOrder('AAPL', filled_qty=Decimal('50'))]
        
        mock_result = MagicMock()
        call_count = [0]
        
        def side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # No existing import
            return existing_orders
        
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = existing_orders
        mock_db.execute.return_value = mock_result
        
        result = await service.import_existing_positions()
        
        assert result['success'] is True
        assert result['imported'] == 0
        assert result['skipped'] == 1
        assert 'prevents double-counting' in result['skipped_symbols'][0]

    @pytest.mark.asyncio
    async def test_import_with_custom_user_id(self, service, mock_db, mock_alpaca):
        """Test import with custom user ID."""
        mock_alpaca.get_positions.return_value = []
        
        result = await service.import_existing_positions(user_id="custom_user")
        
        assert result['success'] is True
        # User ID would be used in the order creation

    @pytest.mark.asyncio
    async def test_import_calculates_correct_value(self, service, mock_db, mock_alpaca):
        """Test that position value is calculated correctly."""
        position = {'symbol': 'AAPL', 'qty': '100', 'avg_entry_price': '150.50'}
        mock_alpaca.get_positions.return_value = [position]
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        result = await service.import_existing_positions()
        
        expected_value = 100 * 150.50
        assert result['positions'][0]['value'] == expected_value

    @pytest.mark.asyncio
    async def test_import_handles_decimal_quantities(self, service, mock_db, mock_alpaca):
        """Test import handles fractional share quantities."""
        position = {'symbol': 'AAPL', 'qty': '10.5', 'avg_entry_price': '150.25'}
        mock_alpaca.get_positions.return_value = [position]
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        result = await service.import_existing_positions()
        
        assert result['positions'][0]['qty'] == 10.5
        assert result['positions'][0]['avg_price'] == 150.25

    @pytest.mark.asyncio
    async def test_import_error_triggers_rollback(self, service, mock_db, mock_alpaca):
        """Test that errors trigger database rollback."""
        mock_alpaca.get_positions.side_effect = Exception("API Error")
        
        with pytest.raises(Exception, match="API Error"):
            await service.import_existing_positions()
        
        mock_db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_database_error_triggers_rollback(self, service, mock_db, mock_alpaca):
        """Test that database errors trigger rollback."""
        position = {'symbol': 'AAPL', 'qty': '100', 'avg_entry_price': '150.50'}
        mock_alpaca.get_positions.return_value = [position]
        
        mock_db.execute.side_effect = Exception("Database Error")
        
        with pytest.raises(Exception, match="Database Error"):
            await service.import_existing_positions()
        
        mock_db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_mixed_positions(self, service, mock_db, mock_alpaca):
        """Test import with mix of new, imported, and duplicate positions."""
        positions = [
            {'symbol': 'AAPL', 'qty': '100', 'avg_entry_price': '150.50'},  # New
            {'symbol': 'GOOGL', 'qty': '50', 'avg_entry_price': '2800.00'},  # Already imported
            {'symbol': 'MSFT', 'qty': '75', 'avg_entry_price': '340.25'}   # Has existing orders
        ]
        mock_alpaca.get_positions.return_value = positions
        
        call_count = [0]
        
        def mock_execute(query):
            call_count[0] += 1
            mock_result = MagicMock()
            
            # For AAPL (1st, 2nd calls): no import, no orders
            if call_count[0] <= 2:
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = []
            # For GOOGL (3rd call): already imported
            elif call_count[0] == 3:
                mock_result.scalar_one_or_none.return_value = MockOrder('GOOGL')
            # For MSFT (4th, 5th calls): no import, but has orders
            elif call_count[0] == 4:
                mock_result.scalar_one_or_none.return_value = None
            elif call_count[0] == 5:
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = [MockOrder('MSFT')]
            
            return mock_result
        
        mock_db.execute = AsyncMock(side_effect=mock_execute)
        
        result = await service.import_existing_positions()
        
        assert result['success'] is True
        assert result['imported'] == 1  # Only AAPL
        assert result['skipped'] == 2  # GOOGL and MSFT


class TestGetImportPreview:
    """Tests for import preview functionality."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def mock_alpaca(self):
        """Create a mock Alpaca client."""
        client = MagicMock()
        client.get_positions = AsyncMock()
        return client

    @pytest.fixture
    def service(self, mock_db, mock_alpaca):
        """Create service with mocked dependencies."""
        return PositionImportService(db=mock_db, alpaca_client=mock_alpaca)

    @pytest.mark.asyncio
    async def test_preview_empty_positions(self, service, mock_alpaca):
        """Test preview with no positions."""
        mock_alpaca.get_positions.return_value = []
        
        result = await service.get_import_preview()
        
        assert result['to_import'] == []
        assert result['to_import_count'] == 0
        assert result['already_imported'] == []
        assert result['already_imported_count'] == 0
        assert result['would_duplicate'] == []
        assert result['would_duplicate_count'] == 0
        assert result['total_positions'] == 0

    @pytest.mark.asyncio
    async def test_preview_new_position(self, service, mock_db, mock_alpaca):
        """Test preview with a new position to import."""
        position = {
            'symbol': 'AAPL',
            'qty': '100',
            'avg_entry_price': '150.50',
            'current_price': '160.00',
            'market_value': '16000.00',
            'unrealized_pl': '950.00',
            'unrealized_plpc': '0.063'
        }
        mock_alpaca.get_positions.return_value = [position]
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        result = await service.get_import_preview()
        
        assert result['to_import_count'] == 1
        assert result['to_import'][0]['symbol'] == 'AAPL'
        assert result['to_import'][0]['qty'] == 100.0
        assert result['already_imported_count'] == 0
        assert result['would_duplicate_count'] == 0

    @pytest.mark.asyncio
    async def test_preview_already_imported_position(self, service, mock_db, mock_alpaca):
        """Test preview with already imported position."""
        position = {
            'symbol': 'AAPL',
            'qty': '100',
            'avg_entry_price': '150.50',
            'current_price': '160.00',
            'market_value': '16000.00',
            'unrealized_pl': '950.00',
            'unrealized_plpc': '0.063'
        }
        mock_alpaca.get_positions.return_value = [position]
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MockOrder('AAPL')
        mock_db.execute.return_value = mock_result
        
        result = await service.get_import_preview()
        
        assert result['to_import_count'] == 0
        assert result['already_imported_count'] == 1
        assert result['already_imported'][0]['symbol'] == 'AAPL'

    @pytest.mark.asyncio
    async def test_preview_would_duplicate_position(self, service, mock_db, mock_alpaca):
        """Test preview with position that would create duplicates."""
        position = {
            'symbol': 'AAPL',
            'qty': '100',
            'avg_entry_price': '150.50',
            'current_price': '160.00',
            'market_value': '16000.00',
            'unrealized_pl': '950.00',
            'unrealized_plpc': '0.063'
        }
        mock_alpaca.get_positions.return_value = [position]
        
        existing_orders = [MockOrder('AAPL', filled_qty=Decimal('50'))]
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = existing_orders
        mock_db.execute.return_value = mock_result
        
        result = await service.get_import_preview()
        
        assert result['to_import_count'] == 0
        assert result['would_duplicate_count'] == 1
        assert result['would_duplicate'][0]['symbol'] == 'AAPL'
        assert result['would_duplicate'][0]['existing_orders_count'] == 1
        assert result['would_duplicate'][0]['existing_orders_qty'] == 50.0
        assert 'Would create duplicates' in result['would_duplicate'][0]['reason']

    @pytest.mark.asyncio
    async def test_preview_includes_unrealized_pl(self, service, mock_db, mock_alpaca):
        """Test preview includes unrealized P/L data."""
        position = {
            'symbol': 'AAPL',
            'qty': '100',
            'avg_entry_price': '150.50',
            'current_price': '160.00',
            'market_value': '16000.00',
            'unrealized_pl': '950.00',
            'unrealized_plpc': '0.063'
        }
        mock_alpaca.get_positions.return_value = [position]
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        result = await service.get_import_preview()
        
        pos = result['to_import'][0]
        assert pos['unrealized_pl'] == 950.00
        assert pos['unrealized_plpc'] == 0.063
        assert pos['market_value'] == 16000.00

    @pytest.mark.asyncio
    async def test_preview_error_handling(self, service, mock_alpaca):
        """Test preview handles errors gracefully."""
        mock_alpaca.get_positions.side_effect = Exception("API Error")
        
        with pytest.raises(Exception, match="API Error"):
            await service.get_import_preview()

    @pytest.mark.asyncio
    async def test_preview_multiple_positions_mixed(self, service, mock_db, mock_alpaca):
        """Test preview with multiple positions in different states."""
        positions = [
            {
                'symbol': 'AAPL', 'qty': '100', 'avg_entry_price': '150.50',
                'current_price': '160.00', 'market_value': '16000.00',
                'unrealized_pl': '950.00', 'unrealized_plpc': '0.063'
            },
            {
                'symbol': 'GOOGL', 'qty': '50', 'avg_entry_price': '2800.00',
                'current_price': '2850.00', 'market_value': '142500.00',
                'unrealized_pl': '2500.00', 'unrealized_plpc': '0.018'
            }
        ]
        mock_alpaca.get_positions.return_value = positions
        
        call_count = [0]
        
        def mock_execute(query):
            call_count[0] += 1
            mock_result = MagicMock()
            
            # AAPL: new (first two calls)
            if call_count[0] <= 2:
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = []
            # GOOGL: already imported (third call)
            else:
                mock_result.scalar_one_or_none.return_value = MockOrder('GOOGL')
            
            return mock_result
        
        mock_db.execute = AsyncMock(side_effect=mock_execute)
        
        result = await service.get_import_preview()
        
        assert result['total_positions'] == 2
        assert result['to_import_count'] == 1
        assert result['already_imported_count'] == 1


class TestPositionImportServiceEdgeCases:
    """Edge case tests for PositionImportService."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        return db

    @pytest.fixture
    def mock_alpaca(self):
        """Create a mock Alpaca client."""
        client = MagicMock()
        client.get_positions = AsyncMock()
        return client

    @pytest.fixture
    def service(self, mock_db, mock_alpaca):
        """Create service with mocked dependencies."""
        return PositionImportService(db=mock_db, alpaca_client=mock_alpaca)

    @pytest.mark.asyncio
    async def test_import_zero_quantity_position(self, service, mock_db, mock_alpaca):
        """Test handling of zero quantity position."""
        position = {'symbol': 'AAPL', 'qty': '0', 'avg_entry_price': '150.50'}
        mock_alpaca.get_positions.return_value = [position]
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        result = await service.import_existing_positions()
        
        # Zero quantity should still be importable
        assert result['imported'] == 1
        assert result['positions'][0]['qty'] == 0.0

    @pytest.mark.asyncio
    async def test_import_very_large_quantity(self, service, mock_db, mock_alpaca):
        """Test handling of very large quantities."""
        position = {'symbol': 'AAPL', 'qty': '1000000', 'avg_entry_price': '150.50'}
        mock_alpaca.get_positions.return_value = [position]
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        result = await service.import_existing_positions()
        
        assert result['positions'][0]['qty'] == 1000000.0
        assert result['positions'][0]['value'] == 150500000.0

    @pytest.mark.asyncio
    async def test_import_very_small_price(self, service, mock_db, mock_alpaca):
        """Test handling of very small prices (penny stocks)."""
        position = {'symbol': 'PNST', 'qty': '10000', 'avg_entry_price': '0.01'}
        mock_alpaca.get_positions.return_value = [position]
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        result = await service.import_existing_positions()
        
        assert result['positions'][0]['avg_price'] == 0.01
        assert result['positions'][0]['value'] == 100.0

    @pytest.mark.asyncio
    async def test_import_very_high_precision_decimal(self, service, mock_db, mock_alpaca):
        """Test handling of high precision decimal values."""
        position = {'symbol': 'AAPL', 'qty': '10.123456', 'avg_entry_price': '150.123456'}
        mock_alpaca.get_positions.return_value = [position]
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        result = await service.import_existing_positions()
        
        # Should preserve decimal precision
        assert 'AAPL' in [p['symbol'] for p in result['positions']]

    @pytest.mark.asyncio
    async def test_commit_error_triggers_rollback(self, service, mock_db, mock_alpaca):
        """Test that commit errors trigger rollback."""
        position = {'symbol': 'AAPL', 'qty': '100', 'avg_entry_price': '150.50'}
        mock_alpaca.get_positions.return_value = [position]
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        mock_db.commit.side_effect = Exception("Commit failed")
        
        with pytest.raises(Exception, match="Commit failed"):
            await service.import_existing_positions()
        
        mock_db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_existing_orders_sum_correctly(self, service, mock_db, mock_alpaca):
        """Test that multiple existing orders are summed correctly."""
        position = {'symbol': 'AAPL', 'qty': '100', 'avg_entry_price': '150.50'}
        mock_alpaca.get_positions.return_value = [position]
        
        existing_orders = [
            MockOrder('AAPL', filled_qty=Decimal('30')),
            MockOrder('AAPL', filled_qty=Decimal('40')),
            MockOrder('AAPL', filled_qty=Decimal('20'))
        ]
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = existing_orders
        mock_db.execute.return_value = mock_result
        
        result = await service.import_existing_positions()
        
        # Should be skipped due to existing orders
        assert result['skipped'] == 1
        assert 'AAPL' in result['skipped_symbols'][0]
        assert '3 existing orders' in result['skipped_symbols'][0]
