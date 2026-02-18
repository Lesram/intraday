import pytest

from backend.models.backtest import Trade
from backend.services.backtest_service import BacktestService


class _MD:
    def __init__(self, open_price: float, close_price: float):
        import pandas as pd

        self.open = open_price
        self.close = close_price
        self.timestamp = pd.Timestamp("2025-01-02", tz="UTC")


class _Portfolio:
    def __init__(self):
        self.cash = 10_000.0
        self.positions = {}

    @property
    def total_equity(self) -> float:
        return self.cash

    @property
    def positions_value(self) -> float:
        return 0.0


@pytest.mark.asyncio
async def test_execute_pending_signals_applies_optuna_slippage_and_commission():
    service = BacktestService.__new__(BacktestService)

    pending_signals = {"AAPL": {"action": "buy"}}
    market_data = {"AAPL": _MD(open_price=100.0, close_price=101.0)}
    portfolio = _Portfolio()

    class _Strategy:
        risk_limits = {"max_position_size": 0.1}
        parameters = {"slippage_bps": 8.5, "commission_per_trade": 0.3}

    trades = service._execute_pending_signals(
        pending_signals=pending_signals,
        market_data=market_data,
        portfolio=portfolio,
        strategy=_Strategy(),
    )

    assert len(trades) == 1
    trade: Trade = trades[0]
    assert trade.side == "buy"
    assert trade.commission == 0.3

    # Slippage is adverse: buy at open * (1 + slippage_pct)
    expected_price = 100.0 * (1 + (8.5 / 10_000.0))
    assert trade.entry_price == pytest.approx(expected_price, rel=1e-12)
