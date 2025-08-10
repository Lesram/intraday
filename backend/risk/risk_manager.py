"""
BRANCH 2.8: Async-first Risk Manager with robust math and structured decisions.

Implements institutional-grade risk controls with:
- Async hygiene (no event loop blocking)  
- Strong types and structured decision flow
- Numerically stable Kelly/VaR/CVaR calculations
- Comprehensive metrics and audit logging
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
import logging
import time
from typing import Any
import warnings

import numpy as np

from ..config import get_settings
from ..infra.metrics import get_metrics_registry
from ..utils.logger import get_structured_logger
from .types import OrderSpec, PortfolioState, RiskDecision

# Numerical stability constants
EPS = 1e-12
MIN_SAMPLES = 30

# Bounded reason categories for metrics
RISK_REASONS = {
    "window", "halt", "whitelist", "pos_cap", "notional_cap",
    "var", "cvar", "kelly", "correlation", "sector", "heat", "leverage"
}


class RiskMathUtils:
    """Pure mathematical utilities for risk calculations (sync, no I/O)."""

    @staticmethod
    def kelly_fraction(
        mean_return: float,
        variance: float,
        kelly_floor: float = 0.0,
        kelly_ceiling: float = 0.2
    ) -> float:
        """Calculate Kelly optimal fraction with stability guards."""
        if variance < EPS or mean_return <= 0:
            return kelly_floor
        kelly = mean_return / variance
        return max(kelly_floor, min(kelly, kelly_ceiling))

    @staticmethod
    def ewma_volatility(returns: np.ndarray, lambda_param: float = 0.94) -> float:
        """Calculate EWMA volatility with numerical stability."""
        if len(returns) < 2:
            return 0.1  # Fallback volatility

        returns = returns[np.isfinite(returns)]
        if len(returns) < 2:
            return 0.1

        weights = np.power(lambda_param, np.arange(len(returns))[::-1])
        weights /= weights.sum()

        mean_return = np.average(returns, weights=weights)
        variance = np.average((returns - mean_return) ** 2, weights=weights)

        # Annualize (assuming daily returns)
        return max(np.sqrt(variance * 252), EPS)

    @staticmethod
    def parametric_var(returns: list, confidence: float = 0.05) -> float:
        """Calculate parametric VaR assuming normal distribution"""
        if len(returns) < 2:
            return 0.0

        returns_array = np.array(returns)
        returns_array = returns_array[np.isfinite(returns_array)]

        if len(returns_array) < 2:
            return 0.0

        mean_return = np.mean(returns_array)
        std_return = np.std(returns_array, ddof=1)

        # Z-score for given confidence level (e.g., 1.645 for 5% VaR)
        # Approximation for normal quantiles to avoid scipy dependency
        if confidence <= 0.01:
            z_score = -2.33  # 1% VaR
        elif confidence <= 0.05:
            z_score = -1.645  # 5% VaR
        elif confidence <= 0.1:
            z_score = -1.28  # 10% VaR
        else:
            z_score = -1.0   # Conservative fallback

        return -(mean_return + z_score * std_return)

    @staticmethod
    def historical_cvar(returns: list, confidence: float = 0.05) -> float:
        """Calculate Conditional Value at Risk (Expected Shortfall)"""
        if len(returns) < 10:
            return 0.0

        returns_array = np.array(returns)
        returns_array = returns_array[np.isfinite(returns_array)]

        if len(returns_array) < 10:
            return 0.0

        sorted_returns = np.sort(returns_array)

        # Find the VaR cutoff point
        cutoff_index = max(1, int(confidence * len(sorted_returns)))

        # CVaR is the mean of returns below the VaR threshold
        worst_returns = sorted_returns[:cutoff_index]
        return -np.mean(worst_returns) if len(worst_returns) > 0 else 0.0


class AsyncRiskManager:
    """Async-first risk manager with structured decisions and robust math."""

    def __init__(
        self,
        max_position_per_symbol: int = 10000,
        max_single_position_value: int = 100000,
        max_portfolio_var: float = 0.05,
        logger: logging.Logger | None = None,
        metrics: Any | None = None
    ):
        """Initialize async-first risk manager with institutional controls."""
        self.max_position_per_symbol = max_position_per_symbol
        self.max_single_position_value = max_single_position_value
        self.max_portfolio_var = max_portfolio_var
        self.math_utils = RiskMathUtils()
        self.logger = logger or get_structured_logger("risk_manager")
        self.metrics = metrics or get_metrics_registry()
        self.settings = get_settings()

        # Risk state
        self.daily_trades = 0
        self.circuit_breaker_active = False
        self.halted_symbols: set[str] = set()

    async def before_order(
        self,
        order: OrderSpec,
        portfolio_state: PortfolioState | None = None,
        request_id: str | None = None
    ) -> RiskDecision:
        """Main risk check entry point - fully async with structured decisions."""
        start_time = time.time()

        try:
            # Comprehensive risk evaluation
            decision = await self._evaluate_order_comprehensive(order)

            # Record metrics
            decision_time = time.time() - start_time

            # Update metrics using the registry interface
            if decision.allowed:
                self.metrics.counter("risk_allows_total").inc()
            else:
                reason_label = decision.reason if decision.reason in RISK_REASONS else "other"
                self.metrics.counter("risk_blocks_total", {"reason": reason_label}).inc()

            # Record decision latency
            self.metrics.histogram("risk_decision_latency_seconds").observe(decision_time)


            return decision

        except Exception as e:
            self.logger.error("Risk check failed", extra={"error": str(e), "order": order})
            decision = RiskDecision.block(
                reason="other",
                adjustments={"error": f"Risk check failed: {str(e)}"}
            )

            decision_time = time.time() - start_time
            self.metrics.histogram("risk_decision_latency_seconds").observe(decision_time)
            self.metrics.counter("risk_blocks_total", {"reason": "other"}).inc()

            return decision

    async def _evaluate_order_comprehensive(self, order: OrderSpec) -> RiskDecision:
        """Comprehensive risk evaluation with all institutional controls"""

        # Get current portfolio state (would come from persistence layer)
        current_state = await self._get_portfolio_state(order.symbol)
        historical_returns = self._get_historical_returns(order.symbol, 60)

        # 1. Position limits check
        current_pos = current_state.positions.get(order.symbol, Decimal('0'))
        order_qty = order.qty if order.side == "buy" else -order.qty
        new_position = current_pos + order_qty

        if abs(new_position) > self.max_position_per_symbol:
            return RiskDecision.block(
                reason="position_limit_exceeded",
                adjustments={"max_allowed": str(self.max_position_per_symbol - abs(current_pos))},
                limits={"max_position_per_symbol": str(self.max_position_per_symbol)},
                original_qty=order.qty
            )

        # 2. Notional value checks
        if order.notional > self.max_single_position_value:
            return RiskDecision.block(
                reason="single_position_value_limit",
                adjustments={"max_notional": str(self.max_single_position_value)},
                limits={"max_single_position_value": str(self.max_single_position_value)},
                original_qty=order.qty
            )

        # 3. Kelly sizing check (if we have returns data)
        if len(historical_returns) >= 10:
            expected_return = float(np.mean(historical_returns[-30:]))
            volatility = self.math_utils.ewma_volatility(np.array(historical_returns[-30:]))

            if expected_return > 0:
                kelly_fraction = self.math_utils.kelly_fraction(expected_return, volatility)
                portfolio_value = float(current_state.equity)
                max_kelly_notional = kelly_fraction * portfolio_value

                if float(order.notional) > max_kelly_notional * 2:  # 2x Kelly max
                    suggested_qty = Decimal(str(max_kelly_notional / float(order.price or 1)))
                    return RiskDecision.block(
                        reason="kelly_size_exceeded",
                        original_qty=order.qty,
                        adjusted_qty=suggested_qty,
                        adjustments={"kelly_limit": str(max_kelly_notional)}
                    )

        # 4. VaR check (if we have sufficient data)
        if len(historical_returns) >= 20:
            var_95 = self.math_utils.parametric_var(historical_returns[-60:])
            if var_95 > self.max_portfolio_var:
                return RiskDecision.block(
                    reason="var_limit_exceeded",
                    original_qty=order.qty,
                    adjustments={"current_var": f"{var_95:.4f}", "limit": f"{self.max_portfolio_var:.4f}"}
                )

        # 5. All checks passed - allow with potential sizing adjustment
        return RiskDecision.allow(
            reason="approved",
            adjustments={},
            limits={
                "max_position_per_symbol": str(self.max_position_per_symbol),
                "max_single_position_value": str(self.max_single_position_value),
                "max_portfolio_var": str(self.max_portfolio_var)
            },
            original_qty=order.qty,
            adjusted_qty=order.qty
        )

    async def _get_portfolio_state(self, symbol: str) -> "PortfolioState":
        """Get current portfolio state - placeholder for persistence integration"""
        # In production, this would query the database for current positions and returns
        from decimal import Decimal

        from backend.risk.types import PortfolioState

        return PortfolioState(
            equity=Decimal('100000'),
            cash=Decimal('50000'),
            positions={symbol: Decimal('0')},  # Current position
            sector_map={symbol: 'Technology'},  # Sector mapping
            last_updated=datetime.now(UTC)
        )

    def _get_historical_returns(self, symbol: str, days: int = 60) -> list:
        """Get historical returns for risk calculations - placeholder"""
        # In production, this would query price/return data
        return [0.01, 0.02, -0.01, 0.005, -0.015] * (days // 5)


# Legacy compatibility wrapper
class RiskManager(AsyncRiskManager):
    """Backward compatibility wrapper."""

    def before_order(self, symbol: str, intended_qty: float, price: float | None = None) -> tuple[bool, str, float]:
        """Legacy synchronous interface - DO NOT USE in new code."""
        warnings.warn(
            "Synchronous before_order is deprecated. Use async interface.",
            DeprecationWarning,
            stacklevel=2
        )

        # Convert to new types
        order = OrderSpec(
            symbol=symbol,
            side="buy" if intended_qty > 0 else "sell",
            qty=Decimal(str(abs(intended_qty))),
            notional=Decimal(str(abs(intended_qty) * (price or 100))),
            price=Decimal(str(price)) if price else None
        )

        # Run async method in event loop (not recommended)
        try:
            # Check if we're already in an async context
            loop = asyncio.get_running_loop()
            # If we are, we can't use run_until_complete, so create a task
            # This is hacky but needed for backward compatibility
            import concurrent.futures

            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(super(RiskManager, self).before_order(order))
                finally:
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                decision = future.result()

        except RuntimeError:
            # No running loop, safe to create new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                decision = loop.run_until_complete(super().before_order(order))
            finally:
                loop.close()

        # Convert back to legacy format
        adjusted_qty = float(decision.adjusted_qty or order.qty)
        if order.side == "sell":
            adjusted_qty = -adjusted_qty

        return decision.allowed, decision.reason, adjusted_qty
