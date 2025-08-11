"""
Legacy Risk Manager Compatibility Tests
Tests to ensure the legacy RiskManager wrapper maintains backward compatibility.
This file specifically tests the deprecated synchronous interface.
"""
import warnings

import pytest

from backend.risk.risk_manager import RiskManager


class TestLegacyRiskManagerCompatibility:
    """Test legacy compatibility wrapper - DO NOT use these patterns in new tests."""

    def setup_method(self):
        """Setup for legacy compatibility tests."""
        # Create a basic risk manager with more permissive limits for testing
        self.risk_manager = RiskManager(
            max_position_per_symbol=50000,  # Higher limit for testing
            max_single_position_value=500000,  # Higher limit for testing
            max_portfolio_var=0.5,  # More permissive VaR limit
        )

    @pytest.mark.unit
    def test_legacy_before_order_returns_tuple(self):
        """Test that legacy before_order returns the expected tri-tuple format."""
        with warnings.catch_warnings():
            # We expect deprecation warnings for the legacy interface
            warnings.simplefilter("ignore", DeprecationWarning)

            # Test basic order - we don't care if it's allowed or not,
            # just that it returns the correct tuple format
            result = self.risk_manager.before_order(symbol="AAPL", intended_qty=50.0, price=150.0)

            # Verify it returns a tuple with exactly 3 elements
            assert isinstance(result, tuple)
            assert len(result) == 3

            allowed, reason, adjusted_qty = result

            # Verify types match legacy interface
            assert isinstance(allowed, bool)
            assert isinstance(reason, str)
            assert isinstance(adjusted_qty, (int, float))

            # Verify the structure is correct (regardless of whether allowed or not)
            assert len(reason) > 0  # Should have a reason
            assert adjusted_qty != 0  # Should have some adjusted quantity

    @pytest.mark.unit
    def test_legacy_before_order_negative_quantity(self):
        """Test legacy interface handles negative quantities (sell orders)."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)

            # Test sell order (negative quantity)
            allowed, reason, adjusted_qty = self.risk_manager.before_order(
                symbol="AAPL", intended_qty=-100.0, price=150.0
            )

            assert isinstance(allowed, bool)
            assert isinstance(reason, str)
            assert isinstance(adjusted_qty, (int, float))

            # Should return negative quantity for sell orders
            if allowed:
                assert adjusted_qty <= 0.0

    @pytest.mark.unit
    def test_legacy_before_order_excessive_quantity(self):
        """Test legacy interface handles excessive position sizes."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)

            # Test very large order that should be limited or rejected
            allowed, reason, adjusted_qty = self.risk_manager.before_order(
                symbol="AAPL",
                intended_qty=1000000.0,  # Excessive quantity
                price=150.0,
            )

            assert isinstance(allowed, bool)
            assert isinstance(reason, str)
            assert isinstance(adjusted_qty, (int, float))

            # Should either be rejected or have adjusted quantity
            if not allowed:
                # If rejected, reason should indicate why
                assert len(reason) > 0
                assert "limit" in reason.lower() or "risk" in reason.lower()
            else:
                # If allowed, quantity should be reduced
                assert adjusted_qty < 1000000.0

    @pytest.mark.unit
    def test_legacy_before_order_emits_deprecation_warning(self):
        """Test that legacy before_order emits deprecation warning."""
        with pytest.warns(DeprecationWarning, match="Synchronous before_order is deprecated"):
            self.risk_manager.before_order(symbol="AAPL", intended_qty=10.0, price=150.0)

    @pytest.mark.unit
    def test_legacy_before_order_without_price(self):
        """Test legacy interface works without explicit price."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)

            # Test order without price (market order scenario)
            allowed, reason, adjusted_qty = self.risk_manager.before_order(
                symbol="AAPL",
                intended_qty=25.0,
                # No price parameter
            )

            assert isinstance(allowed, bool)
            assert isinstance(reason, str)
            assert isinstance(adjusted_qty, (int, float))
