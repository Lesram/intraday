"""Daily strategy league table and promotion verdict helpers."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from statistics import fmean
from typing import Any, Iterable


@dataclass(frozen=True)
class StrategyLeagueRow:
    strategy_id: str
    symbol: str
    session: str
    pnl: float
    realized_bps: float = 0.0
    r_multiple: float = 0.0
    mfe: float = 0.0
    mae: float = 0.0
    alpha_over_symbol_hold_bps: float | None = None
    alpha_over_market_bps: float | None = None
    alpha_over_random_bps: float | None = None
    alpha_over_delay_1_bps: float | None = None
    alpha_over_delay_5_bps: float | None = None
    alpha_over_delay_10_bps: float | None = None


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _optional(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def row_from_mapping(row: dict[str, Any]) -> StrategyLeagueRow:
    return StrategyLeagueRow(
        strategy_id=str(row.get("strategy_id") or "alpha_baseline").strip().lower(),
        symbol=str(row.get("symbol") or "").strip().upper(),
        session=str(row.get("session") or row.get("date") or ""),
        pnl=_finite(row.get("pnl")),
        realized_bps=_finite(row.get("realized_bps")),
        r_multiple=_finite(row.get("r_multiple") or row.get("r")),
        mfe=_finite(row.get("mfe")),
        mae=_finite(row.get("mae")),
        alpha_over_symbol_hold_bps=_optional(row.get("alpha_over_symbol_hold_bps")),
        alpha_over_market_bps=_optional(row.get("alpha_over_market_bps")),
        alpha_over_random_bps=_optional(row.get("alpha_over_random_bps")),
        alpha_over_delay_1_bps=_optional(row.get("alpha_over_delay_1_bps")),
        alpha_over_delay_5_bps=_optional(row.get("alpha_over_delay_5_bps")),
        alpha_over_delay_10_bps=_optional(row.get("alpha_over_delay_10_bps")),
    )


def profit_factor(pnls: Iterable[float]) -> float:
    gains = sum(p for p in pnls if p > 0)
    losses = abs(sum(p for p in pnls if p < 0))
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def max_drawdown(pnls: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def build_strategy_league(
    rows: Iterable[StrategyLeagueRow | dict[str, Any]],
    *,
    min_replay_samples: int = 30,
    min_profit_factor: float = 1.20,
    min_positive_alpha_rate: float = 0.52,
    max_symbol_concentration: float = 0.30,
    max_session_concentration: float = 0.25,
) -> list[dict[str, Any]]:
    normalized = [
        row if isinstance(row, StrategyLeagueRow) else row_from_mapping(row)
        for row in rows
    ]
    groups: dict[str, list[StrategyLeagueRow]] = defaultdict(list)
    for row in normalized:
        groups[row.strategy_id or "alpha_baseline"].append(row)

    out = []
    for strategy_id, group in sorted(groups.items()):
        pnls = [row.pnl for row in group]
        wins = [p for p in pnls if p > 0]
        pf = profit_factor(pnls)
        symbol_totals = _abs_concentration(group, "symbol")
        session_totals = _abs_concentration(group, "session")
        symbol_conc = max(symbol_totals.values(), default=0.0)
        session_conc = max(session_totals.values(), default=0.0)
        symbol_alphas = [
            row.alpha_over_symbol_hold_bps
            for row in group
            if row.alpha_over_symbol_hold_bps is not None
        ]
        random_alphas = [
            row.alpha_over_random_bps
            for row in group
            if row.alpha_over_random_bps is not None
        ]
        delay_alphas = [
            row.alpha_over_delay_1_bps
            for row in group
            if row.alpha_over_delay_1_bps is not None
        ] + [
            row.alpha_over_delay_5_bps
            for row in group
            if row.alpha_over_delay_5_bps is not None
        ] + [
            row.alpha_over_delay_10_bps
            for row in group
            if row.alpha_over_delay_10_bps is not None
        ]
        pos_symbol_alpha_rate = _positive_rate(symbol_alphas)
        verdict = _verdict(
            n=len(group),
            pf=pf,
            avg_r=fmean(row.r_multiple for row in group) if group else 0.0,
            symbol_alphas=symbol_alphas,
            random_alphas=random_alphas,
            delay_alphas=delay_alphas,
            pos_symbol_alpha_rate=pos_symbol_alpha_rate,
            symbol_concentration=symbol_conc,
            session_concentration=session_conc,
            min_replay_samples=min_replay_samples,
            min_profit_factor=min_profit_factor,
            min_positive_alpha_rate=min_positive_alpha_rate,
            max_symbol_concentration=max_symbol_concentration,
            max_session_concentration=max_session_concentration,
        )
        out.append({
            "strategy_id": strategy_id,
            "n": len(group),
            "total_pnl": round(sum(pnls), 6),
            "profit_factor": round(pf, 6) if math.isfinite(pf) else "inf",
            "win_rate": round(len(wins) / len(group), 6) if group else 0.0,
            "avg_r": round(fmean(row.r_multiple for row in group), 6) if group else 0.0,
            "avg_realized_bps": round(fmean(row.realized_bps for row in group), 6) if group else 0.0,
            "avg_alpha_over_symbol_hold_bps": _avg(symbol_alphas),
            "avg_alpha_over_random_bps": _avg(random_alphas),
            "avg_alpha_over_delay_bps": _avg(delay_alphas),
            "positive_symbol_alpha_rate": pos_symbol_alpha_rate,
            "max_drawdown": round(max_drawdown(pnls), 6),
            "max_symbol_concentration": round(symbol_conc, 6),
            "max_session_concentration": round(session_conc, 6),
            "verdict": verdict,
        })
    return out


def _avg(values: list[float]) -> float | None:
    return round(fmean(values), 6) if values else None


def _positive_rate(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(1 for value in values if value > 0) / len(values), 6)


def _abs_concentration(rows: list[StrategyLeagueRow], field: str) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    total_abs = sum(abs(row.pnl) for row in rows)
    if total_abs <= 0:
        return {}
    for row in rows:
        key = str(getattr(row, field) or "<blank>")
        totals[key] += abs(row.pnl) / total_abs
    return dict(totals)


def _verdict(
    *,
    n: int,
    pf: float,
    avg_r: float,
    symbol_alphas: list[float],
    random_alphas: list[float],
    delay_alphas: list[float],
    pos_symbol_alpha_rate: float,
    symbol_concentration: float,
    session_concentration: float,
    min_replay_samples: int,
    min_profit_factor: float,
    min_positive_alpha_rate: float,
    max_symbol_concentration: float,
    max_session_concentration: float,
) -> str:
    if n < min_replay_samples:
        return "collect_more"
    if pf < min_profit_factor or avg_r <= 0:
        return "reject"
    if not symbol_alphas or _avg(symbol_alphas) is None or _avg(symbol_alphas) <= 0:
        return "reject"
    if pos_symbol_alpha_rate < min_positive_alpha_rate:
        return "reject"
    if random_alphas and (_avg(random_alphas) is None or _avg(random_alphas) <= 0):
        return "reject"
    if delay_alphas and (_avg(delay_alphas) is None or _avg(delay_alphas) <= 0):
        return "reject"
    if (
        symbol_concentration > max_symbol_concentration
        or session_concentration > max_session_concentration
    ):
        return "collect_more_concentration_risk"
    return "replay_eligible"
