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
import os
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


def _extract_origin(parameters: dict[str, Any] | None) -> str:
    if isinstance(parameters, dict):
        origin = parameters.get("_origin")
        if isinstance(origin, str) and origin:
            return origin
    return "ui"


def _extract_engine(parameters: dict[str, Any] | None) -> str:
    if isinstance(parameters, dict):
        engine = parameters.get("_engine")
        if isinstance(engine, str) and engine.strip():
            normalized = engine.strip().lower()
            if normalized in {"platform", "research"}:
                return normalized
    return "platform"


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

                    # P&L-017: Generate regime-varied mock data instead of monotonic uptrend.
                    # Split into ~33% uptrend, ~33% downtrend, ~33% choppy to avoid
                    # biasing backtest results toward trend-following strategies.
                    n = len(date_index)
                    if n <= 3:
                        # Too few bars for multi-regime: simple constant series
                        close = np.full(n, 100.0)
                        volume = np.full(n, 1_000, dtype=int)
                    else:
                        third = max(1, n // 3)
                        segments = []
                        base = 100.0
                        # Segment 1: uptrend
                        up = base + np.linspace(0.0, 10.0, num=third)
                        segments.append(up)
                        # Segment 2: downtrend
                        down_start = float(up[-1])
                        down = down_start - np.linspace(0.0, 15.0, num=third)
                        segments.append(down)
                        # Segment 3: choppy/mean-reverting
                        chop_start = float(down[-1])
                        remainder = n - 2 * third
                        if remainder > 0:
                            chop = chop_start + np.random.default_rng(42).normal(0, 0.5, size=remainder).cumsum()
                            segments.append(chop)
                        close = np.concatenate(segments)[:n]
                        # Add realistic daily noise
                        noise = np.random.default_rng(42).normal(0, 0.3, size=n)
                        close = close + noise
                        close = np.maximum(close, 1.0)  # floor at $1
                        vol_base = 1_000
                        volume = np.random.default_rng(42).integers(vol_base // 2, vol_base * 3, size=n)

                    df = pd.DataFrame(
                        {
                            "timestamp": date_index,
                            "open": close * (1.0 + np.random.default_rng(43).uniform(-0.005, 0.005, size=n)),
                            "high": close * (1.0 + np.random.default_rng(44).uniform(0.001, 0.015, size=n)),
                            "low": close * (1.0 - np.random.default_rng(45).uniform(0.001, 0.015, size=n)),
                            "close": close,
                            "volume": volume,
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
        engine: str = "platform",
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

        # Convert user_id to UUID (required by database schema)
        # Handles: string UUID, integer user IDs, UUID objects, or None
        if user_id:
            if isinstance(user_id, UUID):
                user_uuid = user_id
            elif isinstance(user_id, str):
                user_uuid = UUID(user_id)
            elif isinstance(user_id, int):
                # Convert integer user_id to deterministic UUID using namespace
                import uuid as uuid_module
                NAMESPACE = uuid_module.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
                user_uuid = uuid_module.uuid5(NAMESPACE, f"user_{user_id}")
                logger.warning(f"Converting integer user_id {user_id} to UUID {user_uuid}")
            else:
                # Fallback: try to convert to string then UUID
                user_uuid = UUID(str(user_id))
        else:
            # Generate a default UUID for anonymous/system backtests
            user_uuid = uuid4()

        engine_norm = (engine or "platform").strip().lower()
        if engine_norm not in {"platform", "research"}:
            raise ValueError("engine must be 'platform' or 'research'")

        # Use parameters override if provided, otherwise use strategy parameters
        base_params = parameters if parameters is not None else getattr(strategy, 'parameters', {})
        effective_params = dict(base_params or {})
        # Persist engine selection on the record to allow history/result hydration.
        effective_params["_engine"] = engine_norm

        # Create backtest record
        backtest = Backtest(
            id=uuid4(),
            strategy_id=strategy_id,
            user_id=user_uuid,
            start_date=start_date,
            end_date=end_date,
            initial_capital=Decimal(str(initial_capital)),
            parameters=effective_params,
            status="running",
            progress=0,
            started_at=datetime.now(),
        )
        self.session.add(backtest)
        await self.session.commit()

        try:
            # Optuna meta-strategy parity: detect Optuna harness params and run the same
            # signal logic / regime gating as the Optuna research harness.
            origin = _extract_origin(effective_params)
            is_optuna_meta = self._is_optuna_meta_params(effective_params) and origin == "optuna"
            market_symbol = None

            # Get symbols from strategy (safe access)
            symbols_attr = getattr(strategy, 'symbols', [])
            symbols = symbols_attr if isinstance(symbols_attr, list) else []
            if not symbols:
                raise ValueError("Strategy has no symbols configured")

            fetch_symbols = list(symbols)
            if is_optuna_meta:
                market_symbol = str(effective_params.get("market_symbol") or "SPY")
                if market_symbol and market_symbol not in fetch_symbols:
                    fetch_symbols.append(market_symbol)

            if engine_norm == "research":
                if not self._is_optuna_meta_params(effective_params):
                    raise ValueError(
                        "research engine is currently supported only for optuna_meta parameters"
                    )

                if not market_symbol:
                    market_symbol = str(effective_params.get("market_symbol") or "SPY")
                    if market_symbol and market_symbol not in fetch_symbols:
                        fetch_symbols.append(market_symbol)

            # Fetch historical data
            logger.info(f"Fetching historical data for {len(fetch_symbols)} symbols")
            market_data_by_date = await self._fetch_historical_data(
                fetch_symbols, start_date, end_date
            )

            if not market_data_by_date:
                raise ValueError("No historical data available for date range")

            if engine_norm == "research":
                result = await self._run_research_engine_backtest(
                    backtest=backtest,
                    strategy=strategy,
                    symbols=symbols,
                    market_symbol=str(market_symbol or "SPY"),
                    market_data_by_date=market_data_by_date,
                    start_date=start_date,
                    end_date=end_date,
                    initial_capital=initial_capital,
                    effective_params=effective_params,
                )
                return result

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
            warmup = int(effective_params.get('warmup', 0) or 0)
            # Minimum bars needed for indicators + optuna warmup.
            # Note: Optuna harness treats insufficient market SMA history as risk_on,
            # so market_sma should NOT gate signal generation.
            LOOKBACK_REQUIRED = max(sma_period, rsi_period + 1, macd_slow, bb_period, 20, warmup)

            # Parameterized overlays (optuna_meta only)
            overlay_kill_switch = bool(int(effective_params.get("overlay_kill_switch", 0)))
            overlay_kill_dd_pct = float(effective_params.get("overlay_kill_dd_pct", 0.0) or 0.0)
            overlay_kill_cooldown_days = int(effective_params.get("overlay_kill_cooldown_days", 0) or 0)
            overlay_kill_force_exit = bool(int(effective_params.get("overlay_kill_force_exit", 0)))

            overlay_vol_enabled = bool(int(effective_params.get("overlay_vol_enabled", 0)))
            overlay_vol_target = float(effective_params.get("overlay_vol_target", 0.0) or 0.0)
            overlay_vol_window = int(effective_params.get("overlay_vol_window", 20) or 20)
            overlay_vol_min_mult = float(effective_params.get("overlay_vol_min_mult", 0.5) or 0.5)
            overlay_vol_max_mult = float(effective_params.get("overlay_vol_max_mult", 1.5) or 1.5)

            overlay_gap_enabled = bool(int(effective_params.get("overlay_gap_enabled", 0)))
            overlay_gap_max_pct = float(effective_params.get("overlay_gap_max_pct", 0.0) or 0.0)

            kill_cooldown_remaining = 0
            kill_peak_equity = float(initial_capital)

            def _update_kill_state(equity_now: float) -> bool:
                nonlocal kill_peak_equity, kill_cooldown_remaining
                if equity_now > kill_peak_equity:
                    kill_peak_equity = equity_now
                dd = (kill_peak_equity - equity_now) / kill_peak_equity if kill_peak_equity > 0 else 0.0
                if overlay_kill_switch and overlay_kill_dd_pct > 0 and dd >= overlay_kill_dd_pct:
                    if kill_cooldown_remaining <= 0:
                        kill_cooldown_remaining = max(1, overlay_kill_cooldown_days)
                return kill_cooldown_remaining > 0

            def _vol_size_mult() -> float:
                if not overlay_vol_enabled or overlay_vol_target <= 0 or overlay_vol_window < 2:
                    return 1.0
                if not market_symbol:
                    return 1.0
                closes = price_history.get(market_symbol) or []
                if len(closes) < max(3, overlay_vol_window + 1):
                    return 1.0
                window = np.asarray(closes[-(overlay_vol_window + 1):], dtype=float)
                rets = np.diff(window) / np.where(window[:-1] == 0, 1, window[:-1])
                realized = float(np.std(rets)) * np.sqrt(252.0)
                if realized <= 0:
                    return 1.0
                mult = overlay_vol_target / realized
                return float(np.clip(mult, overlay_vol_min_mult, overlay_vol_max_mult))

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
                overlay_context: dict[str, Any] | None = None
                if is_optuna_meta:
                    kill_active = _update_kill_state(portfolio.total_equity)
                    size_mult = _vol_size_mult()
                    overlay_context = {
                        "kill_active": kill_active,
                        "kill_force_exit": overlay_kill_force_exit,
                        "size_mult": size_mult,
                        "gap_enabled": overlay_gap_enabled,
                        "gap_max_pct": overlay_gap_max_pct,
                    }

                if idx >= LOOKBACK_REQUIRED:
                    strategy_type = getattr(strategy, 'strategy_type', 'momentum')
                    # Auto-upgrade Optuna-origin meta configs even if the stored strategy_type
                    # is generic (e.g., technical_analysis).
                    if is_optuna_meta:
                        strategy_type = "optuna_meta"
                    new_signals = self._generate_signals_with_history(
                        strategy_type,
                        effective_params,
                        market_data,
                        price_history,
                        portfolio,
                        trading_date,
                        market_symbol=market_symbol,
                        overlay_context=overlay_context,
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

                if is_optuna_meta and kill_cooldown_remaining > 0:
                    kill_cooldown_remaining -= 1

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
                engine=engine_norm,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                final_equity=portfolio.total_equity,
                metrics=metrics,
                equity_curve=equity_curve,
                trade_log=all_trades,
                monthly_returns=[mr.model_dump() for mr in monthly_returns],
                status="completed",
                origin=_extract_origin(backtest.parameters),
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

    async def _run_research_engine_backtest(
        self,
        *,
        backtest: Backtest,
        strategy: Strategy,
        symbols: list[str],
        market_symbol: str,
        market_data_by_date: dict[date, dict[str, MarketData]],
        start_date: date,
        end_date: date,
        initial_capital: float,
        effective_params: dict[str, Any],
    ) -> BacktestResult:
        """Run the research backtest engine and persist results in platform format."""
        try:
            import pandas as pd
        except Exception as e:  # pragma: no cover
            raise RuntimeError("research engine requires pandas installed") from e

        from backend.research.optuna_meta_research_engine import (
            CostModel,
            run_backtest_panel_detailed,
        )

        trading_days = sorted(market_data_by_date.keys())
        valid_days: list[date] = []
        for d in trading_days:
            md = market_data_by_date[d]
            if market_symbol not in md:
                continue
            if all(sym in md for sym in symbols):
                valid_days.append(d)

        if not valid_days:
            raise ValueError("Insufficient aligned historical data for research engine")

        dt_index = pd.to_datetime(valid_days)
        panel_close = pd.DataFrame(index=dt_index, columns=symbols, dtype=float)
        panel_open = pd.DataFrame(index=dt_index, columns=symbols, dtype=float)

        market_close = pd.Series(index=dt_index, dtype=float)
        market_open = pd.Series(index=dt_index, dtype=float)

        for d in valid_days:
            ts = pd.Timestamp(d)
            md = market_data_by_date[d]
            for sym in symbols:
                panel_close.loc[ts, sym] = float(md[sym].close)
                panel_open.loc[ts, sym] = float(md[sym].open)
            market_close.loc[ts] = float(md[market_symbol].close)
            market_open.loc[ts] = float(md[market_symbol].open)

        slippage_bps = float(effective_params.get("slippage_bps", 0.0) or 0.0)
        # P&L-019: Default commission is $1 per trade to avoid unrealistically
        # optimistic backtests with zero trading costs.
        commission_per_trade = float(effective_params.get("commission_per_trade", 1.0) or 1.0)
        costs = CostModel(slippage_bps=slippage_bps, commission_per_trade=commission_per_trade)

        execution_mode = str(
            effective_params.get("execution_mode")
            or effective_params.get("opt_execution_mode")
            or os.getenv("OPT_EXECUTION_MODE", "close")
        )
        market_buffer_side = str(
            effective_params.get("opt_market_buffer_side")
            or os.getenv("OPT_MARKET_BUFFER_SIDE", "below")
        )

        allow_leverage = bool(
            effective_params.get("allow_leverage")
            or effective_params.get("use_optuna_leverage")
        )

        required_keys = {
            "warmup",
            "stop_loss_pct",
            "take_profit_pct",
            "position_size_pct",
            "max_positions",
            "min_position_dollars",
            "rsi_buy",
            "rsi_sell",
            "sma_fast",
            "sma_slow",
            "band_tolerance",
            "entry_threshold",
            "trend_threshold",
            "decision_threshold",
            "w_ensemble",
            "w_momentum",
            "w_meanrev",
            "w_statarb",
        }
        missing = sorted(k for k in required_keys if k not in effective_params)
        if missing:
            raise ValueError(f"Missing required research params: {missing}")

        out = run_backtest_panel_detailed(
            panel_close,
            market_close,
            effective_params,
            costs,
            initial_capital,
            panel_open=panel_open,
            market_open=market_open,
            execution_mode=execution_mode,
            market_buffer_side=market_buffer_side,
            allow_leverage=allow_leverage,
        )

        # Convert to platform models so the UI can reuse existing components.
        equity_curve: list[EquityPoint] = []
        for ts, equity, cash, pos_value in out.equity_curve:
            d = pd.Timestamp(ts).date()
            equity_curve.append(
                EquityPoint(
                    date=d,
                    value=float(equity),
                    cash=float(cash),
                    positions_value=float(pos_value),
                )
            )

        trade_log: list[Trade] = []
        for ct in out.closed_trades:
            entry_date = pd.Timestamp(ct.entry_dt).date()
            exit_date = pd.Timestamp(ct.exit_dt).date()
            duration = (exit_date - entry_date).days
            pnl = (float(ct.exit_price) - float(ct.entry_price)) * int(ct.qty)
            pnl_percent = ((float(ct.exit_price) / float(ct.entry_price)) - 1.0) * 100.0 if ct.entry_price else 0.0
            per_leg_commission = float(ct.commission) / 2.0 if ct.commission else 0.0

            trade_log.append(
                Trade(
                    symbol=ct.symbol,
                    side="buy",
                    quantity=int(ct.qty),
                    entry_date=entry_date,
                    entry_price=float(ct.entry_price),
                    commission=per_leg_commission,
                )
            )
            trade_log.append(
                Trade(
                    symbol=ct.symbol,
                    side="sell",
                    quantity=int(ct.qty),
                    entry_date=entry_date,
                    entry_price=float(ct.entry_price),
                    exit_date=exit_date,
                    exit_price=float(ct.exit_price),
                    pnl=float(pnl),
                    pnl_percent=float(pnl_percent),
                    duration_days=int(duration),
                    exit_reason=ct.exit_reason,
                    commission=per_leg_commission,
                )
            )

        metrics = self.calculate_metrics(
            trade_log,
            equity_curve,
            initial_capital,
            start_date,
            end_date,
        )
        monthly_returns = self._calculate_monthly_returns(equity_curve)

        final_equity = float(equity_curve[-1].value) if equity_curve else float(initial_capital)

        backtest.status = "completed"
        backtest.progress = 100
        backtest.completed_at = datetime.now()
        backtest.final_equity = Decimal(str(final_equity))
        backtest.total_return = Decimal(str(metrics.total_return))
        backtest.annualized_return = Decimal(str(metrics.annualized_return))
        backtest.sharpe_ratio = Decimal(str(metrics.sharpe_ratio))
        backtest.max_drawdown = Decimal(str(metrics.max_drawdown))
        backtest.win_rate = Decimal(str(metrics.win_rate))
        backtest.profit_factor = Decimal(str(metrics.profit_factor))
        backtest.total_trades = metrics.total_trades
        backtest.winning_trades = metrics.winning_trades
        backtest.losing_trades = metrics.losing_trades

        backtest.equity_curve = [eq.model_dump(mode='json') for eq in equity_curve]
        backtest.trade_log = [t.model_dump(mode='json') for t in trade_log]
        backtest.monthly_returns = [mr.model_dump(mode='json') for mr in monthly_returns]
        backtest.metrics = metrics.model_dump(mode='json')
        await self.session.commit()

        strategy_name = getattr(strategy, 'name', 'Unknown Strategy')
        strategy_id = getattr(strategy, 'id', None)

        return BacktestResult(
            id=str(backtest.id),
            strategy_id=str(strategy_id),
            strategy_name=str(strategy_name),
            engine=_extract_engine(backtest.parameters),
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_equity=final_equity,
            metrics=metrics,
            equity_curve=equity_curve,
            trade_log=trade_log,
            monthly_returns=[mr.model_dump() for mr in monthly_returns],
            status="completed",
            origin=_extract_origin(backtest.parameters),
            created_at=backtest.created_at,
            started_at=backtest.started_at,
            completed_at=backtest.completed_at,
        )

    def _is_optuna_meta_params(self, parameters: dict[str, Any]) -> bool:
        meta_keys = {
            "rsi_buy",
            "rsi_sell",
            "sma_fast",
            "sma_slow",
            "band_tolerance",
            "entry_threshold",
            "trend_threshold",
            "decision_threshold",
            "w_ensemble",
            "w_momentum",
            "w_meanrev",
            "w_statarb",
        }
        return all(k in parameters for k in meta_keys)

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
        *,
        price_history: dict[str, list[float]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Generate trading signals based on strategy type.

        P&L-016: When ``price_history`` is provided, delegates to
        ``_generate_signals_with_history()`` which uses real RSI/SMA
        indicators instead of primitive heuristics.

        Args:
            strategy_type: Type of strategy (momentum, mean_reversion, etc.)
            parameters: Strategy parameters
            market_data: Current market data for all symbols
            portfolio: Current portfolio state
            current_date: Current date in simulation
            price_history: Optional rolling price history per symbol

        Returns:
            List of signals with action, symbol, and confidence
        """
        # P&L-016: Prefer history-aware generation when history is available.
        if price_history:
            return self._generate_signals_with_history(
                strategy_type=strategy_type,
                parameters=parameters,
                market_data=market_data,
                price_history=price_history,
                portfolio=portfolio,
                current_date=current_date,
            )

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
        *,
        market_symbol: str | None = None,
        overlay_context: dict[str, Any] | None = None,
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

        def _to_int(value: object, default: int) -> int:
            if value is None:
                return default
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        # Extract strategy parameters with sensible defaults
        rsi_buy = parameters.get("rsi_buy", parameters.get("oversold_threshold", 35))
        rsi_sell = parameters.get("rsi_sell", parameters.get("overbought_threshold", 65))
        sma_fast = _to_int(parameters.get("sma_fast", parameters.get("ma_period", 20)), 20)
        sma_slow = _to_int(parameters.get("sma_slow", 50), 50)
        min_confidence = parameters.get("min_confidence", 0.5)
        extreme_offset = parameters.get("extreme_offset", 5.0)  # For mean reversion

        if strategy_type == "optuna_meta":
            return self._generate_optuna_meta_signals(
                parameters,
                market_data,
                price_history,
                portfolio,
                current_date,
                market_symbol=market_symbol,
                overlay_context=overlay_context,
            )

        for symbol, data in market_data.items():
            if market_symbol and symbol == market_symbol:
                continue
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

    def _generate_optuna_meta_signals(
        self,
        parameters: dict[str, Any],
        market_data: dict[str, MarketData],
        price_history: dict[str, list[float]],
        portfolio: PortfolioState,
        current_date: date,
        *,
        market_symbol: str | None,
        overlay_context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []

        stop_loss = float(parameters.get("stop_loss_pct", 0.0) or 0.0)
        take_profit = float(parameters.get("take_profit_pct", 0.0) or 0.0)
        min_hold_days = int(parameters.get("min_hold_days", 0) or 0)

        market_sma = int(parameters.get("market_sma", 200) or 200)
        market_buffer = float(parameters.get("market_buffer", 0.0) or 0.0)
        market_force_exit = bool(int(parameters.get("market_force_exit", 1) or 1))
        market_trim_risk_off = bool(int(parameters.get("market_trim_risk_off", 0) or 0))
        risk_off_exposure_mult = float(parameters.get("risk_off_exposure_mult", 0.5) or 0.5)
        risk_off_exposure_mult = float(np.clip(risk_off_exposure_mult, 0.0, 1.0))

        overlay_risk_off_adjust = bool(int(parameters.get("overlay_risk_off_adjust", 0) or 0))
        overlay_risk_off_stop_mult = float(parameters.get("overlay_risk_off_stop_mult", 1.0) or 1.0)
        overlay_risk_off_take_mult = float(parameters.get("overlay_risk_off_take_mult", 1.0) or 1.0)

        kill_active = bool(overlay_context.get("kill_active") if overlay_context else False)
        kill_force_exit = bool(overlay_context.get("kill_force_exit") if overlay_context else False)
        size_mult = float(overlay_context.get("size_mult") if overlay_context else 1.0)
        gap_enabled = bool(overlay_context.get("gap_enabled") if overlay_context else False)
        gap_max_pct = float(overlay_context.get("gap_max_pct") if overlay_context else 0.0)

        default_buffer_side = "above" if _extract_origin(parameters) == "optuna" else "below"
        market_buffer_side = (
            str(
                parameters.get("opt_market_buffer_side")
                or os.getenv("OPT_MARKET_BUFFER_SIDE", default_buffer_side)
            )
            .strip()
            .lower()
        )

        def _market_on() -> bool:
            if not market_symbol or market_symbol not in price_history:
                return True
            closes = price_history.get(market_symbol) or []
            if len(closes) < max(1, market_sma):
                return True
            window = np.asarray(closes[-market_sma:], dtype=float)
            if window.size == 0 or not np.isfinite(window).all():
                return True
            sma = float(np.mean(window))
            if sma <= 0:
                return True
            current = float(closes[-1])
            if market_buffer_side in {"above", "strict", "over"}:
                threshold = sma * (1.0 + market_buffer)
            else:
                threshold = sma * (1.0 - market_buffer)
            return current >= threshold

        risk_on = _market_on()

        stop_loss_adj = stop_loss
        take_profit_adj = take_profit
        if (not risk_on) and overlay_risk_off_adjust:
            stop_loss_adj = stop_loss * overlay_risk_off_stop_mult
            take_profit_adj = take_profit * overlay_risk_off_take_mult

        # 1) Forced exits when market is risk-off.
        if (not risk_on) and market_force_exit and portfolio.positions:
            for symbol in list(portfolio.positions.keys()):
                if market_symbol and symbol == market_symbol:
                    continue
                signals.append(
                    {
                        "action": "sell",
                        "symbol": symbol,
                        "confidence": 1.0,
                        "reason": "market_force_exit",
                        "indicators": {"risk_on": False},
                    }
                )
            return signals

        # 1b) Kill-switch forced exits.
        if kill_force_exit and portfolio.positions:
            for symbol in list(portfolio.positions.keys()):
                if market_symbol and symbol == market_symbol:
                    continue
                signals.append(
                    {
                        "action": "sell",
                        "symbol": symbol,
                        "confidence": 1.0,
                        "reason": "overlay_kill_switch",
                        "indicators": {"kill_active": True},
                    }
                )
            return signals

        # 2) Stop-loss / take-profit exits (decided on close, executed next open).
        for symbol, pos in list(portfolio.positions.items()):
            if market_symbol and symbol == market_symbol:
                continue
            data = market_data.get(symbol)
            if not data:
                continue
            avg_price = float(pos.get("avg_price") or 0.0)
            if avg_price <= 0:
                continue

            entry_date = pos.get("entry_date")
            held_days = 0
            try:
                if entry_date:
                    held_days = (current_date - entry_date).days
            except Exception:
                held_days = 0

            pnl_pct = (float(data.close) - avg_price) / avg_price
            should_exit = False
            if stop_loss_adj > 0 and pnl_pct <= -stop_loss_adj:
                should_exit = True
            if take_profit_adj > 0 and pnl_pct >= take_profit_adj:
                should_exit = True

            if should_exit:
                signals.append(
                    {
                        "action": "sell",
                        "symbol": symbol,
                        "confidence": 1.0,
                        "reason": "stop_or_take_profit",
                        "indicators": {"pnl_pct": pnl_pct, "held_days": held_days},
                    }
                )

        # 3) Risk-off trimming (sell whole positions until below risk-off cap).
        if (not risk_on) and (not market_force_exit) and market_trim_risk_off and portfolio.positions:
            max_gross_exposure = float(parameters.get("max_gross_exposure", 1.0) or 1.0)
            target_cap = max(0.0, max_gross_exposure * risk_off_exposure_mult)
            target_positions_value = float(portfolio.total_equity) * target_cap
            positions_value = float(portfolio.positions_value)

            if positions_value > target_positions_value and portfolio.total_equity > 0:
                ranked: list[tuple[int, float, str]] = []
                for sym in portfolio.positions.keys():
                    if market_symbol and sym == market_symbol:
                        continue
                    closes = price_history.get(sym) or []
                    action, conf = self._optuna_meta_action_conf(closes, parameters)
                    if action == "sell":
                        bucket = 0
                    elif action == "hold":
                        bucket = 1
                    else:
                        bucket = 2
                    ranked.append((bucket, float(conf), sym))
                ranked.sort(key=lambda x: (x[0], x[1]))

                for _bucket, _conf, sym in ranked:
                    if positions_value <= target_positions_value:
                        break
                    signals.append(
                        {
                            "action": "sell",
                            "symbol": sym,
                            "confidence": 0.9,
                            "reason": "market_trim_risk_off",
                            "indicators": {"risk_on": False},
                        }
                    )
                    md = market_data.get(sym)
                    qty = float(portfolio.positions.get(sym, {}).get("quantity") or 0.0)
                    if md and qty > 0:
                        positions_value -= float(md.close) * qty

        # 4) Meta-signal entries/exits.
        for symbol, data in market_data.items():
            if market_symbol and symbol == market_symbol:
                continue
            closes = price_history.get(symbol, [])
            if not closes:
                continue

            has_position = (portfolio.positions.get(symbol, {}).get("quantity", 0) or 0) > 0
            action, conf = self._optuna_meta_action_conf(closes, parameters)

            if action == "buy" and risk_on and (not has_position) and (not kill_active):
                signals.append(
                    {
                        "action": "buy",
                        "symbol": symbol,
                        "confidence": round(float(conf), 3),
                        "reason": "optuna_meta_buy",
                        "indicators": {"risk_on": risk_on},
                        "size_mult": float(size_mult),
                        "prev_close": float(data.close),
                        "max_gap_pct": float(gap_max_pct) if gap_enabled else 0.0,
                    }
                )
            elif action == "sell" and has_position:
                entry_date = portfolio.positions.get(symbol, {}).get("entry_date")
                held_days = 0
                try:
                    if entry_date:
                        held_days = (current_date - entry_date).days
                except Exception:
                    held_days = 0
                if held_days >= min_hold_days:
                    signals.append(
                        {
                            "action": "sell",
                            "symbol": symbol,
                            "confidence": round(float(conf), 3),
                            "reason": "optuna_meta_sell",
                            "indicators": {"risk_on": risk_on, "held_days": held_days},
                        }
                    )

        return signals

    def _optuna_meta_action_conf(
        self, closes: list[float], parameters: dict[str, Any]
    ) -> tuple[str, float]:
        # Mirrors scripts/optuna_meta_strategy_optimizer.py::_meta_signal
        try:
            series = np.asarray(closes, dtype=float)
        except Exception:
            return "hold", 0.0
        if series.size < max(60, int(parameters.get("sma_slow", 40) or 40), 26):
            return "hold", 0.0

        rsi_buy = float(parameters.get("rsi_buy"))
        rsi_sell = float(parameters.get("rsi_sell"))
        sma_fast = int(parameters.get("sma_fast"))
        sma_slow = int(parameters.get("sma_slow"))
        band_tol = float(parameters.get("band_tolerance"))
        entry_z = float(parameters.get("entry_threshold"))
        trend_threshold = float(parameters.get("trend_threshold"))
        decision_threshold = float(parameters.get("decision_threshold"))

        current = float(series[-1])

        def _sma(arr: np.ndarray, period: int) -> float:
            if arr.size == 0:
                return 0.0
            if period <= 0:
                return float(arr[-1])
            if arr.size < period:
                return float(np.mean(arr))
            return float(np.mean(arr[-period:]))

        def _rsi(arr: np.ndarray, period: int = 14) -> float:
            if arr.size < period + 1:
                return 50.0
            delta = np.diff(arr)
            recent = delta[-period:]
            gains = float(recent[recent > 0].sum() / period)
            losses = float((-recent[recent < 0]).sum() / period)
            if losses <= 0:
                return 100.0
            rs = gains / losses
            return float(100.0 - (100.0 / (1.0 + rs)))

        def _bollinger(arr: np.ndarray, period: int = 20, k: float = 2.0) -> tuple[float, float, float]:
            if arr.size < period:
                last = float(arr[-1])
                return last, last, last
            window = arr[-period:]
            mid = float(np.mean(window))
            std = float(np.std(window))
            return mid + k * std, mid, mid - k * std

        def _macd(arr: np.ndarray) -> tuple[float, float]:
            if arr.size < 26:
                return 0.0, 0.0

            def ema(values: np.ndarray, period: int) -> float:
                if values.size < period:
                    return float(values[-1])
                alpha = 2.0 / (period + 1.0)
                e = float(np.mean(values[:period]))
                for v in values[period:]:
                    e = (float(v) - e) * alpha + e
                return e

            ema12 = ema(arr, 12)
            ema26 = ema(arr, 26)
            macd_val = ema12 - ema26
            signal = macd_val * 0.9
            return float(macd_val), float(signal)

        def _trend_regime(arr: np.ndarray) -> bool:
            if arr.size < max(sma_fast, sma_slow):
                return False
            fast = _sma(arr, sma_fast)
            slow = _sma(arr, sma_slow)
            if slow == 0:
                return False
            spread = abs(fast - slow) / abs(slow)
            return spread >= trend_threshold

        in_trend = _trend_regime(series)

        rsi = _rsi(series, 14)
        macd_val, macd_sig = _macd(series)
        sma_f = _sma(series, sma_fast)
        sma_s = _sma(series, sma_slow)
        bb_u, _bb_m, bb_l = _bollinger(series, 20)

        window = series[-60:]
        mean = float(np.mean(window))
        std = float(np.std(window))
        z = (current - mean) / std if std > 0 else 0.0

        buy_votes = 0.0
        sell_votes = 0.0

        ens_buy = 0.0
        ens_sell = 0.0
        if rsi < rsi_buy:
            ens_buy += 0.25
        elif rsi > rsi_sell:
            ens_sell += 0.25

        if macd_val > macd_sig:
            ens_buy += 0.25
        else:
            ens_sell += 0.25

        if current > sma_f > sma_s:
            ens_buy += 0.25
        elif current < sma_f < sma_s:
            ens_sell += 0.25

        if current < bb_l * (1.0 + 2.0 * band_tol):
            ens_buy += 0.25
        elif current > bb_u * (1.0 - 2.0 * band_tol):
            ens_sell += 0.25

        mr_buy = 0.0
        mr_sell = 0.0
        if current < bb_l * (1.0 + band_tol) and rsi < rsi_buy:
            mr_buy = min(0.9, (rsi_buy - rsi) / 20.0)
        elif current > bb_u * (1.0 - band_tol) and rsi > rsi_sell:
            mr_sell = min(0.9, (rsi - rsi_sell) / 20.0)

        mom_buy = 0.0
        mom_sell = 0.0
        if macd_val > macd_sig and current > sma_f > sma_s:
            mom_buy = min(0.85, abs(macd_val - macd_sig) * 10.0)
        elif macd_val < macd_sig and current < sma_f < sma_s:
            mom_sell = min(0.85, abs(macd_val - macd_sig) * 10.0)

        sa_buy = 0.0
        sa_sell = 0.0
        if z < -entry_z:
            sa_buy = min(0.9, abs(z) / 5.0)
        elif z > entry_z:
            sa_sell = min(0.9, abs(z) / 5.0)

        w_ens_raw = max(0.0, float(parameters.get("w_ensemble")))
        w_mom_raw = max(0.0, float(parameters.get("w_momentum")))
        w_mr_raw = max(0.0, float(parameters.get("w_meanrev")))
        w_sa_raw = max(0.0, float(parameters.get("w_statarb")))
        w_sum = w_ens_raw + w_mom_raw + w_mr_raw + w_sa_raw
        if w_sum <= 0:
            return "hold", 0.0
        w_ens = w_ens_raw / w_sum
        w_mom = w_mom_raw / w_sum
        w_mr = w_mr_raw / w_sum
        w_sa = w_sa_raw / w_sum

        if in_trend:
            buy_votes += w_ens * ens_buy + w_mom * mom_buy + 0.25 * w_mr * mr_buy + 0.25 * w_sa * sa_buy
            sell_votes += w_ens * ens_sell + w_mom * mom_sell + 0.25 * w_mr * mr_sell + 0.25 * w_sa * sa_sell
        else:
            buy_votes += w_ens * ens_buy + w_mr * mr_buy + w_sa * sa_buy + 0.25 * w_mom * mom_buy
            sell_votes += w_ens * ens_sell + w_mr * mr_sell + w_sa * sa_sell + 0.25 * w_mom * mom_sell

        if buy_votes >= decision_threshold and buy_votes > sell_votes:
            return "buy", min(1.0, float(buy_votes))
        if sell_votes >= decision_threshold and sell_votes > buy_votes:
            return "sell", min(1.0, float(sell_votes))
        return "hold", 0.0

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

        # Resolve execution cost model (supports Optuna-exported params for parity)
        parameters: dict[str, Any] = {}
        if hasattr(strategy, 'parameters') and strategy.parameters:
            parameters = strategy.parameters
        elif isinstance(strategy, dict) and isinstance(strategy.get('parameters'), dict):
            parameters = strategy['parameters']

        def _coerce_float(value: object) -> float | None:
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def _coerce_bool(value: object) -> bool:
            if isinstance(value, bool):
                return value
            if value is None:
                return False
            if isinstance(value, (int, float)):
                return value != 0
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "y", "on"}
            return False

        # Optuna feature toggles (off by default)
        use_optuna_position_size = _coerce_bool(parameters.get("use_optuna_position_size"))
        use_optuna_max_positions = _coerce_bool(parameters.get("use_optuna_max_positions"))
        use_optuna_min_position_dollars = _coerce_bool(parameters.get("use_optuna_min_position_dollars"))
        use_optuna_leverage = _coerce_bool(parameters.get("use_optuna_leverage")) or _coerce_bool(
            parameters.get("allow_leverage")
        )

        if use_optuna_position_size:
            max_position_size = _coerce_float(parameters.get("position_size_pct")) or max_position_size

        max_positions = risk_limits.get("max_positions", 1_000_000)
        if use_optuna_max_positions:
            max_positions = parameters.get("max_positions", max_positions)
        try:
            max_positions = int(max_positions)
        except (TypeError, ValueError):
            max_positions = 1_000_000

        min_position_dollars = 0.0
        if use_optuna_min_position_dollars:
            min_position_dollars = _coerce_float(parameters.get("min_position_dollars")) or 0.0

        slippage_pct = _coerce_float(risk_limits.get("slippage_pct"))
        if slippage_pct is None:
            slippage_bps = _coerce_float(parameters.get("slippage_bps"))
            if slippage_bps is not None:
                slippage_pct = slippage_bps / 10_000.0
        if slippage_pct is None:
            slippage_pct = _coerce_float(parameters.get("slippage_pct"))
        if slippage_pct is None:
            slippage_pct = 0.001  # 0.1% default slippage

        commission_per_trade = _coerce_float(parameters.get("commission_per_trade"))
        # P&L-019: Default commission is $1 per trade (not $0).
        if commission_per_trade is None:
            commission_per_trade = 1.0

        stop_loss_pct = _coerce_float(parameters.get("stop_loss_pct")) or 0.0
        risk_per_trade_pct = _coerce_float(parameters.get("risk_per_trade_pct")) or 0.0

        max_gross_exposure = 1.0
        if use_optuna_leverage:
            max_gross_exposure = _coerce_float(parameters.get("max_gross_exposure")) or 1.0

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
                if symbol not in portfolio.positions and len(portfolio.positions) >= max_positions:
                    continue

                # Optional gap guard (for optuna_meta overlays)
                prev_close = _coerce_float(signal.get("prev_close"))
                max_gap_pct = _coerce_float(signal.get("max_gap_pct"))
                if prev_close and max_gap_pct and prev_close > 0:
                    gap = abs(execution_price - prev_close) / prev_close
                    if gap > max_gap_pct:
                        continue

                # Calculate position size
                # Base sizing is a notional cap as fraction of equity.
                position_value = portfolio.total_equity * max_position_size

                # Optuna harness also supports risk-based sizing: size so that stop-loss implies
                # ~risk_per_trade_pct loss of equity. Apply only when both are present.
                if risk_per_trade_pct > 0 and stop_loss_pct > 0 and portfolio.total_equity > 0:
                    risk_budget_dollars = portfolio.total_equity * risk_per_trade_pct
                    risk_based_notional = risk_budget_dollars / stop_loss_pct
                    position_value = min(position_value, risk_based_notional)

                size_mult = _coerce_float(signal.get("size_mult")) or 1.0
                position_value *= max(0.0, size_mult)
                if position_value < min_position_dollars:
                    continue

                # Enforce max gross exposure (leverage cap)
                current_gross_exposure = 0.0
                if portfolio.total_equity > 0:
                    current_gross_exposure = portfolio.positions_value / portfolio.total_equity
                projected_exposure = (portfolio.positions_value + position_value) / max(
                    portfolio.total_equity, 1e-9
                )
                if projected_exposure > max_gross_exposure:
                    continue
                quantity = int(position_value / execution_price)

                if quantity > 0 and (portfolio.cash >= quantity * execution_price or use_optuna_leverage):
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
                            "entry_date": data.timestamp.date(),
                        }

                    trade = Trade(
                        symbol=symbol,
                        side="buy",
                        quantity=quantity,
                        entry_date=data.timestamp.date(),
                        entry_price=execution_price,
                        commission=commission_per_trade,
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
                        commission=commission_per_trade,
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

        parameters: dict[str, Any] = {}
        if hasattr(strategy, 'parameters') and strategy.parameters:
            parameters = strategy.parameters
        elif isinstance(strategy, dict) and isinstance(strategy.get('parameters'), dict):
            parameters = strategy['parameters']

        def _coerce_float(value: object) -> float | None:
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        commission_per_trade = _coerce_float(parameters.get("commission_per_trade"))
        # P&L-019: Default commission is $1 per trade (not $0).
        if commission_per_trade is None:
            commission_per_trade = 1.0

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
                        commission=commission_per_trade,
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
                        commission=commission_per_trade,
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
                engine=_extract_engine(bt.parameters),
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
                origin=_extract_origin(bt.parameters),
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
            engine=_extract_engine(backtest.parameters),
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
            origin=_extract_origin(backtest.parameters),
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
