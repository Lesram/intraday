"""Shadow-only ETF/index intraday momentum engine.

Phase 9B.1 implements the top research lane from the strategy rebuild
roadmap.  The engine emits CandidateSignal objects only; it does not submit
orders and is not wired into live trading in this slice.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import time as dtime
from typing import Any, Iterable

import pandas as pd

from backend.organism.engines.gamma_vol_proxy import GammaVolProxy
from backend.organism.schema.candidate_signal import CandidateSignal


DEFAULT_ETF_UNIVERSE: tuple[str, ...] = ("SPY", "QQQ", "IWM", "XLK", "XLE")
INVERSE_ROUTE: dict[str, str] = {"SPY": "SH", "QQQ": "PSQ"}


@dataclass(frozen=True)
class MomentumConfig:
    decision_start_et: dtime = dtime(15, 20)
    decision_end_et: dtime = dtime(15, 40)
    exit_time_et: dtime = dtime(15, 58)
    min_first_half_hour_bps: float = 15.0
    min_rest_of_day_bps: float = 20.0
    min_expected_edge_bps: float = 2.0
    intended_horizon_bars: int = 30


class ETFIntradayMomentumEngine:
    """Generate shadow signals for ETF/index late-day momentum."""

    strategy_id = "etf_intraday_momentum"
    engine_version = "etf_intraday_momentum.v1"
    shadow_only = True

    def __init__(
        self,
        *,
        universe: Iterable[str] = DEFAULT_ETF_UNIVERSE,
        config: MomentumConfig | None = None,
        gamma_proxy: GammaVolProxy | None = None,
    ) -> None:
        self.universe = tuple(str(sym).upper() for sym in universe)
        self.config = config or MomentumConfig()
        self.gamma_proxy = gamma_proxy or GammaVolProxy()

    def generate_signals(self, context: dict[str, Any]) -> list[CandidateSignal]:
        features_by_symbol = context.get("features_by_symbol") or {}
        now = context.get("now") or context.get("timestamp")
        regime = str(context.get("regime") or "unknown")
        if now is None:
            return []
        if not self._in_decision_window(now):
            return []

        signals: list[CandidateSignal] = []
        for symbol in self.universe:
            bars = features_by_symbol.get(symbol)
            state = self.gamma_proxy.evaluate(symbol, bars, now)
            stats = _momentum_stats(bars, now)
            if state is None or stats is None:
                continue
            first_bps = stats["first_half_hour_bps"]
            rest_bps = stats["rest_of_day_bps"]
            direction = 1 if first_bps > 0 else -1 if first_bps < 0 else 0
            if direction == 0:
                continue
            if rest_bps * direction <= 0:
                continue
            if abs(first_bps) < self.config.min_first_half_hour_bps:
                continue
            if abs(rest_bps) < self.config.min_rest_of_day_bps:
                continue
            if not state.high_vol_trend_day:
                continue

            side = "long" if direction > 0 else "short"
            expected_edge_bps = max(
                self.config.min_expected_edge_bps,
                0.20 * min(abs(first_bps), abs(rest_bps)),
            )
            features = {
                "variant": "mim_a_first_30m_confirmed_rest_of_day",
                "first_half_hour_bps": round(first_bps, 4),
                "rest_of_day_bps": round(rest_bps, 4),
                "decision_time_et": stats["decision_time_et"],
                "exit_time_et": self.config.exit_time_et.isoformat(),
                "inverse_route_symbol": INVERSE_ROUTE.get(symbol, "") if direction < 0 else "",
                "gamma_vol_proxy": state.to_dict(),
                "live_enabled": False,
            }
            signals.append(
                CandidateSignal(
                    signal_id=_signal_id(symbol, now, features["variant"]),
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
                    expected_edge_bps=expected_edge_bps,
                    confidence=_confidence_from_state(state.realized_vol_z, state.volume_z),
                    stop_price=None,
                    target_price=None,
                    risk_budget_bps=0.0,
                    features=features,
                )
            )
        return signals

    def _in_decision_window(self, now: Any) -> bool:
        ts = pd.Timestamp(now)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        et = ts.tz_convert("America/New_York").time()
        return bool(self.config.decision_start_et <= et <= self.config.decision_end_et)


def _momentum_stats(bars: pd.DataFrame | None, now: Any) -> dict[str, Any] | None:
    prepared = _prepare_bars(bars)
    if prepared is None:
        return None
    session = _session_bars(prepared, now)
    if len(session) < 60:
        return None
    prev_close = _previous_close(prepared, session)
    if prev_close is None or prev_close <= 0:
        return None
    first_30_close = float(session["close"].iloc[min(len(session) - 1, 29)])
    latest_close = float(session["close"].iloc[-1])
    first_bps = (first_30_close - prev_close) / prev_close * 10000.0
    rest_bps = (latest_close - prev_close) / prev_close * 10000.0
    now_ts = pd.Timestamp(now)
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    return {
        "first_half_hour_bps": first_bps,
        "rest_of_day_bps": rest_bps,
        "decision_time_et": now_ts.tz_convert("America/New_York").time().isoformat(),
    }


def _prepare_bars(bars: pd.DataFrame | None) -> pd.DataFrame | None:
    if bars is None or len(bars) == 0 or not {"open", "close"}.issubset(bars.columns):
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
    first_ts = session["_ts"].iloc[0]
    previous = df[df["_ts"] < first_ts]
    if previous.empty:
        return None
    try:
        return float(previous["close"].iloc[-1])
    except (TypeError, ValueError):
        return None


def _confidence_from_state(realized_vol_z: float, volume_z: float) -> float:
    raw = 0.45 + 0.10 * max(0.0, min(realized_vol_z, 2.0)) + 0.05 * max(0.0, min(volume_z, 2.0))
    return round(min(raw, 0.80), 4)


def _signal_id(symbol: str, now: Any, variant: str) -> str:
    payload = f"{symbol}|{pd.Timestamp(now).isoformat()}|{variant}"
    return hashlib.sha256(payload.encode()).hexdigest()[:24]
