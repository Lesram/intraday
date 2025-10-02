"""
Basic Trading Strategy Module
Provides deterministic RSI + SMA cross strategy implementation.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from backend.features.technical_indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


@dataclass
class StrategyDecision:
    """Strategy decision result."""
    action: str  # "buy", "sell", "hold"
    confidence: float  # 0.0 to 1.0
    tp_pct: float  # take profit percentage
    sl_pct: float  # stop loss percentage
    reason: str  # explanation for the decision


class BasicStrategy:
    """
    Basic deterministic trading strategy using RSI and SMA cross signals.
    
    Strategy Logic:
    - RSI < rsi_buy threshold => buy signal
    - RSI > rsi_sell threshold => sell signal 
    - SMA fast > SMA slow => bullish bias (tie-breaker)
    - SMA fast < SMA slow => bearish bias (tie-breaker)
    - Confidence scaled by distance from RSI thresholds
    """
    
    def __init__(
        self, 
        rsi_buy: float = 35, 
        rsi_sell: float = 65, 
        sma_fast: int = 20, 
        sma_slow: int = 50,
        tp_pct: float = 2.0,  # default 2% take profit
        sl_pct: float = 1.0   # default 1% stop loss
    ):
        """
        Initialize BasicStrategy with configurable parameters.
        
        Args:
            rsi_buy: RSI threshold for buy signals (typically 30-40)
            rsi_sell: RSI threshold for sell signals (typically 60-70)
            sma_fast: Fast SMA period for trend confirmation
            sma_slow: Slow SMA period for trend confirmation
            tp_pct: Take profit percentage
            sl_pct: Stop loss percentage
        """
        self.rsi_buy = rsi_buy
        self.rsi_sell = rsi_sell
        self.sma_fast = sma_fast
        self.sma_slow = sma_slow
        self.tp_pct = tp_pct
        self.sl_pct = sl_pct
        
        self.indicators = TechnicalIndicators()
        
    def decide(
        self, 
        *,
        close_prices: Sequence[float] | None = None,
        closes: Sequence[float] | None = None,
    ) -> dict[str, Any]:
        """
        Generate trading decision based on price history.
        
        Accepts either `close_prices` or `closes` parameter for compatibility.
        Uses whichever is provided (not None). Raises ValueError if both are None.
        
        Args:
            close_prices: List of historical close prices (most recent last) 
            closes: Alternative name for close_prices (backward compatibility)
            
        Returns:
            Dict with keys: action, confidence, tp_pct, sl_pct, reason
        """
        try:
            # Choose the series - use whichever is provided
            series = close_prices or closes
            if series is None:
                raise ValueError("Either close_prices or closes must be provided")
                
            if not series or len(series) < max(self.sma_slow + 1, 15):
                return self._no_decision("insufficient_data", len(series) if series else 0)
            
            # Calculate RSI using the chosen series
            rsi_result = self.indicators.calculate_rsi(series)
            if not rsi_result or rsi_result.value is None:
                return self._no_decision("rsi_calculation_failed", 0)
                
            rsi = rsi_result.value
            
            # Calculate SMAs for trend confirmation
            sma_fast_result = self.indicators.calculate_sma(series, self.sma_fast)
            sma_slow_result = self.indicators.calculate_sma(series, self.sma_slow)
            
            sma_fast = sma_fast_result.value if sma_fast_result else None
            sma_slow = sma_slow_result.value if sma_slow_result else None
            
            # Determine trend bias
            trend_bias = "neutral"
            if sma_fast and sma_slow:
                if sma_fast > sma_slow:
                    trend_bias = "bullish"
                elif sma_fast < sma_slow:
                    trend_bias = "bearish"
            
            # Primary decision based on RSI
            if rsi < self.rsi_buy:
                # RSI oversold - potential buy
                confidence = self._confidence_from_rsi_threshold(rsi, self.rsi_buy, self.rsi_sell)
                
                # Boost confidence if trend is bullish
                if trend_bias == "bullish":
                    confidence = min(1.0, confidence * 1.2)
                elif trend_bias == "bearish":
                    confidence = confidence * 0.8
                
                return StrategyDecision(
                    action="buy",
                    confidence=confidence,
                    tp_pct=self.tp_pct,
                    sl_pct=self.sl_pct,
                    reason=f"RSI oversold ({rsi:.1f} < {self.rsi_buy}), trend: {trend_bias}"
                ).__dict__
                
            elif rsi > self.rsi_sell:
                # RSI overbought - potential sell
                confidence = self._confidence_from_rsi_threshold(rsi, self.rsi_buy, self.rsi_sell)
                
                # Boost confidence if trend is bearish
                if trend_bias == "bearish":
                    confidence = min(1.0, confidence * 1.2)
                elif trend_bias == "bullish":
                    confidence = confidence * 0.8
                
                return StrategyDecision(
                    action="sell",
                    confidence=confidence,
                    tp_pct=self.tp_pct,
                    sl_pct=self.sl_pct,
                    reason=f"RSI overbought ({rsi:.1f} > {self.rsi_sell}), trend: {trend_bias}"
                ).__dict__
                
            else:
                # RSI neutral - use trend as tie-breaker with low confidence
                if trend_bias == "bullish" and rsi < 50:
                    return StrategyDecision(
                        action="buy",
                        confidence=0.3,
                        tp_pct=self.tp_pct,
                        sl_pct=self.sl_pct,
                        reason=f"Neutral RSI ({rsi:.1f}), bullish trend bias"
                    ).__dict__
                elif trend_bias == "bearish" and rsi > 50:
                    return StrategyDecision(
                        action="sell",
                        confidence=0.3,
                        tp_pct=self.tp_pct,
                        sl_pct=self.sl_pct,
                        reason=f"Neutral RSI ({rsi:.1f}), bearish trend bias"
                    ).__dict__
                else:
                    return StrategyDecision(
                        action="hold",
                        confidence=0.8,
                        tp_pct=0.0,
                        sl_pct=0.0,
                        reason=f"Neutral conditions - RSI: {rsi:.1f}, trend: {trend_bias}"
                    ).__dict__
                    
        except Exception as e:
            logger.error(f"Strategy decision error: {e}", exc_info=True)
            return self._no_decision("calculation_error", str(e))
    
    def _calculate_confidence(self, rsi: float, threshold: float, action: str) -> float:
        """
        Calculate confidence based on distance from RSI threshold.
        
        Args:
            rsi: Current RSI value
            threshold: RSI threshold
            action: "buy" or "sell"
            
        Returns:
            Confidence value between 0.0 and 1.0
        """
        return self._confidence_from_rsi_threshold(rsi, self.rsi_buy, self.rsi_sell)
    
    def _confidence_from_rsi_threshold(self, rsi: float, buy_thr: float, sell_thr: float) -> float:
        """
        Unit-testable helper to calculate confidence from RSI and thresholds.
        
        Args:
            rsi: Current RSI value (0-100)
            buy_thr: Buy threshold (typically 30-40)
            sell_thr: Sell threshold (typically 60-70)
            
        Returns:
            Confidence value between 0.3 and 1.0
        """
        if rsi <= buy_thr:
            # RSI oversold - buy signal strength
            distance = buy_thr - rsi
            max_distance = buy_thr  # Distance from 0 to buy_thr
        elif rsi >= sell_thr:
            # RSI overbought - sell signal strength  
            distance = rsi - sell_thr
            max_distance = 100 - sell_thr  # Distance from sell_thr to 100
        else:
            # RSI neutral - low confidence
            return 0.3
            
        # Normalize distance to confidence (0.3 to 1.0 range)
        raw_confidence = distance / max_distance
        return max(0.3, min(1.0, raw_confidence))
    
    def _no_decision(self, reason: str, detail: Any) -> dict[str, Any]:
        """Return a hold decision when no clear signal exists."""
        return StrategyDecision(
            action="hold",
            confidence=0.0,
            tp_pct=0.0,
            sl_pct=0.0,
            reason=f"{reason}: {detail}"
        ).__dict__
    
    def get_parameters(self) -> dict[str, Any]:
        """Get current strategy parameters."""
        return {
            "rsi_buy": self.rsi_buy,
            "rsi_sell": self.rsi_sell,
            "sma_fast": self.sma_fast,
            "sma_slow": self.sma_slow,
            "tp_pct": self.tp_pct,
            "sl_pct": self.sl_pct
        }