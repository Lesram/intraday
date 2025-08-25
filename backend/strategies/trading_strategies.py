"""
Trading Strategies Framework
Implements various algorithmic trading strategies with unified interface
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
from typing import Any

import numpy as np
import pandas as pd

from ..config import get_settings
# Avoid importing heavy ML dependencies (TensorFlow) at module import time unless explicitly enabled.
import os as _os  # local alias to avoid polluting namespace
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

    def __init__(self, name: str, risk_manager: RiskManager):
        self.name = name
        self.risk_manager = risk_manager
        self.settings = get_settings()
        self.positions = {}
        self.trade_history = []
        self.performance_metrics = None
        self.is_active = True

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

    def calculate_position_size(
        self, symbol: str, price: float, confidence: float
    ) -> float:
        """Calculate position size based on confidence and risk"""
        base_position = self.settings.max_position_size * confidence

        # Risk-adjusted position sizing
        portfolio_value = self.risk_manager.get_portfolio_value()
        max_risk_per_trade = portfolio_value * 0.02  # 2% max risk per trade

        position_value = base_position * price
        if position_value > max_risk_per_trade:
            base_position = max_risk_per_trade / price

        return base_position

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

    def __init__(self, risk_manager: RiskManager, ensemble_model: EnsembleModel):
        super().__init__("EnsembleStrategy", risk_manager)
        self.ensemble_model = ensemble_model
        self.confidence_threshold = 0.6

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
            if predicted_return > 0.02:  # 2% threshold
                signal_type = (
                    SignalType.STRONG_BUY if predicted_return > 0.05 else SignalType.BUY
                )
            elif predicted_return < -0.02:
                signal_type = (
                    SignalType.STRONG_SELL
                    if predicted_return < -0.05
                    else SignalType.SELL
                )

        # Calculate position size
        position_size = (
            self.calculate_position_size(
                symbol, current_price, prediction.ensemble_confidence
            )
            if signal_type != SignalType.HOLD
            else 0.0
        )

        # Set stop loss and take profit
        stop_loss = None
        take_profit = None
        if signal_type in [SignalType.BUY, SignalType.STRONG_BUY]:
            stop_loss = current_price * 0.95  # 5% stop loss
            take_profit = prediction.ensemble_prediction * 1.02  # 2% above prediction
        elif signal_type in [SignalType.SELL, SignalType.STRONG_SELL]:
            stop_loss = current_price * 1.05
            take_profit = prediction.ensemble_prediction * 0.98

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

    def __init__(self, risk_manager: RiskManager):
        super().__init__("MeanReversionStrategy", risk_manager)
        self.oversold_threshold = 30
        self.overbought_threshold = 70

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        """Generate mean reversion signal"""

        current_price = price_data["close"].iloc[-1]
        current_rsi = features["rsi"].iloc[-1]
        bb_upper = features["bb_upper"].iloc[-1]
        bb_lower = features["bb_lower"].iloc[-1]
        bb_middle = (bb_upper + bb_lower) / 2

        # Mean reversion logic
        signal_type = SignalType.HOLD
        confidence = 0.5

        # Oversold condition: price near lower band + low RSI
        if current_price < bb_lower * 1.01 and current_rsi < self.oversold_threshold:
            signal_type = SignalType.BUY
            confidence = min(0.9, (self.oversold_threshold - current_rsi) / 20)

        # Overbought condition: price near upper band + high RSI
        elif (
            current_price > bb_upper * 0.99 and current_rsi > self.overbought_threshold
        ):
            signal_type = SignalType.SELL
            confidence = min(0.9, (current_rsi - self.overbought_threshold) / 20)

        position_size = self.calculate_position_size(symbol, current_price, confidence)

        # Set targets
        target_price = bb_middle  # Revert to mean
        stop_loss = None
        take_profit = None

        if signal_type == SignalType.BUY:
            stop_loss = bb_lower * 0.98
            take_profit = bb_middle
        elif signal_type == SignalType.SELL:
            stop_loss = bb_upper * 1.02
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

    def __init__(self, risk_manager: RiskManager):
        super().__init__("MomentumStrategy", risk_manager)

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

        # Bullish momentum: MACD above signal + price above moving averages
        if macd > macd_signal and current_price > sma_20 > sma_50:
            signal_type = SignalType.BUY
            confidence = min(0.85, abs(macd - macd_signal) * 10)

        # Bearish momentum: MACD below signal + price below moving averages
        elif macd < macd_signal and current_price < sma_20 < sma_50:
            signal_type = SignalType.SELL
            confidence = min(0.85, abs(macd - macd_signal) * 10)

        position_size = self.calculate_position_size(symbol, current_price, confidence)

        # Set targets based on momentum strength
        momentum_strength = abs(macd - macd_signal)
        target_multiplier = 1 + (momentum_strength * 0.1)

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
                current_price * 0.97
                if signal_type == SignalType.BUY
                else current_price * 1.03
            ),
            take_profit=target_price,
            position_size=position_size if signal_type != SignalType.HOLD else 0.0,
            metadata={
                "macd": macd,
                "macd_signal": macd_signal,
                "sma_trend": "bullish" if sma_20 > sma_50 else "bearish",
                "strategy": "momentum",
            },
        )

    def get_required_features(self) -> list[str]:
        return ["macd", "macd_signal", "sma_20", "sma_50"]


class RebalancingStrategy(BaseStrategy):
    """Portfolio rebalancing strategy"""

    def __init__(self, risk_manager: RiskManager, target_weights: dict[str, float]):
        super().__init__("RebalancingStrategy", risk_manager)
        self.target_weights = target_weights
        self.rebalance_threshold = 0.05  # 5% deviation triggers rebalance

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        """Generate rebalancing signal"""

        current_price = price_data["close"].iloc[-1]

        # Get current portfolio allocation
        portfolio_value = self.risk_manager.get_portfolio_value()
        current_positions = self.risk_manager.get_positions()

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
    """Statistical arbitrage using correlation and cointegration"""

    def __init__(self, risk_manager: RiskManager, reference_symbol: str = "SPY"):
        super().__init__("StatArbStrategy", risk_manager)
        self.reference_symbol = reference_symbol
        self.lookback_period = 60
        self.entry_threshold = 2.0  # Z-score threshold
        self.exit_threshold = 0.5

    async def generate_signal(
        self, symbol: str, price_data: pd.DataFrame, features: pd.DataFrame
    ) -> TradingSignal:
        """Generate statistical arbitrage signal"""

        if len(price_data) < self.lookback_period:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                target_price=0.0,
            )

        current_price = price_data["close"].iloc[-1]

        # Calculate price ratio and z-score (simplified)
        recent_prices = price_data["close"].tail(self.lookback_period)
        price_mean = recent_prices.mean()
        price_std = recent_prices.std()

        if price_std == 0:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                target_price=current_price,
            )

        z_score = (current_price - price_mean) / price_std

        signal_type = SignalType.HOLD
        confidence = min(0.9, abs(z_score) / 5.0)  # Higher z-score = higher confidence

        if z_score > self.entry_threshold:
            signal_type = SignalType.SELL  # Price is high relative to mean
        elif z_score < -self.entry_threshold:
            signal_type = SignalType.BUY  # Price is low relative to mean

        position_size = self.calculate_position_size(symbol, current_price, confidence)
        target_price = price_mean  # Expect reversion to mean

        return TradingSignal(
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            target_price=target_price,
            stop_loss=(
                current_price * 1.05
                if signal_type == SignalType.SELL
                else current_price * 0.95
            ),
            take_profit=target_price,
            position_size=position_size if signal_type != SignalType.HOLD else 0.0,
            metadata={
                "z_score": z_score,
                "price_mean": price_mean,
                "price_std": price_std,
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
            self.settings.max_position_size * 0.5
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

        # Normalize weights
        if total_score > 0:
            for strategy_name in self.strategies:
                if strategy_name in strategy_scores:
                    self.strategy_weights[strategy_name] = (
                        strategy_scores[strategy_name] / total_score
                    )
                else:
                    self.strategy_weights[strategy_name] = (
                        0.1  # Default for new/untracked strategies
                    )

        audit_logger.info(
            "strategy_weights_updated",
            new_weights=self.strategy_weights,
            performance_scores=strategy_scores,
        )

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
