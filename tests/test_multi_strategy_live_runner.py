from datetime import UTC, datetime

import pandas as pd

from backend.services.multi_strategy_live_runner import MultiStrategyLiveRunner
from backend.strategies.trading_strategies import SignalType, TradingSignal


class _StubDataClient:
    async def get_historical_data(self, symbol: str, timeframe: str, limit: int):
        # Minimal OHLCV frame
        n = max(60, limit)
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range(end=pd.Timestamp.utcnow(), periods=n, freq="D"),
                "open": [100.0] * n,
                "high": [101.0] * n,
                "low": [99.0] * n,
                "close": list(range(1, n + 1)),
                "volume": [1_000_000.0] * n,
            }
        )
        return df


class _StubOrderService:
    def __init__(self):
        self.seen_signals = None

    async def plan_and_submit(self, signals, strategy_engine=None, idempotency_key=None, portfolio_state=None):
        self.seen_signals = signals
        return []


def test_to_engine_signal_maps_direction_and_strength():
    runner = MultiStrategyLiveRunner(base_target_exposure=0.25, strong_exposure_multiplier=2.0)
    ts = datetime.now(UTC)

    buy = TradingSignal(symbol="AAPL", signal_type=SignalType.BUY, confidence=0.7, target_price=100.0)
    sell = TradingSignal(symbol="AAPL", signal_type=SignalType.SELL, confidence=0.7, target_price=100.0)
    strong_buy = TradingSignal(symbol="AAPL", signal_type=SignalType.STRONG_BUY, confidence=0.7, target_price=100.0)
    hold = TradingSignal(symbol="AAPL", signal_type=SignalType.HOLD, confidence=0.7, target_price=100.0)

    e_buy = runner._to_engine_signal(buy, source="momentum", ts=ts)
    e_sell = runner._to_engine_signal(sell, source="momentum", ts=ts)
    e_strong_buy = runner._to_engine_signal(strong_buy, source="momentum", ts=ts)
    e_hold = runner._to_engine_signal(hold, source="momentum", ts=ts)

    assert e_buy.target_exposure == 0.25
    assert e_sell.target_exposure == -0.25
    assert e_strong_buy.target_exposure == 0.5
    assert e_hold.target_exposure == 0.0


async def test_run_once_emits_engine_signals_and_calls_plan_and_submit(monkeypatch):
    runner = MultiStrategyLiveRunner()

    # Skip heavy feature engineering; provide a minimal features frame for strategies.
    def _features(_price_df: pd.DataFrame) -> pd.DataFrame:
        n = len(_price_df)
        return pd.DataFrame(
            {
                "rsi": [50.0] * n,
                "bb_upper": [110.0] * n,
                "bb_lower": [90.0] * n,
                "macd": [1.0] * n,
                "macd_signal": [0.5] * n,
                "sma_20": [95.0] * n,
                "sma_50": [90.0] * n,
                "atr": [1.0] * n,
                "atr_ratio": [0.01] * n,
            }
        )

    monkeypatch.setattr(runner, "_compute_features", _features)

    data_client = _StubDataClient()
    order_service = _StubOrderService()

    result = await runner.run_once(
        symbols=["AAPL"],
        lookback=80,
        timeframe="1Day",
        data_client=data_client,
        order_service=order_service,
    )

    assert result.symbols == ["AAPL"]
    assert result.engine_signals_count >= 1
    assert order_service.seen_signals is not None
    assert all(getattr(s, "symbol", None) == "AAPL" for s in order_service.seen_signals)
