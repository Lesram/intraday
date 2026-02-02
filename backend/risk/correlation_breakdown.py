"""
Correlation Breakdown Detection (M-45)

Detects when asset correlations deviate from historical norms, indicating:
- Market regime changes
- Potential arbitrage opportunities
- Portfolio risk changes
- Sector rotation events

Builds on the existing CorrelationRiskCalculator in advanced_risk.py.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
import logging

import numpy as np

logger = logging.getLogger(__name__)


class CorrelationBreakdownType(Enum):
    """Types of correlation breakdown events."""
    CORRELATION_SPIKE = "correlation_spike"       # Sudden increase in correlation
    CORRELATION_COLLAPSE = "correlation_collapse"  # Sudden decrease in correlation
    REGIME_CHANGE = "regime_change"               # Sustained shift in correlation
    DECOUPLING = "decoupling"                     # Previously correlated assets diverge
    CONVERGENCE = "convergence"                   # Previously uncorrelated assets converge


class AlertSeverity(Enum):
    """Severity level for correlation alerts."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class CorrelationBreakdown:
    """Represents a detected correlation breakdown event."""
    breakdown_id: str
    breakdown_type: CorrelationBreakdownType
    severity: AlertSeverity
    
    # Asset pair information
    symbol_a: str
    symbol_b: str
    
    # Correlation metrics
    historical_correlation: float     # Long-term average
    current_correlation: float        # Recent window
    correlation_change: float         # Absolute change
    z_score: float                    # How many std devs from normal
    
    # Timing
    detected_at: datetime
    lookback_days: int
    recent_window_days: int
    
    # Context
    description: str
    recommendations: list[str] = field(default_factory=list)
    
    # Metadata
    affected_positions: list[str] = field(default_factory=list)
    portfolio_impact: float = 0.0  # Estimated impact on portfolio risk


@dataclass
class CorrelationRegime:
    """Represents a correlation regime for an asset pair."""
    symbol_a: str
    symbol_b: str
    
    # Current regime
    current_correlation: float
    correlation_std: float
    regime_label: str  # "positive", "negative", "uncorrelated"
    
    # Stability metrics
    regime_duration_days: int
    stability_score: float  # 0-1, higher is more stable
    
    # Historical context
    historical_min: float
    historical_max: float
    historical_mean: float


class CorrelationBreakdownDetector:
    """
    Detects correlation breakdown events across assets.
    
    Monitors for:
    - Sudden correlation spikes (flight to safety)
    - Correlation collapses (diversification loss)
    - Regime changes (sustained correlation shifts)
    - Decoupling events (pairs diverging)
    
    Usage:
        detector = CorrelationBreakdownDetector(
            lookback_days=252,
            recent_window=20,
            z_score_threshold=2.0,
        )
        
        # Update with returns
        detector.update_returns({
            "AAPL": 0.015,
            "GOOGL": 0.012,
            "SPY": 0.008,
        })
        
        # Check for breakdowns
        breakdowns = detector.detect_breakdowns()
    """
    
    def __init__(
        self,
        lookback_days: int = 252,
        recent_window: int = 20,
        z_score_threshold: float = 2.0,
        change_threshold: float = 0.30,
        min_history_days: int = 60,
    ):
        """
        Initialize correlation breakdown detector.
        
        Args:
            lookback_days: Days of history for baseline correlation
            recent_window: Days for recent correlation calculation
            z_score_threshold: Z-score threshold for alerting
            change_threshold: Absolute correlation change threshold
            min_history_days: Minimum history required for detection
        """
        self.lookback_days = lookback_days
        self.recent_window = recent_window
        self.z_score_threshold = z_score_threshold
        self.change_threshold = change_threshold
        self.min_history_days = min_history_days
        
        # Returns history
        self._returns: dict[str, list[float]] = {}
        self._timestamps: list[datetime] = []
        
        # Baseline correlations
        self._baseline_correlations: dict[tuple[str, str], float] = {}
        self._correlation_history: dict[tuple[str, str], list[float]] = {}
        
        # Active breakdowns
        self._active_breakdowns: dict[str, CorrelationBreakdown] = {}
        
        # Pair-specific monitoring
        self._monitored_pairs: set[tuple[str, str]] = set()
    
    def update_returns(
        self,
        returns: dict[str, float],
        timestamp: datetime | None = None,
    ) -> None:
        """
        Update with new daily returns.
        
        Args:
            returns: Dictionary of symbol -> daily return
            timestamp: Optional timestamp (defaults to now)
        """
        timestamp = timestamp or datetime.now(UTC)
        self._timestamps.append(timestamp)
        
        for symbol, ret in returns.items():
            if symbol not in self._returns:
                self._returns[symbol] = []
            self._returns[symbol].append(ret)
            
            # Trim to lookback window
            if len(self._returns[symbol]) > self.lookback_days:
                self._returns[symbol] = self._returns[symbol][-self.lookback_days:]
        
        # Trim timestamps
        if len(self._timestamps) > self.lookback_days:
            self._timestamps = self._timestamps[-self.lookback_days:]
    
    def add_monitored_pair(self, symbol_a: str, symbol_b: str) -> None:
        """Add a pair to explicit monitoring list."""
        pair = tuple(sorted([symbol_a, symbol_b]))
        self._monitored_pairs.add(pair)
    
    def detect_breakdowns(
        self,
        symbols: list[str] | None = None,
    ) -> list[CorrelationBreakdown]:
        """
        Detect correlation breakdowns across symbols.
        
        Args:
            symbols: Optional list of symbols to check (defaults to all)
            
        Returns:
            List of detected breakdown events
        """
        if symbols is None:
            symbols = list(self._returns.keys())
        
        if len(symbols) < 2:
            return []
        
        breakdowns: list[CorrelationBreakdown] = []
        
        # Check all pairs
        for i, symbol_a in enumerate(symbols):
            for symbol_b in symbols[i + 1:]:
                breakdown = self._check_pair(symbol_a, symbol_b)
                if breakdown:
                    breakdowns.append(breakdown)
        
        # Also check explicitly monitored pairs
        for pair in self._monitored_pairs:
            if pair[0] in self._returns and pair[1] in self._returns:
                breakdown = self._check_pair(pair[0], pair[1])
                if breakdown and breakdown.breakdown_id not in [b.breakdown_id for b in breakdowns]:
                    breakdowns.append(breakdown)
        
        # Sort by severity
        severity_order = {
            AlertSeverity.CRITICAL: 0,
            AlertSeverity.WARNING: 1,
            AlertSeverity.INFO: 2,
        }
        breakdowns.sort(key=lambda b: severity_order[b.severity])
        
        logger.info(
            f"Correlation breakdown detection completed: {len(breakdowns)} events found",
            extra={"symbols_checked": len(symbols), "pairs_checked": len(symbols) * (len(symbols) - 1) // 2},
        )
        
        return breakdowns
    
    def _check_pair(
        self,
        symbol_a: str,
        symbol_b: str,
    ) -> CorrelationBreakdown | None:
        """Check a single pair for correlation breakdown."""
        returns_a = self._returns.get(symbol_a, [])
        returns_b = self._returns.get(symbol_b, [])
        
        # Need sufficient history
        min_len = min(len(returns_a), len(returns_b))
        if min_len < self.min_history_days:
            return None
        
        # Align returns
        returns_a = returns_a[-min_len:]
        returns_b = returns_b[-min_len:]
        
        # Calculate correlations
        try:
            # Full period correlation (baseline)
            full_corr = np.corrcoef(returns_a, returns_b)[0, 1]
            
            # Recent window correlation
            recent_a = returns_a[-self.recent_window:]
            recent_b = returns_b[-self.recent_window:]
            recent_corr = np.corrcoef(recent_a, recent_b)[0, 1]
            
            if np.isnan(full_corr) or np.isnan(recent_corr):
                return None
            
        except Exception:
            return None
        
        # Store in history
        pair_key = tuple(sorted([symbol_a, symbol_b]))
        if pair_key not in self._correlation_history:
            self._correlation_history[pair_key] = []
        self._correlation_history[pair_key].append(recent_corr)
        
        # Trim history
        if len(self._correlation_history[pair_key]) > 252:
            self._correlation_history[pair_key] = self._correlation_history[pair_key][-252:]
        
        # Calculate rolling statistics
        corr_history = self._correlation_history[pair_key]
        if len(corr_history) < 20:
            return None
        
        historical_mean = np.mean(corr_history[:-1])  # Exclude current
        historical_std = np.std(corr_history[:-1]) or 0.01  # Avoid division by zero
        
        # Calculate z-score
        z_score = (recent_corr - historical_mean) / historical_std
        correlation_change = recent_corr - historical_mean
        
        # Determine if breakdown occurred
        is_breakdown = (
            abs(z_score) >= self.z_score_threshold or
            abs(correlation_change) >= self.change_threshold
        )
        
        if not is_breakdown:
            return None
        
        # Classify breakdown type
        breakdown_type, severity = self._classify_breakdown(
            recent_corr, historical_mean, z_score, correlation_change
        )
        
        # Generate description and recommendations
        description = self._generate_description(
            symbol_a, symbol_b, breakdown_type, recent_corr, historical_mean, z_score
        )
        recommendations = self._generate_recommendations(breakdown_type, severity)
        
        breakdown_id = f"{symbol_a}_{symbol_b}_{breakdown_type.value}"
        
        return CorrelationBreakdown(
            breakdown_id=breakdown_id,
            breakdown_type=breakdown_type,
            severity=severity,
            symbol_a=symbol_a,
            symbol_b=symbol_b,
            historical_correlation=historical_mean,
            current_correlation=recent_corr,
            correlation_change=correlation_change,
            z_score=z_score,
            detected_at=datetime.now(UTC),
            lookback_days=min_len,
            recent_window_days=self.recent_window,
            description=description,
            recommendations=recommendations,
        )
    
    def _classify_breakdown(
        self,
        current_corr: float,
        historical_corr: float,
        z_score: float,
        change: float,
    ) -> tuple[CorrelationBreakdownType, AlertSeverity]:
        """Classify the type and severity of breakdown."""
        # Determine type based on direction and magnitude
        if change > 0:
            # Correlation increasing
            if current_corr > 0.7 and historical_corr < 0.5:
                breakdown_type = CorrelationBreakdownType.CONVERGENCE
            else:
                breakdown_type = CorrelationBreakdownType.CORRELATION_SPIKE
        else:
            # Correlation decreasing
            if historical_corr > 0.5 and current_corr < 0.2:
                breakdown_type = CorrelationBreakdownType.DECOUPLING
            elif current_corr < 0 and historical_corr > 0:
                breakdown_type = CorrelationBreakdownType.REGIME_CHANGE
            else:
                breakdown_type = CorrelationBreakdownType.CORRELATION_COLLAPSE
        
        # Determine severity
        if abs(z_score) >= 3.0 or abs(change) >= 0.5:
            severity = AlertSeverity.CRITICAL
        elif abs(z_score) >= 2.5 or abs(change) >= 0.4:
            severity = AlertSeverity.WARNING
        else:
            severity = AlertSeverity.INFO
        
        return breakdown_type, severity
    
    def _generate_description(
        self,
        symbol_a: str,
        symbol_b: str,
        breakdown_type: CorrelationBreakdownType,
        current_corr: float,
        historical_corr: float,
        z_score: float,
    ) -> str:
        """Generate human-readable description."""
        type_descriptions = {
            CorrelationBreakdownType.CORRELATION_SPIKE: 
                f"{symbol_a}/{symbol_b} correlation spiked to {current_corr:.2f} "
                f"(was {historical_corr:.2f}, z={z_score:.1f})",
            CorrelationBreakdownType.CORRELATION_COLLAPSE:
                f"{symbol_a}/{symbol_b} correlation collapsed to {current_corr:.2f} "
                f"(was {historical_corr:.2f}, z={z_score:.1f})",
            CorrelationBreakdownType.REGIME_CHANGE:
                f"{symbol_a}/{symbol_b} correlation regime changed: "
                f"{historical_corr:.2f} → {current_corr:.2f}",
            CorrelationBreakdownType.DECOUPLING:
                f"{symbol_a}/{symbol_b} decoupled: correlation dropped from "
                f"{historical_corr:.2f} to {current_corr:.2f}",
            CorrelationBreakdownType.CONVERGENCE:
                f"{symbol_a}/{symbol_b} converged: correlation rose from "
                f"{historical_corr:.2f} to {current_corr:.2f}",
        }
        return type_descriptions.get(breakdown_type, "Correlation breakdown detected")
    
    def _generate_recommendations(
        self,
        breakdown_type: CorrelationBreakdownType,
        severity: AlertSeverity,
    ) -> list[str]:
        """Generate recommendations based on breakdown type."""
        recommendations = []
        
        if breakdown_type == CorrelationBreakdownType.CORRELATION_SPIKE:
            recommendations.append("Review portfolio diversification - assets may move together in stress")
            recommendations.append("Consider reducing correlated exposures")
        
        elif breakdown_type == CorrelationBreakdownType.CORRELATION_COLLAPSE:
            recommendations.append("May indicate sector rotation or market regime change")
            recommendations.append("Review pairs trading or relative value positions")
        
        elif breakdown_type == CorrelationBreakdownType.REGIME_CHANGE:
            recommendations.append("Update correlation assumptions in risk models")
            recommendations.append("Consider recalibrating strategy parameters")
        
        elif breakdown_type == CorrelationBreakdownType.DECOUPLING:
            recommendations.append("Review pairs that relied on historical correlation")
            recommendations.append("May present new trading opportunities")
        
        elif breakdown_type == CorrelationBreakdownType.CONVERGENCE:
            recommendations.append("Diversification benefit may be reduced")
            recommendations.append("Consider adding uncorrelated assets")
        
        if severity == AlertSeverity.CRITICAL:
            recommendations.insert(0, "CRITICAL: Immediate review recommended")
        
        return recommendations
    
    def get_correlation_regimes(
        self,
        symbols: list[str] | None = None,
    ) -> list[CorrelationRegime]:
        """Get current correlation regimes for all pairs."""
        if symbols is None:
            symbols = list(self._returns.keys())
        
        regimes: list[CorrelationRegime] = []
        
        for i, symbol_a in enumerate(symbols):
            for symbol_b in symbols[i + 1:]:
                regime = self._get_pair_regime(symbol_a, symbol_b)
                if regime:
                    regimes.append(regime)
        
        return regimes
    
    def _get_pair_regime(
        self,
        symbol_a: str,
        symbol_b: str,
    ) -> CorrelationRegime | None:
        """Get correlation regime for a pair."""
        pair_key = tuple(sorted([symbol_a, symbol_b]))
        history = self._correlation_history.get(pair_key, [])
        
        if len(history) < 20:
            return None
        
        current = history[-1]
        std = float(np.std(history))
        
        # Determine regime label
        if current > 0.5:
            label = "positive"
        elif current < -0.3:
            label = "negative"
        else:
            label = "uncorrelated"
        
        # Estimate regime duration (how long in current regime)
        duration = 1
        for i in range(len(history) - 2, -1, -1):
            if self._same_regime(history[i], current):
                duration += 1
            else:
                break
        
        # Stability score based on std dev
        stability = max(0.0, min(1.0, 1 - std))
        
        return CorrelationRegime(
            symbol_a=symbol_a,
            symbol_b=symbol_b,
            current_correlation=current,
            correlation_std=std,
            regime_label=label,
            regime_duration_days=duration,
            stability_score=stability,
            historical_min=float(np.min(history)),
            historical_max=float(np.max(history)),
            historical_mean=float(np.mean(history)),
        )
    
    def _same_regime(self, corr_a: float, corr_b: float) -> bool:
        """Check if two correlations are in the same regime."""
        def get_regime(corr: float) -> str:
            if corr > 0.5:
                return "positive"
            elif corr < -0.3:
                return "negative"
            return "uncorrelated"
        
        return get_regime(corr_a) == get_regime(corr_b)
    
    def to_dict(self, breakdown: CorrelationBreakdown) -> dict[str, Any]:
        """Convert breakdown to dictionary."""
        return {
            "breakdown_id": breakdown.breakdown_id,
            "breakdown_type": breakdown.breakdown_type.value,
            "severity": breakdown.severity.value,
            "symbol_a": breakdown.symbol_a,
            "symbol_b": breakdown.symbol_b,
            "historical_correlation": breakdown.historical_correlation,
            "current_correlation": breakdown.current_correlation,
            "correlation_change": breakdown.correlation_change,
            "z_score": breakdown.z_score,
            "detected_at": breakdown.detected_at.isoformat(),
            "lookback_days": breakdown.lookback_days,
            "recent_window_days": breakdown.recent_window_days,
            "description": breakdown.description,
            "recommendations": breakdown.recommendations,
            "affected_positions": breakdown.affected_positions,
            "portfolio_impact": breakdown.portfolio_impact,
        }


# Singleton instance
_detector: CorrelationBreakdownDetector | None = None


def get_correlation_detector() -> CorrelationBreakdownDetector:
    """Get or create the correlation breakdown detector singleton."""
    global _detector
    if _detector is None:
        _detector = CorrelationBreakdownDetector()
    return _detector
