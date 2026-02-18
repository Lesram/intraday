import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from math import log
from typing import Any

import pandas as pd

from backend.api.routes.scanner import SCANNABLE_SYMBOLS
from backend.features.feature_engineering import FeatureEngineer
from backend.utils.logger import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True)
class BreakoutCandidate:
    symbol: str
    score: float
    direction: str  # 'long' | 'short'
    close: float
    upper_trigger: float | None
    lower_trigger: float | None
    breakout_strength: float
    volume_ratio: float | None
    atr_ratio: float | None
    reason: str
    # P&L-010: breakout type for differentiated scoring
    breakout_type: str = "standard"  # 'standard' | 'atr_expansion' | 'volume_climax'


@dataclass(frozen=True)
class BreakoutScanResult:
    candidates: list[BreakoutCandidate]
    universe_size: int
    evaluated: int
    timestamp: str


_latest_scan: BreakoutScanResult | None = None


def get_latest_breakout_scan() -> BreakoutScanResult | None:
    return _latest_scan


def _parse_symbols_env(value: str | None) -> list[str]:
    if not value:
        return []
    parts = [p.strip().upper() for p in value.split(",")]
    return [p for p in parts if p]


async def scan_breakouts(
    *,
    data_client: Any,
    symbols: list[str] | None = None,
    lookback: int = 120,
    breakout_lookback: int = 20,
    buffer_pct: float = 0.002,
    volume_spike_mult: float = 1.5,
    min_price: float = 5.0,
    max_price: float = 2_000.0,
    allow_short: bool = False,
    timeframe: str = "1Day",
    limit: int = 25,
    concurrency: int | None = None,
) -> BreakoutScanResult:
    """Scan a symbol universe and return ranked breakout candidates.

    This is designed to be safe-by-default and relatively lightweight.
    For large universes, prefer a bulk data API; this implementation is intentionally conservative.
    """
    global _latest_scan

    concurrency = concurrency if concurrency is not None else int(os.getenv("AUTO_BREAKOUT_SCAN_CONCURRENCY", "6"))
    symbols = symbols or _parse_symbols_env(os.getenv("AUTO_BREAKOUT_SCAN_SYMBOLS")) or list(SCANNABLE_SYMBOLS)

    sem = asyncio.Semaphore(max(1, concurrency))
    engineer = FeatureEngineer(
        config={
            "feature_mode": os.getenv("AUTO_BREAKOUT_SCAN_FEATURE_MODE", "realtime_light"),
            "enable_heavy_features": False,
            "enable_autocorr_features": False,
        }
    )

    async def _fetch_df(symbol: str) -> pd.DataFrame:
        if hasattr(data_client, "get_historical_bars_df"):
            return await data_client.get_historical_bars_df(symbol, lookback=lookback, timeframe=timeframe)
        if hasattr(data_client, "get_historical_data"):
            return await data_client.get_historical_data(symbol, timeframe=timeframe, limit=lookback)
        raise ValueError("Unsupported data_client: missing get_historical_bars_df/get_historical_data")

    async def _eval_symbol(symbol: str) -> BreakoutCandidate | None:
        async with sem:
            try:
                df = await _fetch_df(symbol)
                if df is None or df.empty:
                    return None

                # Normalize column case
                df = df.rename(
                    columns={
                        "Open": "open",
                        "High": "high",
                        "Low": "low",
                        "Close": "close",
                        "Volume": "volume",
                    }
                )
                needed = {"open", "high", "low", "close", "volume"}
                if not needed.issubset(set(df.columns)):
                    return None

                # Ensure timestamp column exists for feature engineer
                if "timestamp" not in df.columns:
                    df = df.reset_index().rename(columns={"index": "timestamp"})

                df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()

                if len(df) < (breakout_lookback + 5):
                    return None

                close = float(df["close"].iloc[-1])
                if close < min_price or close > max_price:
                    return None

                features = engineer.compute_technical_indicators(df)
                if features is None or features.empty:
                    return None

                prior_high = float(df["high"].rolling(breakout_lookback).max().shift(1).iloc[-1])
                prior_low = float(df["low"].rolling(breakout_lookback).min().shift(1).iloc[-1])
                avg_vol = float(df["volume"].rolling(breakout_lookback).mean().shift(1).iloc[-1])
                vol = float(df["volume"].iloc[-1])
                vol_ratio = (vol / avg_vol) if avg_vol > 0 else None

                atr_ratio = None
                if "atr_ratio" in features.columns:
                    atr_ratio = float(features["atr_ratio"].iloc[-1])
                elif "atr" in features.columns and close:
                    atr_ratio = float(features["atr"].iloc[-1]) / close

                upper_trigger = prior_high * (1.0 + buffer_pct)
                lower_trigger = prior_low * (1.0 - buffer_pct)

                long_break = close >= upper_trigger
                short_break = allow_short and close <= lower_trigger

                if not long_break and not short_break:
                    return None

                if vol_ratio is None or vol_ratio < volume_spike_mult:
                    return None

                direction = "long" if long_break else "short"
                breakout_strength = (
                    (close - upper_trigger) / max(1e-9, upper_trigger)
                    if long_break
                    else (lower_trigger - close) / max(1e-9, lower_trigger)
                )

                # P&L-010: Classify breakout type using ATR and volume.
                # ATR expansion breakouts (vol regime shift) score higher than
                # pure price-level breakouts; volume-climax breakouts (extreme
                # vol spike) get a small penalty (often exhaustion moves).
                breakout_type = "standard"
                type_bonus = 0.0
                if atr_ratio is not None and atr_ratio > 0.035:
                    breakout_type = "atr_expansion"
                    type_bonus = 8.0  # vol-regime expansion is higher-quality
                if vol_ratio is not None and vol_ratio > 4.0:
                    breakout_type = "volume_climax"
                    type_bonus = -5.0  # extreme volume spike → possible exhaustion

                # Score is intentionally simple and bounded.
                # Emphasize: breakout strength + volume expansion; lightly factor volatility.
                score = 50.0
                score += min(35.0, breakout_strength * 2500.0)  # 1% => +25
                score += min(25.0, log(max(1.0, float(vol_ratio))) * 10.0)
                score += type_bonus  # P&L-010
                if atr_ratio is not None:
                    # prefer mid volatility; avoid extreme
                    score += max(-10.0, min(10.0, (0.02 - abs(0.02 - atr_ratio)) * 500.0))

                score = float(max(0.0, min(100.0, score)))
                return BreakoutCandidate(
                    symbol=symbol,
                    score=score,
                    direction=direction,
                    close=close,
                    upper_trigger=upper_trigger,
                    lower_trigger=lower_trigger,
                    breakout_strength=float(breakout_strength),
                    volume_ratio=float(vol_ratio) if vol_ratio is not None else None,
                    atr_ratio=float(atr_ratio) if atr_ratio is not None else None,
                    reason="breakout_confirmed",
                    breakout_type=breakout_type,
                )

            except Exception as e:
                logger.debug(
                    "Breakout scan evaluation failed",
                    extra={"symbol": symbol, "error": str(e)},
                )
                return None

    tasks = [_eval_symbol(sym) for sym in symbols]
    results = await asyncio.gather(*tasks)
    candidates = [c for c in results if c is not None]
    candidates.sort(key=lambda c: c.score, reverse=True)
    candidates = candidates[: max(1, min(200, limit))]

    scan = BreakoutScanResult(
        candidates=candidates,
        universe_size=len(symbols),
        evaluated=len(symbols),
        timestamp=datetime.now(UTC).isoformat(),
    )
    _latest_scan = scan
    return scan
