"""Benchmark comparisons for strategy signals and realized trades."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean
from typing import Iterable


def _finite(value: float | int | None, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def directional_return_bps(entry_price: float, exit_price: float, side: str = "long") -> float:
    entry = _finite(entry_price)
    exit_ = _finite(exit_price)
    if entry <= 0:
        return 0.0
    raw = (exit_ - entry) / entry * 10000.0
    return raw if str(side).lower() == "long" else -raw


@dataclass(frozen=True)
class BenchmarkComparison:
    signal_id: str
    strategy_id: str
    symbol: str
    side: str
    realized_bps: float
    same_symbol_hold_bps: float
    market_benchmark_bps: float | None = None
    sector_benchmark_bps: float | None = None
    random_null_bps: float | None = None
    delay_1_bps: float | None = None
    delay_5_bps: float | None = None
    delay_10_bps: float | None = None
    cost_bps: float = 0.0

    @property
    def net_realized_bps(self) -> float:
        return self.realized_bps - self.cost_bps

    @property
    def alpha_over_symbol_hold_bps(self) -> float:
        return self.net_realized_bps - self.same_symbol_hold_bps

    @property
    def alpha_over_market_bps(self) -> float | None:
        if self.market_benchmark_bps is None:
            return None
        return self.net_realized_bps - self.market_benchmark_bps

    @property
    def alpha_over_sector_bps(self) -> float | None:
        if self.sector_benchmark_bps is None:
            return None
        return self.net_realized_bps - self.sector_benchmark_bps

    @property
    def alpha_over_random_bps(self) -> float | None:
        if self.random_null_bps is None:
            return None
        return self.net_realized_bps - self.random_null_bps

    def alpha_over_delay_bps(self, delay_bars: int) -> float | None:
        delay = {
            1: self.delay_1_bps,
            5: self.delay_5_bps,
            10: self.delay_10_bps,
        }.get(delay_bars)
        if delay is None:
            return None
        return self.net_realized_bps - delay

    def to_dict(self) -> dict[str, float | str | None]:
        return {
            "signal_id": self.signal_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side,
            "realized_bps": round(self.realized_bps, 6),
            "net_realized_bps": round(self.net_realized_bps, 6),
            "same_symbol_hold_bps": round(self.same_symbol_hold_bps, 6),
            "market_benchmark_bps": _round_optional(self.market_benchmark_bps),
            "sector_benchmark_bps": _round_optional(self.sector_benchmark_bps),
            "random_null_bps": _round_optional(self.random_null_bps),
            "delay_1_bps": _round_optional(self.delay_1_bps),
            "delay_5_bps": _round_optional(self.delay_5_bps),
            "delay_10_bps": _round_optional(self.delay_10_bps),
            "cost_bps": round(self.cost_bps, 6),
            "alpha_over_symbol_hold_bps": round(self.alpha_over_symbol_hold_bps, 6),
            "alpha_over_market_bps": _round_optional(self.alpha_over_market_bps),
            "alpha_over_sector_bps": _round_optional(self.alpha_over_sector_bps),
            "alpha_over_random_bps": _round_optional(self.alpha_over_random_bps),
            "alpha_over_delay_1_bps": _round_optional(self.alpha_over_delay_bps(1)),
            "alpha_over_delay_5_bps": _round_optional(self.alpha_over_delay_bps(5)),
            "alpha_over_delay_10_bps": _round_optional(self.alpha_over_delay_bps(10)),
        }


def _round_optional(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def summarize_benchmarks(rows: Iterable[BenchmarkComparison]) -> dict[str, object]:
    data = list(rows)
    if not data:
        return {
            "n": 0,
            "avg_net_realized_bps": 0.0,
            "avg_alpha_over_symbol_hold_bps": 0.0,
            "avg_alpha_over_market_bps": None,
            "avg_alpha_over_random_bps": None,
            "positive_symbol_alpha_rate": 0.0,
        }

    def avg_optional(values: Iterable[float | None]) -> float | None:
        finite = [float(v) for v in values if v is not None and math.isfinite(float(v))]
        return round(fmean(finite), 6) if finite else None

    symbol_alphas = [r.alpha_over_symbol_hold_bps for r in data]
    return {
        "n": len(data),
        "avg_net_realized_bps": round(fmean(r.net_realized_bps for r in data), 6),
        "avg_alpha_over_symbol_hold_bps": round(fmean(symbol_alphas), 6),
        "avg_alpha_over_market_bps": avg_optional(r.alpha_over_market_bps for r in data),
        "avg_alpha_over_random_bps": avg_optional(r.alpha_over_random_bps for r in data),
        "positive_symbol_alpha_rate": round(sum(1 for v in symbol_alphas if v > 0) / len(symbol_alphas), 6),
    }
