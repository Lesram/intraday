"""
Order Flow Imbalance Analysis (M-48)

Analyzes buy/sell pressure imbalances to detect:
- Directional momentum
- Potential reversals
- Institutional activity
- Support/resistance levels

Provides real-time order flow signals for trading decisions.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
import logging
from collections import deque

import numpy as np

logger = logging.getLogger(__name__)


class ImbalanceDirection(Enum):
    """Direction of order flow imbalance."""
    STRONG_BUY = "strong_buy"
    MODERATE_BUY = "moderate_buy"
    NEUTRAL = "neutral"
    MODERATE_SELL = "moderate_sell"
    STRONG_SELL = "strong_sell"


class OrderFlowSignal(Enum):
    """Trading signals based on order flow."""
    ACCUMULATION = "accumulation"     # Quiet buying, bullish
    DISTRIBUTION = "distribution"     # Quiet selling, bearish
    BREAKOUT = "breakout"             # Strong momentum, continuation
    EXHAUSTION = "exhaustion"         # Momentum fading, reversal likely
    ABSORPTION = "absorption"         # Large orders absorbed, reversal
    NEUTRAL = "neutral"               # No clear signal


@dataclass
class TradeRecord:
    """Record of an individual trade for order flow analysis."""
    timestamp: datetime
    price: float
    quantity: float
    side: str  # "buy" or "sell"
    is_aggressive: bool = True  # True if taker (market order)


@dataclass
class ImbalanceMetrics:
    """Order flow imbalance metrics for a time window."""
    # Volume metrics
    buy_volume: float
    sell_volume: float
    total_volume: float
    volume_imbalance: float  # (buy - sell) / total
    
    # Trade count metrics
    buy_trades: int
    sell_trades: int
    total_trades: int
    trade_imbalance: float  # (buy - sell) / total
    
    # Value metrics
    buy_value: float  # buy_volume * avg_buy_price
    sell_value: float
    value_imbalance: float
    
    # Aggression metrics
    aggressive_buy_volume: float
    aggressive_sell_volume: float
    aggression_imbalance: float
    
    # Derived metrics
    avg_buy_size: float
    avg_sell_size: float
    size_ratio: float  # avg_buy / avg_sell
    
    # Direction
    direction: ImbalanceDirection
    signal: OrderFlowSignal
    
    # Context
    window_seconds: int
    start_time: datetime
    end_time: datetime
    symbol: str


@dataclass
class CumulativeImbalance:
    """Cumulative order flow imbalance over session."""
    cumulative_delta: float  # Running (buy_volume - sell_volume)
    cumulative_value_delta: float
    session_high_delta: float
    session_low_delta: float
    delta_trend: str  # "rising", "falling", "flat"
    
    # Price correlation
    delta_price_correlation: float
    divergence_detected: bool  # Price moving opposite to delta


@dataclass
class ImbalanceAlert:
    """Alert for significant order flow events."""
    alert_id: str
    symbol: str
    alert_type: str
    severity: str  # "info", "warning", "critical"
    timestamp: datetime
    
    # Details
    imbalance_ratio: float
    volume: float
    direction: ImbalanceDirection
    signal: OrderFlowSignal
    
    message: str
    recommendation: str


class OrderFlowAnalyzer:
    """
    Analyzes order flow to detect buy/sell pressure imbalances.
    
    Tracks:
    - Volume imbalance (buy vs sell volume)
    - Trade count imbalance
    - Dollar value imbalance
    - Aggression imbalance (market vs limit orders)
    - Cumulative delta
    
    Generates signals:
    - Accumulation/Distribution
    - Breakout/Exhaustion
    - Absorption (reversal patterns)
    
    Usage:
        analyzer = OrderFlowAnalyzer()
        
        # Record trades
        analyzer.add_trade(TradeRecord(
            timestamp=datetime.now(),
            price=150.25,
            quantity=100,
            side="buy",
            is_aggressive=True,
        ))
        
        # Get imbalance metrics
        metrics = analyzer.calculate_imbalance("AAPL", window_seconds=300)
        
        # Check for alerts
        alerts = analyzer.check_alerts("AAPL")
    """
    
    # Thresholds
    STRONG_IMBALANCE_THRESHOLD = 0.6
    MODERATE_IMBALANCE_THRESHOLD = 0.3
    ALERT_VOLUME_MULTIPLIER = 2.0
    DIVERGENCE_THRESHOLD = -0.3  # Negative correlation
    
    def __init__(
        self,
        max_trade_history: int = 10000,
        default_window_seconds: int = 300,
        alert_cooldown_seconds: int = 60,
    ):
        """
        Initialize order flow analyzer.
        
        Args:
            max_trade_history: Maximum trades to keep per symbol
            default_window_seconds: Default analysis window
            alert_cooldown_seconds: Minimum time between alerts
        """
        self.max_trade_history = max_trade_history
        self.default_window_seconds = default_window_seconds
        self.alert_cooldown_seconds = alert_cooldown_seconds
        
        # Trade history by symbol
        self._trades: dict[str, deque[TradeRecord]] = {}
        
        # Price history for divergence detection
        self._prices: dict[str, deque[tuple[datetime, float]]] = {}
        
        # Cumulative metrics
        self._cumulative: dict[str, CumulativeImbalance] = {}
        
        # Alert tracking
        self._last_alerts: dict[str, datetime] = {}
        self._alert_history: list[ImbalanceAlert] = []
        
        # Baseline volumes for comparison
        self._volume_baselines: dict[str, float] = {}
    
    def add_trade(self, symbol: str, trade: TradeRecord) -> None:
        """
        Add a trade record for analysis.
        
        Args:
            symbol: Asset symbol
            trade: Trade record
        """
        if symbol not in self._trades:
            self._trades[symbol] = deque(maxlen=self.max_trade_history)
            self._prices[symbol] = deque(maxlen=self.max_trade_history)
        
        self._trades[symbol].append(trade)
        self._prices[symbol].append((trade.timestamp, trade.price))
        
        # Update cumulative delta
        self._update_cumulative(symbol, trade)
    
    def add_trades_batch(
        self,
        symbol: str,
        trades: list[dict[str, Any]],
    ) -> None:
        """Add multiple trades from dict format."""
        for t in trades:
            trade = TradeRecord(
                timestamp=t.get("timestamp", datetime.now(UTC)),
                price=float(t.get("price", 0)),
                quantity=float(t.get("quantity", 0)),
                side=t.get("side", "buy"),
                is_aggressive=t.get("is_aggressive", True),
            )
            self.add_trade(symbol, trade)
    
    def _update_cumulative(self, symbol: str, trade: TradeRecord) -> None:
        """Update cumulative delta with new trade."""
        delta = trade.quantity if trade.side == "buy" else -trade.quantity
        value_delta = delta * trade.price
        
        if symbol not in self._cumulative:
            self._cumulative[symbol] = CumulativeImbalance(
                cumulative_delta=0.0,
                cumulative_value_delta=0.0,
                session_high_delta=0.0,
                session_low_delta=0.0,
                delta_trend="flat",
                delta_price_correlation=0.0,
                divergence_detected=False,
            )
        
        cum = self._cumulative[symbol]
        cum.cumulative_delta += delta
        cum.cumulative_value_delta += value_delta
        cum.session_high_delta = max(cum.session_high_delta, cum.cumulative_delta)
        cum.session_low_delta = min(cum.session_low_delta, cum.cumulative_delta)
    
    def calculate_imbalance(
        self,
        symbol: str,
        window_seconds: int | None = None,
        end_time: datetime | None = None,
    ) -> ImbalanceMetrics:
        """
        Calculate order flow imbalance metrics.
        
        Args:
            symbol: Asset symbol
            window_seconds: Analysis window in seconds
            end_time: End time for window (defaults to now)
            
        Returns:
            ImbalanceMetrics with comprehensive analysis
        """
        window = window_seconds or self.default_window_seconds
        end = end_time or datetime.now(UTC)
        start = end - timedelta(seconds=window)
        
        trades = self._trades.get(symbol, deque())
        
        # Filter trades in window
        window_trades = [t for t in trades if start <= t.timestamp <= end]
        
        if not window_trades:
            return self._create_empty_metrics(symbol, window, start, end)
        
        # Calculate metrics
        buy_trades = [t for t in window_trades if t.side == "buy"]
        sell_trades = [t for t in window_trades if t.side == "sell"]
        
        buy_volume = sum(t.quantity for t in buy_trades)
        sell_volume = sum(t.quantity for t in sell_trades)
        total_volume = buy_volume + sell_volume
        
        buy_value = sum(t.quantity * t.price for t in buy_trades)
        sell_value = sum(t.quantity * t.price for t in sell_trades)
        total_value = buy_value + sell_value
        
        aggressive_buy = sum(t.quantity for t in buy_trades if t.is_aggressive)
        aggressive_sell = sum(t.quantity for t in sell_trades if t.is_aggressive)
        
        # Calculate imbalances
        volume_imbalance = (buy_volume - sell_volume) / total_volume if total_volume > 0 else 0
        trade_imbalance = (len(buy_trades) - len(sell_trades)) / len(window_trades) if window_trades else 0
        value_imbalance = (buy_value - sell_value) / total_value if total_value > 0 else 0
        
        aggressive_total = aggressive_buy + aggressive_sell
        aggression_imbalance = (aggressive_buy - aggressive_sell) / aggressive_total if aggressive_total > 0 else 0
        
        avg_buy_size = buy_volume / len(buy_trades) if buy_trades else 0
        avg_sell_size = sell_volume / len(sell_trades) if sell_trades else 0
        size_ratio = avg_buy_size / avg_sell_size if avg_sell_size > 0 else 1.0
        
        # Determine direction
        direction = self._classify_direction(volume_imbalance)
        
        # Determine signal
        signal = self._classify_signal(
            symbol, volume_imbalance, aggression_imbalance, total_volume
        )
        
        return ImbalanceMetrics(
            buy_volume=buy_volume,
            sell_volume=sell_volume,
            total_volume=total_volume,
            volume_imbalance=volume_imbalance,
            buy_trades=len(buy_trades),
            sell_trades=len(sell_trades),
            total_trades=len(window_trades),
            trade_imbalance=trade_imbalance,
            buy_value=buy_value,
            sell_value=sell_value,
            value_imbalance=value_imbalance,
            aggressive_buy_volume=aggressive_buy,
            aggressive_sell_volume=aggressive_sell,
            aggression_imbalance=aggression_imbalance,
            avg_buy_size=avg_buy_size,
            avg_sell_size=avg_sell_size,
            size_ratio=size_ratio,
            direction=direction,
            signal=signal,
            window_seconds=window,
            start_time=start,
            end_time=end,
            symbol=symbol,
        )
    
    def _classify_direction(self, imbalance: float) -> ImbalanceDirection:
        """Classify imbalance direction."""
        if imbalance >= self.STRONG_IMBALANCE_THRESHOLD:
            return ImbalanceDirection.STRONG_BUY
        elif imbalance >= self.MODERATE_IMBALANCE_THRESHOLD:
            return ImbalanceDirection.MODERATE_BUY
        elif imbalance <= -self.STRONG_IMBALANCE_THRESHOLD:
            return ImbalanceDirection.STRONG_SELL
        elif imbalance <= -self.MODERATE_IMBALANCE_THRESHOLD:
            return ImbalanceDirection.MODERATE_SELL
        else:
            return ImbalanceDirection.NEUTRAL
    
    def _classify_signal(
        self,
        symbol: str,
        volume_imbalance: float,
        aggression_imbalance: float,
        total_volume: float,
    ) -> OrderFlowSignal:
        """Classify trading signal from order flow."""
        baseline = self._volume_baselines.get(symbol, total_volume)
        volume_ratio = total_volume / baseline if baseline > 0 else 1.0
        
        # High volume + strong imbalance = breakout
        if volume_ratio >= self.ALERT_VOLUME_MULTIPLIER:
            if abs(volume_imbalance) >= self.STRONG_IMBALANCE_THRESHOLD:
                return OrderFlowSignal.BREAKOUT
        
        # Strong aggression opposite to volume = absorption (reversal)
        if volume_imbalance * aggression_imbalance < 0:
            if abs(aggression_imbalance) >= self.MODERATE_IMBALANCE_THRESHOLD:
                return OrderFlowSignal.ABSORPTION
        
        # Moderate imbalance with low aggression = accumulation/distribution
        if abs(volume_imbalance) >= self.MODERATE_IMBALANCE_THRESHOLD:
            if abs(aggression_imbalance) < self.MODERATE_IMBALANCE_THRESHOLD:
                if volume_imbalance > 0:
                    return OrderFlowSignal.ACCUMULATION
                else:
                    return OrderFlowSignal.DISTRIBUTION
        
        # Declining volume with extreme imbalance = exhaustion
        if volume_ratio < 0.5 and abs(volume_imbalance) >= self.STRONG_IMBALANCE_THRESHOLD:
            return OrderFlowSignal.EXHAUSTION
        
        return OrderFlowSignal.NEUTRAL
    
    def get_cumulative_imbalance(self, symbol: str) -> CumulativeImbalance:
        """Get cumulative imbalance for session."""
        if symbol not in self._cumulative:
            return CumulativeImbalance(
                cumulative_delta=0.0,
                cumulative_value_delta=0.0,
                session_high_delta=0.0,
                session_low_delta=0.0,
                delta_trend="flat",
                delta_price_correlation=0.0,
                divergence_detected=False,
            )
        
        cum = self._cumulative[symbol]
        
        # Update trend and divergence
        self._update_cumulative_analysis(symbol)
        
        return cum
    
    def _update_cumulative_analysis(self, symbol: str) -> None:
        """Update cumulative delta analysis."""
        if symbol not in self._cumulative:
            return
        
        cum = self._cumulative[symbol]
        trades = list(self._trades.get(symbol, []))
        prices = list(self._prices.get(symbol, []))
        
        if len(trades) < 20:
            return
        
        # Calculate delta trend (last 100 trades)
        recent_trades = trades[-100:]
        mid_point = len(recent_trades) // 2
        
        first_half_delta = sum(
            t.quantity if t.side == "buy" else -t.quantity
            for t in recent_trades[:mid_point]
        )
        second_half_delta = sum(
            t.quantity if t.side == "buy" else -t.quantity
            for t in recent_trades[mid_point:]
        )
        
        delta_change = second_half_delta - first_half_delta
        if delta_change > 0:
            cum.delta_trend = "rising"
        elif delta_change < 0:
            cum.delta_trend = "falling"
        else:
            cum.delta_trend = "flat"
        
        # Calculate price-delta correlation
        if len(prices) >= 20:
            try:
                recent_prices = [p[1] for p in prices[-100:]]
                
                # Calculate running delta
                running_delta = []
                delta = 0
                for t in recent_trades:
                    delta += t.quantity if t.side == "buy" else -t.quantity
                    running_delta.append(delta)
                
                # Align lengths
                min_len = min(len(recent_prices), len(running_delta))
                if min_len >= 10:
                    corr = np.corrcoef(
                        recent_prices[-min_len:],
                        running_delta[-min_len:]
                    )[0, 1]
                    
                    if not np.isnan(corr):
                        cum.delta_price_correlation = float(corr)
                        cum.divergence_detected = corr < self.DIVERGENCE_THRESHOLD
            
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "Order flow delta-price correlation failed for %s: %s",
                    symbol, e
                )

    def check_alerts(self, symbol: str) -> list[ImbalanceAlert]:
        """Check for alert conditions on a symbol."""
        now = datetime.now(UTC)
        
        # Check cooldown
        last_alert = self._last_alerts.get(symbol)
        if last_alert and (now - last_alert).seconds < self.alert_cooldown_seconds:
            return []
        
        alerts: list[ImbalanceAlert] = []
        
        # Calculate current metrics
        metrics = self.calculate_imbalance(symbol)
        cumulative = self.get_cumulative_imbalance(symbol)
        
        # Check for strong imbalance
        if metrics.direction in [ImbalanceDirection.STRONG_BUY, ImbalanceDirection.STRONG_SELL]:
            alert = ImbalanceAlert(
                alert_id=f"{symbol}_{now.timestamp()}_imbalance",
                symbol=symbol,
                alert_type="strong_imbalance",
                severity="warning",
                timestamp=now,
                imbalance_ratio=metrics.volume_imbalance,
                volume=metrics.total_volume,
                direction=metrics.direction,
                signal=metrics.signal,
                message=f"Strong {'buying' if metrics.volume_imbalance > 0 else 'selling'} "
                        f"pressure detected ({metrics.volume_imbalance:.1%} imbalance)",
                recommendation="Monitor for continuation or exhaustion",
            )
            alerts.append(alert)
        
        # Check for divergence
        if cumulative.divergence_detected:
            alert = ImbalanceAlert(
                alert_id=f"{symbol}_{now.timestamp()}_divergence",
                symbol=symbol,
                alert_type="delta_divergence",
                severity="warning",
                timestamp=now,
                imbalance_ratio=metrics.volume_imbalance,
                volume=metrics.total_volume,
                direction=metrics.direction,
                signal=OrderFlowSignal.EXHAUSTION,
                message=f"Price-delta divergence detected (correlation: "
                        f"{cumulative.delta_price_correlation:.2f})",
                recommendation="Potential reversal - consider reducing exposure",
            )
            alerts.append(alert)
        
        # Check for breakout signal
        if metrics.signal == OrderFlowSignal.BREAKOUT:
            alert = ImbalanceAlert(
                alert_id=f"{symbol}_{now.timestamp()}_breakout",
                symbol=symbol,
                alert_type="breakout_signal",
                severity="info",
                timestamp=now,
                imbalance_ratio=metrics.volume_imbalance,
                volume=metrics.total_volume,
                direction=metrics.direction,
                signal=metrics.signal,
                message=f"Breakout detected with {metrics.total_volume:,.0f} volume",
                recommendation="Consider trend-following entry",
            )
            alerts.append(alert)
        
        # Check for absorption (reversal)
        if metrics.signal == OrderFlowSignal.ABSORPTION:
            alert = ImbalanceAlert(
                alert_id=f"{symbol}_{now.timestamp()}_absorption",
                symbol=symbol,
                alert_type="absorption_pattern",
                severity="warning",
                timestamp=now,
                imbalance_ratio=metrics.volume_imbalance,
                volume=metrics.total_volume,
                direction=metrics.direction,
                signal=metrics.signal,
                message="Order absorption detected - potential reversal pattern",
                recommendation="Watch for reversal confirmation",
            )
            alerts.append(alert)
        
        if alerts:
            self._last_alerts[symbol] = now
            self._alert_history.extend(alerts)
            
            for alert in alerts:
                logger.info(
                    f"Order flow alert: {alert.alert_type}",
                    extra={
                        "symbol": symbol,
                        "severity": alert.severity,
                        "imbalance": f"{alert.imbalance_ratio:.1%}",
                    }
                )
        
        return alerts
    
    def set_volume_baseline(self, symbol: str, baseline: float) -> None:
        """Set baseline volume for comparison."""
        self._volume_baselines[symbol] = baseline
    
    def reset_session(self, symbol: str | None = None) -> None:
        """Reset cumulative metrics for new session."""
        if symbol:
            if symbol in self._cumulative:
                self._cumulative[symbol] = CumulativeImbalance(
                    cumulative_delta=0.0,
                    cumulative_value_delta=0.0,
                    session_high_delta=0.0,
                    session_low_delta=0.0,
                    delta_trend="flat",
                    delta_price_correlation=0.0,
                    divergence_detected=False,
                )
        else:
            self._cumulative.clear()
    
    def _create_empty_metrics(
        self,
        symbol: str,
        window: int,
        start: datetime,
        end: datetime,
    ) -> ImbalanceMetrics:
        """Create empty metrics when no data available."""
        return ImbalanceMetrics(
            buy_volume=0,
            sell_volume=0,
            total_volume=0,
            volume_imbalance=0,
            buy_trades=0,
            sell_trades=0,
            total_trades=0,
            trade_imbalance=0,
            buy_value=0,
            sell_value=0,
            value_imbalance=0,
            aggressive_buy_volume=0,
            aggressive_sell_volume=0,
            aggression_imbalance=0,
            avg_buy_size=0,
            avg_sell_size=0,
            size_ratio=1.0,
            direction=ImbalanceDirection.NEUTRAL,
            signal=OrderFlowSignal.NEUTRAL,
            window_seconds=window,
            start_time=start,
            end_time=end,
            symbol=symbol,
        )
    
    def get_alert_history(
        self,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[ImbalanceAlert]:
        """Get alert history."""
        history = self._alert_history
        
        if symbol:
            history = [a for a in history if a.symbol == symbol]
        
        return list(reversed(history[-limit:]))
    
    def to_dict(self, metrics: ImbalanceMetrics) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "buy_volume": metrics.buy_volume,
            "sell_volume": metrics.sell_volume,
            "total_volume": metrics.total_volume,
            "volume_imbalance": metrics.volume_imbalance,
            "buy_trades": metrics.buy_trades,
            "sell_trades": metrics.sell_trades,
            "total_trades": metrics.total_trades,
            "trade_imbalance": metrics.trade_imbalance,
            "buy_value": metrics.buy_value,
            "sell_value": metrics.sell_value,
            "value_imbalance": metrics.value_imbalance,
            "aggressive_buy_volume": metrics.aggressive_buy_volume,
            "aggressive_sell_volume": metrics.aggressive_sell_volume,
            "aggression_imbalance": metrics.aggression_imbalance,
            "avg_buy_size": metrics.avg_buy_size,
            "avg_sell_size": metrics.avg_sell_size,
            "size_ratio": metrics.size_ratio,
            "direction": metrics.direction.value,
            "signal": metrics.signal.value,
            "window_seconds": metrics.window_seconds,
            "start_time": metrics.start_time.isoformat(),
            "end_time": metrics.end_time.isoformat(),
            "symbol": metrics.symbol,
        }


# Singleton instance
_analyzer: OrderFlowAnalyzer | None = None


def get_order_flow_analyzer() -> OrderFlowAnalyzer:
    """Get or create the order flow analyzer singleton."""
    global _analyzer
    if _analyzer is None:
        _analyzer = OrderFlowAnalyzer()
    return _analyzer
