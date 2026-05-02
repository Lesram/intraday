"""
Portfolio Optimizer for Hedge Fund Grade Trading Platform
========================================================

Advanced portfolio optimization with:
- Mean-variance optimization (Markowitz)
- Risk parity allocation
- Factor-based optimization
- Black-Litterman model
- Rebalancing algorithms
- Constraint management
- Transaction cost optimization
- SLO integration

Created: 2025-09-30
Author: Production Trading System
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
import logging
import math
from typing import Any
import warnings

import numpy as np

# Suppress numpy warnings
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Try importing external dependencies with graceful fallback
try:
    from scipy import optimize
    from scipy.linalg import inv
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logging.warning("SciPy not available - using fallback optimization")

try:
    from backend.monitoring.slo_monitor import SLOMonitor
    SLO_AVAILABLE = True
except ImportError:
    SLO_AVAILABLE = False
    logging.warning("SLO Monitor not available")

try:
    from backend.risk.advanced_risk_manager import AdvancedRiskManager
    RISK_MANAGER_AVAILABLE = True
except ImportError:
    RISK_MANAGER_AVAILABLE = False
    logging.warning("Risk Manager not available")

logger = logging.getLogger(__name__)


class OptimizationObjective(Enum):
    """Portfolio optimization objectives"""
    MAX_SHARPE = "max_sharpe"
    MIN_VOLATILITY = "min_volatility"
    MAX_RETURN = "max_return"
    RISK_PARITY = "risk_parity"
    BLACK_LITTERMAN = "black_litterman"
    FACTOR_MODEL = "factor_model"


class RebalanceFrequency(Enum):
    """Rebalancing frequency options"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


@dataclass
class OptimizationConstraints:
    """Portfolio optimization constraints"""
    min_weight: float = 0.0  # Minimum position weight
    max_weight: float = 1.0  # Maximum position weight
    max_turnover: float = 0.5  # Maximum turnover per rebalance
    min_positions: int = 1  # Minimum number of positions
    max_positions: int = 100  # Maximum number of positions
    sector_limits: dict[str, float] = field(default_factory=dict)  # Sector exposure limits
    target_return: float | None = None  # Target return constraint
    max_tracking_error: float | None = None  # Maximum tracking error
    transaction_cost: float = 0.001  # Transaction cost (0.1%)
    long_only: bool = False  # Long-only constraint


@dataclass
class PortfolioAllocation:
    """Portfolio allocation result"""
    weights: dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    objective_value: float
    optimization_method: OptimizationObjective
    constraints_satisfied: bool
    turnover: float = 0.0
    transaction_costs: float = 0.0
    # K-9: tz-aware UTC (was datetime.utcnow, deprecated in Py 3.12+)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssetData:
    """Asset data for optimization"""
    symbol: str
    expected_return: float
    volatility: float
    current_weight: float = 0.0
    sector: str = "Unknown"
    market_cap: float = 0.0
    beta: float = 1.0
    liquidity_score: float = 1.0
    returns_history: list[float] = field(default_factory=list)


class PortfolioOptimizer:
    """
    Advanced Portfolio Optimization System

    Features:
    - Multiple optimization objectives (Sharpe, risk parity, etc.)
    - Constraint management (position limits, turnover, sectors)
    - Transaction cost optimization
    - Black-Litterman model with market views
    - Factor-based optimization
    - Automated rebalancing with scheduling
    - Integration with risk management system
    - SLO monitoring for optimization performance
    """

    def __init__(self,
                 constraints: OptimizationConstraints | None = None,
                 risk_free_rate: float = 0.02,
                 enable_slo: bool = True):
        """Initialize Portfolio Optimizer"""
        self.constraints = constraints or OptimizationConstraints()
        self.risk_free_rate = risk_free_rate
        self.assets: dict[str, AssetData] = {}
        self.covariance_matrix: np.ndarray | None = None
        self.expected_returns: np.ndarray | None = None
        self.asset_symbols: list[str] = []
        self.current_weights: np.ndarray | None = None
        self.optimization_history: list[PortfolioAllocation] = []
        self.executor = ThreadPoolExecutor(max_workers=4)

        # Initialize risk manager if available
        if RISK_MANAGER_AVAILABLE:
            self.risk_manager = AdvancedRiskManager()
        else:
            self.risk_manager = None

        # SLO Integration
        if enable_slo and SLO_AVAILABLE:
            try:
                self.slo_monitor = SLOMonitor()
                logger.info("SLO monitoring enabled for portfolio optimization")
            except Exception as e:
                logger.warning(f"Failed to initialize SLO monitor: {e}")
                self.slo_monitor = None
        else:
            self.slo_monitor = None

        logger.info("Portfolio Optimizer initialized with production-grade capabilities")

    async def update_asset_data(self, assets_data: dict[str, dict[str, Any]]) -> None:
        """Update asset data for optimization"""
        start_time = datetime.now(UTC)

        try:
            self.assets.clear()

            for symbol, data in assets_data.items():
                asset = AssetData(
                    symbol=symbol,
                    expected_return=data.get('expected_return', 0.0),
                    volatility=data.get('volatility', 0.2),
                    current_weight=data.get('current_weight', 0.0),
                    sector=data.get('sector', 'Unknown'),
                    market_cap=data.get('market_cap', 0.0),
                    beta=data.get('beta', 1.0),
                    liquidity_score=data.get('liquidity_score', 1.0),
                    returns_history=data.get('returns_history', [])
                )
                self.assets[symbol] = asset

            # Update internal matrices
            await self._update_optimization_matrices()

            # Record SLO metrics
            if self.slo_monitor:
                execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
                await self._record_slo_metrics("asset_data_update", execution_time, success=True)

            logger.info(f"Updated data for {len(self.assets)} assets")

        except Exception as e:
            logger.error(f"Error updating asset data: {e}")
            if self.slo_monitor:
                execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
                await self._record_slo_metrics("asset_data_update", execution_time, success=False)
            raise

    async def _update_optimization_matrices(self) -> None:
        """Update covariance matrix and expected returns vector"""
        try:
            if not self.assets:
                return

            self.asset_symbols = list(self.assets.keys())
            len(self.asset_symbols)

            # Create expected returns vector
            self.expected_returns = np.array([
                self.assets[symbol].expected_return for symbol in self.asset_symbols
            ])

            # Create current weights vector
            self.current_weights = np.array([
                self.assets[symbol].current_weight for symbol in self.asset_symbols
            ])

            # Calculate covariance matrix
            await self._calculate_covariance_matrix()

        except Exception as e:
            logger.error(f"Error updating optimization matrices: {e}")

    async def _calculate_covariance_matrix(self) -> None:
        """Calculate covariance matrix from historical returns"""
        try:
            n_assets = len(self.asset_symbols)
            self.covariance_matrix = np.eye(n_assets) * 0.04  # Default 20% vol diagonal matrix

            # If we have return histories, calculate actual covariance
            return_histories = []
            min_length = float('inf')

            for symbol in self.asset_symbols:
                returns = self.assets[symbol].returns_history
                if len(returns) > 20:  # Minimum for covariance calculation
                    return_histories.append(returns)
                    min_length = min(min_length, len(returns))
                else:
                    return_histories.append([])

            if min_length < float('inf') and min_length > 20:
                # Align all return series to same length
                aligned_returns = []
                for returns in return_histories:
                    if len(returns) >= min_length:
                        aligned_returns.append(returns[-int(min_length):])
                    else:
                        # Pad with zeros or use asset volatility
                        symbol = self.asset_symbols[len(aligned_returns)]
                        vol = self.assets[symbol].volatility / math.sqrt(252)
                        padding = np.random.normal(0, vol, int(min_length))
                        aligned_returns.append(padding.tolist())

                # Calculate covariance matrix
                returns_matrix = np.array(aligned_returns).T
                self.covariance_matrix = np.cov(returns_matrix.T) * 252  # Annualize

                # Ensure positive definite
                if not self._is_positive_definite(self.covariance_matrix):
                    self.covariance_matrix = self._make_positive_definite(self.covariance_matrix)

            # Fallback: use individual volatilities for diagonal
            else:
                for i, symbol in enumerate(self.asset_symbols):
                    vol = self.assets[symbol].volatility
                    self.covariance_matrix[i, i] = vol ** 2

        except Exception as e:
            logger.error(f"Error calculating covariance matrix: {e}")
            # Fallback to diagonal matrix
            n_assets = len(self.asset_symbols)
            self.covariance_matrix = np.eye(n_assets) * 0.04

    def _is_positive_definite(self, matrix: np.ndarray) -> bool:
        """Check if matrix is positive definite"""
        try:
            np.linalg.cholesky(matrix)
            return True
        except np.linalg.LinAlgError:
            return False

    def _make_positive_definite(self, matrix: np.ndarray) -> np.ndarray:
        """Make matrix positive definite by adding regularization"""
        try:
            eigenvals, eigenvecs = np.linalg.eigh(matrix)
            eigenvals = np.maximum(eigenvals, 1e-8)  # Ensure positive eigenvalues
            return eigenvecs @ np.diag(eigenvals) @ eigenvecs.T
        except Exception:
            # Ultimate fallback
            return np.eye(matrix.shape[0]) * 0.04

    async def optimize_portfolio(self,
                                objective: OptimizationObjective = OptimizationObjective.MAX_SHARPE,
                                market_views: dict[str, float] | None = None) -> PortfolioAllocation:
        """
        Optimize portfolio based on specified objective

        Args:
            objective: Optimization objective
            market_views: Market views for Black-Litterman (optional)

        Returns:
            Optimized portfolio allocation
        """
        start_time = datetime.now(UTC)

        try:
            if not self.assets or self.covariance_matrix is None:
                raise ValueError("Asset data not initialized")

            logger.info(f"Optimizing portfolio with objective: {objective.value}")

            # Choose optimization method
            if objective == OptimizationObjective.MAX_SHARPE:
                result = await self._optimize_max_sharpe()
            elif objective == OptimizationObjective.MIN_VOLATILITY:
                result = await self._optimize_min_volatility()
            elif objective == OptimizationObjective.MAX_RETURN:
                result = await self._optimize_max_return()
            elif objective == OptimizationObjective.RISK_PARITY:
                result = await self._optimize_risk_parity()
            elif objective == OptimizationObjective.BLACK_LITTERMAN:
                result = await self._optimize_black_litterman(market_views)
            elif objective == OptimizationObjective.FACTOR_MODEL:
                result = await self._optimize_factor_model()
            else:
                raise ValueError(f"Unknown optimization objective: {objective}")

            # Calculate additional metrics
            result.turnover = self._calculate_turnover(result.weights)
            result.transaction_costs = result.turnover * self.constraints.transaction_cost
            result.constraints_satisfied = self._check_constraints(result.weights)

            # Store in history
            self.optimization_history.append(result)

            # Keep only last 100 optimizations
            if len(self.optimization_history) > 100:
                self.optimization_history = self.optimization_history[-100:]

            # Record SLO metrics
            if self.slo_monitor:
                execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
                await self._record_slo_metrics("portfolio_optimization", execution_time, success=True)

            logger.info(f"Portfolio optimization completed: {result.objective_value:.4f}")
            return result

        except Exception as e:
            logger.error(f"Error in portfolio optimization: {e}")
            if self.slo_monitor:
                execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
                await self._record_slo_metrics("portfolio_optimization", execution_time, success=False)
            raise

    async def _optimize_max_sharpe(self) -> PortfolioAllocation:
        """Optimize for maximum Sharpe ratio"""
        try:
            n_assets = len(self.asset_symbols)

            # Objective: maximize Sharpe ratio = (return - risk_free) / volatility
            def negative_sharpe(weights):
                portfolio_return = np.dot(weights, self.expected_returns)
                portfolio_vol = np.sqrt(np.dot(weights, np.dot(self.covariance_matrix, weights)))
                if portfolio_vol == 0:
                    return -np.inf
                sharpe = (portfolio_return - self.risk_free_rate) / portfolio_vol
                return -sharpe  # Negative for minimization

            # Constraints
            constraints = [{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}]  # Weights sum to 1

            # Add target return constraint if specified
            if self.constraints.target_return is not None:
                constraints.append({
                    'type': 'eq',
                    'fun': lambda x: np.dot(x, self.expected_returns) - self.constraints.target_return
                })

            # Bounds
            bounds = [(self.constraints.min_weight, self.constraints.max_weight) for _ in range(n_assets)]
            if self.constraints.long_only:
                bounds = [(0, self.constraints.max_weight) for _ in range(n_assets)]

            # Initial guess (equal weights)
            x0 = np.ones(n_assets) / n_assets

            # Optimize
            if SCIPY_AVAILABLE:
                result = optimize.minimize(negative_sharpe, x0, method='SLSQP',
                                         bounds=bounds, constraints=constraints)
                optimal_weights = result.x
                success = result.success
            else:
                # Fallback: equal weight
                optimal_weights = np.ones(n_assets) / n_assets
                success = True

            # Calculate metrics
            portfolio_return = np.dot(optimal_weights, self.expected_returns)
            portfolio_vol = np.sqrt(np.dot(optimal_weights, np.dot(self.covariance_matrix, optimal_weights)))
            sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_vol if portfolio_vol > 0 else 0

            return PortfolioAllocation(
                weights={symbol: float(weight) for symbol, weight in zip(self.asset_symbols, optimal_weights, strict=False)},
                expected_return=float(portfolio_return),
                expected_volatility=float(portfolio_vol),
                sharpe_ratio=float(sharpe_ratio),
                objective_value=float(sharpe_ratio),
                optimization_method=OptimizationObjective.MAX_SHARPE,
                constraints_satisfied=success
            )

        except Exception as e:
            logger.error(f"Error in max Sharpe optimization: {e}")
            return self._fallback_allocation(OptimizationObjective.MAX_SHARPE)

    async def _optimize_min_volatility(self) -> PortfolioAllocation:
        """Optimize for minimum volatility"""
        try:
            n_assets = len(self.asset_symbols)

            # Objective: minimize portfolio volatility
            def portfolio_volatility(weights):
                return np.sqrt(np.dot(weights, np.dot(self.covariance_matrix, weights)))

            # Constraints
            constraints = [{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}]

            # Bounds
            bounds = [(self.constraints.min_weight, self.constraints.max_weight) for _ in range(n_assets)]
            if self.constraints.long_only:
                bounds = [(0, self.constraints.max_weight) for _ in range(n_assets)]

            # Initial guess
            x0 = np.ones(n_assets) / n_assets

            # Optimize
            if SCIPY_AVAILABLE:
                result = optimize.minimize(portfolio_volatility, x0, method='SLSQP',
                                         bounds=bounds, constraints=constraints)
                optimal_weights = result.x
                success = result.success
            else:
                # Fallback: inverse volatility weighting
                inv_vols = 1.0 / np.array([self.assets[symbol].volatility for symbol in self.asset_symbols])
                optimal_weights = inv_vols / np.sum(inv_vols)
                success = True

            # Calculate metrics
            portfolio_return = np.dot(optimal_weights, self.expected_returns)
            portfolio_vol = portfolio_volatility(optimal_weights)
            sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_vol if portfolio_vol > 0 else 0

            return PortfolioAllocation(
                weights={symbol: float(weight) for symbol, weight in zip(self.asset_symbols, optimal_weights, strict=False)},
                expected_return=float(portfolio_return),
                expected_volatility=float(portfolio_vol),
                sharpe_ratio=float(sharpe_ratio),
                objective_value=float(-portfolio_vol),  # Negative vol for maximization context
                optimization_method=OptimizationObjective.MIN_VOLATILITY,
                constraints_satisfied=success
            )

        except Exception as e:
            logger.error(f"Error in min volatility optimization: {e}")
            return self._fallback_allocation(OptimizationObjective.MIN_VOLATILITY)

    async def _optimize_max_return(self) -> PortfolioAllocation:
        """Optimize for maximum expected return"""
        try:
            n_assets = len(self.asset_symbols)

            # Objective: maximize expected return
            def negative_return(weights):
                return -np.dot(weights, self.expected_returns)

            # Constraints
            constraints = [{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}]

            # Add volatility constraint if needed
            if self.constraints.max_tracking_error is not None:
                def vol_constraint(weights):
                    vol = np.sqrt(np.dot(weights, np.dot(self.covariance_matrix, weights)))
                    return self.constraints.max_tracking_error - vol
                constraints.append({'type': 'ineq', 'fun': vol_constraint})

            # Bounds
            bounds = [(self.constraints.min_weight, self.constraints.max_weight) for _ in range(n_assets)]
            if self.constraints.long_only:
                bounds = [(0, self.constraints.max_weight) for _ in range(n_assets)]

            # Initial guess
            x0 = np.ones(n_assets) / n_assets

            # Optimize
            if SCIPY_AVAILABLE:
                result = optimize.minimize(negative_return, x0, method='SLSQP',
                                         bounds=bounds, constraints=constraints)
                optimal_weights = result.x
                success = result.success
            else:
                # Fallback: weight by expected returns
                returns = np.array([max(0, self.assets[symbol].expected_return) for symbol in self.asset_symbols])
                if np.sum(returns) > 0:
                    optimal_weights = returns / np.sum(returns)
                else:
                    optimal_weights = np.ones(n_assets) / n_assets
                success = True

            # Calculate metrics
            portfolio_return = np.dot(optimal_weights, self.expected_returns)
            portfolio_vol = np.sqrt(np.dot(optimal_weights, np.dot(self.covariance_matrix, optimal_weights)))
            sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_vol if portfolio_vol > 0 else 0

            return PortfolioAllocation(
                weights={symbol: float(weight) for symbol, weight in zip(self.asset_symbols, optimal_weights, strict=False)},
                expected_return=float(portfolio_return),
                expected_volatility=float(portfolio_vol),
                sharpe_ratio=float(sharpe_ratio),
                objective_value=float(portfolio_return),
                optimization_method=OptimizationObjective.MAX_RETURN,
                constraints_satisfied=success
            )

        except Exception as e:
            logger.error(f"Error in max return optimization: {e}")
            return self._fallback_allocation(OptimizationObjective.MAX_RETURN)

    async def _optimize_risk_parity(self) -> PortfolioAllocation:
        """Optimize for risk parity (equal risk contribution)"""
        try:
            n_assets = len(self.asset_symbols)

            # Risk parity: each asset contributes equally to portfolio risk
            def risk_parity_objective(weights):
                portfolio_vol = np.sqrt(np.dot(weights, np.dot(self.covariance_matrix, weights)))
                if portfolio_vol == 0:
                    return 1e10

                # Risk contributions
                marginal_contrib = np.dot(self.covariance_matrix, weights) / portfolio_vol
                contrib = weights * marginal_contrib

                # Target: equal contributions
                target_contrib = portfolio_vol / n_assets
                diff = contrib - target_contrib
                return np.sum(diff ** 2)

            # Constraints
            constraints = [{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}]

            # Bounds (risk parity typically long-only)
            bounds = [(0.001, self.constraints.max_weight) for _ in range(n_assets)]

            # Initial guess: inverse volatility weights
            inv_vols = 1.0 / np.array([self.assets[symbol].volatility for symbol in self.asset_symbols])
            x0 = inv_vols / np.sum(inv_vols)

            # Optimize
            if SCIPY_AVAILABLE:
                result = optimize.minimize(risk_parity_objective, x0, method='SLSQP',
                                         bounds=bounds, constraints=constraints)
                optimal_weights = result.x
                success = result.success
            else:
                # Fallback: inverse volatility weighting (approximation)
                optimal_weights = x0
                success = True

            # Calculate metrics
            portfolio_return = np.dot(optimal_weights, self.expected_returns)
            portfolio_vol = np.sqrt(np.dot(optimal_weights, np.dot(self.covariance_matrix, optimal_weights)))
            sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_vol if portfolio_vol > 0 else 0

            return PortfolioAllocation(
                weights={symbol: float(weight) for symbol, weight in zip(self.asset_symbols, optimal_weights, strict=False)},
                expected_return=float(portfolio_return),
                expected_volatility=float(portfolio_vol),
                sharpe_ratio=float(sharpe_ratio),
                objective_value=float(-risk_parity_objective(optimal_weights)),
                optimization_method=OptimizationObjective.RISK_PARITY,
                constraints_satisfied=success
            )

        except Exception as e:
            logger.error(f"Error in risk parity optimization: {e}")
            return self._fallback_allocation(OptimizationObjective.RISK_PARITY)

    async def _optimize_black_litterman(self, market_views: dict[str, float] | None = None) -> PortfolioAllocation:
        """Black-Litterman optimization with market views"""
        try:
            # If no views provided, fall back to market cap weighting
            if not market_views:
                market_caps = np.array([self.assets[symbol].market_cap for symbol in self.asset_symbols])
                if np.sum(market_caps) > 0:
                    market_weights = market_caps / np.sum(market_caps)
                else:
                    market_weights = np.ones(len(self.asset_symbols)) / len(self.asset_symbols)

                portfolio_return = np.dot(market_weights, self.expected_returns)
                portfolio_vol = np.sqrt(np.dot(market_weights, np.dot(self.covariance_matrix, market_weights)))
                sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_vol if portfolio_vol > 0 else 0

                return PortfolioAllocation(
                    weights={symbol: float(weight) for symbol, weight in zip(self.asset_symbols, market_weights, strict=False)},
                    expected_return=float(portfolio_return),
                    expected_volatility=float(portfolio_vol),
                    sharpe_ratio=float(sharpe_ratio),
                    objective_value=float(sharpe_ratio),
                    optimization_method=OptimizationObjective.BLACK_LITTERMAN,
                    constraints_satisfied=True,
                    metadata={'views_applied': 0}
                )

            # Simplified Black-Litterman implementation
            # In production, this would be more sophisticated
            n_assets = len(self.asset_symbols)

            # Market cap weights as prior
            market_caps = np.array([self.assets[symbol].market_cap for symbol in self.asset_symbols])
            if np.sum(market_caps) > 0:
                w_market = market_caps / np.sum(market_caps)
            else:
                w_market = np.ones(n_assets) / n_assets

            # Implied returns (reverse optimization)
            risk_aversion = 3.0  # Typical risk aversion parameter
            pi = risk_aversion * np.dot(self.covariance_matrix, w_market)

            # Incorporate views
            view_symbols = [s for s in market_views.keys() if s in self.asset_symbols]
            if view_symbols:
                # Create picking matrix P and view vector Q
                P = np.zeros((len(view_symbols), n_assets))
                Q = np.zeros(len(view_symbols))

                for i, symbol in enumerate(view_symbols):
                    asset_idx = self.asset_symbols.index(symbol)
                    P[i, asset_idx] = 1.0
                    Q[i] = market_views[symbol]

                # View uncertainty (Omega)
                omega = np.eye(len(view_symbols)) * 0.01  # 1% uncertainty

                # Black-Litterman formula
                try:
                    if not SCIPY_AVAILABLE:
                        # Use numpy fallback if SciPy not available
                        raise ImportError("SciPy not available for Black-Litterman")

                    tau = 1.0 / len(self.expected_returns)  # Scaling factor
                    M1 = inv(tau * self.covariance_matrix)
                    M2 = np.dot(P.T, np.dot(inv(omega), P))
                    M3 = np.dot(inv(tau * self.covariance_matrix), pi)
                    M4 = np.dot(P.T, np.dot(inv(omega), Q))

                    # New expected returns
                    mu_bl = np.dot(inv(M1 + M2), M3 + M4)

                    # New covariance matrix
                    sigma_bl = inv(M1 + M2)

                except (np.linalg.LinAlgError, ImportError) as e:
                    # Fallback if matrix inversion fails or SciPy not available
                    logger.warning(f"Black-Litterman failed ({e}), using fallback")
                    mu_bl = self.expected_returns
                    sigma_bl = self.covariance_matrix
            else:
                mu_bl = self.expected_returns
                sigma_bl = self.covariance_matrix

            # Optimize with Black-Litterman inputs
            def negative_sharpe(weights):
                portfolio_return = np.dot(weights, mu_bl)
                portfolio_vol = np.sqrt(np.dot(weights, np.dot(sigma_bl, weights)))
                if portfolio_vol == 0:
                    return -np.inf
                return -(portfolio_return - self.risk_free_rate) / portfolio_vol

            constraints = [{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}]
            bounds = [(0, self.constraints.max_weight) for _ in range(n_assets)]
            x0 = w_market

            if SCIPY_AVAILABLE:
                result = optimize.minimize(negative_sharpe, x0, method='SLSQP',
                                         bounds=bounds, constraints=constraints)
                optimal_weights = result.x
                success = result.success
            else:
                optimal_weights = w_market
                success = True

            # Calculate metrics with original covariance matrix
            portfolio_return = np.dot(optimal_weights, self.expected_returns)
            portfolio_vol = np.sqrt(np.dot(optimal_weights, np.dot(self.covariance_matrix, optimal_weights)))
            sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_vol if portfolio_vol > 0 else 0

            return PortfolioAllocation(
                weights={symbol: float(weight) for symbol, weight in zip(self.asset_symbols, optimal_weights, strict=False)},
                expected_return=float(portfolio_return),
                expected_volatility=float(portfolio_vol),
                sharpe_ratio=float(sharpe_ratio),
                objective_value=float(sharpe_ratio),
                optimization_method=OptimizationObjective.BLACK_LITTERMAN,
                constraints_satisfied=success,
                metadata={'views_applied': len(view_symbols)}
            )

        except Exception as e:
            logger.error(f"Error in Black-Litterman optimization: {e}")
            return self._fallback_allocation(OptimizationObjective.BLACK_LITTERMAN)

    async def _optimize_factor_model(self) -> PortfolioAllocation:
        """Factor-based optimization"""
        try:
            # Simplified factor model using beta as single factor
            n_assets = len(self.asset_symbols)

            # Create factor loadings matrix (using beta)
            betas = np.array([self.assets[symbol].beta for symbol in self.asset_symbols])

            # Factor-based objective: minimize factor risk, maximize alpha
            def factor_objective(weights):
                # Factor exposure
                factor_exposure = np.dot(weights, betas)

                # Penalize extreme factor exposure
                factor_penalty = (factor_exposure - 1.0) ** 2

                # Reward expected alpha (return above beta * market return)
                market_return = 0.08  # Assumed market return
                alpha_reward = np.dot(weights, self.expected_returns - betas * market_return)

                return factor_penalty - alpha_reward

            # Constraints
            constraints = [{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}]
            bounds = [(self.constraints.min_weight, self.constraints.max_weight) for _ in range(n_assets)]

            if self.constraints.long_only:
                bounds = [(0, self.constraints.max_weight) for _ in range(n_assets)]

            # Initial guess
            x0 = np.ones(n_assets) / n_assets

            # Optimize
            if SCIPY_AVAILABLE:
                result = optimize.minimize(factor_objective, x0, method='SLSQP',
                                         bounds=bounds, constraints=constraints)
                optimal_weights = result.x
                success = result.success
            else:
                # Fallback: weight by inverse beta (market neutral tendency)
                inv_betas = 1.0 / np.maximum(betas, 0.1)  # Avoid division by zero
                optimal_weights = inv_betas / np.sum(inv_betas)
                success = True

            # Calculate metrics
            portfolio_return = np.dot(optimal_weights, self.expected_returns)
            portfolio_vol = np.sqrt(np.dot(optimal_weights, np.dot(self.covariance_matrix, optimal_weights)))
            sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_vol if portfolio_vol > 0 else 0
            portfolio_beta = np.dot(optimal_weights, betas)

            return PortfolioAllocation(
                weights={symbol: float(weight) for symbol, weight in zip(self.asset_symbols, optimal_weights, strict=False)},
                expected_return=float(portfolio_return),
                expected_volatility=float(portfolio_vol),
                sharpe_ratio=float(sharpe_ratio),
                objective_value=float(-factor_objective(optimal_weights)),
                optimization_method=OptimizationObjective.FACTOR_MODEL,
                constraints_satisfied=success,
                metadata={'portfolio_beta': float(portfolio_beta)}
            )

        except Exception as e:
            logger.error(f"Error in factor model optimization: {e}")
            return self._fallback_allocation(OptimizationObjective.FACTOR_MODEL)

    def _fallback_allocation(self, method: OptimizationObjective) -> PortfolioAllocation:
        """Fallback allocation if optimization fails"""
        n_assets = len(self.asset_symbols)
        equal_weights = np.ones(n_assets) / n_assets

        portfolio_return = np.dot(equal_weights, self.expected_returns)
        portfolio_vol = np.sqrt(np.dot(equal_weights, np.dot(self.covariance_matrix, equal_weights)))
        sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_vol if portfolio_vol > 0 else 0

        return PortfolioAllocation(
            weights={symbol: 1.0/n_assets for symbol in self.asset_symbols},
            expected_return=float(portfolio_return),
            expected_volatility=float(portfolio_vol),
            sharpe_ratio=float(sharpe_ratio),
            objective_value=0.0,
            optimization_method=method,
            constraints_satisfied=False,
            metadata={'fallback': True}
        )

    def _calculate_turnover(self, new_weights: dict[str, float]) -> float:
        """Calculate portfolio turnover"""
        if self.current_weights is None:
            return 1.0  # 100% turnover for initial allocation

        turnover = 0.0
        for i, symbol in enumerate(self.asset_symbols):
            old_weight = self.current_weights[i] if i < len(self.current_weights) else 0.0
            new_weight = new_weights.get(symbol, 0.0)
            turnover += abs(new_weight - old_weight)

        return turnover / 2.0  # Divide by 2 since trades are paired

    def _check_constraints(self, weights: dict[str, float]) -> bool:
        """Check if allocation satisfies constraints"""
        try:
            # Weight bounds
            for symbol, weight in weights.items():
                if weight < self.constraints.min_weight or weight > self.constraints.max_weight:
                    return False

            # Sector constraints
            if self.constraints.sector_limits:
                sector_exposure = {}
                for symbol, weight in weights.items():
                    sector = self.assets[symbol].sector
                    if sector not in sector_exposure:
                        sector_exposure[sector] = 0.0
                    sector_exposure[sector] += abs(weight)

                for sector, limit in self.constraints.sector_limits.items():
                    if sector_exposure.get(sector, 0.0) > limit:
                        return False

            # Turnover constraint
            turnover = self._calculate_turnover(weights)
            if turnover > self.constraints.max_turnover:
                return False

            # Position count constraints
            active_positions = sum(1 for w in weights.values() if abs(w) > 0.001)
            if active_positions < self.constraints.min_positions or active_positions > self.constraints.max_positions:
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking constraints: {e}")
            return False

    async def _record_slo_metrics(self, operation: str, execution_time: float, success: bool) -> None:
        """Record SLO metrics"""
        if not self.slo_monitor:
            return

        try:
            await self.slo_monitor.record_metric(
                service_name="portfolio_optimizer",
                operation_name=operation,
                latency_ms=execution_time,
                success=success,
                metadata={
                    'asset_count': len(self.assets),
                    'optimization_history_length': len(self.optimization_history)
                }
            )
        except Exception as e:
            logger.error(f"Error recording SLO metrics: {e}")

    async def generate_rebalance_schedule(self,
                                        frequency: RebalanceFrequency,
                                        start_date: datetime | None = None) -> list[datetime]:
        """Generate rebalancing schedule"""
        if start_date is None:
            start_date = datetime.now(UTC)

        schedule = []
        current_date = start_date

        # Generate next 12 rebalancing dates
        for _ in range(12):
            if frequency == RebalanceFrequency.DAILY:
                current_date += timedelta(days=1)
            elif frequency == RebalanceFrequency.WEEKLY:
                current_date += timedelta(weeks=1)
            elif frequency == RebalanceFrequency.MONTHLY:
                # Approximate monthly (30 days)
                current_date += timedelta(days=30)
            elif frequency == RebalanceFrequency.QUARTERLY:
                # Approximate quarterly (90 days)
                current_date += timedelta(days=90)

            schedule.append(current_date)

        return schedule

    def get_optimization_summary(self) -> dict[str, Any]:
        """Get optimization summary and statistics"""
        if not self.optimization_history:
            return {'status': 'no_optimizations'}

        recent = self.optimization_history[-10:]  # Last 10 optimizations

        return {
            'total_optimizations': len(self.optimization_history),
            'recent_performance': {
                'avg_sharpe': np.mean([opt.sharpe_ratio for opt in recent]),
                'avg_return': np.mean([opt.expected_return for opt in recent]),
                'avg_volatility': np.mean([opt.expected_volatility for opt in recent]),
                'avg_turnover': np.mean([opt.turnover for opt in recent]),
                'constraints_violations': sum(1 for opt in recent if not opt.constraints_satisfied)
            },
            'latest_allocation': {
                'method': recent[-1].optimization_method.value,
                'sharpe_ratio': recent[-1].sharpe_ratio,
                'expected_return': recent[-1].expected_return,
                'expected_volatility': recent[-1].expected_volatility,
                'turnover': recent[-1].turnover,
                'timestamp': recent[-1].timestamp.isoformat()
            },
            'asset_statistics': {
                'asset_count': len(self.assets),
                'avg_expected_return': np.mean([asset.expected_return for asset in self.assets.values()]),
                'avg_volatility': np.mean([asset.volatility for asset in self.assets.values()]),
                'sector_distribution': self._get_sector_distribution()
            }
        }

    def _get_sector_distribution(self) -> dict[str, int]:
        """Get distribution of assets by sector"""
        sectors = {}
        for asset in self.assets.values():
            sector = asset.sector
            sectors[sector] = sectors.get(sector, 0) + 1
        return sectors


# Example usage and testing
if __name__ == "__main__":
    async def test_portfolio_optimizer():
        """Test Portfolio Optimizer"""
        print("📈 Testing Portfolio Optimizer")
        print("=" * 50)

        # Initialize optimizer
        constraints = OptimizationConstraints(
            max_weight=0.3,
            max_turnover=0.5,
            long_only=True,
            transaction_cost=0.001
        )

        optimizer = PortfolioOptimizer(constraints=constraints)

        # Sample asset data
        assets_data = {
            'AAPL': {
                'expected_return': 0.12,
                'volatility': 0.25,
                'current_weight': 0.3,
                'sector': 'Technology',
                'market_cap': 2.5e12,
                'beta': 1.2,
                'returns_history': np.random.normal(0.001, 0.02, 100).tolist()
            },
            'GOOGL': {
                'expected_return': 0.15,
                'volatility': 0.28,
                'current_weight': 0.3,
                'sector': 'Technology',
                'market_cap': 1.8e12,
                'beta': 1.1,
                'returns_history': np.random.normal(0.0012, 0.022, 100).tolist()
            },
            'SPY': {
                'expected_return': 0.08,
                'volatility': 0.15,
                'current_weight': 0.4,
                'sector': 'ETF',
                'market_cap': 5e11,
                'beta': 1.0,
                'returns_history': np.random.normal(0.0008, 0.015, 100).tolist()
            }
        }

        # Update asset data
        await optimizer.update_asset_data(assets_data)

        # Test different optimization methods
        methods = [
            OptimizationObjective.MAX_SHARPE,
            OptimizationObjective.MIN_VOLATILITY,
            OptimizationObjective.RISK_PARITY,
            OptimizationObjective.BLACK_LITTERMAN
        ]

        print("🎯 Testing Optimization Methods:")
        for method in methods:
            try:
                result = await optimizer.optimize_portfolio(method)
                print(f"\n{method.value.upper()}:")
                print(f"  Sharpe Ratio: {result.sharpe_ratio:.3f}")
                print(f"  Expected Return: {result.expected_return:.1%}")
                print(f"  Volatility: {result.expected_volatility:.1%}")
                print(f"  Turnover: {result.turnover:.1%}")
                print(f"  Weights: {result.weights}")
            except Exception as e:
                print(f"  Error in {method.value}: {e}")

        # Test with market views (Black-Litterman)
        market_views = {'AAPL': 0.15, 'GOOGL': 0.10}  # Bullish on AAPL, neutral on GOOGL
        print(f"\n📊 Testing with Market Views: {market_views}")
        bl_result = await optimizer.optimize_portfolio(OptimizationObjective.BLACK_LITTERMAN, market_views)
        print(f"  BL Sharpe: {bl_result.sharpe_ratio:.3f}")
        print(f"  BL Weights: {bl_result.weights}")

        # Get optimization summary
        summary = optimizer.get_optimization_summary()
        print("\n📈 Optimization Summary:")
        for key, value in summary.items():
            if key != 'asset_statistics':
                print(f"  {key}: {value}")

        print("\n✅ Portfolio Optimizer test completed successfully!")

    # Run test
    asyncio.run(test_portfolio_optimizer())
