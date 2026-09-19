"""Stocks-in-play ranking for shadow strategy engines.

This module is intentionally side-effect free. It turns minute bars plus optional
market metadata into an auditable score that ORB v2 and future catalyst engines
can use before any promotion or sizing decision exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

from backend.organism.sector_map import get_sector


@dataclass(frozen=True)
class StocksInPlayConfig:
    top_n: int = 20
    min_price: float = 5.0
    min_avg_volume_14d: float = 1_000_000.0
    min_dollar_volume: float = 2_500_000.0
    min_relative_volume: float = 1.25
    max_spread_bps: float = 25.0
    first_window_minutes: int = 15


@dataclass(frozen=True)
class StockInPlayScore:
    symbol: str
    score: float
    gap_pct: float
    first_window_rvol: float
    dollar_volume: float
    spread_bps: float
    premarket_range_pct: float
    opening_range_expansion_pct: float
    sector_shock_abs_bps: float
    earnings_or_news_score: float
    passed_liquidity: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "score": round(self.score, 6),
            "gap_pct": round(self.gap_pct, 4),
            "first_window_rvol": round(self.first_window_rvol, 4),
            "dollar_volume": round(self.dollar_volume, 2),
            "spread_bps": round(self.spread_bps, 4),
            "premarket_range_pct": round(self.premarket_range_pct, 4),
            "opening_range_expansion_pct": round(self.opening_range_expansion_pct, 4),
            "sector_shock_abs_bps": round(self.sector_shock_abs_bps, 4),
            "earnings_or_news_score": round(self.earnings_or_news_score, 4),
            "passed_liquidity": self.passed_liquidity,
            "reasons": list(self.reasons),
        }


class StocksInPlayScanner:
    """Rank symbols by catalyst, liquidity, volume, and opening movement."""

    def __init__(self, config: StocksInPlayConfig | None = None) -> None:
        self.config = config or StocksInPlayConfig()

    def rank(
        self,
        features_by_symbol: Mapping[str, pd.DataFrame],
        *,
        now: Any,
        metadata_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
        sector_returns_bps: Mapping[str, float] | None = None,
    ) -> list[StockInPlayScore]:
        metadata_by_symbol = metadata_by_symbol or {}
        sector_returns_bps = sector_returns_bps or {}
        scored: list[StockInPlayScore] = []
        for raw_symbol, bars in features_by_symbol.items():
            symbol = str(raw_symbol).upper()
            item = self._score_symbol(
                symbol,
                bars,
                now=now,
                metadata=metadata_by_symbol.get(symbol, {}),
                sector_returns_bps=sector_returns_bps,
            )
            if item is not None:
                scored.append(item)
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[: self.config.top_n]

    def _score_symbol(
        self,
        symbol: str,
        bars: pd.DataFrame,
        *,
        now: Any,
        metadata: Mapping[str, Any],
        sector_returns_bps: Mapping[str, float],
    ) -> StockInPlayScore | None:
        df = _prepare_bars(bars)
        if df is None:
            return None
        session = _session_bars(df, now)
        if session.empty:
            return None
        previous_close = _previous_close(df, session)
        latest_close = _safe_float(session["close"].iloc[-1])
        first_open = _safe_float(session["open"].iloc[0])
        if previous_close is None or previous_close <= 0 or latest_close <= 0 or first_open <= 0:
            return None

        first_window = session.head(self.config.first_window_minutes)
        if len(first_window) < min(5, self.config.first_window_minutes):
            return None
        gap_pct = (first_open - previous_close) / previous_close * 100.0
        first_volume = _sum(first_window.get("volume"))
        avg_first_window_volume = _safe_float(metadata.get("avg_first_window_volume"))
        if avg_first_window_volume <= 0:
            avg_first_window_volume = _historical_first_window_volume(
                df,
                session,
                self.config.first_window_minutes,
            )
        first_window_rvol = (
            first_volume / avg_first_window_volume if avg_first_window_volume > 0 else 1.0
        )
        dollar_volume = float((session["close"].astype(float) * session["volume"].astype(float)).sum())
        spread_bps = _metadata_or_last(metadata, session, "spread_bps", default=0.0)
        avg_volume_14d = _safe_float(metadata.get("avg_volume_14d"))
        if avg_volume_14d <= 0:
            avg_volume_14d = _estimate_avg_daily_volume(df, session)
        premarket_range_pct = _premarket_range_pct(df, now, previous_close)
        opening_range_expansion_pct = _range_pct(first_window, previous_close)
        sector = get_sector(symbol)
        sector_shock_abs_bps = abs(float(sector_returns_bps.get(sector, 0.0)))
        earnings_or_news_score = _bounded01(_safe_float(metadata.get("earnings_or_news_score")))

        reasons: list[str] = []
        if latest_close <= self.config.min_price:
            reasons.append("price_below_min")
        if avg_volume_14d < self.config.min_avg_volume_14d:
            reasons.append("avg_volume_below_min")
        if dollar_volume < self.config.min_dollar_volume:
            reasons.append("dollar_volume_below_min")
        if first_window_rvol < self.config.min_relative_volume:
            reasons.append("rvol_below_min")
        if spread_bps > self.config.max_spread_bps:
            reasons.append("spread_above_max")
        passed_liquidity = not reasons

        raw_score = (
            0.25 * _bounded01(abs(gap_pct) / 5.0)
            + 0.25 * _bounded01((first_window_rvol - 1.0) / 4.0)
            + 0.15 * _bounded01(dollar_volume / 50_000_000.0)
            + 0.10 * _bounded01(premarket_range_pct / 5.0)
            + 0.10 * _bounded01(opening_range_expansion_pct / 3.0)
            + 0.05 * _bounded01(sector_shock_abs_bps / 150.0)
            + 0.05 * _bounded01(1.0 - spread_bps / self.config.max_spread_bps)
            + 0.05 * earnings_or_news_score
        )
        score = raw_score if passed_liquidity else raw_score * 0.25
        return StockInPlayScore(
            symbol=symbol,
            score=score,
            gap_pct=gap_pct,
            first_window_rvol=first_window_rvol,
            dollar_volume=dollar_volume,
            spread_bps=spread_bps,
            premarket_range_pct=premarket_range_pct,
            opening_range_expansion_pct=opening_range_expansion_pct,
            sector_shock_abs_bps=sector_shock_abs_bps,
            earnings_or_news_score=earnings_or_news_score,
            passed_liquidity=passed_liquidity,
            reasons=tuple(reasons),
        )


def _prepare_bars(bars: pd.DataFrame | None) -> pd.DataFrame | None:
    if bars is None or len(bars) == 0:
        return None
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(set(bars.columns)):
        return None
    df = bars.copy()
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        if ts.isna().all():
            return None
        df = df.assign(_ts=ts).sort_values("_ts")
    elif df.index.dtype.kind == "M":
        ts = pd.to_datetime(pd.Series(df.index), utc=True)
        df = df.assign(_ts=ts.values).sort_values("_ts")
    else:
        return None
    return df.reset_index(drop=True)


def _session_bars(df: pd.DataFrame, now: Any) -> pd.DataFrame:
    ts_utc = pd.to_datetime(df["_ts"], utc=True)
    ts_et = ts_utc.dt.tz_convert("America/New_York")
    now_ts = pd.Timestamp(now)
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    session_date = now_ts.tz_convert("America/New_York").date()
    mask = (ts_et.dt.date == session_date) & (ts_utc <= now_ts)
    return df[mask].reset_index(drop=True)


def _previous_close(df: pd.DataFrame, session: pd.DataFrame) -> float | None:
    if session.empty:
        return None
    previous = df[df["_ts"] < session["_ts"].iloc[0]]
    if previous.empty:
        return None
    value = _safe_float(previous["close"].iloc[-1])
    return value if value > 0 else None


def _historical_first_window_volume(
    df: pd.DataFrame,
    session: pd.DataFrame,
    window_minutes: int,
) -> float:
    current_start = session["_ts"].iloc[0]
    previous = df[df["_ts"] < current_start].copy()
    if previous.empty:
        return 0.0
    previous["_date_et"] = pd.to_datetime(previous["_ts"], utc=True).dt.tz_convert(
        "America/New_York",
    ).dt.date
    daily = previous.groupby("_date_et").head(window_minutes).groupby("_date_et")["volume"].sum()
    return float(daily.tail(14).mean()) if len(daily) else 0.0


def _estimate_avg_daily_volume(df: pd.DataFrame, session: pd.DataFrame) -> float:
    previous = df[df["_ts"] < session["_ts"].iloc[0]].copy()
    if previous.empty:
        return _sum(session.get("volume"))
    previous["_date_et"] = pd.to_datetime(previous["_ts"], utc=True).dt.tz_convert(
        "America/New_York",
    ).dt.date
    daily = previous.groupby("_date_et")["volume"].sum()
    return float(daily.tail(14).mean()) if len(daily) else _sum(session.get("volume"))


def _premarket_range_pct(df: pd.DataFrame, now: Any, previous_close: float) -> float:
    if previous_close <= 0:
        return 0.0
    ts_et = pd.to_datetime(df["_ts"], utc=True).dt.tz_convert("America/New_York")
    now_ts = pd.Timestamp(now)
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    session_date = now_ts.tz_convert("America/New_York").date()
    mask = (ts_et.dt.date == session_date) & (ts_et.dt.time < pd.Timestamp("09:30").time())
    pre = df[mask]
    if pre.empty:
        return 0.0
    return (float(pre["high"].max()) - float(pre["low"].min())) / previous_close * 100.0


def _range_pct(window: pd.DataFrame, base_price: float) -> float:
    if window.empty or base_price <= 0:
        return 0.0
    return (float(window["high"].max()) - float(window["low"].min())) / base_price * 100.0


def _metadata_or_last(
    metadata: Mapping[str, Any],
    session: pd.DataFrame,
    key: str,
    *,
    default: float,
) -> float:
    value = _safe_float(metadata.get(key))
    if value > 0:
        return value
    if key in session.columns:
        return _safe_float(session[key].iloc[-1])
    return default


def _sum(series: Any) -> float:
    if series is None:
        return 0.0
    return float(pd.Series(series).astype(float).sum())


def _safe_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if pd.notna(result) else 0.0


def _bounded01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
