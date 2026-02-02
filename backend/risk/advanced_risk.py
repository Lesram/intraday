"""
Advanced Risk Management System for Trading Platform.

Provides institutional-grade risk controls:
- Portfolio-level correlation risk
- Stress testing with historical scenarios
- Dynamic limit adjustment based on volatility
- Greeks-based options risk (delta, gamma, vega)
- Intraday drawdown monitoring
- Sector/factor concentration limits

This module extends the base risk manager with advanced capabilities
required for professional trading operations.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import numpy as np

from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


class RiskLevel(Enum):
    """Risk severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class StressScenario(Enum):
    """Pre-defined stress testing scenarios."""

    MARKET_CRASH_2008 = "2008_financial_crisis"
    FLASH_CRASH_2010 = "2010_flash_crash"
    COVID_CRASH_2020 = "2020_covid_crash"
    RATE_SHOCK_UP = "rate_shock_up_200bps"
    RATE_SHOCK_DOWN = "rate_shock_down_100bps"
    VOLATILITY_SPIKE = "vix_spike_50pct"
    SECTOR_ROTATION = "sector_rotation"
    LIQUIDITY_CRISIS = "liquidity_crisis"
    CUSTOM = "custom"


@dataclass
class CorrelationRisk:
    """Portfolio correlation risk metrics."""

    average_correlation: float
    max_pairwise_correlation: float
    correlation_cluster_count: int
    effective_positions: float  # Diversification-adjusted position count
    concentration_hhi: float  # Herfindahl-Hirschman Index
    risk_contribution: dict[str, float] = field(default_factory=dict)


@dataclass
class StressTestResult:
    """Results from a stress test scenario."""

    scenario: StressScenario
    portfolio_loss_pct: float
    worst_position: str
    worst_position_loss_pct: float
    positions_breaching_limits: list[str]
    margin_call_triggered: bool
    estimated_recovery_days: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DrawdownMetrics:
    """Intraday and historical drawdown tracking."""

    current_drawdown_pct: float
    max_drawdown_today_pct: float
    max_drawdown_mtd_pct: float
    max_drawdown_ytd_pct: float
    drawdown_duration_minutes: int
    recovery_progress_pct: float
    peak_equity: float
    trough_equity: float


@dataclass
class DynamicLimits:
    """Volatility-adjusted risk limits."""

    base_position_limit: float
    adjusted_position_limit: float
    base_concentration_limit: float
    adjusted_concentration_limit: float
    volatility_multiplier: float
    regime: str  # "low_vol", "normal", "high_vol", "crisis"
    limits_tightened: bool
    adjustment_reason: str


@dataclass
class GreeksExposure:
    """Options Greeks portfolio exposure."""

    total_delta: float
    total_gamma: float
    total_vega: float
    total_theta: float
    total_rho: float
    delta_by_underlying: dict[str, float] = field(default_factory=dict)
    gamma_by_underlying: dict[str, float] = field(default_factory=dict)


@dataclass
class SectorExposure:
    """Sector concentration metrics."""

    sector_weights: dict[str, float]
    largest_sector: str
    largest_sector_weight: float
    sector_hhi: float
    factor_exposures: dict[str, float] = field(default_factory=dict)


class VolatilityRegimeDetector:
    """
    Detects market volatility regimes for dynamic limit adjustment.

    Regimes:
    - low_vol: VIX < 15 or realized vol < 10%
    - normal: VIX 15-25 or realized vol 10-20%
    - high_vol: VIX 25-40 or realized vol 20-35%
    - crisis: VIX > 40 or realized vol > 35%
    """

    def __init__(self):
        self._historical_vol: list[float] = []
        self._vix_history: list[float] = []
        self._current_regime = "normal"

    def update(self, realized_vol: float, vix: float | None = None):
        """Update regime detector with new data."""
        self._historical_vol.append(realized_vol)
        if len(self._historical_vol) > 252:  # Keep ~1 year
            self._historical_vol.pop(0)

        if vix is not None:
            self._vix_history.append(vix)
            if len(self._vix_history) > 252:
                self._vix_history.pop(0)

        self._current_regime = self._classify_regime(realized_vol, vix)

    def _classify_regime(self, realized_vol: float, vix: float | None) -> str:
        """Classify current volatility regime."""
        # Use VIX if available, otherwise realized vol
        indicator = vix if vix is not None else realized_vol * 100

        if indicator < 15:
            return "low_vol"
        elif indicator < 25:
            return "normal"
        elif indicator < 40:
            return "high_vol"
        else:
            return "crisis"

    @property
    def current_regime(self) -> str:
        """Get current volatility regime."""
        return self._current_regime

    def get_limit_multiplier(self) -> float:
        """Get position limit multiplier based on regime."""
        multipliers = {
            "low_vol": 1.2,    # Can take more risk
            "normal": 1.0,     # Base limits
            "high_vol": 0.7,   # Tighten limits
            "crisis": 0.4,     # Severely tighten limits
        }
        return multipliers.get(self._current_regime, 1.0)


class CorrelationRiskCalculator:
    """
    Calculates portfolio correlation risk metrics.

    Uses rolling correlation matrices to assess:
    - Average pairwise correlation
    - Correlation clustering
    - Effective number of positions
    - Risk contribution by position
    """

    def __init__(self, lookback_days: int = 60):
        self.lookback_days = lookback_days
        self._returns_history: dict[str, list[float]] = {}

    def update_returns(self, symbol: str, daily_return: float):
        """Update returns history for a symbol."""
        if symbol not in self._returns_history:
            self._returns_history[symbol] = []

        self._returns_history[symbol].append(daily_return)

        # Keep only lookback window
        if len(self._returns_history[symbol]) > self.lookback_days:
            self._returns_history[symbol].pop(0)

    def calculate(
        self,
        positions: dict[str, float],  # symbol -> weight
    ) -> CorrelationRisk:
        """Calculate correlation risk metrics."""
        symbols = list(positions.keys())
        n = len(symbols)

        if n < 2:
            return CorrelationRisk(
                average_correlation=0.0,
                max_pairwise_correlation=0.0,
                correlation_cluster_count=1,
                effective_positions=float(n),
                concentration_hhi=1.0 if n == 1 else 0.0,
                risk_contribution={s: 1.0 / n if n > 0 else 0.0 for s in symbols},
            )

        # Build correlation matrix
        corr_matrix = self._build_correlation_matrix(symbols)

        # Calculate metrics
        avg_corr = self._average_correlation(corr_matrix)
        max_corr = self._max_pairwise_correlation(corr_matrix)
        clusters = self._count_correlation_clusters(corr_matrix, threshold=0.7)

        # Effective positions (diversification-adjusted)
        weights = np.array([positions.get(s, 0.0) for s in symbols])
        weights = weights / (np.sum(np.abs(weights)) + 1e-10)
        effective_n = self._effective_positions(weights, corr_matrix)

        # Herfindahl-Hirschman Index
        hhi = float(np.sum(weights ** 2))

        # Risk contribution
        risk_contrib = self._marginal_risk_contribution(weights, corr_matrix, symbols)

        return CorrelationRisk(
            average_correlation=avg_corr,
            max_pairwise_correlation=max_corr,
            correlation_cluster_count=clusters,
            effective_positions=effective_n,
            concentration_hhi=hhi,
            risk_contribution=risk_contrib,
        )

    def _build_correlation_matrix(self, symbols: list[str]) -> np.ndarray:
        """Build correlation matrix from returns history."""
        n = len(symbols)
        corr_matrix = np.eye(n)

        for i in range(n):
            for j in range(i + 1, n):
                returns_i = self._returns_history.get(symbols[i], [])
                returns_j = self._returns_history.get(symbols[j], [])

                # Need overlapping data
                min_len = min(len(returns_i), len(returns_j))
                if min_len >= 20:  # Minimum for correlation
                    corr = np.corrcoef(
                        returns_i[-min_len:],
                        returns_j[-min_len:],
                    )[0, 1]
                    corr = 0.0 if np.isnan(corr) else corr
                else:
                    corr = 0.3  # Default moderate correlation

                corr_matrix[i, j] = corr
                corr_matrix[j, i] = corr

        return corr_matrix

    def _average_correlation(self, corr_matrix: np.ndarray) -> float:
        """Calculate average off-diagonal correlation."""
        n = corr_matrix.shape[0]
        if n < 2:
            return 0.0

        # Extract upper triangle (excluding diagonal)
        upper = corr_matrix[np.triu_indices(n, k=1)]
        return float(np.mean(upper)) if len(upper) > 0 else 0.0

    def _max_pairwise_correlation(self, corr_matrix: np.ndarray) -> float:
        """Find maximum pairwise correlation."""
        n = corr_matrix.shape[0]
        if n < 2:
            return 0.0

        upper = corr_matrix[np.triu_indices(n, k=1)]
        return float(np.max(np.abs(upper))) if len(upper) > 0 else 0.0

    def _count_correlation_clusters(
        self,
        corr_matrix: np.ndarray,
        threshold: float = 0.7,
    ) -> int:
        """Count clusters of highly correlated assets."""
        n = corr_matrix.shape[0]
        if n < 2:
            return 1

        # Simple clustering: count connected components with corr > threshold
        visited = set()
        clusters = 0

        for i in range(n):
            if i not in visited:
                clusters += 1
                # BFS to find all connected nodes
                queue = [i]
                while queue:
                    node = queue.pop(0)
                    if node not in visited:
                        visited.add(node)
                        for j in range(n):
                            if j not in visited and abs(corr_matrix[node, j]) > threshold:
                                queue.append(j)

        return clusters

    def _effective_positions(
        self,
        weights: np.ndarray,
        corr_matrix: np.ndarray,
    ) -> float:
        """Calculate effective number of positions accounting for correlation."""
        n = len(weights)
        if n == 0:
            return 0.0

        # Covariance-weighted effective N
        # Simplified: 1 / sum(w_i * w_j * corr_ij)
        weighted_corr = 0.0
        for i in range(n):
            for j in range(n):
                weighted_corr += abs(weights[i]) * abs(weights[j]) * corr_matrix[i, j]

        if weighted_corr < 1e-10:
            return float(n)

        return 1.0 / weighted_corr

    def _marginal_risk_contribution(
        self,
        weights: np.ndarray,
        corr_matrix: np.ndarray,
        symbols: list[str],
    ) -> dict[str, float]:
        """Calculate marginal risk contribution by position."""
        n = len(weights)
        if n == 0:
            return {}

        # Assume equal volatility for simplicity
        # In production, would use actual volatilities
        vol = np.ones(n) * 0.2

        # Covariance matrix
        cov = np.outer(vol, vol) * corr_matrix

        # Portfolio variance
        port_var = float(weights @ cov @ weights)
        if port_var < 1e-10:
            return {s: 1.0 / n for s in symbols}

        # Marginal contribution to risk
        mctr = cov @ weights / np.sqrt(port_var)

        # Risk contribution = weight * MCTR
        rc = weights * mctr
        total_rc = np.sum(np.abs(rc))

        if total_rc < 1e-10:
            return {s: 1.0 / n for s in symbols}

        return {
            symbols[i]: float(abs(rc[i]) / total_rc)
            for i in range(n)
        }


class StressTestEngine:
    """
    Stress testing engine with historical and hypothetical scenarios.

    Applies historical shock factors or custom scenarios to
    estimate portfolio losses under extreme conditions.
    """

    # Historical scenario shock factors (as decimal returns)
    SCENARIO_SHOCKS = {
        StressScenario.MARKET_CRASH_2008: {
            "equity": -0.55,
            "bond": 0.05,
            "commodity": -0.40,
            "currency": 0.10,
            "volatility": 3.0,
        },
        StressScenario.FLASH_CRASH_2010: {
            "equity": -0.10,
            "bond": 0.02,
            "commodity": -0.05,
            "currency": 0.0,
            "volatility": 2.0,
        },
        StressScenario.COVID_CRASH_2020: {
            "equity": -0.35,
            "bond": 0.10,
            "commodity": -0.50,
            "currency": 0.05,
            "volatility": 4.0,
        },
        StressScenario.RATE_SHOCK_UP: {
            "equity": -0.15,
            "bond": -0.20,
            "commodity": 0.0,
            "currency": 0.05,
            "volatility": 1.5,
        },
        StressScenario.RATE_SHOCK_DOWN: {
            "equity": 0.10,
            "bond": 0.15,
            "commodity": 0.0,
            "currency": -0.02,
            "volatility": 0.8,
        },
        StressScenario.VOLATILITY_SPIKE: {
            "equity": -0.08,
            "bond": 0.02,
            "commodity": -0.05,
            "currency": 0.0,
            "volatility": 2.5,
        },
        StressScenario.SECTOR_ROTATION: {
            "equity": 0.0,  # Net zero but high dispersion
            "bond": 0.0,
            "commodity": 0.0,
            "currency": 0.0,
            "volatility": 1.2,
        },
        StressScenario.LIQUIDITY_CRISIS: {
            "equity": -0.25,
            "bond": -0.10,
            "commodity": -0.30,
            "currency": 0.0,
            "volatility": 2.5,
        },
    }

    def __init__(
        self,
        margin_requirement: float = 0.25,
        max_acceptable_loss: float = 0.20,
    ):
        self.margin_requirement = margin_requirement
        self.max_acceptable_loss = max_acceptable_loss
        self._asset_classifications: dict[str, str] = {}  # symbol -> asset class

    def classify_asset(self, symbol: str, asset_class: str):
        """Classify an asset for stress testing."""
        self._asset_classifications[symbol] = asset_class

    def run_scenario(
        self,
        scenario: StressScenario,
        positions: dict[str, float],  # symbol -> market value
        portfolio_value: float,
        custom_shocks: dict[str, float] | None = None,
    ) -> StressTestResult:
        """Run a stress test scenario."""
        if scenario == StressScenario.CUSTOM and custom_shocks is None:
            raise ValueError("Custom scenario requires custom_shocks parameter")

        shocks = custom_shocks if scenario == StressScenario.CUSTOM else self.SCENARIO_SHOCKS.get(scenario, {})

        # Calculate position losses
        position_losses: dict[str, float] = {}
        total_loss = 0.0

        for symbol, value in positions.items():
            asset_class = self._asset_classifications.get(symbol, "equity")
            shock = shocks.get(asset_class, shocks.get("equity", -0.20))

            loss = value * shock
            position_losses[symbol] = loss
            total_loss += loss

        # Find worst position
        worst_symbol = min(position_losses.keys(), key=lambda s: position_losses[s]) if position_losses else ""
        worst_loss = position_losses.get(worst_symbol, 0.0)
        worst_loss_pct = worst_loss / positions.get(worst_symbol, 1.0) if positions.get(worst_symbol) else 0.0

        # Portfolio loss percentage
        portfolio_loss_pct = total_loss / portfolio_value if portfolio_value > 0 else 0.0

        # Check for limit breaches
        breaching = [
            s for s, loss in position_losses.items()
            if abs(loss / positions.get(s, 1.0)) > self.max_acceptable_loss
        ]

        # Margin call check
        margin_call = abs(portfolio_loss_pct) > (1 - self.margin_requirement)

        # Estimate recovery (rough heuristic)
        recovery_days = int(abs(portfolio_loss_pct) * 252 / 0.10)  # Assume 10% annual recovery

        return StressTestResult(
            scenario=scenario,
            portfolio_loss_pct=portfolio_loss_pct,
            worst_position=worst_symbol,
            worst_position_loss_pct=worst_loss_pct,
            positions_breaching_limits=breaching,
            margin_call_triggered=margin_call,
            estimated_recovery_days=min(recovery_days, 1000),
            details={
                "position_losses": position_losses,
                "shocks_applied": shocks,
                "total_loss": total_loss,
            },
        )

    def run_all_scenarios(
        self,
        positions: dict[str, float],
        portfolio_value: float,
    ) -> list[StressTestResult]:
        """Run all predefined stress scenarios."""
        results = []

        for scenario in StressScenario:
            if scenario != StressScenario.CUSTOM:
                result = self.run_scenario(scenario, positions, portfolio_value)
                results.append(result)

        return results


class DrawdownMonitor:
    """
    Monitors intraday and historical drawdowns.

    Tracks:
    - Real-time drawdown from daily peak
    - Maximum drawdown this session/day/month/year
    - Time in drawdown
    - Recovery progress
    """

    def __init__(self):
        self._peak_equity: float = 0.0
        self._trough_equity: float = float("inf")
        self._current_equity: float = 0.0

        self._peak_timestamp: datetime | None = None
        self._trough_timestamp: datetime | None = None

        self._max_dd_today: float = 0.0
        self._max_dd_mtd: float = 0.0
        self._max_dd_ytd: float = 0.0

        self._daily_peak: float = 0.0
        self._last_reset_date: datetime | None = None

    def update(self, equity: float):
        """Update with new equity value."""
        now = datetime.now(UTC)

        # Check for new day
        if self._last_reset_date is None or self._last_reset_date.date() != now.date():
            self._daily_peak = equity
            self._max_dd_today = 0.0
            self._last_reset_date = now

        self._current_equity = equity

        # Update peak
        if equity > self._peak_equity:
            self._peak_equity = equity
            self._peak_timestamp = now
            self._trough_equity = equity
            self._trough_timestamp = now

        self._daily_peak = max(self._daily_peak, equity)

        # Update trough
        if equity < self._trough_equity:
            self._trough_equity = equity
            self._trough_timestamp = now

        # Calculate drawdowns
        if self._peak_equity > 0:
            current_dd = (self._peak_equity - equity) / self._peak_equity
            daily_dd = (self._daily_peak - equity) / self._daily_peak if self._daily_peak > 0 else 0.0

            self._max_dd_today = max(self._max_dd_today, daily_dd)
            self._max_dd_mtd = max(self._max_dd_mtd, current_dd)
            self._max_dd_ytd = max(self._max_dd_ytd, current_dd)

    def get_metrics(self) -> DrawdownMetrics:
        """Get current drawdown metrics."""
        current_dd = 0.0
        if self._peak_equity > 0:
            current_dd = (self._peak_equity - self._current_equity) / self._peak_equity

        # Duration in drawdown
        duration_minutes = 0
        if self._peak_timestamp and self._current_equity < self._peak_equity:
            duration = datetime.now(UTC) - self._peak_timestamp
            duration_minutes = int(duration.total_seconds() / 60)

        # Recovery progress
        recovery_pct = 0.0
        if self._peak_equity > self._trough_equity:
            recovery_range = self._peak_equity - self._trough_equity
            recovered = self._current_equity - self._trough_equity
            recovery_pct = max(0.0, min(1.0, recovered / recovery_range))

        return DrawdownMetrics(
            current_drawdown_pct=current_dd,
            max_drawdown_today_pct=self._max_dd_today,
            max_drawdown_mtd_pct=self._max_dd_mtd,
            max_drawdown_ytd_pct=self._max_dd_ytd,
            drawdown_duration_minutes=duration_minutes,
            recovery_progress_pct=recovery_pct,
            peak_equity=self._peak_equity,
            trough_equity=self._trough_equity,
        )

    def reset_monthly(self):
        """Reset monthly tracking."""
        self._max_dd_mtd = 0.0

    def reset_yearly(self):
        """Reset yearly tracking."""
        self._max_dd_ytd = 0.0
        self._max_dd_mtd = 0.0


class AdvancedRiskManager:
    """
    Advanced risk management orchestrator.

    Combines all advanced risk capabilities:
    - Correlation-based risk monitoring
    - Stress testing
    - Dynamic limit adjustment
    - Drawdown monitoring
    - Sector concentration limits

    Usage:
        risk = AdvancedRiskManager(
            base_position_limit=100000,
            max_concentration=0.15,
        )

        # Update with market data
        risk.update_market_data(realized_vol=0.18, vix=22.5)

        # Get dynamic limits
        limits = risk.get_dynamic_limits()

        # Run stress tests
        results = risk.run_stress_tests(positions, portfolio_value)
    """

    def __init__(
        self,
        base_position_limit: float = 100000,
        max_concentration: float = 0.15,
        max_sector_weight: float = 0.30,
        drawdown_limit: float = 0.10,
    ):
        self.base_position_limit = base_position_limit
        self.max_concentration = max_concentration
        self.max_sector_weight = max_sector_weight
        self.drawdown_limit = drawdown_limit

        # Components
        self.volatility_detector = VolatilityRegimeDetector()
        self.correlation_calculator = CorrelationRiskCalculator()
        self.stress_engine = StressTestEngine()
        self.drawdown_monitor = DrawdownMonitor()

        # State
        self._sector_mapping: dict[str, str] = {}
        self._current_limits: DynamicLimits | None = None

    def set_sector(self, symbol: str, sector: str):
        """Set sector classification for a symbol."""
        self._sector_mapping[symbol] = sector
        self.stress_engine.classify_asset(symbol, "equity")  # Default to equity

    def update_market_data(
        self,
        realized_vol: float,
        vix: float | None = None,
    ):
        """Update with current market volatility data."""
        self.volatility_detector.update(realized_vol, vix)
        self._recalculate_limits()

    def update_returns(self, symbol: str, daily_return: float):
        """Update returns history for correlation calculation."""
        self.correlation_calculator.update_returns(symbol, daily_return)

    def update_equity(self, equity: float):
        """Update portfolio equity for drawdown monitoring."""
        self.drawdown_monitor.update(equity)

    def _recalculate_limits(self):
        """Recalculate dynamic limits based on regime."""
        multiplier = self.volatility_detector.get_limit_multiplier()
        regime = self.volatility_detector.current_regime

        adjusted_position = self.base_position_limit * multiplier
        adjusted_concentration = min(self.max_concentration * multiplier, 0.25)

        tightened = multiplier < 1.0

        reason = f"Volatility regime: {regime}"
        if tightened:
            reason += f" - limits reduced by {(1 - multiplier) * 100:.0f}%"

        self._current_limits = DynamicLimits(
            base_position_limit=self.base_position_limit,
            adjusted_position_limit=adjusted_position,
            base_concentration_limit=self.max_concentration,
            adjusted_concentration_limit=adjusted_concentration,
            volatility_multiplier=multiplier,
            regime=regime,
            limits_tightened=tightened,
            adjustment_reason=reason,
        )

    def get_dynamic_limits(self) -> DynamicLimits:
        """Get current volatility-adjusted limits."""
        if self._current_limits is None:
            self._recalculate_limits()
        return self._current_limits  # type: ignore

    def get_correlation_risk(
        self,
        positions: dict[str, float],
    ) -> CorrelationRisk:
        """Calculate portfolio correlation risk."""
        return self.correlation_calculator.calculate(positions)

    def get_drawdown_metrics(self) -> DrawdownMetrics:
        """Get current drawdown metrics."""
        return self.drawdown_monitor.get_metrics()

    def run_stress_tests(
        self,
        positions: dict[str, float],
        portfolio_value: float,
    ) -> list[StressTestResult]:
        """Run all stress test scenarios."""
        return self.stress_engine.run_all_scenarios(positions, portfolio_value)

    def get_sector_exposure(
        self,
        positions: dict[str, float],
    ) -> SectorExposure:
        """Calculate sector concentration metrics."""
        sector_values: dict[str, float] = {}
        total_value = sum(abs(v) for v in positions.values())

        for symbol, value in positions.items():
            sector = self._sector_mapping.get(symbol, "Other")
            sector_values[sector] = sector_values.get(sector, 0.0) + abs(value)

        # Calculate weights
        sector_weights = {
            s: v / total_value if total_value > 0 else 0.0
            for s, v in sector_values.items()
        }

        # Find largest sector
        largest = max(sector_weights.items(), key=lambda x: x[1]) if sector_weights else ("None", 0.0)

        # HHI
        hhi = sum(w ** 2 for w in sector_weights.values())

        return SectorExposure(
            sector_weights=sector_weights,
            largest_sector=largest[0],
            largest_sector_weight=largest[1],
            sector_hhi=hhi,
        )

    def check_risk_limits(
        self,
        positions: dict[str, float],
        portfolio_value: float,
    ) -> dict[str, Any]:
        """
        Comprehensive risk limit check.

        Returns dict with all risk metrics and any violations.
        """
        limits = self.get_dynamic_limits()
        correlation = self.get_correlation_risk(positions)
        drawdown = self.get_drawdown_metrics()
        sector = self.get_sector_exposure(positions)

        violations = []

        # Check drawdown limit
        if drawdown.current_drawdown_pct > self.drawdown_limit:
            violations.append({
                "type": "drawdown",
                "current": drawdown.current_drawdown_pct,
                "limit": self.drawdown_limit,
                "severity": RiskLevel.CRITICAL.value,
            })

        # Check sector concentration
        if sector.largest_sector_weight > self.max_sector_weight:
            violations.append({
                "type": "sector_concentration",
                "sector": sector.largest_sector,
                "current": sector.largest_sector_weight,
                "limit": self.max_sector_weight,
                "severity": RiskLevel.HIGH.value,
            })

        # Check correlation clustering
        if correlation.average_correlation > 0.6:
            violations.append({
                "type": "high_correlation",
                "current": correlation.average_correlation,
                "limit": 0.6,
                "severity": RiskLevel.MEDIUM.value,
            })

        # Determine overall risk level
        if any(v["severity"] == RiskLevel.CRITICAL.value for v in violations):
            overall_level = RiskLevel.CRITICAL
        elif any(v["severity"] == RiskLevel.HIGH.value for v in violations):
            overall_level = RiskLevel.HIGH
        elif violations:
            overall_level = RiskLevel.MEDIUM
        else:
            overall_level = RiskLevel.LOW

        return {
            "risk_level": overall_level.value,
            "violations": violations,
            "limits": {
                "position_limit": limits.adjusted_position_limit,
                "concentration_limit": limits.adjusted_concentration_limit,
                "regime": limits.regime,
            },
            "correlation": {
                "average": correlation.average_correlation,
                "max_pairwise": correlation.max_pairwise_correlation,
                "effective_positions": correlation.effective_positions,
            },
            "drawdown": {
                "current": drawdown.current_drawdown_pct,
                "max_today": drawdown.max_drawdown_today_pct,
                "duration_minutes": drawdown.drawdown_duration_minutes,
            },
            "sector": {
                "largest": sector.largest_sector,
                "largest_weight": sector.largest_sector_weight,
                "hhi": sector.sector_hhi,
            },
        }


# Factory function
def create_advanced_risk_manager(**kwargs) -> AdvancedRiskManager:
    """Create an advanced risk manager with default settings."""
    return AdvancedRiskManager(**kwargs)
