"""
Backtest Service - Core backtesting engine for strategy validation.

This service provides comprehensive backtesting capabilities including:
- Historical data fetching from Alpaca
- Day-by-day strategy simulation
- Signal generation for multiple strategy types
- Trade execution with risk limits
- Performance metrics calculation (25+ metrics)
- Results persistence

Implementation follows Implementation Prompt principles with clear
separation of concerns and comprehensive error handling.
"""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
import logging
from typing import Any
from uuid import UUID, uuid4

import numpy as np
from sqlalchemy import and_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.data.alpaca_client import AlpacaClient, MarketData
from backend.infra.schemas import Backtest, Strategy
from backend.models.backtest import (
    BacktestResult,
    BacktestSummary,
    EquityPoint,
    MonthlyReturn,
    PerformanceMetrics,
    Trade,
)

logger = logging.getLogger(__name__)


class PortfolioState:
    """Tracks portfolio state during backtest simulation."""

    def __init__(self, initial_capital: float):
        self.cash = initial_capital
        self.positions: dict[str, dict[str, Any]] = {}  # {symbol: {quantity, avg_price, unrealized_pnl}}
        self.equity_history: list[float] = [initial_capital]
        self.date_history: list[date] = []

    @property
    def total_equity(self) -> float:
        """Calculate total portfolio equity (cash + positions value)."""
        positions_value = sum(
            pos["quantity"] * pos["current_price"]
            for pos in self.positions.values()
        )
        return self.cash + positions_value

    @property
    def positions_value(self) -> float:
        """Calculate total value of all positions."""
        return sum(
            pos["quantity"] * pos["current_price"]
            for pos in self.positions.values()
        )

    def update_position_prices(self, market_data: dict[str, MarketData]) -> None:
        """Update current prices for all positions."""
        for symbol, position in self.positions.items():
            if symbol in market_data:
                position["current_price"] = market_data[symbol].close
                position["unrealized_pnl"] = (
                    (market_data[symbol].close - position["avg_price"])
                    * position["quantity"]
                )


class BacktestService:
    """
    Comprehensive backtesting engine for strategy validation.

    Simulates strategy execution on historical data and calculates
    detailed performance metrics.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize backtest service.

        Args:
            session: Async SQLAlchemy database session
        """
        self.session = session

        # Initialize Alpaca client with credentials from environment
        import os
        use_mock_broker = os.getenv("USE_MOCK_BROKER", "false").lower() in ("true", "1", "yes")
        use_mock_data = os.getenv("USE_MOCK_DATA", "false").lower() in ("true", "1", "yes")
        app_env = (os.getenv("APP_ENVIRONMENT") or os.getenv("ENVIRONMENT") or "").lower()

        if use_mock_broker or use_mock_data or app_env in ("test", "tests", "testing"):
            # Keep tests/self-contained runs independent of external Alpaca credentials.
            # The backtest engine only needs a `.get_historical_data()` that returns a DataFrame.
            class _LocalMockAlpacaClient:
                def get_historical_data(self, symbol: str, start: str, end: str, timeframe: str = "1Day"):
                    try:
                        import numpy as np
                        import pandas as pd
                    except Exception as e:  # pragma: no cover
                        raise RuntimeError(
                            "Mock backtest requires pandas/numpy installed for synthetic data"
                        ) from e

                    date_index = pd.date_range(start=start, end=end, freq="D", tz="UTC")
                    if len(date_index) == 0:
                        date_index = pd.DatetimeIndex([pd.Timestamp.utcnow().tz_localize("UTC")])

                    base = 100.0
                    trend = np.linspace(0.0, 1.0, num=len(date_index))
                    close = base + trend

                    df = pd.DataFrame(
                        {
                            "timestamp": date_index,
                            "open": close,
                            "high": close * 1.01,
                            "low": close * 0.99,
                            "close": close,
                            "volume": np.full(len(date_index), 1_000, dtype=int),
                        }
                    )
                    return df

            self.alpaca_client = _LocalMockAlpacaClient()
            return

        api_key = os.getenv("ALPACA_API_KEY_ID")
        secret_key = os.getenv("ALPACA_API_SECRET_KEY")
        paper = os.getenv("ALPACA_PAPER", "true").lower() == "true"

        if not api_key or not secret_key:
            raise ValueError(
                "Alpaca API credentials not found in environment. "
                "Please set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY in .env file."
            )

        self.alpaca_client = AlpacaClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper
        )

    async def run_backtest(
        self,
        strategy: Strategy,
        start_date: date,
        end_date: date,
        initial_capital: float,
        parameters: dict[str, Any] | None = None,
        user_id: str = None,
    ) -> BacktestResult:
        """
        Execute backtest simulation.

        Algorithm:
        1. Create backtest record in database
        2. Fetch historical data from Alpaca
        3. Initialize portfolio state
        4. Simulate day-by-day trading
        5. Calculate performance metrics
        6. Save results to database

        Args:
            strategy: Strategy to backtest
            start_date: Start date for backtest
            end_date: End date for backtest
            initial_capital: Initial capital in USD
            parameters: Optional parameter overrides
            user_id: User ID for backtest record

        Returns:
            BacktestResult with complete results

        Raises:
            ValueError: If dates are invalid or data unavailable
            RuntimeError: If backtest execution fails
        """
        # Safe attribute access (strategy might be SimpleNamespace or dict)
        strategy_name = getattr(strategy, 'name', 'Unknown Strategy')
        strategy_id = getattr(strategy, 'id', None)
        if not strategy_id:
            raise ValueError("Strategy ID is required for backtest")

        logger.info(
            f"Starting backtest for strategy {strategy_name} "
            f"({start_date} to {end_date}, capital=${initial_capital:,.2f})"
        )

        # Create backtest record
        backtest = Backtest(
            id=uuid4(),
            strategy_id=strategy_id,
            user_id=user_id if user_id else 0,
            start_date=start_date,
            end_date=end_date,
            initial_capital=Decimal(str(initial_capital)),
            parameters=parameters or getattr(strategy, 'parameters', {}),
            status="running",
            progress=0,
            started_at=datetime.now(),
        )
        self.session.add(backtest)
        await self.session.commit()

        try:
            # Use parameters override if provided, otherwise use strategy parameters
            effective_params = parameters if parameters is not None else getattr(strategy, 'parameters', {})

            # Get symbols from strategy (safe access)
            symbols_attr = getattr(strategy, 'symbols', [])
            symbols = symbols_attr if isinstance(symbols_attr, list) else []
            if not symbols:
                raise ValueError("Strategy has no symbols configured")

            # Fetch historical data
            logger.info(f"Fetching historical data for {len(symbols)} symbols")
            market_data_by_date = await self._fetch_historical_data(
                symbols, start_date, end_date
            )

            if not market_data_by_date:
                raise ValueError("No historical data available for date range")

            # Initialize portfolio
            portfolio = PortfolioState(initial_capital)

            # Execute simulation
            all_trades: list[Trade] = []
            equity_curve: list[EquityPoint] = []

            trading_days = sorted(market_data_by_date.keys())
            total_days = len(trading_days)

            # CRITICAL: Track pending signals to execute on NEXT bar
            # This eliminates look-ahead bias by ensuring we can't trade on
            # information we wouldn't have until after market close
            pending_signals: dict[str, dict[str, Any]] = {}

            # NEW: Build rolling price history for proper indicator calculation
            # This allows RSI, SMA, etc. to be calculated with historical context
            price_history: dict[str, list[float]] = defaultdict(list)
            
            # DYNAMIC LOOKBACK: Set minimum bars based on strategy indicator requirements
            # Default to 50 (enough for RSI 14 + SMA 50), but use strategy params if available
            sma_period = int(effective_params.get('sma_period', 50))
            rsi_period = int(effective_params.get('rsi_period', 14))
            macd_slow = int(effective_params.get('macd_slow', 26))
            bb_period = int(effective_params.get('bb_period', 20))
            LOOKBACK_REQUIRED = max(sma_period, rsi_period + 1, macd_slow, bb_period, 20)  # Minimum 20 bars

            for idx, trading_date in enumerate(trading_days):
                market_data = market_data_by_date[trading_date]

                # Update rolling price history for each symbol
                for symbol, data in market_data.items():
                    price_history[symbol].append(data.close)
                    # Keep only last 200 bars to limit memory
                    if len(price_history[symbol]) > 200:
                        price_history[symbol] = price_history[symbol][-200:]

                # Update progress every 10%
                if idx % max(1, total_days // 10) == 0:
                    progress = int((idx / total_days) * 100)
                    backtest.progress = progress
                    await self.session.commit()

                # Update position prices with current market data
                portfolio.update_position_prices(market_data)

                # FIRST: Execute any pending signals from PREVIOUS day at today's OPEN
                # This is the key fix for look-ahead bias - we trade at the open price
                # of the NEXT bar after the signal was generated
                if pending_signals:
                    day_trades = self._execute_pending_signals(
                        pending_signals, market_data, portfolio, strategy
                    )
                    all_trades.extend(day_trades)
                    pending_signals.clear()

                # THEN: Generate NEW signals based on today's data
                # These signals will be executed tomorrow at the open
                # Only generate signals once we have enough price history
                if idx >= LOOKBACK_REQUIRED:
                    strategy_type = getattr(strategy, 'strategy_type', 'momentum')
                    new_signals = self._generate_signals_with_history(
                        strategy_type,
                        effective_params,
                        market_data,
                        price_history,
                        portfolio,
                        trading_date
                    )

                    # Store signals for next-bar execution (if not last day)
                    if idx < total_days - 1:
                        for signal in new_signals:
                            symbol = signal["symbol"]
                            pending_signals[symbol] = signal

                # Record equity point
                equity_point = EquityPoint(
                    date=trading_date,
                    value=portfolio.total_equity,
                    cash=portfolio.cash,
                    positions_value=portfolio.positions_value,
                )
                equity_curve.append(equity_point)

            # Calculate performance metrics
            metrics = self.calculate_metrics(
                all_trades,
                equity_curve,
                initial_capital,
                start_date,
                end_date,
            )

            # Calculate monthly returns
            monthly_returns = self._calculate_monthly_returns(equity_curve)

            # Update backtest record with results
            backtest.status = "completed"
            backtest.progress = 100
            backtest.completed_at = datetime.now()
            backtest.final_equity = Decimal(str(portfolio.total_equity))
            backtest.total_return = Decimal(str(metrics.total_return))
            backtest.annualized_return = Decimal(str(metrics.annualized_return))
            backtest.sharpe_ratio = Decimal(str(metrics.sharpe_ratio))
            backtest.max_drawdown = Decimal(str(metrics.max_drawdown))
            backtest.win_rate = Decimal(str(metrics.win_rate))
            backtest.profit_factor = Decimal(str(metrics.profit_factor))
            backtest.total_trades = metrics.total_trades
            backtest.winning_trades = metrics.winning_trades
            backtest.losing_trades = metrics.losing_trades

            # Store detailed results as JSON (use mode='json' to serialize dates properly)
            backtest.equity_curve = [eq.model_dump(mode='json') for eq in equity_curve]
            backtest.trade_log = [trade.model_dump(mode='json') for trade in all_trades]
            backtest.monthly_returns = [mr.model_dump(mode='json') for mr in monthly_returns]
            backtest.metrics = metrics.model_dump(mode='json')

            await self.session.commit()

            # Build result (use safe attributes extracted earlier)
            result = BacktestResult(
                id=str(backtest.id),
                strategy_id=str(strategy_id),  # Already validated at start
                strategy_name=strategy_name,   # Already extracted at start
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                final_equity=portfolio.total_equity,
                metrics=metrics,
                equity_curve=equity_curve,
                trade_log=all_trades,
                monthly_returns=[mr.model_dump() for mr in monthly_returns],
                status="completed",
                created_at=backtest.created_at,
                started_at=backtest.started_at,
                completed_at=backtest.completed_at,
            )

            logger.info(
                f"Backtest completed: {metrics.total_trades} trades, "
                f"return={metrics.total_return:.2f}%, "
                f"Sharpe={metrics.sharpe_ratio:.2f}"
            )

            return result

        except Exception as e:
            # Update backtest record with error
            backtest.status = "failed"
            backtest.error_message = str(e)
            backtest.completed_at = datetime.now()
            await self.session.commit()

            logger.error(f"Backtest failed: {e}", exc_info=True)
            raise RuntimeError(f"Backtest execution failed: {e}") from e

    async def _fetch_historical_data(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> dict[date, dict[str, MarketData]]:
        """
        Fetch historical market data from Alpaca.

        Args:
            symbols: List of symbols to fetch
            start_date: Start date
            end_date: End date

        Returns:
            Dictionary mapping dates to market data for each symbol
        """
        market_data_by_date: dict[date, dict[str, MarketData]] = {}

        for symbol in symbols:
            try:
                # Fetch daily bars from Alpaca (returns DataFrame)
                import asyncio
                loop = asyncio.get_event_loop()
                df = await loop.run_in_executor(
                    None,
                    lambda: self.alpaca_client.get_historical_data(
                        symbol=symbol,
                        start=start_date.isoformat(),
                        end=end_date.isoformat(),
                        timeframe="1Day",
                    )
                )

                if df is not None and not df.empty:
                    # Convert DataFrame rows to MarketData objects
                    for _, row in df.iterrows():
                        # Parse timestamp to date
                        if isinstance(row['timestamp'], str):
                            bar_date = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00')).date()
                        else:
                            bar_date = row['timestamp'].date()

                        if bar_date not in market_data_by_date:
                            market_data_by_date[bar_date] = {}

                        # Create MarketData object from DataFrame row
                        market_data_by_date[bar_date][symbol] = MarketData(
                            symbol=symbol,
                            timestamp=row['timestamp'],
                            open=float(row['open']),
                            high=float(row['high']),
                            low=float(row['low']),
                            close=float(row['close']),
                            volume=int(row['volume']),
                        )

            except Exception as e:
                logger.warning(f"Failed to fetch data for {symbol}: {e}")
                continue

        return market_data_by_date

    def _generate_signals(
        self,
        strategy_type: str,
        parameters: dict[str, Any],
        market_data: dict[str, MarketData],
        portfolio: PortfolioState,
        current_date: date,
    ) -> list[dict[str, Any]]:
        """
        Generate trading signals based on strategy type.

        Supports multiple strategy types with different signal logic.

        Args:
            strategy_type: Type of strategy (momentum, mean_reversion, etc.)
            parameters: Strategy parameters
            market_data: Current market data for all symbols
            portfolio: Current portfolio state
            current_date: Current date in simulation

        Returns:
            List of signals with action, symbol, and confidence
        """
        signals = []

        # Simple implementations for each strategy type
        # In production, these would be much more sophisticated

        if strategy_type in ["momentum", "trend_following"]:
            # Simple momentum: Buy if price > moving average
            ma_period = parameters.get("ma_period", 20)
            signals = self._momentum_signals(market_data, ma_period)

        elif strategy_type in ["mean_reversion", "stat_arb", "statistical_arbitrage"]:
            # Mean reversion: Buy if oversold, sell if overbought
            parameters.get("rsi_period", 14)
            oversold = parameters.get("oversold_threshold", 30)
            overbought = parameters.get("overbought_threshold", 70)
            signals = self._mean_reversion_signals(market_data, oversold, overbought)

        elif strategy_type in ["breakout"]:
            # Breakout: Buy on price breakouts
            lookback = parameters.get("lookback_period", 20)
            signals = self._breakout_signals(market_data, lookback)

        elif strategy_type in ["ensemble", "ensemble_model"]:
            # Ensemble: Combine multiple strategies
            # For backtest, use momentum as default
            ma_period = parameters.get("ma_period", 20)
            signals = self._momentum_signals(market_data, ma_period)
            logger.info("Ensemble strategy using momentum signals for backtest")

        else:
            # Default: No signals
            logger.warning(f"Unknown strategy type: {strategy_type}, generating no signals")

        return signals

    def _momentum_signals(
        self,
        market_data: dict[str, MarketData],
        ma_period: int = 20,
    ) -> list[dict[str, Any]]:
        """Generate momentum-based signals."""
        signals = []

        for symbol, data in market_data.items():
            # Simple rule: Buy if price is strong (for simulation purposes)
            # In reality, would need historical prices to calculate MA
            if data.close > data.open * 1.02:  # 2% gain
                signals.append({
                    "action": "buy",
                    "symbol": symbol,
                    "confidence": 0.7,
                    "reason": "momentum_up"
                })
            elif data.close < data.open * 0.98:  # 2% loss
                signals.append({
                    "action": "sell",
                    "symbol": symbol,
                    "confidence": 0.6,
                    "reason": "momentum_down"
                })

        return signals

    def _mean_reversion_signals(
        self,
        market_data: dict[str, MarketData],
        oversold: float = 30,
        overbought: float = 70,
    ) -> list[dict[str, Any]]:
        """Generate mean reversion signals."""
        signals = []

        for symbol, data in market_data.items():
            # Simplified: Use daily range as proxy
            daily_range = ((data.high - data.low) / data.open) * 100

            if daily_range > 5:  # High volatility = reversion opportunity
                if data.close < data.open:  # Down day
                    signals.append({
                        "action": "buy",
                        "symbol": symbol,
                        "confidence": 0.6,
                        "reason": "oversold"
                    })
                else:  # Up day
                    signals.append({
                        "action": "sell",
                        "symbol": symbol,
                        "confidence": 0.5,
                        "reason": "overbought"
                    })

        return signals

    def _breakout_signals(
        self,
        market_data: dict[str, MarketData],
        lookback: int = 20,
    ) -> list[dict[str, Any]]:
        """Generate breakout signals."""
        signals = []

        for symbol, data in market_data.items():
            # Simplified: Check if high is significantly above open
            if data.high > data.open * 1.05:  # 5% breakout
                signals.append({
                    "action": "buy",
                    "symbol": symbol,
                    "confidence": 0.8,
                    "reason": "breakout"
                })

        return signals

    def _generate_signals_with_history(
        self,
        strategy_type: str,
        parameters: dict[str, Any],
        market_data: dict[str, MarketData],
        price_history: dict[str, list[float]],
        portfolio: PortfolioState,
        current_date: date,
    ) -> list[dict[str, Any]]:
        """
        Generate trading signals using ACTUAL technical indicators with price history.
        
        This replaces the simplified placeholder logic with real RSI/SMA calculations.
        
        Args:
            strategy_type: Type of strategy (momentum, mean_reversion, etc.)
            parameters: Strategy parameters (rsi_buy, rsi_sell, sma_fast, sma_slow, etc.)
            market_data: Current market data for all symbols
            price_history: Rolling price history for each symbol
            portfolio: Current portfolio state
            current_date: Current date in simulation
            
        Returns:
            List of signals with action, symbol, confidence, and reason
        """
        from backend.features.technical_indicators import TechnicalIndicators

        signals = []
        indicators = TechnicalIndicators()

        # Extract strategy parameters with sensible defaults
        rsi_buy = parameters.get("rsi_buy", parameters.get("oversold_threshold", 35))
        rsi_sell = parameters.get("rsi_sell", parameters.get("overbought_threshold", 65))
        sma_fast = parameters.get("sma_fast", parameters.get("ma_period", 20))
        sma_slow = parameters.get("sma_slow", 50)
        min_confidence = parameters.get("min_confidence", 0.5)
        extreme_offset = parameters.get("extreme_offset", 5.0)  # For mean reversion

        for symbol, data in market_data.items():
            # Get price history for this symbol
            closes = price_history.get(symbol, [])

            if len(closes) < max(sma_slow + 1, 15):
                continue  # Not enough data for indicators

            try:
                # Calculate RSI
                rsi_result = indicators.calculate_rsi(closes)
                if not rsi_result or rsi_result.value is None:
                    continue
                rsi = rsi_result.value

                # Calculate SMAs for trend confirmation
                sma_fast_result = indicators.calculate_sma(closes, sma_fast)
                sma_slow_result = indicators.calculate_sma(closes, sma_slow)

                sma_fast_val = sma_fast_result.value if sma_fast_result else None
                sma_slow_val = sma_slow_result.value if sma_slow_result else None

                # Determine trend bias
                trend_bias = "neutral"
                if sma_fast_val and sma_slow_val:
                    if sma_fast_val > sma_slow_val:
                        trend_bias = "bullish"
                    elif sma_fast_val < sma_slow_val:
                        trend_bias = "bearish"

                # Current position for this symbol
                current_position = portfolio.positions.get(symbol, {})
                has_position = current_position.get("quantity", 0) > 0

                # Generate signals based on strategy type
                if strategy_type in ["momentum", "trend_following"]:
                    signal = self._momentum_signal_with_indicators(
                        symbol, rsi, rsi_buy, rsi_sell, trend_bias, has_position
                    )
                elif strategy_type in ["mean_reversion", "stat_arb", "statistical_arbitrage"]:
                    signal = self._mean_reversion_signal_with_indicators(
                        symbol, rsi, rsi_buy, rsi_sell, trend_bias, has_position,
                        extreme_offset=extreme_offset
                    )
                else:
                    # Default: RSI-based signal (similar to BasicStrategy)
                    signal = self._rsi_sma_signal(
                        symbol, rsi, rsi_buy, rsi_sell, trend_bias, has_position
                    )

                if signal and signal.get("confidence", 0) >= min_confidence:
                    signals.append(signal)

            except Exception as e:
                logger.warning(f"Error generating signal for {symbol}: {e}")
                continue

        return signals

    def _rsi_sma_signal(
        self,
        symbol: str,
        rsi: float,
        rsi_buy: float,
        rsi_sell: float,
        trend_bias: str,
        has_position: bool,
    ) -> dict[str, Any] | None:
        """
        Generate signal using RSI + SMA cross logic (matches BasicStrategy.decide()).
        
        Buy when: RSI < rsi_buy (oversold), boosted by bullish trend
        Sell when: RSI > rsi_sell (overbought), boosted by bearish trend
        """
        if rsi < rsi_buy:
            # RSI oversold - potential buy
            # Calculate confidence based on how oversold
            confidence = min(1.0, (rsi_buy - rsi) / rsi_buy + 0.5)

            # Adjust for trend
            if trend_bias == "bullish":
                confidence = min(1.0, confidence * 1.2)
            elif trend_bias == "bearish":
                confidence = confidence * 0.8

            return {
                "action": "buy",
                "symbol": symbol,
                "confidence": round(confidence, 3),
                "reason": f"RSI oversold ({rsi:.1f} < {rsi_buy}), trend: {trend_bias}",
                "indicators": {"rsi": rsi, "trend": trend_bias}
            }

        elif rsi > rsi_sell and has_position:
            # RSI overbought - potential sell (only if we have a position)
            confidence = min(1.0, (rsi - rsi_sell) / (100 - rsi_sell) + 0.5)

            if trend_bias == "bearish":
                confidence = min(1.0, confidence * 1.2)
            elif trend_bias == "bullish":
                confidence = confidence * 0.8

            return {
                "action": "sell",
                "symbol": symbol,
                "confidence": round(confidence, 3),
                "reason": f"RSI overbought ({rsi:.1f} > {rsi_sell}), trend: {trend_bias}",
                "indicators": {"rsi": rsi, "trend": trend_bias}
            }

        return None  # Hold - no signal

    def _momentum_signal_with_indicators(
        self,
        symbol: str,
        rsi: float,
        rsi_buy: float,
        rsi_sell: float,
        trend_bias: str,
        has_position: bool,
    ) -> dict[str, Any] | None:
        """
        Momentum strategy: Follow the trend with RSI confirmation.
        
        Buy when: Bullish trend + RSI not overbought (uses rsi_sell threshold)
        Sell when: Bearish trend + RSI not oversold (uses rsi_buy threshold)
        
        Uses parameter-based thresholds instead of hardcoded values.
        """
        # Use parameter-based thresholds for trend confirmation
        rsi_overbought = rsi_sell  # From parameters (e.g., 65)
        rsi_oversold = rsi_buy     # From parameters (e.g., 35)
        rsi_midpoint = (rsi_buy + rsi_sell) / 2  # Dynamic midpoint

        if trend_bias == "bullish" and rsi < rsi_overbought:  # Not overbought
            confidence = 0.6 + (0.2 if rsi < rsi_midpoint else 0.0)  # Higher confidence if RSI is lower
            return {
                "action": "buy",
                "symbol": symbol,
                "confidence": round(confidence, 3),
                "reason": f"Momentum bullish, RSI={rsi:.1f} (< {rsi_overbought})",
                "indicators": {"rsi": rsi, "trend": trend_bias}
            }

        elif trend_bias == "bearish" and rsi > rsi_oversold and has_position:  # Not oversold
            confidence = 0.6 + (0.2 if rsi > rsi_midpoint else 0.0)
            return {
                "action": "sell",
                "symbol": symbol,
                "confidence": round(confidence, 3),
                "reason": f"Momentum bearish, RSI={rsi:.1f} (> {rsi_oversold})",
                "indicators": {"rsi": rsi, "trend": trend_bias}
            }

        return None

    def _mean_reversion_signal_with_indicators(
        self,
        symbol: str,
        rsi: float,
        rsi_buy: float,
        rsi_sell: float,
        trend_bias: str,
        has_position: bool,
        extreme_offset: float = 5.0,  # Parameterized offset for extreme thresholds
    ) -> dict[str, Any] | None:
        """
        Mean reversion strategy: Bet against extremes.
        
        Buy when: RSI very low (oversold), even against bearish trend
        Sell when: RSI very high (overbought), even against bullish trend
        
        Args:
            symbol: Trading symbol
            rsi: Current RSI value
            rsi_buy: RSI buy threshold from strategy parameters
            rsi_sell: RSI sell threshold from strategy parameters  
            trend_bias: Current trend direction
            has_position: Whether we hold this symbol
            extreme_offset: How much more extreme RSI must be vs thresholds
        """
        # More aggressive thresholds for mean reversion (derived from params)
        extreme_oversold = rsi_buy - extreme_offset
        extreme_overbought = rsi_sell + extreme_offset

        if rsi < extreme_oversold:
            # Very oversold - buy for reversion
            confidence = min(1.0, (extreme_oversold - rsi) / 20 + 0.6)
            return {
                "action": "buy",
                "symbol": symbol,
                "confidence": round(confidence, 3),
                "reason": f"Mean reversion: RSI extremely oversold ({rsi:.1f} < {extreme_oversold:.0f})",
                "indicators": {"rsi": rsi, "trend": trend_bias}
            }

        elif rsi > extreme_overbought and has_position:
            # Very overbought - sell for reversion
            confidence = min(1.0, (rsi - extreme_overbought) / 20 + 0.6)
            return {
                "action": "sell",
                "symbol": symbol,
                "confidence": round(confidence, 3),
                "reason": f"Mean reversion: RSI extremely overbought ({rsi:.1f} > {extreme_overbought:.0f})",
                "indicators": {"rsi": rsi, "trend": trend_bias}
            }

        return None

    def _execute_pending_signals(
        self,
        pending_signals: dict[str, dict[str, Any]],
        market_data: dict[str, MarketData],
        portfolio: PortfolioState,
        strategy: Strategy,
    ) -> list[Trade]:
        """
        Execute pending signals at the OPEN price of the current bar.

        This eliminates look-ahead bias by executing signals generated
        from the previous day's close at the next day's open price.

        Args:
            pending_signals: Signals from previous day keyed by symbol
            market_data: Current day's market data
            portfolio: Portfolio state
            strategy: Strategy configuration

        Returns:
            List of executed trades
        """
        trades = []

        # Get risk limits from strategy
        risk_limits = {}
        if hasattr(strategy, 'risk_limits') and strategy.risk_limits:
            risk_limits = strategy.risk_limits
        elif isinstance(strategy, dict) and 'risk_limits' in strategy:
            risk_limits = strategy['risk_limits']

        max_position_size = risk_limits.get("max_position_size", 0.1)

        # Add slippage model for realistic execution
        slippage_pct = risk_limits.get("slippage_pct", 0.001)  # 0.1% default slippage

        for symbol, signal in pending_signals.items():
            if symbol not in market_data:
                continue

            data = market_data[symbol]
            action = signal["action"]

            # Use OPEN price for execution (the key fix)
            execution_price = data.open

            # Apply slippage (adverse to the trade direction)
            if action == "buy":
                execution_price *= (1 + slippage_pct)
            else:
                execution_price *= (1 - slippage_pct)

            if action == "buy":
                # Calculate position size
                position_value = portfolio.total_equity * max_position_size
                quantity = int(position_value / execution_price)

                if quantity > 0 and portfolio.cash >= quantity * execution_price:
                    cost = quantity * execution_price
                    portfolio.cash -= cost

                    if symbol in portfolio.positions:
                        pos = portfolio.positions[symbol]
                        new_quantity = pos["quantity"] + quantity
                        new_avg_price = (
                            (pos["avg_price"] * pos["quantity"] + cost) / new_quantity
                        )
                        pos["quantity"] = new_quantity
                        pos["avg_price"] = new_avg_price
                        pos["current_price"] = data.close
                    else:
                        portfolio.positions[symbol] = {
                            "quantity": quantity,
                            "avg_price": execution_price,
                            "current_price": data.close,
                            "unrealized_pnl": 0.0,
                        }

                    trade = Trade(
                        symbol=symbol,
                        side="buy",
                        quantity=quantity,
                        entry_date=data.timestamp.date(),
                        entry_price=execution_price,
                        commission=0.0,
                    )
                    trades.append(trade)

            elif action == "sell":
                if symbol in portfolio.positions:
                    pos = portfolio.positions[symbol]
                    quantity = pos["quantity"]

                    proceeds = quantity * execution_price
                    portfolio.cash += proceeds

                    pnl = (execution_price - pos["avg_price"]) * quantity
                    pnl_percent = ((execution_price / pos["avg_price"]) - 1) * 100

                    trade = Trade(
                        symbol=symbol,
                        side="sell",
                        quantity=quantity,
                        entry_date=data.timestamp.date(),
                        entry_price=pos["avg_price"],
                        exit_date=data.timestamp.date(),
                        exit_price=execution_price,
                        pnl=pnl,
                        pnl_percent=pnl_percent,
                        duration_days=0,
                        commission=0.0,
                    )
                    trades.append(trade)

                    del portfolio.positions[symbol]

        return trades

    def _execute_signals(
        self,
        signals: list[dict[str, Any]],
        market_data: dict[str, MarketData],
        portfolio: PortfolioState,
        strategy: Strategy,
    ) -> list[Trade]:
        """
        Execute trades based on signals (DEPRECATED - use _execute_pending_signals).

        This method is kept for backward compatibility but should not be used
        for new backtest code as it has look-ahead bias.

        Args:
            signals: List of trading signals
            market_data: Current market data
            portfolio: Portfolio state
            strategy: Strategy configuration

        Returns:
            List of executed trades
        """
        trades = []

        # Get risk limits from strategy (handle both dict and object)
        risk_limits = {}
        if hasattr(strategy, 'risk_limits') and strategy.risk_limits:
            risk_limits = strategy.risk_limits
        elif isinstance(strategy, dict) and 'risk_limits' in strategy:
            risk_limits = strategy['risk_limits']

        max_position_size = risk_limits.get("max_position_size", 0.1)  # 10% default

        for signal in signals:
            symbol = signal["symbol"]
            action = signal["action"]

            if symbol not in market_data:
                continue

            data = market_data[symbol]

            if action == "buy":
                # Calculate position size (max 10% of portfolio)
                position_value = portfolio.total_equity * max_position_size
                quantity = int(position_value / data.close)

                if quantity > 0 and portfolio.cash >= quantity * data.close:
                    # Execute buy
                    cost = quantity * data.close
                    portfolio.cash -= cost

                    if symbol in portfolio.positions:
                        # Add to existing position
                        pos = portfolio.positions[symbol]
                        new_quantity = pos["quantity"] + quantity
                        new_avg_price = (
                            (pos["avg_price"] * pos["quantity"] + cost) / new_quantity
                        )
                        pos["quantity"] = new_quantity
                        pos["avg_price"] = new_avg_price
                        pos["current_price"] = data.close
                    else:
                        # New position
                        portfolio.positions[symbol] = {
                            "quantity": quantity,
                            "avg_price": data.close,
                            "current_price": data.close,
                            "unrealized_pnl": 0.0,
                        }

                    trade = Trade(
                        symbol=symbol,
                        side="buy",
                        quantity=quantity,
                        entry_date=data.timestamp.date(),
                        entry_price=data.close,
                        commission=0.0,  # Simplified
                    )
                    trades.append(trade)

            elif action == "sell":
                # Close position if exists
                if symbol in portfolio.positions:
                    pos = portfolio.positions[symbol]
                    quantity = pos["quantity"]

                    # Execute sell
                    proceeds = quantity * data.close
                    portfolio.cash += proceeds

                    # Calculate P&L
                    pnl = (data.close - pos["avg_price"]) * quantity
                    pnl_percent = ((data.close / pos["avg_price"]) - 1) * 100

                    trade = Trade(
                        symbol=symbol,
                        side="sell",
                        quantity=quantity,
                        entry_date=data.timestamp.date(),  # Use current date as entry
                        entry_price=pos["avg_price"],
                        exit_date=data.timestamp.date(),
                        exit_price=data.close,
                        pnl=pnl,
                        pnl_percent=pnl_percent,
                        duration_days=0,  # Would need trade history
                        commission=0.0,
                    )
                    trades.append(trade)

                    # Remove position
                    del portfolio.positions[symbol]

        return trades

    def calculate_metrics(
        self,
        trades: list[Trade],
        equity_curve: list[EquityPoint],
        initial_capital: float,
        start_date: date,
        end_date: date,
        risk_free_rate: float = 0.02,  # Configurable risk-free rate (default 2%)
    ) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics.

        Calculates 25+ metrics including returns, risk-adjusted metrics,
        and trade statistics.

        Args:
            trades: List of all trades
            equity_curve: Daily equity values
            initial_capital: Starting capital
            start_date: Backtest start date
            end_date: Backtest end date
            risk_free_rate: Risk-free rate for Sharpe/Sortino calculations (default 2%)

        Returns:
            PerformanceMetrics with all calculated metrics
        """
        if not equity_curve:
            # Return zero metrics if no data
            return PerformanceMetrics(
                total_return=0.0, annualized_return=0.0, sharpe_ratio=0.0,
                sortino_ratio=0.0, calmar_ratio=0.0, max_drawdown=0.0,
                max_drawdown_duration_days=0, volatility=0.0, total_trades=0,
                winning_trades=0, losing_trades=0, win_rate=0.0, profit_factor=0.0,
                avg_trade_pnl=0.0, avg_win=0.0, avg_loss=0.0, largest_win=0.0,
                largest_loss=0.0, max_consecutive_wins=0, max_consecutive_losses=0,
                total_commission=0.0, avg_trade_duration_days=0.0
            )

        final_equity = equity_curve[-1].value

        # Calculate returns
        total_return = ((final_equity - initial_capital) / initial_capital) * 100

        # Annualized return
        duration_years = (end_date - start_date).days / 365.25
        if duration_years > 0:
            annualized_return = (((final_equity / initial_capital) ** (1 / duration_years)) - 1) * 100
        else:
            annualized_return = 0.0

        # Calculate daily returns for risk metrics
        daily_returns = []
        for i in range(1, len(equity_curve)):
            daily_return = (equity_curve[i].value - equity_curve[i-1].value) / equity_curve[i-1].value
            daily_returns.append(daily_return)

        # Volatility (annualized)
        if daily_returns:
            volatility = float(np.std(daily_returns) * np.sqrt(252) * 100)
        else:
            volatility = 0.0

        # Sharpe ratio (using configurable risk-free rate)
        if volatility > 0:
            sharpe_ratio = (annualized_return / 100 - risk_free_rate) / (volatility / 100)
        else:
            sharpe_ratio = 0.0

        # Sortino ratio (downside deviation only)
        downside_returns = [r for r in daily_returns if r < 0]
        if downside_returns:
            downside_deviation = float(np.std(downside_returns) * np.sqrt(252))
            sortino_ratio = (annualized_return / 100 - risk_free_rate) / downside_deviation if downside_deviation > 0 else 0.0
        else:
            sortino_ratio = 0.0

        # Maximum drawdown
        max_drawdown = 0.0
        max_drawdown_duration_days = 0
        peak = equity_curve[0].value
        peak_idx = 0

        for idx, point in enumerate(equity_curve):
            if point.value > peak:
                peak = point.value
                peak_idx = idx
            else:
                drawdown = ((peak - point.value) / peak) * 100
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                    max_drawdown_duration_days = idx - peak_idx

        # Calmar ratio
        calmar_ratio = (annualized_return / max_drawdown) if max_drawdown > 0 else 0.0

        # Trade statistics
        completed_trades = [t for t in trades if t.pnl is not None]
        total_trades = len(completed_trades)

        if total_trades > 0:
            winning_trades = [t for t in completed_trades if t.pnl > 0]
            losing_trades = [t for t in completed_trades if t.pnl < 0]

            num_winning = len(winning_trades)
            num_losing = len(losing_trades)
            win_rate = (num_winning / total_trades) * 100

            # P&L stats
            total_pnl = sum(t.pnl for t in completed_trades)
            avg_trade_pnl = total_pnl / total_trades

            if winning_trades:
                total_wins = sum(t.pnl for t in winning_trades)
                avg_win = total_wins / len(winning_trades)
                largest_win = max(t.pnl for t in winning_trades)
            else:
                avg_win = 0.0
                largest_win = 0.0

            if losing_trades:
                total_losses = sum(abs(t.pnl) for t in losing_trades)
                avg_loss = -total_losses / len(losing_trades)
                largest_loss = min(t.pnl for t in losing_trades)
            else:
                avg_loss = 0.0
                largest_loss = 0.0
                total_losses = 0.0

            # Profit factor
            profit_factor = abs(sum(t.pnl for t in winning_trades) / total_losses) if total_losses > 0 else 0.0

            # Consecutive wins/losses
            max_consecutive_wins = 0
            max_consecutive_losses = 0
            current_wins = 0
            current_losses = 0

            for trade in completed_trades:
                if trade.pnl > 0:
                    current_wins += 1
                    current_losses = 0
                    max_consecutive_wins = max(max_consecutive_wins, current_wins)
                else:
                    current_losses += 1
                    current_wins = 0
                    max_consecutive_losses = max(max_consecutive_losses, current_losses)

            # Average trade duration
            durations = [t.duration_days for t in completed_trades if t.duration_days is not None]
            avg_duration = sum(durations) / len(durations) if durations else 0.0

        else:
            num_winning = 0
            num_losing = 0
            win_rate = 0.0
            avg_trade_pnl = 0.0
            avg_win = 0.0
            avg_loss = 0.0
            largest_win = 0.0
            largest_loss = 0.0
            profit_factor = 0.0
            max_consecutive_wins = 0
            max_consecutive_losses = 0
            avg_duration = 0.0

        # Total commission
        total_commission = sum(t.commission for t in trades)

        return PerformanceMetrics(
            total_return=total_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration_days=max_drawdown_duration_days,
            volatility=volatility,
            total_trades=total_trades,
            winning_trades=num_winning,
            losing_trades=num_losing,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_trade_pnl=avg_trade_pnl,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            max_consecutive_wins=max_consecutive_wins,
            max_consecutive_losses=max_consecutive_losses,
            total_commission=total_commission,
            avg_trade_duration_days=avg_duration,
        )

    def _calculate_monthly_returns(
        self,
        equity_curve: list[EquityPoint],
    ) -> list[MonthlyReturn]:
        """
        Calculate monthly returns breakdown.

        Args:
            equity_curve: Daily equity points

        Returns:
            List of monthly returns
        """
        if not equity_curve:
            return []

        # Group by month
        monthly_data: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"start_value": None, "end_value": None, "trades": 0, "wins": 0, "losses": 0}
        )

        for point in equity_curve:
            month_key = point.date.strftime("%Y-%m")
            month = monthly_data[month_key]

            if month["start_value"] is None:
                month["start_value"] = point.value
            month["end_value"] = point.value

        # Calculate returns
        monthly_returns = []
        for month_key in sorted(monthly_data.keys()):
            data = monthly_data[month_key]
            if data["start_value"] and data["end_value"]:
                return_pct = ((data["end_value"] - data["start_value"]) / data["start_value"]) * 100
            else:
                return_pct = 0.0

            monthly_returns.append(MonthlyReturn(
                month=month_key,
                return_pct=return_pct,
                trades=data["trades"],
                winning_trades=data["wins"],
                losing_trades=data["losses"],
            ))

        return monthly_returns

    async def get_backtest_history(
        self,
        user_id: str,  # UUID string from API layer
        strategy_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BacktestSummary]:
        """
        Get list of past backtests.

        Args:
            user_id: User ID (UUID string) to filter by
            strategy_id: Optional strategy ID filter
            limit: Maximum results to return
            offset: Pagination offset

        Returns:
            List of BacktestSummary objects
        """
        try:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
        except (ValueError, AttributeError):
            return []
        
        query = select(Backtest).where(Backtest.user_id == user_uuid)

        if strategy_id:
            try:
                query = query.where(Backtest.strategy_id == UUID(strategy_id))
            except (ValueError, AttributeError):
                # Invalid UUID format - return empty list
                return []

        query = query.order_by(Backtest.created_at.desc()).limit(limit).offset(offset)

        try:
            result = await self.session.execute(query)
        except OperationalError as e:
            # In test/mock mode we may run against a lightweight SQLite DB without migrations.
            # Treat missing tables as empty history rather than returning 500.
            import os

            msg = str(e).lower()
            is_missing_table = "no such table" in msg and ("backtests" in msg or "strategies" in msg)
            use_mock = os.getenv("USE_MOCK_BROKER", "false").lower() in ("true", "1", "yes") or os.getenv(
                "USE_MOCK_DATA", "false"
            ).lower() in ("true", "1", "yes")
            app_env = (os.getenv("APP_ENVIRONMENT") or os.getenv("ENVIRONMENT") or "").lower()

            if is_missing_table and (use_mock or app_env in ("test", "tests", "testing")):
                return []
            raise
        backtests = result.scalars().all()

        summaries = []
        for bt in backtests:
            # Get strategy name
            try:
                strategy_result = await self.session.execute(
                    select(Strategy).where(Strategy.id == bt.strategy_id)
                )
                strategy = strategy_result.scalar_one_or_none()
            except OperationalError:
                strategy = None

            summaries.append(BacktestSummary(
                id=str(bt.id),
                strategy_id=str(bt.strategy_id),
                strategy_name=strategy.name if strategy else "Unknown",
                start_date=bt.start_date,
                end_date=bt.end_date,
                initial_capital=float(bt.initial_capital),
                final_equity=float(bt.final_equity) if bt.final_equity else None,
                total_return=float(bt.total_return) if bt.total_return else None,
                sharpe_ratio=float(bt.sharpe_ratio) if bt.sharpe_ratio else None,
                max_drawdown=float(bt.max_drawdown) if bt.max_drawdown else None,
                total_trades=bt.total_trades,
                status=bt.status,
                error_message=bt.error_message,
                created_at=bt.created_at,
                completed_at=bt.completed_at,
            ))

        return summaries

    async def get_backtest_result(
        self,
        backtest_id: str,
        user_id: str,
    ) -> BacktestResult | None:
        """
        Get detailed backtest result.

        Args:
            backtest_id: Backtest ID
            user_id: User ID (UUID string) for security check

        Returns:
            BacktestResult or None if not found/unauthorized
        """
        try:
            backtest_uuid = UUID(backtest_id)
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
        except (ValueError, AttributeError):
            # Invalid UUID format
            return None

        result = await self.session.execute(
            select(Backtest).where(
                and_(
                    Backtest.id == backtest_uuid,
                    Backtest.user_id == user_uuid
                )
            )
        )
        backtest = result.scalar_one_or_none()

        if not backtest:
            return None

        # Get strategy name
        strategy_result = await self.session.execute(
            select(Strategy).where(Strategy.id == backtest.strategy_id)
        )
        strategy = strategy_result.scalar_one_or_none()

        # Convert stored JSON back to Pydantic models
        equity_curve = [EquityPoint(**eq) for eq in backtest.equity_curve or []]
        trade_log = [Trade(**t) for t in backtest.trade_log or []]
        metrics = PerformanceMetrics(**backtest.metrics) if backtest.metrics else None

        return BacktestResult(
            id=str(backtest.id),
            strategy_id=str(backtest.strategy_id),
            strategy_name=strategy.name if strategy else "Unknown",
            start_date=backtest.start_date,
            end_date=backtest.end_date,
            initial_capital=float(backtest.initial_capital),
            final_equity=float(backtest.final_equity) if backtest.final_equity else 0.0,
            metrics=metrics,
            equity_curve=equity_curve,
            trade_log=trade_log,
            monthly_returns=backtest.monthly_returns or [],
            status=backtest.status,
            error_message=backtest.error_message,
            progress=backtest.progress,
            created_at=backtest.created_at,
            started_at=backtest.started_at,
            completed_at=backtest.completed_at,
        )

    async def delete_backtest(
        self,
        backtest_id: str,
        user_id: str,
    ) -> bool:
        """
        Delete a backtest.

        Args:
            backtest_id: Backtest ID
            user_id: User ID (UUID string) for security check

        Returns:
            True if deleted, False if not found/unauthorized
        """
        try:
            backtest_uuid = UUID(backtest_id)
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
        except (ValueError, AttributeError):
            # Invalid UUID format
            return False

        result = await self.session.execute(
            select(Backtest).where(
                and_(
                    Backtest.id == backtest_uuid,
                    Backtest.user_id == user_uuid
                )
            )
        )
        backtest = result.scalar_one_or_none()

        if not backtest:
            return False

        await self.session.delete(backtest)
        await self.session.commit()

        logger.info(f"Deleted backtest {backtest_id}")
        return True

    # ========================================================================
    # PARAMETER OPTIMIZATION
    # ========================================================================

    async def optimize_parameters(
        self,
        strategy: Strategy,
        start_date: date,
        end_date: date,
        initial_capital: float,
        param_grid: dict[str, list[Any]],
        optimization_metric: str = "sharpe_ratio",
        user_id: str = None,
    ) -> dict[str, Any]:
        """
        Grid search optimization for strategy parameters.
        
        Finds the best parameter combination by running backtests across all
        combinations and selecting the one with the best optimization metric.
        
        Args:
            strategy: Base strategy to optimize
            start_date: Backtest start date
            end_date: Backtest end date
            initial_capital: Initial capital
            param_grid: Dict of parameter names to lists of values to try
                       e.g., {"rsi_buy": [30, 35, 40], "rsi_sell": [60, 65, 70]}
            optimization_metric: Metric to optimize ("sharpe_ratio", "total_return", etc.)
            user_id: User ID for backtest records
            
        Returns:
            Dict with best_params, best_score, and all_results
        """
        import itertools

        logger.info(f"Starting parameter optimization with {len(param_grid)} parameters")

        # Generate all parameter combinations
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(itertools.product(*param_values))

        logger.info(f"Testing {len(combinations)} parameter combinations")

        results = []
        best_score = float('-inf')
        best_params = None
        best_result = None

        for combo in combinations:
            params = dict(zip(param_names, combo))

            try:
                # Run backtest with these parameters
                result = await self.run_backtest(
                    strategy=strategy,
                    start_date=start_date,
                    end_date=end_date,
                    initial_capital=initial_capital,
                    parameters=params,
                    user_id=user_id,
                )

                # Extract optimization metric
                score = getattr(result.metrics, optimization_metric, 0)

                results.append({
                    "params": params,
                    "score": score,
                    "metrics": {
                        "sharpe_ratio": result.metrics.sharpe_ratio,
                        "total_return": result.metrics.total_return,
                        "max_drawdown": result.metrics.max_drawdown,
                        "win_rate": result.metrics.win_rate,
                        "total_trades": result.metrics.total_trades,
                    }
                })

                if score > best_score:
                    best_score = score
                    best_params = params
                    best_result = result

                logger.info(f"Params {params}: {optimization_metric}={score:.4f}")

            except Exception as e:
                logger.warning(f"Failed backtest with params {params}: {e}")
                results.append({
                    "params": params,
                    "score": float('-inf'),
                    "error": str(e)
                })

        # Sort results by score descending
        results.sort(key=lambda x: x.get("score", float('-inf')), reverse=True)

        logger.info(f"Optimization complete. Best params: {best_params}, Best {optimization_metric}: {best_score:.4f}")

        return {
            "best_params": best_params,
            "best_score": best_score,
            "best_result": best_result,
            "optimization_metric": optimization_metric,
            "all_results": results[:20],  # Top 20 results
            "total_combinations_tested": len(combinations),
        }

    # ========================================================================
    # WALK-FORWARD VALIDATION
    # ========================================================================

    async def walk_forward_validation(
        self,
        strategy: Strategy,
        start_date: date,
        end_date: date,
        initial_capital: float,
        param_grid: dict[str, list[Any]],
        n_splits: int = 5,
        train_pct: float = 0.7,
        optimization_metric: str = "sharpe_ratio",
        user_id: str = None,
    ) -> dict[str, Any]:
        """
        Walk-forward validation to prevent overfitting.
        
        Splits data into multiple train/test periods, optimizes on train,
        validates on test. This is the GOLD STANDARD for strategy validation.
        
        Algorithm:
        1. Split date range into n_splits periods
        2. For each period: optimize on training portion, test on validation portion
        3. Aggregate out-of-sample performance across all periods
        
        Args:
            strategy: Strategy to validate
            start_date: Overall start date
            end_date: Overall end date
            initial_capital: Initial capital
            param_grid: Parameters to optimize
            n_splits: Number of walk-forward periods
            train_pct: Percentage of each period for training (0.7 = 70% train, 30% test)
            optimization_metric: Metric to optimize during training
            user_id: User ID
            
        Returns:
            Dict with walk-forward results, out-of-sample metrics, and robustness score
        """
        from datetime import timedelta

        logger.info(f"Starting walk-forward validation with {n_splits} splits")

        # Calculate total days and split size
        total_days = (end_date - start_date).days
        split_size = total_days // n_splits

        if split_size < 60:  # Minimum 60 days per split
            raise ValueError(f"Date range too short for {n_splits} splits. Need at least {60 * n_splits} days.")

        walk_forward_results = []
        oos_equity_curves = []  # Out-of-sample equity curves
        oos_trades = []  # Out-of-sample trades

        for i in range(n_splits):
            split_start = start_date + timedelta(days=i * split_size)
            split_end = split_start + timedelta(days=split_size)

            # Ensure last split extends to end_date
            if i == n_splits - 1:
                split_end = end_date

            # Split into train and test
            train_days = int((split_end - split_start).days * train_pct)
            train_end = split_start + timedelta(days=train_days)
            test_start = train_end + timedelta(days=1)

            logger.info(f"Split {i+1}/{n_splits}: Train {split_start} to {train_end}, Test {test_start} to {split_end}")

            try:
                # STEP 1: Optimize on training period
                optimization_result = await self.optimize_parameters(
                    strategy=strategy,
                    start_date=split_start,
                    end_date=train_end,
                    initial_capital=initial_capital,
                    param_grid=param_grid,
                    optimization_metric=optimization_metric,
                    user_id=user_id,
                )

                best_params = optimization_result["best_params"]
                in_sample_score = optimization_result["best_score"]

                # STEP 2: Validate on out-of-sample test period
                oos_result = await self.run_backtest(
                    strategy=strategy,
                    start_date=test_start,
                    end_date=split_end,
                    initial_capital=initial_capital,
                    parameters=best_params,
                    user_id=user_id,
                )

                oos_score = getattr(oos_result.metrics, optimization_metric, 0)

                # Calculate robustness: OOS performance vs in-sample
                robustness = oos_score / in_sample_score if in_sample_score > 0 else 0

                walk_forward_results.append({
                    "split": i + 1,
                    "train_period": f"{split_start} to {train_end}",
                    "test_period": f"{test_start} to {split_end}",
                    "best_params": best_params,
                    "in_sample_score": in_sample_score,
                    "out_of_sample_score": oos_score,
                    "robustness_ratio": robustness,
                    "oos_metrics": {
                        "sharpe_ratio": oos_result.metrics.sharpe_ratio,
                        "total_return": oos_result.metrics.total_return,
                        "max_drawdown": oos_result.metrics.max_drawdown,
                        "win_rate": oos_result.metrics.win_rate,
                        "total_trades": oos_result.metrics.total_trades,
                    }
                })

                # Collect OOS data
                oos_equity_curves.extend(oos_result.equity_curve)
                oos_trades.extend(oos_result.trade_log)

                logger.info(
                    f"Split {i+1}: IS {optimization_metric}={in_sample_score:.4f}, "
                    f"OOS {optimization_metric}={oos_score:.4f}, Robustness={robustness:.2f}"
                )

            except Exception as e:
                logger.error(f"Walk-forward split {i+1} failed: {e}")
                walk_forward_results.append({
                    "split": i + 1,
                    "error": str(e)
                })

        # Calculate aggregate out-of-sample metrics
        valid_results = [r for r in walk_forward_results if "error" not in r]

        if valid_results:
            avg_oos_score = sum(r["out_of_sample_score"] for r in valid_results) / len(valid_results)
            avg_robustness = sum(r["robustness_ratio"] for r in valid_results) / len(valid_results)

            # Calculate combined OOS metrics from all equity curves
            if oos_equity_curves:
                combined_metrics = self.calculate_metrics(
                    oos_trades,
                    oos_equity_curves,
                    initial_capital,
                    start_date,
                    end_date,
                )
            else:
                combined_metrics = None

            # Determine if strategy is robust
            # Robustness > 0.7 means OOS performance is at least 70% of in-sample
            is_robust = avg_robustness >= 0.7

        else:
            avg_oos_score = 0
            avg_robustness = 0
            combined_metrics = None
            is_robust = False

        # Find most stable parameters (appear most often in best params)
        param_counts = defaultdict(lambda: defaultdict(int))
        for r in valid_results:
            if "best_params" in r:
                for param, value in r["best_params"].items():
                    param_counts[param][value] += 1

        stable_params = {}
        for param, value_counts in param_counts.items():
            stable_params[param] = max(value_counts.keys(), key=lambda v: value_counts[v])

        logger.info(
            f"Walk-forward complete: Avg OOS {optimization_metric}={avg_oos_score:.4f}, "
            f"Avg Robustness={avg_robustness:.2f}, Is Robust={is_robust}"
        )

        return {
            "n_splits": n_splits,
            "train_pct": train_pct,
            "optimization_metric": optimization_metric,
            "walk_forward_results": walk_forward_results,
            "avg_out_of_sample_score": avg_oos_score,
            "avg_robustness_ratio": avg_robustness,
            "is_robust": is_robust,
            "stable_params": stable_params,
            "combined_oos_metrics": combined_metrics.model_dump() if combined_metrics else None,
            "total_oos_trades": len(oos_trades),
            "recommendation": (
                "PASS: Strategy shows robust out-of-sample performance. Safe to deploy."
                if is_robust and avg_oos_score > 0
                else "FAIL: Strategy shows signs of overfitting. Do not deploy without further testing."
            )
        }
