"""Shadow-only residualized mean-reversion engine."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd

from backend.organism.schema.candidate_signal import CandidateSignal
from backend.organism.sector_map import get_sector


SECTOR_ETF_MAP: dict[str, str] = {
    "Technology": "XLK",
    "Energy": "XLE",
    "Index": "SPY",
    "Communication Services": "QQQ",
    "Consumer Discretionary": "QQQ",
    "Financials": "SPY",
    "Healthcare": "SPY",
    "Industrials": "SPY",
}


@dataclass(frozen=True)
class ResidualMeanReversionConfig:
    active_regimes: tuple[str, ...] = ("chop", "low_vol", "liquidity_reversion")
    lookback_bars: int = 120
    min_abs_residual_z: float = 2.0
    intended_horizon_bars: int = 20
    long_only: bool = True
    exclude_symbols: tuple[str, ...] = ("SPY", "QQQ", "IWM", "XLK", "XLE", "SH", "PSQ")


class ResidualMeanReversionEngine:
    """Trade idiosyncratic residual extremes in shadow mode only."""

    strategy_id = "residual_mean_reversion"
    engine_version = "residual_mean_reversion.v1"
    shadow_only = True

    def __init__(
        self,
        *,
        universe: Iterable[str] | None = None,
        config: ResidualMeanReversionConfig | None = None,
    ) -> None:
        self.universe = tuple(str(sym).upper() for sym in universe) if universe else None
        self.config = config or ResidualMeanReversionConfig()

    def generate_signals(self, context: dict[str, Any]) -> list[CandidateSignal]:
        regime = str(context.get("regime") or "unknown").lower()
        if regime not in self.config.active_regimes:
            return []
        now = context.get("now") or context.get("timestamp")
        if now is None:
            return []
        features_by_symbol = context.get("features_by_symbol") or {}
        symbols = self.universe or tuple(str(sym).upper() for sym in features_by_symbol)
        signals: list[CandidateSignal] = []
        for symbol in symbols:
            if symbol in self.config.exclude_symbols:
                continue
            residual = _residual_state(symbol, features_by_symbol, self.config.lookback_bars, now)
            if residual is None:
                continue
            residual_z = residual["residual_z"]
            if abs(residual_z) < self.config.min_abs_residual_z:
                continue
            side = "long" if residual_z < 0 else "short"
            if side == "short" and self.config.long_only:
                continue
            signals.append(
                CandidateSignal(
                    signal_id=_signal_id(symbol, now, "residual_mean_reversion"),
                    strategy_id=self.strategy_id,
                    engine_version=self.engine_version,
                    symbol=symbol,
                    side=side,
                    timeframe="1Min",
                    created_at=now,
                    intended_horizon_bars=self.config.intended_horizon_bars,
                    regime=regime,
                    evidence_tier=0,
                    shadow_only=True,
                    expected_edge_bps=None,
                    confidence=min(0.80, 0.35 + abs(residual_z) * 0.08),
                    stop_price=None,
                    target_price=None,
                    risk_budget_bps=0.0,
                    features={
                        "variant": "sector_market_residual_zscore",
                        "residual_z": round(residual_z, 4),
                        "latest_residual_bps": round(residual["latest_residual_bps"], 4),
                        "beta_spy": round(residual["beta_spy"], 4),
                        "beta_qqq": round(residual["beta_qqq"], 4),
                        "beta_sector": round(residual["beta_sector"], 4),
                        "sector": residual["sector"],
                        "sector_etf": residual["sector_etf"],
                        "live_enabled": False,
                    },
                )
            )
        return signals


def _residual_state(
    symbol: str,
    features_by_symbol: dict[str, pd.DataFrame],
    lookback_bars: int,
    now: Any,
) -> dict[str, Any] | None:
    stock_returns = _returns(features_by_symbol.get(symbol), lookback_bars, now)
    spy_returns = _returns(features_by_symbol.get("SPY"), lookback_bars, now)
    qqq_returns = _returns(features_by_symbol.get("QQQ"), lookback_bars, now)
    sector = get_sector(symbol)
    sector_etf = SECTOR_ETF_MAP.get(sector, "SPY")
    sector_returns = _returns(features_by_symbol.get(sector_etf), lookback_bars, now)
    if stock_returns is None or spy_returns is None or qqq_returns is None:
        return None
    sector_series_source = sector_returns if sector_returns is not None else spy_returns
    aligned = pd.concat(
        [stock_returns, spy_returns, qqq_returns, sector_series_source],
        axis=1,
        join="inner",
    ).dropna()
    if len(aligned) < max(30, lookback_bars // 2):
        return None
    stock = aligned.iloc[:, 0]
    spy = aligned.iloc[:, 1]
    qqq = aligned.iloc[:, 2]
    sector_series = aligned.iloc[:, 3]
    beta_spy = _beta(stock, spy)
    beta_qqq = _beta(stock, qqq)
    beta_sector = _beta(stock, sector_series)
    fitted = beta_spy * spy * 0.45 + beta_qqq * qqq * 0.25 + beta_sector * sector_series * 0.30
    residuals = stock - fitted
    latest = float(residuals.iloc[-1])
    mean = float(residuals.iloc[:-1].mean())
    std = float(residuals.iloc[:-1].std(ddof=0))
    if std <= 0 or not math.isfinite(std):
        return None
    return {
        "residual_z": (latest - mean) / std,
        "latest_residual_bps": latest * 10000.0,
        "beta_spy": beta_spy,
        "beta_qqq": beta_qqq,
        "beta_sector": beta_sector,
        "sector": sector,
        "sector_etf": sector_etf,
    }


def _returns(
    bars: pd.DataFrame | None,
    lookback_bars: int,
    now: Any,
) -> pd.Series | None:
    if bars is None or len(bars) < 5 or "close" not in bars.columns:
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
    now_ts = pd.Timestamp(now)
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    df = df[pd.to_datetime(df["_ts"], utc=True) <= now_ts]
    series = df.set_index("_ts")["close"].astype(float).pct_change().dropna().tail(lookback_bars)
    return series if len(series) >= min(30, lookback_bars) else None


def _beta(y: pd.Series, x: pd.Series) -> float:
    variance = float(x.var(ddof=0))
    if variance <= 0 or not math.isfinite(variance):
        return 0.0
    return float(y.cov(x) / variance)


def _signal_id(symbol: str, now: Any, variant: str) -> str:
    payload = f"{symbol}|{pd.Timestamp(now).isoformat()}|{variant}"
    return hashlib.sha256(payload.encode()).hexdigest()[:24]
