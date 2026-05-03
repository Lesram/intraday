"""
Phase 8: Comprehensive tests for optimization/portfolio_optimizer.py
Coverage target: 85%+
Tests PortfolioOptimizer with various optimization objectives.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
import numpy as np


# ============================================================================
# ENUM TESTS
# ============================================================================

class TestOptimizationObjective:
    """Test OptimizationObjective enum."""
    
    def test_optimization_objectives(self):
        """Test all optimization objective values."""
        from backend.optimization.portfolio_optimizer import OptimizationObjective
        
        assert OptimizationObjective.MAX_SHARPE.value == "max_sharpe"
        assert OptimizationObjective.MIN_VOLATILITY.value == "min_volatility"
        assert OptimizationObjective.MAX_RETURN.value == "max_return"
        assert OptimizationObjective.RISK_PARITY.value == "risk_parity"
        assert OptimizationObjective.BLACK_LITTERMAN.value == "black_litterman"
        assert OptimizationObjective.FACTOR_MODEL.value == "factor_model"


class TestRebalanceFrequency:
    """Test RebalanceFrequency enum."""
    
    def test_rebalance_frequencies(self):
        """Test all rebalance frequency values."""
        from backend.optimization.portfolio_optimizer import RebalanceFrequency
        
        assert RebalanceFrequency.DAILY.value == "daily"
        assert RebalanceFrequency.WEEKLY.value == "weekly"
        assert RebalanceFrequency.MONTHLY.value == "monthly"
        assert RebalanceFrequency.QUARTERLY.value == "quarterly"


# ============================================================================
# DATACLASS TESTS
# ============================================================================

class TestOptimizationConstraints:
    """Test OptimizationConstraints dataclass."""
    
    def test_default_constraints(self):
        """Test default constraint values."""
        from backend.optimization.portfolio_optimizer import OptimizationConstraints
        
        constraints = OptimizationConstraints()
        
        assert constraints.min_weight == 0.0
        assert constraints.max_weight == 1.0
        assert constraints.max_turnover == 0.5
        assert constraints.min_positions == 1
        assert constraints.max_positions == 100
        assert constraints.transaction_cost == 0.001
        assert constraints.long_only is False
    
    def test_custom_constraints(self):
        """Test custom constraint values."""
        from backend.optimization.portfolio_optimizer import OptimizationConstraints
        
        constraints = OptimizationConstraints(
            min_weight=0.01,
            max_weight=0.20,
            max_turnover=0.25,
            long_only=True,
            target_return=0.10
        )
        
        assert constraints.min_weight == 0.01
        assert constraints.max_weight == 0.20
        assert constraints.long_only is True
        assert constraints.target_return == 0.10


class TestPortfolioAllocation:
    """Test PortfolioAllocation dataclass."""
    
    def test_allocation_creation(self):
        """Test creating PortfolioAllocation."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioAllocation, OptimizationObjective
        )
        
        allocation = PortfolioAllocation(
            weights={"AAPL": 0.5, "MSFT": 0.5},
            expected_return=0.10,
            expected_volatility=0.15,
            sharpe_ratio=0.67,
            objective_value=0.67,
            optimization_method=OptimizationObjective.MAX_SHARPE,
            constraints_satisfied=True
        )
        
        assert allocation.weights == {"AAPL": 0.5, "MSFT": 0.5}
        assert allocation.expected_return == 0.10
        assert allocation.sharpe_ratio == 0.67
        assert allocation.turnover == 0.0  # Default


class TestAssetData:
    """Test AssetData dataclass."""
    
    def test_asset_data_creation(self):
        """Test creating AssetData."""
        from backend.optimization.portfolio_optimizer import AssetData
        
        asset = AssetData(
            symbol="AAPL",
            expected_return=0.12,
            volatility=0.25,
            sector="Technology",
            beta=1.2
        )
        
        assert asset.symbol == "AAPL"
        assert asset.expected_return == 0.12
        assert asset.volatility == 0.25
        assert asset.sector == "Technology"
        assert asset.beta == 1.2
    
    def test_asset_data_defaults(self):
        """Test AssetData default values."""
        from backend.optimization.portfolio_optimizer import AssetData
        
        asset = AssetData(
            symbol="AAPL",
            expected_return=0.10,
            volatility=0.20
        )
        
        assert asset.current_weight == 0.0
        assert asset.sector == "Unknown"
        assert asset.market_cap == 0.0
        assert asset.beta == 1.0
        assert asset.liquidity_score == 1.0
        assert asset.returns_history == []


# ============================================================================
# PORTFOLIO OPTIMIZER INIT TESTS
# ============================================================================

class TestPortfolioOptimizerInit:
    """Test PortfolioOptimizer initialization."""
    
    def test_init_defaults(self):
        """Test PortfolioOptimizer with default settings."""
        from backend.optimization.portfolio_optimizer import PortfolioOptimizer
        
        optimizer = PortfolioOptimizer()
        
        assert optimizer.constraints is not None
        assert optimizer.risk_free_rate == 0.02
        assert optimizer.assets == {}
        assert optimizer.covariance_matrix is None
        assert optimizer.optimization_history == []
    
    def test_init_custom_constraints(self):
        """Test PortfolioOptimizer with custom constraints."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationConstraints
        )
        
        constraints = OptimizationConstraints(
            min_weight=0.05,
            max_weight=0.25,
            long_only=True
        )
        
        optimizer = PortfolioOptimizer(
            constraints=constraints,
            risk_free_rate=0.03
        )
        
        assert optimizer.constraints.min_weight == 0.05
        assert optimizer.constraints.max_weight == 0.25
        assert optimizer.risk_free_rate == 0.03
    
    def test_init_slo_disabled(self):
        """Test PortfolioOptimizer with SLO disabled."""
        from backend.optimization.portfolio_optimizer import PortfolioOptimizer
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        assert optimizer.slo_monitor is None


# ============================================================================
# UPDATE ASSET DATA TESTS
# ============================================================================

class TestUpdateAssetData:
    """Test update_asset_data method."""
    
    @pytest.mark.asyncio
    async def test_update_asset_data_success(self):
        """Test updating asset data."""
        from backend.optimization.portfolio_optimizer import PortfolioOptimizer
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        assets_data = {
            "AAPL": {
                "expected_return": 0.12,
                "volatility": 0.25,
                "sector": "Technology"
            },
            "MSFT": {
                "expected_return": 0.10,
                "volatility": 0.22,
                "sector": "Technology"
            }
        }
        
        await optimizer.update_asset_data(assets_data)
        
        assert len(optimizer.assets) == 2
        assert "AAPL" in optimizer.assets
        assert "MSFT" in optimizer.assets
        assert optimizer.assets["AAPL"].expected_return == 0.12
    
    @pytest.mark.asyncio
    async def test_update_asset_data_clears_previous(self):
        """Test that update_asset_data clears previous data."""
        from backend.optimization.portfolio_optimizer import PortfolioOptimizer
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        # First update
        await optimizer.update_asset_data({
            "AAPL": {"expected_return": 0.10, "volatility": 0.20}
        })
        
        # Second update with different assets
        await optimizer.update_asset_data({
            "GOOG": {"expected_return": 0.15, "volatility": 0.30}
        })
        
        assert len(optimizer.assets) == 1
        assert "GOOG" in optimizer.assets
        assert "AAPL" not in optimizer.assets
    
    @pytest.mark.asyncio
    async def test_update_asset_data_with_returns_history(self):
        """Test updating with returns history."""
        from backend.optimization.portfolio_optimizer import PortfolioOptimizer
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        returns = [0.01, -0.02, 0.03, 0.01, -0.01] * 10  # 50 returns
        
        await optimizer.update_asset_data({
            "AAPL": {
                "expected_return": 0.10,
                "volatility": 0.20,
                "returns_history": returns
            }
        })
        
        assert len(optimizer.assets["AAPL"].returns_history) == 50


# ============================================================================
# OPTIMIZATION MATRICES TESTS
# ============================================================================

class TestOptimizationMatrices:
    """Test optimization matrix calculations."""
    
    @pytest.mark.asyncio
    async def test_update_optimization_matrices(self):
        """Test _update_optimization_matrices."""
        from backend.optimization.portfolio_optimizer import PortfolioOptimizer
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        await optimizer.update_asset_data({
            "AAPL": {"expected_return": 0.12, "volatility": 0.25},
            "MSFT": {"expected_return": 0.10, "volatility": 0.22}
        })
        
        assert optimizer.expected_returns is not None
        assert len(optimizer.expected_returns) == 2
        assert optimizer.covariance_matrix is not None
        assert optimizer.covariance_matrix.shape == (2, 2)
    
    @pytest.mark.asyncio
    async def test_covariance_matrix_from_history(self):
        """Test covariance matrix calculation from history."""
        from backend.optimization.portfolio_optimizer import PortfolioOptimizer
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        # Create correlated return histories
        np.random.seed(42)
        returns1 = np.random.normal(0.001, 0.02, 100).tolist()
        returns2 = np.random.normal(0.001, 0.02, 100).tolist()
        
        await optimizer.update_asset_data({
            "AAPL": {
                "expected_return": 0.10,
                "volatility": 0.20,
                "returns_history": returns1
            },
            "MSFT": {
                "expected_return": 0.10,
                "volatility": 0.20,
                "returns_history": returns2
            }
        })
        
        # Covariance matrix should be calculated
        assert optimizer.covariance_matrix is not None
        # Diagonal elements should be positive (variances)
        assert optimizer.covariance_matrix[0, 0] > 0
        assert optimizer.covariance_matrix[1, 1] > 0
    
    def test_is_positive_definite(self):
        """Test _is_positive_definite method."""
        from backend.optimization.portfolio_optimizer import PortfolioOptimizer
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        # Identity matrix is positive definite
        pd_matrix = np.eye(3)
        assert optimizer._is_positive_definite(pd_matrix) is True
        
        # Not positive definite
        non_pd = np.array([[1, 2], [2, 1]])
        assert optimizer._is_positive_definite(non_pd) is False
    
    def test_make_positive_definite(self):
        """Test _make_positive_definite method."""
        from backend.optimization.portfolio_optimizer import PortfolioOptimizer
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        # Start with non-positive definite matrix
        non_pd = np.array([[1, 2], [2, 1]])
        
        result = optimizer._make_positive_definite(non_pd)
        
        # Result should be positive definite
        assert optimizer._is_positive_definite(result)


# ============================================================================
# PORTFOLIO OPTIMIZATION TESTS
# ============================================================================

class TestOptimizePortfolio:
    """Test optimize_portfolio method."""
    
    @pytest.mark.asyncio
    async def test_optimize_max_sharpe(self):
        """Test maximum Sharpe ratio optimization."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        await optimizer.update_asset_data({
            "AAPL": {"expected_return": 0.15, "volatility": 0.25},
            "MSFT": {"expected_return": 0.12, "volatility": 0.20},
            "GOOG": {"expected_return": 0.10, "volatility": 0.22}
        })
        
        result = await optimizer.optimize_portfolio(OptimizationObjective.MAX_SHARPE)
        
        assert result.optimization_method == OptimizationObjective.MAX_SHARPE
        assert abs(sum(result.weights.values()) - 1.0) < 0.01  # Weights sum to 1
        assert result.expected_return > 0
        assert result.expected_volatility > 0
    
    @pytest.mark.asyncio
    async def test_optimize_min_volatility(self):
        """Test minimum volatility optimization."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        await optimizer.update_asset_data({
            "AAPL": {"expected_return": 0.15, "volatility": 0.30},
            "BOND": {"expected_return": 0.03, "volatility": 0.05}
        })
        
        result = await optimizer.optimize_portfolio(OptimizationObjective.MIN_VOLATILITY)
        
        assert result.optimization_method == OptimizationObjective.MIN_VOLATILITY
        # Lower vol asset should have higher weight
        assert result.weights["BOND"] > result.weights["AAPL"]
    
    @pytest.mark.asyncio
    async def test_optimize_max_return(self):
        """Test maximum return optimization."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        await optimizer.update_asset_data({
            "HIGH": {"expected_return": 0.20, "volatility": 0.30},
            "LOW": {"expected_return": 0.05, "volatility": 0.10}
        })
        
        result = await optimizer.optimize_portfolio(OptimizationObjective.MAX_RETURN)
        
        assert result.optimization_method == OptimizationObjective.MAX_RETURN
        # Higher return asset should have higher weight
        assert result.weights["HIGH"] >= result.weights["LOW"]
    
    @pytest.mark.asyncio
    async def test_optimize_without_data_raises(self):
        """Test optimization without asset data raises error."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        with pytest.raises(ValueError, match="not initialized"):
            await optimizer.optimize_portfolio(OptimizationObjective.MAX_SHARPE)
    
    @pytest.mark.asyncio
    async def test_optimization_history_tracking(self):
        """Test optimization history is tracked."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        await optimizer.update_asset_data({
            "AAPL": {"expected_return": 0.12, "volatility": 0.25}
        })
        
        await optimizer.optimize_portfolio(OptimizationObjective.MAX_SHARPE)
        await optimizer.optimize_portfolio(OptimizationObjective.MIN_VOLATILITY)
        
        assert len(optimizer.optimization_history) == 2


# ============================================================================
# CONSTRAINT CHECKING TESTS
# ============================================================================

class TestConstraintChecking:
    """Test constraint checking functionality."""
    
    @pytest.mark.asyncio
    async def test_turnover_calculation(self):
        """Test turnover calculation."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        # Set initial weights
        await optimizer.update_asset_data({
            "AAPL": {"expected_return": 0.12, "volatility": 0.25, "current_weight": 0.5},
            "MSFT": {"expected_return": 0.10, "volatility": 0.20, "current_weight": 0.5}
        })
        
        result = await optimizer.optimize_portfolio(OptimizationObjective.MAX_SHARPE)
        
        # Turnover should be calculated
        assert result.turnover >= 0
    
    @pytest.mark.asyncio
    async def test_transaction_cost_calculation(self):
        """Test transaction cost calculation."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective, OptimizationConstraints
        )
        
        constraints = OptimizationConstraints(transaction_cost=0.002)  # 0.2%
        optimizer = PortfolioOptimizer(constraints=constraints, enable_slo=False)
        
        await optimizer.update_asset_data({
            "AAPL": {"expected_return": 0.12, "volatility": 0.25, "current_weight": 1.0},
            "MSFT": {"expected_return": 0.10, "volatility": 0.20, "current_weight": 0.0}
        })
        
        result = await optimizer.optimize_portfolio(OptimizationObjective.MAX_SHARPE)
        
        # Transaction costs = turnover * cost rate
        assert result.transaction_costs >= 0


# ============================================================================
# FALLBACK ALLOCATION TESTS
# ============================================================================

class TestFallbackAllocation:
    """Test fallback allocation when optimization fails."""
    
    def test_fallback_allocation_exists(self):
        """Test _fallback_allocation method exists."""
        from backend.optimization.portfolio_optimizer import PortfolioOptimizer
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        assert hasattr(optimizer, '_fallback_allocation')


# ============================================================================
# LONG ONLY CONSTRAINT TESTS
# ============================================================================

class TestLongOnlyConstraint:
    """Test long-only constraint handling."""
    
    @pytest.mark.asyncio
    async def test_long_only_positive_weights(self):
        """Test long-only constraint produces positive weights."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective, OptimizationConstraints
        )
        
        constraints = OptimizationConstraints(long_only=True)
        optimizer = PortfolioOptimizer(constraints=constraints, enable_slo=False)
        
        await optimizer.update_asset_data({
            "AAPL": {"expected_return": 0.12, "volatility": 0.25},
            "MSFT": {"expected_return": 0.10, "volatility": 0.20}
        })
        
        result = await optimizer.optimize_portfolio(OptimizationObjective.MAX_SHARPE)
        
        # All weights should be >= 0
        for weight in result.weights.values():
            assert weight >= 0


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Test edge cases in portfolio optimization."""
    
    @pytest.mark.asyncio
    async def test_single_asset(self):
        """Test optimization with single asset."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        await optimizer.update_asset_data({
            "AAPL": {"expected_return": 0.12, "volatility": 0.25}
        })
        
        result = await optimizer.optimize_portfolio(OptimizationObjective.MAX_SHARPE)
        
        # Single asset should have 100% weight
        assert result.weights["AAPL"] == pytest.approx(1.0, rel=0.01)
    
    @pytest.mark.asyncio
    async def test_zero_volatility_asset(self):
        """Test handling asset with zero volatility."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        await optimizer.update_asset_data({
            "CASH": {"expected_return": 0.0, "volatility": 0.001},  # Near-zero
            "STOCK": {"expected_return": 0.10, "volatility": 0.20}
        })
        
        result = await optimizer.optimize_portfolio(OptimizationObjective.MIN_VOLATILITY)
        
        # Should complete without error
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_negative_expected_return(self):
        """Test handling negative expected returns."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        await optimizer.update_asset_data({
            "BEAR": {"expected_return": -0.05, "volatility": 0.30},
            "BULL": {"expected_return": 0.15, "volatility": 0.25}
        })
        
        result = await optimizer.optimize_portfolio(OptimizationObjective.MAX_RETURN)
        
        # Should prefer positive return asset
        assert result.weights["BULL"] > result.weights["BEAR"]
    
    @pytest.mark.asyncio
    async def test_empty_returns_history(self):
        """Test handling empty returns history."""
        from backend.optimization.portfolio_optimizer import PortfolioOptimizer
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        await optimizer.update_asset_data({
            "AAPL": {
                "expected_return": 0.10,
                "volatility": 0.20,
                "returns_history": []  # Empty
            }
        })
        
        # Should use fallback diagonal covariance
        assert optimizer.covariance_matrix is not None
        assert optimizer.covariance_matrix[0, 0] > 0


# ============================================================================
# RISK PARITY TESTS
# ============================================================================

class TestRiskParity:
    """Test risk parity optimization."""
    
    @pytest.mark.asyncio
    async def test_risk_parity_optimization(self):
        """Test risk parity produces equal risk contribution."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        await optimizer.update_asset_data({
            "STOCK": {"expected_return": 0.10, "volatility": 0.20},
            "BOND": {"expected_return": 0.03, "volatility": 0.05}
        })
        
        result = await optimizer.optimize_portfolio(OptimizationObjective.RISK_PARITY)
        
        assert result.optimization_method == OptimizationObjective.RISK_PARITY
        # Lower vol asset should have higher weight to equalize risk
        assert result.weights["BOND"] > result.weights["STOCK"]


# ============================================================================
# BLACK-LITTERMAN TESTS
# ============================================================================

class TestBlackLitterman:
    """Test Black-Litterman optimization."""
    
    @pytest.mark.asyncio
    async def test_black_litterman_with_views(self):
        """Test Black-Litterman with market views."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        await optimizer.update_asset_data({
            "AAPL": {"expected_return": 0.10, "volatility": 0.25},
            "MSFT": {"expected_return": 0.10, "volatility": 0.22}
        })
        
        # Market views: AAPL will outperform
        views = {"AAPL": 0.15, "MSFT": 0.08}
        
        result = await optimizer.optimize_portfolio(
            OptimizationObjective.BLACK_LITTERMAN,
            market_views=views
        )
        
        assert result.optimization_method == OptimizationObjective.BLACK_LITTERMAN


# ============================================================================
# FACTOR MODEL TESTS
# ============================================================================

class TestFactorModel:
    """Test factor model optimization."""
    
    @pytest.mark.asyncio
    async def test_factor_model_optimization(self):
        """Test factor model optimization."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        await optimizer.update_asset_data({
            "AAPL": {"expected_return": 0.12, "volatility": 0.25, "beta": 1.2},
            "MSFT": {"expected_return": 0.10, "volatility": 0.22, "beta": 1.1}
        })
        
        result = await optimizer.optimize_portfolio(OptimizationObjective.FACTOR_MODEL)
        
        assert result.optimization_method == OptimizationObjective.FACTOR_MODEL


# ============================================================================
# DETAILED RISK PARITY TESTS
# ============================================================================

class TestRiskParityDetailed:
    """Test risk parity optimization in detail."""
    
    @pytest.mark.asyncio
    async def test_risk_parity_equal_risk_contribution(self):
        """Test risk parity aims for equal risk contribution."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        # Add assets with different volatilities
        await optimizer.update_asset_data({
            "LOW_VOL": {"expected_return": 0.06, "volatility": 0.10},
            "HIGH_VOL": {"expected_return": 0.12, "volatility": 0.30}
        })
        
        result = await optimizer.optimize_portfolio(OptimizationObjective.RISK_PARITY)
        
        # Higher allocation to low vol asset
        assert result.weights["LOW_VOL"] > result.weights["HIGH_VOL"]


# ============================================================================
# BLACK-LITTERMAN DETAILED TESTS
# ============================================================================

class TestBlackLittermanDetailed:
    """Test Black-Litterman optimization in detail."""
    
    @pytest.mark.asyncio
    async def test_black_litterman_no_views(self):
        """Test Black-Litterman without views falls back to market cap."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        await optimizer.update_asset_data({
            "AAPL": {"expected_return": 0.10, "volatility": 0.20, "market_cap": 3e12},
            "MSFT": {"expected_return": 0.10, "volatility": 0.20, "market_cap": 2e12}
        })
        
        result = await optimizer.optimize_portfolio(OptimizationObjective.BLACK_LITTERMAN)
        
        # AAPL has higher market cap so should have higher weight
        assert result.weights["AAPL"] > result.weights["MSFT"]


# ============================================================================
# OPTIMIZATION HISTORY TESTS
# ============================================================================

class TestOptimizationHistoryTracking:
    """Test optimization history tracking."""
    
    @pytest.mark.asyncio
    async def test_optimization_history_tracked(self):
        """Test that optimization history is tracked."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        await optimizer.update_asset_data({
            "AAPL": {"expected_return": 0.12, "volatility": 0.25},
            "MSFT": {"expected_return": 0.10, "volatility": 0.20}
        })
        
        # Run multiple optimizations
        await optimizer.optimize_portfolio(OptimizationObjective.MAX_SHARPE)
        await optimizer.optimize_portfolio(OptimizationObjective.MIN_VOLATILITY)
        
        assert len(optimizer.optimization_history) == 2


# ============================================================================
# FALLBACK ALLOCATION TESTS
# ============================================================================

class TestFallbackAllocationScenarios:
    """Test fallback allocation in various scenarios."""
    
    @pytest.mark.asyncio
    async def test_fallback_on_low_volatility(self):
        """Test fallback when volatility is very low."""
        from backend.optimization.portfolio_optimizer import (
            PortfolioOptimizer, OptimizationObjective
        )
        
        optimizer = PortfolioOptimizer(enable_slo=False)
        
        # Assets with very low volatility
        await optimizer.update_asset_data({
            "A": {"expected_return": 0.10, "volatility": 0.0001},
            "B": {"expected_return": 0.10, "volatility": 0.0001}
        })
        
        result = await optimizer.optimize_portfolio(OptimizationObjective.MAX_SHARPE)
        
        # Should still return a valid allocation
        assert result is not None
        assert sum(result.weights.values()) == pytest.approx(1.0, abs=0.01)