"""Shadow-only single-name end-of-day reversal engine."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import time as dtime
from typing import Any, Iterable

import pandas as pd

from backend.organism.schema.candidate_signal import CandidateSignal


@dataclass(frozen=True)
class EODReversalConfig:
    decision_start_et: dtime = dtime(15, 25)
    decision_end_et: dtime = dtime(15, 50)
    flatten_time_et: dtime = dtime(15, 58)
    min_intraday_move_bps: float = 120.0
    min_reversal_volume_ratio: float = 1.0
    intended_horizon_bars: int = 20
    long_only: bool = True


class EODReversalShadowEngine:
    """Generate shadow candidates for late-day single-name reversals."""

    strategy_id = "eod_reversal_shadow"
    engine_version = "eod_reversal_shadow.v1"
    shadow_only = True

    def __init__(
        self,
        *,
        universe: Iterable[str] | None = None,
        config: EODReversalConfig | None = None,
    ) -> None:
        self.universe = tuple(str(sym).upper() for sym in universe) if universe else None
        self.config = config or EODReversalConfig()

    def generate_signals(self, context: dict[str, Any]) -> list[CandidateSignal]:
        now = context.get("now") or context.get("timestamp")
        if now is None or not self._in_decision_window(now):
            return []
        features_by_symbol = context.get("features_by_symbol") or {}
        symbols = self.universe or tuple(str(sym).upper() for sym in features_by_symbol)
        signals: list[CandidateSignal] = []
        for symbol in symbols:
            state = _eod_reversal_state(features_by_symbol.get(symbol), now)
            if state is None:
                continue
            intraday_bps = state["intraday_move_bps"]
            if abs(intraday_bps) < self.config.min_intraday_move_bps:
                continue
            side = "long" if intraday_bps < 0 else "short"
            if side == "short" and self.config.long_only:
                continue
            reversal_ok = (
                state["latest_return_bps"] > 0
                if side == "long"
                else state["latest_return_bps"] < 0
            )
            if not reversal_ok:
                continue
            if state["volume_ratio"] < self.config.min_reversal_volume_ratio:
                continue
            signals.append(
                CandidateSignal(
                    signal_id=_signal_id(symbol, now, "eod_reversal_shadow"),
                    strategy_id=self.strategy_id,
                    engine_version=self.engine_version,
                    symbol=symbol,
                    side=side,
                    timeframe="1Min",
                    created_at=now,
                    intended_horizon_bars=self.config.intended_horizon_bars,
                    regime=str(context.get("regime") or "unknown"),
                    evidence_tier=0,
                    shadow_only=True,
                    expected_edge_bps=None,
                    confidence=min(0.75, 0.35 + abs(intraday_bps) / 1000.0),
                    stop_price=None,
                    target_price=None,
                    risk_budget_bps=0.0,
                    features={
                        "variant": "eod_single_name_reversal",
                        "intraday_move_bps": round(intraday_bps, 4),
                        "latest_return_bps": round(state["latest_return_bps"], 4),
                        "volume_ratio": round(state["volume_ratio"], 4),
                        "flatten_time_et": self.config.flatten_time_et.isoformat(),
                        "live_enabled": False,
                    },
                )
            )
        return signals

    def _in_decision_window(self, now: Any) -> bool:
        ts = pd.Timestamp(now)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        et = ts.tz_convert("America/New_York").time()
        return self.config.decision_start_et <= et <= self.config.decision_end_et


def _eod_reversal_state(bars: pd.DataFrame | None, now: Any) -> dict[str, float] | None:
    df = _prepare_bars(bars)
    if df is None:
        return None
    session = _session_bars(df, now)
    if len(session) < 30:
        return None
    open_price = float(session["open"].iloc[0])
    latest = float(session["close"].iloc[-1])
    previous = float(session["close"].iloc[-2])
    if open_price <= 0 or previous <= 0:
        return None
    recent_volume = float(session["volume"].astype(float).tail(3).mean())
    baseline_volume = float(session["volume"].astype(float).iloc[:-3].tail(30).mean())
    return {
        "intraday_move_bps": (latest - open_price) / open_price * 10000.0,
        "latest_return_bps": (latest - previous) / previous * 10000.0,
        "volume_ratio": recent_volume / baseline_volume if baseline_volume > 0 else 0.0,
    }


def _prepare_bars(bars: pd.DataFrame | None) -> pd.DataFrame | None:
    if bars is None or len(bars) == 0:
        return None
    required = {"open", "close", "volume"}
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
    ts_et = pd.to_datetime(df["_ts"], utc=True).dt.tz_convert("America/New_York")
    now_ts = pd.Timestamp(now)
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    session_date = now_ts.tz_convert("America/New_York").date()
    return df[ts_et.dt.date == session_date].reset_index(drop=True)


def _signal_id(symbol: str, now: Any, variant: str) -> str:
    payload = f"{symbol}|{pd.Timestamp(now).isoformat()}|{variant}"
    return hashlib.sha256(payload.encode()).hexdigest()[:24]
