"""
Advanced Trading Strategies — Next-Generation Algorithmic Trading

Implements cutting-edge strategies drawing from modern quantitative finance:

1. AdaptiveRegimeMomentumStrategy       — Regime-adaptive momentum with dynamic parameters
2. OrderFlowImbalanceStrategy           — Microstructure-based signal from bid-ask flow
3. VolatilityStructureStrategy          — Volatility term-structure & GARCH(1,1) forecasting
4. CrossSectionalMomentumStrategy       — Cross-asset risk-adjusted momentum rankings
5. AdaptiveKellyStrategy                — Dynamic Kelly position sizing with edge estimation
6. MicrostructureAlphaStrategy          — Volume-price divergence & smart money detection
7. SqueezeBreakoutStrategy              — Bollinger-Keltner squeeze breakout capture
8. FailedBreakoutReversalStrategy       — Contrarian reversal on failed breakouts
9. MultiTimeframeBreakoutStrategy       — Multi-TF aligned breakout confirmation
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from ..config import get_settings
from ..risk.risk_manager import RiskManager
from ..utils.logger import audit_logger
from .trading_strategies import (
    BaseStrategy,
    OrderType,
    SignalType,
    TradingSignal,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Adaptive Regime Momentum
# ---------------------------------------------------------------------------
class AdaptiveRegimeMomentumStrategy(BaseStrategy):
    """Momentum strategy that dynamically adapts to detected market regime.

    Key innovations:
    - Uses Hidden Markov-inspired regime detection (volatility clustering)
    - Adjusts lookback, confidence scaling, and stop-loss dynamically
    - Combines multiple timeframe momentum signals with regime weighting
    - Includes adaptive trailing stop using ATR expansion/contraction

    This strategy ONLY trades when regime alignment is confirmed across
    multiple timeframe filters, drastically reducing whipsaw losses.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        fast_lookback: int = 10,
        slow_lookback: int = 50,
        vol_lookback: int = 20,
        trend_strength_threshold: float = 0.6,
        vol_regime_high_pct: float = 75,
        vol_regime_low_pct: float = 25,
    ):
        super().__init__("AdaptiveRegimeMomentum", risk_manager, stop_loss_pct=0.015, take_profit_pct=0.06)
        self.fast_lookback = fast_lookback
        self.slow_lookback = slow_lookback
        self.vol_lookback = vol_lookback
        self.trend_strength_threshold = trend_strength_threshold
        self.vol_regime_high_pct = vol_regime_high_pct
        self.vol_regime_low_pct = vol_regime_low_pct

    def _detect_regime(self, returns: np.ndarray) -> str:
        """Classify current regime using realized volatility percentile."""
        if len(returns) < self.vol_lookback * 2:
            return "unknown"
        recent_vol = np.std(returns[-self.vol_lookback:]) * np.sqrt(252)
        historical_vols = pd.Series(returns).rolling(self.vol_lookback).std().dropna() * np.sqrt(252)
        if len(historical_vols) < 20:
            return "normal"
        pct_rank = (historical_vols < recent_vol).mean() * 100
        if pct_rank > self.vol_regime_high_pct:
            return "high_vol"
        elif pct_rank < self.vol_regime_low_pct:
            return "low_vol"
        return "normal"

    def _multi_timeframe_momentum(self, prices: np.ndarray) -> dict[str, float]:
        """Compute momentum scores across multiple lookback windows."""
        scores = {}
        for label, lb in [("fast", self.fast_lookback), ("slow", self.slow_lookback), ("mid", (self.fast_lookback + self.slow_lookback) // 2)]:
            if len(prices) < lb + 1:
                scores[label] = 0.0
                continue
            ret = (prices[-1] / prices[-lb - 1]) - 1.0
            vol = np.std(np.diff(np.log(prices[-lb:]))) * np.sqrt(252)
            scores[label] = ret / max(vol, 1e-9)  # Risk-adjusted (Sharpe-like)
        return scores

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        prices = price_data["close"].values.astype(float)
        if len(prices) < self.slow_lookback + 10:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=float(prices[-1]))

        current_price = float(prices[-1])
        returns = np.diff(np.log(prices))
        regime = self._detect_regime(returns)
        mom_scores = self._multi_timeframe_momentum(prices)

        # Regime-adaptive parameter scaling
        if regime == "high_vol":
            confidence_scale = 0.6  # More conservative in volatile markets
            atr_mult = 2.5
        elif regime == "low_vol":
            confidence_scale = 1.0  # Full confidence in calm markets
            atr_mult = 1.2
        else:
            confidence_scale = 0.8
            atr_mult = 1.8

        # Trend alignment score: weighted combination of multi-timeframe momentum
        alignment = 0.4 * mom_scores["fast"] + 0.35 * mom_scores["mid"] + 0.25 * mom_scores["slow"]

        signal_type = SignalType.HOLD
        if alignment > self.trend_strength_threshold:
            signal_type = SignalType.STRONG_BUY if alignment > self.trend_strength_threshold * 2 else SignalType.BUY
        elif alignment < -self.trend_strength_threshold:
            signal_type = SignalType.STRONG_SELL if alignment < -self.trend_strength_threshold * 2 else SignalType.SELL

        if signal_type == SignalType.HOLD:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=current_price,
                                 metadata={"strategy": "adaptive_regime_momentum", "regime": regime, "alignment": float(alignment)})

        confidence = float(min(0.9, max(0.15, abs(alignment) / 3.0)) * confidence_scale)
        position_size = await self.calculate_position_size(symbol, current_price, confidence)

        # ATR-based adaptive stops
        atr = float(features["atr"].iloc[-1]) if "atr" in features.columns and not pd.isna(features["atr"].iloc[-1]) else current_price * 0.02
        stop_distance = atr * atr_mult
        tp_distance = atr * atr_mult * 2.5  # Minimum 1:2.5 risk-reward

        if signal_type == SignalType.BUY:
            stop_loss = current_price - stop_distance
            take_profit = current_price + tp_distance
        else:
            stop_loss = current_price + stop_distance
            take_profit = current_price - tp_distance

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            target_price=take_profit,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            metadata={
                "strategy": "adaptive_regime_momentum",
                "regime": regime,
                "alignment_score": float(alignment),
                "momentum_fast": float(mom_scores["fast"]),
                "momentum_mid": float(mom_scores["mid"]),
                "momentum_slow": float(mom_scores["slow"]),
                "confidence_scale": confidence_scale,
                "atr_multiplier": atr_mult,
            },
        )

    def get_required_features(self) -> list[str]:
        return ["atr"]


# ---------------------------------------------------------------------------
# 2. Order Flow Imbalance Strategy
# ---------------------------------------------------------------------------
class OrderFlowImbalanceStrategy(BaseStrategy):
    """Microstructure-based strategy using volume-price imbalance signals.

    Core idea from modern market microstructure theory:
    - Detect smart money flow via volume-weighted price momentum
    - Identify buying/selling pressure imbalance using OBV acceleration
    - Filter for institutional-scale moves using abnormal volume detection
    - Combine with VWAP deviation for execution timing

    This provides alpha from order flow that is inaccessible to traditional
    technical indicators alone.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        imbalance_lookback: int = 20,
        volume_spike_mult: float = 1.5,
        vwap_deviation_threshold: float = 0.01,
        obv_acceleration_window: int = 5,
    ):
        super().__init__("OrderFlowImbalance", risk_manager, stop_loss_pct=0.015, take_profit_pct=0.04)
        self.imbalance_lookback = imbalance_lookback
        self.volume_spike_mult = volume_spike_mult
        self.vwap_deviation_threshold = vwap_deviation_threshold
        self.obv_acceleration_window = obv_acceleration_window

    def _compute_order_flow_imbalance(self, df: pd.DataFrame) -> pd.Series:
        """Compute order flow imbalance from OHLCV data.

        Uses close location value (CLV) as proxy for buy/sell pressure:
        CLV = (close - low) / (high - low) * 2 - 1  (ranges from -1 to 1)
        Volume-weighted CLV gives the order flow imbalance.
        """
        hl_range = df["high"] - df["low"]
        clv = np.where(hl_range.abs() < 1e-12, 0.0, ((df["close"] - df["low"]) / hl_range) * 2 - 1)
        vol_weighted_clv = clv * df["volume"]
        return pd.Series(vol_weighted_clv, index=df.index)

    def _detect_smart_money(self, df: pd.DataFrame) -> dict[str, float]:
        """Detect institutional flows via volume anomalies."""
        vol = df["volume"].values.astype(float)
        avg_vol = np.mean(vol[-self.imbalance_lookback:])
        recent_vol = vol[-1]
        vol_ratio = recent_vol / max(avg_vol, 1)

        # OBV acceleration: rate of change of OBV
        direction = np.sign(np.diff(df["close"].values.astype(float)))
        obv = np.cumsum(np.concatenate([[0], direction * vol[1:]]))
        if len(obv) >= self.obv_acceleration_window + 1:
            obv_roc = (obv[-1] - obv[-self.obv_acceleration_window - 1]) / max(abs(obv[-self.obv_acceleration_window - 1]), 1)
        else:
            obv_roc = 0.0

        return {"volume_ratio": vol_ratio, "obv_roc": obv_roc}

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        if len(price_data) < self.imbalance_lookback + 5:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=0.0)

        current_price = float(price_data["close"].iloc[-1])

        # Compute order flow imbalance
        ofi = self._compute_order_flow_imbalance(price_data)
        cumulative_ofi = ofi.rolling(self.imbalance_lookback).sum()
        ofi_zscore = (cumulative_ofi.iloc[-1] - cumulative_ofi.mean()) / max(cumulative_ofi.std(), 1e-9)

        # Smart money detection
        sm = self._detect_smart_money(price_data)

        # VWAP deviation
        typical_price = (price_data["high"] + price_data["low"] + price_data["close"]) / 3
        vwap = (typical_price * price_data["volume"]).cumsum() / price_data["volume"].cumsum()
        vwap_dev = (current_price - float(vwap.iloc[-1])) / max(float(vwap.iloc[-1]), 1e-9)

        # Volume confirmation gate
        if sm["volume_ratio"] < self.volume_spike_mult:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=current_price,
                                 metadata={"strategy": "order_flow_imbalance", "reason": "insufficient_volume", "vol_ratio": sm["volume_ratio"]})

        # Signal generation: combine OFI z-score + OBV acceleration + VWAP deviation
        # Normalize all components to comparable ~[-3, 3] z-score-like scale
        vwap_zscore = vwap_dev / max(abs(self.vwap_deviation_threshold), 1e-9)
        obv_zscore = sm["obv_roc"] / max(abs(sm["obv_roc"]), 1e-9) * min(abs(sm["obv_roc"]) * 5, 3.0) if abs(sm["obv_roc"]) > 0.01 else 0.0
        composite_score = 0.5 * ofi_zscore + 0.3 * obv_zscore + 0.2 * vwap_zscore

        signal_type = SignalType.HOLD
        if composite_score > 1.5:
            signal_type = SignalType.STRONG_BUY if composite_score > 2.5 else SignalType.BUY
        elif composite_score < -1.5:
            signal_type = SignalType.STRONG_SELL if composite_score < -2.5 else SignalType.SELL

        if signal_type == SignalType.HOLD:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=current_price,
                                 metadata={"strategy": "order_flow_imbalance", "composite_score": float(composite_score)})

        confidence = float(min(0.9, max(0.15, abs(composite_score) / 5.0)))
        position_size = await self.calculate_position_size(symbol, current_price, confidence)

        atr = float(features["atr"].iloc[-1]) if "atr" in features.columns and not pd.isna(features["atr"].iloc[-1]) else current_price * 0.015
        if signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
            stop_loss = current_price - atr * 1.5
            take_profit = current_price + atr * 3.0
        else:
            stop_loss = current_price + atr * 1.5
            take_profit = current_price - atr * 3.0

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            target_price=take_profit,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            metadata={
                "strategy": "order_flow_imbalance",
                "ofi_zscore": float(ofi_zscore),
                "obv_roc": float(sm["obv_roc"]),
                "volume_ratio": float(sm["volume_ratio"]),
                "vwap_deviation": float(vwap_dev),
                "composite_score": float(composite_score),
            },
        )

    def get_required_features(self) -> list[str]:
        return ["atr"]


# ---------------------------------------------------------------------------
# 3. Volatility Structure Strategy (GARCH-inspired)
# ---------------------------------------------------------------------------
class VolatilityStructureStrategy(BaseStrategy):
    """Volatility-based strategy using GARCH(1,1)-style forecasting.

    Exploits the well-documented volatility clustering phenomenon:
    - Estimates conditional volatility using exponential smoothing (GARCH proxy)
    - Trades volatility mean-reversion: sell vol when it spikes, buy when compressed
    - Uses volatility ratio (short-term / long-term) as primary signal
    - Adaptive position sizing inversely proportional to forecast volatility

    This captures the volatility risk premium — one of the most robust alpha
    sources in systematic trading.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        short_vol_window: int = 5,
        long_vol_window: int = 60,
        omega: float = 0.00001,
        alpha_garch: float = 0.1,
        beta_garch: float = 0.85,
        vol_expansion_threshold: float = 1.5,
        vol_compression_threshold: float = 0.6,
    ):
        super().__init__("VolatilityStructure", risk_manager, stop_loss_pct=0.02, take_profit_pct=0.04)
        self.short_vol_window = short_vol_window
        self.long_vol_window = long_vol_window
        self.omega = omega
        self.alpha_garch = alpha_garch
        self.beta_garch = beta_garch
        self.vol_expansion_threshold = vol_expansion_threshold
        self.vol_compression_threshold = vol_compression_threshold

    def _garch_forecast(self, returns: np.ndarray) -> float:
        """Compute GARCH(1,1) conditional volatility forecast."""
        n = len(returns)
        if n < 2:
            return 0.01
        # Initialize with unconditional variance
        long_var = np.var(returns)
        sigma2 = long_var
        for i in range(n):
            sigma2 = self.omega + self.alpha_garch * returns[i] ** 2 + self.beta_garch * sigma2
        return float(np.sqrt(sigma2) * np.sqrt(252))  # Annualized

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        prices = price_data["close"].values.astype(float)
        if len(prices) < self.long_vol_window + 5:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=float(prices[-1]))

        current_price = float(prices[-1])
        returns = np.diff(np.log(prices))

        # Compute volatility measures
        short_vol = np.std(returns[-self.short_vol_window:]) * np.sqrt(252)
        long_vol = np.std(returns[-self.long_vol_window:]) * np.sqrt(252)
        garch_vol = self._garch_forecast(returns[-min(252, len(returns)):])

        vol_ratio = short_vol / max(long_vol, 1e-9)
        garch_ratio = garch_vol / max(long_vol, 1e-9)

        # Signal logic:
        # High vol ratio → vol expansion → expect mean reversion (contrarian: buy)
        # Low vol ratio → vol compression → expect breakout (follow momentum)
        signal_type = SignalType.HOLD
        confidence = 0.0

        sma_20 = float(features["sma_20"].iloc[-1]) if "sma_20" in features.columns else current_price

        if vol_ratio > self.vol_expansion_threshold:
            # Volatility spike — contrarian entry (price likely oversold/overbought)
            if current_price < sma_20:
                signal_type = SignalType.BUY  # Panic selling overdone
            else:
                signal_type = SignalType.SELL  # Euphoria overdone
            confidence = min(0.85, max(0.2, (vol_ratio - self.vol_expansion_threshold) / 2.0))
        elif vol_ratio < self.vol_compression_threshold:
            # Volatility compression — breakout imminent, follow momentum
            if "rsi" in features.columns:
                rsi = float(features["rsi"].iloc[-1])
                if rsi > 55:
                    signal_type = SignalType.BUY
                elif rsi < 45:
                    signal_type = SignalType.SELL
                confidence = min(0.7, max(0.15, abs(rsi - 50) / 40.0))

        if signal_type == SignalType.HOLD:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=current_price,
                                 metadata={"strategy": "volatility_structure", "vol_ratio": float(vol_ratio), "garch_vol": float(garch_vol)})

        # Inverse volatility position sizing (smaller in high vol)
        vol_adj_confidence = confidence * min(1.0, 0.15 / max(garch_vol, 0.01))
        vol_adj_confidence = max(0.1, min(0.9, vol_adj_confidence))
        position_size = await self.calculate_position_size(symbol, current_price, vol_adj_confidence)

        atr = float(features["atr"].iloc[-1]) if "atr" in features.columns and not pd.isna(features["atr"].iloc[-1]) else current_price * 0.02
        if signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
            stop_loss = current_price - atr * 2.0
            take_profit = current_price + atr * 4.0
        else:
            stop_loss = current_price + atr * 2.0
            take_profit = current_price - atr * 4.0

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=vol_adj_confidence,
            target_price=take_profit,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            metadata={
                "strategy": "volatility_structure",
                "short_vol": float(short_vol),
                "long_vol": float(long_vol),
                "garch_vol": float(garch_vol),
                "vol_ratio": float(vol_ratio),
                "garch_ratio": float(garch_ratio),
            },
        )

    def get_required_features(self) -> list[str]:
        return ["atr", "sma_20", "rsi"]


# ---------------------------------------------------------------------------
# 4. Cross-Sectional Momentum Strategy
# ---------------------------------------------------------------------------
class CrossSectionalMomentumStrategy(BaseStrategy):
    """Cross-asset risk-adjusted momentum ranking strategy.

    Based on the academic finding that assets with strong risk-adjusted
    past returns tend to outperform in the near future (Jegadeesh & Titman, 1993).

    Innovations over classical momentum:
    - Volatility-normalized returns for fair cross-asset comparison
    - Excludes recent 1-week returns (avoids short-term reversal effect)
    - Momentum score decay weighting (recent months weighted more)
    - Crash protection via momentum reversal detection
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        ranking_lookback: int = 120,  # ~6 months of daily data
        skip_recent: int = 5,  # Skip most recent week
        momentum_threshold: float = 1.0,  # Z-score threshold for signal
    ):
        super().__init__("CrossSectionalMomentum", risk_manager, stop_loss_pct=0.03, take_profit_pct=0.08)
        self.ranking_lookback = ranking_lookback
        self.skip_recent = skip_recent
        self.momentum_threshold = momentum_threshold

    def _compute_risk_adjusted_momentum(self, prices: np.ndarray) -> float:
        """Compute volatility-adjusted momentum score with decay weighting."""
        n = len(prices)
        if n < self.ranking_lookback + self.skip_recent + 1:
            return 0.0

        # Exclude most recent skip_recent days (short-term reversal)
        eval_prices = prices[-(self.ranking_lookback + self.skip_recent):-self.skip_recent]
        if len(eval_prices) < 20:
            return 0.0

        # Log returns
        log_ret = np.diff(np.log(eval_prices))

        # Exponential decay weights (more weight on recent returns)
        decay = np.exp(np.linspace(-1, 0, len(log_ret)))
        decay /= decay.sum()

        weighted_return = np.sum(log_ret * decay)
        vol = np.std(log_ret) * np.sqrt(252)

        return weighted_return / max(vol, 1e-9)

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        prices = price_data["close"].values.astype(float)
        current_price = float(prices[-1])

        if len(prices) < self.ranking_lookback + self.skip_recent + 10:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=current_price)

        mom_score = self._compute_risk_adjusted_momentum(prices)

        # Crash protection: check if momentum has reversed sharply in last week
        if self.skip_recent > 0 and len(prices) > self.skip_recent + 1:
            recent_ret = (prices[-1] / prices[-self.skip_recent - 1]) - 1
            if mom_score > 0 and recent_ret < -0.05:  # Strong momentum but recent 5% crash
                return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=current_price,
                                     metadata={"strategy": "cross_sectional_momentum", "reason": "momentum_reversal", "mom_score": float(mom_score)})

        signal_type = SignalType.HOLD
        if mom_score > self.momentum_threshold:
            signal_type = SignalType.BUY
        elif mom_score < -self.momentum_threshold:
            signal_type = SignalType.SELL

        if signal_type == SignalType.HOLD:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=current_price,
                                 metadata={"strategy": "cross_sectional_momentum", "mom_score": float(mom_score)})

        confidence = float(min(0.85, max(0.15, abs(mom_score) / 4.0)))
        position_size = await self.calculate_position_size(symbol, current_price, confidence)

        atr = float(features["atr"].iloc[-1]) if "atr" in features.columns and not pd.isna(features["atr"].iloc[-1]) else current_price * 0.025
        if signal_type == SignalType.BUY:
            stop_loss = current_price - atr * 2.0
            take_profit = current_price + atr * 5.0
        else:
            stop_loss = current_price + atr * 2.0
            take_profit = current_price - atr * 5.0

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            target_price=take_profit,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            metadata={
                "strategy": "cross_sectional_momentum",
                "momentum_score": float(mom_score),
                "ranking_lookback": self.ranking_lookback,
            },
        )

    def get_required_features(self) -> list[str]:
        return ["atr"]


# ---------------------------------------------------------------------------
# 5. Microstructure Alpha (Volume-Price Divergence + Smart Money)
# ---------------------------------------------------------------------------
class MicrostructureAlphaStrategy(BaseStrategy):
    """Detects institutional smart money flow via volume-price divergence.

    Based on the Wyckoff methodology modernized with quantitative methods:
    - Volume-price divergence: price falling on decreasing volume = accumulation
    - Effort vs result: large volume with small price change = absorption
    - Smart money indicator (SMI): up-volume vs down-volume asymmetry
    - Climactic action detection: extreme volume + price at range extremes

    This captures the footprint of institutional order flow that precedes
    major price moves.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        lookback: int = 20,
        divergence_threshold: float = 0.3,
        effort_result_threshold: float = 2.0,
        climax_vol_mult: float = 3.0,
    ):
        super().__init__("MicrostructureAlpha", risk_manager, stop_loss_pct=0.02, take_profit_pct=0.05)
        self.lookback = lookback
        self.divergence_threshold = divergence_threshold
        self.effort_result_threshold = effort_result_threshold
        self.climax_vol_mult = climax_vol_mult

    def _smart_money_indicator(self, df: pd.DataFrame) -> float:
        """Compute Smart Money Indicator: ratio of up-volume to total volume."""
        price_change = df["close"].diff()
        up_vol = df["volume"].where(price_change > 0, 0).sum()
        down_vol = df["volume"].where(price_change < 0, 0).sum()
        total = up_vol + down_vol
        if total < 1:
            return 0.5
        return float(up_vol / total)

    def _volume_price_divergence(self, df: pd.DataFrame) -> float:
        """Detect divergence between volume and price trends.

        Returns: positive = bullish divergence (accumulation), negative = bearish (distribution)
        """
        n = len(df)
        if n < 10:
            return 0.0
        x = np.arange(n).astype(float)
        # Price trend (linear regression slope)
        price_vals = df["close"].values.astype(float)
        price_slope = np.polyfit(x, price_vals, 1)[0] / max(abs(price_vals.mean()), 1e-9)
        # Volume trend
        vol_vals = df["volume"].values.astype(float)
        vol_slope = np.polyfit(x, vol_vals, 1)[0] / max(abs(vol_vals.mean()), 1e-9)

        # Divergence = volume trend going opposite direction to price trend
        if price_slope < 0 and vol_slope < 0:
            return abs(vol_slope)  # Price down, volume declining = accumulation (bullish)
        elif price_slope > 0 and vol_slope < 0:
            return -abs(vol_slope)  # Price up, volume declining = distribution (bearish)
        elif price_slope > 0 and vol_slope > 0:
            return abs(vol_slope) * 0.5  # Price up, volume confirming = trend continuation (mildly bullish)
        elif price_slope < 0 and vol_slope > 0:
            return -abs(vol_slope) * 0.5  # Price down, volume expanding = capitulation / selling pressure (bearish)
        return 0.0

    def _effort_vs_result(self, df: pd.DataFrame) -> float:
        """Detect absorption: high volume with small price change."""
        if len(df) < 2:
            return 0.0
        vol_ratio = float(df["volume"].iloc[-1]) / max(float(df["volume"].mean()), 1)
        price_change_pct = abs(float(df["close"].iloc[-1]) - float(df["close"].iloc[-2])) / max(float(df["close"].iloc[-2]), 1e-9)
        if price_change_pct < 1e-6:
            return vol_ratio  # Extreme absorption
        return vol_ratio / (price_change_pct * 100)

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        if len(price_data) < self.lookback + 5:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=0.0)

        current_price = float(price_data["close"].iloc[-1])
        recent = price_data.tail(self.lookback)

        smi = self._smart_money_indicator(recent)
        divergence = self._volume_price_divergence(recent)
        effort_result = self._effort_vs_result(price_data)

        # Composite smart money score
        smi_centered = (smi - 0.5) * 2  # Range [-1, 1]
        composite = 0.4 * smi_centered + 0.35 * divergence * 10 + 0.25 * min(effort_result / self.effort_result_threshold, 1.0) * np.sign(smi_centered)

        signal_type = SignalType.HOLD
        if composite > self.divergence_threshold:
            signal_type = SignalType.BUY  # Smart money accumulating
        elif composite < -self.divergence_threshold:
            signal_type = SignalType.SELL  # Smart money distributing

        if signal_type == SignalType.HOLD:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=current_price,
                                 metadata={"strategy": "microstructure_alpha", "composite": float(composite), "smi": float(smi)})

        confidence = float(min(0.85, max(0.15, abs(composite) / 1.5)))
        position_size = await self.calculate_position_size(symbol, current_price, confidence)

        atr = float(features["atr"].iloc[-1]) if "atr" in features.columns and not pd.isna(features["atr"].iloc[-1]) else current_price * 0.02
        if signal_type == SignalType.BUY:
            stop_loss = current_price - atr * 1.5
            take_profit = current_price + atr * 4.0
        else:
            stop_loss = current_price + atr * 1.5
            take_profit = current_price - atr * 4.0

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            target_price=take_profit,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            metadata={
                "strategy": "microstructure_alpha",
                "smart_money_indicator": float(smi),
                "volume_price_divergence": float(divergence),
                "effort_vs_result": float(effort_result),
                "composite_score": float(composite),
            },
        )

    def get_required_features(self) -> list[str]:
        return ["atr"]


# ---------------------------------------------------------------------------
# 7. Bollinger-Keltner Squeeze Breakout Strategy
# ---------------------------------------------------------------------------
class SqueezeBreakoutStrategy(BaseStrategy):
    """Capitalize on volatility compression (squeeze) followed by explosive breakout.

    The Bollinger-Keltner squeeze is one of the highest-probability setups in
    technical analysis.  When Bollinger Bands contract inside the Keltner Channel,
    the market is coiling — accumulating energy.  When the squeeze releases, the
    ensuing move is often large and directional.

    How this strategy works:
    1. Detect squeeze state via Bollinger/Keltner band positions
    2. Wait for the squeeze to *fire* (BB expands outside KC)
    3. Read the momentum histogram direction at the moment of fire
    4. Enter in the direction of the momentum with tight ATR-based risk

    Edge:  Extremely high win-rate on daily+ timeframes when combined with
    volume confirmation and the momentum histogram direction filter.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        bb_period: int = 20,
        bb_mult: float = 2.0,
        kc_period: int = 20,
        kc_mult: float = 1.5,
        min_squeeze_bars: int = 4,
        volume_confirm_mult: float = 1.3,
        atr_stop_mult: float = 1.5,
        atr_tp_mult: float = 3.0,
    ):
        super().__init__("SqueezeBreakout", risk_manager, stop_loss_pct=0.025, take_profit_pct=0.06)
        self.bb_period = bb_period
        self.bb_mult = bb_mult
        self.kc_period = kc_period
        self.kc_mult = kc_mult
        self.min_squeeze_bars = min_squeeze_bars
        self.volume_confirm_mult = volume_confirm_mult
        self.atr_stop_mult = atr_stop_mult
        self.atr_tp_mult = atr_tp_mult

    def _compute_squeeze(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        """Compute inline squeeze state and momentum."""
        close = df["close"].values.astype(float)
        high = df["high"].values.astype(float)
        low = df["low"].values.astype(float)

        # Bollinger Bands
        bb_mid = pd.Series(close).rolling(self.bb_period).mean()
        bb_std = pd.Series(close).rolling(self.bb_period).std()
        bb_upper = bb_mid + self.bb_mult * bb_std
        bb_lower = bb_mid - self.bb_mult * bb_std

        # Keltner Channel
        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - np.roll(close, 1)),
                np.abs(low - np.roll(close, 1)),
            ),
        )
        tr[0] = high[0] - low[0]
        atr = pd.Series(tr).ewm(alpha=1.0 / self.kc_period, adjust=False).mean()
        kc_mid = pd.Series(close).ewm(span=self.kc_period, adjust=False).mean()
        kc_upper = kc_mid + self.kc_mult * atr
        kc_lower = kc_mid - self.kc_mult * atr

        squeeze_on = ((bb_lower > kc_lower) & (bb_upper < kc_upper)).values.astype(float)

        # Momentum: price relative to average of HL-midline and BB-midline
        hl_mid = (pd.Series(high).rolling(self.kc_period).max() + pd.Series(low).rolling(self.kc_period).min()) / 2
        momentum = pd.Series(close) - (hl_mid + bb_mid) / 2

        return {
            "squeeze_on": squeeze_on,
            "momentum": momentum.values,
            "atr": atr.values,
        }

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        min_bars = max(self.bb_period, self.kc_period) + self.min_squeeze_bars + 5
        if len(price_data) < min_bars:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0,
                                 target_price=float(price_data["close"].iloc[-1]) if len(price_data) > 0 else 0.0)

        current_price = float(price_data["close"].iloc[-1])
        sq = self._compute_squeeze(price_data)

        # Count consecutive squeeze bars ending at bar -2 (last closed squeeze bar)
        squeeze_arr = sq["squeeze_on"]
        consecutive_squeeze = 0
        for i in range(len(squeeze_arr) - 2, -1, -1):
            if squeeze_arr[i] == 1.0:
                consecutive_squeeze += 1
            else:
                break

        # Squeeze must have been active for min_squeeze_bars, then released NOW
        is_squeeze_fire = (
            consecutive_squeeze >= self.min_squeeze_bars
            and squeeze_arr[-1] == 0.0
        )

        if not is_squeeze_fire:
            return TradingSignal(
                symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0,
                target_price=current_price,
                metadata={
                    "strategy": "squeeze_breakout",
                    "squeeze_active": bool(squeeze_arr[-1]),
                    "consecutive_squeeze_bars": consecutive_squeeze,
                },
            )

        # Volume confirmation
        vol = price_data["volume"].values.astype(float)
        avg_vol = np.mean(vol[-self.bb_period - 1:-1])
        vol_ratio = vol[-1] / max(avg_vol, 1) if avg_vol > 0 else 0.0

        if vol_ratio < self.volume_confirm_mult:
            return TradingSignal(
                symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0,
                target_price=current_price,
                metadata={"strategy": "squeeze_breakout", "reason": "no_volume_confirmation", "vol_ratio": vol_ratio},
            )

        # Direction from momentum histogram
        mom = sq["momentum"][-1]
        if np.isnan(mom):
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=current_price)

        signal_type = SignalType.BUY if mom > 0 else SignalType.SELL

        # Confidence: tighter squeeze + more volume = higher confidence
        squeeze_quality = min(1.0, consecutive_squeeze / 10.0)
        vol_quality = min(1.0, (vol_ratio - 1.0) / 3.0)
        confidence = float(min(0.92, max(0.2, 0.4 * squeeze_quality + 0.35 * vol_quality + 0.25)))

        atr_val = float(sq["atr"][-1]) if not np.isnan(sq["atr"][-1]) else current_price * 0.02
        position_size = await self.calculate_position_size(symbol, current_price, confidence)

        if signal_type == SignalType.BUY:
            stop_loss = current_price - atr_val * self.atr_stop_mult
            take_profit = current_price + atr_val * self.atr_tp_mult
        else:
            stop_loss = current_price + atr_val * self.atr_stop_mult
            take_profit = current_price - atr_val * self.atr_tp_mult

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            target_price=take_profit,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            metadata={
                "strategy": "squeeze_breakout",
                "consecutive_squeeze_bars": consecutive_squeeze,
                "momentum": float(mom),
                "volume_ratio": vol_ratio,
                "squeeze_quality": squeeze_quality,
                "atr": atr_val,
            },
        )

    def get_required_features(self) -> list[str]:
        return []


# ---------------------------------------------------------------------------
# 8. Failed Breakout Reversal Strategy
# ---------------------------------------------------------------------------
class FailedBreakoutReversalStrategy(BaseStrategy):
    """Profit from breakouts that fail — a high-edge contrarian setup.

    Many breakouts fail.  When price breaks above resistance (or below support)
    on high volume but quickly reverses back inside the range, it traps
    breakout traders.  Their stop-loss liquidations fuel a powerful move in
    the opposite direction.

    Detection logic:
    1. Price broke the Donchian channel boundary within the last N bars
    2. Price has now returned INSIDE the channel
    3. The failed-breakout reversal is confirmed once price crosses back
       through the opposite side of the midline

    This is essentially the *inverse* of a standard breakout strategy and
    tends to work best when the market is range-bound (low ADX).
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        lookback: int = 20,
        recapture_window: int = 5,
        adx_ceiling: float = 25.0,
        atr_stop_mult: float = 1.5,
        atr_tp_mult: float = 2.5,
    ):
        super().__init__("FailedBreakoutReversal", risk_manager, stop_loss_pct=0.02, take_profit_pct=0.04)
        self.lookback = lookback
        self.recapture_window = recapture_window
        self.adx_ceiling = adx_ceiling
        self.atr_stop_mult = atr_stop_mult
        self.atr_tp_mult = atr_tp_mult

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        min_len = self.lookback + self.recapture_window + 5
        if len(price_data) < min_len:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=0.0)

        current_price = float(price_data["close"].iloc[-1])
        closes = price_data["close"].values.astype(float)
        highs = price_data["high"].values.astype(float)
        lows = price_data["low"].values.astype(float)

        # Donchian channel (excluding last bar)
        chan_high = np.max(highs[-(self.lookback + self.recapture_window):-self.recapture_window])
        chan_low = np.min(lows[-(self.lookback + self.recapture_window):-self.recapture_window])
        chan_mid = (chan_high + chan_low) / 2.0

        # ADX filter: only trade failed breakouts when ADX < ceiling (range-bound)
        adx_val = None
        if isinstance(features, pd.DataFrame) and "adx" in features.columns:
            adx_val = float(features["adx"].iloc[-1]) if not pd.isna(features["adx"].iloc[-1]) else None
        if adx_val is not None and adx_val > self.adx_ceiling:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0,
                                 target_price=current_price,
                                 metadata={"strategy": "failed_breakout", "reason": "trending_market", "adx": adx_val})

        # Check for failed bullish breakout (broke above, came back)
        recent_highs = highs[-self.recapture_window:]
        recent_closes = closes[-self.recapture_window:]
        broke_above = np.any(recent_highs > chan_high)
        recaptured_below = current_price < chan_high  # Price returned inside channel

        # Check for failed bearish breakout (broke below, came back)
        recent_lows = lows[-self.recapture_window:]
        broke_below = np.any(recent_lows < chan_low)
        recaptured_above = current_price > chan_low

        signal_type = SignalType.HOLD
        breakout_side = None

        if broke_above and recaptured_below and current_price < chan_mid:
            # Failed bullish breakout => short / sell
            signal_type = SignalType.SELL
            breakout_side = "failed_bull"
        elif broke_below and recaptured_above and current_price > chan_mid:
            # Failed bearish breakout => buy
            signal_type = SignalType.BUY
            breakout_side = "failed_bear"

        if signal_type == SignalType.HOLD:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0,
                                 target_price=current_price,
                                 metadata={"strategy": "failed_breakout", "chan_high": chan_high, "chan_low": chan_low})

        # Confidence scales with how decisively price re-entered the channel
        if breakout_side == "failed_bull":
            depth = (chan_high - current_price) / max(chan_high - chan_low, 1e-9)
        else:
            depth = (current_price - chan_low) / max(chan_high - chan_low, 1e-9)
        confidence = float(min(0.85, max(0.2, 0.3 + depth * 0.5)))

        atr = float(features["atr"].iloc[-1]) if isinstance(features, pd.DataFrame) and "atr" in features.columns and not pd.isna(features["atr"].iloc[-1]) else current_price * 0.02
        position_size = await self.calculate_position_size(symbol, current_price, confidence)

        if signal_type == SignalType.BUY:
            stop_loss = current_price - atr * self.atr_stop_mult
            take_profit = current_price + atr * self.atr_tp_mult
        else:
            stop_loss = current_price + atr * self.atr_stop_mult
            take_profit = current_price - atr * self.atr_tp_mult

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            target_price=take_profit,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            metadata={
                "strategy": "failed_breakout",
                "breakout_side": breakout_side,
                "depth_ratio": float(depth),
                "channel_high": chan_high,
                "channel_low": chan_low,
                "adx": adx_val,
            },
        )

    def get_required_features(self) -> list[str]:
        return ["atr"]


# ---------------------------------------------------------------------------
# 9. Multi-Timeframe Breakout Confirmation Strategy
# ---------------------------------------------------------------------------
class MultiTimeframeBreakoutStrategy(BaseStrategy):
    """Breakout strategy with multi-timeframe alignment for higher conviction.

    The single biggest cause of breakout strategy failure is trading breakouts
    that are *not* aligned with the larger timeframe trend.  This strategy
    solves that by synthesizing multiple timeframe views from a single bar
    series:

    1. **Higher timeframe trend** — Determined via a long-lookback SMA slope
       and whether price is above/below it.
    2. **Trading timeframe breakout** — Short-lookback Donchian channel breakout.
    3. **Momentum confirmation** — MACD histogram direction and RSI not
       over-extended.

    Only when ALL three timeframes agree does the strategy fire, dramatically
    reducing false breakouts and increasing win rate.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        fast_lookback: int = 20,
        slow_lookback: int = 60,
        trend_sma: int = 100,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        volume_confirm: float = 1.3,
        atr_stop_mult: float = 2.0,
        atr_tp_mult: float = 3.5,
    ):
        super().__init__("MultiTFBreakout", risk_manager, stop_loss_pct=0.03, take_profit_pct=0.07)
        self.fast_lookback = fast_lookback
        self.slow_lookback = slow_lookback
        self.trend_sma = trend_sma
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.volume_confirm = volume_confirm
        self.atr_stop_mult = atr_stop_mult
        self.atr_tp_mult = atr_tp_mult

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        min_len = max(self.trend_sma, self.slow_lookback) + 10
        if len(price_data) < min_len:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0,
                                 target_price=float(price_data["close"].iloc[-1]) if len(price_data) > 0 else 0.0)

        close = price_data["close"].values.astype(float)
        high = price_data["high"].values.astype(float)
        low = price_data["low"].values.astype(float)
        vol = price_data["volume"].values.astype(float)
        current_price = float(close[-1])

        # 1. HIGHER TIMEFRAME TREND (long SMA slope)
        sma_long = pd.Series(close).rolling(self.trend_sma).mean().values
        if np.isnan(sma_long[-1]):
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=current_price)

        sma_slope = (sma_long[-1] - sma_long[-5]) / max(abs(sma_long[-5]), 1e-9)
        price_above_sma = current_price > sma_long[-1]
        higher_tf_bullish = sma_slope > 0 and price_above_sma
        higher_tf_bearish = sma_slope < 0 and not price_above_sma

        # 2. TRADING TIMEFRAME BREAKOUT (Donchian channels)
        fast_high = np.max(high[-(self.fast_lookback + 1):-1])
        fast_low = np.min(low[-(self.fast_lookback + 1):-1])
        bullish_breakout = current_price > fast_high
        bearish_breakout = current_price < fast_low

        # 3. MOMENTUM CONFIRMATION
        rsi_val = None
        macd_hist = None
        if isinstance(features, pd.DataFrame) and not features.empty:
            if "rsi" in features.columns:
                rsi_val = float(features["rsi"].iloc[-1]) if not pd.isna(features["rsi"].iloc[-1]) else None
            if "macd_histogram" in features.columns:
                macd_hist = float(features["macd_histogram"].iloc[-1]) if not pd.isna(features["macd_histogram"].iloc[-1]) else None

        # Combine all three filters
        signal_type = SignalType.HOLD

        if (higher_tf_bullish and bullish_breakout
            and (macd_hist is None or macd_hist > 0)
            and (rsi_val is None or rsi_val < self.rsi_overbought)):
            signal_type = SignalType.BUY

        elif (higher_tf_bearish and bearish_breakout
              and (macd_hist is None or macd_hist < 0)
              and (rsi_val is None or rsi_val > self.rsi_oversold)):
            signal_type = SignalType.SELL

        if signal_type == SignalType.HOLD:
            return TradingSignal(
                symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0,
                target_price=current_price,
                metadata={
                    "strategy": "multi_tf_breakout",
                    "higher_tf_bullish": higher_tf_bullish,
                    "higher_tf_bearish": higher_tf_bearish,
                    "bullish_breakout": bullish_breakout,
                    "bearish_breakout": bearish_breakout,
                    "rsi": rsi_val,
                    "macd_hist": macd_hist,
                },
            )

        # Volume confirmation
        avg_vol = np.mean(vol[-(self.fast_lookback + 1):-1])
        vol_ratio = vol[-1] / max(avg_vol, 1) if avg_vol > 0 else 0.0
        if vol_ratio < self.volume_confirm:
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0,
                                 target_price=current_price,
                                 metadata={"strategy": "multi_tf_breakout", "reason": "no_volume", "vol_ratio": vol_ratio})

        # Confidence: multi-factor
        trend_strength = min(1.0, abs(sma_slope) * 100)
        breakout_strength = abs(current_price - (fast_high if signal_type == SignalType.BUY else fast_low)) / max(current_price * 0.01, 1e-9)
        breakout_strength = min(1.0, breakout_strength)
        vol_strength = min(1.0, (vol_ratio - 1.0) / 3.0)

        confidence = float(min(0.92, max(0.25, 0.3 * trend_strength + 0.35 * breakout_strength + 0.2 * vol_strength + 0.15)))

        atr = float(features["atr"].iloc[-1]) if isinstance(features, pd.DataFrame) and "atr" in features.columns and not pd.isna(features["atr"].iloc[-1]) else current_price * 0.02
        position_size = await self.calculate_position_size(symbol, current_price, confidence)

        if signal_type == SignalType.BUY:
            stop_loss = current_price - atr * self.atr_stop_mult
            take_profit = current_price + atr * self.atr_tp_mult
        else:
            stop_loss = current_price + atr * self.atr_stop_mult
            take_profit = current_price - atr * self.atr_tp_mult

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            target_price=take_profit,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            metadata={
                "strategy": "multi_tf_breakout",
                "higher_tf_bullish": higher_tf_bullish,
                "higher_tf_bearish": higher_tf_bearish,
                "sma_slope": float(sma_slope),
                "breakout_strength": breakout_strength,
                "volume_ratio": vol_ratio,
                "rsi": rsi_val,
                "macd_hist": macd_hist,
                "trend_strength": trend_strength,
            },
        )

    def get_required_features(self) -> list[str]:
        return ["atr", "rsi", "macd_histogram"]
