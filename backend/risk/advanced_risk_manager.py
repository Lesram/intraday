"""
Advanced Risk Manager for Hedge Fund Grade Trading Platform
=========================================================

Real-time portfolio risk monitoring and management with:
- Dynamic position sizing based on volatility
- Value at Risk (VaR) calculations 
- Drawdown protection mechanisms
- Correlation analysis and concentration limits
- Market regime detection and adaptation
- Automated risk adjustments
- SLO integration for operational risk

Created: 2025-09-30
Author: Production Trading System
"""

import asyncio
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import math
from concurrent.futures import ThreadPoolExecutor
import warnings

# Suppress numpy warnings for cleaner production logs
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Try importing external dependencies with graceful fallback
try:
    from scipy import stats
    from scipy.optimize import minimize
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logging.warning("SciPy not available - using fallback calculations")

try:
    from backend.monitoring.slo_monitor import SLOMonitor
    SLO_AVAILABLE = True
except ImportError:
    SLO_AVAILABLE = False
    logging.warning("SLO Monitor not available - running without SLO integration")

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level classifications"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MarketRegime(Enum):
    """Market regime classifications"""
    CALM = "calm"
    VOLATILE = "volatile"
    TRENDING = "trending"
    CRISIS = "crisis"


@dataclass
class RiskMetrics:
    """Container for portfolio risk metrics"""
    portfolio_var_1d: float = 0.0
    portfolio_var_5d: float = 0.0
    portfolio_var_10d: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    beta: float = 1.0
    alpha: float = 0.0
    tracking_error: float = 0.0
    information_ratio: float = 0.0
    concentration_risk: float = 0.0
    sector_concentration: Dict[str, float] = field(default_factory=dict)
    correlation_risk: float = 0.0
    leverage: float = 1.0
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    long_exposure: float = 0.0
    short_exposure: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW
    market_regime: MarketRegime = MarketRegime.CALM
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Position:
    """Individual position representation"""
    symbol: str
    quantity: float
    price: float
    market_value: float
    weight: float
    sector: str = "Unknown"
    beta: float = 1.0
    volatility: float = 0.0
    correlation_to_portfolio: float = 0.0


@dataclass
class RiskLimits:
    """Risk management limits and thresholds"""
    max_position_size: float = 0.1  # 10% max per position
    max_sector_concentration: float = 0.25  # 25% max per sector
    max_correlation: float = 0.8  # Maximum correlation between positions
    max_portfolio_var: float = 0.02  # 2% daily VaR limit
    max_drawdown: float = 0.05  # 5% maximum drawdown
    max_leverage: float = 2.0  # 2x maximum leverage
    stop_loss_threshold: float = 0.03  # 3% stop loss
    profit_target: float = 0.05  # 5% profit target
    min_liquidity: float = 0.1  # 10% minimum cash/liquidity
    var_confidence_level: float = 0.95  # 95% VaR confidence


class AdvancedRiskManager:
    """
    Advanced Risk Management System for Production Trading
    
    Features:
    - Real-time risk monitoring and alerts
    - Dynamic position sizing based on market conditions
    - Multi-timeframe VaR calculations
    - Drawdown protection with automatic position reduction
    - Correlation analysis and concentration monitoring
    - Market regime detection and adaptive risk limits
    - Automated rebalancing recommendations
    - Integration with SLO monitoring system
    """
    
    def __init__(self, risk_limits: Optional[RiskLimits] = None, enable_slo: bool = True):
        """Initialize the Advanced Risk Manager"""
        self.risk_limits = risk_limits or RiskLimits()
        self.positions: Dict[str, Position] = {}
        self.portfolio_value = 0.0
        self.cash_balance = 0.0
        self.price_history: Dict[str, List[float]] = {}
        self.returns_history: Dict[str, List[float]] = {}
        self.portfolio_returns: List[float] = []
        self.risk_metrics = RiskMetrics()
        self.alerts: List[Dict[str, Any]] = []
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # SLO Integration
        if enable_slo and SLO_AVAILABLE:
            try:
                self.slo_monitor = SLOMonitor()
                logger.info("SLO monitoring enabled for risk management")
            except Exception as e:
                logger.warning(f"Failed to initialize SLO monitor: {e}")
                self.slo_monitor = None
        else:
            self.slo_monitor = None
        
        logger.info("Advanced Risk Manager initialized with production-grade controls")
    
    async def update_positions(self, positions_data: Dict[str, Dict]) -> None:
        """Update portfolio positions and trigger risk calculations"""
        start_time = datetime.utcnow()
        
        try:
            # Clear existing positions
            self.positions.clear()
            total_value = 0.0
            
            # Process each position
            for symbol, pos_data in positions_data.items():
                position = Position(
                    symbol=symbol,
                    quantity=pos_data.get('quantity', 0),
                    price=pos_data.get('price', 0),
                    market_value=pos_data.get('market_value', 0),
                    weight=0.0,  # Will be calculated after total value
                    sector=pos_data.get('sector', 'Unknown'),
                    beta=pos_data.get('beta', 1.0),
                    volatility=pos_data.get('volatility', 0.0)
                )
                
                self.positions[symbol] = position
                total_value += abs(position.market_value)
            
            # Update portfolio value and calculate weights
            self.portfolio_value = total_value
            for position in self.positions.values():
                if total_value > 0:
                    position.weight = abs(position.market_value) / total_value
            
            # Update price and returns history
            await self._update_price_history()
            
            # Calculate comprehensive risk metrics
            await self._calculate_risk_metrics()
            
            # Check risk limits and generate alerts
            await self._check_risk_limits()
            
            # Record SLO metrics
            if self.slo_monitor:
                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                await self._record_slo_metrics("position_update", execution_time, success=True)
            
            logger.info(f"Updated {len(self.positions)} positions, portfolio value: ${self.portfolio_value:,.2f}")
            
        except Exception as e:
            logger.error(f"Error updating positions: {e}")
            if self.slo_monitor:
                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                await self._record_slo_metrics("position_update", execution_time, success=False)
            raise
    
    async def _update_price_history(self) -> None:
        """Update price and returns history for risk calculations"""
        try:
            for symbol, position in self.positions.items():
                # Initialize history if not exists
                if symbol not in self.price_history:
                    self.price_history[symbol] = []
                    self.returns_history[symbol] = []
                
                # Add current price
                self.price_history[symbol].append(position.price)
                
                # Calculate return if we have previous price
                if len(self.price_history[symbol]) > 1:
                    prev_price = self.price_history[symbol][-2]
                    if prev_price > 0:
                        return_pct = (position.price - prev_price) / prev_price
                        self.returns_history[symbol].append(return_pct)
                
                # Keep only last 252 observations (1 trading year)
                if len(self.price_history[symbol]) > 252:
                    self.price_history[symbol] = self.price_history[symbol][-252:]
                if len(self.returns_history[symbol]) > 252:
                    self.returns_history[symbol] = self.returns_history[symbol][-252:]
            
        except Exception as e:
            logger.error(f"Error updating price history: {e}")
    
    async def calculate_risk_metrics(self) -> Dict[str, Any]:
        """
        Public method to calculate risk metrics and return results
        """
        await self._calculate_risk_metrics()
        return {
            'gross_exposure': self.risk_metrics.gross_exposure,
            'net_exposure': self.risk_metrics.net_exposure,
            'leverage': self.risk_metrics.leverage,
            'var_1d': self.risk_metrics.portfolio_var_1d,
            'var_5d': self.risk_metrics.portfolio_var_5d,
            'var_10d': self.risk_metrics.portfolio_var_10d,
            'max_drawdown': self.risk_metrics.max_drawdown,
            'risk_level': self.risk_metrics.risk_level,
            'timestamp': self.risk_metrics.timestamp
        }
    
    async def _calculate_risk_metrics(self) -> None:
        """Calculate comprehensive portfolio risk metrics"""
        try:
            # Calculate portfolio-level metrics
            self.risk_metrics.gross_exposure = sum(abs(pos.market_value) for pos in self.positions.values())
            self.risk_metrics.net_exposure = sum(pos.market_value for pos in self.positions.values())
            self.risk_metrics.long_exposure = sum(max(0, pos.market_value) for pos in self.positions.values())
            self.risk_metrics.short_exposure = sum(min(0, pos.market_value) for pos in self.positions.values())
            
            if self.portfolio_value > 0:
                self.risk_metrics.leverage = self.risk_metrics.gross_exposure / self.portfolio_value
            
            # Calculate VaR using historical simulation
            await self._calculate_var()
            
            # Calculate drawdown metrics
            await self._calculate_drawdown_metrics()
            
            # Calculate concentration risk
            await self._calculate_concentration_risk()
            
            # Calculate correlation risk
            await self._calculate_correlation_risk()
            
            # Detect market regime
            await self._detect_market_regime()
            
            # Determine overall risk level
            self._determine_risk_level()
            
            self.risk_metrics.timestamp = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Error calculating risk metrics: {e}")
    
    async def _calculate_var(self) -> None:
        """Calculate Value at Risk using historical simulation"""
        try:
            if len(self.portfolio_returns) < 20:  # Need minimum history
                return
            
            returns = np.array(self.portfolio_returns[-252:])  # Last year of returns
            
            if len(returns) > 0:
                # Calculate VaR at different confidence levels
                confidence = self.risk_limits.var_confidence_level
                var_1d = np.percentile(returns, (1 - confidence) * 100)
                
                # Scale to different time horizons (assuming sqrt scaling)
                self.risk_metrics.portfolio_var_1d = abs(var_1d)
                self.risk_metrics.portfolio_var_5d = abs(var_1d) * math.sqrt(5)
                self.risk_metrics.portfolio_var_10d = abs(var_1d) * math.sqrt(10)
            
            # Calculate portfolio return for this period
            if len(self.positions) > 0:
                weighted_return = sum(pos.weight * self.returns_history.get(pos.symbol, [0])[-1] 
                                    for pos in self.positions.values()
                                    if len(self.returns_history.get(pos.symbol, [])) > 0)
                self.portfolio_returns.append(weighted_return)
                
                # Keep only last 252 observations
                if len(self.portfolio_returns) > 252:
                    self.portfolio_returns = self.portfolio_returns[-252:]
            
        except Exception as e:
            logger.error(f"Error calculating VaR: {e}")
    
    async def _calculate_drawdown_metrics(self) -> None:
        """Calculate drawdown metrics"""
        try:
            if len(self.portfolio_returns) < 2:
                return
            
            # Calculate cumulative returns
            cum_returns = np.cumprod(1 + np.array(self.portfolio_returns))
            
            if len(cum_returns) > 0:
                # Calculate running maximum
                running_max = np.maximum.accumulate(cum_returns)
                
                # Calculate drawdown
                drawdown = (cum_returns - running_max) / running_max
                
                self.risk_metrics.current_drawdown = drawdown[-1] if len(drawdown) > 0 else 0.0
                self.risk_metrics.max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0.0
            
        except Exception as e:
            logger.error(f"Error calculating drawdown: {e}")
    
    async def _calculate_concentration_risk(self) -> None:
        """Calculate concentration risk metrics"""
        try:
            if not self.positions:
                return
            
            # Position concentration (Herfindahl index)
            weights = [abs(pos.weight) for pos in self.positions.values()]
            self.risk_metrics.concentration_risk = sum(w**2 for w in weights)
            
            # Sector concentration
            sector_exposure = {}
            for pos in self.positions.values():
                sector = pos.sector
                if sector not in sector_exposure:
                    sector_exposure[sector] = 0.0
                sector_exposure[sector] += abs(pos.weight)
            
            self.risk_metrics.sector_concentration = sector_exposure
            
        except Exception as e:
            logger.error(f"Error calculating concentration risk: {e}")
    
    async def _calculate_correlation_risk(self) -> None:
        """Calculate correlation risk between positions"""
        try:
            if len(self.positions) < 2:
                self.risk_metrics.correlation_risk = 0.0
                return
            
            symbols = list(self.positions.keys())
            correlations = []
            
            # Calculate pairwise correlations
            for i, sym1 in enumerate(symbols):
                for j, sym2 in enumerate(symbols[i+1:], i+1):
                    returns1 = self.returns_history.get(sym1, [])
                    returns2 = self.returns_history.get(sym2, [])
                    
                    if len(returns1) > 10 and len(returns2) > 10:
                        # Align returns to same length
                        min_len = min(len(returns1), len(returns2))
                        r1 = np.array(returns1[-min_len:])
                        r2 = np.array(returns2[-min_len:])
                        
                        if len(r1) > 1 and len(r2) > 1:
                            correlation = np.corrcoef(r1, r2)[0, 1]
                            if not np.isnan(correlation):
                                correlations.append(abs(correlation))
            
            # Average absolute correlation as risk measure
            self.risk_metrics.correlation_risk = np.mean(correlations) if correlations else 0.0
            
        except Exception as e:
            logger.error(f"Error calculating correlation risk: {e}")
    
    async def _detect_market_regime(self) -> None:
        """Detect current market regime based on volatility and trends"""
        try:
            if len(self.portfolio_returns) < 20:
                self.risk_metrics.market_regime = MarketRegime.CALM
                return
            
            returns = np.array(self.portfolio_returns[-20:])  # Last 20 periods
            
            # Calculate volatility (annualized)
            volatility = np.std(returns) * math.sqrt(252)
            
            # Calculate trend strength (absolute mean return)
            trend_strength = abs(np.mean(returns)) * 252
            
            # Regime classification logic
            if volatility > 0.3:  # High volatility
                if trend_strength > 0.1:
                    self.risk_metrics.market_regime = MarketRegime.CRISIS
                else:
                    self.risk_metrics.market_regime = MarketRegime.VOLATILE
            elif trend_strength > 0.05:
                self.risk_metrics.market_regime = MarketRegime.TRENDING
            else:
                self.risk_metrics.market_regime = MarketRegime.CALM
            
        except Exception as e:
            logger.error(f"Error detecting market regime: {e}")
            self.risk_metrics.market_regime = MarketRegime.CALM
    
    def _determine_risk_level(self) -> None:
        """Determine overall portfolio risk level"""
        risk_score = 0
        
        # VaR contribution
        if self.risk_metrics.portfolio_var_1d > self.risk_limits.max_portfolio_var:
            risk_score += 2
        elif self.risk_metrics.portfolio_var_1d > self.risk_limits.max_portfolio_var * 0.7:
            risk_score += 1
        
        # Drawdown contribution
        if abs(self.risk_metrics.current_drawdown) > self.risk_limits.max_drawdown:
            risk_score += 2
        elif abs(self.risk_metrics.current_drawdown) > self.risk_limits.max_drawdown * 0.7:
            risk_score += 1
        
        # Concentration contribution
        if self.risk_metrics.concentration_risk > 0.5:
            risk_score += 1
        
        # Leverage contribution
        if self.risk_metrics.leverage > self.risk_limits.max_leverage:
            risk_score += 2
        elif self.risk_metrics.leverage > self.risk_limits.max_leverage * 0.8:
            risk_score += 1
        
        # Market regime contribution
        if self.risk_metrics.market_regime == MarketRegime.CRISIS:
            risk_score += 2
        elif self.risk_metrics.market_regime == MarketRegime.VOLATILE:
            risk_score += 1
        
        # Classify risk level
        if risk_score >= 5:
            self.risk_metrics.risk_level = RiskLevel.CRITICAL
        elif risk_score >= 3:
            self.risk_metrics.risk_level = RiskLevel.HIGH
        elif risk_score >= 1:
            self.risk_metrics.risk_level = RiskLevel.MEDIUM
        else:
            self.risk_metrics.risk_level = RiskLevel.LOW
    
    async def _check_risk_limits(self) -> None:
        """Check all risk limits and generate alerts"""
        alerts = []
        
        # Position size limits
        for pos in self.positions.values():
            if abs(pos.weight) > self.risk_limits.max_position_size:
                alerts.append({
                    'type': 'position_limit_breach',
                    'severity': 'high',
                    'symbol': pos.symbol,
                    'current_weight': pos.weight,
                    'limit': self.risk_limits.max_position_size,
                    'message': f"Position {pos.symbol} exceeds size limit: {pos.weight:.1%} > {self.risk_limits.max_position_size:.1%}"
                })
        
        # Sector concentration limits
        for sector, exposure in self.risk_metrics.sector_concentration.items():
            if exposure > self.risk_limits.max_sector_concentration:
                alerts.append({
                    'type': 'sector_concentration_breach',
                    'severity': 'medium',
                    'sector': sector,
                    'exposure': exposure,
                    'limit': self.risk_limits.max_sector_concentration,
                    'message': f"Sector {sector} exceeds concentration limit: {exposure:.1%} > {self.risk_limits.max_sector_concentration:.1%}"
                })
        
        # VaR limits
        if self.risk_metrics.portfolio_var_1d > self.risk_limits.max_portfolio_var:
            alerts.append({
                'type': 'var_limit_breach',
                'severity': 'high',
                'current_var': self.risk_metrics.portfolio_var_1d,
                'limit': self.risk_limits.max_portfolio_var,
                'message': f"Portfolio VaR exceeds limit: {self.risk_metrics.portfolio_var_1d:.1%} > {self.risk_limits.max_portfolio_var:.1%}"
            })
        
        # Drawdown limits
        if abs(self.risk_metrics.current_drawdown) > self.risk_limits.max_drawdown:
            alerts.append({
                'type': 'drawdown_limit_breach',
                'severity': 'critical',
                'current_drawdown': self.risk_metrics.current_drawdown,
                'limit': self.risk_limits.max_drawdown,
                'message': f"Portfolio drawdown exceeds limit: {abs(self.risk_metrics.current_drawdown):.1%} > {self.risk_limits.max_drawdown:.1%}"
            })
        
        # Leverage limits
        if self.risk_metrics.leverage > self.risk_limits.max_leverage:
            alerts.append({
                'type': 'leverage_limit_breach',
                'severity': 'high',
                'current_leverage': self.risk_metrics.leverage,
                'limit': self.risk_limits.max_leverage,
                'message': f"Portfolio leverage exceeds limit: {self.risk_metrics.leverage:.1f}x > {self.risk_limits.max_leverage:.1f}x"
            })
        
        # Add alerts with timestamp
        for alert in alerts:
            alert['timestamp'] = datetime.utcnow()
        
        self.alerts.extend(alerts)
        
        # Keep only recent alerts (last 24 hours)
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        self.alerts = [alert for alert in self.alerts if alert['timestamp'] > cutoff_time]
        
        if alerts:
            logger.warning(f"Generated {len(alerts)} risk alerts")
    
    async def calculate_position_size(self, symbol: str, target_risk: float = 0.01) -> float:
        """
        Calculate optimal position size based on volatility targeting
        
        Args:
            symbol: Asset symbol
            target_risk: Target risk contribution (default 1%)
            
        Returns:
            Recommended position size as fraction of portfolio
        """
        try:
            if symbol not in self.returns_history or len(self.returns_history[symbol]) < 10:
                # Default conservative sizing if no history
                return min(0.02, self.risk_limits.max_position_size)  # 2% or limit
            
            returns = np.array(self.returns_history[symbol][-60:])  # Last 60 periods
            volatility = np.std(returns) * math.sqrt(252)  # Annualized volatility
            
            if volatility <= 0:
                return 0.0
            
            # Position size = target_risk / volatility
            position_size = target_risk / volatility
            
            # Apply limits
            position_size = min(position_size, self.risk_limits.max_position_size)
            position_size = max(position_size, 0.001)  # Minimum 0.1%
            
            return position_size
            
        except Exception as e:
            logger.error(f"Error calculating position size for {symbol}: {e}")
            return 0.01  # 1% default
    
    async def get_rebalancing_recommendations(self) -> List[Dict[str, Any]]:
        """Generate portfolio rebalancing recommendations"""
        recommendations = []
        
        try:
            # Check for positions exceeding limits
            for pos in self.positions.values():
                if abs(pos.weight) > self.risk_limits.max_position_size:
                    target_weight = self.risk_limits.max_position_size * 0.8  # 20% buffer
                    recommendations.append({
                        'action': 'reduce_position',
                        'symbol': pos.symbol,
                        'current_weight': pos.weight,
                        'target_weight': target_weight if pos.weight > 0 else -target_weight,
                        'priority': 'high',
                        'reason': 'Position size limit exceeded'
                    })
            
            # Check sector concentrations
            for sector, exposure in self.risk_metrics.sector_concentration.items():
                if exposure > self.risk_limits.max_sector_concentration:
                    recommendations.append({
                        'action': 'reduce_sector_exposure',
                        'sector': sector,
                        'current_exposure': exposure,
                        'target_exposure': self.risk_limits.max_sector_concentration * 0.8,
                        'priority': 'medium',
                        'reason': 'Sector concentration limit exceeded'
                    })
            
            # Risk-based recommendations
            if self.risk_metrics.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                recommendations.append({
                    'action': 'reduce_overall_risk',
                    'current_risk_level': self.risk_metrics.risk_level.value,
                    'target_reduction': 0.2,  # 20% risk reduction
                    'priority': 'high',
                    'reason': f'Portfolio risk level is {self.risk_metrics.risk_level.value}'
                })
            
        except Exception as e:
            logger.error(f"Error generating rebalancing recommendations: {e}")
        
        return recommendations
    
    async def _record_slo_metrics(self, operation: str, execution_time: float, success: bool) -> None:
        """Record SLO metrics for risk management operations"""
        if not self.slo_monitor:
            return
        
        try:
            await self.slo_monitor.record_metric(
                service_name="advanced_risk_manager",
                operation_name=operation,
                latency_ms=execution_time,
                success=success,
                metadata={
                    'portfolio_value': self.portfolio_value,
                    'position_count': len(self.positions),
                    'risk_level': self.risk_metrics.risk_level.value,
                    'market_regime': self.risk_metrics.market_regime.value
                }
            )
        except Exception as e:
            logger.error(f"Error recording SLO metrics: {e}")
    
    def get_risk_summary(self) -> Dict[str, Any]:
        """Get comprehensive risk summary"""
        return {
            'portfolio_metrics': {
                'value': self.portfolio_value,
                'leverage': self.risk_metrics.leverage,
                'gross_exposure': self.risk_metrics.gross_exposure,
                'net_exposure': self.risk_metrics.net_exposure,
                'position_count': len(self.positions)
            },
            'risk_metrics': {
                'var_1d': self.risk_metrics.portfolio_var_1d,
                'var_5d': self.risk_metrics.portfolio_var_5d,
                'max_drawdown': self.risk_metrics.max_drawdown,
                'current_drawdown': self.risk_metrics.current_drawdown,
                'concentration_risk': self.risk_metrics.concentration_risk,
                'correlation_risk': self.risk_metrics.correlation_risk,
                'risk_level': self.risk_metrics.risk_level.value,
                'market_regime': self.risk_metrics.market_regime.value
            },
            'sector_exposure': self.risk_metrics.sector_concentration,
            'active_alerts': len([a for a in self.alerts if a['timestamp'] > datetime.utcnow() - timedelta(hours=1)]),
            'last_updated': self.risk_metrics.timestamp.isoformat()
        }
    
    async def emergency_risk_reduction(self, target_reduction: float = 0.5) -> List[Dict[str, Any]]:
        """
        Emergency risk reduction protocol
        
        Args:
            target_reduction: Target risk reduction (0.5 = 50% reduction)
            
        Returns:
            List of emergency actions to execute
        """
        actions = []
        
        try:
            logger.warning(f"EMERGENCY RISK REDUCTION ACTIVATED - Target: {target_reduction:.1%}")
            
            # Sort positions by risk contribution
            risk_positions = []
            for pos in self.positions.values():
                risk_score = abs(pos.weight) * pos.volatility * (1 + pos.beta)
                risk_positions.append((risk_score, pos))
            
            risk_positions.sort(reverse=True)  # Highest risk first
            
            # Generate reduction actions
            total_risk_reduced = 0.0
            for risk_score, pos in risk_positions:
                if total_risk_reduced >= target_reduction:
                    break
                
                # Reduce position by up to 50%
                reduction_pct = min(0.5, (target_reduction - total_risk_reduced) / risk_score) if risk_score > 0 else 0.5
                
                actions.append({
                    'action': 'emergency_position_reduction',
                    'symbol': pos.symbol,
                    'current_quantity': pos.quantity,
                    'reduction_pct': reduction_pct,
                    'new_quantity': pos.quantity * (1 - reduction_pct),
                    'risk_score': risk_score,
                    'priority': 'critical',
                    'reason': 'Emergency risk reduction protocol'
                })
                
                total_risk_reduced += reduction_pct * risk_score
            
            # Add cash raising action
            actions.append({
                'action': 'raise_cash',
                'target_cash_pct': 0.2,  # Raise to 20% cash
                'priority': 'critical',
                'reason': 'Emergency liquidity buffer'
            })
            
        except Exception as e:
            logger.error(f"Error in emergency risk reduction: {e}")
        
        return actions


# Example usage and testing
if __name__ == "__main__":
    async def test_risk_manager():
        """Test the Advanced Risk Manager"""
        print("🛡️ Testing Advanced Risk Manager")
        print("=" * 50)
        
        # Initialize risk manager
        risk_manager = AdvancedRiskManager()
        
        # Sample portfolio data
        sample_positions = {
            'AAPL': {
                'quantity': 100,
                'price': 150.0,
                'market_value': 15000,
                'sector': 'Technology',
                'beta': 1.2,
                'volatility': 0.25
            },
            'GOOGL': {
                'quantity': 50,
                'price': 2500.0,
                'market_value': 125000,
                'sector': 'Technology',
                'beta': 1.1,
                'volatility': 0.28
            },
            'TSLA': {
                'quantity': 200,
                'price': 200.0,
                'market_value': 40000,
                'sector': 'Automotive',
                'beta': 1.8,
                'volatility': 0.45
            }
        }
        
        # Update positions
        await risk_manager.update_positions(sample_positions)
        
        # Get risk summary
        summary = risk_manager.get_risk_summary()
        print("📊 Risk Summary:")
        for category, metrics in summary.items():
            print(f"  {category}: {metrics}")
        
        # Test position sizing
        print("\n💰 Position Sizing Recommendations:")
        for symbol in sample_positions.keys():
            size = await risk_manager.calculate_position_size(symbol)
            print(f"  {symbol}: {size:.1%} of portfolio")
        
        # Get rebalancing recommendations
        recommendations = await risk_manager.get_rebalancing_recommendations()
        print(f"\n⚖️ Rebalancing Recommendations: {len(recommendations)} found")
        for rec in recommendations:
            print(f"  {rec['action']}: {rec.get('reason', 'N/A')}")
        
        print("\n✅ Advanced Risk Manager test completed successfully!")
    
    # Run test
    asyncio.run(test_risk_manager())