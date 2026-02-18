"""
Trading Strategies Framework
Implements various algorithmic trading strategies with unified interface
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging

# Avoid importing heavy ML dependencies (TensorFlow) at module import time unless explicitly enabled.
import os as _os  # local alias to avoid polluting namespace
from typing import Any

import numpy as np
import pandas as pd

from ..config import get_settings

if _os.getenv("ENABLE_ML_MODELS", "").lower() in ("1", "true", "yes"):
    try:  # pragma: no cover - import guard for optional ML environments
        from ..models.ensemble_model import EnsembleModel  # type: ignore
    except Exception:
        class EnsembleModel:  # type: ignore
            pass
else:  # default: lightweight stub to keep imports fast in tests
    class EnsembleModel:  # type: ignore
        pass
from ..risk.risk_manager import RiskManager
from ..utils.helpers import calculate_sharpe_ratio
from ..utils.logger import audit_logger


class SignalType(Enum):
    """Trading signal types"""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    STRONG_BUY = "STRONG_BUY"
    STRONG_SELL = "STRONG_SELL"


class OrderType(Enum):
    """Order types"""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


@dataclass
class TradingSignal:
    """Trading signal container"""

    symbol: str
    signal_type: SignalType
    confidence: float
    target_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    position_size: float = 0.0
    order_type: OrderType = OrderType.MARKET
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyPerformance:
    """Strategy performance metrics"""

    strategy_name: str
    total_returns: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    avg_trade_duration: timedelta
    last_updated: datetime


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies"""

    # Default risk parameters (can be overridden in child classes)
    DEFAULT_MAX_RISK_PER_TRADE = 0.02  # 2% max risk per trade
    DEFAULT_STOP_LOSS_PCT = 0.02  # 2% stop loss — keeps losses tight
    DEFAULT_TAKE_PROFIT_PCT = 0.05  # 5% take profit — 1:2.5 risk-reward ratio

    def __init__(
        self,
        name: str,
        risk_manager: RiskManager,
        max_risk_per_trade: float | None = None,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
    ):
        self.name = name
        self.risk_manager = risk_manager
        self.settings = get_settings()
        self.positions = {}
        self.trade_history = []
        self.performance_metrics = None
        self.is_active = True

        # Configurable risk parameters
        self.max_risk_per_trade = max_risk_per_trade if max_risk_per_trade is not None else self.DEFAULT_MAX_RISK_PER_TRADE
        self.stop_loss_pct = stop_loss_pct if stop_loss_pct is not None else self.DEFAULT_STOP_LOSS_PCT
        self.take_profit_pct = take_profit_pct if take_profit_pct is not None else self.DEFAULT_TAKE_PROFIT_PCT

    @abstractmethod
    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        """Generate trading signal for given symbol"""
        pass

    @abstractmethod
    def get_required_features(self) -> list[str]:
        """Get list of required feature names"""
        pass

    async def validate_signal(self, signal: TradingSignal) -> bool:
        """Validate signal against risk parameters"""
        if not self.is_active:
            return False

        # Risk manager validation
        risk_check = await self.risk_manager.assess_position_risk(
            symbol=signal.symbol,
            quantity=signal.position_size,
            side=(
                "buy"
                if signal.signal_type in [SignalType.BUY, SignalType.STRONG_BUY]
                else "sell"
            ),
        )

        return risk_check["approved"]

    async def calculate_position_size(
        self, symbol: str, price: float, confidence: float
    ) -> float:
        """Calculate position size based on confidence and risk."""
        import inspect

        base_position = float(self.settings.trading.max_position_size) * float(confidence)

        # Risk-adjusted position sizing
        portfolio_value = self.risk_manager.get_portfolio_value()
        if inspect.isawaitable(portfolio_value):
            portfolio_value = await portfolio_value
        portfolio_value = float(portfolio_value or 0.0)

        max_risk_per_trade = portfolio_value * float(self.max_risk_per_trade)

        position_value = base_position * float(price)
        if max_risk_per_trade > 0 and position_value > max_risk_per_trade:
            base_position = max_risk_per_trade / float(price)

        return float(base_position)

    def update_performance(self, trade_results: list[dict[str, Any]]):
        """Update strategy performance metrics"""
        if not trade_results:
            return

        returns = [trade["return"] for trade in trade_results]
        durations = [trade["duration"] for trade in trade_results]

        self.performance_metrics = StrategyPerformance(
            strategy_name=self.name,
            total_returns=sum(returns),
            sharpe_ratio=calculate_sharpe_ratio(returns),
            max_drawdown=self._calculate_max_drawdown(returns),
            win_rate=len([r for r in returns if r > 0]) / len(returns),
            total_trades=len(trade_results),
            avg_trade_duration=sum(durations, timedelta()) / len(durations),
            last_updated=datetime.now(),
        )

    def _calculate_max_drawdown(self, returns: list[float]) -> float:
        """Calculate maximum drawdown from returns"""
        cumulative = np.cumprod(1 + np.array(returns))
        peak = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - peak) / peak
        return float(np.min(drawdown))


class EnsembleStrategy(BaseStrategy):
    """Strategy based on AI ensemble predictions"""

    def __init__(
        self,
        risk_manager: RiskManager,
        ensemble_model: EnsembleModel,
        confidence_threshold: float = 0.6,
        return_threshold: float = 0.02,
        strong_return_threshold: float = 0.05,
    ):
        super().__init__("EnsembleStrategy", risk_manager)
        self.ensemble_model = ensemble_model
        self.confidence_threshold = confidence_threshold
        self.return_threshold = return_threshold
        self.strong_return_threshold = strong_return_threshold

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        """Generate signal based on ensemble model prediction"""

        # Get ensemble prediction
        prediction = self.ensemble_model.predict(price_data, features, symbol)

        # Current price for comparison
        current_price = price_data["close"].iloc[-1]

        # Calculate expected return
        predicted_return = (
            prediction.ensemble_prediction - current_price
        ) / current_price

        # Determine signal type based on prediction and confidence
        signal_type = SignalType.HOLD
        if prediction.ensemble_confidence > self.confidence_threshold:
            if predicted_return > self.return_threshold:
                signal_type = (
                    SignalType.STRONG_BUY if predicted_return > self.strong_return_threshold else SignalType.BUY
                )
            elif predicted_return < -self.return_threshold:
                signal_type = (
                    SignalType.STRONG_SELL
                    if predicted_return < -self.strong_return_threshold
                    else SignalType.SELL
                )

        # Calculate position size
        position_size = 0.0
        if signal_type != SignalType.HOLD:
            position_size = await self.calculate_position_size(
                symbol, float(current_price), float(prediction.ensemble_confidence)
            )

        # Set stop loss and take profit relative to current price
        stop_loss = None
        take_profit = None
        if signal_type in [SignalType.BUY, SignalType.STRONG_BUY]:
            stop_loss = current_price * (1 - self.stop_loss_pct)
            take_profit = current_price * (1 + self.take_profit_pct)
        elif signal_type in [SignalType.SELL, SignalType.STRONG_SELL]:
            stop_loss = current_price * (1 + self.stop_loss_pct)
            take_profit = current_price * (1 - self.take_profit_pct)

        signal = TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=prediction.ensemble_confidence,
            target_price=prediction.ensemble_prediction,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            metadata={
                "predicted_return": predicted_return,
                "individual_predictions": prediction.predictions,
                "model_confidences": prediction.confidence_scores,
            },
        )

        audit_logger.info(
            "ensemble_signal_generated",
            symbol=symbol,
            signal=signal_type.value,
            confidence=prediction.ensemble_confidence,
            predicted_return=predicted_return,
        )

        return signal

    def get_required_features(self) -> list[str]:
        """Features required by ensemble model"""
        return [
            "sma_20",
            "sma_50",
            "ema_12",
            "ema_26",
            "rsi",
            "macd",
            "macd_signal",
            "bb_upper",
            "bb_lower",
            "volume_sma",
            "atr",
            "adx",
            "cci",
            "williams_r",
            "stoch_k",
            "stoch_d",
            "momentum",
            "rate_of_change",
        ]


class MeanReversionStrategy(BaseStrategy):
    """Mean reversion strategy using Bollinger Bands and RSI"""

    def __init__(
        self,
        risk_manager: RiskManager,
        oversold_threshold: float = 30.0,
        overbought_threshold: float = 70.0,
        band_tolerance: float = 0.01,  # How close to band before triggering (1%)
        band_stop_offset: float = 0.02,  # Stop loss offset from band (2%)
    ):
        super().__init__("MeanReversionStrategy", risk_manager)
        self.oversold_threshold = oversold_threshold
        self.overbought_threshold = overbought_threshold
        self.band_tolerance = band_tolerance
        self.band_stop_offset = band_stop_offset

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        """Generate mean reversion signal"""
        # Insufficient data guards
        required_cols = ["close"]
        for col in required_cols:
            if col not in price_data or price_data[col].empty:
                return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=0.0)
        for col in ["rsi", "bb_upper", "bb_lower"]:
            if col not in features or features[col].empty:
                return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.0, target_price=0.0)

        current_price = price_data["close"].iloc[-1]
        current_rsi = features["rsi"].iloc[-1]
        bb_upper = features["bb_upper"].iloc[-1]
        bb_lower = features["bb_lower"].iloc[-1]
        bb_middle = (bb_upper + bb_lower) / 2

        # Mean reversion logic
        signal_type = SignalType.HOLD
        confidence = 0.5

        # Oversold condition: price near lower band + low RSI
        if current_price < bb_lower * (1 + self.band_tolerance) and current_rsi < self.oversold_threshold:
            signal_type = SignalType.BUY
            confidence = min(0.9, max(0.1, (self.oversold_threshold - current_rsi) / 20))

        # Overbought condition: price near upper band + high RSI
        elif (
            current_price > bb_upper * (1 - self.band_tolerance) and current_rsi > self.overbought_threshold
        ):
            signal_type = SignalType.SELL
            confidence = min(0.9, max(0.1, (current_rsi - self.overbought_threshold) / 20))

        position_size = await self.calculate_position_size(symbol, float(current_price), float(confidence))

        # Set targets
        target_price = bb_middle  # Revert to mean
        stop_loss = None
        take_profit = None

        if signal_type == SignalType.BUY:
            stop_loss = bb_lower * (1 - self.band_stop_offset)
            take_profit = bb_middle
        elif signal_type == SignalType.SELL:
            stop_loss = bb_upper * (1 + self.band_stop_offset)
            take_profit = bb_middle

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            target_price=target_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size if signal_type != SignalType.HOLD else 0.0,
            metadata={
                "rsi": current_rsi,
                "bb_position": (current_price - bb_lower) / (bb_upper - bb_lower),
                "strategy": "mean_reversion",
            },
        )

    def get_required_features(self) -> list[str]:
        return ["rsi", "bb_upper", "bb_lower"]


class MomentumStrategy(BaseStrategy):
    """Momentum strategy using MACD and moving averages"""

    def __init__(
        self,
        risk_manager: RiskManager,
        momentum_multiplier: float = 0.1,  # Target price multiplier based on momentum
        stop_loss_pct: float = 0.03,  # 3% stop loss for momentum trades
    ):
        super().__init__("MomentumStrategy", risk_manager, stop_loss_pct=stop_loss_pct)
        self.momentum_multiplier = momentum_multiplier

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        """Generate momentum signal"""

        current_price = price_data["close"].iloc[-1]
        macd = features["macd"].iloc[-1]
        macd_signal = features["macd_signal"].iloc[-1]
        sma_20 = features["sma_20"].iloc[-1]
        sma_50 = features["sma_50"].iloc[-1]

        # Momentum conditions
        signal_type = SignalType.HOLD
        confidence = 0.5

        # Normalize MACD diff by price to make confidence scale-invariant
        macd_diff_normalized = abs(macd - macd_signal) / max(float(current_price), 1e-9)

        # Bullish momentum: MACD above signal + price above moving averages
        if macd > macd_signal and current_price > sma_20 > sma_50:
            signal_type = SignalType.BUY
            confidence = min(0.85, max(0.1, macd_diff_normalized * 1000))

        # Bearish momentum: MACD below signal + price below moving averages
        elif macd < macd_signal and current_price < sma_20 < sma_50:
            signal_type = SignalType.SELL
            confidence = min(0.85, max(0.1, macd_diff_normalized * 1000))

        position_size = await self.calculate_position_size(symbol, float(current_price), float(confidence))

        # Set targets based on momentum strength — normalized by price for scale-invariance
        momentum_strength = abs(macd - macd_signal) / max(float(current_price), 1e-9)
        target_multiplier = 1 + (momentum_strength * self.momentum_multiplier * 100)

        if signal_type == SignalType.HOLD:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=confidence,
                target_price=current_price,
                stop_loss=None,
                take_profit=None,
                position_size=0.0,
                metadata={
                    "macd": macd,
                    "macd_signal": macd_signal,
                    "sma_trend": "bullish" if sma_20 > sma_50 else "bearish",
                    "strategy": "momentum",
                },
            )

        target_price = (
            current_price * target_multiplier
            if signal_type == SignalType.BUY
            else current_price / target_multiplier
        )

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            target_price=target_price,
            stop_loss=(
                current_price * (1 - self.stop_loss_pct)
                if signal_type == SignalType.BUY
                else current_price * (1 + self.stop_loss_pct)
            ),
            take_profit=target_price,
            position_size=position_size,
            metadata={
                "macd": macd,
                "macd_signal": macd_signal,
                "sma_trend": "bullish" if sma_20 > sma_50 else "bearish",
                "strategy": "momentum",
            },
        )

    def get_required_features(self) -> list[str]:
        return ["macd", "macd_signal", "sma_20", "sma_50"]


class RegimeFilteredMomentumStrategy(BaseStrategy):
    """Regime-filtered momentum strategy.

    Trades only when:
    - Trend regime is aligned (price above/below SMA50)
    - RSI confirms momentum
    - Volatility is within a configured band (ATR ratio)
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        rsi_long: float = 55.0,
        rsi_short: float = 45.0,
        min_atr_ratio: float = 0.002,
        max_atr_ratio: float = 0.05,
        stop_loss_atr_mult: float = 1.5,
        take_profit_atr_mult: float = 2.0,
    ):
        super().__init__(
            "RegimeFilteredMomentumStrategy",
            risk_manager,
            stop_loss_pct=self.DEFAULT_STOP_LOSS_PCT,
            take_profit_pct=self.DEFAULT_TAKE_PROFIT_PCT,
        )
        self.rsi_long = rsi_long
        self.rsi_short = rsi_short
        self.min_atr_ratio = min_atr_ratio
        self.max_atr_ratio = max_atr_ratio
        self.stop_loss_atr_mult = stop_loss_atr_mult
        self.take_profit_atr_mult = take_profit_atr_mult

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        current_price = price_data["close"].iloc[-1]

        sma_50 = features["sma_50"].iloc[-1]
        rsi_value = features["rsi"].iloc[-1]
        atr = features["atr"].iloc[-1] if "atr" in features.columns else None
        atr_ratio = (
            features["atr_ratio"].iloc[-1]
            if "atr_ratio" in features.columns
            else (float(atr) / float(current_price) if atr is not None and current_price else None)
        )

        # Volatility gate
        if atr_ratio is None or not (self.min_atr_ratio <= float(atr_ratio) <= self.max_atr_ratio):
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                target_price=current_price,
                metadata={
                    "strategy": "regime_filtered_momentum",
                    "reason": "volatility_out_of_band",
                    "atr_ratio": float(atr_ratio) if atr_ratio is not None else None,
                },
            )

        trend_up = current_price > sma_50
        trend_down = current_price < sma_50

        signal_type = SignalType.HOLD
        if trend_up and rsi_value >= self.rsi_long:
            signal_type = SignalType.BUY
        elif trend_down and rsi_value <= self.rsi_short:
            signal_type = SignalType.SELL

        if signal_type == SignalType.HOLD:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                target_price=current_price,
                metadata={
                    "strategy": "regime_filtered_momentum",
                    "trend": "up" if trend_up else ("down" if trend_down else "flat"),
                    "rsi": float(rsi_value),
                    "atr_ratio": float(atr_ratio),
                },
            )

        # Confidence increases as RSI moves away from 50.
        confidence = min(0.85, max(0.1, abs(float(rsi_value) - 50.0) / 50.0))
        position_size = await self.calculate_position_size(symbol, float(current_price), float(confidence))

        if atr is None or pd.isna(atr):
            # Fallback to percent-based stops if ATR missing
            stop_loss = (
                current_price * (1 - self.stop_loss_pct)
                if signal_type == SignalType.BUY
                else current_price * (1 + self.stop_loss_pct)
            )
            take_profit = (
                current_price * (1 + self.take_profit_pct)
                if signal_type == SignalType.BUY
                else current_price * (1 - self.take_profit_pct)
            )
        else:
            atr_f = float(atr)
            stop_loss = (
                current_price - self.stop_loss_atr_mult * atr_f
                if signal_type == SignalType.BUY
                else current_price + self.stop_loss_atr_mult * atr_f
            )
            take_profit = (
                current_price + self.take_profit_atr_mult * atr_f
                if signal_type == SignalType.BUY
                else current_price - self.take_profit_atr_mult * atr_f
            )

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            target_price=take_profit,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            metadata={
                "strategy": "regime_filtered_momentum",
                "trend": "up" if trend_up else "down",
                "rsi": float(rsi_value),
                "sma_50": float(sma_50),
                "atr": float(atr) if atr is not None else None,
                "atr_ratio": float(atr_ratio),
            },
        )

    def get_required_features(self) -> list[str]:
        return ["sma_50", "rsi", "atr_ratio"]


class BreakoutStrategy(BaseStrategy):
    """Breakout strategy designed to capture large breaks.

    Core idea:
    - Detect price breaking above/below a rolling range (Donchian-style)
    - Confirm with volume expansion and reasonable volatility regime
    - Emit BUY/SELL with confidence scaled by breakout strength

    Notes:
    - This strategy can *detect* breakouts and provide confidence/diagnostics.
    - Actual stops/TP require execution support (brackets/trailing) beyond a simple market order.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        lookback: int = 20,
        buffer_pct: float = 0.002,
        volume_spike_mult: float = 1.5,
        min_atr_ratio: float = 0.002,
        max_atr_ratio: float = 0.08,
        allow_short: bool = True,
    ):
        super().__init__("BreakoutStrategy", risk_manager)
        self.lookback = lookback
        self.buffer_pct = buffer_pct
        self.volume_spike_mult = volume_spike_mult
        self.min_atr_ratio = min_atr_ratio
        self.max_atr_ratio = max_atr_ratio
        self.allow_short = allow_short
        self.atr_stop_mult = 2.0   # ATR multiplier for stop-loss
        self.atr_tp_mult = 3.0     # ATR multiplier for take-profit

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        if price_data is None or price_data.empty or len(price_data) < (self.lookback + 2):
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                target_price=float(price_data["close"].iloc[-1]) if isinstance(price_data, pd.DataFrame) and not price_data.empty else 0.0,
                metadata={"strategy": "breakout", "reason": "insufficient_history"},
            )

        df = price_data.copy()
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                raise ValueError(f"BreakoutStrategy requires OHLCV column '{col}'")

        # Rolling range excluding current bar
        prior_high = df["high"].rolling(self.lookback).max().shift(1).iloc[-1]
        prior_low = df["low"].rolling(self.lookback).min().shift(1).iloc[-1]
        close = float(df["close"].iloc[-1])
        vol = float(df["volume"].iloc[-1])
        avg_vol = float(df["volume"].rolling(self.lookback).mean().shift(1).iloc[-1])

        atr_ratio = None
        if isinstance(features, pd.DataFrame) and not features.empty:
            if "atr_ratio" in features.columns:
                atr_ratio = float(features["atr_ratio"].iloc[-1])
            elif "atr" in features.columns and close:
                atr_ratio = float(features["atr"].iloc[-1]) / close

        # Volatility regime gate
        if atr_ratio is None or not (self.min_atr_ratio <= atr_ratio <= self.max_atr_ratio):
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                target_price=close,
                metadata={
                    "strategy": "breakout",
                    "reason": "atr_ratio_out_of_band",
                    "atr_ratio": atr_ratio,
                },
            )

        vol_ratio = (vol / avg_vol) if avg_vol > 0 else 0.0
        if vol_ratio < self.volume_spike_mult:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                target_price=close,
                metadata={
                    "strategy": "breakout",
                    "reason": "no_volume_confirmation",
                    "volume_ratio": vol_ratio,
                },
            )

        upper_trigger = float(prior_high) * (1.0 + self.buffer_pct)
        lower_trigger = float(prior_low) * (1.0 - self.buffer_pct)

        signal_type = SignalType.HOLD
        breakout_strength = 0.0
        if close >= upper_trigger:
            signal_type = SignalType.BUY
            breakout_strength = (close - upper_trigger) / max(1e-9, upper_trigger)
        elif self.allow_short and close <= lower_trigger:
            signal_type = SignalType.SELL
            breakout_strength = (lower_trigger - close) / max(1e-9, lower_trigger)

        if signal_type == SignalType.HOLD:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                target_price=close,
                metadata={
                    "strategy": "breakout",
                    "reason": "no_breakout",
                    "upper_trigger": upper_trigger,
                    "lower_trigger": lower_trigger,
                    "volume_ratio": vol_ratio,
                    "atr_ratio": atr_ratio,
                },
            )

        # Confidence combines breakout strength and volume expansion.
        # Keep bounded and conservative.
        conf_from_break = min(0.6, breakout_strength * 50.0)  # 1% break => 0.5
        conf_from_vol = min(0.35, (vol_ratio - 1.0) / 5.0)
        confidence = float(max(0.15, min(0.9, conf_from_break + conf_from_vol)))

        position_size = await self.calculate_position_size(symbol, float(close), float(confidence))

        # ATR-based stops and targets for proper risk management
        atr_val = close * (atr_ratio if atr_ratio else 0.02)
        if signal_type == SignalType.BUY:
            stop_loss = close - atr_val * self.atr_stop_mult
            take_profit = close + atr_val * self.atr_tp_mult
        else:
            stop_loss = close + atr_val * self.atr_stop_mult
            take_profit = close - atr_val * self.atr_tp_mult

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            target_price=take_profit,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            metadata={
                "strategy": "breakout",
                "lookback": self.lookback,
                "upper_trigger": upper_trigger,
                "lower_trigger": lower_trigger,
                "breakout_strength": breakout_strength,
                "volume_ratio": vol_ratio,
                "atr_ratio": atr_ratio,
            },
        )

    def get_required_features(self) -> list[str]:
        return ["atr_ratio"]


class RebalancingStrategy(BaseStrategy):
    """Portfolio rebalancing strategy"""

    def __init__(
        self,
        risk_manager: RiskManager,
        target_weights: dict[str, float],
        rebalance_threshold: float = 0.05,
    ):
        super().__init__("RebalancingStrategy", risk_manager)
        self.target_weights = target_weights
        self.rebalance_threshold = rebalance_threshold  # Deviation threshold to trigger rebalance

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        """Generate rebalancing signal"""

        current_price = price_data["close"].iloc[-1]

        # Get current portfolio allocation
        portfolio_value = await self.risk_manager.get_portfolio_value()
        current_positions = await self.risk_manager.get_positions()

        # Calculate current weight
        current_value = current_positions.get(symbol, {}).get("market_value", 0)
        current_weight = current_value / portfolio_value if portfolio_value > 0 else 0

        # Target weight for this symbol
        target_weight = self.target_weights.get(symbol, 0)

        # Calculate deviation
        weight_deviation = abs(current_weight - target_weight)

        signal_type = SignalType.HOLD
        confidence = min(0.8, weight_deviation * 10)

        if weight_deviation > self.rebalance_threshold:
            if current_weight < target_weight:
                signal_type = SignalType.BUY
            else:
                signal_type = SignalType.SELL

        # Calculate required position adjustment
        target_value = portfolio_value * target_weight
        position_adjustment = (target_value - current_value) / current_price

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            target_price=current_price,  # Market price for rebalancing
            position_size=(
                abs(position_adjustment) if signal_type != SignalType.HOLD else 0.0
            ),
            order_type=OrderType.MARKET,
            metadata={
                "current_weight": current_weight,
                "target_weight": target_weight,
                "deviation": weight_deviation,
                "strategy": "rebalancing",
            },
        )

    def get_required_features(self) -> list[str]:
        return []  # Rebalancing doesn't need technical features


class StatisticalArbitrageStrategy(BaseStrategy):
    """Z-Score Mean Reversion with adaptive Kalman-filtered spread tracking.

    Core logic:
    - Tracks price spread as log(price) vs its Kalman-filtered trend
    - Computes z-score of deviation from smoothed mean
    - Enters when z-score exceeds entry_threshold, exits at exit_threshold
    - Uses half-life estimation for dynamic lookback calibration

    This strategy captures mean-reversion alpha in individual names by detecting
    statistically significant departures from a smoothed equilibrium price.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        reference_symbol: str = "SPY",
        lookback_period: int = 60,
        entry_threshold: float = 2.0,
        exit_threshold: float = 0.5,
        kalman_transition_cov: float = 0.001,
        kalman_observation_cov: float = 1.0,
    ):
        super().__init__("StatArbStrategy", risk_manager)
        self.reference_symbol = reference_symbol
        self.lookback_period = lookback_period
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.kalman_q = kalman_transition_cov
        self.kalman_r = kalman_observation_cov

    def _kalman_filter(self, observations: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """1D Kalman filter: returns (filtered_state, filtered_variance) arrays."""
        n = len(observations)
        x = np.zeros(n)  # state (smoothed level)
        p = np.zeros(n)  # state variance
        x[0] = observations[0]
        p[0] = 1.0
        for i in range(1, n):
            # Predict
            x_pred = x[i - 1]
            p_pred = p[i - 1] + self.kalman_q
            # Update
            k = p_pred / (p_pred + self.kalman_r)  # Kalman gain
            x[i] = x_pred + k * (observations[i] - x_pred)
            p[i] = (1 - k) * p_pred
        return x, p

    def _estimate_half_life(self, spread: np.ndarray) -> float:
        """Estimate OU half-life from spread via AR(1) regression."""
        if len(spread) < 20:
            return float(self.lookback_period)
        y = spread[1:]
        x = spread[:-1]
        denom = np.sum(x * x)
        if abs(denom) < 1e-12:
            return float(self.lookback_period)
        beta = np.sum(x * y) / denom
        if beta >= 1.0 or beta <= 0.0:
            return float(self.lookback_period)
        half_life = -np.log(2) / np.log(beta)
        return float(max(5, min(half_life, self.lookback_period * 2)))

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        """Generate z-score mean reversion signal with Kalman-filtered trend."""

        if len(price_data) < self.lookback_period:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                target_price=0.0,
            )

        current_price = price_data["close"].iloc[-1]

        # Use log prices for better statistical properties
        log_prices = np.log(price_data["close"].values.astype(float))

        # Apply Kalman filter to estimate smoothed trend
        filtered, _ = self._kalman_filter(log_prices)

        # Spread = log_price - kalman_filtered_trend
        spread = log_prices - filtered

        # Estimate mean-reversion half-life for dynamic lookback
        half_life = self._estimate_half_life(spread)
        effective_lookback = max(10, min(int(half_life * 2), len(spread)))

        # Z-score on recent spread window
        recent_spread = spread[-effective_lookback:]
        spread_mean = np.mean(recent_spread)
        spread_std = np.std(recent_spread, ddof=1)

        if spread_std < 1e-10:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                target_price=current_price,
            )

        z_score = (spread[-1] - spread_mean) / spread_std

        signal_type = SignalType.HOLD
        confidence = min(0.9, max(0.1, abs(z_score) / 5.0))

        if z_score > self.entry_threshold:
            signal_type = SignalType.SELL  # Price is high relative to trend
        elif z_score < -self.entry_threshold:
            signal_type = SignalType.BUY  # Price is low relative to trend
        elif abs(z_score) < self.exit_threshold:
            # Z-score reverted to mean — signal to close existing position
            signal_type = SignalType.HOLD
            confidence = 0.0

        position_size = await self.calculate_position_size(symbol, float(current_price), float(confidence))

        # Target = reversion to Kalman-filtered equilibrium
        target_price = float(np.exp(filtered[-1]))

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            target_price=target_price,
            stop_loss=(
                current_price * (1 + self.stop_loss_pct)
                if signal_type == SignalType.SELL
                else current_price * (1 - self.stop_loss_pct)
            ),
            take_profit=target_price,
            position_size=position_size if signal_type != SignalType.HOLD else 0.0,
            metadata={
                "z_score": float(z_score),
                "spread_mean": float(spread_mean),
                "spread_std": float(spread_std),
                "half_life": float(half_life),
                "kalman_level": float(np.exp(filtered[-1])),
                "effective_lookback": effective_lookback,
                "strategy": "statistical_arbitrage",
            },
        )

    def get_required_features(self) -> list[str]:
        return []


class StrategyManager:
    """Manages multiple trading strategies"""

    def __init__(self, risk_manager: RiskManager, ensemble_model: EnsembleModel):
        self.risk_manager = risk_manager
        self.ensemble_model = ensemble_model
        self.strategies: dict[str, BaseStrategy] = {}
        self.strategy_weights = {}
        self.settings = get_settings()

        # Initialize strategies
        self._initialize_strategies()

    def _initialize_strategies(self):
        """Initialize all available strategies"""
        self.strategies = {
            "ensemble": EnsembleStrategy(self.risk_manager, self.ensemble_model),
            "mean_reversion": MeanReversionStrategy(self.risk_manager),
            "momentum": MomentumStrategy(self.risk_manager),
            "stat_arb": StatisticalArbitrageStrategy(self.risk_manager),
        }

        # Equal weighting initially
        self.strategy_weights = {
            name: 1.0 / len(self.strategies) for name in self.strategies
        }

    async def generate_combined_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        """Generate combined signal from all active strategies"""

        strategy_signals = {}

        # Get signals from each strategy
        for strategy_name, strategy in self.strategies.items():
            if strategy.is_active:
                try:
                    signal = await strategy.generate_signal(
                        symbol, price_data, features
                    )
                    strategy_signals[strategy_name] = signal
                except Exception as e:
                    logging.error(f"Error in {strategy_name} signal generation: {e}")

        if not strategy_signals:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                target_price=0.0,
            )

        # Combine signals using weighted voting
        signal_votes = {signal_type: 0.0 for signal_type in SignalType}
        weighted_confidence = 0.0
        weighted_target = 0.0
        total_weight = 0.0

        for strategy_name, signal in strategy_signals.items():
            weight = self.strategy_weights[strategy_name] * signal.confidence
            signal_votes[signal.signal_type] += weight
            weighted_confidence += signal.confidence * weight
            weighted_target += signal.target_price * weight
            total_weight += weight

        # Determine final signal
        if total_weight == 0:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                target_price=0.0,
            )

        # Fix: When the best vote is zero (all HOLD), return HOLD instead of
        # relying on dict insertion order which would always pick BUY.
        max_vote = max(signal_votes.values())
        if max_vote <= 0.0:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                target_price=weighted_target / total_weight,
            )

        final_signal_type = max(signal_votes, key=signal_votes.get)
        final_confidence = weighted_confidence / total_weight
        final_target = weighted_target / total_weight

        # Calculate position size based on combined confidence
        current_price = price_data["close"].iloc[-1]
        position_size = self._calculate_combined_position_size(
            symbol, current_price, final_confidence, strategy_signals
        )

        combined_signal = TradingSignal(
            symbol=symbol,
            signal_type=final_signal_type,
            confidence=final_confidence,
            target_price=final_target,
            position_size=position_size,
            metadata={
                "strategy_signals": {
                    k: v.__dict__ for k, v in strategy_signals.items()
                },
                "signal_votes": {k.value: v for k, v in signal_votes.items()},
                "strategy_weights": self.strategy_weights,
            },
        )

        audit_logger.info(
            "combined_signal_generated",
            symbol=symbol,
            final_signal=final_signal_type.value,
            confidence=final_confidence,
            contributing_strategies=list(strategy_signals.keys()),
        )

        return combined_signal

    def _calculate_combined_position_size(
        self,
        symbol: str,
        price: float,
        confidence: float,
        strategy_signals: dict[str, TradingSignal],
    ) -> float:
        """Calculate position size considering all strategy recommendations"""

        # Average position size from strategies, weighted by confidence
        total_weighted_size = 0.0
        total_weight = 0.0

        for strategy_name, signal in strategy_signals.items():
            if signal.position_size > 0:
                weight = self.strategy_weights[strategy_name] * signal.confidence
                total_weighted_size += signal.position_size * weight
                total_weight += weight

        if total_weight == 0:
            return 0.0

        avg_position_size = total_weighted_size / total_weight

        # Apply overall confidence scaling
        final_size = avg_position_size * confidence

        # Risk management constraint
        max_position = (
            self.settings.trading.max_position_size * 0.5
        )  # Conservative for combined signals
        return min(final_size, max_position)

    def update_strategy_weights(self, performance_data: dict[str, StrategyPerformance]):
        """Update strategy weights based on performance"""
        total_score = 0.0
        strategy_scores = {}

        for strategy_name, performance in performance_data.items():
            if strategy_name in self.strategies:
                # Combined score: Sharpe ratio + win rate - drawdown
                score = (
                    performance.sharpe_ratio * 0.4
                    + performance.win_rate * 0.4
                    - abs(performance.max_drawdown) * 0.2
                )
                strategy_scores[strategy_name] = max(0.1, score)  # Minimum weight
                total_score += strategy_scores[strategy_name]

        # Add minimum weights for untracked strategies
        for strategy_name in self.strategies:
            if strategy_name not in strategy_scores:
                strategy_scores[strategy_name] = 0.1  # Default for new/untracked strategies
                total_score += 0.1

        # Normalize weights to ensure they sum to 1.0
        if total_score > 0:
            for strategy_name in self.strategies:
                self.strategy_weights[strategy_name] = (
                    strategy_scores[strategy_name] / total_score
                )

        audit_logger.info(
            "strategy_weights_updated",
            new_weights=self.strategy_weights,
            performance_scores=strategy_scores,
        )

    def activate_strategy(self, strategy_name: str):
        """Activate a specific strategy"""
        if strategy_name in self.strategies:
            self.strategies[strategy_name].is_active = True
            audit_logger.info("strategy_activated", strategy_name=strategy_name)

    def deactivate_strategy(self, strategy_name: str):
        """Deactivate a specific strategy"""
        if strategy_name in self.strategies:
            self.strategies[strategy_name].is_active = False
            audit_logger.info("strategy_deactivated", strategy_name=strategy_name)

    def get_strategy_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all strategies"""
        status = {}

        for name, strategy in self.strategies.items():
            status[name] = {
                "is_active": strategy.is_active,
                "weight": self.strategy_weights.get(name, 0.0),
                "performance": (
                    strategy.performance_metrics.__dict__
                    if strategy.performance_metrics
                    else None
                ),
                "trade_count": len(strategy.trade_history),
                "required_features": strategy.get_required_features(),
            }

        return status
