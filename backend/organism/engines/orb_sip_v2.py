"""Shadow-only stocks-in-play ORB v2 engine."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import time as dtime
from typing import Any

import pandas as pd

from backend.organism.schema.candidate_signal import CandidateSignal
from backend.organism.universe.stocks_in_play import StocksInPlayScanner


@dataclass(frozen=True)
class ORBSIPV2Config:
    opening_minutes: int = 5
    entry_start_et: dtime = dtime(9, 35)
    entry_end_et: dtime = dtime(15, 30)
    min_relative_volume: float = 1.5
    min_volume_confirmation: float = 1.2
    max_market_selloff_bps: float = -75.0
    intended_horizon_bars: int = 60
    long_only: bool = True


class ORBSIPV2Engine:
    """Generate shadow ORB candidates only after stocks-in-play selection."""

    strategy_id = "orb_sip_v2"
    engine_version = "orb_sip_v2.v1"
    shadow_only = True

    def __init__(
        self,
        *,
        scanner: StocksInPlayScanner | None = None,
        config: ORBSIPV2Config | None = None,
    ) -> None:
        self.scanner = scanner or StocksInPlayScanner()
        self.config = config or ORBSIPV2Config()

    def generate_signals(self, context: dict[str, Any]) -> list[CandidateSignal]:
        now = context.get("now") or context.get("timestamp")
        if now is None or not self._in_entry_window(now):
            return []
        features_by_symbol = context.get("features_by_symbol") or {}
        ranked = self.scanner.rank(
            features_by_symbol,
            now=now,
            metadata_by_symbol=context.get("metadata_by_symbol") or {},
            sector_returns_bps=context.get("sector_returns_bps") or {},
        )
        market_return_bps = float(context.get("market_return_bps") or 0.0)
        if market_return_bps <= self.config.max_market_selloff_bps:
            return []

        signals: list[CandidateSignal] = []
        for item in ranked:
            if not item.passed_liquidity or item.first_window_rvol < self.config.min_relative_volume:
                continue
            bars = features_by_symbol.get(item.symbol)
            setup = _orb_setup(bars, now, opening_minutes=self.config.opening_minutes)
            if setup is None:
                continue
            direction = 1 if setup["orb_close"] > setup["orb_open"] else -1
            if direction < 0 and self.config.long_only:
                continue
            current_price = setup["current_price"]
            broke_level = (
                current_price > setup["orb_high"] if direction > 0 else current_price < setup["orb_low"]
            )
            if not broke_level:
                continue
            if direction > 0 and current_price < setup["vwap"]:
                continue
            if setup["volume_confirmation"] < self.config.min_volume_confirmation:
                continue
            side = "long" if direction > 0 else "short"
            signals.append(
                CandidateSignal(
                    signal_id=_signal_id(item.symbol, now, "orb_sip_v2"),
                    strategy_id=self.strategy_id,
                    engine_version=self.engine_version,
                    symbol=item.symbol,
                    side=side,
                    timeframe="1Min",
                    created_at=now,
                    intended_horizon_bars=self.config.intended_horizon_bars,
                    regime=str(context.get("regime") or "unknown"),
                    evidence_tier=0,
                    shadow_only=True,
                    expected_edge_bps=None,
                    confidence=min(0.80, 0.40 + item.score * 0.50),
                    stop_price=setup["orb_low"] if direction > 0 else setup["orb_high"],
                    target_price=None,
                    risk_budget_bps=0.0,
                    features={
                        "variant": "orb_sip_v2_long_breakout_vwap_volume",
                        "stocks_in_play": item.to_dict(),
                        "orb_open": setup["orb_open"],
                        "orb_close": setup["orb_close"],
                        "orb_high": setup["orb_high"],
                        "orb_low": setup["orb_low"],
                        "vwap": setup["vwap"],
                        "volume_confirmation": setup["volume_confirmation"],
                        "market_return_bps": market_return_bps,
                        "live_enabled": False,
                    },
                )
            )
        return signals

    def _in_entry_window(self, now: Any) -> bool:
        ts = pd.Timestamp(now)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        et = ts.tz_convert("America/New_York").time()
        return self.config.entry_start_et <= et <= self.config.entry_end_et


def _orb_setup(
    bars: pd.DataFrame | None,
    now: Any,
    *,
    opening_minutes: int,
) -> dict[str, float] | None:
    df = _prepare_bars(bars)
    if df is None:
        return None
    session = _session_bars(df, now)
    if len(session) <= opening_minutes:
        return None
    opening = session.head(opening_minutes)
    latest = session.iloc[-1]
    if float(latest["close"]) <= 0:
        return None
    vwap = _vwap(session)
    recent = session.tail(5)
    prior = session.iloc[:-5] if len(session) > 10 else session
    prior_volume = float(prior["volume"].astype(float).tail(20).mean()) or 0.0
    latest_volume = float(recent["volume"].astype(float).mean()) if len(recent) else 0.0
    return {
        "orb_open": float(opening["open"].iloc[0]),
        "orb_close": float(opening["close"].iloc[-1]),
        "orb_high": float(opening["high"].max()),
        "orb_low": float(opening["low"].min()),
        "current_price": float(latest["close"]),
        "vwap": vwap,
        "volume_confirmation": latest_volume / prior_volume if prior_volume > 0 else 0.0,
    }


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
    ts_et = pd.to_datetime(df["_ts"], utc=True).dt.tz_convert("America/New_York")
    now_ts = pd.Timestamp(now)
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    session_date = now_ts.tz_convert("America/New_York").date()
    return df[ts_et.dt.date == session_date].reset_index(drop=True)


def _vwap(session: pd.DataFrame) -> float:
    dollar_volume = (session["close"].astype(float) * session["volume"].astype(float)).sum()
    volume = session["volume"].astype(float).sum()
    return float(dollar_volume / volume) if volume > 0 else float(session["close"].iloc[-1])


def _signal_id(symbol: str, now: Any, variant: str) -> str:
    payload = f"{symbol}|{pd.Timestamp(now).isoformat()}|{variant}"
    return hashlib.sha256(payload.encode()).hexdigest()[:24]
