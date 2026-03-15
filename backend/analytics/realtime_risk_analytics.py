"""
Real-Time Risk Analytics for Hedge Fund Trading Platform
=======================================================

Streaming risk calculations and monitoring with:
- Real-time portfolio exposure analysis
- Sector concentration monitoring
- Cross-asset correlation tracking
- Market stress testing
- Automated risk alerts and notifications
- Risk attribution and decomposition
- Scenario analysis and backtesting
- SLO integration for operational monitoring

Created: 2025-09-30
Author: Production Trading System
"""

import asyncio
from collections import defaultdict, deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import logging
import math
import threading
import time
from typing import Any
import warnings

import numpy as np

# Suppress numpy warnings
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Try importing external dependencies
try:
    from scipy.linalg import eigvals
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logging.warning("SciPy not available - using fallback calculations")

try:
    from backend.monitoring.slo_monitor import SLOMonitor
    SLO_AVAILABLE = True
except ImportError:
    SLO_AVAILABLE = False
    logging.warning("SLO Monitor not available")

logger = logging.getLogger(__name__)


class RiskEvent(Enum):
    """Risk event types"""
    POSITION_LIMIT_BREACH = "position_limit_breach"
    SECTOR_CONCENTRATION = "sector_concentration"
    VAR_EXCEEDED = "var_exceeded"
    DRAWDOWN_ALERT = "drawdown_alert"
    CORRELATION_SPIKE = "correlation_spike"
    VOLATILITY_REGIME_CHANGE = "volatility_regime_change"
    LIQUIDITY_SHORTAGE = "liquidity_shortage"
    STRESS_TEST_FAILURE = "stress_test_failure"


class AlertPriority(Enum):
    """Alert priority levels"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class RiskAlert:
    """Risk alert structure"""
    id: str
    event_type: RiskEvent
    priority: AlertPriority
    title: str
    message: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    auto_resolved: bool = False


@dataclass
class ExposureMetrics:
    """Portfolio exposure metrics"""
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    long_exposure: float = 0.0
    short_exposure: float = 0.0
    sector_exposure: dict[str, float] = field(default_factory=dict)
    currency_exposure: dict[str, float] = field(default_factory=dict)
    region_exposure: dict[str, float] = field(default_factory=dict)
    beta_exposure: float = 1.0
    duration_exposure: float = 0.0
    leverage: float = 1.0


@dataclass
class CorrelationMetrics:
    """Correlation analysis metrics"""
    avg_correlation: float = 0.0
    max_correlation: float = 0.0
    min_correlation: float = 0.0
    correlation_clusters: dict[str, list[str]] = field(default_factory=dict)
    eigen_risk: float = 0.0  # First eigenvalue of correlation matrix
    concentration_ratio: float = 0.0  # Risk concentration measure


@dataclass
class StressTestResult:
    """Stress test scenario result"""
    scenario_name: str
    scenario_description: str
    portfolio_pnl: float
    var_shock: float
    positions_affected: int
    worst_position: str
    worst_position_pnl: float
    risk_metrics_change: dict[str, float]
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RiskAttribution:
    """Risk attribution by factors"""
    position_risk: dict[str, float] = field(default_factory=dict)
    sector_risk: dict[str, float] = field(default_factory=dict)
    factor_risk: dict[str, float] = field(default_factory=dict)
    specific_risk: float = 0.0
    systematic_risk: float = 0.0
    idiosyncratic_risk: float = 0.0


class RealTimeRiskAnalytics:
    """
    Real-Time Risk Analytics System

    Features:
    - Streaming risk calculations with sub-second latency
    - Multi-dimensional exposure analysis (sector, region, currency)
    - Dynamic correlation monitoring with regime detection
    - Automated stress testing with market scenarios
    - Risk attribution and factor decomposition
    - Real-time alert generation and notification
    - Historical risk analytics and backtesting
    - Integration with SLO monitoring for operational excellence
    """

    def __init__(self,
                 update_frequency: int = 1,  # seconds
                 correlation_window: int = 60,  # observations
                 var_confidence: float = 0.95,
                 enable_slo: bool = True,
                 max_alerts_per_hour: int = 50):
        """Initialize Real-Time Risk Analytics"""
        self.update_frequency = update_frequency
        self.correlation_window = correlation_window
        self.var_confidence = var_confidence
        self.max_alerts_per_hour = max_alerts_per_hour

        # Data storage
        self.positions: dict[str, dict[str, Any]] = {}
        self.price_stream: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.return_stream: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.portfolio_values: deque = deque(maxlen=10000)
        self.portfolio_returns: deque = deque(maxlen=1000)

        # Risk metrics
        self.current_exposure: ExposureMetrics = ExposureMetrics()
        self.current_correlation: CorrelationMetrics = CorrelationMetrics()
        self.current_var: float = 0.0
        self.current_cvar: float = 0.0

        # Alerts and notifications
        self.active_alerts: dict[str, RiskAlert] = {}
        self.alert_history: deque = deque(maxlen=1000)
        self.alert_callbacks: list[Callable[[RiskAlert], None]] = []
        self.alert_count_by_hour: deque = deque(maxlen=24)

        # Stress testing
        self.stress_scenarios: dict[str, dict[str, Any]] = {}
        self.stress_results: deque = deque(maxlen=100)

        # Analytics
        self.risk_attribution: RiskAttribution = RiskAttribution()
        self.executor = ThreadPoolExecutor(max_workers=6)
        self.running = False
        self.update_thread: threading.Thread | None = None

        # Initialize stress scenarios
        self._initialize_stress_scenarios()

        # Initialize SLO monitoring
        if enable_slo and SLO_AVAILABLE:
            try:
                self.slo_monitor = SLOMonitor()
                logger.info("SLO monitoring enabled for risk analytics")
            except Exception as e:
                logger.warning(f"Failed to initialize SLO monitor: {e}")
                self.slo_monitor = None
        else:
            self.slo_monitor = None

        logger.info("Real-Time Risk Analytics initialized")

    def _initialize_stress_scenarios(self) -> None:
        """Initialize market stress test scenarios"""
        self.stress_scenarios = {
            'market_crash': {
                'name': '2008-Style Market Crash',
                'description': 'Equity markets down 20%, credit spreads widen 300bp',
                'shocks': {
                    'equity_shock': -0.20,
                    'credit_shock': 0.03,
                    'vol_shock': 2.0,
                    'correlation_shock': 0.3
                }
            },
            'flash_crash': {
                'name': 'Flash Crash Scenario',
                'description': 'Sudden 10% market drop with liquidity crisis',
                'shocks': {
                    'equity_shock': -0.10,
                    'liquidity_shock': 0.5,
                    'vol_shock': 3.0,
                    'correlation_shock': 0.8
                }
            },
            'interest_rate_shock': {
                'name': 'Interest Rate Shock',
                'description': 'Rates up 200bp, duration impact on bonds',
                'shocks': {
                    'rate_shock': 0.02,
                    'duration_impact': -0.15,
                    'credit_shock': 0.01
                }
            },
            'currency_crisis': {
                'name': 'Currency Crisis',
                'description': 'Major currency devaluation, FX volatility spike',
                'shocks': {
                    'fx_shock': -0.15,
                    'vol_shock': 2.5,
                    'correlation_shock': 0.2
                }
            },
            'sector_rotation': {
                'name': 'Sector Rotation Shock',
                'description': 'Tech down 25%, value up 10%',
                'shocks': {
                    'tech_shock': -0.25,
                    'value_shock': 0.10,
                    'growth_shock': -0.15
                }
            }
        }

    async def update_positions(self, positions_data: dict[str, dict[str, Any]]) -> None:
        """Update position data and trigger analytics"""
        start_time = datetime.now(UTC)

        try:
            self.positions = positions_data

            # Extract price data and update streams
            for symbol, data in positions_data.items():
                price = data.get('price', 0.0)
                if price > 0:
                    self.price_stream[symbol].append(price)

                    # Calculate return if we have previous price
                    if len(self.price_stream[symbol]) > 1:
                        prev_price = self.price_stream[symbol][-2]
                        if prev_price > 0:
                            return_pct = (price - prev_price) / prev_price
                            self.return_stream[symbol].append(return_pct)

            # Calculate portfolio value
            portfolio_value = sum(abs(pos.get('market_value', 0)) for pos in positions_data.values())
            self.portfolio_values.append(portfolio_value)

            # Calculate portfolio return
            if len(self.portfolio_values) > 1:
                prev_value = self.portfolio_values[-2]
                if prev_value > 0:
                    portfolio_return = (portfolio_value - prev_value) / prev_value
                    self.portfolio_returns.append(portfolio_return)

            # Run analytics
            await self._calculate_exposure_metrics()
            await self._calculate_correlation_metrics()
            await self._calculate_var_metrics()
            await self._calculate_risk_attribution()

            # Check for alerts
            await self._check_risk_alerts()

            # Record SLO metrics
            if self.slo_monitor:
                execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
                await self._record_slo_metrics("position_update", execution_time, success=True)

        except Exception as e:
            logger.error(f"Error updating positions: {e}")
            if self.slo_monitor:
                execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
                await self._record_slo_metrics("position_update", execution_time, success=False)
            raise

    async def _calculate_exposure_metrics(self) -> None:
        """Calculate portfolio exposure metrics"""
        try:
            exposure = ExposureMetrics()

            # Calculate basic exposures
            for position_data in self.positions.values():
                market_value = position_data.get('market_value', 0.0)

                exposure.gross_exposure += abs(market_value)
                exposure.net_exposure += market_value

                if market_value > 0:
                    exposure.long_exposure += market_value
                else:
                    exposure.short_exposure += abs(market_value)

                # Sector exposure
                sector = position_data.get('sector', 'Unknown')
                if sector not in exposure.sector_exposure:
                    exposure.sector_exposure[sector] = 0.0
                exposure.sector_exposure[sector] += abs(market_value)

                # Currency exposure
                currency = position_data.get('currency', 'USD')
                if currency not in exposure.currency_exposure:
                    exposure.currency_exposure[currency] = 0.0
                exposure.currency_exposure[currency] += abs(market_value)

                # Region exposure
                region = position_data.get('region', 'US')
                if region not in exposure.region_exposure:
                    exposure.region_exposure[region] = 0.0
                exposure.region_exposure[region] += abs(market_value)

            # Calculate derived metrics
            if self.portfolio_values:
                portfolio_value = self.portfolio_values[-1]
                if portfolio_value > 0:
                    exposure.leverage = exposure.gross_exposure / portfolio_value

                    # Convert to percentages
                    for sector in exposure.sector_exposure:
                        exposure.sector_exposure[sector] /= portfolio_value
                    for currency in exposure.currency_exposure:
                        exposure.currency_exposure[currency] /= portfolio_value
                    for region in exposure.region_exposure:
                        exposure.region_exposure[region] /= portfolio_value

            # Calculate beta exposure (weighted average)
            total_weight = 0.0
            weighted_beta = 0.0
            for position_data in self.positions.values():
                weight = abs(position_data.get('market_value', 0.0))
                beta = position_data.get('beta', 1.0)
                weighted_beta += weight * beta
                total_weight += weight

            if total_weight > 0:
                exposure.beta_exposure = weighted_beta / total_weight

            self.current_exposure = exposure

        except Exception as e:
            logger.error(f"Error calculating exposure metrics: {e}")

    async def _calculate_correlation_metrics(self) -> None:
        """Calculate correlation metrics"""
        try:
            if len(self.positions) < 2:
                return

            symbols = list(self.positions.keys())
            correlations = []

            # Calculate pairwise correlations
            for i, symbol1 in enumerate(symbols):
                for _j, symbol2 in enumerate(symbols[i+1:], i+1):
                    returns1 = list(self.return_stream[symbol1])
                    returns2 = list(self.return_stream[symbol2])

                    if len(returns1) >= 20 and len(returns2) >= 20:
                        # Align returns
                        min_len = min(len(returns1), len(returns2))
                        r1 = np.array(returns1[-min_len:])
                        r2 = np.array(returns2[-min_len:])

                        if len(r1) > 1 and len(r2) > 1:
                            corr = np.corrcoef(r1, r2)[0, 1]
                            if not np.isnan(corr):
                                correlations.append(corr)

            if correlations:
                self.current_correlation.avg_correlation = np.mean(correlations)
                self.current_correlation.max_correlation = np.max(correlations)
                self.current_correlation.min_correlation = np.min(correlations)

            # Calculate correlation matrix and eigenvalue risk
            await self._calculate_eigen_risk(symbols)

        except Exception as e:
            logger.error(f"Error calculating correlation metrics: {e}")

    async def _calculate_eigen_risk(self, symbols: list[str]) -> None:
        """Calculate eigenvalue-based risk metrics"""
        try:
            if len(symbols) < 3:
                return

            # Build return matrix
            return_matrix = []
            min_length = float('inf')

            for symbol in symbols:
                returns = list(self.return_stream[symbol])
                if len(returns) >= 30:
                    return_matrix.append(returns)
                    min_length = min(min_length, len(returns))
                else:
                    return_matrix.append([])

            if min_length == float('inf') or min_length < 30:
                return

            # Align all return series
            aligned_returns = []
            for returns in return_matrix:
                if len(returns) >= min_length:
                    aligned_returns.append(returns[-int(min_length):])
                else:
                    # Fill with zeros (not ideal, but prevents crashes)
                    aligned_returns.append([0.0] * int(min_length))

            if len(aligned_returns) > 2:
                returns_df = np.array(aligned_returns).T

                # Calculate correlation matrix
                corr_matrix = np.corrcoef(returns_df.T)

                if SCIPY_AVAILABLE:
                    # Calculate eigenvalues
                    eigenvals = eigvals(corr_matrix)
                    eigenvals = np.real(eigenvals)  # Take real part
                    eigenvals = eigenvals[eigenvals > 0]  # Positive eigenvalues only

                    if len(eigenvals) > 0:
                        # First eigenvalue as risk measure
                        self.current_correlation.eigen_risk = np.max(eigenvals) / len(eigenvals)

                        # Concentration ratio
                        self.current_correlation.concentration_ratio = np.sum(eigenvals[:3]) / np.sum(eigenvals) if len(eigenvals) >= 3 else 1.0

        except Exception as e:
            logger.error(f"Error calculating eigen risk: {e}")

    async def _calculate_var_metrics(self) -> None:
        """Calculate Value at Risk metrics"""
        try:
            if len(self.portfolio_returns) < 20:
                return

            returns = np.array(list(self.portfolio_returns))

            # Historical VaR
            self.current_var = abs(np.percentile(returns, (1 - self.var_confidence) * 100))

            # Conditional VaR (Expected Shortfall)
            var_threshold = np.percentile(returns, (1 - self.var_confidence) * 100)
            tail_returns = returns[returns <= var_threshold]
            if len(tail_returns) > 0:
                self.current_cvar = abs(np.mean(tail_returns))

        except Exception as e:
            logger.error(f"Error calculating VaR metrics: {e}")

    async def _calculate_risk_attribution(self) -> None:
        """Calculate risk attribution by positions and factors"""
        try:
            attribution = RiskAttribution()

            if not self.positions:
                return

            # Portfolio volatility (if we have enough data)
            if len(self.portfolio_returns) > 20:
                portfolio_vol = np.std(list(self.portfolio_returns)) * math.sqrt(252)

                if portfolio_vol > 0:
                    # Position-level risk contribution
                    total_value = sum(abs(pos.get('market_value', 0)) for pos in self.positions.values())

                    for symbol, pos_data in self.positions.items():
                        weight = abs(pos_data.get('market_value', 0)) / total_value if total_value > 0 else 0
                        pos_vol = pos_data.get('volatility', 0.2)  # Default 20% vol

                        # Risk contribution = weight * volatility * correlation with portfolio
                        # Simplified: assume correlation = beta
                        beta = pos_data.get('beta', 1.0)
                        risk_contrib = weight * pos_vol * beta
                        attribution.position_risk[symbol] = risk_contrib

                    # Sector risk aggregation
                    for symbol, pos_data in self.positions.items():
                        sector = pos_data.get('sector', 'Unknown')
                        if sector not in attribution.sector_risk:
                            attribution.sector_risk[sector] = 0.0
                        attribution.sector_risk[sector] += attribution.position_risk.get(symbol, 0.0)

                    # Factor risk (simplified)
                    market_risk = sum(attribution.position_risk.values()) * 0.6  # 60% systematic
                    attribution.systematic_risk = market_risk
                    attribution.idiosyncratic_risk = portfolio_vol - market_risk

            self.risk_attribution = attribution

        except Exception as e:
            logger.error(f"Error calculating risk attribution: {e}")

    async def _check_risk_alerts(self) -> None:
        """Check for risk alerts and generate notifications"""
        try:
            current_hour = datetime.now(UTC).hour

            # Clean up alert count tracking
            while len(self.alert_count_by_hour) >= 24:
                self.alert_count_by_hour.popleft()

            # Count alerts in current hour
            current_hour_alerts = sum(1 for alert in self.alert_history
                                    if alert.timestamp.hour == current_hour and
                                       alert.timestamp.date() == datetime.now(UTC).date())

            # Rate limiting: don't generate too many alerts
            if current_hour_alerts >= self.max_alerts_per_hour:
                return

            # Check various risk conditions
            await self._check_exposure_alerts()
            await self._check_var_alerts()
            await self._check_correlation_alerts()
            await self._check_drawdown_alerts()

        except Exception as e:
            logger.error(f"Error checking risk alerts: {e}")

    async def _check_exposure_alerts(self) -> None:
        """Check exposure-related alerts"""
        try:
            # Leverage alert
            if self.current_exposure.leverage > 3.0:
                await self._generate_alert(
                    RiskEvent.POSITION_LIMIT_BREACH,
                    AlertPriority.HIGH,
                    "High Leverage Alert",
                    f"Portfolio leverage is {self.current_exposure.leverage:.2f}x, exceeding 3.0x limit",
                    {'leverage': self.current_exposure.leverage}
                )

            # Sector concentration alerts
            for sector, exposure in self.current_exposure.sector_exposure.items():
                if exposure > 0.4:  # 40% threshold
                    await self._generate_alert(
                        RiskEvent.SECTOR_CONCENTRATION,
                        AlertPriority.MEDIUM,
                        f"High {sector} Concentration",
                        f"Sector exposure to {sector} is {exposure:.1%}, exceeding 40% limit",
                        {'sector': sector, 'exposure': exposure}
                    )

        except Exception as e:
            logger.error(f"Error checking exposure alerts: {e}")

    async def _check_var_alerts(self) -> None:
        """Check VaR-related alerts"""
        try:
            # VaR threshold alert (2% daily VaR)
            if self.current_var > 0.02:
                await self._generate_alert(
                    RiskEvent.VAR_EXCEEDED,
                    AlertPriority.HIGH,
                    "VaR Limit Exceeded",
                    f"Daily VaR is {self.current_var:.2%}, exceeding 2% limit",
                    {'var': self.current_var, 'cvar': self.current_cvar}
                )

        except Exception as e:
            logger.error(f"Error checking VaR alerts: {e}")

    async def _check_correlation_alerts(self) -> None:
        """Check correlation-related alerts"""
        try:
            # High correlation alert
            if self.current_correlation.avg_correlation > 0.7:
                await self._generate_alert(
                    RiskEvent.CORRELATION_SPIKE,
                    AlertPriority.MEDIUM,
                    "High Portfolio Correlation",
                    f"Average correlation is {self.current_correlation.avg_correlation:.2%}, indicating concentration risk",
                    {'avg_correlation': self.current_correlation.avg_correlation}
                )

            # Eigen risk alert
            if self.current_correlation.eigen_risk > 2.0:
                await self._generate_alert(
                    RiskEvent.CORRELATION_SPIKE,
                    AlertPriority.HIGH,
                    "High Eigenvalue Risk",
                    f"First eigenvalue ratio is {self.current_correlation.eigen_risk:.2f}, indicating systemic risk",
                    {'eigen_risk': self.current_correlation.eigen_risk}
                )

        except Exception as e:
            logger.error(f"Error checking correlation alerts: {e}")

    async def _check_drawdown_alerts(self) -> None:
        """Check drawdown-related alerts"""
        try:
            if len(self.portfolio_values) < 20:
                return

            values = list(self.portfolio_values)
            peak = max(values)
            current = values[-1]

            if peak > 0:
                drawdown = (peak - current) / peak

                if drawdown > 0.05:  # 5% drawdown
                    await self._generate_alert(
                        RiskEvent.DRAWDOWN_ALERT,
                        AlertPriority.CRITICAL if drawdown > 0.10 else AlertPriority.HIGH,
                        "Portfolio Drawdown Alert",
                        f"Portfolio is down {drawdown:.1%} from peak, review risk controls",
                        {'drawdown': drawdown, 'peak_value': peak, 'current_value': current}
                    )

        except Exception as e:
            logger.error(f"Error checking drawdown alerts: {e}")

    async def _generate_alert(self,
                            event_type: RiskEvent,
                            priority: AlertPriority,
                            title: str,
                            message: str,
                            metadata: dict[str, Any]) -> None:
        """Generate and process risk alert"""
        try:
            # Create alert
            alert_id = f"{event_type.value}_{int(time.time() * 1000)}"

            alert = RiskAlert(
                id=alert_id,
                event_type=event_type,
                priority=priority,
                title=title,
                message=message,
                timestamp=datetime.now(UTC),
                metadata=metadata
            )

            # Check if similar alert is already active (avoid spam)
            similar_active = False
            for active_alert in self.active_alerts.values():
                if (active_alert.event_type == event_type and
                    active_alert.title == title and
                    not active_alert.acknowledged):
                    similar_active = True
                    break

            if not similar_active:
                # Store alert
                self.active_alerts[alert_id] = alert
                self.alert_history.append(alert)

                # Execute callbacks
                for callback in self.alert_callbacks:
                    try:
                        callback(alert)
                    except Exception as e:
                        logger.error(f"Error in alert callback: {e}")

                logger.warning(f"Risk Alert Generated: [{priority.name}] {title} - {message}")

        except Exception as e:
            logger.error(f"Error generating alert: {e}")

    async def run_stress_test(self, scenario_name: str) -> StressTestResult:
        """Run stress test scenario"""
        start_time = datetime.now(UTC)

        try:
            if scenario_name not in self.stress_scenarios:
                raise ValueError(f"Unknown stress scenario: {scenario_name}")

            scenario = self.stress_scenarios[scenario_name]
            shocks = scenario['shocks']

            # Calculate portfolio P&L under stress
            total_pnl = 0.0
            positions_affected = 0
            worst_position = ""
            worst_position_pnl = 0.0

            for symbol, position_data in self.positions.items():
                market_value = position_data.get('market_value', 0.0)
                sector = position_data.get('sector', 'Unknown')
                beta = position_data.get('beta', 1.0)

                # Apply shocks based on position characteristics
                position_shock = 0.0

                # Equity shock (applies to all equity positions)
                if 'equity_shock' in shocks:
                    position_shock += shocks['equity_shock'] * beta

                # Sector-specific shocks
                if 'tech_shock' in shocks and 'tech' in sector.lower():
                    position_shock += shocks['tech_shock']
                elif 'value_shock' in shocks and 'value' in sector.lower():
                    position_shock += shocks['value_shock']

                # Credit shock (for fixed income)
                if 'credit_shock' in shocks and 'bond' in sector.lower():
                    duration = position_data.get('duration', 5.0)
                    position_shock -= shocks['credit_shock'] * duration

                # FX shock
                currency = position_data.get('currency', 'USD')
                if 'fx_shock' in shocks and currency != 'USD':
                    position_shock += shocks['fx_shock']

                # Calculate position P&L
                position_pnl = market_value * position_shock
                total_pnl += position_pnl

                if abs(position_pnl) > 0:
                    positions_affected += 1

                if position_pnl < worst_position_pnl:
                    worst_position = symbol
                    worst_position_pnl = position_pnl

            # Calculate VaR shock
            var_multiplier = shocks.get('vol_shock', 1.0)
            var_shock = self.current_var * var_multiplier

            # Risk metrics change
            risk_metrics_change = {
                'var_change': var_shock - self.current_var,
                'correlation_change': shocks.get('correlation_shock', 0.0),
                'volatility_change': var_multiplier - 1.0
            }

            result = StressTestResult(
                scenario_name=scenario['name'],
                scenario_description=scenario['description'],
                portfolio_pnl=total_pnl,
                var_shock=var_shock,
                positions_affected=positions_affected,
                worst_position=worst_position,
                worst_position_pnl=worst_position_pnl,
                risk_metrics_change=risk_metrics_change
            )

            # Store result
            self.stress_results.append(result)

            # Check if stress test failed (>10% portfolio loss)
            if abs(total_pnl) > 0.1 * sum(abs(p.get('market_value', 0)) for p in self.positions.values()):
                await self._generate_alert(
                    RiskEvent.STRESS_TEST_FAILURE,
                    AlertPriority.CRITICAL,
                    f"Stress Test Failure: {scenario['name']}",
                    f"Portfolio would lose {abs(total_pnl):,.0f} in {scenario['name']} scenario",
                    {'scenario': scenario_name, 'pnl': total_pnl}
                )

            # Record SLO metrics
            if self.slo_monitor:
                execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
                await self._record_slo_metrics("stress_test", execution_time, success=True)

            logger.info(f"Stress test '{scenario_name}' completed: P&L = {total_pnl:,.0f}")
            return result

        except Exception as e:
            logger.error(f"Error in stress test '{scenario_name}': {e}")
            if self.slo_monitor:
                execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
                await self._record_slo_metrics("stress_test", execution_time, success=False)
            raise

    async def run_all_stress_tests(self) -> list[StressTestResult]:
        """Run all configured stress tests"""
        results = []
        for scenario_name in self.stress_scenarios.keys():
            try:
                result = await self.run_stress_test(scenario_name)
                results.append(result)
            except Exception as e:
                logger.error(f"Error running stress test {scenario_name}: {e}")
        return results

    def add_alert_callback(self, callback: Callable[[RiskAlert], None]) -> None:
        """Add alert callback function"""
        self.alert_callbacks.append(callback)

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert"""
        if alert_id in self.active_alerts:
            self.active_alerts[alert_id].acknowledged = True
            return True
        return False

    async def _record_slo_metrics(self, operation: str, execution_time: float, success: bool) -> None:
        """Record SLO metrics"""
        if not self.slo_monitor:
            return

        try:
            await self.slo_monitor.record_metric(
                service_name="realtime_risk_analytics",
                operation_name=operation,
                latency_ms=execution_time,
                success=success,
                metadata={
                    'positions_count': len(self.positions),
                    'alerts_count': len(self.active_alerts),
                    'current_var': self.current_var,
                    'leverage': self.current_exposure.leverage
                }
            )
        except Exception as e:
            logger.error(f"Error recording SLO metrics: {e}")

    def get_analytics_summary(self) -> dict[str, Any]:
        """Get comprehensive analytics summary"""
        return {
            'exposure_metrics': {
                'gross_exposure': self.current_exposure.gross_exposure,
                'net_exposure': self.current_exposure.net_exposure,
                'leverage': self.current_exposure.leverage,
                'beta_exposure': self.current_exposure.beta_exposure,
                'sector_exposure': dict(self.current_exposure.sector_exposure),
                'region_exposure': dict(self.current_exposure.region_exposure)
            },
            'risk_metrics': {
                'var_95_1d': self.current_var,
                'cvar_95_1d': self.current_cvar,
                'avg_correlation': self.current_correlation.avg_correlation,
                'max_correlation': self.current_correlation.max_correlation,
                'eigen_risk': self.current_correlation.eigen_risk,
                'concentration_ratio': self.current_correlation.concentration_ratio
            },
            'risk_attribution': {
                'position_risk': dict(self.risk_attribution.position_risk),
                'sector_risk': dict(self.risk_attribution.sector_risk),
                'systematic_risk': self.risk_attribution.systematic_risk,
                'idiosyncratic_risk': self.risk_attribution.idiosyncratic_risk
            },
            'alerts': {
                'active_count': len([a for a in self.active_alerts.values() if not a.acknowledged]),
                'total_count': len(self.alert_history),
                'recent_alerts': [
                    {
                        'id': alert.id,
                        'event_type': alert.event_type.value,
                        'priority': alert.priority.name,
                        'title': alert.title,
                        'timestamp': alert.timestamp.isoformat()
                    } for alert in list(self.alert_history)[-10:]
                ]
            },
            'stress_tests': {
                'scenarios_count': len(self.stress_scenarios),
                'results_count': len(self.stress_results),
                'latest_results': [
                    {
                        'scenario': result.scenario_name,
                        'pnl': result.portfolio_pnl,
                        'positions_affected': result.positions_affected,
                        'timestamp': result.timestamp.isoformat()
                    } for result in list(self.stress_results)[-5:]
                ]
            },
            'system_stats': {
                'positions_tracked': len(self.positions),
                'price_streams': len(self.price_stream),
                'portfolio_history_length': len(self.portfolio_values),
                'return_history_length': len(self.portfolio_returns)
            }
        }

    def start_monitoring(self) -> None:
        """Start real-time monitoring"""
        if self.running:
            logger.warning("Risk analytics already running")
            return

        self.running = True
        self.update_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.update_thread.start()
        logger.info("Real-time risk analytics monitoring started")

    def stop_monitoring(self) -> None:
        """Stop real-time monitoring"""
        self.running = False
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=5)
        logger.info("Real-time risk analytics monitoring stopped")

    def _monitoring_loop(self) -> None:
        """Background monitoring loop"""
        while self.running:
            try:
                # Periodic tasks
                asyncio.run(self._periodic_tasks())

                # Sleep for update interval
                time.sleep(self.update_frequency)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.update_frequency)

    async def _periodic_tasks(self) -> None:
        """Perform periodic analytics tasks"""
        try:
            # Auto-resolve old alerts
            current_time = datetime.now(UTC)
            for alert in list(self.active_alerts.values()):
                if (current_time - alert.timestamp).total_seconds() > 3600:  # 1 hour
                    alert.auto_resolved = True
                    del self.active_alerts[alert.id]

            # Run periodic stress tests (every 5 minutes)
            if int(time.time()) % 300 == 0:  # Every 5 minutes
                await self.run_stress_test('market_crash')  # Run one scenario periodically

        except Exception as e:
            logger.error(f"Error in periodic tasks: {e}")


# Example usage and testing
if __name__ == "__main__":
    async def test_risk_analytics():
        """Test Real-Time Risk Analytics"""
        print("📊 Testing Real-Time Risk Analytics")
        print("=" * 50)

        # Initialize analytics
        analytics = RealTimeRiskAnalytics(update_frequency=1)

        # Add alert callback
        def alert_handler(alert: RiskAlert):
            print(f"🚨 ALERT: [{alert.priority.name}] {alert.title}")

        analytics.add_alert_callback(alert_handler)

        # Sample position data
        positions = {
            'AAPL': {
                'quantity': 100,
                'price': 150.0,
                'market_value': 15000,
                'sector': 'Technology',
                'beta': 1.2,
                'volatility': 0.25,
                'currency': 'USD',
                'region': 'US'
            },
            'GOOGL': {
                'quantity': 50,
                'price': 2500.0,
                'market_value': 125000,
                'sector': 'Technology',
                'beta': 1.1,
                'volatility': 0.28,
                'currency': 'USD',
                'region': 'US'
            },
            'TSLA': {
                'quantity': 200,
                'price': 200.0,
                'market_value': 40000,
                'sector': 'Automotive',
                'beta': 1.8,
                'volatility': 0.45,
                'currency': 'USD',
                'region': 'US'
            }
        }

        # Simulate price updates to build history
        print("📈 Simulating price updates...")
        for _i in range(50):
            # Add some noise to prices
            for symbol in positions:
                price_change = np.random.normal(0, 0.01)  # 1% daily vol
                positions[symbol]['price'] *= (1 + price_change)
                positions[symbol]['market_value'] = (positions[symbol]['quantity'] *
                                                   positions[symbol]['price'])

            await analytics.update_positions(positions)
            await asyncio.sleep(0.1)  # Small delay to simulate real-time

        # Get analytics summary
        summary = analytics.get_analytics_summary()

        print("\n📊 Analytics Summary:")
        for category, metrics in summary.items():
            print(f"\n{category.upper()}:")
            if isinstance(metrics, dict):
                for key, value in metrics.items():
                    if isinstance(value, float):
                        print(f"  {key}: {value:.4f}")
                    elif isinstance(value, dict) and len(value) <= 5 or isinstance(value, list) and len(value) <= 3:
                        print(f"  {key}: {value}")
                    else:
                        print(f"  {key}: {type(value).__name__}")

        # Run stress tests
        print("\n🧪 Running Stress Tests:")
        stress_results = await analytics.run_all_stress_tests()
        for result in stress_results:
            print(f"  {result.scenario_name}: P&L = ${result.portfolio_pnl:,.0f}")

        print("\n✅ Real-Time Risk Analytics test completed!")

        return analytics

    # Run test
    analytics = asyncio.run(test_risk_analytics())
