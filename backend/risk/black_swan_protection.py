"""
Black Swan Protection (M-46)

Implements circuit breakers for extreme market events:
- Rapid market moves (flash crashes)
- Volatility spikes
- Liquidity crises
- Correlation breakdowns
- Portfolio drawdown limits

Provides automated position reduction and trading halts during stress.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Callable
import logging

import numpy as np

logger = logging.getLogger(__name__)


class CircuitBreakerType(Enum):
    """Types of circuit breakers."""
    MARKET_MOVE = "market_move"           # Rapid market decline
    VOLATILITY_SPIKE = "volatility_spike"  # VIX or realized vol spike
    DRAWDOWN = "drawdown"                  # Portfolio drawdown limit
    LIQUIDITY = "liquidity"                # Liquidity crisis
    CORRELATION = "correlation"            # All-assets-down scenario
    POSITION_LOSS = "position_loss"        # Single position loss limit


class CircuitBreakerState(Enum):
    """State of circuit breaker."""
    ARMED = "armed"           # Normal operation, monitoring
    TRIGGERED = "triggered"   # Breaker tripped, action taken
    COOLING_OFF = "cooling_off"  # Post-trigger cooldown period
    DISABLED = "disabled"     # Manually disabled


class ProtectionAction(Enum):
    """Actions to take when circuit breaker triggers."""
    ALERT_ONLY = "alert_only"           # Just send alerts
    REDUCE_EXPOSURE = "reduce_exposure"  # Reduce position sizes
    HEDGE = "hedge"                       # Add hedging positions
    LIQUIDATE_PARTIAL = "liquidate_partial"  # Sell portion of portfolio
    LIQUIDATE_ALL = "liquidate_all"      # Emergency liquidation
    HALT_TRADING = "halt_trading"        # Stop all new orders


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""
    breaker_type: CircuitBreakerType
    name: str
    enabled: bool = True
    
    # Threshold settings
    threshold: float = 0.0
    threshold_period_minutes: int = 60
    
    # Action settings
    action: ProtectionAction = ProtectionAction.REDUCE_EXPOSURE
    action_intensity: float = 0.5  # 0-1, how aggressive the action
    
    # Cooldown
    cooldown_minutes: int = 30
    auto_reset: bool = True
    
    # Additional parameters
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class CircuitBreakerTrigger:
    """Record of a circuit breaker trigger event."""
    trigger_id: str
    breaker_type: CircuitBreakerType
    triggered_at: datetime
    trigger_value: float
    threshold: float
    action_taken: ProtectionAction
    
    # Impact
    positions_affected: list[str] = field(default_factory=list)
    exposure_reduced_pct: float = 0.0
    orders_cancelled: int = 0
    
    # Status
    reset_at: datetime | None = None
    is_active: bool = True
    
    # Details
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketConditions:
    """Current market conditions for circuit breaker evaluation."""
    # Index levels and changes
    spy_price: float = 0.0
    spy_change_pct: float = 0.0
    spy_change_1h_pct: float = 0.0
    
    # Volatility
    vix_level: float = 20.0
    vix_change_pct: float = 0.0
    realized_vol_20d: float = 0.15
    
    # Breadth
    pct_stocks_down: float = 0.5
    avg_stock_decline: float = 0.0
    
    # Liquidity
    relative_volume: float = 1.0  # vs average
    bid_ask_spread_multiplier: float = 1.0
    
    # Portfolio-specific
    portfolio_pnl_today: float = 0.0
    portfolio_drawdown: float = 0.0
    max_position_loss: float = 0.0
    max_position_loss_symbol: str = ""


class BlackSwanProtection:
    """
    Black swan protection system with multiple circuit breakers.
    
    Monitors for extreme market events and takes protective action:
    - Flash crash detection (rapid market declines)
    - Volatility spike detection (VIX surges)
    - Portfolio drawdown limits
    - Single position loss limits
    - Correlation breakdown (all assets down)
    
    Usage:
        protection = BlackSwanProtection()
        
        # Configure breakers
        protection.add_breaker(CircuitBreakerConfig(
            breaker_type=CircuitBreakerType.MARKET_MOVE,
            name="Flash Crash",
            threshold=-0.05,  # 5% down
            threshold_period_minutes=15,
            action=ProtectionAction.REDUCE_EXPOSURE,
        ))
        
        # Update conditions
        conditions = MarketConditions(
            spy_change_1h_pct=-0.06,
            vix_level=35,
            ...
        )
        
        # Check for triggers
        triggers = protection.evaluate(conditions)
    """
    
    # L-23: Default circuit breaker configurations as tuple for immutability and performance
    # Using tuple instead of list reduces overhead in hot paths
    DEFAULT_BREAKERS: tuple[CircuitBreakerConfig, ...] = (
        CircuitBreakerConfig(
            breaker_type=CircuitBreakerType.MARKET_MOVE,
            name="Flash Crash Level 1",
            threshold=-0.03,  # 3% in 1 hour
            threshold_period_minutes=60,
            action=ProtectionAction.ALERT_ONLY,
            cooldown_minutes=30,
        ),
        CircuitBreakerConfig(
            breaker_type=CircuitBreakerType.MARKET_MOVE,
            name="Flash Crash Level 2",
            threshold=-0.05,  # 5% in 1 hour
            threshold_period_minutes=60,
            action=ProtectionAction.REDUCE_EXPOSURE,
            action_intensity=0.3,
            cooldown_minutes=60,
        ),
        CircuitBreakerConfig(
            breaker_type=CircuitBreakerType.MARKET_MOVE,
            name="Flash Crash Level 3",
            threshold=-0.07,  # 7% in 1 hour
            threshold_period_minutes=60,
            action=ProtectionAction.HALT_TRADING,
            cooldown_minutes=120,
        ),
        CircuitBreakerConfig(
            breaker_type=CircuitBreakerType.VOLATILITY_SPIKE,
            name="VIX Spike",
            threshold=40.0,  # VIX > 40
            action=ProtectionAction.REDUCE_EXPOSURE,
            action_intensity=0.5,
            cooldown_minutes=60,
        ),
        CircuitBreakerConfig(
            breaker_type=CircuitBreakerType.DRAWDOWN,
            name="Portfolio Drawdown",
            threshold=-0.05,  # 5% drawdown
            action=ProtectionAction.REDUCE_EXPOSURE,
            action_intensity=0.5,
            cooldown_minutes=1440,  # 24 hours
        ),
        CircuitBreakerConfig(
            breaker_type=CircuitBreakerType.POSITION_LOSS,
            name="Single Position Loss",
            threshold=-0.15,  # 15% loss on single position
            action=ProtectionAction.ALERT_ONLY,
            cooldown_minutes=60,
        ),
    )
    
    def __init__(
        self,
        use_defaults: bool = True,
        global_enabled: bool = True,
    ):
        """
        Initialize black swan protection.
        
        Args:
            use_defaults: Whether to load default circuit breakers
            global_enabled: Global enable/disable switch
        """
        self.global_enabled = global_enabled
        
        # Circuit breaker configurations
        self._breakers: dict[str, CircuitBreakerConfig] = {}
        self._breaker_states: dict[str, CircuitBreakerState] = {}
        
        # Trigger history
        self._active_triggers: dict[str, CircuitBreakerTrigger] = {}
        self._trigger_history: list[CircuitBreakerTrigger] = []
        
        # Action callbacks
        self._action_handlers: dict[ProtectionAction, Callable] = {}
        
        # Load defaults
        if use_defaults:
            for config in self.DEFAULT_BREAKERS:
                self.add_breaker(config)
        
        logger.info(
            "Black swan protection initialized",
            extra={"breaker_count": len(self._breakers), "global_enabled": global_enabled},
        )
    
    def add_breaker(self, config: CircuitBreakerConfig) -> None:
        """Add or update a circuit breaker configuration."""
        breaker_id = f"{config.breaker_type.value}_{config.name}"
        self._breakers[breaker_id] = config
        self._breaker_states[breaker_id] = CircuitBreakerState.ARMED
        
        logger.debug(f"Added circuit breaker: {breaker_id}")
    
    def remove_breaker(self, breaker_id: str) -> bool:
        """Remove a circuit breaker."""
        if breaker_id in self._breakers:
            del self._breakers[breaker_id]
            del self._breaker_states[breaker_id]
            return True
        return False
    
    def register_action_handler(
        self,
        action: ProtectionAction,
        handler: Callable[[CircuitBreakerTrigger], None],
    ) -> None:
        """Register a handler for a specific protection action."""
        self._action_handlers[action] = handler
    
    def evaluate(
        self,
        conditions: MarketConditions,
        positions: dict[str, float] | None = None,
    ) -> list[CircuitBreakerTrigger]:
        """
        Evaluate market conditions against all circuit breakers.
        
        Args:
            conditions: Current market conditions
            positions: Optional position sizes by symbol
            
        Returns:
            List of triggered circuit breakers
        """
        if not self.global_enabled:
            return []
        
        triggers: list[CircuitBreakerTrigger] = []
        now = datetime.now(UTC)
        
        for breaker_id, config in self._breakers.items():
            if not config.enabled:
                continue
            
            state = self._breaker_states[breaker_id]
            
            # Check if in cooldown
            if state == CircuitBreakerState.COOLING_OFF:
                if self._check_cooldown_expired(breaker_id, now):
                    self._breaker_states[breaker_id] = CircuitBreakerState.ARMED
                else:
                    continue
            
            if state != CircuitBreakerState.ARMED:
                continue
            
            # Evaluate this breaker
            trigger = self._evaluate_breaker(config, conditions, positions, now)
            
            if trigger:
                triggers.append(trigger)
                self._handle_trigger(breaker_id, trigger)
        
        return triggers
    
    def _evaluate_breaker(
        self,
        config: CircuitBreakerConfig,
        conditions: MarketConditions,
        positions: dict[str, float] | None,
        now: datetime,
    ) -> CircuitBreakerTrigger | None:
        """Evaluate a single circuit breaker."""
        current_value: float | None = None
        is_triggered = False
        
        if config.breaker_type == CircuitBreakerType.MARKET_MOVE:
            # Check market move threshold
            current_value = conditions.spy_change_1h_pct
            is_triggered = current_value <= config.threshold
        
        elif config.breaker_type == CircuitBreakerType.VOLATILITY_SPIKE:
            # Check VIX level
            current_value = conditions.vix_level
            is_triggered = current_value >= config.threshold
        
        elif config.breaker_type == CircuitBreakerType.DRAWDOWN:
            # Check portfolio drawdown
            current_value = -conditions.portfolio_drawdown  # Make negative for comparison
            is_triggered = current_value <= config.threshold
        
        elif config.breaker_type == CircuitBreakerType.POSITION_LOSS:
            # Check single position loss
            current_value = conditions.max_position_loss
            is_triggered = current_value <= config.threshold
        
        elif config.breaker_type == CircuitBreakerType.CORRELATION:
            # Check if majority of stocks down significantly
            current_value = conditions.pct_stocks_down
            is_triggered = (
                current_value >= 0.9 and  # 90%+ stocks down
                conditions.avg_stock_decline <= -0.02  # Average 2%+ decline
            )
        
        elif config.breaker_type == CircuitBreakerType.LIQUIDITY:
            # Check for liquidity stress
            current_value = conditions.bid_ask_spread_multiplier
            is_triggered = current_value >= config.threshold
        
        if not is_triggered or current_value is None:
            return None
        
        # Build trigger record
        trigger_id = f"{config.breaker_type.value}_{now.timestamp()}"
        
        positions_affected = []
        if positions and config.breaker_type == CircuitBreakerType.POSITION_LOSS:
            positions_affected = [conditions.max_position_loss_symbol]
        elif positions:
            positions_affected = list(positions.keys())
        
        trigger = CircuitBreakerTrigger(
            trigger_id=trigger_id,
            breaker_type=config.breaker_type,
            triggered_at=now,
            trigger_value=current_value,
            threshold=config.threshold,
            action_taken=config.action,
            positions_affected=positions_affected,
            exposure_reduced_pct=config.action_intensity * 100 if config.action == ProtectionAction.REDUCE_EXPOSURE else 0,
            details={
                "breaker_name": config.name,
                "market_conditions": {
                    "spy_change": conditions.spy_change_pct,
                    "vix": conditions.vix_level,
                    "drawdown": conditions.portfolio_drawdown,
                },
            },
        )
        
        logger.warning(
            f"Circuit breaker triggered: {config.name}",
            extra={
                "breaker_type": config.breaker_type.value,
                "trigger_value": current_value,
                "threshold": config.threshold,
                "action": config.action.value,
            },
        )
        
        return trigger
    
    def _handle_trigger(
        self,
        breaker_id: str,
        trigger: CircuitBreakerTrigger,
    ) -> None:
        """Handle a circuit breaker trigger."""
        config = self._breakers[breaker_id]
        
        # Update state
        self._breaker_states[breaker_id] = CircuitBreakerState.TRIGGERED
        self._active_triggers[breaker_id] = trigger
        self._trigger_history.append(trigger)
        
        # Execute action handler if registered
        if trigger.action_taken in self._action_handlers:
            try:
                self._action_handlers[trigger.action_taken](trigger)
            except Exception as e:
                logger.error(f"Action handler failed: {e}", exc_info=True)
        
        # Start cooldown
        self._breaker_states[breaker_id] = CircuitBreakerState.COOLING_OFF
    
    def _check_cooldown_expired(self, breaker_id: str, now: datetime) -> bool:
        """Check if cooldown period has expired."""
        trigger = self._active_triggers.get(breaker_id)
        if not trigger:
            return True
        
        config = self._breakers[breaker_id]
        cooldown_end = trigger.triggered_at + timedelta(minutes=config.cooldown_minutes)
        
        if now >= cooldown_end:
            trigger.reset_at = now
            trigger.is_active = False
            return True
        
        return False
    
    def reset_breaker(self, breaker_id: str) -> bool:
        """Manually reset a circuit breaker."""
        if breaker_id in self._breaker_states:
            self._breaker_states[breaker_id] = CircuitBreakerState.ARMED
            
            if breaker_id in self._active_triggers:
                self._active_triggers[breaker_id].is_active = False
                self._active_triggers[breaker_id].reset_at = datetime.now(UTC)
            
            logger.info(f"Circuit breaker reset: {breaker_id}")
            return True
        return False
    
    def disable_breaker(self, breaker_id: str) -> bool:
        """Disable a circuit breaker."""
        if breaker_id in self._breaker_states:
            self._breaker_states[breaker_id] = CircuitBreakerState.DISABLED
            logger.info(f"Circuit breaker disabled: {breaker_id}")
            return True
        return False
    
    def enable_breaker(self, breaker_id: str) -> bool:
        """Enable a circuit breaker."""
        if breaker_id in self._breaker_states:
            self._breaker_states[breaker_id] = CircuitBreakerState.ARMED
            logger.info(f"Circuit breaker enabled: {breaker_id}")
            return True
        return False
    
    def get_status(self) -> dict[str, Any]:
        """Get current status of all circuit breakers."""
        now = datetime.now(UTC)
        
        breaker_status = []
        for breaker_id, config in self._breakers.items():
            state = self._breaker_states[breaker_id]
            trigger = self._active_triggers.get(breaker_id)
            
            cooldown_remaining = None
            if trigger and state == CircuitBreakerState.COOLING_OFF:
                cooldown_end = trigger.triggered_at + timedelta(minutes=config.cooldown_minutes)
                cooldown_remaining = max(0, (cooldown_end - now).total_seconds())
            
            breaker_status.append({
                "breaker_id": breaker_id,
                "name": config.name,
                "type": config.breaker_type.value,
                "enabled": config.enabled,
                "state": state.value,
                "threshold": config.threshold,
                "action": config.action.value,
                "last_triggered": trigger.triggered_at.isoformat() if trigger else None,
                "cooldown_remaining_seconds": cooldown_remaining,
            })
        
        return {
            "global_enabled": self.global_enabled,
            "breakers": breaker_status,
            "active_triggers": len([t for t in self._active_triggers.values() if t.is_active]),
            "total_triggers_today": len([
                t for t in self._trigger_history
                if t.triggered_at.date() == now.date()
            ]),
        }
    
    def get_trigger_history(
        self,
        limit: int = 100,
        breaker_type: CircuitBreakerType | None = None,
    ) -> list[CircuitBreakerTrigger]:
        """Get trigger history with optional filtering."""
        history = self._trigger_history
        
        if breaker_type:
            history = [t for t in history if t.breaker_type == breaker_type]
        
        return list(reversed(history[-limit:]))
    
    def to_dict(self, trigger: CircuitBreakerTrigger) -> dict[str, Any]:
        """Convert trigger to dictionary."""
        return {
            "trigger_id": trigger.trigger_id,
            "breaker_type": trigger.breaker_type.value,
            "triggered_at": trigger.triggered_at.isoformat(),
            "trigger_value": trigger.trigger_value,
            "threshold": trigger.threshold,
            "action_taken": trigger.action_taken.value,
            "positions_affected": trigger.positions_affected,
            "exposure_reduced_pct": trigger.exposure_reduced_pct,
            "orders_cancelled": trigger.orders_cancelled,
            "reset_at": trigger.reset_at.isoformat() if trigger.reset_at else None,
            "is_active": trigger.is_active,
            "details": trigger.details,
        }


# Singleton instance
_protection: BlackSwanProtection | None = None


def get_black_swan_protection() -> BlackSwanProtection:
    """Get or create the black swan protection singleton."""
    global _protection
    if _protection is None:
        _protection = BlackSwanProtection()
    return _protection
