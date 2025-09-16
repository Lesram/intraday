"""
Tests for backend/risk/risk_calculator.py - Risk calculation utilities
Tests the RiskCalculator class and related functions using direct import.
"""

import os
import sys
import pytest
import importlib.util
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch, Mock


class TestRiskCalculatorDirect:
    """Test suite for risk calculator utilities using direct import."""
    
    def setup_method(self):
        """Set up direct module import."""
        backend_path = Path(__file__).parent.parent.parent / "backend"
        self.backend_path = str(backend_path.resolve())
        
        # Import the risk calculator module using importlib
        risk_calc_path = os.path.join(self.backend_path, 'risk', 'risk_calculator.py')
        spec = importlib.util.spec_from_file_location("risk_calc_module", risk_calc_path)
        self.risk_calc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.risk_calc)
    
    def teardown_method(self):
        """Clean up after each test."""
        self.risk_calc = None

    def test_risk_calculator_initialization(self):
        """Test RiskCalculator class initialization."""
        calculator = self.risk_calc.RiskCalculator()
        
        assert calculator is not None
        assert isinstance(calculator, self.risk_calc.RiskCalculator)
        assert calculator.metrics == {}

    def test_calculate_metrics_with_positions(self):
        """Test calculate_metrics with valid position data."""
        calculator = self.risk_calc.RiskCalculator()
        
        positions = [
            {"value": 10000, "quantity": 100},
            {"value": 20000, "quantity": 200},
            {"value": 15000, "quantity": -50}  # Short position
        ]
        
        metrics = calculator.calculate_metrics(positions)
        
        assert isinstance(metrics, dict)
        assert "total_value" in metrics
        assert "total_exposure" in metrics
        assert "var_95" in metrics
        assert "sharpe_ratio" in metrics
        assert "max_drawdown" in metrics
        assert "beta" in metrics
        
        # Verify calculations
        assert metrics["total_value"] == 45000.0  # 10000 + 20000 + 15000
        assert metrics["total_exposure"] == 350.0  # |100| + |200| + |-50|
        assert metrics["var_95"] == 2250.0  # 45000 * 0.05
        assert metrics["sharpe_ratio"] == 1.2
        assert metrics["max_drawdown"] == -0.08
        assert metrics["beta"] == 0.9

    def test_calculate_metrics_empty_positions(self):
        """Test calculate_metrics with empty positions list."""
        calculator = self.risk_calc.RiskCalculator()
        
        metrics = calculator.calculate_metrics([])
        
        assert metrics["total_value"] == 0.0
        assert metrics["total_exposure"] == 0.0
        assert metrics["var_95"] == 0.0
        assert metrics["sharpe_ratio"] == 1.2
        assert metrics["max_drawdown"] == -0.08
        assert metrics["beta"] == 0.9

    def test_calculate_metrics_with_missing_fields(self):
        """Test calculate_metrics handles missing value/quantity fields."""
        calculator = self.risk_calc.RiskCalculator()
        
        positions = [
            {"value": 10000},  # Missing quantity
            {"quantity": 100},  # Missing value
            {}  # Missing both
        ]
        
        metrics = calculator.calculate_metrics(positions)
        
        assert metrics["total_value"] == 10000.0  # Only first position has value
        assert metrics["total_exposure"] == 100.0  # Only second position has quantity

    def test_calculate_metrics_with_string_numbers(self):
        """Test calculate_metrics handles string numeric values."""
        calculator = self.risk_calc.RiskCalculator()
        
        positions = [
            {"value": "10000.50", "quantity": "100"},
            {"value": "20000.25", "quantity": "200"}
        ]
        
        metrics = calculator.calculate_metrics(positions)
        
        assert metrics["total_value"] == 30000.75
        assert metrics["total_exposure"] == 300.0

    def test_check_position_limits_within_limit(self):
        """Test check_position_limits returns True for positions within limits."""
        calculator = self.risk_calc.RiskCalculator()
        
        position = {"value": 500000}  # Under 1M limit
        
        result = calculator.check_position_limits(position)
        
        assert result is True

    def test_check_position_limits_exceeds_limit(self):
        """Test check_position_limits returns False for positions exceeding limits."""
        calculator = self.risk_calc.RiskCalculator()
        
        position = {"value": 1500000}  # Over 1M limit
        
        result = calculator.check_position_limits(position)
        
        assert result is False

    def test_check_position_limits_at_limit(self):
        """Test check_position_limits behavior exactly at limit."""
        calculator = self.risk_calc.RiskCalculator()
        
        position = {"value": 1000000}  # Exactly at 1M limit
        
        result = calculator.check_position_limits(position)
        
        assert result is False  # Should be False since it's not < 1M

    def test_check_position_limits_negative_value(self):
        """Test check_position_limits handles negative values (absolute value)."""
        calculator = self.risk_calc.RiskCalculator()
        
        position = {"value": -500000}  # Negative value (short position)
        
        result = calculator.check_position_limits(position)
        
        assert result is True  # abs(-500000) = 500000 < 1M

    def test_check_position_limits_missing_value(self):
        """Test check_position_limits handles missing value field."""
        calculator = self.risk_calc.RiskCalculator()
        
        position = {}  # No value field
        
        result = calculator.check_position_limits(position)
        
        assert result is True  # Defaults to 0, which is < 1M

    def test_check_position_limits_string_value(self):
        """Test check_position_limits handles string numeric values."""
        calculator = self.risk_calc.RiskCalculator()
        
        position = {"value": "750000.50"}
        
        result = calculator.check_position_limits(position)
        
        assert result is True

    def test_calculate_var_default_confidence(self):
        """Test calculate_var with default confidence level."""
        calculator = self.risk_calc.RiskCalculator()
        
        positions = [
            {"value": 100000},
            {"value": 200000}
        ]
        
        var = calculator.calculate_var(positions)
        
        # VaR = total_value * (1 - confidence) = 300000 * 0.05 = 15000
        assert abs(var - 15000.0) < 0.0001

    def test_calculate_var_custom_confidence(self):
        """Test calculate_var with custom confidence level."""
        calculator = self.risk_calc.RiskCalculator()
        
        positions = [
            {"value": 100000},
            {"value": 200000}
        ]
        
        var_99 = calculator.calculate_var(positions, confidence=0.99)
        
        # VaR = total_value * (1 - confidence) = 300000 * 0.01 = 3000
        assert abs(var_99 - 3000.0) < 0.0001

    def test_calculate_var_empty_positions(self):
        """Test calculate_var with empty positions."""
        calculator = self.risk_calc.RiskCalculator()
        
        var = calculator.calculate_var([])
        
        assert var == 0.0

    def test_global_risk_calculator_instance(self):
        """Test the global risk_calculator instance."""
        global_instance = self.risk_calc.risk_calculator
        
        assert global_instance is not None
        assert isinstance(global_instance, self.risk_calc.RiskCalculator)

    def test_get_risk_calculator_function(self):
        """Test get_risk_calculator factory function."""
        calculator = self.risk_calc.get_risk_calculator()
        
        assert calculator is not None
        assert isinstance(calculator, self.risk_calc.RiskCalculator)
        
        # Should return the same global instance
        assert calculator is self.risk_calc.risk_calculator

    def test_calculate_metrics_function(self):
        """Test the standalone calculate_metrics function."""
        # Test default behavior
        result = self.risk_calc.calculate_metrics()
        
        assert isinstance(result, dict)
        assert "total_exposure" in result
        assert "max_drawdown" in result
        assert "var_95" in result
        assert "leverage_ratio" in result
        assert "risk_score" in result
        
        # Verify default values
        assert result["total_exposure"] == 100000.0
        assert result["max_drawdown"] == -5000.0
        assert result["var_95"] == 15000.0
        assert result["leverage_ratio"] == 1.5
        assert result["risk_score"] == 0.3

    def test_calculate_metrics_function_with_args(self):
        """Test calculate_metrics function accepts arbitrary arguments."""
        result = self.risk_calc.calculate_metrics("arg1", "arg2", param1="value1")
        
        # Should still return default mock response regardless of args
        assert isinstance(result, dict)
        assert result["total_exposure"] == 100000.0

    def test_risk_calculator_metrics_persistence(self):
        """Test that RiskCalculator maintains metrics state."""
        calculator = self.risk_calc.RiskCalculator()
        
        # Initially empty
        assert calculator.metrics == {}
        
        # Modify metrics
        calculator.metrics["test_metric"] = 123.45
        
        # Should persist
        assert calculator.metrics["test_metric"] == 123.45

    def test_decimal_precision_in_calculations(self):
        """Test that Decimal precision is maintained in calculations."""
        calculator = self.risk_calc.RiskCalculator()
        
        # Use high precision values
        positions = [
            {"value": "10000.123456", "quantity": "100.5"},
            {"value": "20000.654321", "quantity": "200.25"}
        ]
        
        metrics = calculator.calculate_metrics(positions)
        
        # Should handle precise calculations
        expected_total = 10000.123456 + 20000.654321
        assert abs(metrics["total_value"] - expected_total) < 0.000001

    def test_large_number_handling(self):
        """Test handling of large financial numbers."""
        calculator = self.risk_calc.RiskCalculator()
        
        # Test with large positions
        positions = [
            {"value": 999999999, "quantity": 1000000}  # Nearly 1B value
        ]
        
        metrics = calculator.calculate_metrics(positions)
        
        assert metrics["total_value"] == 999999999.0
        assert metrics["total_exposure"] == 1000000.0
        
        # Check position limit (should exceed 1M limit)
        position = {"value": 999999999}
        assert calculator.check_position_limits(position) is False
