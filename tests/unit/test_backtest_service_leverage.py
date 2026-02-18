import pytest

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


class _Strategy:
    risk_limits = {"max_position_size": 0.1}
    parameters = {}


@pytest.mark.asyncio
async def test_execute_pending_signals_respects_leverage_flag():
    service = BacktestService.__new__(BacktestService)

    pending_signals = {"AAPL": {"action": "buy"}}
    market_data = {"AAPL": _MD(open_price=100.0, close_price=101.0)}
    portfolio = _Portfolio()

    # Without leverage: using optuna position_size_pct=1.2 should be blocked by max_gross_exposure=1.0
    strategy = _Strategy()
    strategy.parameters = {
        "use_optuna_position_size": True,
        "position_size_pct": 1.2,
        "allow_leverage": False,
        "use_optuna_leverage": False,
        "max_gross_exposure": 2.0,
    }

    trades = service._execute_pending_signals(
        pending_signals=pending_signals,
        market_data=market_data,
        portfolio=portfolio,
        strategy=strategy,
    )

    assert trades == []

    # With leverage enabled: allow exposure above 1x
    strategy.parameters["allow_leverage"] = True
    strategy.parameters["use_optuna_leverage"] = True

    trades = service._execute_pending_signals(
        pending_signals=pending_signals,
        market_data=market_data,
        portfolio=portfolio,
        strategy=strategy,
    )

    assert len(trades) == 1
    assert trades[0].side == "buy"
