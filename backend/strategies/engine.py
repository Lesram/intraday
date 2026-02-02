"""
Strategy Engine - Branch 2.7

Implements deterministic signal netting, throttling, and risk gating.
Routes all execution through RiskManager.before_order() before creating orders.
"""

import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
import logging
import os
from typing import Any

from ..config import get_settings
from ..infra.metrics import get_metrics_registry
from ..risk.risk_manager import RiskManager
from ..services.positions_service import PositionsService
from .types import ExecutionPlan, Side, TradingSignal

logger = logging.getLogger(__name__)

# M-16 FIX: Import quote manager for real price data
try:
    from ..services.quote_manager import QuoteManager
    QUOTE_MANAGER_AVAILABLE = True
except ImportError:
    QUOTE_MANAGER_AVAILABLE = False
    logger.warning("QuoteManager not available, will use fallback prices")


class StrategyEngine:
    """
    Deterministic strategy engine that nets signals, applies throttles,
    and gates all executions through risk management.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        positions_service: PositionsService,
        config: dict[str, Any] | None = None,
    ):
        self.risk_manager = risk_manager
        self.positions_service = positions_service
        self.settings = get_settings()
        self.metrics = get_metrics_registry()

        # Configuration with defaults
        self.config = config or {}
        self.strategy_weights = {
            "momentum": self.config.get(
                "momentum_weight",
                getattr(self.settings, "strategy_momentum_weight", 0.6),
            ),
            "mean_reversion": self.config.get(
                "mean_rev_weight",
                getattr(self.settings, "strategy_mean_rev_weight", 0.4),
            ),
            "ensemble": self.config.get(
                "ensemble_weight",
                getattr(self.settings, "strategy_ensemble_weight", 1.0),
            ),
        }

        self.min_flip_interval_s = self.config.get(
            "min_flip_interval_s",
            getattr(self.settings, "strategy_min_flip_interval_s", 60),
        )
        self.max_new_risk_per_bar = self.config.get(
            "max_new_risk_per_bar",
            getattr(self.settings, "strategy_max_new_risk_per_bar", 0.15),
        )

        # Precision settings
        self.qty_precision = getattr(self.settings, "qty_precision", 4)
        self.price_precision = getattr(self.settings, "price_precision", 4)

        # Track last flip times for throttling
        self.last_flip_times: dict[str, datetime] = {}
        self.last_exposures: dict[str, float] = {}

        logger.info(
            "StrategyEngine initialized",
            extra={
                "strategy_weights": self.strategy_weights,
                "min_flip_interval_s": self.min_flip_interval_s,
                "max_new_risk_per_bar": self.max_new_risk_per_bar,
            },
        )

    @classmethod
    def create_default(cls, config: dict[str, Any] | None = None):
        """
        Factory method to create StrategyEngine with default dependencies.
        Useful for testing and simple initialization.
        """
        from ..risk.risk_manager import RiskManager
        from ..services.positions_service import PositionsService

        # Create default instances
        risk_manager = RiskManager()
        positions_service = PositionsService()

        return cls(
            risk_manager=risk_manager,
            positions_service=positions_service,
            config=config
        )

    def _get_symbol_bucket(self, symbol: str) -> str:
        """
        Bucket symbols to avoid metric cardinality explosion.
        Groups symbols alphabetically: A-F, G-M, N-S, T-Z
        """
        first_char = symbol[0].upper()
        if first_char <= "F":
            return "A-F"
        elif first_char <= "M":
            return "G-M"
        elif first_char <= "S":
            return "N-S"
        else:
            return "T-Z"

    async def build_execution_plan(
        self, signals: list[TradingSignal]
    ) -> list[ExecutionPlan]:
        """
        Build execution plans from signals using netting and throttling rules.

        Returns one ExecutionPlan per symbol with netted exposure targets.
        """
        if not signals:
            return []

        # Group signals by symbol
        signals_by_symbol = defaultdict(list)
        for signal in signals:
            signals_by_symbol[signal.symbol].append(signal)

            # Increment signal metrics
            if self.metrics:
                self.metrics.inc_counter(
                    "strategy_signals_total", {"source": signal.source}
                )

        plans = []
        current_time = datetime.now(UTC)

        # Get current positions for all symbols
        all_symbols = list(signals_by_symbol.keys())
        try:
            current_positions_dict = await self.positions_service.get_positions_by_symbols(
                all_symbols
            )
            # positions_service returns a dict, convert to position_map directly
            position_map = current_positions_dict
        except Exception as e:
            logger.error(
                "Failed to fetch positions for execution planning",
                extra={
                    "symbols": all_symbols,
                    "error": str(e),
                },
            )
            # Continue with empty position map
            position_map = {}

        # Build plans for all symbols in parallel for better performance
        async def build_plan_safe(symbol: str, symbol_signals: list[TradingSignal]):
            """Wrapper to catch exceptions per-symbol without failing the batch."""
            try:
                return await self._build_symbol_plan(
                    symbol, symbol_signals, current_time, position_map
                )
            except Exception as e:
                import traceback
                logger.error(
                    f"Failed to build plan for {symbol}",
                    extra={
                        "symbol": symbol,
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                        "signals_count": len(symbol_signals),
                    },
                )
                return None

        # Execute all symbol plan builds concurrently
        results = await asyncio.gather(
            *[build_plan_safe(sym, sigs) for sym, sigs in signals_by_symbol.items()]
        )
        plans = [plan for plan in results if plan is not None]

        return plans

    # ------------------------------------------------------------------
    # Legacy compatibility: some tests monkey-patch process_signals.
    # Provide a thin wrapper so patch.object(engine, 'process_signals') works.
    # ------------------------------------------------------------------
    async def process_signals(self, signals: list[TradingSignal]):  # pragma: no cover - simple delegate
        return await self.build_execution_plan(signals)

    def net_signals(self, signals: list[TradingSignal]):  # pragma: no cover - legacy sync hook
        """Legacy test hook: return signals unchanged.

        Some older tests call this method synchronously (without awaiting) while
        others may patch it with a synchronous stub. Making it synchronous avoids
        returning an un-awaited coroutine which previously caused TypeError in
        tests that do: ``netted = engine.net_signals(signals)``.
        """
        return signals

    # Additional legacy hook expected by some tests for patching throttling behavior
    def is_throttled(self, symbol: str) -> bool:  # pragma: no cover - trivial
        """Return False by default; tests may patch this method."""
        return False

    async def _build_symbol_plan(
        self,
        symbol: str,
        signals: list[TradingSignal],
        current_time: datetime,
        position_map: dict[str, Any],
    ) -> ExecutionPlan | None:
        """Build execution plan for a single symbol."""

        # Calculate current exposure
        current_position = position_map.get(symbol)
        account_value = getattr(self.settings.trading, "account_value", 100000)  # Default 100k

        if current_position and account_value > 0:
            # Assume position has qty, price attributes
            position_value = float(current_position.qty) * float(
                getattr(current_position, "price", 100)
            )
            from_exposure = position_value / account_value
            # Clamp to [-1, 1] range
            from_exposure = max(-1.0, min(1.0, from_exposure))
        else:
            from_exposure = 0.0

        # Store last exposure for flip detection
        self.last_exposures.get(symbol, from_exposure)
        self.last_exposures[symbol] = from_exposure

        # Net signals using weighted average
        total_weighted_exposure = 0.0
        total_weight = 0.0

        strategy_sources = []
        for signal in signals:
            # Get strategy weight (default to 1.0 for unknown strategies)
            weight = self.strategy_weights.get(signal.source, 1.0)
            confidence_weight = weight * signal.confidence

            total_weighted_exposure += signal.target_exposure * confidence_weight
            total_weight += confidence_weight
            strategy_sources.append(signal.source)

        if total_weight == 0:
            logger.warning(f"No weighted signals for {symbol}")
            return None

        # Calculate netted target exposure
        netted_exposure = total_weighted_exposure / total_weight
        # Clamp to [-1, 1]
        netted_exposure = max(-1.0, min(1.0, netted_exposure))

        # Apply throttling
        to_exposure, throttle_applied = self._apply_throttling(
            symbol, from_exposure, netted_exposure, current_time
        )

        # Apply max risk per bar limit
        risk_delta = abs(to_exposure - from_exposure)
        if risk_delta > self.max_new_risk_per_bar:
            # Scale down the change
            direction = 1 if to_exposure > from_exposure else -1
            to_exposure = from_exposure + (direction * self.max_new_risk_per_bar)
            throttle_applied = True
            logger.info(
                f"Risk per bar limit applied for {symbol}",
                extra={
                    "original_delta": risk_delta,
                    "max_allowed": self.max_new_risk_per_bar,
                    "from_exposure": from_exposure,
                    "to_exposure": to_exposure,
                },
            )

        # Convert exposure to quantity
        qty, notional, side = await self._exposure_to_qty(
            symbol, to_exposure, account_value
        )

        # Build reason string
        sources_str = "+".join(set(strategy_sources))
        throttle_str = "throttled" if throttle_applied else "ok"
        reason = f"netted: {sources_str}; throttle={throttle_str}"

        # Record metrics
        if self.metrics:
            symbol_bucket = self._get_symbol_bucket(symbol)
            self.metrics.inc_counter(
                "strategy_netting_decisions_total", {"symbol_bucket": symbol_bucket}
            )
            if throttle_applied:
                self.metrics.inc_counter("strategy_throttled_total")

        return ExecutionPlan(
            symbol=symbol,
            side=side,
            quantity=abs(qty),  # ExecutionPlan expects positive quantity
            price=Decimal("1.0") if notional == 0 else abs(notional / qty) if qty != 0 else Decimal("1.0"),
            ts=current_time,
            from_exposure=from_exposure,
            to_exposure=to_exposure,
            notional=notional,
            qty=qty,
            reason=reason,
            risk_allowed=True,  # Will be updated in gate_with_risk
            risk_reason=None,
        )

    def _apply_throttling(
        self,
        symbol: str,
        from_exposure: float,
        target_exposure: float,
        current_time: datetime,
    ) -> tuple[float, bool]:
        """
        Apply throttling rules to prevent rapid position flips.

        Returns (adjusted_exposure, throttle_applied)
        """
        # Check if this is a flip (crossing zero or changing direction significantly)
        is_flip = (from_exposure > 0.1 and target_exposure < -0.1) or (  # long to short
            from_exposure < -0.1 and target_exposure > 0.1
        )  # short to long

        if not is_flip:
            return target_exposure, False

        # Check last flip time
        last_flip = self.last_flip_times.get(symbol)
        if last_flip:
            time_since_flip = (current_time - last_flip).total_seconds()
            if time_since_flip < self.min_flip_interval_s:
                # Throttle: limit movement toward the target
                max_change = 0.2  # Allow small moves but prevent full flip
                direction = 1 if target_exposure > from_exposure else -1
                throttled_exposure = from_exposure + (direction * max_change)

                logger.info(
                    f"Flip throttled for {symbol}",
                    extra={
                        "from_exposure": from_exposure,
                        "target_exposure": target_exposure,
                        "throttled_exposure": throttled_exposure,
                        "time_since_flip": time_since_flip,
                        "min_interval": self.min_flip_interval_s,
                    },
                )

                return throttled_exposure, True

        # Record this flip
        self.last_flip_times[symbol] = current_time
        return target_exposure, False

    async def _exposure_to_qty(
        self, symbol: str, exposure: float, account_value: float
    ) -> tuple[Decimal, Decimal, Side]:
        """
        Convert exposure percentage to broker-ready quantity.
        """
        if abs(exposure) < 0.001:  # Essentially flat
            return Decimal("0"), Decimal("0"), "flat"

        # M-16 FIX: Get current price from quote manager or broker
        price = await self._get_current_price(symbol)

        # Calculate notional value
        notional_value = abs(exposure) * account_value
        notional = Decimal(str(notional_value)).quantize(
            Decimal("0.01"), rounding=ROUND_DOWN
        )

        # Calculate quantity
        qty_float = notional_value / price
        if exposure < 0:
            qty_float = -qty_float

        # Round to exchange precision
        precision = Decimal("0." + "0" * (self.qty_precision - 1) + "1")
        qty = Decimal(str(qty_float)).quantize(precision, rounding=ROUND_DOWN)

        # Determine side
        if qty > 0:
            side = Side.BUY
        elif qty < 0:
            side = Side.SELL
        else:
            side = Side.FLAT

        return qty, notional, side

    async def _get_current_price(self, symbol: str) -> float:
        """
        M-16 FIX: Get current price from broker or quote manager.
        
        Falls back to a conservative default only in test mode.
        """
        # Try QuoteManager first
        if QUOTE_MANAGER_AVAILABLE:
            try:
                quote_manager = QuoteManager()
                quotes = await quote_manager.get_quotes([symbol])
                if symbol in quotes and quotes[symbol].last > 0:
                    return quotes[symbol].last
            except Exception as e:
                logger.warning(f"QuoteManager failed for {symbol}: {e}")
        
        # Try positions service for last known price
        try:
            if self.positions_service:
                positions = await self.positions_service.get_all_positions()
                if positions:
                    for pos in positions:
                        if pos.get('symbol') == symbol and pos.get('current_price', 0) > 0:
                            return float(pos['current_price'])
        except Exception as e:
            logger.warning(f"PositionsService price lookup failed: {e}")
        
        # In production, fail if we can't get real prices
        is_production = os.getenv("APP_ENVIRONMENT", "").lower() in ("production", "prod")
        if is_production:
            logger.error(f"Cannot get real price for {symbol} in production")
            raise ValueError(f"M-16 SECURITY: Cannot calculate order size without real price for {symbol}")
        
        # Test/development fallback with common defaults
        logger.warning(f"Using fallback price for {symbol} - only acceptable in test mode")
        fallback_prices = {
            "AAPL": 175.0, "MSFT": 380.0, "GOOGL": 140.0, "TSLA": 250.0,
            "NVDA": 500.0, "SPY": 450.0, "QQQ": 380.0,
            "BTCUSD": 45000.0, "ETHUSD": 3000.0, "EURUSD": 1.1,
        }
        return fallback_prices.get(symbol, 100.0)

    async def gate_with_risk(
        self, plan: ExecutionPlan, portfolio_state: dict[str, Any] | None = None
    ) -> ExecutionPlan:
        """
        Gate execution plan through risk manager.

        Updates risk_allowed and risk_reason based on RiskManager.before_order().
        """
        if plan.qty == 0 or plan.side == Side.FLAT:
            # No risk check needed for flat positions
            return plan

        try:
            # Create order spec for risk check
            order_spec = {
                "symbol": plan.symbol,
                "side": plan.side,
                "qty": float(plan.qty),
                "notional": float(plan.notional),
                "order_type": "market",  # Assume market orders for strategy engine
                "metadata": {"source": "strategy_engine", "reason": plan.reason},
            }

            # Call risk manager
            if asyncio.iscoroutinefunction(self.risk_manager.before_order):
                risk_result = await self.risk_manager.before_order(
                    order_spec, portfolio_state
                )
            else:
                risk_result = self.risk_manager.before_order(
                    order_spec, portfolio_state
                )

            # Handle risk manager response
            if isinstance(risk_result, dict):
                allowed = risk_result.get("allowed", True)
                reason = risk_result.get("reason", "")
            else:
                # Assume boolean response for backward compatibility
                allowed = bool(risk_result)
                reason = "" if allowed else "Risk manager blocked order"

            if allowed:
                updated_reason = f"{plan.reason}; risk=allow"
                return ExecutionPlan(
                    symbol=plan.symbol,
                    side=plan.side,
                    quantity=plan.quantity,
                    price=plan.price,
                    ts=plan.ts,
                    from_exposure=plan.from_exposure,
                    to_exposure=plan.to_exposure,
                    notional=plan.notional,
                    qty=plan.qty,
                    reason=updated_reason,
                    risk_allowed=True,
                    risk_reason=None,
                )
            else:
                # Risk blocked - force flat position
                blocked_reason = f"{plan.reason}; risk=blocked"

                # Record blocked metric
                if self.metrics:
                    self.metrics.inc_counter(
                        "strategy_blocked_total", {"reason": "risk_manager"}
                    )

                logger.warning(
                    f"Risk manager blocked order for {plan.symbol}",
                    extra={
                        "symbol": plan.symbol,
                        "side": plan.side,
                        "qty": float(plan.qty),
                        "risk_reason": reason,
                    },
                )

                return ExecutionPlan(
                    symbol=plan.symbol,
                    side=Side.FLAT,
                    quantity=Decimal("0"),
                    price=plan.price if hasattr(plan, 'price') else Decimal("1.0"),
                    ts=plan.ts,
                    from_exposure=plan.from_exposure,
                    to_exposure=plan.from_exposure,  # Stay at current position
                    notional=Decimal("0"),
                    qty=Decimal("0"),
                    reason=blocked_reason,
                    risk_allowed=False,
                    risk_reason=reason,
                )

        except Exception as e:
            logger.error(
                f"Risk gating failed for {plan.symbol}",
                extra={"symbol": plan.symbol, "error": str(e)},
            )

            # Default to blocked on error
            if self.metrics:
                self.metrics.inc_counter(
                    "strategy_blocked_total", {"reason": "risk_error"}
                )

            return ExecutionPlan(
                symbol=plan.symbol,
                side=Side.FLAT,
                quantity=Decimal("0"),
                price=plan.price if hasattr(plan, 'price') else Decimal("1.0"),
                ts=plan.ts,
                from_exposure=plan.from_exposure,
                to_exposure=plan.from_exposure,
                notional=Decimal("0"),
                qty=Decimal("0"),
                reason=f"{plan.reason}; risk=error",
                risk_allowed=False,
                risk_reason=f"Risk check failed: {str(e)}",
            )

    async def generate_and_gate(
        self,
        signals: list[TradingSignal],
        portfolio_state: dict[str, Any] | None = None,
    ) -> list[ExecutionPlan]:
        """
        Complete pipeline: build plans → apply risk gate → return final plans.
        """
        # Build initial plans
        plans = await self.build_execution_plan(signals)

        # Apply risk gating to each plan
        gated_plans = []
        for plan in plans:
            gated_plan = await self.gate_with_risk(plan, portfolio_state)
            gated_plans.append(gated_plan)

            # Record notional metrics (using buckets to control cardinality)
            if self.metrics and gated_plan.risk_allowed:
                bucket = self._get_symbol_bucket(gated_plan.symbol)
                notional_value = float(gated_plan.notional)
                # Use gauge to track planned notional by bucket
                self.metrics.set_gauge(
                    f"strategy_planned_notional_{bucket}", notional_value
                )

        logger.info(
            "Strategy engine completed",
            extra={
                "signals_count": len(signals),
                "plans_generated": len(plans),
                "plans_risk_allowed": len([p for p in gated_plans if p.risk_allowed]),
                "symbols": [p.symbol for p in gated_plans],
            },
        )

        return gated_plans
