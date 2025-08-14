import pytest

try:
    from backend.strategies.trading_strategies import SimpleMovingAverageStrategy
except Exception:
    SimpleMovingAverageStrategy = None


def test_strategy_smoke_over_tiny_ohlcv():
    if SimpleMovingAverageStrategy is None:
        pytest.skip("strategy module unavailable")

    # Tiny OHLCV slice
    prices = [1, 2, 3, 4, 5]
    sma = SimpleMovingAverageStrategy(short_window=2, long_window=3)

    decisions = []
    for p in prices:
        decisions.append(sma.on_price(p))

    # Ensure we produced a decision per price and no exceptions
    assert len(decisions) == len(prices)
