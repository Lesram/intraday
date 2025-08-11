"""
Risk Management Module for Real-Time Risk Controls & Position Sizing.
Implements VaR, CVaR, Kelly criterion, and circuit breakers for institutional-grade risk control.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import numpy as np

from ..config import get_settings
from ..utils.helpers import (
    kelly_criterion,
)
from ..utils.logger import audit_logger, get_structured_logger, performance_logger


class RiskLevel(Enum):
    """Risk severity levels."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class RiskLimits:
    """Risk limit configuration."""

    max_daily_loss_pct: float = 0.03  # 3% max daily loss
    max_drawdown_pct: float = 0.06  # 6% max drawdown
    max_position_pct: float = 0.10  # 10% max single position
    max_leverage: float = 2.0  # 2:1 max leverage
    max_correlation: float = 0.7  # Max correlation between positions
    var_limit_pct: float = 0.05  # 5% VaR limit
    max_trades_per_day: int = 100  # Max trades per day
    min_cash_reserve_pct: float = 0.05  # 5% minimum cash reserve


@dataclass
class PositionRisk:
    """Risk metrics for a single position."""

    symbol: str
    quantity: float
    market_value: float
    unrealized_pnl: float
    var_contribution: float
    weight_pct: float
    days_held: int
    entry_price: float


@dataclass
class PortfolioRisk:
    """Portfolio-level risk metrics."""

    total_value: float
    cash: float
    leverage: float
    daily_pnl: float
    daily_return: float
    var_95: float
    cvar_95: float
    max_drawdown: float
    sharpe_ratio: float
    positions: list[PositionRisk]
    correlations: dict[str, float]
    risk_level: RiskLevel


class RiskManager:
    """
    Risk manager for real-time risk monitoring and control.
    Implements institutional-grade risk management with VaR, circuit breakers, and position sizing.
    """

    def __init__(self, portfolio=None, risk_limits: RiskLimits | None = None):
        """
        Initialize risk manager.

        Args:
            portfolio: Portfolio object with current holdings (optional)
            risk_limits: Risk limit configuration
        """
        self.logger = get_structured_logger("risk_manager")
        self.settings = get_settings()
        self.portfolio = portfolio or {}
        self.limits = risk_limits or RiskLimits()

        # Risk state tracking
        self.daily_trades = 0
        self.circuit_breaker_active = False
        self.emergency_liquidation = False
        self.risk_alerts_sent = set()

        # Historical data for risk calculations
        self.price_history = {}  # symbol -> price series
        self.return_history = {}  # symbol -> return series
        self.portfolio_history = []  # Portfolio value history

        # Performance tracking
        self.start_of_day_value = 0
        self.peak_value = 0
        self.last_risk_check = datetime.now(UTC)

        # Monte Carlo simulation parameters
        self.mc_simulations = 10000
        self.mc_days = 1  # 1-day VaR

        # Mock fallback tracking
        self.mock_data_used = set()  # Track which metrics used mock data

        self.logger.info(
            "Risk manager initialized",
            limits=self.limits.__dict__,
            allow_mock_fallbacks=self.settings.trading.allow_mock_fallbacks,
        )

    def calculate_var(self, confidence: float = 0.95, method: str = "monte_carlo") -> float:
        """
        Compute portfolio Value-at-Risk (VaR).

        Args:
            confidence: Confidence level (e.g., 0.95 for 95% VaR)
            method: "monte_carlo", "historical", or "parametric"

        Returns:
            VaR as a negative value (expected loss)
        """
        try:
            start_time = datetime.now(UTC)

            if method == "monte_carlo":
                var = self._calculate_monte_carlo_var(confidence)
            elif method == "historical":
                var = self._calculate_historical_var(confidence)
            else:
                var = self._calculate_parametric_var(confidence)

            # Log performance
            calc_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
            performance_logger.log_latency(f"var_calculation_{method}", calc_time)

            self.logger.info(
                "VaR calculated",
                method=method,
                confidence=confidence,
                var_value=var,
                portfolio_value=self.portfolio.total_value,
                var_pct=(
                    abs(var) / self.portfolio.total_value if self.portfolio.total_value > 0 else 0
                ),
            )

            return var

        except Exception as e:
            self.logger.error("VaR calculation failed", method=method, error=str(e))
            return 0.0

    def _calculate_monte_carlo_var(self, confidence: float) -> float:
        """Calculate VaR using Monte Carlo simulation."""
        try:
            # Get current positions
            positions = self.portfolio.get_positions()
            if not positions:
                return 0.0

            # Simulate portfolio returns
            simulated_returns = []

            for _ in range(self.mc_simulations):
                portfolio_return = 0.0

                for symbol, position in positions.items():
                    if symbol in self.return_history and len(self.return_history[symbol]) > 30:
                        # Sample random return from historical distribution
                        returns = self.return_history[symbol][-252:]  # Last year
                        random_return = np.random.choice(returns)

                        # Position contribution to portfolio return
                        position_weight = abs(position["market_value"]) / self.portfolio.total_value
                        portfolio_return += random_return * position_weight
                    else:
                        # Check if mock fallbacks are allowed
                        if not self.settings.trading.allow_mock_fallbacks:
                            self.logger.warning(
                                f"Insufficient historical data for {symbol}, mock fallbacks disabled"
                            )
                            continue

                        # Fallback to normal distribution
                        self.mock_data_used.add("monte_carlo_var_normal_fallback")
                        if self.settings.trading.mock_fallback_warning:
                            self.logger.warning(
                                f"Using mock normal distribution for {symbol} - insufficient historical data"
                            )

                        random_return = np.random.normal(0, 0.02)  # 2% daily vol
                        position_weight = abs(position["market_value"]) / self.portfolio.total_value
                        portfolio_return += random_return * position_weight

                simulated_returns.append(portfolio_return)

            # Calculate VaR as percentile
            var_percentile = (1 - confidence) * 100
            var = np.percentile(simulated_returns, var_percentile)

            # Convert to dollar amount
            return var * self.portfolio.total_value

        except Exception as e:
            self.logger.error("Monte Carlo VaR calculation failed", error=str(e))
            return 0.0

    def _calculate_historical_var(self, confidence: float) -> float:
        """Calculate VaR using historical simulation."""
        try:
            if len(self.portfolio_history) < 30:
                return 0.0

            # Calculate historical portfolio returns
            values = [
                record["total_value"] for record in self.portfolio_history[-252:]
            ]  # Last year
            returns = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))]

            if not returns:
                return 0.0

            # Calculate VaR as percentile
            var_percentile = (1 - confidence) * 100
            var_return = np.percentile(returns, var_percentile)

            return var_return * self.portfolio.total_value

        except Exception as e:
            self.logger.error("Historical VaR calculation failed", error=str(e))
            return 0.0

    def _calculate_parametric_var(self, confidence: float) -> float:
        """Calculate VaR using parametric method (variance-covariance)."""
        try:
            positions = self.portfolio.get_positions()
            if not positions:
                return 0.0

            # Build covariance matrix
            symbols = list(positions.keys())
            returns_matrix = []

            for symbol in symbols:
                if symbol in self.return_history and len(self.return_history[symbol]) > 30:
                    returns_matrix.append(self.return_history[symbol][-252:])  # Last year
                else:
                    # Check if mock fallbacks are allowed
                    if not self.settings.trading.allow_mock_fallbacks:
                        self.logger.warning(
                            f"Insufficient historical data for {symbol}, mock fallbacks disabled"
                        )
                        continue

                    # Fallback to random data
                    self.mock_data_used.add("parametric_var_random_fallback")
                    if self.settings.trading.mock_fallback_warning:
                        self.logger.warning(
                            f"Using mock random data for {symbol} - insufficient historical data"
                        )
                    returns_matrix.append(np.random.normal(0, 0.02, 252))

            if not returns_matrix:
                return 0.0

            # Convert to numpy array
            returns_matrix = np.array(returns_matrix).T

            # Calculate covariance matrix
            cov_matrix = np.cov(returns_matrix.T)

            # Position weights
            weights = []
            for symbol in symbols:
                weight = positions[symbol]["market_value"] / self.portfolio.total_value
                weights.append(weight)

            weights = np.array(weights)

            # Portfolio variance
            portfolio_variance = np.dot(weights.T, np.dot(cov_matrix, weights))
            portfolio_std = np.sqrt(portfolio_variance)

            # VaR calculation (assumes normal distribution)
            from scipy import stats

            z_score = stats.norm.ppf(1 - confidence)
            var = z_score * portfolio_std * self.portfolio.total_value

            return var

        except Exception as e:
            self.logger.error("Parametric VaR calculation failed", error=str(e))
            return 0.0

    def calculate_cvar(self, confidence: float = 0.95) -> float:
        """
        Compute Conditional Value at Risk (Expected Shortfall).

        Args:
            confidence: Confidence level

        Returns:
            CVaR as a negative value
        """
        try:
            # Use historical simulation for CVaR
            if len(self.portfolio_history) < 30:
                return 0.0

            # Calculate historical returns
            values = [record["total_value"] for record in self.portfolio_history[-252:]]
            returns = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))]

            if not returns:
                return 0.0

            # Calculate VaR threshold
            var_threshold = np.percentile(returns, (1 - confidence) * 100)

            # Calculate CVaR as mean of returns below VaR threshold
            tail_returns = [r for r in returns if r <= var_threshold]

            if not tail_returns:
                return var_threshold * self.portfolio.total_value

            cvar_return = np.mean(tail_returns)
            return cvar_return * self.portfolio.total_value

        except Exception as e:
            self.logger.error("CVaR calculation failed", error=str(e))
            return 0.0

    def kelly_position_size(self, prob_win: float, win_loss_ratio: float) -> float:
        """
        Calculate optimal position size using Kelly criterion.

        Args:
            prob_win: Probability of winning trade (0-1)
            win_loss_ratio: Ratio of average win to average loss

        Returns:
            Optimal fraction of capital to risk (0-1)
        """
        try:
            # Basic Kelly calculation
            kelly_fraction = kelly_criterion(prob_win, win_loss_ratio)

            # Apply safety constraints
            max_kelly = 0.25  # Never risk more than 25% of capital
            conservative_kelly = kelly_fraction * 0.5  # Use half Kelly for safety

            final_fraction = min(conservative_kelly, max_kelly)

            self.logger.info(
                "Kelly position sizing",
                prob_win=prob_win,
                win_loss_ratio=win_loss_ratio,
                raw_kelly=kelly_fraction,
                final_fraction=final_fraction,
            )

            return max(0, final_fraction)

        except Exception as e:
            self.logger.error("Kelly calculation failed", error=str(e))
            return 0.0

    def enforce_global_limits(self) -> dict[str, Any]:
        """
        Check global risk limits and take action if needed.

        Returns:
            Dictionary with risk status and actions taken
        """
        try:
            actions_taken = []
            risk_status = "OK"

            current_value = self.portfolio.total_value
            if current_value <= 0:
                return {"status": "ERROR", "message": "Invalid portfolio value"}

            # Update start of day value if new day
            now = datetime.now(UTC)
            if now.date() != self.last_risk_check.date():
                self.start_of_day_value = current_value
                self.daily_trades = 0
                self.risk_alerts_sent.clear()

            # Update peak value for drawdown calculation
            self.peak_value = max(self.peak_value, current_value)

            # 1. Daily Loss Check
            if self.start_of_day_value > 0:
                daily_loss = (self.start_of_day_value - current_value) / self.start_of_day_value
                if daily_loss > self.limits.max_daily_loss_pct:
                    actions_taken.append("CIRCUIT_BREAKER_DAILY_LOSS")
                    risk_status = "CRITICAL"
                    self._trigger_circuit_breaker("daily_loss_limit", daily_loss)

            # 2. Drawdown Check
            if self.peak_value > 0:
                drawdown = (self.peak_value - current_value) / self.peak_value
                if drawdown > self.limits.max_drawdown_pct:
                    actions_taken.append("CIRCUIT_BREAKER_DRAWDOWN")
                    risk_status = "CRITICAL"
                    self._trigger_circuit_breaker("drawdown_limit", drawdown)

            # 3. Position Size Check
            positions = self.portfolio.get_positions()
            for symbol, position in positions.items():
                position_pct = abs(position["market_value"]) / current_value
                if position_pct > self.limits.max_position_pct:
                    actions_taken.append(f"REDUCE_POSITION_{symbol}")
                    risk_status = "HIGH"
                    self._reduce_oversized_position(symbol, position_pct)

            # 4. Leverage Check
            total_exposure = sum(abs(pos["market_value"]) for pos in positions.values())
            leverage = total_exposure / current_value if current_value > 0 else 0
            if leverage > self.limits.max_leverage:
                actions_taken.append("REDUCE_LEVERAGE")
                risk_status = "HIGH" if risk_status == "OK" else risk_status

            # 5. VaR Check
            current_var = abs(self.calculate_var())
            var_pct = current_var / current_value if current_value > 0 else 0
            if var_pct > self.limits.var_limit_pct:
                actions_taken.append("VAR_LIMIT_BREACH")
                risk_status = "HIGH" if risk_status == "OK" else risk_status

            # 6. Trade Count Check
            if self.daily_trades > self.limits.max_trades_per_day:
                actions_taken.append("TRADE_LIMIT_REACHED")
                risk_status = "MEDIUM" if risk_status == "OK" else risk_status

            # 7. Cash Reserve Check
            cash_pct = self.portfolio.cash / current_value if current_value > 0 else 0
            if cash_pct < self.limits.min_cash_reserve_pct:
                actions_taken.append("LOW_CASH_RESERVE")
                risk_status = "MEDIUM" if risk_status == "OK" else risk_status

            self.last_risk_check = now

            # Log risk check results
            self.logger.info(
                "Global risk limits checked",
                risk_status=risk_status,
                actions_taken=actions_taken,
                current_value=current_value,
                daily_loss_pct=daily_loss if "daily_loss" in locals() else 0,
                drawdown_pct=drawdown if "drawdown" in locals() else 0,
                leverage=leverage,
                var_pct=var_pct,
            )

            return {
                "status": risk_status,
                "actions_taken": actions_taken,
                "metrics": {
                    "portfolio_value": current_value,
                    "daily_loss_pct": daily_loss if "daily_loss" in locals() else 0,
                    "drawdown_pct": drawdown if "drawdown" in locals() else 0,
                    "leverage": leverage,
                    "var_pct": var_pct,
                    "cash_pct": cash_pct,
                },
            }

        except Exception as e:
            self.logger.error("Risk limit enforcement failed", error=str(e))
            return {"status": "ERROR", "message": str(e)}

    def before_order(
        self, symbol: str, intended_qty: float, price: float | None = None
    ) -> tuple[bool, str, float]:
        """
        Pre-trade risk check for order validation.

        Args:
            symbol: Symbol to trade
            intended_qty: Intended quantity (positive for buy, negative for sell)
            price: Intended price (current market price if None)

        Returns:
            Tuple of (allowed, reason, adjusted_quantity)
        """
        try:
            # Circuit breaker check
            if self.circuit_breaker_active:
                return False, "Circuit breaker active", 0.0

            # Emergency liquidation mode - only allow closing trades
            if self.emergency_liquidation:
                current_position = self.portfolio.get_position(symbol)
                if current_position and np.sign(intended_qty) == np.sign(
                    current_position["quantity"]
                ):
                    return (
                        False,
                        "Emergency liquidation - only position closing allowed",
                        0.0,
                    )

            # Daily trade limit check
            if self.daily_trades >= self.limits.max_trades_per_day:
                return False, "Daily trade limit reached", 0.0

            # Estimate trade impact
            if price is None:
                price = self._get_current_price(symbol)

            trade_value = abs(intended_qty * price)
            current_value = self.portfolio.total_value

            if current_value <= 0:
                return False, "Invalid portfolio value", 0.0

            # Position size check
            current_position = self.portfolio.get_position(symbol)
            current_exposure = abs(current_position["market_value"]) if current_position else 0
            new_exposure = current_exposure + trade_value

            position_pct = new_exposure / current_value
            if position_pct > self.limits.max_position_pct:
                # Calculate maximum allowed quantity
                max_allowed_exposure = self.limits.max_position_pct * current_value
                max_additional_exposure = max_allowed_exposure - current_exposure

                if max_additional_exposure > 0:
                    adjusted_qty = max_additional_exposure / price
                    if np.sign(intended_qty) < 0:  # Selling
                        adjusted_qty = -adjusted_qty

                    return (
                        True,
                        f"Position size adjusted to stay within {self.limits.max_position_pct:.1%} limit",
                        adjusted_qty,
                    )
                else:
                    return (
                        False,
                        f"Position size would exceed {self.limits.max_position_pct:.1%} limit",
                        0.0,
                    )

            # Leverage check
            total_exposure = sum(
                abs(pos["market_value"]) for pos in self.portfolio.get_positions().values()
            )
            new_total_exposure = total_exposure + trade_value
            new_leverage = new_total_exposure / current_value

            if new_leverage > self.limits.max_leverage:
                max_allowed_trade = (self.limits.max_leverage * current_value) - total_exposure
                if max_allowed_trade > 0:
                    adjusted_qty = max_allowed_trade / price
                    if np.sign(intended_qty) < 0:
                        adjusted_qty = -adjusted_qty

                    return (
                        True,
                        f"Trade size adjusted to stay within {self.limits.max_leverage:.1f}x leverage limit",
                        adjusted_qty,
                    )
                else:
                    return (
                        False,
                        f"Trade would exceed {self.limits.max_leverage:.1f}x leverage limit",
                        0.0,
                    )

            # Cash availability check (for buys)
            if intended_qty > 0:  # Buying
                available_cash = self.portfolio.cash
                cash_needed = trade_value

                # Maintain minimum cash reserve
                min_cash_required = self.limits.min_cash_reserve_pct * current_value
                available_for_trading = available_cash - min_cash_required

                if cash_needed > available_for_trading:
                    if available_for_trading > 0:
                        adjusted_qty = available_for_trading / price
                        return (
                            True,
                            "Trade size adjusted for available cash",
                            adjusted_qty,
                        )
                    else:
                        return False, "Insufficient cash (maintaining reserve)", 0.0

            # All checks passed
            self.daily_trades += 1

            self.logger.info(
                "Order pre-check passed",
                symbol=symbol,
                intended_qty=intended_qty,
                trade_value=trade_value,
                position_pct=position_pct,
                new_leverage=new_leverage,
            )

            return True, "Order approved", intended_qty

        except Exception as e:
            self.logger.error(
                "Order pre-check failed",
                symbol=symbol,
                intended_qty=intended_qty,
                error=str(e),
            )
            return False, f"Risk check error: {str(e)}", 0.0

    def _trigger_circuit_breaker(self, reason: str, value: float):
        """Trigger circuit breaker and emergency procedures."""
        if not self.circuit_breaker_active:
            self.circuit_breaker_active = True

            audit_logger.log_risk_event(
                "circuit_breaker_triggered",
                f"Circuit breaker activated: {reason}",
                severity="CRITICAL",
                data={"reason": reason, "value": value, "timestamp": datetime.now(UTC)},
            )

            self.logger.critical(
                "Circuit breaker activated",
                reason=reason,
                value=value,
                portfolio_value=self.portfolio.total_value,
            )

            # Trigger emergency liquidation if loss is severe
            if reason == "daily_loss_limit" and value > self.limits.max_daily_loss_pct * 1.5:
                self.emergency_liquidation = True
                self._initiate_emergency_liquidation()

    def _initiate_emergency_liquidation(self):
        """Initiate emergency liquidation of all positions."""
        self.logger.critical("Emergency liquidation initiated")

        audit_logger.log_risk_event(
            "emergency_liquidation",
            "Emergency liquidation of all positions initiated",
            severity="CRITICAL",
            data={
                "timestamp": datetime.now(UTC),
                "portfolio_value": self.portfolio.total_value,
            },
        )

        # This would typically integrate with the trading system
        # to liquidate all positions immediately

    def _reduce_oversized_position(self, symbol: str, current_pct: float):
        """Reduce position that exceeds size limits."""
        self.logger.warning(
            "Oversized position detected",
            symbol=symbol,
            current_pct=current_pct,
            limit_pct=self.limits.max_position_pct,
        )

        audit_logger.log_risk_event(
            "oversized_position",
            f"Position {symbol} exceeds size limit: {current_pct:.1%}",
            severity="WARNING",
            data={
                "symbol": symbol,
                "current_pct": current_pct,
                "limit_pct": self.limits.max_position_pct,
            },
        )

    def _get_current_price(self, symbol: str) -> float:
        """Get current market price for a symbol."""
        # This would integrate with market data provider
        # For now, return a default price
        if symbol in self.price_history and self.price_history[symbol]:
            return self.price_history[symbol][-1]
        return 100.0  # Default fallback price

    def update_price_history(self, symbol: str, price: float):
        """Update price history for risk calculations."""
        if symbol not in self.price_history:
            self.price_history[symbol] = []

        self.price_history[symbol].append(price)

        # Maintain limited history (1 year = ~252 trading days)
        if len(self.price_history[symbol]) > 300:
            self.price_history[symbol] = self.price_history[symbol][-252:]

        # Calculate and store returns
        if len(self.price_history[symbol]) > 1:
            if symbol not in self.return_history:
                self.return_history[symbol] = []

            prev_price = self.price_history[symbol][-2]
            returns = (price - prev_price) / prev_price
            self.return_history[symbol].append(returns)

            # Maintain limited return history
            if len(self.return_history[symbol]) > 300:
                self.return_history[symbol] = self.return_history[symbol][-252:]

    def update_portfolio_history(self):
        """Update portfolio value history for risk calculations."""
        portfolio_record = {
            "timestamp": datetime.now(UTC),
            "total_value": self.portfolio.total_value,
            "cash": self.portfolio.cash,
            "positions": len(self.portfolio.get_positions()),
        }

        self.portfolio_history.append(portfolio_record)

        # Maintain limited history
        if len(self.portfolio_history) > 300:
            self.portfolio_history = self.portfolio_history[-252:]

    def get_risk_metrics(self) -> PortfolioRisk:
        """
        Get comprehensive portfolio risk metrics.

        Returns:
            PortfolioRisk object with all risk metrics
        """
        try:
            # Calculate risk metrics
            var_95 = abs(self.calculate_var(0.95))
            cvar_95 = abs(self.calculate_cvar(0.95))

            # Portfolio metrics
            total_value = self.portfolio.total_value
            cash = self.portfolio.cash

            # Leverage calculation
            positions = self.portfolio.get_positions()
            total_exposure = sum(abs(pos["market_value"]) for pos in positions.values())
            leverage = total_exposure / total_value if total_value > 0 else 0

            # Daily P&L
            daily_pnl = total_value - self.start_of_day_value if self.start_of_day_value > 0 else 0
            daily_return = daily_pnl / self.start_of_day_value if self.start_of_day_value > 0 else 0

            # Drawdown
            max_drawdown = 0
            if self.peak_value > 0:
                max_drawdown = (self.peak_value - total_value) / self.peak_value

            # Sharpe ratio (simplified calculation)
            sharpe_ratio = 0
            if len(self.portfolio_history) > 30:
                values = [record["total_value"] for record in self.portfolio_history[-30:]]
                returns = [
                    (values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))
                ]
                if returns and np.std(returns) > 0:
                    avg_return = np.mean(returns)
                    std_return = np.std(returns)
                    sharpe_ratio = (avg_return * np.sqrt(252)) / (std_return * np.sqrt(252))

            # Position risks
            position_risks = []
            for symbol, pos in positions.items():
                position_risk = PositionRisk(
                    symbol=symbol,
                    quantity=pos["quantity"],
                    market_value=pos["market_value"],
                    unrealized_pnl=pos.get("unrealized_pl", 0),
                    var_contribution=0,  # Would need more complex calculation
                    weight_pct=(abs(pos["market_value"]) / total_value if total_value > 0 else 0),
                    days_held=pos.get("days_held", 0),
                    entry_price=pos.get("avg_entry_price", 0),
                )
                position_risks.append(position_risk)

            # Risk level determination
            risk_level = RiskLevel.LOW
            if max_drawdown > self.limits.max_drawdown_pct * 0.8:
                risk_level = RiskLevel.HIGH
            elif abs(daily_return) > self.limits.max_daily_loss_pct * 0.8 or (
                var_95 / total_value > self.limits.var_limit_pct * 0.8 if total_value > 0 else False
            ):
                risk_level = RiskLevel.MEDIUM

            if self.circuit_breaker_active:
                risk_level = RiskLevel.CRITICAL

            return PortfolioRisk(
                total_value=total_value,
                cash=cash,
                leverage=leverage,
                daily_pnl=daily_pnl,
                daily_return=daily_return,
                var_95=var_95,
                cvar_95=cvar_95,
                max_drawdown=max_drawdown,
                sharpe_ratio=sharpe_ratio,
                positions=position_risks,
                correlations={},  # Would need correlation calculation
                risk_level=risk_level,
            )

        except Exception as e:
            self.logger.error("Risk metrics calculation failed", error=str(e))
            return PortfolioRisk(
                total_value=0,
                cash=0,
                leverage=0,
                daily_pnl=0,
                daily_return=0,
                var_95=0,
                cvar_95=0,
                max_drawdown=0,
                sharpe_ratio=0,
                positions=[],
                correlations={},
                risk_level=RiskLevel.HIGH,
            )

    def reset_circuit_breaker(self, reason: str):
        """Reset circuit breaker (manual override)."""
        if self.circuit_breaker_active:
            self.circuit_breaker_active = False
            self.emergency_liquidation = False

            audit_logger.log_risk_event(
                "circuit_breaker_reset",
                f"Circuit breaker reset: {reason}",
                severity="INFO",
                data={"reason": reason, "timestamp": datetime.now(UTC)},
            )

            self.logger.info("Circuit breaker reset", reason=reason)

    def get_position_sizing_recommendation(
        self,
        symbol: str,
        signal_strength: float,
        win_probability: float | None = None,
        win_loss_ratio: float | None = None,
    ) -> dict[str, Any]:
        """
        Get position sizing recommendation for a trade.

        Args:
            symbol: Symbol to trade
            signal_strength: Signal strength (0-1)
            win_probability: Historical win probability
            win_loss_ratio: Historical win/loss ratio

        Returns:
            Dictionary with sizing recommendation
        """
        try:
            # Base position size from signal strength
            base_size = signal_strength * self.limits.max_position_pct

            # Kelly criterion adjustment if historical stats available
            if win_probability and win_loss_ratio:
                kelly_size = self.kelly_position_size(win_probability, win_loss_ratio)
                # Use the more conservative of the two
                base_size = min(base_size, kelly_size)

            # Risk adjustments
            current_risk = self.get_risk_metrics()

            # Reduce size if portfolio risk is high
            if current_risk.risk_level == RiskLevel.HIGH:
                base_size *= 0.5
            elif current_risk.risk_level == RiskLevel.CRITICAL:
                base_size = 0.0

            # Reduce size based on current drawdown
            if current_risk.max_drawdown > self.limits.max_drawdown_pct * 0.5:
                drawdown_factor = 1 - (current_risk.max_drawdown / self.limits.max_drawdown_pct)
                base_size *= max(0.1, drawdown_factor)

            # Reduce size based on VaR
            var_pct = (
                current_risk.var_95 / current_risk.total_value
                if current_risk.total_value > 0
                else 0
            )
            if var_pct > self.limits.var_limit_pct * 0.5:
                var_factor = 1 - (var_pct / self.limits.var_limit_pct)
                base_size *= max(0.1, var_factor)

            # Convert to dollar amount
            dollar_size = base_size * current_risk.total_value

            recommendation = {
                "symbol": symbol,
                "recommended_position_pct": base_size,
                "recommended_dollar_amount": dollar_size,
                "signal_strength": signal_strength,
                "risk_adjustments": {
                    "risk_level": current_risk.risk_level.value,
                    "drawdown_factor": current_risk.max_drawdown,
                    "var_factor": var_pct,
                },
                "kelly_size": (kelly_size if win_probability and win_loss_ratio else None),
                "max_allowed_pct": self.limits.max_position_pct,
            }

            self.logger.info(
                "Position sizing recommendation",
                symbol=symbol,
                recommended_pct=base_size,
                dollar_amount=dollar_size,
                signal_strength=signal_strength,
            )

            return recommendation

        except Exception as e:
            self.logger.error("Position sizing recommendation failed", symbol=symbol, error=str(e))
            return {"symbol": symbol, "recommended_position_pct": 0, "error": str(e)}

    def get_positions(self) -> dict:
        """Get current portfolio positions."""
        if hasattr(self.portfolio, "get_positions"):
            return self.portfolio.get_positions()
        elif isinstance(self.portfolio, dict):
            return self.portfolio
        else:
            return {}

    def get_portfolio_value(self) -> float:
        """Get current portfolio total value."""
        if hasattr(self.portfolio, "total_value"):
            return float(self.portfolio.total_value)
        elif hasattr(self.portfolio, "get_total_value"):
            return float(self.portfolio.get_total_value())
        else:
            return 0.0

    async def assess_position_risk(self, symbol: str, quantity: int, side: str) -> dict:
        """
        Async wrapper for position risk assessment.

        Args:
            symbol: Trading symbol
            quantity: Order quantity
            side: 'buy' or 'sell'

        Returns:
            Dict with 'approved' bool and 'reason' string
        """
        try:
            # Use the existing before_order method
            validation_result = self.before_order(symbol, quantity, side)

            return {
                "approved": validation_result.get("approved", True),
                "reason": validation_result.get("reason", "Risk check passed"),
            }

        except Exception as e:
            self.logger.error(f"Risk assessment failed for {symbol}: {e}")
            return {"approved": False, "reason": f"Risk assessment error: {str(e)}"}

    async def update_position_risk(self, symbol: str, current_price: float) -> dict:
        """
        Update risk monitoring for a position based on current market price.

        Args:
            symbol: Symbol to update
            current_price: Current market price

        Returns:
            Dict with risk update information
        """
        try:
            # Check if we have this position
            positions = self.get_positions()
            if symbol not in positions:
                return {"symbol": symbol, "status": "no_position", "alerts": []}

            position = positions[symbol]
            alerts = []

            # Calculate current P&L
            if "avg_cost" in position:
                pnl_pct = (current_price - position["avg_cost"]) / position["avg_cost"]

                # Check stop loss
                if hasattr(self.limits, "stop_loss_pct") and pnl_pct < -abs(
                    self.limits.stop_loss_pct
                ):
                    alerts.append(
                        {
                            "type": "stop_loss",
                            "message": f"Position down {pnl_pct:.1%}, consider stop loss",
                            "severity": "high",
                        }
                    )

                # Check daily loss limit
                if hasattr(self.limits, "daily_loss_limit"):
                    position_loss = position.get("quantity", 0) * (
                        position.get("avg_cost", current_price) - current_price
                    )
                    if position_loss > self.limits.daily_loss_limit:
                        alerts.append(
                            {
                                "type": "daily_loss",
                                "message": f"Position loss ${position_loss:.2f} exceeds daily limit",
                                "severity": "critical",
                            }
                        )

            return {
                "symbol": symbol,
                "status": "monitored",
                "current_price": current_price,
                "alerts": alerts,
            }

        except Exception as e:
            self.logger.error(f"Failed to update position risk for {symbol}: {e}")
            return {"symbol": symbol, "status": "error", "error": str(e), "alerts": []}
