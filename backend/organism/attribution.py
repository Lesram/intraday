"""
Phase 1 — Fill-Based PnL Attribution Service.

Reconstructs per-strategy × per-symbol performance from realized order fills,
replacing the living policy's price-close proxy with real execution outcomes.

Pipeline:
1. Ingest filled orders (from Order table) with `attributes.strategy_source`.
2. Reconstruct position changes per strategy × symbol.
3. Compute realized PnL, slippage (expected vs fill price), and fees.
4. Produce per-strategy reward signals consumed by the living policy engine.
5. Persist attribution events for audit.
"""

from __future__ import annotations

# M-11 (audit-2026-05-02): removed unused `import uuid`
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.infra.schemas import ModelLifecycleEvent, Order
from backend.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TradeAttribution:
    """Single trade outcome attributed to a strategy source."""
    id: str
    symbol: str
    strategy_source: str
    side: str
    qty: float
    fill_price: float
    expected_price: float | None
    realized_pnl: float
    slippage_bps: float
    fees: float
    timestamp: str


@dataclass
class StrategyPerformance:
    """Aggregated performance for one strategy source over a window."""
    source: str
    total_pnl: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    total_slippage_bps: float = 0.0
    avg_slippage_bps: float = 0.0
    total_fees: float = 0.0
    max_drawdown: float = 0.0
    sharpe_proxy: float = 0.0
    turnover_usd: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.win_count / self.trade_count if self.trade_count > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "total_pnl": round(self.total_pnl, 4),
            "trade_count": self.trade_count,
            "win_rate": round(self.win_rate, 4),
            "total_slippage_bps": round(self.total_slippage_bps, 2),
            "avg_slippage_bps": round(self.avg_slippage_bps, 2),
            "total_fees": round(self.total_fees, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe_proxy": round(self.sharpe_proxy, 4),
            "turnover_usd": round(self.turnover_usd, 2),
        }


@dataclass
class AttributionResult:
    """Full attribution result for a window."""
    window_start: str
    window_end: str
    strategies: dict[str, StrategyPerformance] = field(default_factory=dict)
    trades: list[TradeAttribution] = field(default_factory=list)
    reward_signals: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start,
            "window_end": self.window_end,
            "strategies": {k: v.to_dict() for k, v in self.strategies.items()},
            "reward_signals": self.reward_signals,
            "trade_count": len(self.trades),
        }


class AttributionService:
    """Compute fill-based PnL attribution per strategy × symbol.

    This replaces the price-close proxy in the living policy with
    actual realized execution outcomes.
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        # Positions reconstructed per (strategy, symbol)
        self._positions: dict[str, dict[str, float]] = {}  # {strategy: {symbol: qty}}
        self._avg_costs: dict[str, dict[str, float]] = {}   # {strategy: {symbol: avg_cost}}

    async def compute_attribution(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        persist: bool = True,
    ) -> AttributionResult:
        """Compute attribution from filled orders in [window_start, window_end]."""
        # Reset position tracking so successive calls don't carry stale state
        self._positions = {}
        self._avg_costs = {}

        trades: list[TradeAttribution] = []
        strategies: dict[str, StrategyPerformance] = {}

        async with self._sessionmaker() as session:
            orders = await self._fetch_filled_orders(session, window_start, window_end)

            for order in orders:
                trade = self._process_order(order)
                if trade is None:
                    continue
                trades.append(trade)

                # Aggregate into strategy performance
                perf = strategies.setdefault(
                    trade.strategy_source,
                    StrategyPerformance(source=trade.strategy_source),
                )
                perf.total_pnl += trade.realized_pnl - trade.fees  # Net of fees
                perf.trade_count += 1
                if trade.realized_pnl > 0:
                    perf.win_count += 1
                elif trade.realized_pnl < 0:
                    perf.loss_count += 1
                perf.total_slippage_bps += trade.slippage_bps
                perf.total_fees += trade.fees
                perf.turnover_usd += abs(trade.qty * trade.fill_price)

            # Compute averages
            for perf in strategies.values():
                if perf.trade_count > 0:
                    perf.avg_slippage_bps = perf.total_slippage_bps / perf.trade_count

            # Compute reward signals (normalized for the living policy)
            reward_signals = self._compute_reward_signals(strategies)

            # Compute max drawdown per strategy
            self._compute_drawdowns(trades, strategies)

            # Compute Sharpe proxy
            self._compute_sharpe_proxies(trades, strategies)

            result = AttributionResult(
                window_start=window_start.isoformat(),
                window_end=window_end.isoformat(),
                strategies=strategies,
                trades=trades,
                reward_signals=reward_signals,
            )

            if persist:
                await self._persist_attribution(session, result)

        return result

    async def get_latest_attribution(self) -> AttributionResult | None:
        """Load the most recent attribution result from DB."""
        try:
            async with self._sessionmaker() as session:
                row = await session.execute(
                    select(ModelLifecycleEvent)
                    .where(ModelLifecycleEvent.event_type == "attribution_result")
                    .order_by(desc(ModelLifecycleEvent.created_at))
                    .limit(1)
                )
                evt = row.scalars().first()
                if not evt:
                    return None
                p = evt.payload or {}
                result = AttributionResult(
                    window_start=p.get("window_start", ""),
                    window_end=p.get("window_end", ""),
                    reward_signals=p.get("reward_signals", {}),
                )
                for src, sd in p.get("strategies", {}).items():
                    perf = StrategyPerformance(source=src)
                    for k, v in sd.items():
                        if hasattr(perf, k):
                            try:
                                setattr(perf, k, type(getattr(perf, k))(v))
                            except Exception:
                                pass
                    result.strategies[src] = perf
                return result
        except Exception as e:
            logger.warning("Failed to load attribution", extra={"error": str(e)})
            return None

    # ── internal ─────────────────────────────────────────────────────

    async def _fetch_filled_orders(
        self,
        session: AsyncSession,
        start: datetime,
        end: datetime,
    ) -> list[Order]:
        """Fetch filled orders in the window."""
        result = await session.execute(
            select(Order)
            .where(
                Order.status.in_(["filled", "partially_filled"]),
                Order.updated_at >= start,
                Order.updated_at <= end,
            )
            .order_by(Order.updated_at)
        )
        return list(result.scalars().all())

    def _process_order(self, order: Order) -> TradeAttribution | None:
        """Convert a filled order into a trade attribution."""
        attrs = order.attributes or {}
        strategy_source = attrs.get("strategy_source", attrs.get("source", "unknown"))
        if not strategy_source or strategy_source == "unknown":
            # Try to extract from metadata
            meta = attrs.get("metadata", {})
            if isinstance(meta, dict):
                strategy_source = meta.get("strategy_source", "unknown")

        symbol = str(order.symbol)
        side = str(order.side).lower()
        qty = float(order.filled_qty or order.qty or 0)
        fill_price = float(order.avg_fill_price or 0)

        if qty <= 0 or fill_price <= 0:
            return None

        # Expected price (limit price or the submitted price from attributes)
        expected_price = float(order.limit_price or 0) or attrs.get("expected_price")
        try:
            expected_price = float(expected_price) if expected_price else None
        except (TypeError, ValueError):
            expected_price = None

        # Slippage
        slippage_bps = 0.0
        if expected_price and expected_price > 0:
            if side == "buy":
                slippage_bps = ((fill_price - expected_price) / expected_price) * 10000
            else:
                slippage_bps = ((expected_price - fill_price) / expected_price) * 10000

        # Reconstruct realized PnL via position tracking
        realized_pnl = self._update_position_pnl(strategy_source, symbol, side, qty, fill_price)

        fees = float(attrs.get("fees", 0.0))

        return TradeAttribution(
            id=str(order.id),
            symbol=symbol,
            strategy_source=strategy_source,
            side=side,
            qty=qty,
            fill_price=fill_price,
            expected_price=expected_price,
            realized_pnl=realized_pnl,
            slippage_bps=round(slippage_bps, 2),
            fees=fees,
            timestamp=order.updated_at.isoformat() if order.updated_at else "",
        )

    def _update_position_pnl(
        self, source: str, symbol: str, side: str, qty: float, fill_price: float
    ) -> float:
        """Track running position and compute realized PnL on closes.

        Uses average cost basis.
        """
        if source not in self._positions:
            self._positions[source] = {}
            self._avg_costs[source] = {}

        pos = self._positions[source].get(symbol, 0.0)
        avg_cost = self._avg_costs[source].get(symbol, 0.0)
        realized = 0.0

        signed_qty = qty if side == "buy" else -qty

        if pos == 0.0:
            # Opening position
            self._positions[source][symbol] = signed_qty
            self._avg_costs[source][symbol] = fill_price
        elif (pos > 0 and signed_qty > 0) or (pos < 0 and signed_qty < 0):
            # Adding to position — update avg cost
            total_cost = avg_cost * abs(pos) + fill_price * qty
            new_pos = pos + signed_qty
            self._positions[source][symbol] = new_pos
            self._avg_costs[source][symbol] = total_cost / abs(new_pos) if new_pos != 0 else 0
        else:
            # Reducing / closing position — realize PnL
            close_qty = min(abs(signed_qty), abs(pos))
            if pos > 0:
                realized = (fill_price - avg_cost) * close_qty
            else:
                realized = (avg_cost - fill_price) * close_qty

            remaining = abs(pos) - close_qty
            if remaining <= 0:
                # Fully closed or flipped
                self._positions[source][symbol] = pos + signed_qty
                if abs(pos + signed_qty) > 0:
                    self._avg_costs[source][symbol] = fill_price
                else:
                    self._avg_costs[source][symbol] = 0.0
            else:
                self._positions[source][symbol] = pos + signed_qty
                # avg cost stays the same for the remaining

        return realized

    def _compute_reward_signals(
        self, strategies: dict[str, StrategyPerformance]
    ) -> dict[str, float]:
        """Produce normalized reward signals for the living policy.

        reward = risk-adjusted PnL - slippage penalty - turnover penalty
        Clamped to [-1, 1].
        """
        rewards: dict[str, float] = {}
        for src, perf in strategies.items():
            if perf.trade_count == 0:
                rewards[src] = 0.0
                continue

            # Normalize PnL by turnover
            pnl_per_turnover = perf.total_pnl / max(perf.turnover_usd, 1.0)
            slippage_penalty = perf.avg_slippage_bps / 100.0  # convert bps to fraction
            turnover_penalty = min(perf.turnover_usd / 100_000.0, 0.1)  # penalize excessive turnover

            raw = pnl_per_turnover * 100 - slippage_penalty - turnover_penalty
            rewards[src] = max(-1.0, min(1.0, raw))

        return rewards

    def _compute_drawdowns(
        self,
        trades: list[TradeAttribution],
        strategies: dict[str, StrategyPerformance],
    ) -> None:
        """Compute max drawdown per strategy from the trade sequence."""
        cumulative: dict[str, float] = {}
        peak: dict[str, float] = {}
        max_dd: dict[str, float] = {}

        for trade in trades:
            src = trade.strategy_source
            cumulative[src] = cumulative.get(src, 0.0) + trade.realized_pnl
            peak[src] = max(peak.get(src, 0.0), cumulative[src])
            dd = peak[src] - cumulative[src]
            max_dd[src] = max(max_dd.get(src, 0.0), dd)

        for src, perf in strategies.items():
            perf.max_drawdown = max_dd.get(src, 0.0)

    def _compute_sharpe_proxies(
        self,
        trades: list[TradeAttribution],
        strategies: dict[str, StrategyPerformance],
    ) -> None:
        """Compute a Sharpe-like ratio from per-trade PnL."""
        import math

        pnls_by_src: dict[str, list[float]] = {}
        for trade in trades:
            pnls_by_src.setdefault(trade.strategy_source, []).append(trade.realized_pnl)

        for src, pnls in pnls_by_src.items():
            if len(pnls) < 2:
                continue
            mean = sum(pnls) / len(pnls)
            var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
            std = math.sqrt(var) if var > 0 else 1.0
            strategies[src].sharpe_proxy = round(mean / std, 4)

    async def _persist_attribution(
        self, session: AsyncSession, result: AttributionResult
    ) -> None:
        """Persist the attribution result for audit."""
        try:
            session.add(
                ModelLifecycleEvent(
                    model_id=None,
                    model_name="attribution",
                    model_version=None,
                    event_type="attribution_result",
                    payload=result.to_dict(),
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()
            logger.info(
                "Attribution persisted",
                extra={
                    "window": f"{result.window_start} → {result.window_end}",
                    "strategies": len(result.strategies),
                },
            )
        except Exception as e:
            logger.warning("Attribution persist failed", extra={"error": str(e)})
