import os
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from backend.features.feature_engineering import FeatureEngineer
from backend.risk.risk_manager import RiskManager
from backend.services.positions_service import PositionsService
from backend.strategies.engine import StrategyEngine
from backend.strategies.types import TradingSignal as EngineTradingSignal
from backend.utils.logger import get_logger

from backend.strategies.trading_strategies import (
    BreakoutStrategy,
    MeanReversionStrategy,
    MomentumStrategy,
    RegimeFilteredMomentumStrategy,
    SignalType,
    StatisticalArbitrageStrategy,
    TradingSignal as FrameworkTradingSignal,
)
from backend.strategies.advanced_strategies import (
    AdaptiveRegimeMomentumStrategy,
    OrderFlowImbalanceStrategy,
    VolatilityStructureStrategy,
    CrossSectionalMomentumStrategy,
    MicrostructureAlphaStrategy,
)

# ---------------------------------------------------------------------------
# P&L-007: Minimum average daily volume to consider a symbol liquid enough
# ---------------------------------------------------------------------------
MIN_AVG_VOLUME_DEFAULT = 50_000


logger = get_logger(__name__)


@dataclass(frozen=True)
class MultiStrategyRunResult:
    symbols: list[str]
    engine_signals_count: int
    engine_signals: list[EngineTradingSignal]
    submitted: list[dict[str, Any]]
    timestamp: str


class MultiStrategyLiveRunner:
    """Generate multiple strategy signals and route them through StrategyEngine + OrderService.

    This is intentionally conservative and stateless:
    - It does not maintain per-strategy position state.
    - It relies on the existing outbox/OrderService pipeline for execution.
    """

    def __init__(
        self,
        *,
        base_target_exposure: float | None = None,
        strong_exposure_multiplier: float | None = None,
        feature_mode: str | None = None,
        risk_manager: RiskManager | None = None,
        min_avg_volume: int | None = None,
    ):
        self.base_target_exposure = base_target_exposure if base_target_exposure is not None else float(
            os.getenv("MULTI_STRATEGY_BASE_TARGET_EXPOSURE", "0.25")
        )
        self.strong_exposure_multiplier = strong_exposure_multiplier if strong_exposure_multiplier is not None else float(
            os.getenv("MULTI_STRATEGY_STRONG_EXPOSURE_MULTIPLIER", "2.0")
        )
        self.feature_mode = feature_mode or os.getenv("MULTI_STRATEGY_FEATURE_MODE", "realtime_light")
        # Reuse a single RiskManager instance for all strategies
        self._risk_manager = risk_manager or RiskManager()

        if self.base_target_exposure <= 0 or self.base_target_exposure > 1:
            raise ValueError("base_target_exposure must be in (0, 1]")
        if self.strong_exposure_multiplier <= 0:
            raise ValueError("strong_exposure_multiplier must be > 0")

        # P&L-007: Minimum average daily volume filter
        self.min_avg_volume = min_avg_volume if min_avg_volume is not None else int(
            os.getenv("MULTI_STRATEGY_MIN_AVG_VOLUME", str(MIN_AVG_VOLUME_DEFAULT))
        )

        # P&L-009: Persist strategy instances across ticks so they retain
        # internal state (e.g. warm-up buffers, regime estimates).
        self._strategies: dict[str, Any] = self._build_strategy_instances()

        # P&L-005: Rolling signal direction history per (symbol, strategy)
        # for cross-strategy correlation tracking (30-bar window).
        self._signal_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=30))

    # ------------------------------------------------------------------
    # P&L-009: Build strategy instances once, reuse across ticks
    # ------------------------------------------------------------------
    def _build_strategy_instances(self) -> dict[str, Any]:
        rm = self._risk_manager
        return {
            "momentum": MomentumStrategy(rm),
            "mean_reversion": MeanReversionStrategy(rm),
            "stat_arb": StatisticalArbitrageStrategy(rm),
            "regime_momentum": RegimeFilteredMomentumStrategy(rm),
            "breakout": BreakoutStrategy(rm),
            "adaptive_regime": AdaptiveRegimeMomentumStrategy(rm),
            "order_flow": OrderFlowImbalanceStrategy(rm),
            "vol_structure": VolatilityStructureStrategy(rm),
            "cross_momentum": CrossSectionalMomentumStrategy(rm),
            "microstructure": MicrostructureAlphaStrategy(rm),
        }

    async def run_once(
        self,
        *,
        symbols: list[str],
        lookback: int = 200,
        timeframe: str = "1Day",
        data_client: Any,
        order_service: Any,
        strategy_engine: StrategyEngine | None = None,
        portfolio_state: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> MultiStrategyRunResult:
        if not symbols:
            return MultiStrategyRunResult(
                symbols=[],
                engine_signals_count=0,
                engine_signals=[],
                submitted=[],
                timestamp=datetime.now(UTC).isoformat(),
            )

        engine = strategy_engine or StrategyEngine(
            risk_manager=RiskManager(),
            positions_service=PositionsService(),
        )

        all_engine_signals: list[EngineTradingSignal] = []
        now = datetime.now(UTC)

        for symbol in symbols:
            price_df = await self._fetch_price_df(
                symbol=symbol,
                data_client=data_client,
                lookback=lookback,
                timeframe=timeframe,
            )
            if price_df.empty:
                continue

            # P&L-032: Data freshness validation — reject stale bars.
            # If the latest bar timestamp is more than 3 days old (allowing for
            # weekends/holidays), log a warning and skip.
            if "timestamp" in price_df.columns:
                try:
                    last_ts = pd.Timestamp(price_df["timestamp"].iloc[-1])
                    if last_ts.tzinfo is None:
                        last_ts = last_ts.tz_localize("UTC")
                    staleness = (now - last_ts).total_seconds()
                    max_stale = float(os.getenv("MULTI_STRATEGY_MAX_STALE_SECONDS", str(3 * 86400)))
                    if staleness > max_stale:
                        logger.warning(
                            "Stale data detected, skipping symbol",
                            extra={"symbol": symbol, "last_bar": str(last_ts), "stale_seconds": staleness},
                        )
                        continue
                except Exception:
                    pass  # Non-datetime timestamps: skip check

            # P&L-007: Skip illiquid symbols
            avg_vol = float(price_df["volume"].tail(20).mean()) if len(price_df) >= 20 else float(price_df["volume"].mean())
            if avg_vol < self.min_avg_volume:
                logger.info(
                    "Skipping illiquid symbol",
                    extra={"symbol": symbol, "avg_volume": avg_vol, "min_required": self.min_avg_volume},
                )
                continue

            features_df = self._compute_features(price_df)

            strategy_signals = await self._generate_strategy_signals(
                symbol=symbol,
                price_df=price_df,
                features_df=features_df,
            )

            # Snapshot metadata used by the living policy loop
            close_now = float(price_df["close"].iloc[-1])
            bar_ts = price_df["timestamp"].iloc[-1]
            sma_50 = None
            atr_ratio = None
            try:
                if "sma_50" in features_df.columns:
                    sma_50 = float(features_df["sma_50"].iloc[-1])
            except Exception:
                sma_50 = None
            try:
                if "atr_ratio" in features_df.columns:
                    atr_ratio = float(features_df["atr_ratio"].iloc[-1])
            except Exception:
                atr_ratio = None

            for source, fw_signal in strategy_signals.items():
                try:
                    engine_signal = self._to_engine_signal(
                        fw_signal,
                        source=source,
                        ts=now,
                        extra_metadata={
                            "price_close": close_now,
                            "bar_timestamp": bar_ts,
                            "timeframe": timeframe,
                            "sma_50": sma_50,
                            "atr_ratio": atr_ratio,
                        },
                    )
                    all_engine_signals.append(engine_signal)
                except Exception as e:
                    logger.warning(
                        "Failed to convert framework signal to engine signal",
                        extra={
                            "symbol": symbol,
                            "source": source,
                            "error": str(e),
                        },
                    )

        if not all_engine_signals:
            return MultiStrategyRunResult(
                symbols=symbols,
                engine_signals_count=0,
                engine_signals=[],
                submitted=[],
                timestamp=datetime.now(UTC).isoformat(),
            )

        submitted = await order_service.plan_and_submit(
            all_engine_signals,
            strategy_engine=engine,
            idempotency_key=idempotency_key,
            portfolio_state=portfolio_state,
        )

        return MultiStrategyRunResult(
            symbols=symbols,
            engine_signals_count=len(all_engine_signals),
            engine_signals=all_engine_signals,
            submitted=submitted,
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def _fetch_price_df(
        self,
        *,
        symbol: str,
        data_client: Any,
        lookback: int,
        timeframe: str,
    ) -> pd.DataFrame:
        if hasattr(data_client, "get_historical_bars_df"):
            df = await data_client.get_historical_bars_df(
                symbol, lookback=lookback, timeframe=timeframe
            )
            return self._normalize_ohlcv_df(df)

        if hasattr(data_client, "get_historical_data"):
            df = await data_client.get_historical_data(symbol, timeframe=timeframe, limit=lookback)
            return self._normalize_ohlcv_df(df)

        raise ValueError("Unsupported data_client: missing get_historical_bars_df/get_historical_data")

    def _normalize_ohlcv_df(self, df: Any) -> pd.DataFrame:
        if df is None:
            return pd.DataFrame()
        if not isinstance(df, pd.DataFrame):
            try:
                df = pd.DataFrame(df)
            except Exception:
                return pd.DataFrame()

        if df.empty:
            return df

        col_map = {
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
        df = df.rename(columns=col_map)

        required = ["open", "high", "low", "close", "volume"]
        if any(c not in df.columns for c in required):
            missing = [c for c in required if c not in df.columns]
            raise ValueError(f"Missing OHLCV columns: {missing}")

        if "timestamp" not in df.columns:
            # If index is datetime-like, promote it; otherwise synthesize.
            try:
                df = df.reset_index().rename(columns={"index": "timestamp"})
            except Exception:
                df["timestamp"] = list(range(len(df)))

        df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        return df

    def _compute_features(self, price_df: pd.DataFrame) -> pd.DataFrame:
        engineer = FeatureEngineer(
            config={
                "feature_mode": self.feature_mode,
                "enable_heavy_features": False,
                "enable_autocorr_features": False,
            }
        )
        return engineer.compute_technical_indicators(price_df)

    async def _generate_strategy_signals(
        self,
        *,
        symbol: str,
        price_df: pd.DataFrame,
        features_df: pd.DataFrame,
    ) -> dict[str, FrameworkTradingSignal]:
        # P&L-009: Reuse persisted strategy instances
        strategies = self._strategies

        results: dict[str, FrameworkTradingSignal] = {}
        for name, strategy in strategies.items():
            try:
                results[name] = await strategy.generate_signal(symbol, price_df, features_df)
            except Exception as e:
                logger.warning(
                    "Strategy generate_signal failed",
                    extra={"symbol": symbol, "strategy": name, "error": str(e)},
                )

        # P&L-005: Record signal directions and detect correlated strategies
        self._record_signal_directions(symbol, results)

        return results

    # ------------------------------------------------------------------
    # P&L-005: Rolling signal correlation tracking
    # ------------------------------------------------------------------
    def _record_signal_directions(
        self,
        symbol: str,
        signals: dict[str, FrameworkTradingSignal],
    ) -> None:
        """Track per-strategy signal directions and log when strategies are highly correlated."""
        for name, sig in signals.items():
            key = f"{symbol}:{name}"
            if sig.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                direction = 1.0
            elif sig.signal_type in (SignalType.SELL, SignalType.STRONG_SELL):
                direction = -1.0
            else:
                direction = 0.0
            self._signal_history[key].append(direction)

        # Check pairwise correlation when we have enough history
        strategy_names = list(signals.keys())
        for i, name_a in enumerate(strategy_names):
            hist_a = self._signal_history.get(f"{symbol}:{name_a}")
            if hist_a is None or len(hist_a) < 10:
                continue
            for name_b in strategy_names[i + 1:]:
                hist_b = self._signal_history.get(f"{symbol}:{name_b}")
                if hist_b is None or len(hist_b) < 10:
                    continue
                min_len = min(len(hist_a), len(hist_b))
                arr_a = np.array(list(hist_a)[-min_len:])
                arr_b = np.array(list(hist_b)[-min_len:])
                if np.std(arr_a) < 1e-9 or np.std(arr_b) < 1e-9:
                    continue
                corr = float(np.corrcoef(arr_a, arr_b)[0, 1])
                if abs(corr) > 0.8:
                    logger.warning(
                        "High signal correlation detected — consider halving weight of one strategy",
                        extra={
                            "symbol": symbol,
                            "strategy_a": name_a,
                            "strategy_b": name_b,
                            "correlation": round(corr, 3),
                        },
                    )

    def _to_engine_signal(
        self,
        signal: FrameworkTradingSignal,
        *,
        source: str,
        ts: datetime,
        extra_metadata: dict[str, Any] | None = None,
    ) -> EngineTradingSignal:
        direction = 0.0
        magnitude = self.base_target_exposure

        if signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
            direction = 1.0
        elif signal.signal_type in (SignalType.SELL, SignalType.STRONG_SELL):
            direction = -1.0
        else:
            direction = 0.0

        if signal.signal_type in (SignalType.STRONG_BUY, SignalType.STRONG_SELL):
            magnitude = min(1.0, magnitude * self.strong_exposure_multiplier)

        target_exposure = float(max(-1.0, min(1.0, direction * magnitude)))
        confidence = float(max(0.0, min(1.0, signal.confidence)))

        metadata = dict(getattr(signal, "metadata", {}) or {})
        if extra_metadata:
            # Do not overwrite strategy-provided keys.
            for k, v in extra_metadata.items():
                metadata.setdefault(k, v)

        return EngineTradingSignal(
            symbol=signal.symbol,
            source=source,
            ts=ts,
            target_exposure=target_exposure,
            confidence=confidence,
            metadata=metadata,
        )
