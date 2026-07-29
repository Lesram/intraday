"""Microstructure feature schema for future order-flow research.

The platform does not currently have reliable Level 2/order-book data. This
schema gives future collectors a strict contract without activating any live
strategy that depends on these fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class MicrostructureSnapshot:
    symbol: str
    timestamp: datetime | str
    bid_price_1: float
    ask_price_1: float
    bid_size_1: float
    ask_size_1: float
    spread_bps: float
    order_flow_imbalance: float
    trade_imbalance: float
    aggressive_buy_ratio: float
    aggressive_sell_ratio: float
    quote_update_rate: float
    depth_imbalance: float

    def __post_init__(self) -> None:
        symbol = str(self.symbol or "").upper().strip()
        ts = _parse_dt(self.timestamp)
        bid = float(self.bid_price_1)
        ask = float(self.ask_price_1)
        bid_size = float(self.bid_size_1)
        ask_size = float(self.ask_size_1)
        if not symbol:
            raise ValueError("symbol is required")
        if bid <= 0 or ask <= 0 or bid >= ask:
            raise ValueError("bid_price_1 must be positive and below ask_price_1")
        if bid_size < 0 or ask_size < 0:
            raise ValueError("top-of-book sizes must be non-negative")
        if float(self.spread_bps) < 0:
            raise ValueError("spread_bps must be non-negative")
        for field_name in (
            "order_flow_imbalance",
            "trade_imbalance",
            "aggressive_buy_ratio",
            "aggressive_sell_ratio",
            "depth_imbalance",
        ):
            value = float(getattr(self, field_name))
            if not -1.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be in [-1, 1]")
        if float(self.quote_update_rate) < 0:
            raise ValueError("quote_update_rate must be non-negative")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "timestamp", ts)

    @property
    def mid_price(self) -> float:
        return (float(self.bid_price_1) + float(self.ask_price_1)) / 2.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "bid_price_1": float(self.bid_price_1),
            "ask_price_1": float(self.ask_price_1),
            "bid_size_1": float(self.bid_size_1),
            "ask_size_1": float(self.ask_size_1),
            "spread_bps": float(self.spread_bps),
            "order_flow_imbalance": float(self.order_flow_imbalance),
            "trade_imbalance": float(self.trade_imbalance),
            "aggressive_buy_ratio": float(self.aggressive_buy_ratio),
            "aggressive_sell_ratio": float(self.aggressive_sell_ratio),
            "quote_update_rate": float(self.quote_update_rate),
            "depth_imbalance": float(self.depth_imbalance),
            "mid_price": self.mid_price,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MicrostructureSnapshot":
        return cls(
            symbol=payload["symbol"],
            timestamp=payload["timestamp"],
            bid_price_1=payload["bid_price_1"],
            ask_price_1=payload["ask_price_1"],
            bid_size_1=payload["bid_size_1"],
            ask_size_1=payload["ask_size_1"],
            spread_bps=payload["spread_bps"],
            order_flow_imbalance=payload["order_flow_imbalance"],
            trade_imbalance=payload["trade_imbalance"],
            aggressive_buy_ratio=payload["aggressive_buy_ratio"],
            aggressive_sell_ratio=payload["aggressive_sell_ratio"],
            quote_update_rate=payload["quote_update_rate"],
            depth_imbalance=payload["depth_imbalance"],
        )


def _parse_dt(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
