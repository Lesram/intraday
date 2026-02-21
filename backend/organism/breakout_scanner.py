"""
Module A — Breakout Pattern Scanner.

Proprietary breakout detection with 6 pattern detectors:
  1. Bollinger Squeeze (compression → expansion imminent)
  2. Volume Surge (institutional accumulation)
  3. Range Contraction (coiled spring — ATR compression)
  4. Relative Strength (top-rank momentum vs universe)
  5. Pivot Breakout (price clearing resistance)
  6. Institutional Flow (large block detection)

Composite score weighted average → rank → top N candidates.

Ref: docs/blueprints/BREAKOUT_ALPHA_BLUEPRINT.md §3 Module A
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class BreakoutSignal:
    """Result of breakout scan for one symbol."""
    symbol: str
    composite_score: float    # [0, 1] weighted breakout score
    squeeze_score: float      # BB squeeze compression
    volume_score: float       # Volume surge magnitude
    contraction_score: float  # ATR range contraction
    rs_score: float           # Relative strength rank
    pivot_score: float        # Resistance breakout
    flow_score: float         # Institutional flow
    direction: float          # +1 long breakout, -1 short breakdown
    squeeze_fired: bool       # True if squeeze is releasing NOW
    volume_ratio: float       # Raw vol ratio for display

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "composite": round(self.composite_score, 4),
            "squeeze": round(self.squeeze_score, 4),
            "volume": round(self.volume_score, 4),
            "contraction": round(self.contraction_score, 4),
            "rs": round(self.rs_score, 4),
            "pivot": round(self.pivot_score, 4),
            "flow": round(self.flow_score, 4),
            "direction": self.direction,
            "squeeze_fired": self.squeeze_fired,
            "vol_ratio": round(self.volume_ratio, 2),
        }


class BreakoutScanner:
    """Scan symbols for breakout setups.

    The core thesis: stocks that compress volatility (squeeze),
    then see a volume surge while breaking a pivot level, are
    likely to make an explosive directional move.

    Scoring weights:
        Squeeze:         25%  — compressed BBands → expansion
        Volume surge:    25%  — confirms institutional participation
        Range contract:  15%  — coiled spring (ATR compression)
        Relative str:    15%  — strongest stocks break out hardest
        Pivot breakout:  15%  — price confirming the pattern
        Inst. flow:       5%  — large block detection
    """

    W_SQUEEZE = 0.25
    W_VOLUME = 0.25
    W_CONTRACTION = 0.15
    W_RS = 0.15
    W_PIVOT = 0.15
    W_FLOW = 0.05

    MIN_BREAKOUT_SCORE = 0.20  # HFT: lower gate for intraday breakouts (was 0.30)
    MIN_SQUEEZE_FIRE = 0.45    # HFT: fire squeeze earlier (was 0.60)

    def __init__(self, top_n: int = 8):
        self.top_n = top_n
        self._scan_count = 0
        self._hit_count = 0

        # ── Tunable indicator periods (Phase 3.8) ────────────
        # Defaults match the originals; overwritten by
        # apply_evolved_params() when the EvolutionEngine adapts.
        self.BB_PERIOD: int = 20
        self.ATR_SHORT: int = 10
        self.ATR_LONG: int = 50
        self.PIVOT_LOOKBACK: int = 20
        self.VOL_AVG_PERIOD: int = 20
        self.RS_PERIOD: int = 20

    @property
    def hit_rate(self) -> float:
        return self._hit_count / max(self._scan_count, 1)

    def scan(
        self,
        data_by_symbol: dict[str, pd.DataFrame],
        spy_data: pd.DataFrame | None = None,
    ) -> list[BreakoutSignal]:
        """Scan all symbols for breakout signals.

        Parameters
        ----------
        data_by_symbol : {symbol: DataFrame with OHLCV + features}
            Must have: open, high, low, close, volume columns.
            Feature columns are optional but improve scoring.
        spy_data : SPY DataFrame for relative strength calc.

        Returns
        -------
        Top-N breakout candidates sorted by composite score.
        """
        self._scan_count += 1
        signals: list[BreakoutSignal] = []

        # Pre-compute cross-sectional relative strength
        rs_ranks = self._compute_rs_ranks(data_by_symbol)

        for symbol, df in data_by_symbol.items():
            if symbol == "SPY" or len(df) < 60:
                continue

            sig = self._score_symbol(symbol, df, rs_ranks, spy_data)
            if sig is not None:
                signals.append(sig)

        # Sort by composite score
        signals.sort(key=lambda s: s.composite_score, reverse=True)
        self._last_full_scan = list(signals)

        # Filter and take top N
        result = [
            s for s in signals[:self.top_n]
            if s.composite_score >= self.MIN_BREAKOUT_SCORE
        ]

        if result:
            self._hit_count += 1

        return result

    def _score_symbol(
        self,
        symbol: str,
        df: pd.DataFrame,
        rs_ranks: dict[str, float],
        spy_data: pd.DataFrame | None,
    ) -> BreakoutSignal | None:
        """Score one symbol across all 6 breakout dimensions."""
        close = df["close"].values
        high = df["high"].values if "high" in df.columns else close
        low = df["low"].values if "low" in df.columns else close
        volume = df["volume"].values if "volume" in df.columns else np.ones(len(close))

        if len(close) < 50:
            return None

        # ── 1. Squeeze Score ─────────────────────────────────
        squeeze_score, squeeze_fired = self._squeeze_detector(close, high, low)

        # ── 2. Volume Surge ──────────────────────────────────
        volume_score, vol_ratio = self._volume_surge(volume)

        # ── 3. Range Contraction ─────────────────────────────
        contraction_score = self._range_contraction(high, low, close)

        # ── 4. Relative Strength ─────────────────────────────
        rs_score = rs_ranks.get(symbol, 0.5)

        # ── 5. Pivot Breakout ────────────────────────────────
        pivot_score, direction = self._pivot_breakout(close, high, low)

        # ── 6. Institutional Flow ────────────────────────────
        flow_score = self._institutional_flow(volume)

        # ── Direction determination ──────────────────────────
        # Squeeze direction: which way is price exiting?
        if direction == 0:
            # Use momentum to determine breakout direction
            ret_5 = (close[-1] - close[-6]) / close[-6] if close[-6] > 0 else 0
            direction = 1.0 if ret_5 > 0 else (-1.0 if ret_5 < -0.01 else 0.0)

        # Only long breakouts in bull market (RS > 0.4)
        if direction < 0 and rs_score > 0.5:
            # Fighting the trend — reduce score
            squeeze_score *= 0.5
            pivot_score *= 0.5

        # ── Composite ────────────────────────────────────────
        composite = (
            self.W_SQUEEZE * squeeze_score
            + self.W_VOLUME * volume_score
            + self.W_CONTRACTION * contraction_score
            + self.W_RS * rs_score
            + self.W_PIVOT * pivot_score
            + self.W_FLOW * flow_score
        )

        # Bonus if squeeze is actively firing with volume confirmation
        if squeeze_fired and vol_ratio > 1.5:
            composite *= 1.3  # 30% bonus for squeeze + volume
            composite = min(composite, 1.0)

        if composite < 0.15:
            return None

        return BreakoutSignal(
            symbol=symbol,
            composite_score=composite,
            squeeze_score=squeeze_score,
            volume_score=volume_score,
            contraction_score=contraction_score,
            rs_score=rs_score,
            pivot_score=pivot_score,
            flow_score=flow_score,
            direction=direction,
            squeeze_fired=squeeze_fired,
            volume_ratio=vol_ratio,
        )

    # ══════════════════════════════════════════════════════════
    # Pattern Detectors
    # ══════════════════════════════════════════════════════════

    def _squeeze_detector(
        self, close: np.ndarray, high: np.ndarray, low: np.ndarray
    ) -> tuple[float, bool]:
        """Detect Bollinger Band squeeze (compression → expansion).

        Squeeze = BB width at N-bar low, about to expand.
        Uses Keltner Channel overlap: when BB fits inside KC, it's a squeeze.

        Returns (score [0,1], squeeze_fired bool).
        """
        period = self.BB_PERIOD

        # Bollinger Bands width
        sma = self._rolling_mean(close, period)
        std = self._rolling_std(close, period)
        bb_width = 2 * std / (sma + 1e-10)

        if len(bb_width) < period + 20:
            return 0.0, False

        # Current width percentile over last 120 bars
        lookback = min(120, len(bb_width))
        recent_widths = bb_width[-lookback:]
        current_width = bb_width[-1]

        if np.std(recent_widths) < 1e-10:
            return 0.0, False

        # Percentile rank (lower = more compressed = higher score)
        percentile = np.sum(recent_widths <= current_width) / len(recent_widths)
        squeeze_score = 1.0 - percentile  # Invert: tightest squeeze = highest score

        # Keltner Channel check — uses rolling ATR for correct historical comparison
        atr_arr = self._rolling_atr(high, low, close, self.ATR_SHORT)
        kc_width = 2.0 * 1.5 * atr_arr / (sma + 1e-10)

        # Squeeze "fires" when BB was inside KC and is now expanding
        was_squeezed = bb_width[-5] < kc_width[-5] if len(kc_width) >= 5 else False
        is_expanding = bb_width[-1] > bb_width[-3] if len(bb_width) >= 3 else False
        squeeze_fired = was_squeezed and is_expanding and percentile < 0.35

        return min(max(squeeze_score, 0.0), 1.0), squeeze_fired

    def _volume_surge(self, volume: np.ndarray) -> tuple[float, float]:
        """Detect volume surge above moving average.

        Score based on how much current volume exceeds N-day average.
        Returns (score [0,1], raw_ratio).
        """
        vol_period = self.VOL_AVG_PERIOD
        needed = vol_period + 5
        if len(volume) < needed:
            return 0.0, 1.0

        avg_vol = np.mean(volume[-needed:-5])  # N-bar avg excluding last 5
        if avg_vol < 1:
            return 0.0, 1.0

        # Max of last 3 bars (captures surge that started 1-3 days ago)
        recent_max_vol = np.max(volume[-3:])
        vol_ratio = float(recent_max_vol / avg_vol)

        # Score: linear from 1.0× to 5.0× average
        score = min(max((vol_ratio - 1.0) / 4.0, 0.0), 1.0)

        return score, vol_ratio

    def _range_contraction(
        self, high: np.ndarray, low: np.ndarray, close: np.ndarray
    ) -> float:
        """Detect ATR contraction (coiled spring).

        When short-term ATR is much lower than long-term ATR,
        the stock is coiling → likely to explode.

        Score = 1 - (ATR_short / ATR_long). Higher = more contracted.
        """
        atr_short = self._atr(high, low, close, self.ATR_SHORT)
        atr_long = self._atr(high, low, close, self.ATR_LONG)

        if atr_long < 1e-10:
            return 0.0

        ratio = atr_short / atr_long
        score = max(1.0 - ratio, 0.0)

        return min(score, 1.0)

    def _pivot_breakout(
        self, close: np.ndarray, high: np.ndarray, low: np.ndarray
    ) -> tuple[float, float]:
        """Detect price breaking above/below recent pivot levels.

        Pivot high = max of last 20 bars' highs (excluding last bar).
        If close > pivot_high, it's a long breakout.

        Returns (score [0,1], direction +1/-1/0).
        """
        plb = self.PIVOT_LOOKBACK
        if len(close) < plb + 5:
            return 0.0, 0.0

        # Resistance: max high over last N bars (excluding current)
        pivot_high = float(np.max(high[-(plb + 1):-1]))
        # Support: min low over last N bars
        pivot_low = float(np.min(low[-(plb + 1):-1]))

        current = float(close[-1])
        atr = self._atr(high, low, close, 14)
        if atr < 1e-10:
            return 0.0, 0.0

        # Long breakout
        if current > pivot_high:
            excess = (current - pivot_high) / atr
            score = min(excess, 1.0)
            return score, 1.0

        # Short breakdown
        if current < pivot_low:
            excess = (pivot_low - current) / atr
            score = min(excess, 1.0)
            return score, -1.0

        # Near pivot (within 0.5 ATR) — pre-breakout
        dist_to_high = (pivot_high - current) / atr
        if dist_to_high < 0.5:
            return 0.3, 1.0  # Close to breakout

        return 0.0, 0.0

    def _institutional_flow(self, volume: np.ndarray) -> float:
        """Detect institutional accumulation via large volume bars.

        Count bars in the last 5 where volume > 5× median.
        """
        if len(volume) < 30:
            return 0.0

        median_vol = float(np.median(volume[-30:-5]))
        if median_vol < 1:
            return 0.0

        # Count 5×+ median volume bars in last 5 trading days
        recent = volume[-5:]
        big_blocks = sum(1 for v in recent if v > 5 * median_vol)

        return min(big_blocks / 3.0, 1.0)  # 3 big blocks = max score

    def _compute_rs_ranks(
        self, data_by_symbol: dict[str, pd.DataFrame]
    ) -> dict[str, float]:
        """Cross-sectional relative strength rank [0,1]."""
        returns_nd: dict[str, float] = {}
        rs_lb = self.RS_PERIOD

        for symbol, df in data_by_symbol.items():
            if symbol == "SPY" or len(df) < rs_lb + 5:
                continue
            close = df["close"].values
            ret = (close[-1] - close[-(rs_lb + 1)]) / close[-(rs_lb + 1)] if close[-(rs_lb + 1)] > 0 else 0
            returns_nd[symbol] = ret

        if not returns_nd:
            return {}

        sorted_syms = sorted(returns_nd.keys(), key=lambda s: returns_nd[s])
        n = len(sorted_syms)
        return {sym: i / max(n - 1, 1) for i, sym in enumerate(sorted_syms)}

    # ══════════════════════════════════════════════════════════
    # Utility functions
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _rolling_mean(arr: np.ndarray, period: int) -> np.ndarray:
        """Rolling mean with NaN padding."""
        result = np.full_like(arr, np.nan, dtype=float)
        if len(arr) < period:
            return result
        cumsum = np.cumsum(arr)
        result[period - 1:] = (cumsum[period - 1:] - np.concatenate(([0], cumsum[:-period]))) / period
        return result

    @staticmethod
    def _rolling_std(arr: np.ndarray, period: int) -> np.ndarray:
        """Rolling standard deviation."""
        result = np.full_like(arr, np.nan, dtype=float)
        if len(arr) < period:
            return result
        for i in range(period - 1, len(arr)):
            result[i] = np.std(arr[i - period + 1:i + 1], ddof=1)
        return result

    @staticmethod
    def _atr(
        high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14
    ) -> float:
        """Average True Range (scalar, latest value)."""
        if len(close) < period + 1:
            return float(np.mean(np.abs(np.diff(close)))) if len(close) > 1 else 0.0

        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1]),
            ),
        )

        if len(tr) < period:
            return float(np.mean(tr))

        # EMA-based ATR
        atr_val = float(np.mean(tr[:period]))
        alpha = 2.0 / (period + 1)
        for i in range(period, len(tr)):
            atr_val = alpha * float(tr[i]) + (1 - alpha) * atr_val
        return atr_val

    @staticmethod
    def _rolling_atr(
        high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14
    ) -> np.ndarray:
        """Rolling ATR array (same length as close) for historical comparison."""
        n = len(close)
        result = np.zeros(n)
        if n < 2:
            return result
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1]),
            ),
        )
        # Pad to align with close
        tr = np.concatenate([[tr[0]], tr])
        alpha = 2.0 / (period + 1)
        result[0] = tr[0]
        for i in range(1, n):
            if i < period:
                result[i] = np.mean(tr[: i + 1])
            else:
                result[i] = alpha * tr[i] + (1 - alpha) * result[i - 1]
        return result
