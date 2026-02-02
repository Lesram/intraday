"""
Comprehensive tests for backend.services.symbol_validator

Targets 90%+ coverage for the symbol validator module which provides:
- Symbol validation via Alpaca API
- Caching of valid/invalid symbols
- Error handling for API failures
"""

from unittest.mock import AsyncMock, Mock, patch
import pytest

from backend.services.symbol_validator import (
    SymbolValidator,
    get_symbol_validator,
    validate_symbol,
)


# ============================================================================
# SYMBOL VALIDATOR TESTS
# ============================================================================

class TestSymbolValidatorInit:
    """Tests for SymbolValidator initialization"""
    
    def test_init_paper_mode(self):
        """Test initialization in paper mode"""
        validator = SymbolValidator("api_key", "secret_key", is_paper=True)
        
        assert validator.api_key == "api_key"
        assert validator.secret_key == "secret_key"
        assert validator.is_paper is True
        assert "paper-api" in validator.base_url
        
    def test_init_live_mode(self):
        """Test initialization in live mode"""
        validator = SymbolValidator("api_key", "secret_key", is_paper=False)
        
        assert validator.is_paper is False
        assert "paper-api" not in validator.base_url
        
    def test_empty_caches(self):
        """Test caches start empty"""
        validator = SymbolValidator("key", "secret")
        
        assert len(validator._valid_symbols) == 0
        assert len(validator._invalid_symbols) == 0


class TestSymbolValidatorHeaders:
    """Tests for authentication headers"""
    
    def test_get_headers(self):
        """Test headers contain credentials"""
        validator = SymbolValidator("my_api_key", "my_secret")
        headers = validator._get_headers()
        
        assert headers["APCA-API-KEY-ID"] == "my_api_key"
        assert headers["APCA-API-SECRET-KEY"] == "my_secret"


class TestSymbolValidation:
    """Tests for validate_symbol method"""
    
    @pytest.fixture
    def validator(self):
        """Create validator instance"""
        return SymbolValidator("test_key", "test_secret", is_paper=True)
    
    @pytest.mark.asyncio
    async def test_empty_symbol_fails(self, validator):
        """Test empty symbol validation fails"""
        is_valid, error = await validator.validate_symbol("")
        
        assert is_valid is False
        assert "empty" in error.lower()
        
    @pytest.mark.asyncio
    async def test_symbol_too_long_fails(self, validator):
        """Test symbol too long validation fails"""
        is_valid, error = await validator.validate_symbol("TOOLONG")
        
        assert is_valid is False
        assert "too long" in error.lower()
        
    @pytest.mark.asyncio
    async def test_cached_valid_symbol(self, validator):
        """Test cached valid symbol returns True"""
        validator._valid_symbols.add("AAPL")
        
        is_valid, error = await validator.validate_symbol("AAPL")
        
        assert is_valid is True
        assert error is None
        
    @pytest.mark.asyncio
    async def test_cached_invalid_symbol(self, validator):
        """Test cached invalid symbol returns False"""
        validator._invalid_symbols.add("INVALID")
        
        is_valid, error = await validator.validate_symbol("INVALID")
        
        assert is_valid is False
        assert "cached" in error
        
    @pytest.mark.asyncio
    async def test_uppercase_conversion(self, validator):
        """Test symbol is uppercased"""
        validator._valid_symbols.add("GOOG")
        
        is_valid, error = await validator.validate_symbol("goog")
        
        assert is_valid is True
        
    @pytest.mark.asyncio
    async def test_whitespace_stripped(self, validator):
        """Test whitespace is stripped"""
        validator._valid_symbols.add("MSFT")
        
        is_valid, error = await validator.validate_symbol("  MSFT  ")
        
        assert is_valid is True
        
    @pytest.mark.asyncio
    async def test_api_valid_tradable_symbol(self, validator):
        """Test API returns valid tradable symbol"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tradable": True,
            "status": "active"
        }
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance
            
            is_valid, error = await validator.validate_symbol("AAPL")
            
            assert is_valid is True
            assert error is None
            assert "AAPL" in validator._valid_symbols
            
    @pytest.mark.asyncio
    async def test_api_not_tradable_symbol(self, validator):
        """Test API returns non-tradable symbol"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tradable": False,
            "status": "active"
        }
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance
            
            is_valid, error = await validator.validate_symbol("NOTRD")
            
            assert is_valid is False
            assert "not tradable" in error
            assert "NOTRD" in validator._invalid_symbols
            
    @pytest.mark.asyncio
    async def test_api_inactive_symbol(self, validator):
        """Test API returns inactive symbol"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tradable": True,
            "status": "inactive"
        }
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance
            
            is_valid, error = await validator.validate_symbol("INACT")
            
            assert is_valid is False
            assert "not active" in error
            
    @pytest.mark.asyncio
    async def test_api_404_not_found(self, validator):
        """Test API returns 404 for unknown symbol"""
        mock_response = Mock()
        mock_response.status_code = 404
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance
            
            is_valid, error = await validator.validate_symbol("NOPE")
            
            assert is_valid is False
            assert "not found" in error
            assert "NOPE" in validator._invalid_symbols
            
    @pytest.mark.asyncio
    async def test_api_other_error(self, validator):
        """Test API returns other HTTP error"""
        mock_response = Mock()
        mock_response.status_code = 500
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance
            
            is_valid, error = await validator.validate_symbol("ERR")
            
            assert is_valid is False
            assert "HTTP 500" in error
            
    @pytest.mark.asyncio
    async def test_api_timeout_allows_order(self, validator):
        """Test API timeout assumes valid"""
        import httpx
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance
            
            is_valid, error = await validator.validate_symbol("TMOT")
            
            # Should allow order to proceed
            assert is_valid is True
            assert error is None
            
    @pytest.mark.asyncio
    async def test_api_exception_allows_order(self, validator):
        """Test API exception assumes valid"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=Exception("Connection error"))
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance
            
            is_valid, error = await validator.validate_symbol("EXCPT")
            
            # Should allow order to proceed
            assert is_valid is True
            assert error is None


class TestClearCache:
    """Tests for cache clearing"""
    
    def test_clear_cache(self):
        """Test clearing symbol cache"""
        validator = SymbolValidator("key", "secret")
        validator._valid_symbols.add("AAPL")
        validator._invalid_symbols.add("BAD")
        
        validator.clear_cache()
        
        assert len(validator._valid_symbols) == 0
        assert len(validator._invalid_symbols) == 0


# ============================================================================
# GLOBAL VALIDATOR TESTS
# ============================================================================

class TestGetSymbolValidator:
    """Tests for get_symbol_validator function"""
    
    def test_creates_validator(self):
        """Test creates validator instance"""
        import backend.services.symbol_validator as sv_module
        sv_module._validator_instance = None  # Reset
        
        with patch.object(sv_module, 'settings', create=True) as mock_settings:
            mock_settings.alpaca = Mock()
            mock_settings.alpaca.api_key = "test_key"
            mock_settings.alpaca.secret_key = "test_secret"
            mock_settings.alpaca.paper = True
            
            validator = get_symbol_validator()
            
            assert validator is not None
            assert isinstance(validator, SymbolValidator)
            
    def test_returns_same_instance(self):
        """Test returns singleton instance"""
        import backend.services.symbol_validator as sv_module
        
        # First call creates instance
        sv_module._validator_instance = SymbolValidator("k", "s")
        
        validator1 = get_symbol_validator()
        validator2 = get_symbol_validator()
        
        assert validator1 is validator2


class TestValidateSymbolFunction:
    """Tests for validate_symbol convenience function"""
    
    @pytest.mark.asyncio
    async def test_calls_validator(self):
        """Test convenience function calls validator"""
        import backend.services.symbol_validator as sv_module
        
        mock_validator = Mock()
        mock_validator.validate_symbol = AsyncMock(return_value=(True, None))
        
        with patch.object(sv_module, 'get_symbol_validator', return_value=mock_validator):
            is_valid, error = await validate_symbol("AAPL")
            
            assert is_valid is True
            mock_validator.validate_symbol.assert_called_once_with("AAPL")
