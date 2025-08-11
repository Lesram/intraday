"""
Order Service - handles order submission and lifecycle.
Now includes strategy engine integration for plan-and-submit workflows.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

if TYPE_CHECKING:
    from ..strategies.engine import StrategyEngine

from ..infra.outbox import OutboxRepo
from ..infra.repositories.orders import OrdersRepo
from ..strategies.types import TradingSignal

logger = logging.getLogger(__name__)


class OrderService:
    """
    Service for order operations including strategy-driven workflows.
    """

    def __init__(
        self,
        orders_repo: OrdersRepo,
        outbox_repo: OutboxRepo,
        strategy_engine: Optional["StrategyEngine"] = None
    ):
        self.orders_repo = orders_repo
        self.outbox_repo = outbox_repo
        self.strategy_engine = strategy_engine

    async def submit_symbol_order(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        idempotency_key: str,
        order_type: str = "market",
        tif: str = "ioc",
        attributes: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Submit a single order through the idempotent order+outbox flow.

        This is the core order submission path used by both direct API calls
        and strategy engine executions.
        """
        try:
            from decimal import Decimal

            # Create order through repository (with idempotency protection)
            order = await self.orders_repo.upsert_by_idempotency(
                client_key=idempotency_key,
                symbol=symbol,
                side=side,
                qty=Decimal(str(qty)),
                order_type=order_type,
                tif=tif,
                attributes=attributes or {}
            )

            # Add to outbox for broker submission
            await self.outbox_repo.add_order_submit_event(
                order_id=str(order.id),
                event_type="order.submit",
                payload={
                    "order_id": str(order.id),
                    "symbol": symbol,
                    "side": side,
                    "qty": str(qty),
                    "order_type": order_type,
                    "tif": tif,
                    "client_key": idempotency_key,
                    "attributes": attributes or {}
                }
            )

            logger.info("Order submitted successfully", extra={
                "order_id": str(order.id),
                "symbol": symbol,
                "side": side,
                "qty": str(qty),
                "idempotency_key": idempotency_key
            })

            return {
                "order_id": str(order.id),
                "symbol": symbol,
                "side": side,
                "qty": str(qty),
                "status": order.status,
                "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
                "idempotency_key": idempotency_key
            }

        except Exception as e:
            logger.error("Order submission failed", extra={
                "symbol": symbol,
                "side": side,
                "qty": str(qty),
                "error": str(e),
                "idempotency_key": idempotency_key
            })
            raise

    async def plan_and_submit(
        self,
        signals: list[TradingSignal],
        idempotency_key: str | None = None,
        portfolio_state: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Strategy engine integration: convert signals to execution plans
        and submit approved plans through the existing order flow.

        Args:
            signals: List of trading signals from strategies
            idempotency_key: Optional base key for order idempotency
            portfolio_state: Current portfolio state for risk calculations

        Returns:
            List of results, one per symbol with execution status
        """
        if not self.strategy_engine:
            raise ValueError("StrategyEngine not configured for this OrderService instance")

        if not signals:
            return []

        base_key = idempotency_key or uuid4().hex

        try:
            # Generate execution plans through strategy engine
            plans = await self.strategy_engine.generate_and_gate(signals, portfolio_state)

            results = []
            for i, plan in enumerate(plans):
                symbol_key = f"{base_key}_{plan.symbol}_{i}"

                if not plan.risk_allowed or plan.qty == 0:
                    # Risk blocked or no-op plan
                    results.append({
                        "symbol": plan.symbol,
                        "status": "risk_blocked" if not plan.risk_allowed else "no_change",
                        "reason": plan.risk_reason or plan.reason,
                        "from_exposure": plan.from_exposure,
                        "to_exposure": plan.to_exposure,
                        "qty": str(plan.qty),
                        "risk_allowed": plan.risk_allowed
                    })
                    continue

                # Submit approved plan through existing order flow
                try:
                    order_result = await self.submit_symbol_order(
                        symbol=plan.symbol,
                        side=plan.side,
                        qty=float(abs(plan.qty)),  # Use absolute value, side determines direction
                        idempotency_key=symbol_key,
                        attributes={
                            "engine": "netting",
                            "reason": plan.reason,
                            "from_exposure": plan.from_exposure,
                            "to_exposure": plan.to_exposure,
                            "notional": str(plan.notional)
                        }
                    )

                    # Enhance result with plan details
                    order_result.update({
                        "from_exposure": plan.from_exposure,
                        "to_exposure": plan.to_exposure,
                        "reason": plan.reason,
                        "risk_allowed": plan.risk_allowed,
                        "notional": str(plan.notional)
                    })

                    results.append(order_result)

                except Exception as e:
                    logger.error("Failed to submit order for plan", extra={
                        "symbol": plan.symbol,
                        "side": plan.side,
                        "qty": float(plan.qty),
                        "error": str(e)
                    })

                    results.append({
                        "symbol": plan.symbol,
                        "status": "submit_error",
                        "reason": f"Order submission failed: {str(e)}",
                        "from_exposure": plan.from_exposure,
                        "to_exposure": plan.to_exposure,
                        "qty": str(plan.qty),
                        "risk_allowed": plan.risk_allowed
                    })

            logger.info("Strategy plan-and-submit completed", extra={
                "signals_count": len(signals),
                "plans_count": len(plans),
                "submitted_count": len([r for r in results if r.get("order_id")]),
                "blocked_count": len([r for r in results if not r.get("risk_allowed", True)]),
                "base_idempotency_key": base_key
            })

            return results

        except Exception as e:
            logger.error("Strategy plan-and-submit failed", extra={
                "signals_count": len(signals),
                "error": str(e),
                "base_idempotency_key": base_key
            })
            raise
